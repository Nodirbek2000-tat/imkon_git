from django.conf import settings
from rest_framework import permissions


class IsArtisan(permissions.BasePermission):
    """
    Faqat arizasi tasdiqlangan hunarmand.

    `is_staff` bilan aralashtirilmaydi: bu bozordagi maqom (mahsulot qo'yish
    huquqi), admin huquqi emas.
    """

    message = "Bu amal faqat hunarmandlar uchun."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and getattr(user, "is_artisan", False)
        )


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    O'qish hammaga, o'zgartirish faqat egasiga.

    Hunarmand boshqa hunarmandning mahsulotini tahrirlab yubormasligi uchun.
    Obyekt egasi `artisan.user` orqali topiladi.
    """

    message = "Bu sizning mahsulotingiz emas."

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        owner_id = getattr(obj, "artisan", None) and obj.artisan.user_id
        return bool(owner_id and owner_id == request.user.id)


class IsBot(permissions.BasePermission):
    """
    `/api/bot/` uchun yagona kalit.

    Bot foydalanuvchi nomidan emas, o'z nomidan murojaat qiladi — JWT yo'q,
    o'rniga umumiy maxfiy kalit. Kalit sozlanmagan bo'lsa hech kim kira
    olmaydi: bo'sh kalitni bo'sh sarlavha bilan solishtirish "hammaga
    ochiq" degani bo'lib qolardi.

    `apps.common` da turadi, chunki uni ikkita ilova ishlatadi:
    `payments` (to'lov) va `accounts` (saytga kirish kodi).
    """

    message = "Bot kaliti noto'g'ri."

    def has_permission(self, request, view):
        secret = settings.BOT_API_SECRET
        if not secret:
            return False
        return request.headers.get("X-Bot-Secret") == secret
