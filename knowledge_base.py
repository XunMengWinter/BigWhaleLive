"""Reviewed local reference material, with bounded lexical retrieval and reload.

The live corpus is a fictional meme library: every entry is marked ``fictional``
and backed by a ``fiction`` source, so retrieval can feed jokes without ever
presenting them to the model as facts.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_CONTEXT_CHARS = 6000
STOP = frozenset(('什么', '怎么', '哪些', '一下', '这个', '那个', '知道', '可以', '介绍', '我们', '你们', '还有', '有没有',
                  '今天', '天天', '给我', '现在', '时候', '真的', '还是', '然后', '就是'))


def normalized(text: str) -> str:
    return unicodedata.normalize('NFKC', text).casefold()


def terms(text: str) -> list[str]:
    result = re.findall(r'[a-z][a-z0-9_.+-]*', normalized(text))
    for phrase in re.findall(r'[\u3400-\u9fff]+', normalized(text)):
        result.extend(phrase[i:i + 2] for i in range(len(phrase) - 1)
                      if phrase[i:i + 2] not in STOP)
    return result


class Source(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,79}$')
    title: str = Field(min_length=1, max_length=200)
    kind: Literal['web', 'local', 'fiction']
    url: str | None = Field(default=None, max_length=500)
    path: str | None = Field(default=None, max_length=500)
    checked_at: date
    sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')

    @field_validator('url')
    @classmethod
    def public_url(cls, value):
        if value is not None:
            parts = urlsplit(value)
            if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
                raise ValueError('来源必须是公开HTTPS地址')
        return value

    @model_validator(mode='after')
    def has_location(self):
        if self.kind == 'web':
            if not self.url:
                raise ValueError('来源缺少位置')
            if not self.sha256:
                raise ValueError('来源缺少哈希')
        elif self.kind == 'local':
            if not self.path or not self.sha256:
                raise ValueError('本地来源缺少位置或哈希')
        elif self.url or self.path:
            raise ValueError('虚构来源不能带位置')
        return self


class Entry(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,79}$')
    title: str = Field(min_length=1, max_length=160)
    category: Literal['character', 'lore', 'scene', 'roast', 'quote', 'interaction', 'boundary']
    tags: list[str] = Field(max_length=32)
    content: str = Field(min_length=1, max_length=3000)
    source_ids: list[str] = Field(min_length=1, max_length=8)
    reviewed_at: date
    valid_until: date | None = None
    fictional: bool = False

    @field_validator('tags')
    @classmethod
    def bounded_tags(cls, values):
        if any(not value.strip() or len(value) > 80 for value in values):
            raise ValueError('标签超出范围')
        return values


class SourceFile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal[1]
    sources: list[Source] = Field(min_length=1, max_length=128)


class CatalogFile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal[1]
    entries: list[Entry] = Field(min_length=1, max_length=256)


class KnowledgeBase:
    def __init__(self, directory: Path, *, today=None):
        self.directory = directory
        self.today = today or (lambda: datetime.now(ZoneInfo('Asia/Shanghai')).date())
        self.entries: tuple[Entry, ...] = ()
        self.sources: dict[str, Source] = {}
        self._index = []
        self._df = Counter()
        self._signature = None
        self._revision = None
        self.status = 'unavailable'
        self.error_code = 'knowledge_missing'
        self.last_retrieved_ids: list[str] = []
        self.refresh()

    def refresh(self):
        """Only swap a complete validated pair; keep the last good copy on error."""
        paths = [self.directory / name for name in ('sources.json', 'catalog.json')]
        try:
            stats = [path.stat() for path in paths]
            signature = tuple((stat.st_mtime_ns, stat.st_size) for stat in stats)
            if signature == self._signature and self.status == 'ready':
                return
            if any(stat.st_size > MAX_FILE_BYTES for stat in stats):
                raise ValueError('oversized knowledge')
            raw = [path.read_bytes() for path in paths]
            if any(len(value) > MAX_FILE_BYTES for value in raw):
                raise ValueError('oversized knowledge')
            sources = SourceFile.model_validate_json(raw[0]).sources
            entries = CatalogFile.model_validate_json(raw[1]).entries
            source_map = {source.id: source for source in sources}
            if len(source_map) != len(sources) or len({entry.id for entry in entries}) != len(entries):
                raise ValueError('duplicate identity')
            if any(source_id not in source_map for entry in entries for source_id in entry.source_ids):
                raise ValueError('unknown source')
            if any(not any(source_map[s].url for s in entry.source_ids)
                   for entry in entries if not entry.fictional):
                raise ValueError('public evidence required')
            if any(entry.fictional and not any(source_map[s].kind == 'fiction'
                                               for s in entry.source_ids) for entry in entries):
                raise ValueError('fiction source required')
            index, df = [], Counter()
            for entry in entries:
                counts = Counter(terms(entry.content))
                counts.update(terms(entry.title) * 3)
                counts.update(terms(' '.join(entry.tags)) * 3)
                df.update(counts.keys())
                index.append((entry, counts, sum(counts.values())))
            # File replacements during validation must be retried as a pair.
            if signature != tuple((p.stat().st_mtime_ns, p.stat().st_size) for p in paths):
                raise ValueError('knowledge changed during load')
            self.entries, self.sources = tuple(entries), source_map
            self._index, self._df = index, df
            self._signature = signature
            self._revision = hashlib.sha256(b'\0'.join(raw)).hexdigest()[:16]
            self.status, self.error_code = 'ready', None
        except (OSError, ValueError, TypeError):
            self.status = 'stale' if self.entries else 'unavailable'
            self.error_code = 'knowledge_missing' if not all(p.exists() for p in paths) else 'knowledge_invalid'

    def _current(self, entry):
        # If an edited bundle is invalid, avoid dated commercial claims even
        # when an older, otherwise valid bundle is still available.
        return entry.valid_until is None or (self.status == 'ready' and self.today() <= entry.valid_until)

    def search(self, query: str, *, limit=4) -> list[Entry]:
        self.refresh()
        query = query[:1200]
        query_terms = set(terms(query))
        if not query_terms:
            return []
        average = max(1, sum(row[2] for row in self._index) / max(1, len(self._index)))
        scored = []
        query_normalized = normalized(query)
        for entry, counts, length in self._index:
            if not self._current(entry):
                continue
            score = 0.0
            for term in query_terms & counts.keys():
                idf = math.log(1 + (len(self.entries) - self._df[term] + .5) / (self._df[term] + .5))
                frequency = counts[term]
                score += idf * frequency * 2.2 / (frequency + 1.2 * (.25 + .75 * length / average))
            for tag in [entry.title, *entry.tags]:
                tag = normalized(tag)
                if len(tag) >= 2 and tag in query_normalized:
                    score += 5
            if score >= 3:
                scored.append((score, entry.id, entry))
        scored.sort(key=lambda row: (-row[0], row[1]))
        return [row[2] for row in scored[:max(0, min(6, limit))]]

    def context(self, query: str) -> dict:
        hits = self.search(query)
        chosen, seen = [], set()
        for entry in hits:
            if entry.id in seen:
                continue
            item = {'id': entry.id, 'title': entry.title, 'category': entry.category,
                    'content': entry.content, 'reviewed_at': entry.reviewed_at.isoformat()}
            if entry.fictional:
                item['note'] = '网友二创虚构梗，仅作玩笑素材，不是事实'
            sources = [{'title': self.sources[s].title, 'url': self.sources[s].url}
                       for s in entry.source_ids if self.sources[s].url]
            if sources:
                item['sources'] = sources
            if entry.valid_until:
                item['valid_until'] = entry.valid_until.isoformat()
            if len(json.dumps([*chosen, item], ensure_ascii=False)) > MAX_CONTEXT_CHARS:
                continue
            chosen.append(item)
            seen.add(entry.id)
        self.last_retrieved_ids = [item['id'] for item in chosen]
        return {'status': self.status, 'revision': self._revision, 'references': chosen}

    def snapshot(self):
        self.refresh()
        return {'status': self.status, 'revision': self._revision,
                'entry_count': len(self.entries), 'source_count': len(self.sources),
                'error_code': self.error_code, 'last_retrieved_ids': self.last_retrieved_ids.copy()}
