# 배포 기록 — 별빛공방 (S9 인프라)

## 실행

```
$ bash docs/ops/run.sh
화면만 → http://localhost:8080/  (node 가 없어 API 는 뜨지 않는다)
```

이 환경(dgx-12)에는 `node` 가 없어 정적 서빙 경로로 떨어졌다.
`server.js` 는 문법 검증만 마쳤고, node 가 있는 환경에서 API 까지 함께 뜬다.

## 확인

```
$ curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/
200

$ curl -s http://localhost:8080/style.css | head -c 60
/* 별빛공방 — 도자기 원데이 클래스

$ curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/app.js
200
```

AGORA Web 미리보기로도 확인했다.

```
/preview/showcase/claude-reference/index.html   → 200
/preview/showcase/claude-reference/style.css    → 200
/preview/showcase/claude-reference/app.js       → 200
```

## 되돌리기

```
$ pkill -f "http.server 8080" || true
```

## 남은 것

- `node` 설치 후 `/api/*` 왕복 확인 (지금은 화면만 검증됨)
- 실서비스 전환 시 HTTPS · rate limit (보안 판정서의 위험 2·3)
