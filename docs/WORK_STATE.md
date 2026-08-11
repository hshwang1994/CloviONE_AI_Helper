# WORK STATE — 지금 어디까지 왔는가

> **새 세션·Context 압축·방향 불확실 시 이 문서를 가장 먼저 읽는다.**
> 대화 History는 Source of Truth가 아니다. 이 문서와 아래 5개가 진실이다.
>
> | 문서 | 역할 |
> |---|---|
> | **WORK_STATE.md** (이 문서) | 현재 사이클·위치·완료 범위·다음 작업·Blocker |
> | [WORK_PLAN_INDEX.md](WORK_PLAN_INDEX.md) | MASTER PLAN — 전체 목표·확정 계획·완료 기준 |
> | [BACKLOG.md](BACKLOG.md) | 발견한 모든 문제·개선사항 + 상태 |
> | [QA_COVERAGE.md](QA_COVERAGE.md) | Route×검증축 매트릭스 — 무엇이 아직 검증 안 됐는가 |
> | [DECISIONS.md](DECISIONS.md) | 이후 작업에 영향을 주는 결정과 이유 |
> | [BUILD_LOG.md](BUILD_LOG.md) | HISTORY — 사이클별 누적 이력 |

**마지막 갱신**: 2026-08-10 · **단계**: **MEGA CYCLE I 구현+테스트 완료(기능·데이터·권한
E2E — FN-*/SEC-* quick-fix 스윕), 배포는 Blocker로 대기**. Cycle 4의 소배치 방식을
그만두고(D-53) 제품 영역 단위로 넓게 조사·대량 수정·영역 종료 시 1회 배포로 전환 —
Cycle 4 배치 1~6(UA/CORE/SEC 22건)은 그대로 유지.
**D-54(2026-08-10) — MEGA CYCLE 크기 재조정**: C/D/E/F처럼 같은 Product Area(Design
System)를 여러 개의 작은 MEGA CYCLE로 쪼개고 매번 전체 회귀·배포·Chrome 검증을 반복하는
방식을 그만둔다. 기준은 "몇 건을 처리했나"가 아니라 "하나의 Product Area/Subsystem이
실질적으로 거의 끝났는가"다 — 같은 영역의 후속 작업은 같은 MEGA CYCLE 안에서 계속하고,
구현 중에는 변경 영역과 직접 관련된 focused test만 반복하며, Full backend + Full frontend +
static + build 같은 전체 회귀와 배포·Chrome E2E는 그 Product Area가 배포 가능한 큰 단위로
충분히 완성됐을 때 한 번 수행한다. 건수(20/50/100+)를 인위적으로 제한하지 않는다.
Critical/Security/RBAC/DataLoss/Migration/Concurrency 또는 즉시 실환경 확인이 필요한
고위험 변경은 예외(그 자리에서 바로 검증). **MEGA CYCLE G가 이 새 기준으로 진행한 첫
사이클**이다 — Admin IA(관리자 정보 구조) 하나를 20개 넘는 관련 변경으로 묶어 한 번에
조사·구현·(거의) 한 번의 전체 회귀·한 번의 배포로 마쳤다. **MEGA CYCLE A**(AI Assistant,
RN-01~14 + Critical AI-30)·**MEGA CYCLE B**(제품 전역 실패 처리, Critical `FAIL-01` +
FAIL-02/03 + FN-51)·**MEGA CYCLE C**(Design System, DS-01~32 전수 재검증)·
**MEGA CYCLE D**(로그인 화면 정적 토큰 사본 핵심 색 부분 동기화)·**MEGA CYCLE E**
(Design System 후속 배치, DS-07/21/22 구현)·**MEGA CYCLE F**(Design System 후속 배치 2,
DS-14/15/20 구현 + DS-33)·**MEGA CYCLE G**(Admin IA 전체 스윕, IA-01/02·FN-13·RG-11)
까지 전부 구현·테스트·배포까지 완료 — BACKLOG의 Critical 0건. 상세는 각 §MEGA CYCLE
섹션. MEGA CYCLE A
검증 중 **배포와 무관한 실서버 인프라 문제 1건 발견**: `n8n` 계정 Claude CLI 미인증
(`OPS-06`) — **2026-08-10 사용자 재로그인으로 해결, 실호출로 확인 완료**(러너와 동일 조건에서
`result:"PROBE_OK"` + 실제 토큰 소모). 같은 날 `OPS-01`(업로드 소유권)도 **이미 복구돼 있음을
재확인**(BACKLOG 표가 낡았던 것). **둘 다 앱 층 E2E 만 미검증** — 웹에서 첨부 1건 · AI 도우미
자유 질문 1건이 남아 있다. 진행률 실측치는
[docs/PROGRESS_STATUS.md](PROGRESS_STATUS.md) 참고 · **브랜치**: `ui/mui-migration`

**BACKLOG ID 정합성 수정(2026-08-10, MEGA CYCLE G→H 사이 정리, D-55)**: `AI-*` 15건이 세
조사 라운드에서 번호가 중복돼 있어 한 차례 재번호했는데, 1차 시도가 "AI-30"(Critical
CREATE 하이재킹, 이 문서 §MEGA CYCLE A가 이미 그렇게 인용) · "AI-31"(의도분류 오탐) ·
"AI-37"(탈출어 안내 없음) 3건을 **엉뚱한 쪽으로 옮기는 실수**를 했다가, 이 문서·
`DECISIONS.md`의 기존 인용과 교차검증해 되돌렸다. 지금은 `AI-30`·`AI-31`·`AI-37`이
원래 의미(위 §MEGA CYCLE A가 인용하는 그 finding들)를 다시 갖고, 밀려난 3건(구 중복
AI-30 Med screen_context·구 중복 AI-31 dead code·구 중복 AI-37 내보내기 없음)은
`AI-66`~`AI-68`로 이동했다. 코드 재확인 결과 `AI-30`(Critical)·`AI-66`(Med)**둘 다
MEGA CYCLE A에서 이미 고쳐져 있었다** — BACKLOG.md 상태 칸이 "발견"으로 방치돼 있던
것도 이번에 구현완료/부분구현으로 갱신했다. 상세 경위는 `DECISIONS.md` D-55.

**자율 Runner 가동 중(2026-08-11, D-57)**: 이 세션(대화창)이 닫혀도 프로젝트가 안 끝났으면
Windows 작업 스케줄러가 3시간마다 이 저장소에서 새 Claude Code 프로세스(`-p`, 비대화형)를
띄워 이어서 작업한다 — `scripts/runner/README.md` 참고. 그러니 **다음에 이 문서를 읽는
세션(사람이든 Runner든)은 커밋 로그에 이 창이 안 만든 새 커밋이 있을 수 있다는 것을
정상으로 받아들여라** — 저자가 다르다고 되돌리지 말고, 그 커밋들이 남긴 이 문서의 최신
갱신을 그대로 이어받는다. 상태는 `var\runner\runner.log`·`var\runner\state.json`(git
비추적)로 확인 가능. 배포 자격증명 경계(위 §D-54 배너)는 Runner의 매 실행 프롬프트에도
동일하게 박혀 있다 — Runner도 이 경계를 스스로 어기지 않는다.

---

## 🟣 MEGA CYCLE I — 기능·데이터·권한 E2E, FN-*/SEC-* quick-fix 스윕 (구현+테스트 완료, 배포 대기) (2026-08-10)

MEGA CYCLE H 종료 직후 착수. Master Plan 축 4("기능·데이터·권한 E2E", `FN-*`/`SEC-*`) —
Design System(1)·AI 도우미(2)·관리자 IA(3)가 MEGA CYCLE A/C/D/E/F/G/H로 상당 부분
커버된 뒤 순서상 다음 축. Cycle 4는 D-53 전환 전 소배치 22건(UA/CORE/SEC)만 됐고
`FN-*`/`SEC-*`는 손 안 댄 채였다.

**조사(넓게, 배경 에이전트)**: FN-*(24건)·SEC-*(11건) 전부 훑어 (a) 이미 고쳐졌는데
상태만 낡은 것, (b) quick·안전한 수정, (c) 깊은 재설계 필요로 분류. 코드 재확인으로
`SEC-31`이 `SEC-30`과 같은 커밋에서 이미 고쳐졌음을 확인(상태만 방치).

**구현(7건)**:
- **SEC-31**: 상태만 "발견"→"구현완료"로 동기화(코드는 이미 고쳐져 있었다).
- **SEC-12/SEC-13**(우선순위 — 실제 데이터 유출 위험): 홈 "최근 문서"·"최근 글" 위젯이
  각각 부서 범위(`doc_in_scope`)·조직 게이트(`org_id`)를 안 지났다 — 다른 부서/조직
  문서·게시글이 전 직원 홈 화면에 그대로 떴다. 위젯에 `viewer`/`org_id` 배선, `two_orgs`/
  두 부서 세계로 실제 유출을 재현·확인. 문서 위젯은 SQL LIMIT 뒤에 부서 필터가 걸리는
  구조라 넉넉히 더 가져와 거른 뒤 자르는 방식(과다조회 비용은 "최근 5건" 규모라 작음).
- **FN-02**: `config/allowed-services.json`에 `api.anthropic.com:443` 추가 —
  `llm_backend=api`가 SSRF allowlist에 막혀 영구 실패하던 것을 고침.
- **SEC-02**: `GET /api/admin/jobs/stats`에 `apply_scope`(형제 목록·상세와 같은 함수) 배선 —
  부서 admin이 전역 큐 깊이를 보던 것을 막음.
- **SEC-03**: `GET /api/admin/impersonation/state`가 매 폴링마다 DB에 쓰던 것(`read_count`,
  CSRF 무방비 — GET은 `require_csrf`가 통과시킨다)을 최초 1회만 쓰도록 고쳐 진짜 멱등하게.
- **FN-07**: 문서 "재시도" 버튼이 전용 `/{id}/retry`(round30이 이미 만들어 둔 idempotency
  안전 경로) 대신 옛 생성 폼 재오픈(`/generate`)을 계속 부르던 것을 jobs·schedule-runs와
  같은 confirm+path 패턴으로 교체.
- **FN-04**(백엔드 전체 회귀 뒤 이어서 추가): 프로젝트 상세 화면에 "보관" 버튼 신설
  (`useArchiveProject`) — `DELETE /api/projects/{id}`는 처음부터 있었는데 부르는 UI가
  없었다. 되돌리는 API가 없어 이미 보관된 프로젝트엔 버튼을 다시 안 그린다. 프런트 전용
  변경이라 프런트 vitest만 재실행(D-54 — frontend-only 변경에 backend suite 반복 안 함).
- **FN-01**(이어서 추가, "기존 백엔드에 UI만 없음" 부류 첫 착수): 새 화면
  `MailStatus.jsx` + `/mail` 라우트 신설("시스템 인프라" 그룹) — `GET /api/admin/
  mail/status`·`POST /test`는 처음부터 완성돼 있었고, **실서버에서 SMTP 미설정으로
  비밀번호 재설정 메일이 조용히 안 가는 것까지 이미 확인된 상태**였는데 그걸 보여줄
  화면이 없었다. 진단 문제 목록·서버 설정 요약·발송 현황·최근 실패 표·시험 발송 버튼.
  프런트 전용 변경.

**계속(2026-08-11) — "기존 백엔드에 UI만 없음" 부류 마저 처리**: 사용자의 "WHOLE PRODUCT
AUTONOMOUS COMPLETION LOOP" 지시에 따라 Product Area/Cycle을 작업 중단 단위로 쓰지 않고
바로 이어서 위 보류 목록 중 FN-03/05/06/09/11/14, SEC-04/05를 마저 처리했다(FN-41/42/12는
여전히 재설계가 필요해 보류 유지, SEC-10은 실 데이터 콘텐츠 문제라 코드 수정 대상이 아님,
SEC-11은 로컬 디스크 정리라 샌드박스 승인 정책상 보류).

**조사에서 재확인된 사실**: 넓게 조사한 8건 중 실제로는 5건이 서술 그대로였고, 3건은
전제가 낡았거나 절반만 사실이었다(FN-05는 행별 사용량이 이미 있었고 org 전체 합계만
없었음, FN-06은 스냅샷 테이블이 "영원히 빈 테이블"이 아니라 시간당 워커가 이미 채우고
있었음, FN-09는 5종 중 4종이 이미 구현·테스트돼 있었고 수동 백업 실패 1종만 진짜 공백)
— 이 세션에서 반복 확인된 패턴(오래된 감사 결과를 검증 없이 실행하면 안 된다)이 여기서도
그대로 나왔다.

**구현(8건)**:
- **FN-03**(고아 엔드포인트 3종): 팀 티켓 동기화 배너(`can_sync` 필드 1줄 + `TicketSyncBanner`),
  통합 검색 재색인 버튼(operator+ 게이트), 알림 삭제 액션(소유권 기반, role 게이트 없음).
- **FN-05**: AI 쿼터 화면에 조직 전체 오늘/이번 달 합계 요약 카드 추가(기존 `summary` 패턴
  재사용) — 행별 "현재 사용"과는 다른 숫자임을 help 문구에 명시.
- **FN-06**: 프로젝트 상세에 진행률/Health "다시 계산" 버튼 2개 + Health 주간 추세 목록
  (프런트 전용, 백엔드는 이미 정확했음).
- **FN-09**: 수동 백업 실패 알림(`announce_backup_failure` 공개화 + `title` 매개변수화,
  `create_backup` 라우터에서 실패 시 호출).
- **FN-11**(보안 관련, revert-to-verify): `approval_view`에 `can_decide`(role 또는 활성
  위임) 신설, 프런트 승인/거절 액션의 static `roles:` 게이트를 `r.can_decide`로 교체.
- **FN-14**: 트래시 목록 응답에 `notion_page_id` 추가, 복원/영구삭제가 문서 상세 캐시
  (`["team-doc", id]`)까지 무효화 — 부수적으로 단일 영구삭제의 누락된 무효화도 맞춤.
- **SEC-04**: 코드/문서화만(역할 변경 없음) — `notion_mapping/router.py::sync_all` 독스트링 +
  `authz.py` 주석 + `DECISIONS.md` D-56.
- **SEC-05**(4개 하위 항목 중 3개 실재, revert-to-verify): 세션 만료 필터 4곳 추가, 아바타
  서빙에 `active` 검사 추가, 위임 취소 시 "종료" 열이 `revoked_at`을 보여주게 수정.
  4번째(allowlist 캐시)는 전제 오류로 판명(이미 mtime+size 기반 재확인, CORE-06).

**신규 인프라(D-57)**: 이 대화창이 닫혀도 이어지도록 로컬 Windows 작업 스케줄러 기반 자율
Runner를 구성·가동(`scripts/runner/`). 클라우드 스케줄(`/schedule`)은 이 저장소·사내
배포서버(`10.100.64.71`) 둘 다에 접근할 수 없어(격리 샌드박스 + GitHub `origin`이 이력이
스크러빙된 별개 사본이라 push 자체가 위험) 후보에서 제외했다 — 상세 판단은 D-57.

**검증**: 신규/확장 테스트 다수(백엔드 통합·보안, 프런트 vitest) — FN-11·SEC-05(세션 만료)는
revert-to-verify로 실제 회귀를 재현·확인. 전체 회귀 2회(첫 회차에서 FN-03의 `can_sync`가
golden 계약 테스트 2개를 깨는 것을 잡아 `UPDATE_GOLDEN=1`로 재생성, 2회차는 green) —
백엔드 2670건·프런트 207파일/1365건 green, `STATIC_CHECKS_OK`. 커밋 `ef1de39`.

**실환경검증 — 로컬 개발 서버 기준(배포 Blocker와 무관하게 가능한 범위)**: 배포된 실서버가
막혀 있어, 로컬 dev DB(`var/web.sqlite3`)에 uvicorn을 직접 띄우고 새 system_admin 계정을
만들어 Chrome으로 직접 열어 확인했다(계정 생성은 CLI `--password-stdin`, 비밀번호는
명령행에 남기지 않음 — 확인 뒤 서버는 종료). **직접 확인함(✅)**: FN-05 — AI 사용 상한
화면에 새 요약 카드 2개("오늘/이번 달 전체 AI 호출")가 실제 데이터(0/200, 0/20)와 함께
올바르게 렌더링. FN-03b — 통합 검색에 "지금 재색인" 버튼이 뜨고 클릭하면 확인 대화상자가
정확한 문구로 뜸(실제 재색인은 안 눌러 데이터에 손 안 댐). 방문한 모든 화면(대시보드,
승인, AI 상한, 검색, 알림, 휴지통, 프로젝트, 승인 위임, 백업)에서 **콘솔 오류 0건**.
**직접 확인 못 함(❌, 이유와 함께)**: FN-03a(팀 티켓 배너)·FN-03c(알림 삭제)·FN-14(휴지통
복원/삭제)·FN-06(프로젝트 다시 계산)·FN-09(백업 실패 알림)·SEC-05(거둔 위임의 종료일)는
이 로컬 dev DB에 해당 데이터(Notion 연결, 알림, 휴지통 항목, 프로젝트, 실패한 백업,
거둔 위임)가 없어 화면에서 직접 못 눌러봤다 — 전부 자동 테스트(일부는 revert-to-verify)로만
검증됨, 정직하게 그렇게 남긴다.

**배포 — Blocker(외부, 유지)**: 위 §D-54 이후 배너에 기록된 대로, 사용자가 채팅에 평문
SSH/sudo 비밀번호를 제공하며 비대화형 자동 배포를 지시했으나 CLAUDE.md §2 불변규칙 #4
위반이라 거부 — 그 비밀번호는 회전 필요. 이 지시는 이번 "WHOLE PRODUCT" 지시에서도 다시
나왔고, 다시 같은 이유로 거부했다. 실서버 배포·Chrome E2E는 스코프 사용자의 다음 조치
(NOPASSWD sudoers 구성 또는 직접 배포) 대기 중이다. 이 사이 다른 독립 작업은 계속한다 —
이제는 D-57의 자율 Runner도 이 원칙을 그대로 이어받아 매 실행마다 같은 경계를 지킨다.

**다음 작업 후보(2026-08-11 체크포인트에서 남김)**: FN-41/42/12는 여전히 재설계 필요로
보류. 다음으로 착수할 만한 후보 둘을 조사했다:
- **QA_COVERAGE.md 체계적 감사** — 배포된 실서버가 아니어도 **로컬 개발 서버(uvicorn +
  프런트 dev server)로 Function/API/Data/Console-Network/RBAC/Responsive/Theme 축을
  상당 부분 검증할 수 있다**(실서버 전용인 것은 배포 확인 자체뿐) — 배포 Blocker와
  무관하게 바로 착수 가능. 73개 route × 7축 매트릭스 중 대부분이 MEGA CYCLE A 이후
  갱신 안 됨.
- **IA-04(사용자 콘솔 vs 관리자 콘솔 UX 통합)** — 이번 체크포인트에서 규모를 다시
  확인했다: 관리자 화면 약 30개는 `DataScreen.jsx`(768줄) 한 벌의 선언적 registry로
  돈다. 사용자 콘솔은 전부 수제 구현이고 규모가 크다 — `MyTickets.jsx` 1030줄,
  `Users.jsx` 951줄, `BoardPost.jsx` 583줄, `TeamDocs.jsx` 582줄, `Board.jsx` 564줄,
  `ChatPane.jsx` 546줄, `Sprint.jsx` 501줄, `Offboarding.jsx` 512줄. 각 화면이 리치텍스트
  본문 편집·일괄 선택·실시간 채팅·드래그 등 서로 다른 고유 UX를 갖고 있어, 어느 화면이
  범용 registry 패턴으로 옮길 수 있고 어느 화면이 구조적으로 못 옮기는지는 화면별로
  실제 코드를 읽어야 판단할 수 있다 — **이번엔 그 판단까지 하지 않았다**(섣부른 분류가
  틀리면 "일부만 옮기는 반쪽짜리 시도"로 이어져 CLAUDE.md의 "No half-finished
  implementations"를 어기게 된다). 다음 착수 시 **화면별 조사 → 가장 안전한 파일럿 1개
  선정 → 그 화면 하나를 처음부터 끝까지 완전히 마친 뒤에만 다음 화면** 순서를 지킨다.

둘 다 배포 Blocker와 무관하게 바로 진행 가능하다 — 다음 세션(사람이든 D-57 자율 Runner든)은
이 중 하나를 골라 조사부터 시작한다.

**계속(2026-08-11, 연속 실행) — RG-01·VIS-72 구현완료**: 사용자의 "CONTINUOUS RUNNER
CORRECTION" 지시(작업 조각→종료→idle-tick 예약 패턴 금지, 다음 작업이 있으면 곧바로
이어간다)에 따라 조사만 끝나 있던 RG-01을 마저 구현하고 VIS-72(이미 구현·테스트됐지만
미커밋 상태였던 것)를 함께 커밋했다.
- **RG-01**: `DataScreen.jsx`의 `runAction`이 `method==="GET"`이면 `{method}`만 보내고
  아니면 `{method, body}`를 보내도록 분기 — `runHeaderAction`/`SubListDrawer.act`가
  이미 쓰던 패턴과 통일했다. `actions.js`의 "비교"(subList 하위 행 액션)는 애초에
  `SubListDrawer.act`의 올바른 GET 분기를 타고 있어 영향 없음을 확인. revert-to-verify:
  `admin-uiux.test.jsx`에 신규 회귀 시험 1건 추가, 수정을 stash하면 타임아웃으로 실패,
  복원하면 통과 확인.
- **VIS-72**: `navConfig.js`의 `USER_SEG_PATHS`에 `/search` 추가(`ROUTE_OWNER`와의
  모순 해소, `/projects`와 같은 결함 부류). revert-to-verify: 신규 시험 파일
  `user-segment-routes.test.js` 4건, stash 시 2건 실패 확인.
- **검증**: 프런트 전체 회귀(208파일/1370건) green, `bash scripts/static_checks.sh` →
  `STATIC_CHECKS_OK`(번들 재빌드 포함).

