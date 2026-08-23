# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-23** (S9)
- phase: **C — AI**
- session: **S9 완료.** 다음은 **S10 — AI Platform 2 (Retrieval · Citation · 생성)**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S9 도 옮기지 않는다.** S9 의 시험 변경은 전부 강화 방향이다 — **시험 10파일 신설**
  (unit 79 · integration 43 · security 13 · regression 15 = **150건**) + 옛 시험 2파일 강화
- s1_commit: `95a89189` · s2_commit: `eec4886c` · s3_commit: `e88e4de3` · s4_commit: `6909bb96` ·
  s5_commit: `aa9c8c63` · s6_commit: `971a31fa` · s7_commit: `87dd8707` · s8_commit: `0240c661`
- working_tree: clean
- **Runtime Component 가 둘 늘었다** — 색인 레인과 임베딩 런타임. Installer 계약(D-205)을
  **같은 세션에서 이행했다**: Stage 12 가 SKIP 에서 OK 가 됐고(이제 **SKIP 인 Stage 가 하나도
  없다**), `clovirassist-index.service` 가 유닛 여섯 번째로 서고, health probe·uninstall 경로·
  재부팅 복구가 함께 들어갔다. **프런트 의존과 번들은 무변경**(S9 은 화면을 안 건드렸다)

## S9 이 실제로 한 것

AI 의 축이다. 이제 **모델이 계약 뒤로 들어갔고, 문서가 스스로 색인되며, 모델이 없어도
그 파이프라인이 돈다.**

| | |
|---|---|
| **모델 이름을 제품이 안 고른다** | 두 곳에 박혀 있던 기본값을 지웠다. 그 한 줄이 「설정에서 모델을 지운다」와 「그 모델을 쓴다」를 **같은 상태**로 만들고 있었다 — 운영자가 칸을 비우면 꺼지는 것이 아니라 우리가 정한 이름으로 조용히 돌았다. 이제 비면 «설정 안 됨»이고 `build_argv()` 는 아예 예외를 던진다 (**D-254**) |
| **호출부는 계약 하나만 안다** | `embed()`·`rerank()`·`generate()`·`capabilities()`. `/usr/bin/claude` 는 Adapter 하나일 뿐이고, `app/llm` 은 지우지 않고 **감쌌다** — 지우면 주간 리포트가 멈추고, 두 벌로 두면 방어가 한쪽에만 걸린다 |
| 🔴 **원문이 Adapter 에 안 간다** | `generate(task=, data=)` 가 난스 구분자를 **Adapter 밖에서** 건다. 계약 시그니처가 원문을 받을 자리를 안 준다 — 새 Adapter 를 붙이는 사람이 방어를 빠뜨릴 자리가 없다. 러너의 `_run_claude` 한 곳도 같은 방어를 받았다 (**D-202 이행**) |
| 🔴 **색인에 권한이 안 구워진다** | `document_chunks` 에 권한 컬럼이 **없다.** 그래서 Permission 변경의 반영 지연이 **0** 이다 — 재계산할 것이 애초에 없다. 「300초 동안 권한 변경을 못 따라간다」를 이벤트를 잘 처리해서가 아니라 **컬럼을 안 만들어서** 없앴다 (**D-256**) |
| **모델이 없어도 색인은 돈다** | 파싱과 chunk 는 돌고 벡터 칸이 NULL 로 남는다. 그 상태에서 키워드 검색은 이미 되고, 모델이 생기면 `embedding IS NULL` 인 chunk 만 채운다. 「AI 없이도 전부 된다」고는 **안 적는다** — 요약·분석·문서생성은 그때 정지한다(D-201 의 경계) |
| **파싱은 AI 가 아니다** | `pypdf` 만 기본 의존이고 DOCX·PPTX·XLSX 는 **표준 라이브러리**로 읽는다. 임베딩 런타임 셋(200MB+)만 `requirements-ai.txt` 로 갈라 Stage 12 가 깐다 (**D-258**) |
| **레인은 잡을 안 집는다** | 할 일 목록이 이미 `ai_index_state` 표다. 신호(저장 시점)와 훑기(안전망)를 **둘 다** 쓰고, 훑기의 첨부 지문은 **한 질의**로 만든다 — 문서마다 물으면 매 tick 에 질의가 1,238번이다 (**D-257**) |
| **설치가 「있다」가 아니라 「된다」를 본다** | `ai_cli status` 는 파일을 보고 `ai_cli selftest` 는 **실제로 벡터를 만들어 길이 1 인지까지** 본다. 받다 만 `model.onnx` 는 이름도 크기도 맞는데 세션을 만들다 죽고, 증상은 「레인이 조용히 재시작만 반복한다」뿐이다 (**D-259**) |

