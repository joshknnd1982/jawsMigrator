# Unit tests for version 1.36, from a tester's issue 34, "a few things missing": "Insert f4 unloads or brings up Jaws exit
# option that doesn't happen in NVDA. I went and changed this ages ago. Insert q tells you the active program. Something
# I changed ages ago. It doesn't do that in NVDA that if it isn't added in your thing should be added."
# JAWS 2026's Default.JKM gives JAWSKey+F4 to ShutDownJAWS and JAWSKey+Q to ScriptFileName (in its Laptop layout, Insert+F4
# and Insert+Q too). The assistant maps them to NVDA's quit and to NVDA's "report the active program"
# (reportAppModuleInfo, NVDA+Control+F1). NVDA+F4 is free in NVDA, so every migration of keystrokes gave it quit: the
# tester's logs show "Input: kb(laptop):NVDA+f4" then "_doShutdown has been queued" 13 times, with no dialog, as their
# NVDA's askToExit is off (from JAWS's confirmWhenExitingJAWS). NVDA+Q is NVDA's own quit, so it was kept for NVDA unless
# the migration could take NVDA's keystrokes: Insert+Q, JAWS's key for the program, exited NVDA at once instead.
# - keyPlan: NVDA's quit (jawsKeyMap.MOVED_TO_JAWS_KEYS) gives up NVDA+Q to Insert+Q wherever the plan gives it Insert+F4,
#   or NVDA runs it there already; otherwise Insert+Q stays NVDA's quit.
# - newKeys plans ScriptFileName once more after the update, for migrations made before.
# NVDA 2026.2's own code runs here: scriptHandler, GlobalGestureMap and GlobalCommands.script_reportAppModuleInfo with
# NVDA's code for programs, from test_v130_appVersion (checked word for word there), and GlobalCommands.script_quit and
# MainFrame.onExitCommand, checked here (NvdasOwnCodeTests). What is imitated: NVDA's exit dialog and core.triggerNVDAExit
# (records of what NVDA was asked to do), wx.CallAfter (run at once), and the gestures NVDA's own classes bind.
# Run: python -m unittest tests.test_v136_insertQ -v

import ast
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v128_startupFocus as v128  # noqa: E402  (nvdaClass)
import test_v130_appVersion as v130  # noqa: E402  (NVDA's scriptHandler, gesture map, programs and reportAppModuleInfo)
import test_v132_inactiveKeys as v132  # noqa: E402  (the tester's NVDA: its laptop layout, newKeys run at once)

from jawsMigrator import jawsFiles, jawsKeyMap, keyPlan, newKeys, nvdaApply, state  # noqa: E402

#: NVDA 2026.2, source/globalCommands.py, class GlobalCommands: NVDA+Q.
NVDA_QUIT = r'''
@script(
	# Translators: Input help mode message for quit NVDA command.
	description=_("Quits NVDA!"),
	gesture="kb:NVDA+q",
)
def script_quit(self, gesture):
	wx.CallAfter(gui.mainFrame.onExitCommand, None)
'''

#: NVDA 2026.2, source/gui/__init__.py, class MainFrame: what quit runs.
NVDA_ON_EXIT_COMMAND = r'''
@blockAction.when(blockAction.Context.MODAL_DIALOG_OPEN)
def onExitCommand(self, evt):
	if config.conf["general"]["askToExit"]:
		self.prePopup()
		d = ExitDialog(self)
		d.Raise()
		d.Show()
		self.postPopup()
	else:
		if not core.triggerNVDAExit():
			log.error("NVDA already in process of exiting, this indicates a logic error.")
'''

NVDA_CODE_FILES = {"NVDA_QUIT": "globalCommands.py", "NVDA_ON_EXIT_COMMAND": "gui/__init__.py"}

#: NVDA's MainFrame, as far as onExitCommand uses it: its popups are noted.
IMITATION_MAIN_FRAME = r'''
def __init__(self):
	self.popups = 0


def prePopup(self):
	self.popups += 1


def postPopup(self):
	pass
'''

