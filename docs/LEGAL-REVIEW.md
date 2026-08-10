# Redistribution of EASA publications — findings and decision

**Status: resolved 2026-08-10. Git history is not being rewritten.**

This file existed because the repository used to contain complete EASA Easy
Access Rules publications under an MIT licence covering the whole tree. Below is
what was actually found, and what was decided.

> Not legal advice. This is a reading of publicly available terms by the people
> building the tool. If this project is used commercially, get a qualified
> opinion.

---

## 1. What was committed

| File | Size | Publication | sha256 |
|------|------|-------------|--------|
| `tests/real_samples/cs-vla.xml` | 6 402 678 B (~6.1 MiB) | Easy Access Rules for Very Light Aeroplanes (CS-VLA), Amendment 1 | `b24a3ab4fe969d646fe3ffb217e693e596ad490e9bf1ae5907723ca754f05bee` |
| `tests/real_samples/cs-23.xml` | 4 184 733 B (~4.0 MiB) | Easy Access Rules for Normal-Category Aeroplanes (CS-23) | `cbaf332c96b4c7b54e6776f8a74df36a8d411885b7d135fbab2f363e76504743` |

Both complete XML exports of the published regulation text, introduced by a
single commit (`59fcb91`) and never modified afterwards.

## 2. Finding: reproduction is authorised

EASA's [copyright page](https://www.easa.europa.eu/copyright-disclaimer)
carries the standard EU formula: reproduction is authorised provided the source
is acknowledged, save where otherwise stated. Where prior permission is
required, that requirement cancels the general permission and must say so
explicitly.

Two things were checked before relying on this:

1. **The "Official Publication of the Agency" carve-out does not apply here.**
   An earlier draft of this document assumed it might. It does not: that clause
   (referencing Executive Director Decision 2012/163/E) sits in the **Disclaimer**
   section and concerns accuracy and completeness of website material. It is not
   a copyright exception.
2. **The publications state no reproduction restriction of their own.** The
   front matter of CS-VLA is a liability disclaimer — it notes that the document
   is a consolidated, unofficial compilation and that EASA accepts no liability.
   There is no "otherwise stated" restriction to trigger.

**Conclusion:** redistributing EAR XML with attribution appears to be permitted.
Committing those files was not a licensing violation, and rewriting history
would solve a problem that does not exist.

## 3. The real issue: the MIT grant

The sharper problem the review raised remains valid, and is independent of
whether redistribution is allowed. MIT grants any recipient the right to use,
modify, sublicense and sell the covered work. Applied to a tree containing
regulatory text, it purports to grant rights over that text which nobody here
holds.

That is fixed by stating the boundary, not by deleting files. See the root
[`NOTICE`](../NOTICE), which carves regulatory text out of the MIT grant and
records the attribution EASA's policy requires.

## 4. Decision

| Question | Decision |
|----------|----------|
| Rewrite git history? | **No.** Nothing was violated; a rewrite would invalidate every clone, fork and the v0.1.x tags for no benefit. |
| Keep publications out of the repository? | **Yes** — but for engineering reasons, not legal ones (see below). |
| Address the MIT scope? | **Yes** — root `NOTICE`, carving regulatory text out of the grant. |

Publications stay out of the repository because:

- 11 MiB of binary-ish XML in a repository of ~3.5k lines of code is a poor
  trade, and it bloats every clone forever;
- the pins (`*.meta.yaml`) already guarantee reproducibility by sha256, so
  nothing is lost — `fetch_samples.py` reconstructs the exact bytes and refuses
  anything that does not match;
- it keeps the sdist on PyPI lean.

The blobs remain reachable in history. That is now a deliberate choice, not an
oversight.

## 5. If the decision is ever revisited

A rewrite was prepared and deliberately not executed:

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

It invalidates existing clones, forks and tags, and PyPI releases already
published cannot be altered.
