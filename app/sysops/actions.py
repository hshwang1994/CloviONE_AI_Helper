"""특권 헬퍼가 할 수 있는 일의 **전부** (§S).

## 이 표가 곧 보안 경계다

웹은 하드닝(`NoNewPrivileges` · `ProtectSystem=strict`)이 걸려 있어 sudo 도 `/etc` 쓰기도 못
한다. 그래서 시스템 설정은 root 로 도는 헬퍼가 대신 한다. 그 헬퍼가 **임의 명령**을 받으면
웹의 하드닝은 통째로 무의미해진다 — 웹을 뚫은 사람이 헬퍼를 통해 root 가 된다.

그래서 헬퍼는 **이름표를 받는다.** 여기 있는 키가 아니면 아무 일도 하지 않는다.

## 되돌리기를 액션이 아니라 엔진이 한다

액션마다 "백업하고, 적용하고, 검증하고, 실패하면 되돌린다" 를 각자 쓰면 언젠가 한 액션이
그 단계를 빠뜨린다(이 저장소는 같은 모양의 실수를 범위 판정에서 네 번 겪었다).
그래서 **백업과 롤백은 `execute` 가 무조건 한다.** 액션은 `touches` 로 "내가 건드릴 파일" 만
선언하면 된다. 빠뜨릴 자리가 코드에 없다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from app.core.errors import AppError
from app.sysops.runner import BinaryNotAllowedError, Runner


class UnknownActionError(AppError):
    status_code = 404
    code = "unknown_sysops_action"
    default_message = "알 수 없는 시스템 동작입니다."


@dataclass(frozen=True)
class ActionOutcome:
    """액션 하나의 결과.

    `changed` 를 따로 두는 이유: 같은 값을 다시 저장하는 일이 흔한데, 그때 "바꿨다" 고
    기록하면 감사 로그가 실제 변경으로 가득 차 진짜 변경을 못 찾는다.
    """

    ok: bool
    detail: str
    changed: bool = False
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionResult:
    action: str
    ok: bool
    detail: str
    changed: bool
    data: dict
    rolled_back: bool
    backup_dir: str | None


@dataclass(frozen=True)
class Action:
    name: str
    summary: str
    mutating: bool
    normalize: Callable[[Mapping], dict]
    perform: Callable[[Runner, dict], ActionOutcome]
    # 적용 전에 복사해 둘 파일. 실패하면 엔진이 이 목록을 그대로 되돌린다.
    touches: Callable[[dict], tuple[str, ...]] = lambda _params: ()


_REGISTRY: dict[str, Action] = {}


def register(action: Action) -> Action:
    if action.name in _REGISTRY:  # pragma: no cover - 모듈 로드 시점 실수 방지
        raise RuntimeError(f"중복된 액션 이름: {action.name}")
    _REGISTRY[action.name] = action
    return action


def get_action(name: object) -> Action:
    if not isinstance(name, str) or name not in _REGISTRY:
        # 이름을 그대로 되돌려 주지만, 이름은 사용자가 보낸 값이므로 길이를 자른다.
        shown = str(name)[:64]
        raise UnknownActionError(f"알 수 없는 시스템 동작입니다: {shown}")
    return _REGISTRY[name]


def list_actions() -> list[dict]:
    """관리자 화면이 "이 서버에서 무엇을 바꿀 수 있는가" 를 그릴 때 쓴다."""
    return [
        {"name": a.name, "summary": a.summary, "mutating": a.mutating}
        for a in sorted(_REGISTRY.values(), key=lambda a: a.name)
    ]


def _backup_dir_name(action: str, now: datetime) -> str:
    return f"{now.strftime('%Y%m%d-%H%M%S')}-{action.replace('.', '-')}"


def execute(
    runner: Runner,
    name: object,
    params: Mapping | None = None,
    *,
    backup_root: str,
    now: datetime,
) -> ExecutionResult:
    """액션 하나를 **백업 → 적용 → 실패 시 원복** 순서로 실행한다.

    검증은 액션 안에서 한다(무엇이 "성공" 인지는 액션마다 다르다). 다만 실패했을 때 되돌리는
    책임은 여기에 있다 — 그래야 새 액션을 추가한 사람이 잊을 수 없다.
    """
    action = get_action(name)
    normalized = action.normalize(params or {})

    if not action.mutating:
        outcome = action.perform(runner, normalized)
        return ExecutionResult(
            action=action.name, ok=outcome.ok, detail=outcome.detail,
            changed=False, data=outcome.data, rolled_back=False, backup_dir=None,
        )

    targets = tuple(action.touches(normalized))
    backup_dir = f"{backup_root}/{_backup_dir_name(action.name, now)}"
    # 원본이 없던 파일은 `saved=False` 로 남는다. 되돌릴 때 **파일을 지워야** 원래 상태가 된다 —
    # 없던 파일을 남겨 두면 "되돌렸다" 고 말하면서 설정이 남아 있게 된다.
    saved: list[tuple[str, bool]] = []
    for path in targets:
        ok = runner.copy(path, f"{backup_dir}/{path.strip('/').replace('/', '_')}")
        saved.append((path, ok))

    try:
        outcome = action.perform(runner, normalized)
    except BinaryNotAllowedError as exc:
        outcome = ActionOutcome(ok=False, detail=f"실행이 차단됐습니다: {exc}")
    except Exception as exc:  # noqa: BLE001 - 아래 백업 롤백이 반드시 돌아야 한다
        # `perform` 은 파일 쓰기·프로세스 호출을 직접 한다(runner.write_text 는 내부에
        # try/except 가 없다). 여기서 잡지 않으면 원인 모를 OSError 하나가 이 함수를 그대로
        # 빠져나가 아래 롤백 블록을 건너뛰고, 호출자(helper.handle_request)의 최상위
        # except 까지 올라가 `rolled_back=False` 로 보고된다 — 백업은 이미 떠 놨는데도 쓰이지
        # 않는다.
        outcome = ActionOutcome(ok=False, detail=f"처리 중 오류가 발생했습니다({exc.__class__.__name__}).")

    rolled_back = False
    if not outcome.ok and targets:
        for path, had_original in saved:
            stored = f"{backup_dir}/{path.strip('/').replace('/', '_')}"
            if had_original:
                runner.copy(stored, path)
            else:
                runner.remove(path)
        rolled_back = True

    return ExecutionResult(
        action=action.name,
        ok=outcome.ok,
        detail=outcome.detail,
        changed=outcome.changed and outcome.ok,
        data=outcome.data,
        rolled_back=rolled_back,
        backup_dir=backup_dir if targets else None,
    )


# 구현을 등록시키기 위한 import. 파일 끝에 둔 이유는 순환 import 를 피하기 위해서다 —
# 구현 모듈이 이 파일의 `Action` 과 `register` 를 쓴다.
from app.sysops import actions_service, actions_system  # noqa: E402,F401  (등록 부작용)
