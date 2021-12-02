#!/bin/bash
set -ex

# Build a new copy of tableconv package
rm -rf dist
python setup.py sdist bdist_wheel

# Release!
twine upload dist/*
