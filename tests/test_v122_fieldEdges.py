# Unit tests for version 1.22, from a tester's report (issue 13): "when I hit control right arrow it knocks me out of the
# edit box. Jaws doesn't do that." In his log of 26 September, in GitHub's comment box in Edge, in focus mode:
# 08:41:32.233 Input: kb(laptop):control+rightArrow
# 08:41:32.343 editableText._hasCaretMoved: Caret didn't move before timeout.
# 08:41:32.347 Speaking ['out of edit', 'button', 'Paste, ']
# and the stack of the profile switch that followed: cursorManager.script_moveByWord_forward, browseMode._set_selection,
# treeInterceptorHandler._set_passThrough. Right Arrow (08:40:03) and Down Arrow (08:39:34) at the end did the same.
# His NVDA config has virtualBuffers.autoPassThroughOnCaretMove on: the migration sets it from JAWS's Auto Forms Mode.
# With it on, NVDA 2026.2's browseMode.BrowseModeDocumentTreeInterceptor.event_caretMovementFailed leaves focus mode
# when any caret key but Home and End can't move the caret in a field, and runs the key again in browse mode.
# JAWS leaves forms mode only when you arrow past the control: Up or Down Arrow in a field of one line.
# - fieldEdges: the assistant's global plugin, which NVDA gives the event to first, keeps the caret and focus mode in
#   the field, but for Up or Down Arrow alone in a field of one line, where NVDA goes on as it does.
# The imitation NVDA runs NVDA 2026.2's own editableText.EditableText._caretMovementScriptHelper,
# eventHandler._EventExecuter and browseMode.BrowseModeDocumentTreeInterceptor.event_caretMovementFailed, word for word.
# The assistant's code is the real one.
# Run: python -m unittest tests.test_v122_fieldEdges -v

import enum
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import jawsMigrator  # noqa: E402
from jawsMigrator import fieldEdges, state  # noqa: E402
from test_v121_alerts import NVDA_EVENT_EXECUTER, nvdaCode  # noqa: E402

#: NVDA 2026.2, source/editableText.py, EditableText._caretMovementScriptHelper, word for word.
NVDA_CARET_MOVEMENT_SCRIPT_HELPER = '''
def _caretMovementScriptHelper(self, gesture, unit):
	try:
		info = self.makeTextInfo(textInfos.POSITION_CARET)
	except:  # noqa: E722
		gesture.send()
		return
	bookmark = info.bookmark
	gesture.send()
	caretMoved, newInfo = self._hasCaretMoved(bookmark)
	if not caretMoved and self.shouldFireCaretMovementFailedEvents:
		eventHandler.executeEvent("caretMovementFailed", self, gesture=gesture)
	self._caretScriptPostMovedHelper(unit, gesture, newInfo)
'''

#: NVDA 2026.2, source/browseMode.py, BrowseModeDocumentTreeInterceptor.event_caretMovementFailed, word for word.
NVDA_EVENT_CARET_MOVEMENT_FAILED = '''
def event_caretMovementFailed(self, obj, nextHandler, gesture=None):
	if (
		not self.passThrough
		or not gesture
		or not config.conf["virtualBuffers"]["autoPassThroughOnCaretMove"]
	):
		return nextHandler()
	if gesture.mainKeyName in ("home", "end"):
		# Home, end, control+home and control+end should not disable pass through.
		return nextHandler()
	script = self.getScript(gesture)
	if not script:
		return nextHandler()

	# We've hit the edge of the focused control.
	# Therefore, move the virtual caret to the same edge of the field.
	info = self.makeTextInfo(textInfos.POSITION_CARET)
	info.expand(textInfos.UNIT_CONTROLFIELD)
	if gesture.mainKeyName in ("leftArrow", "upArrow", "pageUp"):
		info.collapse()
	else:
		info.collapse(end=True)
		info.move(textInfos.UNIT_CHARACTER, -1)
	info.updateCaret()

	scriptHandler.queueScript(script, gesture)
'''


class State(enum.Enum):
	"""NVDA's controlTypes.State, as far as these fields go."""

	EDITABLE = "editable"
	MULTILINE = "multi line"
	FOCUSABLE = "focusable"


