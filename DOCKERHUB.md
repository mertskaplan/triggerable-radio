# 📻 Triggerable Radio

**HTTP GET** istekleriyle kontrol edilen, bilgisayar açılır açılmaz — **kullanıcı oturumu açılmadan** — **Bluetooth A2DP hoparlöre** bağlanıp internet radyosu çalan Docker uygulaması. Akıllı ev sistemleri (Home Assistant vb.) ile tetiklenmek için tasarlanmıştır.

- **Kaynak kod ve ayrıntılı belgeler:** https://github.com/mertskaplan/triggerable-radio
- **Lisans:** [GPL-3.0](https://github.com/mertskaplan/triggerable-radio/blob/main/LICENSE)

## Etiketler

| Etiket | Açıklama |
| :--- | :--- |
| `latest` | En son kararlı sürüm |
| `1.0` | v1.0 sürümü |

Platform: `linux/amd64`

## Özellikler

- `GET /radio/start`, `/radio/stop`, `/radio/status` ile basit kontrol
- Hoparlöre otomatik bağlanma; bağlantı koparsa sürekli yeniden deneme ve yayına kaldığı yerden devam
- Ses seviyesi hoparlörün kendi düğmeleriyle senkron (`/radio/volume`, açılışta %30)
- Web kontrol paneli: `http://<SUNUCU_IP>:8836`
- `docker compose` veya **Portainer Stack** ile kurulum

## Nasıl Çalışır?

Konteyner Bluetooth ve ses için **host'un** servislerini kullanır: BlueZ'a sistem D-Bus'ı üzerinden, sese ise host kullanıcısının PipeWire-Pulse soketi üzerinden erişir. Bu nedenle host'ta bir kez kurulum betiği çalıştırılması gerekir. Betik:

- Bluetooth adaptörünün rfkill engelini kaldırır ve açılışta otomatik açılmasını sağlar,
- PipeWire'ın oturum açılmadan başlaması için kullanıcıya **linger** tanımlar,
- WirePlumber'ın oturum yokken de Bluetooth ses profilini (A2DP) kaydetmesini sağlar,
- hoparlörü eşleştirir.

Desteklenen host: **Ubuntu 26.04 LTS** (PipeWire + WirePlumber kullanan güncel Ubuntu/Debian sürümleri).

## Hızlı Başlangıç

```bash
mkdir -p ~/triggerable-radio && cd ~/triggerable-radio
BASE=https://raw.githubusercontent.com/mertskaplan/triggerable-radio/main
curl -fsSLO $BASE/docker-compose.yml
curl -fsSLO $BASE/host-setup.sh
curl -fsSL  $BASE/.env.example -o .env

nano .env                 # BT_DEVICE_MAC değerini hoparlörünüze göre ayarlayın

chmod +x host-setup.sh
sudo ./host-setup.sh      # hoparlör eşleştirme modundayken; bir kez yeterli

docker compose up -d
docker compose logs -f
```

Test:

```bash
curl http://localhost:8836/radio/start    # 200 active
curl -i http://localhost:8836/radio/status # 200 active / 404 closed
curl http://localhost:8836/radio/stop     # 200 closed
```

## Portainer

1. Önce host'ta `sudo ./host-setup.sh` çalıştırın (yukarıdaki gibi).
2. **Stacks → Add stack → Web editor**, [docker-compose.yml](https://github.com/mertskaplan/triggerable-radio/blob/main/docker-compose.yml) içeriğini yapıştırın.
3. **Environment variables** bölümüne en azından şunları ekleyin:
   ```env
   BT_DEVICE_MAC=AA:BB:CC:DD:EE:FF
   HOST_UID=1000
   ```
   `HOST_UID`, host'ta `id -u` çıktısıdır (`host-setup.sh` kurulum sonunda yazdırır).
4. **Deploy the stack**. Stack'i yönetici hesabıyla oluşturun (`privileged` gerektirir).

## Ortam Değişkenleri

| Değişken | Varsayılan | Açıklama |
| :--- | :--- | :--- |
| `BT_DEVICE_MAC` | `AA:BB:CC:DD:EE:FF` | Hoparlörün MAC adresi (**zorunlu**) |
| `HOST_UID` | `1000` | Host'ta PipeWire'ı çalıştıran kullanıcının UID'si |
| `PORT` | `8836` | Web arayüzü / API portu |
| `STREAM_URL` | `https://radyoilef.ankara.edu.tr/live` | Radyo yayın adresi |
| `DEFAULT_VOLUME` | `30` | Açılıştaki hoparlör ses seviyesi (0-100) |
| `BT_RECONNECT_INTERVAL` | `15` | Yeniden bağlanma aralığı (saniye) |
| `AUTO_CONNECT_BT` | `true` | Açılışta hoparlöre otomatik bağlanma |
| `AUTO_RESUME_ON_BT` | `true` | Hoparlör geri geldiğinde yayına devam etme |
| `AUTO_START_RADIO` | `false` | Konteyner başlar başlamaz çalma |
| `IMAGE_TAG` | `latest` | Kullanılacak imaj sürümü |

## Gerekli Konteyner Ayarları

`docker-compose.yml` bunları zaten içerir; `docker run` ile çalıştıracaksanız aynılarını verin:

| Ayar | Neden |
| :--- | :--- |
| `network_mode: host` | API/web arayüzü host portundan yayınlanır |
| `privileged: true` | BlueZ D-Bus ve rfkill erişimi |
| `/var/run/dbus/system_bus_socket` (bind) | Host `bluetoothd` kontrolü |
| `/run/user` → `/run/host-user` (bind, `ro`, `rslave`) | Host PipeWire-Pulse soketi |
| `PULSE_SERVER=unix:/run/host-user/<HOST_UID>/pulse/native` | Ses sunucusu adresi |

## Güncelleme

```bash
docker compose pull && docker compose up -d
```

Sorun giderme ve Home Assistant entegrasyonu için: https://github.com/mertskaplan/triggerable-radio#readme
