import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel

# +998901234567 — O'zbekiston raqami
PHONE_VALIDATOR = RegexValidator(
    regex=r"^\+998\d{9}$",
    message="Raqam +998XXXXXXXXX ko'rinishida bo'lishi kerak.",
)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, phone=None, password=None, **extra):
        # Foydalanuvchi telefon YOKI Google akkaunt bilan tanilaadi.
        # Ikkalasi ham bo'lmasa akkauntga hech qachon qaytib kira olmaydi.
        if not phone and not extra.get("google_id"):
            raise ValueError("Telefon raqami yoki Google akkaunt kerak.")

        user = self.model(phone=phone or None, **extra)
        # Parol yo'q — foydalanuvchi SMS orqali kiradi. Lekin akkaunt
        # parolsiz login qila olmasligi uchun ishlatib bo'lmaydigan qiymat.
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_phone_verified", True)

        if not extra.get("is_staff") or not extra.get("is_superuser"):
            raise ValueError("Superuser is_staff va is_superuser bo'lishi kerak.")

        return self.create_user(phone, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """
    Platformada ikkita maqom bor:
      • USER    — ro'yxatdan o'tgan hamma. Sotib oladi, auksionda taklif qiladi.
      • ARTISAN — arizasi tasdiqlangan hunarmand. Mahsulot va post qo'yadi.

    Alohida "sotuvchi ro'yxati" yo'q — bitta akkauntning roli o'zgaradi.
    """

    class Role(models.TextChoices):
        USER = "user", "Foydalanuvchi"
        ARTISAN = "artisan", "Hunarmand"

    # Google orqali kirganlarda raqam bo'lmasligi mumkin — keyin profildan
    # qo'shiladi. Shuning uchun null, lekin bo'lsa — yagona.
    phone = models.CharField(
        "Telefon",
        max_length=13,
        unique=True,
        null=True,
        blank=True,
        validators=[PHONE_VALIDATOR],
        db_index=True,
    )
    full_name = models.CharField("To'liq ism", max_length=120, blank=True)
    avatar = models.ImageField("Rasm", upload_to="avatars/%Y/%m/", blank=True, null=True)
    bio = models.TextField("O'zi haqida", max_length=500, blank=True)

    role = models.CharField(
        "Maqom", max_length=10, choices=Role.choices, default=Role.USER, db_index=True
    )
    language = models.CharField(
        "Til", max_length=2, choices=settings.LANGUAGES, default="uz"
    )

    is_phone_verified = models.BooleanField("Raqam tasdiqlangan", default=False)
    is_active = models.BooleanField("Faol", default=True)
    is_staff = models.BooleanField("Xodim", default=False)

    # Google orqali kirish uchun — 1-bosqichda telefon, keyin qo'shiladi
    google_id = models.CharField(max_length=64, blank=True, null=True, unique=True)
    email = models.EmailField(blank=True)

    # Telegram bot orqali kirish uchun — xuddi google_id kabi ixtiyoriy va yagona
    telegram_id = models.BigIntegerField(blank=True, null=True, unique=True, db_index=True)
    telegram_username = models.CharField(max_length=64, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "Foydalanuvchi"
        verbose_name_plural = "Foydalanuvchilar"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.full_name or 'Foydalanuvchi'} ({self.phone or self.email})"

    @property
    def is_artisan(self) -> bool:
        return self.role == self.Role.ARTISAN

    def promote_to_artisan(self):
        """Ariza tasdiqlangach chaqiriladi."""
        if self.role != self.Role.ARTISAN:
            self.role = self.Role.ARTISAN
            self.save(update_fields=["role", "updated_at"])


class PhoneOTP(TimeStampedModel):
    """
    SMS tasdiqlash kodi.

    Kod ochiq saqlanmaydi — hash qilinadi. Baza sizib chiqsa ham
    kodlardan foydalanib bo'lmaydi.
    """

    class Purpose(models.TextChoices):
        LOGIN = "login", "Kirish / ro'yxatdan o'tish"
        CHANGE_PHONE = "change_phone", "Raqamni o'zgartirish"

    phone = models.CharField(max_length=13, validators=[PHONE_VALIDATOR], db_index=True)
    code_hash = models.CharField(max_length=128)
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.LOGIN)

    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = "SMS kod"
        verbose_name_plural = "SMS kodlar"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["phone", "is_used", "-created_at"])]

    def __str__(self):
        return f"{self.phone} — {'ishlatilgan' if self.is_used else 'faol'}"

    # ------------------------------------------------------------ yaratish

    @classmethod
    def issue(cls, phone: str, purpose: str = Purpose.LOGIN) -> tuple["PhoneOTP", str]:
        """
        Yangi kod yaratadi va (obyekt, ochiq_kod) qaytaradi.
        Ochiq kod faqat SMS yuborish uchun — hech qayerda saqlanmaydi.
        """
        # Eski faol kodlarni bekor qilamiz — bir vaqtda bitta kod ishlasin
        cls.objects.filter(phone=phone, purpose=purpose, is_used=False).update(is_used=True)

        code = f"{secrets.randbelow(1_000_000):06d}"
        otp = cls.objects.create(
            phone=phone,
            code_hash=make_password(code),
            purpose=purpose,
            expires_at=timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS),
        )
        return otp, code

    # ------------------------------------------------------------ tekshirish

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    def verify(self, code: str) -> tuple[bool, str]:
        """(muvaffaqiyat, xabar) qaytaradi."""
        if self.is_used:
            return False, "Bu kod allaqachon ishlatilgan."

        if self.is_expired:
            return False, "Kod muddati tugagan. Yangisini so'rang."

        if self.attempts >= settings.OTP_MAX_ATTEMPTS:
            return False, "Urinishlar soni tugadi. Yangi kod so'rang."

        # Noto'g'ri urinishni HAR DOIM yozamiz — brute force to'xtatilsin
        self.attempts += 1

        if not check_password(code, self.code_hash):
            self.save(update_fields=["attempts", "updated_at"])
            left = settings.OTP_MAX_ATTEMPTS - self.attempts
            return False, f"Kod noto'g'ri. {max(left, 0)} ta urinish qoldi."

        self.is_used = True
        self.save(update_fields=["attempts", "is_used", "updated_at"])
        return True, "Tasdiqlandi."


