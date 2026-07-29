# 결함 및 개선 기록 (DEFECT_AND_IMPROVEMENT_LOG)

전면 제품 검수에서 발굴한 결함이다. 8개 도메인에 병렬 검수자를 붙여 찾은 뒤,
각 주장마다 별도의 검증자가 반증을 시도했다. 반증에 실패한 것, 즉 실제로 성립하는 것만 남겼다.

- 발굴 후 검증 통과: **48건**
- 검증에서 기각(반증 성공): 6건

| 심각도 | 건수 |
|---|---|
| High | 25 |
| Medium | 17 |
| Low | 6 |

## 1. [High] 작업 큐(Job Queue) 섹션이 타인의 채팅 원문을 operator에게 그대로 노출 — 채팅 API의 소유자 검사 우회

- 영역: 관리자 운영
- 위치: `app/jobs/router.py:36`
- 재현: tests/integration/에 아래 테스트를 넣고 .venv/Scripts/python -m pytest <file> -s 실행:
1) login_as("user", email="alice@goodmit.co.kr") → POST /api/conversations → POST /api/conversations/{id}/messages {"content":"비공개 메모 SECRET-XYZ","client_message_id":"probe-1"} (202)
2) client.cookies.clear(); login_as("operator")
3) GET /api/conversations/{id}/messages → 403 (정상 차단)
4) GET /api/admin/jobs → 200, items[].payload.content 에 'SECRET-XYZ' 그대로 포함
관리자 콘솔 UI 경로: operator 로그인 → /admin#jobs (nav에 '작업 큐' 노출됨) → 목록 응답 자체에 payload 포함, '상세' 버튼(sections.js:480)이 payload 전체를 모달로 표시.
- 기대: 채팅 API가 본인 대화만 읽히도록 막는 것과 동일한 경계가 Job 큐에도 적용되어야 한다. operator에게는 큐 운영에 필요한 메타데이터(job_type/status/attempt_count/last_error)만 보이고, chat_message payload의 content·requester·attachments는 마스킹되거나 제외되어야 한다.
- 실제: operator가 /api/conversations/{id}/messages 로는 403을 받지만, 같은 내용을 /api/admin/jobs 목록 응답(및 '상세' 모달)에서 원문 그대로 읽는다. requester.email/name까지 함께 노출되어 누가 무슨 말을 했는지 완전히 식별된다. attachments(base64 이미지)는 terminal-success payload에서만 제거되므로(app/chat/service.py:213-260) 처리 중/실패 job의 첨부 이미지 바이트도 함께 노출된다.
- 원인 근거:
```
app/jobs/router.py:18-25 router = APIRouter(prefix="/api/admin/jobs", dependencies=[Depends(require_roles("operator","admin","system_admin")), ...])
app/jobs/router.py:36  "payload": json.loads(job.payload_json),   ← 마스킹/필터 없음
app/chat/service.py:182-192 _build_job_payload() → {"content": message.content, "requester": {"email": ..., "name": ...}}
app/chat/router.py:125 get_messages() → get_owned_conversation(db, user, conversation_id)  ← 채팅은 본인 것만 읽힘

실제 관측 출력(로컬 pytest, 배포본과 md5 동일 확인):
  operator direct conversation read -> 403
  LEAKED ROWS: [{'job_type': 'chat_message', 'payload': {'conten
```
- 수정 방향: app/jobs/router.py의 _job_view()에서 payload를 그대로 내보내지 말 것. (1) 기본 응답에서 payload 제거 또는 app/core/audit.py의 mask_sensitive 계열 필터를 태워 chat_message의 content/attachments/requester를 마스킹, (2) 원문 payload가 실제로 필요한 디버깅 용도는 admin+ 전용 별도 엔드포인트로 분리하고 감사 기록 남기기, (3) sections.js jobs 섹션의 '상세' 액션도 마스킹된 뷰만 쓰도록 정렬, (4) tests/security/에 'operator는 chat_message payload의 content를 볼 수 없다' 회귀 테스트 핀.
- 검증자 판정: 반증 실패 — 주장이 성립한다. 시도한 반증 경로와 결과:

1) 응답 마스킹 존재 여부 → 없음. app/core/audit.py:22 mask_sensitive는 record_audit(:52,:57)에서만 호출되며 job view에 적용되지 않음. RequestContextMiddleware는 헤더만 조작, 본문 미변경.

2) operator에게 설계상 허용된 권한인가 → 아님. app/users/models.py:24 _ROLE_LEVELS에서 operator는 레벨 2(user 바로 위 최하위). docs/SECURITY

## 2. [High] 후속 질문의 지시대명사 '그 프로젝트'가 무시되고 전사 214건 티켓이 반환됨 (컨텍스트 기억 실패)

- 영역: 라이브 사용자 여정
- 위치: `/opt/claude-work-assistant/assistant.py:3329`
- 재현: ssh -o BatchMode=yes cloviradmin@10.100.64.71 'curl -s -X POST http://127.0.0.1:5678/webhook/clovirone-work-assistant -H "Content-Type: application/json" --data @-' <<< '{"requester":{"email":"hshwang@goodmit.co.kr","name":"황형섭"},"message":"스마일게이트 포털 구축 프로젝트 진행 상황 어때?","conversation_id":"audit-lj-003","message_id":"m1"}'
이어서 동일 conversation_id로:
... --data '{"requester":{...},"message":"그 프로젝트 티켓 전부 보여줘","conversation_id":"audit-lj-003","message_id":"m2"}'
- 기대: "그/해당/이" + 프로젝트 형태의 조응 표현은 context.selected_project를 상속해 scope=PROJECT_TICKETS, project_id=262c5c5a-5684-80f5-9e24-fbe0a8c209c4 로 조회되어야 한다. 앞 턴에서 선택된 프로젝트의 티켓만 반환.
- 실제: scope=ALL_TICKETS, project_id="" 로 초기화되어 전사 모든 프로젝트의 티켓 214건을 반환. 사용자가 지목한 프로젝트와 전혀 무관한 결과이며, 사용자가 담당하지 않는 프로젝트 티켓까지 대량 노출된다.
- 원인 근거:
```
is_followup_query()의 has_subject 판정이 리터럴 토큰 "프로젝트"를 '스스로 주어를 명시한 새 질문'의 근거로 취급한다:

    has_subject = any(token in n for token in [
        "프로젝트", "내티켓", "나한테할당", "나에게할당", "전체티켓", "모든티켓",
        ...
    ]) or bool(extract_keyword(message))
    ...
    return not has_subject and condition_only and len(n) <= 40

"그 프로젝트"는 앞 결과를 가리키는 조응(anaphora) 표현인데 "프로젝트"를 포함하므로 has_subject=True → 상속 거부.

[라이브 프로브 — conversation_id=audit-lj-003]
1턴 "스마일게이트 포털 구축 프로젝트 진행 상황 어때?"
 → context.selected_project = {"id":"262c5c5a-5684-80f5-9e24-fbe0a8c209c4","name":"M. 스마일게이트홀딩스 [ClovirONE 2.0 포털 구축]"} (컨텍스트에 정상 저장됨
```
- 수정 방향: has_subject 판정 전에 조응 표현을 먼저 분리한다. norm(message)가 (그|해당|이|저|방금|위|앞)\s*프로젝트 패턴에 매칭되면 '새 주어 명시'가 아니라 '이전 주어 참조'로 보고 explicit_followups와 동일하게 상속 경로(return True)를 태운다. 구체적으로 has_subject 계산 시 사용하는 문자열에서 해당 조응 패턴을 re.sub로 제거한 뒤 "프로젝트" 토큰을 검사하거나, explicit_followups 리스트에 "그프로젝트","해당프로젝트","이프로젝트" 를 추가해 3321행의 조기 return True로 처리한다. 또한 상속이 불가능해 ALL_TICKETS로 폴백할 때는 조용히 전사 목록을 뿌리지 말고 어떤 프로젝트를 말하는지 되묻는(questions) 응답을 반환해야 한다.
- 검증자 판정: 반증 실패 — 결함은 실제로 성립한다. 독립 재현 및 코드 추적 결과:

[라이브 프로브 재현 — conversation_id=disproof-anaphora-91, 신규 대화]
1턴 "스마일게이트 포털 구축 프로젝트 진행 상황 어때?" → context.selected_project = {"id":"262c5c5a-5684-80f5-9e24-fbe0a8c209c4","name":"M. 스마일게이트홀딩스 [ClovirONE 2.0 포털 구축]"} 정상 저장, last_query.scope=PROJECT_TICKETS.
2턴 "그 프

## 3. [High] '진행 상황' 문구의 '진행'이 상태 필터로 강탈되어 상태 조건이 무단 주입됨

- 영역: 라이브 사용자 여정
- 위치: `/opt/claude-work-assistant/assistant.py:765`
- 재현: ssh -o BatchMode=yes cloviradmin@10.100.64.71 'curl -s -X POST http://127.0.0.1:5678/webhook/clovirone-work-assistant -H "Content-Type: application/json" --data @-' <<< '{"requester":{"email":"hshwang@goodmit.co.kr","name":"황형섭"},"message":"스마일게이트 포털 구축 프로젝트 진행 상황 어때?","conversation_id":"audit-x1","message_id":"m1"}'
→ context.last_query.statuses 확인. 영향이 큰 재현은 티켓이 실재하는 프로젝트로: message="SK하이닉스 용인 클러스터 프로젝트 진행 상황 어때?" (해당 프로젝트엔 계획/검증 상태 티켓이 다수 존재 — audit-lj-001 프로브에서 확인됨)
- 기대: '진행 상황', '상황', '진척'은 상태 필터가 아니라 '요약/현황' 요청으로 해석되어야 한다. statuses=[] 로 두고 프로젝트 전체 티켓을 상태별로 집계한 요약(계획 n건 / 진행 n건 / 검증 n건 …)을 반환해야 한다.
- 실제: statuses=["진행"] 이 주입되어 '진행' 상태 티켓만 조회. 스마일게이트 프로젝트는 활성 티켓이 0건이라 결과는 우연히 일치했으나(별도 프로브 audit-lj-005: statuses=[] 로 조회해도 총 0건 확인), 계획/검증 티켓을 보유한 프로젝트에서는 그 티켓들이 통째로 누락된 채 '조건에 맞는 티켓이 없습니다'로 답하게 된다. '검토 상황'의 '검토'(→검증), '작업중인가'의 '작업중'(→진행)도 동일하게 강탈된다.
- 원인 근거:
```
resolve_status_intent()의 긍정 상태 스캔이 아무런 경계 검사 없는 단순 부분문자열 포함으로 판정한다:

    for alias, actual in sorted(status_map.items(), key=lambda item: len(item[0]), reverse=True):
        if alias and alias in scan:
            selected.append(actual)
            scan = scan.replace(alias, "")

STATUS_ALIASES = {..., "진행": ["진행", "진행중", "작업중"], "검증": ["검증", "검토", "테스트중"], ...}
따라서 norm("진행 상황 어때") = "진행상황어때" 안의 "진행"이 상태값으로 매칭된다.

[라이브 프로브 — conversation_id=audit-lj-003, message_id=m-lj-003-1]
프로브: "스마일게이트 포털 구축 프로젝트 진행 상황 어때?"
응답 last_query: {"scope":"PROJECT_TICKETS","operation":"LIST","project_name":"M. 
```
- 수정 방향: 765행의 무경계 부분문자열 매칭을 경계 인식 매칭으로 교체한다. (1) 스캔 전에 상태어를 삼키는 명사구를 directive_patterns와 같은 방식으로 선제거한다: scan = re.sub(r"(진행|검증|계획|완료)\s*(상황|상태|현황|정도|률|율|사항)", "", scan). (2) 상태 별칭 뒤에 조사/한정 어미(중인|인|만|상태|티켓|건)가 오거나 문장이 끝나는 경우에만 상태로 인정하도록 정규식 경계를 건다. (3) 회귀 테스트 추가: "~프로젝트 진행 상황 어때?" → statuses == [] 임을 핀으로 고정(tests/regression).
- 검증자 판정: 반증 실패 — 결함은 실재하며 라이브 운영 환경에서 재현·정량 확인됨.

■ 시도한 반증과 결과 (전부 실패)
1. "상위 가드가 있을 것" → 없음. resolve_status_intent의 directive_patterns(assistant.py:767-771)는 완료/제외/포함 계열 문구만 선제거하며 '상황/현황' 명사구 처리가 전무. 이후 787-790행이 `if alias and alias in scan` 무경계 부분문자열 매칭으로 판정.
2. "요약 요청이면 statuses가 무시될 것" → 무시 안 됨. 2234행 SU

## 4. [High] '이번 주'와 '지난주'의 주 범위 정의가 불일치 — 주말 마감 티켓이 '이번 주'에서 조용히 누락됨

- 영역: 라이브 사용자 여정
- 위치: `/opt/claude-work-assistant/assistant.py:838`
- 재현: ssh -o BatchMode=yes cloviradmin@10.100.64.71 'curl -s -X POST http://127.0.0.1:5678/webhook/clovirone-work-assistant -H "Content-Type: application/json" --data @-' <<< '{"requester":{"email":"hshwang@goodmit.co.kr","name":"황형섭"},"message":"이번 주에 마감인 일 뭐 있어?","conversation_id":"audit-x2","message_id":"m1"}'
→ context.last_query.due_filter 의 start/end 확인. 이어서 message="지난주 마감인 일" 로 재호출해 end가 일요일(월+6)로 잡히는 것과 대조.
- 기대: '주'의 경계 정책이 하나여야 한다. '이번 주'가 업무주(월~금) 정책이라면 '지난주'도 월~금(월+4)이어야 하고, 달력주(월~일) 정책이라면 '이번 주' 종료도 일요일(월+6)이어야 한다. 라벨과 실제 구간도 일치해야 한다(2일 구간이면 '이번 주'가 아니라 '오늘~금요일'로 표기).
- 실제: '이번 주'=오늘~금요일(목요일 실행 시 2일), '다음 주'=월~금(5일), '지난주'=월~일(7일)로 세 표현의 정책이 제각각. 토·일 마감 티켓은 '이번 주' 질의에서 영원히 조회되지 않지만 '지난주' 질의에서는 조회된다. 사용자는 '이번 주 마감 2건'을 전부로 신뢰하게 된다.
- 원인 근거:
```
parse_date_range() 내 주 단위 표현의 종료일 계산이 표현마다 다르다:

    838:    if "이번주" in n or "금주" in n:
    839:        return {"mode": "BETWEEN", "start": today.isoformat(), "end": (monday + timedelta(days=4)).isoformat(), "label": "이번 주"}
           # → 종료 = 월+4 = 금요일 (5일), 시작 = 오늘
    843:    if "지난주" in n or "저번주" in n or "전주" in n:
    844:        last_mon = monday - timedelta(days=7)
    845:        return {"mode": "BETWEEN", "start": last_mon.isoformat(), "end": (last_mon + timedelta(days=6)).isoformat(), "label": "지난주"}
           # → 종료 = 월+6 = 일요일 (7일), 시작 = 월요일
    834:    다음주 → start=월+7, end=월+1
```
- 수정 방향: 주 경계 계산을 단일 헬퍼로 통합한다. week_bounds(anchor_monday, include_weekend: bool) -> (start, end) 를 만들고 이번주/다음주/지난주가 모두 이를 호출하도록 한다. 주말 포함 여부는 상수(WEEK_INCLUDES_WEEKEND)로 한 곳에서 결정한다. '이번 주'의 start를 today로 자르는 동작을 유지하려면 label을 실제 구간에 맞춰 생성하고(예: "이번 주(오늘~금)"), 이미 기한이 지난 이번 주 미완료 티켓이 누락되지 않도록 start=monday 로 두고 기한초과 항목을 별도 표기하는 방안을 권장한다. 838/843행에 주 경계 회귀 테스트를 요일별(월~일 7케이스)로 추가한다.
- 검증자 판정: 반증 실패 — 주장은 성립한다. 시도한 반증 경로와 결과:

1) 코드 실재 확인 (반증 실패)
C:\Users\hshwa\clovirone-web-assistant\runner\claude-work-assistant\assistant.py (APP_VERSION 3.13.0). 주장의 행번호(838/843)는 3.13.0에서 861/866으로 밀렸으나 로직은 동일:
- 861행 이번주: start=today, end=monday+4 (금)
- 857행 다음주: start=monday+7, end=monday+11 (금, 5일)
-

## 5. [High] n8n 멱등성 캐시(processedMessages)가 message_id만으로 키를 만들어 요청자/대화 스코프가 없음 — 타 사용자의 응답·컨텍스트가 그대로 반환됨

- 영역: n8n 워크플로
- 위치: `C:\Users\hshwa\Downloads\ClovirONE_AI_Work_Assistant\ClovirONE_AI_Work_Assistant_v7.json:26`
- 재현: 1) 사용자 A가 message_id='testmsg01'로 '내 티켓 목록 보여줘'를 웹훅에 보낸다. 2) 사용자 B(다른 requester.email)가 동일하게 message_id='testmsg01'로 아무 메시지나 보낸다. 3) B의 응답을 확인한다.
- 기대: 멱등성은 (requester, conversation_id, message_id) 단위여야 하며, B는 B 자신의 요청에 대한 응답을 받아야 한다.
- 실제: NODE 1이 processed['testmsg01']을 히트시켜 B에게 A의 전체 응답을 반환한다 — response_text, tickets/projects 목록, context.selected_ticket까지 포함. 요청자 검증 없는 교차 사용자 데이터 노출이다. 추가로 이 캐시는 실행 '완료 후'에만 채워지므로(NODE 10 timeout 240000ms), 최초 요청이 실행 중인 최대 4분 창에서는 동일 message_id 재시도가 중복 탐지되지 않고 티켓이 두 번 생성될 수 있다.
- 원인 근거:
```
NODE 1 '요청 전처리'(line 26):
  const processed = staticData.processedMessages ?? {};
  if (processed[messageId]) { return [{ json: { local_handled: true, ..., local_response: { ...processed[messageId], duplicate: true, ... } } }]; }
NODE 18 '최종 응답 저장'(line 433):
  processed[value.message_id] = value;   // value = context/tickets/projects 포함 전체 응답
키가 requester나 conversation_id로 스코프되지 않은 전역 맵이다. 반면 백엔드는 올바르게 스코프한다 — assistant.py:3959 `prior = load_processed_message(requester, conversation_id, message_id)`. n8n이 NODE 1에서 먼저 short-circuit하므로 백엔드의 올바른 스코프 검사는 아예 도달하지 못한다.
message_id는 클라이언트가 제어한다: 웹 플랫
```
- 수정 방향: NODE 1/NODE 18의 키를 `${requester.email}|${conversation_id}|${message_id}`로 변경한다. 더 나은 방향은 n8n의 processedMessages를 제거하고 이미 requester 스코프로 올바르게 구현된 백엔드(load_processed_message/save_processed_message)에 멱등성을 일원화하는 것이다 — 현재는 약한 구현이 강한 구현을 가리고 있다.
- 검증자 판정: 반증 실패 — 결함은 실재하며 배포된 시스템에서 라이브 재현했다.

[정적 확인 ✅]
- NODE 1 '요청 전처리'(v7.json jsCode line 23): `const processed = staticData.processedMessages ?? {}; if (processed[messageId]) { ... }` — 키가 messageId 단독이다. 게다가 이 중복 검사는 `if (!requester.email && !requester.name)` 요청자 가드보다 **앞에** 위치해, requester는 비교는커녕 존재 확

## 6. [High] 티켓 첨부 이미지가 현재 메시지 것이 아니라 대화 디렉터리의 '가장 오래된 파일 3개'를 붙임 + conversation_id 기본값 공유로 타인 이미지 유출

- 영역: n8n 워크플로
- 위치: `C:\Users\hshwa\Downloads\ClovirONE_AI_Work_Assistant\ClovirONE_AI_Work_Assistant_v7.json:562`
- 재현: 1) 한 대화에서 이미지 A를 첨부해 티켓 1을 만든다. 2) 같은 대화(24시간 이내)에서 이미지 B만 첨부해 티켓 2를 만든다. 3) Notion에서 티켓 2의 본문 이미지 블록을 확인한다. 별도로: conversation_id를 생략한 PowerShell 클라이언트 두 대에서 각각 이미지를 첨부해 티켓을 만든다.
- 기대: 티켓 2에는 이번 메시지에 첨부한 이미지 B만 붙어야 한다. 서로 다른 사용자의 이미지가 섞이면 안 된다.
- 실제: glob이 A와 B를 모두 반환하고 slice(0,3)이 오래된 순으로 자르므로 티켓 2에 이미지 A(무관한 이전 턴 스크린샷)가 함께 붙는다. 디렉터리에 24시간 내 이미지가 3개 이상 쌓여 있으면 이번 메시지의 이미지 B는 아예 누락되고 옛 이미지만 붙는다. 또 conversation_id를 안 보내는 클라이언트는 모두 key='powershell-local' 디렉터리를 공유하므로, 사용자 B가 만든 티켓에 사용자 A의 스크린샷이 첨부되는 교차 사용자 유출이 발생한다.
- 원인 근거:
```
NODE 25 '첨부 후보 확인'(line 562):
  const key = conv.replace(/[^A-Za-z0-9_-]/g, '').slice(0, 64) || 'unknown';
  return [{ json: { page_id: created.id, glob: '/home/n8n/.n8n-files/clovirone-work-assistant-images/' + key + '/*' } }];
NODE 27 '첨부 필터'(line 590): `return items.slice(0, 3);`
디렉터리 전체를 glob하고 앞 3개를 자른다. 현재 message_id로 필터링하지 않는다.
러너 측 파일 수명·이름 규칙(assistant.py:1905-1906): `file_name = f"{int(time.time())}-{os.urandom(8).hex()}.{ext}"`, TTL은 assistant.py:1811 `IMAGE_TTL_SECONDS = int(os.environ.get("ASSISTANT_IMAGE_TTL_SECONDS", str(24 * 3600)))`. 즉 파일은 24시간 남고, 이름이 unix timestamp 접두사라 사전순 
```
- 수정 방향: 러너가 이미 이번 메시지에 저장한 파일명을 알고 있으므로(assistant.py save_image_attachments가 `file_name`을 반환), 응답 data에 해당 파일명 목록을 실어 n8n에 넘기고 NODE 25는 그 파일들만 명시적으로 읽게 한다(glob '*' 금지). 업로드 성공 후 해당 파일을 삭제하거나 uploaded/ 하위로 이동시킨다. NODE 1의 'powershell-local' 기본값을 제거하고 conversation_id를 필수로 하거나 requester 식별자를 키에 포함시킨다.
- 검증자 판정: 반증 실패 — 핵심 결함은 성립한다.

[코드 확인 ✅]
- v7.json:570 NODE '첨부 후보 확인': glob = '/home/n8n/.n8n-files/clovirone-work-assistant-images/' + key + '/*' (인용 그대로).
- v7.json:589 NODE '첨부 필터': `return items.slice(0, 3);` — message_id 필터 없음.
- assistant.py:1904 file_name = f"{int(time.time())}-{os.urandom(8).hex()}.

## 7. [High] Notion DB가 0행을 반환하면 '프로젝트 묶기'부터 'API 응답'까지 전 체인이 스킵되어 웹훅이 무응답으로 행업

- 영역: n8n 워크플로
- 위치: `C:\Users\hshwa\Downloads\ClovirONE_AI_Work_Assistant\ClovirONE_AI_Work_Assistant_v7.json:97`
- 재현: 1) Notion 통합 토큰에서 '프로젝트' DB(262c5c5a-5684-8108-a949-c4503dd5f9a7) 공유를 해제하거나 DB를 비운다(Notion은 오류가 아니라 200 + 빈 results를 반환). 2) 캐시 TTL(5분) 경과 후 웹훅에 아무 조회 메시지를 보낸다. 3) 응답을 기다린다.
- 기대: 프로젝트가 0건이면 projects=[] 로 백엔드에 넘어가고, 사용자는 '프로젝트가 없습니다' 류의 정상 응답을 받아야 한다.
- 실제: 프로젝트 전체 조회가 0 아이템을 내보내 프로젝트 묶기 이하 전 체인이 스킵되고 respondToWebhook이 실행되지 않는다. 웹훅 호출자는 응답 없이 타임아웃까지 대기한다(오류 메시지조차 없음). 작업 DB가 비는 경우도 동일.
- 원인 근거:
```
캐시 미스 경로는 단일 직렬 체인이다: 캐시 유효?(false) → 프로젝트 전체 조회(line 97) → 프로젝트 묶기(116) → 작업 전체 조회(140) → 작업 묶기(159) → 작업 DB 스키마 조회(181) → 캐시 기록(558) → AI 요청 구성(200) → ... → API 응답(450).
워크플로 JSON 전체에 `alwaysOutputData` 문자열이 0회 등장한다(grep 확인). n8n은 입력 아이템이 0개인 노드를 실행하지 않고 하위 노드를 스킵하며, 바로 그 때문에 alwaysOutputData 설정이 존재한다.
'프로젝트 묶기'의 코드는 빈 배열을 방어하려 하지만(`$input.all().map(...).filter(...)`) 노드 자체가 실행되지 않으므로 이 방어는 무의미하다.
실제 이력 근거 — 서버 로그에 같은 계열의 스킵 사고가 남아 있다: `journalctl -u n8n` 2026-07-15 19:56:26 → "TypeError: Cannot assign to read only property 'name' of object 'Error: Node '프로젝트 묶기' hasn't been executed'" (@n8n
```
- 수정 방향: '프로젝트 전체 조회'와 '작업 전체 조회'에 `alwaysOutputData: true`를 설정해 빈 결과에서도 아이템 1개가 흐르게 한다(그러면 기존 filter 방어 코드가 정상 동작). 아울러 Notion 429/5xx 대비로 두 노드에 retryOnFail을 추가한다 — 현재 워크플로 전체에 retryOnFail이 단 한 건도 없다.
- 검증자 판정: 반증 실패. 결함은 실재하며, 주장자의 증거가 아니라 서버에 설치된 n8n 2.29.9 엔진 소스에서 직접 인과 사슬 전체를 확인했다.

