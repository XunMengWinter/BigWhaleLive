from dataclasses import replace

from config import Settings
from contracts import Danmaku
from conftest import ack, connect, drain, flush


async def test_B02_voice_readiness_blocks_generation_then_rejection_stops_future_calls(make_agent):
    class LLM:
        calls=0
        async def generate(self,event,history, *, scene=None):
            self.calls+=1
            return {'text':'这是测试台词。'}
    class TTS:
        calls=0
        async def stream(self,text):
            self.calls+=1
            yield b'mp3-data'
    llm,tts=LLM(),TTS()
    settings=Settings(tts_mode='edge',llm_mode='openai',llm_base_url='https://api.deepseek.com',llm_model='deepseek-flash',llm_api_key='test-only')
    agent=make_agent(settings=settings,llm=llm,tts=tts)
    stage=await connect(agent,ready=False)
    await agent.control('start')
    await agent.accept(Danmaku(user='一',text='测试'))
    await agent.handle(stage,{'v':1,'type':'renderer.ready','data':{
        'ready':True,'claim_playback':True,'audio_status':'off','character_mode':'demo'}})
    await agent.tick();await flush()
    assert not agent.owner and llm.calls==tts.calls==0
    await agent.handle(stage,{'v':1,'type':'renderer.ready','data':{
        'ready':True,'claim_playback':True,'audio_status':'ready','character_mode':'demo'}})
    await agent.tick();await flush()
    ready=next(m for m in drain(stage) if m['type']=='utterance.ready')
    assert ready['data']['audio_url'] and ready['data']['display_duration_ms'] is None
    await ack(agent,stage,'playback.error',code='autoplay_blocked')
    assert agent.state()['blocked_reason']=='audio_blocked' and not agent.owner
    assert not agent.memory and agent.counters['completed']==0
    await agent.accept(Danmaku(user='二',text='新消息'))
    agent.clock.advance(15)
    await agent.tick();await flush()
    assert llm.calls==tts.calls==1
    await agent.handle(stage,{'v':1,'type':'renderer.ready','data':{
        'ready':True,'claim_playback':True,'audio_status':'ready','character_mode':'demo'}})
    await agent.tick();await flush()
    await ack(agent,stage)
    await ack(agent,stage,'playback.ended')
    assert llm.calls==tts.calls==2 and agent.counters['completed']==1
    assert agent.last_error is None


async def test_B03_timings_start_at_event_receipt_and_are_bounded(make_agent):
    agent=make_agent()
    stage=await connect(agent)
    await agent.control('start')
    await agent.accept(Danmaku(user='一',text='测试'))
    agent.clock.advance(2)
    await agent.tick();await flush()
    diagnostic=agent.state()['diagnostics']['recent'][-1]
    assert diagnostic['ready_ms']==2000 and diagnostic['llm_ms']==0
    agent.clock.advance(1)
    await ack(agent,stage)
    assert agent.state()['diagnostics']['recent'][-1]['started_ms']==3000
    await ack(agent,stage,'playback.ended')
    assert agent.state()['diagnostics']['recent'][-1]['result']=='completed'
    assert '测试' not in str(agent.state()['diagnostics'])
