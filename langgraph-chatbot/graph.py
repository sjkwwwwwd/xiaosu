"""LangGraph 对话图（SQLite 持久化版）。

节点职责：
  trim_history   只保留最近 N 条消息，防止上下文无限膨胀
  chatbot        调用模型，流式产出并累积成完整回复写回状态
  检查点         以 thread_id 为键，把每轮状态持久化到 SQLite

图的形状：

    START -> trim_history -> chatbot -> END

区别只在检查点：从进程内内存换成 SQLite 文件，
服务重启后对话历史依然在（同一个 thread_id 就能接着聊）。
"""

from __future__ import annotations

import contextvars
import time
from pathlib import Path
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, MessagesState, StateGraph

import config
import providers

# 每次请求各自的模型配置。用 contextvar 而不是全局变量，
# 这样多个会话并发时互不干扰。
_current_provider: contextvars.ContextVar[providers.ProviderConfig] = contextvars.ContextVar(
    "current_provider"
)

# 图和数据库连接都是延迟初始化的：AsyncSqliteSaver 必须在事件循环里创建
graph = None
_conn = None


# --------------------------------------------------------------------------
# 1. 节点函数
# --------------------------------------------------------------------------
def trim_history(state: MessagesState) -> dict[str, Any]:
    """历史消息修剪：只保留最近 N 条，防止上下文无限膨胀。

    用 RemoveMessage 删除，而不是返回新列表——
    messages 字段挂了 add_messages reducer，直接返回会被追加而不是覆盖。
    """
    messages = state["messages"]
    if len(messages) <= config.MAX_HISTORY_MESSAGES:
        return {}

    kept = messages[-config.MAX_HISTORY_MESSAGES :]
    # 修剪后开头可能是孤零零的 AI 回复，往前对齐到人类消息
    while kept and not isinstance(kept[0], HumanMessage):
        kept = kept[1:]

    removed_count = len(messages) - len(kept)
    return {"messages": [RemoveMessage(id=m.id) for m in messages[:removed_count]]}


def _to_openai_messages(messages: list) -> list[dict[str, str]]:
    """把 LangChain 消息转成各通道通用的 {role, content} 结构。"""
    out: list[dict[str, str]] = [{"role": "system", "content": config.SYSTEM_PROMPT}]
    for m in messages:
        if isinstance(m, HumanMessage):
            role = "user"
        elif isinstance(m, AIMessage):
            role = "assistant"
        elif isinstance(m, SystemMessage):
            role = "system"
        else:
            continue
        if isinstance(m.content, str) and m.content.strip():
            out.append({"role": role, "content": m.content})
    return out


async def chatbot(state: MessagesState) -> dict[str, Any]:
    """核心对话节点：取本次请求的模型配置，流式产出并累积成完整回复。"""
    cfg = _current_provider.get()
    writer = get_stream_writer()

    payload = _to_openai_messages(state["messages"])
    parts: list[str] = []

    async for token in providers.stream_chat(cfg, payload):
        parts.append(token)
        # 一边推给前端，一边攒起来最后写回状态
        writer({"type": "delta", "content": token})

    answer = "".join(parts)
    return {"messages": [AIMessage(content=answer)]}


# --------------------------------------------------------------------------
# 2. 组装图
# --------------------------------------------------------------------------
def build_graph(checkpointer):
    builder = StateGraph(MessagesState)

    builder.add_node("trim_history", trim_history)
    builder.add_node("chatbot", chatbot)

    builder.add_edge(START, "trim_history")
    builder.add_edge("trim_history", "chatbot")
    builder.add_edge("chatbot", END)

    return builder.compile(checkpointer=checkpointer)