[확정된 인과 사슬 — 모두 소스로 검증]
1) 프로젝트 전체 조회 = Notion databasePage:getAll, returnAll:true → 빈 DB에서 0 아이템 출력.
2) 0 아이템 → 하위 노드 미실행: /opt/n8n/lib/node_modules/n8n/node_modules/n8n-core/dist/execution-engine/workflow-execute.js:530 `

## 8. [High] run-now가 schedule.enable 승인 게이트를 완전 우회 — operator가 비활성·미승인 스케줄의 write workflow를 즉시 실행

- 영역: 플랫폼 API
- 위치: `app/schedules/router.py:373`
- 재현: 실측 출력:
1) admin 로그인 → POST /api/admin/workflows {"name":"danger-wf", "operation_mode":"write", "approval_required":false, "enabled":true} → 201
2) POST /api/admin/schedules {target_type:"workflow", target_ref:wid, preset:"daily"} → 201, 응답 enabled=False (한 번도 승인된 적 없음)
3) admin 로그아웃 → operator 로그인
4) POST /api/admin/schedules/{sid}/run-now (X-CSRF-Token: operator)
   → RUN-NOW AS OPERATOR: 200 {"ok":true,"run":{..."status":"queued"...}}
5) Worker.run_once() → RUN succeeded {"ok": true}
   outbound calls: ['http://127.0.0.1:5678/webhook/clovirone-work-assistant']
- 기대: 스케줄 활성화가 승인 대상(spec §20)이라면, 같은 스케줄 정의를 즉시 실행하는 run-now도 최소한 (a) enabled=True인 스케줄만 허용하거나 (b) 동일한 승인 게이트를 통과해야 한다. 또한 스케줄을 만들 수도 활성화할 수도 없는 operator가 미승인 정의를 실행할 수 있어서는 안 된다.
- 실제: run_now는 row.enabled를 전혀 보지 않고 create_run_and_enqueue를 호출한다. 결과적으로 admin이 승인 없이 스케줄을 만들고 → operator(또는 본인)가 run-now를 눌러 write workflow를 실제로 호출할 수 있다. 승인 게이트는 주기 실행에만 걸리고 동일 payload의 수동 실행에는 전혀 걸리지 않는다.
- 원인 근거:
```
@router.post("/{schedule_id}/run-now", dependencies=[Depends(require_roles(*OPS_ROLES))])
async def run_now(request: Request, schedule_id: str, db: Session = Depends(get_db)):
    row = _get_or_404(db, schedule_id)          # ← row.enabled 검사 없음
    now = request.app.state.clock.now()
    ...
    run = create_run_and_enqueue(db, row, scheduled_at=now, now=now, key=key, manual=True)

# 대조: enable은 승인 대상
#   enable_schedule(): if needs_approval(request.state.user): → 202 approval_pending
# OPS_ROLES = ("operator", "admin", "system_admin")  ← operator는 스케줄 생성/수정/활성 권한이 없음(WRITE_ROLES=admin+)
```
- 수정 방향: run_now에 (1) `if not row.enabled: raise ConflictError('활성화되지 않은 스케줄은 실행할 수 없습니다.')` 가드 추가, 또는 enable과 동일하게 needs_approval 분기 적용. (2) 권한을 WRITE_ROLES로 올리거나, target_type==workflow인 경우만 admin+로 제한. (3) 회귀 테스트: enabled=False 스케줄에 대한 run-now → 409, operator의 workflow run-now → 403.
- 검증자 판정: 반증 5회 시도, 전부 실패. 오히려 스펙이 주장보다 강한 근거를 제공한다.

[반증 시도와 실패 사유]
1. create_run_and_enqueue의 하위 가드 → 없음. app/schedules/scheduler.py:70-106은 schedule.enabled를 전혀 읽지 않는다. enabled.is_(True) 필터는 SchedulerService.tick()(line 136)에만 있고 run_now는 tick을 거치지 않는다.
2. job handler 가드 → 부분적으로만 방어. app/jobs/handlers/sche

## 9. [High] operator/admin의 Job 큐 조회가 타인의 채팅 전문과 첨부 이미지 원본(base64)을 그대로 노출 — 대화 API는 403인데 큐로 우회됨

- 영역: 플랫폼 API
- 위치: `app/jobs/router.py:36`
- 재현: 실측 출력:
1) victim(user) 로그인 → POST /api/conversations → POST /api/conversations/{cid}/messages
   {"content":"내 연봉 협상 초안 좀 검토해줘. 현재 8000, 목표 9500.", "attachments":[{"filename":"payslip.png","media_type":"image/png","data":<base64 PNG>}]} → 202
2) victim 로그아웃 → operator 로그인
3) GET /api/admin/jobs
   JOBS AS OPERATOR 200
     job_type: chat_message
     requester: {'user_id': 'c0f149ab...', 'email': 'victim@goodmit.co.kr', 'name': '테스트 사용자'}
     content: 내 연봉 협상 초안 좀 검토해줘. 현재 8000, 목표 9500.
     attachment: payslip.png data_len: 92 stripped: None      ← 이미지 원본 바이트 그대로
4) 같은 operator로 GET /api/conversations/{cid}/messages
   OPERATOR DIRECT CONV READ: 403 {'code': 'forbidden', 'message': '본인 대화만 접근할 수 있습니다.'}
- 기대: 대화 본문 소유권이 서버측에서 403으로 강제된다면(chat/service.py:get_owned_conversation), 같은 데이터를 담은 Job payload도 운영 화면에서 원문 그대로 노출되면 안 된다. 큐 운영에 필요한 것은 job_type/status/attempt/last_error/식별자이지 본문이 아니다. 이미지 바이트는 '서버 미보관' 원칙(§13 확장) 대상이므로 더더욱 응답에 실려선 안 된다.
- 실제: operator(및 admin/system_admin)가 GET /api/admin/jobs 한 번으로 전 사용자의 채팅 원문 + 요청자 이메일 + 첨부 이미지 base64를 페이지네이션으로 수집할 수 있다. 대화 API의 IDOR 방어가 큐 화면으로 그대로 우회된다.
- 원인 근거:
```
def _job_view(job: Job) -> dict:
    return {
        ...
        "payload": json.loads(job.payload_json),   # ← 마스킹 없음
        ...
    }

router = APIRouter(prefix="/api/admin/jobs",
    dependencies=[Depends(require_roles("operator", "admin", "system_admin")), Depends(require_csrf)])

# payload 구성 (chat/service.py:_build_job_payload)
#   {"content": message.content, "requester": {user_id,email,name}, "attachments":[{filename,media_type,data(base64)}]}
# 감사 로그는 mask_sensitive를 거치는데(core/audit.py) job payload는 그 경로를 타지 않는다.
```
- 수정 방향: _job_view에서 payload를 (1) mask_sensitive 적용 + (2) chat_message는 화이트리스트 필드만(conversation_id, message_id, requester.user_id, content_length) 노출하고 content/attachments.data는 제거. 원문이 꼭 필요하면 별도 엔드포인트로 분리해 system_admin + 감사 로그 기록 필수로 하고, 첨부 data는 어떤 경우에도 응답에 싣지 않는다. 회귀 테스트: operator의 /api/admin/jobs 응답에 'data' 키와 원문 content가 없을 것.
- 검증자 판정: 반증 시도 4건 모두 실패 — 주장이 성립한다.

[반증 시도 1] 상위 호출부/미들웨어 마스킹 존재? → 없음. app/jobs/router.py:36 `_job_view`는 `json.loads(job.payload_json)`를 그대로 반환하고, 라우터 의존성은 require_roles("operator","admin","system_admin")와 require_csrf뿐이며 응답 필터링 계층이 없다.

[반증 시도 2] mask_sensitive가 처리? → 실패. job payload는 core/audit.py 경로를 타

## 10. [High] document_generate가 workflow.approval_required와 템플릿 approval_policy를 전혀 검사하지 않아, admin 1명이 mode=auto_publish로 무승인 Notion 발행 가능 (schedule_run 경로와 정책 충돌)

- 영역: 플랫폼 API
- 위치: `app/documents/service.py:82`
- 재현: 실측 출력:
1) admin 로그인 → POST /api/admin/workflows {"name":"doc-wf", "operation_mode":"write", "approval_required": true, "enabled": true} → 201
2) POST /api/admin/templates {"name":"weekly", "target_ref": wid, "approval_policy": {"required": true}, "enabled": true} → 201
3) POST /api/admin/documents/generate {"workflow_id": wid, "mode": "auto_publish", "period":"2026-W29", "config":{"template_id": tid, "target_parent_page":"page-1"}} → 202
4) Worker.run_once()
5) GET /api/admin/documents/{gid} → STATUS: published  PUBLISHED_REF: https://notion.so/published-abc
6) GET /api/admin/approvals → APPROVALS CREATED: 0 []

즉 approval_required=true + approval_policy.required=true 인데 승인 0건으로 Notion 발행 완료.
- 기대: approval_required=true인 write workflow는 문서 발행 경로에서도 승인 없이 실행되면 안 된다(schedule_run과 동일한 fail-closed). 템플릿의 approval_policy.required=true면 mode를 auto_publish로 요청해도 preview_then_approve로 강등되거나 거부되어야 한다.
- 실제: mode를 요청자가 자유롭게 고른다. auto_publish를 고르면 workflow.approval_required도, 템플릿 approval_policy도 무시되고 핸들러가 곧바로 _publish → Notion 발행. §20 승인 게이트와 §19.3 발행 승인이 모두 사용자 선택으로 무력화되며, 같은 workflow가 스케줄 경로에서는 거부되고 문서 경로에서는 통과하는 화면별 정책 충돌이 발생한다.
- 원인 근거:
```
def request_generation(db, *, workflow_id, mode, config, period, requested_by, now, document_automation_enabled):
    ...
    workflow = db.get(Workflow, workflow_id)
    if workflow is None: raise ValidationAppError(...)
    if not workflow.enabled: raise ConflictError(...)
    # ← workflow.approval_required 검사 없음, config['template_id']의 approval_policy 검사 없음
    # mode는 요청 본문에서 그대로 옴 (router.py GenerateRequest.mode: str = "preview_then_approve")

# 대조: schedule_run 핸들러는 fail-closed
#   if workflow.operation_mode == "write" and workflow.approval_required:
#       if not payload.get("approved"
```
- 수정 방향: request_generation에 (1) `if workflow.operation_mode == "write" and workflow.approval_required and mode == MODE_AUTO_PUBLISH: raise ConflictError(...)` 또는 mode를 MODE_PREVIEW_THEN_APPROVE로 강등. (2) config['template_id']가 있으면 AutomationTemplate.approval_policy_json의 required를 읽어 동일 강등/거부 적용. (3) handle_document_generate의 MODE_AUTO_PUBLISH 분기에도 동일한 fail-closed 검사를 이중으로 둔다(핸들러가 최종 보안 경계). (4) approval_policy_json을 읽는 코드가 하나도 없다는 사실 자체가 회귀 대상 — 강제 로직 추가와 함께 테스트 핀.
- 검증자 판정: 반증 실패 — 결함은 실제로 성립한다.

[시도한 반증 경로 5가지, 전부 실패]
1) request_generation 상위 가드? 없음. app/documents/service.py:82-86은 workflow is None과 workflow.enabled만 검사. approval_required 미검사, config['template_id']의 approval_policy 미조회.
2) 핸들러 하위 가드? 없음. app/jobs/handlers/document_generate.py:96-98이 곧바로 `if gen.mode =

## 11. [High] 담당자별 그룹 집계가 '담당자 있는 티켓'을 미할당으로 집계 — 같은 티켓을 미할당 필터는 제외 (person_label 수정 누락 지점)

- 영역: 러너 데이터 표시
- 위치: `C:\Users\hshwa\clovirone-web-assistant\runner\claude-work-assistant\assistant.py:2549`
- 재현: RUNNER_TOKEN=x python -c "import assistant as a; sm=a.actual_status_map({},[{'status':'진행'}]); t1=a.normalize_ticket({'id':'t1','properties':{'제목':{'title':[{'plain_text':'Tt1'}]},'진행상태':{'status':{'name':'진행'}},'티켓 담당자':{'people':[{'object':'user','id':'6f1b2c3d-aaaa-bbbb-cccc-1234567890ab'}]}}},{}); print(a.query_tickets('담당자별 티켓 보여줘',{},{'email':'a@b.com','name':'황형섭'},None,[],[t1],sm)['response_text'])"
- 기대: 담당자 people 값이 존재하면 이름 해석 실패와 무관하게 '미할당' 버킷에 들어가서는 안 된다. format_ticket(1111행)·TICKET_DETAIL(2522행)이 쓰는 person_label()과 동일한 라벨 정책이어야 한다.
- 실제: 이름/이메일이 비면 버킷 키가 ''가 되어 미할당으로 합산된다. 담당자별 건수가 틀리고, '미할당 티켓 보여줘'와 건수가 서로 모순된다(2건 vs 1건).
- 원인 근거:
```
_bucket(): names = [text(p.get("name")) or text(p.get("email")) for p in safe_list(t.get("assignees"))] / return ", ".join(x for x in names if x) or "미할당"  ← id 폴백 없음.
실측 출력(같은 데이터, 같은 요청):
  [담당자별 티켓 보여줘] ■ 미할당: 2건 / - Tt1(담당자 id=6f1b2c3d-…있음) / - Tt3(진짜 미할당)
  [미할당 티켓 보여줘] 미할당 티켓 (완료 제외): 총 1건
assignee_filter_matches(1382행 부근)는 len(persons)==0만 미할당으로 보는데 _bucket은 '이름 해석 실패'까지 미할당으로 뭉갠다.
```
- 수정 방향: _bucket의 assignee 분기를 person_label(p) 사용으로 교체: names = [person_label(p) for p in safe_list(t.get('assignees'))]; return ', '.join(names) or '미할당'. 이번 person_label 도입(1103행)이 format_ticket/DETAIL 2곳에만 적용되고 집계 경로에 누락됐으므로, person_label을 모든 사람 렌더 경로의 단일 관문으로 강제(테스트로 핀).
- 검증자 판정: 반증 4회 시도, 전부 실패. 결함 성립.

[1] "id만 있는 assignee는 정규화에서 걸러진다"? → 반증 실패. assistant.py:546 `return [p for p in result if p["id"] or p["name"] or p["email"]]` — id만 있어도 명시적으로 보존된다. people_value(595행)가 assignees의 유일한 생산자이므로 {'id':'6f1b…','name':'','email':''}는 정상 도달 가능한 값이다. Notion integration이 user-info c

## 12. [High] '담당자별로 보여줘'가 담당자 이름 '별로'를 찾다가 실패 — 담당자별 집계 조회 자체가 불가

- 영역: 러너 데이터 표시
- 위치: `C:\Users\hshwa\clovirone-web-assistant\runner\claude-work-assistant\assistant.py:1290`
- 재현: RUNNER_TOKEN=x python -c "import assistant as a; sm=a.actual_status_map({},[{'status':'진행'}]); t=a.normalize_ticket({'id':'a','properties':{'제목':{'title':[{'plain_text':'T'}]},'진행상태':{'status':{'name':'진행'}}}},{}); print(a.query_tickets('전체 티켓 담당자별로 보여줘',{},{'email':'a@b.com','name':'황형섭'},None,[],[t],sm)['response_text'])"
- 기대: '담당자별로 보여줘' → group_by=assignee 집계 목록(TICKET_SUMMARY).
- 실제: NEED_INPUT '별로' 담당자를 찾지 못했습니다 — 존재하지도 않는 사람을 되묻고 집계는 영원히 못 본다. '담당자별로 몇건인지'도 동일하게 실패.
- 원인 근거:
```
_explicit_assignee_token patterns[3]: r"담당자(?:는|가|:)?\s*([가-힣A-Za-z][가-힣A-Za-z0-9._+@-]{1,80})"  → '담당자별로'에서 '별로'를 사람 이름으로 캡처.
실측: a.extract_group_by('전체 티켓 담당자별로 보여줘') == 'assignee' 인데 a._explicit_assignee_token(...) == '별로'
최종 응답: NEED_INPUT "'별로' 담당자를 찾지 못했습니다. 정확한 이름 또는 회사 이메일을 알려주세요."
('담당자별 티켓'은 통과 — '별' 1글자라 {1,80} 미달. '담당자별로/담당자별X' 형태만 강탈됨)
```
- 수정 방향: _explicit_assignee_token 진입 전(또는 패턴 앞)에 그룹 지시어를 배제: extract_group_by(message)가 'assignee'이거나 정규식에 (?!별) 부정 전방탐색 추가 — r"담당자(?:는|가|:)?\s*(?!별)([가-힣A-Za-z]...)". _GROUP_TOKENS와 담당자 토큰 추출이 같은 어휘를 두고 경쟁하지 않도록 우선순위를 한 곳에서 결정.
- 검증자 판정: 반증 실패 — 결함은 실재하며, 라이브 프로덕션에서 재현됨.

■ 시도한 반증 벡터 (모두 실패)
1) "상위 호출부 가드가 있을 것" → 없음. assistant.py:2163 `is_freeform_query()`가 유일한 분기인데, extract_group_by()가 참이고 _REASONING_MARKERS가 없으면 False를 반환해 오히려 query_tickets(규칙 엔진)로 **확정 라우팅**한다(2068). 즉 이 코드는 결함 경로를 막기는커녕 보장한다.
2) "NOT_FOUND 앞에 group_by 배제가 있을 것"

## 13. [High] '남' 한 글자 하드코딩이 완료 조회를 무력화 — '강남/하남/성남/남수' 등이 들어가면 완료 티켓이 0건으로 표시

- 영역: 러너 데이터 표시
- 위치: `C:\Users\hshwa\clovirone-web-assistant\runner\claude-work-assistant\assistant.py:2378`
- 재현: RUNNER_TOKEN=x python -c "import assistant as a; sm=a.actual_status_map({},[{'status':'진행'},{'status':'완료'}]); d=a.normalize_ticket({'id':'d','properties':{'제목':{'title':[{'plain_text':'강남 회선'}]},'진행상태':{'status':{'name':'완료'}}}},{}); print(a.query_tickets('강남 완료된 티켓만 보여줘',{},{'email':'a@b.com','name':'황형섭'},None,[],[d],sm)['response_text'])"
- 기대: '강남 완료된 티켓만 보여줘' → 완료 상태 티켓 1건. 프로젝트명·사람 이름에 들어간 '남' 음절이 상태 정책을 바꿔서는 안 된다.
- 실제: 헤더는 '(완료)'라고 하면서 0건 — 오류도 안내도 없이 사실과 다른 답(완료 티켓이 없다)을 낸다. 실사용 지사명(강남/하남/성남/남양주)과 인명(남수/김남일)에서 상시 재현.
- 원인 근거:
```
"exclude_completed": exclude_completed or due_filter is not None or "남" in message or default_active   ← 원문 메시지에 대한 무맥락 부분 문자열 검사('남은'을 노린 것으로 보이나 음절 단위로 걸림)
실측:
  '완료된 티켓만 보여줘'      -> 전체 티켓 (완료): 총 1건
  '강남 완료된 티켓만 보여줘' -> 전체 티켓 (완료): 총 0건
  '남수 완료된 티켓만 보여줘' -> 전체 티켓 (완료): 총 0건
statuses=[완료] 필터 통과 후 exclude_completed→ticket_active()가 완료를 다시 제거해 결과가 전멸한다.
```
- 수정 방향: '남' 검사 삭제. 잔여 티켓 의도는 이미 resolve_status_intent의 '남은티켓/남은작업/남아있는티켓' 토큰(730행 부근)이 정규화된 문장에서 판정하므로 중복이자 오탐 소스다. 부득이 유지하려면 norm(message) 기준 '남은'/'남아' 단어 경계 검사로 좁히고, completed_only일 때는 절대 exclude_completed를 켜지 않도록 상호배타 보장.
- 검증자 판정: 반증 실패 — 결함은 실재하며 프로덕션(3.13.0)에도 살아있다.

[검증 ✅] 반증 시도 4건 전부 실패
1) 상위 라우터 가드? 없음. answer_query(2153-2165)는 is_freeform_query=False인 네 문장 모두 규칙 엔진 query_tickets로 보낸다(실측 확인). LLM 경로로 새지 않는다.
2) completed_only가 막아주나? 아니다. resolve_status_intent(757-761)는 completed_only=True, selected=[완료], exclude_complete

## 14. [High] 후속 발화에서 '완료 포함' 요청이 마감 필터에 의해 무시됨 — 같은 문장이 첫 질문 2건 / 후속 1건

- 영역: 러너 데이터 표시
- 위치: `C:\Users\hshwa\clovirone-web-assistant\runner\claude-work-assistant\assistant.py:2339`
- 재현: RUNNER_TOKEN=x python -c "import assistant as a; sm=a.actual_status_map({},[{'status':'진행'},{'status':'완료'}]); today=a.now_kst().date().isoformat(); mk=lambda i,st:a.normalize_ticket({'id':i,'properties':{'제목':{'title':[{'plain_text':i}]},'진행상태':{'status':{'name':st}},'마감일':{'date':{'start':today}}}},{}); ts=[mk('d','완료'),mk('p','진행')]; req={'email':'a@b.com','name':'황형섭'}; m='완료 포함해서 오늘 마감인 티켓 보여줘'; r1=a.query_tickets(m,{},req,None,[],ts,sm); r2=a.query_tickets(m,r1['context'],req,None,[],ts,sm); print(r1['response_text'].splitlines()[0]); print(r2['response_text'].splitlines()[0])"
- 기대: 명시적 '완료 포함'은 어느 대화 위치에서든 마감 조건보다 우선한다. 같은 문장은 같은 건수를 낸다.
- 실제: 대화 두 번째부터는 완료가 빠져 1건. 사용자는 방금 '완료 포함'이라고 말했는데 헤더는 '완료 제외'라고 표시한다. 화면(첫 질의 vs 후속)마다 완료 제외 정책이 다르다.
- 원인 근거:
```
후속(use_previous) 분기: 2325~2331에서 include_completed → query["exclude_completed"]=False 로 정한 직후,
  if due_filter is not None:
      query["due_filter"] = due_filter
      query["exclude_completed"] = True      # ← 사용자의 명시적 '완료 포함'을 무조건 덮어씀
반면 신규 질의 분기는 2378에서 같은 due_filter 규칙을 쓰지만 2379~2383의 `if include_completed:` 가 마지막에 실행돼 exclude_completed=False로 복구된다. 두 경로의 우선순위가 반대다.
실측(동일 문장 '완료 포함해서 오늘 마감인 티켓 보여줘'):
  first= 전체 티켓 (오늘): 총 2건 | followup= 전체 티켓 (완료 제외, 오늘): 총 1건
```
- 수정 방향: 후속 분기에서 due_filter 설정 시 exclude_completed를 강제하지 말고, 신규 분기와 동일하게 status_intent를 마지막에 적용: `query['exclude_completed'] = (not include_completed) and (exclude_completed or True)` 형태로 include_completed/completed_only가 항상 최종 우선권을 갖게 한다. 두 분기의 완료 정책을 하나의 헬퍼(예: apply_status_policy(query, status_intent, due_filter))로 합쳐 중복 구현 제거.
- 검증자 판정: 반증 실패 — 결함은 실재하고, 주장보다 오히려 더 넓다.

[반증 시도 1] 상위 호출부 가드 존재 여부 → 없음.
answer_query(2162~2165)는 `is_freeform_query(message)`가 False이면 곧바로 query_tickets로 보낸다. 문제 문장 3종 모두 is_freeform_query=False로 확인(즉 LLM 우회 없이 규칙엔진 직행). claude_query의 freeform last_query 무효화 가드(2193~2199)도 이 경로엔 적용되지 않는다. 후속 분기를 막는 가드는 어디

## 15. [High] '이번주' 마감 조회가 주말·지난 요일에 start>end 빈 범위를 만들어 항상 0건

- 영역: 러너 데이터 표시
- 위치: `C:\Users\hshwa\clovirone-web-assistant\runner\claude-work-assistant\assistant.py:861`
- 재현: RUNNER_TOKEN=x python -c "import assistant as a; from datetime import date; print(a.parse_date_range('이번주 마감 티켓', date(2026,7,18))); print(a.parse_date_range('이번주 월요일까지 마감인 티켓', date(2026,7,15)))"
- 기대: 주말에 '이번주 마감'을 물으면 최소한 그 주(월~금 또는 월~일)의 티켓이 보이거나, 범위가 비었음을 알려야 한다.
- 실제: 라벨은 '이번 주'라고 붙은 채 조용히 0건. 사용자는 '이번 주 마감이 없다'고 오인한다. 금요일 이후(토·일) 전체와 '이번주 <지난 요일>까지' 문장에서 상시 재현.
- 원인 근거:
```
861: if "이번주" in n or "금주" in n: return {"mode":"BETWEEN","start": today.isoformat(), "end": (monday + timedelta(days=4)).isoformat(), "label":"이번 주"}  (858행 '이번주까지'도 동일 구조)
실측 parse_date_range:
  토(2026-07-18) '이번주 마감 티켓'   -> {'start':'2026-07-18','end':'2026-07-17'}  ← start>end
  일(2026-07-19) '이번주까지 마감'    -> {'start':'2026-07-19','end':'2026-07-17'}
  수(2026-07-15) '이번주 월요일까지'  -> {'start':'2026-07-15','end':'2026-07-13'}  (818행 부근 요일+까지 분기)
due_matches(BETWEEN)은 start<=current<=end 이므로 어떤 티켓도 통과 못 한다.
```
- 수정 방향: BETWEEN 생성 지점에 불변식 추가: start > end 이면 start=monday(또는 end)로 보정하거나 라벨에 '이미 지난 기간'을 명시. 주 범위는 monday~(monday+4|6)로 고정하고 '오늘 이후'가 필요하면 별도 플래그로 표현. parse_date_range 반환 직전 공통 검증 함수로 start<=end를 강제(모든 분기 일괄 적용).
- 검증자 판정: 반증 실패 — 결함은 실재하며 라이브 프로덕션에서 확인됨.

[반증 시도와 실패 사유]
1. 상위 호출부 가드? 없음. parse_date_range 호출부 4곳(2212, 2810, 3247, 3467) 전부 start<=end 검증/보정 없음. 2502-2505는 due_filter를 그대로 due_matches에 전달.
2. due_matches가 역전 범위를 허용? 아님. 937행이 엄격한 `start <= current <= end`라 start>end면 충족 불가.
3. 주말에 요일 분기가 가로챔? 아님. 830행 루프는

## 16. [High] detect_target_status가 티켓 제목 속 상태 단어를 '변경 요청'으로 읽어, 요청하지 않은 진행상태를 승인 없이 Notion에 직접 쓴다

