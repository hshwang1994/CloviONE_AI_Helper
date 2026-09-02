/* 스프린트 회의 화면의 두 그림(번다운 · WD 밸런스)이 쓰는 순수 변환 — JSX가 한 줄도 없다.
 *
 * 화면 안에 인라인으로 두면 "서버가 준 숫자를 어떻게 해석했는가"를 렌더 하네스를 통해서만
 * 만질 수 있다. 이 파일의 계약은 **숫자를 지어내지 않는 것**이다: 없는 값은 없는 채로 두고,
 * 그릴 수 없으면 null 을 돌려준다(빈 차트를 그리면 '0이다'와 '모른다'가 구분되지 않는다).
 */

// 축 눈금용 짧은 날짜(8/3). 전체 날짜를 양 끝에 쓰면 좁은 폭에서 겹친다.
export function shortDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
  return m ? `${Number(m[2])}/${Number(m[3])}` : String(iso || "");
}

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

/** ISO 날짜의 요일 한글. 못 읽으면 빈 문자열. */
export function weekdayKo(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
  if (!m) return "";
  const dt = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  if (Number.isNaN(dt.getTime())) return "";
  return WEEKDAYS[dt.getDay()] || "";
}

/** 축·배너용 짧은 날짜에 요일을 붙인다. `8/24 월`. */
export function datedLabel(iso) {
  const day = weekdayKo(iso);
  const short = shortDate(iso);
  return day ? `${short} ${day}` : short;
}

/** 목록에서 **오늘에 걸린 열린 회차**를 고른다. `active` 가 있으면 그걸 우선하고,
 * 없으면 `state === "active"` 로 물러난다. 열린 회차가 없으면 **고르지 않는다**(null).
 *
 * qa-contract-change: `|| list[0]` 폴백을 걷었다 — 목록은 `starts_on` 내림차순이라
 * 그 폴백은 「가장 미래의(대개 아직 안 연) 회차」였고, 보드·회의가 진입하자마자 그
 * 회차를 자동으로 열어 첫 화면이 빈 판 + 「아직 열지 않은 회차입니다」가 됐다.
 * 열린 회차가 없다는 사실은 자동 선택이 아니라 화면이 말한다. */
export function pickOpenSprint(rows) {
  const list = Array.isArray(rows) ? rows : [];
  return list.find((s) => s && s.active)
    || list.find((s) => s && s.state === "active")
    || null;
}

/** 건강 점수 밴드. 식은 서버(`meeting.py::_health`)가 이미 깎아 둔 값이다. */
export function healthBand(score) {
  if (typeof score !== "number" || !Number.isFinite(score)) return null;
  if (score >= 75) return { label: "양호", kind: "ok" };
  if (score >= 50) return { label: "주의", kind: "warn" };
  return { label: "위험", kind: "danger" };
}

/** 지연·차단이 깎은 것을 한 문장으로. 숫자를 다시 계산하지 않는다. */
export function healthCuts(summary) {
  if (!summary) return "";
  const parts = [];
  if (summary.overdue) parts.push(`지연 ${summary.overdue}건`);
  if (summary.blocked) parts.push(`차단 ${summary.blocked}건`);
  if (!parts.length) return "지연과 차단이 없어 깎인 점수가 없습니다.";
  return `${parts.join(", ")}이 깎습니다.`;
}

