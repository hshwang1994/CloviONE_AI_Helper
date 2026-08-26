# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-26** (홈·AI 도우미·관리자 대시보드 고도화 뒤)
- phase: **F — Acceptance 완료(S22).** 그 뒤는 CLAUDE.md §7.0 의 **일반 개발**이다
- session: **화면 셋 고도화 + Legacy 정리** — 사용자 홈(`/me`) · 그 안의 AI 도우미 ·
  관리자 대시보드. 🔴 **관리자 대시보드가 정상 제품을 매일 장애로 그리고 있었다** — 걷어낸
  런타임 넷의 연동 등록 행이 살아 있었고(D-338), 그 넷이 필수 서비스와 같은 분모에 들어가
  「서비스 정상 3 / 7」을 만들었다(D-337). 아래 「이번 회차가 한 것」 절.
  결정 **D-335~D-340**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **이번 회차도 안 옮긴다.** 이유는 S11~S22 와 같다 — 그 기준을 옮기는 순간 그동안 지운
  시험들이 검사 시야에서 사라진다.
- working_tree: clean
- s21_commit: `ede55e47` · `916f20fe` · s22_commit: `2f4fc587` · `1921f884`
- this_commit: **`44520b66`** — 화면 셋 고도화 + Legacy 정리
- deployed: **`44520b66`** 이 운영에 나갔다 (2026-08-26 10:26, `install.sh upgrade --source local`).
  Stage 0~18 전부 OK · `VERIFY_OK` · `UPGRADE_OK` · 스냅샷 `/var/backups/clovirassist/20260826-102648`.
  🔴 **0017 이 실제로 도는 것**이 로그에 찍혔다 — 「걷어낸 런타임의 연동 등록 행 4개를
  지웠습니다」. 배포 뒤 운영 `integrations` 표는 **0행**이고, 그래서 관리자 대시보드의
  「외부 연동」은 이제 「추가된 외부 연동이 없습니다」다(장애가 아니라 정상 상태다).
  스모크(비파괴): `/healthz` `{"status":"ok","ticket_source":"native"}` · `/readyz`
  `{"status":"ready"}` · `ssl_verify_result=0` · `/login` 200(12,332바이트) ·
  번들 `index.CV9dZmOE.js` 200(132,245바이트) · `/` 303 ·
  세 화면이 부르는 API 다섯(`/api/home/today` · `/api/home/work-dashboard` ·
  `/api/assistant/briefing` · `/api/admin/dashboard` · `/api/me`)이 **404 가 아니라 401**.
  **운영이 내보내는 번들이 이 저장소가 만든 번들과 같은 바이트**임을 sha256 으로 확인했다
  (`index.CV9dZmOE.js 7d4398839974f51f` · `BUILD_STAMP 4afb3306…`).
  브라우저 전수는 운영에서 안 돌렸다 — 운영 데이터를 확인 편의로 건드리지 않는다.
  되돌리려면 `sudo /opt/clovirassist/deploy/install.sh rollback --target /var/backups/clovirassist/20260826-102648`
- deployed_prev: `2f4fc587`(S22, 2026-08-26 04:33 · 스냅샷 `20260826-043036`)
- verification: 이번 회차는 **표적**이다(§7.0 일반 개발). `STATIC_CHECKS_DEV_OK` ·
  vitest 전량 **335 파일 / 2,488건 통과**(공용 부품을 건드려 전량으로 넓혔다) · 백엔드는
  바뀐 축의 표적(setup checklist · dashboard metrics · health · integrations API ·
  external automation removed · 0017 회귀 · wordmark) 전부 통과 · `TARGETED_OK`.
  S22 의 전량(`FULL_REGRESSION_OK`)은 `2f4fc587` 기준으로 그대로 유효하다
- capture: 전량 정본은 **`s22-final`** 그대로다(81 라우트 × 2 테마 × 9 뷰포트 = 1,440페이지 ·
  승격 검사 열 종 실패 0). 이번 회차는 **바꾼 화면 둘만** 다시 찍었다 —
  `hi-me-admin2`(user_me · admin_dashboard × 4 뷰포트 × 2 테마 · 치명 실패 0).
  **부분 캡처는 전량 원장을 안 덮는다**(D-306) — `capture_labels.after` 를 옮기지 않았다
