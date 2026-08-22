# MASTER PLAN — ClovirAssist 자체 데이터 플랫폼 전환

> **이 문서가 현재 제품 작업의 정본 계획이다.**
> 진입점은 [`WORK_STATE.md`](WORK_STATE.md), 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md),
> 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md), 실측 목록은 [`INVENTORY/`](INVENTORY/README.md),
> 결정과 그 근거는 [`../DECISIONS.md`](../DECISIONS.md) **D-187 이후**다.
>
> `docs/WORK_PLAN_INDEX.md` 는 UI 리뉴얼 이전 축의 마스터 계획이고 **이 문서로 대체됐다**.
> `docs/ui-renewal/*` 는 **W5 까지의 UI 축 자산**이고 살아 있다 — 다만 **W5B~W15 는 동결**이며
> 재개는 이 문서의 Phase E 다.

**기록 시점**: 2026-08-21 (S0) · **기준 Commit**: `60f8fafb` · **Branch**: `ui/mui-migration`

---

## 0. 한 문단 요약

ClovirAssist 는 오늘 Notion 을 System of Record 로 두고 SQLite 파일 하나 위에서 도는 제품이다.
그 구조가 실제로 무너져 있다 — 동기화 셋이 전부 실패 중이고, AI 경로에는 권한 필터가 아예 없으며,
런타임의 제품 정체성은 아직 옛 이름이다. 이 작업은 그 구조를 걷어내고 **PostgreSQL 을 정본으로 하는
자립 제품**을 만든다. 프로젝트·티켓·백로그·스프린트·보드·지식공간·문서·파일·사용자·권한을 제품이
스스로 보유하고, AI 가 그 위에서 **권한을 지켜** 검색·분석·생성한다.

---

## 1. 왜 지금 하는가 — 조사에서 확인된 것 셋

1. **세 개 동기화가 전부 실패 중이다.** `sync_status` 실측(2026-08-20 08:09 UTC): `tickets` ·
   `documents` = `Notion 응답 오류: HTTP 400`, `projects` = 프로젝트 연결 속성을 못 찾음.
   원인은 관리자 콘솔에서 사람이 DB id 를 바꿔 넣은 것이다 — `app_settings.notion_tasks_database_id`
   가 **문서 DB id** 를 가리키고 있다. 그 사이 **"Notion 연결 테스트"는 매번 통과했다** — 토큰만
   검사하고 DB 가 맞는지는 안 보기 때문이다.
2. **AI 도우미에 권한 필터가 없다.** n8n 이 `returnAll: true` 로 Notion 작업 DB **전체**를 가져와
   runner 에 넘기고, runner 는 `tickets[:800]` 을 그대로 모델 프롬프트에 싣는다. 요청자는 대명사
   해석에만 쓰이고 **필터로는 쓰이지 않는다**. 같은 저장소의 `app/assistant/facts.py` 는 정반대로
   `viewer=user` 를 넘긴다 — 즉 설계 선택이 아니라 **한 경로만 이 모델을 우회하고 있는 것**이다.
3. **제품 정체성이 런타임에서 아직 옛 이름이다.** nginx `server_name` · TLS CN/SAN · `APP_BASE_URL`
   이 전부 `clovirone-ai.gooddi.lab` 이다. OS hostname 만 `clovirassist` 로 바뀌어 있다.

---

## 2. Target Architecture

```
                      Browser (React 18 · MUI 7 · HashRouter)
                                    │  HTTPS
                       nginx  clovirassist.gooddi.lab
                                    │
                      FastAPI (sync)  127.0.0.1:8080
      ┌─────────────────────────────┼─────────────────────────────┐
      │                             │                             │
  Domain Services            Internal AI Service            Workers
  · identity/rbac            · Retrieval (LOCAL)            · batch lane
  · project/ticket           · Model Gateway                · conversational lane
  · knowledge/document          └ Provider Adapter          · index lane (신설)
  · storage                        ├ claude_cli
  · backup                         └ (future adapters)
      └─────────────┬───────────────┴─────────────┬───────────────┘
                    │                             │
          PostgreSQL 16 + pgvector + pg_trgm   File Storage Provider
          (System of Record)                   Local │ NFS │ SMB(CIFS)
                                                     └ Backup Storage (별도 Provider)
```

**사라지는 것**: SQLite · Notion Runtime · n8n · `claude-work-assistant`(8789) ·
`claude-request-interpreter`(8787) · `claude-ticket-runner`(8788) · `user_notion_mappings` ·
Notion Console · Notion Mapping Console.

### 2.1 확정 Component (라이선스 확인 완료)

| 영역 | 채택 | 라이선스 | 근거 |
|---|---|---|---|
| DB | **PostgreSQL 16** — Ubuntu 24.04 공식 저장소 (`16.14-0ubuntu0.24.04.1`) | PostgreSQL License | 외부 저장소 의존 없음이 설치 자동화와 고객 Mirror 환경에서 결정적이다 (D-188) |
| Vector | **pgvector 0.6.0** — `postgresql-16-pgvector`, noble/universe | PostgreSQL License | 별도 Vector DB 를 도입하지 않는다 |
| Keyword(한국어) | **`pg_trgm`** GIN | contrib | **FTS5 `tokenize='trigram'` 의 정확한 대체물이다.** PG 기본 `to_tsvector` 는 한국어를 공백으로만 쪼개 부분일치가 안 된다 — 팀이 0030 에서 이미 기각한 `unicode61` 실패 모드다 |
| Full Text | **PG FTS `simple` config** | contrib | 어절 단위 정확 일치·가중치용. `pg_trgm` 과 **함께** 쓴다 |
| Embedding | **`intfloat/multilingual-e5-small`** (384차원 · CPU/ONNX) — **확정 (D-211)** | MIT | S1 이 이 서버 CPU 로 실측했다: 색인 120 docs/s · 질의 p50 **6.0ms**. `bge-m3` 는 품질 +2.5%p 에 값이 11배라 **상향 경로**로만 둔다 |
| Re-rank | **쓰지 않는다 — RRF 융합** — **확정 (D-212)** | — | Cross-encoder 는 이 CPU 에서 top-50 에 **6.7초**다(백본 동일 대리 측정). 공식 ONNX 산출물도 없다. 계획이 적어 둔 대체안(R6)이 실측으로 확정됐다 |
| Vector Index | **처음에는 만들지 않는다.** 임계 초과 시 HNSW `m=32 · ef_construction=200 · ef_search=40` — **확정 (D-210)** | — | 384차원 exact 가 수천 규모에서 1~9ms 다. 교차점 ≈ **1.2만 벡터** |
| Editor | **TipTap (MIT extension 만)** | MIT | ProseMirror 기반 → 문서 정본이 곧 Block JSON. **Pro extension 은 상용이라 쓰지 않는다.** 번들 예산 때문에 **route-level lazy load 필수** |
| DnD | **dnd-kit** | MIT | Backlog·Sprint·Kanban·Folder 공통 |
| Parser | pypdf/pdfplumber · python-docx · python-pptx · openpyxl | BSD/MIT | **Docling 미채택** — torch 의존이 CPU-only 8 vCPU 에 과하다 |
| OCR / ClamAV / LibreOffice | **도입하지 않는다** | — | 폐쇄망 사내 도구 + 현재 업로드 파일 4개. 설정 Hook 만 남긴다 |
| Cache/Queue | **추가하지 않는다** (Redis 없음) | — | PG advisory lock + 테이블로 충분하다 |

### 2.2 유지하는 기존 계약 — 재작성하지 않는다

- `app/core/http_client.py::OutboundClient` — SSRF allowlist · secret-ref 주입 · 429-only retry.
  **Model Gateway 의 HTTP Adapter 가 이 관문을 그대로 쓴다.**
- `app/core/scope.py` · `app/core/ownership.py` — Scope/Ownership 계산 엔진. 확장하되 대체하지 않는다.
- `app/llm/prompt.py` — nonce delimiter + `neutralize()` 기반 Trust Boundary.
  **저장소에서 가장 잘 만들어진 방어다. 전 AI 경로로 확대 적용한다.**
- `app/core/uploads.py` — magic-byte sniffing · traversal guard · RFC 6266. Storage Provider 아래로.
- `app/core/worker_lock.py` — file lease. PG advisory lock 교체 검토하되 단일 호스트면 유지 가능.
- argon2id 해싱 · opaque session + CSRF · 5역할 · audit masking · approval executor registry.

---

## 3. 확정 Decision — 전문은 `../DECISIONS.md` D-187~D-208

