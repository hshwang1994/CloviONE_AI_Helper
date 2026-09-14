# 부품 대장 — 확정 규약 핸드오프 (2~5단계)

**정본**: `frontend/src/ui/**` · `frontend/src/screens/**` Source
**대조표**: `/kit` (`frontend/src/screens/dev/KitGallery.jsx`) — 실제 부품을 불러 쓴다
**측정**: 2026-09-08, 1920x1080 light. 치수는 브라우저의 `getComputedStyle` 실측이고
캡처는 `dist/ui-qa/kit-gallery-r8/` 다.

이 문서가 답하는 것 하나: **「이 모양을 어디서 고치나」**. 부품마다 이름 · 파일 · 무엇을
대체했는지 · 어느 화면이 쓰는지 · 규약값 네 가지를 적는다. `03_COMPONENT.md` 는 전환 계획의
자산 목록이고 이쪽은 확정 규약의 **치수 대장**이다 — 역할이 다르다.

> **정본은 갤러리다** (소유자 확정, 2026-09-08). 시안 HTML(`design_handoff_clovirassist_ui/`)과
> 값이 어긋나면 `/kit` 쪽이 맞다. 시안은 참고로 남고, 어긋난 자리는 §4 에 실측과 함께 적는다.

---

## 1. 신설한 부품

### `DataTable` 의 표 3종 (묶음 머리행 · 발 줄 · 높이)
- **파일**: `frontend/src/ui/kit.jsx` (`GroupHeaderRow` · `GroupHeaderMeta` · `TableFooterRow`)
- **대체**: `MyTickets.jsx::GroupedTickets` 의 자체 12열 표, `DevReport.jsx` 의 담당자 구분 행 표
- **소비 화면**: 내 티켓 · 팀 티켓 · 개발 리포트 · 문서 · 작업 보드(백로그 제외) · 부품 갤러리
- **규약값**: 머리 `CONTROL.tableHead` 40 · 행 `CONTROL.tableRow` 48 · 묶음 머리 36 ·
  발 `CONTROL.tableFooter` 44. 머리 면 `background.inset`, 머리 아래 선 `divider`,
  행 사이 선 `rule`. **실측**: 머리 아래 `#DCDFEC` y=1772, 행 48px, 묶음 행 36px, 행 선 `#E5E8F3`.

### `FlatBadgeSurface`
- **파일**: `frontend/src/ui/kit.jsx`
- **대체**: 호출부 106곳이 각자 기억하던 「표 안에서는 면을 쓰지 않는다」 규칙
- **소비 화면**: `DataTable` 전체 · 홈 · AI 도우미 · 내 활동 · 조직도 · 부서 상세 · 부품 갤러리
- **규약값**: 치수 없음(문맥 제공자). 이 안의 `Badge` 는 `emphasis` 를 안 주면 면이 없다.
  호출부가 `emphasis="strong"` 으로 이길 수 있다.

### `Segmented`
- **파일**: `frontend/src/ui/kit.jsx`
- **대체**: 홈 AI 도우미의 MUI 밑줄 `Tabs`, 내 업무량의 기간 셀렉트
- **소비 화면**: 홈(AI 도우미) · 내 업무량 · 부품 갤러리
- **규약값**: 바깥 `background.inset` + 1px `divider` + `RADIUS.sm`(6) + padding 3 + gap 2,
  안쪽 `CONTROL.button - 6` = 28 · `RADIUS.sm - 2` = 4 · 선택 시 `background.plate` +
  `SHADOW.raised`. **실측**: 바깥 36px(28 + 3+3 + 1+1).

### `StatusSummaryCard` · `StatusChip` · `ZeroChip` · `RatioBar` · `StatusDot`
- **파일**: `frontend/src/ui/StatusKpi.jsx`
- **대체**: 작업 보드·회의의 `StatusKpiStrip` 카드 7~10장, 홈의 `MetricStrip` 판독 줄
- **소비 화면**: 홈 · 내 업무량 · 부품 갤러리 (`StatusKpiStrip` 은 회의가 `note` 캡션과 함께 쓴다.
  작업 보드는 2026-09-14 부터 요약 카드를 안 그린다 — D-484)

