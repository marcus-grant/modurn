# Usage

How to install modurn, write a modlist, and run the commands.

## Install

```bash
pip install -e .            # core
pip install -e '.[rar]'     # add .rar extraction support (needs system `unrar`)
playwright install chromium # only needed for the nexus source
```

For development:

```bash
pip install -e '.[dev]'
pytest
```

## The modlist YAML

A modlist is a single YAML document. This is the whole schema:

```yaml
game:
  config: ~/.config/openmw/openmw.cfg   # the openmw.cfg modurn manages
  mods_dir: ~/games/openmw/mods         # dir modurn owns; one subfolder per mod

profile: my-playthrough                 # names the managed cfg block + profile
save: ~/.local/share/openmw/saves/run1.omwsave   # optional association

mods:
  - name: Patch for Purists             # required; also the install folder name
    nexus: morrowind/45096              # <game>/<modid> on nexusmods.com
    files: [1000000000]                 # explicit Nexus file id(s)
    enabled: true                       # default true

  - name: A mod I already downloaded
    source: local                       # default source is "nexus"
    path: ~/downloads/some-mod.7z        # an archive OR an extracted directory
    data_subdir: "00 Core"              # optional: data files live in a subfolder
    content: [Some.esp, SomeOther.esp]  # optional: explicit plugin order override
```

Field notes:

- **`source`** selects the backend. `nexus` (default) or `local`. New backends
  are added in `src/modurn/sources/` — see [architecture.md](architecture.md).
- **`nexus`** must look like `game/modid` (e.g. `morrowind/19510`).
- **`files`** — omit to let the nexus source auto-resolve the mod's *main* file.
  Multi-file mods (e.g. Tamriel Rebuilt) should list ids explicitly.
- **`content`** — if omitted, modurn auto-detects `.esp/.esm/.omwaddon/.omwgame`
  files in the mod's data dir and adds them in discovered order.
- **`data_subdir`** — set when an archive wraps its data files in a named folder
  that auto-unwrap doesn't pick.

Validation is strict and errors point at the offending field, e.g. a `nexus`
mod missing its `nexus:` slug fails at load time, before any download.

## Commands

| Command | What it does | Network |
| --- | --- | --- |
| `modurn plan <yaml>` | Validate the list and print the install plan. | none |
| `modurn apply <yaml>` | Fetch → install → write the cfg block → write `modurn.lock` + profile record. | as needed |
| `modurn nexus login` | One-time interactive Nexus sign-in; session saved for reuse. | yes |
| `modurn nexus download <yaml>` | Download every Nexus file into the mods cache. **Resumable.** No install. | yes |
| `modurn nexus import-list <url> -o <yaml>` | Read a modding-openmw.com list in your logged-in browser and scaffold a modlist. | yes |
| `modurn profile list` | Show known profiles and their associated saves. | none |
| `modurn profile link <name> <save>` | Associate a profile with a `.omwsave`. | none |

### Typical flows

**All local (fully testable, no network):**

```bash
modurn plan  my.yaml
modurn apply my.yaml
```

**Nexus, bandwidth-first (recommended when connectivity is flaky):**

```bash
modurn nexus login
modurn nexus import-list <list-url> -o list.yaml
modurn nexus download list.yaml     # grab all bytes now; re-run to resume
modurn apply list.yaml              # later, offline: extract + write cfg
```

See [nexus-guided-run.md](nexus-guided-run.md) for the guided-run details and
the network allowlist.

## How modurn writes openmw.cfg

modurn owns only a marked block, keyed by profile name, and never touches the
rest of the file:

```
## >>> modurn:my-playthrough (managed - do not edit inside) >>>
data="/home/you/games/openmw/mods/Patch for Purists"
content=Patch for Purists.esp
## <<< modurn:my-playthrough <<<
```

- A `.bak` of the original is written before the first change.
- Re-applying replaces just this block → **idempotent**.
- Different profiles produce different blocks and **coexist** in one cfg.
- Removing the block (a future `remove` command / manual delete) fully reverts.

The set of installed mods, data dirs, plugins, and Nexus file ids is also
written to `modurn.lock` next to the modlist, so a run is reproducible and
inspectable in git.
