## A-4. 다음 조사 후보 (우선순위 순)

1. **L축 남은 2표면** — `list-screens` · `key-workflows`. 스크린샷·계측은 있다
   (`/my-tickets` 카드 0·버튼 1 / `/team-docs` 카드 21 / `/board` / `/offboarding` /
   `/scheduler-calendar`). DESIGN 현재 **16/18**
2. **Coverage 문서 재생성** — `coverage_state.json` 이 아직 직전 Cycle 값이다. 이번 Cycle 관측
   (28표면 렌더 · 63 RBAC 조합 · 9 상세 라우트 · 12 탭 조합 · API 원문 · 서버 로그)을 반영하고
   `l_axis_design_verdict_complete` 를 DESIGN 판정 블록 수와 **정확히** 맞춘다
3. `PRODUCT_AUDIT_REPORT.md` · `INVENTORY` · `FEATURE_CONTRACTS` 를 이번 Cycle 기준으로 갱신
4. `BACKLOG.md` · `QA_COVERAGE.md` 에 9건 반영(중복 대조 후) + `IMPLEMENTATION_REQUIRED`
5. P·R축(문구·한국어) — `ux-writing` → `humanize-korean` 순서
6. N·O축 — 1366/390 뷰포트, 125/150/175% 배율, 다크
7. W축(시간대·만료) · S축(성능) · T축(관측성)
8. **Blind Re-Audit 2회 연속** — 이전 Cycle의 진입점(퇴사 처리·장애 대응·신규 입사자 첫날·
   감사자 분기 점검)을 재사용하지 않는다

# PRODUCT AUDIT — STATE

> **이 Audit의 resume pointer다.** 새 invocation은 이 문서를 먼저 읽는다.
> cycle_id=PA-20260817-072224-24b91505 · baseline=`2aacd2a2ab4a50e92d3dee8f3aba3a248e175e83`
> baseline_branch=`ui/mui-migration`
>
> 아래 §A가 **현재 Cycle**이다. §B부터는 이전 Cycle들의 기록이며 **증거로 보존**한다 —
> 그 Cycle의 완료 marker와 Blind Re-Audit PASS는 이 Cycle의 완료 근거가 되지 못한다(CLAUDE.md §11-1).

---

# §A. 현재 Cycle — PA-20260817-072224-24b91505

## A-0. 이 Cycle이 존재하는 이유, 그리고 왜 이전 Cycle을 복사하면 안 되는가

사용자가 `2aacd2a`("PROJECT_COMPLETE assessment")에서 `-ResetAudit`을 눌렀다. 직전 Cycle
(`PA-20260816-120655`)은 Root Cause 15건(`PA-RC-0012`~`0026`)을 넘겼고 **구현 Phase가 그것을
전부 닫았다** — `IMPLEMENTATION_CONSUMED`(격리됨)가 `visual_change_rcs=8 / visually_verified_rcs=8`
로 기록하고 있고, `docs/BACKLOG.md`는 278행 전부 ✅다(미해결 0행).

그래서 이 Cycle의 출발 조건은 이전 Cycle들과 질적으로 다르다.

- **알려진 문제가 0건이다.** Backlog에 남은 것이 없으니 "미해결 목록을 판다"는 전략이 통하지 않는다.
  이 Cycle이 찾아야 하는 것은 정의상 **아직 아무도 적지 않은 것**이다.
- **직전 Cycle의 L축 판정은 전부 무효다.** `REBUILD` 1 · `REDESIGN` 10 건이 실제로 구현됐다.
  대시보드 카드 40장은 지금 **11장**이고, 관리자 IA는 `/system`·`/llm-console`·`/notion-console`·
  `/maintenance` 네 라우트가 `/settings?tab=*` 리다이렉트로 접혔다. 옛 판정을 복사하면
  **없어진 화면을 감사한 것이 된다.**

## A-1. 이 Cycle이 먼저 확정한 것 — 관측 대상

이전 Cycle들은 `http://localhost:8099`의 로컬 인스턴스를 봤다. 그 프로세스는 **지금도 살아
있지만 2026-08-12 13:28에 뜬 것**이고, 제품 코드는 그 뒤 `2026-08-17 06:49`(`d5ba3f9`)까지
바뀌었다. 즉 그 인스턴스의 파이썬은 **닷새 낡았다** — 거기서 관측한 동작은 지금 존재하지 않는
코드의 동작이다. 프런트 번들만 디스크에서 읽히므로 최신이라 **겉보기로는 구분되지 않는다.**

그래서 이 Cycle은 **TEST SERVER(`10.100.64.71`)를 관측 대상으로 삼는다.** 그것이 HEAD라는 것을
추정이 아니라 실측으로 확정했다:

| 확인 | 방법 | 결과 |
|---|---|---|
| 백엔드 == HEAD | `app/**/*.py` **314개** 전부 파일별 sha256 대조 | **314/314 일치** |
| 프런트 번들 == HEAD | `BUILD_STAMP.json` `source_hash` | `3c20d624…` 일치 |
| 서비스가 그 코드로 떠 있음 | `ActiveEnterTimestamp` | `06:51:13` — 마지막 제품 커밋(`06:49:09`) 이후 |

### 이 대조에서 내가 처음 낸 답은 틀렸다 (방법론 기록)

첫 비교는 **29개 파일이 다르다**고 나왔다. `app/core/authz.py`를 열어 보니 235줄이 전부
다르다고 표시됐는데, 바이트 차가 정확히 **235바이트 = 줄 수**였다 — CRLF다. 배포본 일부가
Windows 체크아웃에서 왔을 뿐 내용은 같았다. `tr -d '
'` 정규화 후 다시 재니 **차이 0**.

기록해 두는 이유: "배포본이 HEAD가 아니다"는 이 Audit이 낼 수 있는 가장 무거운 결론 중 하나이고,
그것을 **줄 단위 diff 하나 안 보고 파일 개수만으로** 낼 뻔했다. 프로브의 첫 결과는 표본을
직접 열어 보기 전까지 신뢰하지 않는다.

## A-2. 이 Cycle이 지금까지 실행한 것

| Round | 축 | 한 일 | 산출 |
|---|---|---|---|
| 0 | 재접지 | CLAUDE.md·SSOT 7종·BACKLOG 3407행 집계·quarantine 사유·git 교차 대조 | Backlog 미해결 **0**행 확인 |
| 1 | 환경 | 배포본 == HEAD 실측, 관측 하니스 구축(`pa2_env.py`) | TEST SERVER 브라우저 로그인 성립 |
| 2 | L (계측) | 관리자 16 + 사용자 12 = **28 표면** 실렌더 + 레이아웃 계측 + 전체 스크린샷 | `pa2_design_*.json`, `shots2/` |
| 3 | L (육안) | 스크린샷을 `Read`로 열어 판정 | 대시보드·진단·사용자·홈 |
| 4 | L·E (검증) | 대시보드/진단 중복을 **문자열 단위로 계측** | `pa2_dup.py` — 68% 중복 확정 |
| 5 | B·E (검증) | `/api/home/today` 원문 확인 → 문서 계약과 대조 | `PA-F-002` Confirmed |

## A-3. 지금까지 확정한 Root Cause — 9건 (전부 Confirmed)

| RC | Sev | 요지 |
|---|---|---|
| `PA-RC-0032` | **High** | **필수 관문이 500을 낸다.** `POST /change-password` 가 SQLite 잠금에서 raw 500(오늘 31건 중 3건). `app/chat/` 전체도 공용 재시도 관용을 안 쓴다(`is_write_conflict` 0회). 같은 파일의 `login()` 이 기준 구현을 갖고 있는데 쓰기를 더 많이 하는 `change_password()` 에만 없다 |
| `PA-RC-0027` | **High** | `/me`·`/my-stats` 개수 타일이 *"모른다"* 를 `0`으로 그린다. 문서와 코드 주석 두 곳이 그 불변식을 명시하는데 호출부 2곳에 가드가 없다. 23명 중 **10명**이 이 경로. **기존 테스트가 이 결함을 고정**하고 있다 |
| `PA-RC-0031` | Medium | 관리자 `감사` 그룹 6개 중 3개가 감사가 아니다. 같은 명사·같은 종류 화면·한 업무가 그룹으로 쪼개진다. 용어 병기 관례가 34항목 중 3개에만 |
| `PA-RC-0028` | Medium | `/dashboard`·`/diagnostics` 본문 **68%** 중복. `build_diagnostic_bundle` 이 `build_dashboard()` 를 통째로 품는 구조 |
| `PA-RC-0030` | Medium | `/settings` 탭 게이트에서 **주소와 화면이 갈라진다**(12조합 실측). 거부 안내 없음. `system_admin` 2명을 뺀 전원이 이 경로 |
| `PA-RC-0033` | Medium | 관리자 상세 3종이 없는 레코드에 **침묵**한다(목록만 그린다). 사용자 콘솔 5종은 옳게 답한다 |
| `PA-RC-0034` | Medium | 전역 QueryClient 에 `retry` 가 없어 확정적 4xx 를 **4회** 호출한다. `/board/<없는 id>` 가 30초 걸려 답한다. `useQuery` 80곳 중 20곳이 이 기본값 상속, 60곳은 각자 덮어씀 |
| `PA-RC-0029` | Medium | `/users` 이메일 열이 **20/20행** 잘린다(131px, 필요 198px). `역할` 은 295px |
| `PA-RC-0035` | Low | `/new-ticket` 담당자가 체크박스 14개 평면 나열. `FormHelperText` 0회 — 안내가 placeholder 에만 있어 입력 시 사라진다 |

## A-4-B. 이 Cycle의 계측 규칙 (오류 두 번을 겪고 세운 것)

이번 Cycle에서 프로브가 **두 번** 거짓 결론을 냈다. 둘 다 「세어 보니 다르다」에서 멈추고
「무엇이 다른가」를 안 본 것이다.

| # | 첫 결론 | 진실 | 원인 |
|---|---|---|---|
| 1 | 배포본이 HEAD와 **29개 파일** 다르다 | 0개 다르다 | CRLF (바이트 차 = 줄 수) |
| 2 | RBAC 구멍 **27건** | 0건 | 어시스턴트 모달 드로어(1920×1080, x=0)를 사이드바로 오인 |

