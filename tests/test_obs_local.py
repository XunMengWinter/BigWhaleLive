import json
import configparser

import pytest

from tools.obs_local import prepare


def test_local_capture_profile_is_portrait_without_stream_keys_or_device_capture(tmp_path):
    result = prepare(tmp_path)
    root = tmp_path / 'runtime/obs'
    collection = json.loads((root / 'BigWhaleLocal.json').read_text())
    sources = collection['sources']
    assert [source['id'] for source in sources] == ['browser_source', 'scene']
    browser = sources[0]['settings']
    assert browser['width'] == 1080 and browser['height'] == 1920
    assert browser['url'] == 'http://127.0.0.1:8766/?view=obs&audio=auto'
    assert browser['reroute_audio'] is True and sources[0]['monitoring_type'] == 0
    assert all(value is None for key,value in collection.items() if 'AudioDevice' in key)
    profile = configparser.ConfigParser();profile.read(root / 'basic.ini')
    assert profile.get('Video','OutputCX') == '1080'
    assert profile.get('Video','OutputCY') == '1920'
    assert profile.get('SimpleOutput', 'FilePath') == result['recordings']
    assert profile.get('SimpleOutput', 'RecEncoder') == 'apple_h264'
    # ConfigParser accepts whitespace that libobs does not; catch this before
    # OBS silently creates a default landscape profile alongside our keys.
    assert 'BaseCX=1080\n' in (root / 'basic.ini').read_text()
    assert 'BaseCX =' not in (root / 'basic.ini').read_text()
    assert result['streaming_credentials_copied'] is False
    assert not list(root.glob('service*'))


def test_install_refuses_existing_user_profile_and_preserves_other_scenes(tmp_path):
    obs = tmp_path / 'obs'
    target = obs / 'basic/profiles/BigWhaleLocal';target.mkdir(parents=True)
    (target / 'basic.ini').write_text('user config')
    with pytest.raises(ValueError,match='拒绝覆盖'):
        prepare(tmp_path,obs,install=True)
    assert (target / 'basic.ini').read_text() == 'user config'


def test_owned_local_install_is_repeatable(tmp_path):
    obs = tmp_path / 'obs'
    prepare(tmp_path,obs,install=True)
    prepare(tmp_path,obs,install=True)
    assert (obs / 'basic/profiles/BigWhaleLocal/.bigwhale-studio').exists()
    assert (obs / 'basic/scenes/BigWhaleLocal.json').exists()