**VIS-88·VIS-89 구현완료 — 저수준 `Modal` 미저장 보호 전파**: 19개 `Modal` 호출부를 전부
코드로 재확인해(원 목록을 그대로 믿지 않고) 실제로 잃을 입력이 있는 곳만 골라 고쳤다.
- **고친 7곳**(+ dirty 판정 방식): `MyTickets`(티켓 편집 — `buildChanges()`의 diff를
  그대로 재사용) · `TeamDocs`(새 문서 — `EMPTY_DOC`과 JSON 비교) · `Board`(글쓰기/수정 —
  열 때의 값 스냅샷) · `ChatRooms`(그룹 방 만들기만 — 1:1 시작은 즉시 실행이라 제외) ·
  `UsersBulk`(CSV 가져오기 — 이미 반영됐으면 dirty 아님) · `SavedViews`(뷰 저장) ·
  덤으로 `ChatRoomMembers`(채팅방 관리 — 원 목록엔 없었지만 방 이름 수정/초대 선택이
  같은 결함 부류). 화면마다 두 경로를 다 막았다 — `Modal`의 `dirty` prop(Esc·바깥클릭·X)
  + footer의 '취소/닫기' 버튼용 별도 `requestClose`(Games.jsx가 이미 겪은 "footer 버튼은
  Modal.onClose를 직접 불러 dirty 가드를 우회한다" 문제와 동일 패턴).
- **재확인 결과 제외한 곳**(원 목록의 착오 포함): `SchedulerCalendar`(원 목록에 있었지만
  재확인하니 읽기 전용 실행 상세 + 즉시 실행 버튼뿐, 잃을 입력 없음) · `DataScreen`/
  `SubListDrawer`의 상세·안내 모달 · `Offboarding`/`Users`/`SettingVersions` 상세 ·
  `Tour` · `ChatRooms`의 1:1 시작. `SettingEditor`는 이미 자기 `requestClose`가
  `Modal.onClose` 자체를 감싸는 FormModal과 같은 패턴이라 원래부터 보호돼 있었다.
- **미적용으로 남긴 것**: BACKLOG의 "고칠 방향"(opt-in→opt-out 전환 또는 정적 검사)은
  손대지 않았다 — 지금 남은 호출부는 실제로 dirty=false가 맞아 당장 위험하지 않지만,
  다음에 폼이 있는 새 `Modal` 호출부가 추가되면 같은 결함이 재발할 수 있다(후속 과제).
- **검증**: 신규 시험 `modal-dirty-guard-vis88.test.jsx`(9건). revert-to-verify: 7개
  화면 소스를 stash하면 7건 실패(나머지 2건은 "안 바꿨으면 그냥 닫힘" 케이스라 원래도
  통과), 복원 후 재확인. `DocCreateModal`/`GroupModal`/`ImportModal`은 이 시험을 위해
  `export` 추가(동작 변화 없음, `TicketEditModal`/`PostFormModal`/`ManageRoomModal`은
  이미 export돼 있던 것과 통일). 프런트 전체 회귀는 커밋 직전 재확인.

다음 후보를 다시 코드로 재확인했다(포크 조사): **VIS-104는 2026-08-08에 이미 철회됐고**
(실측으로 반증, 「클로비 가림」계열 7건 철회 참고), **VIS-74는 이미 구현완료**(하네스가
1200×900을 기본 뷰포트 목록에 넣고 임의 WxH를 받게 고쳐졌다, 과거형 서술) — 둘 다 남은
작업이 아니다. **VIS-32**는 앱 코드가 아니라 QA 하네스 스크립트 결함(QA 계정이 투어
완료 API를 한 번도 안 불러 온보딩 모달이 항상 홈을 가림)이라 이 코드베이스의 수정
대상이 아니다(범위 밖).

**VIS-73·RESP-01·RESP-02·HOST-01·HOST-02 구현완료 — `DataTable` 열 폭 붕괴/폭주, 한 곳에서
같이 해소**: 다섯 BACKLOG ID가 전부 같은 근본원인(`kit.jsx`의 `DataTable`이 열 폭을 순수하게
내용에서만 파생했다)을 가리켰고, `HOST-02`가 이미 "고칠 것은 화면 28개가 아니라 `DataTable`
한 곳"이라고 정확히 지목해 뒀다. `RESP` 정밀화 절이 이미 "카드 브레이크포인트를 올리는 것은
답이 아니다"(4열 표와 9열 표가 같은 상수를 쓸 수 없다, RESP-02)라고 결론 내려 둔 것도 재확인 —
그래서 브레이크포인트가 아니라 열 폭 계산 자체를 고쳤다.
- **고친 것**(`ui/kit.jsx`의 `DataTable`): ① 머리글 셀에 본문 셀과 같은 `DEFAULT_COL_MIN_WIDTH`
  (4.5rem) 바닥값 추가 — DS-06이 본문에만 이 바닥값을 줬고 머리글엔 없던 비대칭이 폭 900~1366px
  구간에서 열 많은 표(`/users` 9열)가 무너지는 실제 경로였다. ② `render` 없는 순수 텍스트 열은
  기본이 말줄임(`whiteSpace:nowrap`+`textOverflow:ellipsis`+`title`로 전체 값 유지) — 값이 길면
  셀이 2,353px로 벌어지는 것(HOST-01)과 열이 많으면 '한 글자' 폭까지 짜부라지는 것(VIS-73) **둘
  다** `overflowWrap:anywhere`가 원인이었다. `render`가 있는 열(배지·버튼 등 이미 자기 폭을
  관리)은 그대로 둬 회귀 위험을 좁혔다 — 나머지 22개 `nowrap:true` 열도 전부 `render`를 같이
  쓰고 있어 영향 없음을 확인.
- **미적용으로 남긴 것**: `DataTable`이 자기 실제 폭을 재서 카드 레이아웃으로 자동 전환하는
  ResizeObserver 기반 설계(RESP-02가 이상적으로 제안한 방향)는 이번 범위 밖 — 지금은 열 폭을
  고정 바닥값+말줄임으로 방어하는 더 단순한 수정만 했다. 실제 QA 하네스(Playwright, 1199/1201px
  vertical_text_collapse)로 재실측하지 못했다 — 로컬 jsdom 단위 시험(스타일 속성 존재 확인)까지만
  검증했고, **실브라우저 레이아웃 재현은 못 함**(정직하게 남긴다, 다음에 하네스를 돌릴 기회에
  재확인 필요).
- **검증**: `kit.test.jsx`에 신규 시험 4건(말줄임 기본값·render 예외·빈값 title 생략·머리글
  바닥폭), revert-to-verify(되돌리면 2건 실패 확인 후 복원). 프런트 전체 회귀는 커밋 직전 재확인.

**VIS-81 재조사 — 전제 절반 오류, RG-02가 진짜 결함이었다**: VIS-81을 구현하려고 코드를
직접 열어 보니 인용된 근거(`RG-02`)가 **다른 유형(`document`) 얘기**였다. `계정 잠금`(`user`
유형) 예시는 `app/notifications/destinations.py`가 **의도적으로** `related_route`를 안
주는 경우다(그 화면들은 전부 목록 화면이라 id 자리가 없다고 docstring에 명시) — `Users.jsx`가
목록으로 여는 건 지금 설계상 맞는 동작이다. 오래된 backlog 서술을 검증 없이 실행하지 않는다는
이 세션의 반복된 원칙이 여기서도 그대로 확인됐다. `docs/BACKLOG.md`의 VIS-81 행을 정정했다 —
`Users.jsx` 단건 딥링크 신설은 범위 밖 별도 기능 판단으로 보류.

**RG-02 구현완료 — 진짜 결함(팀 문서 댓글 알림 404)**: `registry/notifications.js`의 "관련
항목 보기"/"관련 목록 열기"가 서버의 `related_route`(app/notifications/destinations.py)를
버리고 로컬 표(`shared.js`의 `OBJ_ROUTE`/`OBJ_ID_PARAM`)로만 목적지를 다시 계산해, 팀 문서
댓글이 관리 콘솔 "문서 생성" 화면으로 잘못 가 404였다. `NotificationBell.jsx`(팝오버)는 이미
서버 값을 최우선으로 쓰고 있었다 — `/notifications` 전체 목록 화면만 그 패턴을 안 따랐다.
- **고친 것**: 두 액션 모두 `serverHref(r)`(내부 상대 경로만 허용, `NotificationBell.jsx`의
  `serverRoute()`와 같은 검증)를 로컬 표보다 먼저 본다. 서버가 계산해 준 대상(document/
  ticket/board_post/chat_room/chat_mention)은 전부 사용자 콘솔 화면이라 정적 `roles:
  ADMIN_VIEW_ROLES` 게이트를 없애고 `when()` 안으로 옮겼다 — 안 그러면 일반 사용자가 **자기**
  티켓·채팅 알림도 못 눌렀다(그 정적 게이트는 원래 로컬 표의 관리자 전용 대상만 가리려던
  것인데, 서버 대상까지 함께 가려지고 있었다). 로컬 표 폴백(승인·작업 큐 등)은 그대로.
- **검증**: `notification-server-route.test.jsx` 6건(문서 댓글 정상 경로·일반 사용자 접근·
  로컬 폴백 유지·역할 게이트 유지·프로토콜 상대 URL 거부·두 액션 상호 배타), revert-to-verify
  (되돌리면 3건 실패 확인 후 복원). 프런트 전체 회귀는 커밋 직전 재확인.

다음은 VIS-90(빈 상태 품질 불균일, D-22가 이미 `/my-tickets`를 정답 패턴으로 지목함)으로
이어간다 — 자기완결적이고 적용할 패턴이 이미 정해져 있다. 그 다음은 VIS-107R/108R/109R
(장애 카운터에 시간창이 없고 재시도/알림 워크플로 자체가 없음) 순으로 계속한다. 사용자 확인
대기 없이 진행한다.

**VIS-90 구현완료 — 재확인 결과 `/my-tickets`의 4단계 패턴은 이 상황에 안 맞았다**: 코드를
직접 열어 보니 `/my-tickets`의 "삽화+2단계+기대 결과"는 **Notion 연동 미설정 같은 온보딩
차단 상태**용이고, `/chat`의 마스코트+제안 칩은 **AI 프롬프트 제안**이라 사람 간 대화에는
안 맞는다 — 그대로 옮기면 어울리지 않는 이식이 된다. 대신 `/games`급("아이콘+제목+안내")
패턴을 적용했다: `EmptyState`에 `icon="💬"`만 추가(문구는 그대로 — `gameroom-smoke.test.jsx`가
이미 고정하고 있어 안 건드림). 조사 중 **같은 빈 상태가 `game-room/ChatPanel.jsx`(게임방
사이드 채팅)에도 복제돼 있는 것을 발견**해 함께 맞췄다 — 안 그러면 두 채팅이 다른 기능처럼
보인다. `VIS-91`(450px 빈 공간 뒤에 붙는 위치 문제, `flex-end` 레이아웃)은 범위 밖으로
남긴다 — 실제 대화가 있을 때의 스크롤-바닥-고정 동작과 얽혀 있어 별도 판단이 필요하다.
`chatpane.test.jsx` 신규 시험 1건, revert-to-verify(되돌리면 실패 확인 후 복원). 프런트
전체 회귀는 커밋 직전 재확인.

**VIS-107R 구현완료 — 미해결 실패 카운터에 시간축 추가**: `build_dashboard`가
`failed_open_oldest_at`(가장 오래된 미해결 실패의 생성 시각, 없으면 `null`)을 새로
내려준다. `Dashboard.jsx`의 경보 타일·KPI 타일·현재 큐 상태 StatCard 3곳 전부
`failedOpenAgeLabel()`(`opsHelpers.js`, 하루 미만은 "오늘")로 나이를 덧붙인다. 백엔드
`test_dashboard_failed_open_age.py` 3건 + 프런트 `dashboard-helpers.test.js` 2건,
둘 다 revert-to-verify.

**VIS-108R — 이번 배치에서 범위 밖으로 남김**: 알림 발송(스케줄러+새 알림 유형)·일괄
재시도 액션·"이미 해결된 원인" 표시까지 묶인 별도 기능 추가라 VIS-107R(순수 표시 개선)과
규모가 다르다. 서두르면 half-finished 알림 워크플로가 남는다 — CLAUDE.md의 "No
half-finished implementations" 원칙에 따라 다음 사이클에서 전용 판단으로 다룬다.

**VIS-109R 구현완료(확인됨 — 실제로 이 버그가 있었다) — 배포 재기동 순서 뒤집음**:
`install-clovirone-web-assistant.sh:369-377`을 직접 읽으니 "잡을 넣는 코드가 먼저
올라가고 처리하는 워커가 나중에 올라가면 영구 실패한다"는 VIS-109R의 가설이 정확히
사실이었다 — nginx reload 직후 web을 먼저 재시작+최대 30초 health-gate 대기, 그 뒤에야
worker 재시작. 그 구간엔 새 web이 이미 트래픽을 받는데 옛 worker가 아직 큐를 돌고 있어,
그 사이 들어온 새 job_type의 잡이 영구 실패했다 — `VIS-107R`/`VIS-108R`이 실측한 "3주
방치된 미해결 실패 4건"과 지문이 같다. 순서를 뒤집었다(worker 먼저 재시작+active 확인 →
web 재시작+healthz 게이트). `upgrade-clovirone-web-assistant.sh`·`update-from-git.sh`
둘 다 이 installer를 그대로 호출해 한 곳만 고치면 두 배포 경로 다 고쳐진다. 상세 경위는
`docs/DECISIONS.md` D-58. **직접 확인 못 함(❌)**: systemd·root·실서버가 있어야 실행되는
스크립트라 `bash -n`(문법 검사)까지만 했다 — 다음 배포 때 로그 마지막 줄이 `"worker
active; web healthz OK"`로 바뀌었는지 사용자가 확인할 수 있다.

다음은 VIS-108R을 미룬 자리를 채울 다른 후보를 다시 코드로 재확인해 고른다 — 사용자 확인
대기 없이 진행한다.

**VIS-159 기록만(구현 안 함)**: 채팅 링크 다듬기(`trimUrlTail`, `chat-text.js`)가 자기
주석의 예시("...(https://a.b/c)에서")를 실제로는 못 고친다 — node로 직접 돌려 확인함. 닫는
괄호 뒤에 공백 없이 조사가 바로 붙으면 마지막 글자가 문장부호/닫는 괄호가 아니라 다듬기
반복문이 첫 바퀴에 멈춘다. 팀 채팅·AI 채팅 둘 다 같은 함수를 써서 같은 결함을 물려받는다.
**안 고친 이유**: 이 앱은 임의 외부 URL도 링크화하고 실제 Notion URL은 한글 슬러그를 그대로
담을 수 있어("URL에서 한글 배제" 같은 손쉬운 수정은 정상 슬러그까지 자를 위험) 전용 경계
판정 로직 설계가 필요한 별도 작업이다 — 서두르면 반쪽짜리 정규식이 남는다. `docs/BACKLOG.md`
VIS-159에 재현 방법과 함께 기록.

**APPR-01 구현완료 — 승인/스케줄/작업 큐/러너 알림 딥링크 넷 다 같은 결함**: `RG-02`(팀
문서 댓글)를 고칠 때 발견한 것과 정확히 같은 부류의 결함이 조사 중 4건 더 발견됐다. 각
화면(`/approvals`·`/schedules`·`/jobs`·`/runners`)은 전부 이미 `onQuery`로 `?id=`(작업
큐만 `?job_id=`) 딥링크를 지원하고, 백엔드도 이미 `related=("approval"/"schedule"/"job"/
"runner", id)`로 그 id를 알림에 싣고 있는데, `app/notifications/destinations.py`의
`RELATED_DESTINATIONS`표에만 네 유형이 전부 빠져 있어 `related_route`가 항상 `null`이었다
— 이 표를 처음 만들 때 "그 화면들은 목록 화면이라 id 자리가 없다"고 적어 둔 전제가 각
화면이 onQuery를 갖추면서 낡아 있었다. 프런트 로컬 표(`NotificationBell.jsx` 자체
`OBJ_ROUTE`/`OBJ_ID_PARAM`, `registry/shared.js`)엔 이미 네 유형이 다 있어 어느 정도
폴백으로 동작했겠지만, 서버 표가 `null`을 주는 것 자체가 이 모듈의 "서버가 단일 출처"
설계 원칙(모듈 자체 docstring)을 어기는 상태였다. 네 줄 추가 + docstring 갱신(스케줄
실행 이력의 `schedule_run`과 `user`는 여전히 대상 화면에 id 딥링크가 없어 제외).
`tests/unit/test_notification_destinations.py` 38건(순수 함수 단위 시험, DB 불필요),
revert-to-verify(되돌리면 새 4건 실패 확인 후 복원). 프런트 변경 없음(이미 준비된 로컬
표가 서버 값을 우선하도록 이미 배선돼 있음, 기존 프런트 시험 재확인으로 무충돌 확인).

**APPR-01 커밋 직후 자체 재검토로 발견·수정한 회귀 — role 게이트 없이 서버 경로를 무조건
통과시켰다**: APPR-01을 커밋하고 바로 이어서 NOTI-04R(아래)을 구현하려고 코드를 다시
읽다가, RG-02의 "serverHref만 있으면 role 검사 없이 통과" 로직을 그대로 재사용한 게
틀렸다는 것을 직접 확인했다 — RG-02의 원래 대상(document/ticket/board_post/chat_room/
chat_mention)은 전부 **사용자 콘솔 화면**이라 role 제한이 없어서 안전했지만, APPR-01이
새로 추가한 approval/schedule/job/runner는 **관리 콘솔 화면**이다. 특히 `job_failed`는
그 작업을 만든 사람(어떤 role이든)에게, `approval_decided`는 요청자(위임받은 일반
사용자가 포함될 수 있다고 `notify_approvers`의 자체 docstring이 명시)에게 가는데
`/jobs`·`/approvals`는 `CONSOLE_READ_ROLES`(operator+) 전용이다 — 서버가 `related_route`
를 계산해 준다고 role 검사를 건너뛰면 **일반 사용자에게 늘 403인 클릭 가능한 링크**가
생긴다. 실제 배포 전(커밋 전) 자체 재검토로 잡아 같은 배치에서 함께 고쳤다:
- `NotificationBell.jsx`: `ROUTE_ROLES`(`/users`·`/jobs`는 기존, `/approvals`·
  `/schedules`·`/runners`를 `CONSOLE_READ_ROLES`로 새로 추가)를 서버가 준 경로에도
  적용하도록 `navigable` 계산을 통합(`!!srvRoute || (!isUser && ...)` → 경로 출처와
  무관하게 같은 `routeAllows` 검사).
- `registry/notifications.js`: `reachableAdminTarget(r, ctx)` 헬퍼 신설 — **처음엔
  "OBJ_ROUTE에 등록됐는가"로 관리 콘솔 대상을 판정**했는데, 시험을 돌리자마자 `document`
  (알림에서는 team_docs 댓글, role 제한 없음)가 감사 로그의 `OBJ_ROUTE.document`(관리
  콘솔 "문서 생성" 화면의 별칭, role 제한 있음)와 **같은 문자열의 다른 자원**이라 오탐되는
  것을 시험이 그 자리에서 잡아냈다 — 판정 기준을 "OBJ_ROUTE 멤버십"에서 다섯 유형
  (`approval`/`schedule`/`job`/`runner`/`user`)을 직접 나열하는 방식으로 바꿔 해결했다.
- 신규 시험: `notification-server-route.test.jsx` 5건(job_failed·approval_decided·
  account_locked가 role="user"에게 숨는지, operator+에게는 열리는지, 사용자 콘솔 대상은
  게이트가 아예 없는지), `notification-deeplink.test.jsx` 2건(렌더 레벨 — 정적 항목으로
  남는지). 둘 다 revert-to-verify(되돌리면 실패 확인 후 복원).

**NOTI-04R 구현완료 — 사용자 알림 딥링크**: `user` 유형 알림(`account_locked` 등)이
`/users` 전체 목록이 아니라 그 사용자 상세로 바로 가게 했다. `Users.jsx`가 registry
기반이 아닌 수제 화면이라 다른 화면들의 `onQuery` 배선을 그대로 못 쓴다 — 같은 계약
(단건 `GET /api/admin/users/{id}`, 목록에 없어도/다른 페이지여도 열림, 실패 시 이유
안내, 연 뒤 주소에서 `id` 제거)을 직접 만들었다. 프런트 두 표(`NotificationBell.jsx`
로컬 `OBJ_ID_PARAM`, `registry/shared.js` `OBJ_ID_PARAM`)와 백엔드
`destinations.py`에 `user`를 추가해 APPR-01과 같은 경로로 완결했다.
**구현 중 잡은 두 번째 버그**: `?id=` 처리를 "이미 열린 화면에 같은 라우트로 다시
딥링크가 온 경우"만 다시 읽는 기존 효과(`appliedSearchRef`)에 얹었는데, 그 ref가
**최초 마운트 시의 주소값으로 초기화**돼 있어 최초 진입 자체에서 이 효과 전체(따라서
`id` 처리도)가 곧바로 건너뛰어졌다 — 신규 시험이 처음부터 실패로 잡아냈다. ref 초기값을
`null`로 바꿔 최초 마운트에도 반드시 처리되게 고쳤다. `users-requery-navigation.test.jsx`
신규 2건, revert-to-verify(되돌리면 실패 확인 후 복원). 프런트·백엔드 전체 회귀는 커밋
직전 재확인.

이것으로 알림 딥링크 계열(RG-02/APPR-01/NOTI-04R)이 서버(`destinations.py`)를 단일
출처로 완결됐다 — 남은 것은 `schedule_run`(대상 화면에 실행 건별 onQuery가 없음, 의도적
제외)뿐이다. 다음은 새 후보를 다시 코드로 재확인해 고른다 — 사용자 확인 대기 없이
진행한다.

**계속(2026-08-11, 연속 실행) — OPS-05·OPS-02·AI-27·UB-07 구현완료 + SEC-12R/SEC-13R
문서 정정**: NOTI-04R 커밋 직후 포크로 다음 후보를 찾아 코드로 재확인한 뒤 순서대로
처리했다.
- **OPS-05 구현완료**: `save_upload`(`app/core/uploads.py:146-148`)의 `mkdir`/
  `write_bytes`에 `OSError` 처리가 없어 디스크 풀·권한 드리프트 같은 파일시스템 오류가
  그대로 전역 핸들러까지 올라가 한국어 UI에 영어 "Internal server error"가 뜨던 것을
  고쳤다. `app/core/errors.py`에 `StorageUnavailableError`(503, `NotionNotConfiguredError`
  와 같은 패턴) 신설 — 원인(OSError 원문·경로)은 `logger.exception`으로 서버 로그에만
  남기고 사용자에게는 "파일을 저장할 수 없습니다. 잠시 후 다시 시도해 주세요."만 노출한다
  (info-leak 방지). `test_uploads_namespace.py`에 신규 2건(`Path.mkdir`/`write_bytes`
  몽키패치), revert-to-verify(되돌리면 import 에러로 즉시 실패 확인 후 복원).
- **OPS-02 구현완료**: installer(`scripts/install-clovirone-web-assistant.sh`)의
  `install -d` 소유권 목록에 형제 넷(`exports`·`generated`·`temp`·`locks`)은 있는데
  `uploads`가 빠져 있던 것 — 한 번 어긋나면(OPS-01 실사고) 영구히 어긋난 채로 남고
  재설치로도 안 고쳐지는 재발 경로였다. 한 줄 추가 + 신규 정적 회귀 시험
  `tests/regression/test_installer_uploads_ownership.py`(형제 다섯 전부 존재 확인),
  revert-to-verify. **직접 확인 못 함(❌)**: `bash -n` 문법 검사만 했다 — 실서버
  설치·업그레이드 실행이 있어야 실제 `chown` 결과를 볼 수 있다.
