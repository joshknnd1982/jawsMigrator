# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""JAWS sounds in ClassicSpeech: every JAWS sound at hand, and JAWS sounds in place of NVDA's own.

ClassicSpeech plays the active speech and sound scheme's "NVDA sound" items
(``nvdaSound.browseMode``, ``nvdaSound.focusMode``...) instead of NVDA's own
sounds while its speech and sound schemes are on. NVDA's own files, in its
program folder, are never changed. So all of this needs ClassicSpeech:

- ``importAllSounds`` copies every JAWS sound found into the scheme
  "JAWS Sounds (from JAWS)" in ``ClassicSpeech\\Schemes``, converted where
  needed so NVDA can play it, so each one is at hand in ClassicSpeech's scheme
  editor.
- ``applyNvdaSounds`` gives every ClassicSpeech scheme the JAWS sound for each
  NVDA sound JAWS has an equivalent for (``soundMap``), copied into that
  scheme's own Sounds folder, so JAWS sounds play whichever scheme is active.
  Items a scheme already has are left alone. It returns a record of exactly
  what it added.
- ``restoreNvdaSounds`` takes out exactly what that record lists, so NVDA plays
  its own sounds again. Items the user has changed since are left alone.
- ``backupNvdaSounds`` keeps a copy of NVDA's own sound files.

Nothing here needs NVDA: ClassicSpeech's settings section is passed in.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field

from . import jawsIndex, safety, soundMap, wavUtil

JAWS_SOUNDS_SCHEME = "JAWS Sounds (from JAWS)"
#: The assistant's record of the JAWS sounds it gave ClassicSpeech's schemes, in its state.json.
STATE_KEY = "classicNvdaSounds"
NVDA_SOUND_PREFIX = "nvdaSound."
SCHEME_FILE = "scheme.json"
SCHEME_FORMAT = "ClassicSpeech scheme"
SOUNDS_FOLDER = "Sounds"
DEFAULT_SCHEME = "Default"
RECORD_VERSION = 1
_INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def schemesRoot(configDir: str) -> str:
	return os.path.join(configDir, "ClassicSpeech", "Schemes")


def folderNameFor(name: str) -> str:
	"""A scheme's folder name, as ClassicSpeech makes it."""
	cleaned = _INVALID_NAME.sub("_", str(name or "")).strip().rstrip(". ") or "Scheme"
	return cleaned[:80].rstrip(". ") or "Scheme"


def _now() -> str:
	return datetime.datetime.now().isoformat(timespec="seconds")


