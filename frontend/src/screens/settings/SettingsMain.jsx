import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { useAuth } from "../../app/auth.jsx";
import { PageHeader, Card, Badge, Button, Callout, DataTable, Skeleton, EmptyState, ErrorState, useToast } from "../../ui/kit.jsx";
import {
  SETTING_LABELS, settingLabel, WRITE_ROLES, MAINTENANCE_KEYS, DEDICATED_SCREEN_KEYS,
  CONSOLE_SCREEN_ROLES, MAINTENANCE_READ_ROLES, summarizeSetting, displayValue,
} from "./settingsRegistry.js";
import { AccentPicker } from "./AccentPicker.jsx";
import { SettingEditor } from "./SettingEditor.jsx";

/* 설정 — 시스템 동작 값을 관리한다. GET /api/admin/settings는 {settings:{key:{value,type,
 * description,restart_required,is_default}}} 형태. 편집은 모달에서 타입별 입력 → PUT /{key}. object 타입
 * (ui_branding·password_policy·session_policy·allowed_email_domains)은 JSON 텍스트로 편집한다.
 *
 * 2026-08 MUI 재설계: 손으로 쓴 입력(.c-search/.k-chip/textarea)을 MUI 폼 컴포넌트로 바꿨다.
 * 값은 rem/테마 값이라 4K에서 글자와 여백이 함께 커진다. 저장 로직(coerce/dry-run/보안 완화 확인/
 * 미저장 변경 보호)은 한 줄도 바꾸지 않았다 — 이 화면의 위험은 전부 그쪽에 있다(그 로직은
 * ./SettingEditor.jsx에 있다, 파일을 나누며 옮긴 것이지 다시 쓴 것이 아니다). */
