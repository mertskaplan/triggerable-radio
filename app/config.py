import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "Triggerable Radio"
    PORT: int = int(os.getenv("PORT", "8836"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    
    # Bluetooth settings
    BT_DEVICE_MAC: str = os.getenv("BT_DEVICE_MAC", "AA:BB:CC:DD:EE:FF").strip().upper()
    BT_RECONNECT_INTERVAL: int = int(os.getenv("BT_RECONNECT_INTERVAL", "5"))
    AUTO_CONNECT_BT: bool = os.getenv("AUTO_CONNECT_BT", "true").lower() in ("true", "1", "yes")
    AUTO_RESUME_ON_BT: bool = os.getenv("AUTO_RESUME_ON_BT", "true").lower() in ("true", "1", "yes")
    
    # Radio Stream settings
    # Primary live MP3 stream chosen for lower latency and direct audio pipeline
    STREAM_URL: str = os.getenv("STREAM_URL", "https://radyoilef.ankara.edu.tr/live")
    AUTO_START_RADIO: bool = os.getenv("AUTO_START_RADIO", "false").lower() in ("true", "1", "yes")
    
    # Audio backend settings
    AUDIO_OUTPUT: str = os.getenv("AUDIO_OUTPUT", "pulse,alsa")
    PULSE_SERVER: str = os.getenv("PULSE_SERVER", "unix:/tmp/pulseaudio.socket")
    DEFAULT_VOLUME: int = int(os.getenv("DEFAULT_VOLUME", "30"))

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
