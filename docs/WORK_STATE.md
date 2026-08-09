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

**마지막 갱신**: 2026-08-10 · **단계**: Sonnet 구현 사이클 3 — 로컬 게이트 green, **배포·실환경검증 전** · **브랜치**: `ui/mui-migration`

---

## 0. 한 줄 요약

## 🟡 Sonnet 구현 사이클 3 — 로컬 완료, 배포·실환경검증은 다음 단계 (2026-08-10)

`SONNET_HANDOFF.md §3` 5~11단계(설정 화면 배선 · Notion 본문 쓰기 안전 · 설정 오버레이 배선 ·
셸 스코프 배선 · 게시판/채팅 규약 통일 일부 · 위생 묶음)를 구현했다. **주의: 이 블록은
`구현완료`까지다 — `실환경검증완료`가 아니다.** 다음 세션(또는 이 세션 다음 턴)이 반드시
할 일: 서버 배포 + Chrome 실환경 검증 + 이 블록을 그 결과로 갱신.

**로컬 게이트(전부 확인됨)**: 백엔드 pytest 전체 2회 green(중간에 Notion 블록 계약 골든
파일 갱신 1건 — 의도된 드리프트, `has_children` 필드 추가), 프런트 vitest 전체 3회 green
(174→184 파일, 1224→1248 테스트), `bash scripts/static_checks.sh` → `STATIC_CHECKS_OK`
(44개 검사 전부 통과), `npm run build` + `check_bundle_fresh.py --write` 로 번들 재생성 완료.

**5단계 설정 화면 배선**: `fmtDuration` import(이미 사이클 1에서 완료 확인), `session_policy`
설명문 정정 + 줄이기 경고 추가, `settings-labels.test.js`의 손유지 `OBJECT_TYPES` 목록을
레지스트리에서 동적으로 뽑도록 교체(`SET-...`류, `retry_policy` 죽은 검증기 삭제),
`SettingEditor.jsx` 읽기 전용 버튼을 `disabled`로(안 사라지게).

**6단계 Notion 본문 쓰기 안전 (`FN-50`/H-1)**: `page_block_refs`가 `has_children`도 읽어
자식 있는 블록을 `deletable`에서 제외(`notion_write.py`·`notion_docs.py` 동일 패턴,
죽은 `page_block_ids` 삭제). `EditableBody.jsx`에 중첩 콘텐츠 경고 추가. 게시판→티켓 전환
영구 실패 버그(`_fit_for_ticket_description` 신설 — 긴 한 줄 문단을 줄바꿈으로 나눠
`TicketCreate._check_desc`를 통과시킴, `board/service.py`) 로컬 스텁 테스트로 검증
(D-21 — 실서버 Notion 쓰기는 재현하지 않음, 로컬 스텁이 이 항목의 검증 상한).

**7단계 설정 오버레이 배선 (`WORKER-01`/`SET-10`/`SET-11`)**: `worker_main.py`에 60초 간격
`settings_cache_tick` 신설(다른 콜백보다 먼저 등록 — 같은 반복 안에서 최신값을 보게).
거짓 주석 4곳 정정(worker_main.py·llm_connection_test.py·CONSOLE_SCREENS.md·
tenant_config.py). `apply_setting`이 저장 전 문자열을 `strip()`. `SYS-08`(숫자 센티널
비대칭) docstring 정정 + 참조 연결. `TENANT_SETTINGS`/`OVERRIDABLE_KEYS` 두 목록이 다른
이유(타입 불일치 위험)를 코드에 명시.

