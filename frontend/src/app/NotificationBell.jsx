import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { fmtRelative, fmtDateTime, typeKo, NOTI_FAILURE_TYPES } from "../lib/format.js";
import { Skeleton, ErrorState, useToast, useConfirm } from "../ui/kit.jsx";
import { useAuth } from "./auth.jsx";

/* 알림 벨 + 팝오버(§6.4/§14) — 아이콘을 누르면 페이지로 튀지 않고 최근 알림 팝오버를 연다.
 * 개별/전체 읽음, 관련 화면 이동(딥링크), 전체 보기, 로딩·빈·오류 상태, 열림 애니메이션.
 * 기존 백엔드 API 사용: GET /api/notifications, /unread-count, POST /{id}/read.
 * 유형→한국어(typeKo)는 lib/format.js의 공용 표를 쓴다(목록 화면과 어긋나지 않게). */
// related_object_type → 이동할 화면(딥링크 리졸버). 백엔드가 실제로 보내고, 대상 화면에서
// 그 행에 닿을 수 있는 유형만 남긴다. schedule_run은 개별 실행을 보여 주는 화면이 없어
// /schedules 목록으로 보내도 대상을 못 찾으므로 뺀다(정적 항목으로 자연스럽게 강등).
// document/workflow/integration은 알림 관련 유형으로 발신되지 않는다. runner는 실제로
// 발신된다 — app/runners/service.py가 서킷브레이커가 degraded로 트립할 때마다
// notify_admins(type_="runner_unavailable", related=("runner", runner.id))를 보낸다
// (product-quality-audit AREA=D: 이 항목의 이전 주석이 틀렸었다).
const OBJ_ROUTE = {
  approval: "/approvals", job: "/jobs", user: "/users", schedule: "/schedules", runner: "/runners",
};
// related_object_id로 그 행 하나를 바로 여는 대상 화면만(?파라미터=id 딥링크를 실제로 소비하는
// onQuery가 있는 화면) — registry.js의 OBJ_ID_PARAM과 같은 값이지만, 벨은 registry.js를 import하지
// 않으므로(순환 의존 방지) 여기 필요한 것만 로컬로 둔다. user는 아직 뺀다 — Users.jsx에 id 딥링크
// (onQuery)가 없어 ?id=를 붙여도 조용히 무시되고 그냥 전체 목록이 열린다(product-quality-audit AREA=D).
const OBJ_ID_PARAM = { approval: "id", job: "job_id", schedule: "id", runner: "id" };
function objRouteHref(objType, objId) {
  const base = OBJ_ROUTE[objType];
  const param = OBJ_ID_PARAM[objType];
  return base && param && objId != null && objId !== "" ? base + "?" + param + "=" + encodeURIComponent(objId) : base;
}
/* 서버가 계산한 딥링크(related_route). 출처는 app/notifications/destinations.py의
 * RELATED_DESTINATIONS **한 표**다 — 새 유형(chat_room 등)은 그 표만 늘리면 여기 if 를
 * 늘리지 않아도 벨이 따라온다. 위 OBJ_ROUTE/OBJ_ID_PARAM 은 서버가 아직 목적지를 계산해
 * 주지 않는 기존 관리자 유형용 폴백으로 남는다(둘을 한꺼번에 옮기면 회귀 위험만 크다).
 *
 * 서버 값이라도 그대로 믿고 이동하지 않는다: 앱 내부의 상대 경로(`/`로 시작, `//` 아님)만
 * 받는다 — 프로토콜 상대 URL(`//evil.example`)은 외부로 나가는 이동이 된다. */
function serverRoute(n) {
  const r = n && n.related_route;
  return typeof r === "string" && r.startsWith("/") && !r.startsWith("//") ? r : null;
}
// 대상 라우트의 접근 역할 — App.jsx의 SCREEN_ROLES와 같은 값을 유지한다(어긋나면 벨에선
// 클릭 가능한데 이동한 화면은 '권한이 없습니다'로 막다른 링크가 된다). 여기 없는 라우트
// (/approvals, /schedules)는 라우트 자체에 역할 제한이 없다(일반 사용자는 위 isUser로 이미 제외).
const ROUTE_ROLES = {
  "/users": ["admin", "system_admin"],
  "/jobs": ["operator", "admin", "system_admin"],
};
const FOCUSABLE = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';

/* 정적(딥링크 없는) 알림 행 — 내용이 2줄 클램프를 실제로 넘칠 때만 '펼치기' 토글로 만든다.
 * 넘치지 않는 행(제목만 있는 짧은 알림 등)까지 토글로 두면 눌러도 아무 변화가 없고
 * 스크린리더엔 "전체 내용 펼치기"라는 헛약속이 된다(product-quality-audit AREA=D). 넘침을
 * 측정해, 넘칠 때만 상호작용(버튼+캐럿+aria-expanded)을 주고 아니면 상호작용 없는 표시로 둔다. */
