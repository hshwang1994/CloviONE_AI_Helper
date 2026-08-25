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


def set_db_name(name: str) -> None:
    """이 프로세스가 쓸 데이터베이스 이름을 고정한다 (S21).

    기본값은 pid 를 붙여 매번 다르다 — 한 번 띄우고 한 번 찍는 회차에는 그것이 맞다.
    그런데 Acceptance 는 **같은 서버에 여러 묶음을 나눠 붙인다**(§7 의 bounded batch).
    묶음마다 새 데이터베이스를 만들면 alembic 을 열두 번 더 돌리고, 더 나쁘게는 묶음마다
    씨앗의 id 가 달라져 앞 묶음이 찾은 주소가 다음 묶음에서 죽는다.
    """
    global DB_NAME
    DB_NAME = name


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
    # 🔴 설정 디렉터리를 **베껴서** 쓴다 (S21). 예전에는 저장소의 `config/` 를 그대로
    # 가리켰는데, 기능 플래그 쓰기(`PUT /api/admin/feature-flags/{key}`)의 정본이 그 안의
    # 파일이라 **QA 실행이 저장소의 tracked 파일을 고쳤다.** 값은 같았지만 파일이 다시
    # 쓰이며 키 순서가 바뀌었고, 그 diff 는 이번 작업과 아무 상관이 없다.
    config_dir = workdir / "config"
    if not config_dir.exists():
        import shutil

        shutil.copytree(REPO_ROOT / "config", config_dir)
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        session_secret="ui-qa-local-session-secret",
        cookie_secure=False,          # http 로 띄우므로 Secure 쿠키는 안 붙는다
        config_dir=config_dir,
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
        db.flush()
        _seed_w10(db, me, now)
        db.flush()
        _seed_s21(db, me, now)
        db.commit()
        _seed_search_index(db, settings, now)
        db.commit()
    engine.dispose()


def _seed_search_index(db, settings, now) -> None:
    """검색 색인을 한 번 세운다 (S21).

    검색은 표를 직접 훑지 않는다 — `search_documents` 색인을 읽고, 그 색인은 정기 워커 틱
    (`search_index_interval_seconds`)이나 `POST /api/search/reindex` 가 세운다. 이 서버에는
    워커가 없으니 심은 티켓·문서·게시글·사용자가 **하나도 검색되지 않았다**. 그것은 검색이
    고장 난 것이 아니라 **아직 색인한 적이 없는 것**이라, 여기서 제품이 쓰는 그 함수를
    그대로 한 번 부른다.
    """
    from app.core.allowlist import AllowlistRegistry
    from app.core.http_client import OutboundClient
    from app.core.secret_refs import FileSecretReferenceProvider
    from app.core.source_registry import build_repositories
    from app.search.indexer import reindex_all

    outbound = OutboundClient(
        AllowlistRegistry(settings.config_dir),
        FileSecretReferenceProvider(settings.secrets_dir),
    )
    result = reindex_all(db, tickets=build_repositories(settings, outbound).tickets, now=now)
    print("SEARCH_INDEX=%s items=%s" % (result.status, result.item_count), flush=True)


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