## S9 이 드러낸 것 — 가짜 Adapter 로는 안 나오는 것 넷

실 모델(`intfloat/multilingual-e5-small`)을 붙여서만 확인할 수 있는 것들이다. 원장은
[`EVIDENCE/S9/`](EVIDENCE/S9/README.md).

셋은 **죽어서** 드러난다: ONNX 세션이 요구하는 입력 이름(`token_type_ids` 유무)이 안 맞으면
`InvalidArgument`, 토크나이저 패딩을 안 켜면 길이가 다른 배치가 죽고, 자르기를 안 걸면
512 토큰 초과에서 죽는다.

**넷째는 안 죽는다.** `query: `/`passage: ` 접두사를 안 붙여도 **오류가 하나도 안 나고**
품질만 조용히 떨어진다. 그래서 그것만은 수치로 봤다 — 두 접두사의 벡터 코사인 거리
**0.060378**, 질의↔맞는 본문 **0.8849** > 질의↔상관없는 본문 **0.8016**.

**그리고 시험이 잡은 결함 하나.** 이 저장소의 세션은 `autoflush=False` 다
(`app/core/db.py`). 색인 서비스가 그것을 모르고 쓰면 **같은 문서에 상태 행이 둘** 만들어져
커밋 시점에 부분 유니크가 거절한다 — 실패가 그 자리가 아니라 저 멀리서 터진다.
`enqueue()`·`embed_pending()`·`run_once()` 세 곳에 flush 를 명시했다.

**문서 하나의 쓰기를 SAVEPOINT 로 감쌌다.** 안 감싸면 한 문서의 chunk 하나가 제약을 어길 때
그 실패가 커밋에서 터지고, 같은 tick 에 멀쩡히 색인된 나머지 열아홉 건이 함께 되감긴다.
그리고 다음 tick 이 같은 문서를 다시 잡아 같은 자리에서 또 죽는다.

### 그리고 LXD 리허설이 **S8 의 Stage 11 결함**을 잡았다

S9 의 Stage 12 를 검증하려고 Clean 설치를 돌렸더니 **Stage 11 에서 설치가 통째로 섰다**:

```
PermissionError: [Errno 13] Permission denied: '/tmp/tmp.lzRklX1IW3/10-storage-mounts.conf'
STAGE_11_STORAGE: FAIL 마운트 유닛을 만들지 못했습니다
```

`mktemp -d` 는 **root 소유 0700** 이고, 그 안에 파일을 쓰는 것은 그 셸이 아니라
`run_as_app` 으로 띄운 **서비스 계정**이다. 소유를 안 넘기면 그 자리에서 죽는다.

S8 이 왜 못 봤는지도 적어 둔다: Storage 를 **호스트에서 root 로** 검증했고, Clean 설치
경로(서비스 계정으로 CLI 를 부른다)는 그때 한 번도 안 지났다. 리허설의 단언 둘도 낡아
있었다(Stage 11·12 를 아직 `SKIP` 이라고 기대했다) — **늘 실패하는 검사는 없는 검사보다
나쁘다.** 셋 다 고쳤고, 「서비스 계정에 넘기는 디렉터리는 그 계정 소유여야 한다」를
`tests/unit/test_deploy_wiring.py` 가 계약으로 지킨다.

## 완료

- **S0 — Plan 기록.** Architecture · Decision · S0~S22 실행계획을 저장소 지속 문서로 정착.
- **S1 — 기반 정직화 · 실측 · 성능 검증.** 프로브 8건 · PG 스택 실측(D-209~D-212) ·
  `VARCHAR(n)` 감사(D-214). **제품 코드 diff 0.**
- **S2 — PostgreSQL Foundation.** 70 표 · 256 인덱스가 `0001_pg_baseline` 하나로 선다.
  SQLite Runtime 의존 0 · `--workers 1→4`. 결정 **D-215~D-221**.
- **S3 — Product Identity · Hostname · TLS.** CN/SAN 일치 · `ssl_verify_result=0`.
  결정 **D-222~D-224**.
- **S4 — 설치 · 배포 자동화 Foundation.** Clean OS 에서 세 줄, 재부팅하면 스스로 복귀.
  결정 **D-225~D-229**.
- **S5 — Identity & Access.** 권한이 표가 되고 가시성이 함수 하나가 됐다. 결정 **D-230~D-235**.
- **S6 — Work Domain.** 티켓이 세 이름으로 불리고 그 셋이 같은 티켓을 가리킨다.
  결정 **D-236~D-243**.
