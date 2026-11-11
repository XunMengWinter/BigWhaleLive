"""Room-ID web reader following Beats0/bilive-danmaku (MIT).

Reference revision and attribution: docs/sources/bilive-danmaku.md.
Only reads ordinary text DANMU_MSG; never sends chat messages or gifts.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from urllib.parse import quote, urlencode, urlsplit

from bilibili_adapter import BiliError, BilibiliOpenLive, decode_packets, pack_packet

MIXIN = (46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,
         29,28,14,39,12,38,41,13,37,48,7,16,24,55,40,61,26,17,0,1,60,51,30,4,
         22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52)
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36'


def wbi_query(params, img_key, sub_key, *, timestamp=None):
    original = img_key + sub_key
    if len(original) != 64 or not re.fullmatch(r'[a-zA-Z0-9]{64}', original):
        raise BiliError('web_invalid_response')
    mixin = ''.join(original[index] for index in MIXIN)[:32]
    values = {**params, 'wts': int(time.time() + .5) if timestamp is None else timestamp}
    query = urlencode(sorted((key, re.sub(r"[!'()*]", '', str(value))) for key, value in values.items()),
                      quote_via=quote)
    return query + '&w_rid=' + hashlib.md5((query + mixin).encode()).hexdigest()


def web_room_info(html):
    marker = 'window.__NEPTUNE_IS_MY_WAIFU__='
    if marker not in html:
        raise BiliError('web_room_unavailable')
    try:
        value, _ = json.JSONDecoder().raw_decode(html.split(marker, 1)[1].lstrip())
        info = value['roomInfoRes']['data']['room_info']
        room_id, status = info['room_id'], info['live_status']
        if type(room_id) is not int or not 0 < room_id < 2**63 or type(status) is not int or status not in {0, 1, 2}:
            raise ValueError
        return room_id, status
    except (ValueError, KeyError, TypeError, RecursionError):
        raise BiliError('web_invalid_response') from None


def web_danmaku(data, room_id):
    """Convert the upstream info[] shape to the common platform input shape."""
    try:
        info = data['info']
        metadata, text, actor = info[0], info[1], info[2]
        uid, name, timestamp = actor[0], actor[1], metadata[4]
        # Picture/card messages are not text replies. No media URLs are loaded.
        if len(metadata) > 12 and metadata[12] in {1, 3}:
            return None
        if type(uid) is not int or not 0 <= uid < 2**63 or type(timestamp) not in {int, float} or timestamp <= 0 or not isinstance(name, str):
            raise ValueError
        timestamp = int(timestamp / 1000) if timestamp > 100000000000 else int(timestamp)
        nonce = metadata[5] if len(metadata) > 5 and isinstance(metadata[5], (str, int)) else ''
        # No login/cookie is used. If the platform hides identity, apply one
        # explicitly anonymous room-wide cooldown rather than inventing a UID.
        actor = f'web-uid:{uid}' if uid else f'web-anonymous-room:{room_id}'
        identity = hashlib.sha256(json.dumps([room_id, actor, metadata[4], text, nonce], ensure_ascii=False,
                                             separators=(',', ':')).encode()).hexdigest()
        return {'room_id': room_id, 'open_id': actor, 'uname': name.strip() or '匿名观众',
                'msg': text, 'timestamp': timestamp, 'msg_id': 'web:' + identity, 'dm_type': 0,
                'anonymous': uid == 0}
    except (ValueError, KeyError, TypeError, IndexError, OverflowError):
        raise ValueError('Invalid web danmaku') from None


class WebRoomAPI:
    def __init__(self, settings, limits, *, client=None):
        if client is None:
            from curl_cffi.requests import AsyncSession
            client = AsyncSession(impersonate='chrome', timeout=limits.bili_http_timeout,
                                  headers={'Referer': 'https://www.bilibili.com/'})
        self.client, self.settings, self.limits = client, settings, limits
        self.buvid, self.uid, self.authenticated, self.live_status = '', 0, False, None

    async def _get(self, url, *, page=False):
        chunks, size, oversized = [], 0, False
        maximum = self.limits.bili_web_page_bytes if page else self.limits.bili_response_bytes
        def collect(chunk):
            nonlocal size, oversized
            size += len(chunk)
            if size > maximum:
                oversized = True
                return 0
            chunks.append(chunk)
            return len(chunk)
        try:
            async with asyncio.timeout(self.limits.bili_http_timeout):
                response = await self.client.get(url, allow_redirects=False, content_callback=collect)
            if oversized:
                raise BiliError('web_invalid_response')
            if response.status_code != 200:
                raise BiliError('web_http_rejected', code=response.status_code,
                                transient=response.status_code >= 500)
            raw = b''.join(chunks)
            if page:
                return raw.decode('utf-8')
            value = json.loads(raw)
            if not isinstance(value, dict) or type(value.get('code')) is not int:
                raise BiliError('web_invalid_response')
            return value
        except BiliError:
            raise
        except (ValueError, UnicodeError, RecursionError):
            raise BiliError('web_invalid_response') from None
        except Exception:
            raise BiliError('web_invalid_response' if oversized else 'web_network_unavailable',
                            transient=not oversized) from None

    async def prepare(self, room_id):
        try:
            spi = await self._get('https://api.bilibili.com/x/frontend/finger/spi/')
            if spi.get('code') != 0:
                raise BiliError('web_api_rejected', code=spi.get('code'))
            buvid = spi['data']['b_3']
            if not isinstance(buvid, str) or not 1 <= len(buvid) <= 512 or any(c in buvid for c in '\r\n;'):
                raise ValueError
            self.buvid = buvid
            self.client.cookies.set('buvid3', buvid, domain='.bilibili.com', secure=True)
            nav = await self._get('https://api.bilibili.com/x/web-interface/nav')
            if nav.get('code') not in {0, -101}:
                raise BiliError('web_api_rejected', code=nav.get('code'))
            data = nav['data']
            if data.get('isLogin') is True:
                raise BiliError('web_guest_session_required')
            self.authenticated, self.uid = False, 0
            keys = data['wbi_img']
            img, sub = (urlsplit(keys[key]).path.rsplit('/', 1)[-1].rsplit('.', 1)[0]
                        for key in ['img_url', 'sub_url'])
            html = await self._get(f'https://live.bilibili.com/{room_id}', page=True)
            canonical, self.live_status = web_room_info(html)
            query = wbi_query({'id': canonical, 'type': 0, 'web_location': '444.8'}, img, sub)
            response = await self._get('https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo?' + query)
            if response.get('code') != 0:
                raise BiliError('web_api_rejected', code=response.get('code'))
            info = response['data']
            token, hosts = info['token'], info['host_list']
            if not isinstance(token, str) or not 1 <= len(token.encode()) <= 8192 or not isinstance(hosts, list) or not 1 <= len(hosts) <= 12:
                raise ValueError
            links = []
            for host in hosts:
                name, port = host['host'], host['wss_port']
                if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9.-]+\.chat\.bilibili\.com', name) or type(port) is not int or port not in {443, 2245}:
                    raise ValueError
                links.append(f'wss://{name}:{port}/sub')
            auth = {'uid': self.uid, 'roomid': canonical, 'protover': 3, 'platform': 'web',
                    'type': 2, 'buvid': self.buvid, 'key': token}
            return canonical, tuple(links), json.dumps(auth, ensure_ascii=False, separators=(',', ':')).encode()
        except BiliError:
            raise
        except (ValueError, TypeError, KeyError, IndexError, RecursionError, AttributeError):
            raise BiliError('web_invalid_response') from None

    def websocket_headers(self):
        cookie = f'buvid3={self.buvid}'
        return {'Cookie': cookie, 'Referer': f'https://live.bilibili.com/{self.settings.bili_room_id}'}

    async def aclose(self):
        await self.client.close()


class BilibiliWeb(BilibiliOpenLive):
    def __init__(self, settings, limits, on_danmaku, on_status, *, api=None, **kwargs):
        super().__init__(settings, limits, on_danmaku, on_status,
                         api=api or WebRoomAPI(settings, limits), **kwargs)
        self.counters['anonymous'] = 0

    def diagnostics(self):
        return {**super().diagnostics(), 'authenticated': self.api.authenticated,
                'live_status': self.api.live_status}

    def _packet(self, operation, body=b''):
        return pack_packet(operation, body, version=1, sequence=1)

    def _decode(self, data):
        return decode_packets(data, self.limits, allow_brotli=True)

    def _connection_options(self):
        return {'origin': 'https://live.bilibili.com', 'user_agent_header': USER_AGENT,
                'additional_headers': self.api.websocket_headers()}

    async def _run(self):
        error, attempt = None, 0
        try:
            while True:
                self.connected_since = None
                await self._status('connecting', error)
                try:
                    self.room_id, self.links, self.auth_body = await self.api.prepare(self.settings.bili_room_id)
                    await self._connection(self.counters['reconnects'])
                    raise BiliError('socket_closed', transient=True)
                except BiliError as exc:
                    error = exc
                    if exc.reason == 'auth_failed' and exc.code == -101:
                        error = BiliError('web_auth_rejected', code=-101)
                    if self.connected_since is not None and self.clock() - self.connected_since >= self.limits.bili_web_stable_seconds and self.clock() - self.last_ws_ack <= self.limits.bili_web_heartbeat_interval + 5:
                        attempt = 0
                    if not error.transient or attempt == len(self.limits.bili_retry_delays):
                        break
                    self.counters['reconnects'] += 1
                    await asyncio.sleep(self.limits.bili_retry_delays[attempt])
                    attempt += 1
            await self._status('error', error or BiliError('socket_closed'))
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._status('error', BiliError('web_connection_failed'))
        finally:
            await self._end_session()

    async def _status(self, status, error=None):
        if status == 'connected':
            self.connected_since = self.clock()
        await super()._status(status, error)

    async def _socket_heartbeat(self, ws):
        while True:
            if self.clock() - self.last_ws_ack >= self.limits.bili_web_heartbeat_timeout:
                raise BiliError('socket_heartbeat_timeout', transient=True)
            await ws.send(self._packet(2))
            self.counters['socket_heartbeats'] += 1
            await asyncio.sleep(self.limits.bili_web_heartbeat_interval)

    async def _dispatch(self, packets):
        for operation, body in packets:
            if operation == 5:
                try:
                    data = json.loads(body)
                    command = data.get('cmd', '')
                    if not isinstance(command, str) or command.split(':', 1)[0] != 'DANMU_MSG':
                        continue
                    message = web_danmaku(data, self.room_id)
                    if message is None:
                        self.counters['received'] += 1
                        self.counters['dropped'] += 1
                        await self.on_status()
                        continue
                    if message['anonymous']:
                        self.counters['anonymous'] += 1
                    body = json.dumps({'cmd': 'LIVE_OPEN_PLATFORM_DM', 'data': message}, ensure_ascii=False).encode()
                except (ValueError, TypeError, AttributeError, RecursionError):
                    self.counters['invalid'] += 1
                    await self.on_status()
                    continue
            await super()._dispatch([(operation, body)])

    async def _end_session(self):
        # Web reading has no Open Live application/game session or end RPC.
        self.auth_body, self.links = None, ()
