import os
import time
import requests
from typing import Optional


def send_telegram(chat_id: str, text: str, parse_mode: str = "Markdown") -> Optional[dict]:
    """Send a Telegram message with retry and exponential backoff.

    Retries up to 3 times with 2/4/8 second delays as per PRD requirements.

    Args:
        chat_id: Telegram chat/group ID.
        text: Message text.
        parse_mode: Telegram parse mode ("Markdown" or "HTML"). Defaults to Markdown.

    Returns:
        Telegram API response dict, or None on failure.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN not set; skipping Telegram send")
        return None

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }

    delay = 2.0
    for attempt in range(1, 4):
        try:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            print(f"Telegram send failed ({attempt}/3): {exc}")
            if attempt == 3:
                print(f"Failed to send Telegram message after 3 retries: {exc}")
                return None
            time.sleep(delay)
            delay *= 2
