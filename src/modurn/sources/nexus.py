"""Nexus Mods source via browser automation (Playwright).

Why a browser instead of the Nexus API: API downloads are Premium-only. Free
accounts must click the site's "slow download" button (countdown + Cloudflare),
so modurn drives a real browser and reuses a login session established once via
`modurn nexus login`.

SETTLED best-guess flow (tweak the constants at the top when Nexus markup
drifts -- that is the entire maintenance surface):

  * Manual download page for one file (NOT the mod-manager/nmm handoff):
        https://www.nexusmods.com/<game>/mods/<id>?tab=files&file_id=<fid>
  * Free users: a countdown, then an anchor `#slowDownloadButton` becomes
    clickable; clicking it starts the actual file download from a CDN node.
  * Premium users: an immediate "Download" button.

The design deliberately assumes a human is present for the first runs (headed
browser): if auto-clicking the button doesn't produce a download in time, we
pause and let the user click / solve any Cloudflare challenge, then capture the
download. Everything is resumable via a ledger so flaky bandwidth is survivable.

Playwright is imported lazily so `plan`, the local source, and the whole test
suite run without it installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from ..models import Mod
from .base import FetchedFile, ModSource, SourceError
from .nexus_parse import (
    DownloadLedger,
    NexusModRef,
    extract_nexus_mods_from_html,
    parse_file_id,
)

NEXUS_BASE = "https://www.nexusmods.com"

# --- the maintenance surface: selectors + timings -------------------------
# Free-user download button, tried in order. The first is the long-standing id.
DOWNLOAD_BUTTON_SELECTORS = [
    "#slowDownloadButton",
    "a:has-text('Slow download')",
    "button:has-text('Slow download')",
    "a:has-text('Download')",          # premium immediate download
    "button:has-text('Download')",
]
# On the Files tab, links/buttons that carry a file_id for the "main" files.
MAIN_FILE_LINK_SELECTOR = "a[href*='file_id=']"
COUNTDOWN_WAIT_MS = 12_000    # how long to wait for the slow button to arm
DOWNLOAD_WAIT_MS = 300_000    # how long a single file download may take


def _require_playwright():
    try:
        from playwright.sync_api import sync_playwright  # noqa: WPS433
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise SourceError(
            "Playwright is required for the nexus source. Install it with:\n"
            "  pip install playwright && playwright install chromium"
        ) from exc
    return sync_playwright


def manual_download_url(game: str, mod_id: int, file_id: int) -> str:
    """The free-user manual download page for a specific file."""
    return f"{NEXUS_BASE}/{game}/mods/{mod_id}?tab=files&file_id={file_id}"


def files_tab_url(game: str, mod_id: int) -> str:
    return f"{NEXUS_BASE}/{game}/mods/{mod_id}?tab=files"


class NexusSource(ModSource):
    """Downloads Nexus files for a (free) account using a saved login session."""

    kind = "nexus"

    def __init__(
        self,
        auth_state: Path,
        headless: bool = True,
        # Called when auto-click fails and we need the human to act. Returns
        # after the user has done their part. Defaults to a terminal prompt.
        assist: Optional[Callable[[str], None]] = None,
    ):
        self.auth_state = Path(auth_state).expanduser()
        self.headless = headless
        self.assist = assist or _default_assist
        self._pw = None
        self._browser = None
        self._context = None

    # -- session lifecycle -------------------------------------------------

    def _ensure_context(self):
        if self._context is not None:
            return self._context
        if not self.auth_state.is_file():
            raise SourceError(
                f"no saved Nexus session at {self.auth_state}. Run `modurn nexus login` first."
            )
        sync_playwright = _require_playwright()
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            storage_state=str(self.auth_state),
            accept_downloads=True,
        )
        self._context.set_default_timeout(COUNTDOWN_WAIT_MS)
        return self._context

    def close(self) -> None:
        for closer in (self._context, self._browser):
            try:
                if closer is not None:
                    closer.close()
            except Exception:  # pragma: no cover - best effort teardown
                pass
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:  # pragma: no cover
                pass
        self._pw = self._browser = self._context = None

    # -- login (interactive, run once) ------------------------------------

    @staticmethod
    def login(auth_state: Path) -> None:
        auth_state = Path(auth_state).expanduser()
        auth_state.parent.mkdir(parents=True, exist_ok=True)
        sync_playwright = _require_playwright()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            page.goto(f"{NEXUS_BASE}/users/sign_in", wait_until="domcontentloaded")
            print(
                "\nA browser window is open. Log in to Nexus Mods there\n"
                "(solve any Cloudflare challenge). When you can see you are\n"
                "logged in, come back here and press Enter."
            )
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                pass
            context.storage_state(path=str(auth_state))
            browser.close()
        print(f"Saved Nexus session to {auth_state}")

    # -- import a modding-openmw.com list ---------------------------------

    def import_list(self, list_url: str) -> list[NexusModRef]:
        """Read a MOMW list page in the authenticated browser and return the
        Nexus mods it references, in order. (Our server-side fetches are
        Cloudflare-blocked; the user's real session is not.)"""
        context = self._ensure_context()
        page = context.new_page()
        try:
            page.goto(list_url, wait_until="domcontentloaded")
            # give lazy content a moment; best-effort
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass
            html = page.content()
        finally:
            page.close()
        return extract_nexus_mods_from_html(html)

    # -- resolve the main file id when the user didn't specify one --------

    def resolve_file_ids(self, mod: Mod) -> list[int]:
        if mod.files:
            return mod.files
        context = self._ensure_context()
        page = context.new_page()
        try:
            page.goto(files_tab_url(mod.nexus_game, mod.nexus_mod_id), wait_until="domcontentloaded")
            hrefs = page.locator(MAIN_FILE_LINK_SELECTOR).evaluate_all(
                "els => els.map(e => e.getAttribute('href'))"
            )
        finally:
            page.close()
        ids: list[int] = []
        for href in hrefs:
            fid = parse_file_id(href)
            if fid and fid not in ids:
                ids.append(fid)
        if not ids:
            raise SourceError(
                f"mod {mod.name!r}: could not find any file_id on {files_tab_url(mod.nexus_game, mod.nexus_mod_id)}. "
                f"Specify `files: [...]` explicitly."
            )
        # Best guess: the first main file. The user tweaks the YAML if wrong.
        return ids[:1]

    # -- download (guided, resumable) -------------------------------------

    def download_files(self, mod: Mod, dest_dir: Path, ledger: DownloadLedger) -> list[FetchedFile]:
        """Download all of a mod's files into dest_dir, skipping finished ones."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        file_ids = self.resolve_file_ids(mod)
        context = self._ensure_context()
        page = context.new_page()
        results: list[FetchedFile] = []
        try:
            for file_id in file_ids:
                if ledger.has(mod.nexus, file_id):
                    name = ledger.filename_for(mod.nexus, file_id)
                    results.append(
                        FetchedFile(path=dest_dir / name, from_cache=True, meta={"file_id": file_id})
                    )
                    continue
                results.append(self._download_one(page, mod, file_id, dest_dir, ledger))
        finally:
            page.close()
        return results

    # fetch() satisfies the ModSource protocol (used by `apply`). It downloads
    # then hands paths to the installer. `download_files` is the same machinery
    # without the install step, for the "grab bytes now" command.
    def fetch(self, mod: Mod, dest_dir: Path) -> list[FetchedFile]:
        ledger = DownloadLedger.load(dest_dir / ".modurn-downloads.json")
        return self.download_files(mod, dest_dir, ledger)

    def _download_one(self, page, mod: Mod, file_id: int, dest_dir: Path, ledger: DownloadLedger) -> FetchedFile:
        url = manual_download_url(mod.nexus_game, mod.nexus_mod_id, file_id)
        page.goto(url, wait_until="domcontentloaded")

        download = self._trigger_and_capture(page, mod, file_id, url)
        suggested = download.suggested_filename or f"{mod.nexus_game}-{mod.nexus_mod_id}-{file_id}.bin"
        target = dest_dir / suggested
        download.save_as(str(target))
        ledger.record(mod.nexus, file_id, suggested)
        return FetchedFile(path=target, from_cache=False, meta={"file_id": file_id, "url": url})

    def _trigger_and_capture(self, page, mod: Mod, file_id: int, url: str):
        """Try to auto-click the download button; fall back to human assist."""
        # First attempt: auto-click.
        try:
            with page.expect_download(timeout=DOWNLOAD_WAIT_MS) as dl_info:
                if not self._click_download_button(page):
                    raise _NoButton()
            return dl_info.value
        except _NoButton:
            pass
        except Exception:
            # Auto path timed out or failed; fall through to human assist.
            pass

        # Second attempt: ask the human (headed) to click / solve Cloudflare.
        self.assist(
            f"{mod.name} (file {file_id}): please click the download button in the "
            f"browser (and solve any Cloudflare check). URL: {url}"
        )
        with page.expect_download(timeout=DOWNLOAD_WAIT_MS) as dl_info:
            # They may have already clicked; also try once more programmatically.
            try:
                self._click_download_button(page)
            except Exception:
                pass
        return dl_info.value

    @staticmethod
    def _click_download_button(page) -> bool:
        for selector in DOWNLOAD_BUTTON_SELECTORS:
            locator = page.locator(selector).first
            try:
                if locator.count() > 0:
                    locator.wait_for(state="visible", timeout=COUNTDOWN_WAIT_MS)
                    locator.click()
                    return True
            except Exception:
                continue
        return False


class _NoButton(Exception):
    pass


def _default_assist(message: str) -> None:  # pragma: no cover - interactive
    print(f"\n[assist] {message}\nPress Enter once done...")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass
