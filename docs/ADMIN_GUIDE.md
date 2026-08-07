# ADMIN GUIDE — 관리자 콘솔 안내

`https://clovirone-ai.gooddi.lab/admin` — operator 이상만 진입(일반 user는 채팅으로
리다이렉트). 화면은 좌측 내비게이션 22개 섹션(접이식 5개 그룹)으로 구성되며, 버튼이 보여도
실제 권한은 서버 RBAC이 결정한다(권한 부족 시 403). 모든 변경 요청은 CSRF 헤더가 자동 첨부된다.

## 섹션 구성

내비게이션은 화면에 나오는 한글 이름으로 적는다(코드의 섹션 id와 다르다).

| 그룹 | 섹션 |
|---|---|
| 운영 | 대시보드, 알림, 작업 큐, 설정, 감사 로그, 백업, 진단, 유지보수 |
| 사용자 | 사용자, 부서 관리, 직책 관리, Notion 사용자 연결 |
| 연동 | 외부 연동, 자동화 작업 실행기(러너), 업무 자동화 흐름(워크플로) |
| 콘텐츠 | 프롬프트, 정책, 템플릿 |
| 자동화 | 실행 일정(스케줄), 문서 자동 생성, 개발자 월간 리포트, 승인 |

> 나중에 생긴 system_admin 전용 화면 넷 — **초기 설정**(`#/setup`),
> **시스템 설정**(`#/system`), **Notion 관리**(`#/notion-console`),
> **AI 관리**(`#/llm-console`) — 의 사용법은 [CONSOLE_SCREENS.md](CONSOLE_SCREENS.md)
> 에 따로 있다. 이 화면들은 서버 자체(서비스 재시작, 타임존, 인증서)와 외부 연결
> (Notion 토큰, AI 백엔드)을 만지므로 다룰 때 알아야 할 경계가 많다.

## Dashboard

컴포넌트 상태(web/worker/scheduler — heartbeat 90초 초과 시 stale), 연동 서비스 헬스,
Runner/Workflow/Schedule 개수, 최근 24시간 Job 통계(성공률·평균 처리시간·실패 잔량),
최근 중요 감사 이벤트 5건, 디스크/메모리, TLS 만료 일수, 마지막 백업 상태.
운영 점검의 시작점 — worker가 stale이면 `docs/RUNBOOK.md` #1.

## 사용자 (admin+)

- **추가**: 회사 이메일(`goodmit.co.kr` 도메인 강제) + 이름 + 역할. 비밀번호를 비우면
  임시 비밀번호가 생성되어 **응답에 1회만** 표시된다 — 안전한 채널로 본인에게 전달
- **행 동작**: 상세 / 비활성·활성화 / 비번재발급 / 잠금해제 / 세션폐기
- 비활성화·비번재발급·역할 변경은 해당 사용자의 모든 세션을 즉시 폐기한다
- **역할 변경**: admin/system_admin으로 올리는 변경은 승인 대상 —
  system_admin이 아니면 202로 승인 요청이 생성되고 Approvals 섹션에서 결재된다
- 마지막 활성 system_admin은 비활성화·강등이 서버에서 차단된다
- 상세: `docs/USER_LIFECYCLE.md`

## Notion 사용자 연결

사용자별 매핑 상태(unmapped/verified/conflict), 재검증·해제 버튼.
conflict는 후보 목록에서 선택해 해결한다. 동작 원리는 `docs/NOTION_MAPPING.md`.

## Integrations / Runners / Workflows (연동 레지스트리)

- **Integrations**: 기존 서비스(n8n, work-assistant, ticket-runner 등) 목록 —
  설치 시 discovery로 시드됨. 헬스체크/활성/비활성, 설정 버전 이력과 롤백
- **Runners**(자동화 작업 실행기(러너)): 실행기 등록·헬스·테스트·circuit breaker — `docs/RUNNER_MANAGEMENT.md`
- **Workflows**(업무 자동화 흐름(워크플로)): n8n webhook 메타데이터, 도달성 테스트 — `docs/WORKFLOW_REGISTRY.md`

공통 규칙: URL은 SSRF allowlist에 있어야 저장 가능, 모든 변경은
`config_versions` 스냅샷으로 남고 특정 버전으로 롤백할 수 있다(롤백도 새 버전).

