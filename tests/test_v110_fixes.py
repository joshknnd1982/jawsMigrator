# Unit tests for version 1.10, from a tester's report on version 1.8: "When navigating the web it says
# non breaking space", on profootballrumors.com. Web pages put a no-break space (U+00A0) between words, and
# JAWS's symbol file for Eloquence names it "non breaking space" at the Most punctuation level. Versions 1.0
# to 1.9 gave the name that level in NVDA's symbols, so the tester's NVDA, at its "most" level, said it
# wherever a page had one. A migration now gives JAWS's names for spaces and line breaks NVDA's "char" level
# (symbolMap), and a one-time repair does the same to the lines versions 1.0 to 1.9 wrote (symbolRepair).
# The imitation NVDA below reads symbol files and speaks text as NVDA 2026.2 does
# (characterProcessing.SpeechSymbols.load, SpeechSymbolProcessor, processSpeechSymbol and
# speech.processText), for simple symbols, with the lines of NVDA's own English symbols.dic that matter
# here. The speech is what the tester's log shows NVDA was given to say.
# Run: python -m unittest tests.test_v110_fixes -v

import codecs
import dataclasses
import os
import re
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import jawsMigrator  # noqa: E402
from jawsMigrator import jawsFiles, migrator, nvdaApply, numberSymbols, state, symbolMap, symbolRepair  # noqa: E402

NBSP = "\N{NO-BREAK SPACE}"
MOST = 200

#: What the tester's NVDA was given to say on profootballrumors.com (their log, 13:07:28 and 13:07:29).
TESTERS_SPEECH = [
	["The NFL recently informed its teams that tight end" + NBSP],
	["link", "Dae\u2019Quan Wright", NBSP, "and defensive tackle" + NBSP],
	["link", "Zxavian Harris", NBSP, "are "],
]

#: Lines of the American English section of JAWS 2026's eloq.sbl.
ELOQ_ENGLISH = (
	"[0x409]\r\n"
	"SynthPunctuation=1\r\n"
	"symbol1=! 11000000 exclaim!\r\n"
	"symbol3=# 11111101 number\r\n"
	"symbol12=, 11000000 comma,\r\n"
	"symbol100=u+001e 11110101 non breaking hyphen\r\n"
	"symbol101=u+00a0 11110101 non breaking space\r\n"
	"symbol193=u+000b 11110101 vertical tab\r\n"
	"symbol194=u+000c 11111101 page break\r\n"
)

#: NVDA 2026.2's locale\en\symbols.dic: its lines for spaces and line breaks, and a few others.
NVDA_ENGLISH = (
	"symbols:\r\n"
	"# Whitespace\r\n"
	"\\0\tblank\tchar\t# null\r\n"
	"\\t\ttab\r\n"
	"\\n\tline feed\tchar\r\n"
	"\\f\tpage break\tnone\r\n"
	"\\r\tcarriage return\tchar\r\n"
	" \tspace\tchar\r\n"
	f"{NBSP}\tspace\tchar\t# no-break space\r\n"
	"!\tbang\tall\r\n"
	"\\#\tnumber\tsome\r\n"
	",\tcomma\tall\talways\r\n"
	"-\tdash\tmost\talways\r\n"
	".\tdot\tsome\r\n"
)

#: What versions 1.0 to 1.9 wrote into symbols-en.dic from ELOQ_ENGLISH, with "JAWS's names for all punctuation symbols".
WRITTEN_BY_19 = (
	"symbols:\r\n"
	"!\texclaim\tall\talways\r\n"
	"\\#\tnumber\tsome\t-\r\n"
	",\tcomma\tall\talways\r\n"
	f"{NBSP}\tnon breaking space\tmost\t-\r\n"
	"\\v\tvertical tab\tmost\t-\r\n"
	"\\f\tpage break\tsome\t-\r\n"
)


def jawsSymbols(text=ELOQ_ENGLISH):
	return symbolMap.parseSymbols(jawsFiles.parseIni(text, keepRepeatedKeys=True).section("0x409"))


def migratedFile(folder, symbols=None):
	"""symbols-en.dic as a migration writes it now, with JAWS's names for every symbol."""
	path = os.path.join(folder, "symbols-en.dic")
	symbolMap.mergeIntoSymbolFile(path, symbols or jawsSymbols())
	with codecs.open(path, "r", "utf_8_sig") as stream:
		return stream.read()


