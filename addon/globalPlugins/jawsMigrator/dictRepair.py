# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""One-time repairs of the speech dictionary rules earlier versions wrote.

Versions 1.0 to 1.2 made two kinds of rule that change speech JAWS never changed:

- A JAWS word with a letter or digit at only one end, such as ``St.`` or ``AN:``, became an
  "anywhere" rule, so it also changed the inside of other words: "first." was read
  "firStreet", and "Plan:" "Placcount number". JAWS matches whole words, so the rule is
  rewritten as a regular expression with a word boundary at the letter or digit end, as
  version 1.3 writes it.
- A JAWS word made only of asterisks became an empty regular expression, which matches
  between every two characters and garbles all speech. It is rewritten as the asterisks
  themselves, which its comment still names, or dropped when the comment doesn't.

Versions 1.0 to 1.20 put the rules of JAWS's dictionaries for single applications, such as
Theophilos.jdf or Excel.jdf, into NVDA's default dictionary (or, for one synthesizer, the voice
dictionary), where they change speech in every program. JAWS uses them only in their application:
Theophilos's "Job" -> "jobe" made a tester hear "jobe" on a web page (issue 13). Such a rule, whose
comment names the JAWS file it came from ("From JAWS shared Theophilos.jdf, line 40"), is moved into
that application's own dictionary, which NVDA uses only in its programs (see appDicts). The programs
come from JAWS's ConfigNames.ini, as for a migration. A rule for an application NVDA can't know as a
program is kept in a file of its own that names no program, so it changes nothing, and the user can
still add one.

Only rules the assistant wrote are touched: their comment says ``From JAWS``. Everything else
in the dictionary files, the user's own rules included, stays exactly as it is. NVDA's
settings are backed up before the repair (see repairOnce).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from . import appDicts, dictMap, safety

#: Bumped when a new repair is needed; kept in state.json as "dictionariesRepaired".
#: 1: the rules of versions 1.0 to 1.2; 2: the rules of JAWS application dictionaries, moved out of the default dictionary.
REPAIR_VERSION = 2
STATE_KEY = "dictionariesRepaired"
MARKER = "From JAWS "


@dataclass
class DictRepairResult:
	files: list = field(default_factory=list)
	rewritten: int = 0
	failed: list = field(default_factory=list)
	#: Rules moved into dictionaries for single programs, by JAWS configuration.
	moved: dict = field(default_factory=dict)
	#: The files for single programs written.
	applicationFiles: list = field(default_factory=list)

	@property
	def movedCount(self) -> int:
		return sum(self.moved.values())


def dictionaryFiles(configDir: str) -> list[str]:
	"""NVDA's default dictionary and every voice dictionary in NVDA's settings folder."""
	folder = os.path.join(configDir, "speechDicts")
	files = []
	default = os.path.join(folder, "default.dic")
	if os.path.isfile(default):
		files.append(default)
	voices = os.path.join(folder, "voiceDicts.v1")
	for root, _dirs, names in os.walk(voices):
		files.extend(os.path.join(root, name) for name in sorted(names) if name.lower().endswith(".dic"))
	return files


def repairedEntry(pattern: str, replacement: str, entryType: int, comment: str = "") -> tuple[str, str, int, str] | None:
	"""``(pattern, replacement, type, why)`` for a rule an earlier version wrote wrongly, or None when it is right.

	``pattern`` and ``replacement`` are as NVDA reads them (``\\#`` already turned into ``#``). A type
	of -1 means the rule is dropped.
	"""
	if entryType == dictMap.TYPE_REGEXP and pattern == "":
		# Asterisks alone were taken for a wildcard with no word. The rule was the asterisks
		# themselves; the comment written with it still names them.
		why = "an empty pattern, which changed the text between every two characters"
		match = re.search(r"\(root word (\*+)\)", comment)
		if match is None:
			return "", "", -1, why
		return match.group(1), replacement.replace("\\\\", "\\"), dictMap.TYPE_ANYWHERE, why
	if entryType != dictMap.TYPE_ANYWHERE or not pattern:
		return None
	first, last = dictMap._isWordCharacter(pattern[0]), dictMap._isWordCharacter(pattern[-1])
	if first == last:
		return None
	newPattern = dictMap._wordBoundary(pattern[0]) + re.escape(pattern) + dictMap._wordBoundary(pattern[-1])
	return newPattern, replacement.replace("\\", "\\\\"), dictMap.TYPE_REGEXP, f"whole word {pattern}"


