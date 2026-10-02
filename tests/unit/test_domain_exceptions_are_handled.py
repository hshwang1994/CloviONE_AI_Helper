"""도메인 예외가 요청 경계를 넘어 날것의 500 으로 새지 않는다 (P4 · B-3).

`AppError` 의 하위 예외는 전역 처리기(`app/core/errors.py::register_error_handlers`)가 사람의
문장이 든 봉투(4xx · 503)로 옮긴다. 그 계층 **밖에** 서 있는 예외(`ValueError` · `RuntimeError` ·
`Exception` 을 바로 잇는 것)는 아무도 잡지 않으면 전역 처리기의 마지막 갈래(`Exception` → 500)로
떨어진다. 운영 로그의 진짜 500 다섯 건이 정확히 그 모양이었다 — `BlockError` 가 `ValueError` 였고,
본문 저장 경로만 그것을 422 로 옮기고 만들기 경로는 빠뜨렸다(지금은 `ValidationAppError` 의 하위다).

이 시험은 그런 예외를 **전부** 훑어 하나씩 분류를 요구한다. 분류는 넷 중 하나다.

  * **잡힌다(caught)** — 요청 경로에서 그 예외를 던지는 함수를 부르는 자리가 전부 잡아 값이나
    `AppError` 로 옮긴다. 옮긴 결과가 4xx · 503 · 정상 응답이라는 것을 보이는 시험을 근거로 댄다.
  * **처리기가 있다(handler)** — 앱에 그 예외 전용 처리기가 등록돼 있다.
  * **계약 방어(guard)** — 부르는 쪽이 조건을 먼저 확인해서 제품 경로로는 닿지 않는다. 닿지 않는다는
    것을 보이는 시험을 근거로 댄다.
  * **요청 밖(worker · helper · cli · startup)** — 워커 · 특권 헬퍼 · 명령줄 · 기동에서만 돈다.

분류가 거짓이 되지 않게 네 가지를 함께 못박는다. 던지는 모듈(`raised_in`)이 바뀌면 다시 분류해야
한다. 잡는다고 적은 모듈에는 실제 `except` 가 있어야 한다. 「요청 밖」과 「계약 방어」의 근거가 되는
함수(`reach`)는 적어 둔 모듈 밖에서 불리면 안 된다. 근거로 댄 시험은 실제로 있어야 한다.

새 예외 클래스를 만들면 이 시험이 실패한다. 요청이 닿는 예외라면 `AppError` 의 하위로 만드는 것이
가장 짧은 길이다(`BlockError` 가 그렇게 했다) — 이 목록에 적는 것은 그럴 수 없는 이유가 있을 때다.
"""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"

#: 파이썬 내장 예외의 이름. 앱 안의 클래스가 이 이름을 바로 이으면 예외 클래스다.
BUILTIN_EXCEPTIONS = frozenset(
    name for name, value in vars(builtins).items()
    if isinstance(value, type) and issubclass(value, BaseException)
)
#: 앱 밖(서드파티)의 예외를 잇는 클래스도 놓치지 않는다 — 이름으로 알아본다.
_EXCEPTION_SUFFIXES = ("Error", "Exception", "Warning")

CAUGHT, HANDLER, GUARD = "caught", "handler", "guard"
WORKER, HELPER, CLI, STARTUP = "worker", "helper", "cli", "startup"
#: 요청이 닿을 수 있는 분류 — 이 셋은 근거 시험이 반드시 있어야 한다.
REQUEST_REACHABLE = (CAUGHT, HANDLER, GUARD)


# ── 훑기 ─────────────────────────────────────────────────────────────────────


def _parse_tree(root: Path) -> dict[str, ast.Module]:
    trees: dict[str, ast.Module] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root.parent).as_posix()
        trees[rel] = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    return trees


_TREES: dict[Path, dict[str, ast.Module]] = {}


def _trees(root: Path) -> dict[str, ast.Module]:
    if root not in _TREES:
        _TREES[root] = _parse_tree(root)
    return _TREES[root]