### `TicketPeek` · `useTicketPeek` (2026-09-14, D-483)
- **파일**: `frontend/src/screens/TicketPeek.jsx` · 속성 표 `screens/ticket-meta.jsx`
- **대체**: 카드 클릭 → 상세 이동. 작업 보드·스프린트 회의가 같은 창을 연다
- **소비 화면**: 작업 보드 · 스프린트 회의
- **규약값**: `Modal size="md"`. 속성 줄은 상세와 같은 `MetaBar`. 설명 앞 600자. 발 줄은
  회차 작업(secondary sm) · 빠른 수정 · 「티켓 상세 보기」(primary). 닫기는 창의 X 와 Esc 뿐이다.
  주소 `peek` 은 push, 닫기는 `-1`, 상세는 replace

### `DragItemActions` (2026-09-14, D-483)
- **파일**: `frontend/src/ui/DragDrop.jsx`
- **대체**: 끌 수 있는 카드 안에 단추를 두던 자리(없었다 — 카드 안 단추가 끌기·클릭으로 번졌다)
- **소비 화면**: 작업 보드(카드의 `OverflowMenu` · 백로그 줄의 「회차에 담기」)
- **규약값**: `inline-flex` · 포인터/마우스/터치/키/클릭 전파 차단

### `TeamSelect` (2026-09-14, D-482)
- **파일**: `frontend/src/ui/filters.jsx`
- **대체**: 작업 보드의 부서 필터(`DepartmentFilter`) 자리 — 필터가 아니라 **문맥**이다
- **소비 화면**: 작업 보드 · 스프린트 회의
- **규약값**: `EntityCombobox` · 라벨 「팀」 · 「전체」 없음 · 후보 < 2 면 안 그린다 · 라벨은 경로

### `DiscussBucket` 칩 (2026-09-14, D-484)
- **파일**: `frontend/src/ui/DiscussBucket.jsx`
- **대체**: 같은 이름의 큰 타일 여덟(격자 `DISCUSS_TILE_TRACK` 은 걷었다)
- **소비 화면**: 스프린트 회의
- **규약값**: `role="tab"` + roving tabindex 그대로. 알약 `RADIUS.pill` · px 10 · py 5 ·
  `bodySm`. 톤 점은 KPI 와 같은 `StatusDot` 7px(신호 셋만). 고른 칩은 `primary.soft` 면 + `brand.core` 선

### `Gauge` `centerSize="readout"` · `centerCaption` (2026-09-14, D-484)
- **파일**: `frontend/src/ui/charts/Gauge.jsx`
- **소비 화면**: 스프린트 회의(회차 건강 11rem · 두께 8)
- **규약값**: 덮개 `1fr auto 1fr` 격자. 판독값 `FONT_SIZE.pageTitle`, 캡션 `caption`
- **규약값**: 판 py 18 / px 20, 안쪽 줄 사이 12. 칩 `CONTROL.buttonSm` 30 · px 11 · gap 7 ·
  `RADIUS.sm`. 점 7px. 비율 바 8px `RADIUS.full`, 트랙 `background.sunken`.
  0건 칩은 점선. **실측**: 칩 30px, 전체 숫자 `FONT_SIZE.pageTitle` 28px.

### `ColumnSeries`
- **파일**: `frontend/src/ui/charts/ColumnSeries.jsx`
- **대체**: 내 업무량의 완료율 꺾은선(`LineSeries`)
- **소비 화면**: 내 업무량
- **규약값**: y축 트랙 40 · 격자 120 · 막대 최대 92(= 120 − 값 줄 28) · 격자선 `rule` ·
  막대 모서리 `4px 4px 0 0`. 한 칸에 막대 여럿(`bars`), 값 글자는 그중 하나 위에.

### `FoldMark` (접힘 삼각)
- **파일**: `frontend/src/screens/MyStats.jsx`
- **대체**: 없음(신설). 「주별로 펴기」가 글자만 떠 있던 자리
- **소비 화면**: 내 업무량
- **규약값**: 12x12 `clipPath` 삼각, `currentColor`, 펴짐에서 `rotate(90deg)`.
  **아직 공용 부품이 아니다** — 아래 §3 참고.

### `overflowMenuItems` (팝오버 항목 목록)
- **파일**: `frontend/src/ui/kit.jsx`
- **대체**: `OverflowMenu` 안에 인라인으로 있던 항목 렌더링. 컴포넌트가 아니라 **배열을
  돌려주는 함수**다 — MUI `MenuList` 가 자식을 훑어 키보드 이동을 붙이므로 하나로 감싸면
  화살표 키가 죽는다
- **소비 화면**: `OverflowMenu` 를 쓰는 전 화면 · 부품 갤러리(열린 상태 붙박이)
- **규약값**: 항목 `CONTROL.menuItem` 32 · `FONT_SIZE.bodySm` · 파괴적 항목만 `error.strong`
  글자 + 위 1px `divider` 로 갈림. **실측**: 32px, `#87242B`, 구분선 1px.

