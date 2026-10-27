# VEDA - one container: the API + web page (B-19). Python 3.13 everywhere (decided 22 Oct night).
#   docker build -t veda .
#   docker run --rm -p 8000:8000 -e SAMPLE_MODE=true veda          # judges: offline, no .env, no keys
#   docker run --rm -p 127.0.0.1:8000:8000 --env-file .env veda    # live: keys inside - this computer only
#                                                                   #   (use host.docker.internal in the URLs)
# Base image pinned by digest (supply chain: a tag can move, a digest cannot).
FROM python:3.13-slim@sha256:57b29a7c050c4e679e4bea572e14b3965cf4b5839de2da49d55e49ffc4024f39

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 VEDA_HOST=0.0.0.0 VEDA_PORT=8000
WORKDIR /app

COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt

# Code, the recorded data (SAMPLE_MODE fixtures, curated CSVs, replay anchors) and the eval scenarios.
# Never the .env, the logs or the on-disk World Model (see .dockerignore).
COPY app ./app
COPY data ./data
COPY run.py ./
COPY scripts/run_evals.py ./scripts/
COPY tests/evals ./tests/evals

RUN useradd --create-home veda && mkdir -p logs data/world && chown -R veda:veda /app
USER veda

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=15s --start-period=10s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=10).status == 200 else 1)"
CMD ["python", "-m", "app.main"]