- **S7 — Knowledge Domain (+P-14a).** 본문의 정본이 블록이 되고 그 블록에 이름이 붙었다.
  결정 **D-244~D-248**.
- **S8 — File Storage Providers.** 파일이 DB 밖에 살고, 그 자리가 진짜 그 저장소인지 매번 묻는다.
  결정 **D-249~D-253**.
- **S9 — AI Platform 1 (Gateway · Pipeline).** 위 두 절. 결정 **D-254~D-259**.

## ⚠️ 코드는 옮겼고, **데이터는 아직 안 옮겼다** (S2 가 남긴 구분, 그대로 유효)

| | 상태 |
|---|---|
| **코드** | PG 전용이다. `sqlite://` 를 주면 **기동을 거부한다**(`normalize_database_url`) |
| **스키마** | `0001`~`0007` 이 **98 표**를 만든다 (S9 가 2 표 신설) |
| **운영 데이터** | **여전히 `/var/lib/clovirone-web-assistant/web.sqlite3` 에 있다.** 아무것도 옮기지 않았다 |
| **운영 서버에 도는 것** | **아직 S2 이전 빌드다.** 운영 설치를 새 slug 로 이전하는 것은 데이터 이관과 함께 갈 일이고 S13·S14 의 몫이다 |

**S13 이 알아야 하는 것 일곱** (앞 여섯은 S6·S7·S8 이 남긴 것 그대로):
1. 표 이름이 `departments` → `org_units`(D-234), `ticket_cache` → `tickets`(D-238)로 바뀌었다.
   **컬럼 이름은 둘 다 그대로**다.
2. 적재 직후 `app/work/numbering.py::seed_counters()` 를 부른다.
3. **Project Key 20건은 확정됐다**(D-243). 순서는 하나다 — 프로젝트 적재 →
   `project_keys.apply_confirmed(db)` → `numbering.seed_counters(db)` → 재채번.
4. **날짜 컬럼 16개가 `date`/`timestamp` 다**(D-248). 소스 문자열을 그대로 대입하면
   못 읽는 값에서 **500** 이 난다 — `app/core/dates.py::parse_date`/`parse_dt` 를 지난다.
5. **본문을 옮길 때 앞판을 함께 넘긴다**(D-247). `blocks.derive(body, carry_from=앞판)` 을
   안 쓰면 재실행마다 판이 새로 쌓인다. 다리는 `documents.legacy_page_id`(부분 유니크)다.
6. **파일을 옮길 때 `app/storage/service.py::store_bytes` 를 지난다**(D-250). 직접
   `files` 행을 만들면 체크섬·저장 키·원자적 커밋이 전부 빠진다. 옛 첨부 셋(게시판·티켓·
   채팅)은 아직 `app/core/uploads.py` 의 로컬 경로에 있고 **S14 까지 그대로 남는다**.
7. **색인은 따로 안 만들어도 된다**(S9). 적재가 끝나면 색인 레인의 훑기가 상태 행이 없는
   문서를 전부 찾아 스스로 돈다. 급하면 `python -m app.cli.ai_cli reindex` 로 앞당긴다.

## 상태 — 전환 축 다섯

| 축 | 현재 | 목표 | 소유 Session |
|---|---|---|---|
| **PostgreSQL** | **설치까지 끝났다.** Installer Stage 6·7 이 cluster·role·DB·extension 을 세운다. `0007` 이 `vector` 확장을 켠다 | PG16 + pgvector + pg_trgm 이 System of Record | S2 ✅ · S4 ✅ · S9 ✅ |
| **SQLite 제거** | **Runtime 의존 0.** 코드 수준 13항이 전부 닫혔다. 다만 **운영 데이터는 아직 SQLite 에 있다** | Runtime 0 + 데이터 이관 완료 | S2 ✅ · S7 ✅ → S13·S14 |
| **Notion Migration** | **Runtime 의존 중이고 동기화 셋이 전부 실패 상태.** 미러 `tickets` 1,124 · `document_cache` 110. **받을 그릇은 다 있고, 이제 색인까지 스스로 붙는다** | Notion Runtime 의존 0, 데이터는 PG 로 | S13 → S14 |
| **AI** | **Gateway 와 색인 파이프라인이 섰다.** 모델은 계약 뒤에 있고, `document_chunks` 에 **권한 컬럼이 없다**. 아직 **검색이 이 인덱스를 안 읽는다** — n8n → `claude-work-assistant`(8789) 가 여전히 Notion 전량을 모델에 싣는다(그 경로도 이제 난스 방어를 받는다) | Model Gateway ✅ + 권한이 앞서는 Hybrid Retrieval | S9 ✅ · **S10** · S11 |
| **Backup** | **기본형 + 설치 스냅샷 + 파일 저장소 이관.** `pg_dump -Fc` + 체크섬 + `--exit-on-error` 복원 + 파일 아카이브. **AI 색인은 일부러 백업 대상이 아니다**(D-203·D-204) | + Policy·Schedule·Retention·Manifest·복원 후 앱 기동 검증 | S2 ✅ · S4 ✅ · S8 ✅ → S12 |

