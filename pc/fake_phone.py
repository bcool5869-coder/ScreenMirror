"""Stand-in for the iOS app, for testing sender.py without a phone.

    python fake_phone.py            then:  python sender.py --host 127.0.0.1
    python fake_phone.py --tap      also taps the middle of the sent monitor once
Saves the latest frame to last_frame.jpg.
"""
import json
import socket
import struct
import sys
import time

W, H = 2532, 1170  # an iPhone's screen in landscape pixels


def recv_exact(conn, n):
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError
        data += chunk
    return data


with socket.create_server(("127.0.0.1", 7700)) as server:
    print("fake phone listening on 7700")
    while True:
        conn, _ = server.accept()
        conn.sendall(json.dumps({"w": W, "h": H}).encode() + b"\n")
        frames, total, t0 = 0, 0, time.time()
        try:
            while True:
                jpeg = recv_exact(conn, struct.unpack(">I", recv_exact(conn, 4))[0])
                conn.sendall(b"\x01")
                total += 1
                if "--tap" in sys.argv and total == 10:
                    for phase in (0, 2):  # finger down, finger up
                        conn.sendall(struct.pack(">BBBff", 2, phase, 0, 0.5, 0.5))
                        time.sleep(0.05)
                    print("tapped the middle")
                frames += 1
                if time.time() - t0 >= 2:
                    open("last_frame.jpg", "wb").write(jpeg)
                    print(f"received {frames / (time.time() - t0):.1f} fps")
                    frames, t0 = 0, time.time()
        except ConnectionError:
            print("sender disconnected")
