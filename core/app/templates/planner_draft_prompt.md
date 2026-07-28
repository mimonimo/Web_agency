아래 요구사항(SRS.md)을 읽고, 11개 역할 각각에 대해 AGENT.md 초안을 작성한다.
각 파일은 다음 6칸을 반드시 포함한다:
  나의 역할 / 내 파일 / 출력 형식 / 금지 / 애매할 때 / 완료 보고
이번 요구사항에서 그 역할이 특별히 조심해야 할 것을 '금지' 칸에 최소 1줄 넣는다.
초안은 완벽할 필요 없다. 학생이 자기 전문 지식으로 보강할 것이다.
파일은 agents/<role>/AGENT.md 로 저장한다.

11개 역할은 정확히 다음과 같다 (이 문자열을 디렉터리 이름으로 쓴다):
  pm  planner  sales  sysadmin  designer  frontend  backend  dba  security  qa  customer

즉 output/ 아래에 아래 11개 파일을 만들어야 한다:
  agents/pm/AGENT.md
  agents/planner/AGENT.md
  agents/sales/AGENT.md
  agents/sysadmin/AGENT.md
  agents/designer/AGENT.md
  agents/frontend/AGENT.md
  agents/backend/AGENT.md
  agents/dba/AGENT.md
  agents/security/AGENT.md
  agents/qa/AGENT.md
  agents/customer/AGENT.md

각 파일의 형식은 정확히 이렇다. `##` 제목을 반드시 쓴다.

```markdown
# 나는 AGORA Web 의 <역할> 담당이다

## 나의 역할
(이 역할이 이번 요구사항에서 무엇을 책임지는지 2~3줄)

## 내 파일
(이 역할이 만들고 고칠 파일 경로들)

## 출력 형식
(산출물을 어떤 형식으로 낼지)

## 금지
- (이번 요구사항에서 이 역할이 특히 조심해야 할 것 — 최소 1줄, 역할마다 달라야 한다)

## 애매할 때
(누구에게 무엇을 묻고, 답을 받기 전까지 어떻게 할지)

## 완료 보고
(무엇을 보고할지)
```

⚠️ 11개를 전부 만들어라. 하나라도 빠지면 다음 단계가 열리지 않는다.
⚠️ `## 제목` 6개를 반드시 넣어라. 한 줄로 압축하면 학생이 고칠 자리가 없어진다.
⚠️ '금지' 칸은 **역할마다 달라야 한다.** 같은 문장을 복사하지 마라.
⚠️ front-matter(--- 로 감싼 머리말)는 쓰지 마라. HQ 가 알아서 붙인다.
