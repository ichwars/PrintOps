#!/bin/sh

cd "$(dirname "$0")" || exit 1
project_dir=$PWD
test_python=${PRINTOPS_TEST_PYTHON:-$project_dir/venv/bin/python3}
if [ ! -x "$test_python" ]; then
    if [ -n "${PRINTOPS_TEST_PYTHON:-}" ]; then
        echo "The configured test interpreter is unavailable." >&2
        exit 1
    fi
    test_python=$(command -v python3) || exit 1
fi
test_workers=${PRINTOPS_TEST_WORKERS:-4}
test_dir=$(mktemp -d) || exit 1
trap 'rm -rf "$test_dir"' EXIT

"$test_python" -m ruff check backend/ || exit 1
"$test_python" -m ruff format --check backend/ || exit 1

typecheck="$project_dir/tools/backend-typecheck/node_modules/basedpyright/index.js"
if [ -f "$typecheck" ]; then
    node "$typecheck" --pythonpath "$test_python" --baselinemode=lock || exit 1
else
    echo "Backend type check can be enabled with npm ci --prefix tools/backend-typecheck --ignore-scripts."
fi

test_postgres_url=${TEST_POSTGRES_URL:-}
export DATA_DIR="$test_dir/data" LOG_DIR="$test_dir/logs" DATABASE_URL="sqlite+aiosqlite:///$test_dir/runtime.db"
unset TEST_POSTGRES_URL
cd backend || exit 1

if [ "${1:-}" = "--full" ]; then
    set --
else
    set -- --ignore=tests/unit/services/test_bambu_ftp.py
fi
"$test_python" -m pytest tests/ --tb=short -n "$test_workers" "$@" || exit 1
if [ "$#" -eq 0 ] && [ -n "$test_postgres_url" ]; then
    TEST_POSTGRES_URL="$test_postgres_url" "$test_python" -m pytest tests/ --tb=short -n "$test_workers"
fi