**규칙: 0건/전건 같은 극단값이 나오면 그것부터 의심하고, 표본 하나를 직접 열어 본 뒤에만
기록한다.** `pa2_rbac.py`에는 사이드바를 못 찾으면 `null`을 반환해 실행을 중단시키는 가드를
넣었다 — 「찾지 못했다」가 「비어 있다」로 조용히 번역되는 것이 그 오류의 본질이었다.

## A-5. 현재 blocker

**없다.** `AUDIT_BLOCKED` 사유에 해당하는 항목이 없다.


# §B-0. 이전 Cycle 기록 — PA-20260816-120655-f103fb5b (baseline `70e264b`)

## A-0. 이 Cycle이 존재하는 이유

직전 Cycle(`PA-20260816-100149-48671b72`)이 끝나기 전에 사용자가 **D-75를 커밋하고
`-ResetAudit`을 눌렀다**(`70e264b` — "UI/UX를 '다듬기'에서 '다시 설계'로 — Deep Design Audit Gate").
즉 이 Cycle의 목적은 명확하다 — **이전 Cycle들이 하지 않은 L축 Deep Design Audit을 실제로 하는 것.**

D-75가 바꾼 것: L축에 `OBSERVED`/`EXECUTED`를 쓸 수 없다. HTTP 4xx/5xx · console error ·
overflow · heading · landmark · 접근성 자동검사 · Light/Dark 동작 확인은 **전부 QA이지 Deep
Design Audit이 아니다.** 그리고 완료 Gate가 필수 18표면의 KEEP/REFINE/REDESIGN/REBUILD 판정을
기계적으로 요구한다.

**제품 코드는 `64ef571` 이후 바뀌지 않았다** — 그 사이 커밋은 전부 `docs/`와 `scripts/runner/`다.
따라서 직전 Cycle의 기능 계열 관측(`PA-F-042`~`057`)은 현재 HEAD에서도 유효하며, 이 Cycle은
그것을 다시 재지 않고 **L축에 자원을 집중했다.** 승계한 미해결 RC 4건(`PA-RC-0012`~`0015`)은
Handoff에 그대로 남아 있다.

## A-1. 이 Cycle이 실제로 실행한 것

| Round | 축 | 결과 |
|---|---|---|
| 0 | 재접지 | SSOT 7종 + git + marker + quarantine 사유 교차 대조. `PRODUCT_AUDIT_DESIGN.md`가 **없다**는 것이 이 Cycle의 첫 사실 |
| 1 | L (계측) | 관리자 16 + 사용자 10 = **26 표면 실렌더**, 레이아웃·타입 스케일·색 표면·CTA 수 계측. `design_capture.py` |
| 2 | L (육안) | 스크린샷을 **`Read`로 열어서 판정**. 대시보드·사용자 목록·홈·채팅·설정·빈 상태·다크 |
| 3 | L·N (셸) | 배너 높이·본문 시작 위치·중복 지표를 23라우트에서 계측. `probe_shell.py` |
| 4 | L (검증) | 내비 도달 가능성을 **클릭으로** 판정 → 내 가설 철회. `verify_nav.py` |
| 5 | L·M (검증) | FAB 겹침을 `elementFromPoint` 히트테스트로 판정 → **진짜** 확정. `verify_fab.py` |
| 6 | O (다크) | 토글 후 실측 + 대비 계산. 프로브를 두 번 고쳐야 했다. `verify_dark.py` |
| 7 | L·H·N | 상세·모달·빈/오류/로딩 상태 + 6개 뷰포트/배율. `design_capture2.py` |
| 8 | 산출 | `PRODUCT_AUDIT_DESIGN.md` 신설(18표면 판정) → Handoff `PA-RC-0016`~`0024` 9건 |

## A-2. 이 Cycle의 산출물

| 항목 | 값 |
|---|---|
| 신규 문서 | **`PRODUCT_AUDIT_DESIGN.md`** — 필수 18표면 전부 판정. `REBUILD` 1 · `REDESIGN` 10 · `REFINE` 6 · `KEEP` 1 |
| 신규 Finding | `PA-F-058` ~ `PA-F-080` (음성 결과 8 + 방법론 정정 3 + Blind pass 2 포함) |
| 신규 Root Cause | `PA-RC-0016`(셸 배너 비용) · `0017`(관리자 IA 밀도) · `0018`(대시보드 카드 벽) · `0019`(FAB 가림) · `0020`(어시스턴트 명명·진입점) · `0021`(다크 토큰) · `0022`(산문이 IA를 대신함) · `0023`(동작 위계) · `0024`(상세 기제 분열) |
| HANDOFF 블록 | **15건**(신규 11 + 승계 4). 전부 27 기본 필드 + UI 15 필드 자기검사 PASS. `deferred_for_human_approval=0`, 미루는 표현 0건 |
| Coverage | 2340칸 · UNSEEN 1292(전부 사유) · EXECUTED **366**(190→) · OBSERVED 195 · STATIC 486 · N/A 16 · **L축 판정완료 37 / 시각관측 37** |
| 적용 Skill | 핵심 다섯 **전부 실제 적용** — `ui-ux-pro-max`·`redesign-existing-projects`·`impeccable`(L축) · `ux-writing`(P축) · `humanize-korean`(R축, 탐지 분류 체계만 — 이유는 `PA-F-079`). **skill_gap 없음** |
| Blind Re-Audit | **2 / 2 연속 clean** — pass 1(퇴사 처리)·pass 2(장애 대응) 둘 다 새 Critical/High 범주 **0** |

### 이 Cycle이 찾은 것은 화면 결함 목록이 아니라 **전역 원인 넷**이다

1. **구조가 할 일을 다른 것에 떠넘긴다**(`0016`·`0017`·`0022`) — 배너는 우선순위 판단을
   사용자에게, 8그룹 평면은 분류를 사용자에게, 안내 4문단은 화면 경계 설명을 문구에 떠넘긴다.
   **따로 고치면 서로를 되살린다** — 배너만 접고 IA를 두면 안내문이 여전히 필요하다.
2. **위계가 없다**(`0018`·`0023`) — 정보 위계(카드 40장이 전부 같은 무게)와 동작 위계
   (한쪽은 primary 0개, 다른 쪽은 3개에 「삭제」까지 primary)의 두 축.
3. **어시스턴트 표면이 정리되지 않았다**(`0019`·`0020`) — 이름 4종·진입점 3개이고 그중 하나가
   본문 버튼을 덮는다. 진입점을 하나로 모으면 가림도 함께 닫힌다.
4. **같은 개념이 콘솔별로 다른 것이다**(`0024`) — 상세 보기가 사용자는 라우트, 관리자는 모달.

## A-2-B. Blind Re-Audit 기록

```
blind_pass=1 cycle_id=PA-20260816-120655-f103fb5b new_critical_high_categories=0 at=2026-08-16T13:31:46+09:00
```

**pass 1 진입점**: 「오늘 퇴사자 처리를 끝내야 하는 관리자」 — 오프보딩 업무를 처음부터 끝까지
걸었다. 이전 Cycle이 쓴 진입점(「신규 입사자 첫날」·「감사자 분기 점검」)은 재사용하지 않았다.
기존 Finding 목록을 대조하지 않고 화면이 보여 주는 것만 봤다.

결과는 `PA-F-077`이다 — **새 Critical/High 범주 0**, 새 Medium 1건(`preview` API가 아는
「Notion 미연결이면 재배정 불가」를 목록 화면이 말하지 않는다)은 `PA-RC-0022`·`PA-RC-0023`에 병합.
나머지는 기존 RC 재확인이었고, 잘 만든 것 3건(되돌리기 실재+이력, 잘림 고지, preview 계약)을
`PA-F-068`에 추가했다.

```
blind_pass=2 cycle_id=PA-20260816-120655-f103fb5b new_critical_high_categories=0 at=2026-08-16T13:38:50+09:00
```

**pass 2 진입점**: 「인수하고 첫 장애를 맡은 운영자」 — `operator` 역할로 로그인해 증상에서
원인까지 끌고 갈 수 있는지 봤다. 이 인스턴스가 실제로 고장나 있어(동기화 12일 정지·러너 비활성·
잡 3건 영구 실패) 연출이 아니다. 읽기만 했다.

결과는 `PA-F-078`이다 — **새 Critical/High 범주 0**. 운영자는 배너 → 대시보드 → 작업 큐 →
러너 → 잡 상세로 **원인에 실제로 도달한다**(T축이 강하다). 새 Medium 1건은 `PA-RC-0026`으로
분리했다 — 「진단」 화면이 조회 행위인데 설정 변경 권한으로 막혀 있어, 헬스체크를 담당하는
역할만 그 화면을 못 연다. 잘 만든 것 3건을 `PA-F-068`에 추가했다.

**Gate F 충족**: 서로 다른 진입점·역할·축으로 2회 연속, 두 pass 모두 새 Critical/High 범주 0.

## A-3. 이 Cycle에서 내가 저지르고 정정한 측정 오류 3건

| # | 잘못 세운 결론 | 실제 원인 | 어떻게 잡았나 |
|---|---|---|---|
| 1 | 관리자 사이드바 하단 21항목 **도달 불가**(Critical급) | 탐지기가 `querySelectorAll('*')`로 찾아 **자기 자신을 제외** → `<nav>`의 `overflow-y:auto`를 놓쳤다 | 조상 스크롤 체인 전수 출력 |
| 2 | AI 카드가 **내비 항목을 가린다** | 고정(fixed) 요소 좌표에 `scrollY`를 더해 문서 좌표와 섞었다 | 뷰포트 좌표로 재계산 |
| 3 | 다크 헤더 텍스트 **대비 실패 7건** | 배경이 `linear-gradient`인데 조상 훑기가 body의 밝은 색을 잡았다 | 그라디언트를 만나면 판정 포기 후 따로 집계 |

| 4 | `operator`의 권한 거부 화면에 **문구가 아예 없다**(P축 최대 결함이 될 뻔했다) | 진입 후 **1400ms**에 쟀다. 2500ms로 늘리니 정상적인 47자 거부 화면이 있었다 | settle 시간을 늘려 재측정 + 스크린샷 |

