from datetime import date
import json
from pathlib import Path
import shutil

import pytest

from config import Limits, Settings
from knowledge_base import KnowledgeBase, MAX_CONTEXT_CHARS, MAX_FILE_BYTES
from providers.llm import ChatCompletionsLLM

ROOT = Path(__file__).resolve().parents[1]


def bundle(directory, *, content='一段已审核资料', expires=None, fictional=False):
    directory.mkdir(exist_ok=True)
    public = {'id': 'public', 'title': '公开资料', 'kind': 'web',
              'url': 'https://example.com/source', 'checked_at': '2026-11-09', 'sha256': 'a' * 64}
    private = {'id': 'local', 'title': '本地来源', 'kind': 'local',
               'path': '/private/DO_NOT_DISCLOSE/.env', 'checked_at': '2026-11-09', 'sha256': 'b' * 64}
    fiction = {'id': 'fiction', 'title': '二创虚构设定', 'kind': 'fiction', 'checked_at': '2026-11-09'}
    entry = {'id': 'test-entry', 'title': '测试资料', 'category': 'lore',
             'tags': ['测试资料'], 'content': content,
             'source_ids': ['fiction'] if fictional else ['public', 'local'],
             'reviewed_at': '2026-11-09'}
    if fictional:
        entry['fictional'] = True
    if expires:
        entry['valid_until'] = expires
    (directory / 'sources.json').write_text(json.dumps(
        {'version': 1, 'sources': [public, private, fiction]}))
    (directory / 'catalog.json').write_text(json.dumps({'version': 1, 'entries': [entry]}))
    return entry


def test_reviewed_corpus_retrieves_known_questions_without_network():
    kb = KnowledgeBase(ROOT / 'knowledge', today=lambda: date(2026, 11, 9))
    assert kb.status == 'ready'
    assert kb.snapshot()['entry_count'] == 103
    assert all(entry.fictional for entry in kb.entries)
    assert {entry.category for entry in kb.entries} <= {
        'character', 'lore', 'scene', 'roast', 'quote', 'interaction', 'boundary'}
    dump = json.dumps([entry.model_dump(mode='json') for entry in kb.entries], ensure_ascii=False)
    assert 'winter' not in dump.casefold()
    assert 'minicode.uk' not in dump
    cases = json.loads((ROOT / 'knowledge/evaluation.json').read_text())['cases']
    for case in cases:
        found = {entry.id for entry in kb.search(case['query'])}
        assert not case.get('expected_any') or found.intersection(case['expected_any']), case['id']
        assert not case.get('expect_empty') or not found, case['id']


def test_context_is_bounded_and_excludes_local_paths(tmp_path):
    entry = bundle(tmp_path, content='测试课程知识' * 200)
    payload = json.loads((tmp_path / 'catalog.json').read_text())
    payload['entries'] = [{**entry, 'id': f'entry-{i}'} for i in range(12)]
    (tmp_path / 'catalog.json').write_text(json.dumps(payload))
    kb = KnowledgeBase(tmp_path)
    context = kb.context('测试资料')
    assert 0 < len(context['references']) <= 4
    assert len(json.dumps(context['references'], ensure_ascii=False)) <= MAX_CONTEXT_CHARS
    assert 'DO_NOT_DISCLOSE' not in json.dumps(context)
    assert 'DO_NOT_DISCLOSE' not in json.dumps(kb.snapshot())
    assert all(source['url'].startswith('https://') for item in context['references'] for source in item['sources'])


def test_fictional_entries_are_labeled_and_carry_no_source_urls(tmp_path):
    bundle(tmp_path, content='二创玩梗素材' * 20, fictional=True)
    kb = KnowledgeBase(tmp_path)
    assert kb.status == 'ready'
    context = kb.context('测试资料')
    assert len(context['references']) == 1
    item = context['references'][0]
    assert item['note'] == '网友二创虚构梗，仅作玩笑素材，不是事实'
    assert 'sources' not in item
    assert 'DO_NOT_DISCLOSE' not in json.dumps(context)


