"""이관해 온 문서 111건을 폴더에 넣는다 — **지우고 다시 만들지 않는다.**

Revision ID: 0022_document_folders
Revises: 0021_document_trash
Create Date: 2026-08-27

## 무엇이 문제였나

새 작업공간은 공간과 폴더로 문서를 찾게 만들어 두었는데, 정작 폴더가 **하나도 없었다**
(운영 실측 2026-08-27: `folders` 0행 · 문서 111건 전부 `folder_id IS NULL`). 그래서 탐색기의
폴더 칸은 늘 비어 있고, 문서를 찾는 유일한 길은 목록을 끝까지 훑는 것이었다.

지우고 다시 이관하는 방법도 있었다. 안 한다 — 지금 데이터는 이미 정상적으로 옮겨 온
같은 데이터이고(110/110 이 `document_cache` 와 이어져 있다), 지웠다 다시 넣으면 문서 id 와
판 이력이 바뀐다. **이 마이그레이션은 `documents.folder_id` 한 칸만 채운다.**

## 분류 기준은 데이터에 이미 있었다

`documents.doc_type` 이 옛 시스템의 「문서 종류」다. 111건 중 110건이 값을 갖고, 값은
서로 배타적이며(한 문서에 하나), 종류가 15가지다. 그것이 폴더 트리가 될 축이다 —
태그(19개)는 고객사·업무 분야를 가리키는 **다른 축**이라 폴더로 만들면 한 문서가 여러
폴더에 속해야 한다. 태그는 태그 필터가 이미 답한다.

종류 15가지를 그대로 폴더 15개로 만들지는 않는다. 1~2건짜리 폴더가 여섯 개 생기고, 그런
트리는 접힌 채로 남는다. 뜻이 가까운 것끼리 여덟으로 묶는다.

## 종류가 「기타」인 23건

제목이 근거를 준다 — 「…회의록」·「…요구사항 협의서」·「…교육 커리큘럼」. 그 낱말이 있는
문서는 그 폴더로 보낸다. **본문이 비어 있고 제목에도 근거가 없는 6건은 미분류에 둔다** —
지시가 적은 그대로다: 근거가 없으면 억지로 분류하지 않는다.

## 권한은 안 바뀐다

폴더는 정리 축이고 가시성은 공간이 정한다(§5.3). 문서를 **자기 공간 안에서만** 옮기므로
볼 수 있는 사람이 한 명도 안 늘고 안 준다. 공간을 새로 만들지 않는 이유가 그것이다 —
지금 데이터에는 권한을 갈라야 할 근거가 없다(공간 하나, `confidential` 0건).

## 되감기

되감을 수 있다. 이 마이그레이션이 만든 폴더를 지우면 그 안의 문서는 `SET NULL` 로 공간
첫 화면으로 올라온다 — 이관 전 상태와 같다. 문서·판·태그는 손대지 않았으므로 잃는 것이 없다.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = '0022_document_folders'
down_revision = '0021_document_trash'
branch_labels = None
depends_on = None

MEETING = "01. 회의록"
PLAN = "02. 계획과 요구사항"
DESIGN = "03. 설계와 개발"
OPS = "04. 배포와 운영"
SECURITY = "05. 보안 점검"
KNOWLEDGE = "06. 지식 베이스"
TRAINING = "07. 교육 자료"
UNSORTED = "99. 미분류"

#: 폴더와 그 순서. 이름 앞의 번호가 곧 사람이 읽는 순서이고, `sort_order` 가 그것을
#: 기계에게 말한다(폴더 정렬은 이름이 아니라 이 값이다).
FOLDERS: tuple[tuple[str, int], ...] = (
    (MEETING, 1), (PLAN, 2), (DESIGN, 3), (OPS, 4),
    (SECURITY, 5), (KNOWLEDGE, 6), (TRAINING, 7), (UNSORTED, 99),
)

#: 옛 「문서 종류」 → 폴더. 여기 없는 종류는 아래 제목 규칙으로 간다.
BY_DOC_TYPE: dict[str, str] = {
    "회의록": MEETING,
    "작업 계획서": PLAN,
    "요구 사항 정의서": PLAN,
    "아키텍처 설계서": DESIGN,
    "개발자 레퍼런스 문서": DESIGN,
    "포탈 개발 컨벤션": DESIGN,
    "테스트 결과서": DESIGN,
    "고객사 별 배포 가이드": OPS,
    "사용자 매뉴얼": OPS,
    "Linux": OPS,
    "보안 점검 보고서": SECURITY,
    "Knowledge base": KNOWLEDGE,
    "교육": TRAINING,
}

#: 종류가 「기타」·「기타 문서」·없음인 문서를 위한 제목 규칙. **순서가 뜻을 정한다** —
#: 「서버정보 및 요구사항 협의서」는 회의·요구사항 쪽이 먼저 잡아야 한다.
BY_TITLE: tuple[tuple[str, str], ...] = (
    ("회의록", MEETING),
    ("요구사항", PLAN),
    ("협의서", PLAN),
    ("교육", TRAINING),
    ("커리큘럼", TRAINING),
    ("ci/cd", OPS),
    ("배포", OPS),
    ("서버", OPS),
    ("vm", OPS),
    ("eos 작업", OPS),
    ("작업 정리", OPS),
    ("정의서", DESIGN),
    ("엔티티", DESIGN),
    ("report", DESIGN),
    ("설치", KNOWLEDGE),
    ("설정", KNOWLEDGE),
    ("추천", KNOWLEDGE),
    ("cli", KNOWLEDGE),
)


def _folder_for(doc_type: str | None, title: str, body_len: int) -> str:
    """이 문서가 갈 폴더 이름. 근거가 없으면 미분류다."""
    known = BY_DOC_TYPE.get((doc_type or "").strip())
    if known:
        return known
    # 종류가 근거를 못 주는 문서만 제목을 본다. 본문이 비어 있으면 제목의 낱말 하나로
    # 자리를 정하지 않는다 — 빈 문서를 잘못 분류하면 그 폴더의 뜻이 흐려진다.
    if body_len <= 0:
        return UNSORTED
    lowered = (title or "").casefold()
    for needle, folder in BY_TITLE:
        if needle in lowered:
            return folder
    return UNSORTED


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 손댈 문서가 있는 공간만 고른다. 폴더를 이미 쓰고 있는 설치에서는 아무 일도 안 한다.
    spaces = [
        row[0] for row in conn.execute(sa.text(
            "SELECT DISTINCT space_id FROM documents WHERE folder_id IS NULL"
        )).all()
    ]
    for space_id in spaces:
        existing = {
            name: fid for fid, name in conn.execute(sa.text(
                "SELECT id, name FROM folders WHERE space_id = :s AND parent_id IS NULL"
            ), {"s": space_id}).all()
        }
        ids: dict[str, str] = {}
        for name, order in FOLDERS:
            if name in existing:
                ids[name] = existing[name]
                continue
            folder_id = str(uuid.uuid4())
            conn.execute(sa.text(
                "INSERT INTO folders (id, space_id, parent_id, name, depth, sort_order,"
                " created_at, updated_at)"
                " VALUES (:id, :space, NULL, :name, 0, :ord, :now, :now)"
            ), {"id": folder_id, "space": space_id, "name": name, "ord": order, "now": now})
            ids[name] = folder_id

        rows = conn.execute(sa.text(
            "SELECT d.id, d.doc_type, d.title, coalesce(length(v.body_text), 0)"
            " FROM documents d"
            " LEFT JOIN document_versions v ON v.id = d.current_version_id"
            " WHERE d.space_id = :s AND d.folder_id IS NULL"
        ), {"s": space_id}).all()
        for document_id, doc_type, title, body_len in rows:
            conn.execute(
                sa.text("UPDATE documents SET folder_id = :f WHERE id = :d"),
                {"f": ids[_folder_for(doc_type, title, int(body_len or 0))], "d": document_id},
            )


def downgrade() -> None:
    conn = op.get_bind()
    names = tuple(name for name, _ in FOLDERS)
    # 문서를 먼저 뿌리로 올린다. 폴더를 먼저 지워도 `SET NULL` 이 같은 일을 하지만,
    # 순서를 적어 두는 편이 「무엇이 사라지는가」를 읽는 사람에게 분명하다.
    conn.execute(sa.text(
        "UPDATE documents SET folder_id = NULL WHERE folder_id IN"
        " (SELECT id FROM folders WHERE parent_id IS NULL AND name = ANY(:names))"
    ), {"names": list(names)})
    conn.execute(sa.text(
        "DELETE FROM folders WHERE parent_id IS NULL AND name = ANY(:names)"
    ), {"names": list(names)})
