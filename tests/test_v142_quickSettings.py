# Unit tests for JAWS's Quick Settings (Insert+V), from a tester's issue 40, "Pressing insert V doesn't bring up quick
# settings for that program": "Run a test with Jaws pressing Insert V will bring up the quick settings for that program.
# Example outlook ETC. Should these be added? if so how will you do the live tests? this is a big project I suspect."
# - quickSettings: the window "QuickSettings - <program>", with JAWS's categories, settings and words for the settings NVDA
#   can do, saved for the program alone, in the NVDA profile that turns on in it.
# - The key: JAWS's Default.JKM binds QuickSettings to Insert+V (JAWSKey+V); a migration gives NVDA+V to it, and newKeys
#   adds it once after the update for a migration made before.
# How it is tested (the answer to "how will you do the live tests?"):
# 1. JAWS's own files. Every setting is in JAWS 2026's Default.QS, Browser.qs or another .qs file, with the same kind of
#    control (Boolean or List), the JAWS option it reads and writes (in the .qs file, or, for a setting a script of
#    QuickSet.jss reads and writes, in that script), and the words of its choices (the .qsm files; JAWS's messages for the
#    scripts'). And no option a migration maps to NVDA is left out but by name, with its reason. JawsFilesTests.
# 2. JAWS running. tests/live_jaws_quicksettings.py runs the script QuickSettings through JAWS's programming interface, in
#    Notepad, in an Edge page (the virtual cursor), in Edge's address bar and in new Outlook, reads the tree of each
#    window through Microsoft Active Accessibility and presses Cancel. What it read is in tests/jaws_quicksettings_live.json
#    (JAWS 2026, 27.6.18); LiveJawsTests checks the assistant's window is that window's title, and its categories and
#    settings are in it, in its order, program by program.
# 3. NVDA's own settings. Every NVDA setting a choice sets is in the configSpec of the NVDA installed on this computer
#    (config/configSpec.pyc in library.zip), with a value it takes (NvdaSpecTests).
# 4. The window and the key, against the imitation NVDA of fakeNvda.py (its profiles, triggers and configuration) and wx.
# Run: python -m unittest tests.test_v142_quickSettings -v

import json
import os
import re
import shutil
import sys
import tempfile
import types
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))

import wx  # noqa: E402

import fakeNvda  # noqa: E402
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import jawsDetect, jawsFiles, jawsKeyMap, keyPlan, newKeys, nvdaApply, outlookMessages, quickSettings, settingsMap, state  # noqa: E402

JAWS_SCRIPTS = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "Freedom Scientific", "JAWS", "2026", "Scripts")
JAWS_SETTINGS = os.path.join(os.path.dirname(JAWS_SCRIPTS), "Settings", "enu")
LIVE = os.path.join(os.path.dirname(__file__), "jaws_quicksettings_live.json")
NVDA_LIBRARY = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "NVDA", "library.zip")

needsJaws = unittest.skipUnless(os.path.isfile(os.path.join(JAWS_SCRIPTS, "Default.QS")), "JAWS 2026 isn't installed")

#: NVDA 2026.2's defaults (config/configSpec.py) for every setting a choice sets, which NVDA's configuration always has;
#: NvdaSpecTests reads them from the NVDA installed here to show they are.
NVDA_DEFAULTS = {
	"braille.showMessages": 1,
	"braille.wordWrap": True,
	"documentFormatting.includeLayoutTables": False,
	"documentFormatting.reportArticles": False,
	"documentFormatting.reportBlockQuotes": True,
	"documentFormatting.reportClickable": True,
	"documentFormatting.reportFigures": True,
	"documentFormatting.reportFrames": True,
	"documentFormatting.reportGraphics": True,
	"documentFormatting.reportGroupings": True,
	"documentFormatting.reportHeadings": True,
	"documentFormatting.reportLandmarks": True,
	"documentFormatting.reportLineIndentation": 0,
	"documentFormatting.reportLinkType": True,
	"documentFormatting.reportLists": True,
	"documentFormatting.reportTableCellCoords": True,
	"documentFormatting.reportTableHeaders": 1,
	"documentFormatting.reportTables": True,
	"keyboard.speakTypedCharacters": 1,
	"keyboard.speakTypedWords": 0,
	"presentation.progressBarUpdates.progressBarOutputMode": "beep",
	"presentation.reportDynamicContentChanges": True,
	"presentation.reportHelpBalloons": True,
	"presentation.reportKeyboardShortcuts": True,
	"presentation.reportObjectPositionInformation": True,
	"presentation.reportTooltips": False,
	"speech.autoLanguageSwitching": True,
	"speech.symbolLevel": 100,
	"virtualBuffers.autoPassThroughOnCaretMove": False,
	"virtualBuffers.autoPassThroughOnFocusChange": True,
	"virtualBuffers.autoSayAllOnPageLoad": True,
	"virtualBuffers.passThroughAudioIndication": True,
	"virtualBuffers.useScreenLayout": True,
}

_app = None


def setUpModule():
	global _app
	# The application other test modules made, as they do (a second one, or one that goes with this module, breaks them).
	_app = wx.GetApp() or wx.App(False)


def pump(seconds=0.05):
	import time

	end = time.time() + seconds
	while time.time() < end:
		wx.Yield()
		time.sleep(0.01)


# -- JAWS's own files ------------------------------------------------------------------------------------------------


def jawsQuickSettings() -> dict:
	"""``{setting ID: (type, section, name, write event, [value index...], file)}`` of every .qs file of JAWS."""
	import xml.etree.ElementTree as ET

	found = {}
	for name in sorted(os.listdir(JAWS_SCRIPTS)):
		if not name.lower().endswith(".qs"):
			continue
		for setting in ET.parse(os.path.join(JAWS_SCRIPTS, name)).getroot().iter("Setting"):
			where = setting.find("SettingsFile")
			section = key = event = None
			if where is not None:
				section, key, event = where.get("Section"), where.get("Name"), where.get("WriteValuesEvent")
			found.setdefault(setting.get("ID").strip(), (setting.get("Type"), section, key, event, [value.get("Index") for value in setting.iter("Value")], name))
	return found


def jawsNames() -> dict:
	"""``{ID: text}`` of every DisplayName in JAWS's .qsm files."""
	import xml.etree.ElementTree as ET

	names = {}
	for name in sorted(os.listdir(JAWS_SCRIPTS)):
		if name.lower().endswith(".qsm"):
			for display in ET.parse(os.path.join(JAWS_SCRIPTS, name)).getroot().iter("DisplayName"):
				names.setdefault(display.get("ID").strip(), display.get("Text"))
	return names


def jawsMessages() -> dict:
	"""JAWS's messages (``@name``, the text, ``@@``), lower case names, in its .jsm and .jsh files."""
	messages = {}
	for name in sorted(os.listdir(JAWS_SCRIPTS)):
		if name.lower().endswith((".jsm", ".jsh")):
			with open(os.path.join(JAWS_SCRIPTS, name), encoding="utf-8-sig", errors="replace") as stream:
				text = stream.read().replace("\r\n", "\n")
			for found in re.finditer(r"^@(\w+)\n(.*?)\n@@", text, re.M | re.S):
				messages.setdefault(found.group(1).lower(), found.group(2))
	return messages


def jawsConstants() -> dict:
	"""``{name: text}`` of the constants of JAWS's .jsh files: ``hKey_HeadingIndication = "HeadingIndication",``."""
	constants = {}
	for name in sorted(os.listdir(JAWS_SCRIPTS)):
		if name.lower().endswith(".jsh"):
			with open(os.path.join(JAWS_SCRIPTS, name), encoding="utf-8-sig", errors="replace") as stream:
				for found in re.finditer(r'^\s*(\w+)\s*=\s*"([^"]*)"', stream.read(), re.M):
					constants.setdefault(found.group(1).lower(), found.group(2))
	return constants


def quickSetScript() -> str:
	with open(os.path.join(JAWS_SCRIPTS, "QuickSet.jss"), encoding="utf-8-sig", errors="replace") as stream:
		return stream.read().replace("\r\n", "\n")


def jawsFunction(script: str, name: str) -> str:
	"""The text of the function ``name`` of a JAWS script, up to its endFunction."""
	found = re.search(rf"^\w+\s+function\s+{re.escape(name)}\b.*?^endFunction", script, re.M | re.S | re.I)
	return found.group(0) if found else ""


