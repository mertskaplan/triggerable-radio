import asyncio
import json
import logging
import os
import socket
import subprocess
from datetime import datetime
from typing import Optional

logger = logging.getLogger("triggerable_radio.player")

IPC_SOCKET_PATH = "/tmp/mpv.socket"

class RadioPlayer:
    def __init__(self, default_stream_url: str, audio_output: str = "pulse,alsa", auto_resume_on_bt: bool = True):
        self.default_stream_url: str = default_stream_url
        self.current_stream_url: str = default_stream_url
        self.audio_output: str = audio_output
        self.auto_resume_on_bt: bool = auto_resume_on_bt
        
        self.process: Optional[subprocess.Popen] = None
        self.started_at: Optional[str] = None
        self.should_be_playing: bool = False
        self._lock = asyncio.Lock()

    def is_active(self) -> bool:
        """Returns True if the radio player process is actively running."""
        if self.process is not None:
            if self.process.poll() is None:
                return True
            else:
                self.process = None
        return False

    def _send_ipc_command(self, command: list) -> Optional[dict]:
        """Sends a JSON-IPC command to mpv over the unix domain socket."""
        if not os.path.exists(IPC_SOCKET_PATH):
            return None
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(1.5)
            client.connect(IPC_SOCKET_PATH)
            cmd_data = json.dumps({"command": command}) + "\n"
            client.sendall(cmd_data.encode("utf-8"))
            response = client.recv(4096).decode("utf-8")
            client.close()
            return json.loads(response)
        except Exception as e:
            logger.debug(f"mpv IPC komut hatası: {e}")
            return None

    def start(self, stream_url: Optional[str] = None) -> tuple[bool, str]:
        """Starts radio stream playback using mpv."""
        if self.is_active():
            return True, "active"

        # Clean old IPC socket if leftover
        if os.path.exists(IPC_SOCKET_PATH):
            try:
                os.remove(IPC_SOCKET_PATH)
            except OSError:
                pass

        target_url = stream_url.strip() if stream_url else self.default_stream_url
        self.current_stream_url = target_url
        self.should_be_playing = True

        # Check if Bluetooth audio sink is available to directly target it
        bt_sink = None
        try:
            res_sinks = subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True, text=True, timeout=3)
            if res_sinks.returncode == 0:
                for line in res_sinks.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and "bluez_output" in parts[1].lower():
                        bt_sink = parts[1]
                        break
        except Exception:
            pass

        cmd = [
            "mpv",
            "--no-video",
            "--idle=no",
            "--force-window=no",
            # No software attenuation: loudness is controlled by the speaker (sink) volume
            "--volume=100",
            f"--input-ipc-server={IPC_SOCKET_PATH}",
            "--stream-lavf-o=reconnect=1,reconnect_streamed=1,reconnect_delay_max=5",
            f"--ao={self.audio_output}",
        ]
        
        if bt_sink:
            logger.info(f"mpv doğrudan Bluetooth ses çıkışına yönlendiriliyor: {bt_sink}")
            cmd.append(f"--audio-device=pulse/{bt_sink}")

        cmd.append(target_url)

        logger.info(f"Radyo akışı başlatılıyor: {target_url} (Ses Çıkışı: {self.audio_output})")

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True
            )
            self.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return True, "active"
        except Exception as e:
            logger.error(f"mpv başlatılamadı: {e}")
            self.process = None
            self.should_be_playing = False
            return False, f"Hata: {str(e)}"

    def stop(self) -> tuple[bool, str]:
        """Stops radio stream playback."""
        self.should_be_playing = False
        
        if not self.is_active() and self.process is None:
            return True, "closed"

        try:
            # Try gentle quit via IPC first
            self._send_ipc_command(["quit"])
        except Exception:
            pass

        if self.process is not None:
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=1)
            except Exception as e:
                logger.warning(f"mpv sonlandırma hatası: {e}")

        self.process = None
        self.started_at = None

        if os.path.exists(IPC_SOCKET_PATH):
            try:
                os.remove(IPC_SOCKET_PATH)
            except OSError:
                pass

        logger.info("Radyo akışı durduruldu.")
        return True, "closed"

    def on_bluetooth_reconnected(self):
        """Called when Bluetooth watchdog detects that device has reconnected."""
        logger.info("[Player] Bluetooth yeniden bağlandı sinyali alındı.")
        if self.auto_resume_on_bt and self.should_be_playing:
            if not self.is_active():
                logger.info("[Player] Radyo yeniden başlatılıyor (Bluetooth bağlantısı sonrası)...")
                self.start(self.current_stream_url)

    def get_info(self) -> dict:
        is_playing = self.is_active()
        return {
            "status": "active" if is_playing else "closed",
            "is_playing": is_playing,
            "stream_url": self.current_stream_url,
            "started_at": self.started_at,
            "audio_output": self.audio_output
        }
