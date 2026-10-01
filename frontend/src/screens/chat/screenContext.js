import { objectParticle } from "../../lib/format.js";

/* 서랍이 보는 화면 대상 — 지금 주소가 티켓 · 프로젝트 · 문서 한 건이면 `{kind, ref, label}` 이다 (D-538).
 *
 * 이 값은 사용자가 고칠 수 있는 힌트일 뿐이다. 서버는 대화 주인의 권한으로 그 대상을 **다시 읽은** 것만 모델에 싣고, 못 읽으면
 * 아무것도 싣지 않는다(`app/ai/assistant/history.py`). 그래서 여기서 대상을 미리 확인하지 않는다 — 화면이 그 대상을 보여
 * 주고 있다는 것은 이미 그 사람이 볼 수 있다는 뜻이다. */

const TARGETS = [
  { re: /^\/tickets\/([A-Za-z0-9_-]{1,64})\/?$/, kind: "ticket", label: "티켓" },
  { re: /^\/projects\/([A-Za-z0-9_-]{1,64})\/?$/, kind: "project", label: "프로젝트" },
  { re: /^\/knowledge\/([A-Za-z0-9_-]{1,64})\/?$/, kind: "document", label: "문서" },
];

export function screenTargetFor(pathname) {
  const path = String(pathname || "");
  for (const target of TARGETS) {
    const hit = target.re.exec(path);
    if (hit) return { kind: target.kind, ref: hit[1], label: target.label };
  }
  return null;
}

/* 대상 종류마다 시작 제안. 누르면 입력 칸에 채운다(바로 보내지 않는다). */
export const SCREEN_SUGGESTIONS = {
  ticket: ["이 티켓을 요약해 줘", "이 티켓과 관련된 문서를 찾아 줘"],
  project: ["이 프로젝트 진행 상황을 알려 줘", "이 프로젝트의 늦어진 일을 알려 줘"],
  document: ["이 문서를 요약해 줘", "이 문서와 관련된 티켓을 찾아 줘"],
};

export function screenContextLine(target) {
  return target ? `지금 보는 ${target.label}${objectParticle(target.label)} 기준으로 물어볼 수 있습니다.` : "";
}
