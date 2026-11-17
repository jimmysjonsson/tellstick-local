"""UDP discovery based on the original firmware's discovery.c."""
from dataclasses import dataclass
import ipaddress
import math
import re
import socket
import time

DISCOVERY_PORT = 30303
DISCOVERY_REQUEST = b"D"


class DiscoveryError(ValueError):
    """Invalid discovery response; messages never contain packet contents."""


@dataclass(frozen=True, slots=True)
class Device:
    ip: str
    mac: str
    firmware_version: str


def parse_response(packet: bytes, ip: str) -> Device:
    """Validate a response and discard its secret without decoding or retaining it."""
    fields = packet.split(b":")
    valid = (
        len(packet) <= 2048
        and len(fields) == 4
        and fields[0] == b"TellStickNet"
        and re.fullmatch(rb"[0-9A-Fa-f]{12}", fields[1]) is not None
        and bool(fields[2])
        and all(33 <= ch <= 126 for ch in fields[2])
        and re.fullmatch(rb"[A-Za-z0-9._+-]{1,64}", fields[3]) is not None
    )
    if not valid:
        raise DiscoveryError("Invalid TellStick Net discovery response")
    address = str(ipaddress.IPv4Address(ip))
    mac = fields[1].decode("ascii").upper()
    return Device(address, ":".join(mac[i:i+2] for i in range(0, 12, 2)),
                  fields[3].decode("ascii"))


class TellStickClient:
    """Read-only client. No API sends packets to the local command port."""

    def __init__(self, target: str = "192.168.1.193", *,
                 bind_address: str = "0.0.0.0", timeout: float = 3.0):
        self.target = str(ipaddress.IPv4Address(target))
        self.bind_address = str(ipaddress.IPv4Address(bind_address))
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be finite and positive")
        self.timeout = timeout

    def discover(self) -> list[Device]:
        devices = {}
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # Firmware replies to the request source port; no fixed port needed.
            sock.bind((self.bind_address, 0))
            sock.sendto(DISCOVERY_REQUEST, (self.target, DISCOVERY_PORT))
            deadline = time.monotonic() + self.timeout
            while (remaining := deadline - time.monotonic()) > 0:
                sock.settimeout(remaining)
                try:
                    packet, (ip, port) = sock.recvfrom(65535)
                except socket.timeout:
                    break
                if port != DISCOVERY_PORT:
                    continue
                if self.target != "255.255.255.255" and ip != self.target:
                    continue
                try:
                    device = parse_response(packet, ip)
                except DiscoveryError:
                    continue
                finally:
                    del packet
                devices[(device.ip, device.mac)] = device
        return sorted(devices.values(), key=lambda device: (device.ip, device.mac))