def _sha256(path: str) -> str:
	digest = hashlib.sha256()
	with open(path, "rb") as stream:
		for chunk in iter(lambda: stream.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _sameContents(first: str, second: str) -> bool:
	try:
		if os.path.getsize(first) != os.path.getsize(second):
			return False
		with open(first, "rb") as left, open(second, "rb") as right:
			while True:
				chunk = left.read(64 * 1024)
				if chunk != right.read(64 * 1024):
					return False
				if not chunk:
					return True
	except OSError:
		return False


def _soundTarget(soundsFolder: str, fileName: str, source: str) -> tuple[str, bool]:
	"""Where ``source`` goes in a Sounds folder, and whether an identical copy is already there.

	Like ClassicSpeech: an identical file is reused; a different one with the same name gets a number.
	"""
	base, extension = os.path.splitext(fileName)
	candidate = os.path.join(soundsFolder, fileName)
	counter = 2
	while os.path.exists(candidate):
		if _sameContents(candidate, source):
			return candidate, True
		candidate = os.path.join(soundsFolder, f"{base} {counter}{extension}")
		counter += 1
	return candidate, False


# -- scheme folders ------------------------------------------------------------------------


def _emptyScheme(name: str) -> dict:
	return {
		"format": SCHEME_FORMAT,
		"version": 1,
		"name": name,
		"items": {},
		"custom": {"fonts": [], "fontSizes": [], "styles": [], "classes": []},
	}


def readScheme(folder: str) -> dict | None:
	"""A scheme folder's scheme.json as it is (every field kept), or None."""
	try:
		with open(os.path.join(folder, SCHEME_FILE), encoding="utf-8") as stream:
			data = json.load(stream)
	except (OSError, ValueError):
		return None
	if not isinstance(data, dict):
		return None
	if not isinstance(data.get("items"), dict):
		data["items"] = {}
	return data


def _writeScheme(folder: str, data: dict) -> None:
	"""Write scheme.json through a temporary file, so a failed write keeps the old one."""
	safety.checkWritable(folder)
	os.makedirs(folder, exist_ok=True)
	handle, temporary = tempfile.mkstemp(prefix=".scheme-", suffix=".tmp", dir=folder)
	try:
		with os.fdopen(handle, "w", encoding="utf-8") as stream:
			json.dump(data, stream, ensure_ascii=False, indent="\t")
		os.replace(temporary, os.path.join(folder, SCHEME_FILE))
	except BaseException:
		try:
			os.remove(temporary)
		except OSError:
			pass
		raise


def schemeFolders(root: str) -> list[tuple[str, str, dict]]:
	"""``(folder name, scheme name, scheme.json)`` for every scheme ClassicSpeech would find."""
	result = []
	try:
		entries = sorted(os.listdir(root), key=str.lower)
	except OSError:
		return result
	for entry in entries:
		folder = os.path.join(root, entry)
		if entry.startswith(".") or not os.path.isfile(os.path.join(folder, SCHEME_FILE)):
			continue
		data = readScheme(folder)
		if data is None:
			continue
		result.append((entry, str(data.get("name") or "").strip() or entry, data))
	return result


def _configured(settings) -> bool:
	if not isinstance(settings, dict):
		return False
	voice = settings.get("voice") if isinstance(settings.get("voice"), dict) else {}
	return bool(str(settings.get("sound") or "").strip()) or bool(voice.get("enabled"))


def _soundPath(folder: str, sound) -> str:
	sound = str(sound or "")
	return os.path.normpath(sound if os.path.isabs(sound) else os.path.join(folder, sound))


# -- JAWS sounds -----------------------------------------------------------------------------


def soundChoices(index, scope: str = jawsIndex.BOTH):
	"""``(choices, missing)``: the JAWS sound for each NVDA sound, as the user set them up in JAWS (see soundMap)."""
	return soundMap.chooseSounds(index.defaultJcf(scope), lambda name: index.soundFile(name, scope))


def uniqueSounds(wavFiles) -> list:
	"""One file per sound name, the user's own copy first, as JAWS picks them."""
	chosen = {}
	for indexed in sorted(wavFiles, key=lambda f: (f.scope != jawsIndex.USER, f.path.lower())):
		chosen.setdefault(indexed.name.lower(), indexed)
	return sorted(chosen.values(), key=lambda f: f.name.lower())


@dataclass
class ImportResult:
	folder: str = ""
	#: JAWS sounds now in the scheme's Sounds folder, and how many had to be converted.
	sounds: int = 0
	converted: int = 0
	failed: list = field(default_factory=list)


def importAllSounds(wavFiles, configDir: str) -> ImportResult:
	"""Copy every JAWS sound into the scheme JAWS Sounds (from JAWS), converted where needed so NVDA can play it."""
	folder = safety.checkWritable(os.path.join(schemesRoot(configDir), folderNameFor(JAWS_SOUNDS_SCHEME)))
	sounds = os.path.join(folder, SOUNDS_FOLDER)
	os.makedirs(sounds, exist_ok=True)
	result = ImportResult(folder=folder)
	for indexed in uniqueSounds(wavFiles):
		try:
			how = wavUtil.copyPlayable(indexed.path, os.path.join(sounds, indexed.name))
		except (OSError, wavUtil.WavError) as error:
			result.failed.append(f"{indexed.name}: {error}")
			continue
		result.sounds += 1
		if how == "converted":
			result.converted += 1
	# The scheme changes nothing by itself: its sounds wait to be chosen for items. Keep what the user set in it.
	data = readScheme(folder) or _emptyScheme(JAWS_SOUNDS_SCHEME)
	if not str(data.get("name") or "").strip():
		data["name"] = JAWS_SOUNDS_SCHEME
	_writeScheme(folder, data)
	return result


# -- JAWS sounds in place of NVDA's ------------------------------------------------------


@dataclass
class SoundsResult:
	#: Schemes that play JAWS sounds for NVDA's, by name.
	schemes: list = field(default_factory=list)
	added: int = 0
	removed: int = 0
	#: Items left as the user has them, as ``"scheme: sound"``.
	kept: list = field(default_factory=list)
	failed: list = field(default_factory=list)
	record: dict = field(default_factory=dict)


def _cleanRecord(record) -> dict:
	record = copy.deepcopy(record) if isinstance(record, dict) else {}
	record["version"] = RECORD_VERSION
	schemes = record.get("schemes") if isinstance(record.get("schemes"), dict) else {}
	for folderName, entry in list(schemes.items()):
		if not isinstance(entry, dict):
			del schemes[folderName]
			continue
		entry["items"] = entry.get("items") if isinstance(entry.get("items"), dict) else {}
		entry["files"] = entry.get("files") if isinstance(entry.get("files"), dict) else {}
	record["schemes"] = schemes
	record["sounds"] = record.get("sounds") if isinstance(record.get("sounds"), dict) else {}
	return record


def isApplied(record) -> bool:
	return isinstance(record, dict) and any(isinstance(entry, dict) and entry.get("items") for entry in (record.get("schemes") or {}).values())


def applyNvdaSounds(choices, configDir: str, record=None) -> SoundsResult:
	"""Give every ClassicSpeech scheme the JAWS sound for each NVDA sound that JAWS has one for.

	Each sound is copied, converted where needed, into the scheme's own Sounds folder, so every
	scheme folder stays complete, as ClassicSpeech keeps them. Items a scheme already has are left
	as they are. ``record`` is an earlier record to add to; the result's record lists exactly what
	was added, for ``restoreNvdaSounds``.
	"""
	root = safety.checkWritable(schemesRoot(configDir))
	os.makedirs(root, exist_ok=True)
	result = SoundsResult()
	record = _cleanRecord(record)
	staging = tempfile.mkdtemp(prefix="jawsMigrator-sounds-")
	try:
		staged = {}
		for choice in choices:
			fileName = os.path.basename(choice.jawsPath)
			path = os.path.join(staging, choice.event.nvdaName, fileName)
			try:
				os.makedirs(os.path.dirname(path), exist_ok=True)
				wavUtil.copyPlayable(choice.jawsPath, path)
			except (OSError, wavUtil.WavError) as error:
				result.failed.append(f"{choice.event.label}: {fileName} could not be used ({error})")
				continue
			staged[choice.event.nvdaName] = (path, fileName, _sha256(path))
			record["sounds"][choice.event.nvdaName] = choice.jawsName
		folders = schemeFolders(root)
		if not folders:
			# ClassicSpeech makes its Default scheme the first time it starts; make it now.
			folders = [(DEFAULT_SCHEME, DEFAULT_SCHEME, _emptyScheme(DEFAULT_SCHEME))]
		for folderName, schemeName, data in folders:
			folder = os.path.join(root, folderName)
			entry = record["schemes"].get(folderName) or {"name": schemeName, "items": {}, "files": {}}
			items = data["items"]
			changed = False
			for nvdaName, (source, fileName, digest) in staged.items():
				itemId = NVDA_SOUND_PREFIX + nvdaName
				if _configured(items.get(itemId)):
					if itemId not in entry["items"]:
						result.kept.append(f"{schemeName}: {nvdaName}")
					continue
				try:
					sounds = safety.checkWritable(os.path.join(folder, SOUNDS_FOLDER))
					os.makedirs(sounds, exist_ok=True)
					target, present = _soundTarget(sounds, fileName, source)
					relative = f"{SOUNDS_FOLDER}/{os.path.basename(target)}"
					if not present:
						shutil.copyfile(source, target)
						entry["files"][relative] = digest
				except OSError as error:
					result.failed.append(f"{schemeName}: {nvdaName} ({error})")
					continue
				items[itemId] = {"sound": relative, "soundOnly": False}
				entry["items"][itemId] = {"sound": relative, "sha256": digest}
				changed = True
				result.added += 1
			if changed:
				try:
					_writeScheme(folder, data)
				except OSError as error:
					result.failed.append(f"{schemeName}: {error}")
					continue
			if entry["items"]:
				entry["name"] = schemeName
				record["schemes"][folderName] = entry
				result.schemes.append(schemeName)
	finally:
		shutil.rmtree(staging, ignore_errors=True)
	record.setdefault("applied", _now())
	record["updated"] = _now()
	result.record = record
	return result


def restoreNvdaSounds(configDir: str, record) -> SoundsResult:
	"""Take out exactly the JAWS sounds ``applyNvdaSounds`` added, so NVDA plays its own sounds again."""
	root = schemesRoot(configDir)
	result = SoundsResult()
	record = _cleanRecord(record)
	current = {folderName: (schemeName, data) for folderName, schemeName, data in schemeFolders(root)}
	byName = {schemeName.lower(): folderName for folderName, (schemeName, _data) in current.items()}
	for folderName, entry in record["schemes"].items():
		recordedName = str(entry.get("name") or "")
		target = folderName if folderName in current and (not recordedName or current[folderName][0].lower() == recordedName.lower()) else None
		target = target or byName.get(recordedName.lower())
		if target is None:
			result.failed.append(f"{recordedName or folderName}: the scheme was renamed or deleted, so it was left as it is")
			continue
		schemeName, data = current[target]
		folder = os.path.join(root, target)
		items = data["items"]
		changed = False
		for itemId, added in entry["items"].items():
			settings = items.get(itemId)
			if not isinstance(settings, dict) or not settings.get("sound"):
				continue
			path = _soundPath(folder, settings["sound"])
			voice = settings.get("voice") if isinstance(settings.get("voice"), dict) else {}
			exists = os.path.isfile(path)
			samePlace = os.path.normcase(path) == os.path.normcase(_soundPath(folder, added.get("sound")))
			sameSound = exists and added.get("sha256") and _sha256(path) == added["sha256"]
			if voice.get("enabled") or not (sameSound or (samePlace and not exists)):
				# Changed in ClassicSpeech since: the user's choice now.
				result.kept.append(f"{schemeName}: {itemId[len(NVDA_SOUND_PREFIX) :]}")
				continue
			del items[itemId]
			changed = True
			result.removed += 1
		if changed:
			try:
				_writeScheme(folder, data)
			except OSError as error:
				result.failed.append(f"{schemeName}: {error}")
				continue
		referenced = {os.path.normcase(_soundPath(folder, settings.get("sound"))) for settings in items.values() if isinstance(settings, dict) and settings.get("sound")}
		for relative, digest in entry["files"].items():
			path = _soundPath(folder, relative)
			if os.path.normcase(path) in referenced or not os.path.isfile(path):
				continue
			try:
				if _sha256(path) == digest:
					os.remove(safety.checkWritable(path))
			except OSError:
				pass
		result.schemes.append(schemeName)
	result.record = record
	return result


# -- ClassicSpeech's switch, and NVDA's own sounds --------------------------------------------


def _switches(section) -> dict:
	try:
		data = json.loads(section.get("schemeData", "") or "{}")
	except (TypeError, ValueError):
		data = {}
	return data if isinstance(data, dict) else {}


def schemesEnabled(section) -> bool:
	"""Whether ClassicSpeech's speech and sound schemes are on (they are unless turned off)."""
	return bool(_switches(section).get("enabled", True))


def _setSchemesEnabled(section, enabled: bool) -> bool:
	data = _switches(section)
	if bool(data.get("enabled", True)) == enabled:
		return False
	data["version"] = 2
	data["enabled"] = enabled
	data.setdefault("activeScheme", DEFAULT_SCHEME)
	section["schemeData"] = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
	return True


def enableSchemes(section) -> bool:
	"""Turn ClassicSpeech's speech and sound schemes on, as its settings do. True when they were off."""
	return _setSchemesEnabled(section, True)


def disableSchemes(section) -> bool:
	return _setSchemesEnabled(section, False)


def backupNvdaSounds(wavesDir: str, dataDir: str, nvdaVersion: str = "") -> str:
	"""Copy NVDA's own sound files into ``nvdaSounds\\<NVDA version>`` in the assistant's folder. Returns the folder."""
	if not wavesDir or not os.path.isdir(wavesDir):
		return ""
	folder = safety.checkWritable(os.path.join(dataDir, "nvdaSounds", folderNameFor(nvdaVersion or "NVDA")))
	os.makedirs(folder, exist_ok=True)
	for name in sorted(os.listdir(wavesDir)):
		source = os.path.join(wavesDir, name)
		if name.lower().endswith(".wav") and os.path.isfile(source):
			target = os.path.join(folder, name)
			if not _sameContents(source, target):
				shutil.copy2(source, target)
	return folder


def statusText(record) -> str:
	if not isApplied(record):
		return "NVDA plays its own sounds."
	sounds = record.get("sounds") or {}
	schemes = [entry.get("name") for entry in record["schemes"].values() if entry.get("items")]
	return f"JAWS sounds play in place of {len(sounds)} of NVDA's sounds, through {len(schemes)} ClassicSpeech schemes."
