# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""JAWS's rule for a colon between digits, as in 6:02 PM, as an NVDA symbol rule.

JAWS's symbol files (``.sbl``) have a key of their own for it: ``NumericColonText``, "what to
speak for a colon between digits as in 09:30". JAWS only speaks it at the All punctuation level;
below that it leaves the colon in the text, so the synthesizer reads a time as a time ("six oh
two PM"). NVDA has no such rule: at its "most" symbol level, which JAWS's Most level becomes, the
colon in 6:02 is spoken, and a time sounds like "6 colon 02 PM".

NVDA only allows rules that look at the characters around a symbol ("complex symbols") in its
built-in symbol dictionary, not in the user's symbols file or an add-on's, so the rule is added
while NVDA runs, as a symbol dictionary of its own: ``numeric colon``, a colon with a digit on
each side, spoken at the "all" level only and otherwise kept for the synthesizer, as JAWS does.
It comes after the user's own symbols, so a change made in NVDA's Punctuation/symbol
pronunciation dialog still wins. The word is NVDA's own for the colon in that language.

It is only added once JAWS settings were migrated on this computer, and taken away again when
the assistant stops.
"""

from __future__ import annotations

import re

IDENTIFIER = "numeric colon"
#: A colon with a digit right before and right after it: 6:02, 10:30:15, John 3:16.
PATTERN = r"(?<=\d):(?=\d)"
DISPLAY_NAME = "colon between digits, as in 6:02"
DEFINITION_NAME = "jawsMigratorNumbers"
#: Used where NVDA's own word for the colon can't be found.
FALLBACK_WORD = "colon"

_definition = None


def _log():
	from logHandler import log

	return log


def wanted(stateData: dict) -> bool:
	"""Whether JAWS's number rule applies: JAWS settings were migrated on this computer."""
	return isinstance(stateData, dict) and bool(stateData.get("lastMigration"))


def _builtinDefinition(characterProcessing):
	for definition in getattr(characterProcessing, "_symbolDictionaryDefinitions", ()):
		if getattr(definition, "name", None) == "builtin":
			return definition
	return None


def colonWord(characterProcessing, locale: str) -> str:
	"""NVDA's own word for ":" in ``locale`` (from its built-in symbols), or English "colon"."""
	builtin = _builtinDefinition(characterProcessing)
	for candidate in (locale, locale.split("_", 1)[0], "en"):
		if builtin is None:
			break
		try:
			symbol = builtin.getSymbols(candidate).symbols.get(":")
		except Exception:
			continue
		replacement = getattr(symbol, "replacement", None)
		if replacement:
			return replacement
	return FALLBACK_WORD


def makeDefinition(characterProcessing):
	"""A symbol dictionary definition holding the rule, for NVDA's ``characterProcessing``."""

	class NumberSymbolsDefinition(characterProcessing.SymbolDictionaryDefinition):
		"""Built in memory, for the languages NVDA has built-in symbols for.

		Like NVDA's built-in dictionary it has no data for a regional locale such as en_US, so NVDA
		keeps falling back to the language (en) exactly as before, with the user's own symbols.
		"""

		def _initSymbols(self, locale: str):
			builtin = _builtinDefinition(characterProcessing)
			if builtin is None or locale not in builtin.availableLocales:
				raise FileNotFoundError(f"No {self.name!r} data for locale {locale!r}")
			symbols = characterProcessing.SpeechSymbols()
			symbols.complexSymbols[IDENTIFIER] = PATTERN
			symbols.symbols[IDENTIFIER] = characterProcessing.SpeechSymbol(
				IDENTIFIER,
				None,
				colonWord(characterProcessing, locale),
				characterProcessing.SymbolLevel.ALL,
				characterProcessing.SYMPRES_NOREP,
				DISPLAY_NAME,
			)
			return symbols

	return NumberSymbolsDefinition(
		name=DEFINITION_NAME,
		path="jawsMigrator-numbers-{locale}",
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
		_definition = definition
		characterProcessing.clearSpeechSymbols()
	except Exception:
		_log().debugWarning("jawsMigrator: JAWS's rule for a colon between digits could not be added", exc_info=True)
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
		_log().debugWarning("jawsMigrator: JAWS's rule for a colon between digits could not be taken out", exc_info=True)


def isRegistered() -> bool:
	return _definition is not None


def matches(text: str) -> list[str]:
	"""The colons the rule applies to in ``text``, for tests and the report."""
	return re.findall(PATTERN, text)
