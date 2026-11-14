#!/usr/bin/env bash
# Krazow release kit: builds the Windows installers (production + beta) from /tmp/www/{prod,beta}.
# Uses the kit's shared launcher unless release.json says "windows": {"build": "custom", "custom": "..."}.
# The beta installs as "<App> Beta" in its own folder, on its own port (port + 1000), with its own data.
set -euo pipefail
KIT="$(cd "$(dirname "$0")/.." && pwd)"
cfg() { python3 -c "import json;c=json.load(open('release.json'));v=c$1;print(v if v is not None else '')" 2>/dev/null || true; }
BUILD=$(cfg ".get('windows',{}).get('build','kit')")
if [ "$BUILD" = custom ]; then bash "$KIT/scripts/custom.sh" windows; exit 0; fi

NAME=$(cfg "['name']")
ID=$(cfg "['id']")
PORT=$(cfg "['windows']['port']")
DESC=$(cfg ".get('description') or (c['name'] + ', an app by krazow')")
FILE=$(echo "$NAME" | tr -cd 'A-Za-z0-9')
URL="https://${GITHUB_REPOSITORY_OWNER}.github.io/${GITHUB_REPOSITORY#*/}/"
W=/tmp/winbuild
for CH in prod beta; do
  rm -rf "$W" && cp -r "$KIT/windows" "$W"
  mkdir -p "$W/app/web" "$W/setup/payload" "dist/$CH"
  cp -r /tmp/www/$CH/. "$W/app/web/"
  if [ $CH = beta ]; then AN="$NAME Beta"; AID="${ID}beta"; P=$((PORT + 1000)); VER="$BETA_FULL"; OUTF="$FILE-Beta-Setup-$BETA_FULL.exe"; U="${URL}beta/"
  else AN="$NAME"; AID="$ID"; P=$PORT; VER="$VERSION"; OUTF="$FILE-Setup-$VERSION.exe"; U="$URL"; fi
  FV=$(echo "$VERSION.0.0.0" | cut -d. -f1-4)
  python3 "$KIT/scripts/kit.py" icons "/tmp/www/$CH" --ico "$W/setup/payload/app.ico"
  python3 "$W/tools/mkrsrc.py" "$W/setup/payload/app.ico" "$W/app/rsrc_windows_amd64.syso" "$AN" "$FV" "$AN"
  python3 "$W/tools/mkrsrc.py" "$W/setup/payload/app.ico" "$W/setup/rsrc_windows_amd64.syso" "$AN Setup" "$FV" "$AN"
  X="krazow/webapp/internal/win"
  q() { printf '"%s"' "$(printf '%s' "$1" | tr -d '"')"; } # Go's -ldflags accepts double-quoted values
  LD="-s -w -H=windowsgui -X main.version=$VER -X $(q "$X.AppName=$AN") -X $X.ID=$AID -X $X.PortText=$P -X $X.HomeURL=$U -X $(q "$X.Desc=$DESC")"
  (cd "$W" && export GOOS=windows GOARCH=amd64 CGO_ENABLED=0 \
    && go vet ./app ./internal/... \
    && go build -trimpath -ldflags "$LD" -o setup/payload/app.exe ./app \
    && go vet ./setup \
    && go build -trimpath -ldflags "$LD" -o "/tmp/$OUTF" ./setup)
  mv "/tmp/$OUTF" "dist/$CH/$OUTF"
done
ls -la dist/*
