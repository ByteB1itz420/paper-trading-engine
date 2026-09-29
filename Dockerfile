FROM node:22-alpine AS frontend
WORKDIR /build
COPY apps/frontend/package*.json ./
RUN npm ci
COPY apps/frontend ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY apps ./apps
COPY --from=frontend /build/dist ./apps/frontend/dist
EXPOSE 8000
CMD ["sh", "-c", "uvicorn apps.backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
