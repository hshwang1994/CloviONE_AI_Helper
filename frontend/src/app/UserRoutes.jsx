import React from "react";
import { Routes, Route, useLocation } from "react-router-dom";
import MuiButton from "@mui/material/Button";
import { MyTickets, Unassigned, NewTicket } from "../screens/MyTickets.jsx";
import { Home } from "../screens/Home.jsx";
import { Board, IdeaBoard } from "../screens/Board.jsx";
import { BoardPost } from "../screens/BoardPost.jsx";
import { TeamDocs } from "../screens/TeamDocs.jsx";
import { TeamDoc } from "../screens/TeamDoc.jsx";
import { Trash } from "../screens/Trash.jsx";
import { Ticket } from "../screens/Ticket.jsx";
import { TeamTickets } from "../screens/TeamTickets.jsx";
import { Projects } from "../screens/Projects.jsx";
import { Project } from "../screens/Project.jsx";
import { Sprint } from "../screens/Sprint.jsx";
import { Games } from "../screens/Games.jsx";
import { ChatRooms } from "../screens/ChatRooms.jsx";
import { Search } from "../screens/Search.jsx";
import { Profile } from "../screens/Profile.jsx";
import { MyStats } from "../screens/MyStats.jsx";
import { Activity } from "../screens/Activity.jsx";
import { DisplaySettings } from "../screens/DisplaySettings.jsx";
import { DataScreen } from "../screens/DataScreen.jsx";
/* 알림 화면 설정만 들여온다 — `registry.js` 전체가 아니다 (PF7).
   그 파일은 관리자 화면 스물여덟 개의 설정 덩어리(gzip 43KB)이고, 사용자 콘솔이 거기서
   실제로 쓰는 것은 알림 하나뿐이다. 예전에는 이 한 줄 때문에 평범한 사용자가 평생 열지
   않을 관리자 설정을 전부 내려받았다. */
import { NOTIFICATIONS_SCREEN } from "../screens/registry/notifications.js";
// PA-RC-0024: registry.js 전체(gzip 43KB, 위 주석)는 여전히 안 들여온다 — navConfig.js는
// App.jsx가 이미 무조건 정적으로 물어 오는 가벼운 모듈(아이콘 레퍼런스 + 배열)이라 이
// 파일이 추가로 들여와도 초기 번들 비용이 늘지 않는다.
import { NAV } from "./navConfig.js";
import { Card, Skeleton, ErrorState, EmptyState } from "../ui/kit.jsx";

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

/* PA-RC-0024: 모르는 주소로 들어오면 전부 조용히 /me 로 튕겼다 — 관리자 화면 링크를
 * user 역할 계정이 열어도(App.jsx가 role===user 이면 AdminRoutes 자체를 마운트 안
 * 하므로 그 요청은 항상 여기로 떨어진다), 진짜 오타 URL을 열어도 똑같이 조용히 홈으로
 * 갔다 — 무슨 일이 있었는지 알 방법이 없었다(Handoff PA-F-072).
 *
 * 이 두 경우는 사람이 받아야 할 안내가 다르다: 관리자 전용 화면은 "권한이 없다"(그
 * 화면은 존재한다, 이 역할이 못 쓸 뿐)고, 진짜 모르는 경로는 "찾을 수 없다"(그런
 * 화면 자체가 없다)고 말해야 한다. navConfig.js의 NAV(관리자 내비 설정, App.jsx가 이미
 * 무조건 물어 오는 가벼운 모듈)에 그 경로가 있는지로 둘을 가른다 — registry.js 전체를
 * 새로 들여오지 않는다. */
const ADMIN_NAV_PATHS = NAV.flatMap((group) => group.items).map((item) => item.to);

function isKnownAdminPath(pathname) {
  return ADMIN_NAV_PATHS.some((to) => pathname === to || pathname.startsWith(to + "/"));
}

function UserConsoleFallback() {
  const location = useLocation();
  if (isKnownAdminPath(location.pathname)) {
    return (
      <EmptyState
        title="권한이 없습니다"
        help="이 화면은 관리자 콘솔 전용입니다. 관리자 권한이 필요하면 관리자에게 문의하세요."
        art="noPermission"
        action={<MuiButton variant="contained" href="#/me">홈으로 이동</MuiButton>}
      />
    );
  }
  return <ErrorState error={{ status: 404 }} />;
}

