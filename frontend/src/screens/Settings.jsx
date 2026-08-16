/* 설정 화면 — 실제 구현은 ./settings/ 아래로 나뉘어 있다(파일당 800줄 상한 + 응집도).
 * 이 파일은 기존 경로("./Settings.jsx")를 그대로 쓰는 다른 화면(Ops.jsx의 유지보수 화면)과
 * 테스트(settings-*.test.jsx)를 깨지 않기 위한 재노출 지점이다.
 *
 * 분리 지도:
 *   settings/settingsRegistry.js    라벨·스키마 도움말·역할 목록·순수 판정 함수(JSX 없음)
 *   settings/AccentPicker.jsx        화면 강조색(개인 설정, 서버 저장 아님)
 *   settings/StructuredObjectFields.jsx  설정 카테고리별(비밀번호/세션/도메인/브랜딩) 구조화 입력
 *   settings/SettingEditor.jsx       값 편집 드로어(coerce/dry-run/저장/보안 완화 확인)
 *   settings/SettingVersions.jsx     버전 기록 + 롤백
 *   settings/SettingsMain.jsx        설정 표 화면(Settings 컴포넌트) 본체
 *   settings/SettingsShell.jsx       PA-RC-0017: /settings 라우트가 실제로 그리는 탭 그릇
 *                                    (시스템 정책=Settings+Maintenance / OS와 서비스 동작 /
 *                                    연동 / AI). Settings 자체는 여전히 "설정 표"만이다 —
 *                                    AdminRoutes.jsx는 SettingsShell을 렌더한다. */
export { Settings } from "./settings/SettingsMain.jsx";
export { SettingsShell } from "./settings/SettingsShell.jsx";
export { SettingVersions } from "./settings/SettingVersions.jsx";
export { fmtDuration, summarizeSetting, SETTING_LABELS, OBJECT_SCHEMA_HELP } from "./settings/settingsRegistry.js";
