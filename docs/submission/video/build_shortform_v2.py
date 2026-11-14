#!/usr/bin/env python3
"""숏폼 v2 (1080x1920, 약 55초) — Pleos 실녹화본(raw_pleos_A/B.webm)으로 스토리텔링 + 모션.
실행: /usr/bin/python3 build_shortform_v2.py  (ffmpeg, Pillow 필요. 시스템 python3에 Pillow 있음)
ponytail: 외부 모션 툴 없이 ffmpeg 식(overlay/scale eval=frame/fade alpha/zoompan/xfade)만 쓴다.
         배경음은 ffmpeg aevalsrc로 만든 드론 패드. TTS 구간은 sidechaincompress로 덕킹.
구성: 훅(키네틱 텍스트) → 문제 → 해결(기기 프레임 슬라이드 인) → 원탭 휴식(TTS, 칩) → 예측 → 선라이즈(밝기 바) → 깨움(TTS) → 학습 → 엔드카드
"""
import os, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.join(HERE, "..", "..", "design", "brand")
OUT = os.path.join(HERE, "shortform_pleos_v2.mp4")
W, H, FPS, XF = 1080, 1920, 30, 0.4
BG = "0E0F12"
MINT, AMBER, WHITE, GRAY, DARK = (67, 224, 160), (255, 199, 90), (245, 245, 245), (170, 176, 182), (28, 31, 38)
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
T = tempfile.mkdtemp(prefix="sf2_")
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]

def run(args):
    """ffmpeg 9.0.2가 드물게 필터그래프에서 멈춘다(출력 0% CPU, moov 없음). 120초 넘으면 죽이고 최대 3회 재시도."""
    if os.environ.get("DEBUG"): print("ffmpeg", " ".join(args), flush=True)
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-filter_threads", "1", "-filter_complex_threads", "1", *args]
    for attempt in range(3):
        try:
            r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=float(os.environ.get("FFTIMEOUT", "120")))
        except subprocess.TimeoutExpired:
            print(f"ffmpeg hang, retry {attempt + 1}/3", file=sys.stderr); continue
        if r.returncode: sys.exit(f"ffmpeg failed:\n{' '.join(args)[:2000]}\n{r.stderr[-3000:]}")
        return
    sys.exit("ffmpeg hung 3 times")

def font(size, bold=False): return ImageFont.truetype(FONT, size, index=6 if bold else 0)

