# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""An index of every JAWS setting, sound and synthesizer for one JAWS version.

The index lists each file under the user's and the shared JAWS settings and
scripts folders, which JAWS manager it belongs to, and what it contains
(sections and settings, dictionary rules, scripts, sound formats). It also
merges the files that JAWS layers (a user's ``default.jcf`` over the shared
one) so the rest of the assistant sees the settings JAWS actually uses.

Leasey's files, sections and keystrokes are marked so they can be left out.
Nothing here needs NVDA.
"""

from __future__ import annotations

import json
import os
import re
import wave
from dataclasses import dataclass, field

from . import jawsDetect, jawsFiles, managers, safety, voices

USER = "user"
SHARED = "shared"
BOTH = "both"
SOURCE_LABELS = {USER: "your settings only", SHARED: "shared settings only", BOTH: "your settings and the shared settings"}

#: Folders under a settings language folder that JAWS fills with temporary data.
_SKIP_FOLDERS = {"transient-focus", "transient-session"}
#: Stop indexing after this many files; a JAWS installation has about 2,500.
MAX_FILES = 20000
_SCRIPT_DEFINITION = re.compile(r"(?im)^\s*script\s+([A-Za-z_]\w*)")
_FUNCTION_DEFINITION = re.compile(r"(?im)^\s*(?:void|int|string|handle|object|variant|\w+)?\s*function\s+([A-Za-z_]\w*)")


@dataclass
class IndexedFile:
	path: str
	#: Relative to its root, for example ``enu\Default.jcf``.
	relative: str
	scope: str  # USER or SHARED
	#: "settings" or "scripts"
	root: str
	language: str
	extension: str
	size: int
	managerId: str
	category: str
	leasey: bool = False
	count: int = 0
	summary: str = ""
	readable: bool = True

	@property
	def name(self) -> str:
		return os.path.basename(self.path)

	def toDict(self) -> dict:
		return {
			"path": self.path,
			"relative": self.relative,
			"scope": self.scope,
			"root": self.root,
			"language": self.language,
			"extension": self.extension,
			"size": self.size,
			"manager": self.managerId,
			"category": self.category,
			"leasey": self.leasey,
			"count": self.count,
			"summary": self.summary,
			"readable": self.readable,
		}


@dataclass
class JawsIndex:
	jaws: jawsDetect.JawsInstallation
	language: str
	leasey: jawsDetect.LeaseyInfo = field(default_factory=jawsDetect.LeaseyInfo)
	files: list = field(default_factory=list)
	errors: list = field(default_factory=list)
	otherLanguages: list = field(default_factory=list)
	truncated: bool = False
	jfwIni: jawsFiles.IniFile | None = None
	synths: list = field(default_factory=list)

	# -- lookups ---------------------------------------------------------------

	def filesFor(self, scope: str = BOTH, includeLeasey: bool = False) -> list[IndexedFile]:
		return [
			f
			for f in self.files
			if (scope == BOTH or f.scope == scope) and (includeLeasey or not f.leasey) and f.readable
		]

	def byExtension(self, extension: str, scope: str = BOTH) -> list[IndexedFile]:
		extension = extension.lower().lstrip(".")
		return [f for f in self.filesFor(scope) if f.extension == extension]

	def find(self, name: str, scope: str) -> IndexedFile | None:
		"""A file by name (case-insensitive) in the language folder or root of ``scope``.

		JAWS keeps unused reference copies of some files (``enu\\Reference\\jfw.ini``); those are skipped.
		"""
		wanted = name.lower()
		matches = [
			f
			for f in self.filesFor(scope)
			if f.name.lower() == wanted and "reference" not in f.relative.lower().split(os.sep)[:-1]
		]
		matches.sort(key=lambda f: (f.language != self.language, f.root != "settings", len(f.relative)))
		return matches[0] if matches else None

	def layered(self, name: str, scope: str = BOTH, inlineComments: bool = True) -> jawsFiles.IniFile | None:
		"""Read ``name`` from the shared and/or user folders and layer the user's over the shared one."""
		layers = []
		for layerScope in (SHARED, USER):
			if scope not in (BOTH, layerScope):
				continue
			found = self.find(name, layerScope)
			if found is None:
				continue
			try:
				layers.append(jawsFiles.readIni(found.path, inlineComments=inlineComments))
			except OSError as error:
				self.errors.append(f"{found.path}: {error}")
		if not layers:
			return None
		return jawsFiles.mergeIni(*layers)

	def defaultJcf(self, scope: str = BOTH) -> jawsFiles.IniFile:
		return self.layered("default.jcf", scope) or jawsFiles.IniFile()

	def defaultJkm(self, scope: str = BOTH) -> jawsFiles.IniFile:
		return self.layered("default.jkm", scope, inlineComments=False) or jawsFiles.IniFile()

	def applicationJcfNames(self, scope: str = BOTH) -> list[str]:
		"""Configuration names (``Chrome``, ``WORD``...) that have a ``.jcf`` other than default."""
		names = []
		for f in self.byExtension("jcf", scope):
			if f.language not in ("", self.language):
				continue
			base = os.path.splitext(f.name)[0]
			if base.lower() == "default" or base.lower() in (n.lower() for n in names):
				continue
			names.append(base)
		return sorted(names, key=str.lower)

	def configNames(self) -> dict:
		"""JAWS's executable-to-configuration aliases (ConfigNames.ini), lower-cased both ways reversed.

		Returns ``{configuration name: [executable names]}``.
		"""
		ini = self.layered("confignames.ini", BOTH)
		result: dict[str, list[str]] = {}
		if ini is None:
			return result
		section = ini.section("ConfigNames")
		if section is None:
			return result
		for exe, configName in section.items():
			exe = exe.split(":", 1)[0].strip().lower()
			configName = configName.strip().lower()
			if exe and configName:
				result.setdefault(configName, [])
				if exe not in result[configName]:
					result[configName].append(exe)
		return result

	def voiceProfileFolders(self, scope: str = BOTH) -> list[str]:
		folders = []
		if scope in (BOTH, SHARED):
			folders.append(os.path.join(self.jaws.sharedSettingsDir, "VoiceProfiles"))
		if scope in (BOTH, USER):
			folders.append(os.path.join(self.jaws.userSettingsDir, "VoiceProfiles"))
		return folders

	def voiceProfile(self, name: str, scope: str = BOTH) -> voices.VoiceProfile | None:
		shared = voices.findVoiceProfileFiles([os.path.join(self.jaws.sharedSettingsDir, "VoiceProfiles")]).get(name.lower())
		user = voices.findVoiceProfileFiles([os.path.join(self.jaws.userSettingsDir, "VoiceProfiles")]).get(name.lower())
		if scope == USER:
			shared = None
		elif scope == SHARED:
			user = None
		if not shared and not user:
			return None
		return voices.loadVoiceProfile(name, shared, user)

	def voiceProfileNames(self, scope: str = BOTH) -> list[str]:
		found = voices.findVoiceProfileFiles(self.voiceProfileFolders(scope))
		return sorted((os.path.splitext(os.path.basename(path))[0] for path in found.values()), key=str.lower)

	def wavFiles(self, scope: str = BOTH) -> list[IndexedFile]:
		return self.byExtension("wav", scope)

	def soundFile(self, name: str, scope: str = BOTH) -> str | None:
		"""Find a JAWS sound by file name, the user's copy first, as JAWS does."""
		wanted = (name or "").strip().lower()
		if not wanted:
			return None
		if not wanted.endswith(".wav"):
			wanted += ".wav"
		candidates = [f for f in self.wavFiles(scope) if f.name.lower() == wanted]
		candidates.sort(key=lambda f: (f.scope != USER, f.language != self.language))
		return candidates[0].path if candidates else None

	def managerFiles(self, managerId: str, scope: str = BOTH) -> list[IndexedFile]:
		return [f for f in self.filesFor(scope) if f.managerId == managerId]

	# -- reports ---------------------------------------------------------------

	def summaryByManager(self, scope: str = BOTH) -> list[tuple[str, int, int]]:
		"""``(manager or category name, file count, item count)`` for everything indexed."""
		totals: dict[str, list[int]] = {}
		for f in self.filesFor(scope):
			label = managers.MANAGERS_BY_ID[f.managerId].name if f.managerId else managers.OTHER_CATEGORIES.get(f.category, f.category)
			if f.managerId == "settingsCenter" and f.category in managers.OTHER_CATEGORIES:
				label = managers.OTHER_CATEGORIES[f.category]
			total = totals.setdefault(label, [0, 0])
			total[0] += 1
			total[1] += f.count
		return sorted(((label, count, items) for label, (count, items) in totals.items()), key=lambda row: row[0].lower())

	def toDict(self) -> dict:
		return {
			"jaws": self.jaws.toDict(),
			"language": self.language,
			"otherLanguages": self.otherLanguages,
			"leasey": {"found": self.leasey.found, "evidence": self.leasey.evidence},
			"synthesizers": [
				{"slot": s.slot, "name": s.shortName, "longName": s.longName, "remoteOnly": s.remoteOnly} for s in self.synths
			],
			"files": [f.toDict() for f in self.files],
			"errors": self.errors,
			"truncated": self.truncated,
		}

	def writeJson(self, path: str) -> None:
		safety.checkWritable(path)
		os.makedirs(os.path.dirname(path), exist_ok=True)
		with open(path, "w", encoding="utf-8") as stream:
			json.dump(self.toDict(), stream, ensure_ascii=False, indent="\t")

	def asText(self, scope: str = BOTH) -> str:
		lines = [
			f"JAWS settings index for {self.jaws.displayName}, language {self.language}",
			f"Your settings folder: {self.jaws.userSettingsDir}",
			f"Shared settings folder: {self.jaws.sharedSettingsDir}",
			f"Shared scripts folder: {self.jaws.sharedScriptsDir}",
			"",
		]
		userFiles = [f for f in self.files if f.scope == USER]
		sharedFiles = [f for f in self.files if f.scope == SHARED]
		lines.append(f"{len(userFiles)} files in your settings, {len(sharedFiles)} shared files.")
		if self.leasey.found:
			lines.append(f"Leasey was found; {sum(1 for f in self.files if f.leasey)} Leasey files are left out.")
		lines.append("")
		lines.append("By manager:")
		for label, count, items in self.summaryByManager(scope):
			lines.append(f"  {label}: {count} files" + (f", {items} entries" if items else ""))
		lines.append("")
		if self.synths:
			lines.append("JAWS synthesizers:")
			for synth in self.synths:
				lines.append(f"  {synth.longName} ({synth.shortName})" + (" - remote sessions only" if synth.remoteOnly else ""))
			lines.append("")
		lines.append("Your files:")
		for f in sorted(userFiles, key=lambda f: f.relative.lower()):
			lines.append(f"  {f.relative} - {f.summary or f.category}" + (" (Leasey, ignored)" if f.leasey else ""))
		if self.errors:
			lines.append("")
			lines.append("Could not be read:")
			lines.extend(f"  {error}" for error in self.errors[:50])
		return "\n".join(lines)


