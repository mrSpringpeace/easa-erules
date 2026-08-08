# Real EASA sample documents

This directory holds **real Easy Access Rules XML** packages for smoke tests.

## Checked in

| File | Source |
|------|--------|
| `cs-vla.xml` | EASA CS-VLA (latest XML export at fetch time) |
| `cs-vla.meta.yaml` | Integrity / version metadata from `easa-erules fetch` |
| `cs-23.xml` | EASA CS-23 (latest XML export at fetch time) |
| `cs-23.meta.yaml` | Integrity / version metadata |

Files are large (several MB each). Refresh with:

```bash
export EASA_ERULES_CACHE=/tmp/easa-refresh
easa-erules fetch cs-vla --force
easa-erules fetch cs-23 --force
cp ~/.cache/easa-erules/cs-vla/source.xml tests/real_samples/cs-vla.xml
# or from custom cache:
cp /tmp/easa-refresh/cs-vla/source.xml tests/real_samples/cs-vla.xml
cp /tmp/easa-refresh/cs-vla/versions/*/meta.yaml tests/real_samples/cs-vla.meta.yaml
```

## Running smokes

```bash
pytest tests/test_real_samples.py -v
# optional live network re-fetch:
EASA_ERULES_LIVE=1 pytest tests/test_real_samples.py -v
```
