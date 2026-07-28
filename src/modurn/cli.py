"""modurn command line.

The CLI is the orchestration layer and nothing more: it wires modlist ->
sources -> install -> openmw.cfg -> lockfile/profiles. All the real logic lives
in the modules it calls, so the commands stay short and the pieces stay
independently testable.

Commands:
  modurn plan   <modlist.yaml>   dry run: show what would be fetched/installed
  modurn apply  <modlist.yaml>   fetch, install, write openmw.cfg, write lock
  modurn nexus login             one-time interactive Nexus sign-in
  modurn profile list            show known profiles and their saves
  modurn profile link            associate a profile with a save
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from . import __version__, paths
from .install import InstallError, install_mod
from .lockfile import Lock, LockedMod, lock_path_for, write_lock
from .modlist import ModListError, load_modlist
from .openmw_cfg import CfgEntry, write_profile_block
from .profiles import ProfileRecord, all_profiles, upsert_profile
from .sources import SourceContext, SourceError, get_source

app = typer.Typer(add_completion=False, help="Declarative mod manager for OpenMW.")
nexus_app = typer.Typer(help="Nexus Mods session management.")
profile_app = typer.Typer(help="Profiles and save associations.")
app.add_typer(nexus_app, name="nexus")
app.add_typer(profile_app, name="profile")


def _echo_err(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.RED, err=True)


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
):
    if version:
        typer.echo(f"modurn {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


# -- plan ------------------------------------------------------------------

@app.command()
def plan(modlist: Path = typer.Argument(..., help="Path to a modlist YAML.")):
    """Validate the modlist and show what apply would do. No network, no writes."""
    ml = _load_or_exit(modlist)
    typer.secho(f"Profile: {ml.profile}", bold=True)
    typer.echo(f"openmw.cfg: {ml.game.config}")
    typer.echo(f"mods_dir:   {ml.game.mods_dir}")
    if ml.save:
        typer.echo(f"save:       {ml.save}")
    typer.echo("")
    for mod in ml.mods:
        flag = " " if mod.enabled else "x"
        detail = mod.nexus if mod.source == "nexus" else str(mod.path)
        files = f" files={mod.files}" if mod.files else ""
        typer.echo(f"  [{flag}] {mod.name}  ({mod.source}: {detail}{files})")
    disabled = len(ml.mods) - len(ml.enabled_mods)
    typer.echo("")
    typer.secho(
        f"{len(ml.enabled_mods)} mod(s) to install"
        + (f", {disabled} disabled" if disabled else ""),
        bold=True,
    )


# -- apply -----------------------------------------------------------------

@app.command()
def apply(
    modlist: Path = typer.Argument(..., help="Path to a modlist YAML."),
    no_backup: bool = typer.Option(False, "--no-backup", help="Do not write openmw.cfg.bak."),
    headed: bool = typer.Option(False, "--headed", help="Show the browser during Nexus downloads."),
):
    """Fetch, install, write openmw.cfg's managed block, and write modurn.lock."""
    ml = _load_or_exit(modlist)
    ctx = SourceContext(nexus_auth_state=paths.nexus_auth_state(), headless=not headed)

    # Cache source instances so one browser session serves all Nexus mods.
    source_cache: dict[str, object] = {}

    def source_for(kind: str):
        if kind not in source_cache:
            source_cache[kind] = get_source(kind, ctx)
        return source_cache[kind]

    data_dirs: list[str] = []
    content: list[str] = []
    locked: list[LockedMod] = []

    try:
        for mod in ml.enabled_mods:
            typer.secho(f"-> {mod.name}", bold=True)
            try:
                src = source_for(mod.source)
                fetched = src.fetch(mod, ml.game.mods_dir / "_downloads")
                for f in fetched:
                    tag = "cached" if f.from_cache else "fetched"
                    typer.echo(f"     {tag}: {f.path.name}")

                installed = install_mod(
                    name=mod.name,
                    fetched_paths=[f.path for f in fetched],
                    mods_dir=ml.game.mods_dir,
                    data_subdir=mod.data_subdir,
                    content_override=mod.content or None,
                )
            except (SourceError, InstallError) as exc:
                _echo_err(f"     failed: {exc}")
                raise typer.Exit(code=1)

            data_dirs.append(str(installed.data_dir))
            content.extend(installed.plugins)
            for p in installed.plugins:
                typer.echo(f"     plugin: {p}")

            locked.append(
                LockedMod(
                    name=mod.name,
                    source=mod.source,
                    data_dir=str(installed.data_dir),
                    plugins=installed.plugins,
                    files=installed.source_files,
                    nexus_file_ids=mod.files,
                )
            )
    finally:
        for src in source_cache.values():
            getattr(src, "close", lambda: None)()

    cfg_path = write_profile_block(
        ml.game.config,
        ml.profile,
        CfgEntry(data_dirs=data_dirs, content=content),
        backup=not no_backup,
    )
    typer.secho(f"\nWrote managed block for profile '{ml.profile}' to {cfg_path}", fg=typer.colors.GREEN)

    lock = Lock(
        profile=ml.profile,
        save=str(ml.save) if ml.save else None,
        mods=locked,
    )
    lock_file = write_lock(lock, lock_path_for(modlist))
    typer.echo(f"Wrote {lock_file}")

    upsert_profile(
        ProfileRecord(
            name=ml.profile,
            modlist=str(Path(modlist).expanduser().resolve()),
            lock=str(lock_file.resolve()),
            save=str(ml.save) if ml.save else None,
        )
    )


