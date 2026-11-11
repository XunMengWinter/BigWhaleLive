"""Protocol v1: strict client input, safe display text and model output."""
from __future__ import annotations

import json
import unicodedata
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def clean_text(value: str) -> str:
    return "".join(c for c in value if not unicodedata.category(c).startswith("C")).strip()


def normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Danmaku(StrictModel):
    user: str = Field(min_length=1, max_length=32)
    text: str = Field(min_length=1, max_length=200)
    client_message_id: str | None = None

    @field_validator("user", "text", mode="before")
    @classmethod
    def clean(cls, value):
        return clean_text(value) if isinstance(value, str) else value

    @field_validator("client_message_id")
    @classmethod
    def uuid_string(cls, value):
        return str(UUID(value)) if value is not None else None


class Control(StrictModel):
    action: Literal["start", "resume", "pause", "skip"]


class ClientMessage(StrictModel):
    v: int
    type: str
    data: dict


class Hello(StrictModel):
    role: Literal["stage", "control"]


class RendererReady(StrictModel):
    ready: bool
    claim_playback: bool
    audio_status: Literal["off", "ready", "blocked", "error"]
    character_mode: Literal["demo", "live2d"]


class Playback(StrictModel):
    instance_id: str
    epoch: int = Field(ge=0)
    utterance_id: str


class PlaybackError(Playback):
    code: Literal["autoplay_blocked", "audio_error"]


class Pong(StrictModel):
    token: str


class Speech(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    text: str = Field(min_length=1, max_length=120)
    emotion: Literal["neutral", "happy", "shy", "sad"] = "neutral"
    action: Literal["none", "nod", "shake_head"] = "none"

    @field_validator("text", mode="before")
    @classmethod
    def clean(cls, value):
        return clean_text(value) if isinstance(value, str) else value

    @field_validator("emotion", mode="before")
    @classmethod
    def safe_emotion(cls, value):
        return value if value in ("neutral", "happy", "shy", "sad") else "neutral"

    @field_validator("action", mode="before")
    @classmethod
    def safe_action(cls, value):
        return value if value in ("none", "nod", "shake_head") else "none"


def parse_speech(value) -> Speech:
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("```") and value.endswith("```"):
            lines = value.splitlines()
            if lines[0] in ("```", "```json"):
                value = "\n".join(lines[1:-1])
        value = json.loads(value)
    return Speech.model_validate(value)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(code)
        self.status, self.code, self.message = status, code, message


class ProviderError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
