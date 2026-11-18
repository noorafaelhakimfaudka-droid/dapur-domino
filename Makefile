.PHONY: lint typecheck test check samples reproduce app

PYTHON ?= uv run python

lint:
	uv run ruff check src tests scripts

typecheck:
	uv run mypy src tests scripts

test:
	uv run pytest -v

check: lint typecheck test

samples:
	$(PYTHON) scripts/fetch_m0_samples.py

reproduce:
	$(PYTHON) scripts/reproduce.py

app:
	uv run streamlit run src/dapur_domino/app/streamlit_app.py