> **1~3은 "내가 잰 것이 내가 재려던 것인가"** 다 — 선택자 범위 · 좌표계 · 배경 모델.
> **4는 "내가 잰 *때*가 맞는가"** 이고, 이것은 직전 Cycle이 `PA-F-052`에 *"비동기 화면은 단일
> 스냅샷이 아니라 시계열로 판정하라"* 고 **이미 적어 둔 교훈을 또 밟은 것**이다.
> **"없다"는 결론은 시간이 부족했을 때도 똑같이 나온다** — 부재를 확정하기 전에 반드시 더 기다려라.
> 이 저장소가 이전 Cycle에 배운 교훈(*집계를 세기 전에 표본을 열어라*)의 계측 버전이다.
> **같은 계열로 보이던 `PA-F-061`(FAB이 본문 버튼을 가림)은 히트테스트로 재서 진짜였다.**
> 오탐 경계는 "AI가 뭔가를 가린다"는 주제가 아니라 **측정 방법**에 있었다.

## A-3-B. 이 Cycle은 완료됐다 — `AUDIT_COMPLETE`

> **첫 시도는 거부됐다(2026-08-16 13:49).** 사유: `HANDOFF-SUMMARY`의 `redesign_root_causes=9`가
> DESIGN 판정에서 파생되는 8과 달랐다. **Supervisor가 맞았다** — `PA-RC-0021`(다크 테마 토큰)은
> 신규 L축 RC지만 `REFINE` 판정(`global-header`)만 참조하고, 의미로도 색 토큰 수정이지 재설계가
> 아니다. 한 건만 고치지 않고 `var/product-audit/derive_counts.py`를 만들어 **파생 가능한 수
> 7종을 전부 대조**하게 했다(`PA-F-080`). 완료 시도 전에 이 스크립트를 돌린다.

완료 Gate 8종을 전부 기계 검증했다. **핵심은 Gate F다** — 서로 다른 업무·역할·축으로 blind
pass를 2회 연속 수행했고 둘 다 새 Critical/High Root Cause 범주가 **0**이었다.

| Gate | 결과 |
|---|---|
| A Inventory | Surface 90종, `unseen_without_reason=0`, 산술 2340 == 2340 |
| B Intent | Feature Contract 9종, intent evidence·confidence·UNKNOWN 정직 기록 |
| C Axis | A~Z 26축 전부 Coverage 반영 |
| D Evidence | 정적 추정과 실행 증거 분리, Confirmed/Strong에 재현·trace |
| E Skill | 핵심 다섯 전부 실제 적용, `skill_gap` 없음 |
| **F Blind Re-Audit** | **2/2 연속 clean** (퇴사 처리 · 장애 대응) |
| G Handoff | RC 15건 == summary, BACKLOG 15/15 승격, 미루는 표현 0, marker 정합 |
| H Deep UI/UX | 필수 18표면 판정 완료, Target Design 필드 일습, `l_axis_design_verdict_complete`=18 |

**남은 조사 후보(§A-4)는 완료를 막지 않는다.** 그것들은 Medium 이하이거나(S축·breadcrumb),
역할 밖이거나(러너 활성화 — CLAUDE.md §3-9), 격리 fixture가 필요한 것(승인/반려·업로드)이다.
검증 한계는 `PRODUCT_AUDIT_REPORT.md` §A-5에 전부 적었다. **다음 Cycle의 입력이지 이 Cycle의
미완이 아니다.**

## A-4. 다음 조사 후보 (우선순위 순)

1. ~~**P축 정면 — 「없어서 문제인 문구」.**~~ ✅ **닫았다**(`PA-F-070`·`071`·`073`) — 성공 확인·
   파괴적 확인·진행 표시·대량 피드백·권한 거부 문구가 **대체로 존재한다**. 결함은 둘: 일반
   사용자에게 권한 거부 문구가 없고(`PA-RC-0024`에 병합), 공유 `DataScreen`이 성공 문구를
   조립해 규칙을 어긴다(`PA-RC-0025` 신규). **남은 것**: 빈 상태의 "다음 행동" 부재는
   `PA-RC-0018`이 다루고, 토스트 **실패** 문구는 이전 Cycle이 이미 100% 회복 절을 확인했다.
2. ~~**Q축 확장.**~~ ✅ **닫았다**(`PA-F-075`) — 목적지 11종 중 **9종이 라벨↔제목 정확히 일치**하고
   괄호 병기 3종(「자동화 작업 실행기(러너)」 등)도 괄호까지 반복된다. 흔들리는 것은 어시스턴트와
   `/org-tree` **둘뿐**이라 `PA-RC-0020`의 범위를 그 둘로 좁혔다. **남은 것**: breadcrumb 구조
   (내 선택자가 틀려 이번엔 판정 보류 — 올바른 선택자로 재측정), 상태값/배지 어휘의 일관성.
3. **R축 — `humanize-korean`.** P축을 닫았으므로 순서상 **이제 열렸다**. 다만 직전 Cycle이
   `PA-F-039`에서 *"R축은 깨끗하다"* 고 판정했으므로 처음부터 다시 훑지 말고 **이번 Cycle이 새로
   관측한 문구**(성공 토스트·권한 거부·확인 다이얼로그·빈 상태)에만 적용할 것. → **다음 순번**이다.
4. ~~**C축 쓰기 조작.**~~ ✅ **대부분 닫았다**(`PA-F-070`) — 폐기용 부서로 생성·수정·삭제를 실제로
   실행해 DB 반영까지 확인했고 대량 선택 UI도 봤다. **남은 것**: 대량 동작의 **실행**(선택까지만
   했다), 승인/반려 워크플로, 파일 업로드/다운로드.
5. **C축 잔여 — 대량 동작 '실행'.** 이번에 선택 UI와 액션 바까지는 봤지만(`PA-F-070`) 실제로
   누르지는 않았다. QA 계정에 **멱등한 동작**(이미 활성인 계정에 「활성화」)을 걸어 전체 경로를
   닫을 것. 승인/반려 워크플로와 파일 업로드/다운로드도 미측정이다.
6. **G·K축 성공 경로.** 실패 전파는 닫혔다(`PA-F-057`). 러너가 `enabled=0`이라 **정상 경로를
   본 적이 없다.** 러너를 띄우거나 격리 fixture로 재현할 것.
6-b. ~~**「업무 도우미」 동일성 확인.**~~ ✅ **닫았다** — 표시명이 아니라 `CHAT_WORKFLOW_NAME`
   **DB 조회 키**다(`chat_message.py:39,60`). 바꾸면 채팅이 멈춘다. `PA-RC-0020`의 `constraints`에
   빨간 금지 항목으로 박았다.
7. **S축** — `/board/:id`·`/team-docs/:id`의 not-found 판정이 5~10초. 환경 요인(Notion 동기화
   정지)과 코드 요인을 아직 분리하지 못했다.
8. **Blind Re-Audit 2회 — 아직 0/2. 이제 이것이 완료 Gate의 최대 잔여물이다.**
   L·P·Q·C(기본)·F가 닫혔으므로 착수 조건은 갖춰졌다. **fresh context에서 시작하라** — Blind pass는
   기존 Finding을 다시 읽는 것이 아니라 처음 보는 Auditor처럼 도는 것이고, 이번 Cycle의 관측으로
   머리가 채워진 상태에서는 성립하기 어렵다.
   이전에 쓴 진입점은 **재사용 금지**("신규 입사자 첫날" · "감사자 분기 점검").
   후보: "인수인계받은 운영자가 장애 대응하는 날", "퇴사 처리를 끝까지 실행한다".

## A-5. 현재 Blocker

**없다.** 로컬 dev 서버(`:8099`) 가동 중, Playwright/Chromium 사용 가능, QA 계정 확보,
승인된 TEST 서버 SSH `ok`. UI/UX Skill 3종 전부 설치되어 실제 사용했다 — `skill_gap` 없음.
`ux-writing`·`humanize-korean`도 설치돼 있으며 미적용은 **순서 때문**이지 부재 때문이 아니다
(재설계 문구가 아직 구현되지 않아 다듬을 대상이 없다).

한계로 기록할 것: `node_modules/`가 Audit 시작 전부터 dirty이며 사용자의 것이라 건드리지 않았다.

## A-6. 실행 방법 메모

```
.venv/Scripts/python var/product-audit/design_capture.py admin   # 레이아웃·CTA·타입 스케일 + 스크린샷
.venv/Scripts/python var/product-audit/design_capture.py user
.venv/Scripts/python var/product-audit/design_capture2.py        # 상세·모달·빈/오류/로딩 + 6뷰포트
.venv/Scripts/python var/product-audit/probe_shell.py            # 배너 높이·본문 시작·중복 지표
.venv/Scripts/python var/product-audit/verify_nav.py             # 내비 스크롤 체인 + 클릭 도달
.venv/Scripts/python var/product-audit/verify_fab.py             # FAB elementFromPoint 히트테스트
.venv/Scripts/python var/product-audit/verify_dark.py            # 테마 토글 후 대비
.venv/Scripts/python var/product-audit/gen_coverage.py           # COVERAGE 재생성(요약 자동 일치)
```

스크린샷은 `var/product-audit/shots/`에 있다. **생성만 하고 넘어가지 말 것** — `Read` 도구로
실제로 열어서 판정하는 것이 이 축의 전제다. 전부 로컬 `:8099`를 쓰고 QA 계정 비밀번호는 매
실행 새로 만들어 **stdin으로만** 넣는다(기록 안 함).

---

# §B. 이전 Cycle 기록 — PA-20260816-100149-48671b72 (baseline `64ef571`)

## A-0. 이 Cycle의 성격

이전 Cycle 이후 **272 커밋**이 쌓였고, 그 Handoff 3건(`PA-RC-0001`·`0002`·`0003`)은
`IMPLEMENTATION_CONSUMED`로 닫힌 상태로 넘어왔다. `-ResetAudit`으로 새 Cycle이 열렸다.

