FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN groupadd --gid 10001 manager \
    && useradd --uid 10001 --gid manager --no-create-home --home-dir /nonexistent \
       --shell /usr/sbin/nologin manager

COPY --chown=0:0 manager_core/ ./manager_core/
COPY --chown=0:0 scripts/phase06_kernel_release.py scripts/phase06_release_guard.py \
     scripts/run_owned_digital_cycle.py scripts/owned_runtime_entrypoint.py ./scripts/
COPY --chown=0:0 public_goods/service/catalog.json ./public_goods/service/catalog.json

RUN chmod -R a=rX /app

# Railway mounts the dedicated persistent volume at /data/manager. The short
# root entrypoint verifies that exact mount, fixes only its root directory
# ownership, and execs the bounded worker as UID/GID 10001.
USER 0:0
ENTRYPOINT ["python3", "/app/scripts/owned_runtime_entrypoint.py"]
