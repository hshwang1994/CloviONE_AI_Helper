"""배포 배선이 **파일을 다시 쓰는 사람에 의해 조용히 사라지지 않게** 고정한다.

## 왜 이 파일이 있나

특권 헬퍼(§S)의 systemd 유닛을 만들고 설치/롤백 스크립트에 배선했는데, 같은 시간에 다른
작업자가 그 스크립트들을 **다시 쓰면서 배선 세 곳이 통째로 사라졌다.** 유닛 파일은 남았지만
아무도 설치하지 않고 아무도 띄우지 않는 유닛이 됐다 - 즉 §S 전체가 배포되지 않는 상태였다.

사라진 것을 사람이 알아채기까지 한참 걸렸다(우연히 grep 해 봐서 알았다). 파일을 지키는 것이
아니라 **성질을 지켜야** 다시 사라지지 않는다.

## 여기서 검사하지 않는 것

이 검사는 "스크립트가 그 이름을 언급한다" 까지다. 실제로 설치되는지는 리눅스에서 돌려야
안다. 그걸 이 검사가 하는 척하지 않는다 - 다만 **통째로 빠진 것**은 확실히 잡는다.
"""

from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]
INSTALL = ROOT / "scripts" / "install-clovirone-web-assistant.sh"
ROLLBACK = ROOT / "scripts" / "rollback-clovirone-web-assistant.sh"
BACKUP = ROOT / "scripts" / "backup-clovirone-web-assistant.sh"
WEB_UNIT = ROOT / "deploy" / "systemd" / "clovirone-web-assistant.service"
HELPER_UNIT = ROOT / "deploy" / "systemd" / "clovirone-privhelper.service"


def _text(path: pathlib.Path) -> str:
    assert path.is_file(), f"없는 파일이다: {path}"
    return path.read_text(encoding="utf-8")


def test_the_helper_unit_exists_and_runs_as_root():
    """헬퍼의 존재 이유가 root 권한이다. 아니면 /etc 를 못 쓴다."""
    text = _text(HELPER_UNIT)
    assert "User=root" in text, "헬퍼가 root 로 돌지 않으면 시스템 설정을 못 바꾼다"
    assert "app.sysops.helper" in text, "헬퍼가 우리 모듈을 실행하지 않는다"


def test_the_helper_can_write_the_places_its_actions_touch():
    """액션 표가 건드리는 경로가 `ReadWritePaths` 에 없으면 **런타임에** 조용히 실패한다."""
    text = _text(HELPER_UNIT)
    rw = next((ln for ln in text.splitlines() if ln.startswith("ReadWritePaths=")), "")
    assert rw, "헬퍼에 ReadWritePaths 가 없다"
    for needed in ("/etc/hosts", "/etc/systemd", "/etc/ssl/clovirone"):
        assert needed in rw, f"액션이 쓰는 경로가 빠졌다: {needed} / 실제: {rw}"


def test_the_web_unit_keeps_its_hardening():
    """🔴 헬퍼를 만든 이유가 **이 하드닝을 풀지 않기 위해서**다.

    누군가 편하자고 이 줄을 지우면 §S 전체가 무의미해진다(웹을 뚫은 사람이 곧 root 다).
    """
    text = _text(WEB_UNIT)
    for line in ("NoNewPrivileges=true", "ProtectSystem=strict", "ProtectHome=true"):
        assert line in text, f"웹 유닛의 하드닝이 사라졌다: {line}"


def test_the_web_unit_tolerates_a_missing_helper_socket():
    """헬퍼를 안 깐 설치에서도 웹은 떠야 한다.

    `ReadWritePaths` 에 없는 경로를 `-` 없이 적으면 **유닛이 시작에 실패**한다. 시스템 설정
    기능 하나 때문에 서비스가 통째로 안 뜨는 것은 맞바꿀 수 없는 거래다.
    """
    text = _text(WEB_UNIT)
    rw = next((ln for ln in text.splitlines() if ln.startswith("ReadWritePaths=")), "")
    assert rw, "웹 유닛에 ReadWritePaths 가 없다"
    assert "/run/clovirone-web-assistant" in rw, (
        f"소켓 디렉터리가 웹 유닛에 없다: {rw}"
    )
    assert "-/run/clovirone-web-assistant" in rw, (
        f"`-`(없으면 넘어감)가 없다 - 헬퍼 없는 설치에서 웹이 안 뜬다: {rw}"
    )


