import React from "react";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuList from "@mui/material/MenuList";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import {
  ActionFooter, Badge, Button, Callout, Card, CountChip, DataTable, DotLabel, EmptyState, ErrorState,
  FieldLabel, FlatBadgeSurface, FormFieldCell, ModalBody, ModalFooter, ModalHeader, OverflowMenu,
  PageHeader, SectionTitle, Segmented, Skeleton, Surface, SurfaceReset, Tag, overflowMenuItems, useToast,
} from "../../ui/kit.jsx";
import { FilterBar, FilterConditionLine, FilterToggle } from "../../ui/FilterBar.jsx";
import { EntityCombobox, FilterSelect, SearchBox } from "../../ui/filters.jsx";
import { UserPicker } from "../../ui/UserPicker.jsx";
import { StatusChip, StatusKpiStrip, StatusSummaryCard } from "../../ui/StatusKpi.jsx";
import { TicketFace } from "../../ui/TicketFace.jsx";
import { UserAvatar } from "../../ui/UserAvatar.jsx";
import { SettingRow } from "../../ui/adminKit.jsx";
import { SIGNALS } from "../../lib/ticketSignals.js";
import { CONTROL, FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, RADIUS, remPx } from "../../ui/theme.js";
import { FORM_FIELD_CONTAINER, FORM_FIELD_GRID_12, GRID_GAP, LANE_SURFACE, fieldSpan } from "../../ui/density.js";

/* 부품 갤러리 — **제품 화면이 아니라 공통 부품의 대조표**다.
 *
 * ## 정본은 핸드오프 문서다
 *
 * 값의 정본은 `design_handoff_clovirassist_ui/`(DECISIONS → README → RULES → ACCEPTANCE)이고,
 * 이 화면은 그 계약을 **실제 부품으로** 세운 구현 참고값이다. 예전 머리 주석은 「이 화면이
 * 정본이다」였다(D-473~D-481) — 핸드오프가 그 순서를 뒤집었다. 여기와 문서가 어긋나면 문서가
 * 맞고, 어긋난 자리는 부품을 고친다.
 *
 * ## 🔴 여기서는 값을 베끼지 않는다
 *
 * 모든 견본은 `ui/*` 의 부품을 그대로 `import` 해서 렌더한다. 이 파일에 있는 치수는 견본을
 * **배치**하는 값(줄 간격 · 견본 폭)뿐이고 부품 안쪽 치수는 한 줄도 안 적는다. 예외는
 * 「조작기의 상태」 절의 hover 견본 둘과 「이럴 때 이것」 절의 틀린 견본 하나이고, 그 자리에
 * 이유를 적었다.
 *
 * ## 절마다 무엇을 고치는 자리인가를 적는다 ([9])
 *
 * 절 머리의 칩이 **부품 이름 · 파일 · 대장 항목**이다. 이 부품을 쓰는 화면 전부의 목록은
 * `docs/ui-renewal/COMPONENT_LEDGER.md` 의 같은 항목에 있다. 새 갈래 · 상태를 더할 때는 여기
 * 견본과 시험을 먼저 세우고 화면에서 쓴다 — 화면에서 먼저 한 번 쓰는 갈래를 만들지 않는다.
 */

/* 견본 하나를 감싸는 자리 — 이름표 + 견본. */
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

/* 절 하나 — 제목 · 설명 · 부품 이름과 파일과 대장 항목 · 견본들. */
function GallerySection({ id, title, help, parts, children }) {
  return (
    <Card id={id} sx={{ display: "grid", rowGap: 2, minWidth: 0 }}>
      <SectionTitle component="h2" sx={{ mb: 0 }} title={title} help={help} />
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
        {parts.map((p) => (
          <Box
            key={p.path + p.name}
            data-gallery-part={p.name}
            sx={{
              display: "inline-flex", alignItems: "center", gap: 1,
              px: 1, height: remPx(CONTROL.buttonSm),
              border: 1, borderColor: "divider", borderRadius: `${RADIUS.sm}px`,
              bgcolor: "background.inset", maxWidth: "100%", minWidth: 0,
            }}
          >
            <Typography component="code" sx={{ fontSize: FONT_SIZE.micro, fontWeight: FONT_WEIGHT.semibold, whiteSpace: "nowrap" }}>
              {p.name}
            </Typography>
            <Typography component="code" color="text.secondary" sx={{ fontSize: FONT_SIZE.micro, whiteSpace: "nowrap" }}>
              {p.path}
            </Typography>
            {p.ledger ? (
              <Typography component="span" color="text.secondary" sx={{ fontSize: FONT_SIZE.micro, whiteSpace: "nowrap" }}>
                {`대장 ${p.ledger}`}
              </Typography>
            ) : null}
          </Box>
        ))}
      </Box>
      {children}
    </Card>
  );
}

/* 「이럴 때 이것」 한 쌍 — 두 견본을 나란히 두고 그 아래 한 줄로 가른다. */
function Pair({ caption, left, right }) {
  return (
    <Box sx={{ display: "grid", rowGap: 1.25, minWidth: 0 }}>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0,1fr)", md: "repeat(2, minmax(0, 1fr))" }, gap: 2, alignItems: "start" }}>
        {[left, right].map((side) => (
          <Box
            key={side.label}
            sx={{ display: "grid", alignContent: "start", minWidth: 0, border: 1, borderColor: "divider", borderRadius: `${RADIUS.md}px`, p: 2 }}
          >
            <Sample label={side.label}>{side.node}</Sample>
          </Box>
        ))}
      </Box>
      <Typography color="text.secondary" sx={{ fontSize: FONT_SIZE.caption, ...KO_WORD_BREAK }}>{caption}</Typography>
    </Box>
  );
}

/* 떠 있는 것을 **붙박이로** 세우는 자리 — 캔버스 색 구역 위에 놓아야 그림자와 테두리가 읽힌다. */
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

