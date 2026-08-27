"""지우는 목록을 **시험이 지킨다** (지시 23).

`scripts/reset_domain_data.py` 의 위험은 SQL 이 아니라 **목록**이다. 표 하나를 빠뜨리면
고아 행이 남고, 하나를 더 넣으면 남의 Domain 이 사라진다. 둘 다 실행하는 순간에는
성공으로 보이므로 사람이 눈으로 못 잡는다.

여기서 보는 것 넷:

  1. 목록이 **모델과 맞는가.** 도메인의 표가 늘거나 줄면 이 시험이 먼저 깨진다 —
     스크립트가 조용히 옛 목록으로 도는 것이 가장 나쁜 결과다.
  2. 삭제 **순서**가 외래키를 거스르지 않는가. 자식이 부모보다 먼저 와야 한다.
  3. 보호 목록의 표가 삭제 목록에 **없는가.**
  4. AI 도우미의 대화 기록(`conversations`·`messages`)이 채팅 도메인에 **안 들어갔는가.**
     지시 17 이 말한 「Chat DB 데이터」는 사내 메신저이고, 그쪽은 다른 도메인이다.
     사용자가 지우라고 한 적 없는 것을 지우는 것은 되돌릴 수 없는 사고다.

문서 도메인은 여기에 축을 하나 더 갖는다 — **부분 삭제**. 검색 색인은 문서와 티켓을 한
표에 담으므로, 그 표를 통째로 비우면 문서를 지우면서 티켓 검색이 함께 사라진다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load():
    """스크립트를 모듈로 읽는다. `scripts/` 는 패키지가 아니라 경로로 연다."""
    path = PROJECT_ROOT / "scripts" / "reset_domain_data.py"
    spec = importlib.util.spec_from_file_location("reset_domain_data", path)
    mod = importlib.util.module_from_spec(spec)
    # `sys.modules` 에 먼저 넣는다. 스크립트가 `from __future__ import annotations` 아래에서
    # `@dataclass` 를 쓰는데, 그때 dataclasses 는 문자열 주석을 풀려고 **자기 모듈을**
    # `sys.modules` 에서 되찾는다 — 없으면 클래스 정의 자체가 죽는다.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _tables(domain: str) -> list[str]:
    return [t.table for t in _load().DOMAINS[domain]]


def test_the_chat_domain_list_matches_the_models():
    """🔴 목록이 모델과 어긋나면 스크립트가 옛 목록으로 돈다.

    새 채팅 표가 생겼는데 여기 안 적히면, 초기화 뒤에도 그 표만 옛 데이터를 들고 남는다 —
    그리고 화면은 「지웠다」고 말한다.
    """
    from app.team_chat import models as chat_models

    declared = set(_tables("chat"))
    actual = {
        getattr(v, "__tablename__")
        for v in vars(chat_models).values()
        if hasattr(v, "__tablename__") and hasattr(v, "__table__")
    }
    assert declared == actual, (
        f"삭제 목록과 모델이 다르다.\n  목록에만: {sorted(declared - actual)}"
        f"\n  모델에만: {sorted(actual - declared)}"
    )


def test_children_come_before_their_parents():
    """자식이 먼저다. 부모를 먼저 지우면 외래키가 거절한다."""
    order = _tables("chat")
    at = order.index
    assert at("chat_message_images") < at("chat_messages")
    assert at("chat_messages") < at("chat_rooms")
    assert at("chat_room_members") < at("chat_rooms")
    assert at("chat_read_cursors") < at("chat_rooms")


def test_no_protected_table_is_ever_in_a_delete_list():
    mod = _load()
    for domain in mod.DOMAINS:
        overlap = set(_tables(domain)) & set(mod.PROTECTED)
        assert not overlap, f"{domain} 목록에 보호 대상이 있다: {sorted(overlap)}"


def test_the_things_the_directive_named_are_all_protected():
    """지시 23 이 이름으로 적은 것들이 보호 목록에 있는가."""
    protected = set(_load().PROTECTED)
    for name in ("users", "organizations", "projects", "tickets", "roles", "user_roles"):
        assert name in protected, f"보호 목록에 {name} 이 없다"


def test_the_assistant_conversation_log_is_not_chat_domain():
    """🔴 AI 도우미의 대화 기록은 사내 메신저가 아니다.

    지시 17 은 「Room List · Room Header · 참여자」가 있는 화면을 말한다. 그 화면의
    데이터는 `chat_*` 다. `conversations`/`messages` 를 여기 끼워 넣으면 사용자가 지우라고
    한 적 없는 것을 지우게 되고, 그것은 되돌릴 수 없다.
    """
    chat = set(_tables("chat"))
    assert "conversations" not in chat
    assert "messages" not in chat
    # 이름으로도 잠근다 — 어느 도메인 목록에 적어도 스크립트가 거절한다.
    assert {"conversations", "messages"} <= set(_load().PROTECTED)


def test_the_witness_tables_are_protected_ones():
    """대조군은 **지우지 않는 표**여야 한다. 대상 표를 대조군으로 두면 늘 통과한다."""
    mod = _load()
    for name in mod.WITNESS:
        assert name in mod.PROTECTED, f"대조군 {name} 이 보호 목록에 없다"
        for domain in mod.DOMAINS:
            assert name not in _tables(domain)


# ── 문서 도메인 (지시 22.3) ──────────────────────────────────────────────────


def test_the_document_domain_covers_everything_that_hangs_off_a_document():
    """🔴 문서를 가리키는 표가 하나라도 빠지면 **고아 행**이 남는다.

    목록을 손으로 적지 않고 모델에서 계산해 대조한다: `documents.id` 를 외래키로 가리키는
    표는 전부 문서에서 파생된 것이고, 문서가 사라지면 뜻을 잃는다. 새 표가 생기는 날
    (댓글 반응·읽음 표시 같은 것) 이 시험이 먼저 깨진다.
    """
    from app.knowledge import models as k

    declared = set(_tables("document"))
    hangs_off = set()
    for value in vars(k).values():
        table = getattr(value, "__table__", None)
        if table is None:
            continue
        for column in table.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name == "documents":
                    hangs_off.add(table.name)
    # `documents` 자신은 자기를 안 가리킨다. 목록에는 있어야 한다.
    hangs_off.discard("documents")
    assert "documents" in declared
    missing = hangs_off - declared
    assert not missing, f"문서를 가리키는데 삭제 목록에 없는 표: {sorted(missing)}"


def test_the_derived_ai_and_search_data_is_in_the_list():
    """문서에서 나온 파생 데이터도 함께 지운다 (지시 22.3 의 「Search/AI Index/Chunk」).

    안 지우면 초기화 뒤에도 검색이 없는 문서를 찾아 주고, 누르면 404 다. 「지웠다」와
    「안 보인다」가 여기서 갈라진다.
    """
    declared = set(_tables("document"))
    for name in ("document_chunks", "ai_index_state", "search_documents"):
        assert name in declared, f"파생 데이터 {name} 이 목록에 없다"


def test_the_search_index_is_narrowed_to_documents():
    """🔴 검색 색인은 **한 표에 넷**이 산다 — 문서만 골라 지운다.

    `search_documents` 를 통째로 비우면 문서를 초기화하면서 티켓·게시판·사용자 검색이
    함께 사라진다. 그 표에는 외래키가 없어서 DB 가 막아 주지도 않고, 워커가 다시 채울
    때까지 검색창은 조용히 빈 결과를 낸다.
    """
    target = next(t for t in _load().DOMAINS["document"] if t.table == "search_documents")
    assert target.where, "검색 색인을 조건 없이 지우고 있다"
    assert "kind" in target.where and "document" in target.where


def test_the_skeleton_and_the_binaries_survive():
    """지시 22.3 이 「지우지 않는다」고 이름으로 적은 것들.

    공간과 폴더는 문서가 아니라 문서가 **사는 자리**다. 비우면 초기화 뒤 「새 문서」가
    고를 공간이 하나도 없어서 문서를 만들 수 없다. `files` 는 첨부의 본체 메타데이터이고
    그 뒤에 실제 바이너리가 있다 — 여기서 지우는 것은 문서와 파일을 잇는 줄뿐이다.
    """
    mod = _load()
    declared = set(_tables("document"))
    for name in ("knowledge_spaces", "folders", "files", "document_cache", "trash_items"):
        assert name not in declared, f"{name} 은 지우지 않기로 한 표다"
        assert name in mod.PROTECTED, f"{name} 이 보호 목록에 없다"
    # 잇는 줄은 지운다 — 그것까지 남기면 없는 문서를 가리키는 첨부가 남는다.
    assert "document_attachments" in declared


def test_document_children_come_before_their_parents():
    """판을 문서보다 먼저 지운다 — 두 표가 서로를 가리킨다.

    `document_versions.document_id → documents` 와 `documents.current_version_id →
    document_versions` 가 둘 다 있다. 판을 먼저 지우면 문서의 그 칸이 NULL 이 되어 한 번에
    풀리고, 반대로 하면 순서에 따라 거절당한다.
    """
    order = _tables("document")
    at = order.index
    assert at("document_versions") < at("documents")
    assert at("document_chunks") < at("document_versions")
    assert at("document_tags") < at("tags")
    assert at("document_tags") < at("documents")
    assert at("document_attachments") < at("documents")


def test_a_partial_target_prints_its_condition():
    """보고서에 조건이 보여야 한다 — 「search_documents 111행」만 적히면 읽는 사람은
    표 전체가 111행이라고 읽는다."""
    mod = _load()
    assert str(mod.Target("t")) == "t"
    assert str(mod.Target("t", where="kind = 'document'")) == "t (kind = 'document')"


# ── 구조 행은 지운 뒤 다시 심는다 ────────────────────────────────────────────


def test_the_global_room_is_reseeded_after_a_chat_reset():
    """🔴 실제로 한 번 밟은 자리다.

    `chat_rooms` 를 비웠더니 「전체 채팅」 방이 함께 사라졌다. 그 행은 사람이 만든 대화가
    아니라 마이그레이션 `0001` 이 심은 **구조**이고, 마이그레이션은 한 번만 돌기 때문에
    저절로 안 돌아온다. 앱은 그 방이 없어도 안 죽어서(`get_global_room` 이 `None` 을 곱게
    다룬다) 기능 하나가 조용히 없어진 채로 남았다.
    """
    seeds = _load().RESEED["chat"]
    assert seeds, "채팅 초기화에 재시드가 없다"
    sql, params = seeds[0]
    assert "chat_rooms" in sql
    assert "ON CONFLICT" in sql, "두 번 돌려도 하나여야 한다"
    assert params["title"] == "전체 채팅"


def test_the_reseeded_room_id_matches_the_migration():
    """id 가 마이그레이션과 달라지면 방이 **둘**이 된다 — 옛 것과 새 것.

    고정 id 를 쓰는 이유가 그것이고, 그 값이 두 곳에 적혀 있으므로 여기서 맞물어 둔다.
    """
    import re

    migration = (PROJECT_ROOT / "alembic" / "versions" / "0001_pg_baseline.py").read_text(
        encoding="utf-8"
    )
    m = re.search(r'_GLOBAL_CHAT_ROOM_ID\s*=\s*"([^"]+)"', migration)
    assert m, "마이그레이션에서 전체 채팅 방 id 를 못 찾았다"
    assert _load().RESEED["chat"][0][1]["id"] == m.group(1)


def test_reseeded_rows_are_not_user_data():
    """재시드는 **구조**만이다. 사람이 쓴 것을 다시 심으면 그건 초기화가 아니다."""
    for domain, seeds in _load().RESEED.items():
        for sql, _params in seeds:
            lowered = sql.lower()
            assert "chat_messages" not in lowered, f"{domain}: 메시지를 다시 심고 있다"
            assert "chat_room_members" not in lowered, f"{domain}: 참여자를 다시 심고 있다"
            assert "document_versions" not in lowered, f"{domain}: 문서 본문을 다시 심고 있다"
