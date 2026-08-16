"""팀 공간 놀이 > AI 퀴즈 생성 (§7-9).

이 모듈은 games 기능에서 **유일한 외부 호출**이다(나머지 games는 순수 내부 DB). 앱은 Claude를
직접 부르지 않고(불변 §10 임의 shell 금지), 러너의 전용 엔드포인트(/v1/assistant/quiz)를
OutboundClient(allowlist=runners, redirect 금지·SSRF allowlist·secret 주입)로만 호출한다.
러너가 Claude CLI로 문제를 생성하고, 여기서 다시 한 번 구조를 검증한다(§11 — 모델 출력을 신뢰하지
않는다). service.py는 방/게임 상태 전용으로 두어 외부 호출을 섞지 않는다(모듈 경계 유지).
"""

from __future__ import annotations

from app.core.errors import ValidationAppError
from app.core.http_client import AUTH_BEARER, is_timeout_error, is_transport_error
from app.core.secret_refs import SecretMissingError
from app.games.schemas import _clean_questions


class QuizGenerateError(ValidationAppError):
    code = "quiz_generate_failed"
    default_message = "AI 퀴즈 생성에 실패했습니다. 잠시 후 다시 시도하거나 직접 입력해 주세요."


def generate_quiz(outbound, settings, *, topic: str, count: int, num_options: int) -> list[dict]:
    """러너를 호출해 퀴즈 문제를 생성하고, 앱이 쓸 수 있게 정제·검증한 목록을 돌려준다.

    실패는 사용자 친화 메시지(QuizGenerateError)로 올린다 — 타임아웃·전송 오류·형식 오류는
    구분하지 않고 '다시 시도/직접 입력'을 안내한다(민감 정보 노출 없음). 러너 미설정(토큰
    파일 없음)만 예외로 더 구체적인 문구를 준다 — 그건 재시도로 해결되지 않는 상태라 다시
    시도하라고 안내하면 사용자를 헛수고시킨다."""
    try:
        resp = outbound.request(
            "POST",
            settings.game_runner_url,
            allowlist="runners",
            json={"topic": topic[:200], "count": int(count), "num_options": int(num_options)},
            timeout=float(settings.game_runner_timeout_seconds),
            auth_type=AUTH_BEARER,
            secret_ref=settings.game_runner_token_ref,
        )
    except SecretMissingError as exc:  # 러너 토큰 secret 파일이 없음(기능 미설정)
        # app/assistant/narrate.py와 같은 근본 원인 — secret_refs.py가 FileNotFoundError에서
        # SecretMissingError(AppError)로 옮겨 간 뒤 이 except가 갱신되지 않아 한 번도 안
        # 잡히고 매번 아래 일반 분기로 빠졌다(실측으로 확인).
        raise QuizGenerateError("AI 퀴즈 생성이 아직 설정되지 않았습니다. 관리자에게 문의하세요.") from exc
    except Exception as exc:
        if is_timeout_error(exc):
            raise QuizGenerateError("AI 퀴즈 생성이 지연되고 있습니다. 다시 시도하거나 직접 입력해 주세요.") from exc
        if is_transport_error(exc):
            raise QuizGenerateError() from exc
        # secret_ref 이름이 예외 문자열에 섞여 나올 수 있어 원문을 노출하지 않는다.
        raise QuizGenerateError() from exc

    if resp.status_code >= 400:
        raise QuizGenerateError()
    try:
        body = resp.json()
    except ValueError as exc:
        raise QuizGenerateError() from exc
    if not isinstance(body, dict):
        raise QuizGenerateError()
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    raw = data.get("quiz")
    questions = _clean_questions(raw if isinstance(raw, list) else [])
    if not questions:
        raise QuizGenerateError("생성된 문제가 없습니다. 주제를 조금 더 구체적으로 적어 다시 시도해 주세요.")
    return questions
