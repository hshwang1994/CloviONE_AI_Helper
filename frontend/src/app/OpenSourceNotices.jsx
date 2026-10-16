import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { Modal, ModalFooter, Tag } from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";

/* 오픈소스 고지 (D-579) — 제품에 들어간 바깥 코드 · 자료의 출처와 라이선스를 앱 안에서 보는 한 자리.
 *
 * 예전에는 구슬 레이스 판 옆의 [정보] 단추가 출처를 말했다 — 한 게임의 판에만 있었고, 고지가 필요한 다른 것(물리 엔진 · 결정적 수학 ·
 * 기본 아바타)은 앱 어디에도 없었다. 이제 사용자 메뉴의 「오픈소스 고지」가 모두를 한 목록으로 보인다. 정본 문서는
 * `docs/THIRD_PARTY_NOTICES.md` 이고, 그 문서의 `## ` 머리마다 여기 항목이 하나 있어야 한다(`open-source-notices.test.jsx` 가 대조한다).
 * 라이선스 전문은 그 문서와 `screens/game-room/marble/ATTRIBUTION.md` 에 있다. */

export const NOTICES = [
  {
    key: "marble-roulette",
    doc: "구슬 레이스",
    name: "Marble Roulette (lazygyu)",
    license: "MIT",
    url: "https://github.com/lazygyu/roulette",
    text: "구슬 레이스는 lazygyu의 Marble Roulette의 물리 규칙, 맵 자료, 순위 계산을 바탕으로 만들었습니다. 「Marble Roulette」와 「마블 룰렛」은 lazygyu의 상표이고, 이 제품은 그 이름을 쓰지 않고 「구슬 레이스」라고 부릅니다.",
  },
  {
    key: "planck",
    doc: "planck",
    name: "planck",
    license: "MIT",
    url: "https://github.com/piqnt/planck.js",
    text: "구슬 레이스의 물리 엔진은 Box2D를 JavaScript로 옮긴 planck입니다.",
  },
  {
    key: "fdlibm",
    doc: "fdlibm",
    name: "fdlibm (Sun Microsystems)",
    license: "자유 배포 고지",
    url: "https://www.netlib.org/fdlibm/",
    text: "구슬 레이스가 모든 브라우저에서 같은 경주를 계산하도록 sin, cos, atan2를 fdlibm 알고리즘으로 옮겨 씁니다.",
  },
  {
    key: "dicebear",
    doc: "DiceBear",
    name: "DiceBear",
    license: "CC0 1.0",
    url: "https://www.dicebear.com",
    text: "사진이 없는 사람의 기본 얼굴은 DiceBear의 CC0 스타일로 브라우저 안에서 그립니다.",
  },
];

export function OpenSourceNoticesModal({ open, onClose }) {
  return (
    <Modal open={open} onClose={onClose} title="오픈소스 고지" size="md" footer={<ModalFooter onCancel={onClose} cancelLabel="닫기" />}>
      <Box sx={{ display: "grid", gap: 2 }}>
        <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
          이 제품에 포함된 외부 코드와 자료의 출처입니다. 라이선스 전문은 설치본의 문서에 함께 들어 있습니다.
        </Typography>
        <Box component="ul" data-oss-notices="" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1.75 }}>
          {NOTICES.map((n) => (
            <Box component="li" key={n.key} data-oss-notice={n.key} sx={{ display: "grid", gap: 0.5, minWidth: 0 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
                <Typography component="h3" sx={{ fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.bold }}>{n.name}</Typography>
                <Tag label={n.license} />
              </Box>
              <Typography variant="body2" sx={KO_WORD_BREAK}>{n.text}</Typography>
              <Link href={n.url} target="_blank" rel="noreferrer noopener" variant="body2" sx={{ width: "fit-content", wordBreak: "break-all" }}>{n.url}</Link>
            </Box>
          ))}
        </Box>
      </Box>
    </Modal>
  );
}
