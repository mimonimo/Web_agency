## 품질 기준 (모든 산출물에 적용)

이 기준을 못 지키면 QA·보안·검수 게이트에서 반려된다.

### 공통
- **주문서에 없는 사실을 만들어내지 마라.** 회사명·상품명·가격·연락처는 주문서 그대로.
- 참고 자료(SRS·SCREENS·design-tokens 등)가 주어졌으면 **반드시 읽고 따라라.**
  앞 단계가 정한 것을 무시하고 새로 지어내면 반려다.
- 자리표시자(`TODO`, `lorem ipsum`, `여기에 내용`)를 남기지 마라.
- 한국어로 쓴다. 코드 주석도 한국어.

### 웹 결과물 (HTML/CSS/JS)
- **인터넷이 없는 교실에서 돈다.** CDN·구글폰트·외부 이미지·npm 패키지 금지.
  `npm install` 을 실행하지 마라. 필요한 것은 직접 작성한다.
- `<meta name="viewport" content="width=device-width, initial-scale=1">` 필수.
  **모바일에서 깨지면 반려다.**
- 레이아웃은 flexbox/grid 로. `<br>` 로 줄바꿈해서 폼을 배치하지 마라.
- 시맨틱 태그를 쓴다: `<header> <nav> <main> <section> <footer>`.
  `<div>` 만으로 문서를 만들지 마라.
- **디자인 토큰을 CSS 변수로 받아 쓴다.** 색·간격·글자 크기를 코드에 직접 박지 마라.
  ```css
  :root { --color-primary: #...; --space-md: 16px; }
  .btn { background: var(--color-primary); padding: var(--space-md); }
  ```
- 글꼴은 시스템 폰트 스택으로:
  `font-family: system-ui, "Noto Sans KR", "Malgun Gothic", sans-serif;`
- 접근성: 모든 `<input>` 에 `<label for>`, 이미지에 `alt`,
  버튼은 `<button>`(클릭되는 `<div>` 금지), 본문 대비 4.5:1 이상.
- 상태를 보여준다: 로딩 중, 비어 있음, 오류. 아무 반응 없는 화면을 만들지 마라.
- 입력값 검증은 **화면과 서버 양쪽**에서. 화면만 막으면 보안 게이트에서 반려다.

### API
- 응답 형식은 전 프로젝트 공통이다.
  성공 `{"ok": true, "data": {...}}` / 실패 `{"ok": false, "error": "메시지"}`
- 상태코드 200 / 400 / 401 / 403 / 404 만 쓴다.
- 에러 메시지는 사용자가 읽을 한국어로. 스택 트레이스를 그대로 뱉지 마라.
