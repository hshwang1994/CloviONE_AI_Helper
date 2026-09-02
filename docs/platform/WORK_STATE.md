# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-09-02** (작업 보드·스프린트 회의·문서 페이지 결함 전수 수정 + 429 근본
  해소 — D-407~D-412)
- phase: **F — Acceptance 완료(S22) 뒤의 일반 개발**(CLAUDE.md §7.0)
- session: **「작업 보드·스프린트 회의에 버그가 너무 많고 난해하다, 요청 과다 에러가 지속된다,
  문서의 공간 추가는 왜 필요하냐」는 사용자 보고에서 시작해, 탐색으로 결함을 전수 확정하고
  (보드 B1~B16 · 회의 S1~S18 · 429 근본 2 · 문서 IA) 전부 뿌리에서 고쳤다.**
  ① **보안 둘**(음성 시험 빨간불 선행): 회의 범위 변경 갈래의 가시성 절 누락(타 팀 티켓
  유출)과 move() 담는 쪽 회차의 존재 오라클(400→404). 회차 상태 기계(planned↔active→closed
  종착·이월 축 검증)와 PATCH/DELETE API 도 세웠다 — D-407.
  ② **429 근본 둘**: 성공 로그인이 IP 예산을 안 되돌리던 것(RateLimiter.reset 호출 0건 —
  NAT 뒤 11번째 사람부터 429)과 ErrorState 의 429 자기 강화 루프(살아 있는 「다시 시도」).
  리셋은 옛 코드 빨간불로 증명, 화면은 retry_after 카운트다운 잠금 — D-409.
  ③ **보드**: 죽은 참조 둘(troubleOnly·setShowAll — 더 보기·빈 상태 버튼 즉사), 더 보기
  필터 계약 위반, 같은 칸 아래 이동 no-op(계약 교체), 섞인 판의 rank 이웃을 가시성 범위로
  (놓은 자리가 순위가 된다 — 마이그레이션 0), colExtra 중복, 자동선택 폴백 제거 + 진입 질의
  1회 게이트, 드래그 잠금·version 패치·카드 오버레이·받지 않는 칸, 백로그 연쇄 로드 차단,
  필터 위계(핵심 앞줄 + 상세 접이) — D-408·D-410.
  ④ **회의**: 프로젝트 전환 백지(프로젝트 키 자동선택), state×phase×역할 문구 매트릭스,
  부분 응답 정규화(normalizeMeeting), 서버 today 로 신호 판정, keepPreviousData 전환
  무깜빡, 30초 폴링 + 회의록 캐시 수술(전체 재조회 제거), 이웃 축 정확 일치(팀 회차 이웃
  오염 수정), 후보 잘림 표시, tablist 완성, 세로 예산(8828px→목록별 스크롤), 회의록
  확장(담당자·티켓 연결·수정 — 서버가 이미 지원하던 칸), 「회차에서 빼기」(D-376 잔여).
  ⑤ **문서**: 자리 축을 ?project= 로(none=공통 센티널 — 서버 PROJECT_FILTER_NONE 신설),
  새 문서가 전체 프로젝트를 고른다(공간 없는 11개 포함 — 서버 자동 생성 활용), 「공간 추가」
  UI 걷음(서버 API·SPACE_ADMIN 유지), 옛 ?space= 링크 변환, listRail 표준 트랙으로
  /knowledge·/organizations 통일 — D-411·D-412.
  ⑥ 요청 경제: invalidateTicketViews 에서 불변 후보 목록 제외 + refetchType:"all" 규약
  (삭제·복원급 전용), narrate staleTime 5분.
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — 이번 회차도 안 옮긴다(이유는 S11~ 와 같다).
- this_commits: `ebed4aca`(보안 서버) · `3ebcc0b5`(로그인 리셋) · `2f105b3f`(429 프런트) ·
  `dc41e76c`(보드 죽은 참조) · `eee380b0`(회차 선택) · `8c70623e`(DnD) · `e32c65f2`(rank) ·
  `4eacdb81`(요청 경제) · `a92366ac`(필터 위계) · `f710d576`(회의 견고화) ·
  `4064cf9f`(문구·a11y) · `a44c653b`(회차 API) · `49358698`(SprintLifecycle) ·
  `4961c732`(빼기) · `278ae2e7`(회의록) · `23c04216`(폴링) · `195136dc`(센티널) ·
  `1603ee05`(프로젝트-우선 생성) · `64a75fe8`(축 전환) · `1721b65c`(listRail) ·
  그리고 마감 docs·위생·번들 커밋(아래 verification 뒤)
