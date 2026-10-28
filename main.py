
#!/usr/bin/env python3

from __future__ import annotations

import platform
import queue
import socket
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from urllib.parse import urlparse

try:
    import cv2
    import numpy as np
    from playwright.sync_api import sync_playwright
except ImportError as exc:
    raise SystemExit(
        "Missing packages. Install these first:\n"
        "python -m pip install playwright opencv-python numpy soundcard\n"
        "python -m playwright install chromium\n"
        "Linux: python3 -m pip install --user playwright opencv-python numpy"
    ) from exc


# Keep the pixel order from the original repo or the LEDs will look wrong.
# The Station side expects 89 pixels per frame (356 bytes total).
PIXELS = [
    1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31, 33, 35,
    37, 39, 41, 43, 45, 47, 49, 51, 53, 55, 57, 59, 61, 63, 65, 67, 69,
    71, 73, 75, 77, 87, 89, 91, 103, 105, 107, 117, 119, 121, 123, 125,
    127, 129, 131, 133, 135, 137, 139, 141, 143, 145, 147, 149, 151, 153,
    155, 157, 159, 161, 163, 165, 167, 169, 171, 173, 175, 177, 179, 181,
    183, 185, 187, 189, 191, 193, 112, 110, 81, 83,
]


class StationControl:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Station Control")
        self.root.geometry("560x610")
        self.root.minsize(500, 570)
        self.root.configure(bg="#edf0f3")

        self.commands: queue.Queue = queue.Queue()
        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.audio_process: subprocess.Popen | None = None
        self.audio_thread: threading.Thread | None = None
        self.audio_stop = threading.Event()
        self.audio_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.frame_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.playing = False
        self.duration = 0.0
        self.position = 0.0
        self.seeking = False
        self._build_ui()
        self.root.after(100, self._poll_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background="#edf0f3")
        style.configure(
            "TLabel",
            background="#edf0f3",
            foreground="#202a35",
            font=("TkDefaultFont", 10),
        )
        style.configure(
            "Title.TLabel",
            font=("TkDefaultFont", 19, "bold"),
            foreground="#17212b",
        )
        style.configure("Muted.TLabel", foreground="#667382")
        style.configure(
            "TButton",
            padding=(12, 7),
            font=("TkDefaultFont", 10),
        )
        style.configure(
            "Primary.TButton",
            padding=(14, 9),
            font=("TkDefaultFont", 10, "bold"),
        )
        style.configure(
            "TLabelframe",
            background="#edf0f3",
            bordercolor="#cbd2da",
        )
        style.configure(
            "TLabelframe.Label",
            background="#edf0f3",
            foreground="#344252",
            font=("TkDefaultFont", 10, "bold"),
        )
        style.configure("TEntry", padding=8)
        style.configure("Horizontal.TScale", background="#edf0f3")

        outer = ttk.Frame(self.root, padding=22)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 20))
        ttk.Label(
            header,
            text="Station Control",
            style="Title.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            header,
            text="A small desktop controller for Yandex Station 2",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        device = ttk.LabelFrame(outer, text="  DEVICE  ", padding=14)
        device.pack(fill="x", pady=(0, 14))
        ttk.Label(device, text="Station IP address").grid(
            row=0, column=0, sticky="w"
        )
        self.ip_var = tk.StringVar(value="192.168.50.100")
        ttk.Entry(
            device,
            textvariable=self.ip_var,
            width=22,
        ).grid(row=0, column=1, sticky="ew", padx=(12, 0))
        device.columnconfigure(1, weight=1)

        self.status_var = tk.StringVar(value="●  Not connected")
        self.status_label = ttk.Label(
            device,
            textvariable=self.status_var,
            style="Muted.TLabel",
        )
        self.status_label.grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )

        source = ttk.LabelFrame(outer, text="  SOURCE  ", padding=14)
        source.pack(fill="x", pady=(0, 14))
        self.url_var = tk.StringVar(value="https://nexusnet.party")
        ttk.Label(source, text="Webpage URL").pack(anchor="w")

        url_row = ttk.Frame(source)
        url_row.pack(fill="x", pady=(6, 0))
        self.url_entry = ttk.Entry(url_row, textvariable=self.url_var)
        self.url_entry.pack(side="left", fill="x", expand=True)
        self.load_button = ttk.Button(
            url_row, text="Load", command=self.load_url
        )
        self.load_button.pack(side="left", padx=(8, 0))

        playback = ttk.LabelFrame(outer, text="  PLAYBACK  ", padding=14)
        playback.pack(fill="x", pady=(0, 14))
        buttons = ttk.Frame(playback)
        buttons.pack(fill="x")

        self.play_button = ttk.Button(
            buttons,
            text="▶  Play",
            style="Primary.TButton",
            command=self.toggle_play,
        )
        self.play_button.pack(side="left")
        ttk.Button(
            buttons, text="Restart", command=self.restart
        ).pack(side="left", padx=(8, 0))

        self.show_browser_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            buttons,
            text="Show browser",
            variable=self.show_browser_var,
            command=self.set_browser_visibility,
        ).pack(side="right")

        seek_row = ttk.Frame(playback)
        seek_row.pack(fill="x", pady=(14, 0))
        self.time_var = tk.StringVar(value="0:00  /  --:--")
        ttk.Label(
            seek_row,
            textvariable=self.time_var,
            style="Muted.TLabel",
        ).pack(anchor="w")

        self.seek_var = tk.DoubleVar(value=0)
        self.seek = ttk.Scale(
            playback,
            from_=0,
            to=100,
            variable=self.seek_var,
            command=self._seek_changed,
        )
        self.seek.pack(fill="x", pady=(5, 0))
        self.seek.bind(
            "<ButtonPress-1>",
            lambda _e: setattr(self, "seeking", True),
        )
        self.seek.bind("<ButtonRelease-1>", self._seek_released)

        audio = ttk.LabelFrame(outer, text="  AUDIO  ", padding=14)
        audio.pack(fill="x", pady=(0, 14))
        self.audio_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            audio,
            text="Send computer audio to the Station",
            variable=self.audio_var,
            command=self.toggle_audio,
        ).pack(anchor="w")
        ttk.Label(
            audio,
            text=(
                "Grabs audio from the selected desktop output, so "
                "other PC sounds may come through too."
            ),
            style="Muted.TLabel",
            wraplength=470,
        ).pack(anchor="w", pady=(5, 0))

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(2, 0))
        self.message_var = tk.StringVar(
            value="Ready. Put in the Station IP, then load a page."
        )
        ttk.Label(
            footer,
            textvariable=self.message_var,
            style="Muted.TLabel",
            wraplength=480,
        ).pack(anchor="w")
        ttk.Button(
            footer, text="Quit", command=self.close
        ).pack(anchor="e", pady=(10, 0))

    def _valid_ip(self):
        ip = self.ip_var.get().strip()
        try:
            socket.inet_aton(ip)
        except OSError:
            messagebox.showerror(
                "Invalid address",
                "Enter the Station's IPv4 address, for example 192.168.50.42.",
            )
            return None
        return ip

    def _start_worker(self, url: str):
        ip = self._valid_ip()
        if not ip:
            return

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            messagebox.showerror(
                "Invalid URL",
                "Enter a complete http:// or https:// URL.",
            )
            return

        self.stop_event.set()
        self.commands.put(("stop", None))
        self.stop_event = threading.Event()
        self.commands.put(
            ("load", (url, ip, self.show_browser_var.get(), self.stop_event))
        )

        if not self.worker or not self.worker.is_alive():
            self.worker = threading.Thread(
                target=self._browser_worker,
                daemon=True,
            )
            self.worker.start()

        self.status_var.set("●  Starting browser…")
        self.message_var.set("Loading webpage in Chromium.")

    def load_url(self):
        self._start_worker(self.url_var.get().strip())

    def _browser_worker(self):
        browser = None
        page = None
        active_stop = None
        ip = None

        try:
            with sync_playwright() as p:
                while True:
                    try:
                        cmd, payload = self.commands.get(timeout=0.015)
                    except queue.Empty:
                        cmd, payload = None, None

                    if cmd == "quit":
                        break

                    if cmd == "stop":
                        active_stop = None
                        if page:
                            try:
                                page.close()
                            except Exception:
                                pass
                            page = None

                        if browser:
                            try:
                                browser.close()
                            except Exception:
                                pass
                            browser = None
                        continue

                    if cmd == "load":
                        url, ip, show, active_stop = payload
                        if page:
                            try:
                                page.close()
                                browser.close()
                            except Exception:
                                pass

                        browser = p.chromium.launch(
                            headless=not show,
                            args=[
                                "--autoplay-policy=no-user-gesture-required",
                                "--disable-infobars",
                            ],
                        )
                        page = browser.new_page(
                            viewport={"width": 640, "height": 360},
                            device_scale_factor=1,
                        )
                        page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=60000,
                        )
                        self.events.put(("loaded", url))
                        continue

                    if page and cmd:
                        try:
                            if cmd == "play":
                                page.evaluate(
                                    """() => {
                                        const v = document.querySelector('video');
                                        if (v) v.play().catch(() => {});
                                    }"""
                                )
                            elif cmd == "pause":
                                page.evaluate(
                                    """() => {
                                        const v = document.querySelector('video');
                                        if (v) v.pause();
                                    }"""
                                )
                            elif cmd == "restart":
                                page.evaluate(
                                    """() => {
                                        const v = document.querySelector('video');
                                        if (v) {
                                            v.currentTime = 0;
                                            v.play().catch(() => {});
                                        } else {
                                            location.reload();
                                        }
                                    }"""
                                )
                            elif cmd == "seek":
                                page.evaluate(
                                    """(t) => {
                                        const v = document.querySelector('video');
                                        if (v && Number.isFinite(v.duration)) {
                                            v.currentTime = t;
                                        }
                                    }""",
                                    float(payload),
                                )
                            elif cmd == "visibility":
                                if browser:
                                    browser.close()

                                browser = p.chromium.launch(
                                    headless=not bool(payload),
                                    args=[
                                        "--autoplay-policy=no-user-gesture-required",
                                        "--disable-infobars",
                                    ],
                                )
                                page = browser.new_page(
                                    viewport={"width": 640, "height": 360},
                                    device_scale_factor=1,
                                )
                                page.goto(
                                    self.url_var.get().strip(),
                                    wait_until="domcontentloaded",
                                    timeout=60000,
                                )
                        except Exception as exc:
                            self.events.put(("error", str(exc)))

                    if page and active_stop and not active_stop.is_set():
                        try:
                            shot = page.screenshot(type="jpeg", quality=65)
                            frame = cv2.imdecode(
                                np.frombuffer(shot, dtype=np.uint8),
                                cv2.IMREAD_COLOR,
                            )

                            if frame is not None:
                                tiny = cv2.resize(
                                    frame,
                                    (15, 13),
                                    interpolation=cv2.INTER_AREA,
                                )
                                rgb = cv2.cvtColor(
                                    tiny, cv2.COLOR_BGR2RGB
                                ).reshape(-1, 3)
                                selected = rgb[PIXELS[:89]]
                                rgba = np.zeros(
                                    (len(selected), 4),
                                    dtype=np.uint8,
                                )
                                rgba[:, :3] = selected
                                self.frame_socket.sendto(
                                    rgba.tobytes(), (ip, 8388)
                                )

                            info = page.evaluate(
                                """() => {
                                    const v = document.querySelector('video');
                                    return v
                                        ? {
                                            duration: Number.isFinite(v.duration)
                                                ? v.duration : 0,
                                            currentTime: v.currentTime || 0,
                                            paused: v.paused
                                        }
                                        : {
                                            duration: 0,
                                            currentTime: 0,
                                            paused: true
                                        };
                                }"""
                            )
                            self.events.put(("time", info))
                        except Exception as exc:
                            self.events.put(("error", str(exc)))
                            active_stop = None

                        time.sleep(1 / 20)
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            try:
                if browser:
                    browser.close()
            except Exception:
                pass

    def _send_command(self, command, payload=None):
        self.commands.put((command, payload))

    def toggle_play(self):
        if not self.worker or not self.worker.is_alive():
            self.load_url()
            return

        self.playing = not self.playing
        self._send_command("play" if self.playing else "pause")
        self.play_button.configure(
            text="❚❚  Pause" if self.playing else "▶  Play"
        )

    def restart(self):
        self._send_command("restart")
        self.playing = True
        self.play_button.configure(text="❚❚  Pause")

    def set_browser_visibility(self):
        if self.worker and self.worker.is_alive():
            self._send_command(
                "visibility", self.show_browser_var.get()
            )
            self.message_var.set(
                "Reopening the page with the selected browser visibility."
            )

    def _seek_changed(self, value):
        if not self.seeking:
            return

        if self.duration > 0:
            self.time_var.set(
                f"{self._fmt(float(value))}  /  {self._fmt(self.duration)}"
            )

    def _seek_released(self, _event):
        self.seeking = False
        if self.duration > 0:
            self._send_command(
                "seek", self.seek_var.get() * self.duration / 100.0
            )

    @staticmethod
    def _fmt(seconds):
        seconds = max(0, int(seconds))
        return f"{seconds // 60}:{seconds % 60:02d}"

    def _get_monitor_sources(self):
        try:
            result = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            for line in result.stdout.splitlines():
                fields = line.split()
                if len(fields) >= 2 and ".monitor" in fields[1]:
                    return fields[1]
        except (OSError, subprocess.SubprocessError):
            pass

        return "@DEFAULT_MONITOR@"

    def toggle_audio(self):
        if not self.audio_var.get():
            self._stop_audio()
            self.message_var.set("Audio loopback stopped.")
            return

        ip = self._valid_ip()
        if not ip:
            self.audio_var.set(False)
            return

        if platform.system() == "Windows":
            self._start_windows_audio(ip)
        else:
            self._start_linux_audio(ip)

    def _start_linux_audio(self, ip):
        source = self._get_monitor_sources()
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "pulse",
            "-i",
            source,
            "-ac",
            "1",
            "-ar",
            "44100",
            "-acodec",
            "pcm_s16le",
            "-f",
            "s16le",
            f"udp://{ip}:8188?pkt_size=1024",
        ]

        try:
            self.audio_process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self.message_var.set(
                f"Audio loopback started from {source}."
            )
        except FileNotFoundError:
            self.audio_var.set(False)
            messagebox.showerror(
                "FFmpeg not found",
                "Install ffmpeg and make sure PulseAudio/PipeWire audio is available.",
            )

    def _start_windows_audio(self, ip):
        try:
            import soundcard as sc
        except ImportError:
            self.audio_var.set(False)
            messagebox.showerror(
                "Missing Windows audio package",
                "Install the audio package with:\n"
                "python -m pip install soundcard",
            )
            return

        self.audio_stop.clear()

        def capture():
            try:
                speaker = sc.default_speaker()
                loopback = sc.get_microphone(
                    id=str(speaker.name),
                    include_loopback=True,
                )

                with loopback.recorder(
                    samplerate=44100,
                    channels=1,
                ) as recorder:
                    while not self.audio_stop.is_set():
                        samples = recorder.record(numframes=512)
                        pcm = (
                            np.clip(samples, -1.0, 1.0) * 32767
                        ).astype("<i2")
                        self.audio_socket.sendto(
                            pcm.tobytes(), (ip, 8188)
                        )
            except Exception as exc:
                self.events.put(
                    ("error", f"Windows audio capture: {exc}")
                )
                self.events.put(("audio_failed", None))

        self.audio_thread = threading.Thread(
            target=capture,
            daemon=True,
        )
        self.audio_thread.start()
        self.message_var.set("Windows audio loopback started.")

    def _stop_audio(self):
        self.audio_stop.set()

        if self.audio_process and self.audio_process.poll() is None:
            self.audio_process.terminate()
            try:
                self.audio_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.audio_process.kill()

        self.audio_process = None

    def _poll_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()

                if kind == "loaded":
                    self.status_var.set("●  Page loaded")
                    self.message_var.set(
                        f"Streaming browser frames to "
                        f"{self.ip_var.get().strip()}:8388."
                    )
                elif kind == "time":
                    self.duration = payload.get("duration", 0.0)
                    self.position = payload.get("currentTime", 0.0)
                    self.playing = not payload.get("paused", True)
                    self.play_button.configure(
                        text="❚❚  Pause" if self.playing else "▶  Play"
                    )

                    if self.duration > 0:
                        if not self.seeking:
                            self.seek_var.set(
                                self.position * 100 / self.duration
                            )
                        self.time_var.set(
                            f"{self._fmt(self.position)}  /  "
                            f"{self._fmt(self.duration)}"
                        )
                    else:
                        self.time_var.set(
                            "Webpage mode  /  no HTML video detected"
                        )
                elif kind == "audio_failed":
                    self.audio_var.set(False)
                    self._stop_audio()
                elif kind == "error":
                    self.status_var.set("●  Browser error")
                    self.message_var.set(str(payload)[:220])
        except queue.Empty:
            pass

        self.root.after(100, self._poll_events)

    def close(self):
        self.stop_event.set()
        self.commands.put(("quit", None))
        self._stop_audio()

        try:
            self.audio_socket.close()
            self.frame_socket.close()
        except OSError:
            pass

        self.root.destroy()


def main():
    root = tk.Tk()
    StationControl(root)
    root.mainloop()


if __name__ == "__main__":
    main()
