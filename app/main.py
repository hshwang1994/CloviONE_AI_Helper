"""FastAPI application factory.

Run in development:
    uvicorn "app.main:create_app" --factory --host 127.0.0.1 --port 8080
Production runs the same factory via systemd (spec §26.1).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.assets import AssetVersions
from fastapi.templating import Jinja2Templates

from app.admin.feature_flags import router as feature_flags_router
from app.admin.rbac import router as rbac_matrix_router
from app.admin.router import router as admin_router
from app.announcements.router import admin_router as announcements_admin_router
from app.announcements.router import user_router as announcements_user_router
from app.approvals.router import delegations_router as approval_delegations_router
from app.approvals.router import personal_router as personal_approvals_router
from app.integrity.router import router as integrity_router
from app.approvals.router import router as approvals_router
from app.assistant.router import router as assistant_router
from app.audit.router import router as audit_router
from app.backups.router import router as backups_router
from app.auth.router import router as auth_router
from app.board.router import router as board_router
from app.games.router import router as games_router
from app.chat.router import router as chat_router
from app.notifications.router import router as notifications_router
from app.core.allowlist import AllowlistRegistry
from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.db import make_engine, make_session_factory
from app.core.logging_setup import configure_logging
from app.core.errors import register_error_handlers
from app.core.http_client import OutboundClient
from app.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from app.core.ratelimit import RateLimiter
from app.core.secret_refs import FileSecretReferenceProvider
from app.core.sessions import SessionService
from app.documents.router import router as documents_router
from app.health.router import router as health_router
from app.home.router import router as home_router
from app.impersonation.router import router as impersonation_router
from app.integrations.router import router as integrations_router
from app.jobs.router import router as jobs_router
from app.auth.reset_router import router as password_reset_router
from app.mail.router import router as mail_router
from app.llm_console.router import router as llm_console_router
from app.notion_console.router import router as notion_console_router
from app.notion_mapping.router import router as notion_mapping_router
from app.offboarding.router import router as offboarding_router
from app.org.router import (
    departments_router,
    job_titles_router,
    organizations_router,
)
from app.observability.router import router as system_status_router
from app.profiles.router import router as profiles_router
from app.projects.router import router as projects_router
from app.quotas.router import router as ai_quotas_router
from app.prompts.router import policies_router, prompts_router
from app.reports.router import router as reports_router
from app.search.reindex_router import router as search_reindex_router
from app.search.router import router as search_router
from app.tickets.router import router as tickets_router
from app.runners.router import router as runners_router
from app.schedules.router import router as schedules_router
from app.settings.router import router as settings_router
from app.settings.service import SettingsCache
from app.setup.router import router as setup_router
from app.sysops.router import router as sysops_router
from app.team_docs.router import router as team_docs_router
from app.trash.router import router as trash_router
from app.sprints.router import router as sprint_router
from app.team_chat.router import router as team_chat_router
from app.templates.router import router as templates_router
from app.users.router import router as users_admin_router
from app.workflows.router import router as workflows_router

APP_DIR = Path(__file__).resolve().parent

logger = logging.getLogger("app.main")


def create_app(
    settings: Settings | None = None,
    *,
    clock: Clock | None = None,
    outbound_transport=None,
) -> FastAPI:
    settings = settings or Settings()
    clock = clock or SystemClock()

    # root 로거에 핸들러를 붙인다. 없으면 `app.*` 의 로그가 전부 버려진다 — 액세스 로그
    # (= request_id 를 담은 유일한 줄)까지 포함해서. app/core/logging_setup.py 참조.
    configure_logging()

    app = FastAPI(
        title="ClovirAssist Web Assistant",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.clock = clock

    engine = make_engine(settings.database_url)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)

    # Effective-settings cache: load once at startup so consumers read live
    # values without a DB round-trip (session/password policy, retention, …).
    # `settings` 를 함께 넘긴다: 노션 DB id 와 LLM 설정의 소비자는 전부 `settings.<key>` 를
    # 읽으므로(app/core/tenant_config.py::apply_overrides) 캐시가 그 위에 얹어 줘야 관리
    # 콘솔에서 바꾼 값이 실제 조회에 반영된다. 안 넘기면 화면만 바뀌고 동작은 옛 값이다.
    app.state.settings_cache = SettingsCache(settings)
    try:
        with app.state.session_factory() as _db:
            app.state.settings_cache.load(_db)
    except Exception:
        # CORE-12: 이 except가 두 가지를 구별 없이 삼켰다 — ① 정말 기대한 경우(첫
        # 마이그레이션 전이라 테이블이 아직 없음, 무해함)와 ② DB 잠금·손상 같은 진짜
        # 장애. ②일 때도 조용히 넘어가면 `settings_cache`가 DB 오버라이드 없이
        # env/기본값으로 굳고, 관리자가 설정 화면에서 바꾼 값이 실제 조회에 안 실리는데
        # 그 사실을 알 방법이 로그 어디에도 없었다. 기동을 막지는 않되(설치 직후 실행이
        # 여전히 정상 흐름이어야 한다) 최소한 로그에는 남긴다.
        logger.warning(
            "설정 캐시 초기 로드에 실패했다(첫 마이그레이션 전이면 정상). "
            "그게 아니라면 DB 오버라이드 없이 기본값으로 기동한 것이다",
            exc_info=True,
        )

    app.state.session_service = SessionService(settings, clock, app.state.settings_cache)
    # Login brute-force guard (spec §25.2): ~10 attempts/min per client IP.
    app.state.login_ratelimiter = RateLimiter(
        capacity=10, refill_per_second=10 / 60, clock=clock
    )
    # Chat-send guard: 사용자당 채팅 전송 폭주가 단일 워커 잡 큐를 막고 다운스트림 러너/n8n에
    # 부하·비용을 주는 것을 막는다. 버스트 20건, 지속 ~30건/분(refill 0.5/s).
    app.state.chat_ratelimiter = RateLimiter(
        capacity=20, refill_per_second=0.5, clock=clock
    )
    # AI 퀴즈 생성 guard: LLM 호출은 비싸고 남용 가능하므로 채팅보다 더 조인다. 버스트 5건,
    # 지속 ~5건/분(refill 5/60). 러너의 동시성 슬롯(2)과 비용을 보호한다.
    app.state.game_ai_ratelimiter = RateLimiter(
        capacity=5, refill_per_second=5 / 60, clock=clock
    )
    # AI 도우미 요약 문장(브리핑·스탠드업·주간 다이제스트) guard. 화면 진입 길목이라 퀴즈보다
    # 조금 넉넉하되(버스트 6건, 지속 ~12건/분), 여전히 러너 슬롯을 보호한다. 문장 생성이 꺼져
    # 있으면 이 리미터는 아예 쓰이지 않는다(호출이 나가지 않으므로 토큰도 소비하지 않는다).
    app.state.assistant_ratelimiter = RateLimiter(
        capacity=6, refill_per_second=12 / 60, clock=clock
    )

    app.state.allowlists = AllowlistRegistry(settings.config_dir)
    app.state.secret_provider = FileSecretReferenceProvider(settings.secrets_dir)
    app.state.outbound_client = OutboundClient(
        app.state.allowlists, app.state.secret_provider, transport=outbound_transport
    )

    # 티켓·문서 저장소 배선(§7.1.C). 소스 선택은 여기 한 번뿐이고 라우터는 app.state 에서
    # 꺼내 쓴다 — 설정이 잘못돼 있으면 요청 때가 아니라 지금(기동 시) 분명히 실패한다.
    from app.core.source_registry import install as install_repositories

    install_repositories(app)

    # add_middleware: last added runs outermost — RequestContext must wrap everything.
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    _register_page_redirects(app)

    app.state.templates = Jinja2Templates(directory=str(APP_DIR / "templates_html"))
    # 템플릿이 정적 파일을 부를 때 내용 지문을 붙인다. 이것이 없으면 배포해도 사용자
    # 브라우저가 한 시간 동안 옛 CSS/JS를 붙잡는다(nginx와 앱 모두 max-age=3600).
    static_dir = APP_DIR / "static"
    app.state.assets = AssetVersions(static_dir)
    app.state.templates.env.globals["asset"] = app.state.assets.stamp
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(health_router)
    app.include_router(auth_router)
    # 로그인 라우터 바로 뒤에 둔다 - 세션이 없는 상태에서 부르는 경로라 인접한 것이 맞다.
    app.include_router(password_reset_router)
    app.include_router(mail_router)
    app.include_router(profiles_router)
    app.include_router(chat_router)
    app.include_router(users_admin_router)
    app.include_router(offboarding_router)
    app.include_router(rbac_matrix_router)
    app.include_router(impersonation_router)
    app.include_router(organizations_router)
    app.include_router(departments_router)
    app.include_router(job_titles_router)
    app.include_router(audit_router)
    app.include_router(integrations_router)
    app.include_router(jobs_router)
    app.include_router(runners_router)
    app.include_router(workflows_router)
    app.include_router(prompts_router)
    app.include_router(policies_router)
    app.include_router(templates_router)
    app.include_router(schedules_router)
    app.include_router(approvals_router)
    # 개인 결재함(0060) — 관리자 콘솔 큐와 **다른 경로**다. 위임받은 일반 사용자가
    # 관리자 콘솔 없이 자기 결재를 처리할 수 있어야 한다.
    app.include_router(personal_approvals_router)
    # 조직 정합성 진단(0060) — fail-closed 규칙이 닫아 버린 대상을 사람에게 보여 주고
    # 일괄로 지정하게 한다. 규칙과 같은 배포에 있어야 복구가 몇 분짜리 일이 된다.
    app.include_router(integrity_router)
    app.include_router(approval_delegations_router)
    app.include_router(notifications_router)
    app.include_router(board_router)
    app.include_router(games_router)
    app.include_router(team_docs_router)
    app.include_router(settings_router)
    app.include_router(documents_router)
    app.include_router(notion_mapping_router)
    app.include_router(reports_router)
    app.include_router(search_router)
    app.include_router(search_reindex_router)
    app.include_router(tickets_router)
    # 프로젝트(0044). 앱 DB 가 정본이고 진행률은 앱이 다시 계산한다 — Notion 의 rollup 은
    # 취소한 티켓을 완료로 세기 때문이다(app/projects/progress.py).
    app.include_router(projects_router)
    app.include_router(trash_router)
    app.include_router(sprint_router)
    # 홈 '오늘' 커맨드 센터와 AI 도우미 심화(계획서 Phase 5). 둘 다 조회 전용이고
    # 티켓은 저장소 seam 을 통해서만 읽는다(미러가 채워져 있으면 Notion 왕복 0회).
    app.include_router(home_router)
    app.include_router(assistant_router)
    app.include_router(team_chat_router)
    app.include_router(backups_router)
    # 관리자 백로그 잔여(0033, PLAN Phase 6). 공지는 관리자용/사용자용 두 라우터로
    # 나뉜다 — 같은 데이터지만 권한과 응답 모양이 다르다.
    app.include_router(announcements_admin_router)
    app.include_router(announcements_user_router)
    app.include_router(ai_quotas_router)
    app.include_router(feature_flags_router)
    # 사용자 화면 시스템 상태 배너(0026 sync_status + 러너 헬스 소비).
    app.include_router(system_status_router)
    # 운영 콘솔의 시스템 설정(§S). 실제 변경은 root 로 도는 특권 헬퍼가 하고, 웹은 이름표만
    # 전달한다 — 웹 유닛은 하드닝돼 있어 /etc 를 쓸 수 없다(그 하드닝을 풀지 않는 것이 요점이다).
    app.include_router(sysops_router)
    # 최초 실행 셋업 체크리스트(9-3). 읽기 전용이고 판정은 이미 있는 것을 모아서 한다
    # (app/setup/probes.py) - 여기서 설정을 바꾸지는 않는다.
    app.include_router(setup_router)
    # Notion 관리(9-4)와 LLM 관리(9-5). 둘 다 설정 값 자체는 설정 레지스트리를 지나고
    # (검증·감사·버전 이력·되돌리기가 거기 있다), 이 두 라우터는 레지스트리로 표현할 수 없는
    # 것만 맡는다: 시크릿 파일, 실제 연결 테스트, 노션 데이터베이스 생성.
    app.include_router(notion_console_router)
    app.include_router(llm_console_router)
    app.include_router(admin_router)
    return app


def _register_page_redirects(app: FastAPI) -> None:
    from fastapi import Request
    from fastapi.responses import RedirectResponse

    from app.core.deps import PageAuthRequired
    from app.core.sessions import SESSION_COOKIE_NAME

    @app.exception_handler(PageAuthRequired)
    async def _page_auth_redirect(request: Request, exc: PageAuthRequired):
        # 세션 만료/미인증으로 튕겨나갈 때 원래 있던 화면(예: /admin의 특정 섹션)을 잊는다 —
        # 로그인 후 항상 '/'로 떨어져, 다시 원래 위치까지 수동으로 되찾아가야 했다.
        # same-origin 상대 경로만 이어붙인다(open-redirect 방지, §7 체크리스트): "//evil.com"
        # 같은 프로토콜-상대 형태와 /login 자기 자신(무한 루프)은 제외한다.
        path = request.url.path
        params = []
        if path.startswith("/") and not path.startswith("//") and path != "/login":
            from urllib.parse import quote

            params.append("next=" + quote(path, safe=""))
        # 쿠키가 있었는데 여기로 왔다는 것은 "한 번도 로그인한 적 없음"이 아니라 "일하다가
        # 세션이 끊김"이다 — 그 경우에만 login.html에 문맥 있는 안내를 띄운다(순수 첫 방문엔
        # 굳이 '만료됐다'고 말할 근거가 없다).
        if request.cookies.get(SESSION_COOKIE_NAME):
            params.append("expired=1")
        next_url = ("?" + "&".join(params)) if params else ""
        return RedirectResponse(f"/login{next_url}", status_code=303)
