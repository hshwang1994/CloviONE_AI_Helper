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
import { fmtDateTime, fmtListStamp } from "../../lib/format.js";
import {
  ActionFooter, Button, Callout, Card, DotLabel, ErrorState, Field, FieldRow, FormSection, Skeleton, useConfirm, useToast,
} from "../../ui/kit.jsx";
import { SettingRow, SettingRows } from "../../ui/adminKit.jsx";
import { ChoiceCards } from "../../ui/ChoiceCards.jsx";
import { Disclosure } from "../../ui/Disclosure.jsx";
import { FONT_SIZE, KO_WORD_BREAK } from "../../ui/theme.js";
import { InboxIconHelp } from "./InboxIconHelp.jsx";
import { MailStatusCard, STATE_TONE, testWord } from "./MailStatusCard.jsx";
import { PRESET_CUSTOM, SMTP_PRESETS, presetByKey, presetOf, presetPatch } from "./presets.js";
import {
  MAIL_RELAY_KEY, RelayAdvancedFields, RelayFields, RelayReadOnly, RelayReadiness, RelayVerifyContext, SubHeading,
  readinessSummary, useReadinessCheck, useRelayQuery,
} from "./RelaySection.jsx";

/* 메일 · 설정 탭 (계획 M1 · M4, D-548 · D-560 · D-574) — 다섯 구획이 관리자의 작업 순서대로 선다.
 *
 *   ① 상태 요약          독립된 판(`MailStatusCard`): 상태 낱말 · 한 문장 · 「지금 할 일」과 [이동] · 일곱 단계 · 사실 띠 · 기술 정보
 *   ② 기본 설정          메일 발송 사용 · 보내는 방법 · 보내는 주소와 이름
 *   ③ 전달 방법 설정     **고른 방법의 칸만** — 외부 SMTP(제공자 프리셋 · 서버 · 계정 · 인증서 확인) 또는 로컬 릴레이(구성 요소 · 전달 방식)
 *   ④ 연결과 발송 확인   설정 줄 셋: 연결 확인 · 시험 메일 · 받은 편지함 확인. 단추는 저장한 설정으로만 돈다
 *   ⑤ 문제 해결과 고급   접기 하나(`Disclosure`, 처음에는 닫힘, 머리 요약 = 준비 점검 한 문장): 바깥으로 보내기 준비 · 받은 편지함
 *                        아이콘 · 고급 설정(사설 CA · 응답 대기 시간 | 받는 도메인별 전달 서버 · 비교할 공개 DNS)
 *
 * ②~⑤ 는 한 판 위의 구획이고 판 발(`ActionFooter sticky`)의 「저장」 하나가 비밀번호까지 한 번에 싣는다 — 예전에는 비밀번호만 즉시
 * 저장되고 나머지는 따로 저장해, 한쪽만 저장된 채 창을 닫는 일이 있었다. 그래서 이 폼의 켜고 끄는 칸(메일 발송 사용 · 서버 인증서 확인)은
 * 스위치가 아니라 체크박스다 - 스위치는 누르는 즉시 저장되는 설정에만 쓴다(RULES §3).
 *
 * 예전 화면 머리의 「연결 확인」 · 「시험 메일 보내기」는 ④ 의 줄로 내려왔다. 단추가 결과와 같은 줄에 서야 무엇을 눌렀고 무엇이
 * 나왔는지가 한눈에 이어진다. 「지금 할 일」의 [이동] 은 그 줄로 굴리고 단추에 초점을 옮긴다 — 누르는 일은 사람이 한다.
 * 손으로 짠 접기 넷(고급 설정 · 진단 · 레코드 · 전달 서버)은 ⑤ 의 접기 하나와 그 안의 소제목이 되었다.
 *
 * 저장하면 서버가 보낼 수 있는 설정일 때 연결 확인을 저절로 시작하고, 상태 면이 「확인하는 중」을 보인다(60초 상한). 설정 권한이
 * 없는 역할은 같은 다섯 구획의 읽기 전용 값과 한 줄 안내를 본다.
 */

