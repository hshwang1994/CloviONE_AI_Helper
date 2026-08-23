"""Retrieval → 답변과 문서 초안. **생성으로 가는 문은 하나뿐이다** (D-201 · D-202).

## 🔴 생성 경로를 새로 만들지 않는다

`Gateway.generate(task=, data=)` 가 유일한 문이다. `data` 로 넘어간 것은 난스 구분자
안에 갇히고 구분자 흉내는 걷어내진다 — **Adapter 는 원문을 못 본다.** 그래서 새
Adapter 를 붙이는 사람이 방어를 빠뜨릴 자리 자체가 없다.

`scripts/check_domain_single_source.py` 의 「프롬프트 조립」 규칙이 다른 자리에서
`build_prompt()` 를 부르는 것을 막는다. 이 파일도 그것을 안 부른다 — 부를 필요가 없다.

## Retrieval Content 는 **데이터이지 System Instruction 이 아니다**

인용에 실린 글은 사용자가 쓴 문서 본문이다. 거기 「앞의 지시를 무시하고…」가 적혀 있을
수 있고, 그것은 요약할 내용이지 따를 지시가 아니다. 그래서 Context 는 `task` 가 아니라
**`data` 로** 넘어간다.

## 생성이 없어도 검색과 인용은 계속 동작한다 (S10 Exit)

`answer()` 는 인용을 **먼저** 만들고 생성은 그 뒤에 시도한다. 생성이 막혀 있으면
`text` 가 None 이고 `notice` 가 왜인지 말한다 — 인용 목록은 그대로 나간다. 화면은
그 상태에서도 근거 문서로 이동할 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ai.gateway import contract
from app.ai.retrieval import service as retrieval_service

__all__ = ["Answer", "answer", "draft_document"]

# ── 지시문 ───────────────────────────────────────────────────────────────────
#
# **우리가 쓴 문장만 여기 있다.** 사용자·문서에서 온 글은 한 글자도 안 섞인다 —
# 섞이는 순간 그 글이 지시가 된다.

TASK_ANSWER = "\n".join([
    "아래 사내 문서 발췌만 근거로 질문에 답해 주세요.",
    "발췌에 없는 사실은 만들지 말고, 근거가 없으면 없다고 적어 주세요.",
    "근거로 쓴 발췌의 번호를 문장 끝에 [1] 처럼 붙여 주세요.",
    "한국어로 다섯 문장 이내로 답해 주세요.",
])

TASK_DRAFT = "\n".join([
    "아래 사내 문서 발췌만 근거로 요청한 문서의 초안을 써 주세요.",
    "발췌에 없는 사실은 만들지 말고, 근거가 없는 항목은 비워 두세요.",
    "제목 없이 본문만 쓰고, 문단은 빈 줄로 나눠 주세요.",
    "한국어로 씁니다.",
])

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


def _generate(gateway: contract.Gateway, *, task: str, question: str, retrieval) -> Answer:
    result = gateway.generate(task=task, data=_payload(question, retrieval))
    return Answer(
        retrieval=retrieval,
        status=result.status,
        text=result.text,
        model=result.model,
        delimiter_conflict=result.delimiter_conflict,
        truncated=result.truncated,
    )


def answer(
    db: Session,
    user,
    *,
    raw_query: str | None,
    gateway: contract.Gateway,
    top_k: int = retrieval_service.TOP_K,
) -> Answer:
    """질문 → (인용, 답변). 인용은 언제나 나가고 답변은 될 때만 나간다."""
    retrieval = retrieval_service.retrieve(
        db, user, raw_query=raw_query, gateway=gateway, top_k=top_k
    )
    if retrieval.empty:
        # 근거가 없으면 부르지 않는다. 빈 Context 로 부르면 모델은 무언가를 지어내고,
        # 그 문장에는 인용이 하나도 안 붙는다 — 사람은 그것을 답으로 읽는다.
        return Answer(retrieval=retrieval, status=contract.STATUS_EMPTY)
    return _generate(gateway, task=TASK_ANSWER, question=retrieval.query, retrieval=retrieval)


def draft_document(
    db: Session,
    user,
    *,
    instruction: str | None,
    gateway: contract.Gateway,
    top_k: int = retrieval_service.TOP_K,
) -> Answer:
    """문서 초안. 답변과 **같은 문**을 지나고 지시문만 다르다.

    지시문을 바꾼다고 새 생성 경로를 만들지 않는다 — 그렇게 늘어난 두 번째 경로가
    방어를 한쪽에만 걸리게 만드는 그 자리다(D-202 가 지적한 상태).
    """
    retrieval = retrieval_service.retrieve(
        db, user, raw_query=instruction, gateway=gateway, top_k=top_k
    )
    if retrieval.empty:
        return Answer(retrieval=retrieval, status=contract.STATUS_EMPTY)
    return _generate(gateway, task=TASK_DRAFT, question=retrieval.query, retrieval=retrieval)
