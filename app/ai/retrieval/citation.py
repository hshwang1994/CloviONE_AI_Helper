"""인용 — 「이 문서 어딘가」가 아니라 **「이 자리」**를 가리킨다 (MASTER_PLAN §5.4).

## 새로 만들 것이 없다

앵커는 **S9 가 이미 저장했다**: `anchor_kind`(block/page/slide/section/sheet/text) ·
`anchor_ref`(기계용) · `anchor_label`(사람이 읽는 말). S10 이 하는 일은 그것을
**눌러서 갈 수 있는 자리**로 바꾸는 것 하나다.

## 왜 라우트를 서버가 만드는가

`app/search/models.py` 가 「인덱스가 라우트를 들고 있다 — 화면이 유형별 if 를 갖지
않게」라고 적어 둔 것과 같은 이유다. 화면이 `source_kind` 로 분기해 주소를 조립하면,
경로가 바뀌는 날 고쳐야 할 자리가 화면 수만큼이 된다.

## 앵커가 링크의 **일부**다

문서 chunk 의 주소는 `/knowledge/<문서 id>?block=<블록 id>` 다. 블록 id 는 판이 올라도
안 바뀌므로(D-198 · `blocks.derive(carry_from=)`) 어제 만든 인용이 오늘도 같은 문장을
가리킨다. 그 값이 없으면 문서까지만 간다 — **틀린 자리로 보내는 것보다 낫다.**

첨부 chunk 는 문서까지 데려가고 어느 파일의 몇 쪽인지는 말로 적는다. 파일 안의 특정
쪽으로 브라우저를 보내는 것은 뷰어가 하는 일이고 이 제품에는 그 뷰어가 없다 —
`#page=3` 을 붙여 봐야 형식마다 되고 안 되고가 갈린다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.models import (
    ANCHOR_BLOCK,
    ANCHOR_PAGE,
    ANCHOR_SECTION,
    ANCHOR_SHEET,
    ANCHOR_SLIDE,
    ANCHOR_TEXT,
    SOURCE_FILE,
)

__all__ = ["Citation", "build", "route_for", "where_of"]

#: 앵커 종류 → 자리를 부르는 말. 화면이 이 문자열을 그대로 싣는다.
#: 값이 없을 때를 위한 폴백은 두지 않는다 — `ANCHOR_KINDS` 는 CHECK 제약이라 모르는
#: 값이 DB 에 들어올 수 없고, 여기 없는 종류가 생기면 그 사실이 시험에서 드러나야 한다.
KIND_WORDS: dict[str, str] = {
    ANCHOR_BLOCK: "문단",
    ANCHOR_PAGE: "쪽",
    ANCHOR_SLIDE: "슬라이드",
    ANCHOR_SECTION: "절",
    ANCHOR_SHEET: "시트",
    ANCHOR_TEXT: "구간",
}


@dataclass(frozen=True)
class Citation:
    """인용 하나. **화면이 그대로 그린다.**"""

    chunk_id: str
    document_id: str
    document_title: str
    #: 눌렀을 때 갈 자리. 라우터 경로이고 호스트가 안 붙는다.
    route: str
    #: 「3쪽」·「보고서.pdf 12쪽」처럼 **어디인지**를 말하는 한 줄.
    where: str
    #: 인용한 글의 앞부분. **화면용**이다.
    excerpt: str
    #: chunk 전체. **모델에게 넘기는 것은 이쪽**이고 응답 JSON 에는 안 싣는다 —
    #: 화면은 잘린 글만 보여 주는데 모델에게도 잘린 글을 주면 답이 그만큼 얕아지고,
    #: 반대로 응답에 전문을 실으면 인용 여덟 건이 매 요청 수만 자가 된다.
    text_for_context: str
    source_kind: str
    anchor_kind: str
    anchor_ref: str
    #: 첨부에서 나왔으면 그 파일 이름. 본문에서 나왔으면 빈 문자열이다.
    filename: str = ""
    #: 이 인용을 어느 레인이 찾았는가 — 「의미 검색이 찾았습니다」의 근거다.
    lanes: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "route": self.route,
            "where": self.where,
            "excerpt": self.excerpt,
            "source_kind": self.source_kind,
            "anchor_kind": self.anchor_kind,
            "filename": self.filename,
            # 화면이 레인 이름을 해석하지 않는다 — 답해야 하는 질문은 하나뿐이다.
            "semantic_only": self.semantic_only,
        }

    @property
    def semantic_only(self) -> bool:
        """찾은 낱말이 하나도 없는데 나온 문서인가 (`fusion.semantic_only`)."""
        from app.ai.retrieval import fusion

        return fusion.semantic_only(self.lanes)


def route_for(chunk) -> str:
    """chunk → 눌러서 갈 자리.

    블록 앵커가 있으면 `?block=` 을 붙인다. 화면이 그 값으로 해당 문단까지 스크롤하고
    잠깐 표시한다(`frontend/src/screens/KnowledgeDoc.jsx`).
    """
    base = f"/knowledge/{chunk.document_id}"
    if chunk.anchor_kind == ANCHOR_BLOCK and chunk.anchor_ref:
        return f"{base}?block={chunk.anchor_ref}"
    return base


def where_of(chunk, *, filename: str = "") -> str:
    """「어디인가」 한 줄. 저장된 `anchor_label` 을 **우선 그대로 쓴다.**

    파서가 만든 말이 언제나 더 구체적이다(「12쪽」·「2번 슬라이드」·「Sheet1!A1:D20」).
    없을 때만 종류 이름과 참조로 만든다.
    """
    label = (chunk.anchor_label or "").strip()
    if not label:
        word = KIND_WORDS.get(chunk.anchor_kind, "")
        ref = (chunk.anchor_ref or "").strip()
        label = f"{ref}{word}" if (ref and word and ref.isdigit()) else (word or ref)
    if chunk.source_kind == SOURCE_FILE and filename:
        return f"{filename} {label}".strip() if label else filename
    return label


def build(chunk, *, document_title: str, filename: str = "", lanes=(), excerpt_chars: int) -> Citation:
    """chunk 행 하나 → 인용 하나."""
    body = (chunk.text_body or "").strip()
    excerpt = body if len(body) <= excerpt_chars else body[:excerpt_chars].rstrip() + "…"
    return Citation(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        document_title=document_title,
        route=route_for(chunk),
        where=where_of(chunk, filename=filename),
        excerpt=excerpt,
        text_for_context=body,
        source_kind=chunk.source_kind,
        anchor_kind=chunk.anchor_kind,
        anchor_ref=chunk.anchor_ref or "",
        filename=filename,
        lanes=tuple(lanes),
    )
