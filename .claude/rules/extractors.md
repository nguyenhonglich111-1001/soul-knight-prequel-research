---
paths:
  - "tools/extract_*.py"
  - "tools/dump_prefabs.py"
  - "tools/parallel.py"
---

# Extractor invariants (details in docs/extraction.md)

- **One bundle per UnityPy environment.** Variants share `.resS` CAB names, and co-loading
  them silently scrambles every sprite crop. Never `UnityPy.load(*paths)`.
- **Read only the bundles the catalog names.** Filter through
  `extract_soulknight.shipped_bundles()`, never by filename order.
- **Keep results merged in bundle order** (`map_bundles`, `consume`). "First bundle wins" has to
  stay byte-identical to a sequential run.
- **Keep error results out of `.cache/`.** `cacheable` must reject them.
- **Put every input into the cache tag.** The tag already hashes the worker's source file and
  the UnityPy version. Anything else a result depends on, such as the mono-script bundles, must
  go in through `cache_tag(...)`, or the cache serves stale results.
- **Keep the class name under `$type`** in prefab dumps, never under `type`.
- **Prove output is unchanged after a refactor.** Rebuild into a scratch folder and compare it
  byte-for-byte with `extracted/<version>/` before committing.
