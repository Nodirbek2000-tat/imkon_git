"""
Telegram Bot API bilan ishlash.

`sms.py`ga o'xshab — tashqi provayder bilan aloqa shu yerda izolyatsiya
qilingan. Alohida kutubxona (`python-telegram-bot`/`aiogram`) qo'shilmadi —
ular asinxron va har bir ORM chaqiruvini `sync_to_async` bilan o'rashni
talab qiladi. Bizga kerak bo'lgan uchta metod (`getUpdates`, `sendMessage`,
kontakt so'rash tugmasi) uchun oddiy `requests` yetarli.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(Exception):
    pass


def _call(method: str, **params) -> dict:
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        raise TelegramError("TELEGRAM_BOT_TOKEN sozlanmagan.")

    url = API_BASE.format(token=token, method=method)
    try:
        response = requests.post(url, json=params, timeout=35)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise TelegramError(f"Telegram API xatosi ({method}): {exc}") from exc

    data = response.json()
    if not data.get("ok"):
        raise TelegramError(f"Telegram API rad etdi ({method}): {data}")
    return data["result"]


def get_updates(offset: int | None = None, timeout: int = 30) -> list[dict]:
    """Long-polling — `timeout` soniya kutadi, yangi update kelsa darrov qaytadi."""
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    return _call("getUpdates", **params)


def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    params = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        params["reply_markup"] = reply_markup
    _call("sendMessage", **params)


def request_contact_keyboard() -> dict:
    """Telegram'ning o'z 'kontakt yuborish' tugmasi — raqam Telegram tomonidan tasdiqlangan."""
    return {
        "keyboard": [[{"text": "Telefon raqamni yuborish", "request_contact": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }
