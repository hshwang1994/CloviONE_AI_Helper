"""Project Key — 규칙과 소유 대장 (§5.2 · D-196 · D-197).

## 이 파일이 지키는 문장 하나

**한 번 쓰인 Key 는 다른 프로젝트로 넘어가지 않는다.**

그 문장이 `<KEY>-<SEQ>` 가 전역에서 충돌하지 않는 유일한 근거다. Key 를 재사용하면
옛 `SKH-37` 과 새 `SKH-37` 이 같은 문자열이 되고, 그때 링크 하나가 어느 티켓을
가리키는지는 **아무도 답할 수 없다** — 트리거로도 유니크 제약으로도 못 잡는다.
그래서 해제는 `retired` 이지 삭제가 아니다.

## 이름 짓기는 자동화하지 않는다 (D-197)

`suggest()` 는 **초안만** 만든다. 실제 소유는 사람이 확인한 뒤 `claim()` 이 잡는다.
자동 배정을 안 하는 이유는 잘못 지은 Key 를 되돌릴 수 없기 때문이다 — 위 문장이
그것을 금지한다.
"""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select, text as sa_text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.models_base import utcnow
from app.projects.models import Project
from app.work.models import (
    KEY_ACTIVE,
    KEY_RESERVED,
    KEY_RETIRED,
    ALIAS_SUPERSEDED,
    ProjectKeyRegistry,
)

# 2~10자 · 영문 대문자 시작 · 대문자+숫자 (§5.2). URL 안전은 이 모양의 부산물이다 —
# 이 문자 집합에는 인코딩이 필요한 글자가 없다.
KEY_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
KEY_MIN_LEN = 2
KEY_MAX_LEN = 10

# 미리 막아 두는 이름. **`GIT` 하나뿐이다** (D-196).
#
# 옛 시스템의 티켓 번호가 `GIT-142` 이고 그것은 영구 별칭이다. 어떤 프로젝트가 Key
# 로 `GIT` 을 가져가면 새로 발급한 `GIT-142` 가 옛 `GIT-142` 와 **같은 문자열**이 되고,
# 그 순간 Resolution 순서(canonical → legacy)가 두 티켓 사이에서 조용히 갈린다.
#
# 이 목록을 넉넉하게 채우고 싶은 유혹이 있는데(`API`·`NEW`·`ADMIN` …) 지금 그럴 근거가
# 없다 — 티켓 주소는 `/tickets/:id` 하나뿐이라 경로 조각과 부딪히지 않는다. 필요해지면
# 그때 `reserve()` 로 한 줄 넣으면 되고, 그것이 이 상태가 존재하는 이유다.
RESERVED_KEYS: tuple[str, ...] = ("GIT",)


def normalize(raw: str | None) -> str:
    """사람이 친 값 → 저장형. 대소문자 무관 유일이므로 위로 맞춘다."""
    return (raw or "").strip().upper()


def validate(raw: str | None) -> str:
    """정규화한 Key. 모양이 틀리면 **왜 틀렸는지** 말한다.

    "형식이 올바르지 않습니다" 하나로 뭉치지 않는 이유: 이 값을 치는 사람은 규칙을
    외우고 있지 않다. 길이가 문제인지 첫 글자가 문제인지 모르면 시행착오가 된다.
    """
    key = normalize(raw)
    if not key:
        raise ValidationAppError("프로젝트 키를 입력해 주세요.")
    if len(key) < KEY_MIN_LEN or len(key) > KEY_MAX_LEN:
        raise ValidationAppError(
            f"프로젝트 키는 {KEY_MIN_LEN}~{KEY_MAX_LEN}자여야 합니다."
        )
    if not key[0].isascii() or not key[0].isalpha():
        raise ValidationAppError("프로젝트 키는 영문자로 시작해야 합니다.")
    if not KEY_RE.match(key):
        raise ValidationAppError("프로젝트 키에는 영문 대문자와 숫자만 쓸 수 있습니다.")
    return key


