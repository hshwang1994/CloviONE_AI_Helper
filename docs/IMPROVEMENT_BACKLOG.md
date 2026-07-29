# 개선 백로그 (디스커버리 결과, 2026-07-15)

> IMPROVEMENT_DIRECTIVE 기반 4축 갭 분석 결과. 완료 시 [x] 처리하고 BUILD_LOG에 기록.

**[query]** 조회 축 갭 분석(러너 규칙 엔진 query_tickets vs 지시서 §3.1 매트릭스). 규칙 엔진은 담당자 관계·프로젝트·상태·마감일 기간·우선순위·난이도·따옴표 검색어·4종 정렬·페이징·조건 승계/해제까지 조합 필터를 견고하게 지원한다(assistant.py:1963-2308). 그러나 (1) 관계 축 중 '생성/요청/참여'는 데이터 모델(normalize_ticket:580-599)에 필드 자체가 없고 스코프 토큰(2017-2047)에도 없어 "내가 만든 티켓" 류가 ALL_TICKETS로 침묵 강등되어 전체 목록 오답을 내며(지시서 원칙4 위반), (2) LLM(claude_query)이 last_query를 {"kind":"freeform"}으로 남기는데 '더 보여줘' 분기(2009-2013)가 이를 검사하지 않아 무관한 전체 티켓 2페이지를 반환한다 — 이 둘이 사용자가 즉시 체감하는 P0. 그 외 시작일 기간 축 부재, SUMMARY 연산이 계산만 되고 LIST로 폴스루(그룹화 미구현), 상대 날짜 커버리지 비대칭(지난주/어제/지난달 미인식→무필터 전체 반환)과 규칙·LLM 간 §8.3 해석 기준 불일치, FREEFORM_MARKERS("알려줘/어떤/가장")가 정형 질의를 LLM으로 뺏어가는 경계 문제(같은 질의가 표현 하나로 다른 엔진·다른 수치), 무따옴표 검색어 미인식, 페이지 크기 10 고정·정렬 축 부족이 확인됐다. 결과 0건(라벨 포함 안내)·대량 건(10건 페이징+더보기)·담당자 NOT_FOUND/AMBIGUOUS 처리는 양호.

**[mutate]** runner/claude-work-assistant/assistant.py(3541줄) 전문과 BUILD_LOG의 n8n 캐시/쓰기 경로 이력을 검토한 결과, 생성·변경·삭제 축에서 8건의 갭을 확인했다. 쓰기 경로(update_property_body/build_create_body)는 Notion 페이지 properties PATCH만 지원하므로 제목 변경·프로젝트 이동·시작일은 기존 전송로(write_request)로 즉시 확장 가능하지만 현재 매핑에 없고, 본문(blocks)·댓글·삭제(archive)는 n8n에 새 노드가 필요하다. 즉시 체감 결함(P0) 3건: ①'시작일' 변경 요청이 마감일에 직접 기록됨(오기록) ②'제목을 X로 바꿔줘'가 X 안의 상태어에 걸려 진행상태를 직접 변경하거나, 아니면 "어떤 값을 변경할지 알려주세요"라는 동문서답 ③LLM 대화 경로(claude_query)가 last_results를 갱신하지 않아 그 목록에 대한 '두 번째 티켓' 참조가 이전 목록이나 빈 컨텍스트로 해석됨. 삭제(3.4)는 미지원인데 정직 안내 대신 일반 변경 재질문이 나가고, 일괄 변경·실행 후 재조회(§9.3)·댓글·본문 변경은 부재. 이미 완료된 항목(대화형 폴백, 캐시, 이미지, 버그사냥 13건 등)과 중복 없음.

**[ui]** 화면/추천/표시 축에서 8건의 갭을 확인했다(실코드 검증 기준). 데이터 흐름은 러너 response()→n8n→worker가 응답 JSON 전체를 structured_payload_json으로 저장(chat_message.py:152)→chat.js renderStructured로 이어지며, 러너 필드가 프런트에 그대로 도달함을 확인. 최대 결함(P0)은 renderCard가 assignee/project 단수 키를 읽는데 러너는 assignees/project_names 배열만 내보내 담당자·프로젝트가 모든 티켓 카드에서 항상 누락되는 필드명 불일치 — 지시서 7.1의 필수 표시 항목 5개 중 2개가 죽은 코드다. P1은 (a) LLM 경로(claude_query) 카드의 url 누락으로 경로별 표시 불일치, (b) 목록 텍스트와 카드의 완전 중복 렌더(모바일 체감 큼), (c) 카드 상세 진입·더보기·후속작업 부재(러너는 이미 지원, UI 진입로만 없음), (d) quick prompts 조회 편중·정적 하드코딩·권한 미반영, (e) 프로젝트 카드에 담당 정/부·티켓 수·진행률 부재(티켓 수는 러너가 계산 자체를 안 함). P2는 프로젝트 시각 구분(7.2, 해시 기반 결정적 색상 제안)과 확인/선택 흐름의 버튼화. 모바일 자체 레이아웃(드로어·백드롭·viewport)은 정상이며 모바일 문제의 실체는 텍스트+카드 중복(P1-b)이다. 완료 처리된 선행 작업(대화형 폴백, 이미지 파이프라인, 캐시 등)과 중복되는 제안은 없음.

**[accuracy]** 실코드 정독 결과(assistant.py 전문, chat_message.py, chat/service.py, chat.js), 지시서 축(정확도/맥락/오류) 기준 갭 8건. 핵심 결함 2건: (1) 대화형 폴백(claude_query)이 참조 티켓을 last_results에 기록하지 않아 직후 "두 번째 티켓" 참조가 스테일 목록으로 해석됨, (2) 페이지네이션 후 번호 참조의 page-relative 폴백이 화면의 전역 번호와 충돌해 엉뚱한 티켓을 '직접 쓰기'로 변경할 수 있음. 구조 갭: 규칙 엔진은 구조화된 last_query를 남기지만 LLM 경로는 남기지 않아 후속 조건 수정이 전체 티켓으로 리셋(6장 이원 구조의 실질 비용), CREATE 모드 고착으로 생성 중 조회/주제 전환 불가. 오류 축: LLM에 800건 초과 데이터 잘림 미고지(8.1), n8n 실패가 사용자에게 "실패" 배지+재시도 버튼만으로 표시되어 원인·다음 행동 안내 부재(11장).

## 갭 목록 (우선순위순)

