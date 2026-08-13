"""LLM 관리 화면의 판정 (9-5).

## 왜 이 화면이 생겼는가

`app/llm/provider.py::resolve_config` 는 이렇게 적혀 있었다: "지금 `Settings` 에 `llm_*`
필드가 없다. 필드가 생기면 이 함수를 고치지 않아도 그쪽이 이긴다. 없는 동안에는 환경변수로
켠다." 즉 AI 를 켜려면 서버의 env 파일을 고치고 재시작해야 했다.

그 필드를 만들었다(`app/core/config.py`). 이 화면이 저장하는 값은 설정 레지스트리를 지나
그 필드 위에 얹히고(`app/core/tenant_config.py::apply_overrides`), resolve_config 는 **한 줄도
고치지 않은 채** 그 값을 읽는다. 설계가 이미 그 길을 열어 두고 있었다.

## 빈 값은 '끔' 이 아니라 '안 정함' 이다

세 상태를 구분한다. `켬` / `끔` / `비움(환경변수를 따름)`. bool 로 두면 두 상태밖에 없고,
기본 `False` 가 곧바로 "끄기로 정했다" 로 읽힌다 - 그러면 이미 `LLM_ENABLED=1` 로 켜 둔
설치가 업그레이드하는 순간 조용히 꺼진다.

## 결과 어휘를 새로 만들지 않는다

`app/llm/provider.py` 의 `STATUS_*` 를 그대로 쓴다. 문구만 이 화면의 맥락으로 다시 쓴다 -
provider 의 문구는 전부 "규칙으로 만든 요약을 보여줍니다" 로 끝나는데, 연결 테스트에는
요약이 없다. 어휘가 갈라지면 언젠가 화면 두 개가 같은 상태를 다른 이름으로 부른다.
"""

from __future__ import annotations

from app.llm import cli_backend, provider
from app.llm.service import MAX_CONCURRENCY

# 감사 대상 이름. 한국어 라벨은 app/profiles/activity.py::OBJECT_LABELS 에 있다.
OBJECT_TYPE = "llm_config"

JOB_TYPE_TEST = "llm_connection_test"

# 연결 테스트의 **하드 상한**. 설정된 타임아웃이 이보다 길어도 테스트는 여기서 끊는다.
#
# 테스트는 "지금 통하는가" 를 묻는 것이지 요약을 만드는 것이 아니다. 통하면 몇 초 안에
# 답이 오고, 안 통하면 오래 기다려도 답은 같다. 상한을 안 두면 워커 한 칸이 설정된
# 타임아웃(최대 600초)만큼 잡히고, 그동안 잡 큐 전체가 밀린다.
TEST_TIMEOUT_SECONDS = 60

# 테스트에 넣는 본문. **사용자 데이터를 쓰지 않는다** - 진단 하나 하려고 남의 티켓 본문을
# 외부 모델에 보내는 일이 없어야 한다.
TEST_BODY = "연결 확인용 문장입니다. 한 문장으로 그대로 알겠다고 답해 주세요."

# provider 의 상태 어휘 -> 이 화면의 문장. 전부 "그래서 지금 무엇을 해야 하는가" 로 끝난다.
TEST_MESSAGES: dict[str, str] = {
    provider.STATUS_OK: "연결에 성공했습니다. AI 요약을 쓸 수 있습니다.",
    provider.STATUS_DISABLED: (
        "AI 기능이 꺼져 있어 호출하지 않았습니다. 위에서 사용 여부를 켬으로 바꾸고 다시 "
        "시도하세요."
    ),
    provider.STATUS_NOT_LOGGED_IN: (
        "명령줄 도구는 찾았지만 로그인되어 있지 않습니다. 서버에서 서비스 계정으로 로그인해야 "
        "합니다."
    ),
    provider.STATUS_TIMEOUT: (
        "제한 시간 안에 답이 오지 않았습니다. 제한 시간을 늘리거나 서버의 네트워크를 "
        "확인하세요."
    ),
    provider.STATUS_BUSY: (
        "다른 AI 호출이 진행 중이라 확인하지 못했습니다. 잠시 뒤 다시 시도하세요."
    ),
    provider.STATUS_MISSING_CLI: (
        "서버에서 명령줄 도구를 찾지 못했습니다. 실행 파일 이름이나 절대 경로를 확인하세요."
    ),
    provider.STATUS_UNCONFIGURED: (
        "백엔드 값이 올바르지 않아 무엇을 부를지 정할 수 없습니다. cli 또는 api 중 하나여야 "
        "합니다."
    ),
    provider.STATUS_EMPTY: (
        "호출은 됐지만 답이 비어 있었습니다. 모델 이름이 맞는지 확인하세요."
    ),
    provider.STATUS_FAILED: (
        "호출이 실패했습니다. 자세한 원인은 서버 로그에 남습니다."
    ),
}

