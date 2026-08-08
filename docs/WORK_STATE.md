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

**마지막 갱신**: 2026-08-08 · **단계**: Opus 전수조사 (구현 전) · **브랜치**: `ui/mui-migration`

---

## 1. 현재 단계

**Opus 조사 단계.** 제품 코드 구현·리팩터링을 하지 않는다. 전수조사로 문제를 최대한 발견해
BACKLOG와 계획을 실행 가능한 수준까지 완성한 뒤 Sonnet 구현 단계로 인계한다.

조사를 가능하게 하는 작업만 예외로 수행한다: HEAD 배포 · QA 하네스 보강 · QA 계정 생성 ·
worktree 정리 · 이 문서들 작성.

**사이클**: 0 (준비) → 진행 중

---

## 2. 완료한 범위

| # | 항목 | 상태 | 증거 |
|---|---|---|---|
| C0-1 | 지속 작업 문서 6종 생성 | ✅ 완료 | `WORK_STATE`·`WORK_PLAN_INDEX`·`BACKLOG`·`QA_COVERAGE`·`DECISIONS`·`BUILD_LOG` + `CLAUDE.md` §0 |
| C0-3 | **전체 백엔드 스위트 HEAD 완주 (역대 최초)** | ✅ 완료 | `pytest tests/ -q` **exit 0**, 100%, 실패 0 (`var/pytest_head_run.log`). 라운드 14가 두 번 중단돼 못 하던 것 |
| C0-3b | 프런트 스위트 | ✅ 완료 | `npx vitest run` **172파일 / 1212 테스트 전부 통과** (QA-07 수정 후) |
| C0-3c | 정적 검사 · 마이그레이션 리허설 | ✅ 완료 | `STATIC_CHECKS_OK` · `REHEARSAL_OK`(왕복 후 스키마·76테이블 행수 동일, `integrity_check ok`) |
| C0-2 | **HEAD를 테스트 서버에 배포** | ✅ 완료 | `UPGRADE_OK` → `DEPLOY_VERIFY_OK`(healthz/readyz 200, 정적 자산 **30/30 새 번들**, 새 라우트 401, CSP 새 정책). 파일 해시 5종 로컬=서버 일치, 번들명 `AdminRoutes.2BH7K_x6.js` 일치 |
| C0-4 | QA 하네스 라우트 보강 | ✅ 완료 | 62 → **70 라우트**(`/projects`·`/projects/:id`·`/ideas`·`/system`·`/setup`·`/notion-console`·`/llm-console`). 원격 강제 비밀번호 변경 처리도 추가 |
| C0-5 | 역할별 QA 계정 4개 | ⏳ 다음 | 서버 계정 14개 중 **operator·auditor가 0명**, `user`는 비활성 1명뿐이라 역할 매트릭스 재현 불가임을 확인 |
| C0-6 | QA 하네스 전체 매트릭스 1회 실행 | ⏳ 다음 | SSH 터널 경유 |
| C0-7 | `git worktree prune` (잔재 88개) | 보류 | `du`가 2분 타임아웃 날 만큼 큼. 번들 스크립트가 `.claude`를 이미 제외하므로 배포 차단 요인은 아님 |

**조사 완료 영역** — 결과는 전부 [BACKLOG.md](BACKLOG.md)에 항목화(총 197건):
프런트 디자인 시스템 · 백엔드 기능/RBAC/배선 · 빌드/배포/테스트 · AI 도우미(백엔드 파이프라인 +
프런트 UX) · **`app/core/`(사상 최초)** · **미감사 모듈 19개(사상 최초)**.

**사이클 0에서 고친 것**(조사를 가능하게 하는 범위):
- `QA-07` 시간이 지나 스스로 깨진 프런트 테스트 → 픽스처를 상대값으로. `final_verify`를 막고 있었다
- `QA-09` **번들 무결성 검사가 모든 번들에서 항상 1건 실패**(매니페스트가 자기를 해싱) →
  `! -name MANIFEST.sha256` + 회귀 테스트 3건으로 핀

---

## 3. 다음 작업

1. C0-2 **HEAD 배포**를 끝낸다 — 이게 안 되면 이후 Chrome 조사가 통째로 오염된다(아래 Blocker B-1).
2. C0-4 QA 하네스를 서버에 겨누고 전체 매트릭스 1회 실행 → PNG 판독 → BACKLOG 반영.
3. 사이클 1 전수조사: 아직 아무도 안 본 영역부터(§4 Coverage 공백).
4. 사이클 2 이후 수렴할 때까지 반복.

---

## 4. Blocker

| ID | 내용 | 영향 | 조치 |
|---|---|---|---|
| ~~B-1~~ | ~~테스트 서버가 HEAD가 아니다~~ | — | **✅ 해소됨** (2026-08-08 10:01, `UPGRADE_OK`+`DEPLOY_VERIFY_OK`). 이제 서버 = HEAD이므로 실물 조사 결과를 신뢰할 수 있다 |
| **B-2** | **Chrome 확장 미연결.** `mcp__claude-in-chrome__list_connected_browsers` → `[]` (4회 확인) | Chrome MCP 검증 불가(콘솔·네트워크 탭·수동 조작·폭 실시간 변경) | **사용자 조치 필요**: 확장이 Claude Code와 **같은 claude.ai 계정**으로 로그인됐는지 · 설치 후 Chrome 재시작 · 확장 팝업에서 연결 버튼 클릭. 그 전까지 Playwright 하네스(실제 Chromium·실제 로그인·실제 서버 DB)로 대체하고 PNG를 직접 판독 |
| B-3 | QA 하네스가 자체서명 HTTPS를 못 탄다 (`run.py:52` `urlopen`, `new_context()`에 TLS 예외 없음) | 서버를 직접 못 겨눔 | SSH 터널로 우회(하네스 무수정). CSP는 nginx가 아니라 `app/core/middleware.py`가 내므로 검사 대상 유지 — 확인함 |

---

## 5. 환경 사실 (매번 다시 조사하지 말 것)

**서버** `cloviradmin@10.100.64.71` · `https://clovirone-ai.gooddi.lab` · Ubuntu 24.04 ·
**테스트 서버다**(운영 아님, 사용자 확인). SSH 키 인증, sudo는 비밀번호(stdin으로만 전달).

서비스 상태(2026-08-08 확인): `clovirone-web-assistant`·`clovirone-web-worker`·`nginx` 전부 active ·
러너 `:8787`(ticket)·`:8788`(interpreter v2.1.1)·`:8789`(work-assistant v3.57.0) healthy ·
n8n `:5678` active, 워크플로 2개 active + 웹훅 2개 등록(`clovirone-work-assistant`,
`clovirone-notion-user-mapping`) · Claude CLI 2.1.197 · `ASSISTANT_MODEL=sonnet`(systemd env).

**데이터 규모**(서버 DB): users 15 · conversations 66 · messages 237 · ticket_cache 1077.
DB는 `/var/lib/clovirone-web-assistant/web.sqlite3`(읽기는 `sudo sqlite3 -readonly`).

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
