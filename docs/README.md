# 문서 색인

문서가 서른 개쯤 된다. 어디부터 볼지 몰라 헤매지 않도록 **하려는 일별로** 묶었다.
저장소 전체의 출발점은 루트 [`README.md`](../README.md) 다.

---

## 나는 지금 무엇을 하려고 하는가

| 하려는 일 | 볼 문서 |
|---|---|
| 새 서버에 설치한다 (git clone) | **[INSTALL_FROM_GIT.md](INSTALL_FROM_GIT.md)** |
| 새 서버에 설치한다 (번들 scp) | [MAINTENANCE_PLAYBOOK.md](MAINTENANCE_PLAYBOOK.md) |
| 이미 도는 서버를 최신으로 올린다 | **[INSTALL_FROM_GIT.md](INSTALL_FROM_GIT.md)** (git) / [MAINTENANCE_PLAYBOOK.md](MAINTENANCE_PLAYBOOK.md) (번들) |
| 되돌린다 | [INSTALL_FROM_GIT.md §5](INSTALL_FROM_GIT.md), [BACKUP_RESTORE.md](BACKUP_RESTORE.md) |
| 장애가 났다 | [RUNBOOK.md](RUNBOOK.md) |
| 느리다, 429 가 뜬다, 몇 명까지 되는지 알고 싶다 | **[NGINX_AND_CAPACITY.md](NGINX_AND_CAPACITY.md)** |
| 기능을 새로 만든다 | [EXTENSION_GUIDE.md](EXTENSION_GUIDE.md), [ARCHITECTURE.md](ARCHITECTURE.md) |
| 코드를 처음 읽는다 | [`CLAUDE.md`](../CLAUDE.md), [ARCHITECTURE.md](ARCHITECTURE.md) |
| 사용자에게 쓰는 법을 알려 준다 | [USER_GUIDE.md](USER_GUIDE.md), [ADMIN_GUIDE.md](ADMIN_GUIDE.md) |
| 무엇이 안 되는지 알고 싶다 | [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) |
| 다음에 무엇을 할지 정한다 | [WORK_PLAN_INDEX.md](WORK_PLAN_INDEX.md) |

---

## 설치와 운영

| 문서 | 내용 |
|---|---|
| [INSTALL_FROM_GIT.md](INSTALL_FROM_GIT.md) | git clone 으로 설치, 업데이트, 롤백. 폐쇄망 준비물. 번들 신선도 |
| [NGINX_AND_CAPACITY.md](NGINX_AND_CAPACITY.md) | gzip, 요청 속도 제한, 로그 회전, 동시 사용자 한계 |
| [OPERATIONS.md](OPERATIONS.md) | 서비스, 로그, 계정, 일상 운영 |
| [MAINTENANCE_PLAYBOOK.md](MAINTENANCE_PLAYBOOK.md) | 흔한 유지보수 작업의 단계별 레시피 (번들 배포 포함) |
| [RUNBOOK.md](RUNBOOK.md) | 장애 대응. 증상 → 진단 → 조치 |
| [BACKUP_RESTORE.md](BACKUP_RESTORE.md) | 백업은 앱과 스크립트 양쪽에서, 복원은 스크립트로만 |
| [DEPLOY_VERIFICATION.md](DEPLOY_VERIFICATION.md) | 배포 게이트와 사람이 눈으로 볼 체크리스트 |
| [DEPLOY_NOW.md](DEPLOY_NOW.md) | 특정 배포 건의 남은 절차 (시점 기록) |
| [INSTALLATION_REPORT.md](INSTALLATION_REPORT.md) | 2026-07-14 최초 설치 스냅샷 (기록) |

## 구조와 확장

| 문서 | 내용 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 시스템 구조, 계층, 데이터 흐름 |
| [EXTENSION_GUIDE.md](EXTENSION_GUIDE.md) | 기존 패턴을 따라 기능을 추가하는 절차 |
| [SECURITY.md](SECURITY.md) | 보안 모델. 모든 통제는 서버 측에서 강제된다 |
| [USER_LIFECYCLE.md](USER_LIFECYCLE.md) | 계정 수명주기. 웹 관리자 API 와 CLI 가 같은 서비스를 쓴다 |
| [TEST_SCENARIOS.md](TEST_SCENARIOS.md) | 테스트 스위트 개요와 실행 방법 |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | 의도된 설계 결정과 아직 없는 것의 구분 |

## 기능별 상세

| 문서 | 내용 |
|---|---|
| [USER_GUIDE.md](USER_GUIDE.md) | 사용자 콘솔 사용 안내 |
| [ADMIN_GUIDE.md](ADMIN_GUIDE.md) | 관리자 콘솔 안내 |
| [DASHBOARD_METRICS.md](DASHBOARD_METRICS.md) | 화면에 뜨는 모든 숫자의 출처표 |
| [SCHEDULER.md](SCHEDULER.md) | 스케줄 실행. 별도 데몬이 아니라 worker 안에서 돈다 |
| [PROMPT_POLICY_MANAGEMENT.md](PROMPT_POLICY_MANAGEMENT.md) | Prompt / Policy / Template 의 불변 버전 모델 |
| [DOCUMENT_AUTOMATION.md](DOCUMENT_AUTOMATION.md) | 문서 자동 생성과 발행. 웹 앱은 Notion 토큰을 갖지 않는다 |
| [WORKFLOW_REGISTRY.md](WORKFLOW_REGISTRY.md) | n8n workflow 를 메타데이터로 등록 관리 |
| [RUNNER_MANAGEMENT.md](RUNNER_MANAGEMENT.md) | 로컬 HTTP 실행기 레지스트리 |
| [RUNNER_HANDOFF.md](RUNNER_HANDOFF.md) | 이 저장소에서 고칠 수 없는 n8n 쪽 변경 요청 |
| [NOTION_MAPPING.md](NOTION_MAPPING.md) | 로그인 이메일과 Notion People 의 연결 |

## 계획과 이력

| 문서 | 내용 |
|---|---|
| [WORK_PLAN_INDEX.md](WORK_PLAN_INDEX.md) | 흩어진 계획을 모은 권위 있는 전체 목록. 새 세션은 여기부터 |
| [PRODUCTIZATION_ARCHITECTURE.md](PRODUCTIZATION_ARCHITECTURE.md) | 약 1000명 규모 제품화 아키텍처 계획 |
| [NEXT_SESSION_PLAN.md](NEXT_SESSION_PLAN.md) | 다음 세션 작업 계획 |
| [IDEAS_BACKLOG.md](IDEAS_BACKLOG.md) | 제품 전체 아이디어 백로그 (미확정) |
| [IMPROVEMENT_DIRECTIVE.md](IMPROVEMENT_DIRECTIVE.md) | 사용자가 제시한 상시 개선 기준 (원문 요약) |
| [BUILD_LOG.md](BUILD_LOG.md) | 세션 간 인수인계 기록. 최신이 위 |

## 문서가 아닌 것

- `docs/migration_backups/` - 마이그레이션 전 데이터 스냅샷(JSON). 읽는 문서가 아니다
- `docs/n8n/` - n8n 워크플로 관련 자료
