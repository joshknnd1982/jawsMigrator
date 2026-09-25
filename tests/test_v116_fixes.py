# Unit tests for version 1.16, from a tester's report on version 1.15 (issue 4):
# - driveLetters: with 1.15, "Data (D:)" was still read with a smiley. The 1.15 log shows the symbol rule loaded,
#   NVDA at the "most" level and "Data (D:)" given to NVDA to say. NVDA runs its speech dictionaries before the
#   symbols (speech.speech.processText), so a dictionary entry for ":)" changes the drive's name before the rule
#   sees it. The ":)" of a drive letter is now taken out before the dictionaries too.
# The imitation NVDA is test_v115_fixes' characterProcessing (NVDA 2026.2's symbol processing), with NVDA 2026.2's
# speech.speech.processText in front of it: speechDictHandler.processText (each entry's re.sub, as
# speechDictHandler.types.SpeechDictEntry does), then processSpeechSymbols. The assistant's register, unregister and
# wrapper are the real ones.
# Run: python -m unittest tests.test_v116_fixes -v

import collections
import functools
import os
import re
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v115_fixes as v115  # noqa: E402
from jawsMigrator import driveLetters  # noqa: E402

NONE, SOME, MOST, ALL, CHAR = v115.NONE, v115.SOME, v115.MOST, v115.ALL, 1000
TESTERS_SPEECH = "Data (D:)"

#: NVDA's speech dictionary entry types.
ANYWHERE, REGEXP, WORD = 0, 1, 2
#: An "anywhere" entry for ":)", as NVDA's dictionary dialog makes by default, or the migration for a JAWS rule
#: made only of symbols.
SMILEY = (":)", "smiley", ANYWHERE)
#: The Emoticons add-on 38.0.0's entry for ":)" (smileysList.py), which needs a space or the start before the colon.
EMOTICONS_SMILE = (r"(\s|^)(:([\-]|)([)]{1})(\B|\s|$))", " smiling smiley; ", REGEXP)


def dictionaryEntry(pattern, replacement, type):
	"""speechDictHandler.types.SpeechDictEntry's compiled pattern and replacement."""
	if type == REGEXP:
		return re.compile(pattern), replacement
	if type == WORD:
		return re.compile(rf"\b{re.escape(pattern)}\b"), replacement.replace("\\", "\\\\")
	return re.compile(re.escape(pattern)), replacement.replace("\\", "\\\\")


class _Processors:
	"""characterProcessing._localeSpeechSymbolProcessors: each language's computed symbols, English for en_US."""

	def __init__(self, module):
		self.module = module

	def fetchLocaleData(self, locale, fallback=True):
		fetched = []
		for definition in self.module._symbolDictionaryDefinitions:
			try:
				fetched.append(definition.getSymbols(locale))
			except FileNotFoundError:
				continue
		if len(fetched) <= 1:
			if fallback and "_" in locale:
				return self.fetchLocaleData(locale.split("_")[0])
			raise LookupError(locale)
		symbols = collections.OrderedDict()
		for source in [fetched[-1]] + fetched[-2::-1]:
			for identifier, sourceSymbol in list(source.complexSymbols.items()) + list(source.symbols.items()):
				symbol = symbols.setdefault(identifier, v115._Symbol(identifier))
				if isinstance(sourceSymbol, str):
					continue
				if symbol.level is None:
					symbol.level = sourceSymbol.level
		return types.SimpleNamespace(computedSymbols=symbols)


class SpeechTestCase(v115.NvdaTestCase):
	def setUp(self):
		super().setUp()
		self.module._localeSpeechSymbolProcessors = _Processors(self.module)
		self.dictionaries = []
		self.speechModule = types.ModuleType("speech.speech")
		self.speechModule.processText = self.nvdaProcessText
		self.nvdaOwn = self.speechModule.processText
		speechPackage = types.ModuleType("speech")
		speechPackage.speech = self.speechModule
		patcher = mock.patch.dict(sys.modules, {"speech": speechPackage, "speech.speech": self.speechModule})
		patcher.start()
		self.addCleanup(patcher.stop)
		driveLetters._logged.clear()
		self.addCleanup(driveLetters._logged.clear)

	def nvdaProcessText(self, locale, text, symbolLevel, normalize=False):
		"""NVDA 2026.2's speech.speech.processText: the speech dictionaries, then the symbols."""
		for pattern, replacement, type in self.dictionaries:
			compiled, replacement = dictionaryEntry(pattern, replacement, type)
			text = compiled.sub(replacement, text)
		text = v115.speak(self.module, text, symbolLevel, "en" if locale.startswith("en") else locale)
		return re.sub(r"[\0\r\n]", " ", text).strip()

	def say(self, text, level=MOST, locale="en_US"):
		"""What the synthesizer is given for ``text``, through whatever processText is in place now."""
		return self.speechModule.processText(locale, text, level)