### `KitGallery`
- **파일**: `frontend/src/screens/dev/KitGallery.jsx` (라우트 `/kit`)
- **대체**: 없음(신설). 부품을 확인하려면 그 부품을 쓰는 화면을 하나씩 열어야 했다
- **소비 화면**: 자기 자신(개발용). 사이드바 항목 없음
- **규약값**: 없음 — **값을 한 줄도 안 적는 것이 이 화면의 계약**이다. 모든 견본이 실제 부품을
  `import` 한다. 예외는 hover 견본 둘로, 거기서도 값이 아니라 **토큰 이름**(`primary.dark` ·
  `action.hover` · `text.secondary`)을 부른다 — `:hover` 는 정지 화면에 존재할 수 없다.
- **절 13 개**: 버튼 · 버튼 크기 · 검색과 필터 바 · 세그먼티드 · 팝오버와 모달 · 칸반 카드 ·
  상태 요약 카드 · 데이터 표 · 배지와 태그 · 폼 필드 · 빈 상태 넷 · 메시지 박스 1a ·
  조작기의 상태. 시안 문서의 11 절과 순서가 같고, 세그먼티드와 「조작기의 상태」 둘만 추가다.

---

## 2. 규약을 옮긴 부품 (모양이 바뀐 기존 부품)

### `Callout` — 메시지 박스 1a
- **파일**: `frontend/src/ui/kit.jsx`
- **대체**: `AssistantDrawer.jsx` · `Banners.jsx` · `StatusNotices.jsx` 의 MUI `Alert` 직접 사용 셋,
  그리고 **톤 이름 줄**(안내 · 성공 · 주의 · 오류)
- **소비 화면**: 전 화면(호출부 67곳)
- **규약값**: 면 `background.inset` · 1px `divider` · `RADIUS.sm` · px 14 / py 12(compact 10/7) ·
  아이콘 `remPx(ICON.mark)` 16 + `mt 3px` · 격자 `auto minmax(0,1fr) auto`.
  네 톤이 **같은 면**을 쓰고 아이콘 색만 다르다. **실측**: 면 `#F5F6FB`, 한 줄 상자
  **49.25px**(py 12+12 · 줄상자 24 · 테두리 1+1), compact 36.14px.
- **톤 이름은 아이콘의 접근 이름으로 옮겼다.** 화면 글자로는 안 선다. 예전에는 그 낱말이
  제목 줄로 올라와 ① 한 줄 상자의 높이가 두 배(98px)가 되고 ② 제목 자리를 일반 낱말이
  차지해 진짜 제목을 넣을 곳이 없었다. 색 외 단서(WCAG 1.4.1)는 **모양 넷 + 접근 이름**이
  맡는다. `title` 을 주면 그때만 제목 줄이 선다.

### `Badge` — 면을 가진 갈래
- **파일**: `frontend/src/ui/kit.jsx`
- **대체**: 옛 `strong` 갈래(px 6 · `RADIUS.sm` · 0.875rem · 표지 점 포함)
- **소비 화면**: 전 화면
- **규약값**: 높이 22 · px 8 · `RADIUS.xs`(4) · `FONT_SIZE.micro` 0.75rem / 600 ·
  면과 글자는 `--badge-*` 세트. **면 갈래에는 표지 점이 없다.**
  면이 없는 갈래(표·목록)는 6px 점 + 낱말 그대로. **실측**: 22px, 면 `#E9EDF9`.

### `Tag` — 분류 알약
- **파일**: `frontend/src/ui/kit.jsx`
- **대체**: 옛 태그(높이 20 · 배지와 **같은 옅은 면** · 테두리 없음 · 톤마다 다른 면)
- **소비 화면**: 문서 · 게시판 · 조직도 등 분류를 다는 전 화면
- **규약값**: 높이 `CONTROL.pill` 22 · px 8 · `RADIUS.sm` 6 · **흰 면 `background.paper` +
  1px `divider`** · `FONT_SIZE.micro` 0.75rem. 톤은 **글자만** 받는다.
  **실측**: 22px, `#FFFFFF`, 테두리 `#DCDFEC`, R6.
- 배지와 태그가 **면으로 갈린다**(확정 규약 §9). 예전에는 둘 다 옅은 면이라 한 줄에서
  「계획」 배지와 「Docker」 태그가 같은 부품으로 보였다. `badge-vs-tag.test.jsx` 가 계산된
  면과 테두리를 직접 잰다.

