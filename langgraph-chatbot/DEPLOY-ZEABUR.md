# 部署到 Zeabur（固定域名 + 电脑不用常开）

代码已经准备好：`Dockerfile`、`.dockerignore`、`.gitignore` 都在，数据库路径可通过 `DB_PATH` 环境变量指定。
你只需要做下面几步，全程免费、不需要信用卡。

---

## 先准备两个账号

| 账号 | 用途 | 费用 |
|---|---|---|
| GitHub | 存放代码，Zeabur 从仓库拉取 | 免费 |
| Zeabur | 托管运行 | 免费层 $5/月额度，无需信用卡 |

---

## 第 1 步：把代码推到 GitHub

1. 打开 <https://github.com/new>
2. 仓库名填 `langgraph-chatbot`
3. **Private 或 Public 都行**（Private 也能部署）
4. 下面三个勾选项（README / .gitignore / license）**全部不要勾**
5. 点 Create repository，复制页面上给的仓库地址

然后在本目录（`langgraph-chatbot`）执行：

```bash
git remote add origin https://github.com/你的用户名/langgraph-chatbot.git
git push -u origin main
```

> 第一次 push 会弹浏览器让你登录 GitHub 授权，按提示走完即可。

---

## 第 2 步：Zeabur 建项目

1. 打开 <https://zeabur.com>，用 GitHub 账号登录
2. **Create Project**，区域选 **香港 / 东京 / 新加坡**（这三个在免费区）
3. 进项目后点 **Add Service → GitHub**
4. 授权后选中 `langgraph-chatbot` 仓库，点 Deploy
5. Zeabur 会优先用 `Dockerfile` 构建，没有就用自动识别，都会走到 `python run.py`
6. 等 2–5 分钟构建完成

---

## 第 3 步：挂载持久化存储（这步不做，对话重启就丢）

1. 点进这个服务，切到 **Volumes** 标签
2. 点 **Mount Volumes**
3. **Volume ID** 填：`data`
4. **Mount Directory** 填：`/data`
5. 保存并重启服务

---

## 第 4 步：加环境变量

服务页 → **Variables**，添加一条：

| Key | Value |
|---|---|
| `DB_PATH` | `/data/chat.db` |

**不要设 `PORT`**，Zeabur 会自动注入，代码已经会读。

想换人设可以再加 `SYSTEM_PROMPT`；想接自己的模型再加 `DEEPSEEK_API_KEY`（不填就走内置免费通道）。

---

## 第 5 步：生成域名

服务页 → **Networking / Domains** → **Generate Domain**

- 会得到一个 `随机名.zeabur.app`
- 可以自定义前缀，比如填 `xiaoshu` → **`xiaoshu.zeabur.app`**

HTTPS 证书自动配好，不用管。

---

## 怎么算成功

访问你的新域名：

1. 页面正常打开，能看到小黍头像
2. 问一句「你是谁」，回复「我是小黍」
3. 刷新页面，左下角「会话」按钮里有刚才那轮对话

第 3 条最重要——它同时验证了**数据库挂载成功**。如果不挂 Volume，刷新还能看到（同一次容器内），但服务重启后就没了。

---

## 可能遇到的问题

| 现象 | 原因与处理 |
|---|---|
| 构建失败 | 看 Build Logs。若是 Dockerfile 报错，删掉 `Dockerfile` 重新部署，让 Zeabur 自动识别 Python |
| 启动失败 / 502 | 看 Runtime Logs，确认端口是 Zeabur 注入的（代码已处理） |
| 数据还是会丢 | Volume 没挂上，或 `DB_PATH` 没设成 `/data/chat.db`，两者必须同时满足 |
| 第一次访问很慢 | 免费层闲置会休眠，冷启动几秒，正常 |
| 额度用完了 | 每月 $5，1 vCPU / 2GB 大约能跑 20 天左右；不够就升级 Dev $5/月，或者闲置时手动暂停服务 |

---

## 关于额度的一个提醒

免费层的 $5/月是按实际运行时长和资源算的。一个 1 vCPU / 2GB 的服务**跑满一个月会超出** $5，
实际大概能用 20 天左右。Volume 也按容量计费，几个 MB 的 SQLite 几乎可以忽略。

如果只是自己偶尔用，最省的做法是：**不用的时候在 Zeabur 控制台把服务暂停**，用的时候再开。

---

## 本地和云端的关系

两条腿各走各的，数据互不影响：

- 本地：`127.0.0.1:8000`，数据在 `chat.db`
- 云端：`xiaoshu.zeabur.app`，数据在 Volume 的 `/data/chat.db`

改了代码要同步：`git add . && git commit -m "..." && git push`，Zeabur 会自动重新部署。

原来那个 `workbuddy.host` 的链接可以留着，也可以让我帮你下线。