def flat(categories) -> list:
	"""The names of a tree of categories and settings, as JAWS's tree lists them: a category, then what is in it."""
	names = []
	for category in categories:
		names.append(category.name)
		for child in category.children:
			names.extend(flat([child]) if isinstance(child, quickSettings.Category) else [child.name])
	return names


def isSubsequence(wanted: list, names: list) -> bool:
	rest = iter(names)
	return all(any(name == candidate for candidate in rest) for name in wanted)


@needsJaws
class JawsFilesTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.jaws = jawsQuickSettings()
		cls.names = jawsNames()

	def test_everySettingIsInJawsOwnFiles(self):
		for item in quickSettings.items():
			self.assertIn(item.id, self.jaws, item.id)
			kind = self.jaws[item.id][0]
			self.assertEqual(kind == "Boolean", item.isCheckBox, f"{item.id}: JAWS has a {kind}")
			self.assertEqual(kind == "List", not item.isCheckBox, item.id)

	def test_theNamesAreJawsNames(self):
		for item in quickSettings.items():
			self.assertEqual(self.names[item.id], item.name, item.id)

		def categories(found):
			for category in found:
				yield category
				yield from categories(child for child in category.children if isinstance(child, quickSettings.Category))

		for category in categories(quickSettings.CATEGORIES):
			self.assertEqual(self.names[category.id], category.name, category.id)

	def test_theOptionIsWhatJawsReadsAndWrites(self):
		script = quickSetScript()
		constants = jawsConstants()
		for item in quickSettings.items():
			kind, section, key, event, _indexes, _file = self.jaws[item.id]
			if key:
				self.assertEqual((section.lower(), key.lower()), (item.section.lower(), item.key.lower()), item.id)
				continue
			# A script of QuickSet.jss reads and writes it: what it writes is the option, its section and name given as
			# JAWS's constants or as text.
			body = jawsFunction(script, event)
			self.assertTrue(body, f"{item.id}: {event}")
			words = {constants.get(token.lower(), token).lower() for token in re.findall(r"\b\w+\b", body)}
			words |= {text.lower() for text in re.findall(r'"([^"]*)"', body)}
			self.assertIn(item.key.lower(), words, f"{item.id} writes {item.key}")
			self.assertIn(item.section.lower(), words, f"{item.id} writes in [{item.section}]")

	def test_theChoicesAreJawsChoices(self):
		script = quickSetScript()
		messages = jawsMessages()
		reads = {"Progress Bars": "getProgressBarsInfo", "Punctuation": "getVoicePunctuationInfo", "Auto Forms Mode": "getAutoFormsModeInfo", "Headings Announce": "GetHeadingsInfo", "Document Presentation Mode": "GetDocumentPresentationInfo"}
		for item in quickSettings.items():
			if item.isCheckBox:
				continue
			kind, _section, key, _event, indexes, _file = self.jaws[item.id]
			if key:
				# The names are in the .qsm file, one for each value in the .qs file, by its index or its place.
				values = [index if index is not None else str(place) for place, index in enumerate(indexes)]
				labels = [self.names[f"{item.id}.{place}"] for place in range(len(indexes))]
				self.assertEqual([(choice.value, choice.label) for choice in item.choices], list(zip(values, labels)), item.id)
			else:
				# A script builds the list from JAWS's messages: szListItems[1] = cmsg_off, and so on.
				body = jawsFunction(script, reads[item.name])
				found = re.findall(r"\w*[lL]istItems\[\d+\]\s*=\s*(\w+)", body)
				self.assertEqual([choice.label for choice in item.choices], [messages[name.lower()] for name in found], item.id)

	def test_theWebLevelsAreJawsLevels(self):
		# Verbosity levels are the numbers Default.JCF's tables are in: Beginner 0, Intermediate 1, Advanced 2; Low 0, Medium 1, High 2.
		users = quickSettings.itemById("GeneralOptions.UserVerbosity")
		levels = quickSettings.itemById("VirtualCursorOptions.VirtualCursorVerbosityLevel")
		self.assertEqual([choice.value for choice in users.choices], ["0", "1", "2"])
		self.assertEqual([choice.value for choice in levels.choices], ["0", "1", "2"])

	def test_theBuiltInTablesAreJawsOwn(self):
		# Without JAWS's files a level is JAWS's tables as JAWS comes (settingsMap); with JAWS 2026's own Default.JCF, the same.
		shared = jawsFiles.readIni(os.path.join(JAWS_SETTINGS, "Default.JCF"), inlineComments=True)
		for settingId in ("GeneralOptions.UserVerbosity", "VirtualCursorOptions.VirtualCursorVerbosityLevel"):
			for value in "012":
				self.assertEqual(changes(settingId, value, shared), changes(settingId, value), f"{settingId} {value}")

	def test_jawsNameForProgramsIsRead(self):
		# The plugin reads JAWS's ConfigNames.ini from JAWS as it is on this computer.
		import jawsMigrator

		plugin = jawsMigrator.GlobalPlugin.__new__(jawsMigrator.GlobalPlugin)
		configNames = plugin._jawsConfigNames()
		self.assertEqual(quickSettings.jawsNameFor("olk", configNames), "Outlook Modern")
		self.assertEqual(quickSettings.jawsNameFor("outlook", configNames), "Outlook")
		self.assertEqual(quickSettings.jawsNameFor("msedge", configNames), "msedge")
		self.assertEqual(quickSettings.jawsNameFor("notepad", configNames), "")

	#: The JAWS options a migration maps to NVDA that Quick Settings doesn't have, and why.
	LEFT_OUT = {
		("Options", "ScreenEcho"): "Screen Echo is what JAWS says of text written to the screen; NVDA's live regions, which the migration maps it to with Announce live region updates, are a web page's",
		("Options", "IndicateCaps"): "Caps Indicate has four choices where a migration maps only Never; NVDA raises the pitch for capitals as it is",
		("Braille", "BrailleMode"): "Braille Mode has Line, Structured, Speech Output and Attributes; NVDA has two modes",
		("Braille", "NavByParagraph"): "JAWS shows Pan Text by Paragraph for a display of one line only",
	}

	def test_nothingTheMigrationMapsIsLeftOutButByName(self):
		import xml.etree.ElementTree as ET

		def changes(ini):
			result = settingsMap.mapSettings(ini, ini, isApplication=True, effective=False)
			return {(change.target, change.path, repr(change.value)) for change in result.changes if change.target in (settingsMap.NVDA, settingsMap.ASSISTANT)}

		baseline = changes(jawsFiles.IniFile())
		ours = {(item.section.lower(), item.key.lower()) for item in quickSettings.items()}
		unmapped = []
		for name in sorted(os.listdir(JAWS_SCRIPTS)):
			if not name.lower().endswith(".qs"):
				continue
			for setting in ET.parse(os.path.join(JAWS_SCRIPTS, name)).getroot().iter("Setting"):
				where = setting.find("SettingsFile")
				if where is None or not where.get("Name"):
					continue
				section, key = where.get("Section"), where.get("Name")
				if (section.lower(), key.lower()) in ours:
					continue
				values = ["0", "1"] if setting.get("Type") == "Boolean" else [str(number) for number in range(6)]
				for value in values:
					ini = jawsFiles.IniFile()
					ini.ensureSection(section).set(key, value)
					if changes(ini) - baseline:
						unmapped.append((section, key))
						break
		self.assertEqual(sorted(set(unmapped) - {(section.lower(), key.lower()) for section, key in self.LEFT_OUT} - set(self.LEFT_OUT)), [])
		# What is left out has a reason, and is still a JAWS setting.
		for (section, key), reason in self.LEFT_OUT.items():
			self.assertTrue(reason)
			self.assertIn((section, key), unmapped)

	def test_theKeyIsJawsInsertV(self):
		with open(os.path.join(JAWS_SCRIPTS, "enu", "Default.JKM"), encoding="utf-8-sig", errors="replace") as stream:
			jkm = jawsFiles.parseIni(stream.read())
		self.assertEqual(jkm.get("Common Keys", "JAWSKey+V"), "QuickSettings")
		self.assertEqual(jkm.get("Laptop Keys", "Insert+V"), "QuickSettings")

	def test_theKeyBecomesNvdaV(self):
		with open(os.path.join(JAWS_SCRIPTS, "enu", "Default.JKM"), encoding="utf-8-sig", errors="replace") as stream:
			jkm = jawsFiles.parseIni(stream.read())
		self.assertEqual(jawsKeyMap.getNvdaTargets("QuickSettings")[0][:3], (jawsKeyMap.ASSISTANT_MODULE, jawsKeyMap.ASSISTANT_CLASS, "quickSettings"))
		for layout in ("desktop", "laptop"):
			plan = keyPlan.planKeys(jkm, layout, boundScripts=lambda gesture: [], scriptExists=lambda module, className, script: True, overrideConflicts=False)
			self.assertEqual([(binding.gesture, binding.script) for binding in plan.bindings if binding.jawsScript == "QuickSettings"], [("kb:NVDA+v", "quickSettings")], layout)


