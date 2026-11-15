# syntax=docker/dockerfile:1
# Backend image (FastAPI + Alembic). Multi-arch base: works on Intel/AMD and Apple Silicon.

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/app ./app
COPY ml/coldchain_ml ./ml/coldchain_ml
COPY ml/registry ./ml/registry
ENV PYTHONPATH=/app/ml

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]


# Test image: runtime + test dependencies + tests. Used by `docker compose --profile test`.
FROM runtime AS test
USER root
COPY backend/requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
COPY backend/pyproject.toml ./
COPY backend/tests ./tests
USER appuser
CMD ["pytest", "-v", "-p", "no:cacheprovider"]
