# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Backups of NVDA's settings, add-ons and add-on settings, taken before a migration and restorable at any time.

A backup is a folder under ``jawsMigrator\\backups`` in NVDA's settings folder. It holds a copy of
NVDA's whole settings folder: nvda.ini, input gestures, configuration profiles, speech
dictionaries, symbols, ClassicSpeech, every installed add-on (the ``addons`` folder), the settings
and data add-ons keep in their own files and folders, and NVDA's record of which add-ons are
enabled (addonsState.json). Only what NVDA downloads again by itself is left out: the Add-on
Store's cache and NVDA update downloads. NVDA's own sound files, and the assistant's record of
replaced sounds and sleeping applications, are kept too.

Files that did not change since the previous backup are hard links to it, so backing up a big
add-on collection again takes almost no extra space. ``backup.json`` lists every file with its
size and SHA-256, and every add-on with its version. The backup taken before the first migration
is marked as the original and is never removed automatically.

Restoring puts changed and missing files back and removes what a migration creates (a "JAWS
settings" profile, ClassicSpeech schemes, input gestures). Add-ons go back the way NVDA itself
installs and removes them, through an ``AddonManager``: add-ons installed since the backup are
removed, missing or changed ones are reinstalled from the backup, and each is enabled or disabled
as it was. NVDA finishes those changes when it restarts. The assistant never changes its own
add-on. Callers back up the current settings before restoring, so a restore can be undone too.
This module only works with files; reloading NVDA is done by the caller in NVDA's main thread.
"""

from __future__ import annotations

import datetime
import fnmatch
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field

from . import safety

BACKUP_FORMAT = "JAWS Migration Assistant NVDA settings backup"
#: 1: NVDA's settings only (version 1.0 of the assistant). 2: the whole settings folder, add-ons included.
BACKUP_VERSION = 2
MANIFEST = "backup.json"

#: Files and folders in NVDA's settings folder that a migration writes. On restore, files there
#: that the backup does not have are removed; elsewhere, newer files are left alone.
CONFIG_FILES = ("nvda.ini", "gestures.ini", "profileTriggers.ini")
CONFIG_PATTERNS = ("symbols-*.dic",)
CONFIG_FOLDERS = ("profiles", "speechDicts", "ClassicSpeech")
#: The assistant's own files that describe migrated sounds and applications.
ADDON_FILES = ("state.json",)
ADDON_FOLDERS = ("sounds",)
#: NVDA's add-on folder and its record of add-on states, put back through NVDA's add-on handling.
ADDONS_FOLDER = "addons"
ADDON_STATE_FILES = ("addonsState.json", "addonsState.pickle")
#: Not backed up (lower-case paths in NVDA's settings folder): what NVDA downloads or builds again
#: by itself, and add-on folders NVDA is in the middle of deleting.
SKIPPED = (
	"updates",
	"addonstore/_dl",
	"addonstore/_cached*addons.json",
	"__pycache__",
	"*/__pycache__",
	"addons/*.delete",
)
#: The assistant's own add-on, which backups leave out and restores never change.
SELF_ADDON = "jawsMigrator"
PENDING_INSTALL_SUFFIX = ".pendingInstall"
#: Free space kept in reserve when checking whether a backup fits on the disk.
SPACE_MARGIN = 100 * 1024 * 1024

# What a restore does with an add-on.
REMOVE = "remove"
REINSTALL = "reinstall"
KEEP = "keep"
ENABLE = "enable"
DISABLE = "disable"


@dataclass
class BackupInfo:
	path: str
	created: str = ""
	reason: str = ""
	nvdaVersion: str = ""
	addonVersion: str = ""
	files: list = field(default_factory=list)
	absent: list = field(default_factory=list)
	nvdaSounds: int = 0
	version: int = BACKUP_VERSION
	#: The backup taken before the first migration: never removed automatically.
	original: bool = False
	#: Add-ons installed when the backup was made: ``{"name", "version", "folder", "pendingInstall"}``.
	addons: list = field(default_factory=list)
	#: NVDA's record of add-on states (addonsState.json) when the backup was made.
	addonState: dict = field(default_factory=dict)
	#: Files that could not be read when the backup was made, with the reason.
	skipped: list = field(default_factory=list)
	#: Bytes the backup holds, and bytes it copied (the rest are hard links to an earlier backup).
	totalSize: int = 0
	copiedSize: int = 0

	@property
	def name(self) -> str:
		return os.path.basename(self.path)

	@property
	def label(self) -> str:
		when = self.created.replace("T", " ")[:19] if self.created else self.name
		text = f"{when} - {self.reason}" if self.reason else when
		if self.original:
			text += " (your NVDA settings before the first JAWS migration)"
		if self.version < 2:
			text += " (NVDA settings only, without add-ons)"
		return text


@dataclass
class AddonRecord:
	"""An add-on as it is now."""

	name: str
	version: str
	path: str
	pendingInstall: bool = False
	pendingRemove: bool = False
	#: Disabled, or will be once NVDA restarts.
	disabled: bool = False


@dataclass
class AddonAction:
	name: str
	kind: str
	description: str


@dataclass
class RestoreResult:
	restored: list = field(default_factory=list)
	removed: list = field(default_factory=list)
	failed: list = field(default_factory=list)
	addonActions: list = field(default_factory=list)

	@property
	def restartNeeded(self) -> bool:
		"""Add-on changes finish when NVDA restarts."""
		return bool(self.addonActions)


# -- files -----------------------------------------------------------------------------------


def _sha256(path: str) -> str:
	digest = hashlib.sha256()
	with open(path, "rb") as stream:
		for chunk in iter(lambda: stream.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _copy(source: str, destination: str) -> None:
	os.makedirs(os.path.dirname(destination), exist_ok=True)
	shutil.copy2(source, destination)


def _copyWithHash(source: str, destination: str) -> str:
	"""Copy a file, keeping its times, and return its SHA-256."""
	os.makedirs(os.path.dirname(destination), exist_ok=True)
	digest = hashlib.sha256()
	with open(source, "rb") as reader, open(destination, "wb") as writer:
		for chunk in iter(lambda: reader.read(1024 * 1024), b""):
			digest.update(chunk)
			writer.write(chunk)
	shutil.copystat(source, destination)
	return digest.hexdigest()


def _link(source: str, destination: str) -> bool:
	"""Make ``destination`` a hard link to ``source``, when the disk allows it."""
	os.makedirs(os.path.dirname(destination), exist_ok=True)
	try:
		os.link(source, destination)
		return True
	except (OSError, AttributeError, NotImplementedError):
		return False


def _freeSpace(folder: str) -> int | None:
	path = os.path.abspath(folder)
	while path and not os.path.isdir(path):
		parent = os.path.dirname(path)
		if parent == path:
			return None
		path = parent
	try:
		return shutil.disk_usage(path).free
	except OSError:
		return None


def sizeText(size: int) -> str:
	if size >= 1024**3:
		return f"{size / 1024**3:.1f} GB"
	if size >= 1024**2:
		return f"{round(size / 1024**2):,} MB"
	return f"{max(1, round(size / 1024)):,} KB" if size else "0 KB"


def _key(root: str, relative: str) -> str:
	return f"{root}:{relative.replace(os.sep, '/').lower()}"


def _skipPatterns(configDir: str, addonDir: str) -> tuple:
	patterns = list(SKIPPED)
	patterns += [f"{ADDONS_FOLDER}/{SELF_ADDON.lower()}", f"{ADDONS_FOLDER}/{SELF_ADDON.lower()}{PENDING_INSTALL_SUFFIX.lower()}"]
	try:
		own = os.path.relpath(addonDir, configDir)
	except ValueError:
		own = ""
	if own and own != "." and not own.startswith(".."):
		# The assistant's own folder: its backups are not backed up again.
		patterns.append(own.replace(os.sep, "/").lower())
	return tuple(patterns)


def _isSkipped(relative: str, patterns: tuple) -> bool:
	path = relative.replace(os.sep, "/").lower()
	return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _walk(configDir: str, patterns: tuple):
	"""``(relative path, full path)`` of every file in NVDA's settings folder that is backed up."""
	for current, dirs, files in os.walk(configDir):
		relativeDir = os.path.relpath(current, configDir)
		if relativeDir == ".":
			relativeDir = ""
		dirs[:] = sorted(name for name in dirs if not _isSkipped(os.path.join(relativeDir, name), patterns))
		for name in sorted(files):
			relative = os.path.join(relativeDir, name)
			if not _isSkipped(relative, patterns):
				yield relative, os.path.join(current, name)


def _isEssential(root: str, relative: str) -> bool:
	"""Files a backup cannot do without: everything a migration changes."""
	if root == "addon":
		return True
	parts = relative.replace(os.sep, "/").split("/")
	if len(parts) == 1:
		name = parts[0].lower()
		return name in (f.lower() for f in CONFIG_FILES + ADDON_STATE_FILES) or any(fnmatch.fnmatchcase(name, p.lower()) for p in CONFIG_PATTERNS)
	return parts[0].lower() in (f.lower() for f in CONFIG_FOLDERS)


# -- add-ons as files ------------------------------------------------------------------------

_MANIFEST_VALUE = re.compile(r"^\s*(name|version)\s*=\s*(.*?)\s*$", re.IGNORECASE)


def _readAddonManifest(folder: str) -> dict | None:
	"""``name`` and ``version`` from an add-on's manifest.ini, or None."""
	try:
		with open(os.path.join(folder, "manifest.ini"), encoding="utf-8-sig", errors="replace") as stream:
			lines = stream.read().splitlines()
	except OSError:
		return None
	values = {}
	inText = False
	for line in lines:
		if not inText:
			match = _MANIFEST_VALUE.match(line)
			if match and match.group(1).lower() not in values:
				value = match.group(2)
				if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
					value = value[1:-1]
				values[match.group(1).lower()] = value
		if line.count('"""') % 2 or line.count("'''") % 2:
			# Inside a triple-quoted description or changelog, lines are text, not settings.
			inText = not inText
	return values if values.get("name") else None


def addonRecords(addonsDir: str) -> list[dict]:
	"""Every add-on folder: ``{"name", "version", "folder", "pendingInstall"}``."""
	records = []
	try:
		names = sorted(os.listdir(addonsDir))
	except OSError:
		return records
	for folder in names:
		path = os.path.join(addonsDir, folder)
		if not os.path.isdir(path) or folder.lower().endswith(".delete"):
			continue
		manifest = _readAddonManifest(path)
		if manifest is None:
			continue
		records.append(
			{
				"name": manifest["name"],
				"version": manifest.get("version", ""),
				"folder": folder,
				"pendingInstall": folder.lower().endswith(PENDING_INSTALL_SUFFIX.lower()),
			},
		)
	return records


def readAddonState(configDir: str) -> dict:
	try:
		with open(os.path.join(configDir, ADDON_STATE_FILES[0]), encoding="utf-8") as stream:
			data = json.load(stream)
	except (OSError, ValueError):
		return {}
	return data if isinstance(data, dict) else {}


def _inState(state: dict, category: str, name: str) -> bool:
	values = state.get(category) or ()
	return isinstance(values, (list, tuple, set)) and name.lower() in {str(value).lower() for value in values}


def _disabledIn(state: dict, name: str) -> bool:
	disabled = _inState(state, "disabledAddons", name) or _inState(state, "pendingDisableSet", name)
	return disabled and not _inState(state, "pendingEnableSet", name)


def _compatibilityOverridden(state: dict, name: str) -> bool:
	return _inState(state, "overrideCompatibility", name) or _inState(state, "PENDING_OVERRIDE_COMPATIBILITY", name)


# -- making backups ------------------------------------------------------------------------


def backupsFolder(addonDir: str) -> str:
	return os.path.join(addonDir, "backups")


def _newBackupFolder(addonDir: str) -> str:
	stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
	folder = os.path.join(backupsFolder(addonDir), stamp)
	counter = 1
	while os.path.exists(folder):
		counter += 1
		folder = os.path.join(backupsFolder(addonDir), f"{stamp}-{counter}")
	return folder


def _linkSources(addonDir: str) -> dict:
	"""``{key: (entry, path)}`` for the newest full backup's files, to hard-link unchanged files to."""
	try:
		names = sorted(os.listdir(backupsFolder(addonDir)), reverse=True)
	except OSError:
		names = []
	for name in names:
		info = readBackup(os.path.join(backupsFolder(addonDir), name))
		if info is not None and info.version >= 2:
			sources = {}
			for entry in info.files:
				root = entry.get("root", "config")
				sources[_key(root, entry["relative"])] = (entry, os.path.join(info.path, root, entry["relative"].replace("/", os.sep)))
			return sources
	return {}


def _plan(configDir: str, addonDir: str):
	"""What a backup would hold: ``(work, absent, skipped, needed)``.

	``work`` is ``(root, relative, path, stat, linkSource or None)`` for each file, and ``needed``
	the bytes that have to be copied because no earlier backup has them.
	"""
	patterns = _skipPatterns(configDir, addonDir)
	files = [("config", relative, path) for relative, path in _walk(configDir, patterns)]
	absent = []
	for name in CONFIG_FILES:
		if not os.path.isfile(os.path.join(configDir, name)):
			absent.append({"relative": name, "root": "config"})
	for folderName in CONFIG_FOLDERS:
		if not os.path.isdir(os.path.join(configDir, folderName)):
			absent.append({"relative": folderName, "root": "config", "folder": True})
	for name in ADDON_FILES:
		path = os.path.join(addonDir, name)
		if os.path.isfile(path):
			files.append(("addon", name, path))
		else:
			absent.append({"relative": name, "root": "addon"})
	for folderName in ADDON_FOLDERS:
		root = os.path.join(addonDir, folderName)
		if not os.path.isdir(root):
			absent.append({"relative": folderName, "root": "addon", "folder": True})
			continue
		for current, _dirs, names in os.walk(root):
			for name in sorted(names):
				path = os.path.join(current, name)
				files.append(("addon", os.path.relpath(path, addonDir), path))
	sources = _linkSources(addonDir)
	work = []
	skipped = []
	needed = 0
	for root, relative, path in files:
		try:
			stat = os.stat(path)
		except OSError as error:
			if _isEssential(root, relative):
				raise
			skipped.append({"relative": relative.replace(os.sep, "/"), "root": root, "reason": str(error)})
			continue
		source = sources.get(_key(root, relative))
		linkable = source is not None and source[0].get("size") == stat.st_size and source[0].get("mtime") == stat.st_mtime_ns and os.path.isfile(source[1])
		if not linkable:
			source = None
			needed += stat.st_size
		work.append((root, relative, path, stat, source))
	return work, absent, skipped, needed


def estimateBackup(configDir: str, addonDir: str) -> tuple[int, int, int]:
	"""``(files, bytes, new bytes)`` of the next backup; new bytes are what it has to copy."""
	work, _absent, _skipped, needed = _plan(configDir, addonDir)
	return len(work), sum(item[3].st_size for item in work), needed


def createBackup(
	configDir: str,
	addonDir: str,
	wavesDir: str,
	reason: str,
	nvdaVersion: str = "",
	addonVersion: str = "",
	original: bool = False,
	progress=None,
) -> BackupInfo:
	"""Copy NVDA's settings, add-ons and add-on settings into a new backup folder. Raises OSError when it can't.

	``progress(message)`` is called from time to time with how far the backup got.
	"""
	folder = safety.checkWritable(_newBackupFolder(addonDir))
	info = BackupInfo(
		path=folder,
		created=datetime.datetime.now().isoformat(timespec="seconds"),
		reason=reason,
		nvdaVersion=nvdaVersion,
		addonVersion=addonVersion,
		original=original,
	)
	work, info.absent, info.skipped, needed = _plan(configDir, addonDir)
	free = _freeSpace(folder)
	if free is not None and needed + SPACE_MARGIN > free:
		raise OSError(
			f"There is not enough free disk space to back up NVDA's settings and add-ons: the backup needs about "
			f"{sizeText(needed + SPACE_MARGIN)}, and {sizeText(free)} are free. Free some space and try again.",
		)
	os.makedirs(folder)
	try:
		total = len(work)
		nextReport = 0.25
		for number, (root, relative, path, stat, source) in enumerate(work, 1):
			destination = os.path.join(folder, root, relative)
			entry = {"relative": relative.replace(os.sep, "/"), "root": root, "size": stat.st_size, "mtime": stat.st_mtime_ns}
			try:
				if source is not None and _link(source[1], destination):
					entry["sha256"] = source[0].get("sha256", "")
				else:
					entry["sha256"] = _copyWithHash(path, destination)
					copied = os.stat(destination)
					entry["size"], entry["mtime"] = copied.st_size, copied.st_mtime_ns
					info.copiedSize += copied.st_size
			except OSError as error:
				if _isEssential(root, relative):
					raise
				# A file another program keeps locked, such as an add-on's open database.
				info.skipped.append({"relative": entry["relative"], "root": root, "reason": str(error)})
				continue
			info.files.append(entry)
			info.totalSize += entry["size"]
			if progress is not None and total and number / total >= nextReport:
				progress(f"Backing up NVDA's settings and add-ons: {number * 100 // total}% ({number:,} of {total:,} files)")
				while nextReport <= number / total:
					nextReport += 0.25
		info.addons = addonRecords(os.path.join(configDir, ADDONS_FOLDER))
		info.addons = [record for record in info.addons if record["name"].lower() != SELF_ADDON.lower()]
		info.addonState = readAddonState(configDir)
		# NVDA's own sounds, which the assistant never changes, kept so they can always be compared or recovered.
		if wavesDir and os.path.isdir(wavesDir):
			soundsTarget = os.path.join(folder, "nvdaSounds")
			for name in sorted(os.listdir(wavesDir)):
				path = os.path.join(wavesDir, name)
				if name.lower().endswith(".wav") and os.path.isfile(path):
					_copy(path, os.path.join(soundsTarget, name))
					info.nvdaSounds += 1
		_writeManifest(info)
	except BaseException:
		shutil.rmtree(folder, ignore_errors=True)
		raise
	return info


def _writeManifest(info: BackupInfo) -> None:
	payload = {
		"format": BACKUP_FORMAT,
		"version": info.version,
		"created": info.created,
		"reason": info.reason,
		"original": info.original,
		"nvdaVersion": info.nvdaVersion,
		"addonVersion": info.addonVersion,
		"totalSize": info.totalSize,
		"copiedSize": info.copiedSize,
		"addons": info.addons,
		"addonState": info.addonState,
		"skipped": info.skipped,
		"files": info.files,
		"absent": info.absent,
		"nvdaSounds": info.nvdaSounds,
	}
	with open(os.path.join(info.path, MANIFEST), "w", encoding="utf-8") as stream:
		json.dump(payload, stream, ensure_ascii=False, indent="\t")


def readBackup(folder: str) -> BackupInfo | None:
	try:
		with open(os.path.join(folder, MANIFEST), encoding="utf-8") as stream:
			payload = json.load(stream)
	except (OSError, ValueError):
		return None
	if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT:
		return None
	return BackupInfo(
		path=folder,
		created=str(payload.get("created") or ""),
		reason=str(payload.get("reason") or ""),
		nvdaVersion=str(payload.get("nvdaVersion") or ""),
		addonVersion=str(payload.get("addonVersion") or ""),
		files=list(payload.get("files") or []),
		absent=list(payload.get("absent") or []),
		nvdaSounds=int(payload.get("nvdaSounds") or 0),
		version=int(payload.get("version") or 1),
		original=bool(payload.get("original")),
		addons=list(payload.get("addons") or []),
		addonState=payload.get("addonState") if isinstance(payload.get("addonState"), dict) else {},
		skipped=list(payload.get("skipped") or []),
		totalSize=int(payload.get("totalSize") or 0),
		copiedSize=int(payload.get("copiedSize") or 0),
	)


def listBackups(addonDir: str) -> list[BackupInfo]:
	"""Every readable backup, newest first."""
	root = backupsFolder(addonDir)
	try:
		names = sorted(os.listdir(root), reverse=True)
	except OSError:
		return []
	backups = []
	for name in names:
		info = readBackup(os.path.join(root, name))
		if info is not None:
			backups.append(info)
	return backups


def hasOriginal(addonDir: str) -> bool:
	return any(info.original for info in listBackups(addonDir))


def verifyBackup(info: BackupInfo, thorough: bool = False) -> list[str]:
	"""Problems with a backup's files: missing, or changed since it was made.

	Sizes are always checked; contents (SHA-256) when ``thorough``, and for the small backups of
	version 1. A restore also checks the contents of every file it puts back.
	"""
	thorough = thorough or info.version < 2
	problems = []
	for entry in info.files:
		path = os.path.join(info.path, entry.get("root", "config"), entry["relative"].replace("/", os.sep))
		if not os.path.isfile(path):
			problems.append(f"missing: {entry['relative']}")
		elif "size" in entry and os.path.getsize(path) != entry["size"]:
			problems.append(f"changed: {entry['relative']}")
		elif thorough and entry.get("sha256") and _sha256(path) != entry["sha256"]:
			problems.append(f"changed: {entry['relative']}")
	return problems


def deleteBackup(info: BackupInfo) -> None:
	# Hard links shared with other backups keep their data; only this backup's names go.
	shutil.rmtree(info.path, ignore_errors=True)


def pruneBackups(addonDir: str, keep: int = 10) -> int:
	"""Remove the oldest backups beyond ``keep``, never the original one. Returns how many were removed."""
	backups = [info for info in listBackups(addonDir) if not info.original]
	removed = 0
	for info in backups[keep:]:
		deleteBackup(info)
		removed += 1
	return removed


# -- restoring -----------------------------------------------------------------------------


def _unchanged(path: str, entry: dict) -> bool:
	try:
		stat = os.stat(path)
	except OSError:
		return False
	if "size" in entry and stat.st_size != entry["size"]:
		return False
	if entry.get("mtime") == stat.st_mtime_ns:
		return True
	return bool(entry.get("sha256")) and _sha256(path) == entry["sha256"]


def _putBack(source: str, destination: str, entry: dict) -> None:
	"""Copy one file back from a backup, checking it first; the old file is only replaced once the copy is complete."""
	if entry.get("sha256") and _sha256(source) != entry["sha256"]:
		raise OSError("the copy in the backup is damaged")
	folder = os.path.dirname(destination)
	os.makedirs(folder, exist_ok=True)
	handle, temporary = tempfile.mkstemp(prefix=".jawsMigrator-restore-", dir=folder)
	os.close(handle)
	try:
		shutil.copy2(source, temporary)
		os.replace(temporary, destination)
	except BaseException:
		try:
			os.remove(temporary)
		except OSError:
			pass
		raise


def _removeExtras(root: str, rootName: str, files: tuple, patterns: tuple, folders: tuple, wanted: set, failed: list) -> list:
	"""Remove files a migration may have created in ``root`` that the backup does not have."""
	candidates = []
	for name in files:
		if os.path.isfile(os.path.join(root, name)):
			candidates.append(name)
	if patterns:
		try:
			names = os.listdir(root)
		except OSError:
			names = []
		for name in names:
			if any(fnmatch.fnmatchcase(name.lower(), pattern.lower()) for pattern in patterns) and os.path.isfile(os.path.join(root, name)):
				candidates.append(name)
	for folderName in folders:
		for current, _dirs, names in os.walk(os.path.join(root, folderName)):
			for name in names:
				candidates.append(os.path.relpath(os.path.join(current, name), root))
	removed = []
	for relative in candidates:
		if _key(rootName, relative) in wanted:
			continue
		try:
			os.remove(os.path.join(root, relative))
			removed.append(relative.replace(os.sep, "/"))
		except OSError as error:
			failed.append(f"{relative}: {error}")
	for folderName in folders:
		folder = os.path.join(root, folderName)
		keepFolder = any(key.startswith(f"{rootName}:{folderName.lower()}/") for key in wanted)
		for current, _dirs, _names in os.walk(folder, topdown=False):
			try:
				if not os.listdir(current) and (current != folder or not keepFolder):
					os.rmdir(current)
			except OSError:
				pass
	return removed


def restoreBackup(info: BackupInfo, configDir: str, addonDir: str, addons: "AddonManager | None" = None) -> RestoreResult:
	"""Put a backup back: files, and add-ons too when ``addons`` is given."""
	safety.checkWritable(configDir)
	safety.checkWritable(addonDir)
	problems = verifyBackup(info)
	if problems:
		raise OSError("The backup is incomplete: " + "; ".join(problems[:5]))
	result = RestoreResult()
	if info.version < 2:
		result.restored = _restoreVersion1(info, configDir, addonDir)
		return result
	patterns = _skipPatterns(configDir, addonDir)
	stateFiles = {name.lower() for name in ADDON_STATE_FILES}
	for entry in info.files:
		root = entry.get("root", "config")
		relative = entry["relative"]
		lowered = relative.lower()
		if root == "config":
			# Add-ons and NVDA's record of them go back through NVDA's add-on handling (restoreAddons).
			if lowered.split("/", 1)[0] == ADDONS_FOLDER or lowered in stateFiles or _isSkipped(relative, patterns):
				continue
			target = configDir
		else:
			target = addonDir
		destination = os.path.join(target, relative.replace("/", os.sep))
		if _unchanged(destination, entry):
			continue
		try:
			_putBack(os.path.join(info.path, root, relative.replace("/", os.sep)), destination, entry)
			result.restored.append(relative)
		except OSError as error:
			result.failed.append(f"{relative}: {error}")
	wanted = {_key(entry.get("root", "config"), entry["relative"]) for entry in info.files}
	result.removed.extend(_removeExtras(configDir, "config", CONFIG_FILES, CONFIG_PATTERNS, CONFIG_FOLDERS, wanted, result.failed))
	result.removed.extend(_removeExtras(addonDir, "addon", ADDON_FILES, (), ADDON_FOLDERS, wanted, result.failed))
	if addons is not None:
		restoreAddons(info, addons, result)
	return result


def _restoreVersion1(info: BackupInfo, configDir: str, addonDir: str) -> list[str]:
	"""Backups of version 1.0 of the assistant: NVDA's settings only."""
	done = []
	roots = {"config": configDir, "addon": addonDir}
	backupRoots = {"config": os.path.join(info.path, "config"), "addon": os.path.join(info.path, "addon")}
	folders = {"config": CONFIG_FOLDERS, "addon": ADDON_FOLDERS}
	for rootName, targetRoot in roots.items():
		entries = [entry for entry in info.files if entry.get("root", "config") == rootName]
		for folderName in folders[rootName]:
			folderEntries = [e for e in entries if e["relative"].replace("\\", "/").split("/", 1)[0].lower() == folderName.lower()]
			if folderEntries:
				_mirrorFolder(backupRoots[rootName], os.path.join(targetRoot, folderName), folderEntries)
				done.append(f"{folderName}: {len(folderEntries)} files")
		for entry in entries:
			first = entry["relative"].replace("\\", "/").split("/", 1)[0].lower()
			if first in (f.lower() for f in folders[rootName]):
				continue
			source = os.path.join(backupRoots[rootName], entry["relative"].replace("/", os.sep))
			destination = os.path.join(targetRoot, entry["relative"].replace("/", os.sep))
			_copy(source, destination)
			done.append(entry["relative"])
	for entry in info.absent:
		target = os.path.join(roots.get(entry.get("root", "config"), configDir), entry["relative"])
		if entry.get("folder"):
			if os.path.isdir(target):
				shutil.rmtree(target, ignore_errors=True)
				done.append(f"removed {entry['relative']}")
		elif os.path.isfile(target):
			os.remove(target)
			done.append(f"removed {entry['relative']}")
	return done


def _mirrorFolder(backupRoot: str, target: str, entries: list) -> None:
	"""Make ``target`` hold exactly the backed-up files (backups of version 1)."""
	wanted = {entry["relative"].replace("/", os.sep).lower() for entry in entries}
	if os.path.isdir(target):
		for current, _dirs, files in os.walk(target, topdown=False):
			for name in files:
				path = os.path.join(current, name)
				relative = os.path.relpath(path, os.path.dirname(target)).lower()
				if relative not in wanted:
					try:
						os.remove(path)
					except OSError:
						pass
			try:
				if current != target and not os.listdir(current):
					os.rmdir(current)
			except OSError:
				pass
	for entry in entries:
		source = os.path.join(backupRoot, entry["relative"].replace("/", os.sep))
		destination = os.path.join(os.path.dirname(target), entry["relative"].replace("/", os.sep))
		_copy(source, destination)


# -- add-ons -----------------------------------------------------------------------------------


class AddonManager:
	"""Installs, removes, enables and disables add-ons for a restore. NVDA finishes the changes when it restarts.

	``nvdaApply.NvdaAddonManager`` does this through NVDA's own add-on handling while NVDA runs;
	``FileAddonManager`` works on the files alone, for when NVDA is not running.
	"""

	def installed(self) -> list[AddonRecord]:
		raise NotImplementedError

	def remove(self, name: str) -> None:
		"""Remove every copy of the add-on: installed (at restart) and waiting to be installed (now)."""
		raise NotImplementedError

	def cancelRemove(self, name: str) -> None:
		raise NotImplementedError

	def stageInstall(self, name: str, source: str, disabled: bool, overrideCompatibility: bool) -> None:
		"""Install the add-on in folder ``source`` when NVDA restarts."""
		raise NotImplementedError

	def setEnabled(self, name: str, enabled: bool) -> None:
		raise NotImplementedError

	def save(self) -> None:
		pass


class FileAddonManager(AddonManager):
	"""Works on NVDA's add-on folder and addonsState.json directly, for when NVDA is not running."""

	def __init__(self, configDir: str):
		self.configDir = configDir
		self.addonsDir = os.path.join(configDir, ADDONS_FOLDER)
		self.state = readAddonState(configDir)

	def _add(self, category: str, name: str) -> None:
		values = self.state.setdefault(category, [])
		if not _inState(self.state, category, name):
			values.append(name)

	def _discard(self, category: str, name: str) -> None:
		self.state[category] = [value for value in self.state.get(category) or [] if str(value).lower() != name.lower()]

	def _folders(self, name: str) -> list[dict]:
		return [record for record in addonRecords(self.addonsDir) if record["name"].lower() == name.lower()]

	def installed(self) -> list[AddonRecord]:
		records = []
		for record in addonRecords(self.addonsDir):
			name = record["name"]
			pendingRemove = not record["pendingInstall"] and _inState(self.state, "pendingRemovesSet", name)
			path = os.path.join(self.addonsDir, record["folder"])
			records.append(AddonRecord(name, record["version"], path, record["pendingInstall"], pendingRemove, _disabledIn(self.state, name)))
		return records

	def remove(self, name: str) -> None:
		for record in self._folders(name):
			if record["pendingInstall"]:
				shutil.rmtree(os.path.join(self.addonsDir, record["folder"]))
				self._discard("pendingInstallsSet", name)
			else:
				self._add("pendingRemovesSet", name)
				self._discard("pendingDisableSet", name)

	def cancelRemove(self, name: str) -> None:
		self._discard("pendingRemovesSet", name)

	def stageInstall(self, name: str, source: str, disabled: bool, overrideCompatibility: bool) -> None:
		target = safety.checkWritable(os.path.join(self.addonsDir, name + PENDING_INSTALL_SUFFIX))
		if os.path.isdir(target):
			shutil.rmtree(target)
		shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
		self._add("pendingInstallsSet", name)
		if disabled:
			self._add("disabledAddons", name)
		if overrideCompatibility:
			self._add("PENDING_OVERRIDE_COMPATIBILITY", name)

	def setEnabled(self, name: str, enabled: bool) -> None:
		if enabled:
			if _inState(self.state, "pendingDisableSet", name):
				self._discard("pendingDisableSet", name)
			else:
				self._add("pendingEnableSet", name)
		elif _inState(self.state, "pendingEnableSet", name):
			self._discard("pendingEnableSet", name)
		elif not _inState(self.state, "disabledAddons", name):
			self._add("pendingDisableSet", name)

	def save(self) -> None:
		path = safety.checkWritable(os.path.join(self.configDir, ADDON_STATE_FILES[0]))
		handle, temporary = tempfile.mkstemp(prefix=".addonsState-", dir=self.configDir)
		with os.fdopen(handle, "w", encoding="utf-8") as stream:
			json.dump(self.state, stream)
		os.replace(temporary, path)


def backedUpAddons(info: BackupInfo) -> dict:
	"""``{name, lower case: record}``: the add-ons the backup had, as NVDA would have them after restarting."""
	result = {}
	for record in info.addons:
		name = str(record.get("name") or "")
		key = name.lower()
		if not name or key == SELF_ADDON.lower():
			continue
		if record.get("pendingInstall"):
			# The version NVDA was about to install wins over the installed one.
			result[key] = record
		elif key not in result and not _inState(info.addonState, "pendingRemovesSet", name):
			result[key] = record
	return result


def _currentAddons(installed: list[AddonRecord]) -> dict:
	result = {}
	for record in installed:
		key = record.name.lower()
		if key == SELF_ADDON.lower():
			continue
		if record.pendingInstall or key not in result:
			result[key] = record
	return result


def planAddonRestore(info: BackupInfo, installed: list[AddonRecord]) -> list[AddonAction]:
	"""What restoring ``info`` does to each add-on, for telling the user before restoring."""
	if info.version < 2:
		return []
	wanted = backedUpAddons(info)
	current = _currentAddons(installed)
	actions = []
	for key, record in sorted(current.items()):
		if key not in wanted and not record.pendingRemove:
			actions.append(AddonAction(record.name, REMOVE, f"{record.name} {record.version} is removed; it was not installed when the backup was made"))
	for key, backed in sorted(wanted.items()):
		name = str(backed["name"])
		version = str(backed.get("version") or "")
		record = current.get(key)
		disabled = _disabledIn(info.addonState, name)
		if record is None or record.pendingRemove and record.version != version:
			actions.append(AddonAction(name, REINSTALL, f"{name} {version} is put back from the backup" + (", disabled as it was" if disabled else "")))
		elif record.version != version:
			actions.append(AddonAction(name, REINSTALL, f"{name} goes back from version {record.version} to {version}, from the backup"))
		else:
			if record.pendingRemove:
				actions.append(AddonAction(name, KEEP, f"{name} {version} is kept instead of being removed"))
			if disabled != record.disabled:
				actions.append(AddonAction(name, DISABLE if disabled else ENABLE, f"{name} {version} is {'disabled' if disabled else 'enabled'} again, as it was"))
	return actions


def _checkAddonFolder(info: BackupInfo, folder: str) -> None:
	prefix = f"{ADDONS_FOLDER}/{folder}/".lower()
	for entry in info.files:
		if entry.get("root", "config") == "config" and entry["relative"].lower().startswith(prefix) and entry.get("sha256"):
			path = os.path.join(info.path, "config", entry["relative"].replace("/", os.sep))
			if _sha256(path) != entry["sha256"]:
				raise OSError(f"the backup's copy of {folder} is damaged")


def restoreAddons(info: BackupInfo, manager: AddonManager, result: RestoreResult) -> None:
	"""Put the add-ons back as they were, through ``manager``. The changes finish when NVDA restarts."""
	if info.version < 2:
		return
	installed = manager.installed()
	actions = planAddonRestore(info, installed)
	backedUp = backedUpAddons(info)
	for action in actions:
		try:
			if action.kind == REMOVE:
				manager.remove(action.name)
			elif action.kind == REINSTALL:
				record = backedUp[action.name.lower()]
				_checkAddonFolder(info, record["folder"])
				# Any other version goes, installed or waiting to be installed.
				manager.remove(action.name)
				source = os.path.join(info.path, "config", ADDONS_FOLDER, record["folder"])
				manager.stageInstall(action.name, source, _disabledIn(info.addonState, action.name), _compatibilityOverridden(info.addonState, action.name))
			elif action.kind == KEEP:
				manager.cancelRemove(action.name)
			elif action.kind in (ENABLE, DISABLE):
				manager.setEnabled(action.name, action.kind == ENABLE)
			result.addonActions.append(action)
		except Exception as error:
			result.failed.append(f"{action.name}: {error}")
	# Settings and data that kept add-ons store in their own folders.
	reinstalled = {action.name.lower() for action in actions if action.kind == REINSTALL}
	current = _currentAddons(installed)
	for key, backed in backedUp.items():
		record = current.get(key)
		if key in reinstalled or record is None or record.version != backed.get("version", ""):
			continue
		prefix = f"{ADDONS_FOLDER}/{backed['folder']}/".lower()
		for entry in info.files:
			if entry.get("root", "config") != "config" or not entry["relative"].lower().startswith(prefix):
				continue
			inside = entry["relative"][len(prefix) :]
			destination = os.path.join(record.path, inside.replace("/", os.sep))
			if _unchanged(destination, entry):
				continue
			try:
				_putBack(os.path.join(info.path, "config", entry["relative"].replace("/", os.sep)), destination, entry)
				result.restored.append(entry["relative"])
			except OSError as error:
				result.failed.append(f"{entry['relative']}: {error}")
	manager.save()
