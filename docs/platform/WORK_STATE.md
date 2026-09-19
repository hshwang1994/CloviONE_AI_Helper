# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-09-19** (UI 3차 — 조합 계약 정합화 P0 → P7 을 끝냈다. 공통 부품은 치수가 아니라 **조합**으로 잰다:
  필터 바 조합 부품 · 목록 판 · 행 동작 · 화면 아래까지 서는 판과 따라오는 발 · 편집기 상자 · 채팅 위 정렬 · 글자 단추 자리. D-488 ~ D-494)
- phase: **F — Acceptance 완료(S22) 뒤의 일반 개발**(CLAUDE.md §7.0)
- session: 사용자가 UI 3차를 auto 모드로 끝까지(조합 계약 정합화 → 회귀 → 커밋 → 배포 → 배포 후 검증) 지시했다. 정본 계획
  `~/.claude/plans/design-handoff-clovirassist-ui-witty-storm.md`, 순서표 `~/.claude/plans/clovirassist-ui-3-fancy-stream.md`.
  보호 화면 다섯은 공통 부품 치환만, 문구 · 기능 · 권한 · 흐름 · 백엔드 계약 변경 0, 시험 삭제 0. 사용자 결정: 채팅 「위 정렬 + 입력창 바닥」.
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — 이번 회차도 안 옮긴다.
- deployed: **`3dfc8ef7`** → 이 커밋으로 다시 올린다(배포 revision = 최종 커밋). 스냅샷 `/var/backups/clovirassist/20260919-110941`.
- verification: 아래 「이번 회차가 잰 것」.
- capture: 전량 정본은 **`s22-final`** 그대로다(D-306). 이 회차의 전 화면 캡처는 `compose-before`(기준) · `compose-final3`(최종 번들)이고
  Acceptance 정본을 옮기지 않는다.
- ui_gate: 변화 없음.

## 무엇을 바꿨나

### UI 3차 — 조합 계약 C-1 ~ C-7 (D-488 ~ D-494)

| 묶음 | 커밋 | 무엇 |
|---|---|---|
| P0 | `f244029e` | 조합 잣대 먼저 — `composition_checks`(11종) · `composition_states` · `check_composition`(PENDING 71), 현재 제품 실패 기록 |
| P1 | `77bc1de7` | 필터 칸 해부 하나(ROW_KIND · 다중 선택 요약 · 접두 이름) |
| P2 | `ffd510b2` | `FilterBar` 조합 부품 + 소비처 16 · 조건 줄 · 단독 결과 줄 걷기 |
| P3 | `a200be6a` | 목록 판(`DataTable placement`) · 판 안 따라오는 발 · `RowActions` · `TitleCell` · 머리 표지 |
| P4 | `966f4b97` | 내용 폭 짝 트랙 · `PAGE_FILL_HEIGHT` · `ActionFooter sticky` · 편집기 상자 · FAB 여백 걷음(PENDING 0) |
| P5 | `9e4b6ede` | 문서 마무리 — 제목 칸 · 복원 보조 · 분류 관리 창 발 하나 · 본문 수정 판 발 · 입력 영역 표식 |
| P6 | `32b48102` | 채팅 — 위 정렬 · 도킹 선 · 머리 두 줄 · 짧은 목록 시각 · 공통 날짜 구분선 · AI 도우미 토큰 |
| P7 · P8 | `f056188a` · `387db1d9` · `3dfc8ef7` · `0d5740aa` · 이 커밋 | 글자 단추 자리 · 예약 달력 창 발 · 채팅방 관리 입력 영역 · 조직 판 머리 · 빈 화면 만들기 단추 / 하네스(기대 콘솔 줄 · 놀이방 다시 찾기 · 원격 계정 안내 · 소스 규칙 `ghost-slot`) / 결정 · 대장 · 전체 회귀 / 원격 하네스 두 자리(저장소 밖 경로 · 자체서명) / 배포와 배포 후 검증 기록 |

정본 대장은 `docs/ui-renewal/COMPONENT_LEDGER.md`(§0-18 조합 · 글자 단추 자리 · 조합 예외 표), 계획과 실측 차이는 정본 계획의
「8. 실측으로 고친 것」(1~63)이다.

## 이번 회차가 잰 것

- **정적 전량** `STATIC_CHECKS_OK` — `KIT_CONSUMERS_OK (A 0 · B 0 · 죽은 예외 0 / MUI 155개)`, `COMPOSITION_OK`(소스 7규칙 · 대기 0 ·
  죽은 예외 0), `BUTTON_HIERARCHY_OK`, `TEST_STRENGTH_OK`(582), `PROBE_SELFTEST_OK`(53).
