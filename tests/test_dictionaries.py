# Unit tests for JAWS dictionary rules, JAWS symbol files and the INI reader under them.
# They use small made-up JAWS lines, so they run anywhere.
# Run from the repository root: python -m unittest tests.test_dictionaries -v

import codecs
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import dictMap, jawsFiles, symbolMap  # noqa: E402


def convert(jdfText, language=0x0409):
	"""Convert the rules of a made-up ``.jdf``; returns the DictConversion."""
	return dictMap.convertRules(jawsFiles.parseJdf(jdfText), "Default.jdf", language)


def onlyEntry(testCase, jdfText):
	conversion = convert(jdfText)
	testCase.assertEqual(conversion.skipped, [], [skipped.reason for skipped in conversion.skipped])
	testCase.assertEqual(len(conversion.entries), 1)
	return conversion.entries[0]


def nvdaSpeaks(entry, text):
	"""What NVDA 2026.2 makes of ``text`` with one converted entry.

	The same steps as ``speechDictHandler.types.SpeechDictEntry``. NVDA compiles whole-word
	entries with the ``regex`` module, which gives the same results as ``re`` for this text.
	"""
	flags = re.UNICODE | (0 if entry.caseSensitive else re.IGNORECASE)
	if entry.type == dictMap.TYPE_REGEXP:
		pattern = entry.pattern
		replacement = entry.replacement
	else:
		pattern = re.escape(entry.pattern)
		if entry.type == dictMap.TYPE_WORD:
			pattern = rf"\b{pattern}\b"
		replacement = entry.replacement.replace("\\", "\\\\")
	return re.compile(pattern, flags).sub(replacement, text)


def nvdaLoadsDicLine(line):
	"""The ``(pattern, replacement, caseSensitive, type)`` NVDA reads back from one line of a ``.dic`` file."""
	fields = line.rstrip("\r\n").split("\t")
	if len(fields) != 4:
		return None
	return fields[0].replace(r"\#", "#"), fields[1].replace(r"\#", "#"), bool(int(fields[2])), int(fields[3])


class WholeWordTests(unittest.TestCase):
	"""Finding 2: a rule with a letter or digit at only one end matches whole words there."""

	def test_abbreviation_does_not_change_other_words(self):
		entry = onlyEntry(self, ",St.,Street,*,*,*,0,0,\n")
		self.assertEqual(entry.type, dictMap.TYPE_REGEXP)
		self.assertEqual(entry.pattern, r"\bSt\.")
		self.assertEqual(nvdaSpeaks(entry, "The first. Last. Main St. is most."), "The first. Last. Main Street is most.")
		self.assertEqual(nvdaSpeaks(entry, "st. Louis"), "Street Louis")

	def test_colon_after_letters(self):
		entry = onlyEntry(self, ",AN:,account number,0x09,*,*,0,0,\n")
		self.assertEqual(nvdaSpeaks(entry, "Plan: then AN: done"), "Plan: then account number done")

	def test_symbol_before_letters(self):
		entry = onlyEntry(self, ",.ini,dot inny,*,*,*,0,0,\n")
		self.assertEqual(entry.pattern, r"\.ini\b")
		self.assertEqual(nvdaSpeaks(entry, "setup.ini and obj.initialize()"), "setupdot inny and obj.initialize()")

	def test_case_sensitive_rule_stays_case_sensitive(self):
		entry = onlyEntry(self, ",Mr.,Mister,*,*,*,1,0,\n")
		self.assertTrue(entry.caseSensitive)
		self.assertEqual(nvdaSpeaks(entry, "Mr. Smith, mr. Jones, HMr. X"), "Mister Smith, mr. Jones, HMr. X")

	def test_backslash_in_replacement_is_spoken(self):
		entry = onlyEntry(self, ",St.,S\\t,*,*,*,0,0,\n")
		self.assertEqual(nvdaSpeaks(entry, "Main St."), "Main S\\t")

	def test_other_rules_unchanged(self):
		lines = [entry.asLine() for entry in convert(".reposition*.re position.*.*.*.0.0.\n.<<.double left.*.*.*.0.0.\n.vfo.v f o.*.*.*.0.0.\n,u.s. bank,u s bank,*,*,*,0,0,\n").entries]
		self.assertEqual(lines, ["\\breposition\tre position\t0\t1", "<<\tdouble left\t0\t0", "vfo\tv f o\t0\t2", "u.s. bank\tu s bank\t0\t2"])

	def test_survives_nvda_dictionary_file(self):
		for jdf in (",St.,Street,*,*,*,0,0,\n", ",#1.,number one,*,*,*,0,0,\n", ",No.#,number sign,*,*,*,0,0,\n"):
			entry = onlyEntry(self, jdf)
			self.assertEqual(nvdaLoadsDicLine(entry.asLine()), (entry.pattern, entry.replacement, entry.caseSensitive, entry.type), jdf)
			re.compile(entry.pattern)


