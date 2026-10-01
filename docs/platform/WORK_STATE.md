# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## 진행 중 — UI/UX · AI · 조직 · 초기 설정 · 메일 회차 (2026-10-01 ~)

- 계획 정본: `C:/Users/hshwa/.claude/plans/pasted-content-id-c7b8-clovirassist-ui-cheerful-wozniak.md`(사용자 승인, 추가 지시 40개와 마지막 두 보정 반영).
  결정은 D-526 ~ D-555, 마이그레이션은 0042 ~ 0048. 묶음 순서는 그 문서 7절(P0 → P1 ~ P16 → P17 전량 검증 → P17V 최종 시각 수용 → P18 랩 배포와 실측)이다.
- 사용자 지시: 묶음마다 단위 · 통합 · 보안 · 프런트 시험과 관련 화면 스크린샷 확인을 하고, 이미 정한 것은 다시 묻지 않는다. 디자인 품질과 사용성도 완료 조건이다(D-553).
- 끝난 묶음:

| 묶음 | 커밋 | 결정 |
|---|---|---|
| P0 랩 읽기 전용 기준선(`INVENTORY/13_UX_AI_MAIL_BASELINE.md`, `EVIDENCE/mail/2026-10-01-lab-preflight.md`) · `ux-before` 캡처 68장 | `11537fef` | - |
| P1 메일 보안 핵심(`smtp` 시스템 관리자 전용 · 비밀 칸 고정 · 0042 · 설치기 옛 비밀 복사 · 발송 기록 받는 사람 범위 · 0043 · 모든 종류 받는 사람 재검사 · 열람 권한 fail-closed) | `65aec555` | D-545 · D-547 |
| P2 설정 캐시 판 번호(요청 길목 · 워커 잡 직전 · 반복마다, 초당 한 번) | `175cc7cc` | D-532 |
| P3 컨트롤 높이 34 · 30(입력 포함) · `Field` · `FieldRow` · `FormSection` · `HeadRow` · `FlowStack` · 메시지 상자 머리 줄 · 여백 걷기(75 + 38자리) · `Card padding` · 정적 검사 `callout-margin` · `primitive-geometry-override` · 시각 규율 프로브(`visual_probes.py`) · 대조표(`visual_review.py`) | `8320c83e` | D-526 ~ D-528 · D-553 |
| P4 표 열 배분(`columnPlan.planColumns` — 바닥 · 비중 · 상한 · 머리글 · 값 길이, 열 등급 essential · secondary · context, 필수 열만으로 모자라면 가로 굴림 + 붙박이 첫 열, 화면 폭 덮어쓰기 약 50자리를 min · max · 등급 · 값으로) | `361878f0` | D-529 |
| P5 필터 칸 선택지 폭 · 검색 칸 계단 · 「기간」 칸 하나(`PeriodFilter`, KST) · 보기 기준(`role: "view"`) · 켬/끔 조건 자리 · 목록 상태 일곱 갈래(`resolveListState` · `ListStateView`) · 빈 표의 머리 아래 띠 · 상태 자리(`StateRegion`) · 기능 깃발 문 `feature_disabled` · 정합성 짧은 이름 · P4 값 길이 결함(id) 수정 | `b22fe969` | D-530 |
| P6 채움 모드(`ui/Workspace.jsx` — 고른 화면이 등록하고 창 1200 · 600 이상이면 main 이 창 높이, 판마다 몸만 굴러감) · `DataTable fill` · 스크롤 창 문맥(`scrollRoot.js`) · 견본 `#/kit/workspace` · 실브라우저 `workspace_e2e.py`(34/34 + 반례) | `4096e98a` | D-531 |
| P7 조직 관리 작업 공간(트리 모델 · 판 머리 동작 · 까닭 붙은 비활성 메뉴 · 「상세 정보」 창 · `/impact` 영향 창 · 회차 막음과 떼어 냄 · 「개」 단위와 조사 · 조직 인원은 쓸 수 있는 계정 · 부서 구성원 기본 하위 포함 · 표 채움은 채움 작업 공간에서만) · 큰 조직 시드 · `workspace_e2e --target org` · `hostile_data --modes tree` | 이 커밋 | D-533 |