| ID | 결정 |
|---|---|
| **D-187** | PostgreSQL 이 System of Record 다 — SQLite · Notion Runtime · n8n 을 함께 폐기한다 |
| **D-188** | 제품 표준 스택은 **PG16 + pgvector 0.6.0 + pg_trgm** 이다 (구 D-D). 근거는 성능이 아니라 폐쇄망 설치다 |
| **D-189** | Alembic 61 revision 을 이식하지 않는다. `0001_pg_baseline` 하나로 다시 시작한다 (구 D-A) |
| **D-190** | Test DB 2계층 — 트랜잭션 롤백 기본 + `TEMPLATE` 실 DB fixture (구 D-B). 동시성 테스트 약 40개는 **재작성**이다 |
| **D-191** | `is_write_conflict()` 를 둘로 쪼갠다 — PG 에서 진짜 제약 위반을 재시도로 감추면 안 된다 |
| **D-192** | `--workers 1` 은 공유 저장소를 만든 **다음에만** 푼다 |
| **D-193** | Permission 은 **additive grant + fail-closed** 다. 일반 Deny 를 만들지 않는다 (구 D-E) |
| **D-194** | 목록·상세·Search·**AI Retrieval** 이 같은 `effective_visibility_clause` 를 쓴다 |
| **D-195** | Ticket 식별자는 3층이다 — `UUID` · `<KEY>-<SEQ>` · `GIT-n`(immutable) |
| **D-196** | Project Key 소유는 영구다. 채번은 `INSERT … ON CONFLICT DO UPDATE … RETURNING` 으로 한다 |
| **D-197** | Project Key 20건 확정 **전에는** 재채번을 시작하지 않는다 |
| **D-198** | Document 정본은 **Block JSON** 이다 (구 D-C) |
| **D-199** | File Binary 는 DB 에 넣지 않는다. Storage Provider 는 **접근 Protocol 기준**이다 |
| **D-200** | GPU 를 전제하지 않는다. Retrieval 전 계층은 **CPU Local** 이다 |
| **D-201** | 자연어 생성은 Model Gateway 뒤 **Adapter** 다. `/usr/bin/claude` 는 Adapter 하나일 뿐이다 |
| **D-202** | AI Permission Filter 는 Retrieval **앞**에 둔다 |
| **D-203** | AI Index 는 **파생 데이터**다. 백업하지 않고 재생성한다. Permission 변경은 재임베딩이 아니라 필터 재계산이다 |
| **D-204** | Backup 과 Restore 를 함께 설계한다. **파일 생성만으로 SUCCESS 가 아니다** |
| **D-205** | 설치 자동화는 **제품 요구**다. 모든 Session 이 Installer 계약을 진다. 재부팅 후 수동 명령 0회 |
| **D-206** | Session 종료 규약 — 한 Session 이 여러 대형 Wave 를 몰아 수행하지 않는다 |
| **D-207** | **W5B~W15 즉시 동결.** 재개는 Phase E (S15~S20) 다 |
| **D-208** | 검증 실행 경제 E1~E10 — 없애는 것은 **중복 실행뿐**이고, 필수 검증(§9.3)은 어떤 경우에도 면제되지 않는다 |

---

## 4. 사용자 확정 제약 (U1~U19)

| # | 결정 |
|---|---|
| U1 | **GPU 는 현재도 미래도 없다.** GPU 전제를 Architecture 에 넣지 않는다 |
| U2 | Retrieval 전 계층(Keyword · PG FTS · pgvector · Embedding · Re-ranking · Metadata/Relation Filter · Permission Filter · Source/Citation 조회)은 **CPU 기반 Local** |
| U3 | 자연어 **생성**은 Model Gateway 뒤 교체 가능한 **Provider Adapter**. Business Logic 이 여기 강결합되면 안 된다 |
| U4 | CPU-only Local LLM 을 주 생성 모델로 억지 채택하지 않는다. 검증되면 Adapter 로 **추가**는 가능 |
| U5 | 생성 Provider 부재 시에도 검색·Retrieval·Permission Filter·Source 조회는 동작해야 한다. **다만 요약·분석·문서생성까지 동일하게 동작한다고 과장하지 않는다** |
| U6 | W0~W5 자산 보존. **W5B~W15 즉시 동결** |
| U7 | W5B 의 **목적(Search/Filter 기능 정확성 전 사슬 검증)은 반드시 남긴다.** 단 Legacy Notion Query 를 대상으로 지금 실행하지 않는다 |
| U8 | 실 NFS/NAS 장비 정보 없음. **접근 Protocol 기준으로 추상화하고 재현 가능한 시험 Storage 로 실제 검증한다.** 인터페이스만 남기는 완료 처리 금지 |
| U9 | 시험 Storage 는 실 NAS 검증과 동일하다고 과장하지 않는다. 실 정보 수령 시 **Application 수정 없이 Configuration 만으로** 연결 가능해야 한다 |
| U10 | Ticket 식별자 3층: `Internal ID = UUID` · `Canonical Display Key = <PROJECT_KEY>-<SEQ>` · `Legacy Alias = GIT-n` |
| U11 | 재채번 **전에** 실제 Project Relation 과 20개 Project Key 를 먼저 확정한다. 임의 배정 금지 → **Migration Exception** |
| U12 | Migrated/신규 Ticket Sequence 충돌 없도록 **PostgreSQL 수준에서** 번호 배정과 동시성 안전성 보장 |
| U13 | **제품 설치 자동화가 필수 범위다.** Clean Ubuntu 24.04 에서 GitLab 기준 Source 를 확보해 Entry Point 하나로 전체 자동 설치·구성 |
| U14 | 장기 실행 Service 는 **서버 재기동 후 수동 명령 없이 자동 시작**. **제품 전체 Reboot Test** 수행 |
| U15 | 설치 자동화는 전담 Session 을 갖는다. Harness script 한 줄로 간주하지 않는다 |
| U16 | **한 Session 이 여러 대형 Wave 를 몰아 수행하는 구조 금지.** Cutover 와 UI Renewal 을 같은 Session 에 두지 않는다 |
| U17 | PG Version 은 "최신"이 아니라 제품 설치·운영 근거로 판정한다 → **D-188 로 판정 완료. S1 은 성능 검증만 한다** |
| U18 | Permission 상속을 필요 이상 복잡하게 만들지 않는다. **additive grant + fail-closed.** 단 목록·상세·Search·AI Retrieval 이 같은 계산을 쓴다는 원칙은 유지 |
| U19 | **Core Migration 은 확정이다.** 제품 Domain 밖 Notion DB 는 분리 표시하고 별도 외부 결정으로 둔다. "유일한 Gate" 라고 쓰지 않는다 |

---

## 5. Domain 설계 요지

### 5.1 Identity · RBAC (S5)

| 지금 (S5 완료) | 비고 |
|---|---|
| `users.role` = **주 역할**, `user_roles` = 추가 역할. 유효 권한은 **합집합** | 다섯 역할의 뜻은 안 바뀌었다 (D-230) |
| `CONSOLE_READ/WRITE/OPS_ROLES` 는 **여전히 「역할 → 사람」의 정본**이고, `permissions.py` 가 그 위에 「권한 → 역할」을 얹는다 | 손으로 역할을 나열하면 시험이 잡는다 |
| `org_units`(트리, `kind`) + `organizations`. `Department` 는 같은 클래스의 별칭 | 컬럼 이름은 그대로 (D-234) |
| Ownership 은 **공통 개념**이고 표를 만들지 않았다. 대신 직접 부여를 `resource_grants` 가 담는다 | 근거 D-233 |

Permission 목록 **32개**(정본은 `app/authz/permissions.py`): 위 초안 그대로에 `DOCUMENT_ADMIN`
한 건을 더했다 — `confidential` 을 여는 `*_ADMIN` 이 문서 축에도 있어야 한다(D-230).
`STORAGE_CONFIGURE`(S8) · `AI_CONFIGURE`(S9) 는 그 Component 가 아직 없어 소비처가 없다.
어휘를 먼저 고정한 이유는 그 Session 들이 각자 새 이름을 지어 오는 것을 막기 위해서다 —
실제로 **`SPACE_*` 는 S7 이 새 이름을 안 짓고 그대로 소비했다**(`app/knowledge/router.py`).

**상속 (D-193)**: `Organization ─ OrgUnit ─┐ ├→ Project ─ Knowledge Space ─ Folder ─ Document`,
`User ─ Role ─┘ └ Ticket`. 유효 권한 = `Role ∪ Organization ∪ Project Member ∪ 직접 부여`,
미설정은 fail-closed. 하위는 상위를 **넓히기만** 한다. 유일한 축소 원시연산은 **`confidential`
플래그 하나**이고 의미는 "소유자 + 명시 부여자 + `*_ADMIN` 보유자만" 으로 고정한다.
기존 제품이 이미 additive + fail-closed 다(`visibility_scope = _widest(...)` 는 합집합,
`owner_kind='unset'` 은 어느 분기도 만족하지 않는다) — 새 모델을 발명하는 게 아니라 **일반화**다.

### 5.2 Work Domain (S6)

**Project Key**: `projects.code` 가 22건 전부 NULL 이다. 규칙 = 2~10자 · 영문 대문자 시작 ·
대문자+숫자 · 대소문자 무관 유일 · 예약어 금지 · **재사용 금지** · URL 안전.