class DriveLetterBeforeDictionariesTests(SpeechTestCase):
	def test_theTestersDriveWithADictionaryEntryForTheSmiley(self):
		self.dictionaries.append(SMILEY)
		self.assertIn("smiley", self.say(TESTERS_SPEECH), "NVDA alone")
		driveLetters.register()
		self.speechModule.processText = self.nvdaOwn
		self.assertIn("smiley", self.say(TESTERS_SPEECH), "1.15: the symbol rule never sees the \":)\"")
		driveLetters.unregister()
		self.assertTrue(driveLetters.register())
		self.assertTrue(driveLetters.isGuardingSpeech())
		said = self.say(TESTERS_SPEECH)
		self.assertEqual(v115.words(said), ["Data", "left", "paren", "D"], "JAWS: Data (D")
		self.assertNotIn("smiley", said)

	def test_withoutADictionaryEntryAsIn115(self):
		self.assertTrue(driveLetters.register())
		self.assertEqual(v115.words(self.say(TESTERS_SPEECH)), ["Data", "left", "paren", "D"])
		self.assertEqual(self.say(TESTERS_SPEECH, SOME).split(), ["Data", "(D"])
		self.assertEqual(v115.words(self.say(TESTERS_SPEECH, ALL)), ["Data", "left", "paren", "D", "colon", "right", "paren"], "at All, every symbol")

	def test_whereverADriveIsNamed(self):
		self.dictionaries.append(SMILEY)
		self.assertTrue(driveLetters.register())
		self.assertEqual(v115.words(self.say("Local Disk (C:)")), ["Local", "Disk", "left", "paren", "C"])
		self.assertEqual(v115.words(self.say("Data (D:) - File Explorer")), ["Data", "left", "paren", "D", "dash", "File", "Explorer"], "Alt+Tab")
		self.assertEqual(v115.words(self.say("Data (D:), 3 of 3")), ["Data", "left", "paren", "D", "3", "of", "3"])

	def test_everythingElseAsBefore(self):
		self.dictionaries.extend([SMILEY, EMOTICONS_SMILE])
		texts = ["Great :) thanks", ":)", "C:\\Windows", "(a:)", "(D: drive)", "Re: (Issue #4)", "Received 6:02 PM", "Data (D:"]
		levels = (NONE, SOME, MOST, ALL, CHAR)
		before = {(text, level): self.say(text, level) for text in texts for level in levels}
		self.assertTrue(driveLetters.register())
		after = {(text, level): self.say(text, level) for text in texts for level in levels}
		self.assertEqual(after, before)

	def test_atAllTheTextIsLeftForTheRule(self):
		self.dictionaries.append(SMILEY)
		self.assertTrue(driveLetters.register())
		self.assertIn("smiley", self.say(TESTERS_SPEECH, ALL), "NVDA's dictionaries and symbols have it, as before")
		self.assertIn("smiley", self.say(TESTERS_SPEECH, CHAR), "reading by character")

	def test_theLevelTheUserChoseForTheRule(self):
		self.assertTrue(driveLetters.register())
		user = self.module._symbolDictionaryDefinitions[-1]
		users = v115._Symbols()
		users.symbols[driveLetters.IDENTIFIER] = v115._Symbol(driveLetters.IDENTIFIER, None, None, MOST, None)
		original = v115._Definition._initSymbols
		with mock.patch.object(v115._Definition, "_initSymbols", lambda self, locale: users if self is user else original(self, locale)):
			self.assertEqual(v115.words(self.say(TESTERS_SPEECH)), ["Data", "left", "paren", "D", "colon", "right", "paren"], "set to most in NVDA's dialog")
			self.assertEqual(self.say(TESTERS_SPEECH, SOME).split(), ["Data", "(D"])

	def test_aLanguageWithoutTheRule(self):
		# NVDA has no symbols for Klingon, so it uses English ones (processSpeechSymbols), and the rule's level with them.
		self.assertTrue(driveLetters.register())
		self.assertEqual(driveLetters.leaveOut("tlh", TESTERS_SPEECH, MOST), "Data (D")
		self.assertEqual(driveLetters.leaveOut("tlh", TESTERS_SPEECH, ALL), TESTERS_SPEECH)


