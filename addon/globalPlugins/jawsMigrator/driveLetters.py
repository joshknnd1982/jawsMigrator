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
"""

from __future__ import annotations

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

_definition = None


def _log():
	from logHandler import log

	return log


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
		if _definition is not None and _definition in definitions:
			return True
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
	return True


def unregister() -> None:
	"""Take the rule out of NVDA's symbol processing again."""
	global _definition
	definition, _definition = _definition, None
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


def matches(text: str) -> list[str]:
	"""What the rule leaves out in ``text``, for tests."""
	return re.findall(PATTERN, text)
