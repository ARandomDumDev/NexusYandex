import json, os, subprocess, time

print("загружаем кадры")

values = json.load(open("frames.txt"))
frames = [bytes(b for v in f for b in (v,v,v,0)) for f in values]

print("настраиваем LED")
fd = os.open("/dev/fb0", os.O_WRONLY)

print("включаем звук")
sound = subprocess.Popen(["aplay", "ba.wav"])
time.sleep(0.05) # такая задержка +- на aplay

t0 = time.perf_counter()
for i, frame in enumerate(frames):
    target = t0 + i / 30
    now = time.perf_counter()
    if now < target:
        time.sleep(target - now)
    elif now - target > 1/30:
        continue
    print("кадр", i+1)
    os.pwrite(fd,frame,0)

sound.wait()
print("проект был сделан felicityrux на гитхабе :3")
