import React from "react";
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { actionKo, fmtDateTime } from "../lib/format.js";
import { failureText } from "../lib/failure.js";
import {
  Badge, Callout, DataTable, EmptyState, ErrorState, PageHeader, RowActions, useConfirm, useToast,
  Segmented,
} from "../ui/kit.jsx";
import { OrgPath } from "../ui/OrgPath.jsx";
import { DateCell } from "../ui/cells.jsx";
import { useInfiniteList } from "../lib/useInfiniteList.js";
import { useQueryState } from "../lib/useQueryState.js";
import { celebrateIfCleared } from "../ui/celebrate.js";

/* 개인 결재함 — **승인은 개인 업무이기도 하다** (0060 §22).
 *
 * ## 왜 관리자 콘솔의 승인 화면과 따로 있는가
 *
 * 결재 권한은 역할로만 오는 것이 아니다. 부재 중 위임을 받으면 **일반 사용자도** 결재자가
 * 된다(app/approvals/delegation.py). 그런데 승인 화면이 관리자 콘솔에만 있던 동안 그 사람은:
 *
 *   * "당신이 결재할 차례입니다" 알림은 받고,
 *   * 그 딥링크는 관리자 화면을 가리키는데,
 *   * 그 화면에는 들어갈 수 없었다(`GET /api/admin/approvals` 는 콘솔 읽기 권한 필요).
 *
 * 즉 결재를 부탁받고도 결재할 방법이 없었다. 여기가 그 사람의 자리다.
 *
 * 관리자 콘솔의 `/approvals` 는 없어지지 않는다 — 그쪽은 **관리 범위 전체의 승인 현황**
 * 이고 이쪽은 **나에게 배정된 일**이다. 목적이 달라 한 화면으로 합칠 수 없다.
 */

/* 칸마다 «없다» 의 뜻이 다르다 — 처리할 것이 없는 것은 좋은 소식이고, 올린 것이 없는 것은
 * 아직 아무것도 안 한 것이다. 한 문장으로 뭉치면 화면이 그 차이를 못 말한다. */
const BOXES = [
  { key: "todo", label: "처리할 승인", empty: "지금 결재할 건이 없습니다.",
    emptyHelp: "나에게 배정된 결재가 생기면 여기에 나타납니다." },
  { key: "requested", label: "내가 올린 요청", empty: "내가 올린 승인 요청이 없습니다.",
    emptyHelp: "승인이 필요한 일을 하면 그 요청이 여기에 쌓입니다." },
  { key: "done", label: "내가 처리한 건", empty: "아직 결재한 건이 없습니다.",
    emptyHelp: "승인하거나 거절한 건이 여기에 기록으로 남습니다." },
];

const STATUS_KIND = {
  pending: "warn", approved: "ok", rejected: "danger",
  expired: "neutral", cancelled: "neutral",
};
const STATUS_KO = {
  pending: "대기", approved: "승인됨", rejected: "거절됨",
  expired: "만료", cancelled: "취소됨",
};

/* 결재하기 직전에 **무엇을 결재하는지** 한 문장으로 적는다.
 *
 * 승격 요청의 대상 이름·이메일은 서버가 그 목적으로 payload 에 함께 싣는다
 * (`app/users/router.py` 의 role_change 승인 생성 — target_name/target_email). 그 값이 없는
 * 요청 유형은 대상 유형과 ID 로 떨어진다 — 「무엇인지 모르겠다」가 「아무것도 안 적혀 있다」
 * 보다 낫다.
 *
 * 🔴 예전에는 「요청: …」·「요청자: …」·「대상: …」 세 조각을 `\n` 으로 이어 붙였다. 화면
 * 문구에 `\n` 을 넣지 않는 것이 이 저장소의 규칙이고(CLAUDE.md §10), 이름표와 값을 콜론으로
 * 나열한 조각은 완전한 문장도 아니다. 줄바꿈은 `pre-line` 이라는 CSS 한 줄에 기대는 배치라
 * 그 한 줄이 바뀌면 문구가 한 줄로 뭉개진다 — 같은 사실을 주어와 서술어가 있는 문장으로 적는다. */