- **SEC-12R/SEC-13R 문서 정정(코드 변경 없음)**: BACKLOG.md가 "고칠 곳은
  `home/readers.py` 두 함수에 viewer를 넘기는 것"이라고 미해결로 적어 뒀는데, 직접 코드를
  읽으니 **이미 고쳐져 있었다** — `app/home/readers.py:69,116`의
  `recent_documents(viewer=)`/`recent_board_posts(org_id=)`가 각각 `doc_in_scope`/
  `list_posts`의 org 필터로 실제 스코프 필터링을 하고, `app/home/service.py:127-128`이
  이미 `viewer=user`/`org_id=...`로 넘기고 있다(함수 자체의 `SEC-13:`/`SEC-12:` 인라인
  주석이 이 판정을 명시). 실제로는 MEGA CYCLE I(2026-08-10, 이 문서 위 §66 부근)에서
  SEC-12/SEC-13 본체가 이미 구현됐는데 그 정밀화 변형인 `-R` 표만 "발견"으로 방치돼
  있었던 것 — 오래된 backlog 서술을 검증 없이 실행하지 않는다는 원칙이 여기서도
  그대로 확인됐다. BACKLOG.md 두 행을 취소선+정정 메모로 갱신.
- **AI-27 구현완료**: 드로어 컴포저(`AssistantDrawer.jsx`)가 MUI `InputBase` 단일행
  (HTML `<input>`)이라 여러 줄을 못 쓰고, 폼 안의 `<input>`은 Enter를 누르면 IME 조합
  여부와 무관하게 그대로 제출돼 한글이 조합 중 전송될 수 있었다 — 전체화면 `Chat.jsx`는
  이미 네이티브 `<textarea>` + IME 가드(`isComposing`\|`keyCode===229`)로 이 문제가
  없었다. `useChat()`이 이미 내주고 있던(그런데 드로어가 안 쓰고 있던) `textareaRef`
  (자동 높이 `useLayoutEffect`, `useChat.js`)를 재사용해 같은 네이티브 textarea +
  IME 가드를 이식 — 기계를 두 벌로 만들지 않는다는 이 파일 자체의 원칙을 그대로
  따랐다. `textarea`는 Enter로 폼을 제출하지 않으므로(줄바꿈만 삽입) 전송은 버튼 클릭
  또는 명시적 `onKeyDown`이 `doSend()`를 부를 때만 일어난다(`Chat.jsx`와 동일 패턴).
  신규 시험 `assistant-drawer-composer.test.jsx`(3건: Shift+Enter는 줄바꿈만/Enter는
  전송/`keyCode 229`인 Enter는 무시), revert-to-verify(되돌리면 "Enter가 보낸다" 시험이
  실패 확인 후 복원 — 나머지 2건은 "보내지 않는다"는 원래 코드에도 우연히 참이라 그
  자체는 회귀 신호가 약함, 정직하게 기록).
- **UB-07 구현완료**: 공지 `dismiss()`(`app/announcements/service.py`)가 "이미
  닫았는가"를 SELECT로 확인한 뒤 없으면 INSERT하는 check-then-insert라 탭 두 개(또는
  더블클릭)가 거의 동시에 같은 공지를 닫으면 `uq_announcement_dismissal`(announcement_id,
  user_id) UNIQUE 제약에 걸린 쪽이 잡히지 않은 `IntegrityError`로 500이 됐다 — 함수 자체
  docstring이 약속한 "이미 닫았으면 False(멱등)"와 정반대. `db.flush()`를
  `try/except IntegrityError`로 감싸 `db.rollback()` 후 `False`를 반환하도록 고쳤다
  (rollback이 필요한 이유: flush 실패로 세션이 pending-rollback 상태가 되면 `get_db`의
  요청-끝 commit까지 `PendingRollbackError`로 깨진다).
  **시험 작성 중 겪은 것**: `tests/integration/test_quota_toctou.py`의 실스레드+`Barrier`
  기법을 그대로 썼는데, 1차 시도(SELECT 시점에만 barrier 하나)는 매번 green이 나와
  버그가 있는 원래 코드에서도 재현이 안 됐다 — 원인을 스레드별 타임스탬프로 직접 진단해
  보니 `barrier.wait()`는 두 스레드가 "그 지점에 도달"하는 것만 맞출 뿐 그 다음
  `real_execute()` 호출까지 동시에 실행되는 건 보장하지 않아서, 한쪽이 스케줄링에서
  앞서가 INSERT+commit을 통째로 끝낸 뒤에야 다른 쪽이 자기 SELECT를 실행해(이미 커밋된
  행을 그대로 보고) 조용히 `False`를 반환할 뿐 경합 자체가 전혀 안 걸렸다. `flush()`
  시점에도 barrier를 하나 더 둬(두 스레드의 INSERT 시도를 실제로 겹치게) 3/3 재현으로
  고쳤다 — 표면적으로 "테스트가 통과한다"는 신호를 그대로 믿지 않고 그 초록불이 실제로
  버그를 걸고 있는지 직접 반증(수정 전 코드에 붙여 실패하는지)까지 해야 한다는 이
  세션의 반복 원칙이 시험 코드 자체를 짤 때도 그대로 적용됐다.
  `tests/regression/test_announcement_dismiss_race.py` 신규 1건, revert-to-verify(되돌려
  3회 연속 `IntegrityError`로 실패 확인, 복원 후 3회 연속 통과 확인 — 스레드 타이밍 문제라
  1회가 아니라 반복 확인함).
- **검증**: 프런트 전체 회귀(211파일/1404건) + `STATIC_CHECKS_OK`(번들 재빌드 포함) +
  네 변경 전부에 대한 focused 시험(uploads·installer 회귀·drawer 컴포저·공지 경합 3회
  반복) — 전부 green 확인함. 백엔드 전체 회귀(2670+건)는 이 배치 전체(OPS-05/OPS-02/
  AI-27/UB-07)가 다 들어간 상태로 재실행했다 — 1차 실행(UB-07 반영 전)은 exit code 0·
  실패표시 0건 확인, **UB-07까지 포함한 2차 전체 실행은 이 문단을 쓰는 시점에 아직 배경
  실행 중**이다(커밋은 그 결과를 보고 나서 한다 — 미완료 상태로 green이라 적지 않는다).
  실서버/브라우저 확인은
  배포 Blocker로 여전히 불가(§D-54).

다음은 새 후보를 다시 코드로 재확인해 고른다 — 사용자 확인 대기 없이 진행한다.

---

## 🟣 MEGA CYCLE H — AI 도우미, MEGA CYCLE A 후속 quick-fix 스윕 완료 (2026-08-10)

D-54(2026-08-10) 지시 직후 BACKLOG ID 정합성 수정을 마치고 바로 착수한 두 번째 사이클.
Master Plan 축 2(AI 도우미)로 복귀 — MEGA CYCLE A가 러너 상태머신의 공통 근본원인 5개를
고쳤지만, 그 위에 남은 `AI-*` 개별 결함(61건)은 손대지 않은 채였다. "몇 건 처리했나"가
아니라 이 서브영역이 실질적으로 마무리됐는가를 기준으로 넓게 훑었다.

**조사(넓게)**: 남은 `AI-01`~`AI-68`(중복 정리 후) 전부를 훑어 (a) MEGA CYCLE A의 TTL
수정과 겹쳐 보이지만 실제로는 아직 안 고쳐진 것, (b) quick·안전한 수정, (c) 스트리밍·
동시성·에이전틱 기능·드로어 재설계 같은 깊은 아키텍처 작업으로 분류했다. (a) 조사 중
"AI-30(Critical)"·"AI-66(Med, 구 AI-30)"가 실은 MEGA CYCLE A에서 **이미 고쳐져 있는데**
BACKLOG 상태만 "발견"으로 방치돼 있었음을 코드 재확인으로 발견(위 BACKLOG ID 수정 문단).

**구현(12건, (a)+(b) 전부)**:
- **AI-37**(탈출어 안내): CREATE 흐름 재질문 7곳을 하나씩 고치지 않고, 공용 `response()`
  헬퍼 한 곳에서 `NEED_INPUT`+`mode==CREATE`면 항상 탈출어를 별도 줄로 덧붙이게 함(기존
  스캔 가능 다중 줄 포맷 보존).
- **AI-65**(질문판정 정규식): 조합 불가능한 호환 자모 `ㄹ까`/`ㄴ지`를, 종성이 ㄹ/ㄴ인
  완성형 음절 전체를 유니코드 분해식으로 계산한 문자 클래스로 교체 — 될까·할까·바꿀까·
  된 건지 전부 매칭 확인.
- **AI-03**(메시지 길이 상한 3중화): 러너 `MAX_MESSAGE_CHARS`를 플랫폼이 실제로 강제하는
  값(5,000)에 맞춰 12,000→5,000(도달 불가능하던 방어선을 실제 정책과 일치시킴).
- **AI-04**(시드 러너 행 메타데이터): 실재하는 러너 경로(`send_message`/`sync_context`/
  `generate_quiz`)로 교체(런타임 영향 없는 순수 메타데이터).
- **AI-49**(빈 2xx 응답): 안내 말풍선은 `PROC_DONE` 유지하되 **사용자 메시지**를
  `PROC_FAILED`+`error_code`로 남겨 '다시 시도'를 되살림, `on_failure`와 같은
  `-fail-{job.id}` ID 규약으로 재시도 성공 시 옛 안내가 자동 정리됨을 테스트로 확인.
- **AI-38**(대화 본문 검색): `GET /api/conversations?q=`가 제목·본문 둘 다 검색(IDOR
  격리 테스트 포함), 프런트는 300ms debounce로 서버 검색 전환.
- **AI-41**(결과 카드 앱 내 딥링크): `TicketCard`에 `AssistantPanel`과 같은 패턴의
  `#/tickets/{id}` 링크 추가.
- **AI-44**(AI 쿼터 미표시): 자기서비스 `GET /api/me/ai-quota` 신설(관리자 전용
  `/api/ai-quotas*`와 분리), 컴포저 위에 "오늘 AI 사용량 X/Y" 표시(상한 있을 때만).
- **AI-45**(기능 플래그 없음): `chat_enabled`(기본 ON) 신설 — 대화 CRUD·메시지·쿼터
  API 각각에 걸되, 앱 루트(`app/chat/router.py "/"`, React 앱 전체 진입점)는 **일부러
  제외**하고 테스트로 그 경계를 못박음.
- **AI-67**(죽은 `?c=` 코드): 삭제 — sessionStorage(`CHAT_LAST_CONV_KEY`)만으로 이미
  충분함을 확인.
- **AI-55**(제목 잘림에 표시 없음): `auto_title()`이 60자 초과 시에만 "…" 부착.
- **AI-56**(목록 정리 수단 없음): 방치된 "새 대화" 2개 이상일 때 사이드바에 개수 밝힌
  일괄 보관 버튼(확인 필요, 자동·무확인 보관은 하지 않음).

**보류(6건, 사유 BACKLOG.md에 각각 기록)**: `AI-01`(새 러너 엔드포인트 필요, 기본
OFF라 무영향) · `AI-16`(플랫폼→러너 삭제 HTTP 경로 신설 필요, MEGA CYCLE A TTL로 노출
창은 이미 24h로 제한) · `AI-31`+`AI-53`(의도분류 앞단 재설계 — 좁은 패치는 이미 세 번
회귀를 냈다고 코드 스스로 경고) · `AI-43`(공유 브레이크포인트 값이라 라이브 시각 확인
필요) · `AI-48`(모든 잡 타입이 공유하는 스윕 임계값이라 채팅만 못 낮춤) · `AI-59`
(AI-16과 같은 근본원인). `AI-47`은 **재검토 후 원래 서술이 틀렸음을 확인**(두 제안 칩
목록은 중복이 아니라 의도적으로 다른 목적 — 전체화면 시작 예시 vs 드로어의 맥락 인식
문구) — 통합하지 않음.

**검증**: 신규 회귀 테스트 42건(러너 7 + 백엔드 통합 16 + 프런트 vitest 19) 전부
revert-to-verify 또는 직접 확인. 러너 전체 287건, 백엔드 전체 약 2,650건(수집 기준),
프런트 vitest 200파일/1,332건 전부 green. `bash scripts/static_checks.sh` → `STATIC_CHECKS_OK`
(도중 새 FlagSpec 설명문에 쓴 가운뎃점(·) 1건을 정적 검사가 잡아 콤마로 교체 — 그 자체가
검사기 가치 증명). 커밋은 아래 §BUILD_LOG 참고.

**배포·실서버 Chrome 검증 — Blocker(외부, 2026-08-10)**: 사용자가 채팅에 평문으로
SSH/sudo 비밀번호를 제공하며 비대화형 자동 배포를 지시했으나, CLAUDE.md §2 불변규칙
#4("비밀번호·토큰은 명령행·파일·env·git에 남기지 않는다 — 오직 stdin/프롬프트로만,
sshpass 금지")와 에이전트 시스템 규칙("비밀번호는 사용자 승인으로도 예외를 허용하지
않는다")에 따라 거부했다. 이 비밀번호는 이제 대화 로그에 노출됐으므로 **회전 필요**
(§10에 이미 있던 조치와 합쳐짐). 대안으로 두 배포 스크립트에 한정된 NOPASSWD sudoers
항목을 제안(사용자 결정 필요). 이 Blocker는 배포·실환경 Chrome 검증에만 한정되고
(구현·테스트·정적검사·커밋은 이미 완료), 다른 독립 작업(다음 MEGA CYCLE 조사·구현)은
계속한다 — "blocked_external ≠ project stopped".

---

## 🟣 MEGA CYCLE G — Admin IA 전체 스윕 (D-54 이후 첫 큰 사이클) 완료 (2026-08-10)

D-54 지시 직후 착수한 첫 사이클. Master Plan 원래 축(디자인 시스템 후속 소진 → 관리자 IA)으로
복귀하면서, "IA-01/02/04 세 항목을 처리한다"가 아니라 **Admin IA(관리자 네비게이션·레지스트리
크로스링크) 라는 Product Area 하나를 실질적으로 끝낸다**를 기준으로 조사·구현·검증을 전부
한 사이클 안에서 계속했다.

**조사(넓게, Workflow 4-agent 병렬)**: `navConfig.js`/`registry/*.js` 전체를 훑어 (1) 등록된
화면인데 사이드바 항목이 없는 것, (2) "운영" 그룹 재구조화의 실제 구현 리스크, (3) 백엔드가
이미 참조 ID를 주는데 프런트가 안 그리는 크로스링크 결함, (4) FN-13(IA-02와 "같은 뿌리"로
명시된 옛 항목)의 잔여 범위를 각각 전담 에이전트로 병렬 조사. 코디네이터가 각 주장을 실제
소스로 개별 재검증(D-53 원칙) — `policy-usage` 누락, "운영" 그룹 재구조화가 렌더러 무수정으로
가능함, `jobs`↔스케줄/문서 크로스링크 결함, `ai_quota`/`approval_delegation`/`announcement`/
`offboarding_run` 4건의 감사 크로스링크 결함을 전부 파일·줄 번호로 확인 후 구현.

- **`IA-01`(관리자 메뉴 26곳 재검증)**: "승인/승인위임 2"는 이미 인접해 있어 하향(재현 안 됨).
  진짜 버그는 `policy-usage`(정책 사용 통계) — `registry/authoring.js`에 화면·역할 게이트가
  다 있는데 사이드바 항목만 없었다(형제 `prompt-usage`의 `headerActions`로만 닿을 수 있었다).
  "콘텐츠" 그룹에 1줄 추가. **"운영" 그룹(14항목, product-ops/system-ops/governance가 평평하게
  섞인 것)도 재구조화** — 조사 결과 `AppShell.jsx`의 `SidebarNav`와 `CommandPalette.jsx` 둘 다
  "배열 원소 하나 = 그룹 하나"로만 다뤄 최상위 그룹만 늘리면 렌더러 코드 수정이 전혀 필요
  없음을 확인. "운영 현황"(대시보드·알림·작업 큐·설정)·"시스템 인프라"(진단·시스템 설정·
  초기 설정·유지보수·백업·복구 리허설)·"거버넌스"(감사 로그·감사 이상 징후·기능 플래그·
  공지 배너) 3개로 분리, 항목·role·배지는 전부 그대로.
- **`IA-02`+`FN-13`(작업 큐 ↔ 스케줄/문서 실행 흐름)**: `IA-02`가 명시한 "서로 오갈 길이
  없다"는 재검증 결과 세 방향(실행 달력→스케줄, 문서→스케줄, 스케줄 상세의 실행 이력)은
  **이미 있었다**. 실제로 빠진 방향은 **작업 큐 → 스케줄/문서**(FN-13의 잔여 범위) — 백엔드
  (`app/jobs/router.py::_link_ids`, round30 감사 E)는 `schedule_id`/`schedule_run_id`/
  `generation_id`를 이미 응답에 내려주는데 프런트가 하나도 안 그려서 idempotency_key 문자열을
  손으로 읽는 것 말고는 역추적 방법이 없었다. `jobs.detailFields`에 `schedule_id`(→
  `#/schedules?id=`)·`generation_id`(→ `#/documents?id=`) 링크 추가, `schedule_run_id`는
  여는 화면이 없어 참조값만(가짜 링크 안 만듦). **반대 방향(스케줄/문서→작업 큐)도 같은
  사이클에서 마저 고쳤다** — `ScheduleRun`에 `job_id` 컬럼이 없어(마이그레이션 필요) 대신
  `GET /api/admin/jobs`에 `schedule_id`/`schedule_run_id`/`generation_id` **쿼리 필터**를
  신설(`json_extract`로 `payload_json` 조회 — 인덱스는 없지만 크로스링크 클릭 1회당 1쿼리라
  감내 가능). 스케줄 "실행 이력" 하위 목록에 "작업 큐" 링크 열, 문서 생성 화면에 "작업 큐에서
  보기" 액션, 실행 달력의 실행 상세 모달에 같은 버튼 추가 — 이걸로 FN-13이 완전히 닫혔다.
- **`RG-11`(신규, 같은 결함 부류 4건 추가 발견)**: `organization`/`feature_flag`(F15)와 같은
  결함이 `ai_quota`/`approval_delegation`/`announcement`/`offboarding_run` 4곳 더 있었다 —
  백엔드는 이미 이 object_type들로 감사 기록을 남기고 각 화면도 forward "감사 로그에서 보기"
  딥링크를 걸고 있었는데, `shared.js`의 `OBJ_ROUTE`에 없어 감사 로그 쪽에서 되돌아오는 버튼이
  항상 숨겨졌다(`offboarding_run`은 hand-rolled 화면이라 forward 링크 자체도 없었다). 4곳
  전부 `OBJ_ROUTE` 등록(+ `offboarding_run`만 `OBJ_ROUTE_ROLES`도 — 오프보딩 화면이 audit보다
  role이 좁다), `governance.js`의 로컬 object_type 드롭다운에 4개 옵션 보강(F15와 같은 자리,
  `shared.js`의 `OBJTYPE_OPTS` 자체는 손 안 댐), 3개 DataScreen에 forward 액션 추가,
  hand-rolled `Offboarding.jsx`에 같은 링크 추가. 부산물로 `OBJECT_KO`/`VERB_KO`
  (`lib/format.js`)도 이 4개 + 먼저 고쳐졌던 `organization`/`feature_flag`가 빠져 있어
  감사 로그 '대상'/'작업' 칸에 영어 원문이 새는 것을 발견, 7개 항목 보강.
- **`IA-04`(사용자 콘솔 vs 관리자 콘솔 UX)는 의도적으로 손 안 댐** — 재검증 결과 원 서술은
  맞고 생각보다 크다(`DataScreen.jsx` 768줄짜리 범용 registry 패턴 vs `MyTickets.jsx` 혼자
  1004줄의 완전 수제 구현). 나머지 IA-01/02/RG-11과 risk tier가 다른(nav/registry 배선
  수정이 아니라 다사이클 아키텍처 이관) 별개 작업이라, 일부만 옮기는 반쪽짜리 시도는
  CLAUDE.md의 "No half-finished implementations"를 정면으로 어긴다 — 전용 다사이클
  이니셔티브로 남긴다.

**검증**: 매 변경마다 focused vitest/pytest만 반복(D-54 원칙), 신규 테스트 파일 8개+확장
2개(`nav-ops-group-split.test.js`·`nav-policy-usage.test.js`·
`jobs-schedule-crosslink.test.jsx`·`scheduler-calendar.test.jsx` 확장·
`audit-related-object-routes.test.jsx` 확장·`object-verb-ko.test.js`·
`offboarding.test.jsx` 확장·백엔드 `test_jobs_api.py` 확장), 전부 revert-to-verify(되돌리면
정확히 그 자리에서 실패하는 것 직접 확인). 마무리 시점에 **한 번의 전체 회귀**: 프런트 vitest
**196파일/1319건** green, 백엔드 pytest **1건 실패**(`test_claim_race.py::
test_two_people_claiming_at_once_do_not_both_win`, 티켓 클레임 스레드 경합 타이밍 테스트 —
이번 사이클의 어떤 변경(jobs 라우터 필터, navConfig, audit 레지스트리)과도 무관한 파일이고,
단독 재실행에서 3/3 통과 확인 — 전체 스위트 동시 실행 부하로 인한 기존 플레이키로 판단, 정직하게
기록). `npm run build` 통과, `STATIC_CHECKS_OK`(번들 신선도 포함).

**배포**: `build-bundle.sh` → scp → `sha256sum -c` 확인 → `upgrade-clovirone-web-assistant.sh`
(DNS_NAME=clovirone-ai.gooddi.lab BIND_IP=10.100.64.71) → `UPGRADE_OK`(2026-08-10
17:05 KST) → 서비스 3종 `active` → `/healthz`·`/readyz` 200(BIND_IP 직접 curl 확인). 서빙된
번들 해시(`index.BPDxOLnv.js`)가 로컬 빌드와 일치 확인.

**실서버 실환경검증 — 정직하게 한계를 남긴다**: 배포 직후 Chrome으로 `/dashboard`를 열어
**사이드바 3그룹 분리("운영 현황"/"시스템 인프라"/"거버넌스")가 정확히 항목·순서대로 렌더되는
것을 직접 확인**(콘솔 오류 0건, 스크린샷 확보). 그런데 이어서 다른 탭들을 새로고침하는 중에
**이 브라우저의 로그인 세션이 만료됐다**(모든 탭이 같은 쿠키를 공유 — 배포와 무관, 세션
TTL이 이 장시간 세션 도중 자연 만료된 것으로 판단: 만료 직전 모든 `/api/*` 호출이 200이었고,
만료 후 하드 리로드하면 콘솔 오류 없이 깨끗하게 로그인 화면으로 떨어지는 것을 확인했다 —
서버 쪽 500이 아니라 정상적인 세션 만료 흐름). 로그인 자격 증명이 없고 스스로 만들거나
입력하지 않는다(보안 규칙) — 그래서 `jobs` 상세의 schedule_id/generation_id 링크, 스케줄
실행 이력의 "작업 큐" 열, 문서 생성의 "작업 큐에서 보기", 오프보딩의 "감사 로그에서 보기",
audit 화면의 object_type 드롭다운 4개 옵션은 **라이브 브라우저로 직접 클릭해 확인하지
못했다** — 대신 위 신규/확장 테스트 10벌이 이 부분을 revert-to-verify로 이미 검증했다.
**사용자가 브라우저에서 재로그인하면** 위 항목들을 직접 눌러 확인할 수 있다(그 전까지는
이 문서의 "정당한 미검증"으로 남긴다).

