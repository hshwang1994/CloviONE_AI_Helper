import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { MyTickets, Unassigned, NewTicket } from "../screens/MyTickets.jsx";
import { Home } from "../screens/Home.jsx";
import { Board } from "../screens/Board.jsx";
import { BoardPost } from "../screens/BoardPost.jsx";
import { TeamDocs } from "../screens/TeamDocs.jsx";
import { TeamDoc } from "../screens/TeamDoc.jsx";
import { Trash } from "../screens/Trash.jsx";
import { Ticket } from "../screens/Ticket.jsx";
import { TeamTickets } from "../screens/TeamTickets.jsx";
import { Sprint } from "../screens/Sprint.jsx";
import { Games } from "../screens/Games.jsx";
import { ChatRooms } from "../screens/ChatRooms.jsx";
import { ChatRoom } from "../screens/ChatRoom.jsx";
import { DataScreen } from "../screens/DataScreen.jsx";
import { REGISTRY } from "../screens/registry.js";
import { Card, Skeleton } from "../ui/kit.jsx";

/* 사용자 콘솔 라우트
 *
 * App.jsx에서 분리해 별도 청크로 뺐다. 두 콘솔은 서로 다른 사람이 쓴다 — 일반 사용자는
 * 관리자 화면 20여 개를 평생 열지 않고, 관리자도 첫 진입에서 두 벌을 다 받을 이유가 없다.
 * 초기 번들이 예산(gzip 280KB)에 2KB까지 붙어 있었는데, 이 분리로 여유가 생긴다.
 */

/* 무거운 화면은 이 콘솔 안에서 한 번 더 쪼갠다 — 채팅 1,205줄, 게임방 821줄은
 * 대부분의 사용자가 한 세션에 들르지 않는다. */
const Chat = React.lazy(() => import("../screens/Chat.jsx").then((m) => ({ default: m.Chat })));
const GameRoom = React.lazy(() => import("../screens/GameRoom.jsx").then((m) => ({ default: m.GameRoom })));

function Lazy({ children }) {
  return <React.Suspense fallback={<Card><Skeleton lines={6} /></Card>}>{children}</React.Suspense>;
}

/* 사용자 콘솔 — 내 업무/내 티켓/미할당 + 팀 공간 + 문서 + AI 도우미(/chat).
 * 알림은 공용 DataScreen이라 기본 '관리자' 빵부스러기가 뜨므로 그 라우트만 감싼다. */
function UserRoutes() {
  return (
    <Routes>
      {/* 홈은 '오늘' 커맨드 센터(Home.jsx) — GET /api/home/today 한 번으로 티켓·알림·채팅·
          스프린트·최근 변경을 한 화면에 모은다. 예전 MyWork(티켓만 보던 홈)를 대체한다. */}
      <Route path="/me" element={<Home />} />
      <Route path="/my-tickets" element={<MyTickets />} />
      <Route path="/unassigned" element={<Unassigned />} />
      <Route path="/new-ticket" element={<NewTicket />} />
      <Route path="/tickets/:id" element={<Ticket />} />
      <Route path="/team-tickets" element={<TeamTickets />} />
      <Route path="/sprint" element={<Sprint />} />
      <Route path="/chat" element={<div className="c-chat-embed"><Lazy><Chat /></Lazy></div>} />
      <Route path="/chat-rooms" element={<ChatRooms />} />
      <Route path="/chat-rooms/:id" element={<ChatRoom />} />
      <Route path="/board" element={<Board />} />
      <Route path="/board/:id" element={<BoardPost />} />
      <Route path="/team-docs" element={<TeamDocs />} />
      {/* /team-docs/trash 는 /team-docs/:id 보다 먼저 — id 로 잡히지 않게 */}
      <Route path="/team-docs/trash" element={<Trash />} />
      <Route path="/team-docs/:id" element={<TeamDoc />} />
      <Route path="/games" element={<Games />} />
      <Route path="/games/:id" element={<Lazy><GameRoom /></Lazy>} />
      <Route path="/notifications" element={<div className="c-body--user-noti"><DataScreen config={REGISTRY.notifications} /></div>} />
      <Route path="*" element={<Navigate to="/me" replace />} />
    </Routes>
  );
}


export default UserRoutes;