function StaticNotiRow({ n, content, label, expanded, onToggle }) {
  const ref = useRef(null);
  const [overflow, setOverflow] = useState(false);
  useLayoutEffect(() => {
    if (expanded) return; // 펼친 상태에선 클램프가 풀려 측정이 무의미하다.
    const node = ref.current; if (!node) return;
    let over = false;
    node.querySelectorAll(".noti-item-title, .noti-item-body").forEach((el) => {
      if (el.scrollHeight - el.clientHeight > 1) over = true;
    });
    setOverflow((prev) => (prev === over ? prev : over));
  }, [expanded, n.title, n.body]);
  if (!overflow) {
    // 전체가 이미 보이므로 클릭해도 바뀔 게 없다, 죽은 토글 대신 상호작용 없는 표시로 둔다.
    return <div ref={ref} className="noti-item-main noti-item-main--static">{content}</div>;
  }
  return (
    <button type="button" ref={ref}
      className={"noti-item-main noti-item-main--static noti-item-main--expandable" + (expanded ? " is-expanded" : "")}
      aria-expanded={expanded}
      aria-label={label + (expanded ? ", 눌러서 접기" : ", 눌러서 전체 내용 펼치기")}
      onClick={onToggle}>
      {content}
      <span className="noti-expand-caret" aria-hidden="true">⌄</span>
    </button>
  );
}

