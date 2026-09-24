# Unit tests for turning JAWS keystrokes into NVDA input gestures (jawsKeyMap, keyPlan and the
# gesture functions of nvdaApply). They use small made-up key maps and imitation NVDA classes
# that bind some of NVDA 2026.2's own gestures, so they run anywhere.
# Run: python -m unittest tests.test_keys -v

import os
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import gestureRepair, jawsFiles, jawsKeyMap, keyPlan, migrator, nvdaApply  # noqa: E402

DEFAULT_JKM = r"C:\ProgramData\Freedom Scientific\JAWS\2026\Scripts\enu\Default.JKM"

#: The laptop and common keystrokes of JAWS 2026's Default.JKM that the laptop tests need.
LAPTOP_JKM = (
	"[Keyboard Layouts]\nDesktop=Common\nLaptop=Common\n"
	"[Common Keys]\nJAWSKey+H=HotKeyHelp\nJAWSKey+J=JAWSWindow\nJAWSKey+8=KeyboardManager\nJAWSKey+T=SayWindowTitle\n"
	"JAWSKey+UpArrow=SayLine\nJAWSKey+Shift+DownArrow=SaySelectedText\nNumPadStar=RightMouseButton\n"
	"[Laptop Keys]\nJAWSKey+H=SaySentence\nInsert+h=HotKeyHelp\nJAWSKey+J=SayPriorWord\nInsert+J=JAWSWindow\n"
	"JAWSKey+8=LeftMouseButton\nInsert+8=KeyboardManager\nJAWSKey+Y=SayPriorSentence\nInsert+UpArrow=SayLine\n"
	"[DESKTOP Keys]\nJAWSKey+PageDown=SayBottomLineOfWindow\n"
	"[Laptop Modifiers]\nCapsLock=14|3|0|0|0|0|0x4000\n[Desktop Modifiers]\nInsert=17|3|0|2|0|0|0x4020800\n"
)


def _scriptable(name, module, gestures, scripts=(), bases=(object,)):
	"""A class like NVDA's scriptable classes: its own ``__gestures`` and ``script_`` methods."""
	namespace = {"__module__": module, f"_{name}__gestures": dict(gestures)}
	for script in set(scripts) | {script for script in gestures.values() if script}:
		namespace[f"script_{script}"] = lambda self, gesture: None
	return type(name, bases, namespace)


def fakeNvdaModules() -> dict:
	"""Imitation NVDA 2026.2 modules with some of the gestures NVDA binds itself."""
	globalCommands = types.ModuleType("globalCommands")
	globalCommands.GlobalCommands = _scriptable(
		"GlobalCommands",
		"globalCommands",
		{
			"kb(desktop):NVDA+upArrow": "reportCurrentLine",
			"kb(laptop):NVDA+upArrow": "review_previousLine",
			"kb(desktop):NVDA+shift+upArrow": "reportCurrentSelection",
			"kb(laptop):NVDA+shift+downArrow": "navigatorObject_firstChild",
			"kb:NVDA+control+r": "revertConfiguration",
			"kb:NVDA+control+b": "activateBrowseModeDialog",
			"kb:NVDA+t": "title",
			"kb(laptop):NVDA+enter": "review_activate",
		},
		scripts=("increaseSynthSetting", "activateInputGesturesDialog", "showGui", "leftMouseClick"),
	)
	documentBase = types.ModuleType("documentBase")
	documentBase.DocumentWithTableNavigation = _scriptable(
		"DocumentWithTableNavigation",
		"documentBase",
		{"kb:control+alt+pageUp": "firstRow"},
	)
	cursorManager = types.ModuleType("cursorManager")
	cursorManager.CursorManager = _scriptable(
		"CursorManager",
		"cursorManager",
		{"kb:alt+upArrow": "moveBySentence_back", "kb:NVDA+control+f": "find"},
		scripts=("moveByParagraph_forward", "moveByParagraph_back", "moveBySentence_forward"),
	)
	browseMode = types.ModuleType("browseMode")
	browseMode.BrowseModeTreeInterceptor = _scriptable(
		"BrowseModeTreeInterceptor",
		"browseMode",
		{"kb:NVDA+f7": "elementsList", "kb:h": "nextHeading", "kb:r": "nextRadioButton", "kb:a": "nextAnnotation"},
		scripts=("nextLandmark", "nextTextParagraph"),
	)
	browseMode.BrowseModeDocumentTreeInterceptor = _scriptable(
		"BrowseModeDocumentTreeInterceptor",
		"browseMode",
		{"kb:shift+,": "moveToStartOfContainer"},
		bases=(documentBase.DocumentWithTableNavigation, cursorManager.CursorManager, browseMode.BrowseModeTreeInterceptor),
	)
	virtualBuffers = types.ModuleType("virtualBuffers")
	virtualBuffers.VirtualBuffer = _scriptable(
		"VirtualBuffer",
		"virtualBuffers",
		{"kb:NVDA+f5": "refreshBuffer"},
		bases=(browseMode.BrowseModeDocumentTreeInterceptor,),
	)
	editableText = types.ModuleType("editableText")
	editableText.EditableText = _scriptable("EditableText", "editableText", {"kb:alt+upArrow": "caret_previousSentence"})
	return {
		module.__name__: module
		for module in (globalCommands, documentBase, cursorManager, browseMode, virtualBuffers, editableText)
	}


class FakeGestureMap:
	"""NVDA's GlobalGestureMap, as far as the add-on uses it."""

	def __init__(self):
		self._map = {}
		self.saved = 0

	def add(self, gesture, module, className, script, replace=False):
		self._map.setdefault(gesture.lower(), []).append((module, className, script))

	def save(self):
		self.saved += 1


class NvdaTestCase(unittest.TestCase):
	"""Runs with the imitation NVDA modules and empty user and locale gesture maps."""

	def setUp(self):
		patcher = mock.patch.dict(sys.modules, fakeNvdaModules())
		patcher.start()
		self.addCleanup(patcher.stop)
		inputCore = sys.modules["inputCore"]
		self.manager = types.SimpleNamespace(
			userGestureMap=FakeGestureMap(),
			localeGestureMap=FakeGestureMap(),
			getAllGestureMappings=lambda: {},
		)
		patcher = mock.patch.object(inputCore, "manager", self.manager)
		patcher.start()
		self.addCleanup(patcher.stop)

	def plan(self, text, keyboardLayout="laptop", **options):
		options.setdefault("boundScripts", nvdaApply.gestureBoundScripts)
		return keyPlan.planKeys(jawsFiles.parseIni(text), keyboardLayout, **options)


