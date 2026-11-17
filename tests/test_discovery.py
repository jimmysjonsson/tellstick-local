import contextlib
import io
import json
import socket
import unittest
from unittest.mock import MagicMock, patch

from tellstick_local import Device, DiscoveryError, TellStickClient, parse_response
from tellstick_local.__main__ import main

# Synthetic test data only; never use a real discovery packet in fixtures.
PACKET = b"TellStickNet:012345abcdef:FAKE_TOKEN:X"


class DiscoveryTests(unittest.TestCase):
    def test_decode_and_redaction(self):
        device = parse_response(PACKET, "192.168.1.193")
        self.assertEqual(device, Device("192.168.1.193", "01:23:45:AB:CD:EF", "X"))
        self.assertNotIn("FAKE_TOKEN", repr(device))
        self.assertFalse(hasattr(device, "secret"))

    def test_accepts_unknown_firmware(self):
        self.assertEqual(parse_response(PACKET[:-1] + b"17.2", "127.0.0.1").firmware_version, "17.2")

    def test_malformed_packets_have_safe_errors(self):
        for packet in (b"", b"garbage", PACKET + b":extra", PACKET.replace(b"012345abcdef", b"invalid"),
                       PACKET.replace(b"FAKE_TOKEN", b""), PACKET[:-1] + b"\xff",
                       PACKET[:-1] + b"\n", PACKET.replace(b"FAKE_TOKEN", b"x" * 2048)):
            with self.subTest(length=len(packet)):
                with self.assertRaises(DiscoveryError) as error:
                    parse_response(packet, "127.0.0.1")
                self.assertNotIn("FAKE_TOKEN", str(error.exception))

    @patch("tellstick_local.discovery.socket.socket")
    def test_discover_wire_request_filtering_deduplication(self, factory):
        sock = MagicMock()
        factory.return_value.__enter__.return_value = sock
        sock.recvfrom.side_effect = [
            (PACKET, ("192.168.1.194", 30303)),
            (PACKET, ("192.168.1.193", 42314)),
            (b"bad", ("192.168.1.193", 30303)),
            (PACKET, ("192.168.1.193", 30303)),
            (PACKET, ("192.168.1.193", 30303)), socket.timeout(),
        ]
        devices = TellStickClient().discover()
        self.assertEqual(len(devices), 1)
        sock.sendto.assert_called_once_with(b"D", ("192.168.1.193", 30303))
        sock.bind.assert_called_once_with(("0.0.0.0", 0))
        factory.return_value.__exit__.assert_called_once()

    @patch("tellstick_local.discovery.socket.socket")
    def test_broadcast_timeout(self, factory):
        sock = factory.return_value.__enter__.return_value
        sock.recvfrom.side_effect = socket.timeout()
        self.assertEqual(TellStickClient("255.255.255.255").discover(), [])
        sock.sendto.assert_called_once_with(b"D", ("255.255.255.255", 30303))

    def test_invalid_timeout(self):
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                TellStickClient(timeout=timeout)

    @patch("tellstick_local.__main__.TellStickClient")
    def test_cli_json_contains_only_public_fields(self, client):
        client.return_value.discover.return_value = [parse_response(PACKET, "127.0.0.1")]
        output = io.StringIO()
        with patch("sys.argv", ["tellstick-local", "status", "--json"]), contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertEqual(set(json.loads(output.getvalue())[0]), {"ip", "mac", "firmware_version"})

    @patch("tellstick_local.__main__.TellStickClient")
    def test_cli_no_response(self, client):
        client.return_value.discover.return_value = []
        with patch("sys.argv", ["tellstick-local", "discover"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 1)


if __name__ == "__main__":
    unittest.main()
