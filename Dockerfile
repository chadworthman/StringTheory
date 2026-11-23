# String Theory in one container: the light engine and the control page (port 8080).
#   docker compose up -d        (see compose.yaml and the README)
FROM python:3.12-slim
RUN pip install --no-cache-dir tinytuya
WORKDIR /app
COPY pi/lights.py pi/web.py pi/configure.py pi/tz_coords.json pi/index.html pi/help.html pi/logo.svg pi/manifest.webmanifest pi/icon*.png ./
COPY pi/fonts/ ./fonts/
COPY docker/start.sh /start.sh
# Your keys, strings and settings live in /data (a volume), never in the image.
ENV STRINGTHEORY_DATA=/data PORT=8080 PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8080
CMD ["/start.sh"]
