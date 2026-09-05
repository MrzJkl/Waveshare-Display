"""HomeAssistant entities via MQTT Statestream.

HomeAssistant's mqtt_statestream integration publishes every entity as
retained topics below a base topic:
    <base>/<domain>/<object_id>/state           the state, e.g. "21.3" or "on"
    <base>/<domain>/<object_id>/<attribute>     each attribute; lists and dicts as JSON

This class turns entity ids into those topics and offers typed access. Widgets
register the entities they need once (watch_*) and read the latest values in
draw(); values arrive asynchronously through the shared MQTT client.
"""

import json

UNKNOWN_STATES = ("unknown", "unavailable", "None", "")


class HomeAssistant:
    def __init__(self, mqtt, base_topic):
        self.mqtt = mqtt
        self.base_topic = base_topic
        # Topic strings are cached: widgets ask for the same ones on every loop
        # pass, and building them there would allocate a few dozen strings per
        # pass, which shows up as garbage collector pauses in animations.
        self._state_topics = {}
        self._attribute_topics = {}

    # --- topics -----------------------------------------------------------
    def state_topic(self, entity_id):
        topic = self._state_topics.get(entity_id)
        if topic is None:
            domain, object_id = entity_id.split(".", 1)
            topic = "%s/%s/%s/state" % (self.base_topic, domain, object_id)
            self._state_topics[entity_id] = topic
        return topic

    def attribute_topic(self, entity_id, attribute):
        per_entity = self._attribute_topics.get(entity_id)
        if per_entity is None:
            per_entity = {}
            self._attribute_topics[entity_id] = per_entity
        topic = per_entity.get(attribute)
        if topic is None:
            domain, object_id = entity_id.split(".", 1)
            topic = "%s/%s/%s/%s" % (self.base_topic, domain, object_id, attribute)
            per_entity[attribute] = topic
        return topic

    # --- registration -------------------------------------------------------
    def watch_state(self, entity_id):
        self.mqtt.watch(self.state_topic(entity_id))

    def watch_attribute(self, entity_id, attribute):
        self.mqtt.watch(self.attribute_topic(entity_id, attribute))

    # --- values -------------------------------------------------------------
    def state(self, entity_id, default=None):
        """Raw state string, or default when unknown/unavailable/not yet received."""
        value = self.mqtt.get(self.state_topic(entity_id))
        if value is None or value in UNKNOWN_STATES:
            return default
        return value

    def state_float(self, entity_id, default=None):
        value = self.state(entity_id)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            return default

    def state_bool(self, entity_id, default=None):
        value = self.state(entity_id)
        if value is None:
            return default
        return value in ("on", "true", "True", "1", "home", "open")

    def attribute(self, entity_id, attribute, default=None):
        """Attribute value. Statestream publishes attributes JSON-encoded
        (numbers bare, strings quoted, lists and dicts as JSON), so the payload
        is decoded; undecodable payloads are returned as the raw string."""
        value = self.mqtt.get(self.attribute_topic(entity_id, attribute))
        if value is None or value in UNKNOWN_STATES:
            return default
        try:
            value = json.loads(value)
        except ValueError:
            return value
        return default if value is None else value

    def attribute_float(self, entity_id, attribute, default=None):
        value = self.attribute(entity_id, attribute)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def revision_of(self, entity_id, attribute=None):
        """Message counter of the entity's state topic (or one attribute topic)."""
        if attribute is None:
            return self.mqtt.revision_of(self.state_topic(entity_id))
        return self.mqtt.revision_of(self.attribute_topic(entity_id, attribute))
