"""IPv4 WS-Discovery helpers for finding ONVIF devices on local networks."""
import select
import socket
import struct
import time
import uuid
import xml.etree.ElementTree as ET


DISCOVERY_ADDRESS = ("239.255.255.250", 3702)
PROBE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
 xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
 xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
 xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
 <e:Header><w:MessageID>urn:uuid:{message_id}</w:MessageID>
  <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
  <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
 </e:Header><e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body>
</e:Envelope>"""


def _local_ipv4_interfaces():
    """Return active non-loopback IPv4 interfaces supported by this Linux app."""
    try:
        import fcntl
    except ImportError:
        return []

    interfaces = []
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for _index, name in socket.if_nameindex():
            request = struct.pack("256s", name.encode("ascii")[:15])
            try:
                flags = struct.unpack("H", fcntl.ioctl(probe.fileno(), 0x8913, request)[16:18])[0]
                if not flags & 0x1:  # IFF_UP
                    continue
                address = socket.inet_ntoa(fcntl.ioctl(probe.fileno(), 0x8915, request)[20:24])
            except OSError:
                continue
            if not address.startswith("127."):
                interfaces.append((name, address))
    finally:
        probe.close()
    return interfaces


def _local_name(element, name):
    for child in element.iter():
        if child.tag.rsplit("}", 1)[-1] == name:
            return (child.text or "").strip()
    return ""


def parse_probe_match(payload, source_ip, interface):
    """Parse one WS-Discovery response into a stable, UI-friendly dictionary."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return None

    endpoint_reference = next(
        (element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "EndpointReference"),
        None,
    )
    endpoint = _local_name(endpoint_reference, "Address") if endpoint_reference is not None else ""
    xaddrs = _local_name(root, "XAddrs").split()
    scopes = _local_name(root, "Scopes").split()
    if not xaddrs:
        return None
    return {
        "endpoint_id": endpoint,
        "xaddrs": xaddrs,
        "scopes": scopes,
        "source_ip": source_ip,
        "interface": interface,
    }


def discover(timeout=4.0, rounds=2):
    """Discover ONVIF cameras by sending WS-Discovery probes on active NICs."""
    interfaces = _local_ipv4_interfaces()
    if not interfaces:
        # A fallback still permits discovery on non-Linux test/runtime platforms.
        interfaces = [("default", "0.0.0.0")]

    sockets = []
    errors = []
    for interface, address in interfaces:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(address))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.bind((address, 0))
            sockets.append((sock, interface))
        except OSError as exc:
            errors.append(f"{interface}: {exc}")
            sock.close()

    if not sockets:
        raise OSError("Could not open a discovery socket" + (f": {'; '.join(errors)}" if errors else ""))

    probe = PROBE_TEMPLATE.format(message_id=f"uuid:{uuid.uuid4()}").encode("utf-8")
    found = {}
    deadline = time.monotonic() + max(0.5, float(timeout))
    try:
        for _ in range(max(1, int(rounds))):
            for sock, _interface in sockets:
                try:
                    sock.sendto(probe, DISCOVERY_ADDRESS)
                except OSError as exc:
                    errors.append(str(exc))

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            ready, _, _ = select.select([sock for sock, _ in sockets], [], [], remaining)
            if not ready:
                break
            for sock in ready:
                interface = next(name for current, name in sockets if current is sock)
                try:
                    payload, peer = sock.recvfrom(65535)
                except OSError:
                    continue
                device = parse_probe_match(payload, peer[0], interface)
                if not device:
                    continue
                key = device["endpoint_id"] or " ".join(device["xaddrs"])
                if key not in found:
                    found[key] = device
                else:
                    existing = found[key]
                    for xaddr in device["xaddrs"]:
                        if xaddr not in existing["xaddrs"]:
                            existing["xaddrs"].append(xaddr)
    finally:
        for sock, _interface in sockets:
            sock.close()
    return sorted(found.values(), key=lambda device: (device["source_ip"], device["endpoint_id"]))
