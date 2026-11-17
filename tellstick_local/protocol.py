"""Offline local-message codec; this module has no network transport.

The inspected firmware has a 200-byte buffer, including the trailing NUL.
Only its flat string/integer hash format is supported here.
"""
import re


class ProtocolError(ValueError):
    """Invalid message; never includes input data."""


def encode_message(command: str, fields: dict[str, str | int] | None = None) -> bytes:
    def string(value: str) -> bytes:
        try:
            raw = value.encode("ascii")
        except UnicodeError:
            raise ProtocolError("Strings must be ASCII") from None
        if any(ch < 32 or ch > 126 for ch in raw) or len(raw) > 255:
            raise ProtocolError("Invalid string")
        return f"{len(raw):X}:".encode() + raw

    result = string(command)
    if fields is not None:
        result += b"h"
        for key, value in fields.items():
            result += string(key)
            if type(value) is int and 0 <= value <= 0xFFFFFFFF:
                result += f"i{value:X}s".encode()
            elif isinstance(value, str):
                result += string(value)
            else:
                raise ProtocolError("Values must be strings or unsigned 32-bit integers")
        result += b"s"
    if len(result) > 199:
        raise ProtocolError("Message exceeds firmware buffer capacity")
    return result


def decode_message(packet: bytes, *, max_integer_digits: int = 8) -> tuple[str, dict[str, str | int] | None]:
    # Received RawData frames can exceed the 32-bit command-integer limit.
    if type(max_integer_digits) is not int or not 1 <= max_integer_digits <= 128:
        raise ProtocolError("Invalid integer width limit")
    if not packet or len(packet) > 199 or any(ch < 32 or ch > 126 for ch in packet):
        raise ProtocolError("Invalid message")
    pos = 0

    def string() -> str:
        nonlocal pos
        end = packet.find(b":", pos)
        if end < 0 or re.fullmatch(rb"[0-9A-Fa-f]{1,2}", packet[pos:end]) is None:
            raise ProtocolError("Invalid string length")
        size = int(packet[pos:end], 16)
        pos = end + 1
        if pos + size > len(packet):
            raise ProtocolError("Truncated string")
        value = packet[pos:pos + size].decode("ascii")
        pos += size
        return value

    command = string()
    if pos == len(packet):
        return command, None
    if packet[pos:pos+1] != b"h":
        raise ProtocolError("Expected hash")
    pos += 1
    fields = {}
    while pos < len(packet) and packet[pos:pos+1] != b"s":
        key = string()
        if key in fields:
            raise ProtocolError("Duplicate hash key")
        if packet[pos:pos+1] == b"i":
            end = packet.find(b"s", pos + 1)
            digits = packet[pos+1:end] if end >= 0 else b""
            if not 1 <= len(digits) <= max_integer_digits or re.fullmatch(rb"[0-9A-Fa-f]+", digits) is None:
                raise ProtocolError("Invalid integer")
            value = int(packet[pos+1:end], 16)
            pos = end + 1
        else:
            value = string()
        fields[key] = value
    if packet[pos:] != b"s":
        raise ProtocolError("Missing hash terminator or trailing data")
    return command, fields
