import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { Message } from "./MessageThread.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

/* VIS-158R 재확인: "화면 폭 2200px(xxl) 미만은 구조화된 카드 대신 말풍선 안 텍스트 목록만
 * 받는다"는 주장을 실제 소스로 재확인했다.
 *
 * Chat.jsx를 읽어 보면 그렇지 않다 — `hideCards`는 `!!railMsg && railMsg.id === m.id`로만
 * 계산되고(Chat.jsx:240), `railMsg`는 `railOpen`(`useMediaQuery(theme.breakpoints.up("xxl"))`)이
 * false면 항상 null이다(Chat.jsx:105-107). 즉 xxl 미만에서는 `railMsg`가 없으므로 모든 메시지의
 * `hideCards`가 항상 false이고, 이 컴포넌트(Message)는 `!hideCards && payload.hasAny`일 때
 * CardStack(진짜 카드 — 상태·담당자·마감 배지)을 말풍선 **안에** 그대로 그린다. xxl 이상에서
 * 달라지는 것은 "마지막 카드 그룹을 오른쪽 레일로도 옮겨 계속 보이게 하는가"뿐이지, "카드를
 * 아예 안 보여주고 텍스트로 뭉갠다"가 아니다.
 *
 * 이 시험은 hideCards=false(= xxl 미만에서 실제로 전달되는 값)로 Message를 직접 렌더링해
 * 카드(제목·상태 배지)가 실제로 보이는지 확인한다 — Chat.jsx 전체를 렌더링하지 않고도
 * VIS-158R의 핵심 주장(좁은 화면=텍스트만)이 맞는지 직접 검증한다.
 */

const TICKET_MESSAGE = {
  id: "m1",
  role: "assistant",
  content: "요청하신 티켓을 찾았습니다.",
  processing_status: "done",
  structured: {
    tickets: [
      { title: "로그인 실패 조사", status: "진행", assignees: ["김운영"], due_date: "2026-08-20" },
    ],
  },
};

function renderMessage(props) {
  return render(
    <ThemeModeProvider>
      <Message m={TICKET_MESSAGE} isLast hideCards={false} {...props} />
    </ThemeModeProvider>
  );
}

describe("VIS-158R 재확인 — 좁은 화면(레일 없음)에서도 말풍선 안에 구조화된 카드가 뜬다", () => {
  it("hideCards=false(레일이 없을 때의 실제 값)면 카드 제목과 상태 배지가 텍스트가 아니라 카드로 보인다", () => {
    renderMessage();

    // 카드 특유의 구조(제목 + '상태' 라벨 + 배지)가 실제로 렌더된다 — 평문 목록이 아니다.
    expect(screen.getByText("로그인 실패 조사")).toBeInTheDocument();
    expect(screen.getByText("상태")).toBeInTheDocument();
    expect(screen.getByText("진행")).toBeInTheDocument();
    expect(screen.getByText("담당자")).toBeInTheDocument();
    expect(screen.getByText("김운영")).toBeInTheDocument();
  });

  it("hideCards=true(≥xxl에서 레일이 대신 보여주는 그 메시지일 때만)면 여기서는 중복으로 안 그린다", () => {
    renderMessage({ hideCards: true });

    expect(screen.queryByText("로그인 실패 조사")).toBeNull();
  });
});
