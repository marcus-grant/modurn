# modurn documentation

A declarative mod manager for [OpenMW](https://openmw.org): describe your mods
in YAML, let modurn download and install them, write the `openmw.cfg` lines, and
tie a mod list to a save so a playthrough is reproducible.

This is the documentation index. Start here, then follow the link that matches
what you're doing.

## Index

| Doc | What it covers |
| --- | --- |
| [usage.md](usage.md) | Install, the YAML schema, and every command (`plan`, `apply`, `nexus …`, `profile …`). Start here to *use* modurn. |
| [architecture.md](architecture.md) | How the code is organized, the one abstraction that matters (`ModSource`), and the design principles behind the MVP. Start here to *change* modurn. |
| [nexus-guided-run.md](nexus-guided-run.md) | The step-by-step guided browser download flow, the host allowlist for locked-down networks, and the selectors/timings we tweak against the live site. |
| [reference/morrowind-starter-pack.md](reference/morrowind-starter-pack.md) | A focused reference for making the modding-openmw.com **Morrowind Starter Pack** list work end to end, and where modurn helps vs. where you still do it by hand. |

## Status — what exists today (v0.1, MVP)

Functional now:

- **YAML modlist** with validated schema (pydantic) — the user contract.
- **Three mod sources** behind the `ModSource` seam:
  - `local` — install from archives/dirs you already have (no network).
  - `url` — direct HTTP(S) downloads (GitHub/GitLab/ModDB); fully automatic.
  - `nexus` — guided, resumable browser downloads for free Nexus accounts.
- **Install**: archive extraction (zip/7z, rar optional), wrapper-folder
  unwrap, plugin + data-dir detection.
- **openmw.cfg** writer: a reversible, per-profile *managed block* with a
  first-run `.bak`; idempotent, and multiple profiles coexist.
- **Lockfile** (`modurn.lock`) recording what `apply` did, and a
  **profile ↔ save** registry.
- **Commands**: `plan`, `apply`, `nexus login`, `nexus download`,
  `nexus import-list`, `profile list`, `profile link`.
- **Tests** for the whole network-free half (validation, local install, cfg
  writing, download-resume ledger, list parsing).

Known gaps (tracked as roadmap): groundcover/BSA cfg lines, the merge/patch
step some lists need, `settings.cfg`, and automatic multi-file resolution. See
the starter-pack reference for how these bite in practice.

## Roadmap

- **M1** — Harden the guided Nexus flow against the live site; auto-resolve a
  mod's main file id reliably (incl. multi-file mods).
- **M2** — Real profile switching: swap the active mod set and its save together.
- **M3** — Load-order control and duplicate-plugin/conflict warnings.
- **M4** — A second real backend (Nexus API for Premium, or a homelab server)
  to validate the `ModSource` seam.

## Related prior art

modurn targets the *free-account + your-own-YAML + save-association* angle. For
the broader modding-openmw.com ecosystem see
[umo](https://modding-openmw.gitlab.io/umo/) (API-based list downloader),
the [MOMW Configurator](https://gitlab.com/modding-openmw/momw-configurator),
and [momw-tools-pack](https://modding-openmw.com/mods/momw-tools-pack/).
