# INVENTORY 07 — Notion 원본

**정본**: 실 Notion Workspace (API 조회)
**측정**: 2026-08-20 — **읽기만 했다.**

> **Token 은 이 문서에도, 저장소 어디에도 적지 않는다.** 아래 id 는 워크스페이스 객체 식별자이지
> 자격증명이 아니다.

## 가시 객체

**1,522개 = 데이터베이스 8 + 페이지 1,514**

| Notion DB | id | 행 | 이관 |
|---|---|---|---|
| **작업**(Tasks/Tickets) | `262c5c5a-5684-81fa-…558d` | **1,119** | ✅ 정본 |
| **프로젝트** | `262c5c5a-5684-8108-…f9a7` | **21** | ✅ 정본 |
| **문서** | `262c5c5a-5684-8110-…5487` | **110** | ✅ 정본 |
| 문서 유형 | `262c5c5a-5684-811b-…2c40` | 15 | ✅ 분류 taxonomy |
| 카테고리 | `262c5c5a-5684-812f-…eb86` | 11 | ✅ 분류 taxonomy |
| 오라클 버그 수정 | `3adc5c5a-…` | 179 | ⚠️ **제품 밖 — 별도 외부 결정** |
| 휴일 근무 지원내역 | `26bc5c5a-…` | 23 | ⚠️ **제품 밖** |
| 교육 커리큘럼 | `296c5c5a-…` | 9 | ⚠️ **제품 밖** |
| (운영 설정이 가리키는 문서 DB) | `55efc3c0-…152c` | **0** | ❌ **빈 껍데기** |

## 지금 동기화가 왜 실패하는가

`app_settings.notion_tasks_database_id` 가 **문서 DB id**(`262c5c5a56848110bdafde605ac15487`)를
가리키고 있고, `notion_documents_database_id` 는 **어느 실재 DB 와도 맞지 않는다**.
`config_versions` 24행과 `audit_logs` 가 2026-08-20 02:44~04:01 의 시행착오를 그대로 남기고 있다.

**그 사이 "Notion 연결 테스트" 는 매번 통과했다** — 토큰만 검사하고 DB 가 맞는지는 안 보기 때문이다.
이 전환 이후 이 실패 모드는 **개념째 사라진다.**

## 이관 물량 — 예상보다 훨씬 작다

| 항목 | 실측 |
|---|---|
| 작업 첨부파일 | **4개** (2행) |
| 문서 첨부파일 | **5개** (4행) |
| **첨부 총계** | **9개** — 파일 이관은 사실상 문제가 아니다 |
| 티켓 본문 블록 | 10건 표본 31블록 → 티켓당 **~3블록** |
| 문서 본문 블록 | 10건 표본 **382블록** → 문서당 **~38블록** (bulleted_list 127 · paragraph 93 · **code 46** · heading 56 · divider 28 · table 6 · image 2 · file 1) |
| 예상 본문 API 호출 | 티켓 1,119 + 문서 110 = **~1,230회** (3 req/s 제한 시 ~7분) |
| 댓글 | 15건 표본에 1건 — 사실상 없음 |
| Notion 사용자 (API 가시) | 4명 (person 2 + bot 2) — 그러나 작업 속성의 person id 는 **16종** |
| 티켓 번호 | `unique_id` prefix **`GIT`**, 27~1536 |

## 작업 DB 속성 → 목표 도메인

| Notion 속성 | 타입 | 목표 |
|---|---|---|
| `제목` | title | `tickets.title` |
| `티켓 ID` | unique_id (`GIT-n`) | `legacy_key` 보존 + 새 `<KEY>-<SEQ>` |
| `진행상태` | status (계획/이슈/검증/진행/완료/취소) | `ticket_statuses` + `category` |
| `우선순위` | select (높음/중간/낮음) | `tickets.priority` |
| `난이도` | select (1~6) | **유지** — 실사용 확인됨 |
| `예상 WD` / `실제 WD` | number | `estimate_wd` / `actual_wd` — **버리면 Sprint 번다운과 Dev Report 가 죽는다** |
| `시작일` / `마감일` | date | `start_date` / `due_date` |
| `대분류` | rich_text | `tickets.category` |
| `티켓 담당자` | people | `ticket_assignees` (M:N) |
| `프로젝트` | relation | `tickets.project_id` (FK) |
| `상위 작업` / `하위 작업` | self-relation | `ticket_relations(parent/child)` |
| `티켓 선택(선행/후속)` | self-relation | `ticket_relations(blocks/blocked_by)` |
| `파일과 미디어` | files | `attachments` |
| `다중 선택` | multi_select (옵션 **0개**) | **폐기** — 빈 속성 |
| `텍스트` | rich_text | 용도 불명 — 실데이터 확인 후 최종 판정 |

