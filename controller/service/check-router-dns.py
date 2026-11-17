#!/usr/bin/env python3
"""Read IPv6 router-advertised DNS; changes no network settings."""
import ipaddress
import socket
import struct
import sys
import time


def main():
    interface = sys.argv[1] if len(sys.argv) > 1 else "enp3s0"
    index = socket.if_nametoindex(interface)
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_RAW, socket.IPPROTO_ICMPV6)
    except PermissionError:
        sys.exit("Run with sudo: reading router advertisements requires a raw socket.")
    with sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode() + b"\0")
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, index)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, 255)
        sock.sendto(struct.pack("!BBHI", 133, 0, 0, 0), ("ff02::2", 0, 0, index))
        deadline = time.monotonic() + 10
        seen = False
        while time.monotonic() < deadline:
            sock.settimeout(max(0.01, deadline - time.monotonic()))
            try:
                packet, peer = sock.recvfrom(65535)
            except socket.timeout:
                break
            if len(packet) < 16 or packet[0:2] != b"\x86\x00":
                continue
            seen = True
            print("Router advertisement from", peer[0])
            offset = 16
            found = False
            while offset + 2 <= len(packet):
                kind, units = packet[offset:offset + 2]
                length = units * 8
                if length < 8 or offset + length > len(packet):
                    break
                if kind == 25 and length >= 24 and (length - 8) % 16 == 0:
                    lifetime = struct.unpack_from("!I", packet, offset + 4)[0]
                    for start in range(offset + 8, offset + length, 16):
                        print("Advertised DNS:", ipaddress.IPv6Address(packet[start:start + 16]),
                              "lifetime:", lifetime)
                        found = True
                offset += length
            if not found:
                print("No recursive DNS option in this advertisement.")
        if not seen:
            print("No router advertisement received within 10 seconds; inconclusive.")


if __name__ == "__main__":
    main()
