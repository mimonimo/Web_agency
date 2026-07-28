# AGORA HQ — dgx-12 (PM PC 겸 HQ)
#
# 모든 타깃은 멱등하다. 두 번 돌려도 같은 결과여야 한다 (BRIEF 작업규칙 4).

SHELL := /bin/bash
COMPOSE := docker compose

.DEFAULT_GOAL := help
.PHONY: help dev dev-stop dev-log demo test up down restart logs ps reset provision seed preload acceptance env check

help:  ## 이 도움말
	@echo "AGORA HQ — 사용 가능한 명령"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "지금 바로:  make dev   → http://220.67.5.62:8000/"
	@echo "컨테이너로 가려면: sudo usermod -aG docker \$$USER 후 재로그인 → make up"

dev: env  ## ★ 네이티브로 HQ 기동 (docker 권한 없이 — venv + SQLite)
	@./ops/dev.sh start

dev-stop:  ## 네이티브 HQ 정지
	@./ops/dev.sh stop

dev-log:  ## 네이티브 HQ 로그
	@./ops/dev.sh log

demo:  ## ★ 수업 시연 시나리오 (PM 화면 띄워 놓고 실행)
	@./ops/demo.sh

test:  ## 상태기계 단위 테스트 + E2E 흐름 테스트
	@./.venv/bin/python core/tests/test_orchestrator.py
	@./.venv/bin/python core/tests/test_flow.py

env: .env  ## .env 가 없으면 .env.example 에서 만든다
.env:
	@cp .env.example .env
	@echo ".env 를 .env.example 에서 만들었다. 비밀번호를 바꿔라."

check:  ## docker 를 쓸 수 있는지 먼저 본다
	@docker info >/dev/null 2>&1 || { \
	  echo "docker 에 접근할 수 없다."; \
	  echo "  sudo usermod -aG docker \$$USER   후 재로그인이 필요하다."; \
	  exit 1; }

up: env check  ## HQ 기동
	$(COMPOSE) up -d --build
	@echo
	@$(COMPOSE) ps

down: env  ## HQ 정지 (데이터는 남는다)
	$(COMPOSE) down

restart: down up  ## 재기동

ps: env  ## 컨테이너 상태
	$(COMPOSE) ps

logs: env  ## 로그 따라가기 (make logs SVC=core)
	$(COMPOSE) logs -f $(SVC)

preload: env check  ## ★ 인터넷 있을 때 미리 — 이미지 pull + core 빌드 (BRIEF 작업규칙 7)
	$(COMPOSE) pull postgres caddy
	$(COMPOSE) build core
	@echo "오프라인 준비 완료. 교실에서는 pull 없이 뜬다."

provision: env  ## 노드 11개 등록 + 씨앗 커밋 (Phase 2)
	$(COMPOSE) exec -T core python /app/provisioning/provision.py

seed: env  ## 씨앗 주문·티켓 (Phase 2)
	$(COMPOSE) exec -T core python /app/provisioning/seed.py

acceptance:  ## ★ 인수 테스트 — 돌려서 출력을 봐야 완료다 (BRIEF §12)
	@./ops/acceptance.sh $(if $(PHASE),--phase $(PHASE),)

reset: env  ## 전체 초기화 — 다음 수업/다음 반용 (Phase 5)
	./ops/reset.sh
