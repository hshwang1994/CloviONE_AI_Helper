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

**마지막 갱신**: 2026-08-08 (사이클 0) · **총 항목**: 96

---

## 요약

| 영역 | High | Med | Low | 계 |
|---|---|---|---|---|
| [DS 디자인 시스템](#ds--디자인-시스템) | 6 | 12 | 5 | 23 |
| [AI AI 도우미·채팅](#ai--ai-도우미채팅) | 9 | 16 | 8 | 33 |
| [FN 기능·API·DB](#fn--기능apidb) | 3 | 9 | 6 | 18 |
| [SEC 권한·보안](#sec--권한보안) | 1 | 2 | 2 | 5 |
| [IA 정보구조](#ia--정보구조검색) | 0 | 4 | 1 | 5 |
| [QA 검증 인프라](#qa--검증-인프라) | 3 | 5 | 0 | 8 |
| [DOC 문서 정합성](#doc--문서-정합성) | 0 | 2 | 4 | 6 |

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
| DS-21 | Low | **`.c-screen`이 유령 클래스** — 39곳에 붙어 있는데 기본 규칙이 없고 자식 margin 2줄뿐. 9개 화면은 아예 안 붙어 있어 페이지 리듬이 다르다 | `styles/screens.css:307-308` | 발견 |
| DS-22 | Low | **`ui/Pager.jsx`가 `Activity.jsx`에 복붙**됐고 동작이 갈라졌다(원본은 1페이지에서 `null`, 복사본은 항상 렌더) | `Activity.jsx:175-189` vs `ui/Pager.jsx:18-24` | 발견 |
| DS-23 | Low | **관리자 표 안 링크가 브라우저 기본 파란/보라 밑줄** — `columnHelpers`가 맨 `<a>`/`<ul>`/`<div>`를 뱉고 `a{}` 규칙이 없다. `registry/shared.js:74-75`는 raw `style` 객체 | `data-screen/columnHelpers.jsx:17-23,66,75-86` | 발견 |

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
| DS-28 | Med | **사이드바 배경이 3출처** — `theme.palette.sidebar.bg`는 정의만 되고 **한 번도 안 읽힌다**, `--sidebar-bg`(CSS), `AppShell.jsx:584 #1B2447` 리터럴(어느 팔레트에도 없는 값) | `theme.js:206`, `tokens.css:144,327`, `AppShell.jsx:412,584` | 발견 |
| DS-29 | Med | **상단바 그라데이션이 사용자 accent를 무시** — 청록을 골라도 상단바·사이드바는 남색 고정 | `AppShell.jsx:496-498` | 발견 |
| DS-30 | Med | **`PROJECT_TONE_COLORS` 8색이 다크에서 대비 2.4:1** (비텍스트 기준 3:1 미달). 예: `#1971C2` on `#11182D` | `chat-helpers.js:275-276`, 사용처 `chat/TicketCard.jsx:90` | 발견 |
| DS-31 | Low | 다크에서 안 바뀌는 고정색: `Mascot` FAB `rgba(255,255,255,.96)` · `ImageLightbox` 배경 `rgba(10,16,38,.92)` · `TopSearch` `#fff` | `Mascot.jsx:254,264`, `ImageLightbox.jsx:49`, `TopSearch.jsx:35,38` | 발견 |

> **보존할 올바른 패턴**: `ui/charts/base.jsx:47-63` `resolveChartColor`가 다크에서 묻히는 고정
> 회색을 `text.disabled`로 라우팅한다. 이것을 시스템 전체 규칙으로 승격한다(DECISIONS D-03).

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
| QA-08 | Med | QA-07의 **구조적 원인**: 프런트에 시계 주입 관례가 없다. 백엔드는 `tests/fakes/clock.py`를 두고 결정론을 강제하는데 프런트는 `vi.setSystemTime`을 **172파일 중 5개**만 쓴다. 절대 날짜 픽스처는 **55개 파일**에 있다. 상대 시각 헬퍼(`Dashboard.daysSince`, `lib/format.js:79`, `registry/automation.js:112,336,358`, `registry/integrations.js:144`, `chat-helpers.js:38,94`, `LoginHandoff.jsx:58`)와 만나는 조합만 위험하다 — 이번에 전수 대조해 **활성 rot는 1건뿐**임을 확인했고(`scheduler-calendar`의 "예정"은 서버 `kind` 파생이라 안전) 나머지는 잠복이다. **잠복을 잡을 가드가 없다** | 전수 대조 | 발견 |

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
