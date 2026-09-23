# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Install the recommended add-ons from the NVDA Add-on Store.

The assistant reads the same catalog NVDA's Add-on Store uses
(``addonStore.nvaccess.org``, or the server set in NVDA's Add-on Store
settings), picks the newest stable version compatible with this NVDA,
downloads it, checks it against the SHA-256 the store publishes, and installs
it with NVDA's own add-on installer. The add-ons start after NVDA restarts.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

DEFAULT_STORE = "https://addonStore.nvaccess.org"
TIMEOUT = (15, 120)
MAX_BYTES = 100 * 1024 * 1024


class StoreError(Exception):
	pass


@dataclass
class StoreEntry:
	addonId: str
	name: str
	version: str
	url: str
	sha256: str
	channel: str
	publisher: str = ""
	homepage: str = ""
	description: str = ""

	@property
	def fileName(self) -> str:
		return f"{self.addonId}-{self.version}.nvda-addon"


def _versionTuple(data) -> tuple:
	if not isinstance(data, dict):
		return (0, 0, 0)
	return (int(data.get("major") or 0), int(data.get("minor") or 0), int(data.get("patch") or 0))


def _apiVersions() -> tuple[tuple, tuple]:
	try:
		import addonAPIVersion

		return tuple(addonAPIVersion.CURRENT), tuple(addonAPIVersion.BACK_COMPAT_TO)
	except Exception:
		return (2026, 1, 0), (2026, 1, 0)


def storeUrl(language: str) -> str:
	base = DEFAULT_STORE
	try:
		import config

		base = config.conf["addonStore"]["baseServerURL"] or DEFAULT_STORE
	except Exception:
		pass
	current, _backCompat = _apiVersions()
	return f"{base.rstrip('/')}/{language}/all/{current[0]}.{current[1]}.{current[2]}.json"


def _requests():
	try:
		import requests

		return requests
	except Exception as error:
		raise StoreError("NVDA's internet support is not available.") from error


def _userAgent() -> dict:
	return {"User-Agent": "NVDA JAWS Migration Assistant (+https://github.com/joshknnd1982/jawsMigrator)"}


def pickEntries(catalog: list, wanted: list[str]) -> dict:
	"""The best compatible release of each wanted add-on: stable before beta, newest first."""
	current, backCompat = _apiVersions()
	wantedLower = {addonId.lower(): addonId for addonId in wanted}
	best: dict = {}
	for data in catalog if isinstance(catalog, list) else []:
		if not isinstance(data, dict):
			continue
		addonId = str(data.get("addonId") or "")
		if addonId.lower() not in wantedLower:
			continue
		if _versionTuple(data.get("minNVDAVersion")) > current or _versionTuple(data.get("lastTestedVersion")) < backCompat:
			continue
		channel = str(data.get("channel") or "stable")
		if channel not in ("stable", "beta"):
			continue
		rank = (channel == "stable", _versionTuple(data.get("addonVersionNumber")))
		key = wantedLower[addonId.lower()]
		if key in best and best[key][0] >= rank:
			continue
		entry = StoreEntry(
			addonId=addonId,
			name=str(data.get("displayName") or addonId),
			version=str(data.get("addonVersionName") or ""),
			url=str(data.get("URL") or ""),
			sha256=str(data.get("sha256") or "").lower(),
			channel=channel,
			publisher=str(data.get("publisher") or ""),
			homepage=str(data.get("homepage") or ""),
			description=str(data.get("description") or ""),
		)
		if entry.url and len(entry.sha256) == 64:
			best[key] = (rank, entry)
	return {key: value[1] for key, value in best.items()}


def fetchEntries(wanted: list[str], language: str = "en") -> dict:
	"""Look the wanted add-ons up in the Add-on Store. Runs in a background thread."""
	requests = _requests()
	lastError = None
	for lang in dict.fromkeys([language.split("_", 1)[0] if language else "en", "en"]):
		try:
			response = requests.get(storeUrl(lang), headers=_userAgent(), timeout=TIMEOUT)
		except Exception as error:
			lastError = error
			continue
		if response.status_code == 200:
			try:
				return pickEntries(response.json(), wanted)
			except ValueError as error:
				raise StoreError("The Add-on Store's answer could not be read.") from error
		lastError = StoreError(f"The Add-on Store answered with error {response.status_code}.")
	raise StoreError(f"The Add-on Store could not be reached. {lastError or ''}".strip())


def download(entry: StoreEntry, folder: str) -> str:
	"""Download an add-on and check its SHA-256. Returns the file's path."""
	from . import safety

	requests = _requests()
	os.makedirs(safety.checkWritable(folder), exist_ok=True)
	path = os.path.join(folder, entry.fileName)
	digest = hashlib.sha256()
	size = 0
	try:
		with requests.get(entry.url, headers=_userAgent(), stream=True, timeout=TIMEOUT) as response:
			if response.status_code != 200:
				raise StoreError(f"{entry.name} could not be downloaded (error {response.status_code}).")
			with open(path, "wb") as stream:
				for chunk in response.iter_content(chunk_size=128 * 1024):
					if not chunk:
						continue
					size += len(chunk)
					if size > MAX_BYTES:
						raise StoreError(f"{entry.name} is larger than expected.")
					digest.update(chunk)
					stream.write(chunk)
	except StoreError:
		_remove(path)
		raise
	except Exception as error:
		_remove(path)
		raise StoreError(f"{entry.name} could not be downloaded.") from error
	if digest.hexdigest() != entry.sha256:
		_remove(path)
		raise StoreError(f"The download of {entry.name} did not match the Add-on Store's checksum, so it was deleted.")
	return path


def _remove(path: str) -> None:
	try:
		os.remove(path)
	except OSError:
		pass


def install(path: str) -> None:
	"""Install a downloaded add-on with NVDA's installer. Main thread only. Raises StoreError."""
	try:
		from addonStore.install import installAddon

		installAddon(path)
		return
	except ImportError:
		pass
	except Exception as error:
		message = getattr(error, "displayMessage", None) or str(error)
		raise StoreError(message) from error
	try:
		import addonHandler

		bundle = addonHandler.AddonBundle(path)
		addonHandler.installAddonBundle(bundle)
	except Exception as error:
		raise StoreError(str(error)) from error
