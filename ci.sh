#!/bin/bash

if [ "$1" = "" ]; then
    echo "Please provide a the python major.minor version as first argument."
    exit 1
fi;

set -xe

PYTHON_MAJOR_MINOR=$1

rm -rf .venv

echo "exit()" | ./venv python$PYTHON_MAJOR_MINOR
./venv pip install --quiet poetry
# CPython 3.9+ requires to install cython prior to poetry install
# (possibly because there is no binary wheel for that version in pypi
# as of yet)
./venv poetry install --no-ansi --quiet
./venv pytest tests.py

# Publish if there is a tag on the current commit

# XXX: use set +x to avoid to leak the pypi secret token inside ~/.pypi-token!
set +x
git tag -l --points-at $(git show -q --format=%H) | grep v && ./venv poetry config http-basic.pypi __token__ $(cat ~/.pypi-token) || true
set -x
git tag -l --points-at $(git show -q --format=%H) | grep v && ./venv poetry build --format wheel || true
git tag -l --points-at $(git show -q --format=%H) | grep v && ./venv poetry publish || true