### 1. [P0/accuracy/S] 대화형 답변(claude_query)이 last_results를 기록하지 ✅완료(3.5.0/3.6.0) 않아 후속 번호/지시 참조가 스테일 목록으로 해석됨
- 현재: claude_query(assistant.py L1872-1939)는 LLM이 고른 ref_tickets를 응답 extra(tickets=)로만 내보내고, new_context에는 last_query({kind:'freeform'})와 conversation_history만 저장한다(L1934-1938). last_results/last_result_start/selected_ticket은 갱신되지 않으므로, LLM이 티켓을 열거한 직후 사용자가 "두 번째 티켓 상세/완료 처리해줘"라고 하면 resolve_ticket_reference(L2311)가 이전 규칙 조회의 낡은 last_results 인덱스로 해석해 다른 티켓을 조회·변경할 수 있다(변경은 규칙 파싱 시 직접 쓰기).
- 제안: claude_query가 ref_tickets가 있을 때 new_context에 last_results=[id...], last_result_start=1, selected_ticket(1건일 때)을 함께 기록. ref_tickets가 없으면 기존 last_results를 명시적으로 pop해 스테일 참조를 차단(또는 last_results_at 세대 표식 추가). 회귀 테스트: 규칙 조회→freeform 질문→"두 번째 완료 처리" 시나리오에서 대상 불일치가 없어야 함.
- 파일: runner\claude-work-assistant\assistant.py

### 2. [P0/accuracy/M] 페이지네이션 후 번호 참조의 page-relative ✅완료(3.5.0/3.6.0) 폴백이 화면의 전역 번호와 충돌 — 잘못된 티켓을 직접 변경 가능
- 현재: 목록은 전역 번호(offset+idx, L2297)로 표시되는데 resolve_ticket_reference(L2314-2323)는 전역 해석 실패 시 1..len(last_ids)의 page-relative 폴백을 수행한다. '더 보여줘'로 2페이지(last_result_start=11)를 본 뒤 사용자가 화면에 남아 있는 1페이지의 "3번 완료 처리해줘"를 입력하면 local_index=-8로 실패한 후 폴백이 2페이지의 3번째(화면 표기 13번) 티켓을 반환하고, 규칙 파싱된 상태 변경은 확인 절차 없이 직접 쓰기(update_ticket L2693-2715)로 실행된다.
- 제안: 번호가 현재 페이지 범위(page_start..page_start+len-1) 밖이면 폴백으로 다른 티켓을 고르지 말고 (a) 세션에 페이지 누적 맵(shown_index→ticket_id)을 유지해 이전 페이지 번호도 정확히 해석하거나, (b) 최소한 NEED_INPUT으로 '현재 목록은 N~M번입니다. 대상을 다시 지정해주세요'라고 되묻는다. 폴백 유지가 필요하면 UPDATE 경로에서는 폴백 결과를 확인 미리보기(needs_confirmation)로 강등.
- 파일: runner\claude-work-assistant\assistant.py

### 3. [P0/mutate/M] '시작일' 변경 ✅완료(3.5.0/3.6.0)·지정 요청이 마감일로 오기록됨 (필드 오인 직접 쓰기)
- 현재: parse_date_range()는 문장 안의 날짜 표현만 찾고 어떤 필드를 향한 것인지 구분하지 않는다. update_ticket()(assistant.py:2463~2477)은 그 결과를 무조건 changes['due_date']에 넣고, 규칙 파싱 값이므로 확인 절차 없이 direct=True로 즉시 Notion에 쓴다. 즉 "시작일을 다음 주 월요일로 바꿔줘"가 마감일을 덮어쓴다. create_ticket()(2813~2815행)도 동일하게 "시작일은 내일"을 due로 흡수한다. DB에 '시작일' 속성이 존재하고 읽기(normalize_ticket 593행 start_date)는 되지만, build_create_body specs(1387~1395행)와 update_property_body mapping(1423~1429행) 어디에도 시작일이 없어 쓰기는 불가능하다.
- 제안: ① parse_date_range 호출 전 문장에서 날짜의 앵커 필드를 판별(마감/기한→due, 시작→start; 앵커 없으면 기존대로 due). ② update_property_body mapping과 build_create_body specs에 start_date→['시작일'] 추가(property_value의 date 타입 재사용이라 전송로 변경 불필요). ③ '시작일' 앵커가 있는데 값 파싱 실패 시 되묻기. 회귀 테스트: "시작일을 X로"가 due_date를 건드리지 않음을 고정.
- 파일: runner\claude-work-assistant\assistant.py, runner\claude-work-assistant\test_assistant.py

### 4. [P0/mutate/M] 제목 변경·프로젝트 이동 ✅완료(3.5.0/3.6.0) 미지원 + 제목 문구가 상태 변경으로 오발사
- 현재: update_property_body(1421~1443행)는 status/due_date/priority/difficulty/assignee_ids 5개만 매핑한다(지시서 3.3의 제목 변경·프로젝트 이동 부재). "제목을 X로 바꿔줘"는 is_update_intent에 걸려 update_ticket으로 가지만, detect_target_status(2353~2366행)의 방향격 정규식이 캡처한 X 구절 안에 상태 별칭이 부분 포함되면(예: "제목을 서버작업진행상황으로 바꿔줘"의 '진행') 진행상태를 확인 없이 직접 변경한다. 상태어가 없으면 UPDATE_EXTRACT_SCHEMA(2369~2381행, 제목 필드 없음)도 빈손이라 "어떤 값을 변경할지 알려주세요"(2587~2592행)라는 동문서답이 나간다. 프로젝트 이동("이 티켓 B 프로젝트로 옮겨줘")도 동일. property_value()는 title·relation 타입을 이미 지원하므로 n8n write 경로(properties PATCH)로 둘 다 지원 가능하다.
- 제안: ① update_property_body mapping에 title→['제목'], project_ids→['프로젝트'](relation) 추가. ② update_ticket에 '제목(을/를) …로' 및 '…프로젝트로 이동/옮겨' 규칙 추출 + UPDATE_EXTRACT_SCHEMA에 title/project_name 필드 추가(프로젝트명은 resolve_project로 검증, 모호하면 후보 제시). ③ detect_target_status의 방향격 매칭에서 '제목' 앵커가 선행하는 구절은 제외. ④ 제목·프로젝트 변경은 전/후 표시 미리보기 후 확인(needs_confirmation) 경유.
- 파일: runner\claude-work-assistant\assistant.py, runner\claude-work-assistant\test_assistant.py

### 5. [P0/mutate/S] LLM 대화 경로(claude_query)가 last_results를 남기지 ✅완료(3.5.0/3.6.0) 않아 '두 번째 티켓' 참조가 어긋남
- 현재: claude_query(1934~1939행)는 답변에 근거한 ref_tickets를 표시용으로만 반환하고 new_context에는 last_query(kind=freeform)와 conversation_history만 저장한다. last_results/last_result_start/selected_ticket은 갱신되지 않는다. FREEFORM_MARKERS('정리','알려줘','가장' 등)에 걸린 목록형 답변(예: "내 티켓 정리해줘") 직후 "두 번째 티켓 완료 처리해줘"는 resolve_ticket_reference(2311~2323행)가 이전 규칙 조회의 낡은 last_results(또는 빈 값)로 해석 → 사용자가 방금 본 목록과 다른 티켓을 대상으로 직접 쓰기까지 갈 수 있다(소유권 검사는 통과 가능). 지시서의 '맥락 참조 정확성' 요건과 정면 불일치.
- 제안: claude_query가 ref_tickets를 반환할 때 new_context에 last_results=[id...], last_result_start=1, (1건이면 selected_ticket)을 함께 기록하고, LLM 답변의 표시 순서와 ticket_ids 순서가 일치하도록 QUERY_PROMPT에 '목록으로 답할 때 ticket_ids를 표시 순서대로' 지침 1줄 추가. 잡담(ticket_ids 빈 배열)일 때는 기존 last_results를 보존해 무관한 잡담이 참조 컨텍스트를 지우지 않게 한다. 회귀 테스트: freeform 목록 후 번호 참조가 그 목록을 가리키는지 고정.
- 파일: runner\claude-work-assistant\assistant.py, runner\claude-work-assistant\test_assistant.py