#: The keystrokes of JAWS 2026's Default.JKM for these commands (checked in JawsTests), in its sections.
JAWS_KEYS = (
	"[Keyboard Layouts]\nDesktop=Common\nLaptop=Common\n"
	"[Common Keys]\nWindows+JAWSKey+F4=JAWSMemDmp\nJAWSKey+F4=ShutDownJAWS\nJAWSKey+Q=ScriptFileName\n"
	"[Laptop Keys]\nWindows+Insert+F4=JAWSMemDmp\nInsert+Q=ScriptFileName\nInsert+F4=ShutDownJAWS\n"
	"[Laptop Modifiers]\nCapsLock=14|3|0|0|0|0|0x4000\n[Desktop Modifiers]\nInsert=17|3|0|2|0|0|0x4020800\n"
)
#: What the tester's log (NVDA 2026.2, jawsMigrator 1.35, issue 32's nvda-old.log) shows Insert+F4 doing.
TESTERS_EXIT = (
	"IO - inputCore.InputManager.executeGesture (23:02:14.766) - winInputHook (24556):\nInput: kb(laptop):NVDA+f4\n"
	"DEBUG - core.triggerNVDAExit (23:02:14.767) - MainThread (1844):\n_doShutdown has been queued"
)
QUIT = ("globalCommands", "GlobalCommands", "quit")
PROGRAM = ("globalCommands", "GlobalCommands", "reportAppModuleInfo")
ANNOUNCED = (
	"JAWS Migration Assistant: 1 more JAWS keystroke works in NVDA. NVDA+q, the program you are in, as JAWS's Insert+Q; "
	"it no longer exits NVDA: NVDA+f4 does."
)


def recordingScript(**kwargs):
	"""NVDA's script decorator, as far as the gestures go: ScriptableType puts them in the class's __gestures."""

	def decorate(function):
		function.gestures = [kwargs["gesture"]] if "gesture" in kwargs else list(kwargs.get("gestures", ()))
		return function

	return decorate


class ExitCase(v130.KeysCase):
	"""NVDA's own NVDA+Q (quit) and NVDA+Control+F1 (the program), in NVDA's own globalCommands, and what quit does."""

	askToExit = True

	def setUp(self):
		super().setUp()
		self.exits = []
		self.dialogs = []
		test = self

		class ExitDialog:
			def __init__(self, parent):
				test.dialogs.append(parent)

			def Raise(self):
				pass

			def Show(self):
				pass

		def triggerNVDAExit():
			self.exits.append(True)
			return len(self.exits) == 1

		passThrough = types.SimpleNamespace(when=lambda *contexts: (lambda function: function))
		MainFrame = v128.nvdaClass(
			"class MainFrame",
			[IMITATION_MAIN_FRAME, NVDA_ON_EXIT_COMMAND],
			{
				"blockAction": types.SimpleNamespace(when=passThrough.when, Context=types.SimpleNamespace(MODAL_DIALOG_OPEN="modal")),
				"config": types.SimpleNamespace(conf={"general": {"askToExit": self.askToExit}}),
				"ExitDialog": ExitDialog,
				"core": types.SimpleNamespace(triggerNVDAExit=triggerNVDAExit),
				"log": v130._log,
			},
		)
		self.mainFrame = MainFrame()
		GlobalCommands = v128.nvdaClass(
			"class GlobalCommands",
			[NVDA_QUIT, v130.NVDA_REPORT_APP_MODULE_INFO],
			{
				"script": recordingScript,
				"_": lambda text: text,
				"SCRCAT_TOOLS": "tools",
				"api": self.nvda.api,
				"appModuleHandler": self.programs.appModuleHandler,
				"ui": self.nvda.ui,
				# NVDA runs what wx.CallAfter is given on its main thread, after the script: here, at once.
				"wx": types.SimpleNamespace(CallAfter=lambda function, *args, **kwargs: function(*args, **kwargs)),
				"gui": types.SimpleNamespace(mainFrame=self.mainFrame),
			},
		)
		GlobalCommands.__module__ = "globalCommands"
		GlobalCommands._GlobalCommands__gestures = {
			identifier: name[len("script_") :] for name, function in vars(GlobalCommands).items() if name.startswith("script_") for identifier in getattr(function, "gestures", ())
		}
		normalize = self.normalize

		def getScript(commands, gesture):
			# NVDA's ScriptableObject.getScript, for the class's own gestures.
			for identifier in gesture.normalizedIdentifiers:
				for bound, name in GlobalCommands._GlobalCommands__gestures.items():
					if normalize(bound) == identifier:
						return getattr(commands, f"script_{name}")
			return None

		GlobalCommands.getScript = getScript
		self.commands = GlobalCommands()
		globalCommands = sys.modules["globalCommands"]
		globalCommands.GlobalCommands = GlobalCommands
		globalCommands.commands = self.commands
		# This Python, a program like any other, is the program in the foreground.
		self.focus = v130.Focus(self.programs.appModule(os.getpid(), "python"))
		self.exe = self.programs.appModuleHandler.getAppNameFromProcessID(os.getpid(), True)

	def planFor(self, layout="desktop", overrideConflicts=False, text=JAWS_KEYS, nvdaLayout=None):
		return keyPlan.planKeys(
			jawsFiles.parseIni(text),
			layout,
			boundScripts=nvdaApply.gestureBoundScripts,
			scriptExists=nvdaApply.scriptExists,
			overrideConflicts=overrideConflicts,
			nvdaLayout=nvdaLayout,
		)

	def bindings(self, plan, *targets):
		return sorted((b.gesture, b.script) for b in plan.bindings if (b.module, b.className, b.script) in targets)

	def programSaid(self):
		return [f" {self.exe} is currently running."]