- P3 ~ P6 묶음 끝 `verify.py --full`(HEAD `4096e98a`, 2026-10-01 21:49 ~ 23:11): 정적 전량 · 백엔드 단위 · 회귀 · 보안 · 통합 네 청크 통과, 프런트 전량 4,100 / 4,102. 남은 둘(`home.test.jsx` · `projects.test.jsx` 각 1건)은 메모리 여유 약 1GB 에서 20초 시간 초과였고 단독 재실행 86 / 86 통과다.
- P7 실측: `workspace_e2e --target org`(큰 조직 시드) 46 / 46 · 견본 34 / 34 · 반례 시험 통과, 캡처 `dist/ui-qa/p7-org` · `dist/ui-qa/org-workspace-e2e`(1366 · 1920 을 눈으로 봤다).
- 다음: P8 AI 검색 낱말 · 어댑터 `converse`(A1 의 검색 개선과 제공자 계약, 아직 제품에 배선하지 않는다, D-536).

## 끝남 — 공통 스위치 개편 (2026-10-01)

- 계획 정본: `C:/Users/hshwa/.claude/plans/pasted-content-id-8fa2-clovirassist-buzzing-parrot.md`(사용자 승인, 2차 수정 셋 반영). 결정은 **D-525**.
- 한 일: 공통 `MuiSwitch` 한 곳(`theme.js::SWITCH` + override)에서 트랙 38×22 · 원형 손잡이 16 · 여백 3 · 누르는 자리 50×44(배치 높이 34) ·
  전부 rem · 완전한 알약, 꺼짐 선과 점 · 켜짐 강조색 · 강조색을 뺀 비활성 짝 · 트랙의 초점 링, halo · 물결 · 그림자 제거. 저장 중 비활성을 걷는
  즉시 저장 훅(`lib/useInstantSave.js`)을 내 프로필 · 메일 · AI 설정에 붙였고, `SettingRow controlId` 로 이름을 라벨로 이었다. 화면별 스위치
  CSS 덮기는 0건 그대로다. `local_capture` 가 하네스 모드에서 `--fail-on` 을 버리던 것도 고쳤다.
- 잰 것: 표적 vitest · `verify.py` TARGETED_OK, `kit_measure --fail-on switch_geometry` 282표본 0실패(옛 빌드 270표본 전부 실패),
  `switch_states` 174/174(같은 하네스로 옛 빌드를 임시 worktree 에서 돌리면 라벨 · 가장자리 클릭 · 초점 링 · 저장 판정이 실패한다).
  캡처 라벨은 `switch-before` · `switch-after` 이고 Acceptance 정본을 옮기지 않는다.
- 배포: `5aadfbb6` 를 랩 운영 설치에 올렸다(아래 CHECKPOINT). DEPLOY_VERIFY_OK.
- 남은 일: 범위 밖으로 넘긴 넷이 BACKLOG P-117 ~ P-120 이다(방해금지 이름, AI 답변 생성 초안 스위치, 초점 프로브, 고대비).

## 끝남 — 관리자 · 사용자 화면 전반 개선 회차 (2026-09-30, 사람의 자격이 필요한 측정만 남았다)

- 계획 정본: `C:/Users/hshwa/.claude/plans/pasted-content-id-c5c6-clovirassist-vivid-flask.md`(사용자 승인, 2차 보완 반영).
  구현 순서는 그 문서 §5 다(F 기반 → B 버그 → U 화면 → M 메일 → A AI → I 설치). 결정은 D-503 부터.
- 사용자 지시: auto 모드로 계획 전체를 구현하고 Packet 마다 표적 검증과 회귀를 돈 뒤, 끝에 E2E 와 최종 검증을 한다.
- 끝난 Packet:

| Packet | 커밋 | 결정 |
|---|---|---|
| F1 비밀 입력 경로(헬퍼 secret.write, /api/admin/secrets, SecretField) | `5deb94ef` | D-503 |
| B1 + F2 프로젝트 진행률 · Health(커밋 직전 계산, 0031, 휴지통 공용 절) | `5f15c465` | D-504 |
| B2 월간 리포트(사람 id, 일곱 칸, 완료일 축, 0032) | `dfb85ec7` | D-505 |
| F3 공통 UI 규칙(의미 기반 정렬, 조건 요약 문장, 저장된 뷰 기준) | `dff6b097` | D-506 |
| F4 AI 기능 플래그 셋 DB 소유 | `6147a0b9` | D-507 |
| U1 + B3 조직 정합성(탭 · 전량 목록 · 일괄 작업, 0033, 원인 차단) | `e61bb841` | D-508 |
| B4 메일 큐(재시도 상태와 종류별 일정, 영구 실패 분류, 취소 · 다시 보내기, 0034, 시험 메일 거짓 실패) | `5078693f` | D-509 |
| U2 조직 관리(사용자 목록 조건 넷, 구성원 페이지 목록, 트리 수 정의, 머리 동작) | `7b87cd20` | D-510 |
| M1 메일 전송 강화(인증서 확인 · 사설 CA, 메일 머리, 비밀번호 슬롯, 보내지 않는 연결 확인) | `4ee79d61` | D-511 |
| M2 메일 건강 상태 · 연결 확인 잡 · 복구 재큐 · 발송 직전 유효성 · 발송 기록 탭 · CSV 초대 | `a384e7fb` | D-512 |
| M3 티켓 요청자(0035) · 상태 알림 한 곳 · 요청자 결과 알림 · 위임 알림 목적지 | `0a952ce9` | D-513 |
| M4 알림 메일 채널(0036, 허용 목록, 켜기와 유형 고르기, 받는 사람과 사건의 발송 직전 재검사) | `19b6389c` | D-514 |
| A1 AI 런타임 하나 · Anthropic API 키 · 여섯 연결 상태 · 관리 API · AI 설정 화면 · 0037 | `6387d854` | D-515 |
| A2 OpenAI(API 키 · ChatGPT 계정 연결 도우미) · 토큰 수명과 갱신 · 주기 확인 · 바깥 프록시 · 0038 | `5a21a7ff` | D-516 |
| A4 AI 호출 기록(0039) · 한도의 원장 이전과 퀴즈 · 주간 요약 포함 · 「AI 사용 한도」 · 사용 통계와 호출 기록 탭 | `07fabdd6` | D-517 |
| A5 프롬프트 사용처(0040) · 런타임이 발행본을 다음 호출부터 씀 · 고정된 안전 틀과 출력 형식 · 생명주기 셋 · 기본 제공 행 | `6c487dca` | D-518 |
| A6 AI 정책 종류와 적용할 기능(0041) · 호출마다 적용(가리기 · 응답 제한) · AI 초안의 쓰기 승인 · 옛 정책 옮기기 | `5ec538c1` | D-519 |
| U3 초기 설정 필수 · 선택과 「사용하지 않음」 · 메일과 AI 는 저장된 확인 결과 · 서버 링크 · 판 폭 상한 폐지 | `1e589389` | D-520 |
| U4 AI 화면 문구를 시험으로 고정 · 네 AI 화면의 저장된 뷰 없음(호출 기록은 D-506 기준) | `9533667b` | D-521 |
| I1 Release 설치(받아서 확인한 뒤 풀기) · 24.04 만 · 첫 관리자 설정 코드와 /setup/first-admin · clovirassist 명령 · 허용 목록 병합 · 옛 LLM 키 정리 · 모델 받기 | `1e246db9` | D-522 |
| I2 README · INSTALLATION 공개 기준 재작성 · 문서 대조 검사 · Release 자산 빌드 · 번들 목록 확인 · 설치처 값(Confluence 사이트 등) 걷기 | `f1feedc6` | D-523 |
| 번들 재빌드(화면 Packet 이 모인 뒤 한 번) | `56637a79` | - |
| I3 Release 리허설(LXD 24.04, 39항목) · 되돌리기가 sysops/ 를 고르던 결함 · 연결 확인이 낡은 설정 캐시를 읽던 결함 | `6fab9a77` | D-524 |
| 최종 캡처와 리허설이 찾은 어긋남(웹 프로세스 캐시, 사용 한도 칸, 정책 종류 칸, 메일 설명) · 번들 | `a4bcad38` | D-524 |
| 전량 회귀가 잡은 감사 대상 선택지 누락(`setup`) · 번들 · 회차 마감 문서 | 이 커밋 | D-524 |

