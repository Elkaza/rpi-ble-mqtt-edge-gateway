#!/bin/sh
set -e
echo "[entrypoint] starting BLE->MQTT gateway..."
exec python3 /app/gateway.py