def test_the_installer_actually_installs_the_helper():
    """🔴 유닛 파일만 있고 설치 스크립트가 모르면 **아무도 띄우지 않는 유닛**이 된다."""
    text = _text(INSTALL)
    assert "clovirone-privhelper.service" in text, (
        "설치 스크립트가 특권 헬퍼 유닛을 모른다 - §S 가 배포되지 않는다"
    )
    assert "systemctl enable clovirone-privhelper" in text, (
        "헬퍼를 enable 하지 않는다 - 재부팅하면 시스템 설정 기능이 사라진다"
    )


def test_the_installer_installs_and_enables_the_conversational_worker_unit():
    """D-118 — 같은 사고 부류다: 유닛 파일만 repo 에 있고 설치 스크립트가 모르면
    이 레인은 절대 배포되지 않는다. `worker_conversational_lane_enabled`가 꺼져
    있으면(기본값) 그 프로세스는 안전하게 곧장 종료하도록 `app/worker_main.py`가
    이미 보장한다 — 그래서 이 유닛은 배치 워커처럼 **항상** 설치·enable해도 된다."""
    text = _text(INSTALL)
    assert "clovirone-web-worker-conversational.service" in text, (
        "설치 스크립트가 대화형 레인 유닛을 모른다 - Phase 2가 배포되지 않는다"
    )
    assert "systemctl enable clovirone-web-assistant.service clovirone-web-worker.service clovirone-web-worker-conversational.service" in text, (
        "대화형 레인 유닛을 enable하지 않는다 - 재부팅하면 설정을 켜도 그 레인이 안 뜬다"
    )
    assert "systemctl restart clovirone-web-worker-conversational.service" in text, (
        "배포할 때마다 최신 코드/설정으로 재시작하지 않는다"
    )


def test_the_installer_prepares_the_certificate_directory():
    """인증서 교체 액션이 쓰는 자리를 설치가 만들어 두지 않으면 첫 교체가 실패한다.

    `SYS-03`: 예전엔 `/etc/ssl/clovirone`만 확인해서, **nginx가 실제로 읽는 자리**
    (`$ETC_DIR/tls`, `deploy/nginx/clovirone-web-assistant.conf`)가 설치 스크립트에
    있는지는 아무도 안 지켰다 — SYS-01이 실서버에서 재현한 "조용한 무동작"이 바로 그
    갭이었다. `/etc/ssl/clovirone`는 여전히 확인한다 — `TLS_CERT_PATH`가 없는 설치
    (dev/test)의 폴백 경로로 `app/sysops/actions_service.py::_resolve_tls_paths_for`가
    아직 쓰므로 지우면 그 경로에서도 폴백이 없다는 거짓 안전감이 된다. 두 경로를 **함께**
    확인해야 "인증서 디렉터리가 준비됐다"는 이 시험의 이름이 실제로 뜻하는 바를 지킨다.
    """
    text = _text(INSTALL)
    assert "/etc/ssl/clovirone" in text, "TLS_CERT_PATH 없는 설치의 폴백 디렉터리를 안 만든다"
    assert '"$ETC_DIR/tls"' in text, "nginx가 실제로 읽는 인증서 디렉터리($ETC_DIR/tls)를 안 만든다"


def test_uninstall_removes_the_helper_too():
    """제거했는데 root 데몬이 남아 있으면 그것 자체가 사고다."""
    text = _text(ROLLBACK)
    assert "clovirone-privhelper" in text, "제거 스크립트가 헬퍼를 모른다 - root 데몬이 남는다"


def test_the_installer_has_no_customer_specific_defaults():
    """P1 - 다른 고객사에 설치했을 때 조용히 남의 워크스페이스를 가리키면 안 된다."""
    text = _text(INSTALL)
    for leaked in ("goodmit.co.kr", "gooddi.lab"):
        assert leaked not in text, f"설치 스크립트에 고객사 고유값이 있다: {leaked}"