---

## 🟣 MEGA CYCLE F — Design System 후속 배치 2 (DS-14 · DS-15 · DS-20) + DS-33 완료 (2026-08-10)

MEGA CYCLE E가 후속으로 남긴 마지막 3건(DS-14/15/20)을 구현하고, MEGA CYCLE D가 발견해
둔 DS-33(neutral 배지 대비)도 같은 사이클에서 처리했다. 넷 다 "MUI 전환 이후 옛 CSS가
죽었는데 아무도 확인 안 함"이라는 같은 뿌리를 공유한다 — 조사가 깊어질수록 원 추정보다
죽은 범위가 더 넓다는 것이 계속 드러났다.

- **`DS-14`+`DS-15`**: `kit.jsx`의 `EmptyState`/`ErrorState`에 `size="compact"` prop
  추가 — 일러스트를 빼고 여백·글자를 줄여 팝오버·모달 하위목록·사이드바 같은 좁은
  맥락에 맞춘다. 확정된 7곳(`NotificationBell.jsx`의 빈 상태+오류 상태, `ChatRooms.jsx`
  2곳, `ChatRoomMembers.jsx`, `chat/ConversationSidebar.jsx`, `chat/ResultsRail.jsx`,
  `game-room/ChatPanel.jsx`, `ChatPane.jsx`)의 지역 구현을 전부 이관.
  `ResultsRail.jsx`의 기존 `MascotPose` 일러스트는 `EmptyState`의 `icon` 슬롯에 그대로
  넣어 시각을 유지했다. `NotificationBell.jsx`가 `ErrorState`에 직접 `size="compact"`를
  넘기게 되면서, 이를 CSS로 흉내 내던 `global.css`의 `.noti-pop-error .k-empty*`
  특이도 전쟁 규칙 4줄과 `screens.css`의 `.noti-empty*`(빈 상태 지역 구현용 CSS) 4줄이
  전부 죽어 함께 삭제했다. `kit.test.jsx`에 `size="compact"`가 일러스트를 실제로
  빼는지 revert-to-verify로 확인하는 신규 테스트 2건 추가.
- **`DS-20`**: `screens.css`의 `chat-*`/`game-*`/`board-*`/`doc-*` 4계열을 className
  리터럴 기준으로 전수 재검증(id/data-testid/queryKey 등 className이 아닌 우연한
  문자열 일치는 제외하는 word-boundary 정규식 스캔). 93개 후보 중 실제로 살아있는
  건 `chat-conv-actions`/`chat-conv-time` 2개뿐 — 나머지 91개(연결된 `@keyframes`
  12종 포함)를 삭제, `screens.css` 622→약 470줄. 조사 도중 `TicketBody.jsx`의
  `PROSE_SX`(존재하지 않는 `.doc-h1` 등 5개 nested selector, MUI 전환 후 전부 죽음)와
  `screens.css`의 `.tc-roomrow*`(9개, `--badge-neutral-bg`의 유일한 소비처였으나 그
  className 자체가 어느 JSX에도 안 붙어 있었음)도 같은 자리에서 확인해 함께 정리.
  `.devrep-*`/`.noti-*`는 원 조사가 경고한 대로 계열 내 생사 혼재라 이번에도 손대지
  않음. **CSS 파서 함정**: 첫 두 번의 자동 치환 시도가 주석 안에 든 `{`/`}` 문자
  (`to{opacity:1;transform:none}` 같은 설명 텍스트)에 브레이스 매칭이 속아 죽지 않은
  규칙을 남기거나 살아있는 `@keyframes`를 건드릴 뻔했다 — 주석을 플레이스홀더로
  통째로 빼낸 뒤 처리하고 원상 복구하는 방식으로 고쳐, 최종 결과의 브레이스 균형
  (`{`/`}` 192개씩 일치)과 `npm run build` 통과로 구조 무결성을 확인했다.
- **`DS-33`**: `frontend/src/styles/tokens.css`의 `--badge-neutral-fg`를
  success/warning/error와 같은 패턴으로 전용 짙은 회색(`#4F5A69`, surface-3 위 6.23,
  WCAG 상대휘도 직접 계산)으로 교체. **그런데 소비처를 추적하다 이 토큰이 실제로는
  어디서도 적용되지 않는다는 것을 발견했다** — `Badge`(`kit.jsx`)는 neutral 톤에
  `--badge-neutral-fg`가 아니라 MUI 기본 `color="default"`를 쓰고, 유일한 다른
  소비처(`.tc-roomrow-tag`)도 DS-20 조사에서 이미 죽은 것으로 확인해 삭제했다. 즉
  **이 수정은 수치상 옳지만 화면에 보이는 효과가 없다** — 실서버 시각 확인은 의미가
  없어 생략하고 정직하게 기록만 한다. 같은 조사로 `kit.css`의 `.k-badge--*`(neutral
  포함 9개, `Badge`가 톤 접미사 className을 더 이상 안 붙여 전부 죽음)도 함께 삭제.
  `app/static/css/tokens.css`(로그인 화면 정적 사본) 쪽은 배경이 `color-mix()` 틴트라
  합성 배경 위 대비 재계산이 별도로 필요해 이번에도 범위 밖으로 남긴다(MEGA CYCLE D와
  같은 판단).

**검증**: 프런트 vitest 192파일/1283건 green(1건 무관한 타임아웃 플레이키 재현·재시도로
확인, `doc-create-form.test.jsx` — 단독 실행 시 2초에 통과, 전체 스위트 동시 실행 부하
문제로 이번 변경과 무관). `size="compact"`는 revert-to-verify로 재현 확인. `game-room/
gameroom-smoke.test.jsx`는 채팅 빈 상태 문구가 한 줄에서 제목+설명 두 줄로 갈라진 것에
맞춰 어서션 갱신(그 자체가 회귀가 아니라 EmptyState 구조 변경의 정상적 결과임을 확인 후
수정). 백엔드 pytest **2642개 전체 green**(변경 없음, 게이트로 재확인), `npm run build`
통과(브레이스 균형·번들 크기 확인), `STATIC_CHECKS_OK`(번들 신선도 포함). 커밋은 이 문서
갱신과 함께.

**배포**: `build-bundle.sh` → scp → `sha256sum -c` 확인 → `upgrade-clovirone-web-assistant.sh`
(DNS_NAME=clovirone-ai.gooddi.lab BIND_IP=10.100.64.71) → `UPGRADE_OK`(2026-08-10
15:20 KST) → 서비스 3종 `active` → `/healthz`·`/readyz` 200(BIND_IP 경유 직접 curl 확인,
127.0.0.1 loopback은 nginx가 IP-literal로 바인딩해 응답 안 함 — 기존에도 그랬던 정상 구성).
서빙된 번들 해시(`index.DVCoIXcd.js`)가 로컬 빌드와 일치하는 것 확인.

**실서버 실환경검증**: `/chat`(AI 도우미 사이드바)에서 존재하지 않는 검색어를 쳐 **컴팩트
빈 상태("검색 결과가 없습니다")가 실제로 좁은 사이드바 폭에 맞게 렌더되는 것을 직접
확인**(DS-14의 핵심 대상) — 콘솔 오류 0건. `/chat-rooms`(새 그룹 모달), `/team-docs`
(목록+상세, 문서 종류 배지), `/my-tickets`(목록+티켓 상세, 상태·우선순위 배지) 전부
Chrome으로 직접 열어 정상 렌더 + 콘솔 오류 0건 확인 — 특히 배지들이 여전히 올바른 색으로
뜨는 것은 `kit.css`의 `.k-badge--*`(DS-33에서 삭제) 없이도 `Badge`(`kit.jsx`)의 MUI
`color`/`sx` 경로가 이미 전담하고 있었다는 이번 조사 결론을 실측으로 재확인한 것이다.
**정직하게 남기는 한계**: `NotificationBell.jsx`의 빈 상태/오류 상태, `ChatRooms.jsx`의
초대 목록 빈 상태, `game-room/ChatPanel.jsx`의 빈 채팅 — 셋 다 이 서버엔 이미 실 데이터가
있어(알림·초대 가능 사용자·게임방 전부 존재) 빈 상태 자체를 라이브로 재현하지 못했다
(유닛 테스트 + revert-to-verify로만 검증). 게임방을 새로 만들어 강제로 재현하는 것은
실 데이터에 부작용을 남기는 것이라 하지 않았다.

---

## 🟣 MEGA CYCLE E — Design System 후속 배치 (DS-07 · DS-21 · DS-22) 완료 (2026-08-10)

MEGA CYCLE C가 조사만 하고 구현을 미룬 6건(DS-07/14/15/20/21/22) 중 이미 설계가 확정돼
있던 3건을 구현했다 — 새 조사 없이 바로 구현. 나머지(DS-14/15/20)는 설계는 나왔지만
`EmptyState`/`ErrorState`에 `size="compact"`를 먼저 추가해야 하거나(DS-14/15) 클래스별
개별 검토가 필요해(DS-20) 후속 배치로 남겼다.

- **`DS-07`**: `kit.jsx`에 공용 `SectionTitle`(title/children 겸용, action·help 선택,
  `component`/`sx`로 태그·여백 조정) 추가. `Home.jsx`(`CardHead` ×3곳)·`MyStats.jsx`
  (`CardHead` ×2곳)·`Profile.jsx`(`SectionTitle` ×5곳, `component="h2" sx={{mb:2}}`로
  원래 무게 유지)·`AssistantPanel.jsx`(인라인 1곳)의 로컬 구현을 전부 삭제하고 이관.
  `Dashboard.jsx`의 `DashSection`(더 큰 페이지 섹션용, MEGA CYCLE C에서 이미 분리)은
  별개로 유지.
- **`DS-21`**: 9개 화면에 `className="c-screen"` 추가 — Search·Dashboard·SetupWizard
  (early-return 3곳 포함, `<>`를 `<Box className="c-screen">`로 교체)·SystemOps·
  NotionConsole·LlmConsole·Diagnostics·Maintenance·DevReport(`"devrep c-screen"`으로
  기존 클래스와 병기). **재검증 중 발견**: 원 조사가 지목한 `Settings.jsx`/`Ops.jsx`는
  둘 다 실제 구현이 아니라 재노출 shim 파일이라, 진짜 구현(`settings/SettingsMain.jsx`)은
  이미 갖고 있었고 진짜 대상은 `ops/Diagnostics.jsx`·`ops/Maintenance.jsx` 2파일이었다.
- **`DS-22`**: `Pager.jsx`에 `hasNext` prop 추가(`total`을 안 주는 API용 폴백 — `total`이
  있으면 그쪽을 우선). `Activity.jsx`의 복붙 구현(17줄)을 `<Pager total={total}
  hasNext={items.length>=PAGE_SIZE} .../>` 한 줄로 교체. **revert-to-verify 중 자체
  발견**: 두 파일을 함께 되돌리면 테스트가 그대로 통과해 버렸다 — `Activity.jsx`의 예전
  손코딩이 이미 이 경우를 올바르게 처리하고 있어서다(버그는 `Pager.jsx`라는 공용
  컴포넌트 쪽에만 있었다). `Pager.jsx`만 따로 되돌려서야 실패를 직접 확인했다.

**검증**: 프런트 vitest 192파일/1281건(신규 `activity.test.jsx` 페이지네이션 테스트 1건
포함) green, 백엔드 pytest 전체 green(변경 없음, 게이트로 재확인), `STATIC_CHECKS_OK`,
번들 재빌드. 커밋 `d7d22ca`.

**배포**: `build-bundle.sh` → scp → 체크섬 확인 → `upgrade-clovirone-web-assistant.sh`
→ `UPGRADE_OK`(2026-08-10 13:58 KST) → 서비스 3종 `active` → `/healthz` 200.

**실서버 실환경검증**: `/me`(SectionTitle ×3)·`/my-stats`(SectionTitle+help)·`/profile`
(SectionTitle h2 ×4곳 모두)·`/system`(SystemOps, c-screen)·`/activity`(Pager) 전부
Chrome으로 직접 열어 정상 렌더 + 콘솔 오류 0건 확인. `/activity`는 실제로 "다음" 버튼을
눌러 1페이지→2페이지 이동, "1/18, 총 352건"→"2/18, 총 352건"으로 갱신되고 새 항목이
로드되는 것까지 라이브로 확인 — 이 서버의 `/api/me/activity`는 실제로 `total`을 주고
있어(하네스 조사 당시 가정과 달리) `Pager`의 `total` 우선 경로가 라이브로 검증됐다.
`hasNext` 폴백 경로 자체는 이 서버 데이터로는 재현 못 함(로컬 유닛 테스트로만 검증,
정직하게 남긴다).

---

## 🟣 MEGA CYCLE D — 로그인 화면 정적 토큰 사본 부분 동기화 (DS-18 후속) 완료 (2026-08-10)

MEGA CYCLE C가 DS-18을 재조사하다 발견한 것의 후속 — `app/static/css/tokens.css`
(로그인 화면·`base.html` 전용, React 번들과 별개)가 `frontend/src/styles/tokens.css`
와 약 54개 변수만큼 어긋나 있었다.

**의도적으로 축소한 범위**: 54개 전부를 맞추지 않고 **핵심 브랜드/중립/상태 색 +
모서리(약 20개)만** 동기화했다 — `color-primary-strong`·`color-bg`·`color-card`·
`color-border`·`color-text`·`color-muted`·`color-success`·`color-warning`·
`color-error`·`radius-*`(라이트·다크). **일부러 안 건드린 것**: 상단바 그라데이션
(`--g-topbar`)·사이드바 활성색·배지 글자색처럼 이 파일 자체에 개별 WCAG 대비 계산이
딸린 합성 토큰(맹목적 값 치환이 그 계산을 무효화할 위험이 있어 재계산 없이는 손 안
댐), `--color-ink`(프런트는 테마 무관 고정인데 이 파일은 테마별로 다른 구조적 차이라
값만 맞추는 걸로 안 끝남 — 설계 판단 필요).

**검증에서 실제로 잡힌 것**: `tests/regression/test_css_says_what_it_does.py`(사이드바
대비를 코드에서 직접 재계산해 주석과 대조하는 자동 테스트)가 색 동기화로 실제
계산값이 바뀐 4곳을 정확히 잡아냈다 — 전부 진짜 회귀는 아니었고(4.97~15.00, 전부
AA 4.5 기준 통과) 주석에 박힌 옛 숫자가 낡은 것이었다, 재계산한 값으로 주석 갱신 후
재통과 확인. **이 자동 테스트가 커버 안 하는 배지(badge) 8곳도 직접 재계산해서
주석을 갱신**했다(5.10~7.79) — 이 과정에서 **neutral 배지의 대비가 라이트에서
4.5에 살짝 못 미치는 것(4.28)을 발견**했는데, `frontend/src/styles/tokens.css`의
실제 값으로 같은 조합을 재계산해도 4.43으로 똑같이 살짝 못 미쳐 **이 파일이 새로
만든 문제가 아니라 제품 전체가 공유하는 기존의 작은 결함**임을 확인 — `DS-33`으로
신규 기록만 하고 이번 사이클에선 안 고침(범위 밖).

**검증**: 백엔드 pytest 전체 green(`test_css_says_what_it_does.py` 포함),
`STATIC_CHECKS_OK`. 배지 색 4종(성공/경고/오류/정보) × 라이트/다크 전부 WCAG 상대휘도
공식으로 직접 재계산해 4.5 이상 확인(5.10~7.79). 커밋 `3170857` + `6b3a9f4`.

**배포**: `build-bundle.sh` → scp → 체크섬 확인 → `upgrade-clovirone-web-assistant.sh`
→ `UPGRADE_OK`(2026-08-10 13:02 KST, 두 번째 배포가 최종본) → 서비스 3종 `active` →
`/healthz` 200. 배포된 정적 파일을 직접 curl로 확인해 새 값이 실제로 서빙되는 것 확인.

**실서버 실환경검증 — 정직하게 한계를 남긴다**: 로그인 화면 자체를 Chrome으로 직접
열어 라이트/다크 렌더링을 눈으로 비교하지는 **않았다** — 이 브라우저 세션의 모든 탭이
같은 쿠키를 공유해서, 로그인 화면을 보려고 로그아웃하면 동시에 다른 화면들을 검증하던
탭도 전부 끊긴다. 그 정도 지장을 감수할 만큼 급한 변경이 아니라고 판단해, 대신
① 정적 CSS 파일이 실제로 새 값으로 배포된 것을 curl로 직접 확인, ② 모든 색 변경의
WCAG 대비를 코드로 직접 재계산, ③ 기존 자동 회귀 테스트 통과로 검증 상한을 삼았다.

---

## 🟣 MEGA CYCLE C — Design System 근본원인 (DS-01~32 전수 재검증) 완료 (2026-08-10)

Master Plan 원래 순서(§WORK_PLAN_INDEX §3)의 축 1(디자인 시스템)을 Cycle 4가 건너뛰고
곧장 CORE/UA/UB로 들어간 것이 이 세션의 가장 큰 계획 이탈이었다(PROGRESS_STATUS §5-1) —
Critical 2건(AI-30·FAIL-01)이 이번 세션에서 전부 처리되며 그 이탈을 되돌릴 여유가
생겨, D-53 지시대로 원래 축으로 복귀했다.

**방법론**: `docs/BACKLOG.md`의 DS-01~32(2026-08-04~08 감사에서 나온 미착수 항목) **31건을
전부 재검증**하고 나서야 손을 댔다 — 오래된 조사라 코드가 그 사이 바뀌었을 수 있다는
전제로, 각 항목의 file:line을 다시 읽고 원 서술이 지금도 맞는지 먼저 확인했다(네 개
병렬 조사 에이전트로 토큰/버튼/배지 · 컴포넌트 통합 · CSS 위생/죽은 코드 ·
반응형/대비/4K 네 클러스터를 나눠 맡김). **재검증 결과 12건은 원 서술 그대로 실재해
고쳤고, 12건은 재현이 안 되거나 이미 해결돼 있어 코드를 안 건드리고 정정만 했고, 나머지는
설계는 확정했지만 이번 사이클 범위 밖으로 미뤘다.** 이 비율 자체가 "오래된 감사 결과를
그대로 실행하면 안 된다"는 이 세션의 원칙을 다시 확인해 준다.

**구현한 12건**(전부 공통 원인 하나를 고쳐 여러 화면이 동시에 좋아지는 형태, 개별 화면
패치 없음):
- **`DS-32`(High, 확정 회귀)** — `TopSearch.jsx` 2곳 + `kit.css` 13곳의 절대 px 폰트
  크기를 기존 `--font-size-xs/sm/md` rem 토큰으로 교체. 4K에서 `--clv-root-fs`(16→18→20px)
  레버가 커져도 안 따라가던 게 근본 원인 — 그중 `Ctrl K` 배지(11px)는 12px 접근성
  하한을 어느 뷰포트에서나 밑돌고 있었다.
- **`DS-19`** — `kit.css`/`sx` 이중 선언 실충돌 6곳(`.k-empty`·`.k-stat`·`.k-page-head`·
  `.k-field`·`.c-toolbar-card`·`.k-badge`) 제거 — 승자가 스타일 주입 순서라는 우연에
  달려 있던 비결정성을 없앰. `justify-content`처럼 CSS에만 있던 속성 하나는 먼저
  `PageHeader`의 sx로 옮긴 뒤 CSS를 지웠다.
- **`DS-09`** — `Badge`에 purple/teal/indigo/pink 톤 배선. `tokens.css`에 이미 있던
  (다크모드 대응·대비 검증 완료) CSS 변수를 그대로 재사용 — 새 색 발명 없음. 문서 종류
  8종이 전부 회색 한 가지로 뭉개지던 것이 이제 다 다른 색으로 렌더된다.
- **`DS-04`** — `Button`에 `loading` prop(스피너 오버레이 + `visibility:hidden`으로 라벨
  폭 고정). 가장 레버리지 큰 호출부인 `ModalFooter`(앱 전역 폼 제출 버튼)를 마이그레이션.
- **`DS-06`** — `DataTable` 본문 셀에 기본 `minWidth`(4.5rem) 바닥값 — 열 폭 미지정 시
  `overflowWrap:anywhere`가 폭을 한 글자까지 줄이던 것(SettingsMain.jsx가 실측으로
  이미 겪은 것과 같은 버그)을 관리자 registry 표 28개 전부에서 한 줄로 막음.
- **`DS-17`** — `Dashboard.jsx`(916줄)에 있던 공유 컴포넌트(`DashSection`·`StatusTile`·
  `Note`·`STAT_GRID`·`SERVICE_GRID`·`HEADLINE_GRID`)를 새 `ui/adminKit.jsx`로, 순수
  포맷 헬퍼(`serviceLabel`·`daysSince`·`fmtNum`·`fmtProcessingTime`·`fmtCertDays` 등)를
  기존 `ops/opsHelpers.js`로 이동(동작 변경 없는 순수 리팩터). **조사 중 자체 발견**:
  `opsHelpers.js`가 `fmtCertDays`를 Dashboard.jsx와 별개로 재정의해 두 벌이 따로 살아
  있었다 — 이 이동으로 자동 해소.
- **`DS-10`** — `Drawer = Modal` 별칭 삭제, 실제로는 중앙 다이얼로그로 쓰이던 6개 호출부
  (SubListDrawer·DataScreen·Offboarding·SettingEditor·SettingVersions·Users)를 `Modal`
  로 직접 부르게 이름 정정(동작 변경 없음, 이름만 정확해짐).
- **`DS-11`** — 중복 미디어쿼리 리터럴(`"(max-width:899.95px)"`, kit.jsx·MyTickets.jsx
  각자 갖고 있었다)을 `theme.js`의 `TABLE_CARD_QUERY`(`BREAKPOINTS.md` 기반)로 추출.
  **표 자체 통합은 안 함** — 재검증 결과 `GroupedTickets`(다중 tbody 그룹 헤더)와
  `DevReport`(인쇄 CSS·헤더 툴팁·인라인 차트)는 `DataTable`이 못 하는 실제 구조적
  필요가 있었다.
- **`DS-23`** — `columnHelpers.jsx`의 bare `<a>` 2곳을 MUI `Link`로(28개 registry 표
  전부에 한 번에 적용), `registry/shared.js`의 raw `style` 객체도 `Typography`+시맨틱
  토큰으로 교체.
