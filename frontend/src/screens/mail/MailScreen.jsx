import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import { api } from "../../lib/api.js";
import { failureText } from "../../lib/failure.js";
import {
  Button, Callout, ErrorState, Field, FlowStack, MetaBar, Modal, ModalBody, ModalFooter, Skeleton, useToast,
} from "../../ui/kit.jsx";
import { TabShell } from "../../ui/TabShell.jsx";
import { useAuth } from "../../app/auth.jsx";
import { DataScreen } from "../DataScreen.jsx";
import { MAIL_DELIVERIES } from "./mailDeliveries.js";
import { MailSettingsTab } from "./MailSettingsTab.jsx";
import { NotificationMailTab } from "./NotificationMailTab.jsx";

/* 메일 (계획 M1 · M2 · M3, D-546 · D-548 · D-549 · D-554 · D-555) — 「운영 › 메일」 한 화면, 탭 셋: 설정 · 발송 기록 · 알림 메일.
 *
 * 머리 동작 둘(운영 권한이 있을 때): 「연결 확인」(메일을 보내지 않는다 - 봉투 시험까지)과 「시험 메일 보내기」. 주 동작(보라 채움)은
 * 상태가 정한다: 정상이면 시험 메일, 정상이 아니면 연결 확인. 저장하지 않은 수정 내용이 있으면 둘 다 꺼지고 까닭은 도움말 한 줄이다.
 * 연결 확인과 시험 메일의 기다림은 60초 상한이다 - 넘으면 「확인이 시간 안에 끝나지 않았습니다」라고 말하고 묻기를 멈춘다.
 *
 * 낱말은 확인한 단계까지만이다(D-555): 시험 메일이 끝나면 「메일 서버가 시험 메일을 접수했습니다」이지 「도착했습니다」가 아니다.
 */

export const MAIL_STATUS_KEY = ["mail-status"];
const POLL_MS = 1500;
const WAIT_LIMIT_MS = 60_000;
const TEST_DONE = ["sent", "failed", "unconfigured", "cancelled", "superseded"];
const DIRTY_HINT_ID = "mail-dirty-hint";

/* 연결 확인 잡 하나를 끝날 때까지 지켜본다(60초 상한). 저장 직후 서버가 연 확인도 같은 길로 지켜본다. */
function useVerifyWatch({ onDone }) {
  const [jobId, setJobId] = React.useState(null);
  const [timedOut, setTimedOut] = React.useState(false);
  const poll = useQuery({
    queryKey: ["mail-verify", jobId],
    queryFn: () => api(`/api/admin/mail/verify/${jobId}`),
    enabled: !!jobId && !timedOut,
    refetchInterval: (q) => (q.state.data && q.state.data.pending === false ? false : POLL_MS),
  });
  React.useEffect(() => {
    const d = poll.data;
    if (jobId && d && d.job_id === jobId && d.pending === false) {
      setJobId(null);
      if (onDone) onDone(d.result || null);
    }
  }, [poll.data, jobId, onDone]);
  React.useEffect(() => {
    if (!jobId) return undefined;
    const timer = setTimeout(() => setTimedOut(true), WAIT_LIMIT_MS);
    return () => clearTimeout(timer);
  }, [jobId]);
  const watch = React.useCallback((id) => { setTimedOut(false); setJobId(id || null); }, []);
  return { watch, waiting: !!jobId && !timedOut, timedOut: !!jobId && timedOut };
}

/* 시험 메일 한 통을 끝난 상태가 될 때까지 지켜본다(60초 상한). */
function useTestWatch({ onDone }) {
  const [delivery, setDelivery] = React.useState(null);
  const [timedOut, setTimedOut] = React.useState(false);
  const id = delivery && !TEST_DONE.includes(delivery.status) ? delivery.id : null;
  const poll = useQuery({
    queryKey: ["mail-delivery", id],
    queryFn: () => api(`/api/admin/mail/deliveries/${id}`),
    enabled: !!id && !timedOut,
    refetchInterval: POLL_MS,
  });
  React.useEffect(() => {
    const next = poll.data && poll.data.delivery;
    if (next && next.id === id && TEST_DONE.includes(next.status)) {
      setDelivery(next);
      if (onDone) onDone(next);
    }
  }, [poll.data, id, onDone]);
  React.useEffect(() => {
    if (!id) return undefined;
    const timer = setTimeout(() => setTimedOut(true), WAIT_LIMIT_MS);
    return () => clearTimeout(timer);
  }, [id]);
  const start = React.useCallback((row) => {
    setTimedOut(false);
    setDelivery(row || null);
    if (row && TEST_DONE.includes(row.status) && onDone) onDone(row);
  }, [onDone]);
  return { start, waiting: !!id && !timedOut, timedOut: !!id && timedOut };
}