def _escape(text: str) -> str:
	return text.replace("#", r"\#")


def repairText(text: str) -> tuple[str, int]:
	"""The contents of a ``.dic`` file with the assistant's wrong rules repaired, and how many were changed.

	Rules are read the way NVDA reads them: comment lines (``#``) before a rule belong to it, and a
	blank line ends a comment.
	"""
	output: list[str] = []
	comments: list[str] = []
	changed = 0
	for rawLine in text.splitlines(keepends=True):
		line = rawLine.rstrip("\r\n")
		if not line.strip():
			output.extend(comments)
			comments = []
			output.append(rawLine)
			continue
		if line.startswith("#"):
			comments.append(rawLine)
			continue
		fields = line.split("\t")
		comment = " ".join(item.rstrip("\r\n")[1:] for item in comments)
		repair = None
		if len(fields) == 4 and MARKER in comment:
			try:
				entryType = int(fields[3])
			except ValueError:
				entryType = None
			if entryType is not None:
				repair = repairedEntry(fields[0].replace(r"\#", "#"), fields[1].replace(r"\#", "#"), entryType, comment)
		if repair is None:
			output.extend(comments)
			output.append(rawLine)
		else:
			newPattern, newReplacement, newType, why = repair
			changed += 1
			if newType >= 0:
				ending = "\r\n" if rawLine.endswith("\r\n") else "\n"
				output.extend(comments[:-1])
				lastComment = comments[-1].rstrip("\r\n") if comments else "#" + MARKER.strip()
				output.append(f"{lastComment} (repaired by the JAWS Migration Assistant: {why}){ending}")
				output.append(f"{_escape(newPattern)}\t{_escape(newReplacement)}\t{fields[2]}\t{newType}{ending}")
			# A rule with nothing to keep is dropped with its comment.
		comments = []
	output.extend(comments)
	return "".join(output), changed


def splitApplicationRules(text: str) -> tuple[str, dict]:
	"""The contents of a ``.dic`` file without the rules from JAWS application dictionaries, and those rules.

	Returns ``(text, {configuration: [dictMap.DictEntry]})``. A rule goes with the comment lines before it, as NVDA
	reads them; the rest of the file stays exactly as it is.
	"""
	output: list[str] = []
	comments: list[str] = []
	moved: dict = {}
	for rawLine in text.splitlines(keepends=True):
		line = rawLine.rstrip("\r\n")
		if not line.strip():
			output.extend(comments)
			comments = []
			output.append(rawLine)
			continue
		if line.startswith("#"):
			comments.append(rawLine)
			continue
		fields = line.split("\t")
		comment = " ".join(item.rstrip("\r\n")[1:] for item in comments)
		entry = None
		if len(fields) == 4 and appDicts.isApplicationRule(comment):
			try:
				entry = dictMap.DictEntry(
					pattern=fields[0].replace(r"\#", "#"),
					replacement=fields[1].replace(r"\#", "#"),
					caseSensitive=bool(int(fields[2])),
					type=int(fields[3]),
					comment=comment,
				)
			except ValueError:
				entry = None
		if entry is None:
			output.extend(comments)
			output.append(rawLine)
		else:
			moved.setdefault(appDicts.sourceConfiguration(comment), []).append(entry)
		comments = []
	output.extend(comments)
	return "".join(output), moved


def _read(path: str) -> str:
	with open(path, encoding="utf_8_sig", errors="replace", newline="") as stream:
		return stream.read()


