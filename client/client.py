#!/usr/bin/env python3
import os
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

def utc_ts():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def log(msg):
    print(f"{utc_ts()} {msg}", flush=True)

def main():
    host = os.getenv("MQTT_HOST", "localhost")
    port = int(os.getenv("MQTT_PORT", "8883"))

    ca = os.getenv("MQTT_CA", "/certs/ca.crt")
    cert = os.getenv("MQTT_CERT", "/certs/client.crt")
    key = os.getenv("MQTT_KEY", "/certs/client.key")

    base = os.getenv("TOPIC_BASE", "io25m025")
    topic_temp = os.getenv("TOPIC_TEMP", f"{base}/temperature")
    topic_hum = os.getenv("TOPIC_HUM", f"{base}/humidity")

    c = mqtt.Client(client_id="client", clean_session=True)

    # TLS + client certificate auth
    c.tls_set(ca_certs=ca, certfile=cert, keyfile=key)
    c.tls_insecure_set(False)

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            log("[mqtt] connected OK, subscribing...")
            client.subscribe([(topic_temp, 0), (topic_hum, 0)])
        else:
            log(f"[mqtt] connect failed rc={rc}")

    def on_message(client, userdata, msg):
        log(f"{msg.topic} -> {msg.payload.decode(errors='replace')}")

    c.on_connect = on_connect
    c.on_message = on_message

    log(f"[mqtt] connecting to {host}:{port} with mTLS (CN=client -> username)")
    c.connect(host, port, keepalive=30)
    c.loop_forever()

if __name__ == "__main__":
    main()
