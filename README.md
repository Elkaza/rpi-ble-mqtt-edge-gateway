# BLE-to-MQTT Gateway for IoT Systems

A production-ready Bluetooth Low Energy (BLE) to MQTT gateway built for Raspberry Pi 5, featuring secure mutual TLS (mTLS) authentication, containerized services with Podman Compose, and real-time sensor data streaming.

## Overview

This project demonstrates a complete IoT data pipeline:

```
ESP32 DHT22 Sensor (BLE) 
  ↓ (Nordic UART Service)
BLE Gateway Container 
  ↓ (mTLS encrypted)
Mosquitto MQTT Broker 
  ↓ (Subscription)
MQTT Client Container (Data Display)
```

The system reads temperature and humidity values from a remote BLE sensor device and reliably publishes them to an MQTT broker with enterprise-grade security.

## Key Features

- **BLE Connectivity**: Scans for and connects to remote ESP32 DHT22 sensor via Nordic UART Service
- **Secure MQTT**: Mutual TLS (mTLS) authentication with certificate-based client verification
- **Containerized Architecture**: Three independent services (Mosquitto, BLE Gateway, MQTT Client) orchestrated with Podman Compose
- **Robust Error Handling**: Automatic connection retry logic, graceful reconnection on network issues
- **Comprehensive Logging**: Timestamped logs with ISO 8601 format for debugging and monitoring
- **Host Networking**: Uses host network mode for improved performance and direct hardware access (BLE, D-Bus)
- **Production Configuration**: Persistent certificate management, configurable MQTT topics

## System Architecture

### Service Components

| Service | Role | Technology |
|---------|------|-----------|
| **Mosquitto** | MQTT Broker | Mosquitto 2.1.2 with TLS support |
| **BLE Gateway** | Sensor-to-MQTT Bridge | Python 3 with Bleak + paho-mqtt |
| **MQTT Client** | Data Consumer | Python 3 with paho-mqtt (displays received data) |

### Communication Flow

1. **BLE Discovery**: Gateway scans for target device (MAC: `94:A9:90:1C:81:19`)
2. **BLE Connection**: Establishes GATT connection to Nordic UART Service
3. **Data Reception**: Listens for notifications in format: `T=<temp>,H=<humidity>`
4. **MQTT Publication**: Publishes to two topics:
   - `io25m025/temperature` → temperature value
   - `io25m025/humidity` → humidity value
5. **Data Consumption**: Client subscribes and displays incoming values with timestamps

## Project Structure

```
.
├── README.md                      # This file
├── docker-compose.yml             # Container orchestration
├── Dockerfile.ble                 # Legacy BLE Dockerfile (see ble/Containerfile)
│
├── ble/                          # BLE Gateway Service
│   ├── Containerfile             # Container build instructions
│   ├── entrypoint.sh             # Service startup script
│   └── gateway.py                # Main BLE-to-MQTT bridge logic
│
├── client/                       # MQTT Client Service
│   ├── Containerfile             # Container build instructions
│   ├── entrypoint.sh             # Service startup script
│   └── client.py                 # MQTT subscriber + data display
│
├── mosquitto/                    # MQTT Broker Service
│   ├── Containerfile             # Container build instructions
│   └── mosquitto.conf            # Broker configuration (TLS, auth)
│
└── certs/                        # X.509 Certificate Authority (CA)
    ├── ca.crt, ca.key            # Root CA certificate and key
    ├── ca.srl, ca.csr            # Certificate serial number log
    ├── mosquitto.{crt,csr,key}   # Mosquitto broker certificate
    ├── ble.{crt,csr,key}         # BLE gateway client certificate
    └── client.{crt,csr,key}      # MQTT client certificate
```

## Requirements

- **Hardware**: Raspberry Pi 5 (or compatible ARM64 Linux system)
- **Software**: 
  - Podman and Podman Compose
  - Bluez (BlueZ kernel drivers with D-Bus socket at `/var/run/dbus/system_bus_socket`)
  - Linux kernel with BLE support
- **Network**: Network access between containers (uses host network mode)

## Configuration

All services are configured via environment variables in `docker-compose.yml`. Key settings:

### BLE Gateway

