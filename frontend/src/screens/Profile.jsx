import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DevicesOtherRoundedIcon from "@mui/icons-material/DevicesOtherRounded";
import { api } from "../lib/api.js";
import { fmtDateTime, fmtRelative, shortUA } from "../lib/format.js";
import { useAuth } from "../app/auth.jsx";
import { UserAvatar } from "../ui/UserAvatar.jsx";
import { AvatarCropDialog } from "../ui/AvatarCropDialog.jsx";
import { DefaultAvatarPicker } from "../ui/DefaultAvatarPicker.jsx";
import { ROLE_KO } from "../app/navConfig.js";
import { invalidateNotifications } from "../app/notification-keys.js";
import { invalidatePersonFaces } from "./ticket-views.js";
import {
  Badge, Button, Callout, Card, DetailRow, EmptyState, ErrorState, PageHeader, SectionTitle, Skeleton, SubGroup,
  useConfirm, useToast,
} from "../ui/kit.jsx";
import { FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";
import { Note, SettingRow } from "../ui/adminKit.jsx";
import { pairTracks } from "../ui/density.js";
/* 화면 강조색은 예전에 자기 라우트(`/my-display`)를 갖고 있었다 — 설정 하나뿐인 화면이
 * 사이드바 항목도 없이 계정 메뉴에서만 열렸고, 그래서 그 화면에서는 사이드바 선택 표시가
 * 통째로 사라졌다. 개인 설정은 이미 이 화면이 전부 갖고 있으므로(알림·방해금지·둘러보기)
 * 여기로 합친다(S19). 옛 주소는 이 화면으로 넘긴다. */
import { AccentPicker } from "./settings/AccentPicker.jsx";

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
/* 🔴 **똑같이 나누지 않는다** (S22 · `equal_column_split`). 줄 바닥을 맞추는 것(`stretch`)과
 * 폭을 반씩 주는 것은 다른 결정인데 한 값이 둘 다 하고 있었다. 실측(1920): 두 트랙이
 * 794px 로 같은데 **요구 폭은 2.88배 차이**였다 — 「내 기기」의 설명문과 UA 문자열이 열 줄로
 * 접히는 동안 옆 칸은 92%가 비어 있었다. 1200 에서도 같은 모양이다(2.52배).
 *
 * 그래서 줄마다 **어느 쪽이 폭을 요구하는지**를 적는다. `weight` 는 그 선언이다 — 1.35:1 로
 * 기울이되 반으로 접히는 지점(`lg` 미만)에서는 예전처럼 한 열이다. 바닥 정렬은 그대로다. */
/* 격자의 정본은 `ui/density.js::pairTracks` 다 — 관리자 설정 4탭이 같은 격자를 쓴다(D-457). */
/** 계정(라벨·값 짝) | 내 기기(설명문·기기 문자열) — 오른쪽이 폭을 요구한다. */
const TWO_COL_WIDE_RIGHT = pairTracks("minmax(0, 0.85fr) minmax(0, 1.15fr)");
/** 알림 설정(유형 스물한 줄) | 방해금지·강조색 — 왼쪽이 폭을 요구한다. */
const TWO_COL_WIDE_LEFT = pairTracks("minmax(0, 1.15fr) minmax(0, 0.85fr)");

// 방해금지 빠른 시간. '무한'을 기본으로 두지 않는다 — 실수로 켜 두고 잊는 것이 이 기능의
// 가장 흔한 실패다.
const DND_PRESETS = [
  { minutes: 30, label: "30분" },
  { minutes: 60, label: "1시간" },
  { minutes: 180, label: "3시간" },
  { minutes: 0, label: "직접 끌 때까지" },
];

/* SectionTitle(ui/kit.jsx)로 옮겨졌다(DS-07) — 이 화면은 h2 태그 + mb:2를 그대로 쓰려고
 * component/sx로 넘긴다(다른 화면들의 기본값 h3/mb:1.5보다 한 단계 무게가 있다). */

/* 라벨/값 줄은 `kit.jsx::DetailRow` 다 — 관리자 상세와 같은 줄, 같은 리듬(D-457). */

/* 아바타 + 계정 요약. 업로드는 기존 네임스페이스 업로드 경로를 그대로 쓴다(서버가 매직바이트로
 * 형식을 판정한다) — 화면은 확장자를 믿지 않고 서버 판정 결과만 받는다. */
function AccountCard({ profile, prefs, onChanged, children }) {
  const auth = useAuth();
  const toast = useToast();
  const confirm = useConfirm();
  const fileRef = React.useRef(null);
  const [busy, setBusy] = React.useState(false);
  /* 고른 파일은 **바로 올리지 않는다.** 어디를 쓸지 사람이 정한 뒤에 올린다
     (`AvatarCropDialog`) — 예전에는 서버가 가운데를 잘랐고, 세로 사진에서는 그것이
     대개 어깨였다. */
  const [cropping, setCropping] = React.useState(null);
  const name = profile.display_name || (auth.data && auth.data.display_name) || "";
  /* 씨앗은 사용자 id. `/api/profile` 이 id 를 주기 전에는 여기가 비어 이름이 씨앗이 됐고,
     상단바(UUID)와 이 큰 원이 서로 다른 얼굴이었다. 세션의 id 를 폴백으로 둔다. */
  const userId = profile.id || (auth.data && auth.data.id) || "";
  const avatarUrl = (prefs && prefs.avatar && prefs.avatar.url) || profile.avatar_url || null;
  const defaultKey = (prefs && prefs.avatar && prefs.avatar.default_key) || null;
  const person = { user_id: userId, avatar_url: avatarUrl, avatar_default_key: defaultKey };

  async function upload(crop) {
    const file = cropping;
    if (!file) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      // 원본 짧은 변을 1.0 으로 본 비율. 서버가 같은 축으로 읽는다.
      form.append("crop_x", String(crop.crop_x));
      form.append("crop_y", String(crop.crop_y));
      form.append("crop_zoom", String(crop.crop_zoom));
      await api("/api/me/avatar", { method: "POST", body: form });
      toast("프로필 사진을 바꿨습니다.", "success");
      setCropping(null);
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
    if (!(await confirm("사진을 지우면 기본 아바타로 돌아갑니다.", { title: "프로필 사진 삭제", confirmLabel: "삭제" }))) return;
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

  async function pickDefault(key) {
    setBusy(true);
    try {
      await api("/api/me/preferences", {
        method: "PATCH", body: { avatar_default_key: key },
      });
      toast(
        avatarUrl
          ? "기본 아바타를 저장했습니다. 지금은 올린 사진이 보이므로, 기본 그림을 보려면 사진을 지우세요."
          : (key ? "기본 아바타를 저장했습니다." : "기본 아바타를 자동으로 되돌렸습니다."),
        "success",
      );
      onChanged();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <SectionTitle component="h2" help="사진은 이 조직 안에서만 보입니다. PNG, JPEG, GIF, WebP, 10MB까지.">
        계정
      </SectionTitle>
      <Box sx={{ display: "flex", gap: 3, alignItems: "center", flexWrap: "wrap", mb: 2 }}>
        {/* 사진이 없어도 빈 원이 아니다 — 이 사람의 기본 아바타가 선다. 제품 전체가
            같은 부품을 쓰므로 여기서 보는 그림이 채팅과 목록에서 보는 그것이다. */}
        <UserAvatar person={person} name={name} size="xl" userId={userId} />
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          {/* 파일 입력은 숨기고 버튼으로 연다 — 기본 파일 입력은 브라우저마다 생김새가 달라
              4K에서 혼자 작게 남는다. 라벨은 버튼이 갖는다(스크린리더도 버튼을 읽는다). */}
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            style={{ display: "none" }}
            onChange={(e) => setCropping((e.target.files && e.target.files[0]) || null)}
            aria-hidden="true"
            tabIndex={-1}
          />
          <Button variant="primary" disabled={busy} onClick={() => fileRef.current && fileRef.current.click()}>
            {busy ? "처리 중…" : "사진 바꾸기"}
          </Button>
          {avatarUrl ? <Button disabled={busy} onClick={remove}>사진 삭제</Button> : null}
        </Box>
      </Box>

      {/* 기본 아바타 고르기 — **사진과 다른 축이다.** 사진이 있으면 사진이 보이고, 사진을
          지운 뒤에 여기서 고른 그림이 살아난다. 아무것도 안 고르면 사용자 id 로 안정
          배정된 그림이 그대로 쓰인다. */}
      {avatarUrl ? (
        <Box sx={{ mb: 1.5 }}>
          <Callout tone="info">
            지금은 올린 사진이 보입니다. 아래에서 고른 기본 아바타는 사진을 지운 뒤에 쓰입니다.
          </Callout>
        </Box>
      ) : null}
      <DefaultAvatarPicker
        seed={userId}
        value={defaultKey}
        busy={busy}
        onPick={pickDefault}
      />

      <AvatarCropDialog
        open={!!cropping}
        file={cropping}
        busy={busy}
        onClose={() => { setCropping(null); if (fileRef.current) fileRef.current.value = ""; }}
        onSave={upload}
      />
      <DetailRow label="이름">{name || "-"}</DetailRow>
      <DetailRow label="이메일">{profile.email || "-"}</DetailRow>
      <DetailRow label="역할">{profile.role ? (ROLE_KO[profile.role] || profile.role) : "-"}</DetailRow>
      <DetailRow label="부서">{profile.department || "-"}</DetailRow>
      <DetailRow label="직책">{profile.title || "-"}</DetailRow>
      <DetailRow label="마지막 로그인">{profile.last_login_at ? fmtDateTime(profile.last_login_at) : "-"}</DetailRow>
      <Box sx={{ mt: 2, display: "flex", gap: 1, flexWrap: "wrap" }}>
        <Button component="a" href="/change-password">비밀번호 변경</Button>
      </Box>
      {children}
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
      <SectionTitle component="h2" help="끈 유형도 알림 목록에는 그대로 남습니다. 배지 숫자(빨간 점)에서만 빠집니다. 알림을 없애는 것이 아니라 조용히 하는 것입니다.">
        알림 설정
      </SectionTitle>
      {/* 한 줄은 `SettingRow` 다 — 관리자 설정의 줄과 같은 리듬(D-457). 예전에는 이 화면만
          `py: 0.75` 에 굵은 라벨로 따로 그렸다. */}
      <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0 }}>
        {prefs.notifications.catalog.map((row, i, all) => (
          <Box component="li" key={row.key}>
            <SettingRow
              label={row.label} description={row.help} last={i === all.length - 1}
              /* MUI 7 의 Switch 는 `inputProps` 를 **조용히 버린다** — 그렇게 쓰면 스위치에
                 접근 가능한 이름이 아예 없어 스크린리더가 이름 없는 컨트롤로 읽는다(테스트에서
                 실제로 잡았다). slotProps.input 이 <input> 에 닿는 유일한 통로다. */
              action={(
                <Switch
                  checked={!muted.has(row.key)}
                  disabled={saving}
                  onChange={() => toggle(row.key)}
                  slotProps={{ input: { "aria-label": `${row.label} 배지 알림` } }}
                />
              )}
            />
          </Box>
        ))}
      </Box>
      <Note sx={{ mt: 0 }}>
        계정 잠금처럼 보안에 관한 알림은 끌 수 없습니다. 침해를 알리는 유일한 신호이기 때문입니다.
      </Note>
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
      <SectionTitle component="h2" help="방해금지 중에도 알림은 평소대로 쌓입니다. 사이드바 배지만 조용해지고, 비활성화하면 그동안 쌓인 것이 한꺼번에 다시 보입니다.">
        방해금지
      </SectionTitle>

      {dnd.quiet_now ? (
        <Callout tone="info">
          지금 조용한 상태입니다({dnd.reason === "manual" ? "직접 켬" : "조용시간"}).
          {dnd.until ? ` ${fmtDateTime(dnd.until)}에 자동으로 풀립니다.` : ""}
          {" "}알림은 계속 쌓이고 있습니다.
        </Callout>
      ) : null}

      {/* 두 줄이 `SettingRow` 다 — 알림 설정·관리자 설정과 같은 리듬(D-457). 스위치의 접근 가능한
          이름(「방해금지」·「조용시간」)은 그대로다. */}
      <SettingRow
        label="지금 조용히 하기"
        description={dnd.enabled ? (dnd.until ? `${fmtRelative(dnd.until)} 자동 해제` : "직접 끌 때까지") : undefined}
        action={(
          <Switch
            checked={!!dnd.enabled}
            disabled={saving}
            onChange={(e) => save({ dnd_enabled: e.target.checked, dnd_minutes: e.target.checked ? 60 : 0 })}
            slotProps={{ input: { "aria-label": "방해금지" } }}
          />
        )}
      >
        {dnd.enabled ? (
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mt: 1 }}>
            {DND_PRESETS.map((p) => (
              <Button key={p.label} size="sm" disabled={saving}
                onClick={() => save({ dnd_enabled: true, dnd_minutes: p.minutes })}>
                {p.label}
              </Button>
            ))}
          </Box>
        ) : null}
      </SettingRow>
      <SettingRow
        label="매일 같은 시간대에 조용히 하기"
        description="한국 시간 기준입니다. 자정을 넘겨도 됩니다(예: 22:00 → 08:00)."
        last
        action={(
          <Switch
            checked={!!dnd.quiet_hours_enabled}
            disabled={saving}
            onChange={(e) => save({ quiet_hours_enabled: e.target.checked })}
            slotProps={{ input: { "aria-label": "조용시간" } }}
          />
        )}
      >
        <Box sx={{ display: "flex", gap: 1.5, alignItems: "center", flexWrap: "wrap", mt: 1 }}>
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
      </SettingRow>
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
      <SectionTitle component="h2" help="공용 PC에 로그인해 둔 채로 왔거나, 모르는 기기가 보이면 여기서 끊으세요. 지금 보고 있는 이 창은 유지됩니다.">
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
                  <Typography sx={{ fontWeight: FONT_WEIGHT.semibold }}>
                    {s.current ? "지금 이 창" : "다른 기기"}
                  </Typography>
                  {s.current ? <Badge value="현재" kind="ok" /> : null}
                </Box>
                <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
                  {s.client_ip || "IP 미상"}, 최근 활동 {fmtRelative(s.last_seen_at)}
                </Typography>
                {s.user_agent ? (
                  // Users.jsx(관리자의 다른 사용자 세션 목록)와 같은 이유로 원문 대신 60자로
                  // 자른 표기 + Tooltip으로 전체 문구를 보존한다 — 원문 그대로 두면 긴 UA
                  // 문자열이 이 카드의 폭을 밀어냈다.
                  <Tooltip title={s.user_agent}>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", ...KO_WORD_BREAK }}>
                      {shortUA(s.user_agent)}
                    </Typography>
                  </Tooltip>
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
      invalidateNotifications(qc);
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
      <PageHeader area="내 정보" title="내 프로필" crumbRoot="" />
      {loading ? (
        <Card><Skeleton lines={8} /></Card>
      ) : error ? (
        <ErrorState error={error} onRetry={() => { profileQuery.refetch(); prefsQuery.refetch(); }} />
      ) : (
        <Box sx={{ display: "grid", gap: 2.5 }}>
          <Box sx={TWO_COL_WIDE_RIGHT}>
            <AccountCard
              profile={profileQuery.data}
              prefs={prefsQuery.data}
              onChanged={() => {
                prefsQuery.refetch();
                profileQuery.refetch();
                // 상단바는 /api/me, 티켓·보드·채팅은 각자 캐시에 얼굴을 들고 있다.
                invalidatePersonFaces(qc);
              }}
            >
              {/* 🔴 **둘러보기가 개인 UI 설정보다 위다** (지시 18) — 그래서 계정 판 안, 강조색보다
                  앞에 선다. 예전에는 한 줄과 단추 하나가 전폭 판 하나를 차지했다(「3줄 미만의
                  내용은 판이 아니라 줄이다」). */}
              <SubGroup title="둘러보기" help="처음 들어왔을 때 나오는 안내입니다. 언제든 다시 볼 수 있습니다.">
                <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
                  <Typography variant="body2" color="text.secondary" sx={{ flex: "1 1 12rem", minWidth: 0, ...KO_WORD_BREAK }}>
                    {prefsQuery.data.tour.show
                      ? "아직 보지 않았습니다. 홈으로 가면 자동으로 시작됩니다."
                      : prefsQuery.data.tour.skipped ? "건너뛰었습니다." : "완료했습니다."}
                  </Typography>
                  <Button size="sm" disabled={prefsQuery.data.tour.show || resetTour.isPending} onClick={() => resetTour.mutate()}>
                    둘러보기 다시 보기
                  </Button>
                </Box>
              </SubGroup>
            </AccountCard>
            <SessionsCard />
          </Box>
          <Box sx={TWO_COL_WIDE_LEFT}>
            <NotificationCard prefs={prefsQuery.data} save={savePrefs.mutate} saving={savePrefs.isPending} />
            {/* 알림 설정 카드는 유형이 스물한 개라 세로로 길고, 그 옆 칸은 방해금지
                하나로 끝나 900px 가까이 비어 있었다(`equal_column_split` 실측). 같은
                「내 설정」인 강조색을 그 자리에 세운다 — 빈 자리를 메우려고 아무거나
                옮기는 것이 아니라, 원래 여기 있었어야 할 것이다. */}
            <Box sx={{ display: "grid", gap: 2.5, alignContent: "start", minWidth: 0 }}>
              <DndCard prefs={prefsQuery.data} save={savePrefs.mutate} saving={savePrefs.isPending} />
              <AccentPicker />
            </Box>
          </Box>
        </Box>
      )}
    </div>
  );
}

export default Profile;
