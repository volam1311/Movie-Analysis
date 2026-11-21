FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so code changes don't invalidate this layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ src/
COPY movie_dbt/ movie_dbt/
COPY scripts/ scripts/

# Run as a non-root user. data/ and logs/ are where the pipeline writes.
RUN useradd --create-home --uid 1000 pipeline \
    && mkdir -p data logs \
    && chown -R pipeline:pipeline /app
USER pipeline

# Secrets (READACCESS_TOKEN, DATABRICKS_*) are passed at run time with -e or
# --env-file. They are never baked into the image.
CMD ["bash", "scripts/run_pipeline.sh"]