| Variable | Default | Purpose |
|----------|---------|---------|
| `SENSOR_MAC` | `94:A9:90:1C:81:19` | Target ESP32 device Bluetooth address |
| `MQTT_HOST` | `localhost` | MQTT broker hostname |
| `MQTT_PORT` | `8883` | MQTT broker TLS port |
| `TOPIC_BASE` | `io25m025` | MQTT topic base namespace |
| `FIRST_VALUE` | `temp` | First value in payload: `temp` or `hum` |

### MQTT Client

| Variable | Default | Purpose |
|----------|---------|---------|
| `MQTT_HOST` | `localhost` | MQTT broker hostname |
| `MQTT_PORT` | `8883` | MQTT broker TLS port |
| `TOPIC_BASE` | `io25m025` | Topic base (temp topic: `{base}/temperature`) |

### Mosquitto Broker

Configuration in `mosquitto/mosquitto.conf`:
- **Port**: 8883 (TLS-only, no plaintext)
- **Authentication**: Mandatory client certificates (mTLS)
- **CA Verification**: All clients must present signed certificates
- **Persistence**: Disabled (in-memory messages)

## Installation & Setup

### Prerequisites

Ensure Podman and Podman Compose are installed:

```bash
sudo apt-get update
sudo apt-get install -y podman podman-compose bluez
```

Enable and start the D-Bus service (required for BlueZ BLE access):

```bash
sudo systemctl enable dbus
sudo systemctl start dbus
```

### Quick Start

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd hw2_gateway
   ```

2. **Verify configuration**:
   - Edit `docker-compose.yml` and set `SENSOR_MAC` to your ESP32's MAC address
   - Update `TOPIC_BASE` if needed (default: `io25m025`)

3. **Start services**:
   ```bash
   # Build and start all containers
   podman-compose up -d
   
   # Or with more verbose output for debugging:
   podman-compose up
   ```

4. **View logs**:
   ```bash
   # All services
   podman-compose logs -f
   
   # Specific service
   podman-compose logs -f ble
   podman-compose logs -f client
   podman-compose logs -f mosquitto
   ```

5. **Stop services**:
   ```bash
   podman-compose down
   ```

### Certificate Setup (if regenerating)

Certificates are pre-generated and included. To regenerate them:

```bash
cd certs
# Create new CA
openssl req -new -x509 -days 365 -nodes -out ca.crt -keyout ca.key \
  -subj "/C=AT/ST=State/L=City/O=Org/CN=ca"

