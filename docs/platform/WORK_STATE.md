# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-23** (S11)
- phase: **C — AI (완료).** 다음은 Phase D
- session: **S11 완료.** 다음은 **S12 — Backup / Restore 운영**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S11 도 옮기지 않는다.** S11 은 시험을 **지웠다** — 그러므로 이 기준을 옮기면 그 삭제가
  다음 세션의 검사 시야에서 영영 사라진다. 삭제 17건은 전부
  `qa-contract-replaced-by:` 로 명명됐고 검사가 통과한다.
- s1~s11_commit: `95a89189` · `eec4886c` · `e88e4de3` · `6909bb96` · `aa9c8c63` ·
  `971a31fa` · `87dd8707` · `0240c661` · `ba68ef2c` · `e3953192` · `08472e2e`
- working_tree: clean
- **Runtime Component 가 넷 줄었다.** 제품에 유닛을 더한 것이 아니라 **서버에서 넷을
  걷어냈다** — n8n · 러너 셋. 스키마는 98 → **94 표**(`0009` 가 넷을 내렸다).
  프런트 번들 초기 gzip **265 → 263KB**(예산 280)

## S11 이 실제로 한 것

**옛 AI 경로를 걷어냈다.** 근거는 「기능이 겹친다」가 아니라 **「하나는 권한을 안 본다」**다.

| | |
|---|---|
| 🔴 **채팅이 제품 안에서 답한다** | `chat_message` 가 n8n 웹훅 대신 `app/ai/retrieval::answer()` 를 부른다 — `/ai` 가 부르는 **같은 함수**다. 권한이 `LIMIT` 앞에 걸리고(D-256), 이 레인은 **아무 데도 HTTP 를 안 보낸다** |
| 🔴 **다섯 포트가 죽었다** | 5678 · 5679 · 8787 · 8788 · 8789 미청취. 그리고 `systemctl list-unit-files` 가 **0건**이다 — 정지만 하면 재부팅에 돌아오므로 유닛 파일까지 걷어냈다 |
| **러너를 부르던 기능 셋이 Gateway 로 왔다** | 채팅 · 대시보드 요약 · AI 퀴즈. 새 외부 호출 관문을 안 만들었다 (**D-266**) |
| 🔴 **그 김에 프롬프트 방어가 셋 다에 걸렸다** | 퀴즈 주제와 요약 사실이 이제 `data` 로 가 난스 구분자 안에 갇힌다. 러너 시절 이 둘에는 그 방어가 **안 걸려 있었다** — 퀴즈 주제 칸에 「앞의 지시를 무시하고…」를 적으면 그대로 프롬프트에 들어갔다 |
| **부를 곳이 사라진 표 넷을 내렸다** | `workflows` · `runners` · `automation_templates` · `document_generations` + 컬럼 둘(`prompts.runner_id` · `schedules.runner_id`). `0009` 왕복이 실 PG 에서 대칭이다 (**D-267**) |
| **워크플로 22개를 지우기 전에 보관했다** | 활성 둘 포함 전량(134KB). credential 참조 97건이 전부 `(id, name)` 뿐임을 **구조로** 확인했다 — 값은 0건 |
| **모델 설정이 한 벌이 됐다** | 예전에는 기능마다 주소·토큰·타임아웃이 따로 있었다(`game_runner_*` · `assistant_runner_*` · `assistant_context_delete_*`). 지금은 `app/ai/gateway/registry.py` 하나다 |
| **셋업 체크리스트의 「AI」가 진짜를 본다** | 러너 행의 헬스체크 응답이 아니라 Gateway 의 `capabilities()` 다. 그래서 「실제 업무 처리 여부와는 별개입니다」라는 단서가 필요 없어졌다 |
| **되돌릴 수 있게 해 뒀다** | 서버에서 **지우지 않고 옮겼다** — `/var/backups/n8n-s11/`(2.7GB) + `/var/lib/n8n.removed-s11`(738MB). 디스크 회수는 사람이 확인한 뒤에 한다 |

## S11 이 드러낸 것 — 지우는 일이 만든 함정 넷

