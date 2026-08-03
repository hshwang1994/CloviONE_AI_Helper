# 다음 세션 작업 계획 (2026-07-29 확정)

> 토큰 충전 후(다음 주) 착수. 사용자와 합의된 계획이다. 최우선 기준은 늘 같다: **기존 정상 동작
> 무손상**(티켓/인증/탭/AI도우미/기존 API/자동화), 각 단계 회귀 테스트로 증명, "확인했고 됐다"만 완료.
> 관련 메모리: [[clovirone-team-space]] [[clovirone-web-assistant]] [[layout-spacing-gap]] [[static-asset-cache-busting]].

이미 배포 완료된 것(이번 세션): 팀 채팅 서브시스템(마이그레이션 0021, 전체/그룹/1:1, 홈 위젯),
팀 티켓 담당자별 그룹핑, 스프린트/홈 간격 수정. 아래는 그 다음 할 일이다.

---

## A. 티켓 성능 근본 개선 (최우선) — 문서(team_docs)와 동형 로컬 미러

### 문제
내 티켓/미할당/팀/스프린트가 **매 요청마다 Notion을 실시간 조회**한다.
- `list_my_tickets` → `notion_source.query_tasks_by_assignee` (1회)
- `list_unassigned_tickets` → `query_unassigned_tasks` (1회)
- `list_team_tickets` → `query_all_tasks` (전체 스캔 1회)
- `build_sprint_summary` → 위 3개를 **조합(3회 스캔)** → 제일 느림

문서 탭은 안 느리다. 이유: 워커가 시작 즉시 + 10분마다 백그라운드로 Notion을 로컬 캐시에 미러링하고
(`app/team_docs/sync.py` `sync_documents`, `worker_main.py` `docs_sync_tick`,
`notion_docs_sync_interval_seconds` 기본 600s), 페이지는 **로컬 캐시만 즉시** 읽는다. 수동 동기화 버튼은
"지금 새로고침"용일 뿐. 티켓도 이 패턴을 그대로 도입한다.

### 설계 (team_docs 패턴 이식)
- **신규 테이블** `ticket_cache`(+ 마이그레이션): page_id(PK), title, status, assignee_user_ids(해석된 앱
  user_id 리스트, 구분자 저장), difficulty, priority, est_wd, due_date, project, raw_json, synced_at.
  + 동기화 상태 싱글턴(`NotionSyncState` 동형: last_synced_at, last_error, truncated). 마이그레이션에서 시드.
- **워커 틱** `tickets_sync_tick`: 시작 즉시 + N초 주기(티켓은 문서보다 자주 바뀌니 120~300s 검토,
  설정값 `notion_tickets_sync_interval_seconds` 신규). `query_all_tasks` 한 번으로 전량 미러.
- **읽기 경로 교체**: list_my/unassigned/team/sprint 가 Notion 대신 `ticket_cache`를 읽어 SQL/파이썬으로
  필터(내=assignee 포함, 미할당=assignee 없음, 팀=전체, 계획=status). 스프린트 3회 스캔 → 0회(캐시).
- **쓰기 일관성**: 생성/편집/claim/휴지통 이동은 계속 Notion 실시간 반영 + **캐시 즉시 패치 또는 즉시 재동기화
  트리거**(오래된 캐시로 방금 만든 티켓이 안 보이는 일 방지). 낙관적 업데이트 고려.
- **장애 격리(§17.4 동형)**: Notion 동기화 실패 시 마지막 성공 캐시 + staleness 배지, 500 금지.
- **상세(블록)**: 단건 상세는 계속 Notion 실시간(`ticket_detail`) 유지(온디맨드 1페이지라 캐시 불필요). 필요 시 후속.

### 향후 자체 DB(제품화) 대비 — A 하면서 저비용으로 미리 심을 것 (상세: PRODUCTIZATION_ARCHITECTURE §4)
제품화 시 Notion을 티켓/문서 소스에서 떼고 자체 DB로 갈 수 있다. A에서 어차피 읽기 경로/캐시를 손대니
이때 아래를 함께 심어두면 나중 전환이 마이그레이션이 아니라 설정 스위치가 된다(네이티브 구현은 지금 안 함, 문만 연다):
- ticket_cache에 **자체 UUID `id`(PK) + `notion_page_id`(널 허용)**. 내부 참조(댓글, 휴지통, 링크, 알림)는
  전부 자체 id 사용, notion_page_id 직접 참조 금지.
- `notion_source.*` 직접 호출을 **`TicketRepository` 인터페이스** 뒤로. 지금은 Notion 구현 하나, 설정
  `ticket_source`(notion|native)로 교체 가능하게. 문서도 동형.