class NvdaSymbols:
	"""NVDA 2026.2's symbols for English: its own, with the user's symbols file over them."""

	LEVELS = {"none": 0, "some": 100, "most": 200, "all": 300, "char": 1000}
	PRESERVES = {"never": 0, "always": 1, "norep": 2}
	ESCAPES = {"0": "\0", "t": "\t", "n": "\n", "r": "\r", "f": "\f", "v": "\v", "#": "#", "\\": "\\"}

	def __init__(self, userText=""):
		# SpeechSymbolProcessor: the user's symbols first; a field they leave out ("-") comes from NVDA's.
		computed = {}
		for source in (self.load(userText), self.load(NVDA_ENGLISH)):
			for identifier, fields in source.items():
				symbol = computed.setdefault(identifier, [None, None, None])
				for index, value in enumerate(fields):
					if symbol[index] is None:
						symbol[index] = value
		self.symbols = {
			identifier: (replacement, 300 if level is None else level, 0 if preserve is None else preserve)
			for identifier, (replacement, level, preserve) in computed.items()
			if replacement is not None
		}
		characters = "[%s]" % re.escape("".join(identifier for identifier in self.symbols if len(identifier) == 1))
		multiple = sorted((identifier for identifier in self.symbols if len(identifier) > 1), key=len, reverse=True)
		simple = "|".join([re.escape(identifier) for identifier in multiple] + [characters])
		self.regexp = re.compile(rf"(?P<rstripSpace>  +$)|(?P<repeated>(?P<repTmp>{characters})(?P=repTmp){{3,}})|(?P<simple>{simple})")

	@classmethod
	def load(cls, text):
		"""SpeechSymbols.load for a user's symbols file: ``{symbol: [replacement, level, preserve]}``."""
		symbols = {}
		inSymbols = False
		for line in text.splitlines(keepends=True):
			if line.isspace() or line.startswith("#"):
				continue
			line = line.rstrip("\r\n")
			if line == "symbols:":
				inSymbols = True
				continue
			fields = line.split("\t")
			if fields[-1].startswith("#"):
				fields.pop()
			if not inSymbols or len(fields) < 2 or not fields[0]:
				continue
			identifier = fields[0]
			if identifier.startswith("\\") and len(identifier) >= 2:
				identifier = cls.ESCAPES.get(identifier[1], identifier[1]) + identifier[2:]
			try:
				level = None if len(fields) < 3 or fields[2] == "-" else cls.LEVELS[fields[2]]
				preserve = None if len(fields) < 4 or fields[3] == "-" else cls.PRESERVES[fields[3]]
			except KeyError:
				continue
			symbols[identifier] = [None if fields[1] == "-" else fields[1], level, preserve]
		return symbols

	def _replace(self, match, level):
		if match.lastgroup == "rstripSpace":
			return ""
		text = match.group()
		if match.lastgroup == "repeated":
			replacement, symbolLevel, preserve = self.symbols[text[0]]
			if level >= symbolLevel:
				return f"  {len(text)} {replacement} "
			return text if preserve in (1, 2) else " "
		replacement, symbolLevel, preserve = self.symbols[text]
		suffix = text if preserve == 1 or (preserve == 2 and level < symbolLevel) else " "
		if level >= symbolLevel and replacement:
			return f" {replacement}{suffix}"
		return suffix

	def speak(self, sequence, level=MOST):
		"""What speech.speak sends the synthesizer for each piece of text (speech.processText)."""
		return [re.sub("[\0\r\n]", " ", self.regexp.sub(lambda match: self._replace(match, level), text)).strip() for text in sequence]

	def readCharacter(self, character):
		"""What NVDA says for a character read on its own (characterProcessing.processSpeechSymbol)."""
		return self.symbols[character][0] if character in self.symbols else character


class TemporaryFolder(unittest.TestCase):
	def setUp(self):
		self.folder = tempfile.mkdtemp(prefix="jawsMigrator-v110-")
		self.addCleanup(shutil.rmtree, self.folder, True)

	def write(self, name, text, encoding="utf_8_sig"):
		path = os.path.join(self.folder, name)
		with open(path, "w", encoding=encoding, newline="") as stream:
			stream.write(text)
		return path

	def read(self, path):
		with open(path, encoding="utf_8_sig", newline="") as stream:
			return stream.read()


