#!/usr/bin/env python3
"""숏폼 v2 (1080x1920, 약 55초) — Pleos 실녹화본(raw_pleos_A/B.webm)으로 스토리텔링 + 모션.
실행: /usr/bin/python3 build_shortform_v2.py  (ffmpeg, Pillow 필요. 시스템 python3에 Pillow 있음)
ponytail: 외부 모션 툴 없이 ffmpeg 식(overlay/scale eval=frame/fade alpha/zoompan/xfade)만 쓴다.
         배경음은 make_bgm.py가 합성한 음악상자풍 아르페지오. TTS 구간은 sidechaincompress로 덕킹.
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
    """120초 넘으면 죽이고 최대 3회 재시도(안전망)."""
    if os.environ.get("DEBUG"): import json; open(os.environ["DEBUG"], "a").write(json.dumps(args) + "\n")
    # 멈춤 원인(스레드 스택으로 확인): 별도 -f lavfi 입력(anullsrc/color)의 디먹서 스레드가 큐 전송에서 막히고 필터 스레드는 수신 대기 → 스케줄러 교착.
    # 소스를 필터그래프 안으로 옮긴 뒤 32/32 통과. 타임아웃+재시도는 안전망으로만 남긴다.
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-filter_threads", "1", "-filter_complex_threads", "1", *args]
    for attempt in range(3):
        try:
            r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=float(os.environ.get("FFTIMEOUT", "120")))
        except subprocess.TimeoutExpired:
            print(f"ffmpeg hang, retry {attempt + 1}/3", file=sys.stderr); continue
        if r.returncode: sys.exit(f"ffmpeg failed:\n{' '.join(args)[:2000]}\n{r.stderr[-3000:]}")
        return
    sys.exit("ffmpeg hung 3 times")

def font(size, weight="regular"):
    idx = {"regular": 0, "medium": 2, "semibold": 4, "bold": 6}[weight if isinstance(weight, str) else ("bold" if weight else "regular")]
    return ImageFont.truetype(FONT, size, index=idx)

def _draw_spaced(d, xy, text, f, fill, spacing):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill); x += f.getlength(ch) + spacing

def text_png(name, items, align="center", pad=24, bg=None, radius=0, shadow=False):
    """items = [(text, size, color, weight)] 줄 단위. weight: bold/semibold/medium/regular(또는 True/False).
    자간은 크기에 비례해 살짝 좁힌다(한글 헤드라인). shadow=True면 사진 위 가독성용 부드러운 그림자."""
    fs = [font(s, wgt) for _, s, _, wgt in items]
    sp = [-round(s * 0.04) for _, s, _, _ in items]
    ws = [int(sum(f.getlength(ch) for ch in t) + k * (len(t) - 1)) for (t, *_), f, k in zip(items, fs, sp)]
    hs = [int(s * 1.32) for _, s, _, _ in items]
    w, h = max(ws) + pad * 2, sum(hs) + pad * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if bg: ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=bg + (255,))
    def paint(layer, color_of, dx=0, dy=0):
        d = ImageDraw.Draw(layer); y = pad
        for (t, s, c, _), f, bw, bh, k in zip(items, fs, ws, hs, sp):
            x = pad if align == "left" else (w - bw) // 2
            _draw_spaced(d, (x + dx, y + dy + (bh - s) // 2 - int(s * 0.12)), t, f, color_of(c), k); y += bh
    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0)); paint(sh, lambda c: (0, 0, 0, 200), 0, 6)
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(10)))
    paint(im, lambda c: c + (255,))
    p = os.path.join(T, name); im.save(p); return p, w, h

def chip(name, text, size=40):
    return text_png(name, [(text, size, WHITE, True)], pad=22, bg=DARK, radius=40)

def device_assets():
    dw, dh = 900, 965  # 앱 영역 1100x1180(상태바·내비바 제외) → 900 폭
    m = Image.new("L", (dw, dh), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, dw - 1, dh - 1), 36, fill=255)
    mp = os.path.join(T, "mask.png"); m.save(mp)
    return mp, None, dw, dh

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

# ---------- 모션 식 (ffmpeg expr) ----------
# U: 0→1 진행도, E: ease-out cubic, 오버슈트는 sin(U*PI)로 살짝 넘겼다 돌아오게
def U(start, d): return f"min(1,max(0,(t-{start}))/{d})"
def E(start, d): return f"(1-pow(1-{U(start, d)},3))"
def y_up(y0, start, d=0.55, dist=70, over=18):   # 아래서 올라오며 살짝 넘침
    return f"{y0}+{dist}*(1-{E(start, d)})-{over}*sin({U(start, d)}*PI)"
def x_right(x0, start, d=0.5, over=16):          # 오른쪽 밖에서 들어옴
    return f"{x0}+({W}-{x0})*(1-{E(start, d)})-{over}*sin({U(start, d)}*PI)"
def s_pop(start, d=0.38, over=0.10):             # 0.5→1.1→1.0 팝
    return f"(0.5+0.5*{E(start, d)}+{over}*sin({U(start, d)}*PI))"
def y_device(y0, rise):                          # 등장 + 느린 부유
    f = f"+5*sin(2*PI*t/3.5)"
    return (f"{y0}+({H}-{y0})*(1-{E(0, 0.8)})-26*sin({U(0, 0.8)}*PI){f}") if rise else f"{y0}{f}"

class Scene:
    def __init__(self, name, dur):
        self.name, self.dur, self.inputs, self.fc, self.n, self.last, self.audio = name, dur, [], [], 0, None, None
    def add_input(self, args):
        self.inputs += args; self.n += 1; return self.n - 1
    def base(self, label): self.last = label
    def layer(self, png, x, y, start=0.0, anim="fade", end=None, enable=None, fade=0.25, grow=None, seq=False):
        """x,y: 숫자(또는 식). anim: fade | up | pop | right. end: 사라지는 시각. enable: 보이는 조건식. grow: 폭이 0→100%로 자라는 선.
        seq=True: png는 프레임 시퀀스 패턴(%02d). start까지 투명으로 기다렸다가 재생하고 마지막 프레임을 유지."""
        if seq:
            i = self.add_input(["-framerate", str(FPS), "-i", png])
            f = f"[{i}:v]format=rgba,tpad=start_duration={start}:start_mode=add:color=0x00000000:stop_mode=clone:stop_duration={self.dur + 1}"
        else:
            i = self.add_input(["-loop", "1", "-framerate", str(FPS), "-t", str(self.dur + 1), "-i", png])  # 무한 소스 금지(필터 교착 방지)
            f = f"[{i}:v]format=rgba,fade=t=in:st={start}:d={fade}:alpha=1"
        if end is not None: f += f",fade=t=out:st={end}:d=0.3:alpha=1"
        if anim == "pop": f += f",scale=w='iw*{s_pop(start)}':h=-1:eval=frame"
        if grow: f += f",scale=w='max(2,iw*{E(start, grow)})':h=ih:eval=frame"
        f += f"[l{i}]"; self.fc.append(f)
        if anim == "up": y = y_up(y, start)
        if anim == "right": x = x_right(x, start)
        en = f":enable='{enable}'" if enable else ""
        self.fc.append(f"[{self.last}][l{i}]overlay=x='{x}':y='{y}':eval=frame{en}[v{i}]"); self.last = f"v{i}"
    def render(self):
        out = os.path.join(T, f"{self.name}.mp4"); print("render", self.name, file=sys.stderr, flush=True)
        if self.audio: afc = f"{self.audio},apad,atrim=0:{self.dur}[a]"
        else: afc = f"anullsrc=r=48000:cl=stereo,atrim=0:{self.dur}[a]"  # 그래프 안 소스(별도 lavfi 입력은 스케줄러 교착을 일으킴)
        fc = ";".join(self.fc + [afc, f"[{self.last}]fps={FPS},format=yuv420p[vo]"])
        run([*self.inputs, "-filter_complex", fc, "-map", "[vo]", "-map", "[a]", "-t", str(self.dur), *ENC, out])
        return out

def solid(sc):
    sc.fc.append(f"color=c=0x{BG}:s={W}x{H}:r={FPS}:d={sc.dur + 1}[bg]"); sc.base("bg")

def still(sc, img):
    i = sc.add_input(["-loop", "1", "-framerate", str(FPS), "-t", str(sc.dur + 1), "-i", img]); sc.base(f"{i}:v")

def gradient_png(name, top, bottom):
    g = Image.linear_gradient("L").resize((W, H))
    im = Image.composite(Image.new("RGB", (W, H), bottom), Image.new("RGB", (W, H), top), g)
    p = os.path.join(T, name); im.save(p); return p

def ring_seq(name, r, stroke, color, n=36):
    """링이 12시에서 시계방향으로 그려지는 n프레임 시퀀스(이징). 밑에 넓은 글로우."""
    d = os.path.join(T, name); os.makedirs(d, exist_ok=True); S = (r + 60) * 2; c = S // 2
    for k in range(n):
        u = (k + 1) / n; e = 1 - (1 - u) ** 3; box = (c - r, c - r, c + r, c + r)
        glow = Image.new("RGBA", (S, S), (0, 0, 0, 0)); ImageDraw.Draw(glow).arc(box, -90, -90 + 360 * e, fill=color + (110,), width=stroke * 3)
        im = glow.filter(ImageFilter.GaussianBlur(stroke * 1.4))
        ImageDraw.Draw(im).arc(box, -90, -90 + 360 * e, fill=color + (255,), width=stroke)
        im.save(os.path.join(d, f"{k:02d}.png"))
    return os.path.join(d, "%02d.png"), S

def kenburns(sc, img, dark=0.5, zoom_per_frame=0.0006, pan=(0, 0)):
    """느린 줌 + 팬(pan: 프레임당 px). 사진 위 글자 가독성용 어둡기(dark)."""
    i = sc.add_input(["-loop", "1", "-framerate", str(FPS), "-t", str(sc.dur), "-i", img])
    sc.fc.append(f"[{i}:v]scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
                 f"zoompan=z='min(1+{zoom_per_frame}*on,1.3)':x='iw/2-(iw/zoom/2)+{pan[0]}*on':y='ih/2-(ih/zoom/2)+{pan[1]}*on':d=1:s={W}x{H}:fps={FPS},"
                 f"drawbox=x=0:y=0:w={W}:h={H}:color=0x{BG}@{dark}:t=fill[kb]"); sc.base("kb")

def device(sc, foot, start, end, speed, y0, rise=False, audio=False):
    mp, _, dw, dh = ASSETS
    i = sc.add_input(["-ss", str(start), "-t", str(end - start), "-i", foot])
    m = sc.add_input(["-loop", "1", "-framerate", str(FPS), "-t", str(sc.dur + 1), "-i", mp])
    # 앱 영역에서 상태바(0~100)와 내비바(1280~)를 뺀 가운데 1100x1180만, 둥근 모서리
    sc.fc.append(f"[{i}:v]setpts=(PTS-STARTPTS)/{speed},fps={FPS},crop=1100:1180:303:100,scale={dw}:{dh}[app];[{m}:v]format=gray[mk];[app][mk]alphamerge[dev]")
    sc.fc.append(f"[{sc.last}][dev]overlay=x={(W-dw)//2}:y='{y_device(y0, rise)}':eval=frame[dv]"); sc.base("dv")
    if audio: sc.audio = f"[{i}:a]asetpts=PTS-STARTPTS"

def center(w): return "(W-w)/2"  # overlay 식: 팝(가변 폭)에도 가운데 유지

def rect_png(name, w, h, color, radius=None):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), radius if radius is not None else h // 2, fill=color + (255,))
    p = os.path.join(T, name); im.save(p); return p

def glow_png(name, r, color):
    im = Image.new("RGBA", (r * 4, r * 4), (0, 0, 0, 0)); ImageDraw.Draw(im).ellipse((r, r, 3 * r, 3 * r), fill=color + (255,))
    im = im.filter(ImageFilter.GaussianBlur(r * 0.6)); p = os.path.join(T, name); im.save(p); return p, r * 4

# ---------- 장면 ----------
def build():
    global ASSETS
    ASSETS = device_assets(); F = prep_footage(); scenes = []; trans = []
    NR, NW = os.path.join(BRAND, "night-rest.png"), os.path.join(BRAND, "night-waiting.png")  # 생성 이미지(밤 휴게소 충전 / 차 안에서 폰 알람)
    DY = 620  # 기기 프레임 y (965 높이 → 1585)
    line = rect_png("line.png", 520, 8, MINT)

    # 1 훅: 키네틱 텍스트 (팝 오버슈트 → 민트 밑줄이 자라남)
    sc = Scene("s1", 3.8); kenburns(sc, NR, dark=0.35, zoom_per_frame=0.0012, pan=(0.6, 0))
    p, w, h = text_png("h1.png", [("알람", 170, WHITE, True)], shadow=True); sc.layer(p, center(w), 620, 0.1, "pop")
    p, w, h = text_png("h2.png", [("맞추지 마세요.", 120, WHITE, True)], shadow=True); sc.layer(p, center(w), 830, 0.55, "pop")
    p, w, h = text_png("h3.png", [("출발 시각엔 차가 깨워요.", 76, MINT, True)], shadow=True); sc.layer(p, center(w), 1060, 1.7, "up")
    sc.layer(line, center(0), 1180, 2.1, "fade", grow=0.6)
    scenes.append(sc); trans.append("fadeblack")

    # 2 문제: 줄마다 올라오며 등장, 마지막 줄 팝
    sc = Scene("s2", 4.4); kenburns(sc, NW, dark=0.42, pan=(0, -0.5))
    p, w, h = text_png("p1.png", [("충전하는 동안,", 80, WHITE, True)], shadow=True); sc.layer(p, center(w), 640, 0.2, "up")
    p, w, h = text_png("p2.png", [("시트는 손으로 젖히고", 62, WHITE, "medium")], shadow=True); sc.layer(p, center(w), 790, 1.0, "up")
    p, w, h = text_png("p3.png", [("알람은 폰으로 맞추고", 62, WHITE, "medium")], shadow=True); sc.layer(p, center(w), 880, 1.7, "up")
    p, w, h = text_png("p4.png", [("그럴 필요 없어요.", 76, AMBER, True)], shadow=True); sc.layer(p, center(w), 1060, 2.7, "pop")
    scenes.append(sc); trans.append("slideup")

    # 3 해결: 기기 프레임이 튀어오르듯 등장 (A 47–59.5, 2배속)
    sc = Scene("s3", 6.3); solid(sc); device(sc, F["A"], 47, 59.5, 2, DY, rise=True)
    p, w, h = text_png("c3a.png", [("출발 시각만 고르세요", 78, MINT, True)]); sc.layer(p, center(w), 300, 0.7, "pop")
    p, w, h = text_png("c3b.png", [("10분 후, 한 번 탭", 46, GRAY, "semibold")]); sc.layer(p, center(w), 420, 1.3, "up")
    scenes.append(sc); trans.append("smoothup")

    # 4 원탭 휴식 + TTS (A 59.5–68.5, 1배속), 칩 3개가 오른쪽에서 차례로
    sc = Scene("s4", 9.0); solid(sc); device(sc, F["A"], 59.5, 68.5, 1, DY, audio=True)
    p, w, h = text_png("c4a.png", [("시트, 조명, 공조", 72, WHITE, True), ("한 번에.", 72, MINT, True)]); sc.layer(p, center(w), 250, 0.3, "up")
    p, w, h = text_png("c4b.png", [("차가 직접 말해요", 44, AMBER, "semibold")]); sc.layer(p, center(w), 1660, 0.6, "up")
    chips = [chip(f"chip{k}.png", t) for k, t in enumerate(["등받이 절반", "조명 낮춤", "공조 22°C"])]
    x = (W - sum(w for _, w, _ in chips) - 24 * 2) // 2  # 세 칩을 한 줄로 가로 가운데
    for (p, w, h), st in zip(chips, (4.2, 4.6, 5.0)):
        sc.layer(p, f"{x}+({w}-w)/2", f"1740+({h}-h)/2", st, "pop", fade=0.15); x += w + 24
    scenes.append(sc); trans.append("fade")

    # 5 예측 (A 130–178, 9.6배속): 숫자가 65→75로 올라가는 카운터
    sc = Scene("s5", 5.0); solid(sc); device(sc, F["A"], 130, 178, 9.6, DY)
    p, w, h = text_png("c5a.png", [("충전 속도로", 56, GRAY, "medium"), ("출발 시 배터리를 예측", 72, WHITE, True)]); sc.layer(p, center(w), 250, 0.3, "up")
    t0, step = 2.4, 0.13
    for k, v in enumerate(range(65, 76)):
        p, w, h = text_png(f"cnt{v}.png", [(f"출발 시 약 {v}%", 60, AMBER, True)], pad=28, bg=DARK, radius=50)
        en = f"gte(t,{t0 + k * step:.2f})" if v == 75 else f"between(t,{t0 + k * step:.2f},{t0 + (k + 1) * step:.2f})"
        sc.layer(p, center(w), 1700, t0 if k == 0 else 0, "pop" if k == 0 else "fade", enable=en, fade=0.01)
    scenes.append(sc); trans.append("smoothleft")

    # 6 선라이즈 (B 0–33, 4.7배속) + 차오르는 밝기 바와 빛나는 머리
    sc = Scene("s6", 7.0); solid(sc); device(sc, F["B"], 0, 33, 33 / 7.0, DY)
    p, w, h = text_png("c6a.png", [("깨울 때가 되면,", 56, GRAY, "medium"), ("조명을 천천히 밝혀요", 72, WHITE, True)]); sc.layer(p, center(w), 250, 0.3, "up")
    tp = rect_png("track.png", 900, 26, DARK); fp = rect_png("fill.png", 900, 26, AMBER)
    cp = rect_png("cover.png", 90, 26, tuple(int(BG[i:i+2], 16) for i in (0, 2, 4)), radius=0)
    prog = f"min(1,max(0,t-1.0)/5.0)"
    sc.layer(tp, 90, 1720, 0.8); sc.layer(fp, f"90-900+900*{prog}", 1720, 1.0, fade=0.05); sc.layer(cp, 0, 1720, 0, fade=0.05)
    gp, gs = glow_png("glow.png", 22, AMBER); sc.layer(gp, f"90+900*{prog}-{gs // 2}", 1720 + 13 - gs // 2, 1.0, fade=0.3)
    p, w, h = text_png("c6b.png", [("밝기 10%에서 80%로, 바람은 한 단계 세게", 38, GRAY, "semibold")]); sc.layer(p, center(w), 1780, 1.2, "up")
    scenes.append(sc); trans.append("fade")

    # 7 깨움 + TTS + 복원 (B 33–47, 1배속)
    sc = Scene("s7", 14.0); solid(sc); device(sc, F["B"], 33, 47, 1, DY, audio=True)
    p, w, h = text_png("c7a.png", [("출발 시각에 깨우고,", 72, WHITE, True), ("원래대로.", 72, MINT, True)]); sc.layer(p, center(w), 250, 0.3, "up")
    p, w, h = text_png("c7b.png", [("\"출발 시각입니다. 배터리 72%.\"", 42, AMBER, "semibold")]); sc.layer(p, center(w), 1660, 1.2, "up", end=7.5)
    p, w, h = text_png("c7c.png", [("10초 뒤 시트, 조명, 공조 복원", 48, WHITE, True)], pad=26, bg=DARK, radius=48); sc.layer(p, center(w), 1680, 8.0, "pop", end=12.3)
    p, w, h = text_png("c7d.png", [("내리기 전 확인까지", 48, AMBER, True)], pad=26, bg=DARK, radius=48); sc.layer(p, center(w), 1680, 12.6, "pop")
    scenes.append(sc); trans.append("smoothup")

    # 8 학습 (B 80–93.5, 3배속)
    sc = Scene("s8", 4.5); solid(sc); device(sc, F["B"], 80, 93.5, 3, DY)
    p, w, h = text_png("c8a.png", [("두 번째부터는", 56, GRAY, "medium"), ("내 차의 속도를 기억", 72, WHITE, True)]); sc.layer(p, center(w), 250, 0.2, "up")
    p, w, h = chip("chip8.png", "지난 충전 기준 약 15분", 44); sc.layer(p, center(w), 1700, 2.4, "pop")
    scenes.append(sc); trans.append("circleopen")

    # 9 엔드카드: 링이 그려지고 → 링 중앙에 이름 팝 → 슬로건 두 줄 계단식 → 해시태그
    sc = Scene("s9", 6.0); still(sc, gradient_png("grad.png", (9, 24, 66), (5, 9, 26)))
    CX, CY, R = 540, 600, 400
    rp, rs = ring_seq("ring", R, 14, MINT); sc.layer(rp, CX - rs // 2, CY - rs // 2, 0.2, seq=True)
    p, w, h = text_png("e1.png", [("충전쉼표", 140, WHITE, True), ("Plug & Rest", 46, MINT, "semibold")], shadow=True); sc.layer(p, center(w), f"{CY}-h/2", 1.1, "pop")
    p, w, h = text_png("e2.png", [("충전은 차가,", 84, WHITE, True)], shadow=True); sc.layer(p, center(w), 1140, 1.7, "up")
    p, w, h = text_png("e2b.png", [("휴식은 당신이.", 84, WHITE, True)], shadow=True); sc.layer(p, center(w), 1250, 1.95, "up")
    p, w, h = text_png("e3.png", [("차가 알람이 됩니다.", 52, AMBER, True)], shadow=True); sc.layer(p, center(w), 1420, 2.6, "pop")
    p, w, h = text_png("e4.png", [("#HMG차량용앱개발공모전 #PleosConnect #전기차충전", 34, MINT, "semibold")]); sc.layer(p, center(w), 1760, 3.3, "up")
    scenes.append(sc)

    files = [s.render() for s in scenes]; durs = [s.dur for s in scenes]
    # 장면 전환: xfade(장면마다 다른 전환) + acrossfade
    inputs = []; [inputs.extend(["-i", f]) for f in files]
    fc, cur, vlast, alast = [], durs[0], "0:v", "0:a"
    for k in range(1, len(files)):
        off = round(cur - XF, 3)
        fc.append(f"[{vlast}][{k}:v]xfade=transition={trans[k - 1]}:duration={XF}:offset={off}[xv{k}]")
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
