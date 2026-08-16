"""Application settings (spec §28).

Values come from environment variables (systemd EnvironmentFile in production)
or a local ``.env`` file during development. Tests construct ``Settings``
directly with explicit overrides and ``_env_file=None``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8080
    app_base_url: str = "http://127.0.0.1:8080"

    database_url: str = "sqlite:///./var/web.sqlite3"

    n8n_work_assistant_url: str = "http://127.0.0.1:5678/webhook/clovirone-work-assistant"
    n8n_timeout_seconds: int = 180

    session_secret: str = ""
    session_ttl_seconds: int = 28800
    session_idle_timeout_seconds: int = 1800

    max_message_length: int = 5000
    login_max_failures: int = 5
    login_lock_seconds: int = 900

    trusted_proxy: str = "127.0.0.1"
    cookie_secure: bool = True
    timezone: str = "Asia/Seoul"
    # 설치처 고유값이라 기본값이 없다(app/core/tenant_config.py 에 왜 비웠는지 적어 뒀다).
    # **빈 값은 '계정 생성 시 도메인 제한 없음'** 이다. 로그인은 이 값을 보지 않으므로
    # (app/auth/router.py 는 도메인을 검사하지 않는다) 비워도 아무도 잠기지 않는다 —
    # 계정을 새로 만들 때 이메일 도메인을 안 따진다는 뜻일 뿐이고, 계정 생성 자체가
    # 관리자 전용이다(관리 콘솔·일괄 등록·CLI). 방향을 반대로 잡으면 설치 직후 아무도
    # 계정을 못 만든다.
    allowed_email_domains: str = ""

    # Directory holding allowed-services.json / allowed-runners.json /
    # allowed-workflows.json / feature-flags.json (spec §8: /etc/clovirone-web-assistant
    # in production, ./config in development).
    config_dir: Path = Path("config")
    secrets_dir: Path = Path("var/secrets")
    data_dir: Path = Path("var")

    # Optional path to the TLS cert for expiry monitoring on the dashboard
    # (production: /etc/clovirone-web-assistant/tls/*.crt). None in dev/tests.
    tls_cert_path: str | None = None

    # 개발자 월간 리포트(§ 개발자 리포트): 앱 서버가 Notion "작업" 데이터베이스를 직접 읽어
    # 담당자별 업무 현황을 집계한다. Notion 호출은 다른 외부 호출과 마찬가지로 OutboundClient
    # 단일 관문을 지나며(allowlist=services), 토큰은 secrets_dir/<notion_report_token_ref>
    # 파일에서만 읽는다(평문 노출 없음). 토큰이 없으면 화면은 '연동 필요' 안내를 보여준다.
    notion_api_base: str = "https://api.notion.com"
    notion_api_version: str = "2022-06-28"
    # 설치처마다 다른 값이라 기본값이 없다. 예전엔 개발 워크스페이스의 DB id 가 박혀 있어서
    # 다른 고객사에 설치하면 아무 설정 없이도 조용히 남의 워크스페이스를 가리켰다.
    # 비어 있으면 외부 호출을 내보내기 전에 '설정 안 됨' 으로 끊는다
    # (app/reports/notion_source.py::_require_tasks_database_id).
    notion_tasks_database_id: str = ""
    notion_report_token_ref: str = "notion_report_token"
    # 티켓 로컬 미러 동기화 주기(PLAN §A). 문서(600s)보다 자주 도는 이유는 티켓이 회의 중에도
    # 바뀌기 때문이다. 생성/편집은 캐시를 즉시 패치하므로 이 주기는 '다른 사람이 노션에서 직접
    # 고친 것'이 반영되는 지연일 뿐이다.
    notion_tickets_sync_interval_seconds: int = 180
    # 프로젝트 미러 동기화 주기(0045). 티켓(180s)보다 느슨한 이유: 프로젝트의 이름·기간·담당자는
    # 회의 중에 바뀌는 값이 아니다. 포털에서 고친 값은 그 자리에서 노션으로 밀어 넣으므로
    # (push) 이 주기는 '다른 사람이 노션에서 직접 고친 것'이 반영되는 지연일 뿐이다.
    # 프로젝트 DB id 는 설정에 없다 — 작업 DB 의 프로젝트 relation 을 따라간다
    # (app/projects/notion_source.py 에 왜 설정으로 안 두는지 적어 뒀다).
    notion_projects_sync_interval_seconds: int = 600
    # 팀이 Notion 에서 쓰는 **스프린트 데이터베이스**(9-4). 비어 있는 것이 기본이고, 비어
    # 있어도 포털은 멀쩡히 돈다 - 포털의 '이번 주' 는 작업 DB 의 마감일로 계산하기 때문이다
    # (app/sprints/service.py::default_sprint_window). 바로 그것이 문제라서 이 값이 생겼다:
    # 두 화면이 같은 이름('스프린트')으로 **서로 다른 것**을 부르고 있고, 아무 데서도 그
    # 사실을 말하지 않았다. 값을 넣으면 Notion 관리 화면이 그 DB 를 실제로 한 번 불러
    # '통합에 공유되지 않음(404)' 을 구분해 말한다. 넣지 않으면 '연결 안 됨' 이라고 말한다.
    notion_sprint_database_id: str = ""

    # 팀 공간 > 문서(§17): Notion "문서" 데이터베이스를 읽어 로컬 캐시로 미러링한다(장애 격리:
    # Notion이 죽어도 마지막 정상 동기화 데이터로 목록을 보여준다). 토큰은 secrets_dir 파일
    # 참조로만 읽고(평문 미노출), 없으면 화면은 '연동 필요'를 보여준다. tasks 토큰과 같은 값이어도
    # 무방하다(별도 ref로 두어 문서 접근만 따로 회수/교체 가능).
    # 작업 DB id 와 같은 이유로 기본값이 없다. 비어 있으면 문서 목록은 채워지지 않고,
    # 그 사실은 진단의 '설치처 설정'(app/core/tenant_config.py)이 말한다.
    notion_documents_database_id: str = ""
    notion_docs_token_ref: str = "notion_docs_token"
    notion_docs_sync_interval_seconds: int = 600

    # 통합 검색 인덱스 재구축 주기(PLAN Phase 5). **워커 틱에서만** 돈다 — 채팅 전송·폴링
    # 같은 뜨거운 경로에는 훅을 걸지 않는다(app/search/indexer.py docstring).
    # 티켓 미러(180s)보다 조금 느슨하게 잡는다: 검색 결과가 한 틱 늦는 것은 사람이 못 느끼고,
    # 인덱싱은 네 유형을 전부 다시 읽으므로 미러 동기화보다 비싸다.
    search_index_interval_seconds: int = 300

    # 대화형 워커 레인(D-118, Phase 1 — 아직 아무 실행 경로도 이 값들을 안 쓴다). 켜지면
    # chat_message/llm_connection_test가 별도 워커 프로세스(별도 systemd 유닛)에서
    # `max_concurrency`개까지 동시에 처리되고, 배치 워커는 그 두 job_type을 스케줄 실행 등
    # 배치 잡보다 뒤로 미룬다(단, `takeover_seconds`를 넘겨 계속 대기 중이면 배치 워커가
    # 대신 처리한다 — 대화형 프로세스가 없거나 죽었을 때 채팅이 조용히 영영 안 처리되는
    # 것을 막는 안전장치).
    worker_conversational_lane_enabled: bool = False
    worker_conversational_concurrency: int = 3
    worker_conversational_takeover_seconds: float = 120.0

    # 주간 프로젝트 헬스 스냅샷 주기. **워커에서만** 돈다.
    #
    # '주간' 이력인데 왜 한 시간인가: 스냅샷은 (프로젝트, 주) 유일 키로 upsert 하므로 여러 번
    # 돌아도 그 주의 행은 한 줄이다. 정확히 주 1회로 잡으면 그 한 번이 배포, 재시작, 장애와
    # 겹쳤을 때 **그 주가 통째로 비고**, 몇 주 뒤 추세선에서 그 구멍은 '값이 나쁜 주' 와
    # 구별되지 않는다. 자주 확인하는 편이 싸고(이미 로컬 미러에 있는 행만 읽는다) 안전하다.
    # 회차마다 프로젝트 행의 `updated_at` 을 덮지 않는 것이 전제다
    # (app/projects/service.py::record_health_snapshot).
    project_health_snapshot_interval_seconds: int = 3600

    # 팀 공간 놀이 > AI 퀴즈 생성(§7-9). 앱은 Claude를 직접 부르지 않고(불변 §10 임의 shell 금지)
    # 러너의 전용 엔드포인트(/v1/assistant/quiz)를 OutboundClient(allowlist=runners)로 호출한다.
    # 러너 토큰은 secrets_dir/<game_runner_token_ref> 파일로만 읽는다(평문 미노출). game_ai_enabled
    # 플래그가 꺼져 있으면(기본) 엔드포인트가 404라 이 설정은 켤 때까지 무해하다.
    game_runner_url: str = "http://127.0.0.1:8789/v1/assistant/quiz"
    game_runner_token_ref: str = "game_runner_token"
    game_runner_timeout_seconds: int = 50

    # AI 도우미 심화(계획서 Phase 5) — 오늘 브리핑·스탠드업·주간 다이제스트의 **문장만**
    # 러너에 맡긴다. 숫자는 app/assistant/facts.py 가 로컬에서 결정적으로 만들고, 이 호출이
    # 실패해도 숫자는 그대로 나간다(문장만 빠진다). 퀴즈와 같은 러너·같은 관문
    # (OutboundClient allowlist="runners")을 쓴다 — 새 외부 호출 경로를 만들지 않는다.
    # assistant_narrative_enabled 플래그가 꺼져 있으면(기본) 호출 자체가 나가지 않는다.
    # 타임아웃이 퀴즈(50s)보다 짧은 이유: 이건 화면을 여는 길목이라 사람이 기다리고 있다.
    assistant_runner_url: str = "http://127.0.0.1:8789/v1/assistant/summarize"
    assistant_runner_token_ref: str = "assistant_runner_token"
    assistant_runner_timeout_seconds: int = 25

    # AI-16: 대화 삭제 시 러너의 미러(conversation_state)도 지운다 — 위와 같은 러너·같은
    # 토큰·같은 관문(runners allowlist)이라 새 secret이 필요 없다. 이건 화면을 여는 길목이
    # 아니라 삭제 버튼 하나의 뒤처리라 사람이 기다리는 정도가 훨씬 짧다 — 짧게 잡아 삭제
    # 자체가 러너 장애로 느려지지 않게 한다. 실패해도 삭제는 그대로 성공한다(위생 실패,
    # 데이터 무결성 문제 아님) — TTL 스윕(CONTEXT_MODE_TTL_SECONDS)이 그물을 겹쳐 준다.
    assistant_context_delete_url: str = "http://127.0.0.1:8789/v1/assistant/context/delete"
    assistant_context_delete_timeout_seconds: int = 5

    # 소스 스위치(§7.1.C). 저장소 배선을 바꾸는 재시작급 변경이라 DB 설정이 아니라 env 에 둔다.
    # 값: 'notion' | 'notion_cache' | 'native'. 'native'(자체 DB 정본)는 아직 구현체가 없어
    # 시작 시 거절된다 — 문만 열어 둔 상태다.
    #   ticket_source='notion' 은 **운영 킬 스위치**다: 로컬 미러를 아예 보지 않고 캐시 도입
    #   전과 똑같은 실시간 경로로 돌아간다. 미러가 이상하면 이 값 하나만 바꿔 재시작하면 된다.
    # ── LLM (9-5) ────────────────────────────────────────────────────────────
    #
    # `app/llm/provider.py::resolve_config` 는 이미 `Settings` 필드 → 환경변수 → 기본값
    # 순으로 읽도록 만들어져 있고, 그 docstring 이 "필드가 생기면 이 함수를 고치지 않아도
    # 그쪽이 이긴다" 고 적어 뒀다. 그 자리를 여기서 만든다.
    #
    # 🔴 기본값이 전부 **빈 값**인 것이 핵심이다. 비어 있으면 resolve_config 가 환경변수로
    # 떨어지므로, 이미 `LLM_*` 환경변수로 켜 둔 설치가 업그레이드하는 순간 꺼지지 않는다.
    # 관리 콘솔에서 저장하면 그 값이 여기로 얹히고(app/core/tenant_config.py::apply_overrides)
    # 그때부터 화면이 이긴다.
    #
    # llm_enabled 가 bool 이 아니라 문자열인 이유도 같다: bool 은 "안 정했다" 를 표현할 수
    # 없어서, 기본 False 가 곧바로 "끄기로 정했다" 로 읽힌다. 빈 문자열이 '안 정함' 이다.
    llm_enabled: str = ""
    llm_backend: str = ""
    llm_model: str = ""
    llm_executable: str = ""
    # None 이 '안 정함' 이다. 0 을 기본으로 두면 resolve_config 가 "설정값이 있다" 로 읽고
    # 환경변수를 건너뛴다(0 은 None 이 아니다) - 그러면 LLM_TIMEOUT_SECONDS 가 죽는다.
    llm_timeout_seconds: int | None = None
    # 동시 실행 슬롯 수. 소비자는 app/llm/service.py 의 슬롯 락이다.
    llm_max_concurrency: int = 1

    ticket_source: str = "notion_cache"
    # 문서는 이미 로컬 미러에서 읽으므로 notion / notion_cache 가 같은 구현체를 가리킨다.
    document_source: str = "notion"

    @property
    def allowed_email_domain_list(self) -> list[str]:
        return [d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"
