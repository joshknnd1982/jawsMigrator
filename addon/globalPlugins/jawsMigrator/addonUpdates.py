# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Install the add-ons the assistant relies on, always at their newest versions.

ClassicSpeech is not in NVDA's Add-on Store: its newest release comes from its
GitHub releases (https://github.com/joshknnd1982/classicspeech-nvda) and must
match the release's ``.sha256`` file. The recommended add-ons come from the
Add-on Store, at the newest stable version for this NVDA, checked against the
SHA-256 the store publishes (see storeAddons).

Nothing is ever installed from a copy kept on disk: each time, GitHub or the
Add-on Store is asked for the newest version. An add-on that is already
installed is only replaced by a newer version; one that is already the newest
is left alone, and so is one whose version can't be compared. NVDA's own
installer puts a new version in place of the old one when NVDA restarts,
keeping the add-on's settings. The download is also checked to really be the
add-on it claims to be before NVDA installs it.
"""

from __future__ import annotations

import contextlib
import os
import re
from dataclasses import dataclass, field

from . import debugLog, managers, nvdaEnv, storeAddons, updater

CLASSIC_SPEECH_ID = nvdaEnv.CLASSIC_SPEECH_ID
CLASSIC_SPEECH_NAME = "ClassicSpeech"
CLASSIC_SPEECH_REPOSITORY = "joshknnd1982/classicspeech-nvda"
CLASSIC_SPEECH_PAGE = f"https://github.com/{CLASSIC_SPEECH_REPOSITORY}"
GITHUB = "GitHub"
ADDON_STORE = "the NVDA Add-on Store"

#: ClassicSpeech, which the assistant needs for schemes, voice aliases and sounds. Not in the Add-on Store.
CLASSIC_SPEECH_ADDON = managers.StoreAddon(
	CLASSIC_SPEECH_ID,
	CLASSIC_SPEECH_NAME,
	"Speech and sound schemes, voices for your JAWS voice aliases, JAWS sounds and verbosity, like JAWS's Speech and "
	"Sounds Manager. The assistant uses it for your JAWS schemes, voice aliases and sounds.",
	"Your JAWS schemes, voice aliases and sounds don't come over, and NVDA keeps its own sounds; everything else is "
	"migrated. Installed now, it starts after NVDA restarts: open the assistant again then to bring them over.",
)

#: Status of an add-on (see addonStatus).
MISSING = "missing"
INSTALLED = "installed"
DISABLED = "disabled"
REMOVING = "removing"


def neededAddons() -> tuple:
	"""ClassicSpeech first, then the recommended Add-on Store add-ons."""
	return (CLASSIC_SPEECH_ADDON,) + tuple(managers.RECOMMENDED_ADDONS)


def versionKey(text) -> tuple | None:
	"""The numbers a version starts with, such as ``(1, 16)`` for ``v1.16`` or ``(2, 0)`` for ``2.0-beta``."""
	match = re.match(r"\s*[vV]?(\d+(?:\.\d+)*)", str(text or ""))
	if not match:
		return None
	return tuple(int(part) for part in match.group(1).split("."))


def compareVersions(first, second) -> int | None:
	"""-1, 0 or 1 as ``first`` is older than, the same as or newer than ``second``; None when either can't be read."""
	a, b = versionKey(first), versionKey(second)
	if a is None or b is None:
		return None
	width = max(len(a), len(b))
	a += (0,) * (width - len(a))
	b += (0,) * (width - len(b))
	return (a > b) - (a < b)


def decide(name: str, installed: str, latest: str, source: str) -> tuple[bool, str]:
	"""Whether to download ``latest`` when ``installed`` ("" for none) is there, and if not, why."""
	if not installed:
		return True, ""
	order = compareVersions(latest, installed)
	if order is None:
		return False, (
			f"{name} {installed} is installed and {source} has {latest}. The two versions can't be compared, "
			"so it was left as it is."
		)
	if order == 0:
		return False, f"{name} {installed} is already the newest version."
	if order < 0:
		return False, f"{name} {installed} is newer than the newest in {source} ({latest}), so it was left as it is."
	return True, ""


def installedVersions(addons: list | None = None) -> dict:
	"""``{add-on id, lower case: version}`` for the add-ons NVDA has or will have after a restart.

	A copy being removed doesn't count, but a newer copy waiting for the restart does, so an
	update already waiting is not downloaded again.
	"""
	versions: dict = {}
	for addon in addons if addons is not None else nvdaEnv.installedAddons():
		if addon.pendingRemove:
			continue
		key = addon.addonId.lower()
		if key not in versions or (compareVersions(addon.version, versions[key]) or 0) > 0:
			versions[key] = addon.version
	return versions


def addonStatus(addonId: str, addons: list | None = None) -> tuple[str, str]:
	"""``(status, version)`` of an add-on: MISSING, INSTALLED (running, or waiting for a restart),
	DISABLED, or REMOVING (being removed when NVDA restarts)."""
	matches = [addon for addon in (addons if addons is not None else nvdaEnv.installedAddons()) if addon.addonId.lower() == addonId.lower()]
	if not matches:
		return MISSING, ""
	kept = [addon for addon in matches if not addon.pendingRemove]
	if not kept:
		return REMOVING, matches[0].version
	newest = max(kept, key=lambda addon: versionKey(addon.version) or ())
	if newest.disabled:
		return DISABLED, newest.version
	return INSTALLED, newest.version


@dataclass
class Download:
	"""An add-on file downloaded and checked, ready for NVDA's installer."""

	addonId: str
	name: str
	version: str
	path: str
	#: The version installed before, "" for a new add-on.
	installed: str = ""
	source: str = ""

	def describe(self) -> str:
		if self.installed:
			return f"{self.name} was updated from version {self.installed} to {self.version}, from {self.source}; the new version starts after NVDA restarts."
		return f"{self.name} {self.version} was installed from {self.source}; it starts after NVDA restarts."


@dataclass
class Fetched:
	downloads: list = field(default_factory=list)
	#: Why add-ons were left as they are (already the newest, and the like).
	notes: list = field(default_factory=list)
	errors: list = field(default_factory=list)


def _assistantVersion() -> str:
	addon = updater.installedAddon()
	return addon[0] if addon else "1.3"


def latestClassicSpeech(session=None) -> updater.Release:
	"""ClassicSpeech's newest release on GitHub. Runs in a background thread. Raises updater.UpdateError."""
	return updater.fetchLatestRelease(_assistantVersion(), CLASSIC_SPEECH_REPOSITORY, session=session, product=CLASSIC_SPEECH_NAME)


def _fetchClassicSpeech(installed: str, folder: str, result: Fetched, say, session=None) -> None:
	say("Looking for the newest ClassicSpeech release on GitHub")
	try:
		release = latestClassicSpeech(session)
	except updater.UpdateError as error:
		result.errors.append(f"{CLASSIC_SPEECH_NAME}: {error}")
		return
	fetch, why = decide(CLASSIC_SPEECH_NAME, installed, release.version, GITHUB)
	debugLog.note(f"ClassicSpeech: installed {installed or 'none'}, newest release {release.version}: {'download' if fetch else why}")
	if not fetch:
		result.notes.append(why)
		return
	say(f"Downloading ClassicSpeech {release.version} from GitHub")
	try:
		path = updater.downloadRelease(release, _assistantVersion(), CLASSIC_SPEECH_REPOSITORY, folder, session=session)
	except updater.UpdateError as error:
		result.errors.append(f"{CLASSIC_SPEECH_NAME} {release.version}: {error}")
		return
	result.downloads.append(Download(CLASSIC_SPEECH_ID, CLASSIC_SPEECH_NAME, release.version, path, installed, GITHUB))


def _fetchFromStore(wanted: list, installed: dict, folder: str, language: str, result: Fetched, say, names: dict) -> None:
	say("Looking the add-ons up in the NVDA Add-on Store")
	try:
		entries = storeAddons.fetchEntries(wanted, language)
	except Exception as error:
		debugLog.error("the Add-on Store could not be read")
		result.errors.append(str(error) or error.__class__.__name__)
		return
	for addonId in wanted:
		name = names.get(addonId, addonId)
		entry = entries.get(addonId)
		if entry is None:
			result.errors.append(f"{name}: the Add-on Store has no version for this NVDA")
			continue
		have = installed.get(addonId.lower(), "")
		fetch, why = decide(entry.name, have, entry.version, ADDON_STORE)
		debugLog.note(f"{entry.name}: installed {have or 'none'}, newest in the Add-on Store {entry.version} ({entry.channel}): {'download' if fetch else why}")
		if not fetch:
			result.notes.append(why)
			continue
		say(f"Downloading {entry.name} {entry.version} from the Add-on Store")
		try:
			path = storeAddons.download(entry, folder)
		except Exception as error:
			result.errors.append(str(error) or f"{entry.name} could not be downloaded.")
			continue
		result.downloads.append(Download(entry.addonId, entry.name, entry.version, path, have, ADDON_STORE))


def fetchNewest(wanted: list, folder: str, addons: list | None = None, language: str = "en", progress=None, names: dict | None = None, session=None) -> Fetched:
	"""Download the newest version of each wanted add-on that is missing or older than it. Background thread.

	``wanted`` holds add-on ids: ClassicSpeech's comes from GitHub, the others from the Add-on Store.
	``progress(message)`` is called from this thread.
	"""
	result = Fetched()
	say = progress or (lambda message: None)
	installed = installedVersions(addons)
	storeWanted = [addonId for addonId in wanted if addonId.lower() != CLASSIC_SPEECH_ID.lower()]
	if len(storeWanted) != len(wanted):
		_fetchClassicSpeech(installed.get(CLASSIC_SPEECH_ID.lower(), ""), folder, result, say, session)
	if storeWanted:
		_fetchFromStore(storeWanted, installed, folder, language, result, say, names or {})
	return result


def _bundleName(path: str) -> str:
	"""The add-on name in a downloaded bundle's manifest, or "" when it can't be read."""
	try:
		import addonHandler

		bundleClass = getattr(addonHandler, "AddonBundle", None)
	except ImportError:
		bundleClass = None
	if bundleClass is not None:
		try:
			return str(bundleClass(path).manifest["name"])
		except Exception:
			return ""
	import zipfile

	try:
		with zipfile.ZipFile(path) as bundle:
			text = bundle.read("manifest.ini").decode("utf-8", "replace")
	except (OSError, KeyError, zipfile.BadZipFile):
		return ""
	match = re.search(r'(?m)^\s*name\s*=\s*"?([^"\r\n]+?)"?\s*$', text)
	return match.group(1).strip() if match else ""


def installDownloads(downloads: list) -> tuple[list, list]:
	"""Install downloaded add-ons with NVDA's installer. Main thread only.

	Returns ``(messages for the installed ones, errors)``. Each file is deleted afterwards.
	"""
	messages = []
	errors = []
	for item in downloads:
		try:
			name = _bundleName(item.path)
			if name.lower() != item.addonId.lower():
				raise storeAddons.StoreError(f"the download is the add-on '{name or 'unknown'}', not {item.name}, so it was not installed")
			storeAddons.install(item.path)
			messages.append(item.describe())
			debugLog.note(f"installed {item.name} {item.version} (was {item.installed or 'not installed'}) from {item.source}")
		except Exception as error:
			debugLog.error(f"{item.name} {item.version} could not be installed")
			errors.append(f"{item.name} {item.version}: {error}")
		finally:
			with contextlib.suppress(OSError):
				os.remove(item.path)
	return messages, errors
