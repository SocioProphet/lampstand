.PHONY: validate prophet-understand-smoke

validate: prophet-understand-smoke
	@echo "OK: lampstand validate"

prophet-understand-smoke:
	python3 tools/smoke_prophet_understanding_index.py