- working_tree: 마감 커밋 전 — docs·pilot 위생·번들 스탬프가 스테이징 대상으로 남아 있다.
- deployed: **`392575cf`** 가 운영에 나갔다 (2026-09-02 17:23 · `scripts/deploy-upgrade.sh`).
  Stage 0~18 전부 OK · `VERIFY_OK` · `UPGRADE_OK` · 스냅샷
  `/var/backups/clovirassist/20260902-172343`. **스키마 불변** — alembic head 그대로
  `0026_document_categories`(db=code 일치 확인). 스모크(`--cacert` + `--resolve`):
  `/healthz` `{"status":"ok","ticket_source":"native"}` · 새 진입 번들 `index.CoM9K7ST.js` ·
  `WorkBoard.Cv-R-vfi.js` · `Knowledge.Bg4WJvq_.js` · `UserRoutes.C4T30NAw.js`(회의 포함)
  전부 **200**(`ssl_verify_result=0`) · 제품 유닛 6종 + postgresql + nginx 전부 active.
  되돌리려면 `sudo /home/cloviradmin/clovirassist-upgrade/deploy/install.sh rollback --target /var/backups/clovirassist/20260902-172343`
- verification: 각 단계 표적 verify(TARGETED_OK) + 보안·계약 시험은 빨간불→초록 순서
  준수(S2·S3·리셋·rank·이웃 축·pickOpenSprint — 옛 코드 반례 확인). **전량**:
  `static_checks --scope full` **`STATIC_CHECKS_OK`**(`BUNDLE_FRESH_OK` 포함 — 정적
  게이트가 마감 중 실수 하나를 실제로 잡았다: qa-contract-replaced-by 헤더는 매달린
  참조가 아니라 삭제 시험의 후계 선언이었고, 걷었다가 되돌렸다) · vitest 전량 **376
  파일 2,850시험 전부 초록**(exit 1 은 기존 prosemirror/jsdom unhandled 경고, 실패 0) ·
  백엔드 전량 회귀 **security·integration 4청크 전부 초록**, 실패 3은 전부 이번 회차
  밖 소유 — 둘(document_category 감사 라벨 누락 · 낡은 줄 상한 계약)은 그 자리에서
  수리해 재검증 초록(`de7d2803`), 하나(chunked 413 시험의 405)는 세션 시작 커밋에서도
  같은 실패임을 워크트리로 실측하고 **P-71** 로 라우팅했다.
  스키마 변경 0 · 마이그레이션 0 · RBAC 축 재사용(신규 권한 없음).
- capture: 전량 정본은 **`s22-final`** 그대로다(D-306) — 이번 회차는 캡처를 안 옮겼다.
- ui_gate: 변화 없음 — W8·W15 잔여는 P-44 그대로.

## 이번 회차가 **안 고친** 것 — 그리고 그 이유

- **pilot_b7b8 의 B7 구획**: 은퇴한 `/api/sprint` 와 옛 화면 구조를 조준한다 — P-63 과
  같은 성격이라 수용 회차 재작성으로 넘겼다(**P-64**). pilot_b1 의 API 선언 한 줄만 고쳤다.
- **JS no-undef 정적 검사**: 죽은 참조 둘이 배포까지 간 구조적 원인(eslint 부재) — 기존
  위반 정리가 별도 회차 크기라 **P-65** 로.
- **회의 주간 비교(compare=prev)** — **P-66** · **보드 카드·티켓 상세의 빼기** — **P-67** ·
  **AI 초안 폼의 project_id** — **P-68** · **보드 서버 성능 잔여**(26명 규모라 관측 불가) —
  **P-69** · **nginx conf 주석**(배포 diff 회피, 정본 문서는 세움) — **P-70**.

## 🔴 운영이 PostgreSQL 위에서 돈다

`10.100.64.71` 의 `/healthz` 가 `{"status":"ok","ticket_source":"native"}` 로 답한다.
원장은 [`EVIDENCE/S14/`](EVIDENCE/S14/README.md). (수치 표는 직전 판 그대로 — 사용자 26 ·
프로젝트 22 · 티켓 1,145+ · 옛 이름 층 없음.)

## 완료

- **S0~S22** — 기반 · PostgreSQL · Identity/TLS · 설치 자동화 · RBAC · Work · Knowledge ·
  Storage · AI 1·2 · n8n 제거 · Backup/Restore · Migration · Cutover · Functional E2E ·
  Final Audit. 결정 D-187~D-334.
- **화면 고도화 · 대시보드 · 무한 스크롤 · 서버 필터/정렬 · 티켓 만들기 · 신호 축 ·
  3영역 재설계 · 카테고리 · 엑셀** ✅ — D-335~D-406.
- **작업 보드·스프린트 회의·문서 결함 전수 수정 + 429 근본 해소 ✅** — 이번 회차,
  결정 **D-407~D-412**.

## NEXT — 다음 기능 개발은 §7.0 일반 개발 흐름을 탄다

**새 Stage 를 자동으로 만들지 않는다.** 남긴 것은 전부 Backlog 다:

1. **P-44** — 사슬의 서버 칸 982. W8·W15 게이트의 마지막 축.
2. **P-54~P-56 · P-59** — S22 의 시각 축 잔여.
3. **P-61 ~ P-70** — 부서 없음 센티널 · WBS 담당자 열 · pilot 재작성 둘(b11·b7b8) ·
   eslint · 주간 비교 · 빼기 확장 · AI project_id · 서버 성능 · nginx 주석.
4. **P-50 · P-52 · P-35 · P-37** — 플랫폼 축 잔여.

## BLOCKERS

- 없음.
