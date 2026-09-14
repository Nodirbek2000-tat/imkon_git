from django.conf import settings
from django.db import models
from django.utils.text import slugify

from apps.common.models import TimeStampedModel
from apps.common.translation import TranslatedModelMixin


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

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="artisan_profile",
    )
    slug = models.SlugField(max_length=80, unique=True, db_index=True)

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
        base = slugify(self.shop_name_uz, allow_unicode=False) or "hunarmand"
        slug, index = base, 1
        while ArtisanProfile.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            index += 1
            slug = f"{base}-{index}"
        return slug


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
