import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { act, render } from "@testing-library/react";

/* 탭 제목의 브랜드가 — 라우트가 안 바뀐 채로도 — 늦게 도착한 설정값을 따라가는가 (N5 후속).
 *
 * `/api/me` 는 비동기라 AppShell이 먼저 기본 경로(보통 /me)로 마운트되고, 그 응답이 온
 * 뒤에야 auth.jsx가 setBrand()로 실제 제품명을 흘려 넣는다. 사이드바 로고(AppShell이
 * `brand()`를 렌더 중에 직접 읽는다)는 auth.data가 바뀌며 컴포넌트가 다시 렌더될 때 자연히
 * 새 값을 그린다. 그런데 탭 제목(`useDocumentTitle`)은 `useEffect(..., [pathname])`로
 * 경로 변화에만 반응한다 — 로그인 뒤 사용자가 같은 화면(/me)에 머무르는 가장 흔한 경우,
 * 브랜드가 도착해도 그 사실을 알 방법이 이 훅에 없어 탭은 기본 브랜드("ClovirAssist")에
 * 그대로 갇힌다. 사이드바 로고와 탭 제목이 서로 다른 이름을 말하는 상태가 된다.
 */

import { useDocumentTitle, setBrand, BRAND } from "./documentTitle.js";

function Probe({ path }) {
  useDocumentTitle(path);
  return null;
}

describe("브랜드가 늦게 도착해도 탭 제목이 따라간다", () => {
  beforeEach(() => {
    setBrand("");   // 다음 테스트로 전역 override가 새지 않게
  });

  it("경로가 그대로여도 setBrand 이후 문서 제목이 갱신된다", () => {
    const { rerender } = render(<Probe path="/me" />);
    expect(document.title).toBe(`홈 | ${BRAND}`);

    // /api/me 응답이 늦게 도착해 실제 제품명을 흘려 넣는 순간을 흉내낸다. 리스너가 setState를
    // 부르므로(act 밖에서 부르면 테스트가 경고를 낸다) act로 감싼다 — 실제 앱에서는 이 setState가
    // react-query의 onSuccess 처리 안에서 이미 act 경계 안에 있다.
    act(() => { setBrand("우리회사포털"); });
    // 실제 앱에서는 auth.data가 바뀌며 AppShell이 다시 렌더되는 것과 같다 — 경로 prop은 그대로.
    rerender(<Probe path="/me" />);

    expect(document.title, "탭 제목이 기본 브랜드에 갇혀 사이드바 로고와 다른 이름을 말한다")
      .toBe("홈 | 우리회사포털");
  });
});