function decisionSummary(r) {
  const p = (r && r.request_payload) || {};
  const target = p.target_name || p.target_email
    || (r.object_type ? (r.object_type + " " + (r.object_id || "")).trim() : "");
  const what = actionKo(r.request_type) || r.request_type;
  const requester = r.requester_name || r.requester_email || r.requested_by;
  const who = requester ? requester + "님이 올린" : "요청자를 알 수 없는";
  return target
    ? who + " ‘" + what + "’ 요청이고, 대상은 " + target + "입니다."
    : who + " ‘" + what + "’ 요청입니다.";
}

/* 확인 문구는 관리자 콘솔의 승인 화면과 같은 말을 쓴다(registry/governance.js 의 거절 확인) —
   같은 API 를 부르는 두 화면이 서로 다른 무게로 물으면 한쪽이 거짓말이 된다. */
const CONFIRM_TEXT = {
  approve: (r) => "이 요청을 승인하면 되돌릴 수 없습니다. " + decisionSummary(r)
    + " 내용이 맞으면 계속 승인할까요?",
  reject: (r) => "이 요청을 거절하면 되돌릴 수 없습니다. 같은 건을 다시 승인할 방법이 없고 요청자가 새로 요청해야 합니다. "
    + decisionSummary(r) + " 내용이 맞으면 계속 거절할까요?",
};

/* 고른 칸과 쪽은 **주소에** 둔다 (S15 · `lib/useQueryState.js`).
 *
 * 서버는 이 목록을 자르고 총 건수를 함께 준다(app/approvals/router.py). 한때 화면이 그 둘을
 * 다 무시하고 첫 20건만 그렸다 — 21번째 결재 건은 있다는 사실조차 화면에 없었고, 결재는
 * **놓치면 남이 못 하는** 일이라 그 침묵이 그대로 지연이 된다. 지금은 굴리면 이어 받는다. */
const APPROVAL_SPEC = { box: "todo" };

