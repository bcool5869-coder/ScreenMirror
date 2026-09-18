# ScreenMirror

Show a Windows PC's screen on an iPhone or iPad, over a USB cable or Wi-Fi. No Mac needed.

- `ios/` is the iPhone/iPad app, built into an unsigned `.ipa` by GitHub Actions.
- `pc/` is the Windows sender (Python).

## Install the app

1. Open the **Actions** tab, then the latest **Build ScreenMirror IPA** run, and download `ScreenMirror-IPA`.
2. Unzip it and install `ScreenMirror.ipa` with [Sideloadly](https://sideloadly.io/).
3. Open the app. On first launch, allow **Local Network** access (needed for Wi-Fi).

## Run the sender

Needs Python 3 and a couple of packages:

```
pip install pillow zeroconf
```

For the cable, install **iTunes from apple.com**. It provides the Apple Mobile Device Service that
carries the connection over USB.

```
python pc/sender.py              # cable if plugged in, otherwise Wi-Fi
python pc/sender.py --wifi       # Wi-Fi only
python pc/sender.py --host <IP>  # the address shown in the app
python pc/sender.py --list       # list monitors
python pc/sender.py --monitor 2  # send a different monitor
```

Lower `--quality` or `--max-width` if Wi-Fi is laggy.

## Touch

Fingers on the phone become real Windows touch input on the monitor being sent: tap to click,
drag, swipe to scroll, pinch to zoom, long-press to right-click.

## How it works

The app listens on TCP port 7700. The sender captures the monitor, encodes each frame as JPEG and
sends it with a 4-byte length prefix. The app answers each frame it shows with one byte, and the
sender keeps at most two frames in flight, so a slow link drops frames instead of building up lag.
Finger events travel back on the same connection.
Over the cable, the connection goes through Apple's usbmux service to the same port.

## Limits

- This **mirrors** an existing monitor. To use the device as an extra monitor, install a virtual
  display driver and send that monitor with `--monitor`.
- The app must stay open in the foreground.
