.PHONY: clean clean-build clean-pyc clean-test coverage dist docs help lint test rev_version release
.DEFAULT_GOAL := help

define BROWSER_PYSCRIPT
import os, webbrowser, sys

from urllib.request import pathname2url

webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT

clean: clean-build clean-pyc clean-test ## remove all build, test, coverage and Python artifacts

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test:
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache
	rm -rf .mypy_cache

lint:
	flake8 tableconv tests setup.py
	black tableconv --exclude 'main\.py' --line-length 120 --check
	codespell --check-filenames 'tests/**.py' tableconv setup.py README.md Makefile docs --skip '**/_build'
	mypy --ignore-missing-imports --show-error-codes tableconv tests

test: lint
	update_readme_usage --check
	tableconv --kill-daemon
	unset TABLECONV_AUTO_DAEMON
	pytest

test-ci: lint
	# Smaller testsuite for CI until I bother to fix the CI environment to run postgres etc.
	pytest -k test_cli

test-packaging:
	bash ./test_packaging_in_docker.sh

coverage:
	coverage run --source tableconv -m pytest
	coverage report -m
	coverage html
	$(BROWSER) htmlcov/index.html

docs: ## Generate Sphinx HTML documentation, including API docs
	rm -f docs/tableconv.rst
	rm -f docs/modules.rst
	sphinx-apidoc -o docs/ tableconv
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	$(BROWSER) docs/_build/html/index.html

servedocs: docs ## Autoreload docs
	watchmedo shell-command -p '*.rst' -c '$(MAKE) -C docs html' -R -D .

rev_version:
	python rev_version.py

release: dist ## Build and release to PyPI
	twine upload dist/*

dist: clean
	python setup.py sdist
	python setup.py bdist_wheel
	ls -l dist
