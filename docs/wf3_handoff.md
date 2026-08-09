# 수렴 판정 및 Sonnet 인계 계획

작성 2026-08-09 · 근거는 저장소 파일 직접 확인 + 본 세션 표본 재검증(읽기 전용). 실서버 쓰기·배포·Notion·메일 없음.

---

## 1. 수렴 판정

**판정: 「새 범주 발견」의 의미에서는 수렴했다. 「커버리지」의 의미에서는 수렴하지 않았고, 앞으로도 조사만으로는 수렴하지 않는다.**
→ **결론: 조사를 끝내고 구현으로 넘어가라.** 남은 미감사 영역은 별도 조사 사이클이 아니라 **구현 단계 안에 흡수**한다(§3 단계 9).

### ① 새로운 큰 범주가 더 나오는가 — **아니다 (수렴 신호 3개)**

- **독립 워크플로 2회가 같은 근본 원인에 도달했다.** WF1(프런트 화면 40개 판독 → R1~R7)과 WF2(백엔드 6영역 → R1~R6)는 대상·방법·조사자가 다른데 결론이 같다: **「규칙·헬퍼·술어·토큰이 이미 있는데 부르는 쪽이 안 부른다.」** WF1-R1(옵트인 12곳) · WF2-R1(스코프 관문 밖 7곳) · WF2-R2(무효화가 표가 아니라 기억에 의존 7곳) · WF2-R6(술어가 그 자리에서 안 불림 6곳). 서로 다른 표본에서 같은 분포가 나오는 것이 수렴의 정의다.
- **최근 「새 범주」는 결함 종류가 아니라 계측 축이 늘어난 것이다.** RESP·CTR·FAIL·HOST·KBD·SEM·AI-SCOPE는 전부 **새 프로브를 만들었더니 생긴 범주**다. 프로브를 계속 만들면 범주는 무한히 늘어난다 — 이건 "아직 안 끝났다"의 증거가 아니라 **정지 규칙이 없다**는 뜻이다. 실제로 그중 SEM은 열자마자 「강점」으로 닫혔고(실결함 2건), HOST는 200행·XSS가 무결점이었으며, RESP·HOST는 **원인이 하나로 합쳐졌다**(D-40, `DataTable` 한 곳).
- **미감사 영역 표본 검사 6곳이 전부 건강했다** (이번 세션에 직접 코드 확인, ✅):

| 미감사 영역 | 가설 | 실제 확인 결과 |
|---|---|---|
| `app/team_chat/router.py:453-491` DM 이미지 IDOR | 멤버십 검사 누락 의심 | ✅ **경계가 실제로 구현돼 있다.** `service.ensure_access` 를 파일 서빙 **전에** 호출하고 `ForbiddenError → NotFoundError` 로 바꾼다(:472-475). nosniff + 서버 판정 media_type + `content_disposition()` 까지 붙는다 |
| `app/core/uploads.py` traversal / 네임스페이스 | `../`·널바이트로 탈출 의심 | ✅ `_NAMESPACE_RE = ^[a-z][a-z0-9_]{0,31}$` + `_STORED_NAME_RE = ^[0-9a-f]{32}\.[a-z0-9]{2,5}$` 로 **경로 조각 두 개 모두 화이트리스트**. 사용자 파일명은 경로로 안 쓴다 |
| `app/core/sync_prune.py` 거부 신호 무시 (WF2 R5) | 3개 호출부가 `refused` 를 안 읽을 것 | ✅ **3/3 전부 읽는다** — `tickets/sync.py:207-212`·`team_docs/sync.py:129-132`·`projects/sync.py:336-341` 이 `refused` 를 notes 에 넣고 `bad` 로 승격. 1건일 때 0나눗셈도 `MIN_ROWS_FOR_RATIO_GUARD` 로 막힘 |
| `app/core/etag.py` 사용자 간 캐시 오염 | 같은 ETag 재사용 의심 | ✅ ETag 가 **페이로드 바이트 해시**라 구조적으로 사용자별로 갈린다. `Cache-Control: private, no-cache` |
| `app/cli/user_cli.py` 권한 상승 가드 우회 | `ensure_can_manage_target` 미적용 의심 | ✅ 웹과 **같은 service 함수**를 부르고 그 안에서 가드가 돈다(`users/service.py:230`). docstring 의 단언이 참이다 |
| `app/core/uploads.py` polyglot 실행 | GIF헤더+`<script>` 실행 | ✅ 실행 불가 — `nosniff` + 서버 판정 media_type. (바이트가 통과할 수는 있으나 그건 결함이 아니다) |

  → **6/6 건강.** 유일한 부산물 발견은 Low 급이다: `user_cli` 는 감사를 **`actor_id=None`** 으로 기록한다(:140·:149·:192·:203 등). 즉 `ADM-01` 이 센 **CLI 잠금 해제 13회는 누가 했는지 감사 로그에 없다.** 이건 새 범주가 아니라 ADM 절에 붙는 한 줄이다.

### ② 전혀 안 본 영역이 남았는가 — **남았다 (사실이다)**

`grep` 으로 재확인했다(✅, BACKLOG·QA_COVERAGE·wf1_synthesis·wf2_synthesis 4종 합산 히트 수):

