"""Single-process dialogue scheduler. All state mutations occur under one lock.

Providers run outside the lock; instance/epoch/utterance guards make cancellation
safe even when a provider returns after cancellation. tick() is clock-injectable.
"""
from __future__ import annotations

import asyncio
import copy
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from config import Limits, Settings
from contracts import (ApiError, ClientMessage, Hello, Playback, PlaybackError,
                       Pong, ProviderError, RendererReady, normalized, parse_speech)
from providers.llm import ChatCompletionsLLM, DemoLLM
from providers.tts import AudioStore, EdgeTTS, OffTTS
from providers.local_tts import LocalQwenTTS
from bilibili_adapter import BilibiliOpenLive
from bilibili_web import BilibiliWeb
from companion import CompanionScene

ERROR_TEXT = {
    "llm_timeout": "台词生成超时，本轮已结束",
    "llm_unavailable": "台词生成失败，请稍后再试",
    "llm_invalid_output": "台词格式不符合要求，本轮已结束",
    "content_blocked": "内容被过滤规则阻止",
    "tts_timeout": "语音合成超时，本条改用字幕",
    "tts_unavailable": "语音不可用，本条改用字幕",
    "playback_timeout": "舞台播放确认超时，请重新申请播放权",
    "autoplay_blocked": "声音被浏览器阻止，请在舞台启用声音",
    "audio_error": "舞台播放失败，请重新就绪",
    "renderer_disconnected": "播放舞台已断开，本条已取消",
    "bili_unavailable": "B站弹幕连接失败，请检查平台状态与授权配置",
}


@dataclass
class Client:
    identity: str
    queue: asyncio.Queue
    connected_at: float
    last_pong: float
    last_ping: float
    role: str | None = None
    ready: bool = False
    audio_status: str = "off"
    character_mode: str = "demo"
    pings: dict = field(default_factory=dict)
    close_code: int | None = None
    closing: asyncio.Event = field(default_factory=asyncio.Event)