def bindings(plan, gesture=None) -> list:
	return [(b.gesture, b.className, b.script) for b in plan.bindings if gesture is None or b.gesture.lower() == gesture.lower()]


def skipped(plan, jawsKey, section=None) -> list:
	return [item for item in plan.skipped if item.jawsKey == jawsKey and (section is None or item.section == section)]


def insertKeys(plan) -> list:
	return [(key.gesture, key.jawsKey, key.script, key.capsLockKey) for key in plan.insertKeys]


class TargetTests(unittest.TestCase):
	"""Finding 1 and 6: no target may send the keystroke on; targets that depend on the keystroke."""

	def allTargets(self):
		for table in (jawsKeyMap.SCRIPT_MAP, jawsKeyMap.QUICK_NAV_MAP, jawsKeyMap.COMMAND_KEY_TARGETS):
			yield from table.values()
		for targets in jawsKeyMap.ADDITIONAL_TARGETS.values():
			yield from targets

	def test_no_target_sends_the_keystroke(self):
		for module, className, script, _description in self.allTargets():
			self.assertFalse(jawsKeyMap.sendsKeystroke(module, className, script), f"{module}.{className}.{script}")
			self.assertNotEqual(module, "editableText")
		self.assertEqual(
			[target[:3] for target in jawsKeyMap.getNvdaTargets("SayPriorSentence", "JAWSKey+Y")],
			[("cursorManager", "CursorManager", "moveBySentence_back")],
		)

	def test_sending_targets_are_dropped(self):
		extra = {
			"fakeeditscript": ("editableText", "EditableText", "caret_nextSentence", "sends"),
			"fakecopyscript": ("cursorManager", "CursorManager", "copyToClipboard", "sends"),
		}
		with mock.patch.dict(jawsKeyMap.SCRIPT_MAP, extra):
			self.assertEqual(jawsKeyMap.getNvdaTargets("FakeEditScript"), ())
			self.assertEqual(jawsKeyMap.getNvdaTargets("FakeCopyScript"), ())

	def test_paragraph_targets(self):
		self.assertEqual(jawsKeyMap.getNvdaTargets("SayNextParagraph", "P")[0][2], "nextTextParagraph")
		self.assertEqual(jawsKeyMap.getNvdaTargets("SayNextParagraph")[0][2], "nextTextParagraph")
		self.assertEqual(
			jawsKeyMap.getNvdaTargets("SayNextParagraph", "JAWSKey+Control+O")[0][:3],
			("cursorManager", "CursorManager", "moveByParagraph_forward"),
		)
		self.assertEqual(jawsKeyMap.getNvdaTargets("SayPriorParagraph", "Alt+Control+U")[0][2], "moveByParagraph_back")

	def test_quick_nav_keys(self):
		for key in ("a", "Shift+a", "H", "Dash", "Shift+Dash", "Shift+Comma", "apostrophe", "2", "Shift+1"):
			self.assertTrue(jawsKeyMap.isQuickNavKey(key), key)
		for key in ("F3", "Shift+F3", "Control+JAWSKey+b", "JAWSKey+F5", "Alt+Windows+Home", "Space", "Enter", "Control+a", "JAWSKey+Space&H"):
			self.assertFalse(jawsKeyMap.isQuickNavKey(key), key)

	def test_pass_through_only_for_windows_keys(self):
		self.assertFalse(jawsKeyMap.isPassThroughBinding("Alt+L", "SayNextWord"))
		self.assertFalse(jawsKeyMap.isPassThroughBinding("Alt+.", "SayNextCharacter"))
		self.assertFalse(jawsKeyMap.isPassThroughBinding("JAWSKey+U", "SayPriorLine"))
		for key, script in (
			("Control+RightArrow", "SayNextWord"),
			("RightArrow", "SayNextCharacter"),
			("Control+Z", "Undo"),
			("CTRL+E", "ActivateSearchBox"),
			("Alt+Shift", "SwitchInputLanguage(1)"),
			("Windows+Space", "SwitchInputLanguageAndKeyboardLayout"),
			("Space", "VirtualSpacebar"),
			("Alt+Down Arrow", "OpenListBox"),
			("Tab", "Tab"),
		):
			self.assertTrue(jawsKeyMap.isPassThroughBinding(key, script), key)


