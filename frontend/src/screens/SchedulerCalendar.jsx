import React from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import ChevronLeftRoundedIcon from "@mui/icons-material/ChevronLeftRounded";
import ChevronRightRoundedIcon from "@mui/icons-material/ChevronRightRounded";
import { api } from "../lib/api.js";
import { toUTCDate } from "../lib/format.js";
import {
  PageHeader, Card, Callout, Badge, Button, Skeleton,
  EmptyState, ErrorState, Modal, DataTable,
} from "../ui/kit.jsx";

/* 스케줄러 캘린더 (PLAN Phase 6, 관리자 백로그).
 *
 * **왜 DataScreen 이 아닌가.** 다른 새 관리자 화면 여덟 개는 registry.js 설정으로 끝냈다.
 * 이것만 별도 컴포넌트인 이유는 "언제 도는가"라는 질문이 **표로 답이 안 되기** 때문이다 —
 * 표는 시간을 세로로 늘어놓지만, 사람이 알고 싶은 것은 "이번 주 화요일에 몰려 있나",
 * "주말에도 도나" 같은 **분포**다. 그건 격자에서만 보인다.
 *
 * **지난 실행과 앞으로의 예정을 한 격자에** 그린다. 서버가 `kind`로 구분해 준다:
 *   run     — 실제로 돈 것(성공/실패/건너뜀). 사실이다.
 *   planned — 아직 안 온 예정. cron 을 전개한 계산값이다.
 * 둘을 나눠 그리는 이유: "예정대로 돌았는가"가 이 화면의 유일한 질문인데, 같은 모양으로
 * 그리면 그 질문에 답할 수 없다.
 *
 * 시각은 전부 Asia/Seoul 로 그린다(저장소 불변 §9). 서버는 naive UTC 로 주므로
 * `toUTCDate` 로 해석한 뒤 KST 로 포맷한다 — 로컬 타임존으로 오해하면 9시간이 어긋난다.
 */

const KST = "Asia/Seoul";
const DAY_LABELS = ["일", "월", "화", "수", "목", "금", "토"];

const kstParts = new Intl.DateTimeFormat("en-CA", {
  timeZone: KST, year: "numeric", month: "2-digit", day: "2-digit",
});
const kstTime = new Intl.DateTimeFormat("ko-KR", {
  timeZone: KST, hour: "2-digit", minute: "2-digit", hour12: false,
});

/** UTC Date → KST 달력일 키("2026-08-03"). 격자 칸을 고르는 유일한 기준이다. */
function kstDayKey(date) {
  return kstParts.format(date);
}

function kstHHMM(date) {
  return kstTime.format(date);
}

/** KST 기준 그 달 1일 00:00 에 해당하는 UTC 시각.
 *
 * KST 는 DST 가 없어 고정 +09:00 이다 — 그래서 오프셋을 문자열로 붙여 Date 에 맡길 수 있고,
 * 브라우저 로컬 타임존이 무엇이든 같은 순간을 가리킨다. */
function kstMonthStart(year, month) {
  const mm = String(month + 1).padStart(2, "0");
  return new Date(`${year}-${mm}-01T00:00:00+09:00`);
}

/** 달력 격자에 그릴 42칸(6주). 항상 6주를 그려 달을 넘길 때 높이가 튀지 않게 한다. */
function buildGrid(year, month) {
  const first = kstMonthStart(year, month);
  // 그 달 1일의 KST 요일. Date#getUTCDay 는 UTC 요일이라 못 쓴다 — KST 자정의 순간을
  // 다시 KST 로 포맷해 요일을 얻는다.
  const weekdayFmt = new Intl.DateTimeFormat("en-US", { timeZone: KST, weekday: "short" });
  const shortNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const firstDow = shortNames.indexOf(weekdayFmt.format(first));
  const cells = [];
  for (let i = 0; i < 42; i += 1) {
    const d = new Date(first.getTime() + (i - firstDow) * 86400000);
    cells.push({ key: kstDayKey(d), date: d, inMonth: d.getTime() >= first.getTime() && d < kstMonthStart(year, month + 1) });
  }
  return cells;
}