class Agent:
    def __init__(self, settings: Settings, root: Path, *, limits=None, clock=None,
                 llm=None, tts=None, audio=None, blocked_terms=None, platform_factory=None):
        self.settings, self.root = settings, root
        self.limits = limits or Limits()
        self.clock = clock or time.monotonic
        self.llm = llm if llm is not None else (
            ChatCompletionsLLM(settings, root, self.limits) if settings.llm_mode == "openai" else DemoLLM(settings.ai_name, root))
        self.tts = tts if tts is not None else (
            LocalQwenTTS(settings, root, self.limits) if settings.tts_mode == "qwen_local" else
            EdgeTTS(settings.tts_voice, self.limits, rate=settings.tts_rate, pitch=settings.tts_pitch) if settings.tts_mode == "edge" else OffTTS())
        self.audio = audio if audio is not None else AudioStore(root / "static/audio", self.limits)
        if blocked_terms is None:
            path = root / "config/blocked-terms.txt"
            blocked_terms = path.read_text().splitlines() if path.exists() else []
        self.blocked = tuple(normalized(term.strip()) for term in blocked_terms
                             if term.strip() and not term.lstrip().startswith("#"))
        self.instance_id = str(uuid4())
        self.epoch, self.seq = 0, 0
        self.mode, self.phase = "paused", "idle"
        self.queue = deque()
        self.dedupe = OrderedDict()
        self.cooldowns = {}
        self.memory = deque(maxlen=self.limits.memory_capacity)
        self.companion = CompanionScene()
        self.recent_timings = deque(maxlen=20)
        self.clients: dict[str, Client] = {}
        self.owner: str | None = None
        self.current = None
        self.last_error = None
        self.tts_status = "disabled" if settings.tts_mode == "off" else "idle"
        self.counters = dict.fromkeys(("accepted", "duplicate", "expired", "rejected", "failed", "completed"), 0)
        self.next_autonomous = self.clock() + settings.autonomous_interval_seconds
        self.backoff_until = 0
        self.last_cleanup = self.clock()
        self.lock = asyncio.Lock()
        self.runner = None
        self.work = set()
        self.stopped = False
        self.platform = ((platform_factory or (BilibiliWeb if settings.bili_mode == "web" else BilibiliOpenLive))(
            settings, self.limits, self.accept_platform, self.platform_changed)
            if settings.bili_mode != "off" else None)
        self.last_platform_status = None

    def content_blocked(self, text):
        value = normalized(text)
        return any(term in value for term in self.blocked)

    def state(self):
        blocked_audio = any(client.role == "stage" and client.audio_status == "blocked"
                            for client in self.clients.values())
        renderer = "ready" if self.owner else ("blocked" if blocked_audio else "waiting")
        reason = None
        if self.mode == "running":
            if not self.owner:
                reason = "audio_blocked" if blocked_audio else "no_renderer"
            elif self.clock() < self.backoff_until:
                reason = "provider_backoff"
        current = None
        if self.current:
            current = {key: self.current[key] for key in ("utterance_id", "kind", "text", "emotion", "action")}
        return {"instance_id": self.instance_id, "ai_name": self.settings.ai_name, "epoch": self.epoch, "mode": self.mode,
                "phase": self.phase, "blocked_reason": reason, "queue_size": len(self.queue),
                "playback_owner_id": self.owner, "renderer_status": renderer,
                "llm_mode": self.settings.llm_mode, "tts_mode": self.settings.tts_mode,
                "tts_status": self.tts_status, "tts_voice": "xiaojing-v1" if self.settings.tts_mode == "qwen_local" else self.settings.tts_voice if self.settings.tts_mode == "edge" else "",
                "llm_model": self.settings.llm_model if self.settings.llm_mode == "openai" else "",
                "tts_rate": self.settings.tts_rate if self.settings.tts_mode == "edge" else "",
                "tts_pitch": self.settings.tts_pitch if self.settings.tts_mode == "edge" else "",
                "bili_mode": self.settings.bili_mode,
                "bili_status": self.platform.status if self.platform else "disabled",
                "bili_room_id": self.platform.room_id if self.platform else None,
                "current": current,
                "last_error": copy.deepcopy(self.last_error), "counters": self.counters.copy(),
                "diagnostics": {"llm": self.llm.stats.snapshot() if hasattr(self.llm, "stats") else None,
                                "knowledge": self.llm.knowledge.snapshot() if hasattr(self.llm, "knowledge") else None,
                                "companion": self.companion.snapshot(),
                                "tts": self.tts.stats.snapshot() if hasattr(self.tts, "stats") else None,
                                "bilibili": self.platform.diagnostics() if self.platform else None,
                                "recent": copy.deepcopy(list(self.recent_timings))}}

    def _send(self, client, kind, data):
        if client.close_code:
            return
        self.seq += 1
        message = {"v": 1, "type": kind, "instance_id": self.instance_id,
                   "epoch": self.epoch, "seq": self.seq, "data": copy.deepcopy(data)}
        try:
            client.queue.put_nowait(message)
        except asyncio.QueueFull:
            self._mark_closed(client, 1013)

    def _broadcast(self, kind, data):
        for client in list(self.clients.values()):
            self._send(client, kind, data)

    def _publish(self):
        state = self.state()
        for client in list(self.clients.values()):
            self._send(client, "state.snapshot", {"connection_id": client.identity, "state": state})

    def _error(self, code, identity=None):
        self.counters["failed"] += 1
        message = ERROR_TEXT.get(code, "本轮处理失败")
        self.last_error = {"code": code, "message": message,
                           "at": datetime.now(timezone.utc).isoformat()}
        self._broadcast("system.error", {"code": code, "message": message, "utterance_id": identity})

    def _mark_closed(self, client, code):
        if not client.close_code:
            client.close_code = code
            client.closing.set()

    def _prune(self):
        now = self.clock()
        old_size = len(self.queue)
        self.queue = deque(event for event in self.queue
                           if now - event["received_at"] < self.settings.event_ttl_seconds)
        self.counters["expired"] += old_size - len(self.queue)
        for key, (received, _) in list(self.dedupe.items()):
            if now - received >= self.limits.dedupe_ttl:
                self.dedupe.pop(key)
        while len(self.dedupe) > self.limits.dedupe_capacity:
            self.dedupe.popitem(last=False)
        self.cooldowns = {key: accepted for key, accepted in self.cooldowns.items()
                          if now - accepted < self.limits.user_cooldown}
        return old_size != len(self.queue)

    async def connect(self):
        async with self.lock:
            now = self.clock()
            client = Client(str(uuid4()), asyncio.Queue(maxsize=self.limits.outbound_capacity), now, now, now)
            self.clients[client.identity] = client
            self._send(client, "state.snapshot", {"connection_id": client.identity, "state": self.state()})
            return client

    async def reject_input(self):
        async with self.lock:
            self.counters["rejected"] += 1
            self._publish()

    async def accept(self, message):
        identity = message.client_message_id or str(uuid4())
        return await self._accept(message, identity, "local", "local:" + normalized(message.user))

    async def accept_platform(self, event):
        # Only the backend adapter can supply platform identity/source; HTTP
        # callers continue to accept the strict local Danmaku request contract.
        from contracts import Danmaku
        message = Danmaku(user=event.user, text=event.text)
        return await self._accept(message, event.event_id, "bilibili", event.user_id)

    async def platform_changed(self):
        async with self.lock:
            if self.stopped:
                return
            status = self.platform.status
            if status == "error" and self.last_platform_status != "error":
                self._error("bili_unavailable")
            elif status == "connected" and self.last_error and self.last_error["code"] == "bili_unavailable":
                self.last_error = None
            self.last_platform_status = status
            self._publish()

    async def _accept(self, message, identity, source, user_id):
        async with self.lock:
            self._prune()
            signature = (source, user_id, message.user, message.text)
            if identity in self.dedupe:
                if self.dedupe[identity][1] != signature:
                    return self._reject(409, "id_conflict", "消息 ID 已被其他内容使用")
                self.counters["duplicate"] += 1
                self._publish()
                return 200, {"event_id": identity, "accepted": True, "duplicate": True, "queue_size": len(self.queue)}
            if self.mode != "running":
                return self._reject(409, "agent_paused", "请先开始或恢复主播")
            if self.content_blocked(message.text) or self.content_blocked(message.user):
                return self._reject(422, "content_blocked", ERROR_TEXT["content_blocked"])
            if user_id in self.cooldowns:
                return self._reject(429, "user_cooldown", "同一观众发送过快，请稍后再试")
            if len(self.queue) >= self.settings.queue_capacity:
                return self._reject(429, "queue_full", "等待队列已满，请稍后重试")
            now = self.clock()
            self.queue.append({"event_id": identity, "source": source, "user_id": user_id,
                               "user": message.user, "text": message.text, "received_at": now, "priority": 10})
            self.dedupe[identity] = (now, signature)
            self.cooldowns[user_id] = now
            self._prune()
            self.counters["accepted"] += 1
            if source == "bilibili":
                self._broadcast("danmaku.received", {"event_id": identity, "source": source,
                                                      "user": message.user, "text": message.text})
            self._publish()
            return 202, {"event_id": identity, "accepted": True, "duplicate": False, "queue_size": len(self.queue)}

    def _reject(self, status, code, message):
        self.counters["rejected"] += 1
        self._publish()
        raise ApiError(status, code, message)

    async def control(self, action):
        async with self.lock:
            if action in ("start", "resume"):
                if self.mode != "running":
                    self.mode = "running"
                    self.next_autonomous = self.clock() + self.settings.autonomous_interval_seconds
            elif action == "pause":
                if self.mode != "paused" or self.current or self.queue:
                    self.mode = "paused"
                    self.queue.clear()
                    self._cancel("paused", force=True)
            elif action == "skip":
                if not self.current:
                    raise ApiError(409, "no_active_utterance", "当前没有可以跳过的发言")
                self._cancel("skipped")
            self._publish()
            state = self.state()
        if action in {"start", "resume"} and self.platform:
            self.platform.start()
        return state

    def _cancel(self, reason, force=False):
        old = self.current
        if old or force:
            self.epoch += 1
        if old:
            old["timing"]["result"] = "cancelled"
            task = old.get("task")
            if task and task is not asyncio.current_task():
                task.cancel()
            self._broadcast("utterance.cancel", {"utterance_id": old["utterance_id"], "reason": reason})
        self.current, self.phase = None, "idle"
        self.companion.reset()
        self.next_autonomous = self.clock() + self.settings.autonomous_interval_seconds

    def _lose_owner(self, code=None):
        old_owner = self.clients.get(self.owner)
        if self.current and code:
            self._error(code, self.current["utterance_id"])
        if old_owner:
            old_owner.ready = False
        self.owner = None
        self._cancel(code or "renderer_released", force=True)

    async def disconnect(self, identity):
        async with self.lock:
            client = self.clients.pop(identity, None)
            if client is None:
                return
            self._mark_closed(client, 1000)
            if self.owner == identity:
                self._lose_owner("renderer_disconnected")
            self._publish()

    async def handle(self, client, raw):
        async with self.lock:
            if client.identity not in self.clients or client.close_code:
                return
            try:
                message = ClientMessage.model_validate(raw)
                if message.v != 1:
                    self._mark_closed(client, 1002)
                    return
                if message.type == "client.hello":
                    data = Hello.model_validate(message.data)
                    if client.role is not None:
                        if client.role != data.role:
                            self._mark_closed(client, 1008)
                        return
                    client.role = data.role
                    client.last_pong = self.clock()
                    self._publish()
                    return
                if not client.role:
                    self._protocol_error(client)
                    return
                if message.type == "client.pong":
                    token = Pong.model_validate(message.data).token
                    sent = client.pings.pop(token, None)
                    if sent is not None and self.clock() - sent <= self.limits.pong_timeout:
                        client.last_pong = self.clock()
                    return
                if message.type == "renderer.ready":
                    if client.role != "stage":
                        self._mark_closed(client, 1008)
                        return
                    data = RendererReady.model_validate(message.data)
                    valid_audio = data.audio_status == ("off" if self.settings.tts_mode == "off" else "ready")
                    client.audio_status, client.character_mode = data.audio_status, data.character_mode
                    client.ready = data.ready and valid_audio
                    if self.owner == client.identity and not client.ready:
                        self._lose_owner()
                    elif not self.owner and client.ready and data.claim_playback:
                        self.owner = client.identity
                    self._publish()
                    return
                if message.type in ("playback.started", "playback.ended", "playback.error"):
                    data = (PlaybackError if message.type == "playback.error" else Playback).model_validate(message.data)
                    if not self.current or self.owner != client.identity or data.instance_id != self.instance_id or \
                            data.epoch != self.epoch or data.utterance_id != self.current["utterance_id"]:
                        return
                    if message.type == "playback.started" and self.phase == "awaiting_playback":
                        self.companion.started(self.current['scene_plan'])
                        self.phase = "playing"
                        self.current["timing"]["started_ms"] = round((self.clock() - self.current["began_at"]) * 1000, 1)
                        self.current["timing"]["result"] = "playing"
                        self.current["deadline"] = self.clock() + self.limits.playback_end_timeout
                    elif message.type == "playback.ended" and self.phase == "playing":
                        old = self.current
                        old["timing"]["result"] = "completed_without_audio" if old.get("tts_status") == "error" else "completed"
                        self.memory.append({"event": copy.deepcopy(old["event"]), "text": old["text"], "kind": old["kind"],
                                            "emotion": old['emotion'], "action": old['action']})
                        self.companion.completed(old['scene_plan'])
                        self.counters["completed"] += 1
                        if old.get("tts_status") != "error":
                            self.last_error = None
                        self.current, self.phase = None, "idle"
                        self.next_autonomous = self.clock() + self.settings.autonomous_interval_seconds
                    elif message.type == "playback.error" and self.phase in ("awaiting_playback", "playing"):
                        client.audio_status = "blocked" if data.code == "autoplay_blocked" else "error"
                        self._lose_owner(data.code)
                    else:
                        return
                    self._publish()
                    return
                self._protocol_error(client)
            except (ValidationError, ValueError, TypeError):
                self._protocol_error(client)

    def _protocol_error(self, client):
        self._send(client, "protocol.error", {"code": "invalid_message", "message": "消息字段或顺序不符合协议"})

    def _valid(self, key):
        return bool(self.current and key == (self.epoch, self.current["utterance_id"]) and self.mode == "running" and self.owner)

    async def _produce(self, key, event, history):
        began = self.clock()
        try:
            try:
                async with asyncio.timeout(self.limits.llm_timeout):
                    value = await self.llm.generate(copy.deepcopy(event), history,
                                                    scene=self.current['scene_plan'].context())
                try:
                    speech = parse_speech(value)
                except (ValidationError, ValueError, TypeError):
                    raise ProviderError("llm_invalid_output") from None
                if self.content_blocked(speech.text):
                    raise ProviderError("content_blocked")
            except TimeoutError:
                raise ProviderError("llm_timeout") from None
            async with self.lock:
                if not self._valid(key):
                    return
                self.current["timing"]["llm_ms"] = round((self.clock() - began) * 1000, 1)
                self.current.update(speech.model_dump())
                if self.settings.tts_mode != "off":
                    self.phase = "synthesizing"
                    self.current["timing"]["result"] = "synthesizing"
                    self._publish()
            audio_url = None
            tts_status = "disabled"
            if self.settings.tts_mode != "off":
                synthesis_began = self.clock()
                try:
                    timeout = self.settings.tts_local_timeout_seconds if self.settings.tts_mode == "qwen_local" else self.limits.tts_timeout
                    async with asyncio.timeout(timeout):
                        audio_url = await self.audio.write(key[1], self.tts.stream(speech.text))
                    tts_status = "ok"
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    tts_status = "error"
                    code = exc.code if isinstance(exc, ProviderError) else ("tts_timeout" if isinstance(exc, TimeoutError) else "tts_unavailable")
                    async with self.lock:
                        if not self._valid(key):
                            return
                        self._error(code, key[1])
            async with self.lock:
                if not self._valid(key):
                    if audio_url:
                        self.audio.path(key[1]).unlink(missing_ok=True)
                    return
                if self.settings.tts_mode != "off":
                    self.current["timing"]["tts_ms"] = round((self.clock() - synthesis_began) * 1000, 1)
                self.current["timing"]["ready_ms"] = round((self.clock() - self.current["began_at"]) * 1000, 1)
                self.current["timing"]["result"] = "awaiting_playback"
                self.tts_status = tts_status
                self.current["tts_status"] = tts_status
                self.current["deadline"] = self.clock() + self.limits.playback_start_timeout
                self.phase = "awaiting_playback"
                data = {"utterance_id": key[1], "kind": self.current["kind"], **speech.model_dump(),
                        "audio_url": audio_url, "display_duration_ms": None if audio_url else min(10000, max(2000, len(speech.text) * 80)),
                        "tts_status": tts_status}
                self._send(self.clients[self.owner], "utterance.ready", data)
                self._publish()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            async with self.lock:
                if not self._valid(key):
                    return
                code = exc.code if isinstance(exc, ProviderError) else "llm_unavailable"
                self._error(code, key[1])
                self.current["timing"]["llm_ms"] = round((self.clock() - began) * 1000, 1)
                self.current["timing"]["result"] = code
                self.current, self.phase = None, "idle"
                self.backoff_until = self.clock() + self.limits.provider_backoff
                self.next_autonomous = self.clock() + self.settings.autonomous_interval_seconds
                self._publish()

    async def tick(self):
        async with self.lock:
            now = self.clock()
            changed = self._prune()
            for client in list(self.clients.values()):
                if client.role is None and now - client.connected_at >= self.limits.handshake_timeout:
                    self._mark_closed(client, 1008)
                elif client.role is not None and now - client.last_pong >= self.limits.pong_timeout:
                    self._mark_closed(client, 1001)
                if client.close_code:
                    self.clients.pop(client.identity, None)
                    if self.owner == client.identity:
                        self._lose_owner("renderer_disconnected")
                    changed = True
                    continue
                if client.role and now - client.last_ping >= self.limits.ping_interval:
                    client.pings = {token: sent for token, sent in client.pings.items() if now - sent <= self.limits.pong_timeout}
                    token = str(uuid4())
                    client.pings[token] = now
                    client.last_ping = now
                    self._send(client, "server.ping", {"token": token})
            if self.current and self.phase in ("awaiting_playback", "playing") and now >= self.current["deadline"]:
                self._lose_owner("playback_timeout")
                changed = True
            if now - self.last_cleanup >= self.limits.cleanup_interval:
                self.audio.cleanup(self.current["utterance_id"] if self.current else None)
                self.last_cleanup = now
            if self.mode == "running" and self.owner and not self.current and now >= self.backoff_until:
                event = self.queue.popleft() if self.queue else None
                if event or now >= self.next_autonomous:
                    identity = str(uuid4())
                    timing = {"utterance_id": identity, "kind": "reply" if event else "autonomous",
                              "llm_ms": None, "tts_ms": None, "ready_ms": None, "started_ms": None, "result": "generating"}
                    self.recent_timings.append(timing)
                    self.current = {"timing": timing, "began_at": event["received_at"] if event else self.clock(), "utterance_id": identity, "kind": "reply" if event else "autonomous",
                                    "text": None, "emotion": "neutral", "action": "none", "event": event,
                                    "scene_plan": self.companion.plan(event['text'] if event else None)}
                    self.phase = "generating"
                    task = asyncio.create_task(self._produce((self.epoch, identity), event, copy.deepcopy(list(self.memory))))
                    self.current["task"] = task
                    self.work.add(task)
                    task.add_done_callback(self.work.discard)
                    changed = True
            if changed:
                self._publish()

    async def start(self):
        if self.runner:
            return
        self.audio.cleanup(startup=True)
        self.runner = asyncio.create_task(self._run())
        if self.platform:
            self.platform.start()

    async def _run(self):
        while not self.stopped:
            await self.tick()
            await asyncio.sleep(0.1)

    async def stop(self):
        async with self.lock:
            self.stopped = True
            self.mode = "paused"
            self.queue.clear()
            self._cancel("shutdown", force=True)
            for client in list(self.clients.values()):
                self._mark_closed(client, 1001)
            self.clients.clear()
            self.owner = None
        tasks = [task for task in [self.runner, *self.work] if task]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=1)
        if self.platform:
            await self.platform.aclose()
        for provider in (self.llm, self.tts):
            close_provider = getattr(provider, "aclose", None)
            if close_provider:
                await close_provider()
