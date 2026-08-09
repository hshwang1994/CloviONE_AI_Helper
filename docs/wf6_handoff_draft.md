# ClovirONE Web Assistant — Opus → Sonnet 인계 문서
**작성**: 2026-08-09 · **브랜치** `ui/mui-migration` (HEAD `7f2b1be`, clean) · **단계**: 전수조사 종료 → **구현 착수**

---

## 1. 이번 라운드 Critical/High

**Critical: 없음.** (5라운드 중 처음)

**High 2건** — 둘 다 코드로 직접 확인했다.

### H-1. 본문 저장이 **읽은 적도 없는 자식 블록을 통째로 지운다** (데이터 유실)
`app/tickets/notion_write.py:240-271, 309-312, 360-375` · `app/team_docs/notion_docs.py:458-484, 503, 565-573` · `app/core/notion_blocks.py:30-56`

`fetch_page_blocks` 는 **1레벨 children 만** 읽는데, `_EDITABLE_BLOCK_TYPES` 에는 자식을 가질 수 있는 텍스트 블록 11종(`paragraph`·`heading_1~3`·`bulleted_list_item`·`numbered_list_item`·`to_do`·`quote`·`callout`·`toggle`·`code`)이 전부 들어 있어 저장 시 **DELETE 대상**이 된다. 편집기에 실려 오지도 않은 토글 속 글·콜아웃 속 문단·**중첩 글머리 목록(2단계 이하)** 이 부모와 함께 사라진다.

**내가 직접 재확인한 증거**
- `grep -rn "has_children" app/ frontend/src` → **0건**. 자식을 읽는 코드가 저장소에 없다.
- `notion_write.py:367` / `notion_docs.py:572` = `deletable = [bid for bid, btype in refs if not btype or btype in _EDITABLE_BLOCK_TYPES]` — 두 파일 동일.
- `markdown_to_blocks`(`notion_blocks.py:34`)가 `s = ln.strip()` 으로 들여쓰기를 버리므로 **우리 편집기로는 복구도 불가능**하다.
- `_EDITABLE_BLOCK_TYPES` 자신의 주석이 *"지우면 사용자가 만든 적도 없는 내용을 없애는 것이 된다"* 고 적어 둔 바로 그 사고가, 이미지·표가 아니라 **자식 계층**에 그대로 남아 있다.
- ⚠️ 미검증 1점: "Notion 은 부모를 지우면 자식도 아카이브한다" 는 외부 API semantics 라 로컬에서 확인 불가. 다만 그와 무관하게 부모가 사라지면 자식 서브트리는 본문에서 없어진다.

**범위 축소 주의**: 블록 종류 하향 변환(`quote→paragraph`, `to_do→bulleted`, `code→문단`, `callout/toggle→문단`)은 `notion_blocks.py:62,140` 과 `EditableBody.jsx:141-142` 에 **의도가 명시**돼 있다 — 결함이 아니다. 고칠 것은 **자식 유실 하나**다.

### H-2. `/settings` '세션 정책' 편집기를 열면 **화면이 크래시한다**
`frontend/src/screens/settings/StructuredObjectFields.jsx:1-6` (import 블록) vs `:135, :145` — 정의는 `settingsRegistry.js:92`

**내가 직접 확인한 증거**
- import 블록 실물 6줄: `React / Box / Chip / TextField / Typography / Button` — **`fmtDuration` 없음**.
- `:135`, `:145` 가 `= {fmtDuration(safe.idle_timeout_seconds)}` / `= {fmtDuration(safe.absolute_timeout_seconds)}` 를 호출.
- `settingsRegistry.js:92` 에 `export function fmtDuration(sec)` 가 실재 — **같은 디렉터리, 한 줄 import 누락**.
- 렌더 중 `ReferenceError` → `App.jsx:89` 경로별 ErrorBoundary 가 본문을 오류 화면으로 교체. **탈출구 없음**: 'JSON 으로 직접 편집(고급)' 토글이 `SettingEditor.jsx:233-238` 로 던지는 자식 뒤에 있어 마운트되지 않는다.
- 결과: **유휴 제한·최대 세션 길이를 관리 콘솔에서 편집할 수 없다.**
- 주석 `:133-134` 가 *"표 요약과 같은 fmtDuration 으로"* 라고 **의도를 밝히고 있어** 일부러 뺀 것이 아님이 확실하다.

**한 줄 수정**: `import { fmtDuration } from "./settingsRegistry.js";`

---

## 2. 최종 수렴 판정

### 발견 곡선 (5라운드 실측)

| 라운드 | 대상 | 원 보고 | 폐기 | 채택 | **Crit** | **High** | Med | Low | High 비중 | Low 비중 |
|---|---|---|---|---|---|---|---|---|---|---|
| WF1 | 미판독 화면 40개 | 175 | 102 (58%) | **73** | 0 | 7 | 42 | 24 | 9.6% | 33% |
| WF2 | 백엔드 미조사 6영역 | 67 | 11 (16%) | **56** | **2** | **11** | 27 | 16 | 19.6% | 29% |
| WF4 | High 공백 6영역 | 69 | 24 (35%) | **45** | **2** | 3 | 16 | 24 | 6.7% | 53% |
| WF5 | 잔여 공백 6영역 | 85 | 25 (29%) | **60** | 1 | 6 | 19 | 34 | 10% | 57% |
| **R6 (이번)** | **마지막 미조사 영역** | 51 | 14 (27%) | **37** | **0** | **2** | 12 | 23 | **5.4%** | **62%** |

누적 채택 **271건** → BACKLOG **511항목**.

### 판정: **탐색은 수렴했다. 검증은 시작도 안 했다.**

#### ✅ 새 큰 범주는 멈췄다 — 근거 5가지

1. **Critical 곡선이 0으로 끝났다.** `0 → 2 → 2 → 1 → 0`. WF2·WF4·WF5 가 낸 Critical 5건(`SEC-30`·`OPS-01`·`OPS-10`·`SYS-01`·`DEPLOY-01`)은 전부 **배포·권한·게이트** 축이었고, 그 축을 이번 라운드가 다시 훑었는데 새 Critical 이 없다.
2. **High 비중이 5.4% 로 최저.** 그리고 남은 High 2건은 **새 범주가 아니다** — H-1 은 기존 `문서/티켓 Notion 쓰기` 범주, H-2 는 기존 `설정 화면` 범주 안이다.
3. **Low 비중이 62% 로 최고이고, 그 성격이 바뀌었다.** 이번 Low 23건 중 **10건이 "코드는 맞는데 주석·docstring·설명문이 거짓"** 유형이다(`worker_main.py:298-299`, `llm_connection_test.py:68-69`, `versioning.py:3`, `tenant_config.py:113-114`, `registry.py:259-261`, `CONSOLE_SCREENS.md:185`, `screens.css:231-232` 등). 실행 결함이 고갈되고 **문서 정합만 남았다**는 신호다.
4. **신규 범주 0개.** 37건 전부 기존 36범주 안에 들어가고, **5건은 검증자가 직접 "기존 항목에 붙여라"** 라고 지목했다 — `SYS-08`(LLM 센티널 비대칭), `VIS-129`(RBAC 행 누락), `VIS-54`(smtp 요약), `AI-33`(마크다운 링크), `UA-26`(오프보딩 후계자).
5. **반증률이 안정됐다.** 58% → 16% → 35% → 29% → **27%**. WF1 의 58% 는 "혼자 스크린샷만 보고 판정"의 값이었고, 이후 4라운드가 27~35% 대에서 평평하다 — 판독 방법이 수렴했고, 남은 오차는 방법이 아니라 표본 문제다.

#### ❌ 그러나 "완료"가 아니다 — 검증 축은 0%

`docs/BACKLOG.md` 상태 열 실측(`grep -c`):

```
발견        325
작업예정      9
구현완료      9
작업중        2
배포완료      1
검증대기      1
실환경검증완료  2   ← 511항목 중 2건
```

