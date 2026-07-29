"""Notion 매핑 workflow가 실제로 등록돼 있어야 매핑이 동작한다.

사용자 보고: "Notion 매핑인데 노션에서 Notion ID도 들고오지 않고 있음. 매핑시킬 수 없음."

원인은 코드가 아니라 **없는 워크플로**였다. `notion_mapping/service.py`는
`MAPPING_WORKFLOW_NAME = "notion-user-mapping"`으로 Workflow 레지스트리를 뒤지는데
그 이름이 등록된 적이 없었다. 그래서 `get_mapping_workflow()`가 None을 돌려주고,
`verify_mapping`이 조용히 status=UNMAPPED + "Workflow가 구성/활성화되지 않았습니다"로 끝났다.
플랫폼 코드는 완성돼 있었고 n8n 쪽이 비어 있었던 것이다.

이름은 두 모듈이 공유하는 **계약**이다. 한쪽이 바뀌면 매핑이 통째로 죽는데 아무 테스트도
그 사실을 몰랐다. 여기서 못 박는다.
"""

import pytest

pytestmark = pytest.mark.regression


def test_seed_registers_the_mapping_workflow_under_the_contracted_name():
    """시드가 만드는 이름과 매핑이 찾는 이름이 같아야 한다."""
    from app.notion_mapping.service import MAPPING_WORKFLOW_NAME
    from app.workflows.service import seed_known_workflows
    import inspect

    src = inspect.getsource(seed_known_workflows)
    assert f'"{MAPPING_WORKFLOW_NAME}"' in src, (
        f"시드에 '{MAPPING_WORKFLOW_NAME}'이 없다 — 매핑이 영영 "
        "'Workflow가 구성되지 않았습니다'로 끝난다"
    )


def test_mapping_workflow_is_found_after_seeding(db, app):
    """시드 후 get_mapping_workflow()가 실제로 그것을 찾는다 (이름만 맞추면 되는 게 아니다)."""
    from app.notion_mapping.service import get_mapping_workflow
    from app.workflows.service import seed_known_workflows

    seed_known_workflows(db, allowlists=app.state.allowlists)
    db.flush()

    wf = get_mapping_workflow(db)
    assert wf is not None, "시드했는데도 매핑 workflow를 못 찾는다"
    assert wf.enabled, "매핑 workflow가 비활성이면 verify가 캐시를 지우고 UNMAPPED로 만든다"
    assert wf.webhook_url.endswith("/clovirone-notion-user-mapping"), (
        f"웹훅 경로가 n8n에 등록된 것과 다르다: {wf.webhook_url}"
    )
    # 이 워크플로는 Notion에 아무것도 쓰지 않는다. write로 등록되면 승인 게이트가 걸려
    # 조회 한 번에 승인을 요구하게 된다.
    assert wf.operation_mode == "read", f"읽기 전용이어야 한다: {wf.operation_mode}"


def test_seeding_twice_does_not_duplicate(db, app):
    """설치 스크립트는 멱등이다 — 재실행이 사본을 만들면 어느 것이 쓰이는지 알 수 없다."""
    from app.notion_mapping.service import MAPPING_WORKFLOW_NAME
    from app.workflows.models import Workflow
    from app.workflows.service import seed_known_workflows
    from sqlalchemy import func, select

    seed_known_workflows(db, allowlists=app.state.allowlists)
    seed_known_workflows(db, allowlists=app.state.allowlists)
    db.flush()

    count = db.execute(
        select(func.count()).select_from(Workflow).where(Workflow.name == MAPPING_WORKFLOW_NAME)
    ).scalar_one()
    assert count == 1, f"매핑 workflow가 {count}개 생겼다 — 시드가 멱등하지 않다"
