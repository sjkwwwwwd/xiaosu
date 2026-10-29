"""小黍 · 桌面版启动器。

做的事很简单：
  1. 在本机随机挑一个固定端口起 FastAPI（只绑 127.0.0.1，外部访问不到）
  2. 等它真正能响应了，再用系统 WebView2 打开一个独立窗口

用户看到的就是一个普通桌面应用窗口，没有地址栏、不用开浏览器。

为什么端口要固定：localStorage 按「协议+域名+端口」隔离，
端口一变，浏览器的模型设置和会话 ID 就都读不到了。
所以优先用 8731，被占用才往后挪。
"""

from __future__ import annotations

import argparse
import ctypes
import socket
import sys
import threading
import time
import urllib.request

import uvicorn

APP_TITLE = "小黍"
PREFERRED_PORTS = range(8731, 8751)
WINDOW_SIZE = (1020, 740)
MIN_SIZE = (760, 560)


def pick_port() -> int:
    """优先用 8731 这类固定端口，被占用才往后找。"""
    for port in PREFERRED_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    # 全都占用就交给系统随机分配
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_ready(port: int, timeout: float = 40.0) -> bool:
    """轮询 /api/health，确认服务真的起来了。"""
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def fatal(message: str) -> None:
    """出错时弹一个系统对话框，而不是让窗口一闪而过。"""
    print(message, file=sys.stderr)
    try:
        ctypes.windll.user32.MessageBoxW(None, message, f"{APP_TITLE} 启动失败", 0x10)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true", help="启动后 6 秒自动关闭，用于验证")
    args = parser.parse_args()

    try:
        import webview
    except ImportError:
        fatal(
            "缺少桌面组件 pywebview。\n\n"
            "请在项目目录执行：\n"
            ".venv\\Scripts\\python.exe -m pip install -r requirements-desktop.txt"
        )
        return 1

    port = pick_port()
    config = uvicorn.Config(
        "main:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    if not wait_ready(port):
        fatal(
            "后端服务没有在预期时间内启动。\n\n"
            "请把下面的信息反馈给开发者：\n"
            f"端口 {port} 无响应\n\n"
            "可在项目目录执行以下命令查看详细报错：\n"
            f".venv\\Scripts\\python.exe -m uvicorn main:app --port {port}"
        )
        return 1

    window = webview.create_window(
        APP_TITLE,
        f"http://127.0.0.1:{port}",
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=MIN_SIZE,
        text_select=True,
    )

    if args.selftest:
        threading.Timer(6.0, window.destroy).start()

    webview.start()
    server.should_exit = True
    return 0


if __name__ == "__main__":
    sys.exit(main())