class PlanTests(NvdaTestCase):
	def test_capslock_sentence_key_sends_nothing(self):
		"""Finding 1: Caps Lock+Y must not be bound to EditableText, which would type Y."""
		plan = self.plan(LAPTOP_JKM, nvdaLayout="laptop", overrideConflicts=True)
		self.assertEqual(bindings(plan, "kb(laptop):NVDA+y"), [("kb(laptop):NVDA+y", "CursorManager", "moveBySentence_back")])
		self.assertFalse([b for b in plan.bindings if b.module == "editableText"])

	def test_capslock_decides_laptop_keys(self):
		"""Finding 2: in the Laptop layout the JAWSKey (Caps Lock) keystroke decides NVDA+key."""
		for nvdaLayout in ("laptop", None):
			plan = self.plan(LAPTOP_JKM, nvdaLayout=nvdaLayout)
			for gesture in ("kb:NVDA+h", "kb(laptop):NVDA+h", "kb:NVDA+j", "kb(laptop):NVDA+j"):
				self.assertEqual(bindings(plan, gesture), [], (nvdaLayout, gesture))
			self.assertEqual(bindings(plan, "kb(laptop):NVDA+8"), [("kb(laptop):NVDA+8", "GlobalCommands", "leftMouseClick")])
			# The Insert keystrokes of those keys run their own command when Insert is held (see insertKeys).
			self.assertEqual(
				insertKeys(plan),
				[
					("kb(laptop):NVDA+h", "Insert+h", "activateInputGesturesDialog", "JAWSKey+H"),
					("kb(laptop):NVDA+j", "Insert+J", "showGui", "JAWSKey+J"),
					("kb(laptop):NVDA+8", "Insert+8", "activateInputGesturesDialog", "JAWSKey+8"),
				],
				nvdaLayout,
			)
			self.assertEqual(skipped(plan, "Insert+h", "Laptop Keys"), [])
			self.assertEqual(skipped(plan, "JAWSKey+H", "Laptop Keys")[0].kind, keyPlan.SKIP_NO_EQUIVALENT)
		# NVDA's desktop layout keeps the common keystrokes when NVDA may use it.
		plan = self.plan(LAPTOP_JKM, nvdaLayout=None)
		self.assertEqual(bindings(plan, "kb(desktop):NVDA+h"), [("kb(desktop):NVDA+h", "GlobalCommands", "activateInputGesturesDialog")])
		self.assertEqual(bindings(plan, "kb(desktop):NVDA+j"), [("kb(desktop):NVDA+j", "GlobalCommands", "showGui")])
		# When only the laptop layout is used, the common keystroke is reported as replaced by the layout.
		plan = self.plan(LAPTOP_JKM, nvdaLayout="laptop")
		reason = skipped(plan, "JAWSKey+H", "Common Keys")[0]
		self.assertEqual((reason.kind, reason.reason), (keyPlan.SKIP_DUPLICATE, "the JAWS Laptop layout uses this keystroke for SaySentence"))

	def test_capslock_wins_whatever_the_file_order(self):
		text = LAPTOP_JKM.replace("JAWSKey+H=SaySentence\nInsert+h=HotKeyHelp\n", "Insert+h=HotKeyHelp\nJAWSKey+H=SaySentence\n")
		plan = self.plan(text, nvdaLayout="laptop")
		self.assertEqual(bindings(plan, "kb(laptop):NVDA+h"), [])
		self.assertEqual(insertKeys(plan)[0], ("kb(laptop):NVDA+h", "Insert+h", "activateInputGesturesDialog", "JAWSKey+H"))

	def test_common_capslock_keystroke_beats_laptop_insert(self):
		text = "[Common Keys]\nJAWSKey+Z=VirtualPCCursorToggle\n[Laptop Keys]\nInsert+Z=ShutDownJAWS\n[Laptop Modifiers]\nCapsLock=14|3|0|0|0|0|0x4000\n"
		plan = self.plan(text, nvdaLayout="laptop", boundScripts=None)
		self.assertEqual(bindings(plan), [("kb:NVDA+z", "GlobalCommands", "toggleVirtualBufferPassThrough")])
		# Caps Lock keeps the gesture; Insert+Z runs its own command.
		self.assertEqual(insertKeys(plan), [("kb(laptop):NVDA+z", "Insert+Z", "quit", "JAWSKey+Z")])
		self.assertEqual(skipped(plan, "Insert+Z"), [])

	def test_layouts_in_use_decide_same_and_conflict(self):
		"""Finding 4: a common kb: keystroke is judged in the NVDA layouts that will be used."""
		laptop = self.plan(LAPTOP_JKM, nvdaLayout="laptop")
		item = skipped(laptop, "JAWSKey+UpArrow", "Common Keys")[0]
		self.assertEqual((item.kind, item.reason), (keyPlan.SKIP_CONFLICT, "NVDA already uses this keystroke for review_previousLine"))
		# The laptop section's Insert+UpArrow is the same command, so it says nothing more.
		self.assertEqual(skipped(laptop, "Insert+UpArrow"), [])
		override = self.plan(LAPTOP_JKM, nvdaLayout="laptop", overrideConflicts=True)
		self.assertEqual(bindings(override, "kb(laptop):NVDA+upArrow"), [("kb(laptop):NVDA+upArrow", "GlobalCommands", "reportCurrentLine")])
		desktop = self.plan(LAPTOP_JKM, "desktop", nvdaLayout="desktop")
		self.assertEqual(skipped(desktop, "JAWSKey+UpArrow", "Common Keys")[0].kind, keyPlan.SKIP_SAME)
		self.assertEqual(
			bindings(desktop, "kb(desktop):NVDA+shift+downArrow"),
			[("kb(desktop):NVDA+shift+downArrow", "GlobalCommands", "reportCurrentSelection")],
		)
		self.assertEqual(skipped(desktop, "JAWSKey+Shift+DownArrow"), [])
		# Both layouts: bound where free, and the other layout's conflict named.
		both = self.plan(LAPTOP_JKM, "desktop", nvdaLayout=None)
		self.assertEqual(bindings(both, "kb(desktop):NVDA+shift+downArrow")[0][2], "reportCurrentSelection")
		item = skipped(both, "JAWSKey+Shift+DownArrow", "Common Keys")[0]
		self.assertEqual(item.kind, keyPlan.SKIP_CONFLICT)
		self.assertIn("navigatorObject_firstChild (NVDA's laptop keyboard layout)", item.reason)
		# Keys that are free everywhere stay kb: gestures, and desktop-only keys are left out on a laptop.
		self.assertIn(("kb:NVDA+shift+b", "GlobalCommands", "say_battery_status"), bindings(self.plan("[Common Keys]\nJAWSKey+Shift+B=SayBatteryLevel\n", nvdaLayout="laptop")))
		self.assertEqual(skipped(laptop, "NumPadStar", "Common Keys")[0].kind, keyPlan.SKIP_LAYOUT)

	def test_virtual_keys_ask_before_taking_over(self):
		"""Finding 3: only quick navigation keys take over NVDA's own commands without asking."""
		text = (
			"[virtual keys]\nControl+JAWSKey+r=SelectaRegion\nControl+JAWSKey+b=SelectAButtonFormField\n"
			"JAWSKey+F5=SelectAFormField\nJAWSKey+F6=SelectAHeading\n"
			"[Quick Navigation Keys]\nr=MoveToNextRegion\na=MoveToNextRadioButton\nShift+Comma=StepToStartOfElement\n"
		)
		plan = self.plan(text, "desktop", nvdaLayout="desktop")
		for key, name in (("Control+JAWSKey+r", "revertConfiguration"), ("Control+JAWSKey+b", "activateBrowseModeDialog"), ("JAWSKey+F5", "refreshBuffer")):
			item = skipped(plan, key)[0]
			self.assertEqual(item.kind, keyPlan.SKIP_CONFLICT, key)
			self.assertIn(name, item.reason)
		self.assertEqual(bindings(plan, "kb:NVDA+f6"), [("kb:NVDA+f6", "BrowseModeTreeInterceptor", "elementsList")])
		letters = {b.jawsKey: b for b in plan.bindings if b.section == "Quick Navigation Keys"}
		self.assertEqual((letters["r"].script, letters["r"].replaces), ("nextLandmark", ["nextRadioButton"]))
		self.assertEqual((letters["a"].script, letters["a"].replaces), ("nextRadioButton", ["nextAnnotation"]))
		# NVDA's own shift+comma does the same, now that BrowseModeDocumentTreeInterceptor is searched.
		self.assertEqual(skipped(plan, "Shift+Comma")[0].kind, keyPlan.SKIP_SAME)
		override = self.plan(text, "desktop", nvdaLayout="desktop", overrideConflicts=True)
		f5 = [b for b in override.bindings if b.jawsKey == "JAWSKey+F5"]
		# NVDA+F5 replaces the same command in both NVDA layouts, so it stays a kb: gesture.
		self.assertEqual([(b.gesture, b.replaces, b.unbind) for b in f5], [("kb:NVDA+f5", ["refreshBuffer"], [])])
		# Without the quick navigation letters, the other virtual cursor commands are still planned.
		noLetters = self.plan(text, "desktop", nvdaLayout="desktop", quickNavLetters=False)
		self.assertEqual(skipped(noLetters, "r")[0].kind, keyPlan.SKIP_QUICKNAV)
		self.assertEqual(bindings(noLetters, "kb:NVDA+f6")[0][2], "elementsList")

	def test_override_unbinds_a_more_specific_class(self):
		"""Finding 5: a global command only runs in documents if their own binding is removed."""
		text = "[Common Keys]\nAlt+Control+ExtendedPageUp=IncreaseVoiceRateTemporary\n"
		plan = self.plan(text, "desktop", nvdaLayout="desktop")
		self.assertEqual(skipped(plan, "Alt+Control+ExtendedPageUp")[0].kind, keyPlan.SKIP_CONFLICT)
		plan = self.plan(text, "desktop", nvdaLayout="desktop", overrideConflicts=True)
		(binding,) = plan.bindings
		self.assertEqual((binding.gesture, binding.script, binding.replaces), ("kb:control+alt+pageUp", "increaseSynthSetting", ["firstRow"]))
		self.assertEqual(binding.unbind, [("documentBase", "DocumentWithTableNavigation")])
		# A browse mode command wins in browse mode anyway: nothing to unbind.
		plan = self.plan("[virtual keys]\nControl+JAWSKey+r=SelectaRegion\n", "desktop", nvdaLayout="desktop", overrideConflicts=True)
		self.assertEqual([(b.replaces, b.unbind) for b in plan.bindings], [(["revertConfiguration"], [])])

	def test_user_gestures_cannot_be_replaced(self):
		"""Finding 5: a gestures.ini binding comes first in NVDA's list, so a new one can't replace it."""
		self.manager.userGestureMap.add("kb:NVDA+shift+2", "globalCommands", "GlobalCommands", "toggleReportFontName")
		text = "[Common Keys]\nJAWSKey+Shift+2=SetPunctuationLevel\n"
		plan = self.plan(text, "desktop", nvdaLayout="desktop", overrideConflicts=True)
		self.assertEqual(plan.bindings, [])
		item = skipped(plan, "JAWSKey+Shift+2")[0]
		self.assertEqual(item.kind, keyPlan.SKIP_CONFLICT)
		self.assertIn("gestures.ini", item.reason)
		# The user unbinding the class's keystroke blocks it too.
		self.manager.userGestureMap._map.clear()
		self.manager.userGestureMap.add("kb:NVDA+shift+2", "globalCommands", "GlobalCommands", None)
		plan = self.plan(text, "desktop", nvdaLayout="desktop")
		self.assertEqual((plan.bindings, skipped(plan, "JAWSKey+Shift+2")[0].kind), ([], keyPlan.SKIP_CONFLICT))
		# Earlier migrations: the same binding counts as already there.
		self.manager.userGestureMap._map.clear()
		self.manager.userGestureMap.add("kb:NVDA+shift+2", "globalCommands", "GlobalCommands", "cycleSpeechSymbolLevel")
		self.assertEqual(skipped(self.plan(text, "desktop", nvdaLayout="desktop"), "JAWSKey+Shift+2")[0].kind, keyPlan.SKIP_SAME)

	def test_paragraph_and_classic_laptop_keys(self):
		"""Finding 6: paragraph commands off quick navigation keys, and Alt+letter keys are not Windows keys."""
		text = (
			"[Laptop Keys]\nJAWSKey+Control+O=SayNextParagraph\n[Quick Navigation Keys]\nP=SayNextParagraph\n"
			"[Classic Laptop Keys]\nAlt+L=SayNextWord\nAlt+Control+U=SayPriorParagraph\nShift+DownArrow=SelectNextLine\n"
			"[Laptop Modifiers]\nCapsLock=14|3|0|0|0|0|0x4000\n[Classic Laptop Modifiers]\nInsert=17|3|0|2|0|0|0x4020800\n"
		)
		plan = self.plan(text, nvdaLayout="laptop", boundScripts=None, layouts=["laptop", "classic laptop"])
		self.assertIn(("kb(laptop):NVDA+control+o", "CursorManager", "moveByParagraph_forward"), bindings(plan))
		self.assertIn(("kb:p", "BrowseModeTreeInterceptor", "nextTextParagraph"), bindings(plan))
		self.assertIn(("kb(laptop):control+alt+u", "CursorManager", "moveByParagraph_back"), bindings(plan))
		self.assertEqual(skipped(plan, "Alt+L")[0].kind, keyPlan.SKIP_NO_EQUIVALENT)
		self.assertEqual(skipped(plan, "Shift+DownArrow")[0].kind, keyPlan.SKIP_PASSTHROUGH)

	def test_reverse_map_lists_layout_keystrokes_first(self):
		reverse = keyPlan.buildReverseMap(jawsFiles.parseIni(LAPTOP_JKM), "laptop")
		self.assertEqual(reverse["kb(laptop):h+nvda"][0], ("JAWSKey+H", "SaySentence", "Laptop Keys"))


