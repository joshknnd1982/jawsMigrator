# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""A one-time repair of the symbols versions 1.0 to 1.9 wrote for spaces and line breaks.

Those versions gave JAWS's name for a space or a line break the level of JAWS's flags, so NVDA
said the name wherever the character was in the text. JAWS's files name the no-break space
"non breaking space" at the Most level, and web pages put one between words everywhere: a
tester's NVDA said "non breaking space" all through a news site. The vertical tab, a line break
in Word and in HTML e-mail, was "vertical tab". Version 1.10 writes these names for reading
characters only (see symbolMap.isSpaceOrLineBreak), as NVDA itself says spaces and line breaks,
and this gives the lines those versions wrote the same level.

Only lines the assistant wrote are touched: a line for a space or a line break, at a level at
which NVDA says it within text, with a name JAWS gives that character, in JAWS 2026's own symbol
files or in the JAWS symbol files on this computer (yours included). The name stays, for reading
characters. Everything else in NVDA's symbol files, the user's own symbols included, stays
exactly as it is. NVDA's settings are backed up before the repair (see repairOnce).
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field

from . import debugLog, nvdaEnv, safety, symbolMap

#: Bumped when a new repair is needed; kept in state.json as "symbolsRepaired".
REPAIR_VERSION = 1
STATE_KEY = "symbolsRepaired"
#: The names JAWS 2026's own symbol files give spaces and line breaks, in all their languages. They
#: identify the assistant's lines when JAWS's files are gone from the computer.
JAWS_NAMES = {
	"\N{NO-BREAK SPACE}": (
		"non breaking space",
		"espace insécable",
		"espacio de no separación",
		"geschütztes leerzeichen",
		"murdmatu tühik",
		"spacja nierozdzielająca",
		"spazio continuo",
	),
	"\v": ("vertical tab", "pionowy tab", "tabulación vertical", "tabulation verticale", "vertikalni tabulator", "vertikāla cilne"),
	"\r": ("koniec akapitu",),
}


@dataclass
class SymbolRepairResult:
	files: list = field(default_factory=list)
	#: ``(file name, character, name, old level)`` of each line now read for characters only.
	lines: list = field(default_factory=list)
	failed: list = field(default_factory=list)


def symbolFiles(configDir: str) -> list[str]:
	"""NVDA's symbol files for each language: ``symbols-<locale>.dic`` in NVDA's settings folder."""
	try:
		names = sorted(os.listdir(configDir))
	except OSError:
		return []
	return [
		os.path.join(configDir, name)
		for name in names
		if name.lower().startswith("symbols-") and name.lower().endswith(".dic") and os.path.isfile(os.path.join(configDir, name))
	]


def _jawsSymbolFiles(jaws) -> list[str]:
	"""Every symbol file (``.sbl``) of one JAWS version: the shared ones and the user's, in every language."""
	found = []
	for root in (jaws.sharedSettingsDir, jaws.userSettingsDir):
		for folder, _dirs, names in os.walk(root):
			found.extend(os.path.join(folder, name) for name in sorted(names) if name.lower().endswith(".sbl"))
	return found


def jawsNames(installations=None) -> dict:
	"""``{character: names}``, in lower case, that JAWS gives spaces and line breaks.

	JAWS 2026's own names, and those in the symbol files of every JAWS version on this computer
	(``installations``, or every one found), whether JAWS is still installed or only its settings are left.
	"""
	names = {character: {name.casefold() for name in known} for character, known in JAWS_NAMES.items()}
	if installations is None:
		from . import jawsDetect

		try:
			installations = jawsDetect.findJawsInstallations()
		except Exception:
			debugLog.error("the JAWS versions on this computer could not be found, so only JAWS 2026's own names are known")
			installations = []
	for jaws in installations:
		for path in _jawsSymbolFiles(jaws):
			try:
				ini = symbolMap.readSymbolFile(path)
			except OSError:
				continue
			for sectionName in ini.sectionNames():
				for character, symbol in symbolMap.parseSymbols(ini.section(sectionName)).items():
					if symbolMap.isSpaceOrLineBreak(character) and symbol.spokenText:
						names.setdefault(character, set()).add(symbol.spokenText.casefold())
	return names


def repairText(text: str, names: dict | None) -> tuple[str, list]:
	"""The text of a symbols file with the assistant's lines for spaces and line breaks read for characters
	only, and the ``(character, name, old level)`` of each line changed.

	``names`` is ``{character: names JAWS gives it, in lower case}``; None takes any name, to find out
	whether there can be anything to repair. Lines are read the way NVDA reads them
	(characterProcessing.SpeechSymbols.load): after ``symbols:``, a line's fields are the symbol, its
	name, its level and whether the symbol is kept, maybe with a ``# display name`` last. Lines
	starting with ``#`` are comments.
	"""
	output: list[str] = []
	changed = []
	section = None
	for rawLine in text.splitlines(keepends=True):
		line = rawLine.rstrip("\r\n")
		if line in ("complexSymbols:", "symbols:"):
			section = line
		elif section == "symbols:" and line.strip() and not line.startswith("#"):
			fields = line.split("\t")
			character = symbolMap.symbolOf(fields[0])
			if (
				len(fields) >= 3
				and symbolMap.isSpaceOrLineBreak(character)
				and fields[2] in symbolMap.TEXT_LEVELS
				and fields[1].strip()
				and (names is None or fields[1].strip().casefold() in names.get(character, ()))
			):
				changed.append((character, fields[1], fields[2]))
				fields[2] = "char"
				rawLine = "\t".join(fields) + rawLine[len(line) :]
		output.append(rawLine)
	return "".join(output), changed


