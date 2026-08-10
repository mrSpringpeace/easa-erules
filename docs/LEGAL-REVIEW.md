# Redistribution of EASA publications — groundwork for a decision

**Status: awaiting the repository owner's decision. Nothing in git history has been rewritten.**

This document exists because the repository used to contain complete EASA Easy
Access Rules publications under an MIT licence that covers the whole tree. That
is a licensing question, not an engineering one, so this file only assembles the
facts. The decision — and the history rewrite that may follow from it — is the
owner's.

---

## 1. What was committed

| File | Size | Publication | sha256 |
|------|------|-------------|--------|
| `tests/real_samples/cs-vla.xml` | 6 402 678 B (~6.1 MiB) | Easy Access Rules for Very Light Aeroplanes (CS-VLA), Amendment 1 | `b24a3ab4fe969d646fe3ffb217e693e596ad490e9bf1ae5907723ca754f05bee` |
| `tests/real_samples/cs-23.xml` | 4 184 733 B (~4.0 MiB) | Easy Access Rules for Normal-Category Aeroplanes (CS-23) | `cbaf332c96b4c7b54e6776f8a74df36a8d411885b7d135fbab2f363e76504743` |

Both are complete XML exports of the published regulation text — not excerpts.

## 2. Where they appear in history

Introduced by a single commit:

```text
59fcb91  M10: English README, real EAR samples, expanded catalog, table merges
```

No later commit modified them. That makes a history rewrite comparatively cheap
if one is wanted: a single blob pair, one commit, no interleaved edits.

## 3. What has already been done (no decision required)

- The two XML files are **untracked** as of this change; the working copies stay
  on disk and `.gitignore` prevents them coming back.
- The pins (`cs-vla.meta.yaml`, `cs-23.meta.yaml`) remain tracked. They contain
  download URL, version label, sha256 and size — metadata about the publication,
  not the publication.
- `tests/real_samples/fetch_samples.py` reconstructs the files from the pins and
  refuses any download whose bytes do not match.
- Tests needing a sample are marked `real_sample` and skip when it is absent, so
  `pytest` passes on a clean clone with no network.

The result: nothing at `HEAD` redistributes regulatory text. **The blobs remain
reachable in history** until a rewrite is performed.

## 4. What still needs a decision

### 4.1 Are the terms of use compatible with redistribution?

Do not assume the general EU reuse policy (Decision 2011/833/EU) applies. EASA
publishes Easy Access Rules under its own terms and the documents carry their own
disclaimer and copyright notice. What needs establishing:

- the terms attached to the EAR XML exports specifically, not the EASA website in general;
- whether redistribution in a third-party repository is permitted, and under what attribution;
- whether an MIT-licensed repository containing them misrepresents their licensing status
  (this is the sharper issue: MIT grants rights over the whole tree that the owner does not hold).

Even if redistribution turns out to be permitted, the licence mismatch is worth
resolving — a `LICENSES` note carving the regulatory text out of the MIT grant.

### 4.2 Rewrite history, or leave it?

Leaving the blobs in history is a defensible choice if 4.1 comes back permissive.
If it does not, the rewrite is straightforward but **invalidates every existing
clone, fork and tag**, and PyPI releases already published cannot be altered.

Prepared, not executed:

```bash
# 1. Full backup first — this rewrite is not reversible in place.
git clone --mirror . ../easa-erules-backup.git

# 2. Requires git-filter-repo (pip install git-filter-repo).
git filter-repo --invert-paths \
    --path tests/real_samples/cs-vla.xml \
    --path tests/real_samples/cs-23.xml

# 3. Verify the blobs are gone.
git log --all --oneline -- tests/real_samples/cs-vla.xml   # expect no output

# 4. Force-push, then tell anyone with a clone to re-clone.
git push --force --all && git push --force --tags
```

Do not run step 2 without a decision on 4.1 and without the backup from step 1.

## 5. Recommendation

Resolve 4.1 first — it determines whether 4.2 is required or merely tidy. The
engineering side is already in the safe state either way: `HEAD` ships no
regulatory text, and the smoke tests still work through the pinned fetch.
