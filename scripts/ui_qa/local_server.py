"""캡처 하네스가 붙을 **로컬 서버**를 띄운다 (S15).

## 왜 필요한가

`scripts/ui_qa/run.py` 는 실제로 도는 서버가 있어야 한다. 지금까지 그 서버는 언제나
설치처(랩 서버)였다. 그런데 그 서버는 **사람들이 쓰는 설치**라, 「이번 회차가 고친 화면을
찍으려고」 배포하는 것은 그 자체로 바깥을 향한 변경이다.

Session 이 자기가 바꾼 화면만 다시 찍는 규칙(E5)을 지키려면, 찍을 대상이 **이 회차의
빌드**이기만 하면 된다 — 그것이 어느 호스트에 있는지는 캡처의 본질이 아니다. 그래서
여기서 임시 데이터베이스와 임시 설정으로 앱을 하나 띄운다.

## 무엇을 만드는가

  * 임시 PostgreSQL 데이터베이스(`clovir_uiqa_<pid>`) — alembic 을 head 까지 돌린다.
  * 임시 설정 디렉터리(비밀·업로드) — 설치처의 것을 건드리지 않는다.
  * 그 위에서 도는 앱 하나 (127.0.0.1 의 빈 포트).

**끝나면 데이터베이스를 지운다.** 안 지우면 개발 머신에 `clovir_uiqa_*` 가 쌓인다.

## 쓰는 법

    python -m scripts.ui_qa.local_server --seed        # 띄우고 계정·데이터를 심는다
    python -m scripts.ui_qa.local_server --print-url   # 주소만 인쇄하고 붙잡고 있는다

인자 없이 부르면 서버를 띄우고 `Ctrl+C` 까지 붙잡는다. 주소는 stdout 첫 줄에 나온다 —
다른 스크립트가 그것을 읽어 `--base-url` 로 넘기면 된다.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
from contextlib import closing
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_PG = os.environ.get(
    "CLOVIR_TEST_PG_URL", "postgresql://cloviradmin:s2devpw@127.0.0.1:55433/postgres"
)
DB_NAME = "clovir_uiqa_%d" % os.getpid()


def _url_for(name: str) -> str:
    head, _, _ = DEFAULT_PG.rpartition("/")
    return f"{head}/{name}"


def _admin_engine():
    from sqlalchemy import create_engine

    from app.core.db import normalize_database_url

    return create_engine(
        normalize_database_url(DEFAULT_PG), isolation_level="AUTOCOMMIT", future=True
    )


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def create_database() -> str:
    from sqlalchemy import text

    with _admin_engine().connect() as conn:
        conn.execute(text(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = :d AND pid <> pg_backend_pid()"), {"d": DB_NAME})
        conn.execute(text(f'DROP DATABASE IF EXISTS "{DB_NAME}"'))
        conn.execute(text(f'CREATE DATABASE "{DB_NAME}"'))
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    prior = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _url_for(DB_NAME)
    try:
        command.upgrade(cfg, "head")
    finally:
        if prior is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prior
    return _url_for(DB_NAME)


def drop_database() -> None:
    from sqlalchemy import text

    try:
        with _admin_engine().connect() as conn:
            conn.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :d AND pid <> pg_backend_pid()"), {"d": DB_NAME})
            conn.execute(text(f'DROP DATABASE IF EXISTS "{DB_NAME}"'))
    except Exception:  # noqa: BLE001 - 정리 실패가 결과를 바꾸지는 않는다
        pass


def build_settings(database_url: str, workdir: Path):
    from app.core.config import Settings

    secrets_dir = workdir / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        session_secret="ui-qa-local-session-secret",
        cookie_secure=False,          # http 로 띄우므로 Secure 쿠키는 안 붙는다
        config_dir=REPO_ROOT / "config",
        secrets_dir=secrets_dir,
        data_dir=workdir,
    )


def seed(database_url: str, email: str, password: str, settings) -> None:
    """캡처가 볼 수 있을 만큼의 데이터. **빈 화면만 찍으면 아무것도 못 본다.**"""
    from datetime import date, datetime, timedelta

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.db import normalize_database_url

    engine = create_engine(normalize_database_url(database_url), future=True)
    with Session(engine) as db:
        from app.board.models import Post
        from app.knowledge.models import Document, DocumentTag, KnowledgeSpace, Tag
        from app.notifications.models import Notification
        from app.org.constants import DEFAULT_ORG_ID
        from app.projects.models import Project
        from app.tickets.models import PROJECT_LINK_OK, SOURCE_NATIVE, TicketCache
        from app.users.service import create_user
        from app.work import codes as work_codes

        me = create_user(db, email=email, password=password, display_name="UI QA",
                         role="system_admin", settings=settings, actor_role="system_admin",
                         must_change_password=False, membership_kind="organization")
        db.flush()

        projects = []
        # 셋째 이름이 길다. **의도한 것이다** — R-90 은 상세 상단 속성을 «긴 프로젝트명 실데이터»
        # 로 FHD/QHD/4K 와 Zoom 에서 검증하라고 요구하는데, 씨앗이 전부 네 글자면 그 축은
        # 아무리 찍어도 안 드러난다. 길이는 실제 운영 프로젝트 이름의 최댓값 언저리다.
        for name in ("포털 개편", "인프라 정비", "ClovirAssist 플랫폼 전환 및 자체 데이터 이관"):
            p = Project(name=name, org_id=DEFAULT_ORG_ID)
            work_codes.insert_with_code(db, p)
            db.flush()
            projects.append(p)

        now = datetime(2026, 8, 24, 3, 0, 0)
        statuses = ["진행", "계획", "검증", "완료"]
        prios = ["High", "Normal", "Low"]
        diffs = ["상", "중", "하"]
        from app.work import numbering  # noqa: PLC0415

        for i in range(24):
            # 회전을 1 만큼 밀어 **상세 캡처가 여는 티켓(업무 08)이 긴 이름 프로젝트**를
            # 갖게 한다. 짧은 이름이 걸리면 R-90 이 요구한 축(긴 프로젝트명이 좁은 칸에서
            # 깨지는가)이 그 화면에 아예 나타나지 않는다 — 나머지 티켓은 세 프로젝트에
            # 그대로 고루 퍼진다.
            project = projects[(i + 1) % len(projects)]
            db.add(TicketCache(
                title=f"업무 {i + 1:02d} — 화면에서 읽히는 제목",
                status=statuses[i % 4], priority=prios[i % 3], difficulty=diffs[i % 3],
                category=("인프라" if i % 2 else "포털"),
                due_date=date(2026, 8, 20) + timedelta(days=i % 7),
                est_wd=1.5, act_wd=1.0,
                project_uid=project.id, project_link=PROJECT_LINK_OK,
                project_names=project.name,
                # 번호를 실제 채번기로 받는다. 예전에는 `seq` 를 비워 둬서 트리거가
                # `canonical_key` 를 안 만들었고, 캡처의 티켓에는 **번호가 없었다** —
                # 운영 티켓은 전부 번호가 있으므로 그 화면은 제품과 다른 것을 보여 준다.
                seq=numbering.allocate(db, project.id),
                assignee_notion_ids="" if i % 5 == 0 else f"\x1f{me.id}\x1f",
                source=SOURCE_NATIVE, synced_at=now, notion_ticket_number=i + 1,
                org_id=DEFAULT_ORG_ID,
            ))

        space = KnowledgeSpace(name="팀 문서", slug="team", owner_kind="organization",
                               org_id=DEFAULT_ORG_ID)
        db.add(space)
        db.flush()
        tag = Tag(name="회의록", slug="meeting")
        db.add(tag)
        db.flush()
        for i in range(12):
            doc = Document(space_id=space.id, title=f"문서 {i + 1:02d} — 회의록",
                           created_at=now - timedelta(days=i), updated_at=now - timedelta(days=i))
            db.add(doc)
            db.flush()
            if i % 2 == 0:
                db.add(DocumentTag(document_id=doc.id, tag_id=tag.id))

        # 본문이 «본문» 두 글자면 읽기 화면을 **평가할 수 없다**. 판 하나가 잉크 19% 로
        # 남는 것이 화면 탓인지 씨앗 탓인지 구별이 안 되고, 실제로 S18 이 그 자리에서
        # 한 번 헷갈렸다. 길이는 실제 게시글의 중간값 언저리로 둔다.
        body = (
            "이번 주 배포에서 바뀐 것을 정리합니다. 티켓 목록의 조건이 주소에 실려서 "
            "새로고침하거나 링크를 공유해도 같은 화면이 열립니다.\n\n"
            "확인이 필요한 것은 두 가지입니다. 첫째, 담당자 선택 목록에 새로 들어온 "
            "계정이 보이는지 확인해 주세요. 둘째, 지연된 티켓의 마감일을 다시 정해야 "
            "합니다. 질문은 이 글에 댓글로 남겨 주시면 답을 달겠습니다."
        )
        for i in range(26):
            db.add(Post(author_user_id=me.id, org_id=DEFAULT_ORG_ID, kind="free",
                        category=("공지" if i % 3 == 0 else "자유"),
                        title=f"게시글 {i + 1:02d} — 배포 뒤 확인할 것", body=body,
                        is_pinned=(i == 0), created_at=now - timedelta(hours=i)))
        for i in range(24):
            db.add(Notification(
                user_id=me.id, type="ticket_assigned",
                audience=("admin" if i % 2 else "user"),
                title=f"알림 {i + 1:02d}", body="본문",
                read_at=None if i < 12 else now, created_at=now - timedelta(minutes=i)))
        db.commit()
        _seed_pilot(db, settings, me, projects, now)
        db.commit()
    engine.dispose()


def _seed_pilot(db, settings, me, projects, now) -> None:
    """Pilot 8 Archetype 이 **비어 있지 않게** 한다 (S18).

    S15 의 씨앗은 목록·상세 화면을 위한 것이었다 — 티켓·문서·게시글·알림. 그 위에서
    W8 이 대표로 삼는 여덟 원형 중 **다섯이 빈 화면**이었다: 조직(B11)에 마디가 없고,
    사용자 목록(B2)에 사람이 하나뿐이고, 채팅(B9)에 방이 없고, 작업 이력(B8)에 줄이
    없고, 읽기 화면(B3)에 댓글이 없었다.

    빈 화면을 찍어 놓고 「원형을 검증했다」고 적으면 그 회차는 아무것도 본 것이 없다 —
    검사는 전부 통과하는데(볼 것이 없으니) 그 통과가 아무 뜻이 없는 상태다. 그래서
    여기서 각 원형이 자기 구조를 실제로 보여 줄 만큼만 심는다.

    **적게 심는 데에도 이유가 있다.** 20건 안팎을 쓰는 이유는 쪽 넘김(pagination)이
    실제로 일어나는 최소 규모이기 때문이고, 사람을 여섯 심는 이유는 부서 둘로 갈렸을 때
    한쪽이 비지 않게 하려는 것이다.
    """
    from datetime import date, timedelta

    from app.board.models import Comment as BoardComment
    from app.board.models import Post, Reaction
    from app.jobs.models import Job
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import JobTitle, OrgUnit
    from app.projects.models import (
        Project, ProjectHealthSnapshot, ProjectMember, ProjectMilestone,
    )
    from app.tickets.models import TicketCache, TicketComment
    from app.team_chat.models import ChatMessage, ChatRoom, ChatRoomMember
    from app.users.service import create_user

    # ── 조직 트리 (B11 Split view) ────────────────────────────────────────────
    # 본부 하나 아래 팀 둘. 트리의 «접힘/펼침» 과 «선택하면 오른쪽 판이 바뀐다» 는
    # 마디가 최소 두 층은 있어야 보인다.
    hq = OrgUnit(name="플랫폼본부", kind="department", org_id=DEFAULT_ORG_ID)
    db.add(hq)
    db.flush()
    teams = []
    for name in ("플랫폼개발팀", "서비스운영팀"):
        unit = OrgUnit(name=name, kind="department", parent_id=hq.id, org_id=DEFAULT_ORG_ID)
        db.add(unit)
        teams.append(unit)
    db.flush()
    titles = []
    for name in ("팀장", "선임", "주임"):
        title = JobTitle(name=name, org_id=DEFAULT_ORG_ID)
        db.add(title)
        titles.append(title)
    db.flush()

    me.department_id = teams[0].id
    me.title_id = titles[0].id

    # ── 사람 (B2 · B11) ──────────────────────────────────────────────────────
    # 역할을 섞는다 — 역할 열이 한 값뿐이면 그 열은 아무것도 구별하지 않는다.
    people = [me]
    plan = (
        ("kim.jihoon", "김지훈", "operator", 0, 1, True),
        ("lee.seoyeon", "이서연", "user", 0, 2, True),
        ("park.minjun", "박민준", "admin", 1, 1, True),
        ("choi.yuna", "최유나", "user", 1, 2, True),
        # 비활성 계정 하나 — 「활성/비활성」 필터가 실제로 무엇을 거르는지 보이게.
        ("jung.dohyun", "정도현", "user", 1, 2, False),
    )
    for local, name, role, team_idx, title_idx, active in plan:
        person = create_user(
            db, email=f"{local}@goodmit.co.kr", password="Ui-Qa-Local-1!",
            display_name=name, role=role, settings=settings, actor_role="system_admin",
            must_change_password=False, membership_kind="organization",
            department_id=teams[team_idx].id, title_id=titles[title_idx].id,
        )
        person.active = active
        people.append(person)
    db.flush()

    # ── 프로젝트의 «왜» (B1 · B2) ────────────────────────────────────────────
    # 목록이 Health 점수만 보여 주고 무엇이 그것을 떨어뜨렸는지는 안 보여 준다는 것이
    # 계획서가 이 화면에 적은 가장 큰 공백이다. 그 «왜» 를 화면에서 확인하려면 점수와
    # 근거가 실제로 있어야 한다.
    monday = date(2026, 8, 24) - timedelta(days=date(2026, 8, 24).weekday())
    scores = (47, 72, 91)
    reason_sets = (
        '["지연된 마일스톤이 2건 있습니다.", "이번 주 진행률이 지난주와 같습니다."]',
        '["담당자가 없는 티켓이 3건 있습니다."]',
        "[]",
    )
    for idx, project in enumerate(projects):
        project.dept_id = teams[idx % len(teams)].id
        project.owner_user_id = people[(idx + 1) % len(people)].id
        project.health_score = scores[idx]
        project.progress_pct = (18.0, 55.0, 92.0)[idx]
        project.starts_on = date(2026, 6, 1)
        project.ends_on = date(2026, 12, 31)
        db.add(ProjectMember(project_id=project.id, user_id=people[(idx + 1) % len(people)].id,
                             role="owner"))
        db.add(ProjectHealthSnapshot(project_id=project.id, week_of=monday,
                                     score=scores[idx], reasons_json=reason_sets[idx],
                                     created_at=now))
        for m, (mname, days, status) in enumerate((
            ("요구사항 확정", -20, "done"),
            ("1차 오픈", -3, "planned"),      # 지난 날짜인데 계획 상태 = 지연
            ("안정화", 21, "planned"),
        )):
            db.add(ProjectMilestone(project_id=project.id, name=f"{mname}",
                                    due_on=date(2026, 8, 24) + timedelta(days=days),
                                    status=status, sort_order=m))
    # 보관한 프로젝트 하나 — 「보관 포함」 스위치가 실제로 무엇을 더 보여 주는지 보이게.
    from app.work import codes as work_codes

    archived = Project(name="사내 위키 이관(보관)", org_id=DEFAULT_ORG_ID,
                       dept_id=teams[0].id, archived_at=now - timedelta(days=30),
                       status="완료", health_score=88, progress_pct=100.0)
    work_codes.insert_with_code(db, archived)
    db.flush()

    # ── 읽기 화면의 댓글 (B3) · 상세의 논의 (B4) ─────────────────────────────
    first_post = db.query(Post).order_by(Post.created_at.desc()).first()
    if first_post is not None:
        for i, person in enumerate(people[:4]):
            db.add(BoardComment(post_id=first_post.id, author_user_id=person.id,
                                body=f"댓글 {i + 1} — 이 글에 대한 의견입니다.",
                                created_at=now - timedelta(minutes=30 - i)))
        db.add(Reaction(target_type="post", target_id=first_post.id,
                        user_id=me.id, emoji="👍", created_at=now))
    tickets = db.query(TicketCache).order_by(TicketCache.notion_ticket_number).all()
    if tickets:
        for i, person in enumerate(people[:3]):
            db.add(TicketComment(ticket_uid=tickets[0].id, author_user_id=person.id,
                                 body=f"확인했습니다 ({i + 1}). 다음 단계는 검증입니다.",
                                 created_at=now - timedelta(minutes=20 - i)))

    # ── 채팅 (B9) ────────────────────────────────────────────────────────────
    # 방 셋: 팀 방(부서에 묶인 것) · 일반 그룹 방 · 안 읽은 것이 남은 방.
    rooms = (
        ("플랫폼개발팀", teams[0].id, 6),
        ("배포 준비", None, 3),
        ("장애 대응", None, 12),
    )
    for r, (title, dept_id, message_count) in enumerate(rooms):
        room = ChatRoom(kind="group", title=title, created_by_user_id=me.id,
                        department_id=dept_id, org_id=DEFAULT_ORG_ID,
                        event_seq=message_count)
        db.add(room)
        db.flush()
        members = people[: 3 + r]
        for person in members:
            db.add(ChatRoomMember(
                room_id=room.id, user_id=person.id,
                role="owner" if person.id == me.id else "member",
                # 마지막 방만 안 읽은 것이 남는다 — 안읽음 배지가 «있다/없다» 둘 다 보이게.
                last_read_seq=0 if r == 2 else message_count,
                joined_at=now - timedelta(days=3), last_seen=now - timedelta(minutes=5)))
        for s in range(1, message_count + 1):
            db.add(ChatMessage(
                room_id=room.id, seq=s, sender_user_id=members[s % len(members)].id,
                kind="text", body=f"{title} 메시지 {s:02d}",
                created_at=now - timedelta(minutes=message_count - s)))

    # ── 작업 이력 (B8 Operations console) ────────────────────────────────────
    # 실패가 섞여 있어야 「지금 확인할 것」이 무엇인지 화면이 말할 수 있다. 실패 사유를
    # 두 종류로 나눈다 — 원인별 묶기가 실제로 묶을 것이 있어야 보인다.
    for i in range(22):
        failed = i % 7 == 3
        # 상태 낱말도 **제품이 쓰는 것**이어야 한다(`app/jobs/models.py::ALL_STATUSES`).
        # `done` 은 이 제품에 없는 값이라, 그것을 심으면 화면의 «완료»(succeeded) 조건이
        # 언제나 0건을 돌려주고 그 0건이 화면 결함처럼 보인다 — 바로 위 유형 주석과 같은 실수다.
        status = "failed" if failed else ("succeeded" if i % 3 else "queued")
        # 유형은 제품이 실제로 쓰는 것만이다(`app/jobs/models.py`·`registry/shared.js`
        # 의 `JOB_TYPE`). 없는 유형을 심으면 운영 콘솔의 «유형» 조건이 그 값을 모르는
        # 채로 그리고, 화면이 실제로 무엇을 거르는지 확인할 수 없다.
        db.add(Job(
            job_type=("chat_message" if i % 3 == 0 else
                      "schedule_run" if i % 3 == 1 else "mail_send"),
            user_id=me.id, payload_json="{}", status=status,
            attempt_count=3 if failed else 1, max_attempts=3,
            available_at=now - timedelta(minutes=i * 5),
            started_at=None if status == "queued" else now - timedelta(minutes=i * 5 - 1),
            finished_at=None if status == "queued" else now - timedelta(minutes=i * 5 - 2),
            last_error=("연결 시간이 초과됐습니다 (timeout)" if i % 14 == 3
                        else "저장소에 쓸 수 없습니다 (permission denied)") if failed else None,
            created_at=now - timedelta(minutes=i * 5),
        ))


def serve(settings, port: int):
    import uvicorn

    from app.main import create_app

    app = create_app(settings)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            return server, thread
        time.sleep(0.1)
    raise RuntimeError("로컬 서버가 안 떴다")


def main() -> int:
    ap = argparse.ArgumentParser(description="캡처용 로컬 서버 (S15)")
    ap.add_argument("--email", default="ui-qa@goodmit.co.kr")
    ap.add_argument("--password", default="Ui-Qa-Local-1!")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--hold", action="store_true", help="Ctrl+C 까지 붙잡는다")
    args = ap.parse_args()

    import tempfile

    workdir = Path(tempfile.mkdtemp(prefix="clovir-uiqa-"))
    url = create_database()
    try:
        settings = build_settings(url, workdir)
        seed(url, args.email, args.password, settings)
        port = args.port or _free_port()
        server, _ = serve(settings, port)
        print("http://127.0.0.1:%d" % port, flush=True)
        if args.hold:
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        server.should_exit = True
        time.sleep(0.5)
    finally:
        drop_database()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
