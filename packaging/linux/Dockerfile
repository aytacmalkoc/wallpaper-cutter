FROM debian:12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv libpython3.11 python3-gi python3-gi-cairo gir1.2-gtk-4.0 \
    imagemagick adwaita-icon-theme fonts-dejavu-core libgirepository1.0-dev \
    binutils patchelf ca-certificates curl file desktop-file-utils \
    xvfb xauth dbus libglib2.0-bin gsettings-desktop-schemas \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv --system-site-packages /opt/build \
    && /opt/build/bin/pip install --no-cache-dir pyinstaller==6.22.3 pillow
ENV PATH="/opt/build/bin:${PATH}"
WORKDIR /work
