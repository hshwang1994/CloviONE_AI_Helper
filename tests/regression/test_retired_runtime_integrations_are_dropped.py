"""걷어낸 런타임의 연동 등록 행만 지우고 **살아 있는 연동은 남긴다** (0017).

이 시험이 못 박는 성질은 셋이고, 셋을 함께 봐야 뜻이 있다.

1. n8n 과 러너 셋의 등록 행이 사라진다. 그 넷은 S11 이 걷어낸 런타임을 가리키고, 그 포트에는
   아무도 안 듣는다. 남겨 두면 워커의 자동 헬스 스윕이 30초마다 `down` 을 다시 적고 관리자
   대시보드가 정상 제품을 **매일 장애로** 그린다.
2. 🔴 **반례 하나**: 이름은 같아도 **주소가 다르면 안 지운다.** 운영자가 우연히 같은 이름으로
   살아 있는 연동을 등록했을 수 있다. 이 단언이 없으면 이름만 보고 지우는 회차도 1번을
   만족하며 통과한다.
3. 🔴 **반례 둘**: 관계 없는 연동은 그대로 남는다. `DELETE FROM integrations` 로 표를 통째로
   비우는 회차는 여기서 빨개진다.

마이그레이션이 실제로 실행하는 문장을 그대로 부른다. 시험이 SQL 을 다시 적으면 회차가
무엇을 지우는지가 아니라 시험이 무엇을 지우는지를 재게 된다(0015 의 같은 시험과 같은 규율).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.regression

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0017_drop_retired_integrations.py"
)


def _migration():
    """alembic 회차 파일은 패키지가 아니라 경로로 읽는다(파일 이름이 식별자가 아니다)."""
    spec = importlib.util.spec_from_file_location("mig_0017_retired_integrations", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: 지우면 안 되는 것 둘. 하나는 **이름이 같은데 주소가 다른** 행이고(운영자가 그 이름을
#: 다시 쓴 경우), 하나는 아무 관계 없는 살아 있는 연동이다.
SURVIVORS = (
    ("n8n", "https://n8n.example.internal"),
    ("사내 메신저", "https://example.invalid/messenger"),
)


def _seed(db):
    from app.integrations.models import Integration

    module = _migration()
    for name, base_url in module.REMOVED_RUNTIME_INTEGRATIONS:
        db.add(Integration(
            name=name, provider_type="http_service", base_url=base_url,
            health_url=base_url + "/healthz", auth_type="none",
            capabilities_json="{}", enabled=True, last_health_status="down",
        ))
    for name, base_url in SURVIVORS:
        db.add(Integration(
            name=name + " (살아 있음)", provider_type="http_service", base_url=base_url,
            auth_type="none", capabilities_json="{}", enabled=True, last_health_status="up",
        ))
    db.flush()
    return module


def _names(db) -> set[str]:
    from app.integrations.models import Integration

    return set(db.execute(select(Integration.name)).scalars().all())


def test_the_retired_runtime_rows_are_gone(db):
    module = _seed(db)
    seeded = {name for name, _ in module.REMOVED_RUNTIME_INTEGRATIONS}
    assert seeded <= _names(db), "심는 것부터 실패했다"

    removed = module.delete_removed_runtime_integrations(db.get_bind())
    db.expire_all()

    assert removed == len(module.REMOVED_RUNTIME_INTEGRATIONS)
    left = _names(db) & seeded
    assert not left, f"걷어낸 런타임을 가리키는데 남아 있는 등록 행: {sorted(left)}"


def test_a_row_that_only_shares_the_name_survives(db):
    """🔴 반례. 이름만 보고 지우는 회차는 여기서 빨개진다."""
    module = _seed(db)
    module.delete_removed_runtime_integrations(db.get_bind())
    db.expire_all()

    left = _names(db)
    for name, _ in SURVIVORS:
        assert name + " (살아 있음)" in left, (
            f"{name} 과 이름만 겹치는 살아 있는 연동이 함께 지워졌다. "
            "운영자가 그 이름을 다시 쓸 수 있고, 그 행은 이 회차의 대상이 아니다"
        )


def test_running_it_twice_lands_in_the_same_place(db):
    """두 번 돌려도 같은 자리다. 되감기가 없으니 재실행이 유일한 안전망이다."""
    module = _seed(db)

    first = module.delete_removed_runtime_integrations(db.get_bind())
    second = module.delete_removed_runtime_integrations(db.get_bind())
    db.expire_all()

    assert first == len(module.REMOVED_RUNTIME_INTEGRATIONS)
    assert second == 0, "두 번째 실행이 뭔가를 더 지웠다"


def test_the_names_are_addresses_this_product_no_longer_uses():
    """지우는 주소가 **지금 제품이 쓰는 주소**면 안 된다.

    이 회차는 이름과 주소가 둘 다 맞을 때만 지운다. 그 주소가 우연히 지금 런타임의 것이면
    그 판정은 안전하지 않다 — 허용 목록에 그 호스트가 없다는 사실로 확인한다.
    """
    import json

    module = _migration()
    allowed = json.loads(
        (Path(__file__).resolve().parents[2] / "config" / "allowed-services.json")
        .read_text(encoding="utf-8")
    )["hosts"]
    for _, base_url in module.REMOVED_RUNTIME_INTEGRATIONS:
        hostport = base_url.split("//", 1)[1]
        assert hostport not in allowed, (
            f"{hostport} 이 런타임 허용 목록에 있다. 이 회차가 살아 있는 대상을 지우려 한다"
        )
