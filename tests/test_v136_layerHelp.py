# Unit tests for version 1.36, from a tester's question (issue 33, "Are the commands being properly updated?"):
# the tester pressed NVDA+Shift+J, then question mark, and pasted the help NVDA said.
# - The help was right for 1.35: all 21 keys of the layer, and nothing more. But the keys and the help were two lists
#   kept by hand. Now both come from LAYER_COMMANDS, and these tests check each key against its line of help, its
#   script and README's table, so a command added to the layer can't be left out of its help.
# - JAWS's Insert+Space, question mark shows its layer's help in the Results Viewer, a line for each command
#   (Default.JSS, script BasicLayerHelp). Question mark now shows the layer's help in a window the same way, with
#   NVDA's own ui.browseableMessage, instead of saying all 21 commands in one go.
# - The JAWS keystroke helper (NVDA+Shift+J, then K) didn't know the layer: for Insert+Control+V, when a migration
#   hadn't given it a keystroke, it said "It has no keystroke yet", though NVDA+Shift+J, then V does it. It said
#   Insert+Space "does nothing special in JAWS", since JAWS's key map has only the keys pressed after it. And it said
#   a JAWS command twice when JAWS binds it twice, as Alt+Control+LeftArrow and Alt+Control+ExtendedLeftArrow.
# - README said the NVDA menu, Tools, JAWS Migration Assistant has the layer's actions; it has most, not all.
# JAWS's key map lines are JAWS 2026's own, from Scripts\enu\Default.JKM, which is also read where JAWS is installed.
# NVDA's normalizeGestureIdentifier and its descriptions of NVDA+Space and NVDA+Control+V are NVDA 2026.2's own,
# word for word. The assistant's code is the real one.
# Run: python -m unittest tests.test_v136_layerHelp -v

import ast
import os
import re
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import jawsMigrator  # noqa: E402
from jawsMigrator import jawsFiles, jawsKeyMap, keyPlan, nvdaApply  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
PLUGIN_SOURCE = os.path.join(ROOT, "addon", "globalPlugins", "jawsMigrator", "__init__.py")
README = os.path.join(ROOT, "README.md")
JAWS_JKM = r"C:\ProgramData\Freedom Scientific\JAWS\2026\Scripts\enu\Default.JKM"

# What the tester pasted into issue 33, after "Press insert shift J and question mark.  Are the commands being properly
# updated?": the layer's help as NVDA said it with version 1.35.
TESTERS_PASTE = (
	"JAWS Migration Assistant commands, after NVDA+Shift+J: M, open the migration assistant. O, JAWS Migration "
	"Assistant settings: choose which JAWS items to import. G, open NVDA's Input Gestures dialog. P, turn the JAWS "
	"settings profile on or off. K, hear what a JAWS keystroke does in NVDA. S, JAWS sounds in place of NVDA's own, on "
	"or off, through ClassicSpeech. A, copy all JAWS sounds into ClassicSpeech. C, install ClassicSpeech, or update it "
	"to its newest version. R, open the last migration report. B, restore NVDA settings from a backup. U, check for "
	"updates. I, JAWS, Windows and NVDA versions on this computer. L, save NVDA's log in Documents as a zip file, small "
	"enough to attach to a GitHub issue. V, the name and version of the program you are in, as JAWS's Insert+Control+V. "
	"Shift+V, the version details, to read and copy. Control+V, copy the version details to the clipboard. H, what NVDA "
	"said, the most recent last, as JAWS's speech history. Control+H, copy the speech history to the clipboard. Shift+H, "
	"clear the speech history. Question mark or F1, this help. Escape leaves the layer."
)
#: What 1.39 added to it, after Shift+H: JAWS's Insert+Space, N, Shift+N and D for issue 33, and F11 or Print Screen
#: (JAWS's Screen Shade) and Shift+F11 for issue 37.
ADDED_IN_139 = (
	"N, list recent notifications, the most recent first, as JAWS's Notification History. "
	"Shift+N, repeat the last notification. "
	"D, audio ducking on or off: lower other programs' sound while NVDA speaks. "
	"F11 or Print Screen, turn the screen curtain on or off, as JAWS's Screen Shade. "
	"Shift+F11, say whether the screen curtain is on. "
)
#: The help now: the tester's, word for word, with 1.39's commands where they go.
HELP_NOW = TESTERS_PASTE.replace("Question mark or F1, this help.", ADDED_IN_139 + "Question mark or F1, this help.")

