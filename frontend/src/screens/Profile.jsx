import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import DevicesOtherRoundedIcon from "@mui/icons-material/DevicesOtherRounded";
import { api } from "../lib/api.js";
import { fmtDateTime, fmtRelative } from "../lib/format.js";
import { useAuth } from "../app/auth.jsx";
import { ROLE_KO } from "../app/navConfig.js";
import {
  Badge, Button, Callout, Card, EmptyState, ErrorState, PageHeader, Skeleton,
  useConfirm, useToast,
} from "../ui/kit.jsx";

/* 내 프로필 — 아바타 · 알림 설정 · 방해금지 · 내 기기(세션) (계획서 Phase 6 사용자).
 *
 * 예전에는 상단바 메뉴의 작은 모달 하나가 역할·부서·마지막 로그인만 읽어 주고 끝이었다.
 * "활성 세션 3개"라고 알려 주면서 정작 끊을 방법은 없어서, 그 숫자를 본 사람이 할 수 있는
 * 일이 비밀번호 변경뿐이었다. 이 화면이 그 공백을 메운다.
 *
 * 이 화면이 지키는 두 가지:
 *   1) **방해금지는 미루는 것이지 삼키는 것이 아니다.** 화면 문구도 그렇게 쓴다 —
 *      "알림은 그대로 쌓이고 배지만 조용해집니다". 사용자가 무엇을 포기하는지 모르는 채
 *      켜게 두면, 놓친 다음 날 이 기능을 영영 안 쓴다.
 *   2) **지금 쓰는 기기를 표시한다.** 어느 줄이 이 창인지 모르면 무서워서 아무것도 못 끊는다.
 *
 * px 폰트 크기를 쓰지 않는다(4K 레버는 루트 폰트사이즈 하나다). MUI Grid 도 쓰지 않는다
 * (MUI 7 에서 xs={12} 가 조용히 무시된다) — Box + display:grid 다.
 */

/* 같은 줄 카드는 **높이를 맞춘다** — 사용자 지적 Q5("카드 크기가 제각각").
 *
 * 예전에는 `alignItems: "start"` 라 각 카드가 제 내용 높이를 가졌다. 실측: 사진/세션 줄이
 * 563 vs 358(편차 205px), 알림/방해금지 줄이 690 vs 322(편차 368px) — 아래 모서리가
 * 들쭉날쭉해서 "정리가 안 된 화면" 으로 읽힌다. 기준 목업은 같은 줄 편차가 0 이다.
 *
 * 짧은 카드에 여백이 생기는 것은 감수한다. 카드 안 여백은 흔하고(스탯 카드가 이미 그렇다),
 * 줄 바닥이 어긋나는 것보다 훨씬 덜 눈에 띈다. */
const TWO_COL = {
  display: "grid", gap: 2.5, alignItems: "stretch",
  gridTemplateColumns: {
    xs: "minmax(0, 1fr)",
    lg: "minmax(0, 1fr) minmax(0, 1fr)",
    xxl: "minmax(0, 1fr) minmax(0, 1fr)",
  },
};

// 방해금지 빠른 시간. '무한'을 기본으로 두지 않는다 — 실수로 켜 두고 잊는 것이 이 기능의
// 가장 흔한 실패다.
const DND_PRESETS = [
  { minutes: 30, label: "30분" },
  { minutes: 60, label: "1시간" },
  { minutes: 180, label: "3시간" },
  { minutes: 0, label: "직접 끌 때까지" },
];

function SectionTitle({ children, help }) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography component="h2" variant="h6" sx={{ fontSize: "1.0625rem" }}>{children}</Typography>
      {help ? (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, maxWidth: "70ch" }}>
          {help}
        </Typography>
      ) : null}
    </Box>
  );
}

