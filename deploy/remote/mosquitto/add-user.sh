#!/bin/sh
# Add or change a broker login: sh deploy/remote/mosquitto/add-user.sh <username>
# Prompts for the password (nothing ends up in shell history) and writes deploy/remote/mosquitto/passwd,
# owned by the container's mosquitto user. Restart the broker afterwards:
#   docker compose -f deploy/remote/docker-compose.yml restart mosquitto
set -e
[ -n "$1" ] || { echo "usage: $0 <username>"; exit 1; }
DIR=$(cd "$(dirname "$0")" && pwd)
IMAGE=eclipse-mosquitto:2.1.2-alpine
CREATE=""
[ -f "$DIR/passwd" ] || CREATE="-c"
docker run --rm -it -v "$DIR:/m" "$IMAGE" sh -c \
  "mosquitto_passwd $CREATE /m/passwd '$1' && chown 1883:1883 /m/passwd && chmod 0600 /m/passwd"
echo "Saved $1 to $DIR/passwd"