```sql
project_key_registry(
  key text PRIMARY KEY CHECK (key ~ '^[A-Z][A-Z0-9]{1,9}$'),
  project_id uuid,                       -- NULL 이면 예약어
  state text NOT NULL CHECK (state IN ('active','retired','reserved')),
  created_at timestamptz NOT NULL);
CREATE UNIQUE INDEX uq_pkr_key_ci ON project_key_registry (upper(key));
-- 'GIT' 은 Legacy namespace 로 reserved seed → 어떤 Project 도 가져갈 수 없다
```

**Ticket 식별자 (D-195)**: `canonical_key GENERATED ALWAYS AS (project_key || '-' || seq)` 는
**구현할 수 없다** — PostgreSQL Generated Column 은 다른 테이블 값을 참조할 수 없다. 실제 저장
컬럼 + **BEFORE INSERT/UPDATE 트리거**로 `projects.code + seq` 에서 파생시킨다.

> **S6 이 실제로 만든 모양은 아래 초안과 두 자리가 다르다** (D-236~D-238):
> 표 이름은 `tickets`(`ticket_cache` 에서 이전) · 프로젝트 컬럼은 **`project_uid` 그대로**
> (API 응답에 나가는 이름이라 안 바꿨다) · Key 는 `projects.code` · `ck_tickets_assigned` 는
> 「번호와 표시 이름은 함께 있거나 함께 없다」로 좁혔다(초안대로면 미러 전량이 위반이다 —
> Project Key 가 아직 하나도 없어서 번호를 줄 수가 없다).

```sql
tickets(id uuid PK, project_id uuid REFERENCES projects(id),   -- Exception 은 NULL
        seq integer CHECK (seq > 0), canonical_key text, legacy_key text, …,
  CONSTRAINT ck_tickets_assigned CHECK (
    (project_id IS NULL AND seq IS NULL AND canonical_key IS NULL) OR
    (project_id IS NOT NULL AND seq IS NOT NULL AND canonical_key IS NOT NULL)));
CREATE UNIQUE INDEX uq_tickets_project_seq ON tickets (project_id, seq) WHERE project_id IS NOT NULL;
CREATE UNIQUE INDEX uq_tickets_canonical ON tickets (canonical_key) WHERE canonical_key IS NOT NULL;
CREATE UNIQUE INDEX uq_tickets_legacy    ON tickets (legacy_key)    WHERE legacy_key IS NOT NULL;
ticket_key_aliases(alias text PK, ticket_id uuid NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                   kind text CHECK (kind IN ('legacy','superseded')), created_at timestamptz);
project_ticket_counters(project_id uuid PK REFERENCES projects(id) ON DELETE CASCADE,
                        last_seq integer NOT NULL DEFAULT 0 CHECK (last_seq >= 0));
```

**채번 (D-196)** — `last_seq` 의 의미를 하나로 고정한다: **지금까지 발급된 마지막 번호.**

```sql
INSERT INTO project_ticket_counters (project_id, last_seq) VALUES (:project_id, 1)
ON CONFLICT (project_id) DO UPDATE SET last_seq = project_ticket_counters.last_seq + 1
RETURNING last_seq;   -- ← 이 값이 새 Ticket 의 seq. INSERT 와 같은 트랜잭션이다
```

- Migration 직후 seed: 프로젝트별 `last_seq = COALESCE(MAX(seq), 0)` → **첫 신규 번호 = MAX+1**
- 롤백되면 counter 증가도 함께 롤백된다 → **번호가 소비되지 않고 gap 이 생기지 않는다.**
  PostgreSQL `SEQUENCE` 는 롤백해도 번호를 되돌리지 않아 **채택하지 않는다**
- **Key Resolution 순서**: `canonical_key` → `legacy_key` → `ticket_key_aliases.alias` → `uuid`

**Migration Exception (U11)**: `project_link` = ambiguous 2 · missing 4, 프로젝트 미연결 6건,
`notion_missing_at` 9건. 이들은 `project_id`/`seq`/`canonical_key` 가 **전부 NULL** 로 적재되고
`migration_exceptions(ticket_id, reason, source_evidence, resolved_at, resolved_by)` 에 사유가 남는다.
소속 Project 가 없으므로 fail-closed 에 의해 일반 사용자에게 보이지 않는다 — **의도된 동작이다.**

**Ticket Domain**: Notion Property 를 복제하지 않는다. **난이도 · 예상WD · 실제WD 는 유지한다** —
Sprint 번다운과 Dev Report 집계의 입력이라 버리면 두 화면이 죽는다. 신설 = `ticket_relations` ·
`ticket_activities` · `ticket_watchers` · `backlog_rank` · `sprint_id`.
Workflow 는 표시 Status 와 내부 Category 를 분리한다(`계획→OPEN` · `진행/검증→IN_PROGRESS` ·
`이슈→OPEN` · `완료→DONE` · `취소→CANCELED`).

**Backlog/Sprint/Board**: Backlog rank 는 `priority` 와 별개 축이고 **Fractional ranking** 으로
전체 재번호 없이 삽입한다. Kanban Drop 은 **Status 변경 + Activity + Audit + `updated_at` +
Notification 을 한 트랜잭션**으로 처리한다. DnD 는 `dnd-kit` 기반 공통 부품 하나로 통일한다.

**동시성/삭제**: `version integer` 낙관적 잠금을 Ticket·Document·Project 에 도입하고 현재
`notion_version`(Notion 페이로드 해시)은 폐기한다. 충돌 시 409 + 차이 표시.
외부 식별자(`canonical_key`·`legacy_key`)는 **삭제 후에도 재사용하지 않는다.**

### 5.3 Knowledge Domain (S7 · S8)

```sql
knowledge_spaces(id, org_id, name, slug, owner_ref, …)
folders(id, space_id, parent_id, name, path, sort_order)            -- 트리
documents(id, space_id, folder_id, title, doc_type,
          source_type USER|AI|MIGRATION, current_version_id, version, created_by, …)
document_versions(id, document_id, version_no, body jsonb, author_id, change_reason,
                  ai_used, source, prev_version_id, created_at)
document_attachments · document_relations · tags · document_tags
files(id, filename, mime_type, size_bytes, checksum_sha256,
      storage_provider_id, storage_key, owner_ref, created_by, created_at)
storage_providers(id, kind LOCAL|NFS|SMB, config jsonb, role OPERATIONAL|BACKUP, enabled)
```

**본문 정본 = Block 구조 JSON (D-198).** 파생으로 Markdown·Plain Text 를 함께 저장한다.
블록 id 가 **Citation 의 안정적 앵커**이고, Markdown 만으로는 "이 문장의 출처 위치"를 못 가리킨다.
Notion API 한계에서 온 `MAX_BLOCKS=100` · `MAX_LINE_CHARS=1900` **본문 길이 거절은 삭제한다** — 새 도메인에서 삭제했다(S7). 옛 미러(`app/team_docs`·`app/tickets`)의 거절은 **S14 까지 남는다**: 저쪽은 아직 Notion 으로 나가고 `markdown_to_blocks` 가 상한에서 조용히 자르므로, 거절만 없애면 명시적 거절이 조용한 데이터 손실로 바뀐다(D-247).

**Folder 이동이 Permission 이나 Project Relation 을 바꾸지 않는다** — 별개 축이다.

**Storage (D-199)**: 마운트 관리는 systemd `.mount`/`automount` 유닛으로, Application 은
마운트포인트 경로만 안다. **필수 검증 매트릭스 16항**(S8 Exit) — Mount · Read/Write · Permission ·
Create/Delete · Checksum · Capacity · **Storage unavailable(503, 500 아님)** · **Reconnect** ·
**동작 중 장애 시 부분 파일 미커밋** · Reboot · **Reboot 후 자동 Mount** ·
**Mount 완료 전 App 기동(`RequiresMountsFor=`)** · **잘못된 Local Path 기록 방지(`st_dev` 비교 후
쓰기 거부)** · Backup · Restore · 운영/백업 동일 저장소 경고.

### 5.4 AI Platform (S9 · S10)

```
[ LOCAL — 생성 Provider 없이도 동작 ]        [ Provider 필요 — 없으면 그 기능만 정지 ]
 Keyword (pg_trgm) · Full Text (PG FTS)       요약 · 분석/비교 · 문서 생성 · 자연어 답변
 Semantic (pgvector) · Embedding (CPU)
 Re-ranking (CPU) · Metadata/Relation Filter
 Permission Filter · Source 조회 · Citation
```

완료 조건 문구도 이 경계대로 적는다. **생성이 필요한 기능까지 Provider 없이 동작한다고 쓰지 않는다.**

```
app/ai/gateway/
  contract.py     # embed() · rerank() · generate() · capabilities()
  registry.py     # 설정 기반 Adapter 선택. 모델명은 어디에도 하드코딩하지 않는다
  adapters/claude_cli.py · local_embed.py · local_rerank.py
```
현재 하드코딩 두 곳(`app/llm/provider.py` `DEFAULT_MODEL="sonnet"` · runner `assistant.py`
`ASSISTANT_MODEL`)을 제거하고 설정으로 일원화한다.

**Retrieval — 권한이 먼저다 (D-202)**