def applicationConfigurations(configDir: str) -> list[str]:
	"""The JAWS configurations whose application dictionary rules are in NVDA's default or voice dictionaries."""
	names: dict = {}
	for path in dictionaryFiles(configDir):
		try:
			for name in splitApplicationRules(_read(path))[1]:
				names.setdefault(name.lower(), name)
		except OSError:
			continue
	return sorted(names.values(), key=str.lower)


def needsRepair(configDir: str) -> bool:
	for path in dictionaryFiles(configDir):
		try:
			text = _read(path)
		except OSError:
			continue
		if repairText(text)[1] or splitApplicationRules(text)[1]:
			return True
	return False


class _NoConfigNames:
	"""A JAWS index without ConfigNames.ini, for when JAWS's own can't be read."""

	def configNames(self) -> dict:
		return {}


def programsFor(configNames: list) -> dict:
	"""``{configuration: [program, ...]}``, as a migration finds them: from JAWS's ConfigNames.ini (the newest JAWS
	that maps the configuration), or else the configuration's own name when a program can have it. Reads JAWS's
	files, so it runs in the background."""
	from . import jawsDetect, jawsIndex, migrator

	result: dict = {}
	indexes = []
	try:
		installations = jawsDetect.findJawsInstallations()
	except Exception:
		installations = []
	for jaws in installations:
		for language in getattr(jaws, "settingsLanguages", None) or [getattr(jaws, "primaryLanguage", "") or "enu"]:
			try:
				indexes.append(jawsIndex.buildIndex(jaws, language))
			except Exception:
				continue
	for name in configNames:
		programs = None
		for index in indexes:
			try:
				if name.lower() in index.configNames():
					programs = migrator.appExecutables(index, name)[0]
					break
			except Exception:
				continue
		if programs is None:
			programs = migrator.appExecutables(_NoConfigNames(), name)[0]
		result[name] = programs
	return result


def reloadLiveDictionaries(paths: list) -> None:
	"""Have NVDA read the repaired files again, so it neither speaks with nor saves back the old rules."""
	from . import nvdaApply

	wanted = {os.path.normcase(os.path.abspath(path)) for path in paths}
	for kind in ("default", "voice"):
		dictionary = nvdaApply.liveDictionary(kind)
		fileName = getattr(dictionary, "fileName", None)
		if dictionary is None or not fileName or os.path.normcase(os.path.abspath(fileName)) not in wanted:
			continue
		try:
			dictionary.load(fileName)
		except Exception:
			from . import debugLog

			debugLog.error(f"NVDA could not reload {fileName}")


def repairOnce(announce, done=None) -> None:
	"""Once, after updating from versions 1.0 to 1.20: repair their dictionary rules, after a backup.

	Main thread; the backup runs in the background. ``announce(message)`` tells the user, and
	``done()`` is called on the main thread when the repair is over, whether or not it did anything.
	"""
	from . import migrator

	finished = migrator.callOnce(done)
	started = False
	try:
		started = _startRepair(announce, finished)
	finally:
		if not started:
			finished()


