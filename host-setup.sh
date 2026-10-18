#!/bin/bash
# ==========================================================
# Triggerable Radio — Host Sunucu Kurulum Betiği
# ==========================================================
# Bu betik, konteyner çalıştırılmadan ÖNCE hedef Ubuntu/Debian
# sunucusunda BİR KEZ çalıştırılmalıdır.
#
# Mimari:
#   - Ses sunucusu olarak host'un kendi PipeWire + WirePlumber'ı kullanılır
#     (Ubuntu 22.10+ varsayılanı). PulseAudio kurulmaz; pipewire-pulse ile çakışır.
#   - "linger" sayesinde kullanıcının PipeWire servisleri, oturum açılmadan
#     bilgisayar açılır açılmaz başlar.
#   - WirePlumber'ın "seat-monitoring" özelliği kapatılır; aksi halde aktif bir
#     grafik oturum yokken Bluetooth ses profili (A2DP) kaydedilmez ve bağlantı
#     "br-connection-unknown" hatasıyla düşer.
#   - Bluetooth adaptörünün rfkill engeli her açılışta kaldırılır.
#
# Kullanım:
#   chmod +x host-setup.sh
#   sudo ./host-setup.sh [HOPARLÖR_MAC]
# ==========================================================

set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "Bu betik root yetkisi gerektirir: sudo ./host-setup.sh"
    exit 1
fi

CURRENT_USER="${SUDO_USER:-$(logname 2>/dev/null || echo "$USER")}"
USER_ID=$(id -u "$CURRENT_USER")
USER_HOME=$(getent passwd "$CURRENT_USER" | cut -d: -f6)
BT_MAC="${1:-$(grep -E '^BT_DEVICE_MAC=' "$(dirname "$0")/.env" 2>/dev/null | cut -d= -f2)}"
BT_MAC="${BT_MAC:-AA:BB:CC:DD:EE:FF}"

as_user() {
    sudo -u "$CURRENT_USER" XDG_RUNTIME_DIR="/run/user/$USER_ID" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$USER_ID/bus" "$@"
}

echo "=========================================================="
echo " Triggerable Radio — Host Kurulumu"
echo "=========================================================="
echo " Kullanıcı: $CURRENT_USER (UID: $USER_ID)"
echo " Hoparlör : $BT_MAC"
echo "=========================================================="

# 1. Paketler
echo ""
echo "[1/6] Bluetooth ve PipeWire paketleri kontrol ediliyor..."
apt-get update -qq
apt-get install -y -qq bluez rfkill pipewire pipewire-pulse wireplumber libspa-0.2-bluetooth
echo "  ✔ Paketler yüklü."

# 2. Eski (PulseAudio system mode) kurulum kalıntılarını temizle
echo ""
echo "[2/6] Eski PulseAudio sistem modu kalıntıları temizleniyor..."
if [ -f /etc/systemd/system/pulseaudio-system.service ]; then
    systemctl disable --now pulseaudio-system.service 2>/dev/null || true
    rm -f /etc/systemd/system/pulseaudio-system.service
fi
rm -f /etc/dbus-1/system.d/pulseaudio-bluetooth.conf
rm -f "$USER_HOME/.config/wireplumber/wireplumber.conf.d/51-disable-bluetooth.conf"
echo "  ✔ Temizlendi."

# 3. Bluetooth adaptörünü aç ve her açılışta rfkill engelini kaldır
echo ""
echo "[3/6] Bluetooth adaptörü etkinleştiriliyor..."
rfkill unblock bluetooth
cat > /etc/systemd/system/bluetooth-rfkill-unblock.service <<'EOF'
[Unit]
Description=Unblock Bluetooth rfkill (Triggerable Radio)
After=systemd-rfkill.service
Before=bluetooth.service

[Service]
Type=oneshot
ExecStart=/usr/sbin/rfkill unblock bluetooth

[Install]
WantedBy=bluetooth.target multi-user.target
EOF

# Adaptörün açılışta otomatik güçlendirilmesi
if grep -qE '^\s*AutoEnable\s*=' /etc/bluetooth/main.conf; then
    sed -i -E 's/^\s*AutoEnable\s*=.*/AutoEnable=true/' /etc/bluetooth/main.conf
elif grep -qE '^\s*\[Policy\]' /etc/bluetooth/main.conf; then
    sed -i -E '/^\s*\[Policy\]/a AutoEnable=true' /etc/bluetooth/main.conf
else
    printf '\n[Policy]\nAutoEnable=true\n' >> /etc/bluetooth/main.conf
fi

systemctl daemon-reload
systemctl enable bluetooth-rfkill-unblock.service
systemctl enable bluetooth.service
systemctl restart bluetooth.service
sleep 2
bluetoothctl power on >/dev/null 2>&1 || true
if bluetoothctl show | grep -q "Powered: yes"; then
    echo "  ✔ Bluetooth adaptörü açık."
