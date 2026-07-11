# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12

# ============================================================
# Stage 1: Builder
# ============================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ARG ODOO_VERSION
ARG ODOO_REVISION

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential git pkg-config \
    libpq-dev libldap2-dev libsasl2-dev libxml2-dev libxslt1-dev \
    libffi-dev libjpeg-dev zlib1g-dev

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Fetch the EXACT resolved commit (ODOO_REVISION) so the baked source always
# matches the OCI revision label, and the layer cache-busts when it changes.
RUN mkdir -p /opt/odoo && cd /opt/odoo && \
    git init -q && \
    git remote add origin https://github.com/odoo/odoo.git && \
    git fetch -q --depth 1 origin ${ODOO_REVISION} && \
    git checkout -q FETCH_HEAD

# Layer 1: Odoo core deps (from the cloned source — version-correct by definition).
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip wheel && \
    pip install -r /opt/odoo/requirements.txt

# Layer 2: Hand-maintained extra deps.
COPY factory/extra_requirements.txt /tmp/extra_requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/extra_requirements.txt

# ============================================================
# Stage 2: Production
# ============================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS production

ARG ODOO_VERSION
ARG ODOO_UID=1000
ARG ODOO_GID=1000
ARG ODOO_REVISION=unknown

ENV PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    PATH="/opt/venv/bin:/opt/odoo:$PATH" \
    ODOO_RC=/etc/odoo/odoo.conf \
    ODOO_VERSION=${ODOO_VERSION}

WORKDIR /opt/odoo

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl postgresql-client \
    libpq5 libldap-2.5-0 libsasl2-2 libxml2 libxslt1.1 libjpeg62-turbo \
    zlib1g libffi8 fontconfig xfonts-75dpi xfonts-base fonts-noto-cjk \
    libx11-6 libxcb1 libxext6 libxrender1 \
    && ARCH=$(dpkg --print-architecture); \
    if [ "$ARCH" = "amd64" ]; then \
      curl -o /tmp/wkhtmltox.deb -sSL https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.bookworm_amd64.deb; \
    elif [ "$ARCH" = "arm64" ]; then \
      curl -o /tmp/wkhtmltox.deb -sSL https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.bookworm_arm64.deb; \
    fi; \
    apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb && rm -f /tmp/wkhtmltox.deb

RUN groupadd -g ${ODOO_GID} odoo \
    && useradd -u ${ODOO_UID} -g odoo -m -s /bin/bash odoo

# /mnt/worktrees is the Phase 2 workspace-projection mount point (per-worktree
# addons scanned by entrypoint.sh's build_addons_path); created here so both
# phases share the same directory layout.
RUN mkdir -p /mnt/worktrees /mnt/custom /mnt/community /mnt/localization /mnt/enterprise /var/lib/odoo /etc/odoo \
    && chown -R odoo:odoo /mnt/worktrees /mnt/custom /mnt/community /mnt/localization /mnt/enterprise /var/lib/odoo /etc/odoo

COPY --chown=odoo:odoo --from=builder /opt/venv /opt/venv
COPY --chown=odoo:odoo --from=builder /opt/odoo /opt/odoo

RUN ln -s /opt/odoo/odoo-bin /usr/local/bin/odoo

COPY --chown=odoo:odoo factory/odoo.conf /etc/odoo/odoo.conf
COPY --chown=odoo:odoo factory/entrypoint.sh /entrypoint.sh
COPY --chown=odoo:odoo factory/lib/credentials.sh /lib/credentials.sh
COPY --chown=odoo:odoo factory/wait-for-psql.py /usr/local/bin/wait-for-psql.py
RUN chmod +x /entrypoint.sh /usr/local/bin/wait-for-psql.py

VOLUME ["/var/lib/odoo"]
EXPOSE 8069 8072

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8069/web/health || exit 1

LABEL org.opencontainers.image.title="odoo-ce" \
      org.opencontainers.image.source="https://github.com/aparragithub/odoo-forge" \
      org.opencontainers.image.revision="${ODOO_REVISION}" \
      org.opencontainers.image.version="${ODOO_VERSION}"

USER odoo

ENTRYPOINT ["/entrypoint.sh"]
CMD ["odoo"]
