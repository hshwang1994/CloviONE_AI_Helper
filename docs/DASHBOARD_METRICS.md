> ## ⚠ 정합성 경고 (2026-08-20 · W5 독립 조사)
>
> **이 문서는 지금 코드와 어긋난다.** 실측으로 확인된 어긋남 셋:
> ① §1 표의 「활성 스케줄」·「등록된 러너」·「메모리 사용」·「디스크 여유 / 사용」은
>    `/dashboard` 화면에 **없다**(`Dashboard.jsx` 에 `runners`·`active_schedules` 참조 0건,
>    disk 는 `used_pct` 만 쓴다). 서버는 그 값들을 매 폴링마다 계산해서 보낸다.
> ② §3 의 12행 중 4행(알림·채팅·게시판·내 글)은 화면에서 **제거됐다**.
> ③ 이 문서의 자체 감사 결론("화면은 여유와 전체만 쓴다")은 현재 코드와 **정반대**다.
>
> 이 화면들의 정보 설계는 W8(`/me` Pilot)·W12(관리자 콘솔)가 소유한다.
> 그 Wave 가 «화면이 무엇을 보여야 하는가» 를 결정한 **뒤에** 이 문서를 그 결정에 맞춰
> 다시 쓴다 — 지금 문서를 코드에 맞춰 고치면 «지금 이렇다» 는 기록이 하나 더 생길 뿐
> 「무엇이 옳은가」에 대한 판단은 여전히 없다. 근거는 `docs/DECISIONS.md` D-186.

# 대시보드 지표 출처표

`/dashboard`(frontend/src/screens/Dashboard.jsx)와 `/me`(frontend/src/screens/Home.jsx)에
뜨는 **모든 숫자**의 출처를 한 곳에 적는다.

## 왜 이 표가 있는가

숫자가 틀리는 방식은 대개 계산 오류가 아니다. **기준이 어긋나는 것**이다.

- 어떤 질의에서 온 값인가(같은 이름의 두 숫자가 다른 표에서 올 수 있다)
- 어떤 시점 기준인가(지금 / 롤링 24시간 / KST 달력일 / KST 주)
- 범위(scope)를 지나는가(남의 부서 것이 섞이는가)
- 0과 "없음"을 구분하는가(안 쟀다를 0으로 그리면 그럴듯해서 아무도 신고하지 않는다)

이 네 가지가 표에 없으면 화면의 숫자를 몇 주 뒤에 아무도 설명할 수 없고, 설명할 수 없는
숫자는 결국 아무도 안 본다.

## 시점 어휘 (표에서 쓰는 말)

| 말 | 뜻 | 시간대 위험 |
|---|---|---|
| 지금 | 시간 필터가 없다. 질의하는 순간의 표 상태 | 없음 |
| 롤링 24시간 | `clock.now() - 24h` 이후. 달력일이 아니다 | 없음 (자정 경계를 안 쓴다) |
| KST 달력일 | `app/home/service.py::local_today` 가 정한 그날 | **있음**: UTC로 자르면 9시간 밀린다 |
| KST 주 | `app/projects/weekly.py::week_for`(월요일 시작) | **있음**: 같은 이유 |
| 하트비트 | 마지막 비트가 90초를 넘으면 down | 없음 |

---

## 1. `/dashboard` 운영 지표 (GET `/api/admin/dashboard`, app/health/service.py)

역할 게이트는 `CONSOLE_READ_ROLES`다. 부서/조직 **범위는 지나지 않는다**. 이 값들은
포털 전역 인프라 상태라 부서로 나눌 축이 없기 때문이다(app/core/scope.py: 역할과 범위는
직교하고, 전역 설정 모듈은 역할로만 막는 것이 옳다).

| 지표 | 질의 | 시점 | 범위 | 0과 없음 |
|---|---|---|---|---|
| 서비스 정상 (n/전체) | `components` + `integrations` | 하트비트 + 마지막 헬스체크 | 없음 | 전체 0이면 `-` |
| 활성 워크플로 | `SELECT count(Workflow) WHERE enabled` | 지금 | 없음 | 값 없으면 `-` |
| 활성 스케줄 | `SELECT count(Schedule) WHERE enabled` | 지금 | 없음 | 값 없으면 `-` |
| 등록된 러너 | `SELECT count(Runner)` | 지금 | 없음 | 값 없으면 `-` |
| 처리 요청 | `count(Job) WHERE created_at >= now-24h` | 롤링 24시간 | 없음 | 0은 0 |
| 성공 | 위 + `status=succeeded` | 롤링 24시간 | 없음 | 0은 0 |
| 성공률 | 성공 / (성공+실패+취소) | 롤링 24시간 | 없음 | **분모 0이면 null → `-`** (0%가 아니다) |
| 평균 처리 | 성공한 작업의 `finished-started` 평균 | 롤링 24시간 | 없음 | 표본 0이면 null → `-` |
| 대기 작업 | `count(Job) WHERE status=queued` | 지금 | 없음 | 0은 0 (항상 노출) |
| 미해결 실패 작업 | `count(Job) WHERE status=failed` | 지금 | 없음 | 0은 0 (항상 노출) |
| 디스크 여유 / 사용 | `shutil.disk_usage(data_dir)` | 지금 | 없음 | OSError면 전부 null → **타일을 숨긴다** |
| 메모리 사용 | `/proc/meminfo` | 지금 | 없음 | 비-Linux면 null → **타일을 숨긴다** |
| 인증서 만료 | `ssl` 로 파싱한 `tls_cert_path` | 지금 | 없음 | 경로 없거나 파싱 실패면 null → **타일을 숨긴다** |
| 마지막 백업 | `backups.last_successful_backup` | 지금 | 없음 | 없으면 "없음"(0이 아니다) |
| 최근 주요 변경 | `audit_log` 중 CRITICAL_ACTIONS 5건 | 지금 | **역할**로 자른다(`SENSITIVE_READ_ROLES`) | 권한 없음 / 정말 없음을 **다른 문구**로 구분 |
| 유지보수 모드 | `settings.is_maintenance_mode` | 지금 | 없음 | true면 경보 (아래 "고친 것" 참조) |

성공률의 분모는 **끝난 작업**만이다. 접수만 몰린 순간에 0%로 떨어지지 않게 하려는
의도이고, 화면도 라벨과 각주에 그 기준을 그대로 적는다.

## 2. `/dashboard` 내 업무 구역 (GET `/api/home/work-dashboard`, app/home/work.py)

8단계에서 새로 넣은 구역이다. 세 종류의 소스를 한 응답에 합치되 **장애는 서로 옮지 않는다**.

| 지표 | 질의 | 시점 | 범위 | 0과 없음 |
|---|---|---|---|---|
| 내 미완료 | `tickets.service.list_my_tickets` → `aggregate.bucket_my_tickets` | KST 달력일(오늘) | 세션 사용자 본인 | 소스 장애면 `mine=null` → **타일 자체를 안 그린다** |
| 지연 티켓 | 같은 질의, `due < 오늘` 이고 활성 | KST 달력일(오늘) | 본인 | 같음 |
| 이번 주 마감 | 같은 질의 → `aggregate.sprint_progress` | **KST 주** [월, 다음 월) | 본인 | 같음 |
| 최근 완료 추이 | 같은 질의 → 주별 `sprint_progress` 4주 | **KST 주** 4개 | 본인 | 같음. 완료는 **마감일 기준**(완료 시각이 소스에 없다) |
| 차질 프로젝트 | `projects.repository.list_in_scope` | 지금 | **`principal.scope`** (목록 화면과 같은 조건) | `health_score=null`은 차질이 **아니다**. 0은 차질이다 |
| 아직 안 잰 프로젝트 | 같은 질의 | 지금 | 같음 | `unscored`로 따로 센다(0으로 뭉개지 않는다) |
| 지연 마일스톤 | `projects.milestones.list_for_project` | KST 달력일(오늘) | 범위를 지난 프로젝트에서만 | 기한이 오늘이면 아직 지연이 아니다 |

목록 카드의 `count`는 언제나 진짜 총계이고 `items`만 5줄로 잘린다. "12건"이라고 쓰면서
5줄만 그리는 어긋남이 구조적으로 생기지 않게 하는 이 저장소의 공통 규약이다.

## 3. `/me` 오늘 화면 (GET `/api/home/today`, app/home/service.py)

| 지표 | 질의 | 시점 | 범위 | 0과 없음 |
|---|---|---|---|---|
| 오늘 마감 | `bucket_my_tickets.due_today` | KST 달력일 | 본인 | 소스 장애면 버킷 자체가 없다 → `-` |
| 지연 | `bucket_my_tickets.overdue` | KST 달력일 | 본인 | 같음 |
| 진행 중 | `bucket_my_tickets.in_progress` | 상태만 본다(시점 무관) | 본인 | 같음 |
| 7일 내 마감 | `bucket_my_tickets.due_soon` | KST 달력일 + 7일 롤링 | 본인 | 같음 |
| 막힘(이슈) | `bucket_my_tickets.blocked` | 상태만 본다 | 본인 | 같음 |
| 안 읽은 알림 | `notifications.service.unread_count` | 지금 | 본인 | 0은 0 |
| 안 읽은 채팅 | `team_chat` 저장소 + `unread_for` | 지금 | 본인 | 기능 꺼짐이면 **null**(0이 아니다). 그 자리를 '막힘'이 채운다 |
| 이번 주 내 진척 | `aggregate.sprint_progress` | **KST 주** | 본인 | 소스 장애면 `sprint=null` → "계산할 수 없습니다" |
| 최근 문서 | `team_docs` 캐시 최신 5건 | 지금 | 없음 | 빈 목록과 오류를 다른 그림으로 구분 |
| 게시판 최신글 | `board.repository.list_posts` | 지금 | 없음 | 같음 |
| 내 글 / 받은 댓글 / 조회 | `/api/board/mine` | 지금 | 본인 | 404/로딩이면 위젯을 숨긴다 |
| 동기화 신선도 | `tickets.service.sync_indicator` | 지금 | 없음 | 실시간 응답이면 블록 자체가 없다 |

