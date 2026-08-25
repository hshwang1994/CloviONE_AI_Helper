# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-26** (S22 뒤)
- phase: **F — Acceptance 완료.** S22 가 W15(Final Audit · Full Capture · 설치 Acceptance)를 닫았다
- session: **S22 — Final Product Audit / Final Acceptance / Release.** 판정은
  **RELEASE READY WITH DOCUMENTED LIMITATIONS** 다. 축 열하나를 한 번씩 완주했고 근거는
  [`EVIDENCE/S22/`](EVIDENCE/S22/README.md), 조건별 결과는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §10.1.
  🔴 **되돌리기가 세 레인을 못 살리고 있었다**(D-326·D-327) — 그 동안 `/healthz`·`/readyz` 는
  200 이었다. 아래 「S22 가 한 것」 절. 결정 **D-326~D-334**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S22 도 옮기지 않는다.** 이유는 S11~S21 과 같다 — 그 기준을 옮기는 순간 그동안 지운
  시험들이 검사 시야에서 사라진다.
- working_tree: clean
- s20_commit: `136b00aa` · `9a3ade64` · s21_commit: `ede55e47` · `916f20fe`
- s22_commit: **`2f4fc587`** — S22 본체(제품 결함 · 프로브 · 원장 · 문서). **배포 대상이다**
- deployed: **`2f4fc587`** 이 운영에 나갔다 (2026-08-26 04:33, `install.sh upgrade --source local`).
  Stage 0~18 전부 OK · `VERIFY_OK` · `UPGRADE_OK` · 스냅샷 `/var/backups/clovirassist/20260826-043036`.
  로그에 **D-328 이 실제로 도는 것**이 찍혔다 — 「걷어낸 런타임의 죽은 설정 줄을 지웠습니다」 둘.
  스모크: `/healthz` `{"status":"ok","ticket_source":"native"}` · `/readyz` `{"status":"ready"}` ·
  `ssl_verify_result=0` · `/login` 200(12,332바이트) · 대표 API 다섯이 **404 가 아니라 401** ·
  유닛 8종 active · 티켓 1,145 / 사용자 26 · `storage_cli status` `operational_ok: true`.
  **운영이 내보내는 번들이 캡처가 잰 번들과 같은 바이트**임을 sha256 으로 확인했다
  (`index.html 57956ba3…` · `index.DjLYTf33.js 6d949d74…`) — 브라우저 전수는 운영에서 다시
  안 돌렸다(운영 데이터를 인수 편의로 건드리지 않는다).
  🔴 **재부팅 복구를 실제로 쟀다**: `boot_id` 가 바뀌었고 **수동 명령 0회**로 유닛 8종 ·
  NFS·SMB 마운트 · health · ready · TLS · 데이터(1,145 / 26 / 58)가 전부 돌아왔다
  (`EVIDENCE/S22/reboot.txt` · Storage 매트릭스 10·11 `POST_REBOOT_PASS`).
  되돌리려면 `sudo /opt/clovirassist/deploy/install.sh rollback --target /var/backups/clovirassist/20260826-043036`
- deployed_prev: `916f20fe`(S21, 2026-08-26 00:02 · 스냅샷 `20260826-000222`)
- full_regression: **전량 0 실패** (2026-08-26). 정적 전량 `STATIC_CHECKS_OK` · 백엔드 전량
  `FULL_REGRESSION_OK`(unit · regression · security 757건 · integration 4청크) · vitest 전량
  **334 파일 / 2,464건 전부 통과**. S21 이 넘긴 빨간 것 여덟은 전부 **QA 부채였고 고쳤다** —
  걷어낸 화면(`/api/admin/notion-mapping`)을 겨누던 보안 시험 7건과 사이드바 항목 수 1건
- capture: **`s22-final`** — 81 라우트 × 2 테마 × 9 뷰포트 = **1,440페이지**, 승격 검사
  열 종 **실패 0**. 번들 지문 `57956ba3ea73d674`. 배율은 `s22-zoom` 이 따로 쟀다(112페이지 · 0)
