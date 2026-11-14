#!/usr/bin/env python3
"""Krazow release kit: the build logic the pipeline runs for every app.

Usage (run from the app repo's root unless --src says otherwise):
  kit.py info                     -> works out the mode/version from the git ref, writes GitHub outputs
  kit.py check                    -> QA checks that need no browser (version, service worker, release.json)
  kit.py build-web --channel beta|prod --src DIR --out DIR
                                  -> copies the site into OUT with the version and channel stamped in
  kit.py notes VERSION            -> release notes for VERSION from CHANGELOG.md (or git log)
  kit.py icons PNG --android-res DIR | --ico FILE
"""
import json, os, re, shutil, struct, subprocess, sys
from pathlib import Path

DEFAULT_EXCLUDE = [
    ".git", ".github", ".claude", "node_modules", "tests", "test-results", "playwright-report",
    "android", "windows", "ios", "macos", "tools", "src", "release.json", "VERSION", "package.json",
    "package-lock.json", ".gitignore", ".gitattributes", "README.md", "CHANGELOG.md", "TODO.md", "CLAUDE.md",
]
TAG_BETA = re.compile(r"^v(\d+\.\d+\.\d+)-beta\.(\d+)$")
TAG_PROD = re.compile(r"^v(\d+\.\d+\.\d+)$")


def die(msg):
    print(f"::error::{msg}")
    sys.exit(1)


def load_cfg(src="."):
    p = Path(src) / "release.json"
    if not p.exists():
        die("release.json is missing. Copy templates/release.json from krazow/release-kit and fill it in.")
    cfg = json.loads(p.read_text())
    for k in ("id", "name"):
        if not cfg.get(k):
            die(f"release.json needs \"{k}\".")
    if not re.fullmatch(r"[a-z][a-z0-9]*", cfg["id"]):
        die('release.json "id" must be lowercase letters and digits only (it becomes the cache and storage prefix).')
    cfg.setdefault("site", ".")
    cfg.setdefault("app", cfg["site"])
    cfg.setdefault("exclude", [])
    cfg.setdefault("version", [])
    cfg.setdefault("sw", "sw.js")
    cfg.setdefault("prebuild", [])
    for k in ("android", "windows", "ios", "macos", "extras"):
        cfg.setdefault(k, {})
        cfg[k].setdefault("enabled", False)
    return cfg


def git(*args, cwd="."):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True).stdout.strip()


def tags_matching(rx, cwd="."):
    out = [t for t in git("tag", "--list", "v*", cwd=cwd).split() if rx.match(t)]
    def key(t):
        m = rx.match(t)
        nums = [int(x) for x in m.group(1).split(".")]
        return nums + ([int(m.group(2))] if rx is TAG_BETA else [])
    return sorted(out, key=key)


