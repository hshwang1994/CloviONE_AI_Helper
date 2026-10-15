/* 서비스 주소 카드 · 바꾸기 대화 상자의 순수 함수 (계획 M4, D-574 · 서버 계약은 D-573).
 *
 * 정본은 서버다 — 대표 주소 · 별칭은 env 와 설치 매니페스트에 있고(특권 도우미 `domain.preview` · `domain.apply`), 화면은 그 사실을
 * 그리고 입력을 미리 거를 뿐이다. 여기서 거르는 규칙은 서버 검증(`app/sysops/actions_domain.py::_host`)과 같은 모양이어야 한다 —
 * 화면이 받아 준 값을 서버가 거절하면 사람은 같은 값을 두 번 고친다. 서버가 다시 거른다(그쪽이 경계다).
 */

const LABEL = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
export const MAX_ALIASES = 5;

/** 도메인 이름인가 — 라벨 둘 이상, 라벨은 영문 · 숫자 · 하이픈, 마지막 라벨에 글자가 있다(IP 주소를 이름으로 받지 않는다). */
export function isDomainName(value) {
  const text = String(value || "").trim().toLowerCase().replace(/\.$/, "");
  if (!text || text.length > 253) return false;
  const labels = text.split(".");
  if (labels.length < 2 || !labels.every((l) => LABEL.test(l))) return false;
  return /[a-z]/.test(labels[labels.length - 1]);
}

function looksLikeIp(text) {
  return /^\d{1,3}(?:\.\d{1,3}){3}$/.test(text) || /^\[?[0-9a-f:]+\]?$/i.test(text) && text.includes(":");
}

