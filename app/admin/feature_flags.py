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

## 파일 한 벌을 통째로 다시 쓰므로 **잠가야 한다**

`_write_flag` 는 키 하나를 바꾸려고 파일 전체를 읽어 딕셔너리에 얹고 전체를 다시 쓴다.
잠금이 없으면 서로 다른 두 플래그를 동시에 켜는 것만으로 한쪽이 사라진다 — 읽기와 쓰기
사이에 남이 끼어들면 이쪽의 스냅숏이 그 변경을 통째로 덮기 때문이다(실측: 6회 중 6회
유실, 그중 5회는 **응답이 200 이고 「켰다」고 말한다**). 배포는 `--workers 4` 라
(`deploy/systemd/clovirassist-web.service`) 프로세스 안의 `threading.Lock` 만으로는
못 막는다(D-192 가 같은 이유로 잠금들을 프로세스 밖으로 옮겼다).

그래서 **파일 잠금**이다. 이 파일은 호스트마다 한 벌이므로 잠금도 호스트 안에서 성립하면
충분하다 — 잠금 대상과 잠금 범위가 같다. 잠금 파일은 `data_dir` 에 둔다(`worker.lock` 과
같은 자리): `config_dir` 은 운영에서 서비스 계정에 읽기 전용일 수 있다.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import (
    audit_forbidden_write,
    get_db,
    get_principal,
    require_csrf,
    require_roles,
)
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.feature_flags import (
    FLAG_REGISTRY,
    OWNER_DB,
    OWNER_FILE,
    flags_path,
    load_feature_flags,
    reset_cache,
)
from app.core.scope import Principal, require_global_management

logger = logging.getLogger("app.admin.feature_flags")

router = APIRouter(
    prefix="/api/admin/feature-flags",
    tags=["admin-feature-flags"],
    dependencies=[Depends(require_csrf)],
)

