import asyncio
import os
import time
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from config import ConfigurationError, Limits, Settings, load_settings
from contracts import Danmaku, parse_speech
from main import create_app
from providers.tts import AudioStore

BASE = 'http://127.0.0.1:8765'
ORIGIN = {'origin': BASE, 'host': '127.0.0.1:8765'}


@pytest.fixture
def client(root):
    with TestClient(create_app(settings=Settings(), root=root), base_url=BASE) as client:
        yield client


def until(ws, kind, predicate=lambda message: True):
    for _ in range(80):
        message = ws.receive_json()
        if message['type'] == 'server.ping':
            ws.send_json({'v':1,'type':'client.pong','data':message['data']})
        if message['type'] == kind and predicate(message):
            return message
    raise AssertionError('Expected event was not observed')


def test_A01_http_static_health_and_paused_state(client):
    assert client.get('/').status_code == 200
    assert 'AI 虚拟主播' in client.get('/').text
    assert '模拟弹幕' in client.get('/control').text
    assert client.get('/static/js/client.js').status_code == 200
    assert client.get('/api/health').json()['protocol_version'] == 1
    state = client.get('/api/state').json()
    assert state['mode'] == 'paused' and state['current'] is None
    response = client.post('/api/danmaku', json={'user':'一','text':'你好'})
    assert response.status_code == 409 and response.json()['error']['code'] == 'agent_paused'


@pytest.mark.parametrize('body', [
    {'user':'','text':'你好'}, {'user':'一','text':'  '}, {'user':'x'*33,'text':'hi'},
    {'user':'一','text':'x'*201}, {'user':'一','text':'你好','priority':100},
    {'user':123,'text':'hi'}, {'user':'一','text':'hi','client_message_id':'wrong'}
])
def test_A06_validation_is_safe_and_counted(client, body):
    response = client.post('/api/danmaku', json=body)
    assert response.status_code == 422
    assert set(response.json()) == {'error'}
    assert response.json()['error']['request_id']
    assert client.get('/api/state').json()['counters']['rejected'] == 1


def test_A06_request_limits_and_cleaning(client):
    assert client.post('/api/control', content='{}').status_code == 415
    assert client.post('/api/danmaku', content='x'*16385, headers={'content-type':'application/json'}).status_code == 413
    assert client.post('/api/control', content='not json', headers={'content-type':'application/json'}).status_code == 422
    assert Danmaku(user=' 一\u0000 ', text=' 你好\u0001 ').model_dump()['text'] == '你好'


def test_A03_websocket_reply_control_and_observer(client):
    with client.websocket_connect('/ws', headers=ORIGIN) as stage:
        initial = until(stage, 'state.snapshot')
        owner_id = initial['data']['connection_id']
        stage.send_json({'v':1,'type':'client.hello','data':{'role':'stage'}})
        stage.send_json({'v':1,'type':'renderer.ready','data':{
            'ready':True,'claim_playback':True,'audio_status':'off','character_mode':'demo'}})
        until(stage, 'state.snapshot', lambda m: m['data']['state']['playback_owner_id'] == owner_id)
        assert client.post('/api/control', json={'action':'start'}).status_code == 200
        message = {'user':'小明','text':'你今天怎么又在摸鱼？','client_message_id':str(uuid4())}
        assert client.post('/api/danmaku', json=message).status_code == 202
        ready = until(stage, 'utterance.ready')
        assert ready['data']['text'] and ready['data']['kind'] == 'reply'
        identity = {'instance_id':ready['instance_id'],'epoch':ready['epoch'],'utterance_id':ready['data']['utterance_id']}
        stage.send_json({'v':1,'type':'playback.started','data':identity})
        until(stage, 'state.snapshot', lambda m: m['data']['state']['phase'] == 'playing')
        stage.send_json({'v':1,'type':'playback.ended','data':identity})
        until(stage, 'state.snapshot', lambda m: m['data']['state']['counters']['completed'] == 1)
        assert client.post('/api/danmaku', json=message).json()['duplicate']
        assert client.post('/api/control', json={'action':'pause'}).json()['mode'] == 'paused'


def test_A20_local_boundary_and_protected_files(client, root):
    (root / '.env').write_text('LLM_API_KEY=DO_NOT_LEAK')
    (root / 'knowledge').mkdir()
    (root / 'knowledge/catalog.json').write_text('DO_NOT_LEAK')
    (root / 'knowledge/sources.json').write_text('DO_NOT_LEAK')
    for path in ('/.env','/static/../.env','/static/%2e%2e/.env','/static/%252e%252e/.env',
                 '/static/audio/not-finalized.mp3.tmp','/audio/invalid.mp3','/models/../../.env',
                 '/knowledge/catalog.json','/knowledge/sources.json','/knowledge_base.py'):
        response = client.get(path)
        assert response.status_code in (403,404), (path,response.status_code)
        assert 'DO_NOT_LEAK' not in response.text
    assert client.post('/api/control',json={'action':'start'},headers={'origin':'https://evil.example'}).status_code == 403
    assert client.get('/api/state',headers={'host':'evil.example'}).status_code == 403
    assert client.post('/api/control',json={'action':'start'},headers=ORIGIN).status_code == 200
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws', headers={'origin':'https://evil.example'}):
            pass