**Identity 축은 닫혔다** — 호스트명·TLS 는 S3, slug 는 S4, 역할·권한·가시성은 S5.
**남은 한 건은 세션 쿠키 이름**(`clovirone_session`)이고 S14 다 (`BACKLOG.md` **P-33**).

**UI 축(W0~W5)은 별개로 완료돼 있고 자산은 보존한다.** 근거와 수치는
[`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이고 재개는 Phase E(S15~S20)다 (D-207).

## 최근 테스트

S9 은 **공유 계층 넷**을 바꿨다 — LLM 백엔드 계약(`run()` 분리), 지식 도메인의 저장 경로
(`versions.snapshot`·`attachments`), health(`/readyz`·대시보드), 워커 진입점. 그래서 백엔드
전 회귀를 다시 돌렸다.

| 대상 | 결과 |
|---|---|
| 백엔드 전 회귀 (PostgreSQL) | **통과** — `scripts/run_full_regression.sh` 여섯 통 전부 초록 · `FULL_REGRESSION_OK` · **3,998건** · 43분 25초. ⚠️ **`pytest tests` 를 백그라운드로 직접 돌리면 안 된다**(P-09e — 자식이 안 닫힌 stdin 을 읽는다). 그리고 ⚠️ **도는 시험 아래에서 소스를 만지지 않는다** — 이 세션이 한 번 그렇게 해서 완주하던 회귀를 버리고 처음부터 다시 돌렸다 |
| **실 모델 파이프라인** (S9 Exit) | **17/17 PASS.** 테스트 서버에서 **생성 Adapter 를 끈 채로** 파싱·chunk·임베딩 완주. 처리량 80.2 docs/s · 질의 p50 5.31ms · 최대 RSS 1,001.7MB · 접두사 격차 0.060378. 원장은 [`EVIDENCE/S9/`](EVIDENCE/S9/README.md) |
| **LXD Clean 설치** | **35/35 통과 · `[FAIL]` 0건.** Stage 12 가 OK 이고 유닛이 **여섯**이 됐다. 그리고 이 실행이 **S8 의 Stage 11 결함**을 잡았다(아래) |
| **`--with-ai` 설치** (S9 Exit) | **통과.** 실 모델 465MB 를 넣고 Clean 설치 → `STAGE_12_AI: OK AI 런타임 + 모델 로드 검증 통과` · `INSTALL_OK`. 설치 직후 `ai_cli status` 가 🔴 **`generate` 비활성 · `embed` ok** 를 말하고 `selftest` 가 `{"ok": true, "dim": 384}` · `-index` 유닛 active·enabled · `/readyz` ready |
| **Gateway 계약** | **28건.** 꺼짐과 못 씀을 구별한다 · **Gateway 를 만드는 것은 절대 실패하지 않는다** · 부분 결과는 성공이 아니다 · 모르는 kind 를 조용히 안 접는다 · 모르는 모델 이름을 기본값으로 안 떨어뜨린다 |
| **프롬프트 주입 (보안)** | **13건.** 주입 5종이 전부 구분자 안에 갇힌다 · 흉내 낸 구분자는 걷어내고 **그 사실을 보고한다** · 주입 문장 자체는 남긴다 · 난스가 매번 다르다 · **러너의 값이 우리 값과 같은지 맞물려 둔다** · 계약 시그니처가 원문을 받을 자리를 안 준다 |
| **색인 파이프라인** | **17건.** 블록 앵커 · 제목은 첫 chunk 에만 · **모델이 없으면 벡터 칸만 NULL** · 나중에 모델이 생기면 **다시 파싱하지 않고** 채운다 · 안 바뀐 chunk 는 다시 임베딩하지 않는다 · **모델을 바꾸면 글이 같아도 다시 만든다** · 저장소 장애는 재시도이지 영구 실패가 아니다 |
| **Index Lifecycle** | **14건.** 저장·첨부·해제가 신호를 낸다 · **같은 본문이면 다시 안 돈다** · 파서/임베딩 판이 오르면 전부 낡는다 · **모델이 없는 설치가 매 tick 마다 전 문서를 다시 색인하지 않는다** · 파일을 바꿔 껴도 지문이 잡는다 · 훑기가 지문을 **한 질의**로 묻는다 |
| **파서** | **21건.** 제목마다 절이 열린다 · 슬라이드 10이 2보다 앞에 안 온다 · **시트는 관계를 따라간다**(이름을 추측하면 인용이 다른 시트를 가리킨다) · `AA` 열 · inline string · EUC-KR · 손으로 만든 PDF 에서 쪽마다 글 · 이미지는 «못 함»이 아니라 «안 함» · 항목 상한이 두 겹 |
| **chunk** | **11건.** 파일 chunk 는 쪽을 안 넘는다 · 문서 chunk 는 블록을 합치고 **첫 블록에 앵커한다** · 상한을 안 넘는다 · 마침표 없는 벽도 잘린다 · 쪽 번호만 있는 쪽은 버리고 **제목 한 줄짜리는 남긴다** |
| **풀링** | **8건.** 패딩이 벡터를 안 끈다 · 평균이 진짜 평균이다 · 전부 길이 1 · 0 벡터는 0으로 안 나눈다 · **numpy 갈래와 순수 파이썬 갈래가 같은 답을 낸다**(느린 쪽이 빠른 쪽의 반례다) |
| **AI CLI** | **12건.** 종료코드가 계약(끄고 설치하면 0, 켜 놓고 못 쓰면 1) · **자기검증이 길이 1 까지 본다** · 받다 만 모델 디렉터리를 거절 · 모르는 모델을 거절 · `reindex` 는 표시만 하고 색인하지 않는다 |
| **스키마 ↔ 코드** | **11건.** 마이그레이션에 얼려 둔 어휘 셋과 차원이 코드와 같은가 · `vector` 확장이 섰는가 · 컬럼이 `vector(384)` 인가 · 🔴 **chunk 표에 권한 컬럼이 없다** · **벡터 인덱스가 아직 없다**(D-210) |
| **배선 (회귀)** | **15건.** 색인 레인이 진입점 선택지에 있다 · 유닛이 설치·활성화 목록에 있다 · **`MemoryDenyWriteExecute` 를 안 켠다**(ONNX 가 SIGSEGV) · 레인마다 리스와 liveness 이름이 다르다 · **레인이 잡을 안 집는다** · `/readyz` 가 「켜 놓고 못 쓰는 AI」만 unready · **생성만 없는 것은 unready 가 아니다** · 모델 이름이 어디에도 안 박혀 있다 |
| 시험 합계 | **신설 10파일 · 150건**(unit 79 · integration 43 · security 13 · regression 15) + 설치 배선 5건 신설. 백엔드 전체 3,842 → **3,998건** |
| `check_domain_single_source.py` | 규칙 13→**18**, 자기검증 19→**29사례**(검출 21 · 위양성 8). chunk 행·상태 행·ONNX 세션·**프롬프트 조립**·**모델 이름**이 각각 한 곳에서만 쓰인다 |
| 마이그레이션 왕복 | `upgrade`→`downgrade`→`upgrade` 를 실 PG 에서. `0007`: 표 96→**98** · 인덱스 377→**389** · 제약 912→**955** 가 **대칭** |
| 모델 ↔ 스키마 | autogenerate diff **0** |
| 프런트 | **안 돌렸다.** `frontend/` diff 0 이고 번들 지문이 그대로다(E1). S9 은 화면을 안 건드렸다 |
| `static_checks.sh` | S9 이 만든 실패 **0**. 남은 셋은 전부 P-09a 소유 |

### ⚠️ 시험용 PostgreSQL 컨테이너를 **바꿔 끼웠다**

옛 컨테이너는 `postgres:16-alpine` 이라 **pgvector 가 없었다.** `vector(384)` 컬럼이
생기는 순간 마이그레이션이 그 자리에서 죽는다. `pgvector/pgvector:pg16` 으로 다시 만들었다
(같은 이름 `clovir-s2-pg` · 같은 포트 55433 · 같은 자격증명 · 같은 서버 옵션).
**시험 DB 는 매번 새로 만들므로 잃은 데이터는 없다.**

### ⚠️ `static_checks.sh` 는 아직 빨간불이다 — **S9 이 만든 것이 아니다**

`BACKLOG.md` **P-09a** 가 Owner 를 갖는다. **S9 은 자기가 넣은 것 하나를 그 자리에서
고쳤다**(색인 레인 로그 문구의 em 대시).

| 무엇 | 어디서 왔나 |
|---|---|
| 사용자 문구의 가운뎃점(·) 8건 · em 대시 1건 · `tokens.css` 드리프트 | S5·S6·S4 가 기록한 것 |
| `tests/unit/test_deploy_wiring.py` 의 `subprocess` encoding 누락 | S4(`6909bb96`) |

## NOW

**S9 은 끝났다.** 모델이 계약 뒤로 들어갔고, 문서가 스스로 색인되며, 모델이 없어도 그
파이프라인이 돈다.

이 세션에서 가장 값이 나간 것은 Gateway 를 만든 것도 파서를 만든 것도 아니라 **권한을
인덱스에 안 넣기로 한 것**이다. D-203 이 요구한 「Permission 변경은 재임베딩이 아니라 필터
재계산」은 이벤트를 잘 처리해서 이룰 수 있는 것이 아니었다 — 권한 판정 결과가 인덱스에
있는 한, 권한이 바뀌면 그 인덱스는 바뀌기 전까지 틀린 값이다. 컬럼을 안 만들자 반영
지연이 0 이 됐고, 그 성질은 주석이 아니라 **컬럼 목록**이 지킨다.

두 번째는 **모델 기본값을 지운 것**이다. 「비어 있으면 기본값」은 편의처럼 보이지만
「설정에서 지운다」와 「그것을 쓴다」를 같은 상태로 만든다. 그런 상태는 화면이 거짓말을
하는데 아무 오류도 안 난다.

세 번째는 **접두사를 수치로 확인한 것**이다. 나머지 결함은 전부 죽어서 드러나는데
그것 하나만 안 죽는다 — 그래서 「돌았다」가 아니라 「다른 벡터가 나왔다」를 봤다.

## NEXT — 다음 시작점: S10 (요청 시)

**S10 = AI Platform 2 — Retrieval · Citation · 생성.** 사용자 요청 없이 착수하지 않는다.
범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1, 설계 요지는 §5.4(D-202·D-209·D-210).

S9 이 다음 Session 에게 넘기는 것:

1. 🔴 **권한은 `LIMIT` 앞에 걸어야 한다.** chunk 에 권한이 없는 것이 설계다(D-256) —
   그래서 그 판정을 **질의가** 해야 한다. `document_chunks.document_id` 를
   `effective_visibility_clause` 가 만든 후보 집합과 조인하고, 그 조인을 `LIMIT` **앞에**
   둔다. 음성 테스트는 「답변에 안 나왔다」가 아니라 **「Context 에 안 들어갔다」**를 봐야
   한다(D-202).
2. **벡터 인덱스가 아직 없다. 그것이 의도다**(D-210). 384차원 exact 스캔이 수천 벡터에서
   1~9ms 다. 임계는 약 **1.2만 벡터**이고, 넘었는지는 `ai_cli status` 의
   `vector_index_recommended` 가 말한다. 넘으면 HNSW(`m=32`·`ef_construction=200`·
   `hnsw.ef_search=40`)를 **별도 마이그레이션**으로 만든다.
3. **키워드 인덱스도 S10 의 몫이다.** `document_chunks.text` 에 `gin_trgm_ops` 와 FTS GIN 을
   아직 안 걸었다 — 지금 아무도 그 컬럼으로 검색하지 않는데 걸면 chunk 를 넣을 때마다
   쓰기만 는다. RRF 초기 가중치는 D-209 에 있고 **최종 값은 S10 이 실제 relevance 로 정한다**.
4. **티켓은 아직 색인하지 않는다.** 지금 출처는 `document` 와 `file` 둘이다. 티켓 본문·댓글·
   활동을 인용 앵커와 함께 실으려면 `app/ai/index/service.py::_collect_units` 에 출처를
   하나 더하고 `document_chunks` 의 `source_kind`·`anchor_kind` CHECK 와
   `alembic/versions/0007_ai_index.py` 의 얼린 어휘를 **함께** 넓힌다
   (`tests/unit/test_ai_domain_seed.py` 가 둘을 맞물어 둔다).
   ⚠️ **권한을 묻는 자리를 먼저 정해야 한다** — 지금 `document_id` 가 NOT NULL 이다.
5. **인용 앵커는 이미 저장돼 있다.** `anchor_kind`(block/page/slide/section/sheet/text) ·
   `anchor_ref`(기계용) · `anchor_label`(사람이 읽는 말). S10 은 그것을 **링크로** 바꾸면
   된다 — 새로 만들 것이 없다.
6. 🔴 **생성 경로를 새로 만들지 마라.** `Gateway.generate(task=, data=)` 가 유일한 문이고,
   `scripts/check_domain_single_source.py` 의 「프롬프트 조립」 규칙이 다른 자리에서
   `build_prompt()` 를 부르는 것을 막는다. Retrieval Content 는 **데이터이지 System
   Instruction 이 아니다**(D-202).
7. **실 본문으로 모델을 재검토할 자리다**(D-211 상향 경로). S1 의 품질 측정은 제목 부분구간
   질의였다. 바꾸는 비용은 재색인뿐이지만 **차원이 바뀌면 마이그레이션도 함께**다
   (`vector(384)` 가 얼어 있다).
8. **`kit.jsx` 는 S9 도 안 건드렸다.** S10 이 AI 작업공간 화면을 만들 때 그 파일이 처음
   열린다.

## RISK — 지금 살아 있는 것

전체는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §12.

| # | Risk | 상태 / Owner |
|---|---|---|
| ~~R1~~ ~~R2~~ ~~R3~~ | (S2 가 닫음) | 해소 |
| ~~R4~~ ~~R5~~ ~~R6~~ ~~R7~~ | (S1 이 닫음) | 해소 |
| ~~R13~~ ~~R14~~ | 제품 slug · 설치 자동화 | 해소 (계약 이행은 매 Session 이 계속 진다) |
| ~~R15~~ | LXD 컨테이너가 실 장비와 다르다 | **해소** — 재부팅 축은 S4(D-229), Storage 축은 S8 이 **호스트에서** 닫았다 |
| R11 | **시험 Storage 가 실 NAS 와 다르다** | **살아 있다(의도한 대로)** — 실 정보 수령 시 **설정만** 바꾼다 |
| R16 | GitLab 주소 부재 | **완화** — Installer 가 Remote 중립이다 |
| R17 | pgvector 검색 품질 | **S10** — 하이브리드 가중치(D-209 초기값)와 실 본문 모델 재검토(D-211) |
| — | **저장소 장애 중 쓰기가 21초~180초 이상 걸린다** | **알려진 성질**(D-251). 「몇 초 만에 503」이라고 **약속하지 않는다** |
| — | **색인 레인이 안 뜨면 검색 결과가 조용히 낡는다** | **완화** — `ALWAYS_ACTIVE_UNITS` 에 있어 재부팅 판정과 Stage 17 이 본다. 밀린 건수는 `ai_cli status` 와 대시보드가 말한다. 그래도 **아무 오류도 안 나는** 종류의 실패라 감시 대상이다 |
| — | **운영 데이터가 아직 SQLite 에 있고, 운영 서버는 아직 옛 slug 설치다** | S13 · S14 |

## BLOCKERS

- **없음.**

## 입력 — Blocker 는 아니지만 다음 Session 이 알아야 하는 것

| 항목 | 상태 |
|---|---|
| **20개 Project Key 명명** | **확정됐다** (2026-08-22 · D-243). 정본은 `app/work/project_keys.py::CONFIRMED`, 사람이 읽는 사본은 [`PROJECT_KEYS.md`](PROJECT_KEYS.md). **지금 적용된 프로젝트는 0건이고 그것이 정상이다** — PG 의 `projects` 가 비어 있다(적재는 S13) |
| **테스트 서버 접속** | **쓸 수 있다** — `10.100.64.71` 한정. SSH 키 인증 · sudo 는 `dist/ops/server.env`(gitignore). 값을 tracked 파일·커밋·로그에 복사하지 않는다 |
| **임베딩 모델 파일** | **테스트 서버에 있다** — `~/s1bench/models/intfloat__multilingual-e5-small/`(465MB, S1 이 받은 것). 다시 받으려면 `scripts/bench/setup_models.sh`. 설치처에 넣는 것은 `deploy/install.sh ai --ai-model-dir <디렉터리>` 이고 **네트워크로 안 받는다**(D-259) |
| **S9 검증 하네스** | 서버의 `~/s9verify`(소스 + venv). 다시 돌리려면 `./venv/bin/python scripts/verify_ai_pipeline.py --model-root ~/s1bench/models`. 이 서버에는 **PostgreSQL 이 없다** — DB 축은 개발 머신의 실 PG 가 본다 |
| **S9 이 쓴 LXD 컨테이너** | **지웠다.** 다시 만들려면 `sudo bash scripts/lxd_rehearsal.sh <src.tar.gz> <이름>`. `--with-ai` 설치는 컨테이너에 모델을 `lxc file push -r` 로 넣고 `install.sh install … --ai-model-dir <경로>` 를 부른 것이다 |
| **테스트 서버의 시험 Storage** | **세워 뒀다** — NFS export `/srv/clv-nfs-export` · Samba share `/srv/clv-smb-share`(`[clvtest]`) · 마운트 `/mnt/clv-nfs`·`/mnt/clv-smb`(enabled, 재부팅 복귀 확인) · 하네스 사본 `/opt/clv-matrix-src` · 시험 계정 `clvsvc`. SMB 자격증명은 `/etc/clovirassist/secrets/smb_matrix`(0600, root)이고 **값은 저장소에 없다** |
| **LXD** | 이 서버에 **초기화해 뒀다**(dir 스토리지 풀 + `lxdbr0`). `sudo bash scripts/lxd_rehearsal.sh <src.tar.gz>` 로 언제든 다시 돈다. **`/dev/kvm` 이 없어 LXD VM 은 못 쓴다** — 실 재부팅이 필요하면 서버 자체를 재부팅한다 |
| **리허설 소스 tarball** | 작업 트리를 그대로 tar 로 만들어 넣는다(`.git`·`node_modules`·`docs`·`tests`·`var` 제외). **LF 로 저장돼 있어야 한다** |
| **canonical 호스트** | `https://clovirassist.gooddi.lab` → 10.100.64.71. 옛 이름은 DNS 에 없다(NXDOMAIN). 인증서는 자체서명이고 사본이 `dist/ops/` 에 있다 |
| **하네스를 원격에 겨눌 때** | `UI_QA_TLS_CA` 로 그 인증서를 준다 — `tls.py` 가 파이썬과 Node 양쪽에 심는다. **Chromium 의 페이지 이동만은 운영체제 신뢰 저장소를 본다.** QA 계정 `ui-qa@goodmit.co.kr` 은 **보관 상태**다 |
| **시험용 PostgreSQL** | 개발 머신 컨테이너 `clovir-s2-pg`(포트 55433). **이미지가 `pgvector/pgvector:pg16` 으로 바뀌었다**(S9) — `postgres:16-alpine` 에는 `vector` 확장이 없어 `0007` 이 죽는다. `CLOVIR_TEST_PG_URL` 로 덮어쓴다(주소는 `postgresql+psycopg://` — `psycopg2` 는 안 깔려 있다) |
| **전 회귀를 돌릴 때** | **`scripts/run_full_regression.sh` 를 쓴다.** `pytest tests` 를 백그라운드로 직접 돌리면 14% 근처에서 **CPU 0 으로 멈춘다**(P-09e — 자식이 안 닫힌 stdin 을 읽는다). 그 러너는 `< /dev/null` 을 붙이고 통을 넷으로 나눈다 |
| **회귀 결과를 읽을 때** | **파이프 뒤에서 읽지 않는다.** `pytest … \| grep …` 의 `$?` 는 **grep 의 종료코드**다. 파일로 받고 종료코드를 따로 찍은 뒤 그 파일을 본다. 그리고 **도는 시험 아래에서 소스를 만지지 않는다** |
| **원격에서 오래 걸리는 명령을 돌릴 때** | **하네스가 걸릴 수 있는 자리에는 시간 제한을 건다.** 걸린 하네스는 결과를 한 줄도 안 내므로 「걸렸다」는 사실조차 증거로 안 남는다 |
| **`pg_dump`/`pg_restore`** | 개발 머신(Windows)에는 **없다**. `PG_BIN_DIR` 를 비워 두면 안 된다 |
| **Notion 토큰** | 운영 정본은 `/etc/clovirone-web-assistant/secrets/notion_{docs,report}_token`(0640, sudo), 개발 사본은 `var/secrets/`(gitignore) |
| 실 NFS/NAS 장비 정보 (현재 없음이 **확인됨**) | 실 정보를 받으면 `storage_providers` 행의 `source`·`options` 만 바꾸고 `deploy/install.sh storage` 를 다시 돌린다 — Application 수정은 없다 (U8·U9) |
| 제품 Domain 밖 Notion DB 3종 (179 · 23 · 9) | 기본값 = 이관하지 않음 (U19) |
| GitLab Repository 주소·자격증명 | Installer 가 Remote 중립이라 **주소가 정해지면 설정만 바꾼다** (R16) |

<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