# NVDA 2026.2's inputCore.normalizeGestureIdentifier, word for word.
NVDA_NORMALIZE_GESTURE = (
	"def normalizeGestureIdentifier(identifier):\n"
	'\t"""Normalize a gesture identifier so that it matches other identifiers for the same gesture.\n'
	"\tFirst, the entire identifier is converted to lower case.\n"
	"\tThen, any items separated by a + sign after the source prefix are considered to be of indeterminate order\n"
	"\tand are sorted by character.\n"
	'\tThis is done because, for example, "kb:shift+alt+downArrow"\n'
	'\tmust be treated the same as "kb:alt+shift+downarrow".\n'
	'\t"""\n'
	"\tidentifier = identifier.lower()\n"
	'\tprefix, main = identifier.split(":", 1)\n'
	'\tmain = main.split("+")\n'
	"\t# The order of the parts doesn't matter as far as the user is concerned,\n"
	"\t# but we need them to be in a determinate order so they will match other gesture identifiers.\n"
	"\t# We sort them by character.\n"
	"\tmain.sort()\n"
	'\tmain = "+".join(main)\n'
	'\treturn "{0}:{1}".format(prefix, main)\n'
)
_namespace: dict = {}
exec(NVDA_NORMALIZE_GESTURE, _namespace)
normalizeGestureIdentifier = _namespace["normalizeGestureIdentifier"]

# NVDA 2026.2's descriptions of its scripts for NVDA+Space (globalCommands, script_toggleVirtualBufferPassThrough) and
# NVDA+Control+V (script_activateSpeechDialog), word for word.
NVDA_SPACE_DESCRIPTION = (
	"Toggles between browse mode and focus mode. "
	"When in focus mode, keys will pass straight through to the application, "
	"allowing you to interact directly with a control. "
	"When in browse mode, you can navigate the document with the cursor, quick navigation keys, etc."
)
NVDA_CONTROL_V_DESCRIPTION = "Shows NVDA's speech settings"

# JAWS 2026's own lines of Scripts\enu\Default.JKM, in their sections (line numbers in that file).
JAWS_JKM_LINES = (
	"[Common Keys]\n"
	"alt+JAWSKey+v=SetBrailleView\n"  # 9
	"alt+insert+v=SetBrailleView\n"  # 10
	"Control+JAWSKey+Windows+V=PutVersionDetailsOnClipboard\n"  # 15
	"Control+Insert+Windows+V=PutVersionDetailsOnClipboard\n"  # 16
	"JAWSKey+Space&H=ShowSpeechHistory\n"  # 79
	"Insert+Space&H=ShowSpeechHistory\n"  # 80
	"JAWSKey+Space&Shift+Slash=BasicLayerHelp\n"  # 140
	"Insert+Space&Shift+Slash=BasicLayerHelp\n"  # 141
	"Alt+Control+ExtendedLeftArrow=PriorCell\n"  # 432
	"Control+JAWSKey+V=SayAppVersion\n"  # 445
	"[Laptop Keys]\n"
	"Control+Insert+V=SayAppVersion\n"  # 1030
	"Alt+Control+LeftArrow=PriorCell\n"  # 1116
	"[DESKTOP Keys]\n"
	"Alt+Control+LeftArrow=PriorCell\n"  # 1159
	"[Keyboard Layouts]\n"
	"Desktop=Common\n"
	"Laptop=Common\n"
	"Kinesis=Common\n"
	"PAC Mate=Laptop\n"
)

# How NVDA's Input Gestures dialog and the layer's help name the keys of the layer's gestures.
MODIFIER_NAMES = {"shift": "Shift", "control": "Control", "alt": "Alt"}
KEY_NAMES = {"/": "Question mark", "printscreen": "Print Screen"}


def keyName(identifier: str) -> str:
	"""``kb:shift+v`` -> ``Shift+V``; ``kb:shift+/`` -> ``Question mark`` (Shift and slash is ?)."""
	parts = identifier.split(":", 1)[1].split("+")
	main = parts[-1]
	modifiers = [MODIFIER_NAMES[part] for part in parts[:-1]]
	if main == "/" and modifiers == ["Shift"]:
		return KEY_NAMES[main]
	return "+".join(modifiers + [KEY_NAMES.get(main.lower(), main.upper())])