# 읽는 코드가 하나도 없는 플래그. 화면의 '실제 효과' 열이 이 값을 그대로 보여 준다 —
# 관리자가 스위치를 켜고 무언가 달라지길 기대하지 않도록.
#
# **설명 문자열 매칭만으로는 틀린다.** 예전에는 설명에 `(소비자 없음)` 이 들어 있는지만
# 봤는데, 그 표식은 사람이 손으로 붙이는 것이라 빠뜨리면 화면이 자동으로 「효과 있음」이
# 된다 — 즉 **틀리는 방향이 안전한 쪽이 아니다**. 실제로 `document_automation_enabled` 가
# 그렇게 새어 나갔다: 저장소 전체에서 이 키를 읽는 코드가 0인데(선언 두 곳뿐) 화면은
# 「있음」이라 말했고, 사고 중에 문서 생성을 잠그려던 관리자는 막혔다고 믿게 된다.
#
# 그래서 이름을 여기 명시한다. 표식은 그대로 두 번째 신호로 살려 둔다(레지스트리에 이미
# 적힌 것을 무시하지 않는다). 이 목록과 실제 소비자의 어긋남은
# `tests/integration/test_feature_flag_consumers.py` 가 정적 스캔으로 못박는다.
_NO_CONSUMER_MARK = "(소비자 없음)"
_NO_CONSUMER_FLAGS: frozenset[str] = frozenset(
    {
        "limited_service_actions_enabled",
        "document_automation_enabled",
    }
)

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
            "has_consumer": (
                name not in _NO_CONSUMER_FLAGS
                and _NO_CONSUMER_MARK not in spec.description
            ),
            # 파일 소유는 재시작 없이 즉시 반영된다(mtime 캐시). DB 소유는 설정 화면 소관.
            "edit_hint": (
                "즉시 반영됩니다(재시작 불필요)."
                if spec.owner == OWNER_FILE
                else "이 플래그의 정본은 설정 화면입니다. 여기서는 바꿀 수 없습니다."
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
    request: Request,
    name: str,
    payload: FlagUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> dict:
    # 플래그 하나가 전 조직의 화면을 켜고 끈다 — `board_enabled` 를 끄면 모든 사용자의
    # 사이드바에서 자유게시판이 사라진다. 부서로 나눌 수 있는 값이 아니므로 관리 범위가
    # 전역인 사람만 바꾼다(설정 표와 같은 판정, `app/settings/router.py::_guard_scope`).
    # 막은 시도는 역할 게이트와 같은 자리에 남긴다 — 범위 게이트는 핸들러 안에서
    # 판정하므로 `require_roles` 의 감사 기록을 지나지 않는다.
    try:
        require_global_management(principal, "기능 플래그")
    except ForbiddenError:
        audit_forbidden_write(request, db, request.state.user)
        raise
    spec = FLAG_REGISTRY.get(name)
    if spec is None:
        raise NotFoundError(f"알 수 없는 기능 플래그입니다: {name}")
    if spec.owner != OWNER_FILE:
        raise ConflictError(
            "이 플래그의 정본은 설정(app_settings)입니다. 관리자 콘솔의 '설정' 화면에서 바꾸세요."
        )

    path = flags_path(request.app.state.settings.config_dir)
    try:
        before, after = _write_flag(
            path, name, payload.enabled,
            default=spec.default,
            lock_dir=Path(request.app.state.settings.data_dir),
        )
    except OSError as exc:
        # 여기까지 온 OSError 는 **경합이 아니다.** 동시 저장은 아래 잠금이 직렬화하고,
        # 윈도우의 일시적 공유 위반은 `_replace_with_retry` 가 흡수한다. 남는 것은 권한
        # 어긋남·디스크 가득 참 같은 진짜 파일시스템 고장이라, 예전부터 쓰던 이 안내가
        # 그때는 정확하다(운영에서 config 디렉터리가 읽기 전용인 사고가 실제로 있었다).
        logger.error("기능 플래그 파일 쓰기 실패: %s (%s)", path, exc)
        raise ConflictError(
            f"플래그 파일을 저장하지 못했습니다({path}). 서버에서 이 파일의 쓰기 권한을 확인하세요."
        ) from None
    # mtime 해상도가 낮은 파일시스템에서 같은 캐시 키가 나올 수 있다 — 바꾼 직후만큼은
    # 확실히 다시 읽게 한다(이 경로는 초당 수천 번 불리는 곳이 아니다).
    reset_cache()

    record_audit_from_request(
        request, db, action="feature_flag.update", object_type="feature_flag",
        object_id=name, before={"value": before}, after={"value": after},
    )
    return {"name": name, "value": after, "owner": spec.owner}


def _write_flag(
    path: Path, name: str, value: bool, *, default: bool, lock_dir: Path
) -> tuple[bool, bool]:
    """플래그 하나를 파일에 반영하고 `(직전 값, 반영한 값)` 을 돌려준다.

    다른 키와 주석 필드(`_`)는 그대로 보존한다.

    **읽기·병합·쓰기가 통째로 잠금 안에 있다.** 셋을 나누면 그 틈에 들어온 다른 저장이
    사라진다(모듈 머리말). 직전 값도 이 안에서 읽는다 — 잠금 밖에서 읽으면 응답과 감사
    로그의 `before` 가 남의 저장을 가리키게 된다.

    돌려주는 「반영한 값」이 요청 값과 언제나 같은 이유: 잠금을 놓기 전에 우리가 쓴 내용이
    파일에 있고, 실패했다면 예외로 나간다. 예전에는 잠금을 놓은 뒤 파일을 다시 읽어
    그 값을 돌려줬고, 그래서 남이 덮어쓴 값을 자기 성공으로 200 에 실어 보냈다.
    """
    with _flags_file_lock(lock_dir):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (json.JSONDecodeError, OSError):
            data = {}
        raw = data.get(name)
        # `load_feature_flags` 와 같은 규칙으로 읽는다 — 진짜 JSON 불리언이 아니면
        # 값이 없는 것으로 보고 기본값을 쓴다(app/core/feature_flags.py::_parse, CORE-10).
        before = raw if isinstance(raw, bool) else default
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
            _replace_with_retry(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    return bool(before), bool(value)


# 잠금 파일 이름. `data_dir` 에 둔다 — `config_dir` 은 운영에서 읽기 전용일 수 있고,
# 시험에서는 저장소의 `config/` 라 잠금 파일이 작업 트리에 남는다.
_LOCK_FILENAME = "feature-flags.lock"

# 프로세스 안의 빠른 길. 파일 잠금만으로도 정확하지만, 같은 프로세스의 스레드 넷이 OS
# 잠금에서 부딪히는 것보다 여기서 줄 서는 편이 싸다(웹은 동기 핸들러를 스레드풀에서 돈다).
_process_lock = threading.Lock()

# `os.replace` 재시도. 윈도우는 대상 파일을 다른 스레드가 **읽으려고** 열어 두기만 해도
# 공유 위반(WinError 5)으로 거절한다 — 잠금과 무관한 일시적 실패라 그때만 잠깐 기다렸다
# 다시 한다. 포직스에서는 이 상황이 아예 없으므로 첫 번째 시도에서 끝난다.
_REPLACE_ATTEMPTS = 20
_REPLACE_SLEEP_SECONDS = 0.02


@contextmanager
def _flags_file_lock(lock_dir: Path):
    """플래그 파일을 고치는 동안 드는 잠금. 프로세스 안(스레드)과 밖(워커) 모두 막는다.

    포직스는 `fcntl.flock`, 윈도우는 `msvcrt.locking` 이다. 한쪽만 쓰지 않는 이유는
    `app/core/worker_lock.py` 가 적어 둔 것과 같다 — 개발이 윈도우라 거기서 돌려 볼 수
    없는 잠금은 「있다고 믿지만 확인한 적 없는 잠금」이 된다.
    """
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / _LOCK_FILENAME
    with _process_lock:
        # `a+b` 는 파일이 없으면 만들고, 있으면 내용을 건드리지 않는다. 이 파일에는
        # 아무것도 쓰지 않는다 — 잠금을 걸 대상이 필요할 뿐이다.
        with open(lock_path, "a+b") as handle:
            _lock_exclusive(handle)
            try:
                yield
            finally:
                _unlock(handle)


def _lock_exclusive(handle) -> None:
    try:
        import fcntl
    except ImportError:  # 윈도우
        import msvcrt

        handle.seek(0)
        # LK_LOCK 은 1초 간격으로 열 번 다시 시도한 뒤 OSError 를 낸다. 잠긴 구간이
        # 파일 하나 쓰는 시간이라 그 안에 들어온다.
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock(handle) -> None:
    try:
        import fcntl
    except ImportError:  # 윈도우
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _replace_with_retry(tmp_name: str, path: Path) -> None:
    """`os.replace` 를 윈도우의 일시적 공유 위반에 대해서만 다시 시도한다.

    예산을 다 쓰면 마지막 예외를 그대로 올린다 — 권한 어긋남·디스크 오류를 재시도로
    가리면 「저장이 가끔 안 된다」가 되고 원인은 영영 안 보인다.
    """
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(tmp_name, path)
            return
        except OSError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_SLEEP_SECONDS)