def find(db: Session, key: str) -> ProjectKeyRegistry | None:
    """대장에서 한 줄. 대소문자를 무시하고 찾는다."""
    normalized = normalize(key)
    if not normalized:
        return None
    return db.get(ProjectKeyRegistry, normalized)


def key_for(db: Session, project_id: str) -> str | None:
    """이 프로젝트가 지금 쓰는 Key. 없으면 `None`.

    정본은 `projects.code` 다 — 트리거가 그 컬럼에서 `canonical_key` 를 파생시키므로,
    대장을 읽어 답하면 둘이 갈라지는 날 화면과 DB 가 다른 말을 한다.
    """
    project = db.get(Project, project_id)
    return project.code if project is not None else None


def is_available(db: Session, key: str) -> bool:
    """아무도 쓴 적 없는 Key 인가. **`retired` 도 「쓴 적 있음」이다.**"""
    return find(db, key) is None


def reserve(db: Session, key: str, *, now: datetime | None = None) -> ProjectKeyRegistry:
    """어떤 프로젝트도 가져갈 수 없게 막는다."""
    normalized = validate(key)
    if not is_available(db, normalized):
        raise ConflictError(f"이미 등록된 프로젝트 키입니다: {normalized}")
    row = ProjectKeyRegistry(
        key=normalized, project_id=None, state=KEY_RESERVED, created_at=now or utcnow()
    )
    db.add(row)
    db.flush()
    return row


def claim(
    db: Session, *, project_id: str, key: str, now: datetime | None = None
) -> ProjectKeyRegistry:
    """이 프로젝트가 Key 를 갖는다. **처음 갖는 경우만** 이 함수다.

    이미 Key 가 있는 프로젝트는 `change()` 를 쓴다 — 옛 canonical 을 별칭으로 남기는
    일이 거기서만 일어나기 때문이다. 여기서 조용히 갈아 끼우면 옛 링크가 전부 죽는다.
    """
    normalized = validate(key)
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError("프로젝트를 찾을 수 없습니다.")
    if project.code and normalize(project.code) != normalized:
        raise ConflictError(
            f"이 프로젝트는 이미 «{project.code}» 키를 쓰고 있습니다. 키 변경으로 바꿔 주세요."
        )
    return _register(db, project=project, key=normalized, now=now or utcnow())


def register_existing(
    db: Session, *, project: Project, now: datetime | None = None
) -> ProjectKeyRegistry | None:
    """이미 `projects.code` 가 채워진 채로 만들어진 프로젝트를 **대장에 올린다**.

    프로젝트 생성 경로가 쓴다. 거기서는 행이 코드와 함께 INSERT 되고(그 유니크 제약이
    같은 조직 안의 경합을 잡는다), 그 뒤에 대장에도 같은 이름을 올려야 한다 — 안 올리면
    `projects.code` 에는 Key 가 있는데 대장은 그것을 모르는 상태가 되고, 다른 조직의
    프로젝트가 같은 이름을 가져갈 수 있다.
    """
    if not project.code:
        return None
    return _register(
        db, project=project, key=validate(project.code), now=now or utcnow()
    )