function medianOf(nums) {
  const s = [...nums].sort((a, b) => a - b);
  if (!s.length) return 0;
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

/** 남은 WD 를 팀 중앙값과 비교한 부하 띠. 1.5배면 높음, 절하면 낮음. */
export function loadBand(value, median) {
  if (!(median > 0)) return { label: "보통", kind: "neutral" };
  if (value >= median * 1.5) return { label: "높음", kind: "danger" };
  if (value <= median * 0.5) return { label: "낮음", kind: "ok" };
  return { label: "보통", kind: "warn" };
}

/* 번다운 세 선. 서버(`app/work/meeting.py::_burndown`)가 준 points 를 그대로 옮긴다.
 *
 * **이 그림은 이제 실제 소진을 그린다.** 예전 그림은 「그날 이후로 마감이 남아 있는
 * 업무량」의 분포였고, 그 이유는 완료 시각이 어디에도 없다는 것이었다. 그 전제가 더 이상
 * 사실이 아니다 — `tickets.completed_at` 이 상태를 쓰는 자리 한 곳에서 찍힌다.
 *
 *   이상    첫날의 범위에서 마지막 날 0 까지 곧게 내려가는 계획선
 *   남은 일 그날 끝에 아직 안 끝난 공수. **오늘까지만** 그린다
 *   범위    그날 이 회차에 담겨 있던 총량. 올라가면 일이 불어난 것이다
 *
 * 「오늘 이후는 안 그린다」가 이 그림의 정직성이다 — 내일 얼마가 남을지는 아무도 모른다.
 * `null` 점은 `LineSeries` 가 빈 자리로 둔다.
 */
export function burndownSeries(burndown) {
  const points = (burndown && Array.isArray(burndown.points)) ? burndown.points : [];
  if (points.length < 2) return null;
  const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  const ideal = points.map((p) => num(p.ideal) ?? 0);
  const remaining = points.map((p) => num(p.remaining));
  const scope = points.map((p) => num(p.scope) ?? 0);
  // 전부 0이면(이 회차에 잡힌 업무량이 없다) 바닥에 붙은 선만 남는다 — 그릴 게 없다고 말한다.
  if (!scope.some((v) => v > 0) && !ideal.some((v) => v > 0)) return null;

  const drawn = remaining.filter((v) => v != null);
  const now = drawn.length ? drawn[drawn.length - 1] : null;
  const at = drawn.length - 1;
  const plan = at >= 0 ? ideal[at] : null;
  const scopeGrew = scope[scope.length - 1] > scope[0];

  const parts = [];
  if (now != null && plan != null) {
    const gap = Math.round((now - plan) * 10) / 10;
    parts.push(
      gap > 0
        ? `계획보다 ${gap}인일 남아 있습니다.`
        : gap < 0
          ? `계획보다 ${Math.abs(gap)}인일 앞서 있습니다.`
          : "계획과 같은 속도입니다.",
    );
  }
  if (scopeGrew) {
    parts.push(`회차 중에 범위가 ${Math.round((scope[scope.length - 1] - scope[0]) * 10) / 10}인일 늘었습니다.`);
  }

  /* 색을 지정하지 않는다 — `LineSeries` 가 Brand 고정 시리즈 슬롯(색 + 선 스타일)을 준다.
     예전에는 계획선이 `primary`(사용자 Accent), 잔여선이 `warning` 이었다. 둘 다 틀렸다:
     Accent 는 사용자가 바꾸면 제품 정체성이 따라 바뀌고, `warning` 은 **상태색**이라
     바로 옆 담당자 막대에서 «과부하»를 뜻하는 같은 갈색이 여기서는 «아직 미완료»를 뜻했다.
     한 화면 안에서 같은 색이 두 가지를 뜻하면 색은 아무것도 뜻하지 않는다. */
  const series = [
    { label: "이상", points: ideal },
    { label: "남은 일", points: remaining },
  ];
  // 범위가 안 변했으면 이상선과 겹치는 선을 하나 더 그리지 않는다 — 장식이다.
  if (scopeGrew || scope[scope.length - 1] < scope[0]) {
    series.push({ label: "범위", points: scope });
  }
  return {
    labels: points.map((p) => shortDate(p.date)),
    series,
    summary: parts.join(" "),
  };
}

/* 범위 변경 추이 — 일자별 **누적** 들어옴·빠짐.
 *
 * 서버가 이미 읽은 활동 기록(`ticket_activities`, `kind='sprint'`)을 날짜로 접은 값이다.
 * 없는 자료를 만들지 않는다: 기록 자체가 없으면 서버가 `tracked:false` 로 말하고 이 함수는
 * 불리지도 않는다. 둘 다 0 이면 그릴 것이 없다 — 바닥에 붙은 선 두 개는 그림이 아니다.
 */
export function scopeTrendSeries(scope) {
  const points = (scope && Array.isArray(scope.trend)) ? scope.trend : [];
  if (points.length < 2) return null;
  const added = points.map((p) => Number(p.added) || 0);
  const removed = points.map((p) => Number(p.removed) || 0);
  if (!added.some((v) => v > 0) && !removed.some((v) => v > 0)) return null;
  return {
    labels: points.map((p) => shortDate(p.date)),
    series: [
      { label: "들어옴", points: added },
      { label: "빠짐", points: removed },
    ],
    summary: `회차가 시작한 뒤 ${added[added.length - 1]}건이 들어오고 ${removed[removed.length - 1]}건이 빠졌습니다.`,
  };
}

/* 담당자별 업무량(WD) 균형. 서버가 이미 developers[] 에 실어 준 값을 쓴다 —
 * est_all(취소 제외 계획 업무량)과 est_done(완료분). 같은 숫자를 두 번째 이름으로 다시
 * 내보내지 않는 이유가 이것이다(한쪽만 고쳐지는 날이 온다).
 *
 * 이번 주 배정이 없는 사람은 막대에서 빼고 **숫자로만 말한다**. 활성 사용자 전원이 0짜리
 * 막대로 늘어서면 실제 편중이 그 사이에 묻힌다 — 그러라고 그리는 그림이 아니다.
 */
export function wdBalanceItems(developers) {
  const rows = Array.isArray(developers) ? developers : [];
  const busy = rows.filter((d) => d && (Number(d.est_all) > 0 || Number(d.assigned) > 0));
  if (!busy.length) return null;
  const loads = busy.map((d) => Number(d.est_all) || 0);
  const total = loads.reduce((a, b) => a + b, 0);
  const avg = Math.round((total / busy.length) * 10) / 10;
  const peak = Math.max(...loads);
  const idle = rows.length - busy.length;

  const items = busy
    .map((d) => {
      const load = Number(d.est_all) || 0;
      return {
        label: d.name,
        value: load,
        // 평균의 1.5배를 넘는 사람만 색으로 짚는다. 전부 칠하면 아무 데도 눈이 안 간다.
        // 나머지는 색을 안 준다 — 부품이 Brand 시리즈 슬롯 0 을 준다(사용자 Accent 아님).
        color: avg > 0 && load > avg * 1.5 ? "warn" : undefined,
        note: `완료 ${Number(d.est_done) || 0}인일, 담당 ${Number(d.assigned) || 0}건`,
      };
    })
    .sort((a, b) => b.value - a.value);

  const parts = [`${busy.length}명 평균 ${avg}인일`];
  if (peak > 0 && avg > 0) parts.push(`가장 많은 사람 ${peak}인일`);
  if (idle > 0) parts.push(`이번 주 배정이 없는 사람 ${idle}명`);
  return { items, max: peak, summary: parts.join(", ") };
}

/* 담당자별 **남은** 업무량. 회차 회의가 실제로 묻는 것이 이 값이다 (지시 4 · 질문 3).
 *
 * `wdBalanceItems` 와 다른 그림이다. 그쪽은 「이번 주에 누가 얼마를 맡았나」(계획 업무량)를
 * 그리고, 이것은 「지금 누가 얼마를 지고 있나」(남은 업무량)를 그린다. 회의에서 쓰는 것은
 * 뒤엣것이다 — 회차 중반에 「맡은 양」은 다 비슷한데 「남은 양」은 세 배씩 벌어진다.
 *
 * 예상 WD 를 안 적은 티켓은 **숫자에 안 들어간다.** 0 으로 세면 「일이 없는 사람」과
 * 「예상을 안 적은 사람」이 같아 보이므로, 그 사실을 줄의 설명으로 따로 말한다.
 */
export function workloadItems(workload) {
  const rows = (Array.isArray(workload) ? workload : []).filter(
    (r) => r && (Number(r.remaining_wd) > 0 || Number(r.open) > 0)
  );
  if (!rows.length) return null;
  const loads = rows.map((r) => Number(r.remaining_wd) || 0);
  const total = loads.reduce((a, b) => a + b, 0);
  const avg = Math.round((total / rows.length) * 10) / 10;
  const peak = Math.max(...loads);
  const median = medianOf(loads);
  const items = rows.map((r) => {
    const load = Number(r.remaining_wd) || 0;
    const missing = Number(r.unestimated) || 0;
    return {
      label: r.display_name || "알 수 없음",
      value: load,
      // 평균의 1.5배를 넘는 사람만 색으로 짚는다. 전부 칠하면 아무 데도 눈이 안 간다.
      color: avg > 0 && load > avg * 1.5 ? "warn" : undefined,
      badge: (() => {
        const band = loadBand(load, median);
        return band.label === "보통" ? undefined : band;
      })(),
      note: missing
        ? `남은 ${Number(r.open) || 0}건, 예상을 안 적은 것 ${missing}건`
        : `남은 ${Number(r.open) || 0}건`,
    };
  });
  const parts = [`${rows.length}명 평균 ${avg}인일`];
  if (peak > 0) parts.push(`가장 많은 사람 ${peak}인일`);
  return { items, max: peak, summary: parts.join(", ") };
}