class SpeechGuardTests(SpeechTestCase):
	def test_turnedOffNvdaHasItsOwnBack(self):
		self.assertTrue(driveLetters.register())
		self.assertIsNot(self.speechModule.processText, self.nvdaOwn)
		self.assertIs(self.speechModule.processText.__wrapped__, self.nvdaOwn)
		driveLetters.unregister()
		self.assertIs(self.speechModule.processText, self.nvdaOwn)
		self.assertFalse(driveLetters.isGuardingSpeech())

	def test_registeredTwiceWrappedOnce(self):
		for _ in range(3):
			self.assertTrue(driveLetters.register())
		self.assertIs(self.speechModule.processText.__wrapped__, self.nvdaOwn)

	def test_nvdaReloadingItsSymbolsKeepsTheGuard(self):
		self.assertTrue(driveLetters.register())
		self.module.terminate()
		self.module.initialize()
		self.assertTrue(driveLetters.register())
		self.assertIn(driveLetters.DEFINITION_NAME, self.names())
		self.assertIs(self.speechModule.processText.__wrapped__, self.nvdaOwn, "still wrapped once")

	def test_anotherAddonsWrapperOverTheAssistants(self):
		self.dictionaries.append(SMILEY)
		self.assertTrue(driveLetters.register())
		ours = self.speechModule.processText

		@functools.wraps(ours)
		def otherAddon(*args, **kwargs):
			return ours(*args, **kwargs)

		self.speechModule.processText = otherAddon
		driveLetters.unregister()
		self.assertIs(self.speechModule.processText, otherAddon)
		self.assertIn("smiley", self.say(TESTERS_SPEECH), "the assistant's, still inside it, does nothing")
		self.assertTrue(driveLetters.register())
		self.assertIs(self.speechModule.processText, otherAddon, "not wrapped a second time")
		self.assertNotIn("smiley", self.say(TESTERS_SPEECH))

	def test_nvdaWithoutProcessTextKeepsTheSymbolRule(self):
		del self.speechModule.processText
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.assertTrue(driveLetters.register(), "the symbol rule is still in place")
		self.assertTrue(any("NVDA has no processText" in line for line in logged.output), logged.output)
		self.assertFalse(driveLetters.isGuardingSpeech())
		self.assertIn(driveLetters.DEFINITION_NAME, self.names())

	def test_aFailureLeavesTheTextToNvda(self):
		self.dictionaries.append(SMILEY)
		self.assertTrue(driveLetters.register())
		with mock.patch.object(driveLetters, "_LEAVE_OUT", types.SimpleNamespace(search=mock.Mock(side_effect=RuntimeError("broken")))):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				self.assertIn("smiley", self.say(TESTERS_SPEECH))
				self.assertIn("smiley", self.say(TESTERS_SPEECH))
		failures = [line for line in logged.output if "could not take a drive letter's" in line]
		self.assertEqual(len(failures), 1, logged.output)

	def test_withoutTheRuleLevelNvdaCanTellAllIsAssumed(self):
		self.assertTrue(driveLetters.register())
		del self.module._localeSpeechSymbolProcessors
		self.assertEqual(driveLetters.leaveOut("en_US", TESTERS_SPEECH, MOST), "Data (D")
		self.assertEqual(driveLetters.leaveOut("en_US", TESTERS_SPEECH, ALL), TESTERS_SPEECH)

	def test_whatTheLogSaysOnce(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			for _ in range(3):
				driveLetters.register()
				self.say(TESTERS_SPEECH)
				self.say("Local Disk (C:)")
		lines = [line for line in logged.output if "jawsMigrator" in line]
		self.assertEqual(sum("taken out before NVDA's speech dictionaries" in line for line in lines), 1, lines)
		self.assertEqual(sum("left out before NVDA's speech dictionaries" in line for line in lines), 1, lines)


if __name__ == "__main__":
	unittest.main()