```
app/team_chat/ → 0    core/uploads → 0    app/notion_console/ → 0    app/cli/ → 0
sync_prune → 0        tenant_config → 0   app/notion_mapping/*.py → 0
document_generate → 0 mail_send → 0       project_weekly_summary → 0  llm_connection_test → 0
people.py → 0         versioning → 0      etag → 0                    presence → 0
```

- `app/team_chat/` **1,953줄 = 제품 최대 미감사 백엔드 모듈**. QA_COVERAGE:98-99 에서 `/chat-rooms` 는 8축 중 S 하나만 `O`.
- `app/jobs/handlers/` 5개(document_generate 302 · schedule_run 139 · mail_send 97 · project_weekly_summary 84 · llm_connection_test 82) = **한 번도 실행 안 됨 + 한 번도 읽힘 안 됨**.
- `app/core/` 36파일 중 CORE-01~12 가 다룬 건 12개. **tenant_config(11KB, 소비자 13모듈)·people·versioning·presence·scope·notion_blocks·source_registry 등은 안 봤다.**

**그러나 이것은 조사를 계속할 이유가 되지 못한다.** ①의 표본 6/6이 건강했고, 이 영역들의 결함 가설은 전부 **이미 이름 붙은 범주**(R1 배선 누락 · R5 부분성공 · IDOR)의 재탕이다. 새 범주가 아니라 **같은 범주의 추가 사례**를 세는 일이고, 그건 구현이 그 파일을 건드릴 때 하는 편이 싸다.

### ③ QA 커버리지에 큰 공백이 있는가 — **있다. 그리고 이게 진짜 공백이다**

| 축 | 73라우트 기준 현황 | 판정 |
|---|---|---|
| `S` 화면 판독 | 66/70 | ✅ 거의 끝 |
| `R` RBAC(화면 게이팅) | 4역할 197페이지, 거부화면 0 | ✅ `O` 로 승격됨 |
| `V`·`K`·`B`·`S2` | 실측 완료(도구 8종 상시 재사용 가능) | ✅ |
| **`F` 실기능 실행** | **0** | ❌ |
| **`D` DB 재확인** | **0** | ❌ |
| **`C` 콘솔·네트워크** | **0**(정상 경로만 부분) | ❌ |
| **`L` 화면 간 반영** | **0** | ❌ |
| **`U` 실사용 이력** | 12중 6 미실행 (오프보딩·메일·AI 상한·공지 배너·주간 리포트·휴지통) | ❌ |
| `A` API | `~`(RBAC 17엔드포인트만) | ⚠️ |

**핵심:** `F`·`D`·`L`·`U` 는 **조사로 채울 수 없는 축이다.** 이 축들은 "고치고 → 실행하고 → 결과를 다시 읽는" 행위로만 채워진다. 지금 조사 사이클을 한 번 더 돌려도 이 4열은 `-` 로 남는다. 그래서 **커버리지 공백이 남아 있다는 사실 자체가 구현으로 넘어가야 할 이유**다 — §3의 모든 단계에 "배포 후 재검증"을 붙인 이유가 이것이다.

### 수렴하지 않았다면 무엇을 더 봐야 하는가 (좁게, 구현 전 확인 항목으로만)

조사 사이클이 아니라 **§3 단계 9 안에서 시간 상자 4시간**으로 처리한다. 이 4개만 남긴 이유는 각각 **이미 확정된 Critical/High와 같은 실패 형태의 후보**이기 때문이다.

1. **`app/notion_console/service.py`** — 토큰 저장 경로(`core/secret_refs.write`)와 읽는 경로(`OutboundClient` 의 secret 주입)가 **같은 ref 이름을 보는가**. 갈라져 있으면 `SYS-01` 과 정확히 같은 「저장됐다는 거짓말」이다. 함께: `probe_notion.py` 의 DB 생성이 `OutboundClient` 관문을 지나는가(§2-2).
2. **`app/team_chat/service.py` 의 seq 할당기 ↔ `app/games/service.py` diff** — service.py 가 "놀이의 seq 할당기를 그대로 옮겼다"고 적는데, games 는 12라운드에서 동시성/유령우승 버그 3건이 난 코드다. **복제 시점이 수정 전인지 후인지**만 보면 된다.
3. **`app/core/tenant_config.py` 의 판정 함수 + 소비자 13곳** — 「개발 기본값이 그대로 남아 있을 때 '설정됨' 으로 판정되는가」 한 가지. 그리고 13곳이 **같은 함수를 부르는가, 자기 사본을 갖는가**(= 이 제품의 지배적 결함 유형). `DEPLOY-01`·`WF2 H4` 가 이 판정을 소비하는 설치 경로에서 이미 터졌다.
4. **`app/jobs/handlers/` 5개 정적 대조** — ① 예외를 삼키고 `succeeded` 를 쓰는가(R5) ② 재시도 멱등한가 ③ 외부 호출이 `OutboundClient` 를 지나는가. **실행하지 않는다** — `document_generate`·`mail_send` 는 외부 부작용이 있다(D-21).

---

## 2. 재검증에서 뒤집힌 것