**8단계 셸 스코프 배선**: `ScopeBar`가 라우트를 가려 실제로 범위가 걸리는 화면
(`navConfig.js::SCOPE_ENFORCED_PATHS`)에서만 "범위 밖은 안 보인다" 문구를 띄움. 부서
관리자 표시가 본인 소속 부서가 아니라 **배정받은 관리 범위**(`scope_dept_name`/
`scope_org_name`, `/api/me` 신설 필드)를 보이게. 다른 API의 401이 `["me"]` 쿼리를
무효화해 세션 만료 화면이 실제로 켜지게(`api.js::api.onUnauthorized`, `auth.jsx`) —
**구현 중 자체 발견 버그**: 최초 설계가 `/api/me` 자신의 401에도 무효화를 걸어 무한
재무효화 루프로 vitest 워커가 힙 고갈로 죽는 것을 실측, `path !== "/api/me"` 가드로 수정
+ 회귀 테스트로 고정. 로그아웃 5xx/망 실패 시 무조건 `/login`으로 보내던 것을 401만
그렇게 하고 나머지는 토스트로 알리게(`UserMenu.jsx`).

**11단계 위생 묶음 — 10개 항목을 워크플로(병렬 서브에이전트 10개)로 구현**: RBAC 매트릭스에
`impersonation.start`·`system.settings` 행 추가, `ConfigVersion` ORM에 유니크 제약
선언(alembic 0004와 동일), `versioning.py` docstring의 pre/post-change 서술 정정,
`/healthz`에 `ticket_source` 노출, `/api/team-chat/rooms`에 ETag 적용, `Donut` 빈 상태
높이 유지, `BrandLogo` 부제를 SVG `<text>`(실렌더 ~6.4px)에서 HTML로, `LineSeries`의 null
값 x좌표 보존, 강조색 계정별 저장, `scrollIntoView`의 reduced-motion 반영, 빈
`@media(prefers-reduced-motion)` 블록 8개 + 죽은 `.chat-thinking` CSS 삭제.
**서브에이전트 결과를 그대로 안 믿고 직접 리뷰해서 잡은 것 1건**: 강조색 계정별 저장이
`ThemeModeProvider`에 `userId` prop을 받게 설계됐는데, 그 컴포넌트는 `AuthProvider`
**바깥**(main.jsx)에 마운트돼 있어 그 prop이 실제로는 **한 번도 채워질 수 없는** 구조였다
(에이전트의 단위 테스트는 prop을 직접 주입해서 통과했을 뿐, 실제 앱에서는 죽은 코드).
`identifyAccentUser()`를 컨텍스트에 노출해 `UserMenu.jsx`(계정을 아는 첫 지점, 테마 복원과
같은 자리)가 호출하는 구조로 다시 짜고, 실제 트리로 배선이 닿는지 보는 회귀 테스트
(`user-menu-accent-wiring.test.jsx`)를 새로 추가해 고정했다 — 이 저장소가 그동안 계속
찾아낸 "헬퍼는 있는데 부르는 쪽이 안 부른다" 결함을 새 코드에서 스스로 반복할 뻔한 사례.

**9·10단계는 아직 착수 전** — 게시판·채팅 규약 통일 나머지(수정 흔적 표시, 방장 오프보딩
인계, 전체 채팅 @mention 강조, 댓글 툼스톤, 나가기 문구, 방 이름 저장 버그, 게임 명단/추첨
불일치)와 채팅 텍스트 파서 공용화(`trimUrlTail`, RichText 머리글, `kvOf` 오탐)는 다음 작업.

**다음(순서대로)**: ① 커밋 ② `scripts/build-bundle.sh` → scp → 실서버 배포(DNS_NAME/
BIND_IP 지정) ③ `systemctl is-active` 3종 + `/healthz`(`ticket_source` 필드 확인) ④ Chrome
으로 최소: `/settings`(session_policy·smtp), `/scope`가 걸리는 화면(부서 관리자 계정으로
`/team-docs` vs `/board`), 로그아웃(정상 흐름), `/rbac`(새 두 행), BrandLogo 렌더(육안
확인 — 자동 테스트가 못 잡는 실제 픽셀), Donut 빈 상태 카드 높이 ⑤ 이 블록을
실환경검증완료로 갱신 + BUILD_LOG.md 추가 ⑥ 9·10단계 착수, 그다음 사이클 4(전체 제품
재감사).

