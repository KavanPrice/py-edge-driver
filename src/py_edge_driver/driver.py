import logging
import json
from typing import Dict, Any, Optional, Callable, Type, Mapping, Set, Tuple, List
import paho.mqtt.client as mqtt # type: ignore
import asyncio

from .debug import Debug
from .handler_protocol import HandlerProtocol

# Permitted status returns from Handler.connect.
CONNECT_STATUS: Set[str] = {"UP", "CONN", "AUTH"}

class Driver:
    def __init__(self, opts: Dict[str, Any]):
        """
        Initialize the Driver with the provided options.

        Args:
            opts: Configuration options including:
                - handler: Handler class for device-specific logic
                - env: Environment configuration
        """
        self.HandlerClass: Type[HandlerProtocol] | None = opts.get("handler")

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

        # Create an asyncio event loop for running async tasks in sync contexts
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Create event loop executor
        self._background_tasks = set()

    def run(self) -> None:
        """Run the driver. This connects to the MQTT broker and starts the
        MQTT loop."""
        self.mqtt.connect_async(self.mqtt_host, self.mqtt_port)
        self.mqtt.loop_start()

        try:
            self.loop.run_until_complete(self.connect_handler())
            self.loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.loop.run_until_complete(self._async_cleanup())
            self.loop.close()

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
        self.status = status
        if self.mqtt.is_connected:
            self.mqtt.publish(self.topic("status"), status)

    async def connect_handler(self) -> None:
        """
        Asynchronously attempts to connect the handler to its underlying device.

        This method calls the handler's connect method which may return:
        - An awaitable object that resolves to a connection status string
        - None if the handler is using callbacks for connection management

        If a status is returned, it's validated against the CONNECT_STATUS set.
        Valid statuses will update the driver's status. If the status is not "UP",
        a reconnection attempt will be scheduled.

        After successful connection, this method subscribes to relevant topics.
        """
        self.log("Connecting handler")
        if not self.handler:
            return

        result = self.handler.connect()

        # If this is None, the handler is using callbacks.
        if not result:
            return

        status = await result
        if status in CONNECT_STATUS:
            self.set_status(status)
        else:
            self.log(f"Handler.connect returned invalid value: {status}")

        if status != "UP":
            self._run_async(self.reconnect_handler())

        self.subscribe()

    def conn_up(self) -> None:
        self.set_status("UP")
        self.subscribe()

    def conn_failed(self) -> None:
        self.set_status("CONN")
        self._run_async(self.reconnect_handler())

    def conn_unauth(self) -> None:
        self.set_status("AUTH")
        self._run_async(self.reconnect_handler())

    async def reconnect_handler(self) -> None:
        if self.reconnecting:
            self.log("Handler already reconnecting")
            return

        self.reconnecting = True
        self.log("Handler disconnected")
        await asyncio.sleep(self.reconnect)
        self.reconnecting = False
        self._run_async(self.connect_handler())


    def clear_addrs(self) -> None:
        """Reset device addresses and topics to an empty state."""
        self.addrs = set()
        self.topics = set()

    def set_addrs(self, pkt: dict) -> None:
        return

    def subscribe(self) -> None:
        return

    async def connected(self) -> None:
        """Subscribe to topics and set ready status."""
        topics = [(self.topic(t), 0) for t in self.message_handlers.keys()]

        if topics:
            result, mid = self.mqtt.subscribe(topics)
            if result != mqtt.MQTT_ERR_SUCCESS:
                self.log(f"Failed to subscribe to topics: {result}")

        self.set_status("READY")

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

    def get_mqtt_details(self, broker: str) -> Tuple[str, int]:
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
        return host_and_port[0], int(host_and_port[1])

    async def _async_cleanup(self):
        """Cleanup async resources when shutting down"""
        for task in self._background_tasks:
            task.cancel()
            if self._background_tasks:
                await asyncio.gather(*self._background_tasks, return_exceptions=True)

    def _run_async(self, coro):
        """Run a coroutine from a synchronous context, tracking the task"""
        task = self.loop.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)