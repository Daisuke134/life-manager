FROM node:22.23.3-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip bash ca-certificates curl git jq util-linux passwd \
    libnss3 libatk-bridge2.0-0 libx11-xcb1 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libasound2 libgtk-3-0 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-runtime.txt /app/requirements-runtime.txt
RUN grep -E '^(jsonschema|playwright|cloakbrowser|Pillow|PyYAML|httpx|requests|websocket-client)==' requirements-runtime.txt > /tmp/maritime-requirements.txt \
    && python3 -m pip install --no-cache-dir --break-system-packages -r /tmp/maritime-requirements.txt \
    && rm /tmp/maritime-requirements.txt \
    && CLOAKBROWSER_CACHE_DIR=/opt/cloakbrowser python3 -c "from cloakbrowser.download import ensure_binary; from pathlib import Path; Path('/usr/local/bin/lm-cloud-chromium').symlink_to(ensure_binary())" \
    && chmod -R a+rX /opt/cloakbrowser \
    && npm install --global @openai/codex@0.160.0 \
    && npm cache clean --force
COPY . /app
RUN groupadd --gid 10001 lm-agent \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin lm-agent \
    && chmod -R a-w /app
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["node", "apps/life-manager/maritime/server.js"]
