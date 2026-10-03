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


class IsSchool(permissions.BasePermission):
    """
    Faqat maktab akkaunti.

    Maktabni platforma admini ochadi va login/parol beradi — ariza yo'q,
    o'zini o'zi maktab qilib ro'yxatdan o'tkazish yo'li ham yo'q.
    """

    message = "Bu amal faqat maktablar uchun."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and getattr(user, "is_school", False)
        )


class IsArtisanOrSchool(permissions.BasePermission):
    """
    Mahsulot/post qo'ya oladigan ikki maqom.

    Maktab o'z nomidan emas, o'quvchisi nomidan qo'yadi — qaysi o'quvchi
    ekanini serializer tekshiradi (`student=<slug>`), bu yerda faqat
    "umuman qo'yish huquqi bormi" degan savolga javob beriladi.
    """

    message = "Bu amal faqat hunarmandlar va maktablar uchun."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return bool(
            getattr(user, "is_artisan", False) or getattr(user, "is_school", False)
        )


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    O'qish hammaga, o'zgartirish faqat egasiga.

    Hunarmand boshqa hunarmandning mahsulotini tahrirlab yubormasligi uchun.
    Obyekt egasi `artisan` orqali topiladi.

    Ikkita ID tekshiriladi: `artisan.user_id` — hunarmandning o'zi, va
    `artisan.owner_user_id` — o'quvchining ishi bo'lsa uning MAKTABI.
    Aks holda maktab o'z o'quvchisining mahsulotini tahrirlay olmasdi,
    o'quvchi esa tizimga kirmaydi — ishni hech kim tuzata olmay qolardi.
    """

    message = "Bu sizning mahsulotingiz emas."

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        artisan = getattr(obj, "artisan", None)
        if artisan is None:
            return False
        return request.user.id in (artisan.user_id, artisan.owner_user_id)


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