이 저장소의 정의상 **`실환경검증완료`만 완료**다(`CLAUDE.md §0`). 즉 **조사는 끝났고 구현·검증은 착수 전**이다. WORK_STATE 최상단의 "❌ 수렴하지 않았다" 는 **① 새 큰 범주 ② 안 본 영역** 두 조건 기준이었고, 이번 라운드로 그 둘은 충족됐다 — 그러나 그 문서가 말하는 세 번째 조건은 어디에도 문장으로 적혀 있지 않다(§6 참조).

**따라서 인계 성격은 "조사 종료 → 구현 착수"이고, "제품 완성"이 아니다.** WORK_STATE §0 의 "❌ 수렴하지 않았다" 블록은 Sonnet 이 §3-1단계를 마친 뒤 이 판정으로 갱신해야 한다.

#### 지배적 결함 유형은 5라운드 내내 같았고 이번에도 같다

> **규칙·헬퍼·술어·토큰이 이미 있는데 부르는 쪽이 안 부른다.**

이번 라운드의 재확인 사례:
- `fmtDuration` 이 **같은 디렉터리에 export 돼 있는데** import 안 함 (H-2)
- `trimUrlTail` 이 `chat-text.js:38-54` 에 **있는데** AI 링크화기가 안 씀
- `etag_json_response` 가 **있는데** 가장 팬아웃 큰 `/api/team-chat/rooms` 만 안 씀
- `prefersReducedMotion()` 이 `motion.js` 에 **있는데** `scrollIntoView` 가 안 씀
- `_transfer_room_ownership` 이 **있는데** `archive_user` 가 안 부름
- `_present_players` 결과를 **화면이 못 받음**(`_member_view` 에 `last_seen` 없음)
- `Maintenance.jsx:233-235` 가 **이유까지 적어 고쳐 놓은 패턴**을 원본 `SettingEditor` 가 역이식받지 못함

**구현 단계는 "만들기"가 아니라 "배선하기"다.** 아래 순서를 그 원칙으로 묶었다.

---

## 3. Sonnet 구현 순서

> 각 단계는 **한 PR / 한 배포 단위**다. 단계마다 `.venv/Scripts/python -m pytest` 전체 green + `bash scripts/static_checks.sh` → `STATIC_CHECKS_OK` 가 **공통 완료 기준**이며 아래에는 그것 외의 것만 적는다.
> `실환경검증완료` 로 올리기 전에는 어떤 항목도 완료 처리하지 않는다.

### 🔴 0단계 — **사용자가 해야 할 것** (Sonnet 이 할 수 없음, 지금 바로)

| # | 무엇을 | 왜 지금 | 명령/조치 | 확인 방법 |
|---|---|---|---|---|
| **U-1** | `OPS-01` **업로드 디렉터리 소유권 복구** | **2026-08-07부터 실서버에서 파일 첨부가 안 올라간다.** `uploads` 만 root:clovirone-web 750 이라 서비스 사용자에게 쓰기 비트가 없다. 마지막 성공 업로드 2026-08-05 00:23. **업그레이드로 안 고쳐진다** | `sudo chown -R clovirone-web:clovirone-web /var/lib/clovirone-web-assistant/uploads` | `sudo runuser -u clovirone-web -- test -w /var/lib/clovirone-web-assistant/uploads && echo OK` → `OK` · 그 뒤 웹에서 티켓에 파일 1개 첨부 |
| **U-2** | `SEC-20` **sudo 비밀번호 회전** | 이전 조사가 sudo 비밀번호를 **명령행에 반복 노출**했고 워크플로 프롬프트로 서브에이전트 13개에 배포했다. 불변규칙 §2-4 위반이며 **손상된 것으로 간주해야 한다** | 서버에서 직접 `passwd` (Claude 에게 새 값을 주지 않는다) | 새 비밀번호로 sudo 1회 성공 |
| **U-3** | `SEC-10` Notion 문서 1건의 **평문 자격증명** 제거 | 원본이 실고객 워크스페이스라 Claude 가 손대면 안 된다 | 해당 Notion 페이지에서 수동 제거 + 그 자격증명 회전 | 사용자 눈으로 확인 |
| **U-4** | `SCHD-01` **스케줄을 켜지 말 것** | 유일한 스케줄이 AI 채팅 웹훅을 가리켜, 「활성」을 켜는 순간 매주 월 09:00 에 **실고객 Notion 쓰기**가 나갈 수 있다 | 조치 아님 — **금지** | `/schedules` 에서 비활성 유지 확인 |

> **U-1 은 다른 모든 단계의 선행 조건이 아니다** — 병렬로 진행해도 된다. 다만 첨부 관련 항목(`ATT-01`·`BKP-01`)의 실환경 검증은 U-1 이후에만 가능하다.

---

### 1단계 — **배포 경로 복구** (`DEPLOY-01` + `DEPLOY-02`) 🔴 Critical

- **무엇을**: `upgrade-clovirone-web-assistant.sh` 가 installer 에 `DNS_NAME`·`BIND_IP` 를 넘기게 하고, 번들 경로에도 `rollback_now()` 를 붙인다.
- **왜 지금**: **문서(`MAINTENANCE_PLAYBOOK.md §2`)대로 업그레이드하면 반드시 실패하고 web·worker 가 정지한 채 남는다.** installer 는 두 값이 없으면 `install-*.sh:46-51` 에서 `exit 2` 인데, 그 시점엔 이미 두 서비스를 정지시킨 뒤이고 되살리는 코드가 없다. git 경로에는 `rollback_now()` 가 있는데 번들 경로에만 없다. **이 단계를 먼저 하지 않으면 2~11단계의 "배포 후 재검증"을 한 번도 못 한다.**
  - ※ WORK_STATE §3-1 은 최우선을 `SYS-01` 로 적었다. 그 판단은 옳지만, **재검증 자체가 배포에 의존**하므로 DEPLOY-01 을 게이트로 앞세운다.
- **어느 파일**: `scripts/upgrade-clovirone-web-assistant.sh` · `scripts/install-clovirone-web-assistant.sh:46-51` · `docs/MAINTENANCE_PLAYBOOK.md §2` · `docs/OPERATIONS.md`
- **같이 태울 것 (무료)**: **H-2 한 줄 import**(`StructuredObjectFields.jsx`). 첫 배포에서 함께 검증하면 라운드 최고 ROI.
- **완료 기준**: ① 정지→실패 경로에서 두 서비스가 **자동 복구**된다(고의로 실패시켜 확인) ② 플레이북 §2 명령을 **글자 그대로** 복사·붙여넣기해서 성공 ③ 번들 경로 롤백 함수 존재.
- **배포 후 재검증**:
  ```
  systemctl is-active clovirone-web-assistant clovirone-web-worker   → active active
  curl -sk https://clovirone-ai.gooddi.lab/api/health                 → 200
  ```
  + 브라우저로 `/settings` → '세션 정책' 행 열기 → **오류 화면이 아니라 편집 폼과 `= 30분` / `= 8시간` 표시가 뜬다**(H-2 확인).

### 2단계 — `SYS-01` TLS 교체 무동작 🔴 Critical

