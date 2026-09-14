"""
Google orqali kirish.

Frontend Google'dan ID token oladi va shu yerga yuboradi. Biz tokenni
Google'ning o'z kalitlari bilan tekshiramiz — mijozdan kelgan `email` yoki
`user_id` ga ishonmaymiz, aks holda kimdir istalgan akkauntga kira olardi.
"""

import logging

from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

logger = logging.getLogger(__name__)


class GoogleAuthError(Exception):
    pass


def verify_google_token(token: str) -> dict:
    """
    ID tokenni tekshiradi va profil ma'lumotini qaytaradi.

    Qaytadi: {"google_id", "email", "full_name", "picture", "email_verified"}
    """
    client_id = settings.GOOGLE_CLIENT_ID
    if not client_id:
        raise GoogleAuthError("Google orqali kirish sozlanmagan.")

    try:
        payload = id_token.verify_oauth2_token(
            token, google_requests.Request(), client_id
        )
    except ValueError as exc:
        logger.warning("Google token rad etildi: %s", exc)
        raise GoogleAuthError("Google tokeni yaroqsiz yoki muddati tugagan.") from exc

    # Tokenni kim bergani ham tekshiriladi — soxta emitent o'tib ketmasin
    if payload.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise GoogleAuthError("Token noma'lum manbadan.")

    if not payload.get("email_verified", False):
        raise GoogleAuthError("Google akkauntingiz email tasdiqlanmagan.")

    return {
        "google_id": payload["sub"],
        "email": payload.get("email", ""),
        "full_name": payload.get("name", ""),
        "picture": payload.get("picture", ""),
    }