- 남은 일(사람이 할 것): BACKLOG P-116 - 실제 Anthropic · OpenAI 키로 연결 확인과 채팅 한 번, 실제 ChatGPT 계정으로 연결
  도우미 → 승인 → 연결됨과 토큰 만료 시각, 공개 저장소에 Release 를 올린 뒤 GitHub 에서 받아 설치. 랩 운영 설치에는 `7bf15f4d` 를
  배포했다(아래 CHECKPOINT). 랩의 AI 를 쓰려면 AI 설정 화면에서 키와 모델을 넣고 연결 확인을 누른다. 다음 Acceptance 회차는 P-115 부터다.
  ChatGPT 요금제 연결은 그 계정 한 명의 사용량이라, 여러 사람이 쓰는 설치는 조직 API 키를 권한다(INSTALLATION §12. 화면에는 아직 그 문장이 없다).
  계획의 A3(AI 설정 화면)는 A1(Anthropic)과 A2(OpenAI, ChatGPT 계정 연결)가 나눠 맡아 끝났다(D-515 · D-516).
- 전량 회귀(`verify.py --full`, 마지막 커밋 `a4bcad38`): 정적 전량 통과(번들 신선도 포함), 백엔드 unit · regression · security · integration 4묶음 전부 통과, vitest 465파일 중 464파일(3,936/3,937건) 통과. 남은 1건은 I1 이 더한 감사 대상 `setup` 이 감사 로그 대상 필터 선택지에 없던 것이라 다음 커밋이 고쳤고, 그 파일과 같은 선택지를 쓰는 22파일(189건)을 다시 돌려 통과했다.
- Release 리허설(`scripts/release_rehearsal.sh`, 랩 LXD): 네 번째 실행 39/39 통과(`v0.1.0-rc.5` → `rc.6`, 5분). 개발자 경로
  리허설(`scripts/lxd_rehearsal.sh`)도 35/35 통과했다(`a4bcad38`). 최종 캡처
  `dist/ui-qa/admin-round-final`(19화면 × 1200 · 1366 · 1600 · 1920, 밝은 테마)의 프로브 표시는 스크린샷으로 확인했다 - 짧은
  목록 아래 빈 자리, 고정 선택지 드롭다운, 옆 카드 높이에 맞춘 판은 위양성이고, 잘리던 두 칸은 고쳤다.

## CHECKPOINT

- checkpoint_at: **2026-09-21** (제품 일관성 회차 — 사용자가 짚은 여덟 가지를 **사례**로 보고 공통 원인 다섯을 공통 계층에서 고쳤다:
  문자열 검색 접기 · 필터 칸 크기 · 작업 보드 상단과 백로그 머리 · 재진입과 중복 요청과 오류 그림 · 관리자 화면의 정보 구조.
  D-495 ~ D-502)
- phase: **F — Acceptance 완료(S22) 뒤의 일반 개발**(CLAUDE.md §7.0)
- session: 사용자가 여덟 가지를 auto 모드로 끝까지 지시했고(구현 → 표적 검증 → 문서 → 커밋), 검증이 끝난 뒤 **배포까지** 지시했다.
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — 이번 회차도 안 옮긴다.
- deployed: **`5aadfbb6`** (2026-10-01 14:58 KST, 사용자 지시로 공통 스위치 개편을 올렸다) — 마이그레이션 없음(`0041_ai_policies`
  그대로), Stage 0 ~ 18 전부 OK, VERIFY_OK, 밖에서 본 `verify_deploy.sh` DEPLOY_VERIFY_OK(정적 자산 54/54 새 번들). 스냅샷
  `/var/backups/clovirassist/20261001-145850`, 설치 로그 `/var/log/clovirassist/install-20261001-145850.log`. 되돌리려면
  `sudo clovirassist rollback`(D-524). 원격 QA 계정(`dist/ui-qa-remote`)이 랩에서 보관 상태라 원격 `switch_geometry` 는 재지 못했다 —
  같은 번들을 로컬에서 282표본 0실패로 쟀다. 그 전 배포는 `7bf15f4d`(2026-10-01 09:57, 관리자 화면 개선 회차 — 그 배포가 옮긴 AI
  설정 · 정책 초안의 상태는 위 그 회차 절이 말한다).
