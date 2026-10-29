FROM python:3.12-slim

# 不在容器里写 .pyc，日志实时输出
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# 先装依赖，利用镜像层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# run.py 会读 PORT 并绑定 0.0.0.0
CMD ["python", "run.py"]
