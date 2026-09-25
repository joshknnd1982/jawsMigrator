# Unit tests for version 1.15, from a tester's report on version 1.14 (issue 4):
# - driveLetters: File Explorer's "Data (D:)" was said "Data left paren D colon right paren" at NVDA's "most" symbol
#   level, which the tester's JAWS Most level became. The tester heard the ":)" as a smiley and asked for it to go:
#   JAWS says the drive as "Data (D".
# The imitation NVDA below speaks text as NVDA 2026.2 does (characterProcessing.SpeechSymbolProcessor: its
# sources in NVDA's order, complex symbols first, then simple ones, and _regexpRepl), with the lines of NVDA's own
# English symbols.dic that matter here. The speech is what the tester's 1.14 log shows NVDA was given to say. The
# assistant's rule, register and unregister are the real ones.
# Run: python -m unittest tests.test_v115_fixes -v

import collections
import dataclasses
import os
import re
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import driveLetters, numberSymbols, nvdaApply, state  # noqa: E402

NONE, SOME, MOST, ALL = 0, 100, 200, 300
NEVER, ALWAYS, NOREP = 0, 1, 2

#: What the tester's NVDA was given to say when Alt+Tab brought This PC back (their 1.14 log, 11:09:27.968).
TESTERS_SPEECH = "Data (D:)"

#: NVDA 2026.2's locale\en\symbols.dic: its complex symbols, and the simple symbols that matter here.
NVDA_COMPLEX = {
	". sentence ending": r"(?<=[^\s.])\.(?=[\"'”’)\s]|$)",
	"; phrase ending": r"(?<=[^\s;]);(?=\s|$)",
	": phrase ending": r"(?<=[^\s:]):(?=\s|$)",
	"decimal point": r"(?<![^\d -])\.(?=\d)",
}
NVDA_SYMBOLS = {
	". sentence ending": ("dot", ALL, ALWAYS),
	"; phrase ending": ("semi", MOST, ALWAYS),
	": phrase ending": ("colon", MOST, ALWAYS),
	"decimal point": ("", NONE, ALWAYS),
	"(": ("left paren", MOST, ALWAYS),
	")": ("right paren", MOST, ALWAYS),
	",": ("comma", ALL, ALWAYS),
	"-": ("dash", MOST, ALWAYS),
	".": ("dot", SOME, NEVER),
	":": ("colon", MOST, NOREP),
	"\\": ("backslash", MOST, NEVER),
	"#": ("number", SOME, NEVER),
}
#: NVDA 2026.2's words for ":" and ")" in German (locale\de\symbols.dic).
GERMAN_SYMBOLS = {":": ("Doppelpunkt", MOST, NOREP), ")": ("Klammer zu", MOST, ALWAYS)}


# -- an imitation of NVDA's characterProcessing ------------------------------------------------------------------


class _Symbols:
	def __init__(self, filename=None):
		self.complexSymbols = collections.OrderedDict()
		self.symbols = collections.OrderedDict()


@dataclasses.dataclass
class _Symbol:
	identifier: str
	pattern: str | None = None
	replacement: str | None = None
	level: int | None = None
	preserve: int | None = None
	displayName: str | None = None


@dataclasses.dataclass(frozen=True, kw_only=True)
class _Definition:
	name: str
	path: str
	source: str = "builtin"
	allowComplexSymbols: bool = False
	mandatory: bool = False

	@property
	def availableLocales(self):
		return {"en": "en", "de": "de"} if self.name == "builtin" else {}

	def getSymbols(self, locale):
		return self._initSymbols(locale)

	def _initSymbols(self, locale):
		symbols = _Symbols()
		if self.name == "builtin" and locale in ("en", "de"):
			if locale == "en":
				symbols.complexSymbols.update(NVDA_COMPLEX)
			for identifier, (replacement, level, preserve) in (NVDA_SYMBOLS if locale == "en" else GERMAN_SYMBOLS).items():
				symbols.symbols[identifier] = _Symbol(identifier, None, replacement, level, preserve)
			return symbols
		if self.source == "user":
			return symbols
		raise FileNotFoundError(f"No {self.name!r} data for locale {locale!r}")


def _characterProcessing():
	"""NVDA 2026.2's characterProcessing, as far as symbol dictionaries and symbol processing go."""
	module = types.ModuleType("characterProcessing")
	module.SymbolDictionaryDefinition = _Definition
	module.SpeechSymbols = _Symbols
	module.SpeechSymbol = _Symbol
	module.SymbolLevel = types.SimpleNamespace(NONE=NONE, SOME=SOME, MOST=MOST, ALL=ALL)
	module.SYMPRES_NEVER, module.SYMPRES_ALWAYS, module.SYMPRES_NOREP = NEVER, ALWAYS, NOREP
	module.cleared = 0
	module._symbolDictionaryDefinitions = []

	def clearSpeechSymbols():
		module.cleared += 1

	def initialize():
		module._symbolDictionaryDefinitions.extend(
			[
				_Definition(name="cldr", path="{locale}"),
				_Definition(name="builtin", path="{locale}", allowComplexSymbols=True, mandatory=True),
				_Definition(name="user", path="{locale}", source="user", mandatory=True),
			],
		)

	module.clearSpeechSymbols = clearSpeechSymbols
	module.initialize = initialize
	module.terminate = module._symbolDictionaryDefinitions.clear
	initialize()
	return module


