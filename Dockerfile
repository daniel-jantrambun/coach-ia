# 1. Interface web (Vite)
FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# 2. API Python, qui sert aussi le build du front
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY --from=web /web/dist ./web/dist

ENV COACH_DATA_DIR=/data COACH_WEB_DIR=/app/web/dist
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "coach.api:app", "--host", "0.0.0.0", "--port", "8000"]