def test_the_helper_does_not_claim_the_apps_state_directory():
    """🔴 실제 배포에서 **워커가 기동에 실패**했다.

    `StateDirectory=clovirone-web-assistant` 를 넣었더니 systemd 가 그 디렉터리를
    **이 유닛의 User:Group 으로 chown 하고 모드를 0755 로** 맞췄다. 헬퍼는
    `User=root Group=clovirone-web` 이라 `/var/lib/clovirone-web-assistant` 가
    `root:clovirone-web 0755` 가 됐고, 그룹에 쓰기가 없어 워커(clovirone-web)가
    `worker.lock` 을 만들지 못했다:

        PermissionError: [Errno 13] Permission denied:
        '/var/lib/clovirone-web-assistant/worker.lock'

    재시작 루프에 빠져 잡 큐와 스케줄러가 통째로 멈췄다. 그 디렉터리는 앱의 것이고
    설치 스크립트가 소유권을 정한다 - 헬퍼는 거기에 아무것도 저장하지 않는다.

    이 결함은 systemd 가 있어야만 드러난다(Windows 개발 머신에는 없다). 그래서
    유닛 파일의 **선언**을 검사한다 - 그건 어디서든 읽을 수 있다.
    """
    lines = [ln.strip() for ln in _text(HELPER_UNIT).splitlines()]
    declared = [ln for ln in lines if ln.startswith("StateDirectory=")]
    assert declared == [], (
        f"헬퍼가 앱의 데이터 디렉터리를 가져간다 - 워커가 기동에 실패한다: {declared}"
    )


def test_the_helper_still_gets_its_runtime_and_log_directories():
    """오탐 방지 - 지우느라 소켓·감사 로그 자리까지 없애면 헬퍼가 아예 못 뜬다."""
    text = _text(HELPER_UNIT)
    assert "RuntimeDirectory=clovirone-web-assistant" in text, "소켓 디렉터리 선언이 없다"
    assert "LogsDirectory=clovirone-web-assistant" in text, "감사 로그 디렉터리 선언이 없다"


def test_the_installer_refuses_an_upgrade_that_would_blank_the_tenant_config():
    """🔴 실제 운영에서 난 사고를 스크립트가 막는지 본다.

    예전 코드는 Notion DB id 의 **기본값을 소스에** 들고 있었다. 그 설치의 web.env 에는
    그 값이 한 줄도 없었고, P1 으로 소스 기본값을 비우자 업그레이드 직후 **DB id 가 빈 채로**
    떴다. 티켓·문서 조회가 전부 400 이 됐는데 서비스는 `active` 라 겉으로는 성공한 배포로
    보였다 - 가장 나쁜 실패다.

    검사는 **마이그레이션보다 앞**에 있어야 한다. 뒤에 있으면 이미 스키마를 바꾼 뒤라
    멈춰도 되돌릴 것이 생긴다.
    """
    text = _text(INSTALL)
    assert "NOTION_TASKS_DATABASE_ID" in text, (
        "업그레이드가 설치처 고유값 누락을 확인하지 않는다 - 조용히 깨진 채로 뜬다"
    )
    lines = text.splitlines()
    guard_at = next(i for i, ln in enumerate(lines) if "NOTION_TASKS_DATABASE_ID" in ln)
    migrate_at = next(i for i, ln in enumerate(lines) if "alembic" in ln and "upgrade head" in ln)
    assert guard_at < migrate_at, (
        f"검사가 마이그레이션보다 뒤에 있다(검사 {guard_at}행, 마이그레이션 {migrate_at}행) "
        "- 멈춰도 이미 스키마가 바뀐 뒤다"
    )


def test_the_backup_captures_the_helper_unit():
    """DEPLOY-04: 백업이 web·worker 유닛만 담으면 롤백이 헬퍼를 되살릴 방법이 없다."""
    text = _text(BACKUP)
    assert "clovirone-privhelper.service" in text, (
        "백업이 헬퍼 유닛을 담지 않는다 - 롤백해도 시스템 설정 기능이 죽은 채로 남는다"
    )


def test_the_rollback_restores_and_restarts_the_helper_too():
    """DEPLOY-04: 예전엔 롤백이 web·worker 만 복원·재시작해 healthz 는 통과하고
    'ROLLBACK_OK'가 찍히는데, 관리 콘솔의 시스템 설정(타임존·DNS·호스트명·프록시·인증서)은
    죽은 채로 남았다 - 실패가 성공처럼 보이는 것이 가장 나쁜 결과다."""
    text = _text(ROLLBACK)
    restore_section = text.split("stop_services()")[-1].split("systemctl daemon-reload")[0]
    assert "clovirone-privhelper.service" in restore_section, (
        "복원 루프가 헬퍼 유닛 파일을 되살리지 않는다"
    )
    restart_at = _line_of_text(text, "systemctl restart clovirone-privhelper.service")
    assert restart_at is not None, "롤백이 헬퍼를 재시작하지 않는다"


def _line_of_text(text: str, needle: str):
    for idx, line in enumerate(text.splitlines()):
        if needle in line:
            return idx
    return None


