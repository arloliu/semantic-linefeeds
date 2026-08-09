# 600 - Git Conventions

Apply when crafting commits, branches, or PR titles and descriptions.

## Branches

Prefixes: `feat/`, `fix/`, `docs/`, `chore/`, `test/`, `refactor/`.

## Commit Messages

No `commitlint` config exists in this repo;
the rules below are enforced by convention and review, not tooling.

- [Conventional Commits](https://www.conventionalcommits.org/) type prefix required:
  `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.
  Optional scope: `fix(extractor): ...`.
  Present tense, imperative.
- Header ≤ 50 chars;
  body lines ≤ 72 chars.
- Body explains WHY and WHAT at a high level —
  skip per-file diffs and exhaustive test lists.

### No Plan/Review Jargon

`git log` and `git blame` readers can't see in-progress plans.
Never cite sequencing labels, work-item IDs, review rounds, or `tmp/*` paths.
A committed file path is fine to cite;
a plan's internal step numbering is not.

- Bad: `fix(extractor): close the fence leak per plan step 3`
- Good: `fix(extractor): reset fence state at one-line scope exit`

### Attribution

Never add `Co-Authored-By`, "Generated with ...", or any other attribution trailer.

## Pull Requests

Title matches the commit format.
Body restates WHY for reviewers who haven't read the plan;
lead with domain language.
