import React from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { failureText } from "../../lib/failure.js";
import { fmtDateTime } from "../../lib/format.js";
import { copyText } from "../ops/opsHelpers.js";
import {
  Badge, Button, Callout, FieldLabel, Modal, Segmented, TechDetail, useConfirm, useToast,
} from "../../ui/kit.jsx";
import { KO_WORD_BREAK } from "../../ui/theme.js";

/* ChatGPT 계정 연결 (계획 3.14 · 3.15, D-516) — AI 설정 화면의 인증 칸이 「ChatGPT 계정」일 때 선다.
 *
 * 공식 「Sign in with ChatGPT」는 로그인 결과를 http://127.0.0.1:<포트>/auth/callback 으로만 돌려준다. 그 주소는 이
 * 브라우저가 도는 PC 라서 원격 서버의 화면만으로는 받을 수 없다. 그래서 순서가 셋이다:
 *   ① 이 화면에서 「Continue with ChatGPT」 ② 안내한 명령으로 이 PC 에서 연결 도우미를 한 번 실행한다(브라우저가
 *   ChatGPT 승인 화면을 연다) ③ 승인하면 이 창이 저절로 「연결됨」으로 바뀐다.
 * 도우미는 콜백 주소만 서버에 넘긴다. 토큰은 서버가 받고 이 화면에는 오지 않는다.
 *
 * 공식 화면 지침의 문구(버튼 이름, 첫 연결 안내, 「Using ChatGPT plan」, 「Manage usage」)는 원문 그대로 쓴다.
 */

const POLL_MS = 1500;
const NOTICE_KEY = "clovirassist.chatgpt-plan-notice";
const OS_OPTIONS = [
  { value: "windows", label: "Windows" },
  { value: "unix", label: "macOS와 Linux" },
];
const PHASE_KIND = { waiting_helper: "info", browser: "info", done: "ok", failed: "error" };
const PHASE_LABEL = {
  waiting_helper: "도우미를 기다리는 중", browser: "브라우저 승인을 기다리는 중", done: "연결됨", failed: "실패",
};

function guessOs() {
  try {
    const ua = (navigator.userAgent || "").toLowerCase();
    return ua.includes("windows") ? "windows" : "unix";
  } catch (e) {
    return "windows";
  }
}

function noticeSeen() {
  try { return window.localStorage.getItem(NOTICE_KEY) === "1"; } catch (e) { return false; }
}

function markNoticeSeen() {
  try { window.localStorage.setItem(NOTICE_KEY, "1"); } catch (e) { /* 저장할 수 없는 브라우저는 다음에 한 번 더 보인다 */ }
}

