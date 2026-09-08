import React from "react";
import Box from "@mui/material/Box";
import MenuList from "@mui/material/MenuList";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import MenuItem from "@mui/material/MenuItem";

import {
  Badge, Button, Callout, Card, DataTable, EmptyState, ErrorState, FieldLabel,
  FlatBadgeSurface, ModalBody, ModalFooter, ModalHeader, OverflowMenu, PageHeader,
  SectionTitle, Segmented, Skeleton, Surface, SurfaceReset, Tag, overflowMenuItems, useToast,
} from "../../ui/kit.jsx";
import {
  FilterChips, FilterRow, FilterSurface, ResultLine, ToolbarEnd, ToolbarRow, TOOLBAR_SEARCH_SX,
} from "../../ui/FilterBar.jsx";
import { StatusSummaryCard } from "../../ui/StatusKpi.jsx";
import { TicketFace } from "../../ui/TicketFace.jsx";
import { SIGNALS } from "../../lib/ticketSignals.js";
import { CONTROL, FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, RADIUS, remPx } from "../../ui/theme.js";
import { GRID_GAP, LANE_SURFACE } from "../../ui/density.js";

/* 부품 갤러리 — **제품 화면이 아니라 개발용 대조표**다.
 *
 * ## 왜 필요한가
 *
 * 확정 규약(높이 34 · Radius 6 · Border 1px)이 맞는지 확인하려면 지금까지는 부품을 쓰는
 * 화면을 하나씩 열어야 했다. 그러면 세 가지를 못 본다: 부품끼리 나란히 놓았을 때의 **높이
 * 리듬**, 어느 화면도 안 쓰는 **상태**(비활성 · 오류 · 0건), 그리고 **떠 있는 것**(팝오버 ·
 * 모달) — 마지막 것은 열어야 보이므로 어떤 캡처에도 안 잡혔다. 이 화면이 셋을 한 판에 세운다.
 *
 * ## 🔴 여기서는 값을 베끼지 않는다
 *
 * 시안의 치수를 손으로 옮겨 그리면 이 화면은 **시안의 사본**이 되고, 실제 부품이 시안과
 * 다른 곳은 영영 안 보인다 — 대조표가 대조를 못 하는 것이다. 그래서 모든 견본은
 * `ui/kit.jsx` 와 `ui/*` 의 부품을 그대로 `import` 해서 렌더한다. 이 파일에 있는 치수는
 * 견본을 **배치**하는 값(줄 간격 따위)뿐이고, 부품 안쪽 치수는 한 줄도 안 적는다.
 * 예외는 아래 §13 의 hover 견본 둘뿐이고, 그 자리에 이유를 적어 두었다.
 *
 * ## 이 화면이 정본이다
 *
 * 시안 HTML 과 값이 어긋나면 **여기가 맞다**(소유자 확정, 2026-09-08). 시안 문서는 참고로
 * 남고, 어긋난 자리는 그때마다 실측과 함께 보고한다.
 *
 * 섹션 순서는 `리디자인 시안 - 공통 컴포넌트.dc.html` 과 같다(그 문서에 없는 절은 제목에
 * 그렇게 적어 둔다).
 */

/* 견본 하나를 감싸는 자리 — 이름표 + 견본. 이름표는 시안의 소제목과 같은 등급이다. */
function Sample({ label, children, sx }) {
  return (
    <Box sx={{ display: "grid", rowGap: 1, minWidth: 0, alignContent: "start", ...sx }}>
      <Typography
        component="span" color="text.secondary"
        sx={{ fontSize: FONT_SIZE.micro, fontWeight: FONT_WEIGHT.semibold, letterSpacing: "0.06em", ...KO_WORD_BREAK }}
      >
        {label}
      </Typography>
      {children}
    </Box>
  );
}

/* 섹션 하나 — 제목 · 설명 · **부품 이름과 파일 경로** · 견본들.
 *
 * 경로를 적는 것이 이 화면의 절반이다. 「이 모양을 어디서 고치나」에 답이 없으면 대조표를
 * 봐도 할 수 있는 일이 없다. */
