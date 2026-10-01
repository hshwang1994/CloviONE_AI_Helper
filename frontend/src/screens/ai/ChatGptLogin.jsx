import React from "react";
import { useMutation } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { failureText } from "../../lib/failure.js";
import { Button, Callout, DotLabel, Field, Modal, useConfirm, useToast } from "../../ui/kit.jsx";
import { FONT_SIZE, KO_WORD_BREAK } from "../../ui/theme.js";

/* ChatGPT 계정 로그인 (계획 A3, D-540) — 새 창에서 승인하고, 멈춘 주소를 붙여 넣는다.
 *
 * 공식 「Sign in with ChatGPT」는 로그인 결과를 http://127.0.0.1:<포트>/auth/callback 으로만 돌려준다. 그 주소는 이 브라우저가
 * 도는 PC 라 원격 서버가 받을 수 없다(서버의 `login_flow.py` 머리말). 그래서 순서가 셋이다: ① 같은 클릭 안에서 새 창을 열어
 * 승인으로 보낸다 ② 승인 뒤 새 창의 주소창 주소를 복사한다 ③ 여기에 붙여 넣는다. 서버가 제 PKCE verifier 로 코드를 바꾸므로
 * 주소에 든 코드만으로는 쓸모가 없다. 설치할 것도 실행할 명령도 없다.
 *
 * 응답의 `flow` 가 모양을 정한다. 지금은 `paste` 뿐이고, 공식 지원이 생기면 서버가 `redirect` 를 줄 수 있다 - 그때는 같은
 * 창에서 승인으로 간다(화면을 다시 만들지 않는다).
 *
 * 일반 화면에 PKCE · client id · OAuth · localhost 같은 낱말을 쓰지 않는다(5절). 단추와 첫 연결 안내는 공식 화면 지침의 문구를
 * 그대로 쓴다(「Continue with ChatGPT」, 「You're using your ChatGPT plan」).
 */

export const PASTE_STEPS = [
  "ChatGPT에서 로그인하고 승인하세요.",
  "승인이 끝나면 주소창의 주소를 복사하세요.",
  "아래에 붙여 넣으면 연결됩니다.",
];
export const SHARED_PLAN_NOTICE = "ChatGPT 계정으로 연결하면 이 설치의 모든 사용자가 연결한 한 사람의 ChatGPT 요금제를 함께 씁니다. "
  + "여러 사람이 쓰는 설치에는 API 키가 알맞습니다.";
const CALLBACK_RE = /^http:\/\/127\.0\.0\.1:\d{2,5}\/auth\/callback\?/;
const NOTICE_KEY = "clovirassist.chatgpt-plan-notice";

