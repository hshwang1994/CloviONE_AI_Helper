# INVENTORY — 실측 목록 12종

> **Inventory 를 먼저 만드는 이유**: 「전체 캡처 → 프로브 결함 → 프로브 수정 → 제품 결함 →
> 빌드 변경 → 캡처 무효 → 재캡처」 루프를 반복하지 않기 위해서다. 무엇이 몇 개 있는지를 모르면
> 검증이 **얼마나 남았는지**를 알 수 없고, 알 수 없으면 「위반 0」과 「안 재고 통과」를 구분할 수 없다.

**기록 시점**: 2026-08-21 (S0) · **측정 시점**: 2026-08-20 (Plan Mode 전수조사)

---

## 이 디렉터리의 규칙

1. **여기 적힌 숫자에는 전부 출처와 측정 시점이 붙는다.** 출처 없는 숫자를 쓰지 않는다.
2. **정본은 Source 다.** 이 문서가 Source 와 어긋나면 Source 를 확인하고 이 문서를 정정한다.
3. **확보된 것은 재조사하지 않는다.** Plan Mode/S0 이 확보한 값은 그대로 쓴다.
   각 파일의 **`미확인 항목과 Owner` 절**은 아직 확인되지 않은 것과 **그것을 실제로 필요로 하는
   Session** 을 지목한다. **여기 적힌 것이 전부 S1 작업이라는 뜻이 아니다** — Owner 가 S1 인 것만
   S1 이 한다.
4. **상세 전수 목록은 기본 작업이 아니다.** API 318 decorator · Component · Dependency · Test 파일
   같은 전수 열거는 **후속 Session 이 실제로 필요할 때 그 Owner Session 에서** 갱신한다.
   지금 없다는 것이 결함이 아니다.
5. **해결되지 않은 불일치는 지우지 않고 표시한다.** 현재 0건.

---

## 12종

| # | 파일 | 대상 | S0 시점 상태 |
|---|---|---|---|
| 1 | [`01_ROUTE.md`](01_ROUTE.md) | 사용자/관리자 전체 Route | 확보 (원장 = `ROUTE_COVERAGE.json`) |
| 2 | [`02_PAGE.md`](02_PAGE.md) | Page / Surface / Archetype | 확보 (원장 = `ROUTE_COVERAGE.json`) |
| 3 | [`03_COMPONENT.md`](03_COMPONENT.md) | 공유 UI 부품과 소비처 | 보존/신설/제거 축 확보. 전수 열거는 **소비 Session(S7·S16) 필요 시** |
| 4 | [`04_API.md`](04_API.md) | FastAPI Route / Router | 개수·계약 확보. 경로별 열거는 **소비 Session(S2·S5) 필요 시** |
| 5 | [`05_DB.md`](05_DB.md) | 현행 SQLite 스키마 · 데이터 규모 · 품질 | 확보 (가장 두꺼운 실측) |
| 6 | [`06_DEPENDENCY.md`](06_DEPENDENCY.md) | Python / Node 의존과 신규 도입 후보 | 채택/미채택 확보. 전량 열거는 **소비 Session(S4) 필요 시** |
| 7 | [`07_NOTION.md`](07_NOTION.md) | Notion 워크스페이스 실측 | 확보 (실 API 조회) |
| 8 | [`08_SQLITE.md`](08_SQLITE.md) | SQLite 결합 지점 (코드 레벨) | 확보 (13항 실측 목록) |
| 9 | [`09_N8N.md`](09_N8N.md) | n8n 워크플로 · 외부 Runner | 확보 |
| 10 | [`10_HARNESS.md`](10_HARNESS.md) | 설치/배포/검증 Script | 확보 |
| 11 | [`11_TEST.md`](11_TEST.md) | Backend / Frontend / Runner 테스트 | 확보 — 프런트 수치는 **실행 Evidence 로 확정됨** |
| 12 | [`12_PROBE.md`](12_PROBE.md) | Checker / ui_qa 프로브와 **알려진 거짓 통과 경로 8건** | 확보 — **S1 의 1순위 작업** |

---

## 원장이 따로 있는 것은 여기서 복제하지 않는다

| 대상 | 정본 |
|---|---|
| Route/Surface 상태 · Evidence · Finding | `docs/ui-renewal/ROUTE_COVERAGE.json` |
| Functional Flow 상태 | `docs/ui-renewal/FUNCTIONAL_COVERAGE.json` |
| UI 요구사항 161건 매핑 | `docs/ui-renewal/REQUIREMENT_MATRIX.md` |
| 설계 결정 | `docs/DECISIONS.md` |

**두 곳에 적으면 갈라진다.** 이 디렉터리는 원장을 가리키고, 원장이 없는 것만 직접 담는다.
