#!/usr/bin/env python3
"""숏폼 v2 (1080x1920, 약 55초) — Pleos 실녹화본(raw_pleos_A/B.webm)으로 스토리텔링 + 모션.
실행: /usr/bin/python3 build_shortform_v2.py  (ffmpeg, Pillow 필요. 시스템 python3에 Pillow 있음)
ponytail: 외부 모션 툴 없이 ffmpeg 식(overlay/scale eval=frame/fade alpha/zoompan/xfade)만 쓴다.
         배경음은 Mixkit 무료 음원(저작자 표시 불필요)을 .cache에 내려받아 쓴다(BGM_ID 환경변수로 교체). TTS 구간은 sidechaincompress로 덕킹.
구성: 훅(키네틱 텍스트) → 문제 → 해결(기기 프레임 슬라이드 인) → 원탭 휴식(TTS, 칩) → 예측 → 선라이즈(밝기 바) → 깨움(TTS) → 학습 → 엔드카드
"""
import os, re, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

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

def text_png(name, items, align="center", pad=24, bg=None, radius=0, shadow=False, border=None):
    """items = [(text, size, color, weight)] 줄 단위. weight: bold/semibold/medium/regular(또는 True/False).
    자간은 크기에 비례해 살짝 좁힌다(한글 헤드라인). shadow=True면 사진 위 가독성용 부드러운 그림자."""
    fs = [font(s, wgt) for _, s, _, wgt in items]
    sp = [-round(s * 0.04) for _, s, _, _ in items]
    ws = [int(sum(f.getlength(ch) for ch in t) + k * (len(t) - 1)) for (t, *_), f, k in zip(items, fs, sp)]
    hs = [int(s * 1.32) for _, s, _, _ in items]
    w, h = max(ws) + pad * 2, sum(hs) + pad * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if bg: ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=bg + (255,), outline=border and border + (255,), width=2 if border else 0)
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


def device_assets():
    dw, dh = 900, 965  # 앱 영역 1100x1180(상태바·내비바 제외) → 900 폭
    m = Image.new("L", (dw, dh), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, dw - 1, dh - 1), 36, fill=255)
    mp = os.path.join(T, "mask.png"); m.save(mp)
    # 카드: 아래로 떨어지는 부드러운 그림자 + 1px 밝은 테두리 (앱 화면 밑에 깔린다)
    M = 90; im = Image.new("RGBA", (dw + 2 * M, dh + 2 * M), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle((M, M + 30, M + dw, M + dh + 30), 36, fill=(0, 0, 0, 200))
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(36)))
    cp = os.path.join(T, "card.png"); im.save(cp)
    return mp, (cp, M), dw, dh



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
def y_device(y0, rise):                          # 등장(부유 흔들림은 뺐다: 화면이 위아래로 흔들려 보인다는 피드백)
    f = ""
    return (f"{y0}+({H}-{y0})*(1-{E(0, 0.8)})-26*sin({U(0, 0.8)}*PI){f}") if rise else f"{y0}{f}"

class Scene:
    def __init__(self, name, dur):
        self.name, self.dur, self.inputs, self.fc, self.n, self.last, self.audio, self.voice = name, dur, [], [], 0, None, None, None
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
        if self.audio: afc = f"{self.audio},apad=whole_dur={self.dur},atrim=0:{self.dur}[a]"
        else: afc = f"anullsrc=r=48000:cl=stereo,atrim=0:{self.dur}[a]"  # 그래프 안 소스(별도 lavfi 입력은 스케줄러 교착을 일으킴)
        # 길이는 그래프 안 trim으로 자른다: 출력 -t 는 영상이 끝나는 순간 오디오를 덜 흘린 채 끊어 음성 장면 오디오가 1~4초 짧아졌다(ffmpeg 9)
        fc = ";".join(self.fc + [afc, f"[{self.last}]fps={FPS},format=yuv420p,trim=0:{self.dur}[vo]"])
        run([*self.inputs, "-filter_complex", fc, "-map", "[vo]", "-map", "[a]", *ENC, out])
        return out

def solid(sc):
    sc.fc.append(f"color=c=0x{BG}:s={W}x{H}:r={FPS}:d={sc.dur + 1}[bg]"); sc.base("bg")

