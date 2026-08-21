# INVENTORY 12 — Probe

**정본**: `scripts/check_*.py` · `scripts/ui_qa/**`
**측정**: 2026-08-20 (Plan Mode) · **갱신**: 2026-08-21 (S1 — 8건 수정 완료)
**소유**: S1 (P-01) — **완료**

## 측정

| 항목 | 값 |
|---|---|
| Checker | **21** |
| ui_qa 모듈 | **27** (S1 이 `tls.py` 를 더했다) |
| Assertion | **34종** (W0~W5 자산) |
| `probe_selftest` | **30 사례** — DOM 19 + **로직 11**(S1 추가). 브라우저 없이 돌리려면 `--logic-only` |
| `--self-test` 를 가진 Checker | **8** — `check_icon_props` · `check_ink_scale` · `check_logical_border_props` · **`check_ui_renewal_coverage`** · **`check_scope_gates`** · **`check_qa_target_host`** · **`check_css_vars`** · **`check_test_strength`** (뒤 다섯이 S1 산출) |

## 왜 이걸 먼저 했는가

**검사가 눈을 감으면 「위반 0」이 「결함 0」처럼 보인다.**

W5 에서 실제로 일어난 일이다 — 승격했다고 적힌 검사가 한 번도 `--fail-on` 으로 걸린 적이 없었고,
Gate 가 읽는 After 포인터는 세 Wave 낡아 있었으며, `plain_dropdown_for_entity` 는 `select` 만
순회해 **가장 나쁜 형태(맨 텍스트 상자)를 664 page-instance 에서 전부 skip** 했다.
셋 다 「위반 0」으로 보였다.

이번 전환은 **Route 집합과 DB 를 통째로 바꾼다.** 눈을 감은 검사 위에서 그걸 하면 무엇이 깨졌는지
알 수 없다.

## 알려진 거짓 통과 경로 8건 — S1 이 고쳤다

