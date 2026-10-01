import { useQuery } from "@tanstack/react-query";
import { api } from "./api.js";

/* AI 를 지금 쓸 수 있는가 — `/api/ai/status` 한 질의를 AI 도우미 화면 · 서랍 · 「문서에서 찾기」가 함께 읽는다(D-538).
 *
 * 서버가 판정한다(`app/ai/assistant/availability.py`): `assistant.available` 이 거짓이면 `reason`(no_permission · feature_off ·
 * off · unconfigured · blocked)과 그 까닭을 말하는 완전한 문장(`notice`)이 함께 온다. 화면은 그 문장을 그대로 쓰고 까닭을 지어내지
 * 않는다. 메시지를 보낼 때 409 `ai_unavailable` 이 오면 부른 쪽이 이 질의를 무효로 해 판 상태를 다시 그린다. */

export const AI_STATUS_KEY = ["ai", "status"];

export function useAiStatus({ enabled = true } = {}) {
  return useQuery({
    queryKey: AI_STATUS_KEY,
    queryFn: () => api("/api/ai/status"),
    enabled,
    retry: false,
    staleTime: 30_000,
  });
}

/* 도우미 칸 하나. 아직 모르면 null 이다 — 모를 때 입력을 막지 않는다(보내 보면 서버가 409 로 말한다). */
export function assistantOf(status) {
  const data = status && status.data;
  return data && data.assistant ? data.assistant : null;
}

/* 409 `ai_unavailable` 인가. 그 응답은 실패 문장이 아니라 판 상태로 그린다. */
export function isAiUnavailable(error) {
  return !!(error && error.status === 409 && error.body && error.body.error && error.body.error.code === "ai_unavailable");
}