def _register(
    db: Session, *, project: Project, key: str, now: datetime
) -> ProjectKeyRegistry:
    """대장 한 줄 + `projects.code`. **여기가 Key 를 잡는 유일한 자리다.**

    사전 검사(`find`)만으로는 부족하다 — 같은 이름으로 동시에 들어온 두 요청이 둘 다
    「없음」을 볼 수 있다. SAVEPOINT 로 감싸 진 쪽의 PK 위반이 세션 전체를 망가뜨리지
    않게 하고, 사전 검사와 **같은 409** 로 두 경로를 수렴시킨다
    (`app/projects/service.py::create_project` 의 PROJ-01 과 같은 관용).
    """
    existing = find(db, key)
    if existing is not None:
        if existing.project_id == project.id and existing.state == KEY_ACTIVE:
            project.code = key
            return existing
        raise ConflictError(_taken_message(key, existing))

    row = ProjectKeyRegistry(
        key=key, project_id=project.id, state=KEY_ACTIVE, created_at=now
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except (IntegrityError, OperationalError) as exc:
        raise ConflictError(f"«{key}» 는 다른 프로젝트가 쓰고 있습니다.") from exc
    project.code = key
    db.flush()
    return row


def change(
    db: Session, *, project_id: str, key: str, now: datetime | None = None
) -> dict:
    """Project Key 를 바꾼다 — **한 트랜잭션 안의 여섯 단계** (D-195).

    ① 프로젝트를 `FOR UPDATE` 로 잠근다 ② 현 canonical 전량을 `superseded` 별칭으로
    복사한다 ③ 새 Key 를 `active` 로 등록한다 ④ 옛 Key 를 `retired` 로 둔다(**해제하지
    않는다**) ⑤ `projects.code` 를 갱신하고 `UPDATE tickets SET seq = seq` 로 트리거를
    다시 태운다 ⑥ 감사는 부르는 쪽이 남긴다.

    ②가 이 함수의 전부다. 그 복사 없이 Key 만 바꾸면 옛 `SKH-37` 링크가 **아무 데도
    닿지 않는다** — 404 가 아니라 「없는 티켓」이 되고, 그 링크는 문서·대화·메일에
    이미 뿌려져 있다.

    ①이 없으면 두 관리자가 동시에 바꿀 때 별칭 복사와 `code` 갱신이 엇갈려 한쪽의
    옛 canonical 이 별칭 없이 사라진다.
    """
    normalized = validate(key)
    stamp = now or utcnow()

    project = db.execute(
        select(Project).where(Project.id == project_id).with_for_update()
    ).scalar_one_or_none()
    if project is None:
        raise NotFoundError("프로젝트를 찾을 수 없습니다.")
    old_key = project.code
    if not old_key:
        raise ConflictError("아직 키가 없는 프로젝트입니다. 키 지정으로 먼저 부여해 주세요.")
    if old_key == normalized:
        return {"changed": False, "old_key": old_key, "new_key": normalized, "aliased": 0}

    existing = find(db, normalized)
    if existing is not None:
        raise ConflictError(_taken_message(normalized, existing))

    # ② 옛 canonical → superseded 별칭. 이미 같은 별칭이 있으면 건너뛴다(재실행 안전).
    aliased = db.execute(
        sa_text(
            "INSERT INTO ticket_key_aliases (alias, ticket_id, kind, created_at) "
            "SELECT t.canonical_key, t.id, :kind, :now FROM tickets t "
            "WHERE t.project_uid = :pid AND t.canonical_key IS NOT NULL "
            "ON CONFLICT (alias) DO NOTHING"
        ),
        {"kind": ALIAS_SUPERSEDED, "now": stamp, "pid": project_id},
    ).rowcount

    # ③ 새 Key 등록 · ④ 옛 Key 는 retired. 순서가 중요하다 — 부분 유니크
    # (`uq_pkr_active_project`)가 「프로젝트당 active 하나」를 막으므로 옛 것을 먼저 내린다.
    old_row = find(db, old_key)
    if old_row is not None:
        old_row.state = KEY_RETIRED
    db.flush()
    db.add(
        ProjectKeyRegistry(
            key=normalized, project_id=project_id, state=KEY_ACTIVE, created_at=stamp
        )
    )

    # ⑤ code 갱신 → 트리거 재계산. `SET seq = seq` 가 아무것도 안 바꾸는 것처럼 보이지만
    # BEFORE UPDATE 트리거를 태우고, 그 트리거가 canonical_key 를 새 code 로 다시 만든다.
    project.code = normalized
    db.flush()
    db.execute(
        sa_text("UPDATE tickets SET seq = seq WHERE project_uid = :pid AND seq IS NOT NULL"),
        {"pid": project_id},
    )
    return {"changed": True, "old_key": old_key, "new_key": normalized, "aliased": aliased}


def _taken_message(key: str, row: ProjectKeyRegistry) -> str:
    """왜 못 쓰는지 상태별로 말한다. 「이미 있습니다」만으로는 다음 행동이 안 정해진다."""
    if row.state == KEY_RESERVED:
        return f"«{key}» 는 예약된 키라서 쓸 수 없습니다."
    if row.state == KEY_RETIRED:
        return f"«{key}» 는 예전에 쓰던 키라서 다시 쓸 수 없습니다."
    return f"«{key}» 는 다른 프로젝트가 쓰고 있습니다."


def seed_reserved(db: Session, *, now: datetime | None = None) -> int:
    """예약어를 대장에 넣는다. 이미 있으면 건너뛴다 — 재실행해도 같은 결과다."""
    stamp = now or utcnow()
    added = 0
    for key in RESERVED_KEYS:
        if find(db, key) is None:
            db.add(
                ProjectKeyRegistry(
                    key=key, project_id=None, state=KEY_RESERVED, created_at=stamp
                )
            )
            added += 1
    db.flush()
    return added


# ── 초안 만들기 (D-197: 사람이 확인한다) ─────────────────────────────────────

# 프로젝트 이름 앞에 붙는 한 글자 구분자(`P. ` · `M. ` · `D. `). 실측한 20개 이름이
# 전부 이 모양이라 떼어 내지 않으면 초안 Key 가 전부 `P`·`M`·`D` 로 시작한다.
_NAME_PREFIX_RE = re.compile(r"^[A-Z]\.\s*")
# 이름 뒤 대괄호 안은 그 프로젝트의 **일감**이지 고객이 아니다.
_BRACKET_RE = re.compile(r"\[.*?\]")
_NON_KEY_RE = re.compile(r"[^A-Z0-9]")

# 초성 → 로마자 한 글자. 한국어 회사 이름에서 Key 후보를 뽑는 데만 쓴다.
#
# 한글 초성은 **19개**다: ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ. 한 글자라도 어긋나면
# 그 뒤 초성이 전부 한 칸씩 밀려 엉뚱한 글자가 나오는데, **오류가 아니라 그럴듯한
# 문자열**이라 눈으로는 안 잡힌다(`tests/unit/test_work_keys.py` 가 고정한다).
_CHOSUNG = "GKNDTRMBPSSOJJCKTPH"


def _romanize_initials(name: str, limit: int) -> str:
    """한글 이름의 초성을 로마자 한 글자씩. 영문·숫자는 그대로 쓴다.

    완벽한 로마자 표기를 하려는 것이 아니다 — 사람이 고를 **후보**를 만드는 것이고,
    최종 확인은 사람이 한다(D-197).
    """
    out: list[str] = []
    for ch in name:
        if len(out) >= limit:
            break
        if ch.isascii() and ch.isalnum():
            out.append(ch.upper())
            continue
        code = ord(ch) - 0xAC00
        if 0 <= code <= 11171:
            out.append(_CHOSUNG[code // 588])
    return "".join(out)


def suggest(name: str, *, taken: set[str] | None = None, limit: int = 4) -> str:
    """프로젝트 이름 → Key 초안. **확정이 아니다.**

    구분자 접두어(`M. `)와 대괄호 안 일감을 떼고 남은 고객 이름에서 뽑는다. 이미 쓰인
    후보면 뒤에 숫자를 붙인다 — 그 숫자까지 사람이 보고 고치라는 뜻이다.
    """
    used = {normalize(k) for k in (taken or set())}
    core = _BRACKET_RE.sub(" ", _NAME_PREFIX_RE.sub("", name or "")).strip()
    base = _NON_KEY_RE.sub("", _romanize_initials(core, limit))
    if len(base) < KEY_MIN_LEN:
        base = (base + "PRJ")[:KEY_MIN_LEN]
    base = base[:KEY_MAX_LEN]
    if base not in used and base not in RESERVED_KEYS:
        return base
    stem = base[: KEY_MAX_LEN - 1]
    for n in range(2, 10):
        candidate = f"{stem}{n}"
        if candidate not in used and candidate not in RESERVED_KEYS:
            return candidate
    return base