- **`DS-29`** — 상단바 그라데이션 마지막 정지점이 `DEFAULT_ACCENT`(#536CD6) 리터럴로
  박혀 있어 사용자가 강조색을 바꿔도 상단바만 그대로였던 것 — `theme.palette.brand.accent`
  (실제 선택된 강조색)를 읽게 고침.
- **`DS-30`** — `PROJECT_TONE_COLORS`의 주황(`#F08C00`)이 라이트 테마에서 대비 2.48:1로
  기준(3:1) 미달 — `#C26A00`로 교체, WCAG 상대휘도 공식으로 라이트·다크 양쪽 대비를
  직접 재계산해 확인(라이트 3.921·다크 4.491).
- **`DS-05`(부분)** — `theme.js`에 `FONT_WEIGHT` 토큰(regular/medium/semibold/bold/
  extrabold) 신설. 실제 호출부 70여 곳의 일괄 치환은 이번 범위 밖 — 토큰만 만들어 새
  코드가 쓸 수 있게 함.

**재검증 후 다운그레이드(코드 변경 없음)**: `DS-01`·`DS-02`(버튼 위계는 이미 표준적),
`DS-03`(이미 `size="sm"` 지원), `DS-12`(9화면 중 3개는 필터 UI 자체가 없고 나머지도
전제가 안 맞음), `DS-13`(AppShell pill은 애초에 탭이 아님), `DS-16`(StatCard가 이미
`kind` 축을 가짐), `DS-24`(원 서술의 영향 구간이 틀림, `lg`가 아니라 `xl`), `DS-26`
(PROSE_MAX_WIDTH 이미 적용됨), `DS-27`(두 세부 주장 다 재현 안 됨), `DS-31`(세 곳 다
컨텍스트상 올바른 선택, 버그 아님). **`DS-25`**는 부분 정정(`FAB_CLEARANCE` "소비자
0" 서술이 낡음, 이미 3곳이 쓰고 있음).

**설계는 확정, 구현은 후속 배치로 미룸**: `DS-07`(공용 `SectionTitle` 컴포넌트 설계
확정, 5곳 이관 안 함), `DS-14`/`DS-15`(`EmptyState`/`ErrorState`에 `size="compact"`
추가하는 설계 확정, `NotificationBell.jsx` 등 마이그레이션 안 함), `DS-20`(dead CSS
계열 4개는 전수 확인으로 안전 삭제 가능하나 실행 안 함, `devrep-*`/`noti-*`는 부분
생존이라 개별 검토 필요), `DS-21`(4~9개 화면에 `className="c-screen"` 추가하는 방법
확정), `DS-22`(`Pager.jsx`가 `total==null` 폴백을 먼저 지원해야 함).

**재평가로 범위가 오히려 커진 항목**: `DS-18`("토큰 4벌, 3개 값 어긋남")은 재검증
결과 원 서술이 크게 축소돼 있었다 — `theme.js`/`tokens.css`/`density.js` 셋은 정상
(기준선 대조 테스트로 지켜짐). **진짜 문제는 `app/static/css/tokens.css`(로그인 화면
전용 정적 사본) 단 하나**인데, 두 파일에 공통으로 존재하는 변수만 놓고 값을 직접
대조하니 **약 54개**(라이트 34·다크 20)가 어긋나 있었고, `frontend/src/styles/
tokens.css`에 새로 생긴 변수(`font-size-*`·`space-*`·`badge-purple/teal/pink/indigo`
등)는 정적 사본에 아예 없었다. **로그인 화면이 지금 React 앱과 다른, 한 세대 전
팔레트로 렌더되고 있다는 뜻** — 안전하게 고치려면 라이트/다크 양쪽 시각 회귀 확인이
함께 필요해 이번엔 손대지 않고 **다음 MEGA CYCLE 후보로 승격**했다.

**검증**: 프런트 vitest 192파일/1280건 green(신규 파일 `ui/adminKit.jsx` 포함), 백엔드
pytest 전체 green(변경 없음, 게이트로 재확인), `STATIC_CHECKS_OK`, 번들 재빌드. 커밋
`d2286ab`.

**배포**: `build-bundle.sh` → scp → `bundle.sha256`/`MANIFEST.sha256` 둘 다 일치 확인 →
`upgrade-clovirone-web-assistant.sh` → `UPGRADE_OK`(2026-08-10 12:09 KST), 서비스 3종
`active`, `/healthz`·`/readyz` 200.

**실서버 실환경검증**: `/dashboard`·`/diagnostics`(DS-17 리팩터 소비자) · `/team-docs`
(DS-09 배지 톤 — 실제로 문서 종류별로 다른 색이 렌더되는 것 직접 확인) · `/users` 상세
모달(DS-10 Drawer→Modal 개명) · `/me` 전부 Chrome으로 직접 열어 정상 렌더 + 콘솔 오류
0건 확인. 배포 직후 한 번 스테일 콘솔 오류(옛 번들 해시를 가리키는 동적 import 실패)가
보였으나, 재확인 결과 `read_console_messages` 도구의 버퍼에 남아 있던 배포 이전 기록
이었다(같은 타임스탬프로 반복 출현) — `clear` 후 새로고침하니 깨끗했다. `DS-29`(강조색
반영)는 코드 경로(테마 생성 → `AppShell` sx)를 직접 추적해 확인했고, 실제 강조색을
바꿔 가며 라이브로 대조하지는 않았다(정직하게 남긴다).

---

## 🟣 MEGA CYCLE B — 제품 전역 실패 처리 (Critical `FAIL-01` + FAIL-02/03 + FN-51) 완료 (2026-08-10)

BACKLOG의 마지막 Critical `FAIL-01`("실패를 '없음'으로 표시한다" — `/chat`이 대화 이력이
지워진 것처럼 보이고, `/my-tickets`·`/projects`·`/users` 등이 실패를 빈 상태로 그린다)을
다뤘다. 8화면 각각을 손보는 대신, "왜 이미 잘 짜여 있는 40여 개 화면의 `isError→ErrorState`
규약이 이 상황에서만 발동을 안 하는가"를 먼저 물어 **공통 원인 하나**로 좁혔다.

**근본 원인(1곳)**: `frontend/src/lib/api.js:51-52,77`. `200 OK`인데 본문이 JSON이
아닌 응답(프록시 중간 페이지·SSO 리다이렉트·WAF 차단면 — 전부 실제로 있었던 사고 유형,
`RuntimeError: n8n 응답이 올바른 JSON이 아닙니다` 기존 이력 있음)에서 `r.json()`이 던지는
예외를 `try/catch`로 삼켜 `body=null`을 **정상 반환**했다. `!r.ok` 분기 밖이라 절대 안
던졌다 — 화면 입장에선 "성공했는데 데이터가 없다"와 구별이 안 됐다. **화면 쪽은 대부분
이미 옳았다**(`ErrorState` 컴포넌트가 401/403/404/network를 구분해 재시도 버튼까지 주는
성숙한 공용 컴포넌트이고 ~40개 화면이 이미 정확히 쓰고 있었다) — `api()`가 이 경우에도
반드시 던지게 고치는 것만으로 그 화면 전부가 한 번에 고쳐졌다.

**같은 조사에서 함께 처리한 것**:
- **`FAIL-03`**(`/team-docs` 영원히 로딩) — 다른 화면과 달리 `list`/`filters` 쿼리에만
  `retry:false`가 없어 react-query 기본 재시도(3회, 지수 백오프 ~7초)를 물려받아
  `isError` 전환까지 ~7초 걸렸다. 두 쿼리에 `retry:false` 추가.
- **`FN-51`**(조사 중 발견, 신규) — `/chat`의 새로고침 복원(sessionStorage)이 마운트
  시점 이펙트 순서 경합으로 **성공 경로에서도** 매번 조용히 실패하고 있었다: 저장
  이펙트가 복원 이펙트보다 먼저 실행돼, `cid`가 아직 `null`이라는 이유만으로 저장된
  포인터를 지워 버렸다. 복원 시도가 끝나기 전엔 저장 이펙트가 손대지 않게 하는
  `restoredRef` 가드 추가. FAIL-01 상황(대화 목록 조회 실패)에서는 이 버그가 복원
  포인터까지 함께 날려 "이력이 지워졌다"는 인상을 더 키우고 있었다.
- **`FAIL-04`/`FAIL-05` 재조사 후 정정**(다운그레이드, 코드 변경 없음) — 원 서술을
  검증하려다 둘 다 틀렸음을 확인했다. `FAIL-04`("`/me`가 실패 중에도 정상이라 말한다")는
  `/me`가 SPA 기본 랜딩이라 QA 하네스가 가로채기를 걸기 전에 이미 성공해 캐시된
  하네스 자체의 순서 문제였다 — 캡처된 "정상" 화면은 그 계정의 진짜 데이터였다.
  `FAIL-05`("콘솔 오류 최대 5건")는 앱 코드가 로깅하는 게 아니라 Chromium이 실패한
  HTTP 요청마다 자동으로 남기는 항목이었다(앱 안엔 관련 `console.error` 호출 자체가
  없음, grep 확인) — 건수는 화면이 동시에 쏘는 쿼리 수 × 재시도 횟수와 정확히
  일치했고, `FAIL-03` 수정으로 `team-docs`의 배수 원인은 이미 제거됐다. **자기 발견을
  그대로 안 믿고 재검증해서, 원래 서술이 틀렸으면 심각도를 낮추고 코드를 안 건드린
  사례** — 억지로 "고칠 거리"를 만들지 않았다.

**검증**: 3건(`api.js`/`TeamDocs.jsx`/`useChat.js`) 전부 새 회귀 테스트 + revert-to-verify
(되돌려서 테스트가 실패하는 것을 직접 확인 후 복원) — 이 과정에서 테스트 자체의 결함도
두 번 스스로 잡았다: ① `TeamDocs` 테스트가 처음엔 테스트 하네스의 `QueryClient`가
`retry:false`를 깔아 버려 버그가 있어도 항상 통과했다(운영 `main.jsx`의 실제 기본값으로
맞춰 재작성) ② `useChat` 성공 경로 테스트가 처음엔 복원 대상 id를 우연히 `items[0]`과
같게 둬 버그가 있어도 통과했다(폴백과 구별되게 고정값 순서를 바꿔 재작성). 프런트
vitest 192파일/1280건, 백엔드 pytest 전체 green, `STATIC_CHECKS_OK`, 번들 재빌드.
커밋 `d9dca9c`.

**배포**: `build-bundle.sh` → scp → `bundle.sha256`/`MANIFEST.sha256` 둘 다 일치 확인 →
`upgrade-clovirone-web-assistant.sh` → `UPGRADE_OK`(2026-08-10 10:43 KST), 서비스 3종
`active`, `/healthz`·`/readyz` 200.

**실서버 실환경검증**: 영향받은 5화면(`/my-tickets`·`/chat`·`/projects`·`/users`·
`/team-docs`) 전부 Chrome으로 직접 열어 **정상 경로 무회귀**를 확인함(실 데이터 정상
렌더, 콘솔 오류 0건) — `/chat`은 특히 이전 세션에서 나눈 대화 목록(7/19~8/10)과 마지막
활성 대화가 그대로 복원돼 있는 것까지 직접 확인해 FN-51 수정이 라이브로 동작함을 봤다.
**`200+비JSON` 실패 자체는 운영 서버에 인위적으로 주입하지 않았다**(트래픽 가로채기로
실패를 만드는 것은 이 세션의 원칙상 배제 — 안전하게 재현 불가능한 부류로 분류하고
revert-to-verify된 단위/컴포넌트 테스트로 검증 상한을 삼음, 정직하게 기록).

---

## 🟣 MEGA CYCLE A — AI Assistant / 러너 대화 엔진 (RN-01~14 + Critical AI-30) 완료 (2026-08-10)

D-53 전환 후 첫 MEGA CYCLE. 조사 범위: `runner/claude-work-assistant/assistant.py`의 상태
머신 전체(플랫폼 쪽 `screen_context` 배선 포함). 소단위 티켓 15건을 **공통 원인 5개**로
묶어 한 파일에 한 번에 구현·검증·배포했다(개별 패치 15회 반복 대신).

**5개 공통 원인**:
1. **문맥 상태 TTL 부재** — `mode`/`pending_action`/`pending_question`/`ticket_draft`가
   만료 없이 영속돼, 오래 전에 시작한 CREATE 흐름이 몇 시간 뒤 무관한 메시지를 그 흐름
   안으로 계속 흡수했다(`AI-30` Critical의 근본 원인). `CONTEXT_MODE_TTL_SECONDS`(기본
   24h) 신설 + `drop_stale_in_progress_state()`로 `route_request` 진입 시점에 항상 정리.
2. **부정어 인식이 "하지 마/말"류 어간에만 걸림** — "바꾸지 마"류 흔한 구어체 부정을
   놓쳐 부정 명령이 긍정 명령으로 잘못 라우팅됐다(`RN-02`). `_NEGATION_RE`에
   `[가-힣]{1,8}지\s*마(?!\S)` 패턴 추가(부정 lookahead로 "마감" 등 오탐 방지).
3. **pending 상태가 실패 응답에서도 무조건 지워짐** — `NEED_INPUT`/`FORBIDDEN`/`NO_CHANGE`
   같은 "진행 안 됨" 결과에서도 pending을 지워, 사용자가 다음 턴에 이어가려 하면 문맥이
   이미 사라져 있었다(`RN-05`·`RN-09`·`RN-11` 등 여러 티켓의 공통 증상).
   `_restore_pending_on_stall()`로 6개 pending-clear-then-pivot 호출부 전부 감쌈.
4. **conversation_lock이 전체 잠금 해제** — 한 대화의 lock 해제가 `.clear()`로 **다른 모든
   대화**의 lock까지 지워 동시성 경합 창을 만들었다(`RN-07`). 해당 키만 선택적으로 해제.
5. **화면 문맥(screen_context)이 어디에도 전달 안 됨** — 사용자가 "지금 보고 있는 화면"을
   AI가 알 방법이 없어 매번 다시 설명해야 했다(`AI-30` Med). 프런트(`useChat.js` →
   `AssistantDrawer.jsx`) → `POST /api/assistant/message`(`chat/router.py`·`service.py`) →
   잡 페이로드(`jobs/handlers/chat_message.py`) → 러너 `QUERY_PROMPT`까지 전 구간 배선.
   **알려진 한계**: n8n 워크플로가 이 필드를 최종 전달하는 홉은 저장소 밖(n8n 쪽 워크플로
   변경 필요) — 플랫폼 레이어까지는 라이브로 끝까지 확인됨, 마지막 홉만 미완.

**RN-08은 의도적으로 미수정**: n8n 쪽 쓰기-결과 보고가 없어 이 코드베이스만으로는 안전하게
고칠 수 없음(억지로 고치면 기존 교착 회피 로직이 회귀). `docs/BACKLOG.md`에 그대로 기록.

**검증**: 신규 회귀 테스트 16건(`test_mega_cycle_ai_assistant.py`) 전부 revert-to-verify로
작성 — 되돌려서 실패 확인 → 복원 → 통과 재확인. 기존 러너 테스트 263건 + 신규 16건 +
플랫폼 백엔드 전체 + 프런트 vitest 전체(1272건) 전부 green. 커밋 `5db9fbf`.

**배포**: 러너(별도 파이프라인, `dist/deploy-runner.sh`)와 플랫폼(`build-bundle.sh` →
`upgrade-...sh`) **둘 다** 배포 — MD5/체크섬 일치, 서비스 fresh-restart 타임스탬프,
`/healthz`·`/readyz` 확인.

**실서버 검증 — 정직한 구분**:
- **규칙 기반 라우팅 경로(티켓 조회/상태변경/목록 등)** — Chrome으로 직접 조작해 **라이브로
  정상 동작 확인함**. 이 경로들은 LLM 을 거치지 않아 아래 CLI 이슈와 무관.
- **`screen_context` 플랫폼 배선** — 브라우저 Network 탭에서 실제 요청 페이로드에
  `screen_context` 필드가 채워져 나가는 것 확인(라이브). n8n → 러너 마지막 홉은 저장소
  범위 밖이라 미확인.
- **TTL/부정어/lock/pending-restore 같은 코드 수정 자체의 정확한 트리거 시나리오** —
  백엔드 유닛/통합 테스트로는 확실히 증명됐고 배포도 healthy 하지만, 실제 프로덕션 Notion
  데이터로 그 정확한 트리거(예: 24시간 지난 뒤 재개, 동시 두 대화의 lock 경합)를 독립적으로
  재현하지는 않았다 — 이 세션의 검증 원칙(안전하게 재현 불가능한 것은 로컬 테스트 상한으로
  정직하게 남긴다)에 따름.
- **LLM 의존 자유 대화 경로(`claude_query`/`claude_draft`)** — **검증 중 발견한 별개
  인프라 문제로 막힘**: 실서버 `n8n` 계정의 Claude CLI 가 로그인 상태가 아니다(`"Not
  logged in · Please run /login"`). 내 코드를 거치지 않고 SSH로 직접 재현 확인, 시간대·
  자격증명 파일 터치 패턴 분석으로 **이번 배포가 원인일 가능성은 낮고 자연 세션 만료 쪽이
  더 유력**하다고 판단(100% 확정은 불가 — 자격증명 내용은 보안 불변규칙상 열람 안 함).
  **`OPS-06`으로 BACKLOG에 기록.** 규칙 기반 경로에는 영향 없음.
  **→ 2026-08-10 11:00 KST 해결.** 사용자가 `sudo -iu n8n` → `claude` → `/login` 으로 재인증,
  러너와 동일 조건 실호출로 `result:"PROBE_OK"` + 실제 토큰 소모(`output_tokens:9`) 확인.
  원인은 `.credentials.json` 의 `expiresAt` 이 `0` 으로 초기화된 상태 — refresh 토큰 거부.
  **위에서 「배포가 원인일 가능성은 낮다」고 한 판단이 재로그인만으로 해결된 것으로 뒷받침됐다.**
  서비스 재시작 불필요(러너가 요청마다 `claude` 를 새로 띄움). ⚠️ 웹 AI 도우미 대화 E2E 는 미검증.

---

## 🔵 Sonnet 구현 사이클 4, 배치 6 — Notion 다운 시 502 캐스케이드 + M4 두 건 더 + 휴지통 필터 불일치 (2026-08-10)

**UA-05**: `weekly_digest_facts`가 `my_state["configured"]`만 보고 팀/기여자 집계용
**별개의** Notion 조회(`list_period_tickets`)를 새로 시도했다 — 이미 `ok=False`(Notion
장애)로 알고 있는 상태에서도. 실패하면 그 예외가 안 잡혀 엔드포인트 전체가 502가 되고
Notion과 무관한 문서·게시판 집계까지 함께 사라졌다. `configured and ok`를 보고, 두 번째
조회 자체의 새 실패도 잡아 `team=None`으로 부드럽게 접도록 고침.

**UA-07·UA-08**: 이 저장소가 이미 "M4"라고 이름 붙인 함정(`home/service.py::local_today`
docstring)의 재발 두 건. 스프린트 요약 기본 창(`sprints/router.py`)과 월간 리포트 기본
기간·`today`(`reports/router.py`)가 각각 UTC 시계로 계산되고 있었다 — KST 월요일/월초
00:00~09:00 사이엔 UTC 날짜가 아직 어제/지난달이라 기본값이 하루~한 달 밀렸다. 둘 다
`home_service.local_today(settings, now)`로 교체.

**UA-09**: `home/readers.py`의 형제 함수 `recent_documents`(휴지통 제외, 이미 고쳐짐)와
`documents_changed_between`(휴지통 미제외, 안 고쳐짐)이 갈라져 있었다 — 후자에 같은
제외 조건 추가.

**의도적으로 보류(다음 배치)**: UA-04(프런트 "재시도" 버튼이 백엔드 `/retry` 대신 옛
우회를 씀), UA-06(홈 집계 중복 호출 — React Query staleTime 조정), UA-10(휴지통
페이지네이션) — 셋 다 프런트(React) 변경 + vitest + 번들 재빌드가 필요해 이번 배치(백엔드
전용)와 범위가 다르다. 특히 UA-10은 백엔드만 반쪽으로 고치면(무언 절삭 또는 프런트가 안
쓰는 파라미터 추가) 오히려 "미완성 구현"이 되므로 일부러 손 안 댔다 — 이유는 BACKLOG.md에
개별 기록.

**검증 방법론**: 4건 전부 revert-to-verify. **로컬 게이트**: 백엔드 pytest 전체 green,
`STATIC_CHECKS_OK`. 커밋 `40073c1` → 배포 `UPGRADE_OK`(2026-08-10 07:53), 서비스 3종
`active`, `/healthz`·`/readyz` 200.

**실서버 검증**: 넷 다 특정 시각(KST 경계)이나 특정 상태(Notion 장애, 휴지통 문서 존재)
에서만 재현되는 종류라, 지금(2026-08-10, 마침 월요일이라 정상 케이스와 버그 케이스가
같은 답을 낸다) 시점엔 버그 자체를 실서버에서 재현할 방법이 없다. 대신 세 엔드포인트를
실제 로그인 세션으로 직접 호출해 **정상 경로에 회귀가 없음**을 확인함: `/api/sprint/
summary` → 오늘(월요일) 기준 정상 창(`2026-08-10~2026-08-17`), `/api/admin/reports/
dev-monthly` → 정상 기간(`2026-08`), `/api/assistant/weekly-digest` → 200 정상 응답.
UA-09는 실제 고객 문서를 휴지통에 넣는 부작용을 감수할 이유가 없어 로컬 테스트로만 검증.

---

## 🔵 Sonnet 구현 사이클 4, 배치 5 — CORE-12 잔여 4건 + Notion 호출부 회귀 자체 발견·수정 (2026-08-10)

**CORE-12(마무리)**: 배치 4에서 미룬 4개 소항목을 전부 고쳤다.
- `ratelimit._buckets`가 상한·청소 없이 무한 증가 → dict 삽입 순서를 LRU로 재사용,
  1만 건 넘으면 가장 오래 안 쓴 키부터 제거.
- `_is_safe_request_id`가 `str.isalnum()`(유니코드 인식)이라 한글 등도 통과시켜 응답 헤더
  조립 단계에서 `UnicodeEncodeError`로 죽을 수 있었다(`try/except`가 감싸는 범위 밖) →
  ASCII 영숫자·하이픈만 허용.
- `audit.mask_sensitive`가 `secret_ref`/`secret_reference` **이름**까지 `***`로 가려,
  같은 변경이 `config_versions`엔 이름으로 남는데 감사 로그엔 "***→***"로만 남아 변경
  여부조차 못 읽었다 → 이 두 필드명만 정확히 예외 처리.
- `SecretMissingError`가 ref 이름을 예외 메시지에 실어 그대로 HTTP 응답 본문에 노출됐다
  (이 예외를 일으키는 `OutboundClient` 경로는 관리자 전용이 아니다) → 기본 메시지로 바꾸고
  이름은 서버 로그(`logger.warning`)로만.

**부수 발견(자체 검증 루프가 잡음)**: `SecretMissingError` 메시지에서 이름을 뺀 순간,
Notion 호출부 4곳(`app/reports/notion_source.py`, `app/team_docs/notion_docs.py` ×2,
`app/tickets/notion_write.py`, `app/notion_console/probe_notion.py`)이 전부 "토큰 미설정"
판별을 `그_이름 in str(exc)` 문자열 매칭으로 하고 있었다 — 이름이 메시지에서 빠지자 전부
"설정 안 됨"을 "조회 실패"로 오판하게 됐다. 전체 pytest 1차 실행에서 10건 실패로 잡혔고,
`except SecretMissingError`(타입 기반)로 교체 + 테스트 커버리지가 없던 두 곳
(`notion_docs.py`, `notion_write.py`)에 회귀 테스트를 새로 추가해 고쳤다. **이 문자열
매칭 자체가 CORE-12가 지적한 것과 같은 종류의 설계 취약점이었다** — 고치는 김에 근본
원인까지 없앴다.

**검증 방법론**: 4건 전부(+ Notion 호출부 회귀 2건) revert-to-verify: 고치기 전 코드로
되돌려 새 테스트가 실패하는 것을 직접 확인 → 복원 → 통과 재확인.

**로컬 게이트**: 백엔드 pytest 전체 green(1차 실행에서 위 회귀로 10건 실패 → 원인 수정 →
재실행 green), `STATIC_CHECKS_OK`. 커밋 `6e300b3` → 배포 `UPGRADE_OK`(2026-08-10 07:06),
서비스 3종(`clovirone-web-assistant`·`clovirone-web-worker`·`clovirone-privhelper`) 전부
`active`, `/healthz`·`/readyz` 200.

**실서버 검증**: request-id 건은 **직접 확인함** — `curl -H "X-Request-ID: 한글한글테스트"
https://clovirone-ai.gooddi.lab/healthz` → `200 OK` + 응답 헤더 `x-request-id`가 생성된
uuid(`ab4c5982acd6051c38e42df217a8ce17`)로 교체됨(크래시도 반사도 없음). 나머지 세 건은
정직하게 미검증으로 남긴다 — ratelimit 버킷 상한은 순수 파이썬 객체 상태라 HTTP로 관측
불가, 감사 마스킹은 같은 이유로 관측하려면 실제 secret_ref 변경 감사 로그를 읽어야 하는데
그러려면 테스트용 Integration을 만들어야 하고 **Integration Registry엔 삭제 API가 없어**
영구 클러터가 남는다(이번엔 만들지 않기로 결정), SecretMissingError 노출 건도 같은 이유로
막힘. 상세 표는 [docs/PROGRESS_STATUS.md](PROGRESS_STATUS.md) §6.

**신규 상시 문서**: `docs/PROGRESS_STATUS.md` 신설 — 사용자가 "기억·문서 완료 표시를
맹신하지 말고, Master Plan·BACKLOG·QA_COVERAGE·실소스·배포상태·Chrome 검증을 계속
대조하라"고 명시적으로 지시했다. 이 문서가 그 대조 결과의 단일 Snapshot이다(여러 개 안
만듦). **핵심 발견**: BACKLOG 전체 약 522건 중 이번 세션이 손댄 건 약 39건(약 7%),
QA_COVERAGE 7축 체계적 검증은 73라우트 중 F/D/C축이 사실상 전부 0 — Cycle 4가 CORE/UA/UB만
파고드는 동안 Master Plan §3이 명시한 원래 순서(디자인 시스템 → AI 도우미 → 관리자 IA →
기능/권한 E2E)에서 1~3단계를 건너뛰었다는 것도 기록해 뒀다(§5-1, 아직 결정 안 됨 — 되돌릴지
이대로 계속할지).

---

## 🔵 Sonnet 구현 사이클 4, 배치 4 — page-auth 임퍼소네이션 누락·기능 플래그 타입 강제·설정 캐시 참조 공유·기동 실패 침묵 (2026-08-10)

**CORE-08**: `get_page_auth`가 `get_current_auth`와 같은 `_load_auth` 처리를 중복
구현하면서 임퍼소네이션 쓰기 차단과 `request.state.actor` 배선을 빠뜨렸다 —
`get_current_auth`의 docstring이 정확히 이런 재발을 막으려고 가드를 한 곳에 뒀다고
설명하는데, 이 함수가 그 가드 밖이었다. 지금은 이 의존성을 쓰는 라우트가 전부 GET이라
무해하지만, 이 의존성 자체는 테스트가 0건이었다 — 일반 GET 케이스, 쓰기 차단 케이스,
`request.state.actor` 배선 케이스를 새로 추가.

**CORE-10**: `feature_flags._parse`가 JSON 값을 타입 검사 없이 그대로 담아
`"game_ai_enabled": "false"`(따옴표 붙은 문자열)가 파이썬에서 참이 돼 파일엔 꺼져
있는데 기능이 켜졌다 — 이 모듈의 존재 이유("설정했는데 아무 일도 안 일어난다"를
없애는 것)의 반대 방향 실패. 진짜 JSON boolean만 받아들이고 그 외는 조용히 기본값으로.

**CORE-12(부분)**: `SettingsCache.current()`가 내부 dict를 참조로 돌려줘 부르는 쪽이
고치면 DB 왕복도 `invalidate()`도 없이 캐시 자체가 오염됐다 — `feature_flags`가 같은
이유로 이미 사본을 주는 것과 같은 계약으로 맞춤. `create_app`의 설정 캐시 초기 로드
실패가 `except: pass`로 모든 예외를 구별 없이 삼켜, DB 잠금·손상 같은 진짜 장애에도
로그 한 줄 없이 기본값으로 조용히 기동했다 — 경고 로그 추가(기동은 계속 막지 않음).
CORE-12의 나머지 소항목(ratelimit 버킷 무한 증가, request-id 유니코드 반사, 감사
마스킹 불일치, SecretMissingError 이름 노출)은 이번 배치에서 다루지 않음 — 다음 배치로
미룸.

**검증 방법론**: 4건 전부 회귀 테스트를 새로 추가했고, 고치기 전 코드로 일부러 되돌려
전부 실패하는 것을 직접 확인한 뒤 복원했다. **static_checks가 실제로 잡은 것**: 처음
쓴 CORE-12 경고 로그 문구에 이 저장소가 금지한 glyph(em dash —)가 들어가
`USER_TEXT_FAILED`로 걸렸다 — 배포 전에 고쳤다.

**로컬 게이트**: 백엔드 pytest 전체 green, `STATIC_CHECKS_OK`(프런트 변경 없음). 커밋
`bc650d7` 배포 → `UPGRADE_OK`, 서비스 3종 active, `/healthz`·`/readyz` 정상.

**실서버 검증**: 이 배치의 네 항목은 전부 실서버에서 안전하게 재현할 방법이 없다 —
CORE-08은 이 의존성을 쓰는 실제 POST 페이지 라우트가 아직 하나도 없고(그래서 Low(잠복)),
CORE-10은 재현하려면 운영 `feature-flags.json`을 손으로 망가뜨려야 하며, CORE-12
두 건은 각각 파이썬 객체 참조(HTTP로 관측 불가)와 DB 잠금·손상 주입(운영 위험)이 필요하다.
대신 배포 후 `/api/admin/feature-flags` 목록과 `/admin` 콘솔 셸이 둘 다 200으로 정상
로드되는 것만 확인해 **회귀가 없음**을 확인했다 — 버그 자체의 재현은 로컬 테스트로만
검증됨(정직하게 남긴다).

---

## 🔵 Sonnet 구현 사이클 4, 배치 3 — Retry-After NaN·임퍼소네이션 시간제한 우회·공지 링크 정규화·프롬프트 발행 경합 (2026-08-10)

**CORE-07**: `float("nan")`은 `ValueError`를 안 던지고 NaN과의 비교는 IEEE 754상 전부
`False`라 `Retry-After: nan` 헤더가 두 범위 검사를 그대로 통과해 `time.sleep(nan)`이
단일 아웃바운드 관문 전체를 죽였다. `math.isnan()` 검사 추가(`inf`는 이미 정상 처리되던
것을 회귀 테스트로 함께 고정).

**CORE-09**: 임퍼소네이션 최대 지속 시간(30분) 검사가 `record.impersonation_id`가
비어 있으면(`imp_service.end()`가 이미 폴백을 두는 바로 그 불일치) 통째로 건너뛰어졌다
— `_impersonated_auth`도 같은 `active_for_session()` 폴백을 쓰게 고침. 이 검사 자체가
지금까지 테스트 0건이었다(일반 케이스·이 폴백 케이스 둘 다 새로 추가).

**CORE-11**: `is_safe_external_url`의 제어문자 제거와 `normalize_external_url`의 정리가
서로 다른(그리고 서로 벌어질 수 있는) 구현이었고, `announcements`는 검증에 쓴 정규화된
값이 아니라 **원문**을 저장했다 — 검증한 형태와 저장한 형태가 갈라지는 구조였다(오늘은
무해해도 스킴 검사가 정교해질 다음번의 발판). 하나의 `_clean()`으로 통일하고 저장 경로도
정규화된 값을 쓰게 고침. `link_url=""`이 "링크 없음"이 아니라 422가 되던 것도 함께 고침.

**UB-05**: PATCH가 `link_url`을 안 건드려도 기존 저장값을 재검증해서, safe_url 가드
이전에 저장된 legacy 위험 값이 있는 배너는 **끄기(`{"active": false}`)조차** 422로
막혔다 — "한 번에 끄기"가 존재하는 이유를 무력화. `link_url` 자체를 바꾸려는 요청만
검증하게 좁힘.

**UB-04**: 발행(publish) 전환이 "기존 발행본 조회 → 이전 것 archived → 이 행 published"를
잠금·제약 없이 했다 — 두 관리자가 같은 이름의 다른 버전을 거의 동시에 발행하면 같은
이름에 published가 둘 생기고, 그 뒤 그 이름의 모든 조회가 `MultipleResultsFound` → 500이
됐다. **새 마이그레이션 0053**이 `prompts`·`policies`에 부분 유일 인덱스
(`name` WHERE `status='published'`)를 추가(배포 전 기존 중복은 최신 것만 남기고 자동
정리, approvals의 0052와 같은 패턴). `transition()`이 그 `IntegrityError`를 깨끗한
409로 변환. **구현 중 자체 발견**: 옛 발행본을 archived로 내리는 것과 새 행을 published로
올리는 것을 **같은 flush**에 섞으면, 문장이 나가는 순서에 따라 찰나에 "같은 이름에
published가 둘"인 상태가 생겨 **우리 자신의 정상 발행 경로**가 그 인덱스에 걸릴 수
있었다(기존 테스트 `test_publish_archives_previous_published`가 실제로 이렇게 깨짐 →
재현·원인 확정 후 두 UPDATE를 분리된 flush로 나눠 고침).

**검증 방법론**: 5건 전부 회귀 테스트를 새로 추가했고, 고치기 전 코드로 일부러 되돌려
전부 실패하는 것을 직접 확인한 뒤 복원했다(UB-04는 "고치는 과정에서 기존 테스트가 깨진 것"
자체도 정직하게 기록 — 처음 짠 수정이 완전하지 않았다는 증거이자, 전체 테스트를 돌려야만
잡히는 종류의 결함이었다).

**로컬 게이트**: 백엔드 pytest 전체 green(exit 0), `STATIC_CHECKS_OK`(프런트 변경 없음).
마이그레이션 downgrade/upgrade 왕복도 로컬에서 확인. 커밋 `11949e9` 배포 → `UPGRADE_OK`,
서비스 3종 active, `/healthz`·`/readyz` 정상. **실서버에서 마이그레이션 0053이 실제로
적용된 것을 `sqlite3`로 직접 확인**(`alembic_version=0053`, `ux_prompts_published_dedup`·
`ux_policies_published_dedup` 인덱스 둘 다 존재).

**실서버 실환경검증**: CORE-11만 안전하게 실시 — `POST /api/admin/announcements`에
`link_url=""`을 보내 **422가 아니라 201로 성공하고 `link_url`이 `null`로 저장되는 것**을
실측 확인(테스트 공지는 확인 후 삭제해 정리함). 제어문자 접두 케이스는 셸 도구가 제어문자를
명령어에 못 넣게 막아 실서버에서 직접 만들지 못했다 — 로컬 테스트로만 검증. 나머지 네
항목(CORE-07·09, UB-04·05)은 각각 실제 Notion 429 응답의 NaN 헤더, 임퍼소네이션 포인터
불일치의 자연 발생, 진짜 동시 요청, legacy 위험 링크 행을 실서버에 인위적으로 만들어야
재현되는 종류라 시도하지 않음 — 로컬 테스트로만 검증(정직하게 남긴다).

---

## 🔵 Sonnet 구현 사이클 4, 배치 2 — 세션 폐기 영속화·500 헤더/로그·allowlist 포트/캐시 (2026-08-10)

`app/core/` 인프라 계층에서 4건(CORE-02·04·05·06) — 14라운드 감사가 다른 모듈 수정의
부수효과로만 닿았을 뿐 한 번도 정면으로 조사하지 않은 층이다.

**CORE-02**: `sessions.py::validate()`가 만료·유휴초과 세션의 `revoked_at`을 메모리에서만
바꾸고 `None`을 돌려줬는데, 그 `None`이 `UnauthorizedError`로 이어져 `get_db`의 예외 처리가
그 쓰기까지 롤백했다 — 만료된 세션이 `profiles` 화면에 영원히 "활성"으로 남았다. 두 분기
모두에 `db.commit()` 추가. 게다가 `retention.py`가 세션 표를 정리 대상에 **아예** 안 넣어
(revoked_at이 제대로 저장되기 시작해도) 표가 무한히 자라는 문제가 별도로 있어
`purge_old_sessions()`를 신설해 `run_retention`에 배선(살아 있는 세션은 나이와 무관하게
절대 안 지운다 — 60일 지난 **폐기된** 세션만).

**CORE-04**: `@app.exception_handler(Exception)`은 Starlette `ServerErrorMiddleware`(모든
`add_middleware` 레이어 **바깥**)에 설치된다 — 그래서 예외가 라우터를 빠져나가면
`RequestContextMiddleware`의 `call_next` 이후 코드(보안 헤더 부착, 접근 로그)가 아예 안
돈다. `_unhandled` 핸들러의 로직을 `errors.py::unhandled_error_response()`로 뽑아 공용화하고,
`RequestContextMiddleware.dispatch`가 `call_next`를 try/except로 감싸 예외를 직접 잡아 같은
함수로 응답을 만든 뒤 평소 응답과 똑같이 헤더·로그 처리를 받게 했다.

**CORE-05**: `urlsplit(...).port`는 파싱이 아니라 **접근 시점**에 포트 범위(0~65535)를
검사해 `ValueError`를 던진다 — 저장 시점 URL 검증이 없는 `base_url`/`health_url`/
`webhook_url`에 잘못된 포트가 들어가면 매 헬스체크마다 문서화된 400(`URLNotAllowedError`)
대신 불투명한 500이었다. `try/except ValueError`로 감쌈.

**CORE-06**: allowlist 캐시 키가 `st_mtime`(초 단위) 하나뿐이라, 타임스탬프를 보존하는
복원(`cp -p`·`rsync -a`·tar·installer)이 예전 mtime을 그대로 들고 오면 프로세스 수명 내내
그 시점의(더 넓을 수 있는) 옛 허용목록을 계속 쓴다. 같은 문제를 이미 풀어 둔
`feature_flags._stat_key`와 같은 `(mtime_ns, size)` 키로 교체.

**검증 방법론**: 4건 전부 회귀 테스트를 새로 추가했고, 고치기 전 코드로 일부러 되돌려
전부 실패하는 것을 직접 확인한 뒤 복원했다.

**로컬 게이트**: 백엔드 pytest 전체 green(exit 0), `STATIC_CHECKS_OK`(프런트 변경 없음,
번들 재빌드 불필요). 커밋 `07e532f` 배포 → `UPGRADE_OK`, 서비스 3종 active, `/healthz`·
`/readyz` 정상.

**실서버 실환경검증 — 이번엔 의도적으로 시도하지 않음(정직하게 남긴다)**: 이 배치의 네
항목은 전부 "실서버에서 안전하게 재현하려면 득보다 실이 큰" 종류다 — CORE-02는 실제 유휴
타임아웃(설정값 분 단위)을 실시간으로 기다려야 하고, CORE-04는 운영 서버에서 **일부러
처리되지 않은 예외를 유발**해야 하며, CORE-05/06은 실제 러너·워크플로 allowlist 설정을
망가뜨리거나 서버 파일 타임스탬프를 조작해야 재현된다. 넷 다 사이클 3·4-배치1에서 이미
"고치기 전 코드로 되돌려 실패를 직접 본" 회귀 테스트로 확실히 증명했으므로, 그 확인을
실서버에서 반복하는 대신 배포·서비스 정상 여부만 확인하는 쪽을 택했다.

---

## 0. 한 줄 요약

## 🔵 Sonnet 구현 사이클 4, 배치 1 — RBAC 스코프 가드·쿼터 표시·임퍼소네이션 로그아웃·워커 락·백업 락 (2026-08-10)

사이클 3(11단계) 완료 후 `docs/BACKLOG.md`(529항목)를 다시 훑어 다음 배치를 골랐다 — Opus의
6라운드 전수조사 이후 처음으로 **BACKLOG 자체를 근거로** 고른 사이클이다(SONNET_HANDOFF.md의
11단계 목록이 아니라). 남은 Critical 2건(`AI-30`·`FAIL-01`)은 러너 별도 서브프로젝트·5화면
이상 걸친 교차 패턴이라 각각 전용 사이클로 미루고, 이번엔 **"이미 있는 가드를 새 자리에
안 걸었다"** 류의 High 8건 + 인프라 2건을 같은 뿌리로 묶어 처리했다.

**UA-01·UA-02(전사 데이터 유출, 실서버에서 이미 재현됐던 건)**: `weekly_digest_facts`가
`visible_user_ids`를 안 넘겨 주간 다이제스트 팀 합계·상위 기여자가 항상 전사였다.
`sprints/service.py::_visible_ids`·`tickets/service.py::drop_out_of_scope_dtos`는
`scope.is_dept`일 때만 걸러 org 범위 뷰어는 그대로 무제한이었다(`visible_user_ids` 자신이
이미 전역일 때만 `None`을 주므로 그 판정 하나면 충분한데 불필요하게 좁게 조건을 걸었던 것).
셋 다 고침.

**SEC-01(Notion 신원 결속 권한 상승)**: `notion_mapping` 쓰기 4종에 `ensure_can_manage_target`
누락 — `users/router.py`의 형제 엔드포인트와 같은 패턴으로 추가.

**UB-01(공지 스코프 가드 전무)**: 공지는 부서별로 좁혀 보여줄 방법이 없어(`audience`가
all/admin 둘뿐) 쓰기 전부를 전역 범위로 한정(`quotas`의 `_ensure_may_touch_global`과 같은 판단).

**UB-02(쿼터 화면 표시-집행 불일치)**: 전역 쿼터 집행은 항상 사용자별인데 목록은 전 사용자
합계를 보여줘 존재하지 않는 "상한 도달"을 알렸다. `max_user_used()`(최다 사용자 1인의 값)로 교체.

**UB-03(로그아웃이 임퍼소네이션을 안 끝냄)**: `/logout`이 세션은 폐기하면서
`ImpersonationSession.ended_at`은 영원히 NULL로 남겼다 — 세션 폐기 전에 `imp_service.end(...,
reason="logout")` + 감사 기록을 추가.

**CORE-01·CORE-03(워커 락 경쟁)**: 새 리스 생성 경로가 만료-리스-인수 경로와 달리
`verify_ownership()` 없이 성공을 반환했다(두 프로세스가 동시에 자신이 주인이라 믿을 수 있음).
`_write()`도 `Path.write_text`(truncate-then-write)라 `renew()` 도중 다른 프로세스가 빈 파일을
볼 수 있었다. 생성 경로를 인수 경로와 같은 "쓰고 verify" 구조로 통일하고, `_write()`를
`secret_refs.write()`와 같은 `mkstemp`+`os.replace` 원자적 패턴으로 교체.

**UA-03(백업이 앱 전체 쓰기를 막음)**: `run_backup`이 "running" 행을 만든 `db.flush()` 직후
커밋 없이 전체 DB 복사+임시 복원+무결성 검사 2벌을 수행해 그동안 SQLite 쓰기 락을 계속
쥐고 있었다 — `trash/service.py::purge_expired`(S7)가 이미 겪고 고친 것과 같은 실패 양식.
행 생성 직후 커밋해 락을 놓고, 느린 구간 뒤 짧은 마무리 쓰기로 상태를 확정.

**검증 방법론에 대한 정직한 기록**: 9건 전부 회귀 테스트를 새로 추가했고, **그 테스트가 실제로
버그를 잡는지 고치기 전 코드로 일부러 되돌려 실패를 직접 확인한 뒤 복원**했다(D-54와 같은
정신 — 자기 자신의 "테스트 통과"도 액면 그대로 안 믿는다). 배포 후 실서버에서도 검증을
시도했는데, 그 과정에서 **두 항목의 테스트 설계 결함을 스스로 발견**했다: UA-01/UA-02는
이 서버가 조직 1개·부서 2개(부모-자식이라 사실상 전 직원이 한 트리)뿐이라 "범위 밖 사람이
안 보인다"를 보여줄 고립된 집단이 없었고, SEC-01은 대상(system_admin, 부서 없음)이 애초에
**기존** 범위 검사에서 먼저 404로 막혀 이번에 추가한 새 검사를 전혀 통과시키지 못했다 —
둘 다 "200/404가 나왔다"를 검증 성공으로 착각할 뻔한 자리였다. 상세는 아래 및
`docs/BACKLOG.md`의 각 항목 상태 칸.

**로컬 게이트**: 백엔드 pytest 전체 green(exit 0), 프런트 vitest 189파일/1272건 green,
`STATIC_CHECKS_OK`. 커밋 `aa5e346` 배포 → `UPGRADE_OK`, 서비스 3종(web·worker·privhelper)
전부 active, `/healthz`·`/readyz` 정상.

**실서버 검증(system_admin 계정 + curl, 임시 부서범위 admin 계정 하나를 만들어 검증 후
바로 보관 처리)**:
- **UB-01(실환경검증완료)** — 임시 부서범위 admin으로 `POST /api/admin/announcements` 호출
  → **`403 forbidden`, "공지는 전체 범위 관리자만 만들고 바꿀 수 있습니다."** 실측 확인.
- **UB-03(실환경검증완료)** — system_admin이 QA 테스트 계정(`qa-user`)을 대리 보기 시작 →
  `/logout` → `GET /api/admin/impersonation/sessions`로 그 세션을 다시 조회 →
  **`ended_at`이 실제로 채워지고 `ended_reason: "logout"`, `active: false`** 확인.
- **UA-03(부분)** — "지금 백업"을 실제로 실행 → `201`, `status: "verified"` 정상 확인(기능
  자체 회귀 없음). 이 서버 DB가 작아(6MB) 백업이 0.19초 만에 끝나 "그 사이 다른 쓰기가
  막히는지"는 수동 타이밍으로 관찰 불가 — 락 미보유 자체는 로컬의 인위적 지연 테스트로만
  확실히 증명됨.
- **UA-01·UA-02·SEC-01·UB-02·CORE-01·CORE-03 — 실서버에서 시도했지만 결론에 이르지 못함
  (정직하게 미검증으로 남긴다)**:
  - UA-01/UA-02: 임시 부서범위 admin으로 weekly-digest·sprint-summary 호출 → 200 정상
    응답은 받았으나, 이 서버의 부모-자식 부서 구조상 "범위 밖이라 안 보이는 사람"이 존재하지
    않아 필터가 실제로 작동하는지와 애초에 안 걸렸을 때의 차이를 구별할 수 없었다.
  - SEC-01: 대상(system_admin)이 부서가 없어 **기존**(이번에 안 바꾼) 범위 검사에서 먼저
    404가 나 이번에 추가한 `ensure_can_manage_target`을 애초에 통과시키지 못했다.
  - UB-02: `/api/admin/ai-quotas` 목록이 200으로 정상 응답(회귀 없음)하는 것만 확인 — 이
    서버엔 전역 쿼터 행 자체가 설정돼 있지 않아 표시값 변화를 볼 표본이 없었다.
  - CORE-01/CORE-03: 워커 프로세스를 실제로 둘 띄워 경쟁을 재현하는 것은 운영 워커에
    위험해 시도하지 않음 — 의도적으로 로컬 테스트로만 검증.
  이 다섯/여섯 항목은 `docs/BACKLOG.md`에도 "로컬 테스트로만 확실히 검증됨"이라고 같은
  수위로 적어 뒀다 — 표에는 "구현완료"로만 표시하고 "실환경검증완료"라고 과장하지 않았다.

---

## 🔵 Sonnet 구현 사이클 3, 9·10단계 — 배포·실환경검증 완료 (2026-08-10)

`SONNET_HANDOFF.md §3` 9단계(게시판·채팅 규약 통일, 7항목)·10단계(채팅 텍스트 파서
공용화, 3항목) 전부 구현 완료. 전체 백엔드 pytest green(1건 실패 발견·수정 후 재확인 —
`test_a_moderator_in_another_department_can_still_moderate`가 **예전(운영자가 남의 글
수정 가능) 동작을 정답으로 못박아 둔 테스트**였다, 아래 9-1과 같은 이유로 의도적으로
바꾼 동작이라 테스트를 새 계약에 맞춰 고쳤다), 프런트 vitest 189파일/1272건 green,
`STATIC_CHECKS_OK`, 번들 재빌드 완료. 커밋 `a756f41` 배포 → `UPGRADE_OK`,
`systemctl is-active` 3종(web·worker·privhelper) 전부 active, `/healthz`·`/readyz` 정상
확인 후 Chrome으로 실서버(hshwang@goodmit.co.kr, system_admin)를 직접 열어 아래
항목을 확인했다.

**Chrome 실환경 검증**:
- **9-1·9-4(게시판 수정 흔적·툼스톤)** — 테스트 게시글에 댓글을 달고 수정 → 타임스탬프
  옆에 "(수정됨)"이 실제로 뜨는 것 확인. 그 댓글을 삭제 → "황형섭, 삭제된 댓글입니다"
  툼스톤으로 렌더(사라지지 않음) 확인. 게시글 삭제 → "게시글을 삭제했습니다" 토스트,
  목록이 원래 상태(기존 글 1건)로 복원 — 테스트 데이터 정리 완료.
- **9-3(전체 채팅 자기멘션 강조)** — 전체 채팅에 "@황형섭 자기멘션 테스트" 전송 →
  브라우저 콘솔에서 DOM을 직접 조회해 `@황형섭`이 평범한 텍스트가 아니라
  `<span class="MuiBox-root ...">`(멘션 칩 컴포넌트)로 렌더된 것을 확인 —
  `you.display_name` 배선이 실제로 렌더 경로를 타는 것까지 증명됨. 메시지는 삭제해
  정리(툼스톤 "황형섭님이 메시지를 삭제했습니다"로 뒤바뀐 것도 함께 확인).
- **9-6(방 이름 저장이 초대 대상을 날리는 버그)** — 새 그룹 채팅방을 만들고 관리 모달에서
  "QA 감사자"를 체크 → 방 이름을 바꿔 저장("방 이름을 바꿨습니다" 토스트, 헤더 제목도
  갱신) → **체크박스가 여전히 선택된 채로 남고 "1명 초대" 버튼도 그대로 있는 것**을
  라이브로 확인 — 고치기 전이었다면 이 저장 시점에 선택이 날아갔을 자리. 방은 파하기로
  정리.
- **채팅방·놀이 화면 무결성** — `/chat-rooms`(전체 채팅 + 1:1 목록), `/games`(방 생성 →
  명단에 "황형섭(나)/방장" 정상 렌더 → 방 파하기) 양쪽 다 `read_console_messages`로
  콘솔 오류 0건 확인 — 9-2·9-5·9-7·10-1·10-2·10-3이 공통으로 건드린
  `ChatPane.jsx`/`ChatRoom.jsx`/`ChatRoomMembers.jsx`/`RichText.jsx`/`links.jsx`/
  `MembersList.jsx`에서 런타임 에러 없이 정상 마운트됨을 보여준다.

**아직 실서버에서 안 본 것(정직하게 남긴다)**:
- **9-5(나가기 확인 문구 분기)** — `leaveRoomConfirmMessage()`는 브라우저 네이티브
  `window.confirm()`을 그대로 쓴다. 자동화로 누르면 탭이 그 순간 완전히 멈춰(대화상자가
  후속 명령을 모두 막음) 복구가 어려워 **의도적으로 클릭하지 않았다** — 순수 함수 자체와
  방장 클릭 시나리오는 `chatroom-actions.test.jsx`(로컬)로만 검증됨.
- **9-2(오프보딩 방장 인계 일반화)** — 두 번째 계정을 만들어 방을 만들게 하고 그 계정을
  비활성화·보관해야 재현 가능한데, 이번 세션엔 새 계정을 만들지 않았다. `set_user_active`/
  `archive_user` 경로 모두 로컬 통합 테스트(`test_admin_user_archive.py`의 신규 2건)로만
  검증됨.
- **9-7(게임 명단 "자리 비움" 배지)** — 솔로 계정으로 방을 만들면 항상 "현재 접속"
  상태라 배지가 뜨는 조건(90초 이상 미폴링) 자체를 실서버에서 재현할 수 없었다(두 번째
  계정이나 시간 조작이 필요). 명단이 활성 인원에 대해 배지를 잘못 띄우지 않는 것(회귀
  없음)까지는 라이브로 봤지만, 배지가 실제로 뜨는 것 자체는 `test_games_api.py::
  test_roster_marks_stale_members_as_not_present`(로컬)로만 검증됨.
- **10-1/10-2/10-3(채팅 파서 통일)** — 두 화면 모두 콘솔 오류 0건은 확인했지만, 이 세
  항목을 실제로 트리거하는 문장(머리글에 URL, "오전 9:30" 같은 접두 붙은 시각, 괄호+
  한글조사 URL)을 직접 입력해 렌더 결과를 눈으로 보지는 않았다 — 각각
  `links.test.jsx`/`RichText.test.jsx`/`chat-helpers.test.js`(로컬)로만 검증됨.

**9-1·9-4 (게시판 수정 흔적 + 툼스톤)**: `app/board/service.py`의 `ensure_can_edit`을
작성자 본인만으로 좁히고(`ensure_can_delete`를 새로 분리 — 삭제는 여전히 작성자 또는
운영자군), 응답에 `can_edit`/`can_delete`를 별도 필드로 분리(`_post_summary`·`_post_detail`·
`_comment_view`). 댓글 목록(`repository.list_comments`)이 삭제된 행도 함께 돌려주게
바꾸고(예전엔 `deleted_at IS NULL` 필터로 통째로 사라져 답글만 남으면 고아가 됐다),
`_comment_view`가 삭제된 댓글을 본문 없는 툼스톤으로 감싼다 — 티켓·문서 댓글
(`app/tickets/comments.py`)과 같은 규약. 프런트(`BoardPost.jsx`)에 툼스톤 렌더 +
"(수정됨)" 표시 + 버튼 분리 추가.

**9-2 (방장 오프보딩 인계)**: 방장직 이전 로직(`_transfer_room_ownership`)이 오프보딩
마법사 전체 실행 경로에만 있었다 — `/users`에서 바로 비활성화·보관해도 계정은 똑같이
로그인을 못 하게 되는데 그 경로는 인계를 건너뛰었다. 순환 import를 피해
`app/team_chat/service.py::transfer_owned_rooms`로 옮기고, `app/users/service.py`의
`set_user_active`/`archive_user`(직접 비활성화·보관)와 `app/offboarding/service.py`
(오프보딩 실행) 둘 다 부르게 함.

**9-3 (전체 채팅 @멘션 강조)**: `/api/team-chat/directory`가 호출자 본인을 항상 빼서
(1:1 상대 고르기용 설계) 전체 채팅에서는 렌더용 멘션 후보 목록에 내 이름이 들어올 길이
없었다. `you.display_name`을 `/api/team-chat/rooms/{id}/messages` 응답에 추가하고
(`app/team_chat/router.py`), `ChatPane.jsx`가 전체 채팅일 때 그 값으로 렌더용 목록을
보완.

**9-5 (나가기 문구)**: 방장이 나가면 남은 사람이 없을 때 방이 사라지는데(파하기와 같은
결과) 확인 문구는 "계속할까요?" 한 마디였다. `you.role`/`room.member_count`로 결과가
다른 문구를 만드는 `leaveRoomConfirmMessage()` 신설(`ChatRoom.jsx`).

**9-6 (방 이름 저장이 초대 대상을 날림)**: `ManageRoomModal`의 초기화 effect가
`[open, title]`에 의존해, 열린 채로 이름만 저장해도(rename.onSuccess → refresh() →
title prop 갱신) 골라 둔 초대 대상이 조용히 날아갔다. 의존성을 `[open]`으로 좁힘 —
일부러 되돌려서 새 회귀 테스트가 실제로 잡는 것까지 확인한 뒤 다시 고쳤다.

**9-7 (게임 명단/추첨 풀 어긋남)**: 명단엔 남아 있어도(active) 90초 폴링 정지면 추첨
대상 풀(`_present_players`)에서 조용히 빠졌다 - 명단이 그 사실을 표시할 수단이 없었다.
`app/games/service.py::is_present()` 신설 + `_member_view`에 `present` 플래그 추가,
프런트(`MembersList.jsx`)에 "자리 비움" 배지. `PRESENCE_SECONDS=90`의 거짓 근거 주석
("폴링 스로틀")도 정정 — react-query focusManager는 숨은 탭에서 스로틀이 아니라 폴링을
완전히 멈춘다.

**10-1 (`trimUrlTail` 미공유)**: `chat-text.js`(팀 채팅)의 URL 꼬리 다듬기를 export해
`chat/links.jsx`(AI 답변 링크화기)도 같은 함수를 쓰게 함. **검증 중 발견**: 이 함수는
공백 없이 바로 붙은 한글 조사("...(url)에서")는 못 뗀다 — chat-text.js 자신도 같은
한계가 있고(기존 테스트가 공백 있는 입력만 검증), 이번 통일로 그 한계까지 AI 링크화기가
동일하게 물려받았다. 근본 수정(URL 정규식이 한글 문자를 만나면 멈추게)은 범위가 더 커
`docs/KNOWN_LIMITATIONS.md`에 기록만 하고 보류.

**10-2 (RichText 머리글 미링크화)**: `parseBlocks`의 네 블록(head·list·kv·para) 중
head만 `linkifyText`를 안 거쳤다 — "■ https://…"로 시작하는 답변 줄의 URL이 죽은
글자로 남았다. `RichText.jsx`의 head 렌더에 `linkifyText` 적용.

**10-3 (`kvOf` 시각 오탐)**: "09:00" 같은 **순수 숫자 키**만 시각으로 걸러 냈다 —
"오전 9:30에 회의"처럼 시 앞에 말이 붙으면 못 걸러 2줄이면 정의목록(dl)으로 잘못
렌더됐다. 키 끝이 시(0~23)로 끝나고(줄 시작·공백·여는 괄호 뒤에서만) 값 머리가
분(00~59)이면 시각으로 보는 `HOUR_TAIL`/`MINUTE_HEAD` 판정 추가(`chat-helpers.js`).

---

## 🔵 Sonnet 구현 사이클 3 완료(1차) — 설정/Notion 쓰기/셸 스코프/위생 묶음, 배포·실환경검증 (2026-08-10)

`SONNET_HANDOFF.md §3` 5~11단계(설정 화면 배선 · Notion 본문 쓰기 안전 · 설정 오버레이 배선 ·
셸 스코프 배선 · 게시판/채팅 규약 통일 일부 · 위생 묶음)를 구현하고 **실서버(10.100.64.71)에
배포, Chrome으로 핵심 경로를 직접 열어 확인**했다.

**배포**: `build-bundle.sh` → scp → `bundle.sha256`/`MANIFEST.sha256` 둘 다 체크섬 일치 확인 →
`upgrade-clovirone-web-assistant.sh`(DNS_NAME/BIND_IP 지정) → `UPGRADE_OK`. 배포 직후
`systemctl is-active`로 web·worker·privhelper **3종 전부 active** 확인,
`GET /healthz` → `{"status":"ok","ticket_source":"notion_cache"}`(11단계 항목이 실제로 필드를
내보내는 것 확인), `GET /readyz` → `{"status":"ready"}`.

**Chrome 실환경 검증(로그인 계정: hshwang@goodmit.co.kr, system_admin)**:
- **BrandLogo**(11단계) — 로그인 화면과 앱 상단바 양쪽에서 부제("SMART WORKSPACE ASSISTANT")가
  **실제로 읽을 수 있는 크기로 렌더**되는 것을 육안 확인(수정 전이면 이 자리가 실렌더
  ~6.4px로 사실상 안 보였을 자리 — 자동 테스트가 못 잡는 픽셀 단위 결함이라 이 육안 확인이
  유일한 증거).
- **RBAC 매트릭스**(11단계) — `/rbac`에서 새로 추가한 두 행이 실제로 렌더됨을 확인:
  "대리 보기 시작" = 관리자·시스템 관리자만 허용(운영자·감사자 `—`), "시스템 설정 변경" =
  시스템 관리자만 허용(관리자도 `—`) — 코드로 짠 그대로.
- **설정 화면**(5단계) — `/settings`에서 "세션 정책" 행 설명이 "유휴 제한은 저장 즉시(이미
  열린 세션 포함), 최대 세션 길이는 신규 세션부터 적용"으로 정정된 문구가 실제로 뜨는 것,
  "메일(SMTP) 발송" 행이 raw JSON이 아니라 한국어 요약으로 뜨는 것, 세션 정책 상세 편집기가
  크래시 없이 열리고 `= 680분`/`= 8시간`으로 렌더되는 것(H-2 회귀 없음)을 확인.
