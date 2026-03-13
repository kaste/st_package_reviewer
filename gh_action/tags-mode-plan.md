# Tags Mode Feature Plan (post-transpile)

This document captures the agreed plan for implementing tags-mode behavior **after** we finish the `action.sh` → `action.py` transpile and parity checks.

## Scope and intent

We currently support package release definitions in these practical modes:

- `branch`
- `tags` (explicit or implicit/default)
- `asset`
- static `url` releases

The immediate feature change is for **tags mode only**.

## High-level goal

For packages in tags mode, review the **tip of the default branch** instead of the latest valid tag/release artifact, while still preserving crawler compatibility checks and tag hygiene feedback.

This reduces review-cycle churn (contributors should not need to cut a new tag for every review iteration).

## Non-goals for this change

- Do **not** change behavior for `asset` mode.
- Do **not** change behavior for `branch` mode.
- Do **not** change behavior for static `url` mode.
- Do not add hoster-specific assumptions (must work with generic git details/base handling through crawler).

## Why this approach

Direct hoster API resolution (e.g. GitHub default branch + zipball) is not general enough.
We support git sources beyond GitHub, and crawler behavior is the source of truth for registry compatibility.

Therefore, for tags mode we will use crawler-driven resolution by creating a temporary rewritten package entry that forces branch-tip crawling.

## Agreed implementation strategy for tags mode

For each package detected as tags mode:

1. **Run regular crawl first** against the real target registry/package.
   - Purpose: keep existing compatibility signal that registry entry works with crawler infrastructure.

2. **Create a temporary single-package registry** for review materialization.
   - Start from a minimal registry skeleton.
   - Include only the target package entry (no unrelated packages needed).
   - For that package:
     - remove release definitions (`releases`), then
     - insert exactly one release object: `{ "branch": true }`.
   - Preserve necessary metadata (`details` or `base`) so crawler can resolve source.

3. **Run crawl on the rewritten temporary registry** for that package.
   - Expect one release artifact representing default branch tip.
   - Use workspace output from this crawl as the review input source.

4. **Review the resulting artifact** with `st_package_reviewer` as usual.
   - Keep existing repo/tag checks behavior and messages.

5. **Error handling**
   - If normal crawl fails: fail package (as today).
   - If rewritten branch crawl fails: fail package with clear diagnostics.
   - If no releases are emitted from rewritten crawl: fail package.

## Mode detection rules (current expectation)

Maintain existing mode inference semantics:

- tags mode when releases are absent/empty, or release entries do not define `asset`/`url`/`branch`.
- `asset`, `url`, `branch` remain on current behavior path.

## Important caveat (accepted)

Using branch checkout/crawl output may differ from tag-based archives influenced by `.gitattributes export-ignore`.
That discrepancy is accepted for this tags-mode review flow because the goal is reviewing latest source during iterative feedback.

## Future improvements (explicitly deferred)

- Select release definitions by newest supported ST build or open-ended `"*"` before rewriting.
- Potentially tighten mode detection and diagnostics around malformed metadata.
- Consider optional direct source checkout path if ever needed, but not required now.

## Rollout order

1. Finish transpile: `action.sh` and `action.py` parity.
2. Land transpile safely.
3. Implement tags-mode feature in `action.py` per this plan.
4. Keep `asset`/`branch`/`url` behavior unchanged in the same PR unless explicitly requested.
