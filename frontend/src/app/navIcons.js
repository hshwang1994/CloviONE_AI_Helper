/* 사이드바 아이콘 — 아이콘 키를 **한 계열**에 1:1 매핑 (지시 48 · P1-4).
 *
 * ## 왜 계열을 바꿨는가
 *
 * 예전에는 이 파일만 Lucide 를 썼다. 이유는 파일 자신이 적어 두었다: "기준 파일이 그리는
 * 아이콘이 정확히 이 계열이다" — 그 기준 파일(폐기한 목업)은 지시 64 로 **없앴다**(D-142).
 * 근거가 사라진 선택이 남아, 앱 하나에 아이콘 계열이 둘
 * 있는 상태가 됐다 — 사이드바는 1.8px 둥근 획, 나머지 화면(kit·상세·표·모달) 51종은 MUI.
 * 한 화면 안에서 두 계열이 만나는 자리가 실제로 있다(사이드바 옆 상단바, 설정 화면의 행).
 *
 * 남길 계열은 MUI 다: 51종 27파일이 이미 그것을 쓰고, MUI 자체가 이 앱의 필수 의존이라
 * 계열을 하나로 줄이면 `lucide-react` 를 통째로 뺄 수 있다(초기 번들 예산, 지시 26).
 *
 * 변형은 `*Outlined` 로 통일한다 — 채운 실루엣은 사이드바에서 글자보다 무겁다. 몇 개만
 * `*Rounded` 인 것은 그 이름에 Outlined 변형이 없는 경우이고, 셋 다 선(線) 도형이다.
 *
 * 키 이름은 그대로 둔다(home/ticket/plus/ai/...) — `navConfig.js` 의 표가 이 키를 쓴다.
 *
 * 개별 경로로 import 한다 — 배럴 import 를 쓰면 트리셰이킹 전에 아이콘 모듈이 전부 변환
 * 대상이 되어 개발 빌드가 눈에 띄게 느려진다(정적 검사가 같은 규칙을 강제한다).
 */

import Home from "@mui/icons-material/HomeOutlined";
import Ticket from "@mui/icons-material/ConfirmationNumberOutlined";
import Plus from "@mui/icons-material/AddRounded";
import Sparkles from "@mui/icons-material/AutoAwesomeOutlined";
import CalendarDays from "@mui/icons-material/EventNoteOutlined";
import FileText from "@mui/icons-material/DescriptionOutlined";
import Trash2 from "@mui/icons-material/DeleteOutlineRounded";
import MessageSquare from "@mui/icons-material/ForumOutlined";
import Gamepad2 from "@mui/icons-material/SportsEsportsOutlined";
import ClipboardList from "@mui/icons-material/AssignmentOutlined";
import LayoutDashboard from "@mui/icons-material/DashboardOutlined";
import Bell from "@mui/icons-material/NotificationsNoneRounded";
import Settings from "@mui/icons-material/SettingsOutlined";
import ScrollText from "@mui/icons-material/ReceiptLongOutlined";
import Users from "@mui/icons-material/GroupsOutlined";
import BarChart3 from "@mui/icons-material/BarChartOutlined";
import CheckCircle2 from "@mui/icons-material/CheckCircleOutlined";
import Database from "@mui/icons-material/StorageOutlined";
import Wrench from "@mui/icons-material/BuildOutlined";
import Stethoscope from "@mui/icons-material/MonitorHeartOutlined";
import Link2 from "@mui/icons-material/LinkOutlined";
import Workflow from "@mui/icons-material/AccountTreeOutlined";
import Bot from "@mui/icons-material/SmartToyOutlined";
import ShieldCheck from "@mui/icons-material/VerifiedUserOutlined";
import FileCode from "@mui/icons-material/ArticleOutlined";
import Clock from "@mui/icons-material/ScheduleOutlined";
import User from "@mui/icons-material/PersonOutlineRounded";
import Activity from "@mui/icons-material/TimelineOutlined";
import Building2 from "@mui/icons-material/BusinessOutlined";
import Briefcase from "@mui/icons-material/BadgeOutlined";
import Megaphone from "@mui/icons-material/CampaignOutlined";
import Flag from "@mui/icons-material/FlagOutlined";
import Eye from "@mui/icons-material/VisibilityOutlined";
import Gauge from "@mui/icons-material/SpeedOutlined";
import Search from "@mui/icons-material/SearchOutlined";
import FolderKanban from "@mui/icons-material/TopicOutlined";
import Mail from "@mui/icons-material/MailOutlineRounded";

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
  // 프로젝트는 '작업 묶음'이라 티켓(ticket)이나 리포트(report)와 다른 그림이어야 한다 —
  // 같은 아이콘을 돌려 쓰면 사이드바에서 두 항목이 한 덩어리로 보인다.
  project: FolderKanban,
  mail: Mail,
};

export function navIcon(key) {
  return (key && NAV_ICONS[key]) || null;
}
