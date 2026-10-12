import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { failureText } from "../../lib/failure.js";
import {
  ActionFooter, Button, Callout, Card, ErrorState, Field, FieldRow, FormSection, Skeleton, useConfirm, useToast,
} from "../../ui/kit.jsx";
import { SettingRow } from "../../ui/adminKit.jsx";
import { ChoiceCards } from "../../ui/ChoiceCards.jsx";
import { FONT_SIZE, KO_WORD_BREAK } from "../../ui/theme.js";
import { MailStatusCard } from "./MailStatusCard.jsx";
import { ProgressStrip } from "./ProgressStrip.jsx";
import { PRESET_CUSTOM, SMTP_PRESETS, presetByKey, presetOf, presetPatch } from "./presets.js";
import {
  MAIL_RELAY_KEY, RelayFields, RelayReadOnly, RelayReadiness, RelayVerifyContext, useRelayQuery,
} from "./RelaySection.jsx";

/* 메일 · 설정 탭 (계획 M1, D-548 · D-560) — 관리자의 작업 순서대로 읽힌다: 켜기 → 보내는 방법 → 보내는 사람 → 고른 방식의 설정 → 보안 → 저장.
 *
 * ## 「가진 것」에서 출발하는 안내 흐름 (D-560)
 *
 * 상태 면 아래 **진행 띠**가 서버가 계산한 일곱 단계(켜기 · 방법 · 입력 · 적용 · 연결 확인 · 시험 메일 · 받은 편지함 확인)와 「다음 할 일」
 * 한 문장을 보이고, [이동] 은 그 단계의 구획이나 머리 단추로 간다. 보내는 방법은 로컬 릴레이가 먼저다(설치에 포함된 구성 요소, 계정 불필요).
 * 외부 SMTP 구획 맨 위의 제공자 프리셋(Gmail · Microsoft 365 · Naver · 직접 입력)이 서버 값을 채우고 비밀번호 도움말과 발급처 링크를 준다.
 * 긴 준비 점검 · 레코드 · 기술 값은 로컬 릴레이 구획의 「진단」 접기 안이다(`RelayReadiness`).
 *
 * 카드는 맨 위의 짧은 상태 면 하나뿐이고, 설정은 한 판 위의 구획(머리 + 1px 선)이다(F7). SMTP 설정을 범용 JSON 설정 창으로
 * 되돌리지 않는다. 저장 방식은 하나다: 비밀번호까지 한 번의 「저장」에 실린다 - 예전에는 비밀번호만 즉시 저장되고 나머지는 따로
 * 저장해, 한쪽만 저장된 채 창을 닫는 일이 있었다. 그래서 이 폼의 켜고 끄는 칸(메일 발송 사용 · 서버 인증서 확인)은 스위치가 아니라
 * 체크박스다 - 스위치는 누르는 즉시 저장되는 설정에만 쓴다(RULES §3).
 *
 * 저장하면 서버가 보낼 수 있는 설정일 때 연결 확인을 저절로 시작하고, 상태 면이 「확인하는 중」을 보인다(60초 상한). 설정 권한이
 * 없는 역할은 같은 배치의 읽기 전용 값과 한 줄 안내를 본다.
 */

export const MAIL_SETTINGS_KEY = ["mail-settings"];
const SECURITY = [["starttls", "STARTTLS"], ["ssl", "SSL"], ["none", "사용 안 함"]];
const EMPTY_RELAY = {
  delivery: "smarthost", smarthost: { host: "", port: 587, security: "starttls", username: "" }, helo_name: "",
  public_ip: "", ipv4_only: false, dkim_enabled: false, dkim_selector: "", dkim_public: "", transport_overrides: [],
  compare_resolvers: [],
};
const EMPTY = {
  enabled: false, host: "", port: 587, security: "starttls", from_address: "", from_name: "", username: "",
  timeout_seconds: 20, tls_verify: true, ca_pem: "", mode: "external", relay: EMPTY_RELAY,
};

function sameValue(a, b) {
  if (a && typeof a === "object") return JSON.stringify(a) === JSON.stringify(b);
  return String(a ?? "") === String(b ?? "");
}

