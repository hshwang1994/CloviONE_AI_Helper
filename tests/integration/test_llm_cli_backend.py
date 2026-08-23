"""CLI 백엔드 계약 (§L) - 프로세스를 **어떻게** 띄우는가.

tests/unit/test_llm_prompt.py 가 "무엇을 보내는가" 를 본다면, 이 파일은 "어떻게 띄우는가"
를 본다. 둘 다 있어야 방어가 성립한다. 프롬프트를 아무리 잘 감싸도 도구가 켜져 있으면
주입 한 줄이 서비스 계정 권한의 원격 코드 실행이 된다.

## 진짜 프로세스를 띄우지 않는 이유

Claude CLI 는 로그인 상태·네트워크·구독 한도에 따라 결과가 달라진다. 그것을 테스트에
넣으면 CI 가 남의 상태에 따라 빨개지고, 그러면 아무도 안 본다. 대신 **subprocess 경계를
주입**해서 우리가 지키기로 한 것(argv, stdin, cwd, env, 인코딩, 타임아웃)을 전부 눈으로
본다. 실제 CLI 의 응답 모양은 아래 SUCCESS_JSON / NOT_LOGGED_IN_JSON 으로 고정했다 -
둘 다 진짜 CLI 를 돌려 받아 적은 것이다.

🔴 NOT_LOGGED_IN_JSON 의 `is_error` 는 true 인데 `subtype` 은 "success" 다. 즉 subtype 을
보고 성공을 판정하면 **로그인이 안 된 서버에서 "Not logged in" 이라는 문자열이 그대로
주간 리포트의 요약문으로 실린다.** 이 저장소가 가장 싫어하는 실패다.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import replace

import pytest

from app.llm import cli_backend, prompt, provider
from app.llm.service import LlmService

pytestmark = pytest.mark.integration

# 본문 안에서만 나오는 희귀 토큰. argv 검사가 우연히 통과하지 않게 한다.
BODY = "GIT-4242 결제 모듈이 죽습니다. 재현: 쿠폰 중복적용. 표식Z9Q7X"
RULE_MD = "## 규칙이 쓴 요약\n- 진행 중 2건"

# 진짜 CLI 응답에서 필요한 것만 남긴 것(--output-format json).
SUCCESS_JSON = json.dumps({
    "is_error": False,
    "subtype": "success",
    "result": "결제 모듈 장애 1건이 열려 있습니다.",
    "type": "result",
}, ensure_ascii=False)

# 자격 증명이 없는 홈으로 실제 CLI 를 돌려 받은 응답이다. 종료 코드는 1 이었고 stderr 는
# 비어 있었다. 사람이 보는 문구에 가운뎃점이 들어 있다는 점도 그대로 남겨 둔다 -
# 이 문자열이 화면에 실리면 정적 검사(check_user_text.py)에도 걸린다.
NOT_LOGGED_IN_JSON = json.dumps({
    "is_error": True,
    "subtype": "success",
    "terminal_reason": "api_error",
    "result": "Not logged in · Please run /login",
    "type": "result",
}, ensure_ascii=False)


#: 이 시험들이 쓰는 모델 이름. **제품은 기본 모델을 안 고른다**(P-19 · D-201) —
#: 예전에는 `LlmConfig()` 가 이름 하나를 들고 있어서 시험이 그것에 기대고 있었다.
#: 이제 안 정하면 「설정 안 됨」이라, 시험도 운영자처럼 값을 정해서 준다.
TEST_MODEL = "시험용-모델"


def make_config(**over) -> provider.LlmConfig:
    over.setdefault("model", TEST_MODEL)
    return replace(provider.LlmConfig(), enabled=True, backend=provider.BACKEND_CLI, **over)


class RecordingRun:
    """subprocess.run 자리에 들어가는 가짜. 호출을 통째로 붙잡아 둔다."""

    def __init__(self, *, stdout: str = SUCCESS_JSON, stderr: str = "", returncode: int = 0,
                 raises: BaseException | None = None) -> None:
        self._stdout, self._stderr = stdout, stderr
        self._returncode, self._raises = returncode, raises
        self.argv: list[str] | None = None
        self.kwargs: dict | None = None
        self.cwd_entries: list[str] | None = None
        self.calls = 0

    def __call__(self, argv, **kwargs):
        self.calls += 1
        self.argv, self.kwargs = argv, kwargs
        cwd = kwargs.get("cwd")
        # 디렉터리가 **호출 시점에** 비어 있었는지를 본다. 나중에 보면 이미 지워져 있다.
        self.cwd_entries = sorted(os.listdir(cwd)) if cwd else None
        if self._raises is not None:
            raise self._raises
        return subprocess.CompletedProcess(argv, self._returncode, self._stdout, self._stderr)


def run_backend(runner: RecordingRun, *, config: provider.LlmConfig | None = None):
    backend = cli_backend.ClaudeCliBackend(config or make_config(), run=runner)
    return backend.summarize(body=BODY)


def arg_value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


# ── argv: 본문은 절대 여기 없다 ────────────────────────────────────────────────

def test_the_body_never_appears_in_argv():
    """🔴 argv 는 프로세스 목록에 그대로 보인다. 같은 서버의 다른 사용자가 읽는다."""
    runner = RecordingRun()
    run_backend(runner)

    joined = " ".join(runner.argv)
    assert "표식Z9Q7X" not in joined, (
        "본문이 argv 에 실렸다 - ps 한 번으로 티켓 내용이 읽힌다"
    )
    assert BODY not in joined


def test_the_body_is_delivered_on_stdin_inside_the_markers():
    runner = RecordingRun()
    run_backend(runner)

    stdin_text = runner.kwargs["input"]
    assert BODY in stdin_text
    assert prompt.MARKER_OPEN_PREFIX in stdin_text
    assert prompt.USER_REMINDER in stdin_text


def test_the_system_framing_actually_reaches_the_process():
    """프롬프트 파일에만 있고 argv 에는 안 실리면 방어가 없는 것과 같다."""
    runner = RecordingRun()
    run_backend(runner)
    assert prompt.DATA_NOT_INSTRUCTIONS in arg_value(runner.argv, "--system-prompt")


def test_shell_is_never_used_and_argv_is_a_list_of_strings():
    runner = RecordingRun()
    run_backend(runner)

    assert runner.kwargs.get("shell", False) is False, "shell=True 는 이 저장소에 없다"
    assert isinstance(runner.argv, list)
    assert all(isinstance(a, str) for a in runner.argv)


# ── 도구를 전부 끈다 ───────────────────────────────────────────────────────────

def test_every_builtin_tool_is_off():
    runner = RecordingRun()
    run_backend(runner)

    assert arg_value(runner.argv, "--tools") == "", (
        "내장 도구 전부 끄기가 빠졌다 - 목록에 없는 새 도구는 그대로 살아난다"
    )
    assert "--strict-mcp-config" in runner.argv, (
        "MCP 서버가 살아 있으면 도구 이름을 우리가 모르는 채로 붙는다"
    )


def test_the_named_denylist_is_passed_and_covers_the_dangerous_ones():
    runner = RecordingRun()
    run_backend(runner)

    denied = arg_value(runner.argv, "--disallowed-tools").split(",")
    for name in ("Bash", "Edit", "Write", "Read", "WebFetch", "Task"):
        assert name in denied, f"{name} 를 이름으로 막지 않았다"


def test_every_denied_tool_records_why_it_is_denied():
    """이름만 있는 목록은 다음 사람이 지운다. **왜** 가 같이 있어야 안 지운다."""
    assert cli_backend.DISALLOWED_TOOLS, "거부 목록이 비었다"
    for name, why in cli_backend.DISALLOWED_TOOLS:
        assert name and why, f"{name} 에 막는 이유가 없다"
        assert len(why) > 10, f"{name} 의 이유가 설명이 아니다: {why}"


def test_the_denylist_argument_is_derived_from_the_table():
    """표와 인자가 따로 놀면 표를 고쳐도 실제로는 안 바뀐다."""
    names = [name for name, _why in cli_backend.DISALLOWED_TOOLS]
    assert cli_backend.DISALLOWED_TOOLS_ARG == ",".join(names)


# ── 실행 환경: 빈 디렉터리, 우리 인코딩, 우리 env ─────────────────────────────

def test_it_runs_in_an_empty_directory():
    """설령 도구가 살아나도 거기엔 아무것도 없다. cwd 의 CLAUDE.md 도 안 읽힌다."""
    runner = RecordingRun()
    run_backend(runner)

    assert runner.cwd_entries == [], (
        f"작업 디렉터리가 비어 있지 않다: {runner.cwd_entries}"
    )
    assert os.path.isabs(runner.kwargs["cwd"])


def test_output_is_decoded_as_utf8_not_the_machine_locale():
    """text=True 만 쓰면 로케일로 디코드한다. 한국어 출력에서 실제로 터졌다."""
    runner = RecordingRun()
    run_backend(runner)

    assert runner.kwargs.get("encoding") == "utf-8"
    assert runner.kwargs.get("errors") == "replace"


def test_the_api_key_is_taken_out_of_the_child_environment(monkeypatch):
    """구독을 쓰러 왔는데 키가 남아 있으면 CLI 가 조용히 API 크레딧을 태운다.

    이 과제의 목적(비용)과 정반대라, 조용히 성공하는 쪽이 더 나쁜 실패다.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-be-used")
    runner = RecordingRun()
    run_backend(runner)

    child_env = runner.kwargs["env"]
    assert "ANTHROPIC_API_KEY" not in child_env
    assert child_env.get("NO_COLOR") == "1"