- **무엇을**: `app/sysops/actions_service.py:40-41` 의 하드코딩 경로(`/etc/ssl/clovirone/server.crt`)를 **`settings.tls_cert_path`** 로 바꾼다.
- **왜 지금**: 인증서 교체가 openssl 쌍 검증 → 파일 기록 → `nginx -t` 통과 → reload 성공 → **새 인증서의 subject·만료일과 함께 "교체했습니다"** 를 보여 주는데 **브라우저는 계속 옛 자체서명 인증서를 받는다**. `/setup`·`/diagnostics` 는 올바른 경로를 읽으므로 교체 후에도 옛 만료일을 보여 줘 관리자는 "아직 반영이 안 됐나" 로 읽는다. `CLAUDE.md §10` 의 남은 조치가 정확히 이 경로다.
- **제품 안에 정답이 이미 있다**(D-22): `probe_tls` 와 `app/health/service.py` 가 `settings.tls_cert_path` 를 쓴다. **sysops 만 하드코딩했다.**
- **어느 파일**: `app/sysops/actions_service.py:40-41` · `app/sysops/router.py:32`(같이: `require_roles(ROLE_SYSTEM_ADMIN)` 리터럴 → `SYSTEM_ADMIN_ONLY` 그룹 상수. 저장소에서 그룹 상수를 안 쓰는 **유일한** 라우터다)
- **완료 기준**: 세 소비자(`sysops` · `probe_tls` · `health`)가 **같은 한 값**을 읽는 회귀 테스트.
- **배포 후 재검증**: 관리 콘솔에서 인증서 교체 → **브라우저 주소창 자물쇠 → 인증서 보기 → 새 subject/만료일** 확인(nginx 가 실제로 서빙하는 것). 동시에 `/diagnostics` 의 만료일도 같이 바뀌는지.

### 3단계 — `SEC-30` CSV 가져오기 권한 상승 우회 🔴 Critical

- **무엇을**: 권한 상승 게이트(`ensure_can_manage_target`)를 **`create_user` 안으로 옮겨** 웹 폼·CSV 일괄·CLI **세 경로가 한 관문을 지나게** 한다.
- **왜 지금**: 같은 "역할 부여"가 세 경로에서 **세 가지 규칙**(403 / 승인 / **무검사**)을 갖고, 무검사 경로로 `admin` 이 `system_admin` 을 만들 수 있다. `WF2-R1`(부차 경로가 관문 밖)의 가장 심한 사례이고, 이번엔 읽기가 아니라 **권한 부여**다.
- **어느 파일**: `app/users/service.py`(`create_user`) · CSV 일괄 임포트 경로 · `app/cli/user_cli.py`
- **같이 묶을 것**: `SEC-22` — `anomalies.py:49-59` 의 `SENSITIVE_ACTION_PREFIXES` 에 `"user."` 만 있어 **`cli.user.*` 가 하나도 매칭 안 된다**(off_hours·critical_action·new_actor_action 3규칙이 CLI 계정 조작을 못 잡는다). **`app/audit/actions.py` 신설로 두 모듈이 한 목록을 공유**하게 한다. 같은 사실이 두 벌이면 한쪽만 고쳐지는 이 상태가 재발한다.
- **완료 기준**: `tests/security/` 에 **세 경로 각각**이 같은 403 을 내는 테스트 3개. CLI 로 역할을 올리면 이상 탐지 규칙 3개가 뜨는 테스트.
- **배포 후 재검증**: `admin` 계정으로 ① 웹 폼 ② CSV 업로드 ③ CLI 로 각각 `system_admin` 생성 시도 → **셋 다 거부**. 그 뒤 `/audit` 에서 `cli.user.set_role` 이 이상 징후로 뜨는지.

### 4단계 — `FN-40` + 운영 내구성 (`OPS-10`·`OPS-11`) 🔴 Critical + High

- **무엇을**:
  - `FN-40`: `AnnouncementPatch.body` 가 `str|None` 인데 컬럼은 `nullable=False`. **POST 경로는 이미 `or ""` 로 막고 있다 — PATCH 만 빠졌다.** PATCH 루프에 같은 처리.
  - `OPS-10`: `worker_lock.acquire()` 가 `os.open` 의 `FileExistsError` **만** 잡아 `EACCES`/`ENOSPC`/`EIO` 가 `main()` 을 관통 → systemd 3초 재시작 → **상한 없는 루프**. `except OSError` 로 넓혀 **리스 경쟁**과 **파일시스템 고장**을 구분, 후자는 백오프. 유닛에 `RestartSec` 상향 + `StartLimitIntervalUSec`.
  - `OPS-11`: `beat_liveness()` 는 예외를 다 가두는데 **바로 다음 줄 `lock.renew()` 는 무방비** → 데몬 스레드만 죽고 본 루프는 계속 돈다(대시보드는 「워커 중단」인데 워커는 잡을 처리 중).
- **왜 지금**: `OPS-01` 이 보여 주듯 **이 서버에서 권한 어긋남은 이미 일어났다.** 디스크가 차거나 소유권이 어긋나면 `OPS-10` 은 즉시 발생한다. `FN-40` 은 한국어 UI 에 영어 "Internal server error" 만 뜨는 500 이고 수정은 한 줄이다.
- **어느 파일**: `app/*/schemas.py`(AnnouncementPatch) + 공지 PATCH 라우터 · `app/core/worker_lock.py` · `app/worker_main.py` · `deploy/systemd/clovirone-web-worker.service`
- **완료 기준**: `tests/regression/` 에 ① 공지 body 빈 문자열 PATCH → 200 ② `EACCES` 주입 시 워커가 **백오프하고 traceback 으로 죽지 않는다** ③ `renew()` OSError 시 본 루프가 스레드 사망을 감지.
- **배포 후 재검증**: 공지 편집에서 내용을 비우고 저장 → **한국어 검증 메시지 또는 정상 저장**(500 아님). `journalctl -u clovirone-web-worker --since "10 min ago"` 에 재시작 루프 없음.

---

> 여기까지가 Critical 축이다. **아래부터는 이번 라운드 37건을 "배선 단위"로 묶었다.** 개별 항목이 아니라 **한 배선점을 고치면 여러 건이 동시에 닫히는 묶음**이다.

### 5단계 — 🔌 **설정 화면 배선 한 묶음** (High 1 + Low 3)

- **무엇을**
  1. **H-2** `import { fmtDuration } from "./settingsRegistry.js";` (1단계에 태웠다면 확인만)
  2. `session_policy` **설명문 정정** — `registry.py:259-261` 이 두 필드를 뭉뚱그려 `"신규 세션부터 적용"` 이라 하는데 **`idle_timeout_seconds` 는 저장 즉시 이미 열려 있는 모든 세션에 적용된다**(줄이면 그 자리에서 전원 로그아웃, 저장한 관리자 본인 포함). `absolute_timeout_seconds` 만 '신규부터'가 맞다. **레지스트리 바로 위 줄 `:257-258` password_policy 에는 `"즉시 적용"` 이라 정확히 적혀 있다** — 관용은 이미 있고 이 칸만 오기다. `securityDowngradeWarning`(`settingsRegistry.js:167-176`)이 **늘릴 때만**(`>`) 경고하므로, 즉시 전원을 끊는 '줄이기'에도 확인을 붙인다.
  3. **테스트 게이트 자체의 드리프트** — `settings-labels.test.js:26-27` 의 손유지 목록 `OBJECT_TYPES` 에 **`smtp` 가 빠져 있고**, 레지스트리에서 이미 사라진 **`retry_policy` 가 남아 있다**(`grep -rn _retry_policy app/` → 정의 1건, 호출 0건 = 죽은 검증기). 이 목록을 없애고 `registry.py` 에서 `"object"` 타입을 정규식으로 뽑아 쓴다. 그러면 **VIS-54**(smtp 행이 잘린 raw JSON 으로 나옴)가 같이 닫힌다.
  4. `SettingEditor.jsx:172,174` — 읽기 전용 역할에게 버튼을 **없애지 말고** `disabled` + `aria-describedby`. **정답이 제품 안에 있다**: `Maintenance.jsx:233-241` 이 같은 실수를 겪고 고친 뒤 *"예전엔 '미리 검증'만 canWrite 일 때 렌더돼, 읽기 전용 역할에겐 그 기능의 존재 자체가 사라졌다"* 라고 주석으로 남겨 뒀다.