export function looksLikeCallback(text) {
  return CALLBACK_RE.test(String(text || "").trim());
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

/* 붙여 넣는 단계. 주소 칸 + [붙여넣기] · [연결]. 새 창에 오류 화면이 보여도 정상이라는 한 줄이 도움말이다. */
function PasteSteps({ attempt, onCancel, onConnected }) {
  const toast = useToast();
  const [url, setUrl] = React.useState("");
  const [note, setNote] = React.useState(null);
  const finish = useMutation({
    mutationFn: (callbackUrl) => api(`/api/admin/ai/oauth/openai/transactions/${attempt.transaction_id}/complete`, {
      method: "POST", body: { callback_url: callbackUrl },
    }),
    onSuccess: (res) => onConnected(res),
  });

  async function pasteFromClipboard() {
    setNote(null);
    try {
      const text = await navigator.clipboard.readText();
      if (looksLikeCallback(text)) {
        setUrl(text.trim());
      } else {
        setNote("복사한 내용이 승인 뒤의 주소가 아닙니다. 새 창의 주소창 주소를 다시 복사하세요.");
      }
    } catch (e) {
      setNote("붙여넣기 단추를 쓸 수 없습니다. 칸을 누르고 Ctrl+V 를 누르세요.");
    }
  }

  const failure = failureText([finish, "붙여 넣은 주소로 연결하지 못했습니다."]);
  const ready = looksLikeCallback(url);
  return (
    <Box data-testid="chatgpt-paste-steps" sx={{ display: "grid", gap: 1.5, minWidth: 0 }}>
      <Box component="ol" sx={{ m: 0, pl: 2.5, display: "grid", gap: 0.5 }}>
        {PASTE_STEPS.map((step) => (
          <Typography component="li" key={step} variant="body2" sx={KO_WORD_BREAK}>{step}</Typography>
        ))}
      </Box>
      <Field
        label="주소 붙여 넣기" htmlFor="chatgpt-callback-url" width="full"
        help={note || "승인 뒤 새 창에 오류 화면이 보여도 정상입니다."}
        error={failure}
        action={(
          <>
            <Button onClick={pasteFromClipboard}>붙여넣기</Button>
            <Button variant="primary" disabled={!ready} loading={finish.isPending} onClick={() => finish.mutate(url.trim())}>
              연결
            </Button>
            <Button variant="ghost" onClick={onCancel}>취소</Button>
          </>
        )}
      >
        <TextField
          id="chatgpt-callback-url" size="small" fullWidth value={url}
          onChange={(e) => { setUrl(e.target.value); setNote(null); }}
          onKeyDown={(e) => { if (e.key === "Enter" && ready) { e.preventDefault(); finish.mutate(url.trim()); } }}
          placeholder="http://127.0.0.1:…/auth/callback?code=…"
          inputProps={{ spellCheck: false, autoComplete: "off" }}
        />
      </Field>
      {attempt.blocked ? (
        <Callout tone="info" compact action={(
          <Button size="sm" onClick={() => { window.open(attempt.authorize_url, "_blank", "noopener"); toast("승인 창을 열었습니다.", "info"); }}>
            승인 창 열기
          </Button>
        )}
        >
          브라우저가 새 창을 막았습니다. 승인 창을 직접 여세요.
        </Callout>
      ) : null}
    </Box>
  );
}

function sameWindowRedirect(url) {
  window.location.assign(url);
}

/* 인증 칸 — 연결했으면 「ChatGPT 계정으로 연결됨」 한 줄과 [다시 로그인] · [연결 끊기], 아니면 「Continue with ChatGPT」.
   `redirect` 는 서버가 `flow: "redirect"` 를 줄 때 같은 창을 옮기는 길이다(공식 지원 뒤, 시험은 이것을 바꿔 잰다). */
export function ChatGptLogin({ chatgpt, onConnected, onLoggedOut, redirect = sameWindowRedirect }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [attempt, setAttempt] = React.useState(null);
  const [notice, setNotice] = React.useState(false);
  const windowRef = React.useRef(null);
  const start = useMutation({ mutationFn: () => api("/api/admin/ai/oauth/openai/start", { method: "POST" }) });
  const logout = useMutation({
    mutationFn: () => api("/api/admin/ai/oauth/openai/logout", { method: "POST" }),
    onSuccess: (res) => {
      if (onLoggedOut) onLoggedOut(res);
      toast((res && res.message) || "ChatGPT 계정 연결을 끊었습니다.", res && res.revoked === false && res.removed ? "info" : "success");
    },
  });

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

  function connected(res) {
    const win = windowRef.current;
    if (win && !win.closed) {
      try { win.close(); } catch (e) { /* 이미 닫혔다 */ }
    }
    setAttempt(null);
    if (onConnected) onConnected(res);
    if (noticeSeen()) toast("ChatGPT 계정을 연결했습니다.", "success");
    else setNotice(true);
  }

  async function askLogout() {
    const ok = await confirm("이 서버에서 ChatGPT 계정 연결을 끊을까요? 다시 쓰려면 다시 로그인해야 합니다.",
      { danger: true, title: "ChatGPT 계정 연결 끊기", confirmLabel: "연결 끊기" });
    if (ok) logout.mutate();
  }

  const info = chatgpt || {};
  const startFailure = failureText([start, "연결을 시작하지 못했습니다."]);
  return (
    <Box data-testid="chatgpt-login" sx={{ display: "grid", gap: 1.5, minWidth: 0 }}>
      {attempt ? (
        <PasteSteps attempt={attempt} onCancel={() => setAttempt(null)} onConnected={connected} />
      ) : info.connected ? (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", minHeight: "2.125rem" }}>
          <DotLabel label="ChatGPT 계정으로 연결됨" tone="ok" strong />
          <Box sx={{ flex: 1 }} />
          <Button onClick={begin} loading={start.isPending}>다시 로그인</Button>
          <Button variant="ghost" onClick={askLogout} loading={logout.isPending}>연결 끊기</Button>
        </Box>
      ) : (
        <>
          {info.disconnected ? (
            <Callout tone="warn" compact>ChatGPT 계정 연결이 끊겼습니다. 다시 로그인하세요.</Callout>
          ) : (
            <Callout tone="warn" compact>{SHARED_PLAN_NOTICE}</Callout>
          )}
          <Box>
            <ContinueWithChatGpt onClick={begin} loading={start.isPending} />
          </Box>
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
