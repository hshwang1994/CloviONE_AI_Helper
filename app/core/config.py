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
    allowed_email_domains: str = "goodmit.co.kr"

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
    notion_tasks_database_id: str = "262c5c5a568481fa9697ee5691cb558d"
    notion_report_token_ref: str = "notion_report_token"
    # 티켓 로컬 미러 동기화 주기(PLAN §A). 문서(600s)보다 자주 도는 이유는 티켓이 회의 중에도
    # 바뀌기 때문이다. 생성/편집은 캐시를 즉시 패치하므로 이 주기는 '다른 사람이 노션에서 직접
    # 고친 것'이 반영되는 지연일 뿐이다.
    notion_tickets_sync_interval_seconds: int = 180

    # 팀 공간 > 문서(§17): Notion "문서" 데이터베이스를 읽어 로컬 캐시로 미러링한다(장애 격리:
    # Notion이 죽어도 마지막 정상 동기화 데이터로 목록을 보여준다). 토큰은 secrets_dir 파일
    # 참조로만 읽고(평문 미노출), 없으면 화면은 '연동 필요'를 보여준다. tasks 토큰과 같은 값이어도
    # 무방하다(별도 ref로 두어 문서 접근만 따로 회수/교체 가능).
    notion_documents_database_id: str = "55efc3c0b58341a5b8d17f31fc2b152c"
    notion_docs_token_ref: str = "notion_docs_token"
    notion_docs_sync_interval_seconds: int = 600

    # 통합 검색 인덱스 재구축 주기(PLAN Phase 5). **워커 틱에서만** 돈다 — 채팅 전송·폴링
    # 같은 뜨거운 경로에는 훅을 걸지 않는다(app/search/indexer.py docstring).
    # 티켓 미러(180s)보다 조금 느슨하게 잡는다: 검색 결과가 한 틱 늦는 것은 사람이 못 느끼고,
    # 인덱싱은 네 유형을 전부 다시 읽으므로 미러 동기화보다 비싸다.
    search_index_interval_seconds: int = 300

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

    # 소스 스위치(§7.1.C). 저장소 배선을 바꾸는 재시작급 변경이라 DB 설정이 아니라 env 에 둔다.
    # 값: 'notion' | 'notion_cache' | 'native'. 'native'(자체 DB 정본)는 아직 구현체가 없어
    # 시작 시 거절된다 — 문만 열어 둔 상태다.
    #   ticket_source='notion' 은 **운영 킬 스위치**다: 로컬 미러를 아예 보지 않고 캐시 도입
    #   전과 똑같은 실시간 경로로 돌아간다. 미러가 이상하면 이 값 하나만 바꿔 재시작하면 된다.
    ticket_source: str = "notion_cache"
    # 문서는 이미 로컬 미러에서 읽으므로 notion / notion_cache 가 같은 구현체를 가리킨다.
    document_source: str = "notion"

    @property
    def allowed_email_domain_list(self) -> list[str]:
        return [d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"