class JawsNamesForReadingCharactersTests(TemporaryFolder):
	"""A migration gives JAWS's names for spaces and line breaks NVDA's "char" level; other symbols keep JAWS's level."""

	def test_levels(self):
		symbols = jawsSymbols()
		levels = {character: symbol.nvdaLevel for character, symbol in symbols.items()}
		self.assertEqual(levels[NBSP], "char", "JAWS's flags say Most; between words it is a space")
		self.assertEqual(levels["\v"], "char")
		self.assertEqual(levels["\f"], "some", "a page break is said, as JAWS and NVDA both do")
		self.assertEqual((levels["!"], levels["#"], levels[","]), ("all", "some", "all"), "other symbols keep JAWS's level")

	def test_lines_written(self):
		text = migratedFile(self.folder)
		lines = text.splitlines()
		self.assertIn(f"{NBSP}\tnon breaking space\tchar\t-", lines)
		self.assertIn("\\v\tvertical tab\tchar\t-", lines)
		self.assertIn("\\f\tpage break\tsome\t-", lines)
		self.assertIn("!\texclaim\tall\talways", lines)
		self.assertIn("\\#\tnumber\tsome\t-", lines)

	def test_migrating_again_replaces_the_line_19_wrote(self):
		path = self.write("symbols-en.dic", WRITTEN_BY_19)
		symbolMap.mergeIntoSymbolFile(path, jawsSymbols())
		lines = self.read(path).splitlines()
		self.assertIn(f"{NBSP}\tnon breaking space\tchar\t-", lines)
		self.assertNotIn(f"{NBSP}\tnon breaking space\tmost\t-", lines)

	def test_spaces_and_line_breaks(self):
		for character in (NBSP, " ", "\u202f", "\u2009", "\u3000", "\n", "\r", "\v", "\x85", "\u2028", "\u2029"):
			self.assertTrue(symbolMap.isSpaceOrLineBreak(character), repr(character))
		for character in ("\t", "\f", "\x1e", "\x1f", "\u200b", "\xad", "a", "#", "", NBSP * 2):
			self.assertFalse(symbolMap.isSpaceOrLineBreak(character), repr(character))

	def test_nvda_reads_escaped_symbols_back(self):
		for character in ("\v", "\r", "\n", "\0", "\t", "\f", "#", "\\", NBSP, "!"):
			line = symbolMap.symbolLine(character, symbolMap.JawsSymbol(character, "11110101", "name"))
			self.assertEqual(symbolMap.symbolOf(line.split("\t")[0]), character)


class NvdaSpeechTests(TemporaryFolder):
	"""What NVDA says of the tester's web page with the symbols a migration wrote."""

	def spoken(self, userText, level=MOST):
		nvda = NvdaSymbols(userText)
		return [nvda.speak(sequence, level) for sequence in TESTERS_SPEECH]

	def test_version_19_said_non_breaking_space(self):
		# The tester's report: NVDA at the "most" level, with the line versions 1.0 to 1.9 wrote.
		spoken = self.spoken(WRITTEN_BY_19)
		self.assertEqual(spoken[1], ["link", "Dae\u2019Quan Wright", "non breaking space", "and defensive tackle non breaking space"])
		self.assertEqual(spoken[0], ["The NFL recently informed its teams that tight end non breaking space"])

	def test_now_a_pause_between_words(self):
		userText = migratedFile(self.folder)
		spoken = self.spoken(userText)
		self.assertEqual(spoken[0], ["The NFL recently informed its teams that tight end"])
		self.assertEqual(spoken[1], ["link", "Dae\u2019Quan Wright", "", "and defensive tackle"])
		self.assertEqual(spoken[2], ["link", "Zxavian Harris", "", "are"])
		self.assertEqual(spoken, self.spoken(""), "exactly what NVDA says without the migrated symbols")
		for level in (0, 100, 200, 300):
			self.assertNotIn("non breaking space", str(self.spoken(userText, level)), level)

	def test_reading_by_character_keeps_jaws_name(self):
		nvda = NvdaSymbols(migratedFile(self.folder))
		self.assertEqual(nvda.readCharacter(NBSP), "non breaking space")
		self.assertEqual(nvda.readCharacter("\v"), "vertical tab")
		self.assertEqual(NvdaSymbols().readCharacter(NBSP), "space", "NVDA's own name, without a migration")

	def test_a_row_of_no_break_spaces(self):
		text = "Scores" + NBSP * 4 + "Final"
		self.assertEqual(NvdaSymbols(WRITTEN_BY_19).speak([text]), ["Scores  4 non breaking space Final"])
		self.assertEqual(NvdaSymbols(migratedFile(self.folder)).speak([text]), ["Scores Final"])

	def test_vertical_tab(self):
		text = "First line\vSecond line"
		self.assertEqual(NvdaSymbols(WRITTEN_BY_19).speak([text]), ["First line vertical tab Second line"])
		self.assertEqual(NvdaSymbols(migratedFile(self.folder)).speak([text]), ["First line Second line"])

	def test_punctuation_still_said(self):
		nvda = NvdaSymbols(migratedFile(self.folder))
		self.assertEqual(nvda.speak(["Chapter 1\fChapter 2"]), ["Chapter 1 page break Chapter 2"])
		self.assertEqual(nvda.speak(["Wow!"], 300), ["Wow exclaim!"])
		self.assertEqual(nvda.speak(["Item #3"]), ["Item  number 3"])


