"""기술 태그를 다시 세운다 — 프로젝트성·업무분류 옛 태그를 정리하고 문서가 실제로 다루는
기술로 다시 붙인다 (재검수 묶음2 §13).

Revision ID: 0024_technology_tags
Revises: 0023_project_knowledge_spaces
Create Date: 2026-08-28

## 무엇이 문제였나

지금 태그 19개는 「이 문서가 어떤 기술을 다루는가」에 답하지 못한다. 8개는 프로젝트
이름을 그대로 베꼈고(0023이 `knowledge_spaces.owner_project_id`로 그 축을 대신한다),
10개는 "고객 프로젝트"·"인프라"·"제품 및 플랫폼"처럼 업무 분류이지 기술이 아니다(폴더가
이미 그 축을 담당한다 — 0022). "docker" 하나만 실제 기술 태그이지만 소문자다.

## 매핑 방법 — 문자열 포함이 아니라 실제로 읽었다 (§13.4)

이 마이그레이션 설계 시점에 랩 서버(`clovirassist.gooddi.lab`)에 실제로 배포된 문서
111건을 `GET /api/knowledge/documents/{id}` 로 읽어 제목 + 본문(`body_markdown`)에서
§13.2가 든 후보 기술 43개의 등장을 확인했다. 순수 문자열 포함이 실수를 만드는 자리
(`Git`이 `GitLab`의 일부로 잡히는 것, `Java`가 `JavaScript`의 일부로 잡히는 것, `AD`가
흔한 두 글자라 아무 문장에나 걸리는 것)는 단어 경계·구체적 표현(`adfs`·`active
directory`처럼)으로 피했다. 43개 후보 중 이 문서 111건에 실제로 한 번이라도 등장한
것은 41개다 — `React`·`FastAPI`는 등장하지 않아 만들지 않는다(§13.2 "고정 목록이
아니다 — 근거 없는 것은 만들지 않는다").

그 결과가 `DOC_TAGS` — 문서 80건 · 태그 연결 253개. 나머지 31건은 기술 언급이 없는
문서(회의 일정 조율, 조직 개편 등)라 기술 태그가 없는 것이 맞는 상태다. 한 문서 최대
태그 수는 14개로 `TAG_MAX_PER_DOCUMENT`(20, `app/knowledge/tags.py`) 안이다.

## 순서 — §13 이 정한 그대로

1. 기술 태그(`DOC_TAGS` 에 쓰인 이름 전부, 41개)를 만든다. 이미 같은 slug 가 있으면
   그것을 쓴다 — `docker` 는 slug 가 이미 `docker` 라 새로 안 만들고 3단계에서
   이름만 고친다.
2. `DOC_TAGS` 로 문서-태그 연결을 붙인다.
3. `docker` → `Docker` 로 이름을 바로잡는다(slug 는 `casefold` 라 그대로 `docker`).
4. **연결을 먼저 끊는다** — 프로젝트성 8개·업무분류 10개(`OLD_TAG_LINKS`에 쓰인 18개
   태그 이름)의 문서 연결(`document_tags`)을 지운다.
5. **태그를 나중에 지운다** — 그 18개 태그 행 자체를 지운다. 0023이 만든 프로젝트
   공간이 이미 실제 프로젝트 연결을 대신하고, 0022의 폴더가 이미 업무 분류를 대신한다.

## 세 프로젝트에 동시에 걸린 문서 하나

`aa665d4b`(SCM(Source Code Management) 전략)는 0023이 공용 공간에 남긴 문서다(그
마이그레이션의 docstring 참고). 이 마이그레이션에서도 특별 취급은 없다 — 기술 태그
(Aria·Jenkins·GitLab·Ansible)는 다른 문서와 똑같이 받고(`DOC_TAGS` 에 있다), 프로젝트성
태그 셋은 다른 문서와 똑같이 끊긴다(`OLD_TAG_LINKS` 에도 있다). 그 문서는 이후 어느
프로젝트 문서 탭에도 안 나타나고 공용 문서 목록에만 나온다 — 셋 중 하나를 임의로 골라
나머지 둘의 맥락을 지우는 것보다 낫다는 판단이다.

## 되감기

기술 태그 41개와 그 연결을 지우고 `Docker` → `docker` 로 되돌린 뒤, `OLD_TAG_LINKS` 로
옛 18개 태그를 다시 만들어 원래 문서에 다시 붙인다. 이 되돌린 태그의 `created_at` 은
되감기를 실행한 시각으로 새로 찍힌다 — 0022의 폴더 되감기와 같은 수준이다(완전한
시점 복원이 아니라 기능적 복원).
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = '0024_technology_tags'
down_revision = '0023_project_knowledge_spaces'
branch_labels = None
depends_on = None

_SPACE_RE = re.compile(r"\s+")


def _slugify(name: str) -> str:
    """`app/knowledge/tags.py::slugify` 와 동일한 규칙이다. 마이그레이션은 그 시점의 앱
    모듈이 아니라 이 규칙 자체(NFKC 정규화 + 공백 접기 + casefold)에 의존해야 하므로
    여기 다시 적는다 — 앱 코드가 나중에 바뀌어도 이미 적용된 마이그레이션은 안 바뀐다."""
    folded = unicodedata.normalize("NFKC", name or "").strip().casefold()
    return _SPACE_RE.sub(" ", folded)


# 문서(8자 id prefix — 111건 전부에서 유일함을 확인했다) → 실제로 다루는 기술 태그.
DOC_TAGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('a92fb3a6', ('GPU',)),
    ('bf28ff1d', ('Git',)),
    ('c3150c3b', ('Aria', 'Ubuntu')),
    ('a4bc4119', ('vSphere', 'ESXi', 'VCF', 'NSX', 'Aria', 'Ansible')),
    ('ff8b2d29', ('Aria', 'Kubernetes', 'GPU')),
    ('0564d161', ('Kubernetes', 'GPU')),
    ('77e292fe', ('AD/ADFS',)),
    ('e26d2b6c', ('GPU',)),
    ('ceda62b4', ('vSphere', 'Windows')),
    ('5d4b3361', ('VMware', 'vSphere', 'Linux', 'Rocky', 'Cloud-init')),
    ('4a78321d', ('GPU',)),
    ('012db2f9', ('Windows', 'MariaDB')),
    ('1c84e018', ('ESXi', 'Ansible', 'Redfish')),
    ('e5a9a6fc', ('NSX', 'GPU')),
    ('58f7bcd0', ('AD/ADFS',)),
    ('f3a7edc6', ('GitLab',)),
    ('6718b7aa', ('AD/ADFS', 'SSL/TLS')),
    ('a423b02d', ('VCF', 'Aria')),
    ('71d6bda3', ('VMware', 'vSphere', 'VCF', 'NSX')),
    ('e7898a9d', ('GPU',)),
    ('0ff28696', ('GPU',)),
    ('661d8fe1', ('Docker', 'Linux', 'MariaDB', 'PostgreSQL')),
    ('787b73bc', ('Docker', 'Tomcat', 'Java', 'SSL/TLS')),
    ('d0486bdd', ('Docker', 'Ubuntu')),
    ('4262f4fd', ('Docker', 'Nginx', 'SSL/TLS')),
    ('11576247', ('ESXi', 'Cisco ACI')),
    ('b9ce4b3f', ('Linux', 'PostgreSQL', 'Java', 'Python', 'Cisco ACI', 'L4', 'SSL/TLS', 'Prometheus', 'Grafana')),
    ('cb306d4e', ('VMware', 'containerd', 'Docker', 'Git', 'Ansible', 'Linux', 'Rocky', 'Ubuntu', 'Windows', 'PostgreSQL', 'Nginx', 'Python', 'SSL/TLS')),
    ('e3eb8bf8', ('Docker', 'Linux', 'Windows', 'MariaDB', 'PostgreSQL', 'Redis', 'Nginx', 'Tomcat')),
    ('336514d0', ('Linux', 'Ubuntu', 'LVM')),
    ('599b28b7', ('vSphere',)),
    ('35a6c3a6', ('Docker',)),
    ('d3be62a6', ('Kubernetes', 'Docker', 'Redis', 'Nginx', 'TCP/IP')),
    ('9f18a32f', ('VMware', 'ESXi', 'Cisco ACI', 'KVM')),
    ('7820ca0c', ('Tanzu', 'Kubernetes', 'Windows', 'Palo Alto', 'KVM')),
    ('130c29ab', ('Nginx', 'SSL/TLS')),
    ('bb03e412', ('Linux', 'Windows')),
    ('7a8706d9', ('Docker',)),
    ('928aaa76', ('VMware', 'Docker', 'Linux')),
    ('3635482b', ('vSphere', 'Docker', 'MariaDB', 'Nginx', 'Cisco ACI')),
    ('2ced9e51', ('VCF',)),
    ('96b1b6c3', ('ESXi', 'Aria', 'GPU')),
    ('0fe64068', ('VCF',)),
    ('bbc22b66', ('Docker', 'Linux')),
    ('d038ad95', ('Kubernetes', 'Tomcat')),
    ('23940fb6', ('VMware', 'vSphere', 'VCF', 'Docker', 'Ubuntu', 'Windows', 'Nginx', 'SSL/TLS')),
    ('27e2184f', ('Docker', 'Redis', 'Spring', 'Java')),
    ('5edf0e08', ('VMware', 'vSphere', 'Docker', 'Ansible', 'Linux', 'Windows', 'MariaDB', 'Nginx', 'Tomcat', 'Java', 'SSL/TLS')),
    ('e063bfca', ('VCF', 'GPU')),
    ('6494b35b', ('GPU',)),
    ('bbeb3063', ('Jenkins', 'Git', 'Ansible', 'Nginx')),
    ('8d7d5927', ('Jenkins', 'Git', 'Ansible', 'Nginx')),
    ('8810d47f', ('Linux', 'SSL/TLS')),
    ('aa665d4b', ('Aria', 'Jenkins', 'GitLab', 'Ansible')),
    ('8d0414e8', ('Tanzu', 'Kubernetes')),
    ('776a2a83', ('Docker', 'Jenkins', 'Nginx', 'SSL/TLS')),
    ('ba381735', ('Ansible', 'Oracle', 'Nginx')),
    ('cfda0763', ('VMware', 'Docker', 'Jenkins', 'Git', 'PostgreSQL', 'Spring', 'Java', 'KVM')),
    ('e7a50908', ('VCF',)),
    ('fef98b25', ('VMware', 'ESXi', 'Aria', 'Kubernetes', 'Docker', 'Jenkins', 'Ansible', 'Redfish', 'MariaDB', 'Redis', 'Spring', 'Java', 'GPU', 'Prometheus')),
    ('225ea57a', ('Kubernetes',)),
    ('7de143f0', ('Nginx',)),
    ('cf68fb67', ('vSphere', 'Kubernetes', 'Git', 'Windows', 'Tomcat', 'Java')),
    ('dbb44694', ('Windows', 'Nginx', 'TCP/IP')),
    ('dc0262a5', ('Kubernetes', 'GPU')),
    ('c0961464', ('ESXi', 'Redfish')),
    ('8f34850a', ('Jenkins', 'GitLab', 'Ansible')),
    ('049e2ce9', ('Tanzu', 'Kubernetes')),
    ('3c8dcef3', ('Kubernetes', 'GPU')),
    ('54cc4c61', ('Oracle', 'MariaDB', 'Java')),
    ('e4cf58d5', ('ESXi', 'Oracle', 'MariaDB', 'Java')),
    ('dea57b2c', ('Jenkins', 'GitLab', 'Git', 'SSL/TLS')),
    ('e85c8cf8', ('Docker', 'Oracle')),
    ('78d84d63', ('Tanzu', 'Kubernetes', 'SSL/TLS')),
    ('6e5079cc', ('Windows', 'MariaDB')),
    ('f5eaede7', ('Kubernetes', 'MicroK8s', 'containerd')),
    ('3bfdd68f', ('MariaDB',)),
    ('59eb3738', ('Windows',)),
    ('717226a7', ('Ubuntu', 'Oracle', 'Tomcat', 'Spring', 'Java')),
    ('88664e96', ('Tomcat',)),
)

# 문서(8자 id prefix) → 프로젝트성 8개·업무분류 10개 중 이 문서에 실제로 붙어 있던 것.
# upgrade() 는 이 연결을 끊고 태그 자체를 지운다. downgrade() 는 이 데이터로 되살린다.
OLD_TAG_LINKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('a92fb3a6', ('고객 프로젝트', '포스코DX [P-Cloud 2.0 포털 구축]')),
    ('bf28ff1d', ('인천국제공항공사 [클라우드 인프라 고도화]', '고객 프로젝트')),
    ('c3150c3b', ('고객 프로젝트', '스마일게이트홀딩스 [ClovirONE 2.0 포털 구축]')),
    ('a4bc4119', ('고객 프로젝트',)),
    ('ff8b2d29', ('고객 프로젝트', '포스코DX [P-Cloud 2.0 포털 구축]')),
    ('0564d161', ('고객 프로젝트', '포스코DX [P-Cloud 2.0 포털 구축]')),
    ('9fb48bc8', ('데이터 모니터링', '현대모비스 [MDIP 시스템 운영/개선]')),
    ('77e292fe', ('제품 및 플랫폼', 'KB국민카드 [빅데이터 포털 내부시스템 EOS/디자인 변경]')),
    ('e26d2b6c', ('고객 프로젝트',)),
    ('ceda62b4', ('인프라',)),
    ('5d4b3361', ('인프라',)),
    ('4a78321d', ('인천국제공항공사 [클라우드 인프라 고도화]', '고객 프로젝트')),
    ('2c9e4ec5', ('제품 및 플랫폼', '굿모닝아이텍 [ClovirONE 2.0 제품 개발]')),
    ('c3ed37af', ('제품 및 플랫폼', '굿모닝아이텍 [ClovirONE 2.0 제품 개발]')),
    ('012db2f9', ('자동화 엔지니어링',)),
    ('1c84e018', ('인프라', '자동화 엔지니어링', '제품 및 플랫폼')),
    ('e5a9a6fc', ('고객 프로젝트', '포스코DX [P-Cloud 2.0 포털 구축]')),
    ('58f7bcd0', ('고객 프로젝트', 'KB국민카드 [빅데이터 포털 내부시스템 EOS/디자인 변경]')),
    ('f3a7edc6', ('운영 유지보수',)),
    ('6718b7aa', ('고객 프로젝트', 'KB국민카드 [빅데이터 포털 내부시스템 EOS/디자인 변경]')),
    ('baeb4ca1', ('고객 프로젝트', '포스코DX [P-Cloud 2.0 포털 구축]')),
    ('a423b02d', ('고객 프로젝트', '포스코DX [P-Cloud 2.0 포털 구축]')),
    ('71d6bda3', ('인프라',)),
    ('e7898a9d', ('고객 프로젝트', '포스코DX [P-Cloud 2.0 포털 구축]')),
    ('0ff28696', ('고객 프로젝트', '포스코DX [P-Cloud 2.0 포털 구축]')),
    ('661d8fe1', ('인천국제공항공사 [클라우드 인프라 고도화]', '보안 컴플라이언스')),
    ('787b73bc', ('인천국제공항공사 [클라우드 인프라 고도화]', '보안 컴플라이언스')),
    ('250e9239', ('인천국제공항공사 [클라우드 인프라 고도화]', '보안 컴플라이언스')),
    ('d0486bdd', ('인천국제공항공사 [클라우드 인프라 고도화]', '보안 컴플라이언스')),
    ('a716c863', ('행정 관리',)),
    ('4262f4fd', ('인천국제공항공사 [클라우드 인프라 고도화]', '보안 컴플라이언스')),
    ('77f25358', ('고객 프로젝트', '포스코DX [P-Cloud 2.0 포털 구축]')),
    ('11576247', ('인천국제공항공사 [클라우드 인프라 고도화]', '고객 프로젝트')),
    ('b9ce4b3f', ('인천국제공항공사 [클라우드 인프라 고도화]', '지식 레퍼런스')),
    ('cb306d4e', ('인프라', '배포 관리', '운영 유지보수', '제품 및 플랫폼')),
    ('c59a739d', ('고객 프로젝트', 'KB국민카드 [빅데이터 포털 내부시스템 EOS/디자인 변경]')),
    ('599b28b7', ('고객 프로젝트', '제품 및 플랫폼', 'SK하이닉스 [용인 클러스터 대비]')),
    ('9f18a32f', ('인천국제공항공사 [클라우드 인프라 고도화]', '지식 레퍼런스')),
    ('bb03e412', ('인천국제공항공사 [클라우드 인프라 고도화]',)),
    ('928aaa76', ('고객 프로젝트',)),
    ('cdd39f0c', ('고객 프로젝트', 'KB국민카드 [빅데이터 포털 내부시스템 EOS/디자인 변경]')),
    ('bbc22b66', ('배포 관리', '지식 레퍼런스', '제품 및 플랫폼')),
    ('0a030622', ('고객 프로젝트',)),
    ('d038ad95', ('고객 프로젝트', '암센터 [NCDC 데이터 분석 포털 구축]')),
    ('23940fb6', ('고객 프로젝트',)),
    ('27e2184f', ('배포 관리',)),
    ('8d7d5927', ('고객 프로젝트',)),
    ('aa665d4b', ('지식 레퍼런스', '스마일게이트홀딩스 [ClovirONE 2.0 포털 구축]', '포스코DX [P-Cloud 2.0 포털 구축]', 'SK하이닉스 [용인 클러스터 대비]')),
    ('8d0414e8', ('고객 프로젝트',)),
    ('776a2a83', ('인프라',)),
    ('1d89b3e0', ('제품 및 플랫폼',)),
    ('cfda0763', ('제품 및 플랫폼',)),
    ('e7a50908', ('고객 프로젝트', 'SK하이닉스 [용인 클러스터 대비]')),
    ('dbb44694', ('인프라',)),
    ('c0961464', ('배포 관리',)),
    ('049e2ce9', ('고객 프로젝트',)),
    ('3c8dcef3', ('운영 유지보수',)),
    ('7b34ae16', ('운영 유지보수',)),
    ('6e5079cc', ('운영 유지보수',)),
    ('717226a7', ('SK하이닉스 [용인 클러스터 대비]',)),
    ('88664e96', ('운영 유지보수',)),
)

REMOVED_TAG_NAMES: tuple[str, ...] = tuple(sorted({
    name for _prefix, names in OLD_TAG_LINKS for name in names
}))


def _resolve_document_id(conn, prefix: str) -> str | None:
    """`None` 이면 이 설치에 그 문서가 없다는 뜻이다 — 이관 전 빈 스키마 · 시험용 seed
    데이터 · 이미 지워진 문서 전부 같은 경우다. 부르는 쪽이 건너뛴다(추측으로 만들지
    않는다, 0023 이 모르는 프로젝트 코드를 건너뛰는 것과 같은 원칙)."""
    return conn.execute(
        sa.text("SELECT id FROM documents WHERE id LIKE :p"), {"p": f"{prefix}%"}
    ).scalar()


def _document_org_id(conn, document_id: str):
    return conn.execute(sa.text(
        "SELECT s.org_id FROM documents d JOIN knowledge_spaces s ON s.id = d.space_id"
        " WHERE d.id = :d"
    ), {"d": document_id}).scalar()


def _ensure_tag(conn, cache: dict, org_id, name: str, now) -> str:
    slug = _slugify(name)
    key = (org_id, slug)
    if key in cache:
        return cache[key]
    tag_id = conn.execute(sa.text(
        "SELECT id FROM tags WHERE slug = :s"
        " AND ((org_id IS NULL AND CAST(:o AS varchar) IS NULL) OR org_id = :o)"
    ), {"s": slug, "o": org_id}).scalar()
    if tag_id is None:
        tag_id = str(uuid.uuid4())
        conn.execute(sa.text(
            "INSERT INTO tags (id, org_id, name, slug, created_at)"
            " VALUES (:id, :o, :n, :s, :now)"
        ), {"id": tag_id, "o": org_id, "n": name, "s": slug, "now": now})
    cache[key] = tag_id
    return tag_id


def _link(conn, document_id: str, tag_id: str, now) -> None:
    conn.execute(sa.text(
        "INSERT INTO document_tags (document_id, tag_id, created_at)"
        " VALUES (:d, :t, :now)"
        " ON CONFLICT (document_id, tag_id) DO NOTHING"
    ), {"d": document_id, "t": tag_id, "now": now})


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    tag_cache: dict = {}

    for prefix, tag_names in DOC_TAGS:
        document_id = _resolve_document_id(conn, prefix)
        if document_id is None:
            continue
        org_id = _document_org_id(conn, document_id)
        for name in tag_names:
            tag_id = _ensure_tag(conn, tag_cache, org_id, name, now)
            _link(conn, document_id, tag_id, now)

    conn.execute(sa.text(
        "UPDATE tags SET name = 'Docker' WHERE slug = 'docker' AND name <> 'Docker'"
    ))

    for prefix, tag_names in OLD_TAG_LINKS:
        document_id = _resolve_document_id(conn, prefix)
        if document_id is None:
            continue
        for name in tag_names:
            slug = _slugify(name)
            conn.execute(sa.text(
                "DELETE FROM document_tags WHERE document_id = :d AND tag_id IN"
                " (SELECT id FROM tags WHERE slug = :s)"
            ), {"d": document_id, "s": slug})

    for name in REMOVED_TAG_NAMES:
        slug = _slugify(name)
        conn.execute(sa.text("DELETE FROM tags WHERE slug = :s"), {"s": slug})


def downgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    tag_cache: dict = {}

    # 기술 태그를 지운다 — `Docker` 는 원래 있던 태그(옛 `docker`)라 지우지 않고
    # 이름만 되돌린다.
    tech_names = sorted({name for _prefix, names in DOC_TAGS for name in names})
    for name in tech_names:
        if name == 'Docker':
            continue
        slug = _slugify(name)
        conn.execute(sa.text("DELETE FROM tags WHERE slug = :s"), {"s": slug})

    conn.execute(sa.text("UPDATE tags SET name = 'docker' WHERE slug = 'docker'"))

    for prefix, tag_names in OLD_TAG_LINKS:
        document_id = _resolve_document_id(conn, prefix)
        if document_id is None:
            continue
        org_id = _document_org_id(conn, document_id)
        for name in tag_names:
            tag_id = _ensure_tag(conn, tag_cache, org_id, name, now)
            _link(conn, document_id, tag_id, now)
