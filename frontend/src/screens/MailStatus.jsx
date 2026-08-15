import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Badge, Button, Callout, Card, DataTable, ErrorState, PageHeader, Skeleton,
  useConfirm, useToast,
} from "../ui/kit.jsx";
import { FONT_WEIGHT } from "../ui/theme.js";
import { useAuth } from "../app/auth.jsx";

/* 메일 발송 상태 (FN-01).
 *
 * ## 왜 이 화면이 필요한가
 *
 * `app/mail/router.py`는 처음부터 진단(`GET /status`)과 시험 발송(`POST /test`)을 완성해
 * 뒀는데, 그걸 띄우는 화면이 하나도 없었다 — 실서버 확인 결과 `configured:false`에
 * "SMTP 서버 주소가 비어 있습니다" 같은 한국어 진단까지 이미 나와 있었지만 아무도 볼 방법이
 * 없었다. 그동안 비밀번호 재설정·승인 알림·백업 실패 알림 메일이 조용히 안 갔다.
 *
 * ## 시험 발송은 자기 자신에게만
 *
 * 백엔드가 강제한다(임의 주소로 보내면 이 앱이 스팸 발송기가 된다) — 화면은 그 제약을
 * 다시 검사하지 않고 그대로 따른다.
 */

const WRITE_ROLES = ["admin", "system_admin"];

function ProblemsList({ problems }) {
  if (!problems || !problems.length) {
    return <Callout tone="success">문제가 없습니다. 메일 발송 설정이 완성돼 있습니다.</Callout>;
  }
  return (
    <Callout tone="warn">
      <Typography sx={{ fontWeight: FONT_WEIGHT.bold, mb: 0.5 }}>메일이 나가지 않는 이유</Typography>
      <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
        {problems.map((p, i) => <li key={i}><Typography variant="body2">{p}</Typography></li>)}
      </Box>
    </Callout>
  );
}

const FAILURE_COLUMNS = [
  { key: "kind", label: "종류" },
  { key: "to_email", label: "받는 사람" },
  { key: "subject", label: "제목" },
  { key: "status_label", label: "상태", render: (r) => <Badge value={r.status_label} kind="danger" /> },
  { key: "attempt_count", label: "시도 횟수" },
  { key: "last_error", label: "오류", render: (r) => r.last_error || "-" },
  { key: "created_at", label: "발생" },
];

export function MailStatus() {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const auth = useAuth();
  const role = (auth.data && auth.data.role) || "";
  const canWrite = WRITE_ROLES.includes(role);

  const query = useQuery({
    queryKey: ["mail-status"],
    queryFn: () => api("/api/admin/mail/status"),
  });

  const test = useMutation({
    mutationFn: () => api("/api/admin/mail/test", { method: "POST" }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["mail-status"] });
      const d = data && data.delivery;
      if (d && d.status === "sent") toast("시험 메일을 보냈습니다. 받은 편지함을 확인하세요.", "success");
      else toast("시험 메일을 보내지 못했습니다" + (d && d.last_error ? ": " + d.last_error : "") + ". 위 설정을 확인하세요.", "error");
    },
    onError: (err) => toast((err && err.message) || "요청을 보내지 못했습니다. 잠시 후 다시 시도해 주세요.", "error"),
  });

  if (query.isLoading) return <Box className="c-screen"><PageHeader area="운영" title="메일 발송" /><Skeleton lines={6} /></Box>;
  if (query.isError) return <Box className="c-screen"><PageHeader area="운영" title="메일 발송" /><ErrorState error={query.error} onRetry={query.refetch} /></Box>;

  const data = query.data || {};
  const mail = data.mail || {};
  const server = mail.server || {};
  const counts = data.counts || {};
  const failures = data.recent_failures || [];

  async function sendTest() {
    if (!(await confirm(
      "내 계정(" + ((auth.data && auth.data.email) || "") + ")으로 시험 메일을 보낼까요?",
      { confirmLabel: "시험 발송" }
    ))) return;
    await test.mutateAsync();
  }

  return (
    <Box className="c-screen">
      <PageHeader
        area="운영" title="메일 발송"
        actions={canWrite ? (
          <Button variant="primary" disabled={test.isPending} onClick={sendTest}>시험 메일 보내기</Button>
        ) : null}
      />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
        비밀번호 재설정, 승인 알림, 백업 실패 알림 메일이 실제로 나가는지 확인합니다.
      </Typography>

      <ProblemsList problems={mail.problems} />

      <Card sx={{ mt: 2, p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>서버 설정</Typography>
        <Box sx={{ display: "grid", gap: 0.5 }}>
          {/* Badge(Chip→div)를 Typography 기본 태그(p)의 자식으로 두면 DOM 중첩이 깨진다
              (div는 p 안에 못 들어간다) — component="div"로 바꾼다. */}
          <Typography component="div">사용: <Badge value={server.enabled ? "활성" : "비활성"} kind={server.enabled ? "ok" : "warn"} /></Typography>
          <Typography>주소: {server.host ? server.host + ":" + server.port : "설정 안 됨"}</Typography>
          <Typography>보안: {server.security || "설정 안 됨"}</Typography>
          <Typography>보내는 사람: {server.from_address || "설정 안 됨"}{server.from_name ? " (" + server.from_name + ")" : ""}</Typography>
        </Box>
      </Card>

      <Card sx={{ mt: 2, p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>발송 현황</Typography>
        <Box sx={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
          <Typography>대기 {counts.queued || 0}건</Typography>
          <Typography>발송됨 {counts.sent || 0}건</Typography>
          <Typography color={counts.failed ? "error" : "text.primary"}>실패 {counts.failed || 0}건</Typography>
          <Typography color={counts.unconfigured ? "warning.main" : "text.primary"}>
            설정 안 됨(발송 못 함) {counts.unconfigured || 0}건
          </Typography>
        </Box>
        {/* MAIL-03: 이 건수는 SMTP를 나중에 고쳐도 저절로 줄지 않는다(queue_mail이
            설정 문제를 만나면 애초에 재시도 잡 자체를 안 만든다) — 관리자가 "설정을
            고치면 이 숫자가 빠지겠지"로 오해하기 쉬워 명시적으로 알린다. */}
        {counts.unconfigured ? (
          <Box sx={{ mt: 1.5 }}>
            <Callout tone="warn">
              이 건수는 SMTP 설정을 고쳐도 자동으로 재발송되지 않습니다. 설정을 고친
              뒤 새로 발생하는 메일부터 정상 발송됩니다.
            </Callout>
          </Box>
        ) : null}
      </Card>

      <Card sx={{ mt: 2, p: 0, overflow: "hidden" }}>
        <Typography variant="h6" sx={{ p: 2, pb: 1 }}>최근 실패</Typography>
        <DataTable
          columns={FAILURE_COLUMNS} rows={failures} rowKey={(r) => r.id}
          empty="최근 실패한 메일이 없습니다."
        />
      </Card>
    </Box>
  );
}

export default MailStatus;