## 4. 주간 다이제스트 (GET `/api/assistant/weekly-digest`)

홈의 도우미 패널이 부른다. 이 화면 계열에서 **M4가 실제로 살아 있던 자리**다.

| 지표 | 질의 | 시점 | 범위 | 0과 없음 |
|---|---|---|---|---|
| 내 몫 / 팀 합계 | `sprint_progress` / `reports.build_period_report` | KST 주 | 본인 / 전체 | 소스 장애면 null |
| 바뀐 문서 | `readers.documents_changed_between` | **KST 주를 UTC 문자열 경계로 변환** | 없음 | 0은 0 |
| 올라온 글 | `readers.board_posts_between` | **KST 주를 UTC datetime 경계로 변환** | 없음 | 0은 0 |

---

## 전수 점검 결과

세어 보니 `/dashboard`의 운영 지표는 **17종**, `/me`는 **13종**이었다. "잡 큐 지표만
있다"는 인상은 절반만 맞다. 잡 큐 관련이 6종으로 가장 많고, 나머지는 인프라(디스크/메모리/
인증서/백업)와 인벤토리(워크플로/스케줄/러너)였다. 공통점은 **전부 운영 지표**라는 것이고,
사용자가 자기 일을 보는 지표는 **0종**이었다. 그래서 2절(내 업무)을 새로 넣었다.

### 고친 것

1. **유지보수 모드가 화면에 없었다** (frontend/src/screens/Dashboard.jsx).
   서버는 `maintenance`를 매 폴링마다 실어 보냈고 `app/health/service.py`의 주석도
   "화면이 상단 배너/경보로 띄운다"고 적어 두었지만, 화면은 그 필드를 **한 번도 읽지
   않았다**. 결과: 유지보수 모드가 켜져 일반 사용자의 **모든 쓰기가 막힌 동안에도**
   대시보드는 초록색 "지금 조치가 필요한 문제가 없습니다."를 띄웠다. 운영자는 그 배너를
   믿고 "저장이 안 돼요" 신고를 다른 장애로 오해한다.
   고정: `frontend/src/screens/dashboard-render.test.jsx`의 "유지보수 모드" 묶음.

2. **주간 다이제스트의 '바뀐 문서'가 KST 달력일을 UTC 문자열과 비교했다 (M4)**.
   `app/home/readers.py::documents_changed_since`가 `last_edited >= '2026-08-03'`으로
   잘랐다. `last_edited`는 Notion이 준 UTC 문자열이라 **KST 월요일 오전 9시간이 통째로
   빠졌고**, 위쪽 경계가 아예 없어 **다음 주 문서가 이번 주에 꼈다**.
   고침: `documents_changed_between(since_iso, until_iso)`로 바꾸고 경계는
   `app/home/service.py::utc_iso_bounds` 한 곳에서만 만든다.
   고정: `tests/unit/test_day_boundaries.py`(경계 양쪽) +
   `tests/integration/test_assistant_api.py`의
   `test_weekly_digest_cuts_documents_at_kst_midnight_on_both_sides`(배선).

### 확인했지만 고치지 않은 것

- **연동 배지와 도넛 범례의 말이 다르다.** 한 번도 헬스체크를 안 한 연동은 배지에
  "알 수 없음", 도넛 범례에는 "응답 없음"으로 나온다. 컴포넌트(하트비트)는 두 곳 다
  "응답 없음"으로 통일돼 있다. 두 사실이 실제로 다르기 때문에(하트비트가 끊긴 것과 아직
  한 번도 확인 안 한 것) 한쪽으로 뭉개는 것이 옳은지 판단이 서지 않아 그대로 뒀다.
  숫자가 틀리는 문제가 아니라 어휘 문제다.
- **`disk.used_gb`는 계산만 되고 화면 어디서도 안 쓴다.** 화면은 여유와 전체만 쓴다.
  거짓말은 아니라서 두었다.
- **나머지는 전부 맞다.** 위 표의 시점/범위/0과 없음 칸은 코드를 따라가 확인한 값이다.

## 이 화면들이 시간대를 다루는 규칙

`local_today`(오늘) / `week_for`(주) / `window_utc_bounds`(KST 창 → naive UTC datetime) /
`utc_iso_bounds`(KST 창 → UTC ISO 문자열). **네 개가 전부이고, 새로 만들지 않는다.**
`app/profiles/stats.py::_week_start`가 이미 두 번째 주 경계 구현이라, 세 번째가 생기면
스프린트와 리포트와 대시보드가 서로 다른 주를 "이번 주"라고 부르기 시작한다.