/* 저장 본문의 로컬 릴레이 칸 — 서버가 적는 칸(DKIM 공개키)은 보내지 않는다(보내면 422). 숫자 칸은 숫자로. */
function relayBody(relay) {
  const r = { ...EMPTY_RELAY, ...(relay || {}) };
  const sh = { ...EMPTY_RELAY.smarthost, ...(r.smarthost || {}) };
  return {
    delivery: r.delivery,
    smarthost: { host: String(sh.host || "").trim(), port: Number(sh.port), security: sh.security, username: String(sh.username || "").trim() },
    helo_name: String(r.helo_name || "").trim(),
    public_ip: String(r.public_ip || "").trim(),
    ipv4_only: Boolean(r.ipv4_only),
    dkim_enabled: Boolean(r.dkim_enabled),
    dkim_selector: String(r.dkim_selector || "").trim(),
    transport_overrides: (r.transport_overrides || [])
      .map((o) => ({ domain: String(o.domain || "").trim(), host: String(o.host || "").trim() }))
      .filter((o) => o.domain || o.host),
    compare_resolvers: (r.compare_resolvers || []).map((s) => String(s).trim()).filter(Boolean),
  };
}

export function MailSettingsTab({ status, verify, onDirtyChange, onAction }) {
  const caps = status.capabilities || {};
  if (!caps.can_configure) return <ReadOnlySettings status={status} verify={verify} />;
  return <EditableSettings status={status} verify={verify} onDirtyChange={onDirtyChange} onAction={onAction} />;
}

/* 진행 띠의 「이동」 - 구획(`section:*`)은 여기서 굴리고, 머리 단추(`action:*`)는 화면(MailScreen)에 맡긴다. */
function useSectionJump(onAction) {
  const refs = React.useRef({});
  const register = (key) => (el) => { refs.current[key] = el; };
  const go = (next) => {
    const anchor = (next && next.anchor) || "";
    if (anchor.startsWith("section:")) {
      const el = refs.current[anchor.slice("section:".length)];
      const target = el && (el.firstElementChild || el);
      if (target && typeof target.scrollIntoView === "function") target.scrollIntoView({ block: "start", behavior: "smooth" });
      return;
    }
    if (onAction) onAction(anchor);
  };
  return { register, go };
}

