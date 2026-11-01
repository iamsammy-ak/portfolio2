#!/usr/bin/env bash
# Photographs each card in tools/story-cards.html with headless Chrome and writes assets/story/*.webp.
set -e
cd "$(dirname "$0")/.."
CHROME="${CHROME:-C:/Program Files/Google/Chrome/Application/chrome.exe}"
NAMES=(2022-polito 2022-aiesec 2023-fibzio 2023-pisa 2024-fisu 2025-opensky 2025-msc 2026-hackathons)
SIZES=(800,1000 1280,720 1280,720 800,1000 1280,720 1280,720 800,1000 1080,480)
mkdir -p assets/story tools/.shots
for i in "${!NAMES[@]}"; do
  png="tools/.shots/${NAMES[$i]}.png"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 --window-size="${SIZES[$i]}" --virtual-time-budget=2500 \
    --screenshot="$(cygpath -w "$PWD/$png")" "file:///$(cygpath -m "$PWD/tools/story-cards.html")#$i" 2>/dev/null
  python -c "from PIL import Image; im=Image.open('$png').convert('RGB'); im.save('assets/story/${NAMES[$i]}.webp', quality=88, method=6); print('$png', im.size)"
done