class LiveJawsTests(unittest.TestCase):
	"""What JAWS 2026 showed, running (tests/live_jaws_quicksettings.py), against the assistant's window for the same program."""

	CONTEXTS = {
		"notepad": quickSettings.Context("notepad"),
		"edge-page": quickSettings.Context("msedge", browse=True, name="msedge"),
		"edge-window": quickSettings.Context("msedge", name="msedge"),
		"olk": quickSettings.Context("olk", name="Outlook Modern"),
	}

	@classmethod
	def setUpClass(cls):
		if not os.path.isfile(LIVE):
			raise unittest.SkipTest("tests/jaws_quicksettings_live.json isn't here")
		with open(LIVE, encoding="utf-8") as stream:
			cls.live = json.load(stream)

	def test_everyProgramWasRun(self):
		self.assertEqual(sorted(self.live["scenarios"]), sorted(self.CONTEXTS))
		self.assertEqual(self.live["jaws"], "2026")

	def test_theTitleIsJawsTitle(self):
		for name, context in self.CONTEXTS.items():
			self.assertEqual(f"{quickSettings.TITLE} - {context.jawsName}", self.live["scenarios"][name]["title"], name)
			self.assertEqual([context.jawsName], self.live["scenarios"][name]["applications"], name)

	def test_ourCategoriesAndSettingsAreJawsInJawsOrder(self):
		for name, context in self.CONTEXTS.items():
			ours = flat(quickSettings.tree(context))
			self.assertTrue(ours, name)
			self.assertTrue(isSubsequence(ours, self.live["scenarios"][name]["rows"]), f"{name}: {ours}")

	def test_theVirtualCursorIsOnlyInAPage(self):
		# JAWS shows Virtual Cursor Options while the virtual cursor or forms mode is on, as it says in QuickSet.jss.
		for name, context in self.CONTEXTS.items():
			shown = "Virtual Cursor Options" in self.live["scenarios"][name]["rows"]
			self.assertEqual(shown, context.browse, name)
			self.assertEqual("Virtual Cursor Options" in flat(quickSettings.tree(context)), shown, name)

	def test_outlookModernHasItsOwnSettingButNvdaHasNoneForIt(self):
		# JAWS shows "Messages Automatically Read" in new Outlook (Outlook Modern.qs) as in classic Outlook. The assistant's
		# setting for it is for classic Outlook's messages (outlookMessages.APP_NAME), so NVDA has nothing to change in olk.
		self.assertIn("Messages Automatically Read", self.live["scenarios"]["olk"]["rows"])
		self.assertNotIn("Messages Automatically Read", flat(quickSettings.tree(self.CONTEXTS["olk"])))
		self.assertIn("Messages Automatically Read", flat(quickSettings.tree(quickSettings.Context("outlook", name="Outlook"))))
		self.assertEqual(outlookMessages.APP_NAME, "outlook")


# -- NVDA's own settings ---------------------------------------------------------------------------------------------


def nvdaSpec() -> dict:
	"""``{path: spec}`` of the NVDA installed here: config/configSpec.pyc holds the spec as text."""
	with zipfile.ZipFile(NVDA_LIBRARY) as library:
		data = library.read("config/configSpec.pyc")
	text = "\n".join(run.decode("ascii") for run in re.findall(rb"[\x09\x0a\x0d\x20-\x7e]{1500,}", data))
	spec = {}
	stack = []
	for line in text.splitlines():
		line = line.strip()
		if not line or line.startswith("#"):
			continue
		header = re.match(r"^(\[+)([^\]]+)\]+$", line)
		if header:
			stack = stack[: len(header.group(1)) - 1] + [header.group(2)]
			continue
		entry = re.match(r"^(\w+)\s*=\s*(.*)$", line)
		if entry and stack:
			spec[tuple(stack) + (entry.group(1),)] = entry.group(2)
	return spec


def fits(spec: str, value) -> bool:
	"""Whether ``value`` is one NVDA's spec line takes: boolean, integer(min, max) or string."""
	if spec.startswith("boolean"):
		return isinstance(value, bool)
	if spec.startswith("integer"):
		numbers = re.findall(r"(?:min=|max=|\(|,\s*)(-?\d+)", spec.split("default=")[0])
		low = int(numbers[0]) if len(numbers) > 0 else -(10**9)
		high = int(numbers[1]) if len(numbers) > 1 else 10**9
		return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high
	if spec.startswith("string"):
		return isinstance(value, str)
	return False


@unittest.skipUnless(os.path.isfile(NVDA_LIBRARY), "NVDA isn't installed on this computer")
class NvdaSpecTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.spec = nvdaSpec()

	def test_everySettingIsInNvdasSpecWithAValueItTakes(self):
		count = 0
		for item in quickSettings.items():
			for choice in item.choices:
				for change in quickSettings.nvdaChanges(item, choice.value):
					if change.target != settingsMap.NVDA:
						continue
					count += 1
					self.assertIn(tuple(change.path), self.spec, f"{item.id}: {change.path}")
					self.assertTrue(fits(self.spec[tuple(change.path)], change.value), f"{item.id}: {change.path} = {change.value!r} in {self.spec[tuple(change.path)]}")
		self.assertGreater(count, 80)

	def test_theDefaultsTheTestsUseAreNvdas(self):
		for path, value in NVDA_DEFAULTS.items():
			spec = self.spec[tuple(path.split("."))]
			found = re.search(r'default=("[^"]*"|[A-Za-z0-9_-]+)', spec).group(1).strip('"')
			expected = found.lower() == "true" if spec.startswith("boolean") else int(found) if spec.startswith("integer") else found
			self.assertEqual(value, expected, path)

	def test_progressBarModesAreNvdas(self):
		for choice in quickSettings.itemById("GeneralOptions.ProgressBars").choices:
			for change in quickSettings.nvdaChanges(quickSettings.itemById("GeneralOptions.ProgressBars"), choice.value):
				self.assertIn(change.value, ("off", "speak", "beep", "both"))

	def test_symbolLevelsAreNvdas(self):
		levels = {change.value for choice in quickSettings.itemById("EditingOptions.Punctuation").choices for change in quickSettings.nvdaChanges(quickSettings.itemById("EditingOptions.Punctuation"), choice.value)}
		self.assertEqual(levels, {0, 100, 200, 300})


# -- what a choice is in NVDA ---------------------------------------------------------------------------------------


def changes(settingId: str, value: str, jawsSettings=None) -> dict:
	"""``{path: value}`` of the NVDA settings a choice sets."""
	return {".".join(change.path): change.value for change in quickSettings.nvdaChanges(quickSettings.itemById(settingId), value, jawsSettings) if change.target == settingsMap.NVDA}


