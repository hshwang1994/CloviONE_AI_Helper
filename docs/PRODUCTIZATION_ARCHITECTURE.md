# 제품화 아키텍처 계획 (2026-07-29)

> 목표: 지금의 사내 단일 도구를, 여러 부서 최대 약 1000명이 쓰는(향후 제품화 가능) 플랫폼으로.
> 이건 기능 백로그와 별개의 **큰 아키텍처 프로그램**이라 자체 스펙으로 다룬다. 착수 전 사용자와 핵심
> 결정 1개를 확정한다(아래 §0). 최우선 기준은 늘 같다: 기존 정상 동작 무손상, 단계적, 회귀로 증명.
> 관련: `docs/NEXT_SESSION_PLAN.md`(근시일 A~F), `docs/IDEAS_BACKLOG.md`(제품 전체 아이디어),
> `docs/EXTENSION_GUIDE.md`(Postgres 전환 기준). 메모리 [[clovirone-team-space]] [[clovirone-web-assistant]].

## §0. 착수 전 핵심 결정 — ✅ 확정 (2026-07-29)
**결정: (a) 한 회사 여러 부서 + 관리자 티어로 시작. 데이터 모델에 최상위 `org_id`(널 허용)를
처음부터 심어 향후 (b) 멀티테넌트로 재작업 없이 확장. 완전 멀티테넌시는 실제 두 번째 회사가
생기기 전엔 만들지 않는다(YAGNI).** 아래는 이 결정의 배경.

