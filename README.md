# paperlint

Deterministic pre-submission gates for manuscripts and research repositories.

Every check here started as a throwaway script written during a real submission
round. They caught defects that no amount of re-reading catches: three cited
references that did not exist, a Word file shipping literal `??` where
cross-references should be, a figure whose content overflowed its canvas by 91%,
a deposit record marked "restricted" while claiming to be publicly archived.
`paperlint` puts them behind one interface, one exit code, and one JSON report so
they can run in CI instead of in someone's memory.

## Install

```bash
pip install paperlint                # core, no third-party dependencies
pip install 'paperlint[all]'         # + docx, figure and CI checks
```

Some checks shell out to standard research tooling:

| Tool | Needed by |
| --- | --- |
| `pdfinfo`, `pdftotext`, `pdfimages` (poppler-utils) | `manuscript package` page/figure/cover checks |
| `git` | `manuscript package --git`, `repo divergence`, `repo ci --online` |
| `gh` (authenticated) | `repo ci --online` only |

A missing binary is reported as a failure row, never skipped silently.

## Quick start

Audit a submission package in one pass:

```bash
paperlint manuscript package \
  --base ./submissions \
  --sha-json expects.json \
  --pages paper/manuscript/paper.pdf=15 \
  --tex paper/source/paper.tex \
  --stale 'failed: NaN' \
  --voice we \
  --docx paper/manuscript/paper.docx --min-media 9 \
  --pdf-figs paper/manuscript/paper.pdf:9 \
  --highlights paper/highlights.txt --kwexpect 7 \
  --git .
```

That command line is long, which is the point of the config file:

```bash
paperlint manuscript package --config paperlint.toml
```

```toml
# paperlint.toml
[package]
base = "./submissions"
sha_json = "expects.json"
pages = ["paper/manuscript/paper.pdf=15"]
tex = ["paper/source/paper.tex"]
stale = ["failed: NaN", "not yet quantified"]
voice = ["we", "our"]
docx = ["paper/manuscript/paper.docx"]
min_media = 9
pdf_figs = ["paper/manuscript/paper.pdf:9"]
highlights = "paper/highlights.txt"
kwexpect = 7
git = ["."]
```

Command-line list flags are **appended** to the config, so a saved package can be
audited plus one extra file without editing the file.

## Commands

| Command | What it decides |
| --- | --- |
| `manuscript package` | one PASS/FAIL table across every deliverable |
| `manuscript refs` | rewrites `\ref` from `.aux` so the DOCX has no `??` |
| `manuscript paths` | dangling path references and stale-claim wording |
| `manuscript docx-structure` | paragraph-level dump to compare template vs build |
| `manuscript docx-restyle` | restyles a pandoc DOCX, then re-reads it to verify |
| `manuscript figure` | measures the rendered figure instead of eyeballing it |
| `repo ci` | workflow placement, triggers, working directories, HEAD status |
| `repo divergence` | which files exist in only one of two git roots |
| `verify manifest` | recomputes sha256/bytes for every artefact in a manifest |
| `verify zenodo` | deposit record type, access setting, public file count, age |

`--json` on any command emits a machine-readable report:

```json
{
  "tool": "manuscript package",
  "ok": false,
  "total": 42,
  "passed": 41,
  "failed": 1,
  "checks": [{"name": "pages paper.pdf", "ok": false, "detail": "17 (want 15)"}],
  "notes": []
}
```

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | every check passed |
| `1` | at least one check failed |
| `2` | usage error |

**A run that executed no checks also exits 1.** An empty gate is not a pass —
that rule exists because a silently skipped audit is the failure mode this tool
was written to prevent.

## In CI

```yaml
- name: manuscript gates
  run: |
    pip install 'paperlint[all]'
    paperlint manuscript package --config paperlint.toml
```

## Notes on specific checks

**`manuscript package` citation parity** compares `\cite{...}` keys against
`\bibitem{...}` entries. It applies to documents with an inline bibliography. If
the document uses BibTeX, the check reports "skipped" rather than failing, and a
document with citations but no bibliography at all fails.

**`manuscript figure`** executes the plotting script with `savefig` and
`plt.close` neutralised so the live matplotlib objects can be measured. That is a
convenience on top of trusted local code, not a sandbox — do not point it at a
script you would not run.

**`manuscript paths`** matches anything shaped like `something.ext`, so prose
fragments show up as candidate dangling references. Treat the output as findings
to classify; use `--strict` only when the tree is meant to be link-clean.

**`verify manifest`** auto-detects three shapes: a JSON manifest (`{"artifacts": {...}}`),
`sha256sum` output (`<digest>  <path>`), and a file holding nothing but the digest
itself. The last one carries no filename, so it cannot be verified alone — pass
`--digest-of PATH` to name the artefact it belongs to. `paperlint` refuses to
guess, because guessing the wrong file turns a green tick into a false one:

```bash
paperlint verify manifest internal/bundle_sha.txt \
  --digest-of supplementary/reproducibility_bundle.zip
```

A manifest that lists its own digest fails: the digest is inside the file whose
digest it claims to record, so no value can ever satisfy it.

**`verify zenodo`** reads only the public API: no token, no login, no writes.

## Honest limitations

- There is no plugin system. Checks are a fixed, small set that earned their
  place by catching real defects.
- `paperlint` does not judge scientific quality: it verifies that artefacts match
  what is claimed about them.
- It never edits your manuscript, except `docx-restyle`, which is explicit and
  verifies its own result afterwards.
- Figures are measured through matplotlib internals; a plotting library other
  than matplotlib is not supported.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[all]' pytest
pytest -q
```

## Releasing

See [RELEASING.md](RELEASING.md). Version strings live in `pyproject.toml`,
`src/paperlint/__init__.py` and `CITATION.cff`; a release that updates only one of
them contradicts itself.

## License

MIT — see [LICENSE](LICENSE).
