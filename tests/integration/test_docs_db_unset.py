"""문서 DB id 미설정을 **부르기 전에** 말한다 (P1).

고객사 고유값을 소스 기본값에서 비운 뒤로, 문서 DB id 가 빈 상태는 **설치 직후의 정상
상태**가 됐다. 그대로 부르면 URL 이 `/v1/databases//query` 가 되고 Notion 이 400 을 준다.
화면은 그걸 "조회 실패" 로 그려서, 운영자는 네트워크나 토큰을 의심하며 시간을 버린다.
"설정 안 함" 과 "조회 실패" 는 다른 사실이다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_an_unset_documents_database_says_not_configured(client, settings, monkeypatch):
    from app.team_docs import notion_docs

    (settings.secrets_dir / "notion_docs_token").write_text("t", encoding="utf-8")
    monkeypatch.setattr(settings, "notion_documents_database_id", "")

    with pytest.raises(notion_docs.NotionDocsNotConfiguredError) as err:
        notion_docs._request(
            client.app.state.outbound_client, settings, "POST",
            "/v1/databases//query", json={},
        )
    assert "NOTION_DOCUMENTS_DATABASE_ID" in str(err.value), str(err.value)


def test_a_page_read_still_works_without_the_database_id(client, settings, monkeypatch):
    """오탐 방지 - 페이지 단건 조회는 DB id 가 필요 없다. 거기까지 막으면 기능 고장이다."""
    from app.team_docs import notion_docs

    (settings.secrets_dir / "notion_docs_token").write_text("t", encoding="utf-8")
    monkeypatch.setattr(settings, "notion_documents_database_id", "")

    with pytest.raises(Exception) as err:
        notion_docs._request(
            client.app.state.outbound_client, settings, "GET", "/v1/pages/page-1",
        )
    assert not isinstance(err.value, notion_docs.NotionDocsNotConfiguredError), (
        "DB id 와 무관한 경로까지 '설정 안 됨' 으로 막았다"
    )