- **왜 지금**: H-2 가 이 화면군을 **통째로 막고 있고**, 이 4건이 전부 같은 3파일 안에 있다. 게이트(3번)를 먼저 고치면 5·6번째 object 설정이 추가될 때 같은 결함이 재발하지 않는다.
- **어느 파일**: `frontend/src/screens/settings/{StructuredObjectFields,SettingEditor,SettingsMain}.jsx` · `settingsRegistry.js` · `settings-labels.test.js` · `app/settings/registry.py:230,259-261` · `docs/MAINTENANCE_PLAYBOOK.md:99`
- **완료 기준**: `STRUCTURED_OBJECT_KEYS` **4개를 각각 렌더하는 스모크 테스트**(현재 이 화면군에 렌더 테스트가 **0개**다) + object 타입 전 키에 `summarizeSetting(key, 기본값) != null` 단언. `_retry_policy` 삭제.
- **배포 후 재검증**: `/settings` 에서 object 설정 **6개 행을 모두 열어 본다**(session_policy·smtp 포함) → 크래시 0, smtp 가 raw JSON 이 아닌 한국어 요약. `auditor` 계정으로 열어 버튼이 **보이되 비활성**인지.

### 6단계 — 🔌 **Notion 본문 쓰기 안전** (High 1 + Med 1 + Low 1)

- **무엇을**
  1. **H-1**: `page_block_refs` 가 `has_children` 도 함께 읽어 **자식이 있는 블록을 `deletable` 에서 제외**한다(이미지·표와 같은 취급). 남으면 `EditableBody` 에 *"원본에 접힌/중첩된 내용이 있어 그 블록은 지우지 않았다"* 를 알린다. **`EditableBody.jsx:147-154` 의 기존 경고는 손실 범위를 "굵게·링크 같은 인라인 서식"으로만 말해 자식 삭제를 포함하지 않는다** — 문구 보강을 같이 넣는다.
  2. **게시판 제안 → 티켓 전환이 영구 실패하는 경로**(Med): 게시판 본문은 20,000자까지 받으면서 줄 수·줄 길이를 안 보는데, `TicketCreate._check_desc` 가 **101줄 이상 또는 한 줄 1,900자 초과**를 거절한다. `_create_linked_ticket`(`board/service.py:265`)은 `post.body[:3900]` 로 **글자만** 자른다. **가장 흔한 트리거는 줄 수가 아니라 "2,000자짜리 평범한 문단 하나"** 다. 실패는 롤백이라 상태도 안 바뀌고 화면엔 영어 `"Invalid request data"` 만 뜬다(`api.js:50` 이 `details` 를 안 읽는다). `change_idea_status` docstring 의 *"같은 버튼을 다시 누르면 된다"* 는 이 결정론적 실패에 **거짓**이다.
  3. **100줄 천장의 근거를 문서에 남긴다**(Low): `MAX_BLOCKS = 100` 은 Notion 페이지 제약이 아니라 **`replace_page_body` 가 append 를 청크로 안 나눈 결과**다(`json={"children": blocks[:_MAX_CHILDREN]}` PATCH **1회**). 청크 루프로 올리거나, 못 올리면 `KNOWN_LIMITATIONS.md` 에 근거와 함께 적는다(현재 `grep` **0건**).
- **왜 지금**: 이 셋이 **같은 상수·같은 함수**를 공유한다. 2·3번은 `MAX_BLOCKS` 한 곳에서 갈라진다.
- **어느 파일**: `app/core/notion_blocks.py:12,19,30-56` · `app/tickets/notion_write.py:190-194,240-271,309-312,360-380` · `app/team_docs/notion_docs.py:458-484,503,565-587` · `app/board/{schemas,service}.py` · `app/tickets/schemas.py:15,305-319` · `frontend/src/ui/{BodyEditor,EditableBody}.jsx`
- **완료 기준**: ① 자식 있는 블록이 `deletable` 에서 빠지는 단위 테스트(현재 이 동작을 고정하는 테스트 **0건**) ② 2,000자 한 문단 게시글 → '진행' 전환 성공 회귀 테스트 ③ `KNOWN_LIMITATIONS.md` 갱신.
- **배포 후 재검증**: ⚠️ **D-21 준수** — 실서버 Notion 워크스페이스는 실고객 데이터다. **로컬 스텁으로 재현·검증한다.** 실서버 확인이 필요하면 **내가 만든 QA 전용 페이지 1장에서만**, 사용자 승인 후.

### 7단계 — 🔌 **설정 오버레이 배선** (Med 1 + Low 3)

- **무엇을**
  1. **워커가 최대 10분 낡은 설정으로 돈다**(Med, 핵심): `apply_overrides` 는 `SettingsCache.load()` 안에서만 불리고, 워커에서 `load` 를 부르는 곳은 **부팅 · 백업 틱(600초) · 보존 틱(3600초) 셋뿐**이다. 티켓(180초)·문서·프로젝트·검색 동기화 틱은 **캐시를 다시 읽지 않는다.** 관리자가 Notion 작업 DB id 를 바꾸면 웹은 즉시 새 DB 를 읽는데 티켓 미러 동기화는 최대 600초 동안 옛 DB 를 읽어 **같은 미러에 써 넣는다** — 두 소스가 섞인 미러가 만들어진다. 상한이 600초인 것도 **설계가 아니라 부수 효과**다(`backup_schedule_tick` 이 `enabled` 와 무관하게 항상 먼저 `load` 를 부른다).
     **그리고 코드 주석 3곳 + 문서 1곳이 정반대를 약속한다**: `worker_main.py:298-299` (*"워커는 틱마다 다시 load 하므로 …한 틱 안에 여기에도 온다"*), `llm_connection_test.py:68-69`, `docs/CONSOLE_SCREENS.md:185`. 넷 다 "뭉개지 않겠다"고 **명시적으로 적어 둔 자리**라 의도된 부정확이 아니라 배선이 뒤에 어긋난 자리다.
     → **`Worker.tick` 진입부에서 캐시를 한 번 적재한다**(가장 싼 방법). 못 하면 네 문장을 사실대로 고친다.
  2. **저장 값 정규화 없음**(Low): 검증기는 `strip` 해서 **모양만 보고** 원문을 통과시키고, 읽는 쪽 6곳 중 3곳만 `strip` 한다 → 공백 낀 DB id 를 저장하면 **관리 화면과 연결 테스트는 깨끗한 값을 보여 주는데 실제 조회 URL 에만 `%20`** 이 붙는다(개행이면 `httpx.InvalidURL`). 노출 경로는 **raw API PUT(system_admin)** 과 DB 직접 수정뿐이다(운영자가 쓰는 `NotionConsole.jsx:106` 은 이미 `.trim()`). → `apply_setting` 이 저장 전에 정규화한다.
  3. **오버레이가 env 를 조용히 덮는다**(Low): `_override_is_set` docstring 이 *"이 목록의 숫자 키는 `llm_timeout_seconds` 뿐"* 이라 전제하는데 **`llm_max_concurrency` 도 있고 그 기본값은 1(진짜 값)** 이라, 아무도 손대지 않은 설치에서도 `LLM_MAX_CONCURRENCY` 가 영구히 죽는다. 실노출은 좁다(어느 env 템플릿에도 없는 비문서 노브) — **남는 실질 결함은 docstring 이 거짓이라는 점**이며, 기존 `SYS-08` 에 붙여 처리한다.
  4. **두 목록이 왜 다른지 아무 데도 없다**(Low): `TENANT_SETTINGS` 에만 있는 `allowed_email_domains` 를 다음 사람이 `OVERRIDABLE_KEYS` 에 추가하면, `Settings` 필드는 `str` 인데 레지스트리 값은 `list` 이고 `validate_assignment` 가 없어 **`setattr` 이 조용히 성공**한 뒤 나중에 `allowed_email_domain_list` 의 `list.split` 에서 터진다. → 두 표 사이에 이유 한 줄, 또는 `TenantSetting.overridable: bool` 로 목록 통합.
