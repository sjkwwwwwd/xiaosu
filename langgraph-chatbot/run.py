"""启动入口。

本地运行：`python run.py`，会自动打开浏览器。
云端部署：平台会注入 PORT 环境变量，此时监听 0.0.0.0 且不弹浏览器。
"""

import os
import threading
import webbrowser

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    deployed = bool(os.getenv("PORT"))
    host = "0.0.0.0" if deployed else "127.0.0.1"

    if not deployed:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
        print(f"\n  小黍启动中 -> http://127.0.0.1:{port}\n  按 Ctrl+C 停止\n")

    uvicorn.run("main:app", host=host, port=port, reload=False, log_level="info")
