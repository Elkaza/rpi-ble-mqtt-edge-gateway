# Development Guide

This document provides technical guidance for understanding, extending, and maintaining the BLE-to-MQTT Gateway project.

## Repository Organization

### Root Level Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | **Main orchestration file** - Defines all three services, networking, volumes, and environment variables. This is the primary configuration point. |
| `README.md` | User-facing documentation with setup, operation, and troubleshooting |
| `DEVELOPMENT.md` | This file - Developer/contributor guide |
| `.gitignore` | Git exclusion rules for logs, certs backups, temp files, etc. |

### Legacy/Utility Files (Can be removed)

- `gateway.py` - Root-level copy (duplicate of `ble/gateway.py`)
- `entrypoint.sh` - Root-level copy (not used)
- `Dockerfile.ble` - Legacy Dockerfile (superseded by `ble/Containerfile`)
- `gateway.py.bak.*` - Backup files (should be in `.gitignore`)
- `hw2_run.log` - Execution logs (should be in `.gitignore`)

**Recommendation**: Clean up these files to reduce clutter:
```bash
rm -f gateway.py entrypoint.sh Dockerfile.ble gateway.py.bak.* hw2_run.log
```

## Service Architecture Deep Dive

### 1. Mosquitto MQTT Broker

**Location**: `mosquitto/`

```
mosquitto/
├── Containerfile           # Multi-stage build
└── mosquitto.conf          # Configuration (TLS, auth, logging)
```

**Key Configuration** (`mosquitto.conf`):

```conf
listener 8883              # TLS-only port
protocol mqtt

cafile /certs/ca.crt       # Root CA for client verification
certfile /certs/mosquitto.crt
keyfile /certs/mosquitto.key

require_certificate true   # Force client certificates
use_identity_as_username true # Use certificate CN as username
```

**Container Behavior**:
- Listens on port 8883 (TLS, no plaintext)
- Requires valid client certificates signed by `certs/ca.crt`
- Username derived from certificate Common Name (CN)
- No persistence (messages cleared on disconnection)
- Full logging enabled (`log_type all`)

**Extending**:
- Add ACL file for fine-grained topic access control:
  ```
  acl_file /mosquitto/acl.txt
  ```
- Enable persistence:
  ```
  persistence true
  persistence_location /mosquitto/data
  ```
- Add password-based fallback auth:
  ```
  password_file /mosquitto/passwd.txt
  allow_anonymous false
  ```

### 2. BLE Gateway

**Location**: `ble/`

```
ble/
├── Containerfile           # Builds Python environment with Bleak and paho-mqtt
├── entrypoint.sh          # Wrapper that sources configs and runs gateway.py
└── gateway.py             # Main application logic
```

**Core Logic** (`gateway.py`):

```python
# 1. MQTT Setup
setup_mqtt()  # TLS connection with client certificate

# 2. BLE Device Discovery
device = find_device()  # Scan for target MAC, retries 10x

# 3. GATT Connection
async with BleakClient(device) as client:
    # Connect to Nordic UART Service (NUS)
    
# 4. Notification Handler
def handle_notify(_, data):
    payload = data.decode()        # T=23.40,H=39.90
    temp, hum = parse_payload(payload)
    publish_temp_hum(temp, hum)    # Publish to MQTT
```

**Environment Variables**:

```yaml
SENSOR_MAC=94:A9:90:1C:81:19    # Target device Bluetooth address
MQTT_HOST=localhost              # Broker host
MQTT_PORT=8883                   # Broker port (TLS)
TOPIC_BASE=io25m025              # MQTT topic namespace
FIRST_VALUE=temp                 # Expected first value in payload
```

**Expected Payload Format**: `T=<temperature>,H=<humidity>`

Example: `T=23.40,H=39.90`

**Error Handling**:
- Device not found: Retries up to 10 times with 1-second delay
- MQTT connection failed: Raises exception (container restarts via `restart: unless-stopped`)
- Garbled payload: Logs error, continues listening
- BLE disconnect: Attempts reconnect in outer loop

**Extending**:

Add support for additional sensors:
```python
# In gateway.py, modify find_device() to search by service instead of MAC
def find_device_by_service(service_uuid):
    # Scan and filter by advertised service
```

Add data validation:
```python
def validate_readings(temp, hum):
    assert -50 < float(temp) < 80      # Reasonable temperature range
    assert 0 <= float(hum) <= 100      # Humidity percentage
```

### 3. MQTT Client

**Location**: `client/`

```
client/
├── Containerfile           # Builds Python environment with paho-mqtt
├── entrypoint.sh          # Wrapper script
└── client.py              # Subscriber that displays received messages
```

