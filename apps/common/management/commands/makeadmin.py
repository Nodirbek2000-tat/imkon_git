"""
Foydalanuvchini admin qilish:

    python manage.py makeadmin +998901234567

Raqam bazada bo'lmasa yaratiladi — keyin o'sha raqam bilan saytga kirasiz
va yuqorida "Admin" tugmasi paydo bo'ladi.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import PHONE_VALIDATOR, User


class Command(BaseCommand):
    help = "Telefon raqami bo'yicha foydalanuvchini admin qiladi"

    def add_arguments(self, parser):
        parser.add_argument("phone", help="+998XXXXXXXXX")
        parser.add_argument(
            "--name", default="", help="Ismi (yangi akkaunt yaratilsa)"
        )
        parser.add_argument(
            "--super",
            action="store_true",
            dest="superuser",
            help="Django admin paneliga ham to'liq kirish (is_superuser)",
        )
        parser.add_argument(
            "--remove", action="store_true", help="Admin huquqini olib tashlash"
        )

    def handle(self, *args, **options):
        phone = options["phone"].strip()

        try:
            PHONE_VALIDATOR(phone)
        except Exception as exc:
            raise CommandError(f"Raqam noto'g'ri: {exc}") from exc

        user, created = User.objects.get_or_create(
            phone=phone,
            defaults={"full_name": options["name"], "is_phone_verified": True},
        )

        if options["remove"]:
            user.is_staff = False
            user.is_superuser = False
            user.save(update_fields=["is_staff", "is_superuser", "updated_at"])
            self.stdout.write(self.style.WARNING(f"{phone} — admin huquqi olib tashlandi."))
            return

        user.is_staff = True
        if options["superuser"]:
            user.is_superuser = True
        user.save(update_fields=["is_staff", "is_superuser", "updated_at"])

        if created:
            self.stdout.write(self.style.SUCCESS(f"Yangi akkaunt yaratildi: {phone}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"{phone} endi admin"
                + (" (superuser)" if options["superuser"] else "")
                + "\n\nSaytga kirish: /kirish -> shu raqamni kiriting -> SMS kod"
            )
        )
