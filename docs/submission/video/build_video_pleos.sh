#!/usr/bin/env bash
# Pleos Connect 에뮬레이터 실녹화(raw_pleos_A.webm / raw_pleos_B.webm, 소리 포함)에서
# 시연 영상 demo_pleos_v1.mp4(1920x1080)를 만든다. 숏폼은 build_shortform_v2.py.
# 필요: ffmpeg, swift(macOS 기본). 사용: N_END=<출발 시각 도달 때 배터리 %> ./build_video_pleos.sh
# ponytail: 자막은 render_text.swift가 PNG로 만들어 hstack/vstack으로 붙인다. 배속 구간은 소리를 뺀다(TTS 구간은 모두 1배속).
set -euo pipefail
cd "$(dirname "$0")"
BRAND="$PWD/../../design/brand"
: "${N_END:?출발 시각 도달 때 화면의 배터리 %를 N_END로 지정하세요}"
: "${N_LEARN:?두 번째 설정 화면의 '지난 충전 기준 약 N분' 값을 N_LEARN으로 지정하세요}"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
ENC=(-c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -r 30 -c:a aac -b:a 128k -ar 48000 -ac 2)
BG=0E0F12; W=F5F5F5; G=AAB0B6; M=43E0A0; A=FFC75A
FOOT="시간 단축 데모 / Pleos Connect 에뮬레이터 실녹화 / 음성은 앱 TTS"

# ---------- 1) 자막·카드 PNG ----------
cat > "$T/spec.txt" <<SPEC
title_txt.png|1000|540|none|left|b130,$W,충전쉼표|44,$G,Plug & Rest|b54,$M,충전은 차가, 휴식은 당신이.|30,$A,$FOOT
end.png|1920|1080|$BG|center|b90,$W,충전쉼표 (Plug & Rest)|b48,$A,알람은 차에 맡기세요.|44,$W,① 충전 중 원탭으로 시트, 조명, 공조를 휴식 상태로|44,$W,② 출발 시각이나 목표 배터리에 맞춰 조명을 천천히 밝히고 음성으로 깨움|44,$W,③ 10초 뒤 자동 복원 + 내리기 전 확인|44,$W,④ 두 번째 충전부터 지난 충전 기준으로 바로 예측|34,$M,Pleos Vehicle SDK (EvBattery, Seat, Light, HVAC), TextToSpeech
d1.png|640|1080|$BG|left|b26,$M,STEP 1: 언제 깨울지 고르기|b48,$W,배터리 목표 또는\n출발 시각|28,$G,충전 중(주차 P)일 때만\n'휴식 설정'이 켜집니다.\n\n출발 시각은 5분 단위 휠이나\n10, 30, 60분 후 중에서 고릅니다.|24,$A,$FOOT
d2.png|640|1080|$BG|left|b26,$M,STEP 2: 원탭 휴식|b48,$W,시트, 조명, 공조를\n한 번에|28,$G,등받이 절반, 조명 낮춤, 실내등 끔,\n공조 22°C, 풍량 1단.\n\n차가 직접 말합니다.|26,$A,"출발까지 10분, 편히 쉬세요.\n시간에 맞춰 깨워 드릴게요."|24,$A,$FOOT
d3.png|640|1080|$BG|left|b26,$M,STEP 3: 출발 시 배터리|b48,$W,충전 속도를 보고\n출발 시 배터리 예측|28,$G,처음엔 지난 충전 기준 약 65%,\n실제 오르는 속도가 잡히면\n약 75%로 바꿔 보여 줍니다.\n추측 값은 쓰지 않습니다.|24,$A,$FOOT (5배속)
d4.png|640|1080|$BG|left|b26,$M,STEP 4: 선라이즈 기상|b48,$W,조명을 천천히\n밝혀 깨웁니다|28,$G,출발 전부터 앰비언트 밝기를\n조금씩 올리고 풍량을 한 단계 올립니다.\n알람 대신 해가 뜨듯이.|24,$A,$FOOT (3배속)
d5.png|640|1080|$BG|left|b26,$M,STEP 5: 출발 시각|b48,$W,시각이 되면 깨우고\n전부 원래대로|28,$G,10초 카운트다운 뒤 시트, 조명, 공조를\n복원하고, 내리기 전 확인할 것을\n알려 줍니다.|26,$A,"출발 시각입니다. 배터리 ${N_END}%.\n10초 후 시트를 원래대로 되돌립니다."|24,$A,$FOOT
d6.png|640|1080|$BG|left|b26,$M,STEP 6: 학습|b48,$W,두 번째부터는\n내 차의 속도를 기억|28,$G,설정 화면에 바로\n'지난 충전 기준 약 ${N_LEARN}분'.\n시작 음성에도 예상 시간이 붙습니다.|24,$A,$FOOT
SPEC
swift render_text.swift "$T/spec.txt" "$T"

# 에뮬레이터 webm(가변 프레임, 2560x1440 전체 화면) → 앱 영역(오른쪽 1707px)만 잘라 30fps 고정 mp4
for s in A B; do
  ffmpeg -v error -y -i "raw_pleos_$s.webm" -vf "crop=1707:1440:853:0,fps=30" -c:v libx264 -preset veryfast -crf 16 -c:a aac -b:a 160k -ar 48000 -ac 2 "$T/$s.mp4"
done