export function NotificationBell({ isUser }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const bellRef = useRef(null);
  const popRef = useRef(null);
  const navClosingRef = useRef(false); // 항목 클릭으로 이동하며 닫힐 때는 벨로 포커스를 되돌리지 않는다.
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  // 인증 상태 — 세션 만료(401) 후에도 이 컴포넌트는 마운트된 채 남을 수 있다(App.jsx의 Topbar가
  // minimal을 넘기지 않는 경로). auth.data가 없으면 쿼리를 아예 쏘지 않아, 지울 수 없는 빨간 오류
  // 표식이 60초마다 재발하는 것을 막는다.
  const auth = useAuth();
  const role = auth.data && auth.data.role;
  const isAuthed = !!role;

  /* 낙관 갱신용 — 안 읽음 총계와 **배지 숫자**를 함께 움직인다.
   *
   * 서버 응답에는 둘이 따로 있다: `unread` 는 진짜 총계이고 `badge` 는 방해금지·뮤트를
   * 반영해 화면에 그릴 숫자다(app/notifications/router.py). 한쪽만 낙관 갱신하면 항목을
   * 읽은 직후 배지만 옛 숫자에 얼어붙는다 — 예전에 unread 한쪽만 고쳐 두고 겪은 것과
   * 같은 종류의 어긋남이다. */
  const shiftUnread = (prev, delta) => {
    if (!prev || typeof prev.unread !== "number") return prev;
    const next = { ...prev, unread: Math.max(0, prev.unread + delta) };
    if (typeof prev.badge === "number") next.badge = Math.max(0, prev.badge + delta);
    return next;
  };

  const unread = useQuery({
    queryKey: ["noti-unread"],
    queryFn: () => api("/api/notifications/unread-count"),
    retry: false,
    enabled: isAuthed,
    // 401(세션 만료)로 실패했을 때만 인터벌을 멈춘다 — 안 그러면 세션 만료 중에도 60초마다
    // 계속 실패 요청을 쏘며 지울 수 없는 오류 표식을 재발시킨다. 그 밖의 실패(네트워크 순단,
    // 일시적 500 등)까지 인터벌을 영구히 멈추면, 그 이후로 뭔가 새로 와도 배지가 영영 그
    // 시점 값에 얼어붙고 아무 신호도 없다 — refetchOnWindowFocus/Mount로 자연 회복시킨다.
    refetchInterval: (q) => (isAuthed && q.state.error?.status !== 401 ? 60 * 1000 : false),
    refetchOnWindowFocus: true,
    refetchOnMount: "always",
  });
  // 안 읽음이 있으면 최근 8건이 아니라 '안 읽음 8건'을 가져온다 — 이미 읽은 항목이 더 최근이면
  // 그 안 읽음 항목이 상위 8건에서 밀려나 '안 읽음 N'이라는 헤더 숫자와 실제 보이는 항목이
  // 어긋났었다. 안 읽음이 0건일 때만 최근 혼합 목록으로 되돌아간다(계속 뭔가는 보여줘야 하므로).
  const hasUnread = typeof unread.data?.unread === "number" ? unread.data.unread > 0 : true;
  const list = useQuery({
    queryKey: ["noti-list", hasUnread ? "unread" : "recent"],
    queryFn: () => api("/api/notifications?page_size=8" + (hasUnread ? "&unread_only=true" : "")),
    retry: false,
    enabled: open && isAuthed,
    refetchInterval: (q) => (open && isAuthed && !q.state.error ? 60 * 1000 : false),  // 팝오버가 열려 있는 동안 목록이 배지와 어긋나지 않게 갱신.
    // "unread"/"recent" 변형 사이를 오갈 때(마지막 안 읽음 항목을 읽음 처리하는 순간 등) 캐시 키가
    // 바뀌어 이전엔 항목 전체가 Skeleton으로 통째로 갈아치워졌다 — 포커스가 그 안에 있었다면
    // body로 튕겨 나갔다. keepPreviousData로 새 응답이 올 때까지 이전 항목을 계속 보여준다.
    placeholderData: keepPreviousData,
  });
  // "notifications"도 함께 무효화한다 — 전체 알림 목록 화면(DataScreen, queryKey=["notifications",...])이
  // 이 벨과 별개의 react-query 네임스페이스라, 여기서 읽음 처리해도 목록 화면을 열어 두고 있으면
  // 갱신되지 않았다(product-quality-audit AREA=D). 반대 방향(목록 화면에서 읽음 처리 시 벨 갱신)은
  // DataScreen.jsx의 refresh()에서 맞춰야 한다 — 이 파일만으로는 한쪽만 고칠 수 있다.
  const invalidateNoti = () => {
    qc.invalidateQueries({ queryKey: ["noti-unread"] });
    qc.invalidateQueries({ queryKey: ["noti-list"] });
    qc.invalidateQueries({ queryKey: ["notifications"] });
  };
  // 낙관적 업데이트 — 누른 항목만 즉시 읽음으로 바꿔(체크 버튼 사라짐) 공용 mutation의 isPending이
  // 모든 미읽음 버튼을 함께 잠그거나 이중 발사되던 문제를 없앤다. 실패하면 스냅샷으로 되돌린다.
  const readOne = useMutation({
    mutationFn: (id) => api("/api/notifications/" + id + "/read", { method: "POST", body: {} }),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: ["noti-list"] });
      await qc.cancelQueries({ queryKey: ["noti-unread"] });
      // ["noti-list"]는 실제로 캐시된 키가 아니다 — 실제 쿼리는 ["noti-list","unread"|"recent"]로
      // 저장된다(위 useQuery). getQueryData/setQueryData는 정확히 일치하는 키만 찾으므로 이 줄은
      // 항상 undefined를 돌려주고 쓰기도 아무 캐시에도 닿지 않아, 낙관 업데이트가 조용히
      // 아무 효과 없이 실패했었다(hasUnread가 바뀌어 다른 변형 키로 넘어갈 때는 더 잘 드러난다).
      // getQueriesData/setQueriesData(접두어 일치)로 바꿔 지금 마운트된 변형이 무엇이든 잡는다.
      let wasUnread = false;
      qc.setQueriesData({ queryKey: ["noti-list"] }, (prevList) => {
        if (!prevList || !Array.isArray(prevList.items)) return prevList;
        if (prevList.items.some((it) => it.id === id && !it.read_at)) wasUnread = true;
        return {
          ...prevList,
          items: prevList.items.map((it) => (it.id === id && !it.read_at ? { ...it, read_at: new Date().toISOString() } : it)),
          unread: typeof prevList.unread === "number" ? Math.max(0, prevList.unread - 1) : prevList.unread,
        };
      });
      // noti-unread(벨 배지) 캐시도 같이 낙관 갱신한다 — 예전엔 noti-list만 바뀌어, 항목을 눌러
      // 즉시 팝오버가 닫히는 흐름(openItem)에서 벨 배지가 서버 무효화가 끝날 때까지 옛 값에 얼어붙었다.
      const prevUnread = qc.getQueryData(["noti-unread"]);
      if (wasUnread && prevUnread && typeof prevUnread.unread === "number") {
        qc.setQueryData(["noti-unread"], shiftUnread(prevUnread, -1));
      }
      // 실패 시 되돌릴 컨텍스트로 "이 mutation이 바꾼 것"만 넘긴다(id/wasUnread) — 전체 캐시
      // 스냅샷을 onMutate 시점으로 통째 복원하지 않는다. 두 개의 읽음 처리가 동시에 날아가고
      // 이후 mutation이 먼저 실패하면, 그 onError가 먼저 mutation의 스냅샷(=아직 아무것도 안
      // 읽음 처리되기 전)으로 캐시를 되돌려 나중 mutation이 이미 성공시킨 결과까지 함께
      // 지워버렸다(product-quality-audit AREA=D).
      return { id, wasUnread };
    },
    onError: (e, _id, ctx) => {
      if (ctx && ctx.wasUnread) {
        qc.setQueriesData({ queryKey: ["noti-list"] }, (prevList) => {
          if (!prevList || !Array.isArray(prevList.items)) return prevList;
          if (!prevList.items.some((it) => it.id === ctx.id && it.read_at)) return prevList; // 이미 되돌아갔거나 목록에서 빠짐.
          return {
            ...prevList,
            items: prevList.items.map((it) => (it.id === ctx.id ? { ...it, read_at: null } : it)),
            unread: typeof prevList.unread === "number" ? prevList.unread + 1 : prevList.unread,
          };
        });
        const cur = qc.getQueryData(["noti-unread"]);
        if (cur && typeof cur.unread === "number") qc.setQueryData(["noti-unread"], shiftUnread(cur, 1));
      }
      toast(e.message || "읽음 처리하지 못했습니다.", "error");
    },
    onSettled: invalidateNoti,
  });
  // '모두 읽음'은 로드된 8건이 아니라 서버에서 전체 미읽음을 한 번에 처리한다.
  const readAll = useMutation({
    mutationFn: () => api("/api/notifications/read-all", { method: "POST", body: {} }),
    // 낙관적 처리 — 로드된 목록을 즉시 전부 읽음으로 바꾸고 배지를 0으로. 실패하면 스냅샷으로 되돌린다.
    // (확인 모달로 팝오버가 닫혀도 배지/목록 반영 지연이 눈에 덜 띄게.)
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: ["noti-list"] });
      // readOne의 onMutate와 짝을 맞춘다 — 이게 없으면 '모두 읽음'을 누른 순간 이미 날아가 있던
      // noti-unread 백그라운드 재조회(60초 인터벌/포커스 시)가 낙관 업데이트보다 늦게 응답해
      // 배지를 옛 값으로 되돌려 버렸다(product-quality-audit AREA=D).
      await qc.cancelQueries({ queryKey: ["noti-unread"] });
      // readOne과 같은 이유로 접두어 일치 버전을 쓴다 — ["noti-list"] 단독 키는 캐시에 없다.
      const now = new Date().toISOString();
      // 되돌리기용으로 "이 mutation이 실제로 안읽음→읽음 뒤집은 id"만 모은다 — onError에서
      // 고정 스냅샷 통째 복원 대신 이 id들만 되돌려, 동시에 끝난 다른(readOne) 낙관 업데이트를
      // 지우지 않는다(readOne.onMutate 주석과 같은 이유, product-quality-audit AREA=D).
      const changedIds = new Set();
      qc.setQueriesData({ queryKey: ["noti-list"] }, (prev) => {
        if (!prev || !Array.isArray(prev.items)) return prev;
        return {
          ...prev,
          items: prev.items.map((it) => {
            if (it.read_at) return it;
            changedIds.add(it.id);
            return { ...it, read_at: now };
          }),
          unread: 0,
        };
      });
      // noti-unread(벨 배지) 캐시도 같이 0으로 — readOne과 같은 이유(§readOne.onMutate 주석).
      // 안 그러면 목록은 즉시 다 읽음으로 보이는데 배지 숫자는 서버 무효화가 끝날 때까지 그대로 남아
      // "모두 읽음"을 눌렀는데 안 읽음처럼 보이는 깜빡임이 있었다.
      const prevUnread = qc.getQueryData(["noti-unread"]);
      if (prevUnread && typeof prevUnread.unread === "number") {
        qc.setQueryData(["noti-unread"], { ...prevUnread, unread: 0, ...(typeof prevUnread.badge === "number" ? { badge: 0 } : null) });
      }
      // 배지 복구는 changedIds.size(로드된 ≤8건)가 아니라 이 실제 전체 미읽음 스냅샷으로
      // 되돌린다 — 안 그러면 실제 미읽음이 8을 넘을 때(예: 15) 실패 후 배지가 8로 과소
      // 복구됐다(product-quality-audit AREA=D). onSettled 무효화로 결국 맞춰지지만 그 사이의
      // 배지 숫자도 정직해야 한다.
      const prevUnreadCount = prevUnread && typeof prevUnread.unread === "number" ? prevUnread.unread : null;
      return { changedIds, prevUnreadCount };
    },
    onError: (e, _v, ctx) => {
      if (ctx && ctx.changedIds && ctx.changedIds.size) {
        // 캐시에 "unread"/"recent" 두 변형이 동시에 남아 있을 수 있어(setQueriesData는 접두어가
        // 일치하는 모든 쿼리를 돈다) 복구 카운트는 콜백마다 각자 새로 센다 — 바깥 공유 변수를
        // 쓰면 두 번째 변형이 첫 번째 변형의 복구분까지 더해 unread를 부풀린다.
        qc.setQueriesData({ queryKey: ["noti-list"] }, (prev) => {
          if (!prev || !Array.isArray(prev.items)) return prev;
          let restored = 0;
          const items = prev.items.map((it) => {
            if (ctx.changedIds.has(it.id) && it.read_at) { restored += 1; return { ...it, read_at: null }; }
            return it;
          });
          return { ...prev, items, unread: typeof prev.unread === "number" ? prev.unread + restored : prev.unread };
        });
        const cur = qc.getQueryData(["noti-unread"]);
        if (cur && typeof cur.unread === "number") {
          qc.setQueryData(["noti-unread"], { ...cur, unread: ctx.prevUnreadCount != null ? ctx.prevUnreadCount : cur.unread + ctx.changedIds.size });
        }
      }
      toast(e.message || "모두 읽음 처리하지 못했습니다.", "error");
    },
    // 백엔드가 실제 처리 건수(read_count)를 준다 — 전체 목록 화면과 문구를 맞춘다.
    onSuccess: (res) => { const n = res && typeof res.read_count === "number" ? res.read_count : null; toast(n != null ? n + "건을 읽음 처리했습니다." : "모든 알림을 읽음 처리했습니다.", "success"); },
    onSettled: invalidateNoti,
  });

  useEffect(() => {
    if (!open) return undefined;
    // 팝오버 밖 클릭이면 닫되, '모두 읽음' 확인 모달(앱 루트에 렌더돼 ref 밖에 있음)을 누른 것은
    // 무시한다 — 안 그러면 확인 다이얼로그를 누르는 순간 팝오버가 사라진다.
    const onDoc = (e) => {
      if (!ref.current || ref.current.contains(e.target)) return;
      if (e.target.closest && e.target.closest('.k-modal, .k-modal-overlay, [role="dialog"]')) return;
      setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") { setOpen(false); return; }
      if (e.key === "Tab" && popRef.current) {
        const els = Array.prototype.filter.call(popRef.current.querySelectorAll(FOCUSABLE), (el) => el.offsetParent !== null);
        if (!els.length) return;
        const first = els[0], last = els[els.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    // 열릴 때 포커스를 팝오버 안으로, 닫힐 때 벨로 복귀.
    const t = window.setTimeout(() => {
      const node = popRef.current; if (!node) return;
      const first = node.querySelector(FOCUSABLE);
      (first || node).focus();
    }, 0);
    return () => {
      window.clearTimeout(t);
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
      // 항목 클릭으로 다른 화면으로 이동해 닫히는 경우엔 벨로 포커스를 되돌리지 않는다(새 화면에 포커스가 가야 함).
      if (!navClosingRef.current && bellRef.current && typeof bellRef.current.focus === "function") { try { bellRef.current.focus(); } catch (e) { /* ignore */ } }
      navClosingRef.current = false;
    };
  }, [open]);

  const items = (list.data && list.data.items) || [];
  const rawCount = unread.data && unread.data.unread;
  // 목록 응답에도 전체 미읽음 수(unread)가 들어온다. 팝오버가 열려 목록을 받았으면 그 스냅샷을
  // 헤더 수로 신뢰해 헤더-목록 불일치(두 쿼리의 60s 타이머가 어긋나던 문제)를 없애고,
  // unread-count 조회가 실패하면 목록의 unread로 폴백한다.
  // list.isError면 list.data는 마지막으로 성공했던 응답(react-query 기본 동작)일 수 있다 — 헤더
  // 숫자·힌트가 몸통(ErrorState로 전환)과 다른 이야기를 하지 않도록, 에러 상태에선 이 스냅샷을
  // 신뢰하지 않고 unread-count 조회(rawCount)로만 폴백한다(product-quality-audit AREA=D).
  const listUnread = (!list.isError && list.data && typeof list.data.unread === "number") ? list.data.unread : null;
  const count = (open && listUnread != null) ? listUnread
    : (typeof rawCount === "number" ? rawCount : (listUnread != null ? listUnread : 0));
  // 카운트를 정말 알 수 없을 때만(둘 다 실패) 경고 표식. 목록 폴백이 있으면 0으로 뭉개지 않는다.
  const countError = unread.isError && listUnread == null;
  // 팝오버 몸통이 오류 상태면 헤더가 "안 읽음 N"이나 '모두 읽음'을 자신 있게 말하는 것은
  // 몸통의 '불러오지 못했습니다'와 모순된다 — 그때는 헤더 숫자·일괄 액션을 감춘다(product-quality-audit AREA=D).
  const listError = open && list.isError;
  // 최초 로드가 아직 안 끝났으면(느린 네트워크) 배지가 "확실히 0"과 똑같이 보였다 — 로딩 중인지
  // 정말 0인지 구분할 길이 없었다. unread 쿼리가 한 번이라도 응답(성공/실패)하기 전까지만 표시.
  const countPending = !unread.isFetched && !countError && count === 0;
  /* 방해금지·뮤트 — **알림은 그대로 쌓이고 배지만 조용해진다**(app/profiles/prefs.py).
   *
   * 그래서 이 컴포넌트는 두 숫자를 다르게 쓴다:
   *   count  = 진짜 안 읽음 총계. 팝오버 헤더와 목록은 끝까지 이 숫자를 말한다.
   *   badge  = 서버가 계산한 '지금 눈길을 끌 숫자'. 조용하면 0 이다.
   * 조용한데 안 읽음이 있으면 빨간 숫자 대신 **조용한 점**을 띄운다 — 배지를 통째로
   * 없애면 사용자가 "조용히 해 둔 것"과 "아무것도 안 온 것"을 구분할 수 없다.
   * badge 를 안 주는 옛 응답(캐시)에서는 count 로 폴백해 예전과 똑같이 동작한다. */
  const badge = unread.data && typeof unread.data.badge === "number" ? unread.data.badge : count;
  const quiet = !!(unread.data && unread.data.quiet) || (badge === 0 && count > 0);
  const quietTitle = count > 0
    ? `방해금지, 알림 끔 설정 때문에 조용합니다 (안 읽음 ${count}건)`
    : "방해금지 중입니다";

  async function markAll() {
    // 전체 페이지의 '모두 읽음'과 동작을 맞춘다(되돌릴 수 없는 일괄 처리라 확인을 받는다).
    const ok = await confirm("모든 알림을 읽음 처리할까요?", { confirmLabel: "모두 읽음" });
    if (ok) readAll.mutate();
  }
  // readOne은 항목 전체가 공유하는 단일 mutation이라 isPending/variables로는 '지금 어느 버튼이
  // 요청 중인지'를 정확히 구분할 수 없다 — A를 누른 뒤 응답 전에 B를 누르면 variables가 B로
  // 바뀌어 A의 버튼이 다시 눌려 A에 대해 중복 요청이 나갈 수 있었다. 진행 중인 id를 직접 추적한다.
  const [pendingIds, setPendingIds] = useState(() => new Set());
  // 딥링크가 없는(정적) 항목의 '펼치기' 토글 상태 — 2줄로 잘린 title/body를 눌러서 전체 보기.
  const [expandedIds, setExpandedIds] = useState(() => new Set());
  // 진행 중 id를 pendingIds에 넣고 mutate하고 정리까지 한곳에서 — markOne과 openItem이 같은
  // 가드를 공유하게 한다. 예전엔 openItem이 pendingIds에 넣지 않아, 항목 본문을 빠르게 더블
  // 클릭하면 같은 id로 POST /{id}/read가 두 번 나갔다(product-quality-audit AREA=D).
  function runReadOne(id) {
    setPendingIds((s) => { if (s.has(id)) return s; const n = new Set(s); n.add(id); return n; });
    readOne.mutate(id, {
      onSettled: () => setPendingIds((s) => { if (!s.has(id)) return s; const n = new Set(s); n.delete(id); return n; }), });
  }
  function markOne(e, id) {
    e.stopPropagation();
    if (pendingIds.has(id)) return;
    runReadOne(id);
  }
  function openItem(n) {
    if (!n.read_at && !pendingIds.has(n.id)) runReadOne(n.id);
    // related_object_id가 있고 대상 화면이 id 딥링크를 지원하면(OBJ_ID_PARAM) 목록 전체가 아니라
    // 그 행 하나를 바로 연다, 전체 알림 화면(registry.js)이 이미 하는 것과 같은 동작
    // (product-quality-audit AREA=D). 서버가 목적지를 계산해 준 유형은 그 값이 먼저다.
    const route = serverRoute(n) || objRouteHref(n.related_object_type, n.related_object_id);
    if (route) navClosingRef.current = true; // 이동으로 닫히므로 포커스를 벨로 되돌리지 않음.
    setOpen(false);
    if (route) nav(route);
  }

  return (
    <div className="noti" ref={ref}>
      <button ref={bellRef} type="button" className="c-icon-btn noti-bell"
        aria-label={"알림" + (count ? " (읽지 않음 " + count + ")" : "") + (quiet ? " (방해금지 중: 배지만 조용함)" : "") + (countError ? " (개수를 불러오지 못함)" : "")}
        aria-haspopup="dialog" aria-expanded={open} aria-controls="noti-pop"
        onClick={() => { if (!open && unread.isError) unread.refetch(); setOpen((v) => !v); }}>
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
          strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {badge ? (
          // countError가 true인데 count도 0이 아닐 수 있다, unread 쿼리가 실패했지만 이전에
          // 캐시된 숫자가 남아 있는 경우(react-query 기본 동작)다. 그때는 배지가 최신 여부를
          // 알려주는 신호 없이 그냥 숫자만 보였다, aria-label엔 이미 "개수를 불러오지 못함"이
          // 붙지만 마우스로 보는 사용자에겐 아무 표시가 없었다(product-quality-audit AREA=D).
          <span className={"noti-count" + (countError ? " noti-count--stale" : "")}
            title={countError ? "표시된 숫자가 최신이 아닐 수 있습니다" : undefined}>
            {badge > 99 ? "99+" : badge}
          </span>
        )
          // 조용한 상태 — 안 읽음은 있는데 배지가 0이다. 아무 표시도 안 하면 "안 온 것"과
          // 구분이 안 되므로 중립색 점 하나로 "쌓여 있지만 조용히 하고 있다"를 말한다.
          : quiet ? <span className="noti-quiet" aria-hidden="true" title={quietTitle} />
          // aria-hidden 이유: 설명은 벨 버튼의 aria-label에 이미 있어 스크린리더 사용자는
          // 안내를 받지만, title이 없어 마우스로 보는 사용자는 색 점의 의미를 알 방법이
          // 없었다, title을 더해 마우스/터치 사용자도 같은 설명을 보게 한다.
          : countError ? <span className="noti-err" aria-hidden="true" title="알림 개수를 불러오지 못했습니다" />
          // 로딩 중(아직 한 번도 응답을 못 받음)에는 "확실히 0건"과 시각적으로 구분되는
          // 중립색 점만 보인다, 배지가 아예 없는 것과 달라 "안 온 건지 아직 안 불렀는지"를 구분한다.
          : countPending ? <span className="noti-pending" aria-hidden="true" title="알림 개수를 불러오는 중" /> : null}
      </button>
      {/* 방해금지 중에는 이 낭독도 멈춘다 — 스크린리더 사용자에게 라이브 리전은 곧 푸시다.
          시각 배지만 끄고 여기를 켜 두면 '조용히 해 달라'는 요청을 절반만 지키는 셈이다.
          숫자는 벨을 눌러 팝오버를 열면 그대로 다 들린다(삼키는 것이 아니다). */}
      <span className="sr-only" aria-live="polite">{!quiet && count ? "읽지 않은 알림 " + count + "건" : ""}</span>
      {open ? (
        // role="dialog"는 구조(팝오버)를 알리는 용도로만 남긴다, aria-modal="true"는 배경이
        // 실제로 inert해야 정직한데, 이 팝오버는 사이드바, 상단바, 본문이 전부 계속 상호작용
        // 가능하고 body 스크롤도 잠그지 않는다(kit.jsx Modal과 달리). aria-modal을 켜 둔 채
        // 두면 스크린리더가 "배경은 닿을 수 없다"고 잘못 안내한다(product-quality-audit AREA=D).
        <div className="noti-pop" id="noti-pop" role="dialog" aria-label="알림" ref={popRef} tabIndex={-1}>
          <div className="noti-pop-head">
            <span>알림{count && !listError ? ", 안 읽음 " + count : ""}</span>
            {/* 몸통이 오류면 헤더 숫자, '모두 읽음'을 감춰 한 팝오버 안에서 상반된 메시지를 없앤다.
                개수 조회만 실패한 경우엔(countError) 수동 재시도 진입로를 준다(product-quality-audit AREA=D). */}
            {listError ? null
              : countError ? <button type="button" className="noti-link" onClick={() => unread.refetch()}>개수 다시 불러오기</button>
              : count > 0 ? <button type="button" className="noti-link" onClick={markAll} disabled={readAll.isPending}>모두 읽음</button>
              : null}
          </div>
          {/* 안 읽음이 page_size(8건)보다 많으면 헤더 숫자와 실제 보이는 행 수가 어긋난다 —
              무엇이 더 있는지 명시적으로 알려준다(product-quality-audit AREA=D). */}
          {!list.isPending && !list.isError && items.length > 0 && items.length < count ? (
            <div className="noti-pop-hint">{items.length}건 표시 중, 전체 보기에서 나머지 확인</div>
          ) : null}
          <div className="noti-pop-body">
            {/* v5에서 isLoading은 isPending && isFetching이다, enabled:open이라 팝오버가 막
                열려 fetch가 아직 이펙트로 발사되기 전 프레임엔 isPending=true인데 isFetching이
                아직 false라 isLoading이 false로 잡혀, '로딩 중'도 '빈 목록'도 아닌 순간이 있었다. */}
            {list.isPending ? <div className="noti-loading"><Skeleton lines={3} /></div>
              // 앱 전역의 401/403 오류 패턴을 그대로 쓴다(kit.jsx의 ErrorState), 세션 만료 시
              // '로그인이 필요합니다' + 로그인 링크를 보이고, 소용없는 재시도 버튼을 숨긴다.
              // 자체 오류 UI를 만들지 않는다.
              : list.isError ? <div className="noti-pop-error"><ErrorState error={list.error} onRetry={() => list.refetch()} /></div>
              : items.length === 0 ? (
                <div className="noti-empty">
                  {/* 트리거 버튼과 같은 종 아이콘을 흐리게만 재사용하면 '장식이 흐려진 벨'로 보여
                      플레이스홀더처럼 읽힌다, '다 확인함'을 뜻하는 별개의 체크 아이콘으로 바꾼다. */}
                  <svg className="noti-empty-icon" width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <circle cx="12" cy="12" r="9" /><path d="M8 12.5l2.5 2.5L16 9.5" />
                  </svg>
                  <div className="noti-empty-title">새 알림이 없습니다</div>
                  {/* 일반 사용자에겐 승인, 작업 실패 알림이 거의 오지 않으므로(notify_admins는 관리자 대상)
                      관리자 중심 예시 대신 중립적 문구를 쓴다. */}
                  <div className="noti-empty-help">{isUser ? "나에게 온 알림이 여기에 표시됩니다." : "승인, 작업 실패 등 나에게 온 알림이 여기에 표시됩니다."}</div>
                </div>
              )
              : items.map((n) => {
                // 일반 사용자에겐 딥링크 대상(관리자 화면)이 없다, 예전엔 아무 항목이나 눌러도
                // /chat으로 튕겨 '어딘가 열린다'는 착각만 줬다. 사용자 항목은 정적으로 두고
                // 읽음 처리는 옆의 체크 버튼이, 전체 보기는 하단 링크가 담당한다.
                // '일반 사용자가 아니다'만으로는 부족하다, 예: auditor는 job_failed/user 알림을
                // 받을 수 있지만 /jobs, /users 라우트 접근 권한이 없어 누르면 '권한이 없습니다'로
                // 막힌다. 대상 라우트가 역할 제한을 두면 뷰어 역할이 포함될 때만 누를 수 있게 한다.
                // 서버가 목적지를 준 유형(채팅 초대 등)은 일반 사용자도 눌러서 갈 수 있어야 한다 —
                // 아래 isUser 게이트는 '관리자 화면으로만 가는 폴백 표'를 위한 것이지 딥링크 일반
                // 금지가 아니다. 채팅방은 모든 역할이 접근할 수 있는 사용자 세그먼트 화면이다.
                const srvRoute = serverRoute(n);
                const targetRoute = OBJ_ROUTE[n.related_object_type];
                const routeAllows = !ROUTE_ROLES[targetRoute] || (role && ROUTE_ROLES[targetRoute].includes(role));
                const navigable = !!srvRoute || (!isUser && !!targetRoute && routeAllows);
                // related_object_id + OBJ_ID_PARAM이 있으면 그 행 하나를 여는 실제 딥링크다 -
                // 없으면 여전히 대상 화면의 일반 목록만 연다. 안내 문구(title/aria-label)를
                // 실제 동작과 맞춘다(product-quality-audit AREA=D, 예전엔 항상 "목록"이라고만
                // 말해, 이제 행 하나를 정확히 여는 유형에서도 실제보다 못한 약속을 했다).
                const hasItemLink = !!srvRoute
                  || (!!OBJ_ID_PARAM[n.related_object_type] && n.related_object_id != null && n.related_object_id !== "");
                const isFailure = NOTI_FAILURE_TYPES.has(n.type);
                const expanded = expandedIds.has(n.id);
                // 스크린리더 이름, 이동 가능 버튼과 정적 펼치기 버튼이 같은 본문 설명을 공유한다.
                const ariaLabel = (n.read_at ? "" : "안 읽음, ") + typeKo(n.type) + ": " + n.title + (n.body ? ", " + n.body : "") + ", " + fmtRelative(n.created_at);
                const content = (<>
                  {/* 배경 틴트(7%)만으로는 안 읽음 구분이 약했다(특히 다크 모드), 스크린리더용
                      sr-only 텍스트 옆에 눈에 보이는 점 표식도 더한다(CSS는 global.css). */}
                  {!n.read_at ? <span className="noti-unread-dot" aria-hidden="true" /> : null}
                  {!n.read_at ? <span className="sr-only">안 읽음 </span> : null}
                  {/* 장애/실패류(NOTI_FAILURE_TYPES)는 유형 라벨에 강조색을 더해, 승인 결정, 점검
                      공지 같은 정보성 알림과 섞여도 급한 것부터 눈에 띈다(global.css, product-quality-audit AREA=D). */}
                  <span className={"noti-item-type" + (isFailure ? " noti-item-type--failure" : "")}>{typeKo(n.type)}</span>
                  {/* 2줄로 잘리는 title/body, 마우스 사용자가 잘린 부분을 볼 방법이 없었다.
                      아래 시각(time) span과 같은 title 폴백 패턴을 맞춘다. */}
                  <span className="noti-item-title" title={n.title}>{n.title}</span>
                  {n.body ? <span className="noti-item-body" title={n.body}>{n.body}</span> : null}
                  <span className="noti-item-time" title={fmtDateTime(n.created_at)}>{fmtRelative(n.created_at)}</span>
                </>);
                return (
                <div key={n.id} className={"noti-item" + (n.read_at ? "" : " is-unread")}>
                  {/* aria-label은 항상 자식 subtree 텍스트(안 읽음, 유형, 제목, 본문, 시각)를 이긴다 -
                      예전엔 일반적인 "관련 목록 열기"만 있어 스크린리더 사용자가 팝오버의 모든
                      항목을 구분 없이 "관련 목록 열기, 버튼"으로만 들었다. 실제 알림 내용을
                      접근성 이름에 담고, '무엇을 누르면 어디로 가는지'는 title(마우스 사용자용)에 둔다. */}
                  {navigable
                    ? <button type="button" className="noti-item-main" title={hasItemLink ? "관련 항목 보기" : "관련 목록 열기"}
                        aria-label={ariaLabel}
                        onClick={() => openItem(n)}>{content}</button>
                    // 딥링크 대상이 없는(정적) 알림, 잘린 title/body를 눌러서 펼친다. 단 실제로
                    // 2줄을 넘칠 때만 토글이 되게 StaticNotiRow가 넘침을 측정한다(product-quality-audit AREA=D).
                    : <StaticNotiRow n={n} content={content} label={ariaLabel} expanded={expanded}
                        onToggle={() => setExpandedIds((s) => {
                          const next = new Set(s);
                          if (next.has(n.id)) next.delete(n.id); else next.add(n.id);
                          return next;
                        })} />}
                  {!n.read_at ? (
                    <button type="button" className="noti-item-read" aria-label="읽음 표시" title="읽음 표시"
                      disabled={pendingIds.has(n.id)} onClick={(e) => markOne(e, n.id)}>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
                        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg>
                    </button>
                  ) : null}
                </div>
                );
              })}
          </div>
          {/* 일반 사용자도 최근 8건 너머의 알림에 닿을 수 있게 전체 보기를 항상 제공한다
              (/notifications는 App.jsx에서 사용자도 접근 가능한 뷰로 열어 둔다). */}
          <div className="noti-pop-foot">
            <button type="button" className="noti-link" onClick={() => { setOpen(false); nav("/notifications"); }}>전체 알림 보기</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