class AsteriskTests(unittest.TestCase):
	"""Finding 3: a word made only of asterisks is the asterisks themselves, never an empty pattern."""

	def test_asterisks_only(self):
		entry = onlyEntry(self, ".***.stars.*.*.*.0.0.\n")
		self.assertEqual((entry.pattern, entry.type), ("***", dictMap.TYPE_ANYWHERE))
		self.assertEqual(nvdaSpeaks(entry, "hello"), "hello")
		self.assertEqual(nvdaSpeaks(entry, "one *** two"), "one stars two")
		entry = onlyEntry(self, ".*.star.*.*.*.0.0.\n")
		self.assertEqual((entry.pattern, entry.type), ("*", dictMap.TYPE_ANYWHERE))
		self.assertEqual(nvdaSpeaks(entry, "a*b"), "astarb")

	def test_no_pattern_matches_nothing(self):
		jdf = ".***.x.*.*.*.0.0.\n.**.x.*.*.*.0.0.\n.*.x.*.*.*.0.0.\n.a*.x.*.*.*.0.0.\n.*a.x.*.*.*.0.0.\n.a*b.x.*.*.*.0.0.\n.a**b.x.*.*.*.0.0.\n,*.a*,x,*,*,*,0,0,\n,St.,x,*,*,*,0,0,\n"
		for entry in convert(jdf).entries:
			pattern = entry.pattern if entry.type == dictMap.TYPE_REGEXP else re.escape(entry.pattern)
			self.assertTrue(entry.pattern, entry)
			self.assertFalse([match for match in re.finditer(pattern, "hello, world") if match.start() == match.end()], entry.pattern)


class ReplacementTests(unittest.TestCase):
	"""Finding 10: a replacement of spaces silences the word; only an empty one means "sound or language"."""

	def test_space_replacement_kept(self):
		entry = onlyEntry(self, ".\u25ba. .*.*.*.0.1.\n")
		self.assertEqual((entry.pattern, entry.replacement, entry.type), ("\u25ba", " ", dictMap.TYPE_ANYWHERE))
		self.assertEqual(nvdaSpeaks(entry, "Menu \u25ba File"), "Menu   File")
		self.assertEqual(nvdaLoadsDicLine(entry.asLine()), ("\u25ba", " ", False, 0))

	def test_empty_replacement_and_sounds_still_skipped(self):
		conversion = convert(".chime..0x09.*.*.0.0.\n,bell, ,*,*,*,0,0,bell.wav,\n,gong,,*,*,*,0,0,gong.wav,\n")
		self.assertEqual(conversion.entries, [])
		reasons = [skipped.reason for skipped in conversion.skipped]
		self.assertIn("only changes the sound or language", reasons[0])
		self.assertIn("bell.wav", reasons[1])
		self.assertIn("gong.wav", reasons[2])