FALLBACK_TEST_MESSAGE = "결과를 해석하지 못했습니다. 서버 로그를 확인하세요."


def test_message(status: str) -> str:
    return TEST_MESSAGES.get(status, FALLBACK_TEST_MESSAGE)


# 값이 바뀌면 언제 반영되는가. Notion 쪽(APPLY_NOTE)과 같은 이유로 두 층을 나눠 말한다.
APPLY_NOTE = (
    "저장하면 곧바로 반영됩니다. 백그라운드 워커는 다음 실행 주기부터 새 값을 씁니다. "
    "서비스를 다시 시작할 필요는 없습니다."
)

# 연결 테스트를 왜 이렇게 하는가. 화면이 이 문장을 그대로 보여 준다 - 사람이 버튼을 누른
# 뒤 결과가 바로 안 나오는 이유를 알아야 기다린다.
TEST_MODE_NOTE = (
    "연결 테스트는 작업 큐에 맡깁니다. 명령줄 도구 호출은 수십 초가 걸릴 수 있는데, 웹 요청에서 "
    "그만큼 기다리면 그 요청 처리 칸이 통째로 잠기고 다른 사람의 화면이 함께 느려집니다. "
    f"큐에 맡긴 뒤에도 {TEST_TIMEOUT_SECONDS}초를 넘기면 끊습니다. 결과는 이 화면이 이어서 "
    "확인합니다."
)


def login_guide(config: provider.LlmConfig, *, service_user: str = "clovirone-web") -> dict:
    """로그인 안내. 백엔드에 따라 **할 일이 완전히 다르다.**

    구독 명령줄 도구는 자격 증명을 **그 계정의 홈 디렉터리**에서 찾는다
    (`app/llm/cli_backend.py::child_env` 가 HOME 을 지우지 않는 이유가 그것이다).
    그래서 관리자 계정으로 로그인해 두고 "했다" 고 믿는 일이 실제로 생긴다 - 워커는
    서비스 계정으로 도는데 그 계정 홈에는 자격 증명이 없다.
    """
    if config.backend == provider.BACKEND_API:
        return {
            "backend": provider.BACKEND_API,
            "title": "API 키로 인증합니다",
            "steps": [
                "Anthropic 콘솔에서 API 키를 발급합니다.",
                "서버의 시크릿 디렉터리에 키 파일을 놓고 그 파일 이름을 "
                "LLM_API_SECRET_REF 환경변수에 적습니다.",
                "이 화면의 연결 테스트로 확인합니다.",
            ],
            "note": (
                "API 백엔드는 바깥으로 나가는 호출이라 SSRF 허용 목록의 승인도 따로 "
                "필요합니다. 허용 목록에 없으면 호출 자체가 막힙니다."
            ),
        }
    return {
        "backend": provider.BACKEND_CLI,
        "title": "서버에서 서비스 계정으로 로그인해야 합니다",
        "steps": [
            f"서버에 접속해 서비스 계정({service_user})으로 셸을 엽니다.",
            f"{config.executable} 명령을 실행하고 안내에 따라 구독 계정으로 로그인합니다.",
            "이 화면의 연결 테스트로 확인합니다.",
        ],
        "note": (
            "관리자 계정으로 로그인하면 안 됩니다. 자격 증명은 로그인한 계정의 홈 디렉터리에 "
            "저장되는데, 백그라운드 워커는 서비스 계정으로 돌기 때문에 그 자격 증명을 보지 "
            "못합니다. 로그인이 안 된 상태에서도 도구는 정상 종료처럼 답하므로, 반드시 연결 "
            "테스트로 확인하세요."
        ),
    }


