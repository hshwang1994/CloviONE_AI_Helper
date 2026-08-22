"""git clone 설치·업데이트 경로의 계약 (P5, P6).

## 왜 이런 테스트인가

깨끗한 리눅스에서 clone -> 설치 -> 재부팅 -> 업데이트 -> 롤백을 실제로 돌려 보는 것이
가장 좋다. 이 저장소의 개발 환경(Windows)에서는 그것을 할 수 없다. 그러면 남는 선택은
둘이다: (a) 아무것도 고정하지 않는다, (b) **검사할 수 있는 것만** 고정한다.

(a) 는 실제로 한 번 대가를 치렀다 - 스크립트에서 롤백 경로가 통째로 빠진 것을 아무도
몰랐다. 그래서 (b) 를 한다. grep 수준이라도 "롤백이 있다", "신선도 검사를 지난다",
"백업이 정지 뒤에 온다" 는 사라지면 여기서 걸린다.

**한계를 분명히 적어 둔다**: 이 파일은 스크립트가 그 일을 *하려고 한다*는 것만 본다.
실제 서버에서 그 일이 *되는지*는 보지 못한다. 유일한 예외가
`test_migration_risk_*` 인데, 거기서는 스크립트 안의 실제 함수 본문을 꺼내 실행해서
판정이 맞는지 본다(어림짐작 자체가 헛것이면 경고가 영영 안 뜨기 때문이다).
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import textwrap

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]
UPDATE = ROOT / "scripts" / "update-from-git.sh"
INSTALL = ROOT / "scripts" / "install-clovirone-web-assistant.sh"
NGINX = ROOT / "deploy" / "nginx" / "clovirone-web-assistant.conf"

BASH = shutil.which("bash")


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _without_comments(text: str) -> str:
    """주석을 지운 사본.

    이 저장소는 주석을 한국어로 길게 쓴다. 그래서 "limit_req 를 일부러 안 건다" 같은
    설명이 그대로 grep 에 걸려, 실제로는 없는 지시자를 있다고 읽게 된다. 실제로 이
    파일을 처음 쓸 때 그 오탐으로 통과할 뻔했다.
    """
    out = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out.append(line.split(" #")[0] if " #" in line else line)
    return "\n".join(out)


def _line_of(text: str, needle: str) -> int:
    """needle 이 처음 나오는 줄 번호. 없으면 테스트를 실패시킨다."""
    for idx, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return idx
    raise AssertionError(f"찾지 못했다: {needle!r}")


# ── 스크립트가 존재하고 문법이 맞는가 ────────────────────────────────────────

@pytest.mark.parametrize("path", [UPDATE, INSTALL])
def test_script_exists(path: pathlib.Path):
    assert path.is_file(), f"{path} 가 없다"


@pytest.mark.skipif(BASH is None, reason="bash 없음")
@pytest.mark.parametrize("path", sorted((ROOT / "scripts").glob("*.sh")))
def test_bash_syntax(path: pathlib.Path):
    """bash -n 은 전부 통과해야 한다. 문법 오류는 서버에서 처음 터진다."""
    result = subprocess.run([BASH, "-n", str(path)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    assert result.returncode == 0, f"{path.name}: {result.stderr}"


def test_scripts_have_no_crlf():
    """CRLF 가 섞이면 리눅스에서 `\\r: command not found` 로 죽는다.

    install 스크립트는 첫 줄에서 스스로 CRLF 를 잡아내지만, 새 스크립트가 그 안전망
    없이 들어오는 것을 여기서 막는다.
    """
    for path in (UPDATE, INSTALL):
        assert b"\r\n" not in path.read_bytes(), f"{path.name} 에 CRLF 가 있다"


# ── 업데이트 스크립트: 있어야 하는 단계 ──────────────────────────────────────

def test_update_script_backs_up_before_installing():
    text = _read(UPDATE)
    assert "backup-clovirone-web-assistant.sh" in text, "백업 단계가 없다"
    backup_at = _line_of(text, 'BACKUP_OUT="$(bash')
    install_at = _line_of(text, 'bash "$REPO_DIR/scripts/install-clovirone-web-assistant.sh" --from-repo')
    assert backup_at < install_at, "설치가 백업보다 먼저다 - 되돌릴 지점이 없다"


def test_update_script_stops_services_before_backup():
    """백업을 먼저 뜨고 서비스를 멈추면, 그 사이에 쓰인 데이터가 롤백 때 사라진다.

    사라진 줄도 모른다는 점이 나쁘다. 순서를 테스트로 고정한다.
    """
    text = _read(UPDATE)
    stop_at = _line_of(text, "systemctl stop clovirone-web-worker.service")
    backup_at = _line_of(text, "BACKUP_OUT=")
    assert stop_at < backup_at, "백업이 서비스 정지보다 먼저다"


def test_update_script_has_a_rollback_path():
    """파일 어딘가에 스크립트 이름이 있는 것으로는 부족하다.

    이 테스트는 두 번 헛것이었다. 처음에는 파일 전체에서 이름만 찾아서, 마지막 안내
    문구 때문에 실제 호출을 지워도 통과했다. 고쳐서 rollback_now 안만 보게 했더니
    이번에는 **그 함수 안의 안내 문구**("재시도: bash ... 하십시오")에 같은 이름이
    있어서 또 통과했다. 되돌려 보지 않았으면 둘 다 몰랐다.
    그래서 출력하는 줄을 걷어내고 **실행되는 줄**만 본다.
    """
    text = _read(UPDATE)
    fn = re.search(r"^rollback_now\(\) \{.*?^\}", text, re.S | re.M)
    assert fn, "실패 처리 함수(rollback_now)가 없다"
    body = fn.group(0)
    runnable = "\n".join(
        line for line in body.splitlines()
        if not line.strip().startswith(("say ", "echo ", "#", "printf "))
    )
    assert "rollback-clovirone-web-assistant.sh" in runnable, \
        "되돌리기가 실제 복원 스크립트를 부르지 않는다(이름만 적혀 있다)"
    # 코드도 되돌려야 한다. /opt 만 되돌리고 clone 을 새 커밋에 두면 다음 실행이 어긋난다.
    assert 'reset --hard --quiet "$CURRENT_SHA"' in runnable, "저장소를 원래 커밋으로 되돌리지 않는다"


def test_update_script_rolls_back_on_verification_failure():
    text = _read(UPDATE)
    assert "readyz" in text, "readyz 를 보지 않는다 - 마이그레이션이 어긋나도 통과한다"
    assert "rollback_now \"$VERIFY_FAIL\"" in text, "검증 실패가 롤백으로 이어지지 않는다"


def test_update_script_refuses_a_dirty_clone():
    """`git reset --hard` 를 쓰기 때문에, 손으로 고친 것이 있으면 멈춰야 한다."""
    text = _read(UPDATE)
    assert "status --porcelain" in text, "작업 트리가 깨끗한지 보지 않는다"


def test_update_script_reports_version_changes_and_migrations_up_front():
    """사용자 요구: 시작할 때 버전, 변경 내역, 마이그레이션 필요 여부를 보여 준다."""
    text = _read(UPDATE)
    assert "$CURRENT_SHA:VERSION" in text and "$TARGET_SHA:VERSION" in text, "버전을 출력하지 않는다"
    assert "log --no-merges" in text, "변경 내역을 출력하지 않는다"
    assert "alembic/versions/" in text, "마이그레이션 필요 여부를 판정하지 않는다"


def test_update_script_warns_about_irreversible_migrations():
    text = _read(UPDATE)
    assert "migration_risk" in text, "되돌릴 수 없는 마이그레이션을 가려내지 않는다"
    assert "되돌릴 수 없" in text, "사용자에게 미리 말하지 않는다"


def test_update_script_supports_dry_run():
    text = _read(UPDATE)
    assert "--dry-run" in text, "무엇이 바뀔지 먼저 볼 방법이 없다"


def test_update_script_passes_the_bundle_freshness_gate_before_stopping_services():
    """신선도 검사는 서비스를 멈추기 전에 지나야 한다.

    통과 못 하는 커밋 때문에 서비스를 내렸다가 다시 올릴 이유가 없다.
    """
    text = _read(UPDATE)
    assert "check_bundle_fresh.py" in text, "번들 신선도 검사를 지나지 않는다"
    fresh_at = _line_of(text, "check_bundle_fresh.py")
    stop_at = _line_of(text, "systemctl stop clovirone-web-worker.service")
    assert fresh_at < stop_at, "서비스를 멈춘 뒤에야 신선도를 본다"


def test_update_script_does_not_gate_on_unrelated_services():
    """검증에 n8n 같은 남의 서비스를 쓰면, 무관한 이유로 멀쩡한 업데이트가 롤백된다."""
    text = _read(UPDATE)
    verify_section = text.split("# ── 7. 검증")[-1]
    # 판정 구간은 "[OK ] healthz" 를 찍기 전까지다. 그 뒤는 참고용 출력이다.
    gate = _without_comments(verify_section.split('say "[OK ] healthz')[0])
    assert "n8n" not in gate, "판정 구간에서 n8n 을 본다"
    assert "validate-clovirone-web-assistant.sh" not in gate, \
        "판정에 n8n 까지 보는 전체 검증 스크립트를 쓴다"


# ── 되돌릴 수 없는 마이그레이션 판정이 실제로 작동하는가 ─────────────────────
#
# 위의 grep 들과 달리 여기서는 **스크립트 안의 진짜 함수**를 꺼내 돌린다.
# 경고 문구만 있고 판정이 늘 "괜찮다" 를 내면, 경고는 영영 안 뜬다.

_FN_RE = re.compile(r"^migration_risk\(\) \{.*?^\}", re.S | re.M)


def _run_migration_risk(tmp_path: pathlib.Path, body: str) -> str:
    match = _FN_RE.search(_read(UPDATE))
    assert match, "update-from-git.sh 에서 migration_risk 를 찾지 못했다"
    fixture = tmp_path / "m.py"
    fixture.write_text(textwrap.dedent(body), encoding="utf-8")
    harness = tmp_path / "harness.sh"
    harness.write_text(
        "set -uo pipefail\n"
        'FIXTURE="$1"\n'
        # 진짜 함수가 git 을 부르는 자리를 픽스처 파일로 바꿔 끼운다.
        'git_repo() { cat "$FIXTURE"; }\n'
        "TARGET_SHA=deadbeef\n"
        f"{match.group(0)}\n"
        'if REASON="$(migration_risk alembic/versions/0099_x.py)"; then\n'
        '  echo "FLAGGED:$REASON"\n'
        "else\n"
        '  echo CLEAN\n'
        "fi\n",
        encoding="utf-8",
    )
    # encoding 을 못박는다. Windows 기본 cp949 로 읽으면 한국어 판정 이유에서
    # UnicodeDecodeError 가 나고, 테스트가 "실패" 로 보이는데 원인은 코드가 아니다.
    result = subprocess.run(
        [BASH, str(harness), str(fixture)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.mark.skipif(BASH is None, reason="bash 없음")
def test_migration_risk_leaves_a_reversible_migration_alone(tmp_path):
    """오탐이 나면 사람은 경고를 무시하게 된다. 되돌릴 수 있는 것은 조용해야 한다."""
    out = _run_migration_risk(tmp_path, '''
        def upgrade() -> None:
            op.add_column("users", sa.Column("nickname", sa.String(), nullable=True))


        def downgrade() -> None:
            op.drop_column("users", "nickname")
    ''')
    assert out == "CLEAN", out


@pytest.mark.skipif(BASH is None, reason="bash 없음")
def test_migration_risk_catches_an_empty_downgrade(tmp_path):
    out = _run_migration_risk(tmp_path, '''
        def upgrade() -> None:
            op.create_table("thing", sa.Column("id", sa.Integer(), primary_key=True))


        def downgrade() -> None:
            pass
    ''')
    assert out.startswith("FLAGGED:"), out


@pytest.mark.skipif(BASH is None, reason="bash 없음")
def test_migration_risk_catches_a_raising_downgrade(tmp_path):
    out = _run_migration_risk(tmp_path, '''
        def upgrade() -> None:
            op.create_table("thing", sa.Column("id", sa.Integer(), primary_key=True))


        def downgrade() -> None:
            raise NotImplementedError("한 번 올라가면 못 내려온다")
    ''')
    assert out.startswith("FLAGGED:"), out


@pytest.mark.skipif(BASH is None, reason="bash 없음")
def test_migration_risk_catches_a_dropped_column(tmp_path):
    """downgrade() 가 컬럼을 되살려도 그 안에 있던 값은 돌아오지 않는다."""
    out = _run_migration_risk(tmp_path, '''
        def upgrade() -> None:
            op.drop_column("tickets", "legacy_note")


        def downgrade() -> None:
            op.add_column("tickets", sa.Column("legacy_note", sa.String(), nullable=True))
    ''')
    assert out.startswith("FLAGGED:"), out


@pytest.mark.skipif(BASH is None, reason="bash 없음")
def test_migration_risk_catches_a_missing_downgrade(tmp_path):
    out = _run_migration_risk(tmp_path, '''
        def upgrade() -> None:
            op.add_column("users", sa.Column("nickname", sa.String(), nullable=True))
    ''')
    assert out.startswith("FLAGGED:"), out


# ── 설치 스크립트: --from-repo ───────────────────────────────────────────────

def test_install_script_accepts_from_repo():
    text = _read(INSTALL)
    assert "--from-repo" in text, "저장소에서 바로 설치하는 길이 없다"


def test_install_script_keeps_the_bundle_stage_default():
    """번들 경로는 그대로 살아 있어야 한다. 운영자들이 그 절차를 쓰고 있다."""
    text = _read(INSTALL)
    assert "/home/cloviradmin/deploy/stage" in text
    assert 'MODE=stage' in text, "기본 모드가 번들이 아니다"


def test_install_script_gates_the_bundle_freshness_in_repo_mode():
    """git 설치가 이 검사를 안 지나면, 그 서버는 조용히 옛 화면을 돈다."""
    text = _read(INSTALL)
    assert "check_bundle_fresh.py" in text, "신선도 검사를 지나지 않는다"
    assert 'if [ "$MODE" = repo ]' in text


def test_install_script_does_not_ship_repo_junk_to_production():
    """clone 에는 운영에 실리면 안 되는 것이 있다.

    `.claude` 는 에이전트 worktree 사본이다. 실제로 번들에 88벌(398MB)이 들어간 적이
    있고, 그때 진짜 문제는 용량이 아니라 서버에서 어느 코드가 도는지 알 수 없어진 것이었다.
    """
    text = _read(INSTALL)
    for junk in ("node_modules", ".claude", ".pytest_cache"):
        assert f"--exclude '{junk}'" in text, f"{junk} 를 빼지 않는다"


def test_install_script_refuses_to_install_over_its_own_clone():
    text = _read(INSTALL)
    assert '"$SRC_DIR" = "$APP_DIR"' in text, "자기 자신을 덮어쓰는 배치를 막지 않는다"


def test_install_script_says_what_the_network_needs_when_offline_wheels_are_missing():
    """폐쇄망 고객이 있다. 어디로 나가는지 모른 채 몇 분 매달렸다가 죽는 것이 가장 나쁘다."""
    text = _read(INSTALL)
    assert "pypi.org" in text and "files.pythonhosted.org" in text


# ── nginx (P6) ──────────────────────────────────────────────────────────────

def _nginx_block(text: str, header: str) -> str:
    start = text.index(header)
    depth = 0
    for idx in range(start, len(text)):
        if text[idx] == "{":
            depth += 1
        elif text[idx] == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]
    raise AssertionError(f"블록이 닫히지 않았다: {header}")


def test_nginx_enables_gzip_for_proxied_responses():
    """gzip on 만 켜면 조용히 아무것도 압축되지 않는다.

    이 vhost 의 본문은 전부 proxy_pass 로 오는데 nginx 의 gzip_proxied 기본값이 off 다.
    오류도 경고도 안 난다 - 그냥 안 듣는다.
    """
    text = _read(NGINX)
    assert re.search(r"^\s*gzip on;", text, re.M), "gzip 이 꺼져 있다"
    assert re.search(r"^\s*gzip_proxied\s+any;", text, re.M), "gzip_proxied 가 없다(압축이 안 된다)"
    assert re.search(r"^\s*gzip_vary on;", text, re.M), "gzip_vary 가 없다(캐시가 잘못 섞인다)"
    # text/html 은 nginx 가 항상 압축한다. gzip_types 에 적으면 경고가 뜬다.
    types = re.search(r"gzip_types(.*?);", text, re.S)
    assert types, "gzip_types 가 없다"
    assert "text/html" not in types.group(1)
    for mime in ("application/javascript", "text/css", "application/json"):
        assert mime in types.group(1), f"{mime} 를 압축하지 않는다"


def test_nginx_rate_limits_are_defined_and_actually_applied():
    """존만 정의하고 안 걸면 아무 일도 일어나지 않는다. 실제로 흔한 실수다."""
    text = _read(NGINX)
    assert "limit_req_zone" in text, "속도 제한 존이 없다"
    assert re.search(r"limit_req\s+zone=clv_api", text), "일반 경로에 제한이 걸려 있지 않다"
    assert re.search(r"limit_req\s+zone=clv_login", text), "로그인 경로에 제한이 걸려 있지 않다"
    assert "limit_req_status 429;" in text, "기본 503 이면 과부하와 구분되지 않는다"


def test_nginx_does_not_rate_limit_static_assets():
    """첫 화면 한 번에 자산 열 개 남짓이 동시에 나간다.

    거기에 제한을 걸면 새로고침 한 번에 몇 개가 429 로 떨어지고, 화면은 깨져 보이는데
    서버 로그에는 오류가 없다.
    """
    block = _without_comments(_nginx_block(_read(NGINX), "location /static/ {"))
    assert "limit_req" not in block, "정적 자산에 속도 제한이 걸려 있다"


def _upload_route_patterns() -> list[str]:
    """앱이 「업로드 라우트」로 아는 경로 전부. **목록을 여기 다시 적지 않는다.**

    손으로 적으면 새 업로드 라우트가 생긴 날 이 시험만 옛 목록을 보고 통과한다 —
    그리고 그 라우트는 「10MB 까지 올릴 수 있습니다」라고 말해 놓고 256k 에서 413 을
    낸다. `app/core/middleware.py` 의 주석이 그 반복을 이미 한 번 겪었다고 적어 뒀다.
    """
    from app.core.middleware import _UPLOAD_ROUTE_RES

    return [rx.pattern for rx in _UPLOAD_ROUTE_RES]


#: 제품 vhost. `NGINX` 는 옛 slug 설치가 쓰는 파일이고(S14 가 걷어낸다), 새 설치는
#: `deploy/install.sh` Stage 16 이 이쪽을 깐다. 업로드 경로 계약은 **제품 쪽**을 본다.
NGINX_PRODUCT = ROOT / "deploy" / "nginx" / "clovirassist.conf"


def test_nginx_raises_the_body_limit_for_every_upload_route():
    """🔴 앱만 올리고 nginx 를 안 올리면 운영에서만 413 이 난다(방어 이중화)."""
    text = _read(NGINX_PRODUCT)
    patterns = _upload_route_patterns()
    assert len(patterns) >= 5, "업로드 라우트 목록을 못 읽었다"
    for pattern in patterns:
        header = f"location ~ {pattern} {{"
        assert header in text, f"nginx 에 {pattern} 예외가 없다 — 운영에서 413 이 난다"
        block = _without_comments(_nginx_block(text, header))
        assert "client_max_body_size 12m" in block, f"{pattern} 의 상한이 12m 이 아니다"


def test_nginx_does_not_rate_limit_uploads():
    """10MB 업로드가 속도 제한에 걸려 중간에 끊기면 원인을 찾기 어렵다."""
    text = _read(NGINX_PRODUCT)
    for pattern in _upload_route_patterns():
        header = f"location ~ {pattern} {{"
        block = _without_comments(_nginx_block(text, header))
        assert "limit_req" not in block, f"{header} 에 제한이 걸려 있다"


def test_nginx_login_limit_is_looser_than_the_app_limit():
    """앱 리미터(분당 10회)보다 조이면, 사용자는 앱의 한국어 안내 대신 맨 429 를 받는다.

    무엇이 잘못됐는지 화면에서 알 수 없게 된다.
    """
    match = re.search(r"zone=clv_login:\d+m\s+rate=(\d+)r/m", _read(NGINX))
    assert match, "로그인 존의 속도를 읽지 못했다"
    assert int(match.group(1)) > 10, "nginx 제한이 앱 제한(분당 10회)보다 빡빡하다"


def test_nginx_keeps_what_was_already_good():
    """지시: TLS, 보안 헤더, 업로드 상한은 그대로 둔다."""
    text = _read(NGINX)
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in text
    assert "add_header X-Frame-Options DENY always;" in text
    assert "add_header X-Content-Type-Options nosniff always;" in text
    assert "client_max_body_size 256k;" in text
    assert text.count("client_max_body_size 12m;") == 4
    assert "client_max_body_size 8m;" in text


def test_nginx_has_its_own_log_files_and_a_rotation_owner():
    """로그가 n8n 과 한 파일에 섞이면, 있어도 못 읽는다."""
    text = _read(NGINX)
    assert "clovirone-web-assistant.access.log" in text
    assert "clovirone-web-assistant.error.log" in text
    logrotate = ROOT / "deploy" / "nginx" / "logrotate-clovirone-web-assistant"
    assert logrotate.is_file(), "회전 설정 파일이 없다"
    install_text = _read(INSTALL)
    # ⚠️ 배포판 nginx 설정이 /var/log/nginx/*.log 를 이미 회전시킨다. 둘 다 있으면
    # logrotate 가 duplicate log entry 로 그 실행 전체를 실패시킨다.
    assert "/etc/logrotate.d/nginx" in install_text, "중복 회전을 확인하지 않는다"