이 Cycle의 무게중심은 **이전 Cycle이 스스로 밝힌 한계**다:
*"UNSEEN이 57%이고 브라우저로 실제 본 화면은 12/90 표면이다."*
즉 이전 Cycle의 수렴 근거는 Coverage가 아니라 Gate F였다. **그래서 이번엔 관측 폭부터 넓혔고,
넓히는 과정에서 이전 프로브의 방법 결함을 찾았다**(A-2).

## A-1. 이번 Cycle이 실제로 실행한 것

| Round | 축 | 결과 |
|---|---|---|
| 0 | 재접지 | 이전 Cycle 3개 RC를 **현재 HEAD에서 재측정** → 전부 닫힘 확인(기록을 믿지 않고 직접 실행) |
| 1 | C·L·M (전 라우트) | **60 라우트 실주행**(user 19 + admin 41, 이전 11개). `sweep_all.py` |
| 2 | M (접근성 구조) | 59 라우트 heading outline·label·landmark·tabindex·focus ring 계측. `probe_a11y.py` |
| 3 | 표본 검증 | 플래그된 요소의 **DOM 원본 확인** → 대형 오탐 1건 폐기. `verify_a11y.py`·`verify_select.py` |
| 4 | F (RBAC 행동) | 프런트 게이트 없는 화면 10개 × 역할 2개 실제 접근 + 대조군 3개. `probe_rbac_gate.py` |
| 5 | C·H·I (실조작) | **이 Cycle에서 처음으로 제품을 눌렀다** — 페이지네이션·검색·새로고침 복원을 5화면 대조, 생성 폼 빈 제출. `probe_interact.py`·`probe_deeplink.py`·`probe_deeplink2.py` |
| 6 | H·I (상세 라우트) | **두 Cycle 모두 미관측이던 `:id` 표면 6개**를 없는 ID로 진입 — 전부 정상 처리. `probe_badid.py`·`probe_badid2.py`·`verify_badid.py` |
| 7 | F (쓰기 게이트) | `operator`에게 쓰기 버튼이 보이는지 10화면 실측 — **전부 안 보인다**. 403 막다른 길 없음. `probe_write_gate.py` |
| 8 | H·E·P (입력 경계) | `/users`에 이름 500자 실제 제출 — 서버는 422로 정확히 거절하나 **영문 Pydantic 문구가 그대로 노출**. `probe_limits.py` → `PA-RC-0014` |
| 9 | U·H (이스케이프·중복·빈값) | 검색창에 XSS 페이로드 3종 — **주입 0·실행 0**. 중복은 409+한국어, 빈 필수값은 네이티브 검증이 차단. `probe_xss_dup.py`·`verify_empty.py` |
| 10 | G·P (장애 상태 문구) | dev 인스턴스가 **실제로 12일째 동기화 정지** — 자연 실험으로 관측. 배너가 "17976분"을 8/8 화면에 띄운다. `verify_banner.py` → `PA-RC-0015` |
| 11 | G·K·I (실패 전파) | 영구 실패한 잡 3건을 `jobs → messages → 화면 문구`로 추적 — **전파가 정확하다**. 이 Cycle이 본 가장 잘 만든 실패 경로 |

## A-2. 이번 Cycle이 고친 **이전 Cycle의 관측 방법 결함** (가장 중요)

`probe_spa.py`는 Playwright의 `requestfailed`만 들었다. 그것은 **전송 계층 실패**만 발화하고
**HTTP 500은 전송이 성공한 교환**이라 발화하지 않는다. 즉 화면의 API가 전부 500을 뱉어도
*"실패 요청 (없음)"* 으로 보고된다. `sweep_all.py`는 `response` 이벤트에서 `status >= 400`을
**라우트별로 귀속**해 기록한다. 이전 Cycle의 "네트워크 깨끗함"은 이번 측정으로 **대체**한다.

## A-3. 현재 산출물

| 항목 | 값 |
|---|---|
| 신규 Finding | `PA-F-042` ~ `PA-F-057` |
| 신규 Root Cause | **`PA-RC-0012`**(Med) 제목 계층이 시각 API에 종속 · **`PA-RC-0013`**(Med) `/users`만 목록 상태를 URL에 안 싣는다 · **`PA-RC-0014`**(Med) 스키마 422가 영문으로 나오고 필드에 연결되지 않는다 · **`PA-RC-0015`**(Low) 장애 배너 경과 시간이 항상 '분'이라 12일이 "17976분"으로 나온다 |
| HANDOFF 블록 | **4건** (전부 27필드 자기검사 PASS, 미루는 표현 0건). `deferred_for_human_approval=0` |
| Coverage | 2340칸 · EXECUTED **190**(158→) · OBSERVED **222**(62→) · STATIC_ONLY **604**(784→) · UNSEEN **1324**(전부 사유 있음) |
| 적용 Skill | `ui-ux-pro-max`(L·M축) · `ux-writing`(P축) **둘 다 실제 호출**. `humanize-korean`은 순서상 보류 — 한국어 문구가 아직 없어 다듬을 대상이 없다 |
| Blind Re-Audit | **0 / 2** — 아직 안 함 |

### 이번 Cycle의 음성 결과 (이것도 산출물이다)

- **60 라우트 전부**: HTTP 4xx/5xx 0 · 콘솔 오류 0 · 실패 요청 0 · h1 정확히 1개 · overflow 0 (`PA-F-042`)
- **프런트 role gate 없는 10화면**: 백엔드와 **일치**한다 — operator/auditor 둘 다 정상 열람,
  대조군 3개는 정확히 거부. IDOR·bypass 아님 (`PA-F-045`)
- **표 접근성**: `th` 전부에 `scope` — WCAG 성공 기준 충족, `<caption>` 부재는 권고 수준 (`PA-F-044`)
- **상시 `aria-modal` 패널**: 닫힌 동안 `visibility:hidden` + 조상 `aria-hidden` — 접근성 트리에
  없다. 본문 노출 정상, 포커스 가능 요소 68~115개 도달 가능 (`PA-F-049`)
- **「사용자 추가」 폼**: 필드 8·필수 표시 2·`aria-modal`·포커스 이동까지 갖춤 (`PA-F-050`)
- **목록 상태 URL 보존**: `/team-docs`·`/board`·`/team-tickets`·`/audit` 네 화면 **정상** —
  `/users` 하나만 예외 (`PA-F-048`)
- **쓰기 버튼 역할 게이트**: 라우트 게이트가 없는 10화면에서도 `operator`에게 쓰기 컨트롤이
  하나도 안 보인다 — 403 막다른 길 없음 (`PA-F-053`)
- **서버 입력 경계**: 500자 제출을 `422`로 거절하고 행을 만들지 않으며 제출값을 응답에
  되돌려주지 않는다 — 데이터 경계와 값 유출 방지는 프런트 가드와 무관하게 성립 (`PA-F-054`)
- **연동 실패 전파(G·K축)**: 12일 전 영구 실패한 `chat_message` 잡 3건이 사용자 대화까지
  정확히 되돌아온다 — 사용자 메시지 `processing_status=failed`, 어시스턴트가 3요소를 갖춘
  한국어 설명 + 「다시 시도」. 재시도가 무의미한 실패(`assistant_rejected`)는 **다른 문구**로
  안내한다. 테스트 5파일이 이 계약을 고정 (`PA-F-057`)
- **XSS 이스케이프**: 검색창 페이로드 3종 × 3화면 — 주입 노드 0·실행 0. 이전 Cycle의 정적
  근거(`innerHTML` 0건)를 **행동으로** 확증 (`PA-F-055`)
- **중복·빈 필수값**: 중복은 `409` + 「이미 등록된 이메일입니다.」(한국어), 빈 값은 네이티브
  검증이 POST 0건으로 차단 (`PA-F-055`)
- **없는 ID 딥링크**: 상세 6화면 전부 정상 — 「찾을 수 없습니다 / 이미 삭제되었거나 이동했을
  수 있습니다」 + 「목록」·「홈으로」로 `PA-RC-0002`의 3요소 기준을 만족. 서버도 404를 준다 (`PA-F-052`)

### 이번 Cycle에 내가 저지른 오류 4건 (전부 정정함)

1. **「라벨 없는 입력 47라우트」— 전부 오탐.** 걸린 것은 MUI `<Select>`의 숨은 프록시 입력
   (`aria-hidden="true"`·`tabIndex=-1`·`opacity:0`)이고 실제 이름은 형제 `div[role=combobox]`가
   갖는다(`verify_select.py`로 확정). 내 `named()`가 `aria-hidden`/`tabindex`를 안 봤다.
2. **「생성 폼에 필드 1개, 제목·버튼 없음」— 오탐.** `querySelector('[role=dialog]')`가 DOM
   순서상 첫 번째, 즉 상시 존재하는 AI 도우미 패널을 잡았다. 제외하고 재니 정상적인 8필드 폼이다.
3. **「공유 셸은 되는데 손으로 쓴 화면은 안 된다」— 쓸 뻔한 틀린 일반화.** `/users` 실패 +
   `/audit` 성공만 보고 `PA-RC-0012`와 같은 모양이라 특히 그럴듯했다. 손으로 쓴 화면 3개를
   더 재니 **셋 다 통과** — 일반화는 틀렸고 `/users`가 단독 예외다. 이 확인이 severity를
   High→Medium으로 낮췄다.

4. **「`/board/:id`가 404를 받고도 「불러오는 중…」에서 영원히 멈춘다」— 오탐.** 2.4초 시점에
   찍은 것이었다. 2s/5s/10s 시계열로 재니 10초 안에 정상적인 not-found 상태로 **해소된다**.
   결함이 아니라 느린 것이었고, 스피너는 화면이 자기 상태를 정직하게 말하고 있던 것이다.

> **넷을 관통하는 것**: 1·2는 *"내가 고른 선택자가 내가 생각한 그 요소인가"*, 3은 *"표본 2개로
> 세운 결론을 전체로 넓혔는가"*, 4는 **시간 축**이다. 1~3은 이전 Cycle이 이미 경계해 둔 실수이고
> 4는 이 Cycle이 새로 배운 것이다. **넷 다 추가 측정으로 잡았다** — 집계를 세기 전에 표본을 열고,
> 일반화하기 전에 대조군을 재고, **비동기 화면은 단일 스냅샷이 아니라 시계열로 판정하라.**

