# Real EASA sample documents

Smoke tests run against **real** Easy Access Rules XML — fixtures alone do not
exercise the Word SDT packaging that official exports actually use.

The publications themselves are **not stored in this repository**. Only the pins
are tracked:

| Pin | Publication |
|-----|-------------|
| `cs-vla.meta.yaml` | Easy Access Rules for Very Light Aeroplanes (CS-VLA) |
| `cs-23.meta.yaml` | Easy Access Rules for Normal-Category Aeroplanes (CS-23) |

Each pin carries the download URL, version label, sha256 and size. See
[`../../docs/LEGAL-REVIEW.md`](../../docs/LEGAL-REVIEW.md) for why.

## Fetching

```bash
python tests/real_samples/fetch_samples.py
```

Downloads every pinned sample and verifies its sha256. A mismatch means EASA has
republished the document — the script stops rather than silently changing what
the tests assert against.

Re-pin deliberately, when you want the newer publication:

```bash
python tests/real_samples/fetch_samples.py --refresh
```

## Running the smokes

```bash
pytest -m real_sample -v          # skips cleanly when samples are absent
pytest                            # full suite; real-sample tests skip
EASA_ERULES_LIVE=1 pytest tests/test_real_samples.py -v   # live fetch pipeline
```
