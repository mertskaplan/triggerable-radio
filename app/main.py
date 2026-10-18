import asyncio
import collections
import logging
import os
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Query, Request, Response

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.bluetooth import BluetoothManager
from app.config import settings
from app.player import RadioPlayer

# In-memory log buffer for Web UI
log_buffer = collections.deque(maxlen=100)

class BufferLogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_buffer.append({"time": timestamp, "level": record.levelname, "message": msg})
        except Exception:
            pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
root_logger = logging.getLogger()
buffer_handler = BufferLogHandler()
buffer_handler.setFormatter(logging.Formatter("%(message)s"))
root_logger.addHandler(buffer_handler)

logger = logging.getLogger("triggerable_radio.main")

# Initialize Bluetooth and Player managers
bt_manager = BluetoothManager(
    mac_address=settings.BT_DEVICE_MAC,
    reconnect_interval=settings.BT_RECONNECT_INTERVAL,
    default_volume=settings.DEFAULT_VOLUME
)

player = RadioPlayer(
    default_stream_url=settings.STREAM_URL,
    audio_output=settings.AUDIO_OUTPUT,
    auto_resume_on_bt=settings.AUTO_RESUME_ON_BT
)

# Connect reconnect callback from Bluetooth to Player
bt_manager.add_on_reconnect_callback(player.on_bluetooth_reconnected)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Triggerable Radio başlatılıyor...")
    logger.info(f"Hedef Bluetooth MAC: {settings.BT_DEVICE_MAC}")
    logger.info(f"Varsayılan Radyo Akışı: {settings.STREAM_URL}")
    
    # Start Bluetooth reconnect watchdog if enabled
    if settings.AUTO_CONNECT_BT:
        bt_manager.start_watchdog()

    # Auto start radio if requested in settings
    if settings.AUTO_START_RADIO:
        logger.info("AUTO_START_RADIO devrede, radyo akışı başlatılıyor...")
        player.start()

    yield

    logger.info("Triggerable Radio kapatılıyor...")
    bt_manager.stop_watchdog()
    player.stop()