- 본문(E)은 **마크다운 정본**으로 자체 저장 + Notion 블록 어댑터.
- sync 방향 교체 가능하게(pull → 나중에 push/제거).
- 프런트는 이미 우리 API만 호출하므로 무변경(백엔드 추상화만).

### 파일
`app/tickets/models.py`(신규 테이블 or 신규 모듈 `app/ticket_cache/`), 마이그레이션, `app/tickets/service.py`
(읽기 경로 캐시 전환 + 쓰기 후 캐시 갱신), `app/tickets/sync.py`(신규, docs sync 미러), `app/worker_main.py`
(tick 등록), `app/settings/registry.py`(interval 설정), `app/sprints/service.py`(캐시 기반으로).

### 리스크/검증
중간 규모. 회귀: 기존 티켓 API 응답 형태 동일 유지(프런트 무변경 목표). "방금 만든 티켓 즉시 보임" 확인.
동기화 실패 시 stale 표시 확인. 워커 결정론 테스트(FakeClock) 유지.

---

## B. 스프린트 회의 재설계 (A와 한 묶음: 같은 데이터)

### 변경
- **`티켓 배분` 섹션 제거** — 미할당 티켓 페이지와 중복(사용자 지적).
- **`완료 현황` 카운트 표 → 담당자별 티켓 리스트**로 교체: 담당자마다 자기 티켓을 상태 배지(완료/진행/검증/계획)와
  함께 펼쳐 보여주고, **제목 클릭 시 `/tickets/:id` 상세**. "각자 뭘 끝냈고 뭐 하는지" 한눈에.
- `계획 논의` 섹션은 유지(또는 담당자별에 통합 검토).
- 재사용: 팀 티켓의 `groupByAssignee` + `GroupedTickets`(이미 있음). 주(week) 범위 완료분 반영은 백엔드에서
  담당자별 rows를 주 범위로 필터해 반환.

### 파일
`frontend/src/screens/Sprint.jsx`, `app/sprints/service.py`(담당자별 티켓 rows 반환하도록).

### 리스크
낮음(조회 전용, 기존 컴포넌트 재사용). A의 캐시 위에서 하면 즉시 빠름.

---

## C. 홈 레이아웃 2단 재배치 (사용자 아이디어 채택)

### 변경
- **2단**: 오른쪽 1/3 = 팀 채팅, 왼쪽 2/3 = 요약 카드 + 티켓 리스트 + 내 게시판 활동.
- `내 게시판 활동`이 내용 대비 가로로 늘어져 허전한 문제 → 폭이 좁아지며 해결.
  (대안: 게시판 활동을 오른쪽 채팅 아래로 내리면 작은 콘텐츠에 더 맞음. 착수 때 눈으로 보고 결정.)
- **간격 필수**: [[layout-spacing-gap]] — 새 2단 컨테이너는 `display:grid; gap`으로 짜서 붙음 방지.
- **모바일**: 좁은 화면(<=860px)에서 1단으로 세로 스택.
- **명칭 변경 없음**: 홈은 `홈` 그대로 유지(대시보드로 안 바꿈 — 사용자 결정).

### 파일
`frontend/src/screens/MyTickets.jsx`(MyWork), `frontend/src/styles/screens.css`.

### 리스크
낮음(레이아웃). 반응형 확인 필수.

---

## D. 채팅방 완성도 (팀 채팅방 전용, 놀이 채팅 아님)

1. **안 읽은 메시지 표시 강화**: 그룹/1:1은 이미 안읽음 배지 구현·배포됨. 추가로 **전체 채팅 방도 안읽음
   카운트**가 뜨게 개인별 읽음 커서를 가볍게 추가(폴링마다 쓰지 않고 읽을 때만 기록). 사이드바 `채팅방`
   항목에 총 안읽음 배지도 검토.
2. **이모티콘(버튼식)**: 입력창에 이모지 피커 버튼 → 클릭 삽입(CSP 안전, 유니코드 이모지).
3. **사진 붙여넣기(Ctrl+V)**: 첨부가 아니라 **클립보드 붙여넣기**로 이미지 → 업로드 → 말풍선 인라인.
   게시판의 `app/core/uploads.py`(매직바이트 검증) 재사용. 신규: 메시지-이미지 저장/서빙 경로 + 인증 서빙.
   놀이 채팅은 텍스트 전용 유지.
4. **방 삭제/파하기(disband)**: `POST /rooms/{id}/disband`(방장=owner만, 전체 채팅은 409 보호) → 방
   soft-delete(ChatRoom.deleted_at 이미 있음) + 시스템 메시지 + 목록에서 제거. 방 페이지에 방장 전용 버튼.
   (나가기는 이미 "○○님이 나갔습니다" 시스템 메시지 남김 — leave_room 확인됨.)