## A-4. 다음 조사 후보 (우선순위 순)

> 진행 상황 표시: ~~취소선~~ = 이번 Cycle에서 완료. 나머지가 실제 남은 일이다.

1. ~~**F축 잔여 — 쓰기 액션.**~~ ✅ **이번에 닫았다**(`PA-F-053`) — `operator`에게 쓰기 버튼이
   10화면 모두에서 보이지 않는다. 남은 미측정은 *"보이는 버튼을 눌렀을 때의 서버 응답"* 뿐이고
   그 경로는 권한이 있는 역할에게만 열려 있다.
2. **C축 — 쓰기 조작.** 읽기 계열(페이지네이션·검색·필터·새로고침 복원)은 이번에 닫았다.
   **아직 안 한 것: 실제 생성/수정/삭제·대량 선택·승인/반려.** 격리된 QA 데이터로 수행할 것.
3. ~~**H축 — 입력 경계.**~~ ✅ **이번에 닫았다** — 없는 ID(`PA-F-052`)·과길이(`PA-F-054`)·
   XSS·중복·빈 필수값(`PA-F-055`)까지 전부 실제 제출로 확인.
4. **Q·R축.** `ux-writing`은 두 번 적용해 `PA-RC-0014`·`PA-RC-0015`를 냈다. **아직 안 한 것:
   Q축(같은 개념이 화면마다 다른 용어인가)과 R축(`humanize-korean`).** P축의 핵심 질문
   (**없어서 문제인 문구**)도 아직 정면으로 다루지 않았다.
5. **G·K축 잔여 — 성공 경로.** 실패 전파는 닫았다(`PA-F-057`). **아직 안 한 것**: 이 인스턴스는
   유일한 러너가 `enabled=0`·health `unknown`이라 **러너가 살아 있을 때의 정상 경로**를 볼 수
   없었다. 실패 잡의 「재시도」도 실제로 누르지 않았다(누르면 러너 호출 + 상태 변경).
   러너를 띄우거나 격리 fixture로 성공 경로를 재현할 것.
6. **S축 — `PA-F-052`가 남긴 관측.** `/board/:id`·`/team-docs/:id`의 not-found 판정이 5~10초.
   Notion 동기화 정지라는 환경 요인과 코드 요인을 **분리하지 못했다.** 분리해서 재측정.
7. **서버 렌더 4화면**(`/login`·`/forgot-password`·`/reset-password`·인계 화면)의 heading/구조 —
   이번 M축 측정은 SPA 전용이었다. `PA-RC-0012`의 범위에 포함할지 판단 필요.
8. **`/users` 정렬 부재**(`PA-F-051`) — 의도 근거를 못 찾아 등급 보류. 요구사항·계약을 더 찾거나
   사용자 수가 늘었을 때 재평가.
9. **Blind Re-Audit 2회** — **아직 0/2.** 위 항목이 어느 정도 닫힌 뒤에 할 것(지금 하면
   미조사 영역이 많아 "연속 clean"이 성립하기 어렵다). 이전 Cycle이 쓴 진입점
   ("신규 입사자 첫날"·"감사자 분기 점검")은 **재사용하지 말 것**.
   예: "인수인계받은 운영자가 장애 대응하는 날", "퇴사 처리를 끝까지 실행한다".

## A-5. 현재 Blocker

**없다.** 로컬 dev 서버(`:8099`) 가동 중, Playwright/Chromium 사용 가능, QA 계정
4역할(user·operator·auditor·system_admin) 전부 확보. 승인된 TEST 서버 SSH도 `ok`다.
`stash@{0}` 자격증명 **회전**만 내 권한 밖 외부 행위이며(REPORT §7-B), 저장소 코드로 닫을 수
있는 부분은 이전 Cycle의 `PA-RC-0003`으로 이미 닫혔다(`check_git_secrets.py` 배선 확인).

## A-6. 실행 방법 메모

```
.venv/Scripts/python var/product-audit/sweep_all.py        # 60라우트 + HTTP 4xx/5xx 귀속
.venv/Scripts/python var/product-audit/probe_a11y.py       # heading/label/landmark/focus
.venv/Scripts/python var/product-audit/verify_a11y.py      # 플래그 요소 DOM 원본 확인
.venv/Scripts/python var/product-audit/probe_rbac_gate.py  # 역할별 화면 접근
.venv/Scripts/python var/product-audit/gen_coverage.py     # COVERAGE 재생성(요약 블록 자동 일치)
.venv/Scripts/python var/product-audit/cov.py set "A-*" "C,L,M" OBSERVED
```
전부 로컬 `:8099`를 쓴다. QA 계정 비밀번호는 매 실행 새로 만들어 **stdin으로만** 넣는다(기록 안 함).

---

# §0~§6. 이전 Cycle 기록 (`PA-20260812-171558-56c5befa`) — 증거로 보존

## 0. 이 Cycle의 성격

이 저장소는 이미 14회차(WF1~WF14)의 구현 중심 작업을 거쳤고, `docs/BACKLOG.md`는 549KB,
`docs/WORK_STATE.md`는 248KB다. 즉 **"흔한 결함"은 대부분 닫혀 있다.** 그러므로 이번 Audit의
가치는 같은 각도로 한 번 더 훑는 데 있지 않고, **기존 Backlog 프로세스가 구조적으로 못 보던
층위**를 파는 데 있다.

이 판단의 근거(Round 0 실측, `PRODUCT_AUDIT_INVENTORY.md` §6):
정적 위생 스캔에서 naive datetime 0건, `innerHTML` 0건, `console.log` 0건, `TODO/FIXME` 0건,
bare `except` 0건, `async def` 라우트 핸들러 0건, 네이티브 `alert/confirm/prompt` 0건.
`httpx` 직접 import는 단일 관문 파일 자신 1건뿐. **음성 결과도 증거다.**

따라서 이번 Cycle의 무게중심은 다음 순서다.

1. **L/M/N/O/P/Q/R** — UI/UX·접근성·반응형·테마·UX Writing·용어·한국어. 프롬프트 6절이
   "현재 UI 보존은 목표가 아니다"라고 명시했고, Backlog 기반 구현은 이 축을 화면 단위
   버그로만 다뤄 왔다(공통 Root Cause로 병합된 적이 적다).
2. **D / E** — 개별 기능은 되는데 업무 흐름이 끊기는 곳, 그리고 같은 정책을 FE/API/BE/DB가
   서로 다르게 표현하는 곳.
3. **X / Z** — dead/stub/orphan, 그리고 549KB Backlog·248KB WORK_STATE의 문서 드리프트.
   (이 저장소는 "이미 고쳐졌는데 행만 안 갱신" 패턴을 WF11~WF14에서 반복해서 발견했다 —
   그 패턴 자체가 아직 수렴하지 않았다는 신호다.)
4. **B** — Feature Contract. 의도의 근거가 코드밖에 없는 기능이 얼마나 되는지 자체가 산출물이다.

## 1. 지금까지 확인한 사실 (Round 0 — Baseline/Inventory)

| 사실 | 근거 |
|---|---|
| API 엔드포인트 312개 / 42 모듈 | `var/product-audit/api_inventory.json` (스캐너: `scan_api.py`) |
| DB 테이블 69개, Alembic revision 57개 | 저장소 스캔 |
| 사용자 라우트 26 · 관리자 명시 라우트 18 · REGISTRY 화면 키 27 | `UserRoutes.jsx` / `AdminRoutes.jsx` / `screens/registry/*.js` |
| 화면 모듈 115개(비테스트) | `frontend/src/screens/**` |
| **MUI 마이그레이션은 화면 층위에서 완료됐다** | 렌더되는 화면 중 MUI/kit 밖에 남은 것 0개. `kit.jsx`(1146줄)는 MUI 위 얇은 래퍼(`@mui` import 31, export 26) |
| 로컬 dev 서버가 살아 있다 (`:8099`) | `GET /healthz` → `{"status":"ok","ticket_source":"notion_cache"}`, `GET /` → 303 → `/login?next=%2F` |
| `openapi.json`은 404 | 운영 하드닝으로 보이나 **의도 근거 미확인** — Feature Contract 후보 |
| CSP 실측 | `connect-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'` — CLAUDE.md §2 서술과 일치 |
| `.venv`는 Python **3.11.9** | CLAUDE.md §2는 "Python 3.12"라고 적는다 → Z축 후보 (경미) |

### Round 0에서 배운 방법론 교훈 (다음 invocation도 지켜라)

- **자작 스캐너의 첫 결과를 그대로 믿지 마라.** 이번에 두 번 걸렸다.
  1. `alert|confirm|prompt` 57건 → 전부 앱의 `useConfirm()` 오탐. 표본 4건을 눈으로 보고 폐기.
  2. `dangerouslySetInnerHTML` 2건 → 둘 다 "쓰지 않는다"는 **주석**.
- **`^\s*` + `re.M` 은 앞의 빈 줄까지 먹어서 인용 줄번호가 조용히 N줄 앞으로 밀린다.**
  실제로 `app/auth/router.py:210`을 208로 인용할 뻔했다. 스캐너는 `^[ \t]*`를 쓴다
  (`var/product-audit/scan_invariants.py` 주석 참조).

## 2. Coverage 현황

`PRODUCT_AUDIT_COVERAGE.md`의 기계 요약 블록이 정본이다. Round 0 종료 시점:
Surface 90개 × 축 26개 = **2340 cell**, A축 90칸 STATIC_ONLY, 나머지 2250칸 UNSEEN
(전부 surface 단위 사유 등록됨 — `unseen_without_reason=0`).

Coverage 문서와 Inventory 문서는 **손으로 고치지 않는다.**
`var/product-audit/{gen_coverage,gen_inventory,cov}.py`로 생성·갱신한다. 이렇게 한 이유는
요약 블록이 표와 어긋나면 Supervisor의 완료 Gate가 거부하는데, 손으로 관리하면 반드시
어긋나기 때문이다.

## 2-1. Round 진행 현황 (2026-08-15 회차에 추가된 것)

