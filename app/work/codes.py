"""Project Code — 서버가 짓고, 사람은 고칠 수 없다 (D-282 · D-283).

## 이 파일이 지키는 문장 하나

**프로젝트 코드는 서버가 지은 대문자 여섯 글자이고, 한 번 붙으면 그 프로젝트의 것이다.**

그 문장이 `<CODE>-<SEQ>` 가 전역에서 충돌하지 않는 근거다. 코드가 바뀌면 옛
`ABCDEF-37` 링크가 아무 데도 닿지 않고, 코드를 재사용하면 옛 `ABCDEF-37` 과 새
`ABCDEF-37` 이 같은 문자열이 되어 **어느 티켓인지 아무도 답할 수 없다.**

그래서 이 파일에는 코드를 바꾸는 함수가 없다. 짓는 함수와 모양을 재는 함수뿐이다.

## 왜 사람이 안 짓는가

앞 정책은 사람이 20건을 손으로 확정했다(옛 D-197 · D-243). 그 방식은 세 가지를 요구했다
— 이름마다 사람의 판단, 그 판단을 코드와 문서 두 곳에 옮겨 적기, 그리고 소스의 이름이
바뀔 때마다 표를 다시 맞추기. 마지막 것이 실제로 터졌다: 확정 하루 뒤 소스가 접두사를
빼자 20건 **전부**가 «못 찾음» 이 됐다(옛 D-278).

서버가 지으면 그 셋이 전부 사라진다. 이름은 코드의 근거가 아니므로 **프로젝트 이름을
바꿔도 코드와 티켓 번호는 한 글자도 안 움직인다.**

## 글자 스물셋 — `I` · `L` · `O` 가 없다

`ABCDEFGHJKMNPQRSTUVWXYZ`. 빠진 셋은 사람이 `1` · `1` · `0` 과 헷갈리는 글자다. 코드는
사람이 말로 부르고 손으로 옮겨 적는 값이라("MDIP 사십이번 봐 주세요") 그 혼동이 실제로
잘못된 티켓을 연다. 숫자를 아예 안 쓰는 것도 같은 이유다 — 숫자가 없으면 `<CODE>-<SEQ>`
에서 어디까지가 코드인지 눈으로 바로 갈린다.

23⁶ = 148,035,889 가지다. 프로젝트 수천 개에서도 충돌은 사실상 일어나지 않지만,
「사실상」은 계약이 아니므로 아래 `assign_*` 이 실제로 다시 짓는다.

## 왜 무작위가 아니라 **씨앗에서 파생**하는가

이관이 두 번 돈다. 임시 DB 로 가는 Dry Run 과 운영으로 가는 Cutover 다. 그 둘은 **서로
다른 데이터베이스**이므로, 코드를 무작위로 지으면 같은 프로젝트가 Dry Run 에서
`ABCDEF`, Cutover 에서 `QRSTUV` 를 받는다. 그러면 Dry Run 이 검증한 티켓 이름 1,133개가
Cutover 에서 전부 다른 문자열이 되고, **Dry Run 이 증명한 것이 Cutover 에서 성립하지
않는다.**

그래서 코드는 씨앗의 SHA-256 에서 파생한다. 씨앗은 **소스가 주는 안 변하는 값**이다 —
Notion 페이지 id 가 있으면 그것, 없으면 SQLite 가 준 `projects.id`. 둘 다 두 회차가
같은 소스를 읽으므로 같은 값이고, 따라서 같은 프로젝트가 두 DB 에서 같은 코드를 받는다.

런타임에 새로 만드는 프로젝트도 같은 함수를 쓴다. 씨앗은 그 행의 uuid 이고, uuid 는
이미 무작위라 결과도 무작위다 — **경로가 하나라서 시험도 하나다.**
"""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.core.models_base import new_uuid
from app.projects.models import Project

# 사람이 헷갈리는 `I`·`L`·`O` 를 뺀 대문자 스물셋. **순서가 계약이다** — 이 문자열의
# 순서가 바뀌면 같은 씨앗이 다른 코드를 내고, 그 순간 Dry Run 과 Cutover 가 갈린다.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 6

# 재시도 상한. 충돌 확률이 프로젝트 만 건에서도 3×10⁻⁴ 수준이라 이 수를 다 쓰는 일은
# 없다 — 그런데도 상한을 두는 이유는, 없으면 유니크 제약이 아닌 **다른 이유**로 INSERT
# 가 계속 실패할 때 이 함수가 영원히 돈다는 것이다.
MAX_ATTEMPTS = 32

# DB 의 `ck_projects_code_shape` 와 **같은 모양**이다. 둘이 갈라지면 앱이 만든 코드를
# DB 가 거절하거나, DB 가 받은 코드를 앱이 못 읽는다.
_ALPHABET_SET = frozenset(CODE_ALPHABET)


def is_valid(code: str | None) -> bool:
    """이 문자열이 Project Code 의 모양인가. **정규화하지 않는다.**

    소문자를 대문자로 고쳐서 통과시키면 「사람이 친 값을 받는 자리」가 생긴다. 이 값을
    치는 사람은 없다 — 서버만 짓는다.
    """
    if not code or len(code) != CODE_LENGTH:
        return False
    return all(ch in _ALPHABET_SET for ch in code)


