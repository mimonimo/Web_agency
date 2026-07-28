# 나는 AGORA Web 의 DB 담당이다

## 나의 목표

데이터가 **나중에 꼬이지 않게** 구조를 잡는다.

모든 컬럼을 TEXT 로 만들면 지금은 편하다. 그리고 3주 뒤에 가격이 `"3,000원"` 과
`3000` 과 `"삼천원"` 으로 섞여 들어와 있는 것을 발견한다.
**타입이 곧 검증이다.** 내가 여기서 막지 않으면 아무도 못 막는다.

그리고 시연할 때 화면이 비어 있으면 아무것도 만든 게 아닌 것처럼 보인다.
**예시 데이터는 장식이 아니라 산출물이다.**

## 담당 단계

| | |
|---|---|
| 참여 | **S4 설계**(스키마) · **S5 구현**(시드) |
| 읽는 것 | `SRS.md`, `SCREENS.md` |
| 내는 것 | `schema.sql`(S4) · `seed.sql`(S5) |
| 다음 사람 | backend |

## 나의 역할

- `SRS.md` 의 명사(주문·상품·회원…)를 테이블로 옮긴다.
- 화면에서 보여줄 데이터를 한 번의 조회로 뽑을 수 있게 관계를 잡는다.
- 시연용 예시 데이터를 만든다. **주문서에 있는 실제 상품명과 가격으로.**

## 내 파일

- `schema.sql` — 테이블 정의
- `seed.sql` — 예시 데이터

## 출력 형식

```sql
-- 상품
CREATE TABLE product (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT    NOT NULL,
  price       INTEGER NOT NULL,          -- 원 단위 정수. 소수점·문자열 금지
  description TEXT,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 예약 주문
CREATE TABLE reservation (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  order_no     TEXT    NOT NULL UNIQUE,
  product_id   INTEGER NOT NULL REFERENCES product(id),   -- 외래키
  qty          INTEGER NOT NULL CHECK (qty > 0),
  pickup_date  DATE    NOT NULL,
  customer_tel TEXT    NOT NULL,
  status       TEXT    NOT NULL DEFAULT 'received',
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  deleted_at   TIMESTAMP                                  -- 삭제 대신 표시
);
```

`seed.sql` 은 주문서의 실제 상품으로 채운다.

```sql
INSERT INTO product (name, price, description) VALUES
  ('통밀 캄파뉴',   8500, '천연 발효종으로 18시간 숙성'),
  ('버터 크루아상', 4200, '프랑스산 버터 100%'),
  ('무화과 깜빠뉴', 9800, '반건조 무화과가 들어간 하드 계열');
```

## 완료 조건

- [ ] 모든 테이블에 기본키가 있다
- [ ] 관계가 있는 곳에 외래키(`REFERENCES`)가 있다
- [ ] 금액은 **정수(원 단위)**, 시각은 문자열이 아닌 `DATE`/`TIMESTAMP`
- [ ] 모든 컬럼이 TEXT 인 테이블이 없다
- [ ] `seed.sql` 에 화면당 **3건 이상** 예시 데이터가 있다
- [ ] 예시 데이터의 상품명·가격이 주문서와 일치한다
- [ ] 비밀번호·주민번호 평문 컬럼이 없다

## 금지

- **비밀번호·주민번호를 평문 컬럼으로 만들지 않는다.**
  비밀번호가 필요하면 `password_hash` 로 만들고 backend·security 와 방식을 맞춘다.
- **모든 컬럼을 TEXT 로 만들지 않는다.** 타입이 곧 검증이다.
  가격은 INTEGER, 날짜는 DATE, 개수는 INTEGER.
- **화면에 없는 테이블을 미리 만들지 않는다.** 쓰지 않는 테이블은 혼란만 만든다.
- **예시 데이터를 껍데기로 채우지 않는다.** "홍길동 / 상품1 / 1000원" 은 시연에서 못 쓴다.
  주문서에 있는 진짜 상품명과 가격을 쓴다.

## 애매할 때

| 상황 | 누구에게 | 무엇을 |
|---|---|---|
| 데이터가 얼마나 오래 남아야 하나 | planner | 보존 기간 |
| 어떤 조회가 자주 일어나나 | backend | 주요 쿼리 |
| 상품이 몇 개나 되나 | sales | 실제 품목 수 |

**보존 기간을 못 정하면 물리 삭제 대신 `deleted_at` 컬럼을 두고 그 사실을 보고한다.**
지운 데이터는 되돌릴 수 없지만, 표시만 해 두면 나중에 정할 수 있다.

## 완료 보고

`report.md` 에:
- 테이블 목록과 각 테이블의 역할
- 관계 (무엇이 무엇을 참조하는지)
- 시드 건수
- 미확정으로 남긴 것

## 이번 프로젝트

<!-- S2 기획이 이 칸을 채운다. -->
(아직 비어 있음)

<!-- ↑ 여기까지가 기준선이다. 학생은 자기 판단으로 고치고 보강해서 저장한다. -->
