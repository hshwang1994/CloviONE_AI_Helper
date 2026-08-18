import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { actionKo, fmtDateTime } from "../lib/format.js";
import {
  Badge, Button, Card, DataTable, EmptyState, ErrorState, PageHeader, useToast,
} from "../ui/kit.jsx";
import { OrgPath } from "../ui/OrgPath.jsx";
import { DateCell } from "../ui/cells.jsx";

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

const BOXES = [
  { key: "todo", label: "처리할 승인", empty: "지금 결재할 건이 없습니다." },
  { key: "requested", label: "내가 올린 요청", empty: "내가 올린 승인 요청이 없습니다." },
  { key: "done", label: "내가 처리한 건", empty: "아직 결재한 건이 없습니다." },
];

const STATUS_KIND = {
  pending: "warn", approved: "ok", rejected: "danger",
  expired: "neutral", cancelled: "neutral",
};
const STATUS_KO = {
  pending: "대기", approved: "승인됨", rejected: "거절됨",
  expired: "만료", cancelled: "취소됨",
};

export function MyApprovals() {
  const [box, setBox] = React.useState("todo");
  const toast = useToast();
  const qc = useQueryClient();

  const q = useQuery({
    queryKey: ["my-approvals", box],
    queryFn: () => api(`/api/approvals/mine?box=${box}`),
    // 승인 큐는 여러 사람과 자동 만료(72h)가 동시에 건드리는 경합 자원이다 — 열어 둔 채로
    // 남이 먼저 처리한 건을 눌러 낡은 409 를 보지 않도록 주기적으로 다시 읽는다.
    refetchInterval: box === "todo" ? 30 * 1000 : false,
  });

  const decide = useMutation({
    mutationFn: ({ id, approve }) =>
      api(`/api/admin/approvals/${id}/${approve ? "approve" : "reject"}`, {
        method: "POST", body: {},
      }),
    onSuccess: (_res, vars) => {
      toast(vars.approve ? "승인했습니다." : "거절했습니다.");
      // 세 칸이 같은 자원을 다르게 자른 것이라 한 번에 무효화한다 — 하나만 갱신하면
      // '처리할 승인'에서 사라진 건이 '내가 처리한 건'에는 안 나타난다.
      qc.invalidateQueries({ queryKey: ["my-approvals"] });
      qc.invalidateQueries({ queryKey: ["noti"] });
    },
    onError: (err) => toast(err?.message || "처리하지 못했습니다.", "danger"),
  });

  const data = q.data;
  const canDecide = data ? data.can_decide : true;
  const current = BOXES.find((b) => b.key === box) || BOXES[0];

  const columns = [
    {
      key: "request_type", label: "요청", identifier: true, nowrap: true,
      render: (r) => actionKo(r.request_type) || r.request_type,
    },
    {
      key: "requested_by", label: "요청자",
      // 사람이 나오는 자리에는 **조직 경로를 함께** 보여 준다(0060 §5) — 동명이인을 구별할
      // 방법이 화면에 없으면 잘못된 요청을 승인하게 된다.
      render: (r) => (
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="body2" sx={{ minWidth: 0 }}>
            {r.requester_name || r.requested_by}
          </Typography>
          <OrgPath path={r.requester_path} variant="short" />
        </Box>
      ),
    },
    { key: "object", label: "대상", render: (r) => r.object_type ? `${r.object_type} ${r.object_id || ""}`.trim() : "-" },
    {
      key: "status", label: "상태", nowrap: true,
      render: (r) => <Badge value={STATUS_KO[r.status] || r.status} kind={STATUS_KIND[r.status]} />,
    },
    {
      key: "requested_at", label: "요청 시각", nowrap: true,
      nowrap: true,
      render: (r) => <DateCell value={r.requested_at} />,
    },
  ];

  if (box === "todo") {
    columns.push({
      key: "actions", label: "결재", nowrap: true,
      render: (r) => (
        <Box sx={{ display: "flex", gap: 1 }}>
          <Button size="sm" variant="primary" disabled={decide.isPending}
            onClick={() => decide.mutate({ id: r.id, approve: true })}>승인</Button>
          <Button size="sm" variant="danger" disabled={decide.isPending}
            onClick={() => decide.mutate({ id: r.id, approve: false })}>거절</Button>
        </Box>
      ),
    });
  }

  return (
    <Box className="c-screen">
      <PageHeader
        area="내 업무" title="승인"
        help="나에게 배정된 결재와 내가 올린 요청입니다. 관리 범위 전체 현황은 관리자 콘솔의 승인 화면에 있습니다."
      />
      <Tabs
        value={box}
        onChange={(_e, v) => setBox(v)}
        sx={{ mb: 2 }}
        aria-label="결재함 구분"
      >
        {BOXES.map((b) => <Tab key={b.key} value={b.key} label={b.label} />)}
      </Tabs>

      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : null}
      {!q.data && !q.isError ? <Card>{/* 표가 들어올 자리에는 표 모양을 그린다 (지시 20) - 빈 목록과 아직 안 온 목록은 다른 사실이다. */}<DataTable columns={columns} rows={[]} loading /></Card> : null}

      {data && box === "todo" && !canDecide ? (
        <EmptyState
          title="결재 권한이 없습니다"
          help="지금은 결재할 수 있는 자리가 아닙니다. 부재 중 위임을 받으면 이 목록에 결재할 건이 나타납니다."
          art="noPermission"
        />
      ) : null}

      {/* 아래 `art="success"` 는 예전에 `"done"` 이었다 — ART 에 없는 키라 일러스트가 조용히
          안 그려졌다(Integrity.jsx 와 같은 오배선). */}
      {data && (box !== "todo" || canDecide) ? (
        data.items.length === 0 ? (
          <EmptyState title={current.empty} art="success" />
        ) : (
          <Card>
            <DataTable columns={columns} rows={data.items} rowKey={(r) => r.id} />
          </Card>
        )
      ) : null}
    </Box>
  );
}

export default MyApprovals;