---

## 🔵 Sonnet 구현 사이클 2 완료 — Critical/High 축(SYS-01·SEC-30·SEC-22·FN-40·OPS-10/11) 전부 실환경검증완료 (2026-08-09)

`SONNET_HANDOFF.md §3` 2~4단계를 끝냈다. **여섯 항목 전부 실서버에서 직접 재현·확인**했다
(코드만 고치고 "될 것이다"로 남긴 것 없음):

- **`SYS-01`** TLS 인증서 교체 무동작 — `settings.tls_cert_path`(env `TLS_CERT_PATH`)로 통일하고
  privhelper 유닛에 `EnvironmentFile=` 추가(그 프로세스는 FastAPI `Settings` 가 없는 별도
  프로세스라 env 로 전달해야 했다). **실제로 새 인증서(다른 만료일·serial)로 교체하고
  `openssl s_client` 로 nginx 가 그것을 서빙하는 것을 확인한 뒤 원래 인증서로 복원**했다.
- **`SYS-02`**(무료 동승, 같은 파일) `hostnamectl show -p` 가 systemd 255 에 없는 verb라 호스트
  이름이 영구히 빈 문자열 — `hostname.set` 이 이미 쓰던 `status --static` 폴백으로 통일.
- **`SEC-30`** CSV 가져오기 권한 상승 — 게이트(`ensure_can_grant_role`)를 `create_user()` 안으로
  옮겨 웹 폼·CSV·CLI·`seed_admin.py` 가 전부 한 곳을 지나게 함. **plain admin 계정으로 실제
  CSV 미리보기에 `role=system_admin` 행을 넣어 거부되는 것을 확인.**
- **`SEC-22`**(SEC-30 과 같이 묶임) CLI 계정 조작이 이상 탐지에서 전부 안 보이던 것 —
  `app/audit/actions.py` 신설로 `health/service.py`·`anomalies.py` 가 목록을 공유하게 함.
  **CLI 로 실제 역할 변경을 실행하고 `/api/admin/audit/anomalies` 에 잡히는 것을 확인.**
- **`FN-40`** 공지 PATCH 가 `body`/`title`/`level`/`audience` 를 `null` 로 보내면 500 —
  `body` 는 POST 와 같은 규칙(빈 문자열)으로, 나머지 셋은 명확한 422 로. **실제 PATCH 요청
  두 종류(`body:null`→200, `title:null`→422) 를 직접 보냈다.**
- **`OPS-10`/`OPS-11`** 워커 리스 획득 실패·하트비트 갱신 실패가 예외로 새면 재시작 루프·
  좀비 상태가 됐다 — `WorkerLockError` 로 구분해 깨끗이 종료, `renew()` 도 `beat_liveness()`
  와 같은 방어. 유닛 `RestartSec=10`+`StartLimitIntervalSec=300`. 실패 주입은 **공유 워커를
  실제로 고장내지 않기 위해** mock 기반 단위테스트로(정상 기동·리스 획득은 실배포로 확인).

**자율 연속 실행 체계**: 사용자가 "세션 하나가 끝나도 재호출 없이 계속 이어지는 구조를
만들고 검증하라"고 요청 → 하네스 내장 `/loop` dynamic mode + `ScheduleWakeup` 을 그 목적으로
재사용하기로 결정(D-53). **이미 실측 검증됨**: 사이클 1→2, 사이클 2 안에서도 여러 차례
사용자 입력 없이 `ScheduleWakeup`/배경 작업 완료 알림만으로 재개됨.

로컬 게이트 전부 green(pytest 루트 전체 2회 + 러너 + vitest, `STATIC_CHECKS_OK`).
**다음**: `SONNET_HANDOFF.md §3` 5~11단계(설정 화면 배선 · Notion 본문 쓰기 안전 · 설정
오버레이 배선 · 셸 스코프 배선 · 게시판·채팅 규약 통일 · 채팅 파서 공용화 · 위생 묶음).

