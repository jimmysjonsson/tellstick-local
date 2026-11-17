"""Bounded RF pulse encoding and acknowledged X-TX1 transport.

Protocol facts/timings follow Telldus ProtocolNexa/ProtocolComen at commit
2598bbed16ffd701f2a07c99582f057a3decbaf3 (LGPL-2.1 reference).
No learn, bell, group-bit broadcast, or arbitrary raw-command API is exposed.
"""
from dataclasses import dataclass
import ipaddress
import secrets
import socket
import struct
import time


@dataclass(frozen=True, slots=True)
class Waveform:
    pulses: tuple[int,...]  # Alternating HIGH/LOW durations, units of 10 us.
    gap_ms: int = 11
    frames: int = 10


class RFError(ValueError):pass
class RFUncertainError(OSError):pass


def number(value,minimum,maximum):
    try:result=int(str(value))
    except (ValueError,TypeError):raise RFError('Invalid RF parameter') from None
    if not minimum<=result<=maximum:raise RFError('RF parameter outside protocol range')
    return result


def waveform(device,method,value=0,repeats=1):
    method=number(method,1,16);value=number(value,0,255);repeats=number(repeats,1,10)
    if method not in (1,2,16):raise RFError('Unsupported RF method')
    protocol=device.get('protocol')
    model=str(device.get('model') or '').split(':')[0]
    parameters={p['name']:p['value'] for p in device.get('parameter',[])}
    unit=number(parameters.get('unit'),1,16)-1
    if protocol=='arctech' and model=='codeswitch':
        house=str(parameters.get('house','')).upper()
        if len(house)!=1 or not 'A'<=house<='P' or method==16:raise RFError('Invalid code-switch action or house')
        def tuple_code(code):return ''.join('$kk$' if code>>bit&1 else '$k$k' for bit in range(4))
        end='$k$k$kk$$kk$$kk$$k' if method==1 else '$k$k$kk$$kk$$k$k$k'
        return Waveform(tuple(ord(c) for c in tuple_code(ord(house)-65)+tuple_code(unit)+end),frames=10*repeats)
    if protocol not in ('arctech','comen') or model not in ('selflearning-switch','selflearning-dimmer'):
        raise RFError('Unsupported device protocol/model')
    if protocol=='comen':
        if model!='selflearning-switch' or method==16:raise RFError('Comen device does not support dimming')
        house=(number(parameters.get('house'),1,16777215)<<2)|2
    else:house=number(parameters.get('house'),1,67108863)
    # A dimmer's ON is full-level DIM, matching Telldus's dim-mode workaround.
    if method==1 and model=='selflearning-dimmer':method=16;value=255
    if method==16 and model!='selflearning-dimmer':raise RFError('Switch does not support dimming')
    bits=[(house>>i)&1 for i in range(25,-1,-1)]+[0]
    bits+=[None if method==16 else int(method==1)]
    bits += [(unit>>i)&1 for i in range(3,-1,-1)]
    if method==16:bits += [((value//16)>>i)&1 for i in range(3,-1,-1)]
    pulses=[24,255]
    for bit in bits:
        pulses.extend((24,24,24,24) if bit is None else (24,127,24,24) if bit else (24,24,24,127))
    pulses.extend((24,) if method==16 else (24,24))
    return Waveform(tuple(pulses),frames=10*repeats)


def encode_request(wave,nonce):
    if len(nonce)!=4 or not 1<=len(wave.pulses)<=160:raise RFError('Invalid RF request')
    if not 1<=wave.frames<=100 or not 0<=wave.gap_ms<=50:raise RFError('Invalid RF repeat settings')
    if any(type(t) is not int or not 1<=t<=600 for t in wave.pulses) or sum(wave.pulses)>12000:
        raise RFError('Invalid RF pulse durations')
    return b'TX1\0'+nonce+bytes((wave.frames,wave.gap_ms,len(wave.pulses)))+struct.pack('!'+str(len(wave.pulses))+'H',*wave.pulses)


class RFClient:
    def __init__(self,target='192.168.1.193',*,bind_address='192.168.1.149'):
        self.target=str(ipaddress.IPv4Address(target));self.bind=str(ipaddress.IPv4Address(bind_address))
        address=ipaddress.IPv4Address(self.target)
        if address.is_multicast or address.is_unspecified or int(address)==0xFFFFFFFF:raise ValueError('Unicast RF target required')

    def _exchange(self,packet,nonce,expected_status,timeout):
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.bind((self.bind,0));sock.settimeout(timeout)
            # Deliberately send once. Missing final ACK is uncertain, not a reason
            # to repeat a physical action under a new request identity.
            sock.sendto(packet,(self.target,42314))
            deadline=time.monotonic()+timeout
            try:
                while True:
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise socket.timeout()
                    sock.settimeout(remaining)
                    reply,peer=sock.recvfrom(2048)
                    if peer!=(self.target,42314):continue
                    if len(reply)!=9 or reply[:4]!=b'TA1\0' or reply[4:8]!=nonce:continue
                    if reply[8]!=expected_status:raise RFError('Firmware rejected RF request')
                    return
            except socket.timeout:
                raise RFUncertainError('No matching firmware acknowledgment') from None

    def probe(self):
        nonce=secrets.token_bytes(4)
        self._exchange(b'TP1\0'+nonce,nonce,2,2)

    def send(self,device,method,value=0,repeats=1):
        wave=waveform(device,method,value,repeats)
        nonce=secrets.token_bytes(4)
        self._exchange(encode_request(wave,nonce),nonce,0,25)
