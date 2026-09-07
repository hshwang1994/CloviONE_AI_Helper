# 부품 대장 — 확정 규약 핸드오프 (2~5단계)

**정본**: `frontend/src/ui/**` · `frontend/src/screens/**` Source
**대조표**: `/kit` (`frontend/src/screens/dev/KitGallery.jsx`) — 실제 부품을 불러 쓴다
**측정**: 2026-09-08, 1920x1080 light 캡처 실측 (`dist/ui-qa/kit-gallery-r2/`)

이 문서가 답하는 것 하나: **「이 모양을 어디서 고치나」**. 부품마다 이름 · 파일 · 무엇을
대체했는지 · 어느 화면이 쓰는지 · 규약값 네 가지를 적는다. `03_COMPONENT.md` 는 전환 계획의
자산 목록이고 이쪽은 확정 규약의 **치수 대장**이다 — 역할이 다르다.

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
- **소비 화면**: 홈 · 내 업무량 · 작업 보드 · 부품 갤러리 (`StatusKpiStrip` 은 회의가 계속 쓴다)
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

### `KitGallery`
- **파일**: `frontend/src/screens/dev/KitGallery.jsx` (라우트 `/kit`)
- **대체**: 없음(신설). 부품을 확인하려면 그 부품을 쓰는 화면을 하나씩 열어야 했다
- **소비 화면**: 자기 자신(개발용). 사이드바 항목 없음
- **규약값**: 없음 — **값을 한 줄도 안 적는 것이 이 화면의 계약**이다. 모든 견본이 실제 부품을
  `import` 한다.

---

## 2. 규약을 옮긴 부품 (모양이 바뀐 기존 부품)

### `Callout` — 메시지 박스 1a
- **파일**: `frontend/src/ui/kit.jsx`
- **대체**: `AssistantDrawer.jsx` · `Banners.jsx` · `StatusNotices.jsx` 의 MUI `Alert` 직접 사용 셋
- **소비 화면**: 전 화면(호출부 67곳)
- **규약값**: 면 `background.inset` · 1px `divider` · `RADIUS.sm` · px 14 / py 12(compact 10/7) ·
  아이콘 `remPx(ICON.mark)` 16 + `mt 3px` · 격자 `auto minmax(0,1fr) auto`.
  네 톤이 **같은 면**을 쓰고 아이콘 색만 다르다. **실측**: 면 `#F5F6FB`.

### `Badge` — 면을 가진 갈래
- **파일**: `frontend/src/ui/kit.jsx`
- **대체**: 옛 `strong` 갈래(px 6 · `RADIUS.sm` · 0.875rem · 표지 점 포함)
- **소비 화면**: 전 화면
- **규약값**: 높이 22 · px 8 · `RADIUS.xs`(4) · `FONT_SIZE.micro` 0.75rem / 600 ·
  면과 글자는 `--badge-*` 세트. **면 갈래에는 표지 점이 없다.**
  면이 없는 갈래(표·목록)는 6px 점 + 낱말 그대로. **실측**: 22px, 면 `#E9EDF9`.

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
| `StatusKpiStrip` | `ui/StatusKpi.jsx` | 회의 화면이 아직 쓴다. `StatusSummaryCard` 가 그 자리를 대체할 수 있는지는 회의 화면을 볼 때 판단한다 | 미정 |
| 필터 칩 | `ui/FilterBar.jsx::FilterChips` | MUI `Chip` 을 그대로 쓴다 — 확정 규약의 칩 치수(26 · `RADIUS.full` · 옅은 면)로 안 옮겼다 | 미처리 (아래 대조표 D-8) |
| `Tag` | `ui/kit.jsx` | 확정 규약 §9의 태그(22 · `RADIUS.sm` · **흰 면 + 1px 테두리**)와 다르다 | 미처리 (D-5) |