def speak(module, text, level=MOST, locale="en"):
	"""What NVDA 2026.2 sends the synthesizer for ``text`` (SpeechSymbolProcessor.processText)."""
	fetched = []
	for definition in module._symbolDictionaryDefinitions:
		try:
			fetched.append(definition.getSymbols(locale))
		except FileNotFoundError:
			continue
	# The user's symbols first, then the others from last to first.
	sources = [fetched[-1]] + fetched[-2::-1]
	symbols = collections.OrderedDict()
	complexList = []
	for source in sources:
		for identifier, pattern in source.complexSymbols.items():
			if identifier not in symbols:
				symbols[identifier] = _Symbol(identifier, pattern)
				complexList.append(symbols[identifier])
	for source in sources:
		for identifier, sourceSymbol in source.symbols.items():
			symbol = symbols.setdefault(identifier, _Symbol(identifier))
			for field in ("replacement", "level", "preserve"):
				if getattr(symbol, field) is None:
					setattr(symbol, field, getattr(sourceSymbol, field))
	characters = "[%s]" % re.escape("".join(identifier for identifier, symbol in symbols.items() if symbol.pattern is None and len(identifier) == 1))
	patterns = [f"(?P<c{index}>{symbol.pattern})" for index, symbol in enumerate(complexList)]
	patterns += [r"(?P<rstripSpace>  +$)", rf"(?P<repeated>(?P<repTmp>{characters})(?P=repTmp){{3,}})", rf"(?P<simple>{characters})"]

	def replace(match):
		group = match.lastgroup
		if group == "rstripSpace":
			return ""
		text = match.group()
		symbol = symbols[text] if group == "simple" else complexList[int(group[1:])]
		suffix = text if symbol.preserve == ALWAYS or (symbol.preserve == NOREP and level < symbol.level) else " "
		if level >= symbol.level and symbol.replacement:
			return f" {symbol.replacement}{suffix}"
		return suffix

	return re.sub("|".join(patterns), replace, text)


def words(synthesizerText):
	"""The words a synthesizer says for text NVDA sends it: punctuation left in the text isn't said."""
	return re.findall(r"[^\W_]+", synthesizerText)


class NvdaTestCase(unittest.TestCase):
	def setUp(self):
		self.module = _characterProcessing()
		patcher = mock.patch.dict(sys.modules, {"characterProcessing": self.module})
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(driveLetters.unregister)
		self.addCleanup(numberSymbols.unregister)

	def names(self):
		return [definition.name for definition in self.module._symbolDictionaryDefinitions]


# -- what NVDA says ------------------------------------------------------------------------------------------------


class DriveLetterSpeechTests(NvdaTestCase):
	def test_theTestersDriveAtMost(self):
		self.assertEqual(words(speak(self.module, TESTERS_SPEECH)), ["Data", "left", "paren", "D", "colon", "right", "paren"], "1.14")
		self.assertTrue(driveLetters.register())
		said = speak(self.module, TESTERS_SPEECH)
		self.assertEqual(words(said), ["Data", "left", "paren", "D"], "JAWS: Data (D")
		self.assertNotIn(":", said, "no smiley reaches the synthesizer")
		self.assertNotIn(")", said)

	def test_otherLevels(self):
		self.assertTrue(driveLetters.register())
		self.assertEqual(speak(self.module, TESTERS_SPEECH, SOME).split(), ["Data", "(D"], "the parenthesis stays for the synthesizer's pause")
		self.assertEqual(speak(self.module, TESTERS_SPEECH, NONE).split(), ["Data", "(D"])
		self.assertEqual(words(speak(self.module, TESTERS_SPEECH, ALL)), ["Data", "left", "paren", "D", "colon", "right", "paren"], "at All, every symbol")

	def test_whereverADriveIsNamed(self):
		self.assertTrue(driveLetters.register())
		self.assertEqual(words(speak(self.module, "Local Disk (C:)")), ["Local", "Disk", "left", "paren", "C"])
		self.assertEqual(words(speak(self.module, "Data (D:) - File Explorer")), ["Data", "left", "paren", "D", "dash", "File", "Explorer"], "Alt+Tab")
		self.assertEqual(words(speak(self.module, "Backup (\\\\server\\share) (Z:)")), ["Backup", "left", "paren", "backslash", "backslash", "server", "backslash", "share", "right", "paren", "left", "paren", "Z"])

	def test_everythingElseAsBefore(self):
		texts = ["Great :) thanks", ":)", "C:\\Windows", "Re: (Issue #4)", "(a:)", "(D: drive)", "Received 6:02 PM", "The end."]
		levels = (NONE, SOME, MOST, ALL)
		before = {(text, level): speak(self.module, text, level) for text in texts for level in levels}
		self.assertEqual(words(before["Great :) thanks", MOST]), ["Great", "colon", "right", "paren", "thanks"], "a smiley in text is NVDA's to say")
		self.assertTrue(driveLetters.register())
		after = {(text, level): speak(self.module, text, level) for text in texts for level in levels}
		self.assertEqual(after, before)

	def test_withTheRuleForTimes(self):
		self.assertTrue(numberSymbols.register())
		self.assertTrue(driveLetters.register())
		self.assertEqual(self.names(), ["cldr", "builtin", numberSymbols.DEFINITION_NAME, driveLetters.DEFINITION_NAME, "user"])
		self.assertEqual(words(speak(self.module, "Data (D:) at 6:02 PM")), ["Data", "left", "paren", "D", "at", "6", "02", "PM"])

	def test_theUsersOwnSymbolWins(self):
		self.assertTrue(driveLetters.register())
		user = self.module._symbolDictionaryDefinitions[-1]
		users = _Symbols()
		users.symbols[driveLetters.IDENTIFIER] = _Symbol(driveLetters.IDENTIFIER, None, None, MOST, None)
		with mock.patch.object(_Definition, "_initSymbols", lambda self, locale, original=_Definition._initSymbols: users if self is user else original(self, locale)):
			self.assertEqual(words(speak(self.module, TESTERS_SPEECH)), ["Data", "left", "paren", "D", "colon", "right", "paren"], "set to most in NVDA's dialog")


