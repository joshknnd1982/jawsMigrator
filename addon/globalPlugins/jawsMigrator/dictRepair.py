# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""A one-time repair of the speech dictionary rules versions 1.0 to 1.2 wrote.

Those versions made two kinds of rule that change speech JAWS never changed:

- A JAWS word with a letter or digit at only one end, such as ``St.`` or ``AN:``, became an
  "anywhere" rule, so it also changed the inside of other words: "first." was read
  "firStreet", and "Plan:" "Placcount number". JAWS matches whole words, so the rule is
  rewritten as a regular expression with a word boundary at the letter or digit end, as
  version 1.3 writes it.
- A JAWS word made only of asterisks became an empty regular expression, which matches
  between every two characters and garbles all speech. It is rewritten as the asterisks
  themselves, which its comment still names, or dropped when the comment doesn't.

Only rules the assistant wrote are touched: their comment says ``From JAWS``. Everything else
in the dictionary files, the user's own rules included, stays exactly as it is. NVDA's
settings are backed up before the repair (see repairOnce).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from . import dictMap, safety

#: Bumped when a new repair is needed; kept in state.json as "dictionariesRepaired".
REPAIR_VERSION = 1
STATE_KEY = "dictionariesRepaired"
MARKER = "From JAWS "


@dataclass
class DictRepairResult:
	files: list = field(default_factory=list)
	rewritten: int = 0
	failed: list = field(default_factory=list)


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


def needsRepair(configDir: str) -> bool:
	for path in dictionaryFiles(configDir):
		try:
			with open(path, encoding="utf_8_sig", errors="replace") as stream:
				if repairText(stream.read())[1]:
					return True
		except OSError:
			continue
	return False


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
	"""Once, after updating from versions 1.0 to 1.2: repair their dictionary rules, after a backup.

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

	def finish(outcome):
		try:
			_finish(outcome)
		finally:
			finished()

	def _finish(outcome):
		if isinstance(outcome, Exception):
			debugLog.note(f"the backup failed, so nothing was repaired; it is tried again next time NVDA starts: {outcome}")
			return
		result = repairDictionaries(configDir, debugLog.note)
		reloadLiveDictionaries(result.files)
		if result.failed:
			debugLog.note(f"some dictionaries could not be repaired; tried again next time NVDA starts: {result.failed}")
			return
		state.set(STATE_KEY, REPAIR_VERSION)
		debugLog.note(f"repaired {result.rewritten} rules in {result.files}; backup {getattr(outcome, 'path', '')}")
		if result.rewritten:
			announce(
				f"JAWS Migration Assistant repaired {result.rewritten} speech dictionary rules from your earlier JAWS migration, "
				"so they no longer change the middle of other words.",
			)

	def work():
		from . import migrator

		try:
			outcome = migrator._backupFirst("Before repairing the dictionary rules of an earlier migration")
		except Exception as error:
			debugLog.error("the backup before the dictionary repair failed")
			outcome = error
		import wx

		wx.CallAfter(finish, outcome)

	threading.Thread(target=work, name="jawsMigratorDictRepair", daemon=True).start()
	return True


def repairDictionaries(configDir: str, log=None) -> DictRepairResult:
	"""Repair the assistant's rules in every NVDA dictionary file. Writes only files that change."""
	result = DictRepairResult()
	say = log or (lambda message: None)
	for path in dictionaryFiles(configDir):
		try:
			with open(path, encoding="utf_8_sig", errors="replace", newline="") as stream:
				text = stream.read()
			repaired, changed = repairText(text)
			if not changed:
				continue
			safety.checkWritable(path)
			temporary = path + ".jawsMigrator.tmp"
			with open(temporary, "w", encoding="utf_8_sig", newline="") as stream:
				stream.write(repaired)
			os.replace(temporary, path)
			result.files.append(path)
			result.rewritten += changed
			say(f"repaired {changed} dictionary rules in {path}")
		except OSError as error:
			result.failed.append(f"{path}: {error}")
			say(f"could not repair {path}: {error}")
	return result
