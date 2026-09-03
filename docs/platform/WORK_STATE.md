# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-09-04** (문서 기능 개편 + Notion 정상화 + Confluence 가져오기 —
  D-416~D-425)
- phase: **F — Acceptance 완료(S22) 뒤의 일반 개발**(CLAUDE.md §7.0)
- session: **「문서 기능을 이렇게 바꿔라」 23개 항목.** 화면의 축을 넷으로 세우고, 템플릿을
  실제로 관리할 수 있게 하고, Notion 원본으로 기존 문서를 복구한 뒤 Confluence 두 Space 를
  가져와 기존 AI 검색 구조로 전부 찾을 수 있게 하는 일이다.

  ① **「문서 범위」의 정체는 프로젝트 축이었다.** 주소도 `?project=`, API 도 `project_id`
  였고, 그 이름이 생긴 이유는 후보에 「공통 문서」가 섞여 라벨이 거짓말을 했기 때문이다
  (D-415). 그 값을 **「프로젝트 미지정」**이라 부르니 축 이름이 정직해졌고 우회 이름이
  필요 없어졌다 — D-416. 주소·API 매개변수는 **안 바꿨다**(북마크·목록 복귀 기억·서버
  계약 셋이 그 값을 쓴다).
  ② **폴더는 화면에서만 걷었다** — D-417. 좌측 트리(`KnowledgeNav.jsx`)를 지우고 새 문서·
  이동 대화상자의 폴더 칸, 목록의 폴더 열, 조건 칩, `?folder=` 를 걷었다. 표·트리거(0004)·
  `folder_id`·엔드포인트 넷·응답의 `folder_path` 는 **전부 남는다.** 되돌리기가 화면 파일
  하나여야 한다.
  ③ **프로젝트가 선택이 됐다** — D-418. 안 고르면 서버가 조직 공통 공간을 찾거나 만든다
  (`resolve_or_create_common_space`). 🔴 그 함수가 `owner_kind='organization'` 을
  **단언한다** — `unset` 이면 그 문서는 전역 조회 권한자 말고는 아무에게도 안 보이고,
  실측에서 문서 110건이 그렇게 사라진 적이 있다. slug 를 먼저 찾는 것도 계약이다(소유
  갈래로만 찾으면 운영의 `team-docs` 와 부딪혀 409 가 난다).
  ④ **필수 분류·태그는 대화상자에서만** 막는다 — D-419. 서버에서 강제하면 AI 초안·문서
  복원·이관·Import 가 전부 422 로 죽는다.
  ⑤ **「최근 24시간」이 진짜 창이 됐다** — D-420. 예전 타일은 `sort=recent` 만 걸어 전체를
  정렬만 했다. 타일과 목록이 `recently_updated_since` 한 함수를 함께 쓴다.
  ⑥ **템플릿이 표가 됐다**(0027) — D-421. `documents` 에 `template_id` 를 **안 붙인다**:
  연결이 없으면 「고쳐도 기존 문서가 안 바뀐다」가 코드가 아니라 스키마다. 「빈 문서」만
  표 밖의 상수로 남는다.
  ⑦ 🔴 **제목만 바꾼 저장이 AI 색인을 안 건드리던 구멍을 막았다** — D-422. `snapshot()` 이
  본문 동일 시 `None` 을 주어 신호를 안 보내고 `sweep_stale` 의 조건 넷에도 제목이 없는데,
  제목은 **첫 청크 본문에 들어간다.** 이름을 바꾼 문서가 옛 이름으로 영원히 검색됐다.
  신호 자리를 `versions.mark_stale` 하나로 모았다(`attachments.py` 의 사본을 접었다).
  ⑧ **Notion 복구의 원인을 찾았다.** 컷오버(2026-08-23 03:52)가 돈 커밋 `3cdab1e0` 의
  `transform.py` 는 catch-all `else` 로 `[원본에서 확인: table]` 을 적었고, 04:01 직후
  커밋이 표·이미지 변환을 넣었다 — **고침은 이미 HEAD 에 있고 운영에 다시 적재된 적이
  없다.** 캐시된 블록에 HEAD 를 돌린 실측: 110/110 정규화 통과, **표 93개·이미지 49개**가
  되살아난다(감사 도구가 「잃었다」고 적은 바로 그 수다).
  ⑨ **importer 가 지금 깨져 있었다.** `discover()` 는 제목으로 `/v1/search` 를 뒤지는데
  오늘 search 는 작업·프로젝트만 돌려준다 — 문서·문서 유형·카테고리는 안 나온다.
  `--database role=id` override 로 푼다(이미 있는 플래그다). 다섯 id 를 실측으로 확인했다.
  ⑩ **Confluence 는 ADF 로 읽는다** — D-423. 두 Space(CMP 312 + ClovirONE 212 = **524쪽**,
  보관 5·블로그 0)를 전량 변환해 봤다: **524/524 정규화 통과, 표 179·이미지 978, 버린
  내용 0.** 빈 본문 99건은 전부 원본이 빈 장이다(직접 갈라서 확인했다). 회차 끝에 **원본 수
  대조 게이트**가 선다 — 「전부 가져왔다」가 주장이 아니라 증명이어야 한다.
  ⑪ **첨부 상한 3MB 는 제품 업로드 상한(10MB)과 다른 값이고 다른 뜻이다** — D-424.
  큰 파일 하나가 문서 전체를 실패시키지 않는다. Confluence 는 목록의 `fileSize` 로 받기
  전에 거르고(1,458개 중 7개), Notion 은 받은 뒤 거른다.
  ⑫ **이관 문서의 프로젝트·분류·태그는 사람이 읽는 파일을 지난다** — D-425.
  원본이 못 미덥다(Notion 110건 중 프로젝트 관계는 34건뿐, Confluence 에는 그 축이 없다).
  `classify --emit` 이 판정·근거·후보를 적은 jsonl 을 만들고 `--apply` 가 그것만 읽어 쓴다.
  판단이 안 서면 **비운다.**
  ⑬ 🔴 **자체 작성 문서 보호는 두 자리에 있다.** 적재기(`legacy_page_id` 가 없어 조회에
  안 걸린다)와 **분류 적용기**(술어를 다시 건다). 한 자리에만 두면 그 자리를 안 지나는
  경로가 언젠가 생기고, 적용기가 바로 그런 경로였다. 제목이 같은 반례로 두 경로를 다 잰다.
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — 이번 회차도 안 옮긴다.
- deployed: **`53590e29`** 그대로다. **이번 회차는 아직 배포 전이다.**
- verification: 로컬 전량.
  **프런트** vitest 380파일 2,913시험 — 2,911 초록, 실패 2건은 병렬 부하 타임아웃이고
  단독 실행은 초록(`editable-body-identity-reset` · `donut-empty-state-height`).
  **백엔드** 문서·지식·이관·AI 표적 299 초록 + 신규 4파일(템플릿 5 · 프로젝트 선택 12 ·
  Confluence 9 · 자체 문서 보호 8) 초록. **정적** dev 전량 초록.
  **실데이터 실측**(쓰기 없음): Notion 110쪽·Confluence 524쪽 전량 변환.