function EditableSettings({ status, verify, onDirtyChange, onAction }) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const query = useQuery({ queryKey: MAIL_SETTINGS_KEY, queryFn: () => api("/api/admin/mail/settings") });
  const [draft, setDraft] = React.useState({});
  const [password, setPassword] = React.useState("");
  const [clearPassword, setClearPassword] = React.useState(false);
  const [relayPassword, setRelayPassword] = React.useState("");
  const [clearRelayPassword, setClearRelayPassword] = React.useState(false);
  const [advanced, setAdvanced] = React.useState(false);
  const [presetKey, setPresetKey] = React.useState(null);
  const jump = useSectionJump(onAction);

  const base = { ...EMPTY, ...((query.data && query.data.settings) || {}) };
  base.relay = { ...EMPTY_RELAY, ...(base.relay || {}) };
  const values = { ...base, ...draft };
  const presets = ((query.data && query.data.presets) || {}).ports || { starttls: 587, ssl: 465, none: 25 };
  const stored = Boolean(query.data && query.data.password && query.data.password.stored);
  const relayPasswordStored = Boolean(query.data && query.data.relay_password && query.data.relay_password.stored);
  const dirty = Object.keys(draft).some((k) => !sameValue(draft[k], base[k])) || Boolean(password) || clearPassword
    || Boolean(relayPassword) || clearRelayPassword;
  const local = values.mode === "local_relay";
  const relayQuery = useRelayQuery(local);
  React.useEffect(() => { if (onDirtyChange) onDirtyChange(dirty); }, [dirty, onDirtyChange]);
  React.useEffect(() => () => { if (onDirtyChange) onDirtyChange(false); }, [onDirtyChange]);

  const save = useMutation({
    mutationFn: (body) => api("/api/admin/mail/settings", { method: "PUT", body }),
    onSuccess: (res) => {
      qc.setQueryData(MAIL_SETTINGS_KEY, {
        settings: res.settings, password: res.password, relay_password: res.relay_password, presets: res.presets, limits: res.limits,
      });
      qc.invalidateQueries({ queryKey: ["mail-status"] });
      qc.invalidateQueries({ queryKey: MAIL_RELAY_KEY });
      setDraft({});
      setPassword("");
      setClearPassword(false);
      setRelayPassword("");
      setClearRelayPassword(false);
      const applied = res.relay_apply;
      if (applied && !applied.ok) {
        toast("메일 설정을 저장했지만 로컬 릴레이에 적용하지 못했습니다.", "error");
      } else {
        toast(applied ? "메일 설정을 저장하고 로컬 릴레이에 적용했습니다." : "메일 설정을 저장했습니다.", "success");
      }
      if (res.verify && res.verify.job_id && verify) verify.watch(res.verify.job_id);
    },
  });

  if (query.isLoading) return <Skeleton lines={8} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={query.refetch} />;

  const set = (patch) => setDraft((d) => ({ ...d, ...patch }));
  const setRelay = (patch) => setDraft((d) => ({ ...d, relay: { ...(d.relay || base.relay), ...patch } }));
  /* 프리셋은 값을 채우는 도구다 - 고른 적이 없으면 지금 서버 주소의 모양으로 안다. 서버 주소를 고치면 「직접 입력」으로 돌아간다. */
  const preset = presetKey || presetOf(values);
  const presetInfo = presetByKey(preset);
  function choosePreset(key) {
    setPresetKey(key);
    const patch = presetPatch(key);
    if (Object.keys(patch).length) set(patch);
  }
  function changeSecurity(next) {
    const before = values.security;
    const patch = { security: next };
    // 포트가 이전 방식의 기본값이었으면 새 방식의 기본값으로 따라간다. 사람이 고친 포트는 그대로 둔다.
    if (Number(values.port) === presets[before]) patch.port = presets[next];
    set(patch);
  }

  async function submit() {
    const body = {
      ...values, port: Number(values.port), timeout_seconds: Number(values.timeout_seconds), relay: relayBody(values.relay),
    };
    if (password) body.password = password;
    if (clearPassword && !password) body.clear_password = true;
    if (relayPassword) body.relay_password = relayPassword;
    if (clearRelayPassword && !relayPassword) body.clear_relay_password = true;
    if (!local && base.tls_verify !== false && body.tls_verify === false && body.security !== "none") {
      const ok = await confirm(
        "서버 인증서 확인을 끕니다. 중간에서 메일과 로그인 비밀번호를 가로챌 수 있게 됩니다. 사설 인증서라면 CA 인증서를 붙여 넣는 쪽이 안전합니다. 계속할까요?",
        { danger: true, title: "인증서 확인 끄기", confirmLabel: "끄고 저장" },
      );
      if (!ok) return;
    }
    if (!local && body.security === "none" && body.username && !(base.security === "none" && base.username)) {
      const ok = await confirm(
        "보안 연결 없이 로그인하면 비밀번호가 암호화되지 않은 채로 전송됩니다. 사내망 중계에서만 쓰세요. 계속할까요?",
        { danger: true, title: "보안 연결 없이 로그인", confirmLabel: "그대로 저장" },
      );
      if (!ok) return;
    }
    save.mutate(body);
  }

  const saveError = failureText([save, "메일 설정을 저장하지 못했습니다."]);
  const off = !values.enabled;
  return (
    <RelayVerifyContext.Provider value={verify}>
      <MailStatusCard health={status.health} summary={status.summary} relay={status.relay} checking={verify && verify.waiting}
        timedOut={verify && verify.timedOut} />
      {status.base_url && status.base_url.problem ? <Callout tone="warn" compact>{status.base_url.problem}</Callout> : null}

      {/* 발이 긴 폼에서 창 아래에 따라오도록(`ActionFooter sticky`) 판은 넘침을 자르지 않는다 - MUI Card 뿌리의 `overflow: hidden`
          이 판을 스크롤 창으로 만들면 발이 판 안에서만 움직이고 끝까지 굴렸을 때 마지막 단추를 덮었다(P12 실측 4px). */}
      <Card stack data-testid="mail-settings-form" sx={{ overflow: "visible" }}>
        {/* 진행 띠(D-560) - 서버가 계산한 일곱 단계와 다음 할 일. 저장하지 않은 수정 내용이 있으면 저장한 사실이 아니라 그대로다. */}
        <ProgressStrip progress={status.progress} onGo={jump.go} />

        <Box ref={jump.register("enable")} sx={{ display: "contents" }}>
        <FormSection titleAs="h2" title="메일 보내기">
          <Box sx={{ "& > .k-settingrow:first-of-type": { borderTop: 0, pt: 0 } }}>
            <SettingRow
              compact label="메일 발송 사용" controlId="mail-enabled"
              description="끄면 ClovirAssist 가 메일을 보내지 않습니다. 저장해야 적용됩니다."
              action={(
                <Checkbox id="mail-enabled" checked={Boolean(values.enabled)} onChange={(e) => set({ enabled: e.target.checked })}
                  slotProps={{ input: { "aria-label": "메일 발송 사용" } }} />
              )}
            />
          </Box>
        </FormSection>
        </Box>

        <Box ref={jump.register("method")} sx={{ display: "contents" }}>
        <FormSection titleAs="h2" title="보내는 방법"
          description="메일 계정이 없어도 로컬 릴레이로 보낼 수 있습니다. 회사 계정이나 Gmail 같은 외부 계정이 있으면 외부 SMTP 를 고릅니다.">
          {/* 로컬 릴레이가 먼저다(D-560) - 설치에 포함된 구성 요소라 계정이 필요 없다. */}
          <ChoiceCards
            name="mail-mode" ariaLabel="보내는 방법" value={values.mode} onChange={(next) => set({ mode: next })}
            options={[
              {
                value: "local_relay", label: "ClovirAssist 로컬 릴레이",
                description: "이 서버에 설치된 구성 요소로 보냅니다. 메일 계정이 필요 없습니다.",
              },
              { value: "external", label: "외부 SMTP 사용", description: "회사 메일 계정이나 Gmail 같은 외부 계정으로 보냅니다." },
            ]}
          />
        </FormSection>
        </Box>

        <Box ref={jump.register("inputs")} sx={{ display: "contents" }}>
        <FormSection titleAs="h2" title="보내는 사람">
          <FieldRow columns={["1fr", "1fr"]}>
            <Field label="보내는 주소" htmlFor="mail-from" required={!off}
              help={presetInfo && presetInfo.from_note && !local ? presetInfo.from_note : "받는 사람이 보는 주소입니다."}>
              <TextField id="mail-from" size="small" fullWidth value={values.from_address}
                onChange={(e) => set({ from_address: e.target.value })} placeholder="noreply@example.com"
                inputProps={{ spellCheck: false, autoComplete: "off" }} />
            </Field>
            <Field label="보내는 이름" htmlFor="mail-from-name" help="비우면 주소만 보입니다.">
              <TextField id="mail-from-name" size="small" fullWidth value={values.from_name}
                onChange={(e) => set({ from_name: e.target.value })} placeholder="ClovirAssist" />
            </Field>
          </FieldRow>
        </FormSection>
        </Box>

        {local ? (
          <Box ref={jump.register("relay")} sx={{ display: "contents" }}>
            <RelayFields
              values={values} setRelay={setRelay} relay={relayQuery.data || null} savedLocal={base.mode === "local_relay"} dirty={dirty}
              relayPassword={relayPassword} setRelayPassword={setRelayPassword} clearRelayPassword={clearRelayPassword}
              setClearRelayPassword={setClearRelayPassword} relayPasswordStored={relayPasswordStored}
            />
            {relayQuery.isError ? <ErrorState error={relayQuery.error} onRetry={relayQuery.refetch} /> : null}
            <RelayReadiness relay={relayQuery.data || null} savedLocal={base.mode === "local_relay"} dirty={dirty} />
          </Box>
        ) : null}

        {local ? null : (
        <FormSection titleAs="h2" title="SMTP 서버"
          description="메일 서비스를 고르면 서버 값이 채워집니다. 계정과 비밀번호만 넣으면 됩니다.">
          {/* 제공자 프리셋(D-560) - 값을 채우는 도구다. 서버 주소를 고치면 「직접 입력」으로 돌아간다. */}
          <Field label="메일 서비스" labelId="mail-preset-label">
            <ChoiceCards
              name="mail-preset" ariaLabel="메일 서비스" value={preset} onChange={choosePreset}
              options={SMTP_PRESETS.map((p) => ({ value: p.key, label: p.label, description: p.description }))}
            />
          </Field>
          {presetInfo && preset !== PRESET_CUSTOM ? (
            <Box data-testid="mail-preset-help">
              <Callout tone="info" compact
                action={presetInfo.link ? (
                  <Link href={presetInfo.link.url} target="_blank" rel="noopener noreferrer" sx={{ fontSize: FONT_SIZE.bodySm, whiteSpace: "nowrap" }}>
                    {presetInfo.link.label}
                  </Link>
                ) : null}>
                {presetInfo.help}
              </Callout>
            </Box>
          ) : null}
          <FieldRow columns={["2fr", "12rem", "8rem"]}>
            <Field label="서버 주소" htmlFor="mail-host" required={!off}>
              <TextField id="mail-host" size="small" fullWidth value={values.host}
                onChange={(e) => { set({ host: e.target.value }); setPresetKey(null); }} placeholder="smtp.example.com"
                inputProps={{ spellCheck: false, autoComplete: "off" }} />
            </Field>
            <Field label="보안 연결" labelId="mail-security-label">
              <TextField id="mail-security" select size="small" fullWidth value={values.security}
                SelectProps={{ labelId: "mail-security-label" }}
                onChange={(e) => changeSecurity(e.target.value)}>
                {SECURITY.map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
              </TextField>
            </Field>
            <Field label="포트" htmlFor="mail-port">
              <TextField id="mail-port" size="small" type="number" fullWidth value={values.port}
                onChange={(e) => set({ port: e.target.value })} inputProps={{ min: 1, max: 65535 }} />
            </Field>
          </FieldRow>
          <FieldRow columns={["1fr", "1fr"]}>
            <Field label="계정" htmlFor="mail-username"
              help={preset !== PRESET_CUSTOM ? "그 서비스에 로그인하는 메일 주소입니다." : "계정이 없는 사내 중계라면 계정과 비밀번호를 비워 둡니다."}>
              <TextField id="mail-username" size="small" fullWidth value={values.username}
                onChange={(e) => set({ username: e.target.value })} inputProps={{ spellCheck: false, autoComplete: "off" }} />
            </Field>
            <Field
              label="비밀번호" htmlFor="mail-password"
              help={clearPassword ? "저장하면 비밀번호를 삭제합니다."
                : password ? "저장하면 이 비밀번호로 바꿉니다."
                  : stored ? "비밀번호가 저장돼 있습니다. 바꿀 때만 새로 넣으세요."
                    : (preset === "gmail" ? "16자리 앱 비밀번호를 넣습니다. 계정 비밀번호는 쓸 수 없습니다." : "비밀번호가 저장돼 있지 않습니다.")}
              action={stored && !password ? (
                <Button onClick={() => setClearPassword((v) => !v)}>{clearPassword ? "삭제 취소" : "삭제"}</Button>
              ) : null}
            >
              <TextField id="mail-password" size="small" type="password" fullWidth value={password}
                placeholder={stored ? "저장됨" : ""} disabled={!values.username && !password}
                onChange={(e) => { setPassword(e.target.value); setClearPassword(false); }}
                inputProps={{ autoComplete: "new-password" }} />
            </Field>
          </FieldRow>
        </FormSection>

        )}

        {local ? null : (
        <FormSection titleAs="h2" title="보안">
          <Box sx={{ "& > .k-settingrow:first-of-type": { borderTop: 0, pt: 0 } }}>
            <SettingRow
              compact label="서버 인증서 확인" controlId="mail-tls-verify"
              description={values.security === "none"
                ? "보안 연결을 쓰지 않아 인증서를 확인하지 않습니다."
                : "끄면 중간에서 메일과 로그인 비밀번호를 가로챌 수 있습니다. 사설 인증서는 아래 고급 설정에 CA 를 넣으세요."}
              action={(
                <Checkbox id="mail-tls-verify" checked={values.tls_verify !== false} disabled={values.security === "none"}
                  onChange={(e) => set({ tls_verify: e.target.checked })}
                  slotProps={{ input: { "aria-label": "서버 인증서 확인" } }} />
              )}
            />
          </Box>
          <Box>
            <Button onClick={() => setAdvanced((v) => !v)} aria-expanded={advanced} aria-controls="mail-advanced">
              {advanced ? "고급 설정 접기" : "고급 설정 펼치기"}
            </Button>
          </Box>
          {advanced ? (
            <Box id="mail-advanced" sx={{ display: "grid", gap: 2.5 }}>
              <Field label="사설 CA 인증서" htmlFor="mail-ca" help="-----BEGIN CERTIFICATE----- 로 시작하는 PEM 원문을 붙여 넣습니다.">
                <TextField id="mail-ca" size="small" fullWidth multiline minRows={4} value={values.ca_pem}
                  onChange={(e) => set({ ca_pem: e.target.value })} disabled={values.security === "none"}
                  inputProps={{ spellCheck: false }} />
              </Field>
              <FieldRow columns={["12rem"]}>
                <Field label="응답 대기 시간(초)" htmlFor="mail-timeout" help="1초에서 300초 사이로 정합니다.">
                  <TextField id="mail-timeout" size="small" type="number" fullWidth value={values.timeout_seconds}
                    onChange={(e) => set({ timeout_seconds: e.target.value })} inputProps={{ min: 1, max: 300 }} />
                </Field>
              </FieldRow>
            </Box>
          ) : null}
        </FormSection>
        )}

        {saveError ? <Callout tone="danger" compact>{saveError}</Callout> : null}
        <ActionFooter
          placement="card" sticky
          extra={dirty ? (
            <Typography component="span" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary", ...KO_WORD_BREAK }}>
              저장하지 않은 수정 내용이 있습니다.
            </Typography>
          ) : null}
        >
          <Button disabled={!dirty || save.isPending}
            onClick={() => {
              setDraft({}); setPassword(""); setClearPassword(false); setRelayPassword(""); setClearRelayPassword(false);
            }}>
            되돌리기
          </Button>
          <Button variant="primary" disabled={!dirty} loading={save.isPending} onClick={submit}>저장</Button>
        </ActionFooter>
      </Card>
    </RelayVerifyContext.Provider>
  );
}

