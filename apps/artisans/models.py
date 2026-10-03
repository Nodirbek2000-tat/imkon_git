from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.utils.text import slugify

from apps.accounts.models import PHONE_VALIDATOR
from apps.common.models import TimeStampedModel
from apps.common.translation import TranslatedModelMixin

# Maktab logini — telefon emas, oddiy satr. Faqat kichik lotin harflari,
# raqam va chiziqcha: maktab xodimi uni telefonda ham xatosiz tera olsin.
SCHOOL_LOGIN_VALIDATOR = RegexValidator(
    r"^[a-z0-9][a-z0-9-]{2,39}$",
    message="Login 3-40 belgi: kichik lotin harflari, raqam va chiziqcha.",
)


class Craft(TranslatedModelMixin, TimeStampedModel):
    """Hunar turi: rassomlik, to'qimachilik, kulolchilik..."""

    translated_fields = ("name",)

    slug = models.SlugField(max_length=60, unique=True)
    name_uz = models.CharField(max_length=80)
    name_ru = models.CharField(max_length=80, blank=True)
    name_en = models.CharField(max_length=80, blank=True)
    icon = models.CharField("Emoji yoki ikonka nomi", max_length=40, blank=True)

    class Meta:
        verbose_name = "Hunar turi"
        verbose_name_plural = "Hunar turlari"
        ordering = ("name_uz",)

    def __str__(self):
        return self.name_uz


class ArtisanProfile(TranslatedModelMixin, TimeStampedModel):
    """
    Hunarmandning ommaviy sahifasi — Instagram profiliga o'xshash.
    Faqat arizasi tasdiqlangan foydalanuvchida bo'ladi.
    """

    translated_fields = ("shop_name", "about")

    class Kind(models.TextChoices):
        ARTISAN = "artisan", "Hunarmand"
        STUDENT = "student", "Maktab o'quvchisi"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="artisan_profile",
    )
    slug = models.SlugField(max_length=80, unique=True, db_index=True)

    # O'quvchi ham shu modelda saqlanadi: shunda `Product.artisan` umuman
    # o'zgarmaydi va bolaning ishlari mavjud katalog/auksion/buyurtma
    # oqimiga hech qanday qo'shimchasiz tushadi.
    kind = models.CharField(
        max_length=10, choices=Kind.choices, default=Kind.ARTISAN, db_index=True
    )
    # PROTECT — o'quvchilari bor maktabni o'chirib bo'lmaydi. Aks holda
    # o'chirish bolalarni, ular orqali mahsulot va buyurtma tarixini ham
    # yetaklab ketardi (`Product.artisan` CASCADE).
    school = models.ForeignKey(
        "artisans.SchoolProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="students",
    )
    student_grade = models.CharField("Sinf", max_length=20, blank=True)

    shop_name_uz = models.CharField("Do'kon nomi", max_length=100)
    shop_name_ru = models.CharField(max_length=100, blank=True)
    shop_name_en = models.CharField(max_length=100, blank=True)

    about_uz = models.TextField("Hunarmand haqida", max_length=1500, blank=True)
    about_ru = models.TextField(max_length=1500, blank=True)
    about_en = models.TextField(max_length=1500, blank=True)

    crafts = models.ManyToManyField(Craft, related_name="artisans", blank=True)
    region = models.CharField("Viloyat", max_length=60, blank=True)

    banner = models.ImageField(upload_to="artisans/banners/%Y/%m/", blank=True, null=True)

    # Sanoqlarni har so'rovda COUNT(*) qilib hisoblash sekin — shu yerda saqlaymiz
    products_count = models.PositiveIntegerField(default=0, editable=False)
    posts_count = models.PositiveIntegerField(default=0, editable=False)
    sold_count = models.PositiveIntegerField(default=0, editable=False)

    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "Hunarmand profili"
        verbose_name_plural = "Hunarmand profillari"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["is_active", "-created_at"])]

    def __str__(self):
        return self.shop_name_uz

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def _unique_slug(self) -> str:
        fallback = "oquvchi" if self.kind == self.Kind.STUDENT else "hunarmand"
        base = slugify(self.shop_name_uz, allow_unicode=False) or fallback
        slug, index = base, 1
        while ArtisanProfile.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            index += 1
            slug = f"{base}-{index}"
        return slug

    # ------------------------------------------------------------ egasi
    #
    # Pul va bildirishnoma KIMGA tegishli. O'quvchining o'z akkaunti
    # telefonsiz va parolsiz — unga tushgan pulni hech kim ko'ra olmaydi.
    # Shuning uchun o'quvchining sotuvi MAKTAB hisobiga boradi, oddiy
    # hunarmandda esa hech narsa o'zgarmaydi.

    @property
    def owner_user_id(self):
        return self.school.user_id if self.school_id else self.user_id

    @property
    def owner_user(self):
        return self.school.user if self.school_id else self.user


