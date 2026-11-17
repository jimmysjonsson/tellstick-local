"""Receive-only transport for the physically verified X-RX1 firmware."""
from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
import math
import socket
import time

from .discovery import TellStickClient
from .protocol import ProtocolError, decode_message

REGISTRATION = b"B:reglistener"


@dataclass(frozen=True, slots=True)
class Event:
    received_at: str
    device_ip: str
    kind: str
    fields: dict[str, str | int]


def decode_event(packet: bytes, device_ip: str) -> Event:
    kind, fields = decode_message(packet, max_integer_digits=128)
    if kind not in ("Data", "RawData") or fields is None:
        raise ProtocolError("Expected a received event")
    return Event(datetime.now(timezone.utc).isoformat(), device_ip, kind, fields)


class TellStickListener:
    """One UDP listener; only sends discovery and exact listener registration.

    The firmware supports a single listener and has no registration ACK or
    unregister command. Close releases the host socket, not firmware state.
    """

    def __init__(self, target="192.168.1.193", *, bind_address="0.0.0.0", timeout=3.0):
        self.client = TellStickClient(target, bind_address=bind_address, timeout=timeout)
        address = ipaddress.IPv4Address(self.client.target)
        if address.is_multicast or address.is_unspecified or int(address) == 0xFFFFFFFF:
            raise ValueError("Listener requires a unicast device address")
        self._socket = None
        self.received = self.malformed = self.unexpected_sender = 0

    def __enter__(self):
        if self._socket is not None:
            raise RuntimeError("Listener is already open")
        devices = self.client.discover()
        if not any(d.ip == self.client.target and d.firmware_version in ("X-RX1", "X-TX1") for d in devices):
            raise ValueError("Expected X-RX1/X-TX1 firmware was not discovered")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((self.client.bind_address, 0))
            sock.sendto(REGISTRATION, (self.client.target, 42314))
        except BaseException:
            sock.close()
            raise
        self._socket = sock
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def events(self, *, duration=60.0):
        if duration is not None and (not math.isfinite(duration) or duration <= 0):
            raise ValueError("Duration must be finite and positive")
        if self._socket is None:
            raise RuntimeError("Open the listener with a context manager first")
        deadline = None if duration is None else time.monotonic() + duration
        while self._socket is not None:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                return
            self._socket.settimeout(1 if remaining is None else min(1, remaining))
            try:
                packet, peer = self._socket.recvfrom(2048)
            except socket.timeout:
                continue
            if peer[0] != self.client.target:
                self.unexpected_sender += 1
                continue
            try:
                event = decode_event(packet, peer[0])
            except ProtocolError:
                self.malformed += 1
                continue
            self.received += 1
            yield event
