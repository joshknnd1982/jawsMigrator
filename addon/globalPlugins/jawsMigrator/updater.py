# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.
# The update check follows ClassicSpeech's (https://github.com/joshknnd1982/classicspeech-nvda),
# also GPL 2, so both add-ons behave the same way.

"""Check GitHub for a newer JAWS Migration Assistant, download it and install it with NVDA.

Releases are published on the GitHub repository named by the ``url`` in the
add-on's manifest (https://github.com/joshknnd1982/jawsMigrator). A check asks
GitHub for the latest release and compares its tag, such as ``v1.1``, with the
installed version.

When the release is newer, the assistant shows what is new in a dialog whose
notes can be read line by line, and offers to download the ``.nvda-addon``
file. The download must match the release's ``.sha256`` file. NVDA's own add-on
installation then asks the user to confirm, installs the new version in place
of this one, keeping the assistant's settings, and offers to restart NVDA.

Checks run in the background. An automatic check runs at most once a day, a
little after NVDA starts, and only speaks up when there is an update.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass

API_URL = "https://api.github.com/repos/{repository}/releases/latest"
RELEASES_URL = "https://github.com/{repository}/releases"
DEFAULT_REPOSITORY = "joshknnd1982/jawsMigrator"
CHECK_TIMEOUT_SECONDS = 20
DOWNLOAD_TIMEOUT_SECONDS = (20, 120)
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
AUTOMATIC_CHECK_DELAY_MS = 45 * 1000
AUTOMATIC_CHECK_INTERVAL_SECONDS = 24 * 60 * 60
ADDON_EXTENSION = ".nvda-addon"
CHECKSUM_EXTENSION = ".sha256"
PRODUCT = "JAWS Migration Assistant"

_GITHUB_REPOSITORY = re.compile(r"^https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", re.IGNORECASE)
_CHECKSUM = re.compile(r"^[0-9a-fA-F]{64}$")


class UpdateError(Exception):
	"""A check or download failed; the message can be shown to the user."""


@dataclass(frozen=True)
class Release:
	version: str
	name: str
	notes: str
	pageUrl: str
	addonName: str = ""
	addonUrl: str = ""
	addonSize: int = 0
	checksumUrl: str = ""


# -- pure helpers ---------------------------------------------------------------------------


def githubRepository(url):
	"""Return ``owner/name`` for a GitHub repository URL, otherwise None."""
	match = _GITHUB_REPOSITORY.match(str(url or "").strip())
	if not match:
		return None
	return f"{match.group(1)}/{match.group(2)}"


def parseVersion(text):
	"""Return a version such as ``1.0`` or ``v1.0.2`` as a tuple of numbers, or None."""
	text = str(text or "").strip()
	if text[:1] in ("v", "V"):
		text = text[1:]
	parts = text.split(".")
	if not text or not all(part.isdigit() for part in parts):
		return None
	return tuple(int(part) for part in parts)


def isNewer(candidate, installed):
	new, old = parseVersion(candidate), parseVersion(installed)
	if new is None or old is None:
		return False
	width = max(len(new), len(old))
	return new + (0,) * (width - len(new)) > old + (0,) * (width - len(old))


def releaseFromGithub(data, product=PRODUCT):
	"""The Release described by GitHub's JSON for a release, or None."""
	if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
		return None
	tag = str(data.get("tag_name") or "")
	version = tag[1:] if tag[:1] in ("v", "V") else tag
	if parseVersion(version) is None:
		return None
	addon = checksum = None
	assets = [asset for asset in data.get("assets") or () if isinstance(asset, dict)]
	for asset in assets:
		if str(asset.get("name") or "").lower().endswith(ADDON_EXTENSION):
			addon = asset
			break
	if addon is not None:
		wanted = str(addon.get("name")) + CHECKSUM_EXTENSION
		checksum = next((asset for asset in assets if asset.get("name") == wanted), None)
	return Release(
		version=version,
		name=str(data.get("name") or f"{product} {version}"),
		notes=str(data.get("body") or ""),
		pageUrl=str(data.get("html_url") or ""),
		addonName=str(addon.get("name") or "") if addon else "",
		addonUrl=str(addon.get("browser_download_url") or "") if addon else "",
		addonSize=int(addon.get("size") or 0) if addon else 0,
		checksumUrl=str(checksum.get("browser_download_url") or "") if checksum else "",
	)


def checksumFromFile(text):
	"""The SHA-256 in a ``.sha256`` file (``<hex>  <file name>``), or None."""
	words = str(text or "").split()
	if words and _CHECKSUM.match(words[0]):
		return words[0].lower()
	return None