class TelegramLoginCode(TimeStampedModel):
    """
    Telegram bot orqali kirish kodi.

    `PhoneOTP`dan farqi: u yerda qidiruv avval telefon bo'yicha, keyin kod
    tekshiriladi (shuning uchun sekin hash — `make_password`). Bu yerda
    saytda faqat kod kiritiladi, boshqa hech qanday kalit yo'q — shuning
    uchun tezkor SHA-256 bilan hashlaymiz, to'g'ridan-to'g'ri `code_hash`
    bo'yicha indekslangan qidiruv qilamiz. Xom kod hech qayerda saqlanmaydi.

    `attempts` maydoni yo'q — `PhoneOTP`da u qatorni allaqachon bilgan
    hujumchidan (telefon orqali topilgan) himoya qiladi. Bu yerda bunday
    qator yo'q — noto'g'ri kod shunchaki hech narsa topmaydi. Ko'r-ko'rona
    urinishdan `telegram_verify` throttle scope himoya qiladi.

    `purpose` ham yo'q — bitta kod ham kirish (`telegram/verify/`), ham
    bog'lash (`telegram/link/`) uchun ishlatiladi; qaysi birini bajarish
    kodni qaysi endpoint qabul qilganiga bog'liq, obyektning o'ziga emas.
    """

    telegram_id = models.BigIntegerField(db_index=True)
    telegram_username = models.CharField(max_length=64, blank=True)
    full_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=13, validators=[PHONE_VALIDATOR])
    code_hash = models.CharField(max_length=64, unique=True, db_index=True)

    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Telegram kirish kodi"
        verbose_name_plural = "Telegram kirish kodlari"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.phone} (tg:{self.telegram_id}) — {'ishlatilgan' if self.is_used else 'faol'}"

    @staticmethod
    def _hash(code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()

    @classmethod
    def issue(
        cls, *, telegram_id: int, telegram_username: str, full_name: str, phone: str
    ) -> tuple["TelegramLoginCode", str]:
        """Yangi kod yaratadi va (obyekt, ochiq_kod) qaytaradi."""
        cls.objects.filter(telegram_id=telegram_id, is_used=False).update(is_used=True)

        code = f"{secrets.randbelow(1_000_000):06d}"
        obj = cls.objects.create(
            telegram_id=telegram_id,
            telegram_username=telegram_username,
            full_name=full_name,
            phone=phone,
            code_hash=cls._hash(code),
            expires_at=timezone.now() + timedelta(seconds=settings.TELEGRAM_CODE_TTL_SECONDS),
        )
        return obj, code

    @classmethod
    def consume(cls, code: str) -> "TelegramLoginCode | None":
        """
        Kodni topib, bir martalik qilib belgilaydi. Topilmasa/eskirgan
        bo'lsa `None` qaytaradi. Atomik emas — chaqiruvchi kerak bo'lsa
        `transaction.atomic()` ichiga olishi kerak.
        """
        obj = cls.objects.filter(
            code_hash=cls._hash(code), is_used=False, expires_at__gt=timezone.now()
        ).first()
        if obj is None:
            return None
        obj.is_used = True
        obj.save(update_fields=["is_used", "updated_at"])
        return obj
