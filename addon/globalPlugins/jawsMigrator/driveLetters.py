# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""A drive is said as JAWS says it: "Data (D:)" without the ":)" after its letter.

File Explorer names a drive with its letter in parentheses: "Data (D:)", "Local Disk (C:)". At NVDA's
"most" symbol level, which JAWS's Most level becomes, NVDA says every symbol in it: "Data left paren D
colon right paren". A tester heard the end, ":)", as a smiley and asked for it to go: JAWS says the same
drive as "Data (D", with nothing after the letter (issue 4, with version 1.14). JAWS's symbol files have no
rule of their own for this (eloq.sbl names "(", ":" and ")" at the Most level), so the rule follows what the
tester heard from JAWS.

NVDA allows a rule that looks at the characters around a symbol ("complex symbols") only in a symbol
dictionary of its own kind, so, as with JAWS's rule for a colon between digits (numberSymbols), the rule is
added while NVDA runs, as a symbol dictionary of its own: ``:) drive letter``, a colon and a closing
parenthesis right after "(" and a capital letter. At the "all" level it is said in NVDA's own words for ":"
and ")" ("colon right paren"), as before. Below that it is left out, and it is not passed to the
synthesizer either, so a synthesizer that reads ":)" as a smiley can't. The "(" before the letter is said as
NVDA's symbols say it: "Data left paren D" at the "most" level, "Data D" at "some". This works wherever a
drive's name is read: This PC, the navigation pane, the address bar, Open and Save As dialogs, and a window's
title in Alt+Tab ("Data (D:) - File Explorer"). Reading by character still says each character.

It comes after the user's own symbols, so a change made in NVDA's Punctuation/symbol pronunciation dialog
still wins. It works while the assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration
Assistant.

With version 1.15 the tester still heard "Data (D:)" read with a smiley (issue 4). Their log shows 1.15 and
the rule loaded, NVDA at the "most" level, and "Data (D:)" given to NVDA to say. NVDA 2026.2's own symbol
processing, with the rule, leaves no ":)" there, and none of the Emoticons add-on's patterns matches "(D:)".
The one step before the symbols is the speech dictionaries: ``speech.speech.processText`` runs
``speechDictHandler.processText``, then ``characterProcessing.processSpeechSymbols``. An "anywhere" entry for
":)", the kind NVDA's dictionary dialog makes by default and the migration makes for a JAWS rule made only of
symbols, matches the ":)" in "(D:)" too, where JAWS's whole-word match doesn't, and the symbol rule never sees
it. So the ":)" of a drive letter is also taken out of the text ``processText`` is given, before the
dictionaries, whenever the rule itself would leave it out: below the rule's level, "all" unless the user chose
another in NVDA's dialog. At that level and above, the text is left for the rule to say.
"""

from __future__ import annotations

import functools
import importlib
import re

from . import numberSymbols

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "driveLetterLikeJaws"
IDENTIFIER = ":) drive letter"
#: The ":)" of a drive letter in parentheses, as File Explorer names drives: Data (D:), Local Disk (C:).
PATTERN = r"(?<=\([A-Z]):\)"
DISPLAY_NAME = "colon and parenthesis after a drive letter, as in Data (D:)"
DEFINITION_NAME = "jawsMigratorDrives"
#: Used where NVDA's own words for ":" and ")" can't be found.
FALLBACK_WORDS = {":": "colon", ")": "right paren"}
#: The module and function through which NVDA sends each piece of text it speaks to the speech dictionaries,
#: then to the symbols.
SPEECH_MODULE = "speech.speech"
PROCESS_TEXT = "processText"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's version, so another add-on's wrapper around it is recognized.
MARK = "_jawsMigratorDriveLetters"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16
_LEAVE_OUT = re.compile(PATTERN)

_definition = None
#: What the assistant put in the place of NVDA's processText: (module, the assistant's, NVDA's), or None.
_guard = None
#: What the log has said once: "guardFailed", "leftOut", "processFailed".
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


def wanted(stateData: dict) -> bool:
	"""Whether a drive is said without the ":)" after its letter: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def words(characterProcessing, locale: str) -> str:
	"""NVDA's own words for ":)" in ``locale``, such as "colon right paren", for the "all" level."""
	return " ".join(numberSymbols.symbolWord(characterProcessing, locale, character, fallback) for character, fallback in FALLBACK_WORDS.items())


def makeDefinition(characterProcessing):
	"""A symbol dictionary definition holding the rule, for NVDA's ``characterProcessing``."""

	class DriveSymbolsDefinition(characterProcessing.SymbolDictionaryDefinition):
		"""Built in memory, for the languages NVDA has built-in symbols for, as numberSymbols' is."""

		def _initSymbols(self, locale: str):
			builtin = numberSymbols.builtinDefinition(characterProcessing)
			if builtin is None or locale not in builtin.availableLocales:
				raise FileNotFoundError(f"No {self.name!r} data for locale {locale!r}")
			symbols = characterProcessing.SpeechSymbols()
			symbols.complexSymbols[IDENTIFIER] = PATTERN
			symbols.symbols[IDENTIFIER] = characterProcessing.SpeechSymbol(
				IDENTIFIER,
				None,
				words(characterProcessing, locale),
				characterProcessing.SymbolLevel.ALL,
				characterProcessing.SYMPRES_NEVER,
				DISPLAY_NAME,
			)
			return symbols

	return DriveSymbolsDefinition(
		name=DEFINITION_NAME,
		path="jawsMigrator-drives-{locale}",
		source="jawsMigrator",
		allowComplexSymbols=True,
		mandatory=True,
	)