# -- nexus -----------------------------------------------------------------

@nexus_app.command("login")
def nexus_login():
    """Open a browser to sign in to Nexus once; the session is saved for reuse."""
    from .sources.nexus import NexusSource

    NexusSource.login(paths.nexus_auth_state())


@nexus_app.command("download")
def nexus_download(
    modlist: Path = typer.Argument(..., help="Path to a modlist YAML."),
    headless: bool = typer.Option(
        False, "--headless", help="Run without a visible browser (not recommended for the first runs)."
    ),
):
    """Download every Nexus file in the list into the mods cache. Resumable.

    This only grabs the bytes -- run it while you have bandwidth. Installing
    (extract + write openmw.cfg) happens later, offline, via `modurn apply`.
    """
    from .sources.nexus import NexusSource
    from .sources.nexus_parse import DownloadLedger

    ml = _load_or_exit(modlist)
    nexus_mods = [m for m in ml.enabled_mods if m.source == "nexus"]
    if not nexus_mods:
        typer.echo("No nexus mods in this list.")
        return

    dest = ml.game.mods_dir / "_downloads"
    dest.mkdir(parents=True, exist_ok=True)
    ledger = DownloadLedger.load(dest / ".modurn-downloads.json")
    src = NexusSource(paths.nexus_auth_state(), headless=headless)

    ok, failed = 0, []
    try:
        for i, mod in enumerate(nexus_mods, 1):
            typer.secho(f"[{i}/{len(nexus_mods)}] {mod.name}", bold=True)
            try:
                for f in src.download_files(mod, dest, ledger):
                    tag = "have" if f.from_cache else "got "
                    typer.echo(f"     {tag} {f.path.name}")
                ok += 1
            except Exception as exc:  # keep going; travel bandwidth is flaky
                _echo_err(f"     failed: {exc}")
                failed.append(mod.name)
    finally:
        src.close()

    typer.secho(f"\nDownloaded {ok}/{len(nexus_mods)} mods into {dest}", fg=typer.colors.GREEN)
    if failed:
        _echo_err("Failed (re-run to resume): " + ", ".join(failed))
        raise typer.Exit(code=1)


@nexus_app.command("import-list")
def nexus_import_list(
    url: str = typer.Argument(..., help="A modding-openmw.com list URL."),
    out: Path = typer.Option(..., "-o", "--out", help="Where to write the generated modlist YAML."),
    config: Path = typer.Option(Path("~/.config/openmw/openmw.cfg"), help="openmw.cfg path for the generated list."),
    mods_dir: Path = typer.Option(Path("~/games/openmw/mods"), help="mods_dir for the generated list."),
    profile: str = typer.Option("imported", help="Profile name for the generated list."),
):
    """Read a MOMW list in your logged-in browser and scaffold a modurn YAML.

    Uses your authenticated session because the site is Cloudflare-blocked to
    server-side fetches. File ids are left blank -- `nexus download` resolves the
    main file automatically, and you tweak any that guessed wrong.
    """
    import yaml

    from .sources.nexus import NexusSource

    src = NexusSource(paths.nexus_auth_state(), headless=False)
    try:
        refs = src.import_list(url)
    finally:
        src.close()

    doc = {
        "game": {"config": str(config), "mods_dir": str(mods_dir)},
        "profile": profile,
        "mods": [
            {"name": f"{r.game}/{r.mod_id}", "nexus": r.slug, "files": []} for r in refs
        ],
    }
    out = Path(out).expanduser()
    out.write_text(
        "# Generated by `modurn nexus import-list`.\n"
        "# Review names, fill/verify `files:` (blank = auto-resolve main file),\n"
        f"# then: modurn nexus download {out.name}\n"
        + yaml.safe_dump(doc, sort_keys=False)
    )
    typer.secho(f"Wrote {len(refs)} mods to {out}", fg=typer.colors.GREEN)


# -- profile ---------------------------------------------------------------

@profile_app.command("list")
def profile_list():
    """List known profiles and their associated saves."""
    records = all_profiles()
    if not records:
        typer.echo("No profiles yet. Run `modurn apply` on a modlist to create one.")
        return
    for name, rec in sorted(records.items()):
        typer.secho(name, bold=True)
        typer.echo(f"  save:    {rec.save or '(none)'}")
        typer.echo(f"  modlist: {rec.modlist or '(unknown)'}")


@profile_app.command("link")
def profile_link(
    name: str = typer.Argument(..., help="Profile name."),
    save: Path = typer.Argument(..., help="Path to the .omwsave to associate."),
):
    """Associate a profile with a save file."""
    upsert_profile(ProfileRecord(name=name, save=str(Path(save).expanduser())))
    typer.secho(f"Linked profile '{name}' -> {save}", fg=typer.colors.GREEN)


# -- helpers ---------------------------------------------------------------

def _load_or_exit(modlist: Path):
    try:
        return load_modlist(modlist)
    except ModListError as exc:
        _echo_err(str(exc))
        raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
