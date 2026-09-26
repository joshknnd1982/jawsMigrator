# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""JAWS's dictionary for one application changes speech only in that application, as in JAWS.

Beside its default dictionary, JAWS keeps a dictionary for each application, named after the application's JAWS
configuration: Theophilos.jdf for the Bible program Theophilos, Excel.jdf, Outlook.jdf, WORD.jdf... JAWS uses it
only while that application is active, before the default dictionary. NVDA's speech dictionaries are the same in
every program, and versions 1.0 to 1.20 put the rules of every JAWS application dictionary into NVDA's default
dictionary, so they changed speech everywhere. A tester heard "job" said wrongly on a web page (issue 13):
Freedom Scientific's Theophilos.jdf says the Book of Job as "jobe" ("Job" -> "jobe", not case-sensitive), and JAWS
uses it only in Theophilos. Excel.jdf says "a" as "eigh", for a column's letter; in NVDA's default dictionary it
changed every "a".

Now each JAWS application dictionary is a file of its own, ``speechDicts\\jawsApplications\\<configuration>.dic`` in
NVDA's settings folder, in the format of NVDA's dictionaries, with a comment at its top naming the programs it is
for ("#Programs: theophil"), as JAWS's ConfigNames.ini maps programs to configurations (see
migrator.appExecutables). While the focus is in one of those programs, its rules are applied before NVDA's own
dictionaries, as JAWS applies an application's dictionary before its default one. NVDA applies its dictionaries in
``speechDictHandler.processText``, which ``speech.speech.processText`` calls for each piece of text it speaks; the
assistant's version applies the program's rules first. They are applied as NVDA applies its own: only while NVDA's
dictionary processing is on, and, with NVDA 2026.2, while NVDA's default dictionary is on. The rules earlier
versions put into the default and voice dictionaries are moved into these files once (see dictRepair).

NVDA's log shows the text it speaks before its dictionaries change it, so a word said wrongly can't be traced to a
rule from the log. When NVDA logs at its debug level, the assistant also logs each dictionary rule that changes
what NVDA says, with the rule's comment, which for a migrated rule names the JAWS file and line it came from.
"""

from __future__ import annotations

import functools
import importlib
import logging
import os
import re

from . import dictMap, safety

#: The folder in NVDA's ``speechDicts`` folder that holds the JAWS application dictionaries.
FOLDER_NAME = "jawsApplications"
#: The comment line at the top of each file that names its programs.
PROGRAMS = "Programs:"
#: The module and function through which NVDA applies its speech dictionaries to each piece of text it speaks.
DICTIONARY_MODULE = "speechDictHandler"
PROCESS_TEXT = "processText"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's version, so another add-on's wrapper around it is recognized.
MARK = "_jawsMigratorAppDicts"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16
#: How much of a text the log shows.
_LOGGED_TEXT = 160

#: What the assistant put in the place of NVDA's function: (module, the assistant's, NVDA's), or None.
_guard = None
#: {program: [NVDA SpeechDict, ...]}, loaded when first needed; None until then.
_dictionaries: dict | None = None
#: What the log has said once.
_logged: set = set()


def _log():
	from logHandler import log

	return log


def _once(key: str, message: str, warning: bool = False) -> None:
	if key in _logged:
		return
	_logged.add(key)
	try:
		if warning:
			_log().debugWarning(f"jawsMigrator: {message}", exc_info=True)
		else:
			_log().debug(f"jawsMigrator: {message}")
	except Exception:
		pass


# -- the files -----------------------------------------------------------------------------------------------------


def folder(configDir: str | None = None) -> str:
	if configDir is None:
		from . import nvdaEnv

		configDir = nvdaEnv.configDir()
	return os.path.join(configDir, "speechDicts", FOLDER_NAME)


def path(configName: str, configDir: str | None = None) -> str:
	"""The file for the JAWS configuration ``configName`` (Theophilos, Excel...)."""
	return os.path.join(folder(configDir), f"{configName}.dic")


def header(configName: str, programs: list) -> str:
	"""The comment at the top of a file: what it is, and the programs it is for. A blank line ends it, so NVDA
	doesn't take it for the comment of the first rule."""
	where = ", ".join(programs)
	if programs:
		about = f"JAWS uses these rules only in {configName}, and so does NVDA while the JAWS Migration Assistant runs."
	else:
		about = (
			f"JAWS uses these rules only in {configName}, which NVDA does not know as a program, so NVDA uses them nowhere. "
			f"To use them in a program, add its name (the program's file name without .exe) after {PROGRAMS}"
		)
	return f"#JAWS's dictionary for {configName}. {about}\n#{PROGRAMS} {where}\n\n"


def readPrograms(filePath: str) -> list[str]:
	"""The programs named at the top of a file, lower case; [] when it names none or can't be read."""
	try:
		with open(filePath, encoding="utf_8_sig", errors="replace") as stream:
			for line in stream:
				line = line.strip()
				if not line:
					continue
				if not line.startswith("#"):
					break
				text = line[1:].strip()
				if text.lower().startswith(PROGRAMS.lower()):
					names = text[len(PROGRAMS):].split(",")
					return [name.strip().lower() for name in names if name.strip()]
	except OSError:
		pass
	return []


def _setPrograms(text: str, configName: str, programs: list) -> str:
	"""``text`` with its programs line naming ``programs`` too, or with the header in front when it has none."""
	lines = text.splitlines(keepends=True)
	for index, line in enumerate(lines):
		stripped = line.strip()
		if not stripped:
			continue
		if not stripped.startswith("#"):
			break
		if stripped[1:].strip().lower().startswith(PROGRAMS.lower()):
			names = [name.strip().lower() for name in stripped[1:].strip()[len(PROGRAMS):].split(",") if name.strip()]
			for program in programs:
				if program.lower() not in names:
					names.append(program.lower())
			ending = "\r\n" if line.endswith("\r\n") else "\n"
			lines[index] = f"#{PROGRAMS} {', '.join(names)}{ending}"
			return "".join(lines)
	return header(configName, programs) + text


def writeRules(configName: str, programs: list, entries: list, configDir: str | None = None) -> int:
	"""Add ``entries`` (dictMap.DictEntry) to the file for ``configName``, creating it with its header when needed.

	A rule the file already has (the same word and kind) is not added again. Returns how many were added.
	"""
	filePath = path(configName, configDir)
	existing = ""
	if os.path.isfile(filePath):
		with open(filePath, encoding="utf_8_sig", errors="replace") as stream:
			existing = stream.read()
	known = dictMap.readDicPatterns(filePath) if existing else set()
	new = []
	for entry in entries:
		key = entry.key() + ("",)
		if key in known:
			continue
		known.add(key)
		new.append(entry)
	text = _setPrograms(existing, configName, programs) if existing else header(configName, programs)
	if not new and text == existing:
		return 0
	lines = [text.rstrip("\r\n") + "\n\n" if existing else text]
	for entry in new:
		if entry.comment:
			lines.append(f"#{entry.comment}\n")
		lines.append(entry.asLine() + "\n")
	safety.checkWritable(filePath)
	os.makedirs(os.path.dirname(filePath), exist_ok=True)
	temporary = filePath + ".jawsMigrator.tmp"
	with open(temporary, "w", encoding="utf_8_sig", newline="") as stream:
		stream.write("".join(lines))
	os.replace(temporary, filePath)
	return len(new)


# -- NVDA's dictionaries ---------------------------------------------------------------------------------------------


def _speechDictClass():
	try:
		from speechDictHandler.types import SpeechDict
	except ImportError:
		# NVDA 2026.1 keeps it in speechDictHandler itself.
		from speechDictHandler import SpeechDict
	return SpeechDict


def load(configDir: str | None = None) -> dict:
	"""``{program: [dictionary, ...]}`` for every file, read by NVDA's own dictionary code."""
	result: dict = {}
	directory = folder(configDir)
	try:
		names = sorted(name for name in os.listdir(directory) if name.lower().endswith(".dic"))
	except OSError:
		return result
	SpeechDict = _speechDictClass()
	for name in names:
		filePath = os.path.join(directory, name)
		programs = readPrograms(filePath)
		if not programs:
			continue
		dictionary = SpeechDict()
		try:
			dictionary.load(filePath)
		except Exception:
			_log().debugWarning(f"jawsMigrator: NVDA could not read {filePath}", exc_info=True)
			continue
		if not len(dictionary):
			continue
		for program in programs:
			result.setdefault(program, []).append(dictionary)
	return result


def reload() -> None:
	"""Read the files again when next needed, after a migration, a repair or a restore changed them."""
	global _dictionaries
	_dictionaries = None


def dictionariesFor(program: str) -> list:
	global _dictionaries
	if _dictionaries is None:
		_dictionaries = load()
		if _dictionaries:
			_log().debug(f"jawsMigrator: JAWS's application dictionaries apply only in their programs: {sorted(_dictionaries)}")
	return _dictionaries.get(program.lower(), []) if program else []


def focusedProgram() -> str:
	"""The program the focus is in, as NVDA knows it (appModule.appName), or ""."""
	try:
		import api

		focus = api.getFocusObject()
		return (focus.appModule.appName or "").lower() if focus is not None else ""
	except Exception:
		return ""


def dictionariesOn() -> bool:
	"""Whether NVDA applies its default dictionary now: dictionary processing on, and the default dictionary chosen."""
	try:
		import globalVars

		if not getattr(globalVars, "speechDictionaryProcessing", True):
			return False
	except Exception:
		pass
	try:
		import config

		chosen = config.conf["speech"]["speechDictionaries"]
	except Exception:
		# NVDA 2026.1 has no such setting: its default dictionary is always on.
		return True
	return "default" in chosen


