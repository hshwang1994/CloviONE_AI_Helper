# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-25** (S17)
- phase: **E — UI Renewal 재개.** S17 이 끝났고 다음은 S18~S20
- session: **S17 완료.** 다음은 **S18 — Pilot Archetype 8종(새 IA 기준) (요청 시)**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S17 도 옮기지 않는다.** 이유는 S11~S16 과 같다 — 그 기준을 옮기는 순간 그동안 지운
  시험들이 검사 시야에서 사라진다.
- working_tree: clean
- deployed: **S15~S17 이 운영에 나갔다** (2026-08-25 04:13, `install.sh upgrade --source local`).
  Stage 0~18 전부 OK · `VERIFY_OK` · 스냅샷 `/var/backups/clovirassist/20260825-041314`.
  `/healthz` `{"status":"ok","ticket_source":"native"}` · `/readyz` `{"status":"ready"}` ·
  배포본 번들 지문 `39187bca03b30bc3` 가 빌드한 것과 같다. 스모크 6화면(홈·내 티켓·티켓 상세·
  게시판·문서·채팅방)에서 **콘솔 오류 0 · 페이지 오류 0**. 되돌리려면
  `sudo /opt/clovirassist/deploy/install.sh rollback --target /var/backups/clovirassist/20260825-041314`