# --------------------------------------------------------------------------
# 3. 生命周期：启动时建库，关闭时释放连接
# --------------------------------------------------------------------------
async def init_graph(db_path: str | None = None) -> None:
    """建立 SQLite 连接与检查点。必须在事件循环里调用（FastAPI lifespan）。"""
    global graph, _conn
    if graph is not None:
        return

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    import aiosqlite

    path = db_path or config.DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    _conn = await aiosqlite.connect(path)
    # WAL 模式：读写并发更稳，避免聊天时偶发 database is locked
    await _conn.execute("PRAGMA journal_mode=WAL")
    await _conn.commit()

    saver = AsyncSqliteSaver(_conn)
    await saver.setup()  # 建检查点表

    # 会话索引表：LangGraph 自己的 checkpoints 表按 checkpoint_id（UUID）排序不可靠，
    # 所以单独维护一份「谁最近聊过」的索引，用于侧边的会话列表。
    await _conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_threads (
            thread_id  TEXT PRIMARY KEY,
            title      TEXT NOT NULL DEFAULT '',
            updated_at REAL NOT NULL DEFAULT 0
        )
        """
    )
    await _conn.commit()

    graph = build_graph(saver)

    # 兼容旧数据：之前存的会话还没进索引表，补录一下，免得列表里看不到
    await _migrate_legacy_threads()


async def close_graph() -> None:
    global graph, _conn
    if _conn is not None:
        await _conn.close()
    _conn = None
    graph = None


async def _migrate_legacy_threads() -> None:
    """把已有检查点里、但还没进 chat_threads 的会话补录进索引。

    只在新版本第一次启动时真正有活干，之后 SELECT 结果为空，开销可忽略。
    """
    if _conn is None or graph is None:
        return
    try:
        cur = await _conn.execute(
            "SELECT DISTINCT thread_id FROM checkpoints "
            "WHERE thread_id NOT IN (SELECT thread_id FROM chat_threads)"
        )
        rows = await cur.fetchall()
        await cur.close()
        for row in rows:
            tid = row[0]
            if not tid:
                continue
            msgs = await get_history(tid)
            title = next((m["content"] for m in msgs if m["role"] == "user"), "")
            await touch_thread(tid, title)
    except Exception:
        # 补录失败不影响正常使用，忽略即可
        pass


# --------------------------------------------------------------------------
# 4. 供上层调用的接口
# --------------------------------------------------------------------------
async def stream_chat(
    message: str, thread_id: str, provider_cfg: providers.ProviderConfig
) -> AsyncIterator[str]:
    """异步流式对话，逐 token 吐出文本。

    stream_mode="custom" 接收的是节点里 get_stream_writer() 写出的内容，
    所以不管底层是哪家模型，上层拿到的格式都一样。
    """
    if graph is None:
        raise RuntimeError("对话图还没初始化")

    token = _current_provider.set(provider_cfg)
    try:
        inputs = {"messages": [HumanMessage(content=message)]}
        cfg = {"configurable": {"thread_id": thread_id}}

        async for chunk in graph.astream(inputs, config=cfg, stream_mode="custom"):
            if isinstance(chunk, dict) and chunk.get("type") == "delta":
                text = chunk.get("content")
                if text:
                    yield text
    finally:
        _current_provider.reset(token)


async def get_history(thread_id: str) -> list[dict[str, str]]:
    """读取某个会话的历史（从 SQLite 里读，重启后依然有效）。"""
    if graph is None:
        return []

    cfg = {"configurable": {"thread_id": thread_id}}
    snapshot = await graph.aget_state(cfg)
    if not snapshot or not snapshot.values:
        return []

    out: list[dict[str, str]] = []
    for m in snapshot.values.get("messages", []):
        role = {"human": "user", "ai": "assistant"}.get(m.type)
        if role and isinstance(m.content, str) and m.content:
            out.append({"role": role, "content": m.content})
    return out


async def touch_thread(thread_id: str, first_message: str = "") -> None:
    """记录会话活跃时间与标题。标题只在第一次写入，后续不覆盖。"""
    if _conn is None:
        return
    title = (first_message or "").strip().replace("\n", " ")[:28]
    await _conn.execute(
        """
        INSERT INTO chat_threads (thread_id, title, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(thread_id) DO UPDATE SET
            updated_at = excluded.updated_at,
            title = CASE WHEN chat_threads.title = ''
                         THEN excluded.title ELSE chat_threads.title END
        """,
        (thread_id, title, time.time()),
    )
    await _conn.commit()


async def list_threads(limit: int = 60) -> list[dict[str, Any]]:
    """按最近活跃排序的会话列表。"""
    if _conn is None:
        return []
    cur = await _conn.execute(
        "SELECT thread_id, title, updated_at FROM chat_threads "
        "ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    )
    rows = await cur.fetchall()
    await cur.close()
    return [
        {"thread_id": tid, "title": title or "新对话", "updated_at": ts}
        for tid, title, ts in rows
    ]


async def delete_thread(thread_id: str) -> None:
    """删除会话：检查点和索引一起清掉。"""
    if _conn is None or graph is None:
        return
    try:
        await graph.checkpointer.adelete_thread(thread_id)
    except Exception:
        pass
    await _conn.execute("DELETE FROM chat_threads WHERE thread_id = ?", (thread_id,))
    await _conn.commit()
