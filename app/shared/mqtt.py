"""Shared MQTT client: one broker connection, many watchers.

Built on umqtt.simple. Widgets register the topics they need with watch();
the client subscribes to exactly those (again after every reconnect), keeps
the latest payload per topic and counts messages per topic, so widgets can
detect changes cheaply in service(). Retained messages (HomeAssistant's
statestream publishes everything retained) make values available right after
subscribing.

service() runs from the main loop. Incoming messages are read with the
non-blocking check_msg(); only connect and subscribe wait for the broker,
bounded by MQTT_CONNECT_TIMEOUT_S. Connection loss is detected through socket
errors and a keepalive watchdog; reconnects use an exponential backoff.
"""

import select
import time

from umqtt.simple import MQTTClient

from app import settings


class MqttClient:
    def __init__(self):
        self.enabled = bool(settings.MQTT_HOST)
        self.connected = False
        self.revision = 0            # increases with every received message
        self.last_error = None

        self._values = {}            # topic -> latest payload (str)
        self._revisions = {}         # topic -> message count
        self._watched = []
        self._client = None
        self._poller = None
        self._next_connect = time.ticks_ms()
        self._backoff_ms = settings.MQTT_RECONNECT_MS
        self._last_rx = 0
        self._last_ping = 0

    # ------------------------------------------------------------------
    # Widget side
    # ------------------------------------------------------------------
    def watch(self, topic):
        """Subscribe to a topic (now if connected, otherwise on connect)."""
        if topic in self._watched:
            return
        self._watched.append(topic)
        if self.connected:
            try:
                self._subscribe(topic)
            except Exception as exc:
                self._drop("subscribe failed", exc)

    def get(self, topic, default=None):
        return self._values.get(topic, default)

    def revision_of(self, topic):
        return self._revisions.get(topic, 0)

    # ------------------------------------------------------------------
    # Main loop side
    # ------------------------------------------------------------------
    def service(self, now_ticks, wifi_connected):
        if not self.enabled:
            return
        if not wifi_connected:
            if self.connected:
                self._drop("wifi lost", None)
            return
        if not self.connected:
            if time.ticks_diff(now_ticks, self._next_connect) >= 0:
                self._connect(now_ticks)
            return

        keepalive_ms = settings.MQTT_KEEPALIVE_S * 1000
        try:
            # Drain what arrived since the last call; a bounded number of
            # messages per pass keeps the loop responsive.
            for _ in range(16):
                if not self._poller.poll(0):
                    break
                self._last_rx = now_ticks
                self._client.check_msg()
            if time.ticks_diff(now_ticks, self._last_ping) >= keepalive_ms // 2:
                self._client.ping()
                self._last_ping = now_ticks
            if time.ticks_diff(now_ticks, self._last_rx) > keepalive_ms * 3 // 2:
                self._drop("broker silent", None)
        except Exception as exc:
            self._drop("connection lost", exc)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _on_message(self, topic, payload):
        try:
            topic = topic.decode()
            payload = payload.decode()
        except UnicodeError:
            return
        self._values[topic] = payload
        self._revisions[topic] = self._revisions.get(topic, 0) + 1
        self.revision += 1

    def _subscribe(self, topic):
        self._client.sock.settimeout(settings.MQTT_CONNECT_TIMEOUT_S)
        self._client.subscribe(topic.encode())

    def _connect(self, now_ticks):
        try:
            client = MQTTClient(
                settings.MQTT_CLIENT_ID,
                settings.MQTT_HOST,
                settings.MQTT_PORT,
                settings.MQTT_USER or None,
                settings.MQTT_PASSWORD or None,
                keepalive=settings.MQTT_KEEPALIVE_S,
            )
            client.set_callback(self._on_message)
            client.connect(clean_session=True, timeout=settings.MQTT_CONNECT_TIMEOUT_S)
            self._client = client
            self._poller = select.poll()
            self._poller.register(client.sock, select.POLLIN)
            for topic in self._watched:
                self._subscribe(topic)
        except Exception as exc:
            self._client = None
            self.last_error = exc
            print("mqtt: connect to %s failed: %s, retry in %d s" % (settings.MQTT_HOST, exc, self._backoff_ms // 1000))
            self._next_connect = time.ticks_add(now_ticks, self._backoff_ms)
            self._backoff_ms = min(self._backoff_ms * 2, settings.MQTT_RECONNECT_MAX_MS)
            return
        self.connected = True
        self.last_error = None
        self._backoff_ms = settings.MQTT_RECONNECT_MS
        self._last_rx = now_ticks
        self._last_ping = now_ticks
        print("mqtt: connected to %s, %d topics" % (settings.MQTT_HOST, len(self._watched)))

    def _drop(self, reason, exc):
        if self._client is not None:
            try:
                self._client.sock.close()
            except Exception:
                pass
        self._client = None
        self._poller = None
        if self.connected or exc is not None:
            print("mqtt: %s%s" % (reason, (": %s" % exc) if exc is not None else ""))
        self.connected = False
        self.last_error = exc
        self._next_connect = time.ticks_add(time.ticks_ms(), self._backoff_ms)
        self._backoff_ms = min(self._backoff_ms * 2, settings.MQTT_RECONNECT_MAX_MS)