def test_the_guard_only_fires_for_an_existing_install():
    """오탐 방지 - 신규 설치에서 멈추면 아무도 설치를 못 한다.

    qa-contract-change: 「기존 설치인가」 판정 근거가 SQLite 파일 존재에서 `web.env` 의
    DATABASE_URL 존재로 바뀌었다(D-187). 그 파일은 이제 없으므로 옛 판정은 **항상 «신규»** 가
    되어 안내를 통째로 건너뛴다 — 못박는 성질(무조건 막지 않는다)은 그대로다.
    """
    text = _text(INSTALL)
    assert 'IS_EXISTING' in text, (
        "기존 설치인지 판정하지 않고 무조건 막는다 - 신규 설치가 불가능해진다"
    )
    assert 'grep -qE "^DATABASE_URL=" "$ETC_DIR/web.env"' in text, (
        "판정 근거가 없다 - 무엇을 보고 «기존 설치» 라고 하는지 스크립트에 드러나야 한다"
    )
    assert 'if [ "$IS_EXISTING" = "1" ]; then' in text, (
        "판정 결과로 분기하지 않는다"
    )


def test_the_backup_captures_user_uploads():
    """BKP-01: 백업이 DB만 담으면 복원 후 게시판·팀챗·티켓·프로필 사진이 가리키는 실제
    파일이 없어 조용히 404가 난다."""
    text = _text(BACKUP)
    assert "uploads.tar.gz" in text and "VAR_DIR/uploads" in text, (
        "백업이 uploads 디렉터리를 담지 않는다 - 복원해도 첨부 파일 자체가 없다"
    )


def test_the_rollback_restores_uploads():
    """BKP-01: 복원 루프가 uploads.tar.gz를 풀고, OPS-01/OPS-02와 같은 소유권 드리프트가
    재발하지 않도록 명시적으로 chown해야 한다."""
    text = _text(ROLLBACK)
    assert "uploads.tar.gz" in text, "롤백이 uploads 백업을 복원하지 않는다"
    restore_section = text.split("uploads.tar.gz")[-1]
    assert "chown" in restore_section and "clovirone-web:clovirone-web" in restore_section, (
        "uploads 복원 뒤 소유권을 서비스 계정으로 명시하지 않는다 - OPS-01류 재발 위험"
    )


def test_the_backup_excludes_venv_and_the_rollback_recreates_it():
    """BKP-04: venv는 requirements.txt + wheelhouse(또는 온라인 pip)만 있으면 그대로
    재현되는데도 백업마다 수백MB를 그대로 반복해 담았다. 제외하는 쪽만 고치고 롤백이
    다시 만들지 않으면, 복원 직후 서비스가 venv 자체가 없어 아예 못 뜬다 — 두 가지를
    반드시 짝으로 확인한다."""
    backup_text = _text(BACKUP)
    assert "--exclude" in backup_text and "venv" in backup_text, (
        "백업이 여전히 venv를 통째로 담는다"
    )
    rollback_text = _text(ROLLBACK)
    assert "venv/bin/python" in rollback_text and "python3 -m venv" in rollback_text, (
        "롤백이 app.tar.gz 복원 뒤 venv를 다시 만들지 않는다 - 서비스가 못 뜬다"
    )
    assert "requirements.txt" in rollback_text.split("python3 -m venv")[-1], (
        "venv를 만들었는데 requirements.txt로 채우는 단계가 없다"
    )


# ── PostgreSQL 기동 순서 (D-187) ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "unit",
    [
        "clovirone-web-assistant.service",
        "clovirone-web-worker.service",
        "clovirone-web-worker-conversational.service",
    ],
)
def test_units_start_after_postgresql(unit):
    """DB 를 쓰는 유닛은 PostgreSQL 뒤에 뜬다.

    SQLite 시절에는 DB 가 파일이라 기다릴 서비스가 없었고, 그래서 이 줄이 없었다. 지금
    없으면 재부팅 때 유닛이 PG 보다 먼저 떠서 접속에 실패하고, `Restart=on-failure` 로
    몇 번 죽었다 되살아난다 — 결과적으로 복구되지만 그건 **운이지 설계가 아니다**.
    「재부팅 후 수동 명령 0회 복구」(U14)를 운에 맡기지 않는다.
    """
    text = _text(ROOT / "deploy" / "systemd" / unit)
    after = [l for l in text.splitlines() if l.startswith("After=")]
    assert after, f"{unit} 에 After= 가 없다"
    assert "postgresql.service" in after[0], (
        f"{unit} 이 PostgreSQL 을 안 기다린다: {after[0]}"
    )