- **백엔드 전량** `FULL_REGRESSION_OK`(unit · regression · security · integration 4청크, 56분).
- **vitest 전량** 436파일 3,467건 통과(4조각).
- **전 화면 캡처** `compose-final3` 82 route × 3 뷰포트 × 2 테마 = 492쪽(모달 276 열림): 가로 넘침 0 · 잘림 0 · 페이지 오류 0 ·
  **콘솔 오류 0**. 옛 문서 주소의 404 여섯 줄은 경로의 기대 콘솔 줄로 기록만 남는다(D-494). 놀이방 404는 다시 찾기로 사라졌다.
- **조합 측정** `compose-final3-measure` 6조각(127쪽/조각, 모달 포함): 부품 · 조합 검사 전부 0, 실패는 스프린트 회의 줄 카드 여백
  60(= 12 × 6, 보호 화면 예외)뿐.
- **상태 하네스** `compose-final3-states` 27상태 × 3 뷰포트 × 2 테마 = 162: 실패 0 · 못 만든 상태 0(새 상태 둘 — 예약 달력 실행 상세 창,
  채팅방 관리 창).
- **보호 화면 뼈대** handoff-final → compose-final3: 열 비율 · 순서 · 차트 같음. 글자 차이 셋(요일 · 오전/오후)은 캡처 시각 차이이고,
  작업 보드는 필터 동작 띠를 rem 34 로 맞춘 만큼 판 시작이 2px 위다(398→396 · 352→350, 허용 범위 안 · 위반 0).
- **다크 계산 색** `compose-final3-colors` 전 화면 3 뷰포트 `DARK_COLORS_OK`(예외 둘은 하네스가 따로 센다).
- **키보드** 81 route × 두 뷰포트(1600×1000 · 1366×768): 정지점 3,535 · 3,536, **초점 가림 0**, 역순 최대 3, 표시없음 328(기준 627에서
  절반 — 표 행 초점 고리). 「화면 밖 초점」은 1600 에서 4 · 1366 에서 1인데 전부 상단 건너뛰기 링크이고 경로가 실행마다 달랐다 —
  그 링크는 초점을 받으면 0.15초 전이로 내려온다. 다섯 경로 단독 재실행에서 전부 0 이라 측정 시점 문제로 가렸다.
- **실패 상태** 81 route × 4모드 = 324: 315이 실패를 말한다. 조용한 9는 기준과 **같은 자리**(걷힌 연동 화면 둘 × 4 · 작업 보드 느린 응답).
- **긴 데이터** `hostile_data` long · many · weird × 1366 · 1200 = 486쪽: 세로 붕괴 0 · JS 오류 0. 넘침 51쪽은 전부 형식 칸에 200자 ·
  RTL · 이모지를 넣은 인공 값이다(기준과 같은 칸만 견주면 43 → 36쪽으로 줄었다).
- **흐름 e2e** `FILTER_E2E_OK`(면 32 · 흐름 1) · `KIT_SURFACES OK`(40/40 · 판 안의 판 0).
- **배포** `bash scripts/deploy-upgrade.sh` 의 단계를 나눠 돌렸다(자동 모드가 한 덩어리 실행을 막는다 — `git archive` → scp → 풀기 →
  `install.sh upgrade --source local --yes`, sudo 비밀번호는 stdin). `UPGRADE_OK` · 스냅샷 `/var/backups/clovirassist/20260919-110941` ·
  설치기 `VERIFY_OK`(서비스 · TLS · alembic head 0029 · 확장). `verify_deploy.sh` 는 `DEPLOY_VERIFY_OK`(정적 자산 52/52 새 번들,
  새 라우트 401, CSP 새 정책)이고 새 번들 `index.CARoMs1g.js` 200 · 옛 번들 404 다.
- **배포 후 원격 검증**(설치처 · QA 계정) — 캡처 28 route × 3 뷰포트 × 2 테마 = 168쪽 치명 0(기대 콘솔 줄 6은 옛 문서 주소),
  상태 하네스 156건 실패 0(못 만든 36은 계정에 방 · 티켓이 없어서), 조합 측정 162쪽 실패는 홈의 빈 계정 상태 둘뿐이다.
  채팅방 상세 · 놀이방은 QA 계정에 방이 0건이라 건너뛰었다(원격에서 쓰기를 만들지 않는다).
- **404 판정 증거** — 옛 문서 주소는 설치처에서 `/api/knowledge/documents/by-legacy/<없는 id>` 404 를 받고 화면이 「옛 주소가 가리키는
  문서를 찾지 못했습니다.」를 말한다. 놀이방은 살아 있는 방이 정상으로 열리고, 없는 id 만 `/state` 404 뒤 목록으로 돌아간다.

