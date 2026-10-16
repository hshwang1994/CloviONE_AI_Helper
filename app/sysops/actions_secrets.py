"""비밀 값 저장·삭제 (계획 2.3).

운영 설치에서 `/etc/clovirassist/secrets` 는 root:clovirassist 0750 이고 웹 유닛은
`ProtectSystem=strict` 라 그 디렉터리에 쓸 수 없다. 그래서 SMTP 비밀번호와 AI API 키를
화면에서 넣으려면 누군가 root 로 파일을 놓아야 했고, 그 누군가는 서버에 들어간 사람이었다.
이 두 액션이 그 일을 대신한다.

## 경계

- **이름은 `app/core/secret_slots.py` 의 표에 있는 것만** 받는다. 웹이 이미 검사했어도 여기서
  다시 본다 - 웹이 뚫렸다는 가정에서도 헬퍼가 `/etc/clovirassist/secrets` 아래 임의 파일을
  만들면 안 된다.
- **값은 어디에도 남기지 않는다.** `detail`·`data`·예외 문구 어디에도 싣지 않는다. 헬퍼의
  감사 기록은 원래 `params` 를 적지 않는다(`app/sysops/helper.py`).
- **백업을 뜨지 않는다**(`touches` 가 비어 있다). 엔진의 되돌리기 백업은 `/var/backups` 에
  옛 파일을 복사하는데, 비밀 값의 사본을 그곳에 남기는 편이 되돌리기보다 위험하다.
  실패하면 파일은 원래 값 그대로다(임시 파일에 쓰고 바꿔치기한다).

파일은 헬퍼 프로세스의 그룹(`Group=clovirassist`)으로 만들어지고 권한은 0640 이다 - 설치
스크립트가 놓는 파일과 같은 모양이라 웹과 워커가 그룹 권한으로 읽는다.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from app.core import product
from app.core.secret_slots import SECRET_SLOTS, normalize_value
from app.sysops.actions import Action, ActionOutcome, register
from app.sysops.runner import Runner

SECRET_FILE_MODE = 0o640


class _Rejected(ValueError):
    """헬퍼 안의 검증 실패. 문구는 사용자에게 그대로 간다 - 값을 싣지 않는다."""


def _secrets_dir() -> str:
    # 웹·워커와 같은 env 파일(`EnvironmentFile=`)에서 온다. 없으면 제품 기본 경로다.
    return (os.environ.get("SECRETS_DIR") or product.SECRETS_DIR).rstrip("/")


def _slot_name(params: Mapping) -> str:
    name = params.get("name")
    if not isinstance(name, str) or name not in SECRET_SLOTS:
        raise _Rejected("저장할 수 없는 비밀 값 이름입니다.")
    return name


def _normalize_write(params: Mapping) -> dict:
    name = _slot_name(params)
    try:
        value = normalize_value(SECRET_SLOTS[name], params.get("value"))
    except Exception as exc:  # noqa: BLE001 - 검증 문구만 넘긴다
        raise _Rejected(getattr(exc, "message", "비밀 값이 올바르지 않습니다.")) from None
    return {"name": name, "value": value}


def _normalize_delete(params: Mapping) -> dict:
    return {"name": _slot_name(params)}


def _perform_write(runner: Runner, params: dict) -> ActionOutcome:
    path = f"{_secrets_dir()}/{params['name']}"
    previous = runner.read_text(path)
    if previous is not None and previous.strip() == params["value"]:
        return ActionOutcome(ok=True, detail="같은 값이 이미 저장돼 있습니다.", changed=False,
                             data={"name": params["name"]})
    runner.write_text(path, params["value"], mode=SECRET_FILE_MODE)
    # 되읽어 확인한다. 쓰기가 조용히 실패하면(읽기 전용 마운트 등) 운영자는 저장됐다고 믿는다.
    if runner.read_text(path) != params["value"]:
        return ActionOutcome(ok=False, detail="비밀 값을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")
    return ActionOutcome(ok=True, detail="비밀 값을 저장했습니다.", changed=True,
                         data={"name": params["name"]})


def _perform_delete(runner: Runner, params: dict) -> ActionOutcome:
    path = f"{_secrets_dir()}/{params['name']}"
    existed = runner.exists(path)
    runner.remove(path)
    if runner.exists(path):
        return ActionOutcome(ok=False, detail="비밀 값을 삭제하지 못했습니다.")
    return ActionOutcome(ok=True, detail="비밀 값을 삭제했습니다." if existed else "삭제할 값이 없었습니다.",
                         changed=existed, data={"name": params["name"]})


def _guarded(normalize):
    """검증 실패를 엔진이 이해하는 결과로 바꾼다.

    `execute` 는 normalize 가 던지면 그대로 올린다. 헬퍼의 최상위 처리기는 예외 **종류**만
    알리므로(값이 섞일까 봐) 사용자는 "처리 중 오류(_Rejected)" 만 보게 된다. 그래서 여기서
    문구를 들고 있는 표식으로 바꿔 perform 이 곧바로 실패로 돌려주게 한다.
    """
    def inner(params: Mapping) -> dict:
        try:
            return normalize(params)
        except _Rejected as exc:
            return {"_rejected": str(exc)}
    return inner


def _perform_guarded(perform):
    def inner(runner: Runner, params: dict) -> ActionOutcome:
        if "_rejected" in params:
            return ActionOutcome(ok=False, detail=params["_rejected"])
        return perform(runner, params)
    return inner


register(Action(
    name="secret.write",
    summary="비밀 값 하나를 저장합니다(메일 비밀번호, AI 키)",
    mutating=True,
    normalize=_guarded(_normalize_write),
    perform=_perform_guarded(_perform_write),
))

register(Action(
    name="secret.delete",
    summary="비밀 값 하나를 지웁니다",
    mutating=True,
    normalize=_guarded(_normalize_delete),
    perform=_perform_guarded(_perform_delete),
))