### `FilterChips` — 조건 칩
- **파일**: `frontend/src/ui/FilterBar.jsx` (`CONDITION_CHIP_SX`)
- **대체**: MUI `Chip` 기본 얼굴(중립 회색 필 · 30px · `RADIUS.sm`)
- **소비 화면**: 필터 바를 쓰는 전 목록 화면 · 부품 갤러리
- **규약값**: 높이 `CONTROL.chip` 26 · `RADIUS.full` · 면 `primary.light` · 글자 `primary.dark` ·
  1px `divider` · `FONT_SIZE.caption` 0.8125rem / 600.
  **실측**: 26px, 면 `#EFEDFA`, 글자 `#4742AB`, 모서리 999px.
- 면과 글자를 **강조색 파생**으로 둔다(`primary.light` = 강조색 10% + 판면). 고정 hex 를 쓰면
  보라 이외의 강조색에서 칩만 보라로 남는다. 같은 줄의 「필터 초기화」(30)와 높이가 **다른
  것이 의도**다 — 칩은 표지이고 그 옆은 단추다.

### `ErrorState` — 자리 축과 오류 표지
- **파일**: `frontend/src/ui/kit.jsx`
- **대체**: 자리 축이 **아예 없던** 상태(호출부 87곳 전부가 전면 오류의 크기와 가운데 정렬)
- **소비 화면**: 전 화면. 지금 `layout="region"` 을 쓰는 곳은 부품 갤러리 하나다
- **규약값**: `layout` 은 `EmptyState` 와 같은 어휘(`page` 기본 · `region` · `card` · `inline`).
  `region` 은 왼쪽 정렬 · 위 정렬 · py 28 · 마스코트가 옆에 선다.
  제목 왼쪽에 `ICON.mark` 16 `error.main` 표지(접근 이름 「오류」), 그 아래 원인,
  그 아래 「다시 시도」와 `TechDetail` 접기, 마지막에 문의 번호.

### `SettingRow` — `compact` 갈래
- **파일**: `frontend/src/ui/adminKit.jsx`
- **대체**: 내 프로필의 자체 알림 줄(`py: 0.75` + 굵은 라벨)
- **소비 화면**: 내 프로필(알림 설정 · 방해금지). 관리자 줄은 옛 밀도 그대로
- **규약값**: 이름 `FONT_SIZE.bodySm` 0.875rem / 600 · 설명 `FONT_SIZE.micro` 0.75rem ·
  줄 **위** 1px `rule` · py 10 · gap 12 · **두 줄이 되지 않는다**(말줄임 + `title`).

### `SectionTitle` — 판 제목
- **파일**: `frontend/src/ui/kit.jsx` + `typography.sectionTitle`(`ui/theme.js`)
- **대체**: 옛 1.1875rem / 600
- **소비 화면**: 전 화면
- **규약값**: `FONT_SIZE.cardTitle` 1.0625rem / `FONT_WEIGHT.bold` 700 ·
  설명 `FONT_SIZE.caption` 0.8125rem `text.secondary`.

### `MuiSwitch` — 트랙 치수와 색
- **파일**: `frontend/src/ui/theme.js`
- **대체**: 옛 38x14 트랙 + MUI 기본 반투명 색
- **소비 화면**: 내 프로필(medium). 필터 스위치는 `size="small"` 로 따로 산다
- **규약값**: 트랙 34x20(폭 = 58 − 2x12, 높이 = 34 − 2x7) · 손잡이 흰색 16 · 안쪽 여백 2 ·
  켜짐 이동 14 · 켜짐 `primary.main` · 꺼짐 `dividerStrong`.
  **실측**: 켜짐 `#5A4FCF`, 꺼짐 `#BCC2D9`.

### `AccentPicker` 칩
- **파일**: `frontend/src/screens/settings/AccentPicker.jsx`
- **대체**: 옛 44px 높이 + 2px 테두리 칩
- **소비 화면**: 내 프로필
- **규약값**: `CONTROL.button` 34 · px 12 · `RADIUS.sm` · 색 동그라미 14 ·
  고른 것만 `background.inset` 면 + `primary.main` 테두리 + 체크.

### `UserAvatar` `xl`
- **파일**: `frontend/src/ui/UserAvatar.jsx`
- **대체**: 옛 96px
- **소비 화면**: 내 프로필 신원 머리
- **규약값**: 72px(`4.5rem`).