/** 새 주소 칸 — `https://이름` 또는 `이름` 을 받아 이름만 돌려준다. 틀리면 `{ error }` 하나. */
export function parseAddress(input) {
  const raw = String(input || "").trim();
  if (!raw) return { error: "새 주소를 넣으세요." };
  const scheme = raw.match(/^([a-z][a-z0-9+.-]*):\/\//i);
  if (scheme && scheme[1].toLowerCase() !== "https") return { error: "https 주소만 쓸 수 있습니다." };
  const rest = scheme ? raw.slice(scheme[0].length) : raw;
  const cut = rest.search(/[/?#]/);
  const authority = cut === -1 ? rest : rest.slice(0, cut);
  const tail = cut === -1 ? "" : rest.slice(cut);
  if (tail && tail !== "/") return { error: "경로 없이 주소만 넣으세요." };
  if (authority.includes("@")) return { error: "주소에 계정 정보를 넣을 수 없습니다." };
  const host = authority.replace(/\.$/, "").toLowerCase();
  if (/:\d*$/.test(host) && !looksLikeIp(host)) return { error: "포트 없이 주소만 넣으세요." };
  if (looksLikeIp(host)) return { error: "IP 주소가 아니라 이름을 넣으세요." };
  if (!isDomainName(host)) return { error: "올바른 도메인 이름이 아닙니다. 예: service.example.com" };
  return { host };
}

/** 함께 쓸 주소 — 소문자 · 중복 제거 · 대표 이름 빼기. 상한을 넘으면 앞의 다섯만 남기지 않고 넘었다고 알린다. */
export function normalizeAliases(names, host) {
  const out = [];
  for (const name of names || []) {
    const item = String(name || "").trim().toLowerCase().replace(/\.$/, "");
    if (!item || item === host || out.includes(item)) continue;
    out.push(item);
  }
  return out;
}

/** 지금 이 화면을 연 주소가 대표 주소인가, 별칭인가, 이 서버가 모르는 이름인가. */
export function accessState(request, domain) {
  const host = String((request && request.host) || "").toLowerCase();
  const canonical = String((domain && domain.canonical) || "").toLowerCase();
  const aliases = ((domain && domain.aliases) || []).map((a) => String(a).toLowerCase());
  if (!host || !canonical) return { kind: "unknown", message: null };
  if (host === canonical) return { kind: "canonical", message: "대표 주소로 접속했습니다." };
  if (aliases.includes(host)) return { kind: "alias", message: "대표 주소와 다릅니다. 이 주소는 함께 쓰는 주소(별칭)입니다." };
  return { kind: "foreign", message: "대표 주소와 다릅니다. 이 서버가 모르는 이름입니다." };
}

/** 인증서가 이 이름들을 모두 담는가. 모르는 인증서(못 읽음)는 `known: false`. */
export function certCoverage(cert, names) {
  if (!cert || !cert.readable) return { known: false, missing: [] };
  const have = new Set((cert.sans || []).map((n) => String(n).toLowerCase()));
  const missing = (names || []).filter((n) => !have.has(String(n).toLowerCase()));
  return { known: true, missing };
}

export const CHECK_ORDER = ["dns", "https", "web", "app"];
export const CHECK_LABEL = { dns: "DNS", https: "HTTPS", web: "웹 서버", app: "서비스 설정" };
export const CHECK_WORD = { ok: "정상", warn: "주의", fail: "실패", unknown: "모름" };
export const CHECK_TONE = { ok: "ok", warn: "warn", fail: "danger", unknown: "neutral" };

/** 서버의 확인 넷을 정해진 순서로. 빠진 확인은 「모름」으로 세운다 — 없는 줄을 지어내지 않되 자리는 지킨다. */
export function orderedChecks(checks) {
  const byKey = Object.fromEntries((checks || []).map((c) => [c.key, c]));
  return CHECK_ORDER.map((key) => byKey[key] || { key, label: CHECK_LABEL[key], state: "unknown", message: null });
}

export function hasFailure(checks) {
  return (checks || []).some((c) => c.state === "fail");
}

/** 공개 해석기의 답 — 정보일 뿐 판정이 아니다(사내 해석기 기준이 판정이다). 비교 해석기가 없으면 null. */
export function publicDnsText(dns) {
  const rows = (dns && dns.compare) || [];
  if (!rows.length) return null;
  return rows.map((r) => {
    const answer = r.answers && r.answers.length ? r.answers.join(", ") : "답 없음";
    return `공개 DNS ${r.resolver}의 답은 ${answer}입니다.`;
  }).join(" ");
}

export const CERT_STRATEGIES = [
  { value: "self_signed", label: "자체 서명 새로 만들기", description: "이 서버가 새 이름으로 인증서를 만듭니다. 처음 여는 브라우저가 경고합니다." },
  { value: "keep", label: "지금 인증서 유지", description: "지금 인증서에 새 이름이 모두 들어 있을 때만 고를 수 있습니다." },
  { value: "provided", label: "PEM 붙여 넣기", description: "신뢰된 인증서와 개인키를 붙여 넣습니다." },
];

export const CERT_SENTENCE = {
  self_signed: "인증서는 자체 서명으로 새로 만듭니다. 사내 브라우저는 처음 열 때 경고합니다.",
  keep: "인증서는 지금 것을 그대로 씁니다.",
  provided: "인증서는 붙여 넣은 것으로 바꿉니다. 키와 인증서가 한 쌍인지 먼저 확인합니다.",
};

/** 적용하는 동안 보일 단계 — 서버의 `data.steps` 와 같은 이름 · 같은 순서다(`app/sysops/actions_domain.py`). */
export function plannedSteps(restartWeb) {
  const steps = [
    { name: "validate", label: "입력 확인" },
    { name: "cert", label: "인증서" },
    { name: "web", label: "웹 서버 설정" },
    { name: "config", label: "설정 파일" },
    { name: "check", label: "자체 확인" },
    { name: "services", label: "서비스 재시작" },
  ];
  if (restartWeb) steps.push({ name: "web_restart", label: "웹 서버 다시 시작" });
  return steps;
}

/** 적용 요청 본문. 개인키는 PEM 방식일 때만 싣는다. */
export function applyParams({ host, aliases, strategy, certificate, privateKey, restartWeb }) {
  const cert = { strategy };
  if (strategy === "provided") {
    cert.certificate = certificate;
    cert.private_key = privateKey;
  }
  return { host, aliases, cert, restart_web: Boolean(restartWeb) };
}

/** 미리 확인 주소의 질의 문자열. */
export function previewQuery(host, aliases) {
  const params = new URLSearchParams();
  if (host) params.set("host", host);
  if (aliases && aliases.length) params.set("aliases", aliases.join(","));
  const text = params.toString();
  return text ? `?${text}` : "";
}