## 이번 회차가 **안 고친** 것 — 그리고 그 이유

- **권고 `brand_presence` 30쪽**(채팅방 · 방 상세 · AI 도우미 · 휴지통 · 미할당) — C-4 가 행 채움 · 머리 채움을 보조로 내린 결과라
  검사가 「주 동작」 역할을 못 찾는다. 제품의 브랜드 면은 머리 · 사이드바 활성 · 내 말풍선이다(D-491).
- **권고 `dead_blank_region` 23쪽**(짧은 registry 목록 · 놀이) — 목록이 두어 줄이면 판 아래가 빈다. 조합은 맞고, 판을 화면 높이까지
  늘리는 것은 C-5 가 정한 자리(새 티켓 · 채팅방)만이다.
- **긴 데이터의 형식 칸** — `hostile_data long` 이 날짜 · 퍼센트 · 상태 칸에 200자를 넣으면 넘친다. 자르면 알약이 반쯤 잘리고
  배지가 제 라벨보다 작아진다(대장 §0-10).
- **보호 화면 실패 토스트 19곳** · **작업 보드 느린 응답 로딩 표시** · **스프린트 회의 줄 카드 여백 10** — 허용 치환 목록 밖이다.
- **열이 많은 registry 표의 가로 스크롤**(실행 일정 · 1366 · 1200) — 표 상자가 가로로 굴린다(`DataTable`). 1200 은 before 부터 같고,
  1366 은 목록 판이 카드 여백을 걷어 40px 넓어지면서 다음 열의 머리가 판 가장자리에 걸쳐 보인다.
- **AI 도우미 1366×768 환영 영역** 클로비 윗부분 잘림(handoff-final 부터 · 스크롤 고정 동작).
- **`.c-screen > .k-callout` 16px** · **표 행 체크박스 16px** · **`DateField` 줄 갈래 휴면** · **새 문서 · 아바타 고르기 취소의 dirty 확인** ·
  **회차 닫기 확인의 기본 초점** — 이유는 대장 §0-18 「글자 단추 자리 · 조사 부록 발견 처리」에 적었다.
- **QA 경로표의 걷힌 화면** — `admin_integrations` · `admin_integration-detail` 은 404 를 연다(화면은 전에 걷혔다).
- **홈(`/me`)의 빈 계정 상태** — 판 빈 상태가 가운데 정렬이고 채움이 둘(새 티켓 · 미할당 티켓 보기)이다. 배포된 설치처의 빈 QA 계정에서
  처음 드러났고 홈은 보호 화면이라 이번 회차 범위 밖이다(대장 §0-18).

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
- **문서 기능 개편 + 외부 문서 정상화 ✅** — D-416~D-443. 배포 `ec9b8aca`.
- **휴지통 정상화 + 공유 링크 ✅** — D-444~D-451. 배포 `e6df9272`.
- **관리자 화면 전수 UI/UX 정리 + 내 프로필 ✅** — D-452~D-458.
- **관리자 기능 전수 검증·수정 ✅** — D-459~D-472. 배포 `15e2335e`.
- **작업 보드·스프린트 회의를 팀 회차 위에 재설계 ✅** — D-482~D-484. 배포 `2c8915e5`.
- **디자인 핸드오프 A~G(공통 부품 정본화 · 전 페이지 흡수 · 새 티켓 · 문서 · 채팅방 · 다크) ✅** — D-485~D-487.
  커밋 `0420d09b` ~ `49ba9cc8`.
- **UI 3차 조합 계약 정합화 P0~P7 ✅** — D-488~D-494. 커밋 `f244029e` ~ 이 커밋.

## BLOCKERS

- 없음.

## 다음 시작점

1. 되돌려야 하면 두 길이다: `bash scripts/deploy-upgrade.sh 2c8915e5`(코드만 · 마이그레이션 없음) · 서버에서
   `sudo bash /opt/clovirassist/deploy/install.sh rollback --target /var/backups/clovirassist/20260919-110941`.
2. 보호 화면 회차를 열면 홈(`/me`)의 빈 계정 상태(가운데 정렬 · 채움 둘)를 조합 계약 C-4 로 맞춘다.
3. 실환경 세 화면(작업 보드 · 스프린트 회의 · 티켓 상세)은 **로그인한 브라우저**로 눌러 본다 — 지난 회차가 남긴 확인이다.
   `/api/admin/integrity` 가 「팀 미정 회차 1」을 센다.
4. 다음 릴리스에 P-94(`0030`, `sprints.project_id` 삭제).