- 영역: 러너 의도 해석
- 위치: `runner/claude-work-assistant/assistant.py:2706`
- 재현: RUNNER_TOKEN=x python -c 로 assistant.update_ticket('배포 완료 안내 티켓 마감일을 내일로 바꿔줘', {}, req, me, [me], [제목='배포 완료 안내', status='진행' 인 본인 티켓], schema, status_map) 실행 (3.13.0에서 재현 확인)
- 기대: 마감일만 변경. 진행상태는 사용자가 말하지 않았으므로 건드리지 않는다.
- 실제: action=WRITE_UPDATE, 응답 "- 진행상태: 진행 → 완료 / - 마감일: 2026-07-20 → 2026-07-17", write_request={"kind":"UPDATE","page_id":"id1","body":{"properties":{"진행상태":{"status":{"name":"완료"}},"마감일":{"date":{"start":"2026-07-17"}}}}} — 승인 단계 없이 상태가 완료로 뒤집힌다. '검증 서버 이관 티켓 마감일을 내일로 바꿔줘' → 검증, '계획 수립 티켓 …' → 계획도 동일.
- 원인 근거:
```
detect_target_status() 마지막 폴백:
    matches = [(len(alias), actual) for alias, actual in status_map.items() if alias and alias in n]
    return sorted(matches, reverse=True)[0][1] if matches else ""
앞의 directional 정규식도 `([가-힣A-Za-z0-9 ]{1,20})(?:으)?로\s*(?:바꿔|...)`로 '로 바꿔' 앞 20자를 통째로 캡처하므로, 그 안에 들어온 제목 단어('완료','검증','계획','이슈')가 상태 별칭에 걸린다. update_ticket()은 이 값을 changes['status']에 넣고 단일 소유 티켓이면 승인 없이 직접 write_request를 발행한다("Confirmation is not required for an explicit change against one exact ticket").
```
- 수정 방향: 상태 단어는 '지시 위치'에서만 인정한다. (1) 폴백(무조건 별칭 부분일치) 제거 — directional 매치가 없으면 빈 문자열을 반환하고 LLM 게이트필에 맡긴다. (2) directional 캡처를 `[^\s]{1,10}` 수준의 직전 1어절로 좁히고, 캡처 구간에 '마감/우선순위/난이도/담당자/시작일' 같은 다른 필드명이 끼어 있으면 상태로 해석하지 않는다. (3) update_ticket에서 resolve_ticket_reference가 'title' 소스로 티켓을 특정했다면 그 제목 문자열을 cleaned_for_fields에서 먼저 제거한 뒤 필드 추출을 돌린다(제목 변경 케이스에 이미 쓰는 _TITLE_CHANGE_RE.sub와 동일한 방어).
- 검증자 판정: 반증 실패 — 결함은 실제로 성립하며, 현재 배포판(3.14.0)에서 재현 확인.

[시도한 반증과 결과]
1. 라우팅 차단? → 반증 실패. is_update_intent("배포 완료 안내 티켓 마감일을 내일로 바꿔줘",{},sm)=True (explicit_write 패턴 "내일로바꿔줘" 매치). L3874-3875에서 update_ticket 호출됨.
2. LLM 게이트필이 방어? → 반증 실패. L2944 게이트필은 `not changes or unresolved_mention`일 때만 동작. 규칙 엔진이 이미 status·

## 17. [High] 날짜 조건이 붙은 '완료 티켓 조회'는 statuses=[완료]와 exclude_completed=True가 동시에 걸려 항상 0건을 반환한다

- 영역: 러너 의도 해석
- 위치: `runner/claude-work-assistant/assistant.py:2378`
- 재현: 완료 상태 + 마감일 오늘인 티켓 1건이 있는 상태에서 '오늘 완료된 티켓만 보여줘' / '지난주에 완료한 티켓 보여줘' / '이번주 완료 티켓 몇개야' (3.13.0 재현 확인)
- 기대: 완료 상태이면서 해당 기간에 해당하는 티켓 목록(예: 1건)
- 실제: statuses=['완료'], exclude_completed=True → "전체 티켓 (완료, 오늘): 총 0건 / 조건에 맞는 티켓이 없습니다." 라벨은 '완료, 오늘'이라 조건이 맞은 것처럼 보이지만 결과는 구조적으로 항상 0건. 사용자는 데이터가 없다고 오해한다.
- 원인 근거:
```
query_tickets() 신규 쿼리 구성:
    "statuses": statuses,
    "exclude_completed": exclude_completed or due_filter is not None or "남" in message or default_active,
후속 질의 경로(2339행)도 동일: `if due_filter is not None: query["due_filter"] = due_filter; query["exclude_completed"] = True`.
필터 적용부에서 statuses(=['완료'])로 완료만 남긴 뒤 exclude_completed로 `ticket_active(t)`(완료·취소 제외)를 다시 적용하므로 교집합이 공집합이 된다.
```
- 수정 방향: exclude_completed는 '사용자가 완료 상태를 명시하지 않았을 때의 기본값'이어야 한다. `default_active`/`due_filter is not None` 분기 앞에 `if statuses or status_intent['completed_only'] or include_completed: exclude_completed=False` 가드를 두고, 후속 경로(2339행)의 무조건 `query['exclude_completed']=True`도 동일 가드로 감싼다. 아울러 필터 적용부에서 statuses와 exclude_completed가 모순되면 statuses(명시 조건)를 우선시킨다.
- 검증자 판정: 반증 실패. 주장은 코드·실행·라이브 3중으로 성립한다.\n\n[반증 시도와 결과]\n1) \"completed_only 인텐트가 이미 exclude_completed=False 가드를 건다\" → 인텐트 층(728-761행)에서는 실제로 False를 반환하지만, 2378행 `exclude_completed or due_filter is not None or \"남\" in message or default_active`의 `due_filter is not None` 항이 이를 다시 True로 덮어쓴다. 가드가 무력화됨.\n2) \

## 18. [High] '남' 한 글자를 원문에서 부분일치시켜 완료 제외를 켠다 — 이름·프로젝트명에 '남'이 들어가면 완료 티켓 조회가 0건이 된다

- 영역: 러너 의도 해석
- 위치: `runner/claude-work-assistant/assistant.py:2378`
- 재현: 담당자 '남기훈'의 완료 티켓 1건만 있는 상태에서 두 문장을 비교: '완료한 티켓만 보여줘' vs '남기훈이 완료한 티켓만 보여줘' (3.13.0 재현 확인)
- 기대: 두 문장 모두 완료 티켓 1건
- 실제: '완료한 티켓만 보여줘' → "전체 티켓 (완료): 총 1건" / '남기훈이 완료한 티켓만 보여줘' → "남기훈 담당 티켓 (완료): 총 0건". '강남 프로젝트 완료 티켓만 보여줘'도 0건.
- 원인 근거:
```
"exclude_completed": exclude_completed or due_filter is not None or "남" in message or default_active,
정규화(norm)도 형태소 경계도 없이 raw message에 대한 1글자 substring 검사다. '남은/남았'을 노리고 넣은 것으로 보이지만 '남기훈', '강남', '남양주', '남부', '남기다'에 모두 걸린다.
```
- 수정 방향: 1글자 원문 검사를 제거하고 의도 표현으로 좁힌다: `any(x in n for x in ['남은티켓','남은작업','남아있는','얼마나남','몇개남'])` — 해당 어휘는 이미 resolve_status_intent의 exclude_completed 토큰 목록에 있으므로 이 항은 지우고 status_intent 결과만 신뢰하는 편이 낫다. 어떤 경우에도 raw message에 대한 1~2글자 substring 매칭은 필터 근거로 쓰지 않는다.
- 검증자 판정: 반증 실패 — 결함 성립 (assistant.py:2378, APP_VERSION 3.14.0에서 여전히 존재).

[코드 확인] 라인 2378은 주장 그대로: `"exclude_completed": exclude_completed or due_filter is not None or "남" in message or default_active`. `message`는 raw 문자열이며 norm(n)이 아니다. 경계 없는 1글자 substring 검사가 맞다.

[반증 시도 — 방어 코드 4개 경로 모두 부재]
1. 상위 가드 없음: e

## 19. [High] '난이도 낮은/높은 티켓' 요청이 우선순위 필터로 둔갑하고, '우선순위 높은 순' 정렬 요청이 우선순위 필터로 둔갑해 데이터를 감춘다

- 영역: 러너 의도 해석
- 위치: `runner/claude-work-assistant/assistant.py:1164`
- 재현: 티켓 A(우선순위 높음/난이도 2), B(우선순위 낮음/난이도 6)에 대해 '난이도 높은 티켓 보여줘', '우선순위 높은 순으로 보여줘' (3.13.0 재현 확인)
- 기대: '난이도 높은 티켓 보여줘' → 난이도 6인 B. '우선순위 높은 순으로 보여줘' → A, B 전부를 우선순위 순으로 정렬
- 실제: '난이도 높은 티켓 보여줘' → priority='높음', difficulty_filter=None → "전체 티켓 (완료 제외, 우선순위 높음): 총 1건"으로 난이도 2짜리 A만 반환(정반대 데이터). '우선순위 높은 순으로 보여줘' → sort='PRIORITY' + priority='높음' → 3건 중 1건만 보여주고 나머지를 숨김.
- 원인 근거:
```
_DIFFICULTY_STRIP_RE(1138행)는 `난이도.{0,3}?(아주쉬움|매우쉬움|쉬움|보통|매우어려움|아주어려움|어려움|최상|중간|낮음|높음|[1-6])` 만 제거한다 — 관형형 '낮은/높은'이 목록에 없다. extract_priority(1164행)는 남은 문장에서 PRIORITY_ALIASES('낮은','높은','낮게','높게'…)를 무조건 부분일치시킨다. extract_difficulty_filter는 숫자([1-6])만 파싱하므로 난이도 조건은 사라진다.
```
- 수정 방향: (1) _DIFFICULTY_WORD_ALT/STRIP에 관형·비교형('낮은','높은','쉬운','어려운','높이','낮게')을 추가하고, extract_difficulty_filter가 '난이도 높은/낮은/어려운/쉬운'을 등급 조건(op=이상/이하)으로 파싱하게 한다. (2) extract_priority는 '우선순위' 앵커를 요구하도록 바꾼다(`우선순위.{0,4}?(낮|중간|보통|높|긴급)`) — 앵커 없는 전역 부분일치 금지. (3) 정렬 표현('~순','순으로','정렬')이 붙은 구간은 필터 추출 전에 제거해 정렬 요청이 필터가 되지 않게 한다.
- 검증자 판정: 반증 실패 — 결함이 실재하며 프로덕션에 배포되어 있다.

[시도한 반증 3가지, 전부 실패]
1) 스트립 정규식이 관형형을 처리할 가능성: _DIFFICULTY_STRIP_RE(1138행) 대안 목록은 `아주쉬움|매우쉬움|쉬움|보통|매우어려움|아주어려움|어려움|최상|중간|낮음|높음|[1-6]`뿐이고 '높은/낮은'이 없다. '높음' != '높은'이라 매칭 실패. 실행 확인: strip('난이도 높은 티켓 보여줘')가 원문 그대로 반환.
2) 상위 호출부 가드: 없음. 2220행이 priority = extract_priority(m

## 20. [High] resolve_status_intent가 상태 별칭('문제','계획','검토','대기')을 문장 어디서든 부분일치시켜, 일반 명사를 상태 필터로 둔갑시킨다

- 영역: 러너 의도 해석
- 위치: `runner/claude-work-assistant/assistant.py:788`
- 재현: '결제 문제 재현'(진행), '결제 로그 수집'(계획), '결제 재시도 로직'(진행) 3건이 있는 상태에서 '결제 문제 관련 티켓 보여줘' / '용인 프로젝트에 방화벽 정책 검토 업무 추가해줘' (3.13.0 재현 확인)
- 기대: '결제 문제 관련 티켓 보여줘' → 결제 관련 3건. 사용자는 진행상태를 말한 적이 없다.
- 실제: statuses=['이슈'] → "전체 티켓 (이슈): 총 0건". '…방화벽 정책 검토 업무 추가해줘'는 '검토'가 잡혀 "용인 (검증): 총 0건"을 반환한다. 존재하는 데이터가 통째로 숨겨진다.
- 원인 근거:
```
resolve_status_intent() 긍정 상태 스캔:
    for alias, actual in sorted(status_map.items(), key=lambda item: len(item[0]), reverse=True):
        if alias and alias in scan:
            selected.append(actual)
STATUS_ALIASES(62~70행)에 '이슈': ['이슈','문제'], '계획': ['계획','계획중','예정','대기'], '검증': ['검증','검토','테스트중']가 있어 '문제/계획/예정/대기/검토'라는 일상 명사가 상태 조건이 된다. 앵커도 조사 경계도 없다.
```
- 수정 방향: 상태 별칭은 조건 위치에서만 인정한다. `(?:상태|진행상태)(?:는|가|:)?\s*<alias>` 또는 `<alias>(?:인|된|중인|상태)?\s*(?:티켓|작업|것|거)`, `<alias>만` 같은 앵커된 패턴으로만 매칭하고, 앵커 없는 `alias in scan` 전역 스캔은 제거한다. 최소한 '문제','대기','예정','검토'처럼 일상 명사와 충돌하는 별칭은 앵커 필수로 분리한다.
- 검증자 판정: 반증 실패. 모든 반증 경로를 시도했으나 주장이 코드·로컬 실행·라이브 프로덕션 3중으로 확인됨.

【코드 확인】 C:\Users\hshwa\clovirone-web-assistant\runner\claude-work-assistant\assistant.py:786-789 (로컬 3.14.0)과 배포본 /opt/claude-work-assistant/assistant.py:786-789 (3.14.0) 모두 동일:
    for alias, actual in sorted(status_map.items(), ...):
        

## 21. [High] 댓글 내용에 '정리/요약/설명/왜' 같은 단어가 들어가면 is_freeform_query가 먼저 잡아, 댓글이 실제로 달리지 않고 대화 응답만 돌아온다

- 영역: 러너 의도 해석
- 위치: `runner/claude-work-assistant/assistant.py:3854`
- 재현: route_request({'message': "1번 티켓에 '요구사항 정리 필요'라고 댓글 남겨줘", ...}) vs "1번 티켓에 '내일 배포 예정'이라고 댓글 남겨줘" (3.13.0 재현 확인, claude_query는 스텁으로 대체)
- 기대: 두 요청 모두 action=WRITE_COMMENT + write_request로 댓글 write 발행
- 실제: '요구사항 정리 필요' → action=CONVERSATION, write_request 없음(댓글 미작성, 사용자에게 실패 사실도 안 알림). '내일 배포 예정' → action=WRITE_COMMENT 정상. 즉 댓글 본문 단어에 따라 쓰기가 조용히 사라진다.
- 원인 근거:
```
route_request 순서: `if is_freeform_query(message) or (...): return claude_query(...)` (3854행)가 `if is_comment_intent(message): return comment_ticket(...)` (3858행)보다 먼저 실행된다. FREEFORM_MARKERS(2053행 부근)에 '요약','정리','분석','추천','설명','왜','어떻게','비교','가장','정도'가 있고 is_freeform_query는 전체 문장에 대해 부분일치만 본다 — 따옴표 안의 댓글 본문도 검사 대상이다.
```
- 수정 방향: 라우팅 순서를 바꿔 명시적 쓰기 의도(is_comment_intent, is_update_intent)를 is_freeform_query보다 먼저 평가한다. 최소한 is_freeform_query 판정 전에 _COMMENT_TEXT_RES로 따옴표/'~라고' 인용 구간을 제거한 문자열로 검사해, 사용자가 '말한 내용'이 '요청 유형'을 결정하지 못하게 한다(comment_ticket이 이미 lookup 문자열에 쓰는 것과 같은 기법).
- 검증자 판정: 반증 실패 — 결함은 실제로 성립하며, 주장보다 범위가 넓다.

【반증 시도와 결과】
1. "신버전에서 수정됨?" → 아니오. 주장은 3.13.0 기준이나 로컬은 3.14.0이며 라우팅 순서 그대로: is_freeform_query(3877행)가 is_comment_intent(3881행)보다 먼저.
2. "상위 가드 존재?" → 아니오. 해당 분기의 유일한 예외는 _has_new_images/is_update_intent뿐. comment_ticket은 정작 _COMMENT_TEXT_RES(3087-3122)로 인용문을 제거하는데

## 22. [High] is_create_intent가 '티켓'이라는 단어를 하드코딩 요구해, '작업/업무/할일 만들어줘' 생성 요청이 티켓 목록 조회로 새어나간다

- 영역: 러너 의도 해석
- 위치: `runner/claude-work-assistant/assistant.py:3593`
- 재현: route_request로 '용인 프로젝트에 방화벽 정책 검토 업무 추가해줘', '용인 프로젝트에 IP 중복 방지 작업 하나 만들어줘' (3.13.0 재현 확인)
- 기대: 생성 초안 미리보기(CREATE_PREVIEW) 후 승인 요청
- 실제: is_create_intent=False → is_query_intent=True → action=TICKET_LIST ("용인 (검증): 총 0건" / "용인 (완료 제외): 총 1건"). 생성 요청이 조회 결과로 응답되고, 사용자는 왜 티켓이 안 만들어졌는지 알 수 없다.
- 원인 근거:
```
is_create_intent():
    if "티켓" not in n or not any(x in n for x in ["생성", "만들", "등록", "추가"]):
        return False
반면 is_query_intent(3646행 부근)의 query_markers에는 '작업','할일','업무','프로젝트'가 모두 들어 있어, '티켓'만 빠진 생성 문장은 전부 조회로 흡수된다. 도움말(help_text)도 '티켓 만들어줘' 형태만 예시로 제시한다.
```
- 수정 방향: 주어 어휘를 목록화해 공유한다: `SUBJECT_TOKENS = ['티켓','작업','업무','할일','일감','과제']`를 만들어 is_create_intent의 '티켓' 하드코딩을 `any(t in n for t in SUBJECT_TOKENS)`로 교체하고, 기존 create_verb_leads(마지막 동사 우선) 판정은 그대로 유지한다. is_query_intent와 동일한 상수를 공유해 두 함수가 같은 어휘를 보게 한다.
- 검증자 판정: 반증 실패 — 주장은 코드와 실행 결과 양쪽에서 성립한다. (검증 대상: C:\Users\hshwa\clovirone-web-assistant\runner\claude-work-assistant\assistant.py, APP_VERSION 3.14.0. 주장자가 본 3.13.0 이후에도 미수정.)

[근거 1 — 코드 인용 일치] assistant.py:3606 이 evidence와 정확히 일치:
    if "티켓" not in n or not any(x in n for x in ["생성","만들","등록","추가"]): ret

## 23. [High] is_update_intent의 동사 목록이 '해줘' 형태에만 맞춰져 있어 '마감일 내일로 미뤄줘/당겨줘/늦춰줘'가 조회로 처리된다

- 영역: 러너 의도 해석
- 위치: `runner/claude-work-assistant/assistant.py:3626`
- 재현: route_request로 '이 티켓 마감일 내일로 미뤄줘' (3.13.0 재현 확인). is_update_intent=False, is_query_intent=True.
- 기대: 해당 티켓의 마감일을 내일로 변경(미리보기/직접 변경)
- 실제: action=TICKET_LIST, "전체 티켓 (완료 제외, 내일): 총 0건" — 마감일을 미뤄달라는 쓰기 요청에 내일 마감 티켓 목록(0건)을 답한다. '다음주로 당겨줘', '금요일로 늦춰줘'도 동일.
- 원인 근거:
```
is_update_intent():
    if any(field in n for field in ["마감", "우선순위", "난이도", "담당자", "할당", "배정"]):
        if any(verb in n for verb in ["하자", "해줘", "설정해", "정하자", "바꾸자", "변경하자", "로할게", "추가해", "빼줘", "없애"]):
            return True
explicit_write_patterns도 `(?:으)?로(?:바꿔줘|바꾸자|변경해줘|…|해줘|할게|하겠습니다)`로 종결어미를 열거만 한다. '미뤄줘/당겨줘/늦춰줘/앞당겨줘'는 어디에도 없다. 반면 is_query_intent는 '마감'을 query_marker로 갖고 있어 곧바로 조회로 넘어간다.
```
- 수정 방향: 열거식 어미 매칭을 어간 매칭으로 바꾼다. 변경 동사 어간 집합에 '미루/미뤄','당기/당겨','늦추/늦춰','앞당','옮겨','조정','수정'을 추가하고, 필드명(마감/우선순위/난이도/담당자)이 명시된 문장에서 `<값>(으)?로\s*<변경동사>` 형태면 explicit_write로 인정한다. 장기적으로는 이 필드+동사 조합을 하나의 정규식 테이블(필드 앵커 × 변경동사 어간)로 통합해 어미마다 목록을 늘리는 구조를 없앤다.
- 검증자 판정: 반증 실패. 결함은 실재하며 프로덕션에 라이브 상태다.

[반증 시도와 실패 사유]
1. is_freeform_query LLM 구제 경로(3877행) — 주장자가 언급하지 않은 최유력 가드. route_request에서 is_update_intent(3883)보다 먼저 실행되어 claude_query(LLM)로 보낸다. 그러나 FREEFORM_MARKERS(요약/정리/분석/추천/왜/어떻게…)에 '미뤄줘/당겨줘/늦춰줘'가 하나도 매칭되지 않아 발동 안 함. 실행 확인: freeform=False.
2. answer_query 내부 

## 24. [High] operator 역할이 /api/admin/jobs로 전 사용자의 사적인 채팅 본문·이메일·이미지 원본 바이트를 조회 가능 (소유권 경계 우회)

- 영역: 보안
- 위치: `app/jobs/router.py:36`
- 재현: 1) tests/conftest.py 픽스처로 통합 테스트 작성:
   - `login_as("user", email="victim@goodmit.co.kr")`로 로그인 → POST /api/conversations → POST /api/conversations/{id}/messages 에 content="내 계정 비밀번호는 hunter2 입니다" + attachments=[{filename:"secret.png", media_type:"image/png", data:<1x1 PNG base64>}] 전송 (202 확인).
   - `login_as("operator", email="operator@goodmit.co.kr")`로 로그인 → GET /api/admin/jobs (X-CSRF-Token 헤더 포함).
2) `.venv/Scripts/python -m pytest <probe> -s -q` 실행.
3) 응답 JSON에 victim의 평문 content, 이메일, base64 이미지가 모두 포함됨을 확인.
실서버에서는 operator 세션 쿠키 + /api/me의 csrf_token으로 `curl -s https://clovirone-ai.gooddi.lab/api/admin/jobs` 만으로 동일 재현(관리자 UI는 payload를 렌더하지 않지만 RBAC는 서버 API가 경계이므로 무관).
- 기대: Job 큐 조회(spec §14.1 / docs/SECURITY.md:38 "Job 큐 | 읽기 operator+")는 큐 운영에 필요한 메타데이터(job_type, status, attempt_count, available_at, last_error 등)만 제공해야 한다. 타 사용자의 대화 원문·이미지 바이트는 어떤 관리 역할에도 기본 노출되지 않아야 하며, 노출이 불가피하면 최소한 mask_sensitive() 적용 + 감사 로그 기록 + system_admin 한정이어야 한다.
- 실제: operator(직원 계층 2단계, 감사 로그 열람 권한도 없는 역할)가 전 사용자의 채팅 평문, 요청자 이메일/이름, 첨부 이미지 base64 원본을 마스킹·감사 기록 없이 무제한 페이지네이션으로 조회한다. 사용자가 채팅에 붙여넣은 비밀번호·API 키 등도 그대로 노출된다.
- 원인 근거:
```
app/jobs/router.py:36 — `_job_view()`가 job payload를 마스킹 없이 그대로 반환한다:

    "payload": json.loads(job.payload_json),

chat_message job의 payload는 app/chat/service.py:182-195 `_build_job_payload()`가 만든 것으로 `content`(사용자 원문), `requester.email/name`, `attachments[].data`(base64 이미지 원본)를 포함한다. 라우터 전체 권한은 app/jobs/router.py:18-26의 `require_roles("operator","admin","system_admin")` 뿐이며 소유자 확인이 없다.

실제 관측 출력 (probe 테스트를 작성해 pytest로 실행, 확인 후 파일 삭제함):
=== OPERATOR VIEW OF /api/admin/jobs ===
{"items": [{"id": "9d3292fe-...", "job_type": "chat_message", "status": "queued", "payload": {"content": "내 계정 비밀번호
```
- 수정 방향: app/jobs/router.py의 `_job_view()`에서 원시 payload 반환을 제거하고 운영에 필요한 비민감 요약만 노출한다. 구체적으로:
1) `"payload": json.loads(job.payload_json)` 줄을 삭제하고, 대신 화이트리스트 기반 요약으로 대체 — 예: `"payload_summary": {"has_attachments": bool, "attachment_count": int, "content_length": int}` (본문·base64 제외).
2) 진단 목적으로 원문이 꼭 필요하면 별도 엔드포인트로 분리해 `require_roles("system_admin")` + `mask_sensitive()` 적용 + `record_audit_from_request(action="job.payload_view")`로 열람 자체를 감사에 남긴다.
3) retry/cancel 응답(:103, :121)도 동일 뷰를 쓰므로 함께 수정된다.
4) 회귀 방지: tests/security/ 에 "operator가 GET /api/admin/jobs 응답에서 타 사용자 content/attachments.data를 볼 수 없다"는 테스트를 핀으로 추가(기존 tests/security/test_secret_exposure_sweep.py 와 동일 계열).
- 검증자 판정: 반증 실패 — 주장은 성립한다. 코드 정독 + 자체 probe 테스트 재현으로 확인했다 (probe 파일은 확인 후 삭제, git status에 잔여 없음).

【시도한 반증과 그 결과 — 전부 실패】

1) "상위 호출부/미들웨어에 마스킹 가드가 있을 것" → 없음.
   `grep -rn "mask_sensitive" app/` 결과 사용처는 app/core/audit.py:52,57(감사 레코드 저장 시)과 app/health/service.py:206(설정 노출)뿐. 응답 직렬화 경로에 마스킹 미들웨어가 전혀 없다. app/

## 25. [High] n8n 업무 도우미 웹훅이 무인증 — requester 신원이 요청 본문에서 그대로 신뢰되어 로컬 프로세스가 임의 직원 사칭 가능

- 영역: 보안
- 위치: `ClovirONE_AI_Work_Assistant_v7.json:7`
- 재현: 1) 서버에 로컬 접근 확보(예: ssh cloviradmin@10.100.64.71).
2) Authorization 헤더 없이 웹훅 직접 호출:
   curl -s -X POST http://127.0.0.1:5678/webhook/clovirone-work-assistant -H "Content-Type: application/json" --data '{"requester":{"email":"<임의 직원>@goodmit.co.kr","name":"<임의 이름>"},"message":"내 티켓 몇 건이야?","conversation_id":"x1","message_id":"x1"}'
