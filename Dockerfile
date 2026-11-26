# Odoo 18.0 Community (this fork) + catering add-ons, for Railway or any Docker host.
FROM python:3.12-slim-bookworm

ENV LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl ca-certificates fontconfig fonts-noto-core fonts-dejavu-core \
        libpq-dev libldap2-dev libsasl2-dev libxml2-dev libxslt1-dev libjpeg62-turbo-dev zlib1g-dev \
        postgresql-client xfonts-75dpi xfonts-base \
    && curl -fsSL -o /tmp/wkhtmltox.deb \
        https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.bookworm_amd64.deb \
    && apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb \
    && rm -rf /tmp/wkhtmltox.deb /var/lib/apt/lists/*

RUN useradd --create-home --home-dir /var/lib/odoo --shell /bin/bash odoo

WORKDIR /opt/odoo
COPY requirements.txt /opt/odoo/requirements.txt
RUN pip install -r requirements.txt

COPY --chown=odoo:odoo . /opt/odoo
RUN chmod +x /opt/odoo/deploy/railway/entrypoint.sh

USER odoo
EXPOSE 8069
ENTRYPOINT ["/opt/odoo/deploy/railway/entrypoint.sh"]