- ui_gate: `--stage plan` **PASS**. `--stage wave`(W15)는 **초록이 아니다** — 남은 것은
  **P-44** 의 기록 형식(사슬의 서버 칸 982)과 그것이 붙잡고 있는 축들이다. 상세는
  [`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md)
- 스키마는 **93 표**다. alembic head 는 `0016_document_axis_to_documents` 다. **S22 도 스키마를
  안 건드렸다**

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
| 옛 이름 층 | **없다** · 옛 포트(5678·5679·8787·8788·8789) 청취 **0건** |

## S22 가 한 것 — Final Acceptance (W15)

### 1. 🔴 되돌리기가 **레인을 못 살리고 있었다** (D-326 · D-327)

`take_snapshot` 이 `/var/lib/<slug>` 를 통째로 담으면서 **워커 리스 파일 넷**까지 담았다.
`rollback` 은 유닛을 전부 멈추고(리스가 지워진다) → 스냅샷을 풀고(**리스가 되살아난다**)
→ 4초 뒤 유닛을 띄운다. 새 워커는 「다른 워커가 이미 돌고 있다(owner=6631@…)」 며 1 로
죽는다. 그 6631 은 스냅샷을 뜨던 순간의 프로세스이고 이미 없다.

그리고 **재시도가 리스보다 먼저 끝났다**: `RestartSec=10` · `StartLimitBurst=10` 이라
100초 남짓이고 리스는 120초를 산다. 배치·스케줄러·색인 세 레인이 **영영 안 돌아왔다** —
그 동안 `/healthz` 와 `/readyz` 는 200 이었다.

고친 뒤 반례까지 확인했다: **리스를 담고 있는 옛 스냅샷**으로 되돌려도 `ROLLBACK_OK` 이고
네 레인이 전부 `active` 다.

### 2. 시각 결함 다섯을 뿌리에서 고쳤다 (D-329~D-334)

전량 캡처가 승격 검사 넷을 115페이지에서 빨갛게 만들었다. 개수 열 둘이 어휘를 안 썼고
(D-331), 한 줄의 조작기가 두 높이로 섰고(D-332 — **px 리터럴이 4K 레버를 안 탄다**),
바닥을 맞추는 값이 폭까지 반씩 나눴고(D-333), 자리가 없는 화면을 「회색이다」로 셌다
(D-334). 프로브 문턱 둘은 절벽이었다(D-329 P-40 · D-330 P-43). 고치고 **같은 라벨로 전량을
다시 찍어** 승격 검사 실패 0 을 만들었다.

### 3. 설정 보존이 **죽은 줄까지 보존하고 있었다** (D-328)

운영 설치의 `env` 에 걷어낸 런타임의 키 둘이 남아 있었고 그 값은 **옛 제품 이름**을 담고
있었다. 앱은 그 키를 한 번도 안 읽는다. 설치기가 아는 이름만 지운다.

### 4. 나머지 축은 통과했다

설치 리허설 **35/35** · 복구 리허설 `RESTORE_REHEARSAL_OK`(운영 데이터 · 읽기 경로 13/13 ·
첨부 누락 0) · Storage 16항 실 NFS·SMB · 권한 어긋남 **0** · 재부팅 복구 · 데이터/채번/이관
실측. 조건별 결과는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §10.1.

## 완료

- **S0~S14** — 기반 · PostgreSQL · Identity/TLS · 설치 자동화 · RBAC · Work · Knowledge ·
  Storage · AI 1·2 · n8n 제거 · Backup/Restore · Migration · Cutover. 결정 D-187~D-284.
- **S15~S20** — Search/Filter 정확성 · Table/Grid · Empty/Loading/Error · Pilot Archetype ·
  나머지 User Route · 관리자 IA. 결정 D-285~D-321.
- **S21 ✅ — Functional E2E 전수 (W14).** Flow 809건을 실브라우저에서 눌러 766 PASS / 43 FAIL
  이고 `exists:true` 에 `NOT_AUDITED` 가 0 이다. 눌러도 아무 데도 안 가던 머리 버튼 일곱
  (D-324)과 자기를 지우던 검색 상자(D-325)를 고쳤다. 결정 **D-322~D-325**.
- **S22 ✅ — Final Audit · Full Capture · 설치 Acceptance (W15).** 위 절. 결정
  **D-326~D-334**, 원장 [`EVIDENCE/S22/`](EVIDENCE/S22/README.md).

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