def _simple_name(node) -> str | None:
    """`Boom` · `mod.Boom` · `Boom(...)` · `mod.Boom(...)` → `Boom`."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def domain_exceptions(root: Path = APP) -> dict[str, set[str]]:
    """`AppError` 를 거치지 않는 예외 클래스 이름 → 그것을 정의한 모듈들."""
    defs: dict[str, list[tuple[str, list[str]]]] = {}
    for rel, tree in _trees(root).items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [b for b in (_simple_name(base) for base in node.bases) if b]
                defs.setdefault(node.name, []).append((rel, bases))

    def derives(name: str, target, seen: frozenset = frozenset()) -> bool:
        if target(name):
            return True
        if name in seen:
            return False
        return any(
            derives(base, target, seen | {name})
            for _, bases in defs.get(name, ())
            for base in bases
        )

    def is_exception_base(name: str) -> bool:
        if name in BUILTIN_EXCEPTIONS:
            return True
        return name not in defs and name.endswith(_EXCEPTION_SUFFIXES)

    found: dict[str, set[str]] = {}
    for name, definitions in defs.items():
        if name == "AppError":
            continue
        for rel, bases in definitions:
            is_exc = any(derives(b, is_exception_base) for b in bases)
            is_app = any(derives(b, lambda n: n == "AppError") for b in bases)
            if is_exc and not is_app:
                found.setdefault(name, set()).add(rel)
    return found


def raise_sites(root: Path = APP) -> dict[str, set[str]]:
    """예외 이름 → `raise` 로 그것을 던지는 모듈들(`raise X` · `raise X(...)` · `raise m.X(...)`)."""
    sites: dict[str, set[str]] = {}
    for rel, tree in _trees(root).items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and node.exc is not None:
                name = _simple_name(node.exc)
                if name:
                    sites.setdefault(name, set()).add(rel)
    return sites


def except_sites(root: Path = APP) -> dict[str, set[str]]:
    """예외 이름 → `except` 로 그것을 잡는 모듈들(묶음 `except (A, B)` 포함)."""
    sites: dict[str, set[str]] = {}
    for rel, tree in _trees(root).items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is not None:
                kinds = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
                for kind in kinds:
                    name = _simple_name(kind)
                    if name:
                        sites.setdefault(name, set()).add(rel)
    return sites


def handler_sites(root: Path = APP) -> dict[str, set[str]]:
    """예외 이름 → 그 예외의 처리기를 등록하는 모듈들(`exception_handler(X)` · `add_exception_handler(X, …)`)."""
    sites: dict[str, set[str]] = {}
    for rel, tree in _trees(root).items():
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("exception_handler", "add_exception_handler")
                and node.args
            ):
                name = _simple_name(node.args[0])
                if name:
                    sites.setdefault(name, set()).add(rel)
    return sites


def reference_sites(root: Path = APP) -> dict[str, set[str]]:
    """이름 → 그 이름을 코드로 쓰는 모듈들. 주석 · 문서 문자열 속의 언급은 세지 않는다."""
    sites: dict[str, set[str]] = {}
    for rel, tree in _trees(root).items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.alias):
                name = node.asname or node.name.rsplit(".", 1)[-1]
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                name = node.name
            else:
                continue
            sites.setdefault(name, set()).add(rel)
    return sites


# ── 분류 ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Triage:
    defined_in: str
    kind: str
    raised_in: frozenset[str]
    why: str
    caught_in: frozenset[str] = frozenset()
    #: 근거가 되는 함수 · 클래스 이름 → 그것을 불러도 되는 모듈(끝이 `/` 면 그 아래 전부).
    reach: dict = field(default_factory=dict)
    #: `tests/…py::test_name` — 이 분류가 참이라는 것을 보이는 시험.
    proof: tuple[str, ...] = ()


def _fs(*items: str) -> frozenset[str]:
    return frozenset(items)


TRIAGE: dict[str, Triage] = {
    "OoxmlError": Triage(
        defined_in="app/ai/parsing/ooxml.py", kind=CAUGHT,
        raised_in=_fs("app/ai/parsing/ooxml.py"), caught_in=_fs("app/ai/parsing/ooxml.py"),
        why="밖으로 열린 세 입구(`parse_docx` · `parse_pptx` · `parse_xlsx`)가 잡아 파싱 실패 결과로 접는다.",
        reach={
            "parse_docx": _fs("app/ai/parsing/ooxml.py", "app/ai/parsing/registry.py"),
            "parse_pptx": _fs("app/ai/parsing/ooxml.py", "app/ai/parsing/registry.py"),
            "parse_xlsx": _fs("app/ai/parsing/ooxml.py", "app/ai/parsing/registry.py"),
        },
        proof=(
            "tests/unit/test_ai_parsing.py::test_a_zip_that_is_not_a_docx_fails_with_a_reason",
            "tests/unit/test_ai_parsing.py::test_a_file_that_is_not_a_zip_fails",
            "tests/unit/test_ai_parsing.py::test_an_oversized_entry_is_refused_before_it_is_read",
        ),
    ),
    "DestinationUnavailable": Triage(
        defined_in="app/backups/destination.py", kind=CAUGHT,
        raised_in=_fs("app/backups/destination.py"), caught_in=_fs("app/backups/service.py"),
        why="던지는 `copy_set` 을 부르는 자리는 백업 서비스 하나이고, 거기서 백업 결과의 경고 한 줄로 접는다.",
        reach={"copy_set": _fs("app/backups/destination.py", "app/backups/service.py")},
        proof=(
            "tests/integration/test_backup_destination_and_warnings.py"
            "::test_without_a_backup_store_the_backup_carries_a_warning",
        ),
    ),
    "PgToolMissing": Triage(
        defined_in="app/backups/pg_backup.py", kind=CAUGHT,
        raised_in=_fs("app/backups/pg_backup.py"), caught_in=_fs("app/backups/pg_backup.py"),
        why=(
            "검증 · 복원 시험 함수는 스스로 잡아 실패 사유로 돌려주고, 덤프(`backup_database`)는 백업 서비스의"
            " 실행 전체를 감싼 잡기가 실패한 백업 행으로 남긴다."
        ),
        reach={"backup_database": _fs("app/backups/pg_backup.py", "app/backups/service.py")},
        proof=("tests/unit/test_pg_backup.py::test_a_missing_tool_fails_it_does_not_pass",),
    ),
    "UnsupportedDatabaseError": Triage(
        defined_in="app/core/db.py", kind=STARTUP,
        raised_in=_fs("app/core/db.py"),
        why="PostgreSQL 이 아닌 DB 주소를 기동 때 거절한다 — 엔진을 만드는 자리는 앱 · 워커 기동과 명령줄뿐이다.",
        reach={
            "normalize_database_url": _fs("app/core/db.py"),
            "make_engine": _fs(
                "app/core/db.py", "app/main.py", "app/worker_main.py",
                "app/integrations/discovery.py", "app/cli/",
            ),
        },
    ),
    "PageAuthRequired": Triage(
        defined_in="app/core/deps.py", kind=HANDLER,
        raised_in=_fs("app/core/deps.py"),
        why="화면 경로 전용 신호이고, `app/main.py` 의 처리기가 로그인 화면으로 돌려보낸다.",
        proof=("tests/integration/test_auth_sessions.py::test_unauthenticated_page_redirects_to_login",),
    ),
    "WorkerLockHeld": Triage(
        defined_in="app/core/worker_lock.py", kind=WORKER,
        raised_in=_fs("app/core/worker_lock.py"),
        why=(
            "워커 리스를 `with` 로 잡을 때만 난다 — `with` 로 잡는 곳은 워커 기동뿐이고, AI 동시 실행 슬롯은"
            " `acquire()` 로 잡아 예외 대신 거짓을 받는다."
        ),
        reach={
            "WorkerLock": _fs("app/core/worker_lock.py", "app/worker_main.py", "app/ai/concurrency.py"),
        },
    ),
    "WorkerLockError": Triage(
        defined_in="app/core/worker_lock.py", kind=CAUGHT,
        raised_in=_fs("app/core/worker_lock.py"), caught_in=_fs("app/worker_main.py", "app/ai/runtime.py"),
        why=(
            "리스 파일을 못 쓰는 환경을 알리는 신호다. 워커 기동이 잡아 멈추고, AI 런타임(웹과 워커의 생성)은"
            " 동시 실행 슬롯을 못 잡은 호출을 실패 결과로 접는다."
        ),
        reach={
            "WorkerLock": _fs("app/core/worker_lock.py", "app/worker_main.py", "app/ai/concurrency.py"),
            "concurrency_lock": _fs("app/ai/concurrency.py", "app/ai/runtime.py"),
        },
        proof=("tests/unit/test_ai_runtime_parts.py::test_an_unwritable_slot_directory_is_a_failed_result_not_a_crash",),
    ),
    "PermanentJobError": Triage(
        defined_in="app/jobs/exceptions.py", kind=WORKER,
        raised_in=_fs(
            "app/jobs/handlers/chat_message.py", "app/jobs/handlers/llm_connection_test.py",
            "app/jobs/handlers/mail_relay_check.py",
            "app/jobs/handlers/mail_send.py", "app/jobs/handlers/mail_verify.py",
            "app/jobs/handlers/project_weekly_summary.py",
            "app/jobs/handlers/schedule_run.py", "app/jobs/worker.py", "app/mail/renderers.py",
            # 알림 받을 주소 확인 메일(D-550)을 그리는 함수 — 메일 발송 잡 안에서만 불린다.
            "app/profiles/notify_email.py",
        ),
        caught_in=_fs("app/jobs/worker.py"),
        why="잡 처리기와 잡 루프만 던지고, 워커가 잡아 그 잡을 재시도 없이 실패로 끝낸다.",
        reach={"render_mail": _fs("app/mail/renderers.py", "app/jobs/handlers/mail_send.py")},
    ),
    "InvalidNonceError": Triage(
        defined_in="app/llm/prompt.py", kind=GUARD,
        raised_in=_fs("app/llm/prompt.py"),
        why=(
            "난스는 언제나 `new_nonce()` 가 만든다(사용자 입력이 아니다). 프롬프트를 조립하는 유일한 자리인 AI 런타임이"
            " `new_nonce()` 를 그대로 넘긴다."
        ),
        reach={"build_prompt": _fs("app/llm/prompt.py", "app/ai/runtime.py")},
        proof=(
            "tests/unit/test_llm_prompt.py::test_a_weak_nonce_is_refused",
            "tests/unit/test_llm_prompt.py::test_different_nonces_produce_different_markers",
        ),
    ),
    "EmptyBodyError": Triage(
        defined_in="app/llm/prompt.py", kind=CAUGHT,
        raised_in=_fs("app/llm/prompt.py"),
        caught_in=_fs("app/ai/runtime.py"),
        why="`build_prompt` 를 부르는 유일한 자리(AI 런타임)가 잡아 「비었다」 결과로 접는다.",
        reach={"build_prompt": _fs("app/llm/prompt.py", "app/ai/runtime.py")},
        proof=("tests/unit/test_ai_gateway.py::test_generate_with_empty_data_says_empty",),
    ),
    "MailTransportError": Triage(
        defined_in="app/mail/transport.py", kind=WORKER,
        raised_in=_fs("app/mail/transport.py"),
        why=(
            "SMTP 발송기(`SmtpTransport`)는 메일 발송 잡과 연결 확인 잡, 로컬 릴레이 준비 점검 잡만 만든다. 관리자의"
            " 「시험 메일 보내기」 · 「연결 확인」 · 「점검 다시 하기」는 잡을 큐에 넣고 돌아오며, 실패는 워커가 발송 기록과 건강"
            " 상태, 준비 점검 결과에 남긴다."
        ),
        reach={"SmtpTransport": _fs(
            "app/mail/transport.py", "app/jobs/handlers/mail_send.py", "app/jobs/handlers/mail_verify.py",
            "app/jobs/handlers/mail_relay_check.py",
        )},
        proof=(
            "tests/security/test_global_scope_gate.py::test_global_admin_still_sends_test_mail",
            "tests/integration/test_mail_delivery.py::test_a_failed_send_is_recorded_not_swallowed",
        ),
    ),
    "_Rejected": Triage(
        defined_in="app/sysops/actions_secrets.py", kind=CAUGHT,
        raised_in=_fs("app/sysops/actions_secrets.py"), caught_in=_fs("app/sysops/actions_secrets.py"),
        why=(
            "특권 헬퍼의 비밀 값 검증 실패다. 같은 파일의 정규화 감싸개가 잡아 문구만 든 실패 결과로 돌려주고, 값은"
            " 싣지 않는다."
        ),
        proof=(
            "tests/unit/test_sysops_secret_actions.py::test_a_name_outside_the_table_is_refused_and_nothing_is_written",
            "tests/unit/test_sysops_secret_actions.py::test_a_text_slot_refuses_line_breaks",
        ),
    ),
    "RelayParamsError": Triage(
        defined_in="app/mail/relay_files.py", kind=CAUGHT,
        raised_in=_fs("app/mail/relay_files.py"),
        caught_in=_fs("app/mail/router.py", "app/settings/registry.py", "app/sysops/actions_mailrelay.py"),
        why=(
            "로컬 릴레이 인자(서버 이름 · 받는 도메인별 전달 서버 · 상위 SMTP 주소)의 검증 실패다. 메일 설정 API 와 범용 설정"
            " 검증기는 잡아 422 문장으로, 특권 헬퍼는 문구만 든 실패 결과로 돌려준다."
        ),
        proof=(
            "tests/unit/test_mail_relay_files.py::test_injection_shapes_are_refused",
            "tests/integration/test_mail_relay_api.py::test_relay_settings_refuse_injection_and_unknown_fields",
        ),
    ),
    "SpfPermError": Triage(
        defined_in="app/mail/relay_readiness.py", kind=CAUGHT,
        raised_in=_fs("app/mail/relay_readiness.py"), caught_in=_fs("app/mail/relay_readiness.py"),
        why="SPF 평가가 permerror 에 닿았다는 신호다. 같은 파일의 SPF 점검이 잡아 「SPF 레코드 오류」 줄로 바꾼다.",
        proof=("tests/unit/test_mail_relay_parts.py::test_spf_table",),
    ),
    "_RelayRejected": Triage(
        defined_in="app/sysops/actions_mailrelay.py", kind=CAUGHT,
        raised_in=_fs("app/sysops/actions_mailrelay.py"), caught_in=_fs("app/sysops/actions_mailrelay.py"),
        why=(
            "특권 헬퍼의 로컬 릴레이 동작 인자 검증 실패다. 같은 파일의 감싸개가 잡아 문구만 든 실패 결과로 돌려주고, 아무"
            " 파일도 쓰지 않는다."
        ),
        proof=(
            "tests/unit/test_sysops_mailrelay_actions.py::test_log_arguments_are_checked",
            "tests/unit/test_sysops_mailrelay_actions.py::test_there_is_no_takeover_argument",
        ),
    ),
    "ConvertError": Triage(
        defined_in="app/migration/convert.py", kind=CLI,
        raised_in=_fs("app/migration/convert.py"), caught_in=_fs("app/migration/load.py"),
        why="이관 적재기(명령줄 `migrate_cli`)의 값 변환 실패이고, 적재기가 잡아 이관 보고서의 차단 항목으로 남긴다.",
        reach={
            "coerce": _fs("app/migration/"),
            "Loader": _fs("app/migration/"),
        },
    ),
    "InvalidRetryPolicy": Triage(
        defined_in="app/schedules/scheduler.py", kind=CAUGHT,
        raised_in=_fs("app/schedules/scheduler.py"),
        caught_in=_fs("app/schedules/router.py", "app/schedules/scheduler.py"),
        why=(
            "재시도 정책을 읽는 `_max_attempts` 를 부르는 두 자리가 잡는다 — 실행 이력의 재시도는 422 문장으로,"
            " 지금 실행 · 자동 실행은 실패한 실행 행으로 옮긴다."
        ),
        reach={"_max_attempts": _fs("app/schedules/scheduler.py", "app/schedules/router.py")},
        proof=(
            "tests/integration/test_schedule_runs.py::test_run_now_on_an_unreadable_policy_answers_with_a_failed_run",
            "tests/integration/test_schedule_runs.py::test_retry_run_on_an_unreadable_policy_says_what_to_fix",
        ),
    ),
    "StorageNotReady": Triage(
        defined_in="app/storage/adapters.py", kind=CAUGHT,
        raised_in=_fs("app/storage/adapters.py"),
        caught_in=_fs("app/storage/service.py", "app/storage/archive.py", "app/backups/destination.py"),
        why="저장소 어댑터를 부르는 세 모듈이 잡는다 — 요청 경로(`storage/service.py`)는 503 `StorageUnavailableError` 로 옮긴다.",
        reach={
            "ensure_ready": _fs(
                "app/storage/adapters.py", "app/storage/service.py", "app/storage/archive.py",
                "app/backups/destination.py",
            ),
            "write_object": _fs("app/storage/adapters.py", "app/storage/service.py", "app/storage/archive.py"),
            "read_object": _fs("app/storage/adapters.py", "app/storage/service.py", "app/storage/archive.py"),
            "delete_object": _fs("app/storage/adapters.py", "app/storage/service.py"),
        },
        proof=(
            "tests/regression/test_storage_write_refusal.py::test_uploading_to_an_unmounted_store_is_503_not_500",
            "tests/regression/test_storage_write_refusal.py::test_reading_a_file_whose_store_went_away_is_503_not_404",
        ),
    ),
    "StorageWriteFailed": Triage(
        defined_in="app/storage/adapters.py", kind=CAUGHT,
        raised_in=_fs("app/storage/adapters.py"),
        caught_in=_fs("app/storage/service.py", "app/storage/archive.py"),
        why="실제 쓰기 · 읽기의 OSError 이고, 요청 경로(`storage/service.py`)가 503 이나 404 로 옮긴다.",
        reach={
            "write_object": _fs("app/storage/adapters.py", "app/storage/service.py", "app/storage/archive.py"),
            "read_object": _fs("app/storage/adapters.py", "app/storage/service.py", "app/storage/archive.py"),
            "delete_object": _fs("app/storage/adapters.py", "app/storage/service.py"),
        },
        proof=(
            "tests/regression/test_storage_write_refusal.py::test_a_failed_write_creates_neither_a_partial_file_nor_a_row",
        ),
    ),
    "ArchiveNotPossible": Triage(
        defined_in="app/storage/archive.py", kind=CAUGHT,
        raised_in=_fs("app/storage/archive.py"),
        caught_in=_fs("app/backups/service.py", "app/cli/storage_cli.py"),
        why="첨부 사본을 옮기는 두 입구를 부르는 자리는 백업 서비스(경고 한 줄로 접는다)와 명령줄(종료 코드 2)뿐이다.",
        reach={
            "archive_to_backup": _fs("app/storage/archive.py", "app/backups/service.py", "app/cli/storage_cli.py"),
            "restore_from_backup": _fs("app/storage/archive.py", "app/cli/storage_cli.py"),
        },
        proof=(
            "tests/integration/test_backup_destination_and_warnings.py"
            "::test_without_a_backup_store_the_backup_carries_a_warning",
            "tests/integration/test_storage_archive.py::test_with_no_backup_store_it_says_impossible_not_zero_copied",
        ),
    ),
    "ProtocolError": Triage(
        defined_in="app/sysops/protocol.py", kind=CAUGHT,
        raised_in=_fs("app/sysops/protocol.py", "app/sysops/helper.py"),
        caught_in=_fs("app/sysops/client.py", "app/sysops/helper.py"),
        why=(
            "웹 쪽에서는 `SysopsClient.call` 이 요청을 싸는 순간과 답을 푸는 순간을 둘 다 잡아 「도우미를 못 썼다」는"
            " 답으로 접는다. 헬퍼 쪽은 헬퍼 프로세스 안에서 잡는다."
        ),
        reach={
            "encode_request": _fs("app/sysops/protocol.py", "app/sysops/client.py"),
            "decode_response": _fs("app/sysops/protocol.py", "app/sysops/client.py"),
        },
        proof=(
            "tests/integration/test_sysops_api.py::test_an_oversized_request_is_a_failed_reply_not_a_500",
            "tests/integration/test_sysops_api.py::test_a_garbled_helper_reply_is_a_failed_reply_not_a_500",
        ),
    ),
    "BinaryNotAllowedError": Triage(
        defined_in="app/sysops/runner.py", kind=HELPER,
        raised_in=_fs("app/sysops/runner.py"), caught_in=_fs("app/sysops/actions.py"),
        why="명령을 실제로 띄우는 `RealRunner` 는 특권 헬퍼 프로세스만 쓰고, 동작 실행기가 잡아 실패한 동작으로 접는다.",
        reach={"RealRunner": _fs("app/sysops/runner.py", "app/sysops/helper.py")},
        proof=("tests/security/test_sysops_boundary.py::test_a_blocked_binary_becomes_a_failed_action_not_a_crash",),
    ),
    "NativeArchiveNeedsSessionError": Triage(
        defined_in="app/team_docs/repository_native.py", kind=GUARD,
        raised_in=_fs("app/team_docs/repository_native.py"),
        why=(
            "보관처리를 DB 세션 없이 부르는 코드 결함을 알리는 방어다. 유일한 제품 경로(휴지통 영구삭제의"
            " `_archive_source`)는 세션을 넘긴다."
        ),
        proof=("tests/integration/test_native_document_repository.py::test_archive_without_a_session_fails_loudly",),
    ),
}


# ── 분류가 참인가 ────────────────────────────────────────────────────────────


def test_every_domain_exception_is_triaged():
    found = domain_exceptions()
    missing = sorted(set(found) - set(TRIAGE))
    stale = sorted(set(TRIAGE) - set(found))
    assert not missing, (
        f"AppError 를 거치지 않는 새 예외가 있다: {missing}. 요청이 닿으면 AppError 의 하위로 만들고, "
        "그럴 수 없으면 TRIAGE 에 분류와 근거를 적는다."
    )
    assert not stale, f"없어진(또는 AppError 가 된) 예외가 TRIAGE 에 남아 있다: {stale}"
    wrong_home = {
        name: sorted(found[name]) for name, entry in TRIAGE.items() if found[name] != {entry.defined_in}
    }
    assert not wrong_home, f"정의한 모듈이 TRIAGE 와 다르다: {wrong_home}"


def test_raise_sites_are_pinned():
    sites = raise_sites()
    moved = {
        name: {"지금": sorted(sites.get(name, set())), "TRIAGE": sorted(entry.raised_in)}
        for name, entry in TRIAGE.items()
        if sites.get(name, set()) != entry.raised_in
    }
    assert not moved, (
        f"던지는 자리가 바뀌었다 — 새 자리가 요청 경로인지 보고 다시 분류한다: {moved}"
    )


def test_caught_classes_are_caught_where_the_triage_says():
    sites = except_sites()
    for name, entry in TRIAGE.items():
        if entry.kind == CAUGHT:
            assert entry.caught_in, f"{name}: 「잡힌다」인데 잡는 모듈을 안 적었다"
        missing = sorted(entry.caught_in - sites.get(name, set()))
        assert not missing, f"{name}: TRIAGE 가 잡는다고 한 모듈에 `except {name}` 이 없다: {missing}"


def test_handled_classes_have_a_registered_handler():
    sites = handler_sites()
    for name, entry in TRIAGE.items():
        if entry.kind == HANDLER:
            assert sites.get(name), f"{name}: 처리기가 있다고 했는데 `exception_handler({name})` 가 없다"


def _allowed(module: str, allowed: frozenset[str]) -> bool:
    return any(module == a or (a.endswith("/") and module.startswith(a)) for a in allowed)


def test_entry_points_stay_where_the_triage_says():
    refs = reference_sites()
    for name, entry in TRIAGE.items():
        for symbol, allowed in entry.reach.items():
            used = refs.get(symbol, set())
            assert used, f"{name}: 근거로 적은 `{symbol}` 을 앱에서 찾지 못했다(이름이 바뀌었나)"
            outside = sorted(m for m in used if not _allowed(m, allowed))
            assert not outside, (
                f"{name}: `{symbol}` 을 TRIAGE 가 모르는 모듈이 부른다: {outside}. "
                "그 자리가 요청 경로면 거기서 잡거나 예외를 AppError 로 만든다."
            )


def _test_exists(ref: str) -> bool:
    path, _, test_name = ref.partition("::")
    file = ROOT / path
    if not file.is_file():
        return False
    tree = ast.parse(file.read_text(encoding="utf-8"))
    return any(
        isinstance(node, ast.FunctionDef) and node.name == test_name for node in ast.walk(tree)
    )


def test_every_triage_names_its_reason_and_request_reachable_ones_carry_a_proof():
    kinds = {CAUGHT, HANDLER, GUARD, WORKER, HELPER, CLI, STARTUP}
    for name, entry in TRIAGE.items():
        assert entry.kind in kinds, f"{name}: 모르는 분류 {entry.kind!r}"
        assert entry.why.strip().endswith("."), f"{name}: 근거는 끝난 문장으로 적는다"
        if entry.kind in REQUEST_REACHABLE:
            assert entry.proof, f"{name}: 요청이 닿는 분류({entry.kind})인데 근거 시험이 없다"
        if entry.kind in (WORKER, HELPER, CLI, STARTUP) and not entry.proof:
            assert entry.reach, f"{name}: 요청 밖이라는 근거(`reach`)도 시험도 없다"
        gone = [ref for ref in entry.proof if not _test_exists(ref)]
        assert not gone, f"{name}: 근거로 댄 시험이 없다: {gone}"


# ── 훑기 자체를 믿어도 되는가 (알려진 참 · 알려진 거짓) ─────────────────────────


def _planted(tmp_path: Path) -> Path:
    root = tmp_path / "app"
    (root / "pkg").mkdir(parents=True)
    (root / "core.py").write_text(
        "class AppError(Exception):\n    pass\n"
        "class ConflictError(AppError):\n    pass\n",
        encoding="utf-8",
    )
    (root / "pkg" / "domain.py").write_text(
        "from app.core import AppError, ConflictError\n"
        "import httpx\n"
        "class Boom(ValueError):\n    pass\n"
        "class Bigger(Boom):\n    pass\n"
        "class Fine(ConflictError):\n    pass\n"
        "class AlsoFine(Fine, RuntimeError):\n    pass\n"
        "class Upstream(httpx.HTTPError):\n    pass\n"
        "class NotAnError:\n    pass\n"
        "def go(flag):\n"
        "    if flag:\n        raise Boom('x')\n"
        "    try:\n        raise core.Bigger\n"
        "    except (Boom, KeyError):\n        pass\n",
        encoding="utf-8",
    )
    return root


def test_the_scan_finds_a_planted_domain_exception(tmp_path):
    root = _planted(tmp_path)
    found = domain_exceptions(root)
    # 알려진 참: 내장 예외를 잇는 것 · 그 하위 · 서드파티 예외를 잇는 것.
    assert set(found) == {"Boom", "Bigger", "Upstream"}, found
    assert found["Boom"] == {"app/pkg/domain.py"}
    # 알려진 거짓: AppError 의 하위(다중 상속으로 내장 예외를 함께 이어도) · 예외가 아닌 클래스.
    assert "Fine" not in found and "AlsoFine" not in found and "NotAnError" not in found


def test_the_raise_and_except_scans_see_every_shape(tmp_path):
    root = _planted(tmp_path)
    assert raise_sites(root)["Boom"] == {"app/pkg/domain.py"}
    assert raise_sites(root)["Bigger"] == {"app/pkg/domain.py"}, "속성으로 던진 `raise core.Bigger` 를 놓쳤다"
    assert except_sites(root)["Boom"] == {"app/pkg/domain.py"}, "묶음 `except (A, B)` 를 놓쳤다"
    assert "NotAnError" not in raise_sites(root)


def test_the_reference_scan_ignores_comments_and_docstrings(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    (root / "a.py").write_text('"""make_engine 을 부르지 않는다."""\n# make_engine 도 아니다\n', encoding="utf-8")
    (root / "b.py").write_text("from app.core.db import make_engine\nmake_engine('x')\n", encoding="utf-8")
    assert reference_sites(root)["make_engine"] == {"app/b.py"}
