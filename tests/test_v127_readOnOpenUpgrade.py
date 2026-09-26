# Unit tests for version 1.27, from a tester's report (issue 24, "Now the message is being read automatically"):
#   I this is do to the bad information I submitted earlier.  Hear is the log.  Jaws doesn't read it until I hit down
#   arrow.
# The log attached (NVDA log 2026-09-26 13.32.09.zip) has NVDA 2026.2 with JAWS Migration Assistant 1.25, and Enter on
# GitHub's e-mail of a reply to issue 22 in classic Outlook:
#   13:31:30.069 Input: kb(laptop):enter
#   13:31:30.851 Outlook First Line Silence: silencing event_treeInterceptor_gainFocus
#   13:31:30.959 jawsMigrator: an Outlook message you opened is read from the top, as JAWS reads it, where NVDA said its
#                first line
#   13:31:31.067 Speaking [CallbackCommand(name=say-all:lineReached), LangChangeCommand ('en_US'), 'graphic',
#                'joshknnd1982 left a comment ', 'link', '(joshknnd1982/jawsMigrator#22)', '\r', ...]
# That was 1.25's outlookMessages, which read every message from the top as it opened, after issue 20. Issue 23 said
# the same as this one, and 1.26 made reading on open a setting of its own, off unless turned on
# (readOutlookMessagesOnOpen). The tester's JAWS agrees: its QuickSettings for Outlook (Insert+V) show "Messages
# Automatically Read  not checked" (issue 23).
# What these tests add: the tester updates from 1.25, whose settings file (state.json) has no
# readOutlookMessagesOnOpen, only outlookMessagesAsJaws, which in 1.25 also read a message on open. The settings file
# 1.25 wrote is read by the assistant's real state.load(), and applied by the real code of the assistant's
# GlobalPlugin.applyRuntimeSettings, taken word for word from __init__.py. Opening a message then runs NVDA 2026.2's own
# browse mode code, the imitation of test_v125_outlookMessages: NVDA comes into the message as NVDA does, with no Say
# All, and Outlook First Line Silence, as the tester runs it, keeps its first line quiet, so NVDA says nothing until
# Down Arrow, as JAWS does.
# Run: python -m unittest tests.test_v127_readOnOpenUpgrade -v

import ast
import json
import os
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v125_outlookMessages as opening  # noqa: E402
import test_v126_outlookOpen as v126  # noqa: E402
from jawsMigrator import outlookMessages, state  # noqa: E402

PLUGIN_SOURCE = os.path.join(os.path.dirname(__file__), os.pardir, "addon", "globalPlugins", "jawsMigrator", "__init__.py")

#: The settings file as 1.25 wrote it (state.save: every setting it knew, json.dump with tabs), after a migration and
#: with 1.25's Settings panel left as it came. Its "outlookMessagesAsJaws" was 1.25's one check box for Outlook
#: messages, reading on open included.
STATE_FROM_1_25 = {
	"version": 1,
	"welcomeShown": True,
	"checkForUpdatesAutomatically": True,
	"lastUpdateCheck": 1790443260,
	"jawsProfileName": "",
	"activateJawsProfileAtStartup": False,
	"jawsSoundsEnabled": False,
	"soundReplacements": {},
	"sleepApps": [],
	"lastReport": "",
	"lastBackup": "",
	"lastMigration": {},
	"importSelection": {},
	"classicNvdaSounds": {},
	"voicesRepaired": 0,
	"dictionariesRepaired": 0,
	"gesturesRepaired": 0,
	"insertKeys": {},
	"insertKeysVersion": 0,
	"eloquenceRateRepaired": 0,
	"symbolsRepaired": 0,
	"profileNoticeShown": False,
	"classicSpeechOfferDeclined": False,
	"sayTypeAndStateOnce": True,
	"playJawsLayerSound": True,
	"quietTrayIconChanges": True,
	"sayHeadingAlone": True,
	"listItemsWithoutCoordinates": True,
	"positionLikeJawsInExplorer": True,
	"driveLetterLikeJaws": True,
	"sayWhatBackspaceDeletes": True,
	"browseModeOnTabsAndToolbars": True,
	"documentsWithoutControlSupportTimer": True,
	"documentsWithoutValueEvents": True,
	"backFromTaskbarAtStart": True,
	"linksLikeJaws": True,
	"quietEmptyAlerts": True,
	"stayInFieldsAtTheirEdges": True,
	"quietLeftOutlookMessage": True,
	"outlookWithoutPageNumbers": True,
	"quietColumnsReviewListBounds": True,
	"sayLinksAsJaws": True,
	"outlookMessagesAsJaws": True,
}


def pluginsOutlookMessagesCode():
	"""The part of the assistant's GlobalPlugin.applyRuntimeSettings that applies its Outlook message settings, word for
	word: the try statement that imports outlookMessages."""
	with open(PLUGIN_SOURCE, encoding="utf-8") as stream:
		source = stream.read()
	for node in ast.walk(ast.parse(source)):
		if not (isinstance(node, ast.FunctionDef) and node.name == "applyRuntimeSettings"):
			continue
		for statement in ast.walk(node):
			if isinstance(statement, ast.Try) and any(
				isinstance(inner, ast.ImportFrom) and inner.level == 1 and any(alias.name == "outlookMessages" for alias in inner.names)
				for inner in statement.body
			):
				return textwrap.dedent(ast.get_source_segment(source, statement, padded=True))
	raise AssertionError("applyRuntimeSettings no longer applies outlookMessages in a try statement of its own")


PLUGINS_CODE = compile(pluginsOutlookMessagesCode(), PLUGIN_SOURCE, "exec")


