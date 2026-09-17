#!/usr/bin/env bash
# Usage: generate-image.sh GEMINI_API_KEY "prompt text" OUT_FILE
set -euo pipefail

GEMINI_API_KEY="$1"
PROMPT="$2"
OUT_FILE="$3"

STYLE="Стиль: тёмный сине-фиолетовый градиентный фон (#0B1220 -> #1E1B4B), минимализм, чистые линии, современная айти-эстетика, без текста на изображении."
FULL_PROMPT="${PROMPT}. ${STYLE}"

python3 - "$GEMINI_API_KEY" "$FULL_PROMPT" "$OUT_FILE" <<'EOF'
import sys, json, base64, urllib.request

api_key, prompt, out_file = sys.argv[1], sys.argv[2], sys.argv[3]
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={api_key}"
payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req) as resp:
    data = json.load(resp)

parts = data["candidates"][0]["content"]["parts"]
img_part = next(p for p in parts if "inlineData" in p)
img_bytes = base64.b64decode(img_part["inlineData"]["data"])
with open(out_file, "wb") as f:
    f.write(img_bytes)
print(f"Saved: {out_file}")
EOF