**Core Logic** (`client.py`):

```python
# 1. MQTT Setup
c = mqtt.Client(client_id="client")
c.tls_set(ca_certs, certfile, keyfile)

# 2. Connection Handler
def on_connect(client, userdata, flags, rc):
    # Subscribe to topics on successful connection
    client.subscribe([
        (f"{base}/temperature", 0),
        (f"{base}/humidity", 0)
    ])

# 3. Message Handler
def on_message(client, userdata, msg):
    print(f"{msg.topic} -> {msg.payload.decode()}")

# 4. Blocking Loop
c.loop_forever()
```

**Purpose**: 
- Validates data flow end-to-end
- Demonstrates proper MQTT subscription pattern
- Can be replaced with actual data ingestion logic (database, time-series DB, API, etc.)

**Extending**:

Store data in InfluxDB:
```python
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

def on_message(client, userdata, msg):
    topic, value = msg.topic, msg.payload.decode()
    measurement = topic.split('/')[-1]  # 'temperature' or 'humidity'
    
    point = Point(measurement).field("value", float(value)).tag("source", "esp32")
    write_api.write(bucket="iot", record=point)
```

Store in PostgreSQL:
```python
import psycopg2

def on_message(client, userdata, msg):
    conn = psycopg2.connect("dbname=iot user=iot")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO readings (topic, value, timestamp) VALUES (%s, %s, NOW())",
        (msg.topic, msg.payload.decode())
    )
    conn.commit()
```

## Certificate Management

### Current Setup

Directory structure:
```
certs/
├── ca.crt                  # Root CA certificate (public)
├── ca.key                  # Root CA private key (SECURE!)
├── ca.srl                  # Certificate serial tracker
│
├── mosquitto.crt           # Broker certificate (signed by CA)
├── mosquitto.csr           # Broker certificate signing request
├── mosquitto.key           # Broker private key (SECURE!)
│
├── ble.crt, ble.csr, ble.key         # BLE gateway certificate
└── client.crt, client.csr, client.key # MQTT client certificate
```

### Generating Certificates (For Replacement)

**Create Root CA**:
```bash
openssl req -new -x509 -days 365 -nodes \
  -keyout ca.key -out ca.crt \
  -subj "/C=AT/ST=Vienna/L=Vienna/O=University/CN=mqtt-ca"
```

**Create Broker Certificate**:
```bash
# Generate private key
openssl genrsa -out mosquitto.key 2048

# Create signing request (must use FQDN or localhost for CN)
openssl req -new -key mosquitto.key -out mosquitto.csr \
  -subj "/C=AT/ST=Vienna/L=Vienna/O=University/CN=mosquitto"

# Sign with CA
openssl x509 -req -in mosquitto.csr \
  -CA ca.crt -CAkey ca.key -CAcreateserial -CAserial ca.srl \
  -out mosquitto.crt -days 365
```

**Create Client Certificates**:
```bash
# For BLE gateway
openssl genrsa -out ble.key 2048
openssl req -new -key ble.key -out ble.csr \
  -subj "/C=AT/ST=Vienna/L=Vienna/O=University/CN=ble"
openssl x509 -req -in ble.csr \
  -CA ca.crt -CAkey ca.key -CAserial ca.srl \
  -out ble.crt -days 365

# For MQTT client (duplicate process)
openssl genrsa -out client.key 2048
openssl req -new -key client.key -out client.csr \
  -subj "/C=AT/ST=Vienna/L=Vienna/O=University/CN=client"
openssl x509 -req -in client.csr \
  -CA ca.crt -CAkey ca.key -CAserial ca.srl \
  -out client.crt -days 365
```

**Security Best Practices**:
- Keep `ca.key` and `*.key` files with restrictive permissions (600)
- Never commit private keys to version control
- Rotate certificates at least annually
- Store CA key separately from runtime certificates
- Use certificate expiration alerts/automation

## Building and Testing

### Build Images

```bash
# Build all services
podman-compose build

# Build specific service
podman-compose build mosquitto
podman-compose build ble
podman-compose build client
```

### Run Services

```bash
# Foreground (view all logs)
podman-compose up

# Background
podman-compose up -d

# Rebuild and start
podman-compose up --build
```

### View Logs

```bash
# All services
podman-compose logs -f

# Tail last 50 lines
podman-compose logs -f --tail=50

# Follow specific service
podman-compose logs -f mosquitto
podman-compose logs -f ble
podman-compose logs -f client

# Filter by keyword
podman-compose logs | grep "ERROR\|WARNING"
```

