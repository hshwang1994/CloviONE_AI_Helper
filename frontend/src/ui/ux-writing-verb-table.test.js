/* 화면에 보이는 문구가 표준 동사표를 따르는가 (PA-RC-0002 §3, docs/UX_WRITING.md).
 *
 * 같은 "새로 만든다" 개념에 생성/등록/추가/만들다가 섞여 있었다(원 감사: 생성 84·등록 72·
 * 추가 64·만들 49). docs/UX_WRITING.md §3이 6개 개념 각각의 표준 동사와, 쓰지 않을 동의어를
 * 확정했다. 여기서는 그중 화면 텍스트에서 실제로 관측된 5개 축(생성/등록/만들기 → 추가,
 * 편집/변경 → 수정, 제거/지우기 → 삭제, 끄기/중지/정지 → 비활성화, 켜기 → 활성화)을
 * 소스 전체에서 고정한다 — ux-writing-punctuation.test.js와 같은 관용(jsx-comments.test.js
 * 이후 이 저장소의 표준 패턴): vitest가 렌더링 테스트로 우연히 잡을 때만 걸리는 것을 막기
 * 위해 소스 텍스트를 직접 훑는다.
 *
 * 6번째 축(반영/적용 → 저장)은 일부러 여기 안 걸었다 — 예외가 "폼 저장"이 아닌 별개 개념
 * (설정 즉시반영 화면, 외부 연동 동기화, 필터 범위 설명, 현재 적용 중인 값 표시, 재시작
 * 필요 안내 등)으로 너무 다양해서 규칙만으로 안전하게 자동 검사하기 어렵다고 판단했다 —
 * 억지로 걸면 오탐이 더 많아 이 시험 자체를 못 믿게 된다. 사람이 계속 심사한다.
 *
 * **범위 제한(중요)**: JSX 텍스트 자식(`>...텍스트...<`)만 본다 — `registry/*.js`처럼 문구를
 * 객체 리터럴 속성(`label: "..."`, `help: "..."`)으로 정의하고 다른 컴포넌트가 그 값을 나중에
 * JSX로 렌더링하는 간접 정의는 이 정적 스캔으로 못 잡는다(변수를 따라가려면 데이터 흐름
 * 분석이 필요한데, 정규식 스캔의 범위를 넘는다). 실제로 이 범위를 넓혀 보려다 포기했다 —
 * `registry/authoring.js`·`automation.js`에 "문서 생성"(자동 문서 생성 기능 자체의 고정
 * 이름, 폼으로 레코드를 추가하는 개념과 다르다)이 수십 곳에 정당하게 쓰이고 있어, 허용
 * 목록만으로는 오탐을 안전하게 못 걸렀다. **더 넓은 범위가 필요해지면(예: registry/*.js도
 * 다루고 싶으면) `label:`/`help:`/`title:` 같은 알려진 UI 문구 속성명으로 좁힌 새 규칙을
 * 별도로 만들고, "문서 생성" 계열 예외를 그때 제대로 목록화한다 — 지금 안 억지로 넣는다.
 *
 * 코드 식별자(함수명·변수명·API 필드명)는 대상이 아니다. 아래 allow 는 이미 사람이 검토해
 * "다른 개념이라 대상이 아님"으로 확정한 문구다(UX_WRITING.md §3의 명시된 예외 + 검토
 * 과정에서 확인된 것). 새 예외가 필요하면 여기 먼저 추가하고 이유를 남긴다(§3 "동사표에
 * 없는 개념을 새로 쓸 때" 순서와 같다). */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");

function sourceFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...sourceFiles(full));
    else if ((name.endsWith(".js") || name.endsWith(".jsx")) && !name.includes(".test.")) out.push(full);
  }
  return out;
}

// 주석은 코드가 아니다 — "지우기는 내 말에만" 같은 JSX 주석이 그 자체로 코멘트 안에서
// 금지어를 언급하며 왜 그렇게 안 했는지 설명하는 일이 잦아(이 파일 자체가 그렇듯), 주석을
// 안 지우면 그 설명이 "화면 텍스트"로 오인된다. 완벽한 파서는 아니다(문자열 안의 // 등은
// 못 가린다) — 정적 린트로 충분한 근사치다.
function stripComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