const PEOPLE = [
  { user_id: "u-other-1", display_name: "김정미", dept: "플랫폼개발팀" },
  { user_id: "u-me", display_name: "UI QA", dept: "품질팀" },
  { user_id: "u-other-2", display_name: "박도윤", dept: "인프라운영팀" },
  { user_id: "u-other-3", display_name: "이서연", dept: "플랫폼개발팀" },
];

/* 문서 목록 견본 ([2]) — 칸반 카드 견본이 이미 티켓이라 같은 자료를 두 부품이 그리지 않는다. */
const DOC_ROWS = [
  {
    id: "d1", project: "포털 개편", title: "사용자 대시보드 화면 설계서",
    summary: "첫 화면에 서는 판 넷의 순서와 높이 예산, 빈 상태 문구를 정리했습니다. 판독 줄을 상태 요약 카드로 바꾸는 이유도 함께 적었습니다.",
    tags: ["설계", "대시보드", "접근성", "반응형", "시안", "검수"], kind: "설계서",
    author: { user_id: "u-other-1", display_name: "김정미" }, updated: "2026-09-12",
  },
  {
    id: "d2", project: "포털 개편", title: "배포 전 점검 목록",
    summary: "배포 전에 확인할 항목을 순서대로 적었습니다.",
    tags: ["운영"], kind: "점검표",
    author: { user_id: "u-other-2", display_name: "박도윤" }, updated: "2026-09-10",
  },
  {
    id: "d3", project: "인프라 정비", title: "백업 복원 리허설 기록",
    summary: "월간 리허설에서 복원에 걸린 시간과 막힌 단계를 기록했습니다.",
    tags: ["백업", "리허설"], kind: "회의록",
    author: { user_id: "u-other-3", display_name: "이서연" }, updated: "2026-09-08",
  },
];

const TAG_LIMIT = 4;

const DOC_COLUMNS = [
  {
    key: "title", label: "제목", type: "title",
    render: (r) => (
      <Box sx={{ display: "grid", rowGap: 0.5, minWidth: 0, py: 0.5 }}>
        <Typography sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}>{r.title}</Typography>
        <Typography
          color="text.secondary"
          sx={{ fontSize: FONT_SIZE.caption, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden", ...KO_WORD_BREAK }}
        >
          {r.summary}
        </Typography>
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
          {r.tags.slice(0, TAG_LIMIT).map((t) => <Tag key={t} label={t} />)}
          {r.tags.length > TAG_LIMIT ? <Tag label={`+${r.tags.length - TAG_LIMIT}`} /> : null}
        </Box>
      </Box>
    ),
  },
  { key: "project", label: "프로젝트", type: "name" },
  { key: "kind", label: "분류", type: "enum", render: (r) => <DotLabel label={r.kind} /> },
  {
    key: "author", label: "작성자", type: "name",
    render: (r) => (
      <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75, minWidth: 0 }}>
        <UserAvatar person={r.author} name={r.author.display_name} size="xs" />
        <span>{r.author.display_name}</span>
      </Box>
    ),
  },
  { key: "updated", label: "최종 수정", type: "date" },
  { key: "act", label: "작업", type: "actions", render: () => <Button size="sm">열기</Button> },
];

/* 칸반 카드 견본 둘 ([4]) — 지연이 걸린 카드와 담당자가 없는 카드. */
const BOARD_CARDS = [
  {
    id: "b1", key: "HRXPZY-189", title: "자원 등록 화면 예외 처리와 재시도 안내", project: "포털 개편",
    due: "2026-09-11", est_wd: 4, priority: "high", assignees: [{ display_name: "김정미" }],
  },
  {
    id: "b2", key: "JBBCYU-15", title: "모니터링 수집 주기 정리", project: "인프라 정비",
    due: "2026-08-02", est_wd: 2, priority: "urgent", assignees: [], assignee_tokens: 0,
  },
];

const LONG_TITLE = "사내 업무 자동화 플랫폼의 티켓 상태 전이 규칙을 부서 범위 관리자 권한과 함께 다시 검토하는 아주 긴 제목의 작업 항목";
const LONG_URL = "https://internal.example.co.kr/very/deep/path/segment-without-any-break-opportunity/segment-without-any-break-opportunity";

