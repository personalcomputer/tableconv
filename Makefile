.PHONY: help clean lint test test-ci test-packaging coverage docs release
.DEFAULT_GOAL := help

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

# Linters/tests:
# - Black: Code formatting
# - Isort: Import formatting
# - Ruff: Generic Python linter. Successor to flake8/pyflakes/etc.
# - Codespell: English typo detection
# - Mypy: Type checking
# - Vulture: Dead code detection
# - Pytest: Automated test suite
# - update_readme_usage: Keep the Usage section of the README up to date
# - verify_all_files_in_py_build_are_tracked_in_git: Prevent forgetting to stage files and prevent errant files ending up in the build

_lint_autofixing: # run the linters that support autofixing, with autofixing enabled
	uv run black tableconv tests
	uv run ruff check tableconv tests --fix
	uv run isort tableconv tests
	uv run black tableconv tests  # (rerun. ruff/isort and black sometimes conflict)
	@if which update_readme_usage > /dev/null 2>&1; then \
		uv run update_readme_usage; \
	fi

_lint_autofixing_disabled: # run the linters that support autofixing, but with autofixing disabled
	uv run black tableconv tests --check
	uv run ruff check tableconv tests
	uv run isort tableconv tests --check
	@if which update_readme_usage > /dev/null 2>&1; then \
		uv run update_readme_usage --check; \
	fi

_lint_nonautofixing: # run the linters that don't support autofixing
	uv run codespell --check-filenames 'tests/**.py' tableconv pyproject.toml README.md Makefile docs --skip '**/_build'
	uv run mypy --ignore-missing-imports --show-error-codes tableconv tests
	uvx vulture tableconv tests/vulture_whitelist.list
	@# Regenerate vulture_whitelist.list with:
	@# uvx vulture tableconv --make-whitelist > tests/vulture_whitelist.list

lint: _lint_autofixing_disabled _lint_nonautofixing

auto: _lint_autofixing _lint_nonautofixing test_py test_that_build_is_clean
	@# Run all linters and tests, autofixing any autofixable issues.

test_py:
	uv run tableconv --kill-daemon || true
	TABLECONV_AUTO_DAEMON= uv run pytest

test_that_build_is_clean:
	uv build
	verify_all_files_in_py_build_are_tracked_in_git.py

test_ci: lint
	# Smaller testsuite for CI until I bother to fix the CI environment to run postgres etc.
	uv run pytest -k test_cli

test_packaging:
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

release: ## Build and release to PyPI
	# Get primary branch name
	@if [ "$$(git rev-parse --abbrev-ref HEAD)" != "main" ] && [ "$$(git rev-parse --abbrev-ref HEAD)" != "master" ]; then \
		echo "Error: Must be on main/master branch to do release"; \
		exit 1; \
	fi
	@if git diff --exit-code --cached > /dev/null 2>&1 && git diff --exit-code > /dev/null 2>&1; then \
		echo "No changes to commit"; \
		exit 0; \
	else \
		echo "Error, cannot commit release commit with unresolved changes:"; \
		git status --short --untracked-files=no; \
		exit 1; \
	fi
	# make sure branch is in sync with remote before we do anything
	git checkout master
	git pull origin master
	# Rerun tests
	$(MAKE) lint
	$(MAKE) test
	# Bump version
	rev_version
	# Build & Release to PyPI
	$(MAKE) clean
	uv build
	ls -l dist
	verify_all_files_in_py_build_are_tracked_in_git.py
	uv publish --token "$$(pcregrep -o1 'password: (pypi-.+)$$' ~/.pypirc)"
	# Push the release to github too.
	git push -u origin $$(git rev-parse --abbrev-ref HEAD)