---

## 🔵 Sonnet 구현 사이클 1 완료 — 배포 경로 자체를 고쳐야 나머지를 검증할 수 있었다 (2026-08-09)

`SONNET_HANDOFF.md §3` 의 순서대로 착수. **1단계(배포 경로 복구)를 먼저 끝냈다** — 이후
모든 사이클의 "배포 후 재검증"이 여기 의존하므로, 이 단계가 실서버에서 실제로 되는 것을
확인하기 전에는 아무것도 검증할 수 없었다.

**완료(실환경검증완료)**: `DEPLOY-01`·`DEPLOY-02`(`upgrade-clovirone-web-assistant.sh` 가
DNS_NAME/BIND_IP 를 요구·전달, `rollback_now()` 이식) · `UX-50`(H-2, `fmtDuration` import
누락 — 세션 정책 편집기 크래시) · **직접 배포하다가 새로 발견한 2건**: `DEPLOY-03`(installer
주석이 "아무것도 안 바꿨다"고 거짓말) · `DEPLOY-04`(롤백이 특권 헬퍼를 안 되살림).

**직접 배포 절차를 문자 그대로 따라가다가 문서 자체의 버그 2개를 더 찾았다**(이번 것도
BACKLOG 에 없던 새 발견, `MAINTENANCE_PLAYBOOK.md §2-3` 수정함):
- `sha256sum -c MANIFEST.sha256` 을 **압축을 풀기 전에, 그 파일이 없는 경로에서** 돌리려
  했다 — `&&` 로 이어져 있어 실패해도 뒤 단계가 조용히 안 실행되고 옛 스테이징이 남는다.
- `mkdir -p stage && tar -xzf … -C stage` 가 이미 `stage/…` 로 시작하는 tar 내용을 다시
  `stage/` 안에 풀어 **`~/deploy/stage/stage/app-src` 로 이중 중첩**됐다 — `STAGE=~/deploy/stage`
  를 쓰는 다음 단계가 `app-src` 를 못 찾고 죽는다.

**실서버 검증 방법(그대로 재현 가능)**: 정상 배포 1회(`UPGRADE_OK`) → 스테이징 사본을
고의로 깨서(`requirements.txt` 제거) 재배포 → 서비스 정지 후 install 실패 →
`rollback_now` 가 백업 복원 → `UPGRADE_ROLLED_BACK` → `systemctl is-active` 3종
(web·worker·privhelper) 전부 active + healthz/readyz 200. **두 번** 이렇게 재현해 DEPLOY-04
(privhelper 백업 자체가 새 코드에서만 생기므로) 수정 전/후를 비교 확인했다.

로컬 게이트 전부 green(pytest 루트 전체 + 러너 263 + vitest 173파일/1213개 + `STATIC_CHECKS_OK`).
**다음: `SONNET_HANDOFF.md §3` 2~4단계**(`SYS-01` TLS 무동작 · `SEC-30` CSV 권한 상승 ·
`FN-40` 공지 500 + `OPS-10`/`OPS-11` 워커 내구성) — Critical/High 축.

---

## ✅ 탐색은 수렴했다 — Sonnet 인계 준비 완료 (2026-08-09)

> **먼저 읽을 것: [`SONNET_HANDOFF.md`](SONNET_HANDOFF.md)** — 이 문서 하나로 구현을 시작할 수 있다.

**발견 곡선(6라운드 실측)이 수렴을 보여 준다** — Critical `0 → 2 → 2 → 1 → **0**`,
High 비중 9.6% → 19.6% → 6.7% → 10% → **5.4%**(최저), Low 비중 **62%**(최고).
마지막 라운드의 Low 23건 중 **10건이 "코드는 맞는데 주석·문서가 거짓"** 유형이다 —
실행 결함이 고갈되고 문서 정합만 남았다는 신호다. **신규 범주 0개**, 반증률도 27~35%로 평평하다.

