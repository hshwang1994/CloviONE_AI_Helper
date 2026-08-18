import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Badge, Button, Callout, Card, DataTable, ErrorState, MetaBar, MetricStrip,
  PageHeader, SectionTitle, Skeleton, TechDetail, useConfirm, useToast,
} from "../ui/kit.jsx";
import { DateCell, NumberCell } from "../ui/cells.jsx";
import { FONT_WEIGHT } from "../ui/theme.js";
import { useAuth } from "../app/auth.jsx";
// 설정 값 그대로(`starttls`)는 설정 파일의 어휘다. 고르는 화면과 보는 화면이
// 같은 이름을 써야 한 값이 두 이름을 갖지 않는다.
import { SMTP_SECURITY_LABELS } from "./settings/settingsRegistry.js";

/* 메일 발송 (FN-01 · 지시 35 · 36 · 40).
 *
 * ## 이 화면이 답하는 순서
 *
 *   1. 지금 메일이 나가는가, 안 나가면 무엇을 고쳐야 하는가
 *   2. 지금 설정은 무엇인가
 *   3. 얼마나 나갔고 얼마나 실패했는가
 *   4. 실패한 그 메일들은 무엇인가
 *
 * ## 한 원인을 세 번 말하지 않는다 (지시 35 · 44)
 *
 * 예전에는 같은 사실이 세 곳에 있었다: 상단 진단 목록, `설정 안 됨` 건수 아래의 별도 안내
 * 상자, 그리고 표의 `오류` 열(실패 행마다 설정 문제 문장 전체가 다시 들어갔다). 세 번 읽어도
 * 새 정보가 없으면 그건 강조가 아니라 잡음이다.
 *   · 왜 못 보내는가 → 상단 한 곳(`ProblemsList`)
 *   · 재발송되지 않는다는 사실 → 그 숫자 바로 아래의 각주(`MetricStrip`의 note)
 *   · 표의 `원인` 열 → 그 행에 고유한 사실만. 설정 문제로 못 보낸 행은 위를 가리킨다.
 *
 * ## 내부 구현은 화면의 내용이 아니다 (지시 36)
 *
 * `backup_failed`(종류 키), `starttls`(설정 값), `SMTPAuthenticationError: ...`(예외 원문),
 * `2026-08-16T08:50:39.666400`(ISO 원문)은 전부 우리 구현이다. 서버가 이름을 주고
 * (`kind_label`·`status_label`·`error_summary`) 원문은 `TechDetail` 안에 접힌다 - 지우지는
 * 않는다. 장애를 분석하는 사람에게 원문은 유일한 단서다.
 *
 * ## 시험 발송은 자기 자신에게만
 *
 * 백엔드가 강제한다(임의 주소로 보내면 이 앱이 스팸 발송기가 된다) - 화면은 그 제약을
 * 다시 검사하지 않고 그대로 따른다.
 */

const WRITE_ROLES = ["admin", "system_admin"];

const HELP = "비밀번호 재설정, 승인 알림, 백업 실패 알림 메일이 실제로 나가는지 확인합니다. 시험 발송은 내 계정 주소로만 보냅니다.";


function ProblemsList({ problems }) {
  if (!problems || !problems.length) {
    return <Callout tone="success">메일 발송 설정이 완성돼 있습니다. 지금 메일이 나갑니다.</Callout>;
  }
  return (
    <Callout tone="warn">
      <Typography component="span" sx={{ fontWeight: FONT_WEIGHT.semibold }}>메일이 나가지 않습니다.</Typography>
      {" 아래를 고쳐야 나갑니다."}
      <Box component="ul" sx={{ m: 0, mt: 0.5, pl: 2.5 }}>
        {problems.map((p, i) => <li key={i}><Typography variant="body2">{p}</Typography></li>)}
      </Box>
    </Callout>
  );
}

/** 비밀번호는 값이 아니라 **상태**만 말한다 - 이름조차 화면의 주된 내용이 아니다. */
function passwordState(mail, server) {
  if (!server.username) return "사용 안 함";
  if (mail.password_secret === "configured") return "등록됨";
  return "등록 안 됨";
}

/** 그 행에 고유한 원인만. 원문은 접어 둔다 (지시 36). */
function FailureReason({ row }) {
  const blocked = row.status === "unconfigured";
  const summary = blocked
    ? "발송 설정이 없어 보내지 못했습니다. 위의 고칠 항목을 보세요."
    : row.error_summary;
  if (!summary) return "-";
  const raw = row.last_error;
  return (
    <>
      <Box sx={{ minWidth: 0 }}>{summary}</Box>
      {raw && raw !== summary ? <TechDetail sx={{ mt: 0.5 }}>{raw}</TechDetail> : null}
    </>
  );
}

