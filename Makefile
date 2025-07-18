install:
	poetry install

install_poetry:
	curl -sSL https://install.python-poetry.org | python -
	poetry install

tests: install run_mypy tests_only tests_pre_commit

tests_pre_commit:
	poetry run pre-commit run --all-files

run_mypy:
	poetry run mypy ./realtime

run_infra:
	npx supabase start --workdir infra -x studio,mailpit,edge-runtime,logflare,vector,supavisor,imgproxy,storage-api

stop_infra:
	npx supabase --workdir infra stop

run_tests: tests

local_tests: run_infra sleep tests

tests_only:
	poetry run pytest --cov=realtime --cov-report=xml --cov-report=html -vv

sleep:
	sleep 2
