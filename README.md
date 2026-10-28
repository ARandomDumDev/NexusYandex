# nexusnet for Yandex Station 2

My script for showing NexusNet (or any webpage) on the Yandex Station 2 LED lights, with audio sent to the speaker. felicity is a nexusnet dev

## 1. How it works
1. Opens the webpage on your PC in Chromium
2. Turns the webpage into tiny frames for the LED matrix
3. Sends the frames to the Station over UDP (port `8388`)
4. Can also send PC audio to the Station (port `8188`)

yeah thats basically it

## 2. Requirements

### PC
- Python 3
- Chromium (installed by Playwright)
- the Python packages below
- FFmpeg on Linux if you want audio
- On Windows, `soundcard` for audio loopback

### Yandex Station 2
- Yandex Station 2 (obviously)
- Python 3 on the station (`yse install python3`)
- `netcat` (`yse install netcat`)
- `aplay` available for audio playback

Both devices need to be on the same network, and you need the Station's local IP.

## 3. Install

### Windows
```powershell
py -m pip install playwright opencv-python numpy soundcard
py -m playwright install chromium
```

### Linux
```bash
python3 -m pip install --user playwright opencv-python numpy
python3 -m playwright install chromium
sudo apt install ffmpeg
```

## 4. Run it

1. Run `yandex.py` on the Station:
   ```bash
   python3 yandex.py
   ```
2. Run `main.py` on your PC:
   ```bash
   python main.py
   ```
3. Enter the Station's local IP in the app.
4. Load `https://nexusnet.party` and press play.

The PC runs the webpage. The Station doesn't open the website itself; it just shows the tiny frames on its LED lights.

## 5. Notes
- The LED matrix is only 15x13 pixels, so don't expect to read the whole website on it.
- Audio capture depends on your OS and audio setup. On Linux, FFmpeg needs access to a PulseAudio/PipeWire monitor. On Windows, the `soundcard` package captures speaker loopback.
- If nothing shows up, check the Station IP, make sure both scripts are running, and check that UDP ports `8388` and `8188` aren't blocked.

---

фолывдаофдываодлфылаодфылдафоылдва (idk how to understand this)
