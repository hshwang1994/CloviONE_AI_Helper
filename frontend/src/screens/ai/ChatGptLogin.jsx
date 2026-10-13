import React from "react";
import { useMutation } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { failureText } from "../../lib/failure.js";
import { toUTCDate } from "../../lib/format.js";
import { Button, Callout, DotLabel, Field, Modal, useConfirm, useToast } from "../../ui/kit.jsx";
import { FONT_SIZE, KO_WORD_BREAK } from "../../ui/theme.js";

/* ChatGPT 계정 로그인 — 붙여 넣기 흐름 (계획 A3, D-540 · D-566 · P3 ②).
 *
 * 공식 「Sign in with ChatGPT」는 로그인 결과를 http://127.0.0.1:<포트>/auth/callback 으로만 돌려준다. 그 주소는 이 브라우저가
 * 도는 PC 라 원격 서버가 받을 수 없다(서버의 `login_flow.py` 머리말). 그래서 순서가 셋이고, **단추를 누르기 전에** 세 단계가
 * 먼저 선다 — 특히 둘째 단계: 승인 뒤 새 창이 「127.0.0.1 … 연결할 수 없습니다」 오류 화면으로 바뀌는 것이 흐름의 일부라는 것.
 * 사용자가 그 화면을 보고 「연결할 수 없음」으로 읽은 것이 이 화면을 다시 만든 까닭이다.
 *
 * 붙여 넣는 순간 모양 · 이번 시도의 포트 · state 를 맞춰 보고 맞으면 **단추 없이** 바로 완료를 부른다. 틀리면 한 문장이다.
 * 창이 막히면 링크를, 시도가 만료되면 다시 시작을 준다. 새로고침 뒤에도 서버의 `login.open` 으로 붙여 넣기 칸을 되찾는다.
 *
 * 이 방식은 API 키와 같은 정식 방식이라 모든 설치에 보인다(D-566). 연결한 계정 하나의 요금제를 이 설치의 모든 사용자가 함께 쓰므로
 * 그 사실을 시작 전에 한 줄로 말한다. 일반 화면에 PKCE · client id · OAuth · localhost 같은 낱말을 쓰지 않는다(5절). 단추와
 * 첫 연결 안내는 공식 화면 지침의 문구를 그대로 쓴다(「Continue with ChatGPT」, 「You're using your ChatGPT plan」).
 *
 * 응답의 `flow` 가 모양을 정한다. 지금은 `paste` 뿐이고, 공식 지원이 생기면 서버가 `redirect` 를 줄 수 있다 - 그때는 같은
 * 창에서 승인으로 간다(화면을 다시 만들지 않는다).
 */

export const PASTE_STEPS = [
  "「Continue with ChatGPT」를 누르면 새 창(또는 탭)에서 ChatGPT 가 열립니다. 로그인하고 「허용」을 누르세요.",
  "허용하면 그 창이 「127.0.0.1 … 서버에 연결할 수 없습니다」 오류 화면으로 바뀝니다. 승인이 끝났다는 뜻이라 정상입니다. "
  + "그 창의 주소창에서 전체 주소를 복사하세요(Ctrl+L, Ctrl+C).",
  "이 탭으로 돌아와 아래 칸에 붙여 넣으면 바로 연결됩니다.",
];
export const PLAN_NOTICE = "연결한 ChatGPT 계정 하나의 요금제를 이 설치의 모든 사용자가 함께 씁니다. "
  + "사용량은 ChatGPT 설정에서 확인합니다.";
export const WRONG_ATTEMPT = "이번 시도의 주소가 아닙니다. 1부터 다시 하세요.";
export const NOT_A_CALLBACK = "주소가 아닙니다. 주소창의 전체 주소를 복사하세요.";
export const EXPIRED_TEXT = "시도가 만료됐습니다. 다시 시작하세요.";
export const BLOCKED_TEXT = "창이 열리지 않았습니다. 팝업을 허용하거나 이 링크로 여세요.";
export const CONNECTED_LABEL = "ChatGPT 계정으로 연결됨";
const CALLBACK_RE = /^http:\/\/127\.0\.0\.1:\d{2,5}\/auth\/callback\?/;
/* 붙여 넣은 글 안에서 주소만 찾는다 — 오류 화면의 글을 통째로 넣어도 된다. */
const CALLBACK_IN_TEXT_RE = /http:\/\/127\.0\.0\.1:\d{2,5}\/auth\/callback\?[^\s\x22\x27<>]+/;
const NOTICE_KEY = "clovirassist.chatgpt-plan-notice";
/* 글자를 치는 중에 「주소가 아닙니다」가 깜빡이지 않게 - 이만큼은 있어야 주소를 넣으려 했다고 본다. */
const MIN_PASTE_CHARS = 16;