/* 폼 줄의 칸 폭 — 12칸 격자(`FieldRow` 기본, 칸 폭을 보는 컨테이너 질의)에서 넓을 때 몇 칸, 두 칸 격자일 때 몇 칸. 좁은 판(모바일)
   에서는 한 칸씩 쌓인다. 예전의 고정 열(`2fr 12rem 8rem`)은 390 에서 서버 주소 칸을 20px 로 눌렀다(캡처 m4-1, D-574). */
export const FIELD_SPAN = {
  half: { wide: 6, mid: 1 }, server: { wide: 6, mid: 2 }, security: { wide: 4, mid: 1 }, port: { wide: 2, mid: 1 },
  main: { wide: 8, mid: 1 }, side: { wide: 4, mid: 1 },
};

export const MAIL_SETTINGS_KEY = ["mail-settings"];
const STATUS_KEY = ["mail-status"];
const DIRTY_HINT_ID = "mail-dirty-hint";
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

/* 구획 머리의 id — 「지금 할 일」의 [이동] 이 굴려 갈 자리다. 서버의 자리(`progress.ANCHORS`)를 구획 넷과 ④ 의 줄 셋으로 옮긴다. */
export const SECTION_IDS = {
  basics: "mail-section-basics", method: "mail-section-method", checks: "mail-section-checks", advanced: "mail-section-advanced",
};
const SECTION_OF_ANCHOR = {
  "section:enable": "basics", "section:method": "basics", "section:inputs": "basics", "section:relay": "method",
  "action:verify": "checks", "action:test": "checks", "action:inbox": "checks", "section:advanced": "advanced",
};
const ROW_OF_ANCHOR = { "action:verify": "verify", "action:test": "test", "action:inbox": "inbox" };

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

export function MailSettingsTab({ status, verify, onDirtyChange, checks = {} }) {
  const caps = status.capabilities || {};
  if (!caps.can_configure) return <ReadOnlySettings status={status} verify={verify} checks={checks} />;
  return <EditableSettings status={status} verify={verify} onDirtyChange={onDirtyChange} checks={checks} />;
}

/* 「지금 할 일」의 [이동] — 서버의 자리를 구획 머리나 ④ 의 줄로 옮겨 굴린다. 줄이면 그 줄의 단추에 초점을 둔다(누르지는 않는다). */
function useSectionJump(openAdvanced) {
  return React.useCallback((next) => {
    const anchor = (next && next.anchor) || "";
    const key = SECTION_OF_ANCHOR[anchor];
    if (!key) return;
    if (key === "advanced" && openAdvanced) openAdvanced();
    const rowKey = ROW_OF_ANCHOR[anchor];
    const row = rowKey ? document.querySelector(`[data-check-row="${rowKey}"]`) : null;
    const head = document.getElementById(SECTION_IDS[key]);
    const target = row || (head && (head.closest("section") || head));
    if (!target) return;
    if (typeof target.scrollIntoView === "function") target.scrollIntoView({ block: row ? "center" : "start", behavior: "smooth" });
    const button = row ? row.querySelector("button:not([disabled])") : null;
    if (button) button.focus({ preventScroll: true });
  }, [openAdvanced]);
}

function SectionTitleText({ id, children }) {
  return <span id={id}>{children}</span>;
}

/* 값 한 줄 — 점 + 낱말과 그 뒤의 덧붙임(시각 · 받는 주소). */
function ValueLine({ word, tone, rest }) {
  return (
    <Box component="span" sx={{ display: "inline-flex", alignItems: "baseline", gap: 1, flexWrap: "wrap", minWidth: 0 }}>
      <DotLabel label={word} tone={tone} />
      {rest ? <Typography component="span" variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{rest}</Typography> : null}
    </Box>
  );
}

