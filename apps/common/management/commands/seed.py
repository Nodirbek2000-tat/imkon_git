"""
Demo ma'lumot: `python manage.py seed`

Frontend'ni bo'sh baza bilan sinab bo'lmaydi. Bu buyruq bir nechta
hunarmand, mahsulot, auksion va post yaratadi. Qayta ishga tushirsa
takrorlanmaydi (get_or_create).
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.artisans.models import ArtisanProfile, Craft, Post
from apps.auctions.models import Auction
from apps.catalog.models import Category, Product

CRAFTS = [
    ("rassomlik", "Rassomlik", "Живопись", "Painting", "🎨"),
    ("toqimachilik", "To'qimachilik", "Ткачество", "Weaving", "🧶"),
    ("yogoch", "Yog'och o'ymakorligi", "Резьба по дереву", "Woodcarving", "🪵"),
    ("kulolchilik", "Kulolchilik", "Гончарство", "Pottery", "🏺"),
    ("zargarlik", "Zargarlik", "Ювелирное дело", "Jewelry", "💍"),
    ("oyinchoq", "O'yinchoqlar", "Игрушки", "Toys", "🧸"),
]

CATEGORIES = [
    ("rasmlar", "Rasmlar", "Картины", "Paintings", "🖼️"),
    ("toqima", "To'qima buyumlar", "Текстиль", "Textiles", "🧶"),
    ("yogoch-buyum", "Yog'och buyumlar", "Изделия из дерева", "Woodwork", "🪵"),
    ("sopol", "Sopol idishlar", "Керамика", "Ceramics", "🏺"),
    ("taqinchoq", "Taqinchoqlar", "Украшения", "Accessories", "💍"),
    ("oyinchoqlar", "O'yinchoqlar", "Игрушки", "Toys", "🧸"),
]

ARTISANS = [
    ("+998901000001", "Dilnoza Karimova", "Dilnoza ijodxonasi", "rassomlik", "Toshkent",
     "Akvarel va guash bilan ishlayman. Har bir rasmda o'z kayfiyatim bor."),
    ("+998901000002", "Nilufar Ahmedova", "Nilufar to'qimalari", "toqimachilik", "Samarqand",
     "Qo'lda to'qilgan o'yinchoq va bezaklar. 6 yildan beri shu ish bilan shug'ullanaman."),
    ("+998901000003", "Aziz Rahimov", "Aziz zargarlik", "zargarlik", "Buxoro",
     "Tabiiy toshlardan bilaguzuk va marjonlar yasayman."),
    ("+998901000004", "Sardor To'xtayev", "Xiva o'ymakorligi", "yogoch", "Xiva",
     "Yong'oq yog'ochidan an'anaviy naqshlar o'yaman. Otamdan o'rgandim."),
    ("+998901000005", "Malika Yusupova", "Rishton kulollari", "kulolchilik", "Farg'ona",
     "Rishton maktabi uslubida ko'k-oq sopol idishlar."),
]

PRODUCTS = [
    # (artisan_index, category_slug, uz, ru, en, price, sale_type)
    (0, "rasmlar", "Kuzgi tabiat manzarasi", "Осенний пейзаж", "Autumn landscape", 150_000, "fixed"),
    (0, "rasmlar", "Tog' cho'qqilari", "Горные вершины", "Mountain peaks", 185_000, "fixed"),
    (1, "oyinchoqlar", "Yumshoq ayiqcha", "Мягкий мишка", "Soft teddy bear", 95_000, "fixed"),
    (1, "toqima", "Gilam to'qima panno", "Тканое панно", "Woven wall panel", 480_000, "auction"),
    (2, "taqinchoq", "Qo'lda ishlangan bilaguzuk", "Браслет ручной работы", "Handmade bracelet", 45_000, "fixed"),
    (3, "yogoch-buyum", "Yog'och o'ymakorlik lavhasi", "Резное панно", "Carved wood panel", 320_000, "auction"),
    (4, "sopol", "Sopol choynak", "Керамический чайник", "Ceramic teapot", 210_000, "auction"),
    (4, "sopol", "Ko'k naqshli laganda", "Синее блюдо", "Blue patterned platter", 165_000, "fixed"),
]


class Command(BaseCommand):
    help = "Demo ma'lumot yaratadi (hunarmandlar, mahsulotlar, auksionlar, postlar)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true", help="Avval demo ma'lumotni o'chirish"
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            User.objects.filter(phone__startswith="+99890100000").delete()
            self.stdout.write(self.style.WARNING("Eski demo ma'lumot o'chirildi."))

        crafts = {}
        for slug, uz, ru, en, icon in CRAFTS:
            craft, _ = Craft.objects.get_or_create(
                slug=slug,
                defaults={"name_uz": uz, "name_ru": ru, "name_en": en, "icon": icon},
            )
            crafts[slug] = craft

        categories = {}
        for order, (slug, uz, ru, en, icon) in enumerate(CATEGORIES):
            category, _ = Category.objects.get_or_create(
                slug=slug,
                defaults={"name_uz": uz, "name_ru": ru, "name_en": en, "order": order, "icon": icon},
            )
            categories[slug] = category

        profiles = []
        for phone, name, shop, craft_slug, region, about in ARTISANS:
            user, _ = User.objects.get_or_create(
                phone=phone,
                defaults={
                    "full_name": name,
                    "role": User.Role.ARTISAN,
                    "is_phone_verified": True,
                },
            )
            profile, _ = ArtisanProfile.objects.get_or_create(
                user=user,
                defaults={"shop_name_uz": shop, "about_uz": about, "region": region},
            )
            profile.crafts.add(crafts[craft_slug])
            profiles.append(profile)

        created_products = []
        for artisan_i, cat_slug, uz, ru, en, price, sale_type in PRODUCTS:
            product, _ = Product.objects.get_or_create(
                artisan=profiles[artisan_i],
                title_uz=uz,
                defaults={
                    "category": categories[cat_slug],
                    "title_ru": ru,
                    "title_en": en,
                    "description_uz": f"{uz} — qo'lda ishlangan, yagona nusxa.",
                    "description_ru": f"{ru} — ручная работа, единственный экземпляр.",
                    "description_en": f"{en} — handmade, one of a kind.",
                    "price": Decimal(price),
                    "sale_type": sale_type,
                    "status": Product.Status.ACTIVE,
                },
            )
            created_products.append(product)

        now = timezone.now()
        auction_hours = [5, 29, 74]
        auction_products = [p for p in created_products if p.sale_type == Product.SaleType.AUCTION]

        for product, hours in zip(auction_products, auction_hours):
            Auction.objects.get_or_create(
                product=product,
                defaults={
                    "start_price": product.price,
                    "min_increment": Decimal("10000"),
                    "start_at": now - timedelta(hours=2),
                    "end_at": now + timedelta(hours=hours),
                    "status": Auction.Status.LIVE,
                },
            )

        for profile in profiles[:3]:
            Post.objects.get_or_create(
                artisan=profile,
                caption=f"{profile.shop_name_uz} ustaxonasidan salom! Yangi ish ustida ishlayapman.",
            )

        # Sanoqlarni to'g'rilaymiz
        for profile in profiles:
            ArtisanProfile.objects.filter(pk=profile.pk).update(
                products_count=profile.products.count(),
                posts_count=profile.posts.count(),
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Tayyor: {len(profiles)} hunarmand, {len(created_products)} mahsulot, "
                f"{len(auction_products)} auksion."
            )
        )
