#!/usr/bin/env python3
"""Ежедневный пост целиком на Gemini: поиск повода, текст, иллюстрация, публикация.

Запускается из GitHub Actions по расписанию (.github/workflows/daily-post.yml) и токены
Claude не тратит. Правила для модели — в prompts/gemini-post.md, прошлые посты для
дедупликации — в archive/.
"""
import base64
import datetime
import html
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG = ROOT / "posted-log.md"
ARCHIVE = ROOT / "archive"
PROMPT = ROOT / "prompts" / "gemini-post.md"
GEMINI = "https://generativelanguage.googleapis.com/v1beta/models"


def models(env, default):
    return [m.strip() for m in os.environ.get(env, default).split(",") if m.strip()]


TEXT_MODELS = models(
    "GEMINI_TEXT_MODELS", "gemini-3.8-flash,gemini-3.7-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite"
)
IMAGE_MODELS = models("GEMINI_IMAGE_MODELS", "gemini-3.1-flash-image,gemini-2.5-flash-image")

RUBRICS = {
    0: ("НОВОСТИ НЕДЕЛИ", "🗞", "#22D3EE", "#новости", "главные релизы и обновления AI за последние 7 дней, 2–4 пункта"),
    1: ("ИНСТРУМЕНТ ДНЯ", "🛠", "#8B5CF6", "#инструмент", "разбор одного сервиса: что делает, для кого, цена, честные минусы"),
    2: ("ПРОМПТ НЕДЕЛИ", "💡", "#FBBF24", "#промпт", "готовый универсальный промпт под конкретную задачу — по шаблону «Промпт недели»"),
    3: ("НОВОСТИ НЕДЕЛИ", "🗞", "#22D3EE", "#новости", "главные релизы и обновления AI за последние 7 дней, другие события, чем в понедельник"),
    4: ("КАК СДЕЛАТЬ", "🧭", "#F97316", "#каксделать", "пошаговый разбор конкретной задачи — по шаблону «Как сделать»"),
    5: ("ПОДБОРКА", "📊", "#34D399", "#подборка", "топ-5 инструментов или событий одним постом"),
    6: ("МНЕНИЕ", "🤔", "#EC4899", "#мнение", "сравнение, тренд или «стоит ли того» — короткий авторский разбор"),
}
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
IMAGE_STYLE = (
    "Style: modern editorial tech illustration, dark navy and violet palette with cyan accents, "
    "cinematic lighting, clean composition with empty space in the upper half. "
    "Absolutely no text, letters, numbers, logos or watermarks in the image."
)
MAX_LEN = 1024
ALLOWED_TAGS = ("b", "i", "code")

api_key = os.environ["GEMINI_API_KEY"]
bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
channel = os.environ["TELEGRAM_CHANNEL_ID"]
dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).date()
label, emoji, accent, rubric_tag, rubric_desc = RUBRICS[today.weekday()]


def gemini(model, body):
    response = requests.post(
        f"{GEMINI}/{model}:generateContent",
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=body,
        timeout=240,
    )
    if response.status_code != 200:
        raise RuntimeError(f"{model}: HTTP {response.status_code}: {describe_error(response)}")
    return response.json()


def describe_error(response):
    try:
        error = response.json()["error"]
    except (ValueError, KeyError):
        return response.text[:500]
    reasons = [error.get("status", "")]
    for detail in error.get("details", []):
        for violation in detail.get("violations", []):
            reasons.append(f"{violation.get('quotaId', '')} limit={violation.get('quotaValue', '?')}")
    return " | ".join(r for r in reasons if r) or error.get("message", "")[:300]


def diagnose():
    listing = requests.get(f"{GEMINI}?pageSize=200", headers={"x-goog-api-key": api_key}, timeout=60)
    print(f"список моделей: HTTP {listing.status_code}")
    if listing.ok:
        names = [m["name"].split("/")[-1] for m in listing.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        print("  доступны:", ", ".join(n for n in names if "flash" in n or "image" in n))
    probe = {"contents": [{"parts": [{"text": "Ответь одним словом: ок"}]}]}
    for model in TEXT_MODELS + IMAGE_MODELS:
        for label_, extra in (("без поиска", {}), ("с поиском", {"tools": [{"google_search": {}}]})):
            if model in IMAGE_MODELS and extra:
                continue
            try:
                gemini(model, {**probe, **extra})
                print(f"  {model} {label_}: OK")
            except RuntimeError as err:
                print(f"  {label_}: {err}")


def first_working(model_list, body_for):
    errors = []
    for model in model_list:
        try:
            return model, gemini(model, body_for(model))
        except RuntimeError as err:
            errors.append(str(err))
    raise SystemExit("ни одна модель Gemini не ответила:\n" + "\n".join(errors))


def recent_posts(limit=14):
    files = sorted(ARCHIVE.glob("*.json"), reverse=True)[:limit]
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def sanitize(text):
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I).replace("**", "")
    parts = re.split(r"(</?(?:%s)>)" % "|".join(ALLOWED_TAGS), text)
    out = []
    for part in parts:
        if re.fullmatch(r"</?(?:%s)>" % "|".join(ALLOWED_TAGS), part):
            out.append(part)
        else:
            plain = re.sub(r"<[^>]*>", "", part)
            out.append(html.escape(html.unescape(plain), quote=False))
    return re.sub(r"\n{3,}", "\n\n", "".join(out)).strip()


