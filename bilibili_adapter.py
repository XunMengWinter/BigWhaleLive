"""Bilibili official Open Live API and bounded binary-message connection.

Credentials and auth bodies stay on the backend. No webpage token/cookie API is
used. Public protocol sources and setup steps: docs/bilibili-setup.md.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import hmac
import json
import logging
import struct
import time
from urllib.parse import urlsplit
from uuid import uuid4
import zlib

import httpx
from pydantic import ValidationError

from config import Limits, secret_value
from contracts import ApiError, Danmaku

API_BASE = "https://live-open.biliapi.com"
HEADER = struct.Struct(">IHHII")


class BiliError(Exception):
    def __init__(self, reason, *, transient=False, expired=False, code=None):
        super().__init__(reason)
        self.reason, self.transient, self.expired, self.code = reason, transient, expired, code


def sign_headers(body: bytes, key: str, secret: str, *, timestamp=None, nonce=None):
    headers = {
        "x-bili-accesskeyid": key,
        "x-bili-content-md5": hashlib.md5(body).hexdigest(),
        "x-bili-signature-method": "HMAC-SHA256",
        "x-bili-signature-nonce": nonce or str(uuid4()),
        "x-bili-signature-version": "1.0",
        "x-bili-timestamp": str(int(time.time()) if timestamp is None else timestamp),
    }
    canonical = "\n".join(f"{key}:{headers[key]}" for key in sorted(headers))
    headers["Authorization"] = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    headers.update({"Accept": "application/json", "Content-Type": "application/json"})
    return headers


class OpenLiveAPI:
    def __init__(self, settings, limits, *, client=None):
        self.settings, self.limits = settings, limits
        self.client = client or httpx.AsyncClient(timeout=limits.bili_http_timeout, follow_redirects=False)
        self.owns_client = client is None

    async def call(self, operation, payload):
        if operation not in {"start", "heartbeat", "end"}:
            raise ValueError("Unknown Open Live operation")
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        headers = sign_headers(body, secret_value(self.settings.bili_access_key),
                               secret_value(self.settings.bili_access_secret))
        try:
            async with asyncio.timeout(self.limits.bili_http_timeout):
                async with self.client.stream("POST", f"{API_BASE}/v2/app/{operation}",
                                              content=body, headers=headers) as response:
                    if response.status_code != 200:
                        raise BiliError("http_error", transient=response.status_code >= 500)
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self.limits.bili_response_bytes:
                            raise BiliError("invalid_response")
                        chunks.append(chunk)
            value = json.loads(b"".join(chunks))
            if not isinstance(value, dict) or type(value.get("code")) is not int:
                raise BiliError("invalid_response")
            code = value["code"]
            if code != 0:
                raise BiliError("api_rejected", code=code, expired=code == 7003,
                                transient=code in {5000, 5001, 5002, 7003})
            if not isinstance(value.get("data"), dict):
                raise BiliError("invalid_response")
            return value["data"]
        except BiliError:
            raise
        except (TimeoutError, httpx.TimeoutException, httpx.TransportError):
            raise BiliError("api_unavailable", transient=True) from None
        except (ValueError, TypeError, RecursionError):
            raise BiliError("invalid_response") from None

    async def aclose(self):
        if self.owns_client:
            await self.client.aclose()


def pack_packet(operation: int, body: bytes = b"", *, version=0, sequence=0) -> bytes:
    return HEADER.pack(HEADER.size + len(body), HEADER.size, version, operation, sequence) + body


def decode_packets(data: bytes, limits: Limits, *, allow_brotli=False):
    """Decode complete WS messages, including concatenated and zlib-nested frames."""
    if not isinstance(data, bytes) or len(data) > limits.bili_frame_bytes:
        raise BiliError("invalid_packet", transient=True)
    result, count, remaining = [], 0, limits.bili_decoded_bytes

    def walk(buffer, depth):
        nonlocal count, remaining
        if depth > 4:
            raise ValueError
        offset = 0
        while offset < len(buffer):
            if len(buffer) - offset < HEADER.size:
                raise ValueError
            length, header_length, version, operation, _ = HEADER.unpack_from(buffer, offset)
            if header_length != HEADER.size or length < HEADER.size or offset + length > len(buffer):
                raise ValueError
            count += 1
            if count > limits.bili_packet_count:
                raise ValueError
            body = buffer[offset + header_length:offset + length]
            offset += length
            if version == 2:
                decoder = zlib.decompressobj()
                expanded = decoder.decompress(body, remaining + 1)
                if len(expanded) > remaining or decoder.unconsumed_tail or decoder.unused_data or not decoder.eof:
                    raise ValueError
                remaining -= len(expanded)
                walk(expanded, depth + 1)
            elif version == 3 and allow_brotli:
                import brotli
                decoder = brotli.Decompressor()
                output, position, available = [], 0, remaining
                try:
                    while not decoder.is_finished():
                        chunk = body[position:position + 4096] if decoder.can_accept_more_data() else b""
                        position += len(chunk)
                        expanded = decoder.process(chunk, output_buffer_limit=min(65536, available + 1))
                        if len(expanded) > available:
                            raise ValueError
                        available -= len(expanded)
                        output.append(expanded)
                        if not chunk and not expanded and not decoder.is_finished():
                            raise ValueError
                    if position != len(body):
                        raise ValueError
                except brotli.error:
                    raise ValueError from None
                remaining = available
                walk(b"".join(output), depth + 1)
            elif version in {0, 1}:
                result.append((operation, body))
            else:
                raise ValueError
    try:
        walk(data, 0)
    except (ValueError, struct.error, zlib.error):
        raise BiliError("invalid_packet", transient=True) from None
    return result


@dataclass(frozen=True)
class PlatformDanmaku:
    event_id: str
    user_id: str
    user: str
    text: str
    timestamp: int


def map_danmaku(data, room_id):
    if not isinstance(data, dict) or type(data.get("room_id")) is not int or data["room_id"] != room_id:
        raise ValueError("Invalid room")
    actor, timestamp = data.get("open_id"), data.get("timestamp")
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 256:
        raise ValueError("Missing platform identity")
    if type(timestamp) is not int or timestamp < 0:
        raise ValueError("Invalid timestamp")
    message = Danmaku(user=data.get("uname"), text=data.get("msg"))
    message_id = data.get("msg_id")
    if message_id is not None and (not isinstance(message_id, str) or len(message_id) > 256):
        raise ValueError("Invalid message identity")
    identity = [room_id, message_id] if message_id else [room_id, actor, timestamp, message.text]
    digest = hashlib.sha256(json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    actor_digest = hashlib.sha256(actor.encode()).hexdigest()
    return PlatformDanmaku("bilibili:" + digest, "bilibili:" + actor_digest,
                          message.user, message.text, timestamp)


def validate_link(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise BiliError("invalid_response")
    try:
        url = urlsplit(value)
        valid_host = url.hostname and (url.hostname.endswith(".bilibili.com") or url.hostname.endswith(".biliapi.com"))
        if url.scheme != "wss" or not valid_host or url.port not in {None, 443} or url.username or url.password or url.fragment:
            raise ValueError
    except ValueError:
        raise BiliError("invalid_response") from None
    return value


class BilibiliOpenLive:
    def __init__(self, settings, limits, on_danmaku, on_status, *, api=None, connector=None,
                 clock=time.monotonic, wall_clock=time.time):
        if connector is None:
            from websockets.asyncio.client import connect
            connector = connect
        self.settings, self.limits = settings, limits
        self.on_danmaku, self.on_status = on_danmaku, on_status
        self.api, self.connector = api or OpenLiveAPI(settings, limits), connector
        self.clock, self.wall_clock = clock, wall_clock
        self.status, self.room_id, self.reason, self.error_code = "connecting", None, None, None
        self.game_id, self.auth_body, self.links = None, None, ()
        self.task, self.app_heartbeat, self.ws, self.ending = None, None, None, None
        self.closed = False
        self.restart_requested = False
        self.last_ws_ack = 0
        self.paused_events = OrderedDict()
        self.counters = dict.fromkeys(("received", "accepted", "duplicate", "dropped", "invalid", "expired", "reconnects", "app_heartbeats", "socket_heartbeats", "socket_replies", "end_failures"), 0)
        self.logger = logging.getLogger("bigwhale.bilibili.socket")
        self.logger.setLevel(logging.WARNING)

    def diagnostics(self):
        return {**self.counters, "reason": self.reason, "error_code": self.error_code}

    def start(self):
        if not self.closed and (self.task is None or self.task.done()):
            self.restart_requested = False
            self.task = asyncio.create_task(self._run())
            self.task.add_done_callback(self._finished)
        elif not self.closed and self.status == "error":
            self.restart_requested = True

    def _finished(self, task):
        if task is self.task and self.restart_requested and not self.closed:
            self.restart_requested = False
            self.start()

    async def _status(self, status, error=None):
        self.status = status
        self.reason, self.error_code = (error.reason, error.code) if error else (None, None)
        await self.on_status()

    async def _open_session(self):
        # Never automatically repeat an ambiguous start: the server may have
        # created a session even if its response was lost.
        try:
            data = await self.api.call("start", {"code": secret_value(self.settings.bili_auth_code),
                                                 "app_id": int(self.settings.bili_app_id)})
        except BiliError as error:
            raise BiliError(error.reason, code=error.code) from None
        try:
            game_id = data["game_info"]["game_id"]
            if not isinstance(game_id, str) or not 1 <= len(game_id) <= 256:
                raise ValueError
            # Keep the cleanup handle before validating the remaining response.
            self.game_id = game_id
            room_id = data["anchor_info"]["room_id"]
            if type(room_id) is not int or not 0 < room_id < 2**63:
                raise ValueError
            self.room_id = room_id
            info = data["websocket_info"]
            auth = info["auth_body"]
            if not isinstance(auth, str) or not 1 <= len(auth.encode()) <= 8192 or not isinstance(json.loads(auth), dict):
                raise ValueError
            links = info["wss_link"]
            if not isinstance(links, list) or not 1 <= len(links) <= 8:
                raise ValueError
            self.links, self.auth_body = tuple(validate_link(link) for link in links), auth.encode()
        except (ValueError, TypeError, KeyError, RecursionError):
            raise BiliError("invalid_response") from None

    async def _stop_heartbeat(self):
        task, self.app_heartbeat = self.app_heartbeat, None
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _end_session(self):
        await self._stop_heartbeat()
        game_id, self.game_id = self.game_id, None
        self.auth_body, self.links = None, ()
        if game_id:
            self.ending = asyncio.create_task(self._call_end(game_id))
        if self.ending:
            # Shutdown can cancel _run while it is already ending a failed
            # session. Keep the single bounded end request alive, then join it
            # from aclose before closing the HTTP client.
            await asyncio.shield(self.ending)

    async def _call_end(self, game_id):
        try:
            async with asyncio.timeout(self.limits.bili_end_timeout):
                await self.api.call("end", {"app_id": int(self.settings.bili_app_id), "game_id": game_id})
        except Exception:
            self.counters["end_failures"] += 1

    async def _with_heartbeat(self, awaitable):
        task = asyncio.create_task(awaitable)
        try:
            done, _ = await asyncio.wait({task, self.app_heartbeat}, return_when=asyncio.FIRST_COMPLETED)
            if self.app_heartbeat in done:
                self.app_heartbeat.result()  # propagates only safe BiliError
                raise BiliError("api_unavailable", transient=True)
            return task.result()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _run(self):
        error = None
        try:
            for attempt in range(len(self.limits.bili_retry_delays) + 1):
                await self._status("connecting", error)
                try:
                    if self.game_id is None:
                        await self._open_session()
                    if self.app_heartbeat is None or self.app_heartbeat.done():
                        await self._stop_heartbeat()
                        self.app_heartbeat = asyncio.create_task(self._application_heartbeat())
                    await self._with_heartbeat(self._connection(attempt))
                    raise BiliError("socket_closed", transient=True)
                except BiliError as exc:
                    error = exc
                    if exc.expired:
                        self.game_id = None
                        await self._stop_heartbeat()
                    if not exc.transient or attempt == len(self.limits.bili_retry_delays):
                        break
                    self.counters["reconnects"] += 1
                    # Keep the application heartbeat alive during socket backoff.
                    if self.app_heartbeat and not self.app_heartbeat.done():
                        try:
                            await self._with_heartbeat(asyncio.sleep(self.limits.bili_retry_delays[attempt]))
                        except BiliError as heartbeat_error:
                            error = heartbeat_error
                            if heartbeat_error.expired:
                                self.game_id = None
                            await self._stop_heartbeat()
                            if not heartbeat_error.transient:
                                break
                    else:
                        await asyncio.sleep(self.limits.bili_retry_delays[attempt])
            await self._status("error", error or BiliError("socket_closed"))
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._status("error", BiliError("connection_failed"))
        finally:
            await self._end_session()

    async def _application_heartbeat(self):
        while True:
            await asyncio.sleep(self.limits.bili_heartbeat_interval)
            await self.api.call("heartbeat", {"game_id": self.game_id})
            self.counters["app_heartbeats"] += 1
            await self.on_status()

    def _packet(self, operation, body=b""):
        return pack_packet(operation, body)

    def _decode(self, data):
        return decode_packets(data, self.limits)

    def _connection_options(self):
        return {}

    async def _connection(self, attempt):
        try:
            async with self.connector(self.links[attempt % len(self.links)], open_timeout=self.limits.bili_http_timeout,
                                      close_timeout=1, ping_interval=None, compression=None, proxy=None,
                                      max_size=self.limits.bili_frame_bytes, max_queue=16, logger=self.logger,
                                      **self._connection_options()) as ws:
                self.ws = ws
                await ws.send(self._packet(7, self.auth_body))
                pending = []
                async with asyncio.timeout(self.limits.bili_auth_timeout):
                    authorized = False
                    while not authorized:
                        for operation, body in self._decode(await ws.recv()):
                            if operation == 8:
                                try:
                                    result = json.loads(body)
                                    if not isinstance(result, dict) or type(result.get("code")) is not int:
                                        raise ValueError
                                except (ValueError, TypeError, RecursionError):
                                    raise BiliError("auth_failed") from None
                                if result["code"] != 0:
                                    raise BiliError("auth_failed", code=result["code"])
                                authorized = True
                            elif authorized:
                                pending.append((operation, body))
                self.last_ws_ack = self.clock()
                await self._status("connected")
                await self._dispatch(pending)
                receive = asyncio.create_task(self._receive(ws))
                heartbeat = asyncio.create_task(self._socket_heartbeat(ws))
                try:
                    done, _ = await asyncio.wait({receive, heartbeat}, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                finally:
                    receive.cancel(); heartbeat.cancel()
                    await asyncio.gather(receive, heartbeat, return_exceptions=True)
        except BiliError:
            raise
        except Exception as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            if status in {401, 403}:
                raise BiliError("auth_failed", code=status) from None
            raise BiliError("socket_unavailable", transient=True) from None
        finally:
            self.ws = None

    async def _socket_heartbeat(self, ws):
        while True:
            if self.clock() - self.last_ws_ack >= self.limits.bili_heartbeat_timeout:
                raise BiliError("socket_heartbeat_timeout", transient=True)
            await ws.send(self._packet(2))
            self.counters["socket_heartbeats"] += 1
            await asyncio.sleep(self.limits.bili_heartbeat_interval)

    async def _receive(self, ws):
        while True:
            await self._dispatch(self._decode(await ws.recv()))

    async def _dispatch(self, packets):
        before = tuple(self.counters.values())
        for operation, body in packets:
            if operation == 3:
                self.last_ws_ack = self.clock()
                self.counters['socket_replies'] += 1
                continue
            if operation != 5:
                continue
            try:
                message = json.loads(body)
                if not isinstance(message, dict):
                    raise ValueError
                command, data = message.get("cmd"), message.get("data")
                if command == "LIVE_OPEN_PLATFORM_INTERACTION_END" and isinstance(data, dict) and data.get("game_id") == self.game_id:
                    # Respect an explicit end rather than reopening against the
                    # broadcaster's action. Manual start/resume can reconnect.
                    raise BiliError("session_ended", expired=True)
                if command != "LIVE_OPEN_PLATFORM_DM":
                    continue
                self.counters["received"] += 1
                if isinstance(data, dict) and data.get("dm_type", 0) != 0:
                    self.counters["dropped"] += 1
                    continue
                event = map_danmaku(data, self.room_id)
                age = self.wall_clock() - event.timestamp
                if age > self.settings.event_ttl_seconds or age < -60:
                    self.counters["expired"] += 1
                    continue
                now = self.clock()
                while self.paused_events:
                    first, received_at = next(iter(self.paused_events.items()))
                    if now - received_at < self.limits.dedupe_ttl:
                        break
                    self.paused_events.pop(first)
                if event.event_id in self.paused_events:
                    self.counters["dropped"] += 1
                    continue
                status, result = await self.on_danmaku(event)
                self.counters["duplicate" if result["duplicate"] else "accepted"] += 1
            except ApiError as error:
                self.counters["dropped"] += 1
                if error.code == "agent_paused":
                    # A reconnect must not replay messages observed while
                    # paused. Keep only bounded identity tombstones, no text.
                    self.paused_events[event.event_id] = self.clock()
                    while len(self.paused_events) > self.limits.dedupe_capacity:
                        self.paused_events.popitem(last=False)
            except (ValueError, TypeError, ValidationError, RecursionError):
                self.counters["invalid"] += 1
            await asyncio.sleep(0)
        if before != tuple(self.counters.values()):
            await self.on_status()

    async def aclose(self):
        self.closed = True
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        await self._end_session()
        await self.api.aclose()