# ---------- 2) 조각 ----------
silent() { echo "-f lavfi -i anullsrc=r=48000:cl=stereo"; }
card() { # png 길이 출력
  ffmpeg -v error -y -loop 1 -framerate 30 -t "$2" -i "$T/$1" $(silent) -vf "fade=in:d=0.4,fade=out:st=$(echo "$2-0.4" | bc):d=0.4" -t "$2" "${ENC[@]}" "$3"
}
seg() { # 원본(A|B) 시작 끝 배속 자막png 출력 모드(demo|short)   배속 1 = 소리 유지, 그 외 = 무음
  local src="$T/$1.mp4" s=$2 e=$3 sp=$4 png=$5 out=$6 mode=$7
  local dur; dur=$(echo "($e-$s)/$sp" | bc -l)
  local af; if [ "$sp" = 1 ]; then af="[0:a]asetpts=PTS-STARTPTS[a]"; else af="[0:a]volume=0,asetpts=PTS-STARTPTS,atempo=2,atempo=2[a]"; fi
  if [ "$mode" = demo ]; then
    # 왼쪽 1280x1080 앱 화면 | 오른쪽 640x1080 자막
    ffmpeg -v error -y -ss "$s" -t "$(echo "$e-$s" | bc)" -i "$src" -loop 1 -framerate 30 -i "$T/$png" -filter_complex \
      "[0:v]setpts=(PTS-STARTPTS)/$sp,fps=30,scale=-2:1080,crop=1280:1080[v];[v][1:v]hstack=shortest=1[vo];$af" \
      -map "[vo]" -map "[a]" -t "$dur" "${ENC[@]}" "$out"
  else
    # 위 자막 300 | 앱 화면 가운데 1100x1250만 잘라 1080x1227 (1320 영역 가운데) | 아래 띠 300 = 1080x1920
    ffmpeg -v error -y -ss "$s" -t "$(echo "$e-$s" | bc)" -i "$src" -loop 1 -framerate 30 -i "$T/$png" -loop 1 -framerate 30 -i "$T/s_bot.png" -filter_complex \
      "[0:v]setpts=(PTS-STARTPTS)/$sp,fps=30,crop=1100:1250:303:70,scale=1080:-2,pad=1080:1320:0:(oh-ih)/2:0x$BG[v];[1:v][v][2:v]vstack=3:shortest=1[vo];$af" \
      -map "[vo]" -map "[a]" -t "$dur" "${ENC[@]}" "$out"
  fi
}
bgcard() { local bg=$1 d=$2 out=$3 f=$4; shift 4; local in=(); for p in "$@"; do in+=(-i "$T/$p"); done
  ffmpeg -v error -y -loop 1 -framerate 30 -t "$d" -i "$bg" "${in[@]}" $(silent) -filter_complex "$f,fade=in:d=0.4,fade=out:st=$(echo "$d-0.4" | bc):d=0.4[vo]" -map "[vo]" -map "$(( $# + 1 )):a" -t "$d" "${ENC[@]}" "$out"
}
join() { local out=$1; shift; : > "$T/list.txt"; for f in "$@"; do echo "file '$f'" >> "$T/list.txt"; done
  ffmpeg -v error -y -f concat -safe 0 -i "$T/list.txt" -c copy -movflags +faststart "$out"; }

# ---------- 3) 구간표 (raw 기준 초). 재녹화하면 여기만 고친다 ----------
source ./segments_pleos.env

# ---------- 4) 시연 영상 ----------
bgcard "$BRAND/keyvisual.png" 4 "$T/a0.mp4" "[0:v]scale=1920:-2,crop=1920:1080,format=yuv420p,drawbox=x=60:y=60:w=1000:h=540:color=0x0E0F12@0.55:t=fill[b];[b][1:v]overlay=60:60" title_txt.png
seg A $A_WIZ1_S  $A_WIZ1_E  1 d1.png "$T/a1.mp4" demo   # 홈 → 휴식 설정 → 출발 시각
seg A $A_WIZ2_S  $A_WIZ2_E  1 d1.png "$T/a2.mp4" demo   # 10분 후 → 다음 → 시작 직전
seg A $A_START_S $A_START_E 1 d2.png "$T/a3.mp4" demo   # 시작 + TTS
seg A $A_CALC_S  $A_CALC_E  5 d3.png "$T/a4.mp4" demo   # 계산 중 → 출발 시 약 N%
seg B $B_SUN_S   $B_SUN_E   3 d4.png "$T/a5.mp4" demo   # 선라이즈
seg B $B_WAKE_S  $B_WAKE_E  1 d5.png "$T/a6.mp4" demo   # 출발 TTS + 카운트다운 + 복원 + 확인 카드
seg B $B_LEARN_S $B_LEARN_E 2 d6.png "$T/a7.mp4" demo   # 확인 → 설정에 학습값
seg B $B_S2_S    $B_S2_E    1 d6.png "$T/a8.mp4" demo   # 2회째 시작 TTS(예상 시간)
card end.png 6 "$T/a9.mp4"
join demo_pleos_v1.mp4 "$T"/a{0..9}.mp4

# 숏폼은 build_shortform_v2.py(스토리텔링·모션 버전)가 만든다.

for f in demo_pleos_v1.mp4; do
  printf '%s  ' "$f"; ffprobe -v error -select_streams v -show_entries stream=width,height:format=duration -of csv=p=0 "$f" | tr '\n' ' '; echo
done
