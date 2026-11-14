---
description: Build, test and release this app (beta, then production) with the shared Krazow release kit
argument-hint: "[patch|minor|major] | promote | all | status | rollback [vX.Y.Z]"
---

# /releasenow

Release this app with the shared Krazow release kit (github.com/krazow/release-kit). This repo's
`.github/workflows/release.yml` calls the kit's pipeline; git tags decide what it does:

- `vX.Y.Z-beta.N`: QA, then build every platform in `release.json`, publish the beta (web at `/beta/`, a GitHub
  pre-release with the beta APK/installer), and smoke-test the live beta. The production files wait in a draft release.
- `vX.Y.Z` on the same commit: promote. The web app goes to the main address and the draft release becomes Latest.

The arguments are: `$ARGUMENTS`

## Before anything

1. Run `git status`. If there are uncommitted changes, list them and ask whether to commit them as part of this
   release. Don't release with a dirty tree. Make sure you're on `main` and it's pushed (`git pull --rebase`, then `git push`).
2. Run `git fetch --tags` and read `VERSION`, `release.json` and the last tags (`git tag --list 'v*' --sort=-v:refname | head`).
3. If `node_modules` can be installed here (Node is available and `npm install` works), run `npm test` and stop
   on failures. If not, say so in one line and rely on the QA stage on GitHub.

## Modes

**No argument, `patch`, `minor` or `major`: cut a new beta.**
1. Work out the next version. If the newest tag is a beta of a version that was never promoted
   (no plain `vX.Y.Z` tag), this is the next beta of that same version: keep `VERSION`, and N = last beta number + 1.
   Otherwise bump `VERSION` (patch by default, or the part named) and N = 1.
2. Add a dated entry at the top of `CHANGELOG.md` (create it if missing) headed `## X.Y.Z (YYYY-MM-DD)` covering
   every change since the last tag, in plain language, grouped as Added / Changed / Fixed. Read the commits
   (`git log <last-tag>..HEAD`) and the diffs, not only the commit titles. For a further beta, add to that version's
   entry instead of starting a new one.
3. Commit `VERSION` and `CHANGELOG.md` as "Release X.Y.Z beta N", tag `vX.Y.Z-beta.N` (annotated), and push the commit and the tag.
4. Follow the run (see "Following the run"). On success, tell me in plain language: the beta web address
   (`https://<owner>.github.io/<repo>/beta/`), the pre-release page with the APK and installer, and what's in it.
   End with: "When you've tried it, run /releasenow promote."

**`promote`: put the newest beta into production.**
1. Find the newest `vX.Y.Z-beta.N` tag. Refuse if `vX.Y.Z` already exists or the beta's run didn't succeed.
2. If commits came after that beta, list them and say they won't be included (they go in the next release).
3. Tag that beta's commit `vX.Y.Z` (annotated) and push the tag. Follow the run, then give me the live address
   and the release page.

**`all`: the whole chain without waiting for testers** (for hotfixes or changes already tested).
Do the beta steps, wait for the run to finish, including the live beta smoke test, then do `promote`.
Stop and explain if anything fails.

**`status`**: show what's on production and on beta (tags, dates, web addresses), whether a draft is waiting, and
the result of the last Release and CI runs. Change nothing.

**`rollback [vX.Y.Z]`**: put an earlier production version back at the main web address. Default to the
production tag before the newest one, and confirm with me before running. Start it with
`gh workflow run release.yml -f rollback_to=vX.Y.Z` (or give me the Actions → Release → Run workflow steps if
`gh` isn't available). It doesn't change any tags or releases.

## Following the run

If `gh` is installed and signed in: find the run started by the tag (`gh run list --workflow release.yml -L 3`) and
`gh run watch <id> --exit-status`. Otherwise give me the link `https://github.com/<owner>/<repo>/actions` and
check back by listing the releases and tags.

If it fails, read the failing job's log (`gh run view <id> --log-failed`) and tell me in plain language what broke
and how you'd fix it. Common one-time fixes:
- **Pages wouldn't publish**: Settings → Pages → Source must be "GitHub Actions".
- **"throwaway key" warning on Android**: add the `ANDROID_KEYSTORE_B64`, `ANDROID_KEYSTORE_PASSWORD` and
  `ANDROID_KEY_ALIAS` secrets (Settings → Secrets and variables → Actions).
- **A tag that went wrong**: delete it locally and on GitHub (`git push --delete origin <tag>`), fix the problem, and run /releasenow again.

Never move or delete a production tag that was already promoted, and never force-push `main`.
