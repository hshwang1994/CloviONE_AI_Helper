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

## 0. 한 줄 요약

**조사는 아직 수렴하지 않았다.** BACKLOG **292건**(사이클 0에서 대부분 신규). 판독한 화면 **11/70**에서
**66건**이 나왔고 화면당 약 6건 속도가 유지되고 있다 — 남은 65개 화면에서 새 결함이 계속 나온다는
뜻이므로 Sonnet 인계 기준(§5)을 아직 못 넘었다. 다음에 무엇을 집어 들지는 §3에 있다.

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
| C0-5 | 역할별 QA 계정 4개 | ✅ 완료 | `qa-user`·`qa-operator`·`qa-auditor`·`qa-admin` 생성. 서버 실계정 14개 중 12개가 `admin`이고 **operator·auditor가 0명**이라 역할 매트릭스를 재현할 방법이 애초에 없었다 |
| C0-6 | 하네스 원격 대응 | ✅ 완료 | `--insecure`(터널 불가 이유는 [DECISIONS D-05a](DECISIONS.md)) + 원격 강제 비밀번호 변경 처리. qa-admin으로 실서버 캡처 성공 |
| C0-8 | **첫 실환경 전 라우트 캡처** `c1-admin` | ✅ 완주 | 272페이지. **21검사 중 20개는 전 페이지 통과**, `tiny_text`만 134 fail(3840 전용, 1920은 skip). 모달 **512개를 실제로 열어** 7가지 기하 검사 전부 통과(공허한 pass 아님 — `capture.py:370` 가드 확인) |
| C0-9 | 실화면 눈 판독 | 🔄 **11/70** | `/projects`·`/schedules`·`/chat`·`/dashboard`(라이트·다크)·`/me`·`/users`·`/team-docs`·`/settings`·`/audit`·`/my-tickets`(4K)에서 **63건**(`VIS-01`~`63`). **그 화면들은 기계 검사 21종을 전부 통과했다.** `/audit`(100행)에서만 밀도 문제가 드러났다 — **데이터 많은 화면을 우선 판독해야 새 범주가 나온다** |
| C0-10 | 미감사 영역 추가 조사 | ✅ 완료 | `app/core`(12) · 미감사 19모듈(59) · registry 28화면↔API(8) · **러너 `assistant.py`(20, 라우터를 실제 실행해 재현)** |
| C0-7 | `git worktree prune` (잔재 88개) | 보류 | `du`가 2분 타임아웃 날 만큼 큼. 번들 스크립트가 `.claude`를 이미 제외하므로 배포 차단 요인은 아님 |

**조사 완료 영역** — 결과는 전부 [BACKLOG.md](BACKLOG.md)에 항목화(총 **269건**):
프런트 디자인 시스템 · 백엔드 기능/RBAC/배선 · 빌드/배포/테스트 · AI 도우미(백엔드 파이프라인 +
프런트 UX) · **`app/core/`(사상 최초)** · **미감사 모듈 19개(사상 최초)**.

**사이클 0에서 고친 것**(조사를 가능하게 하는 범위):
- `QA-07` 시간이 지나 스스로 깨진 프런트 테스트 → 픽스처를 상대값으로. `final_verify`를 막고 있었다
- `QA-09` **번들 무결성 검사가 모든 번들에서 항상 1건 실패**(매니페스트가 자기를 해싱) →
  `! -name MANIFEST.sha256` + 회귀 테스트 3건으로 핀

---

## 3. 다음 작업 (이어받는 사람이 그대로 집어 들 수 있게)

**조사는 아직 수렴하지 않았다.** 판독한 화면 5개에서 **43건**이 나왔고 화면당 6~9건 속도가
유지되고 있다 — 남은 65개 화면에서 새 결함이 계속 나온다는 뜻이다.

1. **PNG 판독을 계속한다** (가장 생산적). `dist/ui-qa-admin/c1-admin/{light,dark}/{1920x1080,3840x2160}/`에
   70라우트 × 2테마 × 2뷰포트가 있다. 판독한 것: `/projects`·`/schedules`·`/chat`·`/dashboard`(라이트)
   + `/dashboard`(다크). **아직 안 본 것 60개.** 데이터가 많은 화면(`/board`·`/games`·`/chat-rooms`·`/jobs`·`/notifications`)을 우선한다 — `/audit` 100행에서만 밀도 문제가 처음 나왔다. 판정 기준은 [DECISIONS](DECISIONS.md) D-06~D-12.