class CharacterCodeTests(unittest.TestCase):
	"""Finding 11: JAWS names characters by decimal code in dictionary rules."""

	def test_decoding(self):
		decode = jawsFiles.decodeCharacterCodes
		self.assertEqual(decode(r"\145"), "\u2018")
		self.assertEqual(decode(r"\146"), "\u2019")
		self.assertEqual(decode(r"\150"), "\u2013")
		self.assertEqual(decode(r"\8211"), "\u2013")
		self.assertEqual(decode(r"\189"), "\u00bd")
		self.assertEqual(decode(r"\136\128\137"), "\u02c6\u20ac\u2030")
		self.assertEqual(decode(r"\129"), "\x81")
		self.assertEqual(decode(r"x\65y"), "xAy")

	def test_backslashes_that_are_not_codes(self):
		decode = jawsFiles.decodeCharacterCodes
		for text in (r"C:\Windows", "end\\", r"\u2013", r"\0", r"\55296", r"\1114112", "\\" + "9" * 5000, "\\\u0661\u0662"):
			self.assertEqual(decode(text), text)

	def test_word_and_replacement_decoded(self):
		rules = jawsFiles.parseJdf(".\\150.\\8212.0x09.Eloquence Software.*.0.0.\n")
		self.assertEqual((rules[0].word, rules[0].replacement, rules[0].language, rules[0].synthesizer), ("\u2013", "\u2014", "0x09", "Eloquence Software"))

	def test_jaws_quote_rules(self):
		conversion = convert(".\\145.'.0x09.*.*.0.0.\n.\\8217.'.0x09.*.*.0.0.\n")
		self.assertEqual([entry.pattern for entry in conversion.entries], ["\u2018", "\u2019"])
		self.assertEqual(nvdaSpeaks(conversion.entries[0], "\u2018quoted"), "'quoted")

	def test_fractions_are_symbols_and_letters_whole_words(self):
		entry = onlyEntry(self, ".\\189.one half.0x09.*.*.0.0.\n")
		self.assertEqual((entry.pattern, entry.type), ("½", dictMap.TYPE_ANYWHERE))
		self.assertEqual(nvdaSpeaks(entry, "Add 1½ cups"), "Add 1one half cups")
		entry = onlyEntry(self, ".\\224.eigh grave.0x09.*.*.0.0.\n")
		self.assertEqual((entry.pattern, entry.type), ("à", dictMap.TYPE_WORD))
		self.assertEqual(nvdaSpeaks(entry, "à la carte, voilà"), "eigh grave la carte, voilà")

	def test_codes_for_tabs_and_line_breaks_skipped(self):
		conversion = convert(".a\\9b.x.*.*.*.0.0.\n.c.line\\10two.*.*.*.0.0.\n.d.x\\13.*.*.*.0.0.\n")
		self.assertEqual(conversion.entries, [])
		self.assertEqual(len(conversion.skipped), 3)
		self.assertTrue(all("tab or a line break" in skipped.reason for skipped in conversion.skipped))


