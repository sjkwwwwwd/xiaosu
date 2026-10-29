# 小黍 · LangGraph 聊天机器人（网页版）

打开网页就能聊天。**内置免费模型，零配置**；也可以随时在页面上换成自己的 API 或本地 Ollama。

公网地址：<https://xiaoshu-chat.app.workbuddy.host/?sharecode=DKGYLXPFHX>

骨架来自 B 站《Agent 智能体开发系统教程》第 69–74 集：
**StateGraph + 检查点记忆 + 流式输出 + FastAPI**。

## 启动

```bash
.venv/Scripts/python.exe run.py
```

浏览器会自动打开 http://127.0.0.1:8000

## 三条模型通道

点右上角的模型徽章就能打开设置面板，三种通道任选：

### 1. 内置免费（默认，开箱即用）

不用注册、不用填任何东西。走第三方公共服务 `text.pollinations.ai`，模型 `gpt-oss-20b`，
支持多轮和流式。

代价：约 4 次/分钟的限速，且属于他人提供的公共服务，稳定性和可用性不保证。
适合试玩和演示，正式使用建议换下面的通道。

### 2. 自定义 API（推荐正式使用）

填三样东西：接口地址、API Key、模型名。点「拉取列表」会自动拉取该服务商真实可用的模型，
不用手抄模型名。内置了五个预设：

| 服务商 | 地址 | 备注 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | 国内直连，便宜 |
| 硅基流动 | `https://api.siliconflow.cn/v1` | 国内，有免费模型 |
| OpenRouter | `https://openrouter.ai/api/v1` | 带 `:free` 后缀的免费 |
| Groq | `https://api.groq.com/openai/v1` | 速度快 |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 阿里云百炼 |

只要是 OpenAI 兼容接口都能接，不止这五家。

### 3. 本地 Ollama（完全免费、不限次数）

装好 [Ollama](https://ollama.com/download) 后：

```bash
ollama pull qwen2.5:3b
```

在设置面板点「检测」，会列出本机已下载的模型。全部跑在自己电脑上，不花钱、不联网、不限次数。

## 会话与历史

左下角有「会话」按钮，列出所有聊过的对话，按最近活跃排序，点一下就能切回去。
鼠标悬浮到某条上会出现 ×，可以单独删除（记录不可恢复）。

- 对话内容存在 `chat.db` 的检查点表里，`thread_id` 就是会话 ID。
- 会话索引（标题 + 最近活跃时间）单独存在 `chat_threads` 表。
  为什么不直接用 LangGraph 的 `checkpoints` 表？因为它的 `checkpoint_id` 是 UUID，
  按它排序等于乱序，做不了「最近对话」。
- 标题取第一条用户消息的前 28 个字，之后不再覆盖。
- 旧版本留下的、还没进索引的会话，启动时会自动补录一次。

## 配置存在哪

- 模型配置存在浏览器 `localStorage`，换浏览器要重设。
- API Key **只随请求发给本机后端做一次转发**，不写文件、不进日志、不落库。
- `.env` 里的 `DEEPSEEK_API_KEY` 是可选的：填了就用它当默认通道，不填就走内置免费。

## 目录结构

```
langgraph-chatbot/
├── main.py            FastAPI：/api/chat 流式、/api/providers、/api/models、/api/ollama/models
├── providers.py       三条通道的统一流式实现 + 错误翻译
├── graph.py           LangGraph 图：状态、节点、检查点、流式封装
├── config.py          提示词、历史长度、默认通道
├── run.py             启动入口（本地开浏览器 / 云端读 PORT）
├── static/
│   ├── index.html     聊天界面 + 左下角设置面板（原生实现，无 CDN 依赖）
│   ├── avatar.gif     小黍的头像（由 Wallpaper Engine 壁纸预览压缩而来）
│   └── avatar.png     favicon
├── chat.db            对话持久化（SQLite，首次启动自动创建）
└── .env               可选配置
```

## 部署到公网

云端平台会注入 `PORT` 环境变量，所以启动命令必须用 `python run.py`——
它会读 `PORT` 并绑定 `0.0.0.0`；本地没有 `PORT` 时自动退回 `127.0.0.1:8000` 并打开浏览器。

依赖安装：`python -m pip install -r requirements.txt`

注意：会话存在容器内的 `chat.db` 里。**同一次部署内重启进程历史不丢**，但重新发布会重新上传文件，
旧的 `chat.db` 可能被覆盖，所以别把线上实例当长期档案库用。

## 这张图长什么样

```
START ──> trim_history ──> chatbot ──> END
            (修剪历史)      (调模型)
```

- `trim_history`：超过 `MAX_HISTORY_MESSAGES` 条就删掉最早的，用 `RemoveMessage` 配合 `add_messages` reducer。
- `chatbot`：从 contextvar 取本次请求的模型配置 → 流式调用 → 一边用 `get_stream_writer()` 推 token 给前端，一边累积成完整回复写回状态。
- `InMemorySaver` 做检查点，`thread_id` 就是会话 ID。

模型之所以能在运行时切换，是因为配置放在 `contextvars` 里而不是全局变量——
这样多个会话并发时各自的模型互不干扰。

## 和技术点的对应关系

| 课程内容 | 代码位置 |
|---|---|
| 消息类型 / 系统提示词 | `graph.py` 的 `_to_openai_messages()`、`config.SYSTEM_PROMPT` |
| StateGraph 工作流 | `graph.py` 的 `build_graph()` |
| 记忆与持久化 | `compile(checkpointer=InMemorySaver())` + `thread_id` |
| 历史消息修剪 | `graph.py` 的 `trim_history()` |
| 流式调用 | `graph.py` 的 `stream_chat()`（`stream_mode="custom"`） |
| FastAPI 对外服务 | `main.py` |

## 想继续往下做

**对话存储**：默认落 `chat.db`（SQLite，WAL 模式），想换位置就设环境变量 `DB_PATH`。
想清空所有历史，停掉服务后删掉 `chat.db`、`chat.db-wal`、`chat.db-shm` 即可。

**加工具调用**（第 75–78 集）：`chatbot` 节点里绑定工具，再加一个 `tools` 节点和条件边。

**加 RAG**（第 31–46 集）：在 `trim_history` 和 `chatbot` 之间插一个 `retrieve` 节点。

## 常见问题

| 现象 | 原因 |
|---|---|
| 提示"密钥无效" | Key 填错或已失效，去服务商后台重新生成 |
| 提示"触发限流" | 内置免费通道用太密，等一会儿或换通道 |
| 提示"连不上接口地址" | base_url 写错，注意要带 `/v1` |
| 检测不到 Ollama | 没装或没启动，终端跑 `ollama serve` |
| 回复一半断了 | 关页面会中断流，节点没跑完状态不保存，重新发一次即可 |
| 端口被占用 | `run.py` 里把 `port=8000` 改成 8001 |