def gh_out(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{k}={v}" for k, v in kv.items()]
    print("\n".join(lines))
    if path:
        with open(path, "a") as f:
            f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------- info
def cmd_info(_args):
    cfg = load_cfg()
    ref = os.environ.get("GITHUB_REF_NAME", "")
    rollback = os.environ.get("ROLLBACK_TO", "").strip()
    create_tag = ""
    # Release requests can come as branch pushes (Claude's cloud sessions can push branches but not tags):
    #   release/beta -> next beta of VERSION, release/production -> promote the beta at this commit,
    #   release/rollback/vX.Y.Z -> put vX.Y.Z back. The pipeline then makes the tag itself.
    all_tags = git("tag", "--list", "v*").split()
    if ref.startswith("release/rollback/"):
        rollback = ref.split("/", 2)[2]
    elif ref == "release/beta":
        v = Path("VERSION").read_text().strip() if Path("VERSION").exists() else ""
        if not re.fullmatch(r"\d+\.\d+\.\d+", v):
            die("VERSION must hold a version like 1.2.3.")
        if f"v{v}" in all_tags:
            die(f"v{v} is already released. Bump VERSION (run /releasenow again) for a new beta.")
        nums = [int(TAG_BETA.match(x).group(2)) for x in all_tags if TAG_BETA.match(x) and TAG_BETA.match(x).group(1) == v]
        ref = create_tag = f"v{v}-beta.{max(nums, default=0) + 1}"
    elif ref == "release/production":
        head = git("rev-parse", "HEAD")
        here = [x for x in all_tags if TAG_BETA.match(x) and git("rev-list", "-n1", x) == head]
        if not here:
            die("release/production must point at a commit that went through beta. Run /releasenow first, then /releasenow promote.")
        here.sort(key=lambda x: [int(n) for n in TAG_BETA.match(x).group(1).split(".")] + [int(TAG_BETA.match(x).group(2))])
        v = TAG_BETA.match(here[-1]).group(1)
        if f"v{v}" in all_tags:
            die(f"v{v} is already in production.")
        ref = create_tag = f"v{v}"
    if create_tag:
        subprocess.run(["git", "-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                        "tag", "-a", create_tag, "-m", f"Release {create_tag}"], check=True)
    # Only tags made with the kit count (older releases have no release.json to build from).
    kit_made = lambda t: subprocess.run(["git", "cat-file", "-e", f"{t}:release.json"], capture_output=True).returncode == 0
    prod_tags = [t for t in tags_matching(TAG_PROD) if kit_made(t)]
    beta_tags = [t for t in tags_matching(TAG_BETA) if kit_made(t)]
    if rollback:
        if not TAG_PROD.match(rollback) or rollback not in prod_tags:
            die(f"Rollback target {rollback!r} isn't a production tag. Production tags: {', '.join(prod_tags) or 'none yet'}.")
        mode, version, root_tag = "rollback", TAG_PROD.match(rollback).group(1), rollback
        beta_tag = beta_tags[-1] if beta_tags else ""
    elif TAG_BETA.match(ref):
        mode, version = "beta", TAG_BETA.match(ref).group(1)
        older = [t for t in prod_tags if t != f"v{version}"]
        root_tag = older[-1] if older else ""
        beta_tag = ref
    elif TAG_PROD.match(ref):
        mode, version = "promote", TAG_PROD.match(ref).group(1)
        sha = git("rev-list", "-n1", ref)
        betas_here = [t for t in beta_tags if git("rev-list", "-n1", t) == sha and t.startswith(f"v{version}-beta.")]
        if not betas_here:
            die(f"{ref} isn't on a commit that went through beta. Run /releasenow first, then /releasenow promote.")
        root_tag, beta_tag = ref, beta_tags[-1]
    else:
        die(f"'{ref}' isn't a release tag. Beta tags look like v1.2.3-beta.1 and production tags like v1.2.3.")
    file_version = Path("VERSION").read_text().strip() if Path("VERSION").exists() else ""
    if mode in ("beta", "promote") and file_version != version:
        die(f"The VERSION file says {file_version or 'nothing'} but the tag is for {version}. /releasenow keeps these in step.")
    app_sub = os.path.relpath(cfg["app"], cfg["site"])
    gh_out(mode=mode, version=version, app_sub=app_sub, create_tag=create_tag, root_tag=root_tag, beta_tag=beta_tag,
           beta_full=(TAG_BETA.match(beta_tag).group(0)[1:] if beta_tag else ""),
           id=cfg["id"], name=cfg["name"],
           android=str(cfg["android"]["enabled"]).lower(), windows=str(cfg["windows"]["enabled"]).lower(),
           ios=str(cfg["ios"]["enabled"]).lower(), macos=str(cfg["macos"]["enabled"]).lower(),
           extras=str(cfg["extras"]["enabled"]).lower())


# ---------------------------------------------------------------- check
SW_VERSION = re.compile(r"const VERSION = CACHE_PREFIX \+ '([^']*)'")
SW_PREFIX = re.compile(r"const CACHE_PREFIX = '([^']*)'")


def cmd_check(_args):
    cfg = load_cfg()
    problems = []
    if not Path("VERSION").exists() or not re.fullmatch(r"\d+\.\d+\.\d+", Path("VERSION").read_text().strip()):
        problems.append("VERSION must exist and hold a version like 1.2.3.")
    sw = Path(cfg["app"]) / cfg["sw"]
    if not sw.exists():
        problems.append(f"Service worker {sw} is missing (set \"sw\" in release.json).")
    else:
        t = sw.read_text()
        m = SW_PREFIX.search(t)
        if not m:
            problems.append(f"{sw} needs `const CACHE_PREFIX = '{cfg['id']}-';`")
        elif m.group(1) != cfg["id"] + "-":
            problems.append(f"{sw}: CACHE_PREFIX should be '{cfg['id']}-' (it's '{m.group(1)}').")
        if not SW_VERSION.search(t):
            problems.append(f"{sw} needs `const VERSION = CACHE_PREFIX + '<version>';`")
        if "startsWith(CACHE_PREFIX)" not in t:
            problems.append(f"{sw} must only delete its own caches: filter with k.startsWith(CACHE_PREFIX). "
                            "All krazow.github.io apps share one cache storage.")
    for v in cfg["version"]:
        f = Path(v["file"])
        if not f.exists() or not re.search(v["pattern"], f.read_text()):
            problems.append(f"Version pattern {v['pattern']!r} not found in {v['file']}.")
    man = Path(cfg["app"]) / "manifest.webmanifest"
    if man.exists():
        try:
            mj = json.loads(man.read_text())
            for k in ("start_url", "scope"):
                if str(mj.get(k, ".")).startswith(("/", "http")):
                    problems.append(f"manifest.webmanifest {k} must be relative (like \".\") so the app also works under /beta/.")
        except ValueError:
            problems.append("manifest.webmanifest isn't valid JSON.")
    if cfg["windows"]["enabled"] and cfg["windows"].get("build", "kit") == "kit" and not cfg["windows"].get("port"):
        problems.append('windows.port is required (a fixed number between 40000 and 49000, different for each app).')
    if cfg["android"]["enabled"] and cfg["android"].get("build", "kit") == "kit" and not cfg["android"].get("appId"):
        problems.append("android.appId is required (like com.krazow.myapp).")
    if problems:
        for p in problems:
            print(f"::error::{p}")
        sys.exit(1)
    print("Release checks passed.")


# ---------------------------------------------------------------- build-web
BETA_HEAD = """<script>/* release-kit: beta keeps its own storage so testers' real data is never touched */
(function(){try{var P='beta:';var S=Storage.prototype,g=S.getItem,s=S.setItem,r=S.removeItem,k=S.key;
var L=Object.getOwnPropertyDescriptor(S,'length').get;
function keys(st){var a=[],n=L.call(st);for(var i=0;i<n;i++){var x=k.call(st,i);if(x&&x.indexOf(P)===0)a.push(x.slice(P.length));}return a;}
Object.defineProperty(S,'length',{configurable:true,get:function(){return keys(this).length}});
S.getItem=function(x){return g.call(this,P+x)};S.setItem=function(x,v){return s.call(this,P+x,v)};
S.removeItem=function(x){return r.call(this,P+x)};S.key=function(i){return keys(this)[i]==null?null:keys(this)[i]};
S.clear=function(){var st=this;keys(st).forEach(function(x){r.call(st,P+x)})};
if(window.indexedDB){var o=indexedDB.open.bind(indexedDB),d=indexedDB.deleteDatabase.bind(indexedDB);
indexedDB.open=function(n,v){return v===undefined?o('beta-'+n):o('beta-'+n,v)};indexedDB.deleteDatabase=function(n){return d('beta-'+n)};}
document.addEventListener('DOMContentLoaded',function(){var b=document.createElement('div');b.textContent='BETA';
b.setAttribute('style','position:fixed;z-index:2147483647;top:calc(env(safe-area-inset-top,0px) + 4px);left:50%;transform:translateX(-50%);background:#d32f2f;color:#fff;font:700 11px/1 system-ui,sans-serif;letter-spacing:.1em;padding:4px 8px;border-radius:999px;pointer-events:none;opacity:.85');
document.body.appendChild(b);});}catch(e){}})();</script>"""

PROD_SW_GUARD = ("/* release-kit: leave the beta copy (under /beta/) to its own service worker */\n"
                 "self.addEventListener('fetch', function (e) { if (new URL(e.request.url).pathname.indexOf('/beta/') !== -1) e.stopImmediatePropagation(); });\n")


def stamp_text(text, pattern, value):
    rx = re.compile(pattern)
    m = rx.search(text)
    if not m:
        return text, False
    out = rx.sub(lambda mm: mm.group(0)[: mm.start(1) - mm.start(0)] + value + mm.group(0)[mm.end(1) - mm.start(0):], text)
    return out, True


def cmd_build_web(args):
    channel, src, out = args.channel, Path(args.src).resolve(), Path(args.out)
    cfg = load_cfg(src)
    version = Path(src / "VERSION").read_text().strip()
    label = version if channel == "prod" else (args.label or version + "-beta")
    for cmd in cfg["prebuild"]:
        print(f"$ {cmd}")
        subprocess.run(cmd, shell=True, cwd=src, check=True)
    site = src / cfg["site"]
    exclude = set(DEFAULT_EXCLUDE) | set(cfg["exclude"])
    if out.exists():
        shutil.rmtree(out)
    def ignore(d, names):
        rel = Path(d).resolve().relative_to(site.resolve())
        return [n for n in names if (str(rel / n) if str(rel) != "." else n) in exclude or n in (".git", "node_modules")]
    shutil.copytree(site, out, ignore=ignore)
    app_rel = Path(cfg["app"]).resolve().relative_to(site.resolve()) if (src / cfg["app"]).resolve() != site.resolve() else Path(".")
    app_out = out / app_rel
    # version stamps (paths in release.json are relative to the repo; map them into the copy)
    for v in cfg["version"]:
        f = (src / v["file"]).resolve()
        try:
            target = out / f.relative_to(site.resolve())
        except ValueError:
            continue
        if target.exists():
            t, ok = stamp_text(target.read_text(), v["pattern"], label)
            target.write_text(t)
    sw = app_out / cfg["sw"]
    t = sw.read_text()
    t, _ = stamp_text(t, SW_VERSION.pattern, label)
    if channel == "beta":
        t, _ = stamp_text(t, SW_PREFIX.pattern, cfg["id"] + "beta-")
    else:
        t = PROD_SW_GUARD + t
    sw.write_text(t)
    if channel == "beta":
        for html in out.rglob("*.html"):
            h = html.read_text()
            h2 = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + BETA_HEAD, h, count=1, flags=re.I)
            html.write_text(h2 if h2 != h else BETA_HEAD + h)
        for man in out.rglob("*.webmanifest"):
            try:
                mj = json.loads(man.read_text())
            except ValueError:
                continue
            for k in ("name", "short_name"):
                if k in mj and not mj[k].endswith(" Beta"):
                    mj[k] += " Beta"
            if "id" in mj:
                mj["id"] = str(mj["id"]).rstrip("/") + "-beta"
            man.write_text(json.dumps(mj, indent=2, ensure_ascii=False))
    (out / ".nojekyll").write_text("")
    print(f"Built {channel} site for {cfg['name']} {label} in {out} (app folder: {app_rel})")
    gh_out(app_dir=str(app_out))


# ---------------------------------------------------------------- notes
def cmd_notes(args):
    v = args.version
    cl = Path("CHANGELOG.md")
    if cl.exists():
        lines = cl.read_text().splitlines()
        start = None
        for i, l in enumerate(lines):
            if re.match(rf"^##\s*\[?v?{re.escape(v)}\]?(\s|$)", l):
                start = i
                break
        if start is not None:
            body = []
            for l in lines[start + 1:]:
                if re.match(r"^##\s", l):
                    break
                body.append(l)
            print("\n".join(body).strip())
            return
    prev = tags_matching(TAG_PROD)
    rng = f"{prev[-1]}..HEAD" if prev else "HEAD"
    print(git("log", "--no-merges", "--format=- %s", rng) or "- First release with the release kit.")


# ---------------------------------------------------------------- icons
def best_icon(app_dir):
    man = Path(app_dir) / "manifest.webmanifest"
    best, size = None, 0
    if man.exists():
        try:
            for ic in json.loads(man.read_text()).get("icons", []):
                if not str(ic.get("src", "")).endswith(".png") or "maskable" in str(ic.get("purpose", "")):
                    continue
                s = max(int(x.split("x")[0]) for x in str(ic.get("sizes", "0x0")).split())
                p = Path(app_dir) / ic["src"]
                if s > size and p.exists():
                    best, size = p, s
        except (ValueError, KeyError):
            pass
    if not best:
        pngs = sorted(Path(app_dir).rglob("*.png"), key=lambda p: p.stat().st_size, reverse=True)
        best = pngs[0] if pngs else None
    return best


def cmd_icons(args):
    from PIL import Image
    src = Path(args.png) if args.png.endswith(".png") else best_icon(args.png)
    if not src:
        die("No PNG icon found for the app (add one to manifest.webmanifest).")
    im = Image.open(src).convert("RGBA")
    if args.android_res:
        for d, s in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
            p = Path(args.android_res) / f"mipmap-{d}"
            p.mkdir(parents=True, exist_ok=True)
            im.resize((s, s), Image.LANCZOS).save(p / "ic_launcher.png")
    if args.ico:
        im.save(args.ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Icons made from {src}")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info")
    sub.add_parser("check")
    b = sub.add_parser("build-web")
    b.add_argument("--channel", choices=["beta", "prod"], required=True)
    b.add_argument("--src", default=".")
    b.add_argument("--out", required=True)
    b.add_argument("--label", default="")
    n = sub.add_parser("notes")
    n.add_argument("version")
    i = sub.add_parser("icons")
    i.add_argument("png")
    i.add_argument("--android-res")
    i.add_argument("--ico")
    a = ap.parse_args()
    {"info": cmd_info, "check": cmd_check, "build-web": cmd_build_web, "notes": cmd_notes, "icons": cmd_icons}[a.cmd](a)


if __name__ == "__main__":
    main()
