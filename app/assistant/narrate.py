"""사실 → 문장. **모델로 가는 문은 Gateway 하나다** (S11 · D-201 · D-202).

예전에는 이 파일이 러너(`127.0.0.1:8789/v1/assistant/summarize`)를 직접 불렀다. S11 이
그 러너를 걷어내면서 `Gateway.generate(task=, data=)` 로 옮겼다 — 저장소에 생성 경로를
두 벌 두지 않는다는 D-201 의 결론 그대로다. 부수 효과가 하나 있고 그것이 이 이전의 값이다:
사실 dict 가 `data` 로 넘어가므로 **난스 구분자 안에 갇히고 구분자 흉내가 걷어내진다**
(D-202). 러너 시절에는 그 방어가 이 경로에 안 걸려 있었다.

설계의 핵심은 그대로 한 줄이다: **이 파일은 절대 예외를 밖으로 던지지 않는다.** 계획서
Phase 5 요구사항 — *"러너가 죽어도 숫자는 그대로 보여야 한다(문장만 빠진다)"* — 를 구조로
보장하기 위해서다. 실패는 전부 {"text": None, "error": ...} 로 접힌다. 호출측(router)은
사실 dict 에 이 결과를 덧붙이기만 하므로, 모델 상태와 무관하게 숫자 필드는 언제나 그대로
나간다. `Gateway.generate()` 도 같은 규약이라(실패를 예외가 아니라 값으로 돌려준다) 두
계약이 어긋나는 자리가 없다.

기본은 꺼져 있다(feature flag `assistant_narrative_enabled`, fail-closed). 켜지 않으면
모델을 부르지도 않고 `enabled: false` 만 붙는다.

모델 출력은 신뢰하지 않는다(§11): 문자열인지, 길이는 얼마인지, 제어문자는 없는지 검사한 뒤
통과시킨다.
"""

from __future__ import annotations

import json
import logging

from app.ai.gateway import contract
from app.core.feature_flags import load_feature_flags

logger = logging.getLogger("app.assistant.narrate")

FLAG = "assistant_narrative_enabled"

# 사람이 화면 상단에서 한눈에 읽는 분량. 모델이 장문을 보내도 여기서 자른다.
MAX_TEXT_CHARS = 1200

#: **우리가 쓴 문장만 여기 있다.** 사실 dict 는 `data` 로 따로 간다 — 섞는 순간 그 값이
#: 지시가 된다(D-202).
TASK = "\n".join([
    "아래는 화면에 이미 표시된 숫자입니다.",
    "이 숫자만 근거로 오늘 무엇을 먼저 보면 되는지 한국어로 세 문장 이내로 알려 주세요.",
    "숫자를 새로 계산하거나 없는 값을 만들지 마세요.",
    "제목이나 목록 없이 문장으로만 씁니다.",
])

# 실패 사유는 사용자에게 보여줄 수 있는 짧은 한국어로만 나간다.
_ERR_DISABLED = "요약 문장 생성이 꺼져 있습니다(숫자는 그대로 표시됩니다)."
_ERR_EMPTY = "요약 문장이 비어 있어 숫자만 표시합니다."


def is_enabled(settings) -> bool:
    return bool(load_feature_flags(settings.config_dir).get(FLAG, False))


def disabled_result() -> dict:
    """기능이 꺼져 있을 때의 narrative 블록. 모델을 부르지 않는다."""
    return {"enabled": False, "text": None, "error": _ERR_DISABLED}


def _clean(value) -> str | None:
    """모델이 준 값을 화면에 실을 수 있는 문자열로 정제한다. 아니면 None."""
    if not isinstance(value, str):
        return None
    # 제어문자(줄바꿈/탭 제외)는 버린다 — 터미널 이스케이프가 로그·화면으로 새는 경로를 막는다.
    text = "".join(c for c in value if c in "\n\t" or c.isprintable()).strip()
    return text[:MAX_TEXT_CHARS] if text else None


def narrate(gateway, settings, *, kind: str, facts: dict, requester: dict) -> dict:
    """사실 dict → {"enabled", "text", "error"}. **절대 예외를 던지지 않는다.**

    모델에는 이미 계산된 사실만 보낸다 — 원본 티켓 목록 전체나 사용자 식별자를 넘기지
    않는다. 모델이 숫자를 다시 세지 않으므로, 문장이 화면의 숫자와 어긋날 여지가 구조적으로
    없다(모델은 우리가 준 값을 문장으로 옮기기만 한다).
    """
    if not is_enabled(settings):
        return disabled_result()

    payload = {
        "kind": kind,
        "requester": requester.get("display_name") or "",
        # 사실은 그대로 넘긴다. 지시문이 "여기 있는 숫자만 쓰라"고 가리키는 대상이다.
        "facts": facts,
    }
    try:
        result = gateway.generate(
            task=TASK, data=json.dumps(payload, ensure_ascii=False, default=str)
        )
    except Exception:  # noqa: BLE001 — 어떤 실패든 숫자는 살아야 한다(계획서 Phase 5)
        # Gateway 는 실패를 값으로 돌려주는 계약이라 여기 오면 안 된다. 그래도 남겨 둔다 —
        # 이 함수의 계약은 「예외를 안 던진다」이고, 그 계약이 Gateway 의 계약에 기대면
        # 언젠가 어댑터 하나가 그것을 깨는 날 화면의 숫자가 함께 사라진다.
        logger.exception("assistant narrate 가 예상 못 한 예외를 냈다 (kind=%s)", kind)
        return {"enabled": True, "text": None,
                "error": contract.notice_for(contract.STATUS_FAILED)}

    if not result.ok:
        # 「안 됩니다」만 남기지 않는다 — 운영자가 고칠 수 있는 상태(모델 파일을 안 넣었다)와
        # 못 고치는 상태를 Gateway 의 상태 어휘가 이미 구별해 둔다.
        logger.warning("assistant narrate 실패 (kind=%s status=%s)", kind, result.status)
        return {"enabled": True, "text": None,
                "error": result.notice or contract.FALLBACK_NOTICE}

    text = _clean(result.text)
    if text is None:
        return {"enabled": True, "text": None, "error": _ERR_EMPTY}
    return {"enabled": True, "text": text, "error": None}
