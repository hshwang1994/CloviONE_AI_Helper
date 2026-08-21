"""조직 이름과 부서 계층이 **실제 조직** 그대로인지 (P5).

## 왜 고정하는가

0034 가 리브랜딩하면서 제품명과 조직명을 같은 것으로 취급해 조직 이름에 제품 이름
("ClovirAssist")을 써 넣었다. 화면에서 조직 이름이 나오는 자리마다 회사 이름 대신 제품
이름이 찍혔고, 사용자가 그것을 지적했다(P5). 같은 혼동이 다시 일어나기 쉬운 이유는
**둘 다 문자열이고 둘 다 브랜딩처럼 보이기 때문**이다. 그래서 둘을 함께 못박는다:

  * 조직 이름 = 굿모닝아이텍 (회사)
  * 제품 이름 = ClovirAssist (이 포털)

qa-contract-change: 옛 파일은 SQLite alembic 체인을 0037 까지 올린 뒤 0038 을 돌려 조직명 정정과 부서 계층 생성을 확인했다. 그 체인은 은퇴했고(D-189) 0038 은 이미 있는 행을 보고 움직이는 데이터 마이그레이션이라 새 설치에는 대상이 없다 — 부서 계층은 운영 데이터이므로 S13 이 이관할 때 본다. 여기서는 새 설치가 처음부터 옳은 이름을 갖는가를 상수·시드·표 세 겹으로 본다.
부서 계층(`브로드컴사업본부 > ClovirONE팀`)은 운영 데이터라 여기서 볼 것이 없다.
그 구조가 이관 후에도 그대로인지는 S13 Dry Run 의 「깨진 Relation 0」이 본다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.regression


def test_default_org_name_is_the_company_not_the_product():
    """시드 상수가 회사 이름이어야 한다 — 아니면 새 환경에서 되살아난다."""
    from app.org.constants import DEFAULT_ORG_NAME

    assert DEFAULT_ORG_NAME == "굿모닝아이텍", (
        "조직 이름 자리에 제품 이름이 들어갔다. 제품명은 app_settings 의 "
        "ui_branding.product_name 이고 별개다."
    )
    assert "Clovir" not in DEFAULT_ORG_NAME


def test_a_fresh_install_seeds_the_company_name_not_the_product(db):
    """**상수가 맞는 것과 DB 에 맞게 들어가는 것은 다르다.**

    0034 의 사고가 정확히 그 틈에서 났다 — 마이그레이션이 자기 리터럴을 들고 있었고,
    그 리터럴이 제품명이었다. 기준선도 앱 상수를 import 하지 않으므로(얼어붙은 스냅숏)
    같은 틈이 그대로 있다. 그래서 **실제로 심긴 행**을 본다.
    """
    from app.org.constants import DEFAULT_ORG_ID, DEFAULT_ORG_NAME
    from app.org.models import Organization

    org = db.execute(
        select(Organization).where(Organization.id == DEFAULT_ORG_ID)
    ).scalar_one()
    assert org.name == DEFAULT_ORG_NAME
    assert "Clovir" not in org.name, (
        f"기준선이 조직 이름 자리에 제품 이름을 심었다: {org.name!r}"
    )


def test_the_product_name_lives_somewhere_else_entirely(db):
    """제품명은 `app_settings` 에 있고 조직 표에는 없다 — 둘이 같은 자리에 있으면 또 섞인다."""
    from app.org.models import Organization

    names = {o.name for o in db.execute(select(Organization)).scalars().all()}
    assert not any("Clovir" in n for n in names), (
        f"조직 표에 제품 이름처럼 보이는 값이 있다: {names}"
    )


def test_the_default_org_slug_is_stable(db):
    """슬러그가 바뀌면 조직을 이름이 아니라 **id 로** 찾던 코드가 조용히 다른 행을 만든다."""
    from app.org.constants import DEFAULT_ORG_ID, DEFAULT_ORG_SLUG
    from app.org.models import Organization

    org = db.execute(
        select(Organization).where(Organization.id == DEFAULT_ORG_ID)
    ).scalar_one()
    assert org.slug == DEFAULT_ORG_SLUG
    assert org.slug != org.name, (
        "슬러그와 이름이 같으면 회사 이름을 바꿀 때 식별자까지 따라 바뀐다"
    )


def test_there_is_exactly_one_organization_in_a_fresh_install(db):
    """둘이면 `org_id` 기본값이 어느 쪽을 가리키는지 화면이 말해 주지 않는다."""
    from app.org.models import Organization

    orgs = db.execute(select(Organization)).scalars().all()
    assert len(orgs) == 1, f"새 설치에 조직이 {len(orgs)}개다: {[o.name for o in orgs]}"
