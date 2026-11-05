# SIKADIN — image produksi (frontend dibangun lalu disajikan oleh FastAPI). Belum diuji di Docker pada mesin pengembang.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 SIKADIN_ENV=production SIKADIN_DB=/data/sikadin.db SIKADIN_DIST=/app/dist
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=web /web/dist ./dist
RUN useradd -m sikadin && mkdir -p /data && chown sikadin /data
USER sikadin
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
# Satu proses saja: sesi login disimpan di memori proses.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