def test_the_hard_timeout_is_handed_to_the_process():
    runner = RecordingRun()
    run_backend(runner, config=make_config(timeout_seconds=37))
    assert runner.kwargs["timeout"] == 37


def test_an_absurd_timeout_is_clamped():
    """설정 오타 하나로 워커 한 칸이 반나절 잠기는 것을 막는다."""
    runner = RecordingRun()
    run_backend(runner, config=make_config(timeout_seconds=999999))
    assert runner.kwargs["timeout"] == cli_backend.MAX_TIMEOUT_SECONDS


# ── 결과 판정 ─────────────────────────────────────────────────────────────────

def test_a_successful_run_is_reported_as_llm():
    result = run_backend(RecordingRun())
    assert result.status == provider.STATUS_OK
    assert result.source == provider.SOURCE_LLM
    assert result.text == "결제 모듈 장애 1건이 열려 있습니다."
    assert result.notice is None


def test_not_logged_in_is_detected_even_though_subtype_says_success():
    """🔴 이 판정이 틀리면 'Not logged in' 이 주간 리포트의 요약문이 된다."""
    runner = RecordingRun(stdout=NOT_LOGGED_IN_JSON, returncode=1)
    result = run_backend(runner)

    assert result.status == provider.STATUS_NOT_LOGGED_IN, (
        "로그인 안 된 상태를 성공으로 읽었다"
    )
    assert result.source == provider.SOURCE_RULE
    assert result.text is None