### 6. [P0/query/M] 관계 축 '생성자 ✅완료(3.5.0/3.6.0)/요청자/참여자' 부재가 침묵 오답(전체 티켓)으로 강등됨
- 현재: "내가 만든 티켓 보여줘", "내가 요청한/참여한 티켓"은 스코프 토큰(assistant.py:2017-2047)에 매칭되는 것이 없어 else 분기의 scope=ALL_TICKETS로 떨어지고, '전체 티켓 (완료 제외): 총 N건' 전체 목록을 반환한다. normalize_ticket(580-599)은 Notion page의 created_by/created_time을 추출하지 않고, '요청자/참여자' 속성은 작업 DB에 존재하지 않는다. 지시서 원칙4(없으면 없다고)와 정면 충돌 — 사용자는 자기가 만든 티켓이라 믿고 전체 목록을 받는다.
- 제안: 1) normalize_ticket에서 페이지 레벨 created_by(id)·created_time 추출(n8n이 전체 page 객체를 넘기는지 payload 확인 필요 — 안 넘기면 n8n 워크플로에 필드 추가). 2) query_tickets 스코프 감지에 '내가만든/내가생성한/내가등록한' → MY_CREATED 스코프 추가(created_by == current_user.id 필터). 3) '요청한/참여한'은 필드가 없으므로 정직 안내 분기 추가: "작업 DB에 요청자/참여자 필드가 없어 이 조건으로는 조회할 수 없습니다. 담당자 기준(내 티켓)으로 보시겠어요?" — ALL_TICKETS 강등 금지. 테스트: 생성자 스코프 3건 + 미지원 축 정직 응답 2건.
- 파일: runner\claude-work-assistant\assistant.py, runner\claude-work-assistant\test_assistant.py

### 7. [P0/query/S] LLM 답변 직후 '더 보여줘 ✅완료(3.5.0/3.6.0)'가 무관한 전체 티켓 2페이지를 반환
- 현재: claude_query는 last_query를 {"kind": "freeform", "message": ...}로 저장한다(assistant.py:1936). '더 보여줘'는 is_query_intent로 규칙 엔진에 들어오고, 더보기 분기(2009-2013)는 last_query의 kind를 검사하지 않고 deepcopy 후 offset=10을 설정한다. scope=None이라 어떤 스코프 필터에도 안 걸리고 statuses/exclude_completed/due_filter 키가 전부 없어 완료 포함 전체 티켓이 DUE_ASC로 정렬돼 '티켓: 총 N건'의 11~20번째가 표시된다. 예: "긴급한 티켓 알려줘"(LLM) → "더 보여줘" → 방금 답변과 무관한 전체 목록.
- 제안: 더보기 분기 진입 시 last_query.get("kind") == "freeform"이면 (a) claude_query로 재라우팅해 대화 맥락(conversation_history)으로 이어 답하게 하거나, (b) "직전 답변은 목록 조회가 아니어서 이어서 표시할 수 없습니다. 조회 조건을 말씀해주세요"로 정직하게 안내. 추가로 claude_query가 ref_tickets의 id를 last_results에 저장하면 '두 번째 티켓 상세' 같은 후속 참조도 이어진다. 회귀 테스트: freeform 후 더보기 1건.
- 파일: runner\claude-work-assistant\assistant.py, runner\claude-work-assistant\test_assistant.py

### 8. [P0/ui/S] 티켓 카드에 담당자 ✅완료(3.5.0/3.6.0)·프로젝트가 절대 표시되지 않음 (필드명 불일치)
- 현재: renderCard(chat.js:91-94)는 item.assignee, item.project(단수 문자열)를 읽지만, 러너는 assignees(사람 dict 배열, assistant.py:595) 또는 이름 문자열 배열(_slim_ticket_for_query, assistant.py:1843)과 project_names(배열, assistant.py:597/1845)만 내보낸다. 두 키를 만드는 코드가 러너 어디에도 없어 이 표시 경로는 죽은 코드다. 결과: 지시서 7.1이 요구하는 '제목·프로젝트 배지·상태·담당·마감' 중 담당자와 프로젝트가 모든 티켓 카드에서 항상 빠진 채 렌더된다(제목/상태/우선순위/마감/링크만 표시).
- 제안: renderCard가 두 형태를 모두 처리: assignees가 배열이면 각 원소가 dict면 name||email, 문자열이면 그대로 join(', '), project_names 배열을 join해 프로젝트 행으로 표시. 기존 assignee/project 단수 키도 폴백으로 유지. 프로젝트 카드용으로 primary/secondary(사람 배열)도 같은 헬퍼로 처리. tests/ 프런트 검증은 node --check + 회귀 시나리오(WORK_SUMMARY/TICKET_LIST 응답 fixture)로 확인.
- 파일: app\static\js\chat.js

### 9. [P1/accuracy/M] 질의 구조화의 이원 구조: LLM 경로는 구조화 질의를 남기지 않아 후속 조건 수정이 전체 티켓으로 리셋됨 (지시서 6장) ✅완료(3.8.0)
- 현재: 규칙 엔진(query_tickets)은 scope/statuses/due_filter/assignee_filter 등 재사용 가능한 last_query를 남기지만, claude_query는 last_query={kind:'freeform', message}만 남긴다(L1936). freeform 답변 뒤 "완료 제외"·"몇 개야" 같은 후속(is_query_followup=True)이 오면 query_tickets가 deepcopy(last_query)에서 scope=''를 얻어 어떤 scope 분기에도 걸리지 않아 사실상 전체 티켓 기준으로 계산한다(L2041-2046, L2180-2192) — 사용자가 방금 본 부분집합과 무관한 수치가 나온다. 이것이 6장이 지적한 휴리스틱+LLM 이원 구조의 실질 비용이다.
- 제안: QUERY_SCHEMA에 structured_filter(scope/statuses/project_ids/assignee/due_range/keyword) 필드를 추가해 LLM이 자신이 적용한 필터를 선언하게 하고, 이를 규칙 엔진의 last_query 형식으로 변환·저장해 두 경로가 하나의 질의 표현을 공유하게 한다. 과도기 조치로는 last_query.kind=='freeform'인 후속을 query_tickets 대신 claude_query로 재라우팅(대화 이력이 조건을 보존)하는 방법도 가능. 후속 상속 로직(L2049-2105)이 그대로 재사용되도록 변환 계층에 단위 테스트 추가.
- 파일: runner\claude-work-assistant\assistant.py

