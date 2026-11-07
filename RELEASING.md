# Releasing

## 1. Prepare (no credentials needed)

```bash
# bump the version in pyproject.toml, src/paperlint/__init__.py and CITATION.cff
.venv/bin/python -m pytest
.venv/bin/ruff check src tests
rm -rf dist build
.venv/bin/python -m build --sdist --wheel
.venv/bin/twine check dist/*          # must print PASSED for both files
```

The version string lives in three places on purpose: `pyproject.toml` (packaging),
`src/paperlint/__init__.py` (what `--version` prints) and `CITATION.cff` (what a
citation file consumer sees). Bump all three, or the release contradicts itself.

## 2. Tag and publish the GitHub release

```bash
git add -A && git commit -m "release: vX.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin main --tags
gh release create vX.Y.Z dist/* --title "paperlint vX.Y.Z" --notes-file NOTES.md
gh release view vX.Y.Z --json assets -q '.assets[] | "\(.name)\t\(.size)"'
```

`--notes-file` avoids shell quoting damage in the release body. Verify the assets
are listed with `uploaded` state before announcing anything.

## 3. Two steps that need a human (credentials)

Neither is automated by design: a release token in an agent's reach is a token
that leaks eventually.

- **PyPI** — create an API token, put it in `~/.pypirc` (or `TWINE_PASSWORD`), then
  `.venv/bin/twine upload dist/*`. A published version cannot be deleted, only
  yanked, so bump the version rather than reusing one.
- **Zenodo DOI** — log in at zenodo.org, *Settings → GitHub*, flip the switch for
  `afiqandico/paperlint`. From then on every GitHub release is archived and gets a
  DOI; the already-published `v0.1.0` is picked up when the switch is flipped.
  Then paste the DOI badge into `README.md` and add it to `CITATION.cff`.

## 4. Verify the artefact a stranger gets

```bash
curl -sSLO https://github.com/afiqandico/paperlint/releases/download/vX.Y.Z/paperlint-X.Y.Z-py3-none-any.whl
python3 -m venv /tmp/probe && /tmp/probe/bin/pip install ./paperlint-X.Y.Z-py3-none-any.whl
/tmp/probe/bin/paperlint --version
```

This is the free equivalent of `pip install paperlint` until step 3 happens, and it
is what the README tells people to use.
