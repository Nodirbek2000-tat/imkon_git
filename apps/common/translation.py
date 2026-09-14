"""
Uch tilli maydonlar (uz / ru / en) uchun yordamchi.

Yondashuv: qo'shimcha kutubxona yo'q. Model'da `title_uz`, `title_ru`, `title_en`
maydonlari turadi. Serializer so'rov tiliga qarab bittasini `title` sifatida
qaytaradi. Tarjima yo'q bo'lsa — zaxira zanjiri bo'yicha to'ldiriladi.

Nega shunday: `django-modeltranslation` migratsiyalarni sehrli tarzda
o'zgartiradi va debug qilish qiyin. Bu yerda maydonlar oshkora — ko'rinib
turadi, indekslash oson, JOIN qo'shilmaydi.
"""

from django.conf import settings
from django.db import models

LANGUAGES = ("uz", "ru", "en")
DEFAULT_LANGUAGE = "uz"


def resolve_language(request) -> str:
    """`?lang=ru` yoki `Accept-Language` sarlavhasidan tilni aniqlaydi."""
    if request is None:
        return DEFAULT_LANGUAGE

    explicit = request.query_params.get("lang") if hasattr(request, "query_params") else None
    if explicit in LANGUAGES:
        return explicit

    header = request.headers.get("Accept-Language", "")
    for chunk in header.split(","):
        code = chunk.split(";")[0].strip().lower()[:2]
        if code in LANGUAGES:
            return code

    return DEFAULT_LANGUAGE


def translated_char_field(verbose: str, **kwargs) -> dict[str, models.Field]:
    """`{"title_uz": CharField, "title_ru": ..., "title_en": ...}` qaytaradi."""
    return {
        lang: models.CharField(f"{verbose} ({lang})", **kwargs) for lang in LANGUAGES
    }


class TranslatedModelMixin:
    """
    Model'ga `.tr("title", "ru")` metodini qo'shadi.

    `translated_fields` ni model'da e'lon qiling:
        translated_fields = ("title", "description")
    """

    translated_fields: tuple[str, ...] = ()

    def tr(self, field: str, lang: str = DEFAULT_LANGUAGE) -> str:
        # So'ralgan til → o'zbek → qolgan har qanday to'ldirilgan til
        order = [lang, DEFAULT_LANGUAGE, *LANGUAGES]
        seen = set()
        for code in order:
            if code in seen:
                continue
            seen.add(code)
            value = getattr(self, f"{field}_{code}", "")
            if value:
                return value
        return ""


class TranslatedSerializerMixin:
    """
    `translated_fields` da sanalgan maydonlarni so'rov tiliga qarab tekislaydi.

    Javobda `title_uz/ru/en` o'rniga bitta `title` chiqadi — frontend'da
    til tanlash mantiqi takrorlanmaydi.
    """

    translated_fields: tuple[str, ...] = ()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        lang = resolve_language(self.context.get("request"))

        for field in self.translated_fields:
            data[field] = instance.tr(field, lang)
            # Xom maydonlarni javobdan olib tashlaymiz — trafik bekorga oshmasin
            for code in LANGUAGES:
                data.pop(f"{field}_{code}", None)

        return data


def language_choices():
    return list(settings.LANGUAGES)