def test_the_cli_error_text_is_never_handed_to_the_screen():
    """CLI 문구에는 가운뎃점이 들어 있다(정적 검사 위반). 그대로 옮기지 않는다."""
    runner = RecordingRun(stdout=NOT_LOGGED_IN_JSON, returncode=1)
    result = run_backend(runner)

    assert "Not logged in" not in (result.notice or "")
    assert "·" not in (result.notice or "")
    assert "로그인" in result.notice


def test_a_timeout_is_a_result_not_an_exception():
    """예외로 올리면 부르는 쪽이 감싸는 것을 잊는 날 워커 루프가 죽는다."""
    runner = RecordingRun(raises=subprocess.TimeoutExpired(cmd="claude", timeout=1))
    result = run_backend(runner)

    assert result.status == provider.STATUS_TIMEOUT
    assert result.source == provider.SOURCE_RULE
    assert result.notice


def test_a_missing_cli_says_it_is_missing():
    runner = RecordingRun(raises=FileNotFoundError("claude"))
    result = run_backend(runner)
    assert result.status == provider.STATUS_MISSING_CLI
    assert result.source == provider.SOURCE_RULE


def test_output_that_is_not_json_does_not_become_a_summary():
    runner = RecordingRun(stdout="갑자기 사람이 읽는 문장")
    result = run_backend(runner)
    assert result.status == provider.STATUS_FAILED
    assert result.text is None


def test_an_empty_result_is_not_reported_as_a_summary():
    runner = RecordingRun(stdout=json.dumps({"is_error": False, "result": "   "}))
    result = run_backend(runner)
    assert result.status == provider.STATUS_EMPTY
    assert result.source == provider.SOURCE_RULE


# ── 서비스: 규칙 기반으로 떨어지고, 그 사실을 말한다 ──────────────────────────

class StubBackend:
    name = provider.BACKEND_CLI

    def __init__(self, result, *, on_call=None) -> None:
        self._result, self._on_call = result, on_call
        self.calls = 0

    def summarize(self, *, body: str):
        self.calls += 1
        if self._on_call is not None:
            self._on_call()
        return self._result


