"""USB Mux device representation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class MuxDevice:
    """Represents a device connected through usbmuxd.

    Attributes:
        device_id: Numeric ID assigned by usbmuxd.
        udid: Unique device identifier (40 hex chars for pre-iOS 17, 25 for iOS 17+).
        serial: Device serial number.
        connection_type: How the device is connected ('USB' or 'Network').
        product_id: USB product ID.
        location_id: USB location identifier.
    """

    device_id: int
    udid: str
    serial: str = ""
    connection_type: str = "USB"
    product_id: int = 0
    location_id: int = 0

    @classmethod
    def from_plist(cls, plist: dict) -> "MuxDevice":
        """Create a MuxDevice from usbmuxd plist response.

        Args:
            plist: Dictionary from usbmuxd device listing.

        Returns:
            A MuxDevice instance.
        """
        props = plist.get("Properties", plist)
        return cls(
            device_id=plist.get("DeviceID", props.get("DeviceID", 0)),
            udid=props.get("SerialNumber", ""),
            serial=props.get("SerialNumber", ""),
            connection_type=props.get("ConnectionType", "USB"),
            product_id=props.get("ProductID", 0),
            location_id=props.get("LocationID", 0),
        )

    @property
    def is_usb(self) -> bool:
        """Whether this device is connected via USB."""
        return self.connection_type.upper() == "USB"

    @property
    def is_network(self) -> bool:
        """Whether this device is connected via network."""
        return self.connection_type.upper() == "NETWORK"

    def matches(
        self,
        udid: Optional[str] = None,
        connection_type: Optional[str] = None,
    ) -> bool:
        """Check if this device matches the given criteria.

        Args:
            udid: UDID to match (None matches any).
            connection_type: Connection type to match (None matches any).

        Returns:
            True if the device matches all specified criteria.
        """
        if udid is not None and self.udid != udid:
            return False
        if connection_type is not None:
            if self.connection_type.upper() != connection_type.upper():
                return False
        return True