```
User → effective_visibility_clause(principal)   ← D-194 의 그 함수, AI 도 동일하게 쓴다
     → 후보 집합 결정                             ← 권한 없는 행은 여기서 이미 없다
     → Hybrid Retrieval (pg_trgm ⊕ PG FTS ⊕ pgvector, RRF) + metadata/relation filter
     → Re-rank (CPU) → Context 조립 → Model Gateway.generate()
```

**금지: 전체 검색 → LLM 전달 → "숨기라고 지시".** `LIMIT` **앞에** 권한 조건을 건다.

**Pipeline**: `Upload → 원본 저장 → 검사 → Parsing → 구조 추출 → Chunk → Embedding → Search Ready`.
업로드 요청은 완료를 기다리지 않는다 — 전용 **`index` worker lane** 을 추가한다(임베딩이 배치 틱을
굶기지 않게). **Index Lifecycle**: Permission 변경은 **재임베딩이 아니라 필터 재계산**이다(D-203) —
현재 검색이 300초 재색인 간격 동안 권한 변경을 못 따라가는 문제를 여기서 없앤다.

**Citation 앵커**: PDF=page · PPTX=slide · DOCX=section/paragraph · XLSX=sheet+range ·
Document=block id · Ticket=description/comment id/activity id.

---

## 6. PostgreSQL 전환 실행 목록 (S2)

### 6.1 Alembic (D-189)

61 revision 을 PG 에서 재생하지 않는다. 실측된 장애물:
boolean `server_default=sa.text("0"|"1")` **31곳** → PG 타입 오류 · FTS5 virtual table + trigger
DDL(0030·0050) → PG 에 문법 없음 · `sqlite_where=` 부분 유니크 **3개** → PG 에서 **`WHERE` 가
조용히 사라져 전체 유니크가 된다**(승인 재요청·프롬프트 2차 버전·2회 offboarding 이 막힌다) ·
`recreate="always"` 3곳 · 0055 는 "SQLite 는 기존 데이터를 새 FK 로 소급 검사하지 않는다"에 **의존**한다.

→ `alembic/versions/` 를 `alembic/legacy_sqlite/`(비활성 보관)로 옮기고 `0001_pg_baseline.py`
하나로 목표 스키마를 만든다. 데이터는 alembic 이 아니라 Migration Tool 이 옮긴다.

### 6.2 코드 수준 SQLite 의존 제거 — 실측 13항

> **S2 가 12항을 이행했고 10번(문자열 날짜 컬럼)은 S7 이 닫았다**(P-14a · D-248). 이행 결과와
> 실측 정정은 [`INVENTORY/08_SQLITE.md`](INVENTORY/08_SQLITE.md) 가 정본이다 —
> 여기 계획표는 그대로 둔다(계획과 실행 기록을 한 문서에 겹쳐 쓰지 않는다).

| # | 자리 | 조치 |
|---|---|---|
| 1 | `app/core/db.py:74-102` PRAGMA 4종 · `check_same_thread` · `isolation_level=None` | 삭제. `pool_size`/`max_overflow` 실제 설정 |
| 2 | `app/core/db.py:115-138` `exec_driver_sql("BEGIN")` | 삭제 (psycopg 가 관리) |
| 3 | **`app/core/db.py:154-180` `is_write_conflict()`** | **가장 위험한 자리 (D-191).** `is_serialization_conflict()`(40001·40P01·55P03)와 유니크 충돌 국소 처리로 **둘로 쪼갠다**. 115 호출부 · 30 모듈 전수 감사 |
| 4 | `app/jobs/repository.py:167-193` claim | **`SELECT … FOR UPDATE SKIP LOCKED`**. 문자열 `strftime` 바인딩 제거 → 진짜 `timestamp` |
| 5 | `rowid` 정렬 4곳 (`chat/service.py` · `tickets/comments.py` · `team_docs/comments.py` · `search/service.py`) | **`seq bigint GENERATED ALWAYS AS IDENTITY`** 추가 후 `(created_at, seq)` 정렬 |
| 6 | `func.json_extract` 2곳 (`jobs/router.py` · `prompts/router.py`) | **`jsonb`** + `->>` / GIN 인덱스 |
| 7 | 27개 `*_json` Text 컬럼 | **`jsonb`**. 단 `approvals.request_payload_json` 은 유니크 키의 일부라 **정규화 직렬화 규약 명시** 또는 해시 컬럼 분리 |
| 8 | `sqlite_where=` 3곳 | **`postgresql_where=`** |
| 9 | `LIKE` 대소문자 3곳 (`search/query.py` · `retention.py` · `schedules/router.py`) | `ILIKE` 또는 `pg_trgm` 경로 |
| 10 | 문자열 날짜 컬럼 (`due_date`·`starts_on`·`last_edited`·`week_of`·`sort_key` 등) | **`date`/`timestamptz` 정식 타입** |
| 11 | `VARCHAR(n)` — SQLite 는 무시, PG 는 강제 | **Migration 전 길이 감사 필수(S1).** 13개 컬럼 |
| 12 | `app/backups/sqlite_backup.py` 전체 | `pg_dump -Fc` 기반 재작성 |
| 13 | `ID_BATCH_SIZE=500` 근거 주석 | PG 한계(65535)로 정정 |

### 6.3 `--workers 1` 잠금 해제 (D-192)

지금은 rate limit · claim lock · quota lock 이 전부 프로세스 메모리라 워커를 못 늘린다.
`login/chat/game_ai/assistant` rate limiter → `rate_limit_buckets` 테이블(token bucket,
`UPDATE … RETURNING`) · `tickets/claim_lock.py` → `pg_advisory_xact_lock(hashtext(ticket_id))` ·
`quotas/quota_lock.py` → 동일 + `SELECT … FOR UPDATE` · reindex/sync/create lock → advisory lock ·
`SettingsCache` → 주기 갱신 또는 `LISTEN/NOTIFY`.
**순서 규약: 공유 저장소를 먼저 만들고 그 다음에 `--workers` 를 올린다.**

### 6.4 Test Harness (D-190)

현재는 `alembic upgrade head` 로 **템플릿 파일**을 만들고 테스트마다 `shutil.copy` 한다 — 파일 DB
전용 기법이다. 기본은 테스트당 트랜잭션 rollback, 실 DB 필요 fixture 는
`CREATE DATABASE … TEMPLATE clovir_test_template`.
**동시성 테스트 약 40개는 단순 이식이 아니라 재작성이다** — 지금은 `database is locked` 문자열과
WAL 단일 writer 의미를 단언한다. 그대로 두면 **거짓 초록**이 된다.
`check_test_strength.py` 가 이 재작성을 "약화" 로 오판하지 않도록 `qa-contract-replaced-by:` 규약을 쓴다.

---

## 7. Migration 전략

### 7.1 범위와 결정 주체 (U19) — "유일한 Gate" 라는 표현을 쓰지 않는다

| 구분 | 대상 | 결정 |
|---|---|---|
| **Core Migration — 확정. 사용자 결정 불필요** | Notion 작업(1,119) · 프로젝트(21) · 문서(110) · 문서유형(15) · 카테고리(11) · 첨부(9) + **SQLite 앱 고유 데이터 전량** | **이관한다.** 재확인하지 않는다 |
| **제품 결정 — 사용자 확인 필요** | 20개 Project Key 명명 | 초안 제시 → 확인 → 적용. 확정 전 재채번 없음 |
| **제품 Domain 밖 — 별개 외부 결정** | Notion `오라클 버그 수정`(179) · `휴일 근무 지원내역`(23) · `교육 커리큘럼`(9) | **기본값 = 이관하지 않음.** Core Migration 은 이 결정과 무관하게 진행된다 |

### 7.2 Source 는 둘 다 정본이다

| Source | 정본 자격 |
|---|---|
| **Notion** | Ticket 본문·속성·관계·첨부 · Document 본문·분류 · Project 속성 |
| **SQLite** | **Notion 에 없는 자체 데이터**: `users`(25) · `sessions` · `audit_logs`(1,360) · `ticket_comments`(9) · `ticket_attachments`(2) · `document_comments/favorites/recent_views` · `conversations`(87)/`messages`(311) · `notifications`(309) · `jobs`(165) · `approvals` · `board_*` · `chat_*` · `game_*` · `projects` 의 앱 소유 컬럼 · `app_settings` · `config_versions` · `integrations` · `runners` · `prompts`/`policies`/`templates` · `backups` |
| 충돌 | 양쪽에 있는 것은 **Ticket·Document·Project 셋**. 본문·속성은 Notion, 부가물(댓글·첨부·즐겨찾기·소유권·건강도)은 SQLite |

### 7.3 파이프라인과 Dry Run

```
Notion + SQLite → Extract → Transform → ClovirAssist Domain → Validate → PostgreSQL
```
Notion Schema 를 복제하지 않는다. **Notion 임시 File URL 을 새 DB 에 저장하지 않는다** — 파일 9개는
실제 File Storage 로 내려받아 이관한다. `legacy_mapping(legacy_source, legacy_source_id,
target_type, target_id, migrated_at)` 을 보존하되 **운영 Business Logic 은 Migration 이후 Notion ID 를
사용하지 않는다.**