class RepeatedSymbolKeyTests(unittest.TestCase):
	"""Finding 14: symbol files keep every line, other INI files read as before."""

	SBL = "[0x415]\nsymbol1=U+000b 11010101 pionowy tab\nsymbol2=! 11000000 wykrzyknik!\nsymbol1=U+000b 11000000 pionowy tab\nsymbol2=U+22 11110101 cudzys\u0142\u00f3w\n"

	def test_plain_read_keeps_last_value_per_key(self):
		section = jawsFiles.parseIni(self.SBL).section("0x415")
		self.assertIsNone(section.lines)
		self.assertEqual(section.allItems(), section.items())
		self.assertEqual(section.items(), [("symbol1", "U+000b 11000000 pionowy tab"), ("symbol2", "U+22 11110101 cudzys\u0142\u00f3w")])
		self.assertEqual(set(symbolMap.parseSymbols(section)), {'"', "\x0b"})

	def test_every_symbol_line_kept_in_file_order(self):
		section = jawsFiles.parseIni(self.SBL, keepRepeatedKeys=True).section("0x415")
		self.assertEqual([key for key, _value in section.allItems()], ["symbol1", "symbol2", "symbol1", "symbol2"])
		self.assertEqual(section.get("symbol2"), "U+22 11110101 cudzys\u0142\u00f3w")
		symbols = symbolMap.parseSymbols(section)
		self.assertEqual(set(symbols), {"!", '"', "\x0b"})
		# The later line for a character wins.
		self.assertEqual(symbols["\x0b"].flags, "11000000")

	def test_repeated_section_headers_continue_in_order(self):
		ini = jawsFiles.parseIni("[enu]\nsymbol1=a 11000000 ay\n[deu]\nsymbol1=b 11000000 bee\n[enu]\nsymbol1=c 11000000 see\n", keepRepeatedKeys=True)
		self.assertEqual([value[0] for _key, value in ini.section("enu").allItems()], ["a", "c"])
		self.assertEqual(sorted(symbolMap.parseSymbols(ini.section("enu"))), ["a", "c"])

	def test_read_symbol_file(self):
		folder = tempfile.mkdtemp(prefix="jawsMigrator-dict-")
		try:
			path = os.path.join(folder, "SAPI 5x.sbl")
			with open(path, "w", encoding="utf-8-sig", newline="\r\n") as stream:
				stream.write(self.SBL)
			section = symbolMap.languageSection(symbolMap.readSymbolFile(path), 0x0415, "plk")
			self.assertEqual(set(symbolMap.parseSymbols(section)), {"!", '"', "\x0b"})
			self.assertIsNone(jawsFiles.readIni(path).section("0x415").lines)
		finally:
			shutil.rmtree(folder, ignore_errors=True)

	def test_other_formats_read_as_before(self):
		text = (
			"; comment\nTopKey=1\n[options]\nTypingEcho=1   ; 1=on\nTypingEcho=2\n[Common Keys]\nShift+==AddButton\n[=[\n"
			"[options]\nVerbosity=1\n[ControlType Behavior Table]\n47=1|NormalVoice||LinkVoice|\n47=2|NormalVoice|link1.wav||\n"
		)
		for inlineComments in (False, True):
			plain = jawsFiles.parseIni(text, inlineComments=inlineComments)
			kept = jawsFiles.parseIni(text, inlineComments=inlineComments, keepRepeatedKeys=True)
			self.assertEqual(plain.sectionNames(), kept.sectionNames())
			self.assertEqual(plain.entryCount(), kept.entryCount())
			for name in plain.sectionNames():
				self.assertEqual(plain.section(name).items(), kept.section(name).items(), name)
				self.assertIsNone(plain.section(name).lines, name)
		plain = jawsFiles.parseIni(text, inlineComments=True)
		self.assertEqual(plain.get("options", "TypingEcho"), "2")
		self.assertEqual(plain.get("options", "Verbosity"), "1")
		self.assertEqual(plain.get("", "TopKey"), "1")
		self.assertEqual(plain.get("common keys", "shift+"), "=AddButton")
		self.assertEqual(plain.get("common keys", "["), "[")
		self.assertEqual(plain.get("ControlType Behavior Table", "47"), "2|NormalVoice|link1.wav||")
		self.assertIsNone(jawsFiles.mergeIni(jawsFiles.parseIni(self.SBL, keepRepeatedKeys=True)).section("0x415").lines)


