# 배포 안내 — 별빛공방 (S4 인프라)

## 실행 방법

```bash
bash ops/run.sh              # 기본 8080
PORT=9000 bash ops/run.sh    # 포트 바꾸기
```

인터넷 없이 동작한다. `npm install` · `pip install` 을 쓰지 않는다.

## 포트

| | |
|---|---|
| 정적 화면 | **8080** (`PORT` 로 변경) |
| API 서버 | 8080 (같은 서버가 `/api/*` 를 처리한다) |

## 확인 방법

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/          # 200
curl -s http://localhost:8080/api/classes | head -c 120                  # {"ok":true,...
```

브라우저에서 `http://localhost:8080/` 을 열어
① 클래스 4개가 보이는지 ② 예약이 접수되어 번호가 나오는지 ③ 새로고침 후에도 조회되는지.

## 되돌리는 방법

```bash
pkill -f "node server.js" || true      # 서버만 내린다
```
데이터는 브라우저 localStorage 에 있으므로 서버를 내려도 화면 확인에는 지장이 없다.

## 환경변수

| 이름 | 기본값 | 뜻 |
|---|---|---|
| `PORT` | 8080 | 듣는 포트 |

비밀번호·토큰을 파일에 하드코딩하지 않았다. 필요한 값이 없다.
