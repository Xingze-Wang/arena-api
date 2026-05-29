.PHONY: install backend mock demo reset

install:
	python3 -m venv .venv && . .venv/bin/activate && pip install -e .

backend:
	. .venv/bin/activate && uvicorn arena_api.main:app --port 8001 --reload

mock:
	. .venv/bin/activate && uvicorn arena_api.mock_endpoint:app --port 9001 --reload

reset:
	rm -f data/arena.db

demo:
	@echo "Two terminals please:"
	@echo "  1) make mock     (researcher's paper-to-api on :9001)"
	@echo "  2) make backend  (arena-api on :8001)"
	@echo "Then in a third: cd ../research-to-product/arena-skill && python3 scripts/submit.py"
