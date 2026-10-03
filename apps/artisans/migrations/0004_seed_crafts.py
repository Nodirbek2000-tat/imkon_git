"""
Hunar turlarini bazaga yozadi.

`catalog/0007_seed_categories` bilan bir sabab: hunar turisiz "Do'kon
ochish" arizasini yuborib bo'lmaydi (`ArtisanApplication.craft`
majburiy), ya'ni bu ham demo emas, zarur ma'lumot. Yangi serverda
ro'yxat bo'sh qolib, ariza formasi ishlamasdi.

Idempotent: slug bo'yicha `get_or_create`.
"""

from django.db import migrations

CRAFTS = [
    ("rassomlik", "Rassomlik", "Живопись", "Painting", "🎨"),
    ("toqimachilik", "To'qimachilik", "Ткачество", "Weaving", "🧶"),
    ("yogoch", "Yog'och o'ymakorligi", "Резьба по дереву", "Woodcarving", "🪵"),
    ("kulolchilik", "Kulolchilik", "Гончарство", "Pottery", "🏺"),
    ("zargarlik", "Zargarlik", "Ювелирное дело", "Jewelry", "💍"),
    ("oyinchoq", "O'yinchoqlar", "Игрушки", "Toys", "🧸"),
]


def create_crafts(apps, schema_editor):
    Craft = apps.get_model("artisans", "Craft")
    for slug, uz, ru, en, icon in CRAFTS:
        Craft.objects.get_or_create(
            slug=slug,
            defaults={"name_uz": uz, "name_ru": ru, "name_en": en, "icon": icon},
        )


def remove_crafts(apps, schema_editor):
    """Orqaga qaytarishda o'chirilmaydi — hunarmandlar bunga bog'langan."""


class Migration(migrations.Migration):
    dependencies = [
        ("artisans", "0003_artisanprofile_kind_artisanprofile_student_grade_and_more")
    ]

    operations = [migrations.RunPython(create_crafts, remove_crafts)]
