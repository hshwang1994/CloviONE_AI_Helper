"""이관이 **경계를 넓히지 않는가** (S13).

이관은 한 번 쓰고 버리는 도구다. 그런 도구가 런타임의 보안 경계를 넓혀 놓고 사라지면,
넓어진 채로 남는 것은 제품이다.

qa-contract-change: 이관 허용 목록의 기본값에서 한 고객사의 Confluence 사이트를 뺐다(D-523). 사이트는 설치처마다 달라
설치본에 운영자가 더하고, 이관 도구는 --site 로 같은 주소를 받는다. 목록을 집합으로 적는 방식과 나머지 세 호스트의 이유는
그대로다.
그 전 변경: 런타임 허용 목록이 Anthropic 하나에서 AI 제공자 세 호스트(api.anthropic.com, api.openai.com,
auth.openai.com)가 됐다(계획 3.14, 3.16). OpenAI 는 API 키와 ChatGPT 계정 연결을 공식으로 지원하고, 계정 연결은 토큰
교환과 갱신에 auth.openai.com 을 쓴다. 이관용 호스트(S3, 노션)는 여전히 이 목록에 없다 - 그것이 이 시험이 지키는 경계다.
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
    assert runtime == {"api.anthropic.com:443", "api.openai.com:443", "auth.openai.com:443"}, (
        f"런타임 허용 목록이 바뀌었다: {sorted(runtime)}"
    )


def test_the_migration_allowlist_is_a_separate_narrow_list():
    """이관 목록에 있는 호스트는 **하나하나 이름이 있어야 한다.**

    수만 세면 「셋으로 늘렸다」를 고치는 가장 쉬운 방법이 숫자를 넷으로 바꾸는 것이 된다.
    집합을 통째로 적으면 호스트를 더하는 사람이 **여기에 이유를 적게** 된다.

    - `api.notion.com` · S3 — Notion 이관(S13). 본문과 속성은 API 에서, 첨부 바이트는
      Notion 이 내주는 임시 S3 주소에서 온다.
    - Confluence 사이트(`<site>.atlassian.net`) — 설치처마다 달라 기본 목록에 없다. 운영자가 설치본에 더한다(D-523).
    - `api.media.atlassian.com` — Confluence 첨부의 **바이트**가 실제로 오는 곳. Confluence 의
      download 주소는 302 로 이 CDN 을 가리킨다. 실측에서 이 호스트가 없어 첨부 1,458개가
      0바이트로 들어왔고, 회차는 초록이었다.

    어느 것도 **런타임 목록에는 없다**(위 시험이 그것을 잰다). 한 번 쓰고 버리는 도구가
    제품의 경계를 넓혀 놓고 사라지면, 넓어진 채로 남는 것은 제품이다.
    """
    migration = _hosts("migration")
    assert migration == {
        "api.notion.com:443",
        "prod-files-secure.s3.us-west-2.amazonaws.com:443",
        "api.media.atlassian.com:443",
    }, f"이관 허용 목록이 바뀌었다: {sorted(migration)}"


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
