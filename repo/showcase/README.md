# showcase — 보존된 결과물

사이클 실행 결과 중 **비교·시연용으로 남겨 둔 것**. `ops/reset.sh` 도 여기는 건드리지 않는다.

| 폴더 | 무엇 | 품질 점수 |
|---|---|---|
| `v1-before/` | 지시문 고도화 **이전** | **10/19 (53점)** |
| `v2-after/` | 지시문 고도화 **이후** | **19/19 (100점)** |

## 무엇이 달라졌나

| | v1 (전) | v2 (후) |
|---|---|---|
| viewport | 없음 | 있음 |
| 시맨틱 태그 | 0/5 | 5/5 |
| 레이아웃 | `<br>` 4개 | flex/grid |
| CSS 변수 | 0개 | 24회 사용 |
| 색 | 기본 초록 #4CAF50 | 밀밭제과 톤 #A67C00 금빛 / #FFF8E1 크림 |
| 화면 수 | 1개 (주문폼) | 5개 (홈·상세·장바구니·로그인·문의) |

**원인은 프롬프트가 아니라 참고 자료가 전달되지 않은 것이었다.**
`inputs` 를 실제 경로로 바꾸자 프론트엔드가 SCREENS.md 와 design-tokens.json 을
읽게 됐고, 그때부터 결과가 달라졌다. 자세한 것은 `~/agora/CLAUDE.md`.

## 보는 법

```
/preview/showcase/v1-before/index.html
/preview/showcase/v2-after/index.html
```

## 새로 보존하려면

```bash
cp -r repo/runs/<사이클>/S5/output/<...> repo/showcase/v3-...
```
