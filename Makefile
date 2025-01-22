install:
	poetry install

install_poetry:
	curl -sSL https://install.python-poetry.org | python -
	poetry install

tests: install tests_only tests_pre_commit

tests_pre_commit:
	poetry run pre-commit run --all-files

run_tests: tests

setup_test_infra:
	supabase start --workdir tests
	supabase db reset --workdir tests
	supabase status --workdir tests -o env > tests/.env \
		--override-name auth.anon_key=SUPABASE_ANON_KEY \
		--override-name api.url=SUPABASE_URL

tests_only: setup_test_infra
	poetry run pytest --cov=./ --cov-report=xml --cov-report=html -vv
