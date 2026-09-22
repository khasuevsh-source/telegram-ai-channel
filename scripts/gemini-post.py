#!/usr/bin/env python3
"""Ежедневный пост целиком на Gemini: свежие новости из RSS, текст, публикация.

Запускается из GitHub Actions по расписанию (.github/workflows/daily-post.yml) и токены
Claude не тратит. Правила для модели — в prompts/gemini-post.md, прошлые посты для
дедупликации — в archive/.

Почему RSS, а не поиск Google внутри Gemini: у бесплатного тарифа квота на поиск и на
генерацию картинок нулевая (проверено 2026-09-22, HTTP 429 RESOURCE_EXHAUSTED). Ленты
к тому же дают точную дату публикации — старое за новое модель подать не сможет.
"""
import base64
import datetime
import email.utils
import html
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET

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
# Пусто по умолчанию: картинок в бесплатном тарифе нет. После подключения оплаты в Google
# вписать сюда, например, "gemini-3.1-flash-image,gemini-2.5-flash-image".
IMAGE_MODELS = models("GEMINI_IMAGE_MODELS", "")


def news_query(q, lang):
    region = {"ru": "hl=ru&gl=RU&ceid=RU:ru", "en": "hl=en-US&gl=US&ceid=US:en"}[lang]
    return f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&{region}"


