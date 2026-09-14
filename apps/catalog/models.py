from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify

from apps.artisans.models import ArtisanProfile
from apps.common.models import TimeStampedModel
from apps.common.translation import TranslatedModelMixin

# Comment `comments.py` da, Favorite `favorites.py` da — bu fayl juda uzayib ketmasin
from .comments import Comment  # noqa: F401
from .favorites import Favorite  # noqa: F401


class Category(TranslatedModelMixin, TimeStampedModel):
    translated_fields = ("name",)

    slug = models.SlugField(max_length=80, unique=True, db_index=True)
    name_uz = models.CharField(max_length=100)
    name_ru = models.CharField(max_length=100, blank=True)
    name_en = models.CharField(max_length=100, blank=True)

    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    icon = models.CharField(max_length=40, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Kategoriya"
        verbose_name_plural = "Kategoriyalar"
        ordering = ("order", "name_uz")

    def __str__(self):
        return self.name_uz


class ProductQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Product.Status.ACTIVE, artisan__is_active=True)

    def with_relations(self):
        """
        Ro'yxat uchun standart yuklash.

        Busiz har bir mahsulot uchun alohida so'rov ketadi (N+1) —
        24 ta mahsulotli sahifada 70+ so'rov bo'lib qoladi.

        Reyting ham shu yerda — bitta so'rovda hisoblanadi (izohlar
        orasidan faqat baholanganlari, `rating__isnull=False` javoblarni
        va bahosiz izohlarni chetlab o'tadi).
        """
        return (
            self.select_related("category", "artisan", "artisan__user")
            .prefetch_related("images")
            .annotate(
                rating_avg=models.Avg("comments__rating", filter=models.Q(comments__rating__isnull=False)),
                rating_count=models.Count("comments__rating", filter=models.Q(comments__rating__isnull=False)),
            )
        )

    def with_favorited(self, user):
        """`is_favorited` — joriy foydalanuvchi shu mahsulotni saqlab qo'yganmi."""
        if user is None or not user.is_authenticated:
            return self.annotate(
                is_favorited=models.Value(False, output_field=models.BooleanField())
            )
        return self.annotate(
            is_favorited=models.Exists(
                Favorite.objects.filter(user=user, product=models.OuterRef("pk"))
            )
        )


class Product(TranslatedModelMixin, TimeStampedModel):
    translated_fields = ("title", "description")

    class Status(models.TextChoices):
        DRAFT = "draft", "Qoralama"
        ACTIVE = "active", "Sotuvda"
        SOLD = "sold", "Sotilgan"
        ARCHIVED = "archived", "Arxiv"

    class SaleType(models.TextChoices):
        FIXED = "fixed", "Belgilangan narx"
        AUCTION = "auction", "Auksion"

    artisan = models.ForeignKey(
        ArtisanProfile, on_delete=models.CASCADE, related_name="products"
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products"
    )

    slug = models.SlugField(max_length=140, unique=True, db_index=True)
    title_uz = models.CharField("Nomi", max_length=140)
    title_ru = models.CharField(max_length=140, blank=True)
    title_en = models.CharField(max_length=140, blank=True)

    description_uz = models.TextField("Tavsif", max_length=4000, blank=True)
    description_ru = models.TextField(max_length=4000, blank=True)
    description_en = models.TextField(max_length=4000, blank=True)

    price = models.DecimalField(
        "Narx (so'm)",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    stock = models.PositiveIntegerField("Zaxira", default=1)

    sale_type = models.CharField(
        max_length=10, choices=SaleType.choices, default=SaleType.FIXED, db_index=True
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True
    )

    views_count = models.PositiveIntegerField(default=0, editable=False)

    # Faqat status `SOLD`ga o'tganda o'rnatiladi (`ProductWriteSerializer.update`) —
    # "bu oy sotilgan" statistikasi uchun. `updated_at` (TimeStampedModel) buni
    # qila olmaydi — har qanday tahrirda o'zgaradi.
    sold_at = models.DateTimeField(null=True, blank=True, editable=False)

    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = "Mahsulot"
        verbose_name_plural = "Mahsulotlar"
        ordering = ("-created_at",)
        indexes = [
            # Katalogdagi asosiy filtr — kategoriya + holat + sana
            models.Index(fields=["status", "sale_type", "-created_at"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["artisan", "status"]),
        ]

    def __str__(self):
        return self.title_uz

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title_uz) or "mahsulot"
            slug, index = base, 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                index += 1
                slug = f"{base}-{index}"
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def main_image(self):
        # `images` prefetch qilingan bo'lsa qo'shimcha so'rov ketmaydi
        images = list(self.images.all())
        if not images:
            return None
        return next((img for img in images if img.is_main), images[0])


class ProductFeature(models.Model):
    """
    Mahsulot xususiyati: "Material — yong'oq yog'ochi", "O'lcham — 30x40 sm".
    Erkin matn o'rniga juftlik — frontend'da jadval qilib chiziladi.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="features")
    name = models.CharField("Nomi", max_length=80)
    value = models.CharField("Qiymati", max_length=160)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Xususiyat"
        verbose_name_plural = "Xususiyatlar"
        ordering = ("order", "id")

    def __str__(self):
        return f"{self.name}: {self.value}"


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/%Y/%m/")
    alt_text = models.CharField(
        "Alt matn",
        max_length=200,
        blank=True,
        help_text="Ko'rish qobiliyati cheklangan foydalanuvchilar uchun rasm tavsifi",
    )
    is_main = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("-is_main", "order", "id")

    def __str__(self):
        return f"{self.product.title_uz} — rasm"
