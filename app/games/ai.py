"""팀 공간 놀이 > AI 퀴즈 생성 (§7-9). **모델로 가는 문은 Gateway 하나다** (S11 · D-201).

예전에는 러너(`127.0.0.1:8789/v1/assistant/quiz`)를 직접 불렀고, 러너가 Claude CLI 로
문제를 만들어 JSON 으로 돌려줬다. S11 이 그 러너를 걷어내면서 `Gateway.generate()` 로
옮겼다 — 이제 주제 문자열이 `data` 로 넘어가므로 난스 구분자 안에 갇힌다(D-202). 사용자가
주제 칸에 「앞의 지시를 무시하고…」를 적어도 그것은 문제로 만들 내용이지 따를 지시가 아니다.

바뀌지 않은 것이 하나 있고 그것이 이 파일이 계속 존재하는 이유다: **모델 출력을 신뢰하지
않는다**(§11). 러너가 JSON 을 보장하던 시절에도 여기서 다시 검증했고, 지금은 모델이 글로
답하므로 검증이 더 필요하다. `_clean_questions` 가 구조·범위를 강제한다.
"""

from __future__ import annotations

import json
import re

from app.ai.gateway import contract
from app.core.errors import ValidationAppError
from app.games.schemas import _clean_questions

#: **우리가 쓴 문장만 여기 있다.** 주제는 `data` 로 따로 간다.
TASK = "\n".join([
    "아래 주제로 한국어 객관식 퀴즈를 만들어 주세요.",
    "답은 JSON 배열 하나로만 쓰고, 배열 앞뒤에 다른 글을 붙이지 마세요.",
    '각 항목은 {"q": 문제, "options": [보기, ...], "answer": 정답 보기의 0부터 세는 번호} 입니다.',
    "보기는 서로 다르게 쓰고, 정답 번호는 반드시 보기 범위 안에 있어야 합니다.",
])

#: 모델이 ```json 울타리를 붙여 답하는 경우가 흔하다. 울타리는 내용이 아니므로 걷어낸다.
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class QuizGenerateError(ValidationAppError):
    code = "quiz_generate_failed"
    default_message = "AI 퀴즈 생성에 실패했습니다. 잠시 후 다시 시도하거나 직접 입력해 주세요."


def _parse(text: str) -> list:
    """모델이 쓴 글에서 문제 배열을 꺼낸다. 못 꺼내면 빈 목록이다.

    통째로 JSON 이 아닐 수 있어(앞뒤에 인사말이 붙는다) 첫 `[` 부터 마지막 `]` 까지를
    한 번 더 시도한다. 그래도 안 되면 **지어내지 않는다** — 빈 목록이 곧 실패다.
    """
    body = _FENCE.sub("", text or "").strip()
    for candidate in (body, body[body.find("["): body.rfind("]") + 1] if "[" in body else ""):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            parsed = parsed.get("quiz") or parsed.get("questions")
        if isinstance(parsed, list):
            return parsed
    return []


def generate_quiz(gateway, settings, *, topic: str, count: int, num_options: int) -> list[dict]:
    """모델을 불러 퀴즈 문제를 생성하고, 앱이 쓸 수 있게 정제·검증한 목록을 돌려준다.

    실패는 사용자 친화 메시지(QuizGenerateError)로 올린다. 「아직 설정되지 않았다」만
    따로 구분한다 — 그건 재시도로 해결되지 않는 상태라 다시 시도하라고 안내하면 사용자를
    헛수고시킨다. 나머지(시간 초과·다른 작업 중·형식 오류)는 다시 시도할 값이 있다.
    """
    request = {
        "topic": topic[:200],
        "count": int(count),
        "num_options": int(num_options),
    }
    result = gateway.generate(
        task=TASK, data=json.dumps(request, ensure_ascii=False)
    )
    if not result.ok:
        if result.status in (contract.STATUS_UNCONFIGURED, contract.STATUS_DISABLED,
                             contract.STATUS_MODEL_MISSING, contract.STATUS_RUNTIME_MISSING,
                             contract.STATUS_UNSUPPORTED, contract.STATUS_NOT_LOGGED_IN):
            raise QuizGenerateError(
                f"{result.notice or contract.FALLBACK_NOTICE} 관리자에게 문의하세요."
            )
        raise QuizGenerateError()

    questions = _clean_questions(_parse(result.text))
    if not questions:
        raise QuizGenerateError("생성된 문제가 없습니다. 주제를 조금 더 구체적으로 적어 다시 시도해 주세요.")
    return questions