### 토큰 신설
- **파일**: `frontend/src/ui/theme.js`
- `CONTROL.tableHead/tableRow/tableGroupRow/tableFooter/tableCellDense` = 40/48/36/44/32
  (`tableRow` 는 오래 **정의만 있고 소비처가 0** 이었다 — 44에서 48로 옮기며 배선)
- `palette.rule` = light `#E5E8F3` / dark `#242A46` (`--color-rule`) — 판 **안쪽** 실선
- `ICON.mark` = 16 (다섯째 역할 슬롯)
- `SHADOW.*.raised` = light `0 1px 2px rgba(16,20,40,.10)`
- `FONT_SIZE.cardTitle` = 1.0625rem (여덟째 슬롯)
- `RADIUS.xs` = 4 (다섯째 슬롯)
- `CONTROL.pill` = 22 — 배지의 면 갈래와 태그가 **같은 값**으로 선다(둘은 면으로만 갈린다)
- `CONTROL.chip` = 26 — 조건 칩. 같은 줄의 글자 단추(30)보다 한 단 작다
- `CONTROL.menuItem` = 32 — 팝오버 항목 한 줄. MUI 기본은 48(dense 36)이다.
  `MuiMenuItem` 오버라이드는 `[breakpoints.up("sm")]` 안에서 **한 번 더** 적어야 한다 —
  MUI 의 기본 스타일이 그 미디어에서 `minHeight: auto` 로 되돌리고, 미디어 블록이 평범한
  선언보다 뒤에 실린다(실측: 한 번만 적었을 때 선언 32px / 계산값 0px)

---

## 3. 아직 흡수하지 못한 자체 구현

| 자리 | 파일 | 왜 남았나 | 처리 |
|---|---|---|---|
| 작업 보드 **백로그** 격자 | `screens/WorkBoard.jsx` | 끌어서 순서를 바꾼다. `DataTable` 에 끌기 개념이 없고, `rowWrapper` 로 감싸면 드래그와 60vh 가상화가 함께 깨진다(갈림길 A에서 소유자가 **끌기 우선**으로 확정) | 열 어휘와 치수만 표와 맞춘다. 흡수는 안 한다 |
| 접힘 삼각 `FoldMark` | `screens/MyStats.jsx` | 소비처가 아직 한 곳이다. 둘째 소비처가 생기는 날 `kit.jsx` 로 올린다 | 그때 승격 |
| 신원 사실 줄 `FactLine` · `Dot` | `screens/Profile.jsx` | 같은 이유. 「라벨 없이 값만 잇는 줄」은 상세 화면에도 쓸 자리가 있지만 아직 안 썼다 | 그때 승격 |
| 폼 고정 트랙 `FIELD_ROWS` | `screens/Profile.jsx` | 폼 규약(라벨 20 · 필드 `CONTROL.input` · 도움말 auto)의 첫 소비처다. **5-4 새 티켓**이 같은 트랙을 쓰므로 그때 공용으로 올린다 | 5-4에서 승격 |
| `Chat.jsx` 의 MUI `Alert` | `screens/Chat.jsx` | 메시지 박스 흡수 회차의 범위 밖이었다(채팅은 5-6) | 5-6에서 `Callout` 으로 |
| `kit.jsx` 안의 `MuiAlert` 둘 | `ui/kit.jsx:3351` · `:3458` | 폼 오류 줄과 토스트 알맹이다. 메시지 박스와 **다른 부품**이고 각자 자기 계약이 있다 | 흡수 대상 아님 |
| `StatusKpiStrip` | `ui/StatusKpi.jsx` | 회의 화면이 쓴다 — 세 칸(전체·완료·진행 중)에 「회차 전체의 숫자입니다」 캡션(`note`)을 단 **읽는 줄**이다. `StatusSummaryCard` 는 부분·위험을 함께 말하는 카드라 그 자리에 맞지 않는다(2026-09-14 판단, D-484) | 유지 |
| `ErrorState` 의 판 안 호출부 | 전 화면(87곳) | 자리 축(`layout`)은 생겼지만 기본값은 `page` 다 — 87곳을 한 회차에 뒤집지 않는다. 삼항 형태(`? <ErrorState`)가 31곳이고 그 대부분이 판·패널 안이다 | 화면 회차마다 그 화면 것을 `region` 으로 옮긴다 |
| 모달 머리와 발 | `ui/kit.jsx::ModalHeader` · `ModalFooter` | 제목이 `FONT_SIZE.sectionTitle` 19px / 800 이라 판 제목 규약(1.0625rem / 700)과 두 단 어긋난다. 발 줄은 면도 위 실선도 없다 | 아래 §4 D-11 · D-12 |
| 칸반 카드의 신호 어휘 | `ui/TicketFace.jsx` | 신호를 `variant="mark"`(아이콘만)로 그리고, 우선순위 `긴급` 만 면 있는 배지가 된다 — 한 카드 안에서 어휘가 갈린다 | 아래 §4 D-14 · D-15 |

