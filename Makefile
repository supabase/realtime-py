install:
	poetry install

install_poetry:
	curl -sSL https://install.python-poetry.org | python -
	poetry install

tests: install tests_only tests_pre_commit

tests_pre_commit:
	poetry run pre-commit run --all-files

run_tests: tests

tests_only:
	poetry run pytest -vv

build_sync:
	poetry run unasync realtime tests