def readmeLayerTable() -> list:
	"""``[(key, command)]``: the table under README's "The assistant's own commands"."""
	with open(README, encoding="utf-8") as file:
		text = file.read()
	section = text.split("## The assistant's own commands", 1)[1].split("\n## ", 1)[0]
	rows = []
	for line in section.splitlines():
		match = re.match(r"^\| (.+?) \| (.+) \|$", line)
		if match and match.group(1) not in ("Key", "---"):
			rows.append((match.group(1), match.group(2)))
	return rows


def toolsMenuLabels() -> list:
	"""The labels of the NVDA menu, Tools, JAWS Migration Assistant, from the ``items`` of the plugin's _createMenu."""
	with open(PLUGIN_SOURCE, encoding="utf-8") as file:
		tree = ast.parse(file.read())
	for node in ast.walk(tree):
		if isinstance(node, ast.FunctionDef) and node.name == "_createMenu":
			for assign in ast.walk(node):
				if isinstance(assign, ast.Assign) and getattr(assign.targets[0], "id", None) == "items":
					return [item.elts[0].value for item in assign.value.elts]
	raise AssertionError("no items in _createMenu")


class Gesture:
	"""A key press as NVDA hands it to the keystroke helper's capture function."""

	isModifier = False

	def __init__(self, displayName, *identifiers):
		self.displayName = displayName
		self.normalizedIdentifiers = [normalizeGestureIdentifier(identifier) for identifier in identifiers]


class Script:
	def __init__(self, description):
		self.__doc__ = description


def newPlugin():
	"""The assistant's global plugin, without its start, which needs NVDA."""
	return jawsMigrator.GlobalPlugin.__new__(jawsMigrator.GlobalPlugin)


class TheHelpTests(unittest.TestCase):
	def test_theHelpTheTesterHeardIsTheSame(self):
		# Where no window can show it, NVDA says what it said in 1.35: nothing was lost or added.
		self.assertEqual(jawsMigrator.LAYER_HELP, HELP_NOW)

	def test_eachKeyHasItsLineOfHelp(self):
		commands = jawsMigrator.LAYER_COMMANDS
		for gestures, script, key, words in commands:
			self.assertEqual(key, " or ".join(keyName(gesture) for gesture in gestures), script)
			self.assertIn(f"{key}, {words}", jawsMigrator.LAYER_HELP_LINES)
		self.assertEqual(len(jawsMigrator.LAYER_HELP_LINES), len(commands) + 2)
		self.assertEqual(jawsMigrator.LAYER_HELP_LINES[0], "JAWS Migration Assistant commands, after NVDA+Shift+J:")
		self.assertEqual(jawsMigrator.LAYER_HELP_LINES[-1], "Escape leaves the layer.")

	def test_theLayersKeysAreTheHelpsKeys(self):
		gestures = [gesture for entry in jawsMigrator.LAYER_COMMANDS for gesture in entry[0]]
		self.assertEqual(list(jawsMigrator.LAYER_GESTURES), gestures)
		normalized = [normalizeGestureIdentifier(gesture) for gesture in gestures]
		self.assertEqual(len(set(normalized)), len(normalized), "no key twice")
		# 1.35's 20 commands, on 21 keys (question mark and F1 both show the help), and 1.39's N, Shift+N and D, F11 or
		# Print Screen (both turn the screen curtain on or off, as JAWS's Screen Shade) and Shift+F11.
		self.assertEqual(len(jawsMigrator.LAYER_GESTURES), 27)
		self.assertEqual(len(jawsMigrator.LAYER_COMMANDS), 25)

	def test_eachCommandHasAScriptInInputGestures(self):
		for _gestures, script, key, _words in jawsMigrator.LAYER_COMMANDS:
			method = getattr(jawsMigrator.GlobalPlugin, f"script_{script}", None)
			self.assertTrue(callable(method), script)
			self.assertTrue((method.__doc__ or "").strip(), f"{script} has a description in NVDA's Input Gestures dialog")
			self.assertEqual(jawsMigrator.LAYER_KEYS[script], key)

	def test_theReadmeTableHasTheSameKeys(self):
		rows = readmeLayerTable()
		keys = [row[0].replace("?", "Question mark") for row in rows]
		self.assertEqual(keys, [entry[2] for entry in jawsMigrator.LAYER_COMMANDS])
		self.assertIn("in a window", dict(rows)["? or F1"])

	def test_theReadmeNamesTheToolsMenu(self):
		with open(README, encoding="utf-8") as file:
			text = file.read()
		self.assertNotIn("has the same actions, plus Open the debug log", text)
		sentence = text.split("The NVDA menu, Tools, JAWS Migration Assistant has most of the layer's commands", 1)[1].split("\n", 1)[0]
		labels = toolsMenuLabels()
		self.assertEqual(len(labels), 13)
		for label in labels:
			self.assertIn(label.replace("&", "").rstrip("."), sentence)


