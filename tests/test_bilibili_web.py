import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace
import time
from urllib.parse import parse_qs, urlsplit

import brotli
import pytest

from bilibili_adapter import BiliError, HEADER, decode_packets, map_danmaku, pack_packet
from bilibili_web import BilibiliWeb, WebRoomAPI, web_danmaku, web_room_info, wbi_query
from config import Limits, Settings
from conftest import ack, connect
from test_bilibili import FakeConnector, eventually


def raw_message(uid=123, name='观众', text='你好呀', *, timestamp=None, nonce='one'):
    meta = [0, 1, 25, 16777215, int(time.time() * 1000) if timestamp is None else timestamp,
            nonce, 0, '', 0, 0, 0, 0, 0]
    return {'cmd': 'DANMU_MSG', 'info': [meta, text, [uid, name]]}


def br_packet(data):
    body = brotli.compress(data)
    return HEADER.pack(16 + len(body), 16, 3, 5, 1) + body


def test_web_wbi_golden_matches_upstream_javascript():
    assert wbi_query({'id': 9748572, 'type': 0, 'web_location': '444.8'},
                     '0123456789abcdef' * 2, 'fedcba9876543210' * 2, timestamp=1700000000) == (
        'id=9748572&type=0&web_location=444.8&wts=1700000000&w_rid=cd3bb0d722c82559503d16098633b84f')
    query = wbi_query({'x': "hello world!'()*"}, 'a' * 32, 'b' * 32, timestamp=1)
    assert query.startswith('wts=1&x=hello%20world&')


def test_web_brotli_nested_packet_decode_and_expansion_limits():
    original = pack_packet(5, json.dumps(raw_message(), ensure_ascii=False).encode())
    assert decode_packets(br_packet(original), Limits(), allow_brotli=True) == decode_packets(original, Limits())
    with pytest.raises(BiliError):
        decode_packets(br_packet(original), Limits())  # official mode remains strict
    with pytest.raises(BiliError):
        decode_packets(br_packet(b'x' * 1000000), replace(Limits(), bili_decoded_bytes=100), allow_brotli=True)
    for invalid in [b'broken', brotli.compress(original) + b'extra', brotli.compress(original)[:-1]]:
        packet = HEADER.pack(16 + len(invalid), 16, 3, 5, 1) + invalid
        with pytest.raises(BiliError):
            decode_packets(packet, Limits(), allow_brotli=True)


def test_web_map_uses_uid_and_original_timestamp_and_stable_identity():
    value = raw_message(timestamp=1700000000123)
    mapped = web_danmaku(value, 9748572)
    assert mapped['timestamp'] == 1700000000
    one = map_danmaku(mapped, 9748572)
    assert one.event_id == map_danmaku(web_danmaku(value, 9748572), 9748572).event_id
    other = map_danmaku(web_danmaku(raw_message(uid=456, timestamp=1700000000123), 9748572), 9748572)
    assert other.user_id != one.user_id and other.user == one.user
    anonymous = web_danmaku(raw_message(uid=0, name=''), 9748572)
    assert anonymous['anonymous'] and anonymous['uname'] == '匿名观众'
    assert anonymous['open_id'] == 'web-anonymous-room:9748572'
    value['info'][0][12] = 1
    assert web_danmaku(value, 9748572) is None


@pytest.mark.parametrize('value', [{}, {'info': []}, {'info': [[], 'x', []]}, raw_message(uid=-1), raw_message(timestamp=float('inf'))])
def test_web_invalid_message_shapes_are_rejected(value):
    with pytest.raises(ValueError):
        web_danmaku(value, 9748572)


def test_web_html_uses_json_decoder_not_script_execution():
    html = '<script>window.__NEPTUNE_IS_MY_WAIFU__=' + json.dumps({'roomInfoRes': {'data': {
        'room_info': {'room_id': 9748572, 'live_status': 1}}}}) + ';throw new Error("must not execute");</script>'
    assert web_room_info(html) == (9748572, 1)
    with pytest.raises(BiliError):
        web_room_info('<script>window.__NEPTUNE_IS_MY_WAIFU__=evil()</script>')