def test_A19_audio_resources_expiry_symlinks_and_cleanup(client, root):
    audio = client.app.state.agent.audio
    identity = str(uuid4())
    audio.path(identity).write_bytes(b'fake audio')
    assert client.get(f'/audio/{identity}.mp3').status_code == 200
    os.utime(audio.path(identity), (0,0))
    assert client.get(f'/audio/{identity}.mp3').status_code == 404
    target = root / '.env'
    target.write_text('SECRET')
    linked = str(uuid4())
    audio.path(linked).symlink_to(target)
    assert client.get(f'/audio/{linked}.mp3').status_code == 404
    store = AudioStore(root / 'bounded-audio', replace(Limits(), audio_count=2, audio_age=100), wall_clock=lambda:200)
    identities = [str(uuid4()) for _ in range(5)]
    for identity, modified in zip(identities, [0,50,150,180,190]):
        path = store.path(identity)
        path.write_bytes(b'a')
        os.utime(path,(modified,modified))
    temporary = store.path(str(uuid4())).with_suffix('.mp3.tmp')
    temporary.write_bytes(b'partial')
    store.cleanup(active_id=identities[0],startup=True)
    assert not temporary.exists()
    assert {p.stem for p in store.directory.glob('*.mp3')} == {identities[0],*identities[-2:]}


@pytest.mark.parametrize('environment', [
    {'LLM_MODE':'openai'}, {'QUEUE_CAPACITY':'0'}, {'TTS_MODE':'wrong'},
    {'LIVE2D_MODEL_URL':'/models/%2e%2e/.env'}, {'BILI_ROOM_ID':'0'},
    {'LLM_MODLE':'typo'}, {'AI_NAME':'   '},
    {'LLM_MODE':'openai','LLM_API_KEY':'TOP_SECRET','LLM_BASE_URL':'http://remote.example/v1','LLM_MODEL':'test'},
])
def test_A16_invalid_configuration_no_secret_leak(environment):
    with pytest.raises(ConfigurationError) as error:
        load_settings(env_file=None,environ=environment)
    assert 'TOP_SECRET' not in str(error.value)


def test_A16_precedence_unknown_dotenv_and_platform_configuration(root):
    path = root / '.env'
    path.write_text('AI_NAME=文件昵称\nQUEUE_CAPACITY=10\n')
    settings = load_settings(path, {'AI_NAME':'环境昵称','PATH':'system value'})
    assert settings.ai_name == '环境昵称' and settings.queue_capacity == 10
    path.write_text('UNKNOWN_KEY=secret-value')
    with pytest.raises(ConfigurationError,match='UNKNOWN_KEY'):
        load_settings(path,{})
    configured = Settings(llm_mode='openai',llm_api_key='TOP_SECRET',llm_base_url='https://example.com/v1',llm_model='test')
    with TestClient(create_app(settings=configured,root=root),base_url=BASE) as client:
        state=client.get('/api/state').json()
        assert state['llm_mode']=='openai' and state['llm_model']=='test'
        assert state['mode']=='paused' and state['diagnostics']['llm']['attempts']==0
        assert 'TOP_SECRET' not in str(state)
    platform = Settings(bili_mode='open_live',bili_app_id='123',bili_access_key='KEY',bili_access_secret='SECRET',bili_auth_code='CODE')
    # Runtime Open Live lifecycle is verified with controlled HTTP/WS transports
    # in test_bilibili.py; this configuration check must not contact real B站.
    assert platform.bili_mode == 'open_live'



@pytest.mark.parametrize('message,code', [
    ({'v':2,'type':'client.hello','data':{'role':'stage'}},1002),
    ({'v':1,'type':'client.hello','data':{'role':'control'}},1008),
])
def test_websocket_protocol_version_and_role_violation(client,message,code):
    with client.websocket_connect('/ws',headers=ORIGIN) as ws:
        until(ws,'state.snapshot')
        if code == 1008:
            ws.send_json(message)
            until(ws,'state.snapshot')
            ws.send_json({'v':1,'type':'renderer.ready','data':{
                'ready':True,'claim_playback':True,'audio_status':'off','character_mode':'demo'}})
        else:
            ws.send_json(message)
        with pytest.raises(WebSocketDisconnect) as error:
            for _ in range(5):
                ws.receive_json()
        assert error.value.code == code


def test_websocket_size_and_invalid_json(client):
    with client.websocket_connect('/ws',headers=ORIGIN) as ws:
        until(ws,'state.snapshot')
        ws.send_text('not-json')
        assert until(ws,'protocol.error')['data']['code'] == 'invalid_message'
        ws.send_text('x'*16385)
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 1009


def test_A13_blocked_websocket_send_is_bounded(root, monkeypatch):
    from starlette.websockets import WebSocket

    async def blocked_send(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(WebSocket, 'send_json', blocked_send)
    application = create_app(settings=Settings(), root=root, limits=replace(Limits(), send_timeout=.01))
    with TestClient(application, base_url=BASE) as client:
        with client.websocket_connect('/ws',headers=ORIGIN) as ws:
            with pytest.raises(WebSocketDisconnect) as error:
                ws.receive_json()
            assert error.value.code == 1013
        assert client.get('/api/state').json()['playback_owner_id'] is None


def test_isolated_verification_port_keeps_exact_origin_boundary(root):
    with TestClient(create_app(settings=Settings(),root=root,port=8766),base_url='http://127.0.0.1:8766') as client:
        assert client.get('/api/health').status_code==200
        assert client.post('/api/control',json={'action':'start'},headers={'origin':'http://127.0.0.1:8766'}).status_code==200
        assert client.post('/api/control',json={'action':'pause'},headers={'origin':'http://127.0.0.1:8765'}).status_code==403
        assert client.get('/api/state',headers={'host':'127.0.0.1:8765'}).status_code==403
    with pytest.raises(ValueError,match='port'):
        create_app(settings=Settings(),root=root,port=0)
