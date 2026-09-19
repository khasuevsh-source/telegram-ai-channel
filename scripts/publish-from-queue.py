#!/usr/bin/env python3
"""Публикует пост из queue/post.json в Telegram. Запускается из GitHub Actions.

Защита от дублей: право на публикацию захватывается в git ДО отправки в Telegram —
удаление queue/post.json коммитится и пушится первым. Если push не прошёл, значит
очередь забрал параллельный прогон, и этот выходит молча, ничего не отправив.
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from datetime import date

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUEUE = ROOT / "queue" / "post.json"
LOG = ROOT / "posted-log.md"


def git(*args, check=True):
    return subprocess.run(["git", "-C", str(ROOT), *args], check=check, capture_output=True, text=True)


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

git("config", "user.name", "github-actions[bot]")
git("config", "user.email", "github-actions[bot]@users.noreply.github.com")
git("fetch", "origin", "main")
git("reset", "--hard", "origin/main")

if not QUEUE.exists():
    print("очередь уже забрал другой прогон — выходим")
    sys.exit(0)

git("rm", "--quiet", str(QUEUE.relative_to(ROOT)))
git("commit", "--quiet", "-m", f"publish: {headline}")
if git("push", "origin", "HEAD:main", check=False).returncode != 0:
    print("push не прошёл — очередь забрал другой прогон, ничего не отправляем")
    sys.exit(0)

card = pathlib.Path(tempfile.gettempdir()) / "card.png"
subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "generate-card.py"), headline, str(card), rubric, accent],
    check=True,
)

api = f"https://api.telegram.org/bot{token}"
# лимит подписи к фото в Telegram — 1024 символа
caption = text if len(text) <= 1024 else ""

with card.open("rb") as photo:
    response = requests.post(
        f"{api}/sendPhoto",
        data={"chat_id": channel, "caption": caption, "parse_mode": "HTML"},
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
        f"{api}/sendMessage",
        data={"chat_id": channel, "text": text, "parse_mode": "HTML"},
        timeout=60,
    )
    follow_up.raise_for_status()

with LOG.open("a", encoding="utf-8") as log:
    log.write(f"| {date.today().isoformat()} | {rubric} | {headline} | {message_id} |\n")

git("add", "posted-log.md")
git("commit", "--quiet", "-m", f"log: {headline} ({message_id})")
if git("push", "origin", "HEAD:main", check=False).returncode != 0:
    git("fetch", "origin", "main")
    git("rebase", "origin/main")
    git("push", "origin", "HEAD:main")

print(f"Опубликовано: message_id={message_id}")
