# Architecture

modurn is intentionally small. The goal for the MVP is not a finished design but
a shape where better abstractions can be *hoisted in incrementally* later
without a rewrite. To that end it takes exactly **one** seam seriously and keeps
everything else flat and obvious.

## The one seam: `ModSource`

Everything about *how a mod's bytes are obtained* lives behind a single
protocol, `modurn.sources.base.ModSource`:

```python
class ModSource(Protocol):
    kind: str
    def fetch(self, mod: Mod, dest_dir: Path) -> list[FetchedFile]: ...
    def close(self) -> None: ...
```

Everything downstream — extraction, cfg writing, the lockfile, profiles — is
written against `FetchedFile`, never against a specific backend. Adding a
backend is meant to be: **write one module in `sources/`, add one line to the
registry**, and nothing else in the codebase changes.

Current implementations:

- `sources/local.py` — `LocalSource`: uses an archive/dir you already have.
- `sources/nexus.py` — `NexusSource`: guided, resumable browser downloads.

Planned (proves the seam holds): a Nexus **API** source for Premium accounts, a
homelab backend, and a modding-openmw.com list importer.

The registry (`sources/__init__.py`) builds sources lazily, so importing it
never imports Playwright — that keeps `plan`, the local source, and the test
suite free of the heavy browser dependency.

## Module map

```
src/modurn/
  models.py          # pydantic schema for the YAML — THE user contract
  modlist.py         # load + validate a modlist file
  sources/
    base.py          # ModSource protocol, FetchedFile, SourceError
    __init__.py      # the source registry (kind -> builder)
    local.py         # LocalSource
    nexus.py         # NexusSource (Playwright) — browser flow only
    nexus_parse.py   # PURE helpers: file-id parse, list parse, resume ledger
  install.py         # extract archives, unwrap wrappers, detect data dir + plugins
  openmw_cfg.py      # reversible per-profile managed block, backup on first write
  lockfile.py        # modurn.lock — record of what apply did
  profiles.py        # profile <-> save registry
  paths.py           # default state locations (XDG-aware)
  cli.py             # orchestration ONLY; all logic lives in the modules above
```

## Data flow

```
modlist.yaml
   │  modlist.load_modlist()  ->  ModList (validated)
   ▼
for each enabled mod:
   ModSource.fetch()  ->  FetchedFile[]        (sources/)
   install_mod()      ->  InstalledMod         (install.py: extract, detect)
   ▼
write_profile_block()  ->  openmw.cfg managed block   (openmw_cfg.py)
write_lock()           ->  modurn.lock                (lockfile.py)
upsert_profile()       ->  profile <-> save record    (profiles.py)
```

`cli.py` is the only place that wires these together. Each module is usable and
testable on its own.

## Design principles

1. **One real abstraction, everything else concrete.** Only `ModSource` is a
   protocol. No premature interfaces around extraction, cfg, or profiles — those
   are plain functions/dataclasses that can be lifted into abstractions *if and
   when* a second need appears.
2. **Keep the testable core network-free.** The browser flow can't be
   unit-tested without Nexus, so the decisions it depends on — which files to
   fetch, whether to skip an already-downloaded one, how to parse a list — are
   pulled into `nexus_parse.py` as pure functions with tests. The install and
   cfg layers are likewise fully testable offline.
3. **Isolate the churn.** The Nexus DOM is the part most likely to break. All of
   its selectors and timings sit as named constants at the top of `nexus.py` so
   a site change is a one-line edit, not surgery.
4. **Reversible, idempotent side effects.** modurn writes a marked cfg block and
   a `.bak`, and records a lockfile — so applying twice is safe and undoing is
   trivial. This is what makes iterating on a live config low-risk.
5. **Decouple bytes from install.** `nexus download` captures bytes (online,
   resumable); `apply` installs (offline). Bandwidth and correctness are
   separate concerns with separate failure modes.

## Where new work slots in

- New backend → `sources/<name>.py` + one registry line.
- Groundcover/BSA/`settings.cfg` support → extend `install.py` (detection) and
  `openmw_cfg.py` (new line kinds); the managed-block mechanism already
  generalizes.
- Profile switching / `remove` → new `cli.py` commands over existing
  `lockfile.py` + `openmw_cfg.remove_profile_block()`.
- Merge/patch step (tes3merge/DeltaPlugin) → a post-install stage the CLI runs
  after `apply`; see the starter-pack reference for why some lists need it.