function GallerySection({ title, help, parts, children }) {
  return (
    <Card sx={{ display: "grid", rowGap: 2, minWidth: 0 }}>
      <SectionTitle component="h2" sx={{ mb: 0 }} title={title} help={help} />
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
        {parts.map((p) => (
          <Box
            key={p.path + p.name}
            sx={{
              display: "inline-flex", alignItems: "center", gap: 1,
              px: 1, height: remPx(CONTROL.buttonSm),
              border: 1, borderColor: "divider", borderRadius: `${RADIUS.sm}px`,
              bgcolor: "background.inset",
            }}
          >
            <Typography component="code" sx={{ fontSize: FONT_SIZE.micro, fontWeight: FONT_WEIGHT.semibold }}>
              {p.name}
            </Typography>
            <Typography component="code" color="text.secondary" sx={{ fontSize: FONT_SIZE.micro }}>
              {p.path}
            </Typography>
          </Box>
        ))}
      </Box>
      {children}
    </Card>
  );
}

/* 떠 있는 것을 **붙박이로** 세우는 자리. 팝오버와 모달은 캔버스 위에 뜨므로 캔버스 색
   구역을 만들어 그 위에 놓는다 — 흰 판 위에 놓으면 그림자와 테두리가 안 읽힌다. */
const FLOAT_STAGE = {
  bgcolor: "background.canvas",
  borderRadius: `${RADIUS.md}px`,
  p: 2.5,
  display: "flex",
  flexWrap: "wrap",
  gap: 2.5,
  alignItems: "flex-start",
};

const MENU_ITEMS = [
  { key: "open", label: "상세 열기" },
  { key: "edit", label: "수정" },
  { key: "copy", label: "링크 복사" },
  { key: "del", label: "삭제", tone: "danger" },
];

const TABLE_COLUMNS = [
  { key: "tid", label: "티켓", type: "identifier" },
  { key: "title", label: "제목", type: "title" },
  { key: "status", label: "상태", type: "status", render: (r) => <Badge value={r.status} /> },
  { key: "priority", label: "우선순위", type: "enum" },
  { key: "signal", label: "신호", type: "status", render: (r) => (r.signal ? <Badge value={r.signal} kind="danger" /> : null) },
  { key: "est", label: "예상 WD", type: "number" },
  { key: "due", label: "마감", type: "date" },
  { key: "act", label: "동작", type: "actions", render: () => <Button size="sm">수정</Button> },
];

const TABLE_ROWS = [
  { id: "1", group: "인프라 정비", tid: "HRXPZY-8", title: "자원 등록 화면 예외 처리", status: "계획", priority: "높음", signal: "지연", est: "2", due: "2026-08-20" },
  { id: "2", group: "인프라 정비", tid: "HRXPZY-7", title: "백업 스크립트 점검", status: "진행 중", priority: "높음", signal: "", est: "1.5", due: "2026-08-24" },
  { id: "3", group: "포털 개편", tid: "JBBCYU-6", title: "사용자 대시보드 기획", status: "검증", priority: "보통", signal: "", est: "3", due: "2026-08-23" },
];

/* 칸반 카드 견본 둘. `TicketFace` 가 읽는 모양 그대로다 — 값만 여기서 만든다.
   둘째는 담당자가 없고 지연이 걸린 카드다(그 둘이 카드에서 가장 자주 어긋나는 자리다). */
const BOARD_CARDS = [
  {
    id: "b1",
    key: "HRXPZY-189",
    title: "자원 등록 화면 예외 처리와 재시도 안내",
    project: "포털 개편",
    due: "2026-09-11",
    est_wd: 4,
    priority: "high",
    assignees: [{ display_name: "김정미" }],
  },
  {
    id: "b2",
    key: "JBBCYU-15",
    title: "모니터링 수집 주기 정리",
    project: "인프라 정비",
    due: "2026-08-02",
    est_wd: 2,
    priority: "urgent",
    assignees: [],
    assignee_tokens: 0,
  },
];

