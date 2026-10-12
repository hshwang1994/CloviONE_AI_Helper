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

## 로그인 뒤 — 사용자가 할 일과 그 다음 측정

1. 사용자가 랩 **AI › AI 연결** 화면에서 OpenAI › ChatGPT 계정을 고르고 「Continue with ChatGPT」 → 새 창에서 로그인 · 허용 → 「127.0.0.1 … 연결할 수
   없습니다」 오류 화면의 주소를 복사해 화면의 칸에 붙여 넣는다(D-540 흐름, 설치할 프로그램 없음). 연결되면 모델 목록 → 추천 모델 → 「확인 중」 → 「정상」.
2. 그 뒤 Claude 가 `ai_lab_e2e.py`(채팅 포함)로 인증 · 모델 조회 · 모델 선택 · 일반 대화 · 문서 검색을 각각 따로 재고 이 문서에 표로 적는다.
   OpenAI 가 계정 · 요금제 쪽에서 거절하면(`subscription_sharing_*`) 그 문장이 그대로 측정값이다(D-566 의 한계 ①).

## 로그인 뒤 측정 결과

(아직 없음 — 사용자 로그인 대기)