@pytest.mark.parametrize(
    "unit",
    [
        "clovirone-web-assistant.service",
        "clovirone-web-worker.service",
        "clovirone-web-worker-conversational.service",
    ],
)
def test_postgresql_is_wanted_not_required(unit):
    """`Requires=` 가 아니라 `Wants=` 다.

    `Requires=` 면 PG 를 잠시 재시작하는 것만으로 이 유닛까지 함께 멈춘다. 접속이 끊긴
    동안은 앱이 재시도로 버티는 편이 낫다.
    """
    text = _text(ROOT / "deploy" / "systemd" / unit)
    wants = [l for l in text.splitlines() if l.startswith("Wants=")]
    assert wants and "postgresql.service" in wants[0], f"{unit}: {wants}"
    assert "Requires=postgresql" not in text, (
        f"{unit} 이 PG 를 Requires= 로 묶었다 — PG 재시작이 서비스를 멈춘다"
    )


def test_the_web_unit_no_longer_pins_a_single_worker():
    """`--workers 1` 고정이 풀렸는가 (D-192).

    풀린 조건(공유 rate-limit 표·advisory lock·설정 캐시 TTL)이 먼저 갖춰졌기 때문이다.
    누가 저장소를 되돌리면서 이 값만 남겨 두면 방어가 워커 수만큼 조용히 약해진다 —
    그래서 유닛 주석이 «무엇을 옮겼기에 올릴 수 있는가» 를 함께 적고 있어야 한다.
    """
    text = _text(WEB_UNIT)
    assert "--workers 1" not in text, "워커가 다시 1로 고정됐다"
    assert "rate_limit_buckets" in text and "advisory lock" in text, (
        "무엇을 옮겼기에 워커를 올릴 수 있는지가 유닛에 안 적혀 있다 — "
        "그 근거가 없으면 다음 사람이 저장소를 되돌리면서 이 값만 남긴다"
    )


# ═════════════════════════════════════════════════════════════════════════════
# S4 — deploy/install.sh (새 진입점). 위 검사들은 **옛 설치**(clovirone-web-assistant)를
# 계속 지킨다: 운영 서버가 아직 그것을 돌고 있고, 걷어내는 것은 S14(P-24)의 일이다.
# 여기부터는 새 진입점이 지켜야 하는 성질이다.
# ═════════════════════════════════════════════════════════════════════════════

INSTALL_SH = ROOT / "deploy" / "install.sh"


def _install_sh() -> str:
    return _text(INSTALL_SH)


def _code_only(text: str) -> str:
    """주석을 뺀 실행 줄만. 이 파일의 주석은 「왜 그렇게 안 하는가」를 설명하느라 금지
    패턴을 그대로 인용한다 — 그 인용까지 잡으면 검사가 자기 문서를 벌주는 셈이 된다."""
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def test_the_new_entry_point_has_every_subcommand_the_spec_names():
    """INSTALLATION.md §4 — 서브커맨드 일곱. 하나라도 빠지면 문서가 없는 명령을 안내한다."""
    text = _install_sh()
    for sub in ("install", "upgrade", "rollback", "uninstall", "verify", "version", "preflight"):
        assert f"  {sub}" in text or f"|{sub})" in text or f"{sub})" in text, f"서브커맨드가 없다: {sub}"


def test_the_stages_are_numbered_zero_through_eighteen_in_order():
    """INSTALLATION.md §5 — Stage 0~18. 번호가 빠지거나 순서가 뒤집히면 「어디서 멈췄나」가
    문서와 안 맞는다."""
    import re

    text = _install_sh()
    seen = [int(m.group(1)) for m in re.finditer(r'^  run_stage (\d+)\s', text, re.M)]
    assert seen == list(range(19)), f"Stage 번호가 0~18 순서가 아니다: {seen}"


def test_every_stage_prints_one_contract_line():
    """`STAGE_<n>_<NAME>: OK|SKIP|FAIL …` 한 줄이 계약이다 — 로그 파일을 열지 않고도
    어디서 왜 멈췄는지 판별돼야 한다(INSTALLATION.md §5)."""
    text = _install_sh()
    assert 'line="STAGE_${n}_${name}: ${verdict}"' in text, "Stage 결과 줄 형식이 바뀌었다"
    for verdict in ("OK", "SKIP", "FAIL"):
        assert f'"{verdict}"' in text or f" {verdict} " in text


