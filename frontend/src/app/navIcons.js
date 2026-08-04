/* 사이드바 아이콘 — 기준 파일(preview-standalone.html)의 아이콘 키를 Lucide 에 1:1 매핑.
 *
 * 사용자 지시 §2: "왼쪽 사이드바의 각 메뉴 왼쪽에 표시되는 아이콘도 preview-standalone.html의
 * 디자인을 기준으로 통일하라."
 *
 * 왜 Lucide 인가: 기준 파일이 그리는 아이콘이 정확히 이 계열이다 —
 *   <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
 *        stroke-linecap="round" stroke-linejoin="round">
 * MUI 의 아이콘은 채운(fill) 실루엣이라 Outlined 변형을 써도 획 두께와 끝처리가 다르다.
 * 근사치로 맞추는 대신 같은 계열을 쓴다(2026-08-04 사용자 지시로 외부 라이브러리 허용).
 *
 * 키 이름은 기준 파일의 것을 그대로 쓴다(home/ticket/plus/ai/...). 그래야 기준 파일의
 * `['my-tickets','내 티켓','ticket']` 같은 표와 이 파일을 나란히 놓고 대조할 수 있다.
 *
 * 개별 경로로 import 한다 — 배럴 import 를 쓰면 트리셰이킹 전에 1,500개 아이콘 모듈이
 * 전부 변환 대상이 되어 개발 빌드가 눈에 띄게 느려진다(정적 검사가 MUI 쪽에서 같은 규칙을
 * 강제하고 있고, 이유는 동일하다).
 */

import Home from "lucide-react/dist/esm/icons/house.mjs";
import Ticket from "lucide-react/dist/esm/icons/ticket.mjs";
import Plus from "lucide-react/dist/esm/icons/plus.mjs";
import Sparkles from "lucide-react/dist/esm/icons/sparkles.mjs";
import CalendarDays from "lucide-react/dist/esm/icons/calendar-days.mjs";
import FileText from "lucide-react/dist/esm/icons/file-text.mjs";
import Trash2 from "lucide-react/dist/esm/icons/trash-2.mjs";
import MessageSquare from "lucide-react/dist/esm/icons/message-square.mjs";
import Gamepad2 from "lucide-react/dist/esm/icons/gamepad-2.mjs";
import ClipboardList from "lucide-react/dist/esm/icons/clipboard-list.mjs";
import LayoutDashboard from "lucide-react/dist/esm/icons/layout-dashboard.mjs";
import Bell from "lucide-react/dist/esm/icons/bell.mjs";
import Settings from "lucide-react/dist/esm/icons/settings.mjs";
import ScrollText from "lucide-react/dist/esm/icons/scroll-text.mjs";
import Users from "lucide-react/dist/esm/icons/users.mjs";
import BarChart3 from "lucide-react/dist/esm/icons/chart-column.mjs";
import CheckCircle2 from "lucide-react/dist/esm/icons/circle-check.mjs";
import Database from "lucide-react/dist/esm/icons/database.mjs";
import Wrench from "lucide-react/dist/esm/icons/wrench.mjs";
import Stethoscope from "lucide-react/dist/esm/icons/stethoscope.mjs";
import Link2 from "lucide-react/dist/esm/icons/link-2.mjs";
import Workflow from "lucide-react/dist/esm/icons/workflow.mjs";
import Bot from "lucide-react/dist/esm/icons/bot.mjs";
import ShieldCheck from "lucide-react/dist/esm/icons/shield-check.mjs";
import FileCode from "lucide-react/dist/esm/icons/file-code.mjs";
import Clock from "lucide-react/dist/esm/icons/clock.mjs";
import User from "lucide-react/dist/esm/icons/user.mjs";
import Activity from "lucide-react/dist/esm/icons/activity.mjs";
import Building2 from "lucide-react/dist/esm/icons/building-2.mjs";
import Briefcase from "lucide-react/dist/esm/icons/briefcase.mjs";
import Megaphone from "lucide-react/dist/esm/icons/megaphone.mjs";
import Flag from "lucide-react/dist/esm/icons/flag.mjs";
import Eye from "lucide-react/dist/esm/icons/eye.mjs";
import Gauge from "lucide-react/dist/esm/icons/gauge.mjs";
import Search from "lucide-react/dist/esm/icons/search.mjs";

/* 아이콘 키 → 컴포넌트. 없는 키를 쓰면 아무것도 그리지 않고 조용히 넘어간다 —
 * 메뉴 하나 추가하다 아이콘 키를 오타 내도 화면이 죽지는 않게. */
export const NAV_ICONS = {
  home: Home,
  ticket: Ticket,
  plus: Plus,
  ai: Sparkles,
  sprint: CalendarDays,
  docs: FileText,
  trash: Trash2,
  chat: MessageSquare,
  game: Gamepad2,
  board: ClipboardList,
  dashboard: LayoutDashboard,
  bell: Bell,
  settings: Settings,
  audit: ScrollText,
  users: Users,
  report: BarChart3,
  check: CheckCircle2,
  backup: Database,
  maintenance: Wrench,
  diagnostics: Stethoscope,
  integration: Link2,
  workflow: Workflow,
  runner: Bot,
  policy: ShieldCheck,
  template: FileCode,
  schedule: Clock,
  profile: User,
  activity: Activity,
  org: Building2,
  jobtitle: Briefcase,
  announce: Megaphone,
  flag: Flag,
  impersonate: Eye,
  quota: Gauge,
  search: Search,
};

export function navIcon(key) {
  return (key && NAV_ICONS[key]) || null;
}
