# The speaker service image, used by both setups:
#   compose.yaml           Mac / home LAN (transport "cast": talks to the speaker directly)
#   deploy/vm/compose.yaml remote VM (transport "mqtt": through the ESP32 relay, with Mosquitto and cloudflared)
# Build context is the repository root; .dockerignore lets in only what the service needs.
FROM python:3.13-slim

# yt-dlp needs a JavaScript runtime for YouTube's challenges (server/media.py asks for node);
# live talk transcodes the browser's microphone with ffmpeg.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server ./server
COPY static ./static


# config.json, the database and the YouTube cache live on the volume. /backups is for the backup service:
# a new named volume copies this owner and mode, so backups are written owner-only with no host setup.
ENV CONFIG_PATH=/data/config.json DATA_PATH=/data/data.db CACHE_DIR=/data/cache BACKUP_DIR=/backups
RUN useradd --system --uid 10001 speaker && mkdir -p /data /backups && chown speaker /data /backups \
    && chmod 0700 /backups
USER speaker
VOLUME /data
EXPOSE 8090
CMD ["python", "-m", "server"]