def still(sc, img):
    i = sc.add_input(["-loop", "1", "-framerate", str(FPS), "-t", str(sc.dur + 1), "-i", img]); sc.base(f"{i}:v")

def gradient_png(name, top, bottom):
    g = Image.linear_gradient("L").resize((W, H))
    im = Image.composite(Image.new("RGB", (W, H), bottom), Image.new("RGB", (W, H), top), g)
    p = os.path.join(T, name); im.save(p); return p

def endcard_bg():
    """남색 그라데이션 + 오른쪽 아래 로고 워터마크(앱 아이콘 전경에서 배경색을 빼내 22% 투명도로). brand/vertical-bg.png의 구도를 따른다."""
    bg = Image.open(gradient_png("grad.png", (9, 24, 66), (5, 9, 26))).convert("RGBA")
    ic = Image.open(os.path.join(BRAND, "icon-fg.png")).convert("RGBA")
    key = Image.new("RGB", ic.size, ic.getpixel((0, 0))[:3])
    a = ImageChops.difference(ic.convert("RGB"), key).convert("L").point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.GaussianBlur(1))
    ic.putalpha(a.point(lambda v: v * 22 // 100)); ic = ic.resize((1150, 1150), Image.LANCZOS)
    bg.alpha_composite(ic, (90, 860)); p = os.path.join(T, "endbg.png"); bg.convert("RGB").save(p); return p

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

def backdrop(sc, tint=None):
    """기기 장면 배경: 남색→검정 그라데이션"""
    still(sc, gradient_png("bg.png", (13, 20, 40), (8, 9, 14)))

def header(sc, step, label, lines, start=0.3, anim="up", y=225):
    """헤드라인 블록(장식 없음). step/label은 장면 이름표로만 쓴다."""
    p, w, h = text_png(f"hl{step}.png", lines); sc.layer(p, center(w), y, start, anim); return h

def kenburns(sc, img, dark=0.5, zoom_per_frame=0.0006, pan=(0, 0)):
    """느린 줌 + 팬(pan: 프레임당 px). 사진 위 글자 가독성용 어둡기(dark)."""
    i = sc.add_input(["-loop", "1", "-framerate", str(FPS), "-t", str(sc.dur), "-i", img])
    sc.fc.append(f"[{i}:v]scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
                 f"zoompan=z='min(1+{zoom_per_frame}*on,1.3)':x='iw/2-(iw/zoom/2)+{pan[0]}*on':y='ih/2-(ih/zoom/2)+{pan[1]}*on':d=1:s={W}x{H}:fps={FPS},"
                 f"drawbox=x=0:y=0:w={W}:h={H}:color=0x{BG}@{dark}:t=fill[kb]"); sc.base("kb")

def device(sc, foot, start, end, speed, y0, rise=False, audio=False, more=()):
    """more: 이어 붙일 추가 구간 [(start, end, speed), ...]. audio=True면 마지막 구간의 소리를 그 시작 시각에 맞춰 넣는다."""
    mp, _, dw, dh = ASSETS; segs = [(start, end, speed), *more]; parts = []; at = 0.0
    for k, (s0, s1, sp) in enumerate(segs):
        i = sc.add_input(["-ss", str(s0), "-t", str(s1 - s0), "-i", foot])
        sc.fc.append(f"[{i}:v]setpts=(PTS-STARTPTS)/{sp},fps={FPS}[p{k}]"); parts.append(f"[p{k}]")
        if k < len(segs) - 1: at += (s1 - s0) / sp
    m = sc.add_input(["-loop", "1", "-framerate", str(FPS), "-t", str(sc.dur + 1), "-i", mp])
    # 앱 영역에서 상태바(0~100)와 내비바(1280~)를 뺀 가운데 1100x1180만, 둥근 모서리
    sc.fc.append(f"{''.join(parts)}concat=n={len(parts)}:v=1:a=0,crop=1100:1180:303:100,scale={dw}:{dh}[app];[{m}:v]format=gray[mk];[app][mk]alphamerge[dev]")
    cp, M = ASSETS[1]; c = sc.add_input(["-loop", "1", "-framerate", str(FPS), "-t", str(sc.dur + 1), "-i", cp])
    sc.fc.append(f"[{c}:v]format=rgba,fade=t=in:st=0:d=0.3:alpha=1[card];[{sc.last}][card]overlay=x={(W-dw)//2-M}:y='({y_device(y0, rise)})-{M}':eval=frame[cd]")
    sc.fc.append(f"[cd][dev]overlay=x={(W-dw)//2}:y='{y_device(y0, rise)}':eval=frame[dv]"); sc.base("dv")
    if audio:  # 음성은 wav로 먼저 뽑아 별도 입력으로 넣는다: 영상과 같은 mp4 입력에서 바로 쓰면 무거운 그래프에서 오디오가 몇 초 모자란 채 끝난다(ffmpeg 9)
        ch = "[0:a]asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo"
        if at > 0: ch += f"[tts];anullsrc=r=48000:cl=stereo:d={at:.3f}[sil];[sil][tts]concat=n=2:v=0:a=1"  # 마지막 구간 소리를 그 시작 시각까지 무음으로 지연
        wav = os.path.join(T, f"{sc.name}_voice.wav"); s0, s1, _ = segs[-1]
        run(["-ss", str(s0), "-t", str(s1 - s0), "-i", foot, "-filter_complex", f"{ch},apad=whole_dur={sc.dur},atrim=0:{sc.dur}[a]", "-map", "[a]", wav])
        sc.audio = f"[{sc.add_input(['-i', wav])}:a]anull"; sc.voice = wav

def center(w): return "(W-w)/2"  # overlay 식: 팝(가변 폭)에도 가운데 유지

def rect_png(name, w, h, color, radius=None):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), radius if radius is not None else h // 2, fill=color + (255,))
    p = os.path.join(T, name); im.save(p); return p

def glow_png(name, r, color, alpha=255):
    im = Image.new("RGBA", (r * 4, r * 4), (0, 0, 0, 0)); ImageDraw.Draw(im).ellipse((r, r, 3 * r, 3 * r), fill=color + (alpha,))
    im = im.filter(ImageFilter.GaussianBlur(r * 0.6)); p = os.path.join(T, name); im.save(p); return p, r * 4

def speech_windows(wav, gain_db=20, gap=1.2):
    """음성 wav에서 말하는 구간 [(start, end), ...]. 짧은 숨 구간(gap초 미만)은 하나로 합친다."""
    er = subprocess.run(["ffmpeg", "-nostdin", "-i", wav, "-af", f"volume={gain_db}dB,silencedetect=n=-40dB:d=0.3", "-f", "null", "-"], capture_output=True, text=True).stderr
    dur = float(re.search(r"Duration: (\d+):(\d+):([\d.]+)", er).group(3)) + 60 * float(re.search(r"Duration: (\d+):(\d+):([\d.]+)", er).group(2))
    ev = [(k, float(v)) for k, v in re.findall(r"silence_(start|end): ([\d.]+)", er)]
    cur, out = 0.0, []
    for k, t in ev:
        if k == "start":
            if t > cur: out.append([cur, t])
        else: cur = t
    if cur < dur and (not ev or ev[-1][0] == "end"): out.append([cur, dur])
    merged = []
    for a, b in out:
        if merged and a - merged[-1][1] < gap: merged[-1][1] = b
        else: merged.append([a, b])
    return [(a, b) for a, b in merged if b - a > 0.2]

def duck_expr(wins, depth_db=5, down=1.0, up=2.5):
    """음성 구간마다 down초에 걸쳐 depth_db만큼 내려갔다가 끝나면 up초에 걸쳐 되돌아오는 volume 식(사이드체인은 음절마다 펌핑해서 툭툭 끊긴다)."""
    terms = [f"(clip((t-{a - down:.2f})/{down},0,1)*clip(({b + up:.2f}-t)/{up},0,1))" for a, b in wins]
    m = terms[0]
    for t in terms[1:]: m = f"max({m},{t})"
    return f"pow(10,-{depth_db}/20*{m})"

# ---------- 장면 ----------
def build():
    global ASSETS, DY
    ASSETS = device_assets(); F = prep_footage(); scenes = []; trans = []
    NR, NW = os.path.join(BRAND, "night-rest.png"), os.path.join(BRAND, "night-waiting.png")  # 생성 이미지(밤 휴게소 충전 / 차 안에서 폰 알람)
    DY = 480  # 기기 프레임 y (965 높이 → 1445). 아래 300px는 쇼츠 UI가 가리므로 비워 둔다
    line = rect_png("line.png", 520, 8, MINT)

    # 1 훅: 키네틱 텍스트 (팝 오버슈트 → 민트 밑줄이 자라남)
    sc = Scene("s1", 3.6); kenburns(sc, NR, dark=0.35, zoom_per_frame=0.0012, pan=(0.6, 0))
    p, w, h = text_png("h1.png", [("알람", 170, WHITE, True)], shadow=True); sc.layer(p, center(w), 620, 0.1, "pop")
    p, w, h = text_png("h2.png", [("맞추지 마세요.", 120, WHITE, True)], shadow=True); sc.layer(p, center(w), 830, 0.55, "pop")
    p, w, h = text_png("h3.png", [("출발 시각엔 차가 깨워요.", 76, MINT, True)], shadow=True); sc.layer(p, center(w), 1060, 1.7, "up")
    sc.layer(line, center(0), 1180, 2.1, "fade", grow=0.6)
    scenes.append(sc); trans.append("fadeblack")

    # 2 문제: 줄마다 올라오며 등장, 마지막 줄 팝
    sc = Scene("s2", 3.8); kenburns(sc, NW, dark=0.42, pan=(0, -0.5))
    p, w, h = text_png("p1.png", [("충전하는 동안,", 80, WHITE, True)], shadow=True); sc.layer(p, center(w), 640, 0.2, "up")
    p, w, h = text_png("p2.png", [("시트는 손으로 젖히고", 62, WHITE, "medium")], shadow=True); sc.layer(p, center(w), 790, 1.0, "up")
    p, w, h = text_png("p3.png", [("알람은 폰으로 맞추고", 62, WHITE, "medium")], shadow=True); sc.layer(p, center(w), 880, 1.7, "up")
    p, w, h = text_png("p4.png", [("그럴 필요 없어요.", 76, AMBER, True)], shadow=True); sc.layer(p, center(w), 1060, 2.7, "pop")
    scenes.append(sc); trans.append("slideup")

    # 3 해결: 기기 프레임이 튀어오르듯 등장 (A 47–59.5, 2배속)
    sc = Scene("s3", 5.6); backdrop(sc); device(sc, F["A"], 47, 59.5, 2.1, DY, rise=True)
    header(sc, "01", "출발 시각", [("출발 시각만 고르세요", 78, MINT, True)], 0.7, "pop")
    p, w, h = text_png("c3b.png", [("10분 후, 한 번 탭", 46, GRAY, "semibold")]); sc.layer(p, center(w), 350, 1.3, "up")
    scenes.append(sc); trans.append("smoothup")

    # 4 원탭 휴식 + TTS (A 59.5–68.5, 1배속), 칩 3개가 오른쪽에서 차례로
    sc = Scene("s4", 9.0); backdrop(sc); device(sc, F["A"], 59.5, 68.5, 1, DY, audio=True)
    header(sc, "02", "원탭 휴식", [("시트, 조명, 공조", 72, WHITE, True), ("한 번에.", 72, MINT, True)])
    p, w, h = text_png("c4b.png", [("차가 직접 말해요", 48, AMBER, True)]); sc.layer(p, center(w), 1500, 0.6, "up")
    p, w, h = text_png("c4c.png", [("등받이 절반, 조명 낮춤, 공조 22°C", 40, GRAY, "medium")]); sc.layer(p, center(w), 1580, 4.2, "up")
    scenes.append(sc); trans.append("fade")

    # 5 예측 (A 130–178, 9.6배속): 숫자가 65→75로 올라가는 카운터
    sc = Scene("s5", 4.3); backdrop(sc); device(sc, F["A"], 130, 178, 9.6, DY)
    header(sc, "03", "배터리 예측", [("충전 속도로", 56, GRAY, "medium"), ("출발 시 배터리를 예측", 72, WHITE, True)])
    t0, step = 2.4, 0.13
    for k, v in enumerate(range(65, 76)):
        p, w, h = text_png(f"cnt{v}.png", [(f"출발 시 약 {v}%", 64, AMBER, True)])
        en = f"gte(t,{t0 + k * step:.2f})" if v == 75 else f"between(t,{t0 + k * step:.2f},{t0 + (k + 1) * step:.2f})"
        sc.layer(p, center(w), 1540, t0 if k == 0 else 0, "pop" if k == 0 else "fade", enable=en, fade=0.01)
    scenes.append(sc); trans.append("smoothleft")

    # 6 선라이즈 (B 0–33, 4.7배속) + 차오르는 밝기 바와 빛나는 머리
    sc = Scene("s6", 6.4); backdrop(sc, AMBER); device(sc, F["B"], 0, 33, 33 / 6.4, DY)
    header(sc, "04", "선라이즈", [("깨울 때가 되면,", 56, GRAY, "medium"), ("조명을 천천히 밝혀요", 72, WHITE, True)])
    tp = rect_png("track.png", 900, 26, DARK); fp = rect_png("fill.png", 900, 26, AMBER)
    sc.layer(tp, 90, 1530, 0.8); sc.layer(fp, 90, 1530, 1.0, fade=0.05, grow=5.0)
    p, w, h = text_png("c6b.png", [("밝기 10%에서 80%로, 바람은 한 단계 세게", 38, GRAY, "semibold")]); sc.layer(p, center(w), 1590, 1.2, "up")
    scenes.append(sc); trans.append("fade")

    # 7 깨움 + TTS + 복원 (B 33–47, 1배속)
    sc = Scene("s7", 13.6); backdrop(sc); device(sc, F["B"], 33, 47, 1, DY, audio=True)
    header(sc, "05", "깨움과 복원", [("출발 시각에 깨우고,", 72, WHITE, True), ("원래대로.", 72, MINT, True)])
    p, w, h = text_png("c7b.png", [("\"출발 시각입니다. 배터리 72%.\"", 46, AMBER, True)]); sc.layer(p, center(w), 1520, 1.2, "up", end=7.5)
    p, w, h = text_png("c7c.png", [("10초 뒤 시트, 조명, 공조 복원", 50, WHITE, True)]); sc.layer(p, center(w), 1520, 8.0, "up", end=12.3)
    p, w, h = text_png("c7d.png", [("내리기 전 확인까지", 50, AMBER, True)]); sc.layer(p, center(w), 1520, 12.6, "up")
    scenes.append(sc); trans.append("smoothup")

    # 8 학습 (B 80–101.5, 2.8배속 → 두 번째 휴식 시작) + (B 120.6–125.1, 1배속 → 목표 도달, TTS)
    # 두 번째 설정 → "휴식 모드 시작" 탭(≈6.8초) → "계산 중" → 목표 80% 도달 화면과 음성까지 보여 주고 마무리한다
    sc = Scene("s8", 12.2); backdrop(sc); device(sc, F["B"], 80, 101.5, 2.8, DY, audio=True, more=[(120.6, 125.1, 1)])
    header(sc, "06", "학습", [("두 번째부터는", 56, GRAY, "medium"), ("내 차의 속도를 기억", 72, WHITE, True)], 0.2)
    p, w, h = text_png("c8b.png", [("지난 충전 기준 약 15분", 48, AMBER, True)]); sc.layer(p, center(w), 1540, 2.1, "up", end=6.0)
    p, w, h = text_png("c8c.png", [("이번에도 한 번 탭이면 끝.", 48, WHITE, True)]); sc.layer(p, center(w), 1540, 6.6, "up", end=8.3)
    p, w, h = text_png("c8d.png", [("목표에 닿으면 다시 깨워요.", 48, AMBER, True)]); sc.layer(p, center(w), 1540, 8.9, "up")
    scenes.append(sc); trans.append(("fade", 1.0))  # 마지막 전환은 천천히

    # 9 엔드카드: 링이 그려지고 → 링 중앙에 이름 팝 → 슬로건 두 줄 계단식 → 해시태그
    sc = Scene("s9", 4.6); still(sc, endcard_bg())
    CX, CY, R = 540, 600, 400
    rp, rs = ring_seq("ring", R, 14, MINT); sc.layer(rp, CX - rs // 2, CY - rs // 2, 0.2, seq=True)
    p, w, h = text_png("e1.png", [("충전쉼표", 140, WHITE, True), ("Plug & Rest", 46, MINT, "semibold")], shadow=True); sc.layer(p, center(w), f"{CY}-h/2", 1.1, "pop")
    p, w, h = text_png("e2.png", [("충전은 차가,", 84, WHITE, True)], shadow=True); sc.layer(p, center(w), 1140, 1.5, "up")
    p, w, h = text_png("e2b.png", [("휴식은 당신이.", 84, WHITE, True)], shadow=True); sc.layer(p, center(w), 1250, 1.75, "up")
    p, w, h = text_png("e3.png", [("차가 알람이 됩니다.", 52, AMBER, True)], shadow=True); sc.layer(p, center(w), 1420, 2.3, "pop")
    scenes.append(sc)

    files = [s.render() for s in scenes]; durs = [s.dur for s in scenes]
    # 장면 전환: xfade(장면마다 다른 전환) + acrossfade
    inputs = []; [inputs.extend(["-i", f]) for f in files]
    fc, cur, vlast, alast, starts = [], durs[0], "0:v", "0:a", [0.0]
    for k in range(1, len(files)):
        tr, d = trans[k - 1] if isinstance(trans[k - 1], tuple) else (trans[k - 1], XF)
        off = round(cur - d, 3); starts.append(off)
        fc.append(f"[{vlast}][{k}:v]xfade=transition={tr}:duration={d}:offset={off}[xv{k}]")
        fc.append(f"[{alast}][{k}:a]acrossfade=d={d}:c1=tri:c2=tri[xa{k}]")
        vlast, alast, cur = f"xv{k}", f"xa{k}", off + durs[k]
    total = round(cur, 3)
    # 배경음: Mixkit 무료 음원(Stock Music Free License, 저작자 표시 불필요). 기본 551 "Home"(드림팝, 사용자 청취 선택).
    # 대안 97 "Dim The Lights"(칠아웃), 443 "Serene View", 988 "Day Dreamin' with U", 749 "Relaxation 05"(플루트+하프), 419 "Pilates and Yoga"(피아노). BGM_ID=<id>로 지정하면 라우드니스는 자동 측정.
    bid = os.environ.get("BGM_ID", "551")
    bgm = os.path.join(HERE, ".cache", f"mixkit-{bid}.mp3")
    if not os.path.exists(bgm):
        os.makedirs(os.path.dirname(bgm), exist_ok=True)
        subprocess.run(["curl", "-sSL", "-A", "Mozilla/5.0", "-o", bgm, f"https://assets.mixkit.co/music/{bid}/{bid}.mp3"], check=True)
    ss = float(os.environ.get("BGM_SS", {"551": 30}.get(bid, 0)))  # 곡 시작 오프셋(551 "Home"은 앞 30초가 조용한 빌드업)
    pre = "aresample=48000,dynaudnorm=f=3000:g=15:m=10:p=0.9"  # 느린 레벨링: 크레셴도 곡도 배경으로 깔 수 있게 ±3dB 안으로
    er = subprocess.run(["ffmpeg", "-nostdin", "-ss", str(ss), "-t", str(total), "-i", bgm, "-af", f"{pre},ebur128=framelog=quiet", "-f", "null", "-"], capture_output=True, text=True).stderr  # 실제로 쓰는 구간을 같은 체인으로 측정
    lufs = float(re.search(r"I:\s+(-?[\d.]+) LUFS", er).group(1)); print(f"bgm {bid} {lufs} LUFS", file=sys.stderr)
    inputs += ["-ss", str(ss), "-i", bgm]
    m = len(files)
    fc.append(f"[{m}:a]{pre},atrim=0:{total},afade=t=in:d=1.5,afade=t=out:st={total-3.0}:d=3.0,volume={-24 - lufs}dB[mus]")  # 곡은 -24 LUFS로 깔고 음성 구간에서 4~5dB만 덕킹
    fc.append(f"[{alast}]volume=20dB[voice]")  # 에뮬레이터 TTS 원본이 -39.5 LUFS라 +20dB → 약 -19 LUFS
    wins = [(round(st + a, 2), round(st + b, 2)) for sc, st in zip(scenes, starts) if sc.voice for a, b in speech_windows(sc.voice)]
    print("speech", wins, file=sys.stderr)
    fc.append(f"[mus]volume='{duck_expr(wins)}':eval=frame[duck]")  # 음성 1초 전부터 서서히 내려가고 끝나면 2.5초에 걸쳐 복귀
    fc.append(f"[voice][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[ao]")
    run([*inputs, "-filter_complex", ";".join(fc), "-map", f"[{vlast}]", "-map", "[ao]", "-t", str(total), *ENC, "-movflags", "+faststart", OUT])
    print(OUT, total, "s")

if __name__ == "__main__":
    build()
