import React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { failureText } from "../../lib/failure.js";
import { Button, Callout, Card, DotLabel, Field, FieldRow, FormSection, useToast } from "../../ui/kit.jsx";
import { SettingRow } from "../../ui/adminKit.jsx";
import { FONT_SIZE, KO_WORD_BREAK } from "../../ui/theme.js";

/* 내 프로필 · 메일 알림 (계획 M4, D-550) — 「내가 어떤 메일을 어디에서 받는가」만 다룬다.
 *
 * 관리자의 메일 설정(어떻게 보내는가)과 완전히 나뉜다: 서버 주소 · 포트 · 보안 연결 · 발송 구성 요소 같은 말과 값이 이 카드에 없다.
 * 메일 발송이 지연되면 한 문장만 말하고, 관리자가 메일 발송을 쓰지 않는 설치에서는 스위치를 꺼 두고 까닭을 한 줄로 말한다.
 *
 * 받는 주소는 계정 이메일이 기본이다. 다른 주소는 그 주소로 보낸 6자리 코드를 넣어야 쓴다 - 확인이 끝나기 전에는 알림이 계정 주소로
 * 간다. 회사가 허용 도메인을 정했으면 그 도메인만 받는다. 스위치는 누르는 즉시 저장된다(RULES §3).
 */

export const PREFS_KEY = ["me-preferences"];
const ADDRESS_STATE = {
  account: { label: "계정 이메일", tone: "neutral" },
  pending: { label: "확인 중", tone: "info" },
  verified: { label: "확인됨", tone: "ok" },
  inactive: { label: "쓰지 않음", tone: "warn" },
};

function addressState(address) {
  if (address.pending) return "pending";
  if (address.custom && address.custom.active) return "verified";
  if (address.custom && !address.custom.active) return "inactive";
  return "account";
}

function useNow(enabled) {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    if (!enabled) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [enabled]);
  return now;
}

function AddressBlock({ address, mailOff }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = React.useState(false);
  const [email, setEmail] = React.useState("");
  const [code, setCode] = React.useState("");
  const pending = address.pending;
  const now = useNow(Boolean(pending));
  const resendAt = pending && pending.resend_after ? Date.parse(pending.resend_after) : 0;
  const waitSeconds = resendAt > now ? Math.ceil((resendAt - now) / 1000) : 0;
  const state = addressState(address);
  const meta = ADDRESS_STATE[state];
  const apply = (res) => { if (res && res.mail) qc.setQueryData(PREFS_KEY, (old) => (old ? { ...old, mail: res.mail } : old)); };

  const request = useMutation({
    mutationFn: (target) => api("/api/me/notify-email", { method: "POST", body: { email: target } }),
    onSuccess: (res) => { apply(res); setCode(""); toast("확인 코드를 보냈습니다. 받은 편지함을 확인하세요.", "success"); },
  });
  const verify = useMutation({
    mutationFn: () => api("/api/me/notify-email/verify", { method: "POST", body: { code: code.trim() } }),
    onSuccess: (res) => { apply(res); setOpen(false); setEmail(""); setCode(""); toast("알림 받을 주소를 확인했습니다.", "success"); },
  });
  const cancelPending = useMutation({
    mutationFn: () => api("/api/me/notify-email/pending", { method: "DELETE" }),
    onSuccess: (res) => { apply(res); setCode(""); },
  });
  const reset = useMutation({
    mutationFn: () => api("/api/me/notify-email", { method: "DELETE" }),
    onSuccess: (res) => { apply(res); setOpen(false); toast("계정 이메일로 받습니다.", "success"); },
  });
  const error = failureText([request, "확인 코드를 보내지 못했습니다."])
    || failureText([verify, "코드를 확인하지 못했습니다."])
    || failureText([cancelPending, "취소하지 못했습니다."])
    || failureText([reset, "계정 이메일로 되돌리지 못했습니다."]);
  const domains = address.allowed_domains || [];
  const shown = address.custom && address.custom.active ? address.custom.email : address.account_email;

  return (
    <Box sx={{ display: "grid", gap: 1.5, minWidth: 0 }} data-testid="mail-address">
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap", minWidth: 0 }}>
        <Typography component="span" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary" }}>받는 주소</Typography>
        <Typography component="span" sx={{ minWidth: 0, wordBreak: "break-all" }} data-testid="mail-address-value">{shown}</Typography>
        <DotLabel label={meta.label} tone={meta.tone} data-testid="mail-address-state" />
        <Box sx={{ ml: "auto", display: "flex", gap: 1 }}>
          {state === "verified" || state === "inactive" ? (
            <Button size="sm" loading={reset.isPending} onClick={() => reset.mutate()}>계정 이메일로 되돌리기</Button>
          ) : null}
          {!open && !pending ? (
            <Button size="sm" disabled={mailOff} onClick={() => setOpen(true)}>다른 주소로 받기</Button>
          ) : null}
        </Box>
      </Box>
      {state === "inactive" && address.custom.inactive_reason ? (
        <Callout tone="warn" compact>{address.custom.inactive_reason}</Callout>
      ) : null}
      {open && !pending ? (
        <FieldRow columns={["1fr"]}>
          <Field
            label="알림 받을 이메일" htmlFor="notify-email"
            help={domains.length ? `회사가 허용한 도메인(${domains.join(", ")})의 주소만 쓸 수 있습니다.` : "그 주소로 6자리 확인 코드를 보냅니다."}
            action={(
              <>
                <Button variant="primary" loading={request.isPending} disabled={!email.trim()} onClick={() => request.mutate(email.trim())}>
                  확인 코드 보내기
                </Button>
                <Button onClick={() => { setOpen(false); setEmail(""); }}>취소</Button>
              </>
            )}
          >
            <TextField id="notify-email" size="small" fullWidth value={email} onChange={(e) => setEmail(e.target.value)}
              inputProps={{ spellCheck: false, autoComplete: "email" }} />
          </Field>
        </FieldRow>
      ) : null}
      {pending ? (
        /* 칸 폭은 동작 단추까지 담는 칸 전체다 — 예전에는 칸 하나를 12rem 으로 묶어 단추 셋(확인 · 코드 다시 받기 · 취소)이 그
           폭을 다 가져가고 입력 칸이 10px 로 눌렸다(P17V 상태 캡처). 입력은 남는 폭을 받고, 칸 전체는 24rem 을 넘지 않는다. */
        <FieldRow columns={["1fr"]}>
          <Field
            label="확인 코드" htmlFor="notify-code" width="lg"
            /* 주소 뒤에 조사를 바로 붙이지 않는다 — 「example.com로」처럼 영문 끝의 받침을 코드가 모른다. 「주소로」가 받는다. */
            help={`${pending.email} 주소로 보낸 6자리 코드를 입력하세요. 코드는 15분 동안 쓸 수 있습니다.`}
            action={(
              <>
                <Button variant="primary" loading={verify.isPending} disabled={!/^\d{6}$/.test(code.trim())} onClick={() => verify.mutate()}>
                  확인
                </Button>
                <Button loading={request.isPending} disabled={waitSeconds > 0} onClick={() => request.mutate(pending.email)}>
                  {waitSeconds > 0 ? `코드 다시 받기(${waitSeconds}초 뒤)` : "코드 다시 받기"}
                </Button>
                <Button loading={cancelPending.isPending} onClick={() => cancelPending.mutate()}>취소</Button>
              </>
            )}
          >
            <TextField id="notify-code" size="small" fullWidth value={code} onChange={(e) => setCode(e.target.value)}
              inputProps={{ inputMode: "numeric", maxLength: 6, autoComplete: "one-time-code" }} />
          </Field>
        </FieldRow>
      ) : null}
      {error ? <Callout tone="danger" compact>{error}</Callout> : null}
    </Box>
  );
}

