"""Application configuration via pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_host: str = "127.0.0.1"
    app_port: int = 8765
    debug: bool = True

    database_url: str = "sqlite+aiosqlite:///./data/inventory.db"

    rfid_serial_port: str = "COM3"
    rfid_baud_rate: int = 115200
    rfid_device_address: int = 0x0000
    rfid_auto_start_inventory: bool = True
    rfid_enabled: bool = True
    rfid_read_interval_ms: int = 20

    rfid_presence_enabled: bool = True
    rfid_presence_appear_count: int = 2
    rfid_presence_disappear_count: int = 6
    rfid_presence_tick_ms: int = 200
    rfid_presence_miss_grace_ms: int = 1200
    rfid_presence_bootstrap_ms: int = 5000


@lru_cache
def get_settings() -> Settings:
    return Settings()
