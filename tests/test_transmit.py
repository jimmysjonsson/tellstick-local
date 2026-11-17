from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tellstick_local.transmit import RFClient,RFError,RFUncertainError,Waveform,waveform,encode_request

ROOT=Path(__file__).resolve().parents[1]


def device(protocol='arctech',model='selflearning-switch:nexa',house='12345',unit='1'):
    return {'protocol':protocol,'model':model,'parameter':[{'name':'house','value':house},{'name':'unit','value':unit}]}


class EncoderTests(unittest.TestCase):
    def test_frame_lengths_and_unit_index(self):
        on=waveform(device(),1);off=waveform(device(),2)
        self.assertEqual(len(on.pulses),132)
        self.assertEqual(on.pulses[:2],(24,255))
        self.assertNotEqual(on,off)
        dim=waveform(device(model='selflearning-dimmer:nexa'),16,123)
        self.assertEqual(len(dim.pulses),147)
        self.assertEqual(waveform(device(model='selflearning-dimmer:nexa'),1),waveform(device(model='selflearning-dimmer:nexa'),16,255))
        # Unit 1 uses the all-zero on-air unit code; unit 16 uses all ones.
        self.assertEqual(on.pulses[114:130],(24,24,24,127)*4)
        self.assertEqual(waveform(device(unit='16'),1).pulses[114:130],(24,127,24,24)*4)

    def test_comen_house_transformation(self):
        self.assertEqual(waveform(device(protocol='comen',house='7'),1),waveform(device(house=str((7<<2)|2)),1))
        with self.assertRaises(RFError):waveform(device(protocol='comen'),16,100)

    def test_codeswitch_and_repeats(self):
        wave=waveform(device(model='codeswitch:nexa',house='A'),1,repeats=3)
        self.assertEqual(wave.pulses[:32],tuple(map(ord,'$k$k'*8)))
        self.assertEqual(wave.frames,30)
        self.assertNotEqual(waveform(device(model='codeswitch:nexa',house='A'),1),waveform(device(model='codeswitch:nexa',house='A'),2))

    def test_strict_protocol_bounds(self):
        for change in ({'house':'0'},{'house':'67108864'},{'unit':'0'},{'unit':'17'},{'protocol':'unsupported'},{'model':'bell'}):
            with self.subTest(change=change),self.assertRaises(RFError):waveform(device(**change),1)
        for wave in (Waveform((0,)),Waveform((601,)),Waveform((600,)*21),Waveform((24,),frames=101),Waveform((24,),gap_ms=51)):
            with self.assertRaises(RFError):encode_request(wave,b'TEST')

    def test_binary_request_bounds(self):
        wave=waveform(device(),1)
        packet=encode_request(wave,b'TEST')
        self.assertEqual(packet[:11],b'TX1\0TEST'+bytes([10,11,132]))
        self.assertEqual(struct.unpack('!132H',packet[11:]),wave.pulses)

    @patch('tellstick_local.transmit.secrets.token_bytes',return_value=b'TEST')
    @patch('tellstick_local.transmit.socket.socket')
    def test_ack_filter_and_send_once(self,factory,nonce):
        sock=factory.return_value.__enter__.return_value
        sock.recvfrom.side_effect=[(b'TA1\0TEST\0',('192.168.1.194',42314)),(b'TA1\0NOPE\0',('192.168.1.193',42314)),(b'TA1\0TEST\0',('192.168.1.193',42314))]
        RFClient().send(device(),1)
        sock.sendto.assert_called_once()
        self.assertEqual(sock.sendto.call_args.args[0],encode_request(waveform(device(),1),b'TEST'))

    @patch('tellstick_local.transmit.socket.socket')
    def test_timeout_is_uncertain_and_not_retransmitted(self,factory):
        sock=factory.return_value.__enter__.return_value;sock.recvfrom.side_effect=socket.timeout()
        with self.assertRaises(RFUncertainError):RFClient().send(device(),1)
        sock.sendto.assert_called_once()

    def test_firmware_validation_before_pins_and_duplicate_suppression(self):
        text=(ROOT/'firmware-build/tx-profile/txcontrol.c').read_text()
        start=text.index('static void transmitFrame(');end=text.index('\nunsigned char txControl(',start)
        text=text[:start]+'static unsigned calls=0;\nstatic void transmitFrame(unsigned char count) { (void)count; ++calls; }\n'+text[end:]
        text='\n'.join(line for line in text.splitlines() if not line.startswith('#include'))
        harness='''#include <assert.h>
#include <string.h>
static unsigned char SENDER=0,RX_ANT=1,TX_ANT=0,TMR1ON=0,TMR4ON=1,TMR4IF=0,TMR2IE=1,TMR1IE=0,T1CON=0;
#define __delay_ms(x) ((void)(x))
#define ClrWdt() ((void)0)
static void setTXPulses(unsigned char n) { (void)n; }
'''+text+'''
int main(void) {
 unsigned char packet[15]={'T','X','1',0,'T','E','S','T',2,0,2,0,24,0,255};
 assert(txControl(packet,15)==0 && calls==2 && TX_ANT==0 && RX_ANT==1 && SENDER==0);
 assert(txControl(packet,15)==0 && calls==2);
 packet[7]='U';packet[12]=0;
 assert(txControl(packet,15)==1 && calls==2 && TX_ANT==0 && RX_ANT==1);
 packet[12]=24;packet[8]=101;assert(txControl(packet,15)==1 && calls==2);
 packet[8]=2;packet[9]=51;assert(txControl(packet,15)==1 && calls==2);
 packet[9]=0;assert(txControl(packet,14)==1 && calls==2);
 packet[1]='P';assert(txControl(packet,8)==2 && calls==2);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);(path/'test.c').write_text(harness)
            result=subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror',str(path/'test.c'),'-o',str(path/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            subprocess.run([str(path/'test')],check=True,capture_output=True)

class RadioProviderTests(unittest.TestCase):
    def setUp(self):
        from controller.core import Store
        from controller.radio import RadioProvider
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'private/db')
        self.provider=RadioProvider(self.store)

    @patch('controller.radio.RFClient')
    def test_disabled_gate_never_opens_radio(self,client):
        self.store.set('rf_authorized',True)
        self.assertEqual(self.provider(device(),1,0,1)[0],'blocked')
        client.assert_not_called()

    @patch('controller.radio.RFClient')
    def test_probe_failure_does_not_send(self,client):
        self.store.set('rf_authorized',True);self.store.set('rf_enabled',True)
        client.return_value.probe.side_effect=OSError()
        self.assertEqual(self.provider(device(),1,0,1)[0],'offline')
        client.return_value.send.assert_not_called()

    @patch('controller.radio.RFClient')
    def test_missing_transmit_ack_is_unknown_not_retryable_offline(self,client):
        self.store.set('rf_authorized',True);self.store.set('rf_enabled',True)
        client.return_value.send.side_effect=RFUncertainError()
        self.assertEqual(self.provider(device(),1,0,1)[0],'unknown')
        client.return_value.send.assert_called_once()

    @patch('controller.radio.RFClient')
    def test_acknowledged_command_is_sent_not_receiver_confirmed(self,client):
        self.store.set('rf_authorized',True);self.store.set('rf_enabled',True)
        status,message=self.provider(device(),1,0,1)
        self.assertEqual(status,'sent')
        self.assertIn('unconfirmed',message)