def notesAsText(notes, limit=None):
	"""Release notes as plain text: Markdown headings, bullets, emphasis and link targets removed."""
	text = str(notes or "").replace("\r\n", "\n")
	text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
	text = re.sub(r"(?m)^[ \t]{0,3}#{1,6}[ \t]*", "", text)
	text = re.sub(r"(?m)^[ \t]*[-*+][ \t]+", "- ", text)
	text = text.replace("**", "").replace("__", "").replace("`", "")
	text = re.sub(r"\n{3,}", "\n\n", text).strip()
	if limit is not None and len(text) > limit:
		text = text[:limit].rsplit(" ", 1)[0].rstrip() + "..."
	return text


def isDue(lastCheck, now=None, interval=AUTOMATIC_CHECK_INTERVAL_SECONDS):
	now = time.time() if now is None else now
	try:
		lastCheck = float(lastCheck)
	except (TypeError, ValueError):
		return True
	return lastCheck <= 0 or now - lastCheck >= interval or lastCheck > now


# -- the running add-on ------------------------------------------------------------------------


def installedAddon():
	"""``(version, repository)`` of this add-on, or None when it is not running as an add-on."""
	try:
		import addonHandler

		manifest = addonHandler.getCodeAddon().manifest
		version = str(manifest["version"])
		repository = githubRepository(manifest.get("url")) or DEFAULT_REPOSITORY
	except Exception:
		return None
	if parseVersion(version) is None:
		return None
	return version, repository


def _requests():
	try:
		import requests
	except Exception as error:
		raise UpdateError("NVDA's internet support is not available.") from error
	return requests


def _headers(version, repository):
	return {
		"Accept": "application/vnd.github+json",
		"User-Agent": f"jawsMigrator/{version} (NVDA add-on; +https://github.com/{repository})",
	}


def fetchLatestRelease(version, repository, session=None, product=PRODUCT):
	"""The latest release of ``repository`` on GitHub. ``version`` is this add-on's, for the user agent."""
	getter = session or _requests()
	try:
		response = getter.get(API_URL.format(repository=repository), headers=_headers(version, repository), timeout=CHECK_TIMEOUT_SECONDS)
	except Exception as error:
		raise UpdateError("GitHub could not be reached. Check your internet connection.") from error
	if response.status_code == 404:
		raise UpdateError(f"There are no {product} releases on GitHub yet.")
	if response.status_code != 200:
		raise UpdateError(f"GitHub answered with error {response.status_code}.")
	try:
		release = releaseFromGithub(response.json(), product)
	except Exception as error:
		raise UpdateError("GitHub's answer could not be read.") from error
	if release is None:
		raise UpdateError("The latest release on GitHub has no version number the assistant understands.")
	return release


