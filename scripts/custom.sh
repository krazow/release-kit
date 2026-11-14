#!/usr/bin/env bash
# Krazow release kit: runs an app's own build script for one platform, once per channel.
#   usage: custom.sh <android|windows|ios|macos|extras>
# release.json:  "<platform>": { "enabled": true, "build": "custom", "custom": "bash scripts/build-ios.sh" }
# The script gets:  CHANNEL (beta|prod), VERSION (1.2.3), LABEL (1.2.3 or 1.2.3-beta.1),
#                   WWW (folder holding this channel's built web app), OUT (folder to put the downloads in).
# For the beta channel, name things "<App> Beta" so they install beside the real app; set
# "betaBuild": false to build production only (testers then use the web beta).
set -euo pipefail
P="$1"
CMD=$(python3 -c "import json;print(json.load(open('release.json')).get('$P',{}).get('custom',''))")
BETA=$(python3 -c "import json;print(str(json.load(open('release.json')).get('$P',{}).get('betaBuild',True)).lower())")
[ -n "$CMD" ] || { echo "::error::release.json $P.custom is empty: give the command that builds it."; exit 1; }
for CH in prod beta; do
  [ "$CH" = beta ] && [ "$BETA" = false ] && continue
  export CHANNEL=$CH WWW="/tmp/www/$CH" OUT="$PWD/dist/$CH"
  if [ "$CH" = beta ]; then export LABEL="$BETA_FULL"; else export LABEL="$VERSION"; fi
  mkdir -p "$OUT"
  echo "::group::$P ($CH): $CMD"
  bash -c "$CMD"
  echo "::endgroup::"
done
ls -la dist/*