---

## 4. 갤러리와 시안이 어긋난 자리 (실측)

정본은 갤러리다. 아래 첫 표는 **소유자가 갤러리 쪽으로 확정한** 값이고(시안 문서를 갱신한다),
둘째 표는 아직 판단이 안 난 자리다.

### 확정 — 시안과 다르지만 갤러리가 맞다 (2026-09-08)

| # | 자리 | 시안 | 확정값 | 근거 |
|---|---|---|---|---|
| D-1 | 인라인 버튼 높이 | 28 | **30** (`CONTROL.buttonSm`) | 표 행이 버튼에 끌려 커지지 않게 정한 값이고 제품 전체가 그 값으로 선다 |
| D-5 | 상태 요약 카드의 전체 숫자 | 1.5rem | **1.75rem** (`FONT_SIZE.pageTitle`) | 그 카드를 지배하는 숫자 하나다 |
| D-6 | 검색창 폭 | 320 고정 | **`flex 1 1 20rem` · 최대 32rem** | 좁은 화면에서 320 고정은 도구 줄을 두 줄로 접는다 |
| D-8 | 필터 바 그릇 | `#F5F6FB` 함몰 판 | **판 없음** | 컨트롤이 왼쪽 절반만 쓰는데 판이 전폭이면 빈 판이 된다(지시 80). `FilterBar.jsx` 머리 주석이 실측 근거다 |
| D-9 | 빈 상태와 오류의 마스코트 | 없음 | **표지 크기로 옆에** | 핸드오프 README §10. 시안 문서 두 곳이 서로 달랐고 README 가 맞다 |
| D-10 | 판 제목 | 1.1875rem / 600 | **1.0625rem / 700** (`FONT_SIZE.cardTitle`) | 실측 17px / 700. 시안의 화면 카드도 같은 값이고 대조표 문서만 옛 값을 썼다 |

### 미처리 — 아직 판단이 안 났다

| # | 자리 | 시안 | 실측 | 판단 |
|---|---|---|---|---|
| D-11 | 모달 제목 | 1.0625rem / 700 | **19px / 800** (`FONT_SIZE.sectionTitle` + extrabold) | 미처리. 판 제목 규약과 두 단 어긋난다 |
| D-12 | 모달 발 줄 | 면 `#F5F6FB` + 위 1px, 취소는 흰 면 + 테두리 34 | **면 없음 · 위 선 없음**(몸통의 `dividers` 가 대신한다) · 취소는 ghost(테두리 없음) 34 | 미처리 |
| D-13 | 모달 닫기 | 28 | **30** (`CONTROL.buttonSm`) | 인라인 30 을 유지하기로 한 결정과 같은 값이다 |
| D-16 | 모달 모서리 | 10 | **14** (`RADIUS.lg`) | 떠 있는 것 셋(Menu · Popover · Dialog)이 같은 값을 쓴다 |
| D-17 | 팝오버 모서리 | 8 | **14** (`RADIUS.lg`) | 같은 이유. 그림자는 `--shadow-md` 로 일치한다 |
| D-14 | 칸반 신호 | 점 + 낱말 | **아이콘만**(`TicketSignals variant="mark"`) | 미처리 |
| D-15 | 칸반 우선순위 | 점 + 낱말 | `높음` 은 점 + 낱말, **`긴급` 만 면 있는 배지** (`Badge` 규칙 ③: 목록 밖 danger 는 면을 갖는다) | 미처리. 한 카드 안에서 어휘가 갈린다 |
| D-18 | 칸반 카드 여백 | 12 14, 줄 사이 8, 발 위 1px | **10, 줄 사이 4, 발 선 없음** | 미처리 |
| D-19 | 태그 굵기 | 400 | **500** (`FONT_WEIGHT.medium`) | 요청 범위 밖이라 안 건드렸다 |
| D-20 | 조건 칩 글자색 | `#4038B8` | **`#4742AB`** (`primary.dark`) | 강조색 파생이라 사용자 강조색을 따라간다. 고정 hex 로 안 되돌린다 |