export function MailNotificationCard({ mail, save }) {
  if (!mail) return null;
  const catalog = mail.catalog || [];
  const chosen = new Set(mail.types || []);
  const delivery = mail.delivery || { state: "ok" };
  const off = delivery.state === "off";
  const toggleType = (key) => {
    const next = new Set(chosen);
    if (next.has(key)) next.delete(key); else next.add(key);
    save({ mail_types: catalog.map((row) => row.key).filter((k) => next.has(k)) });
  };
  return (
    <Card stack data-testid="mail-notification-card">
      <FormSection titleAs="h2" title="메일 알림">
        {delivery.state === "delayed" && delivery.message ? <Callout tone="warn" compact>{delivery.message}</Callout> : null}
        <Box sx={{ "& > .k-settingrow:first-of-type": { borderTop: 0, pt: 0 } }}>
          <SettingRow
            compact label="메일 알림 받기" controlId="pref-mail-enabled"
            description={off ? (delivery.message || "관리자가 메일 발송을 켜면 메일 알림을 받을 수 있습니다.") : "아래에서 고른 알림을 메일로도 받습니다."}
            action={(
              <Switch
                id="pref-mail-enabled" checked={!!mail.enabled} disabled={off && !mail.enabled}
                onChange={() => save({ mail_enabled: !mail.enabled })}
                slotProps={{ input: { "aria-label": "메일 알림 받기" } }}
              />
            )}
          />
        </Box>
        {mail.address ? <AddressBlock address={mail.address} mailOff={off} /> : null}
      </FormSection>
      <FormSection titleAs="h2" title="받을 알림">
        {catalog.length ? (
          <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, "& > li:first-of-type .k-settingrow": { borderTop: 0, pt: 0 } }}>
            {catalog.map((row) => (
              <Box component="li" key={row.key}>
                <SettingRow
                  compact label={row.label} description={row.help} controlId={`pref-mail-${row.key}`}
                  action={(
                    <Switch
                      id={`pref-mail-${row.key}`} checked={chosen.has(row.key)} disabled={!mail.enabled || off}
                      onChange={() => toggleType(row.key)}
                      slotProps={{ input: { "aria-label": `${row.label} 메일로 받기` } }}
                    />
                  )}
                />
              </Box>
            ))}
          </Box>
        ) : (
          <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
            관리자가 메일로 보낼 알림을 아직 정하지 않았습니다.
          </Typography>
        )}
      </FormSection>
    </Card>
  );
}

export default MailNotificationCard;