### 10. [P1/accuracy/M] CREATE 모드 고착: 생성 대화 중 조회/잡담이 모두 생성 플로에 흡수되고, 탈출 수단은 초안까지 삭제하는 '취소'뿐 ✅완료(3.8.0)
- 현재: is_create_intent(L3112-3116)는 context.mode=='CREATE'이고 pending_question이 'approval'만 아니면 무조건 True를 반환하며, route_request(L3356)에서 freeform/query 분기보다 먼저 평가된다. 필수값을 되묻는 단계(pending_question='ticket_requirements')에서 사용자가 "잠깐 내 티켓 목록 보여줘"라고 하면 그 문장이 create_ticket→claude_draft의 초안 수정 입력으로 소비된다(주제 전환 시 조건 미승계 위반). 탈출은 CANCEL뿐인데 CANCELLED는 컨텍스트 전체를 {}로 만들어(L3247) 작성 중 초안도 함께 소멸한다.
- 제안: CREATE 모드 중에도 명백한 조회 신호(is_query_intent/is_freeform_query가 참이고 is_revision_intent가 거짓이며 필수값 응답 형태가 아닌 문장)는 answer_query/claude_query로 우회시키고, 응답 말미에 '작성 중인 티켓 초안은 유지 중'을 알린다(기존 pending CREATE 분기 L3288-3305와 동일한 패턴을 ticket_requirements 단계로 확장). 취소는 '이 티켓 작성만 취소'와 '대화 전체 초기화'를 분리.
- 파일: runner\claude-work-assistant\assistant.py

### 11. [P1/accuracy/S] claude_query에 전달되는 데이터 잘림(티켓 800/프로젝트 300건) 미고지 — 집계·개수 답변이 조용히 틀릴 수 있음 (지시서 8.1) ✅완료(3.7.1)
- 현재: payload는 tickets[:800], projects[:300]으로 절단되지만(L1905-1906) truncation 사실이 payload에도 프롬프트에도 없다. 러너 수용 한도는 MAX_TICKETS=10000(L31)이므로 800건 초과 워크스페이스에서 "프로젝트별 티켓 비율은?", "완료가 몇 퍼센트야?" 같은 freeform 집계는 부분 데이터로 확정 어조의 오답을 낸다. QUERY_PROMPT의 '입력 JSON의 사실만 사용' 원칙은 지켜지지만 그 입력이 전체라는 보장을 모델에게 잘못 암시한다.
- 제안: payload에 data_stats={total_tickets, sent_tickets, truncated: bool} 추가하고 QUERY_PROMPT에 'truncated=true면 수치·집계 답에 부분 데이터임을 명시하라'는 지시 1줄 추가. 병행: 순수 개수 질문('몇 개/몇 건')은 is_freeform_query보다 먼저 규칙 COUNT로 라우팅해 전수 데이터 기반 정확 수치를 보장(현재 answer_query는 freeform 마커가 있으면 LLM 우선).
- 파일: runner\claude-work-assistant\assistant.py

### 12. [P1/accuracy/M] n8n/러너 최종 실패가 사용자에게 '실패' 배지 + '다시 시도' 버튼만으로 표시 — 원인·다음 행동 안내 부재 (지시서 11장) ✅완료(3.7.3(플랫폼은 다음 업그레이드))
- 현재: chat_message.py on_failure(L164-186)는 원인(타임아웃 'n8n 응답 시간 초과' / 연결 실패 / HTTP 5xx / 4xx 영구 거부)을 error 문자열로 받지만 error_code를 항상 'assistant_error' 하나로 저장한다. service.py L280이 error_code를 내려줘도 chat.js(L173-178)는 '실패' 텍스트와 재시도 버튼만 렌더한다. 영구 오류(n8n 요청 거부 HTTP 4xx)도 동일하게 재시도를 권해 무한 재시도-실패 루프를 유도하고, 사용자는 일시 장애인지 설정 문제인지 알 수 없다.
- 제안: on_failure에서 오류 클래스를 코드로 분류 저장(assistant_timeout/assistant_unreachable/assistant_rejected/assistant_error — 내부 메시지는 로그에만). chat.js에 코드→사용자 문구 매핑 추가: 타임아웃/연결 '일시적인 문제입니다. 다시 시도해주세요', 거부류 '요청을 처리할 수 없습니다. 문제가 계속되면 관리자에게 문의해주세요'(거부류는 재시도 버튼 비노출 또는 보조 표기). textContent 전용·CSP 불변 규칙 준수, 정적 파일 핫 업데이트로 배포 가능.
- 파일: app\jobs\handlers\chat_message.py, app\chat\service.py, app\static\js\chat.js

### 13. [P1/mutate/S] 삭제/취소(지시서 3.4) 축 부재 — 미지원 정직 안내조차 없음 ✅완료(3.7.1)
- 현재: "이 티켓 삭제해줘"는 change_markers의 '삭제해'(3141행)로 is_update_intent=True → update_ticket → 삭제라는 개념이 없어 changes가 비고 → "어떤 값을 변경할지 알려주세요. 예: 진행으로 변경해줘..."(2587~2592행)라는 오답이 나간다. 지시서 3.4의 '미지원이면 정직하게 안내' 위반. 한편 "이 티켓 취소해줘"는 detect_target_status가 상태 별칭 '취소'에 걸려 진행상태=취소로 즉시 직접 쓰기되는데, 이것이 사용자가 의도한 '취소'인지(아카이브 vs 상태) 구분·고지가 없다. 또한 정확히 '취소' 한 단어는 CANCEL_COMMANDS(50행)로 대화 컨텍스트 전체를 초기화해 의미가 3중으로 겹친다. Notion archive(pages PATCH archived:true)는 기존 n8n 쓰기 노드로 가능하지만 write_request에 그 종류가 없다.
- 제안: 1단계(S): update_ticket에 삭제 의도('삭제','지워','없애 버려' 등 + 티켓 대상) 감지를 추가해 정직 안내로 응답 — "티켓 완전 삭제는 지원하지 않습니다. 대신 진행상태를 '취소'로 바꿀 수 있습니다('취소 처리해줘'). Notion에서 직접 삭제도 가능합니다." + '취소해줘'가 상태 변경일 때 전/후를 명시(직접 쓰기 전 확인 권장). 2단계(선택, M): write_request에 kind=ARCHIVE 추가 + n8n에 archived:true PATCH 분기 + 영향 표시·확인·사후 재조회 절차.
- 파일: runner\claude-work-assistant\assistant.py, runner\claude-work-assistant\test_assistant.py