/* 공식 로고. 공식 파일(chatgpt-logo-white.svg)의 모양을 그대로 두고 색만 글자색을 따른다. */
export function ChatGptLogo({ size = 18 }) {
  return (
    <Box component="svg" viewBox="0 0 21 21" aria-hidden="true" focusable="false" sx={{ width: size, height: size, flex: "none" }}>
      <path fill="currentColor" d="M11.8102 19.1625C11.2327 19.1625 10.6841 19.0528 10.1643 18.8334C9.64459 18.6139 9.18259 18.3078 8.77834 17.9151C8.33944 18.0653 7.88322 18.1404 7.40967 18.1404C6.63582 18.1404 5.91972 17.9498 5.26137 17.5686C4.60302 17.1875 4.07172 16.6677 3.66747 16.0094C3.27477 15.351 3.07842 14.6176 3.07842 13.8091C3.07842 13.4742 3.12462 13.1103 3.21702 12.7176C2.75502 12.2903 2.39697 11.7994 2.14287 11.245C1.88877 10.679 1.76172 10.09 1.76172 9.47785C1.76172 8.85415 1.89454 8.25355 2.16019 7.67605C2.42584 7.09855 2.79544 6.6019 3.26899 6.1861C3.75409 5.75875 4.31427 5.46422 4.94952 5.30252C5.07657 4.64417 5.34222 4.05512 5.74647 3.53537C6.16227 3.00407 6.67047 2.58827 7.27107 2.28797C7.87167 1.98767 8.51269 1.83752 9.19414 1.83752C9.77164 1.83752 10.3203 1.94725 10.84 2.1667C11.3598 2.38615 11.8218 2.69222 12.226 3.08492C12.6649 2.93477 13.1211 2.8597 13.5947 2.8597C14.3685 2.8597 15.0846 3.05027 15.743 3.43142C16.4013 3.81257 16.9269 4.33232 17.3196 4.99067C17.7238 5.64902 17.9259 6.38245 17.9259 7.19095C17.9259 7.5259 17.8797 7.88973 17.7873 8.28242C18.2493 8.70977 18.6074 9.20643 18.8615 9.77238C19.1156 10.3268 19.2426 10.91 19.2426 11.5222C19.2426 12.1459 19.1098 12.7465 18.8442 13.324C18.5785 13.9015 18.2031 14.4039 17.718 14.8313C17.2445 15.2471 16.6901 15.5358 16.0548 15.6975C15.9278 16.3559 15.6564 16.9449 15.2406 17.4647C14.8363 17.996 14.3339 18.4118 13.7333 18.7121C13.1327 19.0124 12.4917 19.1625 11.8102 19.1625ZM7.53094 16.9969C8.10844 16.9969 8.61087 16.8756 9.03822 16.6331L12.2953 14.762C12.4108 14.6811 12.4686 14.5714 12.4686 14.4328V12.9429L8.27592 15.351C8.02182 15.5012 7.76772 15.5012 7.51362 15.351L4.23919 13.4626C4.23919 13.4973 4.23342 13.5377 4.22187 13.5839C4.22187 13.6301 4.22187 13.6994 4.22187 13.7918C4.22187 14.3808 4.36047 14.9237 4.63767 15.4203C4.92642 15.9054 5.32489 16.2866 5.83309 16.5638C6.34129 16.8525 6.90724 16.9969 7.53094 16.9969ZM7.70419 14.1729C7.77349 14.2076 7.83702 14.2249 7.89477 14.2249C7.95252 14.2249 8.01027 14.2076 8.06802 14.1729L9.36739 13.4279L5.19207 11.0024C4.93797 10.8523 4.81092 10.6271 4.81092 10.3268V6.56725C4.23342 6.82135 3.77142 7.21405 3.42492 7.74535C3.07842 8.2651 2.90517 8.8426 2.90517 9.47785C2.90517 10.0438 3.04954 10.5866 3.33829 11.1064C3.62704 11.6261 4.00242 12.0189 4.46442 12.2845L7.70419 14.1729ZM11.8102 18.0191C12.4224 18.0191 12.9768 17.8805 13.4734 17.6033C13.9701 17.3261 14.3628 16.9449 14.6515 16.4598C14.9403 15.9747 15.0846 15.4319 15.0846 14.8313V11.0891C15.0846 10.9505 15.0269 10.8465 14.9114 10.7772L13.5947 10.0149V14.8486C13.5947 15.1489 13.4676 15.3741 13.2135 15.5243L9.93912 17.4127C10.5051 17.817 11.1288 18.0191 11.8102 18.0191ZM12.4686 11.6781V9.32192L10.5108 8.21312L8.53579 9.32192V11.6781L10.5108 12.7869L12.4686 11.6781ZM7.40967 6.15145C7.40967 5.85115 7.53672 5.62592 7.79082 5.47577L11.0652 3.58735C10.4993 3.1831 9.87559 2.98097 9.19414 2.98097C8.58199 2.98097 8.02759 3.11957 7.53094 3.39677C7.03429 3.67397 6.64159 4.05512 6.35284 4.54022C6.07564 5.02532 5.93704 5.56817 5.93704 6.16878V9.89365C5.93704 10.0323 5.99479 10.142 6.11029 10.2228L7.40967 10.9851V6.15145ZM16.2108 14.4328C16.7883 14.1787 17.2445 13.786 17.5794 13.2547C17.9259 12.7234 18.0992 12.1459 18.0992 11.5222C18.0992 10.9562 17.9548 10.4134 17.6661 9.89365C17.3773 9.3739 17.0019 8.9812 16.5399 8.71555L13.3002 6.84445C13.2309 6.79825 13.1673 6.78092 13.1096 6.79248C13.0518 6.79248 12.9941 6.8098 12.9363 6.84445L11.637 7.5721L15.8296 10.0149C15.9567 10.0842 16.0491 10.1766 16.1068 10.2921C16.1761 10.3961 16.2108 10.5231 16.2108 10.6733V14.4328ZM12.7284 5.6317C12.9825 5.47 13.2366 5.47 13.4907 5.6317L16.7825 7.55477C16.7825 7.47393 16.7825 7.36997 16.7825 7.24292C16.7825 6.68852 16.6439 6.163 16.3667 5.66635C16.101 5.15815 15.7141 4.7539 15.2059 4.4536C14.7093 4.1533 14.1318 4.00315 13.4734 4.00315C12.8959 4.00315 12.3935 4.12442 11.9661 4.36697L8.70904 6.23808C8.59354 6.31892 8.53579 6.42865 8.53579 6.56725V8.0572L12.7284 5.6317Z" />
    </Box>
  );
}

