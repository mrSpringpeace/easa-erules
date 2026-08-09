# Authority adapters

| Adapter | Status | Role |
|---------|--------|------|
| `easa` | **Production** | Full EAR fetch / parse / search path |
| `faa` | Scaffold | Future eCFR / FAR ingestion |
| `astm` | Scaffold | Future F44 (and related) standards |

```python
from easa_erules.adapters import get_adapter

adapter = get_adapter("easa")
print(adapter.capabilities())
result = adapter.parse("tests/real_samples/cs-vla.xml")
```

FAA and ASTM adapters intentionally raise `NotImplementedError` on fetch/parse
until designation quality on EASA sources is solid and package formats are chosen.