### 14. [P1/mutate/L] 일괄 변경(3.3) 미지원 — 다건 매칭 시 무조건 1건 선택 강요 ⏸연기(L) — 다건 쓰기 미리보기+확인 흐름 설계 필요, 단독 세션 배치
- 현재: update_ticket(2561~2570행)은 후보가 여러 건이면 항상 "일치하는 내 티켓이 여러 개입니다. 변경할 티켓 번호나 제목을 알려주세요"로 1건 선택을 강요한다. "계획인 내 티켓 전부 진행으로 바꿔줘" 같은 명시적 일괄 요청도 동일 경로다. write_request는 단일 page_id 구조(2714행)라 전송 프로토콜 자체가 다건을 표현하지 못한다. 지시서 3.3(일괄 변경)과 핵심 원칙 5(대량 변경 = 영향 표시 + 확인 + 사후 재조회) 모두 미충족이며, 미지원 정직 안내도 없다.
- 제안: ① '전부/모두/일괄/다' + 변경 동사 조합의 일괄 의도 감지. ② 대상 N건(본인 할당분만) 목록·전/후 값을 미리보기로 표시하고 needs_confirmation 확인 후 진행, 상한(예: 20건) 초과 시 조건 축소 요청. ③ write_request를 kind=BULK_UPDATE, items:[{page_id, body}] 형태로 확장하고 n8n에서 페이지별 PATCH 루프 + 성공/실패 건별 집계를 last_action에 기록. ④ 완료 메시지에 성공 x/N·실패 목록 명시(부분 성공 정직 보고).
- 파일: runner\claude-work-assistant\assistant.py, runner\claude-work-assistant\test_assistant.py

### 15. [P1/mutate/M] 실행 후 재조회(§9.3) 부재 — 쓰기 결과를 실제 값으로 검증·표시하지 않음 ⏸연기 — n8n 응답이 이미 실제 쓰기 결과(page 객체) 기반이라 부분 충족; 변경 전후 값 표시는 다음 n8n 개정(v7)에 배치 → v7에 적용값 표시 포함
- 현재: 러너의 WRITE_CREATE/WRITE_UPDATE는 write_request를 n8n에 넘기는 시점에 끝난다(2708~2715, 2744~2745, 2777~2778행). 러너에는 쓰기 후 대상 페이지를 재조회해 반영된 실제 값을 사용자에게 보여주는 경로가 없고, 결과 확인은 사용자가 "반영됐어?"라고 물을 때 pending_action_status_response(3065행~)가 n8n이 context/sync로 넣어준 last_action을 읽는 수동 경로뿐이다. BUILD_LOG(세션2)에 'Notion 변경 결과 성공 시 캐시 무효화'가 v2 캐시 설계에 있었다고 기록돼 있으나 현재 활성 v4/v6 워크플로에 유지됐는지는 저장소에서 확인 불가(n8n JSON 미보관) — 무효화가 빠졌다면 쓰기 직후 5분간 조회가 낡은 값을 보여주는 불일치가 된다.
- 제안: ① n8n 쓰기 성공 분기에서 해당 페이지 1건을 read-back(GET page)해 최종 값(상태·마감일·담당자·url)을 완료 메시지에 포함하고 last_action에 저장(러너에 결과 포맷터 함수 추가). ② 활성 워크플로의 쓰기 성공→workDataCache 무효화 존재 여부를 실행 기록으로 검증하고 없으면 복원. ③ 실패 시에는 현재의 '재시도' 흐름 유지하되 read-back 값과 요청 값 불일치 시 '반영 안 됨'으로 정직 보고.
- 파일: runner\claude-work-assistant\assistant.py, C:\Users\hshwa\Downloads\ClovirONE_AI_Work_Assistant (n8n 활성 워크플로 — 저장소 외부)

### 16. [P1/query/M] 기간 축이 마감일 단일 필드에 고정 — 시작일 조회가 마감일 필터로 오해석됨 ✅완료(3.7.3)
- 현재: normalize_ticket은 start_date를 수집하지만(593) 어떤 필터·정렬에도 쓰이지 않는다. parse_date_range(793-879)는 필드 구분 없이 날짜 표현을 파싱하고 due_matches는 항상 due_date만 비교한다(2201-2202). "이번 주에 시작하는 티켓"은 '이번주' 토큰으로 마감일 BETWEEN 필터가 되어 시작일과 무관한 오답 목록을 낸다. 정렬에도 시작일 축이 없다.
- 제안: date_filter에 field 키(due|start) 추가: 메시지에 '시작' 계열 토큰('시작하는/착수/시작일')이 날짜 표현과 함께 있으면 field=start로 파싱하고, due_matches를 date_matches(ticket, filter)로 일반화해 filter.field에 따라 due_date/start_date를 비교. 라벨에도 '시작일 이번 주'처럼 필드를 명시해 사용자가 어떤 축이 적용됐는지 알게 한다. extract_sort에 START_ASC 추가.
- 파일: runner\claude-work-assistant\assistant.py, runner\claude-work-assistant\test_assistant.py

### 17. [P1/query/M] 그룹화 미구현 + SUMMARY 연산이 계산만 되고 LIST로 폴스루하는 죽은 분기 ✅완료(3.7.1)
- 현재: operation은 '현황/요약/정리해줘'에서 SUMMARY로 계산되지만(assistant.py:2001) 본문에는 DETAIL(2215)과 COUNT(2239) 분기만 있어 SUMMARY는 일반 LIST로 렌더링된다. '상태별로/프로젝트별로/담당자별로 묶어서' 같은 그룹화 표현은 파일 전체에 인식 코드가 없고(별로/그룹 grep 0건), FREEFORM_MARKERS에도 없어 규칙 엔진의 평면 목록으로 흐른다. 지시서 매트릭스의 '그룹화' 축이 규칙·LLM 어느 쪽에서도 결정론적으로 처리되지 않는다. 예외: MY_WORK_SUMMARY만 자기 티켓의 상태별 건수를 제공(2146-2151).
- 제안: extract_group_by(message) 추가('상태별/프로젝트별/담당자별/우선순위별' → group 키). SUMMARY 또는 group이 있으면 필터링된 결과를 그룹 키로 집계해 '그룹명: N건 + 상위 3건 제목' 형식으로 결정론 렌더링(수치는 규칙 엔진이 보증, LLM 집계 불일치 방지). group 없는 SUMMARY는 상태별 집계를 기본값으로. COUNT/LIST와 동일하게 last_query에 group을 저장해 후속 조건 승계 유지.
- 파일: runner\claude-work-assistant\assistant.py, runner\claude-work-assistant\test_assistant.py