export function KitGallery() {
  const toast = useToast();
  const [view, setView] = React.useState("board");
  const [mine, setMine] = React.useState(true);
  const [status, setStatus] = React.useState("plan");

  return (
    <div className="c-screen">
      <PageHeader
        area="개발"
        title="공통 부품 갤러리"
        crumbRoot=""
        description="확정 규약과 실제 부품을 나란히 놓고 봅니다. 모든 견본이 실제 부품을 그대로 불러 쓰므로, 값을 베낀 그림이 아닙니다."
      />

      <Box sx={{ display: "grid", gap: GRID_GAP, minWidth: 0 }}>
        {/* ── 1. 버튼 ─────────────────────────────────────────────── */}
        <GallerySection
          title="버튼"
          help="한 화면에 primary 는 하나입니다. 나머지는 default 와 ghost 로 내려갑니다. 파괴적 동작은 채운 면을 안 씁니다."
          parts={[
            { name: "Button", path: "ui/kit.jsx" },
            { name: "OverflowMenu", path: "ui/kit.jsx" },
          ]}
        >
          <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 1.25 }}>
            <Button variant="primary">스프린트 추가</Button>
            <Button>티켓 추가</Button>
            <Button variant="ghost">전체 보기</Button>
            <Button variant="danger">나가기</Button>
            <Button disabled>다음 회차</Button>
            <Box aria-hidden="true" sx={{ width: "1px", height: "1.625rem", bgcolor: "divider" }} />
            <Button size="sm">수정</Button>
            <OverflowMenu items={MENU_ITEMS} />
            <Button variant="primary" loading>저장 중</Button>
          </Box>
        </GallerySection>

        {/* ── 2. 버튼 크기 스케일 ─────────────────────────────────── */}
        <GallerySection
          title="버튼 크기"
          help="두 단계뿐입니다. 페이지 동작과 인라인 동작이고, 인라인이 작은 이유는 표 행이 버튼에 끌려 커지지 않게 하기 위해서입니다."
          parts={[{ name: "CONTROL.button / CONTROL.buttonSm", path: "ui/theme.js" }]}
        >
          <Box sx={{ display: "grid", gridTemplateColumns: "8rem minmax(0, 1fr)", columnGap: 2.5, rowGap: 1.75, alignItems: "center" }}>
            <Typography sx={{ fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.semibold }}>
              {`${CONTROL.button}px 페이지 동작`}
            </Typography>
            <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
              <Button variant="primary">스프린트 추가</Button>
              <Button>티켓 추가</Button>
              <Typography color="text.secondary" sx={{ fontSize: FONT_SIZE.micro }}>헤더와 모달 발과 필터 바</Typography>
            </Box>
            <Typography sx={{ fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.semibold }}>
              {`${CONTROL.buttonSm}px 인라인 동작`}
            </Typography>
            <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
              <Button size="sm">수정</Button>
              <Button size="sm" variant="ghost">보기</Button>
              <Typography color="text.secondary" sx={{ fontSize: FONT_SIZE.micro }}>표 행과 칸반 카드와 메시지 박스 오른쪽</Typography>
            </Box>
          </Box>
        </GallerySection>

        {/* ── 3. 검색과 필터 바 ───────────────────────────────────── */}
        <GallerySection
          title="검색과 필터 바"
          help="이 자리는 판이 아닙니다. 캔버스 위에 놓이고 목록과의 경계는 결과 줄과 아래 실선이 만듭니다."
          parts={[
            { name: "FilterSurface / ToolbarRow / FilterRow", path: "ui/FilterBar.jsx" },
            { name: "ResultLine / FilterChips", path: "ui/FilterBar.jsx" },
          ]}
        >
          <FilterSurface divider={false}>
            <ToolbarRow>
              <TextField size="small" placeholder="티켓 제목, 이름 검색" sx={TOOLBAR_SEARCH_SX} />
              <ToolbarEnd>
                <Box sx={{ display: "inline-flex", alignItems: "center", gap: 1 }}>
                  <Switch
                    checked={mine}
                    onChange={(e) => setMine(e.target.checked)}
                    slotProps={{ input: { "aria-label": "내 티켓만" } }}
                  />
                  <Typography sx={{ fontSize: FONT_SIZE.caption }}>내 티켓만</Typography>
                </Box>
                <Button size="sm">상세 필터</Button>
              </ToolbarEnd>
            </ToolbarRow>
            <FilterRow>
              <TextField size="small" select label="프로젝트" value="all" InputLabelProps={{ shrink: true }} sx={{ minWidth: "12rem" }}>
                <MenuItem value="all">전체</MenuItem>
              </TextField>
              <TextField
                size="small" select label="상태" value={status} InputLabelProps={{ shrink: true }}
                onChange={(e) => setStatus(e.target.value)}
                sx={{ minWidth: "10rem" }}
              >
                <MenuItem value="plan">계획</MenuItem>
                <MenuItem value="doing">진행 중</MenuItem>
              </TextField>
              <TextField size="small" select label="담당자" value="me" InputLabelProps={{ shrink: true }} sx={{ minWidth: "10rem" }}>
                <MenuItem value="me">나</MenuItem>
              </TextField>
            </FilterRow>
            <ResultLine total={21} conditions={["담당자", "스프린트"]} />
            <FilterChips
              items={[
                { key: "assignee", label: "담당자 나", onDelete: () => {} },
                { key: "sprint", label: "스프린트 9월 첫째 주", onDelete: () => {} },
              ]}
              onClearAll={() => {}}
            />
          </FilterSurface>
        </GallerySection>

        {/* ── 4. 세그먼티드 ───────────────────────────────────────── */}
        <GallerySection
          title="세그먼티드 (시안 문서에 없는 절, 확정 규약 §2)"
          help="서로 배타적인 값이 셋 이하일 때 씁니다. 지금 무엇을 보고 있는지가 목록을 열지 않아도 읽힙니다."
          parts={[{ name: "Segmented", path: "ui/kit.jsx" }]}
        >
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 3, alignItems: "flex-start" }}>
            <Sample label="뷰 전환">
              <Segmented
                ariaLabel="뷰"
                value={view}
                onChange={setView}
                options={[{ value: "board", label: "칸반" }, { value: "backlog", label: "백로그" }]}
              />
            </Sample>
            <Sample label="개수를 함께">
              <Segmented
                ariaLabel="기간"
                value={view}
                onChange={setView}
                options={[
                  { value: "board", label: "전체", count: 21 },
                  { value: "backlog", label: "내 것", count: 4 },
                ]}
              />
            </Sample>
          </Box>
        </GallerySection>

        {/* ── 5. 팝오버와 모달 ────────────────────────────────────── */}
        <GallerySection
          title="팝오버와 모달"
          help="둘 다 떠 있고, 뜬 것만 그림자를 갖습니다. 팝오버는 머리 없이 항목 목록이고 모달은 머리와 몸과 발의 3단입니다."
          parts={[
            { name: "overflowMenuItems / OverflowMenu", path: "ui/kit.jsx" },
            { name: "Surface tone=overlay, modal", path: "ui/kit.jsx" },
            { name: "ModalHeader / ModalBody / ModalFooter", path: "ui/kit.jsx" },
          ]}
        >
          {/* 🔴 **왜 진짜 `Modal` 과 `Menu` 를 안 여는가.** 둘 다 포털로 화면 맨 위에 뜨고
              뒤에 막을 깐다 — 캡처에는 이 페이지가 아니라 «막에 덮인 페이지 + 가운데 상자»
              하나만 남는다. 그래서 **떠 있게 만드는 껍데기만** 이 자리에서 대신 세우고,
              그 안의 내용은 제품이 쓰는 바로 그 부품을 부른다: 항목 목록은
              `overflowMenuItems`(`OverflowMenu` 가 여는 것과 같은 함수), 모달의 세 단은
              `ModalHeader`/`ModalBody`/`ModalFooter`, 면과 그림자는 `Surface` 의 두 톤이다.
              껍데기가 다르므로 모서리만 실제와 다를 수 있다 — 그 차이는 대장에 적는다. */}
          <Box sx={FLOAT_STAGE}>
            <Sample label="팝오버, 동작 목록">
              <Surface tone="overlay" sx={{ width: "16rem", py: 0.5 }}>
                <MenuList disablePadding>{overflowMenuItems(MENU_ITEMS)}</MenuList>
              </Surface>
            </Sample>

            <Sample label="모달, 머리와 몸과 발">
              <Surface tone="modal" sx={{ width: "28rem", overflow: "hidden" }}>
                <ModalHeader title="스프린트 추가" onClose={() => {}} />
                <ModalBody>
                  <Box sx={{ display: "grid", rowGap: 1.75 }}>
                    <Box>
                      <FieldLabel htmlFor="kg-sprint-name" required>회차 이름</FieldLabel>
                      <TextField id="kg-sprint-name" size="small" fullWidth defaultValue="9월 둘째 주" />
                    </Box>
                    <Callout tone="info">진행 중인 회차가 있으면 새 회차는 대기 상태로 만들어집니다.</Callout>
                  </Box>
                </ModalBody>
                <ModalFooter onCancel={() => {}} onSubmit={() => {}} submitLabel="회차 추가" />
              </Surface>
            </Sample>

            <Sample label="확인 모달, 파괴적">
              <Surface tone="modal" sx={{ width: "24rem", overflow: "hidden" }}>
                <ModalHeader title="채팅방에서 나갑니다" onClose={() => {}} />
                <ModalBody>
                  나가면 이 방의 지난 대화를 더 볼 수 없습니다. 다시 초대받으면 들어올 수 있습니다.
                </ModalBody>
                <ModalFooter onCancel={() => {}} onSubmit={() => {}} submitLabel="나가기" submitVariant="dangerConfirm" />
              </Surface>
            </Sample>
          </Box>
        </GallerySection>

        {/* ── 6. 칸반 카드 ────────────────────────────────────────── */}
        <GallerySection
          title="칸반 카드"
          help="읽는 순서는 티켓 키와 신호, 제목, 프로젝트, 마감과 담당자입니다. 신호는 점과 낱말로만 말하고 색 테두리를 쓰지 않습니다."
          parts={[
            { name: "TicketFace / TicketPeople", path: "ui/TicketFace.jsx" },
            { name: "TicketSignals", path: "ui/TicketSignals.jsx" },
            { name: "LANE_SURFACE", path: "ui/density.js" },
          ]}
        >
          {/* 🔴 `SurfaceReset` 이 없으면 카드가 **테두리도 여백도 없이** 그려진다.
              「판 안에 판을 그리지 않는다」 규칙이 `Card` 를 자동으로 `none` 으로 내리는데,
              이 갤러리에서는 섹션 자체가 판이라 그 규칙이 걸린다. 실제 작업 보드에서는 레인이
              캔버스 위에 있어 depth 가 0 이다 — 여기서도 그 자리를 그대로 만들어 준다.
              대조표가 «실제와 다른 얼굴»을 보여 주면 대조표가 아니다. */}
          <SurfaceReset>
            <Box sx={{ ...LANE_SURFACE, p: 2.5, display: "flex", flexWrap: "wrap", gap: 1.75, alignItems: "flex-start" }}>
              <TicketFace card={BOARD_CARDS[0]} signals={[]} sx={{ width: "17.5rem" }} />
              <TicketFace card={BOARD_CARDS[1]} signals={[SIGNALS.overdue]} sx={{ width: "17.5rem" }} />
            </Box>
          </SurfaceReset>
        </GallerySection>

        {/* ── 7. 상태 요약 카드 ───────────────────────────────────── */}
        <GallerySection
          title="상태 요약 카드"
          help="전체를 남김없이 나눈 부분만 비율을 갖습니다. 서로 겹치는 신호는 같은 바에 넣지 않습니다."
          parts={[
            { name: "StatusSummaryCard", path: "ui/StatusKpi.jsx" },
            { name: "StatusKpiStrip", path: "ui/StatusKpi.jsx" },
          ]}
        >
          <StatusSummaryCard
            ariaLabel="상태 요약"
            total="179"
            totalLabel="전체"
            items={[
              { key: "plan", label: "계획", value: "151" },
              { key: "doing", label: "진행 중", value: "21" },
              { key: "verify", label: "검증", value: "7" },
              { key: "done", label: "완료", value: "0" },
              { key: "hold", label: "보류", value: "0" },
              { key: "cancel", label: "취소", value: "0" },
            ]}
            risks={[
              { key: "overdue", label: "지연", value: "16", kind: "warn" },
              { key: "issue", label: "이슈", value: "9", kind: "danger" },
            ]}
          />
        </GallerySection>

        {/* ── 8. 데이터 표 ────────────────────────────────────────── */}
        <GallerySection
          title="데이터 표"
          help="머리 줄은 회색 면과 아래 실선이고, 몸통은 제목만 왼쪽이며 나머지는 전부 가운데입니다. 표 안의 상태는 점과 낱말입니다."
          parts={[
            { name: "DataTable", path: "ui/kit.jsx" },
            { name: "COLUMN_TYPES", path: "ui/columnTypes.js" },
          ]}
        >
          <DataTable
            columns={TABLE_COLUMNS}
            rows={TABLE_ROWS}
            rowKey={(r) => r.id}
            groupOf={(r) => r.group}
            total={21}
          />
        </GallerySection>

        {/* ── 9. 배지와 태그와 점 어휘 ────────────────────────────── */}
        <GallerySection
          title="배지와 태그와 점 어휘"
          help="배지는 상태이고 태그는 분류입니다. 둘은 면으로 갈립니다. 배지는 옅은 면이고 태그는 흰 면에 테두리입니다."
          parts={[
            { name: "Badge / Tag / FlatBadgeSurface", path: "ui/kit.jsx" },
            { name: "CONTROL.pill", path: "ui/theme.js" },
          ]}
        >
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 3, alignItems: "flex-start" }}>
            <Sample label="배지, 면을 쓰는 자리(카드 머리와 상세)">
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
                <Badge value="계획" emphasis="strong" />
                <Badge value="진행 중" emphasis="strong" />
                <Badge value="완료" kind="ok" emphasis="strong" />
                <Badge value="지연" kind="warn" emphasis="strong" />
                <Badge value="차단됨" kind="danger" emphasis="strong" />
              </Box>
            </Sample>
            <Sample label="태그, 분류">
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
                <Tag label="ClovirONE" />
                <Tag label="Docker" />
                <Tag label="Linux" tone="teal" />
                <Tag label="Nginx" tone="purple" />
              </Box>
            </Sample>
            <Sample label="표와 목록 안, 점과 낱말">
              <FlatBadgeSurface>
                <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.75 }}>
                  <Badge value="계획" />
                  <Badge value="진행 중" />
                  <Badge value="지연" kind="warn" />
                  <Badge value="차단됨" kind="danger" />
                </Box>
              </FlatBadgeSurface>
            </Sample>
          </Box>
        </GallerySection>

        {/* ── 10. 폼 필드 ────────────────────────────────────────── */}
        <GallerySection
          title="폼 필드"
          help="라벨은 필드 위입니다. 떠 있는 노치 라벨을 안 쓰므로 값이 있는 칸과 빈 칸의 라벨 자리가 같습니다."
          parts={[
            { name: "FieldLabel", path: "ui/kit.jsx" },
            { name: "FormField", path: "ui/kit.jsx" },
            { name: "CONTROL.input", path: "ui/theme.js" },
          ]}
        >
          <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(16rem, 1fr))", gap: 2 }}>
            <Box>
              <FieldLabel htmlFor="kg-title" required>제목</FieldLabel>
              <TextField
                id="kg-title" size="small" fullWidth
                defaultValue="자원 등록 화면 예외 처리"
                helperText="한 줄로 무슨 일인지 알 수 있게 씁니다."
              />
            </Box>
            <Box>
              <FieldLabel htmlFor="kg-wd">예상 WD</FieldLabel>
              <TextField id="kg-wd" size="small" fullWidth error defaultValue="0" helperText="1 이상을 넣어 주세요." />
            </Box>
            <Box>
              <FieldLabel htmlFor="kg-assignee">담당자</FieldLabel>
              <TextField id="kg-assignee" size="small" select fullWidth value="me" helperText=" ">
                <MenuItem value="me">나</MenuItem>
              </TextField>
            </Box>
            <Box>
              <FieldLabel htmlFor="kg-off">비활성, 값을 정할 수 없을 때</FieldLabel>
              <TextField
                id="kg-off" size="small" fullWidth disabled defaultValue=""
                helperText="회차를 먼저 고르세요. 막는 이유는 빈 칸 안이 아니라 이 줄에 씁니다."
              />
            </Box>
          </Box>
        </GallerySection>

        {/* ── 11. 빈 상태와 오류와 로딩과 토스트 ──────────────────── */}
        <GallerySection
          title="빈 상태와 오류와 로딩과 토스트"
          help="판 안에서는 왼쪽 정렬에 위 정렬입니다. 가운데로 서는 것은 화면 전체가 비었을 때뿐입니다."
          parts={[
            { name: "EmptyState / ErrorState / Skeleton", path: "ui/kit.jsx" },
            { name: "ToastProvider / useToast", path: "ui/kit.jsx" },
          ]}
        >
          {/* 넷을 한 줄에 넣으면 칸이 좁아 제목이 두 줄로 접힌다 — 실제 화면에서 이 부품이
              서는 폭이 아니다. 두 칸으로 두고, 각 판은 `alignContent: start` 로 내용을 위에
              붙인다(넷이 저마다 다른 높이로 가운데에 서면 한 줄이 계단으로 읽힌다). */}
          <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(34rem, 1fr))", gap: 2 }}>
            {[
              {
                label: "빈 상태, 판 안",
                node: (
                  <EmptyState
                    art="tickets"
                    title="표시할 항목이 없습니다"
                    situation="조건에 맞는 티켓이 없습니다."
                    help="조건을 지우면 전체를 볼 수 있습니다."
                  />
                ),
              },
              {
                label: "오류 상태, 판 안",
                node: (
                  <ErrorState
                    layout="region"
                    error={Object.assign(new Error("NetworkError: Failed to fetch"), { status: 503, requestId: "7f3a91c4" })}
                    onRetry={() => {}}
                  />
                ),
              },
              { label: "로딩, 스켈레톤", node: <Skeleton lines={4} /> },
              {
                label: "토스트, 한 번 뜨고 사라진다",
                node: (
                  <Box sx={{ display: "grid", rowGap: 1, justifyItems: "start" }}>
                    <Box sx={{ display: "flex", gap: 1 }}>
                      <Button size="sm" onClick={() => toast("티켓을 저장했습니다.", "success")}>성공 토스트</Button>
                      <Button size="sm" onClick={() => toast("저장하지 못했습니다.", "error")}>오류 토스트</Button>
                    </Box>
                    <Typography color="text.secondary" sx={{ fontSize: FONT_SIZE.micro, ...KO_WORD_BREAK }}>
                      토스트는 화면 밖에서 떠오르므로 이 판에 붙박이로 그릴 수 없습니다. 눌러서 확인합니다.
                    </Typography>
                  </Box>
                ),
              },
            ].map((s) => (
              <Box
                key={s.label}
                sx={{
                  display: "grid", alignContent: "start", minWidth: 0,
                  border: 1, borderColor: "divider", borderRadius: `${RADIUS.md}px`, p: 2.25,
                }}
              >
                <Sample label={s.label}>{s.node}</Sample>
              </Box>
            ))}
          </Box>
        </GallerySection>

        {/* ── 12. 메시지 박스 1a ─────────────────────────────────── */}
        <GallerySection
          title="메시지 박스 1a"
          help="바탕과 테두리는 네 상태가 같고 아이콘 모양과 색만 상태를 말합니다. 제목 자리는 비워 두고 할 말이 있을 때만 씁니다."
          parts={[{ name: "Callout", path: "ui/kit.jsx" }]}
        >
          <Box sx={{ display: "grid", rowGap: 1.25 }}>
            <Callout tone="info">진행 중인 회차가 없습니다.</Callout>
            <Callout tone="ok">티켓을 저장했습니다.</Callout>
            <Callout tone="warn" action={<Button size="sm">항목 보기</Button>}>
              소속을 판정할 수 없는 항목이 64건 있습니다.
            </Callout>
            <Callout tone="danger" detail="NetworkError: Failed to fetch (request 7f3a)">
              티켓을 불러오지 못했습니다.
            </Callout>
            <Callout tone="warn" title="이 회차는 이미 닫혔습니다">
              닫힌 회차의 티켓은 읽기만 할 수 있습니다. 다시 열려면 관리자에게 요청하세요.
            </Callout>
            <Callout tone="info" compact>좁은 자리를 위한 compact 갈래입니다.</Callout>
          </Box>
        </GallerySection>

        {/* ── 13. 조작기의 상태 ──────────────────────────────────── */}
        <GallerySection
          title="조작기의 상태 (시안 문서에 없는 절)"
          help="기본만 보면 규약을 반만 본 것입니다. 초점과 비활성과 오류와 선택까지 한 줄에 세워야 어긋난 자리가 보입니다."
          parts={[
            { name: "Button / DataTable / Switch", path: "ui/kit.jsx" },
            { name: "MuiButtonBase Mui-focusVisible", path: "ui/theme.js" },
          ]}
        >
          {/* 🔴 **상태를 캡처에 남기는 법.** 이 제품은 초점과 비활성과 선택을 **클래스**로
              그린다(`Mui-focusVisible` · `Mui-disabled` · `Mui-selected`). 그래서 그 클래스를
              그대로 얹으면 실제 규칙이 그대로 적용된다 — 값을 베끼지 않는다.
              hover 만 예외다. `:hover` 는 포인터가 실제로 올라가야 켜지는 상태라 정지 화면에
              존재할 수 없다. 아래 두 견본에서만 그 규칙이 쓰는 **같은 토큰 이름**
              (`primary.dark` · `action.hover` · `text.secondary`)을 직접 부른다 — 이 파일이
              무언가를 다시 적는 유일한 자리이고, 적은 것은 값이 아니라 토큰 이름이다. */}
          <Box sx={{ display: "grid", rowGap: 2.5 }}>
            <Sample label="주 버튼, 기본과 마우스 올림과 초점과 비활성">
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.25, alignItems: "center" }}>
                <Button variant="primary">저장</Button>
                <Button variant="primary" sx={{ bgcolor: "primary.dark" }}>마우스 올림</Button>
                <Button variant="primary" className="Mui-focusVisible">초점</Button>
                <Button variant="primary" disabled>비활성</Button>
              </Box>
            </Sample>

            <Sample label="보조 버튼, 같은 넷">
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.25, alignItems: "center" }}>
                <Button>취소</Button>
                <Button sx={{ bgcolor: "action.hover", borderColor: "text.secondary" }}>마우스 올림</Button>
                <Button className="Mui-focusVisible">초점</Button>
                <Button disabled>비활성</Button>
              </Box>
            </Sample>

            <Sample label="입력, 기본과 초점과 오류와 비활성">
              <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(13rem, 1fr))", gap: 2 }}>
                <Box>
                  <FieldLabel htmlFor="kg-st-normal">기본</FieldLabel>
                  <TextField id="kg-st-normal" size="small" fullWidth defaultValue="9월 둘째 주" />
                </Box>
                <Box>
                  <FieldLabel htmlFor="kg-st-focus">초점</FieldLabel>
                  <TextField id="kg-st-focus" size="small" fullWidth defaultValue="9월 둘째 주" InputProps={{ className: "Mui-focused" }} />
                </Box>
                <Box>
                  <FieldLabel htmlFor="kg-st-error">오류</FieldLabel>
                  <TextField id="kg-st-error" size="small" fullWidth error defaultValue="0" helperText="1 이상을 넣어 주세요." />
                </Box>
                <Box>
                  <FieldLabel htmlFor="kg-st-off">비활성</FieldLabel>
                  <TextField id="kg-st-off" size="small" fullWidth disabled defaultValue="회차 없음" />
                </Box>
              </Box>
            </Sample>

            <Sample label="표 행, 마우스 올림과 선택은 같은 한 단계입니다">
              <DataTable
                columns={TABLE_COLUMNS.slice(0, 4)}
                rows={TABLE_ROWS}
                rowKey={(r) => r.id}
                rowSelected={(r) => r.id === "2"}
                onRow={() => {}}
              />
            </Sample>

            <Sample label="조건 칩과 토글, 켬과 끔과 비활성">
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 3, alignItems: "center" }}>
                <FilterChips
                  items={[{ key: "assignee", label: "담당자 나", onDelete: () => {} }]}
                  onClearAll={() => {}}
                />
                <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
                  <Switch defaultChecked slotProps={{ input: { "aria-label": "켬" } }} />
                  <Switch defaultChecked={false} slotProps={{ input: { "aria-label": "끔" } }} />
                  <Switch checked disabled slotProps={{ input: { "aria-label": "켬, 비활성" } }} />
                  <Switch checked={false} disabled slotProps={{ input: { "aria-label": "끔, 비활성" } }} />
                </Box>
              </Box>
            </Sample>
          </Box>
        </GallerySection>
      </Box>
    </div>
  );
}

export default KitGallery;
