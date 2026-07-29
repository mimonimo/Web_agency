판정: 통과

## 수용 기준 대조 (27/27 통과)

| 기준 | 결과 | 확인 방법 |
|---|---|---|
| F-1 클래스 4개가 모두 보인다 | ✅ | `app.js` CLASSES 4건 → `#class-grid` 렌더 |
| F-1 이름·가격·소요시간·정원 표시 | ✅ | 카드에 `.price` + `.tag` 2개 |
| F-1 가격 세 자리 쉼표 | ✅ | `won()` → `toLocaleString("ko-KR")` |
| F-1 카드 → 상세 이동 | ✅ | `[data-klass]` 클릭 → `showDetail()` |
| F-1 390px 에서 세로 1열 | ✅ | `auto-fill minmax(250px,1fr)` + 640px 미디어쿼리 |
| F-2 상세에 이름·가격·시간·정원·설명 | ✅ | `showDetail()` |
| F-2 준비물 안내 | ✅ | `c.prep` 목록 |
| F-2 예약하기 → 그 클래스 선택됨 | ✅ | `#f-class.value = c.id` 후 `go("book")` |
| F-2 목록으로 복귀 | ✅ | `.btn-back` |
| F-3 미입력 시 제출 불가 | ✅ | `canSubmit()` → `#book-submit.disabled` |
| F-3 오늘 이후만 선택 | ✅ | `#f-date.min` + 제출 시 재확인 |
| F-3 월요일 차단 + 안내 | ✅ | `isMonday()` → "월요일은 휴무입니다" |
| F-3 시간대 3개 | ✅ | 10:00 / 14:00 / 19:00 |
| F-3 정원 초과 차단 + 안내 | ✅ | "정원은 N명입니다" / "남은 자리는 N명입니다" |
| F-3 연락처 9자리 미만 차단 | ✅ | `tel.replace(/\D/g,"").length < 9` |
| F-3 예약번호 `BB-YYYYMMDD-NNN` | ✅ | `nextCode()` |
| F-3 새로고침 후에도 조회 | ✅ | localStorage `byeolbit.bookings` |
| F-4 번호로 조회 성공 | ✅ | `renderCheck()` |
| F-4 없는 번호 안내 | ✅ | "그런 예약번호가 없습니다" |
| F-4 방금 예약자는 자동 입력 | ✅ | 접수 후 `#f-code.value = code` |
| F-5 문의 접수 확인 | ✅ | 목록에 즉시 추가 |
| F-5 10자 미만 차단 | ✅ | "문의 내용을 조금 더 적어 주세요" |
| F-5 문의 목록 누적 | ✅ | localStorage `byeolbit.asks` |
| 공통 viewport | ✅ | `<meta name="viewport">` |
| 공통 시맨틱 태그 | ✅ | header/nav/main/section/footer 5/5 |
| 공통 label 커버 | ✅ | label 10 / input·select·textarea 9 |
| 공통 자리표시자 없음 | ✅ | TODO·lorem 없음 |

## 화면 대조

SCREENS.md 목표 5개 / 구현 5개 (`<section>` 5개 — 목록·상세·예약·확인·문의).

## 재현해 본 것

1. 월요일(2026-08-17) 선택 → "월요일은 휴무입니다", 제출 버튼 비활성 ✅
2. 물레 체험(정원 4)에 5명 입력 → "정원은 4명입니다" ✅
3. 같은 슬롯에 2명 + 3명 연속 예약 → 두 번째에 "남은 자리는 2명입니다" ✅
4. 연락처 `0103` → "연락처를 확인해 주세요" ✅
5. 예약 후 새로고침 → 예약번호로 조회 성공 ✅

## 위험으로 남기는 것 (반려는 아님)

- 예약 취소 경로가 없다. SOW 에서 제외된 항목이므로 이번 판정에 반영하지 않는다.
- localStorage 는 브라우저마다 따로다. 다른 기기에서는 조회되지 않는다.
  SRS 의 "가정" 에 명시돼 있다.