**운영 데이터에 바로 Migration 하지 않는다.** `Notion + SQLite → Dry Run → 임시 PostgreSQL →
검증 → 수정 → 재실행`. 검증 항목: Project/Ticket/Document/User/Relation/Attachment/File 수 · 누락 ·
중복 · 변환 실패 · 깨진 Relation · 깨진 File Link · **문자열 길이 초과** · legacy_key 유일성 ·
canonical_key 충돌 · Exception 분류 결과.

### 7.4 물량 (실측)

| 항목 | 수량 | 비고 |
|---|---|---|
| Ticket | 1,119 (Notion) / 1,124 (미러) | 본문은 **미러에 31건뿐** → Notion block API 로 재수집 |
| Document | 110 | 본문 **미러에 0건** → 110건 전량 재수집 (평균 38 블록) |
| Project | 21 | `projects.code` 22건 전부 NULL |
| 첨부 | **9개** | 티켓 4 + 문서 5 — 파일 이관은 사실상 문제가 아니다 |
| 분류 taxonomy | 문서유형 15 + 카테고리 11 | |
| 예상 Notion API 호출 | ~1,230회 | 3 req/s 제한 시 약 7분 |

### 7.5 Cutover (S14) · Rollback

```
Dry Run 완료 → 전체 검증 → 최종 Backup → Maintenance Mode → 마지막 Delta Migration
→ PostgreSQL 전환 → File 검증 → Relation 검증 → Application 검증 → AI Index 생성
→ 서비스 Open → Notion Runtime 차단 → SQLite Runtime 차단
```

| 단계 | Rollback |
|---|---|
| Dry Run | 전면 가능 (임시 DB 폐기) |
| Delta 이후 · 서비스 Open 전 | 가능 — 최종 Backup + SQLite 원본 보존 |
| **서비스 Open 후** | **부분** — 그 뒤 입력분은 유실. 그래서 Open 직전 검증을 두껍게 한다 |
| Notion/SQLite 차단 후 | 원본 파일은 보존하되 되돌리지 않는다 |

**S14 에는 UI Renewal 을 넣지 않는다 (U16).** Cutover 는 그 자체로 하나의 종료 단위다.

---

## 8. Backup · Restore (S12)

| 정본 (백업 필수) | 재생성 가능 (백업 제외, 명시) |
|---|---|
| PostgreSQL 전체 · 원본 파일 · 첨부 · Settings · Audit | Embedding · Search Index · Chunk · Preview · Temp · Cache |

- `pg_dump -Fc` + 파일 Storage 아카이브 + `manifest.json`(schema version · alembic head · provider ·
  체크섬 · 범위)
- **파일 생성만으로 SUCCESS 처리하지 않는다 (D-204)** — sha256 + `pg_restore --list` 파싱 +
  임시 DB 복원 검증 후 SUCCESS. 상태는 `RUNNING`/`SUCCESS`/`FAILED`
- **운영 Storage 와 Backup Storage 는 별도 Provider.** 동일 물리 저장소면 경고
- Local Backup UX: 실행 → 다운로드 → 다운로드 완료 후 **"서버에 저장된 백업 파일을 삭제하시겠습니까?"**
  명시적 선택. 자동 삭제하지 않는다
- Restore: `Maintenance Mode → Restore → PG Validation → File Validation → Relation Validation →
  필요한 Re-index → Application Validation → Service Open`.
  기존 `scripts/restore_rehearsal.py` 의 8단계(특히 **복원된 DB 로 앱을 실제 기동해 읽기 경로를
  호출하는 7단계**)를 PG 기준으로 이식한다 — 저장소에서 가장 정직한 검증 자산이다

---

## 9. Session 계획 S0~S22

### 9.0 모든 Session 이 지키는 종료 규약 (D-206)

```
구현 → Targeted Test → Static/Contract → 관련 Integration
     → [필요 시] 영향 Flow/E2E → [필요 시] 독립 Reviewer
     → Finding 수정 → 영향 범위 재검증 → Exit Gate → Commit → Working Tree Clean
```
- **`[필요 시]` 두 단계는 기계적으로 붙이지 않는다.** 그 Session 의 성격과 **자기 Exit 조건이
  요구할 때** 수행한다. Exit 조건에 없고 변경 성격상 필요하지도 않으면 생략한다 — 대신
  §9.3 의 필수 검증은 **어떤 경우에도 면제되지 않는다**
- **한 Session 은 위 사슬을 스스로 끝낼 수 있어야 한다.** 여러 대형 Wave 를 몰아 넣지 않는다
- Runtime Component 를 추가하면 **Installer 계약**([INSTALLATION.md](INSTALLATION.md) §6)을
  같은 Session 에서 이행한다
- Full Capture 는 **S22 에서만**. 각 Session 은 자기가 건드린 Surface 만 재캡처한다
- W5 회고의 교훈을 규약으로 고정한다: 한 Wave 에 범위와 검증이 몰려 10시간을 넘겼다.
  **범위가 커지면 Session 을 쪼갠다**

### 9.1 Session 목록

#### Phase A — 기반

| S | 이름 | 핵심 산출 | Exit 조건 |
|---|---|---|---|
| **S0** | Plan 기록 | Master Plan · Work State · Backlog · Decisions(D-187~D-208) · Inventory · Installation 을 `docs/` 에 저장. **W5B~W15 동결 선언** | 문서 커밋 · Tree clean |
| **S1** ✅ | 기반 정직화 · 실측 · **성능 검증** | 프로브 8건 수정 · S1 소유 미확인 항목 확인 · PG16.15+pgvector0.6+pg_trgm 실측 · CPU 임베딩/리랭킹 벤치 · `VARCHAR(n)` 감사 | **완료 (2026-08-21)** — self-test 통과 · 실측이 **D-209~D-214** 에 기록 · **제품 코드 diff 0** |
| **S2** ✅ | PostgreSQL Foundation | 앱 고유 70 테이블 PG 이식(도메인 변경 없음) · `0001_pg_baseline`(256 인덱스 + 부트스트랩 5행) · `is_write_conflict` 재분류(**실측 40 호출부**) · `SKIP LOCKED` · `jsonb` 37 컬럼 · 부분 유니크 **4건** · rowid 제거 · 공유 rate-limit/lock → **`--workers 4`** · Test Harness 2계층 · PG Backup/Restore 기본형 | **완료 (2026-08-21)** — SQLite Runtime 의존 0 · 전 회귀 PG 통과 · 동시성 시험 재작성분 통과 · 실측 정정과 발견은 **D-215~D-221** |
| **S3** ✅ | Product Identity · Hostname · TLS | nginx `server_name` · TLS 재발급(CN/SAN=`clovirassist.gooddi.lab`) · `APP_BASE_URL` · cookie domain · QA base URL · 프로브 TLS 검증 활성화 · 옛 호스트 하드코딩 테스트 2건 정정 | **완료 (2026-08-21)** — CN/SAN 일치 · `ssl_verify_result=0`(반례 18·1 함께) · 로그인/테마 유지 E2E 통과. 발견과 결정은 **D-222~D-224** |
| **S4** ✅ | **설치 · 배포 자동화 Foundation** | Remote 중립 Source · `deploy/install.sh` 단일 진입점(install·upgrade·rollback·uninstall·verify·version·preflight) · Preflight · Stage 0~18 · systemd **5유닛** + enable + 의존 순서 + PG 준비 대기 · Health · 실패 위치/원인 표시 · Idempotent · **옛 slug 이전(R13)** · 스케줄러 레인 분리(D-225) · 제품 정체성 정본 `app/core/product.py`(D-226) · LXD 리허설 · 실 재부팅 검증 | **완료 (2026-08-22)** — LXD 리허설 34항 전부 통과 · 실 커널 재부팅에서 수동 명령 0회 복구 (`boot_id` 변경 확인) · 리허설이 찾은 조용한 초록 넷을 함께 고침. 결정 **D-225~D-229** |

#### Phase B — 도메인