### 18. [P1/query/M] 상대 날짜 커버리지 비대칭·규칙/LLM 간 해석 기준 불일치(§8.3) ✅완료(3.7.1)
- 현재: parse_date_range(793-879)는 '지난주/어제/지난달/이번 분기/N주 후'를 인식하지 못해(다음달은 되고 지난달은 안 됨) 해당 질의는 필터 없이 전체 목록을 반환하는 침묵 오답이 된다. '이번주'는 today~금요일(801,836-837)이라 이미 지난 요일과 주말 마감이 빠지고, '다음주까지'는 차주 금요일 하드코딩(828). 한편 LLM 경로(claude_query)는 today 문자열만 받고 상대 날짜를 자체 해석하므로 같은 '이번 주'가 두 엔진에서 다른 범위가 될 수 있다 — 지시서 §8.3(상대 날짜 일관 기준) 위반.
- 제안: 1) parse_date_range에 지난주(전주 월~일), 어제, 지난달, 'N주 뒤' 패턴 추가. 2) 주 경계 정책을 상수로 명문화(주=월~일 권장, '까지'는 금요일이 아닌 주 끝)하고 미인식 날짜 표현('~날짜같은 단어가 있는데 파싱 실패)이면 전체 반환 대신 NEED_INPUT으로 기간을 되묻기. 3) 동일 해석 규칙 표를 QUERY_PROMPT에 삽입해 LLM도 같은 기준으로 답하게 함.
- 파일: runner\claude-work-assistant\assistant.py, runner\claude-work-assistant\test_assistant.py

### 19. [P1/query/M] 규칙/LLM 경계가 표면 단어로 갈려 동일 의도 질의가 엔진·결과 불일치 ✅완료(3.7.1)
- 현재: FREEFORM_MARKERS(1860-1864)에 '알려줘/어떤/가장/많이'처럼 광범위한 단어가 있고 route_request(3363)에서 freeform이 규칙보다 먼저 평가된다. "내 티켓 보여줘"는 규칙 엔진(정확한 건수·페이징·조건 승계), "내 티켓 알려줘"는 LLM(티켓 800건 컷오프:1905, 수치 검증 없음, last_query가 freeform으로 대체되어 후속 조건 승계 단절)으로 간다. 같은 의도가 어미 하나로 다른 형식·다른 수치를 낼 수 있어 지시서 '정확도(수치 대조)' 요건과 충돌.
- 제안: 라우팅을 표면 단어가 아니라 구조 신호 우선으로: 메시지에서 스코프 토큰/상태/기간/우선순위/담당자 필터가 하나라도 규칙으로 추출되고 집계·추론 마커(왜/비교/분석/추천/요약)가 없으면 규칙 엔진 우선. '알려줘'는 마커에서 제거(단순 종결어). 장기적으로 LLM 답변에 포함된 건수는 규칙 엔진 카운트와 대조 후 불일치 시 규칙 수치로 교정하는 검증 단계 추가.
- 파일: runner\claude-work-assistant\assistant.py, runner\claude-work-assistant\test_assistant.py

### 20. [P1/ui/S] LLM 경로(QUERY) 카드에 Notion 링크 누락 — 같은 티켓이 경로에 따라 다르게 보임 ✅완료(3.7.1)
- 현재: 규칙 엔진 경로(TICKET_LIST/WORK_SUMMARY/TICKET_DETAIL)는 url 포함 전체 티켓 dict를 카드로 보내지만, claude_query의 ref_tickets/ref_projects는 _slim_ticket_for_query/_slim_project_for_query(assistant.py:1833-1856)를 재사용해 url이 없다(assignees도 dict가 아닌 이름 문자열이라 형태 불일치). 그래서 '요약/분석/추천/왜/어떻게' 등 FREEFORM_MARKERS(assistant.py:1860)로 라우팅되는 질문의 카드에는 'Notion에서 열기 ↗'가 절대 뜨지 않는다(chat.js:108-115는 url 없으면 링크 생략).
- 제안: assistant.py:1925-1926의 ref_tickets/ref_projects 매핑에서 출력 전용 직렬화기를 분리해 url(과 assignees 원본 dict)을 포함시킨다. tmap/pmap이 이미 전체 dict를 들고 있으므로 {**_slim_ticket_for_query(t), "url": t.get("url"), "assignees": t["assignees"]} 수준이면 충분. 주의: _slim_*은 LLM 입력(tickets[:800])과 공유되므로 입력 쪽에는 url을 추가하지 말 것(토큰 낭비). test_assistant.py에 QUERY 응답 tickets[].url 존재 테스트 추가.
- 파일: runner\claude-work-assistant\assistant.py, runner\claude-work-assistant\test_assistant.py

### 21. [P1/ui/M] 목록 응답이 텍스트 버블과 카드에 같은 정보를 2번 렌더 (모바일에서 특히 체감) ✅완료(3.7.2)
- 현재: TICKET_LIST(assistant.py:2291-2308)·WORK_SUMMARY(2149-2178)·PROJECT_LIST(2135-2141)의 response_text에 티켓별 상태/프로젝트/담당/마감/우선순위(format_ticket, assistant.py:989-994)가 전부 들어가고, 프런트는 그 버블 아래에 동일 필드의 카드(renderStructured)를 또 붙인다. 10건 조회 시 화면 길이가 2배가 되고 모바일(msg max-width 92%, chat.css:259)에서는 한 응답이 수 화면을 차지한다. 지시서 7.1 '목록=핵심 정보'와 어긋나는 중복.
- 제안: 러너가 카드 배열을 포함하는 응답의 response_text를 헤더+요약(예: '내게 직접 할당된 티켓: 총 12건, 10건 표시')으로 줄이고 상세 라인은 카드가 담당. 카드 없는 소비자(n8n 텍스트 채널) 호환이 필요하면 기존 전체 텍스트를 별도 키(text_detail)로 유지하고 worker의 _TEXT_KEYS(chat_message.py:35)는 그대로 response_text를 쓰게 한다. 프런트 변경 없이 러너만 고치는 것이 안전. 스냅샷 테스트로 회귀 방지.
- 파일: runner\claude-work-assistant\assistant.py, runner\claude-work-assistant\test_assistant.py

### 22. [P1/ui/M] 카드에서 상세 진입·후속 작업·페이지네이션 불가 (지시서 7.1 후반부 미구현) ✅완료(3.7.2)
- 현재: info-card는 정적이다 — 클릭 핸들러가 전혀 없고(chat.js:86-117) 유일한 상호작용은 Notion 외부 링크뿐. 러너는 이미 '2번 티켓 상세'(resolve_ticket_reference, assistant.py:2311+), '더 보여줘'(offset 페이징, assistant.py:2252+), 상태 변경(update_ticket)을 지원하는데 UI에서 진입로가 없다. structured.total(assistant.py:2308)도 프런트에서 미사용이라 '총 N건 중 10건' 이후의 나머지를 카드로 볼 방법이 타이핑뿐.
- 제안: 카드에 '상세' 버튼(클릭 시 sendMessage("'<제목>' 상세") 재사용 — 러너의 제목 정확일치 매칭 assistant.py:2346이 이미 처리), 카드 리스트 하단에 structured.total > 표시건수일 때 '더 보여줘' 칩 추가. 후속 작업은 1단계로 상세 카드에만 '상태 변경' 칩(입력창에 프리필). 모두 기존 sendMessage 경유라 서버/러너 변경 불필요. XSS 불변 규칙(textContent 전용) 유지.
- 파일: app\static\js\chat.js, app\static\css\chat.css

### 23. [P1/ui/S] 빠른 추천(quick prompts)이 조회 편중·정적 하드코딩·권한 미반영 (지시서 '새 대화 추천' 축) ✅완료(3.7.2)
- 현재: chat.html:41-47에 5개 버튼이 하드코딩: 조회 3(내 할당 티켓/이번 주 마감/내 담당 프로젝트) + 생성 1 + 도움말. 지시서가 금지한 '조회 편중' 상태로, 러너가 실제 지원하는 변경(상태/우선순위/마감/담당, update_ticket)과 요약(WORK_SUMMARY '내 업무 현황', assistant.py:2143) 예시가 없다. role 변수가 같은 템플릿(chat.html:30)에서 이미 쓰이는데도 권한별 분기가 없고, 빈 대화에서만 노출(chat.js:328)된다.
- 제안: 실기능 기반 세트로 교체: 조회 2(내 할당 티켓/이번 주 마감) + 요약 1('내 업무 현황 요약') + 생성 1('새 티켓 만들기') + 변경 1('방금 조회한 티켓 상태 바꾸기'류는 문맥 필요하므로 '티켓 상태 변경하기' 문구로) + 도움말. Jinja role 조건으로 쓰기 계열 노출 제어(뷰어 역할이 있으면 조회·요약만). 문구는 러너 지원 표현과 1:1 대응하도록 test_assistant.py의 인식 테스트로 검증.
- 파일: app\templates_html\chat.html, runner\claude-work-assistant\test_assistant.py

### 24. [P1/ui/M] 프로젝트 카드에 담당 정/부·역할·티켓 수·진행률이 없음 ✅완료(3.8.0)
- 현재: 지시서 '프로젝트' 축은 목록·현황·담당·티켓 수·진행률 조회를 요구. PROJECT_LIST 페이로드(assistant.py:2141)의 프로젝트 dict에는 primary/secondary(사람 배열)와 role이 있으나 renderCard는 name·status·url만 표시하고(P0 갭과 동일 원인 일부), 티켓 수·진행률은 러너가 아예 계산하지 않아 structured에 없다 — 프런트가 고쳐도 표시할 데이터가 없는 상태. 티켓에 project_ids가 이미 정규화되어 있어(assistant.py:596) 계산 재료는 러너 메모리에 전부 있다.
- 제안: 러너: PROJECT_LIST/WORK_SUMMARY의 projects 항목에 ticket_count·done_count(프로젝트별 tickets의 project_ids 집계, 완료 판정은 status_map 기반 — 상태명 하드코딩 금지)를 추가하고 response_text에도 반영. 프런트: 프로젝트 카드에 역할(정/부)·담당(정: 이름들, 부: 이름들)·'티켓 N건(완료 M)' 행 추가. 0건 프로젝트도 '0건'으로 명시(지시서 6: 데이터 누락 케이스).
- 파일: runner\claude-work-assistant\assistant.py, app\static\js\chat.js

### 25. [P2/accuracy/S] is_query_followup 과승계: 일반 주어('~한 티켓 보여줘') 문장이 직전 프로젝트/담당자 필터를 상속 ✅완료(3.9.2)
- 현재: is_query_followup(L2989-3033)의 has_subject 목록에 일반 '티켓/작업' 주어가 없어, "용인 프로젝트 티켓 보여줘" 직후 "완료된 티켓 보여줘"(상태 조건어 포함, 40자 이하)는 condition_only=True·has_subject=False로 followup 판정되어 용인 프로젝트 필터와 PROJECT_TICKETS scope를 상속한다(L2041-2046). 완결된 새 문장이 이전 조건을 물려받는 주제 전환 누수이며, 결과 제목에 프로젝트명이 표기되긴 하나 사용자가 전사 기준을 물었다면 수치가 다르다.
- 제안: 주어+서술이 갖춰진 완결형 문장('...티켓 보여줘/알려줘/조회해줘' 등 명령형 종결 + 명시적 조건)은 followup에서 제외하고, 지시어('그중/여기서/이 목록에서')나 조건-단독 파편일 때만 상속. 경계 사례는 결과 첫 줄에 '직전 조회 조건(용인 프로젝트)을 유지했습니다. 전체 기준은 "전체 티켓"이라고 말씀해주세요'를 덧붙여 오해를 즉시 교정 가능하게 함. 기존 followup 테스트에 완결형/파편형 쌍 케이스 추가.
- 파일: runner\claude-work-assistant\assistant.py

### 26. [P2/accuracy/S] COUNT 응답이 화면에 보이지 않는 목록을 last_results로 저장 — 보이지 않는 번호 참조 허용 ✅완료(3.9.1)
- 현재: query_tickets의 COUNT 경로(L2239-2250)는 개수만 표시하면서 last_results=[filtered[:10] id], last_result_start=1을 저장한다. 사용자가 목록을 본 적이 없는데 "첫 번째 완료 처리해줘"가 임의(정렬상 첫) 티켓으로 해석되어 직접 쓰기까지 이어질 수 있다 — 사용자가 참조 근거를 확인할 수 없는 대상 지정이다.
- 제안: COUNT 응답에서는 last_results를 갱신하지 않거나(이전 목록 유지), 저장하되 번호 참조 해석 시 '직전 화면은 개수만 표시했습니다' 안내와 함께 상위 10건 목록을 먼저 보여주고 재지정을 받는다(last_query에 display_kind:'count' 표식 추가로 판별). 갭 2의 페이지 맵 도입 시 함께 처리하면 중복 작업이 없다.
- 파일: runner\claude-work-assistant\assistant.py

### 27. [P2/mutate/M] 댓글 달기(3.3) 미지원 — 무관한 티켓 목록으로 응답 🔧구현완료(3.11.0, n8n v7 import 후 배포)
- 현재: "이 티켓에 댓글 달아줘: ..."는 어떤 쓰기 마커에도 없어('댓글','달아' 부재) is_update_intent=False, '티켓'이 query_markers(3161행)에 있어 is_query_intent=True → query_tickets가 조건 없는 티켓 목록을 돌려주는 동문서답이 된다. 미지원 정직 안내 없음. Notion comments API(POST /v1/comments)는 존재하므로 n8n 확장으로 지원 가능하나 현재 write_request에 종류가 없다.
- 제안: 1단계(S): '댓글/코멘트 + 달아/남겨/추가' 의도 감지 → "댓글 작성은 아직 지원하지 않습니다. 티켓 본문 참고사항에 남기려면 …" 정직 안내(태그도 동일 — 작업 DB에 태그 속성 자체가 없음을 명시). 2단계(선택): write_request kind=COMMENT {page_id, text} + n8n comments POST 노드 + 확인 절차. 지시서가 예시로 든 축이므로 1단계만으로도 요건(정직 안내) 충족.
- 파일: runner\claude-work-assistant\assistant.py, runner\claude-work-assistant\test_assistant.py

### 28. [P2/mutate/L] 본문 변경(3.3)·본문 기반 요약 불가 — 페이지 blocks 미수집·미갱신
- 현재: 본문(children blocks)은 생성 시 build_page_children(1333~1358행)으로 한 번 쓰일 뿐, 이후 어떤 경로로도 읽거나 수정하지 못한다. n8n이 러너에 주는 tickets에는 properties만 있고 blocks가 없어(지시서도 '본문 미수집' 명시) 상세 조회에 본문이 빠지고, "이 티켓 본문에 …추가해줘"는 is_revision_intent가 CREATE 초안에만 적용되므로 기존 티켓에 대해선 갭 2와 같은 동문서답 경로로 빠진다. 요구사항 '본문 요약은 원문 기반'도 충족 불가.
- 제안: ① 우선 정직 안내: 기존 티켓 본문 변경·본문 요약 요청 감지 시 '본문은 아직 조회/수정하지 못합니다' + Notion 링크 제공(S). ② 본지원: n8n에 대상 페이지 1건의 blocks GET(children) 노드를 추가해 상세 조회 시에만 lazy 수집(전체 캐시 부풀림 방지), 본문 추가는 blocks append PATCH(kind=APPEND_BODY) + 확인 절차. 전량 수집은 캐시·60초 병목을 재유발하므로 금지.
- 파일: runner\claude-work-assistant\assistant.py, C:\Users\hshwa\Downloads\ClovirONE_AI_Work_Assistant (n8n 활성 워크플로 — 저장소 외부)

### 29. [P2/query/S] 검색어 축이 따옴표/정형 패턴에 한정 — 무따옴표 키워드 질의는 전체 목록 반환 ⏸보류 — 무따옴표 임의 명사를 검색어로 오인하면 오탐이 정답보다 해로움; 자연어 검색은 LLM 경로가 이미 커버, 정형 검색은 따옴표 규칙 유지(도움말에 안내)
- 현재: extract_keyword(1284-1295)는 "제목에 X 포함", 따옴표 'X' 관련, "검색어는 X" 세 패턴만 인식한다. "배포 관련 티켓 보여줘"처럼 따옴표 없는 자연 표현은 키워드가 비어 프로젝트명 매칭에 실패하면 ALL_TICKETS 전체 목록이 된다('관련'은 FREEFORM_MARKERS에도 없어 LLM으로도 안 감). 검색 대상도 제목+티켓ID뿐(2209-2211) — 본문 미수집은 알려진 한계.
- 제안: 무따옴표 패턴 추가: 'X 관련 티켓/작업', 'X(이)가 들어간' 형태에서 X를 후보 키워드로 추출하되, resolve_project 점수가 임계 이상이면 프로젝트 해석을 우선(충돌 규칙 명시). 키워드 적용 시 제목/티켓ID 검색임을 라벨에 표기하고 0건이면 '본문 검색은 지원하지 않습니다' 정직 안내. 본문(blocks) 수집은 별도 L 과제로 분리(지시서도 검토 필요로만 명시).
- 파일: runner\claude-work-assistant\assistant.py, runner\claude-work-assistant\test_assistant.py

### 30. [P2/query/S] 페이지 크기 10 고정·정렬 축 부족(난이도/시작일/최신순 없음) ✅완료(3.9.1)
- 현재: limit은 신규 질의에서 항상 10으로 하드코딩(2124)되어 "20개씩 보여줘", "상위 5개만"이 무시된다(하드코딩 금지 원칙과도 충돌). extract_sort(1271-1281)는 마감일 오름/내림·우선순위·제목 4종뿐 — '난이도 높은 순', '시작일 순', '최근 만든 순'(created_time 부재와 연동: P0-1 해결 시 가능)이 기본 DUE_ASC로 침묵 대체된다.
- 제안: '(상위 )?N개(씩|만)?' 패턴으로 limit 파싱(1~50 clamp, last_query에 저장해 더보기에도 적용). extract_sort에 DIFFICULTY_DESC/ASC('난이도높은순/낮은순'), START_ASC('시작일순'), CREATED_DESC('최신순', created_time 수집 후) 추가하고 미인식 정렬 표현은 기본값 대체 사실을 응답 라벨에 표기.
- 파일: runner\claude-work-assistant\assistant.py, runner\claude-work-assistant\test_assistant.py

### 31. [P2/ui/M] 프로젝트 시각 구분(색+이름) 및 상태 배지 색상 부재 (지시서 7.2) ✅완료(3.9.1)
- 현재: 모든 info-card가 동일한 border-left: var(--color-secondary)(chat.css:194)이고 status-badge는 상태값과 무관한 단일 중립 스타일(chat.css:203-207). 티켓/프로젝트 카드 구분도 없다(renderCard의 kind 인자는 받기만 하고 미사용, chat.js:86). 여러 프로젝트의 티켓이 섞인 목록에서 어느 프로젝트 것인지 시각적으로 구분 불가 — 지시서 7.2 '프로젝트 시각 구분(색+이름)' 미충족.
- 제안: 프로젝트명 해시 → 고정 팔레트(8~12색, tokens.css에 라이트/다크 쌍 정의) 인덱스로 결정적 색상 산출(프로젝트별 색 하드코딩 금지 원칙 충족). 티켓 카드에 색점+프로젝트명 배지, 카드 border-left도 같은 색. kind 인자를 활용해 프로젝트 카드에 구분 클래스. 상태 배지는 상태 문자열이 Notion 스키마 유래라 명칭 하드코딩 대신 동일한 해시 팔레트 또는 '완료 계열만 흐리게' 수준의 보수적 처리.
- 파일: app\static\js\chat.js, app\static\css\chat.css, app\static\css\tokens.css

### 32. [P2/ui/M] 확인·선택 흐름이 순수 타이핑 의존 — ticket_draft·후보 목록이 카드/버튼으로 렌더되지 않음 ✅완료(3.10.0)
- 현재: CREATE_PREVIEW는 ticket_draft(assistant.py:2986), NEED_INPUT 프로젝트 선택은 후보 목록(assistant.py:2007, context에만 존재)을 내보내지만 renderStructured는 tickets/projects/items/results/ticket/project 키만 인식(chat.js:123-140)해 전부 무시된다. 사용자는 '네', '2' 같은 답을 직접 타이핑해야 하고, 모바일에서 특히 불편. 승인 실수 방지(중복승인 버그 수정 이력)와도 연결되는 UX.
- 제안: 러너: NEED_INPUT/CREATE_PREVIEW 응답에 structured options 배열(예: [{label:'네', send:'네'}, {label:'1. 프로젝트A', send:'1'}])을 추가. 프런트: 마지막 어시스턴트 메시지에만 옵션 칩을 렌더하고 클릭 시 sendMessage(send) — 과거 메시지의 칩은 비활성(취소부활 버그 재발 방지). ticket_draft는 renderCard로 미리보기 카드 표시. 러너 변경+프런트 변경이 커플링되므로 하위호환(옵션 없으면 현행 동작) 유지.
- 파일: runner\claude-work-assistant\assistant.py, app\static\js\chat.js, app\static\css\chat.css
