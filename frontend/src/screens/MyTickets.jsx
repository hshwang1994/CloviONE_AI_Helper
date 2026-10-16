import React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import { api } from "../lib/api.js";
import { Card, Badge, DataTable, EmptyState, ErrorState, Skeleton, Callout, PageHeader, Modal, ModalFooter, Button, useToast, useConfirm, FieldLabel, FormFieldCell, ActionFooter, SectionTitle, RowActions, TitleCell } from "../ui/kit.jsx";
import { DateField } from "../ui/DateField.jsx";
import { PersonLine } from "../ui/UserAvatar.jsx";
import { priorityKo, priorityKind } from "../lib/priority.js";
import { useAuth } from "../app/auth.jsx";
import { editorContainerSx, editorSurfaceWidthSx } from "../ui/BodyEditor.jsx";
import { appendSection, docHasHeading, docIsEmpty } from "../lib/docText.js";

/* 편집기는 **지연 로드**한다 — TipTap 과 확장 열둘을 진입 번들에 넣지 않는다.
 * `ui/block-editor-lazy.test.jsx` 가 소스 전체에서 정적 import 를 금지한다. */
const BlockEditor = React.lazy(() =>
  import("../ui/BlockEditor.jsx").then((m) => ({ default: m.BlockEditor })),
);
import { useRowSelection, selectionColumn } from "../ui/bulkSelect.jsx";
import { pathText } from "../ui/OrgPath.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, LINE_HEIGHT } from "../ui/theme.js";
import { BASELINE_TRACKS, CONTENT_PAIR_CONTAINER, FORM_FIELD_CONTAINER, FORM_FIELD_GRID_12, PAGE_FILL_HEIGHT, contentPairTracks, fieldSpan } from "../ui/density.js";
import { EMPTYABLE_SELECT, EntityCombobox } from "../ui/filters.jsx";
import { UserPicker } from "../ui/UserPicker.jsx";
import { useQueryState } from "../lib/useQueryState.js";
import { TICKET_AUTO_MAX_ROWS, eligibleProjects, useAssigneeOptions, useTicketList, useTicketMeta, useTicketProjects, useWorkStatuses, statusOptions, ticketProjectId, ticketRows } from "./ticket-options.js";
import { invalidateTicketViews } from "./ticket-views.js";
import { useCelebrateOnCleared, celebrateIfCompleted, doneStatusKeys } from "../ui/celebrate.js";
import { bulkFailureNote, fmtDateTime } from "../lib/format.js";
import { NumberCell, DateCell } from "../ui/cells.jsx";
import { TicketEmptyState, TicketFilterBar, applyColumnFilter, clearTicketFilters, columnFilterValue, hasTicketFilter, nextTicketSort, ticketFilterSpec, ticketQueryParams, ticketSortOf, TICKET_LIST_EXTRA } from "./TicketFilterBar.jsx";
import { openStatusKeys } from "../lib/openTicketStatuses.js";
import { TicketSignals } from "../ui/TicketSignals.jsx";
import { InlineEdit } from "../ui/InlineEdit.jsx";
import { SIGNALS, useTicketSignals } from "../lib/ticketSignals.js";

/** 차단 사유 글자 한도. 서버 계약(`app/tickets/schemas.py::TicketUpdate`)과 같은 수다 —
 *  여기서 막아야 사용자가 500자를 넘겨 적고 저장 버튼에서야 그 사실을 알지 않는다. */
const BLOCKED_REASON_MAX = 500;
import { useListMemory } from "../lib/listReturn.js";
import { failureText, latestMutation } from "../lib/failure.js";
import { useGuardedMutation } from "../lib/useGuardedMutation.js";

/* `EMPTYABLE_SELECT` 는 이제 ui/filters.jsx 가 정본이다(필터 select 와 편집 폼 select 가
 * 같은 함정을 밟는다). 여기서 다시 내보내는 이유는 팀 티켓 화면이 예전부터 이 경로로
 * 가져다 쓰기 때문이다 — 옮기면서 import 경로만 바꾸는 변경을 화면마다 흩뜨리지 않는다. */
export { EMPTYABLE_SELECT };

// 일괄 삭제(휴지통) 뮤테이션 — page_ids 를 보낸다. 전부 옮겼으면 토스트로 알리고, 실패 · 일부 건너뜀은
// 목록 위 메시지 박스가 말한다(`listActionNotice`) — 몇 건이 왜 안 됐는지는 사라지면 안 되는 사실이다.
function useBulkTrash(path, qc, toast, onDone) {
  return useMutation({
    mutationFn: (ids) => api(path, { method: "POST", body: { page_ids: ids } }),
    onSuccess: (res) => {
      const n = (res.trashed || []).length;
      const failed = res.failed || [];
      // UA-25 — Trash.jsx와 같은 이유로 실제 사유를 보여준다(전엔 항상 "권한이 없어"였다).
      if (!failed.length) toast(`${n}건을 휴지통으로 보냈습니다.`, "success");
      // refetchType:"all" — 지금 화면에 없는(비활성) 목록까지 즉시 다시 불러와, 삭제 후 어느 페이지로
      // 가도 최신으로 보이게 한다(이전엔 비활성 목록이 stale로만 남아 '자동 갱신 안 됨'처럼 보였다).
      // 어떤 키가 티켓을 그리는지는 ticket-views.js 한 곳이 안다(홈·스프린트가 여기서 빠져 있었다).
      invalidateTicketViews(qc, { refetchType: "all" });
      // 문서 목록은 여기서 안 부른다 — 이 훅은 티켓만 지운다(두 호출부 다
      // `/api/tickets/trash-bulk`). 예전에는 `["team-docs"]` 를 함께 불렀는데 그 키를 쓰는
      // 질의는 이제 없고, 있었더라도 티켓 삭제가 문서 목록을 바꾸지는 않는다.
      qc.invalidateQueries({ queryKey: ["trash"], refetchType: "all" });
      onDone && onDone();
    },
  });
}

/* 목록 동작(일괄 삭제 · 나에게 배정)의 결과 중 **남아야 하는 것** — 실패와 일부 건너뜀.
 * 가장 나중에 보낸 동작 하나만 말한다(`lib/failure.js`): 다음 동작을 누르면 걷히고, 그 동작이
 * 성공하면 다시 서지 않는다. 문구는 토스트 때와 같다.
 * 상자는 `c-screen` 의 직계 자식이라 아래 간격은 화면 리듬 규칙(`styles/screens.css` 의 `.c-screen > .k-callout` 16px)이
 * 정한다. 예전의 `sx mb` 12px 은 그 규칙에 늘 져서 한 번도 그려지지 않았다(UI 3차 조사 부록) — 걷었다. */
function listActionNotice(bulk, claim) {
  const failure = failureText(
    [bulk, "삭제하지 못했습니다. 다시 시도해 주세요."],
    [claim, "배정하지 못했습니다. 잠시 후 다시 시도해 주세요."],
  );
  if (failure) return <Callout tone="danger" compact>{failure}</Callout>;
  const last = latestMutation(bulk, claim);
  const res = last === bulk && bulk.isSuccess ? bulk.data : null;
  const failed = (res && res.failed) || [];
  if (!failed.length) return null;
  return (
    <Callout tone="warn" compact>
      {`${(res.trashed || []).length}건을 휴지통으로 보냈습니다.` + bulkFailureNote(failed)}
    </Callout>
  );
}

/* 사용자 셀프서비스 — 내 업무(홈)·내 티켓·미할당 티켓.
 * 데이터는 /api/tickets/*(백엔드가 세션 사용자 기준으로 본인 것만 준다 — 브라우저는 notion id를
 * 주지 않는다). 편집은 도우미를 통해 수동으로 한다(Notion 직접 진입 없이) — 담당자 배정·예상 WD·
 * 난이도·우선순위·진행상태·마감 수정. 소유권/스키마 검증은 서버가 판단한다. 상태 색은 kit Badge.
 *
 * 2026-08 MUI 재설계: 표·툴바·폼을 MUI로 옮겼다. 예전에는 screens.css/kit.css의 px 값(.k-table
 * font-size:14px 등)에 묶여 있어 4K에서 글자만 그대로 남고 여백만 커졌다 — 이제 전부 rem/테마
 * 값이라 styles/root.css의 루트 폰트사이즈 레버 하나로 같이 커진다. px 폰트사이즈는 새로 쓰지 않는다. */

/* 티켓 이름은 서버가 준다(`key` = `<CODE>-<SEQ>`). 여기서 접두사를 붙여 이름을
   만들어 내지 않는다 — 그렇게 만든 문자열은 제품 어디에도 없는 이름이라, 복사해
   붙여 넣어도 아무 티켓이 안 열린다. */
function ticketId(t) { return (t && t.key) || "-"; }

// 행/‘상세’ 클릭 → 우리 화면의 티켓 상세로 간다(문서처럼). 원본(노션)은 상세에서 '원본 열기'로.
function ticketPath(t) { return "/tickets/" + (t && t.id); }

/* 티켓 상세로 갈 때 **어디서 왔는지**를 함께 넘긴다 (사용자 지적 #14).
 * 사이드바는 `/tickets/:id` 에 맞는 메뉴 항목이 없어서, 이 값이 없으면 선택 표시가
 * `ROUTE_OWNER` 의 기본값('내 티켓')으로 떨어진다 — 미할당에서 연 티켓인데 '내 티켓'이
 * 켜져 있으면 사용자는 자기가 어디에 있는지 알 수 없다. */
function openTicket(nav, from) {
  return (t) => nav(ticketPath(t), { state: { from } });
}

// 제목(이름)을 눌러야 상세로 간다 — 행 전체 클릭은 없앤다(체크박스 오클릭으로 상세 이동하던 불편 제거).
// t.id가 없으면 링크로 만들지 않는다 — 스프린트 화면의 담당자별 목록은 서버가 아직 앱 티켓 id를
// 주지 않는 행(reports의 _ticket_detail)을 섞어 받을 수 있는데, 그걸 링크로 그리면 '/tickets/undefined'
// 라는 없는 경로로 보내게 된다(눌리는데 아무 데도 못 가는 링크보다 링크가 없는 편이 정직하다).
// 모양(링크색 600 · 말줄임 · title)은 kit 의 `TitleCell` 이 갖는다 — 게시판 · 휴지통 · 프로젝트 표와 같은 제목 칸이다.
function ticketTitleCell(t, onOpen) {
  return <TitleCell title={t.title} onOpen={onOpen && t.id ? () => onOpen(t) : undefined} />;
}