**단, "수렴"은 조사가 끝났다는 뜻이지 제품이 고쳐졌다는 뜻이 아니다.**
BACKLOG 529행 중 `실환경검증완료` 는 **2건**이다. 인계 성격은 **조사 종료 → 구현 착수**다.

| | |
|---|---|
| BACKLOG | **529행 / 36범주** · Critical 5 · High 113 |
| 화면 판독 | 66/70 + 4K 128페이지 + 다크 + 반응형 6폭 |
| 역할 매트릭스 | 4역할 197페이지 — **화면 게이팅 결함 0** |
| 새로 연 검증 축 | `U` 실사용 · `K` 대비 · `B` 키보드 · `S2` 시맨틱 (+ `FAIL`·`HOST`·`RESP`) |
| 워크플로 | 5회 · 에이전트 63개 · **원 보고 447건 중 176건(39%) 반증 폐기** |
| 내 오판 | 프로브 위양성 4 · 판정 철회·정정 8 (전부 근거와 함께 기록) |

**지배적 결함 유형은 6라운드 내내 하나로 수렴했다** —
**규칙·헬퍼·술어·토큰이 이미 있는데 부르는 쪽이 안 부른다.**
구현은 "만들기"가 아니라 **"배선하기"**다.

## 3-0-Z. ✅ **사용자 조치 2건 완료** (2026-08-09) — 후속은 남아 있다

- **`OPS-01` 업로드 디렉터리 `chown` 완료**(사용자). ⚠️ **`OPS-02` 는 남았다** —
  installer 의 `install -d -o $SVC_USER` 목록에 `uploads` 가 없어서 **다음 배포에 재발한다.**
  그리고 **"고쳐졌다"를 믿지 말고 실제로 첨부를 한 번 올려 확인해야 한다**(실패는 감사에 안 남는다).
- **`SEC-20` sudo 비밀번호 회전 완료**(사용자). 문서에서 옛 값 제거함.
- `SEC-10`(Notion 문서의 평문 자격증명) 처리 여부는 **미확인**.

### (기록) 원래 내용 — 실서버가 깨져 있던 상태

**`OPS-01` 파일 첨부 업로드가 2026-08-07 부터 불가능하다.**
`/var/lib/clovirone-web-assistant/uploads` 만 **root:clovirone-web 750** 이라 서비스 사용자
(`clovirone-web`)에게 쓰기 비트가 없다 — `runuser -u clovirone-web -- test -w` 로 **쓰기 불가 확인**.
형제 디렉터리(`exports`·`generated`·`locks`·`temp`)는 전부 정상 소유다.
마지막 성공 업로드는 **2026-08-05 00:23**, 이후 시도 자체가 없어 아무도 모르고 있다.
**업그레이드로 안 고쳐진다** — installer 의 `install -d -o $SVC_USER` 목록에 `uploads` 가 없다.

```
sudo chown -R clovirone-web:clovirone-web /var/lib/clovirone-web-assistant/uploads
```
+ installer 목록에 `uploads` 추가(안 하면 재발). `BKP-01`(업로드가 백업에 없음)과 겹친다.

**`SEC-20` 내 조사가 sudo 비밀번호를 명령행에 반복 노출했다** — 불변규칙 §2-4 위반이고
워크플로 프롬프트로 서브에이전트 13개에 배포했다. **그 비밀번호는 손상된 것으로 보고 회전해야 한다.**

## 3-0-B. **Critical 2건 — 조사 중 새로 나왔고 내가 재확인했다** (2026-08-09)

