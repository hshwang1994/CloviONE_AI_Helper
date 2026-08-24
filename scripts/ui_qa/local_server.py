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
        for name in ("포털 개편", "인프라 정비"):
            p = Project(name=name, org_id=DEFAULT_ORG_ID)
            work_codes.insert_with_code(db, p)
            db.flush()
            projects.append(p)

        now = datetime(2026, 8, 24, 3, 0, 0)
        statuses = ["진행", "계획", "검증", "완료"]
        prios = ["High", "Normal", "Low"]
        diffs = ["상", "중", "하"]
        for i in range(24):
            db.add(TicketCache(
                title=f"업무 {i + 1:02d} — 화면에서 읽히는 제목",
                status=statuses[i % 4], priority=prios[i % 3], difficulty=diffs[i % 3],
                category=("인프라" if i % 2 else "포털"),
                due_date=date(2026, 8, 20) + timedelta(days=i % 7),
                est_wd=1.5, act_wd=1.0,
                project_uid=projects[i % 2].id, project_link=PROJECT_LINK_OK,
                project_names=projects[i % 2].name,
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

        for i in range(26):
            db.add(Post(author_user_id=me.id, org_id=DEFAULT_ORG_ID, kind="free",
                        category=("공지" if i % 3 == 0 else "자유"),
                        title=f"게시글 {i + 1:02d}", body="본문",
                        is_pinned=(i == 0), created_at=now - timedelta(hours=i)))
        for i in range(24):
            db.add(Notification(
                user_id=me.id, type="ticket_assigned",
                audience=("admin" if i % 2 else "user"),
                title=f"알림 {i + 1:02d}", body="본문",
                read_at=None if i < 12 else now, created_at=now - timedelta(minutes=i)))
        db.commit()
    engine.dispose()


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