| ID | 판정 | 무엇이 틀렸나 | 어떻게 고쳐 쓰는가 |
|---|---|---|---|
| **AI-40** | **PARTIALLY_WRONG** | 결론(모르는 질문에 틀린 숫자로 답한다)은 참. **Critical 근거가 거짓이다.** BACKLOG:2025 는 「앞의 고지도 이번엔 붙지 않았고 **단정적인 숫자 한 줄**만 남는다」고 적고 그걸 이유로 `AI-31` 보다 나쁘다고 랭크했다. 그런데 조사자 자신의 산출물 `dist/ai-scope/ai_scope.json` 4번 항목(len=100 → `text[:600]` 절단에 안 걸린 **전문**)은 2줄이고 **1줄째가 고지문**이다: 「'지금 실패한 백그라운드'라는 이름으로는 찾지 못해 그 조건을 빼고 보여드립니다…」 + 「조건에 맞는 티켓 완료 제외: 184건입니다.」 고지가 있고, 답 줄 자체가 대상 종류(**티켓**)를 밝힌다 | **재기술 후 재랭크.** 정확한 진술: 「규칙엔진이 못 알아들은 질문을 티켓 질의로 대체하면서, 고지는 붙이지만 그 뒤에 사용자가 묻지 않은 집계를 숫자로 내놓는다 — 정답은 4(실패 잡). 목록과 달리 **숫자는 사용자가 눈으로 틀렸음을 알 수 없다.**」 이것은 별개 결함이 아니라 **`AI-41`(규칙엔진 경로가 정직한 거절로 안 떨어진다)과 같은 뿌리**다 → 두 건을 하나로 묶고 심각도는 거짓 전제 없이 다시 논한다 |
| **FAIL-01** | CONFIRMED (판정 유지) · **근거 3건 정정** | 메커니즘은 코드에서 독립 재도출됨(`frontend/src/lib/api.js:44-45,70` — 2xx 비JSON 이 **성공 + `null`** 로 해석). 그러나 **증거표 BACKLOG:1874-1879 의 '실제' 열 3칸이 틀렸다**: 프로브는 `dist/ui-qa-admin-2` = **qa-admin** 세션으로 돌았는데 ⑴ `/chat` 「대화 52개 있다」 → qa-admin 은 `/api/conversations` = `{"items":[]}` (52는 hshwang@ 것) ⑵ `/my-tickets` 「티켓이 있다」 → `mapped:false, total:0` ⑶ `/users` 「표 0행, 아무 말 없음」 → 실제로는 「사용자가 없습니다」 빈 상태 문구가 있다 | **'실제' 열을 인용하지 말 것.** 결함은 "데이터가 있는데 없다고 말한다"가 아니라 **"API 실패와 0건을 구분할 수단이 화면에 없다"**이다(그게 D-37·D-38 이 말하는 것이고 수정 지점도 같다). ⚠️ **부작용:** 「데이터가 있는데 없다고 말한다」의 **실제 노출 규모는 아직 모른다** — 매핑된 계정으로 `failure_states.py` 를 다시 돌려야 한다(§5-3) |
| SYS-01 | CONFIRMED (**강화됨**) | 뒤집힌 것 없음. 코드+실서버 nginx 설정+실핸드셰이크로 독립 재확인. **추가 발견:** `deploy/systemd/clovirone-privhelper.service:60` 의 `ReadWritePaths` 가 `/etc/ssl/clovirone` 만 담고 `/etc/clovirone-web-assistant` 를 **안 담는다** | **수정 범위가 커진다** — `actions_service.py` 경로 한 줄로는 안 되고 **유닛의 `ReadWritePaths` 도 함께** 고쳐야 한다. WORK_STATE §3-1 의 "고치는 것은 경로 한 곳" 은 정정 필요 |
| DEPLOY-01 | CONFIRMED (**범위 확대**) | 뒤집힌 것 없음. 두 스크립트 전문 확인. **추가:** 절차서 **step 3도 따로 깨져 있다** — `build-bundle.sh:70` 이 `-C "$OUT" stage` 로 말아 아카이브 루트가 `stage/` 인데 문서는 `--strip-components=1` 없이 `-C stage` 로 푼다(→ `stage/stage/app-src`), 같은 줄의 `sha256sum -c MANIFEST.sha256` 은 tarball **내부** 매니페스트를 가리킨다 | 「문서 명령을 **복붙 그대로** 실행해 통과」를 완료 기준으로 삼아야 한다 — 스크립트 단위 통과가 증거가 아니라는 것이 이 사태의 원인이다 |

**요약: 정면으로 뒤집힌 것은 `AI-40` 1건.** 나머지 3건은 판정 유지이나 `FAIL-01` 은 근거를, `SYS-01`·`DEPLOY-01` 은 수정 범위를 정정해야 한다.

---

## 3. Sonnet 구현 계획

> **전제:** 이 제품의 지배적 결함은 「규칙이 없어서」가 아니라 **「안 불려서」**다(D-45·WF1-R1·WF2-R1/R2/R6). 따라서 아래는 **화면·모듈 단위가 아니라 배선 단위**로 묶었다. 한 파일을 고치면 N곳이 함께 닫히는 순서다.
> **새로 설계하기 전에 제품 안의 정답을 먼저 찾는다**(D-22) — 각 단계의 "본보기" 칸이 그 정답의 위치다.
> **완료의 정의:** `실환경검증완료` 만 완료다. 「고쳤다」는 완료가 아니다.

