# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Backups of NVDA's settings, taken before a migration and restorable at any time.

A backup is a folder under ``jawsMigrator\\backups`` in NVDA's settings folder
holding copies of nvda.ini, gestures.ini, profileTriggers.ini, every
configuration profile, speech dictionary and user symbol file, ClassicSpeech's
settings and schemes, NVDA's own sound files, and the assistant's record of
replaced sounds and sleeping applications. ``backup.json`` lists what was
there, and also what was *not* there, so a restore removes files a migration
created (a new "JAWS settings" profile, for example).

Restoring first takes a backup of the current settings, so a restore can be
undone too. This module only copies files; reloading NVDA afterwards is done
by the caller in NVDA's main thread.
"""

from __future__ import annotations

import datetime
import fnmatch
import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field

from . import safety

BACKUP_FORMAT = "JAWS Migration Assistant NVDA settings backup"
BACKUP_VERSION = 1
MANIFEST = "backup.json"

#: Single files in NVDA's settings folder that are backed up.
CONFIG_FILES = ("nvda.ini", "gestures.ini", "profileTriggers.ini")
#: File name patterns in NVDA's settings folder that are backed up.
CONFIG_PATTERNS = ("symbols-*.dic",)
#: Folders in NVDA's settings folder that are mirrored on restore.
CONFIG_FOLDERS = ("profiles", "speechDicts", "ClassicSpeech")
#: The assistant's own files that describe migrated sounds and applications.
ADDON_FILES = ("state.json",)
ADDON_FOLDERS = ("sounds",)


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

	@property
	def name(self) -> str:
		return os.path.basename(self.path)

	@property
	def label(self) -> str:
		when = self.created.replace("T", " ")[:19] if self.created else self.name
		return f"{when} - {self.reason}" if self.reason else when


def _sha256(path: str) -> str:
	digest = hashlib.sha256()
	with open(path, "rb") as stream:
		for chunk in iter(lambda: stream.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _copy(source: str, destination: str) -> None:
	os.makedirs(os.path.dirname(destination), exist_ok=True)
	shutil.copy2(source, destination)


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


def createBackup(
	configDir: str,
	addonDir: str,
	wavesDir: str,
	reason: str,
	nvdaVersion: str = "",
	addonVersion: str = "",
) -> BackupInfo:
	"""Copy NVDA's settings into a new backup folder. Raises OSError when it can't."""
	folder = safety.checkWritable(_newBackupFolder(addonDir))
	os.makedirs(folder)
	info = BackupInfo(
		path=folder,
		created=datetime.datetime.now().isoformat(timespec="seconds"),
		reason=reason,
		nvdaVersion=nvdaVersion,
		addonVersion=addonVersion,
	)
	configTarget = os.path.join(folder, "config")

	def record(source: str, relative: str, base: str) -> None:
		destination = os.path.join(base, relative)
		_copy(source, destination)
		info.files.append({"relative": relative.replace(os.sep, "/"), "root": os.path.basename(base), "sha256": _sha256(destination), "size": os.path.getsize(destination)})

	for name in CONFIG_FILES:
		path = os.path.join(configDir, name)
		if os.path.isfile(path):
			record(path, name, configTarget)
		else:
			info.absent.append({"relative": name, "root": "config"})
	try:
		names = os.listdir(configDir)
	except OSError:
		names = []
	for name in names:
		if any(fnmatch.fnmatch(name.lower(), pattern.lower()) for pattern in CONFIG_PATTERNS):
			path = os.path.join(configDir, name)
			if os.path.isfile(path):
				record(path, name, configTarget)
	for folderName in CONFIG_FOLDERS:
		root = os.path.join(configDir, folderName)
		if not os.path.isdir(root):
			info.absent.append({"relative": folderName, "root": "config", "folder": True})
			continue
		for current, _dirs, files in os.walk(root):
			for name in files:
				path = os.path.join(current, name)
				record(path, os.path.relpath(path, configDir), configTarget)
	addonTarget = os.path.join(folder, "addon")
	for name in ADDON_FILES:
		path = os.path.join(addonDir, name)
		if os.path.isfile(path):
			record(path, name, addonTarget)
		else:
			info.absent.append({"relative": name, "root": "addon"})
	for folderName in ADDON_FOLDERS:
		root = os.path.join(addonDir, folderName)
		if not os.path.isdir(root):
			info.absent.append({"relative": folderName, "root": "addon", "folder": True})
			continue
		for current, _dirs, files in os.walk(root):
			for name in files:
				path = os.path.join(current, name)
				record(path, os.path.relpath(path, addonDir), addonTarget)
	# NVDA's own sounds, which the assistant never changes, kept so they can always be compared or recovered.
	if wavesDir and os.path.isdir(wavesDir):
		soundsTarget = os.path.join(folder, "nvdaSounds")
		for name in sorted(os.listdir(wavesDir)):
			path = os.path.join(wavesDir, name)
			if name.lower().endswith(".wav") and os.path.isfile(path):
				_copy(path, os.path.join(soundsTarget, name))
				info.nvdaSounds += 1
	_writeManifest(info)
	return info


def _writeManifest(info: BackupInfo) -> None:
	payload = {
		"format": BACKUP_FORMAT,
		"version": BACKUP_VERSION,
		"created": info.created,
		"reason": info.reason,
		"nvdaVersion": info.nvdaVersion,
		"addonVersion": info.addonVersion,
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


def verifyBackup(info: BackupInfo) -> list[str]:
	"""Problems with a backup's files: missing or changed since it was made."""
	problems = []
	for entry in info.files:
		path = os.path.join(info.path, entry.get("root", "config"), entry["relative"].replace("/", os.sep))
		if not os.path.isfile(path):
			problems.append(f"missing: {entry['relative']}")
		elif entry.get("sha256") and _sha256(path) != entry["sha256"]:
			problems.append(f"changed: {entry['relative']}")
	return problems


def _mirrorFolder(backupRoot: str, target: str, entries: list) -> None:
	"""Make ``target`` hold exactly the backed-up files."""
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


def restoreBackup(info: BackupInfo, configDir: str, addonDir: str) -> list[str]:
	"""Put the backed-up files back. Returns a list of what was restored or removed."""
	safety.checkWritable(configDir)
	safety.checkWritable(addonDir)
	problems = verifyBackup(info)
	if problems:
		raise OSError("The backup is incomplete: " + "; ".join(problems[:5]))
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


def deleteBackup(info: BackupInfo) -> None:
	shutil.rmtree(info.path, ignore_errors=True)


def pruneBackups(addonDir: str, keep: int = 10) -> int:
	"""Remove the oldest backups beyond ``keep``. Returns how many were removed."""
	backups = listBackups(addonDir)
	removed = 0
	for info in backups[keep:]:
		deleteBackup(info)
		removed += 1
	return removed
