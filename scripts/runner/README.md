# 자율 완성 Runner — 세션이 끝나도 이어지는 로컬 CONTINUOUS 워커 (2차/백업)

> **2026-08-11 (D-60) 갱신**: 1차 연속 실행 메커니즘은 이제 하네스 내장 `/loop` dynamic
> mode + `ScheduleWakeup`이다(대화형 세션 안에서 동작, Task Scheduler 불필요) — 상세는
> `docs/DECISIONS.md` D-53·D-60. 이 문서가 설명하는 로컬 Runner는 **대화형 세션(터미널)이
> 아예 닫혀 있을 때만 쓰는 백업**이다. 대화형 세션이 저장소를 수정하는 동안은 이 Runner를
> 켜지 않는다(동시 수정 방지) — `var/runner/STOP`이 있으면 그런 뜻이다, 지우지 말 것.
> 새 Task Scheduler 항목을 만들거나 기존 것을 삭제하는 것은 이 세션이 하지 않는다(사용자
> 결정 사항).

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

```powershell
cd scripts\runner
.\install_task.ps1
```

15분마다, **로그온 중일 때만** 확인하도록 등록된다(Windows 계정 비밀번호를 스케줄러에 저장하지
않는 것이 더 안전하다는 판단 — 대신 로그아웃/재부팅 중에는 루프가 멈춘다는 뜻이다). 정상
상태에서는 이 15분 확인이 잠금 파일을 보고 즉시 종료하는 공짜 no-op이다 — 루프가 죽었을
때만(크래시·재부팅) 실제로 새 루프가 시작된다.

즉시 루프 시작(등록만으로는 다음 heartbeat까지 최대 15분 걸릴 수 있다):
`schtasks /Run /TN ClovirAssistAutonomousRunner`, 그 뒤 `var\runner\runner.log` 확인.

## 멈추는 방법

- **임시**(지금 반복이 끝나는 대로 루프 종료, 다시 등록 없이 재개 가능): `var\runner\STOP`
  파일을 만든다(빈 파일이어도 됨). 지우면 다음 heartbeat 때 재개된다.
- **즉시+영구**(돌고 있는 루프도 바로 멈추고, 다시 등록하기 전까지 아예 안 뜨게):
  `.\install_task.ps1 -Uninstall`
- 연속 3회 실패하면 스크립트가 **스스로** STOP 파일을 만들고 멈춘다 — `var\runner\runner.log`로
  원인을 본 뒤, STOP 파일을 지우고 `var\runner\state.json`의 `consecutiveFailures`를 0으로
  되돌려야 재개된다(무한 오동작 방지).
- 프로젝트가 실제로 끝나면(모든 완성 기준 충족) Claude 스스로 `PROJECT_COMPLETE`를 만들어
  루프를 정상 종료한다 — 이것이 유일한 "정상적으로 할 일이 없어서 멈춘" 경우다.

## 안전장치 요약

| 장치 | 막는 것 |
|---|---|
| `STOP` 파일 | 다음 반복 전에 확인 — 사용자가 원할 때 멈추는 확실한 수단 |
| `PROJECT_COMPLETE` 파일 | Claude 스스로 전체 완성을 검증했을 때만 — 유일한 정상 종료 |
| `run.lock` | 이미 살아있는 루프가 있으면 새 프로세스가 겹쳐 안 돈다 |
| 연속 실패 3회 → 자동 STOP | 같은 원인으로 무한 재시도하지 않는다 |
| rate-limit/overload 감지 시에만 지수 백오프 | 진짜 기다릴 이유가 있는 경우만 대기(60초~30분) — 일반 실패는 즉시 재시도 |
| 저장소 dirty 시 2분 뒤 재확인 | 대화형 세션과 충돌 방지, 3시간이 아니라 2분 단위로 빠르게 이어받음 |
| `--max-budget-usd 15` | 반복당 API 지출 상한(Claude Code 자체 기능) |
| `Wait-Process -Timeout 150분` | 한 반복이 멈춰 버리면 강제 종료(그 반복만 실패로 셈, 루프는 안 죽음) |
| `$MaxIterationsPerLaunch = 300` | 런어웨이 하드 스톱 — 걸려도 다음 15분 heartbeat가 새 루프로 이어받는다(멈춤 아님) |
| `--permission-mode auto` | `--dangerously-skip-permissions`/`bypassPermissions`는 **절대 쓰지 않는다** — 이 세션이 실제로 쓰고 있는 것과 같은 모드로, 자동 분류기가 여전히 위험한 동작(대량 삭제 등)을 막는다 |
| 프롬프트 안의 배포 자격증명 경계 | 채팅에 붙여넣어진 SSH/sudo 비밀번호를 어떤 서버 배포에도 쓰지 않는다는 규칙을 매 반복 프롬프트에 명시 — 10.100.64.71 배포는 사용자가 직접 하거나 NOPASSWD sudoers를 사용자가 직접 구성해야만 가능하다 |

## 수정 이력

- **2026-08-11**: `Start-Process -ArgumentList`에 거대한 멀티라인 프롬프트 문자열을 배열
  원소로 직접 넘기던 방식이 Windows 커맨드라인 재조립 과정에서 깨져(`error: unknown
  option '--oneline'` — 프롬프트 안의 예시 텍스트가 `claude.exe` 자신의 옵션으로 오인됨)
  2026-08-11 09시경부터 3회 연속 실패 후 자동 STOP, 이후 약 12시간 no-op 상태였다. 프롬프트를
  임시 파일에 써서 `-RedirectStandardInput`으로 표준입력 리다이렉트하는 방식으로 고쳤다
  (`claude -p`는 위치 인자 없이 호출하면 stdin에서 프롬프트를 읽는다 — 직접 확인함). 격리된
  스크래치 디렉터리에서 같은 버그 유발 문구를 포함한 프롬프트로 재현 테스트해 exit 0 +
  의도한 출력을 확인했다. 상세는 `docs/DECISIONS.md` D-60.

## 알려진 한계 (정직하게 남긴다)

- 로그온 중일 때만 돈다. 컴퓨터가 꺼져 있거나 로그아웃 상태면 루프가 멈춘다(재로그온 시
  다음 15분 heartbeat 안에 자동 재개).
- 실제 배포(`10.100.64.71`)는 이 Runner가 자동으로 못 한다(비밀번호 경계) — 사용자가
  NOPASSWD sudoers를 구성하기 전까지는 구현·테스트·문서화까지만 자동으로 진행된다.
- 연속 반복이 API 지출을 빠르게 누적시킬 수 있다(반복당 최대 $15, 반복 사이 지연 없음) —
  `--max-budget-usd`가 반복 단위 상한이지 일일/누적 상한은 아니다. 지출이 걱정되면
  `var\runner\runner.log`의 `totalRuns`로 누적 반복 수를 확인하고 필요시 STOP.
