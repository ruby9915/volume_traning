#!/usr/bin/env bash
# fdd.py 가 만든 fddN.html 을 설치된 Edge(headless)로 찍어 fddN.png(2배율)로 저장한다.
# usage: bash shots.sh <work_dir>      (Git Bash)
set -uo pipefail
work="$1"
edge="/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
winwork="$(cygpath -m "$(cd "$work" && pwd)")"
profile="$winwork/edge-profile"   # 사용 중인 Edge 프로필과 섞이지 않게 따로 둔다
i=1
while read -r w h; do
  [ -z "$w" ] && continue
  "$edge" --headless=new --disable-gpu --no-first-run --user-data-dir="$profile" \
    --hide-scrollbars --force-device-scale-factor=2 --window-size="$w,$h" \
    --screenshot="$winwork/fdd$i.png" "file:///$winwork/fdd$i.html" >/dev/null 2>&1
  echo "fdd$i.png ${w}x${h}"
  i=$((i + 1))
done < <(tr -d '\r' < "$work/fdd_sizes.txt"; echo)
