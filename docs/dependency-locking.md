# Python Dependency Locking

PrintOps keeps human-edited dependency intent in `requirements.txt` and
`requirements-dev.txt`. Clean CI, Docker, and release builds install from the
generated hash-locked files:

- `requirements.lock.txt`
- `requirements-dev.lock.txt`

Regenerate both lockfiles after changing either input file:

```bash
pip install -r requirements-dev.txt
python -m piptools compile requirements.txt --generate-hashes --allow-unsafe --strip-extras --resolver=backtracking --cache-dir .cache/pip-tools --output-file=requirements.lock.txt
python -m piptools compile requirements.txt requirements-dev.txt --generate-hashes --allow-unsafe --strip-extras --resolver=backtracking --cache-dir .cache/pip-tools --output-file=requirements-dev.lock.txt
```

Verify the locked install path before opening a release PR:

```bash
pip install --require-hashes -r requirements-dev.lock.txt
```

The current lockfiles were generated with Python 3.12. Keep CI on a supported
Python version and regenerate locks deliberately when changing the resolver
Python, because environment markers can affect the resolved set.