def derive(seed: str, attempt: int = 0) -> str:
    """씨앗 → 코드 여섯 글자. **같은 씨앗과 같은 회차면 언제나 같은 값이다.**

    `attempt` 는 충돌했을 때 다음 후보를 만드는 손잡이다. 무작위로 다시 뽑지 않는 이유:
    다시 뽑으면 그 프로젝트의 코드가 회차마다 달라지고, 그것이 바로 이 파일이 막으려는
    상태다. 충돌은 회차 번호로 푼다 — 같은 소스를 읽는 두 회차는 같은 순서로 충돌하고
    같은 순서로 푼다.
    """
    digest = hashlib.sha256(f"{seed}\x00{attempt}".encode()).digest()
    value = int.from_bytes(digest, "big")
    out: list[str] = []
    for _ in range(CODE_LENGTH):
        value, index = divmod(value, len(CODE_ALPHABET))
        out.append(CODE_ALPHABET[index])
    return "".join(out)


def taken(db: Session) -> set[str]:
    """지금 어떤 프로젝트가 쓰고 있는 코드 전부. **보관된 프로젝트도 센다.**

    보관은 소프트 삭제라(`projects.archived_at`) 행이 남는다 — 그 코드를 다시 내주면
    보관된 프로젝트의 옛 티켓 이름과 새 프로젝트의 티켓 이름이 같은 문자열이 된다.
    """
    rows = db.execute(select(Project.code).where(Project.code.is_not(None))).scalars()
    return {value for value in rows if value}


def insert_with_code(db: Session, project: Project, *, seed: str | None = None) -> Project:
    """새 프로젝트를 **코드와 함께** 넣는다. 겹치면 다시 짓는다.

    사전 조회(`taken`)만으로는 부족하다 — 같은 코드를 동시에 만든 두 요청이 둘 다
    「없음」을 볼 수 있다. SAVEPOINT 로 감싸 진 쪽의 유니크 위반이 세션 전체를 망가뜨리지
    않게 하고, 그 자리에서 **다음 후보로 다시 짓는다.** 사용자에게 409 를 돌려주지 않는
    이유: 사용자는 코드를 고르지 않았으므로 「이미 있는 코드입니다」가 무엇을 고치라는
    말인지 알 수 없다.
    """
    if not project.id:
        # `id` 는 flush 때 채워지는 기본값이라 아직 비어 있다. 여기서 먼저 정해 둔다 —
        # 씨앗으로 쓸 값이 필요하고, 무엇보다 SAVEPOINT 를 되감고 다시 넣을 때마다
        # **같은 행**이어야 한다.
        project.id = new_uuid()
    base = seed or project.id
    for attempt in range(MAX_ATTEMPTS):
        project.code = derive(base, attempt)
        try:
            with db.begin_nested():
                db.add(project)
                db.flush()
        except (IntegrityError, OperationalError) as exc:
            if not _is_code_conflict(exc):
                raise
            continue
        return project
    raise ConflictError("프로젝트 코드를 만들지 못했습니다. 잠시 뒤 다시 시도해 주세요.")


def assign_many(
    db: Session, projects: list[Project], *, seed_of=None
) -> dict[str, str]:
    """코드가 없는 프로젝트에 한꺼번에 붙인다 — 이관이 쓴다. **재실행해도 같다.**

    이미 코드가 있는 프로젝트는 **건드리지 않는다.** 그것이 재실행 안전의 전부다: 2회차는
    아무것도 안 바꾸고, 그래서 1회차가 검증한 티켓 이름이 그대로 남는다.

    처리 순서를 씨앗으로 정렬하는 이유는 충돌 때문이다. 두 프로젝트가 같은 코드를 뽑으면
    한쪽이 다음 회차로 밀리는데, **누가 밀리는지가 회차마다 달라지면** Dry Run 과 Cutover
    가 갈린다. 정렬해 두면 같은 소스를 읽는 두 회차가 같은 쪽을 민다.
    """
    resolved = dict(seed_of or {})
    used = taken(db)
    assigned: dict[str, str] = {}
    pending = [p for p in projects if not p.code]
    pending.sort(key=lambda p: (resolved.get(p.id) or p.id, p.id))
    for project in pending:
        base = resolved.get(project.id) or project.id
        for attempt in range(MAX_ATTEMPTS):
            candidate = derive(base, attempt)
            if candidate in used:
                continue
            project.code = candidate
            used.add(candidate)
            assigned[project.id] = candidate
            break
        else:
            raise ConflictError(
                f"프로젝트 코드를 만들지 못했습니다: {project.id}"
            )
    db.flush()
    return assigned


def _is_code_conflict(exc: Exception) -> bool:
    """이 오류가 **코드가 겹쳐서** 난 것인가.

    다른 유니크 위반(이름·조직)을 코드 충돌로 읽으면 이 함수가 고칠 수 없는 것을 고치려고
    32번 돈 뒤 엉뚱한 메시지로 실패한다. 제약 이름으로 좁힌다.
    """
    text = str(getattr(exc, "orig", exc)).lower()
    return "uq_projects_code" in text
