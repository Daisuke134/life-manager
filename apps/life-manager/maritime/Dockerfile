FROM node:22.23.3-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip bash ca-certificates curl git jq \
    libnss3 libatk-bridge2.0-0 libx11-xcb1 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libasound2 libgtk-3-0 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-runtime.txt /app/requirements-runtime.txt
RUN grep -E '^(jsonschema|playwright|cloakbrowser|Pillow|PyYAML|httpx|requests|websocket-client)==' requirements-runtime.txt > /tmp/maritime-requirements.txt \
    && python3 -m pip install --no-cache-dir --break-system-packages -r /tmp/maritime-requirements.txt \
    && rm /tmp/maritime-requirements.txt \
    && npm install --global @openai/codex@0.160.0 \
    && npm cache clean --force
COPY . /app
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["node", "apps/life-manager/maritime/server.js"]