function verifyValue(h, verifying) {
  if (verifying) return <ValueLine word="확인하는 중" tone="info" />;
  if (h.state === "disabled" || h.state === "unconfigured") return "메일 발송을 켜고 설정을 마친 뒤에 확인할 수 있습니다.";
  if (!h.checked_at) return "아직 확인하지 않았습니다.";
  if (h.state === "ok") return <ValueLine word="통과" tone="ok" rest={fmtListStamp(h.checked_at)} />;
  if (h.state === "failing") return <ValueLine word="실패" tone="danger" rest={fmtListStamp(h.checked_at)} />;
  return <ValueLine word={h.label || "알 수 없음"} tone={STATE_TONE[h.kind] || "neutral"} rest={fmtListStamp(h.checked_at)} />;
}

function testValue(test, waiting) {
  if (waiting) return <ValueLine word="보내는 중" tone="info" />;
  if (!test) return "아직 보내지 않았습니다.";
  const word = testWord(test);
  const rest = [fmtListStamp(test.sent_at || test.created_at), test.to_email].filter(Boolean).join(", ");
  return (
    <Box component="span" sx={{ display: "grid", gap: 0.25, minWidth: 0 }}>
      <ValueLine word={word.label} tone={word.tone} rest={rest} />
      {test.status === "failed" && test.error_summary ? (
        <Typography component="span" variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{test.error_summary}</Typography>
      ) : null}
    </Box>
  );
}

/* ④ 연결과 발송 확인 — 설정 줄 셋. 받은 편지함 확인(D-560 ⑦)은 접수된 시험 메일 한 통에 대해 사람이 「받았습니다」 · 「못 받았습니다」를
   기록한다. 제품은 도착을 잴 수 없으므로 이 기록이 일곱째 단계의 유일한 근거다. 받는 쪽 메일 서버까지 간 시험 메일만 묻는다 — 수신측이
   거부했거나(bounced) 만료된(expired) 메일, 아직 전달 중인 메일은 묻지 않는다(D-555). 바깥 추적이 없는 외부 SMTP(`remote_status` 없음)는
   「메일 서버가 접수함」까지가 아는 전부라 그대로 묻는다. 운영 권한이 없으면 단추 없이 지금 상태만 보인다. */
