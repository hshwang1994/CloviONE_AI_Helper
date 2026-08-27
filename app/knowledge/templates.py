"""새 문서의 **출발점** 네 가지 (지시 22.5).

## 왜 서버가 들고 있는가

본문의 정본은 ProseMirror Block Tree 다(D-198). 화면이 그 JSON 을 손으로 적으면 서버의
스키마(`blocks.BLOCK_NODES`)와 두 벌이 되고, 어긋난 쪽은 저장할 때가 아니라 **문서를 열
때** 빈 화면으로 드러난다. 그래서 틀은 여기서 만들고 화면은 이름만 고른다.

## 왜 표를 안 만드는가

지시가 「복잡한 Template 관리 시스템을 새로 만드는 것은 별도 필요가 있을 때만」이라고
적었다. 지금 필요한 것은 「새 문서를 빈 화면으로 시작하지 않게 하는 것」이고, 그것은
상수 넷으로 된다. 표를 만들면 그 순간 편집 화면 · 권한 · 이력이 따라붙고, 그 넷은 아직
아무도 요구하지 않았다.

## 틀이 채우는 것은 **질문**이지 문장이 아니다

「1. 배경」 아래에 예시 문장을 넣어 두면 그 문장이 지워지지 않은 채 저장된 문서가 반드시
생긴다. 그래서 각 칸에는 제목과 **무엇을 적는 자리인지**만 둔다 — 새 티켓의 작성 도움이
같은 이유로 예시를 본문에 안 넣는다(묶음 B).
"""

from __future__ import annotations

from typing import Any

__all__ = ["TEMPLATES", "ids", "body_for", "catalog"]

BLANK = "blank"


def _p(text: str = "") -> dict[str, Any]:
    node: dict[str, Any] = {"type": "paragraph"}
    if text:
        node["content"] = [{"type": "text", "text": text}]
    return node


def _h(level: int, text: str) -> dict[str, Any]:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [{"type": "text", "text": text}],
    }


def _ul(*items: str) -> dict[str, Any]:
    return {
        "type": "bulletList",
        "content": [
            {"type": "listItem", "content": [_p(item)]}
            for item in items
        ],
    }


def _doc(*nodes: dict[str, Any]) -> dict[str, Any]:
    return {"type": "doc", "content": list(nodes)}


#: 틀 넷. `body` 가 `None` 이면 빈 문서다 — 빈 사전을 적어 두면 「빈 문서」와 「틀이
#: 없다」가 코드에서 같은 값이 된다.
TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "id": BLANK,
        "name": "빈 문서",
        "help": "아무것도 없는 상태에서 시작합니다.",
        "body": None,
    },
    {
        "id": "meeting",
        "name": "회의록",
        "help": "회의 목적과 참석자, 정한 것과 할 일을 남깁니다.",
        "body": _doc(
            _h(2, "회의 개요"),
            _ul("일시와 장소", "참석자", "회의 목적"),
            _h(2, "논의 내용"),
            _p(),
            _h(2, "정한 것"),
            _ul("무엇을 정했는지 한 줄로 적습니다."),
            _h(2, "할 일"),
            _ul("누가 언제까지 무엇을 하는지 적습니다."),
        ),
    },
    {
        "id": "requirements",
        "name": "요구사항 정의서",
        "help": "배경과 범위, 기능과 완료 기준을 정리합니다.",
        "body": _doc(
            _h(2, "배경과 목적"),
            _p(),
            _h(2, "범위"),
            _ul("이번에 하는 것", "이번에 하지 않는 것"),
            _h(2, "기능 요구사항"),
            _p(),
            _h(2, "비기능 요구사항"),
            _ul("성능", "보안", "운영"),
            _h(2, "완료 기준"),
            _p(),
        ),
    },
    {
        "id": "ops-guide",
        "name": "운영 가이드",
        "help": "절차와 점검 항목, 장애가 났을 때 할 일을 적습니다.",
        "body": _doc(
            _h(2, "이 문서가 다루는 것"),
            _p(),
            _h(2, "사전 준비"),
            _ul("필요한 권한", "필요한 도구"),
            _h(2, "절차"),
            {
                "type": "orderedList",
                "content": [{"type": "listItem", "content": [_p("첫 단계를 적습니다.")]}],
            },
            _h(2, "점검"),
            _ul("무엇이 정상인지 적습니다."),
            _h(2, "문제가 생기면"),
            _p(),
        ),
    },
)

_BY_ID = {t["id"]: t for t in TEMPLATES}


def ids() -> tuple[str, ...]:
    """스키마가 받는 값 목록. 화면이 보내는 이름을 여기서만 정한다."""
    return tuple(_BY_ID)


def body_for(template_id: str | None) -> dict[str, Any] | None:
    """틀 하나의 본문 **새 사전**.

    모르는 이름은 `None` — 거절하지 않는다. 틀을 하나 없앤 날 그 이름을 들고 온 요청이
    문서 생성 자체를 못 하게 되면, 사용자는 자기가 쓴 제목까지 잃는다. 빈 문서로 시작하는
    것은 잃는 것이 없다.
    """
    if not template_id:
        return None
    row = _BY_ID.get(template_id)
    if row is None or row["body"] is None:
        return None
    # 상수를 그대로 주면 부르는 쪽이 그것을 고친다(`blocks.empty_doc` 과 같은 이유).
    import copy

    return copy.deepcopy(row["body"])


def catalog() -> list[dict[str, Any]]:
    """화면이 그리는 목록. **본문은 안 싣는다** — 고르는 자리에 필요한 것은 이름과 설명뿐이고,
    본문까지 실으면 문서를 만들지 않는 사람에게도 네 벌의 Block JSON 이 나간다."""
    return [
        {"id": t["id"], "name": t["name"], "help": t["help"], "empty": t["body"] is None}
        for t in TEMPLATES
    ]