def downloadRelease(release, version, repository, folder, session=None):
	"""Download the release's add-on file into ``folder`` and check it. Returns its path."""
	if not release.addonUrl:
		raise UpdateError("The release has no add-on file.")
	if not release.checksumUrl:
		raise UpdateError("The release has no checksum file, so its add-on file can't be checked.")
	if release.addonSize > MAX_DOWNLOAD_BYTES:
		raise UpdateError("The add-on file is larger than expected.")
	getter = session or _requests()
	headers = _headers(version, repository)
	name = os.path.basename(release.addonName) or "jawsMigrator" + ADDON_EXTENSION
	if not name.lower().endswith(ADDON_EXTENSION):
		name += ADDON_EXTENSION
	path = os.path.join(folder, name)
	try:
		response = getter.get(release.checksumUrl, headers=headers, timeout=CHECK_TIMEOUT_SECONDS)
		expected = checksumFromFile(response.text) if response.status_code == 200 else None
	except Exception as error:
		raise UpdateError("The checksum file could not be downloaded.") from error
	if expected is None:
		raise UpdateError("The checksum file could not be read.")
	digest = hashlib.sha256()
	size = 0
	try:
		with getter.get(release.addonUrl, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
			if response.status_code != 200:
				raise UpdateError(f"GitHub answered with error {response.status_code}.")
			with open(path, "wb") as stream:
				for chunk in response.iter_content(chunk_size=128 * 1024):
					if not chunk:
						continue
					size += len(chunk)
					if size > MAX_DOWNLOAD_BYTES:
						raise UpdateError("The add-on file is larger than expected.")
					digest.update(chunk)
					stream.write(chunk)
	except UpdateError:
		with contextlib.suppress(OSError):
			os.remove(path)
		raise
	except Exception as error:
		with contextlib.suppress(OSError):
			os.remove(path)
		raise UpdateError("The add-on file could not be downloaded.") from error
	if digest.hexdigest() != expected:
		with contextlib.suppress(OSError):
			os.remove(path)
		raise UpdateError("The downloaded file does not match its checksum, so it was deleted.")
	return path


# -- checking from NVDA --------------------------------------------------------------------------


class UpdateChecker:
	"""Runs checks and downloads in the background and talks to the user in NVDA."""

	def __init__(self):
		self._busy = False
		self._stopped = False
		self._timer = None

	def stop(self):
		self._stopped = True
		timer, self._timer = self._timer, None
		if timer is not None:
			with contextlib.suppress(Exception):
				timer.Stop()

	def scheduleAutomaticCheck(self):
		from . import nvdaEnv, state

		if installedAddon() is None or nvdaEnv.isSecureMode() or not state.get("checkForUpdatesAutomatically"):
			return
		if not isDue(state.get("lastUpdateCheck")):
			return
		import wx

		self._timer = wx.CallLater(AUTOMATIC_CHECK_DELAY_MS, self.check, manual=False)

	def check(self, manual=True):
		from . import state

		self._timer = None
		if self._stopped:
			return
		if self._busy:
			if manual:
				import ui

				ui.message(f"A {PRODUCT} update check is already running.")
			return
		addon = installedAddon()
		if addon is None:
			if manual:
				import wx

				wx.CallAfter(self._message, "This copy of the JAWS Migration Assistant doesn't know where its updates are published.", "error")
			return
		if not manual and not state.get("checkForUpdatesAutomatically"):
			return
		version, repository = addon
		self._busy = True
		if manual:
			import ui

			ui.message(f"Checking for {PRODUCT} updates")
		self._run(lambda: fetchLatestRelease(version, repository), lambda outcome: self._checked(outcome, version, repository, manual))

	def _run(self, work, done):
		import wx

		def target():
			try:
				outcome = work()
			except UpdateError as error:
				outcome = error
			except Exception as error:
				_log().debug("jawsMigrator update check failed", exc_info=True)
				outcome = UpdateError(str(error) or error.__class__.__name__)
			wx.CallAfter(done, outcome)

		threading.Thread(target=target, name="jawsMigratorUpdates", daemon=True).start()

	def _checked(self, outcome, version, repository, manual):
		from . import state

		self._busy = False
		if self._stopped:
			return
		if isinstance(outcome, UpdateError):
			_log().info("jawsMigrator: update check failed: %s", outcome)
			if manual:
				self._message(f"The JAWS Migration Assistant could not check for updates. {outcome}", "error")
			return
		state.set("lastUpdateCheck", int(time.time()))
		release = outcome
		if not isNewer(release.version, version):
			if manual:
				self._message(f"The JAWS Migration Assistant is up to date. You have version {version}, the latest release.")
			return
		self._offer(release, version, repository)

	def _offer(self, release, version, repository):
		import wx

		from .gui.updateDialog import showUpdateOffer

		summary = f"{PRODUCT} {release.version} is available. You have version {version}."
		notes = notesAsText(release.notes) or "This release has no notes."
		# While the offer is open, another check must not open a second one.
		self._busy = True
		try:
			if not release.addonUrl:
				showUpdateOffer(
					f"{PRODUCT} update",
					summary,
					notes,
					question=f"This release has no add-on file to install. Download it from {release.pageUrl or RELEASES_URL.format(repository=repository)}",
					closeLabel="&Close",
				)
				return
			answer = showUpdateOffer(
				f"{PRODUCT} update",
				summary,
				notes,
				question="Download and install it now? NVDA asks you to confirm the installation, then offers to restart. Your settings, backups and migration reports are kept.",
				installLabel="&Download and install",
				closeLabel="&Not now",
			)
		finally:
			self._busy = False
		if answer == wx.ID_YES:
			self._download(release, version, repository)

	def _download(self, release, version, repository):
		import ui

		folder = tempfile.mkdtemp(prefix="jawsMigrator-update-")
		self._busy = True
		ui.message(f"Downloading {PRODUCT} {release.version}")
		self._run(lambda: downloadRelease(release, version, repository, folder), lambda outcome: self._downloaded(outcome, folder))

	def _downloaded(self, outcome, folder):
		self._busy = False
		try:
			if self._stopped:
				return
			if isinstance(outcome, UpdateError):
				self._message(f"The JAWS Migration Assistant could not download the update. {outcome}", "error")
				return
			try:
				from gui import addonGui

				addonGui.handleRemoteAddonInstall(outcome)
			except Exception:
				_log().error("jawsMigrator: NVDA could not install the update", exc_info=True)
				self._message("NVDA could not install the update. Details are in the NVDA log.", "error")
		finally:
			shutil.rmtree(folder, ignore_errors=True)

	def _message(self, message, kind="information"):
		import gui
		import wx

		icon = wx.ICON_ERROR if kind == "error" else wx.ICON_INFORMATION
		gui.mainFrame.prePopup()
		try:
			wx.MessageBox(message, f"{PRODUCT} update", wx.OK | icon, gui.mainFrame)
		finally:
			gui.mainFrame.postPopup()


def _log():
	from logHandler import log

	return log
