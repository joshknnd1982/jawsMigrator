# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""JAWS's layered keystroke sound, when NVDA+Shift+J starts the assistant's layer of commands.

When the first key of a JAWS layered keystroke, such as Insert+Space, starts a layer, JAWS plays a
sound. Default.jcf names it: ``[options] KeyLayerSound``, the "sound played when a layer is activated
by pressing the initial key in a key layer sequence". It is KeyLayerSound.wav unless the user chose
another, and JAWS finds it in the user's sounds folder, then in the shared one; an empty option
means no sound. NVDA+Shift+J starts the assistant's own layer the same way, so it plays that sound.

The sound comes from the JAWS the user migrated from, or else the newest JAWS on the computer. It is
looked up the first time the layer starts after NVDA starts, and copied into the assistant's own
folder (``jawsMigrator\\sounds``), so it keeps playing after JAWS is uninstalled. JAWS's file is only
read. Where JAWS plays no layer sound, or none is found, the layer beeps as before.
"""

from __future__ import annotations

# Only modules NVDA's own Python has (its library.zip): it has no filecmp, for one (see tests/test_nvda_runtime).
import os
import shutil
import tempfile

from . import debugLog, jawsDetect, jawsFiles, nvdaEnv, safety, state

#: The Default.jcf option naming the sound.
OPTION = ("options", "KeyLayerSound")
#: JAWS's own choice, used when Default.jcf doesn't name one.
JAWS_DEFAULT = "KeyLayerSound.wav"
#: The copy in the assistant's folder: jawsMigrator\sounds\keyLayer.wav.
COPY_FOLDER = "sounds"
COPY_NAME = "keyLayer.wav"

#: The sound the layer plays, once looked up: its path, or "" to beep. None until then.
_sound: str | None = None


def soundName(jcf: jawsFiles.IniFile | None) -> str:
	"""The file JAWS plays when a key layer starts: KeyLayerSound.wav unless changed, "" when turned off."""
	value = jcf.get(*OPTION) if jcf is not None else None
	if value is None:
		return JAWS_DEFAULT
	name = value.strip().strip('"').strip()
	if name and not os.path.splitext(name)[1]:
		name += ".wav"
	return name


def _languages(jaws) -> list[str]:
	languages = []
	for language in (jaws.primaryLanguage, *jaws.settingsLanguages, "enu"):
		if language and language not in languages:
			languages.append(language)
	return languages


def _defaultJcf(jaws, language: str) -> jawsFiles.IniFile | None:
	"""JAWS's Default.jcf for ``language``, the user's settings over the shared ones, or None without either."""
	layers = []
	for folder in (jaws.sharedLanguageDir(language), jaws.userLanguageDir(language)):
		path = os.path.join(folder, "Default.jcf")
		if os.path.isfile(path):
			try:
				layers.append(jawsFiles.readIni(path, inlineComments=True))
			except OSError:
				pass
	return jawsFiles.mergeIni(*layers) if layers else None


def findSound(jaws, language: str, name: str) -> str | None:
	"""JAWS's sound file ``name``: the user's first, then the shared one, as JAWS looks for it."""
	if os.path.isabs(name):
		return name if os.path.isfile(name) else None
	for folder in (jaws.userLanguageDir(language), jaws.sharedLanguageDir(language)):
		path = os.path.join(folder, "Sounds", name)
		if os.path.isfile(path):
			return path
	return None


def jawsLayerSound(installations, migratedFrom: str = "") -> str | None:
	"""The sound JAWS plays when a key layer starts: its path, "" when JAWS plays none, or None when none is found.

	The JAWS the user migrated from (its display name, as the last migration recorded it) comes first,
	then the others, newest first.
	"""
	ordered = sorted(installations, key=lambda jaws: jaws.displayName != migratedFrom)
	for jaws in ordered:
		for language in _languages(jaws):
			jcf = _defaultJcf(jaws, language)
			if jcf is None:
				continue
			name = soundName(jcf)
			if not name:
				return ""
			path = findSound(jaws, language, name)
			if path is None and name.lower() != JAWS_DEFAULT.lower():
				path = findSound(jaws, language, JAWS_DEFAULT)
			if path is not None:
				return path
			break
	return None


def copyPath() -> str:
	return nvdaEnv.addonDataDir(COPY_FOLDER, COPY_NAME)


def sameContent(first: str, second: str) -> bool:
	"""Whether two files hold the same bytes; False when either can't be read."""
	try:
		if os.path.getsize(first) != os.path.getsize(second):
			return False
		with open(first, "rb") as one, open(second, "rb") as other:
			while True:
				block = one.read(65536)
				if block != other.read(65536):
					return False
				if not block:
					return True
	except OSError:
		return False


def keepCopy(source: str) -> str | None:
	"""Copy ``source`` into the assistant's folder, unless the copy there is the same. Returns the copy, or None."""
	if not nvdaEnv.shouldWriteToDisk():
		return None
	target = copyPath()
	temporary = None
	try:
		safety.checkWritable(target)
		if os.path.isfile(target) and sameContent(source, target):
			return target
		folder = os.path.dirname(target)
		os.makedirs(folder, exist_ok=True)
		handle, temporary = tempfile.mkstemp(prefix="keyLayer-", suffix=".tmp", dir=folder)
		os.close(handle)
		shutil.copyfile(source, temporary)
		os.replace(temporary, target)
		temporary = None
		return target
	except OSError:
		debugLog.error("could not copy JAWS's layered keystroke sound into the assistant's folder")
		return None
	finally:
		if temporary is not None:
			try:
				os.remove(temporary)
			except OSError:
				pass


def find() -> str:
	"""The sound the layer plays: a path, or "" to beep."""
	migrated = state.get("lastMigration")
	migratedFrom = str(migrated.get("jaws") or "") if isinstance(migrated, dict) else ""
	try:
		source = jawsLayerSound(jawsDetect.findJawsInstallations(), migratedFrom)
	except Exception:
		debugLog.error("could not look for JAWS's layered keystroke sound")
		source = None
	if source == "":
		debugLog.note("JAWS plays no sound when a layered keystroke starts, so NVDA+Shift+J beeps")
		return ""
	if source:
		sound = keepCopy(source) or source
		debugLog.note(f"NVDA+Shift+J plays JAWS's layered keystroke sound, {source}" + (f", copied to {sound}" if sound != source else ""))
		return sound
	copy = copyPath()
	if os.path.isfile(copy):
		debugLog.note(f"NVDA+Shift+J plays the copy of JAWS's layered keystroke sound, {copy}")
		return copy
	debugLog.note("no JAWS layered keystroke sound was found, so NVDA+Shift+J beeps")
	return ""


def play(nvwaveModule=None) -> bool:
	"""Play JAWS's layered keystroke sound. False when there is none, so the layer beeps instead."""
	global _sound
	if _sound is None:
		_sound = find()
	if not _sound or not os.path.isfile(_sound):
		return False
	try:
		if nvwaveModule is None:
			import nvwave as nvwaveModule
		nvwaveModule.playWaveFile(_sound, asynchronous=True)
	except Exception:
		debugLog.error(f"could not play JAWS's layered keystroke sound, {_sound}")
		_sound = ""
		return False
	return True


def forget() -> None:
	"""Look the sound up again next time, as after a migration or a restore."""
	global _sound
	_sound = None
