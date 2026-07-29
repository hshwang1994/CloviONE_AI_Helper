# 테스트 결과 (TEST_RESULT)

2026-07-16 기준. 실행하지 않은 것은 실행했다고 적지 않았다.

## 실행한 명령과 결과

| 대상 | 명령 | 결과 |
|---|---|---|
| 러너 단위·회귀 | `cd runner/claude-work-assistant && RUNNER_TOKEN=x PYTHONUTF8=1 python -m pytest test_assistant.py -q` | **92 통과, 0 실패** (세션 시작 시 57개 → 92개) |
| 플랫폼 전체 | `.venv/Scripts/python.exe -m pytest` (pytest.ini: `-m "not smoke"`) | **440 통과, 0 실패** (세션 시작 시 437개 → 440개) |
| 정적 검사 | `bash scripts/static_checks.sh` | **STATIC_CHECKS_OK** |
| JS 문법 | `node --check app/static/js/chat.js app/static/js/admin/*.js` | 4개 파일 전부 통과 |
| n8n Code 노드 문법 | 모든 jsCode를 `async function`으로 감싸 `node --check` | 34개 노드 중 코드 노드 전부 통과, 깨진 것 0 |

Skip 처리한 테스트는 없다. 실패를 통과로 바꾸기 위해 기대값을 고친 테스트도 없다.

## 이번 세션에 추가한 회귀 테스트

러너(35개 추가). 각 테스트는 실제로 발견된 결함 문장을 재현한다.

- `test_status_alias_needs_an_anchor_not_a_coincidence` — '결제 문제 관련 티켓 보여줘'가 상태 필터를 만들지 않는다
- `test_ticket_title_never_becomes_a_status_change` — 제목의 '완료'가 진행상태를 뒤집지 않는다
- `test_a_persons_name_never_switches_off_completed_tickets` — '남기훈'이 완료 조회를 끄지 않는다
- `test_dated_completed_query_is_not_self_contradictory` — '지난주에 완료한 티켓'이 0건이 아니다
- `test_priority_needs_its_own_anchor_and_difficulty_is_a_grade` — '난이도 높은'이 우선순위가 되지 않는다
- `test_creating_work_is_not_only_about_the_word_ticket` — '작업 만들어줘'가 생성이다
- `test_natural_change_verbs_reach_the_write_flow` — '마감일 내일로 미뤄줘'가 쓰기다
- `test_week_is_monday_to_sunday_everywhere` — 세 표현의 주 정의가 같다
- `test_demonstrative_followup_keeps_the_confirmed_project` — '그 프로젝트'가 문맥을 지킨다
- `test_named_subject_that_matches_nothing_is_admitted_not_papered_over` — 없는 이름에 전체 목록을 내놓지 않는다
- `test_project_reference_needs_a_name_not_a_coincidence` — '기능'이 프로젝트 조건이 되지 않는다
- 그 외 24개

플랫폼(3개 추가): Notion 매핑 목록, 스케줄 run-now 승인 게이트, 문서 발행 정책 강제.

## 라이브 검증 (실제 서비스, 실제 데이터)

코드 추적이 아니라 실행 결과다. 상세는 [USER_JOURNEY_REVIEW.md](USER_JOURNEY_REVIEW.md).

| 검증 | 결과 |
|---|---|
| 사용자 여정 프로브 12건 | 전부 정상 (수정 전에는 7건이 0건 또는 정반대 데이터였다) |
| 티켓 생성 → 승인 → Notion 반영 | 실제 티켓 생성, 링크 반환 |
| 댓글 작성 | 실제 Notion 댓글 게시 (Notion API로 존재 확인) |
| 타인 티켓 변경 시도 | FORBIDDEN 차단 |
| 서로 다른 사용자가 같은 message_id | 각자 자기 답 (교차 노출 없음) |
| 같은 사용자 재전송 | 중복 인식, 쓰기 재실행 없음 |
| 관리자 작업 큐 API | 실제 관리자 계정으로 로그인해 응답 필드 15개 확인, 채팅 원문·요청자·첨부 노출 0 |
| 서비스 상태 | clovirone-web-assistant / clovirone-web-worker / n8n / claude-work-assistant 전부 active, healthz·readyz 200 |

## 검증하지 못한 것

- **브라우저 실화면**: 채팅 화면의 오류 표시, 빈 상태, 재시도 버튼, 관리자 모달 접근성은
  코드와 문법 검사, 그리고 node vm 하네스(수정 전 원본과 대조)까지 확인했다.
  실제 브라우저에서 로그인해 눈으로 본 것은 아니다. **확인 필요.**
- **이미지 첨부 여정**: 러너와 n8n 양쪽을 고쳤으나 실제 사진을 올리는 라이브 검증은 못 했다. **확인 필요.**
- **성능 수치**: 개선 전후를 측정하지 않았다. 측정하지 않은 것을 개선됐다고 적지 않는다.
