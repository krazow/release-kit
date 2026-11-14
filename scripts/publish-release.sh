#!/usr/bin/env bash
# Krazow release kit: creates the GitHub releases.
#   beta:    a pre-release for the beta tag with the beta downloads, plus a draft vX.Y.Z holding the production downloads
#   promote: publishes that draft as the Latest release
set -euo pipefail
REPO="$GITHUB_REPOSITORY"
TAG="v$VERSION"
python3 .kit/scripts/kit.py notes "$VERSION" > /tmp/changes.md
shopt -s nullglob
beta_files=(dist/beta/*)
prod_files=(dist/prod/*)

if [ "$MODE" = beta ]; then
  {
    echo "**Beta for testing.** Your real app and its data aren't touched: the beta keeps its own storage and installs as a separate app."
    echo
    [ -n "${URL:-}" ] && echo "- **Web:** ${URL%/}/beta/"
    for f in "${beta_files[@]}"; do echo "- **$(basename "$f")**"; done
    echo
    echo "## What's new"
    cat /tmp/changes.md
  } > /tmp/beta.md
  gh release delete "$BETA_TAG" --repo "$REPO" --yes 2>/dev/null || true
  gh release create "$BETA_TAG" --repo "$REPO" --prerelease --verify-tag \
    --title "$NAME $VERSION beta (${BETA_TAG##*-})" --notes-file /tmp/beta.md "${beta_files[@]}"

  # The production release waits as a draft until /release promote. Replace any older draft for this version.
  if gh release view "$TAG" --repo "$REPO" --json isDraft -q .isDraft 2>/dev/null | grep -q true; then
    gh release delete "$TAG" --repo "$REPO" --yes
  fi
  {
    [ -n "${URL:-}" ] && echo "- **Web:** ${URL%/}/"
    for f in "${prod_files[@]}"; do echo "- **$(basename "$f")**"; done
    echo
    echo "## What's new"
    cat /tmp/changes.md
  } > /tmp/prod.md
  gh release create "$TAG" --repo "$REPO" --draft --target "$GITHUB_SHA" \
    --title "$NAME $VERSION" --notes-file /tmp/prod.md "${prod_files[@]}"
  echo "Beta published. Production $TAG is waiting as a draft for /release promote." >> "$GITHUB_STEP_SUMMARY"

elif [ "$MODE" = promote ]; then
  if gh release view "$TAG" --repo "$REPO" --json isDraft -q .isDraft 2>/dev/null | grep -q true; then
    gh release edit "$TAG" --repo "$REPO" --draft=false --latest --tag "$TAG"
  elif gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
    echo "$TAG is already published."
  else
    echo "::warning::No draft release was waiting for $TAG, so this release has the web app only."
    gh release create "$TAG" --repo "$REPO" --verify-tag --latest --title "$NAME $VERSION" --notes-file /tmp/changes.md
  fi
  echo "Production $TAG is published${URL:+ and live at ${URL%/}/}" >> "$GITHUB_STEP_SUMMARY"
fi