class NvdaApplyTests(NvdaTestCase):
	def test_gesture_classes_include_subclasses(self):
		names = [(cls.__module__, cls.__name__) for cls in nvdaApply._gestureClasses()]
		for location in (("browseMode", "BrowseModeDocumentTreeInterceptor"), ("virtualBuffers", "VirtualBuffer"), ("editableText", "EditableText")):
			self.assertIn(location, names)

	def test_bound_scripts_report_layout_and_source(self):
		found = nvdaApply.gestureBoundScripts("kb:NVDA+upArrow")
		self.assertIn(("globalCommands", "GlobalCommands", "reportCurrentLine", "kb(desktop):NVDA+upArrow", "class"), found)
		self.assertIn(("globalCommands", "GlobalCommands", "review_previousLine", "kb(laptop):NVDA+upArrow", "class"), found)
		self.assertEqual(nvdaApply.gestureBoundScripts("kb(desktop):NVDA+shift+downArrow"), [])
		# Gestures are named after the class that binds them, once.
		self.assertEqual(nvdaApply.gestureBoundScripts("kb:r"), [("browseMode", "BrowseModeTreeInterceptor", "nextRadioButton", "kb:r", "class")])
		self.assertEqual(nvdaApply.gestureBoundScripts("kb:NVDA+f5"), [("virtualBuffers", "VirtualBuffer", "refreshBuffer", "kb:NVDA+f5", "class")])
		self.manager.userGestureMap.add("kb(laptop):NVDA+t", "globalCommands", "GlobalCommands", None)
		self.assertIn(("globalCommands", "GlobalCommands", None, "kb(laptop):nvda+t", "user"), nvdaApply.gestureBoundScripts("kb:NVDA+t"))

	def test_add_gestures_unbinds(self):
		binding = keyPlan.GestureBinding(
			"kb:control+alt+pageUp", "globalCommands", "GlobalCommands", "increaseSynthSetting", "", "Alt+Control+PageUp", "IncreaseVoiceRateTemporary", "Common Keys",
			replaces=["firstRow"], unbind=[("documentBase", "DocumentWithTableNavigation")],
		)
		added, failed = nvdaApply.addGestures([binding])
		self.assertEqual((added, failed, self.manager.userGestureMap.saved), (1, [], 1))
		self.assertEqual(
			self.manager.userGestureMap._map["kb:control+alt+pageup"],
			[("globalCommands", "GlobalCommands", "increaseSynthSetting"), ("documentBase", "DocumentWithTableNavigation", None)],
		)

	def test_keystroke_help_finds_browse_mode_keys_anywhere(self):
		"""Finding 6: outside browse mode NVDA's gesture list leaves browse mode commands out."""
		inputCore = sys.modules["inputCore"]
		with mock.patch.object(inputCore, "getDisplayTextForGestureIdentifier", lambda identifier: ("keyboard", identifier.split(":", 1)[1]), create=True):
			self.assertEqual(nvdaApply.gesturesForScript("browseMode", "BrowseModeTreeInterceptor", "nextHeading"), ["h"])
			self.assertEqual(nvdaApply.gesturesForScript("virtualBuffers", "VirtualBuffer", "refreshBuffer"), ["nvda+f5"])
			self.manager.userGestureMap.add("kb:h", "browseMode", "BrowseModeTreeInterceptor", None)
			self.assertEqual(nvdaApply.gesturesForScript("browseMode", "BrowseModeTreeInterceptor", "nextHeading"), [])