def test_a_failed_stage_stops_and_says_where():
    """실패한 Stage 다음으로 넘어가면 「새 코드 + 옛 스키마」 같은 중간 상태가 남는다."""
    text = _install_sh()
    assert 'say "INSTALL_FAILED stage=$n name=$name"' in text
    assert "exit" in text.split("INSTALL_FAILED")[1][:200]


def test_the_tenant_guard_runs_before_anything_changes():
    """🔴 옛 installer 의 알려진 실패 모드(INSTALLATION.md §5)를 구조적으로 없앤다.

    옛 스크립트는 `rsync --delete` 로 /opt 를 갈아엎고 venv 를 다시 만든 **뒤에** 설정
    가드가 exit 21 을 했다. 그 순간 서버는 「새 코드 + 옛 스키마」였다. 새 설계는 그
    검사를 Stage 0 에 둔다 — 거기서 멈추면 정말로 되돌릴 것이 없다.
    """
    text = _install_sh()
    preflight = text.split("stage_0_preflight() {", 1)[1].split("\n}", 1)[0]
    assert "기존 설치를 감지했습니다" in preflight, "기존 설치 감지가 Preflight 밖에 있다"
    assert "SESSION_SECRET" in preflight, "필수 설정 검사가 Preflight 밖에 있다"
    # 그리고 Preflight 는 첫 Stage 여야 한다.
    assert text.index("run_stage 0  PREFLIGHT") < text.index("run_stage 1  APT")


def test_the_installer_installs_and_enables_every_unit():
    """유닛을 설치만 하고 enable 을 빠뜨리면 **재부팅 뒤에만** 드러난다."""
    text = _install_sh()
    units_block = text.split("stage_13_units() {", 1)[1].split("\n}", 1)[0]
    enable_block = text.split("stage_14_enable() {", 1)[1].split("\n}", 1)[0]
    assert 'for u in "${ALL_UNITS[@]}"' in units_block
    assert 'install -o root -g root -m 0644 "$APP_DIR/deploy/systemd/$u"' in units_block
    assert 'for u in "${ALL_UNITS[@]}"' in enable_block
    assert 'systemctl enable "$u"' in enable_block
    # postgresql·nginx 도 enable 대상이다 — 재부팅 뒤 수동 명령 0회가 이 Stage 의 존재 이유다.
    assert "systemctl enable postgresql" in enable_block
    assert "systemctl enable nginx" in enable_block
    # enable 되지 않은 유닛이 남으면 그 사실이 **재부팅 전에** 드러나야 한다.
    assert "notenabled" in enable_block


def test_uninstall_removes_every_unit_it_installed():
    """설치한 것만큼 지워야 한다. 남은 유닛 하나가 다음 설치를 조용히 방해한다."""
    text = _install_sh()
    block = text.split("do_uninstall() {", 1)[1].split("\n}", 1)[0]
    assert 'for u in "${ALL_UNITS[@]}"' in block
    for verb in ('systemctl stop "$u"', 'systemctl disable "$u"', 'rm -f "/etc/systemd/system/$u"'):
        assert verb in block, f"uninstall 이 {verb} 를 안 한다"
    # 데이터·백업·DB 는 --purge 없이는 지우지 않는다. 되돌릴 수 없는 일에는 문이 하나 더 있다.
    assert 'if [ "$PURGE" = 1 ]' in block
    assert "--yes" in text.split("do_uninstall() {", 1)[1][:600]


def test_the_upgrade_takes_a_snapshot_before_it_touches_anything():
    """되돌릴 지점 없이 업그레이드하지 않는다."""
    text = _install_sh()
    upgrade = text.split("  upgrade)", 1)[1].split("    ;;", 1)[0]
    assert "take_snapshot" in upgrade
    assert upgrade.index("take_snapshot") < upgrade.index("run_all_stages")
    assert "rollback --target" in upgrade, "실패했을 때 무엇을 하라는 안내가 없다"


def test_a_failed_dump_is_fatal_not_skipped():
    """🔴 예전 백업은 파일이 없으면 조용히 건너뛰고 BACKUP_OK 를 찍었다(S2 가 고쳤다).
    그 초록을 믿고 복원 계획을 세우는 것이 가장 나쁘다."""
    text = _install_sh()
    snap = text.split("take_snapshot() {", 1)[1].split("\n}", 1)[0]
    assert "pg_dump" in snap and "die " in snap, "덤프 실패가 치명적이지 않다"
    assert "pg_restore" in snap and "--list" in snap, "덤프를 읽을 수 있는지 확인하지 않는다"


