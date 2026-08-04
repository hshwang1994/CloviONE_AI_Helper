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

/* 번다운 두 선. 서버(app/sprints/burndown.py)가 준 points 를 그대로 옮기기만 한다.
 *
 * **이 그림이 주장하는 것은 마감일 배치뿐이다.** 완료 시각이 어디에도 없어서(원본은 생성·
 * 최종수정 시각만 준다) 날짜별 실제 이력은 만들 수 없고, 만드는 척하지도 않는다. 그래서
 * 선 이름이 '계획/미완료'이지 '이상/실제'가 아니다 — 이름이 데이터가 말할 수 있는 것보다
 * 많은 것을 주장하면 그림 전체가 거짓이 된다.
 */
export function burndownSeries(burndown) {
  const points = (burndown && Array.isArray(burndown.points)) ? burndown.points : [];
  if (points.length < 2) return null;
  const planned = points.map((p) => Number(p.planned) || 0);
  const open = points.map((p) => Number(p.open) || 0);
  // 전부 0이면(이 주에 잡힌 업무량이 없다) 바닥에 붙은 두 선만 남는다 — 그릴 게 없다고 말한다.
  if (!planned.some((v) => v > 0) && !open.some((v) => v > 0)) return null;
  return {
    labels: points.map((p) => shortDate(p.date)),
    series: [
      { label: "계획(마감일 기준)", points: planned, color: "primary" },
      { label: "아직 미완료", points: open, color: "warning" },
    ],
    summary: `이 주에 마감인 업무량 ${planned[0]}인일 중 ${open[0]}인일이 아직 완료되지 않았습니다.`,
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
        color: avg > 0 && load > avg * 1.5 ? "warn" : "primary",
        note: `완료 ${Number(d.est_done) || 0}인일, 담당 ${Number(d.assigned) || 0}건`,
      };
    })
    .sort((a, b) => b.value - a.value);

  const parts = [`${busy.length}명 평균 ${avg}인일`];
  if (peak > 0 && avg > 0) parts.push(`가장 많은 사람 ${peak}인일`);
  if (idle > 0) parts.push(`이번 주 배정이 없는 사람 ${idle}명`);
  return { items, max: peak, summary: parts.join(", ") };
}
