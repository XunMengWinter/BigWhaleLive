import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest

from config import Limits, Settings
from contracts import ApiError, Danmaku
from conftest import Clock, ack, connect, drain, flush, turn


async def test_A01_default_paused_offline(make_agent):
    agent = make_agent()
    stage = await connect(agent)
    state = agent.state()
    assert (state['mode'], state['phase'], state['llm_mode'], state['tts_mode'], state['bili_status']) == ('paused', 'idle', 'demo', 'off', 'disabled')
    agent.clock.advance(30)
    await agent.tick()
    await flush()
    assert not agent.current and not agent.work
    assert not any(message['type'] == 'utterance.ready' for message in drain(stage))


async def test_A02_autonomous_cadence_and_confirmation(make_agent):
    agent = make_agent()
    stage = await connect(agent)
    await agent.control('start')
    agent.clock.advance(14)
    await agent.tick()
    assert agent.current is None
    agent.clock.advance(1)
    await agent.tick()
    await flush()
    assert agent.current['kind'] == 'autonomous' and agent.phase == 'awaiting_playback'
    assert not agent.memory
    ready = [m for m in drain(stage) if m['type'] == 'utterance.ready']
    assert len(ready) == 1 and ready[0]['data']['audio_url'] is None
    await ack(agent, stage)
    assert agent.phase == 'playing'
    await ack(agent, stage, 'playback.ended')
    assert len(agent.memory) == 1 and agent.counters['completed'] == 1
    await agent.tick()
    assert agent.current is None


async def test_A03_reply_and_exactly_once_history(make_agent):
    agent = make_agent()
    stage = await connect(agent)
    await agent.control('start')
    ready = await turn(agent, stage, '你怎么又在摸鱼？', '小明')
    assert ready['data']['text'] and ready['data']['kind'] == 'reply'
    identity = {'instance_id': agent.instance_id, 'epoch': agent.epoch, 'utterance_id': agent.current['utterance_id']}
    await ack(agent, stage)
    await ack(agent, stage, 'playback.ended')
    await ack(agent, stage, 'playback.ended', identity)
    assert agent.counters['completed'] == 1 and len(agent.memory) == 1
    assert agent.memory[0]['event']['text'] == '你怎么又在摸鱼？'


async def test_A04_dedupe_conflict_and_historical_acceptance(make_agent):
    agent = make_agent()
    await agent.control('start')
    message = Danmaku(user='小明', text='你好', client_message_id=str(uuid4()))
    assert (await agent.accept(message))[0] == 202
    await agent.control('pause')
    status, body = await agent.accept(message)
    assert status == 200 and body['duplicate'] and body['accepted']
    with pytest.raises(ApiError, match='id_conflict'):
        await agent.accept(message.model_copy(update={'text': '另一条内容'}))
    assert not agent.queue and agent.counters['accepted'] == 1


async def test_A05_cooldown_capacity_and_rejection_does_not_consume_id(make_agent):
    agent = make_agent(settings=Settings(queue_capacity=1))
    await agent.control('start')
    await agent.accept(Danmaku(user='一', text='第一条'))
    with pytest.raises(ApiError, match='user_cooldown'):
        await agent.accept(Danmaku(user='一', text='第二条'))
    retry = Danmaku(user='二', text='第三条', client_message_id=str(uuid4()))
    with pytest.raises(ApiError, match='queue_full'):
        await agent.accept(retry)
    assert retry.client_message_id not in agent.dedupe
    assert 'local:二' not in agent.cooldowns
    agent.clock.advance(60)
    await agent.tick()
    assert (await agent.accept(retry))[0] == 202


async def test_A06_normalized_input_and_output_filter(make_agent):
    agent = make_agent(blocked_terms=['blocked'])
    await agent.control('start')
    with pytest.raises(ApiError, match='content_blocked'):
        await agent.accept(Danmaku(user='观众', text='ＢＬＯＣＫＥＤ'))
    assert agent.counters['accepted'] == 0
    class BlockedLLM:
        async def generate(self, event, history, *, scene=None):
            return {'text': 'blocked'}
    agent.llm = BlockedLLM()
    stage = await connect(agent)
    await agent.accept(Danmaku(user='观众', text='允许的输入'))
    await agent.tick()
    await flush()
    assert agent.last_error['code'] == 'content_blocked'
    assert not any(m['type'] == 'utterance.ready' for m in drain(stage))