### Stop and Cleanup

```bash
# Stop services (keep data)
podman-compose stop

# Stop and remove containers
podman-compose down

# Remove images too
podman-compose down --rmi all

# Full cleanup (including volumes)
podman-compose down -v
```

## Troubleshooting Development Issues

### BLE Device Not Detected

```bash
# Check BlueZ status
sudo systemctl status bluetooth

# Scan for devices
hcitool scan
# OR
bluetoothctl
> scan on
> devices
```

### D-Bus Socket Error

```
dbus.exceptions.DBusException: g-io-error-quark: 
GDBus.Error:org.freedesktop.DBus.Error.AccessDenied
```

**Solution**: Ensure D-Bus socket is accessible:
```bash
ls -la /var/run/dbus/system_bus_socket
sudo chmod 666 /var/run/dbus/system_bus_socket  # Temporary
# OR add your user to group (permanent)
sudo usermod -a -G message-bus $(whoami)
```

### Certificate or TLS Errors

```
ssl.SSLError: [SSL: CERTIFICATE_VERIFY_FAILED] 
```

**Verify certificates**:
```bash
# Check cert validity
openssl x509 -in certs/ble.crt -text -noout

# Verify client cert was signed by CA
openssl verify -CAfile certs/ca.crt certs/ble.crt

# Test TLS connection to Mosquitto
openssl s_client -connect localhost:8883 \
  -cert certs/ble.crt -key certs/ble.key \
  -CAfile certs/ca.crt
```

### Container Resource Issues

Monitor resource usage:
```bash
podman stats
```

If running out of memory/disk:
```bash
# Clean up unused images/containers
podman image prune
podman container prune
podman system prune
```

## Code Style and Quality

### Python Standards

- PEP 8: Follow standard Python conventions
- Type hints: Use for clarity (optional but recommended)
- Docstrings: Add for functions and classes
- Error handling: Use specific exceptions, not bare `except:`

**Example**:
```python
def parse_payload(payload: str) -> tuple[str, str]:
    """Parse temperature,humidity payload.
    
    Args:
        payload: String format "T=<temp>,H=<hum>"
        
    Returns:
        Tuple of (temperature, humidity) as strings
        
    Raises:
        ValueError: If payload format is invalid
    """
    if not payload.startswith("T="):
        raise ValueError(f"Invalid payload: {payload}")
    # ... parse logic
```

### Testing

Create tests in `tests/` (create directory if needed):

```python
# tests/test_gateway.py
import pytest
from ble.gateway import parse_payload

def test_parse_valid_payload():
    temp, hum = parse_payload("T=23.40,H=39.90")
    assert temp == "23.40"
    assert hum == "39.90"

def test_parse_invalid_format():
    with pytest.raises(ValueError):
        parse_payload("INVALID")
```

Run tests:
```bash
podman-compose run --rm ble python -m pytest tests/
```

## Performance Considerations

### Data Latency

Current implementation:
- BLE notification → parsing: < 1 ms
- MQTT publish: 10-50 ms (depends on broker load)
- Network transport: 1-5 ms (localhost)
- **Total**: ~50-100 ms latency

For time-critical applications, consider:
- Message queueing (enable Mosquitto persistence)
- Batch processing (aggregate readings)
- Database indexing optimization

### Throughput

Current throughput limitation:
- BLE: Limited by notification rate (typically 1-10 readings/second)
- MQTT: Can handle 1000s of messages/second
- System is **BLE-bottlenecked**, not MQTT

To increase throughput:
- Add more BLE sensors (multiple gateways)
- Decrease BLE notification interval on sensor
- Batch multiple readings before MQTT publish

### Memory Usage

Per-service baseline:
- Mosquitto: ~20 MB
- BLE Gateway: ~80 MB (Python + Bleak)
- MQTT Client: ~70 MB (Python)
- **Total**: ~170 MB

For Raspberry Pi with limited memory:
- Use Python Alpine image instead: `python:3.11-alpine`
- Remove unused packages from Containerfile

## Continuous Integration / Deployment

For GitHub Actions, create `.github/workflows/ci.yml`:

```yaml
name: Build and Test

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Build with Podman
        run: podman-compose build
      - name: Run tests
        run: podman-compose run --rm ble python -m pytest tests/
```

## References

- **Bleak**: https://bleak.readthedocs.io/
- **Paho MQTT**: https://github.com/eclipse/paho.mqtt.python
- **Mosquitto**: https://mosquitto.org/
- **Podman**: https://podman.io/
- **OpenSSL**: https://www.openssl.org/