def test_expired_commercial_facts_do_not_enter_model_context(tmp_path):
    bundle(tmp_path, expires='2026-11-09')
    kb = KnowledgeBase(tmp_path, today=lambda: date(2026, 11, 10))
    assert kb.status == 'ready'
    assert kb.context('测试资料')['references'] == []


def test_bad_edit_keeps_last_good_copy_and_recovers_after_fix(tmp_path):
    bundle(tmp_path)
    kb = KnowledgeBase(tmp_path)
    original_revision = kb.snapshot()['revision']
    (tmp_path / 'catalog.json').write_text('broken content with private value')
    assert kb.search('测试资料')[0].content == '一段已审核资料'
    assert kb.snapshot()['status'] == 'stale'
    assert 'private value' not in json.dumps(kb.snapshot())
    bundle(tmp_path, content='新的资料说明')
    assert kb.search('测试资料')[0].content == '新的资料说明'
    assert kb.snapshot()['status'] == 'ready'
    assert kb.snapshot()['revision'] != original_revision


def test_bad_edit_suppresses_dated_facts_from_last_good_copy(tmp_path):
    bundle(tmp_path, expires='2026-12-09')
    kb = KnowledgeBase(tmp_path, today=lambda: date(2026, 11, 9))
    assert kb.search('测试资料')
    (tmp_path / 'sources.json').write_text('{}')
    assert not kb.search('测试资料')
    assert kb.status == 'stale'


@pytest.mark.parametrize('mutation', ['duplicate', 'unknown-source', 'oversized', 'no-public-source',
                                      'fiction-without-fiction-source'])
def test_invalid_bundle_is_unavailable_with_safe_error(tmp_path, mutation):
    bundle(tmp_path, fictional=mutation == 'fiction-without-fiction-source')
    path = tmp_path / 'catalog.json'
    data = json.loads(path.read_text())
    if mutation == 'duplicate':
        data['entries'].append(data['entries'][0])
    elif mutation == 'unknown-source':
        data['entries'][0]['source_ids'] = ['unknown']
    elif mutation == 'no-public-source':
        data['entries'][0]['source_ids'] = ['local']
    elif mutation == 'fiction-without-fiction-source':
        data['entries'][0]['source_ids'] = ['public']
    path.write_text('x' * (MAX_FILE_BYTES + 1) if mutation == 'oversized' else json.dumps(data))
    kb = KnowledgeBase(tmp_path)
    assert kb.snapshot()['error_code'] == 'knowledge_invalid'
    assert kb.context('测试资料')['references'] == []


def test_missing_bundle_can_be_created_without_restarting_process(tmp_path):
    directory = tmp_path / 'knowledge'
    kb = KnowledgeBase(directory)
    assert kb.status == 'unavailable'
    bundle(directory)
    assert kb.search('测试资料')
    assert kb.status == 'ready'


def test_live_model_gets_fictional_meme_references(root):
    shutil.copytree(ROOT / 'knowledge', root / 'knowledge')
    provider = ChatCompletionsLLM(Settings(), root, Limits(), client=object())
    messages = provider.messages({'user': '观众', 'text': 'DeepSeek 和 Claude 有什么恩怨？'}, [])
    request = json.loads(messages[-1]['content'])
    material = request['reference_material']
    assert material['status'] == 'ready'
    assert material['references']
    assert all(item.get('note') == '网友二创虚构梗，仅作玩笑素材，不是事实'
               for item in material['references'])
    assert 'sources' not in json.dumps(material)
    assert '虚构' in messages[0]['content']
    assert '不人身攻击' in messages[0]['content']
    dump = json.dumps(messages, ensure_ascii=False).casefold()
    assert 'winter' not in dump
    assert 'minicode.uk' not in dump


def test_live_model_does_not_force_memes_into_unrelated_chat(root):
    shutil.copytree(ROOT / 'knowledge', root / 'knowledge')
    provider = ChatCompletionsLLM(Settings(), root, Limits(), client=object())
    request = json.loads(provider.messages(
        {'user': '观众', 'text': '今天天气怎么样？'}, [])[-1]['content'])
    assert request['reference_material']['references'] == []