- ui_gate: **UI_RENEWAL_COVERAGE_OK (stage=wave, wave=W7, 억제 1건)** — S17 이 UI 축의
  CHECKPOINT 를 W7 로 올렸고 `capture_labels.after` 를 `s17-after` 로 옮겼다. 억제 하나는
  칸반 레인의 균등 격자다(SUP-01, 만료 2026-10-20).
  그쪽 상세는 [`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md)
- 스키마는 **93 표**다. alembic head 는 `0016_document_axis_to_documents` 다. S17 은 스키마를
  안 건드렸다(프런트·QA 하네스·문서만)

## 🔴 운영이 PostgreSQL 위에서 돈다

`10.100.64.71` 의 `/healthz` 가 `{"status":"ok","ticket_source":"native"}` 로 답한다.
데이터는 전부 넘어갔고 서비스는 열려 있다. 원장은 [`EVIDENCE/S14/`](EVIDENCE/S14/README.md).

| | |
|---|---|
| 사용자 · 프로젝트 · 티켓 | 25 · 22 · **1,140**(컷오버 뒤 실사용자가 새로 만든 7건 포함) |
| 프로젝트 코드 | **22 / 22.** S13 에서 확정표에 없어 못 받던 둘도 받았다 |
| 문서 · 판 · 태그 · 문서 첨부 | 110 · 166 · 106(19종) · 54 |
| 티켓 댓글 · 티켓 첨부 | 336(이관 첫 회차가 0건 옮겼던 324건을 재이관이 채웠다) · 236 |
| 옛 이름 층 | **없다** — `tickets.legacy_key` · `ticket_key_aliases` · `project_key_registry` 를 `0012` 가 내렸다 |
| Notion 런타임 | **없다.** 모듈 열다섯을 지웠고, 런타임 SSRF 목록에 `api.notion.com` 이 **없다** |
| SQLite 런타임 | 없다. 옛 파일은 `/var/lib/clovirassist/web.sqlite3` 에 남아 있지만 제품이 못 연다 |

## S17 이 실제로 한 것

이번 회차가 답한 질문은 둘이다 — **클로비가 실제로 보이는가**, 그리고 **값이 없을 때 화면이
그 사실을 말하는가.**

### 1. 🔴 클로비가 작았던 원인은 «작게 줬다» 가 아니라 **«박스를 줬다»** 였다 (D-294)

포즈 PNG 는 전부 1024² 인데 캐릭터가 차지하는 세로 비율이 자산마다 **0.666~0.850** 으로
벌어진다. 그래서 같은 `size={48}` 이 `clovi-avatar` 면 40px 짜리 캐릭터, `clovi-button` 이면
32px 짜리 캐릭터다 — **같은 숫자가 자산마다 다른 크기로 보인다.** 박스를 재는 어떤 검사로도
안 보이는 축이고, 그래서 상단바는 `size={28}` 로 **22px** 짜리 클로비를 그리고 있었다.

이제 호출부는 **자리 이름**만 말한다(`place="topbar"`). 박스는 `보이는 크기 / 여백 비율` 로
파생하므로 자산을 다시 출력하면 박스가 **따라 움직인다**. 상단바의 보이는 캐릭터가
**22px → 34px**(2200 이상에서 40px)이 됐고, 얼굴이 **눈 감은 졸린 포즈에서 웃는 포즈**로
바뀌었다 — 그 자리 주석은 `clovi-idle` 을 "이미 웃는 얼굴"이라고 적어 두었는데 사실이 아니었다.

그 과정에서 **선언만 있고 배선이 없던 것**을 또 하나 찾았다: QA 프로브가 읽는
`data-mascot-context` 를 내보내는 소스가 저장소에 **한 곳도 없었다**(S16 이 `data-col-role`
에서 찾은 것과 같은 형태). 이제 자리마다 선언한다.

### 2. 🔴 그리고 그것을 재던 검사가 틀려 있었다 (D-295)

프로브가 알파 문턱 **8** 에 부유 픽셀 제거 **없이** 재서 `clovi-talking` 의 세로 잉크 비율을
**1.000** 으로 봤다 — 참값은 **0.817** 이다. 저알파 안티에일리어싱 픽셀이 캔버스 가장자리까지
흩어져 있어서다. 그 22%p 만큼 「보이는 크기」가 부풀어 **정말 작은 마스코트가 통과한다.**
PLAN 이 이 실패를 이름으로 예고해 두었는데("부유 픽셀 제거는 필수다") 구현이 안 따랐다 —
통과하지만 잘못된 표본을 재던 검사다.

정의를 한 곳에 잠갔다: `app/static/brand/mascot/mascot-bounds.json`(자산 28개) + 생성기 +
`static_checks.sh` 신선도 검사 + Python 회귀 6건. 브라우저 쪽 구현과 Pillow 쪽 구현이 같은
값을 내는 것도 실측으로 확인했다(`clovi-avatar` 0.83984 vs 0.840). 그 위에서
`mascot_visible_size` 를 **`--fail-on` 으로 승격**해 60페이지 초록을 받았다.

### 3. 값이 없으면 **접는다** (D-296)

점선 상자(`ChartEmpty`)를 폐기했다. 그것은 「없는 데이터를 위한 컨테이너」였고 지시 0-10 이
처음 묻는 질문이 「데이터가 없을 때 Chart/Table/Card 자체가 필요한가」다. 이제 0건이면
차트·표·페이저가 **실제로 언마운트**되고, 로딩 자리는 같은 높이의 **차트 모양** 스켈레톤이
잡는다 — 그래서 「불러오는 중」과 「값이 없다」가 처음으로 다르게 보인다. 예외 하나(서버가
페이지를 자르고 화면이 다시 거르는 목록에서는 페이저만 남는다)까지 렌더 시험 11건이 지킨다.

### 4. 빈 상태 밴드의 **순환**을 정리했다 (D-297)

「빈 공간을 캐릭터로 때우는가」는 컨테이너 높이를 **그림이 아닌 것이 정할 때만** 물을 수 있다.
그림이 그 구획에서 가장 큰 요소이면 컨테이너 높이가 곧 그림 높이라 어떤 비율도 통과할 수
없다 — 내용 크기 컨테이너에서는 하한(96)을 만족하는 순간 비율이 최소 57% 가 되어 **두 조건이
동시에 만족될 수 없다.** 밴드 상수는 안 건드렸고, 어느 자리가 어느 밴드를 주장하는지를
화면이 선언하게 했다.

### 5. 상세 상단 속성이 **위계**를 갖는다 (D-298)

폭은 S16 이 닫았고(D-288) 남은 것은 무게였다 — 티켓 상세의 속성 아홉이 전부 같은 강도로 한
줄이라, 열자마자 봐야 하는 「상태·담당자·마감」과 지원 문의 때나 부르는 「티켓 번호」가
구별되지 않았다(4K 에서 그 줄은 2,880px 다). 이제 화면이 `rank: "primary"` 로 먼저 판단할
값을 선언하면 그것만 위 줄의 속성 묶음이 되고 나머지는 아래 압축 띠로 내려간다. **선언이
없는 호출부의 렌더는 안 바뀐다.**

### 6. 함께 걷어낸 것

죽은 `PageHeader.spot` prop 과 그것을 넘기던 화면 **열일곱**(Q4 이후 아무 일도 안 하는데 읽는
사람은 그 화면에 그림이 있다고 믿는다) · 화면이 라벨을 갈아 끼우던 버튼 로딩 둘(`Button
loading` 으로 통일) · **P-34 의 프런트 시험 셋**(전부 화면이 아니라 시험이 틀렸다) · 담당자
후보가 비었을 때 **없어진 시스템**을 원인으로 대던 안내.

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
- **S6 — Work Domain.** 티켓에 번호가 붙고 그 번호가 영원히 같은 티켓을 가리킨다.
  결정 **D-236~D-243**(그중 Key 정책은 S14 가 대체했다).
- **S7 — Knowledge Domain (+P-14a).** 본문의 정본이 블록이 되고 그 블록에 이름이 붙었다.
  결정 **D-244~D-248**.
- **S8 — File Storage Providers.** 파일이 DB 밖에 살고, 그 자리가 진짜 그 저장소인지 매번 묻는다.
  결정 **D-249~D-253**.
- **S9 — AI Platform 1 (Gateway · Pipeline).** 모델이 계약 뒤로 들어가고 문서가 스스로
  색인된다. 결정 **D-254~D-259**.
- **S10 — AI Platform 2 (Retrieval · Citation · 생성).** 권한이 `LIMIT` 앞에 걸리고
  인용이 문단을 가리킨다. 결정 **D-260~D-264**.
- **S11 — n8n · 외부 Runner 제거.** 옛 AI 경로가 사라지고 채팅이 제품 안에서 답한다.
  결정 **D-265~D-268**, 원장 [`EVIDENCE/S11/`](EVIDENCE/S11/README.md).
- **S12 — Backup / Restore 운영.** 백업이 「되돌리면 앱이 돈다」를 증명한다.
  결정 **D-269~D-273**, 원장 [`EVIDENCE/S12/`](EVIDENCE/S12/README.md).
- **S13 — Migration Tool + Dry Run.** 옛 데이터가 새 스키마로 전부 건너가고 두 번 돌려도 같다.
  결정 **D-274~D-281**, 원장 [`EVIDENCE/S13/`](EVIDENCE/S13/README.md).
- **S14 — Cutover + Legacy 제거.** 위 절. 결정 **D-282~D-284**, 원장
  [`EVIDENCE/S14/`](EVIDENCE/S14/README.md).
- **S15 — Search/Filter 기능 정확성.** 조건이 맞는지를 **두 구현의 대조**로 봤다 — 결함 여섯을
  뿌리에서 고쳤고 전부 오류를 안 내는 종류였다. 결정 **D-285~D-287**.
- **S16 — Table / Grid / Metadata / Alignment + Chart.** 열이 폭 대신 의미를 말한다.
  `numeric_alignment` 8건이 0 이 됐다. 결정 **D-288~D-293**.
- **S17 — Empty / Loading / Error / Feedback + Clovi + Detail Metadata.** 위 절.
  결정 **D-294~D-298**.

## 상태 — 전환 축 다섯

| 축 | 현재 | 소유 Session |
|---|---|---|
| **PostgreSQL** | ✅ **System of Record 다.** 운영이 그 위에서 돈다 | S2 ✅ · S4 ✅ · S9~S14 ✅ |
| **SQLite 제거** | ✅ **끝났다.** Runtime 의존 0 이고 데이터도 전부 넘어갔다 | S13 ✅ · S14 ✅ |
| **Notion Migration** | ✅ 런타임은 끝났다. **화면에는 잔재가 남아 있다**(P-41, S20) | S13 ✅ · S14 ✅ |
| **AI** | ✅ 끝났다 | S9 ✅ · S10 ✅ · S11 ✅ |
| **Backup** | ✅ 끝났다 — 그리고 S14 가 **실 데이터로 다시 증명**했다 | S2 ✅ · S4 ✅ · S8 ✅ · S12 ✅ · S14 ✅ |

**Identity 축도 닫혔다** — 호스트명·TLS(S3) · slug(S4) · 역할·권한(S5), 그리고 마지막 한 건인
세션 쿠키 이름을 S14 가 갈았다(P-33).

**UI 축은 W7 까지 왔다.** 근거와 수치는 [`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이었고 재개는 Phase E(S15~S20)다 (D-207).

## NEXT — 다음 시작점: S18 (요청 시)

**S18 = Pilot Archetype 8종 end-to-end (새 IA 기준).**
사용자 요청 없이 착수하지 않는다. 범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1,
Backlog 는 **P-28**.

S17 이 다음 Session 에게 넘기는 것 다섯:

1. **클로비 크기는 자리 이름으로 말한다.** `frontend/src/ui/Mascot.jsx` 의 `MASCOT_PLACE` 에
   줄 하나를 더하면 박스가 자산 여백에 맞춰 파생한다 — 숫자를 다시 적지 않는다.
2. **빈/로딩/오류 넷이 부품으로 서 있다.** `Skeleton kind="chart"` · `ChartNoData` ·
   `EmptyState layout="page|region|inline"` · `ErrorState`. 화면은 **고르기만** 한다.
3. **상세 속성의 `rank` 배선이 티켓 하나뿐이다.** 문서·게시글·프로젝트 상세는 그 화면들
   회차(S18·S19)가 같은 한 줄로 닫는다.
4. **긴 데이터도 설치처 없이 잰다** — `python -m scripts.ui_qa.local_capture --harness
   hostile_data --modes long --viewports 1920x1080 2560x1440 3072x1728 3840x2160`.
5. **범위 밖으로 넘긴 것 넷**: 시험 강도 선언 미비 15건(**P-38**) · 백엔드 회귀 넷(**P-39**) ·
   화면에 남은 Notion 잔재(**P-41**, S20) · `/dev-report` 의 빈 판(**P-42**, S20).