3) HTTP 200 + 해당 직원 기준의 티켓 응답 확인 (실제 관측: "내 직접 할당 티켓 완료 제외: 6건입니다.").
4) 대조: 러너 직접 호출은 토큰 없이는 401 — curl -s -X POST http://127.0.0.1:8789/v1/assistant/message -d '{}' → {"error":"unauthorized"}
- 기대: n8n 웹훅도 러너(:8789)와 동일하게 공유 비밀을 강제해야 한다 — 즉 웹 플랫폼만이 유효한 호출자임을 증명할 수 있어야 하고, requester 신원은 인증된 호출자에게서만 수용되어야 한다. 네트워크 격리는 다층 방어의 한 겹이지 신원 경계의 유일한 근거가 되어선 안 된다(CLAUDE.md §1의 "위조 불가" 보장이 전 구간에서 성립해야 함).
- 실제: 웹훅이 authentication: None으로 열려 있어, 127.0.0.1:5678에 도달 가능한 어떤 프로세스든 인증 없이 본문의 requester.email만 바꿔 임의 직원을 사칭할 수 있다. 읽기(타인 티켓 조회)는 프로브로 실증했고, 동일 경로로 쓰기 문장을 보내면 타인 명의의 Notion 생성/변경도 가능하다. 사칭 호출은 웹 플랫폼의 감사 로그에도 남지 않는다(플랫폼을 우회하므로).
- 원인 근거:
```
워크플로 JSON의 웹훅 노드(path="clovirone-work-assistant", 파일 7번째 줄)를 파싱한 결과 인증이 설정되어 있지 않다:

--- 업무 도우미 Webhook | n8n-nodes-base.webhook
  authentication: None
  path: clovirone-work-assistant
  credentials: []

라이브 확인 (Authorization 헤더 없이 read-only 프로브 1회):
$ curl -s -w "HTTP=%{http_code}" -X POST http://127.0.0.1:5678/webhook/clovirone-work-assistant \
    -H "Content-Type: application/json" \
    --data '{"requester":{"email":"hshwang@goodmit.co.kr","name":"황형섭"},"message":"내 티켓 몇 건이야?",...}'
HTTP=200
응답: {"action":"TICKET_COUNT","response_text":"내 직접 할당 티켓 완료 제외: 6건입니다.", ...}

→ 인증 없이 200이 반환되고, 
```
- 수정 방향: n8n 웹훅에 Header Auth를 설정하고 플랫폼이 그 토큰을 주입하도록 한다:
1) n8n 웹훅 노드: authentication=headerAuth, 자격증명에 전용 헤더(예: X-Platform-Token) + 강한 랜덤 값 설정.
2) 토큰 값을 SECRETS_DIR(/etc/clovirone-web-assistant/secrets/<name>, 0640 root:clovirone-web)에 파일로 배치 — CLAUDE.md §2-3에 따라 DB엔 secret_ref 이름만.
3) app/jobs/handlers/chat_message.py:117-122 호출을 `auth_type=AUTH_API_KEY_HEADER, secret_ref="n8n_webhook_token"`으로 변경 (app/core/http_client.py:63-67이 이미 X-API-Key 주입을 지원하므로, 헤더명을 맞추거나 AUTH_API_KEY_HEADER의 헤더명을 설정 가능하게 확장).
4) 러너와의 정책 일치를 회귀 테스트로 핀: 토큰 없는 웹훅 호출이 거부되는지 확인.
주의: 이 변경은 워크플로(id=reuSafmsRzO1tIzX) 수정을 수반하므로 사용자가 직접 적용해야 한다(본 검수는 조사만 수행).
- 검증자 판정: 반증 시도 4건 모두 실패. 주장 성립.

■ 반증 시도 1: "루프백 격리로 무의미하다" → 실패
✅ 확인함: `ss -tlnp` 결과 5678/8789 모두 127.0.0.1 바인딩, nginx에 5678 프록시 설정 없음(grep -rl 결과 없음). 원격 도달은 불가가 맞다. 그러나 격리는 '원격' 공격자만 막는다. 실증된 공격 주체(uid=1000)는 이미 경계 안에 있다. 게다가 같은 제품이 같은 루프백 위 다른 포트에서는 토큰을 강제한다 — 팀 스스로 루프백만으로는 불충분하다고 판단한 것이다.

■ 반증 시도 2(핵심)

## 26. [Medium] 'Notion 매핑' 섹션이 구조적으로 항상 비어 있음 — 5개 행 액션 전부 도달 불가, 문서에 적힌 절차가 실행 불가

- 영역: 관리자 운영
- 위치: `app/notion_mapping/router.py:46`
- 재현: tests/integration/에 아래를 넣고 pytest -s:
1) csrf = login_as("system_admin")
2) POST /api/admin/users {"email":"bob@goodmit.co.kr","display_name":"밥","role":"user"} → 201
3) GET /api/admin/notion-mapping  (콘솔 'Notion 매핑' 섹션이 로드하는 바로 그 엔드포인트) → 200 {"items": []}
콘솔 UI: /admin#notion-mapping → '표시할 항목이 없습니다.' 만 표시, 추가 버튼 없음, 새로고침해도 동일.
- 기대: docs/NOTION_MAPPING.md:86과 ADMIN_GUIDE.md:36("사용자별 매핑 상태(unmapped/verified/conflict), 재검증·해제 버튼")대로, 신규 사용자를 만들면 매핑 섹션에 unmapped 상태로 나타나고 '재검증'/'수동매핑'을 누를 수 있어야 한다.
- 실제: list_mappings가 UserNotionMapping 테이블 행만 반환하는데, 그 행을 만드는 유일한 경로가 user_id를 이미 아는 GET/POST 엔드포인트들이다. 콘솔에는 매핑 행을 생성할 진입점(추가 버튼·사용자 선택 UI)이 없고, 사용자 섹션에도 매핑 관련 액션이 없다. 즉 신규 설치·신규 사용자 기준 이 섹션은 영구히 빈 화면이며 5개 행 액션이 전부 죽어 있다. app/users/router.py:351의 POST /api/admin/users/{user_id}/notion-mapping/verify 는 구현돼 있으나 sections.js 어디에도 연결돼 있지 않다(이름만 있고 동작 경로 없음).
- 원인 근거:
```
app/notion_mapping/router.py:42-48
  @router.get("", ...)
  def list_mappings(db):
      rows = db.execute(select(UserNotionMapping)).scalars().all()   ← 매핑 '행이 이미 있는' 사용자만 반환
      ...
app/users/service.py:83-96 create_user() — UserNotionMapping 행을 만들지 않음
grep 결과: get_or_create_mapping 호출처는 notion_mapping/router.py:54(GET /{user_id})와 service.py의 verify/map/unmap/resolve뿐 — 모두 user_id를 이미 알아야 호출 가능
app/static/js/admin/sections.js:122-144 notion-mapping 섹션: createForm 없음, customActions 없음. rowActions 5종(재검증/수동매핑/충돌해결/상세/해제)은 전부 row.user_id에 의존
docs/NOTION_MAPPING.md:86 "3. 신규 사용자 생성 후 Notion 매
```
- 수정 방향: 둘 중 하나로 정렬: (A) list_mappings를 User LEFT JOIN UserNotionMapping으로 바꿔 매핑 행이 없는 사용자도 status='unmapped'로 항상 노출(권장 — 문서 서술과 일치), 또는 (B) sections.js users 섹션에 rowAction { label: "Notion 매핑", api: POST /api/admin/users/{id}/notion-mapping/verify } 를 추가해 이미 존재하는 엔드포인트로 행을 부트스트랩. 어느 쪽이든 tests/integration/test_notion_mapping.py에 '사용자 생성 직후 매핑 목록에 나타난다' 테스트 추가.
- 검증자 판정: 반증 실패 — 핵심 구조 주장은 성립한다. 다만 severity 근거와 '실행 불가' 프레이밍은 반증됐다.

[확인함] 직접 재현: tests/integration에 임시 테스트를 넣고 .venv/Scripts/python -m pytest -s 실행 → 증거: `CREATE USER: 201 55dff51c-...` / `NOTION-MAPPING LIST: 200 {'items': []}` / `USERS LIST notion status: [('bob@goodmit.co.kr','unmapped'),('admin@goodmit

## 27. [Medium] Integration/Runner/Workflow 설정 버전 이력·롤백이 API와 문서에는 있으나 관리자 콘솔에 UI가 전혀 없음

- 영역: 관리자 운영
- 위치: `app/static/js/admin/sections.js:155`
- 재현: 1) admin/system_admin으로 /admin#integrations (또는 #runners, #workflows) 접속
2) 아무 행의 '버전' 컬럼에 2 이상이 표시되는 것을 확인(수정 이력 있음)
3) 그 행의 작업 버튼을 모두 확인 → 이력 조회/롤백 버튼이 없음
4) 비교: /admin#settings 의 임의 키 → '이력' 버튼 → '이 버전으로 롤백' 존재. /admin#prompts → '롤백' 존재.
- 기대: ADMIN_GUIDE.md:43·47과 RUNNER_MANAGEMENT.md:12대로, Integration/Runner/Workflow 행에서 버전 이력을 조회하고 특정 버전으로 롤백할 수 있어야 한다. 잘못된 base_url/secret_ref로 연동이 끊겼을 때 콘솔에서 되돌리는 것이 핵심 운영 경로다.
- 실제: 세 섹션 모두 config_version 숫자만 보여주고 이력·롤백 버튼이 없다. 잘못 저장한 설정을 콘솔에서 되돌릴 방법이 없어, 관리자는 이전 값을 기억해 '수정' 폼에 손으로 다시 입력해야 한다(그마저도 base_url/secret_ref 변경이면 승인 게이트를 다시 태움). 승인 게이트·감사 기록까지 갖춘 rollback 엔드포인트가 콘솔에서 도달 불가능한 채로 방치돼 있다.
- 원인 근거:
```
구현된 엔드포인트(전부 살아 있음):
  app/integrations/router.py:160 GET /{id}/versions, :184 POST /{id}/rollback
  app/runners/router.py:221 GET /{id}/versions, :242 POST /{id}/rollback
  app/workflows/router.py:123 GET /{id}/versions, :144 POST /{id}/rollback
콘솔 정의:
  sections.js:155-161 integrations rowActions = [상세, 수정, 헬스체크, 활성, 비활성]  ← versions/rollback 없음
  sections.js:200-208 runners rowActions = [상세, 수정, 헬스, 테스트, 활성, 비활성, 복제]  ← 없음
  sections.js:248-254 workflows rowActions = [상세, 수정, 테스트, 활성, 비활성]  ← 없음
  sections.js:153/198/246 세 섹션 모두 col("config_version","버전") 컬럼만 표시
대조군(같은 콘솔 안에 롤백 UI가 이미 존재):

```
- 수정 방향: sections.js의 세 섹션에 대칭 액션 추가: { label: "버전", kind: "sublist", path: r => `/api/admin/<kind>/${r.id}/versions`, itemsKey: "items", columns: [version, created_at, created_by], rowAction: { label: "롤백", roles: WRITE, confirm: "...", api: v => ({method:"POST", path:`/api/admin/<kind>/${r.id}/rollback`, body:{version:v.version}}) } }. 이미 있는 sublist+rowAction 엔진(app.js:293-336)과 schedules '실행이력' 패턴을 그대로 재사용하면 된다. 롤백 응답의 status==='approval_pending' 처리는 app.js:311-314에 이미 없으므로 openActionForm(app.js:280-289) 방식으로 태우거나 sublist rowAction에도 approval_pending 토스트를 추가.
- 검증자 판정: 반증 실패 — 주장 성립. 네 가지 반증 경로를 모두 시도했으나 전부 막혔다.

[✅ 확인함] 엔드포인트 실재: integrations/router.py:161·185, runners/router.py:221·242, workflows/router.py:123·144 모두 /api/admin 프리픽스로 마운트됨(각 router.py:30/29/27). require_roles + 감사기록 + (integrations:198-220, runners:254-280) 승인 게이트까지 완비.

[✅ 확인함] 반증1(레지스트리에 숨은 액션?

## 28. [Medium] 사용자 '비번재발급' 버튼에 확인 절차가 없어 오클릭 한 번으로 타인 계정 비밀번호가 즉시 무효화됨

- 영역: 관리자 운영
- 위치: `app/static/js/admin/sections.js:115`
- 재현: 1) admin으로 /admin#users 접속
2) 목록에서 임의 사용자 행의 '비번재발급' 클릭 (인접 버튼: 상세/수정/세션/비활성/비번재발급/잠금해제/세션폐기 — 좁은 화면에서 밀집)
3) 확인 모달 없이 즉시 POST 발생 → 임시 비밀번호 모달이 뜨는 순간 그 사용자의 기존 비밀번호는 이미 폐기되고 활성 세션 전부 revoke됨
4) 되돌릴 방법 없음(이전 해시 복구 불가). 해당 사용자는 즉시 로그아웃되고 재로그인 시 비밀번호 변경을 강제당함.
- 기대: 비밀번호 재발급은 되돌릴 수 없고 대상 사용자를 즉시 로그아웃시키는 파괴적 작업이므로, 최소한 '세션폐기'와 동일한 수준의 confirm 모달(대상 이메일과 영향 범위 명시)이 있어야 한다. 판정 기준상 위험 작업에는 설명·영향범위·확인이 필요하다.
- 실제: 확인 없이 단일 클릭으로 실행된다. 같은 행의 더 가벼운 작업인 '세션폐기'에는 confirm이 있고 '비번재발급'에는 없어 위험도와 확인 강도가 역전돼 있다. 감사 기록(users/router.py:292-294 user.reset_password)은 남지만 사후 기록일 뿐 오클릭을 막지 못한다.
- 원인 근거:
```
sections.js:115
  { label: "비번재발급", api: function (row) { return { method: "POST", path: "/api/admin/users/" + row.id + "/reset-password" }; }, toastKey: "temp_password" },
  ← confirm 속성 없음, roles 속성 없음
같은 배열의 대조군 sections.js:117
  { label: "세션폐기", ..., confirm: "이 사용자의 모든 세션을 폐기할까요?" }   ← 더 약한 작업인데 확인 있음
app.js:190-191  if (action.confirm) A.confirmModal(...); else run();   ← confirm 없으면 클릭 즉시 POST
서버측 부작용 app/users/service.py:222-251 admin_reset_password():
  user.password_hash = hash_password(password); user.must_change_password = True;
  user.failed_login_count = 0; user.locked_until = N
```
- 수정 방향: sections.js:115에 confirm 추가: confirm: "이 사용자의 비밀번호를 임시 비밀번호로 재발급합니다. 현재 비밀번호는 즉시 무효화되고 로그인 중인 모든 세션이 끊깁니다. 계속할까요?" — 다만 confirmModal 경로(app.js:190)는 toastKey/secretModal 분기(app.js:180-181)를 그대로 태우므로 확인 후 임시 비밀번호 모달이 정상 표시되는지 함께 확인할 것. 동일 기준으로 '비활성'(sections.js:113)에도 confirm 추가 검토(세션 폐기 + 소유 스케줄 자동 비활성이라는 부작용이 users/service.py:196-199에 있음).
- 검증자 판정: 반증 실패 — 주장 성립. 5개 반증 경로를 모두 시도했고 전부 막혔다.

1) confirm 부재 (시각적 독해가 아닌 실행으로 검증). sections.js를 node로 실제 로드해 users 섹션의 rowActions를 프로그램적으로 덤프:
   비번재발급 → api=Y, confirm=*** NONE ***
   세션폐기   → api=Y, confirm="이 사용자의 모든 세션을 폐기할까요?"
   비활성/활성화/잠금해제 → confirm NONE
   즉 주장대로 confirm 키가 객체에 존재하지 않는다. 그리고 비번재

## 29. [Medium] 감사 로그 '행위자'와 승인 '요청자'가 사람 이름/이메일 대신 UUID로 표시 — 같은 콘솔의 Notion 매핑 섹션은 이메일로 해석하는데 불일치

- 영역: 관리자 운영
- 위치: `app/static/js/admin/sections.js:497`
- 재현: 1) admin으로 /admin#audit 접속 → '행위자' 컬럼이 2b74ed6b-9f80-47df-9901-2579ffe6d16b 형태의 UUID로만 표시됨. 필터도 action/object_type 텍스트뿐이라 '누가' 기준으로 좁힐 수 없음(sections.js:491-494).
2) /admin#approvals 접속 → pending 행의 '요청자'가 UUID. 이 화면에서 승인/거절을 결정해야 하는데 요청자가 누구인지 알 수 없음.
3) '상세' 모달을 열어도 approval_view(approvals/service.py:48-60)가 UUID만 담고 있어 동일.
4) 대조: /admin#notion-mapping 은 같은 사용자를 alice@goodmit.co.kr 로 표시.
- 기대: 감사·승인은 책임 추적이 목적이므로 행위자/요청자가 이메일 또는 이름으로 표시되어야 한다. Notion 매핑 섹션이 이미 하는 user_id→User 조인 방식을 audit/approvals에도 동일하게 적용해야 한다(중복 구현·화면별 정책 불일치 제거).
- 실제: 콘솔의 두 핵심 책임추적 화면이 사람을 UUID로만 보여준다. 승인자는 자기 요청인지조차 화면에서 판별할 수 없어(자기승인 금지 규칙이 approvals/service.py에 서버측으로 있긴 하나) 결재 판단에 필요한 정보가 화면에 없다. 감사 로그는 '누가' 기준 필터도 없어 사고 조사 시 DB를 직접 조회해야 한다.
- 원인 근거:
```
sections.js:497  col("object_id","대상ID"), col("result","결과",{badge:true}), col("user_id","행위자"),
  → app/audit/router.py:70 "user_id": row.user_id (UUID 원본, 사용자 조인 없음)
sections.js:446  col("requested_by","요청자"), col("requested_at","요청 시각"),
  → app/approvals/service.py:51 "requested_by": row.requested_by (UUID), :52 "approver_id": row.approver_id (UUID)
대조군 — 같은 콘솔 안에서 이미 사람으로 해석하는 구현이 존재:
  sections.js:126  col("user_email", "사용자")
  app/notion_mapping/router.py:46-48  users = {u.id: u for u in db.execute(select(User)).scalars().all()}
  app/notion_mapping/service.py:72-73  "user_email": user
```
- 수정 방향: app/audit/router.py:66-82의 응답 조립부에 notion_mapping/router.py:46-48과 같은 users 딕셔너리 조인을 추가해 user_email/user_display_name 필드를 내려주고, sections.js:497의 col("user_id","행위자")를 col("user_email","행위자")로 교체. app/approvals/service.py approval_view()에도 requested_by_email/approver_email을 추가하고 sections.js:446을 교체. 감사 섹션 filters에 사용자 검색 필드 추가(audit/router.py:38에 user_id 쿼리 파라미터는 이미 존재하므로 이메일→id 해석만 붙이면 됨).
- 검증자 판정: 반증 실패 — 주장은 5개 축 모두에서 성립한다. 코드 리딩과 실제 실행(TestClient+마이그레이션 DB) 양쪽으로 확인했다.

[반증 시도 1] 프론트가 UUID를 클라이언트에서 해석하는가? → 실패. sections.js:9 col()은 {key,label} 순수 매퍼이고, app.js:84-88 fmtCell()은 String(value)에 null→"—" 분기뿐이다. sections.js/common.js/app.js 전체 grep에서 userMap/resolveUser/users[] 류 코드 0건. UUID가 그대로 

## 30. [Medium] 채팅 폴링이 non-OK HTTP 응답을 조용히 삼킴 — 전송 버튼이 영구 비활성 상태로 고착

- 영역: 화면
- 위치: `app/static/js/chat.js:552`
- 재현: 1) 메시지를 전송한다(setSending(true) → sendBtn.disabled = true).
2) 폴링 중 GET /api/conversations/{id}/messages 가 500 또는 503을 반환하게 한다(워커/DB 장애, 유지보수 모드 등).
3) 화면을 관찰한다.
- 기대: 오류 상태를 사용자에게 알리고(statusEl에 '연결 끊김' 등), 복구 가능한 다음 행동(새로고침/재시도)을 제시하거나 최소한 입력·전송을 다시 가능하게 한다.
- 실제: connection-status는 빈 문자열 그대로라 아무 오류도 표시되지 않는다. setSending(false)가 호출되지 않아 sending 플래그가 true로 남고 sendBtn.disabled가 계속 true다. 5초 간격으로 무한 폴링만 반복한다. sendMessage()는 첫 줄 `if (sending) { return; }`(chat.js:583)로 Enter 입력도 조용히 무시한다. 페이지 새로고침 외에는 복구 경로가 없다.
- 원인 근거:
```
pollOnce():
  if (response.ok) { ... setSending(false); return; }
} catch (e) {
  statusEl.textContent = "연결 끊김 — 재시도 중";
}
pollDelay = Math.min(pollDelay * 2, 5000);
pollTimer = setTimeout(pollOnce, pollDelay);

response.ok === false(500/503 등)이면 ok 분기도 catch 분기도 타지 않고 맨 아래 재시도 라인으로 직행한다. fetch는 5xx에 대해 reject하지 않으므로 catch는 절대 실행되지 않는다.
```
- 수정 방향: if (response.ok) 블록에 else 분기를 추가해 non-OK를 명시적으로 처리한다: statusEl에 오류 문구를 세팅하고 statusEl.classList.add('error')를 적용한 뒤 setSending(false)를 호출해 입력을 복구시킨다. 연속 실패 횟수가 임계치를 넘으면 폴링을 중단하고 '다시 불러오기' 버튼을 노출해 사용자가 다음 행동을 알 수 있게 한다.
- 검증자 판정: 반증 시도했으나 핵심 메커니즘은 살아남음. 다만 주장의 과장 2건을 확인해 severity를 high→medium으로 하향.

■ 반증 시도 및 결과

1) 상위 가드 존재 여부 → 반증 실패. api()(chat.js:41-61)는 401(=/login 리다이렉트+throw)과 403 password_change만 throw하고, 500/503/404/일반 403은 response를 그대로 반환한다. pollOnce의 non-OK를 걸러줄 상위 가드 없음.

2) 다른 복구 경로(워치독/visibilitychange/online 

## 31. [Medium] '다시 시도' 버튼이 실패해도 아무 피드백이 없음 (무반응 버튼)

- 영역: 화면
- 위치: `app/static/js/chat.js:637`
- 재현: 1) 메시지 처리를 실패시켜 processing_status='failed' 상태로 만든다(chat.js:254에서 '실패' + '다시 시도' 버튼 렌더).
2) '다시 시도'를 클릭하되 재시도 요청이 403/409/500을 반환하는 상황(권한 없음, 이미 재시도됨, 유지보수 모드)을 만든다.
- 기대: 재시도가 거부되면 그 사실과 이유를 사용자에게 표시한다(errorEl 또는 메시지 메타 영역).
- 실제: 버튼을 눌러도 DOM이 전혀 바뀌지 않는다. 오류 문구도 없고, '처리 중…'으로 바뀌지도 않으며, 실패 상태 그대로 남는다. 사용자는 클릭이 먹은 것인지 알 수 없어 반복 클릭하게 된다. 네트워크 예외 시에도 catch가 비어 있어 동일하게 무반응이다.
- 원인 근거:
```
async function retryMessage(messageDbId) {
  try {
    var response = await api("/api/messages/" + encodeURIComponent(messageDbId) + "/retry", {
      method: "POST", body: JSON.stringify({}),
    });
    if (response.ok) {
      setSending(true);
      pollOnce();
    }
  } catch (e) { /* 다음 폴링에서 상태 반영 */ }
}

response.ok가 false인 경우를 처리하는 else가 없고, catch는 주석만 있고 비어 있다.
```
- 수정 방향: if (response.ok) 에 else를 추가해 응답 본문의 error.message를 errorEl.textContent에 표시하고, catch에서도 '서버에 연결할 수 없습니다' 수준의 문구를 표시한다. 클릭 즉시 버튼을 disabled 처리해 중복 클릭을 막고, 성공/실패가 판명되면 해제한다.
- 검증자 판정: 반증 4회 시도, 모두 실패 → 결함 성립.

1) "api()가 중앙에서 오류 처리한다"? 실패. chat.js:41-61은 401(로그인 리다이렉트)과 403 중 error.code=="password_change_required"인 경우만 가로챈다. 그 외 상태코드는 ok=false인 response를 그대로 호출부에 반환하며 throw하지 않는다. 즉 retryMessage의 if(response.ok)는 조용히 false가 되고 else가 없어 아무 일도 안 일어난다.

2) "non-2xx가 실제로 발생하지 않는다"? 실

## 32. [Medium] 대화 목록 로드 실패가 '대화 없음'과 구분되지 않음 + 빈 상태 안내 부재

- 영역: 화면
- 위치: `app/static/js/chat.js:432`
- 재현: 1) GET /api/conversations 가 500을 반환하는 상태에서 채팅 화면에 접속한다.
2) 사이드바와 본문을 관찰한다.
- 기대: 목록을 불러오지 못했다는 오류와 재시도 수단을 표시한다. 대화가 실제로 0건일 때는 '아직 대화가 없습니다' 같은 빈 상태 안내를 표시한다.
- 실제: 오류가 빈 배열로 치환되어 사이드바가 완전히 빈 채로 렌더되고, boot()는 이를 '대화 0건'으로 오인해 퀵 프롬프트만 띄운다. 서버 장애와 신규 사용자의 정상 화면이 픽셀 단위로 동일하다. 기존 대화가 있는 사용자는 자신의 대화가 사라진 것으로 오인한다. 또한 대화가 진짜 0건일 때도 사이드바는 아무 문구 없이 비어 있어 빈 상태 처리가 없다.
- 원인 근거:
```
async function loadConversations() {
  var response = await api("/api/conversations");
  if (!response.ok) { return []; }   // 오류를 빈 배열로 치환
  var data = await response.json();
  listEl.textContent = "";
  data.items.forEach(...);
  return data.items;
}

boot() (chat.js:741-749):
  var conversations = await loadConversations();
  var restore = conversations.find(...) || conversations[0];
  if (restore) { await openConversation(...); }
  else { quickPromptsEl.style.display = "flex"; }
```
- 수정 방향: loadConversations가 실패를 삼키지 말고 throw 하거나 상태 객체를 반환하게 바꾼다. boot()에서 오류 시 사이드바에 오류 문구 + '다시 시도' 버튼을 렌더하고, items.length === 0 일 때는 '아직 대화가 없습니다. + 새 대화로 시작하세요' 빈 상태를 렌더한다. admin 콘솔이 이미 갖고 있는 showError/showEmpty(app.js:76-82) 패턴을 채팅에도 동일하게 적용한다.
- 검증자 판정: 반증 실패 — 주장이 성립한다. 5가지 반증 시도를 모두 수행했고 전부 무너졌다.

[반증 시도 1: api() 상위 가드] app/static/js/chat.js:41-61. api()는 401이면 /login 리다이렉트 후 throw, 403+password_change_required면 /change-password 리다이렉트 후 throw 한다. 그러나 그 외 모든 상태(500/502/503)는 `return response`로 통과하고 response.ok===false가 된다. → loadConversations(432-

## 33. [Medium] 관리자 모달 폼의 label이 input과 연결되어 있지 않음 (스크린리더가 레이블을 읽지 못함)

- 영역: 화면
- 위치: `app/static/js/admin/common.js:128`
- 재현: 1) /admin → 사용자 → '+ 사용자 추가' 클릭.
2) 스크린리더(NVDA/VoiceOver)로 폼 필드를 순회하거나, 개발자 도구 접근성 트리에서 각 input의 accessible name을 확인한다.
3) 또는 '이름' 텍스트를 클릭해 해당 입력창에 포커스가 가는지 확인한다.
- 기대: 각 input의 accessible name이 '회사 이메일', '이름', '역할' 등으로 노출되고, 레이블 텍스트 클릭 시 해당 입력으로 포커스가 이동한다.
- 실제: 모든 input의 accessible name이 비어 있어 스크린리더는 '편집 텍스트'로만 읽는다. 어떤 값을 넣어야 하는지 알 수 없다. 레이블 클릭도 동작하지 않으며, checkbox 필드(예: '첫 로그인 때 비밀번호를 바꾸도록 요구', sections.js:83)는 클릭 타겟이 체크박스 자체로만 좁아진다. formModal을 쓰는 16개 섹션의 생성/수정/액션 폼 전부에 해당한다.
- 원인 근거:
```
const children = [el("label", { text: f.label }), input];
if (f.help) children.push(el("div", { class: "kpi-sub", text: f.help }));
return el("div", { class: "field" }, children);