function TestMailDialog({ open, onClose, canChoose, myEmail, onSent }) {
  const [to, setTo] = React.useState(myEmail || "");
  React.useEffect(() => { if (open) setTo(myEmail || ""); }, [open, myEmail]);
  const send = useMutation({
    mutationFn: () => api("/api/admin/mail/test", { method: "POST", body: canChoose && to.trim() ? { to: to.trim() } : {} }),
    onSuccess: (res) => { onSent(res); onClose(); },
  });
  const error = failureText([send, "시험 메일을 보내지 못했습니다."]);
  return (
    <Modal open={open} onClose={onClose} title="시험 메일 보내기" size="sm"
      footer={(
        <ModalFooter onCancel={onClose} onSubmit={() => send.mutate()} submitLabel="보내기" busy={send.isPending}
          disabled={!to.trim()} />
      )}>
      <ModalBody>
        <Field label="받는 주소" htmlFor="mail-test-to"
          help={canChoose
            ? "지금 설정으로 시험 메일 한 통을 보냅니다. 받은 편지함에서 직접 확인하세요."
            : "다른 주소로 보내려면 시스템 관리자 권한이 필요합니다."}>
          <TextField id="mail-test-to" size="small" fullWidth value={to} onChange={(e) => setTo(e.target.value)}
            InputProps={{ readOnly: !canChoose }} inputProps={{ spellCheck: false, autoComplete: "off" }} />
        </Field>
        {error ? <Callout tone="danger" compact>{error}</Callout> : null}
      </ModalBody>
    </Modal>
  );
}

function DeliveriesTab({ status }) {
  const c = status.counts || {};
  const items = [
    { key: "queued", label: "보낼 차례", value: c.queued || 0 },
    { key: "retrying", label: "다시 보낼 차례", value: c.retrying || 0 },
    { key: "sent", label: "서버가 접수함", value: c.sent || 0 },
    { key: "failed", label: "보내지 못함", value: c.failed || 0 },
    { key: "unconfigured", label: "설정이 끝나지 않음", value: c.unconfigured || 0 },
    { key: "skipped", label: "보내지 않음", value: (c.cancelled || 0) + (c.superseded || 0) },
  ];
  /* 그릇은 값이 있어야 선다(D-501) — 한 통도 없으면 0 여섯 칸 대신 목록의 빈 상태가 그 사실을 말한다. */
  const total = items.reduce((sum, item) => sum + item.value, 0);
  return (
    <FlowStack>
      {total ? <MetaBar ariaLabel="상태별 메일 수" items={items} /> : null}
      <DataScreen config={MAIL_DELIVERIES} embedded />
    </FlowStack>
  );
}

function MailBody({ tab, status, verify, setDirty, canOperate, backlog, onBacklog, sendingBacklog }) {
  if (tab === "deliveries") return <DeliveriesTab status={status} />;
  if (tab === "notifications") return <NotificationMailTab status={status} />;
  return (
    <FlowStack>
      {canOperate && backlog > 0 && status.health && status.health.state === "ok" ? (
        <Callout tone="info" action={<Button size="sm" loading={sendingBacklog} onClick={onBacklog}>보내기</Button>}>
          {`설정 전에 쌓인 메일 ${backlog}건이 있습니다. 지금 보내도 되는지 확인한 뒤 보내세요.`}
        </Callout>
      ) : null}
      <MailSettingsTab status={status} verify={verify} onDirtyChange={setDirty} />
    </FlowStack>
  );
}