class TheHelpWindowTests(unittest.TestCase):
	def setUp(self):
		del nvdaStubs.spoken[:]

	def test_questionMarkShowsTheHelpInAWindow(self):
		shown = []
		with mock.patch.object(jawsMigrator.ui, "browseableMessage", lambda *args, **kwargs: shown.append((args, kwargs)), create=True):
			newPlugin().script_layerHelp(None)
		text = "\n".join(jawsMigrator.LAYER_HELP_LINES)
		self.assertEqual(shown, [((text, "JAWS Migration Assistant Layer Help"), {"copyButton": True, "closeButton": True})])
		# A line for each command, as in JAWS's Results Viewer: the arrow keys read one at a time.
		self.assertEqual(len(text.splitlines()), len(jawsMigrator.LAYER_COMMANDS) + 2)
		self.assertIn("Question mark or F1, this help.", text.splitlines())
		self.assertEqual(nvdaStubs.spoken, [], "nothing said in one go")

	def test_anNvdaWhoseWindowHasNoButtons(self):
		shown = []

		def browseableMessage(message, title=None, isHtml=False):
			shown.append((message, title))

		with mock.patch.object(jawsMigrator.ui, "browseableMessage", browseableMessage, create=True):
			self.assertTrue(newPlugin().showLayerHelp())
		self.assertEqual(shown, [("\n".join(jawsMigrator.LAYER_HELP_LINES), "JAWS Migration Assistant Layer Help")])

	def test_saidWhenNoWindowCanOpen(self):
		# NVDA's browseableMessage raises LookupError when its message.html is missing.
		def browseableMessage(*args, **kwargs):
			raise LookupError("message.html")

		with mock.patch.object(jawsMigrator.ui, "browseableMessage", browseableMessage, create=True):
			self.assertFalse(newPlugin().showLayerHelp())
		self.assertEqual(nvdaStubs.spoken, [HELP_NOW])

	def test_theHelpMenusFallbackHasALineEach(self):
		boxes = []
		with mock.patch.object(jawsMigrator, "messageBox", lambda message, title: boxes.append((message, title))):
			newPlugin().openHelp()
		self.assertEqual(boxes, [("\n".join(jawsMigrator.LAYER_HELP_LINES), jawsMigrator.TITLE)])

	def test_nvdaShiftJSaysWhereTheHelpIs(self):
		self.assertIn("question mark or F1 after it to see them", jawsMigrator.GlobalPlugin.script_commandLayer.__doc__)
		self.assertIn("in a window", jawsMigrator.GlobalPlugin.script_layerHelp.__doc__)


