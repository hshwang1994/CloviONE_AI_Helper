# BACKLOG — 발견한 모든 문제와 개선사항

> 사용자가 알려준 문제뿐 아니라 **전수조사로 직접 발견한 것 전부**. 진입점은
> [WORK_STATE.md](WORK_STATE.md).
>
> **상태**: `발견` → `작업예정` → `작업중` → `구현완료` → `검증대기` → `배포완료` → `실환경검증완료`
> **코드를 고쳤다는 이유만으로 완료 처리하지 않는다.** `실환경검증완료`만 완료다.
>
> **근거 열**은 내가 직접 확인한 파일:줄이다. 근거가 "미확인"이면 착수 전에 재확인한다.
>
> 관련: [IDEAS_BACKLOG.md](IDEAS_BACKLOG.md)(미확정 아이디어, 다른 목적) ·
> [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)(구조적 한계) · [DECISIONS.md](DECISIONS.md)

**마지막 갱신**: 2026-08-08 (사이클 0) · **총 항목**: 220

---

## 요약

| 영역 | 항목 | 성격 |
|---|---|---|
| [DS 디자인 시스템](#ds--디자인-시스템) | DS-01~31 (31) | 토큰·Variant·Typography·Color·Card·반응형·다크. High 6 |
| [AI AI 도우미·채팅](#ai--ai-도우미채팅) | AI-01~50 (50) | 고장·아키텍처·기억·능력·프런트. High 11 |
| [FN 기능·API·DB](#fn--기능apidb) | FN-01~20 (20) | 고아 엔드포인트·죽은 조작판·죽은 스키마. High 2 |
| [SEC 권한·보안](#sec--권한보안) | SEC-01~05 (5) | 권한 경계·스코프·CSRF. High 1 |
| [IA 정보구조](#ia--정보구조검색) | IA-01~05 (5) | 관리자 IA·검색 역할 분리 |
| [QA 검증 인프라](#qa--검증-인프라) | QA-01~09 (9) | 배포 동기화·시각 QA·시간 의존 테스트·번들 무결성. High 4 |
| [DOC 문서 정합성](#doc--문서-정합성) | DOC-01~06 (6) | 코드와 어긋난 문서 |
| [VIS 실화면 판독](#vis--실화면-판독-사이클-0-서버-배포본) | VIS-01~23 (23) | **기계 검사 21종이 전부 통과한 화면**에서 눈으로 찾은 것 |
| [CORE `app/core/`](#core--appcore-전수조사-사이클-0) | CORE-01~12 (12) | **한 번도 감사된 적 없는 인프라 계층.** High 1 |
| [UB 미감사 batch 1](#ub--미감사-모듈-전수조사-사이클-0-batch-1) | UB-01~30 (30) | announcements·impersonation·quotas·observability·templates·prompts·conversations. High 3 |
| [UA 미감사 batch 2](#ua--미감사-모듈-전수조사-사이클-0-batch-2) | UA-01~29 (29) | home·assistant·reports·sprints·trash·documents·backups·org·offboarding·audit·llm. High 3 |

**사이클 0에서 새로 드러난 것 중 가장 무거운 것**(전부 직접 재확인함):
`UA-01` 전사 생산성 데이터가 아무 인증 사용자에게 노출 · `UA-02` org 스코프 관리자가 스프린트
스코프를 통째로 우회 · `UA-03` 백업이 도는 동안 앱의 모든 쓰기가 잠김 · `UB-01` 부서 admin이
전사 배너를 띄움 · `UB-02` 전역 AI 상한이 강제와 표시가 서로 다른 것을 셈 · `UB-03` 로그아웃이
임퍼소네이션 기록을 영원히 "진행 중"으로 남김 · `CORE-01` 워커 리스를 두 프로세스가 동시에 잡음 ·
`SEC-01` Notion 신원 결속에 권한 경계 누락.

우선순위는 [WORK_PLAN_INDEX.md](WORK_PLAN_INDEX.md)의 사이클 순서를 따른다.

**`발견`이 아닌 항목**(사이클 0에서 처리):
- `QA-07` **구현완료** — 시간이 지나 스스로 깨진 프런트 테스트. 절대 날짜 픽스처를 상대값으로
  바꿔 고쳤고 해당 파일 5/5 통과 확인. 전체 스위트 재확인은 배포 게이트에서.
- `QA-01`·`QA-03`·`QA-04`·`QA-05` **작업예정** — 조사를 가능하게 하는 선행 작업.
- `DOC-02`·`DOC-05` **작업예정** — 사이클 0에서 문서 재편으로 처리 중.

---

## DS — 디자인 시스템

원칙: **공통화 ≠ 동일화.** 같은 의미는 같은 표현, 다른 의미·다른 중요도는 적절한 시각적 차이.
자세한 설계 방향은 [DECISIONS.md](DECISIONS.md) D-01~D-05.

| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| DS-01 | High | **기본 버튼이 `outlined`라 평범한 버튼까지 전부 테두리 상자**로 강조된다. 조회·이동·보조 작업이 주요 작업과 같은 무게로 경쟁 | `ui/kit.jsx:148-153` `default:{variant:"outlined"}` | 발견 |
| DS-02 | High | **`primary`와 `danger`가 둘 다 `contained`** — 위험 작업이 주요 작업과 같은 시각 무게. 위험은 무게가 아니라 의미로 구분돼야 한다 | `ui/kit.jsx:149-150` | 발견 |
| DS-03 | High | **표/그리드 내부 액션용 표현이 없다.** 행 안 버튼이 데이터보다 강조되고 행 높이를 키운다 | `BUTTON_VARIANT`에 해당 variant 없음 | 발견 |
| DS-04 | High | **Button에 `loading` 상태가 없다.** `DataScreen`이 라벨을 "처리 중…"으로 바꿔 대신한다(스피너·폭 유지가 계약에 없음) | `ui/kit.jsx:154-161`, `DataScreen.jsx:82-88` | 발견 |
| DS-05 | High | **`fontWeight`가 65개 파일에 8종 값으로 흩어져 있다** — 700(70회)·750(48)·800(30)·600(11)·400(8)·650(6)·500(3)·780(2). **≥700이 148회.** 토큰이 아니라 그때그때 고른 값이라 숫자·제목·라벨이 무차별로 굵어져 "중요한 것"이 안 보인다 | 전수 grep | 발견 |
| DS-06 | High | **관리자 registry 표 28개에 열 폭(`width`/`minWidth`) 지정이 0건.** `kit.jsx:498-502`가 바로 이 상태를 "제목이 세로로 무너진다(24px 폭에 11줄)"고 경고해 뒀다 | `screens/registry/*.js` 9파일 grep 0건 | 발견 |
| DS-07 | Med | 같은 역할의 섹션 제목이 **16/17/20px 3종**, `h2`/`h3`/무지정 혼재. 지역 재구현 5벌 | `Dashboard.jsx:67`, `Home.jsx:87`, `MyStats.jsx:62`, `Profile.jsx:62`, `AssistantPanel.jsx:259` | 발견 |
| DS-08 | Med | **시맨틱 색이 거의 안 쓰이고 브랜드 색이 강조용으로 남용.** `text.secondary` 65 · `primary.main` **21** · `error.main` 8 · `success.main` 4 · `warning.main` 2 | 전수 grep | 발견 |
| DS-09 | Med | **`lib/badges.js`가 `purple/teal/indigo/pink` 톤을 내는데 `kit.Badge`의 `TONE_COLOR`에 없어 문서 유형 8종 중 5종이 같은 회색**으로 렌더된다 | `lib/badges.js:14-23` vs `kit.jsx:129`; 호출부 `TeamDocs.jsx:336`·`TeamDoc.jsx:287`·`Board.jsx:395` | 발견 |
| DS-10 | Med | **`Drawer = Modal` 별칭** 때문에 `<Drawer>`가 6곳은 중앙 다이얼로그, 2곳은 진짜 사이드 드로어. `SubListDrawer`는 같은 것을 두 이름으로 동시 import | `ui/kit.jsx:917` | 발견 |
| DS-11 | Med | **표 구현 3벌** — `kit.DataTable` + `MyTickets.GroupedTickets` + `DevReport.TableWrap/Th`. `"(max-width:899.95px)"` 리터럴이 두 파일에 중복 선언 | `kit.jsx:415`, `MyTickets.jsx:197,222`, `DevReport.jsx:88-113` | 발견 |
| DS-12 | Med | **손수 만든 필터/툴바 9개** — `Search`, `Activity`(앱 유일 `ToggleButtonGroup`), `ChatRooms`, `Projects`, `SchedulerCalendar`, `Games`, `Trash`, `Offboarding`, `ConversationSidebar`. 공통 `FilterBarGrid`는 4곳만 사용 | `ui/FilterBar.jsx` 소비자 4개 | 발견 |
| DS-13 | Med | **탭 관용구 3종** — MUI `Tabs`(Project·AssistantPanel) / `ToggleButtonGroup`(Activity) / `AppShell` 수제 pill | `AppShell.jsx:308-321` | 발견 |
| DS-14 | Med | **빈 상태 8벌.** `EmptyState`가 31파일에 쓰이는데도 지역 구현이 남아 있다 | `NotificationBell.jsx:482`, `ChatRooms.jsx:141,180`, `ChatRoomMembers.jsx:243`, `chat/ConversationSidebar.jsx:175`, `chat/ResultsRail.jsx:42`, `game-room/ChatPanel.jsx:28`, `ChatPane.jsx:294`, `BoardPost.jsx:515` | 발견 |
| DS-15 | Med | **`ErrorState`에 `size`가 없어** 340px 팝오버에서 넘치고 `global.css`가 명시도 전쟁으로 덮는다(약 65줄) | `global.css:52-133` | 발견 |
| DS-16 | Med | **카드 유형이 `Card`+`StatCard` 둘뿐.** Metric/Status/Summary/Warning/Action/Content 구분 없이 숫자가 있으면 크게·굵게 처리 | `ui/kit.jsx:167,204` | 발견 |
| DS-17 | Med | **`Dashboard.jsx`(916줄)가 사실상 '관리자 전용 디자인 시스템'** — `DashSection`/`StatusTile`/`STAT_GRID` 등을 export해 5개 모듈이 의존 | `ops/Diagnostics.jsx`, `ops/JobQueuePanel.jsx`, `ops/Maintenance.jsx`, `ops/ServiceStatusPanel.jsx`, `DevReport.jsx` | 발견 |
| DS-18 | Med | **토큰이 4벌** — `ui/theme.js`(MUI rem) · `styles/tokens.css`(145변수) · `ui/density.js`(px→rem) · `app/static/css/tokens.css`(Jinja 사본) | | 발견 |
| DS-19 | Med | **`kit.css`가 `sx`와 동일 명시도(0,1,0)로 7요소에서 충돌** — 승자가 스타일 주입 순서에 달렸다(`.k-empty` flex vs grid, `.k-stat`, `.k-badge`, `.k-page-head`, `.k-field`, `.c-toolbar-card`, `.c-list-card`) | `ui/kit.css` | 발견 |
| DS-20 | Low | **`screens.css` 240클래스 중 138(58%)이 미참조.** 죽은 계열: `.chat-*` 30 · `.game-*` 25 · `.devrep-*` 12 · `.board-*` 13 · `.doc-*` 10 | `styles/screens.css` | 발견 |
| DS-21 | Med | **`.c-screen`이 유령 클래스** — 39곳에 붙어 있는데 기본 규칙이 없고 자식 margin 2줄뿐. 9개 화면은 아예 안 붙어 있어 페이지 리듬이 다르다. **주목할 상관관계: 시각 QA 밖에 있던 `SystemOps`·`SetupWizard`·`NotionConsole`·`LlmConsole` 4화면이 전부 `c-screen` 0건이고 그중 3개는 `EmptyState`도 0건이다** — 아무도 안 본 화면이 규약에서 가장 멀리 떠내려갔다. 검사 공백과 품질 드리프트가 같은 자리에 있다 | `styles/screens.css:307-308`; 4화면 직접 대조 | 발견 |
| DS-22 | Low | **`ui/Pager.jsx`가 `Activity.jsx`에 복붙**됐고 동작이 갈라졌다(원본은 1페이지에서 `null`, 복사본은 항상 렌더) | `Activity.jsx:175-189` vs `ui/Pager.jsx:18-24` | 발견 |
| DS-23 | Low | **관리자 표 안 링크가 브라우저 기본 파란/보라 밑줄** — `columnHelpers`가 맨 `<a>`/`<ul>`/`<div>`를 뱉고 `a{}` 규칙이 없다. `registry/shared.js:74-75`는 raw `style` 객체 | `data-screen/columnHelpers.jsx:17-23,66,75-86` | 발견 |

### DS 4K 스케일 레버가 깨진 지점 (실측으로 발견)
| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| DS-32 | **High** | **4K에서 `tiny_text` 검사가 사용자 콘솔 전 화면에서 실패한다**(3840×2160). 2026-08-04 전체 실행은 0건이었으므로 그 이후 회귀다. 원인은 **절대 px 글자 크기가 4K 레버를 무력화**하는 것: `--clv-root-fs`가 16→18→20px로 커져도 px로 박힌 글자는 그대로 남는다. 확정된 지점: **`app/TopSearch.jsx:68`의 `Ctrl K` 배지가 `fontSize:"11px"`** — 상단바라 **모든 SPA 화면에 있고**, 12px 하한을 어느 뷰포트에서도 밑돈다. 같은 파일 `:56`의 검색 placeholder도 `13px` 절대값이라 안 커진다. 더 넓게는 **`ui/kit.css`에 12/13/14px 절대값이 20군데 이상** 남아 있다(DS-19의 명시도 충돌과 같은 파일) | 하네스 실측 + 소스 확인. 레버 자체는 정상이고 번들에도 반영돼 있음을 확인함 | 발견 |

> **범인은 한 줄일 가능성이 매우 높다.** 앱 전체에서 12px 미만으로 렌더될 수 있는 글자를 전수로
> 좁혔다: 절대 px 글자크기는 `kit.css` 20곳 + JSX 5곳뿐이고 **그중 12px 미만은 `TopSearch.jsx:68`의
> `11px` 하나다**(나머지는 12·13·14·20·24·32·36px). rem 쪽도 최소가 `theme.js:361`의 `0.6875rem`
> = 4K에서 13.75px라 안전하다. 그리고 `tiny_text` 검사는 폭 ≥2200에서만 도는데, 그 배지는
> **상단바라 모든 SPA 화면에 있다** — 실패가 정확히 "SPA 전 화면, Jinja 로그인만 통과"인 것과 일치한다.
> → **한 줄 고치면 67건이 한 번에 사라질 것으로 본다**(고친 뒤 재실행으로 확인해야 함).
>
> 그래도 근본 대책이 따로 필요하다: 이 저장소가 4K를 위해 만든 유일한 장치가 "루트 폰트사이즈
> 하나로 글자·여백·간격이 같은 비율로 커진다"는 것인데(`styles/root.css` 주석), 절대 px이 하나
> 섞이는 것만으로 그 장치가 그 요소에서 무효가 된다. **px 글자 크기를 금지하는 정적 검사**가
> 있어야 다시 안 샌다(`scripts/static_checks.sh`에 21단계가 이미 있고 그중 여럿이 같은 취지다).

### DS 반응형 (규칙이 없어 고정값으로 때운 것)
| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| DS-24 | Med | **`xl`(1200~1536)이 가장 미지정** — 브레이크포인트 사용 `xs`136/`sm`77/`md`48/`lg`33 vs **`xl` 11**. 1280~1536이 가장 취약 | 전수 grep | 발견 |
| DS-25 | Med | **뷰포트 높이 계산이 흩어져 있다** — `Chat.jsx:132 calc(100vh-12rem/13rem)` 손튜닝 상수, `game-room/ChatPanel.jsx:24 45vh`, `ops/Diagnostics.jsx:331 60vh`, `OrgTree.jsx:271 70vh`. `theme.js`의 `FAB_CLEARANCE`는 **소비자가 0** | | 발견 |
| DS-26 | Med | **4K에서 본문이 3040px 폭으로 흐른다** — `PROSE_MAX_WIDTH`가 `Ticket`·`CommentThread`·`EditableBody`에만 적용되고 `TeamDoc`·`BoardPost` 본문엔 없다 | | 발견 |
| DS-27 | Low | 표 행 높이·밀도가 화면마다 다르고 0건/1건/대량 상태가 설계돼 있지 않다 | | 발견 |

### DS 다크 테마
| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| DS-28 | **Low** (하향) | **사이드바 배경이 3출처** — `theme.palette.sidebar.bg`는 정의만 되고 **한 번도 안 읽힌다**, `--sidebar-bg`(CSS), `AppShell.jsx:584 #1B2447` 리터럴(어느 팔레트에도 없는 값). ※ **실화면 확인 결과 눈에 보이는 결함은 없다** — 사이드바는 두 테마에서 의도대로 같은 짙은 남색이다. 유지보수 위험(죽은 팔레트 슬롯 + 리터럴)이지 사용자 결함이 아니므로 Med→Low로 내린다 | 라이트·다크 대조 확인 | 발견 |
| DS-29 | Med | **상단바 그라데이션이 사용자 accent를 무시**한다 — 청록을 골라도 상단바는 남색 고정. 실화면에서 라이트·다크가 **완전히 동일한 그라데이션**임을 확인했다(테마에도 반응하지 않는다). accent 설정이 버튼 색만 바꾸므로 "테마를 골랐는데 화면 상단은 그대로"가 된다 | `AppShell.jsx:496-498` + 라이트·다크 대조 | 발견 |
| DS-30 | Med | **`PROJECT_TONE_COLORS`의 주황 `#F08C00`이 라이트 테마에서 대비 2.48:1**(비텍스트 기준 3:1 미달). 8색을 `surface`(라이트 `#FFFFFF`, 다크 `#11182D`)에 대고 직접 계산한 결과: **다크는 8색 전부 통과**(최저 3.11), **라이트에서 주황 1색만 실패**. ※ 이전 조사에서 "다크에서 2.4:1"이라는 보고가 있었으나 **재계산 결과 틀렸다** — 실제로 문제는 반대 테마다. 8색이 두 테마에 같은 값을 쓰는 구조 자체가 원인이다 | `chat-helpers.js:275-276`, 사용처 `chat/TicketCard.jsx:90`. 대비값 직접 계산(WCAG 상대휘도) | 발견 |
| DS-31 | Low | 다크에서 안 바뀌는 고정색: `Mascot` FAB `rgba(255,255,255,.96)` · `ImageLightbox` 배경 `rgba(10,16,38,.92)` · `TopSearch` `#fff` | `Mascot.jsx:254,264`, `ImageLightbox.jsx:49`, `TopSearch.jsx:35,38` | 발견 |

> **보존할 올바른 패턴**: `ui/charts/base.jsx:47-63` `resolveChartColor`가 다크에서 묻히는 고정
> 회색을 `text.disabled`로 라우팅한다. 이것을 시스템 전체 규칙으로 승격한다(DECISIONS D-03).
>
> **다크 테마는 실제로 잘 돼 있다(확인함).** 관리자 대시보드를 라이트/다크로 나란히 놓고 본 결과
> 팔레트 전환·표면 단차·시맨틱 색(정상 초록·위험 빨강·주의 주황)이 전부 제대로 살아 있고 1920에서
> 기계 검사도 통과한다. 다크는 **회귀시키지 말아야 할 강점**이지 고칠 대상이 아니다 —
> 위 DS-28을 Low로 내린 이유가 그것이다.

---

## AI — AI 도우미·채팅

**구조 요약**: LLM 챗 제품이 아니다. 한국어 키워드 규칙엔진(`runner/claude-work-assistant/assistant.py`
약 5,890줄, `route_request` 약 370줄)이 Notion 티켓 CRUD 앞에 서 있고, Claude는
`claude -p --model sonnet --max-turns 1 --tools "" --no-session-persistence --json-schema`로
**원샷·도구없음·세션없음·스트리밍없음** 호출된다. LLM은 라우팅의 **맨 아래 폴백**이다.

경로: 브라우저 → `POST /api/conversations/{id}/messages`(202) → 잡 큐(단일 워커) →
n8n `:5678` webhook → 러너 `:8789/v1/assistant/message` → `claude -p` → 역순 → 브라우저 1.5초 폴링.

### AI 지금 고장난 것
| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| AI-01 | High | **`assistant_narrative_enabled`를 켜도 문장이 0개 나온다.** `assistant_runner_url` 기본값이 `/v1/assistant/summarize`인데 러너는 `/message`·`/context/sync`·`/quiz` **셋만** 받고 나머지는 404 | `app/core/config.py:132` vs `assistant.py:5707` (양쪽 직접 확인) | 발견 |
| AI-02 | High | **타임아웃 역전**: 플랫폼 180s < n8n 240s → 플랫폼이 먼저 포기하고 **동일 본문을 재전송**하는데, 중복 쓰기 방지는 n8n **휘발성 `staticData`**에만 있다(n8n 재시작 시 소멸). 우리가 보내는 `idempotency_key`를 n8n은 **읽지도 않는다** → Notion 중복 티켓 위험 | `config.py:30`, n8n 노드 240000ms, `assistant.py:25` | 발견 |
| AI-03 | Med | **메시지 길이 상한이 3개** — Pydantic 20,000 / 실제 5,000 / 러너 12,000 | `chat/router.py:66`, `config.py:36`, `assistant.py:32` | 발견 |
| AI-04 | Low | 시드된 러너 행이 없는 기능을 광고 — `actions:["chat","dispatch","summarize","compose_report"]` 중 `chat`만 실재 | `scripts/seed_content.py:85-89` | 발견 |

### AI 아키텍처
| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| AI-05 | High | **스트리밍이 없다.** `subprocess.run`이 전체 출력을 블록하고 전송은 202+1.5초 폴링. 답이 통째로 튀어나온다. 저장소 전체에 SSE/WebSocket 0건 | `assistant.py:2397`, `chat-helpers.js:102` | 발견 |
| AI-06 | High | **중단(Stop) 버튼이 없다.** 브라우저→잡→n8n→러너 어디에도 abort 경로가 없다. `lib/api.js`에 `AbortController` 0건 | 전수 grep | 발견 |
| AI-07 | High | **모든 채팅이 단일 워커 한 슬롯에 직렬화.** `schedule_run` 잡이 최대 3600초 그 슬롯을 잡을 수 있고 그동안 전 사용자 채팅이 `pending` | `jobs/worker.py:62-123`, `worker_main.py:280-287`, `schedules/router.py:66` | 발견 |
| AI-08 | Med | **진행 표시가 가짜.** 세 점 애니메이션이 "마지막 메시지가 사용자 것"이라는 불리언 하나에서 나온다. 러너가 주는 `timing.ai_ms`를 받아 저장하면서도 화면에 안 쓴다 | `chat/MessageThread.jsx:172-197`, `useChat.js:130` | 발견 |
| AI-09 | Med | **답을 기다리는 동안 아무것도 못 한다** — 컴포저 잠기고 Enter가 토스트로 거부(최대 10분) | `useChat.js:414,475` | 발견 |
| AI-10 | Med | 러너 동시성 `BoundedSemaphore(2)`(퀴즈와 공유), 3번째 요청은 즉시 429. 소켓 backlog 5(stdlib 기본값 미변경) | `assistant.py:42,5810,5888` | 발견 |
| AI-11 | Med | 폴링이 5회 연속 실패하면 **자동 폴링을 포기**하고 수동 새로고침만 남는다 | `chat-helpers.js:102-109` | 발견 |
| AI-12 | Low | n8n 캐시가 5분 TTL이라 그보다 긴 간격이면 **Notion 전체 프로젝트+전체 태스크를 `returnAll`로 통째로 덤프**한다 | n8n 워크플로 노드 | 발견 |

### AI 기억·문맥 (사용자 체감 "대화가 안 이어진다"의 정체)
| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| AI-13 | High | **플랫폼이 대화 이력을 0건 보낸다.** 연속성이 전적으로 러너의 별도 SQLite에 있다 | `chat/service.py:209-230`; 계약 테스트가 `"context" not in body`로 못박음 | 발견 |
| AI-14 | High | **모델 기억 = 최근 8턴 × 각 1,000자.** 게다가 **규칙엔진 턴은 이력에 안 들어가** 모델이 보는 대화에 **구멍**이 난다 | `assistant.py:3030,3058-3066` | 발견 |
| AI-15 | Med | 문맥이 250,000자를 넘으면 요약이 아니라 **`conversation_history`를 통째로 삭제** | `assistant.py:215-227` | 발견 |
| AI-16 | High | **대화를 지워도 러너 사본은 안 지워진다** — `clear_persisted_context`가 정의만 되고 **호출 0회**. 대화 전문과 이미지 분석 노트가 `/var/lib/n8n/…state.sqlite3`에 무기한 잔존 (**프라이버시 결함**) | `assistant.py:267`, `chat/service.py:109-114` | 발견 |
| AI-17 | Med | 러너 상태가 유실되면 **승인 턴이 아무 티켓도 안 만드는데 플랫폼은 그것을 알 방법이 없다** | 계약 테스트 주석 | 발견 |
| AI-18 | Med | 대화 목록이 **100개 하드캡**, 페이지네이션 없음. 자동 제목은 첫 메시지 `content[:60]` | `chat/service.py:46,192` | 발견 |

### AI 능력
| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| AI-19 | High | **에이전틱 도구 사용이 전무** (`--max-turns 1`, `--tools ""`). 유일한 도구는 비전용 `Read` | `assistant.py:2364,2374,2604` | 발견 |
| AI-20 | High | **모델이 보는 데이터가 Notion 티켓·프로젝트뿐.** 플랫폼의 통합 검색 인덱스(`app/search/`)·문서(`team_docs`)·게시판·승인·일정·조직/사람·알림에 **접근 불가**. ← 업무 도우미의 핵심 결손 | `chat_message.py` import 목록 | 발견 |
| AI-21 | Med | 티켓 800 / 프로젝트 300 상한 초과 시 `tickets_truncated`로 **개수 질문을 거절**한다 | `assistant.py:3032-3033,2689` | 발견 |
| AI-22 | Med | **프롬프트 관리 콘솔이 채팅에 아무 영향이 없다**(죽은 조작판). `get_published` 소비자는 문서 생성뿐이고 채팅 프롬프트는 러너에 하드코딩 | `documents/service.py:86,91`; `assistant.py:2328,2509,2674,2734` | 발견 |
| AI-23 | Med | **모델이 고정 안 된 별칭** `ASSISTANT_MODEL=sonnet`(systemd env) — 관리 콘솔에서 못 바꾸고 버전 관리·감사도 안 된다 | `assistant.py:24`, systemd 확인 | 발견 |
| AI-24 | Low | 못 하는 것이 코드에 명시: 이메일·Teams·캘린더 발송 · 티켓 삭제 · 일괄 수정 · 실시간 정보 | `assistant.py:511-515,5365-5379,2992-2996,2679` | 발견 |

### AI 프런트 — 드로어가 스텁 (클로비 버튼 3개 중 2개가 여기로 간다)
| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| AI-25 | High | **드로어가 리치 텍스트를 0으로 렌더**(`pre-wrap` 한 줄) — 티켓 카드·프로젝트 카드·Notion 링크·선택지 칩·실패 표시·재시도·복사·타임스탬프를 **전부 버린다** | `AssistantDrawer.jsx:165-167` | 발견 |
| AI-26 | High | **드로어에 새 대화 버튼도 대화 목록도 없다.** 앱 로드 시 마지막 대화가 자동 복원돼 **한 스레드에 영구히 갇힌다**(빈 상태·제안 칩으로 돌아갈 길이 없음) | `useChat.js:300-309`, `AssistantDrawer.jsx:90,144,174` | 발견 |
| AI-27 | High | **드로어 컴포저가 단일 행 `InputBase`** — 여러 줄 불가. **IME 가드가 없어 한글이 조합 중 전송된다**(전체화면엔 가드 있음) | `AssistantDrawer.jsx:189-193` vs `Chat.jsx:346` | 발견 |
| AI-28 | Med | 드로어에 붙여넣은 이미지가 **보이지도 지워지지도 않고** 전송 버튼이 그것을 무시한다(텍스트 없이 이미지만 붙이면 갇힌다) | `AssistantDrawer.jsx:80,206` vs `Chat.jsx:357` | 발견 |
| AI-29 | High | **429/503 한 번에 드로어 컴포저가 영구 잠김.** 안내와 해제 버튼이 전체화면에만 있고 `keepMounted`라 페이지 이동으로도 안 풀린다 — **새로고침만이 해법** | `useChat.js:473-475`, `AssistantDrawer.jsx:198,206` | 발견 |
| AI-30 | Med | **"현재 문맥: X"가 거짓말.** 라우트 정보는 어디로도 전송되지 않는데 화면 3곳이 "지금 보고 있는 화면 기준으로 도와드려요"라고 약속한다 | `AssistantDrawer.jsx:69-72,118,148-150`, `ConversationSidebar.jsx:167-168` vs `useChat.js:167` | 발견 |
| AI-31 | Med | "전체 화면으로 열기"의 `?c=` 인계가 **죽은 코드** — `Chat.jsx`/`useChat.js`가 쿼리 파라미터를 안 읽는다(sessionStorage 덕에 우연히 동작) | `AssistantDrawer.jsx:123`, grep 확인 | 발견 |
| AI-32 | Med | 드로어가 **항상 마운트**돼 모든 화면에서 `/api/conversations` + 메시지 요청이 나간다 | `AppShell.jsx:652-654`, `useChat.js:84-88,300-309` | 발견 |

### AI 프런트 — 렌더링·기본 기능
| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| AI-33 | High | **마크다운이 아니라 정규식 5개짜리 줄 분류기.** 굵게·기울임·`#` 제목·표·인용·`[text](url)`·인라인 코드·이미지 **전부 미지원** | `chat-helpers.js:189-216` | 발견 |
| AI-34 | High | **펜스 코드블록이 지원 안 되는 정도가 아니라 망가진다** — 파서에 fence 상태가 없어 `- foo`는 불릿이 되고 `def f(x):`는 정의목록 행이 된다. 문법 강조·코드 복사 버튼도 없다 | `chat-helpers.js:218-246` | 발견 |
| AI-35 | Med | **Notion 외 링크는 클릭조차 안 된다** — `github.com`·사내 위키·Jira가 복사 버튼으로 격하 | `chat-helpers.js:385-389`, `chat/links.jsx:15-33` | 발견 |
| AI-36 | Med | **재생성 없음**(재시도는 `failed`일 때만) · **내 메시지 수정 후 재전송 없음** · **메시지 삭제 없음** · **분기 없음** | `MessageThread.jsx:111`, `chat/service.py:240-241`, `conversations/models.py:33-47` | 발견 |
| AI-37 | Med | **대화 내보내기/전체 복사 없음**(메시지 단위 복사만) · **공유 링크 없음** · **피드백(👍/👎) 없음** | `MessageThread.jsx:149-155` | 발견 |
| AI-38 | Med | **대화 본문 검색이 없다** — 제목만 클라이언트 측 부분일치 | `ConversationSidebar.jsx:115-116` | 발견 |
| AI-39 | Med | **첨부가 이미지 3종(PNG/JPEG/WebP)뿐** — PDF·CSV·DOCX·TXT·코드 파일 불가. 업무 도우미의 상한 | `app/chat/attachments.py:21`, `Chat.jsx:323` | 발견 |
| AI-40 | Med | 보낸 이미지가 복구 불가 — 서버는 파일명만 저장한다(스크롤 올려도 스크린샷을 다시 못 본다) | `MessageThread.jsx:85-95` | 발견 |
| AI-41 | Med | **결과 카드에서 앱 내 티켓으로 딥링크가 없다**(Notion 외부 링크만). `AssistantPanel`은 `#/tickets/{id}`로 가는데 채팅 카드는 안 간다 | `chat/TicketCard.jsx:110-117` vs `AssistantPanel.jsx:58` | 발견 |
| AI-42 | Med | **결과에서 직접 실행이 없다**(배정·상태변경·댓글). "상세" 버튼조차 `"N번 상세 보여줘"` 텍스트 왕복이다 | `chat/TicketCard.jsx:114` | 발견 |
| AI-43 | Med | **결과 레일이 2200px 이상에서만 보인다** — 1080p/1440p 사용자는 존재 자체를 모른다 | `Chat.jsx:78`, `chat/layout.js:9-14` | 발견 |
| AI-44 | Low | 남은 AI 쿼터가 채팅에 표시되지 않는다(백엔드는 예약·차감한다) | `chat/router.py:160,212`; 프런트 grep 0건 | 발견 |
| AI-45 | Low | 어시스턴트에 **기능 플래그가 없다** — `NAV_FEATURE_FLAG`에 `/chat`이 없어 테넌트별로 못 끈다 | `navConfig.js:277-286` | 발견 |
| AI-46 | Low | 슬래시 명령 없음 · 드래그앤드롭 없음 · 음성 없음 · 모델 선택/커스텀 지시 없음 | | 발견 |
| AI-47 | Low | 제안 칩이 **두 벌로 갈렸다**(`chat-helpers.js:114-124` 7개 vs `AssistantDrawer.jsx:35-40` 4개) | | 발견 |
| AI-48 | Med | `processing` 상태로 멈춘 메시지는 **사용자가 복구할 수 없다** — 재시도는 `failed`만 허용, 스윕은 3900초 뒤 | `chat/service.py:240-241`, `jobs/repository.py:31` | 발견 |
| AI-49 | Low | 빈 `{}` 2xx 응답이 성공으로 처리되고 사용자는 "답을 돌려주지 않았습니다"를 본다 | `chat_message.py:102-103,234` | 발견 |
| AI-50 | Med | **채팅 → 실제 Notion 티켓 생성이 한 번도 실물 검증된 적 없다** | `WORK_PLAN_INDEX.md` §7, 계약 테스트 하단 체크리스트 | 발견 |

> **보존할 강점**: 전체화면 채팅의 폴링 백오프 · 멱등키 재사용 · 첫 전송 실패 시 고아 대화 정리 ·
> IME 가드 · 동시 전송 3중 차단 · `useChat` 상태기계 공유. 문제는 **분배**다 — 드로어가 상태기계만
> 재사용하고 표현층을 다시 만들었다.

---

## FN — 기능·API·DB

| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| FN-01 | High | **메일 모듈에 UI가 0개.** `GET /api/admin/mail/status`·`POST /test`를 부르는 화면이 없고 `setup/probes.py`의 7개 프로브에도 메일이 없다 → SMTP가 틀리면 **비밀번호 재설정 메일이 조용히 안 간다**(승인 알림·백업 실패 알림도 같은 큐) | `app/mail/router.py:45,54`; 프런트 grep 0건 | 발견 |
| FN-02 | High | **`config/allowed-services.json`에 `api.anthropic.com:443`이 없다.** `llm/api_backend.py:50`이 그 호스트를 부른다 → `llm_backend=api`는 **영구 실패**하고 규칙기반 요약으로 조용히 대체돼 관리자가 원인을 알 길이 없다(allowlist UI 자체가 없다) | 파일 직접 확인 | 발견 |
| FN-03 | Med | **고아 엔드포인트 — 문제를 고치려고 만들었는데 부를 방법이 없다**: `POST /api/tickets/sync`(주석: "이 버튼이 없어서" 문제였다고 적힘) · `POST /api/search/reindex` · `DELETE /api/notifications/{id}`(주석: "알림이 무한정 쌓였다") | 프런트 grep 0건 (직접 확인) | 발견 |
| FN-04 | Med | **프로젝트 "보관"을 시킬 방법이 없다** — 화면엔 "보관됨" 배지와 "보관한 프로젝트 포함" 체크박스가 있는데 `DELETE /api/projects/{id}`(archive)를 부르는 UI가 없다 | `Projects.jsx:147,238-242`; `projects/router.py:243` | 발견 |
| FN-05 | Med | **AI 쿼터 화면에 실사용량이 없다** — `GET /api/admin/ai-quotas/usage`를 안 부르고 상한만 보여준다(운영자가 원하는 유일한 숫자가 없음) | `quotas/router.py:129` vs `registry/platform.js:214` | 발견 |
| FN-06 | Med | 프로젝트 진척·헬스 엔드포인트 3종이 고아 — `progress/recompute`, `health/snapshot`, `health/history`. 결과적으로 `project_health_snapshots`는 영원히 빈 테이블 | `projects/router.py:282,524,555` | 발견 |
| FN-07 | Med | **문서 "재시도"가 `/{id}/retry`가 아니라 `/generate`를 호출** → 재시도가 아니라 새 생성. 멱등성·연결이 사라진다 | `registry/automation.js:282-283` vs `documents/router.py:148` | 발견 |
| FN-08 | Med | **러너 레지스트리가 죽은 조작판** — CRUD·enable/disable·health·rollback UI가 완비인데 실제 러너를 부르는 두 기능은 `settings.game_runner_url`·`assistant_runner_url`을 **직접 읽어 레지스트리를 우회**한다. 화면에서 base_url을 바꿔도 아무 일도 안 일어난다 | `games/ai.py`, `assistant/narrate.py`, `config.py:122,132` | 발견 |
| FN-09 | Med | **알림 5종 누락**: 티켓 배정 · 문서 생성 성공 · 오프보딩 후임자 · AI 쿼터 소진 · **백업 실패(예외를 삼키고 로그만)** | | 발견 |
| FN-10 | Med | **감사 로그 보존일수 설정이 아무 일도 하지 않는다**(자동 아카이브가 없다). 그 사실이 화면에 안 적혀 있어 설정한 사람은 동작한다고 믿는다 | `KNOWN_LIMITATIONS.md` §8 | 발견 |
| FN-11 | Med | 승인 **위임받은 운영자에게 승인/거절 버튼이 없다**(서버는 delegation-aware로 완전히 동작) | 라운드 9 보고 | 발견 |
| FN-12 | Med | **"승인 대기" 사이드바 배지가 실제 대기 건수가 아니라 개인 안읽음 알림수** — 다른 관리자가 처리해도 안 사라진다 | 라운드 9 보고 | 발견 |
| FN-13 | Med | 워크플로 실행 이력을 `/jobs`에서 **역추적할 방법이 없다** | 라운드 9 보고 | 발견 |
| FN-14 | Med | `Trash` 복구/영구삭제가 **문서 상세 캐시를 못 씻는다**(트래시 API가 `notion_page_id`를 안 준다 — API 확장 필요) | 라운드 9 보고 | 발견 |
| FN-15 | Low | **죽은 테이블 `project_members`** — 모델·마이그레이션(`0044`)·인덱스·`MEMBER_*` 상수 전부 있는데 읽기 0·쓰기 0 | `projects/models.py:203-225`; grep 확인 | 발견 |
| FN-16 | Low | **죽은 컬럼 `ticket_cache.scope_dept_id`** + 인덱스 — `core/scope.py:139`가 이미 "아무도 안 읽는 컬럼"이라 지목. 미러 동기화마다 쓰기 비용만 | `tickets/models.py:79`, `0023` | 발견 |
| FN-17 | Low | **`app/policies/`가 0바이트 빈 패키지** — 실제 기능은 `app/prompts/`에 있다. 혼동만 유발 | | 발견 |
| FN-18 | Low | `limited_service_actions_enabled` 플래그의 **소비자가 0**(레지스트리가 정직하게 `has_consumer:false`로 표시는 한다) | `core/feature_flags.py:76-82` | 발견 |
| FN-19 | Low | `restore_rehearsals`는 `scripts/restore_rehearsal.py`(cron/수동)만 쓴다 — 그게 안 걸려 있으면 "복구 리허설" 화면이 영구히 빈 화면인데 앱 안에 채울 방법이 없다 | `backups/router.py:89,116` | 발견 |
| FN-20 | Low | 토너먼트 개별전 제출에 경합이 남아 있다(RPS/퀴즈는 CAS로 해결됨) | 라운드 12 커밋 | 발견 |

---

## SEC — 권한·보안

| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| SEC-01 | **High** | **`notion_mapping` 쓰기 4종(`verify`/`map`/`unmap`/`resolve-conflict`)이 `ensure_can_manage_target`을 호출하지 않는다.** 같은 동작의 다른 구현(`users/router.py:693`)에는 있다 → 부서범위 `admin`이 `system_admin`의 Notion 신원 결속을 바꿀 수 있고, **티켓 귀속·오프보딩이 그 결속을 키로 쓴다**. 게다가 UI가 실제로 쓰는 경로가 가드 없는 쪽이다 | `notion_mapping/router.py:203,220,241,254` — grep 0건(직접 확인) | 발견 |
| SEC-02 | Med | `GET /api/admin/jobs/stats`만 `admin_scope`를 무시한다(형제인 목록·상세는 `visible_user_ids`로 스코프). 부서범위 admin이 전역 큐 깊이·실패 수를 본다 | `jobs/router.py:152` vs `:112,157` | 발견 |
| SEC-03 | Med | **`GET /api/admin/impersonation/state`가 GET 안에서 쓴다**(`read_count += 1`) → `require_csrf`가 안전 메서드를 통과시키므로 CSRF 무방비. 저장소 자체 규칙(`notion_mapping/router.py:192-195`)에 위배 | `impersonation/router.py:48,61-63` | 발견 |
| SEC-04 | Low | "강제 동기화" 권한 기준이 모듈마다 다르다 — `tickets/sync`·`team-docs/sync`·`search/reindex`는 operator+, `notion-mapping/sync`는 admin+. 근거가 문서화돼 있지 않다 | | 발견 |
| SEC-05 | Low | 라운드 13·14가 "리포트만" 하고 남긴 것: 세션 만료 미필터링 · 아바타 조회 시 `active` 미확인 · 위임 취소 시 만료일 표시 오류 · allowlist 캐시 staleness | 커밋 본문 | 발견 |

> **확인된 강점(회귀시키지 말 것)**: CSRF 커버리지에 빈틈 없음(26개 라우터 레벨 + 나머지 개별) ·
> 스코프 위반 시 403이 아니라 **404**(열거 방지) · 첨부/이미지 서빙이 부모 객체 가시성을 재유도 ·
> 라우터 미등록 모듈 0건 · `app/` 전체에 `TODO`/`FIXME`/`XXX`/`HACK` **0건**.

---

## IA — 정보구조·검색

| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| IA-01 | Med | **관리자 메뉴 약 45항목 중 28개가 "표 하나" 화면**이고 같은 업무가 여러 메뉴로 흩어져 있다: 프롬프트/정책/템플릿/프롬프트사용통계/정책사용통계 **5메뉴**(하나의 콘텐츠 자산 흐름) · 백업/복구리허설/유지보수/진단/시스템설정/초기설정 **6메뉴**(전부 시스템 운영) · 승인/승인위임 2 · 감사로그/감사이상징후 2 | `navConfig.js`, `registry/*.js` 28키 | 발견 |
| IA-02 | Med | 스케줄 → 실행 달력 → 작업 큐 → 문서 자동생성이 **하나의 실행 흐름인데 서로 오갈 길이 없다**(FN-13과 같은 뿌리) | | 발견 |
| IA-03 | Med | **상단바 검색·`/search`·커맨드 팔레트의 역할이 섞여 있다**(콘텐츠 검색/기능 검색/메뉴 이동). 라우트·메뉴를 나열하는 것이 좋은 검색 UX인지부터 판단 필요 | `TopSearch.jsx`, `Search.jsx`, `CommandPalette.jsx` | 발견 |
| IA-04 | Med | 사용자 콘솔과 관리자 콘솔의 **조회·상세·편집·등록·삭제·위험작업 UX가 서로 다른 제품처럼** 보인다(관리자는 `DataScreen` 한 벌, 사용자는 화면마다 수제) | | 발견 |
| IA-05 | Low | `MIN_FTS_CHARS=3`이라 2글자 한글 질의는 FTS를 못 타고 LIKE로 빠지는데 **그 사실이 화면에 안 적혀 있다** | `app/search/query.py:27,64` | 발견 |

> 참고: 조직 관리는 이미 3메뉴를 1화면(`OrgConsole`)으로 합친 전례가 있고 **그 방향이 옳았다**.

---

## QA — 검증 인프라

| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| QA-01 | High | **테스트 서버가 HEAD가 아니다** — 라운드 9~14 미배포. 조사 신뢰도 0 | 해시 비교(직접 확인) | 작업예정 |
| QA-02 | High | **실브라우저 E2E가 수행된 적 없다.** `tests/smoke/`는 **빈 디렉터리**라 `pytest.ini`의 `-m "not smoke"`가 아무것도 거르지 않는다 | `KNOWN_LIMITATIONS.md` §7 | 발견 |
| QA-03 | Med | **QA 하네스가 자체서명 HTTPS를 못 탄다**(`urlopen` + `new_context()`에 TLS 예외 없음) → 서버를 직접 못 겨눔. SSH 터널로 우회 | `scripts/ui_qa/run.py:52` | 작업예정 |
| QA-04 | Med | **QA 하네스에 라우트 7개가 빠졌다** — `/projects`, `/projects/:id`, `/ideas`, `/notion-console`, `/llm-console`, `/system`, `/setup`. **화면 코드 약 2,600줄이 시각 검사 밖** | `scripts/ui_qa/routes.py` vs 실제 라우트 | 작업예정 |
| QA-05 | Med | **QA 하네스가 역할 1종(system_admin)으로만 돈다** — 역할별 메뉴 노출·데이터 범위·403 막다른 길을 실물에서 못 본다 | `scripts/ui_qa/auth.py:44` | 작업예정 |
| QA-06 | Med | **전체 백엔드 스위트가 HEAD에서 완주된 적 없다**(라운드 14가 환경 이벤트로 두 번 중단) | 커밋 본문 | 작업중 |
| QA-07 | **High** | **시간이 지나면 저절로 깨지는 테스트.** `ops-service-status.test.jsx`가 `last_backup_at: "2026-08-01T00:00:00"` 절대 날짜를 박아 뒀는데 `opsHelpers.js:158`의 판정은 `daysSince(...) > BACKUP_STALE_DAYS(=7)`라는 **상대** 기준이다 → 2026-08-07에 작성돼 **다음 날 스스로 깨졌고**, `final_verify.sh`가 막혀 **배포까지 멈췄다**. 프런트 스위트가 "green"이라던 기록이 하루 만에 거짓이 된 것 | 재현·수정·재검증함(아래) | **구현완료** |
| QA-09 | **High** | **번들 무결성 검사가 모든 번들에서 항상 1건 실패한다.** `build-bundle.sh:59`가 `find . -type f -exec sha256sum {} + > MANIFEST.sha256`라 셸이 find보다 먼저 만든 **빈 매니페스트 자신**을 목록에 넣고 그때의 해시를 적는다 → 다 쓰고 나면 내용이 달라져 **자기 자신과 영원히 불일치**. 서버에서 실측: 1,426개 중 1개 실패, 실패한 것이 `./MANIFEST.sha256`. `MAINTENANCE_PLAYBOOK.md` §2-3이 이 명령을 **배포 전 무결성 확인 단계**로 적어 뒀다 → **늘 실패하는 검사는 없는 검사보다 나쁘다**: 운영자가 그 한 줄을 정상으로 학습하면 진짜 깨진 번들도 똑같아 보인다 | 서버 실측 + 스크립트 확인 | **구현완료** (`! -name MANIFEST.sha256` 추가 + `tests/regression/test_bundle_manifest_self_reference.py` 3건으로 핀) |
| QA-08 | Med | QA-07의 **구조적 원인**: 프런트에 시계 주입 관례가 없다. 백엔드는 `tests/fakes/clock.py`를 두고 결정론을 강제하는데 프런트는 `vi.setSystemTime`을 **172파일 중 5개**만 쓴다. 절대 날짜 픽스처는 **55개 파일**에 있다. 상대 시각 헬퍼(`Dashboard.daysSince`, `lib/format.js:79`, `registry/automation.js:112,336,358`, `registry/integrations.js:144`, `chat-helpers.js:38,94`, `LoginHandoff.jsx:58`)와 만나는 조합만 위험하다 — 이번에 전수 대조해 **활성 rot는 1건뿐**임을 확인했고(`scheduler-calendar`의 "예정"은 서버 `kind` 파생이라 안전) 나머지는 잠복이다. **잠복을 잡을 가드가 없다** | 전수 대조 | 발견 |

---

## VIS — 실화면 판독 (사이클 0, 서버 배포본)

기계 검사 21종이 **전부 통과한 화면**에서 내가 눈으로 찾은 것. 즉 "안 깨졌는가"와 "좋은 제품인가"가
다르다는 증거다. 출처: `dist/ui-qa-admin/c1-admin/` (role=admin, 실제 서버, 실제 데이터).

### `/projects` (1920×1080, light) — 한 화면에서 나온 것만 10건
| ID | 심각 | 문제 |
|---|---|---|
| VIS-01 | Med | **KPI 타일 8개 중 4개가 `0`**(완료·보류·계획·지연 마일스톤)인데 의미 있는 값과 **똑같은 시각 무게**를 갖는다. 게다가 "전체 22"와 "진행 22"는 **같은 수**라 타일 하나가 통째로 중복이다. 8칸을 쓰고 실제로 말하는 것은 3가지뿐 |
| VIS-02 | Med | **표의 두 열이 전 행 동일값이라 정보가 0이다** — `상태`는 22행 전부 "진행", `부서`는 22행 전부 "부서 미지정". 화면 폭의 약 1/4을 아무것도 구분하지 못하는 열이 쓴다 |
| VIS-03 | Med | **"상세" 버튼이 22번 반복되며 각 행에서 가장 무거운 요소**다(테두리 상자, 우측 고정 열). 정작 사용자가 찾는 프로젝트 이름과 시각적으로 경쟁한다 — DS-01(기본이 `outlined`)·DS-03(표 내부 액션 표현 없음)이 실제로 이렇게 보인다는 확인 |
| VIS-04 | Med | **Health 점수(35~100점)가 숫자만이라 위험도가 안 읽힌다.** 35점과 100점이 같은 굵기·같은 색이다. 바로 위 KPI 타일은 "Health 하위 3 **위험**"을 빨강으로 칠하는데 정작 어느 행이 그 3건인지 표에서 구분되지 않는다 |
| VIS-05 | Med | **"보관한 프로젝트 포함" 토글 하나가 전폭 카드를 차지한다**(그 안에 토글 + "총 22건"). 정보량 대비 공간이 과하다. 게다가 `FN-04`대로 **프로젝트를 보관시킬 방법이 UI에 없어** 이 토글은 영원히 켤 이유가 없다 |
| VIS-06 | Med | **떠 있는 마스코트가 표의 "상세" 버튼을 덮는다**(7행 NH손해보험 근처). 자동 `fab_overlap` 검사는 **통과**로 나왔다 — 검사가 최종 정지 위치만 보고 실제로 겹친 상태를 못 잡는다 |
| VIS-07 | Low | 사이드바에 **"문서" 그룹 아래 "문서" 항목**이 있어 같은 낱말이 두 줄 연속으로 보인다 |
| VIS-08 | Low | 페이지 설명 문단이 1920폭에서 **절반 지점에서 어색하게 줄바꿈**된다("…작업을 다시 세어 / 계산한 값이고,"). 산문 폭 규칙이 없다(DS-26) |
| VIS-09 | Low | KPI를 한정하는 주석("평균 진행률은 계산이 끝난 20건만 셌습니다…")이 **타일과 분리된 회색 작은 글씨**로 아래에 떨어져 있다. 정직한 문구인데 그것이 수식하는 숫자와 연결돼 보이지 않는다 |
| VIS-10 | Low | 값이 없는 타일에 **"아직 없음" 같은 처리가 없고 그냥 `0`**이다 — "재지 않았다"와 "재보니 0"이 구분되지 않는다(주석은 둘이 다르다고 말한다) |

> 이 10건 중 **기계 검사가 잡은 것은 0건**이다(그 화면은 21검사 전부 pass).
> `VIS-06`은 검사가 **틀리게 통과**시킨 경우라 검사 자체도 고쳐야 한다.

### `/schedules` (관리자 DataScreen 대표, 1920×1080, light)
| ID | 심각 | 문제 |
|---|---|---|
| VIS-11 | Med | **행에서 가장 눈에 띄는 것이 raw UUID다.** `대상 ID` 열의 `e037ecad-255b-…`가 **브라우저 기본 파란 밑줄 링크**로 그려져(DS-23의 실물 확인) 정작 사람이 찾는 스케줄 이름보다 강조된다. 사람에게 의미 없는 값이 화면에서 가장 강하다 |
| VIS-12 | Med | **10열 중 4열이 `-`**(다음 실행·마지막 실행·유효 기간)인데 전폭을 차지한다. 행이 1개인 표가 전폭 카드를 쓰고 그 아래로 **약 500px가 빈 흰 공간**이다. `FN-13`이 "워크플로 실행 이력을 역추적할 방법이 없다"고 한 바로 그 정보가 들어갈 자리가 비어 있다 |
| VIS-13 | Med | **이 설치의 유일한 자동화가 꺼져 있다**(`활성: 아니오`)는 것이 화면에서 가장 중요한 사실인데, 중립 회색 아웃라인 칩이라 **아무 강조가 없다**. 켜짐/꺼짐이 같은 무게다 |
| VIS-14 | Low | `0 9 * * 1` cron을 **원문 그대로** 보여 준다. 사람 말 번역이 없고, 정작 이름 열에 이미 "(월요일 09:00)"이 적혀 있어 **중복이면서 동시에 불친절**하다 |
| VIS-15 | Low | 페이지 최상단 안내 상자 "정해진 시간에 자동 실행을 예약합니다."는 **페이지 제목이 이미 말한 것**을 전폭 테두리 상자로 반복한다. 첫 화면 세로 공간의 순수 손실 |
| VIS-16 | Low | 필터 카드 안에서 "저장된 뷰 + 링크 아이콘"이 **자기 줄을 통째로** 쓴다. 데이터 1행짜리 화면에서 크롬이 콘텐츠보다 크다 |

> 관리자 사이드바 "운영" 그룹에 대시보드·알림·작업 큐·설정·감사 로그·백업·진단·유지보수·공지 배너·
> 기능 플래그·감사 이상 징후·복구 리허설 **12항목**이 한 묶음으로 들어 있다 — `IA-01`의 실물 확인.

### `/me` 사용자 홈 (1920×1080, light)
| ID | 심각 | 문제 |
|---|---|---|
| VIS-32 | **High** | **온보딩 투어 모달이 첫 진입 화면을 덮는다** — 하네스가 찍은 홈 스크린샷이 전부 **모달에 가려진 상태**다. 즉 지금까지의 자동 QA는 홈의 실제 내용을 **한 번도 검사하지 못했다**(그런데 `auth_ok` 포함 21검사는 전부 통과했다). 검사 하네스가 첫 방문 상태를 처리하지 못하는 구조적 공백 |
| VIS-33 | Med | **KPI 타일 6개가 전부 `0`이다**(오늘 마감·지연·진행 중·7일 내 마감·안 읽은 알림·안 읽은 채팅). 첫 화면에서 사용자가 얻는 정보가 0이고, `VIS-01`(프로젝트 8개 중 4개 0)보다 심하다. "값이 없다"와 "재보니 0"이 여전히 구분되지 않는다 |
| VIS-34 | Med | **같은 실패 문구가 한 화면에 두 번** — "티켓 소스를 읽지 못해 이번 주 진척을 계산할 수 없습니다."가 '이번 주 내 진척' 카드와 'AI 도우미' 카드에 각각. 그리고 AI 카드의 "오늘 마감 0건, 지연 0건, 진행 중 0건, 막힘 0건"은 **위 KPI 타일과 같은 숫자의 세 번째 표현**이다(`VIS-25`와 같은 패턴이 사용자 콘솔에서도 반복) |
| VIS-35 | Med | **오른쪽 열이 y≈900에서 끝나는데 왼쪽 열은 y≈1500까지 이어져** 우하단 약 600px가 빈 흰 공간이다. 2열 그리드가 높이를 조율하지 않는다 |
| VIS-36 | Med | **팀 채팅 카드가 "아직 메시지가 없습니다"를 말하는 데 약 500px를 쓴다**(빈 영역 + 컴포저). 정보량 대비 공간이 화면에서 가장 크다 |
| VIS-37 | Low | 게시판 카드가 `0 내 글 / 0 받은 댓글 / 0 조회` 세 숫자 아래에 "기능개선 · 서운경, 댓글 0"이라는 **다른 모양의 데이터**를 같은 카드에 밀어 넣는다 |
| VIS-38 | Low | AI 카드의 "'문장 요약 만들기'를 누르면 같은 숫자를 문장으로 옮겨 줍니다"는 정직한 문구이지만, `AI-01`에 따라 **그 버튼은 아무 문장도 만들지 못한다**(러너에 `/v1/assistant/summarize`가 없어 404). 화면이 약속하는 것과 동작이 어긋난다 |

### `/dashboard` 관리자 대시보드 (1920×1080, light) — 카드 유형 부재의 결정판
| ID | 심각 | 문제 |
|---|---|---|
| VIS-24 | **High** | **21개 타일이 전부 같은 카드다.** 6개 구역(확인 필요 1 · 지금 상태 5 · 작업 지표 4 · 현재 큐 2 · 인벤토리 3 · 시스템 리소스 4 · 내 업무 2)이 전부 흰 카드 + 큰 숫자 + 작은 라벨 + 꺾쇠다. **"4 실패 작업 위험"(지금 조치해야 함)과 "3 등록된 러너"(단순 재고)가 완전히 같은 무게**로 그려진다 — `DS-16`(카드 유형이 둘뿐)이 실제로 이렇게 보인다 |
| VIS-25 | **High** | **같은 숫자가 한 화면에 세 번 나온다.** `4 미해결 실패 작업`이 "확인이 필요한 항목"·"지금 상태"·"현재 큐 상태"에 각각. `8.5% 디스크 사용`은 "지금 상태"와 "시스템 리소스"에 두 번. `2 활성 워크플로`도 "지금 상태"와 "인벤토리"에 두 번. **`7/7 서비스 정상`은 타일 + 서비스 7행 + 도넛 차트로 세 번** 표현된다. 화면을 훑는 사람은 이것이 서로 다른 지표인지 같은 것인지 알 수 없다 |
| VIS-26 | Med | **숫자에 의미색을 붙이는 규칙이 안 읽힌다.** `100% 성공률`은 초록, `8.5% 디스크 사용`은 검정, `7/7`은 초록, `2 활성 워크플로`는 검정. 같은 백분율인데 하나는 초록 하나는 무채색이라, 색이 "좋음"을 뜻하는지 "이 지표는 중요함"을 뜻하는지 판단할 수 없다 — `DS-08`(색이 의미를 안 나른다)의 실물 |
| VIS-27 | Med | **구역마다 회색 각주가 따로 붙는다**(3개: "이 줄은 요약입니다…", "성공률은 최근 24시간에…", "티켓 소스를 읽지 못해…"). 타일에 붙지 않고 구역 아래에 떨어져 있어 어느 숫자를 한정하는지 시선으로 연결되지 않는다(`VIS-09`와 같은 패턴이 대시보드에서 3번 반복) |
| VIS-28 | Med | **"내 업무" 구역이 자기모순이다** — `3 차질 프로젝트 위험`·`0 지연 마일스톤` 타일을 보여 준 **바로 아래**에 "티켓 소스를 읽지 못해 내 업무를 셀 수 없습니다."라고 적는다. 셀 수 있다는 건지 없다는 건지 화면이 답하지 못한다 |
| VIS-29 | Low | **"최근 주요 변경" 3행이 전부 같은 액션**("사용자, 비활성화")이고, 각 행의 **오른쪽 끝이 잘린 raw UUID**(`23681bfc…`)다. 가장 오른쪽 = 가장 늦게 읽는 자리에 사람이 못 쓰는 값이 있다 |
| VIS-30 | Low | 마스코트 FAB이 "현재 큐 상태" 카드를 덮는다 — `VIS-06`과 같은 문제가 **다른 화면에서 반복**된다(개별 화면이 아니라 FAB 배치 규칙의 문제라는 증거) |
| VIS-31 | Low | "백업" 구역이 사실 한 줄("마지막 백업 · 확인됨 · 20일 전")에 전폭 카드를 쓴다. `20일 전`이 빨강인 것은 옳다(`BACKUP_STALE_DAYS=7`의 2배 초과) |

### `/chat` AI 도우미 빈 상태 (1920×1080, light)
| ID | 심각 | 문제 |
|---|---|---|
| VIS-17 | Med | **한 화면에 "대화를 시작하라"는 말이 3번** 나온다 — 헤더 우측 "대화를 시작해 보세요.", 가운데 "무엇을 도와드릴까요?", 좌측 사이드바 "위의 '새 대화'를 눌러 시작하세요.". 셋 다 같은 말이고 셋 다 다른 위치·다른 크기다 |
| VIS-18 | Med | **마스코트가 동시에 3개 보인다** — 가운데 큰 것, 좌하단 도킹 카드, 상단바 버튼. 게다가 **이미 AI 화면에 들어와 있는데** 좌하단 카드가 "현재 화면을 기준으로 도와드려요"라며 또 AI로 유도한다 |
| VIS-19 | Med | **`AI-30`(거짓말)의 실물 확인** — 대화 사이드바 빈 상태가 "지금 보고 있는 화면을 기준으로 물어볼 수 있습니다"라고 적혀 있다. 실제로는 라우트 정보가 **어디로도 전송되지 않는다**(`useChat.js:167`, `chat/router.py:64-68`) |
| VIS-20 | Med | **한국어 단어 중간에서 줄이 끊긴다** — 사이드바 문구가 "지금 보 / 고 있는 화면을 기준으로 물어볼 수 있습니 / 다."로 쪼개진다. `KO_WORD_BREAK`가 이 자리에 적용돼 있지 않다 |
| VIS-21 | Low | **화면의 약 30%가 시작 전부터 내비게이션 크롬**이다(좌측 나브 264px + 대화 목록 300px). 대화가 0개인데도 목록 칸이 고정 폭으로 자리를 잡고, 그 안에 "보관된 대화 보기" 체크박스가 **보관할 대화가 없는데도** 떠 있다 |
| VIS-22 | Low | 채팅 본문 아래로 **약 600px가 빈 흰 공간**이다. 제안 칩 6개 아래가 통째로 비어 있어, 4K에서는 이 비율이 더 커진다 |
| VIS-23 | Low | 첨부(클립) 버튼이 무엇을 받는지 알 수 없다 — 실제로는 **PNG/JPEG/WebP 3종뿐**이고 PDF·CSV·문서는 안 된다(`AI-39`). 업무 도우미에서 이 제약이 아이콘만 보고는 드러나지 않는다 |

---

## CORE — `app/core/` 전수조사 (사이클 0)

인프라 계층. 14라운드 감사가 **한 번도 대상으로 삼지 않았다**(다른 모듈 수정의 부수효과로만 닿았다).

| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| CORE-01 | **High** | **워커 리스를 두 프로세스가 동시에 잡을 수 있다.** `worker_lock.py:117-131` — `O_CREAT\|O_EXCL`은 **0바이트 파일**을 만들고 페이로드는 `fdopen` 블록이 끝날 때 쓰인다. 그 틈에 P2가 `FileExistsError` → 빈 파일 파싱 실패 → `read()`가 `None` → `is_expired(None)`이 `True` → 자기 것을 쓰고 `verify_ownership()` 통과 → **True**. P1은 뒤늦게 덮어쓰고 **`verify_ownership` 없이** `_held=True`로 **True**. 인수 경로(118-126)는 검증하는데 **생성 경로(`else:`)만 검증이 없다**. 게다가 주석이 말하는 "마지막 쓰기가 이긴다 + verify가 진 쪽을 물러나게 한다"는 `write1,verify1,write2,verify2` 순서에선 **둘 다 통과한다** → 스케줄러가 두 프로세스에서 돌아 일정이 두 번 실행되고 Notion 동기화가 서로의 prune과 경합. 모듈 docstring이 막겠다고 선언한 바로 그 사고. `tests/unit/test_worker_lock.py`는 동시 생성 창을 검사하지 않는다 | 코드 직접 확인 | 발견 |
| CORE-02 | **Med** | **만료 세션의 `revoked_at`이 절대 저장되지 않는다.** `sessions.py:88-95`가 `record.revoked_at = now` 후 `None`을 반환 → `UnauthorizedError` → `deps.py:76-78 get_db`의 `except: db.rollback()`이 그 쓰기를 버린다(직접 확인). 결과: ① `profiles`의 "활성 세션" 목록·개수가 `revoked_at IS NULL`만 보고 `expires_at`을 안 봐서 **죽은 세션이 활성으로 보인다**(사용자가 어느 줄을 끊어야 할지 모른다 — 그 화면이 존재하는 이유가 무력화) ② `revoke_all_for_user`의 rowcount가 부풀어 "N개 종료했습니다"가 과장 ③ `retention.py`가 세션을 정리 대상에 넣지 않아 **행이 무한 증가** | 코드 직접 확인 | 발견 |
| CORE-03 | Med | **`worker_lock._write`가 비원자적**(`write_text`가 먼저 truncate). 다른 워커의 30초 `renew()` 도중 시작한 워커가 잘린 파일을 읽고 → `None` → "만료" 판정 → **살아 있는 워커에게서 리스를 뺏는다**. 같은 저장소의 `secret_refs.write()`는 정확히 같은 이유로 `mkstemp`+`os.replace`를 쓰고 그 이유를 주석에 적어 뒀는데 여기만 안 받았다 | | 발견 |
| CORE-04 | Med | **500 응답이 모든 보안 헤더와 접근 로그를 건너뛴다.** `@app.exception_handler(Exception)`이 Starlette `ServerErrorMiddleware`에 설치돼 `user_middleware` **바깥**에 놓이므로 `RequestContextMiddleware.dispatch`의 `await call_next` 뒤가 실행되지 않는다 → 500엔 CSP·`X-Content-Type-Options`·`X-Frame-Options`·`Referrer-Policy`·`Cache-Control: no-store`·`X-Request-ID`가 **전부 없고**, `logging_setup.py`가 "`request_id`를 담은 유일한 줄"이라 부른 접근 로그도 안 남는다 — 가장 상관관계가 필요한 요청에서. 본문에 내부 정보는 안 샌다(확인함) | 실제 미들웨어 스택으로 검증됨 | 발견 |
| CORE-05 | Med/Low | **잘못된 포트가 정책 판단을 500으로 만든다.** `allowlist.py:46` `parsed.port`가 `ValueError`를 던져 `URLNotAllowedError`(400) 계약을 빠져나간다. `base_url`/`health_url`/`webhook_url`은 저장 시 URL 검증이 없는 평범한 `str`이라, 관리자가 `http://runner.internal:99999/health`를 저장하면 헬스체크마다 "허용 목록에 없는 대상입니다" 대신 불투명한 500 | 재현 확인 | 발견 |
| CORE-06 | Med/Low | **allowlist 캐시 키가 `st_mtime` 하나뿐**이라 타임스탬프를 보존하는 복원(`cp -p`·`rsync -a`·tar·installer)이면 프로세스 수명 내내 **옛 허용목록을 계속 쓴다**(더 넓은 쪽으로). 나중에 같은 문제로 쓰인 `feature_flags._stat_key`는 `(경로, mtime_ns, size)`를 쓰고 그 이유를 docstring에 적어 뒀다. 웹·워커가 각자 캐시라 한쪽만 낡을 수 있다 | | 발견 |
| CORE-07 | Low | `Retry-After: nan`이 단일 아웃바운드 관문을 죽인다 — `nan<0`도 `nan>MAX`도 `False`라 `time.sleep(nan)` → `ValueError`. `inf`는 올바로 처리된다 | 재현 확인 | 발견 |
| CORE-08 | Low(잠복) | **`get_page_auth`가 임퍼소네이션 쓰기 차단과 `request.state.actor`를 빠뜨린다**. 현재 호출부 3곳이 전부 GET이라 악용 불가지만, `get_current_auth`의 docstring이 "라우터마다 걸면 새 라우터에서 빠뜨리고 그 라우터만 조용히 뚫린다"며 가드를 여기 둔 이유를 설명한다 — 이 함수만 그 가드 밖이다. 여기 붙는 첫 POST 페이지 라우트가 쓰기 우회가 되고, 감사도 **대상자**에게 귀속된다 | | 발견 |
| CORE-09 | Low | **임퍼소네이션 최대 시간(30분)을 건너뛸 수 있다.** `deps.py:133-151`이 `row is None`이면 만료 검사를 공허하게 통과시켜 8시간 절대 세션 TTL까지 유지된다. `imp_service.end()`엔 바로 그 경우를 위한 `active_for_session` 폴백이 있는데 `_impersonated_auth`엔 없다 | | 발견 |
| CORE-10 | Low | **기능 플래그에 타입 강제가 없다.** `_parse`가 JSON 값을 그대로 담아서 `"game_ai_enabled": "false"`(문자열)이면 truthy → 파일엔 `false`인데 **기능이 켜진다**. 이 모듈의 존재 이유가 "설정했는데 아무 일도 안 일어난다"를 없애는 것인데 그 역방향 실패가 남아 있다 | | 발견 |
| CORE-11 | Low | `safe_url.normalize_external_url`이 **호출부 0건**(죽은 코드). `announcements`가 `is_safe_external_url`로 검사만 하고 `link_url`을 **원문 그대로 저장**한다 → 검증 형태와 저장 형태가 갈라졌다(`"\x01https://ok.example"`가 통과·저장되어 전 사용자 배너로 나간다). 오늘은 무해하나 다음 `javascript:` 변종의 발판. `link_url=""`이 "링크 없음"이 아니라 422가 되는 것도 같은 가드 탓 | | 발견 |
| CORE-12 | Low | 자잘한 것들: `ratelimit._buckets`가 상한·청소 없이 무한 증가 · `_is_safe_request_id`가 유니코드 `isalnum()`이라 `µ²ª-ª` 같은 값을 헤더·로그에 반사(nginx가 덮어써 실제 도달은 어려움) · `audit._SENSITIVE_KEY`가 `secret_ref` **이름**까지 `***`로 가려 감사 기록이 어느 자격증명으로 바뀌었는지 못 말한다(같은 변경의 `config_versions`는 말한다 → 두 기록이 불일치) · `SecretMissingError`가 아무 데서도 안 잡혀 ref **이름**이 응답 본문에 노출(값은 아님) · `SettingsCache.current()`가 내부 dict를 **참조로** 반환(`feature_flags`는 같은 이유로 `dict()` 복사본을 준다 — 두 캐시가 관례가 다르다) · `main.py:119-123`의 `except: pass`가 DB 잠금·손상까지 삼켜 테넌트 오버라이드가 조용히 env 값으로 남는다 | | 발견 |

> **확인된 강점(회귀시키지 말 것)**: SSRF 관문은 견고하다 — 스킴 allowlist·userinfo 거부·호스트
> 소문자화·기본 포트 해석·정확한 `host:port` 일치·파일 없으면 전면 거부·**저장 시점이 아니라
> 호출 시점 검사**·`follow_redirects=False`·`trust_env=False`. urlsplit이 제어문자를 지우는
> split-parser 우회는 httpx 자체 URL 검증이 막는다(실제 시험함). `SecretValue`는 `%s`/`%r`/
> f-string/`json.dumps(default=str)` 전부에서 `***`로 가려진다. `scope.py`는 알 수 없는
> `admin_scope`에 대해 fail-closed이고 BFS는 순환 안전. `authz.MODERATOR_ROLES`는 `auditor`를
> 올바로 제외한다. `assets.py`는 요청마다 stat하고 traversal을 막는다.
> **§8의 `STRFTIME('%f')` 함정은 실제로 닫혀 있다** — `app/`·`alembic/` 전체에 해당 패턴이 없다.

---

## UB — 미감사 모듈 전수조사 (사이클 0, batch 1)

`announcements` · `impersonation` · `quotas` · `observability` · `templates` · `prompts` ·
`conversations` — 라운드 8~14가 한 번도 보지 않은 7개 모듈.

| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| UB-01 | **High** | **공지에 `admin_scope` 강제가 전혀 없다.** `announcements/router.py`에 `get_principal`이 **0회** 등장한다(직접 확인) → 부서 범위 `admin`이 `audience=all`·`level=critical`·`dismissible=false`·임의 `link_url`로 **전사 배너**를 띄우고 전역 admin의 공지를 지울 수도 있다. 바로 옆 `quotas/router.py:62-71`은 같은 위험을 두고 "부서 관리자가 전역 상한을 0으로 만들면 전 사용자의 AI가 멈춘다. 범위를 좁혀 놓고 이 문을 열어 두면 좁힌 의미가 없다"며 `_ensure_may_touch_global`을 두는데, 공지엔 대응물이 없다 | grep 0건 | 발견 |
| UB-02 | **High** | **전역 AI 상한을 '사용자별'로 강제하면서 화면엔 '전사 공용 풀'로 보여 준다.** 강제는 `service.py:216-220`이 항상 `used(db, user_id=user_id, …)`(사용자별)를 쓰는데(직접 확인), 목록은 `router.py:110-114`가 global 행에 `used_all`(전 사용자 합계)을 넣는다 → 상한 100에 50명이 3회씩 쓰면 콘솔이 **"150 / 100"**과 함께 "상한에 도달했습니다. 이 대상의 AI 요청이 지금 거절됩니다"를 단언한다. **아무도 안 막혀 있다.** 반대로 한 사용자가 99/100인 상황은 이 화면에 안 보인다 | 양쪽 직접 확인 | 발견 |
| UB-03 | **High** | **로그아웃이 임퍼소네이션 세션을 끝내지 않는다.** `END_LOGOUT` 상수가 `app/` 전체에서 **사용처 0건**(직접 확인). `/logout`은 임퍼소네이션 중 허용된 쓰기라 지원되는 종료 경로인데 `ended_at`·`ended_reason`이 영원히 NULL로 남는다 → `GET /sessions?active=true`가 그 세션을 **무기한 "진행 중"**으로 표시한다. 이 표가 `audit_logs`와 별도로 존재하는 이유가 "지금 누가 남의 화면을 보고 있는가"를 한 행으로 답하는 것인데 그 답이 영구히 틀린다. `impersonation.stop` 감사 줄도 안 남는다(모듈 docstring은 "시작과 종료 둘 다 남긴다"고 적음). 권한 상승은 아님 — 쿠키는 폐기된다 | grep 0건 | 발견 |
| UB-04 | Med/High | **"발행 버전 하나" 불변식이 경합에 깨지고, 깨지면 문서 생성이 500이 된다.** `prompts/service.py:83-91`이 잠금·제약 없는 read-then-write다(`UNIQUE(name, version)`만 있고 published 유일성 제약은 없음). 동시에 두 명이 발행하면 published 행이 둘 → 이후 그 이름의 모든 `transition`·`rollback`이 `scalar_one_or_none()`에서 `MultipleResultsFound` → **500**, 그리고 그 이름에 묶인 템플릿의 `POST /documents/generate`도 500 | | 발견 |
| UB-05 | Med | **PATCH가 저장된 `link_url`을 재검증해 옛 위험 배너를 끌 수 없다.** `router.py:184-190`이 `data.get("link_url", row.link_url)`을 검증에 넣는데, `core/safe_url.py:7-11`이 수정 이전 행에 안전하지 않은 값이 실제로 들어 있다고 적어 뒀다 → 화면의 원클릭 내리기(`{"active": false}`)가 **422**로 거부되고 배너는 그대로 떠 있다. `javascript:` 배너를 막으려고 만든 모듈이 그 배너를 못 내리게 하는 셈 | | 발견 |
| UB-06 | Med | 공지에 **`starts_at < ends_at` 검증이 없다.** 뒤집어 넣으면 201 + "활성" 행이 생기고 **아무에게도 안 보인다**. 화면엔 경고가 없다 | | 발견 |
| UB-07 | Med | 공지 `dismiss()`가 UNIQUE 제약을 상대로 **check-then-insert**(`service.py:104-118`) → 탭 두 개나 재시도에서 `IntegrityError` → **500**. docstring은 "이미 닫았으면 False(멱등)"라고 적었지만 원자적이지 않다 | | 발견 |
| UB-08 | Med | **`consume`이 커밋 전에 잠금을 놓는다**(`quotas/service.py:325-371`). `reserve`의 docstring이 "⚠️ 블록 안에서 커밋해야 한다. 잠금을 놓은 뒤에 커밋하면 그 사이 요청이 같은 한 칸을 또 가져간다"고 경고하는데 `consume`엔 그 경고도 커밋도 없다 → 9/10에서 두 요청이 통과해 11/10. 기존 TOCTOU 테스트는 Barrier가 **잠금 안**에 있어 이 창을 못 짚는다 | | 발견 |
| UB-09 | Med | `pending()`이 `chat_message` 잡만 센다(`service.py:116-129`). 오늘은 맞지만 `enforce` 계약은 일반적으로 쓰여 있어, 다른 AI 잡이 큐에 들어가는 순간 예약이 안 보여 큐 깊이만큼 상한이 샌다 — 증상이 "청구서가 예상보다 크다"라 몇 달 뒤에 드러난다(모듈이 스스로 적은 경고) | | 발견 |
| UB-10 | Med | `list_quotas`가 무제한 + N+1(행마다 COUNT 2회). 화면은 "받아 온 것이 곧 전부"라고 가정해 클라이언트 필터를 쓰는데 `capWarning`이 없어, 상한이 생기는 순간 필터가 조용히 결손된다 | | 발견 |
| UB-11 | Med | **`usage_stats`의 50개 상한이 프롬프트를 "쓰이지 않음"으로 오표기한다.** `sorted(ids)[:50]`은 UUID 사전순이라 임의 표본이다 → 버전 80개 중 63번이 실제 사용 중이어도 표본 밖이면 `document_runs: 0` → **"쓰이지 않음" 배지**. 그 배지가 이 화면의 존재 이유("정리 대상을 고를 때 씁니다")라 **운영 중인 프롬프트를 지우게 만든다** | | 발견 |
| UB-12 | Med | `usage_stats`가 무제한 + N+1 + `LIKE '%uuid%'`(인덱스 불가) 전체 스캔을 이름마다 수행. 페이지네이션도 페이저도 없다 | | 발견 |
| UB-13 | Med | **"이 프롬프트 버전 보기" 딥링크가 빈 목록을 연다.** `#/prompts?name=X`로 가는데 `DataScreen`이 필터를 키 단위로 병합해 화면 기본값 `status:"published"`가 살아남는다 → **발행 버전이 없는 프롬프트**(= 가장 유력한 정리 대상)를 클릭하면 0건이 떠서 관리자가 "없는 프롬프트"로 오해한다. `policy-usage`도 같다 | | 발견 |
| UB-14 | Med | **템플릿 `enable`이 참조를 재검증하지 않는다**(생성·수정은 한다). 참조하던 워크플로가 삭제된 뒤 활성화하면 200 OK에 초록 배지가 뜨고, 실패는 **관리자의 조작 시점이 아니라 사용자의 문서 생성 시점**에 터진다 | | 발견 |
| UB-15 | Med | **`read_count`가 브라우징이 아니라 폴링을 센다.** `Banners.jsx`가 60초마다 `GET /state`를 모든 화면에서 부르는데 증가가 거기 붙어 있다 → 모델이 적어 둔 목적("0인데 30분 열려 있었다 같은 이상을 보기 위한 값")이 **구조적으로 불가능**해졌다. 화면 라벨은 "조회 횟수"라 감사자가 페이지뷰로 읽는다 | | 발견 |
| UB-16 | Med | 그 증가가 **GET 안의 non-atomic read-modify-write**다: 탭 두 개면 증가가 유실되고, `require_csrf`가 안전 메서드를 통과시켜 `<img src>`로도 부풀릴 수 있으며(감사 필드에 공격자 잡음), 폴링마다 SQLite 쓰기 트랜잭션이 열린다 — `observability/service.py:11-14`가 금지한 바로 그 패턴 | SEC-03·UA-18과 같은 부류 | 발견 |
| UB-17 | Med | **자동 종료가 감사 줄을 안 남긴다**(수동 종료는 남긴다). 가장 보안상 중요한 두 종료(30분 상한, 대상 계정 잠김)가 `start`만 있고 `stop`이 없다. `"expired"`도 상수가 아닌 문자열 리터럴이라 프런트와 두 곳에 흩어져 있다 | | 발견 |
| UB-18 | Med | **`record_usage`가 `flush()` 실패를 삼켜 호출자의 세션을 오염시킨다**(`observability/service.py:67-84`). INSERT가 실패하면 세션이 rollback 필요 상태가 되고 **다음 문장**이 `PendingRollbackError`를 던진다 → "통계 한 줄 때문에 사용자의 로그인이나 티켓 생성이 실패하면 안 된다"는 계약이 정확히 반대로 작동한다. `quotas`에서 최악(그 직후 4개 질의를 더 던진다). `begin_nested()` SAVEPOINT가 필요 | | 발견 |
| UB-19 | Low/Med | 공지 삭제가 `AnnouncementDismissal`을 고아로 남긴다(FK·cascade 없음). 그 집합을 배너 폴링마다 전부 읽는다 | | 발견 |
| UB-20 | Low/Med | 삭제된 사용자의 쿼터 행이 **영구히 못 지운다**(DELETE가 404). 목록엔 raw UUID로 남는다 | | 발견 |
| UB-21 | Low/Med | 프롬프트/정책 생성·새버전이 경합 시 409가 아니라 **500**(`IntegrityError`). 순차 경로엔 이미 `ConflictError`가 있어 같은 상황이 상태 코드만 달라진다 | | 발견 |
| UB-22 | Low/Med | `_json_object_to_str`의 `None → "{}"` 분기가 타입 게이트 없이 공유돼, `PATCH prompts/{id} {"content": null}`이 422가 아니라 **프롬프트 본문에 문자열 `{}`를 저장**한다 | | 발견 |
| UB-23 | Low/Med | `Message.message_id`가 클라이언트 제공 키인데 **전역 UNIQUE**이고 조회에 소유자 필터가 없다 → 존재 여부 오라클(409 vs 201), 그리고 워커가 만드는 파생 id(`a-{id}-{n}`)와 네임스페이스가 겹쳐 사용자가 스스로 답장을 막을 수 있다. `UNIQUE(conversation_id, message_id)`면 둘 다 닫힌다 | | 발견 |
| UB-24 | Low | 공지 화면의 검색 상자가 **설정돼 있는데 안 그려진다** — `DataScreen.jsx:467 showSearch = config.searchable \|\| !config.paginated`이고 공지는 `paginated:true`에 `searchable` 미설정 → `searchFields`·`searchPlaceholder`가 죽은 설정. 제목으로 배너를 찾을 방법이 없다(백엔드에도 `q`가 없다) | | 발견 |
| UB-25 | Low | 죽은 것들: `observability`의 `body["components"]`(소비자 0, 관리자 폴링마다 생성) · `list_sync_status`(호출 0) · `SyncStatus.detail_json`(쓰기만 하고 읽지 않음) · `KNOWN_EVENTS`(검증에 안 쓰임 — 존재 이유가 오타 누적 방지인데 강제가 없음) · `ROLE_SYSTEM_MSG`(생산자·소비자 0) · `GET /ai-quotas/usage`(호출 0, FN-05과 동일) | | 발견 |
| UB-26 | Low | 한 번도 성공한 적 없고 `error`도 아닌 미러는 **아무 안내도 안 낸다**(`router.py:69-78`) — 사용자가 빈 티켓 목록을 이유 없이 본다. 모듈 docstring이 깨겠다고 한 바로 그 상태이고, 판단에 쓸 `last_run_at`은 이미 로드돼 있는데 안 쓴다 | | 발견 |
| UB-27 | Low | 임퍼소네이션 만료가 **다음 요청에서만** 평가된다(스윕 없음) → 브라우저를 닫으면 30분 상한을 넘겨도 "진행 중"으로 남는다. 온보딩 문구는 "최대 30분 뒤 자동 종료"라고 약속한다. UB-03과 겹쳐 "진행 중" 목록 전체를 신뢰할 수 없다 | | 발견 |
| UB-28 | Low | `visible_user_ids`를 `IN (…)`로 인라인(`impersonation/router.py:164-166`) → 문서화된 ~1000 사용자 규모에서 SQLite 변수 상한(999) 초과. UA-24와 같은 부류 | | 발견 |
| UB-29 | Low | 템플릿: 목록 무제한·파라미터 없음(정책 화면이 "이 정책을 쓰는 템플릿"을 위해 **전 테이블을 끌어와** JS로 거른다) · `created_by`가 raw UUID(프롬프트·정책은 이름을 해석한다) · `prompt_id`가 draft·archived를 가리켜도 통과 · 삭제 수명주기 없음 | | 발견 |
| UB-30 | Low | `PATCH {"max_calls": null}`이 조용히 no-op(200 + 변화 없는 감사 행). `RollbackRequest.name`만 `max_length` 없음 | | 발견 |

> **확인된 것(결함 아님)**: 쿼터의 KST 경계 계산은 **정확하다** — `period_start`/`period_end`의
> 월 롤오버(`replace(day=28)+7일→replace(day=1)`)가 2월 포함 모든 달 길이에서 맞고 KST는 DST가
> 없어 자정 산술이 정확하다. 임퍼소네이션의 **권한 상승 경로는 없다** — `require_roles`·
> `get_principal`이 대상 사용자를 보므로 대상의 권한을 넘을 수 없고, 자기 자신·비활성·동급 이상은
> 차단되며, 재진입은 이중으로 막히고, `blocked_write_count`는 롤백에 지워지지 않게 별도 세션을
> 쓴다. `/stop`에 역할 게이트가 없는 것도 올바른 판단이다.

---

## UA — 미감사 모듈 전수조사 (사이클 0, batch 2)

`home` · `assistant` · `reports` · `sprints` · `trash` · `documents` · `backups` · `org` ·
`offboarding` · `audit` · `llm_console` · `llm` — 라운드 8~14가 한 번도 보지 않은 12개 모듈.

| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| UA-01 | **High** | **`GET /api/assistant/weekly-digest`가 전사 데이터를 아무 인증 사용자에게나 준다.** 라우터가 `get_current_user`만 걸고 `require_roles`도 `principal`도 없는데, `facts.py:102-111`이 `build_period_report(...)`를 **`visible_user_ids` 없이** 부르고 `_top_contributors`로 **이름이 붙은 상위 기여자**까지 만든다. 같은 집계의 형제 경로 `reports/router.py:25,52`는 `SENSITIVE_READ_ROLES` + 스코프를 건다. `Home.jsx:417`이 이 패널을 임베드하므로 일반 사원이 홈에서 탭만 바꾸면 전사 티켓·WD·지연 합계와 상위 5인 명단을 받는다 | 라우터·facts 양쪽 직접 확인 | 발견 |
| UA-02 | **High** | **org 스코프 관리자가 스프린트 스코프를 통째로 우회한다.** `sprints/service.py:54-61` `_visible_ids`가 `scope.is_dept`일 때만 필터를 걸고 그 외에는 `None`(무제한)을 돌려준다. `tickets/service.py:156` `drop_out_of_scope_dtos`도 같다 → 멀티테넌트 설치에서 org B 관리자가 org A의 **직원 명단과 티켓 합계**를 본다. 코드 주석은 이 유출을 "고쳤다"고 적어 뒀는데 dept 스코프에만 적용됐다 | 직접 확인 | 발견 |
| UA-03 | **High** | **백업이 도는 동안 앱의 모든 쓰기가 막힌다.** `backups/service.py:87-109`가 `db.flush()`로 SQLite RESERVED 쓰기 잠금을 잡은 뒤 그 상태로 전체 DB 복사 + 임시 복원 + `integrity_check`(사본 2벌)를 수행하고, 커밋은 요청 끝(`get_db`)에 일어난다 → 그동안 다른 쓰기는 `busy_timeout` 후 `database is locked` 500. `trash/service.py:167-180`이 **똑같은 실패 양식**을 길게 문서화하고 구조를 바꿔 피했는데 백업 경로만 그대로다. 수동(`router.py:60`)·스케줄(`service.py:311`) 양쪽 해당 | 직접 확인 | 발견 |
| UA-04 | Med/High | **문서 "재시도"가 만들어 둔 수정 경로를 안 쓰고 옛 막다른 길을 그대로 쓴다.** `documents/router.py:148`의 `/{id}/retry`는 프런트 호출자가 **0건**이고, `registry/automation.js:283`은 여전히 `/documents/generate`를 부른다. 백엔드 docstring이 "생성 폼을 다시 여는 방식은 idempotency 중복으로 막다른 길이었다(round30 감사 E High)"라고 적어 둔 바로 그 방식이다. 운영자가 같은 기간을 다시 넣으면 409 "이미 생성된 문서입니다" | FN-07과 동일 뿌리, 근거 보강 | 발견 |
| UA-05 | Med | **`/weekly-digest`가 Notion 실패 시 502로 죽는다.** `facts.py:102`가 `configured`만 보고 `ok`를 안 봐서(형제 줄 96-98은 `ok and mapped`를 본다) 소스 장애 때 `NotionQueryError`가 그대로 올라간다 → Notion과 무관한 문서·게시판 집계까지 화면에서 사라진다. 모듈 docstring이 정반대를 약속한다 | 직접 확인 | 발견 |
| UA-06 | Med | **홈이 같은 집계를 한 번의 화면 진입에 두 번 돌린다.** `facts.py:47-49` `briefing_facts`가 `home_service.build_today(...)`를 다시 부르고, `Home.jsx:283`(`/api/home/today`)과 `Home.jsx:417`(`AssistantPanel` → `/assistant/briefing`)이 둘 다 마운트된다. `staleTime`도 30s/60s로 달라 값이 어긋난다 | | 발견 |
| UA-07 | Med | 스프린트 기본 창이 **UTC**로 계산된다(`sprints/router.py:36`). KST 월요일 00:00~09:00 사이엔 UTC가 아직 일요일이라 **지난주 창**이 잡힌다. 브라우저가 명시 날짜를 보내 가려져 있을 뿐 | 저장소가 네 번 문서화한 M4 함정 | 발견 |
| UA-08 | Med | 월간 리포트 기본 기간·`today`도 **UTC**(`reports/router.py:40-52`). 매월 1일 KST 00:00~09:00엔 **지난달** 리포트가 기본이 되고, 매일 9시간 동안 "어제 마감"이 `overdue`로 안 세어진다. `DevReport.jsx:23-26`은 브라우저 로컬로 계산해 **화면 기본값과 API 기본값이 어긋난다** | | 발견 |
| UA-09 | Med | **형제 지표가 휴지통 필터를 서로 다르게 건다.** `home/readers.py:78-91` `recent_documents`는 휴지통을 빼도록 고쳐졌는데(주석에 "지운 문서로 가는 살아있는 링크" 사고 기록), `readers.py:146-150` `documents_changed_between`은 `archived`만 본다 → 주간 다이제스트가 과다 집계하고 `AssistantPanel.jsx:157-160`이 404 링크를 그린다 | | 발견 |
| UA-10 | Med | **`GET /api/trash`가 무제한**이다. `list_items`가 전 행을 가져와 파이썬에서 거르고(사용자 전 행 스캔 추가), `Trash.jsx:41`이 **15초마다 폴링**한다. 양쪽 다 페이지네이션이 없다 | | 발견 |
| UA-11 | Med | **org 생성에 스코프 게이트가 없다**(`org/router.py:308-328`). 목록·단건은 `scope.org_id`로 좁히는데 생성만 무방비라 dept 범위 admin도 새 테넌트를 만들 수 있고, 만든 뒤엔 자기 스코프 밖이라 **자기 눈에 안 보이는 유령 행**이 된다(부서 쪽에서 바로 그 상태를 막으려고 쓴 주석이 있다) | | 발견 |
| UA-12 | Med | **`JobTitle` 중복 검사가 제약과 어긋나 500이 난다.** `org/service.py:227`은 org 범위로 중복을 보는데 `models.py:91`의 유니크는 **전역**이다 → 다른 org에 같은 이름이 있으면 사전검사를 통과하고 INSERT에서 `IntegrityError`가 잡히지 않은 채 500. 이름 변경(`service.py:281`)도 같다. 반대로 전역 admin이 부서를 만들 땐 검사가 **제약보다 엄격**해 잘못된 409가 난다 | | 발견 |
| UA-13 | Med | **부서 부모가 같은 조직인지 확인하지 않는다**(`org/service.py:241-248`, `tree.py:221-223`). 전역 admin이 org B 부서를 org A 부서의 부모로 지정할 수 있고, 그러면 조직도가 엉키고 `department_subtree_ids`가 **다른 테넌트 부서를 dept 스코프에 끌어들여 권한이 조용히 넓어진다** | | 발견 |
| UA-14 | Med | **부분 실패한 오프보딩 되돌리기를 영영 재시도할 수 없다.** `offboarding/service.py:428`이 `undone_at`을 실패 여부와 무관하게 찍는데 `:383` 가드가 `undone_at is not None`이면 거부한다. `REVERTIBLE_MOVES`에 `revert_failed`를 넣어 재시도를 의도한 설계와 모순. Notion이 불안정해 12건 중 3건이 실패하면 그 3건은 영구히 후임자에게 남는다 | | 발견 |
| UA-15 | Med | **오프보딩 중복 실행을 막는 것이 없다.** `_open_run_view`가 경고만 띄우고 `run_offboarding`은 확인하지 않는다. `service.py:227`이 느린 Notion 단계 **전에** 커밋하므로 더블클릭·새로고침으로 두 번 돌면 두 번째 run의 `before_user_ids`가 이미 후임자라 **되돌리기 계약이 깨진다** | | 발견 |
| UA-16 | Med | `org` 목록 3종이 N+1(부서·직책 각 행마다 `usage_count`, 조직은 행마다 COUNT 2번). 같은 파일의 `tree.py:38-42`·`_org_names`는 이미 그룹 질의로 고쳐져 있다 | | 발견 |
| UA-17 | Med | **감사 이상징후가 창 전체를 파이썬으로 끌어온다**(`audit/anomalies.py:127-135`, `limit` 없음). `MAX_WINDOW_HOURS=720`이고 화면에 "최근 30일" 선택지가 있어, 30일치 전 행을 `before_json`/`after_json` 포함 ORM 객체로 적재 + 기준선 질의로 30일 더 | | 발견 |
| UA-18 | Low | `GET /api/admin/backups`가 **GET 안에서 쓴다**(`reap_stuck_running`) → 읽기 경로가 쓰기 잠금을 잡고, CSRF는 안전 메서드라 통과. 게다가 **사람이 화면을 열 때만** 정리가 돈다(워커 틱 없음) | SEC-03과 같은 부류 | 발견 |
| UA-19 | Low | `POST /backups/{id}/verify`가 `running` 행을 막지 않는다(막는 것은 프런트 `when`뿐). 백업 도중 호출하면 `file_missing`으로 행이 잠깐 `failed`가 된다. `reap_stuck_running` docstring은 API가 막는다고 단언한다 | | 발견 |
| UA-20 | Low | 부모 부서를 지울 때 **하위 부서 경고가 없다**(사용자 수만 본다). FK가 `SET NULL`이라 자식이 루트로 올라온다 — 3단 트리가 클릭 한 번에 평탄해진다 | | 발견 |
| UA-21 | Low | 깊이 상한(32) 절단을 **순환으로 보고**한다(`org/tree.py:78,105-107`) → 순환이 없는 트리에 `상위 관계 오류` 빨간 배지가 뜨고 관리자에게 부모를 고치라고 안내한다 | | 발견 |
| UA-22 | Low | 죽은 값들: `home/aggregate.py:96 done_total`(소비자 0, 유일하게 창이 없음) · `blocked` 버킷(팀채팅이 켜져 있으면 도달 불가 UI인데 매 요청 계산) · `work.py`의 `in_scope`/`today`/실패 사유(화면이 일반 문구로 덮어써 "토큰 미설정"과 "조회 실패"가 구분 안 됨) · `llm_console/service.py:197 verified`(항상 False, 화면은 하드코딩 배지) · `documents/router.py:78-87`이 N+1 피하려 붙인 `requested_by_name`을 화면이 **안 쓰고 UUID를 그린다** | | 발견 |
| UA-23 | Low | `home/aggregate.py:126`이 `t not in cancelled`로 dict 값 비교를 O(n²) 수행(500티켓·50취소 = 2.5만 회 깊은 비교), `work.py`가 같은 리스트로 4회 더 호출 | | 발견 |
| UA-24 | Low | `readers.py:81` `trashed_page_ids`를 `notin_()`에 통째로 넣어 휴지통이 커지면 SQLite 변수 상한(999)으로 **홈 전체가 500** | | 발견 |
| UA-25 | Low | 휴지통 일괄 실패 토스트가 원인을 **전부 "권한이 없어"로 뭉갠다**(실제로는 이미 처리됨·권한·**Notion 보관 실패** 3종). Notion 장애 때 관리자가 다른 계정으로 재시도한다 | | 발견 |
| UA-26 | Low | 오프보딩 방 소유권 인계가 **비활성/보관 계정도 후보로 받는다**(`service.py:573-586`) → 이미 퇴사 처리된 계정이 방장이 되어 그 함수가 막으려던 상태가 된다 | | 발견 |
| UA-27 | Low | 이상징후 `new_actor_action`의 `count`가 **이벤트 수가 아니라 액션 종류 수**인데 화면은 한 "건수" 열로 그린다 | | 발견 |
| UA-28 | Low | `llm_console/service.py:143-151` `_source_of`가 `0`·bool 저장값을 `env`로 오분류. `provider.py:219-221`의 backend 오타는 화면에 "꺼짐"으로만 보여 "설정값이 잘못됨"과 구분 안 됨 | | 발견 |
| UA-29 | Low | `documents/service.py:258` `int(config.get("template_version", 1))`이 자유형 dict 값이라 `"v2"` 같은 입력에 422가 아니라 **500** | | 발견 |

> **확인된 것(결함 아님)**: `backups`의 보존 정책은 **정상**이다 — `apply_retention`은 실패 백업을
> keep 창에 넣지 않는다(`service.py:170-175`). 이전 기록의 의심은 근거가 없다.
> **`STRFTIME('%f')` 마이그레이션 함정도 없다** — 40여 리비전 전수 확인 결과 모든 타임스탬프가
> 파이썬에서 만들어져 바인딩된다. 감사 모듈의 KST 경계 계산(`_parse_boundary`·`_is_off_hours`·
> CSV 렌더·절단 센티널)도 전부 맞다.

---

## DOC — 문서 정합성

| ID | 심각 | 문제 | 근거 | 상태 |
|---|---|---|---|---|
| DOC-01 | Med | **`CLAUDE.md` §2-6이 CSP를 `script-src 'self'`라고 적고 있으나 실제는 2026-08-04 사용자 지시로 `'unsafe-inline' 'unsafe-eval' https:`까지 완화됐다.** 되돌리지 말고 **문서를 정정**해야 한다 | `app/core/middleware.py:20-55` vs `CLAUDE.md` §2-6 | 발견 |
| DOC-02 | Med | **`BUILD_LOG.md`에 라운드 8~14가 통째로 빠졌다**(최신 항목 2026-08-07). 가장 최근이자 가장 침습적인 작업의 인수인계가 커밋 본문에만 있다 | | 작업예정 |
| DOC-03 | Low | `OPERATIONS.md:36`이 "웹에는 서비스 재시작 API가 없다"고 하는데 `KNOWN_LIMITATIONS.md` §6은 `#/system`에서 privhelper로 5개 유닛을 재시작할 수 있다고 정정했다 | | 발견 |
| DOC-04 | Low | `NEXT_SESSION_PLAN.md`(2026-07-29)의 A·E 항목은 이미 배송됐다 | | 발견 |
| DOC-05 | Low | `WORK_PLAN_INDEX.md`(2026-08-03)가 5일치 작업만큼 낡았다 | | 작업예정 |
| DOC-06 | Low | `~/.claude/plans/flickering-percolating-clover.md` §E(~90항목)가 **부분적으로 이미 해소됐다** — 예: `PF11 nginx gzip 없음`은 서버에 gzip이 이미 켜져 있고(`Content-Encoding: gzip` 확인), `Z5 MIN_FTS_CHARS`는 LIKE 폴백이 있다. **항목별 실측 없이 신뢰하면 안 된다** | 직접 확인 | 발견 |