class SymbolFileTests(unittest.TestCase):
	"""Finding 12: symbols NVDA's symbol file reader would split are left out."""

	def setUp(self):
		self.folder = tempfile.mkdtemp(prefix="jawsMigrator-symbols-")
		self.path = os.path.join(self.folder, "symbols-en.dic")

	def tearDown(self):
		shutil.rmtree(self.folder, ignore_errors=True)

	def nvdaReads(self):
		"""The symbols NVDA 2026.2 loads from the file (characterProcessing.SpeechSymbols.load)."""
		escapes = {"0": "\0", "t": "\t", "n": "\n", "r": "\r", "f": "\f", "v": "\v", "#": "#", "\\": "\\"}
		loaded = {}
		invalid = []
		handler = None
		with codecs.open(self.path, "r", "utf_8_sig", errors="replace") as stream:
			for line in stream:
				if line.isspace() or line.startswith("#"):
					continue
				line = line.rstrip("\r\n")
				if line == "symbols:":
					handler = "symbols"
					continue
				fields = line.split("\t")
				if handler != "symbols" or not fields[0]:
					invalid.append(line)
					continue
				identifier = fields[0]
				if identifier.startswith("\\") and len(identifier) >= 2:
					identifier = escapes.get(identifier[1], identifier[1]) + identifier[2:]
				loaded[identifier] = fields[1:]
		return loaded, invalid

	def test_line_break_characters_left_out(self):
		def symbol(character, text):
			return symbolMap.JawsSymbol(character, "11110101", text)

		symbols = {
			"\u2029": symbol("\u2029", "paragraph mark"),
			"\u2028": symbol("\u2028", "line separator"),
			"\x1e": symbol("\x1e", "non breaking hyphen"),
			"\x1c": symbol("\x1c", "file separator"),
			"\x85": symbol("\x85", "next line"),
			"a\u2029": symbol("a\u2029", "two characters"),
			"x": symbol("x", "tab\tinside"),
			"\x0b": symbol("\x0b", "vertical tab"),
			"\x0c": symbol("\x0c", "page break"),
			"\n": symbol("\n", "new line"),
			"#": symbol("#", "number"),
		}
		self.assertIsNone(symbolMap.symbolLine("\u2029", symbols["\u2029"]))
		self.assertEqual(symbolMap.symbolLine("#", symbols["#"]), "\\#\tnumber\tmost\t-")
		self.assertEqual(symbolMap.mergeIntoSymbolFile(self.path, symbols), 4)
		loaded, invalid = self.nvdaReads()
		self.assertEqual(invalid, [])
		self.assertEqual(set(loaded), {"\x0b", "\x0c", "\n", "#"})
		# A line break's name is only said when reading characters (version 1.10, see test_v110_fixes).
		self.assertEqual(loaded["\x0b"], ["vertical tab", "char", "-"])
		self.assertEqual(loaded["\x0c"], ["page break", "most", "-"])

	def test_nothing_written_when_nothing_can_be(self):
		self.assertEqual(symbolMap.mergeIntoSymbolFile(self.path, {"\u2029": symbolMap.JawsSymbol("\u2029", "11110101", "paragraph mark")}), 0)
		self.assertFalse(os.path.exists(self.path))

	def test_lines_split_by_older_versions_removed(self):
		# What 1.0 to 1.2 wrote for U+2029: NVDA reads it as a blank line and a line without a symbol.
		with codecs.open(self.path, "w", "utf_8_sig") as stream:
			stream.write("complexSymbols:\r\nx\ty\r\n\r\nsymbols:\r\n?\t-\t-\talways\r\n\u2029\tparagraph mark\tmost\t-\r\n")
		self.assertEqual(symbolMap.mergeIntoSymbolFile(self.path, {"#": symbolMap.JawsSymbol("#", "11111101", "number")}), 1)
		with codecs.open(self.path, "r", "utf_8_sig") as stream:
			text = stream.read()
		self.assertNotIn("\u2029", text)
		self.assertNotIn("\tparagraph mark", text)
		self.assertIn("complexSymbols:\r\nx\ty\r\n", text)
		self.assertIn("?\t-\t-\talways\r\n", text)
		self.assertIn("\\#\tnumber\tsome\t-\r\n", text)


class LanguageTests(unittest.TestCase):
	"""Finding 13: JAWS calls Latvian lvi."""

	def test_latvian(self):
		self.assertEqual(jawsFiles.JAWS_LANGUAGES["lvi"], (0x0426, "lv_LV"))
		self.assertNotIn("ltv", jawsFiles.JAWS_LANGUAGES)
		self.assertEqual(jawsFiles.languageCodeForLcid(0x0426), "lv_LV")
		conversion = convert(".labdien.labdien.0x26.*.*.0.0.\n.Wave.Waiff.0x07.*.*.0.0.\n", jawsFiles.JAWS_LANGUAGES["lvi"][0])
		self.assertEqual([entry.pattern for entry in conversion.entries], ["labdien"])
		self.assertEqual(len(conversion.skipped), 1)


if __name__ == "__main__":
	unittest.main()
