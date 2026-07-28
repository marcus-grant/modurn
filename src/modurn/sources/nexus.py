"""Nexus Mods source via browser automation (Playwright).

Why a browser instead of the Nexus API: API-based downloads are Premium-only.
Free accounts must go through the website's "slow download" button (countdown
+ Cloudflare). Driving a real browser is the only path that works for free
accounts, which is exactly the gap the existing API-based tools don't cover.

Design notes / expected maintenance surface:
  * Auth is handled once, out of band, by `modurn nexus login`, which saves a
    Playwright storage-state file. `fetch` reuses that session headlessly.
  * The DOM selectors below are the part most likely to rot when Nexus
    redesigns. They are deliberately isolated at the top of the file and tried
    in order, so fixing a breakage is a one-line edit here, not surgery.
  * When Premium/API support lands later it is a *sibling* source
    (`NexusApiSource`) added to the registry -- this file does not change.

This module imports Playwright lazily so that `plan`, `local` sources, and the
whole test suite run without Playwright installed or browsers downloaded.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from ..models import Mod
from .base import FetchedFile, ModSource, SourceError

NEXUS_BASE = "https://www.nexusmods.com"

# Candidate selectors for the free-user download button, tried in order.
# Update here if Nexus changes their markup.
_DOWNLOAD_BUTTON_SELECTORS = [
    "button:has-text('Slow download')",
    "a:has-text('Slow download')",
    "#slowDownloadButton",
    "button:has-text('Download')",
]


def _require_playwright():
    try:
        from playwright.sync_api import sync_playwright  # noqa: WPS433
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise SourceError(
            "Playwright is required for the nexus source. Install it with:\n"
            "  pip install playwright && playwright install chromium"
        ) from exc
    return sync_playwright


class NexusSource(ModSource):
    """Downloads Nexus files for a free account using a saved login session."""

    kind = "nexus"

    def __init__(self, auth_state: Path, headless: bool = True, timeout_ms: int = 120_000):
        self.auth_state = Path(auth_state).expanduser()
        self.headless = headless
        self.timeout_ms = timeout_ms
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
        self._context.set_default_timeout(self.timeout_ms)
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
    def login(auth_state: Path, wait_seconds: int = 300) -> None:
        """Open a headed browser, let the user log in, then save the session.

        Interactive by design: rather than fight Cloudflare/CAPTCHA, the human
        logs in normally and we persist the resulting cookies for later
        headless reuse.
        """
        auth_state = Path(auth_state).expanduser()
        auth_state.parent.mkdir(parents=True, exist_ok=True)
        sync_playwright = _require_playwright()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            page.goto(f"{NEXUS_BASE}/users/sign_in", wait_until="domcontentloaded")
            print(
                "\nA browser window is open. Log in to Nexus Mods there.\n"
                "When you can see you are logged in, come back here and press Enter."
            )
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                # Non-interactive fallback: give the user a fixed window.
                time.sleep(wait_seconds)
            context.storage_state(path=str(auth_state))
            browser.close()
        print(f"Saved Nexus session to {auth_state}")

    # -- fetch -------------------------------------------------------------

    def fetch(self, mod: Mod, dest_dir: Path) -> list[FetchedFile]:
        if not mod.files:
            raise SourceError(
                f"mod {mod.name!r}: the nexus source needs explicit file id(s).\n"
                f"  Open {NEXUS_BASE}/{mod.nexus}?tab=files, and read the file_id\n"
                f"  from each file's download link, then add e.g. `files: [7702]`.\n"
                f"  (Auto-resolving the main file is roadmap item M1.5.)"
            )

        dest_dir.mkdir(parents=True, exist_ok=True)
        results: list[FetchedFile] = []
        context = self._ensure_context()
        page = context.new_page()
        try:
            for file_id in mod.files:
                results.append(self._download_one(page, mod, file_id, dest_dir))
        finally:
            page.close()
        return results

    def _download_one(self, page, mod: Mod, file_id: int, dest_dir: Path) -> FetchedFile:
        url = f"{NEXUS_BASE}/{mod.nexus}?tab=files&file_id={file_id}&nmm=1"
        page.goto(url, wait_until="domcontentloaded")

        button = self._find_download_button(page)
        if button is None:
            raise SourceError(
                f"mod {mod.name!r} file {file_id}: could not find a download button on {url}. "
                f"The session may be logged out, or Nexus markup changed "
                f"(update _DOWNLOAD_BUTTON_SELECTORS in sources/nexus.py)."
            )

        with page.expect_download(timeout=self.timeout_ms) as dl_info:
            button.click()
        download = dl_info.value

        suggested = download.suggested_filename or f"{mod.name}-{file_id}.bin"
        target = dest_dir / suggested
        if target.exists():
            return FetchedFile(path=target, from_cache=True, meta={"file_id": file_id, "url": url})
        download.save_as(str(target))
        return FetchedFile(path=target, from_cache=False, meta={"file_id": file_id, "url": url})

    @staticmethod
    def _find_download_button(page) -> Optional[object]:
        for selector in _DOWNLOAD_BUTTON_SELECTORS:
            locator = page.locator(selector).first
            try:
                if locator.count() > 0:
                    locator.wait_for(state="visible", timeout=5_000)
                    return locator
            except Exception:
                continue
        return None