class NvdasKeysTests(ExitCase):
	"""What NVDA's own keys do, before any migration."""

	def test_nvdaQuitsWithNvdaQ(self):
		self.press("kb:NVDA+q")
		self.assertEqual((len(self.dialogs), self.exits), (1, []))
		self.press("kb:NVDA+control+f1")
		self.assertEqual(self.nvda.said(), self.programSaid())

	def test_nvdaF4IsFree(self):
		self.assertEqual(nvdaApply.gestureBoundScripts("kb:NVDA+f4"), [])
		self.assertIsNone(self.scriptHandler._findScript(v130.Key("kb:NVDA+f4", self.normalize)))


class PlanTests(ExitCase):
	"""A migration of keystrokes: Insert+F4 exits NVDA, and Insert+Q says the program."""

	def test_insertQSaysTheProgram(self):
		for layout in ("desktop", "laptop"):
			plan = self.planFor(layout)
			self.assertEqual(self.bindings(plan, QUIT, PROGRAM), [("kb:NVDA+f4", "quit"), ("kb:NVDA+q", "reportAppModuleInfo")], layout)
			program = [b for b in plan.bindings if b.script == "reportAppModuleInfo"][0]
			self.assertEqual((program.replaces, program.moved, program.unbind), (["quit"], {"quit": "kb:NVDA+f4"}, []))
			self.assertEqual(
				program.label,
				"JAWSKey+Q: Report the active program's executable and the NVDA app module loaded for it "
				"(replaces NVDA's quit, which NVDA+f4 runs, as in JAWS)",
			)
			self.assertEqual([item for item in plan.skipped if item.kind == keyPlan.SKIP_CONFLICT], [], layout)

	def test_theKeysInNvda(self):
		nvdaApply.addGestures(self.planFor("laptop").bindings)
		self.press("kb:NVDA+q")
		self.assertEqual(self.nvda.said(), self.programSaid())
		self.assertEqual((self.dialogs, self.exits), ([], []))
		self.press("kb:NVDA+f4")
		self.assertEqual(len(self.dialogs), 1)
		# NVDA's own NVDA+Control+F1 still says the program too.
		self.press("kb:NVDA+control+f1")
		self.assertEqual(self.nvda.said(), self.programSaid() * 2)

	def test_insertF4IsTaken(self):
		# Your input gestures give NVDA+F4 to something else: NVDA's quit keeps NVDA+Q, as before.
		self.userMap.add("kb:NVDA+f4", "globalCommands", "GlobalCommands", "reportAppModuleInfo")
		plan = self.planFor()
		self.assertEqual(self.bindings(plan, QUIT, PROGRAM), [])
		kept = {item.jawsKey: item for item in plan.skipped if item.kind == keyPlan.SKIP_CONFLICT}
		self.assertEqual(kept["JAWSKey+Q"].reason, "NVDA already uses this keystroke for quit")
		nvdaApply.addGestures(plan.bindings)
		self.press("kb:NVDA+q")
		self.assertEqual(len(self.dialogs), 1)

	def test_quitIsOnInsertF4Already(self):
		# An earlier migration gave NVDA's quit Insert+F4: NVDA+Q goes to the program all the same.
		self.userMap.add("kb:NVDA+f4", *QUIT)
		plan = self.planFor("laptop", nvdaLayout="laptop")
		self.assertEqual(self.bindings(plan, QUIT, PROGRAM), [("kb:NVDA+q", "reportAppModuleInfo")])
		self.assertEqual([b.moved for b in plan.bindings], [{"quit": "kb:NVDA+f4"}])
		self.assertIn("JAWSKey+F4", [item.jawsKey for item in plan.skipped if item.kind == keyPlan.SKIP_SAME])

	def test_takingNvdasKeys(self):
		# Letting JAWS's keys take NVDA's gives the same, and the report still says where NVDA's quit is.
		plan = self.planFor(overrideConflicts=True)
		self.assertEqual(self.bindings(plan, QUIT, PROGRAM), [("kb:NVDA+f4", "quit"), ("kb:NVDA+q", "reportAppModuleInfo")])
		self.assertEqual([b.moved for b in plan.bindings if b.script == "reportAppModuleInfo"], [{"quit": "kb:NVDA+f4"}])

	def test_anAddOnsNvdaQ(self):
		# An add-on's own NVDA+Q stays the add-on's: only NVDA's quit gives its keystroke up.
		with mock.patch.object(nvdaApply, "_addonPluginGestures", side_effect=lambda gesture: [("globalPlugins.other", "GlobalPlugin", "other", "kb:NVDA+q", "addon")] if "q" in gesture.lower().split("+") else []):
			plan = self.planFor()
		self.assertEqual(self.bindings(plan, QUIT, PROGRAM), [("kb:NVDA+f4", "quit")])
		kept = {item.jawsKey: item for item in plan.skipped if item.kind == keyPlan.SKIP_CONFLICT}
		self.assertIn("the add-on other (other)", kept["JAWSKey+Q"].reason)

	def test_otherNvdaKeysStayNvdas(self):
		# A JAWS key on NVDA's own NVDA+Control+F1 (the program) wanting quit: NVDA's other commands keep their keys.
		text = JAWS_KEYS + "[Common Keys]\nJAWSKey+Control+F1=ShutDownJAWS\n"
		plan = self.planFor(text=text)
		kept = {item.jawsKey: item for item in plan.skipped if item.kind == keyPlan.SKIP_CONFLICT}
		self.assertEqual(kept["JAWSKey+Control+F1"].reason, "NVDA already uses this keystroke for reportAppModuleInfo")
		# Only NVDA's own quit gives its keystroke up; not a quit of your own input gestures.
		self.assertFalse(keyPlan._movable(keyPlan._Decision("conflict", [keyPlan._Bound(*PROGRAM, None, "class")])))
		self.assertTrue(keyPlan._movable(keyPlan._Decision("conflict", [keyPlan._Bound(*QUIT, None, "class")])))
		self.assertFalse(keyPlan._movable(keyPlan._Decision("conflict", [keyPlan._Bound(*QUIT, None, "user")])))