1. **`DEPLOY-01` 문서에 적힌 업그레이드 절차가 반드시 실패하고 서비스는 멈춘 채 남는다.**
   `upgrade-*.sh` 가 installer 에 `DNS_NAME`·`BIND_IP` 를 안 넘기는데 installer 는 그 둘이 없으면
   `exit 2`(`install-*.sh:46-51`). 그 시점엔 이미 **web·worker 를 둘 다 정지**시킨 뒤이고
   되살리는 코드가 없다. `MAINTENANCE_PLAYBOOK.md` §2 대로 하면 **서비스 중단**이다.
   ※ 이번 사이클 배포가 성공한 것은 내가 두 값을 직접 넘겼기 때문이다.
   ※ 같은 파일의 **git 경로에는 `rollback_now()` 가 있는데 번들 경로에는 없다**(`DEPLOY-02`).
2. **`FN-40` 공지 「내용」을 비우고 저장하면 500.** `AnnouncementPatch.body` 는 `str|None` 인데
   컬럼은 `nullable=False` 이고 PATCH 루프가 null 을 그대로 넣는다. **POST 경로는 이미
   `or ""` 로 막고 있다** — PATCH 만 빠졌다. 화면엔 영어 "Internal server error" 만 뜬다.

## 3-0. 임박한 것 (시간이 지나면 저절로 터진다)

- **`UB-40` 오프보딩 목록이 21명째부터 잘린다** — 현재 **18명**. `Offboarding.jsx:65` 가
  `page_size=20` 하드코딩이고 총건수·페이저·잘림 경고가 없다. 세 명만 더 들어오면
  퇴사 처리 대상자를 목록에서 못 찾는다.
- **`RSTR-03` 자동 백업이 꺼져 있고 마지막 백업이 2026-07-19** — 매일 멀어진다.
- **`SCHD-01` 유일한 스케줄이 AI 채팅 웹훅을 가리킨다** — 누군가 「활성」을 켜는 순간
  매주 월요일 09:00 에 Notion 쓰기가 나갈 수 있다. **켜지 않았다.**
- **`SEC-10` Notion 문서 1건에 평문 자격증명** — 사용자에게 알려야 할 항목(원본은 실고객 워크스페이스).

## 3-1. 가장 먼저 손대야 할 것 (사이클 0이 남긴 결론)

**최우선은 `SYS-01`이다** — TLS 인증서 교체가 성공 메시지·새 인증서의 subject·만료일까지
보여 주면서 **실제로는 아무것도 바꾸지 않는다**(nginx 가 읽지 않는 경로에 쓴다). `CLAUDE.md`
§10이 "운영 전 사설 CA 인증서로 교체"를 남은 조치로 적어 둔 바로 그 경로이고, 관리자는
성공했다고 믿게 된다. 고치는 것은 경로 한 곳이며 **올바른 값이 이미 `settings.tls_cert_path`에
있다**(`probe_tls`·`app/health/service.py`가 그것을 쓴다).

그다음이 `AI-30`(11일 묵은 CREATE 모드가 질문을 티켓 생성으로 바꾼다 — 러너 문맥에 만료가
없다)과 `AI-37`(그 상태의 탈출어를 그 자리에서 안 알려 준다). **둘 다 러너 쪽 작은 변경인데
체감 효과가 가장 크다.**

이어서 아래 러너 쓰기 3건 —

러너에서 **재현까지 끝난** 세 건이 제품 전체에서 가장 위험하다 — AI가 사용자의 **질문과 거절을
승인 없는 Notion 쓰기로 바꾼다**:
- `RN-01` "그거 완료했어?" → 티켓이 완료로 바뀐다 (`norm()`이 `?`를 지우고, 질문 가드가 최상위
  라우터에 없다)
- `RN-02` "완료로 바꾸지 마" → 완료로 바뀐다 (부정 가드가 `is_approval_message` 안에만 있는데
  분기 ③이 그보다 먼저 돈다)
- `RN-03` 티켓 선택 대기 중 "그만할래" → 이전 변경이 쓰인다 (`is_update_intent`가 무조건 True)