function MailChecks({ status, checks, verify, dirty, relayLocal, onOpenAdvanced }) {
  const qc = useQueryClient();
  const toast = useToast();
  const caps = status.capabilities || {};
  const operate = Boolean(caps.can_operate);
  const h = status.health || {};
  const cannotSend = h.state === "disabled" || h.state === "unconfigured";
  const test = status.latest_test || null;
  const inbox = status.inbox || null;
  const remote = test ? test.remote_status : null;
  const recorded = Boolean(test && inbox && inbox.delivery_id === test.id);
  const reachable = Boolean(test && test.status === "sent" && (!remote || remote === "delivered"));
  const asking = reachable && !recorded;
  const rejected = Boolean(test && test.status === "sent" && (remote === "bounced" || remote === "expired"));
  const verifying = Boolean(verify && verify.waiting);
  const next = (status.progress || {}).next || null;
  const anchor = next ? next.anchor : null;
  const primary = anchor === "action:verify" ? "verify" : anchor === "action:test" ? "test" : anchor === "action:inbox" && asking ? "inbox" : null;
  const blocked = dirty || cannotSend;
  const describedBy = dirty ? DIRTY_HINT_ID : undefined;

  const record = useMutation({
    mutationFn: (received) => api("/api/admin/mail/inbox-confirm", { method: "POST", body: { delivery_id: test.id, received } }),
    onSuccess: (res, received) => {
      if (res && res.status) qc.setQueryData(STATUS_KEY, res.status);
      else qc.invalidateQueries({ queryKey: STATUS_KEY });
      toast(received ? "받은 편지함 확인을 기록했습니다. 메일 설정이 끝났습니다." : "받지 못했다고 기록했습니다. 진단을 확인하세요.",
        received ? "success" : "info");
    },
  });
  const recordError = failureText([record, "받은 편지함 확인을 기록하지 못했습니다."]);

  let inboxValue;
  if (asking) {
    inboxValue = `${fmtDateTime(test.sent_at || test.created_at)}에 보낸 시험 메일을 ${remote === "delivered" ? "받는 쪽 메일 서버로 전달했습니다" : "메일 서버가 접수했습니다"}. 받은 편지함(정크함 포함)에서 확인했습니까?`;
  } else if (recorded) {
    inboxValue = (
      <ValueLine word={inbox.received ? "받았다고 기록함" : "받지 못했다고 기록함"} tone={inbox.received ? "ok" : "warn"}
        rest={inbox.at ? fmtListStamp(inbox.at) : null} />
    );
  } else if (rejected) {
    inboxValue = "수신측이 시험 메일을 거부해 받은 편지함을 확인할 수 없습니다. 문제 해결의 요청문을 담당자에게 보내세요.";
  } else if (test && (["queued", "retrying"].includes(test.status) || remote === "deferred")) {
    inboxValue = "시험 메일이 아직 전달되는 중입니다.";
  } else {
    inboxValue = "시험 메일이 받는 쪽까지 간 뒤에 기록할 수 있습니다.";
  }
  const showDiagnosis = relayLocal && onOpenAdvanced && (rejected || (recorded && !inbox.received));
  /* 아직 결과가 없는 줄의 문장은 흐린 글자다 — 결과(점 + 낱말)와 묻는 문장만 진한 글자로 선다. */
  const verifyShown = verifyValue(h, verifying);
  const testShown = testValue(test, checks.testWaiting);
  const muted = (v) => (typeof v === "string" ? "muted" : undefined);
  let inboxAction = null;
  if (operate && asking) {
    inboxAction = (
      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
        <Button variant={primary === "inbox" ? "primary" : undefined} loading={record.isPending} onClick={() => record.mutate(true)}>받았습니다</Button>
        <Button disabled={record.isPending} onClick={() => record.mutate(false)}>못 받았습니다</Button>
      </Box>
    );
  } else if (showDiagnosis) {
    inboxAction = <Button onClick={onOpenAdvanced}>진단 보기</Button>;
  }

  return (
    <FormSection titleAs="h2" title={<SectionTitleText id={SECTION_IDS.checks}>연결과 발송 확인</SectionTitleText>}>
      {operate && dirty ? (
        <Typography id={DIRTY_HINT_ID} variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>저장한 뒤에 확인할 수 있습니다.</Typography>
      ) : null}
      {checks.problem ? <Callout tone="danger" compact>{checks.problem}</Callout> : null}
      {recordError ? <Callout tone="danger" compact>{recordError}</Callout> : null}
      <Box sx={{ minWidth: 0 }}>
        <Box data-check-row="verify">
          <SettingRow
            label="연결 확인" value={verifyShown} tone={muted(verifyShown)}
            description="메일은 보내지 않고 서버 연결과 로그인까지 확인합니다."
            action={operate ? (
              <Button variant={primary === "verify" ? "primary" : undefined} loading={verifying} disabled={blocked}
                aria-describedby={describedBy} onClick={checks.onVerify}>
                연결 확인
              </Button>
            ) : null}
          />
        </Box>
        <Box data-check-row="test">
          <SettingRow
            label="시험 메일" value={testShown} tone={muted(testShown)}
            description="받는 주소를 정해 시험 메일 한 통을 보냅니다. 메일 서버가 접수했는지까지 확인합니다."
            action={operate ? (
              <Button variant={primary === "test" ? "primary" : undefined} loading={Boolean(checks.testWaiting)} disabled={blocked}
                aria-describedby={describedBy} onClick={checks.onTest}>
                시험 메일 보내기
              </Button>
            ) : null}
          />
        </Box>
        <Box data-check-row="inbox" data-testid={asking && operate ? "mail-inbox-confirm" : undefined}>
          <SettingRow
            last label="받은 편지함 확인" value={inboxValue} tone={asking ? undefined : muted(inboxValue)}
            description="메일이 받은 편지함에 들어갔는지는 받는 사람만 알 수 있어 직접 확인한 결과를 기록합니다."
            action={inboxAction}
          />
        </Box>
      </Box>
    </FormSection>
  );
}