async def test_A07_expired_input_never_generates(make_agent):
    agent = make_agent()
    await agent.control('start')
    await agent.accept(Danmaku(user='观众', text='旧消息'))
    agent.clock.advance(60)
    await agent.tick()
    assert not agent.queue and agent.counters['expired'] == 1
    stage = await connect(agent)
    ready = await turn(agent, stage, '新的消息', '新观众')
    assert agent.current['event']['text'] == '新的消息'
    assert agent.current['event']['user'] == '新观众'


async def test_A08_normal_danmaku_waits_without_overlap(make_agent):
    agent = make_agent()
    stage = await connect(agent)
    await agent.control('start')
    await turn(agent, stage)
    await ack(agent, stage)
    identity = agent.current['utterance_id']
    await agent.accept(Danmaku(user='二号', text='排队吧'))
    await agent.tick()
    assert agent.current['utterance_id'] == identity and len(agent.queue) == 1
    assert not any(m['type'] == 'utterance.ready' for m in drain(stage))
    await ack(agent, stage, 'playback.ended')
    await agent.tick()
    await flush()
    assert agent.current['utterance_id'] != identity


class GateLLM:
    def __init__(self):
        self.release = asyncio.Event()
    async def generate(self, event, history, *, scene=None):
        while not self.release.is_set():
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                pass  # Deliberately uncooperative provider to prove epoch guards.
        return {'text': '迟到的台词'}


class GateTTS:
    def __init__(self):
        self.release = asyncio.Event()
    async def stream(self, text):
        yield b'partial'
        while not self.release.is_set():
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                pass
        yield b'complete'


@pytest.mark.parametrize('phase', ['generating', 'synthesizing', 'awaiting_playback', 'playing'])
async def test_A09_pause_invalidates_all_inflight_phases(make_agent, phase):
    llm, tts = GateLLM(), GateTTS()
    kwargs = {'llm': llm} if phase == 'generating' else {}
    if phase == 'synthesizing':
        kwargs.update(tts=tts, settings=Settings(tts_mode='edge'))
    agent = make_agent(**kwargs)
    stage = await connect(agent)
    await agent.control('start')
    await agent.accept(Danmaku(user='一', text='第一条'))
    await agent.tick()
    await flush()
    if phase == 'playing':
        await ack(agent, stage)
    assert agent.phase == phase
    identity = {'instance_id': agent.instance_id, 'epoch': agent.epoch, 'utterance_id': agent.current['utterance_id']}
    await agent.accept(Danmaku(user='二', text='等待中'))
    drain(stage)
    await agent.control('pause')
    assert agent.mode == 'paused' and agent.phase == 'idle' and not agent.queue
    assert agent.epoch > identity['epoch']
    llm.release.set()
    tts.release.set()
    await flush()
    await ack(agent, stage, 'playback.ended', identity)
    assert not agent.current and not agent.memory
    assert not any(m['type'] == 'utterance.ready' for m in drain(stage))
    assert not list(agent.audio.directory.glob('*.tmp'))
    assert not list(agent.audio.directory.glob('*.mp3'))


async def test_A10_idempotent_controls_and_resume(make_agent):
    agent = make_agent()
    stage = await connect(agent)
    await agent.start()
    runner = agent.runner
    await agent.start()
    await agent.control('start')
    deadline = agent.next_autonomous
    agent.clock.advance(1)
    await agent.control('start')
    assert agent.next_autonomous == deadline and agent.runner is runner
    await agent.control('pause')
    epoch = agent.epoch
    await agent.control('pause')
    assert agent.epoch == epoch
    await agent.control('resume')
    await turn(agent, stage)
    assert agent.phase == 'awaiting_playback'


