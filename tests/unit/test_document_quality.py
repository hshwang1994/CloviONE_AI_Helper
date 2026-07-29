import pytest

from app.documents.quality import check_document, duplicate_key

pytestmark = pytest.mark.unit


def test_valid_document_passes():
    assert check_document(
        title="주간 보고서",
        body="이번 주 완료된 작업은 다음과 같습니다. " * 3,
        source_row_count=5,
        notion_links=["https://www.notion.so/abc123"],
    ) == []


def test_empty_title_flagged():
    problems = check_document(title="", body="충분히 긴 본문 내용입니다 " * 3, source_row_count=1)
    assert any("제목" in p for p in problems)


def test_short_body_flagged():
    problems = check_document(title="제목", body="짧음", source_row_count=1)
    assert any("본문" in p for p in problems)


def test_no_source_data_blocks_empty_doc():
    problems = check_document(
        title="제목", body="충분히 긴 본문 내용입니다 " * 3, source_row_count=0
    )
    assert any("Source" in p for p in problems)


def test_sensitive_rrn_detected():
    problems = check_document(
        title="보고서",
        body="담당자 주민번호 901231-1234567 입니다 " * 2,
        source_row_count=1,
    )
    assert any("민감정보" in p for p in problems)


def test_secret_pattern_detected():
    problems = check_document(
        title="설정 문서",
        body="api_key=sk-abcdef1234567890 로 연결합니다 " * 2,
        source_row_count=1,
    )
    assert any("민감정보" in p for p in problems)


def test_invalid_notion_link_flagged():
    problems = check_document(
        title="보고서",
        body="본문 내용이 충분히 깁니다 " * 3,
        source_row_count=1,
        notion_links=["https://evil.example.com/steal"],
    )
    assert any("Notion 링크" in p for p in problems)


def test_duplicate_key_is_stable():
    a = duplicate_key(schedule_id="s1", period="2026-W28", target_ref="page1", template_version=2)
    b = duplicate_key(schedule_id="s1", period="2026-W28", target_ref="page1", template_version=2)
    c = duplicate_key(schedule_id="s1", period="2026-W29", target_ref="page1", template_version=2)
    assert a == b
    assert a != c