class LayerStartTests(unittest.TestCase):
	def test_insertSpaceStartsJawsLayeredKeystrokes(self):
		# JAWS has them as JAWSKey+Space and Insert+Space; its help, and the tester, call it Insert+Space.
		jkm = jawsFiles.parseIni(JAWS_JKM_LINES)
		self.assertEqual(keyPlan.layerStarts(jkm, "desktop"), {"kb:nvda+space": "Insert+Space"})
		# The layered keys themselves are still left out of the reverse map: NVDA has no layered keys.
		self.assertNotIn("kb:nvda+space", keyPlan.buildReverseMap(jkm, "desktop"))
		# JAWS's Laptop layout uses the common keys too.
		self.assertEqual(keyPlan.layerStarts(jkm, "laptop"), {"kb:nvda+space": "Insert+Space"})

	def test_jawsOwnKeyMap(self):
		if not os.path.isfile(JAWS_JKM):
			self.skipTest("JAWS 2026 isn't installed")
		jkm = jawsFiles.readIni(JAWS_JKM)
		for layout in ("desktop", "laptop"):
			starts = keyPlan.layerStarts(jkm, layout)
			self.assertEqual(set(starts.values()), {"Insert+Space"}, layout)
			self.assertIn("kb:nvda+space", starts)

	def test_eachJawsCommandOnce(self):
		jkm = jawsFiles.parseIni(JAWS_JKM_LINES)
		reverse = keyPlan.buildReverseMap(jkm, "desktop")
		# Both of JAWS's keys for it are in the map, as before.
		self.assertEqual(
			[entry[:2] for entry in reverse["kb:alt+control+leftarrow"]],
			[("Alt+Control+LeftArrow", "PriorCell"), ("Alt+Control+ExtendedLeftArrow", "PriorCell")],
		)
		gesture = Gesture("alt+control+leftArrow", "kb(desktop):alt+control+leftArrow", "kb:alt+control+leftArrow")
		self.assertEqual(keyPlan.describeJawsKeystroke(gesture, reverse), [("Alt+Control+LeftArrow", "PriorCell", "DESKTOP Keys")])
		gesture = Gesture("alt+NVDA+v", "kb:alt+NVDA+v")
		self.assertEqual([entry[:2] for entry in keyPlan.describeJawsKeystroke(gesture, reverse)], [("alt+JAWSKey+v", "SetBrailleView")])

	def test_jawsOwnKeyMapHasNoCommandTwice(self):
		if not os.path.isfile(JAWS_JKM):
			self.skipTest("JAWS 2026 isn't installed")
		reverse = keyPlan.buildReverseMap(jawsFiles.readIni(JAWS_JKM), "desktop")
		doubled = [identifier for identifier, entries in reverse.items() if len({entry[1].lower() for entry in entries}) < len(entries)]
		# 1.35's helper said each of these commands twice; now once.
		self.assertGreater(len(doubled), 50)
		for identifier in doubled:
			found = keyPlan.describeJawsKeystroke(types.SimpleNamespace(normalizedIdentifiers=[identifier]), reverse)
			self.assertEqual(len({entry[1].lower() for entry in found}), len(found), identifier)


class KeystrokeHelperTests(unittest.TestCase):
	"""NVDA+Shift+J, then K, then a JAWS keystroke: what NVDA says."""

	def setUp(self):
		del nvdaStubs.spoken[:]
		self.jkm = jawsFiles.parseIni(JAWS_JKM_LINES)
		self.plugin = newPlugin()
		jaws = types.SimpleNamespace(displayName="JAWS 2026")
		self.plugin._keymapCache = (jaws, keyPlan.buildReverseMap(self.jkm, "desktop"), {}, "desktop", keyPlan.layerStarts(self.jkm, "desktop"))
		#: {(module, class, script): the keystrokes NVDA's gesture maps give it, as NVDA names them}
		self.bound = {(jawsKeyMap.ASSISTANT_MODULE, jawsKeyMap.ASSISTANT_CLASS, "commandLayer"): ["NVDA+shift+j"]}
		#: What NVDA's findScript gives for a key press.
		self.nvdaScripts = {}
		patches = (
			mock.patch.object(nvdaApply, "gesturesForScript", lambda module, className, script: list(self.bound.get((module, className, script), []))),
			mock.patch.object(jawsMigrator.scriptHandler, "findScript", lambda gesture: self.nvdaScripts.get(gesture.displayName)),
		)
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)

	def said(self, gesture):
		self.plugin._describeKeystroke(gesture)
		self.assertEqual(len(nvdaStubs.spoken), 1)
		return nvdaStubs.spoken.pop()

	def test_insertSpace(self):
		self.nvdaScripts["NVDA+space"] = Script(NVDA_SPACE_DESCRIPTION)
		text = self.said(Gesture("NVDA+space", "kb(desktop):NVDA+space", "kb:NVDA+space"))
		self.assertEqual(
			text,
			"In JAWS, Insert+Space starts a layered keystroke: you press it, then another key. "
			"In NVDA, NVDA+shift+j starts the JAWS Migration Assistant's layer of commands. It has JAWS's speech history keys, "
			"H, Control+H and Shift+H, its notification keys, N and Shift+N, D for audio ducking, F11 and Print Screen for the "
			"screen curtain, and question mark for its help. "
			f"In NVDA, NVDA+space now does: {NVDA_SPACE_DESCRIPTION}",
		)
		self.assertNotIn("does nothing special in JAWS", text)

	def test_insertSpaceWithTheLayerOnNoKey(self):
		# NVDA+Shift+J taken off in NVDA's Input Gestures dialog: the helper doesn't name a key that doesn't work.
		self.bound.clear()
		text = self.said(Gesture("NVDA+space", "kb:NVDA+space"))
		self.assertEqual(
			text,
			"In JAWS, Insert+Space starts a layered keystroke: you press it, then another key. In NVDA, NVDA+space has no command of its own.",
		)

	def test_insertControlVWithoutAMigration(self):
		# Keys never migrated: NVDA+Control+V is still NVDA's speech settings, and the layer has the command.
		self.nvdaScripts["NVDA+control+v"] = Script(NVDA_CONTROL_V_DESCRIPTION)
		text = self.said(Gesture("NVDA+control+v", "kb(desktop):NVDA+control+v", "kb:NVDA+control+v"))
		description = jawsKeyMap.getNvdaTargets("SayAppVersion", "Control+JAWSKey+V")[0][3]
		self.assertEqual(
			text,
			"In JAWS, Control+JAWSKey+V runs Say App Version. "
			f"In NVDA: {description}. Press NVDA+shift+j, then V. "
			f"In NVDA, NVDA+control+v now does: {NVDA_CONTROL_V_DESCRIPTION}",
		)
		self.assertNotIn("no keystroke yet", text)

	def test_insertControlVAfterAMigration(self):
		self.bound[(jawsKeyMap.ASSISTANT_MODULE, jawsKeyMap.ASSISTANT_CLASS, "sayAppVersion")] = ["NVDA+control+v"]
		self.nvdaScripts["NVDA+control+v"] = Script(jawsMigrator.GlobalPlugin.script_sayAppVersion.__doc__)
		text = self.said(Gesture("NVDA+control+v", "kb:NVDA+control+v"))
		self.assertIn("Press NVDA+control+v, or NVDA+shift+j, then V. ", text)

	def test_controlInsertWindowsV(self):
		text = self.said(Gesture("NVDA+control+windows+v", "kb:NVDA+control+windows+v"))
		self.assertIn("Press NVDA+shift+j, then Control+V. ", text)
		self.assertEqual(text.count("Put Version Details On Clipboard"), 1, "JAWS binds it twice, said once")

	def test_nvdasOwnCommandsAreAsBefore(self):
		# A JAWS command NVDA does itself gets no layer key.
		text = self.said(Gesture("alt+control+leftArrow", "kb(desktop):alt+control+leftArrow", "kb:alt+control+leftArrow"))
		self.assertEqual(text.count("Prior Cell"), 1)
		self.assertNotIn("NVDA+shift+j", text)