- capture: 전량 정본은 **`s22-final`** 그대로다(D-306).
- ui_gate: 변화 없음.

## 🔴 다음에 할 일 — 운영 데이터 반영은 아직 안 했다

코드는 끝났고 검증도 끝났다. **남은 것은 운영에서 도는 세 걸음**이고, 순서가 계약이다.

1. **배포** — `sudo deploy/install.sh upgrade` (alembic head 가 `0026` → **`0027`** 로
   올라간다). 이 명령이 복원 지점도 만든다.
2. **Notion 복구** — 먼저 `--dry-run`.
   ```
   python -m app.cli.migrate_cli reimport-bodies --cache var/migration-cache \
     --scope documents --report var/recovery/notion --dry-run \
     --database documents=262c5c5a-5684-8110-bdaf-de605ac15487 \
     --database doc_types=262c5c5a-5684-811b-86f3-fd88af5a2c40 \
     --database categories=262c5c5a-5684-812f-8bfb-dea96dcceb86 \
     --database tasks=262c5c5a-5684-81fa-9697-ee5691cb558d \
     --database projects=262c5c5a-5684-8108-a949-c4503dd5f9a7
   ```
   판정은 `REIMPORT_OK` 줄이 아니라 `scripts/audit_migration_fidelity.py` 의
   **`FIDELITY_OK`** 다. 임계값: 자리표시자 0 · 표 93 · 이미지 49 · 빈 본문 ≤ 7.