# Generate server and client certificates
# (See certs/ directory for generation scripts)
```

## Operation

### Starting the Gateway

```bash
podman-compose up -d
```

The services start automatically and establish connections in order. Watch for logs:

```bash
podman-compose logs -f
```

### Expected Behavior

**Successful startup sequence**:

1. **Mosquitto**: Starts broker with TLS support
   ```
   [mosquitto] | mosquitto version 2.1.2 starting
   [mosquitto] | Opening ipv4 listen socket on port 8883
   ```

2. **BLE Gateway**: Connects to Mosquitto, scans for device
   ```
   [ble] | [mqtt] connecting to localhost:8883 with mTLS (CN=ble -> username)
   [ble] | [mqtt] connected OK
   [ble] | [ble] scanning for 94:A9:90:1C:81:19
   [ble] | [ble] found 94:A9:90:1C:81:19 name=BLE_DHT22
   ```

3. **MQTT Client**: Subscribes to topics
   ```
   [client] | [mqtt] connecting to localhost:8883 with mTLS (CN=client)
   [client] | [mqtt] connected OK, subscribing...
   ```

4. **Data Flow**: Client receives temperature and humidity
   ```
   [client] | io25m025/temperature -> 23.40
   [client] | io25m025/humidity -> 39.90
   ```

### Monitoring Data

View incoming sensor data in real-time:

```bash
podman-compose logs -f client
```

Each measurement includes:
- **Timestamp**: ISO 8601 format with timezone
- **Topic**: `io25m025/temperature` or `io25m025/humidity`
- **Value**: Float (e.g., `23.40`, `39.90`)

## Results

The system successfully demonstrates:

### MQTT Data Publishing (Verified)

Temperature and humidity values are reliably published to the MQTT broker by the BLE gateway:

```
[ble] | 2026-03-07T14:57:12+00:00 [mqtt] published io25m025/temperature -> 23.40
[ble] | 2026-03-07T14:57:12+00:00 [mqtt] published io25m025/humidity -> 39.90
[ble] | 2026-03-07T14:57:17+00:00 [mqtt] published io25m025/temperature -> 23.42
[ble] | 2026-03-07T14:57:17+00:00 [mqtt] published io25m025/humidity -> 39.88
```

### MQTT Data Reception (Verified)

The MQTT client successfully subscribes and receives published data:

```
[client] | 2026-03-07T14:57:12+00:00 io25m025/temperature -> 23.40
[client] | 2026-03-07T14:57:12+00:00 io25m025/humidity -> 39.90
[client] | 2026-03-07T14:57:17+00:00 io25m025/temperature -> 23.42
[client] | 2026-03-07T14:57:17+00:00 io25m025/humidity -> 39.88
```

### Security (mTLS Verification)

All connections are secured with mutual TLS:

```
[mosquitto] | Client ble negotiated TLSv1.3 cipher TLS_AES_256_GCM_SHA384
[mosquitto] | Client client negotiated TLSv1.3 cipher TLS_AES_256_GCM_SHA384
```

Both gateway and client authenticate using X.509 certificates signed by the project CA, with client identity mapped to username.

## Troubleshooting

### BLE Device Not Found

**Symptom**: `[ble] scan attempt 10/10 did not find target`

**Solutions**:
1. Verify sensor MAC address in `docker-compose.yml` matches your device
2. Ensure sensor is powered and advertising BLE services
3. Check BlueZ is installed: `sudo systemctl status bluetooth`
4. Run `hcitool scan` or `bluetoothctl` to verify device is visible

### MQTT Connection Refused

**Symptom**: `[mqtt] connect failed` or certificate errors

**Solutions**:
1. Verify Mosquitto container started: `podman-compose logs mosquitto`
2. Check certificates exist in `certs/` directory
3. Verify certificate file permissions: `ls -la certs/`
4. Run: `podman-compose down && podman-compose up`

### No Data Received

**Symptom**: Client connects but no temperature/humidity data

**Solutions**:
1. Check BLE device is actually transmitting (power cycle sensor)
2. Verify sensor is sending data in correct format (`T=XX.XX,H=YY.YY`)
3. Monitor gateway logs: `podman-compose logs -f ble`
4. Verify MQTT topics match (check `docker-compose.yml` `TOPIC_BASE`)

## Development

### Modifying Gateway Logic

Edit `ble/gateway.py`:
- Change Nordic UART service UUID (lines 25-27)
- Modify payload parsing in `parse_payload()` function
- Adjust connection retry logic in `run_ble()` function

Rebuild and restart:

```bash
podman-compose up --build ble
```

### Changing MQTT Topics

Modify `docker-compose.yml`:

```yaml
environment:
  - TOPIC_BASE=my_custom_topic
```

This sets:
- `my_custom_topic/temperature`
- `my_custom_topic/humidity`

## Security Considerations

### Current Implementation

- ✅ **mTLS Encryption**: TLS 1.3 with perfect forward secrecy
- ✅ **Client Authentication**: X.509 certificates with certificate verification
- ✅ **Authorization**: Username mapped from certificate CN
- ✅ **No Hardcoded Credentials**: Uses certificate-based auth only
- ⚠️ **Message Persistence**: Disabled (messages purged on disconnect)

### Production Hardening

For production use, consider:

1. **Store certificates securely**: Use volume mounts with restricted permissions
   ```bash
   chmod 600 certs/*.key
   chown root:root certs/
   ```

2. **Enable message persistence** in Mosquitto for data integrity
3. **Implement ACL rules** in Mosquitto for fine-grained access control
4. **Set up monitoring**: Collect and analyze logs from all three services
5. **Use secrets management**: For sensitive configuration (if extended)
6. **Rotate certificates regularly**: Implement automated rotation workflow
7. **Enable Mosquitto authentication logs**: `log_type all` (enabled by default)

## License

[Specify your license here, e.g., MIT, GPL-3.0, Apache-2.0]

## Author

Created as part of IoT Systems Development coursework (Assignment 2).

## References

- [Mosquitto Documentation](https://mosquitto.org/)
- [Bleak Documentation](https://bleak.readthedocs.io/)
- [Paho MQTT Python Client](https://github.com/eclipse/paho.mqtt.python)
- [Podman Compose](https://github.com/containers/podman-compose)
- [Nordic UART Service (NUS)](https://infocenter.nordicsemiconductor.com/index.jsp?topic=%2Fcom.nordic.infocenter.nrf5_sdk.v17.1.0%2Fble_sdk_app_nus.html)