export function ContinueWithChatGpt({ onClick, disabled }) {
  return (
    <Button onClick={onClick} disabled={disabled} sx={{ gap: 1 }}>
      <ChatGptLogo />
      Continue with ChatGPT
    </Button>
  );
}

function CommandBox({ command, onCopy }) {
  return (
    <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start", minWidth: 0 }}>
      <TextField
        value={command} size="small" fullWidth multiline minRows={2}
        inputProps={{ readOnly: true, "aria-label": "실행할 명령", spellCheck: false, style: { fontFamily: "monospace", wordBreak: "break-all" } }}
      />
      <Button onClick={onCopy}>복사</Button>
    </Box>
  );
}

/* 연결 창 — 시작하면 곧바로 서버에 연결 시도를 만들고, 끝날 때까지 단계를 묻는다. */
export function ChatGptConnectDialog({ open, onClose, onConnected }) {
  const toast = useToast();
  const [os, setOs] = React.useState(guessOs);
  const [manualUrl, setManualUrl] = React.useState("");
  const [authorizeUrl, setAuthorizeUrl] = React.useState(null);
  const [showNotice, setShowNotice] = React.useState(false);
  const start = useMutation({ mutationFn: () => api("/api/admin/ai/oauth/openai/start", { method: "POST" }) });
  const txId = start.data && start.data.transaction_id;
  const poll = useQuery({
    queryKey: ["ai-oauth", txId],
    queryFn: () => api("/api/admin/ai/oauth/openai/transactions/" + txId),
    enabled: open && !!txId,
    refetchInterval: (q) => {
      const phase = q.state.data && q.state.data.phase;
      return phase === "done" || phase === "failed" ? false : POLL_MS;
    },
  });
  const manual = useMutation({
    mutationFn: () => api("/api/admin/ai/oauth/openai/transactions/" + txId + "/manual", { method: "POST" }),
    onSuccess: (res) => {
      setAuthorizeUrl(res && res.authorize_url);
      if (res && res.authorize_url) window.open(res.authorize_url, "_blank", "noopener");
    },
  });
  const finishManual = useMutation({
    mutationFn: () => api("/api/admin/ai/oauth/openai/transactions/" + txId + "/complete", {
      method: "POST", body: { callback_url: manualUrl },
    }),
    onSuccess: () => poll.refetch(),
  });

  const startRef = React.useRef(start);
  startRef.current = start;
  React.useEffect(() => {
    if (open) {
      setManualUrl("");
      setAuthorizeUrl(null);
      setShowNotice(false);
      startRef.current.mutate();
    }
  }, [open]);

  const view = poll.data || start.data || null;
  const phase = view && view.phase;
  const finished = React.useRef(null);
  React.useEffect(() => {
    if (phase !== "done" || !txId || finished.current === txId) return;
    finished.current = txId;
    onConnected && onConnected();
    if (noticeSeen()) {
      toast("ChatGPT 계정을 연결했습니다.", "success");
      onClose();
    } else {
      setShowNotice(true);
    }
  }, [phase, txId, onConnected, onClose, toast]);

  const commands = (start.data && start.data.commands) || {};
  const downloads = (start.data && start.data.downloads) || [];
  const download = downloads.find((d) => (os === "windows" ? d.name.endsWith(".ps1") : d.name.endsWith(".py")));
  const failure = failureText([start, "연결을 시작하지 못했습니다."])
    || failureText([manual, "인가 주소를 받지 못했습니다."])
    || failureText([finishManual, "붙여 넣은 주소로 연결하지 못했습니다."])
    || (phase === "failed" ? view.message : null);

  const copy = () => copyText(commands[os] || "").then((ok) => toast(
    ok ? "명령을 복사했습니다." : "복사를 지원하지 않는 환경입니다. 명령을 직접 선택해 복사하세요.", ok ? "success" : "info",
  ));
  const close = () => { onClose(); };

  if (showNotice) {
    return (
      <Modal open={open} onClose={() => { markNoticeSeen(); close(); }} title="You're using your ChatGPT plan" size="sm"
        footer={<Button variant="primary" onClick={() => { markNoticeSeen(); close(); }}>Got it</Button>}
      >
        <Typography variant="body2" sx={KO_WORD_BREAK}>
          Eligible usage in this app uses your ChatGPT plan. Manage usage in your ChatGPT settings.
        </Typography>
      </Modal>
    );
  }

  return (
    <Modal open={open} onClose={close} title="ChatGPT 계정 연결" size="md"
      footer={<Button onClick={close}>{phase === "done" ? "닫기" : "취소"}</Button>}
    >
      <Typography variant="body2" sx={{ ...KO_WORD_BREAK, mb: 2 }}>
        브라우저가 있는 이 PC 에서 연결 도우미를 한 번 실행합니다. 도우미는 ChatGPT 가 돌려주는 주소만 서버에 넘기고, 토큰은 서버가 직접 받습니다.
      </Typography>
      <Segmented value={os} onChange={setOs} options={OS_OPTIONS} ariaLabel="이 PC 의 운영체제" />
      <Box sx={{ mt: 2, display: "grid", gap: 2 }}>
        <Box>
          <FieldLabel>1. 도우미 내려받기</FieldLabel>
          {download ? (
            <>
              <Button component="a" href={download.href} download={download.name}>{download.name} 내려받기</Button>
              {download.sha256 ? (
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5, wordBreak: "break-all" }}>
                  파일의 sha256 지문은 {download.sha256}입니다.
                </Typography>
              ) : null}
            </>
          ) : (
            <Typography variant="body2" color="text.secondary">연결을 준비하고 있습니다.</Typography>
          )}
        </Box>
        <Box>
          <FieldLabel>{os === "windows" ? "2. PowerShell 에 붙여 넣어 실행하기" : "2. 터미널에 붙여 넣어 실행하기"}</FieldLabel>
          {commands[os] ? <CommandBox command={commands[os]} onCopy={copy} /> : null}
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5, ...KO_WORD_BREAK }}>
            명령 안의 토큰은 이번 연결에 한 번만 쓰이고 10분 뒤에 사라집니다.
          </Typography>
        </Box>
        <Box data-testid="chatgpt-connect-phase" sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
          <FieldLabel sx={{ m: 0 }}>3. 진행 상황</FieldLabel>
          {phase ? <Badge value={PHASE_LABEL[phase] || phase} kind={PHASE_KIND[phase] || "muted"} /> : null}
          {view && view.message && phase !== "failed" ? (
            <Typography variant="body2" sx={KO_WORD_BREAK}>{view.message}</Typography>
          ) : null}
        </Box>
        {failure ? <Callout tone="danger" compact>{failure}</Callout> : null}
        <TechDetail label="도우미를 실행할 수 없을 때">
          <Typography variant="body2" sx={{ ...KO_WORD_BREAK, mb: 1 }}>
            인가 주소를 열어 승인한 뒤, 브라우저가 연결하지 못한 채 멈춘 http://127.0.0.1 주소를 주소창에서 복사해 붙여 넣습니다.
          </Typography>
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}>
            <Button disabled={!txId || phase === "done" || phase === "failed"} loading={manual.isPending} onClick={() => manual.mutate()}>
              인가 주소 열기
            </Button>
            {authorizeUrl ? (
              <Typography variant="caption" color="text.secondary" sx={{ wordBreak: "break-all" }}>{authorizeUrl}</Typography>
            ) : null}
          </Box>
          <Box sx={{ display: "flex", gap: 1, mt: 1, alignItems: "flex-start" }}>
            <TextField
              size="small" fullWidth value={manualUrl} onChange={(e) => setManualUrl(e.target.value)}
              placeholder="http://127.0.0.1:1455/auth/callback?code=..."
              inputProps={{ "aria-label": "브라우저 주소창의 주소", spellCheck: false }}
            />
            <Button disabled={!authorizeUrl || !manualUrl.trim()} loading={finishManual.isPending} onClick={() => finishManual.mutate()}>
              연결
            </Button>
          </Box>
        </TechDetail>
      </Box>
    </Modal>
  );
}