def text_png(name, items, align="center", pad=24, bg=None, radius=0):
    """items = [(text, size, color, bold)] 줄 단위. 캔버스는 글자에 맞춰 자동."""
    fs = [font(s, b) for _, s, _, b in items]
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    boxes = [d0.textbbox((0, 0), t, font=f) for (t, *_), f in zip(items, fs)]
    ws = [b[2] - b[0] for b in boxes]; hs = [int(s * 1.25) for _, s, _, _ in items]
    w, h = max(ws) + pad * 2, sum(hs) + pad * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    if bg: d.rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=bg + (255,))
    y = pad
    for (t, s, c, b), f, bw, bh, bx in zip(items, fs, ws, hs, boxes):
        x = pad if align == "left" else (w - bw) // 2 - bx[0]
        d.text((x, y - bx[1] + (bh - (bx[3] - bx[1])) // 2), t, font=f, fill=c + (255,))
        y += bh
    p = os.path.join(T, name); im.save(p); return p, w, h

def chip(name, text, size=40):
    return text_png(name, [(text, size, WHITE, True)], pad=22, bg=DARK, radius=40)

def device_assets():
    dw, dh = 900, 1023
    m = Image.new("L", (dw, dh), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, dw - 1, dh - 1), 36, fill=255)
    mp = os.path.join(T, "mask.png"); m.save(mp)
    sh = Image.new("RGBA", (dw + 160, dh + 160), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((80, 100, dw + 80, dh + 100), 36, fill=(0, 0, 0, 170))
    sh = sh.filter(ImageFilter.GaussianBlur(40)); sp = os.path.join(T, "shadow.png"); sh.save(sp)
    return mp, sp, dw, dh

def prep_footage():
    """에뮬레이터 webm → 앱 영역(오른쪽 1707px) 30fps mp4 (캐시: 같은 폴더 .cache)"""
    cache = os.path.join(HERE, ".cache"); os.makedirs(cache, exist_ok=True); out = {}
    for s in "AB":
        src = os.path.join(HERE, f"raw_pleos_{s}.webm"); dst = os.path.join(cache, f"{s}.mp4")
        if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
            run(["-i", src, "-vf", "crop=1707:1440:853:0,fps=30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                 "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", dst])
        out[s] = dst
    return out

# ---------- 모션 식 ----------
def ease_up(y0, start, d=0.6, dist=60):  # 아래에서 위로 올라오며 등장
    return f"{y0}+{dist}*(1-sin(min(1,max(0,(t-{start}))/{d})*PI/2))"
def slide_in_right(x0, start, d=0.5):   # 오른쪽 밖에서 들어옴
    return f"{x0}+({W}-{x0})*(1-sin(min(1,max(0,(t-{start}))/{d})*PI/2))"
def device_rise(y0, d=0.7):
    return f"{y0}+({H}-{y0})*(1-sin(min(1,t/{d})*PI/2))"

class Scene:
    def __init__(self, name, dur):
        self.name, self.dur, self.inputs, self.fc, self.n, self.last, self.audio = name, dur, [], [], 0, None, None
    def add_input(self, args):
        self.inputs += args; self.n += 1; return self.n - 1
    def base(self, label): self.last = label
    def layer(self, png, x, y, start=0.0, fade=0.3, pop=False, end=None):
        i = self.add_input(["-loop", "1", "-framerate", str(FPS), "-t", str(self.dur + 1), "-i", png])  # 무한 소스 금지(필터 교착 방지)
        f = f"[{i}:v]format=rgba,fade=t=in:st={start}:d={fade}:alpha=1"
        if end is not None: f += f",fade=t=out:st={end}:d=0.3:alpha=1"
        if pop: f += f",scale=w='iw*(0.7+0.3*min(1,max(0,t-{start})/0.25))':h=-1:eval=frame"
        f += f"[l{i}]"; self.fc.append(f)
        o = f"[{self.last}][l{i}]overlay=x='{x}':y='{y}':eval=frame[v{i}]"; self.fc.append(o); self.last = f"v{i}"
    def render(self):
        out = os.path.join(T, f"{self.name}.mp4")
        a = self.audio or f"anullsrc=r=48000:cl=stereo"
        if self.audio: afc = f"{self.audio},apad,atrim=0:{self.dur}[a]"
        else:
            self.add_input(["-f", "lavfi", "-t", str(self.dur + 1), "-i", "anullsrc=r=48000:cl=stereo"]); afc = f"[{self.n-1}:a]atrim=0:{self.dur}[a]"
        fc = ";".join(self.fc + [afc, f"[{self.last}]fps={FPS},format=yuv420p[vo]"])
        run([*self.inputs, "-filter_complex", fc, "-map", "[vo]", "-map", "[a]", "-t", str(self.dur), *ENC, out])
        return out

def solid(sc):
    i = sc.add_input(["-f", "lavfi", "-i", f"color=c=0x{BG}:s={W}x{H}:r={FPS}:d={sc.dur + 1}"]); sc.base(f"{i}:v")

def kenburns(sc, img, dark=0.5, zoom_per_frame=0.0006):
    i = sc.add_input(["-loop", "1", "-framerate", str(FPS), "-t", str(sc.dur), "-i", img])
    sc.fc.append(f"[{i}:v]scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},zoompan=z='min(1+{zoom_per_frame}*on,1.25)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS},"
                 f"drawbox=x=0:y=0:w={W}:h={H}:color=0x{BG}@{dark}:t=fill[kb]"); sc.base("kb")

def device(sc, foot, start, end, speed, y0, rise=False, audio=False):
    mp, sp, dw, dh = ASSETS
    i = sc.add_input(["-ss", str(start), "-t", str(end - start), "-i", foot])
    m = sc.add_input(["-loop", "1", "-framerate", str(FPS), "-t", str(sc.dur + 1), "-i", mp]); s = sc.add_input(["-loop", "1", "-framerate", str(FPS), "-t", str(sc.dur + 1), "-i", sp])
    sc.fc.append(f"[{i}:v]setpts=(PTS-STARTPTS)/{speed},fps={FPS},crop=1100:1250:303:70,scale={dw}:{dh}[app];[{m}:v]format=gray[mk];[app][mk]alphamerge[dev]")
    y = device_rise(y0) if rise else str(y0)
    sc.fc.append(f"[{s}:v]format=rgba[shd];[{sc.last}][shd]overlay=x={(W-dw)//2-80}:y='({y})-100':eval=frame[sh1];[sh1][dev]overlay=x={(W-dw)//2}:y='{y}':eval=frame[dv]"); sc.base("dv")
    if audio: sc.audio = f"[{i}:a]asetpts=PTS-STARTPTS"

def center(w): return "(W-w)/2"  # overlay 식: 팝 애니메이션(가변 폭)에도 가운데 유지

# ---------- 장면 ----------
def build():
    global ASSETS
    ASSETS = device_assets(); F = prep_footage(); scenes = []
    VB = os.path.join(BRAND, "vertical-bg.png")
    NR, NW = os.path.join(BRAND, "night-rest.png"), os.path.join(BRAND, "night-waiting.png")  # 생성 이미지(밤 휴게소 충전 / 차 안에서 폰 알람)

    # 1 훅: 키네틱 텍스트
    sc = Scene("s1", 3.8); kenburns(sc, NR, dark=0.35, zoom_per_frame=0.0012)
    p, w, h = text_png("h1.png", [("알람", 170, WHITE, True)]); sc.layer(p, center(w), 620, 0.1, 0.2, pop=True)
    p, w, h = text_png("h2.png", [("맞추지 마세요.", 120, WHITE, True)]); sc.layer(p, center(w), 830, 0.55, 0.2, pop=True)
    p, w, h = text_png("h3.png", [("출발 시각엔 차가 깨워요.", 76, MINT, True)]); sc.layer(p, center(w), ease_up(1060, 1.7), 1.7, 0.35)
    scenes.append(sc)

    # 2 문제
    sc = Scene("s2", 4.4); kenburns(sc, NW, dark=0.42)
    p, w, h = text_png("p1.png", [("충전하는 동안,", 80, WHITE, True)]); sc.layer(p, center(w), ease_up(640, 0.2), 0.2)
    p, w, h = text_png("p2.png", [("시트는 손으로 젖히고", 64, GRAY, False)]); sc.layer(p, center(w), ease_up(790, 1.0), 1.0)
    p, w, h = text_png("p3.png", [("알람은 폰으로 맞추고", 64, GRAY, False)]); sc.layer(p, center(w), ease_up(880, 1.7), 1.7)
    p, w, h = text_png("p4.png", [("그럴 필요 없어요.", 76, AMBER, True)]); sc.layer(p, center(w), ease_up(1060, 2.7), 2.7, pop=False)
    scenes.append(sc)

    DY = 600  # 기기 프레임 y
    # 3 해결: 출발 시각 고르기 (A 47–59.5, 2배속)
    sc = Scene("s3", 6.3); solid(sc); device(sc, F["A"], 47, 59.5, 2, DY, rise=True)
    p, w, h = text_png("c3a.png", [("출발 시각만 고르세요", 78, MINT, True)]); sc.layer(p, center(w), ease_up(300, 0.6), 0.6, pop=True)
    p, w, h = text_png("c3b.png", [("10분 후 · 한 번 탭", 46, GRAY, False)]); sc.layer(p, center(w), ease_up(420, 1.3), 1.3)
    scenes.append(sc)

    # 4 원탭 휴식 + TTS (A 59.5–68.5, 1배속)
    sc = Scene("s4", 9.0); solid(sc); device(sc, F["A"], 59.5, 68.5, 1, DY, audio=True)
    p, w, h = text_png("c4a.png", [("시트 · 조명 · 공조", 72, WHITE, True), ("한 번에.", 72, MINT, True)]); sc.layer(p, center(w), ease_up(250, 0.3), 0.3)
    p, w, h = text_png("c4b.png", [("차가 직접 말해요", 44, AMBER, False)]); sc.layer(p, center(w), 1660, 0.6)
    x = 90
    for k, (t, st) in enumerate([("등받이 절반", 4.2), ("조명 낮춤", 4.7), ("공조 22°C", 5.2)]):
        p, w, h = chip(f"chip{k}.png", t); sc.layer(p, slide_in_right(x, st), 1740, st, 0.25); x += w + 24
    scenes.append(sc)

    # 5 예측 (A 130–178, 9.6배속)
    sc = Scene("s5", 5.0); solid(sc); device(sc, F["A"], 130, 178, 9.6, DY)
    p, w, h = text_png("c5a.png", [("충전 속도로", 64, GRAY, False), ("출발 시 배터리를 예측", 72, WHITE, True)]); sc.layer(p, center(w), ease_up(250, 0.3), 0.3)
    p, w, h = text_png("c5b.png", [("약 65%  →  약 75%", 66, AMBER, True)], pad=28, bg=DARK, radius=50); sc.layer(p, center(w), 1700, 2.6, 0.2, pop=True)
    scenes.append(sc)

    # 6 선라이즈 (B 0–33, 4.7배속) + 밝기 바
    sc = Scene("s6", 7.0); solid(sc); device(sc, F["B"], 0, 33, 33 / 7.0, DY)
    p, w, h = text_png("c6a.png", [("깨울 때가 되면,", 64, GRAY, False), ("조명을 천천히 밝혀요", 72, WHITE, True)]); sc.layer(p, center(w), ease_up(250, 0.3), 0.3)
    track = Image.new("RGBA", (900, 26), (0, 0, 0, 0)); ImageDraw.Draw(track).rounded_rectangle((0, 0, 899, 25), 13, fill=DARK + (255,)); tp = os.path.join(T, "track.png"); track.save(tp)
    fill = Image.new("RGBA", (900, 26), (0, 0, 0, 0)); ImageDraw.Draw(fill).rounded_rectangle((0, 0, 899, 25), 13, fill=AMBER + (255,)); fp = os.path.join(T, "fill.png"); fill.save(fp)
    cover = Image.new("RGBA", (90, 26), tuple(int(BG[i:i+2], 16) for i in (0, 2, 4)) + (255,)); cp = os.path.join(T, "cover.png"); cover.save(cp)
    sc.layer(tp, 90, 1720, 0.8, 0.2); sc.layer(fp, f"90-900+900*min(1,max(0,t-1.0)/5.0)", 1720, 1.0, 0.1); sc.layer(cp, 0, 1720, 0, 0.05)
    p, w, h = text_png("c6b.png", [("앰비언트 밝기 10% → 80% · 풍량 1 → 2단", 36, GRAY, False)]); sc.layer(p, center(w), 1770, 1.2)
    scenes.append(sc)

    # 7 깨움 + TTS + 복원 (B 33–47, 1배속)
    sc = Scene("s7", 14.0); solid(sc); device(sc, F["B"], 33, 47, 1, DY, audio=True)
    p, w, h = text_png("c7a.png", [("출발 시각에 깨우고,", 72, WHITE, True), ("원래대로.", 72, MINT, True)]); sc.layer(p, center(w), ease_up(250, 0.3), 0.3)
    p, w, h = text_png("c7b.png", [("\"출발 시각입니다. 배터리 72%.\"", 42, AMBER, False)]); sc.layer(p, center(w), 1660, 1.2, end=7.5)
    p, w, h = text_png("c7c.png", [("10초 뒤 시트 · 조명 · 공조 복원", 48, WHITE, True)], pad=26, bg=DARK, radius=48); sc.layer(p, center(w), 1680, 8.0, 0.2, pop=True, end=12.3)
    p, w, h = text_png("c7d.png", [("내리기 전 확인까지", 48, AMBER, True)], pad=26, bg=DARK, radius=48); sc.layer(p, center(w), 1680, 12.6, 0.2, pop=True)
    scenes.append(sc)

    # 8 학습 (B 80–93.5, 3배속)
    sc = Scene("s8", 4.5); solid(sc); device(sc, F["B"], 80, 93.5, 3, DY)
    p, w, h = text_png("c8a.png", [("두 번째부터는", 64, GRAY, False), ("내 차의 속도를 기억", 72, WHITE, True)]); sc.layer(p, center(w), ease_up(250, 0.2), 0.2)
    p, w, h = chip("chip8.png", "지난 충전 기준 약 15분", 44); sc.layer(p, center(w), 1700, 2.4, 0.2, pop=True)
    scenes.append(sc)

    # 9 엔드카드
    sc = Scene("s9", 5.5); kenburns(sc, VB, dark=0.0, zoom_per_frame=0.0004)
    p, w, h = text_png("e1.png", [("충전쉼표", 140, WHITE, True), ("Plug & Rest", 46, MINT, False)]); sc.layer(p, center(w), 480, 0.2, 0.25, pop=True)
    p, w, h = text_png("e2.png", [("충전은 차가,", 84, WHITE, True), ("휴식은 당신이.", 84, WHITE, True)]); sc.layer(p, center(w), ease_up(1060, 1.0), 1.0)
    p, w, h = text_png("e3.png", [("차가 알람이 됩니다.", 52, AMBER, True)]); sc.layer(p, center(w), ease_up(1330, 1.8), 1.8)
    p, w, h = text_png("e4.png", [("#HMG차량용앱개발공모전 #PleosConnect #전기차충전", 34, MINT, False)]); sc.layer(p, center(w), 1760, 2.6)
    scenes.append(sc)

    files = [s.render() for s in scenes]; durs = [s.dur for s in scenes]
    # xfade 체인 + acrossfade 체인
    inputs = []; [inputs.extend(["-i", f]) for f in files]
    fc, cur, vlast, alast = [], durs[0], "0:v", "0:a"
    for k in range(1, len(files)):
        off = round(cur - XF, 3)
        fc.append(f"[{vlast}][{k}:v]xfade=transition=fade:duration={XF}:offset={off}[xv{k}]")
        fc.append(f"[{alast}][{k}:a]acrossfade=d={XF}:c1=tri:c2=tri[xa{k}]")
        vlast, alast, cur = f"xv{k}", f"xa{k}", off + durs[k]
    total = round(cur, 3)
    # 배경음(make_bgm.py) → TTS 사이드체인 덕킹
    bgm = os.path.join(HERE, ".cache", "bgm.wav")
    if not os.path.exists(bgm):  # make_bgm.py: 음악상자풍 아르페지오 + 패드, aecho 잔향
        subprocess.run([sys.executable, os.path.join(HERE, "make_bgm.py"), bgm + ".raw.wav", str(int(total) + 4)], check=True)
        run(["-i", bgm + ".raw.wav", "-af", "aecho=0.7:0.6:60|120|250:0.25|0.18|0.1,lowpass=f=5000,highpass=f=80,volume=0.9", bgm])
    inputs += ["-i", bgm]
    m = len(files)
    fc.append(f"[{m}:a]atrim=0:{total},afade=t=in:d=1.0,afade=t=out:st={total-3.0}:d=3.0,volume=0.45[mus]")
    fc.append(f"[{alast}]asplit=2[voice][sc]")
    fc.append(f"[mus][sc]sidechaincompress=threshold=0.01:ratio=12:attack=40:release=700:makeup=1[duck]")
    fc.append(f"[voice][duck]amix=inputs=2:duration=first:normalize=0,volume=2.0,alimiter=limit=0.9[ao]")
    run([*inputs, "-filter_complex", ";".join(fc), "-map", f"[{vlast}]", "-map", "[ao]", "-t", str(total), *ENC, "-movflags", "+faststart", OUT])
    print(OUT, total, "s")

if __name__ == "__main__":
    build()