else
    echo "  ✘ Bluetooth adaptörü açılamadı! 'rfkill list' ve 'bluetoothctl show' ile kontrol edin."
fi

# 4. Kullanıcı servislerinin oturum açılmadan başlaması (linger)
echo ""
echo "[4/6] Oturum açılmadan ses servisinin başlaması için linger etkinleştiriliyor..."
loginctl enable-linger "$CURRENT_USER"
# linger açıldığında user@UID servisi ve /run/user/UID oluşur
for _ in $(seq 1 10); do
    [ -S "/run/user/$USER_ID/bus" ] && break
    sleep 1
done
as_user systemctl --user enable pipewire.socket pipewire-pulse.socket wireplumber.service >/dev/null 2>&1 || true
echo "  ✔ Linger etkin."

# 5. WirePlumber: aktif oturum (seat) olmadan da Bluetooth'u yönet
echo ""
echo "[5/6] WirePlumber Bluetooth yapılandırması yazılıyor..."
WP_CONF_DIR="$USER_HOME/.config/wireplumber/wireplumber.conf.d"
mkdir -p "$WP_CONF_DIR"
cat > "$WP_CONF_DIR/80-triggerable-radio.conf" <<'EOF'
# Triggerable Radio: grafik oturum açılmamışken de Bluetooth ses profillerini
# (A2DP) kaydet. Varsayılan "seat-monitoring", aktif bir oturum yokken
# Bluetooth monitörünü kapatır.
wireplumber.profiles = {
  main = {
    monitor.bluez.seat-monitoring = disabled
  }
}

# Hoparlörü kulaklık (HSP/HFP) profiline geçirme; her zaman A2DP kalsın
wireplumber.settings = {
  bluetooth.autoswitch-to-headset-profile = false
}
EOF
chown -R "$CURRENT_USER:$CURRENT_USER" "$USER_HOME/.config/wireplumber"
as_user systemctl --user restart wireplumber pipewire pipewire-pulse 2>/dev/null || true
sleep 2
if [ -S "/run/user/$USER_ID/pulse/native" ]; then
    echo "  ✔ PipeWire-Pulse soketi hazır: /run/user/$USER_ID/pulse/native"
else
    echo "  ✘ PipeWire-Pulse soketi bulunamadı! 'systemctl --user status pipewire-pulse' ile kontrol edin."
fi

# 6. Hoparlörü eşleştir
echo ""
echo "[6/6] Bluetooth hoparlör eşleştirme ($BT_MAC)"
if bluetoothctl info "$BT_MAC" 2>/dev/null | grep -q "Paired: yes"; then
    echo "  ✔ Hoparlör zaten eşleşmiş."
    bluetoothctl trust "$BT_MAC" >/dev/null 2>&1 || true
else
    echo "  Hoparlörü EŞLEŞTİRME MODUNA alın. 20 saniye taranacak..."
    bluetoothctl --timeout 20 scan on >/dev/null 2>&1 || true
    if bluetoothctl pair "$BT_MAC" 2>&1 | grep -qiE "successful|already"; then
        bluetoothctl trust "$BT_MAC" >/dev/null 2>&1 || true
        echo "  ✔ Hoparlör eşleşti ve güvenilir olarak işaretlendi."
    else
        echo "  ✘ Eşleştirme başarısız. Hoparlör eşleştirme modundayken betiği tekrar"
        echo "    çalıştırın ya da elle eşleştirin:"
        echo "      bluetoothctl"
        echo "      scan on"
        echo "      pair $BT_MAC"
        echo "      trust $BT_MAC"
    fi
fi
bluetoothctl connect "$BT_MAC" >/dev/null 2>&1 || true

# Konteynerin doğru PipeWire soketini bulması için HOST_UID'yi .env'e yaz
ENV_FILE="$(cd "$(dirname "$0")" && pwd)/.env"
if [ ! -f "$ENV_FILE" ] && [ -f "$(dirname "$ENV_FILE")/.env.example" ]; then
    cp "$(dirname "$ENV_FILE")/.env.example" "$ENV_FILE"
    chown "$CURRENT_USER:$CURRENT_USER" "$ENV_FILE"
fi
if [ -f "$ENV_FILE" ]; then
    if grep -qE '^HOST_UID=' "$ENV_FILE"; then
        sed -i -E "s/^HOST_UID=.*/HOST_UID=$USER_ID/" "$ENV_FILE"
    else
        printf '\nHOST_UID=%s\n' "$USER_ID" >> "$ENV_FILE"
    fi
    echo "  ✔ .env: HOST_UID=$USER_ID"
fi

echo ""
echo "=========================================================="
echo " ✔ Host kurulumu tamamlandı!"
echo ""
echo " Konteyneri başlatın (imaj Docker Hub'dan çekilir):"
echo "   docker compose up -d"
echo ""
echo " Portainer kullanıyorsanız stack'in Environment variables"
echo " bölümüne şunu ekleyin:  HOST_UID=$USER_ID"
echo "=========================================================="