// 목록 표 — 티켓/제목/상태/우선순위/난이도/예상WD/마감. 숫자·날짜는 우측 정렬.
// onEdit/onClaim 을 주면 우측에 액션 열(편집·나에게 배정)이 붙는다. onOpen 을 주면 제목이 상세 링크.
// width는 rem이다 — 4K에서 루트 폰트사이즈가 커지면 열 폭도 같이 커져야 글자와 비율이 맞는다.
//
// compact: **핵심 열만** 남긴다(계획서 4K 계약의 "900–1536 표(핵심열)"). 홈처럼 2단 배치의
// 좁은 열 안에 표가 들어갈 때 쓴다. 전체 열을 그대로 넣으면 1366 화면에서 마감·편집이 잘려
// 나가 가로로 긁어야 보인다 — 실제 캡처에서 그 상태였다. 난이도·예상 WD 는 '오늘 뭘 할까'를
// 정하는 데 필요 없고, 편집은 글자 대신 아이콘 버튼으로 줄여 자리를 아낀다.
//
// claimingId: 「나에게 배정」이 진행 중인 티켓의 id 다. 그동안 그 줄의 단추는 진행 중을 말하고, 모든 줄의
// 배정 단추가 꺼진다(휴지통의 복원 단추와 같은 규칙). 예전에는 단추가 안 꺼져 더블클릭의 둘째 요청이 첫 요청의
// 배정 잠금에 걸렸고, 사용자는 「다른 사람이 지금 이 티켓을 배정하고 있습니다」라는 거짓 문장을 봤다.
export function ticketColumns({ showAssignee, onEdit, onClaim, claimingId = null, onOpen, compact, filterAssignee, signalsOf, statusEdit } = {}) {
  /* `signalsOf` 는 티켓 하나의 **켜져 있는 신호**를 돌려주는 함수다
   * (`lib/ticketSignals.js::useTicketSignals`). 화면이 주지 않으면 신호를 안 그린다 —
   * 어휘 질의가 아직 안 왔거나 시험이 표만 볼 때가 그 경우이고, 그때 빈 알약을 그리면
   * 「신호가 없다」와 「아직 모른다」가 같은 그림이 된다.
   *
   * 밀도가 둘인 이유는 `ui/TicketSignals.jsx` 에 적었다: 좁은 표는 상태 칸에 아이콘만
   * 딸려 서고, 넓은 표는 자기 열에서 낱말을 쓴다. 어휘와 색은 한 표에서 나온다. */
  const marksOf = (t) => (signalsOf ? signalsOf(t) : []);
  /* `statusEdit` 는 「이 표에서 상태를 그 자리에서 바꿀 수 있다」는 선언이다 (지시 18).
   * `{ options, save(ticket, next) }` 를 준다. 안 주면 상태는 예전처럼 읽기만 한다 —
   * 바꿀 수 없는 표에 눌리는 컨트롤을 두지 않는다(`ui/InlineEdit.jsx` 의 `locked` 규칙). */
  const editableStatus = statusEdit && (statusEdit.options || []).length > 0;
  // nowrap: 한 덩어리 값(티켓 번호·날짜·숫자)은 절대 줄바꿈하지 않는다. 예전에는 모든 셀이
  // `overflowWrap: anywhere` 라 열의 최소 폭이 '한 글자'가 됐고, 폭이 모자라면 'GIT-4101'이
  // 세 줄로 쪼개져 세로로 무너졌다(QA vertical_text_collapse). 폭이 정말 모자라면 표를 줄이는
  // 대신 TableContainer 가 스스로 가로 스크롤한다 — 읽을 수 없는 표보다 낫다.
  const cols = [
    /* 티켓 번호는 **식별자형 숫자**다 — 크기를 비교하지 않으므로 좌정렬이고, 자릿수만
       고정한다. 그 뜻을 표가 `data-col-role="identifier"` 로 내보내 QA 가 이 열을 «우정렬
       안 된 숫자 열» 로 세지 않는다. */
    /* 번호는 `AAAAAA-123456` 같이 접두 여섯 + 숫자 여섯까지 한 줄이다. 예전 7rem 은
       접두가 긴 값이 두 줄로 접혀 행 높이가 들쭉날쭉했다. 식별자 기본(anywhere)은
       끄고, 폭이 모자라면 표를 가로로 민다. */
    /* 폭은 티켓 번호 길이가 정한다(코드 열 — 값 길이, D-529). 예전 고정 10rem 은 「MQHENX-8」 옆이 비었다. 그리는 함수만 있는
       열은 열 계획이 값을 재지 않으므로(`columnPlan.js::columnValueText`) 같은 글을 `value` 로 말한다 — 없을 때는 바닥(6.5rem)에
       머물러 홈 지연 표에서 「SXDNMW...」처럼 번호가 잘렸다(r23 캡처 01). */
    { key: "tid", label: "티켓", type: "code",
      nowrap: true, sortable: true, value: (t) => ticketId(t), render: (t) => ticketId(t) },
    // minWidth: 제목 열이 절대 그 아래로 줄지 않는 폭. 나머지 열이 전부 고정폭 + nowrap 이라,
    // 컨테이너가 좁으면(홈의 2단 배치, 1366 화면) 제목만 남은 폭을 다 먹히고 24px 로 눌려
    // 글자가 한 음절씩 세로로 무너졌다(QA vertical_text_collapse 가 실제로 잡았다).
    // rowName: 이 표에서 행을 구별하는 값은 제목이다(ui/rowName.js). 선택 체크박스와 상세
    // 열기 버튼이 이 값을 접근 이름에 쓴다 — 없으면 스무 행이 전부 "이 항목 선택"으로 읽힌다.
    { key: "title", label: "제목", type: "title", min: compact ? "11rem" : undefined, sortable: true, rowName: (t) => t.title || "제목 없음",
      /* 제목이 티켓을 연다 — 표에 숨긴 열이 있으면 「행을 열면 숨긴 값도 볼 수 있습니다」가 맞는 안내다(kit `rowsOpenable`). */
      opensRow: !!onOpen,
      render: (t) => ticketTitleCell(t, onOpen) },
    { key: "status", label: "상태", type: "status", sortable: true, filter: { kind: "enum", field: "status" },
      render: (t) => (t.status
        ? (
          <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5, minWidth: 0 }}>
            {editableStatus ? (
              /* 상세로 들어갔다 나오지 않고 여기서 바꾼다. 저장 중 표시·서버 값 반영·
                 실패 시 원복은 전부 `InlineEdit` 의 상태 기계가 한다 — 이 표가 그 규칙을
                 다시 적으면 다른 자리와 갈라진다. */
              <InlineEdit
                value={t.status}
                options={statusEdit.options}
                canEdit
                label="상태"
                rowName={t.title || (t.key || "")}
                render={(v) => <Badge value={v} />}
                onSave={(next) => statusEdit.save(t, next)}
              />
            ) : (
              <Badge value={t.status} />
            )}
            {compact ? <TicketSignals signals={marksOf(t)} variant="mark" /> : null}
          </Box>
        )
        : "-") },
    { key: "priority", label: "우선순위", type: "status", sortable: true, hideNarrow: true, filter: { kind: "enum", field: "priority" }, render: (t) => (t.priority ? <Badge value={priorityKo(t.priority)} kind={priorityKind(t.priority)} /> : "-") },
  ];
  /* ── 칸이 좁을 때 **접히는 열** (`hideNarrow` · D-380) ──────────────────────
   *
   * 티켓 열셋을 1366 화면(칸 1020px)에 다 세울 방법은 없다. 표는 들어갈 때까지 열 목록의
   * **뒤에서부터** 접으므로, 접히는 순서는 여기 적은 순서의 역순이다:
   * 생성 일자 → 실제 WD → 예상 WD → 난이도 → 우선순위.
   *
   * 접지 않는 것을 고른 이유가 더 중요하다. 티켓 번호·제목·상태·마감·담당자·행 동작은
   * 「무엇이 누구 것이고 언제까지인가」라서 이 목록의 존재 이유다. **신호도 안 접는다** —
   * 지연·차단·이슈는 「지금 무엇이 잘못됐나」이고, 그것을 접으면 목록을 보는 이유가 하나
   * 사라진다. 접힌 값은 행을 열면 상세에 그대로 있고, 표가 무엇을 접었는지 한 줄로 말한다. */
  if (!compact) {
    /* 신호는 상태와 **다른 축**이라 다른 열이다 (D-349). 한 칸에 넣으면 「진행 중」과
       「차단됨」이 한 낱말처럼 읽히고, 정렬·필터도 둘을 못 가른다. */
    cols.push({
      /* 신호는 둘이 함께 설 수 있다(「차단됨」 · 「지연」) — 바닥 9rem 이 둘을 한 줄에 세운다. */
      key: "_signals", label: "신호", type: "status", min: "9rem", nowrap: true,
      render: (t) => <TicketSignals signals={marksOf(t)} />,
    });
    cols.push(
      /* 난이도는 «상·중·하» 라 수치가 아니다 — 우정렬하면 없는 크기 비교를 암시한다. */
      { key: "difficulty", label: "난이도", type: "enum", sortable: true, hideNarrow: true, filter: { kind: "enum", field: "difficulty" }, render: (t) => (t.difficulty || "-") },
      { key: "est_wd", label: "예상 WD", type: "number", sortable: true, hideNarrow: true, filter: { kind: "number", field: "est_wd" }, render: (t) => <NumberCell value={t.est_wd} /> },
      { key: "act_wd", label: "실제 WD", type: "number", sortable: true, hideNarrow: true, filter: { kind: "number", field: "act_wd" }, render: (t) => <NumberCell value={t.act_wd} /> },
    );
  }
  cols.push({ key: "due", label: "마감", type: "date", sortable: true, render: (t) => (t.due || "-") });
  if (!compact) {
    /* 「추가」는 무엇을 추가했다는 말인지 알 수 없었다 — 이 값은 티켓이 만들어진 날이다. */
    cols.push({ key: "created_at", label: "생성 일자", type: "datetime", sortable: true, hideNarrow: true, filter: { kind: "date", field: "created_at" }, render: (t) => <DateCell value={t.created_at} /> });
  }
  if (showAssignee) {
    // VIS-163: 이 열만 nowrap이 빠져 있었다 — 좁은 컨테이너(1200×900)에서 overflowWrap:
    // anywhere가 "임승환, 김동현" 같은 값을 글자 하나씩 세로로 무너뜨렸다(다른 모든 열의
    // 이유와 같다, 위 주석 참고). 담당자가 많아 셀이 넓어지면 이 표도 다른 nowrap 열처럼
    // 가로 스크롤로 넘긴다 — 읽을 수 없는 표보다 낫다는 같은 트레이드오프.
    cols.push({
      key: "assignee_names", label: "담당자", type: "name", nowrap: true,
      filter: filterAssignee ? { kind: "entity", field: "assignee_user_id" } : undefined,
      render: (t) => {
        const people = Array.isArray(t.assignee_people) ? t.assignee_people : [];
        if (people.length) {
          return (
            <Box sx={{ display: "inline-flex", alignItems: "center", verticalAlign: "middle", gap: 0.75, minWidth: 0 }}>
              {people.slice(0, 2).map((p) => (
                <PersonLine
                  key={p.user_id || p.name}
                  person={p}
                  name={p.name || p.display_name}
                  size="inline"
                />
              ))}
              {people.length > 2 ? (
                <Typography variant="caption" color="text.secondary">
                  {`외 ${people.length - 2}명`}
                </Typography>
              ) : null}
            </Box>
          );
        }
        return ((t.assignee_names || []).join(", ") || "-");
      },
    });
  }
  if (onEdit || onClaim) {
    cols.push({
      key: "_actions", label: "", type: "actions",
      min: onClaim ? "13rem" : compact ? "3.5rem" : "6rem",
      nowrap: true,
      /* 행 동작은 `RowActions` 다 — 30 보조 단추이고 채움이 없다(조합 계약 C-4). 「나에게 배정」이 행마다 채움이었을 때
         미할당 목록 한 화면에 채움이 스무 개 섰다. 좁은 열(홈의 핵심 열 표)에서 수정은 글자 대신 아이콘이고 이름은
         `aria-label` 이 든다. */
      render: (t) => (
        <RowActions
          actions={[
            onClaim ? {
              key: "claim", label: "나에게 배정",
              disabled: claimingId != null, loading: claimingId === t.id,
              onClick: () => onClaim(t),
            } : null,
            onEdit ? (compact
              ? { key: "edit", label: "수정", ariaLabel: "수정: " + (t.title || "제목 없음"), icon: <EditOutlinedIcon fontSize="small" />, onClick: () => onEdit(t) }
              : { key: "edit", label: "수정", onClick: () => onEdit(t) }) : null,
          ]}
        />
      ),
    });
  }
  return cols;
}

/* 편집 드롭다운 옵션 — 현재 값이 목록에 없으면(메타 미로딩·옵션 rename) 맨 앞에 끼워 넣어
 * '현재 값이 화면에서 사라지는' 문제를 막는다(kit FormField selNeedEmpty 와 같은 취지). */
function withCurrent(list, cur) {
  const opts = Array.isArray(list) ? list : [];
  if (cur && !opts.includes(cur)) return [cur, ...opts];
  return opts;
}
function sameSet(a, b) {
  return [...(a || [])].sort().join(",") === [...(b || [])].sort().join(",");
}

// 티켓을 프로젝트별로 묶는다(대표 프로젝트명 기준). 이름 없는 티켓은 '프로젝트 없음'으로 맨 뒤에.
function groupByProject(rows) {
  const map = new Map();
  for (const t of rows) {
    const key = t.project || "프로젝트 없음";
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(t);
  }
  return [...map.entries()].sort((a, b) => {
    if (a[0] === "프로젝트 없음") return 1;
    if (b[0] === "프로젝트 없음") return -1;
    return a[0].localeCompare(b[0]);
  });
}

// ctx: kit.jsx DataTable과 같은 규칙(cellValue) — 선택 체크박스처럼 셀 안에서 '자기 행이
// 무엇인지' 알아야 하는 렌더러에 rowName을 건넨다. 이게 없으면 ctx가 항상 undefined라
// selectionColumn의 render가 매 행 "이 항목 선택"으로 떨어진다(DataTable에서 이미 고친
// 접근성 버그가 GroupedTickets에는 안 옮겨져 있었다 — ui/row-select-name.test.jsx 참고).
function groupedCell(c, t, ctx) {
  if (c.render) return c.render(t, ctx);
  const v = t[c.key];
  return v == null || v === "" ? "-" : String(v);
}
// 그룹 안에서 같은 티켓이 여러 그룹에 들어갈 수 있어(담당자 다중 배정) 그룹별로만 유일하면 된다.
// 앱 id가 없는 행(스프린트 담당자별 파생 rows)도 안전하게 키를 얻도록 tid·인덱스로 폴백한다.
function groupedRowKey(t, i) {
  if (t && t.id != null) return String(t.id);
  if (t && t.tid != null) return "tid-" + t.tid;
  return "i-" + i;
}

/* 그룹 기준으로 묶어 '하나의 표'로 그린다(그룹마다 별도 table을 쓰면 열 너비가 어긋남). 기본은
 * 프로젝트별, groupBy 를 주면 담당자별 등 다른 기준으로. 행 전체는 클릭 대상이 아니다 — 제목만 상세로.
 *
 * **이 부품은 이제 표를 직접 그리지 않는다.** 오래 `DataTable` 과 나란히 자기 `<Table>` 을
 * 그렸고, 그것을 붙잡고 있던 것은 묶음 머리행 하나였다. 그 대가는 이 파일이 여러 번 적어 둔
 * 그대로다 — 열 폭·정렬·말줄임·카드 접기 규칙이 두 벌이 되어 「팀 티켓은 접히는데 내 티켓은
 * 안 접히는」 상태가 실제로 두 번 났다. 지금은 표가 묶음을 안다(`groupOf`·`groupCollapsible`)
 * 이라 규칙이 한 벌이다.
 *
 * 남는 일은 셋뿐이다: 어떤 기준으로 묶을지 정하고, 행을 그 순서로 펴고, 티켓 도메인의 조건
 * 조회(`columnFilterValue` — 기간·범위는 한 필드가 아니라 두 칸에 흩어져 산다)를 표에 건넨다. */
export function GroupedTickets({ rows, columns, empty, emptyHelp, emptyState, groupBy, collapsible, sort, onSort, filters, onFilter, filterOptions, entityOptions, placement, list, selection, note }) {
  const safeRows = Array.isArray(rows) ? rows : [];
  const grouper = groupBy || groupByProject;

  /* 묶음 순서대로 편 행과, 그 행이 어느 묶음인지의 **나란한 목록**.
   *
   * 행에 묶음 이름을 실어 보내지 않는 이유: 같은 티켓이 여러 묶음에 들어갈 수 있고(담당자
   * 다중 배정) 그때 행 객체를 복제하면 `render(t)` 가 받는 것이 원본이 아니게 된다. 표는
   * `groupOf(row, i)` 로 자리를 물어보므로 나란한 배열이면 충분하다. */
  const groups = grouper(safeRows);
  const flatRows = [];
  const rowGroup = [];
  for (const [name, items] of groups) {
    for (const t of items) { flatRows.push(t); rowGroup.push(name); }
  }

  return (
    <DataTable
      columns={columns}
      rows={flatRows}
      /* 키는 **묶음까지 포함해야** 유일하다 — 같은 티켓이 두 묶음에 서면 id 만으로는 겹친다. */
      rowKey={(t, i) => rowGroup[i] + "::" + groupedRowKey(t, i)}
      groupOf={(t, i) => rowGroup[i]}
      groupCollapsible={collapsible}
      emptyState={emptyState || <EmptyState title={empty || "표시할 티켓이 없습니다."} help={emptyHelp} />}
      sort={sort}
      onSort={onSort}
      filters={filters}
      filterValueOf={columnFilterValue}
      onFilter={onFilter}
      filterOptions={filterOptions}
      entityOptions={entityOptions}
      /* 목록 판 · 발(받은 건수 · 「더 보기」 · 선택 묶음)은 표가 그린다 — 이 부품은 넘기기만 한다(조합 계약 C-3). */
      placement={placement}
      list={list}
      selection={selection}
      note={note}
    />
  );
}

