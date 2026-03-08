#!/usr/bin/env python3
import os
import ssl
import sys
import time
import re
from datetime import datetime

from pydbus import SystemBus
from gi.repository import GLib
import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
TOPIC_BASE = os.getenv("TOPIC_BASE", "io25m025")
TARGET_MAC = os.getenv("SENSOR_MAC", "94:A9:90:1C:81:19").upper().replace(":", "_")

CA_CERT = "/certs/ca.crt"
CLIENT_CERT = "/certs/ble.crt"
CLIENT_KEY = "/certs/ble.key"

MQTT_TOPIC_TEMP = f"{TOPIC_BASE}/temperature"
MQTT_TOPIC_HUM = f"{TOPIC_BASE}/humidity"

BLUEZ_SERVICE = "org.bluez"
OM_IFACE = "org.freedesktop.DBus.ObjectManager"
PROP_IFACE = "org.freedesktop.DBus.Properties"
ADAPTER_IFACE = "org.bluez.Adapter1"
DEVICE_IFACE = "org.bluez.Device1"
GATT_CHAR_IFACE = "org.bluez.GattCharacteristic1"

NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

bus = None
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


def publish_values(temp, hum):
    mqtt_client.publish(MQTT_TOPIC_TEMP, f"{temp:.2f}", qos=0)
    mqtt_client.publish(MQTT_TOPIC_HUM, f"{hum:.2f}", qos=0)
    log(f"[mqtt] published temperature={temp:.2f} humidity={hum:.2f}")


def parse_payload(text):
    m = re.search(r"T\s*=\s*(-?\d+(?:\.\d+)?)\s*,\s*H\s*=\s*(-?\d+(?:\.\d+)?)", text, re.I)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def get_managed_objects():
    om = bus.get(BLUEZ_SERVICE, "/")
    return om.GetManagedObjects()


def find_adapter_path():
    objects = get_managed_objects()
    for path, ifaces in objects.items():
        if ADAPTER_IFACE in ifaces:
            return path
    return None


def find_device_path():
    objects = get_managed_objects()
    suffix = f"dev_{TARGET_MAC}"
    for path, ifaces in objects.items():
        if DEVICE_IFACE in ifaces and path.endswith(suffix):
            return path
    return None


def start_discovery(adapter):
    try:
        log("[ble] starting discovery...")
        adapter.StartDiscovery()
    except Exception as e:
        log(f"[ble] StartDiscovery warning: {e}")


def stop_discovery(adapter):
    try:
        log("[ble] stopping discovery...")
        adapter.StopDiscovery()
    except Exception as e:
        log(f"[ble] StopDiscovery warning: {e}")


def wait_for_device(adapter, timeout=20):
    start_discovery(adapter)
    start = time.time()
    while time.time() - start < timeout:
        path = find_device_path()
        if path:
            log(f"[ble] found device at {path}")
            stop_discovery(adapter)
            return path
        time.sleep(1)
    stop_discovery(adapter)
    return None


def connect_device(dev):
    for attempt in range(1, 11):
        try:
            log(f"[ble] Connecting (attempt {attempt}/10)...")
            dev.Connect()
            time.sleep(3)
            log("[ble] Connected OK")
            return True
        except Exception as e:
            log(f"[ble] Connect error: {e}")
            time.sleep(2)
    return False


def find_tx_char_path(device_path, timeout=20):
    log("[ble] waiting for TX characteristic to appear...")
    start = time.time()

    while time.time() - start < timeout:
        objects = get_managed_objects()

        for path, ifaces in objects.items():
            if not path.startswith(device_path):
                continue
            if GATT_CHAR_IFACE not in ifaces:
                continue

            uuid = str(ifaces[GATT_CHAR_IFACE].get("UUID", "")).lower()
            if uuid == NUS_TX_UUID:
                log(f"[ble] found TX char: {path}")
                return path

        time.sleep(1)

    return None


def on_properties_changed(iface, changed, invalidated, path=None):
    if iface != GATT_CHAR_IFACE:
        return
    if "Value" not in changed:
        return

    try:
        raw = bytes(changed["Value"])
        text = raw.decode("utf-8", errors="ignore").strip()
        log(f"[ble] notify payload: {text}")
        vals = parse_payload(text)
        if vals is None:
            log("[ble] payload format not recognized")
            return
        temp, hum = vals
        publish_values(temp, hum)
    except Exception as e:
        log(f"[ble] notification parse error: {e}")


def subscribe_notifications(tx_path):
    tx = bus.get(BLUEZ_SERVICE, tx_path)

    bus.subscribe(
        sender=BLUEZ_SERVICE,
        object=tx_path,
        iface=PROP_IFACE,
        signal="PropertiesChanged",
        signal_fired=lambda sender, obj, iface, signal, params: on_properties_changed(
            params[0], params[1], params[2], obj
        ),
    )

    log("[ble] starting notifications...")
    tx.StartNotify()
    log("[ble] notifications started")


def run():
    global bus

    setup_mqtt()
    bus = SystemBus()

    adapter_path = find_adapter_path()
    if not adapter_path:
        log("[ble] ERROR: no Bluetooth adapter found")
        sys.exit(1)

    log(f"[ble] adapter found: {adapter_path}")
    adapter = bus.get(BLUEZ_SERVICE, adapter_path)

    device_path = wait_for_device(adapter, timeout=20)
    if not device_path:
        log("[ble] ERROR: device not found")
        sys.exit(1)

    dev = bus.get(BLUEZ_SERVICE, device_path)

    if not connect_device(dev):
        log("[ble] ERROR: could not connect after retries")
        sys.exit(1)

    tx_path = find_tx_char_path(device_path, timeout=20)
    if not tx_path:
        log("[ble] ERROR: TX characteristic not found after connect")
        sys.exit(1)

    subscribe_notifications(tx_path)

    log("[ble] gateway running")
    GLib.MainLoop().run()


if __name__ == "__main__":
    run()
