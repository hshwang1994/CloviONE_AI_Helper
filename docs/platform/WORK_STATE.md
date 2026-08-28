# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-28** (작업 보드 · 스프린트 회의)
- phase: **F — Acceptance 완료(S22).** 그 뒤는 CLAUDE.md §7.0 의 **일반 개발**이다
- session: **작업 보드 · 스프린트 회의 재설계** — 칸반·논의·후보가 같은 티켓 얼굴을 쓰고,
  상태 KPI와 논의 버킷으로 건수를 읽게 한다. 회의 화면은 차트 짝 판과 요일 라벨을 붙인다.
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **이번 회차도 안 옮긴다.** 이유는 S11~S22 와 같다 — 그 기준을 옮기는 순간 그동안 지운
  시험들이 검사 시야에서 사라진다.
- working_tree: clean
- s22_commit: `2f4fc587` · `1921f884` · prev_commit: `ca49e7d8` · `3804bc0e` · `91bf3af9`
- this_commit: **`31bfb341`** — 작업 보드 · 스프린트 회의 재설계
- deployed: **`31bfb341`** 이 운영에 나갔다 (2026-08-28 16:32 · `install.sh upgrade --source local --yes`).
  Stage 0~18 전부 OK · `VERIFY_OK` · `UPGRADE_OK` · 스냅샷 `/var/backups/clovirassist/20260828-163250`.
  스키마는 안 건드렸다 — alembic 이 `0024_technology_tags` 에서 그대로다(표 94개 · 사용자 26명).
  **이번 커밋의 것이 실제로 올라갔다**: 진입 번들 `index.DPCnHHw3.js` · `WorkBoard.9wriO0YU.js` ·
  `UserRoutes.HklDhJl7.js` 가 운영에서 200 이다. 옛 `WorkBoard.CLmlRt1q.js` 는 404.
  스모크: `/healthz` `{"status":"ok","ticket_source":"native"}` 200 · `/readyz` `{"status":"ready"}` 200.
  제품 유닛 여섯 + nginx + postgresql 전부 active.
  되돌리려면 `sudo /home/cloviradmin/clovirassist-upgrade/deploy/install.sh rollback --target /var/backups/clovirassist/20260828-163250`
- deployed_prev: `93c6ce76`(2026-08-28 15:20 · 스냅샷 `20260828-152003`)
- verification: 이번 회차도 **표적**이다(§7.0 일반 개발). 작업 보드·스프린트·차트·밀도 관련
  vitest가 통과했고, 배포 뒤 `/healthz` · `/readyz` · 새 번들 자산이 200 이다.
- browser: 운영에 새 번들이 나갔다. 이 회차는 1366·1920 실브라우저 레이아웃 실측을 안 했다.
- capture: 전량 정본은 **`s22-final`** 그대로다. 이번 회차도 캡처 하네스를 안 돌렸다.
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

## 이번 회차가 한 것 — 작업 보드 · 스프린트 회의

작업 보드와 스프린트 회의가 같은 티켓 얼굴(`TicketFace`)·상태 KPI(`StatusKpi`)·논의 버킷
(`DiscussBucket`)을 쓴다. 칸반 카드는 애니메이션이 없고, 차트 툴팁은 HTML로 켠다. 백로그는
상태가 아니라 `sprint_id IS NULL` 이다. 스키마·권한·채번 계약은 안 건드렸다.

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
- **화면 셋 고도화 + Legacy 정리 ✅** — 결정 **D-335~D-340**.
- **화면 셋 UI/UX 마무리 ✅** (`b3c368c6`) — 홈 판의 높이 범위 · 레일 폭 · 「최근 완료 추이」
  비율 · 낱말 · 관리자 「운영」 세 묶음. 결정 **D-341~D-345**.
- **대시보드 높이 예산 ✅** (`ca49e7d8` · `3804bc0e`) — 판마다 바닥과 천장을 함께 주고, 자라는
  것은 판이 아니라 판 안의 한 칸이 맡는다. AI 도우미의 탭이 `{ head, detail }` 두 조각을 내고,
  `stickyHeader` 를 켠 표의 감싸는 상자가 스스로 안 굴러간다. 결정 **D-346 · D-347**.

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