def _read(path: str) -> str:
	"""The text of an NVDA symbols file. Raises OSError, or ValueError when it isn't UTF-8 as NVDA writes it."""
	with open(path, encoding="utf_8_sig", newline="") as stream:
		return stream.read()


def needsRepair(configDir: str, names: dict | None = None) -> bool:
	"""Whether a symbols file has a line to repair; with ``names`` None, one that may be, whatever its name."""
	for path in symbolFiles(configDir):
		try:
			if repairText(_read(path), names)[1]:
				return True
		except (OSError, ValueError):
			# Left as it is: a file that can't be read is never written back.
			continue
	return False


def repairSymbolFiles(configDir: str, names: dict, log=None) -> SymbolRepairResult:
	"""Repair the assistant's lines in every NVDA symbols file. Writes only files that change."""
	result = SymbolRepairResult()
	say = log or (lambda message: None)
	for path in symbolFiles(configDir):
		try:
			text = _read(path)
		except (OSError, ValueError) as error:
			say(f"{path} was left as it is: it could not be read ({error})")
			continue
		repaired, changed = repairText(text, names)
		if not changed:
			continue
		try:
			safety.checkWritable(path)
			temporary = path + ".jawsMigrator.tmp"
			with open(temporary, "w", encoding="utf_8_sig", newline="") as stream:
				stream.write(repaired)
			os.replace(temporary, path)
		except OSError as error:
			result.failed.append(f"{path}: {error}")
			say(f"could not repair {path}: {error}")
			continue
		result.files.append(path)
		for character, name, level in changed:
			result.lines.append((os.path.basename(path), character, name, level))
			say(f'{os.path.basename(path)}: U+{ord(character):04X} "{name}" was at the "{level}" level; it is now said only when reading characters')
	return result


def announcement(lines: list) -> str:
	"""What the user hears after the repair, naming each name NVDA no longer says within text."""
	spoken = []
	for _fileName, _character, name, _level in lines:
		if name.casefold() not in (known.casefold() for known in spoken):
			spoken.append(name)
	said = " or ".join(f'"{name}"' for name in spoken)
	them = "it wherever it was" if len(spoken) == 1 else "them wherever they were"
	return (
		f"JAWS Migration Assistant: NVDA no longer says {said} as it reads, only when you read by character. "
		f"The earlier migration had made NVDA say {them} in the text. NVDA's settings were backed up first."
	)


def repairOnce(announce, done=None) -> None:
	"""Once, after updating from versions 1.0 to 1.9: have NVDA say JAWS's names for spaces and line breaks
	only when reading characters, after a backup.

	Main thread; JAWS's symbol files are read and the backup is made in the background. ``announce(message)``
	tells the user, and ``done()`` is called on the main thread when the repair is over, whether or not it
	did anything.
	"""
	from . import migrator

	finished = migrator.callOnce(done)
	started = False
	try:
		started = _startRepair(announce, finished)
	except Exception:
		debugLog.error("the repair of punctuation symbols failed")
	finally:
		if not started:
			finished()


def _startRepair(announce, finished) -> bool:
	from . import state

	if state.get(STATE_KEY) == REPAIR_VERSION or not nvdaEnv.shouldWriteToDisk():
		return False
	configDir = nvdaEnv.configDir()
	# Only a migration writes JAWS's symbols, and nothing is backed up unless a line may need the repair.
	if not state.get("lastMigration") or not needsRepair(configDir):
		state.set(STATE_KEY, REPAIR_VERSION)
		return False

	def work():
		from . import migrator

		try:
			names = jawsNames()
			backupInfo = None
			if needsRepair(configDir, names):
				backupInfo = migrator._backupFirst("Before repairing the punctuation symbols of an earlier migration")
			outcome = (names, backupInfo)
		except Exception as error:
			debugLog.error("the repair of punctuation symbols could not start")
			outcome = error
		import wx

		wx.CallAfter(finish, outcome)

	def finish(outcome):
		try:
			_finish(configDir, outcome, announce)
		finally:
			finished()

	threading.Thread(target=work, name="jawsMigratorSymbolRepair", daemon=True).start()
	return True


def _finish(configDir: str, outcome, announce) -> None:
	from . import nvdaApply, state

	if isinstance(outcome, Exception):
		debugLog.note(f"the punctuation symbols were not repaired; it is tried again next time NVDA starts: {outcome}")
		return
	names, backupInfo = outcome
	if backupInfo is None:
		# A space or a line break said within text, but with a name JAWS doesn't give it: the user's own.
		debugLog.note("the symbols for spaces and line breaks in NVDA's symbol files are the user's own, so they stay as they are")
		state.set(STATE_KEY, REPAIR_VERSION)
		return
	debugLog.section("Repairing the punctuation symbols of an earlier migration")
	result = repairSymbolFiles(configDir, names, debugLog.note)
	if result.files:
		nvdaApply.reloadSymbols()
	if result.failed:
		debugLog.note(f"some symbol files could not be repaired; tried again next time NVDA starts: {result.failed}")
		return
	state.set(STATE_KEY, REPAIR_VERSION)
	debugLog.note(f"repaired {len(result.lines)} symbols in {result.files}; backup {getattr(backupInfo, 'path', '')}")
	if result.lines:
		announce(announcement(result.lines))