| S | 이름 | 핵심 산출 | Exit 조건 |
|---|---|---|---|
| **S5** ✅ | Identity & Access | `permissions`(32) · `roles`(builtin 5) · `role_permissions`(107) · `user_roles` · `resource_grants` · `departments`→`org_units` · **additive+fail-closed 상속**(Project Member 항 신설) · `effective_visibility_clause`(SQL·행 두 렌더러) · `confidential` 단일 축소 원시연산 · auth provider 추상화 · P-12a 범위 게이트 | **완료 (2026-08-22)** — 5역할 동등성 전수(표 + 실제 요청) · 두 렌더러 대조(자원 3 × 사람 5) · 부여/축소 음성 15건 · `check_visibility_single_source.py`(자기검증 5사례) · `KNOWN_GAPS` 0건. 결정 **D-230~D-235** |
| **S6** ✅ | Work Domain | `project_key_registry` · **Project Key 20건 확정(사용자 확인 완료 — [`PROJECT_KEYS.md`](PROJECT_KEYS.md), D-243)** · Ticket 3층 식별자 · `last_seq` 채번 · Relation · Comment · Attachment · Activity · Status/Workflow · Backlog rank · Sprint · Kanban · DnD 공통 · 낙관적 잠금 | **완료 (2026-08-22)** — 동시 12건에서 1..12 가 정확히 한 번씩(반례 포함) · 롤백 시 미소비 · `GIT-142` 가 Key 변경 뒤에도 같은 티켓 · Exception 임의 배정 0. 결정 **D-236~D-242**. Key 20건은 **확정됐고**(D-243) 적용 함수(`project_keys.apply_confirmed`)까지 섰다 — 실제 프로젝트에 붙는 것은 적재 이후라 S13 이다 |
| **S7** ✅ | Knowledge Domain | `knowledge_spaces` · `folders`(트리 — `path`·`depth` **트리거 파생**) · `documents` · `document_versions`(**Block JSON 정본**) · Version/Diff/Restore · `tags` · `document_relations` · `document_mentions` · Editor(TipTap MIT, route-level lazy) · **문자열 날짜 16컬럼 → `date`/`timestamp`(P-14a)** | **완료 (2026-08-22)** — 판이 쌓이고(같은 본문이면 안 쌓인다) 차이가 블록 단위로 나오고 되돌리기가 이력을 남긴 채 새 판을 만든다(낙관적 잠금 포함). 초기 번들 gzip **265KB → 265KB**(예산 280) — 편집기는 지연 청크 309KB. 결정 **D-244~D-248** |
| **S8** | File Storage Providers | `storage_providers` · Local/NFS/SMB Adapter · 마운트 유닛 · `st_dev` 가드 · 업로드 파이프라인 · **16항 실검증(NFS·SMB 각각)** | **16항 매트릭스 전부 실측 로그 첨부** · 미마운트 시 쓰기 거부 확인 |

#### Phase C — AI

| S | 이름 | 핵심 산출 | Exit 조건 |
|---|---|---|---|
| **S9** | AI Platform 1 — Gateway · Pipeline | `app/ai/gateway` contract/registry/adapters · 모델명 하드코딩 2곳 제거 · Parser(PDF/DOCX/PPTX/XLSX) · Chunk · Embedding · **`index` worker lane** · Index Lifecycle · Prompt Injection 경계 확대 | 생성 Adapter 비활성 상태에서 색인·임베딩 정상 · injection 회귀 |
| **S10** | AI Platform 2 — Retrieval · Citation · 생성 | Hybrid Retrieval(pg_trgm ⊕ FTS ⊕ pgvector, **RRF — Re-rank 없음, D-212**) · **권한을 LIMIT 앞에** · Citation 앵커 · AI 작업공간 · AI 문서 생성(`source_type=AI`) · **융합 가중치를 실제 relevance 로 재조정**(D-209 초기값에서 출발) · **실 본문으로 임베딩 모델 재검토**(D-211) | **권한 없는 사용자 질의 시 Context 미포함을 음성 테스트로 증명** · Citation 클릭 이동 · 생성 Provider 차단 시 검색/인용 계속 동작 |
| **S11** | n8n · 외부 Runner 제거 | 워크플로 Export 보관 · 잔여 로직 이관 확인 · n8n + 3 runner 서비스 정지·제거 · 포트/유닛/백업/테스트/문서 정리 · `validate-*.sh:23` n8n 단언 제거 | 5678/5679/8787/8788/8789 미청취 · 회귀 통과 · Installer 에서 n8n 흔적 0 |

#### Phase D — 운영 · 이관

| S | 이름 | 핵심 산출 | Exit 조건 |
|---|---|---|---|
| **S12** | Backup / Restore 운영 | Policy · Schedule · Retention · Manifest · 무결성(체크섬+`pg_restore --list`+임시 복원) · Local 다운로드 UX · NFS/SMB Backup Provider · Restore Validation · 동일 저장소 경고 | 복원 후 **앱 기동 + 읽기 경로 호출** 통과 · 파일 생성만으로 SUCCESS 안 됨 확인 |
| **S13** | Migration Tool + Dry Run | Extract(Notion+SQLite) · Transform · Validate · Load · Idempotent 재실행 · **임시 PG Dry Run** · Report · **Migration Exception 분류** · Project Key 적용 · 재채번 · `legacy_mapping` | Dry Run 무결성 전항 0(또는 Exception 분류) · 길이 초과 0 · legacy/canonical 충돌 0 |
| **S14** | **Cutover + Legacy 제거** (단독) | 최종 Backup → Maintenance → 마지막 Delta → PG 전환 → File/Relation/Application 검증 → AI Index → Open → **Notion·SQLite Runtime 차단** → Legacy 코드·문서·Harness 제거 | Notion/SQLite Runtime 의존 **0** · Legacy 잔존 0 · Rollback 지점 문서화 |

#### Phase E — UI Renewal 재개 (동결 해제, 각 Session 독립 종료)

| S | 이름 | 원 Wave | Exit 조건 |
|---|---|---|---|
| **S15** | Search/Filter **기능 정확성** — 새 PG Backend 대상 | W5B (REDEFINE) | C7 8단계 사슬이 전 Consumer 에서 PASS · 조합 필터 · 주소 복원 · page 리셋 · race · cache key |
| **S16** | Table / Grid / Metadata / Alignment + Chart | W6 | 4개 Table Assertion `--fail-on` 승격 초록 · C9 통과 |
| **S17** | Empty / Loading / Error / Feedback + Clovi + Detail Metadata | W7 | `mascot_visible_size` 초록 · 빈 데이터에서 차트·표·Pager 언마운트 |
| **S18** | Pilot Archetype 8종 — 새 IA 기준 | W8 (REDEFINE) | Pilot Exit Gate 9문항 + Functional Flow PASS |
| **S19** | 나머지 User Route | W10 (REDEFINE) | 각 화면 Functional Flow 가 최소 IN_PROGRESS |
| **S20** | Admin IA + Admin Console | W11 + W12 | 옛 주소 제자리 렌더 + query 보존 회귀 · 죽은 Action Finding 등록 |

#### Phase F — 최종

| S | 이름 | 원 Wave | Exit 조건 |
|---|---|---|---|
| **S21** | Functional E2E 전수 (27범주 + Backlog/Sprint/Board/Space/Citation/Storage) | W14 | C11~C14 통과 · `exists:true` Flow 에 `NOT_AUDITED` 0 |
| **S22** | Final Audit · **Full Capture(최초이자 유일)** · **설치 Acceptance 완주** · **S21 Evidence 재사용** | W15 | 이 문서 §10 + CLAUDE.md §11 + INSTALLATION §8 전 단계 |

### 9.2 Dependency

```
S0 → S1 → S2 → S3 → S4 ─┬→ S5 → ┬→ S6 ─┐
                        │       ├→ S7 ─┤→ S8 → S9 → S10 → S11
                        │              │
                        └──────────────┘
S11 → S12 → S13 → S14 → S15 → S16 → S17 → S18 → S19 → S20 → S21 → S22
```

- **S6 와 S7 은 S5 완료 후 병렬 가능**(서로 다른 도메인). S8 은 S7 이후(문서 첨부가 소비처)
- S4 가 S5 보다 앞인 이유: **이후 모든 Session 이 Installer 계약을 지려면 Installer 골격이 먼저
  있어야 한다**
- Phase E 는 순차다 — `kit.jsx`·`navConfig.js`·`DataScreen.jsx` 소유가 겹친다

### 9.3 검증 실행 경제 (D-208)

**우선순위**: S0~S22 의 실행·검증 규칙은 이 절과 D-208 이 정본이다.
`docs/ui-renewal/PLAN.md` 가 적어 둔 **과거 Wave 실행 규칙 중 「Wave 종료마다 전체 Regression」·
「전체 뷰포트 × 2테마 전량 Capture」 조항은 재개되는 S15~S20 에 적용하지 않는다.**
그 조항은 W0~W5 가 실제로 그렇게 실행했다는 **기록**이고, **W0~W5 의 완료 기록과 Evidence 는
그대로 둔다.** 앞으로의 Session 은 아래 E1~E10 을 따른다.

| # | 원칙 |
|---|---|
| **E1** | 같은 Source/Build 에서 **이미 PASS 한 비싼 검증은 반복하지 않는다.** 지문(`build_index_sha256` · `BUILD_STAMP.source_hash` · git commit)이 같으면 인용한다 — **인용할 때 지문을 함께 적는다** |
| **E2** | Source 변경 후에는 **변경 Domain → 관련 Integration → 영향 Route/Flow** 순으로 재검증한다. 일부 실패 시 **실패 범위부터** 다시 실행한다 |
| **E3** | Probe/Harness 결함은 **자체 검증(self-test·반례) 후 수정**한다. Probe 하나 고칠 때마다 Full Capture 하지 않는다 |
| **E4** | Installer 개발 중에는 **변경 Stage 만** 검증한다. Clean 설치·Reboot·Upgrade·Rollback Acceptance 는 **Source Freeze 후**(S22) |
| **E5** | S15~S20 UI 작업은 **변경 Surface 만** 검증하고 **필요한 최소 Reviewer 만** 쓴다 |
| **E6** | Reviewer Finding 수정 후 **전체 검증을 처음부터 반복하지 않는다.** 영향 범위를 우선 재검증한다 |
| **E7** | S21 의 Functional Evidence 를 **S22 에서 재사용한다.** S22 는 S21 전체 재실행이 아니다 |
| **E8** | Whole-product Full Capture 는 **S22 최종 빌드에서 1회만** |
| **E9** | 현재 Session 범위 밖 Finding 은 **Owner Session 으로 Routing** 할 수 있다. 단 **현재 변경이 만든 Regression 은 넘기지 않는다** |
| **E10** | **비용을 이유로 필수 안전/기능 검증을 생략하지 않는다.** 없애는 것은 중복 실행뿐이다 |

