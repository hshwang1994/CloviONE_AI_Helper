"""Retrieval → 답변과 문서 초안. **생성으로 가는 문은 하나뿐이다** (D-201 · D-202).

## 🔴 생성 경로를 새로 만들지 않는다

`AiRuntime.generate(action_key=, data=)` 가 유일한 문이다(`app/ai/runtime.py`, D-515). `data` 로 넘어간
것은 난스 구분자 안에 갇히고 구분자 흉내는 걷어내진다 — **제공자는 원문을 못 본다.** 그래서 새 제공자를 붙이는
사람이 방어를 빠뜨릴 자리 자체가 없다. 검색(임베딩)은 여전히 Gateway 가 한다.

`scripts/check_domain_single_source.py` 의 「프롬프트 조립」 규칙이 다른 자리에서
`build_prompt()` 를 부르는 것을 막는다. 이 파일도 그것을 안 부른다 — 부를 필요가 없다.

## Retrieval Content 는 **데이터이지 System Instruction 이 아니다**

인용에 실린 글은 사용자가 쓴 문서 본문이다. 거기 「앞의 지시를 무시하고…」가 적혀 있을
수 있고, 그것은 요약할 내용이지 따를 지시가 아니다. 그래서 Context 는 `task` 가 아니라
**`data` 로** 넘어간다.

## 생성이 없어도 검색과 인용은 계속 동작한다 (S10 Exit)

`draft_document()` 는 인용을 **먼저** 만들고 생성은 그 뒤에 시도한다. 생성이 막혀 있으면
`text` 가 None 이고 `notice` 가 왜인지 말한다 — 인용 목록은 그대로 나간다. 화면은
그 상태에서도 근거 문서로 이동할 수 있다.

질문에 답하는 일은 여기 없다. 채팅과 작업 공간의 「물어보기」는 AI 도우미 한 차례다(`app/ai/assistant/`, D-535) -
근거가 0건이면 모델을 부르지 않던 옛 `answer()` 는 걷었다.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ai import actions
from app.ai.gateway import contract
from app.ai.retrieval import service as retrieval_service

__all__ = ["Answer", "draft_document"]

# ── 지시문 ───────────────────────────────────────────────────────────────────
#
# 지시문은 여기 없다. 액션의 사용처(질문 답변, 문서 초안)에서 런타임이 고른다 - 기본 제공 지시문은
# `app/ai/prompts/catalog.py` 에 있고 관리자가 발행본으로 바꿀 수 있다(D-518). 사용자와 문서에서 온 글은 `data` 로만
# 간다 - 지시문에 섞이는 순간 그 글이 지시가 된다.

#: 질문과 Context 를 나누는 말. 둘 다 `data` 안에 있으므로 **둘 다 데이터**다 —
#: 이 줄은 모델이 무엇을 무엇으로 읽을지 알려 주는 표지이지 지시가 아니다.
_QUESTION_HEAD = "질문:"
_CONTEXT_HEAD = "문서 발췌:"


@dataclass(frozen=True)
class Answer:
    """답변 하나. **인용이 먼저 있고 생성은 그 위에 얹힌다.**"""

    retrieval: retrieval_service.RetrievalResult
    status: str
    text: str | None = None
    model: str = ""
    delimiter_conflict: bool = False
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.status == contract.STATUS_OK and bool(self.text)

    @property
    def notice(self) -> str | None:
        return None if self.ok else contract.notice_for(self.status)

    def as_dict(self) -> dict:
        return {
            **self.retrieval.as_dict(),
            "answer": self.text,
            "status": self.status,
            "model": self.model,
            "notice": self.notice,
            "truncated": self.truncated,
            # 조용히 고치면 「왜 답이 이상하지」를 아무도 추적하지 못한다.
            "delimiter_conflict": self.delimiter_conflict,
        }


def _payload(question: str, retrieval: retrieval_service.RetrievalResult) -> str:
    return "\n\n".join([
        f"{_QUESTION_HEAD} {question}",
        f"{_CONTEXT_HEAD}",
        retrieval.context_text(),
    ])


def _generate(db: Session, runtime, *, action_key: str, question: str, retrieval, actor,
              job_id: str | None = None) -> Answer:
    result = runtime.generate(db, action_key=action_key, data=_payload(question, retrieval), actor=actor,
                              job_id=job_id)
    return Answer(
        retrieval=retrieval,
        status=result.status,
        text=result.text,
        model=result.model,
        delimiter_conflict=result.delimiter_conflict,
        truncated=result.truncated,
    )


def draft_document(
    db: Session,
    user,
    *,
    instruction: str | None,
    gateway: contract.Gateway,
    runtime,
    top_k: int = retrieval_service.TOP_K,
) -> Answer:
    """문서 초안. 답변과 **같은 문**을 지나고 사용처(지시문)만 다르다.

    지시문을 바꾼다고 새 생성 경로를 만들지 않는다 — 그렇게 늘어난 두 번째 경로가
    방어를 한쪽에만 걸리게 만드는 그 자리다(D-202 가 지적한 상태).
    """
    retrieval = retrieval_service.retrieve(
        db, user, raw_query=instruction, gateway=gateway, top_k=top_k
    )
    if retrieval.empty:
        return Answer(retrieval=retrieval, status=contract.STATUS_EMPTY)
    return _generate(db, runtime, action_key=actions.WORKSPACE_DRAFT, question=retrieval.question or retrieval.query,
                     retrieval=retrieval, actor=user)
