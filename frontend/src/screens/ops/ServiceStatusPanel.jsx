import React from "react";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { Badge, MetricStrip, Callout, useToast } from "../../ui/kit.jsx";
import { DashSection, StatusList, StatusTile } from "../../ui/adminKit.jsx";
import { fmtNum, serviceLabel, fmtCertDays, copyText } from "./opsHelpers.js";

/* 진단 화면의 "시스템 리소스" + "서비스 상태" 카드 — 둘 다 '지금 이 순간' 스냅샷이라 한 패널로 묶는다.
 * 서비스가 중단·응답 없음이면 재시작 안내(journalctl 명령 + 복사)까지 이 패널이 책임진다 — 상태를
 * 보여주기만 하고 다음 행동이 없는 막다른 카드로 남기지 않는다(스펙 §10: 웹에서 재시작하는 수단은
 * 제공하지 않으므로 로그 확인·담당자 재시작으로 안내한다). */
export function ServiceStatusPanel({ disk, mem, certDaysRemaining, comps, nav }) {
  const toast = useToast();
  // 실제로 중단·응답 없음 상태인 컴포넌트의 systemd 유닛만 안내한다 — web과 worker/scheduler는
  // 서로 다른 유닛(clovirone-web-assistant.service / clovirone-web-worker.service)이라, 웹만 죽었을
  // 때 워커 로그를 보라고 하면 실제 장애 순간에 엉뚱한 곳을 가리키게 된다. worker_conversational
  // (D-118)은 배치 워커와 또 다른 세 번째 유닛이다 — 예전의 이분법(web이 아니면 무조건
  // clovirone-web-worker)을 그대로 두면 대화형 레인이 죽었을 때도 배치 워커 로그를 보라고
  // 안내해, 실제 장애 유닛과 다른 곳을 가리키는 바로 그 문제가 재발한다.
  const DOWN_UNIT_FOR = {
    web: "clovirone-web-assistant",
    worker_conversational: "clovirone-web-worker-conversational",
  };
  const downComponentKeys = Object.keys(comps).filter((k) => comps[k] && comps[k] !== "up");
  const downUnits = Array.from(new Set(downComponentKeys.map((k) => DOWN_UNIT_FOR[k] || "clovirone-web-worker")));

  return (
    <>
      {/* 디스크, 메모리, 인증서가 모두 null이면(비-Linux 호스트, nginx TLS 종단 등) 섹션 자체를 숨긴다 -
          Dashboard.jsx의 규칙(§ '영구, 죽은 타일을 남기지 않는다')과 동일하게, 값이 없는 개별 타일도 숨긴다. */}
      {(disk.free_gb != null || disk.used_pct != null || mem.used_pct != null || certDaysRemaining != null) ? (
        <DashSection title="시스템 리소스">
          {/* Dashboard.jsx가 같은 필드(disk.free_gb)를 fmtNum()+단위-on-값으로 보여주는데
              이 화면만 raw 숫자에 라벨 괄호 단위였다, 같은 표기 규칙으로 맞춘다. */}
          <MetricStrip
            ariaLabel="시스템 리소스"
            items={[
              disk.free_gb != null ? { key: "disk_free", value: fmtNum(disk.free_gb) + "GB", label: "디스크 여유" } : null,
              disk.used_pct != null ? { key: "disk_used", value: disk.used_pct + "%", label: "디스크 사용",
                kind: disk.used_pct >= 85 ? "danger" : disk.used_pct >= 80 ? "warn" : undefined } : null,
              mem.used_pct != null ? { key: "mem", value: mem.used_pct + "%", label: "메모리 사용",
                kind: mem.used_pct >= 90 ? "danger" : mem.used_pct >= 80 ? "warn" : undefined } : null,
              certDaysRemaining != null ? { key: "cert", value: fmtCertDays(certDaysRemaining), label: "인증서 만료",
                kind: certDaysRemaining <= 0 ? "danger" : certDaysRemaining <= 30 ? "warn" : undefined } : null,
            ].filter(Boolean)}
          />
        </DashSection>
      ) : null}
      {/* build_dashboard()(app/health/service.py)는 components/counts/jobs_24h를 항상 고정된
          채워진 dict로 돌려준다, 이 Object.keys(...).length 가드는 기능적으로 결코 false가 될
          수 없다(사전 방어일 뿐). 실제 통제는 bundle 자체의 존재 여부다(부모의 !bundle 가드). */}
      {Object.keys(comps).length ? (
        <DashSection title="서비스 상태"
          // PA-RC-0028: Dashboard.jsx의 같은 섹션과 동일하게 도넛 대신 'N / M' 한 줄 요약을
          // 제목 옆에 둔다(up만 정상으로 센다 — unknown/down은 위 Callout이 이미 별도로 알린다).
          action={<Typography variant="body2" color="text.secondary">정상 {Object.values(comps).filter((v) => v === "up").length} / {Object.keys(comps).length}</Typography>}>
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
                  <Link component="button" type="button" variant="body2" underline="hover" onClick={() => copyText(journalCmd).then((ok) => toast(ok ? "명령을 복사했습니다." : "복사에 실패했습니다. 직접 선택해 복사하세요.", ok ? "success" : "error"))}>복사</Link>
                  )를 확인하고, 필요하면 담당자가 서비스를 재시작하세요.
                </Callout>
              </Box>
            );
          })() : null}
          <StatusList ariaLabel="서비스 상태">
            {Object.keys(comps).map((k) => {
              // 'unknown'(하트비트 없음/오래됨)도 상단 healthVerdict()가 이미 주의 대상으로 세는 문제다 -
              // 배지를 무채색 그대로 두면 상단 '주의 N건' 배너와 이 타일의 심각도가 서로 어긋나 보인다.
              const badgeKind = comps[k] === "unknown" ? "warn" : undefined;
              // 바로 아래 '외부 연동' 카드는 클릭 가능한데 이 서비스 카드만 정적이라, 시각적으로
              // 똑같은 두 그리드가 나란히 있어 죽은 카드를 눌러 보게 유도했다, 워커/스케줄러는
              // Dashboard.jsx compNav처럼 작업 큐(/jobs)로 드릴다운시킨다(웹은 드릴다운할 곳이 없어 정적 유지).
              const dest = (k === "worker" || k === "scheduler" || k === "worker_conversational") ? "/jobs" : null;
              // 상단 healthVerdict() 배너, Dashboard.jsx 서비스 카드는 이 상태를 '응답 없음'이라
              // 부른다, kit.jsx STATUS_TEXT는 'unknown'을 '알 수 없음'으로 옮겨, 같은 상태를
              // 이 화면 안에서만 다른 한국어로 말하고 있었다(배너와 타일이 서로 모순).
              return (
                <StatusTile key={k} name={serviceLabel(k)}
                  onClick={dest ? () => nav(dest) : undefined}
                  ariaLabel={serviceLabel(k) + " 관련 작업 큐로 이동"}>
                  <Badge value={comps[k] === "unknown" ? "응답 없음" : comps[k]} kind={badgeKind} />
                </StatusTile>
              );
            })}
          </StatusList>
        </DashSection>
      ) : null}
    </>
  );
}