- **왜 지금**: 넷 다 `app/core/tenant_config.py` + `app/settings/service.py` + `app/worker_main.py` **한 삼각형** 안이고, 1번이 실동작 결함, 나머지 셋은 그 삼각형의 **거짓 문서**다. 같이 안 고치면 다음 사람이 같은 함정에 빠진다.
- **어느 파일**: `app/core/tenant_config.py:95-124,141-159` · `app/settings/service.py:49-62,124-149` · `app/settings/registry.py:156-177,226,296-341` · `app/worker_main.py:298-302,397-425,462-549` · `app/jobs/handlers/llm_connection_test.py:68-69` · `docs/CONSOLE_SCREENS.md:185`
- **완료 기준**: ① `" <id>\n"` 을 PUT 한 뒤 `settings.notion_tasks_database_id` 에 공백이 없다는 회귀 테스트 ② 워커 틱이 캐시를 재적재한다는 테스트 ③ 거짓 주석 4문장 정정.
- **배포 후 재검증**: 관리 콘솔에서 Notion 문서 DB id 를 바꾸고 **3분 이내**(다음 티켓 동기화 틱)에 워커 로그가 새 id 로 조회하는지 `journalctl -u clovirone-web-worker` 로 확인.

### 8단계 — 🔌 **셸이 말하는 것과 서버가 하는 것을 일치시킨다** (Med 4)

- **무엇을**
  1. **ScopeBar 가 오늘 거짓말을 한다**(발현 중): 라우트를 보지 않고 모든 화면에 *"이 범위 밖의 항목은 목록에 나오지 않습니다."* 를 단언하는데, **게시판·놀이·알림은 부서 범위를 안 건다**(`board/repository.py:124-128` 이 *"사내 공지판이다 … 부서로 좁히지는 않는다"* 고 명시). 로컬 DB 실측으로 **부서가 배정된 일반 사용자 3명**이 있어 이들에게는 실제로 이 문장이 렌더되고, `#/board` 를 열면 그 자리에서 거짓이 된다. → 범위가 실제로 걸리는 라우트 집합을 `navConfig` 에 선언하고 그 화면에서만 렌더.
  2. **ScopeBar 가 틀린 컬럼을 읽는다**(잠복): `admin_scope='dept'` 일 때 서버가 거는 `scope_dept_id` 가 아니라 **본인 소속 부서 이름**(`me.department`)을 표시하고, `org` 는 `scope_org_id` 를 무시하고 `"내 조직"` 하드코딩. 현재 전원 `global` 이라 아무도 안 보지만 **`Users.jsx:438-440` 에 `scope_dept_id` 폼 필드가 실재하므로 관리자가 부서 범위를 부여하는 순간 발현**한다. `/api/me` 에 `scope_dept_name`/`scope_org_name` 을 실어 보내고, 판정을 `Users.jsx:101-114 scopeLabel`(정확히 그림)과 **한 벌로 합친다**.
  3. **'세션 만료' 모드가 죽은 코드다**: `minimal = auth.isError` 인데 `["me"]` 를 다시 돌리는 경로가 없다(`retry:false`, `refetchInterval` 없음, 전역 `refetchOnWindowFocus:false`, 401 이 queryClient 를 안 건드림). 게다가 SPA 셸이 서버측 게이팅(`admin/router.py:26-32`)이라 **첫 로드 401 경로조차 사실상 없다** — 즉 만들어진 목적(세션 만료)으로는 **한 번도 켜지지 않는다.** 관리자가 역할·범위를 바꿔 세션을 강제 폐기해도 열린 탭의 사이드바·팔레트·스코프 바가 **옛 역할 기준 그대로** 남는다. → `api.js` 의 401 지점에서 `invalidateQueries(["me"])` 한 번.
  4. **로그아웃 실패를 삼킨다**: `/logout` POST 가 5xx·망 순단으로 실패해도 무조건 `/login` 으로 보내는데 세션·쿠키가 살아 있어 `GET /login` 이 303 으로 `/` 로 되돌린다 → **'로그아웃 중…'을 보고 기다렸다가 대시보드로 돌아오고 오류 메시지가 없다.** 주석 `/* 세션이 이미 없어도 로그인으로 */` 는 **401 한 경우만** 정당화한다. **정답이 같은 셸에 있다**: `Banners.jsx:83-90` 이 쌍둥이 실패(대리 보기 종료)에 대해 토스트를 띄우고 이동하지 않는다.
- **왜 지금**: 넷 다 `frontend/src/app/` 셸 4파일 + `/api/me` 이고, **"화면이 서버 상태에 대해 단언하는데 그 단언을 검증하는 배선이 없다"** 는 한 가지 문제다. 3·4번은 보안 체감 항목(공용 PC)이다.
- **어느 파일**: `frontend/src/app/{ScopeBar,AppShell,auth,UserMenu}.jsx` · `frontend/src/lib/api.js:39-50` · `app/profiles/router.py:103-111`
- **완료 기준**: ① ScopeBar 렌더 테스트(dept/org/global × board/tickets 라우트) ② 401 후 `minimal` 이 켜지는 테스트 ③ logout 5xx 시 이동하지 않고 토스트가 뜨는 테스트.
- **배포 후 재검증**: 임시로 `admin_scope='dept'` 계정을 만들어 ① `/my-tickets` 에서 범위 문구가 **`scope_dept_id` 부서 이름**으로 뜨는지 ② `/board` 에서 **범위 문구가 안 뜨는지**. 다른 탭에서 그 계정 세션을 폐기 → 원래 탭이 **'다시 로그인' 한 칸**으로 접히는지.

### 9단계 — 🔌 **게시판·채팅 규약 통일** (Med 4 + Low 3)

- **무엇을**
  1. **운영자가 남의 글·댓글 본문을 고쳐도 화면에 흔적이 없다**(Med): 티켓·문서 댓글은 *"운영자도 남의 문장을 고쳐 쓸 수는 없다"* 며 수정을 작성자 본인으로 못 박고 '(수정됨)'을 붙이는데, 게시판은 (a) 운영자에게 남의 글 수정을 허용 (b) `can_edit` 하나로 수정·삭제를 뭉뚱그림 (c) '(수정됨)' 표시 없음. **감사 로그는 있다** — 결함은 **화면에 흔적이 없다**는 데 한정된다. `tickets/comments.py:18` 이 *"게시판과 같은 규약"* 을 **삭제에 대해서만** 적고 수정은 명시적으로 배제하므로, 두 모듈을 맞춘 사람의 의도는 '삭제만 공통'이었다. → `can_edit`/`can_delete` 2필드로 분리 + `updated_at !== created_at` 이면 '(수정됨)'.
  2. **로그인 불가 계정이 채팅방 방장으로 남으면 그 방을 아무도 관리 못 한다**(Med): `archive_user`/`set_user_active(False)` 는 세션 폐기·소유 스케줄 인계는 하는데 **방장 인계를 안 한다**(그 인계는 `_transfer_room_ownership` 에 있고 **호출부가 오프보딩 전체 실행 1곳뿐**). `ensure_can_manage_room` 에 관리자 우회가 없어 `system_admin` 도 이름 변경·초대·파하기를 못 한다. 게다가 관리 대화상자가 **archived 멤버에게도 '방장 넘기기' 버튼을 그대로 준다**(`transfer_owner` 에도 활성 검사 없음) — 한 클릭으로 같은 상태를 만들 수 있다. → `archive_user`/`set_user_active` 가 **이미 `_disable_owned_schedules` 를 부르는 그 자리**에서 `_transfer_room_ownership` 도 부른다. `UA-26` 과 한 판정 함수로 묶는다.
     ※ 복구 경로는 있다(오프보딩 재실행) — 비직관적일 뿐 "영구 불가"는 아니다.
  3. **전체 채팅에서 남이 부른 `@내이름` 이 강조되지 않는다**(Med): 서버는 알림을 만드는데 화면만 조용하다. `/api/team-chat/directory` 가 `User.id != exclude_user_id` 로 **호출자를 이미 제거**해서 렌더용 목록에 내 이름이 들어올 경로가 없다. 로컬 DB 실측: 전체 채팅 방의 `chat_room_members` 가 **0행**(마이그 0021 이 방만 INSERT)이라 **디렉터리가 유일한 출처**임이 확정. → `include_self` 파라미터, 또는 `mentionNames` global 분기에서 렌더용에 한해 나를 다시 합친다.
  4. **게시판 댓글만 툼스톤 없이 행이 사라진다**(Low): 부모 삭제가 답글까지 전파하므로 **제3자의 글이 아무 흔적 없이 사라진다.** `CommentThread` 는 자기 존재 이유를 *"한쪽만 고치는 날 …사용자는 같은 낱말이 화면마다 다른 뜻이라는 걸 스스로 알아내야 한다"* 로 적고 티켓·문서를 한 벌로 합쳤는데 **세 번째 면인 게시판이 정확히 그 동작을 한다.** ※ `board/repository.py:3` 이 자기 규약을 명시했으므로 **어느 규약이 정본인지 DECISIONS 에 적고** 나머지를 맞추는 편이 낫다.
  5. **'나가기' 확인 문구가 결과를 말하지 않는다**(Low): 방장이면 자동 승계(누구에게인지 안 알림), 남은 사람이 없으면 **방 삭제** — '파하기'와 같은 결과인데 바로 옆 파하기 버튼만 *"되돌릴 수 없습니다"* 라고 경고한다. 문구를 갈라 쓸 재료(`you.role`, `room.member_count`)는 응답에 이미 다 있다.
  6. **방 이름 저장이 골라 둔 초대 대상을 날린다**(Low): `rename.onSuccess → refresh() → title prop 변경 → useEffect([open,title]) → setPicked({})`. 초대 성공 경로는 `setPicked({})` 를 **명시적으로** 부르므로 이름 저장 쪽 초기화는 부수효과다. → 효과를 `[open]` 에만.
  7. **게임 명단과 추첨 대상 풀이 다른데 아무도 안 알린다**(Med): 탭을 90초 숨기면 명단에는 남은 채 추첨·팀나누기·사다리·투표 대상에서만 조용히 빠진다(`_present_players` 호출부 7곳). 방 화면 명단은 `last_seen` 을 안 보므로 **5명이 보이는데 4명 중에서 뽑힌다.** `_member_view` 가 `last_seen` 을 안 실어 **화면이 자리비움을 표시할 수단조차 없다.** `PRESENCE_SECONDS = 90` 의 근거 주석(*"백그라운드 탭 폴링 스로틀"*)도 틀렸다 — react-query `focusManager` 소스를 직접 읽어 확인했고, 숨은 탭에서 폴링은 스로틀이 아니라 **완전히 멈춘다.** → `_member_view` 에 `present` 플래그, 또는 결과 이벤트에 제외 인원.
