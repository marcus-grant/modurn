# modurn

A declarative mod manager for [OpenMW](https://openmw.org). Describe your mods
in a YAML file; `modurn` downloads and installs them, writes the `openmw.cfg`
lines for you, and ties a mod list to a save so a playthrough is reproducible.

Early MVP: intentionally small and un-clever so better abstractions can be
hoisted in incrementally later. The one seam it takes seriously today is **how
mods are sourced** (`modurn.sources`) — Nexus via a browser now; Nexus API, a
homelab backend, or a [modding-openmw.com](https://modding-openmw.com) importer
later, each a drop-in without touching the rest of the code.

Nexus API downloads are Premium-only, so for free accounts modurn drives a real
browser ([Playwright](https://playwright.dev)) and reuses a login session you
establish once.

## 📖 Documentation

**Full docs live in [`docs/`](docs/README.md) — start with the
[documentation index](docs/README.md).**

| I want to… | Go to |
| --- | --- |
| Install and use modurn (schema + commands) | [docs/usage.md](docs/usage.md) |
| Understand / change the code | [docs/architecture.md](docs/architecture.md) |
| Run the guided Nexus download flow | [docs/nexus-guided-run.md](docs/nexus-guided-run.md) |
| Make the Morrowind Starter Pack list work | [docs/reference/morrowind-starter-pack.md](docs/reference/morrowind-starter-pack.md) |

## Quick start

```bash
pip install -e .
playwright install chromium      # only for the nexus source

# fully local, no network:
modurn plan  examples/local-example.yaml
modurn apply examples/local-example.yaml

# nexus (bandwidth-first, resumable):
modurn nexus login
modurn nexus import-list <list-url> -o list.yaml
modurn nexus download list.yaml      # grab bytes now; re-run to resume
modurn apply list.yaml               # later, offline: extract + write cfg
```

## Status

v0.1 MVP. Working: YAML modlist, `local` + guided `nexus` sources, archive
extraction, a reversible per-profile `openmw.cfg` managed block, lockfile, and
profile↔save records. See the [documentation index](docs/README.md#status--what-exists-today-v01-mvp)
for the full status and roadmap.

## Development

```bash
pip install -e '.[dev]'
pytest
```

Tests cover the network-free half of the pipeline (validation, local install,
cfg writing, download-resume ledger, list parsing) so refactors stay honest
without needing Nexus.

## License

MIT