function Row({ label, children }) {
  return (
    <Box sx={{
      display: "grid", gap: 1, py: 1.25, borderBottom: 1, borderColor: "divider",
      gridTemplateColumns: { xs: "minmax(0,1fr)", sm: "10rem minmax(0,1fr)" },
    }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Box sx={{ minWidth: 0 }}>{children}</Box>
    </Box>
  );
}

/* 아바타 + 계정 요약. 업로드는 기존 네임스페이스 업로드 경로를 그대로 쓴다(서버가 매직바이트로
 * 형식을 판정한다) — 화면은 확장자를 믿지 않고 서버 판정 결과만 받는다. */
function AccountCard({ profile, prefs, onChanged }) {
  const auth = useAuth();
  const toast = useToast();
  const confirm = useConfirm();
  const fileRef = React.useRef(null);
  const [busy, setBusy] = React.useState(false);
  const name = profile.display_name || (auth.data && auth.data.display_name) || "";
  const avatarUrl = (prefs && prefs.avatar && prefs.avatar.url) || profile.avatar_url || null;

  async function upload(file) {
    if (!file) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      await api("/api/me/avatar", { method: "POST", body: form });
      toast("프로필 사진을 바꿨습니다.", "success");
      onChanged();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
      // 같은 파일을 다시 고를 수 있게 값을 비운다(안 그러면 change 이벤트가 안 난다).
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function remove() {
    if (!(await confirm("기본 이니셜 아바타로 돌아갑니다.", { title: "프로필 사진 삭제", confirmLabel: "삭제" }))) return;
    setBusy(true);
    try {
      await api("/api/me/avatar", { method: "DELETE" });
      toast("프로필 사진을 지웠습니다.", "success");
      onChanged();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <SectionTitle help="사진은 이 조직 안에서만 보입니다. PNG, JPEG, GIF, WebP, 10MB까지.">
        계정
      </SectionTitle>
      <Box sx={{ display: "flex", gap: 3, alignItems: "center", flexWrap: "wrap", mb: 2 }}>
        <Avatar
          src={avatarUrl || undefined}
          alt=""
          sx={{ width: "5rem", height: "5rem", fontSize: "2rem", bgcolor: "primary.main" }}
        >
          {name ? name[0] : "?"}
        </Avatar>
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          {/* 파일 입력은 숨기고 버튼으로 연다 — 기본 파일 입력은 브라우저마다 생김새가 달라
              4K에서 혼자 작게 남는다. 라벨은 버튼이 갖는다(스크린리더도 버튼을 읽는다). */}
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/gif,image/webp"
            style={{ display: "none" }}
            onChange={(e) => upload(e.target.files && e.target.files[0])}
            aria-hidden="true"
            tabIndex={-1}
          />
          <Button variant="primary" disabled={busy} onClick={() => fileRef.current && fileRef.current.click()}>
            {busy ? "처리 중…" : "사진 바꾸기"}
          </Button>
          {avatarUrl ? <Button disabled={busy} onClick={remove}>사진 삭제</Button> : null}
        </Box>
      </Box>
      <Row label="이름">{name || "-"}</Row>
      <Row label="이메일">{profile.email || "-"}</Row>
      <Row label="역할">{profile.role ? (ROLE_KO[profile.role] || profile.role) : "-"}</Row>
      <Row label="부서">{profile.department || "-"}</Row>
      <Row label="직책">{profile.title || "-"}</Row>
      <Row label="마지막 로그인">{profile.last_login_at ? fmtDateTime(profile.last_login_at) : "-"}</Row>
      <Row label="Notion 연결">
        {profile.notion_mapping_status ? <Badge value={profile.notion_mapping_status} /> : "-"}
      </Row>
      <Box sx={{ mt: 2, display: "flex", gap: 1, flexWrap: "wrap" }}>
        <Button component="a" href="/change-password">비밀번호 변경</Button>
      </Box>
    </Card>
  );
}

/* 알림 설정 — 유형별 뮤트. 목록은 **서버가 준다**(prefs.notifications.catalog).
 * 프런트에 유형 목록을 복사해 두면 서버가 유형을 늘려도 화면에는 영영 안 나온다. */
function NotificationCard({ prefs, save, saving }) {
  const muted = new Set(prefs.notifications.muted_types || []);
  const toggle = (key) => {
    const next = new Set(muted);
    if (next.has(key)) next.delete(key); else next.add(key);
    save({ muted_types: Array.from(next) });
  };
  return (
    <Card>
      <SectionTitle help="끈 유형도 알림 목록에는 그대로 남습니다. 배지 숫자(빨간 점)에서만 빠집니다. 알림을 없애는 것이 아니라 조용히 하는 것입니다.">
        알림 설정
      </SectionTitle>
      <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5 }}>
        {prefs.notifications.catalog.map((row) => (
          <Box component="li" key={row.key} sx={{ display: "flex", alignItems: "center", gap: 2, py: 0.75, borderBottom: 1, borderColor: "divider" }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography sx={{ fontWeight: 650 }}>{row.label}</Typography>
              <Typography variant="body2" color="text.secondary">{row.help}</Typography>
            </Box>
            {/* MUI 7 의 Switch 는 `inputProps` 를 **조용히 버린다** — 그렇게 쓰면 스위치에
                접근 가능한 이름이 아예 없어 스크린리더가 이름 없는 컨트롤로 읽는다(테스트에서
                실제로 잡았다). slotProps.input 이 <input> 에 닿는 유일한 통로다. */}
            <Switch
              checked={!muted.has(row.key)}
              disabled={saving}
              onChange={() => toggle(row.key)}
              slotProps={{ input: { "aria-label": `${row.label} 배지 알림` } }}
            />
          </Box>
        ))}
      </Box>
      <Callout>
        계정 잠금처럼 보안에 관한 알림은 끌 수 없습니다. 침해를 알리는 유일한 신호이기 때문입니다.
      </Callout>
    </Card>
  );
}

/* 방해금지 — '지금 조용히'(수동)와 '매일 이 시간대'(조용시간) 두 가지. */
function DndCard({ prefs, save, saving }) {
  const dnd = prefs.dnd;
  const [start, setStart] = React.useState(dnd.quiet_start);
  const [end, setEnd] = React.useState(dnd.quiet_end);
  React.useEffect(() => { setStart(dnd.quiet_start); setEnd(dnd.quiet_end); }, [dnd.quiet_start, dnd.quiet_end]);

  return (
    <Card>
      <SectionTitle help="방해금지 중에도 알림은 평소대로 쌓입니다. 사이드바 배지만 조용해지고, 끄면 그동안 쌓인 것이 한꺼번에 다시 보입니다.">
        방해금지
      </SectionTitle>

      {dnd.quiet_now ? (
        <Callout tone="warn">
          지금 조용한 상태입니다({dnd.reason === "manual" ? "직접 켬" : "조용시간"}).
          {dnd.until ? ` ${fmtDateTime(dnd.until)}에 자동으로 풀립니다.` : ""}
          {" "}알림은 계속 쌓이고 있습니다.
        </Callout>
      ) : null}

      <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap", mb: 1.5 }}>
        <FormControlLabel
          control={
            <Switch
              checked={!!dnd.enabled}
              disabled={saving}
              onChange={(e) => save({ dnd_enabled: e.target.checked, dnd_minutes: e.target.checked ? 60 : 0 })}
              slotProps={{ input: { "aria-label": "방해금지" } }}
            />
          }
          label="지금 조용히 하기"
        />
        {dnd.enabled ? (
          <Typography variant="body2" color="text.secondary">
            {dnd.until ? `${fmtRelative(dnd.until)} 자동 해제` : "직접 끌 때까지"}
          </Typography>
        ) : null}
      </Box>

      {dnd.enabled ? (
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mb: 2 }}>
          {DND_PRESETS.map((p) => (
            <Button key={p.label} size="sm" disabled={saving}
              onClick={() => save({ dnd_enabled: true, dnd_minutes: p.minutes })}>
              {p.label}
            </Button>
          ))}
        </Box>
      ) : null}

      <Box sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: "divider" }}>
        <FormControlLabel
          control={
            <Switch
              checked={!!dnd.quiet_hours_enabled}
              disabled={saving}
              onChange={(e) => save({ quiet_hours_enabled: e.target.checked })}
              slotProps={{ input: { "aria-label": "조용시간" } }}
            />
          }
          label="매일 같은 시간대에 조용히 하기"
        />
        <Box sx={{ display: "flex", gap: 1.5, alignItems: "center", flexWrap: "wrap", mt: 1.5 }}>
          <TextField
            type="time" size="small" label="시작" value={start}
            onChange={(e) => setStart(e.target.value)}
            InputLabelProps={{ shrink: true }}
            disabled={!dnd.quiet_hours_enabled || saving}
          />
          <TextField
            type="time" size="small" label="종료" value={end}
            onChange={(e) => setEnd(e.target.value)}
            InputLabelProps={{ shrink: true }}
            disabled={!dnd.quiet_hours_enabled || saving}
          />
          <Button
            size="sm"
            disabled={!dnd.quiet_hours_enabled || saving || (start === dnd.quiet_start && end === dnd.quiet_end)}
            onClick={() => save({ quiet_start: start, quiet_end: end })}
          >
            시간 저장
          </Button>
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          한국 시간 기준입니다. 자정을 넘겨도 됩니다(예: 22:00 → 08:00).
        </Typography>
      </Box>
    </Card>
  );
}