// 개념별 [금지 패턴, 표준 동사, 허용된 예외 문구(부분 문자열)] — 예외는 review로 확정된 것만.
const RULES = [
  {
    concept: "새 항목을 만든다 → 추가",
    banned: /(생성|등록|만들기|만들다)/,
    allow: [
      // AI가 콘텐츠(문제·요약·문서)를 만들어 내는 기능은 전부 같은 계열 — 폼에 값을 채워
      // 레코드를 추가하는 것과 다른 개념이다(AssistantPanel/Games/ProjectWeekly에 흩어져
      // 있지만 전부 "AI가 ~을 생성/만든다"는 같은 도메인 관용). 새 AI 생성 기능 문구가
      // 생기면 여기 먼저 추가한다.
      "AI로 문제 생성", "생성 중…", "주제를 적고 생성하면",     // Games.jsx
      "문장 요약 만들기", "요약 만드는 중",                     // AssistantPanel.jsx
      "AI 요약 생성",                                          // ProjectWeekly.jsx
      "등록된 부서", "등록된 직책", "등록된 조직", // Users.jsx: 목록이 비었다는 상태 서술(초대 CTA 아님)
      "임시 비밀번호는 생성",                   // Users.jsx: "생성 시점"을 가리키는 명사구
      "예: 서버 등록 IP",                       // MyTickets.jsx: placeholder 예시 문장 안의 사용자
                                                 // 입력 예시일 뿐, 앱 자신의 안내 문구가 아니다
    ],
  },
  {
    concept: "이미 있는 값을 고친다 → 수정",
    // "편집" 뒤에 "기"가 오면 동사가 아니라 명사 "편집기"(이 저장소의 JSON/리치텍스트
    // 편집 컴포넌트 고유 이름, EditableBody.jsx·SettingEditor.jsx 등)다 — 부정 전방탐색으로
    // 뺀다. 한글은 ASCII \b 워드 경계가 의미가 없어 이렇게 개별적으로 막는다.
    banned: /(편집(?!기)|변경)/,
    allow: [
      "역할 변경",                              // §3 명시 예외 — 굳어진 개념 명사
      "비밀번호 변경", "시 변경을 요구",          // 업계 표준 고정 용어(§3 "역할 변경"과 같은 부류) +
                                                 // "첫 로그인 시 변경을 요구"(UsersBulk.jsx, 비밀번호
                                                 // 변경 요구를 문맥상 생략한 같은 개념)
      "변경 이력", "변경 기록", "새 변경으로 다시 기록", // 로그/감사·버전 화면의 고정 용어(changelog 류)
      "적용 시점은 항목마다", "이전 변경 이력을 볼", // SettingsMain: 설정 즉시반영 예외 문단 안
      "어떤 변경도 저장되지", "차단된 변경 시도",   // Banners.jsx: 임퍼소네이션 읽기전용 안내 —
                                                 // "변경 일반"을 가리키는 서술이지 특정 버튼이 아니다
      ">변경<",                                // SystemOps.jsx: "변경 작업" 묶음의 구역 제목(카드
                                                 // 헤딩) — 개별 항목을 누르라는 동사가 아니라 그
                                                 // 아래 나열된 액션들을 묶는 범주명이다
      "최근 주요 변경은 대시보드",                // Diagnostics.jsx(PA-RC-0028): Dashboard.jsx의
                                                 // 기존 섹션 제목 "최근 주요 변경"을 그대로 가리켜
                                                 // "그 섹션은 대시보드에서 보라"고 안내하는 문장 —
                                                 // 사용자에게 무언가를 고치라는 동사가 아니라 이미
                                                 // 존재하는 고유명사(섹션 제목)를 인용한 것이다.
    ],
  },
  {
    concept: "목록에서 없앤다(복원 가능) → 삭제",
    banned: /(제거|지우기|지우다)/,
    allow: [
      "필터 지우기", "검색어 지우기", "카테고리 지우기", "검색, 필터 지우기", "검색, 카테고리 지우기",
      // 전부 폼 입력·필터 비우기 — §3 명시 예외("사용자 입력을 지우다")
    ],
  },
  {
    concept: "못 쓰게 막는다(복원 가능) → 비활성화",
    banned: /(끄기|중지|정지)/,
    allow: [],
  },
  {
    concept: "다시 쓰게 한다 → 활성화",
    banned: /(켜기)/,
    allow: [],
  },
];

describe("UX Writing — 표준 동사표 (PA-RC-0002 §3)", () => {
  for (const { concept, banned, allow } of RULES) {
    it(`${concept} — 화면 텍스트에 금지된 동의어가 없다`, () => {
      const violations = [];
      // [^<]{0,120} — 길이를 제한한다(줄바꿈 자체는 허용 — 이 저장소의 흔한 포맷팅은
      // `<Button>\n  {조건 ? a : b}\n</Button>`처럼 여는 태그·내용·닫는 태그가 다른 줄에
      // 있다, 그래서 줄바꿈을 통째로 막으면 진짜 JSX 텍스트를 놓친다). 주석을 먼저 지운
      // 뒤에도 폭을 120자로 막아, JS 비교 연산자(`a > b`)의 `>`가 수백 줄 뒤 무관한 `<`와
      // 짝지어져 그 사이 전체를 "JSX 텍스트"로 오인하던 원래 버그를 막는다 — 진짜
      // 버튼/라벨 텍스트는 120자를 넘지 않는다(UX_WRITING.md §4의 "한 문장 40자"보다 넉넉함).
      const textNode = new RegExp(`>[^<]{0,120}?(${banned.source})[^<]{0,120}?<`, "g");
      for (const file of sourceFiles(SRC)) {
        const text = stripComments(readFileSync(file, "utf8"));
        let m;
        while ((m = textNode.exec(text)) !== null) {
          const snippet = m[0];
          if (allow.some((phrase) => snippet.includes(phrase))) continue;
          const line = text.slice(0, m.index).split("\n").length;
          violations.push(`${file.replace(SRC, "src")}:${line} — ${snippet.trim()}`);
        }
      }
      expect(violations).toEqual([]);
    });
  }
});