- **로그아웃**(8단계) — 정상 흐름에서 로그인 화면으로 깨끗이 이동하는 것 확인(골든 패스).
- **`/api/team-chat/rooms` ETag**(11단계) — 배포된 서버에 브라우저 콘솔에서 직접 `fetch`
  두 번을 날려 **첫 요청 200+ETag, 두 번째 요청(`If-None-Match`)이 실제로 304를 받는 것**을
  실측 확인(설계대로 동작).
- **문서 목록/개별 문서**(6단계 EditableBody 변경 회귀 없음 확인) — `/team-docs`에서 실제
  Notion 미러 문서 107개 목록과 그중 하나(Cloud-init 가이드)의 상세를 열어 콘솔 오류 0건
  확인. **저장(쓰기)은 시도하지 않았다**(D-21) — 이 화면의 검증은 "안 깨졌다"까지다.
- 대시보드 화면(`/dev-report`)의 Donut 차트가 실데이터로 정상 렌더되는 것 확인(빈 상태
  높이 유지 자체는 데이터가 없을 때만 발현하므로 이 화면에서는 회귀 없음만 확인).

**아직 실서버에서 안 본 것(정직하게 남긴다)**: 부서 관리자 계정의 ScopeBar 라우트별 문구
차이(계정을 새로 만들어야 해서 이번엔 로컬 테스트로만 검증 — `scope-bar-route-awareness.test.jsx`),
Notion 원문에 실제 중첩/토글 블록이 있는 문서를 열어 새 경고 문구가 뜨는지(그런 문서를
못 찾음 — 로컬 스텁 테스트만), 강조색 선택 UI를 눌러 실제로 계정별 저장되는지(로컬 배선
테스트만 — `user-menu-accent-wiring.test.jsx`), LineSeries null 값 렌더(현재 두 소비자 모두
null을 0으로 치환해 실화면에 발현 안 함, 설계대로).

