import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { failureText } from "../../lib/failure.js";
import { fmtDateTime } from "../../lib/format.js";
import {
  Button, Callout, DotLabel, Field, FieldRow, FormSection, HeadRow, TechDetail, useConfirm, useToast,
} from "../../ui/kit.jsx";
import { SettingRow } from "../../ui/adminKit.jsx";
import { ChoiceCards } from "../../ui/ChoiceCards.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, RADIUS } from "../../ui/theme.js";

/* 메일 · 설정 탭의 「ClovirAssist 로컬 릴레이」 구획 (계획 M7, D-551).
 *
 * 점진 공개다: 먼저 구성 요소의 상태 한 줄과 켜고 끄는 단추, 그다음 전달 방식(상위 SMTP 이용 · 인터넷으로 직접 전달(고급)), 고른 방식의
 * 칸, 마지막으로 바깥으로 보내기 준비 점검과 복사할 DNS 레코드다. 「인터넷으로 직접 전달」을 고를 때만 서버 이름 · 공인 IP · DKIM ·
 * 받는 도메인별 전달 서버가 보인다. 일반 화면에는 구성 요소의 제품 이름을 쓰지 않는다 - 꾸러미 · 서비스 · 듣는 소켓은 「기술 정보」
 * 안에만 있다.
 *
 * 칸 값은 메일 설정 폼의 한 번의 「저장」에 실린다(비밀번호 포함). 활성화 · 다시 적용 · 비활성화 · 키 추가 · 점검은 저장한 설정으로만
 * 한다 - 저장하지 않은 수정 내용이 있으면 그 단추들은 닫혀 있고 까닭을 한 줄로 말한다.
 */

export const MAIL_RELAY_KEY = ["mail-relay"];
const POLL_MS = 2000;
const CHECK_LIMIT_MS = 90_000;
const SECURITY = [["starttls", "STARTTLS"], ["ssl", "SSL"], ["none", "사용 안 함"]];
const PORT_PRESETS = { starttls: 587, ssl: 465, none: 25 };
const COMPONENT_TONE = { ready: "neutral", running: "ok", stopped: "danger", not_installed: "warn", foreign: "warn", unavailable: "neutral" };
const CHECK_STATE = {
  ok: { label: "정상", tone: "ok" },
  warn: { label: "주의", tone: "warn" },
  fail: { label: "실패", tone: "danger" },
  unknown: { label: "모름", tone: "neutral" },
};

function Line({ children, muted = true }) {
  return (
    <Typography variant="body2" color={muted ? "text.secondary" : "text.primary"} sx={KO_WORD_BREAK}>{children}</Typography>
  );
}

function TechRows({ data }) {
  if (!data) return null;
  const rows = [
    ["꾸러미", data.packages ? Object.entries(data.packages).map(([k, v]) => `${k} ${v || "없음"}`).join(", ") : null],
    ["다른 메일 발송 프로그램", (data.other_mta || []).join(", ") || null],
    ["설정 파일", data.config],
    ["서비스", data.services ? Object.entries(data.services).map(([k, v]) => `${k}=${v}`).join(", ") : null],
    ["듣는 소켓", (data.listeners || []).join(", ") || (data.listeners ? "없음" : null)],
    ["큐", data.queue_count != null ? `${data.queue_count}통` : null],
    ["도우미", data.helper],
  ].filter(([, v]) => v);
  if (!rows.length) return null;
  return (
    <TechDetail>
      <Box component="dl" sx={{ m: 0, display: "grid", gridTemplateColumns: "10rem minmax(0,1fr)", gap: 0.5 }}>
        {rows.map(([k, v]) => (
          <React.Fragment key={k}>
            <Typography component="dt" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary" }}>{k}</Typography>
            <Typography component="dd" sx={{ m: 0, fontSize: FONT_SIZE.caption, wordBreak: "break-all" }}>{v}</Typography>
          </React.Fragment>
        ))}
      </Box>
    </TechDetail>
  );
}

