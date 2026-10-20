.PHONY: test doctor research-check boundaries

test:
	python3 -m unittest discover -s tests -v

doctor:
	python3 -m manager_core

research-check:
	python3 tools/imozuru/report.py research/imozuru/manager-foundations --check

boundaries:
	python3 scripts/check_boundaries.py