const FAILURE_COLUMNS = [
  { key: "kind_label", label: "종류" },
  { key: "to_email", label: "받는 사람" },
  { key: "subject", label: "제목" },
  {
    key: "status_label", label: "상태",
    render: (r) => <Badge value={r.status_label} kind={r.status === "unconfigured" ? "warn" : "danger"} />,
  },
  { key: "attempt_count", label: "시도", hideNarrow: true, render: (r) => <NumberCell value={r.attempt_count} unit="회" /> },
  { key: "reason", label: "원인", render: (r) => <FailureReason row={r} /> },
  { key: "created_at", label: "발생", render: (r) => <DateCell value={r.created_at} /> },
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
      /* 실패 원문을 토스트에 붙이지 않는다 - 토스트는 사라지고, 예외 원문은 사라지는 자리에
         둘 것이 아니다. 결과 행은 아래 `최근 실패` 표에 남고 원문은 그 행의 기술 정보에 있다. */
      else toast("시험 메일을 보내지 못했습니다. 아래 최근 실패에서 원인을 확인하세요.", "error");
    },
    onError: (err) => toast((err && err.message) || "요청을 보내지 못했습니다. 잠시 후 다시 시도해 주세요.", "error"),
  });

  if (query.isLoading) return <Box className="c-screen"><PageHeader area="운영" title="메일 발송" help={HELP} /><Skeleton lines={6} /></Box>;
  if (query.isError) return <Box className="c-screen"><PageHeader area="운영" title="메일 발송" help={HELP} /><ErrorState error={query.error} onRetry={query.refetch} /></Box>;

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
        area="운영" title="메일 발송" help={HELP}
        actions={canWrite ? (
          <Button variant="primary" loading={test.isPending} onClick={sendTest}>시험 메일 보내기</Button>
        ) : null}
      />

      <ProblemsList problems={mail.problems} />

      <MetaBar
        ariaLabel="메일 서버 설정"
        sx={{ mt: 2 }}
        items={[
          { key: "enabled", label: "발송", value: <Badge value={server.enabled ? "사용" : "사용 안 함"} kind={server.enabled ? "ok" : "warn"} /> },
          { key: "host", label: "메일 서버", value: server.host ? server.host + ":" + (server.port == null ? "?" : server.port) : "설정 안 됨" },
          { key: "security", label: "보안 연결", value: SMTP_SECURITY_LABELS[server.security] || server.security || "설정 안 됨" },
          {
            key: "from", label: "보내는 사람",
            value: server.from_address
              ? (server.from_name ? server.from_name + " (" + server.from_address + ")" : server.from_address)
              : "설정 안 됨",
          },
          { key: "username", label: "로그인 계정", value: server.username || "사용 안 함" },
          { key: "secret", label: "비밀번호", value: passwordState(mail, server) },
        ]}
      />

      <MetricStrip
        ariaLabel="발송 현황"
        sx={{ mt: 2 }}
        items={[
          {
            key: "failed", label: "발송 실패", value: counts.failed || 0, primary: true,
            kind: counts.failed ? "danger" : undefined,
          },
          { key: "queued", label: "발송 대기", value: counts.queued || 0 },
          { key: "sent", label: "발송됨", value: counts.sent || 0 },
          {
            key: "blocked", label: "발송 못 함", value: counts.unconfigured || 0,
            kind: counts.unconfigured ? "warn" : undefined,
            /* MAIL-03: 이 건수는 설정을 나중에 고쳐도 저절로 줄지 않는다(queue_mail 이 설정
               문제를 만나면 재시도 잡 자체를 안 만든다). 그 사실을 별도 상자가 아니라 그
               숫자 바로 아래에 둔다 - 어느 숫자를 한정하는지 다시 찾을 필요가 없다. */
            note: counts.unconfigured
              ? "설정을 고쳐도 이 건들은 다시 보내지 않습니다. 고친 뒤 새로 생기는 메일부터 나갑니다."
              : null,
          },
        ]}
      />

      <Card sx={{ mt: 2, p: 0, overflow: "hidden" }}>
        <SectionTitle title="최근 실패" component="h2" sx={{ p: 2, pb: 1 }} />
        <DataTable
          columns={FAILURE_COLUMNS} rows={failures} rowKey={(r) => r.id}
          empty="최근 실패한 메일이 없습니다."
        />
      </Card>
    </Box>
  );
}

export default MailStatus;