const STATUS_KO = { queued: "대기", running: "실행 중", succeeded: "성공", failed: "실패", skipped: "건너뜀" };
const STATUS_KIND = { succeeded: "ok", failed: "danger", running: "info", queued: "info", skipped: "warn" };

/** 한 칸 안의 점 하나. 예정은 테두리만, 실행은 채운다 — 색만으로 구분하지 않는다
 *  (색각 이상에서도 구별돼야 한다). */
function EventDot({ event, onClick }) {
  const at = toUTCDate(event.occurs_at);
  const planned = event.kind === "planned";
  const failed = event.status === "failed";
  const label = `${at ? kstHHMM(at) : ""} ${event.schedule_name || "(이름 없음)"}`;
  return (
    <Box
      component="button"
      type="button"
      onClick={() => onClick(event)}
      title={`${label}${planned ? ", 예정" : `, ${STATUS_KO[event.status] || event.status || "실행"}`}`}
      sx={{
        display: "block", width: "100%", textAlign: "start",
        border: planned ? "1px dashed" : "1px solid",
        borderColor: failed ? "error.main" : planned ? "divider" : "primary.main",
        bgcolor: planned ? "transparent" : failed ? "error.light" : "primary.light",
        color: planned ? "text.secondary" : failed ? "error.contrastText" : "primary.contrastText",
        borderRadius: 1, px: 0.75, py: 0.25, mb: 0.25, cursor: "pointer",
        fontSize: "0.6875rem", lineHeight: 1.4,
        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        "&:hover": { filter: "brightness(0.95)" },
        "&:focus-visible": { outline: "2px solid", outlineColor: "primary.main", outlineOffset: 1 },
      }}
    >
      {planned ? "○ " : failed ? "● " : "● "}
      {label}
    </Box>
  );
}

