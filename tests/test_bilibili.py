"""Official-protocol tests. No test claims to connect to a real B站 room."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import hashlib
import json
import struct
import time
import zlib

import httpx
import pytest

from bilibili_adapter import (API_BASE, HEADER, BiliError, BilibiliOpenLive,
                              OpenLiveAPI, decode_packets, map_danmaku,
                              pack_packet, sign_headers, validate_link)
from config import Limits, Settings
from contracts import ApiError
from conftest import ack, connect, drain


def configured(**kwargs):
    return Settings(bili_mode='open_live', bili_app_id='1234567890123',
                    bili_access_key='private-key', bili_access_secret='private-secret',
                    bili_auth_code='private-code', **kwargs)


def wire_message(data=None, command='LIVE_OPEN_PLATFORM_DM'):
    return pack_packet(5, json.dumps({'cmd': command, 'data': data}, ensure_ascii=False).encode())


def danmaku(identity='one', actor='viewer-one', text='你好', **kwargs):
    return {'room_id': 42, 'uid': 0, 'open_id': actor, 'timestamp': int(time.time()),
            'uname': '同名观众', 'msg': text, 'msg_id': identity, 'dm_type': 0, **kwargs}


def compressed(data):
    body = zlib.compress(data)
    return HEADER.pack(HEADER.size + len(body), 16, 2, 5, 0) + body


async def eventually(predicate, seconds=3):
    async with asyncio.timeout(seconds):
        while not predicate():
            await asyncio.sleep(.005)


class FakeAPI:
    def __init__(self, *, heartbeat_errors=(), bad_start=None, start_error=None):
        self.calls, self.closed = [], False
        self.heartbeat_errors = list(heartbeat_errors)
        self.bad_start, self.start_error = bad_start, start_error
        self.starts = 0

    async def call(self, operation, body):
        self.calls.append((operation, body.copy()))
        if operation == 'start':
            self.starts += 1
            if self.start_error:
                raise self.start_error
            return self.bad_start or {'game_info': {'game_id': f'private-game-{self.starts}'},
                'anchor_info': {'room_id': 42}, 'websocket_info': {
                    'auth_body': json.dumps({'key': f'private-auth-{self.starts}', 'roomid': 42}),
                    'wss_link': ['wss://one.chat.bilibili.com/sub', 'wss://two.chat.bilibili.com/sub']}}
        if operation == 'heartbeat' and self.heartbeat_errors:
            error = self.heartbeat_errors.pop(0)
            if error:
                raise error
        return {}

    async def aclose(self):
        self.closed = True


class FakeWS:
    def __init__(self, *, auth_code=0, acknowledge=True):
        self.incoming, self.sent = asyncio.Queue(), []
        self.auth_code, self.acknowledge = auth_code, acknowledge
        self.closed = False

    async def send(self, data):
        self.sent.append(data)
        operation, _ = decode_packets(data, Limits())[0]
        if operation == 7:
            self.incoming.put_nowait(pack_packet(8, json.dumps({'code': self.auth_code}).encode()))
        elif operation == 2 and self.acknowledge:
            self.incoming.put_nowait(pack_packet(3, struct.pack('>I', 1)))

    async def recv(self):
        value = await self.incoming.get()
        if isinstance(value, Exception):
            raise value
        return value


class FakeConnector:
    def __init__(self, *, auth_code=0, acknowledge=True):
        self.connections, self.links = [], []
        self.auth_code, self.acknowledge = auth_code, acknowledge

    @asynccontextmanager
    async def __call__(self, url, **kwargs):
        assert url.startswith('wss://') and kwargs['proxy'] is None
        assert kwargs['max_size'] == Limits().bili_frame_bytes
        self.links.append(url)
        ws = FakeWS(auth_code=self.auth_code, acknowledge=self.acknowledge)
        self.connections.append(ws)
        try:
            yield ws
        finally:
            ws.closed = True


def make_platform_agent(make_agent, *, api=None, connector=None, limits=None, **kwargs):
    api, connector = api or FakeAPI(), connector or FakeConnector()
    limits = limits or replace(Limits(), bili_heartbeat_interval=.025, bili_heartbeat_timeout=.15,
                              bili_retry_delays=(.01, .02, .03), ping_interval=10000,
                              pong_timeout=10000, handshake_timeout=10000, outbound_capacity=1000)
    def factory(settings, limits, on_danmaku, on_status):
        return BilibiliOpenLive(settings, limits, on_danmaku, on_status, api=api, connector=connector)
    return make_agent(settings=configured(), limits=limits, platform_factory=factory, **kwargs), api, connector


def test_D01_signature_golden_openssl_and_utf8_lengths():
    body = b'{"code":"test-code","app_id":1234567890123}'
    headers = sign_headers(body, 'test-access', 'test-secret', timestamp=1700000000, nonce='fixed-nonce')
    # Golden independently generated with OpenSSL, not the production helper.
    assert headers['x-bili-content-md5'] == '279f97c4a30ed6422da0b0258d1de36c'
    assert headers['Authorization'] == 'dce131ff3705cd095eb504f3498df2138149889e9459d30c82a3cc2b855bbc10'
    assert headers['x-bili-signature-version'] == '1.0'
    chinese = '中文身份码'.encode()
    packet = pack_packet(7, chinese)
    assert HEADER.unpack(packet[:16]) == (16 + len(chinese), 16, 0, 7, 0)
    assert decode_packets(packet, Limits()) == [(7, chinese)]


async def test_D01_http_body_signed_exactly_and_secrets_never_returned():
    calls = []
    def handle(request):
        calls.append(request)
        assert str(request.url) == API_BASE + '/v2/app/start'
        assert request.method == 'POST'
        assert request.headers['x-bili-content-md5'] == hashlib.md5(request.content).hexdigest()
        assert request.headers['content-type'] == 'application/json'
        assert json.loads(request.content) == {'code': '中文身份码', 'app_id': 1234567890123}
        return httpx.Response(200, json={'code': 0, 'data': {'ok': True}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        api = OpenLiveAPI(configured(), Limits(), client=client)
        assert await api.call('start', {'code': '中文身份码', 'app_id': 1234567890123}) == {'ok': True}
    assert len(calls) == 1


@pytest.mark.parametrize('code,transient,expired', [(4002, False, False), (4008, False, False),
    (5000, True, False), (7003, True, True), (7007, False, False), (8002, False, False)])
async def test_D03_api_error_codes_are_safe_and_do_not_retry_in_http_adapter(code, transient, expired):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={'code': code, 'message': 'private-secret private-code'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        api = OpenLiveAPI(configured(), Limits(), client=client)
        with pytest.raises(BiliError) as error:
            await api.call('heartbeat', {'game_id': 'private-game'})
        assert error.value.code == code
        assert (error.value.transient, error.value.expired) == (transient, expired)
        assert 'private' not in str(error.value) and len(calls) == 1


@pytest.mark.parametrize('response', [httpx.Response(302), httpx.Response(200, text='invalid'),
    httpx.Response(200, json={'code': True, 'data': {}}), httpx.Response(200, json={'code': 0, 'data': []}),
    httpx.Response(200, content=b'x' * 500)])
async def test_D01_http_rejects_redirects_invalid_and_oversized_responses(response):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)) as client:
        with pytest.raises(BiliError):
            await OpenLiveAPI(configured(), replace(Limits(), bili_response_bytes=100), client=client).call('start', {})


def test_D01_nested_zlib_and_coalesced_frames():
    one, two = wire_message(danmaku('one')), wire_message(danmaku('two'))
    assert decode_packets(compressed(one + compressed(two)), Limits()) == decode_packets(one + two, Limits())


@pytest.mark.parametrize('payload', [b'x', HEADER.pack(10, 16, 0, 5, 0), HEADER.pack(16, 15, 0, 5, 0),
    HEADER.pack(16, 16, 3, 5, 0), pack_packet(2) + b'x', HEADER.pack(30, 16, 0, 5, 0)])
def test_D01_malformed_packet_lengths_and_versions_are_rejected(payload):
    with pytest.raises(BiliError, match='invalid_packet'):
        decode_packets(payload, Limits())


def test_D01_compression_bomb_packet_count_depth_and_size_are_bounded():
    limits = replace(Limits(), bili_decoded_bytes=100)
    with pytest.raises(BiliError):
        decode_packets(compressed(b'x' * 100000), limits)
    with pytest.raises(BiliError):
        decode_packets(pack_packet(2) * 3, replace(Limits(), bili_packet_count=2))
    with pytest.raises(BiliError):
        decode_packets(b'x' * 100, replace(Limits(), bili_frame_bytes=50))
    nested = pack_packet(2)
    for _ in range(6):
        nested = compressed(nested)
    with pytest.raises(BiliError):
        decode_packets(nested, Limits())


@pytest.mark.parametrize('link', ['ws://one.chat.bilibili.com/sub', 'wss://example.com/sub',
    'wss://one.chat.bilibili.com.evil.test/sub', 'wss://private-key@one.chat.bilibili.com/sub',
    'wss://127.0.0.1/sub', 'wss://one.chat.bilibili.com:123/sub'])
def test_D01_platform_auth_cannot_be_sent_to_non_official_endpoints(link):
    with pytest.raises(BiliError):
        validate_link(link)


def test_D02_platform_identity_dedup_fallback_and_no_uid_zero_collision():
    one = map_danmaku(danmaku('one', 'actor-a'), 42)
    two = map_danmaku(danmaku('two', 'actor-b'), 42)
    assert one.user == two.user and one.user_id != two.user_id
    assert one.user_id != 'bilibili:0' and 'actor-a' not in one.user_id
    no_id = danmaku(None, 'actor-a', timestamp=1700000000)
    assert map_danmaku(no_id, 42).event_id == map_danmaku(no_id, 42).event_id
    with pytest.raises(ValueError):
        map_danmaku(danmaku(open_id='', uid=123), 42)
    with pytest.raises(ValueError):
        map_danmaku(danmaku(room_id=99), 42)


async def test_D02_same_queue_filter_cooldown_dedup_and_public_platform_event(make_agent):
    agent, api, connector = make_platform_agent(make_agent, blocked_terms=['屏蔽'])
    control = await connect(agent, role='control')
    await agent.control('start')
    await eventually(lambda: agent.platform.status == 'connected')
    ws = connector.connections[0]
    values = [danmaku('one', 'a'), danmaku('one', 'a'), danmaku('two', 'b'),
              danmaku('three', 'a', uname='换昵称'), danmaku('four', 'c', text='屏蔽'),
              danmaku('old', 'd', timestamp=int(time.time()) - 500), danmaku('emoji', 'e', dm_type=1)]
    ws.incoming.put_nowait(compressed(b''.join(wire_message(value) for value in values)))
    await eventually(lambda: agent.platform.counters['received'] == 7)
    assert len(agent.queue) == 2 and {item['source'] for item in agent.queue} == {'bilibili'}
    assert all(item['priority'] == 10 for item in agent.queue)
    assert agent.counters['accepted'] == 2 and agent.counters['duplicate'] == 1
    assert agent.platform.counters['expired'] == 1 and agent.platform.counters['dropped'] == 3
    received = [message for message in drain(control) if message['type'] == 'danmaku.received']
    assert len(received) == 2 and received[0]['data']['source'] == 'bilibili'
    public = json.dumps(agent.state())
    for secret in ['private-key', 'private-secret', 'private-code', 'private-game', 'private-auth']:
        assert secret not in public


async def test_D03_paused_still_heartbeats_but_never_queues_or_calls_llm(make_agent):
    agent, api, connector = make_platform_agent(make_agent)
    await agent.start()
    await eventually(lambda: agent.platform.status == 'connected')
    paused_message = danmaku()
    connector.connections[0].incoming.put_nowait(wire_message(paused_message))
    await eventually(lambda: agent.platform.counters['dropped'] == 1)
    await eventually(lambda: agent.platform.counters['app_heartbeats'] >= 2)
    assert not agent.queue and not agent.current and agent.counters['accepted'] == 0
    assert agent.platform.counters['socket_heartbeats'] >= 2
    assert api.starts == 1
    await agent.control('resume')
    connector.connections[0].incoming.put_nowait(wire_message(paused_message))
    await eventually(lambda: agent.platform.counters['received'] == 2)
    assert not agent.queue and agent.counters['accepted'] == 0
    assert agent.platform.counters['dropped'] == 2
    await agent.stop()
    assert api.closed and all(ws.closed for ws in connector.connections)
    assert [name for name, _ in api.calls].count('end') == 1


async def test_D03_socket_reconnect_reuses_session_switches_cluster_and_retries_once_per_budget(make_agent):
    agent, api, connector = make_platform_agent(make_agent)
    await agent.start()
    for index in range(4):
        await eventually(lambda: len(connector.connections) > index and agent.platform.status == 'connected')
        connector.connections[index].incoming.put_nowait(ConnectionError('private-auth'))
    await eventually(lambda: agent.platform.status == 'error' and agent.platform.task.done())
    assert len(connector.connections) == 4 and api.starts == 1
    assert connector.links[0] != connector.links[1]
    assert agent.platform.counters['reconnects'] == 3
    assert [name for name, _ in api.calls].count('end') == 1
    assert agent.state()['last_error']['code'] == 'bili_unavailable'
    await agent.control('resume')
    await eventually(lambda: api.starts == 2 and agent.platform.status == 'connected')
    assert agent.last_error is None


async def test_D03_rejected_socket_auth_does_not_retry_and_partial_start_is_closed(make_agent):
    agent, api, connector = make_platform_agent(make_agent, connector=FakeConnector(auth_code=-101))
    await agent.start()
    await eventually(lambda: agent.platform.task.done())
    assert agent.platform.status == 'error' and len(connector.connections) == 1
    assert agent.platform.error_code == -101
    assert [name for name, _ in api.calls].count('end') == 1
    bad = {'game_info': {'game_id': 'private-game'}, 'anchor_info': {'room_id': 'private-auth'}}
    second, bad_api, _ = make_platform_agent(make_agent, api=FakeAPI(bad_start=bad))
    await second.start()
    await eventually(lambda: second.platform.task.done())
    assert [name for name, _ in bad_api.calls].count('end') == 1
    assert second.state()['bili_room_id'] is None and 'private' not in json.dumps(second.state())


async def test_D03_expired_heartbeat_renews_only_confirmed_dead_session(make_agent):
    api = FakeAPI(heartbeat_errors=[BiliError('api_rejected', code=7003, expired=True, transient=True)])
    agent, api, connector = make_platform_agent(make_agent, api=api)
    await agent.start()
    await eventually(lambda: api.starts == 2 and agent.platform.status == 'connected')
    assert all(ws.closed for ws in connector.connections[:-1])
    assert not [name for name, _ in api.calls if name == 'end']  # old session is confirmed expired
    assert agent.platform.game_id == 'private-game-2'


async def test_D03_explicit_platform_end_stops_until_manual_resume(make_agent):
    agent, api, connector = make_platform_agent(make_agent)
    await agent.start()
    await eventually(lambda: agent.platform.status == 'connected')
    connector.connections[0].incoming.put_nowait(wire_message(
        {'game_id': agent.platform.game_id}, command='LIVE_OPEN_PLATFORM_INTERACTION_END'))
    await eventually(lambda: agent.platform.task.done())
    assert api.starts == 1 and agent.platform.reason == 'session_ended'
    assert agent.platform.game_id is None and agent.platform.status == 'error'


async def test_D03_start_timeout_is_not_blindly_repeated(make_agent):
    agent, api, connector = make_platform_agent(make_agent, api=FakeAPI(start_error=BiliError('api_unavailable', transient=True)))
    await agent.start()
    await eventually(lambda: agent.platform.task.done())
    assert api.starts == 1 and not connector.connections and agent.platform.status == 'error'


async def test_D03_missing_socket_ack_exhausts_bounded_reconnects(make_agent):
    agent, api, connector = make_platform_agent(make_agent, connector=FakeConnector(acknowledge=False))
    await agent.start()
    await eventually(lambda: agent.platform.task.done())
    assert len(connector.connections) == 4 and agent.platform.reason == 'socket_heartbeat_timeout'
    assert api.starts == 1


async def test_D02_actual_local_websocket_three_messages_to_agent_and_playback(make_agent):
    """Real sockets + signed HTTP mock + real Agent. Still not a B站 service test."""
    from websockets.asyncio.client import connect as ws_connect
    from websockets.asyncio.server import serve

    api_calls, wire_calls = [], []
    auth_body = '{"roomid":42,"key":"private-auth","note":"原始鉴权体"}'

    def http_handler(request):
        operation = str(request.url).rsplit('/', 1)[-1]
        api_calls.append((operation, json.loads(request.content)))
        assert request.headers['x-bili-content-md5'] == hashlib.md5(request.content).hexdigest()
        if operation == 'start':
            data = {'game_info': {'game_id': 'private-game'}, 'anchor_info': {'room_id': 42},
                    'websocket_info': {'auth_body': auth_body, 'wss_link': ['wss://one.chat.bilibili.com/sub']}}
        else:
            data = {}
        return httpx.Response(200, json={'code': 0, 'data': data})

    async def ws_handler(ws):
        first = decode_packets(await ws.recv(), Limits())
        assert first == [(7, auth_body.encode())]
        wire_calls.extend(first)
        # Auth acknowledgement and compressed messages in one websocket frame.
        await ws.send(pack_packet(8, b'{"code":0}') + compressed(b''.join(
            wire_message(danmaku(str(i), f'actor-{i}', text=f'这是第{i}条消息')) for i in range(3))))
        async for raw in ws:
            packets = decode_packets(raw, Limits())
            wire_calls.extend(packets)
            assert packets == [(2, b'')]
            await ws.send(pack_packet(3, struct.pack('>I', 1)))

    async with serve(ws_handler, '127.0.0.1', 0, compression=None, ping_interval=None) as server:
        local_url = f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}'
        async with httpx.AsyncClient(transport=httpx.MockTransport(http_handler)) as client:
            def factory(settings, limits, on_danmaku, on_status):
                def connector(official_url, **kwargs):
                    assert official_url == 'wss://one.chat.bilibili.com/sub'
                    return ws_connect(local_url, **kwargs)  # test transport only
                return BilibiliOpenLive(settings, limits, on_danmaku, on_status,
                                       api=OpenLiveAPI(settings, limits, client=client), connector=connector)
            limits = replace(Limits(), bili_heartbeat_interval=.03, ping_interval=10000,
                             pong_timeout=10000, handshake_timeout=10000, outbound_capacity=1000)
            agent = make_agent(settings=configured(), limits=limits, platform_factory=factory)
            stage = await connect(agent)
            await agent.control('start')
            await agent.start()
            for _ in range(3):
                await eventually(lambda: agent.phase == 'awaiting_playback')
                await ack(agent, stage, 'playback.started')
                await ack(agent, stage, 'playback.ended')
            assert agent.counters['completed'] == 3 and agent.platform.counters['accepted'] == 3
            assert [turn['event']['text'] for turn in agent.memory] == [f'这是第{i}条消息' for i in range(3)]
            assert len([message for message in drain(stage) if message['type'] == 'utterance.ready']) == 3
            await eventually(lambda: agent.platform.counters['app_heartbeats'] >= 1)
            await agent.stop()
            assert [operation for operation, _ in api_calls].count('start') == 1
            assert [operation for operation, _ in api_calls].count('end') == 1
            assert any(operation == 2 for operation, _ in wire_calls)


async def test_D03_manual_retry_during_cleanup_is_queued_only_once(make_agent):
    began, release = asyncio.Event(), asyncio.Event()
    class SlowEnd(FakeAPI):
        async def call(self, operation, body):
            if operation == 'end':
                began.set()
                await release.wait()
            return await super().call(operation, body)
    agent, api, _ = make_platform_agent(make_agent, api=SlowEnd(), connector=FakeConnector(auth_code=-101))
    await agent.start()
    await began.wait()
    for _ in range(3):
        await agent.control('resume')
    assert api.starts == 1
    release.set()
    await eventually(lambda: api.starts == 2 and agent.platform.task.done())
    assert api.starts == 2  # three clicks did not create three sessions


async def test_D03_end_timeout_is_bounded_and_visible_in_diagnostics(make_agent):
    ended = asyncio.Event()
    class HangingEnd(FakeAPI):
        async def call(self, operation, body):
            if operation == 'end':
                try:
                    await asyncio.Event().wait()
                finally:
                    ended.set()
            return await super().call(operation, body)
    limits = replace(Limits(), bili_end_timeout=.025, bili_heartbeat_interval=.025)
    agent, api, connector = make_platform_agent(make_agent, api=HangingEnd(), limits=limits)
    await agent.start()
    await eventually(lambda: agent.platform.status == 'connected')
    async with asyncio.timeout(.5):
        await agent.stop()
    assert ended.is_set() and agent.platform.counters['end_failures'] == 1
    assert connector.connections[0].closed and api.closed


async def test_D03_shutdown_during_failed_session_cleanup_finishes_one_end_request(make_agent):
    began, release, completed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    class SlowEnd(FakeAPI):
        async def call(self, operation, body):
            if operation == 'end':
                began.set()
                await release.wait()
                completed.set()
            return await super().call(operation, body)
    agent, api, _ = make_platform_agent(make_agent, api=SlowEnd(), connector=FakeConnector(auth_code=-101))
    await agent.start()
    await began.wait()
    stopping = asyncio.create_task(agent.stop())
    await asyncio.sleep(.01)
    assert not stopping.done() and not api.closed
    release.set()
    await stopping
    assert completed.is_set() and api.closed
    assert [name for name, _ in api.calls].count('end') == 1


async def test_D03_websocket_http_permission_rejection_is_not_retried(make_agent):
    from websockets.asyncio.client import connect as ws_connect
    from websockets.asyncio.server import serve
    attempts = []
    async def deny(connection, request):
        attempts.append(request.path)
        return connection.respond(403, 'Denied')
    async def never_called(ws):
        pytest.fail('Rejected socket must not reach application handler')
    async with serve(never_called, '127.0.0.1', 0, process_request=deny) as server:
        local_url = f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}'
        api = FakeAPI()
        def factory(settings, limits, on_danmaku, on_status):
            return BilibiliOpenLive(settings, limits, on_danmaku, on_status, api=api,
                connector=lambda url, **kwargs: ws_connect(local_url, **kwargs))
        agent = make_agent(settings=configured(), platform_factory=factory)
        await agent.start()
        await eventually(lambda: agent.platform.task.done())
        assert len(attempts) == 1 and agent.platform.reason == 'auth_failed'
        assert agent.platform.error_code == 403 and api.starts == 1


@pytest.mark.parametrize('identities,expected', [(['one', 'one', 'one'], 1), (['one', 'two', 'three'], 0)])
async def test_D01_reception_check_requires_distinct_events_and_closes(monkeypatch, capsys, identities, expected):
    from types import SimpleNamespace
    from tools import check_bilibili
    closed = []
    class ProbeAdapter:
        status, room_id, reason, error_code = 'connected', 42, None, None
        counters = {'end_failures': 0}
        def __init__(self, settings, limits, on_message, on_status):
            self.message, self.changed = on_message, on_status
        def start(self):
            self.task = asyncio.create_task(self.run())
        async def run(self):
            await self.changed()
            for identity in identities:
                await self.message(SimpleNamespace(event_id=identity, text='private-message'))
                await asyncio.sleep(0)
        async def aclose(self):
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            closed.append(True)
        def diagnostics(self):
            return self.counters.copy()
    monkeypatch.setattr(check_bilibili, 'BilibiliOpenLive', ProbeAdapter)
    assert await check_bilibili.listen(configured(), .02) == expected
    output = capsys.readouterr().out
    assert 'private-message' not in output and closed == [True]
