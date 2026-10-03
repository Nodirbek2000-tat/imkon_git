"""
Kategoriyalarni bazaga yozadi.

NEGA MIGRATSIYADA: kategoriyasiz birorta ham mahsulot qo'yib bo'lmaydi
(`Product.category` majburiy), ya'ni bu demo ma'lumot emas — saytning
ishlashi uchun zarur ma'lumot. Avval u faqat `seed` buyrug'ida edi,
`seed` esa kategoriyalar bilan birga 10 ta soxta hunarmand va ularning
mahsulotlarini ham yaratadi — buni productionga qo'yib bo'lmaydi.

Shuning uchun yangi serverda kategoriya ro'yxati bo'm-bo'sh qolib,
"Yangi ish qo'shish" formasidagi "Kategoriya" ro'yxati ochilmasdi.

Idempotent: `get_or_create` slug bo'yicha, shuning uchun mavjud bazada
hech narsa o'zgarmaydi va qayta ishga tushirilsa ham dublikat bo'lmaydi.
"""

from django.db import migrations

CATEGORIES = [
    ("rasmlar", "Rasmlar", "Картины", "Paintings", "🖼️"),
    ("toqima", "To'qima buyumlar", "Текстиль", "Textiles", "🧶"),
    ("yogoch-buyum", "Yog'och buyumlar", "Изделия из дерева", "Woodwork", "🪵"),
    ("sopol", "Sopol idishlar", "Керамика", "Ceramics", "🏺"),
    ("taqinchoq", "Taqinchoqlar", "Украшения", "Accessories", "💍"),
    ("oyinchoqlar", "O'yinchoqlar", "Игрушки", "Toys", "🧸"),
]


def create_categories(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    for order, (slug, uz, ru, en, icon) in enumerate(CATEGORIES):
        Category.objects.get_or_create(
            slug=slug,
            defaults={
                "name_uz": uz,
                "name_ru": ru,
                "name_en": en,
                "order": order,
                "icon": icon,
            },
        )


def remove_categories(apps, schema_editor):
    """
    Orqaga qaytarishda HECH NARSA o'chirilmaydi.

    Bu kategoriyalarga allaqachon mahsulot bog'langan bo'lishi mumkin —
    o'chirish ularni ham yetaklab ketardi yoki `PROTECT` ga urilib
    migratsiyani yiqitardi.
    """


class Migration(migrations.Migration):
    dependencies = [("catalog", "0006_favorite")]

    operations = [migrations.RunPython(create_categories, remove_categories)]
