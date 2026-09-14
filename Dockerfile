# Imkon backend — Django + gunicorn
FROM python:3.11-slim AS base

# Python konteynerda: log darrov chiqsin, .pyc yozilmasin
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Pillow (rasm) va psycopg (Postgres) uchun kerakli tizim kutubxonalari.
# `--no-install-recommends` — образ shishib ketmasin.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libjpeg62-turbo \
        zlib1g \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Avval faqat requirements — kod o'zgarganda kutubxonalar qayta
# o'rnatilmasin (Docker qatlam keshi)
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# entrypoint'ga huquq Docker ichida beriladi — git/Windows fayl huquqini
# yo'qotib qo'yadi ("permission denied"). CRLF qator oxirlari ham
# tozalanadi, aks holda `#!/bin/sh` topilmaydi.
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Root'dan ishlamaymiz: konteyner buzilsa ham zarari cheklangan bo'lsin
RUN useradd --create-home --uid 1000 imkon \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R imkon:imkon /app
USER imkon

EXPOSE 8000

# Sog'liq tekshiruvi — nginx faqat tayyor backendga so'rov yuborsin
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fs http://localhost:8000/api/categories/ >/dev/null || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]

# `--workers 3` — kichik serverga mos. Ko'proq yadro bo'lsa oshiring.
# `--timeout 60` — rasm yuklash sekin bo'lishi mumkin.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
