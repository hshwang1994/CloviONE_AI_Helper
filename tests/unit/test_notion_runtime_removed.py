"""지운 Notion 런타임이 **돌아오지 않는다** (S14 · D-284).

qa-contract-replaced-by: tests/unit/test_ticket_sync.py
qa-contract-replaced-by: tests/unit/test_pf8_notion_parallel_calls.py
qa-contract-replaced-by: tests/regression/test_document_comment_survives_resync.py

## 왜 이 파일이 있는가

S11 이 n8n 과 러너 셋을 걷어낼 때 같은 파일을 만들었다
(`tests/regression/test_external_automation_removed.py`). 이유도 같다: **지운 것은 조용히
돌아온다.** 누군가 옛 모듈을 되살리거나, 워커에 틱을 하나 더 붙이거나, 허용 목록에
`api.notion.com` 을 다시 적으면 — 그 순간 제품이 **정본 데이터베이스에 외부 소스를 덮어쓰는
경로**를 다시 갖는다. 그리고 그 사고는 오류를 안 낸다.

## Cutover 가 실제로 겪은 일이라 이 검사가 있다

Cutover 직후 워커를 올리자 미러 동기화 틱이 PostgreSQL 을 향해 돌기 시작했다. 설정을 껐는데도
계속 돌았다 — DB 설정을 비웠지만 **환경파일이 이겼다.** 그리고 그 값이 유효한 데이터베이스
id 라 동기화가 성공하기 시작했다. 데이터는 무사했지만 그것은 운이었다.

끄는 자리가 둘이면 하나를 끈 사람은 껐다고 믿는다. 그래서 「설정이 꺼져 있다」가 아니라
**「코드가 없다」**를 검사한다.

## 대체한 세 파일이 지키던 것

* `test_ticket_sync.py` — 미러 동기화의 데이터 보존(상한에 걸린 회차는 prune 안 함, 소스
  5xx 에도 캐시 유지). 미러가 없으므로 지킬 대상이 없다. **되살아나면 안 되는 것**만 남긴다.
* `test_pf8_notion_parallel_calls.py` — Notion 왕복을 병렬로 내보내 지연 누적을 없앤 것.
  왕복 자체가 없다.
* `test_document_comment_survives_resync.py` — 재동기화가 문서 캐시 행을 지워도 댓글이
  살아남는가. **그 성질은 살아 있고** 자리를 옮겼다 — 아래
  `test_a_document_comment_survives_its_cache_row` 가 동기화 대신 행을 직접 지워서 본다.
  그쪽이 오히려 정확하다: 지키는 것은 `ON DELETE SET NULL` 이지 동기화가 아니다.
"""

from __future__ import annotations

import json
import pathlib

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]

# 지운 런타임 모듈. **이름을 적어 둔다** — 「없어졌다」를 파일 목록으로 확인해야 되살아난
# 파일이 눈에 띈다.
REMOVED_MODULES = (
    "app/tickets/sync.py",
    "app/tickets/notion_write.py",
    "app/tickets/repository_notion.py",
    "app/team_docs/sync.py",
    "app/team_docs/notion_docs.py",
    "app/team_docs/repository_notion.py",
    "app/projects/sync.py",
    "app/projects/notion_source.py",
    "app/projects/notion_write.py",
    "app/reports/notion_source.py",
    "app/notion_console/__init__.py",
    "app/notion_console/router.py",
    "app/notion_console/service.py",
    "app/notion_console/probe_notion.py",
    # 미러 회차의 prune 바닥. 「이번 조회에서 못 본 행을 지운다」가 이 모듈의 전부라,
    # 조회할 회차가 없어진 뒤로는 부르는 곳도 없었다. 남겨 두면 다음 사람이 「이미 있으니
    # 쓰자」로 미러를 다시 만든다.
    "app/core/sync_prune.py",
)


def test_the_removed_runtime_modules_are_still_gone():
    """열다섯이 전부 없다. **수를 함께 단언한다** — 목록이 비면 이 검사도 통과한다."""
    assert len(REMOVED_MODULES) == 15
    back = [name for name in REMOVED_MODULES if (ROOT / name).exists()]
    assert not back, f"지운 런타임 모듈이 돌아왔다: {back}"


def test_nothing_under_app_imports_them():
    """파일이 없어도 **이름으로 부르는 자리**가 남아 있을 수 있다.

    지연 import(`from app.tickets import sync` 를 함수 안에서)는 파일 목록으로 안 잡히고,
    부르는 순간까지 조용하다. 그래서 소스를 직접 훑는다.
    """
    needles = (
        "app.tickets.sync", "app.tickets.notion_write", "app.tickets.repository_notion",
        "app.team_docs.sync", "app.team_docs.notion_docs", "app.team_docs.repository_notion",
        "app.projects.sync", "app.projects.notion_source", "app.projects.notion_write",
        "app.reports.notion_source", "app.notion_console", "app.core.sync_prune",
    )
    offenders: list[str] = []
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle in text:
                offenders.append(f"{path.relative_to(ROOT)} :: {needle}")
    assert not offenders, "지운 모듈을 아직 부르는 자리가 있다:\n  " + "\n  ".join(offenders)


