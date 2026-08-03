import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api.js";
import { PageHeader, Card, Badge, Button, Callout, Skeleton, ErrorState } from "../ui/kit.jsx";

// 이번 달을 'YYYY-MM'으로. 리포트는 마감일 기준이라 월만 쓴다.
function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

// 연도 선택지 — 올해부터 과거 count년까지 내림차순.
function yearOptions(count) {
  const y0 = new Date().getFullYear();
  const out = [];
  for (let i = 0; i < count; i += 1) out.push(y0 - i);
  return out;
}
// 월 선택지 — '01'~'12'.
const MONTH_VALUES = Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, "0"));

// 상태 구성 막대의 세그먼트 순서와 색 클래스.
const SEGS = [["seg-done", "done"], ["seg-prog", "prog"], ["seg-verify", "verify"], ["seg-plan", "plan"], ["seg-cancel", "cancel"]];

// 담당자 한 명의 상태 구성 스택 막대(SVG). 색은 CSS 클래스, 폭은 속성으로(인라인 스타일 금지).
function StatusBar({ d }) {
  const total = d.done + d.prog + d.verify + d.plan + d.cancel;
  if (!total) {
    return (
      <svg className="devrep-bar" viewBox="0 0 100 12" preserveAspectRatio="none" aria-hidden="true">
        <rect className="track" x="0" y="0" width="100" height="12" />
      </svg>
    );
  }
  let x = 0;
  const rects = [];
  for (const [cls, key] of SEGS) {
    const n = d[key];
    if (!n) continue;
    const w = (100 * n) / total;
    rects.push(<rect key={cls} className={cls} x={x} y="0" width={w} height="12" />);
    x += w;
  }
  const label = `완료 ${d.done}, 진행 ${d.prog}, 검증 ${d.verify}, 계획 ${d.plan}, 취소 ${d.cancel}`;
  return (
    <svg className="devrep-bar" viewBox="0 0 100 12" preserveAspectRatio="none" role="img" aria-label={label}>
      <rect className="track" x="0" y="0" width="100" height="12" />
      {rects}
    </svg>
  );
}

// 완료 예상 WD 가로 막대 그래프(SVG). 완료 예상 WD가 있는 사람만.
function WdBars({ devs }) {
  const rows = devs.filter((d) => d.est_done > 0);
  if (!rows.length) return null;
  const max = Math.max(...rows.map((d) => d.est_done));
  return (
    <div className="devrep-hbars">
      {rows.map((d) => {
        const pct = (100 * d.est_done) / max;
        return (
          <div className="devrep-hbar" key={d.name}>
            <span className="devrep-hbar-name">{d.name}</span>
            <svg viewBox="0 0 100 18" preserveAspectRatio="none" role="img" aria-label={`${d.name} 완료 업무량 ${d.est_done}인일`}>
              <rect className="track" x="0" y="3" width="100" height="12" />
              <rect className="fill" x="0" y="3" width={pct} height="12" />
            </svg>
            <span className="devrep-hbar-val">{d.est_done}</span>
          </div>
        );
      })}
    </div>
  );
}

function Kpi({ label, val, unit, note, accent, warn }) {
  return (
    <div className={"devrep-kpi" + (accent ? " is-accent" : "") + (warn ? " is-warn" : "")}>
      <p className="devrep-kpi-label">{label}</p>
      <p className="devrep-kpi-val">{val}{unit ? <small> {unit}</small> : null}</p>
      <p className="devrep-kpi-note">{note}</p>
    </div>
  );
}

function num(v) { return v == null ? "-" : v; }
function zed(v) { return v ? String(v) : <span className="devrep-z">0</span>; }

/* 개발자 월간 리포트 — 앱이 Notion "작업" DB를 라이브로 읽어 담당자별 업무를 보여준다.
 * 처음 제공한 HTML 리포트와 같은 시각 디자인(KPI 카드, 상태 스택 막대, WD 막대 그래프)을
 * 앱 토큰과 SVG로 재현한다(CSP상 인라인 스타일 금지). */