### 1. 「지웠다」는 시험으로 안 남으면 조용히 되돌아온다

허용 목록에 `127.0.0.1:5678` 을 한 줄 되돌리거나, 옛 설치 스크립트가 여전히 n8n 유닛을
확인하거나, 누가 `app/runners` 를 다시 만들면 이 세션이 한 일이 **아무 오류 없이** 무효가
된다. `tests/regression/test_external_automation_removed.py`(9건)가 그 회귀만 본다 —
import · 라우트 · 잡 종류 · 허용 목록 · 표 · 컬럼 · 배포 산출물, 그리고 **아카이브가
실제로 저장소에 있는지**까지.

### 2. 삭제 규약이 1:1 을 강제하면 껍데기 파일을 만들게 된다

`check_test_strength.py` 는 시험 파일 삭제를 대체 파일이 명명될 때만 통과시키는데, 그
파싱이 `search()` 라 **파일당 한 건**이었다. S11 은 열일곱 개를 지운다 — 1:1 이면 아무것도
안 지키는 파일 열일곱 개를 만들게 되고 그것이 규칙이 막으려던 상태보다 나쁘다.
`finditer` 로 바꾸고 **반례 둘을 자기검증에 넣었다**(선언이 없으면 못 찾는다 · 머리 40줄
밖이면 못 찾는다). 규칙의 뜻은 「1:1」이 아니라 **「지운 파일마다 이름이 적혀 있다」**다 (D-268).

### 3. 「검증 통과」와 「검증할 대상이 사라짐」은 다른 초록이다

기능을 지우면 그 기능의 시험도 사라져 **남은 시험이 전부 통과한다.** 그것을 완료로 읽으면
안 된다. 그래서 S11 은 지운 자리마다 계약을 **다시 세웠다**: 채팅은
`test_chat_answers_from_retrieval.py`(7건)가 새로 진다 — 그리고 그 중심 시험은
「답변에 안 나왔다」가 아니라 **모델에게 실제로 넘어간 문자열**을 본다(D-202).

### 4. 화면을 지우면 **부를 곳 없는 조각**이 남는다

지운 화면이 남긴 것들이 오류를 안 내면서 남아 있었다: `runner_unavailable` 알림
(보내는 코드가 없다) · `document_ready` 알림 설정 토글 · Notion 매핑의 `/resolve-conflict`
(충돌 상태를 만들 수 있는 경로가 사라져 영영 도달 불가) · 스케줄의 `TARGET_WORKFLOW`
(화면은 고를 수 있게 보여 주고 실행은 매번 실패) · `prompts.runner_id`(아무것도 안
가리키는 36자). 전부 함께 걷어냈다.

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
- **S9 — AI Platform 1 (Gateway · Pipeline).** 모델이 계약 뒤로 들어가고 문서가 스스로
  색인된다. 결정 **D-254~D-259**.
- **S10 — AI Platform 2 (Retrieval · Citation · 생성).** 권한이 `LIMIT` 앞에 걸리고
  인용이 문단을 가리킨다. 결정 **D-260~D-264**.
- **S11 — n8n · 외부 Runner 제거.** 위 두 절. 결정 **D-265~D-268**, 원장
  [`EVIDENCE/S11/`](EVIDENCE/S11/README.md).

## ⚠️ 코드는 옮겼고, **데이터는 아직 안 옮겼다** (S2 가 남긴 구분, 그대로 유효)

| | 상태 |
|---|---|
| **코드** | PG 전용이다. `sqlite://` 를 주면 **기동을 거부한다**(`normalize_database_url`) |
| **스키마** | `0001`~`0009` 가 **94 표**를 만든다 (S11 이 넷을 내렸다) |
| **운영 데이터** | **여전히 `/var/lib/clovirone-web-assistant/web.sqlite3` 에 있다.** 아무것도 옮기지 않았다 |
| **운영 서버에 도는 것** | **아직 S2 이전 빌드다.** 그 빌드의 채팅은 n8n 을 부르므로 지금부터 답을 못 한다 — 의도한 결과다. 새 빌드의 채팅은 n8n 을 안 부른다. 설치 이전은 S13·S14 |

