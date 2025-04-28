import logging
import json
from typing import Dict, Any, Optional, Callable, Type, Mapping, Set, Tuple, List
import paho.mqtt.client as mqtt # type: ignore
import asyncio

from .debug import Debug
from .handler_protocol import HandlerProtocol

class Driver:
    def __init__(self, opts: Dict[str, Any]):
        """
        Initialize the Driver with the provided options.

        Args:
            opts: Configuration options including:
                - handler: Handler class for device-specific logic
                - env: Environment configuration
        """
        self.HandlerClass: Type[HandlerProtocol] | None = opts.get('handler')

        self.status = "DOWN"
        self.clear_addrs()

        env = opts.get("env", {})
        self.debug = Debug(env.get("VERBOSE", ""))
        self.log = self.debug.bound("driver")

        self.id = env.get("EDGE_USERNAME")

        self.mqtt_host, self.mqtt_port = self.get_mqtt_details(env.get("EDGE_MQTT"))
        self.mqtt = self.create_mqtt_client(env.get("EDGE_PASSWORD"))

        self.message_handlers: Dict[str, Callable[[str], None]] = {}
        self.setup_message_handlers()

        self.reconnect = 5000
        self.reconnecting = False

    def run(self) -> None:
        """Run the driver. This connects to the MQTT broker and starts the
        MQTT loop."""
        self.mqtt.connect_async(self.mqtt_host, self.mqtt_port)
        self.mqtt.loop_start()

    def topic(self, msg, data=None) -> str:
        """Construct a topic string for the given message and data."""
        return f"fpEdge1/{self.id}/{msg}" + (f"/{data}" if data else "")

    def json(self, buf: str|bytes|bytearray) -> Optional[dict]:
        """
        Parse a JSON string or buffer into a Python dictionary.

        Attempts to convert the input buffer to a string and parse it as JSON.
        If parsing fails, logs the error and returns None.

        Args:
            buf: The input to parse, can be a string, bytes, or bytearray

        Returns:
            Dict containing the parsed JSON data, or None if parsing failed
        """
        try:
            return json.loads(str(buf))
        except Exception as e:
            self.log("JSON parse error: %s", e)
            return None

    def create_mqtt_client(self, password: str) -> mqtt.Client:
        """
        Create and configure MQTT client.

        Args:
            password: Authentication password

        Returns:
            Configured MQTT client. This should be used to connect when running
            the driver.
        """
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.id,
            reconnect_on_failure=False,
        )
        client.username_pw_set(self.id, password)
        client.on_connect = self.connected
        client.on_message = self.handle_message
        client.will_set(self.topic("status"), payload="DOWN")

        return client

    def setup_handler(self, conf: Optional[dict] = None) -> bool:
        if not conf:
            return False

        if not self.HandlerClass:
            return False

        self.handler = self.HandlerClass.create(self, conf)

        valid = getattr(self.handler.__class__, 'validAddrs', None)
        parse = getattr(self.handler, 'parseAddr', lambda a: a)

        def handle_addrs(addrs):
                entries = list(addrs.items())

                if valid:
                    bad_entries = [(t, a) for t, a in entries if a not in valid]
                    if bad_entries:
                        self.log(f"Invalid addresses: {bad_entries}")
                        return False

                parsed_entries = [(t, parse(a)) for t, a in entries]

                bad_addresses = [addrs[t] for t, s in parsed_entries if not s]
                if bad_addresses:
                    self.log(f"Invalid addresses: {bad_addresses}")
                    return False

                return parsed_entries

        self.handle_addrs = handle_addrs

        return True

    def set_status(self, status: str) -> None:
        return

    def connect_handler(self) -> None:
        return

    def conn_up(self) -> None:
        return

    def conn_failed(self) -> None:
        return

    def conn_unauth(self) -> None:
        return

    def reconnect_handler(self) -> None:
        return

    def clear_addrs(self) -> None:
        """Reset device addresses and topics to an empty state."""
        self.addrs = set()
        self.topics = set()

    def set_addrs(self, pkt: dict) -> None:
        return

    def subscribe(self, specs: List[Any]) -> None:
        return

    def connected(self) -> None:
        """Subscribe to topics and set ready status."""
        self.log("Connected to broker")

    def handle_message(self) -> None:
        """Handle incoming MQTT messages."""
        self.log("Handling message")

    def message(self, msg: str, handler: Callable[[str], None]) -> None:
        """
        Register a handler function for a specific message.

        Args:
            msg: The message identifier to associate with the handler
            handler: A callback function that accepts a string parameter and returns None,
                    which will be called when the specified message is received
        """
        self.message_handlers[msg] = handler

    def setup_message_handlers(self) -> None:
        """Set up handlers for different message types."""
        return

    def get_mqtt_details(self, broker: str) -> Tuple[str, str]:
        """
        Parse the MQTT broker URL to extract host and port.

        Args:
            broker: MQTT broker URL in format "mqtt://host:port" or "host:port"

        Returns:
            A tuple containing (host, port) as strings
        """
        if broker.startswith("mqtt://"):
            broker = broker[7:]

        host_and_port = broker.split(":")
        return host_and_port[0], host_and_port[1]