def test_a_failure_falls_back_to_the_rule_summary_and_the_screen_says_why(tmp_path):
    backend = StubBackend(provider.failure(provider.STATUS_NOT_LOGGED_IN, provider.BACKEND_CLI))
    svc = LlmService(make_config(), data_dir=tmp_path, backend=backend)

    out = svc.weekly_summary(body=BODY)
    assert out["source"] == provider.SOURCE_RULE
    assert out["llm_summary"] is None
    assert "로그인" in out["llm_notice"], (
        "화면이 '왜 규칙 요약인지' 를 말하지 않는다 - 조용히 성공한 척하는 것과 같다"
    )


def test_a_success_is_reported_as_llm_with_no_notice(tmp_path):
    backend = StubBackend(provider.ok("한 줄 요약", provider.BACKEND_CLI))
    svc = LlmService(make_config(), data_dir=tmp_path, backend=backend)

    out = svc.weekly_summary(body=BODY)
    assert out["source"] == provider.SOURCE_LLM
    assert out["llm_summary"] == "한 줄 요약"
    assert out["llm_notice"] is None


def test_when_the_switch_is_off_the_backend_is_never_called(tmp_path):
    backend = StubBackend(provider.ok("불려서는 안 된다", provider.BACKEND_CLI))
    svc = LlmService(replace(make_config(), enabled=False), data_dir=tmp_path, backend=backend)

    out = svc.weekly_summary(body=BODY)
    assert backend.calls == 0
    assert out["source"] == provider.SOURCE_RULE
    assert out["llm_notice"]


def test_only_one_run_at_a_time(tmp_path):
    """🔴 워커가 한도를 태우면 사람이 쓰던 CLI 까지 막힌다. 동시 실행은 1개다."""
    inner: dict = {}

    def reenter():
        second = LlmService(
            make_config(), data_dir=tmp_path,
            backend=StubBackend(provider.ok("두 번째 요약", provider.BACKEND_CLI)),
        )
        inner["out"] = second.weekly_summary(body=BODY)

    outer_backend = StubBackend(
        provider.ok("첫 번째 요약", provider.BACKEND_CLI), on_call=reenter
    )
    first = LlmService(make_config(), data_dir=tmp_path, backend=outer_backend)

    out = first.weekly_summary(body=BODY)
    assert out["source"] == provider.SOURCE_LLM

    assert inner["out"]["source"] == provider.SOURCE_RULE, (
        "두 번째 호출이 동시에 CLI 를 띄웠다"
    )
    assert inner["out"]["llm_notice"]


def test_the_lock_is_released_so_the_next_run_can_take_it(tmp_path):
    """락이 안 풀리면 첫 실패 이후 영영 규칙 요약만 나온다 - 가용성 사고가 된다."""
    backend = StubBackend(provider.ok("요약", provider.BACKEND_CLI))
    svc = LlmService(make_config(), data_dir=tmp_path, backend=backend)

    assert svc.weekly_summary(body=BODY)["source"] == provider.SOURCE_LLM
    assert svc.weekly_summary(body=BODY)["source"] == provider.SOURCE_LLM
    assert backend.calls == 2


def test_the_source_vocabulary_matches_the_report_that_consumes_it():
    """주간 리포트 응답과 저장 행이 쓰는 `source` 어휘와 **같은 문자열**이어야 한다.

    여기서 갈라지면 화면은 두 어휘를 분기하게 되고, 저장 행의 source 는 조회 조건에서
    조용히 안 맞는다. app/projects 는 이 작업에서 읽기만 하므로, 어긋남은 이쪽이 고친다.
    """
    from app.projects.models import REPORT_SOURCE_LLM, REPORT_SOURCE_RULE

    assert provider.SOURCE_RULE == REPORT_SOURCE_RULE
    assert provider.SOURCE_LLM == REPORT_SOURCE_LLM


def test_a_backend_that_raises_does_not_take_the_worker_down(tmp_path):
    class Exploding:
        name = provider.BACKEND_CLI

        def summarize(self, *, body: str):
            raise RuntimeError("예상 못 한 실패")

    svc = LlmService(make_config(), data_dir=tmp_path, backend=Exploding())
    out = svc.weekly_summary(body=BODY)

    assert out["source"] == provider.SOURCE_RULE
    assert out["llm_notice"]
