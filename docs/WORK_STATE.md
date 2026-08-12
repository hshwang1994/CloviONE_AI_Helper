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

**마지막 갱신**: 2026-08-12 · **단계**: WF11(제품 BACKLOG 재개 — SEC-12/13 문서 정정 +
`USE-01` 휴지통 왕복 + `QA-02` smoke 스위트 신설로 종결) 완료. 그 앞의 WF10-0(Continuity Bootstrap, D-64) →
WF10-1(Supervisor runtime contract 확정, D-65)와 WF9-0(D-63) → WF9-1(`SEC-10` 부분) →
WF9-2(`ADM-02R`) → WF9-3(`AI-62`), WF8(12건 + 전체 회귀 green)은 그대로 유효하다.

**WF11(2026-08-12) — 제품 BACKLOG 재개, WF9-3 "다음 후보" 중 자기완결 2건 종결.**
비대화형 무인 실행 재개 시작 시 예산이 제한적(세션 USD 예산)이라 값비싼 다중 에이전트
Workflow 대신 직접 조사·구현으로 진행 — 저장소 상태(CLAUDE.md·WORK_STATE·BACKLOG·
QA_COVERAGE·DECISIONS·git log) 재확인 후 WF9-3이 남긴 후보 중 값싸고 확실한 것부터.

- **`SEC-12`/`SEC-13`(문서 자기모순 정정, 코드 변경 없음)**: BACKLOG 원 행(§2542-2543)은
  아직 "발견"인데, 같은 파일 뒤쪽 "정밀화" 절(§2556-2591, 2026-08-11 작성)은 이미 코드
  확인까지 마치고 "표 낡음 — 이미 코드에 있다"고 적어 뒀다 — WF8-3이 잡았던 것과 같은
  자기모순 패턴이 한 번 더 있었다. 문서만 보고 믿지 않고 `app/home/readers.py`
  (`recent_documents(viewer=...)`→`doc_in_scope`, `recent_board_posts(org_id=...)`→
  `list_posts`)와 `app/home/service.py:127-128`(실제 호출부가 `viewer=user`/`org_id`를
  넘기는지)를 직접 읽어 실제로 배선돼 있음을 재확인하고, 전용 회귀 시험
  `tests/security/test_home_widget_org_dept_scope.py`(5건: 조직 필터링·대조군·부서
  필터링·대조군·limit 뒤 필터링) 재실행으로 green 확인. 두 행을 "구현완료(행 정정)"로
  갱신 — 새 코드는 필요 없었다.
- **`USE-01` 마지막 항목(휴지통 실제 왕복) 구현완료**: 2026-08-11 WF7 후속이 "새 문서
  생성은 Notion 쓰기 위험, 기존 실문서를 잠시 trash하는 것도 실고객 화면에 순간 영향"
  이라며 보류해 둔 항목. `app/trash/service.py`를 직접 읽어 `move_to_trash`/`restore`가
  **Notion을 전혀 호출하지 않음**(docstring부터 "노션은 손대지 않는다", archive 호출은
  `purge`에만 있음)을 재확인해 세 번째 선택지를 찾았다 — 완전히 합성된 문서 1행
  (`notion_page_id="qa-trash-axis-e2e-doc-1"`, 실동기화를 거치지 않은 가짜 행)을 로컬
  dev `document_cache`에 직접 심어 실고객 데이터·다른 사람 화면과 완전히 무관하게
  왕복시켰다. 로컬 dev 서버(`var/web.sqlite3`, uvicorn `:8099`) 기동 + 기존 QA 계정
  (`qa-use-axis-admin`) 비밀번호 재설정 후 신규 도구 `scripts/ui_qa/trash_axis_e2e.py`
  실행 — 실제 HTTP 응답으로 확인: `GET 상세` 200 → `POST /trash` 200/ok → `GET 상세`
  **404**(H2 규칙) → `GET /api/trash` 목록에 등장 → `POST /restore` 200/ok → `GET 상세`
  다시 200(제목 원문 그대로) → 목록에서 사라짐 → 감사 로그 `team_docs.trash`/
  `trash.restore` 둘 다 이 문서의 `object_id`로 기록됨. 종료 후 합성 행을 지우고 **별도
  DB 조회로**(스크립트 자기 보고가 아니라) `document_cache`/`trash_items` 양쪽에 잔여
  없음을 재확인. `USE-01`의 12개 중 9개가 이제 실행 확인 완료 — 남은 3개(문서 생성·
  스케줄·주간 리포트)는 `DGEN-02`/D-21로 원인이 이미 규명된 의도적 보류뿐이다.
- **`QA-02`(High) 구현완료**: `tests/smoke/`가 저장소 생성 이래 **한 번도 내용이 없던**
  빈 디렉터리라(`git log`로 확인) `pytest.ini`의 `-m "not smoke"`가 애초에 거를 대상이
  없었다 — "실브라우저 E2E가 수행된 적 없다"는 지적이 문자 그대로 맞았다(다만 §12
  QAH 하네스·`scripts/ui_qa/*` 전수 스크립트들은 이미 실브라우저 E2E를 폭넓게 해 왔다는
  점과는 구분해야 한다 — 그 도구들은 pytest 마커 체계 밖의 별도 도구다). `tests/smoke/
  conftest.py`(살아있는 서버 확인 후 skip/browser/qa_session fixture) +
  `test_golden_path.py`(3건: 사용자 콘솔 홈·관리자 콘솔 대시보드·문서 목록, 콘솔 오류·
  4xx/5xx 네트워크 응답 실측 수집) 신설. 로컬 dev(`:8099`) 대상 3건 green, 서버 미기동
  대상 3건 전부 skip(에러 아님) 확인, 기본 `pytest`(마커 미지정)는 여전히 3건 deselect
  확인 — 구현 도중 실제 버그 하나를 잡았다: 테스트 함수 안에서 `sync_playwright()`를
  또 열면(conftest의 세션 fixture가 이미 하나 열어 둔 상태라) "Sync API inside the
  asyncio loop"로 죽는다 — 세션 fixture가 준 `browser`를 재사용하도록 고쳐 해결.
  `README.md`에 실행 예시 추가, `KNOWN_LIMITATIONS.md` §7 갱신.

**검증**: `tests/security/test_home_widget_org_dept_scope.py`(5건) green. 휴지통·smoke는
전용 도구로 실제 로컬 서버 대상 검증(`dist/trash-axis-e2e/trash_axis.json` +
`pytest tests/smoke -m smoke` 3건 green + skip 경로 확인). `bash scripts/static_checks.sh`
→ `STATIC_CHECKS_OK`, `pytest --collect-only`로 전체 스위트가 smoke 3건을 정상
deselect하며 깨짐 없이 수집됨을 확인. `app/` 자체는 이번 배치에서 손대지 않아(문서·
QA 도구·pytest smoke 인프라만 추가) 기존 회귀 스위트를 다시 돌릴 필요는 없다고 판단.
로컬 dev 서버는 이 배치가 끝날 때까지 계속 띄워 둔다(다음 작업에서도 재사용 가능하면
그대로 씀 — CLAUDE.md 지시).

**이 invocation은 세션 USD 예산 소진(약 70% 소비, 자세한 값은 harness system-reminder
참고)으로 여기서 멈춘다 — PROJECT는 끝나지 않았다.** §0 원칙대로 이것은 정지 사유가
아니다: 다음 invocation(로컬 Supervisor가 즉시 이어받거나, 사람이 다시 시작)은 아래를
바로 실행하면 된다.
- **로컬 dev 서버가 이미 떠 있다** — uvicorn `http://127.0.0.1:8099`(`--factory
  app.main:create_app`, `.env` 기준 `var/web.sqlite3`). `curl -s localhost:8099/readyz`로
  살아있는지 먼저 확인하고, 살아있으면 재기동하지 말고 그대로 쓴다. QA 계정
  `qa-use-axis-admin@goodmit.co.kr`(system_admin)의 로컬 비밀번호를 이번에
  `LocalQaTrash-2026-08!`로 재설정했다(다음 세션이 원하면 이 값으로 바로 로그인 가능 —
  로컬 전용 계정이라 credential 규정 §3-4 대상 아님, 실서버·실 사용자 계정과 무관).
- **다음 후보(WF9-3 목록에서 남은 것 + 이번에 새로 확인된 것)**: `QA_COVERAGE.md`
  `L`축(화면 간 반영) 전수 매트릭스 — 아직 `CROSS_SCREEN_KEYS` 6개 매핑만 시험이 있고
  전체 화면 쌍을 훑은 적은 없다(§11 표) · BACKLOG 나머지 Med/Low 항목 Root Cause
  클러스터링(이번에 "SEC-12/13류 자기모순 재검증" 패턴을 훑었지만 그 외 새 후보는 못
  찾음 — 다음 세션은 다른 각도로, 예를 들어 "구현완료인데 실서버 미배포로 남은 항목"
  재고를 시도해볼 만하다) · `DS-18` 남은 34개 합성 토큰(시각 회귀 확인 필요) ·
  Admin IA 나머지(`IA-04`, 전용 다사이클 이니셔티브, 이번 범위 아님) · 승인된 TEST
  SERVER(`10.100.64.X`) 배포 — 자격증명 없음이 여전히 외부 Blocker다(CLAUDE.md §4).
  `AI-01/02/05~29` 등 AI 심화 아키텍처는 계속 의도적 보류(전담 설계 세션 필요, quick
  patch로 건드리지 않는다).

**WF10-0(2026-08-12) — Continuity Bootstrap 완료(D-64). 제품 구현은 하지 않은 세션이다.**
증상은 제품 품질이 아니라 실행 구조였다: `PROJECT_COMPLETE=false`인데 Worker가 Summary를 내고
끝났고, 그 뒤 다음 invocation이 이어지지 않았다. 이번에 넣은 것:
- **Stop hook 보조 제동** — `scripts/runner/stop_guard.py` + `.claude/settings.json`.
  Supervisor가 띄운 Worker에서만(`CLOVIR_SUPERVISED=1`) 동작하고, 완료 마커가 유효하지 않으면
  invocation당 **한 번** block한다. `stop_hook_active`면 통과시켜 무한 루프를 만들지 않는다.
  사람의 대화형 세션에는 영향이 없다(실측 확인). 어떤 예외에서도 정지를 허용한다(fail-open).
- **Primary continuity는 여전히 로컬 PowerShell Supervisor**(`autonomous_runner.ps1`).
  Stop hook은 보조 장치일 뿐이다. **Windows Task Scheduler 의존 없음**(현재 해당 task 미등록 확인).
- **Persistent Worker Session**(`--resume`)을 실제 프로세스 경계에서 재검증 — 2번째 프로세스가
  1번째의 대화를 기억함(`SEEN=3`).
- **실제로 발견해 고친 continuity 결함**: ① `app/worker_main.py`의 CRLF/LF 유령 dirty 상태 때문에
  Supervisor가 Claude를 한 번도 못 띄우고 무한 대기하던 문제(파일 정규화 + dirty 대기 상한),
  ② `Wait-Process -PassThru`로는 timeout이 절대 감지되지 않아 강제 종료 분기가 죽은 코드였던 문제,
  ③ 런어웨이 상한에서 "스케줄러가 이어받는다"는 거짓 안내, ④ 같은 초 로그 파일 덮어쓰기.
- **`STOP`(사용자 전용)과 `AUTO_STOP`(자동 실패 흔적) 분리** — stale 흔적이 수동 재시작을 조용히
  무력화하던 문제 제거. 단일 Writer 잠금은 배타 파일 핸들 방식으로 교체.
- Controlled test A~H를 격리 scratch 저장소에서 **실제 스크립트**로 실행해 통과(근거는 D-64).