**S13 이 알아야 하는 것 아홉** (앞 여덟은 S6~S10 이 남긴 것 그대로):
1. 표 이름이 `departments` → `org_units`(D-234), `ticket_cache` → `tickets`(D-238)로 바뀌었다.
   **컬럼 이름은 둘 다 그대로**다.
2. 적재 직후 `app/work/numbering.py::seed_counters()` 를 부른다.
3. **Project Key 20건은 확정됐다**(D-243). 순서는 하나다 — 프로젝트 적재 →
   `project_keys.apply_confirmed(db)` → `numbering.seed_counters(db)` → 재채번.
4. **날짜 컬럼 16개가 `date`/`timestamp` 다**(D-248). 소스 문자열을 그대로 대입하면
   못 읽는 값에서 **500** 이 난다 — `app/core/dates.py::parse_date`/`parse_dt` 를 지난다.
5. **본문을 옮길 때 앞판을 함께 넘긴다**(D-247). `blocks.derive(body, carry_from=앞판)` 을
   안 쓰면 재실행마다 판이 새로 쌓인다. 다리는 `documents.legacy_page_id`(부분 유니크)다.
6. **파일을 옮길 때 `app/storage/service.py::store_bytes` 를 지난다**(D-250).
7. **색인은 따로 안 만들어도 된다**(S9). 적재가 끝나면 색인 레인의 훑기가 상태 행이 없는
   문서를 전부 찾아 스스로 돈다. 급하면 `python -m app.cli.ai_cli reindex`.
8. 🔴 **색인 처리량은 D-211 의 120 docs/s 가 아니다.** 실제 본문 길이(중앙값 705자)에서는
   **11.7 chunk/s** 다(D-262). 용량 계산에 쓸 값은 이쪽이다.
9. 🔴 **Notion 사용자 매핑에 자동 조회가 없다.** S11 이 그 워크플로를 걷어냈다 — 매핑은
   이제 사람이 직접 지정한다. 적재가 매핑을 채워야 한다면 그것은 S13 의 일이고, 화면에
   그 버튼을 되살리는 것이 아니다.

## 상태 — 전환 축 다섯

| 축 | 현재 | 목표 | 소유 Session |
|---|---|---|---|
| **PostgreSQL** | **설치까지 끝났다.** `0007` 이 `vector` 확장을 켜고 `0008` 이 키워드 인덱스 둘을 걸고 `0009` 가 외부 자동화 표 넷을 내린다 | PG16 + pgvector + pg_trgm 이 System of Record | S2 ✅ · S4 ✅ · S9 ✅ · S10 ✅ · S11 ✅ |
| **SQLite 제거** | **Runtime 의존 0.** 다만 **운영 데이터는 아직 SQLite 에 있다** | Runtime 0 + 데이터 이관 완료 | S2 ✅ · S7 ✅ → S13·S14 |
| **Notion Migration** | **Runtime 의존 중이고 동기화 셋이 전부 실패 상태.** 미러 `tickets` 1,123 · `document_cache` 110 이고 **본문은 거의 비어 있다**. 받을 그릇과 검색·인용은 다 섰다 | Notion Runtime 의존 0, 데이터는 PG 로 | S13 → S14 |
| **AI** | ✅ **끝났다.** 권한이 앞서는 Hybrid Retrieval · 인용 · 생성이 서고, **옛 경로(n8n → 러너)를 걷어냈다.** 채팅·요약·퀴즈가 전부 한 문(`Gateway`)을 지난다 | Model Gateway + 권한이 앞서는 Retrieval + 옛 경로 0 | S9 ✅ · S10 ✅ · S11 ✅ |
| **Backup** | **기본형 + 설치 스냅샷 + 파일 저장소 이관.** `pg_dump -Fc` + 체크섬 + `--exit-on-error` 복원 + 파일 아카이브. **AI 색인은 일부러 백업 대상이 아니다**(D-203·D-204) | + Policy·Schedule·Retention·Manifest·복원 후 앱 기동 검증 | S2 ✅ · S4 ✅ · S8 ✅ → **S12** |