def register() -> bool:
	"""Add the rule to NVDA's symbol processing. Returns whether it is in place.

	NVDA rebuilds its list of symbol dictionaries when it reloads its configuration (NVDA+Control+R, or
	after a restore), which drops the rule; registering again puts it back.
	"""
	global _definition
	try:
		import characterProcessing

		definitions = characterProcessing._symbolDictionaryDefinitions
		if _definition is None or _definition not in definitions:
			definition = _definition or makeDefinition(characterProcessing)
			# The user's symbols stay last, where NVDA expects them, so they win over this rule.
			position = len(definitions)
			for index, existing in enumerate(definitions):
				if getattr(existing, "name", None) == "user":
					position = index
			definitions.insert(position, definition)
			if _definition is None:
				_log().debug('jawsMigrator: a drive is said without the ":)" after its letter, as JAWS says "Data (D:)" (NVDA symbol rule ":) drive letter")')
			_definition = definition
			characterProcessing.clearSpeechSymbols()
	except Exception:
		_log().debugWarning("jawsMigrator: the rule for a drive's letter could not be added", exc_info=True)
		return False
	_guardSpeech()
	return True


def unregister() -> None:
	"""Take the rule out of NVDA's symbol processing again."""
	global _definition
	definition, _definition = _definition, None
	_unguardSpeech()
	if definition is None:
		return
	try:
		import characterProcessing

		definitions = characterProcessing._symbolDictionaryDefinitions
		if definition in definitions:
			definitions.remove(definition)
		characterProcessing.clearSpeechSymbols()
	except Exception:
		_log().debugWarning("jawsMigrator: the rule for a drive's letter could not be taken out", exc_info=True)


def isRegistered() -> bool:
	return _definition is not None


def isGuardingSpeech() -> bool:
	"""Whether the assistant's version of NVDA's processText is in place now."""
	return _guard is not None and _isOurs(vars(_guard[0]).get(PROCESS_TEXT))


# -- before NVDA's speech dictionaries ---------------------------------------------------------------------------


def _isOurs(function) -> bool:
	"""Whether ``function`` is the assistant's version, or wraps it (as another add-on's functools.wraps wrapper would)."""
	for _ in range(_MOST_WRAPPERS):
		if function is None:
			return False
		if getattr(function, MARK, None) is _TOKEN:
			return True
		function = getattr(function, "__wrapped__", None)
	return False


def _guardSpeech() -> bool:
	"""Put the assistant's version of NVDA's processText in place, once. True when it is there."""
	global _guard
	try:
		module = importlib.import_module(SPEECH_MODULE)
		current = vars(module).get(PROCESS_TEXT)
		if _isOurs(current):
			return True
		if not callable(current):
			_once("guardFailed", f"NVDA has no {PROCESS_TEXT} the assistant knows, so a drive's letter is left to NVDA's symbols alone")
			return False
		installed = _guarded(current)
		setattr(module, PROCESS_TEXT, installed)
		_guard = (module, installed, current)
		_log().debug(f'jawsMigrator: the ":)" after a drive letter is taken out before NVDA\'s speech dictionaries ({SPEECH_MODULE}.{PROCESS_TEXT})')
		return True
	except Exception:
		_once("guardFailed", "can't take a drive letter's \":)\" out before NVDA's speech dictionaries", warning=True)
		return False


def _unguardSpeech() -> None:
	"""Give NVDA its own processText back, where nothing has been put over the assistant's since."""
	global _guard
	guard, _guard = _guard, None
	if guard is None:
		return
	module, installed, original = guard
	try:
		if vars(module).get(PROCESS_TEXT) is installed:
			setattr(module, PROCESS_TEXT, original)
	except Exception:
		pass


def _ruleLevel(locale: str):
	"""The symbol level from which the rule says the ":)": "all", or the level the user chose for it in NVDA's
	Punctuation/symbol pronunciation dialog."""
	import characterProcessing

	try:
		processors = characterProcessing._localeSpeechSymbolProcessors
		try:
			processor = processors.fetchLocaleData(locale)
		except LookupError:
			# NVDA speaks such a language with English symbols (processSpeechSymbols).
			processor = processors.fetchLocaleData("en")
		level = getattr(processor.computedSymbols.get(IDENTIFIER), "level", None)
	except Exception:
		level = None
	return characterProcessing.SymbolLevel.ALL if level is None else level


def leaveOut(locale: str, text: str, symbolLevel) -> str:
	"""``text`` without the ":)" of a drive letter, where the rule would leave it out at ``symbolLevel``."""
	if _definition is None or not isinstance(text, str) or ":)" not in text or not _LEAVE_OUT.search(text):
		return text
	if symbolLevel >= _ruleLevel(locale):
		return text
	_once("leftOut", 'the ":)" after a drive letter is left out before NVDA\'s speech dictionaries, as JAWS says "Data (D:)"')
	return _LEAVE_OUT.sub("", text)


def _guarded(original):
	"""NVDA's processText: speech dictionaries, then symbols. A drive letter's ":)" is taken out first."""

	@functools.wraps(original)
	def processText(locale, text, symbolLevel, *args, **kwargs):
		try:
			text = leaveOut(locale, text, symbolLevel)
		except Exception:
			_once("processFailed", "could not take a drive letter's \":)\" out, so NVDA's dictionaries and symbols have it", warning=True)
		return original(locale, text, symbolLevel, *args, **kwargs)

	setattr(processText, MARK, _TOKEN)
	setattr(processText, ORIGINAL, original)
	return processText


def matches(text: str) -> list[str]:
	"""What the rule leaves out in ``text``, for tests."""
	return re.findall(PATTERN, text)
