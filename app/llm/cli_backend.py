"""서버에 로그인된 **구독 CLI** 를 부른다 (§L). 프로세스를 띄우는 유일한 자리.

## 왜 이렇게까지 하는가

넣는 것이 사용자가 쓴 글(Notion 티켓 본문)이고, 부르는 것이 **도구를 쓸 수 있는 에이전트**다.
둘을 그냥 이으면 "요약해 줘" 가 아니라 "티켓에 적은 대로 해 줘" 가 된다. 서비스 계정
권한으로.

그래서 여섯 가지를 전부 지킨다. 하나라도 빠지면 나머지가 우회된다.

1. **본문은 stdin 으로만.** argv 는 `ps` 로 다 보인다. 같은 서버의 다른 사용자가 티켓
   내용을 읽는다. (`--system-prompt` 는 argv 에 실리지만 그건 **우리가 쓴 문자열**이다.)
2. **`shell=False`, argv 리스트만.** 문자열 명령을 받는 문을 열면 언젠가 그 문으로 값이
   흘러든다(`app/sysops/runner.py` 가 같은 문장을 적어 뒀다).
3. **도구를 전부 끈다.** 아래 세 겹이다.
4. **빈 임시 디렉터리에서 실행.** 설령 도구가 살아나도 거기엔 아무것도 없다. cwd 의
   CLAUDE.md 도, 프로젝트 설정도 없다.
5. **구분자 + "데이터이지 지시가 아니다"** 는 `prompt.py` 가 만든다.
6. **인코딩을 반드시 지정.** `text=True` 만 쓰면 로케일로 디코드한다. 한국어 Windows 는
   cp949 라 한글 출력이 UnicodeDecodeError 로 터지고, 그 예외는 리더 스레드에서 난다
   (`app/sysops/runner.py` 와 `tests/conftest.py` 가 같은 사고를 기록해 뒀다).

## 도구 차단이 세 겹인 이유 (그리고 그 한계)

  * `--tools ""` — **내장 도구 전부 끄기.** 이름을 안 적어도 되니 새 도구가 생겨도 안 낡는다.
  * `--disallowed-tools <이름 목록>` — 아래 표. **이름을 못박아 감사 가능하게** 한다.
  * `--strict-mcp-config` — MCP 서버를 전부 무시한다. 이게 없으면 서비스 계정에 붙어 있는
    MCP 도구(문서, 브라우저 등)가 그대로 살아난다. `--tools` 는 "내장 도구" 만 다룬다고
    도움말에 적혀 있어서, MCP 는 이 플래그로만 닫힌다.

**정직한 한계.** 이름 목록은 **우리가 아는 도구만** 막는다. CLI 에 새 도구가 생기면 그날부터
이 목록은 낡는다. 그래서 목록 하나에 기대지 않고 위 두 플래그를 같이 쓴다. 그래도
"모르는 도구가 하나도 없다" 는 증명은 못 한다 - 우리가 통제하지 않는 프로그램이다.
그리고 이 플래그들의 의미는 CLI 버전에 달려 있다. 다음 버전에서 이름이 바뀌면 조용히
효과가 없어질 수 있고, 그것은 이 파일에서 알아챌 방법이 없다.

## `--bare` 를 쓰지 않는 이유

도움말에 "Anthropic auth is strictly ANTHROPIC_API_KEY" 라고 적혀 있다. 즉 **구독 로그인을
무시하고 API 키를 쓴다.** 이 과제의 목적(구독으로 비용 줄이기)과 정확히 반대다.
같은 이유로 자식 환경에서 `ANTHROPIC_API_KEY` 를 **빼고** 띄운다. 키가 남아 있으면 CLI 가
조용히 API 크레딧을 태우고, 아무도 모른다.

## 로그인 상태를 어떻게 아는가 (직접 확인한 것)

자격 증명이 없는 홈으로 실제로 돌려 봤다. 결과가 이랬다.

    종료 코드 1, stderr 는 비어 있음, stdout 은 JSON:
    {"is_error": true, "subtype": "success", "terminal_reason": "api_error",
     "result": "Not logged in ..."}

🔴 `subtype` 이 `"success"` 다. 그것만 보고 성공을 판정하면 **"Not logged in" 이라는 영어
문장이 그대로 주간 리포트의 요약문이 된다.** 그래서 `is_error` 와 종료 코드를 먼저 보고,
실패일 때 메시지에서 로그인 문제인지 가린다.

메시지 문자열로 가리는 것은 취약하다(우리가 만든 문자열이 아니다). 그래서 못 가려도
안전한 쪽으로 접힌다: 못 가리면 그냥 '실패'이고, 어느 쪽이든 규칙 기반 요약으로 떨어지며
화면이 그 사실을 말한다. 틀려도 조용히 성공한 척은 안 된다.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess  # noqa: S404 - argv 전용, shell=False 고정
import tempfile

from app.llm import prompt, provider

logger = logging.getLogger("app.llm.cli")

# 이름을 못박아 막는 도구와 **왜** 막는지. 이유를 같이 두는 것이 이 표의 존재 이유다 -
# 이름만 있으면 다음 사람이 "요약하는데 Read 정도는 되겠지" 하고 지운다.
DISALLOWED_TOOLS: tuple[tuple[str, str], ...] = (
    ("Bash", "임의 명령 실행. 주입이 성공하면 서비스 계정 권한의 원격 코드 실행이 된다."),
    ("BashOutput", "백그라운드 셸의 출력을 읽는다. Bash 를 막아도 이름이 달라 따로 막는다."),
    ("KillShell", "실행 중인 셸을 죽인다. 요약에 필요 없고 남의 작업을 끊을 수 있다."),
    ("Edit", "파일을 고친다. 빈 디렉터리에서 돌아도 절대경로를 쓰면 바깥을 건드린다."),
    ("Write", "파일을 새로 쓴다. Edit 와 같은 이유로 막는다."),
    ("NotebookEdit", "노트북 파일을 고친다. Edit 의 다른 이름이라 따로 막는다."),
    ("Read", "파일을 읽는다. 읽은 내용이 요약문에 섞여 나오면 그대로 유출이다."),
    ("Glob", "파일 이름을 훑는다. 서버 구조를 알려 주는 것 자체가 다음 공격의 재료다."),
    ("Grep", "파일 내용을 훑는다. Read 와 같은 이유로 막는다."),
    ("WebFetch", "본문에 적힌 주소로 나간다. 요약본을 밖으로 실어 보내는 통로가 된다."),
    ("WebSearch", "밖으로 나간다. 요약에 필요 없고 검색어에 본문이 실려 나간다."),
    ("Task", "하위 에이전트를 띄운다. 그 에이전트의 도구 제한은 여기서 안 보인다."),
    ("SlashCommand", "저장소나 사용자 정의 명령을 부른다. 그 정의는 이 파일에 안 보인다."),
    ("TodoWrite", "요약에 필요 없다. 최소 권한 원칙에 따라 필요 없는 것은 준다는 이유가 없다."),
)

# 표에서 **파생**한다. 따로 적으면 표를 고쳐도 실제 인자는 안 바뀐다.
# 쉼표로 잇는 이유: 도움말이 "Comma or space-separated" 라고 적어 뒀고, 쉼표 하나짜리
# 인자는 argv 경계가 분명해서 뒤에 오는 플래그를 삼킬 여지가 없다.
DISALLOWED_TOOLS_ARG = ",".join(name for name, _why in DISALLOWED_TOOLS)

# 사람이 승인해 줄 수 없는 자리다(비대화식). 이 모드는 물어보는 모드라 사실상 전부 거절이다.
PERMISSION_MODE = "manual"

# 하드 상한. 설정에 0 이 하나 더 붙는 오타 하나로 워커 한 칸이 반나절 잠기는 것을 막는다.
MAX_TIMEOUT_SECONDS = 600
MIN_TIMEOUT_SECONDS = 5

# 모델이 장문을 보내도 여기서 자른다(app/assistant/narrate.py 의 MAX_TEXT_CHARS 와 같은 발상).
MAX_TEXT_CHARS = 2000

# 로그인 문제로 보이는 조각. 전부 소문자로 비교한다. 우리가 만든 문자열이 아니라서
# 목록이 낡을 수 있다 - 못 가려도 '실패'로 접히므로 조용한 성공은 안 된다.
LOGIN_HINTS: tuple[str, ...] = (
    "not logged in",
    "please run /login",
    "invalid api key",
    "authentication_error",
    "authentication failed",
    "unauthorized",
    "oauth token",
    "no credentials",
)

# 자식 프로세스에서 **지우는** 환경변수와 그 이유.
STRIPPED_ENV: tuple[tuple[str, str], ...] = (
    ("ANTHROPIC_API_KEY", "구독을 쓰러 왔는데 키가 있으면 CLI 가 조용히 API 크레딧을 태운다."),
    ("ANTHROPIC_AUTH_TOKEN", "같은 이유. 구독 로그인 대신 이 토큰이 쓰인다."),
    ("ANTHROPIC_BASE_URL", "호출이 우리가 모르는 곳으로 나간다."),
)

FORCED_ENV: dict[str, str] = {
    # 워커 안에서 자동 업데이트가 돌면 실행 시간이 예측 불가능해지고 타임아웃이 의미를 잃는다.
    "DISABLE_AUTOUPDATER": "1",
    # ANSI 이스케이프가 응답과 로그에 섞인다. 터미널 제어문자가 로그로 새는 경로이기도 하다.
    "NO_COLOR": "1",
    # 사용자가 쓴 티켓 본문이 서비스 계정 홈의 히스토리 파일에 남지 않게 한다.
    "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1",
}


def clamp_timeout(seconds) -> int:
    """설정값을 [MIN, MAX] 로 접는다. 타임아웃이 없으면 워커 한 칸이 영원히 잠긴다."""
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return provider.DEFAULT_TIMEOUT_SECONDS
    return max(MIN_TIMEOUT_SECONDS, min(MAX_TIMEOUT_SECONDS, value))


def build_argv(config: provider.LlmConfig, *, system_prompt: str) -> list[str]:
    """띄울 명령 전부. **본문은 여기 없다** - 이 함수에 본문을 넘길 방법 자체가 없다."""
    return [
        config.executable,
        "-p",
        "--input-format", "text",
        "--output-format", "json",
        "--model", config.model,
        "--permission-mode", PERMISSION_MODE,
        # 내장 도구 전부 끄기. 목록이 낡는 문제를 덮는 쪽이라 먼저 둔다.
        "--tools", "",
        "--disallowed-tools", DISALLOWED_TOOLS_ARG,
        "--strict-mcp-config",
        # 본문에 "/명령" 이 적혀 있어도 그것이 명령으로 해석되지 않게 한다.
        "--disable-slash-commands",
        # 티켓 본문이 서비스 계정 디스크에 세션 기록으로 남지 않게.
        "--no-session-persistence",
        "--system-prompt", system_prompt,
    ]


def child_env(base=None) -> dict[str, str]:
    """자식 환경. **지우는 것**과 **박는 것**이 위 두 표에 이유와 함께 있다.

    통째로 비우지 않고 복사해서 지우는 이유: CLI 는 구독 자격 증명을 홈 디렉터리에서 찾는다.
    HOME/USERPROFILE/APPDATA 를 지우면 로그인이 돼 있는데도 안 돼 있다고 나온다. 즉
    '더 안전하게' 만든 것이 기능을 조용히 죽인다.
    """
    env = dict(os.environ if base is None else base)
    for name, _why in STRIPPED_ENV:
        env.pop(name, None)
    env.update(FORCED_ENV)
    return env


def looks_like_login_problem(text: str) -> bool:
    lowered = (text or "").lower()
    return any(hint in lowered for hint in LOGIN_HINTS)


def clean_text(value) -> str | None:
    """모델 출력은 신뢰하지 않는다(불변 §11). 문자열인지, 제어문자는 없는지 보고 자른다."""
    if not isinstance(value, str):
        return None
    text = "".join(c for c in value if c in "\n\t" or c.isprintable()).strip()
    return text[:MAX_TEXT_CHARS] if text else None


class ClaudeCliBackend:
    """구독 CLI 백엔드. `summarize` 하나만 밖에서 부른다."""

    name = provider.BACKEND_CLI

    def __init__(
        self,
        config: provider.LlmConfig,
        *,
        run=subprocess.run,
        nonce_factory=prompt.new_nonce,
        workdir_factory=tempfile.TemporaryDirectory,
    ) -> None:
        # subprocess 경계를 주입받는 이유는 `app/sysops/runner.py` 와 같다: 실제 프로세스를
        # 띄우지 않고도 "우리가 지키기로 한 것" 을 전부 검사할 수 있어야 한다.
        self._config = config
        self._run = run
        self._nonce_factory = nonce_factory
        self._workdir_factory = workdir_factory

    def summarize(self, *, body: str, task: str = prompt.TASK_WEEKLY) -> provider.LlmResult:
        """본문 → 요약. **예외를 던지지 않는다.** 실패는 전부 값으로 돌아간다."""
        try:
            built = prompt.build_prompt(body=body, nonce=self._nonce_factory(), task=task)
        except prompt.EmptyBodyError:
            return provider.failure(provider.STATUS_EMPTY, self.name)
        except prompt.InvalidNonceError:
            # 코드 결함이다(사용자 입력 문제가 아니다). 그래도 워커를 죽이지는 않는다.
            logger.exception("난스 생성이 계약을 어겼다")
            return provider.failure(provider.STATUS_FAILED, self.name)

        if built.delimiter_conflict:
            # 사람이 볼 자리에만 남긴다. 프롬프트에는 적지 않는다(prompt.py 참조).
            logger.warning("본문에 구분자 흉내가 있어 걷어냈다")

        argv = build_argv(self._config, system_prompt=built.system)
        timeout = clamp_timeout(self._config.timeout_seconds)

        with self._workdir_factory(prefix="clovi-llm-") as workdir:
            try:
                completed = self._run(
                    argv,
                    input=built.user,
                    cwd=workdir,
                    env=child_env(),
                    shell=False,
                    capture_output=True,
                    # 🔴 인코딩을 안 적으면 로케일로 디코드한다. 한국어 출력에서 실제로 터진다.
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                logger.warning("LLM CLI 시간 초과 (%s초)", timeout)
                return provider.failure(provider.STATUS_TIMEOUT, self.name)
            except (FileNotFoundError, NotADirectoryError, PermissionError):
                logger.warning("LLM CLI 를 실행할 수 없다: %s", self._config.executable)
                return provider.failure(provider.STATUS_MISSING_CLI, self.name)
            except OSError:
                logger.exception("LLM CLI 실행이 실패했다")
                return provider.failure(provider.STATUS_FAILED, self.name)

        return self._interpret(completed)

    def _interpret(self, completed) -> provider.LlmResult:
        """CLI 응답 → 결과. 판정 순서가 이 함수의 전부다."""
        stdout = (getattr(completed, "stdout", "") or "").strip()
        stderr = (getattr(completed, "stderr", "") or "").strip()
        returncode = getattr(completed, "returncode", 1)

        try:
            payload = json.loads(stdout)
        except ValueError:
            payload = None

        if not isinstance(payload, dict):
            # 진단은 서버 로그에만. 원문에 경로나 토큰 이름이 섞여 있을 수 있다.
            logger.warning("LLM CLI 응답을 해석하지 못했다 (rc=%s): %s", returncode, stderr[-300:])
            if looks_like_login_problem(f"{stdout}\n{stderr}"):
                return provider.failure(provider.STATUS_NOT_LOGGED_IN, self.name)
            return provider.failure(provider.STATUS_FAILED, self.name)

        raw_result = payload.get("result")
        # 🔴 `subtype` 은 실패에도 "success" 다. is_error 와 종료 코드를 본다.
        if payload.get("is_error") or returncode != 0:
            blob = f"{raw_result if isinstance(raw_result, str) else ''}\n{stderr}"
            logger.warning("LLM CLI 실패 (rc=%s): %s", returncode, blob.strip()[-300:])
            if looks_like_login_problem(blob):
                return provider.failure(provider.STATUS_NOT_LOGGED_IN, self.name)
            return provider.failure(provider.STATUS_FAILED, self.name)

        text = clean_text(raw_result)
        if text is None:
            return provider.failure(provider.STATUS_EMPTY, self.name)
        return provider.ok(text, self.name)
