`SRS.md` 와 `SCREENS.md` 를 읽고 **네 역할의 설계 산출물**을 만든다.
결정한 것과 그 이유를 함께 적어, 다음 단계가 그대로 구현할 수 있게 한다.

## 디자이너라면

`design-tokens.json` — 이 가게에 맞는 색을 고른다. 기본 파랑을 쓰지 마라.
주문서의 업종과 톤&매너를 보고 정한다 (빵집 + 따뜻한 느낌 → 베이지·브라운·크림).

```json
{
  "color": {
    "primary":"#...", "primary-dark":"#...", "accent":"#...",
    "bg":"#...", "surface":"#...", "text":"#...", "text-dim":"#...",
    "border":"#...", "danger":"#..."
  },
  "space": {"xs":"4px","sm":"8px","md":"16px","lg":"24px","xl":"40px"},
  "radius": {"sm":"6px","md":"10px","pill":"999px"},
  "font": {
    "family":"system-ui, 'Noto Sans KR', sans-serif",
    "size":{"sm":"0.9rem","base":"1rem","lg":"1.25rem","h2":"1.5rem","h1":"2rem"},
    "weight":{"regular":400,"bold":700}
  },
  "shadow": {"card":"0 2px 8px rgba(0,0,0,.08)"}
}
```

- **8색 확정** (BRIEF §11). 본문/배경 대비는 4.5:1 이상이어야 한다.
- `UI-GUIDE.md` — 각 화면의 배치를 글로 설명한다. 버튼·카드·폼의 규칙을 정한다.

## DBA라면

`schema.sql` — `users` 는 PK·UNIQUE·created_at 까지 완성한다.
주문서의 기능에 필요한 테이블을 전부 만든다 (상품·장바구니·문의 등).
외래키와 인덱스를 빠뜨리지 마라.

## 백엔드라면

`api-contract.yaml` — SCREENS 의 화면마다 필요한 엔드포인트를 정의한다.
각 엔드포인트에 **요청·응답 예시 JSON** 을 붙인다. 응답 형식은 공통 규격을 따른다.

## 인프라라면

`ops/run.sh` — 인터넷 없이 띄우는 절차. `DEPLOY.md` 에 확인 방법을 적는다.
