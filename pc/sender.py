"""Stream a Windows monitor to the ScreenMirror app on an iPhone or iPad.

    python sender.py                   cable if one is plugged in, otherwise Wi-Fi
    python sender.py --usb             cable only
    python sender.py --wifi            Wi-Fi only (finds the app automatically)
    python sender.py --host 172.20.10.1
    python sender.py --list            show monitors
    python sender.py --monitor 2
"""
import argparse
import ctypes
import io
import json
import socket
import struct
import time
from ctypes import wintypes

from PIL import Image, ImageDraw, ImageGrab

import usbmux

PORT = 7700
SERVICE = "_screenmirror._tcp.local."
MAX_IN_FLIGHT = 2  # frames sent but not yet shown; keeps lag low when the link is slow

user32 = ctypes.windll.user32
ctypes.windll.shcore.SetProcessDpiAwareness(2)  # real pixels, not scaled ones


def monitors():
    """Monitor rectangles in desktop coordinates, primary first."""
    rects = []
    proc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                              ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def callback(_monitor, _hdc, rect, _data):
        r = rect.contents
        rects.append((r.left, r.top, r.right, r.bottom))
        return 1

    user32.EnumDisplayMonitors(None, None, proc(callback), 0)
    return sorted(rects, key=lambda r: (r[0], r[1]) != (0, 0))


def fit(rect, width, height):
    """Largest size with the monitor's shape that fits in width x height."""
    mw, mh = rect[2] - rect[0], rect[3] - rect[1]
    scale = min(width / mw, height / mh, 1)
    return round(mw * scale), round(mh * scale)


def grab(rect, size, quality):
    img = ImageGrab.grab(bbox=rect, all_screens=True)
    if img.size != size:
        img = img.resize(size, Image.BILINEAR)
    # screen grabs don't include the mouse pointer, so draw one
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    if rect[0] <= pt.x < rect[2] and rect[1] <= pt.y < rect[3]:
        s = size[0] / (rect[2] - rect[0])
        x, y = (pt.x - rect[0]) * s, (pt.y - rect[1]) * s
        k = max(1.0, size[0] / 1280)
        ImageDraw.Draw(img).polygon(
            [(x, y), (x, y + 17 * k), (x + 4.5 * k, y + 12.5 * k), (x + 12 * k, y + 12 * k)],
            fill="white", outline="black")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def discover(timeout=5):
    """Find the app on the local network over Bonjour."""
    from zeroconf import IPVersion, ServiceBrowser, Zeroconf

    zc = Zeroconf()
    found = []

    class Listener:
        def add_service(self, zc, type_, name):
            info = zc.get_service_info(type_, name, timeout=2000)
            if info and info.parsed_addresses(IPVersion.V4Only):
                found.append(info.parsed_addresses(IPVersion.V4Only)[0])

        def update_service(self, *_):
            pass

        def remove_service(self, *_):
            pass

    ServiceBrowser(zc, SERVICE, Listener())
    deadline = time.time() + timeout
    while not found and time.time() < deadline:
        time.sleep(0.1)
    zc.close()
    if not found:
        raise ConnectionError("ScreenMirror not found on Wi-Fi - is the app open, on the same network?")
    return found[0]


def connect(args):
    if not args.wifi and not args.host:
        try:
            return usbmux.connect(PORT, args.device), "cable"
        except usbmux.NoDevice:
            if args.usb:
                raise
    host = args.host or discover()
    return socket.create_connection((host, PORT), timeout=5), f"Wi-Fi {host}"


def recv_line(sock):
    line = b""
    while not line.endswith(b"\n"):
        chunk = sock.recv(1)
        if not chunk:
            raise ConnectionError("app closed the connection")
        line += chunk
    return line


def stream(sock, rect, args):
    sock.settimeout(5)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    hello = json.loads(recv_line(sock))
    size = fit(rect, min(hello["w"], args.max_width), hello["h"])
    print(f"  screen {hello['w']}x{hello['h']}, sending {size[0]}x{size[1]}")

    in_flight, frames, sent, t0 = 0, 0, 0, time.time()
    while True:
        start = time.perf_counter()
        jpeg = grab(rect, size, args.quality)
        sock.sendall(struct.pack(">I", len(jpeg)) + jpeg)
        in_flight += 1
        while in_flight >= MAX_IN_FLIGHT:
            acks = sock.recv(64)
            if not acks:
                raise ConnectionError("app closed the connection")
            in_flight -= len(acks)

        frames += 1
        sent += len(jpeg)
        if time.time() - t0 >= 2:
            dt = time.time() - t0
            print(f"  {frames / dt:4.1f} fps  {sent / frames / 1024:5.0f} KB/frame  {sent / dt / 1e6:4.1f} MB/s", end="\r")
            frames, sent, t0 = 0, 0, time.time()
        time.sleep(max(0, 1 / args.fps - (time.perf_counter() - start)))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    link = p.add_mutually_exclusive_group()
    link.add_argument("--usb", action="store_true", help="cable only")
    link.add_argument("--wifi", action="store_true", help="Wi-Fi only")
    link.add_argument("--host", help="phone/tablet IP (shown in the app)")
    p.add_argument("--device", type=int, default=0, help="which cabled device, if several (0 = first)")
    p.add_argument("--monitor", type=int, default=1, help="monitor to send (1 = primary)")
    p.add_argument("--list", action="store_true", help="list monitors and exit")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--quality", type=int, default=70, help="JPEG quality 1-95")
    p.add_argument("--max-width", type=int, default=1920, help="cap the width sent (big iPads are slow at full size)")
    args = p.parse_args()

    screens = monitors()
    if args.list:
        for i, r in enumerate(screens, 1):
            print(f"{i}: {r[2] - r[0]}x{r[3] - r[1]} at ({r[0]}, {r[1]})" + ("  primary" if i == 1 else ""))
        return
    rect = screens[args.monitor - 1]

    while True:
        try:
            sock, how = connect(args)
            print(f"Connected by {how}")
            with sock:
                stream(sock, rect, args)
        except KeyboardInterrupt:
            return
        except OSError as e:  # includes timeouts and usbmux errors
            print(f"\nNot connected: {e}. Retrying...")
            time.sleep(2)


if __name__ == "__main__":
    main()