class RepairTextTests(unittest.TestCase):
	"""The lines versions 1.0 to 1.9 wrote are read for characters only; nothing else changes."""

	names = {character: {name.casefold() for name in known} for character, known in symbolRepair.JAWS_NAMES.items()}

	def test_the_testers_file(self):
		repaired, changed = symbolRepair.repairText(WRITTEN_BY_19, self.names)
		self.assertEqual(changed, [(NBSP, "non breaking space", "most"), ("\v", "vertical tab", "most")])
		self.assertEqual(
			repaired,
			WRITTEN_BY_19.replace(f"{NBSP}\tnon breaking space\tmost\t-", f"{NBSP}\tnon breaking space\tchar\t-").replace("\\v\tvertical tab\tmost\t-", "\\v\tvertical tab\tchar\t-"),
		)
		self.assertEqual(symbolRepair.repairText(repaired, self.names), (repaired, []), "repairing twice changes nothing")
		self.assertEqual(NvdaSymbols(repaired).speak(TESTERS_SPEECH[1]), ["link", "Dae\u2019Quan Wright", "", "and defensive tackle"])

	def test_saved_again_by_nvda(self):
		# NVDA's Punctuation/symbol pronunciation dialog saves a symbol without its "-" fields, and with its display name.
		for line, expected in (
			(f"{NBSP}\tnon breaking space\tmost", f"{NBSP}\tnon breaking space\tchar"),
			(f"{NBSP}\tnon breaking space\tmost\t-\t# no-break space", f"{NBSP}\tnon breaking space\tchar\t-\t# no-break space"),
			(f"{NBSP}\tnon breaking space\tall\tnever", f"{NBSP}\tnon breaking space\tchar\tnever"),
		):
			self.assertEqual(symbolRepair.repairText(f"symbols:\n{line}\n", self.names)[0], f"symbols:\n{expected}\n", line)

	def test_other_languages(self):
		text = f"symbols:\r\n{NBSP}\tespace insécable\tmost\t-\r\n\\v\ttabulation verticale\tmost\t-\r\n\\r\tkoniec akapitu\tall\t-\r\n{NBSP}\tGeschütztes Leerzeichen\tmost\t-\r\n"
		repaired, changed = symbolRepair.repairText(text, self.names)
		self.assertEqual(len(changed), 4)
		self.assertEqual(repaired, text.replace("\tmost\t", "\tchar\t").replace("\tall\t", "\tchar\t"))

	def test_the_users_own_lines_stay(self):
		text = (
			"complexSymbols:\r\n"
			f"{NBSP} run\t{NBSP}+\r\n"
			"\r\n"
			"symbols:\r\n"
			"# My symbols\r\n"
			f"{NBSP}\thard space\tmost\t-\r\n"
			f"{NBSP}\tnon breaking space\tchar\t-\r\n"
			f"{NBSP}\tnon breaking space\r\n"
			f"{NBSP}\tnon breaking space\t-\t-\r\n"
			f"{NBSP}\tnon breaking space\tmost \t-\r\n"
			f"{NBSP} run\tnon breaking space\tmost\r\n"
			"\\f\tpage break\tsome\t-\r\n"
			"\\t\ttab\tmost\t-\r\n"
			"\\#\tnumber\tsome\t-\r\n"
			"\u200b\tzero width space\tmost\t-\r\n"
		)
		self.assertEqual(symbolRepair.repairText(text, self.names), (text, []))

	def test_before_the_symbols_section(self):
		text = f"{NBSP}\tnon breaking space\tmost\t-\r\nsymbols:\r\n!\tbang\tall\r\n"
		self.assertEqual(symbolRepair.repairText(text, self.names), (text, []), "NVDA reads no symbol before symbols:")

	def test_any_name_is_a_candidate(self):
		text = f"symbols:\n{NBSP}\thard space\tmost\t-\n"
		self.assertEqual(symbolRepair.repairText(text, None)[1], [(NBSP, "hard space", "most")])
		self.assertEqual(symbolRepair.repairText(text, self.names)[1], [])

	def test_announcement(self):
		self.assertEqual(
			symbolRepair.announcement([("symbols-en.dic", NBSP, "non breaking space", "most")]),
			'JAWS Migration Assistant: NVDA no longer says "non breaking space" as it reads, only when you read by character. '
			"The earlier migration had made NVDA say it wherever it was in the text. NVDA's settings were backed up first.",
		)
		message = symbolRepair.announcement([("symbols-en.dic", NBSP, "non breaking space", "most"), ("symbols-en.dic", "\v", "vertical tab", "most"), ("symbols-de.dic", NBSP, "Non breaking space", "most")])
		self.assertIn('says "non breaking space" or "vertical tab" as it reads', message)
		self.assertIn("say them wherever they were", message)


