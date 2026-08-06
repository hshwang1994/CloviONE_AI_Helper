import React from "react";
import Box from "@mui/material/Box";
import Alert from "@mui/material/Alert";
import AlertTitle from "@mui/material/AlertTitle";
import Button from "@mui/material/Button";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useToast } from "../ui/kit.jsx";
import { api } from "../lib/api.js";
import { fmtDateTime } from "../lib/format.js";
import { safeExternal } from "../lib/safeUrl.js";

/* 화면 위쪽 띠 — 세 종류가 같은 자리를 쓴다 (PLAN Phase 6).
 *
 *   1. 임퍼소네이션    — "지금 남의 눈으로 보고 있다". 닫을 수 없다.
 *   2. 시스템 상태     — "지금 티켓 동기화가 늦다" 같은 사실. 서버가 정상이라고 하면 사라진다.
 *   3. 공지            — 관리자가 띄운 것. 사용자가 닫으면 그 계정에는 다시 안 뜬다.
 *
 * **한 컴포넌트에 모은 이유.** 셋을 각자 다른 곳에서 그리면 동시에 뜰 때 순서와 간격이
 * 화면마다 달라지고, 무엇보다 "본문이 아래로 얼마나 밀리는가"를 아무도 책임지지 않는다.
 * 여기 한 곳에서 그리면 순서(위험한 것이 위)와 간격이 항상 같다.
 *
 * **폴링에 대해.** 상태는 서버가 알려 준 주기(`poll_seconds`)로만 다시 묻는다 — 프런트에
 * 숫자를 박아 두면 부하를 줄이려 할 때 배포가 두 번 필요하다. 공지는 훨씬 덜 바뀌므로
 * 그보다 느리게 돈다. 임퍼소네이션 상태는 자기 세션에 대한 것이라 짧게 본다.
 *
 * 실패하면 **조용히 아무것도 그리지 않는다**. 배너를 못 불러온 것 때문에 화면 위에
 * 빨간 오류가 뜨면, 정작 아래 본문은 멀쩡한데 사용자는 앱이 고장 났다고 읽는다.
 */

const LEVEL_SEVERITY = { info: "info", warning: "warning", critical: "error" };

function useImpersonation() {
  return useQuery({
    queryKey: ["impersonation-state"],
    queryFn: () => api("/api/admin/impersonation/state"),
    refetchInterval: 60000,
    retry: false,
    staleTime: 30000,
  });
}

function useSystemStatus() {
  const [interval_, setInterval_] = React.useState(120000);
  const query = useQuery({
    queryKey: ["system-status"],
    queryFn: () => api("/api/system/status"),
    refetchInterval: interval_,
    retry: false,
    staleTime: 30000,
  });
  React.useEffect(() => {
    const seconds = query.data && query.data.poll_seconds;
    if (seconds && seconds * 1000 !== interval_) setInterval_(seconds * 1000);
  }, [query.data, interval_]);
  return query;
}

function useAnnouncements() {
  return useQuery({
    queryKey: ["announcements-active"],
    queryFn: () => api("/api/announcements"),
    refetchInterval: 300000,
    retry: false,
    staleTime: 120000,
  });
}

function ImpersonationBanner() {
  const state = useImpersonation();
  const qc = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = React.useState(false);
  const data = state.data;
  if (!data || !data.impersonating) return null;

  const stop = async () => {
    setBusy(true);
    try {
      await api("/api/admin/impersonation/stop", { method: "POST", body: {} });
      // 역할·이름이 통째로 바뀌므로 부분 갱신이 아니라 새로 읽는다. 어중간하게 남은
      // 캐시는 "관리자인데 사용자 메뉴가 보인다" 같은 뒤섞인 화면을 만든다.
      window.location.reload();
    } catch (e) {
      setBusy(false);
      qc.invalidateQueries({ queryKey: ["impersonation-state"] });
      /* 조용히 삼키면 **관리자가 남인 채로 계속 활동**하면서 빠져나온 줄 안다 (E5).
         대리 보기 중에는 그 사람 이름으로 기록이 남으므로, 못 빠져나온 것을 모르는 것이
         가장 위험하다. */
      toast((e && e.message) || "대리 보기를 종료하지 못했습니다. 다시 시도해 주세요.", "error");
    }
  };

  return (
    <Alert
      severity="warning"
      variant="filled"
      role="status"
      sx={{ borderRadius: 0, alignItems: "center" }}
      action={
        <Button color="inherit" size="small" onClick={stop} disabled={busy} sx={{ fontWeight: 800 }}>
          {busy ? "종료 중…" : "대리 보기 종료"}
        </Button>
      }
    >
      <AlertTitle sx={{ fontWeight: 800, mb: 0 }}>
        {data.target_name || data.target_email}님의 화면을 보는 중입니다 (읽기 전용)
      </AlertTitle>
      <Box component="span" sx={{ fontSize: "0.8125rem" }}>
        {data.actor_name}(으)로 로그인한 상태이며, 이 화면에서는 어떤 변경도 저장되지 않습니다.
        {data.blocked_write_count ? ` 지금까지 차단된 변경 시도 ${data.blocked_write_count}건.` : ""}
      </Box>
    </Alert>
  );
}

