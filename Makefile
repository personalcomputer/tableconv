.PHONY: help clean lint test test-ci test-packaging coverage docs release
.DEFAULT_GOAL := help

# Show makefile usage help message
help:
	@# Run makehelp using python uv, if available, otherwise, pipx, otherwise error.
	@(which uvx >/dev/null 2>&1 && uvx makehelp) || (which pipx >/dev/null 2>&1 && pipx run makehelp) || echo 'Error: Please run `pip install uv && uv tool install makehelp` first'

clean:
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/

lint:
	uv run flake8 tableconv tests setup.py
	uv run black tableconv --exclude 'main\.py' --line-length 120 --check
	uv run codespell --check-filenames 'tests/**.py' tableconv pyproject.toml README.md Makefile docs --skip '**/_build'
	uv run update_readme_usage --check
	uv run mypy --ignore-missing-imports --show-error-codes tableconv tests

test:
	uv run tableconv --kill-daemon
	unset TABLECONV_AUTO_DAEMON
	uv run pytest

test-ci: lint
	# Smaller testsuite for CI until I bother to fix the CI environment to run postgres etc.
	uv run pytest -k test_cli

test-packaging:
	# test installing the package fresh on a new computer, using docker
	bash ./test_in_container.sh

coverage:
	uv run coverage run --source tableconv -m pytest
	uv run coverage report -m
	uv run coverage html
	$(BROWSER) htmlcov/index.html

docs: ## Generate Sphinx HTML documentation, including API docs
	rm -f docs/timetool.rst
	rm -f docs/modules.rst
	uvx --from sphinx sphinx-apidoc -o docs/ timetool
	uvx --from sphinx $(MAKE) -C docs clean
	uvx --from sphinx $(MAKE) -C docs html
	xdg-open docs/_build/html/index.html

servedocs: docs ## Autoreload docs
	uvx --with sphinx --from watchdog watchmedo shell-command -p '*.rst' -c '$(MAKE) -C docs html' -R -D .

release: clean ## Build and release to PyPI
	@if git diff --exit-code --cached > /dev/null 2>&1 && git diff --exit-code > /dev/null 2>&1; then \
		echo "No changes to commit"; \
		exit 0; \
	else \
		echo "Error, cannot commit release commit with unresolved changes:"; \
		git status --short --untracked-files=no; \
		exit 1; \
	fi
	# Rerun tests
	$(MAKE) lint
	$(MAKE) test
	# Bump version
	rev_version
	# Build & Release to PyPI
	$(MAKE) clean
	uv build
	ls -l dist
	uv publish --token "$$(pcregrep -o1 'password: (pypi-.+)$$' ~/.pypirc)"