2. **`DS-32` 두 줄 고치고 재실행해 확인**한다 — `TopSearch.jsx:68` `fontSize:"11px"` +
   `Mascot.jsx:364` `fontSize="10px"`. `results.json`의 samples가 페이지마다 이 둘만 지목하므로
   **134건이 한 번에 사라질 것으로 본다**(확인 필요). 두 번째는 `sx`가 아니라 prop이라 grep에
   안 걸린다 — 정적 검사를 만들 때 두 형태를 모두 봐야 한다.
3. **역할 매트릭스 실행**. 계정은 만들어 뒀다(`qa-user`/`qa-operator`/`qa-auditor`/`qa-admin`,
   비밀번호는 `dist/ui-qa-*/credentials.json`). 역할별로 `--out-dir`을 따로 줘야 세션이 안 섞인다:
   ```bash
   UI_QA_EMAIL=qa-operator@goodmit.co.kr UI_QA_PASSWORD=... UI_QA_ROLE=operator \
   .venv/Scripts/python.exe -u -m scripts.ui_qa.run --label c1-operator --insecure --modals \
     --base-url https://clovirone-ai.gooddi.lab --viewports 1920x1080 --out-dir dist/ui-qa-operator
   ```
   보는 것: 메뉴 노출 · 데이터 범위 · "눌렀더니 403" 막다른 길 · `SEC-01`·`UB-01`·`UA-02` 재현.
4. **`F`~`L` 축은 아직 0%다** — 실제 조작·결과 데이터·관련 화면 반영·Console/Network.
   [QA_COVERAGE](QA_COVERAGE.md) §7의 흐름 9개가 착수 대상이다.
5. **판독 대상 우선순위 제안**: 아직 안 본 65개 중 `/team-docs`·`/board`·`/games`·`/my-tickets`·
   `/tickets/:id`·`/sprint`(사용자 핵심 흐름)와 `/settings`·`/audit`·`/notion-console`·`/llm-console`
   (관리자 밀도 높은 화면)을 먼저 보면 새 범주가 나올 가능성이 크다. 4K(3840) PNG도 같이 본다 —
   1920만 보면 `DS-24`(`xl` 구간 미지정) 같은 것이 안 드러난다.

---

## 3-1. 가장 먼저 손대야 할 것 (사이클 0이 남긴 결론)

러너에서 **재현까지 끝난** 세 건이 제품 전체에서 가장 위험하다 — AI가 사용자의 **질문과 거절을
승인 없는 Notion 쓰기로 바꾼다**:
- `RN-01` "그거 완료했어?" → 티켓이 완료로 바뀐다 (`norm()`이 `?`를 지우고, 질문 가드가 최상위
  라우터에 없다)
- `RN-02` "완료로 바꾸지 마" → 완료로 바뀐다 (부정 가드가 `is_approval_message` 안에만 있는데
  분기 ③이 그보다 먼저 돈다)
- `RN-03` 티켓 선택 대기 중 "그만할래" → 이전 변경이 쓰인다 (`is_update_intent`가 무조건 True)

그다음이 `SEC-01`(권한 경계) · `UA-01`(전사 데이터 노출) · `UB-01`(부서 admin이 전사 배너) ·
`UA-03`(백업 중 전체 쓰기 잠김) · `RG-01`(절대 작동 못 하는 버튼) · `DS-32`(4K 두 줄).

## 4. Blocker

| ID | 내용 | 영향 | 조치 |
|---|---|---|---|
| ~~B-1~~ | ~~테스트 서버가 HEAD가 아니다~~ | — | **✅ 해소됨** (2026-08-08 10:01, `UPGRADE_OK`+`DEPLOY_VERIFY_OK`). 이제 서버 = HEAD이므로 실물 조사 결과를 신뢰할 수 있다 |
| **B-2** | **Chrome 확장 미연결.** `mcp__claude-in-chrome__list_connected_browsers` → `[]` (4회 확인) | Chrome MCP 검증 불가(콘솔·네트워크 탭·수동 조작·폭 실시간 변경) | **사용자 조치 필요**: 확장이 Claude Code와 **같은 claude.ai 계정**으로 로그인됐는지 · 설치 후 Chrome 재시작 · 확장 팝업에서 연결 버튼 클릭. 그 전까지 Playwright 하네스(실제 Chromium·실제 로그인·실제 서버 DB)로 대체하고 PNG를 직접 판독 |
| ~~B-3~~ | ~~하네스가 자체서명 HTTPS를 못 탄다~~ | — | **✅ 해소됨** — `--insecure` 추가. **SSH 터널은 쓰면 안 된다**(서버가 `COOKIE_SECURE=true`라 Playwright API 클라이언트가 http로 세션 쿠키를 안 싣는다, [DECISIONS D-05a](DECISIONS.md)) |

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
