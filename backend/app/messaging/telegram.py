import requests
from app.config import Config
from app.messaging.base import Sender


class TelegramSender(Sender):
    def send(self, identifier: str, text: str) -> dict:
        if not Config.TELEGRAM_BOT_TOKEN:
            return {"ok": False, "detail": "TELEGRAM_BOT_TOKEN not configured"}

        url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
        # Sanity check: Telegram rejects MarkdownV2 messages whose every character
        # is a backslash or whitespace.
        if not isinstance(text, str) or not text.strip():
            return {"ok": False, "detail": "message_text_empty"}
        try:
            resp = requests.post(
                url,
                json={
                    "chat_id": identifier,
                    "text": text,
                    "parse_mode": "MarkdownV2",
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
            body = resp.json()
            if resp.ok and body.get("ok"):
                return {"ok": True, "detail": "sent"}
            return {
                "ok": False,
                "detail": f"telegram_http_{resp.status_code}: {body.get('description', 'no description')}",
            }
        except requests.RequestException as e:
            detail = str(e).replace(url, "Telegram API endpoint")
            detail = detail.replace(Config.TELEGRAM_BOT_TOKEN, "[redacted]")
            return {
                "ok": False,
                "detail": f"telegram_request_error: {type(e).__name__}: {detail}",
            }
