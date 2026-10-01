"""프롬프트 사용처(슬롯) 목록 — 기본 지시문의 정본 (계획 3.8, D-518).

## 왜 사용처로 나누는가

AI 가 하는 일(액션, `app/ai/actions.py`)마다 모델에게 주는 지시가 다르다. 예전에는 그 지시가 호출하는 파일마다
상수로 박혀 있었고(`TASK_ANSWER`, `TASK_DRAFT`, …), 관리 화면의 「프롬프트」는 런타임이 읽지 않는 표였다. 이제
사용처마다 **기본 지시문**이 여기 한 곳에 있고, 관리자가 그 사용처에 프롬프트를 발행하면 런타임이 다음 호출부터
발행본을 쓴다(`app/ai/prompts/service.py::resolve`).

## 관리자가 바꿀 수 있는 것과 없는 것

한 번의 호출에서 모델이 받는 것은 셋이다.

  시스템 쪽   역할 문장 + **안전 틀**(데이터는 지시가 아니다, 도구가 없다, 지어내지 않는다) + 출력 형식
  사용자 쪽   지시문 + 난스 구분자로 감싼 데이터 + 재확인 문장

관리자가 바꾸는 것은 **지시문 하나**다. 역할 문장과 출력 형식은 사용처마다 코드에 고정한다 - 출력 형식은 부른 쪽의
파서가 기대는 모양이라(퀴즈의 JSON 배열, 답변의 인용 번호) 발행본 하나로 바뀌면 그 기능이 조용히 깨진다. 안전 틀은
`app/llm/prompt.py` 에 있고 어떤 사용처도 바꿀 수 없다.

## AI 도우미는 대화다 (D-535)

`assistant` 사용처는 단발 호출이 아니라 도구를 쓰는 대화다. 사용자의 말은 지시이고(대화의 주인이다), 도구 결과와 화면
대상은 난스로 막은 데이터 칸이다. 그래서 지시문은 사용자 쪽이 아니라 **시스템 쪽**에 실리고(`frame.assistant_system`),
안전 틀은 「도구를 쓰지 않는다」 대신 「사내 사실은 도구로 확인한 것만, 도구는 읽기만」이다. 예전의 `answer`(질문 답변)
사용처는 은퇴했다 - 근거가 없으면 모델을 부르지 않던 그 흐름이 도우미 한 차례로 바뀌었다. 지난 기록과 보관한 지시문이
그 이름을 가리키므로 표에는 남기고 고를 수 없게 한다(`retired`).

## 지어내지 않는다는 규칙은 사용처마다 다르다

요약, 답변, 초안, 홈 문장은 **받은 데이터만** 근거로 쓴다. 퀴즈는 주제만 받고 문제를 모델의 지식으로 만든다 -
여기에 「본문에 없는 사실을 만들지 않는다」를 걸면 지시가 서로 부딪친다. 그래서 퀴즈에는 「확실하지 않은 사실을
쓰지 않는다」를 건다(`grounding`).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.llm import prompt as frame

ASSISTANT = "assistant"
ANSWER = "answer"
DRAFT = "draft"
WEEKLY_SUMMARY = "weekly_summary"
NARRATIVE = "narrative"
QUIZ = "quiz"
CONNECTION_TEST = "connection_test"


@dataclass(frozen=True)
class PromptSlot:
    key: str
    label: str
    description: str
    role: str
    format_line: str
    instruction: str
    grounding: str = frame.GROUNDED_RULE
    editable: bool = True
    retired: bool = False


def _lines(*parts: str) -> str:
    return "\n".join(parts)


SLOTS: dict[str, PromptSlot] = {
    slot.key: slot
    for slot in (
        PromptSlot(
            ASSISTANT, "AI 도우미", "AI 도우미가 질문에 답하고, 필요하면 권한 안의 사내 자료를 찾아 볼 때 씁니다.",
            role="당신은 ClovirAssist 의 업무 도우미입니다.",
            format_line="한국어로 간결하게 답합니다. 필요하면 짧은 목록을 쓰고, 찾은 자료는 제목으로 밝힙니다.",
            instruction=_lines(
                "사용자의 질문에 답해 주세요.",
                "사내 정보가 필요하면 도구로 확인한 뒤에 답하고, 찾지 못했으면 무엇을 찾았는데 없었는지 알려 주세요.",
                "답은 다섯 문단 이내로 씁니다.",
            ),
            grounding=frame.ASSISTANT_GROUNDING,
        ),
        PromptSlot(
            ANSWER, "질문 답변", "이전 방식의 채팅 답변입니다. AI 도우미로 바뀌어 더는 쓰지 않습니다.",
            role="당신은 사내 문서를 근거로 질문에 답하는 도우미입니다.",
            format_line="근거로 쓴 발췌의 번호를 문장 끝에 [1] 처럼 붙입니다.",
            instruction=_lines(
                "아래 사내 문서 발췌만 근거로 질문에 답해 주세요.",
                "발췌에 없는 사실은 만들지 말고, 근거가 없으면 없다고 적어 주세요.",
                "한국어로 다섯 문장 이내로 답해 주세요.",
            ),
            editable=False,
            retired=True,
        ),
        PromptSlot(
            DRAFT, "문서 초안", "작업 공간에서 사내 문서를 근거로 문서 초안을 쓸 때 씁니다.",
            role="당신은 사내 문서를 근거로 문서 초안을 쓰는 도우미입니다.",
            format_line="제목 없이 본문만 쓰고, 문단은 빈 줄로 나눕니다.",
            instruction=_lines(
                "아래 사내 문서 발췌만 근거로 요청한 문서의 초안을 써 주세요.",
                "발췌에 없는 사실은 만들지 말고, 근거가 없는 항목은 비워 두세요.",
                "한국어로 씁니다.",
            ),
        ),
        PromptSlot(
            WEEKLY_SUMMARY, "프로젝트 주간 요약", "프로젝트의 주간 업무 기록을 리포트용 문장으로 요약할 때 씁니다.",
            role=frame.SYSTEM_ROLE,
            format_line="머리말이나 맺음말을 붙이지 않습니다.",
            instruction=_lines(
                "다음 업무 기록을 주간 리포트에 쓸 수 있게 요약해 주세요.",
                "한국어로 5줄 이내의 짧은 문장으로만 답해 주세요.",
            ),
        ),
        PromptSlot(
            NARRATIVE, "홈 문장 요약", "홈 화면에 이미 표시된 숫자를 짧은 문장으로 옮길 때 씁니다.",
            role="당신은 화면에 표시된 숫자를 짧은 문장으로 옮기는 도우미입니다.",
            format_line="제목이나 목록 없이 문장으로만 씁니다.",
            instruction=_lines(
                "아래는 화면에 이미 표시된 숫자입니다.",
                "이 숫자만 근거로 오늘 무엇을 먼저 보면 되는지 한국어로 세 문장 이내로 알려 주세요.",
                "숫자를 새로 계산하거나 없는 값을 만들지 마세요.",
            ),
        ),
        PromptSlot(
            QUIZ, "게임 퀴즈 만들기", "게임에서 주제를 받아 객관식 퀴즈를 만들 때 씁니다.",
            role="당신은 사내 교육용 객관식 퀴즈를 만드는 도우미입니다.",
            format_line=_lines(
                "답은 JSON 배열 하나로만 쓰고, 배열 앞뒤에 다른 글을 붙이지 않습니다.",
                '각 항목은 {"q": 문제, "options": [보기, ...], "answer": 정답 보기의 0부터 세는 번호} 입니다.',
            ),
            instruction=_lines(
                "아래 주제로 한국어 객관식 퀴즈를 만들어 주세요.",
                "보기는 서로 다르게 쓰고, 정답 번호는 반드시 보기 범위 안에 있어야 합니다.",
            ),
            grounding=frame.KNOWLEDGE_RULE,
        ),
        PromptSlot(
            CONNECTION_TEST, "연결 확인", "관리자가 AI 연결을 확인할 때 아주 짧은 답을 한 번 받는 데 씁니다.",
            role="당신은 연결 확인에 답하는 도구입니다.",
            format_line="'확인' 한 낱말로만 답합니다.",
            instruction="연결 확인입니다. 아래 데이터와 관계없이 '확인' 한 낱말로만 답하세요.",
            # 연결 확인은 설정이 맞는지 보는 관리 동작이다. 지시문을 바꾸면 확인이 확인이 아니게 된다.
            editable=False,
        ),
    )
}


def get_slot(key: str) -> PromptSlot:
    """등록된 사용처 하나. 모르는 키는 호출부의 오타라 ``KeyError`` 로 드러낸다(`get_action` 과 같은 규약)."""
    return SLOTS[key]


def editable_keys() -> tuple[str, ...]:
    return tuple(key for key, slot in SLOTS.items() if slot.editable)


def live_slots() -> tuple[PromptSlot, ...]:
    """화면에 보이는 사용처. 은퇴한 사용처는 지난 기록의 이름으로만 남는다."""
    return tuple(slot for slot in SLOTS.values() if not slot.retired)