/* 편집 모달용 후보/옵션은 모달이 열릴 때만 불러온다(enabled:open) — 목록 화면 초기 로드를
 * 늘리지 않는다. 질의 자체는 `ticket-options.js` 가 갖는다(공용 필터 줄이 같은 목록을 쓴다).
 *
 * 담당자 선택 — 편집 모달과 새 티켓 폼이 같은 마크업을 쓴다(예전엔 .k-check-list를 두 곳에
 * 손으로 복사해 두어 한쪽만 고치면 조용히 어긋났다).
 *
 * PA-RC-0035: 예전엔 평면 체크박스 그리드였다 — 후보 수만큼 화면이 그대로 길어져(14명
 * 기준 새 티켓 폼 세로의 상당 부분) 조직이 크면 스크롤 없이는 제출 버튼에 닿지 못했다.
 * 자동완성 입력 + 선택 칩(MUI Autocomplete, 이 저장소에서 첫 사용이지만 이미 설치된
 * @mui/material 안이라 새 의존성은 아니다 — multiple 모드가 다중 선택·칩·키보드 조작·
 * ARIA combobox 시맨틱을 전부 내장해서 준다)으로 바꾸면 후보가 14명이든 50명이든 입력
 * 한 줄 높이는 그대로다. 오프보딩(TargetPicker)·조직 관리(OrgTree)의 기존 사람 선택
 * 화면은 "고른 뒤 그 사람으로 이동/전환"하는 **단일 선택** 패턴이라 여기(다중 배정,
 * 폼 안에 머무름)에 그대로 재사용할 모양이 아니었다 — 그래도 새 컴포넌트를 만들지는
 * 않았다, MUI가 이미 이 상호작용을 위해 제공하는 컴포넌트를 쓴다. */
function AssigneePicker({ loading, candidates, selected, onChange, myId }) {
  /* 로딩은 화면마다 다른 회색 문장을 쓰지 않는다 (R-20) — 들어올 것의 모양을 그린다.
     여기 들어오는 것은 선택 상자 한 줄이라 `lines={1}` 이다. */
  if (loading) return <Skeleton lines={1} />;
  /* 이 문장은 **틀린 원인을 말하고 있었다.** 「Notion에 연결된 사용자 없음」이라고 적혀
     있었는데, 후보를 고르는 규칙은 S15 가 바꿨다(D-285): 서버는 이제 **활성 사용자 전원**
     가운데 그 프로젝트에 닿을 수 있는 사람을 준다. Notion 런타임은 S14 가 걷어서 존재하지도
     않는다. 원인을 잘못 말하는 안내는 없는 것보다 나쁘다 — 사용자가 없는 시스템을 고치러 간다. */
  if (!candidates.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        배정할 수 있는 사람이 없습니다. 이 프로젝트에 접근할 수 있는 계정만 후보로 나옵니다.
      </Typography>
    );
  }
  /* 고르개는 사람 고르개 정본(`ui/UserPicker.jsx`)이다 — 핸드오프 계획 B-7 · P-6. 예전에는 이 자리가
     MUI 자동완성을 따로 짜서 옵션 줄(이름 + 소속 두 줄)과 칩을 손으로 그렸다. 정본은 한 줄 32 에
     아바타 22 + 이름 + 소속 muted + 고른 사람 체크를 세우고, 내 계정을 맨 위에 둔다.
     `selected` 는 id 배열 그대로다(서버로 보내는 값 — PA-RC-0035 이전과 같은 계약). 후보 밖으로 나간
     id 는 정본이 「이름을 확인할 수 없는 항목」 칩으로 남겨 저장할 때까지 지우지 않는다(아래 도움말 문장
     「앱에 연결되지 않은 기존 담당자는 그대로 유지됩니다」와 같은 약속). */
  return (
    <UserPicker
      multiple
      layout="form"
      label="담당자 검색"
      placeholder="예: 김하나"
      candidates={candidates}
      value={selected}
      onChange={onChange}
      myId={myId}
    />
  );
}

/* 티켓 편집 모달 — Notion에 들어가지 않고 도우미로 담당자·예상 WD·난이도·우선순위·진행상태·마감을
 * 수정한다. 바뀐 필드만 PATCH 한다(exclude_unset). 소유권/스키마 검증은 서버가 판단한다. */
/* 지금 걸려 있는 프로젝트가 목록에 없으면(아카이브됨, 조회 권한 없음) 그 항목을 끼워 넣는다.
 * 안 그러면 select 가 빈 값으로 떨어지고, 저장하는 순간 **손대지도 않은 프로젝트 연결이 끊긴다**.
 * 진행상태·우선순위의 withCurrent 와 같은 취지다. */
function withCurrentProject(projects, currentId) {
  if (!currentId || projects.some((p) => p.id === currentId)) return projects;
  return [...projects, { id: currentId, name: "(목록에 없는 프로젝트)" }];
}

/* `projectScope` — 열린 회차에 담긴 티켓은 **같은 팀의 프로젝트로만** 옮길 수 있다(D-482).
 * 작업 보드·미리보기가 `{ teamId, note }` 를 넘기면 프로젝트 후보를 그 팀으로 좁히고 한 줄로
 * 이유를 말한다. 서버 검증(422)은 그대로 정본이다 — 골라서 거절당하는 것은 안내가 아니다. */