class ChoiceTests(unittest.TestCase):
	def test_everyChoiceSetsSomething(self):
		for item in quickSettings.items():
			for choice in item.choices:
				self.assertTrue(quickSettings.nvdaChanges(item, choice.value), f"{item.id}: {choice.label}")

	def test_twoChoicesAreNeverTheSameUnlessJawsHasOneWordForTwo(self):
		# Where two of JAWS's choices set the same in NVDA, the one chosen last is shown: these are all of them.
		same = {}
		for item in quickSettings.items():
			seen = {}
			for choice in item.choices:
				key = repr(sorted((change.target, change.path, repr(change.value)) for change in quickSettings.nvdaChanges(item, choice.value)))
				seen.setdefault(key, []).append(choice.label)
			for labels in seen.values():
				if len(labels) > 1:
					same[item.name] = labels
		self.assertEqual(
			same,
			{
				"Graphics Show": ["Tagged", "All"],
				"Headings Announce": ["On", "Heading and Level"],
				"Table Titles": ["Both Row and Column", "Only Marked Headers"],
				# With JAWS's tables as they come, Beginner and Intermediate say the same things in NVDA.
				"User Verbosity": ["Beginner", "Intermediate"],
			},
		)

	def test_typingEcho(self):
		self.assertEqual(changes("EditingOptions.TypingEcho", "0"), {"keyboard.speakTypedCharacters": 0, "keyboard.speakTypedWords": 0})
		self.assertEqual(changes("EditingOptions.TypingEcho", "1"), {"keyboard.speakTypedCharacters": 1, "keyboard.speakTypedWords": 0})
		self.assertEqual(changes("EditingOptions.TypingEcho", "3"), {"keyboard.speakTypedCharacters": 1, "keyboard.speakTypedWords": 1})

	def test_punctuation(self):
		self.assertEqual([changes("EditingOptions.Punctuation", value)["speech.symbolLevel"] for value in "0123"], [0, 100, 200, 300])

	def test_indentation(self):
		self.assertEqual(changes("EditingOptions.Indentation", "0"), {"documentFormatting.reportLineIndentation": 0})
		self.assertEqual(changes("EditingOptions.Indentation", "1"), {"documentFormatting.reportLineIndentation": 1})

	def test_progressBars(self):
		self.assertEqual(changes("GeneralOptions.ProgressBars", "1"), {"presentation.progressBarUpdates.progressBarOutputMode": "speak"})
		self.assertEqual(changes("GeneralOptions.ProgressBars", "0"), {"presentation.progressBarUpdates.progressBarOutputMode": "off"})

	def test_layoutTablesIgnoredIsNvdasLayoutTablesLeftOut(self):
		self.assertEqual(changes("VirtualCursorOptions.TableOptions.LayoutTables", "1"), {"documentFormatting.includeLayoutTables": False})
		self.assertEqual(changes("VirtualCursorOptions.TableOptions.LayoutTables", "0"), {"documentFormatting.includeLayoutTables": True})

	def test_tableTitles(self):
		self.assertEqual([changes("VirtualCursorOptions.TableOptions.TableTitles", value)["documentFormatting.reportTableHeaders"] for value in "01234"], [0, 2, 3, 1, 1])

	def test_autoFormsModeHasThreeChoices(self):
		# JAWS: Manual, Auto (forms mode as the arrow keys reach a field and as Tab does), Semi-Auto (as Tab does, alone).
		auto = "VirtualCursorOptions.FormsOptions.AutoFormsMode"
		self.assertEqual(changes(auto, "0"), {"virtualBuffers.autoPassThroughOnFocusChange": False, "virtualBuffers.autoPassThroughOnCaretMove": False})
		self.assertEqual(changes(auto, "1"), {"virtualBuffers.autoPassThroughOnFocusChange": True, "virtualBuffers.autoPassThroughOnCaretMove": True})
		self.assertEqual(changes(auto, "2"), {"virtualBuffers.autoPassThroughOnFocusChange": True, "virtualBuffers.autoPassThroughOnCaretMove": False})

	def test_aMigrationAgreesWithTheWindowOnAutoFormsMode(self):
		for value in "012":
			ini = jawsFiles.IniFile()
			ini.ensureSection("FormsMode").set("AutoFormsMode", value)
			migrated = {".".join(change.path): change.value for change in settingsMap.mapSettings(ini, ini).changes if "autoPassThrough" in change.key}
			self.assertEqual(migrated, changes("VirtualCursorOptions.FormsOptions.AutoFormsMode", value), value)

	def test_verbosityLevelsAreJawsTables(self):
		# Without JAWS's files, JAWS's own tables (Default.JCF as it comes): the position of an item in a list is said at
		# Beginner and Intermediate, not at Advanced; a list is said at Medium and High, not at Low.
		users = quickSettings.itemById("GeneralOptions.UserVerbosity")
		self.assertEqual(changes(users.id, "0")["presentation.reportObjectPositionInformation"], True)
		self.assertEqual(changes(users.id, "2")["presentation.reportObjectPositionInformation"], False)
		self.assertEqual(changes("VirtualCursorOptions.VirtualCursorVerbosityLevel", "0")["documentFormatting.reportLists"], False)
		self.assertEqual(changes("VirtualCursorOptions.VirtualCursorVerbosityLevel", "1")["documentFormatting.reportLists"], True)

	def test_aVerbosityLevelSetsOnlyItsOwnRows(self):
		# A migration reads every table of JAWS at once; the level of one is not the rows of the other.
		for value in "012":
			self.assertEqual(set(changes("GeneralOptions.UserVerbosity", value)), set(quickSettings.USER_VERBOSITY), value)
			self.assertEqual(set(changes("VirtualCursorOptions.VirtualCursorVerbosityLevel", value)), set(quickSettings.WEB_LEVEL), value)

	def test_theUsersOwnTablesWinOverJawsOwn(self):
		# The tables a user changed in JAWS, and the level chosen over them, as the migration reads them.
		ini = jawsFiles.parseIni("[OutputModes]\nACCESS_KEY=0|0|0|Access Key\n[VirtualCursorVerbosity]\nList=0|0|0\n")
		self.assertEqual(changes("GeneralOptions.UserVerbosity", "0", ini)["presentation.reportKeyboardShortcuts"], False)
		self.assertEqual(changes("VirtualCursorOptions.VirtualCursorVerbosityLevel", "1", ini)["documentFormatting.reportLists"], False)

	def test_theChoiceIsTheLevelEvenWhenJawsIsAtAnother(self):
		ini = jawsFiles.parseIni("[options]\nVerbosity=2\n[VirtualCursorVerbosity]\nVirtualCursorVerbosityLevel=0\n")
		self.assertEqual(changes("GeneralOptions.UserVerbosity", "0", ini), changes("GeneralOptions.UserVerbosity", "0"))
		self.assertEqual(changes("VirtualCursorOptions.VirtualCursorVerbosityLevel", "2", ini), changes("VirtualCursorOptions.VirtualCursorVerbosityLevel", "2"))

	def test_messagesAutomaticallyReadIsTheAssistants(self):
		item = quickSettings.itemById("ReadingOptions.MessagesAutomaticallyRead")
		found = quickSettings.nvdaChanges(item, "1")
		self.assertEqual([(change.target, change.path, change.value) for change in found], [(settingsMap.ASSISTANT, (outlookMessages.READ_KEY,), True)])
		self.assertEqual([change.value for change in quickSettings.nvdaChanges(item, "0")], [False])

	def test_brailleOptions(self):
		self.assertEqual(changes("BrailleOptions.PanningOptions.WordWrap", "0"), {"braille.wordWrap": False})
		self.assertEqual(changes("BrailleOptions.FlashMessages", "0"), {"braille.showMessages": 0})
		self.assertEqual(changes("BrailleOptions.FlashMessages", "1"), {"braille.showMessages": 1})


class TreeTests(unittest.TestCase):
	def test_notepad(self):
		self.assertEqual(
			flat(quickSettings.tree(quickSettings.Context("notepad"))),
			["General Options", "User Verbosity", "Progress Bars", "Reading Options", "Language Detect Change", "Editing Options", "Typing Echo", "Punctuation", "Indentation"],
		)

	def test_aPageAddsTheVirtualCursorFirst(self):
		names = flat(quickSettings.tree(quickSettings.Context("msedge", browse=True)))
		self.assertEqual(names[0], "Virtual Cursor Options")
		self.assertIn("Forms Options", names)
		self.assertEqual(names.count("General Options"), 2, "the virtual cursor's own, and the program's")
		# The program's own settings follow the virtual cursor's last: Cell Coordinates Announcement, then General Options.
		self.assertEqual(names[names.index("Cell Coordinates Announcement") + 1], "General Options")
		self.assertEqual(names[-3:], ["Typing Echo", "Punctuation", "Indentation"])

	def test_braille(self):
		self.assertNotIn("Braille Options", flat(quickSettings.tree(quickSettings.Context("notepad"))))
		names = flat(quickSettings.tree(quickSettings.Context("notepad", braille=True)))
		self.assertEqual(names[-4:], ["Braille Options", "Panning Options", "Word Wrap", "Flash Messages"])

	def test_outlookAddsItsSetting(self):
		names = flat(quickSettings.tree(quickSettings.Context("outlook")))
		self.assertEqual(names[names.index("Reading Options") + 1 :][:2], ["Language Detect Change", "Messages Automatically Read"])
		self.assertNotIn("Messages Automatically Read", flat(quickSettings.tree(quickSettings.Context("winword"))))

	def test_noSettingTwice(self):
		ids = [item.id for item in quickSettings.items()]
		self.assertEqual(len(ids), len(set(ids)))

	def test_jawsNameFor(self):
		ini = jawsFiles.parseIni("[ConfigNames]\nolk=Outlook Modern\nfirefox:3=Firefox\nOUTLOOK=Outlook\nregex:https?:\\/\\/x=Outlook Modern\n")
		self.assertEqual(quickSettings.jawsNameFor("olk", ini), "Outlook Modern")
		self.assertEqual(quickSettings.jawsNameFor("outlook", ini), "Outlook")
		self.assertEqual(quickSettings.jawsNameFor("firefox", ini), "Firefox", "a name for one version of a program")
		self.assertEqual(quickSettings.jawsNameFor("notepad", ini), "")
		self.assertEqual(quickSettings.jawsNameFor("regex", ini), "")
		self.assertEqual(quickSettings.jawsNameFor("notepad", None), "")
		self.assertEqual(quickSettings.Context("notepad").jawsName, "notepad")
		self.assertEqual(quickSettings.Context("olk", name="Outlook Modern").jawsName, "Outlook Modern")