class TheLayersKeystrokeTests(unittest.TestCase):
	def test_theLayersScriptIsTheOneNvdaListsForTheAssistant(self):
		# NVDA's Input Gestures lists a global plugin's scripts by its module and class, and names them without script_.
		self.assertEqual((jawsMigrator.GlobalPlugin.__module__.split(".")[-1], jawsMigrator.GlobalPlugin.__name__), ("jawsMigrator", jawsKeyMap.ASSISTANT_CLASS))
		self.assertTrue(jawsKeyMap.ASSISTANT_MODULE.endswith(".jawsMigrator"))
		self.assertTrue(callable(getattr(jawsMigrator.GlobalPlugin, "script_commandLayer", None)))

	def test_nvdaApplysOwnLookupFindsTheLayersKey(self):
		# nvdaApply.gesturesForScript itself, over NVDA's gesture mappings as its Input Gestures dialog gets them.
		info = types.SimpleNamespace(
			moduleName=jawsKeyMap.ASSISTANT_MODULE, className=jawsKeyMap.ASSISTANT_CLASS, scriptName="commandLayer", gestures=["kb:nvda+shift+j"]
		)
		inputCore = sys.modules["inputCore"]
		with mock.patch.object(
			inputCore.manager, "getAllGestureMappings", lambda: {"JAWS Migration Assistant": {"Starts a layer": info}}, create=True
		), mock.patch.object(inputCore, "getDisplayTextForGestureIdentifier", lambda identifier: ("keyboard, all layouts", "NVDA+shift+j"), create=True):
			self.assertEqual(newPlugin()._layerKeystroke(), "NVDA+shift+j")

	def test_noKeyWhenNvdaListsNone(self):
		inputCore = sys.modules["inputCore"]
		with mock.patch.object(inputCore.manager, "getAllGestureMappings", lambda: {}, create=True):
			# The class's own gestures are looked up by importing globalPlugins.jawsMigrator, which isn't there outside NVDA.
			self.assertIsNone(newPlugin()._layerKeystroke())


if __name__ == "__main__":
	unittest.main()