async def test_A11_skip_keeps_queue_and_ignores_old_work(make_agent):
    llm = GateLLM()
    agent = make_agent(llm=llm)
    stage = await connect(agent)
    await agent.control('start')
    await agent.accept(Danmaku(user='一', text='被跳过'))
    await agent.tick()
    await flush()
    await agent.accept(Danmaku(user='二', text='要保留'))
    await agent.control('skip')
    assert len(agent.queue) == 1
    with pytest.raises(ApiError, match='no_active_utterance'):
        await agent.control('skip')
    llm.release.set()
    await flush()
    assert not agent.current
    await agent.tick()
    await flush()
    assert agent.current['event']['text'] == '要保留'


async def test_A12_single_owner_observer_and_invalid_acks(make_agent):
    agent = make_agent()
    owner = await connect(agent)
    observer = await connect(agent)
    control = await connect(agent, 'control')
    assert agent.owner == owner.identity
    await agent.control('start')
    await turn(agent, owner)
    assert not any(m['type'] == 'utterance.ready' for m in drain(observer))
    await ack(agent, observer)
    await ack(agent, control)
    assert agent.phase == 'awaiting_playback'
    await ack(agent, owner)
    assert agent.phase == 'playing'
    await ack(agent, owner)
    assert agent.counters['completed'] == 0


async def test_A13_disconnect_requires_new_explicit_claim(make_agent):
    agent = make_agent()
    owner = await connect(agent)
    observer = await connect(agent)
    await agent.control('start')
    await turn(agent, owner)
    await agent.disconnect(owner.identity)
    assert not agent.owner and not agent.current and agent.counters['failed'] == 1
    await agent.accept(Danmaku(user='新观众', text='等待舞台'))
    await agent.tick()
    assert not agent.current
    await agent.handle(observer, {'v':1,'type':'renderer.ready','data': {
        'ready':True,'claim_playback':True,'audio_status':'off','character_mode':'demo'}})
    await agent.tick()
    await flush()
    assert agent.owner == observer.identity and agent.current


async def test_A13_heartbeat_handshake_and_slow_connection(make_agent):
    clock = Clock()
    agent = make_agent(clock=clock, limits=replace(Limits(), outbound_capacity=3))
    idle = await agent.connect()
    clock.advance(5)
    await agent.tick()
    assert idle.close_code == 1008
    owner = await connect(agent)
    await agent.control('start')
    drain(owner)
    clock.advance(5)
    await agent.tick()
    ping = next(m for m in drain(owner) if m['type'] == 'server.ping')
    await agent.handle(owner, {'v':1, 'type':'client.pong', 'data':ping['data']})
    clock.advance(9)
    await agent.tick()
    assert agent.owner == owner.identity
    drain(owner)
    clock.advance(1)
    await agent.tick()
    assert owner.close_code == 1001 and agent.owner is None
    fresh = await connect(agent)
    for _ in range(5):
        await agent.control('start')
    assert fresh.close_code == 1013
    await agent.tick()
    assert agent.owner is None


@pytest.mark.parametrize('started', [False, True])
async def test_A14_playback_timeouts_recover(make_agent, started):
    agent = make_agent()
    stage = await connect(agent)
    await agent.control('start')
    await turn(agent, stage)
    if started:
        await ack(agent, stage)
    agent.clock.advance(45 if started else 10)
    await agent.tick()
    assert agent.last_error['code'] == 'playback_timeout'
    assert agent.counters['failed'] == 1 and not agent.owner and not agent.current
    await agent.tick()
    assert agent.counters['failed'] == 1
    await agent.handle(stage, {'v':1,'type':'renderer.ready','data':{
        'ready':True,'claim_playback':True,'audio_status':'off','character_mode':'demo'}})
    await turn(agent, stage, user='新观众')
    assert agent.current


async def test_A15_old_instance_ignored(make_agent):
    old, new = make_agent(), make_agent()
    stage = await connect(new)
    await new.control('start')
    await turn(new, stage)
    identity = {'instance_id':old.instance_id,'epoch':new.epoch,'utterance_id':new.current['utterance_id']}
    await ack(new, stage, identity=identity)
    assert new.phase == 'awaiting_playback' and new.counters['completed'] == 0


