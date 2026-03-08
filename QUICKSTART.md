# QUICKSTART.md

Minimal setup and run instructions to get the BLE-to-MQTT gateway running.

## 30-Second Setup

```bash
git clone <repository-url>
cd hw2_gateway

# Edit configuration (set your ESP32 MAC address)
# In docker-compose.yml, update: SENSOR_MAC=94:A9:90:1C:81:19

# Start gateway
podman-compose up -d

# View live logs
podman-compose logs -f
```

## Requirements

- Raspberry Pi 5 (or ARM64 Linux)
- Podman + Podman Compose: `sudo apt install podman podman-compose bluez`
- D-Bus enabled: `sudo systemctl start dbus`
- Powered ESP32 DHT22 sensor advertising BLE

## Configuration

Edit `docker-compose.yml` and adjust these environment variables:

| Variable | Location | Default | Set To |
|----------|----------|---------|--------|
| `SENSOR_MAC` | `ble.environment` | `94:A9:90:1C:81:19` | Your ESP32 MAC address |
| `TOPIC_BASE` | `ble.environment` + `client.environment` | `io25m025` | Custom namespace (optional) |

## Run Commands

```bash
# Start all services
podman-compose up -d

# View logs
podman-compose logs -f

# Watch only BLE gateway
podman-compose logs -f ble

# Watch only client (received data)
podman-compose logs -f client

# Stop services
podman-compose down
```

## Verify It Works

1. **Service startup** (watch logs 5-10 seconds):
   ```
   mosquitto: Opening listen socket on port 8883
   ble: connecting to localhost:8883
   client: connected OK, subscribing
   ```

2. **Data flowing** (watch client logs for values):
   ```
   [client] io25m025/temperature -> 23.40
   [client] io25m025/humidity -> 39.90
   ```

If you don't see data, check:
- ESP32 sensor is powered on
- MAC address in `docker-compose.yml` is correct
- Run `hcitool scan` to verify device is visible on Raspberry Pi

## Troubleshooting

| Problem | Check |
|---------|-------|
| `BLE device not found` | MAC address, sensor power, `hcitool scan` |
| `MQTT connection refused` | Port 8883 accessible, certificates in `certs/` |
| `No data received` | Sensor is transmitting, check `docker-compose.yml` TOPIC_BASE |
| `Permission denied (dbus socket)` | Run: `sudo systemctl start dbus` |

For more details, see [README.md](README.md) or [DEVELOPMENT.md](DEVELOPMENT.md).
