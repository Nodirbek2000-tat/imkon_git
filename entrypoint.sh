#!/bin/sh
#
# Konteyner har ishga tushganda bajariladigan tayyorgarlik.
#
# MUHIM: bu yerda bazani o'chiradigan yoki tozalaydigan hech qanday buyruq
# YO'Q. `migrate` faqat yangi o'zgarishlarni qo'shadi, mavjud ma'lumotga
# tegmaydi — shuning uchun har deploy'da xavfsiz ishlaydi.
set -e

echo "==> Baza kutilmoqda..."
python - <<'PY'
import os, sys, time
import psycopg

url = os.environ.get("DATABASE_URL", "")
if not url:
    print("    DATABASE_URL yo'q — SQLite ishlatiladi, kutish shart emas")
    sys.exit(0)

for attempt in range(1, 61):
    try:
        psycopg.connect(url, connect_timeout=3).close()
        print(f"    baza tayyor ({attempt}-urinish)")
        sys.exit(0)
    except Exception as exc:
        if attempt == 1:
            print(f"    hali tayyor emas: {exc}")
        time.sleep(2)

print("    XATO: baza 2 daqiqada javob bermadi")
sys.exit(1)
PY

echo "==> Migratsiyalar..."
python manage.py migrate --noinput

echo "==> Statik fayllar..."
python manage.py collectstatic --noinput --clear

echo "==> Ishga tushmoqda: $*"
exec "$@"
