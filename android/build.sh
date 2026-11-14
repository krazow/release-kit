#!/usr/bin/env bash
# Krazow release kit: builds the Android APKs (production + beta) from /tmp/www/{prod,beta}.
# Uses the kit's shared wrapper unless release.json says "android": {"build": "custom", "custom": "..."}.
# Signing: the repo secrets ANDROID_KEYSTORE_B64 (base64 of a .p12/.jks), ANDROID_KEYSTORE_PASSWORD, ANDROID_KEY_ALIAS.
set -euo pipefail
KIT="$(cd "$(dirname "$0")/.." && pwd)"
cfg() { python3 -c "import json,sys;c=json.load(open('release.json'));v=c$1;print(v if v is not None else '')" 2>/dev/null || true; }
BUILD=$(cfg ".get('android',{}).get('build','kit')")
if [ "$BUILD" = custom ]; then bash "$KIT/scripts/custom.sh" android; exit 0; fi

NAME=$(cfg "['name']")
FILE=$(echo "$NAME" | tr -cd 'A-Za-z0-9')
APPID=$(cfg "['android']['appId']")
IFS=. read -r MA MI PA <<< "$VERSION"
CODE=$((MA * 10000 + MI * 100 + PA))
BT=$(ls -d "$ANDROID_HOME"/build-tools/* | sort -V | tail -1)

REQUIRE=$(cfg ".get('android',{}).get('requireKey',False)")
if [ -z "${KS_B64:-}" ] && [ "$REQUIRE" = True ]; then
  echo "::warning::No Android signing key is set up, and this app's APKs must keep their existing key (requireKey), so no APK is built this time. Add the ANDROID_KEYSTORE_B64, ANDROID_KEYSTORE_PASSWORD and ANDROID_KEY_ALIAS secrets."
  mkdir -p dist; exit 0
fi
if [ -n "${KS_B64:-}" ]; then
  echo "$KS_B64" | base64 -d > /tmp/ks
else
  echo "::warning::No Android signing key is set up (secrets ANDROID_KEYSTORE_B64, ANDROID_KEYSTORE_PASSWORD, ANDROID_KEY_ALIAS). This build uses a throwaway key, so installing the next build will need an uninstall first, which deletes the app's data on the phone. Add the secrets to fix this."
  export KS_PASS=throwaway KS_ALIAS=app
  keytool -genkeypair -keystore /tmp/ks -storetype PKCS12 -storepass "$KS_PASS" -alias "$KS_ALIAS" -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=$NAME" >/dev/null 2>&1
fi

for CH in prod beta; do
  W=/tmp/android-$CH
  rm -rf "$W" && cp -r "$KIT/android/project" "$W"
  mkdir -p "$W/app/src/main/assets/www" && cp -r /tmp/www/$CH/. "$W/app/src/main/assets/www/"
  python3 "$KIT/scripts/kit.py" icons "/tmp/www/$CH" --android-res "$W/app/src/main/res"
  if [ "$(cfg ".get('android',{}).get('camera',False)")" = True ]; then
    sed -i 's#<uses-permission android:name="android.permission.INTERNET" />#&\n    <uses-permission android:name="android.permission.CAMERA" />#' "$W/app/src/main/AndroidManifest.xml"
  fi
  if [ $CH = beta ]; then ID="$APPID.beta"; AN="$NAME Beta"; VN="$BETA_FULL"; OUTF="$FILE-Beta-$BETA_FULL.apk"
  else ID="$APPID"; AN="$NAME"; VN="$VERSION"; OUTF="$FILE-$VERSION.apk"; fi
  (cd "$W" && gradle --no-daemon --console=plain assembleRelease -PappId="$ID" -PappName="$AN" -PversionName="$VN" -PversionCode="$CODE")
  mkdir -p "dist/$CH"
  "$BT/zipalign" -f -p 4 "$W/app/build/outputs/apk/release/app-release-unsigned.apk" /tmp/aligned.apk
  "$BT/apksigner" sign --ks /tmp/ks --ks-pass env:KS_PASS --ks-key-alias "$KS_ALIAS" --key-pass env:KS_PASS --out "dist/$CH/$OUTF" /tmp/aligned.apk
  "$BT/apksigner" verify "dist/$CH/$OUTF"
done
rm -f /tmp/ks
ls -la dist/*