- **왜 지금**: 전부 **"같은 낱말이 화면마다 다른 뜻"** 이라는 한 축이고, 저장소가 티켓·문서에 대해 이미 답을 만들어 둔 것을 **세 번째 면(게시판/채팅/게임)이 못 받은** 형태다.
- **어느 파일**: `app/board/{service,router,repository}.py` · `app/team_chat/{service,router,repository}.py` · `app/users/service.py:353-408` · `app/games/{service,router}.py` · `frontend/src/screens/{BoardPost,ChatRoom,ChatRoomMembers,ChatPane,CommentThread}.jsx`
- **완료 기준**: 삭제 규약 정본을 `DECISIONS.md` 에 새 항목으로 기록 + 세 면이 그것을 따르는 테스트. `archive_user` 가 방장을 인계하는 테스트. **"전체 채팅에서 남이 보낸 `@내이름` 이 mention 조각이 된다"** 회귀 테스트(현재 global 렌더 경로 **무테스트**).
- **배포 후 재검증**: 계정 2개로 ① 전체 채팅에서 서로 `@이름` → 말풍선 칩 확인 ② 그룹방 만들고 방장 계정을 CLI 로 보관 → 남은 멤버가 방 이름을 바꿀 수 있는지 ③ 게임방에서 탭 2분 숨겼다 돌아와 명단에 '자리 비움'이 뜨는지.

### 10단계 — 🔌 **채팅 텍스트 파서 공용화** (Med 1 + Low 2)

- **무엇을**: AI 답변 링크화기가 **팀 채팅 쌍둥이가 이미 가진 처리를 안 쓴다.**
  1. `URL_RE = /(https?:\/\/[^\s]+)/g` 에 문장부호 잘라내기가 없어 **`"...(https://www.notion.so/abc)에서"`** 가 통째로 URL 이 된다(node 로 직접 재현: `href` = `...abc)%EC%97%90%EC%84%9C`). `safeNotion` 이 호스트만 보므로 **자신만만한 'Notion에서 열기' 링크로 나가고**, Notion 외 URL 이면 **복사되는 주소까지 오염**된다. → **`chat-text.js:38-54 trimUrlTail()` 을 공용 모듈로 올려 두 링크화기가 같은 함수를 보게 한다.**
  2. `RichText.jsx:19-20` 머리글의 `text`/`note` 만 `linkifyText` 를 안 거친다(나머지 4곳은 전부 거친다) → 머리글 줄의 URL 은 링크도 복사 버튼도 아닌 **죽은 글자**. 두 줄 수정. ※ 가장 흔한 트리거는 `AI-33`(마크다운 링크 미지원)과 겹치지만, `■ https://…` 경로는 **AI-33 을 고쳐도 남는다.**
  3. `kvOf` 의 '시각 오인' 가드가 맨 숫자(`09:00`)만 막아, **`"오전 9:30에 회의"` 2줄이 정의목록(dl 2열)** 으로 렌더된다(node 재현 확인). ※ `AI-34`(코드펜스 상태 부재)와 **수정 지점이 다르다** — AI-34 를 고쳐도 이 입력은 그대로 깨진다.
- **왜 지금**: 셋 다 `frontend/src/screens/chat*` 이고, 1번이 **"헬퍼가 있는데 안 부른다"의 교과서적 사례**다.
- **어느 파일**: `frontend/src/screens/chat-helpers.js:189-252` · `frontend/src/screens/chat/{RichText,links}.jsx` · `frontend/src/screens/chat-text.js:26,38-54`
- **완료 기준**: 회귀 테스트 3개 — 괄호로 감싼 Notion 링크 · 마침표로 끝나는 Notion 링크 · `■ https://…` 머리글.
- **배포 후 재검증**: `/chat` 에서 도우미에게 Notion 링크를 문장 끝·괄호 안에 넣어 답하게 하고 **링크를 실제로 클릭**해 Notion 이 열리는지.

### 11단계 — 위생 묶음 (Low, 한 PR)

