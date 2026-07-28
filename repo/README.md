# repo/ — 프로젝트 산출물 저장소

BRIEF §2 · §3.5.

```
repo/
  project-001/            ← 확정 산출물. step 이 DONE 되면 여기로 승격된다
  runs/{cycle_id}/{step_id}/output/...
  runs/{cycle_id}/{step_id}/report.md    ← 에이전트 완료 보고
```

- `runs/` 는 `.gitignore` 에 있다. 재생성 가능하고 `reset` 으로 날아간다.
- **step 을 두 번 돌려도 결과가 같아야 한다** (인수 #23). rewind/reset 의 전제다.
- `repo/` 조작은 반드시 git 커밋과 함께 한다 (BRIEF §15-5). 커밋 메시지 형식:

  ```
  [cycle-3][S5][backend] 구현 산출물
  ```

  회고 시간에 이 로그를 띄운다.

bare git + 작업 트리 초기화는 **Phase 1** 에서 한다.
