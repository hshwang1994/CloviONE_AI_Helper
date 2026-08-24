"""이관이 **경계를 넓히지 않는가** (S13).

이관은 한 번 쓰고 버리는 도구다. 그런 도구가 런타임의 보안 경계를 넓혀 놓고 사라지면,
넓어진 채로 남는 것은 제품이다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.allowlist import ALLOWLIST_FILES, AllowlistRegistry, URLNotAllowedError

pytestmark = pytest.mark.security

CONFIG = Path(__file__).resolve().parents[2] / "config"
NOTION_FILE_HOST = "https://prod-files-secure.s3.us-west-2.amazonaws.com/x/y.pdf"


def _hosts(name: str) -> set[str]:
    payload = json.loads((CONFIG / ALLOWLIST_FILES[name]).read_text(encoding="utf-8"))
    return set(payload["hosts"])


def test_the_runtime_allowlist_did_not_grow_for_the_migration():
    """첨부를 내려받으려고 **런타임** 목록에 S3 호스트를 넣지 않았다.

    넣었으면 이관이 끝난 뒤에도 앱 서버가 그 호스트로 나갈 수 있다. 이관은 한 번
    쓰고 버리는데 넓어진 경계는 안 사라진다.

    `api.notion.com` 도 이제 여기 없다. 런타임이 노션을 부르던 구현체가 전부 사라졌고,
    호스트만 남겨 두면 되살아난 코드 한 줄이 정본 표에 다시 쓸 수 있다 — Cutover 때
    설정으로 껐는데도 환경 파일이 이겨서 미러가 계속 돌던 사고가 그것이었다.
    """
    runtime = _hosts("services")
    assert runtime == {"api.anthropic.com:443"}, (
        f"런타임 허용 목록이 바뀌었다: {sorted(runtime)}"
    )


def test_the_migration_allowlist_is_a_separate_narrow_list():
    migration = _hosts("migration")
    assert "prod-files-secure.s3.us-west-2.amazonaws.com:443" in migration
    assert "api.notion.com:443" in migration
    # 넓히지 않았는지도 본다 — 「필요할 것 같아서」 늘린 호스트가 없어야 한다.
    assert len(migration) == 2, f"이관 목록이 두 곳보다 많다: {sorted(migration)}"


def test_a_host_outside_the_migration_list_is_refused():
    """**반례** — 목록에 없는 주소는 이관 관문으로도 못 나간다.

    실측에 SharePoint 링크가 하나 있었다(`goodmorningit.sharepoint.com`). 자격증명이
    없어 어차피 못 받지만, **막히는 자리가 어디인지**가 중요하다 — 허용 목록이지
    HTTP 응답이 아니다.
    """
    registry = AllowlistRegistry(CONFIG)
    allowlist = registry.get("migration")
    allowlist.check(NOTION_FILE_HOST)
    with pytest.raises(URLNotAllowedError):
        allowlist.check("https://goodmorningit.sharepoint.com/:x:/s/whatever")
    with pytest.raises(URLNotAllowedError):
        allowlist.check("http://169.254.169.254/latest/meta-data/")


def test_the_report_never_carries_a_token():
    """보고서는 원장에 저장되고 사람이 돌려 본다. **토큰 이름도 값도 안 실린다.**"""
    from app.migration.report import MigrationReport

    report = MigrationReport()
    report.mode = "dry-run"
    report.target_database = "10.100.64.71:55432/clovir_s13"
    report.notion = {"api_calls": 12, "pages_fetched": 3}
    report.check("표본", True, 1, 1)
    text = report.to_text() + report.to_json()
    for forbidden in ("secret_ref", "Authorization", "Bearer", "ntn_", "secret_"):
        assert forbidden not in text, f"보고서에 {forbidden} 가 실렸다"


def test_the_database_label_drops_the_password():
    """대상 주소를 적을 때 자격증명이 따라가지 않는다."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.migration.runner import database_label

    engine = create_engine("postgresql+psycopg://someone:hunter2@db.example:5432/clovir")
    try:
        label = database_label(Session(bind=engine))
    finally:
        engine.dispose()
    assert label == "db.example:5432/clovir"
    assert "hunter2" not in label