export function MailScreen() {
  const qc = useQueryClient();
  const toast = useToast();
  const auth = useAuth();
  const me = auth.data || {};
  const query = useQuery({ queryKey: MAIL_STATUS_KEY, queryFn: () => api("/api/admin/mail/status") });
  const [dirty, setDirty] = React.useState(false);
  const [dialog, setDialog] = React.useState(false);
  const [notice, setNotice] = React.useState(null);

  const verify = useVerifyWatch({
    onDone: React.useCallback((result) => {
      qc.invalidateQueries({ queryKey: MAIL_STATUS_KEY });
      if (result && result.ok) toast("메일 서버 연결을 확인했습니다.", "success");
      else if (result) setNotice(`연결 확인에 실패했습니다. ${result.message || ""}`.trim());
    }, [qc, toast]),
  });
  const startVerify = useMutation({
    mutationFn: () => api("/api/admin/mail/verify", { method: "POST" }),
    onSuccess: (res) => { setNotice(null); verify.watch(res && res.job_id); },
  });
  const sentence = React.useRef(null);
  const test = useTestWatch({
    onDone: React.useCallback((row) => {
      qc.invalidateQueries({ queryKey: MAIL_STATUS_KEY });
      if (row.status === "sent") toast(sentence.current || "메일 서버가 시험 메일을 접수했습니다.", "success");
      else setNotice(["시험 메일을 보내지 못했습니다.", row.error_summary || row.skip_reason_label || ""].join(" ").trim());
    }, [qc, toast]),
  });
  const backlog = useMutation({
    mutationFn: () => api("/api/admin/mail/resend-unconfigured", { method: "POST" }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: MAIL_STATUS_KEY });
      toast(`쌓여 있던 메일 ${(res && res.queued) || 0}건을 다시 보낼 차례에 넣었습니다.`, "success");
    },
  });

  if (query.isLoading) return <Skeleton kind="page" lines={8} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={query.refetch} />;

  const status = query.data || {};
  const caps = status.capabilities || {};
  const state = (status.health || {}).state;
  const cannotSend = state === "disabled" || state === "unconfigured";
  const busy = verify.waiting || startVerify.isPending;
  const verifyPrimary = state !== "ok";
  const actions = caps.can_operate ? (
    <>
      <Button
        variant={verifyPrimary ? "primary" : undefined} loading={busy} disabled={dirty || cannotSend}
        aria-describedby={dirty ? DIRTY_HINT_ID : undefined} onClick={() => startVerify.mutate()}
      >
        연결 확인
      </Button>
      <Button
        variant={verifyPrimary ? undefined : "primary"} loading={test.waiting} disabled={dirty || cannotSend}
        aria-describedby={dirty ? DIRTY_HINT_ID : undefined} onClick={() => setDialog(true)}
      >
        시험 메일 보내기
      </Button>
      {dirty ? <Box id={DIRTY_HINT_ID} component="span" className="sr-only">저장한 뒤에 확인할 수 있습니다.</Box> : null}
    </>
  ) : null;
  const startError = failureText([startVerify, "연결 확인을 시작하지 못했습니다."]);
  const timedOut = test.timedOut ? "확인이 시간 안에 끝나지 않았습니다. 잠시 뒤 발송 기록에서 다시 확인하세요." : null;
  const verifyState = { ...verify, waiting: busy };
  const problem = startError || notice || timedOut;
  const body = (tab) => (
    <FlowStack>
      {problem ? <Callout tone="danger" compact>{problem}</Callout> : null}
      <MailBody
        tab={tab} status={status} verify={verifyState} setDirty={setDirty} canOperate={caps.can_operate}
        backlog={(status.backlog || {}).count || 0} onBacklog={() => backlog.mutate()} sendingBacklog={backlog.isPending}
      />
    </FlowStack>
  );

  return (
    <>
      <TabShell
        area="운영" title="메일" idPrefix="mail" actions={actions}
        help="메일 서버를 설정하고 실제로 나가는지 확인합니다. 발송 기록과 사람들이 받는 메일의 모양도 여기서 봅니다."
        tabs={[
          { key: "settings", label: "설정", render: () => body("settings") },
          { key: "deliveries", label: "발송 기록", help: MAIL_DELIVERIES.help, render: () => body("deliveries") },
          { key: "notifications", label: "알림 메일", render: () => body("notifications") },
        ]}
      />
      <TestMailDialog
        open={dialog} onClose={() => setDialog(false)} canChoose={Boolean(caps.can_configure)} myEmail={me.email || ""}
        onSent={(res) => { setNotice(null); sentence.current = res && res.sentence; test.start(res && res.delivery); }}
      />
    </>
  );
}

export default MailScreen;
