# Krazow release kit

One way to build, test and release every krazow app: the web app (PWA), an Android APK, a Windows installer, and
iOS/macOS where an app has its own build for them. Each app repo calls this kit, so a fix here reaches every app.

In any app repo, type **`/release now`** in a Claude chat:

| You type | What happens |
|---|---|
| `/release now` | Bumps the version, writes the changelog, pushes the `release/beta` branch. GitHub tags `vX.Y.Z-beta.N`, runs QA, builds every platform, publishes the beta and smoke-tests it live. |
| `/release promote` | Puts that beta into production: the main web address and the Latest release (with the APK and installer). |
| `/release all` | Beta, live smoke test, then production in one go (hotfixes). |
| `/release status` | What's on beta and production, and the last runs. |
| `/release rollback` | Puts the previous production version back at the main web address. |

## How a release works

Releases start from a **branch push** (`release/beta`, `release/production`, `release/rollback/vX.Y.Z`), because
Claude's cloud sessions can push branches but not tags. The pipeline creates the version tags itself. Pushing the
tags directly (`v1.2.3-beta.1`, `v1.2.3`) from your own computer works too.

1. **QA** (`qa.yml`): release checks (`VERSION`, service worker, manifest), both site variants build, the app's own
   tests (`npm test`, Playwright), and the kit's browser check. Apps also run this on every pull request (`ci.yml`).
2. **Build**: the web app twice. *Production* gets the version stamped in. *Beta* also gets:
   - storage of its own: `localStorage`/`sessionStorage` keys get a `beta:` prefix and IndexedDB databases a `beta-` prefix, so testers' real data is never touched;
   - its own cache prefix (`<id>beta-`), a BETA badge, and " Beta" added to the manifest's name.
   Then Android (`android/`), Windows (`windows/`) and any custom builds (iOS, macOS, extras), in beta and production versions.
3. **Beta**: GitHub Pages gets the last production version at the root and this beta at `/beta/`. A pre-release
   carries the beta downloads; a draft release `vX.Y.Z` holds the production downloads.
4. **Live check**: a browser opens the real beta address.
5. **Promote** (`release/production` pushed to a commit that passed beta; the pipeline tags it `vX.Y.Z`): Pages root gets this version and the draft becomes Latest.
   The same files the testers had, not a rebuild.

All krazow apps share the address `krazow.github.io`, so they share browser storage and caches. Each app's service
worker must only delete caches starting with its own `CACHE_PREFIX`. The QA checks enforce this.

## Platforms

| Platform | Production | Beta |
|---|---|---|
| Web (any device) | `https://krazow.github.io/<repo>/` | `…/<repo>/beta/` |
| Android (optional, off unless `release.json` turns it on) | `<App>-X.Y.Z.apk` (app ID from `release.json`) | `<App>-Beta-….apk`: separate app (`.beta` app ID), installs beside the real one |
| Windows | `<App>-Setup-X.Y.Z.exe`: per-user, no admin, Edge app window | `<App>-Beta-Setup-….exe`: own folder, port (+1000) and data |
| iOS | Web app (Safari → Add to Home Screen), or an app's own unsigned `.ipa` build | the `/beta/` address |
| macOS | Web app (Safari → Add to Dock, or Chrome → Install) | the `/beta/` address |

Native iOS and macOS apps need the Apple Developer Program for signing, so the kit only runs an app's own build
script for those (`"ios": {"enabled": true, "build": "custom", "custom": "..."}`).

## One-time setup in each app repo

1. **Settings → Pages → Source: GitHub Actions.**
2. **Settings → Actions → General → Workflow permissions: Read and write.**
3. **Settings → Secrets and variables → Actions:** `ANDROID_KEYSTORE_B64`, `ANDROID_KEYSTORE_PASSWORD`,
   `ANDROID_KEY_ALIAS`. Without them, APKs are signed with a throwaway key and each update needs an uninstall.
   To make a key once (keep the file and password safe; losing them means existing installs can't update):
   `keytool -genkeypair -keystore krazow.p12 -storetype PKCS12 -alias krazow -keyalg RSA -keysize 2048 -validity 10000`,
   then `base64 -w0 krazow.p12` (macOS/Linux) or `[Convert]::ToBase64String([IO.File]::ReadAllBytes("krazow.p12"))` (PowerShell)
   gives the text for `ANDROID_KEYSTORE_B64`.

See [docs/adopting.md](docs/adopting.md) for adding an app.

## Changing the kit

Apps use the kit's `v1` **branch** (`@v1`). Work on `main`; after a change passes the self-test (`self-test.yml`,
which builds `examples/sample` on every platform), bring it to the apps with `git push origin main:v1`.
Breaking changes go to a new `v2` branch, and apps move over one at a time.