controlTypes = types.ModuleType("controlTypes")
controlTypes.State = State

textInfos = types.SimpleNamespace(POSITION_CARET="caret", UNIT_CONTROLFIELD="controlField", UNIT_CHARACTER="character")


class Gesture:
	"""NVDA's KeyboardInputGesture, as far as these scripts go: its main key, its modifiers and send()."""

	def __init__(self, mainKeyName, *modifierNames):
		self.mainKeyName = mainKeyName
		self.modifierNames = list(modifierNames)
		# NVDA's modifiers are (virtual key, extended) pairs; only whether there are any matters here.
		self.modifiers = {(name, False) for name in modifierNames}
		self.sent = 0

	def send(self):
		self.sent += 1

	def __repr__(self):
		return "+".join(self.modifierNames + [self.mainKeyName])


class DocumentCaret:
	"""Browse mode's cursor, as NVDA's event moves it to the field's edge: what was done to it, in order."""

	def __init__(self, document):
		self.document = document
		self.steps = []

	def expand(self, unit):
		self.steps.append(("expand", unit))

	def collapse(self, end=False):
		self.steps.append(("collapse", "end" if end else "start"))

	def move(self, unit, direction):
		self.steps.append(("move", unit, direction))

	def updateCaret(self):
		self.document.carets.append(self.steps)


class Document:
	"""Edge's page in browse mode (a BrowseModeDocumentTreeInterceptor): focus mode or not, its scripts and cursor."""

	isReady = True

	def __init__(self, passThrough=True):
		self.passThrough = passThrough
		self.carets = []

	def getScript(self, gesture):
		# Browse mode has a script for every caret key: moveByWord_forward for Control+Right Arrow, and so on.
		return f"browse mode's script for {gesture!r}"

	def makeTextInfo(self, position):
		return DocumentCaret(self)


class Field:
	"""An edit field in Edge (NVDA's EditableTextBase), in focus mode, with its caret at an edge it can't pass."""

	appModule = None
	shouldFireCaretMovementFailedEvents = True

	def __init__(self, name, states, document):
		self.name = name
		self.states = set(states)
		self.treeInterceptor = document
		self.said = []

	def makeTextInfo(self, position):
		return types.SimpleNamespace(bookmark=("caret", 0))

	def _hasCaretMoved(self, bookmark):
		# NVDA waited, and the caret didn't move: "Caret didn't move before timeout."
		return (False, types.SimpleNamespace(bookmark=bookmark))

	def _caretScriptPostMovedHelper(self, unit, gesture, info):
		self.said.append(unit)


class Unreadable(Field):
	"""A field whose states can't be read any more (the page took it away)."""

	@property
	def states(self):
		raise OSError("(-2147467259, 'Unspecified error')")

	@states.setter
	def states(self, value):
		pass


