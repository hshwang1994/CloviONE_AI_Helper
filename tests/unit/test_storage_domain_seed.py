"""마이그레이션에 얼려 둔 Storage 값이 **코드의 표와 같은가** (S8 · 0004 와 같은 관용).

마이그레이션은 앱 코드를 import 하지 않는다 — 그 시점 스키마의 얼어붙은 스냅숏이어야
하기 때문이다. 그래서 어휘가 두 곳에 적히고, **두 곳에 적힌 값이 어긋나면 조용히 깨진다**:

  * 코드에 저장소 종류를 하나 늘리고 마이그레이션의 CHECK 를 안 고치면 → 새 종류가
    DB 에서 거절된다. 오류 메시지는 제약 이름뿐이라 아무도 원인을 못 찾는다.
  * 역할을 늘리고 CHECK 를 안 고치면 → 백업 저장소를 못 만든다. 그런데 화면에는
    「저장 실패」로만 보인다.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from sqlalchemy import inspect, text

from app.storage.adapters import KINDS, ROLES

pytestmark = pytest.mark.unit

MIGRATION = (
    pathlib.Path(__file__).resolve().parents[2]
    / "alembic" / "versions" / "0006_file_storage.py"
)


def _frozen(name: str) -> tuple[str, ...]:
    """마이그레이션이 얼려 둔 상수 튜플을 **글자로** 읽는다.

    import 하면 안 된다 — import 가 되는 순간 두 곳이 한 곳이 되고, 이 시험이 아무것도
    확인하지 않게 된다(그래도 초록이라 아무도 눈치채지 못한다).
    """
    source = MIGRATION.read_text(encoding="utf-8")
    match = re.search(rf"^{name}\s*=\s*\(([^)]*)\)", source, re.M)
    assert match, f"마이그레이션에서 {name} 을 못 찾았다"
    return tuple(re.findall(r'"([^"]+)"', match.group(1)))


def test_the_frozen_reader_is_not_vacuous():
    """이 파일의 다른 시험들이 **빈 튜플끼리 비교하며** 통과하지 않는지 먼저 본다."""
    assert len(_frozen("_KINDS")) == 3


@pytest.mark.parametrize("frozen_name,code_values", [("_KINDS", KINDS), ("_ROLES", ROLES)])
def test_every_frozen_vocabulary_matches_the_code(frozen_name, code_values):
    assert _frozen(frozen_name) == tuple(code_values), (
        f"{frozen_name} 이 코드와 다르다 — 새 값이 DB 에서 조용히 거절된다"
    )


# ── 스키마가 실제로 그렇게 섰는가 ───────────────────────────────────────────


def test_every_storage_table_stands(db):
    names = set(inspect(db.get_bind()).get_table_names())
    expected = {"storage_providers", "files", "document_attachments"}
    assert expected <= names, sorted(expected - names)


def test_only_one_provider_per_role_can_be_enabled(db):
    """🔴 「업로드가 어디로 가는가」에 답이 둘이면 어제 올린 파일과 오늘 올린 파일이
    다른 장치에 있고, 그 사실은 백업을 복원할 때 처음 드러난다."""
    db.execute(text(
        "INSERT INTO storage_providers "
        "(id, name, kind, role, base_path, config_json, enabled, version, created_at, updated_at) "
        "VALUES ('p1','하나','LOCAL','OPERATIONAL','/tmp/a','{}',true,1,now(),now())"
    ))
    with pytest.raises(Exception):
        db.execute(text(
            "INSERT INTO storage_providers "
            "(id, name, kind, role, base_path, config_json, enabled, version, created_at, updated_at) "
            "VALUES ('p2','둘','LOCAL','OPERATIONAL','/tmp/b','{}',true,1,now(),now())"
        ))
    db.rollback()


def test_a_disabled_provider_may_stay_alongside_an_enabled_one(db):
    """반대쪽. 옮겨 가는 중에는 옛 저장소를 꺼서 남겨 둬야 파일을 마저 읽는다 —
    전부 거절하는 유니크 인덱스도 위 시험은 통과시킨다."""
    db.execute(text(
        "INSERT INTO storage_providers "
        "(id, name, kind, role, base_path, config_json, enabled, version, created_at, updated_at) "
        "VALUES ('p3','켠 것','LOCAL','OPERATIONAL','/tmp/a','{}',true,1,now(),now()), "
        "('p4','끈 것','LOCAL','OPERATIONAL','/tmp/b','{}',false,1,now(),now())"
    ))
    db.flush()
    db.rollback()


def test_a_remote_provider_without_a_mountpoint_is_refused_by_the_database(db):
    """가드가 물어야 할 자리를 모르는 행은 애초에 못 만든다."""
    with pytest.raises(Exception):
        db.execute(text(
            "INSERT INTO storage_providers "
            "(id, name, kind, role, base_path, config_json, enabled, version, created_at, updated_at) "
            "VALUES ('p5','원격','NFS','OPERATIONAL','/mnt/nas','{}',true,1,now(),now())"
        ))
    db.rollback()


def test_a_local_provider_with_a_mountpoint_is_refused_by_the_database(db):
    with pytest.raises(Exception):
        db.execute(text(
            "INSERT INTO storage_providers (id, name, kind, role, base_path, mount_point, "
            "config_json, enabled, version, created_at, updated_at) "
            "VALUES ('p6','로컬','LOCAL','OPERATIONAL','/tmp/a','/mnt/nas','{}',true,1,now(),now())"
        ))
    db.rollback()


def test_a_relative_base_path_is_refused_by_the_database(db):
    """상대 경로는 프로세스의 작업 디렉터리에 따라 다른 곳을 가리킨다. 웹과 워커는
    작업 디렉터리가 같다는 보장이 없다."""
    with pytest.raises(Exception):
        db.execute(text(
            "INSERT INTO storage_providers "
            "(id, name, kind, role, base_path, config_json, enabled, version, created_at, updated_at) "
            "VALUES ('p7','상대','LOCAL','OPERATIONAL','var/files','{}',true,1,now(),now())"
        ))
    db.rollback()


def test_a_provider_that_still_holds_files_cannot_be_deleted(db):
    """지울 수 있게 하면 그 행들이 어느 장치를 가리켰는지 아무도 모르게 된다."""
    db.execute(text(
        "INSERT INTO storage_providers "
        "(id, name, kind, role, base_path, config_json, enabled, version, created_at, updated_at) "
        "VALUES ('p8','보유','LOCAL','OPERATIONAL','/tmp/a','{}',true,1,now(),now())"
    ))
    db.execute(text(
        "INSERT INTO files (id, storage_provider_id, storage_key, filename, mime_type, "
        "size_bytes, checksum_sha256, created_at) "
        "VALUES ('f1','p8','ab/cd/" + "0" * 32 + ".txt','a.txt','text/plain',3,'" + "a" * 64 + "',now())"
    ))
    db.flush()
    with pytest.raises(Exception):
        db.execute(text("DELETE FROM storage_providers WHERE id = 'p8'"))
    db.rollback()


def test_the_checksum_column_refuses_a_wrong_length(db):
    """sha256 이 아닌 값이 들어오면 무결성 확인이 통째로 뜻을 잃는다."""
    db.execute(text(
        "INSERT INTO storage_providers "
        "(id, name, kind, role, base_path, config_json, enabled, version, created_at, updated_at) "
        "VALUES ('p9','체크섬','LOCAL','OPERATIONAL','/tmp/a','{}',true,1,now(),now())"
    ))
    with pytest.raises(Exception):
        db.execute(text(
            "INSERT INTO files (id, storage_provider_id, storage_key, filename, mime_type, "
            "size_bytes, checksum_sha256, created_at) "
            "VALUES ('f2','p9','ab/cd/" + "1" * 32 + "','a.txt','text/plain',3,'short',now())"
        ))
    db.rollback()


def test_deleting_a_document_removes_the_link_but_not_the_file(db):
    """CASCADE 규약은 `document_tags` 와 같다. 파일까지 지우면 같은 파일을 붙인 남의
    문서의 첨부가 조용히 깨진다."""
    from app.knowledge.models import Document, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID
    from app.storage.models import File, StorageProvider

    space = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="공간", slug="sp-cascade", owner_kind="organization"
    )
    db.add(space)
    db.flush()
    doc = Document(space_id=space.id, title="문서")
    provider = StorageProvider(
        name="첨부용", kind="LOCAL", role="OPERATIONAL", base_path="/tmp/a"
    )
    db.add_all([doc, provider])
    db.flush()
    record = File(
        storage_provider_id=provider.id, storage_key="ab/cd/" + "2" * 32,
        filename="a.txt", mime_type="text/plain", size_bytes=3, checksum_sha256="b" * 64,
    )
    db.add(record)
    db.flush()
    db.execute(text(
        "INSERT INTO document_attachments (id, document_id, file_id, sort_order, created_at) "
        f"VALUES ('a1','{doc.id}','{record.id}',1024,now())"
    ))
    db.flush()

    db.execute(text(f"DELETE FROM documents WHERE id = '{doc.id}'"))
    db.flush()
    assert db.execute(text("SELECT count(*) FROM document_attachments")).scalar_one() == 0
    assert db.execute(
        text(f"SELECT count(*) FROM files WHERE id = '{record.id}'")
    ).scalar_one() == 1
    db.rollback()
