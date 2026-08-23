"""티켓 채번 (D-196 · U12).

## 한 문장

`last_seq` 는 **지금까지 발급된 마지막 번호**다. 「다음 번호」가 아니다.

두 뜻이 섞이면 Migration 시드(`MAX(seq)`)와 런타임 채번이 한 칸 어긋나서 첫 신규
티켓이 마지막 기존 티켓과 같은 번호를 받는다. 그 사고는 유니크 제약이 잡아 주지만,
잡히는 자리는 사용자가 「저장」을 누른 뒤다.

## 왜 SEQUENCE 를 안 쓰나

PostgreSQL `SEQUENCE` 는 **롤백해도 번호를 되돌리지 않는다.** 티켓 생성이 실패할
때마다 구멍이 생기고, 사람이 "37번 어디 갔어?" 라고 물으면 답이 「실패한 요청이
가져갔습니다」다 — 설명은 되지만 납득은 안 된다.

`INSERT … ON CONFLICT DO UPDATE … RETURNING` 은 그 행에 **쓰기 잠금**을 건다. 같은
트랜잭션이 롤백되면 증가도 함께 돌아가고, 커밋될 때까지 다른 트랜잭션은 그 프로젝트의
다음 번호를 못 받는다. 대가는 **프로젝트별 직렬화**이고, 그것이 「번호가 연속이다」의
값이다. 티켓 생성은 초당 수천 건이 아니다.
"""

from __future__ import annotations

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.projects.models import Project

# 한 트랜잭션에서 번호를 받고 커밋하기까지 다른 요청이 기다린다. 그 대기가 무한이면
# 하나가 멈출 때 그 프로젝트의 티켓 생성이 통째로 멈춘다 — 기다릴 만큼만 기다리고
# 아니면 깨끗한 409 로 돌려보낸다.
LOCK_TIMEOUT_MS = 5000


def allocate(db: Session, project_id: str) -> int:
    """이 프로젝트의 다음 티켓 번호. **부르는 트랜잭션이 커밋해야 소비된다.**

    Key 가 없는 프로젝트에서는 번호를 주지 않는다. 주면 `canonical_key` 를 만들 수
    없고(트리거가 거부한다) 「번호는 있는데 이름이 없는 티켓」이 생긴다 — 그 상태는
    화면에서 빈 칸으로 보이고 검색으로도 안 잡힌다.
    """
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError("프로젝트를 찾을 수 없습니다.")
    if not project.code:
        raise ConflictError(
            "프로젝트 키가 아직 없어서 티켓 번호를 만들 수 없습니다. 프로젝트 키를 먼저 정해 주세요."
        )

    db.execute(sa_text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT_MS}ms'"))
    try:
        return int(
            db.execute(
                sa_text(
                    "INSERT INTO project_ticket_counters (project_id, last_seq) "
                    "VALUES (:pid, 1) "
                    "ON CONFLICT (project_id) DO UPDATE "
                    "SET last_seq = project_ticket_counters.last_seq + 1 "
                    "RETURNING last_seq"
                ),
                {"pid": project_id},
            ).scalar_one()
        )
    except Exception as exc:  # noqa: BLE001 — lock_timeout 은 깨끗한 409 로 바꾼다
        if "lock" not in str(exc).lower():
            raise
        raise ConflictError(
            "같은 프로젝트에 티켓이 몰리고 있습니다. 잠시 뒤 다시 시도해 주세요."
        ) from exc


def peek(db: Session, project_id: str) -> int:
    """지금까지 발급된 마지막 번호. 없으면 0. **잠그지 않는다** — 표시용이다."""
    value = db.execute(
        sa_text("SELECT last_seq FROM project_ticket_counters WHERE project_id = :pid"),
        {"pid": project_id},
    ).scalar_one_or_none()
    return int(value or 0)


def seed_counters(db: Session) -> int:
    """카운터를 실제 티켓 번호에 맞춘다 — `last_seq = COALESCE(MAX(seq), 0)`.

    S13 이 적재를 끝낸 직후에 부른다. 여기 없으면 첫 신규 티켓이 1번을 받고 기존
    티켓과 부딪힌다.

    **낮추지 않는다.** 이미 발급된 번호보다 작은 값으로 되돌리면 그 사이 발급된 번호가
    다시 나온다 — 티켓이 지워져서 `MAX(seq)` 가 내려간 경우가 정확히 그렇고, 외부
    식별자는 삭제 후에도 재사용하지 않는다(§5.2).
    """
    return db.execute(
        sa_text(
            "INSERT INTO project_ticket_counters (project_id, last_seq) "
            "SELECT t.project_uid, MAX(t.seq) FROM tickets t "
            "WHERE t.project_uid IS NOT NULL AND t.seq IS NOT NULL "
            "GROUP BY t.project_uid "
            "ON CONFLICT (project_id) DO UPDATE "
            "SET last_seq = GREATEST(project_ticket_counters.last_seq, EXCLUDED.last_seq)"
        )
    ).rowcount


def projects_behind(db: Session) -> int:
    """카운터가 실제 최대 번호보다 **작은** 프로젝트 수. 0 이어야 한다.

    이 질의가 여기 있는 이유는 `seed_counters` 와 같다 — 카운터를 아는 코드가 두
    곳이면 한쪽이 「다음 번호」와 「마지막 번호」를 반대로 읽고, 그 어긋남은 사용자가
    「저장」을 누른 뒤 유니크 위반으로만 드러난다(D-196).

    S13 의 Dry Run 검증이 이 값을 읽는다.
    """
    return int(
        db.execute(
            sa_text(
                "SELECT count(*) FROM ("
                "  SELECT t.project_uid AS pid, MAX(t.seq) AS mx FROM tickets t"
                "  WHERE t.project_uid IS NOT NULL AND t.seq IS NOT NULL"
                "  GROUP BY t.project_uid) s "
                "LEFT JOIN project_ticket_counters c ON c.project_id = s.pid "
                "WHERE c.last_seq IS NULL OR c.last_seq < s.mx"
            )
        ).scalar_one()
    )