const TOKEN_FIELDS = [
  ["ai_openai_access_ttl_fallback_seconds", "access token 기본 수명(초)"],
  ["ai_openai_refresh_ttl_fallback_days", "갱신 토큰 기본 수명(일)"],
  ["ai_token_refresh_lead_seconds", "미리 갱신하는 시간(초)"],
];

function TokenDefaults({ values, onSave, saving }) {
  const [draft, setDraft] = React.useState({});
  return (
    <TechDetail label="토큰 수명 기본값">
      <Typography variant="body2" sx={{ ...KO_WORD_BREAK, mb: 1 }}>
        만료 시각은 ChatGPT 가 토큰과 함께 알려 준 값을 씁니다. 아래 값은 그 정보가 없을 때만 씁니다.
      </Typography>
      <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: { xs: "1fr", sm: "repeat(3, minmax(0, 1fr))" } }}>
        {TOKEN_FIELDS.map(([key, label]) => (
          <Box key={key} sx={{ display: "flex", gap: 1, alignItems: "flex-end", minWidth: 0 }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <FieldLabel htmlFor={"ai-token-" + key}>{label}</FieldLabel>
              <TextField
                id={"ai-token-" + key} size="small" type="number" fullWidth
                value={draft[key] ?? values[key] ?? ""}
                onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
              />
            </Box>
            <Button
              disabled={saving || draft[key] === undefined || draft[key] === "" || Number(draft[key]) === values[key]}
              onClick={() => onSave(key, Number(draft[key]), () => setDraft((d) => { const n = { ...d }; delete n[key]; return n; }))}
            >
              저장
            </Button>
          </Box>
        ))}
      </Box>
    </TechDetail>
  );
}

