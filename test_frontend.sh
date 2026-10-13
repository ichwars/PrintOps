#!/bin/sh

# Keep checks sequential so low-memory hosts do not need both heaps at once.
cd frontend || exit 1
npm run typecheck
typecheck_rc=$?
npm run lint
lint_rc=$?
npm run test:run
test_rc=$?

if [ "$typecheck_rc" -ne 0 ] || [ "$lint_rc" -ne 0 ] || [ "$test_rc" -ne 0 ]; then
    echo "FAILED: typecheck=$typecheck_rc lint=$lint_rc tests=$test_rc"
    exit 1
fi
