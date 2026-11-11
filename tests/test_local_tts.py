import asyncio
import base64
import json
import shutil
import sys
from dataclasses import replace

import pytest

from config import ConfigurationError, Limits, ROOT, Settings
from contracts import ProviderError
from providers.local_tts import LocalQwenTTS
from providers.tts import AudioStore


async def test_local_mode_reports_fixed_identity_without_private_paths(make_agent):
    agent = make_agent(settings=Settings(tts_mode='qwen_local',
                                        tts_local_model='/private/model',
                                        tts_local_python='/private/python'), tts=object())
    state = agent.state()
    assert state['tts_mode'] == 'qwen_local' and state['tts_voice'] == 'xiaojing-v1'
    assert state['tts_rate'] == state['tts_pitch'] == ''
    assert '/private/' not in json.dumps(state)


def local_provider(root, script, *, limits=None):
    shutil.copytree(ROOT / 'assets/voices', root / 'assets/voices')
    model = root / 'test-model'
    model.mkdir()
    (model / 'config.json').write_text('{}')
    processes = []

    async def spawn(*args, **kwargs):
        assert args[0] == sys.executable
        assert kwargs['env']['HF_HUB_OFFLINE'] == '1'
        assert not any(key.startswith(('LLM_', 'BILI_')) for key in kwargs['env'])
        # Real subprocess, controlled implementation: verifies pipe reuse and
        # process cancellation without a GPU, model weights or external network.
        process = await asyncio.create_subprocess_exec(sys.executable, '-u', '-c', script, **kwargs)
        processes.append(process)
        return process

    settings = Settings(tts_mode='qwen_local', tts_local_python=sys.executable, tts_local_model=str(model))
    return LocalQwenTTS(settings, root, limits or Limits(), process_factory=spawn), processes


async def test_fixed_voice_reuses_worker_and_closes_on_shutdown(root, monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'must-not-reach-worker')
    script = '''import sys,json,base64
for line in sys.stdin:
    text=json.loads(line)['text']
    print(json.dumps({'type':'audio','data':base64.b64encode(text.encode()).decode()}),flush=True)
    print('{"type":"done"}',flush=True)
'''
    provider, processes = local_provider(root, script)
    try:
        for text in ['吃饭啦', '欢迎回来']:
            assert b''.join([chunk async for chunk in provider.stream(text)]) == text.encode()
        assert len(processes) == 1 and processes[0].returncode is None
        assert provider.stats.successes == 2
    finally:
        await provider.aclose()
    assert processes[0].returncode is not None


async def test_cancel_kills_gpu_worker_discards_partial_and_allows_next_call(root):
    script = '''import sys,json,base64,time
for line in sys.stdin:
    text=json.loads(line)['text']
    print(json.dumps({'type':'audio','data':base64.b64encode(b'x'*9000).decode()}),flush=True)
    if text=='block': time.sleep(60)
    print('{"type":"done"}',flush=True)
'''
    provider, processes = local_provider(root, script)
    store = AudioStore(root / 'audio-test', Limits())
    from uuid import uuid4
    identity = str(uuid4())
    task = asyncio.create_task(store.write(identity, provider.stream('block')))
    try:
        async with asyncio.timeout(3):
            while not list(store.directory.glob('*.tmp')) or not next(store.directory.glob('*.tmp')).stat().st_size:
                await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert processes[0].returncode is not None
        assert not list(store.directory.iterdir())
        assert provider.stats.cancelled == 1
        assert len(b''.join([chunk async for chunk in provider.stream('next')])) == 9000
        assert len(processes) == 2 and provider.stats.successes == 1
    finally:
        task.cancel()
        await provider.aclose()


@pytest.mark.parametrize('response', [
    '{"type":"error","detail":"private-test-key"}',
    '{"type":"done"}',
    '{"type":"audio","data":"broken-base64"}',
    json.dumps({'type': 'audio', 'data': base64.b64encode(b'oversized').decode()}),
    'not-json',
])
async def test_protocol_failure_is_bounded_and_redacted(root, response):
    script = f'import sys\nsys.stdin.readline()\nprint({response!r},flush=True)\n'
    provider, processes = local_provider(root, script, limits=replace(Limits(), audio_bytes=3))
    try:
        with pytest.raises(ProviderError, match='^tts_unavailable$'):
            async with asyncio.timeout(3):
                _ = [chunk async for chunk in provider.stream('你好')]
        assert processes[0].returncode is not None and provider.stats.failures == 1
    finally:
        await provider.aclose()


def test_missing_or_modified_approved_voice_fails_before_model_launch(root):
    with pytest.raises(ConfigurationError, match='校验失败'):
        LocalQwenTTS(Settings(tts_mode='qwen_local'), root, Limits())
    shutil.copytree(ROOT / 'assets/voices', root / 'assets/voices')
    (root / 'assets/voices/xiaojing-v1/reference.wav').write_bytes(b'changed')
    with pytest.raises(ConfigurationError, match='校验失败'):
        LocalQwenTTS(Settings(tts_mode='qwen_local'), root, Limits())