**Identity 축은 닫혔다** — 호스트명·TLS 는 S3, slug 는 S4, 역할·권한·가시성은 S5.
**남은 한 건은 세션 쿠키 이름**(`clovirone_session`)이고 S14 다 (`BACKLOG.md` **P-33**).

**UI 축(W0~W5)은 별개로 완료돼 있고 자산은 보존한다.** 근거와 수치는
[`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이고 재개는 Phase E(S15~S20)다 (D-207).

## 최근 테스트

S11 은 **지우는 세션**이라 검증의 성격이 다르다 — 「남은 것이 통과한다」로는 아무것도 증명
못 한다. 그래서 지운 자리마다 계약을 다시 세우고, 그 다음에 전 회귀를 돌렸다.

| 대상 | 결과 |
|---|---|
| 백엔드 전 회귀 (PostgreSQL) | **`FULL_REGRESSION_OK`** — unit · regression · security · integration 네 통 전부 초록이고 실패 0. ⚠️ **`pytest tests` 를 백그라운드로 직접 돌리면 안 된다**(P-09e). 그리고 **파이프 뒤에서 결과를 읽지 마라** — 이번에도 첫 회차가 `\| tail` 뒤에서 조용히 죽어 결과를 한 줄도 안 남겼다 |
| 프런트 전 회귀 (vitest) | **2,400 통과 · 3 실패** — 실패 셋은 전부 **S11 이전 것**이고 P-09a 소유다. S11 이 만든 실패 **0** |
| **제거가 유지되는가 (regression)** | **9건.** 지운 패키지를 다시 import 안 한다(정적) · 라우트가 없다 · 잡 종류에 핸들러가 없다 · **허용 목록이 죽은 포트로 못 나간다** · `AllowlistRegistry` 에 러너/워크플로 레인이 없다 · **배포·운영 산출물에 n8n 흔적 0** · 아카이브가 저장소에 있다 · 표 넷과 컬럼 둘이 스키마에 없다 |
| **채팅의 새 계약 (integration)** | **7건.** 답과 인용이 함께 나온다 · **모델은 인용된 글만 본다** · 🔴 **볼 수 없는 문서는 모델에게 안 간다**(넘어간 문자열로 본다) · 근거가 0 이면 모델을 안 부르고 그것은 실패가 아니다 · 생성이 막혀도 인용은 나온다 · **아무 데도 HTTP 를 안 보낸다** · 쿼터는 모델이 실제로 답한 경우만 센다 |
| **프롬프트 경계 (security)** | 러너 쪽 두 벌 대조가 사라진 자리에 **새 시험 둘**을 넣었다 — 러너 시절 방어가 안 걸려 있던 AI 퀴즈와 대시보드 요약이 이제 구분자 안에 갇힌다(여는 표지가 입력보다 앞이다) |
| **셋업 체크리스트 (integration)** | AI 항목이 Gateway 를 읽는다 — 둘 다 되면 done · **검색만 되는 반쪽 상태를 따로 말한다**(D-201) · 아무것도 없으면 그렇게 말한다 |
| 마이그레이션 왕복 | `upgrade`→`downgrade`→`upgrade` 를 실 PG 에서. 표 98→**94** · 인덱스 391→**383** · 제약 955→**905** 이고 되감기가 **대칭**이다 |
| 모델 ↔ 스키마 | autogenerate diff **0** — 표 넷과 컬럼 둘을 내린 뒤에도 모델과 스키마가 같다 |
| `check_test_strength.py` | 자기검증 7 → **11사례**(삭제 선언 파싱 4 추가, **반례 둘 포함**). 삭제 17건이 전부 명명됐고 약화 0 |
| 프런트 번들 | 다시 만들었다. 초기 gzip **263KB**(예산 280) · CSS 29KB · `BUNDLE_FRESH_OK` |
| `static_checks.sh` | S11 이 만든 실패 **0**. 남은 셋은 전부 P-09a 소유(가운뎃점·em 대시 6 · subprocess encoding · `tokens.css` 드리프트) — S10 시점 9건에서 **6건으로 줄었다**(지운 화면이 갖고 있던 셋이 함께 사라졌다) |
| 서버 실측 | [`EVIDENCE/S11/service_removal.txt`](EVIDENCE/S11/service_removal.txt) — 다섯 포트 미청취 · `list-unit-files` 0건 · 제품 서비스 5종 active · failed unit 0 |

## NOW

**S11 은 끝났다.** 옛 AI 경로가 사라졌고, 그 자리에 남은 것은 권한을 먼저 보는 한 경로다.

이 세션에서 가장 값이 나간 것은 지운 줄 수가 아니라 **지운 것이 돌아오지 않게 만든 것**이다.
삭제는 그 자체로는 아무 시험도 남기지 않는다 — 오히려 시험을 함께 지우므로 초록이 늘어난다.
그 초록을 완료로 읽는 것이 이 종류의 작업에서 가장 흔한 실패다.

두 번째는 **이관이 방어를 넓혔다**는 것이다. AI 퀴즈와 대시보드 요약은 러너 시절 프롬프트
방어를 안 지나고 있었다 — 옮길 자리를 `Gateway.generate()` 하나로 정했더니 그 둘이
자동으로 그 안에 들어왔다. 기능을 보존하려고 한 일이 보안 구멍 둘을 함께 닫았다.

세 번째는 **부를 곳 없는 조각을 함께 걷어낸 것**이다. 알림 유형 둘, 도달 불가능한
엔드포인트 하나, 고를 수 있지만 매번 실패하는 스케줄 대상 하나, 아무것도 안 가리키는
컬럼 둘. 전부 오류를 안 내면서 「아직 쓰는 기능」이라고 거짓말하고 있었다.

## NEXT — 다음 시작점: S12 (요청 시)

**S12 = Backup / Restore 운영.** 사용자 요청 없이 착수하지 않는다.
범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1, Backlog 는 **P-22**(+**P-23a**).

S11 이 다음 Session 에게 넘기는 것:

1. **`backup-cron.sh` 에서 n8n 절이 빠졌다.** 이제 그 스크립트는 플랫폼 백업과 보존 정리만
   한다 — S12 가 Policy·Schedule·Retention 을 제품 안으로 가져올 때 그 셸 스크립트가
   어디까지 남을지가 첫 질문이다.
2. 🔴 **`scripts/restore_rehearsal.py` 는 아직 SQLite 전제다**(P-23a). 8단계 중 7단계
   (**복원본으로 앱을 띄워 읽기 경로 호출**)가 저장소에서 가장 정직한 검증 자산이고,
   S2 가 그 전제를 깨뜨린 뒤 **큰 소리로 멈추게** 해 뒀다. 그 초록을 믿고 복원 계획을
   세우는 것이 가장 나쁘다.
3. **서버에 2.7GB + 738MB 가 「치워 둔」 채로 있다.** `/var/backups/n8n-s11` 과
   `/var/lib/n8n.removed-s11`. 백업 용량을 재는 세션이므로 이 둘을 계산에 넣거나,
   사람 확인 뒤 회수한다.
4. **`app/llm` 은 아직 산다.** 주간 리포트 요약이 그 경로를 쓴다 — 지우면 그 기능이 멈춘다.
5. **`user_notion_mappings` · Notion Console · Notion Mapping Console 은 S14 다.** S11 은
   그 기능의 **n8n 전송 계층**만 걷어냈다.

## RISK — 지금 살아 있는 것

전체는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §12.

| # | Risk | 상태 / Owner |
|---|---|---|
| ~~R1~~ ~~R2~~ ~~R3~~ | (S2 가 닫음) | 해소 |
| ~~R4~~ ~~R5~~ ~~R6~~ ~~R7~~ | (S1 이 닫음) | 해소 |
| ~~R9~~ | **러너 6,395줄 중 무엇이 이관 대상인가** | **해소 (S11)** — 이관 대상은 **없었다.** 의도 분류·규칙 기반 질의·JSON Schema 강제는 S9·S10 이 이미 제품 안에 세웠고, 남은 것은 Notion API 를 직접 두드리는 코드였다(옮길 것이 아니라 S14 가 지울 것) |
| ~~R13~~ ~~R14~~ | 제품 slug · 설치 자동화 | 해소 (계약 이행은 매 Session 이 계속 진다) |
| ~~R15~~ | LXD 컨테이너가 실 장비와 다르다 | **해소** — 재부팅 축은 S4(D-229), Storage 축은 S8 이 **호스트에서** 닫았다 |
| ~~R17~~ | pgvector 검색 품질 | **해소 (S10)** — MRR@10 0.7553 → **0.8869**(D-260) |
| R11 | **시험 Storage 가 실 NAS 와 다르다** | **살아 있다(의도한 대로)** — 실 정보 수령 시 **설정만** 바꾼다 |
| R16 | GitLab 주소 부재 | **완화** — Installer 가 Remote 중립이다 |
| — | **검색 품질을 업무 기록으로는 아직 못 쟀다** | **살아 있다** — 미러에 본문이 없다. 하네스는 그대로 있고 다시 재는 자리는 **S13 이후**다(D-262) |
| — | **저장소 장애 중 쓰기가 21초~180초 이상 걸린다** | **알려진 성질**(D-251) |
| — | **색인 레인이 안 뜨면 검색 결과가 조용히 낡는다** | **완화** — `ALWAYS_ACTIVE_UNITS` 에 있어 재부팅 판정과 Stage 17 이 본다. 그래도 **아무 오류도 안 나는** 종류의 실패라 감시 대상이다 |
| — | **운영 서버의 옛 빌드는 이제 채팅이 안 된다** | **의도한 결과 (S11)** — 그 빌드가 부르던 n8n 이 없다. 새 빌드 설치는 S13·S14 |
| — | **운영 데이터가 아직 SQLite 에 있고, 운영 서버는 아직 옛 slug 설치다** | S13 · S14 |

## BLOCKERS

- **없음.**

## 입력 — Blocker 는 아니지만 다음 Session 이 알아야 하는 것

| 항목 | 상태 |
|---|---|
| **20개 Project Key 명명** | **확정됐다** (2026-08-22 · D-243). 정본은 `app/work/project_keys.py::CONFIRMED`, 사람이 읽는 사본은 [`PROJECT_KEYS.md`](PROJECT_KEYS.md). **지금 적용된 프로젝트는 0건이고 그것이 정상이다** — PG 의 `projects` 가 비어 있다(적재는 S13) |
| **테스트 서버 접속** | **쓸 수 있다** — `10.100.64.71` 한정. SSH 키 인증 · sudo 는 `dist/ops/server.env`(gitignore). 값을 tracked 파일·커밋·로그에 복사하지 않는다 |
| **n8n 을 되살려야 한다면** | `/var/backups/n8n-s11/` 에 DB 스냅숏 · 유닛 · `/etc` · `/opt` 원본이 그대로 있고 `SHA256SUMS` 가 붙어 있다. 데이터 디렉터리는 `/var/lib/n8n.removed-s11` 이다 |
| **임베딩 모델 파일** | **테스트 서버에 셋 다 있다** — `~/s1bench/models/`. 설치처에 넣는 것은 `deploy/install.sh ai --ai-model-dir <디렉터리>` 이고 **네트워크로 안 받는다**(D-259) |
| **S9·S10 검증 하네스** | 서버의 `~/s9verify` · `~/s10bench`. 이 서버에는 **PostgreSQL 이 없다** — DB 축은 개발 머신의 실 PG 가 본다 |
| **S9 이 쓴 LXD 컨테이너** | **지웠다.** 다시 만들려면 `sudo bash scripts/lxd_rehearsal.sh <src.tar.gz> <이름>`. **S11 은 설치 축을 안 건드렸다** — 새 유닛도 새 Stage 도 없다(뺀 것만 있다) |
| **테스트 서버의 시험 Storage** | **세워 뒀다** — NFS export `/srv/clv-nfs-export` · Samba share `/srv/clv-smb-share` · 마운트 `/mnt/clv-nfs`·`/mnt/clv-smb`(재부팅 복귀 확인) · 시험 계정 `clvsvc`. SMB 자격증명은 `/etc/clovirassist/secrets/smb_matrix`(0600, root)이고 **값은 저장소에 없다** |
| **LXD** | 이 서버에 **초기화해 뒀다**. **`/dev/kvm` 이 없어 LXD VM 은 못 쓴다** — 실 재부팅이 필요하면 서버 자체를 재부팅한다 |
| **canonical 호스트** | `https://clovirassist.gooddi.lab` → 10.100.64.71. 옛 이름은 DNS 에 없다(NXDOMAIN). 인증서는 자체서명이고 사본이 `dist/ops/` 에 있다 |
| **하네스를 원격에 겨눌 때** | `UI_QA_TLS_CA` 로 그 인증서를 준다. **Chromium 의 페이지 이동만은 운영체제 신뢰 저장소를 본다.** QA 계정 `ui-qa@goodmit.co.kr` 은 **보관 상태**다 |
| **시험용 PostgreSQL** | 개발 머신 컨테이너 `clovir-s2-pg`(포트 55433 · 이미지 `pgvector/pgvector:pg16`). `CLOVIR_TEST_PG_URL` 로 덮어쓴다(주소는 `postgresql+psycopg://` — `psycopg2` 는 안 깔려 있다) |
| **전 회귀를 돌릴 때** | **`scripts/run_full_regression.sh` 를 쓴다.** `pytest tests` 를 백그라운드로 직접 돌리면 14% 근처에서 **CPU 0 으로 멈춘다**(P-09e). 그 러너는 `< /dev/null` 을 붙이고 통을 넷으로 나눈다 |
| **회귀 결과를 읽을 때** | **파이프 뒤에서 읽지 않는다.** `pytest … \| grep …` 의 `$?` 는 **grep 의 종료코드**다. 결과는 **파일로 받는다** — S11 이 이 함정을 다시 밟아 한 회차를 통째로 버렸다. 그리고 **도는 시험 아래에서 소스를 만지지 않는다** |
| **파이썬으로 파일을 다시 쓸 때** | `Path.write_text` 는 윈도에서 `\n` 을 **CRLF 로 바꾼다.** 배포 자산이 그렇게 되면 리눅스에서 `set -euo pipefail\r` 로 죽는다 — `static_checks.sh` 가 그것만 보는 검사를 갖고 있다 |
| **프런트를 고쳤을 때** | `cd frontend && npm run build` → `python scripts/check_bundle_fresh.py --write`. 안 하면 git 으로 설치한 서버가 **아무 오류 없이 옛 화면을 계속 돌린다** |
| **원격에서 오래 걸리는 명령을 돌릴 때** | **하네스가 걸릴 수 있는 자리에는 시간 제한을 건다.** 걸린 하네스는 결과를 한 줄도 안 내므로 「걸렸다」는 사실조차 증거로 안 남는다 |
| **`pg_dump`/`pg_restore`** | 개발 머신(Windows)에는 **없다**. `PG_BIN_DIR` 를 비워 두면 안 된다 |
| **Notion 토큰** | 운영 정본은 `/etc/clovirone-web-assistant/secrets/notion_{docs,report}_token`(0640, sudo), 개발 사본은 `var/secrets/`(gitignore) |
| 실 NFS/NAS 장비 정보 (현재 없음이 **확인됨**) | 실 정보를 받으면 `storage_providers` 행의 `source`·`options` 만 바꾸고 `deploy/install.sh storage` 를 다시 돌린다 (U8·U9) |
| 제품 Domain 밖 Notion DB 3종 (179 · 23 · 9) | 기본값 = 이관하지 않음 (U19) |
| GitLab Repository 주소·자격증명 | Installer 가 Remote 중립이라 **주소가 정해지면 설정만 바꾼다** (R16) |

<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
