# 랩 ChatGPT 계정 연결 실측 (D-566 — ChatGPT 계정 연결 정식 방식 복귀)

**잰 날**: 2026-10-13 08:11 KST(배포 직후, 로그인 전) · **대상**: `clovirassist.gooddi.lab`(배포 `6b848630`, 스냅샷 `/var/backups/clovirassist/20261013-080213`)
· **하네스**: `python -m scripts.ui_qa.ai_lab_e2e --base https://clovirassist.gooddi.lab --skip-chat --label lab-d566-pre`(QA 계정 비밀번호는 환경 변수로만)
· **결과**: `dist/ui-qa/ai-lab-e2e/lab-d566-pre.{md,json}`.

## 로그인 전 — 배포가 바꾼 것

| 항목 | 결과 | 뜻 |
|---|---|---|
| 제공자 표 | anthropic: `api_key` · openai: `api_key`, **`chatgpt`** (둘 다 ready=false) | D-559 가 숨겼던 ChatGPT 방식이 설치 플래그 없이 표에 선다(D-566). 순서는 API 키 먼저 |
| 저장된 설정 | provider openai · auth_method chatgpt · model gpt-5.5 · generation_enabled true | 이전 회차에 남은 값이 그대로 **유효한 설정**으로 읽힌다(D-559 때는 「이 설치에서는 쓸 수 없습니다」였다) |
| 상태 면 | **미설정** — 「ChatGPT 계정을 아직 연결하지 않았습니다.」, 다음 할 일 `login` | 자격(토큰 묶음)이 없을 뿐이다. 응답에 `chatgpt_allowed` 가 없다 |
| 자격 | `credentials.ready=false, method=chatgpt`, `login_open=false` | 열린 로그인 시도가 없다 — 사용자가 화면에서 시작한다 |
| 모델 목록 · 채팅 | 건너뜀(자격 없음) | 로그인 뒤 같은 하네스가 잰다 |

하네스가 `auth.credentials` · `state` 를 FAIL 로 적은 것은 「자격이 아직 없다」는 판정이지 결함이 아니다 — 로그인 전의 기대 상태다.

## 로그인 전 — 사용자가 「주소를 붙여 넣을 수 없다」고 한 결함 (2026-10-13 09:00 KST 실측, 수정 `670c6058`)

- **랩 기록**(`ai_oauth_transactions`, 서비스 계정 읽기 전용 조회): 사용자(h****g@goodmit.co.kr)의 시도가 10-12 11:43 KST(만료) · 10-13 08:51 · 08:52 · 08:53 KST
  세 번(각각 다음 시도가 앞 것을 닫음 `superseded`, 마지막은 열림). 붙여 넣기 완료 요청은 한 번도 서버에 닿지 않았다(실패 수 0, 오류 코드 없음).
- **재현**(QA 계정, Playwright, ChatGPT 로그인 없이 승인 창만 열고 닫음): Chromium · Firefox 둘 다 시작 직후 붙여 넣기 칸이 **비활성**이고
  「시도가 만료됐습니다. 다시 시작하세요.」가 선다. 서버의 `expires_at` 은 `2026-10-13T00:13:22.230582`(UTC, Z 없음 — `iso_dt` 규약)인데
  `useCountdown` 이 `Date.parse` 로 읽어 브라우저가 **지역 시각**으로 해석했다 → 한국에서는 9시간 일찍 만료 → 칸이 잠기고 「다시 시작」만 보임.
  사용자가 본 것과 같다(세 번 다시 시작, 붙여 넣기 불가). 캡처 `dist/ui-qa-lab/chatgpt-paste/{chromium,firefox}-*.png`.
- **고침**: `ChatGptLogin.jsx::useCountdown` 이 제품의 UTC 파서 `lib/format.js::toUTCDate` 를 쓴다. 같은 뿌리의 결함 하나 더 —
  `profile/MailNotificationCard.jsx` 의 「코드 다시 받기」 대기(`resend_after`)도 지역 시각으로 읽어 한국에서 대기 없이 열렸다 → 같은 파서.
  붙여 넣기는 오류 화면의 글을 통째로 넣어도 그 안의 주소(`http://127.0.0.1:<포트>/auth/callback?…`)를 찾고, 다른 탭에서 돌아오면 칸에 초점을 둔다.
  회귀 시험: `chatgpt-login.test.jsx`(Z 없는 만료 시각 · 글 안의 주소 · `matchAttempt`) · `profile-mail-card.test.jsx`(Z 없는 재발송 시각).
- **고친 뒤 랩**: 배포 `670c6058`(스냅샷 `/var/backups/clovirassist/20261013-091622`) 뒤 같은 대본으로 Chromium · Firefox 둘 다 시작 직후 칸이 **열려 있고** 「남은 시간 9:59 · 10:00」이 보이며(서버 `expires_at` 은 여전히 Z 없는 UTC), 오류 화면 글을 통째로 넣자 그 안의 주소로 완료 요청이 서버에 닿았다(가짜 코드라 `ChatGPT 에서 토큰을 받지 못했습니다` 409 — 실제 교환까지 간 것). 캡처 `dist/ui-qa-lab/chatgpt-paste/*-after-*.png`
- **「오류 페이지 없이 자동으로」는 안 되는 까닭**: OpenAI 가 이 로그인 방식의 콜백을 `http://127.0.0.1:<포트>/auth/callback` 만 허용한다. 그 주소는
  사용자의 PC 안이라 ClovirAssist 서버가 받을 수 없고, 브라우저도 다른 출처 창의 주소를 읽지 못한다. 자동화하려면 PC 에서 그 포트를 듣는 작은
  도우미가 있어야 한다(이전 회차에 걷은 「연결 도우미」와 같은 것 — 사용자 결정 사항).

## 로그인 뒤 — 사용자가 할 일과 그 다음 측정

1. 사용자가 랩 **AI › AI 연결** 화면에서 OpenAI › ChatGPT 계정을 고르고 「Continue with ChatGPT」 → 새 창에서 로그인 · 허용 → 「127.0.0.1 … 연결할 수
   없습니다」 오류 화면의 주소를 복사해 화면의 칸에 붙여 넣는다(D-540 흐름, 설치할 프로그램 없음). 연결되면 모델 목록 → 추천 모델 → 「확인 중」 → 「정상」.
2. 그 뒤 Claude 가 `ai_lab_e2e.py`(채팅 포함)로 인증 · 모델 조회 · 모델 선택 · 일반 대화 · 문서 검색을 각각 따로 재고 이 문서에 표로 적는다.
   OpenAI 가 계정 · 요금제 쪽에서 거절하면(`subscription_sharing_*`) 그 문장이 그대로 측정값이다(D-566 의 한계 ①).

## 로그인 뒤 측정 결과

(아직 없음 — 사용자 로그인 대기)