class RepairFilesTests(TemporaryFolder):
	names = RepairTextTests.names

	def test_repairs_only_the_assistants_lines(self):
		english = self.write("symbols-en.dic", WRITTEN_BY_19)
		german = self.write("symbols-de.dic", f"symbols:\r\n{NBSP}\tmein Leerzeichen\tmost\t-\r\n")
		french = os.path.join(self.folder, "symbols-fr.dic")
		with open(french, "wb") as stream:
			stream.write(b"symbols:\r\n\xc2\xa0\tespace ins\xe9cable\tmost\t-\r\n")
		other = self.write("gestures.ini", f"{NBSP}\tnon breaking space\tmost\t-\r\n")
		before = {path: os.path.getmtime(path) for path in (german, french, other)}
		self.assertTrue(symbolRepair.needsRepair(self.folder, self.names))
		logged = []
		result = symbolRepair.repairSymbolFiles(self.folder, self.names, logged.append)
		self.assertEqual(result.files, [english])
		self.assertEqual(result.lines, [("symbols-en.dic", NBSP, "non breaking space", "most"), ("symbols-en.dic", "\v", "vertical tab", "most")])
		self.assertEqual(result.failed, [])
		self.assertIn(f"{NBSP}\tnon breaking space\tchar\t-\r\n", self.read(english))
		with open(english, "rb") as stream:
			self.assertTrue(stream.read().startswith(codecs.BOM_UTF8 + b"symbols:\r\n"), "as NVDA writes it: a BOM and Windows line endings")
		self.assertEqual({path: os.path.getmtime(path) for path in before}, before, "only files with the assistant's lines are written")
		self.assertTrue(any('U+00A0 "non breaking space" was at the "most" level' in line for line in logged), logged)
		self.assertTrue(any("symbols-fr.dic was left as it is" in line for line in logged), "a file that isn't UTF-8 is never written back")
		self.assertFalse(symbolRepair.needsRepair(self.folder, self.names))
		self.assertTrue(symbolRepair.needsRepair(self.folder), "the user's own name for the no-break space may still be one")

	def test_no_files(self):
		self.assertEqual(symbolRepair.symbolFiles(os.path.join(self.folder, "missing")), [])
		self.assertFalse(symbolRepair.needsRepair(self.folder))
		self.assertEqual(symbolRepair.repairSymbolFiles(self.folder, self.names).files, [])