## Notion 모양이 도메인에 새어 든 자리 — 재설계 근거

- **page-id 가 곧 API 의 `id` 다.** `ticket_view()` 가 `"id": t.page_id` 를 반환하고, 딥링크·휴지통·
  감사·문서 댓글·즐겨찾기·최근 열람이 전부 `notion_page_id` 를 키로 쓴다.
  `document_cache.notion_page_id` 는 **NOT NULL** — Notion 페이지 없이는 문서가 존재할 수 없다
- **속성이 곧 폼이다.** 티켓 생성/수정 폼의 허용값이 요청 시점 Notion 스키마 조회에서 나온다.
  앱은 상태·우선순위·난이도의 **자기 어휘를 갖고 있지 않다**
- **CSV 문자열 관계.** `ticket_cache.project_ids`/`project_names`/`assignee_notion_ids`,
  `document_cache.author_notion_ids`/`type_names`/`category_names`/`project_names` 가 전부 구분자로
  이어붙인 TEXT 다 — **FK 검사에 안 걸리는 "soft" 참조**다
- **Notion API 한계가 도메인 검증이 됐다.** `MAX_BLOCKS=100`·`MAX_LINE_CHARS=1900` 이
  `BODY_MAX_LINES` 로 재수출돼 **본문 길이를 거절한다**
- **낙관적 잠금이 Notion 페이로드 해시다** (`notion_version`/`base_notion_version` — 공개 API 필드)
- **Sprint 는 정의돼 있지 않다.** `notion_sprint_database_id` 를 읽는 코드가 없고, 화면의 "이번 주" 는
  마감일 범위 집계다. 화면 자체가 "이건 팀의 Notion 스프린트가 아니다" 라고 설명한다
- 삭제가 도메인 이벤트가 아니라 Notion 이벤트다(`notion_missing_at` + 유예 후 정리)
- 감사 object_type 이 Notion 명사다: `notion_task` · `notion_document` · `notion_token`

## 토큰은 어디 있나 (S1 확인 · 2026-08-21)

**값은 이 저장소에 없고 앞으로도 없다.** 코드는 **secret-ref** 로 다룬다 — 설정이 들고 있는
것은 파일 **이름**이고(`app/core/config.py`: `secrets_dir` · `notion_report_token_ref` ·
`notion_docs_token_ref`), 값은 그 이름의 파일에서 읽는다. `OutboundClient` 단일 관문이
그 참조를 주입한다(MASTER_PLAN §2.2).

| 위치 | 파일 | 권한 |
|---|---|---|
| **운영 (정본)** | `/etc/clovirone-web-assistant/secrets/{notion_docs_token, notion_report_token}` | `root:clovirone-web` **0640** — 읽으려면 sudo |
| 개발 기계 | `var/secrets/{notion_docs_token, notion_report_token}` (`secrets_dir` 기본값) | `.gitignore` 의 `var/` 로 제외 · **git 미추적 확인** |

같은 디렉터리에 `assistant_runner_token` · `game_runner_token` 도 있다.

### 네 파일은 **같은 토큰**이다 — 통합은 하나다

sha256 대조(값은 찍지 않는다). 파일 크기가 갈리는 이유는 **끝의 개행 하나**뿐이다:

| | `notion_docs_token` | `notion_report_token` |
|---|---|---|
| 개발 `var/secrets/` | `2abdd8cd…` (50 B, 개행 없음) | `2abdd8cd…` (50 B) |
| 운영 `/etc/…/secrets/` | `4f24558f…` (51 B = **같은 값 + 개행**) | `2abdd8cd…` (50 B) |