# -- the rule ------------------------------------------------------------------------------------------------------


class DriveLetterRuleTests(NvdaTestCase):
	def test_pattern(self):
		for text in ("Data (D:)", "Local Disk (C:)", "Data (D:) - File Explorer", "USB Drive (E:), 3 of 3"):
			self.assertEqual(driveLetters.matches(text), [":)"], text)
		for text in (":)", "Great :) thanks", "C:\\Windows", "(a:)", "(D: drive)", "Re: (Issue #4)", "6:02", "(DE:)", "Data (D:"):
			self.assertEqual(driveLetters.matches(text), [], text)

	def test_theSymbol(self):
		self.assertTrue(driveLetters.register())
		self.assertTrue(driveLetters.register(), "registering twice does nothing more")
		self.assertEqual(self.names(), ["cldr", "builtin", driveLetters.DEFINITION_NAME, "user"])
		definition = self.module._symbolDictionaryDefinitions[2]
		self.assertTrue(definition.allowComplexSymbols and definition.mandatory)
		english = definition.getSymbols("en")
		self.assertEqual(english.complexSymbols, {driveLetters.IDENTIFIER: driveLetters.PATTERN})
		symbol = english.symbols[driveLetters.IDENTIFIER]
		self.assertEqual((symbol.replacement, symbol.level, symbol.preserve), ("colon right paren", ALL, NEVER))
		self.assertEqual(symbol.displayName, "colon and parenthesis after a drive letter, as in Data (D:)")
		self.assertEqual(definition.getSymbols("de").symbols[driveLetters.IDENTIFIER].replacement, "Doppelpunkt Klammer zu", "NVDA's own words")
		with self.assertRaises(FileNotFoundError, msg="like NVDA's built-in symbols, no data for en_US"):
			definition.getSymbols("en_US")

	def test_unregister(self):
		self.assertTrue(driveLetters.register())
		driveLetters.unregister()
		self.assertEqual(self.names(), ["cldr", "builtin", "user"])
		self.assertFalse(driveLetters.isRegistered())
		self.assertEqual(self.module.cleared, 2)
		self.assertEqual(words(speak(self.module, TESTERS_SPEECH)), ["Data", "left", "paren", "D", "colon", "right", "paren"])
		driveLetters.unregister()

	def test_nvdaReloadingItsSymbols(self):
		self.assertTrue(numberSymbols.register())
		self.assertTrue(driveLetters.register())
		nvdaApply.reloadSymbols()
		self.assertEqual(sorted(self.names()), sorted(["cldr", "builtin", numberSymbols.DEFINITION_NAME, driveLetters.DEFINITION_NAME, "user"]))
		self.assertEqual(self.names()[-1], "user", "the user's symbols stay last")
		driveLetters.unregister()
		nvdaApply.reloadSymbols()
		self.assertNotIn(driveLetters.DEFINITION_NAME, self.names(), "turned off, it doesn't come back")

	def test_whatTheLogSays(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			driveLetters.register()
			driveLetters.register()
		lines = [line for line in logged.output if "a drive is said without" in line]
		self.assertEqual(len(lines), 1, logged.output)

	def test_aFailureIsLogged(self):
		del self.module._symbolDictionaryDefinitions
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.assertFalse(driveLetters.register())
		self.assertTrue(any("the rule for a drive's letter could not be added" in line for line in logged.output), logged.output)
		self.assertFalse(driveLetters.isRegistered())

	def test_theSetting(self):
		self.assertTrue(driveLetters.wanted({}))
		self.assertFalse(driveLetters.wanted({driveLetters.STATE_KEY: False}))
		self.assertFalse(driveLetters.wanted(None))
		self.assertIs(state.DEFAULTS[driveLetters.STATE_KEY], True)


if __name__ == "__main__":
	unittest.main()
