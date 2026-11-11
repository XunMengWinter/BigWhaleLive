"""Edge TTS streaming and bounded, atomic generated-audio storage."""
from __future__ import annotations

import asyncio
import os
from contextlib import aclosing
import time
from pathlib import Path
from uuid import UUID

from config import Limits
from contracts import ProviderError
from providers import CallStats


class OffTTS:
    async def stream(self, text):
        raise ProviderError("tts_unavailable")
        yield b""  # async-generator contract; never called in off mode


class EdgeTTS:
    def __init__(self, voice: str, limits: Limits, *, rate="+0%", pitch="+0Hz", communicate_factory=None):
        if communicate_factory is None:
            from edge_tts import Communicate
            communicate_factory = Communicate
        self.voice, self.limits, self.factory = voice, limits, communicate_factory
        self.rate, self.pitch = rate, pitch
        self.stats = CallStats()

    async def stream(self, text):
        self.stats.attempts += 1
        began = time.monotonic()
        outcome = 'cancelled'
        try:
            async with aclosing(self._stream(text)) as chunks:
                async for chunk in chunks:
                    yield chunk
            outcome = 'successes'
        except Exception:
            outcome = 'failures'
            raise
        finally:
            self.stats.finish(outcome, time.monotonic() - began)

    async def _stream(self, text):
        try:
            communicate = self.factory(text, self.voice, rate=self.rate, pitch=self.pitch, connect_timeout=min(10, self.limits.tts_timeout),
                                       receive_timeout=self.limits.tts_timeout)
            async with aclosing(communicate.stream()) as chunks:
                async for chunk in chunks:
                    if chunk.get('type') == 'audio':
                        yield chunk['data']
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise ProviderError('tts_timeout') from None
        except Exception:
            raise ProviderError('tts_unavailable') from None


class AudioStore:
    def __init__(self, directory: Path, limits: Limits, wall_clock=time.time):
        self.directory, self.limits, self.wall_clock = directory, limits, wall_clock
        directory.mkdir(parents=True, exist_ok=True)

    def path(self, utterance_id: str) -> Path:
        return self.directory / f"{UUID(utterance_id)}.mp3"

    async def write(self, utterance_id, chunks):
        target = self.path(utterance_id)
        temporary = target.with_suffix(".mp3.tmp")
        size = 0
        try:
            async with aclosing(chunks):
                with temporary.open("wb") as output:
                    async for chunk in chunks:
                        size += len(chunk)
                        if size > self.limits.audio_bytes:
                            raise ProviderError("tts_unavailable")
                        output.write(chunk)
            if not size:
                raise ProviderError("tts_unavailable")
            os.replace(temporary, target)
            return f"/audio/{utterance_id}.mp3"
        finally:
            temporary.unlink(missing_ok=True)

    def cleanup(self, active_id=None, startup=False):
        now = self.wall_clock()
        valid = []
        for path in self.directory.iterdir():
            if path.is_symlink() or not path.is_file():
                continue
            if startup and path.name.endswith(".mp3.tmp"):
                try:
                    UUID(path.name.removesuffix(".mp3.tmp"))
                except ValueError:
                    continue
                path.unlink(missing_ok=True)
                continue
            try:
                if path.suffix != ".mp3":
                    continue
                identity = str(UUID(path.stem))
            except ValueError:
                continue
            if identity == active_id:
                continue
            age = now - path.stat().st_mtime
            if age > self.limits.audio_age:
                path.unlink(missing_ok=True)
            else:
                valid.append(path)
        valid.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for path in valid[self.limits.audio_count:]:
            path.unlink(missing_ok=True)
