import React from "react";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { Badge, Callout, MetaBar, Section, useToast } from "../../ui/kit.jsx";
import { StatusKpiStrip } from "../../ui/StatusKpi.jsx";
import { StatusList, StatusTile } from "../../ui/adminKit.jsx";
import { STRIP_AS_META_MAX } from "../data-screen/SummaryView.jsx";
import {
  fmtNum, serviceLabel, fmtCertDays, copyText,
  componentState, upSummaryText, SERVICE_STATE_LABEL, SERVICE_STATE_KIND,
} from "./opsHelpers.js";

/* 진단 화면의 "시스템 리소스" + "서비스 상태" 카드 — 둘 다 '지금 이 순간' 스냅샷이라 한 패널로 묶는다.
 * 서비스가 중단·응답 없음이면 재시작 안내(journalctl 명령 + 복사)까지 이 패널이 책임진다 — 상태를
 * 보여주기만 하고 다음 행동이 없는 막다른 카드로 남기지 않는다(스펙 §10: 웹에서 재시작하는 수단은
 * 제공하지 않으므로 로그 확인·담당자 재시작으로 안내한다). */
/* `aside` 는 「필수 서비스」 옆에 설 구획(진단의 「외부 연동」)이고, `pair` 가 참일 때만 xl 부터
   2열이다 — 대시보드와 같은 규칙(D-343): 양쪽 다 목록일 때만 나란히 둔다. 오른쪽이 문장 한 줄뿐이면
   균등 분할이 그 옆을 빈 칸으로 남긴다. */