### 단계 0 — 코드 아님. 되돌릴 수 없는 것 먼저 (오늘)

| | |
|---|---|
| **무엇** | ⑴ `dist/ui-qa-admin-2/…/user_team-doc-detail.png` 처리 + git 히스토리 확인 ⑵ Notion 원본 문서에서 평문 자격증명 제거 ⑶ 노출된 계정·비밀번호 회전 |
| **왜** | WF1 단독 High + `SEC-10`. **72건 중 유일하게 시간이 갈수록 회수 비용이 커진다.** 접속 URL 2 · 계정 ID 3 · 비밀번호 4 · RDP IP+포트+계정이 마스킹 없이 렌더되고, 그 PNG 가 **저장소 안에** 있다 |
| **파일** | `dist/ui-qa-admin-2/**/user_team-doc-detail.png`, Notion 원본(앱 밖) |
| **완료 기준** | 저장소·히스토리에서 그 값이 grep 되지 않고, 노출 자격증명이 회전됨 |
| **재검증** | `git log -p --all -S '<자격증명 일부>'` 무결과 |
| ⚠️ | **원본은 실고객 워크스페이스다.** Notion 쓰기는 사용자 승인 후에만 |

### 단계 1 — 배포 배선 복구 (다른 모든 단계의 전제)

| | |
|---|---|
| **무엇** | ⑴ `upgrade-*.sh` 가 installer 에 `DNS_NAME`·`BIND_IP` 전달 ⑵ 서비스 정지 **전** 사전검증 ⑶ `update-from-git.sh:61-88` 의 `rollback_now()` 를 번들 경로에 이식 ⑷ 설치처 고유값 가드 블록을 rsync **앞으로** 이동 ⑸ `clovirone-privhelper.service` 를 backup·rollback 대상에 추가 ⑹ 절차서 tar/sha256 3줄 정정 |
| **왜** | **`DEPLOY-01`(Critical).** 문서대로 하면 web·worker 를 정지시킨 뒤 `exit 2` 로 죽고 되살리는 코드가 없다 = **서비스 중단**. 여기가 막히면 나머지 전부를 고쳐도 내보낼 수 없다. `H5`(privhelper 죽은 채 `ROLLBACK_OK`)·`H3`(실패 처리 0)·`H4`(가드 주석이 거짓)가 같은 커밋에 닫힌다 |
| **파일** | `scripts/upgrade-clovirone-web-assistant.sh:20-33` · `scripts/install-clovirone-web-assistant.sh:154, 217-252(exit 21은 :249)` · `scripts/backup-clovirone-web-assistant.sh:21` · `scripts/rollback-clovirone-web-assistant.sh:64,76` · `scripts/build-bundle.sh:70` · `docs/MAINTENANCE_PLAYBOOK.md:64-70` · `docs/DEPLOY_NOW.md:28` · `tests/unit/test_update_script_contract.py`(대상에 upgrade 추가) · `tests/unit/test_deploy_wiring.py:97-100(재시작 대상에 있는가로 변경), :157-163(guard_at < rsync_at 로 강화)` |
| **본보기** | `scripts/update-from-git.sh:61-88, 301-302` — 호출 형태와 롤백의 정본이 **같은 저장소에 이미 있다** |
| **완료 기준** | 절차서에 적힌 명령을 **한 글자도 안 고치고 복붙 실행**해서 통과. 실패를 주입(pip·alembic·`nginx -t`·healthz 각각)했을 때 **자동 롤백 후 서비스가 다시 active** |
| **배포 후 재검증** | `systemctl is-active clovirone-web-assistant clovirone-web-worker clovirone-privhelper nginx` 4개 active + **nginx 경유 URL**(`https://clovirone-ai.gooddi.lab/healthz`)로 200. ⚠️ `127.0.0.1:8080` 직접 찌르기는 증거가 아니다(`H5`·R5가 그 함정이다) |

### 단계 2 — SYS-01 TLS 경로 + 특권 헬퍼 샌드박스

