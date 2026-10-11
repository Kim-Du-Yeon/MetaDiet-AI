FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    ENABLE_SCHEDULER=false

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app backend/ ./
COPY --chown=app:app docs/nutrition/ /docs/nutrition/
COPY --chown=app:app supabase/migrations/20261008233749_agent_proposals.sql ./migrations/20261008233749_agent_proposals.sql
RUN mkdir -p /app/artifacts && chown app:app /app/artifacts

USER app
EXPOSE 8080 8090
CMD ["python", "main.py"]
