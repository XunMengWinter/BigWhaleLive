"""Bounded async bridge to a resident, isolated MLX voice worker."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import time
from pathlib import Path

from config import ConfigurationError
from contracts import ProviderError
from providers import CallStats


class LocalQwenTTS:
    voice = "xiaojing-v1"

    def __init__(self, settings, root, limits, *, process_factory=None):
        self.root, self.limits = Path(root), limits
        # Keep the venv's entry-point path: resolving its symlink would select
        # the base interpreter and silently lose the optional environment.
        self.python = (self.root / settings.tts_local_python).absolute()
        self.model = (self.root / settings.tts_local_model).resolve()
        self.profile = self.root / "assets/voices/xiaojing-v1"
        try:
            manifest = json.loads((self.profile / "voice.json").read_text())
            digest = hashlib.sha256((self.profile / "reference.wav").read_bytes()).hexdigest()
            if manifest["voice_id"] != self.voice or digest != manifest["reference_sha256"]:
                raise ValueError
            if not self.python.is_file() or not (self.model / "config.json").is_file():
                raise ValueError
        except (OSError, ValueError, KeyError):
            raise ConfigurationError("本地小鲸音色资源缺失或校验失败；请按运行配置安装固定音色") from None
        self.factory = process_factory or asyncio.create_subprocess_exec
        self.process = None
        self.lock = asyncio.Lock()
        self.closed = False
        self.stats = CallStats()

    async def _terminate(self):
        process, self.process = self.process, None
        if process is None:
            return
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(process.wait(), 1)
        except TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()

    async def stream(self, text):
        self.stats.attempts += 1
        began, outcome, complete = time.monotonic(), "cancelled", False
        async with self.lock:
            try:
                if self.closed:
                    raise ValueError
                if self.process is None or self.process.returncode is not None:
                    # Model weights must already exist. Runtime never downloads models.
                    environment = {key: value for key, value in os.environ.items()
                                   if not key.startswith(("LLM_", "BILI_"))}
                    environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                                       HF_HOME=str(self.root / ".cache/huggingface"), TOKENIZERS_PARALLELISM="false")
                    self.process = await self.factory(
                        str(self.python), str(Path(__file__).with_name("_qwen_worker.py")),
                        str(self.model), str(self.profile),
                        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL, env=environment, limit=65536)
                process = self.process
                process.stdin.write((json.dumps({"text": text}, ensure_ascii=False) + "\n").encode())
                await process.stdin.drain()
                size = 0
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        raise ValueError
                    message = json.loads(line)
                    if message.get("type") == "done":
                        if not size:
                            raise ValueError
                        complete, outcome = True, "successes"
                        break
                    if message.get("type") != "audio":
                        raise ValueError
                    chunk = base64.b64decode(message["data"], validate=True)
                    size += len(chunk)
                    if not chunk or size > self.limits.audio_bytes:
                        raise ValueError
                    yield chunk
            except asyncio.CancelledError:
                raise
            except Exception:
                outcome = "failures"
                raise ProviderError("tts_unavailable") from None
            finally:
                if not complete:
                    # Cancelling the worker also cancels GPU work. No late result can
                    # be consumed by a later utterance; the next call starts fresh.
                    await self._terminate()
                self.stats.finish(outcome, time.monotonic() - began)

    async def aclose(self):
        self.closed = True
        async with self.lock:
            await self._terminate()
