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
# ⚠️ 이 목록과 아래 OVERRIDABLE_KEYS 는 **다른 목적의 다른 목록**이다 - 셋 중 둘(노션 DB
# id 둘)만 겹친다. `allowed_email_domains` 가 여기에만 있고 저기엔 없는 이유는 취향이
# 아니라 **타입이 안 맞기 때문**이다: `Settings.allowed_email_domains` 는 `str`(콤마
# 구분)인데 레지스트리 값은 `list`(registry.py:264) 다. `apply_overrides` 는
# `setattr(settings, key, target)` 을 그대로 하므로, 이 키를 OVERRIDABLE_KEYS 에 넣으면
# `Settings` 필드에 리스트가 얹히고 - `validate_assignment` 가 없어 그 대입은 **조용히
# 성공**한 뒤 나중에 `allowed_email_domain_list`(config.py:170, `.split(",")` 를 부르는 곳)
# 에서 `AttributeError`(list 에는 `.split` 이 없다) 로 터진다. 이 키를 오버레이에 추가하려면
# 먼저 양쪽 타입을 맞춰야 한다.
TENANT_SETTINGS: tuple[TenantSetting, ...] = (
    TenantSetting(
        key="notion_tasks_database_id",
        label="노션 작업 데이터베이스",
        env_var="NOTION_TASKS_DATABASE_ID",
        when_unset="티켓 목록과 개발자 리포트가 채워지지 않습니다. 노션 작업 데이터베이스 id 를 넣으세요.",
    ),
    TenantSetting(
        key="notion_documents_database_id",
        label="노션 문서 데이터베이스",
        env_var="NOTION_DOCUMENTS_DATABASE_ID",
        when_unset="팀 공간 문서 목록이 채워지지 않습니다. 노션 문서 데이터베이스 id 를 넣으세요.",
    ),
    TenantSetting(
        key="allowed_email_domains",
        label="계정 생성 허용 도메인",
        env_var="ALLOWED_EMAIL_DOMAINS",
        when_unset="새 계정을 만들 때 이메일 도메인을 제한하지 않습니다. 기존 사용자의 로그인은 영향받지 않습니다.",
    ),
)

STATE_SET = "set"
STATE_UNSET = "unset"


# ── 관리 콘솔에서 바꾼 값을 살아 있는 Settings 에 덮어쓰는 목록 (9-4, 9-5) ────
#
# ## 왜 필요한가
#
# 이 값들의 **소비자는 전부 `settings.<key>` 를 읽는다**(app/reports/notion_source.py,
# app/team_docs/notion_docs.py, app/tickets/*, app/llm/provider.py::resolve_config).
# 그래서 DB 설정만 바꾸면 화면에는 새 값이 보이는데 실제 조회는 옛 값으로 나간다 -
# 이 저장소가 가장 싫어하는 종류의 거짓말이다("설정했다는데 안 된다").
#
# 소비자를 전부 고쳐 캐시를 읽게 만드는 길도 있지만, 그러면 판정이 소비자 수만큼 흩어진다.
# 대신 **한 곳**에서 살아 있는 Settings 객체에 값을 얹는다. `SettingsCache.load()` 가
# 이 함수를 부르고, 그 load 는 웹 부팅 - 워커 부팅 - 설정 저장 - 워커의 60초 재적재 틱
# (worker_main.py::settings_cache_tick)마다 돈다. 즉 두 프로세스가 최대 60초 안에 같은
# 값으로 수렴한다.
#
# 이 목록과 위 TENANT_SETTINGS 가 다른 목적의 다른 목록인 이유는 그 목록 위 주석에 적었다.
# ## 왜 빈 값은 덮지 않고 **원래 값으로 되돌리는가**
#
# 레지스트리 기본값이 빈 문자열이다(= 아직 이 화면에서 저장한 적 없음). 빈 값까지 덮으면
# **env 로 설정해 둔 기존 설치가 업그레이드하는 순간 통째로 미설정이 된다.**
#
# 그래서 빈 값은 "덮지 않는다" 가 아니라 **"원래 값(부팅 시점의 env 값)으로 되돌린다"** 다.
# 처음에는 '덮지 않는다' 로 만들었는데, 그러면 화면에서 값을 넣었다가 지웠을 때 지운 값이
# 그대로 남는다 - 화면은 "환경변수 값을 씁니다" 라고 말하면서 실제로는 방금 지운 값으로
# 조회한다. 테스트가 그것을 잡았다. 그래서 첫 load 에서 원래 값을 기억해 둔다.
OVERRIDABLE_KEYS: tuple[str, ...] = (
    "notion_tasks_database_id",
    "notion_documents_database_id",
    "notion_sprint_database_id",
    "llm_enabled",
    "llm_backend",
    "llm_model",
    "llm_executable",
    "llm_timeout_seconds",
    "llm_max_concurrency",
)