- verification: 아래 「이번 회차가 잰 것」.
- capture: 전량 정본은 **`s22-final`** 그대로다(D-306). 이번 회차의 부분 캡처는 `p8-admin` · `p8-admin2` · `p8-user` · `p8-recheck` ·
  `p8-org2` · `p8-mystats` 이고 Acceptance 정본을 옮기지 않는다. 뼈대 기준 라벨은 **`p8-geo`** 다 — 작업 보드는 D-497 이 상단을
  바꿨으므로 그 라벨이 새 기준이다.
- ui_gate: 변화 없음.

## 무엇을 바꿨나

### 제품 일관성 회차 — 공통 원인 다섯 (D-495 ~ D-502)

| 묶음 | 커밋 | 무엇 |
|---|---|---|
| P0 | `edc9f71f` | 재현 하네스 먼저 — 같은 메뉴 두 번 누르기(`reactivate_e2e`, 두 브라우저 × 두 폭 × 여덟 모드). 옛 빌드 1,984 실행에서 폴백 42건과 스택을 잡았다 |
| P1 | `cf97b18b` · `b2b6968f` | 검색 접기 규칙 하나 — 프런트 아홉 자리 · 백엔드 열두 자리, `search_fold()` 와 생성 열(`0030`) |
| P2 | `d337fc30` | 필터 칸 폭 = 종류 + 크기(wide 칸의 세 계단) |
| P3 | `1e37b8c6` · `73b610a4` | 작업 보드 상단 두 줄 · 백로그 머리 필터와 정렬 · 서버 `BoardFilters` 하나 |
| P4 | `ac0bde51` · `47cc6b33` · `eb0a5b1c` · `2bd93ca5` · `675c3382` · `43849750` · `9f572f9f` · `e3952bd9` · `e74b23b3` · `56796fbe` | 재진입 = 새 진입 · 포인터 아래 불변 · 「500」 그림은 진짜 5xx 에만 · 로그의 진짜 500 둘 · 중복 제출 · 경합 |
| P5 | `3f94a1f2` | 채팅방 참여자 명단 팝오버(요약 단추 · 얼굴 스택) |
| P6 | `30b64356` | 조직 관리 IA — 같은 수는 한 곳, 동작은 고른 대상 옆 |
| P7 | `6a490edf` · `fdd32629` | 관리자 화면 — 공통 계층 일곱과 전용 화면 아홉 |
| P8 | `4f794649` · `9d407895` · `db06c713` · `ac45f480` · `c16329b7` · `9d6005c7` · `77ee2f8b` · 이 커밋 | 결정 · 대장 · 백로그 · 번들 · 프로브 위양성 다섯 · 전량 회귀 · 배포 |

결정 정본은 `docs/DECISIONS.md` D-495 ~ D-502, 부품 계약은 `docs/ui-renewal/COMPONENT_LEDGER.md`(§0-9 · §0-10 · §0-11 · §0-18 · §1)다.

## 이번 회차가 잰 것

- **정적 전량** `STATIC_CHECKS_OK` — 번들 신선도(`BUNDLE_FRESH_OK`, 272 입력) · `COMPOSITION_OK`(소스 8규칙, `primary-last` 신설) ·
  `COLUMN_TYPES_OK` · `KIT_CONSUMERS_OK` · `TEST_STRENGTH_OK` · `PROBE_SELFTEST_OK`(로직 27) · `UI_RENEWAL_COVERAGE_OK`.
- **백엔드 전량** `FULL_REGRESSION_OK` — unit · regression · security · integration 4청크(49 · 49 · 49 · 46 파일), 53분 54초.
- **vitest 전량** 457 파일 / 3,887 시험 통과.
- **재진입 하네스(최종 번들)** `REACTIVATE_E2E OK` — Chromium · Firefox × 사용자 · 관리자 콘솔 × 1920 · 1366 × 여덟 모드 **1,936 실행
  실패 0**(폴백 0 · 페이지 예외 0 · 5xx 0 · 포인터 밀림 0 · 두 번 누른 끝 상태 ≠ 한 번 누른 끝 상태 0). 옛 빌드 1,984 실행에서는
  폴백 42건이었고 전부 `/work-board` 의 `null.draggable` 이었다(두 브라우저 · 두 폭).
- **흐름 · 조합** `FILTER_E2E_OK`(면 50 · 흐름 1 — 지난 회차 32 면에서 늘었다) · `KIT_MEASURE_OK` · `COMPOSITION_STATES_OK`(28 상태 ·
  실패 0 · 못 만든 상태 0, 새 상태 「채팅방 참여자 명단 열림」 포함).