def _seed_s21(db, me, now) -> None:
    """관리자 영역이 **빈 화면이 아니게** 한다 (S21 · W14).

    S15·S18 의 씨앗은 사용자 화면을 위한 것이었다. 그 위에서 S21 이 감사해야 하는 관리자
    화면 열둘이 **0행**이었다: 프롬프트 · 정책 · 공지 · AI 상한 · 외부 연동 · 실행 일정 ·
    승인 위임 · 백업 · 복구 리허설 · 놀이방 · 사용 통계 둘.

    빈 목록 위에서 「행을 골라 고친다」를 돌리면 Flow 는 「누를 것이 없다」로 죽고, 그
    죽음이 **제품 결함처럼 보인다**. 반대로 그 Flow 를 지우면 원장에는 「감사했다」가
    남는데 실제로 본 것은 빈 화면뿐이다 — 두 쪽 다 거짓이다.

    **UI 로 만들 수 있는 것도 여기서 심는다.** 만드는 Flow 는 만드는 Flow 대로 돌지만,
    그 Flow 하나가 실패하면 뒤따르는 열 몇 개가 연쇄로 죽는다. Flow 는 서로 독립이어야
    한다(S18 이 같은 이유로 `goto` 를 다시 읽게 했다).
    """
    import json as _json
    from datetime import timedelta

    from app.announcements.models import Announcement
    from app.approvals.models import ApprovalDelegation
    from app.backups.models import (
        BACKUP_TYPE_PG_DUMP, FILE_PRESENT, STATUS_VERIFIED, Backup, RestoreRehearsal,
    )
    from app.games.models import (
        GAME_QUICK_VOTE, GAME_RANDOM_DRAW, ROLE_HOST, ROLE_PLAYER, ROOM_WAITING,
        GameRoom, GameRoomMember,
    )
    from app.integrations.models import Integration
    from app.org.constants import DEFAULT_ORG_ID
    from app.prompts.models import STATUS_DRAFT, STATUS_PUBLISHED, Policy, Prompt
    from app.quotas.models import GLOBAL_USER_ID, PERIOD_DAY, SCOPE_GLOBAL, AiQuota
    from app.schedules.models import (
        RUN_FAILED, RUN_SUCCEEDED, TARGET_SYSTEM, TYPE_CRON, Schedule, ScheduleRun,
    )
    from app.users.models import User

    people = db.query(User).order_by(User.created_at).all()
    other = next((u for u in people if u.id != me.id), me)

    # 프롬프트·정책 (AI 저작). 발행본과 초안을 **같은 이름으로** 둔다 — 「버전 기록」 하위
    # 목록과 「초안일 때만 수정」 갈래는 한 이름에 판이 둘 이상이어야 화면에 나타난다.
    prompts = []
    for name, version, status, published in (
        ("티켓 요약", 1, STATUS_PUBLISHED, now - timedelta(days=3)),
        ("티켓 요약", 2, STATUS_DRAFT, None),
        ("회의록 정리", 1, STATUS_PUBLISHED, now - timedelta(days=9)),
    ):
        row = Prompt(name=name, purpose="%s 용 지시문입니다." % name, version=version,
                     content="다음 내용을 세 문장으로 요약해 주세요.",
                     status=status, created_by=me.id,
                     created_at=now - timedelta(days=10 - version),
                     published_at=published)
        db.add(row)
        prompts.append(row)
    for name, version, status in (("응답 길이 제한", 1, STATUS_PUBLISHED),
                                  ("금지어", 1, STATUS_DRAFT)):
        db.add(Policy(name=name, purpose="%s 정책입니다." % name, version=version,
                      content_json=_json.dumps({"max_tokens": 800}, ensure_ascii=False),
                      status=status, created_by=me.id,
                      created_at=now - timedelta(days=6),
                      published_at=(now - timedelta(days=5)
                                    if status == STATUS_PUBLISHED else None)))
    db.flush()

    # 실행 일정 + 실행 이력. 사용 통계 화면은 「이 프롬프트를 가리키는 일정이 있는가」로
    # «쓰이는가» 를 센다 — 일정이 하나도 없으면 모든 행이 «쓰이지 않음» 이라 판정력이 0 이다.
    schedules = []
    for i, (name, enabled, prompt_ref) in enumerate((
        ("야간 티켓 요약", True, prompts[0].id),
        ("주간 회의록 정리", False, prompts[2].id),
    )):
        row = Schedule(name=name, description="%s 을(를) 정해진 시각에 돌립니다." % name,
                       schedule_type=TYPE_CRON, cron_expression="0 %d * * *" % (2 + i),
                       owner_user_id=me.id, target_type=TARGET_SYSTEM,
                       target_ref="ai.summarize", prompt_id=prompt_ref,
                       enabled=enabled, next_run_at=now + timedelta(hours=6 + i),
                       last_run_at=now - timedelta(hours=18 - i))
        db.add(row)
        schedules.append(row)
    db.flush()
    for i, status in enumerate((RUN_SUCCEEDED, RUN_SUCCEEDED, RUN_FAILED)):
        db.add(ScheduleRun(
            schedule_id=schedules[0].id, scheduled_at=now - timedelta(days=i + 1),
            idempotency_key="s21-run-%d" % i, status=status,
            response_summary=("성공했습니다." if status == RUN_SUCCEEDED
                              else "대상이 응답하지 않았습니다."),
            started_at=now - timedelta(days=i + 1),
            finished_at=now - timedelta(days=i + 1) + timedelta(seconds=12)))

    # 공지 배너·AI 사용 상한. 공지 하나는 **꺼진 채로** 둔다: 「사용」 조건이 실제로 무엇을
    # 거르는지 보이게.
    for title, active in (("정기 점검 안내", True), ("지난 분기 공지", False)):
        db.add(Announcement(title=title, body="자세한 내용은 공지 게시판을 확인해 주세요.",
                            level="info", audience="all", active=active,
                            created_by=me.id, created_at=now - timedelta(days=2)))
    db.add(AiQuota(scope_type=SCOPE_GLOBAL, user_id=GLOBAL_USER_ID, period=PERIOD_DAY,
                   max_calls=500, note="전체 기본 상한입니다.", created_by=me.id))
    db.add(AiQuota(scope_type="user", user_id=other.id, period=PERIOD_DAY,
                   max_calls=50, note="개별 상한입니다.", created_by=me.id))

    # 외부 연동.
    for name, enabled, health in (("사내 메신저", True, "ok"), ("사내 위키", False, "unknown")):
        db.add(Integration(name=name, provider_type="http_service",
                           description="%s 로 보내는 바깥 호출입니다." % name,
                           base_url="https://example.invalid/%s" % name,
                           health_url="https://example.invalid/%s/health" % name,
                           auth_type="none", enabled=enabled, last_health_status=health,
                           last_health_at=now - timedelta(hours=1)))

    # 승인 위임.
    db.add(ApprovalDelegation(delegator_user_id=me.id, delegate_user_id=other.id,
                              reason="휴가 기간 동안 대신 결재합니다.",
                              starts_at=now - timedelta(days=1),
                              ends_at=now + timedelta(days=6), created_by=me.id))

    # 백업·복구 리허설. 리허설 하나는 **실패**로 둔다 — 성공만 있으면 실패 배지가 화면에
    # 있는지 확인할 방법이 없다(같은 이유로 `_seed_w10` 이 감사 실패 한 줄을 섞는다).
    for i in range(2):
        db.add(Backup(backup_type=BACKUP_TYPE_PG_DUMP,
                      path="/var/backups/clovirassist/2026082%d-020000/db.dump" % (3 + i),
                      status=STATUS_VERIFIED, size_bytes=48_000_000 + i, checksum="0" * 64,
                      created_by=me.id, created_at=now - timedelta(days=i + 1),
                      verified_at=now - timedelta(days=i + 1) + timedelta(minutes=4),
                      file_state=FILE_PRESENT,
                      manifest_json=_json.dumps({"tables": 93}, ensure_ascii=False)))
    for i, ok in enumerate((True, False)):
        db.add(RestoreRehearsal(
            source_label="2026082%d-020000" % (3 + i),
            started_at=now - timedelta(days=i + 1),
            finished_at=now - timedelta(days=i + 1) + timedelta(minutes=9), ok=ok,
            failures_json=None if ok else _json.dumps(["첨부 3건이 안 맞습니다."],
                                                      ensure_ascii=False),
            summary_json=_json.dumps({"tables": 93, "rows": 12004}, ensure_ascii=False),
            created_by=me.id))

    # 놀이방. **두 종류를 심는다** (S21): «준비/준비 해제» 는 `canReady = isDraw && …`
    # 라서 추첨 게임에만 있다(`frontend/src/screens/game-room/useGameRoomController.js`).
    # 투표 방만 심어 두면 그 동작은 영영 「버튼이 없다」로 적힌다 — 없는 것이 아니라
    # 이 방에 없는 것이다.
    draw = GameRoom(title="S21 추첨 방", game_type=GAME_RANDOM_DRAW, host_user_id=me.id,
                    status=ROOM_WAITING, max_players=8, allow_spectators=True,
                    org_id=DEFAULT_ORG_ID)
    db.add(draw)
    db.flush()
    db.add(GameRoomMember(room_id=draw.id, user_id=me.id, role=ROLE_PLAYER))

    room = GameRoom(title="점심 메뉴 정하기", game_type=GAME_QUICK_VOTE, host_user_id=me.id,
                    status=ROOM_WAITING, max_players=8, allow_spectators=True,
                    config_json=_json.dumps({"options": ["국밥", "돈가스", "비빔밥"]},
                                            ensure_ascii=False),
                    org_id=DEFAULT_ORG_ID)
    db.add(room)
    db.flush()
    db.add(GameRoomMember(room_id=room.id, user_id=me.id, role=ROLE_HOST))

    # 휴지통. **복원과 영구 삭제는 되돌릴 대상이 있어야 잴 수 있다.** 하나는 남이 버린
    # 것으로 둔다 — 「관리할 수 있는 행만 고를 수 있다」는 두 종류가 섞여야 보인다.
    from app.org.constants import DEFAULT_ORG_ID as _ORG
    from app.trash.models import TRASH_DOCUMENT, TRASH_TICKET, TrashItem

    # **여섯 건을 심는다.** 이 화면의 Flow 는 복원·영구 삭제·일괄 복원·일괄 영구 삭제를
    # 차례로 하는데, 셋만 심으면 뒤의 두 Flow 가 「고를 행이 없다」로 죽는다 — 화면이
    # 아니라 씨앗이 모자란 것이다.
    for i, (kind, title, owner) in enumerate((
        (TRASH_TICKET, "업무 90 — 버린 티켓", me),
        (TRASH_DOCUMENT, "문서 90 — 버린 문서", me),
        (TRASH_TICKET, "업무 91 — 남이 버린 티켓", other),
        (TRASH_TICKET, "업무 92 — 버린 티켓", me),
        (TRASH_DOCUMENT, "문서 92 — 버린 문서", me),
        (TRASH_TICKET, "업무 93 — 버린 티켓", me),
    )):
        db.add(TrashItem(
            item_type=kind, notion_page_id="s21-trash-%02d" % i, title=title,
            url=None, target_uid=None, deleted_by_user_id=owner.id,
            deleted_by_name=owner.display_name or "", deleted_at=now - timedelta(hours=i + 1),
            org_id=_ORG))


