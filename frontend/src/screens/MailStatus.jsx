import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { failureText } from "../lib/failure.js";
import {
  Badge, Button, Callout, Card, DataTable, EmptyState, ErrorState, MetaBar, Section, Segmented, Skeleton, TechDetail,
  useConfirm, useToast,
} from "../ui/kit.jsx";
import { SettingRow } from "../ui/adminKit.jsx";
import { HeaderActions } from "../ui/HeaderSlot.jsx";
import { TabShell } from "../ui/TabShell.jsx";
import { DataScreen } from "./DataScreen.jsx";
import { MAIL_DELIVERIES } from "./mail/mailDeliveries.js";
import { fmtDateTimeCompact } from "./registry/shared.js";
import { StatusSummaryCard } from "../ui/StatusKpi.jsx";
import { DateCell, NumberCell } from "../ui/cells.jsx";
import { FONT_WEIGHT } from "../ui/theme.js";
import { useAuth } from "../app/auth.jsx";
// 설정 값 그대로(`starttls`)는 설정 파일의 어휘다. 고르는 화면과 보는 화면이
// 같은 이름을 써야 한 값이 두 이름을 갖지 않는다.
import { SMTP_SECURITY_LABELS } from "./settings/settingsRegistry.js";
import { CONSOLE_WRITE_ROLES } from "../lib/roles.js";

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
 *   · 재발송되지 않는다는 사실 → 그 숫자의 각주(상태 요약 카드의 정의 목록 `notes`, 예전에는 판독 줄 칸의 note)
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

// 값의 정본은 서버(app/core/authz.py)이고, 화면 쪽 사본은 lib/roles.js 한 곳이다(지시 21).

const HELP = "비밀번호 재설정, 승인 알림, 백업 실패 알림 메일이 실제로 나가는지 확인합니다. 시험 발송은 내 계정 주소로만 보냅니다.";


/* 메일 설정 한 줄을 여는 주소 — 설정 표가 `?setting=` 으로 그 항목의 편집 창을 연다(`SettingsMain.jsx`). 초기 설정의
   메일 항목(`SetupWizard.jsx::SETUP_LINKS.mail`)과 같은 곳이다. */
const MAIL_SETTING_HREF = "#/settings?setting=smtp";
/* 시험 발송 단추가 가리키는 이유 문장의 자리(`aria-describedby`). */
const PROBLEMS_ID = "mail-problems";

/* 건강 상태(계획 2.4 · 3.3) — 「값이 있다」와 「동작한다」를 가른다. 서버가 저장된 상태만 읽어 준다(`app/mail/health.py`):
   미설정이면 무엇을 고칠지(아래 `ProblemsList`), 확인 전이면 연결 확인을, 정상이면 마지막 확인 시각을, 발송 실패면 그
   까닭을 말한다. 예전에는 설정이 채워지면 「지금 메일이 나갑니다」라고 했다 — 비밀번호가 틀려도 그랬다. */
function HealthStatus({ health, problems, canFix }) {
  const h = health || {};
  if (!h.state || h.state === "unconfigured") return <ProblemsList problems={problems} canFix={canFix} />;
  const checked = h.checked_at ? " 마지막 확인 " + fmtDateTimeCompact(h.checked_at) + "." : "";
  if (h.state === "ok") {
    return <Callout tone="success">메일 서버에 정상으로 연결했습니다.{checked}</Callout>;
  }
  if (h.state === "unverified") {
    return <Callout tone="info">메일 설정은 채워졌지만 아직 발송을 확인하지 않았습니다. 연결 확인으로 확인하세요.</Callout>;
  }
  return (
    <Callout tone="danger" action={canFix ? <Button size="sm" href={MAIL_SETTING_HREF}>메일 설정 열기</Button> : null}>
      <Typography component="span" sx={{ fontWeight: FONT_WEIGHT.semibold }}>메일 발송이 실패하고 있습니다.</Typography>
      {" " + (h.message || "") + checked}
    </Callout>
  );
}

/* 왜 못 보내는가 — 이 화면의 첫 답이다. 고칠 자리로 가는 단추(「메일 설정 열기」)가 상자의 동작 칸에 선다(D-501 —
   발송이 꺼져 있을 때 머리의 「시험 메일 보내기」는 성공할 수 없는 일이었고, 정작 할 일은 설정을 여는 것이었다).
   단추는 설정을 고칠 수 있는 역할에게만 선다 — 서버가 설정 쓰기를 같은 역할로 막는다. */