export function TicketEditModal({ ticket, open, onClose, projectScope }) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const assigneesQ = useAssigneeOptions(open);
  const metaQ = useTicketMeta(open);
  const projectsQ = useTicketProjects(open);
  /* 「완료로 옮겼는가」는 상태 **어휘**가 답한다 — 이 폼은 이미 같은 질의를 쓰고 있고
     (`useWorkStatuses`, 5분 캐시·같은 키) 요청이 늘지 않는다. */
  const statusesQ = useWorkStatuses(open);
  const doneKeys = React.useMemo(() => doneStatusKeys(statusesQ.data), [statusesQ.data]);
  const [form, setForm] = React.useState(null);
  React.useEffect(() => {
    if (!open || !ticket) { setForm(null); return; }
    setForm({
      title: ticket.title || "",
      // 프로젝트 축은 `ticket-options.js` 한 곳이 고른다 — 옛 relation id 를 그대로 넣으면
      // 후보 목록(Portal id)에 그 값이 없어 프로젝트가 **없는 것처럼** 보인다.
      project_id: ticketProjectId(ticket),
      status: ticket.status || "",
      priority: ticket.priority || "",
      difficulty: ticket.difficulty || "",
      est_wd: ticket.est_wd != null ? String(ticket.est_wd) : "",
      act_wd: ticket.act_wd != null ? String(ticket.act_wd) : "",
      due: ticket.due || "",
      start: ticket.start || "",
      category: ticket.category || "",
      assignees: [...(ticket.assignee_user_ids || [])],
      /* Signal — 상태와 직교하는 축 (D-349). 「지연」은 여기 없다: 마감일과 종료 여부에서
         계산하는 값이라 사람이 켤 것이 아니다(`lib/ticketSignals.js`). */
      issue: !!ticket.issue,
      blocked: !!ticket.blocked,
      blockedReason: ticket.blocked_reason || "",
    });
  }, [open, ticket]);
  /* 같은 고침은 끝나기 전에 한 번만 나간다(`useGuardedMutation`). 이 폼은 Enter 로 제출되는데 그 Enter 는 발의
     「저장」이 아니라 폼 안의 숨은 제출 단추를 누르고, 그 단추는 저장 중에도 꺼지지 않는다 — 예전에는 Enter 두 번이
     같은 PATCH 두 번이었다. */
  const m = useGuardedMutation({
    mutationFn: (changes) => api(`/api/tickets/${ticket.id}`, { method: "PATCH", body: changes }),
    /* 이 모달은 홈·스프린트·프로젝트 티켓 등 **여러 화면에 얹혀 있다.** 그래서 무효화 대상을
     * 여기서 정하면 안 된다 — 얹히는 화면이 늘 때마다 빠뜨린다(실제로 홈·스프린트가 빠져 있었다).
     * 티켓을 그리는 질의 키는 ticket-views.js 가 한 곳에서 안다. */
    /* 두 번째 인자는 이 뮤테이션에 넘긴 `changes` 다. `buildChanges` 가 **바뀐 값만**
       담으므로, 여기 `status` 가 있다는 것이 곧 「이번에 상태를 옮겼다」이다 — 이미
       완료인 티켓의 제목만 고친 저장에는 이 칸이 없어서 축하하지 않는다.
       모달을 먼저 닫는다: 종잇조각이 폼 위가 아니라 끝낸 티켓 위로 쏟아져야 한다. */
    onSuccess: (_res, changes) => {
      toast("티켓을 저장했습니다.", "success");
      invalidateTicketViews(qc);
      onClose();
      celebrateIfCompleted(changes && changes.status, doneKeys);
    },
  });
  /* 모달은 닫혀도 자리를 지키므로(`return null`) 요청 상태가 남는다 — 다시 열 때 지난 실패를 걷는다. */
  React.useEffect(() => { if (open) m.reset(); }, [open, ticket]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!open || !ticket || !form) return null;

  const meta = metaQ.data || {};
  const candidates = (assigneesQ.data && assigneesQ.data.assignees) || [];
  /* 칸을 고치면 그 칸의 오류를 걷는다 — 오류는 폼 상태(`form.errors`)에 들어 있어 모달을 다시 열면
     폼과 함께 새로 선다. */
  const set = (k, v) => setForm((s) => ({ ...s, [k]: v, errors: s.errors && s.errors[k] ? { ...s.errors, [k]: null } : s.errors }));
  const invalid = (k, message) => setForm((s) => ({ ...s, errors: { [k]: message } }));
  const fieldError = (k) => (form.errors && form.errors[k]) || null;

  function buildChanges() {
    const c = {};
    if (form.title.trim() !== (ticket.title || "")) c.title = form.title.trim();
    if (form.project_id !== ticketProjectId(ticket)) c.project_id = form.project_id;
    if (form.status !== (ticket.status || "")) c.status = form.status;
    if (form.priority !== (ticket.priority || "")) c.priority = form.priority;
    if (form.difficulty !== (ticket.difficulty || "")) c.difficulty = form.difficulty;
    const initWd = ticket.est_wd != null ? String(ticket.est_wd) : "";
    if (form.est_wd !== initWd) c.est_wd = form.est_wd === "" ? null : Number(form.est_wd);
    const initAct = ticket.act_wd != null ? String(ticket.act_wd) : "";
    if (form.act_wd !== initAct) c.act_wd = form.act_wd === "" ? null : Number(form.act_wd);
    if (form.due !== (ticket.due || "")) c.due_date = form.due;
    if (form.start !== (ticket.start || "")) c.start_date = form.start;
    if (form.category.trim() !== (ticket.category || "")) c.category = form.category.trim();
    if (!sameSet(form.assignees, ticket.assignee_user_ids || [])) c.assignee_user_ids = form.assignees;
    if (form.issue !== !!ticket.issue) c.issue_flag = form.issue;
    /* `blocked_flag` 를 `blocked_reason` **앞에** 싣는다. 서버는 사유를 적용할 때 그 순간의
       차단 여부를 보므로(`repository_native.update`), 순서가 뒤집히면 「막혔다 + 이유」를 한
       번에 저장할 때 이유만 조용히 버려진다. */
    if (form.blocked !== !!ticket.blocked) c.blocked_flag = form.blocked;
    /* 사유는 차단이 켜져 있을 때만 뜻이 있다. 차단을 풀면 서버가 사유도 함께 지우므로
       (지난 이유가 다음 차단에 그대로 붙어 나오면 그 말은 이미 틀렸다) 여기서 안 보낸다. */
    const initReason = ticket.blocked_reason || "";
    if (form.blocked && form.blockedReason.trim() !== initReason) {
      c.blocked_reason = form.blockedReason.trim();
    }
    return c;
  }

  /* 검증 실패는 **그 칸 아래**에 선다(핸드오프 RULES §1 · §7) — 토스트는 몇 초 뒤 사라지고 어느 칸인지도
     말하지 않았다. 검사 순서와 문구는 그대로이고, 예전처럼 처음 걸린 하나만 말한다. */
  function submit() {
    if (!form.title.trim()) { invalid("title", "제목은 비울 수 없습니다."); return; }
    if (!form.status) { invalid("status", "상태는 비울 수 없습니다."); return; }
    if (form.est_wd !== "" && Number.isNaN(Number(form.est_wd))) { invalid("est_wd", "예상 WD에는 숫자를 입력하세요."); return; }
    if (form.act_wd !== "" && Number.isNaN(Number(form.act_wd))) { invalid("act_wd", "실제 WD에는 숫자를 입력하세요."); return; }
    if (form.blocked && form.blockedReason.trim().length > BLOCKED_REASON_MAX) {
      invalid("blockedReason", `차단 사유는 ${BLOCKED_REASON_MAX}자 이하로 입력하세요.`); return;
    }
    setForm((s) => ({ ...s, errors: null }));
    const changes = buildChanges();
    if (Object.keys(changes).length === 0) { toast("수정한 내용이 없습니다.", "info"); return; }
    m.mutate(changes);
  }

  // 바뀐 필드가 있으면(=buildChanges가 비어있지 않으면) Esc·바깥 클릭·X·'취소' 전부에서
  // 확인을 받는다(VIS-88) — 이 모달은 담당자·마감일 등 여러 필드를 한 번에 고치는데,
  // 실수로 닫으면 전부 다시 입력해야 했다. `Modal`의 `dirty` prop은 Esc/바깥클릭/X만
  // 지킨다 — 하단 '취소' 버튼은 onClose를 직접 불러 그 가드를 우회하므로(Games.jsx가
  // 같은 이유로 이미 겪은 문제) 여기서도 별도 requestClose로 감싼다.
  const changes = buildChanges();
  const dirty = Object.keys(changes).length > 0;
  async function requestClose() {
    if (!dirty) { onClose(); return; }
    const ok = await confirm("입력한 내용이 저장되지 않았습니다. 창을 닫을까요?",
      { danger: true, title: "변경 사항 버리기", confirmLabel: "닫기" });
    if (ok) onClose();
  }
  const footer = <ModalFooter onCancel={requestClose} onSubmit={submit} submitLabel="저장" busy={m.isPending} />;
  const statusOpts = withCurrent(meta.statuses, form.status);
  const prioOpts = withCurrent(meta.priorities, form.priority);
  const diffOpts = withCurrent(meta.difficulties, form.difficulty);
  const projects = (projectsQ.data && projectsQ.data.projects) || [];
  const saveFailure = failureText([m, "저장하지 못했습니다. 잠시 후 다시 시도해 주세요."]);
  return (
    <Modal open={open} onClose={onClose} title={"티켓 수정" + (ticket.key ? ", " + ticket.key : "")} size="md" footer={footer} dirty={dirty}>
      {/* `noValidate` — 검사는 `submit()` 이 칸 아래 제품 문장으로 한다. 없으면 브라우저 기본 말풍선(영문 「Please fill out this
          field.」)이 먼저 떠 그 검사에 닿지 못했다(r23 화면 대장 03-invalid). */}
      <form noValidate onSubmit={(e) => { e.preventDefault(); submit(); }}>
        {/* 제목이 맨 위다 — 이 화면에서 바꾸는 값 중 사용자가 가장 먼저 보는 것이다.
            예전에는 아예 없어서 제목 오타 하나 때문에 노션을 열어야 했다. */}
        <Box sx={{ minWidth: 0 }}>
          <FieldLabel htmlFor="te-title" required>제목</FieldLabel>
          <TextField id="te-title" fullWidth size="small" required sx={{ mb: 2.5 }}
            value={form.title} onChange={(e) => set("title", e.target.value)}
            error={!!fieldError("title")} helperText={fieldError("title") || undefined}
            inputProps={{ maxLength: 200 }} />
        </Box>
        <Box sx={{ mb: 2.5 }}>
          <Typography component="span" variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, display: "block", mb: 1 }}>담당자</Typography>
          <AssigneePicker loading={assigneesQ.isLoading} candidates={candidates} selected={form.assignees} onChange={(ids) => set("assignees", ids)} />
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
            선택한 사람으로 담당자를 설정합니다. 앱에 연결되지 않은 기존 담당자는 그대로 유지됩니다.
          </Typography>
        </Box>
        {/* 짧은 값 입력들은 넓은 화면에서 두 열로 접는다 — 한 열로 길게 쌓으면 모달이 세로로만 길어진다. */}
        <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0,1fr))" } }}>
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel id="te-status-label">진행상태</FieldLabel>
            <TextField SelectProps={{ labelId: "te-status-label" }} id="te-status" select fullWidth size="small" value={form.status} onChange={(e) => set("status", e.target.value)}
              error={!!fieldError("status")} helperText={fieldError("status") || undefined}>
              {statusOptions(statusOpts).map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
            </TextField>
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel id="te-prio-label">우선순위</FieldLabel>
            <TextField id="te-prio" select fullWidth size="small" SelectProps={{ displayEmpty: true, labelId: "te-prio-label" }} value={form.priority} onChange={(e) => set("priority", e.target.value)}>
              <MenuItem value="">없음</MenuItem>
              {prioOpts.map((p) => <MenuItem key={p} value={p}>{priorityKo(p)}</MenuItem>)}
            </TextField>
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel id="te-diff-label">난이도</FieldLabel>
            <TextField id="te-diff" select fullWidth size="small" SelectProps={{ displayEmpty: true, labelId: "te-diff-label" }} value={form.difficulty} onChange={(e) => set("difficulty", e.target.value)}>
              <MenuItem value="">없음</MenuItem>
              {diffOpts.map((d) => <MenuItem key={d} value={d}>{d}</MenuItem>)}
            </TextField>
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel htmlFor="te-wd">예상 WD</FieldLabel>
            <TextField id="te-wd" fullWidth size="small" type="number" inputProps={{ step: "0.5", min: "0" }}
              value={form.est_wd} onChange={(e) => set("est_wd", e.target.value)}
              error={!!fieldError("est_wd")} helperText={fieldError("est_wd") || undefined} />
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel htmlFor="te-act-wd">실제 WD</FieldLabel>
            <TextField id="te-act-wd" fullWidth size="small" type="number" inputProps={{ step: "0.5", min: "0" }}
              value={form.act_wd} onChange={(e) => set("act_wd", e.target.value)}
              error={!!fieldError("act_wd")} helperText={fieldError("act_wd") || "다 끝낸 뒤 실제로 들인 공수"} />
          </Box>
          <DateField id="te-start" label="시작일" value={form.start} onChange={(v) => set("start", v)} />
          <DateField id="te-due" label="마감일" value={form.due} onChange={(v) => set("due", v)} />
          {/* 새 티켓 폼과 **같은 부품**이다 — 같은 값을 고르는 자리가 화면마다 다른 상호작용을
              갖지 않는다(C8 «하나의 Model, 세 개의 표면»). 지금 걸린 프로젝트가 후보에
              없으면(아카이브·권한 밖) `withCurrentProject` 가 끼워 넣는 계약은 그대로다 —
              빠지면 손대지도 않은 프로젝트 연결이 저장 시 끊긴다. */}
          <EntityCombobox
            id="te-proj"
            label="프로젝트"
            value={form.project_id}
            onChange={(v) => set("project_id", v)}
            loading={projectsQ.isLoading}
            disabled={projectsQ.isLoading}
            allLabel="선택 안 함"
            helperText={projectScope && projectScope.teamId ? projectScope.note : undefined}
            sx={{ width: "100%", maxWidth: "none" }}
            options={withCurrentProject(
              projectScope && projectScope.teamId ? eligibleProjects(projects, projectScope.teamId) : projects,
              form.project_id,
            ).map((p) => ({
              value: p.id, label: p.name || "(제목 없음)",
            }))}
          />
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel htmlFor="te-category">대분류</FieldLabel>
            <TextField id="te-category" fullWidth size="small"
              value={form.category} onChange={(e) => set("category", e.target.value)}
              inputProps={{ maxLength: 200 }} />
          </Box>
        </Box>
        {/* 🔴 신호를 켜는 자리가 제품 어디에도 없었다. 서버는 이 세 칸을 받고
            (`app/tickets/schemas.py::TicketUpdate`), 목록·상세·보드·회의·주간보고가 전부
            그 값을 읽어 그리는데, **쓰는 화면이 하나도 없었다.** 그래서 「이슈 있음」 필터도
            보드의 신호 타일도 이관 시점 데이터 말고는 영원히 0 이었다.

            상태 격자 아래에 따로 세운 이유는 이것이 **다른 축**이기 때문이다 — 상태는 하나만
            고르고 신호는 여럿이 함께 켜진다. 같은 격자에 섞으면 둘이 같은 종류로 읽힌다. */}
        <Box sx={{ mt: 2.5 }}>
          <Typography component="span" variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, display: "block", mb: 0.5 }}>신호</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1, ...KO_WORD_BREAK }}>
            진행에 무슨 일이 있는지 표시합니다. 진행상태와 별개라서 함께 켤 수 있습니다. 지연은 마감일에서 자동으로 계산합니다.
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", columnGap: 2 }}>
            <FormControlLabel
              control={<Checkbox id="te-issue" checked={form.issue} onChange={(e) => set("issue", e.target.checked)} />}
              label={SIGNALS.issue.label}
            />
            <FormControlLabel
              control={<Checkbox id="te-blocked" checked={form.blocked} onChange={(e) => set("blocked", e.target.checked)} />}
              label={SIGNALS.blocked.label}
            />
          </Box>
          {/* 사유 칸은 차단을 켰을 때만 선다. 항상 세워 두면 「사유는 적었는데 차단은 안 켜진」
              저장이 생기고, 그 글은 아무 화면에도 안 나온다(서버가 버린다). */}
          {form.blocked ? (
            <Box sx={{ minWidth: 0, mt: 1 }}>
              <FieldLabel htmlFor="te-blocked-reason">차단 사유</FieldLabel>
              <TextField id="te-blocked-reason" fullWidth size="small"
                value={form.blockedReason} onChange={(e) => set("blockedReason", e.target.value)}
                inputProps={{ maxLength: BLOCKED_REASON_MAX }}
                error={!!fieldError("blockedReason")}
                helperText={fieldError("blockedReason") || "무엇이 끝나야 이 일이 다시 움직이는지 적습니다. 목록에서 신호에 마우스를 올리면 보입니다."} />
            </Box>
          ) : null}
        </Box>
        {/* 저장 실패는 발 바로 위 — 누른 단추 곁에 남는다. 다시 저장하면 걷힌다. */}
        {saveFailure ? <Callout tone="danger" compact>{saveFailure}</Callout> : null}
        <button type="submit" className="sr-only" tabIndex={-1} aria-hidden="true" />
      </form>
    </Modal>
  );
}

// 미할당 티켓을 '나에게 배정'하는 뮤테이션 — 성공 시 목록을 다시 불러온다.
// 같은 티켓의 배정은 끝나기 전에 한 번만 나간다. 둘째 요청은 서버의 배정 잠금(`claim_lock.py`)에 걸려
// 409 로 끝나는데, 그 문장은 남이 배정 중이라고 말해서 자기 더블클릭을 남의 경합으로 읽게 한다.
export function useClaim() {
  const qc = useQueryClient();
  const toast = useToast();
  return useGuardedMutation({
    mutationFn: (id) => api(`/api/tickets/${id}/claim`, { method: "POST" }),
    onSuccess: () => { toast("나에게 배정했습니다.", "success"); invalidateTicketViews(qc); },
  });
}

// configured=false(서버가 티켓을 읽지 못함) 공통 안내.
// 반드시 '일반 함수'다, 컴포넌트로 <ConnState/>를 만들면 그 JSX 요소가 항상 truthy라
// `if (conn) return conn`가 언제나 참이 되어 본문(카드, 표)이 통째로 안 그려졌다(빈 화면 버그).
// 문제가 없으면 null을 돌려주고, 호출부는 그 null을 보고 본문을 그린다.
//
// 사내 대부분의 설치에서 이 화면의 첫인상이 바로 이 상태다(Notion 토큰이 없으면 항상 여기로 온다) —
// 경고 한 줄로 끝내지 말고 '지금 무엇을 하면 되는지'까지 EmptyState로 보여준다(kit §9와 같은 규칙).
// 팀 티켓·스프린트 화면도 같은 함수를 쓴다 — 예전엔 화면마다 같은 뜻의 문장을 따로 적어 두어
// 한 곳만 고치면 나머지가 옛 문구로 남았다(연동 미설정은 티켓 화면 전부가 동시에 맞는 상태다).
/* `onRetry` 를 주면 빈 상태에 **다시 불러오기** 버튼이 붙는다.
 *
 * 이 안내는 스스로 "연결이 끝나면 이 화면을 새로고침하세요"라고 말하면서 정작 새로고침할
 * 방법을 주지 않았다(지시 18: 빈 상태에는 다음 행동이 있어야 한다). 안 주면 예전처럼
 * 버튼 없이 안내만 그린다 — 다시 불러올 수단이 없는 호출부가 아직 있기 때문이다. */
export function ticketConnState(data, onRetry) {
  if (data && data.configured === false) {
    return (
      /* 이 갈래는 더 이상 안 열린다 — 티켓의 정본이 이 서버라 사람이 채워 넣을 접속
         설정이 없다(S14 · D-284). 응답 모양은 남아 있으므로 갈래도 남기되, 없어진
         절차를 안내하지는 않는다. */
      <EmptyState
        art="tickets"
        title="지금은 티켓 목록을 불러올 수 없습니다."
        situation="서버가 티켓을 읽지 못했습니다."
        steps={["잠시 뒤 '다시 불러오기'를 누르세요.", "계속 같으면 관리자에게 문의하세요."]}
        expected="다시 불러오면 담당자, 상태, 마감이 담긴 티켓 목록이 이 자리에 표시됩니다."
        action={onRetry ? <Button onClick={onRetry}>다시 불러오기</Button> : null}
      />
    );
  }
  /* 여기 「내 계정이 Notion 사용자와 연결되어 있지 않습니다」 갈래가 있었다 (S15).
   *
   * 그 문장은 두 번 틀렸다. 첫째, 안내한 절차(‘관리자에게 Notion 사용자 연결을
   * 요청하세요’)를 아무도 수행할 수 없다 — 연결할 상대가 없어졌다. 둘째, 그 상태는
   * 이제 존재하지 않는다: 사람마다 담당자로 가리킬 값이 언제나 있다(D-285). 실제로
   * 그 갈래에 걸려 있던 계정 둘은 「연결을 기다리라」는 말을 읽으며 자기 티켓 목록을
   * 영원히 못 보고 있었다. */
  if (data && data.ok === false && data.error) {
    return <Callout tone="danger">{data.error}</Callout>;
  }
  return null;
}


