# 별빛공방 — 실행 방법

도자기 원데이 클래스 예약 사이트. 정적 화면 + 작은 API 서버.

## 띄우기

```bash
bash docs/ops/run.sh          # 기본 8080
PORT=9000 bash docs/ops/run.sh
```

`node` 가 있으면 `server.js` 가 화면과 API 를 함께 서빙한다.
없으면 `python3 -m http.server` 로 **화면만** 뜬다 —
예약은 브라우저 안(localStorage)에서 그대로 동작하므로 확인에는 지장이 없다.

**외부 패키지를 설치하지 않는다.** Node 표준 모듈(`http`/`fs`/`path`/`url`)만 쓴다.

## 확인

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/     # 200
curl -s http://localhost:8080/api/classes | head -c 120             # {"ok":true,...
```

## 엔드포인트

| method | path | 하는 일 |
|---|---|---|
| GET | `/api/classes` | 클래스 목록 |
| GET | `/api/classes/{id}` | 클래스 하나 |
| GET | `/api/slots?klassId=&date=` | 시간대별 남은 자리 |
| POST | `/api/bookings` | 예약 접수 → 예약번호 발급 |
| GET | `/api/bookings/{code}` | 예약번호로 조회 |
| POST | `/api/inquiries` | 문의 접수 |

응답은 전부 `{"ok":true,"data":…}` / `{"ok":false,"error":"…"}`.
상태코드는 200 / 400 / 404 만 쓴다.

## 서버에서 다시 검증하는 것

브라우저 검증은 개발자 도구로 우회된다. 아래는 **서버에서도** 확인한다.

- 필수값 누락, 날짜 형식
- 오늘 이전 날짜 / **월요일 휴무**
- 시간대가 10:00 / 14:00 / 19:00 인지
- 인원이 정수인지, 정원·잔여 자리를 넘지 않는지
- 연락처 숫자 9자리 이상
- 문의 본문 10자 이상
- 요청 본문 8KB 초과 시 연결 종료
- 정적 파일 경로 탈출(`..`) 차단

예기치 못한 오류는 `{"ok":false,"error":"요청을 처리하지 못했습니다"}` 로 감싸고
상세는 서버 로그에만 남긴다 — 스택 트레이스를 사용자에게 보이지 않는다.

## 데이터

지금은 메모리 배열이다 (**DB 연결 전**).
`docs/schema.sql` 대로 테이블을 만들고 `docs/seed.sql` 을 넣으면 그대로 옮겨 붙는다.