label에 for 속성이 없고, input에 id가 없으며, label이 input을 감싸지도 않는다. el() 헬퍼는 opts.attrs를 지원하지만(common.js:18) 여기서는 사용하지 않는다. 대조적으로 login.html:54 / change_password.html:15 는 <label for="email"> 로 올바르게 연결되어 있다.
```
- 수정 방향: formModal 내부에서 필드마다 고유 id를 생성해(예: 'f-' + f.name + '-' + counter) input.id 에 부여하고 label을 el('label', { text: f.label, attrs: { for: id } }) 로 만든다. f.help가 있으면 help div에도 id를 부여하고 input에 aria-describedby로 연결한다. required 필드에는 input.required 와 aria-required도 함께 설정한다.
- 검증자 판정: 반증 실패 — 결함이 실재함. 시도한 반증 경로와 결과:

(1) "호출부가 attrs/aria-label을 넘긴다" → 반증 실패. formModal(common.js:109-131)은 f.type/f.value만 읽고 f.attrs를 전혀 참조하지 않음. app/static/js/admin/ 전체에서 aria-label|htmlFor|labelledby|.id= 검색 결과 0건. 프런트 전체 통틀어 aria-label은 login.js:16 하나뿐.

(2) "placeholder가 accessible name 폴백을 준다" →

## 34. [Medium] 관리자 모달에 Escape 닫기·포커스 이동·포커스 트랩이 없어 키보드 사용자가 갇힘

- 영역: 화면
- 위치: `app/static/js/admin/common.js:174`
- 재현: 1) /admin → 사용자 → '+ 사용자 추가' 클릭(마우스로 연다).
2) 키보드만 사용해 Escape를 눌러 닫기를 시도한다.
3) Tab을 반복해 포커스 위치를 추적한다.
- 기대: Escape로 모달이 닫히고, 열릴 때 포커스가 모달 내부(첫 필드 또는 제목)로 이동하며, Tab 포커스가 모달 내부를 순환하고, 닫으면 포커스가 트리거 버튼으로 복귀한다.
- 실제: Escape가 아무 동작도 하지 않는다. 모달을 열어도 포커스는 뒤쪽 트리거 버튼에 남아 있어, 스크린리더 사용자는 모달이 열린 사실조차 통지받지 못한다. Tab은 모달을 지나 뒤쪽 테이블/네비게이션으로 빠져나가며 보이지 않는(가려진) 요소를 순회한다. confirmModal(common.js:178)로 뜨는 '세션폐기', '유지보수 시작' 같은 파괴적 확인 대화상자도 동일해, 키보드 사용자는 취소 버튼을 Tab으로 찾아 헤매야 한다. 참고로 채팅 화면은 Escape로 사이드바를 닫는 처리가 있어(chat.js:726) 두 화면의 키보드 정책이 서로 다르다.
- 원인 근거:
```
formModal():
  const backdrop = el("div", { class: "modal-backdrop" }, [modal]);
  backdrop.addEventListener("click", function (e) { if (e.target === backdrop) closeModal(); });
  root.appendChild(backdrop);

닫기 수단이 backdrop 마우스 클릭과 '취소' 버튼뿐이다. grep 결과 static/js/admin/ 전체에서 keydown 리스너는 app.js:238(툴바 필터 input의 Enter)이 유일하며 Escape 핸들러는 존재하지 않는다. 모달을 열 때 포커스를 옮기는 코드도 없다(secretModal:224의 field.focus()만 예외). 배경 콘텐츠에 aria-hidden이나 inert도 적용되지 않고 role="dialog"/aria-modal도 없다.
```
- 수정 방향: 모달 생성 지점을 공통 헬퍼로 묶고: (1) document 레벨 keydown에서 Escape 시 closeModal() 호출(모달이 열려 있을 때만, secretModal은 명시적 확인이 필요하므로 예외 유지), (2) 모달에 role="dialog" aria-modal="true" 와 제목 aria-labelledby 부여, (3) 열 때 첫 포커서블 요소로 focus() 이동, (4) Tab/Shift+Tab을 모달 내부로 순환시키는 포커스 트랩, (5) 닫을 때 이전 포커스 복원(열기 전 document.activeElement 저장)을 적용한다.
- 검증자 판정: 반증 실패 — 주장의 사실관계가 모두 검증됨.\n\n[시도 1] 다른 곳의 전역 Escape 핸들러? 없음. app/static/js/ 전체 grep 결과 keydown 리스너는 admin/app.js:238(툴바 필터 Enter), chat.js:482/659/726뿐. admin/common.js에는 keydown 리스너 0개.\n\n[시도 2] 템플릿/셸이 주입? 없음. base_admin.html은 common.js/sections.js/app.js만 로드하고 base.html은 스크립트 무로드. #modal-root(39행

## 35. [Medium] 관리자 테이블 정렬이 현재 페이지 20건만 정렬하면서 전체를 정렬한 것처럼 보임

- 영역: 화면
- 위치: `app/static/js/admin/app.js:98`
- 재현: 1) /admin → 감사 로그(또는 사용자) 로 이동해 전체 건수가 page_size(20)보다 크게 만든다.
2) 페이저에 '1–20 / 137건' 이 표시된 상태에서 '시각' 컬럼 헤더를 클릭해 정렬한다.
3) '다음 ›' 으로 2페이지로 이동한다.
- 기대: 정렬은 전체 데이터셋 기준으로 적용되어, 2페이지에는 1페이지 마지막 값에 이어지는 값이 나온다. 또는 정렬이 페이지 내부로만 한정됨을 UI가 명시한다.
- 실제: 1페이지의 20건만 재배열된다. '137건' 이라는 전체 건수 표시 때문에 사용자는 137건 전체가 정렬된 것으로 믿지만, 실제로는 서버가 준 임의의 20건 안에서만 순서가 바뀐다. 2페이지로 넘어가면 정렬 상태가 초기화(loadSection이 renderTable을 새로 호출, sortState는 유지되나 다시 그 페이지 20건만 정렬)되어 페이지 간 순서가 뒤죽박죽이 된다. '가장 오래된 감사 로그' 같은 판단을 이 정렬로 내리면 틀린 결론에 도달한다. 비교자 자체도 null/undefined에 대해 va > vb 가 항상 false라 -1을 반환해 순서가 불안정하며, c.map으로만 만들어지는 컬럼은 row[c.key]가 undefined라 정렬이 무의미하다.
- 원인 근거:
```
renderTable(section, items):
  if (sortState.key) {
    items = items.slice().sort(function (a, b) {
      const va = a[sortState.key], vb = b[sortState.key];
      if (va === vb) return 0;
      return (va > vb ? 1 : -1) * sortState.dir;
    });
  }

items는 loadSection이 넘긴 data[section.itemsKey] = 현재 페이지 결과다(app.js:408-413). buildQuery(app.js:385-392)는 page/page_size와 필터만 보내고 정렬 파라미터를 전혀 보내지 않는다. 그런데 renderPager(app.js:158-160)는 '1–20 / 137건' 처럼 전체 건수를 표시한다.
```
- 수정 방향: 정렬을 서버로 위임한다: sortState.key/dir을 buildQuery에 sort/order 파라미터로 추가하고 헤더 클릭 시 loadSection을 재호출한다. 서버 지원 전까지는 페이지네이션이 있는 섹션(total > page_size)에서 헤더 정렬을 비활성화하거나 '현재 페이지 내 정렬' 임을 헤더에 명시한다. 비교자는 null/undefined를 항상 뒤로 보내고 문자열은 localeCompare, 숫자·날짜는 타입별로 비교하도록 수정한다.
- 검증자 판정: 반증 실패. 방어 코드·상위 가드·서버 처리 경로 모두 부재함을 직접 확인했다.\n\n[확인한 증거]\n- app.js:98-104: renderTable이 인자로 받은 현재 페이지 슬라이스만 클라이언트 정렬.\n- app.js:385-392: buildQuery가 page/page_size + 필터만 전송, sort/order 파라미터 전무.\n- app.js:408-413: loadSection이 data[itemsKey](서버가 준 20건)를 그대로 renderTable에 전달.\n- app.js:158-160: 페이저는 to

## 36. [Medium] 정렬 가능한 테이블 헤더가 키보드로 접근 불가하고 정렬 상태가 스크린리더에 노출되지 않음

- 영역: 화면
- 위치: `app/static/js/admin/app.js:105`
- 재현: 1) /admin → 사용자 섹션으로 이동한다.
2) 마우스를 쓰지 않고 Tab 키만으로 컬럼 헤더에 포커스를 주려고 시도한다.
3) 스크린리더로 헤더를 읽어 현재 정렬 방향을 확인한다.
- 기대: 헤더가 Tab으로 포커스를 받고 Enter/Space로 정렬이 토글되며, aria-sort="ascending|descending"으로 현재 정렬 상태가 통지된다. 정렬 방향이 시각적으로도(화살표 등) 표시된다.
- 실제: <th>는 기본적으로 포커서블하지 않아 Tab으로 도달할 수 없고, 키보드만 쓰는 사용자는 정렬 기능을 전혀 사용할 수 없다(cursor: pointer로 마우스 사용자에게만 상호작용 가능함을 암시). aria-sort가 없어 스크린리더는 정렬 가능 여부도, 현재 어느 컬럼이 어느 방향으로 정렬됐는지도 알리지 못한다. 정렬 방향을 나타내는 시각적 표식(▲/▼)도 없어 마우스 사용자조차 클릭 후 오름차순인지 내림차순인지 헤더만 봐서는 알 수 없다.
- 원인 근거:
```
const thead = A.el("tr", {}, section.columns.map(function (c) {
  const th = A.el("th", { text: c.label });
  th.addEventListener("click", function () {
    sortState = { key: c.key, dir: sortState.key === c.key ? -sortState.dir : 1 };
    renderTable(section, items);
  });
  return th;
}) ... );

admin.css:120: table.data th { color: var(--color-muted); font-weight: 600; cursor: pointer; user-select: none; }

<th>에 click 리스너만 붙어 있고 tabindex, role="button", keydown(Enter/Space) 핸들러, aria-sort 속성이 모두 없다.
```
- 수정 방향: th에 tabindex="0" 과 role="columnheader"를 부여하고 keydown에서 Enter/Space를 click과 동일하게 처리한다(또는 th 내부에 실제 <button>을 넣는 방식이 더 견고하다). 정렬 적용 시 해당 th에 aria-sort를 ascending/descending으로 설정하고 나머지 헤더에서는 제거한다. 라벨 옆에 방향 화살표 텍스트를 함께 렌더해 시각적 표식도 추가한다.
- 검증자 판정: 반증 4회 시도, 모두 실패 — 결함은 진짜다.

[반증 1] A.el 헬퍼가 a11y 속성을 주입하는가? → 아니다. common.js:9의 el()은 opts.attrs가 있을 때만 setAttribute를 호출하는데, thead 생성부는 A.el("th", { text: c.label })로 attrs 없이 호출한다. textContent만 설정되고 tabindex/role/aria-sort는 붙지 않는다. th 내부에 <button>을 넣는 경로도 없다.

[반증 2] 위임 키보드 핸들러나 상위 가드가 있는가? → 없다. a

## 37. [Medium] 상태 배지 체계가 화면마다 이원화 — 채팅은 한국어+하드코딩 hex, 관리자는 영어 원문 enum+토큰

- 영역: 화면
- 위치: `app/static/js/chat.js:95`
- 재현: 1) 채팅에서 '내 티켓 보여줘' → 카드의 상태 배지를 확인한다(한국어 '진행', 초록 .st-active).
2) /admin → 작업 큐 또는 승인 섹션의 상태 컬럼을 확인한다.
3) /admin → 유지보수 섹션에서 현재 상태 배지를 확인한다(app.js:587 A.statusBadge(on ? "enabled" : "disabled")).
- 기대: 한 제품 안에서 상태 라벨 언어와 색상 규칙이 하나의 체계로 통일되고, 매핑에 없는 상태도 예측 가능하게 표현된다.
- 실제: 두 개의 독립적인 상태→색상 시스템이 병존한다. 채팅은 한국어 라벨 + .st-* 하드코딩 팔레트, 관리자는 영어 enum 원문 + .badge-* 토큰 팔레트다. 관리자 화면은 한국어 UI에 'awaiting_approval', 'quality_failed', 'unmapped', 'published' 같은 영어 스네이크케이스를 그대로 노출한다. 매핑 누락도 조용히 발생한다: 유지보수 OFF는 'disabled'가 STATUS_KIND에 없어 'unknown'/'draft'와 똑같은 회색 neutral로 렌더되고, 승인 섹션 필터의 'expired'와 작업 큐 필터의 'cancelled'(sections.js:443, 472)도 매핑에 없어 회색으로 떨어진다. 채팅 쪽도 Notion에 새 상태가 추가되면 STATUS_CLASS에 없어 무색 배지가 되는데, 하드코딩된 10개 한국어 문자열이 데이터 원천(Notion) 상태 집합을 프런트에 중복 정의하고 있다.
- 원인 근거:
```
chat.js:95-99 (채팅):
  var STATUS_CLASS = {
    "진행": "st-active", "진행 중": "st-active", "계획": "st-plan", "예정": "st-plan",
    "완료": "st-done", "검증": "st-review", "검토": "st-review",
    "이슈": "st-issue", "보류": "st-issue", "취소": "st-cancel",
  };

common.js:75-88 (관리자):
  const STATUS_KIND = {
    up: "success", verified: "success", succeeded: "success", published: "success", ...
    down: "error", failed: "error", ... unknown: "neutral", draft: "neutral", running: "info", ...
  };
  function statusBadge(value) {
    if (value === true) return badge("예", "success");
    if (value === false) retur
```
- 수정 방향: 상태 라벨·색상 매핑을 tokens 계층의 단일 모듈로 통합해 채팅과 관리자가 공유하게 한다. 표시 라벨은 한국어로 번역하는 단일 사전을 두고(관리자에도 적용), 색상은 .st-* 하드코딩 hex를 제거하고 --color-success/warning/error 토큰 기반 .badge-* 로 일원화한다. 매핑에 없는 값이 조용히 회색으로 떨어지지 않도록 fallback 시 원문+중립 배지를 쓰되 개발 시 경고를 남기고, 'disabled'/'expired'/'cancelled' 등 현재 누락된 키를 매핑에 채운다.
- 검증자 판정: 반증 시도 4건 중 2건 실패, 2건 부분 성공. 핵심 주장은 살아남았다.

■ 반증 실패 (= 주장이 맞음)

1) "공유 라벨/색상 사전이 어딘가 있을 것" → 없다.
   `grep -rn "진행 중|awaiting_approval|LABEL|label_map|STATUS_LABEL" app/static/js/` 결과가
   chat.js:96, common.js:80 두 정의부 자신뿐. 공유 계층이 존재하지 않는다.

2) "chat.css의 .st-*가 실은 토큰에서 파생될 것" → 아니다. C:\Users\hshwa\cl

## 38. [Medium] staticData 무제한 증식(전체 프로젝트·티켓 raw + 응답 500건)과 동시 실행 시 last-writer-wins로 캐시·멱등성 표 유실

- 영역: n8n 워크플로
- 위치: `C:\Users\hshwa\Downloads\ClovirONE_AI_Work_Assistant\ClovirONE_AI_Work_Assistant_v7.json:558`
- 재현: 1) 서로 다른 두 사용자가 동시에(5분 TTL 만료 직후) 메시지를 보낸다. 2) 두 실행이 각각 workDataCache와 processedMessages를 갱신한 뒤 종료 순서에 따라 한쪽 쓰기가 사라진다. 3) 별도로: Notion '작업' DB의 티켓이 0건인 상태를 만들고 반복 요청하면 캐시가 영구 미스가 된다.
- 기대: 캐시는 5분 TTL 안에서 안정적으로 히트하고, 멱등성 표는 동시 실행에서도 유실되지 않아야 한다.
- 실제: 동시 실행에서 캐시 기록과 processedMessages 항목이 조용히 유실되어 중복 탐지가 새고 Notion 재조회가 반복된다. 또 히트 조건이 AND라서 프로젝트나 티켓 중 한쪽이라도 0건이면(신규 도입 초기, 권한 문제 등) 캐시가 절대 히트하지 않아 매 요청마다 두 DB를 returnAll로 전량 재조회한다(NODE 24는 OR 조건 `projects.length > 0 || tickets.length > 0`로 기록해 판정 기준도 불일치). 티켓/프로젝트가 늘어날수록 staticData가 수 MB 규모로 커져 매 실행마다 직렬화·DB 저장 비용을 낸다.
- 원인 근거:
```
NODE 24 '캐시 기록'(line 558): `staticData.workDataCache = { projects, tickets, work_schema: workSchema, ts: Date.now() };` — projects/tickets는 NODE 4/6이 `simple: false, returnAll: true`로 가져온 Notion 원본 페이지 객체 전량이다.
NODE 18 '최종 응답 저장'(line 433): `processed[value.message_id] = value;` 후 500개까지 보관 — value는 context/tickets/projects를 포함한 전체 응답 객체다.
두 구조 모두 n8n workflow staticData에 들어가고, staticData는 실행 시작 시 DB에서 로드되어 실행 종료 시 통째로 다시 저장된다. 따라서 동시 실행 2건은 같은 스냅샷을 읽고 나중에 끝난 쪽이 앞의 쓰기를 덮어쓴다.
NODE 22 '캐시 확인'(line 511)의 히트 조건: `Array.isArray(cache.projects) && cache.projects.length > 0 && Array.isArray(cache.tic
```
- 수정 방향: processedMessages는 백엔드(SQLite, requester 스코프)로 일원화하고 n8n staticData에서 제거한다. workDataCache에는 Notion 원본 대신 백엔드가 쓰는 최소 필드만 투영해 저장하거나, 캐시 자체를 러너 측으로 옮긴다. 캐시 히트 조건을 NODE 24의 기록 조건과 일치시키고(`ts` 존재 + TTL만으로 판정, 0건도 유효한 캐시로 인정) 빈 결과 캐싱을 허용한다.
- 검증자 판정: 반증 실패 — 5개 축 전부에서 방어 코드·상위 가드를 찾지 못했다.

[1] 원본 객체 전량 저장 ✅ 확인함
NODE 4/6 파라미터가 실제로 `simple: false, returnAll: true`이고, NODE 5/7 '묶기'는 `$input.all().map((item) => item.json).filter((item) => item?.id)` — 필드 투영이 전혀 없다. 따라서 workDataCache에 Notion 원본 페이지 객체 전량이 들어간다는 주장은 정확. 캐시 크기 상한도 없다(데이터 증가에 비례해 무한 증식)

## 39. [Medium] schedule.enable 승인이 설정 스냅샷 없이 object_id만 저장 — 승인 대기 중 PUT으로 스케줄을 바꿔치기해 승인자가 검토하지 않은 정의가 활성화됨(TOCTOU)

- 영역: 플랫폼 API
- 위치: `app/approvals/service.py:200`
- 재현: 실측 출력:
1) admin1 로그인 → POST /api/admin/schedules {name:"benign", preset:"daily", target:system/noop, payload_template:{"harmless":true}} → 201
2) POST /api/admin/schedules/{sid}/enable → 202
   APPROVAL VIEW {'request_type': 'schedule.enable', 'object_id': '3f91...', 'request_payload': {}, 'status': 'pending'}   ← 승인자가 볼 수 있는 정보는 object_id뿐
3) 승인 전에 admin1이 PUT /api/admin/schedules/{sid} {cron_expression:"* * * * *", payload_template:{"exfiltrate":"everything"}, timeout_seconds:3600} → PUT RESP 200 (승인 불필요)
4) admin2 로그인 → POST /api/admin/approvals/{aid}/approve {"comment":"reviewed the benign daily noop"} → 200
5) GET /api/admin/schedules/{sid}
   FINAL SCHEDULE: enabled=True, cron_expression='* * * * *', payload_template={'exfiltrate': 'everything'}, next_run_at='2026-07-14T00:01:00'
- 기대: 승인 요청에 검토 대상 설정 전체를 스냅샷으로 저장하고, 실행기는 그 스냅샷과 현재 행이 일치할 때만 적용(불일치 시 stale로 거부)해야 한다. runner.change_config / integration.change_config가 payload={"config": config.model_dump()}로 저장하는 방식과 동일해야 한다.
- 실제: request_payload={}라 승인자는 무엇을 승인하는지 화면에서 알 수 없고, 실행기는 승인 순간의 라이브 행을 읽는다. 승인 대기 중(또는 승인 후) PUT으로 cron/타깃/payload를 바꾸면 승인자가 본 적 없는 정의가 그대로 활성화되어 주기 실행된다. 승인 후 PUT도 무게이트라 활성 상태를 유지한 채 타깃 교체가 가능하다.
- 원인 근거:
```
# 요청 생성 시 payload가 비어 있음 (schedules/router.py:305-313)
approval = create_approval(db, request_type="schedule.enable", object_type="schedule",
                          object_id=row.id, requested_by=request.state.user,
                          payload={},   # ← 검토 대상 스냅샷이 전혀 없음
                          now=now)

# 실행기는 승인 시점의 '살아있는' 행을 읽어서 그대로 활성화
def _execute_schedule_enable(db, approval, app_state) -> None:
    schedule = db.get(Schedule, approval.object_id)   # ← stale 가드 없음
    ...
    schedule.enabled = True

# 대조: _execute_user_role_change에는 명시적 TOCTOU/stale 가드가 있음
#   if user.role == 
```
- 수정 방향: (1) enable_schedule의 create_approval에 payload={"snapshot": _view(row)} 저장. (2) _execute_schedule_enable에서 현재 _view(schedule)와 스냅샷의 핵심 필드(cron_expression, timezone, target_type, target_ref, payload_template, timeout_seconds)를 비교해 다르면 ConflictError('stale')로 거부. (3) update_schedule(PUT)이 enabled=True이거나 pending 승인이 있는 스케줄의 타깃/payload를 바꿀 때는 동일 승인 게이트를 태우거나 자동으로 enabled=False + pending 승인 무효화. (4) 회귀 테스트로 위 repro를 핀.
- 검증자 판정: 반증 실패 — 결함은 실제로 성립한다. 다만 severity는 high가 아니라 medium이 맞다.

[반증 시도 및 결과]
1) 실행기 방어 코드 부재 확인: app/approvals/service.py:200-217 _execute_schedule_enable은 db.get(Schedule, approval.object_id)로 라이브 행을 읽고 enabled=True를 설정. 스냅샷 비교·stale 가드 전무.
2) 상위 호출부 가드 부재 확인: app/schedules/router.py:305-313 create_appro

## 40. [Medium] Runner Registry의 enabled/maintenance/circuit breaker가 어떤 실행 경로에서도 적용되지 않음 — RunnerHttpProvider·can_dispatch가 전부 dead code

- 영역: 플랫폼 API
- 위치: `app/runners/router.py:170`
- 재현: 1) grep -rn "can_dispatch\|RunnerHttpProvider" app/ --include=*.py
   → runners/provider_http.py:12,21,33 / runners/router.py:14,170 / runners/service.py:185 뿐
2) grep -rn "Runner" app/jobs/ --include=*.py → 출력 없음
3) app/runners/router.py:170-186을 읽으면 provider 변수가 이후 한 번도 사용되지 않고 outbound_client.post가 직접 호출됨
→ 즉 관리자 콘솔에서 Runner를 disable/maintenance로 바꿔도, circuit이 열려도 실제 트래픽 경로(chat_message → n8n → runner)는 영향을 받지 않는다.
- 기대: docs/RUNNER_MANAGEMENT.md는 'can_dispatch의 거부 사유: runner_disabled / runner_maintenance / circuit_open. 판단은 호출 직전마다 수행된다', '쿨다운 동안 can_dispatch가 circuit_open으로 호출을 거부', 'POST /{id}/test — RunnerHttpProvider.test_request'라고 명시한다. 문서대로면 최소한 /test가 provider를 경유해 can_dispatch를 평가해야 한다.
- 실제: can_dispatch를 부르는 유일한 함수(RunnerHttpProvider.invoke)가 어디서도 호출되지 않는다. /test조차 provider를 만들어놓고 버린 뒤 outbound_client를 직접 호출한다. 결과적으로 circuit breaker는 카운터(record_runner_result)만 돌고 차단 기능은 한 번도 동작하지 않으며, 콘솔의 Runner 활성/점검 토글은 실제 동작에 아무 영향이 없다(버튼은 눌리지만 결과는 없음). 문서와 구현이 불일치한다.
- 원인 근거:
```
@router.post("/{runner_id}/test", dependencies=[Depends(require_roles(*OPS_ROLES))])
def test_request(request: Request, runner_id: str, db: Session = Depends(get_db)):
    row = get_runner_or_404(db, runner_id)
    provider = RunnerHttpProvider(request.app.state.outbound_client)   # ← 생성 후 사용되지 않음(dead)
    ...
    response = request.app.state.outbound_client.post(row.base_url, ...)   # provider.invoke가 아니라 직접 호출

# 채팅 파이프라인은 Runner 레지스트리를 아예 참조하지 않는다:
#   jobs/handlers/chat_message.py:118 → ctx.outbound_client.post(settings.n8n_work_assistant_url, ...)
#   grep -rn "Runner" app/jobs/ → 0건
# c
```
- 수정 방향: 둘 중 하나로 정리: (A) 실제 연결 — /test와 /health를 RunnerHttpProvider 경유로 바꾸고(테스트는 의도적 우회라면 그 의도를 코드 주석이 아니라 provider의 명시적 플래그로 표현), 향후 runner 직접 호출 경로가 생기면 반드시 provider.invoke를 쓰도록 강제(정적 검사 추가). (B) 정직한 축소 — RunnerHttpProvider/can_dispatch를 삭제하고 docs/RUNNER_MANAGEMENT.md의 circuit breaker 차단 서술을 '카운터/표시 전용'으로 정정, KNOWN_LIMITATIONS에 명시. 어느 쪽이든 runners/router.py:170의 미사용 provider 변수는 제거.
- 검증자 판정: 반증 실패 — 결함 성립. 5개 각도로 반증 시도했으나 핵심 주장 전부 확인됨.\n\n[확인된 사실]\n1) can_dispatch 프로덕션 호출처 0건: app/runners/provider_http.py:33이 유일. 나머지는 tests/unit/test_runner_circuit.py와 dist/stage/ 빌드 사본뿐.\n2) RunnerHttpProvider.invoke 프로덕션 호출처 0건: provider_http.py:59(test_request, 이것도 미호출)과 테스트 2곳(tests/integration/test

## 41. [Medium] 대화 삭제·보존기간 만료가 Job payload를 지우지 않아 삭제된 대화의 원문이 큐에 영구 잔존 (retention 설정이 지켜지지 않음)

- 영역: 플랫폼 API
- 위치: `app/chat/service.py:75`
- 재현: 1) user가 대화 생성 → 메시지 전송(POST /api/conversations/{cid}/messages) → Job(chat_message) 생성, payload_json에 content 원문 저장
2) DELETE /api/conversations/{cid} → 200 {"ok": true}
3) GET /api/conversations/{cid}/messages → 404 (사용자 시점에선 삭제됨)
4) operator/admin으로 GET /api/admin/jobs → 삭제된 대화의 job이 그대로 조회되고 payload.content에 원문이 남아 있음 (finding #4의 실측과 동일 경로)
5) conversation_retention_days가 지나 purge_old_conversations가 돌아도 jobs 테이블은 손대지 않으므로 원문은 계속 남는다.
- 기대: 사용자가 대화를 삭제하면 그 대화에서 파생된 Job payload의 본문도 함께 제거(또는 익명화)되어야 하고, conversation_retention_days 만료 시에도 동일해야 한다. '삭제했다'가 실제로 삭제를 의미해야 한다.
- 실제: Job 행은 삭제·보존정책 어디에서도 정리되지 않는다. strip_stale_job_attachments는 이미지 바이트만 24시간 후 제거할 뿐 content 원문·requester 이메일은 무기한 보존된다. 사용자에게는 삭제된 것처럼 보이지만 운영 화면에서는 계속 읽힌다.
- 원인 근거:
```
def delete_conversation(db: Session, conversation: Conversation) -> None:
    """Hard-delete a conversation and its messages (owner-checked by caller)."""
    db.execute(delete(Message).where(Message.conversation_id == conversation.id))
    db.delete(conversation)
    db.flush()
    # ← Job(conversation_id=..., payload_json에 content 원문 포함) 은 그대로 남음

# core/retention.py: 대화/알림만 purge, jobs 테이블은 대상 아님
def run_retention(db, *, now, settings_cache) -> dict:
    return {"conversations": purge_old_conversations(...),
            "notifications": purge_old_notifications(...),
            "job_attachm
```
- 수정 방향: (1) delete_conversation에서 해당 conversation_id의 Job payload를 즉시 스텁화(content 제거, strip_attachment_bytes와 동일한 방식)하거나 터미널 상태 Job은 삭제. (2) retention.py에 purge_old_jobs / scrub_job_payloads를 추가해 purge_old_conversations가 지운 conversation_id 집합의 Job도 함께 정리하고 run_retention 반환값에 포함. (3) 근본적으로 _job_view가 원문을 노출하지 않게 하면(finding #4) 영향이 크게 줄어든다. (4) 회귀 테스트: 대화 삭제 후 /api/admin/jobs 응답에 원문이 없을 것.
- 검증자 판정: 반증 5가지 시도 모두 실패 — 주장 성립.

1) DB 레벨 cascade 반증 실패: alembic/versions/0005_jobs.py:22-38이 conversation_id/user_id를 sa.String 순수 컬럼으로 생성. ForeignKey·ondelete 없음. app/jobs/models.py:28과 일치. cascade 경로 부재 확인.

