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

**마지막 갱신**: 2026-08-10 · **단계**: **MEGA CYCLE B 완료(마지막 남은 Critical `FAIL-01`
포함), 다음 MEGA CYCLE 착수 준비**. Cycle 4의 소배치 방식을 그만두고(D-53) 제품 영역
단위로 넓게 조사·대량 수정·영역 종료 시 1회 배포로 전환 — Cycle 4 배치 1~6(UA/CORE/SEC
22건, 전부 배포·문서화 완료)은 그대로 유지. **MEGA CYCLE A**(AI Assistant / 러너 대화
엔진, RN-01~14 + Critical AI-30)는 구현·테스트·배포·부분 실환경검증까지 완료. **MEGA
CYCLE B**(제품 전역 실패 처리, Critical `FAIL-01` + FAIL-02/03 + 부수 발견 FN-51)도
구현·테스트·배포·실환경검증까지 완료 — **BACKLOG의 마지막 Critical이 이걸로 0건**이
됐다(남은 건 High 이하와 `OPS-06` 사용자 조치 항목뿐). 상세는 각 §MEGA CYCLE 섹션. MEGA
CYCLE A 검증 중 **배포와 무관한 실서버 인프라 문제 1건 발견**: `n8n` 계정 Claude CLI
미인증(`OPS-06`, **사용자 조치 필요**, 아직 미해결). 진행률 실측치는
[docs/PROGRESS_STATUS.md](PROGRESS_STATUS.md) 참고 · **브랜치**: `ui/mui-migration`

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
  **`OPS-06`으로 BACKLOG에 기록, 사용자 조치 필요**(서버에서 `n8n` 계정 `claude /login`
  재인증). 규칙 기반 경로에는 영향 없음.

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
