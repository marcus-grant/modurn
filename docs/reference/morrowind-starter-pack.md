# Reference: the Morrowind Starter Pack list

A focused guide to getting the modding-openmw.com
[**Morrowind Starter Pack**](https://modding-openmw.com/lists/morrowind-starter-pack/)
running with modurn — what modurn does for you today, and the parts of this
particular list that still need care or manual steps.

> Scope note: the site is behind Cloudflare, so the exact per-mod file ids and
> ordering are confirmed **during** `nexus import-list` in your own browser, not
> pre-baked here. This doc covers the *shape* of the list and its known
> gotchas so nothing surprises us on the guided run.

## What this list is

A curated, art-style-preserving base for OpenMW: vanilla bug/consistency
patches (all official plugins + fixes), the **Tamriel Rebuilt** and **Project
Tamriel** landmasses, quality-of-life mods, and select graphical mods that use
OpenMW features (normal mapping, shaders, distant land, groundcover). It
deliberately excludes rebalances, city/landscape revamps, NPC overhauls, and UI
mods — it's a *foundation* you build on.

That composition matters for modurn because the list spans several install
shapes: plain `content=` plugins, big **multi-file** mods, **BSA-archived**
mods, **groundcover** mods, and a final **merge/patch** step.

## The fast path

```bash
modurn nexus login
modurn nexus import-list \
  https://modding-openmw.com/lists/morrowind-starter-pack/ \
  -o starter-pack.yaml
# review starter-pack.yaml (see gotchas below), then:
modurn nexus download starter-pack.yaml     # resumable
modurn apply starter-pack.yaml              # later, offline
```

See [../nexus-guided-run.md](../nexus-guided-run.md) for the network allowlist
and the selectors we tweak live.

## What modurn handles today

- Downloading each mod's file(s) via the guided browser flow, **resumably**.
- Extracting zip/7z (rar with the `[rar]` extra), unwrapping a single wrapper
  folder, and detecting plugins + the `data=` directory.
- Writing the `data=` and `content=` lines into a reversible managed block in
  `openmw.cfg`, plus a `modurn.lock` for reproducibility.

## Gotchas specific to this list

### 1. Load order is not optional

MOMW lists are ordered; plugins must load in that order or you get bugs/crashes.
modurn currently appends `content=` lines **in modlist order**, so *the order of
`mods:` in the YAML is the load order*. Keep the import order, and for a mod with
several plugins set an explicit `content: [...]` to pin their sequence.

Roadmap M3 adds explicit ordering + duplicate-plugin warnings; until then, the
YAML order is the source of truth.

### 2. Multi-file mods (Tamriel Rebuilt / Project Tamriel)

These ship several files that must all be installed and ordered:
`Tamriel_Data` first (the shared assets), then the landmass plugins
(`TR_Mainland`, `PT_Data`/province plugins, etc.). Auto main-file resolution
grabs only the **first** main file, which is wrong here.

Fix in the YAML: list the file ids explicitly, and give the mod an explicit
`content:` order. Also note these are **multi-GB** — if a download times out,
bump `DOWNLOAD_WAIT_MS` in `sources/nexus.py` and re-run (it resumes).

### 3. Groundcover (grass) mods need a different cfg line

OpenMW loads grass via `groundcover=<Plugin.esp>` in `openmw.cfg`, **not**
`content=`. modurn does not yet emit `groundcover=` lines, so any grass plugin
in this list needs that line added by hand after `apply` (inside or after the
managed block). Tracked as a roadmap gap — the managed-block mechanism will
generalize to line kinds beyond `data=`/`content=`.

### 4. BSA-archived mods need `fallback-archive=`

Some mods ship a `.bsa` instead of loose files; OpenMW needs a
`fallback-archive=<Name.bsa>` line. modurn detects loose plugins but does not
yet emit `fallback-archive=`. If a mod's textures/meshes don't show up, check
for a `.bsa` in its folder and add the line manually. Also a roadmap gap.

### 5. The merge/patch step (momw-tools-pack)

This list expects a final generated patch — a merged plugin (via
[tes3merge](https://www.nexusmods.com/morrowind/mods/49266) or
[DeltaPlugin](https://gitlab.com/bmwinger/delta-plugin)) and sometimes
navmesh/other outputs from the
[momw-tools-pack](https://modding-openmw.com/mods/momw-tools-pack/). modurn does
**not** run this yet. For now, after `apply`, run the merge tool yourself and
add its output plugin to the end of the load order.

Roadmap: a post-`apply` stage that shells out to these tools.

### 6. settings.cfg (distant land, shaders, groundcover toggles)

The list's graphical results depend on `settings.cfg` values (distant land,
shader settings, `[Groundcover] enabled=true`). modurn manages `openmw.cfg`
only. Apply the recommended `settings.cfg` from the list page manually, or use
the [MOMW Configurator](https://gitlab.com/modding-openmw/momw-configurator) for
that half.

## Summary: modurn vs. manual, for this list

| Step | modurn today | You do it |
| --- | --- | --- |
| Download all files (resumable) | ✅ `nexus download` | — |
| Extract + `data=`/`content=` lines | ✅ `apply` | — |
| Load order | ✅ via YAML order | keep import order; pin multi-plugin mods |
| Multi-file mods (TR/PT) | ⚠️ needs explicit `files:`/`content:` | fill ids + order |
| Groundcover `groundcover=` | ❌ not yet | add lines manually |
| BSA `fallback-archive=` | ❌ not yet | add lines manually |
| Merge/patch (tes3merge/DeltaPlugin) | ❌ not yet | run momw-tools-pack |
| `settings.cfg` (graphics) | ❌ out of scope for now | MOMW Configurator / manual |

The ❌/⚠️ rows are exactly the roadmap. Nothing here blocks getting the bytes
down today; they're about turning a complete download into a fully configured
playthrough.