/* ⑤ 문제 해결과 고급 — 구획 머리는 접기의 단추이고, 그 단추를 h2 가 감싼다(`Disclosure titleAs`, P-137).
   위 구획과는 선 하나로 갈린다(구획 머리의 선과 같은 선이다). */
function AdvancedSection({ open, onToggle, summary, children }) {
  return (
    <Box
      component="section" id={SECTION_IDS.advanced} aria-labelledby="mail-advanced-title"
      sx={{ minWidth: 0, borderTop: 1, borderColor: "rule", pt: 1.5 }}
    >
      <Disclosure id="mail-advanced" title="문제 해결과 고급" titleAs="h2" titleId="mail-advanced-title"
        summary={summary} open={open} onToggle={onToggle}>
        <Box sx={{ display: "grid", gap: 3, minWidth: 0 }}>{children}</Box>
      </Disclosure>
    </Box>
  );
}

function hasIconHelp(help) {
  return Boolean(help && Array.isArray(help.inbox_icon) && help.inbox_icon.length);
}

function EditableSettings({ status, verify, onDirtyChange, checks }) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const query = useQuery({ queryKey: MAIL_SETTINGS_KEY, queryFn: () => api("/api/admin/mail/settings") });
  const [draft, setDraft] = React.useState({});
  const [password, setPassword] = React.useState("");
  const [clearPassword, setClearPassword] = React.useState(false);
  const [relayPassword, setRelayPassword] = React.useState("");
  const [clearRelayPassword, setClearRelayPassword] = React.useState(false);
  const [presetKey, setPresetKey] = React.useState(null);
  const [advancedOpen, setAdvancedOpen] = React.useState(false);
  const openAdvanced = React.useCallback(() => setAdvancedOpen(true), []);
  const jump = useSectionJump(openAdvanced);
  const check = useReadinessCheck();

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
      qc.invalidateQueries({ queryKey: STATUS_KEY });
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
  const savedLocal = base.mode === "local_relay";
  const relay = relayQuery.data || null;
  const relaySummary = local ? readinessSummary(relay && relay.readiness) : null;
  let advancedSummary;
  if (check.running) advancedSummary = "바깥으로 보내기 준비를 점검하는 중입니다.";
  else if (local && relaySummary) advancedSummary = <span data-testid="relay-summary">{relaySummary}</span>;
  else if (local && relay) advancedSummary = "아직 바깥으로 보내기 준비를 점검하지 않았습니다.";
  else if (local) advancedSummary = null;
  else advancedSummary = hasIconHelp(status.help)
    ? "받은 편지함 아이콘 조건을 보고 사설 CA 인증서와 응답 대기 시간을 정합니다."
    : "사설 CA 인증서와 응답 대기 시간을 정합니다.";

  return (
    <RelayVerifyContext.Provider value={verify}>
      <MailStatusCard
        health={status.health} summary={status.summary} relay={status.relay} checking={verify && verify.waiting}
        timedOut={verify && verify.timedOut} progress={status.progress} latestTest={status.latest_test} inbox={status.inbox} onGo={jump}
      />
      {status.base_url && status.base_url.problem ? <Callout tone="warn" compact>{status.base_url.problem}</Callout> : null}

      {/* 발이 긴 폼에서 창 아래에 따라오도록(`ActionFooter sticky`) 판은 넘침을 자르지 않는다 - MUI Card 뿌리의 `overflow: hidden`
          이 판을 스크롤 창으로 만들면 발이 판 안에서만 움직이고 끝까지 굴렸을 때 마지막 단추를 덮었다(P12 실측 4px). */}
      <Card stack data-testid="mail-settings-form" sx={{ overflow: "visible" }}>
        <FormSection titleAs="h2" title={<SectionTitleText id={SECTION_IDS.basics}>기본 설정</SectionTitleText>}>
          <SettingRows>
            <SettingRow
              compact label="메일 발송 사용" controlId="mail-enabled"
              description="끄면 ClovirAssist 가 메일을 보내지 않습니다. 저장해야 적용됩니다."
              action={(
                <Checkbox id="mail-enabled" checked={Boolean(values.enabled)} onChange={(e) => set({ enabled: e.target.checked })}
                  slotProps={{ input: { "aria-label": "메일 발송 사용" } }} />
              )}
            />
          </SettingRows>
          {/* 로컬 릴레이가 먼저다(D-560) - 설치에 포함된 구성 요소라 계정이 필요 없다. */}
          <Field label="보내는 방법" labelId="mail-mode-label"
            help="메일 계정이 없어도 로컬 릴레이로 보낼 수 있습니다. 회사 계정이나 Gmail 같은 외부 계정이 있으면 외부 SMTP 를 고릅니다.">
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
          </Field>
          <FieldRow>
            <Field span={FIELD_SPAN.half} label="보내는 주소" htmlFor="mail-from" required={!off}
              help={presetInfo && presetInfo.from_note && !local ? presetInfo.from_note : "받는 사람이 보는 주소입니다."}>
              <TextField id="mail-from" size="small" fullWidth value={values.from_address}
                onChange={(e) => set({ from_address: e.target.value })} placeholder="noreply@example.com"
                inputProps={{ spellCheck: false, autoComplete: "off" }} />
            </Field>
            <Field span={FIELD_SPAN.half} label="보내는 이름" htmlFor="mail-from-name" help="비우면 주소만 보입니다.">
              <TextField id="mail-from-name" size="small" fullWidth value={values.from_name}
                onChange={(e) => set({ from_name: e.target.value })} placeholder="ClovirAssist" />
            </Field>
          </FieldRow>
        </FormSection>

        <FormSection
          titleAs="h2" title={<SectionTitleText id={SECTION_IDS.method}>전달 방법 설정</SectionTitleText>}
          description={local
            ? "로컬 릴레이가 메일을 어디로 넘길지 정합니다."
            : "메일 서비스를 고르면 서버 값이 채워집니다. 계정과 비밀번호만 넣으면 됩니다."}
        >
          {local ? (
            <>
              <RelayFields
                values={values} setRelay={setRelay} relay={relay} savedLocal={savedLocal} dirty={dirty}
                relayPassword={relayPassword} setRelayPassword={setRelayPassword} clearRelayPassword={clearRelayPassword}
                setClearRelayPassword={setClearRelayPassword} relayPasswordStored={relayPasswordStored}
              />
              {relayQuery.isError ? <ErrorState error={relayQuery.error} onRetry={relayQuery.refetch} /> : null}
            </>
          ) : (
            <>
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
              <FieldRow>
                <Field span={FIELD_SPAN.server} label="서버 주소" htmlFor="mail-host" required={!off}>
                  <TextField id="mail-host" size="small" fullWidth value={values.host}
                    onChange={(e) => { set({ host: e.target.value }); setPresetKey(null); }} placeholder="smtp.example.com"
                    inputProps={{ spellCheck: false, autoComplete: "off" }} />
                </Field>
                <Field span={FIELD_SPAN.security} label="보안 연결" labelId="mail-security-label">
                  <TextField id="mail-security" select size="small" fullWidth value={values.security}
                    SelectProps={{ labelId: "mail-security-label" }}
                    onChange={(e) => changeSecurity(e.target.value)}>
                    {SECURITY.map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
                  </TextField>
                </Field>
                <Field span={FIELD_SPAN.port} label="포트" htmlFor="mail-port">
                  <TextField id="mail-port" size="small" type="number" fullWidth value={values.port}
                    onChange={(e) => set({ port: e.target.value })} inputProps={{ min: 1, max: 65535 }} />
                </Field>
              </FieldRow>
              <FieldRow>
                <Field span={FIELD_SPAN.half} label="계정" htmlFor="mail-username"
                  help={preset !== PRESET_CUSTOM ? "그 서비스에 로그인하는 메일 주소입니다." : "계정이 없는 사내 중계라면 계정과 비밀번호를 비워 둡니다."}>
                  <TextField id="mail-username" size="small" fullWidth value={values.username}
                    onChange={(e) => set({ username: e.target.value })} inputProps={{ spellCheck: false, autoComplete: "off" }} />
                </Field>
                <Field span={FIELD_SPAN.half}
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
              <SettingRows>
                <SettingRow
                  compact label="서버 인증서 확인" controlId="mail-tls-verify"
                  description={values.security === "none"
                    ? "보안 연결을 쓰지 않아 인증서를 확인하지 않습니다."
                    : "끄면 중간에서 메일과 로그인 비밀번호를 가로챌 수 있습니다. 사설 인증서는 문제 해결과 고급에 CA 를 넣으세요."}
                  action={(
                    <Checkbox id="mail-tls-verify" checked={values.tls_verify !== false} disabled={values.security === "none"}
                      onChange={(e) => set({ tls_verify: e.target.checked })}
                      slotProps={{ input: { "aria-label": "서버 인증서 확인" } }} />
                  )}
                />
              </SettingRows>
            </>
          )}
        </FormSection>

        <MailChecks
          status={status} checks={checks} verify={verify} dirty={dirty} relayLocal={local && savedLocal}
          onOpenAdvanced={() => jump({ anchor: "section:advanced" })}
        />

        <AdvancedSection open={advancedOpen} onToggle={setAdvancedOpen} summary={advancedSummary}>
          {local ? <RelayReadiness relay={relay} savedLocal={savedLocal} dirty={dirty} check={check} /> : null}
          <InboxIconHelp help={status.help} />
          <Box component="section" aria-labelledby="mail-advanced-fields-title" sx={{ display: "grid", gap: 2, minWidth: 0 }}>
            <SubHeading id="mail-advanced-fields-title">고급 설정</SubHeading>
            {local ? <RelayAdvancedFields values={values} setRelay={setRelay} /> : (
              <>
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
              </>
            )}
          </Box>
        </AdvancedSection>

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

function ReadOnlyValue({ label, value, span }) {
  return (
    <Field label={label} span={span}>
      <Typography sx={{ minHeight: 34, display: "flex", alignItems: "center", ...KO_WORD_BREAK }}>{value || "-"}</Typography>
    </Field>
  );
}

function ReadOnlySettings({ status, verify, checks }) {
  const s = status.summary || {};
  const relay = s.relay || {};
  const sh = relay.smarthost || {};
  const local = s.mode === "local_relay";
  const direct = relay.delivery === "direct";
  const securityLabel = Object.fromEntries(SECURITY)[s.security] || s.security;
  const [advancedOpen, setAdvancedOpen] = React.useState(false);
  const openAdvanced = React.useCallback(() => setAdvancedOpen(true), []);
  const jump = useSectionJump(openAdvanced);
  const overrides = relay.transport_overrides || [];
  return (
    <>
      <MailStatusCard
        health={status.health} summary={s} relay={status.relay} checking={verify && verify.waiting}
        timedOut={verify && verify.timedOut} progress={status.progress} latestTest={status.latest_test} inbox={status.inbox} onGo={jump}
      />
      <Card stack data-testid="mail-settings-readonly">
        <Callout tone="info" compact>메일 서버 설정은 시스템 관리자만 바꿀 수 있습니다.</Callout>
        <FormSection titleAs="h2" title={<SectionTitleText id={SECTION_IDS.basics}>기본 설정</SectionTitleText>}>
          <FieldRow>
            <ReadOnlyValue span={FIELD_SPAN.half} label="메일 발송" value={s.enabled ? "사용" : "사용 안 함"} />
            <ReadOnlyValue span={FIELD_SPAN.half} label="보내는 방법" value={local ? "ClovirAssist 로컬 릴레이" : "외부 SMTP 사용"} />
          </FieldRow>
          <FieldRow>
            <ReadOnlyValue span={FIELD_SPAN.half} label="보내는 주소" value={s.from_address} />
            <ReadOnlyValue span={FIELD_SPAN.half} label="보내는 이름" value={s.from_name} />
          </FieldRow>
        </FormSection>
        <FormSection titleAs="h2" title={<SectionTitleText id={SECTION_IDS.method}>전달 방법 설정</SectionTitleText>}>
          {local ? (
            <>
              <RelayReadOnly summary={s} />
              {direct ? (
                <FieldRow>
                  <ReadOnlyValue span={FIELD_SPAN.main} label="서버 이름(HELO)" value={relay.helo_name} />
                  <ReadOnlyValue span={FIELD_SPAN.side} label="DKIM 서명" value={relay.dkim_enabled ? `사용, 선택자 ${relay.dkim_selector || "-"}` : "사용 안 함"} />
                </FieldRow>
              ) : (
                <FieldRow>
                  <ReadOnlyValue span={FIELD_SPAN.main} label="상위 SMTP 서버" value={sh.host ? `${sh.host}:${sh.port}` : ""} />
                  <ReadOnlyValue span={FIELD_SPAN.side} label="계정" value={sh.username || "사용 안 함"} />
                </FieldRow>
              )}
            </>
          ) : (
            <>
              <FieldRow>
                <ReadOnlyValue span={FIELD_SPAN.server} label="서버 주소" value={s.host} />
                <ReadOnlyValue span={FIELD_SPAN.security} label="보안 연결" value={securityLabel} />
                <ReadOnlyValue span={FIELD_SPAN.port} label="포트" value={s.port != null ? String(s.port) : ""} />
              </FieldRow>
              <FieldRow>
                <ReadOnlyValue span={FIELD_SPAN.half} label="계정" value={s.username || "사용 안 함"} />
                <ReadOnlyValue span={FIELD_SPAN.half} label="비밀번호" value={!s.username ? "사용 안 함" : (s.password && s.password.stored ? "저장됨" : "저장되지 않음")} />
              </FieldRow>
              <ReadOnlyValue label="서버 인증서 확인" value={s.security === "none" ? "보안 연결 없음" : (s.tls_verify === false ? "확인 안 함" : "확인함")} />
            </>
          )}
        </FormSection>
        <MailChecks status={status} checks={checks} verify={verify} dirty={false} relayLocal={false} />
        <AdvancedSection
          open={advancedOpen} onToggle={setAdvancedOpen}
          summary={local ? "비교할 공개 DNS 와 받는 도메인별 전달 서버를 봅니다." : "사설 CA 인증서와 응답 대기 시간을 봅니다."}
        >
          <InboxIconHelp help={status.help} />
          <Box component="section" aria-labelledby="mail-advanced-fields-title" sx={{ display: "grid", gap: 2, minWidth: 0 }}>
            <SubHeading id="mail-advanced-fields-title">고급 설정</SubHeading>
            {local ? (
              <FieldRow>
                <ReadOnlyValue span={FIELD_SPAN.half} label="비교할 공개 DNS 서버" value={(relay.compare_resolvers || []).join(", ") || "없음"} />
                {direct ? <ReadOnlyValue span={FIELD_SPAN.half} label="받는 도메인별 전달 서버" value={overrides.length ? `${overrides.length}개` : "없음"} /> : null}
              </FieldRow>
            ) : (
              <FieldRow>
                <ReadOnlyValue span={FIELD_SPAN.half} label="사설 CA 인증서" value={s.ca_pem_set ? "붙여 넣음" : "없음"} />
                <ReadOnlyValue span={FIELD_SPAN.half} label="응답 대기 시간" value={s.timeout_seconds != null ? `${s.timeout_seconds}초` : ""} />
              </FieldRow>
            )}
          </Box>
        </AdvancedSection>
      </Card>
    </>
  );
}

export default MailSettingsTab;