def _seed_w10(db, me, now) -> None:
    """W10 의 사용자 화면이 **비어 있지 않게** 한다 (S19).

    S18 의 씨앗은 Pilot 8 원형을 겨냥했다. 그 위에서 W10 이 담당하는 나머지 사용자
    화면 넷은 여전히 빈 화면이었다 — 기능 개선 제안(`/ideas`)에 글이 하나도 없고,
    놀이(`/games`)에 방이 없고, 승인(`/my-approvals`)에 결재할 건이 없고,
    내 활동(`/activity`)에 줄이 없다.

    빈 화면을 찍어 놓고 「그 화면을 봤다」고 적으면 그 회차는 아무것도 본 것이 없다.
    표의 열이 겹치는지, 상태 배지가 값마다 갈리는지, 작성자 칸이 소속까지 그리는지는
    **행이 있어야만** 보인다. 반대로 빈 화면 자체도 봐야 하는 얼굴이라, 그 얼굴은
    조건을 걸어 만든다(검색어를 못 맞히는 목록) — 씨앗을 비워서 만들지 않는다.
    """
    from datetime import datetime, timedelta, timezone

    from app.approvals.models import Approval
    from app.audit.models import AuditLog
    from app.board.models import (
        IDEA_CATEGORIES, IDEA_STATUSES, KIND_IDEA, LIKE_EMOJI, Post, Reaction,
    )
    from app.board.models import Comment as BoardComment
    from app.games.models import (
        ROOM_FINISHED, ROOM_PLAYING, ROOM_WAITING, GameRoom, GameRoomMember,
    )
    from app.org.constants import DEFAULT_ORG_ID
    from app.users.models import User

    people = list(db.query(User).order_by(User.created_at, User.id).all()) or [me]

    # ── 기능 개선 제안 (`/ideas`) ────────────────────────────────────────────
    # 열이 여섯이고 그중 넷(카테고리·상태·작성자·작성)이 값마다 폭이 다르다. 한 값만
    # 심으면 그 열들이 전부 같은 폭으로 서고, 머리글이 겹치는지 본문이 잘리는지가
    # **씨앗 때문에 안 보인다.** 그래서 분류 넷과 상태 다섯을 다 돌린다.
    cats = sorted(IDEA_CATEGORIES)
    titles = (
        "티켓 목록에서 담당자를 바로 바꿀 수 있으면 좋겠습니다",
        "문서 검색이 본문까지 찾도록 해 주세요",
        "알림을 종류별로 끄고 켤 수 있으면 좋겠습니다",
        "스프린트 주간 보고를 자동으로 만들어 주세요",
        "첨부 파일을 목록에서 미리 볼 수 있으면 좋겠습니다",
        "채팅방을 즐겨찾기에 고정하고 싶습니다",
    )
    idea_body = (
        "지금은 티켓을 하나씩 열어 담당자를 바꿔야 해서 열 건을 옮기는 데 시간이 오래 "
        "걸립니다. 목록에서 바로 바꿀 수 있으면 좋겠습니다.\n\n"
        "권한이 있는 사람만 바꿀 수 있어야 하고, 바꾼 뒤에는 담당자에게 알림이 가야 "
        "합니다. 지금 화면에서 이미 되는 부분이 있으면 알려 주세요."
    )
    ideas = []
    for i in range(22):
        author = people[i % len(people)]
        post = Post(
            author_user_id=author.id, org_id=DEFAULT_ORG_ID, kind=KIND_IDEA,
            category=cats[i % len(cats)],
            idea_status=IDEA_STATUSES[i % len(IDEA_STATUSES)],
            title="%s (%02d)" % (titles[i % len(titles)], i + 1),
            body=idea_body,
            view_count=(i * 13) % 97,
            is_pinned=(i == 0),
            created_at=now - timedelta(hours=i * 3),
        )
        db.add(post)
        ideas.append(post)
    db.flush()
    # 공감은 새 표가 아니라 반응 중 👍 다(`board/models.py`). 값이 0 뿐이면 「공감」 열의
    # 자릿수 정렬을 확인할 수 없다.
    for i, post in enumerate(ideas):
        for person in people[: i % 4]:
            db.add(Reaction(target_type="post", target_id=post.id, user_id=person.id,
                            emoji=LIKE_EMOJI, created_at=now - timedelta(minutes=i)))
    for i, person in enumerate(people[:3]):
        db.add(BoardComment(post_id=ideas[0].id, author_user_id=person.id,
                            body="같은 불편을 겪고 있습니다 (%d)." % (i + 1),
                            created_at=now - timedelta(minutes=40 - i)))

    # ── 놀이 (`/games` · `/games/:id`) ──────────────────────────────────────
    # 상태 셋이 다 있어야 카드의 배지가 무엇을 구별하는지 보인다. 방 하나는 참가자를
    # 정원까지 채워 「자리 없음」 쪽도 화면에 나오게 한다.
    # 🔴 방의 `last_seen` 만은 **씨앗 시각이 아니라 진짜 지금**이어야 한다.
    # `list_rooms` 가 먼저 `cleanup_idle_rooms` 를 부르고, 그것은 참여자의 마지막 폴링이
    # 180초보다 오래됐으면 방을 닫는다(`service.IDLE_ROOM_SECONDS`). 고정 시각을 넣으면
    # 방을 심자마자 전부 닫혀 화면이 언제나 빈 목록이 되고, 그 빈 화면이 제품 결함처럼
    # 보인다. 씨앗이 제품에 없는 상태를 만든 S18 의 `done` 과 같은 부류다.
    live = datetime.now(timezone.utc).replace(tzinfo=None)
    rooms = (
        ("점심 내기 추첨", "random_draw", ROOM_WAITING, 8, 3),
        ("회식 장소 투표", "quick_vote", ROOM_PLAYING, 6, 5),
        ("스터디 팀 나누기", "team_split", ROOM_FINISHED, 4, 4),
        ("숫자 눈치 한 판", "number", ROOM_WAITING, 10, 2),
    )
    for r, (title, gtype, status, cap, joined) in enumerate(rooms):
        room = GameRoom(
            title=title, game_type=gtype, host_user_id=me.id, status=status,
            max_players=cap, allow_spectators=True, org_id=DEFAULT_ORG_ID,
            event_seq=joined,
            # 게임이 끝난 것(`finished`)과 방이 닫힌 것(`closed_at`)은 다른 사실이다 —
            # 목록은 닫힌 방을 아예 안 보여 주므로(`list_open_rooms`), 「결과 확인 중」
            # 배지를 화면에서 확인하려면 끝난 방이 열려 있어야 한다.
            closed_at=None,
            created_at=live - timedelta(minutes=r * 7),
        )
        db.add(room)
        db.flush()
        for m in range(joined):
            person = people[m % len(people)]
            db.add(GameRoomMember(
                room_id=room.id, user_id=person.id, display_name=person.display_name,
                role="host" if m == 0 else "player", ready=(m % 2 == 0),
                joined_at=live - timedelta(minutes=r), last_seen=live))

    # ── 승인 (`/my-approvals`) ──────────────────────────────────────────────
    # 세 칸이 서로 다른 것을 담는다(처리할 것 · 내가 올린 것 · 내가 처리한 것). 한 칸만
    # 채우면 나머지 둘의 빈 상태가 전부 같은 얼굴로 보이고, 그 얼굴이 맞는지 알 수 없다.
    requesters = [p for p in people if p.id != me.id] or [me]
    # 대기 건은 `(request_type, object_id, payload)` 로 중복이 막혀 있다
    # (`ux_approvals_pending_dedup`). 같은 요청을 두 번 심을 수 없다는 뜻이라 —
    # 그것이 제품의 계약이다 — 값을 실제로 다르게 만든다.
    # 🔴 **제품이 실제로 만드는 종류만** 심는다. 서버가 승인을 거는 자리는 셋뿐이다
    # (`app/users/router.py` 의 `user.role_change` · `app/integrations/router.py` 의
    # `integration.change_config` · `app/schedules/router.py` 의 `schedule.enable`).
    # 없는 종류를 심으면 화면이 그 값을 모르는 채 절반만 번역된 라벨을 그리고, 그것이
    # 제품 결함처럼 보인다 — S18 이 `done` 으로 같은 함정에 빠졌다.
    pending = (
        ("user.role_change", "user", '{"to": "operator"}'),
        ("user.role_change", "user", '{"to": "admin"}'),
        ("user.role_change", "user", '{"to": "auditor"}'),
        ("integration.change_config", "integration", '{"enabled": true}'),
        ("integration.change_config", "integration", '{"enabled": false}'),
        ("schedule.enable", "schedule", '{"cron": "0 9 * * 1"}'),
        ("schedule.enable", "schedule", '{"cron": "0 18 * * 5"}'),
    )
    for i, (req_type, obj_type, payload) in enumerate(pending):
        who = requesters[i % len(requesters)]
        db.add(Approval(
            request_type=req_type, object_type=obj_type,
            object_id="%s-%02d" % (obj_type, i + 1),
            requested_by=who.id,
            approver_id=None, status="pending", request_payload_json=payload,
            requested_at=now - timedelta(hours=i + 1),
            expires_at=now + timedelta(hours=72 - i),
        ))
    for i in range(3):
        db.add(Approval(
            request_type="schedule.enable", object_type="schedule",
            object_id="mine-%02d" % (i + 1),
            requested_by=me.id, approver_id=None, status="pending",
            request_payload_json='{"mine": %d}' % (i + 1),
            requested_at=now - timedelta(hours=i + 2),
        ))
    for i, state in enumerate(("approved", "rejected")):
        db.add(Approval(
            request_type="user.role_change", object_type="user",
            object_id="decided-%02d" % (i + 1),
            requested_by=requesters[i % len(requesters)].id,
            approver_id=me.id, status=state,
            request_payload_json='{"decided": %d}' % (i + 1),
            requested_at=now - timedelta(days=i + 1),
            decided_at=now - timedelta(days=i + 1) + timedelta(hours=2),
        ))

    # ── 내 활동 (`/activity`) ───────────────────────────────────────────────
    # 「내가 한 일」은 감사 로그에서, 「나에게 일어난 일」은 알림에서 온다. 알림은 위에서
    # 이미 심었으므로 여기서는 감사 쪽만 채운다. 실패 한 줄을 섞는다 — 성공만 있으면
    # 실패 배지가 화면에 있는지 확인할 방법이 없다.
    acts = (
        ("board_post.create", "board_post", "success"),
        ("notion_task.update", "notion_task", "success"),
        ("document.update", "document", "success"),
        ("notion_task.create", "notion_task", "success"),
        ("board_post.update", "board_post", "failure"),
    )
    for i in range(14):
        action, obj_type, result = acts[i % len(acts)]
        db.add(AuditLog(
            user_id=me.id, action=action, object_type=obj_type,
            object_id=(ideas[i % len(ideas)].id if obj_type == "board_post" else None),
            result=result, created_at=now - timedelta(hours=i * 5)))


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
    ap.add_argument("--db-name", default="", help="고정 데이터베이스 이름 (S21 bounded batch)")
    ap.add_argument("--data-dir", default="", help="고정 작업 디렉터리 (비밀·업로드)")
    ap.add_argument("--keep", action="store_true",
                    help="끝나도 데이터베이스를 안 지운다 — 여러 묶음이 같은 씨앗을 본다")
    args = ap.parse_args()

    import tempfile

    if args.db_name:
        set_db_name(args.db_name)
    workdir = Path(args.data_dir) if args.data_dir else Path(
        tempfile.mkdtemp(prefix="clovir-uiqa-"))
    workdir.mkdir(parents=True, exist_ok=True)
    url = create_database()
    try:
        settings = build_settings(url, workdir)
        seed(url, args.email, args.password, settings)
        port = args.port or _free_port()
        server, _ = serve(settings, port)
        print("http://127.0.0.1:%d" % port, flush=True)
        # 다른 프로세스(하네스 묶음)가 같은 DB·같은 비밀 디렉터리를 보게 하는 데 필요한 값.
        # 이것을 안 알려 주면 `auth.py` 의 역할 계정 프로비저닝이 **기본 주소**로 붙다가
        # 시간 초과로 죽는다 — 실제로 S21 첫 실행이 그렇게 죽었다.
        print("DATABASE_URL=%s" % url, flush=True)
        print("DATA_DIR=%s" % workdir, flush=True)
        print("SECRETS_DIR=%s" % settings.secrets_dir, flush=True)
        if args.hold:
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        server.should_exit = True
        time.sleep(0.5)
    finally:
        if not args.keep:
            drop_database()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