class JawsNamesTests(TemporaryFolder):
	"""JAWS's names come from JAWS 2026's own files, and from the JAWS symbol files on this computer."""

	def installation(self):
		shared = os.path.join(self.folder, "ProgramData", "SETTINGS")
		user = os.path.join(self.folder, "AppData", "Settings")
		os.makedirs(os.path.join(user, "enu"))
		os.makedirs(shared)
		with open(os.path.join(shared, "eloq.sbl"), "w", encoding="utf-8") as stream:
			stream.write(ELOQ_ENGLISH)
		with open(os.path.join(user, "enu", "eloq.sbl"), "w", encoding="utf-8") as stream:
			stream.write(ELOQ_ENGLISH.replace("11110101 non breaking space", "11110101 Hard Space"))
		return types.SimpleNamespace(sharedSettingsDir=shared, userSettingsDir=user)

	def test_names(self):
		names = symbolRepair.jawsNames([self.installation()])
		self.assertIn("hard space", names[NBSP], "the user's own name in their JAWS settings")
		self.assertIn("non breaking space", names[NBSP])
		self.assertIn("espace insécable", names[NBSP], "JAWS 2026's names in every language")
		self.assertIn("vertical tab", names["\v"])
		self.assertNotIn("\f", names, "a page break keeps its level")
		self.assertNotIn("!", names)

	def test_without_jaws(self):
		names = symbolRepair.jawsNames([])
		self.assertEqual(set(names), {NBSP, "\v", "\r"})
		with mock.patch("jawsMigrator.jawsDetect.findJawsInstallations", side_effect=OSError("no registry")), mock.patch.object(symbolRepair.debugLog, "error"):
			self.assertEqual(symbolRepair.jawsNames(), names)