function ProblemsList({ problems, canFix }) {
  if (!problems || !problems.length) {
    return <Callout tone="success">메일 발송 설정이 완성돼 있습니다. 지금 메일이 나갑니다.</Callout>;
  }
  return (
    <Box id={PROBLEMS_ID}>
      <Callout tone="warn" action={canFix ? <Button size="sm" href={MAIL_SETTING_HREF}>메일 설정 열기</Button> : null}>
        <Typography component="span" sx={{ fontWeight: FONT_WEIGHT.semibold }}>메일이 나가지 않습니다.</Typography>
        {" 아래를 고쳐야 나가고, 그 전에는 시험 메일도 보낼 수 없습니다."}
        <Box component="ul" sx={{ m: 0, mt: 0.5, pl: 2.5 }}>
          {problems.map((p, i) => <li key={i}><Typography variant="body2">{p}</Typography></li>)}
        </Box>
      </Callout>
    </Box>
  );
}

/* 속성 줄에 보일 설정이 **하나라도** 있는가. 서버 주소 · 보내는 사람 · 로그인 계정이 모두 비어 있으면 여섯 칸이 전부
   「설정 안 됨 · 사용 안 함」이고(보안 연결은 기본값이다), 그 사실은 바로 위 목록이 이미 말한다 — 빈 칸 여섯은 그릇만
   있고 값이 없다(D-501). 하나라도 채워져 있으면 무엇이 채워졌는지가 고칠 때 필요한 정보라 줄이 선다. */
