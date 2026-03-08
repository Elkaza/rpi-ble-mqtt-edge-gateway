#!/usr/bin/env python3
import asyncio
import ssl
import time
from datetime import datetime

import paho.mqtt.client as mqtt
from bleak import BleakClient, BleakScanner

MQTT_HOST = "localhost"
MQTT_PORT = 8883

CA_CERT = "/app/certs/ca.crt"
CLIENT_CERT = "/app/certs/ble.crt"
CLIENT_KEY = "/app/certs/ble.key"

MQTT_TOPIC_TEMP = "io25m025/temperature"
MQTT_TOPIC_HUM = "io25m025/humidity"

TARGET_MAC = "94:A9:90:1C:81:19"

# Nordic UART Service
NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID      = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID      = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

mqtt_client = None


def ts():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def log(msg):
    print(f"{ts()} {msg}", flush=True)


def setup_mqtt():
    global mqtt_client

    c = mqtt.Client(client_id="ble")
    c.tls_set(
        ca_certs=CA_CERT,
        certfile=CLIENT_CERT,
        keyfile=CLIENT_KEY,
        tls_version=ssl.PROTOCOL_TLS_CLIENT,
    )
    c.username_pw_set("ble")
    log("[mqtt] connecting to localhost:8883 with mTLS (CN=ble -> username)")
    c.connect(MQTT_HOST, MQTT_PORT, 60)
    c.loop_start()
    log("[mqtt] connected OK")
    mqtt_client = c


def publish_temp_hum(temp: str, hum: str):
    mqtt_client.publish(MQTT_TOPIC_TEMP, temp)
    mqtt_client.publish(MQTT_TOPIC_HUM, hum)
    log(f"[mqtt] published {MQTT_TOPIC_TEMP} -> {temp}")
    log(f"[mqtt] published {MQTT_TOPIC_HUM} -> {hum}")


def parse_payload(payload: str):
    """
    Expected format:
      T=23.40,H=39.90
    """
    payload = payload.strip()
    if not payload.startswith("T=") or ",H=" not in payload:
        raise ValueError(f"unexpected payload format: {payload}")

    temp_part, hum_part = payload.split(",H=", 1)
    temp = temp_part.replace("T=", "").strip()
    hum = hum_part.strip()

    float(temp)
    float(hum)
    return temp, hum


async def find_device():
    log(f"[ble] scanning for {TARGET_MAC} ...")
    for attempt in range(1, 11):
        devices = await BleakScanner.discover(timeout=3.0)
        for d in devices:
            if d.address.upper() == TARGET_MAC.upper():
                log(f"[ble] found {TARGET_MAC} name={d.name}")
                return d
        log(f"[ble] scan attempt {attempt}/10 did not find target, retrying...")
        await asyncio.sleep(1)
    raise RuntimeError(f"could not find BLE device {TARGET_MAC}")


async def run_ble():
    device = await find_device()

    got_first_packet = asyncio.Event()

    def handle_notify(_: int, data: bytearray):
        try:
            payload = data.decode("utf-8", errors="replace").strip()
            log(f"[ble] notify -> {payload}")
            temp, hum = parse_payload(payload)
            publish_temp_hum(temp, hum)
            got_first_packet.set()
        except Exception as e:
            log(f"[ble] notify parse error: {e}")

    for attempt in range(1, 11):
        try:
            log(f"[ble] connecting (attempt {attempt}/10) ...")
            async with BleakClient(device, timeout=15.0) as client:
                log(f"[ble] connected: {client.is_connected}")

                services = client.services
                if services is None:
                    log("[ble] services not ready yet")
                else:
                    found_nus = any(s.uuid.lower() == NUS_SERVICE_UUID for s in services)
                    log(f"[ble] NUS service present: {found_nus}")

                await client.start_notify(NUS_TX_UUID, handle_notify)
                log(f"[ble] notifications started on {NUS_TX_UUID}")

                # wait long enough to get packets
                try:
                    await asyncio.wait_for(got_first_packet.wait(), timeout=20.0)
                    log("[ble] first valid packet received")
                except asyncio.TimeoutError:
                    log("[ble] timeout waiting for first packet")

                # keep receiving
                while client.is_connected:
                    await asyncio.sleep(1)

                log("[ble] disconnected")
        except Exception as e:
            log(f"[ble] connection error: {type(e).__name__}: {e}")
            await asyncio.sleep(2)

    raise RuntimeError("BLE gateway failed after retries")


async def main():
    setup_mqtt()
    await run_ble()


if __name__ == "__main__":
    asyncio.run(main())
