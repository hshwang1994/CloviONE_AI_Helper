import React from "react";
import { PageHeader } from "../ui/kit.jsx";
import { AccentPicker } from "./settings/AccentPicker.jsx";

/* 내 화면 설정 (PA-RC-0022) — 이 브라우저에만 저장되는 개인 표시 설정.
 *
 * 예전엔 화면 강조색이 관리자 전용 「설정」 화면(시스템 정책 표) 하단에 있었다 — 전역 정책과
 * 개인 취향이 한 화면에 있어 적용 범위를 착각하기 쉬웠고(괄호 문장으로만 구분), 무엇보다
 * **관리자가 아니면 이 화면 자체에 닿을 수 없었다** — 개인 취향인데 역할에 따라 못 바꾸는
 * 사람이 있었다. 계정 메뉴 아래로 옮겨 역할과 무관하게 누구나 닿게 한다(acceptance_criteria 5).
 *
 * 다크/라이트 전환은 **여기 없다** — UserMenu.jsx의 기존 결정과 같은 이유(상단바 아이콘이
 * 정본, 두 곳에 상태를 나눠 들면 서로 낡은 채 어긋난다). 이 화면은 강조색만 다룬다.
 *
 * AccentPicker 자체는 옮기지 않았다 — `settings/` 아래 그대로 두고 여기서 가져다 쓴다.
 * 파일 위치가 실제로 무엇에 영향을 주지 않으니(순수 컴포넌트, 자기 상태는 useThemeMode에서
 * 옴), 옮기는 것 자체가 새 위험 없는 리네임 작업이라 지금은 안 건드린다. */
export function DisplaySettings() {
  return (
    <div className="c-screen">
      <PageHeader area="내 정보" title="내 화면 설정" crumbRoot="" />
      <AccentPicker />
    </div>
  );
}

export default DisplaySettings;
