"""Document quality gates (spec §19.5).

Pure functions returning a list of violations (empty = passed). Run on the
preview the n8n document workflow returns, before any publish.
"""

from __future__ import annotations

import re

MIN_BODY_LENGTH = 30

# Conservative sensitive-data patterns (Korean RRN, common card shapes, secrets).
_SENSITIVE_PATTERNS = [
    (re.compile(r"\b\d{6}-\d{7}\b"), "주민등록번호 패턴"),
    (re.compile(r"\b(?:\d[ -]?){13,16}\b"), "카드번호 패턴"),
    (re.compile(r"(?i)(password|secret|api[_-]?key)\s*[:=]\s*\S+"), "비밀정보 패턴"),
]

_NOTION_HOST = re.compile(r"^https://([a-z0-9-]+\.)?notion\.(so|site)(/|$)")


def check_document(
    *,
    title: str | None,
    body: str | None,
    source_row_count: int,
    notion_links: list[str] | None = None,
) -> list[str]:
    problems: list[str] = []
    if not title or not title.strip():
        problems.append("제목이 비어 있습니다.")
    if not body or len(body.strip()) < MIN_BODY_LENGTH:
        problems.append(f"본문이 최소 길이({MIN_BODY_LENGTH}자) 미만입니다.")
    # spec §19.5: Source 데이터 없는 경우 빈 문서 생성 금지.
    if source_row_count <= 0:
        problems.append("Source 데이터가 없어 빈 문서를 생성할 수 없습니다.")
    haystack = f"{title or ''}\n{body or ''}"
    for pattern, label in _SENSITIVE_PATTERNS:
        if pattern.search(haystack):
            problems.append(f"민감정보 감지: {label}")
    for link in notion_links or []:
        if not _NOTION_HOST.match(link):
            problems.append(f"유효하지 않은 Notion 링크: {link}")
    return problems


def duplicate_key(
    *, schedule_id: str, period: str, target_ref: str, template_version: int
) -> str:
    """Idempotency key for duplicate-document prevention (spec §19.4)."""
    return f"doc:{schedule_id}:{period}:{target_ref}:v{template_version}"
