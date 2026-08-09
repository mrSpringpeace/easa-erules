# Publishing checklist — PyPI + GitHub Release

## Prerequisites (one-time)

1. **PyPI account** at https://pypi.org (and optionally TestPyPI).
2. **Trusted Publishing** (preferred, no long-lived token):
   - PyPI → Account settings → Publishing → Add a new pending publisher  
   - **PyPI project name:** `easa-erules`  
   - **Owner:** `mrSpringpeace`  
   - **Repository:** `easa-erules`  
   - **Workflow name:** `publish.yml`  
   - **Environment name:** `pypi`
3. **GitHub Environment** `pypi` (Settings → Environments) — optional protection rules.
4. Alternative: store `PYPI_API_TOKEN` as a repo secret and switch the publish job to token auth (not configured by default).

## Release a new version

1. Bump version in **both**:
   - `pyproject.toml` → `[project].version`
   - `src/easa_erules/__init__.py` → `__version__`
2. Update `CHANGELOG.md` (Keep a Changelog style).
3. Ensure clean tree and green CI:

   ```bash
   pytest -q
   ruff check src tests
   ```

4. Local package check:

   ```bash
   pip install -e ".[dev]"
   python -m build
   twine check dist/*
   ```

5. Commit, tag, push:

   ```bash
   git add -A
   git commit -m "Release vX.Y.Z"
   git tag -a vX.Y.Z -m "easa-erules vX.Y.Z"
   git push origin main --tags
   ```

6. Create GitHub Release from the tag (UI or CLI):

   ```bash
   gh release create vX.Y.Z --title "vX.Y.Z" --notes-file CHANGELOG.md
   ```

   Publishing the release triggers `.github/workflows/publish.yml` → PyPI.

7. Verify:

   ```bash
   pip install easa-erules==X.Y.Z
   easa-erules --help
   ```

## Manual / dry-run publish workflow

Actions → **Publish to PyPI** → Run workflow → leave **dry_run** checked to only build+check.

## Install from source (always works)

```bash
pip install "git+https://github.com/mrSpringpeace/easa-erules.git@main"
# or a tag:
pip install "git+https://github.com/mrSpringpeace/easa-erules.git@v0.1.1"
```

## Notes

- Regulatory **text** is not re-licensed by this package; only the **code** is MIT.
- Large real EAR samples under `tests/real_samples/` are pruned from the sdist (`MANIFEST.in`).
- Wheel contains only `src/easa_erules` (including `sources/easa.yaml`).
