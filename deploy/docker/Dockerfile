# 多阶段构建: 前端构建产物由 Nginx 容器托管, 后端双镜像 (api / worker)
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /srv/app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ backend/

# ---- API 镜像入口 ----
FROM base AS api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

# ---- Worker 镜像入口 ----
FROM base AS worker
CMD ["python", "-m", "app.worker"]