export function MyApprovals() {
  const [view, setView] = useQueryState(APPROVAL_SPEC);
  const { box } = view;
  const setBox = (next) => setView({ box: next });
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();

  /* 방금 결재한 줄은 **그 자리에 남는다** (id → "approved" | "rejected").
   *
   * 예전에는 결재가 성공하는 순간 목록을 다시 받아 그 줄이 빠졌고, 아래 줄이 커서 밑으로
   * 올라왔다 — 같은 자리를 한 번 더 누른 사람이 **열어 본 적 없는 다른 사람의 승격**을
   * 승인했다(실측으로 계정 둘이 연속 admin 이 됐다). 결재는 되돌릴 수 없으므로 그 사고는
   * 사과로 끝나지 않는다.
   *
   * 그래서 이 칸을 보는 동안 목록은 스스로 다시 정렬되지 않는다. 결재한 줄은 「승인함」·
   * 「거절함」으로 바뀌고 단추가 사라질 뿐 자리를 지킨다. 새 목록은 칸을 옮기거나 화면을
   * 다시 열 때 받는다. */
  const [decided, setDecided] = React.useState({});
  React.useEffect(() => { setDecided({}); }, [box]);
  const hasDecided = Object.keys(decided).length > 0;

  const q = useInfiniteList({
    key: ["my-approvals", box],
    rowId: (r) => (r && r.id) || undefined,
    fetch: ({ page }) => api(`/api/approvals/mine?box=${box}` + (page > 1 ? `&page=${page}` : "")),
    /* 승인 큐는 여러 사람과 자동 만료(72h)가 동시에 건드리는 경합 자원이다 — 열어 둔 채로
       남이 먼저 처리한 건을 눌러 낡은 409 를 보지 않도록 주기적으로 다시 읽는다.
       🔴 **첫 묶음만 받아 둔 동안에만** 켠다: 무한 질의를 다시 받으면 react-query 가 받아 둔
       묶음을 전부 순서대로 다시 부른다 — 다섯 묶음이면 30초마다 요청이 다섯 번이다.
       더 받기 시작한 사람은 스스로 새로 받는다(탭을 옮기거나 결재를 처리한다).
       🔴 **결재한 줄이 하나라도 화면에 남아 있으면 끈다** — 이 폴링이 30초 뒤에 목록을 다시
       받으면 위 `decided` 가 지켜 둔 자리가 그 순간 무너진다(그 결함을 없애려고 남긴 자리다). */
    refetchInterval: box === "todo" && !hasDecided
      ? (qy) => (((qy.state.data && qy.state.data.pages) || []).length === 1 ? 30 * 1000 : false)
      : false,
  });

  const decide = useMutation({
    mutationFn: ({ id, approve }) =>
      api(`/api/admin/approvals/${id}/${approve ? "approve" : "reject"}`, {
        method: "POST", body: {},
      }),
    onSuccess: (_res, vars) => {
      toast(vars.approve ? "승인했습니다." : "거절했습니다.");
      setDecided((prev) => ({ ...prev, [vars.id]: vars.approve ? "approved" : "rejected" }));
      /* 🔴 「한 건 처리했다」가 아니라 **「처리할 게 없어졌다」**에만 축하한다. 방금 것을
         빼고도 남아 있으면 축포는 방해다. 세는 값은 지금 칸이 「처리할 승인」일 때의
         남은 건수이고, 못 세면(총계가 없는 응답) 아무것도 안 한다. */
      if (box === "todo" && typeof q.total === "number") celebrateIfCleared(q.total - 1);
      /* 세 칸이 같은 자원을 다르게 자른 것이라 한 번에 무효화한다 — 하나만 갱신하면
         '처리할 승인'에서 사라진 건이 '내가 처리한 건'에는 안 나타난다.
         🔴 **지금 보고 있는 칸의 목록만 빼 둔다.** 그 한 벌을 다시 받으면 방금 결재한 줄이
         빠지면서 아래 줄이 커서 밑으로 올라온다 — 위 `decided` 가 막으려는 바로 그 일이다.
         사이드바 배지(`["my-approvals","todo","badge"]`)와 다른 칸은 그대로 갱신한다. */
      qc.invalidateQueries({
        queryKey: ["my-approvals"],
        predicate: (query) => !(query.queryKey[1] === box && query.queryKey[2] === "inf"),
      });
      qc.invalidateQueries({ queryKey: ["noti"] });
    },
  });
  /* 결재 실패는 목록 위에 남는다 — 되돌릴 수 없는 결재가 됐는지 안 됐는지는 사라지면 안 되는 사실이다. */
  const decideFailure = failureText([decide, "처리하지 못했습니다."]);

  /* 결재 한 번은 되돌릴 수 없다 — 누구의 무엇을 결재하는지 먼저 확인받는다.
     관리자 콘솔의 같은 API 도 승인에 메모 폼을, 거절에 확인 창을 받는다. */
  async function askAndDecide(row, approve) {
    const ok = await confirm(approve ? CONFIRM_TEXT.approve(row) : CONFIRM_TEXT.reject(row), {
      title: approve ? "승인" : "거절",
      confirmLabel: approve ? "승인" : "거절",
      danger: !approve,
    });
    if (ok) decide.mutate({ id: row.id, approve });
  }

  /* 목록 밖의 값(결재 권한)은 첫 묶음 원본이 들고 온다 — 묶음마다 같다. */
  const data = q.first;
  const canDecide = data ? data.can_decide : true;
  const current = BOXES.find((b) => b.key === box) || BOXES[0];

  const columns = [
    /* 요청 종류는 닫힌 집합이다 — 식별자가 아니라 낱말이라 `enum` 이다. 예전에는
       `identifier: true` 라 12.5rem 바닥을 받고 그 폭의 29% 만 채웠다(실측). */
    {
      key: "request_type", label: "요청", type: "enum", minWidth: "9rem",
      render: (r) => actionKo(r.request_type) || r.request_type,
    },
    {
      key: "requested_by", label: "요청자", type: "name", minWidth: "13rem",
      // 사람이 나오는 자리에는 **조직 경로를 함께** 보여 준다(0060 §5) — 동명이인을 구별할
      // 방법이 화면에 없으면 잘못된 요청을 승인하게 된다.
      /* 이 칸은 두 줄로 쌓인다(이름 + 조직 경로). 칸의 정렬은 `text-align` 하나뿐이라
         안쪽 블록이 자기 폭을 가지면 두 줄의 시작점이 서로 어긋난다 — 두 줄을 같은
         축에 세우려면 안쪽도 함께 가운데로 맞춰야 한다. */
      render: (r) => (
        <Box sx={{ minWidth: 0, display: "flex", flexDirection: "column", alignItems: "center" }}>
          <Typography variant="body2" sx={{ minWidth: 0 }}>
            {r.requester_name || r.requested_by}
          </Typography>
          <OrgPath path={r.requester_path} variant="short" />
        </Box>
      ),
    },
    { key: "object", label: "대상", type: "text", render: (r) => r.object_type ? `${r.object_type} ${r.object_id || ""}`.trim() : "-" },
    {
      key: "status", label: "상태", type: "status",
      // 방금 결재한 줄은 목록을 다시 받지 않아도 결과를 말한다 — 자리를 지키면서 「대기」로
      // 남아 있으면 그 줄이 아직 안 끝난 것으로 읽힌다.
      render: (r) => {
        const st = decided[r.id] || r.status;
        return <Badge value={STATUS_KO[st] || st} kind={STATUS_KIND[st]} />;
      },
    },
    {
      key: "requested_at", label: "요청 시각", type: "datetime",
      render: (r) => <DateCell value={r.requested_at} />,
    },
  ];

  if (box === "todo") {
    columns.push({
      key: "actions", label: "결재", type: "actions",
      render: (r) => {
        // 결재가 끝난 줄에는 단추를 안 그린다 — 서버가 409 로 막을 두 번째 클릭을 화면이
        // 먼저 없앤다. 자리는 그대로 두어 아래 줄이 커서 밑으로 올라오지 않게 한다.
        if (decided[r.id]) {
          return (
            <Typography variant="body2" color="text.secondary">
              {decided[r.id] === "approved" ? "승인했습니다." : "거절했습니다."}
            </Typography>
          );
        }
        /* 행 동작은 `RowActions` 다 — 「승인」은 30 보조, 「거절」은 파괴 단추다. 결재 한 건은 확인 창을 거치므로 행마다
           채움을 세울 이유가 없다(조합 계약 C-4). */
        return (
          <RowActions
            actions={[
              { key: "approve", label: "승인", disabled: decide.isPending, onClick: () => askAndDecide(r, true) },
              { key: "reject", label: "거절", variant: "danger", disabled: decide.isPending, onClick: () => askAndDecide(r, false) },
            ]}
          />
        );
      },
    });
  }

  return (
    <Box className="c-screen">
      <PageHeader
        area="내 업무" title="승인"
        help="나에게 배정된 결재와 내가 올린 요청입니다. 관리 범위 전체 현황은 관리자 콘솔의 승인 화면에 있습니다."
      />
      {/* 보기 전환은 세그먼티드(34)다 — 밑줄 탭(48)은 페이지 탭(`TabShell`)의 어휘다(핸드오프 RULES §3 · 계획 B-7). */}
      <Segmented
        ariaLabel="결재함 구분" value={box} onChange={setBox}
        options={BOXES.map((b) => ({ value: b.key, label: b.label }))}
        sx={{ mb: 2 }}
      />

      {q.isError ? <ErrorState layout="region" error={q.error} onRetry={() => q.refetch()} /> : null}
      {decideFailure ? <Callout tone="danger" compact sx={{ mb: 2 }}>{decideFailure}</Callout> : null}
      {!q.first && !q.isError ? <DataTable placement="surface" columns={columns} rows={[]} loading /> : null}

      {data && box === "todo" && !canDecide ? (
        <EmptyState
          layout="page"
          title="결재 권한이 없습니다"
          help="지금은 결재할 수 있는 자리가 아닙니다. 부재 중 위임을 받으면 이 목록에 결재할 건이 나타납니다."
          art="noPermission"
        />
      ) : null}

      {/* 아래 `art="success"` 는 예전에 `"done"` 이었다 — ART 에 없는 키라 일러스트가 조용히
          안 그려졌다(Integrity.jsx 와 같은 오배선). */}
      {data && (box !== "todo" || canDecide) ? (
        q.rows.length === 0 ? (
          /* 세 칸 전부 화면 전체가 비는 자리다 — 탭 아래에 이 상태밖에 없다. */
          <EmptyState layout="page" title={current.empty} help={current.emptyHelp} art="success" />
        ) : (
          /* 목록 판 — 받은 건수와 「결재 더 보기」는 판 안 발이다(조합 계약 C-3). */
          <DataTable
            placement="surface"
            columns={columns} rows={q.rows} rowKey={(r) => r.id} total={q.total}
            list={{
              total: q.total, loaded: q.loaded,
              hasNext: q.hasNext, isFetchingNext: q.isFetchingNext, onMore: q.fetchNext,
              moreLabel: "결재 더 보기",
            }}
          />
        )
      ) : null}
    </Box>
  );
}

export default MyApprovals;