3. **Confluence 가져오기** — `python -m app.cli.migrate_cli import-confluence --dry-run`
   으로 수를 먼저 보고, 그다음 실행. 원본 수 대조 게이트가 524 를 확인한다.
4. **분류** — `classify --emit` → **사람이 검토** → `classify --apply`.
5. **색인** — `python -m app.cli.ai_cli reindex` 로 대기 0 까지, 그리고
   `POST /api/search/reindex`.
   AI 색인(`document_chunks`)은 훑기의 「상태 행이 없다」 갈래가 가져온 문서를 알아서
   집어 간다. ⌘K 색인(`search_documents`)은 다르다 — `owner_kind`·분류·태그를 **행에
   복사**하므로 프로젝트를 옮기면 낡는다. 워커가 **300초마다** 전량 재구축하므로 결국
   스스로 낫지만(`settings.search_index_interval_seconds`), 그 5분을 기다리지 않으려면
   위 요청을 한 번 부른다.

되돌리기는 `sudo /home/cloviradmin/clovirassist-upgrade/deploy/install.sh rollback
--target <스냅샷>` 하나다. DB 만 복원하면 첨부 교체가 지운 바이트 때문에 행이 없는 파일을
가리킨다.

## 이번 회차가 **안 고친** 것 — 그리고 그 이유

- 🔴 **티켓 본문 약 1,120건에 같은 자리표시자가 남아 있다.** 이번 요구는 문서라
  `--scope documents` 로 제외했고, 회차가 그 사실을 Finding 으로 적는다. 같은 회차에 함께
  고치면 되돌릴 수 없는 변경의 범위가 열 배가 된다 — **P-78** 로 남긴다(지시가 있으면 한다).
- **Notion 블록 깊이 상한(`_MAX_BLOCK_DEPTH = 3`)은 안 올렸다.** 캐시가 그 한도로
  만들어졌고 감사 목표치도 그 캐시에서 나오므로, 「원본보다 적다」를 재려면 한도를 올려
  **별도 캐시**로 재추출해 대조해야 한다. 운영 복구 앞에 도는 읽기 전용 단계다 — **P-79**.
- **`["doc-comments", id]` 질의 키가 `["knowledge", …]` 접두 규칙을 어긴다.** 이번 변경과
  무관한 기존 상태이고 `invalidateDocumentViews` 가 그 키에 못 닿는다 — **P-80**.
- 🔴 **`test_login_visual_contract::test_pointer_tracking_is_limited_to_resting_states` 가
  HEAD 에서 이미 빨간불이다.** 직전 회차(⑦)가 시선 버그를 고치며 `clovi-login.js` 의
  `POINTER_TRACKED_STATES` 에 `email` 을 더했는데 시험은 아직 `["idle","welcome"]` 을
  요구한다. 이번 변경은 `app/static/js` 를 한 줄도 안 건드렸다(`git diff HEAD` 로 확인).
  둘 중 어느 쪽이 옳은지는 그 회차의 결정이라 여기서 정하지 않는다 — **P-81**.
- **P-44 · P-54~P-56 · P-59 · P-61~P-77** — 그대로다.

## 🔴 운영이 PostgreSQL 위에서 돈다

`10.100.64.71` 의 `/healthz` 가 `{"status":"ok","ticket_source":"native"}` 로 답한다.
원장은 [`EVIDENCE/S14/`](EVIDENCE/S14/README.md).

## 완료

- **S0~S22** — 기반 · PostgreSQL · Identity/TLS · 설치 자동화 · RBAC · Work · Knowledge ·
  Storage · AI 1·2 · n8n 제거 · Backup/Restore · Migration · Cutover · Functional E2E ·
  Final Audit. 결정 D-187~D-334.
- **화면 고도화 · 대시보드 · 무한 스크롤 · 서버 필터/정렬 · 티켓 만들기 · 신호 축 ·
  3영역 재설계 · 카테고리 · 엑셀** ✅ — D-335~D-406.
- **작업 보드·스프린트 회의·문서 결함 전수 수정 + 429 근본 해소 ✅** — D-407~D-412.
- **3라운드 운영 실화면 재검수 ✅** — D-413~D-415. 배포 `c3c2e195`.
- **문서 기능 개편 + 외부 문서 정상화 — 코드 ✅ / 운영 데이터 ⬜** — 이번 회차, D-416~D-425.

## BLOCKERS

- 없음. Confluence 자격증명은 확보했다(`var/secrets/confluence_token`, gitignore).