| Round | 축 | 결과 |
|---|---|---|
| 재접지 | 저장소 위생 | **`PA-RC-0003` (Critical)** — `stash@{0}` 평문 자격증명 |
| 2 | P (UX Writing) | `ux-writing` Skill 적용 → **`PA-F-011`**, `PA-RC-0002`를 High로 재분류 |
| 3 | Y (회귀 공백) | **프런트 전체 회귀 실행** — 253파일/1,718건 green. Y축 74칸 EXECUTED. 백엔드 `pytest tests/regression`은 이 회차에 완료 못 함 |
| 4 | L·M | `redesign-existing-projects` Skill 적용 → 해당 항목 대부분 통과, **`PA-RC-0004`(Low)** 신규 |
| 5 | W (타임존/스케줄) | **위반 0건** — 시계 주입 186회, 우회 0회, KST는 전부 허용 용도 |
| 5 | T (관측성) | **끊김 없음** — `request_id`가 응답 헤더·액세스 로그·감사 기록을 잇는다 |
| 6 | J (동시성) | **`PA-RC-0008`(High)** — race 테스트가 5회 중 2회 실패, 재시도 예산이 호출부마다 2/5/10/12 |
| 7 | Y (회귀) | **백엔드 2,903건 전부 통과**(청크 분할). `PA-RC-0009`를 High→Medium으로 자기 정정 |
| 8 | V (배포) | **`PA-RC-0007`(Med)** — TEST 서버가 131커밋 뒤처져 최종 Gate 무효 |
| 9 | D (업무 흐름) | 오프보딩·문서생성 **둘 다 닫혀 있다** → FC-07·FC-08 (UNKNOWN 2건 종결) |
| 10 | L/M/N/O (브라우저) | 화면 12개 실측. `PA-RC-0010`·`PA-RC-0011` 신규, `PA-F-028~031`. **중복 기준선 오류 정정**(prefix 41종/552행) |
| 11 | O/N/M (다크·배율·대비) | SPA 다크 **정상**(`PA-F-032`) · **175% 배율에서 `/users` overflow**(`PA-F-033`) · 대비 1~3차 실패(`PA-F-034`·`035`) · 신규 계정 첫 `/me`에 모달 2개(`PA-F-036`, UNKNOWN) |
| 12 | M (대비 4차) | **성공** — 227요소 판정, **미달 1건**(아바타 이니셜 3.41/4.5). 대비는 대체로 건강하다(`PA-F-037`) |
| 13 | L (재설계) | `ui-ux-pro-max`로 **`RD-1`~`RD-6` 확정**. `impeccable` 교차검증이 `RD-5` 진단을 교체 — 대시보드는 섹션 수가 아니라 **수치 20개가 전부 30px/800** 인 것이 문제 |
| 14 | C (기능 조작) | 목록 조작 실측 — 페이지네이션·검색·필터가 **URL 해시에 상태를 싣는다**(딥링크 성립). 정렬·`/audit` select는 선택자 한계로 **판정 보류**(단정 안 함). 마지막 미조사 축 종결 |
| 15 | S (성능/무제한 목록) | 후보 15건 **전부 판정**. 실제 결함 **1건**(`PA-F-040`, Low) — `/usage/stats`가 모든 프롬프트 버전을 전량 적재하고 삭제 경로가 0건이다. 12건은 상수/설정/스키마 상한으로 **오탐**, 1건은 기존 `UB-29` |

## 2-2. 현재 산출물 요약 (resume 시 여기부터 본다)

| 항목 | 값 |
|---|---|
| Root Cause | **11건** — Critical 1(`0003`) · High 3(`0001`,`0002`,`0008`) · Med 4(`0005`,`0007`,`0009`,`0010`) · Low 3(`0004`,`0006`,`0011`) |
| Finding | PA-F-001 ~ **PA-F-040** + 재설계 후보 `RD-1`~`RD-6` |
| HANDOFF의 PA-RC 블록 | **8건** — 필수 27필드 자기검사 PASS. Low 3건은 승격 안 함 |
| Coverage | 2340칸 중 EXECUTED 158 · OBSERVED 62 · STATIC_ONLY **784** · UNSEEN 1336(**전부 사유 있음**, `unseen_without_reason=0`) · **Gate C: A~Z 26축 전부 반영됨** |
| 실행 증거 | **백엔드 2,903건 전부 통과**(4청크) · 프런트 1,718건 통과 · **Chromium 151로 화면 12개 실측** + 다크/배율/대비 probe · race 1건 flaky(`0008`) |
| Blind Re-Audit | **2 / 2 연속 clean** — pass 1(신규 입사자)·pass 2(감사자) 모두 새 Critical/High **0건**. §5에 기록 |
| Backlog 승격 | ✅ **완료(2026-08-15, commit `703f253`)** — 신규 7행 `PA-01`~`PA-07`, 기존 6행 갱신(`SEC-20`·`DS-05`·`DS-18`·`RESP-01`·`RESP-04`·`SEM-02`). `PA-RC-0003`은 `SEC-20`과 같은 자격증명이라 **중복 행 안 만들고 그 행을 확장**했다. `QA_COVERAGE.md` **§13** 신설(새 축 `T1`~`T9`). `DECISIONS.md`는 갱신 안 함(새로 확정된 정책/설계 결정 없음) |
| `IMPLEMENTATION_REQUIRED` | ✅ **생성됨** — `cycle_id`·`created_at`·`baseline_sha`·`handoff`·`root_causes=8`·`audit_commit` |

