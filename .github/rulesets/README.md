# Release tag ruleset

[`immutable-v-tags.json`](immutable-v-tags.json) is the repository-level GitHub
ruleset for release tags. It allows a new `v*` tag to be created, then rejects
updates and deletion. There are no bypass actors.

The JSON file is declarative and does not change repository settings by itself.
An administrator can install it once with GitHub CLI:

```bash
gh api \
  --method POST \
  repos/ejupi-djenis30/DjenisAiAgent/rulesets \
  --input .github/rulesets/immutable-v-tags.json
```

Before running that command, list the existing rulesets to avoid creating a
duplicate:

```bash
gh api repos/ejupi-djenis30/DjenisAiAgent/rulesets \
  --jq '.[] | {id, name, target, enforcement}'
```

If `Immutable v* release tags` already exists, update its numeric ID instead:

```bash
gh api \
  --method PUT \
  repos/ejupi-djenis30/DjenisAiAgent/rulesets/RULESET_ID \
  --input .github/rulesets/immutable-v-tags.json
```

The Docker release workflow independently fetches the exact remote tag into an
isolated ref. Creating the initial draft authorization also atomically fetches
`origin/master` and requires both dereferenced commits to match. Retries use the
exact draft's persisted commit and digest, so a later `master` commit cannot
strand an already authorized release. The publisher enumerates the authenticated
Release inventory across every page to recover drafts, rejects ambiguous or
out-of-order SemVer state, and rereads the exact authorization immediately before
promotion. The remote tag is fetched again before draft creation, GHCR alias
promotion, and draft finalization.

Repository release immutability is a separate required administrator setting.
Check it outside the workflow with a token that has repository Administration
read permission:

```bash
gh api \
  -H "X-GitHub-Api-Version: 2026-03-10" \
  repos/ejupi-djenis30/DjenisAiAgent/immutable-releases \
  --jq '{enabled, enforced_by_owner}'
```

The jobs that enumerate drafts need `contents: write`: GitHub only includes
drafts in Release listings for callers with push access. Even that scoped
`GITHUB_TOKEN` cannot read the separate repository Administration endpoint
above. Instead, the publisher fails closed after publication unless the exact
Release response reports `immutable: true`, and it verifies a newly published
Release is explicitly latest. Treat the administrator setting check above as a
required external release gate.