# -- the imitation NVDA ---------------------------------------------------------------------------------------------


class NvdaCase(unittest.TestCase):
	def setUp(self):
		super().setUp()
		self.root = tempfile.mkdtemp(prefix="jawsMigrator-quickSettings-")
		self.addCleanup(shutil.rmtree, self.root, True)
		self.configDir, appDir = fakeNvda.makeNvdaFolders(os.path.join(self.root, "nvda"))
		self.frame = wx.Frame(None)
		self.addCleanup(self.frame.Destroy)
		# No frame for NVDA's gui: what the fake leaves in gui.mainFrame must not be a window this test destroys.
		self.conf, _current = fakeNvda.install(self.configDir, appDir, None)
		# NVDA's configuration always has its defaults.
		for path, value in NVDA_DEFAULTS.items():
			self.setBase(path, value)
		nvdaStubs.spoken.clear()
		state.forget()
		self.addCleanup(state.forget)

	def said(self):
		return list(nvdaStubs.spoken)

	def setBase(self, path, value):
		"""Set a setting of NVDA's normal configuration: ``setBase("speech.symbolLevel", 200)``."""
		node = self.conf.base
		parts = path.split(".")
		for part in parts[:-1]:
			node = node.setdefault(part, {})
		node[parts[-1]] = value

	def profileValue(self, name, path):
		node = self.conf._getProfile(name)
		for part in path.split("."):
			node = node.get(part) if isinstance(node, dict) else None
		return node


class ReadingTests(NvdaCase):
	notepad = quickSettings.Context("notepad")

	def test_whatNvdaHasIsShown(self):
		self.setBase("keyboard.speakTypedCharacters", 1)
		self.setBase("keyboard.speakTypedWords", 1)
		self.setBase("speech.symbolLevel", 300)
		self.setBase("documentFormatting.reportLineIndentation", 0)
		shown = quickSettings.readAll(self.notepad)
		self.assertEqual(shown["EditingOptions.TypingEcho"], "3")
		self.assertEqual(shown["EditingOptions.Punctuation"], "3")
		self.assertEqual(shown["EditingOptions.Indentation"], "0")

	def test_whereNvdaHasNoneOfJawsChoicesNothingIsShown(self):
		# NVDA beeps for a progress bar as it comes; JAWS has spoken and silent.
		self.setBase("presentation.progressBarUpdates.progressBarOutputMode", "beep")
		self.assertIsNone(quickSettings.readAll(self.notepad)["GeneralOptions.ProgressBars"])

	def test_oneWordCoversMoreThanOneValue(self):
		# Indicate is speech, tones or both; Characters is in edit controls or everywhere; Spoken has beeps or not.
		self.setBase("documentFormatting.reportLineIndentation", 3)
		self.setBase("keyboard.speakTypedCharacters", 2)
		self.setBase("keyboard.speakTypedWords", 0)
		self.setBase("presentation.progressBarUpdates.progressBarOutputMode", "both")
		shown = quickSettings.readAll(self.notepad)
		self.assertEqual(shown["EditingOptions.Indentation"], "1")
		self.assertEqual(shown["EditingOptions.TypingEcho"], "1")
		self.assertEqual(shown["GeneralOptions.ProgressBars"], "1")

	def test_theProgramsOwnProfileIsShown(self):
		nvdaApply.setValue(self.conf, ("keyboard", "speakTypedCharacters"), 1)
		with nvdaApply.writingTo("JAWS - notepad"):
			nvdaApply.setValue(self.conf, ("speech", "symbolLevel"), 0)
		nvdaApply.setProfileTrigger("notepad", "JAWS - notepad")
		self.assertEqual(quickSettings.readAll(self.notepad)["EditingOptions.Punctuation"], "0")
		self.assertEqual(quickSettings.readAll(quickSettings.Context("winword"))["EditingOptions.Punctuation"], "1", "another program has NVDA's own")
		self.assertIsNone(self.conf.profiles[-1].name if len(self.conf.profiles) > 1 else None, "no profile is left on")
		self.assertTrue(self.conf.profileTriggersEnabled)

	def test_twoChoicesForOneNvdaSettingShowTheOneChosenLast(self):
		item = quickSettings.itemById("VirtualCursorOptions.GraphicsOptions.GraphicsShow")
		context = quickSettings.Context("msedge", browse=True)
		self.setBase("documentFormatting.reportGraphics", True)
		self.assertEqual(quickSettings.readAll(context)[item.id], "1")
		state.set(quickSettings.CHOICES_KEY, {item.id: "2"})
		self.assertEqual(quickSettings.readAll(context)[item.id], "2")
		# Chosen last, but NVDA's setting has changed since: what NVDA has wins.
		self.setBase("documentFormatting.reportGraphics", False)
		self.assertEqual(quickSettings.readAll(context)[item.id], "0")

	def test_theProgramNeedsNoProfileToBeRead(self):
		before = list(self.conf.listProfiles())
		quickSettings.readAll(self.notepad)
		self.assertEqual(self.conf.listProfiles(), before)