class PlanKeyboardTests(unittest.TestCase):
	"""Finding 4: migrator passes NVDA's keyboard layout when the migration sets it in the normal configuration."""

	def nvdaLayoutPassed(self, settings=True, target=migrator.TARGET_NORMAL, layout="laptop"):
		options = types.SimpleNamespace(scope="both", quickNavLetters=True, overrideConflicts=False, settings=settings, target=target)
		plan = types.SimpleNamespace(
			options=options,
			index=types.SimpleNamespace(defaultJkm=lambda scope: jawsFiles.IniFile(), leasey=types.SimpleNamespace(found=False)),
			jawsKeyboardLayout="laptop",
			chosenKeyboardLayouts=lambda: [],
			nvdaKeyboardLayout=lambda: layout,
			keys=keyPlan.KeyPlan(),
		)
		with mock.patch.object(migrator.keyPlan, "planKeys", return_value=keyPlan.KeyPlan()) as planKeys:
			migrator.planKeyboard(plan)
		return planKeys.call_args.kwargs["nvdaLayout"]

	def test_nvda_layout(self):
		self.assertEqual(self.nvdaLayoutPassed(), "laptop")
		self.assertIsNone(self.nvdaLayoutPassed(target=migrator.TARGET_PROFILE))
		self.assertIsNone(self.nvdaLayoutPassed(settings=False))
		self.assertIsNone(self.nvdaLayoutPassed(layout=""))


@unittest.skipUnless(os.path.isfile(DEFAULT_JKM), "JAWS 2026's Default.JKM is not on this computer")
class RealKeyMapTests(NvdaTestCase):
	"""JAWS 2026's own key map, read only."""

	@classmethod
	def setUpClass(cls):
		cls.jkm = jawsFiles.readIni(DEFAULT_JKM)

	def test_laptop_layout(self):
		for nvdaLayout in ("laptop", None):
			plan = keyPlan.planKeys(self.jkm, "Laptop", boundScripts=nvdaApply.gestureBoundScripts, nvdaLayout=nvdaLayout)
			self.assertFalse([b for b in plan.bindings if jawsKeyMap.sendsKeystroke(b.module, b.className, b.script)])
			self.assertEqual(bindings(plan, "kb(laptop):NVDA+y"), [("kb(laptop):NVDA+y", "CursorManager", "moveBySentence_back")])
			for gesture in ("kb(laptop):NVDA+h", "kb(laptop):NVDA+j", "kb:NVDA+h", "kb:NVDA+j"):
				self.assertEqual(bindings(plan, gesture), [], gesture)
			self.assertEqual(skipped(plan, "Control+JAWSKey+r", "virtual keys")[0].kind, keyPlan.SKIP_CONFLICT)

	def test_classic_laptop_alt_keys(self):
		plan = keyPlan.planKeys(self.jkm, "Classic Laptop", nvdaLayout="laptop")
		for key in ("Alt+L", "Alt+J", "Alt+N", "Alt+M", "Alt+.", "Alt+Y"):
			self.assertEqual(skipped(plan, key, "Classic Laptop Keys")[0].kind, keyPlan.SKIP_NO_EQUIVALENT, key)