그다음이 `SEC-01`(권한 경계) · `UA-01`(전사 데이터 노출) · `UB-01`(부서 admin이 전사 배너) ·
`UA-03`(백업 중 전체 쓰기 잠김) · `RG-01`(절대 작동 못 하는 버튼) · `DS-32`(4K 두 줄).

## 3-2. 조사 종료 시 정리할 것 (내가 만든 것)

- **`qa-user`·`qa-operator`·`qa-auditor`·`qa-admin` 4계정을 비활성화한다.** 지금 이 계정들이
  `/dev-report` **개발자 월간 리포트에 빈 행으로 섞여 있고**, `/users` 목록 맨 위에 뜨며,
  스프린트 담당자 후보에도 나온다. 명령:
  `sudo … venv/bin/python -m app.cli.user_cli disable --email qa-*@goodmit.co.kr`
- `~/deploy/stage-new2`, `dist/ui-qa-*` 등 산출물은 서버·로컬 모두 `dist`·홈이라 무해하지만,
  서버 홈에 116MB짜리 옛 번들이 여러 개 쌓여 있다(7GB) — 정리하면 좋다.
- 로컬 `.claude/worktrees/` 88개(`C0-7`, 보류 중) — **저장소 grep 을 오염시키므로 조사 방해 요인이기도 하다.**
- **`hshwang@` 계정에 조사용 대화 4개**가 생겼다("방금 말한 것 중에 제일 오래된 건 뭐야?" ×2 등).
  기존 52개에 섞여 있다. 지우거나, 남기기로 했다면 그 사실을 여기 유지한다.
- **`/chat` 의 오래된 대화 하나가 `mode=CREATE` 로 갇혀 있다**(`112347f0-…`, `AI-30`의 실물).
  고치기 전에는 **재현용 증거이므로 지우지 않는다.**
- **`mail_deliveries` 14행 · `approvals` 1행 · `restore_rehearsals` 1행** — 내 실행 검증의 흔적.
  메일은 전부 `unconfigured` 라 **실제 발송은 없었다.** `USE-01` 집계를 다시 낼 때 이것을 뺀다.
- **`saved_views` 에 조사용 행 1개**(`QA 조사용 뷰`, `/workflows`, `hshwang@` 소유). 개인 뷰라
  다른 사용자에게 안 보인다. 지우거나 남겨도 무해하다.

## 3-3. 이번 구간에 철회한 것 (같은 실수를 반복하지 않기 위해 남긴다)

| 철회 | 왜 틀렸나 |
|---|---|
| 「클로비가 ~를 가린다」 계열 **7건**(`VIS-104`·`VIS-122` 등) | **전체 페이지 스크린샷이 `position:fixed` 를 엉뚱한 자리에 그린다.** 살아 있는 DOM 으로 재니 60라우트 중 1건, 긴 표 8종×스크롤 4위치에서 0건. 하네스의 `fab_overlap`은 내내 옳았다 → [D-23](DECISIONS.md) |
| `USE-03` "저장된 뷰에 빈 상태가 없다" | **클릭하지 않고 스크린샷만 보고 판정했다.** 실제로는 빈 상태 문구·저장 미리보기까지 잘 만들어져 있고 DB 저장까지 정상이다 |
| `AI-31` "조건을 조용히 버린다" | **조용하지 않다** — 코드가 반드시 고지하고, 그 주석에 세 번의 회귀 이력까지 적혀 있다. 진짜 문제는 앞단의 의도 분류다 |
| `VIS-107~109` "지금 오류 4건이 나 있다" | **전부 3주 전 것**이고 원인 하나는 이미 고쳐졌다. 진짜 문제는 **아무도 3주간 재시도를 안 눌렀다**는 것 |

## 4. Blocker