| 항목 | 한 줄 | 파일 |
|---|---|---|
| RBAC 매트릭스 **행 누락** | 제품에서 가장 강한 두 권한(**임퍼소네이션**, **시스템 설정**)이 표에 없고, `setup.read` note 가 **존재하지 않는 행**("시스템 설정과 같은 근거")을 참조한다. 테스트 9개는 전부 **기존 행의 모양**만 본다 — 행 집합 완전성 검사 0건. `VIS-129` 옆에 붙일 것 | `app/core/authz.py:137-185` |
| `ConfigVersion` **유니크 제약이 ORM 에 없다** | 재시도 로직(`except IntegrityError`)과 `get_version` 의 `scalar_one_or_none` 이 그 제약을 전제하는데 마이그 0004 에만 있다. `create_all` 경로에서 조용히 사라진다(현재 사용처 1곳뿐이라 **잠재적**) | `app/core/versioning.py:24-32` |
| `versioning.py` docstring 이 **거짓** | *"Every mutation writes a full post-change snapshot"* 인데 **설정만 pre-change** 다. 화면 한 곳(`SettingVersions.jsx:53`)만 개별 방어했고 러너 쪽은 단서 없음 | `app/core/versioning.py:1-9` |
| `ticket_source` 를 **어디서도 볼 수 없다** | 문서·주석·회귀 테스트가 "운영 킬 스위치"라 부르는데 현재 모드를 확인할 방법이 SSH 로 `web.env` 읽기뿐. 비밀도 아니다 → `/api/health` 에 한 줄 | `app/core/config.py:136-141` |
| ETag 가 **가장 비싼 폴링에만 없다** | `/api/team-chat/rooms` 는 셸에서 60초마다 **모든 사용자·모든 화면**에서 돈다(주석이 *"가장 비싼 조회 축(H4)"* 이라 적음). 정작 ETag 는 팬아웃 가장 작은 `/api/trash` 에 걸려 있다. ※ 이득은 **전송량뿐** — 조회 비용은 안 줄어든다 | `app/team_chat/router.py` |
| Donut 만 빈 상태 높이를 안 넘김 | 9rem → 4rem 으로 카드가 주저앉는다. **넘길 값이 있는데 안 넘기는 유일한 곳** | `Donut.jsx:28` |
| 상단바 로고 부제가 **6.4px** | SVG `<text>` 라 실렌더 6~8px. `charts/base.jsx:38-39` 가 정확히 이 이유로 금지 규칙을 못 박았고, **자동 검사(tiny_text)는 20px 으로 보고 pass 한다.** HTML 대안이 이미 사이드바에 있다 | `BrandLogo.jsx:170-184` |
| LineSeries **결측 x 재계산** | 값 하나가 null 이면 뒤 점들이 앞당겨진다. **현재 소비자 2곳으로는 발현 안 함**(둘 다 null 을 0 으로 눕히고 그 의도를 명시) — 강제되지 않은 계약 | `LineSeries.jsx:26-47` |
| 강조색이 **계정 구분 없는 전역 키** | 공용 PC 에서 다음 사람이 앞사람 색을 본다. **테마는 이미 계정별로 나눠 저장하고 그 이유까지 적혀 있다**(`theme-store.js:7-12`) — 액센트 주석은 *"테마와 같은 방식"* 이라 적고 계정 분리·로그아웃 정리를 둘 다 빠뜨렸다 | `ThemeModeProvider.jsx:17,31,54` |
| `scrollIntoView smooth` 가 reduced-motion 무시 | 앱에서 유일한 부드러운 스크롤. `behavior:"smooth"` 를 명시하면 CSS `scroll-behavior` 를 참조하지 않아 전역 `!important` 로 못 막는다. **`motion.js` 에 판정기가 이미 있다** | `kit.jsx:806-811` |
| 빈 `@media (prefers-reduced-motion)` 블록 8개 | 기능 영향 0, 그러나 grep 하는 사람에게 거짓 신호. `f8845c0` 이 선택자만 지우고 껍데기를 남김. `static_checks.sh` 에 CSS 검사 **0건** | `kit.css` · `global.css` · `screens.css` |
| `.chat-thinking` **죽은 a11y 예외** | 주석이 선언한 예외(*"동작 줄이기에서도 작동 중 표시는 멈추지 않는다"*)가 캐스케이드상 성립 불가이고, 게다가 그 선택자가 죽은 클래스다. **살아 있는 `MessageThread.jsx:189` 도 같은 이유로 정지**한다(`sr-only` 는 남아 있음) | `screens.css:231-232` |

- **완료 기준**: 각 항목에 회귀 테스트 1개, 또는 고치지 않기로 했으면 **`KNOWN_LIMITATIONS.md`/`DECISIONS.md` 에 이유와 함께 기록**(둘 중 하나는 반드시).
- **배포 후 재검증**: `scripts/ui_qa/` 하네스 재실행 + `/dev-report`·`/home`·`/my-stats` 를 빈 데이터 상태로 열어 도넛 높이 확인.

---

## 4. Sonnet 이 먼저 읽을 파일 5개 (순서대로)

| # | 파일 | 왜 이 순서인가 |
|---|---|---|
| 1 | **`docs/WORK_STATE.md`** (특히 §3-0-Z · §3-0-B · §3-3 · §4) | **진입점.** 실서버가 지금 깨져 있다는 사실(`OPS-01`), Critical 2건의 재확인 근거, **철회된 판정 4건**, Blocker 해소 상태가 전부 여기 있다. 대화 History 는 Source of Truth 가 아니다 |
| 2 | **`docs/BACKLOG.md`** — 최상단 Critical 표(:16-30)와 **⚠️ 정정 블록 안내**(:22-30) | 511항목 중 **325행이 아직 `발견`** 이다. **항목을 집어 들기 전에 그 자리의 정정 블록을 먼저 읽어야 한다** — 이 문서에는 철회·정정된 항목이 섞여 있고, 그걸 모르고 고치면 되돌린 결정을 다시 뒤집게 된다 |
| 3 | **`CLAUDE.md`** — §2 불변 규칙 · §8 함정 | **배선 수정이 가장 자주 어기는 자리다.** sync 일관성, `OutboundClient` 단일 관문, `textContent` 전용, 라우터 팩토리에 `from __future__ import annotations` 금지, SQLite `%f` 함정, `assets.py` 지문 캐시 금지 |
| 4 | **`docs/DECISIONS.md`** — **D-21**(러너 Notion 쓰기 실서버 재현 금지) · **D-22**(제품 안의 정답을 먼저 찾는다) · **D-45**(공용 규칙은 기본값이어야 한다) · D-13(CSP 는 되돌리지 않는다) | §3 의 배선 전략이 **D-22·D-45 에서 나왔다.** D-21 은 6단계에서 실수하기 가장 쉬운 금지선이다 |
| 5 | **`scripts/upgrade-clovirone-web-assistant.sh`** (+ `scripts/install-clovirone-web-assistant.sh:46-51`) | **1단계가 이 파일이고, 이걸 안 읽고 플레이북대로 배포하면 첫 시도에서 서비스가 멈춘 채 남는다.** 나머지 10단계의 "배포 후 재검증"이 전부 여기에 의존한다 |

---

## 5. 손대면 안 되는 것

이 저장소가 **이유를 적어 둔** 결정들이다. 고치려다 되돌리면 안 된다.

### 5-1. 명시된 설계 결정

| 결정 | 내용 | 근거 위치 |
|---|---|---|
| **D-21** | **러너의 Notion 쓰기를 실서버에서 재현하지 않는다.** `RN-01~03` 은 로컬 CLI 스텁으로 이미 재현했다. **서버는 테스트 서버지만 Notion 워크스페이스는 아니다** — 현대모비스·SK하이닉스·KB국민카드·인천국제공항공사 등 **실고객 프로젝트 티켓**이 들어 있다. "서버가 테스트용"이라는 사실이 그 부작용까지 테스트용으로 만들지 않는다 | `docs/DECISIONS.md:173` |
| **alembic 0039** | **`team_chat_room` 에 유니크 제약을 걸지 않은 것은 의도다** — *"부서가 지워졌다 다시 생기거나 방이 soft-delete 된 경우까지 DB 제약으로 다루면 복구 경로가 막힌다."* 대신 `ensure_team_room` 이 SAVEPOINT 로 경합을 처리한다. **WF4 의 원 보고가 이 결정을 뒤집는 수정을 제안했다가 검증자에게 반려됐다** | `alembic/versions/0039_team_chat_room.py:15-16` |
| **D-13** | **CSP 는 되돌리지 않는다 — 문서를 정정한다.** `script-src 'self'`, 인라인 `<script>`·`onclick=` 금지, 런타임 외부 CDN/폰트 0 | `docs/DECISIONS.md:126` |
| **D-05a** | 하네스는 SSH 터널이 아니라 **HTTPS 를 직접** 겨눈다(`--insecure`). 서버가 `COOKIE_SECURE=true` 라 http 로는 세션 쿠키가 안 실린다 | `docs/DECISIONS.md:52` |
| **D-23** | **전체 페이지 스크린샷으로 `position:fixed` 겹침을 판정하지 않는다.** 이걸로 7건을 잘못 올렸다 | `docs/DECISIONS.md:217` |
| **불변규칙 §2 전체** | sync 일관성(`async def` 핸들러 금지) · 아웃바운드는 `OutboundClient` 한 곳 · secret 은 DB 에 `secret_ref` 만 · 세션은 opaque 토큰(JWT 아님) · 프런트는 `textContent` 전용 · `assets.py` 지문을 **캐시하지 않는다** | `CLAUDE.md §2`, `§8` |