| | |
|---|---|
| **무엇** | `CERT_PATH`/`KEY_PATH` 하드코딩을 `settings.tls_cert_path`/`tls_key_path` 로 교체 + `privhelper` 유닛 `ReadWritePaths` 에 `/etc/clovirone-web-assistant` 추가 |
| **왜** | **`SYS-01`(Critical).** 인증서 교체가 성공 메시지·새 subject·새 만료일까지 보여 주면서 nginx 가 안 읽는 경로에 쓴다. `CLAUDE.md` §10 이 "운영 전에 하라"고 적은 바로 그 작업이 조용한 무동작이다 |
| **파일** | `app/sysops/actions_service.py:40-43, 170-217` · `deploy/systemd/clovirone-privhelper.service:60` · `scripts/install-clovirone-web-assistant.sh:281(`mkdir /etc/ssl/clovirone`) vs :294(`$ETC_DIR/tls/...`) — 13줄 떨어진 두 경로를 하나로 |
| **본보기** | `app/setup/probes.py:353` · `app/health/service.py:136` — **올바른 값을 이미 둘 다 쓰고 있다** |
| **완료 기준** | `grep -rn '/etc/ssl/clovirone' app/ deploy/ scripts/` 가 0건이거나 정리 코드에서만 매치 |
| **배포 후 재검증** | 실서버에서 인증서 교체 실행 → **`openssl s_client -connect 10.100.64.71:443` 의 `notAfter` 가 실제로 바뀐다.** 화면의 성공 메시지는 증거가 아니다(그게 이 버그다) |
| ⚠️ | 실서버 TLS 변경 = 사용자 승인 필요. 승인 전에는 스테이징에서만 |

### 단계 3 — `lib/api.js` 한 파일 (레버리지 최대: 131 호출부 + 실패상태 8화면 + 공지 500)

| | |
|---|---|
| **무엇** | ⑴ 오류 문구 조립을 `message` → **`details` 우선**으로(+`"Value error, "` 접두사 제거) ⑵ **2xx 비JSON 을 성공으로 취급하지 않는다**(현재 `catch → body=null → return null`) ⑶ 공지 PATCH 의 `None` 을 '변경 없음'으로 ⑷ 여력 있으면 `loc` 마지막 요소를 `setErrField` 로 |
| **왜** | 네 결함이 **한 파일 두 줄**에 모인다. `H2` — `e.message` 호출부 **131건**이 지금 영어 `"Invalid request data"` 만 본다(한국어 사유는 `error.details` 에만 실림). `FAIL-01`·`FAIL-02` — 2xx 비JSON 이 성공+null 이 되어 8화면 전부가 실패를 **「~가 없습니다」**로 바꿔 말하고 재시도 버튼을 잃는다. `FN-40`/`C1` — 공지 「내용」을 비우면 500 + 영어(POST 경로는 `or ""` 로 이미 막고 **PATCH 만 빠졌다**) |
| **파일** | `frontend/src/lib/api.js:44-45, 50, 70` · `app/announcements/router.py:190-192` · `frontend/src/ui/kit.jsx:889-892` |
| **본보기** | `app/static/js/change_password.js:492-501` — **details 우선 + 접두사 제거 규칙이 바닐라 시절에 이미 적혀 있다.** React 로 전파만 안 됐다. null 코어서는 `app/schedules/router.py:78-80` 의 `mode="before"` |
| **완료 기준** | 게시판 본문 20,001자 → 화면에 **「본문은 20000자 이하여야 합니다.」** · 공지 body 비우고 저장 → **422 한국어**(500 아님) · 200+HTML 주입 → 8화면 전부 오류 문구 + 재시도 |
| **배포 후 재검증** | `.venv/Scripts/python -m scripts.ui_qa.failure_states --mode garbage`(도구 존재, `scripts/ui_qa/failure_states.py`) → **「~가 없습니다」 0건 · 재시도 버튼 ≥6/8 · `/team-docs` 무한 로딩 해소**. ⚠️ **매핑된 계정으로** 돌릴 것(§2 FAIL-01 정정 사유) |
| ⚠️ | `inputProps` 로 min/max 다는 접근은 **통하지 않는다** — `SettingEditor.jsx:59-60` 이 이유를 이미 적어 뒀다(Save 가 커스텀 버튼이라 네이티브 검증이 안 돈다). `maxLength` 만 예외 |

### 단계 4 — `home/readers.py` 에 viewer 를 붙인다 (WF2-R1, 오늘 실제로 새는 유일한 것)

| | |
|---|---|
| **무엇** | `recent_documents`·`recent_board_posts`·`documents_changed_between`·`board_posts_between` 4함수에 **viewer 인자 추가** → `doc_in_scope`·`org_id` 경유 → `kind=KIND_FREE` 추가 → `comment_count` 루프를 `comment_counts` 로. 같은 커밋에 문서 목록의 범위 필터를 **SQL 로 내림** |
| **왜** | `H7` — 다른 부서 문서의 제목·소유자·종류가 **전 직원 홈 사이드레일에 지금 뜬다**(잠재 아님). `H6` — 홈 게시판 위젯이 조직 게이트 밖(단일 조직이라 오늘 유출은 없음). `H8` — 범위를 페이지 자른 **뒤** 파이썬으로 걸러 사용자가 「3건」 페이저와 **빈 목록**을 동시에 본다. **수정 범위가 1파일 3~4함수 + service.py 2줄인데 High 3 + Med 3 + Low 1이 닫힌다** |
| **파일** | `app/home/readers.py:69-102, 105-109` · `app/home/service.py:126-127` · `app/team_docs/router.py:124-126` |
| **본보기** | `app/board/router.py:244-263`(정답 모양) · `app/tickets/service.py:289-311 _scope_assignee_ids`(질의) + `:459-469 _drop_out_of_scope`(그물) · `app/tickets/router.py:235-237` 은 **이 결함에 이미 이름을 붙여 놨다** |
| **완료 기준** | 회귀 테스트: 「조직/부서 밖 사용자의 `/api/home/today` 와 `/api/board/posts`·`/api/team-docs` 가 **같은 집합**을 본다」 |
| **배포 후 재검증** | `qa-user` 세션으로 세 엔드포인트 교차 대조(`D` 축을 처음으로 채우는 단계다) |

### 단계 5 — 프런트 공용 규칙을 **옵트인 → 기본값**으로 (WF1-R1, D-45)

| | |
|---|---|
| **무엇** | `EmptyState` 에 `KO_WORD_BREAK` · `ROUTE_OWNER` 2경로 등록 · `detailTitle` 이 `rowName` 을 쓰도록 · `config.help` 의 `tone` 존중 · `activeCol`/`searchPlaceholder`/`openLabel`/`align:right` 지정 · `Profile.jsx` 에 `shortUA`+Tooltip. **그리고 테스트를 "특정 컴포넌트"에서 "사용자 산문을 그리는 모든 컴포넌트"로 확장**, `ROUTE_OWNER` 미등록은 CI 실패 |
| **왜** | **12건이 배선만으로 닫히고 논쟁할 것이 없다** — 토큰·헬퍼·등록표가 **이미 다 있다**. `EmptyState` 한 줄 = 31파일. `ROUTE_OWNER` 2줄 = High 1건. 실패 모드가 조용해서 리뷰에서 안 걸리고, **뒤집지 않으면 다음에 추가되는 모든 화면에서 재발한다**(KO_WORD_BREAK 는 이번 판독에서 3번 재발이 실측됨). `SEM-01`(「상세 보기」 100개 동명, `kit.jsx:403-413` 의 `openLabel` 탈출구 미사용)도 여기 포함 |
| **파일** | `frontend/src/ui/kit.jsx:295-311, 403-413` · `frontend/src/app/navConfig.js:240-265` · `DataScreen.jsx:486-489, 524` · `Trash.jsx:140-142` · `Profile.jsx:383-386` · `detailFields.js:18-29` · `columnHelpers.jsx:11-15` · `platform.js:67` · `frontend/src/ui/ko-wordbreak.test.jsx:25-37`(확장) |
| **완료 기준** | 확장한 테스트가 RED → GREEN. `nav-active` 테스트가 미등록 라우트에서 실패 |
| **배포 후 재검증** | 하네스 재실행(`--label c3-*`) + 해당 8화면 PNG 재판독 |

### 단계 6 — 표는 화면 28개가 아니라 `DataTable` **한 곳**에서 고친다 (D-40)

| | |
|---|---|
| **무엇** | ⑴ `DataTable` 열에 콘텐츠 폭 + 최대폭 제약(균등분산 금지) ⑵ 표→카드 전환 임계값을 **전역 상수가 아니라 표가 필요한 폭**으로(D-33) |
| **왜** | `RESP-01`(1024 에서 `/users` 사용 불가 — 이메일 6줄·이름 4줄·표가 뷰포트 밖)과 `HOST-01`(셀 51×2,353px, 문서 폭이 뷰포트의 3.3배)이 **같은 뿌리**다 — 두 경우 다 셀 폭이 **51px** 로 측정됐다. **768 에서 도는 카드 레이아웃은 이미 훌륭하다** — 켜지는 지점만 낮다. 열이 적은 표(`/integrations` 6열)는 1024 에서 멀쩡하므로 전역 상수로는 못 푼다 |
| **파일** | `frontend/src/ui/kit.jsx:415`(`TABLE_CARD_BREAKPOINT = 899.95px`) + `DataTable` 열 정의 |
| **완료 기준** | `hostile_data.py --mode long` 에서 문서 폭 ≤ 뷰포트 · 1024 에서 `/users` `vertical_text_collapse` 0 |
| **배포 후 재검증** | `scripts/ui_qa/hostile_data.py`(long/many/weird) + **768/1024/1200/1366 4폭 스윕**(D-34 — 기존 목록이 768→1366 으로 건너뛰어 최악 구간을 한 번도 안 봤다) |

### 단계 7 — 4K 두 줄 (`DS-32`), 가장 싼 252건

| | |
|---|---|
| **무엇** | `frontend/src/…/TopSearch.jsx:68` `fontSize:"11px"` · `Mascot.jsx:364` `fontSize="10px"`(**prop 이다 — grep 주의**) 를 `--clv-root-fs` 스케일 따르도록 |
| **왜** | 4K 전수 스윕(64라우트 × 2테마 = 128페이지)에서 **정확히 2요소 × 126페이지 = 252건**이고 그 밖의 tiny text 는 **하나도 없다**. 통과한 2페이지는 앱 셸이 없는 `public_login` 뿐 |
| **완료 기준** | 3840 스윕 `tiny_text` 0 fail |
| **배포 후 재검증** | **반드시 `--viewports 3840x2160`.** 1920 으로 돌리면 검사가 skip 되어 확인 자체가 안 된다(`QA-10`) |

### 단계 8 — 러너 라우터 **전처리 1회 리팩터링** (별도 트랙, 개별 패치 금지)

| | |
|---|---|
| **무엇** | 질문·취소·부정·댓글 술어를 **pending 분기 안이 아니라 라우팅 전처리에서 한 번** 평가. `_READ_OR_QUESTION_RE` 의 **호환 자모 리터럴** `ㄹ까`(U+3139)·`ㄴ지`(U+3134) → `[가-힣]까`/`[가-힣]지`. 술어마다 유니코드 정규화 테스트 |
| **왜** | `RN-01`(질문이 완료 쓰기) · `RN-02`(거절이 실행) · `RN-03`(「그만할래」가 쓰기) · `H10`(자모 리터럴로 가드 무력화) · WF2-R6 6건이 **전부 같은 뿌리**다 — 판단 로직이 없는 게 아니라 **그 경로에서 안 불린다.** 개별 패치는 두더지잡기다. `AI-30`(11일 묵은 CREATE 모드가 무관한 질문 납치) + `AI-37`(탈출어를 그 자리에서 안 알려줌)도 같은 트랙: **러너 문맥에 만료가 없다** |
| **파일** | `runner/claude-work-assistant/…/assistant.py:4984-4988, 5492` + 최상위 라우터 · 회귀는 `test_assistant.py:3416` 계약 미러링 |
| **완료 기준** | `'될까'`·`'바꿀까'`·`'된 건지'` 가 질문으로 인식 · UPDATE-pending 중 `'완료로 바꿔도 될까?'` 가 **WRITE_UPDATE 로 안 간다** · CREATE 중 `is_undo_intent`·`DECLINE_COMMANDS` 가 도달 가능 |
| **배포 후 재검증** | **로컬 스텁 재현만**(`D-21`). ⚠️ **실서버에서 재현하지 않는다** — 승인 없는 Notion 쓰기가 나간다. `AI-30` 회귀는 서버에 남아 있는 대화 `112347f0-…` 에 같은 질문을 던져 `ai_verify.py` 대조 실험으로. **그 대화를 고치기 전에 지우지 말 것** |

### 단계 9 — 미감사 4곳 좁은 확인 (시간 상자 4h, §1 말미 목록)

`notion_console` 저장↔읽기 ref 대조 · `team_chat` seq ↔ `games` 수정본 diff · `tenant_config` 판정 + 소비자 13곳 · `jobs/handlers` 5개 워커 계약 정적 대조.
**완료 기준:** 4개 각각 「결함 있음(BACKLOG 등재)」 또는 「확인함, 건강」 중 하나로 라벨링. 「아마 괜찮을 것」 금지.

### 단계 10 — `U`·`F`·`D`·`L` 축 채우기 + 조사 잔재 정리 (마지막)

- **미실행 기능 6개를 끝까지 한 번씩 돌린다**: 오프보딩 · 메일 · AI 사용 상한 · 공지 배너 · 주간 리포트 · 휴지통. 본보기는 `scripts/ui_qa/saved_view_e2e.py` + RSTR 절의 3단계(**실행 → DB → 화면 반영**).
  ⚠️ 메일·오프보딩은 외부 부작용(SMTP) — D-21 확인 후. ⚠️ **공지 배너는 다른 19명에게 보인다 — 켜면 반드시 되돌린다.** ⚠️ 스케줄 실행은 유일한 스케줄이 **AI 채팅 웹훅을 리포트 생성기로** 가리켜 켜면 Notion 쓰기가 나갈 수 있다(`SCHD-01`) — **켜지 않는다.**
- **정리**: `qa-user`·`qa-operator`·`qa-auditor`·`qa-admin` 4계정 `disable`(지금 `/dev-report` 에 빈 행으로 섞이고 `/users` 맨 위에 뜬다) · 로컬 `.claude/worktrees/` 88개(저장소 grep 오염) · 서버 홈 옛 번들 7GB · `mail_deliveries` 14 / `approvals` 1 / `restore_rehearsals` 1 은 조사 흔적이므로 `USE-01` 재집계에서 뺀다.

### 임박한 것 — 위 순서와 별개로 시간이 지나면 저절로 터진다

`UB-40` 오프보딩 목록이 **21명째부터 잘린다**(현재 18명, `Offboarding.jsx:65` `page_size=20` 하드코딩, 총건수·페이저·잘림 경고 없음 — 세 명만 더 들어오면 퇴사 처리 대상자를 못 찾는다) · `RSTR-03` 자동 백업 꺼짐 + 마지막 백업 2026-07-19.

---

## 4. Sonnet 이 먼저 읽을 파일 순서 (5개)

| # | 파일 | 왜 / 어디를 볼 것인가 |
|---|---|---|
| 1 | **`docs/WORK_STATE.md`** | 진입점. **§3-0-B(Critical 2건)** → **§3-3 철회 목록** → §5 환경 사실(서버 DB 경로·읽는 법·배포 절차). ⚠️ **§3-3 을 읽기 전에 BACKLOG 항목을 집어 들지 말 것** — 철회·정정된 항목이 그대로 남아 있다 |
| 2 | **이 인계 문서 §2 + §3** | BACKLOG 보다 먼저. §2 가 **어느 근거를 인용하면 안 되는지**(AI-40 의 전제, FAIL-01 의 '실제' 열)를 말하고, §3 이 착수 순서다 |
| 3 | **`docs/wf2_synthesis.md`** | 백엔드 근본 원인 R1~R6 + §1 Critical/High 13건 전수표(문제·근거·**고칠 지점 file:line** 3열). §4 「가장 먼저 고칠 것 3개」가 §3 단계 1·3·4 의 원문이다 |
| 4 | **`docs/wf1_synthesis.md`** | 프런트 R1~R7 + **§2 「[잘 됨] 본보기 10개」**. D-22("새로 설계하기 전에 제품 안의 정답을 먼저 찾는다")를 실행하는 목록이라 단계 5·6 을 쓸 때 여기부터 본다 |
| 5 | **`CLAUDE.md` §2(불변 규칙 10) + §8(함정)** | 깨면 정적 검사·CI 가 막는 것들. 특히 §2-2(`import httpx` 금지) · §2-6(`innerHTML` 금지) · §8(`STRFTIME('%f')`, 라우터 팩토리의 `from __future__`, `assets.py` 지문 캐시 금지) |

> **`docs/BACKLOG.md`(2,551줄)는 통독하지 않는다.** 절 단위 색인으로만 쓴다: `SYS`(927) · `USE`(1057) · `SRCH`(1244) · `NOTI`(1342) · `ADM`(1373) · `FAIL`(1859) · `HOST`(1896) · `KBD`(1929) · `AI-SCOPE`(2009) · `WF1`(2037) · `WF2`(2373). 정정 절은 **1163**(클로비 가림 7건 철회) · **2243**(RET 정정).
> 파일 단위 원문이 필요하면 `docs/wf1_findings.json`(73KB) · `docs/wf2_findings.json`(110KB).

---

## 5. 남은 불확실성 — 조사로 답 못 낸 것

1. **미감사 11영역 중 5곳은 열지도 않았다.** 표본 6곳이 건강했다는 것은 **6곳에 대한 사실**이지 나머지 5곳(`tenant_config` · `people` · `versioning` · `notion_mapping/service.py` · `jobs/handlers` 5개)의 상태에 대한 예측이 아니다. **「건강할 것」이 아니라 「모른다」**로 취급한다(D-48).
2. **`/etc/ssl/clovirone` 이 실제로 비었는지 확인 불가**(❌). 0750 root 이고 sudo 비밀번호가 없다. `SYS-01` 판정에는 무관하나(경로 불일치는 nginx 설정 + 코드만으로 확정), **정리 범위와 privhelper 가 뭘 써 왔는지는 모른다.**
3. **`FAIL-01` 의 실제 노출 규모를 모른다.** 프로브가 **Notion 미매핑·데이터 0건 계정**(qa-admin)으로 돌아서, "실패를 없음으로 말한다"는 메커니즘은 코드로 확정됐지만 **"데이터가 있는데 없다고 말하는" 장면은 한 번도 실측되지 않았다.** 단계 3 의 재검증은 **매핑된 계정**으로 다시 돌려야 한다.
4. **`AI-42`(모델이 티켓 부분집합만 받는다)의 절단 규모가 미측정이다.** 모델이 스스로 "일부만 포함된 상태"라고 말해서 알았을 뿐, **몇 건 중 몇 건인지 모른다.** 이 수치 없이는 AI 도우미의 모든 집계·요약 답변의 신뢰도를 말할 수 없다.
5. **다크 테마 판독과 4K 판독이 남았다.** 66/70 은 **라이트 1920 기준**이다. `CTR` 이 **다크 8/8 위반**을 이미 찾았으므로 다크 판독은 라이트와 같은 결과를 낼 이유가 없다.
6. **러너 수정을 실환경에서 검증할 방법이 아직 없다**(D-21 로 실서버 재현 금지). 단계 8 은 **로컬 스텁 통과 = ⚠️ 미확인**으로 남는다. 실환경 확인 절차를 사용자와 먼저 합의해야 한다.
7. **조사 대부분이 단일 조직·단일 부서 실데이터 위에서 이뤄졌다.** `UA-02`·`UB-01`·`H6` 같은 스코프 결함의 "오늘 유출 여부" 판정이 그 사실에 의존한다 — **조직이 둘이 되는 날 잠재가 현행이 된다.**
8. **4K 회귀의 원인 커밋을 특정하지 않았다.** 2026-08-04 실행은 992페이지 fail 0 이었는데 지금 4K 가 전면 실패한다. `DS-32` 두 줄로 증상은 사라지지만 **왜 그 사이에 들어왔는지는 모른다** — 같은 경로로 다음 회귀가 또 들어올 수 있다.
9. **`app/core/` 36파일 중 24개가 여전히 미감사다.** CORE-01~12 는 12개만 다뤘고, 그 뒤 `people.py`·`versioning.py`·`worker_lock.py` 가 **2026-08-08 에 수정됐다** — 즉 감사 이후에 바뀐 코드가 있고 **최신 상태는 정의상 미감사**다.
10. **`ADM-01` 의 CLI 13회 잠금 해제가 누가 한 것인지 감사 로그에 없다**(신규, ✅ 코드 확인): `app/cli/user_cli.py` 가 `record_audit(..., actor_id=None, ...)` 로 기록한다(:140·:149·:192·:203 등). 관리자 수명주기의 다수가 CLI 를 지나므로 **감사 추적성에 구멍이 있다.** 심각도는 미판정.