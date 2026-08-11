/* 알림 목록 화면 설정.
 *
 * **이 파일만 따로 있는 이유는 크기가 아니라 누가 받아 가느냐다** (PF7).
 * 알림은 관리자 화면이면서 동시에 **사용자 콘솔의 화면**이다(`/notifications`). 예전에는
 * 그 하나 때문에 사용자 콘솔이 registry.js 전체를 정적으로 들여왔고, 평범한 사용자가
 * 관리자 화면 스물일곱 개의 설정을 함께 내려받았다 — 평생 열지 않을 화면들이다.
 *
 * registry.js 를 쪼갠 조각이다 (E-10). 쪼갠 축은 '줄 수'가 아니라 **관리자가 한 번에
 * 함께 보는 묶음**이다 — 줄 수를 맞추려고 아무 데나 자르면 화면 하나를 고치는 데
 * 파일 셋을 열게 되어 오히려 더 나빠진다.
 *
 * 화면 설정만 있고 그리는 코드는 없다. 그리는 것은 DataScreen.jsx 하나다.
 */
import { NOTI_SCREEN } from "../../app/notification-keys.js";
import { ADMIN_VIEW_ROLES, OBJ_ID_PARAM, OBJ_ROUTE, TYPE_KO, canReachObjRoute, col, dateCol, field, mapCol, objField, objRouteHref, opt, readCol } from "./shared.js";

/* RG-02 — 서버가 계산한 목적지(related_route, app/notifications/destinations.py)가 있으면
 * 그걸 최우선으로 쓴다. 아래 OBJ_ROUTE/OBJ_ID_PARAM(프런트의 로컬 표, 승인·작업 큐처럼
 * 목록 화면뿐인 관리자 대상용)은 서버가 아직 모르는 유형의 폴백일 뿐이다 — 팀 문서 댓글
 * (document)이 정확히 이 순서를 안 지켜서 겪은 문제였다: 서버는 `/team-docs/{id}`를
 * 계산해 주는데 이 화면이 그걸 버리고 로컬 표로 `#/documents?id=<id>`(관리 콘솔의 "문서
 * 생성" 화면, 전혀 다른 자원)를 만들어 404로 갔다. NotificationBell.jsx의 `serverRoute()`와
 * 같은 검증(내부 상대 경로만, `//`로 시작하는 프로토콜 상대 URL 거부)이지만, 벨은 이 파일을
 * import하지 않으므로(순환 의존 회피, 벨의 자체 주석 참고) 3줄을 그대로 여기 독립적으로 둔다. */
function serverHref(r) {
  const p = r && r.related_route;
  return typeof p === "string" && p.startsWith("/") && !p.startsWith("//") ? "#" + p : null;
}
// 서버가 계산해 준 유형(document/ticket/board_post/chat_room/chat_mention)은 전부 사용자
// 콘솔 화면이라 role 제한이 없다 — ADMIN_VIEW_ROLES로 가리면 안 된다(일반 사용자가 자기
// 티켓·채팅 알림에서도 못 눌리게 된다). 그래서 이 게이트는 정적 roles:가 아니라 when() 안에서,
// 서버 값이 없을 때(로컬 표의 관리자 전용 대상)만 적용한다.

