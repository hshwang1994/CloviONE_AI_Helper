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
  ⑧ 🔴 **Notion 본문은 이미 고쳐져 있었다 — 그리고 그것을 재 보고 계획을 바꿨다.**
  컷오버가 돈 커밋의 `transform.py` 는 자리표시자를 적었고 직후 커밋이 표·이미지 변환을
  넣었다. 그래서 「운영에 다시 적재된 적이 없다」고 판단하고 110건 재적재를 계획했는데,
  **운영을 재 보니 아니었다**: 현재 판의 자리표시자 0, `tableRow` 558개, 그리고 살아
  있는 Notion 원본과 글자 수를 문서마다 대조해 **비율 1.016**(원본 277,058 : 운영
  281,420). 부족한 것은 **한 건뿐**이고 원인은 블록 깊이 상한이었다.
  계획대로 돌렸으면 바꿀 이유가 없는 109건을 바꿨다. 아래 「운영 실측」 절에 수를 적었다.
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
- deployed: **`a3b05cd2`** 가 운영에 나갔다 (2026-09-04 07:31 · **전체 업그레이드 경로** —
  마이그레이션이 낀 회차다). `VERIFY_OK` · `UPGRADE_OK` · 스냅샷
  `/var/backups/clovirassist/20260904-073154` · alembic **0026 → 0027**(db=code) ·
  제품 유닛 5종 active · `ssl_verify_result=0`.
- verification: 로컬 전량.
  **프런트** vitest 380파일 2,913시험 — 2,911 초록, 실패 2건은 병렬 부하 타임아웃이고
  단독 실행은 초록(`editable-body-identity-reset` · `donut-empty-state-height`).
  **백엔드** 문서·지식·이관·AI 표적 299 초록 + 신규 4파일(템플릿 5 · 프로젝트 선택 12 ·
  Confluence 9 · 자체 문서 보호 8) 초록. **정적** dev 전량 초록.
  **실데이터 실측**(쓰기 없음): Notion 110쪽·Confluence 524쪽 전량 변환, 그리고 배포
  뒤 **운영 실측** — 문서 116건의 축과 본문을 살아 있는 원본과 대조했다(아래 절).
  Confluence 는 운영에서 dry-run 이 `CONFLUENCE_DRY_RUN_OK` 로 통과했다(524 = 524).
- capture: 전량 정본은 **`s22-final`** 그대로다(D-306).
- ui_gate: 변화 없음.

## 🔴 운영 실측이 계획을 고쳤다 — 무엇이 실제로 문제였나

배포는 끝났다(`a3b05cd2` → alembic **0027**, 스냅샷
`/var/backups/clovirassist/20260904-073154`). 그다음 **운영을 재 보고** 계획을 고쳤다.

### 재 본 것과 나온 값

| 잰 것 | 값 |
|---|---|
| 문서 | 116건 (이관 110 · 자체 작성 **6**) |
| 다리 없는 이관 문서 | **0** — 110건 전부 `legacy_page_id` 가 있다 |
| 소유 없는 공간 | **0** — `organization` 1 · `project` 11 |
| 현재 판의 자리표시자 | **0** (옛 판 56개에는 있다 — 이력이지 지금이 아니다) |
| 표 | `tableRow` **558개**가 이미 본문에 있다 |
| 🔴 **살아 있는 Notion 원본과 대조** | 110건, 원본 277,058자 : 운영 281,420자 = **1.016** |
| 원본의 90% 미만인 문서 | **1건**(`ClovirPackageRepo`, 78%) |
| 폴더를 쓰는 문서 | 52건 (표는 그대로 남는다) |

### 그래서 8번(본문 복구)은 **거의 다 돼 있었다**

캐시가 아니라 **라이브 API 를 깊이 8 로 훑어** 문서마다 글자 수를 대조했다. 캐시로 재면
순환 논증이다 — 캐시가 깊이 3 으로 잘려 있으면 그 캐시에서 나온 목표치도 잘려 있다.

결과: 109건은 원본과 같거나 길고, **한 건만 78%** 다. 그 한 건의 원인도 찾았다 —
블록 175개 중 85개가 깊이 3 이상이라 `_MAX_BLOCK_DEPTH = 3` 이 잘랐다. 상수를 6 으로
올리고 `--page` 로 **그 문서만** 다시 넣는다. 110건을 통째로 다시 쓰면 바꿀 이유가
없는 109건을 바꾸는 것이다.

### 진짜 남은 것은 11·12번(프로젝트·분류·태그)이다

| 축 | 지금 |
|---|---|
| 프로젝트 공간 | 58건 |
| 프로젝트 미지정 | 52건 |
| 분류 | 110/110 (0026 이 `doc_type` 에서 시드했다) |
| 태그 | 80/110, 문서당 평균 2.3개 |

Notion 원본에서 프로젝트 관계가 있던 것은 **34건뿐**인데 지금 58건이 프로젝트 공간에
있다. 그 차이가 사용자가 말한 「프로젝트 연결이 많이 이상함」이다. 제목과 본문으로
다시 판정해야 한다 — `classify --emit` 이 근거를 적은 파일을 만들고 사람이 검토한다.

### Confluence 는 dry-run 이 통과했다

`CONFLUENCE_DRY_RUN_OK` — 524쪽(current 519 · archived 5) 전부 설명됨, 블로그 0,
첨부 1,458개, 댓글 15건, blocking 0. 원본 수 대조 게이트가 524 = 524 를 확인했다.

## 다음 명령

```
bash scripts/recover-documents.sh notion 2a4c5c5a-5684-8092-9a03-d025a938fc4f  # 그 한 건만
bash scripts/recover-documents.sh confluence        # 524쪽 실제 가져오기
bash scripts/recover-documents.sh classify-emit     # 제안 → **사람이 검토**
bash scripts/recover-documents.sh classify-apply
bash scripts/recover-documents.sh reindex
```

AI 색인은 훑기의 「상태 행이 없다」 갈래가 새 문서를 알아서 집어 간다. ⌘K 색인
(`search_documents`)은 `owner_kind`·분류·태그를 **행에 복사**하므로 프로젝트를 옮기면
낡는다 — 워커가 300초마다 전량 재구축하지만(`search_index_interval_seconds`) 그 5분을
기다리지 않으려면 `POST /api/search/reindex` 를 한 번 부른다.

되돌리기는 `sudo /home/cloviradmin/clovirassist-upgrade/deploy/install.sh rollback
--target /var/backups/clovirassist/20260904-073154` 하나다. DB 만 복원하면 첨부 교체가
지운 바이트 때문에 행이 없는 파일을 가리킨다.

## 이번 회차가 **안 고친** 것 — 그리고 그 이유

- 🔴 **티켓 본문 약 1,120건에 같은 자리표시자가 남아 있다.** 이번 요구는 문서라
  `--scope documents` 로 제외했고, 회차가 그 사실을 Finding 으로 적는다. 같은 회차에 함께
  고치면 되돌릴 수 없는 변경의 범위가 열 배가 된다 — **P-78** 로 남긴다(지시가 있으면 한다).
- **~~Notion 블록 깊이 상한~~ 은 실측으로 반증하고 올렸다(P-79 종료).** 3 → 6.
  `ClovirPackageRepo` 는 블록 175개 중 **85개가 깊이 3 이상**이고, 그래서 그 문서만
  운영 본문이 원본의 78% 였다. 「그 아래는 구조다」는 추측이었다.
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
