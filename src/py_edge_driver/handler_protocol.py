"""
Handler Protocol Module

This module defines the protocol (interface) that all device handlers must implement.
Handlers are responsible for the device-specific logic and communication details.
"""

from typing import Protocol, ClassVar, Optional, Set, Any, Dict, Callable
from .driver import Driver

class HandlerProtocol(Protocol):
    """
    Protocol defining the interface for device handlers.

    Any class implementing this protocol can be used as a device handler
    with the Driver class.
    """

    validAddrs: ClassVar[Optional[Set[Any]]]
    """Set of valid addresses that this handler can manage, or None if any address is valid."""

    def parseAddr(self, addr: Any) -> Any:
        """
        Parse a device address into a format usable by the handler.

        Args:
            addr: The raw address to parse

        Returns:
            The parsed address, or a falsy value if parsing failed
        """
        ...

    def close(self, callback: Optional[Callable[[], None]] = None) -> Any:
        """
        Close the handler and clean up any resources.

        Args:
            callback: Optional callback function to call when closing is complete

        Returns:
            An optional result that may be used by the driver
        """
        ...

    @classmethod
    def create(cls, driver: 'Driver', conf: Dict[str, Any]) -> Optional['HandlerProtocol']:
        """
        Create a new handler instance for the given driver and configuration.

        Args:
            driver: The driver instance that will use this handler
            conf: Configuration data for initializing the handler

        Returns:
            A new handler instance, or None if creation failed
        """
        ...