# -- building the index -------------------------------------------------------------


def _summarize(entry: IndexedFile, leaseyActive: bool) -> None:
	extension = entry.extension
	try:
		if extension in ("jcf", "jkm", "vpf", "smf", "jgf", "jff", "jfd", "ini", "jsi", "sbl", "chr", "qsm"):
			ini = jawsFiles.readIni(entry.path, inlineComments=extension in ("jcf", "ini"))
			settings = ini.entryCount()
			entry.count = settings
			entry.summary = f"{len(ini.sections)} sections, {settings} entries"
			if leaseyActive and extension in ("jcf", "jkm"):
				leaseyEntries = sum(
					1
					for section in ini.sections.values()
					for key, value in section.items()
					if jawsDetect.hasLeaseyMarker(section.name) or jawsDetect.hasLeaseyMarker(key) or jawsDetect.hasLeaseyMarker(value)
				)
				if leaseyEntries:
					entry.summary += f" ({leaseyEntries} belong to Leasey and are ignored)"
		elif extension == "jdf":
			rules = jawsFiles.readJdf(entry.path)
			entry.count = len(rules)
			entry.summary = f"{len(rules)} dictionary rules"
		elif extension == "jss":
			text = jawsFiles.readText(entry.path)
			scripts = _SCRIPT_DEFINITION.findall(text)
			functions = _FUNCTION_DEFINITION.findall(text)
			entry.count = len(scripts)
			entry.summary = f"{len(scripts)} scripts, {len(functions)} functions"
		elif extension == "jsd":
			text = jawsFiles.readText(entry.path)
			documented = re.findall(r"(?m)^:(?:Script|Function)\s+(\w+)", text)
			entry.count = len(documented)
			entry.summary = f"{len(documented)} documented scripts and functions"
		elif extension == "wav":
			try:
				with wave.open(entry.path, "rb") as sound:
					entry.summary = (
						f"{sound.getframerate()} Hz, {sound.getsampwidth() * 8}-bit, "
						f"{'mono' if sound.getnchannels() == 1 else 'stereo'}, "
						f"{sound.getnframes() / float(sound.getframerate() or 1):.1f} seconds"
					)
			except Exception:
				entry.summary = "compressed WAV that NVDA cannot play directly"
			entry.count = 1
		elif extension == "json":
			with open(entry.path, encoding="utf-8-sig", errors="replace") as stream:
				data = json.load(stream)
			if isinstance(data, dict):
				items = data.get("Messages") or data.get("notifications") or data.get("Notifications")
				if isinstance(items, list):
					entry.count = len(items)
					entry.summary = f"{len(items)} items"
		else:
			entry.summary = f"{entry.size:,} bytes"
	except (OSError, ValueError) as error:
		entry.summary = f"could not be read: {error}"
		entry.readable = False


