# INVENTORY 12 — Probe

**정본**: `scripts/check_*.py` · `scripts/ui_qa/**`
**측정**: 2026-08-20 (Plan Mode)
**소유**: **S1 — 이것이 S1 의 1순위 작업이다** (P-01)

## 측정

| 항목 | 값 |
|---|---|
| Checker | **21** |
| ui_qa 모듈 | **26** |
| Assertion | **34종** (W0~W5 자산) |
| `probe_selftest` | **19 사례** — 판정 규칙을 고친 커밋에서 «결함은 잡히고 정상은 안 잡힌다» 를 합성 DOM 으로 확인한다 |

## 왜 이걸 먼저 하는가

**검사가 눈을 감으면 「위반 0」이 「결함 0」처럼 보인다.**

W5 에서 실제로 일어난 일이다 — 승격했다고 적힌 검사가 한 번도 `--fail-on` 으로 걸린 적이 없었고,
Gate 가 읽는 After 포인터는 세 Wave 낡아 있었으며, `plain_dropdown_for_entity` 는 `select` 만
순회해 **가장 나쁜 형태(맨 텍스트 상자)를 664 page-instance 에서 전부 skip** 했다.
셋 다 「위반 0」으로 보였다.

이번 전환은 **Route 집합과 DB 를 통째로 바꾼다.** 눈을 감은 검사 위에서 그걸 하면 무엇이 깨졌는지
알 수 없다.

## 알려진 거짓 통과 경로 8건 — S1 이 고친다

| 우선순위 | 프로브 | 결함 | 조치 |
|---|---|---|---|
| **1** | `check_ui_renewal_coverage.py` `read_tab_groups()` / `read_settings_tabs()` / `read_jsx_routes()` | 소스 리터럴을 못 찾으면 **`[]` 반환 → 검사 루프가 0번 돌고 OK 를 찍는다.** Route 를 갈아엎으면 정확히 이 경로로 조용히 통과 | **빈 결과를 FATAL 로.** 최소 개수 단언 추가 (R4) |
| 2 | `check_scope_gates.py` | `ROOT.glob("app/*/router.py")` **단일 레벨**이라 중첩 라우터 미검사. **공유 헬퍼 안에서 게이트를 지워도 통과**(손으로 확인됨) | `rglob` + 헬퍼 본문 추적 |
| 3 | `check_qa_target_host.py` | 디렉터리 없으면 `[SKIP]` + **exit 0 (fail-open)**. IP·포트 대상 프로브는 정규식이 못 본다 | **fail-closed** + IP 패턴 추가 |
| 4 | viewport-gated assertion **6종** | 1366/1920 에서 `skip` → 요약에서 "문제 없음" 으로 읽힘 (QA-10·QA-13 전례) | `--fail-on all` 의 `unverified_gates` 면제(`run.py:701`) **제거** |
| 5 | `check_test_strength.py` | assertion **개수**만 센다. `toBe`→`toBeDefined` 가 통과. 기본 `--base HEAD` 라 **커밋된 약화는 영구 불가시** | 기본 base 를 **직전 Session 커밋**으로 |
| 6 | `final_verify.sh:38-39` | `check_bundle_fresh --write` 직후 같은 검사 → **절대 실패할 수 없다** | `--write` 를 빌드 직후로 옮기고 검사는 plain 으로 |
| 7 | `check_css_vars.py` | JS 정의 판정이 **전 JS 파일 concat 대상 substring** — 주석에 한 번만 나와도 "정의됨" | 정의 구문만 인정 |
| 8 | ui_qa **20개 보조 프로브** | **전부 TLS 검증을 끈다** → 호스트명 불일치가 **구조적으로 안 보인다** | **S3 인증서 재발급 후** 검증 활성화 + `ssl_verify_result=0` 단언 |

> 8번은 S1 에서 **코드를 준비**하고 **S3 에서 켠다** — 지금 켜면 옛 호스트명 인증서 때문에 전부
> 빨갛다. 「지금 못 켠다」와 「안 켤 것이다」는 다르다. S3 Exit 조건에 들어 있다.

## 템플릿 — 이 셋을 닮게 만든다

`check_icon_props.py` · `check_ink_scale.py` · `check_logical_border_props.py` 와 `probe_selftest.py`.

**실제 스캔 전에 양방향 `--self-test` 를 돌리고, 실패하면 아무것도 보고하지 않는다.**
나머지 프로브를 이 형태로 끌어올린다.

## 반례 도구도 반례가 필요하다

W5 독립 검수가 잡은 것: `control_baseline_mismatch` 의 「두 줄로 접힌 글은 컨트롤이 아니다」 규칙이
**모든 MUI 입력**을 함께 떨어뜨렸다(노치 라벨이 `position:absolute` 다). 탈락률 **100%**.

더 아픈 것은 `probe_selftest` 17 사례가 이것을 **구조적으로 못 잡았다**는 사실이다 — 반례가 전부
맨 `<button>`/`<input>` 이라 MUI 구조를 한 번도 태우지 않았다.

**위양성을 의심하는 것과 눈이 먼 것을 의심하는 것은 둘 다 해야 한다.**

## Gate 실행 (E3)

```bash
python scripts/check_ui_renewal_coverage.py --stage plan    # 문서 정합성만
python scripts/check_ui_renewal_coverage.py --stage wave    # Wave 범위 전량
```

**Probe 하나 고칠 때마다 Full Capture 하지 않는다.** 8건을 **Batch 로** 처리하고, 판정 규칙 검증은
합성 DOM(`probe_selftest.py`)으로 한다 — 실브라우저 전량 실행에 기대지 않는다.

## 완성도 — S1 이 마저 할 것

- 위 8건 전부. 각 수정마다 **양방향 반례**를 `probe_selftest` 에 추가한다
- 21 checker + 26 ui_qa 모듈을 열거하고 **self-test 보유 여부**를 표시한다 — 지금은 셋만 확인돼 있다
- **프로브를 좁히는 것과 끄는 것은 다르다.** 좁힌 자리마다 반례를 넣고, 넓힌 것도 함께 기록한다