export function DevReport() {
  const [period, setPeriod] = useState(thisMonth());
  const query = useQuery({
    queryKey: ["dev-report", period],
    queryFn: () => api("/api/admin/reports/dev-monthly?period=" + encodeURIComponent(period)),
    retry: false,
  });
  const data = query.data;
  const ok = data && data.ok;
  const devs = ok ? data.developers : [];
  const withTickets = ok ? devs.filter((d) => d.has_tickets) : [];

  return (
    <div className="c-screen devrep">
      <PageHeader area="자동화" title="개발자 월간 리포트"
        actions={<Button variant="primary" onClick={() => query.refetch()}>새로고침</Button>} />

      <div className="c-page-callout">
        <Callout>
          <p>마감일이 선택한 달인 티켓을 Notion에서 실시간으로 읽어 담당자별로 집계합니다. 각자 얼마나 일했는지는 완료 건수와 예상 WD로 보고, 지금 안고 있는 부담과 위험은 진행 중 업무와 지연으로 함께 봅니다. 예상 WD와 난이도는 티켓 내용을 바탕으로 추정한 값이고, 실제 WD는 완료한 담당자가 입력합니다.</p>
        </Callout>
      </div>

      <Card className="c-toolbar-card devrep-noprint">
        <div className="c-toolbar-row">
          <label className="k-field-label" htmlFor="devrep-year">기간</label>
          <select id="devrep-year" className="c-filter" value={period.slice(0, 4)}
            onChange={(e) => setPeriod(e.target.value + "-" + period.slice(5, 7))} aria-label="연도 선택">
            {yearOptions(5).map((y) => <option key={y} value={String(y)}>{y}년</option>)}
          </select>
          <select id="devrep-month" className="c-filter" value={period.slice(5, 7)}
            onChange={(e) => setPeriod(period.slice(0, 4) + "-" + e.target.value)} aria-label="월 선택">
            {MONTH_VALUES.map((m) => <option key={m} value={m}>{parseInt(m, 10)}월</option>)}
          </select>
          <Button onClick={() => window.print()}>인쇄하거나 PDF로 저장</Button>
        </div>
      </Card>

      {query.isLoading ? (
        <Card><Skeleton lines={6} /></Card>
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : data && data.configured === false ? (
        <Card>
          <Callout tone="warn">
            <p>이 화면을 쓰려면 앱 서버가 Notion을 읽을 수 있도록 연동 토큰이 설정되어야 합니다. 토큰이 아직 없어 데이터를 불러오지 못했습니다. 관리자가 Notion 통합 토큰을 서버에 설정하면 새로고침만으로 실제 데이터가 나옵니다.</p>
          </Callout>
        </Card>
      ) : data && ok === false ? (
        <ErrorState error={{ message: data.error || "리포트를 불러오지 못했습니다." }} onRetry={() => query.refetch()} />
      ) : ok ? (
        <>
          <div className="devrep-kpis">
            <Kpi accent label="완료" val={data.team.done} unit="건" note={"취소를 뺀 기준 완료 " + data.team.est_done_total + "인일"} />
            <Kpi label="진행 중" val={data.team.in_progress} unit="건" note="진행과 이슈 상태" />
            <Kpi label="검증" val={data.team.verify} unit="건" note="검토, 확인 단계" />
            <Kpi label="계획" val={data.team.plan} unit="건" note="아직 착수 전" />
            <Kpi warn label="지연" val={data.team.overdue} unit="건" note="마감이 지난 미완료" />
            <Kpi label="담당자 없음" val={data.unassigned.total} unit="건" note="담당자가 지정되지 않음" />
          </div>

          <section className="devrep-sec">
            <h2 className="devrep-sec-title">개발자별 상세 ({data.period})</h2>
            <div className="devrep-tablewrap">
              <table className="devrep-table devrep-table--summary">
                <colgroup>
                  <col className="dc-name" /><col className="dc-bar" />
                  <col className="dc-n" /><col className="dc-n" /><col className="dc-n" /><col className="dc-n" />
                  <col className="dc-n" /><col className="dc-n" /><col className="dc-n" /><col className="dc-n" />
                </colgroup>
                <thead>
                  <tr>
                    <th className="l" title="티켓 담당자입니다. 이름은 앱의 Notion 사용자 연결로 해석했습니다.">개발자</th>
                    <th className="l" title="담당한 티켓의 상태 비율을 색 막대로 나타냅니다. 완료는 초록, 진행은 파랑, 검증은 주황, 계획은 회색, 취소는 어두운 색입니다.">상태 구성</th>
                    <th title="이번 달 마감분 가운데 완료 상태인 티켓 수입니다.">완료</th>
                    <th title="진행 상태인 티켓 수입니다.">진행</th>
                    <th title="검증 상태인 티켓 수입니다.">검증</th>
                    <th title="아직 시작하지 않은 계획 상태 티켓 수입니다.">계획</th>
                    <th title="취소된 티켓 수입니다.">취소</th>
                    <th title="이 사람에게 배정된 이번 달 마감 티켓 수입니다. 티켓 하나에 담당자가 둘이면 양쪽에 각각 셉니다.">담당</th>
                    <th title="담당한 일 가운데 완료한 비율입니다. 취소는 제외하며, 완료를 담당에서 취소를 뺀 수로 나눕니다.">완료율</th>
                    <th title="마감일이 지났는데 아직 완료되지 않은 티켓 수입니다.">지연</th>
                  </tr>
                </thead>
                <tbody>
                  {devs.map((d) => (
                    <tr key={d.name} className={d.has_tickets ? "" : "is-none"}>
                      <td className="l">{d.name}</td>
                      <td className="bar"><StatusBar d={d} /></td>
                      <td className="devrep-done">{d.done}</td>
                      <td>{zed(d.prog)}</td>
                      <td>{zed(d.verify)}</td>
                      <td>{zed(d.plan)}</td>
                      <td>{zed(d.cancel)}</td>
                      <td>{zed(d.assigned)}</td>
                      <td>{d.completion_rate == null ? <span className="devrep-z">-</span> : d.completion_rate + "%"}</td>
                      <td>{d.overdue > 0 ? <span className="devrep-chip is-od">{d.overdue}</span> : <span className="devrep-z">0</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="devrep-legend">
              <span><i className="done" />완료</span>
              <span><i className="prog" />진행</span>
              <span><i className="verify" />검증</span>
              <span><i className="plan" />계획</span>
              <span><i className="cancel" />취소</span>
            </div>
          </section>

          <section className="devrep-sec">
            <h2 className="devrep-sec-title">업무량 분석 (완료 업무량 기준)</h2>
            <WdBars devs={devs} />
            <div className="devrep-tablewrap">
              <table className="devrep-table">
                <thead>
                  <tr>
                    <th className="l" title="티켓 담당자입니다.">개발자</th>
                    <th title="완료한 티켓 수입니다.">완료</th>
                    <th title="진행과 검증을 합한 티켓 수입니다.">진행 중</th>
                    <th title="이번 달 완료한 티켓들의 예상 공수 합(인일). 예상 기준으로 이 사람이 이번 달에 끝낸 업무량입니다.">완료 업무량</th>
                    <th title="맡은 티켓 전체(취소 제외, 아직 안 끝낸 것 포함)의 예상 공수 합(인일). '완료 업무량'보다 크거나 같고, 둘의 차이가 남은 업무량입니다.">맡은 업무량</th>
                    <th title="완료한 티켓에 실제로 든 공수입니다. 담당자가 입력하는 값이며, 아직 입력 전이라 지금은 추정치로 채워져 있습니다.">실제 WD</th>
                    <th title="이 사람이 완료한 티켓 1건당 평균 실제 공수입니다. 실제 WD를 완료 건수로 나눈 값이라, 티켓 크기가 다른 사람끼리 부담을 비교할 때 씁니다.">평균 실제WD/건</th>
                    <th title="완료 티켓의 실제 공수를 예상 공수로 나눈 비율입니다. 100%면 예상과 같고, 100%보다 크면 예상보다 오래 걸렸다는 뜻입니다(견적 정확도).">예상 정확도</th>
                    <th title="맡은 티켓들의 난이도 평균입니다. 1에서 6까지이고 취소는 제외하며, 추정치입니다.">난이도 평균</th>
                  </tr>
                </thead>
                <tbody>
                  {devs.map((d) => (
                    <tr key={d.name} className={d.has_tickets ? "" : "is-none"}>
                      <td className="l">{d.name}</td>
                      <td>{zed(d.done)}</td>
                      <td>{zed(d.prog + d.verify)}</td>
                      <td className="devrep-done">{d.est_done}</td>
                      <td>{d.est_all}</td>
                      <td>{d.act_done ? d.act_done : <span className="devrep-z">-</span>}</td>
                      <td>{d.done && d.act_done ? (d.act_done / d.done).toFixed(1) : <span className="devrep-z">-</span>}</td>
                      <td>{d.est_done && d.act_done ? Math.round((100 * d.act_done) / d.est_done) + "%" : <span className="devrep-z">-</span>}</td>
                      <td>{d.difficulty_avg == null ? <span className="devrep-z">-</span> : d.difficulty_avg}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <div className="c-page-callout">
            <Callout tone="info">
              <p>완료 건수와 완료 예상 WD는 그 사람이 이번 달에 실제로 마무리한 일의 양을 나타냅니다. 진행과 검증 건수가 많으면 지금 손에 쥔 일이 많다는 뜻이고, 지연 건수는 마감이 지났는데 아직 끝나지 않은 티켓입니다. 완료율은 담당한 일 가운데 끝낸 비율이며 취소는 제외합니다. 담당 건수가 적으면 완료율이 쉽게 높아지므로 담당 건수와 함께 보아야 공정합니다.</p>
            </Callout>
          </div>

          <section className="devrep-sec">
            <h2 className="devrep-sec-title">담당자별 상세 티켓</h2>
            {withTickets.length === 0 ? (
              <p className="k-field-help">이 달에 담당한 티켓이 있는 사람이 없습니다.</p>
            ) : (
              <div className="devrep-tablewrap">
                <table className="devrep-table">
                  <thead>
                    <tr>
                      <th title="티켓 번호입니다(Notion 자동 번호).">번호</th>
                      <th className="l" title="티켓 제목입니다. 누르면 Notion 원본으로 이동합니다.">제목</th>
                      <th title="티켓의 진행 상태입니다.">상태</th>
                      <th title="티켓 마감일입니다.">마감일</th>
                      <th title="티켓 우선순위입니다(높음, 중간, 낮음).">우선순위</th>
                      <th title="티켓 난이도입니다(1에서 6까지, 추정치).">난이도</th>
                      <th title="이 티켓의 예상 공수입니다(인일, 추정치).">예상 WD</th>
                      <th title="이 티켓에 실제로 든 공수입니다. 담당자 입력값이며 현재는 추정치입니다.">실제 WD</th>
                      <th title="마감일이 지났는데 완료되지 않은 티켓을 표시합니다.">지연</th>
                    </tr>
                  </thead>
                  <tbody>
                    {withTickets.flatMap((d) => [
                      <tr key={d.name + "::group"} className="devrep-grouprow">
                        <td className="l" colSpan={9}>
                          {d.name}
                          <span className="k-field-help">완료 {d.done}건, 진행 중 {d.prog + d.verify}건, 완료 예상 WD {d.est_done}인일</span>
                        </td>
                      </tr>,
                      ...d.tickets.map((t) => (
                        <tr key={d.name + ":" + (t.tid || t.title) + ":" + t.status}>
                          <td className="n">{t.tid ? "GIT-" + t.tid : "-"}</td>
                          <td className="title">{t.url ? <a className="c-linkbtn" href={t.url} target="_blank" rel="noreferrer noopener">{t.title}</a> : t.title}</td>
                          <td><Badge value={t.status || "-"} /></td>
                          <td className="n">{t.due || "-"}</td>
                          <td className="n">{t.priority || "-"}</td>
                          <td className="n">{num(t.difficulty)}</td>
                          <td className="n">{num(t.est_wd)}</td>
                          <td className="n">{t.act_wd == null ? <span className="devrep-z">-</span> : t.act_wd}</td>
                          <td>{t.overdue ? <span className="devrep-chip is-od">지연</span> : ""}</td>
                        </tr>
                      )),
                    ])}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
