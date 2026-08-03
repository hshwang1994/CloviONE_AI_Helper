"""기능 플래그 화면 API (0033, PLAN Phase 6).

## 왜 파일을 쓰는가 (DB 로 옮기지 않는 이유)

`app/core/feature_flags.py` 의 존재 이유가 **소유자 단일화**다. 파일 소유 플래그를 화면에서
바꿀 수 있게 하려고 DB 에 사본을 두면, 그 순간 split-brain 이 그대로 되살아난다 — 서버에
들어가 JSON 을 고친 사람은 아무 일도 안 일어나는 것을 보게 되고, 그건 이 파일이 애초에
고쳤던 사고다. 그래서 화면도 **정본인 그 파일을 고친다**.

캐시 무효화는 이미 되어 있다: `load_feature_flags` 는 `(경로, mtime_ns, size)` 로 캐시하므로
파일을 바꾸면 다음 호출에서 자동으로 다시 읽는다. 여기서 캐시를 건드릴 필요가 없다.

## 쓰기는 원자적으로

임시 파일에 쓰고 `os.replace` 로 바꾼다. 곧바로 덮어쓰면, 쓰는 도중 요청이 들어와 **반쪽짜리
JSON** 을 읽을 수 있다 — 그러면 `_parse` 가 기본값으로 되돌아가 모든 모듈이 한순간 기본
상태가 된다(그리고 아무 오류도 안 난다).

DB 소유 플래그는 여기서 **못 바꾼다**. 409 로 거절하고 설정 화면으로 안내한다 — 두 화면이
같은 값을 서로 다르게 바꿀 수 있으면 그게 곧 split-brain 이다.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import get_db, require_csrf, require_roles
from app.core.errors import ConflictError, NotFoundError
from app.core.feature_flags import (
    FLAG_REGISTRY,
    OWNER_DB,
    OWNER_FILE,
    flags_path,
    load_feature_flags,
    reset_cache,
)

logger = logging.getLogger("app.admin.feature_flags")

router = APIRouter(
    prefix="/api/admin/feature-flags",
    tags=["admin-feature-flags"],
    dependencies=[Depends(require_csrf)],
)

# 읽는 코드가 하나도 없는 플래그. 레지스트리 설명에 그렇게 적혀 있으므로 화면에도 그대로
# 드러낸다 — 관리자가 스위치를 켜고 무언가 달라지길 기대하지 않도록.
_NO_CONSUMER_MARK = "(소비자 없음)"

# 파일에 쓸 때 쓰는 줄바꿈. 상수로 빼 둔 이유는 리터럴 안의 백슬래시가 편집 중 실제 줄바꿈으로
# 바뀌어 파일이 깨진 적이 있어서다(그때는 SyntaxError 라 곧바로 드러났지만, 조용히 CRLF 가
# 섞이는 쪽이 더 나쁘다 — 내용이 같은데도 저장소 diff 가 통째로 흔들린다).
_LF = "\n"


class FlagUpdate(BaseModel):
    enabled: bool


def _db_values(request: Request) -> dict:
    cache = getattr(request.app.state, "settings_cache", None)
    if cache is None:
        return {}
    out = {}
    for name, spec in FLAG_REGISTRY.items():
        if spec.owner != OWNER_DB:
            continue
        value = cache.current_value(name)
        out[name] = spec.default if value is None else bool(value)
    return out


def _items(request: Request) -> list[dict]:
    file_values = load_feature_flags(request.app.state.settings.config_dir)
    db_values = _db_values(request)
    items = []
    for name in sorted(FLAG_REGISTRY):
        spec = FLAG_REGISTRY[name]
        if spec.owner == OWNER_FILE:
            value = bool(file_values.get(name, spec.default))
        else:
            value = bool(db_values.get(name, spec.default))
        items.append({
            "name": name,
            "value": value,
            "default": spec.default,
            "owner": spec.owner,
            "description": spec.description,
            "editable_here": spec.owner == OWNER_FILE,
            "has_consumer": _NO_CONSUMER_MARK not in spec.description,
            # 파일 소유는 재시작 없이 즉시 반영된다(mtime 캐시). DB 소유는 설정 화면 소관.
            "edit_hint": (
                "즉시 반영됩니다(재시작 불필요)."
                if spec.owner == OWNER_FILE
                else "이 플래그의 정본은 설정 화면입니다 — 여기서는 바꿀 수 없습니다."
            ),
        })
    return items


@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_flags(request: Request) -> dict:
    return {
        "items": _items(request),
        "source": str(flags_path(request.app.state.settings.config_dir)),
        "registry": "app/core/feature_flags.py",
    }


@router.put("/{name}", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def set_flag(
    request: Request, name: str, payload: FlagUpdate, db: Session = Depends(get_db)
) -> dict:
    spec = FLAG_REGISTRY.get(name)
    if spec is None:
        raise NotFoundError(f"알 수 없는 기능 플래그입니다: {name}")
    if spec.owner != OWNER_FILE:
        raise ConflictError(
            "이 플래그의 정본은 설정(app_settings)입니다. 관리자 콘솔의 '설정' 화면에서 바꾸세요."
        )

    path = flags_path(request.app.state.settings.config_dir)
    before = bool(load_feature_flags(path.parent).get(name, spec.default))
    try:
        _write_flag(path, name, payload.enabled)
    except OSError as exc:
        # 운영에서 config 디렉터리가 서비스 계정에 읽기 전용일 수 있다. 스택을 뱉는 500 대신
        # 관리자가 무엇을 해야 하는지 말해 준다 — "저장 안 됨"을 "서버 오류"로 보여 주면
        # 아무도 원인을 못 찾는다.
        logger.error("기능 플래그 파일 쓰기 실패: %s (%s)", path, exc)
        raise ConflictError(
            f"플래그 파일을 저장하지 못했습니다({path}). 서버에서 이 파일의 쓰기 권한을 확인하세요."
        ) from None
    # mtime 해상도가 낮은 파일시스템에서 같은 캐시 키가 나올 수 있다 — 바꾼 직후만큼은
    # 확실히 다시 읽게 한다(이 경로는 초당 수천 번 불리는 곳이 아니다).
    reset_cache()

    after = bool(load_feature_flags(path.parent).get(name, spec.default))
    record_audit_from_request(
        request, db, action="feature_flag.update", object_type="feature_flag",
        object_id=name, before={"value": before}, after={"value": after},
    )
    return {"name": name, "value": after, "owner": spec.owner}


def _write_flag(path: Path, name: str, value: bool) -> None:
    """플래그 하나를 파일에 반영한다. 다른 키와 주석 필드(`_`)는 그대로 보존한다."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (json.JSONDecodeError, OSError):
        data = {}
    data[name] = value
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    # 같은 디렉터리에 임시 파일을 만들어야 os.replace 가 원자적이다(다른 파일시스템 간
    # replace 는 원자성이 보장되지 않는다).
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".flags-", suffix=".tmp")
    try:
        # newline 을 LF 로 명시한다 — 윈도우에서 기본 변환이 걸리면 같은 내용인데도
        # 저장소에 커밋되는 파일이 플랫폼마다 달라져 diff 가 통째로 흔들린다.
        with os.fdopen(fd, "w", encoding="utf-8", newline=_LF) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
