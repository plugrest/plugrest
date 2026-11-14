# Pleos 에뮬레이터 실녹화 대본 (OBS, TTS 포함, 약 3분)

## 준비 (녹화 전)
1. 에뮬레이터 실행: `emulator -avd Pleos_Connect_v2_1 -no-snapshot -no-boot-anim -gpu host -cores 4 -memory 8192 -no-metrics`
2. 앱 설치: `adb install -r app/build/outputs/apk/debug/PlugRest-debug.apk` (데모 모드 빌드: 계산 중 20초, 선라이즈 30초)
3. 포트 포워드: `adb forward tcp:8088 tcp:8088` → 브라우저로 http://127.0.0.1:8088 열어 두기(Virtual Console. 열려 있어야 REST가 살아 있음)
4. OBS: 소스 = 에뮬레이터 창(앱 영역만 크롭), 오디오 = 시스템 오디오(TTS). 해상도 1920×1080, 30fps
5. Virtual Console 초기값: Gear **Park**, Battery SOC **50**, Charge Port **Open**, Charge Switch **ON**, 창문 FR **40**(하차 체크용), 뒷좌석 왼쪽 착좌 **ON**

아래 `vc` 명령은 터미널에서 바로 쳐도 된다(콘솔 브라우저 탭이 열려 있을 때만 동작):
```
vc(){ curl -s -o /dev/null -X POST "http://127.0.0.1:8088$1"; }
vc "/vehicle/gear?gear=Park"; vc "/vehicle/ev-battery?field=soc&value=50"
vc "/vehicle/ev-battery?field=charge_port_open&value=true"; vc "/vehicle/ev-battery?field=charge_switch&value=true"
vc "/vehicle/body?window_fr=40"; vc "/vehicle/seat?kind=occupied&area=rear_left&value=true"
```

## 녹화 순서
| 시각 | 화면 조작 | Virtual Console | 보이는 것 |
|---|---|---|---|
| 0:00 | 앱 실행 | (초기값) | 홈: "충전 중 · 기어 P" 뱃지, 50% 링, "휴식 설정" 활성 |
| 0:10 | 휴식 설정 → **출발 시각** → 다음 | | 1/3 "언제 깨워 드릴까요?" |
| 0:20 | 휠로 **현재+2분** 맞춤(데모 하한 1분) → 다음 | | 2/3 "언제 출발하세요?" 휠·프리셋 |
| 0:30 | 통풍 **끔** → 휴식 모드 시작 | | 3/3 요약 뱃지 → TTS "출발까지 2분, 편히 쉬세요…" |
| 0:35 | 가만히 | 콘솔에서 시트 리클라인 팝업·앰비언트 10%·HVAC 22°C 확인 | "HH:MM에 깨워 드려요", 남은 시간 바, 상태 뱃지 2줄 |
| 0:50 | | SOC 50→55→60 (15초마다 +1씩 올리거나 슬라이더) | "출발 시 배터리 약 N%" |
| 1:30 | | 콘솔 앰비언트 밝기 카드 보기 | "곧 깨워 드려요", 조명 밝아짐·풍량 2단 |
| 2:00 | | | TTS "출발 시각입니다. 배터리 N%…" → 10초 카운트다운 |
| 2:12 | | 콘솔에서 시트·조명 복원 확인 | "원래대로 돌려놨어요" + 주의 카드(조수석 창문 열림 / 뒷좌석 탑승자) |
| 2:25 | 확인 | | 홈 |
| 2:30 | 휴식 설정 → 목표 배터리 → 다음 | | 2/3에 "지난 충전 기준 약 N분" 학습값 |
| 2:40 | 80% → 다음 → 시작 | SOC 50 | "계산 중" + "지난 충전 기준 약 N분" |
| 3:00 | 종료 | | 끝 |

## 멘트(자막 또는 내레이션)
- 0:00 "충전을 시작하면 차가 알아서 알아챕니다."
- 0:20 "출발할 시각만 정하면 됩니다."
- 0:35 "시트가 젖혀지고, 조명이 낮아지고, 공조가 맞춰집니다."
- 1:30 "출발 전엔 조명이 천천히 밝아집니다. 알람 대신 해가 뜨듯이."
- 2:00 "시각이 되면 깨우고, 전부 원래대로."
- 2:12 "내리기 전에 확인할 것도 알려 줍니다."
- 2:30 "두 번째부터는 내 차의 충전 속도를 기억합니다."
- 하단 고정 자막: "시간 단축 데모 · Pleos Connect 에뮬레이터 v2.1 실녹화"

## 녹화 후
- 2026-11-14 실제 녹화는 OBS 대신 **에뮬레이터 콘솔의 `screenrecord`**(소리 포함 webm, 최대 180초)로 두 구간(`raw_pleos_A.webm` 설정→휴식 시작, `raw_pleos_B.webm` 선라이즈→깨움→학습값)을 찍었다. 화면 조작은 `adb shell input tap` 좌표로 자동화(출발 시각은 "10분 후" 프리셋, SOC는 30초마다 +1%).
  - scrcpy의 기기 오디오 캡처는 Pleos 온디바이스 TTS를 잡지 못한다(무음). 에뮬레이터 콘솔 녹화만 TTS가 들어간다.
  - 콘솔 녹화 중에는 `uiautomator dump`가 실패하므로 텍스트 기반 탭 대신 좌표 탭을 쓴다.
- 원본(gitignore 대상)에서 `N_END=72 N_LEARN=15 ./build_video_pleos.sh` → `demo_pleos_v1.mp4`(1920×1080, 약 2분)와 `shortform_pleos_v1.mp4`(1080×1920, 60초 이내). 구간표는 `segments_pleos.env`.
