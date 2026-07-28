# modurn

A declarative mod manager for [OpenMW](https://openmw.org). Describe your mods
in a YAML file; `modurn` downloads and installs them, writes the `openmw.cfg`
lines for you, and ties a mod list to a save so a playthrough is reproducible.

This is an early MVP. It is intentionally small and un-clever so that better
abstractions can be hoisted in incrementally later. The one seam it takes
seriously today is **how mods are sourced** (`modurn.sources`) — Nexus via a
browser now; Nexus API, a homelab backend, or a
[modding-openmw.com](https://modding-openmw.com) list importer later, each a
drop-in without touching the rest of the code.

## Why a browser for Nexus?

Nexus API downloads are Premium-only. Free accounts must click the site's
"slow download" button (countdown + Cloudflare), so `modurn` drives a real
browser with [Playwright](https://playwright.dev) and reuses a login session
you establish once. (Premium/API downloading is a planned sibling source.)

Related prior art worth knowing:
[umo](https://modding-openmw.gitlab.io/umo/) (API-based modlist downloader) and
the [MOMW Configurator](https://gitlab.com/modding-openmw/momw-configurator).
`modurn` targets the free-account + your-own-YAML + save-association angle.

## Install

```bash
pip install -e .
playwright install chromium      # only needed for the nexus source
```

## Quick start

Test the whole pipeline with no network using a mod you already have:

```yaml
# my.yaml
game:
  config: ./sandbox/openmw.cfg
  mods_dir: ./sandbox/mods
profile: test
mods:
  - name: My Mod
    source: local
    path: ~/downloads/some-mod.zip
```

```bash
modurn plan  my.yaml     # validate + show what would happen (no writes)
modurn apply my.yaml     # install, write the openmw.cfg block, write modurn.lock
```

For Nexus:

```bash
modurn nexus login       # opens a browser; log in, press Enter
modurn apply nexus.yaml  # see examples/nexus-example.yaml for the schema
```

## How it writes openmw.cfg

`modurn` only owns a marked block, keyed by profile name:

```
## >>> modurn:test (managed - do not edit inside) >>>
data="/home/you/sandbox/mods/My Mod"
content=MyMod.esp
## <<< modurn:test <<<
```

Everything outside the markers is left untouched, a `.bak` is written before
the first change, and re-applying replaces just that block — so it is
idempotent and reversible. Different profiles get different blocks and coexist.

## Commands

| Command | What it does |
| --- | --- |
| `modurn plan <yaml>` | Validate the list; print the install plan. No network, no writes. |
| `modurn apply <yaml>` | Fetch → install → write the cfg block → write `modurn.lock`. |
| `modurn nexus login` | One-time interactive Nexus sign-in; session is saved for reuse. |
| `modurn profile list` | Show known profiles and their associated saves. |
| `modurn profile link <name> <save>` | Associate a profile with a `.omwsave`. |

## Project layout

```
src/modurn/
  models.py        # the YAML schema (pydantic) — the user contract
  modlist.py       # load + validate a modlist
  sources/         # THE seam: base.ModSource protocol + local/nexus impls + registry
  install.py       # extract archives, detect data dir + plugins
  openmw_cfg.py    # safe, reversible managed-block writer
  lockfile.py      # modurn.lock — record of what apply did
  profiles.py      # profile <-> save registry
  cli.py           # orchestration only; logic lives in the modules above
```

## Roadmap

- **M0 (this MVP)** — YAML schema, `ModSource` seam, local + Nexus-browser
  sources, extraction, safe cfg writer, lockfile, profile/save records.
- **M1** — Harden the Nexus flow (session-expiry detection, Cloudflare/Turnstile
  handling, retries) and auto-resolve a mod's main file id.
- **M2** — Real profile switching: swap the active mod set and its save together.
- **M3** — Load-order & conflict awareness (duplicate-plugin warnings, ordering).
- **M4** — A second real backend (Nexus API for Premium, or a homelab server)
  to validate the `ModSource` seam; a `modding-openmw.com` list importer.

## Development

```bash
pip install -e '.[dev]'
pytest
```

The tests cover the network-free half of the pipeline (validation, local
install, cfg writing) so refactors stay honest without needing Nexus.