/* 사용자 콘솔 — 내 업무/내 티켓/미할당 + 팀 공간 + 문서 + AI 도우미(/chat).
 * 알림은 공용 DataScreen이라 기본 '관리자' 빵부스러기가 뜨므로 그 라우트만 감싼다. */
function UserRoutes() {
  return (
    <Routes>
      {/* 홈은 '오늘' 커맨드 센터(Home.jsx) — GET /api/home/today 한 번으로 티켓·알림·채팅·
          스프린트·최근 변경을 한 화면에 모은다. 예전 MyWork(티켓만 보던 홈)를 대체한다. */}
      <Route path="/me" element={<Home />} />
      {/* 통합 검색 결과(계획서 Phase 5). 두 콘솔 **양쪽에** 같은 경로로 등록한다 —
          관리자가 /dashboard 에서 Ctrl+K 로 검색했는데 세그먼트가 사용자 쪽으로 튀면
          사이드바가 통째로 바뀐다. 그래서 navConfig 의 USER_SEG_PATHS 에는 넣지 않는다. */}
      <Route path="/search" element={<Search />} />
      <Route path="/my-tickets" element={<MyTickets />} />
      <Route path="/unassigned" element={<Unassigned />} />
      <Route path="/new-ticket" element={<NewTicket />} />
      <Route path="/tickets/:id" element={<Ticket />} />
      <Route path="/team-tickets" element={<TeamTickets />} />
      {/* 프로젝트 목록과 상세. 상세 안의 탭(개요·WBS·마일스톤·티켓·주간 리포트)은 라우트가
          아니라 주소의 `?tab=` 이다 — 탭마다 라우트를 두면 사이드바 소속 판정과 뒤로가기
          동작이 탭 수만큼 늘어나는데, 사용자에게는 여전히 '한 화면'이다. */}
      <Route path="/projects" element={<Projects />} />
      <Route path="/projects/:id" element={<Project />} />
      <Route path="/sprint" element={<Sprint />} />
      <Route path="/chat" element={<div className="c-chat-embed"><Lazy><Chat /></Lazy></div>} />
      {/* 두 경로가 **같은 껍데기**를 그린다(S1). 오른쪽 칸만 바뀌므로 방을 옮겨도 목록이
          그대로 있고, 알림 딥링크(`/chat-rooms/<id>`)와 새로고침·뒤로가기도 그대로 동작한다. */}
      <Route path="/chat-rooms" element={<ChatRooms />} />
      <Route path="/chat-rooms/:id" element={<ChatRooms />} />
      <Route path="/board" element={<Board />} />
      {/* 제안 게시판(7단계 #1)은 **목록만** 따로 있다. 상세는 `/board/:id` 하나뿐이다 —
          같은 표의 같은 행이고, 화면도 하나여야 첨부·댓글·반응이 두 벌이 되지 않는다. */}
      <Route path="/ideas" element={<IdeaBoard />} />
      <Route path="/board/:id" element={<BoardPost />} />
      <Route path="/team-docs" element={<TeamDocs />} />
      {/* /team-docs/trash 는 /team-docs/:id 보다 먼저 — id 로 잡히지 않게 */}
      <Route path="/team-docs/trash" element={<Trash />} />
      <Route path="/team-docs/:id" element={<TeamDoc />} />
      <Route path="/games" element={<Games />} />
      <Route path="/games/:id" element={<Lazy><GameRoom /></Lazy>} />
      <Route path="/notifications" element={<DataScreen config={NOTIFICATIONS_SCREEN.notifications} />} />
      {/* 내 정보(계획서 Phase 6 사용자) — 프로필 셀프서비스·업무량 통계·활동 피드.
          역할과 무관하게 누구나 자기 것만 본다. 서버가 세션 사용자 기준으로만 답하므로
          라우트 역할 게이트가 필요 없다(가드가 없는 게 아니라 대상이 하나뿐이다). */}
      <Route path="/profile" element={<Profile />} />
      <Route path="/my-stats" element={<MyStats />} />
      <Route path="/activity" element={<Activity />} />
      {/* PA-RC-0022: 화면 강조색은 브라우저 로컬 저장이라 서버 세션·역할과 아예 무관하다 —
          위 셋보다도 게이트가 더 필요 없다. */}
      <Route path="/my-display" element={<DisplaySettings />} />
      <Route path="*" element={<UserConsoleFallback />} />
    </Routes>
  );
}


export default UserRoutes;