function ReadOnlyValue({ label, value }) {
  return (
    <Field label={label}>
      <Typography sx={{ minHeight: 34, display: "flex", alignItems: "center", ...KO_WORD_BREAK }}>{value || "-"}</Typography>
    </Field>
  );
}

function ReadOnlySettings({ status, verify }) {
  const s = status.summary || {};
  const securityLabel = Object.fromEntries(SECURITY)[s.security] || s.security;
  return (
    <>
      <MailStatusCard health={status.health} summary={s} relay={status.relay} checking={verify && verify.waiting}
        timedOut={verify && verify.timedOut} />
      <Card stack data-testid="mail-settings-readonly">
        <Callout tone="info" compact>메일 서버 설정은 시스템 관리자만 바꿀 수 있습니다.</Callout>
        <FormSection titleAs="h2" title="메일 보내기">
          <ReadOnlyValue label="메일 발송" value={s.enabled ? "사용" : "사용 안 함"} />
        </FormSection>
        <FormSection titleAs="h2" title="보내는 방법">
          <ReadOnlyValue label="보내는 방법" value={s.mode === "local_relay" ? "ClovirAssist 로컬 릴레이" : "외부 SMTP 사용"} />
        </FormSection>
        <FormSection titleAs="h2" title="보내는 사람">
          <FieldRow columns={["1fr", "1fr"]}>
            <ReadOnlyValue label="보내는 주소" value={s.from_address} />
            <ReadOnlyValue label="보내는 이름" value={s.from_name} />
          </FieldRow>
        </FormSection>
        {s.mode === "local_relay" ? <RelayReadOnly summary={s} /> : (
        <FormSection titleAs="h2" title="SMTP 서버">
          <FieldRow columns={["2fr", "12rem", "8rem"]}>
            <ReadOnlyValue label="서버 주소" value={s.host} />
            <ReadOnlyValue label="보안 연결" value={securityLabel} />
            <ReadOnlyValue label="포트" value={s.port != null ? String(s.port) : ""} />
          </FieldRow>
          <FieldRow columns={["1fr", "1fr"]}>
            <ReadOnlyValue label="계정" value={s.username || "사용 안 함"} />
            <ReadOnlyValue label="비밀번호" value={!s.username ? "사용 안 함" : (s.password && s.password.stored ? "저장됨" : "저장되지 않음")} />
          </FieldRow>
        </FormSection>
        )}
        <FormSection titleAs="h2" title="보안">
          <ReadOnlyValue label="서버 인증서 확인" value={s.security === "none" ? "보안 연결 없음" : (s.tls_verify === false ? "확인 안 함" : "확인함")} />
        </FormSection>
      </Card>
    </>
  );
}

export default MailSettingsTab;