function SystemStatusBanner() {
  const status = useSystemStatus();
  const notices = (status.data && status.data.notices) || [];
  if (!notices.length) return null;
  return (
    <>
      {notices.map((notice) => (
        <Alert
          key={notice.id}
          severity={LEVEL_SEVERITY[notice.level] || "info"}
          role="status"
          sx={{ borderRadius: 0 }}
        >
          {notice.message}
          {notice.since ? (
            <Box component="span" sx={{ ml: 1, opacity: 0.8, fontSize: "0.8125rem" }}>
              (마지막 정상: {fmtDateTime(notice.since)})
            </Box>
          ) : null}
          {/* 서버가 갈 곳을 함께 준 알림에만 링크가 붙는다(초기 설정 안내). "화면에서
              확인하세요"라고만 하고 가는 길을 안 주면 그 문장은 안내가 아니라 수수께끼다.
              **앱 안의 해시 경로만** 받는다 - 배너가 임의 URL로 사람을 보내는 통로가 되면
              안 된다(공지의 safeExternal과 같은 이유, 여기서는 더 좁게 본다). */}
          {typeof notice.href === "string" && notice.href.startsWith("#/") ? (
            <Box sx={{ mt: 0.5 }}>
              <Button size="small" href={notice.href} sx={{ px: 0, fontWeight: 700 }}>
                초기 설정 계속하기
              </Button>
            </Box>
          ) : null}
        </Alert>
      ))}
    </>
  );
}

function AnnouncementBanner() {
  const announcements = useAnnouncements();
  const qc = useQueryClient();
  const [dismissing, setDismissing] = React.useState({});
  const items = (announcements.data && announcements.data.items) || [];
  if (!items.length) return null;

  const dismiss = async (id) => {
    setDismissing((d) => ({ ...d, [id]: true }));
    try {
      await api(`/api/announcements/${encodeURIComponent(id)}/dismiss`, { method: "POST", body: {} });
      qc.invalidateQueries({ queryKey: ["announcements-active"] });
    } catch (e) {
      setDismissing((d) => ({ ...d, [id]: false }));
    }
  };

  return (
    <>
      {items.map((item) => (
        <Alert
          key={item.id}
          severity={LEVEL_SEVERITY[item.level] || "info"}
          role="status"
          sx={{ borderRadius: 0 }}
          onClose={item.dismissible && !dismissing[item.id] ? () => dismiss(item.id) : undefined}
        >
          <AlertTitle sx={{ fontWeight: 800, mb: item.body ? 0.5 : 0 }}>{item.title}</AlertTitle>
          {item.body ? <Box component="span" sx={{ fontSize: "0.875rem" }}>{item.body}</Box> : null}
          {safeExternal(item.link_url) ? (
            <Box sx={{ mt: 0.5 }}>
              <Button size="small" href={safeExternal(item.link_url)} sx={{ px: 0, fontWeight: 700 }}>
                {item.link_label || "자세히 보기"}
              </Button>
            </Box>
          ) : null}
        </Alert>
      ))}
    </>
  );
}

/** 위험한 것이 위. 임퍼소네이션 → 시스템 상태 → 공지 순서는 바꾸지 않는다. */
export function Banners() {
  return (
    <Box sx={{ display: "grid" }}>
      <ImpersonationBanner />
      <SystemStatusBanner />
      <AnnouncementBanner />
    </Box>
  );
}

export default Banners;