/* 내 티켓·미할당이 쓰는 필터 조건.
 *
 * 담당자를 빼는 이유는 서버가 그 조건을 **이 두 경로에서 안 받기** 때문이다
 * (`build_filters(allow_assignee_filter=False)`): 내 티켓의 담당자는 언제나 세션 사용자이고,
 * 미할당은 정의상 담당자가 없다. 안 먹는 조건을 그려 두면 고른 값이 아무 일도 안 하는데,
 * 그건 사용자가 알아챌 수 없는 방향의 오류다.
 *
 * `/mine` 의 기본 상태는 워크플로 정본에서 **종료가 아닌** 것만 고른다. 이름 목록을
 * 여기에 적지 않는다. 그 집합은 Chip 으로 보이고, 「필터 초기화」는 그 기본값으로
 * 돌아가며 「전체 보기」는 상태 조건을 푼다. */
export const SELF_FILTER_FIELDS = ["q", "project_id", "status", "priority", "difficulty", "due", "category"];
const SELF_SPEC = ticketFilterSpec(SELF_FILTER_FIELDS, TICKET_LIST_EXTRA);
const MY_SPEC = { ...SELF_SPEC, all_status: false };

function useTicketColumnOptions(wantAssignee) {
  const metaQ = useTicketMeta(true);
  const assigneesQ = useAssigneeOptions(!!wantAssignee);
  const meta = metaQ.data || {};
  return {
    filterOptions: {
      status: statusOptions(meta.statuses),
      priority: (meta.priorities || []).map((p) => ({ value: p, label: priorityKo(p) })),
      difficulty: meta.difficulties || [],
    },
    entityOptions: wantAssignee ? {
      assignee_user_id: ((assigneesQ.data && assigneesQ.data.assignees) || []).map((c) => ({
        value: c.user_id, label: c.display_name,
      })),
    } : undefined,
  };
}

function appendDefaultStatuses(params, filters, openKeys) {
  if (filters.all_status) return params;
  if ((filters.status || []).length) return params;
  for (const key of openKeys) params.append("status", key);
  return params;
}

function resetListFilters(fields) {
  return { ...clearTicketFilters(fields), ...TICKET_LIST_EXTRA, all_status: false };
}

/* 내 티켓. 조건은 서버가 걸고(질의 파라미터), 그 조건은 주소에 남는다. */
export function MyTickets() {
  /* 상세를 열었다 돌아오면 조건·페이지·스크롤이 그대로다 (지시 19). */
  useListMemory("/my-tickets");
  const signalsOf = useTicketSignals();
  const statusEdit = useInlineStatusEdit();
  const confirm = useConfirm();
  const nav = useNavigate();
  const [filters, setFilters] = useQueryState(MY_SPEC);
  const workQ = useWorkStatuses(true);
  const openKeys = openStatusKeys(workQ.data && workQ.data.statuses);
  const qs = appendDefaultStatuses(
    ticketQueryParams(filters, SELF_FILTER_FIELDS),
    filters,
    openKeys,
  ).toString();
  const q = useTicketList("/api/tickets/mine", qs);
  /* 내 열린 티켓을 **다 끝낸 순간** 한 번 축하한다. 이 화면의 기본 조건이 「열린 상태」라
     (`appendDefaultStatuses`) 그 건수가 0 이 되는 것은 곧 「내 일이 없다」이다. 조건을
     바꿔서 0 이 된 경우와 구별하려고 질의 지문(`qs`)을 함께 넘긴다. */
  useCelebrateOnCleared(q.total, qs);
  const colOpts = useTicketColumnOptions(false);
  const [editing, setEditing] = React.useState(null);
  const toast = useToast();
  const qc = useQueryClient();
  const sel = useRowSelection();
  const bulk = useBulkTrash("/api/tickets/trash-bulk", qc, toast, () => { sel.clear(); q.refetch(); });
  // 보이는 티켓이 바뀌면(필터·페이지) 선택을 비운다 — 숨겨진 항목이 선택된 채 남지 않게.
  React.useEffect(() => { sel.clear(); }, [qs]); // eslint-disable-line react-hooks/exhaustive-deps
  const clearFilters = () => setFilters(resetListFilters(SELF_FILTER_FIELDS));
  /* 고른 티켓에 할 일은 목록 판 발의 선택 묶음이다(조합 계약 C-3). 예전에는 화면 머리 동작 자리에 나타났다 사라져, 긴
     목록을 내려가며 고르면 단추가 화면 밖에 있었다. */
  const selection = {
    count: sel.selected.size,
    onClear: sel.clear,
    actions: (
      <Button size="sm" variant="danger" disabled={bulk.isPending}
              /* 확인을 받는다 (E1). 예전에는 누르는 순간 선택 전부가 휴지통으로 갔다 —
                 같은 화면군의 `Trash.jsx` 는 확인을 받는데 여기만 규칙이 갈려 있었다.
                 **몇 건인지 숫자로** 말한다: "선택한 항목" 은 몇 개인지 안 알려 준다. */
              onClick={async () => {
                const n = sel.selected.size;
                if (!(await confirm(`티켓 ${n}건을 휴지통으로 보냅니다. 휴지통에서 복원할 수 있습니다.`,
                  { danger: true, title: "선택 삭제", confirmLabel: `${n}건 삭제` }))) return;
                bulk.mutate([...sel.selected]);
              }}>선택 삭제</Button>
    ),
  };
  return (
    <div className="c-screen">
      <PageHeader crumbRoot="내 업무" area="내 티켓" title="내 티켓" />
      {q.isLoading ? <Card><Skeleton /></Card>
        : q.isError ? <ErrorState layout="region" error={q.error} onRetry={() => q.refetch()} />
        : (() => {
          /* 목록 밖의 값(연결 상태 안내)은 첫 묶음 원본이 들고 온다 — 묶음마다 같다. */
          const data = q.first || {};
          const conn = ticketConnState(data, () => q.refetch());
          if (conn) return conn;
          const rows = q.rows;
          const cols = [selectionColumn(sel, rows.map((r) => r.id)),
            ...ticketColumns({ showAssignee: true, onEdit: setEditing, signalsOf, statusEdit, onOpen: openTicket(nav, "/my-tickets") })];
          return (
            <>
              {/* SEM-02(PA-F-031): 이 화면은 h1 하나뿐이라 필터·표가 스크린리더 제목
                  탐색에서 구획 없는 한 덩어리였다. 시각 디자인은 그대로 두고(.sr-only)
                  마크업에만 h2 두 개를 더한다. */}
              {/* 여기 미러 신선도 안내가 있었다. 「아직 한 번도 동기화 안 됨」과 「정말
                  0건」을 가르던 안내인데, 이 표가 정본이 된 뒤로 빈 목록은 언제나 정말
                  0건이다(S14). 서버도 `sync` 블록을 더 이상 안 싣는다. */}
              <Typography component="h2" className="sr-only">필터</Typography>
              <TicketFilterBar
                fields={SELF_FILTER_FIELDS} value={filters} onChange={setFilters} total={q.total}
                defaultStatusKeys={openKeys}
                allStatus={filters.all_status}
                onShowAll={() => setFilters({ all_status: true, status: [] })}
                onClear={clearFilters}
                resetLabel="필터 초기화"
              />
              {listActionNotice(bulk, null)}
              <Typography component="h2" className="sr-only">목록</Typography>
              <GroupedTickets
                placement="surface"
                rows={rows} columns={cols}
                sort={ticketSortOf(filters)}
                onSort={(key) => setFilters(nextTicketSort(filters, key))}
                filters={filters}
                onFilter={(field, next) => setFilters(applyColumnFilter(field, next))}
                filterOptions={colOpts.filterOptions}
                emptyState={
                  <TicketEmptyState
                    filtered={hasTicketFilter(filters, SELF_FILTER_FIELDS)}
                    onClear={clearFilters}
                    title="담당한 티켓이 없습니다."
                    help="나에게 배정된 티켓이 아직 없습니다. ‘미할당 티켓’에서 맡을 일을 고를 수 있습니다."
                  />
                }
                list={{
                  total: q.total, loaded: q.loaded,
                  hasNext: q.hasNext, isFetchingNext: q.isFetchingNext, onMore: q.fetchNext,
                  moreLabel: "티켓 더 보기",
                  /* 이 표는 가상화가 없다(D-354 · D-361) — 받은 행 전부가 DOM 에 남는다.
                     그래서 **자동 로딩에만** 상한을 둔다. 「더 보기」로는 계속 받을 수 있고,
                     끝 줄이 「N건 중 M건」을 계속 말한다 — 감추는 것은 없다. */
                  autoMaxRows: TICKET_AUTO_MAX_ROWS,
                }}
                selection={selection}
              />
            </>
          );
        })()}
      <TicketEditModal ticket={editing} open={!!editing} onClose={() => setEditing(null)} />
    </div>
  );
}

/* 미할당 티켓 — 담당자 없는 활성 티켓. '나에게 배정'(claim) 또는 편집으로 담당자를 지정한다. */
export function Unassigned() {
  /* 예전에는 이 화면만 `useConfirm()` 을 빠뜨려서 `confirm` 이 전역(window.confirm)으로
     떨어졌다 — 옆 화면은 앱 확인 대화상자를 쓰는데 여기만 브라우저 기본 상자가 떴고,
     danger·건수 라벨 같은 옵션은 조용히 무시됐다. */
  const confirm = useConfirm();
  const nav = useNavigate();
  useListMemory("/unassigned");
  const signalsOf = useTicketSignals();
  const [filters, setFilters] = useQueryState(SELF_SPEC);
  const qs = ticketQueryParams(filters, SELF_FILTER_FIELDS).toString();
  const q = useTicketList("/api/tickets/unassigned", qs);
  const colOpts = useTicketColumnOptions(false);
  const toast = useToast();
  const qc = useQueryClient();
  const [editing, setEditing] = React.useState(null);
  const claim = useClaim();
  const sel = useRowSelection();
  const bulk = useBulkTrash("/api/tickets/trash-bulk", qc, toast, () => { sel.clear(); q.refetch(); });
  React.useEffect(() => { sel.clear(); }, [qs]); // eslint-disable-line react-hooks/exhaustive-deps
  const clearFilters = () => setFilters(resetListFilters(SELF_FILTER_FIELDS));
  const selection = {
    count: sel.selected.size,
    onClear: sel.clear,
    actions: (
      <Button size="sm" variant="danger" disabled={bulk.isPending}
              /* 확인을 받는다 (E1). 예전에는 누르는 순간 선택 전부가 휴지통으로 갔다 —
                 같은 화면군의 `Trash.jsx` 는 확인을 받는데 여기만 규칙이 갈려 있었다.
                 **몇 건인지 숫자로** 말한다: "선택한 항목" 은 몇 개인지 안 알려 준다. */
              onClick={async () => {
                const n = sel.selected.size;
                if (!(await confirm(`티켓 ${n}건을 휴지통으로 보냅니다. 휴지통에서 복원할 수 있습니다.`,
                  { danger: true, title: "선택 삭제", confirmLabel: `${n}건 삭제` }))) return;
                bulk.mutate([...sel.selected]);
              }}>선택 삭제</Button>
    ),
  };
  return (
    <div className="c-screen">
      {/* 화면 설명은 페이지 머리의 한 줄이다(조합 계약 C-3). 예전에는 목록 판 안 표 위에 서서 머리 줄을 판 윗변에서 밀어냈다. */}
      <PageHeader
        crumbRoot="팀 업무" area="미할당 티켓" title="미할당 티켓"
        description="담당자 없는 활성 티켓입니다. ‘나에게 배정’ 또는 ‘수정’으로 지정하세요."
      />
      {q.isLoading ? <Card><Skeleton /></Card>
        : q.isError ? <ErrorState layout="region" error={q.error} onRetry={() => q.refetch()} />
        : (() => {
          /* 목록 밖의 값(연결 상태 안내)은 첫 묶음 원본이 들고 온다 — 묶음마다 같다. */
          const data = q.first || {};
          const conn = ticketConnState(data, () => q.refetch());
          if (conn) return conn;
          const rows = q.rows;
          const cols = [selectionColumn(sel, rows.map((r) => r.id)),
            ...ticketColumns({
              onEdit: setEditing, onClaim: (t) => claim.mutate(t.id),
              claimingId: claim.isPending ? claim.variables : null,
              signalsOf, onOpen: openTicket(nav, "/unassigned"),
            })];
          return (
            <>
              {/* 여기 미러 신선도 안내가 있었다. 위 목록과 같은 이유로 걷었다(S14). */}
              <TicketFilterBar fields={SELF_FILTER_FIELDS} value={filters} onChange={setFilters} total={q.total} onClear={clearFilters} />
              {listActionNotice(bulk, claim)}
              <GroupedTickets
                placement="surface"
                rows={rows} columns={cols}
                sort={ticketSortOf(filters)}
                onSort={(key) => setFilters(nextTicketSort(filters, key))}
                filters={filters}
                onFilter={(field, next) => setFilters(applyColumnFilter(field, next))}
                filterOptions={colOpts.filterOptions}
                emptyState={
                  <TicketEmptyState
                    filtered={hasTicketFilter(filters, SELF_FILTER_FIELDS)}
                    onClear={clearFilters}
                    title="미할당 티켓이 없습니다."
                    help="모든 활성 티켓에 담당자가 지정되어 있습니다."
                  />
                }
                list={{
                  total: q.total, loaded: q.loaded,
                  hasNext: q.hasNext, isFetchingNext: q.isFetchingNext, onMore: q.fetchNext,
                  moreLabel: "티켓 더 보기",
                  autoMaxRows: TICKET_AUTO_MAX_ROWS,
                }}
                selection={selection}
              />
            </>
          );
        })()}
      <TicketEditModal ticket={editing} open={!!editing} onClose={() => setEditing(null)} />
    </div>
  );
}