2) 다른 곳의 정리 코드 반증 실패: 저장소 전체에서 delete(Job)|DELETE FROM jobs|purge_old_jobs|scrub|job_retention g

## 42. [Medium] 존재하지 않는 날짜(2월 30일 등)를 말하면 마감 조건이 통째로 사라지고 전체 티켓이 반환됨

- 영역: 러너 데이터 표시
- 위치: `C:\Users\hshwa\clovirone-web-assistant\runner\claude-work-assistant\assistant.py:919`
- 재현: RUNNER_TOKEN=x python -c "import assistant as a; sm=a.actual_status_map({},[{'status':'진행'}]); mk=lambda i,d:a.normalize_ticket({'id':i,'properties':{'제목':{'title':[{'plain_text':i}]},'진행상태':{'status':{'name':'진행'}},**({'마감일':{'date':{'start':d}}} if d else {})}},{}); ts=[mk('a','2026-07-16'),mk('b','2027-01-01'),mk('c',None)]; print(a.parse_date_range('2월 30일까지 마감인 티켓 보여줘', a.now_kst().date())); print(a.query_tickets('2월 30일까지 마감인 티켓 보여줘',{},{'email':'a@b.com','name':'x'},None,[],ts,sm)['response_text'].splitlines()[0])"
- 기대: 사용자가 말한 날짜 조건이 해석 불가면 되묻거나(NEED_INPUT) 무시했음을 명시해야 한다.
- 실제: 조건이 침묵 강등돼 마감일 없는 티켓·내년 마감 티켓까지 '전체 티켓 (완료 제외)'로 나열된다. 헤더 어디에도 날짜를 버렸다는 표시가 없어, 사용자는 이 목록이 '2월 30일까지 마감'인 줄 안다.
- 원인 근거:
```
908: md = re.search(r"(?:(20\d{2})년\s*)?(\d{1,2})월\s*(\d{1,2})일", raw) …  try: target = date(...)  except ValueError: return None   ← 파싱 실패를 '날짜 조건 없음'과 동일하게 취급
실측:
  a.parse_date_range('2월 30일까지 마감인 티켓 보여줘', date(2026,7,15)) -> None
  query_tickets(같은 문장) -> TICKET_LIST | '전체 티켓 (완료 제외): 총 3건'  (마감 2027-01-01 티켓, 마감 없음 티켓까지 포함)
'2월 29일까지 마감'(평년), '6월 31일'도 동일하게 None.
```
- 수정 방향: except ValueError에서 None 대신 {'mode':'INVALID','raw':매치문자열}를 반환하고, query_tickets에서 INVALID면 response('NEED_INPUT', "'2월 30일'은 존재하지 않는 날짜입니다. 정확한 마감일을 알려주세요.") 로 되묻는다. '날짜 언급 없음'과 '날짜 해석 실패'를 서로 다른 상태로 구분(같은 원칙을 ISO 분기 894행 부근에도 적용).
- 검증자 판정: 반증 실패 — 결함 성립. 확인 경로: (1) 상위 가드 부재: 라우터 전 체인을 실측한 결과 '2월 30일까지 마감인 티켓 보여줘'는 create=false, freeform=false, comment=false, update=false, query=true → answer_query → is_freeform_query=false이므로 LLM(claude_query)이 아니라 규칙 엔진 query_tickets로 확정 진입. 잘못된 날짜를 구제하는 대화형 폴백 없음. (2) query_tickets 내부 가드 부재: 2212행 d

## 43. [Low] 사이드바가 역할과 무관하게 16개 섹션을 전부 노출하고, 승인 섹션의 승인/거절 버튼에 roles 게이트가 없어 operator에게는 항상 403

- 영역: 관리자 운영
- 위치: `app/static/js/admin/app.js:26`
- 재현: 1) operator 계정으로 로그인 → /admin
2) 좌측 nav에 '사용자', '감사 로그' 포함 16개 섹션이 모두 보임
3) '사용자' 클릭 → '이 화면에 접근할 권한이 없습니다.' (섹션 전체가 죽은 링크)
4) '승인' 클릭 → 목록은 200으로 뜨고 pending 행에 '승인'/'거절' 버튼이 렌더링됨
5) '승인' 클릭 → confirm 모달까지 뜬 뒤 POST /api/admin/approvals/{id}/approve → 403, 에러 토스트만 표시. 같은 행의 '취소'는 정상 동작.
- 기대: 서버 RBAC가 최종 권한이라는 원칙(CLAUDE.md §2-5, deps.py 상단 주석)은 유지하되, 콘솔은 자신의 역할로 실행 불가능한 진입점을 애초에 보여주지 않아야 한다. sections에 이미 있는 roles 메타데이터 패턴대로 nav와 승인/거절 버튼도 게이트해야 한다.
- 실제: nav는 역할 필터가 없어 operator에게 항상 403인 섹션 2개를 링크로 노출하고, 승인 섹션은 roles를 지정한 다른 모든 섹션과 달리 승인/거절에 roles를 빠뜨려 operator에게 '눌리지만 반드시 실패하는' 버튼을 렌더링한다. 같은 행 안에서 '취소'만 실제로 동작해 정책이 화면마다 어긋나 있다.
- 원인 근거:
```
app.js:26-52 renderNav() — SECTIONS를 그대로 순회, A.role() 기반 필터 전혀 없음
app.js:415  if (e.status === 403) showError("이 화면에 접근할 권한이 없습니다.");   ← 사후 에러 화면으로만 처리
app/admin/router.py:19-20  role == ROLE_USER 만 리다이렉트 → operator/auditor는 /admin 진입
서버측 실제 권한:
  app/users/router.py:30  require_roles("admin","system_admin")      → operator는 '사용자' 섹션 전체 403
  app/audit/router.py:20  require_roles("admin","system_admin","auditor") → operator는 '감사 로그' 전체 403
  app/approvals/router.py:29 DECIDE_ROLES = ("admin","system_admin")
콘솔 정의의 비대칭:
  sections.js:450-451  { label: "승인", api: ... }, { label: "거절", api: ... 
```
- 수정 방향: (1) sections.js 각 섹션에 readRoles(예: users: WRITE, audit: ["admin","system_admin","auditor"])를 선언하고 app.js:30 renderNav()에서 A.role() 기준으로 필터. (2) sections.js:450-451의 '승인'/'거절'에 roles: WRITE 추가(approvals/router.py:29 DECIDE_ROLES와 일치). (3) app.js:415의 403 화면은 방어선으로 남겨둘 것 — UI 숨김은 통제가 아니며 서버 require_roles가 계속 최종 판단이어야 한다.
- 검증자 판정: 부분 성립. 반증 결과를 나눠 보고한다.\n\n[반증 성공 — 주장 헤드라인(nav 16개 노출)은 결함이 아님]\n1) docs/ADMIN_GUIDE.md:3-5가 이 동작을 명시적으로 문서화한 의도된 설계다: \"화면은 좌측 내비게이션 16개 섹션으로 구성되며, 버튼이 보여도 실제 권한은 서버 RBAC이 결정한다(권한 부족 시 403).\" nav에 역할 필터가 없는 것은 사양 위반이 아니라 문서화된 정책이고, sections에는 애초에 read용 roles 메타데이터 자체가 설계된 적이 없다(users/audit 섹션 모두 s

## 44. [Low] 진단 번들·복원 안내 등 구현 완료된 운영 엔드포인트가 관리자 콘솔에서 도달 불가

- 영역: 관리자 운영
- 위치: `app/health/router.py:46`
- 재현: 1) system_admin으로 /admin#backup 접속 → '백업 실행'과 행별 '검증'만 보임. 장애 시 복원 절차를 콘솔에서 확인할 수 없음.
2) 브라우저에서 직접 https://clovirone-ai.gooddi.lab/api/admin/backups/restore-instructions 호출 → 4단계 절차 JSON이 정상 반환됨(엔드포인트는 살아 있음).
3) /admin 전 섹션을 훑어도 진단 번들을 내려받는 버튼이 없음. GET /api/admin/diagnostics/bundle 은 정상 응답.
- 기대: docs/OPERATIONS.md·RUNBOOK 흐름상 장애 대응 시 (a) 진단 번들 확보 (b) 복원 절차 확인이 콘솔에서 가능해야 한다. 두 기능 모두 마스킹까지 끝난 상태로 구현돼 있으므로 진입점만 붙이면 된다.
- 실제: 세 엔드포인트 모두 구현·RBAC·마스킹이 완료됐지만 관리자 콘솔에 진입점이 없어, 실제로 쓰려면 관리자가 URL을 직접 알고 브라우저 주소창에 입력해야 한다. 특히 복원 안내는 '웹에서 복원하지 않고 안내만 준다'는 설계 결정의 결과물인데, 그 안내가 UI에 없어 설계 의도가 반쪽만 구현됐다.
- 원인 근거:
```
구현돼 있고 라우팅도 살아 있으나 sections.js에 어떤 참조도 없는 엔드포인트:
  app/health/router.py:46-53  GET /api/admin/diagnostics/bundle  (require_roles("admin","system_admin")) — build_diagnostic_bundle(): dashboard + mask_sensitive(settings) + 최근 실패 job 20건 + down 상태 integration
  app/backups/router.py:68-79 GET /api/admin/backups/restore-instructions (require_roles("system_admin")) — 복원 4단계 절차 반환
  app/jobs/router.py:79-81    GET /api/admin/jobs/stats
grep 확인: sections.js·app.js 어디에도 "diagnostics", "restore-instructions", "jobs/stats" 문자열 없음
백업 섹션 정의 sections.js:500-514 — rowActions=[검증], customActions=[백업 실행] 뿐, 
```
- 수정 방향: (1) sections.js backup 섹션(500-514)에 customActions 추가: { label: "복원 안내", roles: ["system_admin"], api: { method: "GET", path: "/api/admin/backups/restore-instructions" } } — 단 app.js:250-271의 customActions 실행부는 현재 JSON.stringify({}) 본문으로 POST만 보내므로 GET 지원 분기를 함께 추가해야 함. (2) dashboard 섹션(sections.js:52-53)에 '진단 번들 내려받기' 버튼 추가 → GET /api/admin/diagnostics/bundle 결과를 Blob으로 저장. (3) 대시보드가 이미 jobs_24h를 표시하므로 jobs/stats는 UI 필요 없다고 판단되면 엔드포인트를 제거하거나 docs/OPERATIONS.md에 'API 전용'이라고 명시해 중복 구현을 정리.
- 검증자 판정: 반증 시도 4건 중 3건 성공, 1건 실패 → 주장은 성립하나 범위는 1/3로 축소.

■ 사실관계 검증 (모두 정확)
- app/health/router.py:46-53, app/backups/router.py:68-79, app/jobs/router.py:79-81 세 엔드포인트 실재·RBAC 정상 확인.
- grep 재현: `grep -rn "diagnostics/bundle|restore-instructions|jobs/stats" --include=*.js --include=*.html app/static app/templ

## 45. [Low] 대화 컨텍스트·응답문 생성 책임이 백엔드와 n8n에 중복 구현 — 레이블 맵·상태 기본값·속성명이 양쪽에 하드코딩되어 분기 위험

- 영역: n8n 워크플로
- 위치: `C:\Users\hshwa\Downloads\ClovirONE_AI_Work_Assistant\ClovirONE_AI_Work_Assistant_v7.json:420`
- 재현: Notion '작업' DB에서 '난이도' 속성 이름을 '작업 난이도'로 바꾼다. 백엔드 assistant.py의 매핑만 고치고 배포한다. 그 후 난이도 변경을 요청한다.
- 기대: 스키마를 동적 조회하는 설계이므로 속성명 변경이 한 곳 수정으로 반영되어야 한다.
- 실제: n8n NODE 17의 하드코딩된 label 맵이 '난이도'를 찾지 못해 '적용된 값 —' 표시에서 조용히 누락되고, 백엔드와 n8n의 응답문이 서로 다른 레이블 집합을 쓰게 된다. 티켓 생성 시 status 기본값 '계획'도 n8n에만 박혀 있어 Notion 스키마의 기본 상태가 바뀌면 사용자에게 잘못된 상태가 표시된다.
- 원인 근거:
```
NODE 17 'Notion 변경 결과'(line 420)가 백엔드와 동일한 로직을 재구현한다:
1) 레이블 맵 중복 — n8n: `const labels = { status: '진행상태', due_date: '마감일', priority: '우선순위', difficulty: '난이도', assignee_ids: '티켓 담당자' };` vs assistant.py:2988 및 3007: `{"title": "제목", "status": "진행상태", "due_date": "마감일", "start_date": "시작일", "priority": "우선순위", "difficulty": "난이도", "assignee_ids": "티켓 담당자"}` (n8n판에는 title/start_date가 빠져 있어 이미 불일치).
2) 상태 기본값 하드코딩 — n8n: `status: context.status ?? '계획'`.
3) Notion 속성명 하드코딩 — `const label = { '진행상태': '진행상태', '마감일': '마감일', '시작일': '시작일', '우선순위': '우선순위', '난이도': '난이도', '제목': '제목' };` 워크플로가 NODE 8에서 '
```
- 수정 방향: 응답문 생성과 컨텍스트 리비전 관리를 백엔드(assistant.py) 한 곳으로 일원화한다. n8n은 Notion HTTP 호출과 결과 전달만 담당하고, 성공 응답문·레이블·기본값은 백엔드가 write 결과를 후처리하는 엔드포인트에서 만들게 한다. 최소 조치로는 NODE 17의 label/labels 맵과 '계획' 기본값을 NODE 8이 조회한 스키마에서 파생시키고, _context_revision 증가는 백엔드에만 남긴다.
- 검증자 판정: 반증 실패 — 핵심 주장(응답문·레이블 생성이 백엔드와 n8n에 중복 구현되어 이미 분기)은 성립한다. 다만 4개 근거 중 2개는 반증됐고, 그 2개가 원래 severity(medium)를 떠받치고 있었으므로 low로 정정한다.

[확인된 사실 — 코드 원문 일치]
NODE 17 '(Notion 변경 결과)' jsCode를 JSON에서 직접 덤프한 결과, 인용된 4개 코드 조각이 모두 축자 일치. assistant.py:2997-3000, 3016-3019(labels), 169(persist_context)도 일치. 인용 위조 없

## 46. [Low] BodySizeLimitMiddleware가 Content-Length 헤더가 있을 때만 검사 — chunked 요청은 본문 크기 상한이 전혀 적용되지 않음

- 영역: 플랫폼 API
- 위치: `app/core/middleware.py:81`
- 재현: Transfer-Encoding: chunked 로 Content-Length 없이 임의 크기 본문을 /api/admin/... 등에 전송하면 미들웨어의 413 경로에 도달하지 않고 그대로 핸들러로 넘어간다(코드 경로상 declared is None → 무검사). 프로덕션에서는 nginx의 client_max_body_size가 먼저 막지만, nginx를 거치지 않는 경로(127.0.0.1:8080 직접 접근, SSH 터널, 향후 프록시 설정 변경)에서는 앱 계층 상한이 0이 된다.
- 기대: 주석대로 defense in depth라면 Content-Length 유무와 무관하게 실제 수신 바이트 누적치로 상한을 강제해야 한다(스트림을 읽으며 limit 초과 시 413).
- 실제: Content-Length가 없는 요청에는 어떤 상한도 적용되지 않는다. 앱 계층 방어가 프록시 설정에 100% 의존하게 되어 '심층 방어'라는 주석과 실제 동작이 불일치한다.
- 원인 근거:
```
class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        declared = request.headers.get("content-length")
        if declared is not None:            # ← 헤더가 없으면(=chunked) 아래 검사를 통째로 건너뜀
            try:
                length = int(declared)
            except ValueError:
                return _reject(request, 400, "bad_request", "Invalid Content-Length")
            limit = MAX_BODY_BYTES
            if request.method == "POST" and _MESSAGE_POST_RE.match(request.url.path):
                limit = ATTACHMENT_BODY_BYTES
            
```
- 수정 방향: receive 래퍼로 실제 바디 청크를 누적하며 limit 초과 시 413을 반환하는 pure ASGI 미들웨어로 교체(BaseHTTPMiddleware 대신). 최소한 Content-Length가 없고 Transfer-Encoding: chunked인 요청은 명시적으로 411/413으로 거부하는 가드를 추가하고, 회귀 테스트로 chunked 대용량 요청 → 413을 핀.
- 검증자 판정: 반증 3회 시도, 전부 실패 → 결함 성립.

[반증1: 코드 내 다른 가드 존재?] 실패. 저장소 전체를 MAX_BODY_BYTES / content-length / transfer-encoding / chunked 로 grep한 결과, 앱 계층 크기 검사는 app/core/middleware.py:81 단 하나뿐. 핸들러·의존성 계층 상한 없음. runner/claude-work-assistant/assistant.py:3926의 자체 검사는 :8789의 별도 프로세스라 이 경로와 무관.

[반증2: uvicorn/Starlet

## 47. [Low] 프로젝트 담당자 이름이 해석되지 않으면 '담당자 미지정'으로 표시 — 담당자(정)가 실재하는데 없다고 단정

- 영역: 러너 데이터 표시
- 위치: `C:\Users\hshwa\clovirone-web-assistant\runner\claude-work-assistant\assistant.py:1078`
- 재현: RUNNER_TOKEN=x python -c "import assistant as a; sm=a.actual_status_map({},[{'status':'진행'}]); p=a.normalize_project({'id':'p1','properties':{'프로젝트':{'title':[{'plain_text':'차세대 포털 구축'}]},'진행 상태':{'status':{'name':'진행'}},'담당자(정)':{'people':[{'object':'user','id':'aaaa-bbbb-cccc-dddd'}]}}}); print(a.project_role(p,None,{'email':'a@b.com','name':'황형섭'})); print(a.query_tickets('전체 프로젝트 보여줘',{},{'email':'a@b.com','name':'황형섭'},None,[p],[],sm)['response_text'])"
- 기대: 담당자(정) 값이 있으면 '담당자 미지정'이라고 표시하면 안 된다. '담당자 정 (이름 미확인)' 처럼 존재 사실은 유지해야 한다.
- 실제: '전체 프로젝트' 목록에서 담당자가 있는 프로젝트가 '담당자 미지정'으로 뜬다. 담당자 배정 누락으로 오인해 잘못된 후속 조치(재배정 요청)를 유발한다. 또한 owners[0]만 써서 공동 담당자(정)가 2명 이상이면 나머지는 화면에서 사라진다.
- 원인 근거:
```
project_role(): owners = [text(x.get("name")) for x in safe_list(project.get("primary")) if text(x.get("name"))]
                return f"담당자 정 {owners[0]}" if owners else "담당자 미지정"
실측(담당자(정) people=[{id:'aaaa-bbbb-cccc-dddd'}] 인 프로젝트):
  normalized primary: [{'id': 'aaaa-bbbb-cccc-dddd', 'name': '', 'email': ''}]
  project_role -> '담당자 미지정'
  PROJECT_LIST: '1. 차세대 포털 구축\n   역할: 담당자 미지정 / 상태: 진행 / 미완료 티켓 0건'
```
- 수정 방향: owners = [person_label(x) for x in safe_list(project.get('primary'))] 로 바꾸고, 비어 있을 때만 '담당자 미지정'. 표시도 owners[0] 대신 ', '.join(owners)로 전원 노출. backfill_people(635행)이 실패한 경우(=워크스페이스 어디에도 이름이 없는 id)와 '사람 필드가 비어 있음'을 코드 전역에서 구분하도록 person_label을 유일한 렌더 관문으로 통일.
- 검증자 판정: 반증 실패. 코드 결함은 확인되나, 주장이 서술한 "현재 사용자가 겪는 피해"는 라이브 데이터에서 발생하지 않아 severity를 medium→low로 하향한다.

■ 반증 시도 1: backfill_people(635행)이 이름을 채워주는 방어 코드 아닌가 → 실패.
build_directory(604행)는 별도 Notion users API가 아니라 **payload의 projects/tickets 자체에서** 디렉터리를 만든다(3713행). 따라서 워크스페이스 어디에도 이름이 없는 id는 backfill로 구제 불가능하다. 결

## 48. [Low] 계정 잠금 응답(403 account_locked)이 비밀번호 검증 전에 반환되어 계정 존재 여부가 노출됨 (user enumeration)

- 영역: 보안
- 위치: `app/auth/router.py:99`
- 재현: 1) 통합 테스트에서 make_user(email="real@goodmit.co.kr") 로 계정 생성.
2) 레이트리밋 회피를 위해 시도마다 fake_clock.advance(30) 후 POST /login {email, password:"WrongPass-000!"}를 6회 반복 → 6번째 응답 확인: 403 account_locked.
3) 존재하지 않는 nobody@goodmit.co.kr에 동일하게 6회 → 6번째 응답 확인: 401 invalid_credentials.
4) 두 응답의 (status_code, error.code)가 다름 = 계정 존재 여부 확정 가능.
- 기대: 인증 실패 응답은 계정 존재 여부와 무관하게 구분 불가능해야 한다. 잠금 상태도 올바른 비밀번호를 제시한 요청자에게만(또는 별도 채널로) 알리는 것이 원칙이며, 그 전까지는 존재하지 않는 계정과 동일한 401/invalid_credentials로 수렴해야 한다.
- 실제: 6회 시도만으로 임의 이메일의 계정 존재 여부를 확정할 수 있다(존재=403 account_locked, 부재=401 invalid_credentials). 더불어 존재하지 않는 계정은 Argon2 검증을 건너뛰어 응답이 빨라 타이밍으로도 구분 가능하다.
- 원인 근거:
```
app/auth/router.py:99-100 — 잠금 검사가 비밀번호 검증(:102)보다 먼저 수행되고, 존재하지 않는 계정과 다른 상태코드/에러코드를 반환한다:

    if user is not None and user.locked_until is not None and user.locked_until > now:
        raise AccountLockedError()          # 403 / "account_locked"

    if user is None or not verify_password(user.password_hash, password):
        ...
        raise InvalidCredentialsError()     # 401 / "invalid_credentials"

존재하는 계정은 실패 5회(settings.login_max_failures) 누적 시 잠기고(:105-106), 이후 요청은 비밀번호를 몰라도 403 account_locked를 돌려준다. 존재하지 않는 계정은 user is None이라 실패 카운트가 쌓이지 않아 영원히 401이다.

