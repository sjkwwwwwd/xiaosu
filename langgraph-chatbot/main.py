"""FastAPI 服务：聊天接口 + SSE 流式 + 网页 + 模型通道管理。

对应课程第 22 集「FastAPI 对外提供服务」和第 57 集「流式调用」。

关于密钥：前端把 key 随请求发过来，只在本次转发中用到，
不写文件、不进日志、不做任何持久化。
"""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
import providers
from graph import (
    close_graph,
    delete_thread,
    get_history,
    init_graph,
    list_threads,
    stream_chat,
    touch_thread,
)

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    """启动时打开 SQLite 检查点，关闭时释放连接。"""
    await init_graph()
    yield
    await close_graph()


app = FastAPI(
    title="小黍 · LangGraph 聊天机器人", version="2.2.0", lifespan=lifespan
)

# 头像等静态资源
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class ProviderPayload(BaseModel):
    kind: str = Field(default="free", description="free | openai | ollama")
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.7

    def to_config(self) -> providers.ProviderConfig:
        return providers.ProviderConfig(
            kind=self.kind if self.kind in {"free", "openai", "ollama"} else "free",
            base_url=self.base_url.strip(),
            api_key=self.api_key.strip(),
            model=self.model.strip(),
            temperature=self.temperature,
        )


class ChatRequest(BaseModel):
    message: str
    thread_id: str
    provider: ProviderPayload | None = None


def sse(payload: dict) -> str:
    """包装成 Server-Sent Events 格式。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/")
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
def health() -> dict:
    default = config.default_provider()
    return {
        "ok": True,
        "default_kind": default.kind,
        "default_label": default.label,
        "storage": "sqlite",
        "db": Path(config.DB_PATH).name,
    }


@app.get("/api/providers")
def provider_list() -> dict:
    """预设服务商 + 各通道说明，前端用来自动填充表单。"""
    return {
        "presets": providers.PRESETS,
        "free": {
            "label": providers.FREE_MODEL_LABEL,
            "note": "无需注册和密钥，公共服务，约 4 次/分钟",
        },
    }


@app.get("/api/models")
async def models(
    base_url: str = Query(...), api_key: str = Query(default="")
) -> dict:
    """动态拉取服务商的模型列表，避免前端写死过时的模型名。"""
    try:
        items = await providers.list_models(base_url, api_key)
        return {"ok": True, "models": items}
    except providers.ProviderError as exc:
        return {"ok": False, "error": exc.message, "models": []}


@app.get("/api/ollama/models")
async def ollama_models(
    base_url: str = Query(default="http://127.0.0.1:11434"),
) -> dict:
    try:
        items = await providers.list_ollama_models(base_url)
        return {"ok": True, "models": items}
    except providers.ProviderError as exc:
        return {"ok": False, "error": exc.message, "models": []}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    message = req.message.strip()
    if not message:
        return StreamingResponse(iter([sse({"type": "error", "message": "消息不能为空"})]))

    cfg = req.provider.to_config() if req.provider else config.default_provider()

    async def event_stream():
        try:
            async for token in stream_chat(message, req.thread_id, cfg):
                yield sse({"type": "delta", "content": token})
            # 对话成功后才记入会话索引，失败的轮次不污染列表
            await touch_thread(req.thread_id, message)
            yield sse({"type": "done"})
        except providers.ProviderError as exc:
            yield sse({"type": "error", "message": exc.message, "status": exc.status})
        except Exception as exc:  # 兜底，别让前端一直转圈
            yield sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/history/{thread_id}")
async def history(thread_id: str) -> dict:
    return {"messages": await get_history(thread_id)}


@app.get("/api/threads")
async def threads() -> dict:
    """会话列表，按最近活跃排序。"""
    return {"threads": await list_threads()}


@app.delete("/api/threads/{thread_id}")
async def remove_thread(thread_id: str) -> dict:
    await delete_thread(thread_id)
    return {"ok": True}


@app.post("/api/reset")
def reset() -> dict:
    """开一个新会话：换 thread_id 即可，旧记忆自然被隔离。"""
    return {"thread_id": str(uuid.uuid4())}
