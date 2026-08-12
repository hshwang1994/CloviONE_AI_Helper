# 자율 완성 Runner — 세션이 끝나도 이어지는 로컬 CONTINUOUS 워커 (Primary Supervisor)

> **2026-08-11 (D-61, D-60 정정) 갱신**: 이 로컬 Runner가 **1차(Primary) 연속 실행
> 메커니즘**이다. 하네스 내장 `/loop` dynamic mode + `ScheduleWakeup`은 지금 열려 있는
> 대화형 세션 안에서 부가적으로만 쓰는 session-local 보조 기능이지, 그 자체가 project
> continuity의 근거가 아니다(D-60이 한 번 반대로 정했다가 D-61이 사용자 지시로 뒤집었다) —
> 상세·controlled test 증거는 `docs/DECISIONS.md` D-61, 그리고 **D-64**(Stop hook 보조 제동 +
> Supervisor 계약 정정). Windows Task Scheduler에는 의존하지 않는다 — 새 항목을 만들지 않고,
> 기존 것을 삭제하는 것도 사용자 몫이다. 대화형 세션이 저장소를 수정하는 동안은 이 Runner를
> 켜지 않는다(동시 수정 방지 — `run.lock` 배타 핸들이 두 Supervisor는 막지만, 사람의 대화형
> 세션까지 막아 주지는 않는다). **대화형 세션이 끝나면 사용자가 아래 한 줄로 이 Runner를
> 시작하는 것이 연속성의 주 경로다.**

Claude Code 세션(터미널 창)을 닫아도, ClovirONE Web Assistant 프로젝트가 완료되지 않았다면
이 컴퓨터에서 `autonomous_runner.ps1`이 **쉬지 않고 반복**해서 Claude Code를 이어 띄운다 —
한 반복이 끝나면 성공이든 실패든 곧장 다음 반복이 시작된다. Windows 작업 스케줄러는 "언제
일할지"를 정하는 페이서가 아니라, 이 루프가 죽어 있을 때만 되살리는 **감시자**다.

## 왜 클라우드 스케줄(`/schedule`)이 아니라 로컬인가

`/schedule`(RemoteTrigger)로 만드는 클라우드 루틴은 Anthropic 클라우드의 격리된 샌드박스에서
GitHub 저장소를 새로 clone해 돈다 — 이 컴퓨터의 로컬 파일도, 사내망 안의 `10.100.64.71`도
접근할 수 없다. 게다가 이 저장소의 `origin`(GitHub)에는 "secrets excluded" 라는 압축된 커밋
하나만 올라가 있고, `ui/mui-migration`의 실제 개발 이력(수백 커밋, 서버 IP·내부 도메인 포함)은
한 번도 push된 적이 없다 — 클라우드 루틴을 쓰려면 그 이력을 통째로 올려야 하는데, 그건 사용자의
명시적 승인 없이 할 수 없는 일이다. 그래서 실제 로컬 저장소와 사내 배포 서버 둘 다에 닿을 수
있는 방법은 이 컴퓨터 자체의 스케줄러뿐이다.

## 왜 "3시간마다 한 번씩"이 아니라 연속 루프인가 (2026-08-11 재설계)

처음 버전은 작업 스케줄러가 3시간마다 Claude Code를 **한 번** 띄우고 끝내는 방식이었다 —
실행 가능한 작업이 남아 있어도 다음 3시간을 그냥 흘려보냈다. 이 저장소가 스스로 지켜 온
MEGA LOOP 원칙("cycle 끝났다고 멈추지 않는다")을 감싸는 스크립트가 구조적으로 어기는
꼴이었다. 지금은 `autonomous_runner.ps1` 자체가 while 루프다 — 반복 사이에 sleep이 없다.

## 구성

- `autonomous_runner.ps1` — **연속 루프** 본체. 반복마다 **새 비대화형(`-p`) Claude Code
  프로세스**를 띄운다(대화를 이어받지 않는다 — 이 프로젝트 자체 규칙과 같은 이유: 상태는
  파일에 있다). 한 반복이 끝나면 곧장 다음 반복 — STOP/`PROJECT_COMPLETE`/연속실패 3회
  중 하나에 걸릴 때까지 멈추지 않는다.