export function KitGallery() {
  const toast = useToast();
  const [view, setView] = React.useState("all");
  const [period, setPeriod] = React.useState("3");
  const [mine, setMine] = React.useState(true);
  const [advanced, setAdvanced] = React.useState(true);
  const [status, setStatus] = React.useState("plan");
  const [project, setProject] = React.useState("");
  const [projects, setProjects] = React.useState(["p1", "p3"]);
  const [assignee, setAssignee] = React.useState("u-other-1");
  const [notify, setNotify] = React.useState(true);

  return (
    <div className="c-screen">
      <PageHeader
        area="개발"
        title="공통 부품 갤러리"
        crumbRoot=""
        description="확정 규약을 실제 부품으로 세워 봅니다. 모든 견본이 제품 부품을 그대로 불러 쓰므로 값을 베낀 그림이 아닙니다."
      />

      <Box sx={{ display: "grid", gap: GRID_GAP, minWidth: 0 }}>
        {/* ── 1. 버튼 ─────────────────────────────────────────────── */}
        <GallerySection
          id="kit-buttons"
          title="버튼"
          help="한 화면에 채운 버튼은 하나입니다. 보조는 흰 면에 테두리이고, 파괴적 동작은 채운 면을 쓰지 않습니다."
          parts={[
            { name: "Button", path: "ui/kit.jsx", ledger: "Button" },
            { name: "OverflowMenu", path: "ui/kit.jsx", ledger: "overflowMenuItems" },
          ]}
        >
          <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 1.25 }}>
            <Button variant="primary">회차 추가</Button>
            <Button variant="secondary">티켓 추가</Button>
            <Button variant="ghost">전체 보기</Button>
            <Button variant="danger">나가기</Button>
            <Button disabled>다음 회차</Button>
            <Box aria-hidden="true" sx={{ width: "1px", height: "1.625rem", bgcolor: "divider" }} />
            <Button size="sm">수정</Button>
            <OverflowMenu items={MENU_ITEMS} size="sm" />
            <Button variant="primary" loading>저장</Button>
          </Box>
        </GallerySection>

        {/* ── 2. 버튼 크기 ────────────────────────────────────────── */}
        <GallerySection
          id="kit-button-sizes"
          title="버튼 크기"
          help="버튼은 두 단계뿐입니다. 28은 세그먼티드 안쪽 칸에만 쓰고, 26은 조건 칩입니다."
          parts={[{ name: "CONTROL.button / buttonSm / chip", path: "ui/theme.js", ledger: "토큰" }]}
        >
          <Box sx={{ display: "grid", gridTemplateColumns: "9rem minmax(0, 1fr)", columnGap: 2.5, rowGap: 1.75, alignItems: "center" }}>
            <Typography sx={{ fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.semibold }}>{`${CONTROL.button}px 페이지 동작`}</Typography>
            <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
              <Button variant="primary">회차 추가</Button>
              <Button>티켓 추가</Button>
              <Typography color="text.secondary" sx={{ fontSize: FONT_SIZE.micro }}>페이지 머리, 모달 발, 필터 바에 섭니다.</Typography>
            </Box>
            <Typography sx={{ fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.semibold }}>{`${CONTROL.buttonSm}px 인라인 동작`}</Typography>
            <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
              <Button size="sm">수정</Button>
              <Button size="sm" variant="ghost">보기</Button>
              <Typography color="text.secondary" sx={{ fontSize: FONT_SIZE.micro }}>표 행, 칸반 카드, 메시지 박스 오른쪽에 섭니다.</Typography>
            </Box>
          </Box>
        </GallerySection>

        {/* ── 3. 검색과 필터 바 [1] ───────────────────────────────── */}
        {/* 견본 셋이 **조합 부품 하나**(`FilterBar`)다 — 낱개 부품을 여기서 조립하지 않는다(조합 계약 C-1). 목록 화면이
            쓰는 모양 그대로다: 조건이 없으면 한 줄, 조건이 걸리면 같은 면 안 둘째 줄, 좁은 판에서는 오른쪽 묶음이 통째로 내려간다. */}
        <GallerySection
          id="kit-filter-bar"
          title="검색과 필터 바"
          help="한 줄 순서는 검색 320, 필터 칸, 빈 공간, 오른쪽 끝 묶음입니다. 칸 이름은 칸 안에 서고, 조건이 걸리면 실선 아래 둘째 줄에 조건 수와 칩과 지우기가 섭니다."
          parts={[
            { name: "FilterBar", path: "ui/FilterBar.jsx", ledger: "FilterBar" },
            { name: "FilterConditionLine / FilterToggle", path: "ui/FilterBar.jsx", ledger: "FilterBar" },
            { name: "SearchBox / FilterSelect / EntityCombobox / RowSummary", path: "ui/filters.jsx", ledger: "필터 칸" },
          ]}
        >
          <Sample label="조건이 없는 한 줄">
            <FilterBar
              search={<SearchBox value="" onSearch={() => {}} placeholder="티켓 제목, 이름 검색" ariaLabel="조건 없는 티켓 검색" />}
              end={<FilterToggle expanded={false} onClick={() => {}}>상세 필터</FilterToggle>}
              conditions={{ chips: [], total: 21 }}
            >
              <EntityCombobox
                label="프로젝트" value={project} onChange={setProject}
                options={[{ value: "p1", label: "포털 개편" }, { value: "p2", label: "인프라 정비" }]}
              />
              <FilterSelect label="상태" value="" onChange={() => {}} options={["계획", "진행 중"]} />
              <FilterSelect label="우선순위" value="" onChange={() => {}} options={["높음", "보통", "낮음"]} />
            </FilterBar>
          </Sample>
          <Sample label="조건 여럿, 다중 선택은 칸 안 한 줄 요약이고 칩은 조건 줄에 섭니다">
            <FilterBar
              search={<SearchBox value="배포" onSearch={() => {}} placeholder="티켓 제목, 이름 검색" ariaLabel="조건 있는 티켓 검색" />}
              end={(
                <>
                  <FilterToggle pressed={mine} onClick={() => setMine((v) => !v)}>내 티켓만</FilterToggle>
                  <FilterToggle expanded={advanced} onClick={() => setAdvanced((v) => !v)}>상세 필터</FilterToggle>
                </>
              )}
              conditions={{
                chips: [
                  { key: "q", label: "검색: 배포", onDelete: () => {} },
                  { key: "p1", label: "프로젝트: ClovirAssist 플랫폼 전환 및 자체 데이터 이관", onDelete: () => {} },
                  { key: "p3", label: "프로젝트: 포털 개편", onDelete: () => {} },
                  { key: "status", label: "상태: 계획", onDelete: () => {} },
                ],
                total: 21,
                onClearAll: () => {},
                clearLabel: "필터 초기화",
                extraAction: { label: "전체 보기", onClick: () => {} },
              }}
            >
              <EntityCombobox
                multiple label="프로젝트" value={projects} onChange={setProjects}
                options={[
                  { value: "p1", label: "ClovirAssist 플랫폼 전환 및 자체 데이터 이관" },
                  { value: "p2", label: "인프라 정비" },
                  { value: "p3", label: "포털 개편" },
                ]}
              />
              <FilterSelect
                label="상태" value={status} onChange={setStatus}
                options={[{ value: "plan", label: "계획" }, { value: "doing", label: "진행 중" }]}
              />
              <FilterSelect label="우선순위" value="" onChange={() => {}} options={["높음", "보통", "낮음"]} />
            </FilterBar>
          </Sample>
          <Sample label="1200 폭의 좁은 판, 순서를 지킨 채 줄이 바뀌고 오른쪽 묶음이 통째로 내려갑니다">
            <Box sx={{ maxWidth: "44rem", border: 1, borderColor: "divider", borderRadius: `${RADIUS.md}px`, p: 2 }}>
              <FilterBar
                sx={{ mb: 0 }}
                search={<SearchBox value="" onSearch={() => {}} placeholder="티켓 제목, 이름 검색" ariaLabel="좁은 판 티켓 검색" />}
                end={(
                  <>
                    <FilterToggle pressed={false} onClick={() => {}}>내 티켓만</FilterToggle>
                    <FilterToggle expanded={false} onClick={() => {}}>상세 필터</FilterToggle>
                  </>
                )}
              >
                <FilterSelect label="상태" value="" onChange={() => {}} options={["계획", "진행 중"]} />
                <FilterSelect label="난이도" value="" onChange={() => {}} options={["상", "중", "하"]} />
              </FilterBar>
            </Box>
          </Sample>
        </GallerySection>

        {/* ── 4. 세그먼티드 ───────────────────────────────────────── */}
        <GallerySection
          id="kit-segmented"
          title="세그먼티드"
          help="보는 방식을 바꿀 때 씁니다. 컨테이너 34, 여백 3, 안쪽 칸 28이고 고른 칸만 한 겹 올라옵니다. 화살표 키로 옮깁니다."
          parts={[{ name: "Segmented", path: "ui/kit.jsx", ledger: "Segmented" }]}
        >
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 3, alignItems: "flex-start" }}>
            <Sample label="보기 전환, 건수와 함께">
              <Segmented
                ariaLabel="문서 보기" value={view} onChange={setView}
                options={[
                  { value: "all", label: "전체", count: 128 },
                  { value: "recent", label: "최근 24시간", count: 6 },
                  { value: "fav", label: "즐겨찾기", count: 12 },
                  { value: "draft", label: "내 초안", count: 3 },
                ]}
              />
            </Sample>
            <Sample label="기간">
              <Segmented
                ariaLabel="기간" value={period} onChange={setPeriod}
                options={[{ value: "3", label: "3개월" }, { value: "6", label: "6개월" }, { value: "12", label: "12개월" }]}
              />
            </Sample>
          </Box>
        </GallerySection>

        {/* ── 5. 팝오버와 모달 [3] ────────────────────────────────── */}
        <GallerySection
          id="kit-floating"
          title="팝오버와 모달"
          help="떠 있는 셋의 모서리는 모두 8입니다. 모달 제목은 판 제목과 같은 단계이고, 발은 함몰면과 위 실선이며 취소는 흰 면입니다."
          parts={[
            { name: "overflowMenuItems", path: "ui/kit.jsx", ledger: "overflowMenuItems" },
            { name: "ModalHeader / ModalBody / ModalFooter / ActionFooter", path: "ui/kit.jsx", ledger: "ActionFooter" },
            { name: "EntityCombobox 목록 / PickerOption / UserPicker", path: "ui/filters.jsx", ledger: "검색 팝오버" },
          ]}
        >
          {/* 진짜 `Modal` · `Menu` 는 포털로 막을 깔아 캡처에 이 페이지가 안 남는다. 떠 있게
              만드는 껍데기(`Surface` overlay · modal)만 대신 세우고 안의 내용은 제품 부품이다. */}
          <Box sx={FLOAT_STAGE}>
            <Sample label="팝오버, 동작 목록">
              <Surface tone="overlay" sx={{ width: "16rem", py: 0.5 }}>
                <MenuList disablePadding>{overflowMenuItems(MENU_ITEMS)}</MenuList>
              </Surface>
            </Sample>

            <Sample label="검색 팝오버, 사람 고르기(내 계정이 맨 위, 고른 사람에 체크)">
              <Box sx={{ width: "22rem", pb: "16rem" }}>
                <UserPicker
                  label="담당자" candidates={PEOPLE} value={assignee} onChange={setAssignee}
                  myId="u-me" layout="form" open disablePortal
                />
              </Box>
            </Sample>

            <Sample label="모달, 머리와 몸과 발">
              <Surface tone="modal" sx={{ width: "28rem", overflow: "hidden" }}>
                <ModalHeader title="회차 추가" onClose={() => {}} />
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

            <Sample label="확인 모달, 되돌릴 수 없는 동작(취소가 기본 포커스)">
              <Surface tone="modal" sx={{ width: "24rem", overflow: "hidden" }}>
                <ModalHeader title="채팅방에서 나갑니다" tone="danger" onClose={() => {}} />
                <ModalBody>나가면 이 방의 지난 대화를 더 볼 수 없습니다. 다시 초대받으면 들어올 수 있습니다.</ModalBody>
                <ModalFooter onCancel={() => {}} onSubmit={() => {}} submitLabel="나가기" submitVariant="dangerConfirm" />
              </Surface>
            </Sample>
          </Box>
        </GallerySection>

        {/* ── 6. 칸반 카드 [4] ────────────────────────────────────── */}
        <GallerySection
          id="kit-kanban"
          title="칸반 카드"
          help="읽는 순서는 티켓 키와 우선순위와 신호, 제목, 프로젝트, 발입니다. 신호와 우선순위는 점과 낱말이고, 발은 위 실선으로 갈립니다."
          parts={[
            { name: "TicketFace / TicketPeople", path: "ui/TicketFace.jsx", ledger: "칸반 카드" },
            { name: "TicketSignals variant=dot", path: "ui/TicketSignals.jsx", ledger: "신호 어휘" },
            { name: "LANE_SURFACE", path: "ui/density.js" },
          ]}
        >
          <SurfaceReset>
            <Box sx={{ ...LANE_SURFACE, p: 2.5, display: "flex", flexWrap: "wrap", gap: 1.75, alignItems: "flex-start" }}>
              <TicketFace card={BOARD_CARDS[0]} signals={[SIGNALS.overdue]} sx={{ width: "17.5rem" }} />
              <TicketFace card={BOARD_CARDS[1]} signals={[]} sx={{ width: "17.5rem" }} />
            </Box>
          </SurfaceReset>
        </GallerySection>

        {/* ── 7. 상태 요약 ────────────────────────────────────────── */}
        <GallerySection
          id="kit-status-summary"
          title="상태 요약 카드"
          help="전체를 남김없이 나눈 부분만 비율 바를 갖습니다. 서로 다른 측정값은 측정값 줄이고, 값이 하나면 큰 숫자 하나입니다."
          parts={[
            { name: "StatusSummaryCard", path: "ui/StatusKpi.jsx", ledger: "상태 요약" },
            { name: "StatusKpiStrip", path: "ui/StatusKpi.jsx", ledger: "상태 요약" },
          ]}
        >
          <Box sx={{ display: "grid", rowGap: 2 }}>
            <StatusSummaryCard
              ariaLabel="상태 요약" total="179" totalLabel="전체"
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
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0,1fr)", md: "repeat(2, minmax(0,1fr))" }, gap: 2, alignItems: "start" }}>
              <Sample label="값 하나, 큰 숫자">
                <StatusSummaryCard ariaLabel="안 읽음" title="알림" total="12" totalLabel="안 읽음" />
              </Sample>
              <Sample label="서로 다른 측정값, 측정값 줄">
                <StatusKpiStrip
                  ariaLabel="처리 현황"
                  items={[
                    { label: "처리 요청", value: "48", primary: true },
                    { label: "성공률", value: "96%" },
                    { label: "대기", value: "3" },
                  ]}
                />
              </Sample>
            </Box>
          </Box>
        </GallerySection>

        {/* ── 8. 데이터 표 [2] ────────────────────────────────────── */}
        <GallerySection
          id="kit-table"
          title="데이터 표"
          help="제목 열만 왼쪽이고 나머지는 가운데이며 머리와 행이 같습니다. 두 줄 행의 바닥은 76이고, 표 안의 분류는 점과 낱말입니다."
          parts={[
            { name: "DataTable rowHeight=tall", path: "ui/kit.jsx", ledger: "DataTable" },
            { name: "COLUMN_TYPES / headerAlignOf", path: "ui/columnTypes.js", ledger: "DataTable" },
            { name: "CountChip / DotLabel / Tag", path: "ui/kit.jsx" },
          ]}
        >
          <DataTable
            columns={DOC_COLUMNS}
            rows={DOC_ROWS}
            rowKey={(r) => r.id}
            groupOf={(r) => r.project}
            rowHeight="tall"
            total={3}
          />
        </GallerySection>

        {/* ── 9. 배지 · 태그 · 점 · 칩 [5] ───────────────────────── */}
        <GallerySection
          id="kit-values"
          title="배지와 태그와 점과 칩"
          help="배지는 목록 밖의 정해진 값이고 안에 점이 없습니다. 태그는 사람이 붙인 낱말이고 굵기 400입니다. 표와 카드 안에서는 점과 낱말입니다."
          parts={[
            { name: "Badge / Tag / DotLabel / CountChip", path: "ui/kit.jsx", ledger: "값 표시" },
            { name: "FilterChips / StatusChip", path: "ui/FilterBar.jsx, ui/StatusKpi.jsx" },
          ]}
        >
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 3, alignItems: "flex-start" }}>
            <Sample label="배지, 목록 밖">
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
                <Badge value="계획" emphasis="strong" />
                <Badge value="진행 중" emphasis="strong" />
                <Badge value="완료" kind="ok" emphasis="strong" />
                <Badge value="지연" kind="warn" emphasis="strong" />
                <Badge value="차단됨" kind="danger" emphasis="strong" />
              </Box>
            </Sample>
            <Sample label="태그">
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
                <Tag label="ClovirONE" />
                <Tag label="Docker" />
                <Tag label="Linux" tone="teal" />
                <Tag label="+2" />
              </Box>
            </Sample>
            <Sample label="점과 낱말, 표와 카드와 목록 행 안">
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.75 }}>
                <DotLabel label="계획" tone="info" />
                <DotLabel label="높음" tone="warn" />
                <DotLabel label="지연" tone="danger" strong />
                <DotLabel label="회의록" />
              </Box>
            </Sample>
            <Sample label="건수 칩">
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, alignItems: "center" }}>
                <CountChip value="3건" />
                <CountChip value={12} unread ariaLabel="안 읽음 12" />
                <CountChip value={4} compact />
              </Box>
            </Sample>
            <Sample label="상태 칩, 고른 것과 안 고른 것">
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
                <StatusChip label="진행 중" value="21" accent="info.main" onClick={() => {}} selected />
                <StatusChip label="검증" value="7" accent="warning.main" onClick={() => {}} selected={false} />
              </Box>
            </Sample>
          </Box>
          <FlatBadgeSurface>
            <Sample label="표 문맥 안의 배지는 스스로 점과 낱말이 됩니다">
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.75 }}>
                <Badge value="계획" />
                <Badge value="지연" kind="warn" />
              </Box>
            </Sample>
          </FlatBadgeSurface>
        </GallerySection>

        {/* ── 10. 폼 필드 ─────────────────────────────────────────── */}
        <GallerySection
          id="kit-form"
          title="폼 필드"
          help="칸 하나는 라벨 20, 필드 36, 도움말의 세 줄 트랙입니다. 도움말이 없어도 트랙이 남아 한 줄의 입력칸 윗선이 같습니다."
          parts={[
            { name: "FormFieldCell / FIELD_ROWS / FieldLabel", path: "ui/kit.jsx", ledger: "폼 필드" },
            { name: "FORM_FIELD_GRID_12 / fieldSpan", path: "ui/density.js", ledger: "폼 필드" },
          ]}
        >
          <Box sx={FORM_FIELD_CONTAINER}>
            <Box sx={FORM_FIELD_GRID_12}>
              <FormFieldCell label="제목" htmlFor="kg-f-title" required help="한 줄로 무슨 일인지 알 수 있게 씁니다." sx={fieldSpan({ wide: 12, mid: 2 })}>
                <TextField id="kg-f-title" size="small" fullWidth defaultValue="자원 등록 화면 예외 처리" />
              </FormFieldCell>
              <FormFieldCell label="프로젝트" htmlFor="kg-f-project" required sx={fieldSpan({ wide: 6, mid: 2 })}>
                <TextField id="kg-f-project" size="small" fullWidth defaultValue="포털 개편" />
              </FormFieldCell>
              <FormFieldCell label="진행 상태" htmlFor="kg-f-status" sx={fieldSpan({ wide: 3, mid: 1 })}>
                <TextField id="kg-f-status" size="small" fullWidth defaultValue="계획" />
              </FormFieldCell>
              <FormFieldCell label="우선순위" htmlFor="kg-f-priority" sx={fieldSpan({ wide: 3, mid: 1 })}>
                <TextField id="kg-f-priority" size="small" fullWidth defaultValue="보통" />
              </FormFieldCell>
              <FormFieldCell label="예상 WD" htmlFor="kg-f-wd" error="1 이상을 넣어 주세요." sx={fieldSpan({ wide: 3, mid: 1 })}>
                <TextField id="kg-f-wd" size="small" fullWidth error defaultValue="0" />
              </FormFieldCell>
              <FormFieldCell label="담당자" htmlFor="kg-f-assignee" help="프로젝트를 먼저 고르세요." sx={fieldSpan({ wide: 3, mid: 1 })}>
                <TextField id="kg-f-assignee" size="small" fullWidth disabled defaultValue="" />
              </FormFieldCell>
            </Box>
          </Box>
          <Card sx={{ p: 2.5 }}>
            <Typography sx={{ fontSize: FONT_SIZE.bodySm }}>카드 발은 판 가장자리까지 함몰면을 펴고 위 실선으로 갈립니다.</Typography>
            <ActionFooter placement="card">
              <Button>취소</Button>
              <Button variant="primary">저장</Button>
            </ActionFooter>
          </Card>
        </GallerySection>

        {/* ── 11. 빈 상태 · 오류 · 로딩 · 토스트 [7] ─────────────── */}
        <GallerySection
          id="kit-states"
          title="빈 상태와 오류와 로딩과 토스트"
          help="판 안에서는 왼쪽 정렬과 위 정렬이고 클로비는 72 이하입니다. 오류에는 아이콘이 붙고 다시 시도는 30입니다."
          parts={[
            { name: "EmptyState / ErrorState / Skeleton", path: "ui/kit.jsx", ledger: "빈 상태와 오류" },
            { name: "MASCOT_PLACE", path: "ui/Mascot.jsx", ledger: "마스코트 크기" },
            { name: "ToastProvider", path: "ui/kit.jsx", ledger: "토스트" },
          ]}
        >
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0,1fr)", lg: "repeat(2, minmax(0, 1fr))" }, gap: 2, alignItems: "start" }}>
            {[
              {
                label: "빈 상태, 판 안(자료가 아직 없음)",
                node: <EmptyState art="tickets" title="아직 맡은 티켓이 없습니다" help="새 티켓을 만들면 여기에 모입니다." action={<Button size="sm">새 티켓</Button>} />,
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
                label: "토스트, 방금 한 일이 잘 됐을 때만",
                node: (
                  <Box sx={{ display: "grid", rowGap: 1, justifyItems: "start" }}>
                    <Button size="sm" onClick={() => toast("티켓을 저장했습니다.", "success")}>성공 토스트 띄우기</Button>
                    <Typography color="text.secondary" sx={{ fontSize: FONT_SIZE.micro, ...KO_WORD_BREAK }}>
                      토스트는 화면 밖에서 떠오르므로 누르면 확인할 수 있습니다.
                    </Typography>
                  </Box>
                ),
              },
            ].map((s) => (
              <Box key={s.label} sx={{ display: "grid", alignContent: "start", minWidth: 0, border: 1, borderColor: "divider", borderRadius: `${RADIUS.md}px`, p: 2 }}>
                <Sample label={s.label}>{s.node}</Sample>
              </Box>
            ))}
          </Box>
        </GallerySection>

        {/* ── 12. 메시지 박스 1a [7] ─────────────────────────────── */}
        <GallerySection
          id="kit-callout"
          title="메시지 박스 1a"
          help="네 상태의 면과 테두리가 같고 아이콘만 다릅니다. 톤 이름 줄은 없습니다. 한 줄이면 높이 49입니다."
          parts={[{ name: "Callout variant=block, inline, bleed", path: "ui/kit.jsx", ledger: "Callout" }]}
        >
          <Box sx={{ display: "grid", rowGap: 1.25 }}>
            <Callout tone="info">진행 중인 회차가 없습니다.</Callout>
            <Callout tone="ok">티켓을 저장했습니다.</Callout>
            <Callout tone="warn" action={<Button size="sm">항목 보기</Button>}>소속을 판정할 수 없는 항목이 64건 있습니다.</Callout>
            <Callout tone="danger" detail="NetworkError: Failed to fetch (request 7f3a)">티켓을 불러오지 못했습니다.</Callout>
            <Callout tone="warn" title="이 회차는 이미 닫혔습니다">
              닫힌 회차의 티켓은 읽기만 할 수 있습니다.
              <Box component="ul" sx={{ m: 0, mt: 0.75, pl: 2.5, display: "grid", rowGap: 0.5 }}>
                <li>티켓을 옮기거나 순서를 바꿀 수 없습니다.</li>
                <li>다시 열려면 관리자에게 요청하세요.</li>
              </Box>
            </Callout>
            <Callout tone="info" compact>좁은 자리를 위한 컴팩트 갈래입니다.</Callout>
            <Callout tone="info" variant="inline">문장 흐름 안에 서는 한 줄 갈래입니다.</Callout>
            <Callout tone="warn" variant="bleed">판 밖 전폭 띠로 서는 갈래입니다.</Callout>
          </Box>
        </GallerySection>

        {/* ── 13. 조작기의 상태 [6] ──────────────────────────────── */}
        <GallerySection
          id="kit-control-states"
          title="조작기의 상태"
          help="기본만 보면 규약을 반만 본 것입니다. 초점과 비활성과 오류와 선택을 한 줄에 세워야 어긋난 자리가 보입니다."
          parts={[
            { name: "Button / DataTable / Switch / Checkbox", path: "ui/kit.jsx, ui/theme.js", ledger: "조작기 상태" },
            { name: "SettingRow compact", path: "ui/adminKit.jsx" },
          ]}
        >
          {/* 초점 · 비활성 · 선택은 클래스(`Mui-focusVisible` 등)를 얹어 실제 규칙으로 그린다.
              hover 만 정지 화면에 없어 **토큰 이름**을 직접 부른다(값이 아니다). */}
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
                <Button sx={{ bgcolor: "background.inset", borderColor: "dividerStrong" }}>마우스 올림</Button>
                <Button className="Mui-focusVisible">초점</Button>
                <Button disabled>비활성</Button>
              </Box>
            </Sample>
            <Sample label="입력, 기본과 초점과 오류와 비활성">
              <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(13rem, 1fr))", gap: 2 }}>
                <FormFieldCell label="기본" htmlFor="kg-st-normal"><TextField id="kg-st-normal" size="small" fullWidth defaultValue="9월 둘째 주" /></FormFieldCell>
                <FormFieldCell label="초점" htmlFor="kg-st-focus"><TextField id="kg-st-focus" size="small" fullWidth defaultValue="9월 둘째 주" InputProps={{ className: "Mui-focused" }} /></FormFieldCell>
                <FormFieldCell label="오류" htmlFor="kg-st-error" error="1 이상을 넣어 주세요."><TextField id="kg-st-error" size="small" fullWidth error defaultValue="0" /></FormFieldCell>
                <FormFieldCell label="비활성" htmlFor="kg-st-off" help="회차를 먼저 고르세요."><TextField id="kg-st-off" size="small" fullWidth disabled defaultValue="" /></FormFieldCell>
              </Box>
            </Sample>
            <Sample label="표 행, 마우스 올림과 선택은 같은 한 단계">
              <DataTable
                columns={DOC_COLUMNS.slice(0, 3)}
                rows={DOC_ROWS}
                rowKey={(r) => r.id}
                rowSelected={(r) => r.id === "d2"}
                onRow={() => {}}
                rowHeight="tall"
              />
            </Sample>
            <Sample label="토글은 누르는 즉시 저장되는 설정의 자리입니다">
              <Box sx={{ maxWidth: "36rem" }}>
                <SettingRow
                  compact label="새 댓글 알림" description="내 티켓에 댓글이 달리면 알립니다."
                  action={<Switch checked={notify} onChange={(e) => setNotify(e.target.checked)} slotProps={{ input: { "aria-label": "새 댓글 알림" } }} />}
                />
                <SettingRow
                  compact label="주간 요약 메일" description="월요일 아침에 한 번 보냅니다."
                  action={<Switch checked={false} onChange={() => {}} slotProps={{ input: { "aria-label": "주간 요약 메일" } }} />}
                />
                <SettingRow
                  compact label="관리자가 끈 알림" description="조직 설정에서 막았습니다."
                  action={<Switch checked disabled slotProps={{ input: { "aria-label": "관리자가 끈 알림" } }} />}
                />
              </Box>
            </Sample>
            <Sample label="체크박스, 저장을 눌러야 확정되는 폼 안 선택">
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
                <FormControlLabel control={<Checkbox defaultChecked />} label="담당자에게 알림" />
                <FormControlLabel control={<Checkbox />} label="회차에 바로 담기" />
                <FormControlLabel control={<Checkbox disabled />} label="비활성" />
              </Box>
            </Sample>
          </Box>
        </GallerySection>

        {/* ── 14. 이럴 때 이것 [8] ───────────────────────────────── */}
        <GallerySection
          id="kit-when"
          title="이럴 때 이것"
          help="같은 자리에서 헷갈리기 쉬운 부품 둘을 나란히 두고 언제 무엇을 쓰는지 한 줄로 적었습니다."
          parts={[{ name: "RULES", path: "design_handoff_clovirassist_ui/RULES.md" }]}
        >
          <Box sx={{ display: "grid", rowGap: 3 }}>
            <Pair
              caption="자료가 없어 비었으면 만드는 동작을 주고, 조건 때문에 비었으면 조건을 지우는 동작을 줍니다. 조건 때문일 때는 클로비가 없습니다."
              left={{ label: "자료가 아직 없음", node: <EmptyState art="tickets" title="아직 맡은 티켓이 없습니다" action={<Button size="sm">새 티켓</Button>} /> }}
              right={{ label: "조건 때문에 0건", node: <EmptyState title="조건에 맞는 항목이 없습니다" help="지금 걸린 조건에 맞는 항목이 없습니다." action={<Button size="sm">필터 지우기</Button>} /> }}
            />
            <Pair
              caption="판 하나가 실패하면 그 판 안에서 왼쪽 정렬로, 화면 전체가 실패하면 가운데로 섭니다."
              left={{ label: "판 안 오류", node: <ErrorState layout="region" error={Object.assign(new Error("요청 시간이 지났습니다."), { status: 504 })} onRetry={() => {}} /> }}
              right={{ label: "화면 전체 오류", node: <Box sx={{ border: 1, borderColor: "divider", borderRadius: `${RADIUS.md}px` }}><ErrorState layout="page" error={Object.assign(new Error("요청 시간이 지났습니다."), { status: 504 })} onRetry={() => {}} /></Box> }}
            />
            <Pair
              caption="방금 한 일이 잘 됐으면 토스트로 알리고, 저장 실패처럼 다시 해야 하는 일은 사라지지 않는 메시지 박스로 남깁니다."
              left={{ label: "성공, 토스트", node: <Button size="sm" onClick={() => toast("티켓을 저장했습니다.", "success")}>저장 완료 알리기</Button> }}
              right={{ label: "실패, 폼 안 메시지 박스", node: <Callout tone="danger">티켓을 저장하지 못했습니다. 입력한 내용은 그대로 있습니다.</Callout> }}
            />
            <Pair
              caption="목록 밖의 정해진 값은 배지, 사람이 붙인 낱말은 태그, 표와 카드 안은 점과 낱말, 지울 수 있는 조건은 필터 칩, 목록을 좁히는 조작은 상태 칩입니다."
              left={{
                label: "배지, 태그, 점과 낱말",
                node: (
                  <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.25, alignItems: "center" }}>
                    <Badge value="진행 중" emphasis="strong" />
                    <Tag label="Docker" />
                    <DotLabel label="지연" tone="danger" />
                  </Box>
                ),
              }}
              right={{
                label: "필터 칩, 상태 칩",
                node: (
                  <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.25, alignItems: "center" }}>
                    <FilterConditionLine total={8} chips={[{ key: "s", label: "상태 계획", onDelete: () => {} }]} />
                    <StatusChip label="진행 중" value="21" accent="info.main" onClick={() => {}} selected={false} />
                  </Box>
                ),
              }}
            />
            <Pair
              caption="즉시 저장되는 설정은 토글, 폼 안 선택은 체크박스, 보기 전환은 세그먼티드, 패널을 여는 것은 버튼입니다."
              left={{
                label: "토글, 체크박스",
                node: (
                  <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, alignItems: "center" }}>
                    <Switch defaultChecked slotProps={{ input: { "aria-label": "즉시 저장 설정" } }} />
                    <FormControlLabel control={<Checkbox defaultChecked />} label="폼 안 선택" />
                  </Box>
                ),
              }}
              right={{
                label: "세그먼티드, 버튼",
                node: (
                  <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, alignItems: "center" }}>
                    <Segmented ariaLabel="보기" value="board" onChange={() => {}} options={[{ value: "board", label: "칸반" }, { value: "backlog", label: "백로그" }]} />
                    <FilterToggle expanded={false} onClick={() => {}}>상세 필터</FilterToggle>
                  </Box>
                ),
              }}
            />
            <Pair
              caption="항목이 일곱 개 이하이고 늘지 않으면 셀렉트, 사람과 프로젝트처럼 늘어나면 검색 팝오버입니다."
              left={{ label: "셀렉트", node: <FilterSelect label="우선순위" value="" onChange={() => {}} options={["높음", "보통", "낮음"]} layout="row" /> }}
              right={{ label: "검색 팝오버", node: <UserPicker label="담당자" candidates={PEOPLE} value="" onChange={() => {}} myId="u-me" layout="row" /> }}
            />
            <Pair
              caption="막힌 이유는 필드 밖 도움말 줄에 씁니다. 이유를 필드 안 회색 글자로 쓰면 값처럼 읽힙니다."
              left={{ label: "옳음, 비활성 필드와 밖 도움말", node: <FormFieldCell label="담당자" htmlFor="kg-w-ok" help="프로젝트를 먼저 고르세요."><TextField id="kg-w-ok" size="small" fullWidth disabled defaultValue="" /></FormFieldCell> }}
              right={{
                label: "이렇게 하지 않는다, 필드 안 회색 이유",
                /* 틀린 견본 — 규칙을 보여 주려고 **일부러** 틀리게 그린다. 제품 코드에서 쓰지 않는다. */
                node: <FormFieldCell label="담당자" htmlFor="kg-w-bad"><TextField id="kg-w-bad" size="small" fullWidth disabled defaultValue="프로젝트를 먼저 고르세요." /></FormFieldCell>,
              }}
            />
          </Box>
        </GallerySection>

        {/* ── 15. 긴 데이터 ───────────────────────────────────────── */}
        <GallerySection
          id="kit-long-data"
          title="긴 데이터"
          help="높이가 정해진 부품은 한 줄로 서고 말줄임과 전체 값을 함께 둡니다. 글이 흐르는 부품은 자리 안에서 줄을 바꾸고 폭을 밀지 않습니다."
          parts={[{ name: "줄바꿈 계약", path: "design_handoff_clovirassist_ui 계획 §0-3", ledger: "줄바꿈" }]}
        >
          <Box data-long-data="" sx={{ display: "grid", rowGap: 2, minWidth: 0 }}>
            <Sample label="좁은 칸의 버튼, 말줄임을 켠 자리">
              <Box sx={{ width: "12rem", border: 1, borderColor: "divider", borderRadius: `${RADIUS.sm}px`, p: 1 }}>
                <Button size="sm" truncate>{LONG_TITLE}</Button>
              </Box>
            </Sample>
            <Sample label="배지, 태그, 건수 칩, 점과 낱말">
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, maxWidth: "28rem" }}>
                <Tag label={LONG_TITLE} />
                <DotLabel label={LONG_TITLE} tone="warn" sx={{ maxWidth: "16rem" }} />
                <CountChip value="12,345건" />
              </Box>
            </Sample>
            <Sample label="필터 칸의 긴 값">
              <FilterBar sx={{ mb: 0, maxWidth: "40rem" }}>
                <EntityCombobox label="프로젝트" value="p-long" onChange={() => {}} options={[{ value: "p-long", label: `P. ${LONG_TITLE}` }]} />
                <FilterSelect label="분류" value="k" onChange={() => {}} options={[{ value: "k", label: LONG_TITLE }]} />
              </FilterBar>
            </Sample>
            <Sample label="메시지 박스와 오류 문장">
              <Callout tone="danger" detail={LONG_URL}>{`${LONG_TITLE}을 저장하지 못했습니다. 잠시 뒤 다시 시도해 주세요.`}</Callout>
            </Sample>
            <Sample label="긴 판 제목과 긴 사람 이름">
              <Card sx={{ maxWidth: "32rem" }}>
                <SectionTitle title={LONG_TITLE} sx={{ mb: 1 }} />
                <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75, minWidth: 0, maxWidth: "100%" }}>
                  <UserAvatar person={{ user_id: "u-long" }} name="아주긴이름을가진사용자의표시이름" size="xs" />
                  <Box component="span" sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>아주긴이름을가진사용자의표시이름 플랫폼개발본부 인프라자동화파트</Box>
                </Box>
              </Card>
            </Sample>
          </Box>
        </GallerySection>
      </Box>
    </div>
  );
}

export default KitGallery;