/* 구성 요소 상태 한 줄과 활성화 · 다시 적용 · 비활성화(동사표 PA-RC-0002: 켜기 → 활성화, 끄기 → 비활성화). */
function RelayComponent({ relay, savedLocal, dirty, verify }) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const component = relay.component || {};
  const after = (res) => {
    if (res && res.relay) qc.setQueryData(MAIL_RELAY_KEY, res.relay);
    qc.invalidateQueries({ queryKey: ["mail-status"] });
  };
  const apply = useMutation({
    mutationFn: () => api("/api/admin/mail/relay/apply", { method: "POST", body: {} }),
    onSuccess: (res) => {
      after(res);
      if (res.result && res.result.ok) {
        toast(res.result.message || "로컬 릴레이를 켰습니다.", "success");
        if (res.verify && res.verify.job_id && verify) verify.watch(res.verify.job_id);
      }
    },
  });
  const disable = useMutation({
    mutationFn: () => api("/api/admin/mail/relay/disable", { method: "POST", body: {} }),
    onSuccess: (res) => { after(res); if (res.result && res.result.ok) toast("로컬 릴레이를 비활성화했습니다.", "success"); },
  });
  const refused = apply.data && apply.data.result && !apply.data.result.ok ? apply.data.result : null;
  const error = failureText([apply, "로컬 릴레이를 켜지 못했습니다."]) || failureText([disable, "로컬 릴레이를 끄지 못했습니다."]);
  const blockedWhy = !savedLocal ? "보내는 방법을 로컬 릴레이로 저장한 뒤에 활성화할 수 있습니다."
    : dirty ? "저장하지 않은 수정 내용이 있습니다. 저장한 뒤에 활성화할 수 있습니다." : null;
  const canStart = ["ready", "stopped"].includes(component.state);
  async function turnOff() {
    const ok = await confirm(
      "로컬 릴레이를 비활성화하면 큐에 남은 메일은 다시 활성화할 때까지 나가지 않습니다. 비활성화할까요?",
      { danger: true, title: "로컬 릴레이 비활성화", confirmLabel: "비활성화" },
    );
    if (ok) disable.mutate();
  }
  const actions = (
    <Box sx={{ display: "flex", gap: 1 }}>
      {canStart ? (
        <Button variant="primary" loading={apply.isPending} disabled={Boolean(blockedWhy)} aria-describedby={blockedWhy ? "relay-blocked" : undefined}
          onClick={() => apply.mutate()}>로컬 릴레이 활성화</Button>
      ) : null}
      {component.state === "running" ? (
        <>
          <Button loading={apply.isPending} disabled={Boolean(blockedWhy)} onClick={() => apply.mutate()}>다시 적용</Button>
          <Button variant="danger" loading={disable.isPending} onClick={turnOff}>비활성화</Button>
        </>
      ) : null}
    </Box>
  );
  return (
    <Box sx={{ display: "grid", gap: 1.25, minWidth: 0 }} data-testid="relay-component" data-relay-state={component.state}>
      <HeadRow action={actions}>
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.25, flexWrap: "wrap", minWidth: 0 }}>
          <DotLabel label={component.label || "확인할 수 없음"} tone={COMPONENT_TONE[component.state] || "neutral"} strong />
          <Line>{component.message}</Line>
        </Box>
      </HeadRow>
      {component.help ? <Line>{component.help}</Line> : null}
      {blockedWhy && canStart ? <Typography id="relay-blocked" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary" }}>{blockedWhy}</Typography> : null}
      {component.stale && !dirty ? (
        <Callout tone="info" compact>저장한 설정이 아직 로컬 릴레이에 적용되지 않았습니다. 다시 적용하세요.</Callout>
      ) : null}
      {refused ? <Callout tone="danger" compact>{refused.message}</Callout> : null}
      {error ? <Callout tone="danger" compact>{error}</Callout> : null}
      <TechRows data={component.technical} />
    </Box>
  );
}

