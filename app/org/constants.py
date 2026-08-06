"""조직(organization) 고정 상수.

제품화 대비(§7.1.A)로 organizations 를 1급 엔티티로 두되, 지금은 단일 조직 한 행만 쓴다.
그 한 행의 id 를 랜덤 UUID 로 두면 마이그레이션·시드·테스트가 서로 다른 값을 보게 되므로,
채팅 '전체 방'(_GLOBAL_ROOM_ID)·문서 sync 싱글턴(SYNC_STATE_ID)과 같은 관례로 **고정 id**를 쓴다.

여기 값은 마이그레이션(0022)과 애플리케이션 코드가 공유하는 단 하나의 정의다 — 두 곳에
따로 적어 두면 반드시 어긋난다.
"""

from __future__ import annotations

# 36자(8-4-4-4-12) UUID 모양의 고정 id. 마지막 그룹에 'org1'을 넣어 DB를 눈으로 볼 때
# 바로 알아볼 수 있게 한다(chat_rooms 의 '0000cha70001' 과 같은 관례).
DEFAULT_ORG_ID = "00000000-0000-0000-0000-00000000org1"
DEFAULT_ORG_SLUG = "default"
# 실제 조직 이름. **제품명이 아니다** — 0034 가 리브랜딩하면서 둘을 같은 것으로 취급해
# 여기에 제품명("ClovirAssist")이 들어갔고, 화면에 조직 이름이 나오는 자리마다 회사 이름
# 대신 제품 이름이 찍혔다(사용자 지적 P5). 0038 이 기존 행을 고치고, 여기 상수는 새 환경
# 시드가 같은 실수를 반복하지 않게 한다 — 상수를 안 고치면 다음 시드에서 되살아난다.
#
# 제품명은 `app_settings` 의 `ui_branding.product_name` 이고 별개로 관리된다.
DEFAULT_ORG_NAME = "굿모닝아이텍"

# 조직 상태. 지금은 active 하나만 쓰지만, 제품화 때 정지/해지를 붙일 자리를 열어 둔다.
ORG_ACTIVE = "active"
ORG_SUSPENDED = "suspended"