export function ServiceStatusPanel({ disk, mem, certDaysRemaining, comps, nav, aside = null, pair = false }) {
  const [copyFailed, setCopyFailed] = React.useState(false);
  const toast = useToast();
  // 실제로 중단·응답 없음 상태인 컴포넌트의 systemd 유닛만 안내한다 — web과 worker/scheduler는
  // 서로 다른 유닛이라, 웹만 죽었을 때 워커 로그를 보라고 하면 실제 장애 순간에 엉뚱한 곳을
  // 가리키게 된다. worker_conversational (D-118)은 배치 워커와 또 다른 세 번째 유닛이다 —
  // 예전의 이분법(web이 아니면 무조건 배치 워커)을 그대로 두면 대화형 레인이 죽었을 때도
  // 배치 워커 로그를 보라고 안내해, 실제 장애 유닛과 다른 곳을 가리키는 바로 그 문제가 재발한다.
  //
  // 이름은 제품 slug 를 따른다(app/core/product.py). 여기 옛 slug 가 남으면 장애 중에
  // **없는 유닛**의 로그를 보라고 안내하게 되고, 그 순간 이 화면은 안내가 아니라 방해다.
  const DOWN_UNIT_FOR = {
    web: "clovirassist-web",
    worker_conversational: "clovirassist-worker-conversational",
  };
  const downComponentKeys = Object.keys(comps).filter((k) => comps[k] && comps[k] !== "up");
  const downUnits = Array.from(new Set(downComponentKeys.map((k) => DOWN_UNIT_FOR[k] || "clovirassist-worker")));
  /* Dashboard.jsx가 같은 필드(disk.free_gb)를 fmtNum()+단위-on-값으로 보여주는데
     이 화면만 raw 숫자에 라벨 괄호 단위였다, 같은 표기 규칙으로 맞춘다. 값이 없는 측정은 서지 않는다. */
  const resources = [
    disk.free_gb != null ? { key: "disk_free", value: fmtNum(disk.free_gb) + "GB", label: "디스크 여유" } : null,
    disk.used_pct != null ? { key: "disk_used", value: disk.used_pct + "%", label: "디스크 사용",
      kind: disk.used_pct >= 85 ? "danger" : disk.used_pct >= 80 ? "warn" : undefined } : null,
    mem.used_pct != null ? { key: "mem", value: mem.used_pct + "%", label: "메모리 사용",
      kind: mem.used_pct >= 90 ? "danger" : mem.used_pct >= 80 ? "warn" : undefined } : null,
    certDaysRemaining != null ? { key: "cert", value: fmtCertDays(certDaysRemaining), label: "인증서 만료",
      kind: certDaysRemaining <= 0 ? "danger" : certDaysRemaining <= 30 ? "warn" : undefined } : null,
  ].filter(Boolean);

  return (
    <>
      {/* 디스크, 메모리, 인증서가 모두 null이면(비-Linux 호스트, nginx TLS 종단 등) 섹션 자체를 숨긴다 -
          Dashboard.jsx의 규칙(§ '영구, 죽은 타일을 남기지 않는다')과 동일하게, 값이 없는 개별 타일도 숨긴다.
          측정이 둘 이하이면 판 대신 속성 줄이다(D-501 · `SummaryView.jsx` 의 같은 규칙) — 1920 에서 디스크 여유 · 사용 두 값이
          각자 반폭 판 하나씩을 차지해 숫자 하나 옆이 780px 비었다. 누를 곳이 없는 값이라 판을 세울 이유가 없다. 셋 이상이면
          타일 줄이 나란한 비교를 돕는다. 경계를 넘은 값은 값 옆 배지가 톤을 말한다. */}
      {resources.length ? (
        <Section titleAs="h2" title="시스템 리소스">
          {resources.length <= STRIP_AS_META_MAX ? (
            <MetaBar
              ariaLabel="시스템 리소스"
              items={resources.map((it) => ({
                key: it.key,
                label: it.label,
                value: it.kind ? <Badge value={it.value} kind={it.kind} /> : it.value,
              }))}
            />
          ) : (
            <StatusKpiStrip ariaLabel="시스템 리소스" items={resources} />
          )}
        </Section>
      ) : null}
      {/* build_dashboard()(app/health/service.py)는 components/counts/jobs_24h를 항상 고정된
          채워진 dict로 돌려준다, 이 Object.keys(...).length 가드는 기능적으로 결코 false가 될
          수 없다(사전 방어일 뿐). 실제 통제는 bundle 자체의 존재 여부다(부모의 !bundle 가드). */}
      {Object.keys(comps).length ? (
        <Box sx={{ display: "grid", alignItems: "start", columnGap: 4, gridTemplateColumns: { xs: "minmax(0,1fr)", xl: pair ? "repeat(2, minmax(0,1fr))" : "minmax(0,1fr)" } }}>
        {/* 이름은 대시보드와 **같아야 한다** — 같은 데이터를 두 화면이 다른 이름으로 부르면
           운영자는 그것이 다른 것인지 확인해야 한다. 그쪽이 「필수 서비스」로 부르면서
           외부 연동과 분모를 갈랐고, 여기도 같은 말을 쓴다. */}
        <Section titleAs="h2" title="필수 서비스"
          action={<Typography variant="body2" color="text.secondary">{upSummaryText(Object.values(comps).map(componentState))}</Typography>}>
          {/* 중단·응답 없음을 빨간 배지로만 두면 조치할 곳이 없는 막다른 화면이 된다 — 다음 행동을 한 줄로 안내한다.
              (스펙 §10: 임의 systemd 재시작 API는 제공하지 않으므로 로그 확인·담당자 재시작으로 안내한다.) */}
          {downUnits.length ? (() => {
            // 장애 대응 중 그대로 터미널에 붙여 넣을 명령이다, 감사 로그 대상 ID와 같은 이유로
            // (Dashboard.jsx의 copyObjectId) hover 전용 선택이 아니라 눌러서 복사하는 버튼을 함께 준다.
            const journalCmd = "journalctl -u " + downUnits.join(" -u ");
            return (
              <Box sx={{ mb: 2 }}>
                <Callout tone="danger">
                  일부 서비스가 응답하지 않습니다. 이 화면에서 재시작할 수는 없습니다. 서버 로그(예: <Box component="code" sx={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>{journalCmd}</Box>{" "}
                  <Link component="button" type="button" variant="body2" underline="hover" onClick={() => { setCopyFailed(false); copyText(journalCmd).then((ok) => { if (ok) toast("명령을 복사했습니다.", "success"); else setCopyFailed(true); }); }}>복사</Link>
                  )를 확인하고, 필요하면 담당자가 서비스를 재시작하세요.
                  {/* 복사가 안 된 사실은 이 상자 안에 남는다 — 명령을 직접 선택해 복사해야 한다. */}
                  {copyFailed ? <Box component="span" sx={{ display: "block", mt: 0.5 }}>복사에 실패했습니다. 직접 선택해 복사하세요.</Box> : null}
                </Callout>
              </Box>
            );
          })() : null}
          <StatusList ariaLabel="필수 서비스">
            {Object.keys(comps).map((k) => {
              /* 상태 어휘는 `opsHelpers.js` 한 곳에서 온다 — 예전에는 이 화면이 배지 값을
                 직접 고르고 요약은 `v === "up"` 만 세어서, 세는 규칙과 그리는 규칙이 갈릴
                 수 있었다(대시보드에서 실제로 갈렸다). */
              const state = componentState(comps[k]);
              // 바로 아래 '외부 연동' 카드는 클릭 가능한데 이 서비스 카드만 정적이라, 시각적으로
              // 똑같은 두 그리드가 나란히 있어 죽은 카드를 눌러 보게 유도했다, 워커/스케줄러는
              // Dashboard.jsx compNav처럼 작업 큐(/jobs)로 드릴다운시킨다(웹은 드릴다운할 곳이 없어 정적 유지).
              const dest = (k === "worker" || k === "scheduler" || k === "worker_conversational") ? "/jobs" : null;
              return (
                <StatusTile key={k} name={serviceLabel(k)}
                  onClick={dest ? () => nav(dest) : undefined}
                  ariaLabel={serviceLabel(k) + " 관련 작업 큐로 이동"}>
                  <Badge value={SERVICE_STATE_LABEL[state]} kind={SERVICE_STATE_KIND[state]} />
                </StatusTile>
              );
            })}
          </StatusList>
        </Section>
        {aside}
        </Box>
      ) : aside}
    </>
  );
}