class RepairOnceTests(TemporaryFolder):
	"""repairOnce: once, after a backup, then NVDA reads its symbols again; done() is always called once."""

	def setUp(self):
		super().setUp()
		self.state = {"lastMigration": {"when": "2026-09-20T18:00:00"}}
		self.done = []
		self.announced = []
		self.backups = []
		self.reloaded = []

		class SyncThread:
			def __init__(self, target=None, name=None, daemon=None):
				self.target = target

			def start(self):
				self.target()

		def backupFirst(reason):
			self.backups.append(reason)
			return types.SimpleNamespace(path="backup")

		for patcher in (
			mock.patch.object(state, "get", lambda key: self.state.get(key, state.DEFAULTS.get(key))),
			mock.patch.object(state, "set", lambda key, value, persist=True: self.state.__setitem__(key, value)),
			mock.patch.object(symbolRepair.nvdaEnv, "configDir", lambda: self.folder),
			mock.patch.object(symbolRepair.nvdaEnv, "shouldWriteToDisk", lambda: True),
			mock.patch.object(symbolRepair, "jawsNames", lambda: RepairTextTests.names),
			mock.patch.object(migrator, "_backupFirst", backupFirst),
			mock.patch.object(nvdaApply, "reloadSymbols", lambda: self.reloaded.append(True)),
			mock.patch.object(symbolRepair.debugLog, "note", lambda message: None),
			mock.patch.object(symbolRepair.debugLog, "error", lambda message, exc_info=True: None),
			mock.patch("threading.Thread", SyncThread),
			mock.patch("wx.CallAfter", lambda function, *args: function(*args)),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def run_once(self):
		symbolRepair.repairOnce(self.announced.append, lambda: self.done.append(True))

	def test_repairs_once(self):
		path = self.write("symbols-en.dic", WRITTEN_BY_19)
		self.run_once()
		self.assertIn(f"{NBSP}\tnon breaking space\tchar\t-\r\n", self.read(path))
		self.assertEqual(self.backups, ["Before repairing the punctuation symbols of an earlier migration"])
		self.assertEqual((self.reloaded, self.state[symbolRepair.STATE_KEY], self.done), ([True], symbolRepair.REPAIR_VERSION, [True]))
		self.assertEqual(len(self.announced), 1)
		self.assertIn('no longer says "non breaking space" or "vertical tab"', self.announced[0])
		self.run_once()
		self.assertEqual((len(self.announced), len(self.backups), self.reloaded, self.done), (1, 1, [True], [True, True]))

	def test_nothing_to_repair(self):
		self.write("symbols-en.dic", migratedFile(os.path.join(self.folder, "new")))
		self.run_once()
		self.assertEqual((self.state[symbolRepair.STATE_KEY], self.backups, self.announced, self.reloaded, self.done), (1, [], [], [], [True]))

	def test_the_users_own_name_stays(self):
		text = f"symbols:\r\n{NBSP}\thard space\tmost\t-\r\n"
		path = self.write("symbols-en.dic", text)
		self.run_once()
		self.assertEqual(self.read(path), text)
		self.assertEqual((self.state[symbolRepair.STATE_KEY], self.backups, self.announced, self.done), (1, [], [], [True]))

	def test_no_migration_on_this_computer(self):
		self.state["lastMigration"] = {}
		path = self.write("symbols-en.dic", WRITTEN_BY_19)
		self.run_once()
		self.assertEqual(self.read(path), WRITTEN_BY_19)
		self.assertEqual((self.state[symbolRepair.STATE_KEY], self.backups, self.done), (1, [], [True]))

	def test_failed_backup_repairs_nothing(self):
		path = self.write("symbols-en.dic", WRITTEN_BY_19)

		def fail(reason):
			raise OSError("disk full")

		with mock.patch.object(migrator, "_backupFirst", fail):
			self.run_once()
		self.assertEqual(self.read(path), WRITTEN_BY_19)
		self.assertNotIn(symbolRepair.STATE_KEY, self.state, "tried again next time NVDA starts")
		self.assertEqual((self.announced, self.reloaded, self.done), ([], [], [True]))

	def test_nothing_written_when_nvda_must_not_write(self):
		path = self.write("symbols-en.dic", WRITTEN_BY_19)
		with mock.patch.object(symbolRepair.nvdaEnv, "shouldWriteToDisk", lambda: False):
			self.run_once()
		self.assertEqual(self.read(path), WRITTEN_BY_19)
		self.assertEqual((self.backups, self.done), ([], [True]))
		self.assertNotIn(symbolRepair.STATE_KEY, self.state)


@dataclasses.dataclass(frozen=True, kw_only=True)
class _Definition:
	name: str
	path: str
	source: str = "builtin"
	allowComplexSymbols: bool = False
	mandatory: bool = False


def _characterProcessing():
	"""NVDA's characterProcessing, as far as its list of symbol dictionaries goes."""
	module = types.ModuleType("characterProcessing")
	module.SymbolDictionaryDefinition = _Definition
	module.SymbolLevel = types.SimpleNamespace(ALL=300)
	module.SYMPRES_NOREP = 2
	module.clearSpeechSymbols = lambda: None
	module._symbolDictionaryDefinitions = []

	def initialize():
		module._symbolDictionaryDefinitions.extend([_Definition(name="cldr", path="{locale}"), _Definition(name="builtin", path="{locale}"), _Definition(name="user", path="{locale}", source="user")])

	module.initialize = initialize
	module.terminate = module._symbolDictionaryDefinitions.clear
	initialize()
	return module


class ReloadSymbolsTests(unittest.TestCase):
	"""NVDA reads the repaired file again, and JAWS's rule for times stays."""

	def names(self, module):
		return [definition.name for definition in module._symbolDictionaryDefinitions]

	def test_rule_for_times_stays(self):
		module = _characterProcessing()
		with mock.patch.dict(sys.modules, {"characterProcessing": module}):
			try:
				self.assertTrue(numberSymbols.register())
				nvdaApply.reloadSymbols()
				self.assertEqual(self.names(module), ["cldr", "builtin", numberSymbols.DEFINITION_NAME, "user"])
			finally:
				numberSymbols.unregister()
			nvdaApply.reloadSymbols()
			self.assertEqual(self.names(module), ["cldr", "builtin", "user"], "without a migration, no rule comes back")


class StartupTests(unittest.TestCase):
	def test_repair_runs_after_nvda_starts(self):
		plugin = object.__new__(jawsMigrator.GlobalPlugin)
		plugin._busy = False
		plugin._repairTimer = None
		with mock.patch.object(jawsMigrator.GlobalPlugin, "_runRepairs") as runRepairs:
			plugin._repairVoices()
		steps = runRepairs.call_args[0][0]
		self.assertIn(symbolRepair.repairOnce, [repair for _what, repair in steps])

	def test_kept_in_the_assistants_settings(self):
		self.assertEqual(state.DEFAULTS[symbolRepair.STATE_KEY], 0, "state.json keeps only the keys it knows")


if __name__ == "__main__":
	unittest.main()