**로컬 게이트(전부 확인됨)**: 백엔드 pytest 전체 2회 green(중간에 Notion 블록 계약 골든
파일 갱신 1건 — 의도된 드리프트, `has_children` 필드 추가), 프런트 vitest 전체 3회 green
(174→184 파일, 1224→1248 테스트), `bash scripts/static_checks.sh` → `STATIC_CHECKS_OK`
(44개 검사 전부 통과), `npm run build` + `check_bundle_fresh.py --write` 로 번들 재생성 완료.

**5단계 설정 화면 배선**: `fmtDuration` import(이미 사이클 1에서 완료 확인), `session_policy`
설명문 정정 + 줄이기 경고 추가, `settings-labels.test.js`의 손유지 `OBJECT_TYPES` 목록을
레지스트리에서 동적으로 뽑도록 교체(`SET-...`류, `retry_policy` 죽은 검증기 삭제),
`SettingEditor.jsx` 읽기 전용 버튼을 `disabled`로(안 사라지게).

**6단계 Notion 본문 쓰기 안전 (`FN-50`/H-1)**: `page_block_refs`가 `has_children`도 읽어
자식 있는 블록을 `deletable`에서 제외(`notion_write.py`·`notion_docs.py` 동일 패턴,
죽은 `page_block_ids` 삭제). `EditableBody.jsx`에 중첩 콘텐츠 경고 추가. 게시판→티켓 전환
영구 실패 버그(`_fit_for_ticket_description` 신설 — 긴 한 줄 문단을 줄바꿈으로 나눠
`TicketCreate._check_desc`를 통과시킴, `board/service.py`) 로컬 스텁 테스트로 검증
(D-21 — 실서버 Notion 쓰기는 재현하지 않음, 로컬 스텁이 이 항목의 검증 상한).

**7단계 설정 오버레이 배선 (`WORKER-01`/`SET-10`/`SET-11`)**: `worker_main.py`에 60초 간격
`settings_cache_tick` 신설(다른 콜백보다 먼저 등록 — 같은 반복 안에서 최신값을 보게).
거짓 주석 4곳 정정(worker_main.py·llm_connection_test.py·CONSOLE_SCREENS.md·
tenant_config.py). `apply_setting`이 저장 전 문자열을 `strip()`. `SYS-08`(숫자 센티널
비대칭) docstring 정정 + 참조 연결. `TENANT_SETTINGS`/`OVERRIDABLE_KEYS` 두 목록이 다른
이유(타입 불일치 위험)를 코드에 명시.

**8단계 셸 스코프 배선**: `ScopeBar`가 라우트를 가려 실제로 범위가 걸리는 화면
(`navConfig.js::SCOPE_ENFORCED_PATHS`)에서만 "범위 밖은 안 보인다" 문구를 띄움. 부서
관리자 표시가 본인 소속 부서가 아니라 **배정받은 관리 범위**(`scope_dept_name`/
`scope_org_name`, `/api/me` 신설 필드)를 보이게. 다른 API의 401이 `["me"]` 쿼리를
무효화해 세션 만료 화면이 실제로 켜지게(`api.js::api.onUnauthorized`, `auth.jsx`) —
**구현 중 자체 발견 버그**: 최초 설계가 `/api/me` 자신의 401에도 무효화를 걸어 무한
재무효화 루프로 vitest 워커가 힙 고갈로 죽는 것을 실측, `path !== "/api/me"` 가드로 수정
+ 회귀 테스트로 고정. 로그아웃 5xx/망 실패 시 무조건 `/login`으로 보내던 것을 401만
그렇게 하고 나머지는 토스트로 알리게(`UserMenu.jsx`).

**11단계 위생 묶음 — 10개 항목을 워크플로(병렬 서브에이전트 10개)로 구현**: RBAC 매트릭스에
`impersonation.start`·`system.settings` 행 추가, `ConfigVersion` ORM에 유니크 제약
선언(alembic 0004와 동일), `versioning.py` docstring의 pre/post-change 서술 정정,
`/healthz`에 `ticket_source` 노출, `/api/team-chat/rooms`에 ETag 적용, `Donut` 빈 상태
높이 유지, `BrandLogo` 부제를 SVG `<text>`(실렌더 ~6.4px)에서 HTML로, `LineSeries`의 null
값 x좌표 보존, 강조색 계정별 저장, `scrollIntoView`의 reduced-motion 반영, 빈
`@media(prefers-reduced-motion)` 블록 8개 + 죽은 `.chat-thinking` CSS 삭제.
**서브에이전트 결과를 그대로 안 믿고 직접 리뷰해서 잡은 것 1건**: 강조색 계정별 저장이
`ThemeModeProvider`에 `userId` prop을 받게 설계됐는데, 그 컴포넌트는 `AuthProvider`
**바깥**(main.jsx)에 마운트돼 있어 그 prop이 실제로는 **한 번도 채워질 수 없는** 구조였다
(에이전트의 단위 테스트는 prop을 직접 주입해서 통과했을 뿐, 실제 앱에서는 죽은 코드).
`identifyAccentUser()`를 컨텍스트에 노출해 `UserMenu.jsx`(계정을 아는 첫 지점, 테마 복원과
같은 자리)가 호출하는 구조로 다시 짜고, 실제 트리로 배선이 닿는지 보는 회귀 테스트
(`user-menu-accent-wiring.test.jsx`)를 새로 추가해 고정했다 — 이 저장소가 그동안 계속
찾아낸 "헬퍼는 있는데 부르는 쪽이 안 부른다" 결함을 새 코드에서 스스로 반복할 뻔한 사례.

**9·10단계는 아직 착수 전** — 게시판·채팅 규약 통일 나머지(수정 흔적 표시, 방장 오프보딩
인계, 전체 채팅 @mention 강조, 댓글 툼스톤, 나가기 문구, 방 이름 저장 버그, 게임 명단/추첨
불일치)와 채팅 텍스트 파서 공용화(`trimUrlTail`, RichText 머리글, `kvOf` 오탐)는 다음 작업.

**다음**: 9·10단계(게시판·채팅 규약 통일 나머지, 채팅 파서 공용화) 착수 → 완료되면 그 배치도
같은 방식(로컬 테스트 green → 배포 → Chrome 확인)으로 마무리 → 사이클 4(전체 제품 재감사,
CLAUDE.md/WORK_PLAN §12 기준 수렴할 때까지 반복).

---

## 🔵 Sonnet 구현 사이클 2 완료 — Critical/High 축(SYS-01·SEC-30·SEC-22·FN-40·OPS-10/11) 전부 실환경검증완료 (2026-08-09)

`SONNET_HANDOFF.md §3` 2~4단계를 끝냈다. **여섯 항목 전부 실서버에서 직접 재현·확인**했다
(코드만 고치고 "될 것이다"로 남긴 것 없음):

