설계 산출물을 읽고 **실제로 동작하는 것**을 만든다.

## 시작 전에 반드시 할 것

1. `SCREENS.md` 를 읽고 **만들어야 할 화면이 몇 개인지** 센다.
2. `design-tokens.json` 을 읽고 색·간격·글자 크기를 확인한다.
3. `api-contract.yaml` / `schema.sql` 을 읽고 필드 이름을 맞춘다.

**참고 자료에 있는 것을 무시하고 새로 지어내면 반려다.**
화면이 6개라고 적혀 있는데 1개만 만들면 반려다.

## 프론트엔드라면

### ⚠️ 파일 배치 — 여기서 제일 많이 틀린다

**`output/` 바로 아래에 평평하게** 놓는다. 하위 폴더를 만들지 마라.

```
output/index.html
output/style.css
output/app.js
```

- `output/frontend/index.html` 처럼 한 겹 더 만들면 **링크가 깨진다.**
- `design-tokens.json` 을 읽었으면 그 값을 **`style.css` 맨 위 `:root` 에 직접 써라.**
  별도 파일(`design-tokens.css`)로 나누지 마라. 실제로 나눴다가 `@import` 를 빠뜨려
  색이 하나도 안 먹은 적이 있다.

```css
/* style.css 맨 위 */
:root {
  --color-primary: #A67C00;   /* design-tokens.json 에서 그대로 */
  --space-md: 16px;
  ...
}
```

- `index.html` 에서 참조하는 경로는 `./style.css` 처럼 같은 폴더 기준으로 쓴다.

### 화면 구성

`index.html` 하나에 **필요한 화면을 전부** 담는다 (섹션 전환 방식).
파일을 여러 개로 쪼개면 인터넷 없는 환경에서 링크가 깨지기 쉽다.

```
<header>  로고 · 내비게이션
<main>
  <section id="home">     상품 목록 (카드 그리드)
  <section id="detail">   상품 상세
  <section id="cart">     장바구니
  <section id="login">    로그인
  <section id="contact">  문의폼
<footer>  가게 정보 · 영업시간
```

- 상품 목록은 **카드 그리드**로. `display:grid; grid-template-columns:
  repeat(auto-fill, minmax(220px,1fr));`
- 이미지는 외부에서 받아오지 말고 **CSS 배경/그라데이션이나 인라인 SVG** 로 대신한다.
- 폼은 `<label>` + `<input>` 을 세로로 쌓고 `<br>` 을 쓰지 않는다.
- `app.js` 에서 화면 전환·장바구니 상태·입력 검증을 처리한다.
  데이터는 `localStorage` 에 둔다 (서버가 없어도 동작해야 한다).
- **주문서의 톤&매너를 실제로 반영한다.** "따뜻하고 아날로그한 느낌" 이면
  둥근 모서리·따뜻한 베이지/브라운 계열·넉넉한 여백을 쓴다. 파란 버튼을 쓰지 마라.

## 백엔드라면

`server.js` — 의존성 없이 Node 표준 모듈(`http`, `fs`)만으로 만든다.
`npm install` 하지 마라. `api-contract.yaml` 의 엔드포인트를 그대로 구현한다.

## DB라면

`seed.sql` — `schema.sql` 에 맞는 **실제로 말이 되는 예시 데이터**.
빵집이면 빵 이름과 가격이 그럴듯해야 한다.

## 마지막에

`report.md` 에 만든 파일, 구현한 화면 수, 남은 이슈를 적는다.
