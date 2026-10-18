# 📻 Triggerable Radio

Ev sunucunuzda (Ubuntu / Debian tabanlı herhangi bir sistemde) Docker üzerinde çalışan, belirli **HTTP GET** istekleriyle kontrol edilebilen, **Bluetooth A2DP hoparlöre otomatik bağlanan** ve bağlantı koptuğunda kesintisiz yeniden bağlanmayı deneyen modern radyo çalma uygulaması.

---

## 🎯 Özellikler

- **REST GET API ile Kontrol:**
  - `GET /radio/start` &rarr; Radyoyu başlatır (Yanıt: `200 OK` - `active`)
  - `GET /radio/stop` &rarr; Radyoyu durdurur (Yanıt: `200 OK` - `closed`)
  - `GET /radio/status` &rarr; Çalıyorsa `200 OK` (`active`), çalmıyorsa `404 Not Found` (`closed`)
- **Otomatik Bluetooth Bağlantısı ve Watchdog:**
  - Konteyner başladığında belirtilen Bluetooth MAC adresine (`AA:BB:CC:DD:EE:FF`) otomatik bağlanır.
  - Bağlantı koparsa arka plandaki izleme mekanizması her 5 saniyede bir cihazı tekrar aramaya ve bağlanmaya devam eder.
  - Hoparlör tekrar bağlandığında çalan radyo yayını otomatik olarak hoparlöre yönlendirilir.
- **Canlı Yayın Seçimi (MP3 Kararı):**
  - Doğrudan MP3 canlı yayın bağlantısı (`https://radyoilef.ankara.edu.tr/live`) tercih edilmiştir. M3U çalma listesi ayrıştırma gecikmesini ortadan kaldırarak akışın anında başlamasını sağlar. Dileyen kullanıcılar `STREAM_URL` değişkeni ile M3U adresini de tanımlayabilir.
- **Taşınabilir Docker Mimarisi:**
  - Ubuntu 26.04 LTS (ve PipeWire kullanan diğer güncel Ubuntu/Debian sürümleri) için tasarlanmıştır.
  - Host'un BlueZ (D-Bus) ve PipeWire ses sunucusunu kullanır; **kullanıcı oturumu açılmadan**, bilgisayar açılır açılmaz çalışır.
  - `docker compose` ile ya da **Portainer Stack** olarak kurulabilir.
- **Tüm Ayarlar Docker Compose Üzerinden:**
  - Port, MAC adresi, yeniden bağlanma aralığı, radyo adresi ve diğer tüm parametreler `docker-compose.yml` veya `.env` üzerinden değiştirilebilir.
- **Şık Web Kontrol Paneli (`http://localhost:8836`):**
  - Canlı spektrum görselleştirici (visualizer), ses seviyesi ayarı, anlık Bluetooth durumu, tek tıkla test ve cURL komut kopyalama araçları.

---

## 📁 Proje Yapısı

```text
triggerable-radio/
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI REST endpoint'leri ve Web UI rotaları
│   ├── bluetooth.py        # Bluetooth bağlantısı, watchdog ve A2DP yönlendirmesi
│   ├── player.py           # mpv tabanlı düşük gecikmeli ses motoru ve IPC yönetimi
│   ├── config.py           # Ortam değişkenleri ve yapılandırma
│   ├── static/
│   │   ├── css/style.css   # Modern koyu tema cam efekti (glassmorphism) stilleri
│   │   └── js/app.js       # Canlı durum sorgulama, visualizer ve etkileşimler
│   └── templates/
│       └── index.html      # Web kontrol paneli şablonu
├── Dockerfile              # BlueZ, mpv, pactl ve Python ortamı
├── docker-compose.yml      # Docker Compose dosyası (imajı kaynaktan derler)
├── portainer-stack.yml     # Portainer Web editor için stack dosyası (önceden derlenmiş imaj)
├── host-setup.sh           # Host sunucu kurulum betiği (ilk kurulumda BİR KEZ çalıştırılır)
├── .env.example            # Örnek yapılandırma dosyası (.env olarak kopyalanır)
├── .env                    # Yerel ayarlar (git'e gönderilmez)
├── LICENSE                 # GNU GPL v3
├── entrypoint.sh           # Konteyner başlangıç ve ses yönlendirme betiği
└── README.md               # Detaylı kullanım kılavuzu
```