class AskToExitOffCase(ExitCase):
	"""The tester's NVDA: "askToExit": "False", as their log's configuration shows."""

	askToExit = False


class TestersExitTests(AskToExitOffCase):
	def test_insertF4ExitsAtOnce(self):
		# As their log shows it: NVDA+F4, then NVDA's exit, with no dialog.
		self.assertIn("Input: kb(laptop):NVDA+f4", TESTERS_EXIT)
		nvdaApply.addGestures(self.planFor("laptop").bindings)
		self.press("kb:NVDA+f4")
		self.assertEqual((self.dialogs, self.exits), ([], [True]))

	def test_insertQNoLongerExits(self):
		# Kept for NVDA, as up to 1.35, Insert+Q exited NVDA at once.
		self.press("kb:NVDA+q")
		self.assertEqual(self.exits, [True])
		self.exits.clear()
		nvdaApply.addGestures(self.planFor("laptop").bindings)
		self.press("kb:NVDA+q")
		self.assertEqual(self.exits, [])
		self.assertEqual(self.nvda.said(), self.programSaid())


class NewKeysTests(v132.TestersCase, AskToExitOffCase):
	"""Once after the update to 1.36, for the tester's migration of 2026-09-23 as 1.35 left it."""

	def as135LeftIt(self, overrideConflicts=False):
		state.set("lastMigration", {"when": "2026-09-23T20:43:59", "keyboardLayouts": ["laptop"], "overrideConflicts": overrideConflicts})
		state.set(newKeys.STATE_KEY, ["putversiondetailsonclipboard", "sayappversion", "showversiondetails"])
		state.set(newKeys.RECHECK_KEY, True)
		# The migration gave NVDA's quit Insert+F4 (JAWSKey+F4, the same in both NVDA layouts).
		self.userMap.add("kb:NVDA+f4", *QUIT)
		if overrideConflicts:
			self.userMap.add("kb:NVDA+q", *PROGRAM)

	def addOnce(self, jawsLayout="laptop", text=JAWS_KEYS):
		super().addOnce(jawsLayout, text)

	def test_pending(self):
		self.as135LeftIt()
		self.assertEqual(newKeys.pending(state.load()), ["scriptfilename"])
		self.assertEqual(newKeys.toRecheck(state.load()), [])

	def test_theTestersNvda(self):
		self.as135LeftIt()
		with mock.patch.object(newKeys.debugLog, "note") as note:
			self.addOnce()
		self.assertEqual(self.bound("kb:NVDA+q"), [PROGRAM])
		self.assertEqual(self.said, [ANNOUNCED])
		self.assertEqual((self.done, len(self.backups)), ([True], 1))
		lines = [call.args[0] for call in note.call_args_list]
		self.assertIn(
			"kb:NVDA+q -> globalCommands.GlobalCommands.reportAppModuleInfo (JAWS JAWSKey+Q=ScriptFileName, [Common Keys]); "
			"NVDA's quit stays on kb:NVDA+f4, JAWS's keystroke for it",
			lines,
		)
		self.assertIn("scriptfilename", state.get(newKeys.STATE_KEY))
		# Insert+Q says the program; Insert+F4 exits NVDA at once, as before.
		self.press("kb:NVDA+q")
		self.assertEqual((self.nvda.said(), self.exits), (self.programSaid(), []))
		self.press("kb:NVDA+f4")
		self.assertEqual(self.exits, [True])
		# Once only.
		self.addOnce()
		self.assertEqual((len(self.backups), len(self.said)), (1, 1))

	def test_bothNvdaLayouts(self):
		# NVDA's quit is on NVDA+F4 in both layouts, so Insert+Q says the program in both: kb:, not kb(laptop):.
		self.as135LeftIt()
		self.addOnce()
		self.assertEqual(sorted(self.userMap._map), sorted([self.normalize("kb:NVDA+f4"), self.normalize("kb:NVDA+q")]))

	def test_aMigrationThatTookNvdasKeys(self):
		self.as135LeftIt(overrideConflicts=True)
		self.addOnce()
		self.assertEqual(self.bound("kb:NVDA+q"), [PROGRAM])
		self.assertEqual((self.said, self.backups, self.done), ([], [], [True]))
		self.assertEqual(newKeys.pending(state.load()), [])

	def test_whereInsertF4DoesSomethingElse(self):
		# After the migration, you gave NVDA+F4 a command of your own: NVDA+Q stays NVDA's quit.
		self.as135LeftIt()
		self.userMap._map.clear()
		self.userMap.add("kb:NVDA+f4", "globalCommands", "GlobalCommands", "reportAppModuleInfo")
		self.addOnce()
		self.assertEqual(self.bound("kb:NVDA+q"), [])
		self.assertEqual((self.said, self.done), ([], [True]))
		self.press("kb:NVDA+q")
		self.assertEqual(self.exits, [True])

	def test_yourOwnNvdaQ(self):
		# You gave NVDA+Q a command of your own: it stays yours.
		self.as135LeftIt()
		self.userMap.add("kb:NVDA+q", "globalCommands", "GlobalCommands", "reportAppModuleInfo")
		before = self.bound("kb:NVDA+q")
		self.addOnce()
		self.assertEqual(self.bound("kb:NVDA+q"), before)
		self.assertEqual(self.said, [])

	def test_noMigratedKeystrokes(self):
		state.set("lastMigration", {"when": "2026-09-23T20:43:59", "keyboardLayouts": [], "overrideConflicts": False})
		self.addOnce()
		self.assertEqual((self.bound("kb:NVDA+q"), self.backups, self.done), ([], [], [True]))
		self.assertEqual(newKeys.pending(state.load()), [])

	def test_aNewMigrationCountsItDone(self):
		self.assertEqual(newKeys.NEW_SCRIPTS["scriptfilename"][0], "1.36")
		self.assertIn("scriptfilename", sorted(newKeys.NEW_SCRIPTS))


