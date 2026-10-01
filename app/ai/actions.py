"""AI 가 하는 일의 목록 — **액션 레지스트리** (계획 3.9 · 3.13, D-515).

## 왜 목록으로 두는가

생성 호출은 여러 화면에서 나간다(채팅, 작업 공간의 질문과 초안, 주간 요약, 홈 요약, 퀴즈, 연결 확인). 예전에는
호출마다 출력 길이, 한도 적용 여부, JSON 여부가 제각각이었고, 요약용 한 틀과 2,000자 절단이 문서 초안까지
잘랐다. 이제 모든 호출이 이 표의 액션 하나를 이름으로 대고 런타임(`app/ai/runtime.py`)이 그 값대로 처리한다.
사용 한도(3.10), 사용 기록(3.11), 프롬프트 슬롯(3.8), 정책(3.9)도 이 이름으로 묶인다.

## 값의 뜻

  kind              `read` 는 읽고 답만 한다. `write` 는 결과가 저장된다(문서 초안, 주간 요약)
  counts_quota      사람이 부른 호출이라 AI 사용 한도에 센다. 연결 확인은 관리 동작이라 세지 않는다
  max_output_chars  화면에 싣는 글의 상한. 넘으면 자르고 `truncated` 를 단다
  json_output       JSON 을 돌려받는 액션. **자르지 않는다** - 자른 JSON 은 쓸 수 없으니 넘으면 실패다
  max_output_tokens Provider 에 넘기는 출력 한도(요금제 연결처럼 넘길 수 없는 경로는 무시된다)
  supports_approval 정책이 승인을 요구할 수 있는 쓰기(3.9)
  prompt_slot       지시문을 고르는 사용처(`app/ai/prompts/catalog.py`, D-518)
  tools             제공자에 도구를 건네는 액션(`AiRuntime.converse`, D-535). AI 도우미 하나뿐이다 — 다른 단발 기능은
                    도구 없는 `generate()` 를 그대로 쓴다
  retired           더는 부르지 않는 액션. 지난 사용 기록의 이름과 그날의 한도 셈이 이어지도록 표에 남긴다. 정책의 대상으로
                    고를 수 없다

## AI 도우미 (D-535)

채팅과 작업 공간의 「물어보기」는 예전에 `chat.answer` · `workspace.ask` 두 액션이었고, 근거를 못 찾으면 모델을 부르지
않았다. 이제 둘 다 `assistant.chat` 한 액션이다 — 권한 범위의 읽기 도구를 쓰는 대화이고, 한 차례가 사용 기록 한 행 ·
한도 한 칸이다(D-537). 옛 두 이름은 은퇴했다.
"""

from __future__ import annotations

from dataclasses import dataclass

KIND_READ = "read"
KIND_WRITE = "write"

ASSISTANT_CHAT = "assistant.chat"
CHAT_ANSWER = "chat.answer"
WORKSPACE_ASK = "workspace.ask"
WORKSPACE_DRAFT = "workspace.draft"
WEEKLY_SUMMARY = "report.weekly_summary"
HOME_NARRATIVE = "home.narrative"
GAME_QUIZ = "game.quiz"
CONNECTION_TEST = "system.connection_test"


@dataclass(frozen=True)
class AiAction:
    key: str
    label: str
    kind: str
    counts_quota: bool
    max_output_chars: int
    max_output_tokens: int
    json_output: bool = False
    supports_approval: bool = False
    prompt_slot: str = ""
    tools: bool = False
    retired: bool = False


ACTIONS: dict[str, AiAction] = {
    a.key: a
    for a in (
        AiAction(ASSISTANT_CHAT, "AI 도우미", KIND_READ, True, 6000, 2000, prompt_slot="assistant", tools=True),
        AiAction(CHAT_ANSWER, "채팅 답변(이전 방식)", KIND_READ, True, 4000, 1500, prompt_slot="answer", retired=True),
        AiAction(WORKSPACE_ASK, "작업 공간 질문(이전 방식)", KIND_READ, True, 4000, 1500, prompt_slot="answer", retired=True),
        AiAction(WORKSPACE_DRAFT, "작업 공간 문서 초안", KIND_WRITE, True, 12000, 4000, supports_approval=True,
                 prompt_slot="draft"),
        AiAction(WEEKLY_SUMMARY, "프로젝트 주간 요약", KIND_WRITE, True, 2000, 800, prompt_slot="weekly_summary"),
        AiAction(HOME_NARRATIVE, "홈 문장 요약", KIND_READ, True, 1200, 600, prompt_slot="narrative"),
        AiAction(GAME_QUIZ, "게임 퀴즈 만들기", KIND_READ, True, 8000, 2000, json_output=True, prompt_slot="quiz"),
        AiAction(CONNECTION_TEST, "연결 확인", KIND_READ, False, 200, 32, prompt_slot="connection_test"),
    )
}


def get_action(key: str) -> AiAction:
    """등록된 액션 하나. 모르는 키는 호출부의 오타라 ``KeyError`` 로 드러낸다 - 조용히 기본값으로 돌리지 않는다.

    액션 키는 코드 상수라 요청이 이 오류에 닿지 않는다. 그래서 따로 도메인 예외를 두지 않는다.
    """
    return ACTIONS[key]
