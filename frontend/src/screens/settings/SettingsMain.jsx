import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { useAuth } from "../../app/auth.jsx";
import { useQueryState } from "../../lib/useQueryState.js";
import { Badge, Button, DataTable, DotLabel, EmptyState, ErrorState, RowActions, useToast } from "../../ui/kit.jsx";
import { FilterBar, FilterToggle } from "../../ui/FilterBar.jsx";
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
/* 주소로 **항목 하나**를 연다 (`#/settings?setting=backup_schedule`).
 *
 * 다른 화면이 「여기서 고치세요」라고 보낼 곳이 필요하다. 예전에는 그런 버튼이
 * (백업 화면의 «백업 일정 설정») `#/settings` 만 가리켰고, 눌린 사람은 스무 항목짜리 표
 * 앞에 서서 어느 줄인지를 스스로 찾아야 했다 — 보내 준 쪽은 어느 줄인지 알고 있었는데도.
 * 스펙 상수는 **모듈에 둔다**(useQueryState 문서: 렌더마다 새 객체면 메모가 깨진다). */
const DEEPLINK_SPEC = { setting: "" };

export function Settings({ embedded = false } = {}) {
  const [sel, setSel] = useState(null);
  const [deepLink, setDeepLink] = useQueryState(DEEPLINK_SPEC);
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
  /* 주소가 항목 하나를 지목했으면 그 편집기를 연다 — **한 번만**. 열고 나서 주소를 비우는
     이유는 둘이다: 닫은 뒤 화면을 다시 그릴 때 같은 모달이 계속 되살아나지 않게, 그리고
     그 상태에서 새로고침하면 사용자가 이미 닫은 것이 또 열리지 않게. 모르는 키는 조용히
     둔다 — 옛 링크가 오류 화면이 되지 않게 하는 이 저장소의 딥링크 규약 그대로다. */
  const deepLinkKey = deepLink.setting;
  React.useEffect(() => {
    if (!deepLinkKey) return;
    /* 이 표가 실제로 그리는 줄만 연다. 유지보수·AI 키는 여기서 일부러 숨긴 것이라
       (전용 화면이 따로 있고, 서버가 역할도 다르게 막는다) 주소로 뒷문을 내지 않는다. */
    const row = rows.find((r) => r.key === deepLinkKey);
    if (!row) return;
    setSel(row);
    setDeepLink({ setting: "" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deepLinkKey, q.data]);
  /* '항목명' 외 열엔 width를 주지 않는다(DataTable이 지원하긴 한다). 이 표는 '설명'만
   * 길고 나머지는 짧은데, 앞 네 열 전부에 고정 폭을 주면 요청 폭 합이 1366px 화면의 가용
   * 폭을 넘겨 브라우저가 폭을 지정하지 않은 '설명' 열을 0에 가깝게 짜부라뜨린다 — 실제로
   * 설명 글자가 한 줄에 한 자씩 세로로 흘렀다(DS-06). 나머지 열의 폭 배분은 여전히 브라우저
   * auto 레이아웃에 맡긴다(내용에 비례해 나눈다).
   *
   * PA-RC-0037: '항목명'은 이 표에서 행을 식별하는 유일한 열인데 1366px에서 91px로
   * 줄어 11행 중 8행이 잘렸다(예: "계정 추가 허용 도메인" 141px 필요) — identifier:true로
   * 최소 폭만 준다(minWidth는 바닥값이지 다른 열처럼 고정 width가 아니라서 위 함정을
   * 다시 밟지 않는다 — '설명'은 여전히 자유롭게 auto 레이아웃 대로 남는 공간을 가져간다). */
  /* 「항목명」은 이 표의 제목 열이다 — 제목 열만 왼쪽이고 나머지는 가운데다(핸드오프 RULES §5 · 조합 계약 C-3). 바닥 폭
     10rem 은 그대로다(PA-RC-0037). */
  const columns = [
    { key: "label", label: "항목명", type: "title", minWidth: "10rem" },
    // PA-RC-0022: 백엔드 키는 기본 숨김이다 — showKey가 꺼져 있으면 이 열 자체를 안 만든다
    // (렌더는 하고 CSS로 숨기지 않는다, 스크린리더가 안 쓰는 열까지 훑지 않게).
    ...(showKey ? [{ key: "key", label: "키", render: (r) => <Typography component="span" variant="caption" color="text.secondary">{r.key}</Typography> }] : []),
    { key: "value", label: "현재 값", type: "text", render: (r) => summarizeSetting(r.key, r.value) || displayValue(r.value) },
    /* 적용 상태 (지시 45). 두 가지를 말한다.
     *
     *  - **수정됨** — 기본값에서 벗어났다. 기본값 그대로면 배지가 아예 없다(PA-RC-0022:
     *    "변경 안 됐다"는 사실 자체는 정보 가치가 낮다 — 눈에 띄어야 하는 것은 누가 뭔가
     *    바꿨다는 사실 하나다).
     *  - **재시작 필요** — 저장해도 워커가 다시 뜨기 전에는 그 값으로 동작하지 않는다.
     *    예전에는 이 사실이 저장 후 토스트에만 잠깐 떴다가 사라졌다 — 표를 다시 열면
     *    "저장됐는데 왜 안 바뀌지"를 알 방법이 없었다. */
    { key: "is_default", label: "적용 상태", type: "status", nowrap: true, render: (r) => (
      <Box sx={{ display: "flex", gap: 0.75, alignItems: "center", flexWrap: "wrap" }}>
        {r.is_default ? null : <Badge value="수정됨" kind="info" />}
        {/* 표 안 표지는 면 없는 점 + 낱말이다(핸드오프 RULES §2 · ACCEPTANCE F7). */}
        {r.restart_required ? <DotLabel label="재시작 필요" tone="warn" /> : null}
      </Box>
    ) },
    // VIS-55: 백엔드 description이 라벨과 같은 말로 시작하는 항목이 여럿이다(예: "대화 보존
    // 기간(일)" 라벨 + "대화 보존 기간(일). 초과 시…" 설명) — 바로 왼쪽 열과 같은 문장을
    // 반복해 가로 공간만 먹었다. 그 앞부분이 라벨 그대로면 벗겨내고 나머지만 보여준다(라벨
    // 자체를 여기서 다시 만들지 않고 실제 렌더된 r.label과 대조 — 두 소스가 갈리면 이 열이
    // 조용히 잘못 벗겨내는 대신 원문을 그대로 보여주게 안전한 쪽으로 둔다).
    { key: "description", label: "설명", type: "text", render: (r) => {
      const desc = r.description;
      if (!desc) return "-";
      if (desc.startsWith(r.label)) {
        const rest = desc.slice(r.label.length).replace(/^[.:]\s*/, "");
        if (rest) return rest;
      }
      return desc;
    } },
    /* 변경 어포던스 (지시 32). 행 전체가 예전에도 눌렸지만 **눌러도 되는지 화면이 말하지
     * 않았다** — 읽기 전용 표처럼 보였고, 사용자 지적이 정확히 그것이었다. 각 행이 자기
     * 변경 방법을 들고 있게 한다. 권한이 없으면 죽은 버튼을 남기지 않고 왜 못 바꾸는지 쓴다
     * (프런트 표시일 뿐 판단은 서버가 한다 — 불변규칙 §5). */
    { key: "_edit", label: "", type: "actions", render: (r) => (
      canWrite
        /* 행 동작은 `RowActions` 다(30 보조, 조합 계약 C-4). 표는 단추에서 시작한 클릭을 행 열기로 번지게 하지 않는다. */
        ? <RowActions actions={[{ key: "edit", label: "수정", onClick: () => setSel(r) }]} />
        : <Typography component="span" variant="caption" color="text.secondary">읽기 전용</Typography>
    ) },
  ];

  /* 🔴 여기 `embedded ? null : <PageHeader area="운영" title="설정" />` 가 있었다.
     이 화면은 **언제나 설정 껍데기 안**이라(`settings/SettingsShell.jsx` 가 `embedded` 로만
     그린다) 도달할 수 없는 갈래였고, `area="운영"` 은 사이드바 묶음(**설정**)과도 어긋나
     있었다. 껍데기가 머리와 `.c-screen` 을 이미 그린다 — 여기서 또 감싸면 바깥 여백이
     두 번 붙는다. */
  return (
    <>
      {q.isLoading ? <DataTable placement="surface" columns={columns} rows={[]} loading />
        : q.isError ? <ErrorState layout="region" error={q.error} onRetry={() => q.refetch()} />
        /* effective_settings()는 항상 REGISTRY의 모든 키를 반환하므로 정상 경로에선 도달하지 않는다.
           응답이 비정상(빈 형태)일 때를 위한 방어적 폴백으로만 남긴다. */
        /* effective_settings()가 항상 전 키를 돌려주므로 이 빈 상태는 비정상 응답에서만 뜬다 -
           막다른 안내 대신 원인(비어 있음)과 다시 불러오기 경로를 준다(오류에 가깝게 취급). */
        : rows.length === 0 ? <EmptyState title="설정을 표시할 수 없습니다" help="설정을 불러왔지만 항목이 비어 있습니다. 일시적인 문제일 수 있습니다." action={<Button size="sm" onClick={() => q.refetch()}>다시 불러오기</Button>} />
        : <>
            {/* 기술 정보 토글 (지시 36). 원시 설정 키는 운영·장애 분석에 필요한 값이지만
                일반 사용자 언어가 아니다 — 기본은 숨기고 필요할 때 꺼내 본다. */}
            {/* 목록 위의 보기 줄도 필터 바다 — 켬/끔은 34 중립 단추이고 줄 오른쪽 끝 묶음이며, 다른 목록 화면처럼 아래
                실선으로 목록과 갈린다(핸드오프 RULES §3 · 계획 P-14 · 조합 계약 C-1). */}
            <FilterBar
              end={<FilterToggle pressed={showKey} onClick={() => setShowKey(!showKey)}>기술 정보(설정 키) 보기</FilterToggle>}
            />
            {/* 목록 판 — 다른 목록 화면과 같은 판이다(판이 곧 표 상자 · 발은 판 안, 조합 계약 C-3). */}
            <DataTable placement="surface" columns={columns} rows={rows} rowKey={(r) => r.key} onRow={setSel} />
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
    </>
  );
}