- ui_gate: `--stage plan` **PASS**. `--stage wave`(W15)는 **초록이 아니다** — 남은 것은
  **P-44** 의 기록 형식(사슬의 서버 칸 982)과 그것이 붙잡고 있는 축들이다. 상세는
  [`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md)
- 스키마는 **93 표**다. alembic head 는 **`0017_drop_retired_integrations`** 다 — 표를 만들거나
  지우지 않았고, 걷어낸 런타임의 **등록 행 넷**만 지운다(D-338)

## 🔴 운영이 PostgreSQL 위에서 돈다

`10.100.64.71` 의 `/healthz` 가 `{"status":"ok","ticket_source":"native"}` 로 답한다.
데이터는 전부 넘어갔고 서비스는 열려 있다. 원장은 [`EVIDENCE/S14/`](EVIDENCE/S14/README.md).

| | |
|---|---|
| 사용자 · 프로젝트 · 티켓 | 26 · 22 · **1,145** |
| 티켓 번호 | 1,130건에 붙어 있고 **중복 0** · 고유 1,130 · 나머지 15 는 컷오버 뒤 만든 native 티켓이다 |
| 프로젝트 코드 | **22 / 22** · 중복 0 · 전부 여섯 자 대문자 · UNIQUE 인덱스가 지킨다 |
| 첨부 | `files` 58 · 티켓 첨부 237 · 문서 첨부 54 · **DB 가 가리키는 바이트 누락 0** |
| 이관 예외 | 미해결 11 — 그중 사람이 프로젝트를 정해야 하는 **9 건은 `/integrity` 가 전부 보여 준다**(P-52) |
| 옛 이름 층 | **없다** · 옛 포트(5678·5679·8787·8788·8789) 청취 **0건** · 그 포트를 가리키던 연동 등록 행 넷도 이제 없다(0017) |

## 이번 회차가 한 것 — 화면 셋 고도화 + Legacy 정리

### 1. 🔴 관리자 대시보드가 **정상 제품을 장애로** 그리고 있었다 (D-337 · D-338)

운영 `integrations` 표에 `n8n`(5678)과 러너 셋(8787·8788·8789)이 **활성**으로 남아 있었다.
넷 다 S11 이 걷어낸 런타임이고 그 포트에는 아무도 안 듣는다. 워커의 자동 헬스 스윕이 30초
마다 `down` 을 다시 적었고 화면은 그것을 「중단 · 위험」 네 줄로 맨 위에 올렸다. 그중
`clovirone-work-assistant` 는 **옛 제품 이름**을 관리자 화면에 띄우고 있었다(§10-13).

데이터를 고쳤다 — `0017_drop_retired_integrations` 가 **이름과 주소가 둘 다 맞는** 행만
지운다(반례 시험 포함). 제품에는 연동을 지우는 경로가 없어서(라우터에 DELETE 가 없다)
운영자가 콘솔에서 치울 방법이 애초에 없었다.

판정 모델도 고쳤다: 필수 서비스와 선택 연동의 **분모를 갈랐고**, 상태 어휘 다섯 중 빨간
것은 `down` 하나로 좁혔다(「사용 안 함」·「미점검」은 상태이지 장애가 아니다). 어휘는
`ops/opsHelpers.js` 한 곳에서 오고 진단 화면도 같은 함수를 쓴다. 화면의 순서는 이제
「지금 정상인가 → 조치할 것 → 필수 서비스 → 외부 연동 → 운영 자료 → 최근 주요 변경」이다.

### 2. 사용자 홈의 **빈 판**은 여백이 아니라 격자가 만들고 있었다 (D-335)

본문 격자가 한 줄이었고 그 뒤에 두 구역이 전체 폭으로 이어졌다. 한 줄 격자의 높이는 큰
칸이 정하므로 레일이 길면 왼쪽 카드 아래가 통째로 비었다(티켓 두 건인 계정에서 화면 절반).
지금은 격자가 **독립된 세로 흐름 둘**을 담고 **격자 뒤에 아무것도 없다**.

같은 회차가 **같은 수를 세 번 말하던 것**을 걷었다(D-336) — 「지연 12」가 판독 줄과 「내 업무」
줄에 나란히 있었고 AI 브리핑이 그 둘을 문장으로 한 번 더 읽었다. 내부 진단 문구
(「Health 를 계산하지 않은」·「점수의 신뢰도」)는 접힌 도움말로 내렸고, 완료 1건을 꽉 찬
막대로 그리던 추이는 **그 주 마감 건수**를 기준으로 바꿨다(D-339).

### 3. AI 도우미는 **숫자를 다시 읽지 않는다** (D-336)

네 탭이 같은 흐름을 쓴다: 요약 한 문장 → 주요 정보 → 세부와 시각화 → 필요한 Action.
요약은 사실에서 규칙으로 뽑고(지연 → 막힘 → 오늘 마감 → 곧 마감 → 진행 중) 그 순서를 단위
시험이 값으로 고정한다. 판 안에 판을 안 넣고 실선·여백·소제목으로 가른다(`SubGroup`).
탭 밑줄 이동 · 내용 등장 · 높이 전환 · 그림 reveal 을 짧게 넣되, **처음 보거나 값이 바뀐
것만** 재생한다(D-340). 동작 최소화를 켠 사람에게는 시작하지 않는다.

### 4. Legacy 잔재를 제품 전체에서 훑었다

지운 것: 걷어낸 런타임의 연동 등록 행 넷 · 아무도 안 읽는 옛 slug env 예시
(`deploy/web.env.example`) · 참조 0건인 옛 이름 브랜드 자산 다섯(`app/static/img/`).
고친 것: 사전 점검이 **현재 유닛을 모른 채** 옛 유닛만 보던 것(`00-precheck.sh`) ·
초기 설정의 「AI 러너」 단계와 「자동화 워크플로」 설명 · 「연동 0개」를 할 일로 세던 판정 ·
걷어낸 엔진을 현재 연동처럼 심던 씨앗과 픽스처 셋 · `.env.example` 의 옛 운영 경로 ·
INSTALLATION §10 의 낡은 현재형 문장.

**남긴 것도 정했다**(D-338): 옛 이름을 **읽는** 어휘(감사 대상 유형 · provider 라벨),
이관 계보(`user_notion_mappings` · `alembic/legacy_sqlite/` · 이관 CLI), 이전·되돌리기가
옛 설치를 찾는 자리, 역사 기록(사전 점검 산출물 — README 로 그 성격을 못 박았다).
큰 것 넷은 그대로 Backlog 다: **P-35 · P-37 · P-50 · P-52**.

## 완료

- **S0~S14** — 기반 · PostgreSQL · Identity/TLS · 설치 자동화 · RBAC · Work · Knowledge ·
  Storage · AI 1·2 · n8n 제거 · Backup/Restore · Migration · Cutover. 결정 D-187~D-284.
- **S15~S20** — Search/Filter 정확성 · Table/Grid · Empty/Loading/Error · Pilot Archetype ·
  나머지 User Route · 관리자 IA. 결정 D-285~D-321.
- **S21 ✅ — Functional E2E 전수 (W14).** Flow 809건을 실브라우저에서 눌러 766 PASS / 43 FAIL
  이고 `exists:true` 에 `NOT_AUDITED` 가 0 이다. 눌러도 아무 데도 안 가던 머리 버튼 일곱
  (D-324)과 자기를 지우던 검색 상자(D-325)를 고쳤다. 결정 **D-322~D-325**.
- **S22 ✅ — Final Audit · Full Capture · 설치 Acceptance (W15).** 판정은 **RELEASE READY
  WITH DOCUMENTED LIMITATIONS** 다. 되돌리기가 세 레인을 못 살리던 것(D-326·D-327), 설정
  보존이 죽은 줄까지 보존하던 것(D-328), 시각 결함 다섯(D-329~D-334)을 고쳤다. 결정
  **D-326~D-334**, 원장 [`EVIDENCE/S22/`](EVIDENCE/S22/README.md).
- **화면 셋 고도화 + Legacy 정리 ✅** — 위 「이번 회차가 한 것」 절. 결정 **D-335~D-340**.

## 상태 — 전환 축 다섯

| 축 | 현재 | 소유 Session |
|---|---|---|
| **PostgreSQL** | ✅ **System of Record 다.** 운영이 그 위에서 돈다 | S2 ✅ · S4 ✅ · S9~S14 ✅ |
| **SQLite 제거** | ✅ 끝났다 | S13 ✅ · S14 ✅ |
| **Notion Migration** | ✅ 끝났다 — 마지막 설정 잔재는 S22 가 걷었다 | S13 ✅ · S14 ✅ · S20 ✅ · S22 ✅ |
| **AI** | ✅ 끝났다 | S9 ✅ · S10 ✅ · S11 ✅ |
| **Backup** | ✅ 끝났다 — S22 가 **운영 데이터로** 다시 증명했다 | S2 ✅ · S12 ✅ · S14 ✅ · S22 ✅ |

**UI 축은 W15 까지 왔다.** 근거와 수치는 [`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).

## NEXT — 이 Transition/Renewal 계획의 Acceptance 는 끝났다

**새 Stage 를 자동으로 만들지 않는다.** S0~S22 로 세운 계획이 닫혔을 뿐이고, 이 제품의
다음 기능 개발은 평소대로 CLAUDE.md §7.0 의 일반 개발 흐름을 탄다.

남긴 것은 전부 Backlog 다 — 새 회차가 아니라 **소유자 없는 항목**이다:

1. **P-44** — 사슬의 서버 칸 982. 그 하나가 W8·W15 게이트의 마지막 축을 붙잡고 있다.
2. **P-54 · P-55 · P-56 · P-58** — S22 가 새로 적은 것 넷(넓은 화면의 빈 아래 / 곁열 판정
   위양성 의심 / 모달 검사 0회 실행 / 열 하나의 어휘 누락).
3. **P-50 · P-52** — 부르는 화면이 없는 라우터 둘. P-52 의 남은 물음은 S22 가 답했다.
4. **P-57** — 설치 로그 보관 기간.
5. **P-35 · P-37** — 옛 문서 미러 표와 담당자 축 통합(플랫폼 축).

## BLOCKERS

- 없음.
