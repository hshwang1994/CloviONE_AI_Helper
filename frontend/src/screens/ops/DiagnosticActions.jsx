import React from "react";
import Box from "@mui/material/Box";
import { Button } from "../../ui/kit.jsx";

/* 진단 화면 헤더의 액션 3종(수집/복사/다운로드) — 상태(수집 중·복사됨)는 부모(Diagnostics)가
 * 들고, 이 컴포넌트는 그 상태를 보여주고 클릭을 그대로 위임하는 순수 표시 컴포넌트다. */
export function DiagnosticActions({ manualCollecting, onCollect, hasText, copied, onCopy, onDownload }) {
  return (
    <>
      <Button variant="primary" onClick={onCollect} disabled={manualCollecting}>{manualCollecting ? "수집 중…" : "진단 수집"}</Button>
      {/* '복사'↔'복사됨' 라벨 전환으로 버튼 폭이 바뀌어 옆 'JSON 다운로드' 버튼이 그때마다
          옆으로 밀리던 문제, 폭을 예약하는 래퍼로 감싼다(rem이라 4K에서 함께 커진다). */}
      {hasText ? (
        <>
          <Box sx={{ minWidth: "5.5rem", display: "inline-flex" }}>
            <Button onClick={onCopy} sx={{ width: "100%" }}>{copied || "복사"}</Button>
          </Box>
          <Button onClick={onDownload}>JSON 다운로드</Button>
        </>
      ) : null}
    </>
  );
}