/* 내 기기 — 살아 있는 세션 목록 + 다른 기기 로그아웃. */
function SessionsCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const q = useQuery({ queryKey: ["my-sessions"], queryFn: () => api("/api/me/sessions"), retry: false });
  const items = (q.data && q.data.items) || [];
  const others = items.filter((s) => !s.current);

  const revokeOthers = useMutation({
    mutationFn: () => api("/api/me/sessions/revoke-others", { method: "POST", body: {} }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["my-sessions"] });
      toast(`${res.revoked_count}개 기기의 로그인을 해제했습니다.`, "success");
    },
    onError: (e) => toast(e.message, "error"),
  });
  const revokeOne = useMutation({
    mutationFn: (id) => api("/api/me/sessions/" + id, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["my-sessions"] });
      toast("해당 기기의 로그인을 해제했습니다.", "success");
    },
    onError: (e) => toast(e.message, "error"),
  });

  async function askRevokeOthers() {
    const ok = await confirm(
      `지금 보고 있는 이 창은 그대로 두고 나머지 ${others.length}개의 로그인을 끊습니다.
끊긴 기기는 즉시 다시 로그인해야 합니다.`,
      { title: "다른 기기 모두 로그아웃", confirmLabel: "모두 로그아웃", danger: true },
    );
    if (ok) revokeOthers.mutate();
  }

  return (
    <Card>
      <SectionTitle help="공용 PC에 로그인해 둔 채로 왔거나, 모르는 기기가 보이면 여기서 끊으세요. 지금 보고 있는 이 창은 유지됩니다.">
        내 기기(로그인 세션)
      </SectionTitle>
      {q.isLoading ? <Skeleton lines={3} /> : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState title="표시할 세션이 없습니다" />
      ) : (
      <>
        {/* 총계를 먼저 말한다 — 아래 목록은 높이가 묶여 있어 일부만 보인다. 숫자를 안 쓰면
            "몇 개인지"를 스크롤해서 세어야 하고, 잘린 마지막 줄이 오류처럼 보인다. */}
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          총 {items.length}개, 다른 기기 {others.length}개{items.length > 6 ? " (목록은 스크롤됩니다)" : ""}
        </Typography>
        {/* 목록 높이를 묶고 안에서 스크롤한다 — 오래 쓴 계정은 세션이 수십 개까지 쌓여
            카드 하나가 화면 스무 개 길이가 된다(QA 캡처에서 실제로 22개였다). 그러면 옆
            칸(계정 카드) 아래가 통째로 비고, 아래에 있는 '알림 설정'까지 스크롤이 멀어진다. */}
        <Box
          component="ul"
          sx={{
            listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5,
            maxHeight: { md: "26rem" }, overflowY: { md: "auto" }, pr: { md: 1 },
          }}
        >
          {items.map((s) => (
            <Box component="li" key={s.id} sx={{ display: "flex", gap: 2, alignItems: "flex-start", py: 1, borderBottom: 1, borderColor: "divider" }}>
              <DevicesOtherRoundedIcon fontSize="small" aria-hidden="true" color={s.current ? "primary" : "disabled"} sx={{ mt: 0.5 }} />
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
                  <Typography sx={{ fontWeight: 650 }}>
                    {s.current ? "지금 이 창" : "다른 기기"}
                  </Typography>
                  {s.current ? <Badge value="현재" kind="ok" /> : null}
                </Box>
                <Typography variant="body2" color="text.secondary" sx={{ wordBreak: "break-word" }}>
                  {s.client_ip || "IP 미상"}, 최근 활동 {fmtRelative(s.last_seen_at)}
                </Typography>
                {s.user_agent ? (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", wordBreak: "break-word" }}>
                    {s.user_agent}
                  </Typography>
                ) : null}
                {/* 버튼을 행의 **왼쪽 글 블록 안**에 둔다. 오른쪽 끝에 두면 우하단에 고정된
                    마스코트 버튼(94×94)이 그 자리에 겹쳐 눌리지 않는다 — 긴 목록이라 어느
                    행이든 그 높이에 올 수 있고, 실제로 QA 의 fab_overlap 검사가 잡았다
                    (놀이방 '보내기'가 같은 이유로 죽었던 적이 있다). */}
                {!s.current ? (
                  <Button size="sm" sx={{ mt: 1 }} disabled={revokeOne.isPending} onClick={() => revokeOne.mutate(s.id)}>
                    이 기기 로그아웃
                  </Button>
                ) : null}
              </Box>
            </Box>
          ))}
        </Box>
      </>
      )}
      <Box sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: "divider" }}>
        <Button
          variant="danger"
          disabled={others.length === 0 || revokeOthers.isPending}
          onClick={askRevokeOthers}
        >
          {revokeOthers.isPending ? "처리 중…" : `다른 기기 모두 로그아웃${others.length ? ` (${others.length})` : ""}`}
        </Button>
        {others.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            지금은 이 창에서만 로그인되어 있습니다.
          </Typography>
        ) : null}
      </Box>
    </Card>
  );
}