class SavingTests(NvdaCase):
	notepad = quickSettings.Context("notepad")

	def save(self, context=None, **choices):
		selections = {f"{settingId.replace('_', '.')}": value for settingId, value in choices.items()}
		return quickSettings.save(context or self.notepad, selections)

	def test_aChoiceIsSavedForTheProgramAlone(self):
		saved = quickSettings.save(self.notepad, {"EditingOptions.TypingEcho": "3", "EditingOptions.Punctuation": "3"})
		self.assertEqual(saved.profile, "JAWS - notepad")
		self.assertEqual(sorted(change.key for change in saved.applied), ["keyboard.speakTypedCharacters", "keyboard.speakTypedWords", "speech.symbolLevel"])
		self.assertEqual(self.profileValue("JAWS - notepad", "keyboard.speakTypedWords"), 1)
		self.assertEqual(self.profileValue("JAWS - notepad", "speech.symbolLevel"), 300)
		# The normal configuration is as it was.
		self.assertEqual((self.conf.base["speech"]["symbolLevel"], self.conf.base["keyboard"]["speakTypedWords"]), (100, 0))
		# It turns on in the program alone.
		self.assertEqual(self.conf.triggersToProfiles, {"app:notepad": "JAWS - notepad"})
		self.assertEqual(quickSettings.readAll(self.notepad)["EditingOptions.Punctuation"], "3")

	def test_savedAgainItIsTheSameProfile(self):
		quickSettings.save(self.notepad, {"EditingOptions.Punctuation": "3"})
		quickSettings.save(self.notepad, {"EditingOptions.Indentation": "1"})
		self.assertEqual(self.conf.listProfiles(), ["JAWS - notepad"])
		self.assertEqual(self.profileValue("JAWS - notepad", "speech.symbolLevel"), 300)
		self.assertEqual(self.profileValue("JAWS - notepad", "documentFormatting.reportLineIndentation"), 1)

	def test_theProfileIsNamedForJawsConfiguration(self):
		quickSettings.save(quickSettings.Context("outlook", name="Outlook"), {"EditingOptions.Punctuation": "3"})
		self.assertEqual(self.conf.listProfiles(), ["JAWS - Outlook"])
		self.assertEqual(self.conf.triggersToProfiles, {"app:outlook": "JAWS - Outlook"})
		quickSettings.save(quickSettings.Context("olk", name="Outlook Modern"), {"EditingOptions.Punctuation": "0"})
		self.assertEqual(sorted(self.conf.listProfiles()), ["JAWS - Outlook", "JAWS - Outlook Modern"])
		self.assertEqual(self.conf.triggersToProfiles["app:olk"], "JAWS - Outlook Modern")

	def test_aMigrationsProfileIsTheOneUsed(self):
		# "JAWS - Outlook", made by a migration and turned on in outlook: the settings go into it, no other is made.
		with nvdaApply.writingTo("JAWS - Outlook"):
			nvdaApply.setValue(self.conf, ("keyboard", "speakTypedWords"), 1)
		nvdaApply.setProfileTrigger("outlook", "JAWS - Outlook")
		saved = quickSettings.save(quickSettings.Context("outlook", name="Outlook"), {"EditingOptions.Punctuation": "3"})
		self.assertEqual(saved.profile, "JAWS - Outlook")
		self.assertEqual(self.conf.listProfiles(), ["JAWS - Outlook"])
		self.assertEqual(self.profileValue("JAWS - Outlook", "keyboard.speakTypedWords"), 1, "what was there stays")

	def test_aProfileOfTheUsersOwnIsTheOneUsed(self):
		with nvdaApply.writingTo("My Notepad"):
			nvdaApply.setValue(self.conf, ("keyboard", "speakTypedWords"), 1)
		nvdaApply.setProfileTrigger("notepad", "My Notepad")
		saved = quickSettings.save(self.notepad, {"EditingOptions.Punctuation": "3"})
		self.assertEqual(saved.profile, "My Notepad")
		self.assertEqual(self.conf.listProfiles(), ["My Notepad"])
		self.assertEqual(self.conf.triggersToProfiles, {"app:notepad": "My Notepad"})
		self.assertEqual(saved.notice, "")

	def test_aProfileByTheNameThatIsNotTurnedOnGetsItsTrigger(self):
		with nvdaApply.writingTo("JAWS - notepad"):
			nvdaApply.setValue(self.conf, ("keyboard", "speakTypedWords"), 1)
		saved = quickSettings.save(self.notepad, {"EditingOptions.Punctuation": "3"})
		self.assertEqual(saved.profile, "JAWS - notepad")
		self.assertEqual(self.conf.triggersToProfiles, {"app:notepad": "JAWS - notepad"})

	def test_aTriggerForAProfileThatIsGoneIsNotTheUsersOwn(self):
		self.conf.triggersToProfiles["app:notepad"] = "Deleted"
		saved = quickSettings.save(self.notepad, {"EditingOptions.Punctuation": "3"})
		self.assertEqual(saved.profile, "JAWS - notepad")
		self.assertEqual(self.conf.triggersToProfiles["app:notepad"], "JAWS - notepad")

	def test_whatNvdaDoesAlreadyMakesNoProfile(self):
		# Some (100) is what NVDA's normal configuration has: a profile holding nothing would only make NVDA switch for nothing.
		saved = quickSettings.save(self.notepad, {"EditingOptions.Punctuation": "1"})
		self.assertEqual(self.conf.listProfiles(), [])
		self.assertEqual(self.conf.triggersToProfiles, {})
		self.assertTrue(saved.removedEmpty)
		self.assertEqual(quickSettings.confirmation(self.notepad, saved), "notepad does these already, so no profile was needed.")

	def test_theAssistantsOwnSettingIsSavedInItsState(self):
		context = quickSettings.Context("outlook", name="Outlook")
		saved = quickSettings.save(context, {"ReadingOptions.MessagesAutomaticallyRead": "1"})
		self.assertTrue(state.get(outlookMessages.READ_KEY))
		self.assertEqual(saved.profile, "", "no profile for what NVDA doesn't hold")
		self.assertEqual(self.conf.listProfiles(), [])
		self.assertEqual(quickSettings.readAll(context)["ReadingOptions.MessagesAutomaticallyRead"], "1")
		quickSettings.save(context, {"ReadingOptions.MessagesAutomaticallyRead": "0"})
		self.assertFalse(state.get(outlookMessages.READ_KEY))
		self.assertEqual(quickSettings.confirmation(context, saved), "The assistant's setting is saved.")

	def test_aSettingThatIsNotForTheProgramIsNotSaved(self):
		saved = quickSettings.save(self.notepad, {"ReadingOptions.MessagesAutomaticallyRead": "1", "VirtualCursorOptions.FormsOptions.UseSound": "0", "Nothing.Here": "1"})
		self.assertEqual(saved.count, 0)
		self.assertFalse(state.get(outlookMessages.READ_KEY))
		self.assertEqual(self.conf.listProfiles(), [])

	def test_aSettingNvdaKeepsInItsNormalConfigurationOnlyComesBackAsFailed(self):
		# None of the settings is one, but what NVDA can't take in a profile is reported, not lost.
		with mock.patch.object(nvdaApply, "normalConfigurationOnly", side_effect=lambda path: path == ("speech", "symbolLevel")):
			saved = quickSettings.save(self.notepad, {"EditingOptions.Punctuation": "3", "EditingOptions.Indentation": "1"})
		self.assertEqual([change.key for change in saved.applied], ["documentFormatting.reportLineIndentation"])
		self.assertEqual([change.key for change, _reason in saved.failed], ["speech.symbolLevel"])
		self.assertIn("could not be saved", quickSettings.confirmation(self.notepad, saved))

	def test_theChoiceIsRememberedForTwoChoicesThatAreOne(self):
		context = quickSettings.Context("msedge", browse=True, name="msedge")
		quickSettings.save(context, {"VirtualCursorOptions.GraphicsOptions.GraphicsShow": "2", "VirtualCursorOptions.TableOptions.TableTitles": "4"})
		shown = quickSettings.readAll(context)
		self.assertEqual(shown["VirtualCursorOptions.GraphicsOptions.GraphicsShow"], "2")
		self.assertEqual(shown["VirtualCursorOptions.TableOptions.TableTitles"], "4")
		self.assertEqual(state.get(quickSettings.CHOICES_KEY)["VirtualCursorOptions.GraphicsOptions.GraphicsShow"], "2")

	def test_aPageSetting(self):
		context = quickSettings.Context("msedge", browse=True, name="msedge")
		# NVDA's normal configuration has the arrow keys turn focus mode on; Semi-Auto is Tab alone.
		self.setBase("virtualBuffers.autoPassThroughOnCaretMove", True)
		quickSettings.save(context, {"VirtualCursorOptions.FormsOptions.AutoFormsMode": "2", "VirtualCursorOptions.LinksOptions.LinksIdentifySamePage": "0"})
		self.assertEqual(self.profileValue("JAWS - msedge", "virtualBuffers.autoPassThroughOnCaretMove"), False)
		self.assertEqual(self.profileValue("JAWS - msedge", "documentFormatting.reportLinkType"), False)
		self.assertEqual(self.conf.triggersToProfiles, {"app:msedge": "JAWS - msedge"})

	def test_theManualProfileAndTheTriggersAreAsTheyWere(self):
		with nvdaApply.writingTo("Mine"):
			nvdaApply.setValue(self.conf, ("keyboard", "speakTypedWords"), 1)
		nvdaApply.activateProfile("Mine")
		quickSettings.save(self.notepad, {"EditingOptions.Punctuation": "3"})
		self.assertEqual(nvdaApply.activeManualProfile(), "Mine")
		self.assertTrue(self.conf.profileTriggersEnabled)

	def test_theTriggerOfAnotherProfileIsKeptAndSaidSo(self):
		with mock.patch.object(nvdaApply, "setProfileTrigger", return_value=(nvdaApply.TRIGGER_KEPT, "Yours")):
			saved = quickSettings.save(self.notepad, {"EditingOptions.Punctuation": "3"})
		self.assertIn('NVDA already turns on your profile "Yours" in notepad', saved.notice)
		self.assertIn(saved.notice, quickSettings.confirmation(self.notepad, saved))

	def test_theConfirmation(self):
		saved = quickSettings.save(self.notepad, {"EditingOptions.Punctuation": "3"})
		self.assertEqual(quickSettings.confirmation(self.notepad, saved), 'Saved for notepad in the profile "JAWS - notepad".')
		self.assertEqual(quickSettings.confirmation(self.notepad, quickSettings.Saved()), "Nothing to save.")