/* 인증 칸 — 연결했으면 누구로 연결했는지와 만료, 아니면 「Continue with ChatGPT」. */
export function ChatGptAccount({ chatgpt, state, tokenSettings, onChanged }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [dialog, setDialog] = React.useState(false);
  const logout = useMutation({
    mutationFn: () => api("/api/admin/ai/oauth/openai/logout", { method: "POST" }),
    onSuccess: (res) => {
      onChanged && onChanged();
      toast((res && res.message) || "ChatGPT 계정 연결을 끊었습니다.", res && res.revoked === false && res.removed ? "info" : "success");
    },
  });
  const saveSetting = useMutation({
    mutationFn: ({ key, value }) => api("/api/admin/settings/" + key, { method: "PUT", body: { value } }),
    onSuccess: (_res, vars) => { vars.done && vars.done(); onChanged && onChanged(); toast("토큰 수명 기본값을 저장했습니다.", "success"); },
    onError: (e) => toast(e.message, "error"),
  });
  const info = chatgpt || {};
  const planLimited = state && state.reason_code === "plan_usage_limit";
  const fallback = typeof info.expiry_source === "string" && info.expiry_source.includes("fallback");

  async function askLogout() {
    const ok = await confirm("이 서버에서 ChatGPT 계정 연결을 끊을까요? 다시 쓰려면 다시 로그인해야 합니다.",
      { danger: true, title: "ChatGPT 계정 연결 끊기", confirmLabel: "연결 끊기" });
    if (ok) logout.mutate();
  }

  return (
    <Box sx={{ display: "grid", gap: 1.5 }}>
      {info.connected ? (
        <>
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
            <Badge value="Using ChatGPT plan" kind="info" />
            {info.account_label ? <Typography variant="body2">{info.account_label}</Typography> : null}
            <Button component="a" href={info.manage_usage_url} target="_blank" rel="noopener noreferrer" variant="ghost">
              Manage usage
            </Button>
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", ...KO_WORD_BREAK }}>
            {info.access_expires_at ? `access token 은 ${fmtDateTime(info.access_expires_at)}에 끝나며 서버가 그 전에 갱신합니다. ` : ""}
            {info.refresh_expires_at ? `다시 로그인하지 않아도 되는 기한은 ${fmtDateTime(info.refresh_expires_at)}입니다. ` : ""}
            {fallback ? "ChatGPT 가 수명을 알려 주지 않은 값은 아래 기본값으로 계산했습니다." : ""}
          </Typography>
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
            <Button onClick={() => setDialog(true)}>다시 로그인</Button>
            <Button variant="ghost" loading={logout.isPending} onClick={askLogout}>로그아웃</Button>
          </Box>
        </>
      ) : (
        <>
          {info.disconnected ? (
            <Callout tone="warn" compact>ChatGPT 계정 연결이 끊겼습니다. 다시 로그인하세요.</Callout>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
              ChatGPT 계정을 아직 연결하지 않았습니다. 연결하면 그 계정의 ChatGPT 요금제로 답을 만듭니다.
            </Typography>
          )}
          <Box><ContinueWithChatGpt onClick={() => setDialog(true)} /></Box>
        </>
      )}
      {planLimited ? (
        <Callout tone="warn" compact
          action={<Button component="a" href={info.manage_usage_url} target="_blank" rel="noopener noreferrer" variant="primary">Manage usage</Button>}
        >
          ChatGPT 요금제 사용량 한도에 닿았습니다. 한도가 풀리면 다음 호출부터 다시 답합니다.
        </Callout>
      ) : null}
      <TokenDefaults
        values={tokenSettings || {}} saving={saveSetting.isPending}
        onSave={(key, value, done) => saveSetting.mutate({ key, value, done })}
      />
      <ChatGptConnectDialog open={dialog} onClose={() => setDialog(false)} onConnected={onChanged} />
    </Box>
  );
}

export default ChatGptAccount;
