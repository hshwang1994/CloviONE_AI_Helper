import { useQuery } from "@tanstack/react-query";
import { api } from "./api.js";

/* 지식 공간 목록을 묻는 자리는 **하나**다 (S19).
 *
 * 🔴 왜 생겼나. 같은 질의가 두 화면에 각자 있었다 — `Knowledge.jsx` 와 `AiWorkspace.jsx`.
 * 서버는 `{ items: [...] }` 를 주는데 AI 작업공간 쪽은 응답을 **배열로 알고** `.map` 을
 * 불렀다. 그리고 그 한 줄은 모달 안이 아니라 `FormModal` 의 `fields` 배열 안에 있어서
 * 모달이 닫혀 있어도 매 렌더 계산된다 — 공간 질의가 도착하는 순간 `/ai` 가 통째로
 * 500 화면이 됐다. 목록이 비어 있는 개발 환경에서는 `[]` 라 아무 일도 안 일어난다.
 *
 * 그래서 «묻는 자리» 와 «응답을 푸는 자리» 를 하나로 둔다. 한쪽만 틀릴 수가 없다.
 */
export const SPACES_KEY = ["knowledge", "spaces"];

/** 지식 공간 목록. `query` 는 상태(로딩·오류·재시도), `items` 는 언제나 배열이다. */
export function useKnowledgeSpaces() {
  const query = useQuery({ queryKey: SPACES_KEY, queryFn: () => api("/api/knowledge/spaces") });
  const items = Array.isArray(query.data?.items) ? query.data.items : [];
  return { query, items };
}