def _override_is_set(value: Any) -> bool:
    """오버레이에서 '값이 정해졌다' 고 볼 수 있는가.

    `_is_set` 과 **한 군데 다르다**: 숫자 0 을 '안 정함' 으로 본다.

    이유: `llm_timeout_seconds` 의 레지스트리 기본값 0 은 "환경변수나 기본값을 따른다"는
    센티널이다(app/settings/registry.py::_llm_timeout). 그런데 `_is_set(0)` 은 True 다.
    그대로 쓰면 **아무도 손대지 않은 설치에서 0 이 얹혀** env 의 `LLM_TIMEOUT_SECONDS` 가
    조용히 무시된다 - 화면에는 아무 표시도 안 난다. `_is_set` 자체를 고치지 않는 이유:
    그 함수는 진단의 '설정 안 함' 판정에도 쓰이고, 거기서는 0 의 뜻이 다르다.

    ⚠️ 이 목록의 숫자 키가 `llm_timeout_seconds` 뿐이라는 전제는 **더 이상 사실이 아니다**
    (`llm_max_concurrency` 도 숫자이고 OVERRIDABLE_KEYS 에 있다). 그 키의 레지스트리
    기본값은 1(센티널이 아니라 **실제 값** - "동시 실행 1개"). 그래서 이 함수는
    `llm_max_concurrency` 를 **아무도 손대지 않아도 매 재적재마다 1로 얹는다** - env 의
    `LLM_MAX_CONCURRENCY` 를 설정해 둔 설치라면 그 값이 조용히 무시된다. 실노출은 좁다
    (어느 env 템플릿에도 이 변수가 없는, 비문서 노브다) - 같은 비대칭이 화면에도 있어
    `SYS-08`(docs/BACKLOG.md)로 추적한다. 두 숫자 키가 "0=센티널" 규약을 공유하게 만들거나,
    센티널 판정을 값이 아니라 "DB 행이 있는가"로 바꾸는 것이 근본 수정이다.
    """
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)) and value == 0:
        return False
    return _is_set(value)


def apply_overrides(settings, values: dict, baseline: dict | None = None) -> list[str]:
    """DB 설정 값을 `settings` 에 얹는다. 실제로 바꾼 키 이름을 돌려준다.

    `baseline` 은 **부팅 시점의 env 값**을 담는 dict 다. 제자리에서 채워 넣으므로 부르는
    쪽(SettingsCache)은 같은 dict 를 계속 넘기기만 하면 된다. 첫 호출에서 채워지고,
    그 뒤로는 "DB 값이 비었으면 여기로 되돌린다" 의 기준이 된다.

    `settings` 가 None 이면 아무것도 안 한다(테스트가 Settings 없이 캐시만 쓰는 경우).
    """
    if settings is None:
        return []
    if baseline is None:
        baseline = {}
    changed: list[str] = []
    for key in OVERRIDABLE_KEYS:
        if not hasattr(settings, key):
            # Settings 에 없는 필드는 얹을 자리가 없다. 배선 실수지만 부팅을 죽이지는 않는다.
            continue
        if key not in baseline:
            baseline[key] = getattr(settings, key)
        db_value = _unwrap(values.get(key))
        target = db_value if _override_is_set(db_value) else baseline[key]
        if getattr(settings, key, None) == target:
            continue
        try:
            setattr(settings, key, target)
        except (AttributeError, ValueError, TypeError):
            # 타입이 안 맞으면 조용히 넘긴다. 레지스트리 검증기가 모양을 이미 봤으므로
            # 여기까지 오는 것은 배선 실수뿐인데, 그것 때문에 부팅이 죽으면 설정 하나가
            # 서버 전체를 못 뜨게 만든다.
            continue
        changed.append(key)
    return changed


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
        # 그때 실제로 적용되는 값은 env 다(app/core/tenant_config.py::apply_overrides).
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