- **`SYS-01`** TLS 인증서 교체 무동작 — `settings.tls_cert_path`(env `TLS_CERT_PATH`)로 통일하고
  privhelper 유닛에 `EnvironmentFile=` 추가(그 프로세스는 FastAPI `Settings` 가 없는 별도
  프로세스라 env 로 전달해야 했다). **실제로 새 인증서(다른 만료일·serial)로 교체하고
  `openssl s_client` 로 nginx 가 그것을 서빙하는 것을 확인한 뒤 원래 인증서로 복원**했다.
- **`SYS-02`**(무료 동승, 같은 파일) `hostnamectl show -p` 가 systemd 255 에 없는 verb라 호스트
  이름이 영구히 빈 문자열 — `hostname.set` 이 이미 쓰던 `status --static` 폴백으로 통일.
- **`SEC-30`** CSV 가져오기 권한 상승 — 게이트(`ensure_can_grant_role`)를 `create_user()` 안으로
  옮겨 웹 폼·CSV·CLI·`seed_admin.py` 가 전부 한 곳을 지나게 함. **plain admin 계정으로 실제
  CSV 미리보기에 `role=system_admin` 행을 넣어 거부되는 것을 확인.**
- **`SEC-22`**(SEC-30 과 같이 묶임) CLI 계정 조작이 이상 탐지에서 전부 안 보이던 것 —
  `app/audit/actions.py` 신설로 `health/service.py`·`anomalies.py` 가 목록을 공유하게 함.
  **CLI 로 실제 역할 변경을 실행하고 `/api/admin/audit/anomalies` 에 잡히는 것을 확인.**
- **`FN-40`** 공지 PATCH 가 `body`/`title`/`level`/`audience` 를 `null` 로 보내면 500 —
  `body` 는 POST 와 같은 규칙(빈 문자열)으로, 나머지 셋은 명확한 422 로. **실제 PATCH 요청
  두 종류(`body:null`→200, `title:null`→422) 를 직접 보냈다.**
- **`OPS-10`/`OPS-11`** 워커 리스 획득 실패·하트비트 갱신 실패가 예외로 새면 재시작 루프·
  좀비 상태가 됐다 — `WorkerLockError` 로 구분해 깨끗이 종료, `renew()` 도 `beat_liveness()`
  와 같은 방어. 유닛 `RestartSec=10`+`StartLimitIntervalSec=300`. 실패 주입은 **공유 워커를
  실제로 고장내지 않기 위해** mock 기반 단위테스트로(정상 기동·리스 획득은 실배포로 확인).

**자율 연속 실행 체계**: 사용자가 "세션 하나가 끝나도 재호출 없이 계속 이어지는 구조를
만들고 검증하라"고 요청 → 하네스 내장 `/loop` dynamic mode + `ScheduleWakeup` 을 그 목적으로
재사용하기로 결정(D-53). **이미 실측 검증됨**: 사이클 1→2, 사이클 2 안에서도 여러 차례
사용자 입력 없이 `ScheduleWakeup`/배경 작업 완료 알림만으로 재개됨.

로컬 게이트 전부 green(pytest 루트 전체 2회 + 러너 + vitest, `STATIC_CHECKS_OK`).
**다음**: `SONNET_HANDOFF.md §3` 5~11단계(설정 화면 배선 · Notion 본문 쓰기 안전 · 설정
오버레이 배선 · 셸 스코프 배선 · 게시판·채팅 규약 통일 · 채팅 파서 공용화 · 위생 묶음).

---

## 🔵 Sonnet 구현 사이클 1 완료 — 배포 경로 자체를 고쳐야 나머지를 검증할 수 있었다 (2026-08-09)

`SONNET_HANDOFF.md §3` 의 순서대로 착수. **1단계(배포 경로 복구)를 먼저 끝냈다** — 이후
모든 사이클의 "배포 후 재검증"이 여기 의존하므로, 이 단계가 실서버에서 실제로 되는 것을
확인하기 전에는 아무것도 검증할 수 없었다.

**완료(실환경검증완료)**: `DEPLOY-01`·`DEPLOY-02`(`upgrade-clovirone-web-assistant.sh` 가
DNS_NAME/BIND_IP 를 요구·전달, `rollback_now()` 이식) · `UX-50`(H-2, `fmtDuration` import
누락 — 세션 정책 편집기 크래시) · **직접 배포하다가 새로 발견한 2건**: `DEPLOY-03`(installer
주석이 "아무것도 안 바꿨다"고 거짓말) · `DEPLOY-04`(롤백이 특권 헬퍼를 안 되살림).

**직접 배포 절차를 문자 그대로 따라가다가 문서 자체의 버그 2개를 더 찾았다**(이번 것도
BACKLOG 에 없던 새 발견, `MAINTENANCE_PLAYBOOK.md §2-3` 수정함):
- `sha256sum -c MANIFEST.sha256` 을 **압축을 풀기 전에, 그 파일이 없는 경로에서** 돌리려
  했다 — `&&` 로 이어져 있어 실패해도 뒤 단계가 조용히 안 실행되고 옛 스테이징이 남는다.
- `mkdir -p stage && tar -xzf … -C stage` 가 이미 `stage/…` 로 시작하는 tar 내용을 다시
  `stage/` 안에 풀어 **`~/deploy/stage/stage/app-src` 로 이중 중첩**됐다 — `STAGE=~/deploy/stage`
  를 쓰는 다음 단계가 `app-src` 를 못 찾고 죽는다.

**실서버 검증 방법(그대로 재현 가능)**: 정상 배포 1회(`UPGRADE_OK`) → 스테이징 사본을
고의로 깨서(`requirements.txt` 제거) 재배포 → 서비스 정지 후 install 실패 →
`rollback_now` 가 백업 복원 → `UPGRADE_ROLLED_BACK` → `systemctl is-active` 3종
(web·worker·privhelper) 전부 active + healthz/readyz 200. **두 번** 이렇게 재현해 DEPLOY-04
(privhelper 백업 자체가 새 코드에서만 생기므로) 수정 전/후를 비교 확인했다.

로컬 게이트 전부 green(pytest 루트 전체 + 러너 263 + vitest 173파일/1213개 + `STATIC_CHECKS_OK`).
**다음: `SONNET_HANDOFF.md §3` 2~4단계**(`SYS-01` TLS 무동작 · `SEC-30` CSV 권한 상승 ·
`FN-40` 공지 500 + `OPS-10`/`OPS-11` 워커 내구성) — Critical/High 축.

---

## ✅ 탐색은 수렴했다 — Sonnet 인계 준비 완료 (2026-08-09)

> **먼저 읽을 것: [`SONNET_HANDOFF.md`](SONNET_HANDOFF.md)** — 이 문서 하나로 구현을 시작할 수 있다.

**발견 곡선(6라운드 실측)이 수렴을 보여 준다** — Critical `0 → 2 → 2 → 1 → **0**`,
High 비중 9.6% → 19.6% → 6.7% → 10% → **5.4%**(최저), Low 비중 **62%**(최고).
마지막 라운드의 Low 23건 중 **10건이 "코드는 맞는데 주석·문서가 거짓"** 유형이다 —
실행 결함이 고갈되고 문서 정합만 남았다는 신호다. **신규 범주 0개**, 반증률도 27~35%로 평평하다.

**단, "수렴"은 조사가 끝났다는 뜻이지 제품이 고쳐졌다는 뜻이 아니다.**
BACKLOG 529행 중 `실환경검증완료` 는 **2건**이다. 인계 성격은 **조사 종료 → 구현 착수**다.

| | |
|---|---|
| BACKLOG | **529행 / 36범주** · Critical 5 · High 113 |
| 화면 판독 | 66/70 + 4K 128페이지 + 다크 + 반응형 6폭 |
| 역할 매트릭스 | 4역할 197페이지 — **화면 게이팅 결함 0** |
| 새로 연 검증 축 | `U` 실사용 · `K` 대비 · `B` 키보드 · `S2` 시맨틱 (+ `FAIL`·`HOST`·`RESP`) |
| 워크플로 | 5회 · 에이전트 63개 · **원 보고 447건 중 176건(39%) 반증 폐기** |
| 내 오판 | 프로브 위양성 4 · 판정 철회·정정 8 (전부 근거와 함께 기록) |

**지배적 결함 유형은 6라운드 내내 하나로 수렴했다** —
**규칙·헬퍼·술어·토큰이 이미 있는데 부르는 쪽이 안 부른다.**
구현은 "만들기"가 아니라 **"배선하기"**다.

## 3-0-Z. ✅ **사용자 조치 2건 완료** (2026-08-09) — 후속은 남아 있다

- **`OPS-01` 업로드 디렉터리 `chown` 완료**(사용자). ⚠️ **`OPS-02` 는 남았다** —
  installer 의 `install -d -o $SVC_USER` 목록에 `uploads` 가 없어서 **다음 배포에 재발한다.**
  그리고 **"고쳐졌다"를 믿지 말고 실제로 첨부를 한 번 올려 확인해야 한다**(실패는 감사에 안 남는다).
- **`SEC-20` sudo 비밀번호 회전 완료**(사용자). 문서에서 옛 값 제거함.
- `SEC-10`(Notion 문서의 평문 자격증명) 처리 여부는 **미확인**.

### (기록) 원래 내용 — 실서버가 깨져 있던 상태

**`OPS-01` 파일 첨부 업로드가 2026-08-07 부터 불가능하다.**
`/var/lib/clovirone-web-assistant/uploads` 만 **root:clovirone-web 750** 이라 서비스 사용자
(`clovirone-web`)에게 쓰기 비트가 없다 — `runuser -u clovirone-web -- test -w` 로 **쓰기 불가 확인**.
형제 디렉터리(`exports`·`generated`·`locks`·`temp`)는 전부 정상 소유다.
마지막 성공 업로드는 **2026-08-05 00:23**, 이후 시도 자체가 없어 아무도 모르고 있다.
**업그레이드로 안 고쳐진다** — installer 의 `install -d -o $SVC_USER` 목록에 `uploads` 가 없다.

```
sudo chown -R clovirone-web:clovirone-web /var/lib/clovirone-web-assistant/uploads
```
+ installer 목록에 `uploads` 추가(안 하면 재발). `BKP-01`(업로드가 백업에 없음)과 겹친다.

**`SEC-20` 내 조사가 sudo 비밀번호를 명령행에 반복 노출했다** — 불변규칙 §2-4 위반이고
워크플로 프롬프트로 서브에이전트 13개에 배포했다. **그 비밀번호는 손상된 것으로 보고 회전해야 한다.**

## 3-0-B. **Critical 2건 — 조사 중 새로 나왔고 내가 재확인했다** (2026-08-09)

1. **`DEPLOY-01` 문서에 적힌 업그레이드 절차가 반드시 실패하고 서비스는 멈춘 채 남는다.**
   `upgrade-*.sh` 가 installer 에 `DNS_NAME`·`BIND_IP` 를 안 넘기는데 installer 는 그 둘이 없으면
   `exit 2`(`install-*.sh:46-51`). 그 시점엔 이미 **web·worker 를 둘 다 정지**시킨 뒤이고
   되살리는 코드가 없다. `MAINTENANCE_PLAYBOOK.md` §2 대로 하면 **서비스 중단**이다.
   ※ 이번 사이클 배포가 성공한 것은 내가 두 값을 직접 넘겼기 때문이다.
   ※ 같은 파일의 **git 경로에는 `rollback_now()` 가 있는데 번들 경로에는 없다**(`DEPLOY-02`).
2. **`FN-40` 공지 「내용」을 비우고 저장하면 500.** `AnnouncementPatch.body` 는 `str|None` 인데
   컬럼은 `nullable=False` 이고 PATCH 루프가 null 을 그대로 넣는다. **POST 경로는 이미
   `or ""` 로 막고 있다** — PATCH 만 빠졌다. 화면엔 영어 "Internal server error" 만 뜬다.

## 3-0. 임박한 것 (시간이 지나면 저절로 터진다)

- **`UB-40` 오프보딩 목록이 21명째부터 잘린다** — 현재 **18명**. `Offboarding.jsx:65` 가
  `page_size=20` 하드코딩이고 총건수·페이저·잘림 경고가 없다. 세 명만 더 들어오면
  퇴사 처리 대상자를 목록에서 못 찾는다.
- **`RSTR-03` 자동 백업이 꺼져 있고 마지막 백업이 2026-07-19** — 매일 멀어진다.
- **`SCHD-01` 유일한 스케줄이 AI 채팅 웹훅을 가리킨다** — 누군가 「활성」을 켜는 순간
  매주 월요일 09:00 에 Notion 쓰기가 나갈 수 있다. **켜지 않았다.**
- **`SEC-10` Notion 문서 1건에 평문 자격증명** — 사용자에게 알려야 할 항목(원본은 실고객 워크스페이스).

## 3-1. 가장 먼저 손대야 할 것 (사이클 0이 남긴 결론)

**최우선은 `SYS-01`이다** — TLS 인증서 교체가 성공 메시지·새 인증서의 subject·만료일까지
보여 주면서 **실제로는 아무것도 바꾸지 않는다**(nginx 가 읽지 않는 경로에 쓴다). `CLAUDE.md`
§10이 "운영 전 사설 CA 인증서로 교체"를 남은 조치로 적어 둔 바로 그 경로이고, 관리자는
성공했다고 믿게 된다. 고치는 것은 경로 한 곳이며 **올바른 값이 이미 `settings.tls_cert_path`에
있다**(`probe_tls`·`app/health/service.py`가 그것을 쓴다).

그다음이 `AI-30`(11일 묵은 CREATE 모드가 질문을 티켓 생성으로 바꾼다 — 러너 문맥에 만료가
없다)과 `AI-37`(그 상태의 탈출어를 그 자리에서 안 알려 준다). **둘 다 러너 쪽 작은 변경인데
체감 효과가 가장 크다.**

이어서 아래 러너 쓰기 3건 —

러너에서 **재현까지 끝난** 세 건이 제품 전체에서 가장 위험하다 — AI가 사용자의 **질문과 거절을
승인 없는 Notion 쓰기로 바꾼다**:
- `RN-01` "그거 완료했어?" → 티켓이 완료로 바뀐다 (`norm()`이 `?`를 지우고, 질문 가드가 최상위
  라우터에 없다)
- `RN-02` "완료로 바꾸지 마" → 완료로 바뀐다 (부정 가드가 `is_approval_message` 안에만 있는데
  분기 ③이 그보다 먼저 돈다)
- `RN-03` 티켓 선택 대기 중 "그만할래" → 이전 변경이 쓰인다 (`is_update_intent`가 무조건 True)

그다음이 `SEC-01`(권한 경계) · `UA-01`(전사 데이터 노출) · `UB-01`(부서 admin이 전사 배너) ·
`UA-03`(백업 중 전체 쓰기 잠김) · `RG-01`(절대 작동 못 하는 버튼) · `DS-32`(4K 두 줄).

## 3-2. 조사 종료 시 정리할 것 (내가 만든 것)

- **`qa-user`·`qa-operator`·`qa-auditor`·`qa-admin` 4계정을 비활성화한다.** 지금 이 계정들이
  `/dev-report` **개발자 월간 리포트에 빈 행으로 섞여 있고**, `/users` 목록 맨 위에 뜨며,
  스프린트 담당자 후보에도 나온다. 명령:
  `sudo … venv/bin/python -m app.cli.user_cli disable --email qa-*@goodmit.co.kr`
- `~/deploy/stage-new2`, `dist/ui-qa-*` 등 산출물은 서버·로컬 모두 `dist`·홈이라 무해하지만,
  서버 홈에 116MB짜리 옛 번들이 여러 개 쌓여 있다(7GB) — 정리하면 좋다.
- 로컬 `.claude/worktrees/` 88개(`C0-7`, 보류 중) — **저장소 grep 을 오염시키므로 조사 방해 요인이기도 하다.**
- **`hshwang@` 계정에 조사용 대화 4개**가 생겼다("방금 말한 것 중에 제일 오래된 건 뭐야?" ×2 등).
  기존 52개에 섞여 있다. 지우거나, 남기기로 했다면 그 사실을 여기 유지한다.
- **`/chat` 의 오래된 대화 하나가 `mode=CREATE` 로 갇혀 있다**(`112347f0-…`, `AI-30`의 실물).
  고치기 전에는 **재현용 증거이므로 지우지 않는다.**
- **`mail_deliveries` 14행 · `approvals` 1행 · `restore_rehearsals` 1행** — 내 실행 검증의 흔적.
  메일은 전부 `unconfigured` 라 **실제 발송은 없었다.** `USE-01` 집계를 다시 낼 때 이것을 뺀다.
- **`saved_views` 에 조사용 행 1개**(`QA 조사용 뷰`, `/workflows`, `hshwang@` 소유). 개인 뷰라
  다른 사용자에게 안 보인다. 지우거나 남겨도 무해하다.

## 3-3. 이번 구간에 철회한 것 (같은 실수를 반복하지 않기 위해 남긴다)

| 철회 | 왜 틀렸나 |
|---|---|
| 「클로비가 ~를 가린다」 계열 **7건**(`VIS-104`·`VIS-122` 등) | **전체 페이지 스크린샷이 `position:fixed` 를 엉뚱한 자리에 그린다.** 살아 있는 DOM 으로 재니 60라우트 중 1건, 긴 표 8종×스크롤 4위치에서 0건. 하네스의 `fab_overlap`은 내내 옳았다 → [D-23](DECISIONS.md) |
| `USE-03` "저장된 뷰에 빈 상태가 없다" | **클릭하지 않고 스크린샷만 보고 판정했다.** 실제로는 빈 상태 문구·저장 미리보기까지 잘 만들어져 있고 DB 저장까지 정상이다 |
| `AI-31` "조건을 조용히 버린다" | **조용하지 않다** — 코드가 반드시 고지하고, 그 주석에 세 번의 회귀 이력까지 적혀 있다. 진짜 문제는 앞단의 의도 분류다 |
| `VIS-107~109` "지금 오류 4건이 나 있다" | **전부 3주 전 것**이고 원인 하나는 이미 고쳐졌다. 진짜 문제는 **아무도 3주간 재시도를 안 눌렀다**는 것 |

## 4. Blocker

| ID | 내용 | 영향 | 조치 |
|---|---|---|---|
| ~~B-1~~ | ~~테스트 서버가 HEAD가 아니다~~ | — | **✅ 해소됨** (2026-08-08 10:01, `UPGRADE_OK`+`DEPLOY_VERIFY_OK`). 이제 서버 = HEAD이므로 실물 조사 결과를 신뢰할 수 있다 |
| ~~B-2~~ | ~~Chrome 확장 미연결~~ | — | **✅ 해소됨** (2026-08-08). 붙자마자 **스크린샷으로는 절대 안 나오는 결함**을 찾았다 — `VIS-72`(검색하면 사용자 콘솔에서 관리자 콘솔로 튕겨 나감). 실조작(`F` 축)이 왜 필요한지 첫 증거 |
| ~~B-2-old~~ | ~~Chrome 확장 미연결.~~ `mcp__claude-in-chrome__list_connected_browsers` → `[]` (4회 확인) | Chrome MCP 검증 불가(콘솔·네트워크 탭·수동 조작·폭 실시간 변경) | **사용자 조치 필요**: 확장이 Claude Code와 **같은 claude.ai 계정**으로 로그인됐는지 · 설치 후 Chrome 재시작 · 확장 팝업에서 연결 버튼 클릭. 그 전까지 Playwright 하네스(실제 Chromium·실제 로그인·실제 서버 DB)로 대체하고 PNG를 직접 판독 |
| ~~B-3~~ | ~~하네스가 자체서명 HTTPS를 못 탄다~~ | — | **✅ 해소됨** — `--insecure` 추가. **SSH 터널은 쓰면 안 된다**(서버가 `COOKIE_SECURE=true`라 Playwright API 클라이언트가 http로 세션 쿠키를 안 싣는다, [DECISIONS D-05a](DECISIONS.md)) |

---

## 5. 환경 사실 (매번 다시 조사하지 말 것)

**서버** `cloviradmin@10.100.64.71` · `https://clovirone-ai.gooddi.lab` · Ubuntu 24.04 ·
**테스트 서버다**(운영 아님, 사용자 확인). SSH 키 인증, sudo는 비밀번호(stdin으로만 전달).

서비스 상태(2026-08-08 확인): `clovirone-web-assistant`·`clovirone-web-worker`·`nginx` 전부 active ·
러너 `:8787`(ticket)·`:8788`(interpreter v2.1.1)·`:8789`(work-assistant v3.57.0) healthy ·
n8n `:5678` active, 워크플로 2개 active + 웹훅 2개 등록(`clovirone-work-assistant`,
`clovirone-notion-user-mapping`) · Claude CLI 2.1.197 · `ASSISTANT_MODEL=sonnet`(systemd env).

**데이터 규모**(서버 DB, 2026-08-08 실측): users 19 · conversations 68 · messages 247 ·
ticket_cache 1077 · search_documents 1201 · notifications 103 · audit_logs 603 · jobs 130.
**0행인 것**: approvals · document_generations · schedule_runs · mail_deliveries ·
offboarding_runs · restore_rehearsals · impersonation_sessions · ai_quotas · announcements ·
saved_views · trash_items · project_weekly_reports (→ `USE-01`).
DB는 `/var/lib/clovirone-web-assistant/web.sqlite3`(**`app.db` 아님**).
읽는 법 — 리다이렉트를 쓰면 sudo 가 stdin 을 빼앗기므로 **SQL 을 인자로** 넘긴다:
```bash
ssh cloviradmin@10.100.64.71 "echo '<비밀번호>' | sudo -S sqlite3 -readonly \
  /var/lib/clovirone-web-assistant/web.sqlite3 \"SELECT COUNT(*) FROM jobs;\""
```

**호스트 사실**: static hostname `ai-n8n-svr` · systemd 255 (`hostnamectl` 에 `show` verb 와
`--property` 옵션이 **없다**, `SYS-02`) · nginx TLS 는
`/etc/clovirone-web-assistant/tls/clovirone-ai.gooddi.lab.crt`(자체서명, issuer==subject,
2027-07-14 만료) · `/etc/ssl/clovirone/` 은 설치 스크립트가 만들지만 **비어 있고 아무도 안 읽는다**.

**로컬 게이트 현황**: `static_checks.sh` → `STATIC_CHECKS_OK` · pytest 2512개 수집 ·
vitest 172파일 · 번들 신선도 OK · playwright 1.62.0 + chromium 설치됨 · node 24 / npm 11.

**배포 절차**: `docs/MAINTENANCE_PLAYBOOK.md` §2 (번들 경로). 순서 불변 — 백엔드(CSP·마이그레이션·
라우터) 먼저, 프런트 번들 나중. `upgrade-clovirone-web-assistant.sh`가 그 순서로 한다.

---

## 6. 이 문서를 갱신하는 시점

의미 있는 조사·작업 단위가 끝날 때. 작은 코드 수정 하나마다 기록하지 않는다.
- 새 문제 발견 → [BACKLOG.md](BACKLOG.md)
- 새 Route/기능 검증 → [QA_COVERAGE.md](QA_COVERAGE.md)
- 중요한 설계 판단 → [DECISIONS.md](DECISIONS.md)
- 사이클 종료 → 이 문서 + [BUILD_LOG.md](BUILD_LOG.md)
