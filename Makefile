.PHONY: validate prophet-understand-smoke contract-schemas

validate: prophet-understand-smoke contract-schemas
	@echo "OK: lampstand validate"

prophet-understand-smoke:
	python3 tools/smoke_prophet_understanding_index.py

contract-schemas:
	python3 tools/check_lampstand_contract_schemas.py