#: gestures.ini after a version 1.2 migration with the JAWS Laptop layout, as NVDA saves it, with
#: some of the user's own bindings and a comment of theirs.
AFTER_12 = (
	"[globalCommands.GlobalCommands]\n"
	"    toggleScreenCurtain = kb:control+nvda+s\n"
	"    None = kb:nvda+q\n"
	"    activateInputGesturesDialog = kb:h+nvda, kb(laptop):h+nvda\n"
	"    showGui = kb:j+nvda, kb(laptop):j+nvda\n"
	"    cycleSpeechSymbolLevel = kb:2+nvda+shift\n"
	"# the user's own note\n"
	"[editableText.EditableText]\n"
	"    caret_previousSentence = kb(laptop):nvda+y, kb(desktop):alt+numpadminus\n"
	"[cursorManager.CursorManager]\n"
	"    moveBySentence_back = kb(laptop):nvda+y\n"
	"[browseMode.BrowseModeTreeInterceptor]\n"
	"    elementsList = kb:control+nvda+r, kb:b+control+nvda, kb:f5+nvda, kb:f6+nvda\n"
	"    nextNotLinkBlock = kb:enter+nvda\n"
	"    nextLandmark = kb:r\n"
	"    nextTab = \"kb:'\"\n"
	"[appModules.notepad.AppModule]\n"
	"    myScript = kb:control+shift+x\n"
)
#: What version 1.3 leaves of it.
REPAIRED_12 = (
	"[globalCommands.GlobalCommands]\n"
	"    toggleScreenCurtain = kb:control+nvda+s\n"
	"    None = kb:nvda+q\n"
	"    activateInputGesturesDialog = kb(desktop):h+nvda\n"
	"    showGui = kb(desktop):j+nvda\n"
	"    cycleSpeechSymbolLevel = kb:2+nvda+shift\n"
	"# the user's own note\n"
	"[cursorManager.CursorManager]\n"
	"    moveBySentence_back = kb(laptop):nvda+y\n"
	"[browseMode.BrowseModeTreeInterceptor]\n"
	"    elementsList = kb:f6+nvda\n"
	"    nextNotLinkBlock = kb(desktop):enter+nvda\n"
	"    nextLandmark = kb:r\n"
	"    nextTab = \"kb:'\"\n"
	"[appModules.notepad.AppModule]\n"
	"    myScript = kb:control+shift+x\n"
)
#: gestures.ini before that migration: the user's own bindings.
BEFORE_12 = (
	"[globalCommands.GlobalCommands]\n"
	"    toggleScreenCurtain = kb:control+nvda+s\n"
	"    None = kb:nvda+q\n"
	"[appModules.notepad.AppModule]\n"
	"    myScript = kb:control+shift+x\n"
)
#: The keyboard part of that migration's report.txt, as versions 1.0 to 1.2 wrote it.
REPORT_12 = (
	"=== JAWS Migration Assistant report\n"
	"Migrated from JAWS 2026.\n"
	"\n"
	"=== Keyboard Manager and Navigation Quick Keys\n"
	"15 JAWS keystrokes became NVDA input gestures. gestures.ini was backed up first.\n"
	"JAWS keyboard layouts found: Desktop, Laptop (in use), Kinesis, Classic Laptop. Keystrokes brought over from: Laptop.\n"
	"  - JAWSKey+H: Open the Input Gestures dialog [kb:NVDA+h]\n"
	"  - Insert+h: Open the Input Gestures dialog [kb(laptop):NVDA+h]\n"
	"  - JAWSKey+J: Open the NVDA menu [kb:NVDA+j]\n"
	"  - Insert+J: Open the NVDA menu [kb(laptop):NVDA+j]\n"
	"  - JAWSKey+SHIFT+2: Cycle the symbol (punctuation) level [kb:NVDA+shift+2]\n"
	"  - JAWSKey+Y: Move to the previous sentence and read it (browse mode documents) [kb(laptop):NVDA+y]\n"
	"  - JAWSKey+Y: Move the caret to the previous sentence and read it (Word and other editable text) [kb(laptop):NVDA+y]\n"
	"  - Alt+NumPadMinus: Move the caret to the previous sentence and read it (Word and other editable text) [kb(desktop):alt+numpadMinus]\n"
	"  - Control+JAWSKey+r: Open the Elements List (replaces NVDA's revertConfiguration) [kb:NVDA+control+r]\n"
	"  - Control+JAWSKey+b: Open the Elements List (replaces NVDA's activateBrowseModeDialog) [kb:NVDA+control+b]\n"
	"  - JAWSKey+F5: Open the Elements List [kb:NVDA+f5]\n"
	"  - JAWSKey+F6: Open the Elements List [kb:NVDA+f6]\n"
	"  - JAWSKey+Enter: Skip forward past a block of links (replaces NVDA's review_activate) [kb:NVDA+enter]\n"
	"  - r: Move to the next landmark (region) (replaces NVDA's nextRadioButton) [kb:r]\n"
	"  - apostrophe: Move to the next tab [kb:']\n"
	"  - JAWSKey+[: Route the mouse [kb(laptop):NVDA+[]\n"
	"  - 12 already the same in NVDA\n"
	"\n"
	"--- Keystrokes kept for NVDA\n"
	"  - JAWSKey+Q (ScriptFileName): NVDA already uses this keystroke for quit [kb:NVDA+q]\n"
	"\n"
	"=== Sounds\n"
)
#: The JAWS key map those keystrokes came from.
KEYMAP_12 = LAPTOP_JKM + (
	"[virtual keys]\nControl+JAWSKey+r=SelectaRegion\nControl+JAWSKey+b=SelectAButtonFormField\nJAWSKey+F5=SelectAFormField\n"
	"JAWSKey+F6=SelectAHeading\nJAWSKey+Enter=MoveToNextNonLinkText\n"
)