| ID | 내용 | 영향 | 조치 |
|---|---|---|---|
| ~~B-1~~ | ~~테스트 서버가 HEAD가 아니다~~ | — | **✅ 해소됨** (2026-08-08 10:01, `UPGRADE_OK`+`DEPLOY_VERIFY_OK`). 이제 서버 = HEAD이므로 실물 조사 결과를 신뢰할 수 있다 |
| ~~B-2~~ | ~~Chrome 확장 미연결~~ | — | **✅ 해소됨** (2026-08-08). 붙자마자 **스크린샷으로는 절대 안 나오는 결함**을 찾았다 — `VIS-72`(검색하면 사용자 콘솔에서 관리자 콘솔로 튕겨 나감). 실조작(`F` 축)이 왜 필요한지 첫 증거 |
| ~~B-2-old~~ | ~~Chrome 확장 미연결.~~ `mcp__claude-in-chrome__list_connected_browsers` → `[]` (4회 확인) | Chrome MCP 검증 불가(콘솔·네트워크 탭·수동 조작·폭 실시간 변경) | **사용자 조치 필요**: 확장이 Claude Code와 **같은 claude.ai 계정**으로 로그인됐는지 · 설치 후 Chrome 재시작 · 확장 팝업에서 연결 버튼 클릭. 그 전까지 Playwright 하네스(실제 Chromium·실제 로그인·실제 서버 DB)로 대체하고 PNG를 직접 판독 |
| ~~B-3~~ | ~~하네스가 자체서명 HTTPS를 못 탄다~~ | — | **✅ 해소됨** — `--insecure` 추가. **SSH 터널은 쓰면 안 된다**(서버가 `COOKIE_SECURE=true`라 Playwright API 클라이언트가 http로 세션 쿠키를 안 싣는다, [DECISIONS D-05a](DECISIONS.md)) |

---

## 5. 환경 사실 (매번 다시 조사하지 말 것)

**서버** `cloviradmin@10.100.64.71` · `https://clovirone-ai.gooddi.lab` · Ubuntu 24.04 ·
**테스트 서버다**(운영 아님, 사용자 확인). SSH 키 인증, sudo는 비밀번호(stdin으로만 전달).

서비스 상태(2026-08-08 확인): `clovirone-web-assistant`·`clovirone-web-worker`·`nginx` 전부 active ·
러너 `:8787`(ticket)·`:8788`(interpreter v2.1.1)·`:8789`(work-assistant v3.57.0) healthy ·
n8n `:5678` active, 워크플로 2개 active + 웹훅 2개 등록(`clovirone-work-assistant`,
`clovirone-notion-user-mapping`) · Claude CLI 2.1.197 · `ASSISTANT_MODEL=sonnet`(systemd env).

**데이터 규모**(서버 DB, 2026-08-08 실측): users 19 · conversations 68 · messages 247 ·
ticket_cache 1077 · search_documents 1201 · notifications 103 · audit_logs 603 · jobs 130.
**0행인 것**: approvals · document_generations · schedule_runs · mail_deliveries ·
offboarding_runs · restore_rehearsals · impersonation_sessions · ai_quotas · announcements ·
saved_views · trash_items · project_weekly_reports (→ `USE-01`).
DB는 `/var/lib/clovirone-web-assistant/web.sqlite3`(**`app.db` 아님**).
읽는 법 — 리다이렉트를 쓰면 sudo 가 stdin 을 빼앗기므로 **SQL 을 인자로** 넘긴다:
```bash
ssh cloviradmin@10.100.64.71 "echo '<비밀번호>' | sudo -S sqlite3 -readonly \
  /var/lib/clovirone-web-assistant/web.sqlite3 \"SELECT COUNT(*) FROM jobs;\""
```

**호스트 사실**: static hostname `ai-n8n-svr` · systemd 255 (`hostnamectl` 에 `show` verb 와
`--property` 옵션이 **없다**, `SYS-02`) · nginx TLS 는
`/etc/clovirone-web-assistant/tls/clovirone-ai.gooddi.lab.crt`(자체서명, issuer==subject,
2027-07-14 만료) · `/etc/ssl/clovirone/` 은 설치 스크립트가 만들지만 **비어 있고 아무도 안 읽는다**.

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
