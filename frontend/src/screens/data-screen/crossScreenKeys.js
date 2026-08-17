import { NOTI_ROOT } from "../../app/notification-keys.js";

/* 이 화면을 바꾸면 **화면 밖의 무엇이 같이 낡는가** (X10).
 *
 * 알림이 대표적이다: 목록에서 읽음 처리를 해도 상단 벨과 사이드바 배지는 다른 키로 폴링한다.
 * 지도를 한 곳에 두면 새 화면을 추가할 때 여기만 보면 된다. */
export const CROSS_SCREEN_KEYS = {
  // 알림은 이제 벨·팝오버·이 화면이 **한 뿌리**(`["noti"]`)를 쓴다 (PF9). 그래서 여기 적을
  // 것이 하나뿐이고, 그 하나가 셋을 다 덮는다 — 예전에는 세 네임스페이스를 손으로 나열해야
  // 했고 한 줄이 빠질 때마다 "읽었는데 숫자가 그대로" 가 됐다.
  notifications: [NOTI_ROOT],
  // 조직도 트리(`["org-tree"]`)는 조직·부서와 **같은 자료의 다른 보기**다. 조직 콘솔
  // (OrgConsole.jsx)이 둘을 한 화면에 나란히 놓은 뒤로는 그 어긋남이 곧바로 눈에 보인다 —
  // 오른쪽에서 부서를 추가·이름 변경·비활성화했는데 왼쪽 트리가 옛 모습 그대로면 사용자는
  // "추가했는데 조직도에 없다"로 읽는다. 조직 이름·정지 상태도 트리 맨 윗줄에 실려 있다.
  // WF44 배경 조사(L축) — 티켓 담당자 배정 드롭다운(ticket-options.js::useAssigneeOptions,
  // `["tickets","assignees"]`, staleTime 60초)이 이름과 함께 부서·직책·조직을 그대로
  // 싣는다(app/tickets/service.py::list_assignees 주석 "사용자 지시 2026-08-04"). 세 화면
  // 중 어느 하나에서 이름을 바꿔도 안 무효화하면, 다른 탭에 열린 티켓 생성/수정 모달의
  // 담당자 후보가 최대 60초간 옛 이름을 보여준다.
  organizations: [["org-tree"], ["tickets"]],
  departments: [["org-tree"], ["tickets"]],
  "job-titles": [["tickets"]],
  // 대시보드의 "실패 작업"/"미해결 실패 작업" 타일은 이 화면과 같은 사실(jobs.failed_open,
  // app/health/service.py)을 보여준다. 재시도·취소로 그 작업이 failed/queued 상태를
  // 벗어나면 서버 값은 그 자리에서 바뀌지만, 대시보드는 별도 queryKey(["dashboard"])를
  // 30초 폴링으로만 봐서 여기 매핑이 없으면 최대 30초 동안 옛 건수를 계속 보여준다
  // (알림 화면이 예전에 벨을 못 갱신했던 것과 같은 부류의 결함, 위 notifications 주석 참고).
  jobs: [["dashboard"]],
  // 공지 배너(Banners.jsx)는 AppShell에 한 번만 마운트되어 내비게이션 중에도 언마운트되지
  // 않는다 — 다른 DataScreen처럼 화면을 벗어났다 돌아오는 것만으로는 staleTime:0 재조회가
  // 일어나지 않는다. 그래서 이 화면(공지 관리)의 생성·수정·사용/사용 안 함·삭제가 배너의
  // ["announcements-active"] 캐시까지 무효화해 주지 않으면, "즉시 사라집니다"(사용 안 함
  // 확인 문구)라는 약속과 달리 다른 탭/세션은 배너의 5분 폴링이 돌 때까지 옛 상태를 본다.
  announcements: [["announcements-active"]],
  // 실행 일정 DataScreen(registry/automation.js `schedules`)과 달력(SchedulerCalendar.jsx,
  // `["scheduler-calendar", ...]`)은 같은 스케줄/실행 자료를 두 가지 보기로 보여준다 — 이 화면에서
  // 지금 실행·활성/비활성을 눌러도 달력은 별도 캐시라 반영되지 않았다(반대 방향은 SchedulerCalendar.jsx
  // 쪽 재시도/취소 mutation에서 이 키를 함께 무효화해 맞춘다).
  schedules: [["scheduler-calendar"]],
  // 승인(WF7 재감사, L축): 승인 실행기 5종(app/approvals/service.py APPROVAL_EXECUTORS)이
  // 각각 users/integrations/runners/schedules/documents 중 하나를 실제로 바꾼다 — "승인"을
  // 누른 화면과 그 대상 화면이 다른 탭에 함께 열려 있으면(관리 콘솔에서 드물지 않은 사용
  // 패턴 — 한 탭에서 승인, 다른 탭에서 대상 확인), 대상 화면은 자기 폴링/재마운트 전까지
  // 옛 값을 계속 보여줬다. 어느 승인이 어느 화면을 바꿨는지 여기서 다시 나누지 않는다 —
  // 무효화는 값싸고(그 화면이 열려 있지 않으면 아무 일도 안 한다), 거절·취소처럼 대상을
  // 안 바꾸는 액션까지 함께 걸려도 해가 없다(jobs→dashboard와 같은 "거칠지만 안전한" 판단).
  // users는 registry.js에 없는 전용 화면(Users.jsx)이라 그 자체 쿼리 키 접두어를 그대로 쓴다.
  approvals: [["users"], ["integrations"], ["runners"], ["schedules"], ["documents"]],
};
