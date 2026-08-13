#!/usr/bin/env python3
"""Stop hook — Supervised Worker가 "요약 쓰고 끝"으로 빠지는 것을 한 번 제동한다.

이것은 **보조 안전장치**다. Project continuity의 1차 책임은 여전히 로컬 PowerShell
Supervisor(`autonomous_runner.ps1`)에 있다(CLAUDE.md §11). Stop hook이 하는 일은 딱 하나 —
`PROJECT_COMPLETE=false`인데 Claude가 Summary/recap을 내고 invocation을 끝내려 할 때
**한 번** block해서 "아직 남은 일을 계속하라"고 되돌리는 것이다. 그 뒤 프로세스가 실제로
끝나면 다음 invocation은 Supervisor가 책임진다.

왜 "한 번"인가: block을 무한 반복하면 Claude Code의 Stop-hook 재진입 방어에 걸리고, 무엇보다
Supervisor를 대체하는 장치가 되어 버린다. 그래서 이 hook이 유발한 continuation 안에서
(`stop_hook_active=true`) 다시 멈추려 하면 그냥 보내 준다 — invocation당 제동 1회.

설치 위치는 `.claude/settings.json`(project scope)이고, **Supervisor가 띄운 Worker에서만**
활성화된다(`CLOVIR_SUPERVISED=1`). 사람이 직접 쓰는 대화형 세션에는 이 환경변수가 없으므로
hook은 즉시 통과한다 — 평소 작업을 방해하지 않는다.

--- 이 파일이 의존하는 계약 (2026-08-12, 설치된 claude 2.1.228에서 실제 호출로 확인) ---
  * `-p`(비대화형) 모드에서도 Stop hook은 실행된다.
  * project `.claude/settings.json`의 hooks는 `-p`에서 기본으로 로드된다.
  * Supervisor 프로세스의 환경변수는 claude.exe를 거쳐 hook 프로세스까지 상속된다.
  * stdin JSON에 `stop_hook_active`(bool)가 실제로 들어온다 — 정상 정지 시 false,
    이 hook이 block해서 이어진 continuation에서는 true.
  * exit 0 + stdout `{"decision":"block","reason":...}` → 정지가 취소되고 대화가 이어진다
    (실측: num_turns 1 → 2).
근거·재현 절차는 docs/DECISIONS.md D-64.

실패 시 방향(중요): 이 hook이 무슨 이유로든 깨지면 **정지를 허용한다**(fail-open). 보조
장치가 Worker를 영구히 붙잡아 두는 것이 block에 실패하는 것보다 훨씬 나쁘다 — 어차피
Supervisor가 다음 invocation을 띄운다.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# scripts/runner/stop_guard.py → parents[2] == 저장소 루트
PROJECT_DIR = Path(__file__).resolve().parents[2]
RUNNER_DIR = PROJECT_DIR / "var" / "runner"
COMPLETE_FILE = RUNNER_DIR / "PROJECT_COMPLETE"
GUARD_LOG = RUNNER_DIR / "stop_guard.log"

BLOCK_REASON = (
    "PROJECT_COMPLETE=false 다. Summary·recap·commit·clean tree·Full Regression green·"
    "현재 batch 완료·\"다음에 이어서\"는 전부 종료 조건이 아니다(CLAUDE.md §0/§13).\n"
    "invocation은 work unit이 아니다 — PROJECT 전체가 유일한 work unit이다. 지금 곧바로 "
    "가장 영향도 높은 runnable whole-product work를 계속하라. 하나의 Root Cause를 닫았으면 "
    "같은 invocation 안에서 다음 Root Cause로 넘어가라.\n"
    "다음에 할 일이 이미 정해져 있으면 **대형 상태 문서를 다시 통독하지 말고** 그대로 이어서 "
    "하라. 후보가 정말 고갈됐을 때만 docs/BACKLOG.md·QA_COVERAGE.md의 미해결 영역을 다시 "
    "훑되, 상단 몇 줄이나 \"다음 후보\"만 보고 정하지 마라.\n"
    "승인된 TEST SERVER(CLAUDE.md §9)에서는 SSH·sudo·package 설치·배포·E2E를 네가 직접 "
    "수행한다 — 도구나 QA 데이터가 없다는 것은 정지 사유가 아니다.\n"
    "사람만 풀 수 있는 진짜 외부 blocker(MFA·외부 승인·접근 불가)를 만났으면 "
    "docs/WORK_STATE.md에 기록하고 그것과 독립적으로 가능한 작업을 계속하라.\n"
    "완료 기준(CLAUDE.md §13)을 실제로 검증해 충족했다면, 그 근거와 타임스탬프를 "
    "var/runner/PROJECT_COMPLETE 에 적어라 — 그때만 정지가 허용된다."
)


def log(message: str) -> None:
    """진단용 append-only 로그. 실패해도 hook 판단에는 영향을 주지 않는다."""
    try:
        RUNNER_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).astimezone().isoformat()
        with GUARD_LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def _process_alive(pid: int) -> bool:
    """해당 PID의 프로세스가 지금 살아 있는가 (Windows, 의존성 없이).

    `os.kill(pid, 0)`은 **Windows에서 쓰면 안 된다** — 신호 0을 지원하지 않고 TerminateProcess로
    빠지는 경로가 있다. OpenProcess + GetExitCodeProcess로 확인한다.
    판단이 불가능하면 True(살아 있다고 가정)를 돌려준다 — 이 함수의 실패가 hook을 무력화하지
    않게 하기 위함이다(무력화 방향은 아래 supervisor_alive()가 별도로 관리한다).
    """
    try:
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return True


def supervisor_alive() -> bool:
    """`CLOVIR_SUPERVISED=1`이 **지금 살아 있는 Supervisor**에서 온 것인가.

    왜 필요한가(2026-08-12 실제로 발생): Supervisor는 자식 claude.exe에 표시를 물려주려고
    자기 프로세스 환경에 `CLOVIR_SUPERVISED=1`을 넣는다. 그런데 그 값은 **Supervisor를 시작한
    사용자의 PowerShell 창에도 그대로 남는다**. 사용자가 Ctrl+C로 Supervisor를 멈춘 뒤 같은
    창에서 대화형 Claude 세션을 시작하면, 그 세션이 supervised worker로 오인되어 이 hook이
    사람의 작업을 막는다 — 이 파일이 위에서 "대화형 세션에는 영향이 없다"고 약속한 것과 정반대다.
    Ctrl+C 경로에서는 Supervisor의 finally 정리도 보장되지 않으므로, 환경 복원만으로는 부족하다.

    그래서 Supervisor는 `CLOVIR_SUPERVISOR_PID`를 함께 넘긴다. 그 PID가 살아 있지 않으면
    (또는 아예 없으면) 이 표시는 죽은 Supervisor가 남긴 흔적이므로 사람 세션으로 보고 통과한다.
    """
    raw = os.environ.get("CLOVIR_SUPERVISOR_PID", "").strip()
    if not raw.isdigit():
        return False
    return _process_alive(int(raw))


def project_complete() -> bool:
    """완료 마커 gate — `autonomous_runner.ps1`의 판정과 **같은 규칙**이어야 한다.

    존재만으로는 부족하고 내용이 있어야 한다(빈 파일이 실수로 생겨 프로젝트가 조용히
    끝나는 것을 막는다). Claude는 무엇을 근거로 완료라 판단했는지 적게 되어 있다.
    """
    try:
        if not COMPLETE_FILE.is_file():
            return False
        return bool(COMPLETE_FILE.read_text(encoding="utf-8", errors="replace").strip())
    except Exception:
        return False


def allow(reason: str) -> None:
    log(f"allow  — {reason}")
    sys.exit(0)


def block() -> None:
    payload = {"decision": "block", "reason": BLOCK_REASON}
    # ensure_ascii=True: Windows 콘솔 인코딩(cp949)에 상관없이 안전한 순수 ASCII JSON.
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=True).encode("ascii"))
    sys.stdout.buffer.flush()
    log("block  — PROJECT_COMPLETE 없음, 이 invocation에서 제동 1회")
    sys.exit(0)


def main() -> None:
    # 1) Supervisor가 띄운 Worker가 아니면 아무 것도 하지 않는다 — 사람의 대화형 세션 보호.
    if os.environ.get("CLOVIR_SUPERVISED") != "1":
        sys.exit(0)

    # 1-A) 표시는 있는데 그 Supervisor가 이미 죽었으면, 사용자의 셸에 남은 흔적이다 —
    #      사람 세션으로 보고 통과한다(안 그러면 그 창에서 시작한 모든 세션이 계속 막힌다).
    if not supervisor_alive():
        allow(
            "CLOVIR_SUPERVISED=1 이지만 살아있는 Supervisor가 아니다"
            f"(CLOVIR_SUPERVISOR_PID={os.environ.get('CLOVIR_SUPERVISOR_PID', '<없음>')}) "
            "— 사용자 셸에 남은 흔적으로 보고 통과"
        )
        return

    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        # 앞의 BOM을 벗긴다. 호출자에 따라 stdin에 UTF-8 BOM이 붙는다 — 2026-08-12 실측:
        # Windows PowerShell 5.1에서 문자열을 native 명령에 파이프하면 실제로
        # b'\xef\xbb\xbf{...}' 가 들어온다. 그러면 json.loads가 실패하고 이 hook은 **조용히
        # fail-open** 한다. 제동 장치가 아무도 모르게 무력화되는 경로라 반드시 막는다.
        # (PowerShell 쪽 파일 읽기도 같은 규칙으로 BOM을 벗긴다 — runner_common.ps1)
        raw = raw.lstrip("﻿")
        if not raw.strip():
            # 입력이 비어 있으면 stop_hook_active를 알 수 없다 → 제동하면 무한 block 위험.
            allow("stdin 비어 있음 — stop_hook_active를 알 수 없어 fail-open")
            return
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            allow(f"stdin이 object가 아님({type(payload).__name__}) — fail-open")
            return
    except Exception as exc:  # 입력을 못 읽으면 판단할 근거가 없다 → 통과
        allow(f"stdin 파싱 실패({exc.__class__.__name__}) — fail-open")
        return

    # Worker 안에서 **실제로** 적용된 effort를 남긴다 — Supervisor가 `--effort max`를 넘겼는데
    # 사용자 settings의 effortLevel이나 환경변수에 밀리지 않았는지를 로그만으로 확인할 수 있다
    # (2026-08-12 실측: `--effort` 없이 부르면 여기 `high`가, `--effort max`면 `max`가 찍힌다).
    effort = (payload.get("effort") or {}).get("level")
    log(f"관측  — effort={effort} permission_mode={payload.get('permission_mode')} "
        f"stop_hook_active={payload.get('stop_hook_active')}")

    # 2) 이 hook이 이미 한 번 제동해서 이어진 continuation이면 보내 준다.
    #    (무한 block 루프 방지 — Supervisor를 대체하는 장치가 되면 안 된다.)
    if payload.get("stop_hook_active") is True:
        allow("stop_hook_active=true — 이 invocation에서는 이미 제동함, Supervisor에게 넘긴다")
        return

    # 3) 진짜 완료면 정지 허용.
    if project_complete():
        allow(f"PROJECT_COMPLETE 유효 — {COMPLETE_FILE}")
        return

    # 4) 그 외에는 한 번 제동한다.
    block()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # 어떤 예외도 Worker를 붙잡아 두지 않는다
        log(f"allow  — 예상치 못한 예외({exc.__class__.__name__}: {exc}) — fail-open")
        sys.exit(0)