@pytest.mark.parametrize('value,code', [('invalid JSON','llm_invalid_output'), ({'text':'x'*121},'llm_invalid_output'), (None,'llm_invalid_output'), (RuntimeError('SECRET'),'llm_unavailable')])
async def test_A17_invalid_model_output_backoff_and_recovery(make_agent, value, code):
    class FakeLLM:
        async def generate(self, event, history, *, scene=None):
            if isinstance(value, Exception):
                raise value
            return value
    agent = make_agent(llm=FakeLLM())
    stage = await connect(agent)
    await agent.control('start')
    await agent.accept(Danmaku(user='一', text='一'))
    await agent.tick()
    await flush()
    assert agent.last_error['code'] == code and agent.state()['blocked_reason'] == 'provider_backoff'
    assert 'SECRET' not in str(agent.state())
    from providers.llm import DemoLLM
    agent.llm = DemoLLM('小鱼', agent.root)
    await agent.accept(Danmaku(user='二', text='二'))
    await agent.tick()
    assert not agent.current
    agent.clock.advance(5)
    await agent.tick()
    await flush()
    assert agent.current and agent.phase == 'awaiting_playback'


async def test_A17_unknown_actions_fallback_and_timeout(make_agent):
    class Unknown:
        async def generate(self, event, history, *, scene=None):
            return '```json\n{"text":"合格台词","emotion":"hacked","action":"execute","priority":999}\n```'
    agent = make_agent(llm=Unknown())
    stage = await connect(agent)
    await agent.control('start')
    ready = await turn(agent, stage)
    assert ready['data']['action'] == 'none' and ready['data']['emotion'] == 'neutral'
    assert 'priority' not in ready['data']
    await agent.control('skip')
    class Slow:
        async def generate(self, event, history, *, scene=None):
            await asyncio.Event().wait()
    agent.llm = Slow()
    agent.limits = replace(agent.limits, llm_timeout=.01)
    await agent.accept(Danmaku(user='新观众', text='超时'))
    await agent.tick()
    await asyncio.sleep(.03)
    assert agent.last_error['code'] == 'llm_timeout' and not agent.current


@pytest.mark.parametrize('mode', ['failure','oversize','timeout'])
async def test_A18_tts_failure_falls_back_and_cleans_files(make_agent, mode):
    class FakeTTS:
        async def stream(self, text):
            yield b'1234'
            if mode == 'failure':
                raise RuntimeError('secret')
            if mode == 'timeout':
                await asyncio.Event().wait()
            yield b'567890'
    limits = replace(Limits(), audio_bytes=8, tts_timeout=.01, ping_interval=100000, pong_timeout=100000, outbound_capacity=1000)
    agent = make_agent(settings=Settings(tts_mode='edge'), tts=FakeTTS(), limits=limits)
    stage = await connect(agent)
    await agent.control('start')
    await agent.accept(Danmaku(user='一', text='测试语音'))
    await agent.tick()
    await asyncio.sleep(.03)
    assert agent.phase == 'awaiting_playback' and agent.tts_status == 'error'
    ready = next(m for m in drain(stage) if m['type'] == 'utterance.ready')
    assert ready['data']['audio_url'] is None and ready['data']['tts_status'] == 'error'
    assert not list(agent.audio.directory.glob('*.tmp'))
    assert not list(agent.audio.directory.glob('*.mp3'))
    await ack(agent, stage)
    await ack(agent, stage, 'playback.ended')
    assert agent.counters['failed'] == 1 and agent.counters['completed'] == 1


async def test_A19_memory_dedupe_and_cooldowns_are_bounded(make_agent):
    agent = make_agent(limits=replace(Limits(), dedupe_capacity=5, dedupe_ttl=10, outbound_capacity=1000, ping_interval=100000, pong_timeout=100000))
    stage = await connect(agent)
    await agent.control('start')
    for index in range(25):
        await turn(agent, stage, user=f'观众{index}')
        await ack(agent, stage)
        await ack(agent, stage, 'playback.ended')
        drain(stage)
    assert len(agent.memory) == 20 and len(agent.dedupe) <= 5
    assert agent.memory[0]['event']['user'] == '观众5'
    agent.clock.advance(10)
    await agent.tick()
    assert not agent.dedupe and not agent.cooldowns