def _startRepair(announce, finished) -> bool:
	import threading

	from . import debugLog, nvdaEnv, state

	if state.get(STATE_KEY) == REPAIR_VERSION or not nvdaEnv.shouldWriteToDisk():
		return False
	configDir = nvdaEnv.configDir()
	if not needsRepair(configDir):
		state.set(STATE_KEY, REPAIR_VERSION)
		return False
	debugLog.section("Repairing the dictionary rules of an earlier migration")

	def finish(outcome, programs):
		try:
			_finish(outcome, programs)
		finally:
			finished()

	def _finish(outcome, programs):
		if isinstance(outcome, Exception):
			debugLog.note(f"the backup failed, so nothing was repaired; it is tried again next time NVDA starts: {outcome}")
			return
		result = repairDictionaries(configDir, debugLog.note, programs)
		reloadLiveDictionaries(result.files)
		appDicts.reload()
		if result.failed:
			debugLog.note(f"some dictionaries could not be repaired; tried again next time NVDA starts: {result.failed}")
			return
		state.set(STATE_KEY, REPAIR_VERSION)
		debugLog.note(
			f"repaired {result.rewritten} rules in {result.files}; moved {result.moved} into {result.applicationFiles}; "
			f"backup {getattr(outcome, 'path', '')}",
		)
		messages = []
		if result.rewritten:
			messages.append(
				f"JAWS Migration Assistant repaired {result.rewritten} speech dictionary rules from your earlier JAWS migration, "
				"so they no longer change the middle of other words.",
			)
		if result.movedCount:
			messages.append(movedMessage(result))
		if messages:
			announce(" ".join(messages))

	def work():
		from . import migrator

		programs = None
		try:
			outcome = migrator._backupFirst("Before repairing the dictionary rules of an earlier migration")
		except Exception as error:
			debugLog.error("the backup before the dictionary repair failed")
			outcome = error
		if not isinstance(outcome, Exception):
			try:
				# JAWS's ConfigNames.ini says which programs each application dictionary is for; reading JAWS's
				# files takes a moment, so it is done here, not on NVDA's main thread.
				programs = programsFor(applicationConfigurations(configDir))
			except Exception:
				debugLog.error("could not find the programs of JAWS's application dictionaries")
		import wx

		wx.CallAfter(finish, outcome, programs)

	threading.Thread(target=work, name="jawsMigratorDictRepair", daemon=True).start()
	return True


def repairDictionaries(configDir: str, log=None, programs: dict | None = None) -> DictRepairResult:
	"""Repair the assistant's rules in every NVDA dictionary file, and move the rules of JAWS application dictionaries
	into dictionaries for their programs. Writes only files that change.

	``programs`` is ``{configuration: [program, ...]}`` (see programsFor); found here when not given. The rules are
	written to their program's file before they are taken out of NVDA's, so a file that can't be written loses
	nothing, and the repair is tried again next time NVDA starts.
	"""
	result = DictRepairResult()
	say = log or (lambda message: None)
	known = {name.lower(): value for name, value in (programs or {}).items()}
	for path in dictionaryFiles(configDir):
		try:
			text = _read(path)
			repaired, changed = repairText(text)
			remaining, moved = splitApplicationRules(repaired)
			if not changed and not moved:
				continue
			for configName, entries in moved.items():
				if configName.lower() not in known:
					known.update({name.lower(): value for name, value in programsFor([configName]).items()})
				where = known.get(configName.lower()) or []
				appDicts.writeRules(configName, where, entries, configDir)
				filePath = appDicts.path(configName, configDir)
				if filePath not in result.applicationFiles:
					result.applicationFiles.append(filePath)
				say(f"moving {len(entries)} rules from JAWS's {configName} dictionary out of {path} into {filePath}, used only in {', '.join(where) or 'no program'}")
			safety.checkWritable(path)
			temporary = path + ".jawsMigrator.tmp"
			with open(temporary, "w", encoding="utf_8_sig", newline="") as stream:
				stream.write(remaining)
			os.replace(temporary, path)
			result.files.append(path)
			result.rewritten += changed
			for configName, entries in moved.items():
				result.moved[configName] = result.moved.get(configName, 0) + len(entries)
			if changed:
				say(f"repaired {changed} dictionary rules in {path}")
		except OSError as error:
			result.failed.append(f"{path}: {error}")
			say(f"could not repair {path}: {error}")
	return result


def movedMessage(result: DictRepairResult) -> str:
	"""What the user is told about the rules moved into dictionaries for single programs, or ""."""
	if not result.movedCount:
		return ""
	names = [name for name, _count in sorted(result.moved.items(), key=lambda item: (-item[1], item[0].lower()))]
	if len(names) == 1:
		which = names[0]
	elif len(names) <= 3:
		which = ", ".join(names[:-1]) + " and " + names[-1]
	else:
		which = ", ".join(names[:3]) + f" and {len(names) - 3} more"
	return (
		f"JAWS Migration Assistant moved {result.movedCount} speech dictionary rules from JAWS's dictionaries for {which} "
		"out of NVDA's default dictionary. As in JAWS, they now change speech only in those programs."
	)
