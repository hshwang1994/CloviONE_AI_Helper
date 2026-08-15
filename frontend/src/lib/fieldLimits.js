/* 관리자 폼 maxLength 조회 (PA-RC-0005).
 *
 * 값은 손으로 옮기지 않는다 — scripts/generate_field_limits.py가 백엔드 Pydantic 스키마의
 * max_length를 그대로 읽어 frontend/src/generated/fieldLimits.json으로 내보내고, 여기서는
 * 그 JSON을 화면 키(registry의 config.key)·폼 종류(create/edit)·필드 이름으로 조회만 한다.
 * scripts/check_field_limits_fresh.py(static_checks.sh)가 이 파일이 스키마와 어긋나면 잡는다.
 */
import LIMITS from "../generated/fieldLimits.json";

export const maxLengthFor = (screenKey, formKind, fieldName) => {
  const forScreen = LIMITS[screenKey];
  const forForm = forScreen ? forScreen[formKind] : null;
  const v = forForm ? forForm[fieldName] : null;
  return typeof v === "number" ? v : null;
};
