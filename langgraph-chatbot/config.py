"""集中管理配置：提示词、历史长度、默认通道。

对齐课程第 47~53 集（模型调用 / 消息类型 / 系统提示词设计原则）。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

import providers

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# 对话持久化：SQLite 文件，默认落在项目目录
DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "chat.db"))


# ---------- 对话配置 ----------
# 系统提示词：角色 + 边界 + 风格（第 51 集的原则）
SYSTEM_PROMPT: str = os.getenv(
    "SYSTEM_PROMPT",
    "你叫小黍，是一个中文聊天助手。被问到名字时就说自己叫小黍。"
    "回答简洁、准确、自然。不确定的事情要说明不确定，不要编造事实。"
    "回答默认控制在 3 段以内，除非用户明确要求展开。",
)

# 最多保留多少条历史消息（第 62 集「历史消息自动修剪」）
MAX_HISTORY_MESSAGES: int = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))

# ---------- 默认通道 ----------
# 浏览器没带配置时用这里的默认值：
#   .env 里填了 DEEPSEEK_API_KEY -> 自动用 DeepSeek
#   没填                          -> 走内置免费通道，开箱即用
def default_provider() -> providers.ProviderConfig:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if key:
        return providers.ProviderConfig(
            kind="openai",
            base_url=os.getenv("MODEL_BASE_URL", "https://api.deepseek.com/v1"),
            api_key=key,
            model=os.getenv("MODEL_NAME", "deepseek-chat"),
            temperature=float(os.getenv("TEMPERATURE", "0.7")),
        )
    return providers.ProviderConfig(kind="free", temperature=0.7)
