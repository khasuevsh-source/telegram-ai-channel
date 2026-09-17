#!/usr/bin/env bash
# Usage: send-telegram-post.sh BOT_TOKEN CHANNEL_ID [IMAGE_PATH] CAPTION
# If IMAGE_PATH is empty or missing, sends plain text instead of a photo.
set -euo pipefail

BOT_TOKEN="$1"
CHANNEL_ID="$2"
IMAGE_PATH="$3"
CAPTION="$4"

if [ -n "$IMAGE_PATH" ] && [ -f "$IMAGE_PATH" ]; then
  curl -sS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendPhoto" \
    --form-string "chat_id=${CHANNEL_ID}" \
    --form-string "caption=${CAPTION}" \
    -F "photo=@${IMAGE_PATH}"
else
  curl -sS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -d "chat_id=${CHANNEL_ID}" \
    --data-urlencode "text=${CAPTION}"
fi
