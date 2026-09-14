"""
SMS yuborish.

Eskiz.uz sozlanmagan bo'lsa (`.env` da ESKIZ_EMAIL bo'sh) — kod konsolga
chiqariladi. Shu bilan development'da haqiqiy SMS sarflanmaydi va
frontend'ni to'liq sinash mumkin.
"""

import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

ESKIZ_BASE = "https://notify.eskiz.uz/api"
TOKEN_CACHE_KEY = "eskiz:token"
TOKEN_TTL = 60 * 60 * 24 * 25  # token ~30 kun yashaydi, ehtiyot uchun 25


class SMSError(Exception):
    pass


def _is_configured() -> bool:
    return bool(settings.ESKIZ_EMAIL and settings.ESKIZ_PASSWORD)


def _get_token() -> str:
    token = cache.get(TOKEN_CACHE_KEY)
    if token:
        return token

    response = requests.post(
        f"{ESKIZ_BASE}/auth/login",
        data={"email": settings.ESKIZ_EMAIL, "password": settings.ESKIZ_PASSWORD},
        timeout=10,
    )
    response.raise_for_status()
    token = response.json()["data"]["token"]
    cache.set(TOKEN_CACHE_KEY, token, TOKEN_TTL)
    return token


def send_sms(phone: str, text: str) -> bool:
    """
    Xabar yuboradi. Provayder sozlanmagan bo'lsa log'ga yozadi va True qaytaradi.
    Xato bo'lsa SMSError ko'taradi — view uni ushlab foydalanuvchiga xabar beradi.
    """
    if not _is_configured():
        # ASCII only: Windows konsoli (cp866/cp1251) emoji'da UnicodeEncodeError beradi
        logger.warning("SMS (provayder sozlanmagan) -> %s: %s", phone, text)
        print(f"\n  [SMS] {phone}\n  {text}\n", flush=True)
        return True

    try:
        response = requests.post(
            f"{ESKIZ_BASE}/message/sms/send",
            headers={"Authorization": f"Bearer {_get_token()}"},
            data={
                "mobile_phone": phone.lstrip("+"),
                "message": text,
                "from": settings.ESKIZ_FROM,
            },
            timeout=10,
        )
        if response.status_code == 401:
            # Token eskirgan — tozalab bir marta qayta urinamiz
            cache.delete(TOKEN_CACHE_KEY)
            response = requests.post(
                f"{ESKIZ_BASE}/message/sms/send",
                headers={"Authorization": f"Bearer {_get_token()}"},
                data={
                    "mobile_phone": phone.lstrip("+"),
                    "message": text,
                    "from": settings.ESKIZ_FROM,
                },
                timeout=10,
            )

        response.raise_for_status()
        return True

    except requests.RequestException as exc:
        logger.exception("SMS yuborilmadi: %s", phone)
        raise SMSError("SMS yuborishda xatolik. Birozdan keyin urinib ko'ring.") from exc


def send_otp(phone: str, code: str) -> bool:
    return send_sms(phone, f"Imkon: tasdiqlash kodi {code}. Hech kimga bermang.")