class SchoolProfile(TranslatedModelMixin, TimeStampedModel):
    """
    Maktabning ommaviy sahifasi.

    Maktabni FAQAT platforma admini ochadi va unga login/parol beradi —
    ariza ham, tasdiqlash ham yo'q. Maktab esa o'z o'quvchilarini hech
    kimdan ruxsat so'ramasdan o'zi kiritadi.

    Hunarmanddan farqi: maktab o'zi mahsulot qo'ymaydi, u o'quvchilari
    nomidan qo'yadi. Shuning uchun bu alohida model — `ArtisanProfile`
    ga `is_school` degan bayroq qo'shish ikkisining maydonlarini
    chalkashtirib yuborardi (maktabda hunar turi, do'kon nomi yo'q;
    o'quvchida login, parol yo'q).
    """

    translated_fields = ("name", "about")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="school_profile",
    )
    # Maktab telefon raqami bilan emas, shu login bilan kiradi. `User.phone`
    # unda bo'sh — shuning uchun login shu yerda, alohida maydonda saqlanadi.
    login = models.CharField(
        "Login",
        max_length=40,
        unique=True,
        db_index=True,
        validators=[SCHOOL_LOGIN_VALIDATOR],
        help_text="Maktab shu login bilan kiradi. Masalan: 15-maktab-chirchiq",
    )
    slug = models.SlugField(max_length=80, unique=True, db_index=True)

    name_uz = models.CharField("Maktab nomi", max_length=140)
    name_ru = models.CharField(max_length=140, blank=True)
    name_en = models.CharField(max_length=140, blank=True)

    about_uz = models.TextField("Maktab haqida", max_length=1500, blank=True)
    about_ru = models.TextField(max_length=1500, blank=True)
    about_en = models.TextField(max_length=1500, blank=True)

    region = models.CharField("Viloyat", max_length=60, blank=True)
    district = models.CharField("Tuman / shahar", max_length=60, blank=True)
    contact_phone = models.CharField(
        "Aloqa raqami", max_length=13, blank=True, validators=[PHONE_VALIDATOR]
    )

    logo = models.ImageField(upload_to="schools/logos/%Y/%m/", blank=True, null=True)
    banner = models.ImageField(upload_to="schools/banners/%Y/%m/", blank=True, null=True)

    students_count = models.PositiveIntegerField(default=0, editable=False)

    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "Maktab"
        verbose_name_plural = "Maktablar"
        ordering = ("name_uz",)
        indexes = [models.Index(fields=["is_active", "name_uz"])]

    def __str__(self):
        return self.name_uz

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def _unique_slug(self) -> str:
        base = slugify(self.name_uz, allow_unicode=False) or "maktab"
        slug, index = base, 1
        while SchoolProfile.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            index += 1
            slug = f"{base}-{index}"
        return slug

    def set_active(self, flag: bool):
        """
        Maktabni yoqadi/o'chiradi.

        Ikkita joyni birga o'zgartirish SHART: `is_active` sahifani
        yashiradi, `User.is_active` esa loginni to'xtatadi. Faqat biri
        o'zgarsa — o'chirilgan maktab baribir tizimga kira olardi (yoki
        teskarisi: yoqilgan maktab kira olmasdi).
        """
        with transaction.atomic():
            self.is_active = flag
            self.save(update_fields=["is_active", "updated_at"])
            if self.user.is_active != flag:
                self.user.is_active = flag
                self.user.save(update_fields=["is_active", "updated_at"])


class ArtisanApplication(TimeStampedModel):
    """
    "Do'kon ochish" arizasi. Foydalanuvchi profilidan yuboradi,
    admin ko'rib chiqadi. Tasdiqlansa — rol `artisan` ga o'zgaradi.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Ko'rib chiqilmoqda"
        APPROVED = "approved", "Tasdiqlangan"
        REJECTED = "rejected", "Rad etilgan"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="artisan_applications"
    )
    shop_name = models.CharField("Do'kon nomi", max_length=100)
    craft = models.ForeignKey(Craft, on_delete=models.PROTECT, related_name="applications")
    description = models.TextField("Nima ishlab chiqarasiz", max_length=1500)
    region = models.CharField(max_length=60, blank=True)
    document = models.FileField("Hujjat", upload_to="applications/%Y/%m/", blank=True, null=True)

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    admin_note = models.TextField("Admin izohi", blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Hunarmand arizasi"
        verbose_name_plural = "Hunarmand arizalari"
        ordering = ("-created_at",)
        constraints = [
            # Bitta odam bir vaqtda bitta ariza yubora oladi
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status="pending"),
                name="one_pending_application_per_user",
            )
        ]

    def __str__(self):
        return f"{self.shop_name} — {self.get_status_display()}"


class Post(TimeStampedModel):
    """
    Hunarmand posti — Instagram uslubida.
    Mahsulot emas: jarayon, ustaxona, tayyor ish haqida hikoya.
    Ixtiyoriy ravishda mahsulotga bog'lash mumkin.
    """

    artisan = models.ForeignKey(
        ArtisanProfile, on_delete=models.CASCADE, related_name="posts"
    )
    caption = models.TextField("Matn", max_length=2200, blank=True)
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posts",
        help_text="Post shu mahsulot haqida bo'lsa — bog'lang",
    )

    likes_count = models.PositiveIntegerField(default=0, editable=False)
    is_published = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "Post"
        verbose_name_plural = "Postlar"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["artisan", "is_published", "-created_at"])]

    def __str__(self):
        return f"{self.artisan.shop_name_uz}: {self.caption[:40]}"


class PostImage(models.Model):
    """Bitta postda bir nechta rasm — Instagram karuseli kabi."""

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="posts/%Y/%m/")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")

    def __str__(self):
        return f"Rasm #{self.order}"


class PostLike(TimeStampedModel):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="likes")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="post_likes"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["post", "user"], name="one_like_per_user_post")
        ]
