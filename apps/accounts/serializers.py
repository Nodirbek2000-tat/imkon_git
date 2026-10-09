from rest_framework import serializers

from .models import PHONE_VALIDATOR, User


class UserSerializer(serializers.ModelSerializer):
    """Profil — o'z akkauntini ko'rish va tahrirlash."""

    is_artisan = serializers.BooleanField(read_only=True)
    is_school = serializers.BooleanField(read_only=True)
    is_student = serializers.BooleanField(read_only=True)
    # Admin panel havolasi shu bayroqqa qarab ko'rsatiladi
    is_admin = serializers.BooleanField(source="is_staff", read_only=True)
    artisan_slug = serializers.SerializerMethodField()
    # Maktab akkauntining o'z ommaviy sahifasiga havola
    school_slug = serializers.SerializerMethodField()
    school_name = serializers.SerializerMethodField()
    # Xom google_id/telegram_id/parol hech qachon clientga chiqmaydi — faqat holat
    has_google = serializers.SerializerMethodField()
    has_telegram = serializers.SerializerMethodField()
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "phone", "full_name", "avatar", "bio", "email",
            "role", "is_artisan", "is_admin", "artisan_slug",
            "is_school", "is_student", "school_slug", "school_name",
            "language", "is_phone_verified", "created_at",
            "has_google", "has_telegram", "telegram_username", "has_password",
        )
        read_only_fields = ("id", "phone", "role", "is_phone_verified", "created_at")

    def get_artisan_slug(self, obj) -> str | None:
        # `artisan_profile` select_related bilan oldindan yuklanadi
        profile = getattr(obj, "artisan_profile", None)
        return profile.slug if profile else None

    def get_school_slug(self, obj) -> str | None:
        # `school_profile` ham select_related bilan oldindan yuklanadi
        profile = getattr(obj, "school_profile", None)
        return profile.slug if profile else None

    def get_school_name(self, obj) -> str | None:
        profile = getattr(obj, "school_profile", None)
        return profile.name_uz if profile else None

    def get_has_google(self, obj) -> bool:
        return bool(obj.google_id)

    def get_has_telegram(self, obj) -> bool:
        return bool(obj.telegram_id)

    def get_has_password(self, obj) -> bool:
        return obj.has_usable_password()


class PublicUserSerializer(serializers.ModelSerializer):
    """Boshqalarga ko'rinadigan qism — telefon raqami chiqmaydi."""

    class Meta:
        model = User
        fields = ("id", "full_name", "avatar", "bio", "role")


class SendOTPSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=13, validators=[PHONE_VALIDATOR])


class VerifyOTPSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=13, validators=[PHONE_VALIDATOR])
    code = serializers.CharField(min_length=6, max_length=6)
    # Yangi foydalanuvchi bo'lsa ismini birdan olib qo'yamiz
    full_name = serializers.CharField(max_length=120, required=False, allow_blank=True)


class GoogleLoginSerializer(serializers.Serializer):
    """Google Identity Services'dan kelgan ID token."""

    credential = serializers.CharField()


class TelegramCodeSerializer(serializers.Serializer):
    """Bot yuborgan 6 xonali kod — kirish uchun ham, bog'lash uchun ham."""

    code = serializers.CharField(min_length=6, max_length=6)


class BotLoginCodeSerializer(serializers.Serializer):
    """
    Bot saytga kirish kodi so'rayotganda yuboradigan ma'lumot.

    Raqam Telegramning "kontakt yuborish" tugmasidan keladi — Telegram uni
    o'zi tasdiqlagan, shuning uchun bu yerda SMS tekshiruvi yo'q.
    """

    telegram_id = serializers.IntegerField()
    telegram_username = serializers.CharField(max_length=64, allow_blank=True, default="")
    full_name = serializers.CharField(max_length=120, allow_blank=True, default="")
    phone = serializers.CharField(max_length=13, validators=[PHONE_VALIDATOR])


class PasswordLoginSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=13, validators=[PHONE_VALIDATOR])
    password = serializers.CharField()


class SchoolLoginSerializer(serializers.Serializer):
    """
    Maktab login + parol bilan kiradi.

    Telefon ham, SMS ham yo'q: maktabda bitta umumiy akkaunt bo'ladi va
    unda ishlaydigan odam o'zgarib turadi — shaxsiy raqamga bog'lash
    noto'g'ri bo'lardi. Login/parolni platforma admini beradi.
    """

    login = serializers.CharField(max_length=40)
    password = serializers.CharField()

    def validate_login(self, value: str) -> str:
        # Maktab xodimi loginni bosh harf bilan yoki bo'sh joy bilan
        # terishi mumkin — bu xato emas, tozalab olamiz. Qoida admin
        # panelidagi va brauzerdagi bilan AYNAN bir xil, aks holda
        # qog'ozdan ko'chirilgan login topilmay qolardi.
        from apps.artisans.models import normalize_school_login

        return normalize_school_login(value)


class SetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(min_length=6)


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()
    is_new = serializers.BooleanField()
