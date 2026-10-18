#!/bin/bash
set -e

echo "=========================================================="
echo " Starting Triggerable Radio Container"
echo "=========================================================="
echo "Port: ${PORT:-8836}"
echo "Target Bluetooth MAC: ${BT_DEVICE_MAC:-AA:BB:CC:DD:EE:FF}"
echo "Stream URL: ${STREAM_URL:-https://radyoilef.ankara.edu.tr/live}"
echo "=========================================================="

# 1. Check D-Bus socket for BlueZ Bluetooth control
if [ -S "/var/run/dbus/system_bus_socket" ]; then
    echo "[D-Bus] ✔ Host system D-Bus socket detected."
else
    echo "[D-Bus] ✘ Host D-Bus socket not found!"
    echo "         Ensure /var/run/dbus/system_bus_socket is mounted in docker-compose.yml."
    echo "         Bluetooth control will NOT work without D-Bus."
fi

# 2. Wait for the host PipeWire-Pulse socket.
# At boot the container may start before the user's (lingering) PipeWire services,
# so wait instead of giving up immediately.
HOST_UID="${HOST_UID:-1000}"
export PULSE_SERVER="${PULSE_SERVER:-unix:/run/host-user/$HOST_UID/pulse/native}"
PULSE_SOCKET="${PULSE_SERVER#unix:}"
PULSE_WAIT="${PULSE_WAIT:-120}"

echo "[Audio] Waiting for host audio socket: $PULSE_SOCKET (max ${PULSE_WAIT}s)"
for _ in $(seq 1 "$PULSE_WAIT"); do
    if [ -S "$PULSE_SOCKET" ] && pactl info >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

if pactl info >/dev/null 2>&1; then
    SERVER_NAME=$(pactl info 2>/dev/null | grep "Server Name" | head -1)
    echo "[Audio] ✔ Audio server reachable: $SERVER_NAME"
else
    echo "[Audio] ✘ Cannot reach audio server via PULSE_SERVER=$PULSE_SERVER"
    echo "         Run 'sudo ./host-setup.sh' on the host (enables linger for UID $HOST_UID)."
fi

# 3. Ensure Bluetooth controller is unblocked and powered on
echo "[Bluetooth] Powering on adapter..."
rfkill unblock bluetooth 2>&1 || true
bluetoothctl power on 2>&1 || true

# 4. Start Triggerable Radio Web Application
echo "[App] Launching Uvicorn server on port ${PORT:-8836}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8836}"