def test_rollback_checks_the_snapshot_before_trusting_it():
    """손상된 백업으로 복원하면 되돌릴 수 없는 상태가 된다."""
    text = _install_sh()
    block = text.split("do_rollback() {", 1)[1].split("\n}", 1)[0]
    assert "sha256sum -c" in block, "체크섬을 확인하지 않는다"
    assert "pg_restore --clean --if-exists" in block or "--clean --if-exists" in block
    assert "do_verify" in block, "복원 뒤에 실제로 도는지 확인하지 않는다"


def test_verify_does_not_use_curl_dash_k():
    """🔴 `curl -k` 는 아무것도 증명하지 않는다 — 이름이 어긋나도, 남의 인증서여도 초록이다.
    S3 이 그 상태를 실제로 찾았다(옛 CN/SAN 을 서브하는데 설치 검증은 계속 OK)."""
    text = _install_sh()
    block = _code_only(text.split("do_verify() {", 1)[1].split("\njq_get", 1)[0])
    assert "curl -k" not in block and "--insecure" not in block
    assert "--cacert" in block, "신뢰 기준점 없이 검증한다고 말한다"
    # 이름만으로 자기 서버를 부르면 /etc/hosts 때문에 code=000 이 난다(S3 실측).
    assert "--resolve" in block
    assert "ssl_verify_result" in block


def test_stages_that_have_no_component_yet_say_skip_not_ok():
    """OK 로 찍으면 「설치했다」는 거짓말이 로그에 남는다. S22 는 전 Stage OK 를 요구하므로
    SKIP 이 남아 있으면 그때 걸린다.

    **Stage 11 은 S8 이 채웠다.** 이제 SKIP 이면 안 된다 — 저장소 Component 가 제품에
    있는데 설치가 「아직 없다」고 말하면 그것이 새로운 거짓말이다.
    """
    text = _install_sh()
    storage = text.split("stage_11_storage() {", 1)[1].split("\n}", 1)[0]
    ai = text.split("stage_12_ai() {", 1)[1].split("\n}", 1)[0]
    assert "skip " not in storage, "저장소는 S8 에서 제품에 들어왔다 — SKIP 이 남아 있으면 안 된다"
    assert "skip " in ai and "S9" in ai


def test_storage_stage_asks_the_product_not_the_shell(deploy_root=None):
    """🔴 Stage 11 이 셸에서 장치 번호를 비교하면 마운트 판정이 두 벌이 된다 (D-199 13번).

    두 벌이 되면 그중 하나가 빠진 날 로컬 디스크에 조용히 쌓인다. 파이썬 쪽은
    `scripts/check_domain_single_source.py` 가 같은 규칙을 지킨다.
    """
    text = _install_sh()
    storage = _code_only(text.split("stage_11_storage() {", 1)[1].split("\n}", 1)[0])
    assert "storage_cli status" in storage, "제품의 판정을 안 부르고 OK 를 찍는다"
    assert "storage_cli bootstrap" in storage
    assert "storage_cli units" in storage, "마운트 유닛을 제품이 만들지 않는다"
    assert "st_dev" not in storage, "셸이 장치 번호를 직접 본다 — 판정이 두 벌이 된다"
    assert "stat -c" not in storage


def test_storage_can_be_reinstalled_without_a_full_reinstall():
    """저장소를 추가한 뒤 마운트 유닛을 다시 깔 길이 있어야 한다.

    전체 재설치를 시키면 사람이 안 한다. 안 하면 **유닛 없이 도는 저장소**가 남고,
    그 설치는 재부팅 한 번에 마운트를 잃는다(INSTALLATION.md §6.1 Installer 계약).
    """
    text = _install_sh()
    assert "install|upgrade|rollback|uninstall|verify|version|preflight|storage)" in text, \
        "storage 서브커맨드가 dispatch 화이트리스트에 없다"
    assert "storage)   open_log; run_stage 11 STORAGE stage_11_storage" in text
    assert "  storage     " in text, "usage 에 안 적혀 있으면 아무도 그 명령을 모른다"


def test_every_app_unit_waits_for_the_mount():
    """🔴 웹만 기다리게 하면 워커가 마운트 전에 떠서 같은 사고를 낸다 (D-199 12번)."""
    text = _install_sh()
    storage = _code_only(text.split("stage_11_storage() {", 1)[1].split("\n}", 1)[0])
    assert 'for u in "${ALL_UNITS[@]}"' in storage, "drop-in 을 유닛 전부에 얹지 않는다"
    assert "10-storage-mounts.conf" in storage