실제 관측 출력 (rate limit 영향을 배제하
```
- 수정 방향: 1) 잠금 검사를 비밀번호 검증 뒤로 옮겨, 비밀번호가 맞은 경우에만 AccountLockedError를 반환한다. 비밀번호가 틀렸으면 잠금 여부와 무관하게 401 invalid_credentials로 통일한다(잠긴 계정의 실패 카운트는 계속 누적하되 응답은 동일).
   - 이때 잠긴 계정 안내는 app/notifications/service.py의 기존 account_locked 알림(:109-121)과 로그인 화면의 일반 안내 문구로 대체 — UX 손실이 거의 없다.
2) 타이밍 채널 제거: user is None인 경우에도 더미 Argon2 해시에 대해 verify_password()를 수행해 연산 시간을 맞춘다(예: 모듈 상수 _DUMMY_HASH = hash_password(secrets.token_urlsafe(32))).
3) 회귀 방지: tests/security/ 에 "존재/부재 계정의 로그인 실패 응답 (status_code, error.code)가 동일하다"는 테스트를 추가한다.
- 검증자 판정: 반증 실패 — 주장 성립. 5가지 반증 시도 모두 무산됨.

(1) 상위 정규화 가드 부재: app/core/errors.py:98-107의 AppError 핸들러는 exc.code/exc.status_code를 그대로 통과시킨다. AccountLockedError(403/account_locked)와 InvalidCredentialsError(401/invalid_credentials)가 클라이언트에 구분 가능한 형태로 도달한다. app/auth/router.py:99-100의 잠금 검사가 :102의 verify_password보

## 검증에서 기각된 주장

발굴자가 결함이라고 봤으나 검증자가 반증에 성공한 항목이다. 고치지 않는다.

- LLM에 넘기는 슬림 페이로드가 담당자·프로젝트 담당자 이름을 빈 문자열로 전달 (person_label 미적용)
  - 기각 사유: 반증 성공. 주장자가 놓친 방어 코드가 두 겹 있고, 주장한 피해(actual)는 라이브 프로브로 반증됐다.

1) backfill_people (635행) 미고려 — dispatch 직전 3714행에서 항상 실행되어, 워크스페이스 어디든 이름이 있는 인물은 슬림 페이로드 생성 전에 이름이 채워진다. 실측(Case B): 같은 id가 다른 티켓에 이름과 함
- n8n가 HTTP 200으로 에러 본문을 반환하면 '요청이 처리되었습니다'라는 거짓 성공 응답을 사용자에게 표시하고 Job은 succeeded로 종결
  - 기각 사유: 반증 성공. 주장의 전제(n8n이 200 + {"ok":false,"error":...} 본문 반환)가 실제 시스템에서 생성 불가능한 조작된 페이로드다.

[1] 핸들러 코드 자체는 정확히 기술됨: chat_message.py:43의 기본 문구 폴백과 200 무조건 성공 경로는 실재한다. 그러나 repro는 실제 시스템이 아닌 가짜 본문을 테스트했다.

[
- '대화 상태 동기화'(NODE 20) 실패 시 워크플로 전체 중단 — Notion 쓰기는 성공했는데 사용자는 오류를 받고, 재시도 시 티켓 중복 생성
  - 기각 사유: 반증 성공. 주장의 핵심 전제가 사실과 다르다.

【1】NODE 20에 오류 처리가 있다 (주장은 "없다"고 단정)
주장은 `retryOnFail`·`alwaysOutputData`·`onError`만 grep했고, n8n의 레거시 동등 속성인 `continueOnFail`은 grep하지 않았다. 실제 파일(ClovirONE_AI_Work_Assistant
- Notion 쓰기 노드(티켓 생성/변경/댓글)에 onError 미설정 — NODE 17의 WRITE_ERROR 복구 경로 전체가 도달 불가능한 죽은 코드
  - 기각 사유: 반증 성립 — 주장은 grep 누락에 기반한 오진이다.

1) 결정적 반증: 세 쓰기 노드 모두 `continueOnFail: true`를 갖고 있다.
C:\Users\hshwa\Downloads\ClovirONE_AI_Work_Assistant\ClovirONE_AI_Work_Assistant_v7.json 의 'Notion 티켓 생성'(id acb3b6
- 'ClovirONE 업무 해석'(NODE 10) onError 미설정 — 러너 장애 시 NODE 11의 ASSISTANT_ERROR 경로가 죽은 코드가 되어 모든 요청이 raw 오류로 실패
  - 기각 사유: 반증 성공. 주장의 핵심 전제(NODE 10에 오류 계속-진행 설정이 없어 500/504가 예외로 워크플로를 중단시킨다)가 사실이 아니다.

1) 놓친 방어 코드: NODE 10은 v7.json:234에 `"continueOnFail": true`를 갖고 있다. 주장은 onError·retryOnFail·neverError 세 키만 조회했고(그 셋이 없는 
- '내 업무 현황'이 기한 초과 티켓을 정상 티켓과 동일하게 표시 — 10일 지난 마감이 아무 표시 없이 섞여 나옴
  - 기각 사유: 반증 성립. 코드 사실 자체는 맞으나(format_ticket 1118행은 today 파라미터가 없고, MY_WORK_SUMMARY 2432~ 블록은 status로만 집계하며, grep "초과|지연|overdue" 결과 렌더 경로에 기한 초과 로직 전무 — 서버 /opt/claude-work-assistant/assistant.py에서도 동일 확인), 이를

---

# 2차 검수 (수정 이후 재검수)

1차 수정을 배포한 뒤 같은 방식으로 다시 검수했다. 이번에는 '이 수정이 무언가를 깨뜨렸는가'를 함께 물었다.

- 확정: **26건** (기각 6건)

| 심각도 | 종류 | 건수 |
|---|---|---|
| High | 회귀(이번 수정이 깨뜨림) | 3 |
| High | 신규 발견 | 9 |
| High | 고쳤다는데 안 고쳐짐 | 3 |
| Medium | 신규 발견 | 8 |
| Medium | 고쳤다는데 안 고쳐짐 | 1 |
| Low | 고쳤다는데 안 고쳐짐 | 2 |

가장 뼈아픈 것은 1차 수정이 만든 회귀였다. '이름을 못 찾으면 정직하게 말한다'는 수정이
못 알아들은 조건까지 이름으로 단정해, "내가 담당하는 티켓 보여줘"에 "'내가 담당하는'이라는
이름으로는 찾지 못했습니다"라고 답했다. 얼버무림을 없애려다 더 나쁜 거짓말을 한 것이다.
적대적 검수가 없었다면 이대로 배포된 채 남았을 것이다.

## R1. [High / 신규 발견] isSafeNotionUrl이 실제 데이터의 호스트(app.notion.com)를 거부해 모든 카드에서 'Notion에서 열기' 링크가 조용히 사라진다

- 위치: `app/static/js/chat.js:72`
- 재현: 1) 채팅에서 '내 티켓 보여줘' 전송. 2) 티켓 카드가 렌더되는 것을 확인. 3) 어떤 카드에도 'Notion에서 열기 ↗' 링크가 없다. 4) DevTools 콘솔에서 new URL('https://app.notion.com/p/x').hostname === 'app.notion.com' → 위 allowlist 어디에도 매치되지 않음을 확인.
- 기대: 티켓/프로젝트 카드마다 'Notion에서 열기 ↗' 링크가 보이고, 클릭하면 해당 Notion 페이지가 새 탭에서 열린다.
- 실제: 링크가 한 번도 렌더되지 않는다. 오류도 안내도 없이 조건이 조용히 버려진다(침묵 강등). 사용자는 채팅에서 Notion 원본으로 이동할 수단이 전혀 없다.
- 수정 방향: isSafeNotionUrl의 허용 호스트에 'app.notion.com'을 추가한다(기존 www.notion.so/notion.so/*.notion.site 유지). 하드코딩 목록을 늘리는 대신 `parsed.hostname === 'app.notion.com' || parsed.hostname === 'www.notion.so' || parsed.hostname === 'notion.so' || parsed.hostname.endsWith('.notion.site')` 형태로 명시하고, tests/에 실제 프로덕션 URL 샘플(

## R2. [High / 신규 발견] 카드 번호를 n8n이 절대 전달하지 않는 structured.start_index로 계산해, 2페이지부터 카드 번호가 본문과 어긋나고 '상세' 버튼이 거부된다

- 위치: `app/static/js/chat.js:187`
- 재현: 1) '내 티켓 2개만 보여줘' 전송 → 본문 '1. …/2. …', 카드 1./2. (여기까지는 우연히 일치). 2) '더 보여줘' 전송 → 본문은 '3. …/4. …'인데 카드는 다시 '1.' '2.'로 매겨진다. 3) 카드 '1.'(실제로는 3번 티켓)의 '상세' 버튼 클릭 → chat.js:176이 '1번 상세 보여줘'를 전송 → 러너가 ambiguous_number로 거부. 4) 동시에 같은 화면에서 본문 텍스트와 카드가 같은 티켓을 중복 표시한다.
- 기대: 카드 번호가 답변 본문의 번호(3., 4., …)와 일치하고, '상세' 버튼이 그 티켓의 상세를 연다. 목록 답변은 본문 요약 한 줄 + 카드로 한 번만 표시된다.
- 실제: 2페이지 이상에서 카드 번호가 항상 1부터 다시 시작해 본문 번호와 모순되고, '상세' 버튼은 러너에게 거부당해 아무 결과도 못 준다. 중복 제거는 한 번도 동작하지 않아 모든 목록이 두 번씩 보인다.
- 수정 방향: n8n이 실제로 전달하는 필드에서 읽는다: `var startNo = Number(structured.start_index) || Number(structured.context && structured.context.last_result_start) || 1;` 로 바꾸고, chat.js:226의 게이트도 동일한 해석 결과가 숫자일 때로 바꾼다(러너 assistant.py:2904가 쓰는 기준값과 같아진다). 근본 수정은 n8n '조회 및 질문 응답' 노드 화이트리스트에 start_index와 choices를 추가하는 것 — 그러면

## R3. [High / 고쳤다는데 안 고쳐짐] '이번 달' 마감 조회가 1일~어제 마감을 조용히 버린다 — 주 범위 통일 수정이 달에는 적용되지 않음

- 위치: `runner/claude-work-assistant/assistant.py:953`
- 재현: 1) 오늘=2026-07-16 기준으로 챗봇에 '이번달 마감인 작업 전부 보여줘' 전송.
2) 반환된 last_query.due_filter.start를 확인 → "2026-07-16"(오늘)이지 "2026-07-01"이 아님.
3) 모순 확인: 프로브4에서 확인된 실제 티켓 '[SDDC 구성] 호스트 관리, 워크로드 도메인 구성, 클러스터 구성 화면 개발'(id 388c5c5a-5684-80f5-b487-f2407030c7de, status=진행, priority=높음, due_date=2026-07-14)은 미완료이고 2026년 7월 마감인데, '이번달' 목록(07-16~07-31)에는 없음. 그러나 parse_date_range('이번주 마감 티켓', 2026-07-16) = 07-13~07-19(te
- 기대: '이번달 마감' 조회는 라벨과 일치하게 그 달 전체(2026-07-01~2026-07-31)를 대상으로 해야 한다. 이번 주 정책(이미 지난 마감도 그 기간 마감으로 센다)과 동일해야 하고, 지난달·다음달이 전체 기간인 것과도 일치해야 한다. 미완료 상태로 이번 달 초에 마감이 지난 티켓(가장 급한 연체 건)이 '이번 달' 목록에서 빠지면 안 된다.
- 실제: start=today로 잘려 2026-07-01~07-15 마감이 조용히 사라지는데 헤더는 여전히 '이번 달'이라고 표시한다. 사용자는 조건이 축소된 사실을 알 수 없고, 그 달에 이미 연체된 미완료 티켓을 놓친다. '이번 주'로 물으면 나오고 '이번 달'로 물으면 안 나오는 모순이 발생.
- 수정 방향: assistant.py:952-955를 지난달/다음달과 같은 전체 달 범위로 통일:

    if "이번달" in n or "금월" in n:
        start = today.replace(day=1)
        end = next_month - timedelta(days=1)
        return {"mode": "BETWEEN", "start": start.isoformat(), "end": end.isoformat(), "label": "이번 달"}

'이번달까지'처럼 오늘 이후만 원하는 표현은 이번주까지(92

## R4. [High / 신규 발견] '내 미완료 작업 몇 건이야?'가 전체 티켓 수를 내 것처럼 답한다 (조건 침묵 강등)

- 위치: `assistant.py:2503`
- 재현: ssh cloviradmin@10.100.64.71 로 웹훅 프로브 2회: (1) message='내 미완료 작업 몇 건이야?' conversation_id=ra-n8n-audit-001 (2) message='전체 미완료 작업 몇 건이야?' conversation_id=ra-n8n-audit-002. 두 응답의 total/response_text/context.last_query.scope 비교.
- 기대: '내'가 붙었으므로 scope=MY_TICKETS(또는 assignee_filter=본인)로 요청자 담당 미완료 건수만 세고, 응답 문구도 '내게 할당된 …'임이 드러나야 한다. 담당자를 특정하지 못하면 침묵 강등 대신 되물어야 한다.
- 실제: scope=ALL_TICKETS / assignee_filter=null 로 조용히 강등되어 전사 미완료 214건을 '조건에 맞는 티켓 완료 제외: 214건입니다.'로 답한다. '내'라는 조건이 버려진 사실이 응답 어디에도 없어, 사용자는 자기 업무가 214건이라고 믿는다. 챗봇에서 가장 흔한 질문 형태라 영향이 크다.
- 수정 방향: 토큰 부분일치 목록(2503행) 대신 '내/나/제/저' 1인칭 지시어 + 작업명사(이미 공유 집합이 있다)를 앵커 기반으로 판정하도록 바꾼다. 최소한 else(2517행)에서 ALL_TICKETS로 떨어지기 전에 1인칭 표지가 있으면 MY_TICKETS로 승격하고, 스코프가 추론된 경우 response_text에 '전체 기준'임을 명시한다.

## R5. [High / 신규 발견] 티켓 생성(CREATE) 쓰기 실패 시 안내한 '재시도'가 러너에 없어 영구 교착

- 위치: `ClovirONE_AI_Work_Assistant_v7.json:420`
- 재현: 티켓 생성 승인('예') → Notion /v1/pages 호출 실패(권한/레이트리밋/타임아웃; 노드는 continueOnFail=true) → n8n이 WRITE_ERROR와 함께 "다시 시도하려면 '재시도'" 안내 → 사용자가 '재시도' 입력 → 러너 4113행 CREATE 분기에서 is_approval_message('재시도',{kind:'CREATE'})=False(3813~3816: 재시도는 UPDATE 전용) → claude_query로 빠져 잡담 답변. 사용자가 '등록해줘'로 재시도 → 3463행 dispatched_at 가드 → "이미 처리하는 중입니다 … '재시도'라고 말씀해주세요" → 무한 루프.
- 기대: 쓰기 실패 후 안내한 복구 명령이 실제로 동작해 티켓이 생성되거나, 최소한 실패를 정직하게 알리고 초안을 다시 승인받는 경로가 있어야 한다.
- 실제: CREATE/COMMENT 실패는 복구 불가다. n8n이 '재시도'를 광고하지만 러너는 UPDATE에만 구현했고, dispatched_at 가드가 CREATE에서 해제되지 않아 '등록해줘'조차 막힌다. 두 안내가 서로를 가리키는 교착이라 티켓은 끝내 생성되지 않는다. 덤으로 COMMENT 실패에는 pending_question='approval' + "승인 대기 중인 티켓 초안을 유지했습니다"라는 사실과 다른 문구가 나간다(초안이 없다).
- 수정 방향: n8n 'Notion 변경 결과'에서 pending_question을 kind별로 정확히 설정하고(CREATE/COMMENT도 'write_retry'), 실패 시 pending_action에서 dispatched_at을 제거해 러너 가드를 풀어준다. 또는 러너 4113행 CREATE 분기에 UPDATE와 동일한 retry_asked 처리(dispatched_at 제거 후 handle_confirmation 재호출)를 추가하고 3816행 재시도 승인어를 CREATE/COMMENT에도 허용한다. 문구는 kind별로 분기한다.

## R6. [High / 회귀(이번 수정이 깨뜨림)] 'Notion 변경 결과'가 dedupe_key를 전달하지 않아 쓰기 경로의 재전송 방지가 완전히 죽었다

- 위치: `ClovirONE_AI_Work_Assistant_v7.json:420`
- 재현: 플랫폼이 같은 message_id로 재전송하는 경로가 실재한다(app/jobs/handlers/chat_message.py:110 `"message_id": payload["message_id"]`, 큐 재시도는 payload 그대로 재사용; app/chat/service.py:250-261 '다시 시도'도 message.message_id 유지). 승인 '예' → n8n이 Notion 티켓을 만들지만 응답이 n8n_timeout_seconds를 넘김 → 워커가 같은 message_id로 재시도 → '요청 전처리'가 processed['email|conv|msg-1']를 찾지만 저장은 'msg-1'로 되어 있어 MISS → 전 체인 재실행.
- 기대: 같은 요청자·대화·메시지의 재전송은 저장된 응답('티켓이 생성됐습니다 + 링크')을 그대로 되돌려줘야 한다(원래 dedupe의 목적).
- 실제: 쓰기 응답은 저장은 되나 절대 조회되지 않는다. 재전송이 전 체인을 다시 타고, 러너의 dispatched_at 가드(assistant.py:3463) 덕분에 티켓 중복 생성은 면하지만 사용자는 확인 문구와 Notion 링크 대신 "요청하신 작업을 이미 처리하는 중입니다" 또는 컨텍스트 동기화가 끝난 경우 무관한 잡담 답변을 받는다. 또한 이 message_id 키 항목들은 아무도 읽지 않는 쓰레기로 남아 500개 상한(`keys.slice(0, keys.length - 500)`)을 잡아먹어 살아있는 조합키 항목을 조기 축출한다.
- 수정 방향: 'Notion 변경 결과'의 두 return(WRITE_ERROR 분기와 성공 분기)에 `dedupe_key: decision.dedupe_key`를 추가한다. 방어적으로 '최종 응답 저장'에서 dedupe_key가 없으면 저장하지 말고(맨 message_id 폴백 제거) 경고를 남겨, 같은 결함이 조용히 재발하지 않게 한다.

## R7. [High / 고쳤다는데 안 고쳐짐] schedule run 재시도가 run-now 승인 게이트를 통째로 우회한다 (operator가 비활성·미승인 정의를 실행)

- 위치: `app/schedules/router.py:452`
- 재현: 임시 테스트(tests/regression/test_probe_r4b.py, 실행 후 삭제함)로 재현: (1) system_admin이 target_ref=APPROVED_URL 워크플로 스케줄 생성→enable(200). (2) run-now로 run 생성 후 run.status='failed'로 설정. (3) admin(승인 대상 역할)이 PUT으로 target_ref를 EVIL_URL 워크플로로 교체 → 이번 라운드 수정대로 응답의 enabled=False가 됨(게이트 닫힘). (4) 같은 admin이 POST /api/admin/schedules/runs/{run_id}/retry → **200**. (5) Worker.run_once() 실행 → fake_http 호출 기록 CALLED: ['htt
- 기대: retry_run도 run_now와 동일한 문을 통과해야 한다 — 비활성(=승인 게이트 미통과) 스케줄의 run은 409로 거절되어야 하고, 승인된 정의와 현재 정의가 다르면 실행되지 않아야 한다.
- 실제: retry_run이 enabled를 전혀 보지 않아 200을 반환하고, 승인된 적 없는 교체된 target_ref(EVIL_URL)로 실제 아웃바운드 호출이 나가 run이 succeeded로 종료된다. run_now/PUT 수정이 설치한 승인 게이트가 operator 권한으로 완전히 우회된다.
- 수정 방향: retry_run에서 `schedule = _get_or_404(db, run.schedule_id)` 직후 run_now와 같은 검사를 추가: `if not schedule.enabled: raise ConflictError("비활성 스케줄의 실행은 재시도할 수 없습니다. 먼저 활성화(승인)하세요.")`. 더 근본적으로는 '스케줄 실행 job을 만들 수 있는 유일한 경로'를 헬퍼 하나(예: schedules/service.py의 ensure_executable(schedule))로 모아 run_now·retry_run·schedu

## R8. [High / 고쳤다는데 안 고쳐짐] 문서 발행 승인이 승인자가 본 미리보기가 아니라 '승인 시점에 새로 렌더한 문서'를 발행한다 (+품질게이트 실패 시 침묵 중단)

- 위치: `app/approvals/service.py:267`
- 재현: 임시 테스트(tests/regression/test_probe_r4c.py, 실행 후 삭제함): approval_required=True 워크플로로 mode=preview_then_approve 생성 → 1차 preview는 정상 문서(title='승인자가 검토한 좋은 문서', source_row_count=12) → status=awaiting_approval. 승인 직전 fake_http 응답을 title='', body='', source_row_count=0으로 교체 → system_admin이 POST /approvals/{id}/approve → 200, approval status=approved. Worker.run_once() 후 출력: FINAL doc status: quality_fail
- 기대: 승인은 '승인자가 본 그 문서'에 대한 것이다. 승인 후에는 저장된 preview를 그대로 발행하거나, 재렌더가 불가피하다면 승인 스냅샷과 대조해 달라지면 STALE로 거절해야 한다. 어떤 경우에도 approved인데 발행이 조용히 사라지면 안 된다(침묵 강등 금지).
- 실제: 승인 후 preview가 한 번 더 호출되어 승인 대상 문서가 덮어써지고, 그 재렌더 결과가 발행된다. 재렌더가 품질게이트에 걸리면 approval=approved / job=succeeded / doc=quality_failed / published_ref=None으로 아무 알림 없이 끝난다. 승인 화면과 실제 결과가 불일치한다.
- 수정 방향: (1) 발행 job에 재렌더를 붙이지 않는다: payload에 {"generation_id":…, "publish_only": True}를 넣고 핸들러 최상단에서 publish_only면 preview 호출·게이트를 건너뛰고 저장된 gen.preview_json으로 바로 `_publish`로 진입. (2) 굳이 재렌더한다면 schedule.enable의 stale 검사와 같은 불변식 적용 — 새 preview가 승인 스냅샷과 다르면 ConflictError로 거절하고 gen.status를 되돌린다. (3) quality_failed

## R9. [High / 신규 발견] 삭제 차단 가드가 '담당자 제거·마감일 지우기' 같은 정상 변경까지 가로채고 잘못된 안내를 한다

- 위치: `runner/claude-work-assistant/assistant.py:4082`
- 재현: 실제 실행 확인(assistant.py를 import해 route_request 직접 호출, 티켓 tk1 '로그인 버그'는 요청자 본인 담당, 실제 스키마 사용):
1) route_request({"message": "이 티켓 담당자 제거해줘", context={selected_ticket: tk1, last_results:[tk1]}}) → action=UNSUPPORTED, response_text="티켓 삭제는 아직 채팅에서 지원하지 않습니다...", context.selected_ticket=None
2) 같은 문장을 update_ticket()에 직접 넘기면 → action=WRITE_UPDATE, "'로그인 버그' 티켓을 바로 변경합니다. - 티켓 담당자: 황형섭 → 미할당"
동일 재현: "로그인
- 기대: '담당자 제거/마감일 지우기'는 지원되는 필드 변경이므로 update_ticket으로 흘러가 미리보기 또는 직접 변경이 되어야 한다. 삭제 가드는 티켓 자체를 지우라는 요청('이 티켓 삭제해줘', '영구삭제')에만 걸려야 한다.
- 실제: '티켓/작업'이라는 낱말이 문장에 있기만 하면 필드 비우기 요청이 전부 '티켓 삭제는 지원하지 않습니다'로 거절되고, 지목해 둔 티켓(selected_ticket)까지 null로 날아가 후속 '그 티켓 ~' 지시도 깨진다. update_ticket의 "담당자제거" 처리 분기는 자연스러운 한국어 문장으로는 도달 불가능한 죽은 코드다.
- 수정 방향: 가드를 삭제 '대상'이 티켓 자체일 때로 좁힌다. 예: 필드 이름(_FIELD_NAME_RE: 제목·마감·시작일·우선순위·난이도·담당자·프로젝트)이 문장에 있으면 가드를 건너뛰고 update_ticket으로 보낸다. 또는 앵커 정규식으로 `(?:티켓|작업)(?:을|를)?\s*(?:영구)?(?:삭제|제거|지워)` 처럼 삭제 동사가 작업 명사에 직접 붙은 경우만 잡는다. selected_ticket을 null로 만드는 것도 삭제 요청이 실제로 성립할 때만 한다.

## R10. [High / 신규 발견] 댓글 쓰기에 소유권 검사가 없어 남의 티켓에 댓글을 쓸 수 있다(변경은 FORBIDDEN인데 댓글은 통과)

- 위치: `runner/claude-work-assistant/assistant.py:3408`
- 재현: 실제 실행 확인(tk2 '결제 오류 수정'의 담당자는 민지원, 요청자는 황형섭):
- comment_ticket('결제 오류 수정 티켓에 "이거 롤백하세요"라고 댓글 남겨줘', {}, [tk1, tk2]) → action=WRITE_COMMENT, write_request={"kind":"COMMENT","page_id":"tk2","body":{"parent":{"page_id":"tk2"},"rich_text":[{..."이거 롤백하세요"...}]}}
- 같은 티켓에 update_ticket("결제 오류 수정 티켓 완료로 바꿔줘", ...) → action=FORBIDDEN
또한 comment_ticket은 승인 단계도 없어("low-risk write — no approval step") 곧바로 n8n
- 기대: 쓰기 정책이 한 곳에서 정해져야 한다. 티켓 변경이 '본인 할당 티켓만' 정책이면 그 티켓에 대한 댓글 쓰기도 같은 검사를 통과해야 하거나, 정책상 댓글이 허용된다면 그 예외가 명시적으로 정의·문서화되어야 한다.
- 실제: 변경은 막히는 남의 티켓에 실제 Notion 댓글이 즉시 작성된다(고객 데이터에 남는 쓰기). 지시대명사·제목 일치만으로 대상이 잡히므로 남의 티켓 제목만 알면 누구나 댓글을 남길 수 있다.
- 수정 방향: comment_ticket에서 대상 확정 직후 update_ticket과 동일한 소유권 검사를 넣는다: `if not person_matches(safe_list(target.get("assignees")), current_user, requester.get("name",""), requester.get("email","")): return response("FORBIDDEN", ...)`. 이를 위해 route_request에서 comment_ticket에 current_user·requester를 넘겨야 한다(현재는 messag

## R11. [High / 신규 발견] 회사 이메일이 Notion 디렉터리와 '다른데도' 이름만 같으면 그 사람으로 매핑되어 남의 티켓을 변경할 수 있다

- 위치: `runner/claude-work-assistant/assistant.py:671`
- 재현: 실제 실행 확인:
- directory = build_directory([], [tk2]) → [{'id':'u-other','name':'민지원','email':'mjw@goodmit.co.kr','source':'ticket_assignee'}] (이메일이 이미 존재)
- match_person(directory, email='outsider@example.com', name='민지원') → ({'id':'u-other','name':'민지원','email':'mjw@goodmit.co.kr'}, quality='name')  ← 이메일이 명백히 다른데 매칭됨
- update_ticket("결제 오류 수정 티켓 완료로 바꿔줘", {}, requester={'email':'outsider@example.c
- 기대: 이름 폴백은 '디렉터리 항목에 이메일 정보가 없어서 매핑할 방법이 없을 때'의 최후 수단이어야 한다. 디렉터리 항목이 이메일을 가지고 있고 그것이 요청자 이메일과 다르면 그건 '정보 부족'이 아니라 '명백한 불일치'이므로 매칭을 거부해야 한다(현재 person_matches의 주석이 요구하는 바와 동일).
- 실제: 요청자 이메일이 Notion 디렉터리에 없기만 하면(아직 어떤 티켓·프로젝트에도 배정된 적 없는 신규 입사자 등) 표시 이름이 같은 기존 직원으로 매핑되어, 그 사람의 티켓을 조회·변경(WRITE_UPDATE 직접 쓰기)할 수 있다. 동명이인은 실제로 흔하며, diagnose()는 이 상태를 quality='name'으로 표시할 뿐 차단하지 않는다.
- 수정 방향: match_person의 이름 폴백에 이메일 충돌 검사를 넣는다: 후보 중 `clean_email(p.get("email"))`가 비어 있지 않고 요청자 이메일과 다른 항목은 제외하고, 남은(이메일 미상) 후보가 정확히 1명일 때만 매칭한다. 요청자 이메일이 있는데 이메일이 서로 다른 동명이인만 남으면 not_found로 돌려 수동 매핑(user-map.json) 안내를 하게 한다.

## R12. [High / 회귀(이번 수정이 깨뜨림)] residual_subject가 평범한 조회 요청을 '이름'으로 오해해 0건 + '못 찾음' 응답 — '내가 담당하는 티켓 보여줘'가 실패한다

- 위치: `assistant.py:1610`
- 재현: cd C:\Users\hshwa\clovirone-web-assistant\runner\claude-work-assistant && RUNNER_TOKEN=x PYTHONUTF8=1 python -c "import assistant as A; print(A.residual_subject('내가 담당하는 티켓 보여줘')); print(A.residual_subject('마감 임박한 티켓 알려줘'))"  # -> '내가담당하는', '임박한'. query_tickets로 동일 문장 실행 시 tickets=0 + '이름으로는 찾지 못했습니다'
- 기대: '내가 담당하는 티켓 보여줘'는 내게 할당된 미완료 티켓 목록(=‘내 티켓 보여줘’와 동일, 2건). '마감 임박한 티켓 알려줘'는 최소한 전체 미완료 목록이나 정직한 한계 안내.
- 실제: 둘 다 tickets=0 + "'내가 담당하는'이라는 이름으로는 티켓을 찾지 못했습니다" / "'임박한'이라는 이름으로는 티켓을 찾지 못했습니다". 존재하는 데이터를 없다고 답한다. '이름 못 찾으면 정직하게 안내' 수정이 조건 표현까지 이름으로 오인하면서, 얼버무림을 없애는 대신 정상 질의를 거짓 '없음'으로 바꿔놓았다.
- 수정 방향: (1) residual_subject 앞단에서 이미 해석 가능한 조건 어휘를 제거한다 — _CONSUMED_PHRASE_RE에 담당/할당/맡은/임박/지난/초과/없는/까지/끝내야/제외/포함 등 엔진이 이해하는 조건 표현과 그 관형형을 추가하거나, 더 안전하게 (2) '이름 추정'을 화이트리스트 방식으로 뒤집는다 — 조사·서술어를 제외하고 남은 조각이 실제 프로젝트명/티켓 제목 토큰과 겹칠 때만 keyword_is_guess를 세우고, 겹치지 않으면 기존대로 전체 목록 + 조건 미해석 고지. (3) 별도로 scope 분기(2500행)에

## R13. [High / 회귀(이번 수정이 깨뜨림)] 상태를 둘 이상 나열하면 마지막 하나만 남는다 — '계획과 진행 상태 티켓'이 진행만 보여준다(침묵 강등, 잘못된 데이터)

- 위치: `assistant.py:736`
- 재현: cd C:\Users\hshwa\clovirone-web-assistant\runner\claude-work-assistant && RUNNER_TOKEN=x PYTHONUTF8=1 python -c "import assistant as A; SM={A.norm(a):c for c,al in A.STATUS_ALIASES.items() for a in [c,*al]}; [print(m, A.resolve_status_intent(m,SM)['selected']) for m in ['계획과 진행 상태 티켓','진행중이거나 검증중인 티켓 보여줘','검증이랑 이슈 티켓']]"
- 기대: selected=['계획','진행'] (그리고 ['진행','검증'], ['검증','이슈']) — 사용자가 말한 상태 전부가 OR 조건으로 들어가야 한다.
- 실제: 각각 ['진행'], ['검증'], ['이슈'] — 앞쪽 상태가 통째로 사라진 채 결과만 나가고, 헤더가 남은 상태 하나만 표기해 사용자는 그게 요청 전부인 줄 안다.
- 수정 방향: _STATUS_ANCHOR_TEMPLATES에 접속 어미 앵커를 추가한다: r"@(?:인|된|중인|하는|중|한)?(?:이거나|거나|이랑|랑|와|과|또는|하고)" 와 r"@(?:인|된|중인|하는|중|한)?\s*," . 나열 문맥은 그 자체가 '상태를 말하는 자리'라는 앵커다. 대안으로 resolve_status_intent에서 앵커 매치가 1건이라도 성립하면(=이 문장이 상태를 말하는 문장임이 확정되면) 그 문장 안의 다른 상태 별칭도 어절 경계 기준으로 함께 인정하도록 2패스로 바꾼다.

## R14. [High / 신규 발견] extract_priority의 무앵커 폴백이 '중간 점검' 같은 평범한 제목어를 우선순위 필터로 둔갑시킨다

- 위치: `assistant.py:1264`
- 재현: cd C:\Users\hshwa\clovirone-web-assistant\runner\claude-work-assistant && RUNNER_TOKEN=x PYTHONUTF8=1 python -c "import assistant as A; [print(repr(m),'->',A.extract_priority(m)) for m in ['중간 점검 티켓 보여줘','높은 확률로 지연될 티켓','보통 수준으로 진행하면 될 것 같아요']]"
- 기대: '중간 점검 티켓 보여줘'는 priority='' 이고 '중간 점검'이 제목 키워드로 검색되어야 한다. 단답 폴백은 봇이 우선순위를 되물은 직후(pending_question='priority')에만 적용되어야 한다.
- 실제: 우선순위=중간 필터가 조용히 걸려 무관한 티켓 3건이 '우선순위 중간' 헤더로 나간다. 생성 흐름에서는 제목 답변의 '보통/중간' 한 단어가 사용자가 지정한 적 없는 우선순위로 Notion에 기록된다.
- 수정 방향: 폴백을 문맥으로 좁힌다. extract_priority에 pending 인자를 받아(또는 별칭 전용 함수 extract_priority_answer(message)를 분리해) '봇이 우선순위를 물은 직후의 단답'일 때만 폴백을 쓰도록 한다 — 조회 경로(2432행)와 일반 필드 추출은 _PRIORITY_RE 앵커 매치만 인정. 폴백을 남긴다면 최소한 norm(message)가 별칭과 **완전히 같을 때**(n in _PRIORITY_BY_NORM)로 제한하고, '긴급'처럼 앵커 없이도 우선순위인 낱말은 별도 화이트리스트(_PRIOR

## R15. [High / 신규 발견] '기준으로' 그룹 요청이 집계로 인식되지 않는다 — 같은 파일 두 상수가 서로 다른 문법을 본다(침묵 강등)

- 위치: `assistant.py:1544`
- 재현: cd C:\Users\hshwa\clovirone-web-assistant\runner\claude-work-assistant && RUNNER_TOKEN=x PYTHONUTF8=1 python -c "import assistant as A; [print(repr(m), bool(A._GROUP_AXIS_RE.search(m)), repr(A.extract_group_by(m))) for m in ['담당자 기준으로 묶어줘','프로젝트 기준으로 집계해줘','담당자별로 묶어줘']]"
- 기대: '담당자 기준으로 묶어줘' -> group_by='assignee' (='담당자별로 묶어줘'와 동일). 두 상수가 같은 축 문법을 공유해야 한다.
- 실제: group_by='' 로 집계 요청이 조용히 사라지고 그냥 티켓 목록이 나간다. '담당자별 집계' 수정이 '별/별로' 어미에만 적용돼, 같은 뜻의 '기준으로'는 축 인식 쪽에서만 반쪽으로 반영됐다.
- 수정 방향: 축 접미사를 한 곳에서 공유한다. _GROUP_SUFFIXES = ('별로','별','기준으로','기준','단위로','마다') 로 확장하고 _GROUP_AXIS_RE를 이 상수로부터 생성한다: re.compile(r"(?:"+"|".join(a for a,_ in _GROUP_AXES)+r")\s*(?:"+"|".join(_GROUP_SUFFIXES)+r")"). extract_group_by도 norm(axis+suffix) 대신 이 정규식 매치 결과에서 축을 뽑아 쓰면 두 판정이 영원히 어긋날 수 없다.

## R16. [Medium / 신규 발견] 대화 이름 변경이 HTTP 실패를 성공으로 처리해, 저장되지 않은 제목을 헤더에 표시한다

- 위치: `app/static/js/chat.js:525`
- 재현: 1) 사이드바 대화의 ✎ 클릭. 2) 201자 이상 제목을 붙여넣고 Enter(또는 다른 탭에서 그 대화를 삭제한 뒤 이름 변경). 3) 서버는 422/404로 거절한다(DevTools Network에서 확인). 4) 화면에는 오류가 전혀 안 뜨고, 헤더 제목은 방금 입력한 값으로 바뀌며, 사이드바는 loadConversations()로 다시 그려져 예전 제목을 보여준다.
- 기대: 저장이 거절되면 그 사실을 사용자에게 알리고(오류 문구), 헤더 제목은 서버가 실제로 가진 값 그대로 둔다.
- 실제: 실패가 성공처럼 처리된다. 헤더에는 저장된 적 없는 제목이, 사이드바에는 예전 제목이 동시에 표시되어 두 곳이 서로 다른 값을 보여준다. 사용자는 이름이 바뀐 줄 안다.
- 수정 방향: save()를 async로 바꾸고 응답을 검사한다: `var r = await api(...); if (!r.ok) { errorEl.textContent = '이름을 변경하지 못했습니다 (오류 ' + r.status + ').'; loadConversations(); return; } var d = await r.json(); if (conv.id === currentConversationId) titleEl.textContent = d.conversation.title; loadConversations();` — 제목은 입력값이

## R17. [Medium / 신규 발견] 대화 삭제가 DELETE 응답을 확인하지 않아, 실패해도 열려 있던 채팅 화면을 지운다

- 위치: `app/static/js/chat.js:545`
- 재현: 1) 대화 A를 연다. 2) 서버를 잠시 멈추거나 DELETE가 5xx/403을 내는 상황을 만든다(예: 세션이 다른 탭에서 폐기되어 CSRF 토큰이 무효). 3) A의 🗑 → '예' 클릭. 4) 메시지 영역이 비워지고 제목이 '새 대화'로 바뀐다. 5) 그런데 사이드바에는 A가 그대로 남아 있다. 오류 안내는 없다.
- 기대: 삭제가 실패하면 그 사실을 알리고, 열려 있던 대화 화면은 건드리지 않는다.
- 실제: 삭제 실패인데도 사용자의 열린 채팅이 화면에서 사라진다. 사이드바에는 대화가 남아 있어 화면 두 곳이 모순되고, 사용자는 자기 대화가 지워졌다고 오해한다(loadConversations가 이번 라운드에 굳이 구분한 '서버 장애 ≠ 대화 없음' 원칙과 정면으로 어긋난다).
- 수정 방향: 응답을 검사한 뒤에만 로컬 상태를 비운다: `var r = await api(...); if (!r.ok) { errorEl.textContent = '대화를 삭제하지 못했습니다 (오류 ' + r.status + ').'; loadConversations(); return; }` 그 다음에 currentConversationId/titleEl/messagesEl 정리. 전체를 try/catch로 감싸 네트워크 오류도 문구로 알리고 행을 원상 복구(loadConversations)한다.

## R18. [Medium / 신규 발견] 관리자 콘솔 모바일 드로어를 닫을 방법이 없다 — 백드롭도 Escape도 없고 토글 버튼은 사이드바에 덮인다

- 위치: `app/static/css/admin.css:222`
- 재현: 1) 브라우저 폭을 860px 이하로 줄이거나 휴대폰으로 /admin 접속(#dashboard 상태). 2) ☰ 탭 → 드로어가 열린다. 3) ☰를 다시 탭 → 사이드바에 막혀 아무 반응 없음. 4) Escape → 반응 없음. 5) 오른쪽 빈 30% 영역 탭 → 반응 없음. 6) 사이드바에서 현재 활성 섹션(대시보드)을 탭 → 해시 동일 → hashchange 미발생 → 드로어가 계속 열린 채. 화면 70%가 가려진 상태에서 벗어나려면 원하지 않는 다른 섹션으로 이동하거나 페이지를 새로고침해야 한다.
- 기대: 채팅과 동일하게 ☰ 재탭·바깥 영역 탭·Escape 중 어느 것으로든 드로어를 닫을 수 있어야 한다.
- 실제: 드로어를 닫는 정상 수단이 전부 막혀 있고, 같은 섹션을 다시 누르면 영원히 열린 채 남는다. 콘텐츠 영역 70%가 가려진다.
- 수정 방향: 채팅의 해결책을 그대로 옮긴다(중복 구현이 아니라 동일 패턴 이식): (1) base_admin.html의 .admin-sidebar 바로 뒤에 `<div class="admin-sidebar-backdrop" id="admin-sidebar-backdrop" aria-hidden="true"></div>` 추가, (2) admin.css의 @media 블록에 `.admin-sidebar.open ~ .admin-sidebar-backdrop { display:block; position:fixed; inset:0; z-index:

## R19. [Medium / 신규 발견] '분기' 기간 표현이 미지원 — 기간 조건이 조용히 제목 키워드 검색으로 강등된다

- 위치: `runner/claude-work-assistant/assistant.py:885`
- 재현: 1) 챗봇에 '이번 분기에 끝내야 하는 일 몇 개나 남았어?' 전송.
2) action이 COUNT/TICKET_SUMMARY가 아니라 TICKET_LIST이고, 문장 전체가 티켓 '이름'으로 취급되어 0건 반환됨을 확인.
3) context.last_query가 null이라 후속 질문으로 이어붙일 수도 없음.
4) '이번 분기 마감 티켓 보여줘', '3분기에 끝내야 할 일' 등 다른 분기 표현도 동일.
- 기대: '이번 분기'는 2026-07-01~2026-09-30 기간 필터로 해석되고 '몇 개나'는 COUNT 연산으로 처리되어 건수를 답해야 한다. 최소한 지원하지 않는 기간 표현이라면 '분기 조회는 아직 지원하지 않습니다. 이번 달 기준으로 보여드릴까요?'처럼 미지원 사실을 밝히고 되물어야 한다(assistant.py:880-882 invalid_date의 '침묵 강등하면 조건이 사라진 전체 목록이 나온다' 원칙과 동일한 취지).
- 실제: 기간 조건이 아무 고지 없이 제목 키워드로 강등되어, 사용자에게는 마치 그런 이름의 티켓이 없는 것처럼 보인다. 0건이 반환되지만 실제로는 이번 분기 마감 미완료 티켓이 다수 존재한다(프로브5에서 7월 마감분만 27건 확인). 없는 데이터를 지어내지는 않아 Critical은 아니나, 사용자의 질문 의도가 통째로 사라지는 침묵 강등이다.
- 수정 방향: parse_date_range에 분기 분기(branch)를 이번달 처리(952) 앞에 추가:

    q_now = (today.month - 1) // 3
    def _quarter_range(qi: int, year: int) -> tuple[date, date]:
        sm = qi * 3 + 1
        start = date(year, sm, 1)
        end = (date(year, sm + 2, 28) + timedelta(days=4)).replace(day=1) - timedelta(day

## R20. [Medium / 신규 발견] 그룹 요약이 실행 불가능한 후속 명령 '프로젝트 없음 티켓 보여줘'를 안내한다 (조회 경로에 프로젝트 미지정 필터가 없음)

- 위치: `runner/claude-work-assistant/assistant.py:2811`
- 재현: 1) 챗봇에 '프로젝트별로 미완료 작업이 몇 건씩인지 정리해줘' 전송 → '■ 프로젝트 없음: 9건 ... 나머지 6건은 \'프로젝트 없음 티켓 보여줘\'로 볼 수 있습니다.' 안내를 받는다.
2) 안내대로 '프로젝트 없음 티켓 보여줘' 전송.
3) 조회 경로에 프로젝트 미지정 필터가 없으므로 나머지 6건을 볼 수 없다. norm/키워드 정리(1115, _PROJECT_QUERY_WORDS 1015-1023이 '프로젝트'·'티켓'·'보여줘'를 제거)를 거치면 '없음'만 남아 제목에 '없음'을 포함한 티켓을 찾는 keyword_is_guess 검색으로 흘러 0건이 된다.
- 기대: 시스템이 안내하는 후속 명령은 시스템이 실제로 수행할 수 있어야 한다. '프로젝트 없음' 버킷의 나머지 티켓을 볼 방법을 제시했다면 그 명령이 그 9건을 반환해야 한다.
- 실제: 챗봇이 스스로 실행할 수 없는 명령을 사용자에게 지시하는 막다른 안내(dead-end)다. 사용자는 집계로 9건이 있다는 것을 보고도 그 목록에 도달할 수 없다. 버킷명을 명령문에 그대로 문자열 보간하는 하드코딩 패턴이 원인이며, group_by=assignee의 다중 담당자 버킷('정현수, 이성진' → \'정현수, 이성진 티켓 보여줘\')에도 같은 구조적 위험이 있다(2796).
- 수정 방향: 두 가지 중 하나로 정합성을 맞춘다.
(A) 조회 경로에 미지정 필터를 추가한다 — query에 project_unassigned 플래그를 두고 2717 근처에 분기 추가:
    elif scope == "PROJECT_NONE_TICKETS":
        filtered = [t for t in filtered if not t.get("project_ids")]
의도 인식은 이미 있는 names_no_project()(3903)를 query_tickets 경로에서도 재사용해 중복 구현을 피한다.
(B) 안내를 실행 가능한 것

## R21. [Medium / 신규 발견] 대화 상태 동기화 실패 경고를 아무도 읽지 않는 필드에 넣고 삼킨다

- 위치: `ClovirONE_AI_Work_Assistant_v7.json:492`
- 재현: 러너(:8789)가 /v1/assistant/context/sync에서 오류를 내는 상태에서 티켓 생성 승인. '대화 상태 동기화'는 continueOnFail=true라 워크플로는 계속 진행되고, 응답 JSON에 state_sync_warning이 붙지만 채팅 화면에는 '티켓이 생성됐습니다'만 뜬다.
- 기대: 동기화 실패는 이후 대화가 깨진다는 뜻이므로 사용자·운영자 어느 쪽에든 보여야 한다. 검출해 놓고 표시하지 않는다면 검출하지 않은 것과 같다.
- 실제: 경고가 소리 없이 사라진다. 게다가 러너의 저장 컨텍스트에는 dispatch 시점 값(pending_action.dispatched_at + pending_question='write_in_progress')이 남아 있어, 이후 승인성 발화는 전부 assistant.py:3463 가드에 걸려 "이미 처리하는 중입니다"만 반복한다. 티켓은 이미 만들어졌는데 대화는 영구히 '처리 중'에 묶인다.
- 수정 방향: state_sync_warning을 response_text 말미에 덧붙여(또는 플랫폼 _TEXT_KEYS/renderStructured가 읽는 필드로) 반드시 노출한다. 동기화 실패 시 재시도(짧은 백오프 1~2회)를 하고, 그래도 실패하면 러너 컨텍스트가 write_in_progress에 갇히지 않도록 명시적 해제 경로를 둔다.

## R22. [Medium / 신규 발견] staticData에 1026건 원본 Notion 페이지 + 응답 500건을 쌓고 매 실행마다 통째로 다시 쓴다

- 위치: `ClovirONE_AI_Work_Assistant_v7.json:552`
- 재현: 라이브 프로브 응답(단순 COUNT)만도 844바이트이고 context가 528바이트를 차지한다. TICKET_LIST 응답은 티켓 객체 배열까지 실려 훨씬 크다. 이 응답 ×500 + 원본 티켓 1026건이 한 행에 들어간다. (서버 ~/.n8n/database.sqlite는 sudo 없이 읽을 수 없어 실제 blob 크기는 측정하지 못했다 — 크기 수치는 미확인, 구조는 코드로 확인.)
- 기대: staticData에는 재전송 판별에 필요한 최소 정보(키 + 작은 응답 요약)만 두고, 대용량 조회 캐시는 staticData가 아닌 곳(러너 측 캐시 등)에 두거나 바이트 상한을 둬야 한다.
- 실제: 조회 캐시(원본 Notion 페이지 1026건)와 응답 500건이 워크플로 staticData 한 곳에 쌓이고, 매 실행마다 전량 재직렬화·재기록된다. 요청당 고정 비용이 데이터 건수에 비례해 커지고, n8n DB 행이 계속 부풀며, 백엔드(플랫폼)가 이미 chatmsg:{client_message_id} 잡 멱등키로 같은 재전송을 막고 있어 책임도 중복된다.
- 수정 방향: processedMessages에는 dedupe_key와 응답 전문 대신 필요한 최소 필드만 저장하고 전체 인코딩 바이트 상한을 건다. workDataCache는 staticData에서 빼거나(러너/외부 캐시로 이전) 원본 페이지 대신 러너가 실제로 쓰는 정규화 필드만 담는다. 플랫폼 잡 멱등키와 n8n dedupe 중 하나로 책임을 일원화한다.

## R23. [Medium / 고쳤다는데 안 고쳐짐] 승인된 발행 job을 operator가 취소하면 문서가 awaiting_approval로 영구 wedge된다 (cancel 종결 처리가 pending만 커버)

- 위치: `app/jobs/router.py:153`
- 재현: (1) approval_required 워크플로로 preview_then_approve 문서 생성 → worker 1회 → gen.status='awaiting_approval', approval=pending. (2) admin이 approve → docpublish:{gen.id} job이 queued로 생성되고 gen.status는 여전히 'awaiting_approval'(probe test_probe_r4c에서 이 상태 확인함). (3) worker가 집기 전에 operator가 POST /api/admin/jobs/{job_id}/cancel → 큐 상태 검사(123)만 통과하면 취소됨 → _terminalize_linked_record가 gen.status='awaiting_approval'을 
- 기대: job.cancel은 그 job이 구동하던 레코드도 종결시켜 wedge를 남기지 않아야 한다 — gen은 failed(또는 취소 상태)로 내려가고 사유가 남아야 한다.
- 실제: gen.status가 awaiting_approval에 영구히 머문다. approval은 이미 approved라 다시 승인할 수도 없고, 문서 목록에는 '승인 대기'로 계속 보이지만 이를 진행시킬 경로가 없다. 화면 표시와 실제 상태가 어긋난다.
- 수정 방향: 153행을 `if gen is not None and gen.status in (STATUS_PENDING, STATUS_AWAITING_APPROVAL):`로 넓히고 error_message에 취소 사유를 남긴다. 근본적으로는 `_execute_document_publish`가 발행 job을 enqueue할 때 gen.status를 STATUS_PENDING으로 되돌려 '큐에 실려 있다'는 사실을 상태에 반영하게 하는 편이 더 정직하다(그러면 기존 ("pending",) 검사로도 커버된다).

## R24. [Medium / 신규 발견] 댓글 쓰기 실패 후 안내대로 '재시도'라고 해도 아무 일도 일어나지 않는다(handle_confirmation이 COMMENT를 모른다)

- 위치: `runner/claude-work-assistant/assistant.py:3452`
- 재현: 실제 실행 확인(pending_action={kind:COMMENT, ticket_id:tk1}, pending_question='approval', last_action={kind:COMMENT, success:False, error:'Notion 429'}):
- handle_confirmation(ctx, SCHEMA, [tk1], ME, REQ) → None
- route_request({"message": "재시도", context=위}) → action=FREEFORM_CHAT(일반 대화 LLM), write_request 없음
- route_request({"message": "응", context=위}) → action=FREEFORM_CHAT, write_request 없음
- route_r
- 기대: 실패 안내가 '재시도'를 제시했으면 '재시도'는 같은 댓글 쓰기(write_request kind=COMMENT, page_id, body)를 다시 내보내야 한다. UPDATE 실패 재시도는 route_request 4159행 부근에 구현돼 있다.
- 실제: '재시도'/'응'이 잡담 응답(claude_query)으로 새어 나가 댓글은 영영 달리지 않고, 사용자는 실패 사실만 안내받은 채 복구 경로가 없다. 안내 문구와 실제 동작이 어긋난다(핵심: 안내한 복구 경로가 존재하지 않음).
- 수정 방향: 두 곳 중 하나를 맞춘다. (a) pending에 body(또는 comment 원문)를 보관하고 handle_confirmation에 `if kind == "COMMENT":` 분기를 추가해 write_request={"kind":"COMMENT", "page_id": pending["ticket_id"], "body": ...}를 재발행하고, route_request의 pending 블록에 COMMENT 분기(재시도/승인/거절)를 추가한다. (b) 댓글을 재시도 불가로 유지한다면 n8n 실패 문구에서 COMMENT일 때는 '재시도

## R25. [Low / 고쳤다는데 안 고쳐짐] 만료된 승인이 목록에서는 'expired', 상세에서는 'pending'으로 표시된다 (같은 데이터, 화면별 결론 충돌)

- 위치: `app/approvals/router.py:67`
- 재현: 임시 테스트(tests/regression/test_probe_r4d.py, 실행 후 삭제함): admin이 스케줄 enable 요청 → 202 + approval(pending) 생성. DB에서 approval.expires_at를 fake_clock.now()-1h로 백데이트 후 커밋. 같은 세션으로 조회하면 출력이 'LIST status  : expired' / 'DETAIL status: pending'. 두 응답이 같은 행에 대해 다른 상태를 말한다.
- 기대: 만료 판정은 표시 계층의 단일 규칙이어야 한다 — 목록·상세 어디서 봐도 만료된 pending은 'expired'로 보이고, 결정 가능한 것처럼 보이지 않아야 한다.
- 실제: 상세 화면은 'pending'으로 표시해 승인/거절 버튼이 살아 있는 것처럼 보이지만, 실제로 누르면 _ensure_decidable(service.py:114)이 '만료된 승인 요청입니다' 409를 던진다. 목록에서 expired로 본 사람과 상세에서 pending으로 본 사람의 결론이 갈린다.
- 수정 방향: router.py의 get_approval에 Request를 받아 `approval_view(get_approval_or_404(db, approval_id), request.app.state.clock.now())`로 now를 전달한다. 재발 방지를 위해 approval_view의 now를 선택 인자가 아닌 필수 인자로 바꾸면 호출부 누락이 구조적으로 불가능해진다.

## R26. [Low / 고쳤다는데 안 고쳐짐] schedule run 재시도가 started_at을 초기화하지 않아 실행 소요시간이 이전 실패 시도까지 포함해 표시된다

- 위치: `app/schedules/router.py:462`
- 재현: (1) 스케줄 enable 후 run-now로 run 생성, 워크플로 호출을 실패시켜 run.status='failed', started_at=T1, finished_at=T2로 만든다. (2) 몇 시간 뒤 POST /api/admin/schedules/runs/{run_id}/retry → finished_at=None, status='queued'가 되지만 started_at은 T1 그대로. (3) worker가 T3에 실행 → 핸들러의 `run.started_at or now`가 T1을 유지 → run.finished_at=T4. 콘솔의 실행 이력은 T1~T4(실패 후 방치된 시간 포함)를 이 재시도의 소요시간으로 보여준다.
- 기대: 재시도는 새 실행이다 — job 재시도와 동일하게 started_at을 지워 이번 시도의 실제 소요시간만 표시되어야 한다.
- 실제: started_at이 이전 실패 시도의 값으로 남아, 운영 화면의 실행 소요시간이 실제보다 임의로 크게(대기 시간 포함) 표시된다. 성능 판단·타임아웃 조사에 잘못된 데이터가 들어간다.
- 수정 방향: retry_run에서 `run.finished_at = None` 옆에 `run.started_at = None`, `run.response_summary = None`을 추가한다. 겸사겸사 462행의 하드코딩 문자열 `run.status = "queued"`를 app/schedules/models의 RUN_QUEUED 상수로 바꾼다(같은 파일이 RUN_FAILED는 상수로 쓰고 있어 일관성이 깨져 있다).
