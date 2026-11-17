"""Local TellStick discovery, reachability and receive-only event monitoring."""
import argparse
import json
import sys
from dataclasses import asdict
from .discovery import TellStickClient
from .listener import TellStickListener
import math


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("discover", "status", "monitor"))
    parser.add_argument("--target", default="192.168.1.193", help="IPv4 address; use 255.255.255.255 for broadcast discovery")
    parser.add_argument("--bind", default="0.0.0.0", help="Local IPv4 address (e.g. 192.168.1.149)")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--duration", type=float, default=60, help="Monitor duration in seconds (default 60)")
    args = parser.parse_args()
    if args.command == "monitor":
        if not math.isfinite(args.duration) or args.duration <= 0:
            parser.error("--duration must be finite and positive")
        try:
            with TellStickListener(args.target, bind_address=args.bind, timeout=args.timeout) as listener:
                if not args.json:
                    print("Listening for received events (X-RX1/X-TX1). No RF transmit commands are sent.", flush=True)
                for event in listener.events(duration=args.duration):
                    if args.json:
                        print(json.dumps(asdict(event)), flush=True)
                    else:
                        print(f"{event.received_at} {event.kind} " + json.dumps(event.fields), flush=True)
                print(f"Received {listener.received}; ignored {listener.malformed} malformed and {listener.unexpected_sender} unexpected-source packets.", file=sys.stderr)
        except KeyboardInterrupt:
            return 130
        except (OSError, ValueError):
            print("Monitor failed: verify X-RX1/X-TX1 firmware, addresses and UDP access.", file=sys.stderr)
            return 2
        return 0
    try:
        devices = TellStickClient(args.target, bind_address=args.bind, timeout=args.timeout).discover()
    except (OSError, ValueError):
        print("Discovery failed: check addresses, timeout, and UDP network access.", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([asdict(device) for device in devices]))
    elif devices:
        for device in devices:
            print(f"Reachable: {device.ip} MAC {device.mac} firmware {device.firmware_version}")
    else:
        print("No discovery response received; device status is unknown.")
    return 0 if devices else 1


if __name__ == "__main__":
    raise SystemExit(main())
