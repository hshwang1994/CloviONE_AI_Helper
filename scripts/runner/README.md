# 자율 완성 Runner — 세션이 끝나도 이어지는 로컬 스케줄러

Claude Code 세션(터미널 창)을 닫아도, ClovirONE Web Assistant 프로젝트가 완료되지 않았다면
Windows 작업 스케줄러가 3시간마다 새 Claude Code 프로세스를 띄워 이어서 작업한다.

## 왜 클라우드 스케줄(`/schedule`)이 아니라 로컬인가

`/schedule`(RemoteTrigger)로 만드는 클라우드 루틴은 Anthropic 클라우드의 격리된 샌드박스에서
GitHub 저장소를 새로 clone해 돈다 — 이 컴퓨터의 로컬 파일도, 사내망 안의 `10.100.64.71`도
접근할 수 없다. 게다가 이 저장소의 `origin`(GitHub)에는 "secrets excluded" 라는 압축된 커밋
하나만 올라가 있고, `ui/mui-migration`의 실제 개발 이력(수백 커밋, 서버 IP·내부 도메인 포함)은
한 번도 push된 적이 없다 — 클라우드 루틴을 쓰려면 그 이력을 통째로 올려야 하는데, 그건 사용자의
명시적 승인 없이 할 수 없는 일이다. 그래서 실제 로컬 저장소와 사내 배포 서버 둘 다에 닿을 수
있는 방법은 이 컴퓨터 자체의 스케줄러뿐이다.

## 구성

- `autonomous_runner.ps1` — 실제 실행 스크립트. 매번 **새 비대화형(`-p`) Claude Code 프로세스**를
  띄운다(대화를 이어받지 않는다 — 이 프로젝트 자체 규칙과 같은 이유: 상태는 파일에 있다).
- `install_task.ps1` — 작업 스케줄러 등록/제거.
- 런타임 산출물은 전부 `var\runner\`(git 추적 안 됨)에 쌓인다:
  - `var\runner\logs\<timestamp>.log` — 각 실행의 원본 출력(`--output-format json`).
  - `var\runner\runner.log` — 실행 요약 한 줄씩(append-only).
  - `var\runner\state.json` — 연속 실패 횟수 등.
  - `var\runner\STOP` — 있으면 다음 실행이 즉시 건너뛴다.
  - `var\runner\run.lock` — 겹쳐 도는 것을 막는다(이전 실행이 살아있으면 건너뜀).

## 설치

```powershell
cd scripts\runner
.\install_task.ps1
```

3시간마다, **로그온 중일 때만** 실행되도록 등록된다(Windows 계정 비밀번호를 스케줄러에 저장하지
않는 것이 더 안전하다는 판단 — 대신 로그아웃/재부팅 중에는 돌지 않는다는 뜻이다).

즉시 한 번 테스트: `schtasks /Run /TN ClovirAssistAutonomousRunner`, 그 뒤
`var\runner\runner.log` 확인.

## 멈추는 방법

- **임시**(다음 실행 하나만 건너뛰고 싶을 때, 또는 잠깐 멈추고 싶을 때): `var\runner\STOP` 파일을
  만든다(빈 파일이어도 됨). 지우면 재개된다.
- **영구**(다시 등록하기 전까지 아예 안 뜨게): `.\install_task.ps1 -Uninstall`
- 연속 3회 실패하면 스크립트가 **스스로** STOP 파일을 만들고 멈춘다 — `var\runner\runner.log`로
  원인을 본 뒤, STOP 파일을 지우고 `var\runner\state.json`의 `consecutiveFailures`를 0으로
  되돌려야 재개된다(무한 오동작 방지).

## 안전장치 요약

| 장치 | 막는 것 |
|---|---|
| `STOP` 파일 | 즉시, 확실하게 멈추는 수단 |
| `run.lock` | 이전 실행이 아직 살아있으면 겹쳐 안 돈다 |
| 연속 실패 3회 → 자동 STOP | 같은 원인으로 무한 재시도하지 않는다 |
| `--max-budget-usd 15` | 1회 실행당 API 지출 상한(Claude Code 자체 기능) |
| `Wait-Process -Timeout 150분` | 멈춰 버린 프로세스를 강제 종료(3시간 주기보다 짧게 잡아 다음 실행과 안 겹침) |
| `--permission-mode auto` | `--dangerously-skip-permissions`/`bypassPermissions`는 **절대 쓰지 않는다** — 이 세션이 실제로 쓰고 있는 것과 같은 모드로, 자동 분류기가 여전히 위험한 동작(대량 삭제 등)을 막는다 |
| 프롬프트 안의 배포 자격증명 경계 | 채팅에 붙여넣어진 SSH/sudo 비밀번호를 어떤 서버 배포에도 쓰지 않는다는 규칙을 매 실행 프롬프트에 명시 — 10.100.64.71 배포는 사용자가 직접 하거나 NOPASSWD sudoers를 사용자가 직접 구성해야만 가능하다 |

## 알려진 한계 (정직하게 남긴다)

- 로그온 중일 때만 돈다. 컴퓨터가 꺼져 있거나 로그아웃 상태면 그 주기는 건너뛴다.
- Windows 작업 스케줄러의 "놓친 실행" 정책에 따라, 오래 로그아웃해 있다 로그온하면 여러 번
  밀린 실행이 한꺼번에 시작될 수 있다 — `run.lock`이 겹침은 막아도, 밀린 횟수만큼 순차 실행될
  수 있다. 오래 자리를 비울 예정이면 `install_task.ps1 -Uninstall`로 미리 내리는 것이 안전하다.
- 실제 배포(`10.100.64.71`)는 이 Runner가 자동으로 못 한다(비밀번호 경계) — 사용자가
  NOPASSWD sudoers를 구성하기 전까지는 구현·테스트·문서화까지만 자동으로 진행된다.