- `install_task.ps1` — 작업 스케줄러 등록/제거(15분마다 감시하는 supervisor로 등록).
- 런타임 산출물은 전부 `var\runner\`(git 추적 안 됨)에 쌓인다:
  - `var\runner\logs\<timestamp>.log` — 각 반복의 원본 출력(`--output-format json`).
  - `var\runner\runner.log` — 반복 요약 한 줄씩(append-only).
  - `var\runner\state.json` — 연속 실패/연속 rate-limit 횟수 등.
  - `var\runner\STOP` — 있으면 다음 반복 시작 전에 루프가 끝난다.
  - `var\runner\PROJECT_COMPLETE` — Claude가 전체 완성 기준을 스스로 확인했을 때만 만든다.
    있으면 루프가 **정상 종료**한다 — 유일한 "성공적 종료" 조건.
  - `var\runner\run.lock` — 겹쳐 도는 것을 막는다. 이미 살아있는 루프가 있으면 새로 뜬
    프로세스(작업 스케줄러의 15분 heartbeat 대부분)는 즉시 조용히 종료한다.

## 설치

**시작 방법은 이 한 줄이다**(2026-08-12, D-64 — Task Scheduler 의존은 폐기됐다):

```powershell
cd C:\Users\hshwa\clovirone-web-assistant
.\scripts\runner\autonomous_runner.ps1
```

이 PowerShell 프로세스 자체가 `PROJECT_COMPLETE`까지 살아 있으면서 Worker invocation을 계속
관리한다. 창을 닫거나 Ctrl+C 하면 멈춘다(다음에 다시 같은 명령으로 재개 — 상태는 git과
`docs/`에서 복원된다). `install_task.ps1`은 남겨 두었지만 **더 이상 이 구조의 일부가 아니다** —
등록하지 않아도 되고, 등록된 항목의 삭제는 사용자가 직접 한다(CLAUDE.md §0).

## 멈추는 방법

- **사용자가 명시적으로 멈추기**: `var\runner\STOP` 파일을 만든다(빈 파일이어도 됨). 돌고 있는
  루프는 다음 invocation 전에 이 파일을 보고 끝나고, 이 파일이 있는 동안은 새로 시작해도
  이유를 크게 출력하고 exit 3으로 끝난다. 지우면 다시 시작할 수 있다.
  **이 파일은 오직 사람만 만든다** — 스크립트는 절대 여기에 쓰지 않는다.
- **연속 3회 실패 시**: 스크립트가 `var\runner\AUTO_STOP`(STOP이 아니다)을 만들고 멈춘다.
  `var\runner\logs\`로 원인을 본 뒤 **그냥 다시 실행하면 된다** — 수동 재시작 자체를 그 실패에
  대한 확인으로 보고, AUTO_STOP을 크게 알린 뒤 정리하고 `consecutiveFailures`를 0으로 되돌린다.
  (예전엔 이 경우에도 STOP을 만들어서, 원인을 고치고 재시작해도 조용히 아무 일도 안 일어났다.)
- 프로젝트가 실제로 끝나면(모든 완성 기준 충족) Claude 스스로 `PROJECT_COMPLETE`를 **내용과 함께**
  만들어 루프를 정상 종료한다 — 이것이 유일한 "정상적으로 할 일이 없어서 멈춘" 경우다.
  빈 파일은 완료로 인정되지 않는다(Supervisor와 Stop hook이 같은 규칙을 쓴다).

## Stop hook (보조 제동)

`.claude/settings.json`이 `scripts/runner/stop_guard.py`를 Stop hook으로 걸어 둔다. Supervisor가
띄운 Worker에서만(`CLOVIR_SUPERVISED=1`) 동작하며, `PROJECT_COMPLETE`가 유효하지 않은데 Claude가
끝내려 하면 **invocation당 한 번** 되돌린다. 그 제동으로 이어진 continuation에서 다시 멈추려
하면 통과시킨다(무한 루프 방지). **사람이 직접 쓰는 대화형 세션에는 이 환경변수가 없어 아무
영향이 없다.** 어떤 오류에서도 정지를 허용한다(fail-open) — 보조 장치가 Worker를 영구히 붙잡는
것이 더 나쁘기 때문이다. process 경계를 넘는 연속성의 1차 책임은 어디까지나 이 Supervisor다.

## 안전장치 요약

| 장치 | 막는 것 |
|---|---|
| `STOP` 파일 (사용자 전용) | 다음 invocation 전에 확인 — 사용자가 원할 때 멈추는 확실한 수단. 있으면 새 시작도 이유를 크게 출력하고 exit 3 |
| `PROJECT_COMPLETE` 파일 | Claude 스스로 전체 완성을 검증했을 때만(**내용 필수**) — 유일한 정상 종료 |
| `run.lock` (배타 파일 핸들) | 두 Supervisor가 같은 워킹트리를 동시에 고치지 않는다. 크래시해도 OS가 핸들을 회수하므로 stale lock이 다음 시작을 막지 않는다 |
| 연속 실패 3회 → `AUTO_STOP` | 같은 원인으로 무한 재시도하지 않는다. 수동 재시작 시 크게 알리고 자동 정리 |
| rate-limit/overload 감지 시에만 지수 백오프 | 진짜 기다릴 이유가 있는 경우만 대기(60초~30분) — 일반 실패는 즉시 재시도 |
| 저장소 dirty 시 2분 뒤 재확인 (내용 안 변하면 5회 후 진행) | 대화형 세션과 충돌 방지 + **무한 대기 방지**(유령 dirty 상태로 영원히 멈추지 않는다) |
| `--max-budget-usd 15` | invocation당 API 지출 상한(Claude Code 자체 기능). **PROJECT work unit이 아니다** — 예산으로 한 Worker가 끝나도 곧바로 다음 invocation이 같은 세션을 resume한다 |
| `Process.WaitForExit(150분)` | 멈춰 버린 invocation을 실제로 강제 종료(그 invocation만 실패로 셈, 루프는 안 죽음) |
| `$MaxIterationsPerLaunch = 0` | **무제한(production 기본)**. invocation 횟수는 Supervisor 종료 조건이 아니다. 양수는 controlled test 전용 override |
| `--model sonnet --effort max` | Worker 품질을 매 invocation에 명시 고정(새 세션·`--resume` 모두). 이전 세션의 `/model`, 사용자 global setting, 과거 세션에 저장된 model, 우연한 default에 좌우되지 않는다 |
| Stop hook (`stop_guard.py`) | 완료 마커 없이 끝내려는 Worker를 invocation당 한 번 되돌린다(보조 장치, fail-open) |
| `--permission-mode auto` | `--dangerously-skip-permissions`/`bypassPermissions`는 **절대 쓰지 않는다** — 이 세션이 실제로 쓰고 있는 것과 같은 모드로, 자동 분류기가 여전히 위험한 동작(대량 삭제 등)을 막는다 |
| 프롬프트 안의 배포 자격증명 경계 | 채팅에 붙여넣어진 SSH/sudo 비밀번호를 어떤 서버 배포에도 쓰지 않는다는 규칙을 매 반복 프롬프트에 명시 — 10.100.64.71 배포는 사용자가 직접 하거나 NOPASSWD sudoers를 사용자가 직접 구성해야만 가능하다 |

## 수정 이력

- **2026-08-12 (D-65, Runtime contract 확정)**: Worker 품질을 `--model sonnet --effort max`로
  매 invocation에 명시 고정(새 세션·`--resume` 모두). 실측 근거: `--effort`를 안 넘기면
  Worker 안의 effort가 사용자 `settings.json`의 `effortLevel: high`를 그대로 따라갔고,
  `--effort max`를 넘기면 `max`로 확정됐다(Stop hook 입력의 `effort.level`로 직접 관측,
  주변에 `CLAUDE_EFFORT=high`가 있어도 동일). `--model sonnet`은 응답 JSON의
  `canonicalModel=claude-sonnet-5`로 확인. `$MaxIterationsPerLaunch` 기본값을 300 → **0(무제한)**
  으로 바꿔 invocation 횟수가 Supervisor 종료 조건이 되지 않게 했다(양수는 test override).
  requested/actual model·effort를 `runner.log`에 남긴다. `--max-budget-usd`는 15 그대로.
- **2026-08-12 (D-64, Continuity Bootstrap)**: Stop hook(`stop_guard.py`) 추가 —
  Supervisor가 띄운 Worker에서만 동작하며 완료 마커 없이 끝내려 할 때 invocation당 한 번
  되돌린다. `STOP`(사용자 전용)과 `AUTO_STOP`(자동 실패 흔적)을 분리해, 원인을 고친 뒤
  수동 재시작하면 조용히 무력화되지 않게 했다. 이번에 실제로 발견해 고친 결함:
  ① `app/worker_main.py`가 CRLF/LF 정규화 때문에 내용 차이가 0인데도 영원히 `git status`에
  modified로 보여, Supervisor가 dirty 대기 루프에서 Claude를 **한 번도 못 띄우던** 문제
  (파일 정규화 + 대기 상한 추가), ② `Wait-Process -Timeout -PassThru`로는 timeout이 절대
  감지되지 않아 강제 종료 분기가 죽은 코드였던 문제(`Process.WaitForExit(ms)`로 교체 —
  실측: 상한을 넘긴 프로세스가 죽지 않고 같은 세션에 두 프로세스가 붙었다), ③ 런어웨이
  상한에서 "스케줄러가 이어받는다"는 거짓 안내, ④ 같은 초에 시작된 두 invocation의 로그
  파일 덮어쓰기. 단일 Writer 잠금은 PID 비교 → 배타 파일 핸들로 교체. 격리 scratch 저장소에서
  **실제 스크립트**로 controlled test A~H 통과(근거는 `docs/DECISIONS.md` D-64).
- **2026-08-11**: `Start-Process -ArgumentList`에 거대한 멀티라인 프롬프트 문자열을 배열
  원소로 직접 넘기던 방식이 Windows 커맨드라인 재조립 과정에서 깨져(`error: unknown
  option '--oneline'` — 프롬프트 안의 예시 텍스트가 `claude.exe` 자신의 옵션으로 오인됨)
  2026-08-11 09시경부터 3회 연속 실패 후 자동 STOP, 이후 약 12시간 no-op 상태였다. 프롬프트를
  임시 파일에 써서 `-RedirectStandardInput`으로 표준입력 리다이렉트하는 방식으로 고쳤다
  (`claude -p`는 위치 인자 없이 호출하면 stdin에서 프롬프트를 읽는다 — 직접 확인함). 격리된
  스크래치 디렉터리에서 같은 버그 유발 문구를 포함한 프롬프트로 재현 테스트해 exit 0 +
  의도한 출력을 확인했다. 상세는 `docs/DECISIONS.md` D-60.
- **2026-08-11 (D-61)**: `run.lock`을 이미 살아있는 루프가 쥐고 있어 새 프로세스가 조용히
  `exit 0` 하던 것 — 사용자가 직접 수동 실행했는데 아무 일도 안 일어나면 이유를 알 수
  없었다. 이제 항상 한 줄 로그를 남긴다. `STOP` 파일이 이미 있는 채로 새로 수동 실행하는
  경우도 잠금 획득 직후 한 번 더 명시적으로 알리도록 추가(재개 방법 포함). 격리된 스크래치
  저장소에서 실제로 controlled test를 돌려 (1) exit 0 뒤 sleep 없이 ~0.1초 만에 다음
  반복이 시작되는 것, (2) 두 번째 인스턴스가 즉시 물러나는 것, (3) STOP이 있으면 새 실행이
  이유를 출력하고 끝나는 것을 타임스탬프 로그로 확인했다. 상세는 `docs/DECISIONS.md` D-61.

## 알려진 한계 (정직하게 남긴다)

- 이 PowerShell 프로세스가 살아 있는 동안만 돈다. 창을 닫거나 로그아웃·재부팅하면 멈춘다 —
  **자동으로 되살리는 장치는 없다**(Task Scheduler 의존 폐기). 다시 시작하려면 사용자가
  `.\scripts\runner\autonomous_runner.ps1`을 한 번 더 실행하면 된다(상태는 git과 `docs/`에서 복원).
- 실제 배포(`10.100.64.71`)는 이 Runner가 자동으로 못 한다(비밀번호 경계) — 사용자가
  NOPASSWD sudoers를 구성하기 전까지는 구현·테스트·문서화까지만 자동으로 진행된다.
- 연속 실행이 API 지출을 빠르게 누적시킬 수 있다(invocation당 최대 $15, 사이에 지연 없음,
  **invocation 횟수 상한 없음**) — `--max-budget-usd`는 invocation 단위 상한이지 일일/누적
  상한이 아니다. 이것은 의도된 설계다(횟수 때문에 프로젝트가 중간에 멈추지 않게 하려는 것).
  지출이 걱정되면 `var\runner\runner.log`의 `totalRuns`로 누적 invocation 수를 확인하고
  필요할 때 `var\runner\STOP`을 만들어 멈춘다.