# -- JAWS's own keys and words ------------------------------------------------------------------------------------


@v130.needsJaws
class JawsTests(unittest.TestCase):
	def test_theKeysAreJaws(self):
		jkm = jawsFiles.readIni(os.path.join(v130.JAWS_SCRIPTS, "enu", "Default.JKM"))
		mine = jawsFiles.parseIni(JAWS_KEYS)
		for name in ("Common Keys", "Laptop Keys"):
			section = {key.lower(): script for key, script in jkm.sections[name.lower()].items()}
			for key, script in mine.sections[name.lower()].items():
				self.assertEqual(section.get(key.lower()), script, key)

	def test_whatJawsSays(self):
		# Insert+Q: "%1 settings are loaded / The application currently being used is %2 / %3" (the name spelled);
		# Insert+F4: "Unloading JAWS", then JAWS exits.
		messages = v130.jawsMessages("common.jsm")
		self.assertEqual(messages["cmsg145_l"], "%1 settings are loaded\nThe application currently being used is %2\n%3")
		self.assertEqual(messages["cmsg26_l"], "Unloading JAWS")
		default = v130.jawsScript("Default.JSS")
		self.assertIn("Script ScriptFileName()\nScriptAndAppNames(cmsg238_L)", default)
		self.assertIn("SayFormattedMessage (ot_JAWS_message, cmsg26_L) ;\"Unloading JAWS\"\n\tShutDownJAWS()", default)

	def test_theJawsDefaultKeyMap(self):
		with open(os.path.join(v130.JAWS_SCRIPTS, "enu", "Default.JKM"), encoding="utf-8-sig", errors="replace") as f:
			text = f.read()
		case = PlanTests("test_insertQSaysTheProgram")
		case.setUp()
		try:
			for layout in ("desktop", "laptop"):
				plan = case.planFor(layout, text=text)
				self.assertEqual(case.bindings(plan, QUIT, PROGRAM), [("kb:NVDA+f4", "quit"), ("kb:NVDA+q", "reportAppModuleInfo")], layout)
				# The only NVDA command a JAWS keystroke took without being asked is NVDA's quit.
				self.assertEqual({tuple(b.replaces) for b in plan.bindings if b.replaces and not b.section.lower().startswith(("quick", "virtual"))}, {("quit",)}, layout)
		finally:
			case.doCleanups()