class SessionTests(NvdaCase):
	def test_theWindowIsJawsWindow(self):
		session = quickSettings.Session(quickSettings.Context("olk", name="Outlook Modern"))
		self.assertEqual(session.title, "QuickSettings - Outlook Modern")
		self.assertEqual(quickSettings.Session(quickSettings.Context("notepad")).title, "QuickSettings - notepad")

	def test_rowsSayTheSettingAndItsValue(self):
		self.setBase("keyboard.speakTypedCharacters", 1)
		self.setBase("keyboard.speakTypedWords", 0)
		session = quickSettings.Session(quickSettings.Context("notepad"))
		echo = quickSettings.itemById("EditingOptions.TypingEcho")
		self.assertEqual(session.rowText(echo), "Typing Echo: Characters")
		self.assertEqual(session.effect(echo), "In NVDA: Speak typed characters: only in edit controls; Speak typed words: off.")
		progress = quickSettings.itemById("GeneralOptions.ProgressBars")
		self.setBase("presentation.progressBarUpdates.progressBarOutputMode", "beep")
		session = quickSettings.Session(quickSettings.Context("notepad"))
		self.assertEqual(session.rowText(progress), "Progress Bars: NVDA's own setting")
		self.assertIn("not one of JAWS's choices", session.effect(progress))

	def test_onlyWhatChangedIsSaved(self):
		session = quickSettings.Session(quickSettings.Context("notepad"))
		self.assertEqual(session.changes(), {})
		echo = quickSettings.itemById("EditingOptions.TypingEcho")
		session.choose(echo, "3")
		self.assertEqual(session.changes(), {echo.id: "3"})
		session.choose(echo, session.initial[echo.id])
		self.assertEqual(session.changes(), {})

	def test_savedItIsWhatNvdaHas(self):
		session = quickSettings.Session(quickSettings.Context("notepad"))
		punctuation = quickSettings.itemById("EditingOptions.Punctuation")
		session.choose(punctuation, "3")
		saved = session.save()
		self.assertEqual(saved.count, 1)
		self.assertEqual(session.changes(), {})
		self.assertEqual(session.initial[punctuation.id], "3")
		self.assertEqual(quickSettings.readAll(quickSettings.Context("notepad"))[punctuation.id], "3")


# -- the window -----------------------------------------------------------------------------------------------------


def descendants(window):
	for child in window.GetChildren():
		yield child
		yield from descendants(child)


def rows(tree):
	"""``[(depth, text)]`` of a wx tree, in order."""
	found = []

	def walk(node, depth):
		child, cookie = tree.GetFirstChild(node)
		while child.IsOk():
			found.append((depth, tree.GetItemText(child)))
			walk(child, depth + 1)
			child, cookie = tree.GetNextChild(node, cookie)

	walk(tree.GetRootItem(), 0)
	return found


class WindowTests(NvdaCase):
	def open(self, context=None):
		from jawsMigrator.gui import quickSettingsDialog

		self.saved = []
		session = quickSettings.Session(context or quickSettings.Context("msedge", browse=True, name="msedge"))
		dialog = quickSettingsDialog.QuickSettingsDialog(self.frame, session, self.saved.append)
		self.addCleanup(dialog.Destroy)
		pump()
		return dialog

	def select(self, dialog, text):
		stack = [dialog.tree.GetRootItem()]
		while stack:
			node = stack.pop()
			child, cookie = dialog.tree.GetFirstChild(node)
			while child.IsOk():
				if dialog.tree.GetItemText(child).startswith(text):
					dialog.tree.SelectItem(child)
					pump()
					return child
				stack.append(child)
				child, cookie = dialog.tree.GetNextChild(node, cookie)
		self.fail(f"no row {text}")

	def test_titleAndControlsAreJaws(self):
		dialog = self.open()
		self.assertEqual(dialog.GetTitle(), "QuickSettings - msedge")
		labels = [child.GetLabel() for child in descendants(dialog) if isinstance(child, wx.Button)]
		self.assertEqual(labels, ["&Apply", "OK", "Cancel"])

	def test_theTreeIsTheTreeOfThePage(self):
		dialog = self.open()
		texts = [text for _depth, text in rows(dialog.tree)]
		self.assertEqual(texts[0], "Virtual Cursor Options")
		self.assertIn("Forms Options", texts)
		self.assertTrue(any(text.startswith("Typing Echo: ") for text in texts))
		self.assertEqual([depth for depth, text in rows(dialog.tree) if text == "Virtual Cursor Options"], [0])
		self.assertEqual([depth for depth, text in rows(dialog.tree) if text == "Forms Options"], [1])
		self.assertEqual([depth for depth, text in rows(dialog.tree) if text.startswith("Auto Forms Mode")], [2])

	def test_everyControlHasItsLabelJustBefore(self):
		dialog = self.open()
		children = list(dialog.GetChildren())

		def before(control):
			return children[children.index(control) - 1]

		self.assertEqual(before(dialog.search).GetLabel(), "&Search:")
		self.assertEqual(before(dialog.tree).GetLabel(), "S&ettings:")
		self.assertIs(before(dialog.list), dialog.listLabel)
		self.assertIs(before(dialog.effect), dialog.effectLabel)
		keys = [re.search("&(.)", child.GetLabel()).group(1).lower() for child in children if isinstance(child, (wx.StaticText, wx.Button)) and "&" in child.GetLabel()]
		self.assertEqual(len(keys), len(set(keys)), "no two access keys are the same")

	def test_aCheckBoxIsShownForACheckBox(self):
		dialog = self.open()
		self.select(dialog, "Use Sound")
		self.assertTrue(dialog.check.IsShown())
		self.assertFalse(dialog.list.IsShown())
		self.assertEqual(dialog.check.GetLabel(), "Use Sound")
		self.assertIn("In NVDA: Audio indication of focus and browse modes", dialog.effect.GetValue())

	def test_aListIsShownForAList(self):
		dialog = self.open()
		self.select(dialog, "Auto Forms Mode")
		self.assertTrue(dialog.list.IsShown())
		self.assertFalse(dialog.check.IsShown())
		self.assertEqual(dialog.listLabel.GetLabel(), "Auto Forms Mode:")
		self.assertEqual(dialog.list.GetStrings(), ["Manual", "Auto", "SemiAuto"])

	def test_aChoiceChangesTheRowAndWhatItDoes(self):
		dialog = self.open()
		self.select(dialog, "Punctuation")
		dialog.list.SetSelection(3)
		dialog.list.GetEventHandler().ProcessEvent(wx.CommandEvent(wx.EVT_CHOICE.typeId, dialog.list.GetId()))
		pump()
		self.assertIn("Punctuation: All", [text for _depth, text in rows(dialog.tree)])
		self.assertEqual(dialog.effect.GetValue(), "In NVDA: Punctuation level: all.")
		self.assertEqual(dialog.session.changes(), {"EditingOptions.Punctuation": "3"})

	def test_aCheckBoxIsChecked(self):
		dialog = self.open()
		self.select(dialog, "Use Sound")
		was = dialog.check.GetValue()
		dialog.check.SetValue(not was)
		dialog.check.GetEventHandler().ProcessEvent(wx.CommandEvent(wx.EVT_CHECKBOX.typeId, dialog.check.GetId()))
		self.assertEqual(dialog.session.changes(), {"VirtualCursorOptions.FormsOptions.UseSound": "0" if was else "1"})
		self.assertIn(f"Use Sound: {'not checked' if was else 'checked'}", [text for _depth, text in rows(dialog.tree)])

	def test_applyAndOkSave(self):
		dialog = self.open(quickSettings.Context("notepad"))
		self.select(dialog, "Punctuation")
		dialog.list.SetSelection(3)
		dialog.list.GetEventHandler().ProcessEvent(wx.CommandEvent(wx.EVT_CHOICE.typeId, dialog.list.GetId()))
		dialog.apply.GetEventHandler().ProcessEvent(wx.CommandEvent(wx.EVT_BUTTON.typeId, dialog.apply.GetId()))
		self.assertEqual(self.profileValue("JAWS - notepad", "speech.symbolLevel"), 300)
		self.assertEqual(self.said()[-1], 'Saved for notepad in the profile "JAWS - notepad".')
		self.assertEqual(len(self.saved), 1)
		# Nothing more changed: OK saves nothing more, and closes.
		nvdaStubs.spoken.clear()
		closed = []
		dialog.EndModal = lambda code: closed.append(code)
		dialog._onOk(None)
		self.assertEqual((closed, self.said(), len(self.saved)), ([wx.ID_OK], [], 1))

	def test_okSavesWhatWasChosenAndCloses(self):
		dialog = self.open(quickSettings.Context("notepad"))
		self.select(dialog, "Indentation")
		dialog.list.SetSelection(1)
		dialog.list.GetEventHandler().ProcessEvent(wx.CommandEvent(wx.EVT_CHOICE.typeId, dialog.list.GetId()))
		closed = []
		dialog.EndModal = lambda code: closed.append(code)
		dialog._onOk(None)
		self.assertEqual(closed, [wx.ID_OK])
		self.assertEqual(self.profileValue("JAWS - notepad", "documentFormatting.reportLineIndentation"), 1)

	def test_cancelSavesNothing(self):
		dialog = self.open(quickSettings.Context("notepad"))
		self.select(dialog, "Indentation")
		dialog.list.SetSelection(1)
		dialog.list.GetEventHandler().ProcessEvent(wx.CommandEvent(wx.EVT_CHOICE.typeId, dialog.list.GetId()))
		self.assertEqual(dialog.GetEscapeId(), wx.ID_CANCEL)
		self.assertEqual(self.conf.listProfiles(), [])

	def test_searchFindsSettingsByName(self):
		dialog = self.open()
		dialog.search.SetValue("table")
		pump()
		texts = [text for _depth, text in rows(dialog.tree)]
		self.assertEqual(
			texts,
			["Virtual Cursor Options", "Table Options", "Layout Tables Ignore: checked", "Table Titles: Both Row and Column"],
		)
		dialog.search.SetValue("")
		pump()
		self.assertGreater(len(rows(dialog.tree)), 20)
		dialog.search.SetValue("no such setting")
		pump()
		self.assertEqual(rows(dialog.tree), [])
		self.assertEqual(dialog.effect.GetValue(), "No setting has that in its name.")

	def test_aChoiceSurvivesLookingAtAnother(self):
		dialog = self.open()
		self.select(dialog, "Punctuation")
		dialog.list.SetSelection(0)
		dialog.list.GetEventHandler().ProcessEvent(wx.CommandEvent(wx.EVT_CHOICE.typeId, dialog.list.GetId()))
		self.select(dialog, "Typing Echo")
		self.select(dialog, "Punctuation")
		self.assertEqual(dialog.list.GetSelection(), 0)

	def test_aSettingWithNoJawsChoiceHasNothingSelected(self):
		self.setBase("presentation.progressBarUpdates.progressBarOutputMode", "beep")
		dialog = self.open()
		self.select(dialog, "Progress Bars")
		self.assertEqual(dialog.list.GetSelection(), wx.NOT_FOUND)
		self.assertIn("not one of JAWS's choices", dialog.effect.GetValue())

	def test_aCategoryRowSaysHowManySettings(self):
		dialog = self.open(quickSettings.Context("notepad"))
		self.select(dialog, "Editing Options")
		self.assertFalse(dialog.check.IsShown() or dialog.list.IsShown())
		self.assertIn("Editing Options: 3 settings", dialog.effect.GetValue())


