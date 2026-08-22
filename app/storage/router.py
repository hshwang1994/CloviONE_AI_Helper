"""저장소 설정 API (S8).

## 권한 이름을 새로 짓지 않는다

S5 가 `STORAGE_CONFIGURE` 를 미리 고정해 뒀다(`app/authz/permissions.py`). S8 은 그
이름의 **첫 소비처**가 된다 — 새 이름을 지으면 나중에 한 번에 모으지 못한다.

읽기도 같은 권한으로 막는다. 저장소 목록은 경로·마운트 소스·용량을 담고 있어서,
그것만으로도 서버의 구조가 드러난다. 「보기만 하는 권한」을 따로 만들 이유가 지금은
없다 — 이 화면을 보는 사람은 곧 고칠 사람이다.

## 마운트 상태는 요청할 때마다 실제로 본다

캐시하지 않는다. 이 화면을 여는 이유가 「지금 붙어 있나」이기 때문이다. `st_dev` 조회는
`stat(2)` 두 번이라 캐시할 만큼 비싸지 않다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.deps import get_db, require_csrf, require_permission
from app.storage import service
from app.storage.models import StorageProvider
from app.storage.schemas import ProviderCreate, ProviderUpdate
from app.users.models import User

router = APIRouter(prefix="/api/storage", tags=["storage"])


@router.get("/status")
def storage_status(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("STORAGE_CONFIGURE")),
) -> dict:
    return service.storage_health(db)


@router.get("/providers")
def list_providers(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("STORAGE_CONFIGURE")),
) -> dict:
    rows = list(
        db.execute(
            select(StorageProvider).order_by(StorageProvider.role, StorageProvider.name)
        ).scalars().all()
    )
    return {
        "items": [service.provider_status(p) for p in rows],
        "warning": service.same_device_warning(db),
    }


@router.post("/providers", dependencies=[Depends(require_csrf)])
def create_provider(
    payload: ProviderCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("STORAGE_CONFIGURE")),
) -> dict:
    provider = service.create_provider(
        db,
        name=payload.name, kind=payload.kind, role=payload.role,
        base_path=payload.base_path, mount_point=payload.mount_point,
        source=payload.source, options=payload.options,
        credentials_ref=payload.credentials_ref, enabled=payload.enabled,
    )
    record_audit_from_request(
        request, db, action="storage.provider.create", object_type="storage_provider",
        object_id=provider.id,
        after={"name": provider.name, "kind": provider.kind, "role": provider.role},
    )
    return service.provider_status(provider)


@router.patch("/providers/{provider_id}", dependencies=[Depends(require_csrf)])
def update_provider(
    provider_id: str,
    payload: ProviderUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("STORAGE_CONFIGURE")),
) -> dict:
    provider = service.get_provider_or_404(db, provider_id)
    before = {"enabled": provider.enabled, "base_path": provider.base_path}
    changes = payload.model_dump(exclude_unset=True, exclude={"base_version"})
    provider = service.update_provider(
        db, provider, expected_version=payload.base_version, **changes
    )
    record_audit_from_request(
        request, db, action="storage.provider.update", object_type="storage_provider",
        object_id=provider.id, before=before,
        after={"enabled": provider.enabled, "base_path": provider.base_path},
    )
    return service.provider_status(provider)


@router.post("/providers/{provider_id}/probe", dependencies=[Depends(require_csrf)])
def probe_provider(
    provider_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("STORAGE_CONFIGURE")),
) -> dict:
    """지금 이 저장소에 쓸 수 있는가를 **실제로** 확인한다.

    상태 조회와 달리 마운트 유닛 이름까지 함께 낸다 — 안 붙어 있을 때 관리자가
    다음에 칠 명령이 `systemctl start <그 유닛>` 이기 때문이다.
    """
    provider = service.get_provider_or_404(db, provider_id)
    out = service.provider_status(provider)
    if provider.mount_point:
        from app.storage.units import unit_name

        out["mount_unit"] = unit_name(provider.mount_point)
    return out