export function Settings() {
  const [sel, setSel] = useState(null);
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useNavigate();
  const auth = useAuth();
  const canWrite = (auth.data && WRITE_ROLES.includes(auth.data.role)) || false;
  const canReachMaintenance = (auth.data && MAINTENANCE_READ_ROLES.includes(auth.data.role)) || false;
  const canReachConsoles = (auth.data && CONSOLE_SCREEN_ROLES.includes(auth.data.role)) || false;
  const q = useQuery({ queryKey: ["settings"], queryFn: () => api("/api/admin/settings"), retry: false });

  const map = (q.data && q.data.settings) || {};
  // SETTING_LABELS/OBJECT_SCHEMA_HELP/STRUCTURED_OBJECT_KEYS/INT_BOUNDS는 백엔드 registry.py의
  // REGISTRY와 같은 키를 손으로 따로 유지한다(공유 소스가 없다) — 새 키가 registry.py에 추가되고
  // 여기 라벨이 빠지면, 원시 영문 키가 표에 그대로 새어 나가는데도 조용히(에러 없이) 넘어간다.
  // 개발 중 눈에 띄도록 최소한의 드리프트 경고를 남긴다. **운영에서는 이 경고가 침묵하므로**
  // 진짜 안전망은 `settings-labels.test.js` 다 — 그쪽이 registry.py 의 키 목록과 대조한다
  // (N6 이 이 게이트를 뚫고 나간 뒤에 붙였다).
  React.useEffect(() => {
    // 이 드리프트 경고는 개발자용 유지보수 힌트다 — 프로덕션 사용자의 devtools 콘솔로 새지 않도록
    // 개발 빌드에서만 낸다('no console.log in production' 규칙, typescript/coding-style.md).
    if (!(import.meta && import.meta.env && import.meta.env.DEV)) return;
    Object.keys(map).forEach((k) => {
      if (!SETTING_LABELS[k]) console.warn("[Settings] SETTING_LABELS에 없는 설정 키: " + k + ", registry.py에 새 키를 추가했다면 SETTING_LABELS(Settings.jsx)에도 한국어 라벨을 추가하세요.");
      // displayValue()의 raw-JSON(JSON.stringify) 폴백은 summarizeSetting이 그 키를 모를 때만 쓰인다 -
      // 지금은 등록된 4개 object 설정이 전부 요약 분기를 갖고 있어 이 폴백이 죽은 코드다. 새 object
      // 설정이 registry.py에 추가되고 summarizeSetting에 짝이 되는 한국어 분기가 빠지면, SETTING_LABELS
      // 드리프트와 같은 방식으로 콘솔에 알려 raw JSON이 조용히 화면에 새지 않게 한다.
      const row = map[k];
      if (row && row.value != null && (row.type === "object" || row.type === "json") && summarizeSetting(k, row.value) == null) {
        console.warn("[Settings] summarizeSetting에 한국어 요약 분기가 없는 object 설정 키: " + k + ", 추가하지 않으면 값 열에 raw JSON이 그대로 노출됩니다.");
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q.data]);
  // "설정" 열의 원시 값 자체를 이미 사람이 읽는 한국어 라벨로 만든다, 커스텀 render 대신 원시
  // 값을 그대로 보여주면, kit.jsx의 DataTable이 그 값으로 '상세 보기: <라벨>'을 만들어 스크린리더/
  // 음성 제어 사용자가 행마다 다른 aria-label을 듣는다(예전엔 render가 있어 모든 행이 동일하게
  // '상세 보기'로만 들렸다). raw 키는 옆의 별도 열로 유지해 정보 손실 없이 보인다.
  const rows = Object.keys(map)
    .filter((k) => !MAINTENANCE_KEYS.includes(k) && !DEDICATED_SCREEN_KEYS.includes(k))
    .map((k) => ({ key: k, label: settingLabel(k), ...map[k] }));
  /* 열에 width를 주지 않는다(DataTable이 지원하긴 한다). 이 표는 '설명'만 길고 나머지는 짧은데,
   * 앞 네 열에 고정 폭을 주면 요청 폭 합이 1366px 화면의 가용 폭을 넘겨 브라우저가 폭을 지정하지
   * 않은 '설명' 열을 0에 가깝게 짜부라뜨린다 — 실제로 설명 글자가 한 줄에 한 자씩 세로로 흘렀다.
   * 폭 배분은 브라우저 auto 레이아웃에 맡긴다(내용에 비례해 나눈다). */
  const columns = [
    { key: "label", label: "설정" },
    { key: "key", label: "키", render: (r) => <Typography component="span" variant="caption" color="text.secondary">{r.key}</Typography> },
    { key: "value", label: "값", render: (r) => summarizeSetting(r.key, r.value) || displayValue(r.value) },
    // '변경됨'은 기본값과 다를 뿐 문제 상태가 아니다 — warn(주황)은 이상으로 오독되므로 info로 표시한다.
    { key: "is_default", label: "상태", render: (r) => <Badge value={r.is_default ? "기본값" : "변경됨"} kind={r.is_default ? "neutral" : "info"} /> },
    { key: "description", label: "설명" },
  ];

  return (
    <div className="c-screen">
      <PageHeader area="운영" title="설정" />
      {/* 다른 관리 화면(DataScreen)의 help 인트로와 같은 패턴, 처음 오는 관리자에게 화면 사용법을 안내한다. */}
      {/* '즉시 적용됩니다'는 사실이 아니었다, 세션 정책은 신규 세션부터, 허용 도메인은 사용자 생성 시, 보존 기간은 다음 정리 작업 때 반영된다. 적용 시점은 항목별 '설명'을 따르도록 문구를 완화한다. */}
      {/* 예전엔 이 안내가 인트로 Callout, '열람만 가능' 안내, '유지보수' 안내로 3개의 서로 떨어진
          시각 블록이었다, 개별로는 다 맞는 말이지만 함께 있으면 세 조각 난 도입부처럼 읽혀 아래
          진짜 콘텐츠(설정 표)를 더 밀어냈다. 한 Callout 안의 문단으로 한 덩어리로 묶는다. */}
      <Box sx={{ mb: 2.5, "& p": { m: 0 }, "& p + p": { mt: 0.75 } }}>
        <Callout tone="info">
          {/* 버전 기록은 읽기 전용 역할(operator, auditor)도 편집기의 '버전 기록' 버튼으로 열람할 수
              있다(롤백만 canWrite), 예전엔 canWrite일 때만 언급해, 읽기 역할은 이력의 존재조차 몰랐다. */}
          <p>시스템 동작 값을 관리합니다. 항목을 클릭하면 편집기가 열립니다. 저장 시 유효성 검증 후 반영되며, 적용 시점은 항목마다 다를 수 있습니다(각 항목의 ‘설명’ 참고).{canWrite ? " 각 항목의 ‘버전 기록’에서 이전 값으로 되돌릴 수 있습니다." : " 각 항목의 ‘버전 기록’에서 이전 변경 이력을 볼 수 있습니다."}</p>
          {!canWrite ? <p>설정 값은 열람만 가능합니다. 변경은 관리자, 시스템 관리자만 할 수 있습니다.</p> : null}
          {/* maintenance_mode, maintenance_message는 이 표에서 의도적으로 숨겨진다(위 MAINTENANCE_KEYS) -
              숨긴 이유만 있고 어디로 갔는지 안내가 없으면 관리자가 '유지보수 스위치가 없어졌다'고 오인한다.
              /maintenance는 operator, admin, system_admin, auditor가 조회할 수 있다(App.jsx RequireRole/NAV) -
              쓰기만 canWrite(admin/system_admin)로 서버가 막으므로, 이 안내 링크는 canWrite가 아니라
              MAINTENANCE_READ_ROLES로 게이트해야 조회만 가능한 역할도 실제로 열 수 있는 화면을 클릭할 수 있다. */}
          <p>유지보수 모드, 점검 공지는 {canReachMaintenance
            ? <Link component="button" type="button" underline="hover" sx={{ font: "inherit", verticalAlign: "baseline" }} onClick={() => nav("/maintenance")}>‘유지보수’ 화면</Link>
            : "‘유지보수’ 화면"}에서 관리합니다.</p>
          {/* 숨긴 이유만 있고 어디로 갔는지 안내가 없으면 관리자가 '노션 설정이 없어졌다'고
              오인한다 - 유지보수 안내와 같은 실수를 반복하지 않는다. */}
          <p>노션 데이터베이스 id 와 토큰은 {canReachConsoles
            ? <Link component="button" type="button" underline="hover" sx={{ font: "inherit", verticalAlign: "baseline" }} onClick={() => nav("/notion-console")}>‘Notion 관리’ 화면</Link>
            : "‘Notion 관리’ 화면"}에서, AI 설정은 {canReachConsoles
            ? <Link component="button" type="button" underline="hover" sx={{ font: "inherit", verticalAlign: "baseline" }} onClick={() => nav("/llm-console")}>‘AI 관리’ 화면</Link>
            : "‘AI 관리’ 화면"}에서 관리합니다. 두 화면에는 연결 테스트가 함께 있습니다.</p>
        </Callout>
      </Box>
      {q.isLoading ? <Card><Skeleton lines={5} /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        /* effective_settings()는 항상 REGISTRY의 모든 키를 반환하므로 정상 경로에선 도달하지 않는다.
           응답이 비정상(빈 형태)일 때를 위한 방어적 폴백으로만 남긴다. */
        /* effective_settings()가 항상 전 키를 돌려주므로 이 빈 상태는 비정상 응답에서만 뜬다 -
           막다른 안내 대신 원인(비어 있음)과 다시 불러오기 경로를 준다(오류에 가깝게 취급). */
        : rows.length === 0 ? <EmptyState title="설정을 표시할 수 없습니다" help="설정을 불러왔지만 항목이 비어 있습니다, 일시적인 문제일 수 있습니다." action={<Button onClick={() => q.refetch()}>다시 불러오기</Button>} />
        : <Card sx={{ mb: 2.5 }}><DataTable columns={columns} rows={rows} rowKey={(r) => r.key} onRow={setSel} /></Card>}
      {/* 시스템 설정 표 아래에 개인 취향 설정을 둔다 — 위와 성격이 달라(서버 저장 아님) 카드를 나눈다. */}
      <AccentPicker />
      <SettingEditor setting={sel} canWrite={canWrite} onClose={() => setSel(null)}
        onSaved={(res) => {
          qc.invalidateQueries({ queryKey: ["settings"] });
          // 버전 기록 쿼리도 함께 무효화한다 — SettingVersions.doRollback과 동일한 이유: 기본
          // staleTime(30초) 안에 '버전 기록'을 열면 방금 저장한 변경이 빠진 캐시를 보여준다.
          if (sel) qc.invalidateQueries({ queryKey: ["settings", sel.key, "versions"] });
          setSel(null);
          // 재시작이 필요한 키는 저장만으로 적용되지 않는다 — 수동 재시작 안내를 분명히 남긴다(현재는 해당 키 없음, 향후 대비).
          if (res && res.restart_required) toast("설정을 저장했습니다, 적용하려면 서비스를 수동으로 재시작하세요.", "info");
          else toast("설정을 저장했습니다.", "success");
        }} />
    </div>
  );
}
