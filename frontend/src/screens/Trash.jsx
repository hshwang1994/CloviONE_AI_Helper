import React, { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";
import { api } from "../lib/api.js";
import {
  Badge, Button, Callout, DataTable, EmptyState, ErrorState, ListEmptyState,
  Modal, PageHeader, RowActions, Skeleton, TitleCell, useConfirm, useToast,
  Segmented,
} from "../ui/kit.jsx";
import { DocBody } from "../ui/DocBody.jsx";
import { toggleSort } from "../ui/TableHeaderCell.jsx";
import { bulkFailureNote, objectParticle, toUTCDate } from "../lib/format.js";
import { failureText, latestMutation } from "../lib/failure.js";
import { useQueryState } from "../lib/useQueryState.js";
import { useRowSelection, selectionColumn } from "../ui/bulkSelect.jsx";
import { invalidateTicketViews } from "./ticket-views.js";
import { invalidateDocumentViews } from "./document-views.js";
import { DateCell } from "../ui/cells.jsx";

/* 휴지통 — 삭제한 티켓/문서를 보관기간 동안 잡아둔다. 복원하면 원래 목록으로 돌아가고, 보관기간이
 * 지나면 백그라운드가 원본을 보관처리하고 여기서 사라진다. 지금 바로 영구 삭제도 가능(권한 필요).
 * 문서 하위 페이지. 종류(티켓/문서)·제목·삭제한 사람·삭제일·삭제 예정일이 보인다.
 *
 * 2026-08 MUI 재설계: 화면 고유 CSS 클래스(.k-row-actions 등)에 기대지 않고 sx로 직접 그린다 —
 * 그 클래스들은 kit.css가 걷히면서 이미 규칙이 사라져 버튼이 서로 붙어 있었다. 열 너비도
 * screens.css의 nth-child가 아니라 열 정의(width)에 함께 적는다(열을 옮기면 폭도 따라간다).
 *
 * 2026-09 개편: 사용자가 「탭도 이상하고 뒤로가기도 안 되고 본문도 안 보이고 그리드도 이상하고
 * 정렬 안 돼 있고」라고 지적했다. 다섯이 전부 실제 결함이었고 각각 다른 뿌리를 갖고 있었다 —
 * 아래 각 자리의 🔴 주석이 그 뿌리를 적는다. */

function typeKind(t) { return t === "ticket" ? "info" : "purple"; }

const DAY_MS = 24 * 60 * 60 * 1000;
// UA-10 확증 — 예전엔 상한도 total도 없어 "더 보기" 자체가 불가능했다. useChat.js의 대화
// 목록(AI-18)과 같은 값·같은 관용(더 보기는 상한을 늘려 처음부터 다시 받는다 — 그 사이 항목이
// 복원/영구삭제돼도 오프셋 이어붙이기처럼 중복·누락이 안 생긴다).
const TRASH_PAGE_SIZE = 100;
/* 🔴 서버가 받아 주는 상한(`app/trash/repository.py::MAX_TRASH_LIST_LIMIT`)과 **같은 값**이다.
 * 넘겨 보내면 FastAPI 가 422 를 내고, 이 화면은 그것을 오류 화면으로 그려 목록이 통째로
 * 사라진다. 그리고 이제 이 값이 주소에 실리므로(`TRASH_SPEC`) 새로고침해도 안 낫는다 —
 * 「더 보기」도, 주소로 들어온 값도 여기서 자른다. */
const TRASH_MAX_LIMIT = 1000;

/* 🔴 화면 상태는 **주소**에 둔다. 예전에는 `useSearchParams` 를 직접 불러 조건 하나만
 * `setParams({ kind })` 로 갈아치웠고, 그것이 세 가지를 한꺼번에 깨뜨렸다:
 *
 *   ① **뒤로가기.** 두 번째 인자를 안 줘서 react-router 가 **push** 했다. 탭을 세 번 누르면
 *      화면을 벗어나는 데 뒤로가기가 네 번 필요했다. 사용자가 「뒤로가기도 안 되고」라고
 *      한 것이 이것이다.
 *   ② **다른 파라미터.** 쿼리를 통째로 갈아치워서 알림 딥링크 같은 다른 규약의 값이 사라졌다.
 *   ③ **페이지 깊이.** 「더 보기」로 늘린 상한이 `useState` 에만 살아 뒤로가기·새로고침에
 *      안 돌아왔고, 조건을 바꿔도 안 되돌아갔다.
 *
 * `useQueryState` 가 셋을 다 해결한다 — 기본이 `replace`, 모르는 키를 보존, `reset` 이
 * 「조건을 바꾸면 페이지 깊이를 되돌린다」를 해 준다. 스펙은 **모듈 상수**여야 메모가 산다. */
const TRASH_SPEC = { kind: "", sort: "deleted_at", dir: "desc", limit: TRASH_PAGE_SIZE };
const TRASH_QUERY_OPTS = { reset: ["limit"] };

/* 종류 축. 값이 주소에 그대로 실리므로 서버가 아는 낱말과 같아야 한다. */
const KINDS = [
  { value: "", label: "전체", countKey: "all" },
  { value: "ticket", label: "티켓", countKey: "ticket" },
  { value: "document", label: "문서", countKey: "document" },
];

/* 서버가 아는 정렬 축(`app/trash/router.py::TRASH_SORTS`)과 같은 낱말. 여기 없는 값이
   주소로 들어오면 서버가 기본으로 떨어뜨리므로, 화면도 같은 판단을 해서 화살표가
   거짓말하지 않게 한다. */
const SORT_KEYS = ["deleted_at", "purge_after", "title"];
/* 열마다 **처음 누를 때의 방향**. 날짜는 최신부터, 글자는 가나다순이 사람의 기대다. */
const SORT_DEFAULT_DIR = { deleted_at: "desc", purge_after: "asc", title: "asc" };

/* 24시간 안에 영구 삭제될 항목 수 — '보관기간이 지나면 사라진다'는 설명만으로는 언제가 그 순간인지
 * 알 수 없어서, 지금 손을 써야 하는 건수를 숫자로 앞에 내놓는다.
 *
 * 🔴 화면은 이제 이 함수를 **안 쓴다** — 서버가 조건·상한과 무관하게 센 값을 준다
 * (`counts.urgent`). 예전에는 받아 온 목록만 세서, 종류를 좁히거나 항목이 상한을 넘으면
 * 급한 건수가 조용히 줄었다. 함수는 그 계산의 정의를 시험이 붙잡고 있어 남긴다. */
export function urgentCount(items, nowMs) {
  const now = nowMs == null ? Date.now() : nowMs;
  return (items || []).filter((r) => {
    const d = toUTCDate(r && r.purge_after);
    return d != null && d.getTime() - now <= DAY_MS;
  }).length;
}

/** 한 줄로 자르고 끝에 「…」를 붙인다. 제목과 발췌가 같은 선언을 쓴다. */
const ONE_LINE = { display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };

/** 휴지통 줄이 **우리 문서**를 가리키면 그 id. 아니면 `null`.
 *
 * 서버가 `doc:<uuid>` 로 접두를 붙인다(`app/trash/router.py::DOC_PREFIX`). 옛 미러
 * 항목은 `source: "legacy"` 라 우리 쪽에 열 문서가 없다 — 접두만 보고 이으면 없는 화면으로
 * 보낸다. */
const DOC_PREFIX = "doc:";

function docIdOf(row) {
  if (!row || row.item_type !== "document" || row.source !== "knowledge") return null;
  const id = String(row.id || "");
  return id.startsWith(DOC_PREFIX) ? id.slice(DOC_PREFIX.length) : null;
}

/* 🔴 **옛 미러 줄(티켓·옛 문서)의 본문을 지우기 전에 본다.**
 *
 * 그쪽은 평소 경로가 전부 막혀 있다 — `ticket_detail` 과 `GET /api/team-docs/{id}` 가
 * 첫 줄에서 「휴지통에 있으면 없는 것으로 본다」를 지난다(H2). 그 가드는 **편집을 막으려고**
 * 있는데, 보기까지 막은 결과가 「무엇인지 모른 채 영구 삭제」였다. 서버에 읽기 전용 경로를
 * 따로 열고(`GET /api/trash/{id}/preview`) 이 창이 그것을 그린다.
 *
 * Native 문서는 여기 안 온다 — 그쪽은 제목이 문서 화면으로 가는 링크다(그 링크는 고른 줄을
 * 잃지 않으려고 새 탭으로 연다, 아래 열 정의 참고). */
function PreviewDialog({ row, onClose }) {
  const q = useQuery({
    queryKey: ["trash-preview", row && row.id],
    queryFn: () => api("/api/trash/" + row.id + "/preview"),
    enabled: !!row,
    staleTime: 60000,
  });
  return (
    <Modal open={!!row} onClose={onClose} size="md" title={(row && row.title) || "제목 없음"}>
      {q.isPending ? <Skeleton kind="page" lines={4} />
        : q.isError ? <ErrorState layout="region" error={q.error} onRetry={() => q.refetch()} />
        : <DocBody blocks={q.data && q.data.blocks} blocksError={q.data && q.data.blocks_error} />}
    </Modal>
  );
}

export function Trash() {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [state, setState] = useQueryState(TRASH_SPEC, TRASH_QUERY_OPTS);
  /* 주소의 값을 **읽을 때 정규화한다.** 이상한 값이 오면 화면이 「필터가 걸렸다」고 말하면서
     실제로는 전체를 보여 준다(서버가 모르는 값을 무시하므로). 두 층이 다른 말을 하게 둔다. */
  const kind = KINDS.some((k) => k.value === state.kind) ? state.kind : "";
  const sortKey = SORT_KEYS.indexOf(state.sort) >= 0 ? state.sort : TRASH_SPEC.sort;
  const dir = state.dir === "asc" ? "asc" : "desc";
  const limit = Math.min(state.limit > 0 ? state.limit : TRASH_PAGE_SIZE, TRASH_MAX_LIMIT);
  const sort = { key: sortKey, dir };

  const q = useQuery({
    queryKey: ["trash", limit, kind, sortKey, dir],
    queryFn: () => api(
      `/api/trash?limit=${limit}&sort=${sortKey}&dir=${dir}${kind ? `&kind=${kind}` : ""}`,
    ),
    refetchInterval: 15000,
    // AI-18과 같은 이유 — "더 보기"가 상한을 늘려 새 쿼리 키로 다시 받는 동안 이전 목록을
    // 그대로 보여준다(없으면 15초 폴링과 무관하게 매번 스켈레톤이 깜빡인다).
    placeholderData: keepPreviousData,
  });
  const sel = useRowSelection();
  const [preview, setPreview] = useState(null);

  /* 🔴 **조건이 바뀌면 고른 것을 비운다.**
   *
   * 예전에는 안 비웠다. 티켓 탭에서 다섯을 고르고 문서 탭으로 넘어가면 머리줄에 「5개 선택」이
   * 그대로 남고, 화면에는 그 다섯이 하나도 없는데 「선택 영구 삭제」가 **댓글·첨부까지 함께**
   * 지웠다. 확인 창은 개수만 말해서 사용자가 알아챌 방법이 없었다.
   * 형제 화면이 이미 이렇게 한다(`MyTickets.jsx` — 쿼리스트링이 바뀌면 선택을 비운다). */
  useEffect(() => { sel.clear(); }, [kind, sortKey, dir]); // eslint-disable-line react-hooks/exhaustive-deps

  const bulkMsg = (res, verb) => {
    const changed = (res.restored || res.purged) || [];
    const n = changed.length;
    const failed = res.failed || [];
    // UA-25 — 실패 사유를 "권한이 없어"로 뭉개지 않는다. 실제로는 이미 처리됨·권한·Notion
    // 보관 실패 3종이 섞일 수 있고, Notion 장애일 때 이 문구 때문에 관리자가 다른 계정으로
    // 헛되이 재시도했다.
    /* 전부 되살렸으면 토스트다. 일부 건너뜀 · 영구 삭제는 목록 위 메시지 박스가 말한다(`trashNotice`) —
       안 된 이유와 되돌릴 수 없는 결과는 사라지면 안 된다. */
    if (!failed.length && verb === "복원") toast(`${n}건을 ${verb}했습니다.`, "success");
    qc.invalidateQueries({ queryKey: ["trash"], refetchType: "all" });
    // 복원한 티켓은 홈·스프린트에도 다시 나타나야 한다 — 그 키 목록은 ticket-views.js 가 안다.
    invalidateTicketViews(qc, { refetchType: "all" });
    // 문서 쪽도 마찬가지 — document-views.js의 ["team-doc"] 접두어(id 없이)가 상세 캐시
    // 전부를 한 번에 잡는다(예전엔 FN-14 수정 때 notion_page_id별로 손으로 순회했다).
    invalidateDocumentViews(qc, { refetchType: "all" });
    sel.clear();
  };
  const bulkRestore = useMutation({
    mutationFn: (ids) => api("/api/trash/restore-bulk", { method: "POST", body: { ids } }),
    onSuccess: (res) => bulkMsg(res, "복원"),
  });
  const bulkPurge = useMutation({
    mutationFn: (ids) => api("/api/trash/purge-bulk", { method: "POST", body: { ids } }),
    onSuccess: (res) => bulkMsg(res, "영구 삭제"),
  });

  // FN-14 — id가 아니라 행 전체(row)를 넘긴다(mutationFn이 row.id를 쓴다). onSuccess는 더는
  // row 데이터가 필요 없다 — document-views.js의 ["team-doc"] 접두어(id 없이)가 상세 캐시
  // 전부를 한 번에 잡는다(예전엔 notion_page_id별로 손으로 순회했다).
  const restore = useMutation({
    mutationFn: (row) => api("/api/trash/" + row.id + "/restore", { method: "POST" }),
    onSuccess: () => {
      toast("복원했습니다. 원래 목록에서 다시 볼 수 있습니다.", "success");
      qc.invalidateQueries({ queryKey: ["trash"], refetchType: "all" });
      invalidateTicketViews(qc, { refetchType: "all" });
      invalidateDocumentViews(qc, { refetchType: "all" });
    },
  });
  const purge = useMutation({
    mutationFn: (row) => api("/api/trash/" + row.id + "/purge", { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trash"], refetchType: "all" });
      // restore와 대칭을 맞춘다 — 예전엔 purge만 이 둘이 빠져 있어 티켓/문서 목록이 영구
      // 삭제 뒤에도 최대 staleTime 동안 그 항목을 계속 보여줄 수 있었다(FN-14와 같은 자리에서
      // 함께 고친다).
      invalidateTicketViews(qc, { refetchType: "all" });
      invalidateDocumentViews(qc, { refetchType: "all" });
    },
  });
  /* 목록 동작의 결과 중 **남아야 하는 것** — 실패(오류), 일부 건너뜀과 영구 삭제의 사실(주의).
     가장 나중에 누른 동작 하나만 말하고 다음 동작에서 걷힌다(`lib/failure.js`). 휴지통이 비어도
     서도록 목록 판이 아니라 머리 바로 아래에 둔다. 문구는 토스트 때와 같다. */
  const trashNotice = (() => {
    const failure = failureText(
      [bulkRestore, "복원하지 못했습니다. 다시 시도해 주세요."],
      [bulkPurge, "삭제하지 못했습니다. 다시 시도해 주세요."],
      [restore, "복원하지 못했습니다. 다시 시도해 주세요."],
      [purge, "삭제하지 못했습니다. 다시 시도해 주세요."],
    );
    if (failure) return { tone: "danger", text: failure };
    const last = latestMutation(bulkRestore, bulkPurge, restore, purge);
    if (!last || !last.isSuccess) return null;
    if (last === purge) return { tone: "warn", text: "영구 삭제했습니다. 원본은 보관 처리됐습니다." };
    if (last === bulkRestore || last === bulkPurge) {
      const res = last.data || {};
      const failed = res.failed || [];
      const verb = last === bulkPurge ? "영구 삭제" : "복원";
      if (!failed.length && last === bulkRestore) return null;
      return { tone: "warn", text: `${((res.restored || res.purged) || []).length}건을 ${verb}했습니다.` + bulkFailureNote(failed) };
    }
    return null;
  })();

  const days = (q.data && q.data.retention_days) || 7;
  // 문서 정책은 티켓과 따로다(D-352) — 그쪽의 다음 단계는 「행을 지우는 것」이라 되돌릴 수
  // 없고, 그래서 끌 수 있다. 화면은 둘을 구별해서 말한다.
  const docAuto = !q.data || q.data.document_autopurge !== false;
  const docDays = (q.data && q.data.document_retention_days) || days;
  const items = (q.data && q.data.items) || [];
  // UA-10 확증 — total이 지금 받은 개수보다 크면 상한(TRASH_PAGE_SIZE) 너머에 더 있다는 뜻.
  const total = (q.data && q.data.total) || 0;
  /* 🔴 개수는 **서버가 조건·상한과 무관하게 센 값**이다. 예전에는 화면이 받아 온 목록에서
     셌고, 그래서 문서 화면의 「휴지통」이 `?kind=document` 로 열면 첫 화면부터 「티켓 0」이
     떴다 — 티켓이 수십 건 들어 있어도 그랬다. */
  const counts = (q.data && q.data.counts) || null;
  // 상한에 닿으면 「더 보기」를 안 그린다 — 눌러도 같은 목록이 다시 올 뿐이다.
  const hasMore = items.length < total && limit < TRASH_MAX_LIMIT;
  const loadMore = () => setState({ limit: Math.min(limit + TRASH_PAGE_SIZE, TRASH_MAX_LIMIT) });
  /* 「다음 묶음을 받는 중」과 「15초 폴링 중」은 다른 사실이다. 예전에는 `q.isFetching` 을
     그대로 넘겨서 「휴지통 더 보기」가 15초마다 저절로 회색이 됐고, `ListFooter` 의
     무성장 감지기(`stalled`)도 그 폴링을 「다음 쪽을 요청했는데 안 늘었다」로 읽었다.
     이 파생값이 참이 되는 경우는 하나다 — 방금 상한을 늘렸고 그 응답이 아직 안 온 때.
     단추가 보이는 상황(`hasMore`)에서는 언제나 `items.length === limit` 이므로
     (서버가 합친 뒤 상한으로 자른다) 평상시 폴링은 이 값을 못 켠다. */
  const fetchingNext = q.isFetching && items.length < limit;

  const visibleIds = new Set(items.map((i) => i.id));
  const manageable = new Set(items.filter((i) => i.can_manage).map((i) => i.id));
  /* 🔴 일괄 동작은 **지금 화면에 있는 줄**로 좁힌다. 위 effect 가 조건이 바뀔 때 선택을
     비우지만, 폴링으로 목록이 바뀌거나 「더 보기」 앞뒤로 줄이 사라지는 경우도 있다.
     되돌릴 수 없는 동작이라 두 겹으로 막는다. */
  const chosen = [...sel.selected].filter((id) => visibleIds.has(id));
  const chosenRows = items.filter((r) => sel.selected.has(r.id));
  const selCol = selectionColumn(sel, items.map((i) => i.id), { eligible: (id) => manageable.has(id) });

  /* 지울 것의 **이름**을 확인 창에 적는다. 예전에는 건수만 말해서, 화면에 없는 줄이 섞여
     있어도 알아챌 수 없었다. `useConfirm` 이 `whiteSpace: "pre-line"` 로 그리므로 줄바꿈이
     그대로 산다. 너무 길면 앞 다섯 줄만 적고 나머지는 수로 말한다. */
  const nameList = (rows) => {
    const shown = rows.slice(0, 5).map((r) => `- ${r.title || "제목 없음"}`);
    const rest = rows.length - shown.length;
    return shown.join("\n") + (rest > 0 ? `\n- 그 밖에 ${rest}건` : "");
  };
  const purgeSelected = async () => {
    // 🔴 문구가 사실과 달랐다. 예전에는 영구 삭제가 노션 페이지를 보관처리하는 것이었고
    // 되돌릴 여지는 **노션 휴지통**이 줬다. 지금은 이 서버가 정본이라 행을 진짜로 지우고
    // (`repository_native.archive`) 딸린 댓글·첨부도 CASCADE 로 함께 사라진다. 되돌릴 수
    // 없는 동작을 「30일 내 복구 가능」이라고 말하면 사용자는 그것을 믿고 누른다.
    const ok = await confirm(
      `다음 ${chosen.length}건을 영구 삭제합니다.\n\n${nameList(chosenRows)}\n\n댓글과 첨부까지 함께 지워지고 되돌릴 수 없습니다. 계속할까요?`,
      { title: "선택 영구 삭제", confirmLabel: "영구 삭제", danger: true },
    );
    if (ok) bulkPurge.mutate(chosen);
  };
  /* 열 너비는 열 정의가 든다(`type` + `ellipsis`) — 예전처럼 CSS nth-child로 잡으면
   * 선택 체크박스 열이 앞에 붙는 순간 한 칸씩 밀려 엉뚱한 열의 폭이 된다.
   * `fixed` 는 걷었다 — 그 배치에서는 `type` 이 주는 폭이 뜻을 잃는다(`kit.jsx::DataTable`).
   *
   * 🔴 **`hideNarrow` 가 하나도 없었다.** 이 열들의 바닥 폭 합이 83.5rem(1336px)이라
   * 1920 미만 어느 해상도에서도 표가 칸을 넘쳐 가로로 굴러갔고, 오른쪽 끝의 복원·영구삭제
   * 단추가 화면 밖으로 나갔다. 열 배분(`columnPlan.planColumns`)은 보조 열을 **오른쪽부터 필요한 만큼만** 숨기므로
   * 부가 열 셋에 표시를 달면 좁아지는 만큼 하나씩 빠진다.
   * 「삭제 예정」은 **절대 안 뺀다** — 24시간 안에 사라지는지가 이 화면의 판단 근거다. */
  const columns = [
    selCol,
    { key: "type_label", label: "종류", type: "status", render: (r) => <Badge value={r.type_label} kind={typeKind(r.item_type)} /> },
    {
      key: "title", label: "제목", type: "title", sortable: true,
      // rowName: 휴지통에서 행을 구별하는 값은 제목이다(ui/rowName.js). 여기가 영구 삭제를
      // 고르는 표라, 어느 줄을 고르는지 낭독되지 않으면 되돌릴 수 없는 실수가 난다.
      rowName: (r) => r.title || "제목 없음",
      /* 🔴 제목이 **그 항목의 본문으로 가는 길**이다. 종류마다 길이 다르다.
       *
       * 예전에는 옛 Notion 주소로 나가는 링크였고, 정본이 이 서버로 넘어오면서 그 주소가
       * 여는 것이 낡은 사본이 되어 걷어냈다(서버도 응답에서 `url` 을 뺐다). 그런데
       * **대체를 안 놓았다.** 그래서 이 표에서 지우려는 것이 무엇인지 제목 말고는 볼
       * 방법이 없었다 — 영구 삭제는 되돌릴 수 없는데도 그렇다. 사용자가 물어서 드러났다.
       *
       * Native 문서는 **문서 화면**으로 간다. 서버가 이미 열어 준다:
       * `get_scoped_document_or_404` 는 권한만 보고 `archived` 를 안 막는다. 새 탭으로
       * 여는 이유는 이 표가 고른 줄과 일괄 선택을 들고 있어서다 — 같은 탭에서 나갔다
       * 오면 그 선택이 사라진다.
       *
       * 옛 미러 항목과 티켓은 **미리보기 창**으로 간다. 그쪽은 상세 경로가 H2 가드로 막혀
       * 있어 열 화면이 없다 — 없는 링크를 만들지 않고, 대신 읽기 전용 경로를 연다. */
      render: (r) => {
        const id = docIdOf(r);
        return (
          <Box sx={{ minWidth: 0 }}>
            {/* 🔴 잘림을 **제목 줄 자신**이 든다. 표의 한 줄 래퍼(`ELLIPSIS_CELL_SX`)는
                셀의 **직계 인라인 내용**에만 「…」를 붙이는데, 발췌를 넣으면서 이 칸이
                블록 하나를 돌려주게 됐다 — 그러면 긴 제목이 「…」 없이 그냥 잘린다. */}
            {/* 제목 칸의 모양(링크색 600 · 한 줄 말줄임 · title)은 kit 의 `TitleCell` 이 갖는다 — 티켓 · 게시판 · 프로젝트
                표와 같은 제목 칸이다(조합 계약 C-3). */}
            {id ? (
              <TitleCell title={r.title} href={`#/knowledge/${id}`} target="_blank" rel="noreferrer" />
            ) : (
              <TitleCell title={r.title} onOpen={() => setPreview(r)} />
            )}
            {/* 본문 첫머리. 서버가 이미 계산해 두고 버리던 값이다(`list_page_extras`). */}
            {r.excerpt ? (
              <Typography variant="caption" color="text.secondary" sx={ONE_LINE}>
                {r.excerpt}
              </Typography>
            ) : null}
          </Box>
        );
      },
    },
    {
      /* 「어느 프로젝트의 문서였나」 (지시 22.7). 옛 미러 항목은 이 값을 모른다 — 그 개념이
         없는 표에서 왔다. 없는 값을 「-」로 지어내지 않고 자리를 비운다.
         🔴 `key` 가 `"place"` 였다. 데이터 필드는 `space` 라, 그 한 글자 때문에 이 칸만
         말줄임 힌트(`columnCellHint` 가 `row[c.key]` 를 읽는다)를 못 받았다. */
      key: "space", label: "프로젝트", type: "name", min: "10rem", hideNarrow: true,
      /* 폴더 줄은 걷었다 — 폴더 축이 화면에서 사라져(문서 개편 1·5번) 복원한 뒤 그
         폴더를 볼 자리가 없다. 응답의 `folder` 는 그대로 온다. */
      render: (r) => (r.space ? <Typography variant="body2">{r.space}</Typography> : ""),
    },
    {
      /* 값이 없을 때의 표기를 「프로젝트」 열과 맞춘다 — 한 표 안에서 빈칸과 「-」가
         섞이면 그 둘이 다른 뜻처럼 읽힌다(옛 미러 항목은 둘 다 「모른다」다). */
      key: "deleted_by", label: "삭제한 사람", type: "name", min: "11rem", hideNarrow: true,
      render: (r) => (r.deleted_by ? <Typography variant="body2">{r.deleted_by}</Typography> : ""),
    },
    {
      key: "deleted_at", label: "삭제일", type: "datetime", sortable: true, hideNarrow: true,
      render: (r) => <DateCell value={r.deleted_at} />,
    },
    {
      /* 🔴 「삭제 예정」이 비어 있는 것과 「자동으로 안 지운다」는 다른 사실이다.
         문서 휴지통의 자동 영구 삭제는 끌 수 있고(설정 `document_trash_autopurge`), 꺼져
         있으면 서버가 이 값을 안 싣는다 — 그때 빈 칸을 두면 사람은 「곧 사라지는데 날짜만
         안 보인다」로 읽는다. */
      key: "purge_after", label: "삭제 예정", type: "datetime", sortable: true,
      render: (r) => (r.purge_after
        ? <DateCell value={r.purge_after} />
        : <Typography variant="body2" color="text.secondary">자동 삭제 안 함</Typography>),
    },
    {
      /* 🔴 `label` 이 빈 문자열이라 이 열에는 스크린리더가 부를 이름이 없었고, 좁은 화면의
         카드 뷰에서는 이름 칸이 통째로 비었다. 그리고 셀은 가운데 정렬 계약(`actions`)인데
         내용만 `flex-end` 라 권한 없는 줄의 「권한 없음」과 좌우가 어긋났다 — 한 축으로 모은다.
         폭도 14rem 이었다: 실제 내용은 단추 둘 + 간격 + 셀 여백으로 11.75rem 이다. */
      key: "_actions", label: "작업", type: "actions", min: "11.5rem",
      /* 행 동작은 `RowActions` 다 — 「복원」은 30 보조, 「영구 삭제」는 파괴 단추다. 「복원」이 행마다 채움이었을 때
         휴지통 한 화면에 채움이 스무 개 섰다(조합 계약 C-4). */
      render: (r) => (r.can_manage ? (
        <RowActions
          actions={[
            { key: "restore", label: "복원", disabled: restore.isPending, onClick: () => restore.mutate(r) },
            {
              key: "purge", label: "영구 삭제", variant: "danger", disabled: purge.isPending,
              onClick: async () => {
                const trashName = r.title || "제목 없음";
                const ok = await confirm(
                  `‘${trashName}’${objectParticle(trashName)} 지금 영구 삭제하면 댓글과 첨부까지 함께 삭제되고 되돌릴 수 없습니다. 계속할까요?`,
                  { title: "영구 삭제", confirmLabel: "영구 삭제", danger: true });
                if (ok) purge.mutate(r);
              },
            },
          ]}
        />
      ) : <Typography variant="body2" color="text.secondary">권한 없음</Typography>),
    },
  ];

  /* 고른 항목에 할 일은 목록 판 발의 선택 묶음이다(조합 계약 C-3). 예전에는 화면 머리 동작 자리에 나타났다 사라졌다.
     「선택 복원」은 행의 「복원」과 같은 보조 단추다 — 되돌리는 일이라 파괴도 채움도 아니다. */
  const selection = {
    count: chosen.length,
    onClear: sel.clear,
    actions: (
      <>
        <Button size="sm" disabled={bulkRestore.isPending}
          onClick={() => bulkRestore.mutate(chosen)}>선택 복원</Button>
        <Button size="sm" variant="danger" disabled={bulkPurge.isPending} onClick={purgeSelected}>선택 영구 삭제</Button>
      </>
    ),
  };

  const urgent = counts ? counts.urgent : urgentCount(items);
  /* 조건이 걸려 0건인 것과 휴지통이 정말 빈 것은 다른 사실이다. 앞은 조건을 풀 자리를
     남겨야 하고, 뒤는 전면 안내가 맞다. */
  const filtered = !!kind;
  const empty = items.length === 0;

  /* 🔴 종류 조작기가 **진짜 탭**이다.
   *
   * 예전에는 한 축(`?kind=`)을 둘이 나눠 쥐고 있었다 — 큰 숫자 판독 줄이 필터 구실을 겸하고
   * 그 위에 「종류」 드롭다운이 또 있었다. 게다가 조건 결과가 0건이면 판독 줄이 통째로
   * 언마운트돼서, 조건을 걸어 비운 사람이 그 조건을 풀 자리를 잃었다. 사용자가 「탭도
   * 이상하고」라고 부른 것이 그 줄이다.
   *
   * 관용은 이 저장소에 이미 있다 — 제목 아래 `Tabs` 로 한 목록을 거른다(`MyApprovals.jsx`).
   * 숫자는 **탭 라벨**에 들어가고 서버의 조건-무관 개수에서 온다. */
  const tabs = (
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap", mb: 2 }}>
      {/* 종류 구분은 세그먼티드(34)다(계획 B-7). 숫자는 **서버가 준 것만** 적는다. 옛 응답이나 304 로
          `counts` 가 없으면 낱말만 남기고 조작기는 그대로 둔다 — 숫자를 지어내는 것보다 낫고, 조작기를
          통째로 없애는 것보다는 훨씬 낫다(그것이 이 화면의 원래 결함이었다). */}
      <Segmented
        ariaLabel="종류 구분" value={kind} onChange={(v) => setState({ kind: v })}
        options={KINDS.map((k) => ({ value: k.value, label: k.label, count: counts ? counts[k.countKey] : undefined }))}
      />
      {/* 「곧 사라진다」는 말만으로는 언제가 그 순간인지 알 수 없다. 누르면 임박한 순으로
          세워 준다 — 예전에는 같은 줄에 서 있으면서 혼자 누를 수 없는 칸이었다. */}
      {urgent > 0 ? (
        /* 누르는 것이라 30 단추다 — 칩 모양 조작기는 버튼 높이 집합 밖이다(핸드오프 RULES §3). 임박하다는
           사실은 낱말이 말하고 경고 아이콘 색이 거든다. */
        <Button
          size="sm"
          startIcon={<WarningAmberRoundedIcon fontSize="small" color="warning" />}
          onClick={() => setState({ sort: "purge_after", dir: "asc" })}
        >
          {`24시간 내 영구 삭제 ${urgent}`}
        </Button>
      ) : null}
    </Box>
  );

  return (
    <div className="c-screen">
      {/* PA-RC-0039: crumbRoot를 더 이상 손으로 고정하지 않는다 — AppShell의 CrumbRootProvider가
          지금 경로가 속한 navConfig 그룹에서 유도한다(부모 /team-docs와 항상 같은 값). 여기서
          "문서"를 계속 하드코딩하면 PA-RC-0031이 그 그룹 이름을 바꿀 때 부모만 따라가고 이
          자식은 옛 이름에 남아 갈라진다. */}
      <PageHeader
        area="휴지통" title="휴지통"
        description={
          docAuto
            ? `삭제한 티켓은 ${days}일, 문서는 ${docDays}일 동안 보관합니다. 그 전에 복원하면 원래 목록으로 돌아옵니다. 기간이 지나면 문서는 영구 삭제됩니다.`
            : `삭제한 티켓을 ${days}일 동안 보관합니다. 문서는 자동으로 삭제되지 않으며, 영구 삭제는 사람이 누를 때만 실행됩니다.`
        }
      />
      {trashNotice ? <Callout tone={trashNotice.tone} compact>{trashNotice.text}</Callout> : null}

      {q.isError ? <ErrorState layout="region" error={q.error} onRetry={() => q.refetch()} />
        : q.isPending ? <DataTable placement="surface" columns={columns} rows={[]} loading />
        : empty && !filtered ? (
          /* 정말 0건이면 탭 줄은 안 그린다 — 「전체 0 / 티켓 0 / 문서 0」은 소음이다. 목록 판(표 머리 아래 띠)은 다건과 같은
             셸이다(D-588) — 예전에는 판 없이 화면 가운데 큰 그림이었다(r23 화면 대장 22).
             WF1 R5 — 예전엔 여기서 "{days}일 동안 여기 보관됩니다"를 또 말했다, 바로 위 상시 안내문이 이미 같은 사실을 말한다. */
          <DataTable
            placement="surface" columns={columns} rows={[]}
            emptyState={(
              <EmptyState
                art="trash"
                title="휴지통이 비어 있습니다."
                help="삭제한 티켓이나 문서가 없습니다. 실수로 삭제했다면 이 화면에서 복원할 수 있습니다."
              />
            )}
          />
        ) : (
          <>
            {tabs}
            {/* 목록 판 — 조건 때문에 빈 목록 · 행 · 발(받은 건수 · 「휴지통 더 보기」 · 선택 묶음)이 한 판 안이다(조합 계약 C-3). */}
            <DataTable
              placement="surface"
              columns={columns} rows={items} rowKey={(r) => r.id} ellipsis
              sort={sort}
              onSort={(key) => {
                const next = toggleSort(sort, key, SORT_DEFAULT_DIR[key] || "asc");
                setState({ sort: next.key, dir: next.dir });
              }}
              emptyState={(
                /* 조건 때문에 비었다 — 조건을 풀 자리를 함께 준다. 탭 줄은 위에 그대로 있다. 판 안 빈 칸이라 region 이다. */
                <ListEmptyState
                  layout="region" filtered onClear={() => setState({ kind: "" })} clearLabel="전체 결과 보기"
                  filteredTitle={kind === "document" ? "휴지통에 문서가 없습니다." : kind === "ticket" ? "휴지통에 티켓이 없습니다." : "휴지통에 항목이 없습니다."}
                  filteredHelp="'전체 결과 보기'를 누르면 다른 종류의 항목을 볼 수 있습니다."
                />
              )}
              /* 🔴 여기만 **자동 로딩을 안 켠다**(`autoMaxRows: 0`) — 문서화된 예외다.
                 `/api/trash` 는 티켓과 문서 **두 원천을 각각 상한으로 받아 합쳐** 정렬한다
                 (`app/trash/router.py`). offset 이 없고, 얹으면 두 원천 사이 경계에서 항목이
                 중복·누락된다. 그래서 이 화면은 「상한을 키워 처음부터 다시 받는」 관용을
                 **의도적으로** 유지하고(`Trash.jsx` 머리말), 굴릴 때마다 100→200→300 을 연달아
                 다시 받는 일이 없게 단추로만 받는다. 문구는 다른 목록과 같은 부품이 낸다. */
              list={{
                total, loaded: items.length,
                hasNext: hasMore, isFetchingNext: fetchingNext, onMore: loadMore,
                autoMaxRows: 0,
                moreLabel: "휴지통 더 보기",
              }}
              selection={selection}
            />
          </>
        )}

      {preview ? <PreviewDialog row={preview} onClose={() => setPreview(null)} /> : null}
    </div>
  );
}
