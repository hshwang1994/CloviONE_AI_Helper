"""프로젝트별 지식 공간을 만들고, 근거가 확실한 문서를 그 공간으로 옮긴다 (재검수 묶음2 §11·§14).

Revision ID: 0023_project_knowledge_spaces
Revises: 0022_document_folders
Create Date: 2026-08-28

## 무엇이 문제였나

문서 111건이 전부 조직 공용 공간(`팀 문서`) 하나에 있다. §11.1이 정한 정본 구조는
"프로젝트 소속의 정본은 `knowledge_spaces.owner_kind='project'`"인데, 지금은 그런 공간이
하나도 없다 — 프로젝트 상세에 문서 탭을 붙여도 보여줄 것이 없다.

## 근거 등급 (§14.1) — 랩 서버 실제 데이터를 읽고 판단했다

이 마이그레이션 설계 시점에 랩 서버(`clovirassist.gooddi.lab`)의 실제 문서 111건을
`GET /api/knowledge/documents` · `GET /api/knowledge/documents/{id}` 로 읽어 판단했다.
Notion 문자열 매칭이 아니라 이 저장소가 실제로 배포된 인스턴스의 현재 데이터다.

- **1등급** — 기존 "프로젝트성" 태그(§13 표, 이름이 프로젝트명과 글자까지 일치)가
  **단 하나만** 붙은 문서. 그대로 그 프로젝트로 옮긴다.
- **2등급** — 태그가 없고 제목에 고객·시스템 이름이 있는 문서 중, 그 고객의 프로젝트가
  단 하나뿐이거나(예: 한강홍수통제소·한국인터넷진흥원·NextHub 는 각자 프로젝트가 하나뿐),
  프로젝트가 여럿인 고객(SK하이닉스 2개·현대모비스 2개·굿모닝아이텍 2개)이면 제목이
  그중 하나를 구체적으로 가리킬 때만(예: "MDIP" 는 현대모비스의 두 프로젝트 중
  "MDIP 시스템 운영/개선" 만 가리킨다. "ClovirONE"·"PoC"·"환경정보" 로 이어지는 하이닉스
  문서는 다른 1등급 하이닉스 문서(SK_Hynix POC clovirone 환경 정보 등)와 같은 주제라
  "용인 클러스터 대비" 프로젝트로 판단했다).
- **근거 없음** → 공통 문서로 남긴다. "ERP"/"ERP 서버"(고객명 없이 사내 시스템일 수 있음),
  "하이닉스 운영"·"하이닉스 5월 19일 기준 엔티티 정의"·"외부 Tomcat 배포 패키지 사용 방법
  (SKHynix)"(하이닉스 프로젝트 2개 중 어느 쪽인지, 심지어 고객 프로젝트인지 자체도 가릴
  근거가 없다)는 넣지 않았다.

그 결과가 `RELOCATE` — 문서 58건, 프로젝트 11개(문서가 하나라도 오는 프로젝트에만
공간을 만든다, §14.2). 나머지 53건은 공용 공간에 남는다.

## 예외 — 프로젝트 셋에 동시에 걸린 문서 하나

"SCM(Source Code Management) 전략" 문서는 1등급 태그가 **셋**(스마일게이트홀딩스 ·
포스코DX · SK하이닉스[용인 클러스터 대비]) 붙어 있다. 문서의 공간은 하나뿐이라 셋 중
하나를 고르면 나머지 둘의 문맥을 잃는다. 내용도 "clovirone-base repo" 전략처럼 특정
고객이 아니라 제품 자체를 다룬다 — 셋 중 하나를 임의로 골라 나머지 둘을 지우지 않고
공용 공간에 남긴다(`RELOCATE`에 이 문서는 없다). 기술 태그(0024)는 다른 문서와 똑같이
받는다.

## 폴더는 새 공간에 복제하지 않는다

문서를 옮기면 `folder_id`가 옛 공간의 폴더(0022가 만든 8개)를 가리키게 되는데, 폴더는
공간마다 별도 트리라 그 참조는 새 공간에서 무의미하다(다른 공간의 폴더를 가리키는
문서가 생긴다). §14.2가 "프로젝트마다 미리 만들지 않는다"고 이미 정했으므로 새 폴더
트리를 복제하지 않고 `folder_id`를 비운다 — 공간 뿌리로 올라온다(0022가 폴더를 지울 때
하는 처리와 같다). 사용자는 이동 대화상자(§14.4)로 언제든 다시 분류할 수 있다.

## 권한은 안 바뀐다 (§11.1)

새 공간은 `owner_kind='project'`다. §11.1의 가시성 확인(운영 활성 사용자 25명 중 24명이
`admin_scope=global`, 나머지 1명도 프로젝트의 `dept_id`로 걸림, 프로젝트 전부 `dept_id`
있음)을 그대로 신뢰한다 — 문서를 볼 수 있는 사람이 줄지 않는다. `confidential=false` ·
`owner_dept_id=NULL`(프로젝트 소유는 부서 축을 같이 쓰지 않는다 — `ck_kspace_dept_pair`).

## 되감기

`RELOCATE`의 문서를 원래 공간(`owner_kind='organization'`)과 원래 폴더 이름으로 되돌리고,
이 마이그레이션이 만든 프로젝트 공간을 지운다. 문서·판·태그는 손대지 않는다.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = '0023_project_knowledge_spaces'
down_revision = '0022_document_folders'
branch_labels = None
depends_on = None

# (document_id, project_code, original_folder_name) — §14.1 근거 등급 1·2로 판단한 58건.
# project_code 는 app/projects 의 실제 Project.code, original_folder_name 은 0022 가
# 붙인 8개 폴더 중 이 문서가 이관 직전에 있던 폴더(되감기가 그 이름으로 복원한다).
RELOCATE: tuple[tuple[str, str, str], ...] = (
    ('a92fb3a6-b6dc-439a-8ddd-ce50a507e5eb', 'TMRWGY', '01. 회의록'),
    ('bf28ff1d-c568-4d76-a056-840ab84c7cbc', 'HAASFT', '01. 회의록'),
    ('c3150c3b-ebb2-4be8-af19-c21d4cef69e6', 'HSDFXZ', '01. 회의록'),
    ('a4bc4119-8ab8-4778-9bf7-2eebdaf78317', 'ZCYMPW', '01. 회의록'),
    ('ff8b2d29-1a91-4ff6-910a-fc8fcf1d8bb9', 'TMRWGY', '01. 회의록'),
    ('0564d161-a2d9-4c49-a491-c225c09c5e9e', 'TMRWGY', '01. 회의록'),
    ('9fb48bc8-656a-4f6b-bd42-2a11bef7da99', 'RYPDYW', '02. 계획과 요구사항'),
    ('77e292fe-ef14-4f52-817c-cfd23d2f03a6', 'XDTBCC', '02. 계획과 요구사항'),
    ('e26d2b6c-a1d4-43ff-ac9a-52df6eecf8dc', 'TMRWGY', '01. 회의록'),
    ('4a78321d-bd63-4ea9-bd40-8cb85359e09d', 'HAASFT', '01. 회의록'),
    ('2c9e4ec5-ffc4-433c-ac17-c8679659808d', 'SNGZRK', '03. 설계와 개발'),
    ('c3ed37af-666b-4731-8dce-203842e3b960', 'SNGZRK', '03. 설계와 개발'),
    ('e5a9a6fc-2e99-4917-9d7c-02db8f6f7737', 'TMRWGY', '01. 회의록'),
    ('58f7bcd0-1537-44b6-b346-63dfef9506e1', 'XDTBCC', '02. 계획과 요구사항'),
    ('f3a7edc6-f0be-4b12-8719-18ee2e596ca4', 'EEQFAP', '02. 계획과 요구사항'),
    ('6718b7aa-4f31-4756-bf8b-6c419ab28ec7', 'XDTBCC', '02. 계획과 요구사항'),
    ('d401ffc8-effa-4ac2-9e24-a47736631b90', 'HAASFT', '02. 계획과 요구사항'),
    ('baeb4ca1-64f0-4797-92a7-c797c2ccc3af', 'TMRWGY', '01. 회의록'),
    ('a423b02d-a797-4018-9b26-404585df05bb', 'TMRWGY', '01. 회의록'),
    ('fc5e545a-4766-4cfd-b46b-6ff3b00a08be', 'HAASFT', '01. 회의록'),
    ('e7898a9d-9222-41df-b010-5432d39358d4', 'TMRWGY', '01. 회의록'),
    ('0ff28696-a712-4ba4-8940-ad5717e49a0b', 'TMRWGY', '01. 회의록'),
    ('661d8fe1-5eaa-4e57-afe4-92d8a0e729bd', 'HAASFT', '05. 보안 점검'),
    ('787b73bc-6ff4-4ac6-8dc3-10136f31b08d', 'HAASFT', '05. 보안 점검'),
    ('250e9239-80ef-4cce-a7a9-3e7fc30e9712', 'HAASFT', '05. 보안 점검'),
    ('d0486bdd-646d-4ea7-9af9-230e521e6951', 'HAASFT', '05. 보안 점검'),
    ('4262f4fd-b89e-4e09-95a6-fed4fe41b6fa', 'HAASFT', '05. 보안 점검'),
    ('77f25358-3ebf-417e-8e2d-fa0981b6e75c', 'TMRWGY', '01. 회의록'),
    ('11576247-b587-4ec0-b08a-87e14fd6b807', 'HAASFT', '02. 계획과 요구사항'),
    ('b9ce4b3f-516e-4863-8330-ecee31fce189', 'HAASFT', '06. 지식 베이스'),
    ('c59a739d-9a67-499b-914c-926a40ba46ed', 'XDTBCC', '02. 계획과 요구사항'),
    ('599b28b7-acce-438d-af05-98c82e4560b8', 'ZCYMPW', '06. 지식 베이스'),
    ('9f18a32f-b4fa-42a3-88d1-2fbda1282395', 'HAASFT', '06. 지식 베이스'),
    ('7820ca0c-42ff-4238-a93a-d1b6afe9599b', 'RYPDYW', '02. 계획과 요구사항'),
    ('bb03e412-0e8e-44a8-a8d0-9309cc51a3ab', 'HAASFT', '04. 배포와 운영'),
    ('928aaa76-4884-42d0-a521-e9ebc6d7be2c', 'TMRWGY', '04. 배포와 운영'),
    ('cdd39f0c-7f69-41b6-98dc-c2cd762d848e', 'XDTBCC', '02. 계획과 요구사항'),
    ('3635482b-03c1-4f28-89a8-abe903994f03', 'HAASFT', '04. 배포와 운영'),
    ('0fe64068-19ec-430e-9258-c3ac0ec85c40', 'TMRWGY', '01. 회의록'),
    ('bbc22b66-3bf0-46a9-b3b5-3909fc33e6d1', 'ZCYMPW', '06. 지식 베이스'),
    ('0a030622-866b-4665-928b-bba8291c88ca', 'ZCYMPW', '02. 계획과 요구사항'),
    ('d038ad95-b72a-41c7-bbb6-69d011eaa2b8', 'EEQFAP', '06. 지식 베이스'),
    ('23940fb6-ca22-4444-935e-953ff30e5d32', 'EYWYRY', '04. 배포와 운영'),
    ('6494b35b-7f1a-4d9e-8a50-65167f689139', 'TMRWGY', '02. 계획과 요구사항'),
    ('bbeb3063-c1ba-4dd0-b871-a3cd2af4c33b', 'ZCYMPW', '01. 회의록'),
    ('8d7d5927-5f66-4af1-8350-f052b865d8af', 'ZCYMPW', '01. 회의록'),
    ('8d0414e8-8627-4287-980d-a9d9fe539242', 'RYPDYW', '02. 계획과 요구사항'),
    ('e7a50908-cf58-4f3f-ade4-1f1ff7791c48', 'ZCYMPW', '02. 계획과 요구사항'),
    ('225ea57a-1138-4043-a019-d2962a32f3e0', 'EEQFAP', '04. 배포와 운영'),
    ('7de143f0-7b5a-4e3a-862c-ba52298001a0', 'HAASFT', '04. 배포와 운영'),
    ('cf68fb67-f389-46cc-838f-b559da017856', 'VWMETX', '04. 배포와 운영'),
    ('c0961464-617e-4b75-8dcb-bb2f73259f67', 'ZCYMPW', '04. 배포와 운영'),
    ('049e2ce9-f659-4b2c-8372-e55d85a1f3b7', 'RYPDYW', '02. 계획과 요구사항'),
    ('3c8dcef3-dc72-41a8-9d5b-b038f3af3462', 'EEQFAP', '01. 회의록'),
    ('7b34ae16-194b-4aed-a79f-ccfc5a33f92b', 'HQUCQH', '02. 계획과 요구사항'),
    ('6e5079cc-1184-4c46-8c6f-82062e2a02a1', 'RYPDYW', '02. 계획과 요구사항'),
    ('59eb3738-579f-4102-b352-7b90af82ef42', 'RYPDYW', '02. 계획과 요구사항'),
    ('717226a7-35de-4e89-9497-e1d2ab3d79e5', 'ZCYMPW', '04. 배포와 운영'),
)

#: 새 공간이 필요한 프로젝트 코드 — 문서가 하나라도 옮겨가는 프로젝트만 (§14.2).
PROJECT_CODES: tuple[str, ...] = tuple(sorted({code for _id, code, _folder in RELOCATE}))


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    space_ids: dict[str, str] = {}
    for code in PROJECT_CODES:
        row = conn.execute(sa.text(
            "SELECT id, name, org_id FROM projects WHERE code = :c"
        ), {"c": code}).first()
        if row is None:
            # 이 설치에 그 프로젝트가 없으면 건너뛴다 — 추측으로 프로젝트를 만들지 않는다.
            continue
        project_id, name, org_id = row

        existing = conn.execute(sa.text(
            "SELECT id FROM knowledge_spaces"
            " WHERE owner_kind = 'project' AND owner_project_id = :p"
        ), {"p": project_id}).scalar()
        if existing:
            space_ids[code] = existing
            continue

        space_id = str(uuid.uuid4())
        conn.execute(sa.text(
            "INSERT INTO knowledge_spaces"
            " (id, org_id, name, slug, description, owner_kind, owner_dept_id,"
            "  owner_project_id, confidential, archived, created_by, version,"
            "  created_at, updated_at)"
            " VALUES (:id, :org, :name, :slug, '', 'project', NULL, :proj,"
            "  false, false, NULL, 1, :now, :now)"
        ), {
            "id": space_id, "org": org_id, "name": name, "slug": code.lower(),
            "proj": project_id, "now": now,
        })
        space_ids[code] = space_id

    for document_id, code, _folder in RELOCATE:
        if code not in space_ids:
            continue
        conn.execute(sa.text(
            "UPDATE documents SET space_id = :s, folder_id = NULL WHERE id = :d"
        ), {"s": space_ids[code], "d": document_id})


def downgrade() -> None:
    conn = op.get_bind()

    origin = conn.execute(sa.text(
        "SELECT id FROM knowledge_spaces WHERE owner_kind = 'organization' LIMIT 1"
    )).scalar()
    if origin is None:
        return  # 조직 공용 공간이 없으면 되돌릴 원래 자리가 없다 — 아무 것도 하지 않는다.

    for document_id, _code, folder_name in RELOCATE:
        folder_id = conn.execute(sa.text(
            "SELECT id FROM folders WHERE space_id = :s AND parent_id IS NULL AND name = :n"
        ), {"s": origin, "n": folder_name}).scalar()
        conn.execute(sa.text(
            "UPDATE documents SET space_id = :s, folder_id = :f WHERE id = :d"
        ), {"s": origin, "f": folder_id, "d": document_id})

    conn.execute(sa.text(
        "DELETE FROM knowledge_spaces WHERE owner_kind = 'project' AND owner_project_id IN"
        " (SELECT id FROM projects WHERE code = ANY(:codes))"
    ), {"codes": list(PROJECT_CODES)})