# -- NVDA's own code and keys -------------------------------------------------------------------------------------


def nvdaSource():
	source = os.environ.get("NVDA_SOURCE")
	if not source:
		raise unittest.SkipTest("NVDA_SOURCE isn't set to a folder with NVDA 2026.2's source")
	return source


#: The classes nvdaApply._gestureClasses asks, and their files in NVDA's source.
GESTURE_CLASSES = {
	("globalCommands", "GlobalCommands"): "globalCommands.py",
	("browseMode", "BrowseModeTreeInterceptor"): "browseMode.py",
	("browseMode", "BrowseModeDocumentTreeInterceptor"): "browseMode.py",
	("virtualBuffers", "VirtualBuffer"): "virtualBuffers/__init__.py",
	("cursorManager", "CursorManager"): "cursorManager.py",
	("documentBase", "DocumentWithTableNavigation"): "documentBase.py",
	("editableText", "EditableText"): "editableText.py",
}


def nvdasGestures(source) -> list:
	"""``(module, class, script, identifier, "class")`` for every keyboard gesture those classes bind in NVDA's source:
	their ``__gestures`` and their scripts' ``gesture``/``gestures``."""
	found = []
	for (module, className), path in GESTURE_CLASSES.items():
		with open(os.path.join(source, *path.split("/")), encoding="utf-8") as f:
			tree = ast.parse(f.read())
		for node in ast.walk(tree):
			if not (isinstance(node, ast.ClassDef) and node.name == className):
				continue
			for item in node.body:
				if isinstance(item, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__gestures" for t in item.targets) and isinstance(item.value, ast.Dict):
					for key, value in zip(item.value.keys, item.value.values):
						if isinstance(key, ast.Constant) and isinstance(value, ast.Constant):
							found.append((module, className, value.value, key.value, "class"))
				if isinstance(item, ast.FunctionDef) and item.name.startswith("script_"):
					for decorator in item.decorator_list:
						if isinstance(decorator, ast.Call) and getattr(decorator.func, "id", None) == "script":
							for keyword in decorator.keywords:
								values = [keyword.value] if keyword.arg == "gesture" else list(getattr(keyword.value, "elts", ())) if keyword.arg == "gestures" else []
								for value in values:
									if isinstance(value, ast.Constant):
										found.append((module, className, item.name[len("script_") :], value.value, "class"))
	return [entry for entry in found if str(entry[3]).lower().startswith("kb")]


class NvdasOwnCodeTests(unittest.TestCase):
	def test_theCodeIsNvdas(self):
		import textwrap

		source = nvdaSource()
		for name, path in NVDA_CODE_FILES.items():
			with open(os.path.join(source, *path.split("/")), encoding="utf-8") as f:
				text = f.read().replace("\r\n", "\n")
			block = globals()[name].strip("\n")
			self.assertTrue(block in text or textwrap.indent(block, "\t") in text, name)

	@v130.needsJaws
	def test_onlyInsertQChanges(self):
		# With every keyboard gesture of NVDA 2026.2's own classes, and JAWS 2026's Default.JKM, the plan made without
		# taking NVDA's keystrokes differs from 1.35's in Insert+Q alone.
		bound = nvdasGestures(nvdaSource())
		self.assertIn(("globalCommands", "GlobalCommands", "quit", "kb:NVDA+q", "class"), bound)
		self.assertFalse([entry for entry in bound if nvdaApply._sameKeys(entry[3], "kb:NVDA+f4")])

		def boundScripts(gesture):
			return [entry for entry in bound if nvdaApply._sameKeys(entry[3], gesture)]

		jkm = jawsFiles.readIni(os.path.join(v130.JAWS_SCRIPTS, "enu", "Default.JKM"))
		for layout in ("desktop", "laptop"):
			now = keyPlan.planKeys(jkm, layout, boundScripts=boundScripts, nvdaLayout=layout)
			with mock.patch.object(jawsKeyMap, "MOVED_TO_JAWS_KEYS", frozenset()):
				before = keyPlan.planKeys(jkm, layout, boundScripts=boundScripts, nvdaLayout=layout)

			def keys(plan):
				return {(b.jawsKey, b.gesture, b.script, tuple(b.replaces)) for b in plan.bindings}

			def skipped(plan):
				return {(item.jawsKey, item.section, item.kind) for item in plan.skipped}

			self.assertEqual(keys(now) - keys(before), {("JAWSKey+Q", "kb:NVDA+q", "reportAppModuleInfo", ("quit",))}, layout)
			self.assertEqual(keys(before) - keys(now), set(), layout)
			self.assertEqual(skipped(before) - skipped(now), {("JAWSKey+Q", "Common Keys", keyPlan.SKIP_CONFLICT)}, layout)
			self.assertEqual(skipped(now) - skipped(before), set(), layout)


if __name__ == "__main__":
	unittest.main()