**어떤 경우에도 면제되지 않는 검증** — E1~E9 의 어떤 조항도 아래를 건너뛰는 근거가 되지 않는다.

- **권한/RBAC 음성 테스트** — 특히 AI Retrieval 이 권한 없는 데이터를 Context 에 넣지 않음 (S10)
- **Ticket 채번 동시성** — 중복 0 · 번호 연속 · 롤백 시 번호 미소비 (S6)
- **Migration 무결성** — 수량 · 누락 · 중복 · 변환 실패 · 깨진 Relation · 깨진 File Link (S13)
- **Backup 무결성과 복원 후 앱 기동 검증** (S12)
- **Storage 16항 매트릭스**와 미마운트 시 쓰기 거부 (S8)
- **Reboot 후 수동 명령 0회 복구** (S4 범위 · S22 전 제품)
- **Cutover 전 최종 Backup 과 Rollback 지점 확인** (S14)
- **Secret 노출 검사 · CSRF/Session 계약 · Prompt Injection 경계**

「이번엔 안 바뀌었으니 건너뛴다」는 **E1 의 지문 비교로 증명될 때만** 허용된다.

---

## 10. 완료 조건

**최종 완료는 S22 다.** 이 문서 §10 과 CLAUDE.md §11, 그리고 아래를 모두 만족해야 한다.

1. Source 기준 전체 Route 가 Coverage 에 존재 · UNKNOWN/TODO/NOT_AUDITED 0건 · Critical/High Finding 0건
2. **SQLite Runtime 의존 0 · Notion Runtime 의존 0 · n8n 흔적 0**(포트 5678/5679/8787/8788/8789 미청취)
3. **PostgreSQL 이 System of Record** — `DATABASE_URL=postgresql://…` 로 전 회귀 통과
4. **권한 없는 사용자 질의 시 해당 데이터가 AI Context 에 들어가지 않음을 음성 테스트로 증명**
5. **Ticket 채번**: 동시 부하에서 중복 0 · 번호 연속 · 롤백 시 미소비 · `GIT-n` 영구 resolution
6. **Migration 무결성 전항 0**(또는 Exception 분류) · 길이 초과 0 · legacy/canonical 충돌 0
7. **Backup**: 체크섬 → `pg_restore --list` → 임시 복원 → **앱 기동 + 읽기 경로 호출** 통과
8. **Storage 16항 매트릭스**를 NFS·SMB 각각에서 실행한 로그 · 미마운트 시 로컬 디스크에 안 쓰임
9. **설치 Acceptance 완주** — Clean Ubuntu 24.04 3줄 → 설치 → Health → **Reboot → 수동 명령 0회 복구**
   → 기존 데이터 정상 → Upgrade ([INSTALLATION.md](INSTALLATION.md) §8)
10. TLS CN/SAN = `clovirassist.gooddi.lab` 일치 · `ssl_verify_result=0`
11. Purple/Indigo Brand Identity · Clovi 검수 · 거대 Blank Canvas 0 · FHD/QHD/4K 및 Zoom 검증
12. Coverage Gate `--stage complete` PASS · 독립 Visual Reviewer PASS · 독립 Requirement Reviewer PASS
13. **Product-owned Source/Config/Artifact 에 Legacy Product Identity 잔존 없음**

**외부 Blocker 로만 남길 수 있는 것**: 실제 외부 권한·MFA·외부 제공 자격증명 부재.
「코드가 많다 · 오래 걸린다 · 테스트가 많다」는 미완료 항목을 남기는 근거가 아니다.

---

## 11. 검증 명령

```bash
# 정적 + 프로브 자기검증
bash scripts/static_checks.sh
python scripts/check_ui_renewal_coverage.py --stage wave

# 백엔드 회귀 (PostgreSQL)
DATABASE_URL=postgresql://clovirassist@127.0.0.1/clovirassist \
  bash scripts/run_full_regression.sh

# 프런트
cd frontend && npx vitest run

# 설치 — Clean Ubuntu 24.04 최초 3줄
sudo apt-get update && sudo apt-get install -y git ca-certificates
sudo git clone --branch v<VERSION> https://gitlab.<사내>/clovir/clovirassist.git /opt/clovirassist
sudo /opt/clovirassist/deploy/install.sh install \
     --dns-name clovirassist.gooddi.lab --bind-ip <IP>

# 설치 확인 / 버전 / 업그레이드
sudo /opt/clovirassist/deploy/install.sh verify
sudo /opt/clovirassist/deploy/install.sh version
sudo /opt/clovirassist/deploy/install.sh upgrade --ref v<VERSION+1>

# LXD Clean 설치 리허설 (테스트 서버 위, 34항)
sudo bash scripts/lxd_rehearsal.sh <source.tar.gz> s4-rehearsal

# Reboot 검증 — prep / reboot / verify 로 나눈다. 그 사이에 사람은 아무것도 하지 않는다
sudo bash scripts/reboot_check.sh prep <source.tar.gz> s4-reboot
sudo reboot
sudo bash scripts/reboot_check.sh verify   # boot_id 가 바뀌었는지부터 본다

# 손으로 볼 때 (index 는 S9 이후에 생긴다)
systemctl is-active postgresql nginx clovirassist-{privhelper,web,worker,scheduler}

# 배포 검증
BASE=https://clovirassist.gooddi.lab bash scripts/verify_deploy.sh

# 브라우저 QA (최종 1회)
python -m scripts.ui_qa.run --label final --fail-on <승격 클래스…>
```

---

## 12. Risk 등록부