class Cookies:
    def __init__(self):
        self.values = {}
    def set(self, name, value, **kwargs):
        assert kwargs['domain'] == '.bilibili.com' and kwargs['secure'] is True
        self.values[name] = value


class HTTPClient:
    def __init__(self, *, authenticated=False, response_hook=None):
        self.cookies, self.calls, self.closed = Cookies(), [], False
        self.authenticated, self.hook = authenticated, response_hook
    async def get(self, url, **kwargs):
        self.calls.append(url)
        path = urlsplit(url).path
        if path.endswith('/spi/'):
            value = {'code': 0, 'data': {'b_3': 'private-buvid'}}
        elif path.endswith('/nav'):
            value = {'code': 0 if self.authenticated else -101, 'data': {
                'isLogin': self.authenticated, 'mid': 99 if self.authenticated else 0,
                'wbi_img': {'img_url': 'https://i0.hdslb.com/' + 'a' * 32 + '.png',
                            'sub_url': 'https://i0.hdslb.com/' + 'b' * 32 + '.png'}}}
        elif path == '/123':
            value = '<script>window.__NEPTUNE_IS_MY_WAIFU__=' + json.dumps({'roomInfoRes': {'data': {
                'room_info': {'room_id': 9748572, 'live_status': 1}}}}) + '</script>'
        elif path.endswith('/getDanmuInfo'):
            assert parse_qs(urlsplit(url).query)['id'] == ['9748572']
            value = {'code': 0, 'data': {'token': 'private-token', 'host_list': [
                {'host': 'one.chat.bilibili.com', 'wss_port': 2245}]}}
        else:
            pytest.fail('Unexpected web API URL')
        status = 200
        if self.hook:
            status, value = self.hook(path, value)
        raw = value.encode() if isinstance(value, str) else json.dumps(value).encode()
        assert kwargs['allow_redirects'] is False
        result = kwargs['content_callback'](raw)
        if result == 0:
            raise RuntimeError('private-token')
        return SimpleNamespace(status_code=status)
    async def close(self):
        self.closed = True


async def test_web_prepare_anonymous_canonical_room_and_secret_boundaries():
    client = HTTPClient()
    api = WebRoomAPI(Settings(bili_mode='web', bili_room_id=123), Limits(), client=client)
    room, links, auth = await api.prepare(123)
    assert room == 9748572 and links == ('wss://one.chat.bilibili.com:2245/sub',)
    assert json.loads(auth) == {'uid': 0, 'roomid': 9748572, 'protover': 3,
                              'platform': 'web', 'type': 2, 'buvid': 'private-buvid', 'key': 'private-token'}
    assert not api.authenticated and api.live_status == 1 and len(client.calls) == 4
    await api.aclose()
    assert client.closed


async def test_web_reader_rejects_account_login_state():
    client = HTTPClient(authenticated=True)
    api = WebRoomAPI(Settings(bili_mode='web'), Limits(), client=client)
    with pytest.raises(BiliError, match='web_guest_session_required'):
        await api.prepare(123)
    assert len(client.calls) == 2 and 'SESSDATA' not in client.cookies.values


@pytest.mark.parametrize('status,value,reason', [(412, {}, 'web_http_rejected'),
    (200, {'code': True}, 'web_invalid_response'), (200, 'x' * 300, 'web_invalid_response')])
async def test_web_response_limits_and_rejections_are_safe(status, value, reason):
    client = HTTPClient(response_hook=lambda path, original: (status, value))
    api = WebRoomAPI(Settings(bili_mode='web'), replace(Limits(), bili_response_bytes=100), client=client)
    with pytest.raises(BiliError, match=reason) as error:
        await api.prepare(123)
    assert 'private' not in str(error.value)


async def test_web_disallows_foreign_host_and_port_in_api_response():
    def hook(path, value):
        if path.endswith('/getDanmuInfo'):
            value['data']['host_list'][0]['host'] = 'steal.example.com'
        return 200, value
    api = WebRoomAPI(Settings(bili_mode='web'), Limits(), client=HTTPClient(response_hook=hook))
    with pytest.raises(BiliError, match='web_invalid_response'):
        await api.prepare(123)


