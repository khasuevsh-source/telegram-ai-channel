#!/usr/bin/env python3
"""Публикует пост из queue/post.json в Telegram. Запускается из GitHub Actions."""
import json
import os
import pathlib
import subprocess
import sys
from datetime import date

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUEUE = ROOT / "queue" / "post.json"
CARD = ROOT / "queue" / "card.png"
LOG = ROOT / "posted-log.md"

if not QUEUE.exists():
    print("queue/post.json нет — публиковать нечего")
    sys.exit(0)

token = os.environ["TELEGRAM_BOT_TOKEN"]
channel = os.environ["TELEGRAM_CHANNEL_ID"]

post = json.loads(QUEUE.read_text(encoding="utf-8"))
text = post["text"]
headline = post.get("headline", "")
rubric = post.get("rubric_label", "AI БЕЗ ВОДЫ")
accent = post.get("accent", "#8B5CF6")

subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "generate-card.py"), headline, str(CARD), rubric, accent],
    check=True,
)

api = f"https://api.telegram.org/bot{token}"
# лимит подписи к фото в Telegram — 1024 символа
caption = text if len(text) <= 1024 else ""

with CARD.open("rb") as photo:
    response = requests.post(
        f"{api}/sendPhoto",
        data={"chat_id": channel, "caption": caption},
        files={"photo": photo},
        timeout=60,
    )
response.raise_for_status()
result = response.json()
if not result.get("ok"):
    raise SystemExit(f"Telegram вернул ошибку: {result}")
message_id = result["result"]["message_id"]

if not caption:
    follow_up = requests.post(
        f"{api}/sendMessage", data={"chat_id": channel, "text": text}, timeout=60
    )
    follow_up.raise_for_status()

with LOG.open("a", encoding="utf-8") as log:
    log.write(f"| {date.today().isoformat()} | {rubric} | {headline} | {message_id} |\n")

QUEUE.unlink()
CARD.unlink(missing_ok=True)
print(f"Опубликовано: message_id={message_id}")
