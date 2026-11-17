import contextlib
import io
import json
import socket
import unittest
from unittest.mock import MagicMock, patch

from tellstick_local import Device, TellStickListener, decode_event
from tellstick_local.protocol import ProtocolError, decode_message
from tellstick_local.__main__ import main

# Synthetic frame only; not captured from a real sensor.
FRAME = b'7:RawDatah5:class6:sensor8:protocol6:oregon5:modeliFFFFs4:datai123456789ABCDEF012ss'
DEVICE = Device('192.168.1.193', '01:23:45:AB:CD:EF', 'X-RX1')


class EventTests(unittest.TestCase):
    def test_raw_frame_wider_than_command_integer(self):
        event = decode_event(FRAME, DEVICE.ip)
        self.assertEqual(event.kind, 'RawData')
        self.assertEqual(event.fields['data'], 0x123456789ABCDEF012)
        with self.assertRaises(ProtocolError):decode_message(FRAME)

    def test_reject_other_commands_and_excessive_width(self):
        for packet in (b'B:reglistener',b'4:sendhs',b'4:Data',b'4:Datah4:datai'+b'F'*129+b'ss'):
            with self.subTest(length=len(packet)), self.assertRaises(ProtocolError):
                decode_event(packet, DEVICE.ip)

    @patch('tellstick_local.listener.socket.socket')
    @patch('tellstick_local.listener.TellStickClient.discover',return_value=[DEVICE])
    def test_only_registration_and_filtering(self,discover,factory):
        sock=factory.return_value
        sock.recvfrom.side_effect=[
            (FRAME,('192.168.1.194',43210)),
            (b'invalid private content', (DEVICE.ip,43210)),
            (FRAME,(DEVICE.ip,43210)),
        ]
        with TellStickListener(bind_address='192.168.1.149') as listener:
            stream=listener.events(duration=5)
            self.assertEqual(next(stream).fields['protocol'],'oregon')
            stream.close()
            self.assertEqual((listener.received,listener.malformed,listener.unexpected_sender),(1,1,1))
        sock.sendto.assert_called_once_with(b'B:reglistener',(DEVICE.ip,42314))
        sock.bind.assert_called_once_with(('192.168.1.149',0))
        sock.close.assert_called_once()

    @patch('tellstick_local.listener.socket.socket')
    @patch('tellstick_local.listener.TellStickClient.discover',return_value=[Device(DEVICE.ip,DEVICE.mac,'4')])
    def test_stock_firmware_does_not_receive_registration(self,discover,factory):
        with self.assertRaises(ValueError):
            with TellStickListener():pass
        factory.assert_not_called()

    @patch('tellstick_local.listener.socket.socket')
    @patch('tellstick_local.listener.TellStickClient.discover',return_value=[DEVICE])
    def test_timeout_ends_without_an_event(self,discover,factory):
        factory.return_value.recvfrom.side_effect=socket.timeout()
        with TellStickListener() as listener, patch('tellstick_local.listener.time.monotonic',side_effect=[0,0,2]):
            self.assertEqual(list(listener.events(duration=1)),[])
        factory.return_value.close.assert_called_once()

    @patch('tellstick_local.listener.socket.socket')
    @patch('tellstick_local.listener.TellStickClient.discover',return_value=[DEVICE])
    def test_close_socket_if_registration_fails(self,discover,factory):
        factory.return_value.sendto.side_effect=OSError('synthetic')
        with self.assertRaises(OSError):TellStickListener().__enter__()
        factory.return_value.close.assert_called_once()

    def test_invalid_addresses_and_duration(self):
        for address in ('255.255.255.255','224.0.0.1','0.0.0.0','not-an-ip'):
            with self.assertRaises(ValueError):TellStickListener(address)
        for duration in (0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):next(TellStickListener().events(duration=duration))

    @patch('tellstick_local.__main__.TellStickListener')
    def test_monitor_ndjson(self,factory):
        listener=factory.return_value.__enter__.return_value
        listener.events.return_value=[decode_event(FRAME,DEVICE.ip)]
        listener.received=1;listener.malformed=0;listener.unexpected_sender=0
        output=io.StringIO()
        with patch('sys.argv',['tellstick-local','monitor','--json','--duration','1']),contextlib.redirect_stdout(output),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(),0)
        event=json.loads(output.getvalue())
        self.assertEqual(event['fields']['data'],0x123456789ABCDEF012)
        self.assertEqual(set(event),{'received_at','device_ip','kind','fields'})

    def test_decode_error_does_not_include_packet(self):
        with self.assertRaises(ProtocolError) as caught:decode_event(b'PRIVATE_SENTINEL',DEVICE.ip)
        self.assertNotIn('PRIVATE_SENTINEL',str(caught.exception))
