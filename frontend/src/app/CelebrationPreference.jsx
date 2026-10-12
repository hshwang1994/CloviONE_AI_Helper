import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api.js";
import { setCelebrationEnabled } from "../ui/celebrate.js";

/* 「축하 효과」 스위치(D-563)를 축포 모듈에 맞춘다. 셸에 한 번 서고 아무것도 그리지 않는다.
 *
 * 내 프로필과 같은 쿼리 열쇠(`["me-preferences"]`)를 보므로 거기서 스위치를 바꾸면 응답이 캐시에 쓰이는 순간 여기도 따라온다 —
 * 새로고침 없이 다음 축포부터 적용된다. 값을 못 받으면(오류 · 로딩) 켬이다 — 모르는 것 때문에 축하를 거두지 않는다. */
export function CelebrationPreference() {
  const prefs = useQuery({
    queryKey: ["me-preferences"],
    queryFn: () => api("/api/me/preferences"),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  const enabled = prefs.data && prefs.data.celebration ? prefs.data.celebration.enabled : undefined;
  useEffect(() => {
    setCelebrationEnabled(enabled !== false);
  }, [enabled]);
  return null;
}
