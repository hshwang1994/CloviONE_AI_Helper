import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api.js";
import { CONSOLE_WRITE_ROLES } from "../lib/roles.js";
import { useAuth } from "../app/auth.jsx";
import { Callout, Card, ErrorState, Skeleton } from "../ui/kit.jsx";
import { TabShell } from "../ui/TabShell.jsx";
import { AdminScopeList, INTEGRITY_KEY, IntegrityTab } from "./integrity/IntegrityList.jsx";

/* 조직 정합성 진단 — **닫아 버린 것을 사람에게 보여 주는 화면** (0060 §41, 계획 3.2, D-508).
 *
 * 이 제품의 접근 모델은 "소속을 모르면 닫는다" 다. 그 규칙만 있으면 안전하기는 한데
 * 아무도 원인을 못 찾는다 — 증상이 "권한이 없습니다" 가 아니라 **"목록이 비어 있음"** 이기
 * 때문이다. 그래서 닫는 규칙과 이 화면은 같은 배포에 있어야 한다.
 *
 * ## 탭은 행을 가진 표로 나눈다
 *
 * 예전에는 검사 아홉 개를 한 페이지에 세로로 쌓고 검사마다 50건 표본을 그렸다. 51번째 행부터는 볼 길이
 * 없었고, 검색도 정렬도 없었고, 읽는 폭 상한(`READ_COLUMN`) 때문에 넓은 화면의 오른쪽 3분의 1이 비었다.
 * 이제 탭 하나가 표 하나다(사람 · 티켓 · 프로젝트와 문서 공간 · 회차 · 관리자 범위). 탭 옆 칩이 그 탭의
 * 건수이고, 탭 안에서 검사를 고르면 그 목록이 전량 페이지로 온다(`integrity/IntegrityList.jsx`).
 *
 * 화면은 추측해서 자동으로 고치지 않는다. 사람이 목록에서 고르고, 작업은 서버가 원래 수정 함수로 한다.
 */

export function Integrity() {
  const auth = useAuth();
  const role = auth.data ? auth.data.role : null;
  /* 고치기는 **전역 관리자**만 할 수 있다 — 서버가 그렇게 막는다(`app/integrity/router.py` CONSOLE_WRITE +
     `_require_global`). 이 화면 자체는 운영자 · 감사자도 여는데(진단은 읽기다), 그 역할에게 작업 줄을
     그리면 누르는 순간 403 이다. */
  const canFix = role != null && CONSOLE_WRITE_ROLES.includes(role)
    && (!auth.data || !auth.data.admin_scope || auth.data.admin_scope === "global");
  const q = useQuery({ queryKey: INTEGRITY_KEY, queryFn: () => api("/api/admin/integrity") });
  /* 주소에 탭이 없을 때 켜질 탭 — **처음 받은 요약**에서 건수가 있는 첫 탭이다. 한 번 정하면 바꾸지 않는다:
     고친 뒤 요약이 다시 오면서 기본 탭이 바뀌면, 보던 탭이 저절로 넘어간다. */
  const landing = React.useRef(null);

  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <Card><Skeleton lines={6} /></Card>;

  const data = q.data;
  const findings = data.findings || [];
  const serverTabs = data.tabs || [];
  if (landing.current == null) {
    const first = serverTabs.find((t) => t.count > 0);
    landing.current = first ? first.key : (serverTabs[0] ? serverTabs[0].key : "admins");
  }
  const closedSprints = (data.notes && data.notes.closed_sprints_without_team) || 0;

  const tabs = serverTabs.map((t) => ({
    key: t.key,
    label: t.label,
    count: t.count,
    render: () => (
      <>
        {t.key === "sprints" && closedSprints > 0 ? (
          <Callout tone="info" variant="inline" sx={{ mb: 2 }}>
            팀이 정해지지 않은 닫힌 회차 {closedSprints}건은 기록이라 세지 않습니다.
          </Callout>
        ) : null}
        <IntegrityTab findings={findings.filter((f) => f.tab === t.key)} canFix={canFix} />
      </>
    ),
  })).concat([{
    key: "admins",
    label: "관리자 범위",
    help: "조직이나 부서 관리자는 admin과 범위의 조합입니다.",
    render: () => <AdminScopeList summary={data.admins} />,
  }]);

  return (
    <TabShell
      area="운영" title="조직 정합성" ariaLabel="조직 정합성 탭" idPrefix="integrity"
      help="소속을 판정할 수 없어 화면에서 닫혀 있는 데이터를 모았습니다. 여기서 지정하면 바로 열립니다."
      tabs={tabs}
      defaultTab={landing.current}
    >
      {data.total_issues === 0 ? (
        <Callout tone="ok" sx={{ mb: 2.5 }}>정리할 것이 없습니다. 모든 자원의 소속을 판정할 수 있습니다.</Callout>
      ) : (
        <Callout tone="warn" sx={{ mb: 2.5 }}>
          정리할 항목이 모두 {data.total_issues}건 있습니다. 탭에서 항목을 골라 한 번에 고칠 수 있습니다.
        </Callout>
      )}
    </TabShell>
  );
}

export default Integrity;
