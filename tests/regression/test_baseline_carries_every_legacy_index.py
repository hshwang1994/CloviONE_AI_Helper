"""기준선이 **옛 체인이 만든 인덱스·제약을 하나도 안 빠뜨렸는가** (D-189 · D-221).

## 왜 이 시험이 있는가

D-189 는 `sqlite_where=` 가 PG 에서 조용히 무시되는 경로를 경고했다. S2 가 실제로 옮기면서
**두 번째 경로**를 발견했다 — 그리고 그쪽이 더 넓었다:

> 옛 체인이 만든 인덱스 중 **10개가 모델에 없었다.** 기준선을 모델에서 생성하는 순간
> 그 열이 통째로 사라진다.

빠진 것들의 성격이 이 시험의 존재 이유다:

  * **부분 유니크 셋**(`ux_prompts_published_dedup` · `ux_policies_published_dedup` ·
    `ux_offboarding_runs_open_user`) — 사라지면 「같은 이름의 발행본이 둘」과 「같은 사람의
    열린 오프보딩이 둘」을 아무도 안 막는다. 증상은 **한참 뒤 데이터가 이상해진 것**이다.
  * **뜨거운 질의 인덱스 여섯**(0041 다섯 + `ix_mail_deliveries_created_at`) — 사라져도
    **화면은 멀쩡하다.** 느려질 뿐이고 그 느려짐은 데이터가 쌓인 뒤에야 나타난다.
  * **`ix_jobs_claim`** — 워커 claim 이 순차 스캔이 된다. "큐가 밀린다" 로만 보인다.

셋 다 **오류를 내지 않는다.** 그래서 사람이 알아채는 경로가 없고, 시험이 유일한 방어선이다.

## 이 시험이 헛돌지 않으려면

`alembic/legacy_sqlite/` 를 **문자열 리터럴 전수**로 훑는다. `op.create_index("...")` 만
찾는 좁은 정규식으로는 0041 처럼 목록 변수를 도는 형태를 놓친다 — 실제로 처음 만든 검사가
그렇게 놓쳐서 다섯 개를 못 봤다(그 뒤 시험이 빨간불로 잡았다). 과하게 잡는 편이 안전하다:
잘못 잡으면 `KNOWN_RETIRED` 에 이유를 적으면 되고, 못 잡으면 조용히 사라진다.
"""

from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.regression

REPO = pathlib.Path(__file__).resolve().parents[2]
LEGACY = REPO / "alembic" / "legacy_sqlite"

# 인덱스·제약처럼 보이는 이름. 저장소 관례가 `ix_`/`uq_`/`ux_` 셋뿐이다.
_NAME = re.compile(r"""['"]((?:ix|uq|ux)_[a-z0-9_]+)['"]""")
_DROP = re.compile(r"""(?:op|batch_op|batch)\.drop_(?:index|constraint)\(\s*['"]([^'"]+)['"]""")
_DROP_VAR = re.compile(r"""drop_(?:index|constraint)\(\s*(\w+)\s*[,)]""")

# 체인 안에서 만들어졌다가 **같은 체인이 다시 지운** 이름. 이유를 적는다 — 적지 않으면
# 다음 사람이 "왜 빠졌지" 를 다시 조사한다.
KNOWN_RETIRED = {
    # 0054 가 대화 범위 복합 유니크(`uq_messages_conversation_message_id`)로 좁혔다.
    # 전역 유니크였을 때는 "이 문자열이 어딘가에 있는가" 를 아무나 물어볼 수 있는
    # 오라클이었다(UB-23).
    "uq_messages_message_id",
}


def _legacy_names() -> dict[str, str]:
    """옛 체인이 만들고 **안 지운** 이름 → 그 이름이 처음 나온 파일."""
    created: dict[str, str] = {}
    dropped: set[str] = set()
    for f in sorted(LEGACY.glob("*.py")):
        src = f.read_text(encoding="utf-8")
        for m in _NAME.finditer(src):
            created.setdefault(m.group(1), f.name)
        for m in _DROP.finditer(src):
            dropped.add(m.group(1))
        # 변수로 지우는 형태(`batch.drop_index(_OLD_UNIQUE_NAME)`)
        for var in _DROP_VAR.findall(src):
            m2 = re.search(rf"^{var}\s*=\s*['\"]([^'\"]+)['\"]", src, re.MULTILINE)
            if m2:
                dropped.add(m2.group(1))
    return {k: v for k, v in created.items() if k not in dropped}


def _model_names() -> set[str]:
    """모델 메타데이터가 만들어 낼 이름 전부."""
    import app.models_registry  # noqa: F401 — Base.metadata 를 채운다
    from app.core.models_base import Base

    names: set[str] = set()
    for t in Base.metadata.tables.values():
        names |= {ix.name for ix in t.indexes}
        names |= {c.name for c in t.constraints if c.name}
        # `unique=True` / `index=True` 컬럼은 SQLAlchemy 가 이름을 자동으로 짓는다 —
        # 옛 체인이 쓰던 이름과 같은 규칙이라 그 형태도 후보로 본다.
        for c in t.columns:
            if c.unique:
                names |= {f"uq_{t.name}_{c.name}", f"ix_{t.name}_{c.name}"}
            if c.index:
                names.add(f"ix_{t.name}_{c.name}")
    return names


def test_the_detector_actually_finds_things():
    """이 시험이 **빈 목록을 훑고 초록을 찍는** 상태가 아님을 먼저 보인다.

    D-213 이 정한 규약이다: 빈 결과는 통과가 아니라 FATAL 이다. 옛 체인이 61 revision 인데
    이름을 하나도 못 찾았다면 정규식이나 경로가 틀린 것이지 "빠진 게 없는" 것이 아니다.
    """
    names = _legacy_names()
    assert len(names) >= 60, f"옛 체인에서 이름을 {len(names)}개밖에 못 찾았다 — 검사가 헛돈다"


def test_no_legacy_index_was_silently_dropped():
    """옛 체인이 만든 것 중 모델에 없는 것이 있으면 **기준선에서 사라진다.**"""
    legacy = _legacy_names()
    models = _model_names()
    missing = {
        name: origin
        for name, origin in sorted(legacy.items())
        if name not in models and name not in KNOWN_RETIRED
    }
    assert not missing, (
        "옛 체인이 만든 인덱스·제약이 모델에 없다 — 기준선을 모델에서 만들면 그대로 "
        "사라지고, 셋 다 오류를 내지 않아 아무도 못 알아챈다:\n  "
        + "\n  ".join(f"{n}  ({o})" for n, o in missing.items())
    )


def test_the_indexes_s2_had_to_rescue_are_present():
    """S2 가 실제로 놓칠 뻔한 열 개를 이름으로 못박는다.

    위 시험이 일반 규칙이고 이것은 **회귀 고정**이다 — 누가 정규식을 느슨하게 만들어도
    이 열 개만은 이름으로 걸린다.
    """
    models = _model_names()
    rescued = [
        "ux_prompts_published_dedup",
        "ux_policies_published_dedup",
        "ux_offboarding_runs_open_user",
        "ix_jobs_claim",
        "ix_notifications_user_unread",
        "ix_board_posts_created_at",
        "ix_conversations_updated_at",
        "ix_schedule_runs_created_at",
        "ix_audit_logs_object_id",
        "ix_mail_deliveries_created_at",
    ]
    missing = [n for n in rescued if n not in models]
    assert not missing, f"S2 가 되살린 인덱스가 다시 빠졌다: {missing}"
