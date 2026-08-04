# Python Dependency Locking

PrintOps keeps human-edited dependency intent in `requirements.txt` and
`requirements-dev.txt`. The runtime input contains only packages needed by the
application. The development input includes it with `-r requirements.txt` and
adds test, lint, lock-generation, and audit tooling. Clean CI, Docker, and
release builds install from the generated hash-locked files:

- `requirements.lock.txt`
- `requirements-dev.lock.txt`

Regenerate both lockfiles after changing either input file:

```bash
pip install -r requirements-dev.txt
python -m piptools compile requirements.txt --generate-hashes --allow-unsafe --strip-extras --resolver=backtracking --cache-dir .cache/pip-tools --output-file=requirements.lock.txt
python -m piptools compile requirements-dev.txt --generate-hashes --allow-unsafe --strip-extras --resolver=backtracking --cache-dir .cache/pip-tools --output-file=requirements-dev.lock.txt
python tools/check_dependency_boundaries.py
```

Verify the locked install path before opening a release PR:

```bash
pip install --require-hashes -r requirements-dev.lock.txt
```

The boundary check verifies that the production input and lock do not contain
development-only tools, that the development input includes the runtime input,
and that both locks contain all direct requirements from their source files.

The current lockfiles were generated with Python 3.12. Keep CI on a supported
Python version and regenerate locks deliberately when changing the resolver
Python, because environment markers can affect the resolved set.