- **부분 캡처**(관리자 14 + 사용자 8 route × 1920 · 1600 · 1366, 일부 다크): 가로 넘침 0 · 내용 잘림 0 · 콘솔 오류 0 · 페이지 오류 0 ·
  깨진 그림 0 · 중복 id 0. 눈으로 확인한 것 — 작업 보드 필터가 1920 · 1600 에서 **한 줄**, 백로그 머리에 정렬 화살표와 필터 깔때기,
  조직 관리에서 같은 수가 한 번만, 초기 설정의 「지금 할 차례」 레일, 메일 발송의 「메일 설정 열기」와 비활성 시험 메일.
- **뼈대 비교** `compose-final3-geo` → `p8-geo`: 홈 · 내 프로필 · 스프린트 회의는 **날짜 낱말만** 다르다(캡처 시각 — 구조 · 열 비율 ·
  차트 불변). 작업 보드는 의도한 변경이다(필터 줄 2 → 1 at 1920, 「필터 초기화」가 사라지고 「검색어」 · 「보기 옵션」이 생겼다).
  내 업무량은 표 열 비율이 바뀌었다 — D-501 ⑤ 의 결과로 「달」 열이 1920 에서 39.3% 를 먹던 것이 사라졌다.
- **프로브 위양성 다섯**을 반례와 함께 고쳤다(`probe_selftest` 90 사례): 보이는 순서로 본문 · 곁열 짝짓기 · 한 칸 격자의 쌓임 ·
  `.sr-only` 줄 수 · 글자 그대로인 단추 · 메뉴를 여는 「더 보기」. 다섯 다 known good/known bad 로 확인했다.
- **면제 없는 검증**(§9.3) 중 해당분: 권한 음성(검색 범위 · AI 검색 권한 · 조직 `can_edit` · 작업 보드 모르는 담당자) ·
  마이그레이션 무결성(`0030` 왕복 + 제품 옵션 그대로의 pg_dump → pg_restore) · 동시성(회차 만들기 · 열기 · 지켜보기 · 관계 잇기).
- **배포와 배포 후 검증**(커밋 `1e87ec86` → `9a0f578c` → `f0232c51`, 세 번) — `git archive` → scp → `install.sh upgrade --source local --yes`(sudo 비밀번호는 stdin).
  `STAGE_9_MIGRATION: OK 0029_sprint_team_owner → 0030_search_fold · public 표 96개` · 설치기 `VERIFY_OK`(유닛 7 active/enabled ·
  TLS 만료 2027-08-21 · alembic head 코드와 일치 · `vector` · `pg_trgm` 확장) · `UPGRADE_OK`.
  `scripts/verify_deploy.sh` → `DEPLOY_VERIFY_OK`(healthz · readyz 200 · 로그인 화면 제품명 · **정적 자산 51/51 새 번들** ·
  새 라우트 401 · 새 CSP). 이 PC 에서 TLS 로 찌른 값: `/healthz` · `/readyz` 200, `/api/admin/organizations` 401, 해시 주소 303.
  배포 뒤 12분 로그에 5xx **0건** · Traceback 0 · nginx 오류 로그 0.
  설치처 DB 실측: `search_fold('ClovirONE  현황 제외')` → `clovirone현황제외`, 생성 열 3개, fold 인덱스 12개.
  **못 한 것** — 로그인이 필요한 원격 캡처. 설치처의 QA 계정이 보관 상태라 되살리려면 비밀번호를 정해야 해서 하지 않았다
  (`~/qa-user-cli.sh unarchive` → `passwd` 는 사람이 돌린다).

## 이번 회차가 **안 고친** 것 — 그리고 그 이유

- **권고 `brand_presence`** — 읽기 전용 관리자 화면(개발자 리포트 · 메일 발송 · 작업 큐 · 정합성 · 권한 매트릭스)은 브랜드 자리가 3/7 이다.
  개발자 리포트는 합계 카드를 다시 그리던 도넛을 걷어 자리가 하나 줄었다. 제품의 브랜드 면은 머리 · 사이드바 활성 · 내 말풍선이라는
  판단은 그대로다(D-491). Acceptance 회차가 다시 잰다(BACKLOG P-103).