/* 목록에서 상태를 그 자리에서 바꾸는 배선 (지시 18).
 *
 * 범위 안의 티켓은 담당자가 아니어도 고칠 수 있으므로, 이 목록에 보이는 행은 서버의
 * 편집 판정(`app/tickets/service.py::ensure_can_edit`)을 지난다 — 눌러 보고 403 을 받는
 * 경로를 만들지 않는다는 규칙이 여기서 지켜지는 방식이다.
 *
 * 어휘는 서버가 준다(`/api/work/statuses`) — 화면이 상태 이름을 적으면 어휘가 바뀐 날
 * 이 드롭다운만 옛 목록으로 남는다.
 */
export function useInlineStatusEdit() {
  const qc = useQueryClient();
  const workQ = useWorkStatuses(true);
  // 편집 모달과 같은 규칙이다 — 목록에서 그 자리에서 완료로 바꾼 것도 끝낸 것이다.
  const doneKeys = React.useMemo(() => doneStatusKeys(workQ.data), [workQ.data]);
  const options = ((workQ.data && workQ.data.statuses) || []).map((st) => ({
    value: st.key,
    // 저장값과 표시값이 다른 것이 하나 있다(`진행` → `진행 중`). 서버가 준 라벨을 쓴다.
    label: st.label || st.key,
  }));
  return React.useMemo(() => ({
    options,
    save: async (ticket, next) => {
      const res = await api(`/api/tickets/${encodeURIComponent(ticket.id)}`, {
        method: "PATCH", body: { status: next },
      });
      /* 티켓 값을 그리는 질의는 한 표가 안다(`ticket-views.js`) — 홈·스프린트·보드가
         같은 티켓을 세고 있으므로 여기만 고치면 그쪽 숫자가 남는다. */
      invalidateTicketViews(qc);
      // 서버가 돌려준 값이 정본이다. 안 주면 넘긴 값을 쓴다(`InlineEdit` 의 §정직한 성공).
      const saved = (res && res.ticket && res.ticket.status) || next;
      // 원래 값과 같으면 옮긴 것이 아니다 — 같은 값을 다시 고른 저장에는 축하하지 않는다.
      if (saved !== ticket.status) celebrateIfCompleted(saved, doneKeys);
      return saved;
    },
  }), [JSON.stringify(options), qc, doneKeys]);   // eslint-disable-line react-hooks/exhaustive-deps
}


/* 새 티켓 — 채팅 없이 폼으로 생성(제목·프로젝트 필수). 담당자 기본값은 나(연결된 경우).
 * 복잡한 배경/요구사항이 필요한 티켓은 AI 도우미가 더 낫다 — 여기선 빠른 생성에 집중한다. */
/* 새 티켓 '작성 도움' 레일 — 기준 목업의 오른쪽 칸.
 *
 * 목업은 여기에 **AI가 분석한 결과**("제목과 설명에서 확인할 항목을 정리했습니다")를 그린다.
 * 우리는 그 분석을 하지 않는다. **없는 것을 있는 척 그리지 않는다** — 클로비 말투로
 * 고정 문구를 띄우면 사용자는 자기 티켓을 읽고 준 답이라고 믿는다. 그게 이 저장소가
 * 곳곳에서 잡아낸 '화면이 거짓말하는' 부류다.
 *
 * 대신 **실제로 일을 해 주는 것**으로 바꾼다: 누르면 설명 본문에 그 절이 실제로 들어간다.
 * 좋은 티켓이 무엇인지 알려 주면서 동시에 쓰는 수고를 던다. 이미 있는 절은 다시 넣지 않는다.
 * 진짜 AI 도움이 필요하면 그 자리에서 AI 도우미로 넘어갈 수 있게 links 를 남긴다. */
/* 네 가지가 핵심이고 둘은 보조다 (지시 10).
 *
 * 예전 셋(검증 범위 명시 · 예외 처리 · 완료 기준)은 **추상적이었다.** 「검증 범위를
 * 명시하라」는 말은 이미 무엇을 쓸지 아는 사람에게만 뜻이 통하고, 처음 티켓을 쓰는
 * 사람에게는 그 자리에 무슨 문장이 들어가야 하는지 알려 주지 않는다. 그리고 셋 다
 * **끝에 대한 이야기**여서 정작 「왜 이 일을 하는가」를 묻는 칸이 없었다.
 *
 * 그래서 각 항목이 **묻는 문장**과 **짧은 실제 예시**를 함께 든다. 예시는 설명 본문에
 * 안 들어간다 — 들어가면 남의 문장이 자기 티켓에 남는다. 들어가는 것은 절 제목뿐이다.
 */
const TICKET_SECTIONS = [
  {
    title: "배경과 문제",
    hint: "왜 필요한가요? 지금 무엇이 문제인가요?",
    example: "예: 서버를 등록할 때 같은 IP를 두 번 넣을 수 있어 운영에서 중복 장비가 생깁니다.",
    heading: "## 배경과 문제",
  },
  {
    title: "목표",
    hint: "무엇을 달성하려고 하나요?",
    example: "예: 같은 IP로는 등록이 안 되게 막고, 막힌 이유를 화면에서 알려 줍니다.",
    heading: "## 목표",
  },
  {
    title: "작업 범위",
    hint: "이번에 할 것과 하지 않을 것을 나눠 적습니다.",
    example: "예: 등록 화면과 저장 API를 고칩니다. 이미 들어간 중복 데이터 정리는 이번에 안 합니다.",
    heading: "## 작업 범위",
  },
  {
    title: "완료 기준",
    hint: "어떤 상태가 되면 끝난 건가요?",
    example: "예: 같은 IP를 저장하면 오류 문구가 뜨고, 목록에 새 줄이 안 생깁니다.",
    heading: "## 완료 기준",
  },
  {
    title: "예외 처리",
    hint: "정상 경로 말고, 실패하면 어떻게 되어야 하나요?",
    example: "예: 저장 도중 연결이 끊기면 아무것도 저장되지 않고 입력한 값이 화면에 남습니다.",
    heading: "## 예외 처리",
    optional: true,
  },
  {
    title: "확인 방법",
    hint: "받는 사람이 무엇을 눌러 보면 되나요?",
    example: "예: 서버 등록에서 10.0.0.1을 두 번 저장해 봅니다.",
    heading: "## 확인 방법",
    optional: true,
  },
];


/* 작성 도움 — 판 하나 안의 목록이다(핸드오프 계획 C · O-4).
 *
 * 예전에는 항목 하나가 통째로 단추였다(흰 판 위 12px 모서리 · surface2 면 · 넣은 뒤 반투명). 항목은 읽을 것
 * (절 이름 · 무엇을 적나 · 예시)이고 누를 것은 「넣기」 하나다 — 그래서 줄마다 오른쪽에 작은 단추(30)를 둔다.
 * 넣은 절은 단추가 꺼지고 「✓」가 선다(「넣었음」 같은 낱말을 새로 만들지 않는다). 단추의 접근 이름은 예전
 * 그대로다: 「설명에 '…' 절 넣기」 · 「…: 이미 넣었습니다」.
 *
 * REAUDIT C19 — 여섯이 넷(핵심)과 둘(「더 적으면 좋은 항목」, 「선택」 배지)로 갈린 구성은 그대로다. */
function WritingAidItem({ sec, already, onInsert }) {
  return (
    <Box
      component="li"
      data-writing-aid-item=""
      sx={{
        display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", columnGap: 1.25, alignItems: "start",
        py: 1.5, borderTop: 1, borderColor: "rule",
      }}
    >
      {/* 한 줄의 글자는 셋이 한 단씩 작아진다 — 절 이름(0.875rem/700) · 무엇을 적나(0.8125rem) · 예시(0.75rem 기울임). */}
      <Box sx={{ display: "grid", gap: 0.375, minWidth: 0 }}>
        <Stack direction="row" gap={0.75} alignItems="center">
          <Typography component="span" sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.bodySm, ...KO_WORD_BREAK }}>
            {sec.title}
          </Typography>
          {sec.optional ? <Badge value="선택" /> : null}
        </Stack>
        <Typography component="span" color="text.secondary" sx={{ fontSize: FONT_SIZE.caption, lineHeight: LINE_HEIGHT.caption, ...KO_WORD_BREAK }}>
          {sec.hint}
        </Typography>
        {/* 예시는 **넣어 주지 않는다.** 이 자리에서 보여 주기만 한다 — 눌러서 들어가는
            것은 절 제목뿐이고, 남의 문장이 자기 티켓에 남으면 안 된다. */}
        <Typography component="span" color="text.secondary" sx={{ fontSize: FONT_SIZE.micro, lineHeight: LINE_HEIGHT.caption, fontStyle: "italic", ...KO_WORD_BREAK }}>
          {sec.example}
        </Typography>
      </Box>
      <Button
        size="sm"
        onClick={() => onInsert(sec)}
        disabled={already}
        aria-label={already ? `${sec.title}: 이미 추가했습니다` : `설명에 '${sec.title}' 절 추가`}
      >
        {/* 하는 일을 이름으로 말한다(계획 §6) — 「넣기 · ✓」는 무엇을 어디에 넣는지 말하지 않았다. */}
        {already ? "추가함" : "설명에 추가"}
      </Button>
    </Box>
  );
}

function WritingAid({ doc, onInsert }) {
  const core = TICKET_SECTIONS.filter((sec) => !sec.optional);
  const optional = TICKET_SECTIONS.filter((sec) => sec.optional);
  const list = (items) => (
    <Box component="ul" sx={{ m: 0, p: 0, listStyle: "none" }}>
      {items.map((sec) => (
        <WritingAidItem key={sec.title} sec={sec} already={docHasHeading(doc, sec.title)} onInsert={onInsert} />
      ))}
    </Box>
  );
  return (
    /* 두 판은 화면 아래까지 선다(조합 계약 C-5). 2열에서는 격자의 `stretch` 가 레일을 폼 판 높이에 맞춰 준다.
       레일에는 바닥 높이를 따로 걸지 않는다 — 1열(레일이 폼 아래)에서 바닥을 걸면 내용보다 긴 빈 판이 선다(1200 실측). */
    <Card data-page-fill="grow" sx={{ display: "grid", gap: 1.75, alignContent: "start" }}>
      {/* 판 제목과 도움말 한 쌍(`SectionTitle help`) — 문장은 그대로다. */}
      <SectionTitle spacing="none"
        component="h2"
        title="작성 도움"
        help="배경, 목표, 작업 범위, 완료 기준을 정리해 주세요. 아래 「설명에 추가」를 누르면 그 절이 설명에 들어갑니다."

      />
      {list(core)}
      {/* 묶음 이름은 오른쪽으로 흐르는 실선과 한 줄이다 — 항목 줄의 위 선과 겹쳐 두 줄 선이 되지 않는다. */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Typography component="span" color="text.secondary" sx={{ fontSize: FONT_SIZE.micro, fontWeight: FONT_WEIGHT.semibold, whiteSpace: "nowrap" }}>
          더 적으면 좋은 항목
        </Typography>
        <Box aria-hidden="true" sx={{ flex: 1, borderTop: 1, borderColor: "divider" }} />
      </Box>
      {list(optional)}
      {/* 판 안 안내는 메시지 박스다(핸드오프 RULES §7) — 문장과 링크는 그대로이고 단추를 새로 만들지 않는다. */}
      <Callout compact>
        배경이 복잡한 티켓은 <Link href="#/chat" underline="hover">AI 도우미</Link>가 초안을 잡아 줍니다.
      </Callout>
    </Card>
  );
}


/* 칸마다 도움말 · 오류 줄의 id — 입력이 `aria-describedby` 로 가리키고, 검증에 걸린 칸을 찾을 때도 쓴다. */
const FIELD_HELP_IDS = { title: "nt-title-help", project_id: "nt-proj-help", est_wd: "nt-wd-help", due: "nt-due-help" };

/* '새 티켓' 바깥 2열(폼 + 작성 도움 레일) — 정본 내용 폭 짝 트랙이다(`density.js::contentPairTracks`, 조합 계약 C-5).
 *
 * 예전에는 이 화면이 뷰포트 `lg` 문턱의 사본(`NEW_TICKET_GRID`)을 들고 있었다. 1200 뷰포트에서 본문 칸은 59.5rem 인데
 * 2열로 서서 폼이 1칸 8줄로 좁고 레일 아래가 비었다. 이제 본문 칸 64rem 이상일 때만 2열이고, 아니면 레일이 폼 아래로 간다.
 *
 * `stretch` 다. `start` 로 두면 레일이 자기 내용만큼만 높아져 폼 카드와 바닥이 어긋난다 — 사용자가 지적한 Q5
 * ("카드 크기가 제각각")가 정확히 그것이다. 두 판은 화면 아래까지 서고(`PAGE_FILL_HEIGHT` 바닥), 폼이 더 길면 판이 자라며
 * 판 발이 화면 아래에 따라온다. */
const NEW_TICKET_PLATE = {
  minHeight: { md: PAGE_FILL_HEIGHT },
};

/* 이 티켓이 **어디로 공유되는가** (0060 §13).
 *
 * 작성자의 소속(Actor Context)과 프로젝트의 소속(Resource Context)은 다른 개념이고 다를 수
 * 있다. A-1 사람이 상위 A 부서 프로젝트에 티켓을 만들면 형제 팀 A-2 사람도 그 티켓을 본다 —
 * 만들고 나서 알게 되면 늦다. 과한 경고 대신 두 줄로 사실만 적는다.
 */
export function TicketShareScope({ project, me }) {
  if (!project) return null;
  const myPath = (me && me.department_path) || [];
  const orgName = (me && me.organization && me.organization.name) || "";
  const owner = project.dept_path && project.dept_path.length
    ? pathText(project.dept_path)
    : `${orgName || "조직"} 전체 공통`;
  return (
    <Box sx={{ mb: 2.5, display: "grid", gap: 0.5 }}>
      <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold }}>공유 범위</Typography>
      <Typography variant="body2" color="text.secondary">
        요청자 {myPath.length ? pathText(myPath) : (orgName || "-")}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        이 티켓은 <b>{owner}</b>의 일로 기록되고, 그 범위의 사람들에게 보입니다.
      </Typography>
    </Box>
  );
}