---

## 🚀 Kurulum

Aşağıdaki adımlar radyonun çalışacağı **hedef cihazda** (Ubuntu 26.04 LTS) yapılır. Bluetooth hoparlör bu cihaza eşleştirilir; konteyner host'un Bluetooth ve ses servislerini kullanır.

### Gereksinimler

- Ubuntu 26.04 LTS (PipeWire + WirePlumber varsayılan ses sistemi)
- Bluetooth adaptörü
- `sudo` yetkisi olan **normal bir kullanıcı** (ses servisi bu kullanıcı adına çalışır; root hesabıyla kurmayın)
- Docker Engine ve Compose eklentisi:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker $USER   # sudo'suz docker için; ardından oturumu kapatıp açın
```

### 1. Projeyi Hedef Cihaza İndirin

```bash
git clone https://github.com/mertskaplan/triggerable-radio.git
cd triggerable-radio
```

### 2. Ayarları Yapılandırın (`.env`)

```bash
cp .env.example .env
nano .env   # En azından BT_DEVICE_MAC değerini kendi hoparlörünüze göre ayarlayın
```

| Değişken | Varsayılan Değer | Açıklama |
| :--- | :--- | :--- |
| `PORT` | `8836` | Uygulamanın çalışacağı port |
| `BT_DEVICE_MAC` | `AA:BB:CC:DD:EE:FF` | Hedef Bluetooth hoparlörün MAC adresi |
| `STREAM_URL` | `https://radyoilef.ankara.edu.tr/live` | Oynatılacak radyo canlı yayın adresi |
| `BT_RECONNECT_INTERVAL`| `15` | Bağlantı koptuğunda tekrar deneme süresi (saniye) |
| `AUTO_CONNECT_BT` | `true` | Konteyner başladığında hoparlöre otomatik bağlanma |
| `AUTO_RESUME_ON_BT` | `true` | Hoparlör yeniden bağlandığında yayına otomatik devam etme |
| `AUTO_START_RADIO` | `false` | Konteyner başlar başlamaz radyonun çalması |
| `AUDIO_OUTPUT` | `pulse` | mpv ses çıkış sürücüsü |
| `DEFAULT_VOLUME` | `30` | Hoparlörün açılıştaki ses seviyesi (yüzde 0-100). Sonrasında hoparlörün düğmeleriyle değiştirilebilir |
| `HOST_UID` | `1000` | Host'ta PipeWire'ı çalıştıran kullanıcının UID'si (`id -u`). `host-setup.sh` otomatik yazar |

### 3. Host Kurulumu (Bir Kez Yapılır)

Hoparlörü açın ve **eşleştirme moduna** alın (başka bir cihaza, örneğin telefonunuza bağlı olmamalı). Ardından betiği normal kullanıcınızla `sudo` üzerinden çalıştırın:

```bash
chmod +x host-setup.sh
sudo ./host-setup.sh            # MAC adresini .env'den okur
# veya: sudo ./host-setup.sh AA:BB:CC:DD:EE:FF
```

Betik şunları yapar:

1. Gerekli paketleri kurar (`bluez`, `rfkill`, `pipewire-pulse`, `wireplumber`, `libspa-0.2-bluetooth`).
2. Varsa eski PulseAudio sistem modu kurulumunun kalıntılarını temizler (PulseAudio, PipeWire ile çakışır).
3. Bluetooth adaptörünün **rfkill** engelini kaldırır, her açılışta kaldıran bir servis ekler ve adaptörün otomatik açılmasını (`AutoEnable=true`) sağlar.
4. Kullanıcı için **linger**'ı açar: PipeWire/WirePlumber bilgisayar açılınca, oturum açılmadan başlar.
5. WirePlumber'da `monitor.bluez.seat-monitoring`'i kapatır. Aksi halde aktif bir oturum yokken Bluetooth ses profili (A2DP) kaydedilmez ve bağlantı `br-connection-unknown` hatasıyla düşer.
6. Hoparlörü tarar, eşleştirir ve güvenilir (`trust`) olarak işaretler.
7. Kullanıcının UID'sini `.env` dosyasına `HOST_UID` olarak yazar.

