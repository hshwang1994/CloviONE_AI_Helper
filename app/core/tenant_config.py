"""설치처(테넌트) 고유 설정이 채워졌는지 한곳에서 판정한다.

## 왜 이 모듈이 있는가

`app/core/config.py` 의 **기본값**에 개발 워크스페이스의 Notion DB id 두 개와
`allowed_email_domains="goodmit.co.kr"` 가 박혀 있었다. 다른 고객사에 설치하면 아무 설정
없이도 조용히 그 워크스페이스를 가리켰다. 토큰이 없어 데이터가 새지는 않지만,
**동작하지 않는 이유가 어디에도 안 뜬다** — 화면에는 그냥 빈 목록이 나오고, 운영자는
"연결은 됐는데 안 된다" 로 읽는다.

기본값을 비우는 것은 절반이다. 비우기만 하면 화면은 여전히 빈 목록을 보여 주고,
그건 "설정을 안 했다" 와 "설정은 했는데 결과가 없다" 를 구분하지 못한다
(§불변 6: 0 과 "없음" 과 "못 잼" 은 서로 다른 사실이다). 그래서 "아직 설정하지 않았습니다" 를
**별도 상태**로 만들어 진단 번들에 싣는다.

## 왜 여기(app/core)인가

진단(app/health), 설정 화면, 앞으로 생길 설치 점검 스크립트가 같은 판정을 공유해야 한다.
판정이 두 벌이 되는 순간 한쪽만 고쳐지고, 그러면 "설정했다는데 안 된다" 가 다시 생긴다.
정적 검사(scripts/check_tenant_defaults.py)는 이 목록의 **키**를 읽어 소스 기본값을 검사한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TenantSetting:
    """설치처마다 값이 다른 설정 하나.

    `when_unset` 은 "비면 무슨 일이 벌어지는가" 를 사람 문장으로 적는다. 화면이 키 이름만
    보여 주면 운영자는 그게 문제인지 원래 그런 건지 모른다.
    """

    key: str
    label: str
    env_var: str
    when_unset: str


# 설치처 고유값 목록. **여기가 유일한 목록이다** — 화면·진단·정적 검사가 전부 이걸 읽는다.
#
# 새 설치처 고유값을 설정에 추가하면 여기에도 넣어야 한다. 안 넣으면 그 값은 비어 있어도
# 아무 데도 안 뜨고, 우리가 없애려던 바로 그 침묵으로 돌아간다.
#
# ⚠️ 관리 콘솔에서 바꾼 값을 `Settings` 에 덮어쓰던 목록(`OVERRIDABLE_KEYS`)은 D-515 에서 걷었다 - 그 목록과는
# **다른 목적의 다른 목록**이었다. 아래 설명은 그때의 기록이다. 지금은 겹치는
# 항목이 하나도 없다. `allowed_email_domains` 가 여기에만 있고 저기엔 없는 이유는 취향이
# 아니라 **타입이 안 맞기 때문**이다: `Settings.allowed_email_domains` 는 `str`(콤마
# 구분)인데 레지스트리 값은 `list`(registry.py:264) 다. `apply_overrides` 는
# `setattr(settings, key, target)` 을 그대로 하므로, 이 키를 OVERRIDABLE_KEYS 에 넣으면
# `Settings` 필드에 리스트가 얹히고 - `validate_assignment` 가 없어 그 대입은 **조용히
# 성공**한 뒤 나중에 `allowed_email_domain_list`(config.py:170, `.split(",")` 를 부르는 곳)
# 에서 `AttributeError`(list 에는 `.split` 이 없다) 로 터진다. 이 키를 오버레이에 추가하려면
# 먼저 양쪽 타입을 맞춰야 한다.
# 노션 데이터베이스 id 둘이 여기 있었다. 티켓 목록과 문서 목록이 그 값으로 노션을
# 조회했으므로 비어 있는 것이 곧 「화면이 빈 이유」였다. 지금은 둘 다 자체 데이터베이스에서
# 나오고 설정 자체가 없어서, 여기 남아 있으면 존재하지 않는 값을 안 채웠다고 말하게 된다.
TENANT_SETTINGS: tuple[TenantSetting, ...] = (
    TenantSetting(
        key="allowed_email_domains",
        label="계정 생성 허용 도메인",
        env_var="ALLOWED_EMAIL_DOMAINS",
        when_unset="새 계정을 만들 때 이메일 도메인을 제한하지 않습니다. 기존 사용자의 로그인은 영향받지 않습니다.",
    ),
)

STATE_SET = "set"
STATE_UNSET = "unset"


def _unwrap(value: Any) -> Any:
    """DB 설정 값의 두 가지 모양을 하나로 맞춘다.

    `SettingsCache.current()` 는 값을 날것으로 준다. 그런데 진단이 쓰는
    `app/settings/service.py::effective_settings` 는 화면용 메타데이터로 감싼 봉투를 준다:
    `{"value": [...], "type": ..., "description": ..., "is_default": ...}`.

    이 차이 때문에 실제로 한 번 틀렸다. 봉투를 그대로 보면 **항상 비어 있지 않은 dict** 라
    빈 목록이 "설정됨" 으로 보고됐다 — 우리가 없애려던 바로 그 거짓 신호를, 그것을 없애는
    코드가 냈다. 값이 달라지는 표본으로 두 번 불러 본 테스트가 잡았다.
    """
    if isinstance(value, dict) and "value" in value and "type" in value:
        return value["value"]
    return value


def _is_set(value: Any) -> bool:
    """값이 '들어 있다' 고 볼 수 있는가.

    빈 문자열·빈 목록·None 을 전부 '없음' 으로 본다. 공백만 있는 문자열도 없음이다 —
    env 파일에 `NOTION_TASKS_DATABASE_ID= ` 처럼 남겨 두고 설정했다고 착각하는 일이 있다.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def tenant_config_status(settings, effective: dict | None = None) -> dict:
    """설치처 고유 설정의 현재 상태를 돌려준다.

    `effective` 는 관리 콘솔에서 바꾼 DB 설정(app/settings/service.py::effective_settings).
    같은 키가 있으면 그쪽이 실제로 적용 중인 값이므로 우선한다 — env 만 보면 관리자가
    콘솔에서 도메인을 넣어 둔 설치를 "설정 안 함" 이라고 잘못 말한다.
    """
    eff = effective or {}
    items: list[dict] = []
    for spec in TENANT_SETTINGS:
        # DB 값이 **채워져 있을 때만** 그쪽을 본다. 예전에는 "키가 있으면 그쪽" 이었는데,
        # 9-4 에서 노션 DB id 도 레지스트리에 들어오면서 그 규칙이 뒤집혔다: 저장한 적 없는
        # 키도 기본값(빈 문자열)으로 항상 존재하게 되어, env 로 설정을 마친 설치가
        # "설정 안 함" 으로 보고됐다. 빈 DB 값은 '아직 이 화면에서 안 건드림' 이라는 뜻이고
        # 그때 실제로 적용되는 값은 env 다.
        db_value: Any = _unwrap(eff[spec.key]) if spec.key in eff else None
        if _is_set(db_value):
            value: Any = db_value
            source = "settings"
        else:
            value = getattr(settings, spec.key, None)
            source = "env"
        items.append(
            {
                "key": spec.key,
                "label": spec.label,
                "env_var": spec.env_var,
                "source": source,
                "state": STATE_SET if _is_set(value) else STATE_UNSET,
                "when_unset": spec.when_unset,
            }
        )
    unset = [i for i in items if i["state"] == STATE_UNSET]
    return {
        "configured": not unset,
        "unset_count": len(unset),
        "items": items,
    }
