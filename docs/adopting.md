# Adding an app to the release kit

What an app repo needs. `templates/` has a copy of every file.

| File | What it's for |
|---|---|
| `release.json` | Describes the app (below). |
| `VERSION` | The version, like `1.4.0`. `/release now` bumps it; nothing else should. |
| `.github/workflows/release.yml` | Calls the kit's pipeline when a release tag is pushed. |
| `.github/workflows/ci.yml` | Runs the kit's QA on pull requests and pushes to `main`. |
| `.claude/commands/release.md` (+ `releasenow.md`) | The `/release` command (`/release now`, `promote`, …) and its old name. Copy both unchanged. It only ever releases the repo the chat is on. |
| `package.json` + `tests/` | Playwright tests run by `npm test`. Start from `templates/tests/smoke.test.mjs` and add the app's main actions. |
| `CHANGELOG.md` | Release notes, one `## X.Y.Z (date)` section per version. |

Remove any workflow that deploys Pages or makes releases on push to `main`: releases now only happen through tags.

## release.json

```json
{
  "id": "myapp",
  "name": "My App",
  "description": "One sentence for the Windows installer.",
  "site": ".",
  "app": ".",
  "exclude": ["docs-src"],
  "prebuild": ["python3 tools/build.py"],
  "sw": "sw.js",
  "version": [{ "file": "index.html", "pattern": "const APP_VERSION = '([^']*)'" }],
  "android": { "enabled": true, "appId": "com.krazow.myapp" },
  "windows": { "enabled": true, "port": 47850 },
  "ios":     { "enabled": false },
  "macos":   { "enabled": false },
  "extras":  { "enabled": false }
}
```

- **id**: lowercase letters and digits. It's the cache prefix (`myapp-`) and the Windows folder name. Never change it after release.
- **site**: the folder published to GitHub Pages. **app**: the folder holding the PWA (`index.html`, `sw.js`,
  `manifest.webmanifest`), the same as `site` or a folder inside it.
- **exclude**: extra paths (relative to `site`) left out of the published site. Tests, tools, `src/`, `android/`,
  `windows/`, READMEs and similar are always left out.
- **prebuild**: commands run in the repo before the site is copied (generated files, for example).
- **version**: every place the app shows its version. The first `( )` group in `pattern` is replaced with the release's version.
- **android.appId**: never change it after release, or phones treat it as a different app. The beta uses `<appId>.beta`.
  Add `"camera": true` if the page uses the live camera (`getUserMedia`, for example to scan QR codes); photo
  pickers (`<input type="file" capture>`) work without it.
  Add `"requireKey": true` for an app whose APKs are already signed with a real key: without the signing secrets the
  pipeline then skips the APK instead of signing it with a throwaway key that couldn't update existing installs.
- **windows.port**: fixed and different for every app (40000–49000). The app's saved data on Windows is tied to it.
  The beta uses port + 1000.
- **Custom builds**: any platform can use `"build": "custom", "custom": "bash scripts/build-x.sh"`. The command runs
  once per channel with `CHANNEL` (`beta`/`prod`), `VERSION`, `LABEL` (e.g. `1.4.0-beta.2`), `WWW` (the built web app
  for that channel) and `OUT` (put the downloads there). Name beta downloads with "Beta". Add `"betaBuild": false` to
  build production only. iOS and macOS custom builds run on GitHub's macOS runners.

## Server apps

An app that runs as a service (a Python server on a Raspberry Pi, for example) uses `"type": "server"`. There's no
GitHub Pages site and no Android/Windows wrapper: QA runs `bash -n` on every `.sh` file plus the commands in
`"setup"` and `"test"`, and the downloads come from `"extras"` (a script that zips the app, once per channel). The
beta is a pre-release, and promotion makes the production zip the Latest release.

```json
{
  "id": "dronedash", "name": "Drone Dash", "type": "server",
  "setup": ["pip install -r requirements.txt"], "test": ["python3 tests/smoke_test.py"],
  "version": [{ "file": "server.py", "pattern": "APP_VERSION = \"([^\"]*)\"" }],
  "extras": { "enabled": true, "custom": "bash scripts/package.sh" }
}
```

## Service worker rules

```js
const CACHE_PREFIX = 'myapp-';                  // the kit makes this 'myappbeta-' in the beta
const VERSION = CACHE_PREFIX + '1.4.0';         // the kit stamps the version in
// ...
self.addEventListener('activate', e => e.waitUntil(caches.keys().then(keys =>
  Promise.all(keys.filter(k => k.startsWith(CACHE_PREFIX) && k !== VERSION).map(k => caches.delete(k))))));
```

Only delete caches that start with `CACHE_PREFIX`. Every krazow app shares `krazow.github.io`, so deleting every
other cache wipes the other apps' offline copies. Caches you want to keep across versions (map tiles, fonts) get a
name that doesn't start with `CACHE_PREFIX`. Paths in `sw.js` and `start_url`/`scope` in the manifest must be relative.

## Storage in the beta

The beta build wraps `localStorage`, `sessionStorage` and `indexedDB.open`, so the app's code needs no changes.
Only the `Storage` methods are wrapped: code that reads `localStorage.someKey` directly, or loops over
`Object.keys(localStorage)`, sees production's data. Use `getItem`/`setItem`.

## One-time GitHub settings

See the README: Pages source, workflow permissions, Android signing secrets.