FEEDS = [
    ("Google News", news_query("нейросеть OR «искусственный интеллект» OR ChatGPT when:7d", "ru")),
    ("Google News", news_query("AI model OR chatbot OR OpenAI OR Anthropic OR Gemini OR DeepSeek when:7d", "en")),
    ("TechCrunch", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("VentureBeat", "https://venturebeat.com/category/ai/feed/"),
    ("Ars Technica", "https://arstechnica.com/ai/feed/"),
    ("The Verge", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("OpenAI", "https://openai.com/news/rss.xml"),
    ("Google", "https://blog.google/technology/ai/rss/"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml"),
    ("Хабр", "https://habr.com/ru/rss/hub/artificial_intelligence/all/"),
]

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
PER_FEED = 8

api_key = os.environ["GEMINI_API_KEY"]
bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
channel = os.environ["TELEGRAM_CHANNEL_ID"]
dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
if not dry_run and not bot_token:
    raise SystemExit("секрет TELEGRAM_BOT_TOKEN пустой — добавьте его в Settings → Secrets → Actions")

now = datetime.datetime.now(datetime.timezone.utc)
today = now.astimezone(datetime.timezone(datetime.timedelta(hours=3))).date()
label, emoji, accent, rubric_tag, rubric_desc = RUBRICS[today.weekday()]
is_news = label == "НОВОСТИ НЕДЕЛИ"


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
            reasons.append(violation.get("quotaId", ""))
    return " | ".join(r for r in reasons if r) or error.get("message", "")[:300]


def first_working(model_list, body):
    errors = []
    for model in model_list:
        try:
            return model, gemini(model, body)
        except RuntimeError as err:
            errors.append(str(err))
    raise SystemExit("ни одна модель Gemini не ответила:\n" + "\n".join(errors))


def parse_date(value):
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.timezone.utc)


def clean(text, limit):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def fetch_news(max_age_days):
    items, seen = [], set()
    for source, url in FEEDS:
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (ai-bez-vody bot)"})
            root = ET.fromstring(resp.content)
        except requests.RequestException as err:
            print(f"лента {source}: не загрузилась ({err.__class__.__name__})")
            continue
        except ET.ParseError:
            print(f"лента {source}: не RSS (HTTP {resp.status_code}, {resp.headers.get('Content-Type', '?')})")
            continue
        entries = root.iter("item") if root.find(".//item") is not None else root.iter("{http://www.w3.org/2005/Atom}entry")
        feed_items = []
        for entry in entries:
            def field(*names):
                for name in names:
                    node = entry.find(name)
                    if node is not None:
                        return node.get("href") if name.endswith("link") and node.get("href") else (node.text or "")
                return ""

            atom = "{http://www.w3.org/2005/Atom}"
            title = clean(field("title", f"{atom}title"), 200)
            published = parse_date(field("pubDate", f"{atom}published", f"{atom}updated"))
            if not title or not published or (now - published).days > max_age_days:
                continue
            key = re.sub(r"\W+", "", title.lower())[:60]
            if key in seen:
                continue
            seen.add(key)
            outlet = source
            if source == "Google News" and " - " in title:
                title, outlet = title.rsplit(" - ", 1)
            feed_items.append({
                "title": title,
                "outlet": outlet,
                "date": published.date().isoformat(),
                "summary": clean(field("description", f"{atom}summary", f"{atom}content"), 240),
                "link": field("link", f"{atom}link"),
            })
        # не больше 8 с ленты: иначе поток региональных заметок из Google News
        # вытесняет профильные издания
        feed_items.sort(key=lambda i: i["date"], reverse=True)
        items += feed_items[:PER_FEED]
        print(f"лента {source}: {len(feed_items)} свежих, берём {min(len(feed_items), PER_FEED)}")
    items.sort(key=lambda i: i["date"], reverse=True)
    return items


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


def problems(post, news):
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
    sources = post.get("sources", [])
    if any(not isinstance(s, int) or not 1 <= s <= len(news) for s in sources):
        found.append(f"sources — только номера материалов из списка, от 1 до {len(news)}")
    elif is_news and not sources:
        found.append("для новостей укажи в sources номера материалов из списка, на которых основан пост")
    return found


def parse_json(raw):
    block = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.S) or re.search(r"(\{.*\})", raw, re.S)
    if not block:
        raise ValueError("в ответе нет JSON")
    return json.loads(block.group(1))


def write_post(news):
    history = "\n\n".join(
        f"[{p['date']} · {p['rubric']}] {re.sub(r'<[^>]+>', '', p['text'])}" for p in recent_posts()
    ) or "постов пока нет"
    materials = "\n".join(
        f"{n}. [{i['date']} · {i['outlet']}] {i['title']}" + (f" — {i['summary']}" if i["summary"] else "")
        for n, i in enumerate(news, 1)
    ) or "свежих материалов нет"
    task = (
        f"Сегодня {today.isoformat()}, {WEEKDAYS[today.weekday()]}.\n"
        f"Рубрика: {emoji} {label} — {rubric_desc}.\n"
        f"Хештег рубрики: {rubric_tag}.\n\n"
        f"Свежие материалы (номер, дата публикации, издание, заголовок):\n{materials}\n\n"
        f"Прошлые посты — не повторяй их продукты и события:\n{history}\n\n"
        "Напиши пост по правилам."
    )
    contents = [{"role": "user", "parts": [{"text": task}]}]
    system = {"parts": [{"text": PROMPT.read_text(encoding="utf-8")}]}

    for attempt in range(3):
        model, resp = first_working(
            TEXT_MODELS,
            {"systemInstruction": system, "contents": contents, "generationConfig": {"temperature": 0.7}},
        )
        raw = "".join(p.get("text", "") for p in resp["candidates"][0]["content"]["parts"])
        try:
            post = parse_json(raw)
            post["text"] = sanitize(post.get("text", ""))
            issues = problems(post, news)
        except (ValueError, json.JSONDecodeError) as err:
            post, issues = None, [f"ответ не разобрался как JSON: {err}"]
        print(f"попытка {attempt + 1} ({model}): {'ок' if not issues else '; '.join(issues)}")
        if not issues:
            post["sources"] = [{"url": news[s - 1]["link"], "date": news[s - 1]["date"], "outlet": news[s - 1]["outlet"]}
                               for s in post.get("sources", [])]
            return post
        contents += [
            {"role": "model", "parts": [{"text": raw}]},
            {"role": "user", "parts": [{"text": "Исправь и верни JSON заново:\n- " + "\n- ".join(issues)}]},
        ]
    raise SystemExit("Gemini не написал валидный пост за 3 попытки — публикация пропущена")


def draw_image(prompt, out):
    for model in IMAGE_MODELS:
        body = {
            "contents": [{"parts": [{"text": f"{prompt}\n\n{IMAGE_STYLE}"}]}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "1:1"}},
        }
        try:
            resp = gemini(model, body)
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


news = fetch_news(7 if is_news else 14)
print(f"материалов в работу: {len(news)}")
if is_news and len(news) < 3:
    raise SystemExit("свежих новостей почти нет — лучше пропустить день, чем пересказывать старое")

post = write_post(news)
tmp = pathlib.Path(tempfile.gettempdir())
background, card = tmp / "gemini-bg.png", tmp / "card.png"
card_args = [sys.executable, str(ROOT / "scripts" / "generate-card.py"), post["headline"], str(card), label, accent]
if IMAGE_MODELS and draw_image(post.get("image_prompt", post["headline"]), background):
    card_args.append(str(background))
subprocess.run(card_args, check=True)

print("\n" + post["text"] + "\n")
print("источники:", json.dumps(post["sources"], ensure_ascii=False))
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
            "sources": post["sources"],
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