def problems(post, grounded):
    found = []
    text = post.get("text", "")
    if len(text) > MAX_LEN:
        found.append(f"текст {len(text)} знаков, нужно не больше 1000 — сократи")
    if rubric_tag not in text:
        found.append(f"нет хештега рубрики {rubric_tag} в последней строке")
    if "#новичкам" not in text and "#продвинутым" not in text:
        found.append("нет тега сложности #новичкам или #продвинутым")
    for tag in ALLOWED_TAGS:
        if text.count(f"<{tag}>") != text.count(f"</{tag}>"):
            found.append(f"незакрытый тег <{tag}>")
    if not post.get("headline") or len(post["headline"]) > 50:
        found.append("headline пустой или длиннее 45 знаков")
    if label == "НОВОСТИ НЕДЕЛИ" and not grounded:
        found.append("для новостей обязателен поиск в Google — найди события за последние 7 дней")
    return found


def parse_json(raw):
    block = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.S) or re.search(r"(\{.*\})", raw, re.S)
    if not block:
        raise ValueError("в ответе нет JSON")
    return json.loads(block.group(1))


def write_post():
    history = "\n\n".join(
        f"[{p['date']} · {p['rubric']}] {re.sub(r'<[^>]+>', '', p['text'])}" for p in recent_posts()
    ) or "постов пока нет"
    task = (
        f"Сегодня {today.isoformat()}, {WEEKDAYS[today.weekday()]}.\n"
        f"Рубрика: {emoji} {label} — {rubric_desc}.\n"
        f"Хештег рубрики: {rubric_tag}.\n\n"
        f"Прошлые посты — не повторяй их продукты и события:\n{history}\n\n"
        "Найди повод через поиск и напиши пост по правилам."
    )
    contents = [{"role": "user", "parts": [{"text": task}]}]
    system = {"parts": [{"text": PROMPT.read_text(encoding="utf-8")}]}

    for attempt in range(3):
        model, resp = first_working(
            TEXT_MODELS,
            lambda m: {
                "systemInstruction": system,
                "contents": contents,
                "tools": [{"google_search": {}}],
                "generationConfig": {"temperature": 0.7},
            },
        )
        candidate = resp["candidates"][0]
        raw = "".join(p.get("text", "") for p in candidate["content"]["parts"])
        grounded = bool(candidate.get("groundingMetadata", {}).get("groundingChunks"))
        try:
            post = parse_json(raw)
            post["text"] = sanitize(post.get("text", ""))
            issues = problems(post, grounded)
        except (ValueError, json.JSONDecodeError) as err:
            post, issues = None, [f"ответ не разобрался как JSON: {err}"]
        print(f"попытка {attempt + 1} ({model}): {'ок' if not issues else '; '.join(issues)}")
        if not issues:
            return post
        contents += [
            {"role": "model", "parts": [{"text": raw}]},
            {"role": "user", "parts": [{"text": "Исправь и верни JSON заново:\n- " + "\n- ".join(issues)}]},
        ]
    raise SystemExit("Gemini не написал валидный пост за 3 попытки — публикация пропущена")


def draw_image(prompt, out):
    def body(model, with_ratio=True):
        config = {"responseModalities": ["IMAGE"]}
        if with_ratio:
            config["imageConfig"] = {"aspectRatio": "1:1"}
        return {"contents": [{"parts": [{"text": f"{prompt}\n\n{IMAGE_STYLE}"}]}], "generationConfig": config}

    for model in IMAGE_MODELS:
        for with_ratio in (True, False):
            try:
                resp = gemini(model, body(model, with_ratio))
            except RuntimeError as err:
                print("картинка:", err)
                continue
            for part in resp.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                data = part.get("inlineData") or part.get("inline_data")
                if data:
                    out.write_bytes(base64.b64decode(data["data"]))
                    print(f"картинка: {model}")
                    return True
    return False


if dry_run:
    diagnose()
post = write_post()
tmp = pathlib.Path(tempfile.gettempdir())
background, card = tmp / "gemini-bg.png", tmp / "card.png"
card_args = [sys.executable, str(ROOT / "scripts" / "generate-card.py"), post["headline"], str(card), label, accent]
if draw_image(post.get("image_prompt", post["headline"]), background):
    card_args.append(str(background))
else:
    print("картинка от Gemini не получилась — рисую фирменную карточку без неё")
subprocess.run(card_args, check=True)

print("\n" + post["text"] + "\n")
if dry_run:
    print("DRY_RUN: в канал не отправляю")
    sys.exit(0)

telegram = f"https://api.telegram.org/bot{bot_token}"
with card.open("rb") as photo:
    sent = requests.post(
        f"{telegram}/sendPhoto",
        data={"chat_id": channel, "caption": post["text"], "parse_mode": "HTML"},
        files={"photo": photo},
        timeout=60,
    ).json()
if not sent.get("ok"):
    # запасной путь: Telegram не принял разметку — отправляем тем же текстом без тегов
    print("Telegram отклонил HTML:", sent.get("description"))
    with card.open("rb") as photo:
        sent = requests.post(
            f"{telegram}/sendPhoto",
            data={"chat_id": channel, "caption": html.unescape(re.sub(r"<[^>]+>", "", post["text"]))},
            files={"photo": photo},
            timeout=60,
        ).json()
if not sent.get("ok"):
    raise SystemExit(f"Telegram вернул ошибку: {sent}")
message_id = sent["result"]["message_id"]

ARCHIVE.mkdir(exist_ok=True)
(ARCHIVE / f"{today.isoformat()}-{message_id}.json").write_text(
    json.dumps(
        {
            "date": today.isoformat(),
            "rubric": label,
            "headline": post["headline"],
            "text": post["text"],
            "sources": post.get("sources", []),
            "message_id": message_id,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
with LOG.open("a", encoding="utf-8") as log:
    log.write(f"| {today.isoformat()} | {label} | {post['headline']} | {message_id} |\n")
print(f"Опубликовано: message_id={message_id}")