**WF10-1(2026-08-12) — Supervisor runtime contract 확정(D-65). 역시 제품 구현은 없다.**
장기 실행 시작 직전에 Worker 품질과 종료 조건이 우연에 좌우되던 구멍 둘을 닫았다.
- **Worker 품질 고정**: 매 invocation에 `--model sonnet --effort max`를 명시한다(새 세션·`--resume`
  모두). 안 넘기면 사용자 `settings.json`의 `effortLevel: high`가 그대로 적용되는 것을 실측했고,
  넘기면 `max`로 확정되는 것을 Stop hook 입력의 `effort.level`로 직접 관측했다. 모델은 응답
  JSON의 `canonicalModel=claude-sonnet-5`로 확인. `runner.log`에 requested/actual을 남긴다.
  설치 CLI가 허용하는 effort는 `low|medium|high|xhigh|max`뿐 — `ultracode`/`ultrathink`는 effort가
  아니며 `ValidateSet`으로 오입력을 막았다.
- **invocation 횟수는 종료 조건이 아니다**: `$MaxIterationsPerLaunch` 기본값 300 → **0(무제한)**.
  양수는 controlled test 전용. 무제한 기동으로 23회 연속 invocation(전부 exit 0) 후 외부 STOP으로만
  종료되는 것을 실측했다. `--max-budget-usd`는 15 그대로(요청 없이 바꾸지 않음).

**다음**: 사용자가 로컬 PowerShell에서 `scripts\runner\autonomous_runner.ps1`을 한 번 시작하면,
그 Supervisor가 `PROJECT_COMPLETE`까지 Worker invocation을 계속 관리한다. 제품 작업 재개 지점은
아래 "다음 후보(WF9 시점 갱신)" 그대로다.

**WF9-3(2026-08-12) — `AI-62`(High) 구현완료: 티켓이 잘려도 모델이 안 밝히면 사용자는
몰랐다.** 시스템 프롬프트가 `tickets_truncated`일 때 총계를 단정하지 말라고 이미 모델에게
지시하지만(`assistant.py` QUERY_PROMPT), 그 지시를 실제로 따르는지는 매 답변마다 다르다 —
AI-31류(프롬프트 지시만으로는 순응이 보장되지 않는다)와 같은 실패 계열이다. `claude_query()`
에 결정적 게이트를 추가: 실제로 800건 컷에 걸렸고(`tickets_truncated`) 업무 질문
(`is_query_intent()` — AI-60에서 이미 검증된 기존 분류기를 그대로 재사용, 새 휴리스틱
안 만듦)이면 모델이 언급했든 안 했든 안내 문구를 답변에 결정적으로 덧붙인다. 진행률·개수
질문은 특정 티켓을 안 짚어 `ticket_ids`가 비어 있을 수 있으므로 `ref_tickets` 유무가 아니라
`is_query_intent`로 판단(AI-62가 지목한 바로 그 케이스를 놓치지 않기 위함). 잡담에는 안
붙여, 워크스페이스가 800건 넘게 큰 설치에서 모든 대화가 안내문으로 오염되지 않게 했다.

`test_assistant.py` 신규 3건(① 모델이 안 밝혀도 결정적으로 붙음 ② 안 잘렸으면 안 붙음
③ 잡담엔 안 붙음), revert-to-verify(안내 문구 삽입 줄만 제거 → ①만 정확히 그 증상으로
실패 확인 후 복원). 러너 전체 스위트 291건 green(신규 3건 포함, 이전 258건에서 증가).
`app/`·`frontend/`는 손대지 않아 `STATIC_CHECKS_OK`만 재확인(밴드 문자 없음, 번들 무관).

**다음 후보(WF9 시점 갱신)**: `SEC-10`은 ①(앱 측 열람 제한)만 구현완료, **②(Notion 원본
자격증명 제거·회전)는 여전히 사용자 직접 조치 필요** — 다음 세션이 사용자 확인 없이는
닫을 수 없다. 남은 BACKLOG 재고: `QA-02`(실브라우저 E2E 0회) · `USE-01`(자동화 실행이력,
WF7-U축에서 상당 부분 처리됐다는 이전 기록은 재검증 없이 믿지 말 것) · `SEC-12`/`SEC-13`
(Med로 낮춰졌지만 아직 `발견` 상태로 남아 있는지 재확인 필요) · `QA_COVERAGE` L축(화면 간
반영) 전수 매트릭스 · 나머지 Med/Low Root Cause 클러스터링. AI 도우미 심화 아키텍처
항목(`AI-01/02/05~29` 등, 스트리밍·중단·도구사용·컨텍스트 한계)은 여러 사이클째 의도적
보류 — 전담 설계 세션 없이 quick patch로 건드리지 않는다.

**WF9-2(2026-08-12) — `ADM-02R`(Med) 구현완료: `/setup` 체크리스트에 메일 항목 추가.**
`ADM-02`(High, "메일이 없어서 CLI로 임시 비밀번호를 전달하는 흐름이 굳어졌다")는 §1812
"ADM-02 정정"에서 이미 근거가 약함이 밝혀져 있었다 — 관리자 재설정은 메일과 무관하게
화면만으로 완결되고, 자가 재설정은 `mail_is_sendable()`로 스스로 확인해 안 되는 버튼을
숨긴다(제품이 메일 부재를 이미 정직하게 다룸). 살아남은 유일한 문제(`ADM-02R`, Med)만
구현: `app/setup/steps.py`에 `mail` 항목(`admin_account` 다음, `user_visible=False`) +
`app/setup/probes.py::probe_mail`이 비밀번호 재설정 화면이 이미 쓰는
`app/mail/config.py::configuration_problems`를 그대로 재사용(새 판정 안 만듦, 모듈
docstring 원칙 준수). `SetupWizard.jsx`에 설정 화면 딥링크 추가.

신규 테스트 5건 + `EXPECTED_ORDER` 갱신 + 기존 2건을 새 순서(`mail`이 이제
`organization`보다 앞)에 맞게 수정, revert-to-verify(`PROBES`에서 등록 제거 →
35건 연쇄 실패로 실제 wiring 확인 후 복원). 관련 스위트(`test_mail_delivery`·
`test_password_reset`·`test_admin_backlog`) + 프런트 `setup-wizard.test.jsx`(12건) green,
`STATIC_CHECKS_OK`(도중 새 텍스트의 가운뎃점 위반 1건 발견해 정리), 번들 재빌드 반영.
BACKLOG의 `ADM-02` 원 행도 "정정"으로 인라인 갱신(원래 High가 근거 약해 철회된 사실을
그 행 자체에도 남김 — WF8의 ADM-01류 자기모순 정정과 같은 이유).

**WF9-1(2026-08-12) — `SEC-10`(High) 부분 구현완료: 문서 단위 열람 제한.** BACKLOG 전체
재고에서 아직 남은 High 중 유일한 **Security/DataLoss급**(Notion 문서 1건의 평문 자격증명을
인증된 사용자 전원이 볼 수 있음)을 최우선 처리. 원본(실고객 워크스페이스)은 여러 handoff
문서(`SONNET_HANDOFF.md` 등)에 걸쳐 이미 "사용자에게 알려야 할 항목"으로 반복 기록돼 있어
다시 적지 않고, 앱이 실제로 할 수 있는 ①(문서 단위 열람 범위)을 구현했다: `document_cache.
restricted`(마이그레이션 `0057`, `classification_manual`과 같은 이유로 `sync._upsert`가
건드리지 않아 재동기화로 안 풀림) + `doc_in_scope`가 부서 범위 판정보다 **먼저** 보는 게이트
(운영자군/작성자 본인 외에는 같은 부서 동료라도 예외 없이 차단) + `POST /api/team-docs/
{id}/restrict`(운영자만, `get_doc_in_scope` 선통과라 범위 밖은 404) + `TeamDoc.jsx`
배지·Callout·토글 버튼 + `TeamDocs.jsx` 카드/표 🔒 표시.

조사 중 부수 발견 하나를 같이 닫았다: `service.recent_documents()`("최근 열람")가 처음부터
`doc_in_scope`를 전혀 안 거쳐, 부서가 바뀌거나 문서가 나중에 restricted가 돼도 **예전에
한 번 연 사람에게는 계속 보이는** 별도 유출 경로였다 — SEC-10 제한 기능 자체를 무의미하게
만들 수 있는 구멍이라 `viewer` 인자를 추가해 같이 막았다.

신규 테스트 `tests/security/test_document_restricted_scope.py`(11건, 같은 부서 차단·작성자/
운영자 예외·토글 권한 3-way·범위 밖 404·최근 열람 우회 포함) + `teamdoc.test.jsx`/
`teamdocs-view.test.jsx` 확장(4건) + revert-to-verify(제한 게이트를 임시로 빼서 3건이 정확히
그 증상으로 실패하는 것을 확인 후 복원). 관련 스위트(`test_document_scope`·
`test_team_docs_write_scope`·`test_team_docs_filter_scope`·`test_document_author_identity`·
`test_team_docs_api`·`test_document_comments`·`test_document_edit`·`test_team_docs_sync`·
`test_document_comment_survives_resync`, 총 104건) + 프런트 전체(220파일/1498건) green,
번들 재빌드 반영.

**부분 구현인 이유**: ②(원본에서 제거·회전)는 여전히 사용자가 실제 Notion 워크스페이스에서
직접 해야 한다 — 미확인 상태로 남는다. 이 기능은 어느 문서가 새는지 자동으로 찾아내지
않는다(본문 스캔은 범위 밖) — 관리자가 문서를 특정한 뒤 상세 화면에서 수동으로 제한을 켜야
한다. **사용자 확인 필요**: 예전에 특정된 그 1건(`document_cache` 107건 중 1건, 접속 URL·
계정·비밀번호 포함)을 실제로 열어 지금 당장 `열람 제한`을 켜고, Notion 원본에서 자격증명을
제거·회전해야 한다.

