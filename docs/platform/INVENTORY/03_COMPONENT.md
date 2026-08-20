# INVENTORY 03 — Component

**정본**: `frontend/src/**` Source
**측정**: 2026-08-20 (Plan Mode) — **목록 전량 열거는 S1 이 채운다**

## W0~W5 가 만든 공유 자산 — 보존한다 (U6)

| 자산 | 역할 |
|---|---|
| `theme.js` | Indigo 하우징 · 토큰 · Light/Dark 램프 |
| `kit.jsx` | 공유 Layout Primitive. **면(Surface)은 부품이 정한다** (D-185) |
| `FilterBar` / `filters.jsx` | 탐색 줄. **판이 아니다** — `c-toolbar-card` 를 걷어냈다 (D-186) |
| `EntityCombobox` | Entity 는 고르는 것이지 옮겨 적는 것이 아니다 |
| `navConfig` | Navigation 단일 정의. **한 열의 라벨 · 신호 둘 · 랜드마크당 글리프 하나** (D-184) |
| `DataScreen` + registry | 27/28 소비처 |
| `charts/*` · CommandPalette · `lib/api.js` · auth · error envelope | 유지 (재스킨 이하) |

**이 자산을 폐기하지 않는다.** 이번 전환은 데이터 계층과 도메인을 바꾸는 것이지 부품을 버리는
것이 아니다.

## 신설 예정 (지금 0%)

| 부품 | 소유 Session |
|---|---|
| **DnD 인프라** — `dnd-kit` 기반 `SortableList`/`SortableBoard` 공통 부품 하나 | S6 |
| 소비처: Backlog · Sprint 배정 · Sprint 내 정렬 · Kanban · Folder 이동 · Document 이동 | S6·S7 |
| **Rich Editor** — TipTap(MIT extension 만), **route-level lazy load 필수** | S7 |
| Ticket Relation UI · Project Member 관리 · Knowledge Space/Folder 트리 | S6·S7 |

> Editor + DnD 도입이 번들 예산을 넘길 수 있다 (R10). `check_bundle_size.sh` 게이트를 유지하고
> lazy load 를 강제한다.

## 제거 예정

| 부품 | 이유 |
|---|---|
| `MirrorNotice` 와 그 소비처 6곳 | **동기화 개념 자체가 사라진다.** CLAUDE.md §145 위반이 자동 해소된다 |
| NotionConsole · Notion Mapping Console | Notion Runtime 소멸 |

## 완성도 — S1 이 마저 할 것

- `frontend/src/components/**` 와 `kit.jsx` export 를 실제로 열거해 **부품 ↔ 소비처 표**를 만든다.
  지금은 위 표가 「보존/신설/제거」 축만 갖고 있고 전량 목록이 아니다
- Assertion 34종과 부품의 매핑 확인 (`12_PROBE.md` 와 짝)