### 5-2. 이번 라운드에서 **"의도 명시"로 확인해 뺀 것** — 결함으로 재보고하지 말 것

- **Notion 블록 종류 하향 변환**(`quote→paragraph`, `to_do→bulleted`, `code→문단`, `callout/toggle→문단`) — `notion_blocks.py:62,140` 과 `EditableBody.jsx:141-142` 에 의도가 적혀 있다. 6단계에서 고칠 것은 **자식 유실 하나**다.
- **게시판 soft delete 규약**(`board/repository.py:3`) — *"조회 함수는 기본으로 `deleted_at IS NULL` 만 돌려준다"* 는 이 모듈의 **선언된 방침**이다. 9-4 는 "규약을 바꿔라"가 아니라 **"정본을 정하고 세 면을 맞춰라"** 다.
- **댓글 삭제의 답글 전파**(`board/service.py:366-368`) — *"부모만 지우면 답글이 고아가 되어 화면엔 안 보이면서 댓글 수에만 남는다"* 는 이유까지 적힌 의도.
- **`MyStats` 의 null→0**(`MyStats.jsx:166-168`) — *"배정 0건인 달의 완료율은 null(0%가 아니다). 선은 숫자만 그릴 수 있으므로 0으로 눕히되 아래 표가 '-'로 보여 준다."* LineSeries 계약 문제(11단계)와 혼동하지 말 것.
- **`_MAX_REPLACE_BLOCKS = 200`** — 1차 근거는 *"삭제가 블록당 DELETE 한 번"* 이라는 **독립적 비용 논거**다. "순환 논거"라는 원 보고 해석은 과잉이었다.
- **`app/admin/rbac.py:3-6`** — *"표 전체가 `rbac_matrix()` 에서 나온다"* 는 **완전성 선언이 아니라 단일 출처 선언**이다.

### 5-3. 조사 산출물 — 지우거나 켜지 말 것

- **`/chat` 의 `112347f0-…` 대화** — `AI-30`(11일 묵은 CREATE 모드가 질문을 납치)의 **재현용 증거**다. 고치기 전에는 지우지 않는다.
- **`SCHD-01` 스케줄** — 켜면 매주 월 09:00 에 실고객 Notion 쓰기가 나갈 수 있다.
- **철회된 항목을 다시 고치려 들지 말 것**: 「클로비 가림」 계열 7건 · `USE-03` · `AI-31` · `ADM-01` · `VIS-107~109` · `HOST-01` · `AI-40` · `RET-01/02` · `NOTI-04` · `ADM-06`.
- **nginx 는 공유 자원** — vhost 추가만, 기존 무접촉, `default_server` 금지. n8n `:5678` · claude runner `:8787/:8788/:8789` 절대 미접촉.

### 5-4. 정리해도 되는 것 (조사 종료 후)

`qa-user`/`qa-operator`/`qa-auditor`/`qa-admin` 4계정 비활성화(현재 `/dev-report` 에 빈 행으로 섞이고 `/users` 맨 위에 뜬다) · `mail_deliveries` 14행(전부 `unconfigured`, 실발송 없음) · `saved_views` 조사용 1행 · 로컬 `.claude/worktrees/` 88개(**저장소 grep 을 오염시켜 조사를 방해한다**).

---

## 6. 남은 불확실성

조사로 답을 못 낸 것들이다. **추측으로 메우지 말고, 착수 시점에 다시 확인하거나 사용자에게 물어라.**

### 6-1. 문서 자체의 모순 — 확인 필요

1. **"Critical 5건"인데 표에 6행이 있다.** `docs/BACKLOG.md:14` 는 `Critical 5`, `:17-24` 표는 `OPS-01`·`SEC-20`·`SEC-30`·`SYS-01`·`DEPLOY-01`·`FN-40` **6행**이다. 게다가 `OPS-10`(워커 무한 재시작)은 WF4 절에서 **Critical** 로 표기됐는데 최상단 표에 없다. **실제 Critical 집합이 5인지 6인지 7인지 확정되지 않았다.** → 착수 전 재집계.
2. **수렴 기준의 "세 조건" 중 세 번째가 어디에도 없다.** `WORK_STATE.md:40` 이 *"세 조건 중 ①②"* 라고 쓰는데 `grep -rn "새 큰 범주" docs/` → **그 한 줄이 유일한 히트**다. ①②는 이번 라운드로 충족했지만 **③이 무엇인지 모른다.** → 사용자에게 확인하거나, 이 인계 문서를 근거로 세 조건을 명문화.

### 6-2. 로컬에서 검증 불가 — 서버·외부 API 필요

3. **Notion API 의 실제 semantics 2건**: (a) 부모 블록 DELETE 시 자식이 아카이브되는가 (H-1 의 손실 범위가 "본문에서 사라짐"인지 "영구 삭제"인지가 여기 달렸다) (b) 공백 포함 database_id 를 Notion 이 실제로 어떻게 응답하는가(**URL 인코딩과 개행 예외까지만** 확인했고 실응답 코드는 토큰이 없어 미확인).
4. **`LLM_MAX_CONCURRENCY` 를 실제로 걸어 둔 설치가 있는가.** 어느 env 템플릿에도 없는 비문서 노브라(`grep -rn LLM_ deploy/web.env.example .env.example` → **0건**) 실노출을 판단할 수 없었다. 서버 `web.env` 는 0640 root 라 읽지 못했다.
5. **실서버의 `admin_scope` 분포.** 로컬 `var/web.sqlite3` 는 13명 전원 `global`, BACKLOG 는 프로덕션 18명 전원 `global` 로 기록. 8-2(ScopeBar 컬럼 오독)가 **오늘 발현하는지 잠복인지**가 여기 달렸다.
6. **`OPS-01` 이후 첨부 시도가 정말 0건인지.** "마지막 성공 2026-08-05, 이후 시도 없음"은 로그 기준이고, **실패한 시도가 로그를 안 남겼을 가능성**을 배제하지 못했다.

### 6-3. 조사 방법의 한계 — 이 라운드가 못 본 것

7. **런타임 재현이 아니라 코드 판독으로만 판정한 항목이 있다.** 명시된 것: 9-6(방 이름 저장 → `picked` 리셋)은 데이터 흐름 4단계를 파일로 이었을 뿐 **브라우저에서 재현하지 않았다.** 8-1·8-3·8-4 도 코드 근거 + 로컬 DB 실측이지 실조작이 아니다.
8. **러너(`claude-work-assistant`)는 이 5라운드에서 별도 트랙이었다.** `RN-01~03`·`AI-30`·`AI-37` 은 로컬 스텁 재현까지만 됐고, **러너 코드 전체에 대한 전수조사는 하지 않았다.** "수렴했다"는 §2 판정은 **플랫폼(`app/` + `frontend/`) 범위에 한정**된다.
9. **실환경 검증 축은 통째로 0%다.** 511항목 중 `실환경검증완료` **2건**. §2 의 수렴 판정은 **"더 찾을 것이 없다"** 이지 **"고쳐졌다"** 가 아니다. 1~11단계를 마친 뒤에도 각 항목은 배포·재검증 전까지 `구현완료` 이상으로 올리면 안 된다.
10. **`QA_COVERAGE.md` 를 이 라운드 결과로 갱신하지 않았다.** 이번에 새로 덮인 영역(설정 오버레이·versioning·Notion 본문 쓰기·셸 스코프·채팅 파서·차트 프리미티브·reduced-motion)이 매트릭스에 반영돼 있지 않다. **Sonnet 의 첫 문서 작업으로 넣어라** — 안 그러면 다음 세션이 같은 영역을 "미조사"로 보고 또 훑는다.