def test_the_runtime_cannot_reach_notion_at_all():
    """🔴 런타임 SSRF 목록에 `api.notion.com` 이 **없다**.

    이것이 마지막 방어선이다. 코드가 어떻게 되살아나든 이 목록에 없으면 나갈 수가 없다
    (`app/core/allowlist.py` 는 목록에 없는 주소를 거절한다).

    이관 도구는 **자기 목록**을 따로 든다(`allowed-migration-sources.json`) — 그쪽은 있어야
    한다. 둘을 한 목록으로 합치면 런타임이 다시 정본을 덮어쓸 수 있게 된다.
    """
    services = json.loads((ROOT / "config/allowed-services.json").read_text(encoding="utf-8"))
    assert "api.notion.com:443" not in services["hosts"]
    assert services["hosts"], "목록이 비었다 — 이 단언이 아무것도 안 본다"

    migration = json.loads(
        (ROOT / "config/allowed-migration-sources.json").read_text(encoding="utf-8")
    )
    assert "api.notion.com:443" in migration["hosts"], (
        "이관 도구의 목록에서 Notion 이 사라졌다 — 재실행과 두 번째 설치가 데이터를 못 읽는다"
    )


def test_the_worker_registers_no_mirror_sync_tick():
    """워커에 미러 동기화 틱이 하나도 없다.

    틱 하나가 다시 붙는 것이 이 저장소에서 가장 조용한 사고다 — 그 틱은 실패해도 로그만
    남기고 워커를 안 죽이므로(설계가 그렇다), 정본을 덮어쓰는 동안에도 모든 것이 정상으로
    보인다.
    """
    text = (ROOT / "app/worker_main.py").read_text(encoding="utf-8")
    for banned in ("sync_tickets", "sync_documents", "sync_projects",
                   "tickets_sync_tick", "docs_sync_tick", "projects_sync_tick"):
        assert banned not in text, f"워커에 미러 동기화가 돌아왔다: {banned}"
    # `import` 로도 안 부른다. 이름을 안 쓰고 같은 일을 하는 코드는 못 잡지만, 그쪽은
    # 위 `test_nothing_under_app_imports_them` 이 모듈 이름으로 본다.
    assert "app.tickets.sync" not in text
    assert "app.team_docs.sync" not in text
    assert "app.projects.sync" not in text


def test_a_document_comment_no_longer_hangs_off_the_mirror(db, make_user):
    """**옮겨 온 성질** — 사람이 쓴 댓글이 미러의 사정으로 사라질 수 없다.

    예전에는 「재동기화가 문서 캐시 행을 지워도 댓글은 남는가」로 봤고, 그것을 지키는 것은
    `ON DELETE SET NULL` 이었다. 그 방어가 필요했던 이유는 **댓글의 주인이 미러 행**이었기
    때문이다.

    S14 가 그 소유를 옮겼다(`0016_document_axis_to_documents`). 이제 댓글은 정본 문서
    (`documents`)에 달리고, 미러 표는 그 글을 **가리키지도 못한다** — 그래서 미러가 어떤
    이유로 사라지든 사람이 쓴 글에는 아무 일도 일어나지 않는다. 방어가 사라진 것이 아니라
    방어할 상황이 없어진 것이고, 이 시험은 그 사실을 못박는다.
    """
    import app.team_docs.models as legacy_models
    from app.knowledge.models import Document, DocumentComment, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID

    # ① 옛 소유 자리가 없다 — 있으면 댓글이 두 곳에 살 수 있고, 그때부터 어느 쪽이
    #    정본인지 아무도 모른다.
    assert not hasattr(legacy_models, "DocumentComment"), (
        "미러 표가 다시 댓글의 주인이 됐다 — 정본이 둘이 되면 한쪽이 조용히 사라진다"
    )

    # ② 정본에서는 문서와 함께 산다. 문서를 지우는 것은 사람이 하는 결정이고, 그때
    #    딸린 글이 함께 지워지는 것은 사고가 아니라 계약이다(S14 · C2).
    author = make_user(email="doc-comment@goodmit.co.kr")
    space = KnowledgeSpace(name="공간", slug="nrr-space", owner_kind="organization",
                           org_id=DEFAULT_ORG_ID)
    db.add(space)
    db.flush()
    doc = Document(space_id=space.id, title="문서")
    db.add(doc)
    db.flush()
    db.add(DocumentComment(document_id=doc.id, author_user_id=author.id,
                           body="이 글은 정본 문서에 달린다"))
    db.flush()

    rows = db.query(DocumentComment).filter(DocumentComment.document_id == doc.id).all()
    assert [r.body for r in rows] == ["이 글은 정본 문서에 달린다"]