def _isLanguageFolder(name: str) -> bool:
	"""JAWS names language folders with three letters: enu, deu, fra..."""
	return len(name) == 3 and name.isalpha()


def _scan(root: str, scope: str, rootKind: str, language: str, index: JawsIndex, leaseyActive: bool) -> None:
	if not os.path.isdir(root):
		return
	for folder, dirs, files in os.walk(root, onerror=lambda error: index.errors.append(f"{error.filename}: {error.strerror}")):
		relativeFolder = os.path.relpath(folder, root)
		parts = [] if relativeFolder == "." else relativeFolder.split(os.sep)
		languageParts = [part.lower() for part in parts if _isLanguageFolder(part)]
		# Skip other languages' folders and JAWS's temporary folders.
		if languageParts and languageParts[0] != language:
			if languageParts[0] not in index.otherLanguages:
				index.otherLanguages.append(languageParts[0])
			dirs[:] = []
			continue
		dirs[:] = [d for d in dirs if d.lower() not in _SKIP_FOLDERS]
		for name in files:
			if len(index.files) >= MAX_FILES:
				index.truncated = True
				return
			path = os.path.join(folder, name)
			relative = os.path.join(*parts, name) if parts else name
			fileLanguage = languageParts[0] if languageParts else ""
			managerId, category = managers.classifyFile(relative)
			try:
				size = os.path.getsize(path)
			except OSError:
				size = -1
			entry = IndexedFile(
				path=path,
				relative=relative,
				scope=scope,
				root=rootKind,
				language=fileLanguage,
				extension=jawsFiles.fileExtension(name),
				size=size,
				managerId=managerId,
				category=category,
				leasey=leaseyActive and jawsDetect.hasLeaseyMarker(relative),
			)
			if size < 0:
				entry.readable = False
				entry.summary = "could not be read"
				index.errors.append(f"{path}: cannot be read")
			else:
				_summarize(entry, leaseyActive)
				if not entry.readable:
					index.errors.append(f"{path}: {entry.summary}")
			index.files.append(entry)


def buildIndex(
	jaws: jawsDetect.JawsInstallation,
	language: str | None = None,
	leasey: jawsDetect.LeaseyInfo | None = None,
) -> JawsIndex:
	"""Index one JAWS version's user and shared settings and shared scripts for one language."""
	language = (language or jaws.primaryLanguage or "enu").lower()
	leasey = leasey or jawsDetect.LeaseyInfo()
	index = JawsIndex(jaws=jaws, language=language, leasey=leasey)
	_scan(jaws.userRoot, USER, "settings", language, index, leasey.found)
	_scan(jaws.sharedSettingsDir, SHARED, "settings", language, index, leasey.found)
	_scan(jaws.sharedScriptsDir, SHARED, "scripts", language, index, leasey.found)
	# jfw.ini: the user's copy wins over the shared one when JAWS keeps one per user.
	index.jfwIni = index.layered("jfw.ini", BOTH)
	index.synths = voices.readJawsSynths(index.jfwIni)
	return index


def isLeaseyText(*texts: str) -> bool:
	return any(jawsDetect.hasLeaseyMarker(text) for text in texts)