export const NOTIFICATIONS_SCREEN = {
  notifications: {
    key: "notifications",
    /* 캐시 주소는 화면 키와 다르다 — 벨(`["noti","unread"]`)·팝오버 목록(`["noti","list"]`)과
       같은 뿌리를 쓴다 (PF9). 그래야 어느 쪽에서 읽음 처리를 하든 한 번의 무효화로 셋이
       함께 갱신된다. 정본은 app/notification-keys.js 다. */
    cacheKey: NOTI_SCREEN,
    area: "운영", title: "알림", endpoint: "/api/notifications",
    help: "나에게 온 알림을 확인합니다.",
    emptyTitle: "새 알림이 없습니다",
    // 일반 사용자(role=user)는 승인/작업 실패 알림을 거의 받지 않는다 → 관리자 중심 예시를 보여주지 않는다(알림 벨과 동일).
    emptyHelp: (role) => role === "user" ? "나에게 온 알림이 여기에 표시됩니다." : "승인, 작업 실패 등 나에게 온 알림이 여기에 표시됩니다.",
    paginated: true,
    // 목록 응답이 이미 unread 총합을 함께 돌려준다(app/notifications/router.py) — 벨 팝오버의
    // '안 읽음 N'과 같은 값을 이 화면에서도 그대로 보여준다(행마다 배지를 세지 않아도 되게).
    unreadCountKey: "unread",
    // 안 읽은 알림만 골라 보는 트리아지(백엔드 unread_only 쿼리).
    filters: [{ key: "unread_only", type: "select", label: "읽음 상태", options: opt([["true", "안 읽음만"]]) }],
    // 제목을 첫 열로 둔다 — DataScreen의 상세 드로어 제목(detailTitle)은 columns[0]을 쓰는데, 예전엔
    // 그게 mapCol('type')이라 같은 유형('승인 요청' 등)의 알림이 모두 같은 제목으로 열려 어느 알림을
    // 보고 있는지 구분이 안 됐다 — 각 알림의 실제 제목이 드로어 제목으로도 보이게 한다.
    columns: [col("title", "제목"), mapCol("type", "유형", TYPE_KO), readCol("read_at", "읽음"), dateCol("created_at", "시각")],
    // related_object_id는 원래 상세에서 원시 UUID로만 보여줬다 — 바로 옆 '관련 항목 보기'/'관련
    // 목록 열기' 액션 버튼이 이미 같은 id를 실제로 이동 가능한 링크로 해석해 주므로, 클릭도
    // 복사도 안 되는 평문 UUID 한 줄은 정보 없이 자리만 차지했다(drop).
    detailFields: [field("body", "내용"), objField("related_object_type", "관련 대상")],
    headerActions: [
      // unread===0이면 눌러도 항상 '0건을 읽음 처리했습니다' 무의미 토스트만 나므로, 안 읽은 알림이
      // 있을 때만 노출한다(같은 화면 상단 StatCard의 unread 값과 동일한 기준).
      { label: "모두 읽음", when: (ctx) => ctx.unreadCount > 0, path: () => "/api/notifications/read-all", confirm: "모든 알림을 읽음 처리할까요?",
        result: (res) => ({ ok: true, msg: (res && res.read_count != null ? res.read_count : 0) + "건을 읽음 처리했습니다." }) },
    ],
    actions: [
      // keepSelection은 쓰지 않는다 — POST /api/notifications/{id}/read(app/notifications/router.py
      // mark_read)는 {"ok": true}만 돌려주고 갱신된 항목(res.item)을 포함하지 않는다. DataScreen의
      // keepSelection 분기는 res.item이 있을 때만 드로어를 그 항목으로 갱신하고, 없으면 그냥
      // setSel(null)로 닫는다(runAction) — 즉 여기선 keepSelection을 켜 놔도 항상 드로어가 닫혔다.
      // 실제 동작(닫힘)과 의도가 어긋났던 것을 없앤다.
      // localPatch — 서버가 {"ok":true}만 돌려주고 갱신된 항목을 안 주므로(위 주석), 드로어를 곧장
      // 닫는 대신 read_at을 로컬에서 채워 드로어를 열어 둔 채로 '읽음' 상태를 바로 보여준다.
      { label: "읽음 처리", when: (r) => !r.read_at, path: (r) => "/api/notifications/" + r.id + "/read",
        localPatch: (r) => ({ ...r, read_at: new Date().toISOString() }) },
      // 삭제(FN-03) — 이 엔드포인트는 role이 아니라 소유권(user_id==나)으로 막는다
      // (app/notifications/router.py) — 그래서 다른 액션과 달리 roles: 를 안 준다. roles를
      // 주면 백엔드가 이미 허용하는 '자기 알림 삭제'가 일반 사용자에게만 숨겨지는 반대 방향
      // 버그가 된다. 삭제는 DataScreen이 CROSS_SCREEN_KEYS.notifications로 벨 배지/팝오버까지
      // 이미 함께 무효화한다(다른 액션과 동일 배선, shared.js 참고).
      { label: "삭제", variant: "danger", method: "DELETE", path: (r) => "/api/notifications/" + r.id,
        confirm: "이 알림을 삭제할까요? 목록에서 완전히 사라지며 되돌릴 수 없습니다." },
      // 관련 대상(승인·작업·스케줄 등 로컬 표 대상)이 있으면 해당 관리 화면으로 이동한다.
      // 로컬 표 대상은 전부 관리자 콘솔 경로라 일반 사용자(role=user)에겐 숨긴다(위 serverHref
      // 주석 참고 — 서버가 계산해 준 사용자 콘솔 대상은 이 게이트를 안 탄다).
      // ADMIN_VIEW_ROLES 통과만으로는 부족하다 — 대상 화면 중 일부(사용자·부서·직책·작업 큐)는
      // auditor 등을 추가로 제외한다(App.jsx SCREEN_ROLES) — canReachObjRoute로 실제 도달 가능할 때만 노출.
      // schedule_run은 제외한다 — '#/schedules'로 보내도 특정 실행 행을 찾아 주지 못해(스케줄
      // 화면에 그런 딥링크가 없다) 클릭해도 실제로는 아무것도 못 찾는 겉보기 기능이었다
      // (NotificationBell.jsx의 동일한 제외와 맞춘다).
      // related_object_type이 OBJ_ID_PARAM에 있으면(감사 로그 액션과 동일한 기준) 그 화면이 ?id=
      // 딥링크를 지원하므로 목록이 아니라 그 항목 하나를 직접 연다 — 라벨도 실제 동작대로 구분한다.
      { label: "관련 항목 보기",
        when: (r, ctx) => !!serverHref(r) ||
          (!!(r.related_object_type && OBJ_ROUTE[r.related_object_type] && OBJ_ID_PARAM[r.related_object_type] && r.related_object_id) &&
           ADMIN_VIEW_ROLES.includes((ctx && ctx.role) || "") && canReachObjRoute(r.related_object_type, ctx && ctx.role)),
        navigate: (r) => serverHref(r) || objRouteHref(r.related_object_type, r.related_object_id) },
      // 그 외(서버·로컬 표 둘 다 단건 딥링크를 못 주는 대상 유형, 또는 related_object_id 없음)는
      // 여전히 목록 전체로만 이동한다 — 라벨을 실제 동작대로 정직하게 알린다. schedule_run도
      // 이제 여기 포함한다 — 예전엔 따로 빼서 이 알림 유형만 클릭할 게 아무것도 없었다(스케줄
      // 화면에 실행 건별 딥링크가 없다는 이유였지만, 목록 전체로라도 보내는 게 아무 동작도 없는
      // 것보다는 낫다 — schedule_run은 OBJ_ROUTE에서 이미 '#/schedules'로 매핑돼 있다).
      { label: "관련 목록 열기",
        when: (r, ctx) => !serverHref(r) &&
          !!(r.related_object_type && OBJ_ROUTE[r.related_object_type]) && !(OBJ_ID_PARAM[r.related_object_type] && r.related_object_id) &&
          ADMIN_VIEW_ROLES.includes((ctx && ctx.role) || "") && canReachObjRoute(r.related_object_type, ctx && ctx.role),
        navigate: (r) => OBJ_ROUTE[r.related_object_type] },
    ],
  },
};
