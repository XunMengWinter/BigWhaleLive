"""Validate reviewed references and exercise retrieval without an LLM or network."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from knowledge_base import KnowledgeBase


def main():
    parser = argparse.ArgumentParser(description='本地知识库校验与检索；不联网、不调用AI或TTS。')
    parser.add_argument('--query', help='查看该问题检索到的公开条目')
    parser.add_argument('--evaluate', action='store_true', help='运行固定检索验收题')
    args = parser.parse_args()
    base = KnowledgeBase(ROOT / 'knowledge')
    result = base.snapshot()
    if args.query:
        result['matches'] = [{'id': entry.id, 'title': entry.title,
                              'source_urls': [base.sources[s].url for s in entry.source_ids
                                              if base.sources[s].url]}
                             for entry in base.search(args.query)]
    failed = []
    if args.evaluate and base.status == 'ready':
        cases = json.loads((ROOT / 'knowledge/evaluation.json').read_text())['cases']
        for case in cases:
            found = {entry.id for entry in base.search(case['query'])}
            if (case.get('expected_any') and not found.intersection(case['expected_any'])) or (
                    case.get('expect_empty') and found):
                failed.append(case['id'])
        result['evaluation'] = {'total': len(cases), 'passed': len(cases) - len(failed), 'failed': failed}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if base.status == 'ready' and not failed else 2


if __name__ == '__main__':
    raise SystemExit(main())
