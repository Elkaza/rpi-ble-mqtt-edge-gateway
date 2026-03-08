#!/bin/sh
set -eu
echo "[entrypoint] starting MQTT client subscriber..."
exec python3 /app/client.py
