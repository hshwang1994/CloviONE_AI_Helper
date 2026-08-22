"""프로젝트 Notion 양방향 동기화 (0045). `app/tickets/sync.py` 와 같은 구조다.

읽기(Notion → 앱)는 워커가 주기적으로 프로젝트 DB 를 통째로 읽어 `projects` 에 반영하고,
쓰기(앱 → Notion)는 포털에서 이름·상태·기간·담당자를 고칠 때 그 자리에서 push 한다.

**예외는 절대 밖으로 나가지 않는다.** 워커 tick 이 죽으면 같은 루프의 스케줄러·하트비트·
승인 만료·문서 동기화가 전부 함께 멈춘다. fetch 뿐 아니라 upsert/prune/flush 까지 통째로
가둔다(티켓 sync 와 같은 이유).

## 티켓 미러와 다른 점 세 가지

1. **앱 DB 가 정본이다.** `projects` 는 미러가 아니라 자체 표다(0044). 그래서 동기화가 손대는
   컬럼을 좁게 정해 두고(`_MIRRORED`) 부서·코드·목표·마일스톤·헬스·주간 리포트는 건드리지
   않는다. 저것들은 Notion 에 아예 없으므로 덮어쓰면 되돌아오지 않는다.
2. **소프트 프룬이 필수다.** 프로젝트 행에 `project_members` / `project_milestones` /
   `project_health_snapshots` / `project_weekly_reports` 가 CASCADE 로 매달려 있고 **넷 다
   Notion 에 없다.** 한 회차 깜빡임으로 지우면 재동기화로 돌아오지 않는다.
   다만 표시된 프로젝트를 **목록에서 감추지는 않는다** - 감추면 Notion 이 깜빡인 순간 포털의
   마일스톤·주간 리포트가 화면에서 통째로 사라진다(티켓과 갈리는 지점, models.py 참조).
3. **`updated_at` 을 매 회차 건드리지 않는다.** 목록 정렬이 `updated_at` 이라 회차마다
   찍으면 아무것도 안 바뀐 날에도 순서가 뒤섞이고, "최근 갱신" 이 아무 뜻도 없게 된다.
   실제로 값이 달라진 회차에만 찍는다.

## 진행률은 두 값을 나란히 싣는다

Notion 의 `티켓 진행률`(rollup) / `프로젝트 진행률`(formula)은 **취소한 티켓을 완료로 세므로**
정본으로 쓰지 않는다(`app/projects/progress.py` 에 실측 근거 세 가지). 그렇다고 버리지도
않는다 - 두 화면에 다른 숫자가 뜨는 것은 정상 상태이고, 그때 한쪽만 보이면 사용자는 "포털이
틀렸다" 고 결론 내린다. `notion_progress_pct` 로 따로 담아 화면이 나란히 보여 준다.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.core.models_base import join_names, split_names
from app.core.sync_prune import PruneResult, prune_missing
from app.org.constants import DEFAULT_ORG_ID
from app.projects import notion_source, notion_write
from app.projects.models import (
    PROJECT_SYNC_STATE_ID,
    SYNC_ERROR,
    SYNC_OK,
    Project,
    ProjectSyncState,
)
from app.tickets import notion_write as tickets_notion_write

logger = logging.getLogger("app.projects.sync")

# 동기화가 덮어쓰는 컬럼. **여기 없는 것은 앱 정본이다** - 부서·코드·목표·진행률 계산값·
# 헬스·보관 시각은 Notion 에 대응이 없으므로 동기화가 손대면 되돌아오지 않는다.
_MIRRORED = (
    "name", "starts_on", "ends_on", "biz_type", "product",
    "notion_status", "notion_progress_pct", "notion_owner_ids", "notion_last_edited",
)

# 포털에서 고치면 Notion 으로 push 하는 필드(사용자 지시).
#
# 예전에는 낙관적 잠금의 지문도 이 목록에서 만들었다. S6 이 그 결합을 끊었다 —
# 여기 없는 필드(부서·목표·마일스톤)를 두 사람이 동시에 고치는 것도 충돌이고, 지문이
# 이 목록에 묶여 있으면 그 충돌이 안 잡혔다(`ensure_not_changed` 참조).
PUSHED_FIELDS: tuple[str, ...] = (
    "name", "notion_status", "starts_on", "ends_on", "owner_user_id",
)


def get_or_create_state(db: Session) -> ProjectSyncState:
    state = db.get(ProjectSyncState, PROJECT_SYNC_STATE_ID)
    if state is None:
        state = ProjectSyncState(id=PROJECT_SYNC_STATE_ID)
        db.add(state)
        db.flush()
    return state


# ── 낙관적 잠금 ────────────────────────────────────────────────────────────────


def ensure_not_changed(project: Project, base_version: int | None) -> None:
    """그 사이 누가 먼저 저장했으면 막는다. **정수 `version` 을 본다** (S6).

    **왜 필요한가**: 프로젝트는 여러 사람이 같은 화면을 연다. 두 사람이 동시에 기간을
    고치면 나중 사람이 앞사람 변경을 덮어쓰고 **양쪽 다 성공 화면을 본다.** 사람이 이미 한
    일을 조용히 파괴하는 부류라 어떤 성능 문제보다 아프다.

    ## 예전에는 `PUSHED_FIELDS` 의 해시였다 — 왜 물러났나

    그 지문은 **Notion 에 실려 나가는 필드 집합**으로 만들었다. 그래서 소스에 안 보내는
    값(부서·소유자 표시·목표)이 바뀐 것은 충돌로 안 잡혔고, 반대로 `PUSHED_FIELDS` 를
    한 줄 고치는 날 **모든 열린 폼의 지문이 한꺼번에 무효**가 됐다. 정수는 둘 다와
    무관하다 — 그 행이 저장될 때마다 1 씩 늘 뿐이다.

    동기화가 Notion 에서 새 값을 가져와도 `version` 이 는다(`_upsert` 참조). 그것도
    충돌이 맞다 — 내가 폼을 열어 둔 사이 저쪽에서 바뀐 값을 내 화면의 옛 값으로
    되돌려 보내면 안 된다.

    `base_version` 이 없으면(구버전 클라이언트·CLI) 예전대로 동작한다 - 새 계약을 강제해
    기존 경로를 깨뜨리지 않는다(티켓 본문 `_ensure_body_not_changed` 와 같은 규약).
    """
    if base_version is None:
        return
    if int(base_version) != int(project.version or 1):
        raise ConflictError(
            "다른 사람이 먼저 저장했습니다. 새로고침해 최신 내용을 확인한 뒤 다시 저장해 주세요."
        )


# ── 읽기 (Notion → 앱) ─────────────────────────────────────────────────────────


def _verified_notion_to_user(db: Session) -> dict[str, str]:
    """verified 이고 활성인 매핑 {Notion person id: 앱 user_id}. 회차당 한 번만 만든다.

    verified 만 보는 이유: 담당자 판정은 표시용이 아니라 권한·알림의 재료라, 미검증 매핑을
    쓰면 남의 이름으로 일이 배정된다(스펙 §12.3, 티켓 쪽과 같은 규칙).

    프로젝트마다 다시 질의하지 않는다 - 100개 프로젝트면 질의가 100번이 된다.
    """
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.users.models import User

    rows = db.execute(
        select(UserNotionMapping.notion_user_id, User.id)
        .join(User, User.id == UserNotionMapping.user_id)
        .where(
            UserNotionMapping.status == STATUS_VERIFIED,
            UserNotionMapping.notion_user_id.is_not(None),
            User.active.is_(True),
            User.archived_at.is_(None),
        )
    ).all()
    out: dict[str, str] = {}
    for nid, uid in rows:
        out.setdefault(nid, uid)
    return out


def _apply(row: Project, field: str, value) -> bool:
    """값이 실제로 달라질 때만 쓰고, 달라졌는지 알려 준다.

    무조건 대입해도 SQLAlchemy 가 같은 값이면 UPDATE 를 안 내지만, 우리가 알고 싶은 것은
    "이 회차에 무언가 바뀌었는가" 다 - 그 답으로 `updated_at` 을 찍을지 정한다(모듈 docstring).
    """
    if getattr(row, field) == value:
        return False
    setattr(row, field, value)
    return True


def _upsert(db: Session, p: dict, id_to_user: dict[str, str], now: datetime) -> "Project | None":
    """파싱된 Notion 프로젝트 한 건을 앱 표에 반영한다(있으면 갱신, 없으면 삽입).

    반환값은 호출측이 **진행률을 재계산**할 대상을 고르는 데 쓴다(아래 sync_projects).
    """
    page_id = p.get("id")
    if not page_id:
        return None
    row = db.execute(
        select(Project).where(Project.notion_page_id == page_id)
    ).scalar_one_or_none()
    created = row is None
    if created:
        # ⚠️ **부서가 비어 있다.** Notion 프로젝트 DB 에는 부서 속성이 없고(앱에만 둔다),
        # `dept_id IS NULL` 인 프로젝트는 부서 범위 사용자에게 **통째로 안 보인다**
        # (app/projects/repository.py 의 규칙 - 부서 관리자 화면이지 전사 화면이 아니다).
        # 즉 새로 들어온 프로젝트는 누군가 부서를 지정해 줄 때까지 전역 관리자만 본다.
        # 이것을 오류로 올리지는 않는다 - 정상 동작이고, 부서 지정은 사람의 판단이다.
        row = Project(
            notion_page_id=page_id,
            org_id=DEFAULT_ORG_ID,
            name="",
            created_at=now,
            updated_at=now,
        )
        db.add(row)

    owner_ids = [i for i in (p.get("owner_ids") or []) if i]
    changed = False
    # 이름이 빈 채로 온 페이지(제목 속성을 지웠거나 이름을 바꾼 경우)까지 그대로 받아 적으면
    # 목록에 이름 없는 줄이 생긴다. 그때는 page id 를 이름으로 세워 최소한 열 수 있게 한다.
    changed |= _apply(row, "name", (p.get("title") or "").strip() or f"(제목 없음) {page_id}")
    changed |= _apply(row, "starts_on", p.get("start"))
    changed |= _apply(row, "ends_on", p.get("end"))
    changed |= _apply(row, "biz_type", p.get("biz_type"))
    changed |= _apply(row, "product", p.get("product"))
    changed |= _apply(row, "notion_status", p.get("status"))
    changed |= _apply(row, "notion_progress_pct", p.get("notion_progress_pct"))
    changed |= _apply(row, "notion_owner_ids", join_names(owner_ids))
    changed |= _apply(row, "notion_last_edited", p.get("last_edited"))

    resolved = next((id_to_user[i] for i in owner_ids if i in id_to_user), None)
    if resolved is not None:
        changed |= _apply(row, "owner_user_id", resolved)
    # 해석이 안 되면 기존 소유자를 **지우지 않는다.** 담당자가 포털 미가입이거나 매핑이
    # 아직 검증 전인 것이지 "담당자가 없어졌다" 가 아니다. 원문은 notion_owner_ids 에 남는다.

    # 돌아왔다 - 지난 회차에 "안 보임" 으로 표시됐더라도 아무 일 없었던 것이 된다.
    changed |= _apply(row, "notion_missing_at", None)
    # push 실패 자국은 정상 회차에 지운다. Notion 이 지금 이 값을 돌려주고 있다는 것은
    # 어긋남이 해소됐다는 뜻이고, 남겨 두면 화면이 영원히 "반영 실패" 배너를 단다.
    changed |= _apply(row, "notion_sync_error", None)

    if not (changed or created):
        # **아무것도 안 바뀌었으면 행을 한 글자도 건드리지 않는다.**
        #
        # 여기서 `notion_synced_at = now` 한 줄만 써도 행이 dirty 가 되고, 그 UPDATE 에
        # `TimestampMixin.updated_at` 의 `onupdate=utcnow` 가 딸려 붙는다(명시적으로 대입한
        # 컬럼만 onupdate 를 비껴간다). 즉 **회차마다 전 프로젝트의 `updated_at` 이 같은
        # 시각으로 덮인다.** 목록 정렬이 `updated_at DESC` 라(repository.list_in_scope)
        # 그러면 정렬이 사실상 id 순으로 무너지고, 사용자가 방금 고친 프로젝트가 맨 위에
        # 오지 않는다. 원인이 정렬 코드에 없어서 아무도 못 찾는다.
        #
        # 같은 값을 다시 대입해도 소용없다 - SQLAlchemy 는 값이 같으면 변경으로 세지 않아
        # 그 컬럼이 UPDATE 에서 빠지고, 결국 onupdate 가 이긴다. 안 건드리는 것이 답이다.
        #
        # ⚠️ 그래도 **row 는 돌려준다.** 프로젝트 자신은 안 바뀌었어도 그 프로젝트에 달린
        # 티켓은 이번 회차에 바뀌었을 수 있다 - 진행률은 티켓을 세므로 재계산이 필요하다.
        # 호출측이 진행률 재계산 대상을 이 반환값으로 고르기 때문에, 여기서 None 을 주면
        # "프로젝트 필드는 그대로인데 티켓만 바뀐" 흔한 경우에 진행률이 영원히 안 바뀐다.
        return row

    # "노션 값을 이 행에 반영한 시각" 이다. "언제 확인했나" 가 아니다 - 확인만 하고 같았던
    # 회차는 위에서 그냥 돌아간다. 미러 전체의 신선도는 `ProjectSyncState.last_success_at`
    # 이 답한다(그쪽은 회차마다 갱신된다).
    row.notion_synced_at = now
    row.updated_at = now
    # 낙관적 잠금도 함께 는다 (S6). 예전 지문(`PUSHED_FIELDS` 해시)은 저쪽 값이 바뀌면
    # 자동으로 달라졌지만 정수는 누가 올려 주지 않으면 안 는다 — 안 올리면 내가 폼을
    # 열어 둔 사이 동기화가 가져온 값을 내 화면의 옛 값으로 조용히 되돌려 보낸다.
    #
    # **값이 실제로 바뀐 회차에만** 는다. 위 `if not (changed or created)` 를 지난
    # 자리라 그것이 보장된다.
    row.version = int(row.version or 1) + 1
    return row



def _prune(db: Session, keep: set[str], now: datetime) -> PruneResult:
    """Notion 에서 사라진 프로젝트를 **표시**한다 - 지우지 않는다.

    포털 전용 프로젝트(`notion_page_id IS NULL`)는 후보가 아니다. Notion 조회 결과에 없는
    것이 당연하기 때문이다(티켓의 native 행과 같은 이유).

    삭제 판단은 `core/sync_prune` 의 바닥을 거친다 - Notion 이 빈 결과를 200 으로 돌려주면
    여기서 전 프로젝트가 한 번에 표시된다(거기 주석 참조).

    **왜 지우지 않는가**: 그 바닥은 대량 손실을 막지만, 프로젝트 **한 건**이 응답에서
    깜빡이는 것은 정상 삭제로 보여 그대로 지운다. 그러면 CASCADE 가 참여자·마일스톤·헬스
    이력·주간 리포트를 함께 지우는데, **넷 다 Notion 에 없으므로 재동기화로 돌아오지 않는다.**
    게다가 프로젝트 행 자체가 앱 정본이라(0044) 부서·코드·목표까지 함께 사라진다.
    """
    rows = db.execute(
        select(Project).where(
            Project.notion_page_id.is_not(None),
            # 이미 표시된 행은 다시 후보로 세지 않는다 - 세면 낙폭 비율이 회차마다 부풀어
            # 바닥이 엉뚱하게 발동하고, 표시 시각이 계속 갱신된다(티켓 쪽과 같은 함정).
            Project.notion_missing_at.is_(None),
        )
    ).scalars().all()

    def _mark(row: Project) -> None:
        row.notion_missing_at = now

    return prune_missing(
        db, rows, keep, key=lambda r: r.notion_page_id, label="프로젝트", mark=_mark
    )


def sync_projects(db: Session, *, outbound, settings, now: datetime) -> ProjectSyncState:
    """전체 동기화. 어떤 단계에서 실패해도 **예외를 밖으로 던지지 않는다**.

    호출측(워커 tick)은 절대 크래시하지 않고, 실패하면 마지막 정상 데이터가 그대로 남는다.
    """
    state = get_or_create_state(db)
    state.last_run_at = now
    try:
        # 작업 DB 스키마를 먼저 읽어 `프로젝트` relation 이 가리키는 DB 를 찾는다.
        tasks_schema = tickets_notion_write.fetch_schema(outbound, settings)
        database_id = notion_source.discover_database_id(tasks_schema)
        if not database_id:
            # relation 조회 실패는 **승격한다**(티켓 C4 와 같은 이유). 여기서 조용히 0건으로
            # 끝내면 화면은 '정상 동기화' 라고 말하는데 프로젝트가 하나도 안 뜬다. 사용자는
            # "프로젝트 화면이 비었다" 고 신고하고 관리자는 프로젝트 코드를 판다 - 원인은
            # 동기화이고 그 화면은 정상이라고 말하고 있다.
            #
            # 그리고 **prune 을 절대 안 돈다**: 못 읽은 것을 '삭제됨' 으로 표시하면 전 프로젝트에
            # "Notion 짝 없음" 배지가 붙는다.
            state.status = SYNC_ERROR
            state.error = (
                "작업 데이터베이스에서 프로젝트 연결 속성을 찾지 못해 프로젝트를 "
                "하나도 가져오지 못했습니다. 노션에서 속성 이름이 바뀌었는지 확인해 주세요."
            )
            state.updated_at = now
            db.flush()
            return state

        rows, truncated = notion_source.query_all_projects_paged(
            outbound, settings, database_id
        )
        id_to_user = _verified_notion_to_user(db)

        keep: set[str] = set()
        touched: list[Project] = []
        for p in rows:
            row = _upsert(db, p, id_to_user, now)
            if row is not None:
                touched.append(row)
            if p.get("id"):
                keep.add(p["id"])

        # 🔴 진행률을 재계산한다. `_upsert` 는 프로젝트 자신의 필드만 채운다 - 진행률은
        # `ticket_cache` 를 세므로 이 자리가 아니면 아무도 안 부른다. 실제로 안 부르고
        # 있었고, 운영 프로젝트 22건이 전부 "아직 계산하지 않았습니다" 로 떴다.
        #
        # 함수 안에서 import 하는 이유: `service.py` 가 이 모듈을 import 하므로 파일 위에서
        # 임포트하면 순환 임포트가 된다.
        #
        # 한 프로젝트가 터져도 나머지는 계속 돈다(휴지통 정리와 같은 원칙) - 계산 하나가
        # 이상한 데이터로 죽는다고 이번 동기화 전체를 SYNC_ERROR 로 만들 이유는 없다.
        from app.projects.service import recompute_progress

        for row in touched:
            try:
                recompute_progress(db, row, now=now)
            except Exception:
                logger.exception("프로젝트 진행률 재계산 실패: %s", row.notion_page_id)

        # 티켓의 **소속을 다시 해석한다** (0060). 티켓 동기화가 먼저 돌면 그 시점에 없던
        # 프로젝트를 가리키는 티켓은 `unresolved`(= 아무에게도 안 보임)로 남는다. 프로젝트가
        # 방금 들어왔으니 여기서 풀어 주지 않으면 그 티켓들은 영영 닫힌 채다 — 증상이
        # "권한 오류" 가 아니라 "목록이 비어 있음" 이라 원인을 찾기 어렵다.
        #
        # 실패해도 이번 프로젝트 동기화를 실패로 만들지 않는다(위 진행률 재계산과 같은 원칙) —
        # 다음 회차가 다시 해석하고, 그 사이는 닫혀 있는 쪽(안전한 쪽)이다.
        from app.tickets import project_link as ticket_project_link

        try:
            link_counts = ticket_project_link.reresolve_all(db)
            logger.info("티켓 소속 재해석: %s", link_counts)
        except Exception:
            logger.exception("티켓 소속 재해석 실패")

        # 문서도 같은 이유로 다시 해석한다 — 프로젝트가 방금 들어왔으니 그때까지 미지정
        # (= 아무에게도 안 보임) 이던 문서가 여기서 풀린다.
        from app.team_docs import sync as doc_sync

        try:
            doc_counts = doc_sync.resolve_project_ownership(db)
            if doc_counts["promoted"]:
                logger.info("문서 Ownership 재해석: %s", doc_counts)
        except Exception:
            logger.exception("문서 Ownership 재해석 실패")

        # 상한에 걸려 일부만 받아왔다면 prune 하지 않는다 - 안 받아온 프로젝트를 'Notion 에서
        # 삭제됨' 으로 오인해 표시하면 멀쩡한 프로젝트에 배지가 붙는다.
        pruned = _prune(db, keep, now) if not truncated else PruneResult()

        notes = []
        if truncated:
            notes.append(f"프로젝트가 상한({len(keep)}건)을 초과해 일부만 동기화했습니다.")
        if pruned.refused:
            notes.append(pruned.refused)

        # prune 을 거부했다는 것은 소스를 믿을 수 없다는 뜻이다. 그걸 ok 로 적으면 화면이
        # '정상' 이라 말하는 동안 미러가 조용히 낡아 간다.
        bad = bool(pruned.refused)
        state.status = SYNC_ERROR if bad else SYNC_OK
        if not bad:
            state.last_success_at = now
        state.project_count = len(keep)
        state.truncated = truncated
        state.pruned_count = pruned.deleted
        state.error = " / ".join(notes) or None
        state.updated_at = now
        db.flush()
    except Exception as exc:  # AppError(Notion 오류)·DB 충돌 등 무엇이든 여기서 가둔다
        db.rollback()
        # 롤백으로 state 가 detach 될 수 있으니 다시 읽어 error 를 남긴다.
        # last_success_at 은 손대지 않는다 - 미러가 '언제까지 정상이었는지' 가 신선도 표시의
        # 근거이고, 실패했다고 그 사실이 사라지면 화면이 신선도를 거짓말한다.
        fresh = get_or_create_state(db)
        fresh.last_run_at = now
        fresh.status = SYNC_ERROR
        fresh.error = getattr(exc, "message", None) or type(exc).__name__
        fresh.updated_at = now
        db.flush()
        return fresh
    return state


# ── 쓰기 (앱 → Notion) ─────────────────────────────────────────────────────────


def _push_owner_ids(db: Session, project: Project) -> list[str]:
    """소유자를 Notion person id 목록으로. 해석 안 되면 **원래 값을 그대로 되돌려 보낸다.**

    빈 목록을 보내면 Notion 의 담당자가 지워진다. 포털에 매핑이 없는 사람이 담당자인
    프로젝트를 포털에서 한 번 저장했다고 저쪽 담당자가 사라지면, 그건 우리가 모르는 값을
    우리가 모른다는 이유로 지운 것이다.
    """
    if not project.owner_user_id:
        return split_names(project.notion_owner_ids)
    for nid, uid in _verified_notion_to_user(db).items():
        if uid == project.owner_user_id:
            return [nid]
    return split_names(project.notion_owner_ids)


def push_project(db: Session, project: Project, *, outbound, settings, now: datetime) -> bool:
    """앱의 현재 값을 Notion 페이지에 밀어 넣는다. 성공하면 True.

    **실패해도 예외를 던지지 않는다.** 던지면 요청 트랜잭션이 롤백되어 방금 사용자가 고친
    이름·기간까지 사라진다 - Notion 장애의 대가를 사용자 입력으로 치르게 하는 것이다
    (티켓 본문 push 가 같은 판단을 기록한다). 대신 어긋난 상태를 `notion_sync_error` 에
    남기고 화면이 "저장됨, Notion 반영 실패" 를 말하게 한다.

    Notion 짝이 없는 포털 전용 프로젝트는 할 일이 없으므로 True 다 - 실패가 아니다.
    """
    if not project.notion_page_id:
        return True
    try:
        tasks_schema = tickets_notion_write.fetch_schema(outbound, settings)
        database_id = notion_source.discover_database_id(tasks_schema)
        if not database_id:
            raise ValueError("프로젝트 데이터베이스를 찾지 못했습니다.")
        schema = notion_write.fetch_schema(outbound, settings, database_id)
        properties = notion_write.build_properties(
            schema,
            title=project.name,
            status=project.notion_status,
            # 시작이 비어 있어도 `""` 로 넘겨 '지움' 이 되게 한다. None 을 넘기면 '안 건드림'
            # 이라 포털에서 기간을 지운 것이 저쪽에 반영되지 않는다.
            start=project.starts_on or "",
            end=project.ends_on or "",
            owner_notion_ids=_push_owner_ids(db, project),
        )
        if not properties:
            raise ValueError("노션 스키마에서 고칠 수 있는 속성을 찾지 못했습니다.")
        notion_write.update_project_properties(
            outbound, settings, page_id=project.notion_page_id, properties=properties
        )
    except Exception as exc:  # noqa: BLE001 - 위 docstring: 롤백하면 사용자 입력이 사라진다
        project.notion_sync_error = (
            getattr(exc, "message", None) or str(exc) or type(exc).__name__
        )
        project.updated_at = now
        db.flush()
        return False

    project.notion_sync_error = None
    project.notion_synced_at = now
    project.updated_at = now
    db.flush()
    return True
