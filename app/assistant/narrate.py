"""사실 → 문장. **여기만 러너를 부른다.**

저장소 불변 §2: 앱은 Claude/LLM API 를 직접 부르지 않는다. 팀 공간 놀이의 AI 퀴즈
(app/games/ai.py)와 **같은 경로**를 쓴다 — OutboundClient(allowlist="runners", redirect 금지,
SSRF allowlist, secret 주입)로 러너의 전용 엔드포인트를 부르고, 러너가 Claude 를 실행한다.
새 외부 호출 관문을 만들지 않는다.

설계의 핵심은 한 줄이다: **이 파일은 절대 예외를 밖으로 던지지 않는다.** 계획서 Phase 5
요구사항 — *"러너가 죽어도 숫자는 그대로 보여야 한다(문장만 빠진다)"* — 를 구조로 보장하기
위해서다. 실패는 전부 {"text": None, "error": ...} 로 접힌다. 호출측(router)은 사실 dict 에
이 결과를 덧붙이기만 하므로, 러너 상태와 무관하게 숫자 필드는 언제나 그대로 나간다.

기본은 꺼져 있다(feature flag `assistant_narrative_enabled`, fail-closed). 켜지 않으면
러너를 부르지도 않고 `enabled: false` 만 붙는다 — 설정 안 한 설치에서 매 요청마다 연결
거부를 기다리는 일이 없다.

모델 출력은 신뢰하지 않는다(§11): 문자열인지, 길이는 얼마인지, 제어문자는 없는지 검사한 뒤
통과시킨다.
"""

from __future__ import annotations

import logging

from app.core.feature_flags import load_feature_flags
from app.core.http_client import AUTH_BEARER, is_timeout_error, is_transport_error
from app.core.secret_refs import SecretMissingError

logger = logging.getLogger("app.assistant.narrate")

FLAG = "assistant_narrative_enabled"

# 사람이 화면 상단에서 한눈에 읽는 분량. 러너가 장문을 보내도 여기서 자른다.
MAX_TEXT_CHARS = 1200

# 러너 응답에서 문장을 찾을 키(우선순위 순). chat_message 핸들러의 _TEXT_KEYS 와 같은 발상.
_TEXT_KEYS = ("text", "narrative", "summary", "response_text", "reply", "message", "output")

# 실패 사유는 사용자에게 보여줄 수 있는 짧은 한국어로만 나간다(러너 주소·secret_ref 미노출).
_ERR_DISABLED = "요약 문장 생성이 꺼져 있습니다(숫자는 그대로 표시됩니다)."
_ERR_UNCONFIGURED = "요약 문장 생성이 아직 설정되지 않았습니다(숫자는 그대로 표시됩니다)."
_ERR_TIMEOUT = "요약 문장 생성이 지연되어 숫자만 표시합니다."
_ERR_UNAVAILABLE = "요약 문장을 만들지 못해 숫자만 표시합니다."
_ERR_EMPTY = "요약 문장이 비어 있어 숫자만 표시합니다."


def is_enabled(settings) -> bool:
    return bool(load_feature_flags(settings.config_dir).get(FLAG, False))


def disabled_result() -> dict:
    """기능이 꺼져 있을 때의 narrative 블록. 러너를 부르지 않는다."""
    return {"enabled": False, "text": None, "error": _ERR_DISABLED}


def _clean(value) -> str | None:
    """러너가 준 값을 화면에 실을 수 있는 문자열로 정제한다. 아니면 None."""
    if not isinstance(value, str):
        return None
    # 제어문자(줄바꿈/탭 제외)는 버린다 — 터미널 이스케이프가 로그·화면으로 새는 경로를 막는다.
    text = "".join(c for c in value if c in "\n\t" or c.isprintable()).strip()
    return text[:MAX_TEXT_CHARS] if text else None


def _extract(body) -> str | None:
    """{"data": {...}} 로 감싸 오는 러너 규약과 평평한 응답을 모두 받는다."""
    if not isinstance(body, dict):
        return None
    scopes = [body]
    if isinstance(body.get("data"), dict):
        scopes.insert(0, body["data"])
    for scope in scopes:
        for key in _TEXT_KEYS:
            text = _clean(scope.get(key))
            if text:
                return text
    return None


def narrate(outbound, settings, *, kind: str, facts: dict, requester: dict) -> dict:
    """사실 dict → {"enabled", "text", "error"}. **절대 예외를 던지지 않는다.**

    러너에는 이미 계산된 사실만 보낸다 — 원본 티켓 목록 전체나 사용자 식별자를 넘기지
    않는다. 러너가 숫자를 다시 세지 않으므로, 문장이 화면의 숫자와 어긋날 여지가 구조적으로
    없다(러너는 우리가 준 값을 문장으로 옮기기만 한다).
    """
    if not is_enabled(settings):
        return disabled_result()

    payload = {
        "kind": kind,
        "locale": "ko-KR",
        "requester": {"name": requester.get("display_name") or "", "user_id": requester.get("user_id")},
        # 사실은 그대로 넘긴다. 러너 프롬프트가 "여기 있는 숫자만 쓰라"고 지시하는 대상이다.
        "facts": facts,
    }
    try:
        response = outbound.request(
            "POST",
            settings.assistant_runner_url,
            allowlist="runners",
            json=payload,
            timeout=float(settings.assistant_runner_timeout_seconds),
            auth_type=AUTH_BEARER,
            secret_ref=settings.assistant_runner_token_ref,
        )
    except SecretMissingError:  # 러너 토큰 secret 파일 없음 = 기능 미설정
        # secret_refs.py가 SecretMissingError(AppError)로 옮겨 간 뒤 이 except가 갱신되지
        # 않았다 — FileNotFoundError는 이제 여기서 안 올라온다(실측: 이 갈래가 한 번도
        # 안 잡히고 매번 아래 except Exception → _ERR_UNAVAILABLE로 빠졌다). 사용자에게는
        # "지연/실패"와 "아직 설정 안 됨"이 다른 문구라 실제로 갈라져야 한다.
        return {"enabled": True, "text": None, "error": _ERR_UNCONFIGURED}
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 숫자는 살아야 한다(계획서 Phase 5)
        if is_timeout_error(exc):
            logger.warning("assistant narrate timeout (kind=%s)", kind)
            return {"enabled": True, "text": None, "error": _ERR_TIMEOUT}
        if is_transport_error(exc):
            logger.warning("assistant narrate transport failure (kind=%s)", kind)
            return {"enabled": True, "text": None, "error": _ERR_UNAVAILABLE}
        # secret_ref 이름이 예외 문자열에 섞여 나올 수 있어 원문을 사용자에게 노출하지 않는다.
        logger.warning("assistant narrate failed (kind=%s): %s", kind, type(exc).__name__)
        return {"enabled": True, "text": None, "error": _ERR_UNAVAILABLE}

    if response.status_code >= 400:
        logger.warning("assistant narrate HTTP %s (kind=%s)", response.status_code, kind)
        return {"enabled": True, "text": None, "error": _ERR_UNAVAILABLE}
    try:
        body = response.json()
    except ValueError:
        return {"enabled": True, "text": None, "error": _ERR_UNAVAILABLE}

    text = _extract(body)
    if text is None:
        return {"enabled": True, "text": None, "error": _ERR_EMPTY}
    return {"enabled": True, "text": text, "error": None}