class FieldEdgesTest(unittest.TestCase):
	def setUp(self):
		self.queued = []
		self.conf = {"virtualBuffers": {"autoPassThroughOnCaretMove": True}}
		config = types.SimpleNamespace(conf=self.conf)
		self.plugin = object.__new__(jawsMigrator.GlobalPlugin)
		self.plugin._fieldEdges = fieldEdges
		self.plugins = [self.plugin]
		patches = [
			mock.patch.dict(sys.modules, {"controlTypes": controlTypes, "config": config}),
			mock.patch.object(fieldEdges, "_failed", False),
			mock.patch.object(fieldEdges, "_enabled", fieldEdges._enabled),
			mock.patch.object(fieldEdges, "_noted", None),
		]
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)
		fieldEdges.register()
		executer = nvdaCode(
			NVDA_EVENT_EXECUTER,
			"_EventExecuter",
			{
				"garbageHandler": types.SimpleNamespace(TrackedObject=object),
				"globalPluginHandler": types.SimpleNamespace(runningPlugins=self.plugins),
				"log": nvdaStubs.logging.getLogger("nvda"),
				"extensionPoints": types.SimpleNamespace(callWithSupportedKwargs=lambda func, *args, **kwargs: func(*args)),
			},
		)
		eventHandler = types.SimpleNamespace(executeEvent=lambda name, obj, **kwargs: executer(name, obj, kwargs))
		scriptHandler = types.SimpleNamespace(queueScript=lambda script, gesture: self.queued.append(script))
		namespace = {"textInfos": textInfos, "eventHandler": eventHandler, "config": config, "scriptHandler": scriptHandler}
		Field._caretMovementScriptHelper = nvdaCode(NVDA_CARET_MOVEMENT_SCRIPT_HELPER, "_caretMovementScriptHelper", namespace)
		Document.event_caretMovementFailed = nvdaCode(NVDA_EVENT_CARET_MOVEMENT_FAILED, "event_caretMovementFailed", namespace)
		self.addCleanup(lambda: [delattr(owner, name) for owner, name in ((Field, "_caretMovementScriptHelper"), (Document, "event_caretMovementFailed"))])
		self.document = Document()
		self.comment = Field("Add a comment", (State.EDITABLE, State.MULTILINE, State.FOCUSABLE), self.document)
		self.search = Field("Search or jump to", (State.EDITABLE, State.FOCUSABLE), self.document)

	def press(self, field, key, *modifiers):
		"""A caret key in field, at its edge, as NVDA's editable text script runs it. True when browse mode went on past the field."""
		gesture = Gesture(key, *modifiers)
		queued = len(self.queued)
		field._caretMovementScriptHelper(gesture, "word")
		self.assertEqual(gesture.sent, 1, "the key reaches the page either way")
		return len(self.queued) > queued

	def nvdaAlone(self, field, key, *modifiers):
		"""What NVDA 2026.2 does without the assistant."""
		self.plugins.clear()
		try:
			return self.press(field, key, *modifiers)
		finally:
			self.plugins.append(self.plugin)

	def test_control_right_arrow_left_the_comment_box(self):
		self.assertTrue(self.nvdaAlone(self.comment, "rightArrow", "control"), "NVDA 2026.2 went on past the field in browse mode")
		self.assertEqual(self.queued, ["browse mode's script for control+rightArrow"])
		self.assertEqual(
			self.document.carets,
			[[("expand", "controlField"), ("collapse", "end"), ("move", "character", -1)]],
			"after putting browse mode's cursor at the end of the field",
		)

	def test_control_right_arrow_stays_in_the_comment_box(self):
		self.assertFalse(self.press(self.comment, "rightArrow", "control"))
		self.assertEqual(self.document.carets, [], "browse mode's cursor isn't moved either")
		self.assertEqual(self.comment.said, ["word"], "NVDA says the word at the caret as it does")

	def test_every_caret_key_stays_in_a_multi_line_field(self):
		# The tester's Right Arrow and Down Arrow at the end of the comment, and the keys at its start.
		for key, modifiers in (
			("rightArrow", ()),
			("downArrow", ()),
			("leftArrow", ()),
			("upArrow", ()),
			("leftArrow", ("control",)),
			("downArrow", ("control",)),
			("upArrow", ("control",)),
			("pageDown", ()),
			("pageUp", ()),
		):
			with self.subTest(key=key, modifiers=modifiers):
				self.assertTrue(self.nvdaAlone(self.comment, key, *modifiers), "NVDA 2026.2 leaves the field")
				self.assertFalse(self.press(self.comment, key, *modifiers))
		self.assertEqual(len(self.document.carets), 9, "only NVDA alone moved browse mode's cursor, once for each key")

	def test_up_and_down_arrow_leave_a_field_of_one_line(self):
		# JAWS's Auto Forms Mode: "If you continue to arrow past the control, Forms mode will be disabled again automatically."
		self.assertTrue(self.press(self.search, "downArrow"))
		self.assertTrue(self.press(self.search, "upArrow"))
		self.assertEqual(self.queued, ["browse mode's script for downArrow", "browse mode's script for upArrow"])
		self.assertEqual(self.document.carets[1], [("expand", "controlField"), ("collapse", "start")])

	def test_other_keys_stay_in_a_field_of_one_line(self):
		for key, modifiers in (("rightArrow", ()), ("leftArrow", ()), ("rightArrow", ("control",)), ("downArrow", ("control",)), ("downArrow", ("shift",))):
			with self.subTest(key=key, modifiers=modifiers):
				self.assertFalse(self.press(self.search, key, *modifiers))
		self.assertEqual(self.queued, [])

	def test_home_and_end_go_on_to_nvda_which_stays(self):
		for key, modifiers in (("home", ()), ("end", ()), ("end", ("control",))):
			with self.subTest(key=key):
				with self.assertNoLogs("nvda", level="DEBUG"):
					self.assertFalse(self.press(self.comment, key, *modifiers))
				self.assertFalse(fieldEdges.keepsFocusMode(self.comment, Gesture(key, *modifiers)))

	def test_without_automatic_focus_mode_for_caret_movement_nvda_does_as_it_does(self):
		self.conf["virtualBuffers"]["autoPassThroughOnCaretMove"] = False
		with self.assertNoLogs("nvda", level="DEBUG"):
			self.assertFalse(self.press(self.comment, "rightArrow", "control"))
		self.assertFalse(fieldEdges.keepsFocusMode(self.comment, Gesture("rightArrow", "control")), "nothing to keep")

	def test_in_browse_mode_nvda_does_as_it_does(self):
		self.document.passThrough = False
		self.assertFalse(fieldEdges.keepsFocusMode(self.comment, Gesture("rightArrow", "control")))
		outside = Field("Notepad", (State.EDITABLE, State.MULTILINE), None)
		self.assertFalse(fieldEdges.keepsFocusMode(outside, Gesture("rightArrow", "control")), "a field outside browse mode's documents")
		self.assertFalse(fieldEdges.keepsFocusMode(self.comment, None), "an event without a key")

	def test_turned_off_nvda_leaves_the_field(self):
		fieldEdges.unregister()
		self.assertTrue(self.press(self.comment, "rightArrow", "control"))

	def test_before_the_settings_are_applied_nvda_leaves_the_field(self):
		self.plugin._fieldEdges = None
		self.assertTrue(self.press(self.comment, "rightArrow", "control"))

	def test_a_field_that_cant_be_read_goes_on_to_nvda_logged_once(self):
		gone = Unreadable("gone", (), self.document)
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.assertTrue(self.press(gone, "upArrow"))
			self.assertTrue(self.press(Unreadable("gone too", (), self.document), "downArrow"))
		failures = [line for line in logged.output if "could not tell whether a key at the edge of a field" in line]
		self.assertEqual(len(failures), 1, logged.output)

	def test_logged_once_for_each_field(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.press(self.comment, "rightArrow", "control")
			self.press(self.comment, "rightArrow")
			self.press(self.search, "rightArrow")
		kept = [line for line in logged.output if "stays in it, in focus mode, as JAWS's Auto Forms Mode does" in line]
		self.assertEqual(len(kept), 2, logged.output)
		self.assertIn("control+rightArrow at the edge of the field 'Add a comment'", kept[0])
		self.assertIn("rightArrow at the edge of the field 'Search or jump to'", kept[1])


class SettingTest(unittest.TestCase):
	def test_on_unless_turned_off(self):
		self.assertTrue(fieldEdges.wanted({}))
		self.assertTrue(fieldEdges.wanted(dict(state.DEFAULTS)))
		self.assertFalse(fieldEdges.wanted({fieldEdges.STATE_KEY: False}))
		self.assertFalse(fieldEdges.wanted(None))
		self.assertIs(state.DEFAULTS[fieldEdges.STATE_KEY], True)

	def test_register_and_unregister(self):
		with mock.patch.object(fieldEdges, "_enabled", False):
			fieldEdges.register()
			self.assertTrue(fieldEdges.isRegistered())
			fieldEdges.unregister()
			self.assertFalse(fieldEdges.isRegistered())

	def test_the_event_goes_on_when_the_assistant_has_nothing_to_do(self):
		plugin = object.__new__(jawsMigrator.GlobalPlugin)
		handled = []
		plugin.event_caretMovementFailed(object(), lambda: handled.append(True))
		self.assertEqual(handled, [True], "before the settings are applied, and without a key")


if __name__ == "__main__":
	unittest.main()
