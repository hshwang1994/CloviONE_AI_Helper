import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { useAuth } from "../../app/auth.jsx";
import { PageHeader, Card, Badge, Button, DataTable, Skeleton, EmptyState, ErrorState, useToast } from "../../ui/kit.jsx";
import {
  SETTING_LABELS, settingLabel, WRITE_ROLES, MAINTENANCE_KEYS, DEDICATED_SCREEN_KEYS,
  summarizeSetting, displayValue,
} from "./settingsRegistry.js";
import { SettingEditor } from "./SettingEditor.jsx";

/* 설정 — 시스템 동작 값을 관리한다. GET /api/admin/settings는 {settings:{key:{value,type,
 * description,restart_required,is_default}}} 형태. 편집은 모달에서 타입별 입력 → PUT /{key}. object 타입
 * (ui_branding·password_policy·session_policy·allowed_email_domains)은 JSON 텍스트로 편집한다.
 *
 * 2026-08 MUI 재설계: 손으로 쓴 입력(.c-search/.k-chip/textarea)을 MUI 폼 컴포넌트로 바꿨다.
 * 값은 rem/테마 값이라 4K에서 글자와 여백이 함께 커진다. 저장 로직(coerce/dry-run/보안 완화 확인/
 * 미저장 변경 보호)은 한 줄도 바꾸지 않았다 — 이 화면의 위험은 전부 그쪽에 있다(그 로직은
 * ./SettingEditor.jsx에 있다, 파일을 나누며 옮긴 것이지 다시 쓴 것이 아니다).
 *
 * PA-RC-0017: `embedded`(SettingsShell.jsx의 '시스템 정책' 탭에서 렌더될 때)일 땐 자체
 * PageHeader를 그리지 않는다 — 바깥 탭 헤더가 이미 "관리자 › 운영 › 설정 › 시스템 정책"을
 * 보여주므로 안에서 또 h1을 그리면 탭 하나에 제목이 두 개가 된다. 예전엔 이 표 위에 "시스템
 * 설정/유지보수/Notion 관리/AI 관리는 다른 화면에 있다"는 안내 4문단(Callout)이 있었다 —
 * 그 화면들이 이제 같은 탭 줄에 나란히 보이는 형제 탭이라 어디 있는지 설명할 필요 자체가
 * 없어져 통째로 없앴다(Handoff acceptance_criteria: "안내 4문단이 삭제되어 있다"). */
export function Settings({ embedded = false } = {}) {
  const [sel, setSel] = useState(null);
  // PA-RC-0022 acceptance_criteria 6: 백엔드 키(raw REGISTRY 키 문자열)는 운영 디버깅에는
  // 유용하지만 일반 사용자 언어가 아니다 — 기본 숨김 + 열 토글로 내린다(완전히 없애지는
  // 않는다, constraints가 명시).
  const [showKey, setShowKey] = useState(false);
  const qc = useQueryClient();
  const toast = useToast();
  const auth = useAuth();
  const canWrite = (auth.data && WRITE_ROLES.includes(auth.data.role)) || false;
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
    { key: "label", label: "항목명" },
    // PA-RC-0022: 백엔드 키는 기본 숨김이다 — showKey가 꺼져 있으면 이 열 자체를 안 만든다
    // (렌더는 하고 CSS로 숨기지 않는다, 스크린리더가 안 쓰는 열까지 훑지 않게).
    ...(showKey ? [{ key: "key", label: "키", render: (r) => <Typography component="span" variant="caption" color="text.secondary">{r.key}</Typography> }] : []),
    { key: "value", label: "현재 값", render: (r) => summarizeSetting(r.key, r.value) || displayValue(r.value) },
    // PA-RC-0022 target_design: "「기본값」 배지 10개는 없애고 「수정됨」만 표시한다" — 기본값
    // 상태는 이제 배지가 아예 없는 것으로 표현한다(변경 안 됐다는 사실 자체는 정보 가치가
    // 낮다 - 눈에 띄어야 하는 건 "누가 뭔가 바꿨다"는 사실 하나뿐이다).
    { key: "is_default", label: "상태", render: (r) => (r.is_default ? null : <Badge value="수정됨" kind="info" />) },
    { key: "description", label: "설명" },
  ];

  return (
    <div className="c-screen">
      {embedded ? null : <PageHeader area="운영" title="설정" />}
      {q.isLoading ? <Card><Skeleton lines={5} /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        /* effective_settings()는 항상 REGISTRY의 모든 키를 반환하므로 정상 경로에선 도달하지 않는다.
           응답이 비정상(빈 형태)일 때를 위한 방어적 폴백으로만 남긴다. */
        /* effective_settings()가 항상 전 키를 돌려주므로 이 빈 상태는 비정상 응답에서만 뜬다 -
           막다른 안내 대신 원인(비어 있음)과 다시 불러오기 경로를 준다(오류에 가깝게 취급). */
        : rows.length === 0 ? <EmptyState title="설정을 표시할 수 없습니다" help="설정을 불러왔지만 항목이 비어 있습니다. 일시적인 문제일 수 있습니다." action={<Button onClick={() => q.refetch()}>다시 불러오기</Button>} />
        : <>
            <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1 }}>
              <FormControlLabel
                control={<Checkbox size="small" checked={showKey} onChange={(e) => setShowKey(e.target.checked)} />}
                label="백엔드 키 표시"
              />
            </Box>
            <Card sx={{ mb: 2.5 }}><DataTable columns={columns} rows={rows} rowKey={(r) => r.key} onRow={setSel} /></Card>
          </>}
      <SettingEditor setting={sel} canWrite={canWrite} onClose={() => setSel(null)}
        onSaved={(res) => {
          qc.invalidateQueries({ queryKey: ["settings"] });
          // 버전 기록 쿼리도 함께 무효화한다 — SettingVersions.doRollback과 동일한 이유: 기본
          // staleTime(30초) 안에 '버전 기록'을 열면 방금 저장한 변경이 빠진 캐시를 보여준다.
          if (sel) qc.invalidateQueries({ queryKey: ["settings", sel.key, "versions"] });
          setSel(null);
          // 재시작이 필요한 키는 저장만으로 적용되지 않는다 — 수동 재시작 안내를 분명히 남긴다(현재는 해당 키 없음, 향후 대비).
          if (res && res.restart_required) toast("설정을 저장했습니다. 적용하려면 서비스를 수동으로 재시작하세요.", "info");
          else toast("설정을 저장했습니다.", "success");
        }} />
    </div>
  );
}