`FileSecretReferenceProvider.get()` 이 `read_text().strip()` 을 한다
(`app/core/secret_refs.py`). **개행은 런타임에서 무의미하고, 네 파일은 전부 같은 값을 준다.**

즉 이 설치는 **Notion 통합 하나**를 두 ref 이름으로 나눠 쓰고 있다. 문서 쪽과 리포트 쪽을
서로 다른 통합으로 분리할 계획이 있다면 그건 **설계 결정이지 지금의 결함이 아니다.**

> **이 절은 한 번 틀렸다가 정정됐다.** 처음엔 파일 크기와 원시 해시만 보고
> 「개발 사본의 `notion_docs_token` 이 틀렸다」고 적었다. 공백을 정규화하지 않고 비교했기
> 때문이다 — `scripts/ui_qa/README.md` 가 적어 둔 그 규율(**첫 «위반» 은 위양성부터
> 의심한다**)을 지키지 않은 자리다. **해시를 비교하기 전에 소비자가 값을 어떻게 읽는지
> 먼저 본다.**

> 토큰 **유효성**은 다시 재지 않았다 — 「Notion 연결 테스트는 매번 통과한다」가 이미
> 실측으로 기록돼 있고(§1), 동기화 실패의 원인은 토큰이 아니라 **DB id 오설정**이다.
> 확인이 다시 필요해지는 시점은 S13 이 실제로 본문을 읽을 때다.

## 속성 이름을 다시 쟀다 (2026-08-23 · S13) — 옛 상수는 문서 DB 에서 하나도 안 맞았다

위 「작업 DB 속성」표는 그대로 유효하다. **문서 DB 와 프로젝트 DB 는 아니었다.**
`app/team_docs/notion_docs.py` 가 찾는 이름이 지금 워크스페이스에 없다.

| 우리가 찾던 이름 | 실제 이름 | 값이 있는 행 |
|---|---|---|
| `제목` | **`이름 `** (끝에 공백) | 108 / 110 |
| `유형` | **` 유형`** (앞에 공백) | 93 |
| `카테고리` | **` 카테고리`** | 61 |
| `프로젝트` | **`프로젝트 선택`** | 34 |
| `상태`(select) | **`상태 `** — 타입도 `status` 다 | 110 |
| `소유자` · `메모` · `즐겨찾기` · `보관됨` | 전부 앞뒤에 공백이 붙어 있다 | 5 · 1 · 110 · 110 |
| `원본 생성일` · `원본 URL` | **없다.** 대신 ` 출처`(url)가 있고 그마저 110행 전부 비어 있다 | 0 |
| 첨부 | `첨부파일 `(끝 공백)**와** `파일과 미디어` **둘 다** | 9 |

프로젝트 DB 도 같다: 제목은 `프로젝트`, 담당자는 `담당자(정)`, 진행률은
**`프로젝트 진행률`(formula)** 이라 `prop["number"]` 만 보면 언제나 `None` 이다.
`사업 구분`·`제품/품목`·`기간`·`요약` 은 21건 전부 값이 있는데 미러에는 안 들어와 있었다.

**이것이 [`05_DB.md`](05_DB.md) 가 기록한 「`type_names` 110건 전부 빈 문자열」의
원인이다.** Notion 은 이름이 안 맞을 때 오류를 내지 않는다 — 그냥 그 키가 없는 응답을
준다. 그래서 동기화는 매번 성공했고 분류만 조용히 비어 있었다. 대응은 **D-277** 이다.

작업 DB 에서 새로 쓰기 시작한 속성 둘: `티켓 선택(선행 작업)` 30건 ·
`티켓 선택(후속 작업)` 26건 → `ticket_relations(blocks)` 45변.

## 미확인 항목과 Owner

**없다.** 이 목록은 **S13 Migration Tool 의 입력으로 그대로 쓴다.** 재조사하지 않는다.
단 본문 재수집 시 `last_edited` 기준 delta 로 **재실행 가능해야 한다** (R8 — S13 이 닫았다).
