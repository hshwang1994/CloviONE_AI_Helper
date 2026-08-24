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

    # System of Record 는 PostgreSQL 이다(D-187). 기본값은 개발용 로컬 주소이고,
    # 운영은 systemd EnvironmentFile 이 덮어쓴다. SQLite 주소를 넣으면 앱이 뜨지
    # 않는다 — `app/core/db.py::normalize_database_url` 이 막는다.
    database_url: str = "postgresql://cloviradmin@127.0.0.1:5432/clovir"
    # `pg_dump`/`pg_restore`/`psql` 이 있는 디렉터리. 비우면 `PATH` 에서 찾는다.
    #
    # 비워 두면 안 되는 환경이 있다: Ubuntu 는 버전별 디렉터리에 둔다
    # (`/usr/lib/postgresql/16/bin`). `PATH` 의 `pg_dump` 는 더 낮은 버전일 수 있고,
    # **서버보다 낮은 `pg_dump` 는 실행을 거부한다** — 그러면 백업이 한 번도 성공한 적
    # 없는데 그 사실이 백업을 되돌리려는 날에야 드러난다.
    pg_bin_dir: str = ""

    # 자격 증명을 무엇이 검증하는가 (S5). 지금 값은 `local` 하나뿐이고, LDAP·OIDC 가
    # 들어오면 여기에 이름이 는다. **모르는 이름은 기동 시점이 아니라 첫 로그인에서
    # 오류가 된다** — 조용히 local 로 떨어뜨리면 「켰다고 믿는데 안 켜진」 상태가 된다
    # (`app/auth/providers.py::resolve_identity_provider`).
    auth_provider: str = "local"

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

    # Directory holding allowed-services.json / feature-flags.json
    # (spec §8: /etc/clovirassist in production, ./config in development).
    config_dir: Path = Path("config")
    secrets_dir: Path = Path("var/secrets")
    data_dir: Path = Path("var")

    # Optional path to the TLS cert for expiry monitoring on the dashboard
    # (production: /etc/clovirassist/tls/*.crt). None in dev/tests.
    tls_cert_path: str | None = None

    # ── 이관 도구가 쓰는 Notion 설정 ─────────────────────────────────────────
    #
    # **제품은 더 이상 Notion 을 부르지 않는다.** 티켓·문서·프로젝트의 정본은 이 서버의
    # 데이터베이스이고, Notion 을 읽고 쓰던 구현체는 전부 사라졌다. 그래서 여기 남은 값은
    # 세 개뿐이고, 셋의 소비자도 하나뿐이다 — 이관 CLI(`app/cli/migrate_cli.py`)다.
    #
    # 그 CLI 는 재설치나 두 번째 설치에서 옛 데이터를 한 번 읽어 오는 도구라 살아 있어야
    # 한다. 다만 그 호출은 런타임 허용 목록이 아니라 **이관 전용 허용 목록**을 지난다
    # (`allowlist="migration"`, app/migration/source_notion.py). 런타임 목록에는
    # api.notion.com 이 없다.
    #
    # 데이터베이스 id 는 여기에 없다. 이관 CLI 는 제목으로 찾거나 `--database role=id` 로
    # 받는다(`app/migration/source_notion.py::discover`). 설정에 두면 설치처마다 다른 값이
    # 소스에 박히는 문제가 예전 그대로 돌아온다.
    notion_api_base: str = "https://api.notion.com"
    notion_api_version: str = "2022-06-28"
    # 토큰 자체는 여기 없다. 이 값은 secrets_dir 안의 **파일 이름**일 뿐이고, 토큰은 그
    # 파일에서만 읽는다(§2 불변 규칙 3).
    notion_docs_token_ref: str = "notion_docs_token"

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
    # Phase 3 실측(2026-08-17, TEST SERVER)에서 직접 발견: 동시성 3에서 SQLite 쓰기
    # 경합("database is locked")이 실제로 발생했다 — 대부분은 기존 재시도/백오프로
    # 회복됐지만, 한 건은 claim_next의 최초 쓰기와 그 실패를 기록하려던 fail()의 쓰기가
    # **둘 다** 락에 걸려 잡이 `running` 상태로 멈춰 버렸다. `Worker`의 기본
    # `running_timeout_seconds`(repository.DEFAULT_RUNNING_TIMEOUT_SECONDS=3900,
    # 3600초짜리 schedule_run에 맞춘 값)를 대화형 레인이 그대로 물려받으면 이런 잡이
    # 최대 65분 동안 "처리 중"인 것처럼 멈춰 있다 — 채팅은 수십 초 안에 끝나야 정상인
    # 레인이라 그 격차가 훨씬 크게 느껴진다. 모델 응답 상한(180초) 기준 3회 재시도 여유를
    # 두고 훨씬 짧게 잡는다.
    worker_conversational_running_timeout_seconds: int = 840

    # 스케줄러 레인(S4 · D-225). **기본이 켜짐**이라는 점이 대화형 레인과 다르다 —
    # 스케줄러는 선택 기능이 아니라 제품의 상시 Component 이고, `clovirassist-scheduler.service`
    # 라는 1급 유닛을 갖는다(INSTALLATION.md §6).
    #
    # 왜 꺼도 되게 두는가: 되돌릴 스위치 없이 실행 위상을 바꾸지 않는다. 꺼면 스케줄러
    # 프로세스는 리스를 잡기 전에 정상 종료하고, 배치 워커가 예전처럼 스케줄러 tick 과
    # 좀비 스윕을 다시 등록한다. **같은 값이 양쪽을 반대로 가르므로 둘 다 도는 상태는
    # 만들어지지 않는다** — 값을 바꾼 뒤 두 유닛을 재시작하면 된다.
    #
    # 이중 발화 방어는 그 위에 한 겹 더 있다: `schedule_runs.idempotency_key`
    # (`{schedule_id}:{scheduled_at}`)가 UNIQUE 라 행을 넣은 쪽이 그 실행을 갖는다.
    worker_scheduler_lane_enabled: bool = True
    # 스케줄러 루프의 최소 간격. 스케줄의 최소 단위가 1분(cron)이라 1초면 충분히 촘촘하다.
    worker_scheduler_tick_seconds: float = 1.0

    # 주간 프로젝트 헬스 스냅샷 주기. **워커에서만** 돈다.
    #
    # '주간' 이력인데 왜 한 시간인가: 스냅샷은 (프로젝트, 주) 유일 키로 upsert 하므로 여러 번
    # 돌아도 그 주의 행은 한 줄이다. 정확히 주 1회로 잡으면 그 한 번이 배포, 재시작, 장애와
    # 겹쳤을 때 **그 주가 통째로 비고**, 몇 주 뒤 추세선에서 그 구멍은 '값이 나쁜 주' 와
    # 구별되지 않는다. 자주 확인하는 편이 싸고(이미 로컬 미러에 있는 행만 읽는다) 안전하다.
    # 회차마다 프로젝트 행의 `updated_at` 을 덮지 않는 것이 전제다
    # (app/projects/service.py::record_health_snapshot).
    project_health_snapshot_interval_seconds: int = 3600

    # 팀 공간 놀이 > AI 퀴즈 생성(§7-9)과 AI 도우미의 요약 문장(계획서 Phase 5)은 둘 다
    # **Model Gateway 를 지난다** — S11 이전에는 각자 러너 HTTP 를 직접 불렀고, 그래서
    # 주소·토큰·타임아웃 설정이 기능마다 세 벌이었다. 지금은 모델 설정이 한 곳
    # (`app/ai/gateway/registry.py`)이라 여기에 남길 값이 없다. 두 기능의 기능 플래그
    # (`game_ai_enabled` · `assistant_narrative_enabled`)는 그대로다.

    # 소스 스위치(§7.1.C)는 여기 있었다. 값이 셋('notion' · 'notion_cache' · 'native')이라
    # 뜻이 있었고, Cutover 를 되돌릴 수 있는 동안에는 되돌린 설치가 옛 값으로 떴다.
    # 지금은 구현체가 자체 DB 하나뿐이라 고를 것이 없다 — 배선은 코드가 정한다
    # (`app/core/source_registry.py`).

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

    # ── AI Platform (S9 · D-200~D-203) ───────────────────────────────────────
    #
    # `app/ai/gateway/registry.py::resolve_config` 가 `Settings` 필드 → 환경변수 →
    # 기본값 순으로 읽는다. `llm_*` 와 같은 규약이고, 이유도 같다 — 빈 값이 「안 정함」
    # 이라 이미 환경변수로 켜 둔 설치가 업그레이드에서 꺼지지 않는다.
    #
    # 🔴 기본이 **꺼짐**이다. AI 기능을 기본 ON 으로 두는 관례가 이 저장소에 없다.
    ai_enabled: str = ""
    # 임베딩 모델 파일이 사는 뿌리. 비우면 `data_dir/ai/models` 다. `storage_providers`
    # 와 **별개**다 — 모델은 사용자 데이터가 아니라 재생성 가능한 자산이고 백업 대상이
    # 아니다(D-203 · D-204).
    ai_model_root: str = ""
    # `app/ai/catalog.py` 가 아는 id 중 하나. 모르는 이름이면 임베딩이 「설정 안 됨」이
    # 된다 — 조용히 기본 모델로 떨어뜨리지 않는다(그러면 벡터가 바꾼 줄 알았던 모델의
    # 것이 아니다).
    ai_embed_model: str = ""
    ai_embed_batch_size: int = 0
    # ONNX Runtime intra-op 스레드. 0 이면 런타임 기본값(코어 수)이다.
    ai_embed_threads: int = 0

    # 색인 레인(D-203). 배치·대화형과 분리하는 이유는 하나다 — **임베딩이 배치 틱을
    # 굶기지 않게.** 기본 켬이고, 그래서 `clovirassist-index.service` 는 재부팅 뒤
    # 떠 있어야 하는 유닛이다(`app/core/product.py::ALWAYS_ACTIVE_UNITS`).
    worker_index_lane_enabled: bool = True
    # 색인 파이프라인이 한 번의 tick 에서 처리하는 대상 수. 크게 잡으면 한 tick 이
    # 길어져 종료 신호에 늦게 답한다.
    index_batch_documents: int = 20

    @property
    def allowed_email_domain_list(self) -> list[str]:
        return [d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"