export function looksLikeCallback(text) {
  return CALLBACK_RE.test(String(text || "").trim());
}

function stateOf(url) {
  try {
    return new URL(String(url)).searchParams.get("state") || null;
  } catch (e) {
    return null;
  }
}

/* 붙여 넣은 글을 이번 시도와 맞춰 본다. `{ok, url}` 또는 `{ok:false, note}` (note 가 null 이면 아직 아무 말도 안 한다). */
export function matchAttempt(text, attempt) {
  const raw = String(text || "").trim();
  if (!raw) return { ok: false, note: null };
  const found = raw.match(CALLBACK_IN_TEXT_RE);
  const trimmed = found ? found[0] : raw;
  if (!looksLikeCallback(trimmed)) {
    return { ok: false, note: raw.length >= MIN_PASTE_CHARS ? NOT_A_CALLBACK : null };
  }
  const expected = attempt && attempt.redirect_uri;
  if (expected && !trimmed.startsWith(`${expected}?`)) return { ok: false, note: WRONG_ATTEMPT };
  const want = attempt ? stateOf(attempt.authorize_url) : null;
  const got = stateOf(trimmed);
  if (want && got && want !== got) return { ok: false, note: WRONG_ATTEMPT };
  return { ok: true, url: trimmed };
}

function noticeSeen() {
  try { return window.localStorage.getItem(NOTICE_KEY) === "1"; } catch (e) { return false; }
}

function markNoticeSeen() {
  try { window.localStorage.setItem(NOTICE_KEY, "1"); } catch (e) { /* 저장할 수 없는 브라우저는 다음에 한 번 더 보인다 */ }
}

/* 같은 클릭 안에서 빈 새 창을 연다 — 응답을 기다린 뒤에 열면 팝업 차단기에 걸린다. 그 창의 opener 는 끊는다(새 창이 이 화면을
   조작하지 못하게). `noopener` 를 열 때 주면 창 참조가 null 이라 주소를 옮길 수 없어 열고 나서 끊는다. */
export function openBlankWindow() {
  let win = null;
  try {
    win = window.open("about:blank", "_blank");
  } catch (e) {
    win = null;
  }
  if (win) {
    try { win.opener = null; } catch (e) { /* 끊을 수 없는 창은 그대로 둔다 */ }
  }
  return win;
}

/* 남은 시간(초). 만료 시각이 없으면 null. 1초마다 다시 센다. */
export function useCountdown(expiresAt) {
  const compute = React.useCallback(() => {
    if (!expiresAt) return null;
    /* 서버는 UTC 를 Z 없이 준다(`iso_dt` 규약). 그대로 Date.parse 하면 브라우저가 지역 시각으로 읽어 한국에서는 9시간 일찍
       「만료」가 됐다(랩 실측 2026-10-13) — 제품의 UTC 파서로 읽는다. */
    const end = toUTCDate(expiresAt);
    if (!end) return null;
    return Math.max(0, Math.floor((end.getTime() - Date.now()) / 1000));
  }, [expiresAt]);
  const [left, setLeft] = React.useState(compute);
  React.useEffect(() => {
    setLeft(compute());
    if (!expiresAt) return undefined;
    const timer = setInterval(() => setLeft(compute()), 1000);
    return () => clearInterval(timer);
  }, [expiresAt, compute]);
  return left;
}