app = FastAPI(
    title="Triggerable Radio",
    description="Ev sunucusu için REST GET kontrollü, otomatik Bluetooth yeniden bağlanmalı radyo çalıcı.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static and templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# ==========================================
# CORE REQUIRED GET ENDPOINTS
# ==========================================

@app.get("/radio/start", response_class=PlainTextResponse)
def radio_start(url: Optional[str] = Query(None, description="Opsiyonel özel radyo akış URL'si")):
    """
    Radyo çalmayı başlatır.
    İstek: GET http://localhost:8836/radio/start
    Yanıt: 200 OK (body: active)
    """
    bt_manager.route_audio_to_bluetooth()
    success, state = player.start(stream_url=url)
    # Ensure audio moves to bluetooth sink
    bt_manager.route_audio_to_bluetooth()
    logger.info(f"GET /radio/start çağrıldı -> Durum: {state}")
    return PlainTextResponse(content="active", status_code=200)



@app.get("/radio/stop", response_class=PlainTextResponse)
def radio_stop():
    """
    Radyo çalmayı durdurur.
    İstek: GET http://localhost:8836/radio/stop
    Yanıt: 200 OK (body: closed)
    """
    success, state = player.stop()
    logger.info(f"GET /radio/stop çağrıldı -> Durum: {state}")
    return PlainTextResponse(content="closed", status_code=200)


@app.get("/radio/status")
def radio_status():
    """
    Radyo durumunu döner.
    İstek: GET http://localhost:8836/radio/status
    - Radyo çalıyorsa: 200 OK (body: active)
    - Radyo çalmıyorsa: 404 Not Found (body: closed)
    """
    if player.is_active():
        return Response(content="active", media_type="text/plain; charset=utf-8", status_code=200)
    else:
        return Response(content="closed", media_type="text/plain; charset=utf-8", status_code=404)


# ==========================================
# ADDITIONAL CONVENIENCE & WEB DASHBOARD ENDPOINTS
# ==========================================

@app.get("/radio/toggle", response_class=PlainTextResponse)
def radio_toggle():
    """Radyo çalıyorsa durdurur, çalmıyorsa başlatır."""
    if player.is_active():
        player.stop()
        return PlainTextResponse(content="closed", status_code=200)
    else:
        player.start()
        return PlainTextResponse(content="active", status_code=200)


@app.get("/radio/volume", response_class=PlainTextResponse)
def radio_volume(level: int = Query(..., ge=0, le=100, description="Ses seviyesi 0-100")):
    """Hoparlörün ses seviyesini ayarlar (hoparlörün kendi ses düğmeleriyle aynı seviye)."""
    if not bt_manager.set_volume(level):
        return PlainTextResponse(content="Bluetooth hoparlör bağlı değil", status_code=503)
    return PlainTextResponse(content=str(level), status_code=200)


def current_volume() -> int:
    """Hoparlörün güncel ses seviyesi; hoparlör bağlı değilse varsayılan seviye."""
    volume = bt_manager.get_volume()
    return volume if volume is not None else settings.DEFAULT_VOLUME


@app.get("/radio/bluetooth/reconnect")
async def bluetooth_manual_reconnect():
    """Bluetooth cihazına manuel anlık yeniden bağlanma tetikler."""
    success, message = await bt_manager.connect_async()
    return JSONResponse({
        "success": success,
        "message": message,
        "is_connected": bt_manager.is_connected,
        "mac_address": bt_manager.mac_address
    })


@app.get("/radio/debug")
def radio_debug():
    """Ses çıkışları ve Bluetooth durumunu detaylı inceleme endpoint'i."""
    sinks_out = subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True, text=True, timeout=3).stdout
    inputs_out = subprocess.run(["pactl", "list", "short", "sink-inputs"], capture_output=True, text=True, timeout=3).stdout
    bt_info = subprocess.run(["bluetoothctl", "info", settings.BT_DEVICE_MAC], capture_output=True, text=True, timeout=3).stdout
    pactl_info = subprocess.run(["pactl", "info"], capture_output=True, text=True, timeout=3).stdout

    return JSONResponse({
        "pulse_server": os.getenv("PULSE_SERVER"),
        "pactl_info": pactl_info.splitlines()[:6],
        "sinks": sinks_out.splitlines(),
        "sink_inputs": inputs_out.splitlines(),
        "bluetooth_info": bt_info.splitlines(),
        "player_is_active": player.is_active(),
        "speaker_volume": bt_manager.get_volume(),
        "bluetooth_sink_found": bt_manager.get_bluetooth_sink()
    })


@app.get("/api/status")
def api_status():

    """Web arayüzü ve akıllı ev sistemleri için detaylı JSON durum çıktısı."""
    is_playing = player.is_active()
    return JSONResponse({
        "radio": {
            "status": "active" if is_playing else "closed",
            "is_playing": is_playing,
            "stream_url": player.current_stream_url,
            "started_at": player.started_at,
            "volume": current_volume(),
            "audio_output": player.audio_output,
        },
        "bluetooth": bt_manager.get_info(),
        "app": {
            "name": settings.APP_NAME,
            "port": settings.PORT,
            "auto_connect_bt": settings.AUTO_CONNECT_BT,
            "auto_resume_on_bt": settings.AUTO_RESUME_ON_BT,
        }
    })


@app.get("/api/logs")
def api_logs():
    """Son olay ve logları döner."""
    return JSONResponse(list(log_buffer))


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    """Modern, şık Web Kontrol Paneli."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": settings.APP_NAME,
            "port": settings.PORT,
            "bt_mac": settings.BT_DEVICE_MAC,
            "stream_url": settings.STREAM_URL,
            "m3u_url": "https://radyoilef.ankara.edu.tr/dinle.m3u",
            "is_playing": player.is_active(),
            "bt_connected": bt_manager.is_connected,
            "bt_device_name": bt_manager.device_name,
            "volume": current_volume(),
        }
    )

