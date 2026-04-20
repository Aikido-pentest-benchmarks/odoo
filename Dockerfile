FROM python:3.13-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    libldap2-dev \
    libsasl2-dev \
    libssl-dev \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    libffi-dev \
    postgresql-client \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/odoo

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY setup.py setup.cfg MANIFEST.in odoo-bin LICENSE README.md ./
COPY odoo odoo
COPY addons addons
COPY debian debian
COPY setup setup

RUN pip install --no-cache-dir .

RUN python3 -c "from odoo.tools.config import crypt_context; open('/tmp/admin_hash.txt','w',encoding='utf-8').write(crypt_context.hash('DBMGR_7f91c4e2a8b03d6f5e1c9a0b4d8e3f2c1a5b9d7e6f0c4a8b2d6e0f3c7a1b5d9'))"

COPY docker/odoo.conf /etc/odoo/odoo.conf
RUN printf '\nadmin_passwd = %s\n' "$(cat /tmp/admin_hash.txt)" >> /etc/odoo/odoo.conf \
    && rm /tmp/admin_hash.txt

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN mkdir -p /var/lib/odoo && chmod 755 /var/lib/odoo

EXPOSE 8069

ENTRYPOINT ["/entrypoint.sh"]