| # | 프로브 | 결함 | S1 이 한 것 |
|---|---|---|---|
| **1** | `check_ui_renewal_coverage.py` 리더 셋 | 소스 리터럴을 못 찾으면 `[]` → 검사 루프가 0번 돌고 OK (R4) | `SourceReadError` + `SOURCE_FLOOR` 하한. `<Route` 는 **리터럴·계산·index 셋 중 하나로 분류돼야 하고** 미분류가 있으면 FATAL. 새 조건 **C0r** 이 리더 실패를 Gate 실패로 옮기고 **표본 수를 먼저 찍는다** |
| 2 | `check_scope_gates.py` | `ROOT.glob("app/*/router.py")` 단일 레벨. 공유 헬퍼 본문에서 게이트를 지워도 통과 | **사각 셋**을 막았다 (아래 별도 절) |
| 3 | `check_qa_target_host.py` | 디렉터리 없으면 `[SKIP]` + exit 0 (fail-open). IP·포트 대상은 정규식이 못 봄 | **fail-closed** · IP 패턴(되돌이 제외) · `checked==0` 도 실패 · TLS 정책 가드(#8) |
| 4 | viewport-gated assertion 6종 | `--fail-on all` 이 `unverified_gates` 를 **통째로** 껐다 (QA-10·QA-13) | 면제를 **`assertions.MODAL_CLASSES` + `--modals` 없음** 으로 좁혔다. 무엇을 면제했는지 실행이 직접 찍는다 |
| 5 | `check_test_strength.py` | 기본 `--base HEAD` → **커밋된 약화는 영구 불가시**. 단언 **개수**만 셈 | 기준을 `WORK_STATE.last_stable_commit` 에서 읽고 **없으면 실행 거부**. ref 를 `rev-parse --verify`. **강한 단언 수**(약한 형태 제외)가 줄면 실패 |
| 6 | `final_verify.sh:38-39` | `--write` 직후 같은 검사 → 절대 실패 불가 | 신선도 검사를 **빌드 앞**(커밋된 상태)으로, `--write` 는 빌드 스텝에 붙였다 |
| 7 | `check_css_vars.py` | JS 정의 판정이 전 JS concat substring — 주석 한 번이면 "정의됨" | **정의 구문만** 인정(`setProperty` · 객체 키 · 템플릿 선언). 실측 48개 중 진짜 정의는 **6개**였다 |
| 8 | ui_qa 보조 프로브 **19개** | 전부 TLS 검증을 끔. 13개는 **스위치조차 없이** `insecure=True` 를 박아 둠 | `scripts/ui_qa/tls.py` **한 곳**으로 모았다. **S3 이 `DEFAULT_VERIFY = True` 한 줄을 바꾸면 19개가 함께 켜진다** |

## 2번이 실제로 무엇을 안 보고 있었나

`glob` 하나만 문제가 아니었다. 세 겹으로 눈이 감겨 있었다.

1. **파일 이름이 `router.py` 가 아니면 통째로 안 봤다** — `app/admin/feature_flags.py` ·
   `app/admin/rbac.py` · `app/auth/reset_router.py` · `app/search/reindex_router.py`.
2. **변수 이름이 `router` 가 아니면 안 봤다** — `@admin_router` · `@user_router` ·
   `@organizations_router` · `@delegations_router` · `@personal_router` 로 선언된 **14 라우트**.
   그래서 `app/announcements/router.py` 는 **파일 전체가 0개 라우트**로 읽혔다.
3. **공용 조회 헬퍼의 본문이 비어도** 호출부 모양(`_get_x_or_404(db, id, me)`)만으로 통과했다.
   파일 상단 「한계」에 «못 잡는다» 고 적혀 있던 자리다. 이제 헬퍼 본문까지 따라간다.

**수치**: 라우트 선언 파일 44 → **48**, 모듈 43 → **44**, id 를 받는 경로 123 → **129**.

그리고 눈을 뜨자마자 **둘이 나왔다**:

| 경로 | 판정 | 처리 |
|---|---|---|
| `app/announcements/router.py::dismiss_announcement` | **위양성** — 공지는 부서로 좁혀 저장되지 않는다(`_ensure_may_touch_announcements` docstring, UB-01). 좁힐 범위가 없다 | `EXEMPT` 에 사유와 함께 등록 |
| `app/approvals/router.py::revoke_delegation` | **진짜 결함** — `/api/admin/approval-delegations` 표면 전체가 `principal` 을 안 받는다 | `KNOWN_GAPS` → **S5** (아래) |

## `EXEMPT` 와 `KNOWN_GAPS` 는 다른 통이다

`EXEMPT` = 「안 거는 것이 **의도**다」. `KNOWN_GAPS` = 「**결함인데** 이 Session 이 고칠 자리가
아니다」. 둘을 한 통에 담으면 결함이 의도로 위장한다.

`KNOWN_GAPS` 규칙 셋: ① Owner Session 과 원장을 적는다 ② 매 실행 `[GAP]` 로 크게 찍고 OK 줄에도
개수를 넣는다 ③ **거기 적힌 경로가 스캔에서 사라지면 실패한다**(늙은 면제 검출).

## 템플릿 — 이 셋을 닮게 만든다

`check_icon_props.py` · `check_ink_scale.py` · `check_logical_border_props.py` 와 `probe_selftest.py`.

**실제 스캔 전에 양방향 `--self-test` 를 돌리고, 실패하면 아무것도 보고하지 않는다.**
S1 이 고친 다섯도 이제 이 형태다.

## 반례 도구도 반례가 필요하다

W5 독립 검수가 잡은 것: `control_baseline_mismatch` 의 「두 줄로 접힌 글은 컨트롤이 아니다」 규칙이
**모든 MUI 입력**을 함께 떨어뜨렸다(노치 라벨이 `position:absolute` 다). 탈락률 **100%**.

더 아픈 것은 `probe_selftest` 17 사례가 이것을 **구조적으로 못 잡았다**는 사실이다 — 반례가 전부
맨 `<button>`/`<input>` 이라 MUI 구조를 한 번도 태우지 않았다.

**위양성을 의심하는 것과 눈이 먼 것을 의심하는 것은 둘 다 해야 한다.**
S1 도 그 자리를 한 번 밟았다 — 첫 지연 측정이 세 경로 전부 ~20ms 로 같게 나왔는데, 그건 PG 지연이
아니라 `psql` **프로세스 시작 시간**이었다(같은 실행의 `EXPLAIN` 은 0.23ms 였다).
**값이 전 표본에서 같으면 측정이 아니라 상수를 읽고 있는 것이다.**

## Gate 실행 (E3)

```bash
python scripts/check_ui_renewal_coverage.py --self-test   # 리더 자기검증만
python scripts/check_ui_renewal_coverage.py --stage plan   # 문서 정합성만
python scripts/check_ui_renewal_coverage.py --stage wave   # Wave 범위 전량
python -m scripts.ui_qa.probe_selftest --logic-only        # 브라우저 없이 규칙 반례만
```

**Probe 하나 고칠 때마다 Full Capture 하지 않는다.** 8건을 **Batch 로** 처리하고, 판정 규칙 검증은
합성 DOM·합성 소스로 한다 — 실브라우저 전량 실행에 기대지 않는다.

## 미확인 항목과 Owner

| 미확인 | Owner | 내용 |
|---|---|---|
| #8 TLS 검증 **켜기** | **S3** | S1 이 스위치를 만들었다. S3 이 인증서를 CN/SAN=`clovirassist.gooddi.lab` 로 재발급한 뒤 `scripts/ui_qa/tls.py` 의 `DEFAULT_VERIFY = True` 로 바꾸고 `ssl_verify_result=0` 을 단언한다 |
| `revoke_delegation` 범위 게이트 | **S5** | `KNOWN_GAPS` 에 등록돼 있다. 고친 뒤 그 항목을 **지워야** 검사가 통과한다(늙은 면제 검출) |
| 21 checker + 27 ui_qa 모듈의 self-test 보유 여부 전수 표시 | **각 Owner Session** (필요 시) | S1 은 고친 8건만 봤다. 나머지를 전수 표로 만드는 것은 S1 필수 작업이 아니었다 |

**프로브를 좁히는 것과 끄는 것은 다르다.** 좁힌 자리마다 반례를 넣고, 넓힌 것도 함께 기록한다.
