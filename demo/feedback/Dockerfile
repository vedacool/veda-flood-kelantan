# VEDA public demo - feedback form. Standard library only: nothing is installed.
# Same pinned base image as VEDA's own Dockerfile.
FROM python:3.13-slim@sha256:57b29a7c050c4e679e4bea572e14b3965cf4b5839de2da49d55e49ffc4024f39

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FEEDBACK_FILE=/data/answers.jsonl FEEDBACK_PORT=8090
WORKDIR /srv
COPY feedback.py .
# /data is the volume with the answers; created here so the volume is owned by the app user
RUN useradd --create-home fb && mkdir -p /data && chown fb:fb /data
USER fb
EXPOSE 8090
HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8090/feedback/health', timeout=4).status == 200 else 1)"
CMD ["python", "feedback.py", "serve"]