function OverrideRows({ rows, onChange }) {
  const list = rows || [];
  const update = (i, patch) => onChange(list.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  return (
    <Box sx={{ display: "grid", gap: 1.5 }} data-testid="relay-overrides">
      {list.map((r, i) => (
        // eslint-disable-next-line react/no-array-index-key
        <FieldRow key={i} columns={["1fr", "1fr"]}>
          <Field label="받는 도메인" htmlFor={`relay-ov-domain-${i}`}>
            <TextField id={`relay-ov-domain-${i}`} size="small" fullWidth value={r.domain} placeholder="example.com"
              onChange={(e) => update(i, { domain: e.target.value })} inputProps={{ spellCheck: false }} />
          </Field>
          <Field label="전달 서버" htmlFor={`relay-ov-host-${i}`}
            action={(
              <Button onClick={() => onChange(list.filter((_, k) => k !== i))} aria-label={`${r.domain || "빈"} 줄 삭제`}>삭제</Button>
            )}>
            <TextField id={`relay-ov-host-${i}`} size="small" fullWidth value={r.host} placeholder="mx.example.com"
              onChange={(e) => update(i, { host: e.target.value })} inputProps={{ spellCheck: false }} />
          </Field>
        </FieldRow>
      ))}
      <Box>
        <Button disabled={list.length >= 20} onClick={() => onChange([...list, { domain: "", host: "" }])}>줄 추가</Button>
      </Box>
    </Box>
  );
}

/* 고른 전달 방식의 칸 — 메일 설정 폼의 값(`values.relay`)을 고친다. */
export function RelayFields({ values, setRelay, relayPassword, setRelayPassword, clearRelayPassword, setClearRelayPassword,
  relayPasswordStored, relay, savedLocal, dirty }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [showOverrides, setShowOverrides] = React.useState(Boolean((values.relay.transport_overrides || []).length));
  const r = values.relay;
  const sh = r.smarthost || {};
  const direct = r.delivery === "direct";
  const setSmarthost = (patch) => setRelay({ smarthost: { ...sh, ...patch } });
  const dkim = useMutation({
    mutationFn: () => api("/api/admin/mail/relay/dkim", { method: "POST", body: { selector: r.dkim_selector || null } }),
    onSuccess: (res) => {
      if (res.relay) qc.setQueryData(MAIL_RELAY_KEY, res.relay);
      qc.invalidateQueries({ queryKey: ["mail-settings"] });
      toast(res.result && res.result.message ? res.result.message : "DKIM 키를 만들었습니다.", "success");
    },
  });
  const dkimError = failureText([dkim, "DKIM 키를 만들지 못했습니다."]);
  const keyBlocked = !savedLocal || dirty;
  const publicKey = relay && relay.dkim ? relay.dkim.public : null;
  function changeSecurity(next) {
    const patch = { security: next };
    if (Number(sh.port) === PORT_PRESETS[sh.security]) patch.port = PORT_PRESETS[next];
    setSmarthost(patch);
  }
  return (
    <>
      <FormSection titleAs="h2" title="로컬 릴레이">
        {relay ? <RelayComponentSlot relay={relay} savedLocal={savedLocal} dirty={dirty} /> : null}
        <Field label="전달 방식" labelId="relay-delivery-label">
          <ChoiceCards
            name="relay-delivery" ariaLabel="전달 방식" value={r.delivery}
            onChange={(next) => setRelay({ delivery: next })}
            options={[
              { value: "smarthost", label: "상위 SMTP 이용", description: "다른 SMTP 서버를 거쳐 보냅니다." },
              {
                /* 「고급」은 제목 옆 표지다 — 설명 아래 한 줄(`note`)로 두면 낱말 하나가 외딴 줄로 섰다(P17V 상태 캡처). */
                value: "direct", label: "인터넷으로 직접 전달", badge: "고급",
                description: "받는 쪽 메일 서버로 바로 보냅니다. DNS 설정이 필요합니다.",
              },
            ]}
          />
        </Field>
      </FormSection>

      {!direct ? (
        <FormSection titleAs="h2" title="상위 SMTP 서버">
          <FieldRow columns={["2fr", "12rem", "8rem"]}>
            <Field label="서버 주소" htmlFor="relay-sh-host" required={values.enabled}>
              <TextField id="relay-sh-host" size="small" fullWidth value={sh.host || ""} placeholder="smtp.example.com"
                onChange={(e) => setSmarthost({ host: e.target.value })} inputProps={{ spellCheck: false, autoComplete: "off" }} />
            </Field>
            <Field label="보안 연결" labelId="relay-sh-security-label">
              <TextField id="relay-sh-security" select size="small" fullWidth value={sh.security || "starttls"}
                SelectProps={{ labelId: "relay-sh-security-label" }} onChange={(e) => changeSecurity(e.target.value)}>
                {SECURITY.map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
              </TextField>
            </Field>
            <Field label="포트" htmlFor="relay-sh-port">
              <TextField id="relay-sh-port" size="small" type="number" fullWidth value={sh.port ?? 587}
                onChange={(e) => setSmarthost({ port: e.target.value })} inputProps={{ min: 1, max: 65535 }} />
            </Field>
          </FieldRow>
          <FieldRow columns={["1fr", "1fr"]}>
            <Field label="계정" htmlFor="relay-sh-username" help="계정이 없는 사내 중계라면 계정과 비밀번호를 비워 둡니다.">
              <TextField id="relay-sh-username" size="small" fullWidth value={sh.username || ""}
                onChange={(e) => setSmarthost({ username: e.target.value })} inputProps={{ spellCheck: false, autoComplete: "off" }} />
            </Field>
            <Field
              label="비밀번호" htmlFor="relay-sh-password"
              help={clearRelayPassword ? "저장하면 비밀번호를 삭제합니다."
                : relayPassword ? "저장하면 이 비밀번호로 바꿉니다."
                  : relayPasswordStored ? "비밀번호가 저장돼 있습니다. 바꿀 때만 새로 넣으세요." : "비밀번호가 저장돼 있지 않습니다."}
              action={relayPasswordStored && !relayPassword ? (
                <Button onClick={() => setClearRelayPassword((v) => !v)}>{clearRelayPassword ? "삭제 취소" : "삭제"}</Button>
              ) : null}
            >
              <TextField id="relay-sh-password" size="small" type="password" fullWidth value={relayPassword}
                placeholder={relayPasswordStored ? "저장됨" : ""} disabled={!sh.username && !relayPassword}
                onChange={(e) => { setRelayPassword(e.target.value); setClearRelayPassword(false); }}
                inputProps={{ autoComplete: "new-password" }} />
            </Field>
          </FieldRow>
        </FormSection>
      ) : (
        <FormSection titleAs="h2" title="보내는 도메인과 서버 이름"
          description="받는 쪽 메일 서버가 이 이름과 주소로 이 서버를 확인합니다.">
          <FieldRow columns={["2fr", "1fr"]}>
            <Field label="서버 이름(HELO)" htmlFor="relay-helo" required={values.enabled}
              help="공개 DNS 에 있는 이름이어야 합니다. 예: mail.example.com">
              <TextField id="relay-helo" size="small" fullWidth value={r.helo_name || ""} placeholder="mail.example.com"
                onChange={(e) => setRelay({ helo_name: e.target.value })} inputProps={{ spellCheck: false, autoComplete: "off" }} />
            </Field>
            <Field label="공인 IP" htmlFor="relay-ip" help="비우면 점검이 받는 쪽 인사말에서 읽습니다.">
              <TextField id="relay-ip" size="small" fullWidth value={r.public_ip || ""} placeholder="자동 확인"
                onChange={(e) => setRelay({ public_ip: e.target.value })} inputProps={{ spellCheck: false }} />
            </Field>
          </FieldRow>
          <Box sx={{ "& > .k-settingrow:first-of-type": { borderTop: 0, pt: 0 } }}>
            <SettingRow
              compact label="IPv4 만 쓰기" controlId="relay-ipv4"
              description="이 서버에서 바깥으로 나가는 IPv6 가 없으면 켜 둡니다."
              action={(
                <Checkbox id="relay-ipv4" checked={Boolean(r.ipv4_only)} onChange={(e) => setRelay({ ipv4_only: e.target.checked })}
                  slotProps={{ input: { "aria-label": "IPv4 만 쓰기" } }} />
              )}
            />
            <SettingRow
              compact label="DKIM 서명" controlId="relay-dkim"
              description="보내는 메일에 이 서버의 서명을 붙입니다. 받는 쪽이 정크로 분류하지 않게 돕습니다."
              action={(
                <Checkbox id="relay-dkim" checked={Boolean(r.dkim_enabled)} onChange={(e) => setRelay({ dkim_enabled: e.target.checked })}
                  slotProps={{ input: { "aria-label": "DKIM 서명" } }} />
              )}
            />
          </Box>
          {r.dkim_enabled ? (
            <FieldRow columns={["20rem"]}>
              <Field label="선택자" htmlFor="relay-dkim-selector"
                help={publicKey ? "키가 있습니다. 아래 준비 점검의 DKIM 레코드를 도메인 DNS 에 넣으세요."
                  : keyBlocked ? "저장한 뒤에 키를 만들 수 있습니다." : "키를 만들면 DNS 에 넣을 레코드가 생깁니다."}
                action={(
                  <Button loading={dkim.isPending} disabled={keyBlocked} onClick={() => dkim.mutate()}>
                    {publicKey ? "키 확인" : "키 추가"}
                  </Button>
                )}>
                <TextField id="relay-dkim-selector" size="small" fullWidth value={r.dkim_selector || ""} placeholder="ca1"
                  onChange={(e) => setRelay({ dkim_selector: e.target.value })} inputProps={{ spellCheck: false }} />
              </Field>
            </FieldRow>
          ) : null}
          {dkimError ? <Callout tone="danger" compact>{dkimError}</Callout> : null}
          <Box>
            <Button onClick={() => setShowOverrides((v) => !v)} aria-expanded={showOverrides} aria-controls="relay-overrides-box">
              {showOverrides ? "받는 도메인별 전달 서버 접기" : "받는 도메인별 전달 서버 펼치기"}
            </Button>
          </Box>
          {showOverrides ? (
            <Box id="relay-overrides-box" sx={{ display: "grid", gap: 2 }}>
              <Line>이 서버의 DNS 가 받는 쪽 메일 서버를 모를 때(사내 분리 DNS) 도메인마다 보낼 서버를 정합니다.</Line>
              <OverrideRows rows={r.transport_overrides} onChange={(rows) => setRelay({ transport_overrides: rows })} />
              <FieldRow columns={["1fr"]}>
                <Field label="비교할 공개 DNS 서버" htmlFor="relay-resolvers"
                  help="준비 점검이 이 서버의 답과 견줍니다. IPv4 주소를 쉼표로 나눠 세 개까지 넣습니다. 비우면 견주지 않습니다.">
                  <TextField id="relay-resolvers" size="small" fullWidth value={(r.compare_resolvers || []).join(", ")}
                    placeholder="8.8.8.8" inputProps={{ spellCheck: false }}
                    onChange={(e) => setRelay({ compare_resolvers: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
                </Field>
              </FieldRow>
            </Box>
          ) : null}
        </FormSection>
      )}
    </>
  );
}

/* RelayFields 안에서 쓰는 구성 요소 줄 - verify 감시는 MailScreen 의 것을 문맥으로 받는다. */
export const RelayVerifyContext = React.createContext(null);
function RelayComponentSlot(props) {
  const verify = React.useContext(RelayVerifyContext);
  return <RelayComponent {...props} verify={verify} />;
}

/* 바깥으로 보내기 준비 — 점검 결과 표와 복사할 DNS 레코드. */
export function RelayReadiness({ relay, savedLocal, dirty }) {
  const qc = useQueryClient();
  const [jobId, setJobId] = React.useState(null);
  const [timedOut, setTimedOut] = React.useState(false);
  const [showRecords, setShowRecords] = React.useState(false);
  const toast = useToast();
  const start = useMutation({
    mutationFn: () => api("/api/admin/mail/relay/check", { method: "POST", body: {} }),
    onSuccess: (res) => { setTimedOut(false); setJobId(res.job_id); },
  });
  const poll = useQuery({
    queryKey: ["mail-relay-check", jobId],
    queryFn: () => api(`/api/admin/mail/relay/check/${jobId}`),
    enabled: !!jobId && !timedOut,
    refetchInterval: (q) => (q.state.data && q.state.data.pending === false ? false : POLL_MS),
  });
  React.useEffect(() => {
    const d = poll.data;
    if (jobId && d && d.job_id === jobId && d.pending === false) {
      setJobId(null);
      if (d.readiness) qc.setQueryData(MAIL_RELAY_KEY, (old) => (old ? { ...old, readiness: d.readiness } : old));
      qc.invalidateQueries({ queryKey: MAIL_RELAY_KEY });
    }
  }, [poll.data, jobId, qc]);
  React.useEffect(() => {
    if (!jobId) return undefined;
    const timer = setTimeout(() => setTimedOut(true), CHECK_LIMIT_MS);
    return () => clearTimeout(timer);
  }, [jobId]);
  const readiness = relay && relay.readiness;
  const checks = (readiness && readiness.checks) || [];
  const records = (readiness && readiness.records) || [];
  const running = !!jobId && !timedOut;
  const failed = poll.data && poll.data.pending === false && poll.data.error ? poll.data.error : null;
  const error = failureText([start, "점검을 시작하지 못했습니다."]) || failed;
  const blocked = !savedLocal || dirty;
  async function copy(value) {
    try {
      await navigator.clipboard.writeText(value);
      toast("복사했습니다.", "success");
    } catch {
      toast("복사하지 못했습니다. 값을 직접 선택해 복사하세요.", "error");
    }
  }
  return (
    <FormSection
      titleAs="h2" title="바깥으로 보내기 준비"
      description={readiness && readiness.checked_at ? `최근 점검 ${fmtDateTime(readiness.checked_at)}` : "아직 점검하지 않았습니다."}
      action={(
        <Button loading={running || start.isPending} disabled={blocked} onClick={() => start.mutate()}>점검 다시 하기</Button>
      )}
    >
      {readiness && readiness.stale ? <Callout tone="info" compact>점검한 뒤 설정이 바뀌었습니다. 다시 점검하세요.</Callout> : null}
      {timedOut ? <Callout tone="info" compact>점검이 시간 안에 끝나지 않았습니다. 잠시 뒤 다시 점검하세요.</Callout> : null}
      {error ? <Callout tone="danger" compact>{error}</Callout> : null}
      {checks.length ? (
        <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid" }} data-testid="relay-checks">
          {checks.map((c) => {
            const meta = CHECK_STATE[c.state] || CHECK_STATE.unknown;
            return (
              <Box component="li" key={c.key} data-check={c.key} data-check-state={c.state}
                sx={{ display: "grid", gridTemplateColumns: "5rem 11rem minmax(0,1fr)", columnGap: 1.5, py: 1.25, alignItems: "baseline",
                  borderTop: 1, borderColor: "rule", "&:first-of-type": { borderTop: 0, pt: 0 } }}>
                <DotLabel label={meta.label} tone={meta.tone} />
                <Typography sx={{ fontWeight: FONT_WEIGHT.semibold, fontSize: FONT_SIZE.bodySm, ...KO_WORD_BREAK }}>{c.label}</Typography>
                <Box sx={{ minWidth: 0, display: "grid", gap: 0.25 }}>
                  <Line muted={false}>{c.message}</Line>
                  {c.need ? <Line>{c.need}</Line> : null}
                  {c.where ? <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary" }}>고칠 곳: {c.where}</Typography> : null}
                  {c.technical ? (
                    <TechDetail><Typography sx={{ fontSize: FONT_SIZE.caption, wordBreak: "break-all" }}>{c.technical}</Typography></TechDetail>
                  ) : null}
                </Box>
              </Box>
            );
          })}
        </Box>
      ) : (
        <Line>{blocked ? "로컬 릴레이 설정을 저장한 뒤에 점검할 수 있습니다." : "점검하면 바깥으로 보내는 데 필요한 것을 한 줄씩 확인합니다."}</Line>
      )}
      {records.length ? (
        <>
          <Box>
            <Button onClick={() => setShowRecords((v) => !v)} aria-expanded={showRecords} aria-controls="relay-records">
              {showRecords ? "복사할 DNS 레코드 접기" : "복사할 DNS 레코드 펼치기"}
            </Button>
          </Box>
          {showRecords ? (
            <Box id="relay-records" component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1.5 }}
              data-testid="relay-records">
              {records.map((rec) => (
                <Box component="li" key={rec.key + rec.name}
                  sx={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", columnGap: 1.5, alignItems: "start",
                    p: 1.5, bgcolor: "background.inset", borderRadius: `${RADIUS.sm}px` }}>
                  <Box sx={{ minWidth: 0, display: "grid", gap: 0.5 }}>
                    <Box sx={{ display: "flex", gap: 1, minWidth: 0 }}>
                      <Typography sx={{ fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.semibold }}>{rec.type}</Typography>
                      <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", wordBreak: "break-all" }}>{rec.name}</Typography>
                    </Box>
                    <Typography component="code"
                      sx={{ fontSize: FONT_SIZE.caption, fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", wordBreak: "break-all" }}>
                      {rec.value}
                    </Typography>
                    {rec.request ? <Line>{rec.request}</Line> : null}
                    {rec.note ? <Line>{rec.note}</Line> : null}
                  </Box>
                  <Button size="sm" onClick={() => copy(rec.value)} aria-label={`${rec.name} 값 복사`}>복사</Button>
                </Box>
              ))}
            </Box>
          ) : null}
        </>
      ) : null}
    </FormSection>
  );
}

/* 설정 권한이 없는 역할이 보는 한 줄 — 방식과 구성 요소 상태만. */
export function RelayReadOnly({ summary }) {
  const relay = summary && summary.relay ? summary.relay : {};
  return (
    <FormSection titleAs="h2" title="로컬 릴레이">
      <Line muted={false}>{relay.delivery === "direct" ? "인터넷으로 직접 전달합니다." : "상위 SMTP 서버를 거쳐 보냅니다."}</Line>
    </FormSection>
  );
}

export function useRelayQuery(enabled) {
  return useQuery({ queryKey: MAIL_RELAY_KEY, queryFn: () => api("/api/admin/mail/relay"), enabled, retry: false });
}
