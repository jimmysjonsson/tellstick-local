import unittest
from tellstick_local.protocol import ProtocolError, decode_message, encode_message


class CodecTests(unittest.TestCase):
    def test_firmware_wire_format(self):
        # Independent expected bytes matching client/send.py (offline only).
        expected = b"4:sendh8:protocol7:arctech5:modelC:selflearning5:housei1s4:uniti0s6:methodi2ss"
        fields = dict(protocol="arctech", model="selflearning", house=1, unit=0, method=2)
        self.assertEqual(encode_message("send", fields), expected)
        self.assertEqual(decode_message(expected), ("send", fields))

    def test_command_and_empty_hash(self):
        self.assertEqual(encode_message("reglistener"), b"B:reglistener")
        self.assertEqual(decode_message(b"B:reglistener"), ("reglistener", None))
        self.assertEqual(decode_message(b"1:xhs"), ("x", {}))

    def test_reject_malformed(self):
        for packet in (b"", b"2:x", b"1:xh", b"1:xhsjunk", b"1:xh1:aiGs s", b"1:xh1:ai100000000ss", b"1:xh1:a1:x1:a1:ys"):
            with self.subTest(packet=packet), self.assertRaises(ProtocolError):
                decode_message(packet)

    def test_limits(self):
        for value in (-1, 2**32, True, "\x00", "å", "x" * 200):
            with self.assertRaises(ProtocolError):
                encode_message("test", {"value": value})
        self.assertEqual(decode_message(encode_message("x", {"n": 0xFFFFFFFF})), ("x", {"n": 0xFFFFFFFF}))
