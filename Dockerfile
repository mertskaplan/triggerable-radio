FROM python:3.11-slim

# Prevent interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies:
# - bluez: provides bluetoothctl (talks to the host bluetoothd over the mounted system D-Bus)
# - rfkill: unblocks a soft-blocked host Bluetooth adapter
# - mpv: lightweight, high-performance audio engine with reconnect support
# - pulseaudio-utils: provides pactl; audio is played through the host PipeWire-Pulse socket
# - ca-certificates, curl: for HTTPS streaming and health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    bluez \
    rfkill \
    mpv \
    pulseaudio-utils \
    curl \
    ca-certificates \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source and scripts
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

COPY app /app/app

# Default application port
EXPOSE 8836

ENTRYPOINT ["/app/entrypoint.sh"]
