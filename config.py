"""Validated configuration and deterministic runtime limits."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator, model_validator

ROOT = Path(__file__).resolve().parent


class ConfigurationError(ValueError):
    """A safe startup error: never includes configuration values."""


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, validate_default=True)

    llm_mode: Literal["demo", "openai"] = "demo"
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = ""
    llm_model: str = ""
    ai_name: str = Field(default="大肥鱼", min_length=1, max_length=32)
    tts_mode: Literal["off", "edge", "qwen_local"] = "off"
    tts_voice: str = Field(default="zh-CN-XiaoyiNeural", min_length=1, max_length=128)
    tts_rate: str = Field(default="+8%", pattern=r"^[+-]\d{1,2}%$")
    tts_pitch: str = Field(default="+35Hz", pattern=r"^[+-]\d{1,3}Hz$")
    tts_local_python: str = ".cache/voice-env/bin/python"
    tts_local_model: str = ".cache/models/xiaojing-base"
    tts_local_timeout_seconds: int = Field(default=90, ge=5, le=120)
    bili_mode: Literal["off", "open_live", "web"] = "off"
    bili_room_id: int = Field(default=9748572, ge=1, lt=2**63)
    bili_app_id: str = Field(default="", max_length=19)
    bili_access_key: SecretStr = SecretStr("")
    bili_access_secret: SecretStr = SecretStr("")
    bili_auth_code: SecretStr = SecretStr("")
    live2d_model_url: str = ""
    autonomous_interval_seconds: int = Field(default=15, ge=5, le=120)
    queue_capacity: int = Field(default=100, ge=1, le=1000)
    event_ttl_seconds: int = Field(default=60, ge=5, le=300)

    @field_validator("ai_name", "llm_model", "llm_base_url", "tts_voice", mode="before")
    @classmethod
    def strip_strings(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("tts_rate", "tts_pitch")
    @classmethod
    def bound_prosody(cls, value, info):
        number = int(value[:-1] if info.field_name == "tts_rate" else value[:-2])
        bound = 50 if info.field_name == "tts_rate" else 100
        if not -bound <= number <= bound:
            raise ValueError("语速或音高超出允许范围")
        return value


    @field_validator("llm_base_url")
    @classmethod
    def validate_base_url(cls, value):
        if not value:
            return value
        url = urlsplit(value)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if (url.scheme != "https" and not (url.scheme == "http" and local)) or not url.hostname:
            raise ValueError("须使用 HTTPS 或本机 HTTP 地址")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("地址不能包含用户信息、查询串或片段")
        return value.rstrip("/")

    @field_validator("live2d_model_url")
    @classmethod
    def validate_model_path(cls, value):
        decoded = unquote(value)
        if value and (not decoded.startswith("/models/") or ".." in decoded or
                      any(c in decoded for c in "? #\\") or urlsplit(decoded).netloc):
            raise ValueError("须为 /models/ 下无路径穿越的同源资源路径")
        return value

    @model_validator(mode="after")
    def validate_mode_requirements(self):
        if self.llm_mode == "openai":
            missing = [key.upper() for key in ("llm_api_key", "llm_base_url", "llm_model")
                       if not secret_value(getattr(self, key))]
            if missing:
                raise ValueError("缺少配置键: " + ", ".join(missing))
        if self.bili_mode == "open_live":
            missing = [key.upper() for key in ("bili_app_id", "bili_access_key", "bili_access_secret", "bili_auth_code")
                       if not secret_value(getattr(self, key))]
            if missing:
                raise ValueError("缺少配置键: " + ", ".join(missing))
            if not self.bili_app_id.isdecimal() or not 0 < int(self.bili_app_id) < 2**63:
                raise ValueError("BILI_APP_ID 须为 int64 范围内的十进制正整数字符串")
        return self


def secret_value(value):
    return value.get_secret_value() if isinstance(value, SecretStr) else value


def load_settings(env_file: Path | None = ROOT / ".env", environ=None) -> Settings:
    environment = os.environ if environ is None else environ
    known = {name.upper(): name for name in Settings.model_fields}
    values = dict(dotenv_values(env_file, interpolate=False)) if env_file and env_file.exists() else {}
    unknown = set(values) - set(known)
    prefixes = ("AI_", "LLM_", "TTS_", "BILI_", "LIVE2D_", "AUTONOMOUS_", "QUEUE_", "EVENT_")
    unknown.update(key for key in environment if key.startswith(prefixes) and key not in known)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigurationError("未知配置键: " + names)
    values.update({key: environment[key] for key in known if key in environment})
    try:
        return Settings.model_validate({known[key]: value for key, value in values.items()})
    except ValidationError as exc:
        fields = set()
        for error in exc.errors(include_input=False):
            if error["loc"]:
                fields.add(".".join(str(part).upper() for part in error["loc"]))
            else:
                # Only allow known field names out of our cross-field validator.
                fields.update(key for key in known if key in error["msg"])
        fields = sorted(fields or {"模式依赖"})
        # Field names are useful; potentially sensitive validation input is not.
        raise ConfigurationError("配置校验失败: " + ", ".join(fields) + "；请核对模式、必填项与取值范围") from None


def require_supported_modes(settings: Settings):
    """All declared modes are implemented; required credentials validate above."""


@dataclass(frozen=True)
class Limits:
    user_cooldown: float = 5
    dedupe_ttl: float = 600
    dedupe_capacity: int = 1000
    llm_response_bytes: int = 65536
    llm_timeout: float = 20
    tts_timeout: float = 20
    provider_backoff: float = 5
    handshake_timeout: float = 5
    playback_start_timeout: float = 10
    playback_end_timeout: float = 45
    ping_interval: float = 5
    pong_timeout: float = 10
    send_timeout: float = 2
    outbound_capacity: int = 100
    frame_bytes: int = 16384
    memory_capacity: int = 20
    cleanup_interval: float = 60
    audio_age: float = 3600
    audio_count: int = 200
    audio_bytes: int = 5 * 1024 * 1024
    bili_http_timeout: float = 10
    bili_auth_timeout: float = 10
    bili_heartbeat_interval: float = 20
    bili_heartbeat_timeout: float = 40
    bili_end_timeout: float = 5
    bili_retry_delays: tuple[float, ...] = (2, 4, 8)
    bili_response_bytes: int = 65536
    bili_frame_bytes: int = 1024 * 1024
    bili_decoded_bytes: int = 4 * 1024 * 1024
    bili_packet_count: int = 512
    bili_web_page_bytes: int = 2 * 1024 * 1024
    bili_web_heartbeat_interval: float = 30
    bili_web_heartbeat_timeout: float = 60
    bili_web_stable_seconds: float = 30