**WF9-0(2026-08-12) — Runner Supervisor를 Persistent Worker Session으로 재설계(D-63).**
사용자가 "직전 실행이 Session Summary만 남기고 끝났는데 다음 invocation이 이어받지 않았다"고
지적하며 `autonomous_runner.ps1`을 매 반복 새 세션이 아니라 **같은 Worker Session을
`--resume`으로 계속 이어받도록** 재설계하라고 명시적으로 지시(D-61이 "이번 지시는 이 설계를
바꾸라고 하지 않았다"며 유지했던 그 설계를 이번엔 명시적으로 바꾸라는 지시).

먼저 실제 원인을 추측 없이 로그/커밋으로 재구성했다: `var/runner/STOP`이 2026-08-11
08:59에 3연속 실패로 자동 생성돼 있었고, 원인(`--oneline` 오인식, Start-Process 인자
재조립 버그)은 **같은 날 21:40 커밋 `12b81fe`로 이미 고쳐진 뒤**였다 — 즉 그 STOP은 이미
해결된 버그의 흔적일 뿐이었는데, 아무도 지우고 재시작하지 않아 15분 heartbeat가
2026-08-11 21:24까지 "STOP 발견 — 종료"만 계속 찍다가 그 뒤로 방치돼 있었다(하루 넘게
아무 Supervisor도 안 돈 상태 — 이번 지적의 "연속 실행 안 됨"은 로직 결함이 아니라
아무도 재시작하지 않은 방치였다는 뜻).

**구현**: `scripts/runner/autonomous_runner.ps1`에 `var/runner/session_id.txt` 저장
session_id를 도입 — 있으면 `--resume <id>`, 없으면(최초/이전 resume 실패) `--session-id
<새 GUID>`로 시작하고 즉시 파일에 저장. resume 실패(exit!=0 + stderr에 `No conversation
found with session ID`)는 연속실패 카운터를 안 올리고 즉시 새 세션으로 넘어간다.
`docs/*.md`+git을 매 반복 다시 확인하라는 프롬프트 지시는 유지(대화 기억보다 저장소
실제 상태 우선).

**Controlled test(실제 API 호출, 프로덕션과 동일한 Start-Process 호출 경로, 격리 환경 —
실저장소·이 대화형 세션과 분리)**: (1) 원시 CLI로 `--session-id`→`--resume` 왕복 시
코드워드가 실제로 이어짐을 증명(`result:"PINEAPPLE42"`). (2) 없는 세션 ID로 `--resume`
시 시그니처 확인(exit=1, stderr=`No conversation found with session ID: ...`). (3)
프로덕션과 동일한 Start-Process+파일 리다이렉트 경로로 재현 — 이 과정에서 테스트
스크립트 자체에 `--tools ""`(빈 문자열 배열 요소)를 넣었을 때 세션이 엉뚱하게 붙는
오류를 실제로 재현했고(Windows Start-Process 인자 재조립 함정, `--oneline` 버그와 같은
계열), 제거하자 정상화됨을 확인(`result:"KIWI-9917"` 정확히 일치) — 이 자체가
revert-to-verify. 근거는 `docs/DECISIONS.md` D-63에 로그 원문과 함께 기록.

근거가 확인된 뒤 `var/runner/STOP`을 해제하고 `state.json.consecutiveFailures`를 0으로
되돌렸다(사유를 `runner.log`에 남김). **이 대화형 세션이 여전히 활성 Writer이므로 실제
`autonomous_runner.ps1` while 루프는 기동하지 않았다** — 단일 Writer 원칙(이번 지시 §6/§8)
때문에, 검증은 격리된 스크래치 환경에서만 했다. 상시 가동은 이 세션이 끝난 뒤 사용자가
`autonomous_runner.ps1`을 수동 시작하는 것이 여전히 주 경로(D-61 원칙 유지, 이유는
"두 Writer 동시 실행 방지"이지 로컬 Runner가 부차적이라서가 아님). 기존 Task Scheduler
watchdog(`install_task.ps1`)은 건드리지 않았다(신규 생성 금지, 기존 삭제는 사용자 몫).

이 보정 자체는 완료 조건이 아니다 — 곧바로 아래 WF8 이후 남은 BACKLOG/QA_COVERAGE
작업으로 계속한다.

**새 세션 시작(2026-08-11) — 상태 복원 + Runner Supervisor 재확인.** 이전 대화 기억 없이
CLAUDE.md·WORK_STATE·BACKLOG·QA_COVERAGE·DECISIONS·Git을 교차 대조해 복원했다.
`autonomous_runner.ps1`(D-60/D-61)은 이미 실제 코드로 stdin 리다이렉트 수정이 들어가 있고
DECISIONS.md에 controlled test 증거(타임스탬프 로그, 두 인스턴스 동시 실행 방지, STOP 처리)가
남아 있음을 코드 직접 재확인으로 검증함 — 재작업 불필요. 이 세션이 활성 상태이므로
`var/runner/STOP`은 D-61 원칙대로 그대로 둔다(단일 인스턴스 보호, 두 Supervisor가 동시에
같은 워킹트리를 건드리면 안 됨).

**WF8-1 — `AI-60`(Critical)/`AI-61`(High) 구현완료.** BACKLOG 전체 unresolved inventory(154건
`발견` 상태)를 훑어 Critical 1건(AI-60: "모르는 질문에 184건입니다라고 확답")을 최우선 처리.
`runner/claude-work-assistant/assistant.py`의 `is_query_intent`/`query_markers`는 이미 3번
회귀한 이력이 있어(AI-31 기록) 직접 손대지 않고, `route_request` 맨 앞단에 새 게이트
`is_out_of_domain_query()`를 추가 — 이 러너가 데이터를 아예 갖지 않는 플랫폼 도메인(백그라운드
작업 큐·채팅방, AI-61이 예로 든 두 가지)을 가리키는 낱말이 있고 "티켓"/"프로젝트"가 함께
언급되지 않았으면 조회 분류 이전에 정직한 `unsupported_response()`로 답한다. 재현 시나리오
("지금 실패한 백그라운드 작업이 몇 건이야?" → 수정 전 `TICKET_COUNT`, 수정 후 `UNSUPPORTED`)
+ pending CREATE 초안 보존까지 회귀 테스트 2건 신규, **revert-to-verify 2단계로 확인**(①
함수 자체 제거 시 AttributeError ② wiring만 제거 시 실제로 `TICKET_COUNT`(184건 재현) 확인
후 복원). 러너 전체 스위트 288건 green.

**WF8-2 — `ADM-03R`(High) 부분구현.** "제품이 스스로 SSH 트래픽을 만든다"(계정 잠금 알림에
자동 해제 사실이 없어 관리자가 매번 CLI로 풂) 중 ②(관리자 알림 본문)를 고쳤다 —
`app/auth/router.py`의 `account_locked` 관리자 알림에 분 단위 자동 해제 ETA + "기다려도 된다"
안내 추가. `test_account_lock_notifies_admins`에 회귀 검증 추가, revert-to-verify 확인.
①(잠금 정책 2개를 설정 화면에 노출)은 `ADM-05`와 겹치는 별도 설계 판단(env 설정을 DB
레지스트리로 옮길지 읽기전용 표시만 할지)이 필요해 이번 범위에서 뺐다 — BACKLOG에 사유 기록.

**WF8-3 — BACKLOG 문서 자기모순 정정(코드 변경 없음).** `ADM-01`·`NOTI-04`·`NOTI-05`·`ADM-01R`
네 행이 원래 있던 자리(§1457·1529-1530·1830)에는 "발견"만 있고, 같은 파일 뒤쪽 `WF3 재검증`
절(§2687-2736, 2026-08-09 작성)에는 이미 이 넷이 철회/정정/구현완료로 처리돼 있었다 — 즉
문서가 자기 자신과 모순된 상태로 방치돼 있었다(상단 경고 배너에는 나열돼 있었지만 각 행
자체엔 정정 내용이 없어 배너를 못 보고 그 행만 검색하면 낡은 "발견"을 그대로 믿게 됨). 네 행에
정정 내용을 인라인으로 채워 넣었다: `ADM-01`(결론 철회 — CLI 집계가 조사 자신의 QA 계정 생성
흔적으로 오염돼 있었다) · `NOTI-04`(103건 중 3건→94/97로 정정, 철회) · `NOTI-05`(전제였던
"91% 갈 곳 없음"이 무효화, `NOTI-04R`이 이미 더 나은 방식으로 구현완료) · `ADM-01R`(같은 사유로
철회, 하위 `ADM-03R`/`ADM-06R`은 독립 결함으로는 유효).

**WF8-4 — `SRCH-01`(High) 구현완료.** 명령 팔레트(Ctrl+K)가 사이드바와 같은 `nav`(현재
콘솔 하나)만 검색해, 관리자군이 사용자 콘솔(`/me`)에 있는 동안엔 관리자 화면을 팔레트로
못 찾았다(팔레트의 존재 이유를 정면으로 부정). `App.jsx`가 두 콘솔 전체를 합친 `paletteNav`
prop을 추가로 넘기고, `AppShell.jsx`는 `filterNavByRole()` 공유 헬퍼로 사이드바(`groups`,
현재 콘솔)와 팔레트(`paletteGroups`, `paletteNav||nav`)를 분리 — role 필터는 그대로 공유해
RBAC는 그대로 적용된다. `command-palette-cross-console.test.jsx` 신규 3건 + 관련 8파일
39건 green, revert-to-verify(AppShell/App.jsx stash 후 실패 재현 확인 후 복원).

**WF8-5 — `RSTR-03`(High) 구현완료.** 예약 백업이 20일째 안 도는데(기본값이 꺼짐) 아무도
몰랐다 — `announce_backup_failure`는 백업을 "시도했다가 실패"할 때만 켜져, 애초에 안 도는
것은 알림이 한 번도 안 났다. `app/backups/service.py`에 `backup_health_alert_reason()`
(꺼짐/한번도성공못함/`BACKUP_STALE_ALERT_DAYS`=7일+정체) + `check_backup_health()` 신설,
기존 10분 백업 틱(`worker_main.py`)에 배선. `runner_unavailable`이 쓰는 "나쁜 상태 전환 시
1회" 원칙을 전용 상태 컬럼이 없어 "최근 24시간 안에 같은 유형 관리자 알림이 있으면 건너뜀"
(Notification 테이블 자체를 정본으로)으로 구현. 신규 6건 + revert-to-verify, 관련 41건 green.

**WF8-6 — `SCHD-01`(High) 구현완료.** 유일한 스케줄이 채팅 전용 웹훅(`CHAT_WORKFLOW_NAME`)을
대상으로 삼고 있었다 — 활성화하면 실고객 Notion 워크스페이스에 의도치 않은 쓰기로 이어질
위험(D-21). `app/schedules/router.py`에 `_assert_safe_workflow_target()` 신설(기존
"승인필요 write 워크플로 거부" 검사와 통합) — create·update·**enable** 세 경로 전부에서
차단(enable에도 넣은 이유: 이 검사가 생기기 전에 정의된 스케줄이 정의를 안 고치고 활성화만
으로 새어나갈 수 있어서). **실서버에 이미 있을 수 있는 미스컨픽 행 자체는 D-21 경계상 이
세션에서 직접 안 건드렸다** — 코드 예방책만 넣고 실데이터 정정은 배포 담당자 몫으로 남김
(`DECISIONS.md` D-62). 신규 5건 + revert-to-verify, 관련 45건 green.

**WF8-7 — `USE-02`(High) 재확인·부분해소.** "잡 2종만 돈다 + notion_mapping_sync가 등록
안 된 job_type 오류 이력" — `build_handlers()`를 직접 읽어 확인하니 **지금은 정상 등록**돼
있다(과거 배포 창의 이력으로 추정, 정확한 시점은 확정 못 함). 코드 결함이 없어 "고칠 것"은
없지만, 이 결함 부류(잡을 큐에 넣는 코드와 핸들러 등록 코드가 다른 파일이라 한쪽만 고쳐도
컴파일·기동은 성공하는 조용한 실패)가 재발하지 않게 `tests/regression/
test_job_handler_registration_complete.py` 신설 — 실제 enqueue 7개 호출부의 job_type을
원본 상수에서 가져와 `build_handlers()` 키 집합과 대조. revert-to-verify(등록 제거 시
과거와 똑같은 증상 재현 확인 후 복원).

**WF8-8 — `UA-20R`(High) 구현완료.** 부서 삭제 확인 문구("되돌릴 수 없습니다")가 하위 부서
수를 안 말했다 — `parent_id`는 `ondelete="SET NULL"`이라 데이터 유실은 아니지만(자식은
최상위로 승격), 3단 트리가 클릭 한 번에 평탄해지는 걸 사전에 몰랐다. 조직 정지 확인문과
같은 원칙(차단하지 않고 영향받는 수를 명시)으로, `app/org/service.py`에
`bulk_child_department_count()` 신설(부서 전용), `item_view()`가 `child_department_count`를
실어 주고 프런트 `org.js` 삭제 confirm을 동적 함수로 교체. 신규 4건 + revert-to-verify,
관련 63건 green. (참고: 이 동적 confirm 함수 자체를 누르는 UI 상호작용 시험은 조직 정지
포함 이 저장소에 아직 없다는 기존 공백은 정직하게 남김.)

**WF8-9 — `ADM-06R`(Low) 구현완료.** "지금 잠긴 사람만 보기" 필터가 `/users`에 없었다(배지·
상세·잠금해제 버튼은 이미 다 있었음). `_filtered_users_stmt()`에 `locked`/`now` 매개변수
추가 — `_user_row`가 이미 쓰는 판정식(`locked_until and locked_until > now`)과 통일해
배지와 필터 결과가 어긋나지 않게 했다. `list_users`·`export_users_csv`가 같은 문장을
공유하므로 CSV 내보내기도 자동으로 따라옴. 프런트 `Users.jsx`에 "잠김" select 필터 신설.
신규 2건(실제 로그인 실패로 잠금 재현 + CSV) + revert-to-verify, 관련 23건 green.

**WF8-10 — `NOTI-03`(Low) 재조사로 확대, 6건 구현완료.** 원 서술(`chat_invited`가 레지스트리에
없다)은 낡았다 — 이미 등록돼 있었다. 재조사(실제 `type_=` 호출부 전수 대조)로 **같은 결함
부류가 여섯 건 더** 있음을 새로 발견: `approval_delegated`·`approval_overdue`·
`board_comment`·`document_comment`·`idea_status_changed`·`ticket_comment`가 실제로 알림을
만드는데 `NOTIFICATION_TYPES`(뮤트 가능 레지스트리)에 없어 사용자가 절대 못 껐다(`parse_muted`
가 "모르는 키"로 조용히 버림). 6종 등록 + `tests/unit/test_profile_prefs.py`에 **상시
완결성 가드** 신설(app/ 전체 `type_="literal"` 정적 스캔, 상수 기반 호출부는 스캔 한계로
못 잡는다는 것도 정직하게 주석에 남김). revert-to-verify(6종 전부 재현 확인 후 복원),
관련 166건 green.

**WF8-11 — `DOC-01`(Med) 구현완료(코드 변경 없음).** `CLAUDE.md`·`docs/SECURITY.md` 둘 다
CSP를 예전 `script-src 'self'` 정책으로 서술하고 있었다(2026-08-04 사용자 지시로 완화된
지 오래) — `SECURITY.md`는 "인라인 JS/CSS는 어디에도 없다"까지 지금은 틀린 문장이었다.
둘 다 `app/core/middleware.py`의 `CSP_POLICY`를 정본으로 가리키게 정정, 실제 헤더값·잃은
방어·유지하는 방어를 정직하게 적었다. 기존 `tests/regression/test_csp_policy.py`로 서술이
실제 응답과 일치함을 재확인.

**WF8-12 — `ADM-05`(Med) 구현완료, `ADM-03R`이 미룬 나머지 절반.** 잠금 정책
(`login_max_failures`/`login_lock_seconds`)이 env 전용이라 화면에서 볼 수도 바꿀 수도
없었다. `app/core/sessions.py::SessionService`가 이미 쓰는 "env 기본값 + DB override"
모양(`session_policy`와 같은 패턴)을 그대로 따라 `lockout_policy` 설정 신설 —
`app/settings/registry.py`에 `SettingSpec`+검증기, `app/auth/router.py`에
`_effective_lockout_policy()` 리졸버(다음 로그인 시도부터 즉시 적용). 설정 화면에
구조화 편집기(분 단위 잠금시간 + 실패 임계값, `session_policy`와 같은 UX) + 완화 시
보안 경고. 신규 3건(설정값이 실제 로그인 잠금에 즉시 반영 + 미설정 시 env 폴백 + 범위
검증) + revert-to-verify, 관련 49건 green.

**정적 검사 회귀 2건 수정(코드 아님, 문구).** 배치 마무리 전 `bash scripts/static_checks.sh`를
돌리자 `USER_TEXT_FAILED`(화면 문구 금지 문자 가운뎃점 ·) 2건이 잡혔다 — 하나는 이번 배치가
새로 만든 것(`lockout_policy` 설명), 하나는 **이 세션과 무관한 기존 커밋(RG-07,
`frontend/src/screens/registry/actions.js`)이 이미 갖고 있던 위반**인데 그 뒤로 정적 검사를
안 돌려 아무도 못 잡았던 것 — 둘 다 다른 표현으로 정리. `BUNDLE_FRESH_OK`도 실패(프런트
소스가 커밋된 번들보다 새로움, 이 배치의 프런트 변경 다수가 재빌드 전이었다) — `npm run
build` + `check_bundle_fresh.py --write`로 해소.

**검증(WF8 전체, 최종)**: 매 항목 focused test + revert-to-verify 확인함(예외 없이 전부).
**배치 마무리 전체 검증**: 백엔드 전체 회귀 **2회**(1회차는 SRCH-01 직후 시작~UA-20R 이전
스냅샷, 2회차는 배치 전체 최종 스냅샷 — 둘 다 2791+건 **exit 0, 실패 0건**) · 프런트 전체
회귀(**220파일/1494건, exit 0**) · 러너 전체(**288건, exit 0**) · `bash
scripts/static_checks.sh` → **`STATIC_CHECKS_OK`**(번들 신선도 포함) · `npm run build` 통과.
커밋은 항목마다 개별(구현 1 + docs 1 페어 기본) — 이 배치 전체 **총 26커밋**.

**배포 — Blocker(외부, 사용자 조치 필요).** 승인된 TEST SERVER(`10.100.64.X` 대역) 배포
자격증명이 이 세션에 없다(CLAUDE.md §4 불변규칙: credential은 runtime에서만, 대화/문서에
남기지 않는다 — 채팅으로 전달받는 것 자체가 이미 노출이라 받지 않는다). 실서버 배포·Chrome
Whole-product E2E는 사용자가 직접 배포하거나 승인된 접근 경로가 마련된 뒤 가능하다. 이
Blocker와 무관하게 다른 독립 작업(BACKLOG 나머지 항목·QA_COVERAGE 공백)은 계속 진행 가능.

**다음 후보**: BACKLOG 나머지 `발견`/`정밀화` 재고 중 남은 High(QA-02 실브라우저 E2E 0회,
USE-01 자동화 실행이력 0 — 이미 WF7-U축에서 상당 부분 처리됨) + QA_COVERAGE L축(화면 간 반영)
전수 매트릭스 + 나머지
Med/Low 항목 Root Cause 클러스터링(VIS-158R AI 응답 좁은화면 미노출은 라이브 확인 필요한
디자인 판단이라 신중 검토, AI-31/AI-53/AI-05~29 등 AI 도우미 심화 아키텍처 항목은 여러
사이클째 의도적 보류 — 스트리밍/중단/도구사용 등 전담 설계 필요).
+ QA_COVERAGE L축(화면 간 반영) 전수 매트릭스 + 나머지 발견 항목 Root Cause 클러스터링.

**같은 세션 계속(2026-08-11) — WF7 whole-product 재감사 1회차.** RG-*/APPR-*/UB-25
배치가 소진된 뒤 §8 지시대로 착수 — 배경 포크 3개(백엔드 RBAC/DB/API, 프런트
Design/UX, AI/Runner/Ops) 병렬 실행, 각각 기존 BACKLOG를 먼저 훑어 **새로운** Root
Cause만 보고하게 지시.
- **AI/Runner/Ops 포크**: 4개 영역(잡·핸들러 완결성, AI 라우팅, 러너/워크플로 설정
  검증, 관측성 죽은 코드 재확인 — UB-25에서 잡은 "실측 없이 지우면 안 된다" 교훈을
  방법론에 반영해 재적용)을 훑고 **새 발견 없음**으로 정직하게 보고. 이 도메인은
  MEGA CYCLE A + 이번 세션 DGEN/USE/SCHD·UB-25 배치로 이미 수렴한 것으로 판단.
- **PROJ-01(백엔드 포크 발견, High)**: `app/projects/service.py::create_project`/
  `update_project`가 `uq_projects_org_code`에 대해 사전 SELECT(순차 중복만 409)만
  두고 SAVEPOINT 재시도가 없었다 — 이 저장소가 이미 13곳 넘게 고친 것과 같은 클래스의
  버그인데 `projects` 모듈(migration 0044)만 빠져 있었다. `profiles/service.py::
  create_view`와 같은 관용으로 수정, `threading.Barrier(2)` 결정적 경합 재현 시험
  신설, revert-to-verify 확인함.
- **QAH-06(프런트 포크 발견, High)**: `/mail`(`MailStatus.jsx`, `AdminRoutes.jsx`에
  실재하는 라우트)이 `scripts/ui_qa/routes.py`에 등록이 안 돼 있어 이번 QAH 68라우트
  1회차를 포함해 한 번도 캡처되지 않았다 — `routes.py` 자체의 "2026-08-08 추가" 주석에
  이미 기록된 것과 같은 결함 클래스가 세 번째로 반복된 사례. 등록 추가 + 같은 함정의
  재발을 막는 상시 완전성 가드 시험(`AdminRoutes.jsx`의 실제 라우트 전부를 하네스
  등록과 대조) 신설.

**검증**: 둘 다 focused test + revert-to-verify 확인함. PROJ-01은 프로젝트 관련
전체 스위트 137건 green. QAH-06은 관련 QA 하네스 시험 14건 green(프런트 소스 변경
없음 — routes.py는 Python 하네스 코드라 프런트 전체 회귀 재실행 불필요로 판단).
커밋 4개(구현 2 + docs 2).

**남은 다음 후보**: PERF-02(낮은 우선순위, 보류) · DGEN-03(보류) · QA_COVERAGE의
U(실사용 이력)·K(그라디언트 대비)·L(화면 간 반영 전수) 공백. WF7이 새 발견을 2건만
(3개 포크 중 1개는 무결과)냈다는 것은 이 배치 규모에서는 제품이 상당히 수렴했다는
신호 — 다음은 QA_COVERAGE 공백 착수, 또는 더 넓은/다른 각도의 재감사(예: 실제
Chrome 기반 E2E, 이번 재감사가 못 본 영역) 후보.

**같은 세션 계속(2026-08-11) — WF7 후속: `K`축(그라디언트 배경 위 텍스트 대비) 종결.**
위 "남은 다음 후보" 중 `K`를 착수 — 상단바(`AppShell.jsx` `AppBar`) 전체를 직접 계산으로
실측했다. 그라디언트는 `radial-gradient(circle at 78% -120%, brand.purple@0.74, transparent
44%) + linear-gradient(112deg, deep→mid→accent)`.
- **`WF7-K01`(실결함, Med)**: 78% 부근(`UserMenu`가 실제로 있는 자리)에서 보라 광원과
  강조색 정지점이 겹치는 최악 지점의 흰 글자 대비가 4종 강조색 전부에서 AA(4.5) 미달 —
  `UserMenu.jsx`의 계정 이름 버튼이 배경 없이 이 위에 바로 앉아 있었다. "최종안"인
  그라디언트 자체는 손대지 않고, 버튼에 옅은 검정 알약 배경(`rgba(0,0,0,.15)`)만 얹어
  같은 최악 지점에서도 4종 전부 5.1 이상으로 통과하게 함. 신규 시험 3건, revert-to-verify
  확인함.
- **나머지 상단바 요소 점검(결함 아님 확인)**: 같은 자리를 손대기 전에 상단바의 다른
  텍스트/요소도 훑었다 — `NotificationBell`의 배지는 MUI `color` prop이 주는 자기 자신의
  불투명 배경 위에 숫자가 앉아 그라디언트와 무관, `TopBrand`는 텍스트가 아니라 반전 SVG
  로고, `TopSearch`는 자기 자신의 반투명 남색 오버레이(`rgba(7,12,34,.22)`)가 있고 실제
  flex 레이아웃(`flex:1`+`maxWidth:720px`, 뒤따르는 별도 `flex:1` 스페이서와 공간을
  나눠 가짐)상 x≈45~55% 구간에만 위치해 78% 위험 구간에 안 닿는다 — 소스 주석의 실측
  빈 공간 값(1920px에서 573px)과 교차검증 + 정밀 radial-gradient 기하 시뮬레이션(farthest-
  corner circle 공식)으로 6.8 이상 확인. **먼저 실측한 뒤에만 "고치기"로 판단** —
  자작 대비 계산이 실제 요소 위치와 안 맞으면 위양성이 될 수 있어, 손대기 전에 flex
  레이아웃 수식과 소스 주석의 실측치를 교차검증했다(이 세션의 반복 원칙: 새 측정 도구의
  첫 결과는 표본을 개별 확인한 뒤에만 기록한다).
- **검증**: `usermenu-topbar-gradient-contrast.test.js`(회귀 고정 + 배선 확인 + 통과 확인
  3건) 통과. 관련 프런트 4파일 10건 통과(`UserMenu`/`NotificationBell`/`AppShell` 관련
  시험). `docs/BACKLOG.md`에 `WF7-K01` 행 추가, `docs/QA_COVERAGE.md` §11 `K`축 O로 갱신.

**남은 다음 후보(갱신)**: PERF-02(보류) · DGEN-03(보류) · QA_COVERAGE의 U(실사용 이력) ·
L(화면 간 반영 — WF7-L01로 승인 1건만 해소, 전수 매트릭스는 아직 없음) 공백. K축은
상단바 기준으로 이번에 종결 — 남은 그라디언트 표면(로그인 화면 등)이 있다면 다음
whole-product 재감사 라운드에서.

**같은 세션 계속(2026-08-11) — WF7 후속: `U`축(실사용 이력) 나머지 항목 실행.**
`USE-01`의 12개 중 미실행이던 오프보딩·공지 배너·AI 쿼터 3종을 처음부터 끝까지 실행했다.
- **원격 승인 TEST SERVER(`10.100.64.71`) 접근 실패**: 캐시된 QA 세션이 전부 만료
  (401), 저장된 비밀번호도 재로그인 실패 — 원격 계정 재발급은 SSH가 필요해 이 조사
  하나로는 범위 밖이라 판단, **로컬 dev 서버**(이 저장소의 `var/web.sqlite3`, uvicorn
  직접 기동)로 전환. `user_cli`로 전용 QA 계정 4개 신설(admin 1 + 각 기능별 대상 계정).
- **Notion 쓰기 위험 재확인**: 로컬 dev도 `var/secrets/notion_docs_token` 등 실토큰이
  있어 D-21의 실고객 워크스페이스 위험이 로컬이라고 사라지지 않는다 — 오프보딩은
  `ticket_page_ids: []`(빈 목록, Notion 쓰기 0건 직접 확인)로만 실행, 공지는
  `active=false`로만 만들어 실사용자 화면에 실제로 뜨는 일을 피했다(회사 전체에 보이는
  배너를 실제로 띄우는 것은 이 세션 혼자 결정할 일이 아니라고 판단).
- **결과: 셋 다 정상 동작, 결함 0건.** 오프보딩(실행→계정 비활성화 확인→되돌리기→계정
  재활성화 확인), 공지 배너(생성→목록 노출→삭제→목록에서 사라짐 확인), AI 쿼터(생성→
  `used` 필드와 함께 목록 노출→`/usage` 확인→삭제 확인) — 감사 로그도 4개 액션
  (`offboarding.run`/`.undo`/`announcement.create`/`ai_quota.create`) 전부 기록됨을
  확인했다. 신규 도구 `scripts/ui_qa/use_axis_e2e.py`(커밋 대상, `dist/`는 gitignore).
- **남은 U축 공백**: 문서 생성(`DGEN-02`, 워크플로 없음)·스케줄·주간 리포트(D-21) 3개는
  원인 규명된 의도적 보류, 휴지통 1개만 실제 왕복이 미실행(기존 `trash_e2e.py`가 빈
  상태만 확인했었다 — 실제 문서를 trash에 넣으려면 새 문서 생성(Notion 쓰기, D-21) 또는
  기존 실문서를 잠시 건드려야 해 보류 유지).

**검증**: `docs/BACKLOG.md`에 `## OFFB·ANN·QUOTA` 절 추가, `docs/QA_COVERAGE.md` U축을
`~`(6확인) → `~`(8확인, 정확한 잔여 공백 명시)로 갱신. 로컬 dev 서버는 확인 후 정지함.
SHORT OVERRIDE 단계는 그 아래 그대로 유지

**같은 세션 계속(2026-08-11) — APPR-02/03·RG-06/07 4건**: QAH+DGEN 배치 직후 "다음
후보" 목록에서 자기완결 항목 4개를 이어서 구현.
- **APPR-03**: `GET /api/admin/approvals?status=<모르는 값>`이 조용히 0건 → 알려진 5개
  상태 밖이면 422(이 저장소의 다른 enum 검증과 같은 상태 코드).
- **APPR-02**: 승인 알림/메일 제목이 `user.role_change` 같은 내부 코드를 그대로 노출 →
  `_REQUEST_TYPE_KO` 매핑으로 3개 호출부(요청/결정 알림, 요청 메일) 전부 한국어화.
- **RG-07**: `documents` 목록 요청자·`workflows` 버전 기록 변경자가 서버는 이미 이름을
  주는데 화면이 raw UUID만 그림 → `personField`로 교체, `versionsAction()`에 opt-in
  `namedCreator` 추가(연동·러너 `/versions`는 실제로 이름을 안 준다는 것 재확인 후 그대로 둠).
- **RG-06**: 복구 리허설 첫 실행 안내 4종이 `canOnboard`(create/primary headerAction
  전제) 게이트 때문에 어떤 역할에서도 안 그려짐 → `config.forceOnboarding` opt-in 신설.
  같은 함정이 다른 registry 화면에도 있는지 전수 감사 시험(`onboarding-gate-coverage.
  test.jsx`)을 새로 만들어 확인 — 이 화면이 유일한 사례, 이 시험이 앞으로 상시 가드로 남음.

**검증**: 4건 전부 focused test + revert-to-verify 확인함. 백엔드 관련 스위트(approvals ·
session · schedules · documents · templates · security 전체) 85건 green. 프런트 전체
회귀 1484건 green(216파일). 커밋 8개(구현 4 + docs 4).

**같은 세션 계속(2026-08-11) — RG-05·UB-25 2건**:
- **RG-05**: 승인 큐(`governance.js`)에 `status` 서버 필터만 있고, 백엔드가 이미 받는
  `request_type`/`requested_by`는 안 쓰고 있었다 — 추가(request_type은 select, 라벨은
  `actionKo`로 만들어 목록 열과 항상 같은 말을 쓰게 함; requested_by는 impersonation
  화면과 같은 자유 텍스트 ID 필터).
- **UB-25**: 죽은 코드 후보 5개를 재검토. **하나는 전제가 틀렸다** — `body["components"]`를
  실측 없이 지우려다 `test_admin_backlog.py::test_operators_get_component_detail`이
  운영자 이상에게 이 필드를 이미 의도적으로 요구하는 것을 발견하고 되돌림("소비자 0"이
  아니라 "프런트가 아직 안 읽는다"였다 — 이 세션이 이미 여러 번 강조한 "재검증 없이
  지우지 않는다"가 여기서도 실제로 뭔가를 구했다). 나머지 4개는 실측대로 죽어 있었다:
  `list_sync_status`·`SYNC_ERROR` import 삭제, `ROLE_SYSTEM_MSG` 삭제, `KNOWN_EVENTS`는
  삭제 대신 실제로 강제하도록 고침(그 과정에서 `app/quotas/service.py`가 `EVENT_AI_CALL`을
  별도 재정의해 "이벤트 이름은 한 곳에서만 만든다"는 모듈 규칙이 이미 깨져 있던 것도
  함께 고침).

**검증**: 둘 다 focused test + revert-to-verify 확인함. UB-25는 백엔드 전체 회귀
2791건 green(28분, exit 0, 실측 로그 확인) — 큰 폭의 변경(4개 파일, import 구조
변경 포함)이라 전체 회귀를 조기 실행. 프런트 전체 회귀 1487건 green(217파일).
커밋 4개(구현 2 + docs 2).

**남은 다음 후보**: PERF-02(GET /api/tickets 405, "정상 동작" 명시된 Low 항목 — 값이
낮아 보류 판단) · QAH-05(game-room contrast, 하네스 라우트 편입 먼저 필요) ·
DGEN-03(FormModal 전역 영향 커서 보류) · QA_COVERAGE의 U(실사용 이력)·K(그라디언트 대비)·
L(화면 간 반영 전수) 공백. **RG-*/APPR-*/UB-25 계열은 이번 배치로 사실상 소진** —
다음은 whole-product 재감사(§8) 또는 QA_COVERAGE 공백 착수가 유력.


**QAH 배치(2026-08-11) — 전수 QA 하네스 1회차 실행 + 4개 축 결함 전부 수정.**
`scripts/ui_qa/run.py`를 68라우트 × 라이트/다크 × 3뷰포트(408페이지) 로컬 dev 서버 대상
전체 실행 — `QA_COVERAGE.md`가 오래전부터 "가장 큰 미검증 표면"으로 남겨 뒀던 항목.
4개 축(`console_errors`·`vertical_text_collapse`·`contrast`·`tiny_text`)에서 실 결함 발견,
나머지 17+1개 축은 전부 통과. 상세는 `BACKLOG.md` §QAH, `QA_COVERAGE.md` §12.
- **QAH-01(High)**: `app/core/sessions.py::validate()`의 세 부수효과 커밋(last_seen_at
  스로틀 갱신, idle/절대 만료 revoke)이 재시도 없이 `db.commit()`을 직접 불러 동시 요청과
  SQLite 쓰기충돌 시 순수 조회 API(`/api/notifications/unread-count` 등)까지 500을 냈다.
  기존 `is_write_conflict()` + SAVEPOINT 재시도 관용(D-59/CORE-13)을 재사용하되, 이 세
  지점은 실패해도 예외를 안 올리는 `_commit_best_effort()`로 통일 — root cause는 D-59와
  같은 부류지만 "커밋 실패 시 요청을 계속 실패시켜야 하는가"가 이 세 지점은 다르다(인증
  판단 자체가 이미 메모리에서 끝나 있다).
- **QAH-02/03(대비·세로붕괴)**: `MuiButton` 기본 text/outlined variant와 `kit.jsx::StatCard`
  sev 배지가 CTR-01/04와 같은 이유(raw `palette.*.main`)로 WCAG AA 미달 — `primaryStrong`과
  같은 배합의 `success`/`warning`/`error`.`strong`을 theme.js에 추가. 표본 519건 중 513건
  (98.8%)을 이 세션에서 고쳤다(포크 병렬 조사 활용) — 남은 6건(`button.password-toggle`,
  로그인 화면)은 승인된 디자인 베이스라인 고정 계약이라 의도적 보류. 조사 중 발견한 game-room
  화면 7곳의 같은 패턴은 하네스 라우트 밖이라 QAH-05로 미착수 등록.
- **QAH-04**: `Mascot.jsx` 사이드바 힌트의 절대 px 글자 크기(4K 레버 무력화) — DS-32 관용대로
  rem 전환.
- **DGEN-01(High)/USE-04/SCHD-02** — QAH와 별개로 이 배치에서 함께 처리(같은 세션, "다음
  후보" 목록에 있던 자기완결 항목): 문서 생성 모달의 워크플로/템플릿 ID, 스케줄 대상 ID가
  자유 텍스트 UUID 받아쓰기였던 것을 이름 select로 교체. `DataScreen.jsx`에 `config.refLists`
  공용 훅 신설(다른 화면의 리소스를 select 옵션으로) — DGEN-03(필드 접기)은 blast radius가
  커 범위 밖으로 명시 보류.

**검증**: 항목마다 focused test + revert-to-verify(전부 확인함). 프런트 전체 회귀
1469건 green(215파일). 백엔드 관련 스위트(세션·스케줄·문서·템플릿) green. **백엔드
전체(integration+security+regression) 회귀 1회 별도 실행 — exit 0, 실패 0건 확인**(이
배치 시작 시점에 백그라운드로 돌려 둠, 진행 중 별도 스위트 재확인들과 함께 교차 검증).
커밋 9개(session 락 수정 1 · Mascot 1 · contrast 배치 2 · QAH 문서화 2 · DGEN/USE/SCHD
기능 1 · 문서 2).

**다음 후보(그대로 유효, 이번 배치가 손 안 댐)**: RG-05/06/07(승인 큐 필터·복구 리허설
온보딩·raw UUID 표시) · APPR-02/03(알림 제목 내부 코드 노출·status=all 무검증) ·
PERF-02(GET /api/tickets 405) · UB-25 나머지 2종(죽은 코드) · QAH-05(game-room contrast,
하네스 라우트 편입 먼저 필요) · DGEN-03(보류 이유 위 참고).

— KBD-01/02/03·FN-17·UB-21/22/40/41/23/19·UA-12/29/13/11/14/15/16 15건 구현+테스트+커밋
완료(재검토로 결함 아님 정정 4건: FN-15/16/18, UB-20). 배치 종료 시점 전체 백엔드(2670+건)
green 재확인(exit 0, F/E/x/s 0건). 상세는 §「SHORT OVERRIDE 이후 배치」 섹션. 배포는 여전히
Blocker로 대기(SSH/sudo 비밀번호 비사용 정책). 이전 단계는 아래 그대로 유지:
**MEGA CYCLE I 구현+테스트 완료(기능·데이터·권한 E2E — FN-*/SEC-* quick-fix 스윕)**.
Cycle 4의 소배치 방식을
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

**세션 재개(2026-08-11, D-60) — Runner 12시간 무동작 원인 수정 + 아키텍처 재확인**: 새
대화형 세션이 사용자의 "WHOLE PRODUCT AUTONOMOUS COMPLETION" 지시로 시작해 상태를
복원하다가, `var/runner/state.json`이 연속 실패 3회로 STOP돼 있고 마지막 반복이 전부
09시경 즉시 `exit 1`이었음을 발견했다 — 원인은 `autonomous_runner.ps1`이 거대한 멀티라인
프롬프트를 `Start-Process -ArgumentList` 배열 원소로 넘기던 것이 Windows 커맨드라인
재조립 과정에서 깨진 것(`error: unknown option '--oneline'`, 프롬프트 안의 예시 문구가
`claude.exe` 옵션으로 오인됨). 프롬프트를 파일 + `-RedirectStandardInput`으로 넘기는
방식으로 고치고 격리된 스크래치 디렉터리에서 같은 버그 유발 문구로 재현 테스트해
exit 0 확인. 상세는 `docs/DECISIONS.md` D-60. **아키텍처**: 1차 연속 실행은 하네스
`/loop` dynamic mode + `ScheduleWakeup`(대화형 세션 안, D-53에서 이미 결정)이고
`autonomous_runner.ps1`은 터미널이 닫혔을 때만 쓰는 2차/백업으로 재확인 — 이 세션이
활성인 동안은 `var/runner/STOP`을 그대로 두어 동시 수정을 막는다. 새/기존 Task Scheduler
항목은 건드리지 않는다(사용자 결정 사항). 커밋 전 우연히 발견: `CLAUDE.md`가 이전
실행이 재작성해 두고 미커밋 상태로 남긴 것(§0 원본 상세 → `docs/ARCHITECTURE.md`/
`docs/SECURITY.md`로 위임하는 더 짧은 최상위 실행 규칙 버전) — 내용을 대조해 정보
손실이 없음을 확인하고 그대로 커밋했다. 이어서 §「다음 후보」(위 §「SHORT OVERRIDE
이후 배치」 끝의 CTR-01~05·DGEN-01/03·SCHD-02·USE-04·AI-33/34·BKP-01/02/04·UB-14/29·
UB-17/27·OPS-03/04·UB-25·FN-08/20·RG-05~07/10·APPR-02/03·NOTI-02·MAIL-02/03·PERF-02·
SYS-09/10/11) 재검증을 배경 Workflow(읽기 전용 조사 전용, 파일 수정 없음 — 동시 편집
충돌 방지)로 병렬 착수, 결과가 오는 대로 이 세션이 직접 순차 구현으로 이어간다.

**D-60 정정(D-61)**: 사용자가 직접 "1차 Supervisor는 `/loop`+`ScheduleWakeup`이 아니라
로컬 `autonomous_runner.ps1`"이라고 뒤집었다 — 대화형 세션 안 메커니즘은 project
continuity의 근거가 아니라는 지시. `run.lock`/`STOP` 파일이 조용히 아무 설명 없이
새 수동 실행을 무력화하던 것도 함께 고쳤다(항상 이유를 로그로 남기게). 격리된 스크래치
저장소에서 controlled test로 (1) exit 0 뒤 sleep 없이 ~0.1초 만에 다음 반복 시작
(2) 두 번째 인스턴스 즉시 물러남 (3) STOP 있으면 새 실행이 이유를 밝히고 종료, 세 가지
전부 타임스탬프 로그로 직접 증명했다. 상세·로그 원본은 `docs/DECISIONS.md` D-61. 이
세션이 활성인 동안은 여전히 `var/runner/STOP`을 유지한다(단일 인스턴스 보호) — 이
세션이 끝나면 사용자가 그 파일을 지우고 Runner를 시작하는 것이 이제 명시적인 주 경로다.
같은 배치에서 재검증 Workflow 결과 처리 중 발견한 실제 결함(UB-17: 임퍼소네이션 자동
종료가 감사에 안 남음, UB-27: 요청 없이는 만료된 임퍼소네이션이 영원히 "진행 중"으로
남음, + 재확인 중 새로 발견한 사전 결함: `imp_service.END_TARGET_UNAVAILABLE`이
`service.py`에 애초에 import돼 있지 않아 대상 계정이 비활성화되는 경로가 **항상
500이었다**)를 구현+테스트 완료(revert-to-verify 확인) — 커밋은 이 문서 갱신과 함께
진행.

**같은 세션 계속(2026-08-11) — 재검증 배치 11건 구현완료**: 위 배경 Workflow(10개
클러스터, 읽기 전용 조사)의 결과를 받아 순차로 직접 구현. Security/Audit/Integrity 우선
순서(CLAUDE.md §4)를 따랐다. 커밋 순서대로:
- **UB-17·UB-27**(임퍼소네이션 자동종료 감사 누락 + 만료 스윕 부재) — 위 D-61 문단 참고.
- **OPS-04**(업로드 실패 감사 누락, tickets/board/profiles 3곳 공통): `audit_failure_on_exception`
  컨텍스트 매니저 신설(app/core/audit.py), 세 라우터에 배선. `db.commit()` 명시 필요(auth
  로그인 실패 경로와 같은 이유 — 안 하면 실패 감사 행이 롤백에 딸려 감).
- **OPS-03**(uploads 쓰기 불가가 관측 안 됨, OPS-01 재발 방지): `uploads_writable()` 신설,
  대시보드(지속 관측)·`/readyz`(배포 게이트, 503+reason) 배선.
- **UB-14·UB-29 일부**(템플릿 활성화가 대상 생존 안 봄 + archived Prompt/Policy 새 바인딩
  허용): `_validate_enable_target()` 신설(존재 422·비활성 409), `_validate_references()`에
  status 검사 추가. UB-29 나머지 3개 하위 항목(페이지네이션·creator_name·DELETE)은 범위
  밖으로 보류, BACKLOG에 기록.
- **FN-20**(토너먼트 대진 제출 CAS 없이 덮어씀, 데이터 유실): `_tournament_advance`를 순수
  함수로 분리(room/db 쓰기 없음, 재시도 안전), `_tournament_submit`·`_finish_rps_tournament`
  둘 다 `_cas_update_state`로 감쌈 — submit_number·단판 submit_rps가 이미 쓰던 패턴과 통일.
- **BKP-01·BKP-04**(백업이 첨부 누락 + venv 통째로 포함): 백업에 `uploads.tar.gz` 추가,
  `app.tar.gz`에서 venv 제외 + 롤백이 복원 직후 재생성(installer 로직과 동일, WHEELHOUSE
  환경변수 지원). BKP-02(복구 리허설이 첨부 존재까지 교차검증)는 4개 다른 스키마 매핑이
  필요해 범위 밖으로 보류.
- **CTR-01·CTR-02·CTR-04**(WCAG AA 미달 — 다크 링크 3.5~4.1, 콘솔전환 다크 2.86, 라이트
  링크 4.37): MuiLink에 `primaryStrong` 배선, ConsoleSwitch를 `primary.dark`→`primary.main`
  으로 교체. **1차 작성한 시험이 팔레트 값을 독립적으로 재계산해 배선 누락 회귀를 못
  잡는 것을 스스로 발견·수정**(되돌려도 통과해서 직접 확인함 — 실제 적용값을 읽도록 고침).
  CTR-03·CTR-05는 재검증 결과 CTR-01로 부분 해소되거나(텍스트 실사용) 별도 게이트 작업이라
  범위 밖.
- **MAIL-03**(설정 안 됨 건수가 재발송 안 된다는 안내 없음): MailStatus.jsx에 Callout 추가.

**의도적으로 구현 보류(재검증했지만 이번 배치에서 안 함, 이유 BACKLOG에 기록)**:
`AI-33`(마크다운 인라인 토크나이저, 아키텍처 결정 필요 — AI-34부터 먼저), `NOTI-02`/
`MAIL-02`(알림·메일 팬아웃, Notification 모델 변경 필요), `RG-10`(auditor 읽기 범위
확장 — RBAC 정책 결정 필요, 코드 diff는 작지만 사람 판단 필요).

**검증**: 매 항목 focused test + revert-to-verify(CTR-01/02/04는 1차 실수를 잡고
재작성 후 재확인). 프런트 전체 회귀 213파일/1429건 green(MAIL-03 직전 실행, 그 항목은
focused만). 백엔드 전체 회귀는 이 체크포인트 시점 진행 중 — 완료되는 대로 실패가 있으면
Root Cause grouping 후 일괄 수정.

**다음 후보(2026-08-11 체크포인트에서 남김, 재검증까지 끝났지만 미구현)**: AI-34(코드펜스
파싱, 단일 파일 패치 규모) · RG-05/06/07(승인 큐 필터·복구 리허설 온보딩·raw UUID 표시) ·
APPR-02/03(알림 제목 내부 코드 노출·status=all 무검증) · SYS-09/10/11(NotionConsole.jsx
저장 패턴 불일치·중복 경고·배지 의미 혼동, 셋 다 같은 파일) · FN-08(퀴즈/내레이션이 러너
레지스트리 우회) · PERF-02(GET /api/tickets 405, 매우 낮은 우선순위) · DGEN-01/03·SCHD-02·
USE-04(자유입력 UUID→picker, DataScreen.jsx 공유 aux-list 메커니즘 하나로 4건 해소 가능) ·
UB-25(죽은 코드 5종 중 3종은 진짜 삭제 대상, 2종은 backend-complete-미UI라 삭제 아님) ·
CTR-03/05(강조색 검증 게이트) · BKP-02 · UB-29 나머지 3개. QA_COVERAGE 73라우트 전수검증도
여전히 미착수(가장 큰 미검증 표면).

**같은 세션 계속(2026-08-11) — 위 13건 배치 뒤 백엔드 전체 회귀 1회, SYS-10/11·AI-34 2건
추가(총 15건) + CTR-03/05 미착수로 재확인**. 전체 백엔드(수집 전체) 회귀 결과: **1건
실패** — `tests/integration/test_prompt_create_new_version_race.py::
test_concurrent_new_version_all_succeed_with_distinct_versions`(`sqlite3.OperationalError:
database is locked`가 `_NEW_VERSION_RETRIES=5` 재시도 상한을 넘겨 500). 이 세션의 변경
파일 목록에 `app/prompts/service.py`·`app/prompts/router.py`·`app/core/db.py`가 전혀
없음을 확인했고, **단독 재실행 3/3 통과**로 이번 배치와 무관한 기존 플레이키 확인
(`test_claim_race.py`와 같은 부류 — 8-way 실스레드 타이밍 경합 시험이 이 특정 실행에서
동시에 돌던 다른 무거운 작업(프런트 vitest 전체 회귀·여러 git stash 조작)으로 시스템
부하가 커져 재시도 상한을 넘긴 것으로 추정, 정직하게 기록). **회귀는 사실상 green** —
2670+건 중 이 무관한 1건 외 전부 통과.

**이 배치의 다음 우선순위(재검증 완료, 다음 착수 후보)**: 위 목록 그대로 유효. 특히
BKP-02(4개 스키마 매핑)·UB-29 나머지 3개(pagination/creator_name/DELETE, 이미 배선
패턴 확정됨)·CTR-05(contrast.py 하네스 편입)가 각각 자기완결적이고 조사가 이미 끝나
바로 구현 가능하다. QA_COVERAGE 73라우트 전수검증은 여전히 이 세션이 손 안 댄 가장 큰
단일 미검증 표면으로 남아 있다 — 다음 큰 착수 후보.

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
  반복) — 전부 green 확인함. 백엔드 전체 회귀(2670+건)를 이 배치 전체(OPS-05/OPS-02/
  AI-27/UB-07)가 다 들어간 상태로 재실행해 exit code 0·실패표시 0건 확인. 커밋 `a625f76`.
  실서버/브라우저 확인은 배포 Blocker로 여전히 불가(§D-54).

**계속(2026-08-11, 연속 실행) — UB-18 구현완료**: `a625f76` 커밋 직후 바로 다음 후보를
코드로 재확인해 착수했다.
- **UB-18**: `record_usage`(`app/observability/service.py`)가 `db.flush()` 실패를
  `except Exception:`으로 삼키기만 하고 `db.rollback()`을 안 해 세션이 pending-rollback
  상태로 남았다 — 그 세션으로 **다음 문장을 하나라도 더** 실행하면(호출자의 나머지
  로직, 또는 `get_db`의 요청-끝 `db.commit()`) 전부 `PendingRollbackError`로 깨진다.
  이 함수 자체 docstring이 약속한 "통계 한 줄 때문에 로그인·티켓 생성이 실패하면
  안 된다"와 정확히 반대로, 통계 실패가 본 작업까지 끌고 내려가는 구조였다. `db.add(row);
  db.flush()`를 `with db.begin_nested():`(SAVEPOINT)로 감쌌다 — `app/core/versioning.py`
  의 `_create_version_with_retry`가 이미 쓰던 것과 같은 패턴("실패한 insert를 savepoint로
  감싸 세션에 이미 올라와 있는 다른 변경까지 되돌리지 않는다"는 그 파일 자체 docstring이
  UB-18에 그대로 들어맞는다). 신규 시험
  `test_record_usage_failure_does_not_poison_other_pending_changes_in_the_session` —
  다른 pending 변경(커밋 안 된 별도 `UsageEvent`)을 세션에 먼저 올려 두고, 실패하는
  기록(`event=None`, NOT NULL 위반)을 호출한 뒤, **수동 rollback 없이** 정상 커밋까지
  되는지 + 그 다른 변경이 실제로 저장됐는지 확인. revert-to-verify(되돌리면 잡히지 않은
  `IntegrityError`로 즉시 실패 확인 후 복원). 호출부 4곳(auth 로그인·티켓 생성·문서
  생성·quotas) 중 `quotas.consume()`은 이미 자체 `begin_nested()`를 쓰고 있어 중첩
  SAVEPOINT가 되는데, 관련 시험 전부(quota TOCTOU 포함 18건) green으로 문제없음을 확인.
- **검증**: `test_usage_events.py`(15건) + 로그인/티켓생성/문서생성/quota 관련 폭넓은
  focused 시험 전부 green. 백엔드 전체 회귀(2670+건) exit code 0·실패표시 0건. 커밋 `5db84f5`.

**계속(2026-08-11, 연속 실행) — UB-06 구현완료**: `5db84f5` 커밋 직후 바로 다음 후보를
코드로 재확인해 착수했다.
- **UB-06**: 공지 생성·수정(`app/announcements/router.py`)에 `starts_at < ends_at`
  검증이 아예 없었다 — 뒤집어 넣으면(또는 폭이 0이면) 201/200이 그대로 나고 "활성" 행이
  생기지만, `service.in_window()`(`now < starts_at` 이면 제외, `now >= ends_at` 이면
  제외)의 두 조건이 뒤집힌 창에서는 **항상 동시에 걸려** 그 공지를 아무도 영원히 못 본다
  — 화면엔 아무 경고도 없어 관리자는 DB나 감사 로그를 직접 봐야만 원인을 안다.
  `service.validate_window(starts_at, ends_at)` 신설(`starts_at >= ends_at`이면 422,
  `>=`라서 폭 0도 함께 막는다) — POST는 그대로 페이로드 값으로, **PATCH는 결과로 남을
  값**(patch 대상이면 새 값, 아니면 기존 저장값)으로 검증한다: 한쪽만 고쳐도 이미 저장된
  다른 쪽과 뒤집힐 수 있기 때문이다(예: `ends_at`만 과거로 당기면 기존 `starts_at`보다
  앞서게 된다). 신규 시험 4건(`tests/integration/test_admin_backlog.py`) — 뒤집힌 창
  생성 거부·폭 0 거부·PATCH로 뒤집기 거부·정상적인 창 연장은 그대로 통과. revert-to-verify
  (되돌리면 뒤집힌 창 3건 실패 확인 후 복원 — "정상 창 편집" 시험은 원래도 통과라 회귀
  신호가 없는 게 정상, 정직하게 확인함).
- **검증**: `test_admin_backlog.py`(32건) + 공지 전체(33건) green. 백엔드 전체 회귀
  (2670+건) exit code 0·실패표시 0건 확인. 커밋 `890754d`.

## 🔴 사용자 지시 전환 — FINAL EXECUTION DIRECTIVE (2026-08-11, D-60 성격의 방법론 변경)

사용자가 "AREA/CYCLE/BACKLOG 몇 건 단위로 멈추지 말고 PROJECT 전체를 끝낼 때까지 계속하라,
넓게 조사하고 크게 고치고 전체 회귀는 뒤에서 한 번에" 취지의 대형 지시를 내렸다(Ultracode
사용 허가 포함). 이 시점부터 기존 "한 BACKLOG ID → 구현 → focused test → 전체 회귀 →
커밋 → 다음" 루프를, "루트 코즈 클러스터 단위로 크게 조사·구현하고, 전체 회귀는 배치가
수렴했을 때만" 방식으로 전환했다. `Workflow` 도구로 남은 오픈 BACKLOG(~190여 건, "발견"
상태만)를 프리픽스별 5개 에이전트로 병렬 감사해 근본원인 클러스터·우선순위 큐를 뽑았다
(전체 결과는 워크플로 저널에 있음 — 요지는 아래 "다음 착수 후보"에 옮겨 적는다).

## 🔴 이 감사에서 시작한 UB-08 시험 작성 중 이 세션에서 가장 큰 발견 — SQLite 트랜잭션이
## 진짜 BEGIN 없이 돌고 있었다 (Critical, CORE-13)

UB-08(쿼터 `consume()`의 잠금 해제~커밋 사이 창) 회귀 테스트를 짜다가, 의도한 경합
시나리오가 예상과 다르게(반대로) 동작하는 것을 보고 원인을 추적한 끝에 발견했다:
`app/core/db.py`가 pysqlite의 레거시 암묵적 트랜잭션 관리에 의존해서, `db.begin_nested()`
(SAVEPOINT — 이 저장소 13곳 이상이 "실패한 쓰기만 되돌리고 세션의 다른 변경은 지킨다"는
목적으로 쓴다)가 **진짜 BEGIN 없이** SAVEPOINT를 먼저 내보냈다. SQLite는 그 SAVEPOINT
자체가 트랜잭션을 암묵적으로 연 것으로 보고, 그 SAVEPOINT를 RELEASE하는 순간을 **커밋과
동일하게** 처리했다 — 직접 재현·확인(임시 프로브 스크립트, 검증 뒤 삭제): 커밋 안 한
SAVEPOINT 쓰기가 다른 커넥션에 즉시 보이고, 그 뒤 `session.rollback()`을 불러도 그 행이
사라지지 않았다(세션 자기 자신도 마찬가지 — `sqlite3.Connection.in_transaction`이
SAVEPOINT 직후에도 `False`). 즉 이 코드 13곳 이상이 믿고 있던 "SAVEPOINT 실패 시 그것만
되돌아간다"는 전제가 **실제로는 롤백이 안 되는 채로 프로덕션에 배포돼 있었다** — 진짜
ACID 위반. 왜 지금까지 안 드러났는지는 `docs/DECISIONS.md` D-59 참고("SAVEPOINT가
실패한 뒤 그 세션이 계속 살아서 재시도/다른 로직을 타는" 좁은 창에서만 관찰되고, 대부분의
요청은 애초에 경합이 안 일어나거나 결국 요청 끝에 정상 커밋되므로 "저장은 됐다"만 보면
차이가 없다).

**고친 것** — `app/core/db.py::make_engine()`: SQLAlchemy 공식 권고(pysqlite 다이얼렉트
문서의 "Serializable isolation / Savepoints") 그대로 `isolation_level=None`(pysqlite의
암묵 관리를 끔) + `"begin"` 이벤트에서 직접 `BEGIN` 발행. `BEGIN IMMEDIATE`를 먼저
시도했다가 실측으로 되돌렸다 — 읽기 전용 세션까지 전역 쓰기 예약을 잡아, 이 저장소의
"세션 하나를 테스트 내내 열어 두는" 픽스처 패턴과 부딪혀 전체 회귀 적색이 23건→**84건**
으로 늘었다. DEFERRED(평범한 BEGIN)로 되돌리고 아래 재시도 로직으로 해결했다 —
`quota_lock.py`·`claim_lock.py`가 이미 전제하던 busy_timeout 모델과도 이쪽이 맞는다.

**부작용(정확한 격리가 드러낸 진짜 경합) — 같은 커밋에서 함께 정리**:
- `is_write_conflict()` 신설(`app/core/db.py`) — `IntegrityError`뿐 아니라
  `OperationalError`(SQLite 확장 결과 코드, 실측: 517=`SQLITE_BUSY_SNAPSHOT` — 하위
  바이트로 낮춰 `SQLITE_BUSY`/`SQLITE_LOCKED` 판정)도 "쓰기 충돌"로 인식. `db.begin_nested()`
  재시도 코드 13곳(announcements/approvals/board/games/integrations/profiles/prompts/
  team_chat×3/team_docs×2/workflows/core.versioning)에 적용.
- 스냅샷이 낡으면 **같은 트랜잭션 안에서 재조회해도 여전히 낡은 값을 본다**는 것도 새로
  확인(`versioning.py::snapshot_config`가 최초 사례 — 재시도해도 매번 같은 버전 번호를
  계산해 같은 충돌을 반복했다). 재시도 전 `db.commit()`(다른 pending 변경을 잃지 않으려
  rollback 대신 — 이 함수 자체 docstring이 그 전제를 이미 적어 뒀었다) 또는
  `db.rollback()`(잃을 게 없는 곳)으로 스냅샷을 새로 뜨는 보강. `approvals.create_approval`
  은 8-way 실측 경합 후 재시도 횟수도 12회로 늘림, `games._cas_update_state`도 동일 패턴.
- `prompts/service.py::transition()` — 옛 발행본을 archive로 내리는 UPDATE가 SAVEPOINT
  **밖**에 있어 그 문장의 경합이 안 잡히고 새고 있었다 — 두 UPDATE를 하나의 SAVEPOINT로
  묶었다.
- `/login`(`app/auth/router.py`) — 성공 경로 쓰기(세션 생성·감사·사용통계)가 로그인
  앞부분의 읽기로 이미 굳은 스냅샷 위에서 실행돼, 동시 로그인이 몰리면 무관한 다른
  사용자의 커밋과도 부딪힐 수 있었다(10-way 동시 로그인 스트레스 시험으로 실측 재현 —
  프로덕션에 실제로 영향을 줄 수 있는 경로라 중요). 재시도(최대 10회) + 지터(즉시 재시도만
  하면 여러 스레드가 서로 계속 다시 부딪힌다 — 지터 없이는 5번 중 1번꼴로 여전히 실패) 추가,
  연속 8/8 통과 확인.
- 테스트 픽스처 12개 파일(project_sync/users_bulk_csv/collab_notifications/settings_api/
  job_scope/project_scope/trash_scope/chat_ticket_routing_contract/health_snapshot_job/
  project_api/project_milestones/team_chat_completion/review3_fixes) — `db.expire_all()`
  만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다(ORM 캐시만 지운다)는 것도 이번에 드러나,
  `client`로 다른 세션이 쓴 뒤 `db` 픽스처로 다시 읽는 자리마다 `db.commit()`을 먼저
  하도록 고쳤다.

**검증**: 전체 백엔드 회귀(2670+건) — DEFERRED+위 보강 적용 후 exit code 0·진행 표시에
실패 표시(F/E/x/s) 0건. `bash scripts/static_checks.sh` → `STATIC_CHECKS_OK`. 커밋
`400503c`. 상세 경위·트레이드오프는 `docs/DECISIONS.md` D-59, BACKLOG 항목은 `CORE-13`.

다음은 새 후보를 다시 코드로 재확인해 고른다 — 사용자 확인 대기 없이 진행한다.

---

## 🔴 SHORT OVERRIDE 이후 배치 — CORE-13 다음 12건 구현 + 재검토 3건 (2026-08-11)

CORE-13 커밋 뒤 "AREA/CYCLE/건수를 정지 단위로 쓰지 말고, 매 사이클 BACKLOG/QA_COVERAGE/
Source/Git/Tests 전체를 다시 대조해 다음 작업을 고르며, 완료 즉시 다음으로 넘어가고
요약·"다음 착수"·유휴를 두지 말라"는 SHORT OVERRIDE 지시를 받아 그대로 적용했다. 매 항목:
(1) BACKLOG 서술을 그대로 믿지 않고 현재 소스로 재확인 (2) 구현 (3) 신규 focused test
작성 후 **revert-to-verify**(고치기 전 코드로 되돌려 새 테스트가 그 실패 양식대로 죽는 것
직접 확인, 복원) (4) 관련 영역 스윕 green 확인 (5) BACKLOG.md 갱신 (6) 커밋 — 순서로
끊지 않고 이어갔다. 커밋 순서대로:

- **KBD-01/02/03**(High/High/Med) — MUI 마이그레이션이 지운 키보드 포커스 링.
  `MuiButtonBase`(`&.Mui-focusVisible`)·`MuiLink`·`MuiOutlinedInput`(`&.Mui-focused`)에
  3px/2px outline 신설, 색은 tokens.css `--color-primary-soft`(실측 대비 3.2:1) 재사용 —
  12% 배경 틴트(`palette.primary.soft`, 대비 1.05/1.45)는 안 씀. `theme-focus-visible.test.js`
  신설. 커밋 `7c5bfb0`.
- **FN-17**(Low) — `app/policies/`(빈 패키지) 삭제 확인·삭제. **FN-15/16/18은 재검토 결과
  결함 아님으로 정정** — 셋 다 코드 자체 주석이 "의도적으로 비워 둔 문"이라고 명시한다
  (ProjectMember의 N+1 방지 설계, ticket_cache.scope_dept_id의 "문만 연다", feature_flags.py의
  "지우지 않는 이유" 주석) — 감사가 "소비자 없음"을 자동으로 결함 취급한 오분류. 프런트
  번들 재빌드 동봉(직전 커밋이 `npm run build` 를 누락해 BUNDLE_FRESH 가 깨져 있었음).
  커밋 `49e4bc6`.
- **UB-21**(Low/Med) — 프롬프트/정책 생성·새버전 경합이 500으로 새던 것. `create()`는
  `begin_nested()`+같은 409(재시도 안 함 — "이름 존재"는 재시도로 안 풀림), `new_version_from()`
  은 `approvals.create_approval`과 같은 SAVEPOINT 재시도(재시도하면 실제로 성공하므로 409
  대신 성공). HTTP 레벨 실스레드 시험 2개 — `create` 쪽은 8-way 순수 타이밍으로는 위양성
  (로그인 자체 경합이 스레드를 흩어 놔서 안 겹침)이라 `before_cursor_execute`로 SELECT
  둘을 `threading.Barrier(2)`에 세워 결정적으로 겹치게 함(UB-08 시험 때와 같은 실수를
  또 잡고 바로잡음).
- **UB-22**(Low/Med) — 같은 파일에서 발견: prompts/policies PATCH가 `ContentUpdateRequest`
  하나를 공유해 Policy용 "null→{}" 기본값이 Prompt 자유 텍스트에도 적용됐다
  (`PATCH prompts/{id} {"content":null}`이 422 대신 문자열 "{}" 저장). `create()`처럼
  kind별 스키마(`PromptContentUpdateRequest`/`PolicyContentUpdateRequest`)로 분리.
  UB-21+UB-22 커밋 `af951e7`.
- **UB-40**(High) — 오프보딩 "대상 고르기"가 `page_size=20`으로 조용히 잘렸다(총건수·
  잘림 경고 없음). `TargetPicker`에 Search.jsx의 `ResultGroup`과 같은 잘림 안내 관용 추가.
- **UB-41**(Med) — `/search` 요청 limit이 20 하드코딩(서버 상한 50). 상한까지 올림 —
  전체 페이지네이션 재설계는 범위 밖으로 판단해 안 함. UB-40+UB-41 커밋 `96924dd`.
- **UB-23**(Low/Med) — `messages.message_id`가 전역 UNIQUE + 소유자 필터 없는 존재
  확인 = 아무 사용자나 임의 id로 다른 사용자 대화의 메시지 존재를 201/409로 알아낼 수
  있는 오라클. migration 0054로 `UNIQUE(conversation_id, message_id)`로 좁힘(기존 전역
  유일이 이미 이 약한 제약을 만족해 배포 전 dedup 불필요). 같은 패턴의 조회 4곳(post_user_
  message·jobs/handlers/chat_message.py의 `_load_message`/`on_failure`·jobs/router.py
  cancel)을 grep으로 전부 찾아 conversation_id로 스코프. 커밋 `d4ba79d`.
- **UB-19**(Low/Med) — 공지 삭제가 `AnnouncementDismissal`을 고아로 남김(FK 없음, 매
  배너 폴링이 그 무한히 자라는 집합을 전부 읽음). migration 0055로 `ON DELETE CASCADE` FK
  + 배포 전 기존 고아 무조건 삭제(되살릴 값 없음). **UB-20은 재검토 결과 전제가 재현 안
  됨으로 정정** — 이 저장소에서 `User` 행은 하드 삭제 경로가 없다(퇴사=비활성화+보관).
  커밋 `514f106`.
- **UA-12**(Med) — `JobTitle`(전역 유니크, 모델 docstring이 명시) 중복검사가 Department의
  `(org_id,name)` 스코프를 그대로 써서 다른 org 동명 직책 생성이 사전검사를 통과해 INSERT의
  전역 UNIQUE에서 처리 안 된 IntegrityError→500. 반대로 전역 admin이 org_id 없이 부서를
  만들면 사전검사가 실제 저장 조직(DEFAULT_ORG_ID 폴백)을 몰라 관계없는 다른 org와 충돌해
  잘못된 409. `create_item`/`update_item` 검사 범위를 모델별 실제 제약에 맞춤. 커밋 `97246ec`.
- **UA-29**(Low) — `documents/service.py`의 `int(config.get("template_version",1))`이
  자유형 dict 값(`"v2"` 등)에 처리 안 된 ValueError→500. `ValidationAppError`(422)로 변환.
  커밋 `e2212a1`.
- **UA-13**(Med, 테넌트 격리) — 부서 부모 지정이 `scope_allows_item`만 봐서(전역 admin
  에게는 모든 행이 "범위 안") 다른 조직 부서를 부모로 지정 가능. `department_subtree_ids`
  (순수 parent_id 그래프 순회, org 필터 없음)가 그 조직 부서를 dept-scope 관리자의
  서브트리에 끌어들여 권한이 조용히 넓어짐 — 실제 테넌트 격리 붕괴. `create_item`+
  `tree.py::validate_parent` 둘 다 `parent.org_id` 일치 검사 추가. 커밋 `d3229f0`.
- **UA-11**(Med) — 조직(테넌트) 생성이 `principal`조차 안 받아 스코프 게이트가 전혀 없음
  (role="admin"이면 통과 — role과 admin_scope는 다른 축). dept/org 범위 admin이 새 테넌트를
  만들 수 있었다. `principal.scope.is_global` 아니면 403. 커밋 `59951be`.
- **UA-14**(Med) — 오프보딩 되돌리기가 부분 실패해도 `undone_at`을 찍어, `REVERTIBLE_MOVES`
  가 이미 `revert_failed`를 재시도 대상으로 넣어 둔 설계(부분 실패를 재시도하게 하려던 의도)
  와 정면으로 모순됐다 — Notion이 불안정해 12건 중 3건이 실패하면 그 3건은 후임자에게
  영구히 남았다. `undone_at`/`undone_by_user_id`는 완전 성공(`failed==0`)일 때만 찍도록
  고쳤다 — 프런트는 이미 그 필드 하나로만 되돌리기 버튼을 보여줘 백엔드만 고치면 됐다.
- **UA-15**(Med) — `run_offboarding()`이 대상에게 이미 열린(안 되돌린) 실행이 있는지 확인
  안 함. 느린 Notion 단계 전에 장부를 먼저 커밋하므로 더블클릭·새로고침이면 두 번째 실행의
  `before_user_ids`가 첫 번째 실행이 넣은 후임을 "원래 담당자"로 기록해 되돌리기 계약이
  깨진다. 빠른 경로(사전 확인, 409) + migration 0056(부분 유일 인덱스
  `offboarding_runs(user_id) WHERE undone_at IS NULL`, approvals 0052/prompts 0053과 같은
  관용)로 진짜 동시 요청까지 막음. `offboarding_runs` 프로덕션 0행이라 배포 전 정리 불필요.
  UA-14+UA-15 커밋 `0b11a9f`.
- **UA-16**(Med, 성능) — 부서·직책·조직 목록 3종이 N+1(행마다 `usage_count` 또는 조직이면
  COUNT 2번) — 같은 파일의 `_org_names`·`tree.py`는 이미 그룹 질의로 고쳐져 있던 것과
  대조적이었다. `bulk_usage_count`/`_bulk_org_counts` 신설, 목록만 그룹 질의로 전환(단건은
  유지). `QueryCounter`(팀챗 방 목록과 같은 기법)로 행 2→10개 질의 증가량 실측 확인.
  커밋 `d012114`.

**검증**: 매 항목 focused test + revert-to-verify 확인함. 배치 중간·종료 시점 각 1회
전체 백엔드(전체 마커, 2670+건) green(exit 0, F/E/x/s 0건) 확인 — 이후 각 항목은 관련
영역 전체 스윕(`-k` 필터)으로도 확인. 프런트 유닛 전체(212파일/1412테스트) green(UB-40/41
이후 1회). `bash scripts/static_checks.sh` → `STATIC_CHECKS_OK` 매 커밋 전 확인. 배포는
여전히 Blocker 대기(SSH/sudo 비밀번호 비사용 정책 불변). 이 배치에서 신설한 마이그레이션
(0054 message_id 스코프·0055 announcement_dismissal FK·0056 offboarding 중복방지) 전부
업/다운그레이드 왕복 확인함.

다음 후보(재검토 없이 다음 세션이 코드로 재확인 후 고를 것 — 이 목록도 stale할 수 있음):
CTR-01~05(다크/강조 대비 WCAG), DGEN-01/03·SCHD-02·USE-04(자유입력 UUID→picker),
AI-33/34(마크다운 fence 상태 추적), BKP-01/02(백업이 첨부 제외), UB-14/29(참조 검증 공백),
UB-17/27(자동 종료 감사 공백), OPS-03/04(침묵 실패), UB-25(죽은 코드 5종 재검증 필요 —
FN-15/16/18처럼 의도적 설계일 수 있음, 소스로 재확인할 것), FN-08/20·RG-05~07/10·
APPR-02/03·NOTI-02·MAIL-02/03·BKP-04·PERF-02·SYS-09/10/11 등 Tier 3 소품 다수.

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
