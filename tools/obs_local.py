"""Prepare a credential-free OBS profile, or serve an isolated capture backend."""
from __future__ import annotations

import argparse
import configparser
import json
from pathlib import Path
import shutil
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PROFILE = 'BigWhaleLocal'
SCENE = '大肥鱼·本地采集'
SOURCE = '大肥鱼·竖屏与声音'
CANVAS = '6c69626f-6273-4c00-9d88-c5136d61696e'


def scene_collection(port):
    browser, scene = str(uuid4()), str(uuid4())
    return {
        'name': PROFILE, 'current_scene': SCENE, 'current_program_scene': SCENE,
        'scene_order': [{'name': SCENE}], 'groups': [], 'canvases': [],
        'resolution': {'x': 1080, 'y': 1920}, 'migration_resolution': {'x': 1080, 'y': 1920},
        'version': 2, 'current_transition': '淡入淡出', 'transition_duration': 300,
        'transitions': [], 'quick_transitions': [], 'saved_projectors': [],
        'DesktopAudioDevice1': None, 'DesktopAudioDevice2': None,
        **{f'AuxAudioDevice{i}': None for i in range(1, 5)},
        'sources': [
            {'name': SOURCE, 'uuid': browser, 'id': 'browser_source', 'versioned_id': 'browser_source',
             'settings': {'url': f'http://127.0.0.1:{port}/?view=obs&audio=auto',
                          'width': 1080, 'height': 1920, 'fps': 30, 'fps_custom': True,
                          'reroute_audio': True, 'shutdown': False, 'restart_when_active': False,
                          'webpage_control_level': 0, 'css': 'body {margin:0;overflow:hidden;}'},
             'volume': 1.0, 'muted': False, 'mixers': 1, 'sync': 0, 'monitoring_type': 0,
             'enabled': True, 'hotkeys': {}, 'private_settings': {}},
            {'name': SCENE, 'uuid': scene, 'id': 'scene', 'versioned_id': 'scene',
             'canvas_uuid': CANVAS, 'settings': {'id_counter': 1, 'custom_size': False, 'items': [
                 {'name': SOURCE, 'source_uuid': browser, 'visible': True, 'locked': True,
                  'id': 1, 'rot': 0.0, 'align': 5, 'bounds_type': 0,
                  'pos': {'x': 0.0, 'y': 0.0}, 'pos_rel': {'x': -.5625, 'y': -1.0},
                  'scale': {'x': 1.0, 'y': 1.0}, 'scale_rel': {'x': 1.0, 'y': 1.0},
                  'scale_ref': {'x': 1080.0, 'y': 1920.0},
                  'bounds': {'x': 0.0, 'y': 0.0}, 'bounds_rel': {'x': 0.0, 'y': 0.0},
                  'crop_left': 0, 'crop_top': 0, 'crop_right': 0, 'crop_bottom': 0,
                  'private_settings': {}}]}, 'volume': 1.0, 'muted': False, 'mixers': 1,
             'hotkeys': {}, 'private_settings': {}},
        ]}


def prepare(root=ROOT, obs_root=None, *, port=8766, install=False):
    if not 1 <= port <= 65535:
        raise ValueError('Invalid port')
    destination = root / 'runtime/obs'
    destination.mkdir(parents=True, exist_ok=True)
    recording = root / 'artifacts/obs-recordings'
    recording.mkdir(parents=True, exist_ok=True)
    profile = configparser.ConfigParser(interpolation=None)
    profile.optionxform = str
    profile.read_dict({
        'General': {'Name': PROFILE}, 'Output': {'Mode': 'Simple'},
        'Video': {'BaseCX': '1080', 'BaseCY': '1920', 'OutputCX': '1080', 'OutputCY': '1920',
                  'FPSType': '0', 'FPSCommon': '30', 'ScaleType': 'bicubic',
                  'ColorFormat': 'NV12', 'ColorSpace': '709', 'ColorRange': 'Partial'},
        'Audio': {'SampleRate': '48000', 'ChannelSetup': 'Stereo'},
        'SimpleOutput': {'FilePath': str(recording), 'RecFormat2': 'mkv', 'RecQuality': 'HQ',
                         'RecEncoder': 'apple_h264', 'ABitrate': '160',
                         'FileNameWithoutSpace': 'true'},
        'Hotkeys': {'OBSBasic.StopRecording': json.dumps({'bindings': [
            {'control': True, 'alt': True, 'shift': True, 'key': 'OBS_KEY_F10'}]})},
    })
    ini, collection = destination / 'basic.ini', destination / f'{PROFILE}.json'
    with ini.open('w') as output:
        # libobs treats spaces before '=' as part of the key.
        profile.write(output, space_around_delimiters=False)
    collection.write_text(json.dumps(scene_collection(port), ensure_ascii=False, indent=2))
    for path in (ini, collection):
        path.chmod(0o600)
    if install:
        obs_root = obs_root or Path.home() / 'Library/Application Support/obs-studio'
        target = obs_root / 'basic/profiles' / PROFILE
        scene_target = obs_root / 'basic/scenes' / f'{PROFILE}.json'
        # Keep the existing ownership marker compatible with installed profiles.
        marker = target / '.bigwhale-studio'
        if (target.exists() or scene_target.exists()) and not marker.exists():
            raise ValueError('同名OBS配置已存在，拒绝覆盖用户配置')
        target.mkdir(parents=True, exist_ok=True)
        scene_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ini, target / 'basic.ini')
        shutil.copy2(collection, scene_target)
        marker.write_text('BigWhaleLive local capture only\n')
    return {'profile': PROFILE, 'collection': PROFILE, 'scene': SCENE, 'port': port,
            'width': 1080, 'height': 1920, 'recordings': str(recording),
            'installed': install, 'streaming_credentials_copied': False}


def serve(port, with_danmaku=False):
    import uvicorn
    from agent import Agent
    from config import Limits, load_settings
    from main import create_app
    from providers.tts import AudioStore
    if port == 8765:
        raise ValueError('本地采集验证请使用独立端口，保留8765主服务')
    settings = load_settings()
    if not with_danmaku:
        settings = settings.model_copy(update={'bili_mode': 'off'})
    class CaptureAgent(Agent):
        def __init__(self, settings, root, *, limits=None):
            limits = limits or Limits()
            super().__init__(settings, root, limits=limits,
                             audio=AudioStore(ROOT / 'runtime/obs/audio', limits))
    app = create_app(settings=settings, port=port, agent_factory=CaptureAgent)
    uvicorn.run(app, host='127.0.0.1', port=port, workers=1, access_log=False)


def main():
    parser = argparse.ArgumentParser(description='OBS独立本地采集，不复制推流凭据、不自动开播。')
    parser.add_argument('action', choices=['prepare', 'serve'])
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--install', action='store_true', help='安装独立OBS配置，不改已有集合')
    parser.add_argument('--with-danmaku', action='store_true', help='采集验证服务也读取配置中的弹幕；默认只用模拟输入')
    args = parser.parse_args()
    if args.action == 'prepare':
        print(json.dumps(prepare(port=args.port, install=args.install), ensure_ascii=False))
    else:
        serve(args.port, args.with_danmaku)


if __name__ == '__main__':
    main()
