import asyncio
import logging
import re
import subprocess
import time
from datetime import datetime
from typing import Callable, Optional

logger = logging.getLogger("triggerable_radio.bluetooth")

class BluetoothManager:
    def __init__(self, mac_address: str, reconnect_interval: int = 5, default_volume: int = 30):
        self.mac_address: str = mac_address.strip().upper()
        self.reconnect_interval: int = max(2, reconnect_interval)
        self.default_volume: int = max(0, min(100, int(default_volume)))
        # Default volume is applied once, the first time the speaker sink appears.
        # After that the speaker's own buttons (AVRCP absolute volume) stay in control.
        self._default_volume_applied: bool = False
        self.is_connected: bool = False
        self.device_name: str = "Bilinmeyen Cihaz"
        self.last_checked_at: Optional[str] = None
        self.last_status_message: str = "Henüz başlatılmadı"
        self._watchdog_task: Optional[asyncio.Task] = None
        self._on_reconnect_callbacks: list[Callable[[], None]] = []
        self._lock = asyncio.Lock()

    def add_on_reconnect_callback(self, callback: Callable[[], None]):
        """Callback triggered when Bluetooth reconnects after being disconnected."""
        self._on_reconnect_callbacks.append(callback)

    # ──────────────────────────────────────────────
    # Low-level bluetoothctl helpers
    # ──────────────────────────────────────────────

    def _run_btctl(self, *args, timeout: int = 8) -> str:
        """Run a single bluetoothctl command and return combined stdout+stderr."""
        cmd = ["bluetoothctl"] + list(args)
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return (res.stdout + res.stderr).strip()
        except subprocess.TimeoutExpired:
            logger.debug(f"bluetoothctl timeout: {' '.join(cmd)}")
            return ""
        except Exception as e:
            logger.debug(f"bluetoothctl error: {e}")
            return ""

    def power_on_adapter(self) -> bool:
        """Ensures the host Bluetooth adapter is powered on (unblocking rfkill if needed)."""
        if "Powered: yes" in self._run_btctl("show", timeout=5):
            return True

        # A soft-blocked adapter (rfkill) silently refuses to power on
        try:
            subprocess.run(["rfkill", "unblock", "bluetooth"], capture_output=True, text=True, timeout=5)
            time.sleep(1)
        except Exception as e:
            logger.debug(f"rfkill unblock hatası: {e}")

        self._run_btctl("power", "on", timeout=5)
        if "Powered: yes" in self._run_btctl("show", timeout=5):
            logger.info("Bluetooth adaptörü açıldı.")
            return True

        logger.warning(
            "Bluetooth adaptörü açılamadı (rfkill engeli olabilir). "
            "Host'ta 'sudo rfkill unblock bluetooth' çalıştırın."
        )
        return False

    # ──────────────────────────────────────────────
    # Connection status
    # ──────────────────────────────────────────────

    def check_connection(self) -> bool:
        """Checks if the target Bluetooth device is currently connected."""
        self.last_checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            output = self._run_btctl("info", self.mac_address, timeout=5)

            # Parse device name if present
            for line in output.splitlines():
                line_strip = line.strip()
                if line_strip.startswith("Name:") or line_strip.startswith("Alias:"):
                    self.device_name = line_strip.split(":", 1)[1].strip()

            was_connected = self.is_connected
            self.is_connected = "Connected: yes" in output

            if self.is_connected:
                self.last_status_message = f"Bağlı ({self.device_name})"
                if not was_connected:
                    logger.info(f"Bluetooth cihazı bağlandı: {self.mac_address} ({self.device_name})")
            else:
                self.last_status_message = "Bağlantı kesik"
                if was_connected:
                    logger.warning(f"Bluetooth bağlantısı kesildi: {self.mac_address}")

            return self.is_connected
        except Exception as e:
            logger.error(f"Bluetooth durum kontrolü hatası: {e}")
            self.last_status_message = f"Hata: {str(e)}"
            return False

    # ──────────────────────────────────────────────
    # Audio sink management
    # ──────────────────────────────────────────────

    def get_bluetooth_sink(self) -> Optional[str]:
        """Finds the PulseAudio/PipeWire sink name corresponding to the Bluetooth speaker."""
        mac_under = self.mac_address.replace(":", "_")
        try:
            res = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True,
                text=True,
                timeout=4
            )
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        sink_name = parts[1]
                        # Match by MAC address (case-insensitive) or bluez_output prefix
                        if mac_under.lower() in sink_name.lower() or mac_under.upper() in sink_name:
                            return sink_name
        except Exception as e:
            logger.debug(f"pactl list sinks hatası: {e}")
        return None

    def _wait_for_bluetooth_sink(self, timeout: int = 10) -> Optional[str]:
        """Wait for the Bluetooth audio sink to appear in PulseAudio after connection."""
        start = time.monotonic()
        while (time.monotonic() - start) < timeout:
            sink = self.get_bluetooth_sink()
            if sink:
                return sink
            time.sleep(1)
        return None

    def get_volume(self) -> Optional[int]:
        """Returns the Bluetooth speaker volume (0-100), which follows the speaker's own buttons."""
        sink_name = self.get_bluetooth_sink()
        if not sink_name:
            return None
        try:
            res = subprocess.run(["pactl", "get-sink-volume", sink_name], capture_output=True, text=True, timeout=3)
            match = re.search(r"(\d+)%", res.stdout)
            if match:
                return int(match.group(1))
        except Exception as e:
            logger.debug(f"pactl get-sink-volume hatası: {e}")
        return None

    def set_volume(self, level: int) -> bool:
        """Sets the Bluetooth speaker volume (0-100). With AVRCP absolute volume this is the speaker's own level."""
        level = max(0, min(100, int(level)))
        sink_name = self.get_bluetooth_sink()
        if not sink_name:
            return False
        try:
            subprocess.run(["pactl", "set-sink-mute", sink_name, "0"], capture_output=True, text=True, timeout=3)
            res = subprocess.run(["pactl", "set-sink-volume", sink_name, f"{level}%"], capture_output=True, text=True, timeout=3)
            return res.returncode == 0
        except Exception as e:
            logger.warning(f"Ses seviyesi ayarlanamadı: {e}")
            return False

    def route_audio_to_bluetooth(self) -> Optional[str]:
        """Sets default audio sink to Bluetooth speaker and moves active streams to it.

        The sink volume is deliberately left alone (except for the one-time default),
        so that the speaker's volume buttons keep working.
        """
        sink_name = self.get_bluetooth_sink()
        if not sink_name:
            return None

        try:
            # 1. Set as default sink
            subprocess.run(["pactl", "set-default-sink", sink_name], capture_output=True, text=True, timeout=3)
            # 2. Apply the default volume once per application start
            if not self._default_volume_applied and self.set_volume(self.default_volume):
                self._default_volume_applied = True
                logger.info(f"Hoparlör varsayılan ses seviyesi ayarlandı: %{self.default_volume}")
            # 3. Move all active sink inputs (e.g. mpv) to this Bluetooth sink
            res_inputs = subprocess.run(["pactl", "list", "short", "sink-inputs"], capture_output=True, text=True, timeout=3)
            if res_inputs.returncode == 0:
                for line in res_inputs.stdout.splitlines():
                    parts = line.split()
                    if parts:
                        input_id = parts[0]
                        subprocess.run(["pactl", "move-sink-input", input_id, sink_name], capture_output=True, text=True, timeout=2)

            logger.info(f"Ses çıkışı Bluetooth hoparlöre yönlendirildi: {sink_name}")
            return sink_name
        except Exception as e:
            logger.warning(f"Ses yönlendirme hatası: {e}")
            return None

    # ──────────────────────────────────────────────
    # Connection logic
    # ──────────────────────────────────────────────

    def connect_sync(self) -> tuple[bool, str]:
        """Attempts to trust, pair (if needed), and connect to the target Bluetooth MAC address.
        
        Uses individual bluetoothctl commands instead of piping to interactive mode
        for reliability in containerized environments.
        """
        logger.info(f"Bluetooth cihazına bağlanılıyor: {self.mac_address}...")

        # Step 1: Power on adapter
        if not self.power_on_adapter():
            self.last_status_message = "Bluetooth adaptörü kapalı/engelli (rfkill)"
            return False, self.last_status_message

        # Step 2: Check if already paired, if not, discover and pair
        info_out = self._run_btctl("info", self.mac_address, timeout=5)
        if "Paired: no" in info_out or "not available" in info_out.lower():
            if "not available" in info_out.lower():
                # Unknown devices must be discovered before they can be paired
                logger.info("Cihaz tanınmıyor. Taranıyor (hoparlör eşleştirme modunda olmalı)...")
                self._run_btctl("--timeout", "10", "scan", "on", timeout=15)
            logger.info("Cihaz henüz eşleşmemiş. Eşleştirme deneniyor...")
            pair_out = self._run_btctl("pair", self.mac_address, timeout=20)
            logger.debug(f"pair: {pair_out}")
            if "successful" not in pair_out.lower() and "already" not in pair_out.lower():
                last_line = pair_out.splitlines()[-1] if pair_out else "Bilinmeyen hata"
                self.last_status_message = f"Eşleştirme başarısız: {last_line}"
                return False, self.last_status_message

        # Step 3: Trust the device (so it auto-reconnects)
        trust_out = self._run_btctl("trust", self.mac_address, timeout=5)
        logger.debug(f"trust: {trust_out}")

        # Step 4: Connect
        connect_out = self._run_btctl("connect", self.mac_address, timeout=12)
        logger.debug(f"connect output: {connect_out}")

        # Check result
        if "Connection successful" in connect_out:
            self.is_connected = True
            self.last_status_message = "Bağlantı başarılı"

            # Wait for the Bluetooth audio sink to appear
            logger.info("Bluetooth ses çıkışı (A2DP sink) bekleniyor...")
            sink = self._wait_for_bluetooth_sink(timeout=8)
            if sink:
                logger.info(f"Bluetooth ses çıkışı bulundu: {sink}")
                self.route_audio_to_bluetooth()
            else:
                logger.warning("Bluetooth bağlandı ama ses çıkışı (sink) bulunamadı. Host'ta PipeWire/WirePlumber çalışıyor mu? (sudo ./host-setup.sh)")

            return True, "Bağlantı başarılı"

        # If connection failed, verify via info (sometimes output is misleading)
        if self.check_connection():
            sink = self._wait_for_bluetooth_sink(timeout=8)
            if sink:
                self.route_audio_to_bluetooth()
            return True, "Bağlantı başarılı"

        # Parse error details
        error_msg = connect_out.strip().splitlines()[-1] if connect_out.strip() else "Bağlantı kurulamadı"
        if "br-connection-unknown" in connect_out:
            error_msg = (
                "br-connection-unknown: A2DP ses profili backend'i bulunamadı. "
                "Host'ta PipeWire/WirePlumber oturum açılmadan çalışmıyor olabilir; "
                "'sudo ./host-setup.sh' çalıştırın."
            )
        elif "br-connection-refused" in connect_out:
            error_msg = "br-connection-refused: Cihaz bağlantıyı reddetti. Hoparlör eşleşme modunda mı?"
        elif "not available" in connect_out.lower():
            error_msg = "Cihaz bulunamadı. Hoparlör açık ve yakında mı?"

        self.last_status_message = f"Bağlantı hatası: {error_msg}"
        return False, error_msg

    async def connect_async(self) -> tuple[bool, str]:
        """Asynchronous wrapper for connecting."""
        async with self._lock:
            return await asyncio.to_thread(self.connect_sync)

    # ──────────────────────────────────────────────
    # Watchdog
    # ──────────────────────────────────────────────

    async def _watchdog_loop(self):
        """Continuously monitors Bluetooth connection and reconnects if dropped."""
        logger.info(f"Bluetooth İzleme (Watchdog) devrede. Hedef MAC: {self.mac_address}, Aralık: {self.reconnect_interval}s")
        
        # Initial connection attempt
        success, msg = await self.connect_async()
        if not success:
            logger.warning(f"[Watchdog] İlk bağlantı denemesi başarısız: {msg}")
        fail_count = 0

        while True:
            try:
                await asyncio.sleep(self.reconnect_interval)
                connected = await asyncio.to_thread(self.check_connection)

                if not connected:
                    fail_count += 1
                    # Log first failure or once every 5 cycles to keep logs clean
                    if fail_count == 1 or fail_count % 5 == 0:
                        logger.warning(
                            f"[Watchdog] {self.mac_address} bağlı değil (Deneme #{fail_count}). Yeniden bağlanılıyor..."
                        )
                    else:
                        logger.debug(f"[Watchdog] Yeniden bağlanma denemesi #{fail_count}")

                    success, msg = await self.connect_async()
                    if not success and (fail_count == 1 or fail_count % 5 == 0):
                        logger.warning(f"[Watchdog] Bağlantı başarısız: {msg}")
                    if success:
                        fail_count = 0
                        logger.info(f"[Watchdog] Başarıyla yeniden bağlandı: {self.mac_address}")
                        # Notify listeners (e.g. to resume audio if needed)
                        for cb in self._on_reconnect_callbacks:
                            try:
                                if asyncio.iscoroutinefunction(cb):
                                    await cb()
                                else:
                                    cb()
                            except Exception as e:
                                logger.error(f"Reconnect callback hatası: {e}")
                else:
                    fail_count = 0
                    # Periodically ensure audio sink is routed to bluetooth
                    await asyncio.to_thread(self.route_audio_to_bluetooth)


            except asyncio.CancelledError:
                logger.info("Bluetooth watchdog durduruldu.")
                break
            except Exception as e:
                logger.error(f"Watchdog döngüsü beklenmeyen hata: {e}")
                await asyncio.sleep(self.reconnect_interval)

    def start_watchdog(self):
        """Starts the background reconnection task."""
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())

    def stop_watchdog(self):
        """Stops the background watchdog."""
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()

    def get_info(self) -> dict:
        return {
            "mac_address": self.mac_address,
            "device_name": self.device_name,
            "is_connected": self.is_connected,
            "last_checked_at": self.last_checked_at,
            "last_status_message": self.last_status_message,
            "reconnect_interval": self.reconnect_interval,
        }
