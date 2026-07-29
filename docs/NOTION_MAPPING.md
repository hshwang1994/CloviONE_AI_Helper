# NOTION MAPPING — 이메일 ↔ Notion People 매핑 (spec §12)

"내 티켓 보여줘" 같은 본인 기준 요청을 처리하려면 로그인 계정이 Notion 워크스페이스의
People 사용자와 연결되어야 한다. 매핑 키는 **로그인 이메일 = Notion People 이메일**이다.

## 설계 원칙 (spec §12.3)

- 웹 앱은 **Notion 토큰을 보유하지 않는다.** Notion 조회는 승인된 n8n workflow를 통해서만
- 이메일 문자열을 People 속성 값으로 보내지 않는다 — 반드시 Notion **user id**로 해석 후 사용
- Notion user id는 **브라우저에서 절대 받지 않는다.** id의 출처는
  ① 매핑 workflow의 응답, ② 관리자의 명시적 수동 입력(형식 검증) 둘뿐이다
- 조회된 id는 `user_notion_mappings`에 캐시되고, 화면에는 마스킹(`앞4…뒤4`)되어 표시된다

## 예약 workflow: `notion-user-mapping`

Workflow Registry에 정확히 이 이름으로 등록된 workflow가 매핑 조회를 담당한다
(`app/notion_mapping/service.py`의 `MAPPING_WORKFLOW_NAME`). 등록되지 않았거나
비활성이면 검증은 항상 unmapped + "Workflow가 구성/활성화되지 않았습니다"로 끝난다.

### 요청 (웹 → n8n)

```json
{ "action": "lookup_user", "email": "hong@goodmit.co.kr" }
```

### 기대 응답

```json
{
  "matches": [
    { "notion_user_id": "abcd1234-....", "notion_email": "hong@goodmit.co.kr" }
  ]
}
```

n8n 쪽 구현 요건: 주어진 이메일과 일치하는 Notion People 사용자를 찾아 `matches`
배열로 반환한다. 0건이면 빈 배열, 동명 이메일 등으로 복수면 모두 반환한다.

## 상태 모델

| status | 의미 | 전이 |
|---|---|---|
| `unmapped` | 미연결 (초기값, 또는 조회 결과 0건) | 검증 성공 시 verified |
| `verified` | 연결 완료 — id 캐시됨, source는 `workflow` 또는 `manual` | unmap 시 unmapped |
| `conflict` | 조회 결과 2건 이상 — 후보가 `candidates_json`에 저장됨 | 관리자 해결 시 verified |

조회 자체가 실패(n8n 다운 등)하면 상태는 유지하고 `error_message`에
`매핑 조회 실패: <예외타입>`만 기록한다. `last_verified_at`으로 최신성 확인.

## 검증(verify) 흐름

- 트리거: 관리자 콘솔 Notion 매핑 → **재검증**,
  `POST /api/admin/users/{id}/notion-mapping/verify`,
  `POST /api/admin/notion-mapping/{user_id}/verify`, CLI `verify-notion <email>`
- 처리: 매핑 workflow 호출(timeout 30s) → matches 개수에 따라
  1건=verified(id/email 캐시), 0건=unmapped, 2건 이상=conflict(후보 저장)

## 관리자 해결 (admin+)

| 작업 | API | 비고 |
|---|---|---|
| 수동 매핑 | `POST /api/admin/notion-mapping/{user_id}/map` | `notion_user_id` 형식 `^[A-Za-z0-9-]{8,64}$` 검증, source=manual |
| 충돌 해결 | `POST /api/admin/notion-mapping/{user_id}/resolve-conflict` | **저장된 후보 목록에 있는 id만** 선택 가능 |
| 해제 | `POST /api/admin/notion-mapping/{user_id}/unmap` | id/이메일/후보 모두 삭제, unmapped로 |

## 미매핑 사용자의 안전 거절 (safe-refusal)

`chat_message` 핸들러는 n8n 호출 **전에** 다음을 검사한다:

1. 메시지가 1인칭 요청인가 — 정규식: `내 (티켓|프로젝트|담당|업무|작업)`, `나의`,
   `제 (티켓|프로젝트)`, `my ticket|project` (`is_first_person_request`)
2. 요청자의 매핑 상태가 `verified`가 아닌가

둘 다 참이면 n8n을 호출하지 않고, "계정이 아직 Notion 사용자와 연결되지 않아 본인 기준
조회를 수행할 수 없습니다. 관리자에게 Notion 매핑을 요청해 주세요"라는 assistant
메시지로 즉시 응답한다(structured payload에 `{"unsupported": true, "reason":
"notion_unmapped"}`). 요청자가 아무에게도 해석되지 않은 채 n8n으로 흘러가
잘못된 사람의 데이터가 조회되는 사고를 원천 차단하기 위함이다.

1인칭이 아닌 일반 조회("진행 중 전체 티켓")는 매핑 없이도 정상 처리된다.

## 운영 절차 요약

1. n8n에 `notion-user-mapping` webhook workflow를 만들고 위 요청/응답 계약을 구현
2. Workflow Registry에 같은 이름으로 등록(URL은 workflows allowlist에 추가) + 활성화
3. 신규 사용자 생성 후 Notion 매핑 섹션에서 재검증 → verified 확인
4. conflict 발생 시 후보 중 올바른 사용자를 선택해 해결
5. 퇴사/계정 정리 시 unmap (계정 비활성화와 별개)