class GestureRepairCase(NvdaTestCase):
	"""An NVDA settings folder in a temporary folder, for the gesture repair."""

	def setUp(self):
		super().setUp()
		temporary = tempfile.TemporaryDirectory(prefix="jawsMigrator-gestureRepair-")
		self.addCleanup(temporary.cleanup)
		self.configDir = temporary.name
		self.keyMap = jawsFiles.parseIni(KEYMAP_12)

	def writeFile(self, relative: str, text: str) -> str:
		path = os.path.join(self.configDir, relative)
		os.makedirs(os.path.dirname(path), exist_ok=True)
		with open(path, "w", encoding="utf-8", newline="") as stream:
			stream.write(text)
		return path

	def gestures(self, text: str = AFTER_12, migration: str = "20260915-093000", copy: str | None = BEFORE_12, report: str | None = REPORT_12) -> str:
		"""NVDA's settings folder after a migration: gestures.ini, NVDA's copy of it in memory, the migration folder."""
		folder = os.path.join("jawsMigrator", "migrations", migration)
		if copy is not None:
			self.writeFile(os.path.join(folder, gestureRepair.COPY_NAME), copy)
		if report is not None:
			self.writeFile(os.path.join(folder, gestureRepair.REPORT_NAME), report)
		self.manager.userGestureMap._map.clear()
		for gesture, module, className, script in gestureRepair.bindingsOf(text):
			self.manager.userGestureMap.add(gesture, module, className, None if script == "None" else script)
		return self.writeFile(gestureRepair.GESTURES_FILE, text)

	def repair(self, keyMap="default"):
		log = []
		result = gestureRepair.repairGestures(self.configDir, log.append, boundScripts=nvdaApply.gestureBoundScripts, keyMap=self.keyMap if keyMap == "default" else keyMap)
		return result, log

	def read(self, path: str) -> str:
		with open(path, encoding="utf-8", newline="") as stream:
			return stream.read()


class GestureRepairTests(GestureRepairCase):
	"""The one-time repair of the keystrokes versions 1.0 to 1.2 wrote into gestures.ini."""

	def test_report_is_read(self):
		count, listed, names = gestureRepair.readReport(REPORT_12)
		self.assertEqual((count, names), (15, {"Laptop"}))
		self.assertIn(("Control+JAWSKey+r", "kb:NVDA+control+r"), listed)
		self.assertIn(("JAWSKey+[", "kb(laptop):NVDA+["), listed)
		self.assertNotIn("kb:NVDA+q", [gesture for _key, gesture in listed])

	def test_repair_with_a_copy(self):
		path = self.gestures()
		self.assertTrue(gestureRepair.needsRepair(self.configDir, nvdaApply.gestureBoundScripts, self.keyMap))
		result, log = self.repair()
		self.assertEqual(result.failed, [])
		self.assertEqual(self.read(path), REPAIRED_12)
		# NVDA+H and NVDA+J twice, two sentence keys, NVDA+Control+R, NVDA+Control+B, NVDA+F5 and NVDA+Enter.
		self.assertEqual(len(result.changes), 10)
		self.assertEqual(len(log), 10)
		self.assertTrue(any("kb:control+nvda+r" in line and "revertConfiguration" in line for line in log), log)
		self.assertTrue(any("kb(laptop):h+nvda" in line and "SaySentence" in line for line in log), log)

	def test_repair_without_a_copy(self):
		"""No gestures.ini before the migration: the report alone shows what the assistant added."""
		path = self.gestures(copy=None)
		self.repair()
		self.assertEqual(self.read(path), REPAIRED_12)

	def test_repair_without_any_record_of_the_migration(self):
		"""No migration folder: only what nothing but the assistant writes goes."""
		path = self.gestures(copy=None, report=None)
		result, _log = self.repair()
		self.assertEqual({(change.script, change.newGesture) for change in result.changes}, {("caret_previousSentence", None)})
		self.assertEqual(self.read(path), AFTER_12.replace("[editableText.EditableText]\n    caret_previousSentence = kb(laptop):nvda+y, kb(desktop):alt+numpadminus\n", ""))

	def test_copies_alone_show_the_assistants_bindings(self):
		"""A migration whose report is gone: whatever is in none of the copies came from it."""
		path = self.gestures(report=None)
		self.repair()
		self.assertEqual(self.read(path), REPAIRED_12)

	def test_users_own_bindings_are_kept(self):
		"""Bindings the user had before the first migration stay, even ones like the assistant's."""
		before = BEFORE_12.replace("    None = kb:nvda+q\n", "    None = kb:nvda+q\n    activateInputGesturesDialog = kb(laptop):h+nvda\n") + "[browseMode.BrowseModeTreeInterceptor]\n    elementsList = kb:f5+nvda\n"
		path = self.gestures(copy=before)
		self.repair()
		expected = REPAIRED_12.replace("activateInputGesturesDialog = kb(desktop):h+nvda\n", "activateInputGesturesDialog = kb(desktop):h+nvda, kb(laptop):h+nvda\n")
		expected = expected.replace("elementsList = kb:f6+nvda\n", "elementsList = kb:f5+nvda, kb:f6+nvda\n")
		self.assertEqual(self.read(path), expected)

	def test_earlier_migration_without_a_copy(self):
		"""The first migration had no gestures.ini to copy; a later one's copy holds its keystrokes."""
		self.gestures(copy=None, migration="20260901-080000")
		path = self.gestures(copy=AFTER_12, report=REPORT_12.replace("15 JAWS keystrokes became", "0 JAWS keystrokes became"), migration="20260915-093000")
		self.repair()
		self.assertEqual(self.read(path), REPAIRED_12)

	def test_second_repair_changes_nothing(self):
		path = self.gestures()
		self.repair()
		repaired = self.read(path)
		self.manager.userGestureMap._map.clear()
		for gesture, module, className, script in gestureRepair.bindingsOf(repaired):
			self.manager.userGestureMap.add(gesture, module, className, None if script == "None" else script)
		self.assertFalse(gestureRepair.needsRepair(self.configDir, nvdaApply.gestureBoundScripts, self.keyMap))
		result, log = self.repair()
		self.assertEqual((result.changes, log), ([], []))
		self.assertEqual(self.read(path), repaired)

	def test_desktop_layout_keeps_nvda_h(self):
		"""Without the JAWS Laptop layout, NVDA+H and NVDA+J are what JAWS does."""
		report = REPORT_12.replace("Keystrokes brought over from: Laptop.", "Keystrokes brought over from: Desktop.")
		report = "".join(line for line in report.splitlines(keepends=True) if "kb(laptop)" not in line)
		text = AFTER_12.replace(", kb(laptop):h+nvda", "").replace(", kb(laptop):j+nvda", "").replace("kb(laptop):nvda+y, ", "")
		text = text.replace("moveBySentence_back = kb(laptop):nvda+y", "moveBySentence_back = kb(desktop):alt+numpadminus")
		path = self.gestures(text=text, report=report)
		self.repair()
		repaired = self.read(path)
		self.assertIn("activateInputGesturesDialog = kb:h+nvda\n", repaired)
		self.assertIn("showGui = kb:j+nvda\n", repaired)
		self.assertIn("elementsList = kb:f6+nvda\n", repaired)

	def test_asked_overrides_from_layout_keys_stay(self):
		"""The Laptop layout's Caps Lock+Control+O took NVDA+Control+O only when the user asked for it."""
		self.writeFile(os.path.join("jawsMigrator", "state.json"), '{"lastMigration": {"keyboardLayouts": ["laptop"]}}')
		text = AFTER_12 + "[browseMode.BrowseModeTreeInterceptor]\n    nextTextParagraph = kb(laptop):control+nvda+o\n"
		report = REPORT_12.replace("  - apostrophe:", "  - JAWSKey+Control+O: Move to the next paragraph of text and read it [kb(laptop):NVDA+control+o]\n  - apostrophe:")
		sys.modules["globalCommands"].GlobalCommands._GlobalCommands__gestures["kb:NVDA+control+o"] = "activateObjectPresentationDialog"
		keyMap = jawsFiles.parseIni(KEYMAP_12.replace("[Laptop Keys]\n", "[Laptop Keys]\nJAWSKey+Control+O=SayNextParagraph\n"))
		for source in (keyMap, jawsFiles.IniFile()):
			path = self.gestures(text=text, report=report)
			self.repair(keyMap=source)
			self.assertIn("nextTextParagraph = kb(laptop):control+nvda+o\n", self.read(path))

	def test_file_that_cannot_be_read_exactly_is_left_alone(self):
		path = self.gestures()
		with open(path, "ab") as stream:
			stream.write(b"\xff\xfe broken\n")
		with open(path, "rb") as stream:
			before = stream.read()
		self.assertIsNone(gestureRepair.needsRepair(self.configDir, nvdaApply.gestureBoundScripts, self.keyMap))
		result, _log = self.repair()
		self.assertTrue(result.failed)
		with open(path, "rb") as stream:
			self.assertEqual(stream.read(), before)


