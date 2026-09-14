from django.db import migrations

ICONS = {
    "rasmlar": "🖼️",
    "toqima": "🧶",
    "yogoch-buyum": "🪵",
    "sopol": "🏺",
    "taqinchoq": "💍",
    "oyinchoqlar": "🧸",
}


def set_icons(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    for slug, icon in ICONS.items():
        Category.objects.filter(slug=slug, icon="").update(icon=icon)


def clear_icons(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Category.objects.filter(slug__in=ICONS.keys()).update(icon="")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0004_comment_rating"),
    ]

    operations = [
        migrations.RunPython(set_icons, clear_icons),
    ]