| # | Risk | 영향 | 완화 | Owner |
|---|---|---|---|---|
| R1 | **`is_write_conflict` 가 PG 에서 진짜 제약 위반을 10회 재시도 후 503 으로 감춘다** | 데이터 버그가 "일시적 오류" 로 위장 | 재분류 + 115 호출부 전수 감사 + 음성 테스트 | S2 |
| R2 | **부분 유니크 인덱스 3개가 PG 에서 전체 유니크가 된다** | 승인 재요청·프롬프트 2차 버전·2회 offboarding 이 조용히 막힘 | `postgresql_where=` 명시 + 각각 회귀 테스트 | S2 |
| R3 | **약 40개 동시성 테스트가 거짓 초록이 된다** | 잠금 회귀를 못 잡음 | 재작성 + `qa-contract-replaced-by:` | S2 |
| ~~R4~~ | **Coverage Gate 가 Route 개편 시 조용히 통과한다** | — | **해소 (S1)** — 빈 결과 FATAL + 리더 표본 수 출력 + 배선 반례 (D-213) | 닫힘 |
| ~~R5~~ | 한국어 검색 품질 회귀 | — | **해소 (S1)** — `pg_trgm` GIN 이 어절 내부 부분일치 recall **1.000**, FTS `simple` 은 **0.083** (D-209) | 닫힘 |
| ~~R6~~ | CPU 임베딩/리랭킹이 예상보다 느림 | — | **확정 (S1)** — 리랭커를 **쓰지 않고** RRF 로 간다. 임베딩은 `e5-small` (D-211 · D-212) | 닫힘 |
| ~~R7~~ | 문자열 길이 초과로 Migration 실패 | — | **범위 확정 (S1)** — 선언 410 컬럼 중 초과 **1건**(`messages.message_id`), 대응은 «넓힌다» (D-214) | 닫힘 → S2 |
| R8 | Notion 본문 재수집 중 rate limit / 원본 변경 | 본문 유실 | Idempotent Tool + `last_edited` 기준 delta + 재실행 가능 | S13 |
| R9 | `assistant.py` 6,395줄 로직 이관 누락 | AI 기능 퇴행 | 293개 runner 테스트를 이관 대상 판별에 사용. 병행 운영 후 제거 | S9·S11 |
| R10 | Editor + DnD 도입이 번들 예산 초과 | 초기 로드 회귀 | route-level lazy load 강제 + `check_bundle_size.sh` 게이트 유지 | S7 |
| R11 | 시험 Storage 가 실 NAS 와 다르다 | 실 장비에서 새 결함 | U9 대로 **과장하지 않고** 명시. 실 정보 수령 시 Configuration 만 변경 | S8 |
| R12 | Cutover 후 부분 Rollback 만 가능 | Open 이후 입력분 유실 위험 | Open 직전 검증을 두껍게. Dry Run 반복으로 미리 소진 | S14 |
| ~~R13~~ | 제품 slug 가 경로·유닛·백업 루트에 박혀 있다 | **해소** | 호스트명·TLS 는 S3(D-222~D-224), 경로·유닛·시스템 계정·관리 콘솔이 보는 이름은 S4(D-226). Installer 가 새 slug 로 설치하고 **옛 설치를 이전한다** — 리허설이 「업로드·비밀이 따라오고 옛 경로·유닛·계정이 사라진다」를 확인했다. **남은 한 건은 세션 쿠키 이름**(`clovirone_session`)이고 바꾸면 전원 로그아웃이라 S14 로 넘겼다(P-33) | ~~S3~~ ~~S4~~ · P-33 |
| R14 | **설치 자동화를 마지막에 몰면 실패한다** | **골격 해소, 계약은 계속** | S4 가 골격을 세웠고 리허설로 확인했다. 남은 위험은 「이후 Session 이 자기 Component 의 Stage 를 안 넣는 것」이라 Stage 12·13 이 **소스에 Component 가 생겼는데 Stage 가 비어 있으면 FAIL** 을 낸다(D-227) — 문서가 아니라 스크립트가 §6.1 을 지킨다 | ~~S4~~ · S5~ |
| R15 | **LXD 컨테이너 리허설이 실 VM 과 다르다** | **절반 해소** | 재부팅 축은 닫혔다 — 이 서버에 `/dev/kvm` 이 없어 LXD VM 을 못 써서 **테스트 서버 자체를 재부팅**했다(D-229). **Storage(NFS/SMB)는 여전히 컨테이너에서 검증되지 않는다** — S8 의 실 검증 몫이고, 컨테이너 통과를 "설치 검증 완료" 라고 쓰지 않는 규칙은 그대로다 | ~~S4~~ · S8 · S22 |
| R16 | GitLab Repository 가 아직 없다(현 origin=GitHub) | **완화** | Installer 가 Remote 중립으로 완성됐다 — `--git-remote`/`--ref` 를 받고 없으면 `installed_manifest.json` 에서 읽는다. `--source local|bundle` 로 오프라인 경로도 그대로다(리허설이 `local` 경로로 돈다). 주소가 정해지면 **설정만** 바꾼다 | 외부 입력 대기 |
| R17 | pgvector 0.6.0 의 검색 품질/지연이 요구에 못 미칠 수 있다 | 검색 체감 저하 | **Version 결정(D-188)은 확정이고 이 Risk 의 대상이 아니다.** 인덱스 파라미터와 하이브리드 가중치로 대응 | S1·S10 |
| R18 | Ticket canonical_key Trigger 가 대량 UPDATE 에서 느릴 수 있다 | Project Key 변경 시 지연 | Key 변경은 드문 명시적 Migration 동작. 프로젝트당 최대 416건이라 실질 영향 없음. 트랜잭션 시간 측정·기록 | S6 |

---

## 13. 외부 Blocker / 결정 대기

| 항목 | 성격 | 처리 |
|---|---|---|
| 실 NFS/NAS 장비 정보 | 현재 없음이 **확인됨** | **Blocker 가 아니다.** 시험 Storage 로 실검증하고, 실 정보 수령 시 Configuration 만 변경 |
| ~~20개 Project Key 명명~~ | **해소 (2026-08-22)** | 초안표 그대로 확정 → [`PROJECT_KEYS.md`](PROJECT_KEYS.md) · **D-243**. 정본은 `app/work/project_keys.py::CONFIRMED` 이고 적용은 S13 이 적재 직후에 한다 |
| **제품 Domain 밖 Notion DB 3종** (오라클 버그수정 179 · 휴일근무 23 · 교육 9) | **Core Migration 과 분리된 별도 결정사항** | 기본값 = 이관하지 않음. Core Migration 은 이 결정과 무관하게 진행 |
| GitLab Repository 주소·자격증명 | 외부 제공 필요 | **없어도 S4 는 진행한다**(Remote 중립 + 오프라인 Bundle). 주소 수령 시 설정 반영 |

---

## 14. UI · IA 목표와 W5B~W15 재배치

### 14.1 목표 IA

```
대시보드
프로젝트   개요 · 티켓 · 백로그 · 보드 · 스프린트 · 문서 · 설정
티켓       전체 티켓 · 내 티켓
문서       전체 문서 · 지식공간 · 내 문서 · 즐겨찾기 · 최근 문서 · 휴지통
AI         새 대화 · 지식 검색 · 작업공간 · 생성 기록
사용자 관리 사용자 · 조직 · Role · Permission
시스템     일반 설정 · File Storage · AI 설정 · Backup 및 Restore · 작업 이력 · 감사 로그 · 시스템 상태
```

### 14.2 재작성 / 신설 / 유지

| 재작성 (Notion 모양) | 신설 (지금 0%) | 유지 (앱 고유, 재스킨 이하) |
|---|---|---|
| `/my-tickets` `/unassigned` `/new-ticket` `/team-tickets` `/tickets/:id` | Kanban Board | Shell · navConfig · CommandPalette |
| `/team-docs` `/team-docs/:id` `/team-docs/trash` | Backlog | `lib/api.js` · auth · error envelope |
| **모든 `MirrorNotice` 소비처** (동기화 배너·"지금 동기화" 6곳) | Sprint 엔티티 | `theme.js` · `kit.jsx` · `charts/*` · tokens |
| `/sprint` (지금은 마감일 집계) | Knowledge Space · Folder 트리 | `DataScreen` + registry 27/28 |
| `/projects` `/projects/:id` 의 Notion 지층 | Ticket Relation UI | `/chat` · prompts · policies · templates |
| `/notion-mapping` · NotionConsole · Notion 설정키 | Project Member 관리 화면 | `/board` `/ideas` `/chat-rooms` `/games` |
| `/backup` `/restore-drills` (SQLite 모양) | DnD 인프라 · Rich Editor | `/users` `/organizations` `/rbac` `/audit` … |

**수동 동기화 UI 제거**(D-207 / S6·S7): 일반 사용자 화면의 수동 동기화("지금 동기화") 6곳은
**동기화 개념 자체가 사라져** 자동으로 제거된다.

### 14.3 W5B~W15 재배치 (D-207)

**즉시 동결.** 판정 확정은 새 IA 가 실재한 뒤(S10 종료 시점)에 하고, 실행은 Phase E 에서 한다.

**재개 시 실행 규칙은 §9.3(D-208)이 우선한다.** S15~S20 은 **영향 Surface/범위만** 검증하고
자기가 건드린 Surface 만 재캡처한다. Whole-product Full Capture 는 **S22 최종 빌드에서 1회**다.
Wave 별 전체 Regression·전량 Capture 를 반복하지 않는다.

| Wave | 원래 내용 | 판정 | 재배치 |
|---|---|---|---|
| **W5B** | Search/Filter 기능 정확성 (C7 8단계 사슬) | **REDEFINE** — 목적 보존, 대상 교체 | **S15 단독.** Legacy Notion Query 가 아니라 **새 PG Project/Ticket Query 와 Relation** 대상 (U7) |
| W6 | Table/Grid/Alignment + Chart + Property Editing | **KEEP**(공유 부품) + **MERGE**(Inline Edit 는 Ticket 도메인) | **S16 단독** |
| W7 | Empty/Loading/Error + Clovi 크기 + Detail Metadata | **KEEP** | **S17 단독** |
| W8 | Pilot 8종 end-to-end | **REDEFINE** — Pilot 집합을 새 IA Archetype 으로 교체 | **S18 단독** |
| W9 | 티켓/문서/채팅 Workflow + 수동 동기화 제거 | **MERGE into S6·S7** + **REMOVE**(동기화 개념 소멸로 자동 해소) | S6·S7 흡수 |
| W10 | 나머지 사용자 Route | **REDEFINE**(Route 집합 자체가 바뀜) | **S19 단독** |
| W11 | 관리자 IA | **REDEFINE**(§14.1 IA 로 교체) | **S20** |
| W12 | 관리자 Console 44 Surface | **REDEFINE** — Notion/SQLite 화면 제거 후 재산정 | **S20** (W11 과 `navConfig.js`·`AdminRoutes.jsx` 를 공유해 분리하면 충돌한다 — 이 묶음만 예외로 합친다) |
| **W13** | Identity + Hostname + TLS | **MOVE — 맨 앞으로** | **S3 단독.** 이후 모든 캡처 증거가 한 origin 으로 남아야 한다 |
| W14 | Functional E2E 27범주 전수 | **KEEP + 확장**(Backlog·Sprint·Board·Space·AI Citation·Storage) | **S21 단독** |
| W15 | Whole-product 재감사 | **KEEP + 확장**(설치 Acceptance 포함) | **S22 단독** |

**W0~W5 자산 보존**: `theme.js` · `kit.jsx` · `FilterBar`/`filters.jsx` · `EntityCombobox` ·
`navConfig` · Control Plane 3종 · Assertion 34종 · `probe_selftest.py` · 프런트 테스트 전량.
**폐기하지 않는다.**