5. **채팅 초대 알림**: 그룹 생성/1:1 시작 시 초대된 본인에게 `notify_user(type_="chat_invited",
   title="○○님이 대화에 초대했습니다", related=("chat_room", room_id))`. 알림벨 클릭 시 `/chat-rooms/:id`
   딥링크. 프런트 `TYPE_KO`에 `chat_invited` 한국어 라벨 + NotificationBell 링크 처리.

### 파일
`app/team_chat/{models,service,router}.py`, 마이그레이션(이미지 메시지/전체채팅 읽음 커서 필요 시),
`app/core/uploads.py`(재사용), `frontend/src/screens/{ChatPane,ChatRoom,ChatRooms}.jsx`,
`frontend/src/lib/format.js`(TYPE_KO), `frontend/src/app/NotificationBell.jsx`.

### 리스크
낮음~중(이미지 업로드/서빙, 전체채팅 보호 가드 필수).

---

## E. 티켓 본문 수정 + 댓글 (이전부터 남은 것)

- **본문 수정**: 티켓 상세에 본문 에디터(기존 `frontend/src/ui/BodyEditor.jsx` + `app/core/notion_blocks.py`
  재사용) → Notion 페이지 블록 업데이트(`notion_write`). 리스크 중(Notion 쓰기, A 캐시 갱신도 연동).
- **댓글**: Notion comments API 권한 불확실 → **자체 DB 댓글**(신규 `ticket_comments` 테이블 + 마이그레이션),
  티켓과 느슨 결합. 작성/수정/삭제 소유권, 알림 연동 검토.

### 파일
`app/tickets/*`, 신규 마이그레이션(댓글), `frontend/src/screens/Ticket.jsx`.

---

## F. 추가 아이디어 (여유 있으면, 우선순위 낮음)

- **메시지 삭제**: 본인 메시지 soft-delete(ChatMessage.deleted_at 이미 있음) → "삭제된 메시지" 표시.
- **1:1 읽음 표시**: 상대 last_read_seq >= 내 마지막 메시지 seq면 "읽음" 표기(데이터 이미 있음).
- **온라인 표시**: member.last_seen 활용(그룹 멤버 목록에 접속 점).
- **그룹 관리**: 방장이 방 이름 변경 + 멤버 추가/제외(생성 후).
- **@멘션 + 멘션 알림**: 그룹에서 특정인 지목 시 알림.
- **링크 자동 인식**: 메시지 URL을 안전하게 클릭 가능한 앵커로(textContent/CSP 준수).
- **알림 딥링크 일반화**: NotificationBell이 related_object_type별 목적지 매핑(chat_room, ticket, document…).
- **스프린트 진척 시각화**: 주간 완료 추세/담당자별 WD 밸런스 막대(기존 dev-report 데이터 재사용).
- **모바일 반응형/접근성 점검**: 신규 컴포넌트(채팅 2단, 홈 2단) 좁은 화면·포커스·aria.

---

## 권장 순서
1. **A + B** (성능 근본 개선 + 스프린트 재설계, 같은 캐시 데이터라 함께)
2. **C** (홈 2단 레이아웃)
3. **D** (채팅방 완성: 이미지/이모지/삭제/알림/전체채팅 안읽음)
4. **E** (티켓 본문 수정 + 댓글)
5. **F** (여유분)

## 배포 참고 (이번 세션에서 검증된 절차)
- 마이그레이션 있는 배포: `~/deploy-teamchat/do.sh`(deploy-trash 템플릿) 방식 —
  py_compile 게이트 → 서비스 정지 → DB 백업 → `install -D` → `sudo -u clovirone-web ... alembic upgrade head`
  → static 전체 스왑(react.old-* 롤백본) → 기동 → healthz 200 + 신규 라우트 401 확인.
- 정적만 바뀌면 무중단 스왑(재시작 불필요), `assets.py`가 mtime/크기로 캐시버스팅.
- 함정: py_compile 게이트가 SRC에 __pycache__ 생성 → install 루프가 /opt로 복사 → 배포 후 stray pyc 삭제.
- 서버 nginx는 `127.0.0.1` 아니라 실제 IP `10.100.64.71:443`에서 listen(healthz 확인은 실제 IP로).
- sudo 비번은 stdin으로만(`printf '%s\n' '...' | sudo -S -p ''`). git/러너토큰 복사는 분류기 차단 → 사용자 몫.
- 육안(브라우저) 검증은 로그인 필요 → 나는 비번 입력 불가 → 사용자가 확인.
