"""docs/design/screenshots/*.png -> docs/submission/화면시안_충전쉼표.pdf (표지 + 화면당 1장, 설명 1줄).
실행: cd docs && /usr/bin/python3 submission/build_mockup_pdf.py "$PWD"   (Pillow 필요)
재촬영 시 파일명이 바뀌면 SHOTS만 고친다. 설명은 실제 화면을 보고 맞춘 문장이다."""
import sys
from PIL import Image, ImageDraw, ImageFont

D = sys.argv[1]
APP = "충전쉼표 (Plug & Rest)"
ONE_LINER = ("출발 시각이나 목표 배터리에 맞춰 차가 운전자를 깨우는 Pleos Connect 앱.",
             "충전 대기 중 시트·조명·공조를 원탭으로 휴식 상태로 바꾸고, 조명을 서서히 밝혀 깨운 뒤 원래대로 되돌린다")
SHOTS = [
    ("01-home.png", "홈 — 충전 중·기어 P를 확인하면 '휴식 설정'이 켜진다. 상단 상태 뱃지 / 가운데 배터리 링 / 하단 버튼 하나"),
    ("02-step1-mode.png", "설정 1/3 — '언제 깨워 드릴까요?' 목표 배터리 또는 출발 시각. 화면마다 질문 하나, 큰 카드 두 장"),
    ("03-step2-target.png", "설정 2/3 — 목표 배터리는 현재 잔량보다 높은 값만 라디오로. 두 번째 충전부터 '지난 충전 기준 약 N분'"),
    ("04-step2-depart.png", "설정 2/3 — 출발 시각은 시·분 휠(5분 단위) 또는 10/30/60분 후 프리셋. 현재 시각 이전은 잠김"),
    ("05-step3-vent.png", "설정 3/3 — 통풍 시트 켤지 고르고 요약 뱃지 확인 후 '휴식 모드 시작'"),
    ("06-resting-calc.png", "휴식 시작 — 시트·조명·공조를 한 번에 바꾸고 상태를 뱃지로. 남은 시간은 실측 전까지 '계산 중'"),
    ("07-resting-remaining.png", "휴식 중(배터리 모드) — 실측 충전 속도로 남은 시간을 분으로. 링에 목표 구간이 옅게 깔리고 차오른다"),
    ("08-resting-depart.png", "휴식 중(출발 시각 모드) — 'HH:MM에 깨워 드려요'와 줄어드는 남은 시간 바, 출발 시 예상 배터리"),
    ("09-sunrise.png", "선라이즈 기상 — 종료 전 조명이 천천히 밝아지고 풍량 2단, '곧 깨워 드려요'"),
    ("10-restoring.png", "도달 — 음성 안내 후 10초 카운트다운. '취소'하면 지금 상태 그대로"),
    ("11-done.png", "휴식 끝 — 원래대로 복원한 결과 뱃지와 '내리기 전 확인' 주의 카드(뒷좌석 탑승자·조수석 창문 열림)"),
]
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"  # ponytail: macOS 전용 한글 폰트 경로
W, H, M = 1240, 1754, 80  # A4 세로 150dpi
f = lambda size: ImageFont.truetype(FONT, size)

# 표지: keyvisual을 하단에 깔고, 그 위 단색 남색 영역에 글자를 올린다(이미지 위에 글자를 겹치지 않아 가독성 확보)
kv = Image.open(f"{D}/design/brand/keyvisual.png").convert("RGB")
kv = kv.resize((W, round(kv.height * W / kv.width)))
cover = Image.new("RGB", (W, H), kv.getpixel((10, 10)))
cover.paste(kv, (0, H - kv.height - 140))
d = ImageDraw.Draw(cover)
d.text((M, 260), APP, font=f(72), fill="white")
d.text((M, 380), "화면 시안", font=f(44), fill=(255, 199, 90))  # 앰버 #FFC75A
for i, line in enumerate(ONE_LINER):
    d.text((M, 500 + i * 44), line, font=f(28), fill=(220, 226, 240))
d.text((M, H - M - 40), "Pleos Connect 에뮬레이터 v2.1 실화면 캡처 · 시간 단축 데모 모드", font=f(24), fill=(170, 180, 205))
pages = [cover]

for n, (name, cap) in enumerate(SHOTS, 1):
    shot = Image.open(f"{D}/design/screenshots/{name}").convert("RGB")
    if shot.width == 2560: shot = shot.crop((853, 0, 2560, 1440))  # Pleos 2-window 캡처 → 앱 영역만
    page = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(page)
    d.text((M, M - 20), f"{n}/{len(SHOTS)}", font=f(32), fill=(90, 90, 90))
    shot.thumbnail((W - 2 * M, H - 2 * M - 160))
    page.paste(shot, ((W - shot.width) // 2, M + 40))
    d.text((M, H - M - 50), cap, font=f(26), fill=(30, 30, 30))
    pages.append(page)

out = f"{D}/submission/화면시안_충전쉼표.pdf"
pages[0].save(out, save_all=True, append_images=pages[1:], resolution=150)
print("saved", out, len(pages), "pages")
