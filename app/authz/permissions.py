"""Permission 어휘 — 「무엇을 할 수 있는가」의 최소 단위 (MASTER_PLAN §5.1 · D-193).

## 왜 역할 상수 위에 한 층을 더 얹는가

`app/core/authz.py` 의 그룹 상수(`CONSOLE_WRITE_ROLES` 등)는 **다섯 역할을 전제로 한다.**
역할이 늘어나는 순간 — 「백업만 돌릴 수 있는 계정」, 「감사 로그만 보는 외부 감사인」 —
그 상수에 이름을 하나 더 끼워 넣는 것 말고는 표현할 방법이 없고, 끼워 넣는 순간 그 역할은
그 그룹이 가진 **다른 모든 것**도 함께 갖는다. 권한을 쪼개 두면 새 역할은 권한의 조합으로
표현되고, 기존 다섯 역할은 그 조합 중 다섯 개일 뿐이다.

## 다섯 역할의 뜻은 **바뀌지 않는다**

그래서 아래 표는 새 규칙을 발명하지 않는다. 각 권한이 어느 **기존 그룹 상수**에 붙는지만
적고, 그룹의 내용은 여전히 `app/core/authz.py` 한 곳에서만 정해진다. 즉 이 파일은
「권한 → 역할」 사상(map)이고 「역할 → 사람」은 손대지 않는다.

`tests/security/test_builtin_role_equivalence.py` 가 다섯 역할 각각에 대해
**옛 게이트와 새 게이트가 같은 답을 내는지** 전수로 확인한다.

## 목록의 출처

MASTER_PLAN §5.1 의 초안 목록 그대로다. 한 건만 더했다 — `DOCUMENT_ADMIN`.
초안에는 `SPACE_ADMIN`(S7 에서 생긴다)만 있는데, D-193 이 정한 `confidential` 의 뜻
(「소유자 + 명시 부여자 + `*_ADMIN` 보유자만」)을 **지금 있는 문서**에 적용하려면 문서 축의
`*_ADMIN` 이 있어야 한다. 그 값을 `MODERATOR_ROLES` 에 붙여 현행 `restricted` 의 동작
(운영자군 + 작성자)과 정확히 같게 만든다.

## 아직 소비처가 없는 권한이 있다 — 의도한 것이다

`SPACE_*`(S7) · `STORAGE_CONFIGURE`(S8) · `AI_CONFIGURE`(S9) 는 그 Component 가 아직 없다.
`ROLE_MANAGE` 는 역할을 만들고 고치는 **화면이** 아직 없다(S20 Admin Console) — 부여·회수
자체는 `app/authz/service.py` 가 이미 할 수 있다.

어휘를 먼저 고정해 두는 이유는 그 Session 들이 **각자 새 이름을 지어 오는 것**을 막기
위해서다 — 그렇게 갈라진 이름은 나중에 한 번에 모으지 못한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.authz import (
    CONSOLE_OPS_ROLES,
    CONSOLE_READ_ROLES,
    CONSOLE_WRITE_ROLES,
    MODERATOR_ROLES,
    ROLE_ORDER,
    SENSITIVE_READ_ROLES,
    SYSTEM_ADMIN_ONLY,
)
from app.users.models import ALL_ROLES

# ── 권한 키 ──────────────────────────────────────────────────────────────────
# 문자열을 직접 적지 않는다. 오타는 **조용히 거부**로 나타나고(fail-closed),
# 그건 사람이 원인을 찾기 가장 어려운 실패다.

PROJECT_READ = "PROJECT_READ"
PROJECT_WRITE = "PROJECT_WRITE"
PROJECT_ADMIN = "PROJECT_ADMIN"

TICKET_READ = "TICKET_READ"
TICKET_CREATE = "TICKET_CREATE"
TICKET_UPDATE = "TICKET_UPDATE"
TICKET_DELETE = "TICKET_DELETE"
TICKET_TRANSITION = "TICKET_TRANSITION"

SPACE_READ = "SPACE_READ"
SPACE_WRITE = "SPACE_WRITE"
SPACE_ADMIN = "SPACE_ADMIN"

DOCUMENT_READ = "DOCUMENT_READ"
DOCUMENT_CREATE = "DOCUMENT_CREATE"
DOCUMENT_UPDATE = "DOCUMENT_UPDATE"
DOCUMENT_DELETE = "DOCUMENT_DELETE"
DOCUMENT_PUBLISH = "DOCUMENT_PUBLISH"
DOCUMENT_ADMIN = "DOCUMENT_ADMIN"

FILE_UPLOAD = "FILE_UPLOAD"
FILE_DOWNLOAD = "FILE_DOWNLOAD"
FILE_DELETE = "FILE_DELETE"

USER_MANAGE = "USER_MANAGE"
ORG_MANAGE = "ORG_MANAGE"
ROLE_MANAGE = "ROLE_MANAGE"

BACKUP_READ = "BACKUP_READ"
BACKUP_EXECUTE = "BACKUP_EXECUTE"
BACKUP_CONFIGURE = "BACKUP_CONFIGURE"

STORAGE_CONFIGURE = "STORAGE_CONFIGURE"

AI_USE = "AI_USE"
AI_CONFIGURE = "AI_CONFIGURE"

AUDIT_READ = "AUDIT_READ"
SYSTEM_CONFIGURE = "SYSTEM_CONFIGURE"
IMPERSONATE = "IMPERSONATE"


@dataclass(frozen=True)
class PermissionSpec:
    """권한 한 개. `roles` 는 **반드시 `app/core/authz.py` 의 그룹 상수**여야 한다.

    여기에 역할 이름을 손으로 나열하면 그 순간 규칙이 두 벌이 된다 —
    `tests/security/test_permission_catalog.py` 가 모든 행이 알려진 그룹과 같은 집합인지 본다.
    """

    key: str
    label: str
    area: str
    roles: tuple[str, ...]
    note: str = ""


# 「역할 게이트가 없다」는 뜻의 그룹. 그 기능이 **누구나 쓰는 기능**이라는 사실을 적는
# 자리가 필요하다 — 표에서 그 행이 빠져 있으면 「아직 안 정했다」와 구별되지 않는다.
EVERYONE: tuple[str, ...] = tuple(r for r in ROLE_ORDER if r in ALL_ROLES)


PERMISSIONS: tuple[PermissionSpec, ...] = (
    # ── 프로젝트 ─────────────────────────────────────────────────────────────
    PermissionSpec(
        PROJECT_READ, "프로젝트 조회", "프로젝트", EVERYONE,
        "역할이 아니라 범위가 정한다. 어느 프로젝트가 보이는지는 "
        "app/authz/visibility.py 가 답한다.",
    ),
    PermissionSpec(
        PROJECT_WRITE, "프로젝트 내용 편집", "프로젝트", CONSOLE_OPS_ROLES,
        "현행 app/projects/router.py 의 require_write 와 같은 집합이다.",
    ),
    PermissionSpec(
        PROJECT_ADMIN, "프로젝트 소속 변경과 삭제", "프로젝트", CONSOLE_WRITE_ROLES,
        "소속을 바꾸는 것은 편집이 아니라 조직 결정이다(app/core/ownership.py::can_manage).",
    ),
    # ── 티켓 ────────────────────────────────────────────────────────────────
    PermissionSpec(TICKET_READ, "티켓 조회", "티켓", EVERYONE),
    PermissionSpec(TICKET_CREATE, "티켓 생성", "티켓", EVERYONE),
    PermissionSpec(
        TICKET_UPDATE, "티켓 편집", "티켓", EVERYONE,
        "담당자와 작성자 판정, 그리고 프로젝트 범위가 실제 문을 지킨다. 역할로는 막지 않는다.",
    ),
    PermissionSpec(
        TICKET_DELETE, "티켓 삭제와 휴지통 이동", "티켓", MODERATOR_ROLES,
        "본인 것이 아니어도 지울 수 있는 권한이라 중재 권한과 같은 선이다.",
    ),
    PermissionSpec(TICKET_TRANSITION, "티켓 상태 전이", "티켓", EVERYONE),
    # ── Knowledge Space (S7 이 소비한다) ─────────────────────────────────────
    PermissionSpec(SPACE_READ, "지식 공간 조회", "지식", EVERYONE, "S7 에서 생긴다."),
    PermissionSpec(SPACE_WRITE, "지식 공간 편집", "지식", EVERYONE, "S7 에서 생긴다."),
    PermissionSpec(
        SPACE_ADMIN, "지식 공간 관리", "지식", CONSOLE_WRITE_ROLES,
        "S7 에서 생긴다. confidential 문서를 여는 *_ADMIN 이 이것이 된다.",
    ),
    # ── 문서 ────────────────────────────────────────────────────────────────
    PermissionSpec(DOCUMENT_READ, "문서 조회", "문서", EVERYONE),
    PermissionSpec(DOCUMENT_CREATE, "문서 생성", "문서", EVERYONE),
    PermissionSpec(DOCUMENT_UPDATE, "문서 편집", "문서", EVERYONE),
    PermissionSpec(
        DOCUMENT_DELETE, "문서 삭제와 동기화", "문서", MODERATOR_ROLES,
        "현행 app/team_docs 의 중재 경로와 같은 집합이다.",
    ),
    PermissionSpec(
        DOCUMENT_PUBLISH, "문서 발행", "문서", MODERATOR_ROLES,
        "S7 이 Version/발행을 만들 때 확정한다. 지금은 중재 권한과 같은 선에 둔다.",
    ),
    PermissionSpec(
        DOCUMENT_ADMIN, "열람 제한 문서 관리", "문서", MODERATOR_ROLES,
        "confidential 을 켜고 끄고, 켜진 문서를 볼 수 있는 권한(D-193 의 *_ADMIN).",
    ),
    # ── 파일 ────────────────────────────────────────────────────────────────
    PermissionSpec(FILE_UPLOAD, "파일 업로드", "파일", EVERYONE),
    PermissionSpec(FILE_DOWNLOAD, "파일 다운로드", "파일", EVERYONE),
    PermissionSpec(
        FILE_DELETE, "남의 첨부 삭제", "파일", MODERATOR_ROLES,
        "자기 첨부를 지우는 것은 소유권 판정이라 권한이 필요 없다.",
    ),
    # ── 사용자·조직 ──────────────────────────────────────────────────────────
    PermissionSpec(
        USER_MANAGE, "사용자 계정 관리", "사용자", CONSOLE_WRITE_ROLES,
        "대상은 언제나 자기 관리 범위 안으로 제한된다(app/core/scope.py).",
    ),
    PermissionSpec(ORG_MANAGE, "부서와 직책, 조직도 편집", "사용자", CONSOLE_WRITE_ROLES),
    PermissionSpec(
        ROLE_MANAGE, "역할과 권한 편집", "사용자", CONSOLE_WRITE_ROLES,
        "기본 제공 역할은 편집할 수 없다. 그것이 다섯 역할의 뜻을 고정한다.",
    ),
    # ── 백업·저장소 ──────────────────────────────────────────────────────────
    PermissionSpec(
        BACKUP_READ, "백업 목록과 이력 조회", "시스템", CONSOLE_READ_ROLES,
        "현행 app/backups/router.py 의 목록 게이트와 같은 집합이다.",
    ),
    PermissionSpec(BACKUP_EXECUTE, "백업 생성과 검증", "시스템", SYSTEM_ADMIN_ONLY),
    PermissionSpec(BACKUP_CONFIGURE, "백업 정책과 일정 설정", "시스템", SYSTEM_ADMIN_ONLY),
    PermissionSpec(
        STORAGE_CONFIGURE, "파일 저장소 설정", "시스템", SYSTEM_ADMIN_ONLY,
        "S8 에서 생긴다.",
    ),
    # ── AI ──────────────────────────────────────────────────────────────────
    PermissionSpec(AI_USE, "AI 질의와 작업공간 사용", "AI", EVERYONE),
    PermissionSpec(
        AI_CONFIGURE, "모델과 프롬프트, 쿼터 설정", "AI", SYSTEM_ADMIN_ONLY,
        "현행 app/llm_console 과 같은 집합이다. S9 이 Gateway 로 넓힌다.",
    ),
    # ── 감사·시스템 ──────────────────────────────────────────────────────────
    PermissionSpec(
        AUDIT_READ, "감사 로그와 민감 집계 조회", "감사", SENSITIVE_READ_ROLES,
        "사람에 대한 평가가 담기므로 운영자를 뺀다.",
    ),
    PermissionSpec(
        SYSTEM_CONFIGURE, "시스템 설정(TLS, 호스트 이름, 서비스 제어)", "시스템", SYSTEM_ADMIN_ONLY,
        "바뀌는 대상이 서버 한 대 전체라 admin_scope 라는 개념 자체가 없다.",
    ),
    PermissionSpec(
        IMPERSONATE, "대리 보기 시작", "사용자", CONSOLE_WRITE_ROLES,
        "운영자는 남의 화면을 볼 수 없다. 감사자는 기록 조회만 할 수 있다.",
    ),
)

ALL_PERMISSION_KEYS: frozenset[str] = frozenset(p.key for p in PERMISSIONS)

PERMISSION_BY_KEY: dict[str, PermissionSpec] = {p.key: p for p in PERMISSIONS}


def _builtin_map() -> dict[str, frozenset[str]]:
    out: dict[str, set[str]] = {role: set() for role in ALL_ROLES}
    for spec in PERMISSIONS:
        for role in spec.roles:
            out.setdefault(role, set()).add(spec.key)
    return {role: frozenset(keys) for role, keys in out.items()}


# 기본 제공 역할 다섯의 권한 집합. **여기서 역할 이름을 나열하지 않는다** — 위 표의
# 그룹 상수를 뒤집어 만든다. 그래서 그룹이 바뀌면 이 사상도 함께 바뀐다.
BUILTIN_ROLE_PERMISSIONS: dict[str, frozenset[str]] = _builtin_map()


def permissions_for_role(role: str) -> frozenset[str]:
    """기본 제공 역할 하나의 권한 집합. 모르는 역할은 **빈 집합**(fail-closed)."""
    return BUILTIN_ROLE_PERMISSIONS.get(role, frozenset())
