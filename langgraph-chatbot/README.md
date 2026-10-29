<p align="center">
  <img src="static/avatar.gif" width="104" alt="小黍" />
</p>

<h1 align="center">小黍</h1>

<p align="center">
  一个会记住你说过什么的中文聊天机器人<br/>
  双击打开就能聊，不用注册，不用配置
</p>

<p align="center">
  Python 3.10+ · FastAPI · LangGraph · SQLite · pywebview 桌面窗口
</p>

---

## 这是什么

小黍是一个自己搭的聊天机器人。它不依赖任何一家大模型厂商才能跑起来——
**默认内置一条免费通道，双击就能用**，想换成自己的 API 或者本地 Ollama 也可以，在窗口左下角点两下就行。

对话不是"聊完就忘"：每一轮都写进 SQLite，刷新页面、重启服务、关掉电脑再打开，历史都还在。

在线体验：**<https://xiaoshu-chat.app.workbuddy.host/?sharecode=DKGYLXPFHX>**

---

## 能做什么

| | |
|---|---|
| **多轮记忆** | 记得住上下文。告诉它"我叫阿豆"，隔几轮再问"我叫什么"，它答得出来 |
| **对话不丢** | 消息存在 SQLite 里，重启服务、刷新页面都在 |
| **会话列表** | 左下角「会话」，按最近活跃排序，随时切回几天前的对话 |
| **三种模型通道** | 内置免费 / 自己的 API（DeepSeek、硅基流动、OpenRouter、Groq、通义）/ 本地 Ollama |
| **流式输出** | 逐字吐出来，不用干等一整段 |
| **免登录免配置** | 打开就能用，密钥只保存在本机 |

---

## 30 秒跑起来

**Windows**：双击 `start-desktop.bat`

会弹出一个独立窗口，没有地址栏、没有标签页，就是一个普通的桌面应用。首次运行自动装环境（几分钟），之后秒开。

**其他系统**（跑网页版）：

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py
```

然后浏览器访问 <http://127.0.0.1:8000>。

> 需要 Python 3.10 或更高版本。没装的话去 [python.org](https://www.python.org/downloads/) 下载，安装时记得勾选 "Add Python to PATH"。

### 桌面版和网页版是同一个内核

| | 启动 | 界面 | 数据 |
|---|---|---|---|
| 桌面版 | `start-desktop.bat` | 独立窗口（WebView2） | 同一个 `chat.db` |
| 网页版 | `start.bat` | 浏览器标签页 | 同一个 `chat.db` |

桌面版只是把浏览器换成系统自带的 WebView2，后端和界面一行没改。

---

## 三种模型，随便挑

网页左下角那个头像按钮，点开就是模型设置。

### 内置免费（默认）

不用注册、不用填密钥，选中即可用。走第三方公共服务，模型 `gpt-oss-20b`。

代价是**约 4 次/分钟**的限速，而且它是别人提供的公共服务，不保证一直可用。适合试玩和演示。

### 自己的 API

填三样：接口地址、API Key、模型名。点「拉取」会自动取回该服务商真实可用的模型列表，不用手抄模型名。

内置了五个预设：

| 服务商 | 特点 |
|---|---|
| DeepSeek | 国内直连，便宜 |
| 硅基流动 | 国内，有免费模型 |
| OpenRouter | 带 `:free` 后缀的免费 |
| Groq | 速度快 |
| 通义千问 | 阿里云百炼，有免费额度 |

只要是 OpenAI 兼容接口，不在这五个里也能接。

### 本地 Ollama

装好 [Ollama](https://ollama.com/download) 后执行 `ollama pull qwen2.5:3b`，在设置里点「检测」，会列出本机已下载的模型。

完全免费、不限次数、不联网，全部跑在自己电脑上。

---

## 界面在哪操作

整个页面只有三个区域：

- **顶栏** — 左边是小黍和技术栈，右边「新会话」按钮
- **对话区** — AI 回复在左边带头像，你的消息在右边蓝色气泡；流式逐字输出
- **底部** — 输入框（`Enter` 发送，`Shift + Enter` 换行）和一个发送按钮

**左下角两个按钮**是关键：

- **会话** — 点开是历史对话列表，按最近活跃排序，点一条就切回去
- **头像** — 点开是模型设置，三条通道任选

---

## 技术栈

| 层 | 用了什么 |
|---|---|
| 对话编排 | LangGraph（StateGraph + 检查点） |
| 模型接入 | 自写的 provider 层，统一流式接口 |
| 后端 | FastAPI + SSE |
| 存储 | SQLite（`sqlite3` + `aiosqlite`，WAL 模式） |
| 桌面外壳 | pywebview + 系统自带 WebView2 |
| 前端 | 原生 HTML/CSS/JS，无框架无 CDN，可离线 |

对话图很简单，但骨架留好了扩展位：

```
START ──> trim_history ──> chatbot ──> END
            (修剪历史)      (调模型)
```

想加 RAG 就在中间插个检索节点，想加工具调用就在 `chatbot` 后面挂条件边。

---

## 项目结构

```
langgraph-chatbot/
├── main.py            FastAPI 路由：聊天、历史、会话列表、模型管理
├── graph.py           LangGraph 图 + SQLite 持久化
├── providers.py       三条模型通道的统一实现
├── config.py          提示词、历史长度、默认通道
├── desktop.py         桌面版启动器（WebView2 窗口）
├── run.py             网页版启动入口
├── start-desktop.bat  Windows 双击启动桌面版
├── start.bat          Windows 双击启动网页版
├── static/
│   ├── index.html     界面（含设置面板、会话列表）
│   ├── avatar.gif     小黍
│   └── avatar.png     favicon
├── Dockerfile         容器部署用
├── DEPLOY-ZEABUR.md   部署到 Zeabur 的完整步骤
└── requirements.txt
```

---

## 常见问题

| 现象 | 原因 |
|---|---|
| 提示「密钥无效」 | Key 填错或已失效，去服务商后台重新生成 |
| 提示「触发限流」 | 内置免费通道用太密，等几十秒或换通道 |
| 提示「连不上接口地址」 | `base_url` 写错，注意要带 `/v1` |
| 检测不到 Ollama | 没装或没启动，终端执行 `ollama serve` |
| 回复到一半断了 | 关页面会中断流，那一轮不会入库，重发一次即可 |
| 端口被占用 | `run.py` 里把 `port=8000` 改成 8001 |

---

## 许可

个人学习项目，随手用，不担保任何东西。
