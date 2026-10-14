# Deliberately contains no Python, GTK or ImageMagick packages.
FROM debian:12-slim
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    libgl1 libegl1 libx11-6 libxcb1 libxext6 libxrender1 libwayland-client0 \
    libwayland-egl1 libwayland-cursor0 fontconfig fonts-dejavu-core xvfb xauth dbus
ENV GSETTINGS_BACKEND=memory GDK_BACKEND=x11 GTK_A11Y=none GSK_RENDERER=cairo
# An incompatible host IM7 must never override our bundled IM6 tools.
COPY packaging/linux/reject-host-magick /usr/local/bin/magick
RUN chmod +x /usr/local/bin/magick
