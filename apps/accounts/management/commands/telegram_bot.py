"""
Bu buyruq ishlatilmaydi — bot alohida loyihaga ko'chirildi.

Eski bot faqat saytga kirish kodini berardi. Yangi bot (`imkon_bot/`)
bundan tashqari to'lov, chek va balans bilan ham ishlaydi, va backendga
faqat `/api/bot/` orqali murojaat qiladi.

MUHIM: ikkalasi bir vaqtda ishlay olmaydi. Telegram bitta bot uchun
`getUpdates` ni faqat bitta jarayonga beradi — ikkinchisi xabarlarni
o'g'irlab, foydalanuvchi javobsiz qoladi. Shuning uchun bu buyruq
o'chirib qo'yilgan.
"""

from django.core.management.base import BaseCommand, CommandError

MESSAGE = (
    "Bu buyruq endi ishlatilmaydi.\n\n"
    "Bot alohida loyihaga ko'chirildi:\n\n"
    "    cd imkon_bot\n"
    "    venv\\Scripts\\python.exe app.py\n\n"
    "Sozlamalar: imkon_bot/.env (namuna — .env.dist)"
)


class Command(BaseCommand):
    help = "Ishlatilmaydi — bot imkon_bot/ loyihasiga ko'chirilgan"

    def handle(self, *args, **options):
        raise CommandError(MESSAGE)
