"""Tiny client for Apple's usbmux service (installed with iTunes).

usbmux tunnels a TCP connection over the USB cable to a port on the iPhone/iPad,
so the app's normal network listener also works over the cable.
"""
import plistlib
import socket
import struct

USBMUXD = ("127.0.0.1", 27015)


class NoDevice(ConnectionError):
    pass


def _recv_exact(sock, n):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("usbmux closed the connection")
        data += chunk
    return data


def _request(sock, message):
    body = plistlib.dumps({**message, "ClientVersionString": "screenmirror", "ProgName": "screenmirror"})
    # header: total length, version 1, type 8 (plist), tag
    sock.sendall(struct.pack("<IIII", 16 + len(body), 1, 8, 1) + body)
    length = struct.unpack("<I", _recv_exact(sock, 16)[:4])[0]
    return plistlib.loads(_recv_exact(sock, length - 16))


def usb_devices():
    """Devices plugged in by cable (usbmux also lists Wi-Fi-synced ones; skip those)."""
    try:
        with socket.create_connection(USBMUXD, timeout=3) as sock:
            reply = _request(sock, {"MessageType": "ListDevices"})
    except OSError as e:
        raise NoDevice("Apple Mobile Device Service isn't running - install iTunes") from e
    return [d for d in reply.get("DeviceList", []) if d["Properties"].get("ConnectionType") == "USB"]


def connect(port, device_index=0):
    devices = usb_devices()
    if not devices:
        raise NoDevice("no iPhone/iPad on the cable")
    device = devices[min(device_index, len(devices) - 1)]
    sock = socket.create_connection(USBMUXD, timeout=5)
    reply = _request(sock, {"MessageType": "Connect", "DeviceID": device["DeviceID"],
                            "PortNumber": socket.htons(port)})
    if reply.get("Number") != 0:
        sock.close()
        raise ConnectionRefusedError("device found on the cable, but ScreenMirror isn't open on it")
    return sock  # from here on it's a raw TCP stream to the app