export function fmtLeft(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/* 공식 로고. 공식 파일(chatgpt-logo-white.svg)의 모양을 그대로 두고 색만 글자색을 따른다. */
export function ChatGptLogo({ size = 18 }) {
  return (
    <Box component="svg" viewBox="0 0 21 21" aria-hidden="true" focusable="false" sx={{ width: size, height: size, flex: "none" }}>
      <path fill="currentColor" d="M11.8102 19.1625C11.2327 19.1625 10.6841 19.0528 10.1643 18.8334C9.64459 18.6139 9.18259 18.3078 8.77834 17.9151C8.33944 18.0653 7.88322 18.1404 7.40967 18.1404C6.63582 18.1404 5.91972 17.9498 5.26137 17.5686C4.60302 17.1875 4.07172 16.6677 3.66747 16.0094C3.27477 15.351 3.07842 14.6176 3.07842 13.8091C3.07842 13.4742 3.12462 13.1103 3.21702 12.7176C2.75502 12.2903 2.39697 11.7994 2.14287 11.245C1.88877 10.679 1.76172 10.09 1.76172 9.47785C1.76172 8.85415 1.89454 8.25355 2.16019 7.67605C2.42584 7.09855 2.79544 6.6019 3.26899 6.1861C3.75409 5.75875 4.31427 5.46422 4.94952 5.30252C5.07657 4.64417 5.34222 4.05512 5.74647 3.53537C6.16227 3.00407 6.67047 2.58827 7.27107 2.28797C7.87167 1.98767 8.51269 1.83752 9.19414 1.83752C9.77164 1.83752 10.3203 1.94725 10.84 2.1667C11.3598 2.38615 11.8218 2.69222 12.226 3.08492C12.6649 2.93477 13.1211 2.8597 13.5947 2.8597C14.3685 2.8597 15.0846 3.05027 15.743 3.43142C16.4013 3.81257 16.9269 4.33232 17.3196 4.99067C17.7238 5.64902 17.9259 6.38245 17.9259 7.19095C17.9259 7.5259 17.8797 7.88973 17.7873 8.28242C18.2493 8.70977 18.6074 9.20643 18.8615 9.77238C19.1156 10.3268 19.2426 10.91 19.2426 11.5222C19.2426 12.1459 19.1098 12.7465 18.8442 13.324C18.5785 13.9015 18.2031 14.4039 17.718 14.8313C17.2445 15.2471 16.6901 15.5358 16.0548 15.6975C15.9278 16.3559 15.6564 16.9449 15.2406 17.4647C14.8363 17.996 14.3339 18.4118 13.7333 18.7121C13.1327 19.0124 12.4917 19.1625 11.8102 19.1625ZM7.53094 16.9969C8.10844 16.9969 8.61087 16.8756 9.03822 16.6331L12.2953 14.762C12.4108 14.6811 12.4686 14.5714 12.4686 14.4328V12.9429L8.27592 15.351C8.02182 15.5012 7.76772 15.5012 7.51362 15.351L4.23919 13.4626C4.23919 13.4973 4.23342 13.5377 4.22187 13.5839C4.22187 13.6301 4.22187 13.6994 4.22187 13.7918C4.22187 14.3808 4.36047 14.9237 4.63767 15.4203C4.92642 15.9054 5.32489 16.2866 5.83309 16.5638C6.34129 16.8525 6.90724 16.9969 7.53094 16.9969ZM7.70419 14.1729C7.77349 14.2076 7.83702 14.2249 7.89477 14.2249C7.95252 14.2249 8.01027 14.2076 8.06802 14.1729L9.36739 13.4279L5.19207 11.0024C4.93797 10.8523 4.81092 10.6271 4.81092 10.3268V6.56725C4.23342 6.82135 3.77142 7.21405 3.42492 7.74535C3.07842 8.2651 2.90517 8.8426 2.90517 9.47785C2.90517 10.0438 3.04954 10.5866 3.33829 11.1064C3.62704 11.6261 4.00242 12.0189 4.46442 12.2845L7.70419 14.1729ZM11.8102 18.0191C12.4224 18.0191 12.9768 17.8805 13.4734 17.6033C13.9701 17.3261 14.3628 16.9449 14.6515 16.4598C14.9403 15.9747 15.0846 15.4319 15.0846 14.8313V11.0891C15.0846 10.9505 15.0269 10.8465 14.9114 10.7772L13.5947 10.0149V14.8486C13.5947 15.1489 13.4676 15.3741 13.2135 15.5243L9.93912 17.4127C10.5051 17.817 11.1288 18.0191 11.8102 18.0191ZM12.4686 11.6781V9.32192L10.5108 8.21312L8.53579 9.32192V11.6781L10.5108 12.7869L12.4686 11.6781ZM7.40967 6.15145C7.40967 5.85115 7.53672 5.62592 7.79082 5.47577L11.0652 3.58735C10.4993 3.1831 9.87559 2.98097 9.19414 2.98097C8.58199 2.98097 8.02759 3.11957 7.53094 3.39677C7.03429 3.67397 6.64159 4.05512 6.35284 4.54022C6.07564 5.02532 5.93704 5.56817 5.93704 6.16878V9.89365C5.93704 10.0323 5.99479 10.142 6.11029 10.2228L7.40967 10.9851V6.15145ZM16.2108 14.4328C16.7883 14.1787 17.2445 13.786 17.5794 13.2547C17.9259 12.7234 18.0992 12.1459 18.0992 11.5222C18.0992 10.9562 17.9548 10.4134 17.6661 9.89365C17.3773 9.3739 17.0019 8.9812 16.5399 8.71555L13.3002 6.84445C13.2309 6.79825 13.1673 6.78092 13.1096 6.79248C13.0518 6.79248 12.9941 6.8098 12.9363 6.84445L11.637 7.5721L15.8296 10.0149C15.9567 10.0842 16.0491 10.1766 16.1068 10.2921C16.1761 10.3961 16.2108 10.5231 16.2108 10.6733V14.4328ZM12.7284 5.6317C12.9825 5.47 13.2366 5.47 13.4907 5.6317L16.7825 7.55477C16.7825 7.47393 16.7825 7.36997 16.7825 7.24292C16.7825 6.68852 16.6439 6.163 16.3667 5.66635C16.101 5.15815 15.7141 4.7539 15.2059 4.4536C14.7093 4.1533 14.1318 4.00315 13.4734 4.00315C12.8959 4.00315 12.3935 4.12442 11.9661 4.36697L8.70904 6.23808C8.59354 6.31892 8.53579 6.42865 8.53579 6.56725V8.0572L12.7284 5.6317Z" />
    </Box>
  );
}

export function ContinueWithChatGpt({ onClick, disabled, loading }) {
  return (
    <Button onClick={onClick} disabled={disabled} loading={loading} sx={{ gap: 1 }}>
      <ChatGptLogo />
      Continue with ChatGPT
    </Button>
  );
}

/* 세 단계. 단추를 누르기 전부터 선다 — 둘째 단계의 오류 화면이 정상이라는 것을 미리 안다. */
function Steps({ current }) {
  return (
    <Box component="ol" data-testid="chatgpt-steps" sx={{ m: 0, pl: 2.5, display: "grid", gap: 0.5 }}>
      {PASTE_STEPS.map((step, index) => (
        <Typography
          component="li" key={step} variant="body2"
          aria-current={current === index + 1 ? "step" : undefined}
          sx={{ ...KO_WORD_BREAK, fontWeight: current === index + 1 ? 600 : 400,
            color: current === index + 1 ? "text.primary" : "text.secondary" }}
        >
          {step}
        </Typography>
      ))}
    </Box>
  );
}

/* 붙여 넣는 칸. 맞는 주소가 들어오는 순간 완료를 부른다 - 누를 단추가 없다. */
function PasteBox({ attempt, onCancel, onRestart, onConnected }) {
  const [url, setUrl] = React.useState("");
  const [note, setNote] = React.useState(null);
  const sentRef = React.useRef(null);
  const left = useCountdown(attempt.expires_at);
  const expired = left === 0;
  /* 다른 탭에서 주소를 복사해 돌아오면 칸에 초점을 둔다 — 바로 Ctrl+V 하면 된다. */
  React.useEffect(() => {
    if (expired) return undefined;
    const onFocus = () => {
      const el = document.getElementById("chatgpt-callback-url");
      if (el && !el.disabled) el.focus();
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [expired]);
  const finish = useMutation({
    mutationFn: (callbackUrl) => api(`/api/admin/ai/oauth/openai/transactions/${attempt.transaction_id}/complete`, {
      method: "POST", body: { callback_url: callbackUrl },
    }),
    onSuccess: (res) => onConnected(res),
    onError: () => { sentRef.current = null; },
  });

  function take(text) {
    setUrl(text);
    const check = matchAttempt(text, attempt);
    setNote(check.note || null);
    if (check.ok && !finish.isPending && sentRef.current !== check.url && !expired) {
      sentRef.current = check.url;
      finish.mutate(check.url);
    }
  }

  async function pasteFromClipboard() {
    setNote(null);
    try {
      const text = await navigator.clipboard.readText();
      take(String(text || "").trim());
    } catch (e) {
      setNote("붙여넣기 단추를 쓸 수 없습니다. 칸을 누르고 Ctrl+V 를 누르세요.");
    }
  }

  const failure = failureText([finish, "붙여 넣은 주소로 연결하지 못했습니다."]);
  const help = expired ? EXPIRED_TEXT
    : (finish.isPending ? "연결하고 있습니다."
      : (note || (left != null ? `남은 시간 ${fmtLeft(left)}` : "맞는 주소가 들어오면 바로 연결됩니다.")));
  return (
    <Box data-testid="chatgpt-paste-steps" sx={{ display: "grid", gap: 1.5, minWidth: 0 }}>
      <Field
        label="주소 붙여 넣기" htmlFor="chatgpt-callback-url" width="full"
        help={help}
        error={failure}
        action={(
          <>
            {expired ? (
              <Button variant="primary" onClick={onRestart}>다시 시작</Button>
            ) : (
              <Button onClick={pasteFromClipboard} disabled={finish.isPending}>붙여넣기</Button>
            )}
            <Button variant="ghost" onClick={onCancel}>취소</Button>
          </>
        )}
      >
        <TextField
          id="chatgpt-callback-url" size="small" fullWidth value={url} disabled={expired}
          onChange={(e) => take(e.target.value)}
          placeholder="http://127.0.0.1:…/auth/callback?code=…"
          inputProps={{ spellCheck: false, autoComplete: "off" }}
        />
      </Field>
      {attempt.blocked && attempt.authorize_url ? (
        <Callout tone="info" compact>
          {BLOCKED_TEXT}{" "}
          <Link href={attempt.authorize_url} target="_blank" rel="noopener">ChatGPT 승인 창 열기</Link>
        </Callout>
      ) : null}
      {attempt.resumed ? (
        <Callout tone="info" compact action={<Button size="sm" onClick={onRestart}>처음부터 다시</Button>}>
          앞서 시작한 로그인이 아직 열려 있습니다. 새 창에서 승인했다면 그 주소를 붙여 넣으세요.
        </Callout>
      ) : null}
    </Box>
  );
}

function sameWindowRedirect(url) {
  window.location.assign(url);
}

/* 인증 칸 — 연결했으면 「ChatGPT 계정으로 연결됨」 한 줄과 [다시 로그인] · [연결 끊기], 아니면 요금제 공유 한 줄과 세 단계 카드와
   「Continue with ChatGPT」. `login` 은 서버가 본 이 관리자의 열린 시도다(새로고침 뒤 붙여 넣기 칸을 되찾는다).
   `redirect` 는 서버가 `flow: "redirect"` 를 줄 때 같은 창을 옮기는 길이다(공식 지원 뒤, 시험은 이것을 바꿔 잰다). */
export function ChatGptLogin({ chatgpt, login, onConnected, onLoggedOut, redirect = sameWindowRedirect }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [attempt, setAttempt] = React.useState(null);
  const [notice, setNotice] = React.useState(false);
  const windowRef = React.useRef(null);
  const dismissedRef = React.useRef(null);
  const start = useMutation({ mutationFn: () => api("/api/admin/ai/oauth/openai/start", { method: "POST" }) });
  const logout = useMutation({
    mutationFn: () => api("/api/admin/ai/oauth/openai/logout", { method: "POST" }),
    onSuccess: (res) => {
      if (onLoggedOut) onLoggedOut(res);
      toast((res && res.message) || "ChatGPT 계정 연결을 끊었습니다.", res && res.revoked === false && res.removed ? "info" : "success");
    },
  });

  const info = chatgpt || {};
  /* 서버가 열린 시도를 알고 있고(새로고침 · 다른 탭) 이 화면에는 없다 - 붙여 넣기 칸을 되찾는다. 취소한 시도는 다시 열지 않는다. */
  React.useEffect(() => {
    if (attempt || info.connected || !login || !login.open || !login.transaction_id) return;
    if (dismissedRef.current === login.transaction_id) return;
    setAttempt({ transaction_id: login.transaction_id, expires_at: login.expires_at, resumed: true, blocked: false });
  }, [attempt, info.connected, login]);

  function begin() {
    const win = openBlankWindow();
    windowRef.current = win;
    start.mutate(undefined, {
      onSuccess: (res) => {
        if (res && res.flow === "redirect") {
          if (win) win.close();
          redirect(res.authorize_url);
          return;
        }
        let blocked = !win || win.closed;
        if (!blocked) {
          try { win.location.href = res.authorize_url; } catch (e) { blocked = true; }
        }
        setAttempt({ ...res, blocked });
      },
      onError: () => { if (win && !win.closed) win.close(); },
    });
  }

  function cancel() {
    if (attempt) dismissedRef.current = attempt.transaction_id;
    setAttempt(null);
  }

  function connected(res) {
    const win = windowRef.current;
    if (win && !win.closed) {
      try { win.close(); } catch (e) { /* 이미 닫혔다 */ }
    }
    setAttempt(null);
    if (onConnected) onConnected(res);
    if (noticeSeen()) toast("ChatGPT 계정을 연결했습니다. 모델 목록을 가져옵니다.", "success");
    else setNotice(true);
  }

  async function askLogout() {
    const ok = await confirm("이 서버에서 ChatGPT 계정 연결을 끊을까요? 다시 쓰려면 다시 로그인해야 합니다.",
      { danger: true, title: "ChatGPT 계정 연결 끊기", confirmLabel: "연결 끊기" });
    if (ok) logout.mutate();
  }

  const startFailure = failureText([start, "연결을 시작하지 못했습니다."]);
  return (
    <Box data-testid="chatgpt-login" sx={{ display: "grid", gap: 1.5, minWidth: 0 }}>
      {info.connected && !attempt ? (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", minHeight: "2.125rem" }}>
          <DotLabel label={CONNECTED_LABEL} tone="ok" strong />
          <Box sx={{ flex: 1 }} />
          <Button onClick={begin} loading={start.isPending}>다시 로그인</Button>
          <Button variant="ghost" onClick={askLogout} loading={logout.isPending}>연결 끊기</Button>
        </Box>
      ) : (
        <>
          {info.disconnected ? (
            <Callout tone="warn" compact>ChatGPT 계정 연결이 끊겼습니다. 다시 로그인하세요.</Callout>
          ) : null}
          {!info.connected && !info.disconnected ? (
            <Callout tone="info" compact>{PLAN_NOTICE}</Callout>
          ) : null}
          <Steps current={attempt ? 3 : 1} />
          {attempt ? (
            <PasteBox attempt={attempt} onCancel={cancel} onRestart={() => { cancel(); begin(); }} onConnected={connected} />
          ) : (
            <Box>
              <ContinueWithChatGpt onClick={begin} loading={start.isPending} />
            </Box>
          )}
        </>
      )}
      {startFailure ? <Callout tone="danger" compact>{startFailure}</Callout> : null}
      <Modal
        open={notice} onClose={() => { markNoticeSeen(); setNotice(false); }} title="You're using your ChatGPT plan" size="sm"
        footer={<Button variant="primary" onClick={() => { markNoticeSeen(); setNotice(false); }}>Got it</Button>}
      >
        <Typography variant="body2" sx={{ ...KO_WORD_BREAK, fontSize: FONT_SIZE.body }}>
          Eligible usage in this app uses your ChatGPT plan. Manage usage in your ChatGPT settings.
        </Typography>
      </Modal>
    </Box>
  );
}

export default ChatGptLogin;