def _source_of(settings, effective: dict, key: str) -> str:
    """지금 적용 중인 값이 어디서 왔는가. 화면이 '무엇을 고쳐야 하는가' 를 말하려면 필요하다.

    UA-28: 예전엔 저장된 값의 타입/참값으로 짐작했다(문자열이 비어있지 않은가 · bool이
    아닌 정수이면서 0이 아닌가) — `llm_enabled`처럼 bool로 저장한 값(예: 사용 여부를
    명시적으로 끔)과 정수 0을 저장한 값이 전부 "settings"가 아니라 "env"로 잘못
    분류됐다. `effective_settings()`가 이미 이 물음("저장 행이 있고 그 값이 레지스트리
    기본값과 다른가")에 정확히 답하는 `is_default`를 계산해 두므로 그걸 그대로 쓴다
    (`SettingEditor.jsx` 등 다른 설정 화면이 이미 같은 신호를 쓴다 — 판정 방식을 두
    벌로 만들지 않는다). `llm_timeout_seconds`의 "0=env를 따름" 센티널 규약
    (`tenant_config.py::_override_is_set`)과도 저절로 맞아떨어진다 — 그 값 자체가
    레지스트리 기본값이라 `is_default`가 이미 참이 되고, 따로 처리할 필요가 없다.
    """
    raw = effective.get(key)
    if isinstance(raw, dict) and "is_default" in raw:
        return "env" if raw["is_default"] else "settings"
    return "env"


# 화면이 편집하는 설정 키와 라벨. 레지스트리에 있는 키만 적는다 - 여기 없는 키를 화면이
# 그리면 저장 버튼이 422 를 받는다.
EDITABLE_KEYS: tuple[tuple[str, str], ...] = (
    ("llm_enabled", "사용 여부"),
    ("llm_backend", "백엔드"),
    ("llm_executable", "실행 파일"),
    ("llm_model", "모델"),
    ("llm_timeout_seconds", "제한 시간(초)"),
    ("llm_max_concurrency", "동시 실행 수"),
)


def overview(settings, effective: dict) -> dict:
    """화면 한 판. **외부 호출도 프로세스 실행도 하지 않는다.**

    `resolve_config` 는 설정만 읽는다(프로세스를 띄우지 않는다). 실제로 통하는지는 사람이
    연결 테스트를 눌러야 알 수 있고, 그 사실을 화면이 말해야 한다 - 여기 초록불을 그리면
    "설정은 됐는데 안 된다" 가 다시 생긴다.
    """
    config = provider.resolve_config(settings)
    return {
        "config": {
            "enabled": config.enabled,
            "backend": config.backend,
            "executable": config.executable,
            "model": config.model,
            "timeout_seconds": cli_backend.clamp_timeout(config.timeout_seconds),
            "max_concurrency": max(
                1, min(MAX_CONCURRENCY, int(getattr(settings, "llm_max_concurrency", 1) or 1))
            ),
        },
        # UA-28: backend가 cli/api 둘 다 아니면 resolve_config가 enabled를 강제로 꺼서
        # 돌려준다(오타를 조용히 cli로 읽지 않으려는 안전장치, provider.py 주석 참고) —
        # 그런데 화면은 그 결과만 보고 "꺼짐" 배지를 그려, 사용 여부를 직접 껐다고 착각하게
        # 만든다. 진짜 원인(백엔드 값이 잘못됨)을 화면이 따로 말할 수 있게 신호를 싣는다.
        "backend_invalid": config.backend not in {provider.BACKEND_CLI, provider.BACKEND_API},
        "limits": {
            "min_timeout_seconds": cli_backend.MIN_TIMEOUT_SECONDS,
            "max_timeout_seconds": cli_backend.MAX_TIMEOUT_SECONDS,
            "max_concurrency": MAX_CONCURRENCY,
            "test_timeout_seconds": TEST_TIMEOUT_SECONDS,
        },
        # 각 값이 화면에서 저장한 것인지 서버 환경변수인지. 화면이 이걸 옆에 붙여 줘야
        # "저장했는데 왜 안 바뀌지" 의 답이 화면 안에 있게 된다.
        "sources": {key: _source_of(settings, effective, key) for key, _label in EDITABLE_KEYS},
        "login": login_guide(config),
        "apply_note": APPLY_NOTE,
        "test_mode_note": TEST_MODE_NOTE,
        "verified": False,
        "verified_note": (
            "이 화면은 설정값만 보여 줍니다. 실제로 통하는지는 연결 테스트를 눌러야 알 수 "
            "있습니다."
        ),
    }


__all__ = [
    "APPLY_NOTE",
    "EDITABLE_KEYS",
    "JOB_TYPE_TEST",
    "OBJECT_TYPE",
    "TEST_BODY",
    "TEST_MESSAGES",
    "TEST_MODE_NOTE",
    "TEST_TIMEOUT_SECONDS",
    "login_guide",
    "overview",
    "test_message",
]