# -- the command ------------------------------------------------------------------------------------------------------


class CommandTests(NvdaCase):
	def setUp(self):
		super().setUp()
		import jawsMigrator

		self.jawsMigrator = jawsMigrator
		self.focus = types.SimpleNamespace(appModule=types.SimpleNamespace(appName="olk"), treeInterceptor=None)
		self.api = types.SimpleNamespace(getFocusObject=lambda: self.focus)
		patcher = mock.patch.dict(sys.modules, {"api": self.api, "braille": types.SimpleNamespace(handler=types.SimpleNamespace(display=types.SimpleNamespace(name="noBraille")))})
		patcher.start()
		self.addCleanup(patcher.stop)

	def plugin(self, secure=False):
		plugin = self.jawsMigrator.GlobalPlugin.__new__(self.jawsMigrator.GlobalPlugin)
		plugin._gestureMap = {}
		plugin._secure = secure
		plugin._layerActive = False
		plugin._insertKeys = {}
		plugin._quickSettingsOpen = False
		return plugin

	def test_theScriptIsInInputGestures(self):
		script = self.jawsMigrator.GlobalPlugin.script_quickSettings
		self.assertIn("QuickSettings", script.__doc__)
		self.assertIn("Insert+V", script.__doc__)

	def test_theContextIsTheProgramYouAreIn(self):
		plugin = self.plugin()
		with mock.patch.object(plugin, "_jawsConfigNames", return_value=jawsFiles.parseIni("[ConfigNames]\nolk=Outlook Modern\n")):
			context = plugin._quickSettingsContext()
		self.assertEqual(context, quickSettings.Context("olk", browse=False, braille=False, name="Outlook Modern"))
		self.focus.treeInterceptor = object()
		self.focus.appModule.appName = "msedge"
		with mock.patch.object(plugin, "_jawsConfigNames", return_value=None):
			context = plugin._quickSettingsContext()
		self.assertEqual(context, quickSettings.Context("msedge", browse=True, braille=False, name=""))

	def test_aBrailleDisplay(self):
		sys.modules["braille"].handler.display.name = "brailliantB"
		plugin = self.plugin()
		with mock.patch.object(plugin, "_jawsConfigNames", return_value=None):
			self.assertTrue(plugin._quickSettingsContext().braille)

	def test_noProgramSaysSo(self):
		self.focus.appModule = None
		plugin = self.plugin()
		plugin.script_quickSettings(None)
		self.assertEqual(self.said(), ["NVDA can't tell which program you are in."])

	def test_theScriptOpensTheWindowForThatProgram(self):
		plugin = self.plugin()
		opened = []
		with mock.patch.object(plugin, "_jawsConfigNames", return_value=None), mock.patch.object(self.jawsMigrator.wx, "CallAfter", side_effect=lambda function, *args: function(*args)), mock.patch(
			"jawsMigrator.gui.quickSettingsDialog.show",
			side_effect=lambda session, onSaved, parent=None: opened.append(session.title),
		), mock.patch.object(plugin, "_jawsDefaultJcf", return_value=None), mock.patch.object(plugin, "_refuseWhileSettingsOpen", return_value=False):
			plugin.script_quickSettings(None)
		self.assertEqual(opened, ["QuickSettings - olk"])
		self.assertFalse(plugin._quickSettingsOpen)

	def test_notWhileNvdasSettingsAreOpen(self):
		plugin = self.plugin()
		with mock.patch.object(plugin, "_refuseWhileSettingsOpen", return_value=True), mock.patch("jawsMigrator.gui.quickSettingsDialog.show") as show:
			plugin.quickSettings(quickSettings.Context("notepad"))
		show.assert_not_called()

	def test_notOnASecureScreen(self):
		plugin = self.plugin(secure=True)
		with mock.patch("jawsMigrator.gui.quickSettingsDialog.show") as show:
			plugin.script_quickSettings(None)
			plugin.quickSettings(quickSettings.Context("notepad"))
		show.assert_not_called()
		self.assertEqual(self.said(), [])

	def test_notTwice(self):
		plugin = self.plugin()
		plugin._quickSettingsOpen = True
		with mock.patch("jawsMigrator.gui.quickSettingsDialog.show") as show:
			plugin.quickSettings(quickSettings.Context("notepad"))
		show.assert_not_called()

	def test_theAssistantsSettingTakesEffectAtOnce(self):
		plugin = self.plugin()
		applied = []
		plugin.applyRuntimeSettings = lambda: applied.append(True)
		plugin._quickSettingsSaved(quickSettings.Saved())
		self.assertEqual(applied, [])
		plugin._quickSettingsSaved(quickSettings.Saved(assistant=[object()]))
		self.assertEqual(applied, [True])

	def test_aFailureIsSaid(self):
		plugin = self.plugin()
		with mock.patch("jawsMigrator.gui.quickSettingsDialog.show", side_effect=RuntimeError("boom")), mock.patch.object(plugin, "_jawsDefaultJcf", return_value=None), mock.patch.object(
			plugin,
			"_refuseWhileSettingsOpen",
			return_value=False,
		):
			plugin.quickSettings(quickSettings.Context("notepad"))
		self.assertEqual(self.said(), ["QuickSettings could not be opened. NVDA's log says why."])
		self.assertFalse(plugin._quickSettingsOpen)

	def test_theLayerIsUnchanged(self):
		# The command has NVDA+V from a migration and its place in Input Gestures; the layer's keys are as they were.
		self.assertNotIn("quickSettings", self.jawsMigrator.LAYER_KEYS)
		self.assertTrue(callable(getattr(self.jawsMigrator.GlobalPlugin, "script_quickSettings", None)))

	def test_theKeyIsAddedOnceAfterTheUpdate(self):
		self.assertIn("quicksettings", newKeys.NEW_SCRIPTS)
		self.assertEqual(newKeys.pending({}), sorted(newKeys.NEW_SCRIPTS))
		self.assertNotIn("quicksettings", newKeys.pending({newKeys.STATE_KEY: ["quicksettings"]}))
		self.assertIn("quicksettings", newKeys.toRecheck({newKeys.STATE_KEY: []}) + newKeys.pending({}))


if __name__ == "__main__":
	unittest.main()
