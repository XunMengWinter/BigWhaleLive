import asyncio
import shutil
import socket
from dataclasses import replace

import pytest

from agent import Agent
from config import ROOT, Limits, Settings
from urllib.parse import urlsplit


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    original_connect = socket.socket.connect
    original_resolve = socket.getaddrinfo

    def connect(sock, address):
        if isinstance(address, tuple) and address[0] not in ('127.0.0.1', 'localhost', '::1'):
            raise AssertionError('External network is forbidden in stage 1A tests')
        return original_connect(sock, address)

    def resolve(host, *args, **kwargs):
        if host not in ('127.0.0.1', 'localhost', '::1', None):
            raise AssertionError('External DNS is forbidden in stage 1A tests')
        return original_resolve(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, 'connect', connect)
    monkeypatch.setattr(socket, 'getaddrinfo', resolve)
    # curl_cffi uses native sockets, which the Python socket guard cannot see.
    # Guard its public request entry as well; live verification runs separately.
    from curl_cffi.requests import AsyncSession
    original_request = AsyncSession.request
    async def native_request(self, method, url, *args, **kwargs):
        if urlsplit(str(url)).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise AssertionError('External native HTTP is forbidden in tests')
        return await original_request(self, method, url, *args, **kwargs)
    monkeypatch.setattr(AsyncSession, 'request', native_request)


@pytest.fixture
def root(tmp_path):
    for name in ('prompts', 'config'):
        shutil.copytree(ROOT / name, tmp_path / name)
    shutil.copytree(ROOT / 'static', tmp_path / 'static', ignore=shutil.ignore_patterns('audio', 'generated'))
    (tmp_path / 'models').mkdir()
    (tmp_path / 'vendor').mkdir()
    return tmp_path


@pytest.fixture
async def make_agent(root):
    created = []

    def make(*, settings=None, clock=None, limits=None, **kwargs):
        injected = limits or replace(Limits(), ping_interval=100000, pong_timeout=100000,
                                     handshake_timeout=100000, outbound_capacity=1000)
        agent = Agent(settings or Settings(), root, clock=clock or Clock(), limits=injected, **kwargs)
        created.append(agent)
        return agent

    yield make
    for agent in created:
        await agent.stop()


async def flush():
    for _ in range(8):
        await asyncio.sleep(0)


def drain(client):
    result = []
    while not client.queue.empty():
        result.append(client.queue.get_nowait())
    return result


async def connect(agent, role='stage', ready=True):
    client = await agent.connect()
    drain(client)
    await agent.handle(client, {'v': 1, 'type': 'client.hello', 'data': {'role': role}})
    drain(client)
    if role == 'stage' and ready:
        await agent.handle(client, {'v': 1, 'type': 'renderer.ready', 'data': {
            'ready': True, 'claim_playback': True,
            'audio_status': 'off' if agent.settings.tts_mode == 'off' else 'ready', 'character_mode': 'demo'}})
        drain(client)
    return client


async def ack(agent, client, kind='playback.started', identity=None, **extra):
    identity = identity or {'instance_id': agent.instance_id, 'epoch': agent.epoch,
                            'utterance_id': agent.current['utterance_id']}
    await agent.handle(client, {'v': 1, 'type': kind, 'data': {**identity, **extra}})


async def turn(agent, client, text='你好', user=None):
    from contracts import Danmaku
    await agent.accept(Danmaku(user=user or f'观众{agent.counters["accepted"]}', text=text))
    await agent.tick()
    await flush()
    messages = drain(client)
    ready = [message for message in messages if message['type'] == 'utterance.ready']
    assert len(ready) == 1
    return ready[0]