export function mailSettingsShown(server) {
  const s = server || {};
  return !!(s.host || s.from_address || s.username);
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

/* 「제목」은 그 메일의 제목 열이다(D-501) — 홀로 왼쪽에 서고, 남는 폭은 제목과 「원인」(산문, `grow`)이 나눈다.
   제목 열이 남는 폭을 먹기 시작하면 나머지 열은 자기 바닥 폭으로 선다. 그래서 타입이 없던 넷(4.5rem 바닥)에
   값이 한 줄로 서는 타입을 함께 준다 — 안 주면 「받는 사람」의 주소와 머리 이름이 72px 칸에서 잘리고,
   「발송 불가(설정 없음)」 표지가 옆 칸 위로 넘친다. 바닥 합이 1366 화면의 목록 폭보다 조금 넓어서
   그 폭에서는 「시도」가 숨는다(`hideNarrow`, 발이 그 사실을 말한다). */
const FAILURE_COLUMNS = [
  { key: "kind_label", label: "종류", type: "enum", minWidth: "8rem" },
  { key: "to_email", label: "받는 사람", type: "name", minWidth: "10rem" },
  { key: "subject", label: "제목", type: "title", minWidth: "12rem" },
  {
    key: "status_label", label: "상태", type: "status", minWidth: "10.5rem",
    /* 끝난 실패만 danger 다. 설정 없음과 다시 보내는 중은 아직 고치면 나갈 메일이라 warn 이다. */
    render: (r) => <Badge value={r.status_label} kind={r.status === "failed" ? "danger" : "warn"} />,
  },
  { key: "attempt_count", label: "시도", type: "count", hideNarrow: true, render: (r) => <NumberCell value={r.attempt_count} unit="회" /> },
  /* 산문이라 `text` 다. 타입이 없으면 말줄임이 안 걸려 실패 사유가 여러 줄로 접히고,
     가운데 정렬에서 접힌 줄은 양쪽 모서리가 다 들쭉날쭉해진다(`columnShouldTruncate`). */
  { key: "reason", label: "원인", type: "text", grow: true, render: (r) => <FailureReason row={r} /> },
  { key: "created_at", label: "발생", type: "datetime", render: (r) => <DateCell value={r.created_at} /> },
];

/* 시험 메일의 결과를 기다리는 방법 (계획 3.3).
 *
 * `POST /test` 는 메일을 **큐에 넣고** 돌아온다(`queued`). 예전 화면은 그 응답의 상태가 `sent` 가 아니면 실패로
 * 읽어서, 워커가 곧 보낼 시험 메일도 「보내지 못했습니다」였고 성공 토스트는 닿을 수 없는 코드였다. 이제 한 통의
 * 상세(`GET /deliveries/{id}`)를 끝난 상태가 될 때까지 읽는다. 90초 안에 안 끝나면 워커가 멈춘 것이라 그렇게 말한다. */
const TEST_DONE = ["sent", "failed", "unconfigured", "cancelled", "superseded"];
const TEST_POLL_MS = 1500;
const TEST_WAIT_LIMIT_MS = 90000;

/* 연결 확인 — 잡을 넣고 끝날 때까지 결과를 읽는다(`GET /verify/{job_id}`). 메일은 보내지 않는다. */
function useMailVerify({ onDone }) {
  const [jobId, setJobId] = React.useState(null);
  const [result, setResult] = React.useState(null);
  const start = useMutation({
    mutationFn: () => api("/api/admin/mail/verify", { method: "POST" }),
    onSuccess: (data) => { setResult(null); setJobId(data && data.job_id); },
  });
  const poll = useQuery({
    queryKey: ["mail-verify", jobId],
    queryFn: () => api(`/api/admin/mail/verify/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (q) => (q.state.data && q.state.data.pending === false ? false : TEST_POLL_MS),
  });
  React.useEffect(() => {
    const d = poll.data;
    if (d && d.pending === false && d.result) {
      setResult(d.result);
      setJobId(null);
      if (onDone) onDone(d.result);
    }
  }, [poll.data, onDone]);
  return { start, result, waiting: start.isPending || !!jobId };
}

function useTestMailWatch() {
  const [delivery, setDelivery] = React.useState(null);
  const [timedOut, setTimedOut] = React.useState(false);
  const id = delivery && !TEST_DONE.includes(delivery.status) ? delivery.id : null;
  const poll = useQuery({
    queryKey: ["mail-delivery", id],
    queryFn: () => api(`/api/admin/mail/deliveries/${id}`),
    enabled: !!id && !timedOut,
    refetchInterval: TEST_POLL_MS,
  });
  React.useEffect(() => {
    const next = poll.data && poll.data.delivery;
    if (next && next.id === id && TEST_DONE.includes(next.status)) setDelivery(next);
  }, [poll.data, id]);
  React.useEffect(() => {
    if (!id) return undefined;
    const timer = setTimeout(() => setTimedOut(true), TEST_WAIT_LIMIT_MS);
    return () => clearTimeout(timer);
  }, [id]);
  const start = React.useCallback((row) => { setTimedOut(false); setDelivery(row || null); }, []);
  return { delivery, waiting: !!id && !timedOut, timedOut: !!id && timedOut, start };
}

export function MailStatus() {
  return (
    <TabShell
      area="운영" title="메일 발송" idPrefix="mail"
      tabs={[
        { key: "status", label: "상태", help: HELP, render: () => <MailStatusPanel /> },
        { key: "deliveries", label: "발송 기록", help: MAIL_DELIVERIES.help, render: () => <DataScreen config={MAIL_DELIVERIES} embedded /> },
      ]}
    />
  );
}

function MailStatusPanel() {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const auth = useAuth();
  const role = (auth.data && auth.data.role) || "";
  const canWrite = CONSOLE_WRITE_ROLES.includes(role);

  const query = useQuery({
    queryKey: ["mail-status"],
    queryFn: () => api("/api/admin/mail/status"),
  });

  const watch = useTestMailWatch();
  const test = useMutation({
    mutationFn: () => api("/api/admin/mail/test", { method: "POST" }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["mail-status"] });
      watch.start(data && data.delivery);
    },
  });
  const outcome = watch.delivery && TEST_DONE.includes(watch.delivery.status) ? watch.delivery : null;
  const announced = React.useRef(null);
  React.useEffect(() => {
    if (!outcome || announced.current === outcome.id) return;
    announced.current = outcome.id;
    qc.invalidateQueries({ queryKey: ["mail-status"] });
    if (outcome.status === "sent") toast("시험 메일을 보냈습니다. 받은 편지함을 확인하세요.", "success");
  }, [outcome, qc, toast]);
  /* 시험 발송의 결과 중 남아야 하는 것 — 요청 실패, 「못 보냈다」, 워커가 응답하지 않음. 다시 보내면 걷힌다.
     못 보낸 까닭은 서버가 고른 한 문장(`error_summary`)이다. 원문은 아래 `최근 실패` 행의 기술 정보에 있다. */
  const testNotice = failureText([test, "요청을 보내지 못했습니다. 잠시 후 다시 시도해 주세요."])
    || (outcome && outcome.status !== "sent"
      ? ["시험 메일을 보내지 못했습니다.", outcome.error_summary || "아래 최근 실패에서 원인을 확인하세요."].join(" ")
      : null)
    || (watch.timedOut ? "워커가 응답하지 않아 시험 메일이 아직 나가지 않았습니다. 워커 서비스가 실행 중인지 확인하세요." : null);

  const verify = useMailVerify({
    onDone: React.useCallback((r) => {
      qc.invalidateQueries({ queryKey: ["mail-status"] });
      if (r && r.ok) toast("메일 서버 연결을 확인했습니다.", "success");
    }, [qc, toast]),
  });
  const verifyNotice = failureText([verify.start, "연결 확인을 시작하지 못했습니다."])
    || (verify.result && !verify.result.ok ? "연결 확인에 실패했습니다. " + (verify.result.message || "") : null);
  const sendBacklog = useMutation({
    mutationFn: () => api("/api/admin/mail/resend-unconfigured", { method: "POST" }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["mail-status"] });
      toast(`쌓여 있던 메일 ${(res && res.queued) || 0}건을 보냈습니다.`, "success");
    },
  });

  if (query.isLoading) return <Skeleton lines={6} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={query.refetch} />;

  const data = query.data || {};
  const mail = data.mail || {};
  const health = data.health || null;
  const backlog = data.pending_unconfigured_count || 0;
  const server = mail.server || {};
  const counts = data.counts || {};
  const failures = data.recent_failures || [];
  /* 설정 문제가 남아 있으면 시험 발송은 성공할 수 없다 — 서버는 그 요청을 「발송 못 함」 한 줄로 남기고 끝낸다
     (`app/mail/service.py::queue_mail`). 단추는 숨기지 않고 꺼 두며, 이유는 바로 아래 목록이 말한다(`aria-describedby`). */
  const blocked = !!(mail.problems && mail.problems.length);
  const skipped = (counts.cancelled || 0) + (counts.superseded || 0);
  const total = (counts.failed || 0) + (counts.retrying || 0) + (counts.queued || 0) + (counts.sent || 0)
    + (counts.unconfigured || 0) + skipped;

  async function sendTest() {
    if (!(await confirm(
      "내 계정(" + ((auth.data && auth.data.email) || "") + ")으로 시험 메일을 보낼까요?",
      { confirmLabel: "시험 발송" }
    ))) return;
    await test.mutateAsync();
  }

  /* 머리 동작 둘 — 보조 「연결 확인」(메일을 보내지 않는다)과 주 동작 「시험 메일 보내기」. 설정 문제가 남아 있으면 둘 다
     성공할 수 없어 꺼 두고, 이유는 바로 아래 목록이 말한다(`aria-describedby`). */
  const headActions = canWrite ? (
    <>
      <Button loading={verify.waiting} disabled={blocked} onClick={() => verify.start.mutate()}
        aria-describedby={blocked ? PROBLEMS_ID : undefined}>
        연결 확인
      </Button>
      <Button variant="primary" loading={test.isPending || watch.waiting} disabled={blocked} onClick={sendTest}
        aria-describedby={blocked ? PROBLEMS_ID : undefined}>
        시험 메일 보내기
      </Button>
    </>
  ) : null;

  return (
    <Box>
      {headActions ? <HeaderActions fallback={headActions}>{headActions}</HeaderActions> : null}

      {testNotice ? <Callout tone="danger" compact sx={{ mb: 2 }}>{testNotice}</Callout> : null}
      {verifyNotice ? <Callout tone="danger" compact sx={{ mb: 2 }}>{verifyNotice}</Callout> : null}
      <HealthStatus health={health} problems={mail.problems} canFix={canWrite} />
      {/* 설정 전에 쌓인 초대 메일(최근 7일) — 연결이 확인된 뒤에만 보낼 수 있게 묻는다. 오래된 메일을 예고 없이
          뿌리지 않는다(계획 3.4). 보내기 직전에 아직 의미가 있는지 서버가 한 번 더 본다. */}
      {canWrite && backlog > 0 && health && health.state === "ok" ? (
        <Callout
          tone="info" sx={{ mt: 2 }}
          action={<Button size="sm" loading={sendBacklog.isPending} onClick={() => sendBacklog.mutate()}>보내기</Button>}
        >
          설정 전에 쌓인 메일 {backlog}건이 있습니다. 지금 보내도 되는지 확인한 뒤 보내세요.
        </Callout>
      ) : null}

      {mailSettingsShown(server) ? <MetaBar
        ariaLabel="메일 서버 설정"
        sx={{ mt: 2 }}
        items={[
          { key: "enabled", label: "발송", type: "status", value: <Badge value={server.enabled ? "사용" : "사용 안 함"} kind={server.enabled ? "ok" : "warn"} /> },
          { key: "host", label: "메일 서버", type: "identifier", value: server.host ? server.host + ":" + (server.port == null ? "?" : server.port) : "설정 안 됨" },
          { key: "security", label: "보안 연결", type: "enum", value: SMTP_SECURITY_LABELS[server.security] || server.security || "설정 안 됨" },
          /* 인증서 확인을 끈 설치는 경고로 선다(계획 3.3) — 끈 사실이 화면 어디에도 없으면 아무도 다시 켜지 않는다. */
          server.security && server.security !== "none" ? {
            key: "tls", label: "인증서 확인", type: "status",
            value: <Badge value={server.tls_verify === false ? "확인 안 함" : "확인함"} kind={server.tls_verify === false ? "warn" : "ok"} />,
          } : null,
          {
            key: "from", label: "보내는 사람", type: "identifier",
            value: server.from_address
              ? (server.from_name ? server.from_name + " (" + server.from_address + ")" : server.from_address)
              : "설정 안 됨",
          },
          { key: "username", label: "로그인 계정", type: "identifier", value: server.username || "사용 안 함" },
          { key: "secret", label: "비밀번호", type: "status", value: passwordState(mail, server) },
        ]}
      /> : null}

      {/* 발송 현황은 네 상태의 합이 전체 메일인 구성이다 — 상태 요약 카드(계획 표 7). 한 통도 쌓인 적이 없으면(전체 0)
          카드는 서지 않는다(D-501 · `StatusKpi.jsx`) — 그 사실은 아래 「최근 실패」의 빈 상태가 말한다. */}
      <StatusSummaryCard
        ariaLabel="발송 현황"
        sx={{ mt: 2 }}
        total={total}
        items={[
          { key: "failed", label: "발송 실패", value: counts.failed || 0, kind: "danger" },
          { key: "retrying", label: "다시 보내는 중", value: counts.retrying || 0, kind: "warn" },
          { key: "queued", label: "발송 대기", value: counts.queued || 0, kind: "info" },
          { key: "sent", label: "발송됨", value: counts.sent || 0, kind: "ok" },
          { key: "blocked", label: "발송 못 함", value: counts.unconfigured || 0, kind: "warn" },
          { key: "skipped", label: "보내지 않음", value: skipped, kind: "primary" },
        ]}
        /* MAIL-03: 이 건수는 설정을 나중에 고쳐도 저절로 줄지 않는다(queue_mail 이 설정 문제를 만나면
           재시도 잡 자체를 안 만든다). 그 사실을 별도 상자가 아니라 그 숫자의 정의로 둔다 — 어느 숫자를
           한정하는지 다시 찾을 필요가 없다. */
        notes={counts.unconfigured ? [{
          key: "blocked", label: "발송 못 함",
          text: "설정을 고쳐도 저절로 다시 보내지 않습니다. 연결 확인이 정상이면 최근 7일 안의 초대는 위에서 보낼 수 있습니다.",
        }] : null}
      />

      {/* 구획 제목 + 목록 판 — 다른 목록 화면과 같은 배치. 0건은 표 안의 평문 한 줄이 아니라
          빈 상태다(성공 그림) — 실패가 없다는 것은 이 화면의 좋은 소식이다.
          한 통도 쌓인 적이 없으면 「실패가 없다」는 좋은 소식이 아니라 아직 아무것도 안 보냈다는 뜻이다 — 위 발송 현황
          카드가 서지 않는 그 상태를 여기서 그대로 말한다. */}
      <Section titleAs="h2" title="최근 실패" sx={{ mt: 3, mb: 0 }}>
        {failures.length ? (
          <DataTable placement="surface" columns={FAILURE_COLUMNS} rows={failures} rowKey={(r) => r.id} />
        ) : total === 0 ? (
          <EmptyState title="아직 보낸 메일이 없습니다" help="메일이 나가기 시작하면 그 결과가 여기에 쌓입니다." />
        ) : (
          <EmptyState art="success" title="최근 실패한 메일이 없습니다" />
        )}
      </Section>

      <NotificationMailSection info={data.notification_mail} canWrite={canWrite} />
    </Box>
  );
}

/* 오래된 메일의 기준으로 고를 수 있는 날 수. 지금 값이 이 안에 없으면(설정 API 로 바꾼 값) 그 값도 함께 보인다. */
const AGE_CHOICES = [1, 3, 7, 14, 30];

/* 메일로 보내는 알림(계획 3.4) — 사용자가 메일로 받을 수 있는 알림의 허용 목록과 오래된 메일의 기준.
 *
 * 목록은 **서버가 준다**(`notification_mail.catalog` — 메일로 보낼 수 있는 유형 전부). 저장은 설정 API 하나로 하고
 * (`mail_notification_types`, `mail_notification_max_age_days`), 그 두 값은 설정 표에서 숨긴다 — 같은 값을 두 화면이
 * 서로 다른 방식으로 다루지 않게(`settingsRegistry.js::MAIL_SCREEN_KEYS`). */
function NotificationMailSection({ info, canWrite }) {
  const qc = useQueryClient();
  const toast = useToast();
  const save = useMutation({
    mutationFn: ({ key, value }) => api("/api/admin/settings/" + key, { method: "PUT", body: { value } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["mail-status"] });
      toast("알림 메일 설정을 저장했습니다.", "success");
    },
    onError: (e) => toast(e.message, "error"),
  });
  if (!info) return null;
  const catalog = info.catalog || [];
  const allowed = new Set(info.allowed || []);
  const toggle = (key) => {
    const next = new Set(allowed);
    if (next.has(key)) next.delete(key); else next.add(key);
    save.mutate({ key: "mail_notification_types", value: catalog.map((row) => row.key).filter((k) => next.has(k)) });
  };
  const days = info.max_age_days;
  const ages = AGE_CHOICES.includes(days) ? AGE_CHOICES : [...AGE_CHOICES, days].sort((a, b) => a - b);
  return (
    <Section
      titleAs="h2" title="메일로 보내는 알림" sx={{ mt: 3, mb: 0 }}
      help="여기서 허용한 알림만 사용자가 메일로 받을 수 있습니다. 사용자는 내 프로필에서 메일 알림을 켜고 받을 알림을 고릅니다."
    >
      <Card>
        <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, columnWidth: "20rem", columnGap: 3 }}>
          {catalog.map((row) => (
            <Box component="li" key={row.key} sx={{ breakInside: "avoid" }}>
              <SettingRow
                compact label={row.label} description={row.help}
                action={(
                  <Switch
                    checked={allowed.has(row.key)}
                    disabled={!canWrite || save.isPending}
                    onChange={() => toggle(row.key)}
                    slotProps={{ input: { "aria-label": `${row.label} 메일 허용` } }}
                  />
                )}
              />
            </Box>
          ))}
        </Box>
        <SettingRow
          compact label="오래된 메일"
          description="메일 서버가 멈춘 동안 쌓인 메일은 이 기간이 지나면 보내지 않습니다."
          action={canWrite ? (
            <Segmented
              ariaLabel="오래된 메일의 기준"
              value={String(days)}
              onChange={(v) => save.mutate({ key: "mail_notification_max_age_days", value: Number(v) })}
              options={ages.map((d) => ({ value: String(d), label: d + "일" }))}
            />
          ) : <Typography component="span">{days}일</Typography>}
        />
      </Card>
    </Section>
  );
}

export default MailStatus;