**단일 회사(여러 부서)인가, 진짜 다중 회사(멀티테넌트 SaaS)인가?**
- (a) **한 회사, 여러 부서**: 필요한 건 "부서 계층 + 범위 제한 관리자 티어". 훨씬 단순. 지금 요청("부서
  관리자는 본인 부서 리포트만")은 여기로 충분히 커버된다.
- (b) **여러 회사에 파는 제품**: "조직(=테넌트)" 단위 완전 데이터 격리 + 테넌트별 설정/브랜딩/Notion.
  훨씬 큼(멀티테넌시).
- **내 권장**: 지금은 **(a) 부서 계층 + 관리자 티어**를 만들되, 데이터 모델에 최상위 `org_id`(널 허용)를
  처음부터 넣어 **나중에 (b)로 재작업 없이 확장** 가능하게 설계. 실제 두 번째 회사가 생기기 전엔
  완전 멀티테넌시를 만들지 않는다(YAGNI). 사용자 확정 필요.

## §1. RBAC: 범위 제한 관리자 티어 (사용자 아이디어 핵심)
현재: 평면 5역할(user/operator/auditor/admin/system_admin), 평면 department 필드.
목표 티어:
- **포탈 관리자(portal admin)**: 전역. 조직·부서까지 구분해 전부 열람/관리.
- **조직 관리자(org admin)**: 자기 조직 범위. 조직 내 부서별로 구분해 열람.
- **부서 관리자(dept admin)**: 자기 부서 범위만.
설계:
- 역할을 **(역할, 범위)** 튜플로: 범위 = org/dept. 권한 검사에 범위 포함("이 사용자가 부서 X 리포트를
  볼 수 있나"). 서버측 강제(불변 §5, 프런트 신뢰 금지).
- 리포트 예: 포탈=전체, 조직관리자=자기 조직(부서 breakdown), 부서관리자=자기 부서만.
- 마이그레이션: 현재 admin→포탈 관리자로 매핑, 조직/부서 관리자는 신규 역할로 추가. 기존 사용자 무손상.
- 영향 범위: 사용자/티켓/리포트/문서/게시판/채팅 등 **범위가 있는 모든 조회에 row-level scoping**.
  UI만이 아니라 쿼리에서 걸어야 IDOR/데이터 유출 방지.

## §2. 데이터 모델: 조직/부서 계층 + 스코핑
- **부서 계층**: department 를 트리로(parent_id). 조직관리자가 "부서별로 구분"하려면 부서가 1급 엔티티.
- **조직 엔티티**: (b) 대비 `organizations` 테이블 + 모든 스코프 리소스에 `org_id`(초기엔 단일 org 시드).
- **스코프 전파**: 티켓/문서/리포트/게시판/채팅에 dept/org 스코프 부여. 신규 마이그레이션 다수.
- 주의: Notion 소스가 부서 개념을 어떻게 담는지 매핑 필요(사람→부서는 이미 있음; 티켓→부서는 담당자
  부서로 유도 가능).

## §3. 스케일: DB와 동시성 (1000명)
- 현재: SQLite(WAL) + sync FastAPI. 채팅/놀이 폴링(1.5~3초)이 1000명이면 읽기 QPS가 높고, SQLite는
  단일 writer라 쓰기가 직렬화된다 → 병목 위험.
- **권장: Postgres 전환**(EXTENSION_GUIDE.md에 기준 있음). SQLAlchemy 추상화라 코드 영향 작음(sync
  psycopg), Alembic 그대로. 세션은 이미 DB의 opaque 토큰이라 다중 프로세스 OK.
- **수평 확장**: 무상태 앱 프로세스 여러 개 + 공유 Postgres + nginx 로드밸런싱. 워커/스케줄러는
  싱글턴 보장(리더 선출 또는 단일 워커 인스턴스).
- **sync 불변(§1)과 스케일**: sync는 다중 프로세스 + 커넥션 풀로 확장 가능(async 회피가 목적이지
  확장 금지가 아님). uvicorn/gunicorn 워커 수 튜닝. 아주 높은 폴링 부하는 폴링 간격↑/ETag 304, 최종적
  으로 격리된 async 푸시(SSE) 서비스로(원래 계획대로 메인 앱은 sync 유지).
- **결정 포인트**: 언제 Postgres로 갈지 — 제품화/1000명 목표면 사실상 전제 조건.

## §4. Notion 의존 탈피 = 자체 DB (티켓/문서). 지금 싸게 대비할 것
- 리스크: Notion API rate limit(대략 초당 3요청)이 1000명 규모 쓰기에서 병목. 제품화(여러 회사 판매)
  하면 "모든 고객이 Notion을 쓴다"는 가정 자체가 성립 안 함. 즉 **언젠가 티켓/문서의 진짜 소스를
  자체 DB로 옮기고 Notion은 선택적 연동으로 강등(또는 제거)**해야 할 수 있다.
- **핵심 통찰: 다음 주에 만드는 티켓 캐시(NEXT_SESSION_PLAN §A)를 "읽기 캐시"가 아니라 "미래의 자체
  소스가 될 수 있는 완전한 표"로 설계하면, 나중 전환이 큰 마이그레이션이 아니라 설정 스위치가 된다.**
  전면 네이티브화는 그때 별도로 하되, 아래 4가지는 리팩토링 때 미리(저비용) 심는다.

### 지금(다음 주 리팩토링) 심어둘 4가지 — 저비용, 미래 전환 비용 급감
1. **자체 식별자(ID) 정책**: ticket_cache/문서 캐시에 **자체 UUID `id`(PK) + `notion_page_id`(널 허용)**.
   내부 참조(댓글 §E, 휴지통, 채팅↔티켓 링크, 알림 related)는 **전부 자체 id를 쓰고 notion_page_id를
   직접 참조하지 않는다.** (이게 안 되면 나중에 Notion 뗄 때 모든 참조가 깨진다. 가장 중요.)
2. **저장소 추상화(provider 인터페이스)**: 지금 `app/tickets/service.py`가 `notion_source.*`를 직접
   부른다 → 이 결합을 `TicketRepository` 인터페이스 뒤로 옮긴다. 구현체는 지금 `NotionTicketRepository`
   하나, 나중에 `NativeTicketRepository`(Postgres/SQLite) 추가. 비즈니스 로직(sprint/reports/service)은
   인터페이스에만 의존. 설정 `ticket_source`(notion | native | notion+cache)로 소스를 스위치.
   A단계에서 읽기 경로를 어차피 손대므로 이때 함께 하면 추가 비용이 작다. 문서(team_docs)도 동형으로.
3. **본문 정본 포맷**: 티켓/문서 본문(§E 본문 수정)은 **마크다운을 정본으로 자체 저장**하고, Notion
   블록은 어댑터로 양방향 변환(기존 `app/core/notion_blocks.py` 재사용). 그러면 Notion 없이도 본문이
   온전하다.
4. **동기화 방향을 뺄 수 있게**: 지금은 Notion → 로컬 one-way pull. 이후 로컬 → Notion push 또는 완전
   제거가 가능하도록 sync를 방향 교체 가능한 형태로. 양방향 시 충돌 정책(updated_at 최신 우선 등)은 그때.

### 리팩토링 때 필요할 수 있는 추가 컴포넌트/변경 (사용자 질문에 대한 답)
- 신규 모듈/파일: `app/tickets/repository_notion.py`(현행 래핑) + 훗날 `repository_native.py`, 그리고
  provider 선택기. 문서도 `app/team_docs/repository_*`.
- 신규 설정: `ticket_source`, `document_source`(registry에).
- 스키마 확장: 캐시 표에 자체 UUID PK + notion_page_id 널 + 완전한 필드(+본문 마크다운). 마이그레이션.
- 첨부/파일: Notion 호스팅 파일을 쓰면 네이티브 전환 시 로컬 저장(app/core/uploads.py)으로 이관 필요.
- 프런트: 이미 우리 API(`/api/tickets/*`)만 호출하고 Notion 형태를 모른다 → **프런트는 그대로 두면 됨**
  (백엔드 추상화만 하면 UI 재설계와 독립적으로 소스 교체 가능). 이 점이 유리하다.
- 주의(YAGNI): 지금 NativeTicketRepository를 구현하지는 않는다. 인터페이스 + 자체 id + 정본 본문만
  심어 "문을 열어둔다". 실제 네이티브 전환은 §6 단계에서 별도 결정.

## §5. 제품 운영 준비 (제품화 시)
- 조직/부서별 사용량·쿼터·(상업화 시)과금 훅.
- 프로비저닝: 조직 생성, 관리자 초대, 온보딩.
- 조직별 백업/복구, 데이터 내보내기.
- 관측성: 메트릭/트레이싱/에러 추적을 스케일에 맞게.
- 조직별 브랜딩/테마(멀티테넌트 시).

## §6. 단계적 로드맵 (권장)
1. **부서 계층 + 관리자 티어 + row-level scoping**(§1·§2). 한 회사에서 즉시 가치, 증분. org_id는 널로
   심어 미래 대비.
2. **성능 근본안 + 리포트 스코핑**(NEXT_SESSION_PLAN §A와 결합): 부서/조직 관리자 리포트가 캐시 위에서 빠르게.
3. **Postgres 전환**(§3): 1000명/제품화 신호가 오면. 코드 영향 작지만 인프라·배포 변경.
4. **네이티브 티켓 저장 + Notion 선택 동기화**(§4): Notion 병목이 실제로 문제될 때.
5. **완전 멀티테넌시**(§0-b, §5): 진짜 다른 회사에 팔 때만.

## §7. 통합 제품화 설계 (6관점 통합, 2026-07-30)

> 이 절은 §1~§6의 방향을 6개 관점(데이터 모델, RBAC 스코핑, 저장소 추상화, 스케일/Postgres, 구조/운영, 이행 순서)의 실제 코드 검증 결과로 하나로 합친 실행 설계다. 앞 절과 충돌하는 부분은 이 절이 우선한다(정리 근거는 §7.5). 검증 기준(alembic head=0021, app/tickets에 models.py 없음, service.py가 notion_source/notion_write 직접 import, AppSetting PK가 key 단일, config.py에 소스 스위치 없음, TrashItem.notion_page_id 참조, 설정 split-brain)은 코드로 확인함.

### §7.0 큰 원칙 (한 문장)

**소스 DB 전환(Notion -> 자체 DB)은 지금 구현하지 않는다. 인터페이스, 자체 UUID 식별자, 정본 본문 컬럼, 소스 스위치 설정만 심어 "문만 연다"(YAGNI). 그 외 전체 구조(조직/부서 계층, 관리자 티어, 행 수준 스코핑, 모듈 경계, 설정, 관측성, 스케일 seam)는 처음부터 제품화 가능하게 스키마와 배관을 심되, 강제 로직과 실제 격리는 실제 필요가 올 때(둘째 회사, 1000명 신호) 켠다.** 최우선 기준은 불변: 기존 정상 동작 무손상, 단계적, 회귀로 증명.

이 원칙의 세 갈래:
1. **문만 연다(defer 대상)**: 네이티브 소스 구현, 완전 멀티테넌시 격리, org_id NOT NULL 승격, Postgres 전환, 양방향 sync.
2. **처음부터 심는다(build now)**: organizations 테이블 + org_id 컬럼, 부서 트리, 관리자 스코프 컬럼, ticket_cache 완전판, 저장소 인터페이스, scope/authz 배관, 스케일 seam, 관측성 표.
3. **무손상 게이트**: 신규 테이블/컬럼은 nullable + DEFAULT_ORG_ID 백필, 소비자가 없는 동안 응답 형태 불변, 각 단계 pytest 전체 green + static_checks OK + 골든 회귀로 증명.

### §7.1 영역별 설계

#### A. 데이터 모델 / 멀티테넌시 준비

- **organizations 1급 엔티티**: 자체 UUID id(PK), slug(unique), name, status, settings_json(nullable), created_at/updated_at. 고정 상수 `DEFAULT_ORG_ID`(app/org/constants.py 신규)로 단일 org 1행 시드. 기존 고정 id 관례(GLOBAL_ROOM_ID, DocumentSyncState 싱글턴) 재사용.
- **OrgScopedMixin**(app/core/models_base.py): org_id String(36) nullable FK(organizations.id) + index. 신규 테이블은 믹스인으로, 기존 핵심 스코프 테이블(departments, job_titles, users, board_posts, chat_rooms, document_cache, notifications)에는 마이그레이션으로 org_id 추가 후 DEFAULT_ORG_ID 백필. 컬럼은 nullable 유지(NOT NULL churn 회피, "문만 연다"와 일치).
- **부서 트리**: Department에 parent_id(self-FK, nullable, ondelete=SET NULL) + org_id. 이름 유일성은 (org_id, name) 복합 unique로 이행(현행 전역 name unique는 단일 org 상태에서 의미가 동일하므로 복합으로 대체). SQLite는 UNIQUE에서 NULL을 서로 다르게 취급하므로 org_id는 반드시 DEFAULT_ORG_ID 실값으로 백필해 복합 unique가 실제로 동작하게 한다.
- **자체 UUID 단일 식별 전략 확정**: 내부 참조(댓글, 휴지통, 즐겨찾기/최근열람, 알림 related, 채팅-티켓 링크)는 전부 자체 id를 쓴다. notion_page_id는 nullable 보조 외부키로만 남긴다(소스가 Notion일 때만 채워짐). DocumentCache가 이미 이 형태이므로 ticket_cache도 동형으로 만들고, 위성 테이블 참조를 자체 id로 이행한다(레거시 notion_page_id 참조 컬럼은 한 릴리스 병행 유지, drop은 defer).
- **ticket_cache = 미래 자체 소스가 될 완전한 표**(얇은 읽기 캐시 금지): id(UUID PK), notion_page_id(nullable, unique), org_id(FK 백필), scope_dept_id(nullable FK departments, 담당자 부서로 유도), title, status, priority, difficulty, est_wd, act_wd, due_date, project_id, project_names, assignee_notion_ids(원본 Notion user id를 NAMES_SEP 0x1f sentinel-wrapped로 저장, 앱 user 해석은 읽기 시점에), body_markdown(본문 정본, nullable), source('notion'|'native', 기본 'notion'), notion_created_time, notion_last_edited, synced_at, created_at/updated_at. ticket_sync_state 싱글턴(고정 id, last_success_at/last_error/truncated).
- **본문 정본은 마크다운 자체 저장**: ticket_cache.body_markdown, document_cache.body_markdown 신규. app/core/notion_blocks.py에 역방향 blocks_to_markdown 어댑터 추가(현행 markdown_to_blocks 단방향 write를 양방향으로). 읽기는 정본 우선, 없으면 실시간 블록 폴백.

#### B. RBAC 스코핑 (역할 x 범위 직교)

- **역할과 범위를 직교로 분리**: users.role(capability tier, 평면 5역할)은 그대로 두어 require_roles가 무변으로 동작한다. 범위는 별도 컬럼으로 붙인다. 3티어 관리자는 신규 역할 문자열을 만들지 않고 스코프 조합으로 표현한다.
- **users 스코프 컬럼**(4컬럼, 전부 nullable): org_id(소속 org, 멤버십), admin_scope('portal'|'org'|'dept'|NULL, 관리자 티어), scope_org_id(org 관리자 앵커), scope_dept_id(부서 관리자 앵커). 백필: 기존 admin/system_admin -> admin_scope='portal'(포탈 관리자, 권한 상실도 전역 승격도 없음), org_id -> DEFAULT_ORG_ID.
- **Scope/Principal 추상화**(app/core/scope.py 신규): frozen dataclass Scope(type: 'global'|'org'|'dept'|'self', org_id, dept_id)와 Principal(user, role, scope). scope는 서버측 User 행에서만 도출(불변 §5, 프런트 신뢰 금지). get_principal(auth) 디펜던시가 request.state.principal로 싣는다. admin_scope='portal'이 Scope type 'global'로 매핑된다.
- **행 수준 스코핑은 UI가 아니라 쿼리에서 강제**: scope_filter(stmt, model, principal) 헬퍼가 범위에 따라 .where를 덧붙이고, type=='global'이면 no-op(기존 관리자 무영향). 범위 밖 단건 접근은 존재 노출 방지를 위해 403이 아니라 404로 응답. visible_dept_ids 헬퍼로 가시 부서 계산.
- **ensure_can_manage_target 확장**: 기존 system_admin 보호 + 부서 관리자는 자기 부서 사용자만, 조직 관리자는 자기 조직 안에서만. Principal 오버로드를 추가하되 구 actor_role 시그니처를 계속 받아 점진 이행(서비스/라우터/CLI 여러 곳 호출부 무손상). global 관리자는 이전과 완전히 동일.
- **중앙 authz 레지스트리**(app/core/authz.py 신규): documents/runners/workflows/settings/prompts/templates/integrations/org 라우터마다 재정의된 READ_ROLES/WRITE_ROLES/OPS_ROLES를 명명된 capability 집합 한 곳으로 통합(순수 리팩토링, 동작 보존).
- **리소스별 스코프 정책**: 리포트/티켓은 담당자 부서 기준 dept 스코프(ticket_cache.scope_dept_id 유도), 사용자 관리는 dept/org, 게시판/채팅은 org(전사 소셜, dept 강제는 defer). 부서 미상(unmapped) 티켓은 포탈 전용 버킷으로 몰아 누락/유출 방지. auditor는 당분간 global 읽기 유지.
- **지금 강제할 두 조회**: /api/admin/users list와 /api/admin/reports/dev-monthly에 scope_filter 적용. global이면 기존과 동일 반환, 신규 dept 관리자는 자기 부서만. 나머지 조회는 컬럼/배관만 심고 강제는 제품 요구 시.

#### C. 저장소 / 소스 추상화 (Notion 탈피 대비)

- **인터페이스는 feature-local, 도메인 용어로만**: app/tickets/repository.py(TicketRepository Protocol + TicketDTO frozen), app/team_docs/repository_iface.py(DocumentRepository Protocol). Notion 속성명(PROP_STATUS='진행상태' 등)과 페이지네이션은 구현체 내부에만 가둔다. DTO는 자체 id와 notion_page_id를 둘 다 담되, 응답에는 절대 raw Notion user id를 넣지 않는다(§12.3 IDOR 방어, 해석은 서비스에서만).
- **구현체는 지금 Notion 하나**: NotionTicketRepository(app/tickets/repository_notion.py, ticket_cache를 읽고 미스/빈 캐시면 Notion 라이브 폴백), NotionDocumentRepository(app/team_docs/repository_notion.py, 기존 캐시 repository.py + notion_docs + sync 래핑). NativeTicketRepository/NativeDocumentRepository는 스텁만(defer).
- **단일 소스 선택기**(app/core/source_registry.py 신규): 설정 ticket_source/document_source를 읽어 repo를 생성하고 app.state.repositories로 노출. service/sprints/reports는 raw outbound+settings 대신 repo에 의존. (별도 provider.py 선택기는 두지 않는다. 선택 로직을 source_registry 한 곳에 모아 이중 선택기를 피한다.)
- **동기화 방향 교체 가능**: 현행 Notion -> 로컬 one-way pull을 sync 모듈로 격리(app/tickets/sync.py, team_docs/sync.py 동형). source=native면 pull은 no-op. push/충돌정책(updated_at 최신 우선)은 인터페이스 자리만 연다(defer). 모든 sync는 team_docs 동형 장애 격리: 예외를 밖으로 안 던지고 sync_state에만 error 기록, 마지막 정상 캐시 유지, truncated면 prune 생략, staleness를 API로 노출.
- **경계 정적검사**: notion_source/notion_write/notion_docs를 import하는 곳은 *_notion.py 구현체와 sync 모듈뿐이라는 규칙을 scripts/static_checks.sh에 추가(httpx 단일 관문 검사와 동형).
- **응답 계약 동결**: 프런트가 우리 API dict 키를 기대하므로, 리팩토링 전에 /api/tickets/*, /api/team-docs/*, /api/sprint, /api/admin/reports 응답을 골든 회귀(바이트 동일)로 고정한 뒤 이관한다.

#### D. 스케일 / Postgres 경로 (최대 1000명, sync 불변 유지)

- **sync + 단일 writer 모델 유지**: 읽기는 무상태 uvicorn 워커/프로세스 다중화로 하나의 DB를 공유해 확장한다. 세션이 이미 opaque DB 토큰이라 N개 프로세스가 새 상태 없이 동작한다. async 회피는 확장 금지가 아니라 결정론 유지가 목적임을 명확히 한다(불변 §1).
- **DATABASE_URL 단일 스왑 포인트**: make_engine(app/core/db.py)을 Settings의 db_pool_size/db_max_overflow/db_pool_recycle로 파라미터화하고 dialect_name(engine) 헬퍼 추가. SQLite 기본값은 그대로 두어 기존 테스트 green 유지.
- **claim_next 다이얼렉트 seam**(app/jobs/repository.py): SQLite 경로는 바이트 단위 그대로, engine.dialect.name=='postgresql' 분기에서 네이티브 datetime 바인딩 + FOR UPDATE SKIP LOCKED. 회귀 테스트로 못박기. (현행 now.strftime 문자열 비교 + SQLite RETURNING 서브쿼리는 그대로는 이식 불가.)
- **폴링 부하 1순위 레버**: 핫 폴링 3개(team_chat state, games state, notifications)에 ETag/If-None-Match 304(app/core/poll_conditional.py 신규). since==현재 seq면 본문 없이 304로 끝나 JSON 생성/직렬화/쿼리 절약. 결정적으로 room_messages GET이 매 폴링에서 유발하는 touch_presence 쓰기를 GET 핫 경로에서 분리하거나 스로틀을 presence_write_interval_seconds(기본 30초)로 올린다(현재 2초). 이게 1000명에서 SQLite 단일 writer 직렬화의 최대 병목.
- **레이트리미터 store 인터페이스화**(app/core/ratelimit_store.py 신규): RateLimitStore 프로토콜 + InMemoryRateLimitStore(현행 유지). 웹 워커 >1로 올리면 in-memory 리미터가 실효 한도 x N으로 조용히 약화되므로 공유 store가 필요함을 문서화(SqlRateLimitStore 구현은 defer). 계정 무차별 방어는 이미 DB 기반(failed_login_count/locked_until)이라 프로세스 간 안전.
- **워커 싱글턴 가드**(app/core/worker_lock.py 신규): acquire_singleton_lock()(SQLite lock 행/파일, Postgres pg_advisory_lock). 둘째 워커가 뜨면 기동 거부. 잡 claim은 이미 경합 안전이나 비멱등 tick(스케줄러/retention/docs-sync/runner-health)을 보호.
- **Postgres 경로(defer)**: sync psycopg(postgresql+psycopg://), Alembic 그대로, pgbouncer(transaction pooling), pool_recycle 필수(pgbouncer 뒤 장수명 커넥션 stale 방지), rowid 정렬은 명시적 단조 컬럼으로 대체. naive UTC 저장은 그대로 호환. EXTENSION_GUIDE §7 신호(락 경합 상시화, 웹 다중 노드, 백업 한계)가 올 때만.
- **async 푸시(defer)**: SSE/WebSocket은 ETag+간격 튜닝으로 부족할 때만, 같은 DB/seq를 읽는 별도 격리 프로세스(async 허용)로. 메인 앱은 sync 불변.

#### E. 구조 / 설정 / 운영 관측성

- **모듈 경계 불변**: 신규 기능은 feature-per-dir(router/service/repository/schemas/models, 200~400줄, 800 최대). cross-cutting 관심사(org/scope/authz/metrics)는 app/core 공용 또는 전용 최상위 모듈로 분리해 feature 모듈이 서로 결합하지 않게 한다. 신규 모델은 models_registry.py 임포트 한 줄, 신규 라우터는 main.py include 한 줄(기존 패턴 그대로).
- **설정 split-brain 정리(build now)**: maintenance_mode/document_automation_enabled가 registry와 config/feature-flags.json 양쪽에 있는 문제를 registry 단일 정본으로 확정한다. feature-flags.json 값을 registry의 feature.* SettingSpec으로 흡수하고 load_feature_flags를 registry+cache resolver로 위임(파일은 폴백 유지). 주의: 정적 자산 캐시 버스팅 교훈과 동형으로, write마다 reload를 반드시 보장해 "바꿔도 안 바뀐다"를 막는다.
- **설정 스코프 일반화(defer)**: AppSetting을 (scope_type, scope_id, key) 복합 PK로 확장하는 것은 미룬다(per-org 설정 = 완전 멀티테넌시 = YAGNI, 게다가 config_versions.object_id 규약 변경이 기존 rollback 이력을 끊을 위험). 지금은 resolve_setting() 간접 seam만 도입해 나중에 스코프를 붙여도 호출부를 안 건드리게 한다.
- **관측성 2층(build now, 저위험 additive)**: (a) usage_events(append-only: id, org_id, actor_id, kind, count, at) + sync_status(source, last_ok_at, last_error, lag_seconds, updated_at) 테이블. (b) app/core/metrics.py의 record_usage_event 헬퍼를 저빈도 지점(login, ai quiz, document create)에만 삽입하고 chat send/폴링 핫 경로에는 넣지 않는다(SQLite 단일 writer 쓰기 경합 회피, 필요 시 배치/샘플링). (c) GET /metrics OpenMetrics 텍스트(신규 의존성 없이 dashboard 숫자 재노출, operator+ 또는 nginx 127.0.0.1 제한). sync_status는 worker의 docs_sync_tick/runner_health_tick/notion_mapping_sync/tickets_sync에서 기록. 대시보드의 즉석 집계 -> 롤업 재배선은 defer.
- **프로비저닝(defer)**: org 생성/관리자 초대/온보딩 상태 머신은 실제 둘째 회사가 없으므로 전부 미룬다. 지금 필요한 건 organizations 테이블 + DEFAULT_ORG_ID 시드 하나뿐. 조직별 논리 export(NDJSON), 쿼터/과금 훅, 브랜딩/테마 오버레이도 defer.
- **불변 준수**: 관측/프로비저닝/메트릭 어떤 것도 async/aiosqlite 도입 금지, 외부 관측 push는 OutboundClient만. 새 백그라운드 훅은 worker tick 결정론(FakeClock)을 깨지 않게.

### §7.2 지금 심을 것(다음 주) vs 이후로 미룰 것

| 영역 | 다음 주에 지금 심을 것 (build now, 무손상) | 이후로 미룰 것 (defer, 문만 열어둠) |
|---|---|---|
| 조직/테넌시 | organizations 테이블 + DEFAULT_ORG_ID 시드, 핵심 테이블에 org_id nullable + 백필 | org_id NOT NULL 승격, (org_id, 키) 복합 unique 전면 강제, 완전 멀티테넌시 격리, 테넌트별 Notion 토큰/secret_ref, 브랜딩/테마 |
| 부서 | Department.parent_id(self-FK) + org_id, (org_id, name) 복합 unique | parent_id 재귀 롤업 스코프 순회, 다단계 부서 집계 UI |
| RBAC | users.admin_scope/scope_org_id/scope_dept_id + org_id, admin/system_admin -> portal 백필, app/core/scope.py, app/core/authz.py 중앙화, list_users + dev-monthly 스코프 강제 | board/chat/documents dept 스코프 실제 강제, auditor dept/org 세분화, admin_grants 테이블 |
| 저장소/소스 | TicketRepository/DocumentRepository 인터페이스 + Notion 구현 + source_registry + ticket_source/document_source 설정(기본 notion), 경계 정적검사, 골든 회귀 | NativeTicketRepository/NativeDocumentRepository 실제 구현, source=native 컷오버, 양방향 sync + 충돌정책, 조직별 소스 설정 |
| 티켓 캐시 | ticket_cache 완전판(자체 UUID PK + notion_page_id nullable + org_id/scope_dept_id + body_markdown + source) + ticket_sync_state + pull sync + write-through | ticket_comments(E단계), body_markdown 실제 백필, 첨부 로컬 이관 |
| 본문 정본 | ticket_cache/document_cache.body_markdown 컬럼 + blocks_to_markdown 역어댑터 + 신규 create 시 markdown 저장 | 기존 Notion 본문 대량 백필 |
| 자체 id 참조 | favorites/recent에 doc_id, trash_items에 ticket_id/doc_id 추가 + notion_page_id 매칭 백필(미매칭 NULL + 로그) | 레거시 notion_page_id 참조 컬럼 drop |
| 스케일 | make_engine 풀 파라미터 + dialect_name, claim_next 다이얼렉트 분기, ETag/304, presence 스로틀(30s), RateLimitStore 인터페이스, worker 싱글턴 가드, systemd WEB_WORKERS 변수화 | Postgres+pgbouncer 프로비저닝/전환, 공유 rate-limit store 구현, WEB_WORKERS>1/멀티 노드, SSE 푸시 서비스 |
| 설정 | feature-flags -> registry 흡수(split-brain 제거), resolve_setting seam | AppSetting (scope_type, scope_id, key) 복합 PK, per-org 오버레이 |
| 관측성 | usage_events + sync_status 테이블, record_usage_event(저빈도 지점), /metrics(operator+), sync_status 훅 | usage_events 롤업 배치 + 대시보드 재배선, 외부 APM/OTel 연동 |
| 운영 | (없음, 아래 defer) | 프로비저닝(org 생성/초대/온보딩), 조직별 export(NDJSON)/백업, 쿼터/과금 |

### §7.3 무손상 단계적 이행 순서 (canonical alembic 0022+)

여섯 관점이 각자 제시한 0022+ 번호를 하나의 정본 체인으로 통합한다. organizations를 맨 앞에 두는 이유는 ticket_cache.org_id FK가 organizations 테이블을 필요로 하기 때문이다. 모든 마이그레이션의 timestamp는 반드시 Python datetime으로 생성해 파라미터 바인딩한다(불변 §8, SQLite STRFTIME %S.%f 이중초 버그 회피). 기존 테이블 alter는 0015가 검증한 batch_alter_table 패턴 + upgrade/downgrade 라운드트립 회귀로 못박는다.

- **0단계(무코드)**: /api/tickets/mine|unassigned|team, /api/sprint, /api/team-docs/*, /api/admin/reports 응답을 tests/regression 골든으로 동결. 페이크 Notion transport 사용.
- **0022 organizations**: 테이블 생성 + DEFAULT_ORG_ID 1행 시드. 기존 테이블 무접촉, 아무 코드도 org_id를 읽지 않음 -> 기존 동작 100% 동일. 게이트: 전체 pytest green.
- **0023 ticket_cache**: ticket_cache 완전판 + ticket_sync_state 싱글턴(신규 테이블만). models_registry.py에 `from app.tickets import models` 한 줄. app/tickets/sync.py + worker tickets_sync_tick(즉시+notion_tickets_sync_interval_seconds 주기, try/except 격리, truncated prune 가드) 등록해 캐시만 채운다. 읽기 경로는 아직 Notion 그대로 -> 동작 무변경. sync_state.last_success_at로 채워짐 확인.
- **코드 이관(0023과 같은 배포 또는 직후, 마이그레이션 아님)**: 저장소 인터페이스 + Notion 구현 + source_registry + app.state.repositories 배선. service/sprints/reports가 인터페이스에 의존. NotionTicketRepository가 ticket_cache 읽되 미스면 Notion 라이브 폴백. create/update/claim/trash 후 캐시 write-through(방금 만든 티켓 즉시 보임 회귀 핀). 골든 회귀 바이트 동일 확인. blocks_to_markdown 역어댑터 + 경계 정적검사 추가.
- **0024 org_scope_and_dept_tree**: batch_alter로 departments.parent_id/org_id + (org_id, name) 복합 unique, job_titles.org_id, users.org_id/admin_scope/scope_org_id/scope_dept_id, board_posts.org_id, chat_rooms.org_id, document_cache.org_id/body_markdown/source, notifications.org_id 추가. org_id -> DEFAULT_ORG_ID, admin/system_admin -> admin_scope='portal' 백필. 소비자 없음 -> 무영향. '부서 관리' 화면/CLI 크래시 없음 확인(Python timestamp).
- **RBAC 배관(0024 후, 코드)**: app/core/scope.py(Scope/Principal/get_principal/scope_filter/visible_dept_ids) + app/core/authz.py 중앙화. /api/me에 scope 필드 가산. ensure_can_manage_target Principal 오버로드(global 관리자 무영향 회귀). list_users + dev-monthly에 scope_filter(global=무제한). 시스템/포탈 관리자가 사용자에게 org/dept 스코프를 배정하는 경로 추가. 스코프 IDOR 매트릭스 회귀(부서 관리자가 타 부서 사용자/리포트 조회 시 404/필터, 관리자 카운트 불변).
- **스케일 seam(독립, 위 단계들과 병렬 가능)**: db.py/config.py 풀+다이얼렉트 seam(SQLite 기본 불변), claim_next 다이얼렉트 분기, ETag/304, presence 스로틀, RateLimitStore 인터페이스, worker 싱글턴 가드. 전체 스위트로 동작 무변화 증명.
- **0025 self_id_refs**: document_favorites.doc_id, document_recent_views.doc_id, trash_items.ticket_id/doc_id 추가 후 캐시 notion_page_id 매칭으로 백필(미매칭 NULL 허용 + 로그). 신규 코드만 자체 id 사용, 레거시 컬럼은 이번에 남긴다. document_cache.body_markdown은 0024에서 이미 추가됨 -> 신규 create 시 markdown 저장.
- **0026 observability**: usage_events + sync_status 테이블. app/core/metrics.py + /metrics(operator+). record_usage_event를 login/ai-quiz/doc-create에 삽입(기록만). sync_status를 worker tick에 기록. 설정 split-brain 정리(feature.* 흡수, load_feature_flags 위임, write마다 reload). 회귀: 이벤트 기록 + /metrics 파싱 + feature 토글/파일 폴백.
- **defer 경계(별도 신호 시)**: Postgres 전환, native 소스 구현/컷오버, 완전 멀티테넌시, provisioning, settings 복합 PK, ticket_comments(E), 레거시 컬럼 drop, 공유 rate-limit store, WEB_WORKERS>1/멀티 노드, SSE. org_id가 이미 전 스코프 리소스에 있어 멀티테넌시는 재작업이 아니라 격리 강제만 추가하면 된다.

각 단계 공통 게이트: `.venv pytest` 전체 green + `scripts/static_checks.sh` -> STATIC_CHECKS_OK + 기존 티켓/문서/스프린트/리포트 응답 형태 불변 골든 회귀 + 워커 결정론(FakeClock) 유지.

### §7.4 신규 컴포넌트 / 설정 / 테이블 총목록

**신규 테이블**: organizations, ticket_cache, ticket_sync_state(싱글턴), usage_events, sync_status. (defer: ticket_comments, provisioning_invites, rate_limit_buckets, admin_grants.)

**컬럼 추가**: departments.parent_id/org_id, job_titles.org_id, users.org_id/admin_scope/scope_org_id/scope_dept_id, board_posts.org_id, chat_rooms.org_id, document_cache.org_id/body_markdown/source, notifications.org_id, document_favorites.doc_id, document_recent_views.doc_id, trash_items.ticket_id/doc_id.

**신규 모듈/파일**:
- app/org/constants.py: DEFAULT_ORG_ID 고정 상수
- app/org/models.py 수정: Organization 모델 + Department.parent_id/org_id
- app/core/models_base.py 수정: OrgScopedMixin(org_id)
- app/core/scope.py: Scope/Principal frozen dataclass + get_principal + scope_filter/visible_dept_ids
- app/core/authz.py: 중앙 capability/역할 상수(흩어진 READ_ROLES/WRITE_ROLES/OPS_ROLES 대체)
- app/core/source_registry.py: ticket_source/document_source 기반 repo 팩토리 + app.state.repositories
- app/core/notion_blocks.py 확장: blocks_to_markdown 역어댑터
- app/core/poll_conditional.py: etag_or_304(request, seq) 폴링 헬퍼
- app/core/ratelimit_store.py: RateLimitStore 프로토콜 + InMemoryRateLimitStore
- app/core/worker_lock.py: acquire_singleton_lock()
- app/core/metrics.py: record_usage_event + OpenMetrics 렌더
- app/tickets/models.py: TicketCache, TicketSyncState (기존 models.py 없음)
- app/tickets/repository.py: TicketRepository Protocol + TicketDTO(frozen)
- app/tickets/repository_notion.py: NotionTicketRepository, app/tickets/repository_native.py: 스텁(defer)
- app/tickets/sync.py: Notion -> ticket_cache pull 미러(team_docs/sync.py 동형)
- app/team_docs/repository_iface.py: DocumentRepository Protocol, app/team_docs/repository_notion.py: NotionDocumentRepository
- app/jobs/repository.py 수정: claim_next 다이얼렉트 분기
- app/core/db.py 수정: make_engine 풀 파라미터 + dialect_name(engine)
- app/users/service.py 수정: ensure_can_manage_target Principal 오버로드 + 스코프 배정
- app/reports/service.py, app/users/router.py 수정: scope_filter 배선
- app/worker_main.py 수정: tickets_sync_tick 등록 + sync_status 기록 훅
- app/models_registry.py 수정: tickets 모델 등 신규 import 한 줄씩

**신규 설정(env, app/core/config.py Settings)**: ticket_source(기본 'notion'), document_source(기본 'notion'), notion_tickets_sync_interval_seconds(기본 180), db_pool_size(5), db_max_overflow(10), db_pool_recycle(1800), web_workers(1), worker_singleton_lock(True). (소스 스위치는 엔진/repo 배선을 바꾸는 재시작급 변경이라 env에 둔다. 기존 notion_* 키와 동일 위치.)

**신규 설정(DB registry, 런타임 토글)**: presence_write_interval_seconds(기본 30), feature.*(흡수된 플래그), maintenance_mode/document_automation_enabled(정본을 registry로 확정). (defer: quota.max_users, quota.ai_quiz_per_day, quota.max_documents.)

**신규 엔드포인트**: GET /metrics(operator+). (defer: /api/admin/orgs/*, /api/admin/provisioning/*, /api/admin/export/org/{id}.)

**정적검사/테스트**: scripts/static_checks.sh에 notion 모듈 import 경계 규칙 추가. tests/regression에 티켓/문서/스프린트/리포트 골든, write-through 즉시 가시, since==seq->304, sync 결정론(FakeClock), tests/security에 스코프 IDOR 매트릭스.

### §7.5 겹치거나 상충한 제안의 통합 결정

1. **Alembic 번호 충돌**: 여섯 관점이 0022를 organizations/ticket_cache/org_scope로 제각각 잡았다. -> 정본 체인 0022 organizations, 0023 ticket_cache, 0024 org_scope+dept_tree, 0025 self_id_refs, 0026 observability로 통합. organizations를 맨 앞에 둔 근거: ticket_cache.org_id FK가 organizations를 요구하고, organizations는 기존 테이블을 안 건드려 무손상 게이트를 가장 쉽게 통과한다. ticket_cache가 A단계 운반체로 조기(0023)에 온다.
2. **users 스코프 컬럼 설계 충돌**: rbac 관점은 scope_type 단일 컬럼(멤버십 org_id를 앵커로 재사용), data-model 관점은 admin_scope + 명시 앵커(scope_org_id/scope_dept_id)를 제안. -> 명시 4컬럼(org_id + admin_scope + scope_org_id + scope_dept_id)으로 통합. 포탈 관리자는 특정 org 멤버십이 없을 수 있어 명시 앵커가 더 안전하고, "내가 속한 부서"와 "내가 관리하는 부서"를 분리한다. Principal이 이 컬럼에서 Scope(type)를 도출한다.
3. **모듈 파일명 충돌**: scope.py(rbac, structure-ops) vs scoping.py(data-model, migration-seq). -> app/core/scope.py로 단일화.
4. **소스 선택기 이중화**: source_registry.py(storage) vs tickets/provider.py(migration-seq). -> 선택 로직을 app/core/source_registry.py 한 곳에 모으고 별도 provider.py는 두지 않는다(인터페이스는 feature-local repository.py 유지).
5. **ticket_source/document_source 위치**: config.py(storage) vs settings registry(data-model, structure-ops). -> env config.py로 결정. 소스 스위치는 repo/엔진 배선을 바꾸는 재시작급 변경이라 런타임 토글 registry보다 env가 맞고, 기존 notion_* 키와 같은 위치다. per-org 소스 설정은 멀티테넌시로 defer.
6. **설정 복합 PK 시점**: structure-ops는 (scope_type, scope_id, key) 복합 PK를 build now로 제안. -> defer로 조정. per-org 설정은 완전 멀티테넌시(YAGNI)이고 config_versions.object_id 규약 변경이 rollback 이력을 끊을 위험이 있다. 지금은 split-brain 제거 + resolve_setting seam만 build now.
7. **프로비저닝 시점**: structure-ops는 초대/온보딩 백엔드 스켈레톤을 build now로 제안. -> defer로 조정. 둘째 회사가 없어 org 생성 흐름은 조기(premature)다. 지금은 organizations 테이블 + DEFAULT_ORG_ID 시드만.
8. **body_markdown 채우기 시점**: migration-seq는 컬럼만 심고 채우기는 E단계로, storage는 create 시 저장을 제안. -> 통합: 컬럼은 지금(0024) 심고, 신규 create의 본문은 지금부터 저렴하게 markdown 저장, 기존 본문 대량 백필만 defer.
9. **관측성 vs SQLite 쓰기 경합**: usage_events append가 단일 writer를 가중할 수 있다는 리스크(structure-ops, scale)를 반영해 record_usage_event를 저빈도 지점(login/ai/doc)에만 넣고 chat send/폴링 핫 경로에서 제외한다.

### 착수 순서 (통합)
1. 0단계(무코드): 현행 /api/tickets/mine|unassigned|team, /api/sprint, /api/team-docs/*, /api/admin/reports 응답을 tests/regression 골든으로 동결(페이크 Notion transport). 이게 이후 모든 단계의 무손상 증명 기준이다.
2. 0022 organizations 마이그레이션 + DEFAULT_ORG_ID 시드(기존 테이블 무접촉). 전체 pytest green + static_checks OK 확인.
3. 0023 ticket_cache + ticket_sync_state 신규 테이블 + models_registry 한 줄. app/tickets/sync.py + worker tickets_sync_tick(truncated 가드, try/except 격리) 등록해 캐시만 채운다. 읽기 경로 무변경, sync_state 채워짐 확인.
4. 저장소 추상화 코드 이관(마이그레이션 아님): TicketRepository/DocumentRepository 인터페이스 + Notion 구현 + source_registry + app.state.repositories, service/sprints/reports가 인터페이스 의존, ticket_source/document_source 기본 notion. NotionTicketRepository는 캐시 읽고 미스면 라이브 폴백. create/update/claim/trash write-through. 골든 회귀 바이트 동일 확인. blocks_to_markdown + notion import 경계 정적검사 추가.
5. 0024 org_scope+dept_tree 마이그레이션(batch_alter): departments.parent_id/org_id +(org_id,name) unique, users.admin_scope/scope_org_id/scope_dept_id/org_id, board/chat/document_cache/notifications.org_id, document_cache.body_markdown/source. DEFAULT_ORG_ID 및 admin/system_admin->portal 백필(Python timestamp). 소비자 없음, 관리자 화면 동일 확인.
6. RBAC 배관 코드: app/core/scope.py(Scope/Principal/get_principal/scope_filter) + app/core/authz.py 중앙화. /api/me에 scope 가산, ensure_can_manage_target Principal 오버로드, list_users + dev-monthly에 scope_filter(global=무제한), 사용자에게 org/dept 스코프 배정 경로. 스코프 IDOR 매트릭스 회귀.
7. 스케일 seam(위 단계들과 병렬 가능): make_engine 풀 파라미터 + dialect_name, claim_next 다이얼렉트 분기, ETag/304(chat/games/notifications), presence 스로틀 30s, RateLimitStore 인터페이스, worker 싱글턴 가드, systemd WEB_WORKERS 변수화. SQLite 기본 동작 불변 증명.
8. 0025 self_id_refs 마이그레이션: favorites/recent doc_id, trash ticket_id/doc_id + notion_page_id 매칭 백필(미매칭 NULL+로그). 신규 코드만 자체 id. 신규 문서 create 시 body_markdown 저장.
9. 0026 observability 마이그레이션: usage_events + sync_status. app/core/metrics.py + /metrics(operator+), record_usage_event(login/ai/doc), sync_status worker 훅. 설정 split-brain 정리(feature.* registry 흡수, write마다 reload).
10. (defer, 신호 도달 시) Postgres+pgbouncer 전환 -> native 소스 구현/컷오버 -> 완전 멀티테넌시 격리 -> provisioning/settings 복합 PK/공유 rate-limit store/WEB_WORKERS>1/SSE. org_id가 이미 전 스코프에 있어 재작업 아닌 강제 추가만.

### 열린 질문 (사용자 결정 필요)
- users 스코프 컬럼을 4컬럼(org_id 멤버십 + admin_scope + scope_org_id + scope_dept_id)으로 확정할지, 아니면 rbac 관점의 leaner scope_type 단일 컬럼(멤버십 org_id를 앵커로 재사용)으로 갈지. 나는 명시 4컬럼을 권장(포탈 관리자는 org 멤버십이 없을 수 있고 관리 대상 부서와 소속 부서를 분리해야 하므로).
- 다중 담당자 티켓의 scope_dept_id를 어느 부서로 유도할지(대표 담당자 부서 / 전 담당자 / 담당자 부서 미상 시 포탈 전용 버킷). dept 스코프를 실제 켜기 전에 이 규칙을 확정해야 부서 간 데이터 유출(IDOR)이나 누락을 막는다. 지금은 값이 비어 무해하나 강제 단계의 전제조건.
- AppSetting 복합 PK(scope_type, scope_id, key)와 프로비저닝(org 생성/초대/온보딩)을 지금 심을지 미룰지. 나는 둘 다 defer 권장(단일 org에서 이득 없음 + config_versions rollback 규약 변경 위험 + YAGNI). structure-ops 관점은 build now를 제안했으므로 사용자 확정 필요.
- ticket_source/document_source를 env config.py(재시작급, 기존 notion_* 키와 동일 위치)에 둘지, DB registry(런타임 토글)에 둘지. 나는 env 권장(소스 스위치가 repo/엔진 배선을 바꾸므로).
- /metrics 접근 통제를 operator+ 역할 게이팅으로 할지 nginx 127.0.0.1 allow로 제한할지(또는 둘 다). 운영 정보 유출 방지 방식 결정.

## 승인/상태
- 사용자가 "모든 아이디어 승인, 모두 계획" 지시(2026-07-29). 조직/부서 관리자 티어 아이디어 채택.
- **§0 확정(2026-07-29): (a) 부서 계층 + 관리자 티어로 시작, org_id 널로 심어 확장 여지 유지.**
- 마스코트: 외부 이미지 대신 **로컬 번들 권장**(CSP §6 불변 유지, 애니메이션 자유도는 동일).
- 다음 주 착수는 여전히 NEXT_SESSION_PLAN §A(성능)부터. 이 아키텍처는 그 뒤 별도 스펙으로 수렴.
