# Guided Nexus download run

The plan for getting the starter-pack bytes onto **your** machine while you have
bandwidth. Downloads run in a real browser you're logged into; installing
happens later, offline.

## One-time setup (on your machine)

```bash
pip install -e '.[rar]'
playwright install chromium
```

## Step 1 — log in (saves a reusable session)

```bash
modurn nexus login
```

A browser opens. Log in to Nexus, solve any Cloudflare challenge, then press
Enter in the terminal. Your session is saved to
`~/.local/share/modurn/nexus-auth.json` and reused headlessly afterward.

## Step 2 — build the modlist from the MOMW list

```bash
modurn nexus import-list \
  https://modding-openmw.com/lists/morrowind-starter-pack/ \
  -o starter-pack.yaml \
  --mods-dir ~/games/openmw/mods \
  --config ~/.config/openmw/openmw.cfg
```

This loads the list page **in your authenticated browser** (our server-side
fetches are Cloudflare-blocked; your real session isn't) and scaffolds a YAML
with every Nexus mod it links. `files:` are left blank — Step 3 auto-resolves
each mod's main file. Skim the file and delete anything you don't want.

## Step 3 — download everything (resumable)

```bash
modurn nexus download starter-pack.yaml
```

A visible browser walks each mod's manual-download page. For each file it waits
out the free-user countdown and clicks **Slow download**. If auto-click misses
(Cloudflare, markup drift), it pauses and asks you to click in the browser, then
captures the file. Progress is tracked in
`<mods_dir>/_downloads/.modurn-downloads.json`, so **re-running skips finished
files** — exactly what you want when the connection drops.

Bytes land in `<mods_dir>/_downloads/`.

## Step 4 — later, offline

```bash
modurn apply starter-pack.yaml
```

Extracts the cached archives, writes the managed `openmw.cfg` block, and records
`modurn.lock`. No network needed.

---

## What the network must reach (allowlist for a locked-down travel network)

The whole flow lives under `nexusmods.com`, plus Cloudflare and the CDN that
serves the actual file bytes:

| Host | Why |
| --- | --- |
| `www.nexusmods.com` | mod pages, files tab, manual-download page |
| `users.nexusmods.com` | login / SSO |
| `api.nexusmods.com` | (future Premium/API source) |
| `static.nexusmods.com` | page assets the download page waits on |
| `*.nexus-cdn.com` | **the file bytes** (geographic CDN nodes) |
| `challenges.cloudflare.com` | Cloudflare Turnstile during login/download |

If bytes stall at 0 while pages load fine, it's almost always `*.nexus-cdn.com`
being blocked.

## The best-guess bits we may need to tweak live

All isolated at the top of `src/modurn/sources/nexus.py`:

- `DOWNLOAD_BUTTON_SELECTORS` — tried in order; `#slowDownloadButton` is the
  long-standing free-user id. If clicks don't register, we inspect the page and
  add the current selector here.
- `MAIN_FILE_LINK_SELECTOR` — how `import-list`/main-file resolution reads
  `file_id`s off the Files tab.
- `COUNTDOWN_WAIT_MS`, `DOWNLOAD_WAIT_MS` — timing for the countdown and for
  large files (Tamriel Rebuilt is multi-GB — bump `DOWNLOAD_WAIT_MS` if needed).

Known best-guess risks we'll confirm on the first run:
- Multi-file mods (e.g. Tamriel Rebuilt data + maps): main-file auto-resolve
  grabs only the first; fill `files: [id1, id2]` explicitly for those.
- The MOMW list page may render mod links via JS; if `import-list` comes back
  short, we wait for a specific container instead of `networkidle`.