export function NewTicket() {
  const auth = useAuth();
  const myId = auth.data && auth.data.id;
  const qc = useQueryClient();
  const toast = useToast();
  /* 만든 뒤 이동은 라우터가 한다 — 예전에는 `window.location.hash` 에 직접 대입해
     react-router 의 `navigate` 를 우회했고, 그래서 `state.from`(목록으로 되돌아갈 자리)을
     실을 수가 없었다. */
  const nav = useNavigate();
  const projectsQ = useTicketProjects(true);
  /* **티켓을 만드는 자리가 기본값을 정한다** (지시 5).
   *
   * 일반 「새 티켓」은 아직 언제 할지 안 정한 일이라 백로그로 간다(회차를 안 붙인다).
   * 판의 회차 맥락 안에서 누른 「티켓 추가」는 주소에 `project` 와 `sprint` 를 싣고 오고,
   * 그러면 그 회차의 일이 된다 — 만든 사람이 곧바로 「스프린트에 담기」를 한 번 더 눌러야
   * 한다면 그 한 번을 빠뜨린 티켓은 회의에서 아무도 못 본다.
   *
   * 회차 id 는 서버가 다시 본다(`app/tickets/service.py::_place_in_sprint`) — 주소에
   * 남의 팀 회차 id 를 적어 넣어도 그 문을 못 지난다. */
  const context = React.useMemo(() => {
    const raw = String(window.location.hash || "");
    const q = raw.indexOf("?");
    const sp = new URLSearchParams(q >= 0 ? raw.slice(q + 1) : "");
    return {
      project: sp.get("project") || "",
      sprint: sp.get("sprint") || "",
      status: sp.get("status") || "",
      // 작업 보드의 팀 문맥(D-482). 회차에 담을 수 있는 것은 **그 팀의 프로젝트** 뿐이라
      // 프로젝트 후보를 여기서 먼저 좁힌다 — 서버가 다시 본다(`ensure_eligible`).
      team: sp.get("team") || "",
    };
  }, []);
  /* 설명의 정본은 **문서**다(`description_doc`). 문서 화면과 같은 편집기를 쓰므로 만들 때부터
     이 모양이고, 서버가 여기서 마크다운·평문을 파생시킨다 — 화면이 두 벌을 만들지 않는다. */
  const [form, setForm] = React.useState({ title: "", project_id: context.project, status: context.status, priority: "", difficulty: "", est_wd: "", due: "", assignees: [], description_doc: null });
  // 담당자 후보는 **선택한 프로젝트에 닿을 수 있는 사람**만이다 (0060 §14).
  const assigneesQ = useAssigneeOptions(!!form.project_id, form.project_id);
  const metaQ = useTicketMeta(true);
  /* 🔴 「한 번만」의 기준은 **컴포넌트 수명이 아니라 프로젝트**다.
   *
   * 프로젝트를 바꾸면 담당자를 비운다(아래 `EntityCombobox` 의 `onChange`) — 후보가 그
   * 프로젝트에 닿을 수 있는 사람으로 바뀌므로 옛 선택을 들고 갈 수 없다. 그런데 「나」를
   * 채우는 이 이펙트가 컴포넌트 수명당 한 번만 돌면, **두 번째로 고른 프로젝트에서는
   * 담당자가 빈 채로 남는다.** 그렇게 만든 티켓은 미할당이라 `/my-tickets`(내가 담당인
   * 티켓)에 안 뜨고, 사용자에게는 「만들었는데 안 보인다」로 읽힌다.
   *
   * 그래서 「그 프로젝트에 대해 한 번」으로 바꾼다. 사용자가 직접 체크를 다 지운 경우를
   * 덮어쓰지 않게, 지금 비어 있을 때만 채운다. */
  const meAppliedFor = React.useRef(null);
  React.useEffect(() => {
    if (!form.project_id || meAppliedFor.current === form.project_id) return;
    const cands = (assigneesQ.data && assigneesQ.data.assignees) || [];
    if (!cands.length) return;
    meAppliedFor.current = form.project_id;
    if (myId && cands.some((c) => c.user_id === myId)) {
      setForm((s) => ({ ...s, assignees: s.assignees.length ? s.assignees : [myId] }));
    }
  }, [assigneesQ.data, myId, form.project_id]);
  // 진행상태 기본값(계획)을 메타 로드 후 한 번 채운다.
  const statusApplied = React.useRef(false);
  React.useEffect(() => {
    if (statusApplied.current) return;
    const st = (metaQ.data && metaQ.data.statuses) || [];
    if (st.length) {
      statusApplied.current = true;
      setForm((s) => ({ ...s, status: s.status || (st.includes("계획") ? "계획" : st[0]) }));
    }
  }, [metaQ.data]);

  /* 같은 티켓은 끝나기 전에 한 번만 만든다(`useGuardedMutation`). 「티켓 추가」는 저장 중에 꺼지지만 그 끄기는
     다음 렌더의 일이고, `submit()` 에는 진행 중 가드가 없었다 — 제목 칸의 Enter 연타가 같은 티켓 둘이었다. */
  const create = useGuardedMutation({
    mutationFn: (body) => api("/api/tickets", { method: "POST", body }),
    // 회차 맥락에서 왔으면 그 판으로 돌아간다. 만든 티켓이 안 보이는 화면으로 튕기면
    // 사용자는 방금 만든 것이 어디 갔는지 확인할 방법이 없다.
    /* 🔴 **만든 것을 연다.** 문서 만들기가 이미 그렇게 한다(`Knowledge.jsx` — `navigate('/knowledge/' + doc.id)`).
     *
     * 예전에는 목록으로 튕기고 응답의 `ticket` 을 버렸다. 그런데 그 목록이 방금 만든 티켓을
     * 보여 준다는 보장이 없다 — 담당자를 안 붙였으면 「내 티켓」에 없고, 상태·기간 조건이
     * 걸려 있으면 거기에도 없다. 사용자에게는 「만들었는데 안 보인다」가 된다.
     * 「목록으로」 되돌아갈 자리는 상세 화면의 기존 규약(`Ticket.jsx::useListReturn`)이 준다. */
    onSuccess: (res) => {
      toast("티켓을 추가했습니다.", "success");
      invalidateTicketViews(qc);
      const made = res && res.ticket;
      const from = context.sprint || context.team ? "/work-board" : "/my-tickets";
      if (made && made.id) nav(`/tickets/${made.id}`, { state: { from } });
      else nav(from);
    },
    /* 실패는 토스트가 아니라 발 바로 위 메시지 박스다(핸드오프 RULES §1 · 계획 표 6) — 아래 `saveFailure` 가
       요청 상태에서 읽으므로 다시 누르면 걷히고, 성공하면 다시 서지 않는다. */
  });
  const saveFailure = failureText([create, "추가하지 못했습니다. 잠시 후 다시 시도해 주세요."]);
  /* 칸 검증 오류는 그 칸의 도움말 자리에 선다(토스트였다). 칸을 고치면 그 칸의 오류가 걷힌다. */
  const [errors, setErrors] = React.useState({});

  const meta = metaQ.data || {};
  const candidates = (assigneesQ.data && assigneesQ.data.assignees) || [];
  const allProjects = (projectsQ.data && projectsQ.data.projects) || [];
  /* 회차 문맥이면 **그 팀의 프로젝트만** 후보다(D-482). 다른 팀·조직 공통 프로젝트를 골라
     만들면 서버가 담기를 거절(422)하고 티켓은 만들어지지 않는다 — 고를 수 없게 두는 편이
     거절을 설명하는 것보다 낫다. 팀 문맥이 없으면 예전처럼 전부다. */
  const projects = context.team ? eligibleProjects(allProjects, context.team) : allProjects;
  const selectedProject = projects.find((p) => p.id === form.project_id) || null;
  const me = auth.data && (auth.data.user || auth.data);
  const set = (k, v) => {
    setForm((s) => ({ ...s, [k]: v }));
    setErrors((e) => (e[k] ? {} : e));
  };
  const notConfigured = (projectsQ.data && projectsQ.data.configured === false) || (metaQ.data && metaQ.data.configured === false);
  /* 후보를 **못 받은 것**과 후보가 **없는 것**은 다른 사실이다. 예전에는 조회가 실패해도
     `projects` 가 그냥 빈 배열이 되어 프로젝트 칸이 "선택할 수 있는 프로젝트가 없습니다"
     라고만 말했다 — 사용자는 자기 권한에 프로젝트가 없다고 읽고, 실제로는 서버를 못
     불렀는데 다시 시도할 자리도 없었다. 실패는 실패라고 말하고 다시 부를 길을 준다. */
  const loadFailed = projectsQ.isError || metaQ.isError;
  const retryLoad = () => { projectsQ.refetch(); metaQ.refetch(); };
  /* 첫 조회(프로젝트 · 메타)가 오는 동안은 폼 대신 들어올 폼의 모양을 그린다(R-20). 폼을 먼저 세우면 후보를 아직
     못 받은 프로젝트 칸이 「선택할 수 있는 프로젝트가 없습니다」라고 말하고 진행상태가 빈 채로 서서, 사용자는 불러오는
     중을 「없다」로 읽는다(느린 응답 실측: 로딩 표시 0). */
  const firstLoad = projectsQ.isLoading || metaQ.isLoading;

  /* 검증 실패는 **그 칸 아래**에 선다(핸드오프 RULES §1 · §7 · 계획 C) — 토스트였다. 검사 순서와 문구는 그대로이고,
     수정 모달(`TicketEditModal`)과 같이 처음 걸린 하나만 말한다. 이 폼은 본문 편집기까지 있어 화면보다 길고 단추는
     맨 아래라, 걸린 칸으로 포커스를 옮겨 그 칸과 오류 줄이 화면에 들어오게 한다(토스트는 어디서든 보였다).
     날짜 칸은 보이지 않는 입력 대신 첫 날짜 조각(`spinbutton`)이 포커스를 받는다. */
  function invalid(k, message) {
    setErrors({ [k]: message });
    const help = document.getElementById(FIELD_HELP_IDS[k]);
    const cell = help && help.parentElement;
    const target = cell && cell.querySelector('input:not([aria-hidden="true"]), [role="spinbutton"]');
    if (target && typeof target.focus === "function") target.focus();
  }

  function submit() {
    if (!form.title.trim()) { invalid("title", "제목을 입력하세요."); return; }
    // 프로젝트는 **언제나** 필수다 (0060 §11). 예전에는 후보 목록이 비면 그냥 통과시켰는데,
    // 그러면 소속이 없는 티켓이 만들어지고 그 티켓은 전체 관리자 말고는 아무에게도 안 보인다.
    if (!form.project_id) { invalid("project_id", "프로젝트를 선택하세요."); return; }
    /* 예상 WD 와 마감일은 필수다 (지시 10). 서버도 같은 요구를 하므로 여기서 막는 것은
       방어가 아니라 **먼저 말해 주는 것**이다 — 서버까지 다녀와서 422 를 보여 주면
       사용자는 무엇이 빠졌는지 폼에서 다시 찾아야 한다. */
    if (form.est_wd === "" || Number.isNaN(Number(form.est_wd))) { invalid("est_wd", "예상 WD를 숫자로 입력하세요."); return; }
    if (!form.due) { invalid("due", "마감일을 입력하세요."); return; }
    setErrors({});
    const body = {
      title: form.title.trim(),
      project_id: form.project_id,
      est_wd: Number(form.est_wd),
      due_date: form.due,
    };
    if (form.status) body.status = form.status;
    if (form.priority) body.priority = form.priority;
    if (form.difficulty) body.difficulty = form.difficulty;
    if (form.assignees.length) body.assignee_user_ids = form.assignees;
    if (!docIsEmpty(form.description_doc)) body.description_doc = form.description_doc;
    // 회차 맥락에서 왔으면 그 회차로 간다. 안 왔으면 이 칸을 아예 안 보낸다 — 그게 백로그다.
    if (context.sprint) body.sprint_id = context.sprint;
    create.mutate(body);
  }

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="내 업무" area="새 티켓" title="새 티켓" />
      {notConfigured ? (
        <Callout tone="warn">지금은 티켓을 추가할 수 없습니다. 잠시 뒤 다시 시도하고, 계속 같으면 관리자에게 문의하세요.</Callout>
      ) : loadFailed ? (
        /* `ErrorState` 는 상태 코드로 제목과 안내를 스스로 고른다(401·403·404·네트워크를
           갈라 쓴다) — 여기서 문구를 덧씌우지 않는다. */
        <ErrorState layout="region" error={projectsQ.error || metaQ.error} onRetry={retryLoad} />
      ) : (
        /* 폼 + 작성 도움 레일 2열(기준 목업과 같은 구조). 본문 칸이 좁으면 레일이 폼 아래로 내려간다 —
           레일을 옆에 억지로 붙여 두면 폼이 짜부라져 정작 쓸 수가 없다. */
        <Box sx={CONTENT_PAIR_CONTAINER}>
        <Box sx={contentPairTracks(BASELINE_TRACKS.two)}>
        {/* 폼 판은 세로 흐름이다 — 편집기 상자가 남는 높이를 채우고(`fill`), 발은 판 아래 끝이다. 발이 긴 폼에서 화면 아래에
            따라오도록(`ActionFooter sticky`) 판은 넘침을 자르지 않는다(MUI Card 뿌리의 `overflow: hidden` 을 푼다). */}
        <Card data-page-fill="grow" sx={{ ...NEW_TICKET_PLATE, display: "flex", flexDirection: "column", overflow: "visible" }}>
          {firstLoad ? <Skeleton kind="section" lines={8} /> : (
          /* 폼은 판 전체다 — 발(`ActionFooter card`)이 판 가장자리까지 면을 펴야 하므로 읽기 폭 상한(72rem)은 안쪽 칸들에만 건다. */
          /* `noValidate` — 검사는 `submit()` 이 칸 아래 제품 문장으로 하고 걸린 칸에 초점을 준다(위 `invalid`). 없으면 브라우저 기본
             말풍선(영문 「Please fill out this field.」)만 뜨고 그 검사에 닿지 못했다(r23 화면 대장 03-invalid). */
          <Box component="form" noValidate onSubmit={(e) => { e.preventDefault(); submit(); }} sx={{ display: "flex", flexDirection: "column", flex: "1 1 auto" }}>
          <Box sx={{ maxWidth: "72rem", display: "flex", flexDirection: "column", flex: "1 1 auto" }}>
            {/* 폼 안 안내는 메시지 박스다(핸드오프 RULES §7) — 문장과 링크는 그대로다. */}
            <Callout>
              필수 항목을 입력하고 티켓을 추가하세요.
            </Callout>
            {/* 칸은 12칸 격자에 선다(핸드오프 RULES §7 · 계획 표 8): 제목 12 / 프로젝트 6 · 진행상태 3 · 우선순위 3 /
                난이도 3 · 예상 WD 3 · 마감일 3 · 담당자 3. 열 수는 뷰포트가 아니라 **폼이 받은 칸의 폭**이 정한다
                (`density.js::FORM_FIELD_GRID_12` — 칸 셋이 들어가면 12칸, 둘이면 2칸, 더 좁으면 1칸). 칸마다 라벨 20 ·
                필드 36 · 도움말의 세 줄 트랙이라(`FormFieldCell`) 도움말이 긴 칸이 있어도 같은 줄의 입력칸 윗선이 같다.
                컨테이너는 격자만 감싼다: 레이아웃 격리(contain)가 본문 편집기까지 덮으면 확인하지 않은 부작용이 생긴다. */}
            <Box sx={{ ...FORM_FIELD_CONTAINER, mb: 2.5 }}>
              <Box sx={FORM_FIELD_GRID_12}>
                <FormFieldCell label="제목" htmlFor="nt-title" required helpId="nt-title-help" error={errors.title} sx={fieldSpan({ wide: 12, mid: 2 })}>
                  <TextField
                    id="nt-title" fullWidth size="small" required
                    value={form.title} onChange={(e) => set("title", e.target.value)}
                    error={!!errors.title}
                    inputProps={{ maxLength: 200, "aria-describedby": "nt-title-help" }}
                    placeholder="예: 서버 등록 IP 중복 방지"
                  />
                </FormFieldCell>
                {/* 프로젝트는 필수다 — 티켓의 조직 소속을 프로젝트가 정하기 때문이다(0060 §11).
                    '선택 안 함' 을 없앤다: 고를 수 있게 두면 소속 없는 티켓이 만들어지고,
                    그 티켓은 전체 관리자 말고는 아무에게도 안 보인다.
                    프로젝트는 **Entity** 다 — 후보가 업무가 쌓이는 만큼 자라고 이름이 길다.
                    검색 없는 드롭다운으로 두면 사용자는 이름을 알면서도 목록을 눈으로 훑어야
                    한다(지시 0-2.17 · R-5). */}
                <FormFieldCell
                  label="프로젝트" labelId="nt-proj-label" required helpId="nt-proj-help"
                  error={errors.project_id}
                  help={
                    !projects.length
                      ? (context.team ? "이 팀의 회차에 담을 수 있는 프로젝트가 없습니다." : "선택할 수 있는 프로젝트가 없습니다.")
                      : (context.team ? "이 팀의 회차에 담을 수 있는 프로젝트만 보입니다." : undefined)
                  }
                  sx={fieldSpan({ wide: 6, mid: 1 })}
                >
                  <EntityCombobox
                    id="nt-proj"
                    required
                    layout="form"
                    ariaLabelledBy="nt-proj-label"
                    ariaDescribedBy="nt-proj-help"
                    value={form.project_id}
                    onChange={(v) => { set("project_id", v); set("assignees", []); }}
                    loading={projectsQ.isLoading}
                    disabled={projectsQ.isLoading || !projects.length}
                    allLabel="프로젝트 선택"
                    noOptionsText={projects.length ? "일치하는 프로젝트가 없습니다." : "선택할 수 있는 프로젝트가 없습니다."}
                    options={projects
                      .filter((p) => p.can_create_ticket !== false)
                      .map((p) => ({ value: p.id, label: p.name || "(제목 없음)" }))}
                  />
                </FormFieldCell>
                <FormFieldCell label="진행상태" labelId="nt-status-label" sx={fieldSpan({ wide: 3, mid: 1 })}>
                  <TextField
                    id="nt-status" select fullWidth size="small"
                    SelectProps={{ labelId: "nt-status-label" }}
                    value={form.status} onChange={(e) => set("status", e.target.value)}
                  >
                    {/* 값은 저장 키, 이름은 사람 말이다 — 예전엔 키를 그대로 그려 「진행 중」이
                        「진행」으로 떴다(`ticket-options.js::statusOptions`). */}
                    {statusOptions(withCurrent(meta.statuses, form.status)).map((o) => (
                      <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
                    ))}
                  </TextField>
                </FormFieldCell>
                <FormFieldCell label="우선순위" labelId="nt-prio-label" sx={fieldSpan({ wide: 3, mid: 1 })}>
                  <TextField
                    id="nt-prio" select fullWidth size="small"
                    SelectProps={{ displayEmpty: true, labelId: "nt-prio-label" }}
                    value={form.priority} onChange={(e) => set("priority", e.target.value)}
                  >
                    <MenuItem value="">없음</MenuItem>
                    {withCurrent(meta.priorities, form.priority).map((p) => <MenuItem key={p} value={p}>{priorityKo(p)}</MenuItem>)}
                  </TextField>
                </FormFieldCell>
                <FormFieldCell label="난이도" labelId="nt-diff-label" sx={fieldSpan({ wide: 3, mid: 1 })}>
                  <TextField
                    id="nt-diff" select fullWidth size="small"
                    SelectProps={{ displayEmpty: true, labelId: "nt-diff-label" }}
                    value={form.difficulty} onChange={(e) => set("difficulty", e.target.value)}
                  >
                    <MenuItem value="">없음</MenuItem>
                    {withCurrent(meta.difficulties, form.difficulty).map((d) => <MenuItem key={d} value={d}>{d}</MenuItem>)}
                  </TextField>
                </FormFieldCell>
                {/* 예상 WD 와 마감일은 **필수**다 (지시 10). 이 제품의 계획이 그 둘 위에
                    선다 — 예상 WD 가 없으면 스프린트의 남은 일과 담당자별 부하를 못 세고,
                    마감일이 없으면 「지연」이라는 신호 자체가 계산되지 않는다(D-349).
                    별표만 붙이고 끝내지 않는다: 서버도 같은 요구를 한다(`TicketCreate`). */}
                <FormFieldCell
                  label="예상 WD" htmlFor="nt-wd" required helpId="nt-wd-help"
                  help="사람 한 명이 며칠 동안 할 일인지 입력합니다. 0도 입력할 수 있습니다." error={errors.est_wd}
                  sx={fieldSpan({ wide: 3, mid: 1 })}
                >
                  <TextField
                    id="nt-wd" fullWidth size="small" required type="number"
                    inputProps={{ step: "0.5", min: "0", "aria-describedby": "nt-wd-help" }}
                    error={!!errors.est_wd}
                    value={form.est_wd} onChange={(e) => set("est_wd", e.target.value)}
                  />
                </FormFieldCell>
                <FormFieldCell label="마감일" htmlFor="nt-due" labelId="nt-due-label" required helpId="nt-due-help" error={errors.due} sx={fieldSpan({ wide: 3, mid: 1 })}>
                  {/* 날짜 칸은 보이지 않는 입력(`#nt-due`)과 날짜 조각 묶음(`role="group"`)으로 선다. 칸 위 라벨의 `for` 는
                      보이지 않는 입력에만 닿으므로, 낭독기가 실제로 들어가는 묶음에도 이름과 도움말 줄을 따로 잇는다
                      (MUI 라벨을 쓸 때는 MUI 가 묶음에 라벨을 이었다). */}
                  <DateField
                    id="nt-due" required error={!!errors.due}
                    value={form.due} onChange={(v) => set("due", v)}
                    slotProps={{ input: { "aria-labelledby": "nt-due-label", "aria-describedby": "nt-due-help" } }}
                  />
                </FormFieldCell>
                {/* 담당자 후보는 **선택한 프로젝트에 닿을 수 있는 사람**만이다(0060 §14) — 프로젝트를 고르기 전에는
                    후보를 묻지 않는다. 그동안 칸은 꺼진 고르개로 서고, 이유는 칸 안의 회색 글자가 아니라 칸 밖 도움말이
                    말한다(핸드오프 RULES §7 — 칸 안 글자는 값처럼 읽힌다). 후보를 부르는 동안은 고르개가 불러오는 중을
                    말하고, 후보가 없다는 사실도 같은 도움말 자리가 말한다(예전 문장 그대로). */}
                <FormFieldCell
                  label="담당자" labelId="nt-assignee-label" helpId="nt-assignee-help"
                  help={!form.project_id
                    ? "프로젝트를 먼저 고르세요. 그 프로젝트에 접근할 수 있는 사람만 담당자가 될 수 있습니다."
                    : (!assigneesQ.isLoading && !candidates.length
                      ? "배정할 수 있는 사람이 없습니다. 이 프로젝트에 접근할 수 있는 계정만 후보로 나옵니다."
                      : undefined)}
                  sx={fieldSpan({ wide: 3, mid: 2 })}
                >
                  {/* 후보를 부르는 동안은 들어올 고르개 한 줄의 모양을 그린다(R-20 — 예전 담당자 칸과 같다). */}
                  {form.project_id && assigneesQ.isLoading ? <Skeleton lines={1} /> : (
                    <UserPicker
                      multiple
                      layout="form"
                      ariaLabelledBy="nt-assignee-label"
                      ariaDescribedBy="nt-assignee-help"
                      placeholder="예: 김하나"
                      candidates={candidates}
                      value={form.assignees}
                      onChange={(ids) => set("assignees", ids)}
                      myId={myId}
                      disabled={!form.project_id || !candidates.length}
                    />
                  )}
                </FormFieldCell>
              </Box>
            </Box>
            {/* 이 티켓이 **어디로 공유되는가** (0060 §13).
                작성자의 소속과 프로젝트의 소속은 다를 수 있다 — A-1 사람이 상위 A 프로젝트에
                티켓을 만들면 A-2 사람도 그 티켓을 본다. 만든 뒤에 알게 되면 늦다. */}
            <TicketShareScope project={selectedProject} me={me} />
            {/* 폭: 설명 블록은 컨테이너 실측 폭을 따른다(editorContainerSx/editorSurfaceWidthSx, BodyEditor.jsx) —
                폼의 72rem 상한 안에서 부모 폭을 그대로 따라가고, 아주 넓어졌을 때만(80rem) 한 번 더 멈춘다. */}
            <Box sx={{ mb: 2.5, display: "flex", flexDirection: "column", flex: "1 1 auto", ...editorContainerSx("nt-desc-surface") }}>
              {/* 폭 규칙을 시험이 짚는 자리 — 표시가 아니라 **이름**으로 짚게 한다. */}
              <Box data-nt-desc="surface" sx={{ ...editorSurfaceWidthSx("nt-desc-surface"), display: "flex", flexDirection: "column", flex: "1 1 auto" }}>
                {/* 칸 이름은 칸 위 라벨이다(`FieldLabel`). `contenteditable` 은 `<label htmlFor>` 의 대상이 될 수 없어
                    편집기가 자기 이름을 든다(`ariaLabel="설명"`) — 화면에 보이는 이 말과 같은 말이다. */}
                <FieldLabel>설명</FieldLabel>
                {/* 🔴 **문서와 같은 편집기다.** 예전에는 이 자리만 글자 칩 열한 개짜리 마크다운 편집기였고, 그래서
                    굵게 · 기울임 · 표 · 이미지를 쓸 수 없었다. 이제 티켓 본문도 문서와 같은 정본을 쓴다.
                    편집기 상자가 폼 판의 남는 높이를 채운다(`fill`) — 짧은 폼에서 판 아래가 비지 않는다. */}
                <React.Suspense fallback={<Skeleton kind="section" lines={6} />}>
                  <BlockEditor
                    value={form.description_doc}
                    onChange={(v) => set("description_doc", v)}
                    label="설명"
                    ariaLabel="설명"
                    fill
                  />
                </React.Suspense>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                  선택 항목입니다. 문서와 같은 도구로 서식, 목록, 표, 링크, 이모지를 넣을 수 있습니다.
                </Typography>
              </Box>
            </Box>
            {saveFailure ? <Callout tone="danger" compact>{saveFailure}</Callout> : null}
          </Box>
          {/* 저장은 판 발이다(`ActionFooter card` — 함몰면 + 위 실선, 오른쪽 확정). 취소는 이 화면에 없다(계획 P-24).
              이 폼은 본문 편집기까지 있어 화면보다 길 수 있다 — 발이 화면 아래에 따라와 「티켓 추가」가 늘 보인다(`sticky`).
              예전에는 우하단 마스코트 FAB 자리를 비우느라 단추가 판 여백보다 80px 안쪽에 섰는데, 그 FAB 은 PA-RC-0020 에서
              걷혔다 — 단추 오른쪽 끝은 판 여백(20)이다. */}
          <ActionFooter placement="card" sticky>
            <Button variant="primary" type="submit" loading={create.isPending}>티켓 추가</Button>
          </ActionFooter>
          </Box>
          )}
        </Card>
        <WritingAid
          doc={form.description_doc}
          onInsert={(sec) => set("description_doc", appendSection(form.description_doc, sec.title))}
        />
        </Box>
        </Box>
      )}
    </div>
  );
}