> **이 회차의 가장 중요한 자기 정정**: `PA-RC-0009`를 처음 High(*"Full Regression green이
> 성립한 적 없다"*)로 썼다가, 스스로 제시한 처방(청크 분할 전경 실행)을 직접 돌려
> **백엔드 2,903건 전부 통과**를 확인하고 Medium으로 낮췄다.
> **다음 회차도 같은 기준을 지켜라** — 처방을 제시했으면 가능한 범위에서 그것을 직접 시험한다.

### AUDIT_COMPLETE까지 남은 일 (순서대로)

1. ~~인증 이후 SPA 화면 관측~~ → **완료(2026-08-15).** 화면 11개 실측, OBSERVED 53칸.
   재실행은 `.venv/Scripts/python var/product-audit/probe_spa.py` 한 줄이다 —
   QA 계정 2개(`audit-qa-user@`·`audit-qa-admin@`)가 dev DB에 이미 있고, 스크립트가 매 실행
   비밀번호를 새로 만들어 **stdin으로만** 넣는다(기록 안 함).
1-A. ~~`ui-ux-pro-max`·`impeccable` 적용~~ → **완료.** 재설계 후보 `RD-1`~`RD-6` 확정
   (`FINDINGS`의 '재설계 후보' 절). `impeccable` 교차검증이 `RD-5`의 진단을 바꿨다 —
   대시보드 문제는 섹션 수가 아니라 **수치 20개가 전부 30px/800으로 동일해 우선순위가 없다**는 것.
   핵심 Skill 5개 중 **4개 적용 완료**, `humanize-korean`만 순서상 보류(아래 2번).
1-B. ~~배율·다크~~ → **완료.** 125/150/175% 배율 측정(**175%에서 `/users` overflow — `PA-F-033`**),
   SPA 다크 정상 확인(`PA-F-032`).
1-C. ~~`CTR` 대비 재측정~~ → **완료(4차에서 성공).** 화면 4개 **227요소 판정, 미달 1건**
   (상단바 아바타 이니셜 3.41/4.5). 대비는 대체로 건강하다. `DS-33`과 같은 계열이라
   새 RC 없이 그 행에 붙였다. 스크립트: `var/product-audit/probe_contrast2.py`.
   **한계**: 후보 356 중 120은 글자 픽셀을 못 잡아 판정 제외 — 전수가 아니다.
1-D. ~~`RESP-03`~~ → **완료.** 768/1024/1280 세 폭에서 31.1×14px로 정상 — **재현 안 됨**
   (`PA-F-038`). 단 선택자 한계가 있어 '해결됨'으로 단정하지 않았다.
1-E. ~~`PA-F-036` 확인~~ → **완료 · 정정됨.** 모달 2개가 아니라 **AI 도우미 패널이 기본 열림**
   (비모달, backdrop 0). 남는 관측은 1920 폭에서 상시 크롬 724px(38%)와
   `role="dialog"`인데 비모달인 불일치(M축).
2. ~~`R`(한국어)~~ → **완료.** `humanize-korean` 탐지 적용 — **S1 고위험 번역투 지표 전부 0**,
   검출 88건은 전수 확인 후 오탐/정상으로 폐기(`PA-F-039`). R축은 깨끗하다.
   ~~`Z`(문서 드리프트)~~ → **완료.** 다른 축을 파는 내내 5건 발견(COVERAGE Z축 절).
   **남은 미조사 축: `C`(기능 CRUD/필터/정렬/페이지네이션) 하나뿐.**
3. ~~S축 잔여~~ → **완료.** 후보 15건 전부 판정(`FINDINGS`의 S축 절 표).
   실제 결함은 **1건뿐**(`PA-F-040`, Low — Handoff 승격 대상 아님). 판정 기준은
   *"`limit`이 있는가"* 가 아니라 **"이 집합이 무엇에 비례해 자라는가"** 였고,
   그 질문 하나가 12건을 걸러냈다.
4. ~~Blind Re-Audit~~ → **완료. Gate F 2/2 연속 clean.**
   pass 1 *"신규 입사자 첫날"*(0건) · pass 2 *"감사자 분기 점검"*(0건).
   pass 2는 `auditor` 역할로 **F축을 행동 검증**했다 — 화면·라우트·API 세 계층이 같은 답을 낸다.
5. ~~§11 Backlog 승격~~ → **완료(commit `703f253`).** 기존 552행 전체와 대조 후
   신규 7행 + 기존 6행 갱신, `QA_COVERAGE.md` §13(새 축 `T1`~`T9`), marker 생성.

**→ AUDIT_COMPLETE Gate 평가 단계에 진입했다.** 남은 것은 최종 문서 commit 과
Supervisor 기계 Gate 통과 확인뿐이다.

### 실행 방법 메모 (다음 회차가 그대로 쓸 것)

- 백엔드 전체 회귀: **전경 + 청크**. `var/product-audit/chunk{1..4}.txt` +
  `tests/{unit,security,regression}` 각각 단독. 단일 호출은 45분+라 세션 경계를 못 넘는다.
- 브라우저: `probe_login2.py`(로그인 화면·다크) / `probe_spa.py`(인증 이후 11화면).
  **로컬 `:8099`를 쓴다** — TEST 서버는 08-10 빌드라 화면 판정에 쓰면 안 된다(`PA-RC-0007`).
  `probe_spa.py`는 QA 계정 비밀번호를 매 실행 새로 만들어 stdin으로만 넣는다(기록 안 함).

## 3. 다음 조사 후보 (우선순위 순)

1. **Round 1 · L축 진입점**: `ui/theme.js`(520줄) + `styles/tokens.css`(366줄) +
   `ui/kit.jsx`(1146줄) + `AppShell.jsx`(693줄)를 2026 Enterprise SaaS 기준으로 평가.
   토큰·밀도·위계·모션이 실제 화면에서 어떻게 소비되는지까지 본다.
2. **Round 1 · L축 대표 화면**: `Dashboard.jsx`(774줄), `MyTickets.jsx`(1049줄),
   `Users.jsx`(981줄), `DataScreen.jsx`(826줄), `Home.jsx`, `ChatPane.jsx`(550줄).
   프롬프트 6절 rubric 12항을 적용하고, 재설계 후보는 "기능/데이터/권한/업무 흐름을
   바꾸는가"를 반드시 명시한다.
3. **Round 2 · P/Q/R축**: 사용자 문구 전수 수집(정규식으로 한글 리터럴 추출) →
   ux-writing 기준 적용 → 용어 일관성 → humanize-korean.
4. **Round 3 · D/E축**: 대표 업무 흐름 4~6개를 `화면→API→BE→DB→관련화면`으로 추적.
5. **Round 4 · X/Z축**: dead route/orphan API, 그리고 BACKLOG/QA_COVERAGE 자기모순 스캔.
6. **Round 5 · F/U/J/W축**: 기존 테스트가 실제로 계약을 검증하는지(Y축과 함께).
7. **Blind Re-Audit 2회** — 다른 진입점(예: "신규 입사자가 첫날 하는 일", "감사자가 분기
   점검에서 하는 일")으로 처음 보는 것처럼.

## 4. 현재 Blocker

**2026-08-15 COLD 재접지에서 이 표를 정정했다.** 이전 판은 "TEST 서버 접근 불가"라고 적었는데,
Supervisor가 이제 `test_server_ssh=ok` 와 승인된 sudo 자격증명 경로(환경변수 →
stdin 전용)를 주고 프롬프트 7절이 관측 권한을 명시한다. **즉 그 Blocker는 해소됐고, 남은 것은
Blocker가 아니라 '아직 안 한 일'이다.** 낡은 Blocker를 그대로 두면 다음 회차가 할 수 있는 일을
안 한다.

| 항목 | 상태 |
|---|---|
| 실제 브라우저 렌더·콘솔·네트워크 관찰 | **해소됨(2026-08-15).** Chromium 151로 **화면 12개 실측 완료** — 로그인(`PA-RC-0010`) + 인증 이후 11개(`PA-F-028~031`). TEST 서버가 아니라 로컬 `:8099`를 쓴다(`PA-RC-0007`). **잔여는 조건**이다: `RESP-03`·125~175% 배율·SPA 다크 모드·`CTR` 대비 |
| 인증이 필요한 화면·API 실호출 | **해소됨.** QA 계정 2개를 dev DB에 추가하고 강제 비밀번호 변경까지 통과해 SPA에 진입했다. 재실행은 `probe_spa.py` |
| 배포·재배포·롤백 실행 | **의도적으로 안 한다.** 자격증명 문제가 아니라 **역할 경계**다 — PHASE 2의 일이다 |
| `PA-RC-0003` 자격증명 회전·`stash drop` | **사람만 가능.** 되돌릴 수 없는 운영 결정이고, drop은 사람이 검토하기 전에 증거를 지우는 일이다 |
| 워킹트리의 사용자 미완성 변경 5개 | 건드리지 않는다(`AppShell.jsx`·`CommandPalette.jsx`·`command-palette.test.jsx`·`lib/recentNav.js`·`lib/recent-nav.test.js`). 이 파일들에 대한 판단은 미완성 변경 위에서 내려진 것일 수 있다 — REPORT §6에 한계로 기록 |

## 5. Blind Re-Audit 기록

blind_pass=1 cycle_id=PA-20260812-171558-56c5befa new_critical_high_categories=0 at=2026-08-15T12:54:24+09:00

### pass 1 — 진입점: **"신규 입사자가 첫날 하는 일"**

기존 Finding 목록을 보지 않고, **데이터가 하나도 없는 `user` 역할 계정**으로 첫 로그인부터
11개 화면을 순서대로 걸었다(`var/product-audit/blind1_newhire.py`, 결과 `blind1.json`).
"이 사람이 오늘 업무를 시작할 수 있는가"만 물었다.

**새 Critical/High 범주: 0건.**

| 관측 | 판정 |
|---|---|
| **전 화면(11/11)에 "초기 설정이 아직 끝나지 않았습니다 … 관리자에게 문의해 주세요" 배너** | **결함 아님 — 폐기.** `app/setup/checklist.py:123-141`이 `USER_VISIBLE_KEYS` 중 `state != DONE`인 항목이 있을 때만 띄우고, **역할에 따라 문구를 바꾼다**(관리자에겐 "초기 설정 화면에서 확인하세요"). 이 dev 인스턴스는 실제로 설정이 미완이라 **띄우는 것이 옳다.** 문구도 "~수 있습니다"로 단정하지 않는다 |
| `/my-tickets`·`/my-stats`가 **완전히 비어 있다** | **원인이 명확히 안내된다** — *"계정 연결이 없으면 어떤 티켓이 내 것인지 판단할 수 없어 목록을 불러올 수 없습니다"*, *"관리자에게 계정 연결을 요청하세요"*. `PA-RC-0002`가 센 **회복 경로를 갖춘 좋은 문구**의 실례다 |
| 그런데 **제품 안에 "요청"할 방법이 없다** | **신규 관측(Low, improvement)** — `app/notion_mapping/router.py`의 엔드포인트 7개가 전부 `CONSOLE_READ/WRITE_ROLES`다. 일반 사용자는 자기 매핑을 조회도 요청도 할 수 없고 `Profile.jsx:159`에서 상태 배지만 본다. **설계로서는 옳다**(외부 시스템 신원 매핑은 관리자 일이다). 빠진 것은 **"관리자에게 요청" 버튼 하나**뿐이고, 이 제품엔 이미 알림 체계가 있다 |
| `/projects` "프로젝트가 없습니다", `/my-stats` "아직 집계할 티켓이 없습니다" | 빈 상태 문구 정상 |
| 콘솔 오류 | **0건** |

**결론**: 신규 입사자는 팀 티켓·문서·게시판·채팅은 **첫날 바로 쓸 수 있고**, 개인 화면
(`/my-tickets`·`/my-stats`)만 관리자 연결을 기다린다. 그 사실이 화면에 정직하게 적혀 있다.
**새 Critical/High 없음.**

blind_pass=2 cycle_id=PA-20260812-171558-56c5befa new_critical_high_categories=0 at=2026-08-15T12:58:29+09:00

### pass 2 — 진입점: **"감사자가 분기 점검에서 하는 일"**

pass 1과 **역할도 workflow도 다르게** 잡았다 — 이 Cycle에서 한 번도 안 써 본 `auditor` 역할을
만들고, "시작하기"가 아니라 **"이력을 읽고 경계를 확인한다"** 는 일을 걸었다
(`var/product-audit/blind2_auditor.py`, 결과 `blind2.json`).
프롬프트 F축이 특별히 지목한 것 — *"UI에서 버튼을 숨기는 것과 실제 API authorization을
구분한다. direct URL/direct API"* — 를 **행동으로** 시험했다.

**새 Critical/High 범주: 0건.** 그리고 F축이 **행동으로 확인됐다.**

| 검사 | 결과 |
|---|---|
| 감사자가 써야 하는 화면 8개(`/audit`·`/audit-anomalies`·`/impersonation`·`/backup`·`/rbac`·`/dev-report`·`/maintenance`·`/announcements`) | **전부 정상 렌더 + 실데이터**(감사 로그 100행, 개발자 리포트 65행, 권한 매트릭스 13행 등) |
| 감사자가 못 써야 하는 화면 8개(`/users`·`/offboarding`·`/organizations`·`/job-titles`·`/system`·`/setup`·`/notion-console`·`/llm-console`)에 **직접 URL로 진입** | **8개 전부 차단**(`h1` 없음, 거부 표시, 0행) |
| **세션 쿠키를 들고 API 직접 호출** | `/api/admin/users` **403** · `/api/admin/offboarding` **403** · `/api/admin/audit` 200 · `/api/admin/backups` 200 · `/api/admin/settings` 200 · `/api/admin/reports/dev-monthly` 200 |
| 사이드바 필터링 | 관리자 세그먼트로 전환하면 **29개 항목**이 보이고, **차단 대상 8개는 정확히 빠져 있다** |

즉 **화면 게이트·라우트 게이트·API 게이트 셋이 모두 같은 답을 낸다.** `FC-05`(화면 역할 게이트)가
정적 대조로 주장한 것을 이번에 **실제 요청으로** 확인했다.

**조사 중 내 오탐 1건**: 처음에 *"감사자에게 관리자 메뉴가 하나도 안 보인다"* 로 읽었다.
사이드바를 `/#/me`(사용자 세그먼트)에서 읽고, 세그먼트 전환 탭을 `header` 안에서만 찾았기
때문이다. 실제로는 **사이드바 최상단(x=132, y=80)에 「관리자」 버튼**이 있고
(`AppShell.jsx:322-339`, *"사용자 지적 P2 — 왼쪽 트리 상단으로 옮겨라"*), 누르면
`/#/dashboard`로 전환된다. `App.jsx:46`의 `isUser = role === "user"` 조건상 `auditor`는
당연히 탭을 받는다. **결함 아님.**

## 2026-08-16 회차 — Gate 거부 해소 + Handoff 소비 재검증

Supervisor가 직전 `AUDIT_COMPLETE`를 3가지 이유로 거부했다. 셋 다 해소했고,
그 과정에서 **Handoff가 이미 대부분 소비됐다**는 것을 발견해 재검증까지 수행했다.

### 거부 사유 해소

| 사유 | 해소 |
|---|---|
| allowlist 밖 dirty(`node_modules/`, `BUILD_STAMP.json`) | **내가 만든 것이 아니다.** Supervisor가 이번 invocation 시작 시 `cycle.json`의 `foreignDirty`에 두 경로를 이미 등록했다(RUN CONTEXT의 `pre_existing_dirty_paths`와 일치). 건드리지 않았다. 내 `gate_check.py`가 목록을 하드코딩하고 있어 `cycle.json`을 읽도록 고쳤다 — 하드코딩은 Cycle 상태가 바뀔 때 조용히 어긋난다 |
| `HANDOFF-SUMMARY`에 `deferred_for_human_approval` 없음 | 이 charter 판에서 새로 요구된 블록이다. `actionable_root_causes=3` · `redesign_root_causes=1` · `deferred_for_human_approval=0`으로 추가 |
| Handoff에 사람에게 미루는 표현 | `PA-RC-0003`을 **구현 가능한 Root Cause로 재정의**했다 — "저장소 보안 검사가 `.git` 내부(stash/reflog/dangling)를 안 본다". 자격증명 회전 자체는 내 권한 밖 외부 행위라 `REPORT` §7-B "외부 제약"에 사실만 적었다. 즉 *"사람이 할 때까지 아무것도 못 한다"* 가 아니라 **검사를 먼저 켜서 그 조치가 실제로 일어나게 만드는 쪽**을 택했다 |

### Handoff 소비 재검증 (이번 회차의 실질 작업)

구현 Phase가 17커밋을 진행했다. **"완료"라는 기록을 믿지 않고** 각 RC를 그 자신의
`acceptance_criteria`로 다시 쟀다. 결과: **8건 중 4건 닫힘 · 1건 철회 · 3건 열림.**

| RC | 결과 |
|---|---|
| `PA-RC-0005`·`0007`·`0008`·`0009` | ✅ 닫힘. 특히 `0008`은 **race 테스트 5회 연속 통과**로 실행 확인(원래 약 40% 실패) |
| `PA-RC-0010` | ❌ **철회 — 내 오탐이었다** |
| `PA-RC-0001`·`0002`·`0003` | 열림(각각 잔여 범위가 명확) |

### 이번 회차에 내가 저지른 오류 3건 (전부 정정함)

1. **`PA-RC-0010` 자체가 오탐이었다.** `/login`의 라이트 고정은 빠뜨린 것이 아니라
   회귀 테스트(`test_login_page_does_not_theme_itself`)와 `login.css`의 `color-scheme: light`
   선언이 못박은 **의도된 설계**다. 나는 `templates_html`과 `tokens.css`만 보고
   **그 화면이 실제로 읽는 `login.css`를 열지 않았다.**
2. **그 정정도 틀렸다.** `/login` 하나만 다시 재고 *"수정이 무효하니 되돌려라"* 라고 적었다.
   4화면을 전부 재니 `/forgot-password`·`/reset-password`에서는 **다크가 실제로 켜진다** —
   구조적 주장은 옳았고 구현 Phase의 판단이 정확했다. 되돌리라는 지시를 철회했다.
3. **`PA-RC-0001`을 잘못 깎아내렸다.** *"리터럴 285회·44종으로 늘었다"* 고 적었는데,
   `fontSize:` 출현을 세면서 **토큰 참조 206회와 아이콘 크기 27회까지 리터럴로 계산**했다.
   실제로는 이 RC의 핵심 처방(일급 타이포 API)이 적용됐고 소비도 진행 중이다.

> **관통하는 교훈**: 셋 다 *"패턴이 몇 번 걸렸는가"* 만 세고 *"무엇이 걸렸는가"* 를 안 본 것이다.
> 이 Audit이 Cycle 내내 13번 경계해 온 바로 그 실수를, 재검증 단계에서 3번 더 했다.
> **표본 하나로 세운 결론은 표본 하나로 뒤집으면 안 된다** — 원 주장이 "전체"였으면 정정도 전체를 재야 한다.

## 완료 Gate A~G 평가 (2026-08-15, AUDIT_COMPLETE 직전)

프롬프트 12절의 Gate를 하나씩 근거와 함께 판정한다. *"문서 많이 씀"* 은 근거가 아니다.

| Gate | 요구 | 판정 | 근거 |
|---|---|---|---|
| **A** Inventory | 주요 Surface가 전부 inventory에 있고 **이유 없는 UNSEEN이 없다** | ✅ | 90표면 × 26축 = 2,340칸. `gen_coverage.py` 재생성 결과 `unseen_without_reason=0`. Inventory는 소스에서 기계 생성(`gen_inventory.py`) |
| **B** Intent | 주요 Feature가 Intent 근거와 confidence를 가진 Contract를 갖고, 모르는 것은 정직하게 UNKNOWN | ✅ | `FC-01`~`FC-08` 전부 confidence 기재. **UNKNOWN 3건은 지우지 않고 남겼다**(티켓 정본 정책 · 복구 리허설 성공 판정 기준 · n8n/Runner 실패 전파). 이 Cycle에 2건(오프보딩·문서생성)을 D축 추적으로 닫아 `FC-07`·`FC-08`이 됐다 |
| **C** Axis | 5절 A~Z 축이 전부 Coverage에 반영 | ✅ | 26축 전부. 마지막까지 비어 있던 `C`(기능 조작)·`S`(성능)를 Round 14·15에서 닫았다 |
| **D** Evidence | 정적 추정과 실행 증거가 **구분**되고, Confirmed/Strong에 재현/trace가 있으며, Finding이 Root Cause로 병합 | ✅ | Coverage가 `STATIC_ONLY`/`OBSERVED`/`EXECUTED`를 셀 단위로 구분한다. Handoff 8건의 근거: `0008` race 테스트 **실제 40% 실패 재현** · `0009` 2,903건 **실행** · `0007` 원격 mtime+asset 해시 **실측** · `0010`·`0001` **브라우저 실측** · `0003` stash 직접 확인 · `0002`·`0005` 소스 전수 스캔(주장 자체가 소스에 대한 것) |
| **E** Skill | 사용 가능한 Skill을 **실제로** 적용하고, 미설치는 skill_gap + 대체 방법 | ✅ | 핵심 5개 전부 적용(`ux-writing`→`PA-F-011` / `ui-ux-pro-max`→`RD-1`~`3` / `impeccable`→`RD-5` 진단 교체 / `redesign-existing-projects`→L·M축 / `humanize-korean`→`PA-F-039`). 순서(UX Writing → 한국어) 준수. 미설치 2건(`chrome-devtools`·`a11y-debugging`)은 `skill_gap`으로 기록하고 Playwright+Chromium 151 실측으로 대체 — 각 Handoff 블록의 `quality_rubric`에 쓴 자를 그대로 남겼다 |
| **F** Blind Re-Audit | 서로 다른 진입점으로 **2회 연속**, 둘 다 새 Critical/High 범주 0 | ✅ | pass 1 *"신규 입사자 첫날"* 0건 · pass 2 *"감사자 분기 점검"* 0건. pass 2는 `auditor` 역할로 **F축을 행동 검증**(화면·직접 URL·직접 API 세 계층이 같은 답) |
| **G** Handoff | REPORT 존재 · Confirmed/Strong이 BACKLOG에 **중복 없이** 반영 · PA-RC 블록 완전 · QA gap 반영 · marker 정확 | ✅ | commit `703f253`. 기존 552행 전체 대조 후 신규 7행 + 기존 6행 갱신. `PA-RC-0003`은 `SEC-20`과 같은 자격증명이라 **중복 행을 만들지 않고** 그 행을 확장. PA-RC 블록 8건 × 필수 27필드 자기검사 PASS. QA gap은 `QA_COVERAGE.md` §13 새 축 `T1`~`T9` |

**BLOCKED 없음.** `AUDIT_BLOCKED` 사유(사람/환경 때문에 끝내 막힌 필수 Coverage)에 해당하는 항목이 없다.

> **이 Gate 표가 숨기지 않는 것**: Coverage 2,340칸 중 **1,336칸(57%)이 여전히 UNSEEN**이다.
> Gate A가 요구하는 것은 *"UNSEEN이 없다"* 가 아니라 *"이유 없는 UNSEEN이 없다"* 이고 그것은 만족했지만,
> 이 Audit이 제품 전체를 실행으로 훑었다는 뜻은 아니다. 브라우저로 실제로 본 화면은 **12/90 표면**이다.
> 수렴의 근거는 Coverage 비율이 아니라 **Gate F** — 서로 다른 진입점의 blind pass 2회가
> 새 Critical/High를 하나도 못 찾았다는 사실이다.

## Gate F 상태: **2 / 2 연속 clean** — 두 pass 모두 새 Critical/High 0건.
## 6. 2026-08-15 COLD 재접지에서 확인한 것

- 이전 회차의 Audit 문서 4종이 그대로 남아 있고 내용이 유효하다(`git ls-files` 로 추적 확인).
  Coverage 요약 블록도 표와 일치한다 — 이어서 진행했다.
- **`git stash@{0}` 에 TEST 서버 SSH/sudo 평문 비밀번호가 있다** → `PA-RC-0003`(Critical) 신규.
  추적 중인 `CLAUDE.md`(HEAD)와 워킹트리는 깨끗하다. 값을 문서·로그에 복제하지 않았다.
- `ux-writing` Skill을 **실제로 적용**해 `PA-F-011`(실패 문구의 85%가 회복 경로 없음, 3요소를
  갖춘 것 0건)을 도출했고, 그 결과 `PA-RC-0002`를 Medium → **High**로 재분류했다.
- 필수 문서 7종을 모두 만들었다(`FEATURE_CONTRACTS`·`HANDOFF`·`REPORT` 신규).