export function Profile() {
  const qc = useQueryClient();
  const toast = useToast();
  const profileQuery = useQuery({ queryKey: ["profile"], queryFn: () => api("/api/profile"), retry: false });
  const prefsQuery = useQuery({ queryKey: ["me-preferences"], queryFn: () => api("/api/me/preferences"), retry: false });

  const savePrefs = useMutation({
    mutationFn: (body) => api("/api/me/preferences", { method: "PATCH", body }),
    onSuccess: (data) => {
      qc.setQueryData(["me-preferences"], data);
      // 배지가 즉시 조용해지거나 다시 켜지도록 벨 폴링도 함께 무효화한다.
      qc.invalidateQueries({ queryKey: ["noti-unread"] });
      toast("설정을 저장했습니다.", "success");
    },
    onError: (e) => toast(e.message, "error"),
  });

  const resetTour = useMutation({
    mutationFn: () => api("/api/me/tour", { method: "POST", body: { action: "reset" } }),
    onSuccess: (data) => {
      qc.setQueryData(["me-preferences"], data);
      toast("둘러보기를 다시 볼 수 있습니다. 홈으로 가면 시작됩니다.", "success");
    },
    onError: (e) => toast(e.message, "error"),
  });

  const loading = profileQuery.isLoading || prefsQuery.isLoading;
  const error = profileQuery.error || prefsQuery.error;

  return (
    <div className="c-screen">
      <PageHeader area="내 정보" title="내 프로필" crumbRoot="" spot="mywork" />
      {loading ? (
        <Card><Skeleton lines={8} /></Card>
      ) : error ? (
        <ErrorState error={error} onRetry={() => { profileQuery.refetch(); prefsQuery.refetch(); }} />
      ) : (
        <Box sx={{ display: "grid", gap: 2.5 }}>
          <Box sx={TWO_COL}>
            <AccountCard
              profile={profileQuery.data}
              prefs={prefsQuery.data}
              onChanged={() => {
                prefsQuery.refetch();
                profileQuery.refetch();
                // 상단바 아바타는 /api/me 를 본다 — 같이 새로 받아야 사진이 바로 바뀐다.
                qc.invalidateQueries({ queryKey: ["me"] });
              }}
            />
            <SessionsCard />
          </Box>
          <Box sx={TWO_COL}>
            <NotificationCard prefs={prefsQuery.data} save={savePrefs.mutate} saving={savePrefs.isPending} />
            <DndCard prefs={prefsQuery.data} save={savePrefs.mutate} saving={savePrefs.isPending} />
          </Box>
          <Card>
            <SectionTitle help="처음 들어왔을 때 나오는 안내입니다. 언제든 다시 볼 수 있습니다.">
              둘러보기
            </SectionTitle>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {prefsQuery.data.tour.show
                ? "아직 보지 않았습니다. 홈으로 가면 자동으로 시작됩니다."
                : prefsQuery.data.tour.skipped ? "건너뛰었습니다." : "완료했습니다."}
            </Typography>
            <Button disabled={prefsQuery.data.tour.show || resetTour.isPending} onClick={() => resetTour.mutate()}>
              둘러보기 다시 보기
            </Button>
          </Card>
        </Box>
      )}
    </div>
  );
}

export default Profile;