- **권고 `dead_blank_region`** — 조직 관리(1600) · 메일 발송 · 직책 관리는 내용이 짧아 아래가 빈다. 중복을 걷어 낸 결과라 되돌리지 않는다.
  판을 화면 높이까지 늘리는 것은 C-5 가 정한 자리(새 티켓 · 채팅방)만이다.
- **스프린트 회의 캡션 대비 4.45**(「15」, 기준 4.5) — 지난 회차 캡처에도 있던 것이고 이번 변경이 만든 것이 아니다. 문구 · 토큰 결정이
  먼저라 BACKLOG 로 돌렸다(P-107).
- **nginx 앞단 프록시 목록은 비워 두었다** — `realip.conf` 배선만 올라갔고 값이 없어 동작은 지금과 같다(D-499). 실제 사용자 주소로
  속도 제한을 걸려면 `install.sh upgrade --upstream-proxy <프록시 CIDR>` 로 목록을 채우는 운영 결정이 필요하다.
- **작업 보드 백로그의 정렬 중 쪽 넘김** · **대화 검색이 지운 메시지도 찾는다** · **우선순위 어휘 갈림** · **동시성 잔여 셋** —
  각각 결정이 먼저라 BACKLOG 로 돌렸다(P-98 ~ P-101).
- **오프보딩의 목록 상태 밖** — 이번에 **안 봤다**. 「안 봤다」와 「없다」는 다른 사실이다(D-501).

## 🔴 운영이 PostgreSQL 위에서 돈다

`10.100.64.71` 의 `/healthz` 가 `{"status":"ok","ticket_source":"native"}` 로 답한다.
원장은 [`EVIDENCE/S14/`](EVIDENCE/S14/README.md).

## 완료

- **S0~S22** — 기반 · PostgreSQL · Identity/TLS · 설치 자동화 · RBAC · Work · Knowledge ·
  Storage · AI 1·2 · n8n 제거 · Backup/Restore · Migration · Cutover · Functional E2E ·
  Final Audit. 결정 D-187~D-334.
- **화면 고도화 · 대시보드 · 무한 스크롤 · 서버 필터/정렬 · 티켓 만들기 · 신호 축 ·
  3영역 재설계 · 카테고리 · 엑셀** ✅ — D-335~D-406.
- **작업 보드·스프린트 회의·문서 결함 전수 수정 + 429 근본 해소 ✅** — D-407~D-412.
- **3라운드 운영 실화면 재검수 ✅** — D-413~D-415. 배포 `c3c2e195`.
- **문서 기능 개편 + 외부 문서 정상화 ✅** — D-416~D-443. 배포 `ec9b8aca`.
- **휴지통 정상화 + 공유 링크 ✅** — D-444~D-451. 배포 `e6df9272`.
- **관리자 화면 전수 UI/UX 정리 + 내 프로필 ✅** — D-452~D-458.
- **관리자 기능 전수 검증·수정 ✅** — D-459~D-472. 배포 `15e2335e`.
- **작업 보드·스프린트 회의를 팀 회차 위에 재설계 ✅** — D-482~D-484. 배포 `2c8915e5`.
- **디자인 핸드오프 A~G · UI 3차 조합 계약 ✅** — D-485~D-494. 배포 `3dfc8ef7`.
- **제품 일관성 회차(검색 · 필터 · 작업 보드 · 재진입 · 채팅 명단 · 조직 관리 · 관리자 화면) ✅** — D-495~D-502. 배포 `f0232c51`.

## BLOCKERS

- 없음.

## 다음 시작점

1. 되돌려야 하면 두 길이다: `bash scripts/deploy-upgrade.sh 3dfc8ef7`(코드만 — `0030` 마이그레이션은 `downgrade()` 가 정확히 되돌리므로
   필요하면 `alembic downgrade 0029` 를 함께 돌린다) · 서버에서 `sudo bash /opt/clovirassist/deploy/install.sh rollback --target <스냅샷>`.
2. 속도 제한을 실제 사용자 주소로 걸 것인지 정한다(D-499 — `--upstream-proxy`). 지금은 배선만 있고 동작은 예전과 같다.
3. BACKLOG P-97 ~ P-107 — 이 회차가 범위 밖으로 돌린 발견들이다.
4. 다음 릴리스에 P-94(`0031`, `sprints.project_id` 삭제).
