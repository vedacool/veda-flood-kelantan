# VEDA public demo - the proxy: pinned nginx with demo/nginx.conf built in (no files mounted from the host).
FROM nginx:1.27.5-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10
COPY nginx.conf /etc/nginx/nginx.conf
COPY demo-banner.js /etc/nginx/demo/demo-banner.js