class RepairOnceTests(GestureRepairCase):
	"""repairOnce: once, after a backup, then NVDA reads gestures.ini again; done() is always called once."""

	def setUp(self):
		super().setUp()
		self.state = {}
		self.done = []
		self.announced = []
		self.manager.loadUserGestureMap = mock.Mock()
		from jawsMigrator import debugLog, state

		class SyncThread:
			def __init__(self, target=None, name=None, daemon=None):
				self.target = target

			def start(self):
				self.target()

		for patcher in (
			mock.patch.object(state, "get", lambda key: self.state.get(key, 0)),
			mock.patch.object(state, "set", lambda key, value, persist=True: self.state.__setitem__(key, value)),
			mock.patch.object(gestureRepair.nvdaEnv, "configDir", lambda: self.configDir),
			mock.patch.object(gestureRepair.nvdaEnv, "shouldWriteToDisk", lambda: True),
			mock.patch.object(gestureRepair, "_readJawsKeyMap", lambda configDir: self.keyMap),
			mock.patch.object(migrator, "_backupFirst", lambda reason: types.SimpleNamespace(path="backup")),
			mock.patch.object(debugLog, "note", lambda message: None),
			mock.patch.object(debugLog, "error", lambda message, exc_info=True: None),
			mock.patch("threading.Thread", SyncThread),
			mock.patch("wx.CallAfter", lambda function, *args: function(*args)),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def run_once(self):
		gestureRepair.repairOnce(self.announced.append, lambda: self.done.append(True))

	def test_repairs_once(self):
		path = self.gestures()
		self.run_once()
		self.assertEqual(self.read(path), REPAIRED_12)
		self.assertEqual(self.manager.loadUserGestureMap.call_count, 1)
		self.assertEqual(self.state, {gestureRepair.STATE_KEY: gestureRepair.REPAIR_VERSION})
		self.assertEqual(len(self.announced), 1)
		self.assertIn("repaired 10 keystrokes", self.announced[0])
		self.assertEqual(self.done, [True])
		self.run_once()
		self.assertEqual((len(self.announced), self.done, self.manager.loadUserGestureMap.call_count), (1, [True, True], 1))

	def test_nothing_to_repair(self):
		path = self.gestures(text=REPAIRED_12)
		self.run_once()
		self.assertEqual(self.read(path), REPAIRED_12)
		self.assertEqual((self.state, self.announced, self.done), ({gestureRepair.STATE_KEY: gestureRepair.REPAIR_VERSION}, [], [True]))
		self.manager.loadUserGestureMap.assert_not_called()

	def test_nothing_written_when_nvda_must_not_write(self):
		path = self.gestures()
		with mock.patch.object(gestureRepair.nvdaEnv, "shouldWriteToDisk", lambda: False):
			self.run_once()
		self.assertEqual((self.read(path), self.state, self.done), (AFTER_12, {}, [True]))

	def test_failed_backup_repairs_nothing(self):
		path = self.gestures()

		def fail(reason):
			raise OSError("disk full")

		with mock.patch.object(migrator, "_backupFirst", fail):
			self.run_once()
		self.assertEqual((self.read(path), self.state, self.announced, self.done), (AFTER_12, {}, [], [True]))


if __name__ == "__main__":
	unittest.main()
