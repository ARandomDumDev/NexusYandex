#!/usr/bin/env python3
"""Run this ON the Station (same place your working script ran).

Listens for UDP from the PC app:
  port 8388 -> LED frames (89 pixels * 4 bytes = 356 bytes) -> /dev/fb0
  port 8188 -> raw audio (s16le, mono, 44100 Hz)            -> aplay
"""
import os
import socket
import subprocess
import threading

FRAME_PORT = 8388
AUDIO_PORT = 8188
FRAME_SIZE = 89 * 4  # 356 bytes, same as the working code

print("настраиваем LED")
fd = os.open("/dev/fb0", os.O_WRONLY)


def frame_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", FRAME_PORT))
    n = 0
    while True:
        data, _ = sock.recvfrom(4096)
        if len(data) != FRAME_SIZE:
            continue
        os.pwrite(fd, data, 0)  # same call as the working code
        n += 1
        if n % 30 == 0:
            print("кадр", n)


def audio_loop():
    print("включаем звук")
    sound = subprocess.Popen(
        ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-r", "44100",
         "-c", "1", "-B", "100000", "-"],
        stdin=subprocess.PIPE,
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", AUDIO_PORT))
    while True:
        data, _ = sock.recvfrom(4096)
        try:
            sound.stdin.write(data)
            sound.stdin.flush()
        except (BrokenPipeError, OSError):
            break


threading.Thread(target=audio_loop, daemon=True).start()
print(f"слушаем: кадры UDP {FRAME_PORT}, звук UDP {AUDIO_PORT}")
frame_loop()
