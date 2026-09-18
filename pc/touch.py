"""Replays the phone's fingers as real Windows touch input.

Windows then handles the gestures itself: tap = click, drag, swipe to scroll,
pinch to zoom, long-press = right-click.
"""
import ctypes
import threading
import time
from ctypes import wintypes

user32 = ctypes.windll.user32

PT_TOUCH = 2
INRANGE, INCONTACT, DOWN, UPDATE, UP = 0x2, 0x4, 0x10000, 0x20000, 0x40000
PHASE_DOWN, PHASE_MOVE, PHASE_UP = 0, 1, 2
HOLD_REFRESH = 0.05  # Windows drops a contact that goes quiet, so re-send held fingers


class POINTER_INFO(ctypes.Structure):
    _fields_ = [("pointerType", ctypes.c_uint32), ("pointerId", ctypes.c_uint32),
                ("frameId", ctypes.c_uint32), ("pointerFlags", ctypes.c_uint32),
                ("sourceDevice", wintypes.HANDLE), ("hwndTarget", wintypes.HWND),
                ("ptPixelLocation", wintypes.POINT), ("ptHimetricLocation", wintypes.POINT),
                ("ptPixelLocationRaw", wintypes.POINT), ("ptHimetricLocationRaw", wintypes.POINT),
                ("dwTime", wintypes.DWORD), ("historyCount", ctypes.c_uint32),
                ("InputData", ctypes.c_int32), ("dwKeyStates", wintypes.DWORD),
                ("PerformanceCount", ctypes.c_uint64), ("ButtonChangeType", ctypes.c_int)]


class POINTER_TOUCH_INFO(ctypes.Structure):
    _fields_ = [("pointerInfo", POINTER_INFO), ("touchFlags", ctypes.c_uint32),
                ("touchMask", ctypes.c_uint32), ("rcContact", wintypes.RECT),
                ("rcContactRaw", wintypes.RECT), ("orientation", ctypes.c_uint32),
                ("pressure", ctypes.c_uint32)]


_initialized = False


class Touch:
    def __init__(self, rect):
        global _initialized
        if not _initialized:  # allowed once per process
            if not user32.InitializeTouchInjection(10, 1):  # 10 fingers, show touch dots
                raise ctypes.WinError()
            _initialized = True
        self.rect = rect
        self.contacts = {}  # finger id -> (x, y) in desktop pixels
        self.last_inject = 0.0
        self.lock = threading.Lock()
        self.running = True
        threading.Thread(target=self._hold, daemon=True).start()

    def handle(self, phase, finger, nx, ny):
        """nx, ny: 0-1 across the picture shown on the phone."""
        left, top, right, bottom = self.rect
        pos = (left + round(nx * (right - left - 1)), top + round(ny * (bottom - top - 1)))
        with self.lock:
            flags = {f: UPDATE | INRANGE | INCONTACT for f in self.contacts}
            if phase == PHASE_DOWN:
                if finger in self.contacts:  # missed an "up"; lift it first
                    self._inject({finger: UP})
                    flags.pop(finger)
                self.contacts[finger] = pos
                flags[finger] = DOWN | INRANGE | INCONTACT
            elif finger not in self.contacts:
                return
            elif phase == PHASE_MOVE:
                self.contacts[finger] = pos
            else:
                flags[finger] = UP
            self._inject(flags)
            if phase == PHASE_UP:
                del self.contacts[finger]

    def release_all(self):
        with self.lock:
            if self.contacts:
                self._inject({f: UP for f in self.contacts})
                self.contacts.clear()
            self.running = False

    def _hold(self):
        while self.running:
            time.sleep(HOLD_REFRESH)
            with self.lock:
                if self.contacts and time.time() - self.last_inject >= HOLD_REFRESH:
                    self._inject({f: UPDATE | INRANGE | INCONTACT for f in self.contacts})

    def _inject(self, flags):
        infos = (POINTER_TOUCH_INFO * len(flags))()
        for info, (finger, flag) in zip(infos, flags.items()):
            x, y = self.contacts[finger]
            info.pointerInfo.pointerType = PT_TOUCH
            info.pointerInfo.pointerId = finger
            info.pointerInfo.pointerFlags = flag
            info.pointerInfo.ptPixelLocation = wintypes.POINT(x, y)
        user32.InjectTouchInput(len(flags), infos)
        self.last_inject = time.time()