def test_uninstall_removes_only_the_mounts_the_product_installed():
    """제품 제거가 사람이 손으로 만든 마운트까지 떼면, 같은 서버의 다른 것이 조용히
    안 보이게 된다."""
    text = _install_sh()
    block = _code_only(text.split("do_uninstall() {", 1)[1].split("\n}\n", 1)[0])
    assert "*.mount" in block, "저장소 마운트 유닛이 제거 경로에 없다"
    assert "ClovirAssist" in block, "제품이 깐 것과 아닌 것을 구별하지 않는다"


def test_a_component_that_appears_without_its_stage_is_caught():
    """INSTALLATION.md §6.1 — Component 를 넣는 Session 이 installer Stage 도 함께 넣는다.
    「나중에 설치 붙이기」를 허용하지 않으려면 검사가 있어야 한다."""
    text = _install_sh()
    assert "LANE_INDEX" in text, "색인 레인이 생겼는데 유닛이 없는 상태를 아무도 안 잡는다"
    assert 'app/ai/gateway' in text, "AI Gateway 가 생겼는데 Stage 12 가 비어 있는 상태를 안 잡는다"


def test_the_installer_waits_for_postgres_before_starting():
    """`After=postgresql.service` 는 「유닛이 active」까지만 보장한다 — 소켓이 받는 것과 다르다.
    INSTALLATION.md §6 이 S4 에 요구한 기동 시 대기다."""
    wait = ROOT / "deploy" / "wait-for-postgres.sh"
    assert wait.is_file(), "PG 준비 대기 스크립트가 없다"
    for unit in ("clovirassist-web.service", "clovirassist-worker.service",
                 "clovirassist-scheduler.service", "clovirassist-worker-conversational.service"):
        text = _text(ROOT / "deploy" / "systemd" / unit)
        assert "ExecStartPre=-/opt/clovirassist/deploy/wait-for-postgres.sh" in text, (
            f"{unit}: PG 준비를 안 기다린다"
        )


def test_the_new_web_unit_keeps_its_hardening():
    """🔴 헬퍼를 만든 이유가 **이 하드닝을 풀지 않기 위해서**다."""
    text = _text(ROOT / "deploy" / "systemd" / "clovirassist-web.service")
    for line in ("NoNewPrivileges=true", "ProtectSystem=strict", "ProtectHome=true",
                 "PrivateTmp=true", "RestrictSUIDSGID=true"):
        assert line in text, f"웹 유닛에서 하드닝이 사라졌다: {line}"


def test_the_new_web_unit_does_not_pin_a_single_worker():
    """D-192 — 공유 저장소를 먼저 만들었으므로 워커를 1로 묶을 이유가 없다."""
    text = _text(ROOT / "deploy" / "systemd" / "clovirassist-web.service")
    assert "--workers 1" not in text
    assert "--workers 4" in text


def test_the_env_file_reader_does_not_word_split():
    """옛 스크립트의 `env $(grep -v '^#' file | xargs)` 는 값에 공백이 있으면 조용히 깨졌다
    (`ALLOWED_EMAIL_DOMAINS=a.com, b.com` 한 줄이면 그렇다)."""
    text = _code_only(_install_sh())
    assert "| xargs" not in text, "값을 단어 분리하는 옛 관용이 남아 있다"
    assert "export_env_file()" in text


def test_the_entry_point_is_executable_straight_out_of_a_clone():
    """INSTALLATION.md §1 의 세 줄은 `sudo /opt/clovirassist/deploy/install.sh install …` 로
    **직접 실행**한다 — git clone 직후에 실행 비트가 없으면 그 줄이 «Permission denied» 다.

    이 저장소의 다른 셸 스크립트는 전부 0644 다(전부 `bash <script>` 로 부른다). 이 둘만
    다른 이유가 있다: 하나는 사용자가 직접 치는 첫 명령이고, 다른 하나는 systemd 가
    `ExecStartPre=` 로 직접 부른다. 후자가 0644 면 `-` 접두사 때문에 유닛은 그대로 뜨고
    **「PG 준비를 기다린다」가 아무 흔적 없이 사라진다.**
    """
    import subprocess

    out = subprocess.run(
        ["git", "ls-files", "-s", "deploy/install.sh", "deploy/wait-for-postgres.sh"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout
    assert out.strip(), "git 이 이 파일들을 모른다"
    for line in out.splitlines():
        mode, _, rest = line.partition(" ")
        assert mode == "100755", f"실행 비트가 없다: {rest.split()[-1]} (mode={mode})"
