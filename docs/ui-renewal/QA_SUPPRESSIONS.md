# QA Assertion 억제 목록

억제는 결정이 아니라 **날짜 있는 약속**이다. 행이 없으면 소스의 `data-*` 마커도 없어야 하고,
그 반대도 마찬가지다. `scripts/check_ui_renewal_coverage.py` 가 양방향 정합을 검사한다.

## 규칙

1. 소스의 억제 마커(`data-equal-grid`, `data-control-row`, `data-surface-intent`,
   `data-page-density`, `data-detail-rail`, `data-surface-set`, `data-qa-slack`,
   `data-entity-select`, `data-mascot-role`)와 이 표의 행은 1:1 이다. 어느 쪽 고아든 실패다.
2. `expires` 는 `opened` 로부터 **60일 이내**여야 한다. 지나면 실패한다.
3. 총 15행, 클래스당 2행을 넘지 않는다.
4. **억제할 수 없는 클래스**: `header_cell_alignment_mismatch`, `numeric_alignment`,
   `plain_dropdown_for_entity`, `brand_presence`.
5. `reason` 은 40자 이상이며 `임시`, `나중에`, `TODO`, `일단` 을 쓸 수 없다.
   "일단"은 억제가 아니라 `DEFERRED` 이고 Requirement Matrix 에 적는다.
6. 억제 수가 실패 수보다 많은 클래스는 QA 요약에 경고로 표시된다.

## 목록

| id | assertion | marker | surface | reason | owner | opened | expires | evidence |
|---|---|---|---|---|---|---|---|---|

(현재 0건)
