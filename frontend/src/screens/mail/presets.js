/* 외부 SMTP 제공자 프리셋 (기능 개선 회차 P4 ②, D-560).
 *
 * 계정이 있는 설치를 위한 것이다 - 고르면 서버 주소 · 포트 · 보안 연결이 채워지고, 제공자마다 비밀번호에 대한 한 줄 도움말과
 * 발급처 링크가 선다. 저장 값은 지금 필드 그대로다(프리셋은 화면 상수이고 서버는 모른다). 사람이 서버 주소를 고치면 「직접 입력」으로
 * 돌아간다 - 프리셋은 값을 채우는 도구이지 잠그는 도구가 아니다.
 */

export const PRESET_CUSTOM = "custom";

export const SMTP_PRESETS = [
  {
    key: "gmail", label: "Gmail", host: "smtp.gmail.com", port: 587, security: "starttls",
    description: "Google 계정의 앱 비밀번호로 보냅니다.",
    help: "Google 계정 › 보안 › 2단계 인증 › 앱 비밀번호에서 16자리 앱 비밀번호를 만들어 비밀번호 칸에 넣으세요. 계정 비밀번호는 쓸 수 없습니다.",
    link: { label: "앱 비밀번호 발급 안내", url: "https://myaccount.google.com/apppasswords" },
    from_note: "보내는 주소는 그 Google 계정 주소입니다. 다른 주소를 적어도 Gmail이 계정 주소로 바꿔 보냅니다.",
  },
  {
    key: "m365", label: "Microsoft 365", host: "smtp.office365.com", port: 587, security: "starttls",
    description: "회사 Microsoft 365 계정으로 보냅니다.",
    help: "회사 계정 비밀번호를 넣습니다. 연결 확인에 「535 5.7.139」가 나오면 조직이 SMTP 인증을 막은 것이라 Microsoft 365 관리자가 켜야 합니다.",
    link: { label: "SMTP AUTH 안내", url: "https://learn.microsoft.com/exchange/clients-and-mobile-in-exchange-online/authenticated-client-smtp-submission" },
    from_note: "보내는 주소는 그 계정 주소이거나 그 계정이 보낼 수 있는 주소여야 합니다.",
  },
  {
    key: "naver", label: "Naver", host: "smtp.naver.com", port: 465, security: "ssl",
    description: "네이버 메일 계정으로 보냅니다.",
    help: "네이버 메일 › 환경설정 › POP3/IMAP 설정에서 POP3/SMTP 사용을 켠 뒤 계정 비밀번호를 넣으세요.",
    link: { label: "네이버 메일 설정 열기", url: "https://mail.naver.com/option/pop3" },
    from_note: "보내는 주소는 그 네이버 계정 주소입니다.",
  },
  {
    key: PRESET_CUSTOM, label: "직접 입력", host: "", port: 587, security: "starttls",
    description: "회사 SMTP 서버나 다른 서비스의 값을 직접 넣습니다.",
    help: "메일 서비스가 안내하는 SMTP 서버 주소, 포트, 보안 연결, 계정, 비밀번호를 넣습니다.",
    link: null,
    from_note: null,
  },
];

const BY_KEY = Object.fromEntries(SMTP_PRESETS.map((p) => [p.key, p]));

export function presetByKey(key) {
  return BY_KEY[key] || null;
}

/* 지금 값이 어느 프리셋의 모양인가 - 서버 주소가 프리셋의 것이면 그 프리셋, 아니면 「직접 입력」. */
export function presetOf(values) {
  const host = String((values && values.host) || "").trim().toLowerCase();
  const found = SMTP_PRESETS.find((p) => p.key !== PRESET_CUSTOM && p.host === host);
  return found ? found.key : PRESET_CUSTOM;
}

/* 프리셋을 고르면 채우는 값. 직접 입력은 서버 값을 비우지 않는다(사람이 적은 값을 지우지 않는다). */
export function presetPatch(key) {
  const preset = presetByKey(key);
  if (!preset || preset.key === PRESET_CUSTOM) return {};
  return { host: preset.host, port: preset.port, security: preset.security };
}
