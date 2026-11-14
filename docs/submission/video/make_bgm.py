#!/usr/bin/env python3
"""숏폼 배경음(조용한 밤, 밝고 안정적) — 표준 라이브러리만으로 합성. 사용: python3 make_bgm.py out.wav [초]
ponytail: 외부 음원 없이 C장조 펜타토닉 음악상자풍 아르페지오 + 부드러운 패드. 잔향은 ffmpeg aecho로 입힌다."""
import math, struct, sys, wave, random

SR = 48000
OUT = sys.argv[1] if len(sys.argv) > 1 else "bgm.wav"
DUR = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
BPM = 72; BEAT = 60 / BPM; STEP = BEAT / 2  # 8분음표 단위 아르페지오

def hz(n): return 440.0 * 2 ** ((n - 69) / 12)
# 코드 진행(2마디씩): C - Am - F - G  (MIDI)
CHORDS = [[60, 64, 67, 71], [57, 60, 64, 67], [53, 57, 60, 65], [55, 59, 62, 67]]
ARP = [0, 1, 2, 3, 2, 1, 0, 2, 1, 3, 2, 1, 0, 1, 2, 3]  # 2마디(16스텝) 패턴

n = int(SR * DUR); L = [0.0] * n; R = [0.0] * n
random.seed(7)

def pluck(t0, f, amp, pan):
    # 음악상자/전기피아노 느낌: 기본음 + 2배음 약간, 빠른 어택, 지수 감쇠
    i0 = int(t0 * SR); dur = 1.6; m = int(dur * SR)
    for k in range(m):
        i = i0 + k
        if i >= n: break
        t = k / SR
        env = (1 - math.exp(-t * 400)) * math.exp(-t * 2.2)
        s = math.sin(2 * math.pi * f * t) + 0.25 * math.sin(2 * math.pi * 2 * f * t) * math.exp(-t * 6) + 0.08 * math.sin(2 * math.pi * 3 * f * t) * math.exp(-t * 10)
        v = amp * env * s
        L[i] += v * (1 - pan); R[i] += v * pan

def pad(t0, notes, dur, amp):
    i0 = int(t0 * SR); m = int(dur * SR)
    for k in range(m):
        i = i0 + k
        if i >= n: break
        t = k / SR
        env = min(1, t / 1.2) * min(1, (dur - t) / 1.2)
        s = 0.0
        for j, nn in enumerate(notes):
            f = hz(nn - 12)
            s += math.sin(2 * math.pi * f * t + 0.3 * j) * (0.8 + 0.2 * math.sin(2 * math.pi * 0.17 * t + j))
            s += 0.5 * math.sin(2 * math.pi * f * 1.003 * t)  # 살짝 디튠 → 넓은 느낌
        v = amp * env * s / (len(notes) * 1.5)
        L[i] += v * 0.55; R[i] += v * 0.45

t = 0.0; bar = 0
while t < DUR:
    chord = CHORDS[(bar // 2) % 4]
    if bar % 2 == 0: pad(t, chord, 4 * BEAT + 0.3, 0.16)
    for s in range(8):
        step = (bar % 2) * 8 + s
        deg = ARP[step]
        note = chord[deg] + (12 if deg >= 2 and random.random() < 0.35 else 0)
        amp = 0.17 if s % 4 == 0 else 0.11
        if random.random() < 0.08: amp = 0.0  # 가끔 쉼표
        pluck(t + s * STEP + random.uniform(-0.004, 0.004), hz(note), amp, 0.35 + 0.3 * (deg / 3))
        if s == 0 and bar % 2 == 0: pluck(t, hz(chord[0] - 12), 0.12, 0.5)  # 저음 루트
    t += 4 * BEAT; bar += 1

peak = max(max(map(abs, L)), max(map(abs, R))) or 1
with wave.open(OUT, "w") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    fr = bytearray()
    for i in range(n):
        g = 0.85 / peak
        fr += struct.pack("<hh", int(L[i] * g * 32767), int(R[i] * g * 32767))
    w.writeframes(bytes(fr))
print(OUT, DUR, "s")