Eşleştirme başarısız olursa hoparlörü tekrar eşleştirme moduna alıp betiği yeniden çalıştırabilir ya da elle eşleştirebilirsiniz:

```bash
bluetoothctl
  scan on
  pair AA:BB:CC:DD:EE:FF
  trust AA:BB:CC:DD:EE:FF
  connect AA:BB:CC:DD:EE:FF
  quit
```

### 4. Host Kurulumunu Doğrulayın

```bash
bluetoothctl show | grep -E "Powered|Audio Source"         # Powered: yes ve "Audio Source" görünmeli
bluetoothctl info AA:BB:CC:DD:EE:FF | grep -E "Paired|Trusted"   # ikisi de yes olmalı
loginctl show-user $USER | grep Linger                    # Linger=yes
ls -l /run/user/$(id -u)/pulse/native                     # PipeWire-Pulse soketi mevcut olmalı
```

### 5. Konteyneri Başlatın

Komut satırından:

```bash
docker compose up -d --build
docker compose logs -f
```

Portainer kullanacaksanız bu adım yerine [Portainer Stack Olarak Kurulum](#-portainer-stack-olarak-kurulum) bölümüne geçin.

Loglarda şu satırları görmelisiniz:

```text
[Audio] ✔ Audio server reachable: Server Name: PulseAudio (on PipeWire ...)
[triggerable_radio.bluetooth]: Bluetooth cihazı bağlandı: AA:BB:CC:DD:EE:FF (...)
[triggerable_radio.bluetooth]: Ses çıkışı Bluetooth hoparlöre yönlendirildi: bluez_output....
```

### 6. Açılışta Çalıştığını Test Edin

```bash
sudo reboot
```

Cihaz açıldıktan sonra **oturum açmadan**, ağdaki başka bir cihazdan:

```bash
curl http://<SUNUCU_IP>:8836/radio/start
```

Konteyner `restart: unless-stopped` ile Docker açılınca başlar; ses soketi henüz hazır değilse 120 saniyeye kadar bekler.

---

## 📡 HTTP İstekleri ile Kontrol

### 1. Radyoyu Başlatma

```bash
curl http://localhost:8836/radio/start
```

- **HTTP Kodu:** `200 OK`
- **Gövde:** `active`

---

### 2. Radyoyu Durdurma

```bash
curl http://localhost:8836/radio/stop
```

- **HTTP Kodu:** `200 OK`
- **Gövde:** `closed`

---

### 3. Radyo Durumunu Sorgulama

```bash
curl -i http://localhost:8836/radio/status
```

- **Radyo Çalıyorsa:**
  - **HTTP Kodu:** `200 OK`
  - **Gövde:** `active`
- **Radyo Çalmıyorsa:**
  - **HTTP Kodu:** `404 Not Found`
  - **Gövde:** `closed`

---

### 4. Ses Seviyesini Ayarlama

```bash
curl http://localhost:8836/radio/volume?level=50
```

- **HTTP Kodu:** `200 OK` (gövde: ayarlanan seviye) — hoparlör bağlı değilse `503`
- Ses seviyesi doğrudan **hoparlörün kendi seviyesidir**; hoparlörün ses düğmeleri, web arayüzündeki kaydırıcı ve bu istek aynı değeri değiştirir. Radyo sesi yazılımsal olarak kısılmaz.
- `DEFAULT_VOLUME` (varsayılan `%30`) yalnızca uygulama başladıktan sonra hoparlör ilk bağlandığında bir kez uygulanır; sonrasında seviyeye dokunulmaz.

---

## 🌐 Web Arayüzü & Ekstra Araçlar

Tarayıcınızdan `http://<SUNUCU_IP>:8836` adresini açarak kontrol merkezine ulaşabilirsiniz:

- **Canlı Yayın Başlat / Durdur** butonu
- **Ses Seviyesi Ayarı** (0 - 100%)
- **Bluetooth Durum Kartı:** Bağlantı durumu, hedef MAC adresi ve cihaz adı
- **Canlı Spektrum Görselleştirici:** Radyo çaldığında hareket eden modern ses dalgaları
- **Hızlı Test Araçları:** `/radio/start`, `/radio/stop` ve `/radio/status` isteklerini arayüzden test etme ve cURL komutlarını tek tıkla kopyalama
- **Swagger API Dokümantasyonu:** `http://localhost:8836/docs`

---

## ⚙️ Konteyner Yapılandırması Hakkında

Uygulama, host'un Bluetooth ve ses servislerine erişebilmek için şu parametrelerle yapılandırılmıştır:

1. **`network_mode: "host"`**: Web arayüzü/API host'un `PORT` portundan doğrudan yayınlanır.
2. **`privileged: true`**: BlueZ D-Bus soketine ve `rfkill` ile Bluetooth adaptörüne erişim sağlar.
3. **`/var/run/dbus/system_bus_socket`**: Host'un `bluetoothd` servisine `bluetoothctl` komutlarını iletmek için zorunludur.
4. **`/run/user:/run/host-user` (`rslave`)**: Host kullanıcısının PipeWire-Pulse soketini (`/run/user/<HOST_UID>/pulse/native`) konteynerle paylaşır. `rslave` sayesinde açılışta soket konteynerden sonra oluşsa bile görünür; `entrypoint.sh` soket hazır olana kadar bekler.

Konteyner çalıştığı andan itibaren hoparlör açık ve menzilde olduğu sürece otomatik olarak bağlanır, kopsa bile belirtilen aralıkta tekrar dener.

---

## 🏠 Home Assistant Entegrasyonu Örneği

`configuration.yaml` dosyanıza aşağıdaki REST komutlarını ve binary sensor'ü ekleyebilirsiniz:

```yaml
rest_command:
  triggerable_radio_start:
    url: "http://<SUNUCU_IP>:8836/radio/start"
    method: GET

  triggerable_radio_stop:
    url: "http://<SUNUCU_IP>:8836/radio/stop"
    method: GET

binary_sensor:
  - platform: rest
    name: "Triggerable Radio Durumu"
    resource: "http://<SUNUCU_IP>:8836/radio/status"
    method: GET
    # 200 dönerse on (active), 404 dönerse off (closed)
    scan_interval: 10
```

---

## 🐳 Portainer Stack Olarak Kurulum

> **Önemli:** Portainer yalnızca konteyneri yönetir. [Kurulum](#-kurulum) bölümündeki **1-4. adımlar** (özellikle `sudo ./host-setup.sh`) hedef cihazda Portainer'dan önce yapılmış olmalıdır.

Portainer'ı henüz kurmadıysanız:

```bash
docker volume create portainer_data
docker run -d --name portainer --restart=always \
  -p 9443:9443 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v portainer_data:/data \
  portainer/portainer-ce:lts
```

Ardından `https://<SUNUCU_IP>:9443` adresinden yönetici hesabını oluşturun ve **local** ortamı seçin. Stack iki yöntemle kurulabilir:

### Yöntem A — Web editor (Git deposu gerekmez)

Web editor'de proje dosyaları bulunmadığından imaj Portainer içinde derlenemez. Bu yüzden imajı önce hedef cihazda derleyin:

```bash
cd triggerable-radio
docker build -t triggerable-radio:latest .
```

1. **Stacks** → **Add stack**
2. **Name**: `triggerable-radio`
3. **Build method**: **Web editor**
4. [`portainer-stack.yml`](portainer-stack.yml) dosyasının içeriğini editöre yapıştırın.
5. **Environment variables** bölümünde değişkenleri ekleyin (**Advanced mode** ile toplu yapıştırabilirsiniz). Verilmeyenler için varsayılan değerler kullanılır; en azından şunları girin:

   ```env
   HOST_UID=1000
   BT_DEVICE_MAC=AA:BB:CC:DD:EE:FF
   ```

   `HOST_UID` değerini hedef cihazda `id -u` ile öğrenin (`host-setup.sh` de kurulum sonunda yazdırır).
6. **Deploy the stack**

> Kodu güncellediğinizde imajı tekrar derleyin (`docker build -t triggerable-radio:latest .`) ve Portainer'da stack'i açıp **Update the stack** düğmesine basın.

### Yöntem B — Repository (Git deposundan)

Portainer depoyu GitHub'dan çekip imajı kendisi derleyebilir:

1. **Stacks** → **Add stack**
2. **Name**: `triggerable-radio`
3. **Build method**: **Repository**
4. **Repository URL**: `https://github.com/mertskaplan/triggerable-radio` (kendi çatalınızı kullanıyorsanız onun adresi)
5. **Repository reference**: `refs/heads/main` (kullandığınız dal)
6. **Compose path**: `docker-compose.yml`
7. **Environment variables**: Yöntem A'daki gibi `HOST_UID`, `BT_DEVICE_MAC` vb. ekleyin. `.env` dosyası genellikle depoya eklenmediği için değişkenler burada tanımlanmalıdır.
8. **Deploy the stack**

> Depodaki değişiklikleri almak için stack sayfasında **Pull and redeploy** kullanın.

### Portainer Notları

- Stack `privileged: true` ve `network_mode: host` kullanır. Portainer'da **Settings → Security** altında *"Disable privileged mode for non-administrators"* açıksa stack'i **yönetici** hesabıyla oluşturun.
- Loglar için **Containers** → `triggerable-radio` → **Logs** sayfasını kullanın.
- Aynı cihazda hem `docker compose up` hem Portainer stack'i çalıştırmayın; `container_name` çakışır ve iki örnek aynı hoparlöre bağlanmaya çalışır.

---

## 🛠️ Sorun Giderme

- **"br-connection-unknown" hatası:**
  - Bluetooth A2DP profili kayıtlı değil demektir (PipeWire/WirePlumber çalışmıyor ya da seat-monitoring açık).
  - `bluetoothctl show` çıktısında `Audio Source` UUID'si görünmelidir. Görünmüyorsa `sudo ./host-setup.sh` çalıştırın ve `loginctl show-user $USER | grep Linger` ile `Linger=yes` olduğunu doğrulayın.
- **"Device ... not available" / "Eşleştirme başarısız":**
  - Hoparlör host'ta eşleşmemiş. Hoparlörü eşleştirme moduna alıp `sudo ./host-setup.sh` çalıştırın (ya da uygulama tarayıp kendisi eşleştirir).
- **Bluetooth Bağlanmıyor:**
  - Hoparlörün başka bir cihaza (örneğin telefonunuza) bağlı olmadığından emin olun.
  - Sunucuda Bluetooth'un soft-blocked olup olmadığını kontrol edin: `rfkill list` (Gerekirse: `sudo rfkill unblock bluetooth`). `bluetoothctl show` çıktısında `Powered: yes` olmalıdır.
- **Ses Çok Kısık / Hoparlör Düğmeleri Çalışmıyor:**
  - Seviye hoparlörün kendi seviyesidir; `curl "http://localhost:8836/radio/volume?level=60"` ile ya da hoparlörün düğmeleriyle artırın. Güncel seviye `curl http://localhost:8836/radio/debug` çıktısındaki `speaker_volume` alanında görünür.
  - Hoparlör AVRCP "absolute volume" desteklemiyorsa düğmeler yalnızca hoparlörün iç seviyesini değiştirir; bu da çalışır, ancak arayüzdeki değer değişmez.
- **Ses Gelmiyor:**
  - Konteynerden `curl http://localhost:8836/radio/debug` çağırarak ses çıkışlarını ve Bluetooth durumunu inceleyin.
  - Host'ta `pactl list short sinks` komutuyla `bluez_output.*` adında bir sink görüyor olmanız gerekir.
- **Loglarda "Cannot reach audio server":**
  - `HOST_UID` yanlış ya da linger kapalı. Host'ta `id -u` ile UID'yi kontrol edin, `.env` (veya Portainer Environment variables) içindeki `HOST_UID` ile aynı olmalı. `loginctl show-user $USER | grep Linger` çıktısı `Linger=yes` olmalı.
- **Konteyner Loglarını İnceleme:**
  ```bash
  docker compose logs -f triggerable-radio
  ```
- **Konteyneri Yeniden Başlatma:**
  ```bash
  docker compose restart
  ```

---

## 📄 Lisans

Bu proje [GNU General Public License v3.0](LICENSE) ile lisanslanmıştır.