class RoomAPI:
    authenticated, live_status = False, 1
    def __init__(self):
        self.prepared, self.closed = 0, False
    async def prepare(self, room_id):
        self.prepared += 1
        return room_id, ('wss://one.chat.bilibili.com:2245/sub',), b'{"uid":0,"key":"private-token"}'
    def websocket_headers(self):
        return {'Cookie': 'buvid3=private-buvid'}
    async def aclose(self):
        self.closed = True


async def test_web_three_brotli_messages_same_agent_and_no_official_rpc(make_agent):
    api, connector = RoomAPI(), FakeConnector()
    limits = replace(Limits(), bili_web_heartbeat_interval=.02, bili_web_heartbeat_timeout=.2,
                     ping_interval=10000, pong_timeout=10000, outbound_capacity=1000)
    def factory(settings, limits, on_message, on_status):
        return BilibiliWeb(settings, limits, on_message, on_status, api=api, connector=connector)
    agent = make_agent(settings=Settings(bili_mode='web'), limits=limits, platform_factory=factory)
    stage = await connect(agent)
    await agent.control('start')
    await agent.start()
    await eventually(lambda: agent.platform.status == 'connected')
    for i in range(3):
        body = json.dumps(raw_message(uid=100+i, text=f'你好{i}', nonce=str(i)), ensure_ascii=False).encode()
        connector.connections[0].incoming.put_nowait(br_packet(pack_packet(5, body)))
        await eventually(lambda: agent.phase == 'awaiting_playback')
        await ack(agent, stage, 'playback.started')
        await ack(agent, stage, 'playback.ended')
    public = json.dumps(agent.state())
    assert agent.counters['completed'] == 3 and agent.platform.counters['accepted'] == 3
    assert agent.state()['bili_mode'] == 'web' and agent.state()['bili_room_id'] == 9748572
    assert agent.platform.counters['app_heartbeats'] == 0 and agent.platform.app_heartbeat is None
    assert all(value not in public for value in ['private-token', 'private-buvid'])
    first = connector.connections[0].sent[0]
    assert HEADER.unpack(first[:16])[2:] == (1, 7, 1)
    await agent.stop()
    assert api.closed and all(ws.closed for ws in connector.connections)


async def test_web_masked_identity_keeps_reading_and_uses_anonymous_cooldown(make_agent):
    api, connector = RoomAPI(), FakeConnector()
    def factory(settings, limits, on_message, on_status):
        return BilibiliWeb(settings, limits, on_message, on_status, api=api, connector=connector)
    agent = make_agent(settings=Settings(bili_mode='web'), platform_factory=factory)
    await agent.control('start')
    await agent.start()
    await eventually(lambda: agent.platform.status == 'connected')
    for i in range(2):
        connector.connections[0].incoming.put_nowait(pack_packet(5, json.dumps(raw_message(uid=0,nonce=str(i))).encode()))
    await eventually(lambda: agent.platform.counters['received']==2)
    assert agent.platform.status == 'connected' and len(agent.queue)==1
    assert agent.platform.counters['anonymous']==2 and agent.platform.counters['dropped']==1


async def test_web_retries_are_bounded_but_stable_connections_reset_failure_budget(make_agent):
    api, connector, clock = RoomAPI(), FakeConnector(), [0.0]
    limits = replace(Limits(), bili_retry_delays=(.005, .005, .005), bili_web_heartbeat_interval=.01)
    def factory(settings, limits, on_message, on_status):
        return BilibiliWeb(settings, limits, on_message, on_status, api=api, connector=connector, clock=lambda:clock[0])
    agent = make_agent(settings=Settings(bili_mode='web'), limits=limits, platform_factory=factory)
    await agent.start()
    for index in range(6):
        await eventually(lambda:len(connector.connections)>index and agent.platform.status=='connected')
        if index == 2:
            clock[0] = 35
            connector.connections[index].incoming.put_nowait(pack_packet(3, b'\0\0\0\1'))
            await eventually(lambda:agent.platform.last_ws_ack == 35)
        connector.connections[index].incoming.put_nowait(ConnectionError('private-token'))
    await eventually(lambda:agent.platform.task.done())
    assert len(connector.connections) == 6 and agent.platform.counters['reconnects'] == 5
    assert api.prepared == 6 and agent.platform.status == 'error'