def _nvdaDictionaries() -> list:
	"""``[(name, dictionary)]`` NVDA applies to what it speaks, in its order, without its built-in one."""
	try:
		from speechDictHandler import definitions

		return [
			(definition.name, definition.dictionary)
			for definition in definitions._speechDictDefinitions
			if definition.enabled and definition.name != "builtin"
		]
	except ImportError:
		pass
	try:
		import speechDictHandler

		return [(kind, speechDictHandler.dictionaries[kind]) for kind in speechDictHandler.dictTypes if kind != "builtin"]
	except Exception:
		return []


def _short(text: str) -> str:
	return text if len(text) <= _LOGGED_TEXT else text[: _LOGGED_TEXT - 3] + "..."


def trace(text: str, program: str, application: list) -> list[str]:
	"""Each rule that changes ``text``, applied as NVDA applies them: the program's first, then NVDA's own."""
	fired = []
	steps = [(f"{program}'s JAWS", dictionary) for dictionary in application] + _nvdaDictionaries()
	for name, dictionary in steps:
		for entry in list(dictionary):
			try:
				changed = entry.sub(text)
			except Exception:
				continue
			if changed != text:
				comment = f": {entry.comment}" if getattr(entry, "comment", "") else ""
				fired.append(f"{entry.pattern!r} -> {entry.replacement!r} ({name} dictionary{comment})")
				text = changed
	return fired


def apply(text: str) -> str:
	"""``text`` with the rules for the focused program applied, when there are any."""
	if not isinstance(text, str) or not text or not dictionariesOn():
		return text
	program = focusedProgram()
	application = dictionariesFor(program)
	log = _log()
	try:
		debugging = log.isEnabledFor(logging.DEBUG)
	except Exception:
		debugging = False
	if debugging:
		try:
			fired = trace(text, program, application)
			if fired:
				log.debug(f"jawsMigrator: speech dictionary rules change {_short(text)!r}: " + "; ".join(fired))
		except Exception:
			_once("traceFailed", "could not log which dictionary rules change what NVDA says", warning=True)
	for dictionary in application:
		text = dictionary.sub(text)
	return text


# -- in NVDA's dictionary processing ---------------------------------------------------------------------------------


def _isOurs(function) -> bool:
	"""Whether ``function`` is the assistant's version, or wraps it (as another add-on's functools.wraps wrapper would)."""
	for _ in range(_MOST_WRAPPERS):
		if function is None:
			return False
		if getattr(function, MARK, None) is _TOKEN:
			return True
		function = getattr(function, "__wrapped__", None)
	return False


def _guarded(original):
	"""NVDA's speechDictHandler.processText, with the focused program's JAWS rules applied first."""

	@functools.wraps(original)
	def processText(text, *args, **kwargs):
		try:
			text = apply(text)
		except Exception:
			_once("applyFailed", "could not apply a JAWS application dictionary, so only NVDA's dictionaries were used", warning=True)
		return original(text, *args, **kwargs)

	setattr(processText, MARK, _TOKEN)
	setattr(processText, ORIGINAL, original)
	return processText


def register() -> bool:
	"""Apply JAWS's application dictionaries in their programs, reading their files again. True when in place."""
	global _guard
	reload()
	try:
		module = importlib.import_module(DICTIONARY_MODULE)
		current = vars(module).get(PROCESS_TEXT)
		if _isOurs(current):
			return True
		if not callable(current):
			_once("guardFailed", f"NVDA has no {DICTIONARY_MODULE}.{PROCESS_TEXT}, so JAWS's application dictionaries are not used")
			return False
		installed = _guarded(current)
		setattr(module, PROCESS_TEXT, installed)
		_guard = (module, installed, current)
		_log().debug(f"jawsMigrator: JAWS's application dictionaries apply in their programs, before NVDA's ({DICTIONARY_MODULE}.{PROCESS_TEXT})")
		return True
	except Exception:
		_once("guardFailed", "JAWS's application dictionaries could not be put in place", warning=True)
		return False


def unregister() -> None:
	"""Give NVDA its own processText back, where nothing has been put over the assistant's since."""
	global _guard
	guard, _guard = _guard, None
	reload()
	if guard is None:
		return
	module, installed, original = guard
	try:
		if vars(module).get(PROCESS_TEXT) is installed:
			setattr(module, PROCESS_TEXT, original)
	except Exception:
		pass


def isRegistered() -> bool:
	return _guard is not None and _isOurs(vars(_guard[0]).get(PROCESS_TEXT))


# -- which JAWS file a rule came from ----------------------------------------------------------------------------------

#: The JAWS file named in a migrated rule's comment: "From JAWS shared Theophilos.jdf, line 40".
_SOURCE = re.compile(r"From JAWS (?:your|shared) (.+?)\.jdf\b", re.IGNORECASE)


def sourceConfiguration(comment: str) -> str | None:
	"""The JAWS configuration (Theophilos) whose dictionary a migrated rule came from; "default" for the default one,
	None when the comment names no JAWS dictionary."""
	match = _SOURCE.search(comment or "")
	if match is None:
		return None
	return match.group(1).strip()


def isApplicationRule(comment: str) -> bool:
	name = sourceConfiguration(comment)
	return name is not None and name.lower() != "default"