class DebugLog:
	"""The assistant's debugLog, as far as applyRuntimeSettings uses it: what couldn't be applied."""

	def __init__(self):
		self.errors = []

	def error(self, what, *args, **kwargs):
		self.errors.append(what)


class SettingsFile(unittest.TestCase):
	"""A settings file of the assistant's in a folder of its own, read by the real state.load()."""

	def setUp(self):
		super().setUp()
		folder = tempfile.TemporaryDirectory()
		self.addCleanup(folder.cleanup)
		self.path = os.path.join(folder.name, "state.json")
		patch = mock.patch.object(state, "statePath", return_value=self.path)
		patch.start()
		self.addCleanup(patch.stop)
		state.forget()
		self.addCleanup(state.forget)

	def write(self, data):
		with open(self.path, "w", encoding="utf-8") as stream:
			json.dump(data, stream, ensure_ascii=False, indent="\t")
		state.forget()

	def applyAsThePluginDoes(self):
		"""Run the plugin's own code with the settings as state.load() gives them, as NVDA starts."""
		debugLog = DebugLog()
		exec(PLUGINS_CODE, {"__name__": "jawsMigrator", "__package__": "jawsMigrator", "data": state.load(), "debugLog": debugLog})
		self.assertEqual(debugLog.errors, [])


class UpdatedFromOneTwentyFiveTest(SettingsFile, opening.Isolated):
	"""The tester's NVDA after updating from 1.25: Enter on a message in Outlook's message list."""

	def setUp(self):
		super().setUp()
		v126.resetTheAssistant(self)
		self.addCleanup(outlookMessages.unregister)
		self.write(STATE_FROM_1_25)

	def nvdasOwn(self, treeInterceptor):
		"""What NVDA says as it comes into a message: the document, and the line at the caret, which Outlook First Line
		Silence keeps quiet."""
		return [("object", treeInterceptor.rootNVDAObject, opening.OutputReason.FOCUS), ("text", "caret", "line", opening.OutputReason.CARET)]

	def test_the_settings_file_has_no_setting_for_reading_on_open(self):
		self.assertNotIn(outlookMessages.READ_KEY, STATE_FROM_1_25)
		self.assertIn(outlookMessages.STATE_KEY, STATE_FROM_1_25)

	def test_the_assistant_reads_it_with_reading_on_open_off(self):
		data = state.load()
		self.assertTrue(data["welcomeShown"], "the file 1.25 wrote is the one read")
		self.assertFalse(outlookMessages.readWanted(data), "what the Settings panel's check box shows too")
		self.assertTrue(outlookMessages.wanted(data))

	def test_a_message_opens_as_nvda_opens_it(self):
		self.applyAsThePluginDoes()
		self.assertFalse(outlookMessages.readsOnOpen())
		self.assertIs(vars(self.tree)["event_treeInterceptor_gainFocus"], self.nvdasGainFocus, "NVDA's own")
		treeInterceptor, said = self.open()
		self.assertEqual(said, self.nvdasOwn(treeInterceptor))
		self.assertEqual(self.speech.readings, [], "no Say All")

	def test_the_debug_log_no_longer_says_the_message_is_read(self):
		self.applyAsThePluginDoes()
		with self.assertNoLogs("nvda", level="DEBUG"):
			self.open()

	def test_as_1_25_did_it_was_read_from_the_top_as_in_the_log(self):
		# 1.25 turned reading on with "outlookMessagesAsJaws": the log's Say All, from the caret, at the top.
		outlookMessages.register(saying=outlookMessages.wanted(state.load()), reading=True)
		with self.assertLogs("nvda", level="DEBUG") as logged:
			treeInterceptor, said = self.open()
		self.assertEqual(said, [("object", treeInterceptor.rootNVDAObject, opening.OutputReason.FOCUS), ("say all", self.speech.sayAll.CURSOR.CARET)])
		self.assertTrue(any("an Outlook message you opened is read from the top" in line for line in logged.output), logged.output)

	def test_links_lists_and_headings_are_still_said_as_jaws_says_them(self):
		self.applyAsThePluginDoes()
		self.assertTrue(outlookMessages.isRegistered())
		self.assertEqual(opening.NVDA().speakLine(opening.Document(), opening.fromLine()), opening.AS_JAWS)

	def test_turned_off_in_1_25_nothing_is_in_place(self):
		self.write(dict(STATE_FROM_1_25, **{outlookMessages.STATE_KEY: False}))
		self.applyAsThePluginDoes()
		self.assertFalse(outlookMessages.isRegistered())
		treeInterceptor, said = self.open()
		self.assertEqual(said, self.nvdasOwn(treeInterceptor))

	def test_turned_on_since_it_stays_on(self):
		# Someone who checks the box in 1.26 or later keeps it through the next update.
		self.write(dict(STATE_FROM_1_25, **{outlookMessages.READ_KEY: True}))
		self.applyAsThePluginDoes()
		self.open()
		self.assertEqual(self.speech.readings, [self.speech.sayAll.CURSOR.CARET])

	def test_anything_but_true_or_false_in_the_file_is_off(self):
		# state.load() keeps only a value of the setting's own type: JAWS's number 1 isn't turned into "on".
		for value in (1, "1", "true", None):
			with self.subTest(value=value):
				self.write(dict(STATE_FROM_1_25, **{outlookMessages.READ_KEY: value}))
				self.assertFalse(outlookMessages.readWanted(state.load()))


class PluginsCodeTest(unittest.TestCase):
	def test_the_plugin_decides_from_both_settings(self):
		code = pluginsOutlookMessagesCode()
		self.assertIn("outlookMessages.readWanted(data)", code)
		self.assertIn("outlookMessages.wanted(data)", code)
		self.assertIn("reading=reading", code)


if __name__ == "__main__":
	unittest.main()
