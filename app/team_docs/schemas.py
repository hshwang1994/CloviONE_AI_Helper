"""팀 공간 > 문서 생성 입력 스키마 (§17 개편).

extra='forbid' + 옵션 검증. 문서 종류·업무 분야·기술 태그는 classify.py 고정 상수로 제한
(임의 문자열 금지, §4/§9). 상태·우선순위는 Notion 실제 select 옵션.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 본문 상한은 마크다운 → 블록 변환기가 정한다. 여기서 숫자를 다시 적으면 편집기 미리보기와
# 실제 저장 결과가 갈라진다(티켓 스키마도 같은 곳에서 가져온다).

from app.team_docs.classify import DOC_TYPES, TECH_TAGS, WORK_FIELDS

MAX_TITLE = 200
MAX_MEMO = 2000
MAX_OWNER = 200
#: 문서 본문의 총 글자 상한. 🔴 **없다** — 값은 남기되 아무도 안 본다는 뜻이 아니라,
#: 실제로 검사하지 않는다는 뜻이다(`_body` 참고). 이름은 옛 응답 계약이 참조한다.
MAX_BODY = 20000

STATUS_OPTIONS = frozenset({"초안", "활성", "서명됨", "만료됨"})
PRIORITY_OPTIONS = frozenset({"높음", "보통", "낮음"})
_DOC_TYPES = frozenset(DOC_TYPES)
_WORK_FIELDS = frozenset(WORK_FIELDS)
_TECH_TAGS = frozenset(TECH_TAGS)


class DocumentCreate(BaseModel):
    # validate_default: 문서 종류·업무 분야가 아예 생략돼도(기본 None) 검증기가 돌아 필수로 막힌다.
    model_config = ConfigDict(extra="forbid", validate_default=True)

    title: str
    document_type: str | None = None
    work_field: str | None = None
    tech_tags: list[str] = []
    project: str | None = None
    status: str | None = None
    priority: str | None = None
    owner: str = ""
    memo: str = ""
    body: str = ""

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("제목을 입력하세요.")
        if len(v) > MAX_TITLE:
            raise ValueError(f"제목은 {MAX_TITLE}자 이하여야 합니다.")
        return v

    @field_validator("document_type")
    @classmethod
    def _dt(cls, v: str | None) -> str:
        v = v.strip() if isinstance(v, str) else ""
        if not v:
            raise ValueError("문서 종류를 선택하세요.")  # 필수(§9)
        if v not in _DOC_TYPES:
            raise ValueError("허용되지 않은 문서 종류입니다.")
        return v

    @field_validator("work_field")
    @classmethod
    def _wf(cls, v: str | None) -> str:
        v = v.strip() if isinstance(v, str) else ""
        if not v:
            raise ValueError("업무 분야를 선택하세요.")  # 필수(§9)
        if v not in _WORK_FIELDS:
            raise ValueError("허용되지 않은 업무 분야입니다.")
        return v

    @field_validator("tech_tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        out = []
        for t in (v or []):
            if not isinstance(t, str):
                continue
            if t not in _TECH_TAGS:
                raise ValueError(f"허용되지 않은 기술 태그입니다: {t}")
            if t not in out:
                out.append(t)
        return out[:20]

    @field_validator("project")
    @classmethod
    def _project(cls, v: str | None) -> str | None:
        v = (v or "").strip() if isinstance(v, str) else None
        return v or None

    @field_validator("status")
    @classmethod
    def _status(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if v not in STATUS_OPTIONS:
            raise ValueError("허용되지 않은 상태입니다.")
        return v

    @field_validator("priority")
    @classmethod
    def _priority(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if v not in PRIORITY_OPTIONS:
            raise ValueError("허용되지 않은 우선순위입니다.")
        return v

    @field_validator("owner")
    @classmethod
    def _owner(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) > MAX_OWNER:
            raise ValueError(f"소유자는 {MAX_OWNER}자 이하여야 합니다.")
        return v

    @field_validator("memo")
    @classmethod
    def _memo(cls, v: str) -> str:
        if v and len(v) > MAX_MEMO:
            raise ValueError(f"메모는 {MAX_MEMO}자 이하여야 합니다.")
        return v or ""

    @field_validator("body")
    @classmethod
    def _body(cls, v: str) -> str:
        """**줄 수·줄 길이 상한이 없다.**

        「최대 100줄」·「한 줄 1900자」가 여기 있었다. Notion 블록으로 변환해 밀어 넣던
        시절의 상한이고(`app/core/notion_blocks.py`), 밀어 넣을 곳이 없어진 뒤로는 지킬
        이유가 없다 — 그 파서도 더 이상 자르지 않는다. 문서는 길어질 수 있어야 한다.
        """
        return v or ""


# 댓글 스키마는 여기 없다 (S14 · C2) — `app/knowledge/schemas.py` 가 든다.


class DocumentBodyUpdate(BaseModel):
    """문서 본문(마크다운 정본) 저장 (사용자 지적 #9).

    티켓 본문(`app/tickets/schemas.py::TicketBodyUpdate`)과 **같은 규칙**이다. 상한값도 같은
    출처(`app/core/notion_blocks.py`)에서 가져온다 - 여기서 숫자를 다시 정하면 한쪽만 고치는
    날 편집기 미리보기와 실제 저장 결과가 어긋난다.

    상한을 **거절**로 두고 잘라내지 않는 이유: 우리 DB 에는 다 들어가는데 원본에는 앞부분만
    올라가면 두 곳이 조용히 달라진다. 사용자에게 어긋난 이유를 말하지 않고 어긋나게 두느니,
    저장을 거절하고 무엇을 줄여야 하는지 알려주는 편이 낫다.
    """

    model_config = ConfigDict(extra="forbid")

    body_markdown: str
    # 낙관적 잠금. 편집을 시작할 때 받은 본문의 지문을 그대로 돌려보낸다.
    # **선택 사항**이다 - 안 보내면 예전처럼 그냥 덮어쓴다(기존 클라이언트, CLI 호환).
    base_version: str | None = Field(default=None, max_length=64)

    @field_validator("body_markdown")
    @classmethod
    def _check_body(cls, v: str) -> str:
        """줄끝만 고른다. 길이 상한은 없다(위 `_body` 와 같은 이유)."""
        return (v or "").replace("\r\n", "\n").replace("\r", "\n")