export function SchedulerCalendar() {
  // 오늘의 KST 연·월에서 시작한다.
  const todayKey = kstDayKey(new Date());
  const [cursor, setCursor] = React.useState(() => ({
    year: Number(todayKey.slice(0, 4)),
    month: Number(todayKey.slice(5, 7)) - 1,
  }));
  const [scheduleId, setScheduleId] = React.useState("");
  const [selected, setSelected] = React.useState(null);

  const rangeStart = kstMonthStart(cursor.year, cursor.month);
  const rangeEnd = kstMonthStart(cursor.year, cursor.month + 1);
  // 격자는 앞뒤 달을 조금씩 물고 있으므로 조회 구간도 그만큼 넓힌다(최대 92일 이내).
  const queryStart = new Date(rangeStart.getTime() - 7 * 86400000);
  const queryEnd = new Date(rangeEnd.getTime() + 7 * 86400000);

  const url =
    "/api/admin/schedules/calendar?start=" + encodeURIComponent(queryStart.toISOString()) +
    "&end=" + encodeURIComponent(queryEnd.toISOString()) +
    (scheduleId ? "&schedule_id=" + encodeURIComponent(scheduleId) : "");

  const query = useQuery({
    queryKey: ["scheduler-calendar", cursor.year, cursor.month, scheduleId],
    queryFn: () => api(url),
    retry: false,
  });

  const cells = React.useMemo(() => buildGrid(cursor.year, cursor.month), [cursor]);
  const byDay = React.useMemo(() => {
    const map = {};
    for (const event of (query.data && query.data.items) || []) {
      const at = toUTCDate(event.occurs_at);
      if (!at) continue;
      const key = kstDayKey(at);
      (map[key] = map[key] || []).push(event);
    }
    return map;
  }, [query.data]);

  const schedules = (query.data && query.data.schedules) || [];
  const monthLabel = `${cursor.year}년 ${cursor.month + 1}월`;
  const move = (delta) => setCursor((c) => {
    const next = new Date(Date.UTC(c.year, c.month + delta, 1));
    return { year: next.getUTCFullYear(), month: next.getUTCMonth() };
  });

  const counts = React.useMemo(() => {
    const items = (query.data && query.data.items) || [];
    return {
      planned: items.filter((e) => e.kind === "planned").length,
      run: items.filter((e) => e.kind === "run").length,
      failed: items.filter((e) => e.status === "failed").length,
    };
  }, [query.data]);

  return (
    <div className="c-screen">
      <PageHeader
        area="자동화"
        title="실행 달력"
        actions={
          <Button variant="ghost" href="#/schedules">일정 목록으로</Button>
        }
      />
      <Callout>
        예약된 실행을 달력으로 봅니다. <strong>채워진 점</strong>은 실제로 돈 실행,{" "}
        <strong>점선 테두리</strong>는 아직 오지 않은 예정입니다. 시각은 모두 한국 시간입니다.
        예정은 Cron 식을 펼쳐 계산한 값이라, 일정을 껐다 켜면 다시 계산됩니다.
      </Callout>

      <Card sx={{ mt: 2, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 1.5 }}>
        <IconButton onClick={() => move(-1)} aria-label="이전 달"><ChevronLeftRoundedIcon /></IconButton>
        <Typography component="h2" sx={{ fontWeight: 800, fontSize: "1.125rem", minWidth: "8ch" }}>
          {monthLabel}
        </Typography>
        <IconButton onClick={() => move(1)} aria-label="다음 달"><ChevronRightRoundedIcon /></IconButton>
        <Button
          variant="ghost"
          onClick={() => setCursor({ year: Number(todayKey.slice(0, 4)), month: Number(todayKey.slice(5, 7)) - 1 })}
        >
          이번 달
        </Button>
        <Box sx={{ flex: 1 }} />
        {/* displayEmpty 가 없으면 값이 ""일 때 칸이 통째로 비어 보인다 — 컨트롤이 고장 난
            것처럼 읽히고, 무엇이 선택돼 있는지도 알 수 없다(DataScreen 의 필터 select 가
            "값의 주인: 전체"처럼 항상 현재 선택을 보여 주는 것과 같은 이유). */}
        <TextField
          select
          size="small"
          label="일정"
          value={scheduleId}
          onChange={(e) => setScheduleId(e.target.value)}
          slotProps={{ select: { displayEmpty: true } }}
          sx={{ minWidth: "16ch" }}
        >
          <MenuItem value="">일정: 전체</MenuItem>
          {schedules.map((s) => (
            <MenuItem key={s.id} value={s.id}>{s.name}{s.enabled ? "" : " (꺼짐)"}</MenuItem>
          ))}
        </TextField>
      </Card>

      {query.data && query.data.truncated ? (
        <Box sx={{ mt: 2 }}>
          <Callout tone="warn">
            일정이 너무 촘촘해 이 달의 예정을 전부 펼치지 못했습니다(일정 하나당 200개까지).
            위에서 일정을 하나만 골라 보면 전체를 볼 수 있습니다.
          </Callout>
        </Box>
      ) : null}

      {query.isLoading ? (
        <Card sx={{ mt: 2 }}><Skeleton lines={8} /></Card>
      ) : query.isError ? (
        <Box sx={{ mt: 2 }}><ErrorState error={query.error} onRetry={() => query.refetch()} /></Box>
      ) : schedules.length === 0 ? (
        <Box sx={{ mt: 2 }}>
          <EmptyState
            art="search"
            title="등록된 실행 일정이 없습니다"
            help="‘실행 일정(스케줄)’ 화면에서 일정을 만들고 활성화하면 이 달력에 표시됩니다."
            relatedLink={{ href: "#/schedules", label: "실행 일정으로 이동" }}
          />
        </Box>
      ) : (
        <>
          <Card sx={{ mt: 2, display: "flex", gap: 2, flexWrap: "wrap", alignItems: "center" }}>
            <Typography sx={{ fontSize: "0.875rem" }}>
              이 구간 실행 <strong>{counts.run}</strong>건, 예정 <strong>{counts.planned}</strong>건
            </Typography>
            {counts.failed ? <Badge value={`실패 ${counts.failed}건`} kind="danger" /> : null}
          </Card>

          <Card sx={{ mt: 2, p: { xs: 1, sm: 2 }, overflowX: "auto" }}>
            <Box
              role="grid"
              aria-label={`${monthLabel} 실행 달력`}
              sx={{ minWidth: "44rem", display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 0.5 }}
            >
              {DAY_LABELS.map((d, i) => (
                <Box
                  key={d}
                  role="columnheader"
                  sx={{
                    textAlign: "center", py: 0.75, fontWeight: 800, fontSize: "0.8125rem",
                    color: i === 0 ? "error.main" : i === 6 ? "primary.main" : "text.secondary",
                  }}
                >
                  {d}
                </Box>
              ))}
              {cells.map((cell) => {
                const events = byDay[cell.key] || [];
                const isToday = cell.key === todayKey;
                return (
                  <Box
                    key={cell.key}
                    role="gridcell"
                    sx={{
                      minHeight: { xs: "5.5rem", xl: "7rem", xxl: "8rem" },
                      p: 0.75, borderRadius: 1.5,
                      border: "1px solid",
                      borderColor: isToday ? "primary.main" : "divider",
                      bgcolor: cell.inMonth ? "background.paper" : "action.hover",
                      opacity: cell.inMonth ? 1 : 0.55,
                      overflow: "hidden",
                    }}
                  >
                    <Typography
                      sx={{
                        fontSize: "0.75rem", fontWeight: isToday ? 800 : 600, mb: 0.5,
                        color: isToday ? "primary.main" : "text.secondary",
                      }}
                    >
                      {Number(cell.key.slice(8, 10))}
                      {isToday ? ", 오늘" : ""}
                    </Typography>
                    {events.slice(0, 4).map((event, i) => (
                      <EventDot key={event.run_id || `${event.schedule_id}-${event.occurs_at}-${i}`} event={event} onClick={setSelected} />
                    ))}
                    {events.length > 4 ? (
                      <Tooltip title={`${events.length - 4}건 더 있습니다`}>
                        <Typography sx={{ fontSize: "0.6875rem", color: "text.secondary" }}>
                          +{events.length - 4}건
                        </Typography>
                      </Tooltip>
                    ) : null}
                  </Box>
                );
              })}
            </Box>
          </Card>
        </>
      )}

      <Modal
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected ? (selected.schedule_name || "실행") : ""}
        size="sm"
      >
        {selected ? (
          <DataTable
            columns={[{ key: "label", label: "항목" }, { key: "value", label: "값" }]}
            rowKey={(r) => r.label}
            rows={[
              { label: "구분", value: selected.kind === "planned" ? "예정(아직 실행 전)" : "실행 기록" },
              {
                label: "시각(KST)",
                value: (() => { const d = toUTCDate(selected.occurs_at); return d ? `${kstDayKey(d)} ${kstHHMM(d)}` : "-"; })(),
              },
              { label: "상태", value: selected.kind === "planned" ? "-" : (STATUS_KO[selected.status] || selected.status || "-") },
              { label: "오류", value: selected.error_message || "-" },
              { label: "일정 ID", value: selected.schedule_id },
            ]}
          />
        ) : null}
        <Box sx={{ mt: 2, display: "flex", gap: 1, flexWrap: "wrap" }}>
          <Button
            variant="primary"
            onClick={() => { const id = selected && selected.schedule_id; setSelected(null); window.location.hash = "#/schedules?id=" + encodeURIComponent(id || ""); }}
          >
            이 일정 열기
          </Button>
          <Button variant="ghost" onClick={() => setSelected(null)}>닫기</Button>
        </Box>
      </Modal>
    </div>
  );
}

export default SchedulerCalendar;
export { buildGrid, kstDayKey, STATUS_KIND };