## Prompts / Policies / Templates

Prompt·Policy는 draft→test→review→published→archived 수명주기(발행은 이전 발행본을
자동 archive), Template은 Workflow/Runner를 향한 자동화 정의.
상세: `docs/PROMPT_POLICY_MANAGEMENT.md`.

## 실행 일정(스케줄)

cron(daily/weekly/monthly preset 지원) 또는 once 스케줄. 생성은 항상 **비활성** 상태 —
활성화는 승인 대상이다(system_admin은 즉시). dry-run(payload 미리보기 + 다음 3회 실행
시각), run-now(즉시 1회), 실행 이력과 실패 run 재시도. 상세: `docs/SCHEDULER.md`.

## 문서 자동 생성

문서 생성 요청 이력(모드/상태/품질 게이트 결과/발행 링크) 조회와 생성 요청.
상세: `docs/DOCUMENT_AUTOMATION.md`.

## 개발자 월간 리포트 (admin, system_admin, auditor)

마감일이 해당 월인 티켓을 담당자별로 집계한 조회 전용 리포트(기간은 `YYYY-MM`, 생략 시
이번 달). 담당자별 생산성이 담긴 민감 집계라 operator는 제외되고 감사 로그와 같은 역할 선에서만
본다. Notion 토큰이 아직 없으면 오류 대신 "연동 필요" 안내를 그린다.

## Approvals (결재함)

pending 승인 목록 — 요청 유형(schedule.enable / runner.change_config /
user.role_change / document.publish), 요청자, payload, 만료 시각(기본 72시간).
approve/reject는 admin+, **자기 요청은 승인 불가**. approve 시 저장된 payload가
원래 서비스 경로로 1회 실행되고, 실행 중 오류면 전체가 롤백되어 pending 유지가 아닌
오류로 표시된다. 요청자는 결과를 알림으로 받는다.

## Notifications

본인 수신 알림 목록(승인 요청/결정, Job 실패, 스케줄 실패, 계정 잠금 등)과 읽음 처리.

## Settings

수정 허용 목록에 있는 키만 노출. 각 키에 "재시작 필요/즉시" 배지 —
재시작 필요 항목은 저장 후 서버에서 systemctl 재시작을 해야 반영된다.
변경 전 dry-run 검증, 버전 이력에서 롤백 가능. 목록은 `docs/OPERATIONS.md` 참조.
일부 다크런치 기능은 이 목록이 아니라 별도 기능 플래그로 게이트된다 — 예로 팀 공간 실시간
퀴즈의 AI 문제 생성은 `game_ai_enabled` 플래그(기본 OFF)로 켜야 동작한다.

## Audit (admin, system_admin, auditor)

모든 상태 변경 이력: 시각, actor, action, 대상, before/after(민감 값은 `***` 마스킹),
결과, client IP, request_id. 조회 전용 — 수정·삭제 API는 존재하지 않는다.

## Backup (생성/검증은 system_admin)

수동 백업 실행(온라인 Backup API + 체크섬 + 임시 복원 검증), 기존 백업 재검증,
복원 절차 안내 조회. **실제 복원은 웹에서 불가** — `docs/BACKUP_RESTORE.md`.

## Maintenance

유지보수 모드 토글(admin+)과 공지 메시지 확인. 켜면 일반 user의 신규 요청이
503으로 차단되고 operator+는 계속 작업할 수 있다.

## 자주 하는 작업 요약

| 작업 | 위치 |
|---|---|
| 신규 입사자 계정 | 사용자 → 추가 → 임시 비밀번호 전달 → (필요 시) Notion 매핑 → 재검증 |
| 퇴사자 처리 | 사용자 → 비활성 (세션 자동 폐기) |
| 비밀번호 분실 | 사용자 → 비번재발급 → 임시 비밀번호 전달 |
| 로그인 잠금 해제 | 사용자 → 잠금해제 (또는 15분 자동 해제 대기) |
| 새 정기 자동화 | Workflows 등록 → Schedules 생성 → dry-run → 활성화(승인) |
| n8n 순단 후 정리 | Dashboard 확인 → Schedules 이력 retry, 실패 Job retry |
| 점검 공지 | Maintenance 켜기 → 작업 → 끄기 |
