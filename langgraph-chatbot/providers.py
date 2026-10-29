"""模型通道层：把「内置免费 / 自定义 OpenAI 兼容 / 本地 Ollama」抽象成同一套流式接口。

三条通道的差别只在「请求怎么发、响应怎么解析」，上层拿到的一律是纯文本 token。

实测结论（2026-10-29）：
  - 免费通道 text.pollinations.ai 匿名 POST 可用，支持 system + 多轮 + 流式，
    模型是 gpt-oss-20b，限速约 4 次/分钟，且官方已标记 legacy，属于尽力而为。
  - 自定义通道覆盖 DeepSeek / 硅基流动 / OpenRouter / Groq / 通义，均为 OpenAI 兼容。
  - Ollama 走 /api/chat 的 NDJSON 流。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx

# 内置免费通道：匿名可用，不需要任何 key
FREE_URL = "https://text.pollinations.ai/"
FREE_MODEL_LABEL = "gpt-oss-20b（内置免费）"

TIMEOUT = httpx.Timeout(120.0, connect=15.0, read=120.0)


class ProviderError(Exception):
    """带用户可读中文说明的通道异常。"""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class ProviderConfig:
    kind: str = "free"          # free | openai | ollama
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.7

    @property
    def label(self) -> str:
        if self.kind == "free":
            return FREE_MODEL_LABEL
        if self.kind == "ollama":
            return f"{self.model}（Ollama）"
        return self.model or "自定义模型"


# --------------------------------------------------------------------------
# 预设：只收录我实测能连通的服务商，模型名交给 /api/models 动态拉取
# --------------------------------------------------------------------------
PRESETS: list[dict[str, Any]] = [
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "hint": "国内直连，便宜，注册送额度",
        "key_url": "https://platform.deepseek.com/api_keys",
    },
    {
        "id": "siliconflow",
        "label": "硅基流动",
        "base_url": "https://api.siliconflow.cn/v1",
        "hint": "国内，有多个免费模型",
        "key_url": "https://cloud.siliconflow.cn/account/ak",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "hint": "带 :free 后缀的模型免费",
        "key_url": "https://openrouter.ai/keys",
    },
    {
        "id": "groq",
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "hint": "速度快，有免费额度",
        "key_url": "https://console.groq.com/keys",
    },
    {
        "id": "dashscope",
        "label": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "hint": "阿里云百炼，新用户有免费额度",
        "key_url": "https://bailian.console.aliyun.com/",
    },
]


# --------------------------------------------------------------------------
# 公共工具
# --------------------------------------------------------------------------
def _is_local(url: str) -> bool:
    """判断是不是本机地址。

    本机请求必须绕开系统代理，否则 HTTP_PROXY 会把 127.0.0.1 也拦下来，
    报出一堆莫名其妙的 502。
    """
    try:
        host = httpx.URL(url).host
    except Exception:
        return False
    return host in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def _explain_status(status: int, raw: str) -> str:
    """把 HTTP 状态码翻译成用户能看懂的话。"""
    snippet = (raw or "").strip().replace("\n", " ")[:180]
    mapping = {
        400: "请求格式有问题",
        401: "密钥无效，请检查 API Key",
        402: "账户余额不足",
        403: "没有权限访问该模型（或密钥被限制）",
        404: "接口地址或模型名不对",
        429: "请求过于频繁，触发了限流",
        500: "服务端内部错误",
        502: "网关错误，上游服务不可用",
        503: "服务暂时不可用",
    }
    base = mapping.get(status, f"请求失败（HTTP {status}）")
    return f"{base}：{snippet}" if snippet else base


def _parse_sse_line(line: str) -> str | None:
    """解析一行 OpenAI 风格的 SSE，返回增量文本。"""
    line = line.strip()
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if not data or data == "[DONE]":
        return None
    try:
        chunk = json.loads(data)
    except json.JSONDecodeError:
        return None

    choices = chunk.get("choices") or []
    if not choices:
        return None
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    return content if isinstance(content, str) and content else None


# --------------------------------------------------------------------------
# 通道实现
# --------------------------------------------------------------------------
async def _stream_openai_like(
    client: httpx.AsyncClient,
    url: str,
    payload: dict,
    headers: dict[str, str],
    params: dict[str, str] | None = None,
) -> AsyncIterator[str]:
    """OpenAI 兼容流式：自定义 API 和内置免费通道共用。"""
    try:
        async with client.stream(
            "POST", url, json=payload, headers=headers, params=params
        ) as resp:
            if resp.status_code >= 400:
                raw = (await resp.aread()).decode("utf-8", "ignore")
                raise ProviderError(_explain_status(resp.status_code, raw), resp.status_code)

            ctype = resp.headers.get("content-type", "")

            # 少数情况下服务端忽略 stream 参数，直接回整段文本/JSON
            if "event-stream" not in ctype and "json" not in ctype:
                async for chunk in resp.aiter_text():
                    if chunk:
                        yield chunk
                return

            async for line in resp.aiter_lines():
                text = _parse_sse_line(line)
                if text:
                    yield text

    except httpx.ConnectError as exc:
        raise ProviderError(f"连不上接口地址，请检查 base_url 或网络：{exc}") from exc
    except httpx.ReadTimeout as exc:
        raise ProviderError("等待响应超时，模型可能太慢或网络不稳定") from exc


async def _stream_ollama(
    client: httpx.AsyncClient, cfg: ProviderConfig, messages: list[dict]
) -> AsyncIterator[str]:
    """Ollama 的 /api/chat 返回 NDJSON，一行一个 JSON。"""
    base = (cfg.base_url or "http://127.0.0.1:11434").rstrip("/")
    payload = {
        "model": cfg.model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": cfg.temperature},
    }
    try:
        async with client.stream("POST", f"{base}/api/chat", json=payload) as resp:
            if resp.status_code >= 400:
                raw = (await resp.aread()).decode("utf-8", "ignore")
                if resp.status_code == 404:
                    raise ProviderError(
                        f"本机没有这个模型（{cfg.model}），先执行：ollama pull {cfg.model}"
                    )
                raise ProviderError(_explain_status(resp.status_code, raw), resp.status_code)

            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("error"):
                    raise ProviderError(str(obj["error"]))
                piece = (obj.get("message") or {}).get("content")
                if piece:
                    yield piece
                if obj.get("done"):
                    break

    except httpx.ConnectError as exc:
        raise ProviderError(
            "连不上本地 Ollama。确认已安装并启动（终端执行 ollama serve），"
            f"默认地址 http://127.0.0.1:11434。详情：{exc}"
        ) from exc
    except httpx.ReadTimeout as exc:
        raise ProviderError("Ollama 响应超时，模型可能正在加载，稍等重试") from exc


async def stream_chat(cfg: ProviderConfig, messages: list[dict]) -> AsyncIterator[str]:
    """统一入口：给什么通道就走什么通道，一律吐文本 token。"""
    target = cfg.base_url or ""
    trust_env = not (_is_local(target) or cfg.kind == "ollama")
    async with httpx.AsyncClient(
        timeout=TIMEOUT, follow_redirects=True, trust_env=trust_env
    ) as client:
        if cfg.kind == "free":
            # 注意：匿名通道不要传 model / temperature，会被拒
            payload = {"messages": messages, "stream": True}
            gen = _stream_openai_like(client, FREE_URL, payload, {}, {"stream": "true"})
            got = False
            async for token in gen:
                got = True
                yield token
            if not got:
                raise ProviderError(
                    "内置免费通道没有返回内容，可能触发了限流（约 4 次/分钟）。"
                    "等一会儿再试，或在设置里换成自己的 API。"
                )
            return

        if cfg.kind == "ollama":
            async for token in _stream_ollama(client, cfg, messages):
                yield token
            return

        # 自定义 OpenAI 兼容
        if not cfg.base_url:
            raise ProviderError("还没填接口地址（base_url）")
        if not cfg.model:
            raise ProviderError("还没填模型名")
        if not cfg.api_key:
            raise ProviderError("还没填 API Key")

        url = cfg.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": cfg.model,
            "messages": messages,
            "stream": True,
            "temperature": cfg.temperature,
        }
        async for token in _stream_openai_like(client, url, payload, headers):
            yield token


async def list_models(base_url: str, api_key: str) -> list[str]:
    """动态拉取服务商的模型列表，避免预设里写死过时的模型名。"""
    base_url = (base_url or "").rstrip("/")
    if not base_url:
        raise ProviderError("还没填接口地址")

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=10.0), trust_env=not _is_local(base_url)
    ) as client:
        try:
            resp = await client.get(f"{base_url}/models", headers=headers)
        except httpx.ConnectError as exc:
            raise ProviderError(f"连不上 {base_url}：{exc}") from exc

        if resp.status_code >= 400:
            raise ProviderError(_explain_status(resp.status_code, resp.text), resp.status_code)

        try:
            data = resp.json()
        except Exception as exc:
            raise ProviderError("接口返回的不是合法 JSON，确认 base_url 是否正确") from exc

        items = data.get("data") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []
        return sorted(
            {i.get("id") for i in items if isinstance(i, dict) and i.get("id")}
        )


async def list_ollama_models(base_url: str = "http://127.0.0.1:11434") -> list[str]:
    """列出本机 Ollama 已下载的模型。"""
    base = (base_url or "http://127.0.0.1:11434").rstrip("/")
    # trust_env=False：本机请求不能走系统代理
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(6.0, connect=3.0), trust_env=False
    ) as client:
        try:
            resp = await client.get(f"{base}/api/tags")
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise ProviderError(
                "没有检测到 Ollama 服务。先安装并启动：终端执行 ollama serve"
            ) from exc
        if resp.status_code >= 400:
            raise ProviderError(
                f"Ollama 返回异常（HTTP {resp.status_code}），确认地址是否写对"
            )
        data = resp.json()
        return [m["name"] for m in data.get("models", []) if m.get("name")]
