# Unit tests for version 1.40, from the tester's log on 1.38 for issue 36 ("possible issue"). We asked: "NVDA+Shift+J,
# then H. Does NVDA say just "Speech History" and the last line?" 1.38 no longer read the whole history, but NVDA said
# "Speech History, dialog", then "edit", the line and "read only" (the JAWS dictionary rule from Default.JDF made it
# "reed only"). JAWS's Insert+Space, H opens its Results Viewer and says the title and the line, nothing more.
# - speechHistory: while its window is open, the assistant gives the window and its text box classes of its own
#   (chooseOverlay, from the plugin's chooseNVDAObjectOverlayClasses). NVDA says the window's title without "dialog"
#   as the focus enters it, and the line at the caret as the arrow keys say it, without "edit" or "read only", as the
#   text box gets the focus. It tells them by their window handles and by the classes NVDA chose (Dialog, EditableText),
#   not by their roles, which NVDA would go on using as read before the objects had their classes (issue 36, 1.38).
# NVDA 2026.2's own code runs here, word for word: NVDAObject's event_focusEntered, event_gainFocus and reportFocus,
# speech's speakObject, speakObjectProperties and speakTextInfo, EditableText's _caretScriptPostMovedHelper (what the
# arrow keys say), and eventHandler's _getFocusLossCancellableSpeechCommand; with test_v138_dialogText's, which makes
# the tester's objects: DynamicNVDAObjectType.__call__, the property cache and behaviors.Dialog, and the classes the
# tester's Control Usage Assistant and Enhanced Control Support choose. What is imitated: what NVDA says of an object's
# properties and text (getObjectSpeech, getObjectPropertiesSpeech, getTextInfoSpeech), as far as these windows go and as
# the tester's log has it; braille; and the speech manager's command that drops speech for a focus that has moved on.
# The assistant's code is the real one: its plugin's chooseNVDAObjectOverlayClasses, speechHistory and documentPolling.
# The Speech History window itself is the real wx one.
# Run: python -m unittest tests.test_v140_speechHistoryOpening -v

import ctypes
import enum
import os
import sys
import types
import unittest
from typing import Dict, Optional, Union
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v129_speechHistory as v129  # noqa: E402
import test_v138_dialogText as v138  # noqa: E402
import wx  # noqa: E402

import jawsMigrator  # noqa: E402
from jawsMigrator import documentPolling, speechHistory  # noqa: E402

# -- NVDA 2026.2's own code, word for word (see NvdasOwnCodeTests) -----------------------------------------------

NVDA_REPORT_FOCUS = '\tdef reportFocus(self):\n\t\t"""Announces this object in a way suitable such that it gained focus."""\n\t\tspeech.speakObject(self, reason=controlTypes.OutputReason.FOCUS)\n'

NVDA_FOCUS_EVENTS = '\tdef event_focusEntered(self):\n\t\tif self.role in (controlTypes.Role.MENUBAR, controlTypes.Role.POPUPMENU, controlTypes.Role.MENUITEM):\n\t\t\tspeech.cancelSpeech()\n\t\t\treturn\n\t\tif self.isPresentableFocusAncestor:\n\t\t\tspeech.speakObject(self, reason=controlTypes.OutputReason.FOCUSENTERED)\n\n\tdef event_gainFocus(self):\n\t\t"""\n\t\tThis code is executed if a gain focus event is received by this object.\n\t\t"""\n\t\tself.reportFocus()\n\t\tbraille.handler.handleGainFocus(self)\n\t\tbrailleInput.handler.handleGainFocus(self)\n\t\tvision.handler.handleGainFocus(self)\n'

NVDA_CARET_POST_MOVED = '\tdef _caretScriptPostMovedHelper(self, speakUnit, gesture, info=None):\n\t\tif isScriptWaiting():\n\t\t\treturn\n\t\tif not info:\n\t\t\ttry:\n\t\t\t\tinfo = self.makeTextInfo(textInfos.POSITION_CARET)\n\t\t\texcept:  # noqa: E722\n\t\t\t\treturn\n\t\t# Forget the word currently being typed as the user has moved the caret somewhere else.\n\t\tspeech.clearTypedWordBuffer()\n\t\treview.handleCaretMove(info)\n\t\tif speakUnit and not willSayAllResume(gesture):\n\t\t\tinfo.expand(speakUnit)\n\t\t\tspeech.speakTextInfo(info, unit=speakUnit, reason=controlTypes.OutputReason.CARET)\n\t\tbraille.handler.handleCaretMove(self)\n'

NVDA_SPEAK_OBJECT = 'def speakObject(\n\tobj,\n\treason: OutputReason = OutputReason.QUERY,\n\t_prefixSpeechCommand: Optional[SpeechCommand] = None,\n\tpriority: Optional[Spri] = None,\n):\n\tsequence = getObjectSpeech(\n\t\tobj,\n\t\treason,\n\t\t_prefixSpeechCommand,\n\t)\n\tif sequence:\n\t\tspeak(sequence, priority=priority)\n'

NVDA_SPEAK_OBJECT_PROPERTIES = 'def speakObjectProperties(\n\tobj: "NVDAObjects.NVDAObject",\n\treason: OutputReason = OutputReason.QUERY,\n\t_prefixSpeechCommand: Optional[SpeechCommand] = None,\n\tpriority: Optional[Spri] = None,\n\t**allowedProperties,\n):\n\tspeechSequence = getObjectPropertiesSpeech(\n\t\tobj,\n\t\treason,\n\t\t_prefixSpeechCommand,\n\t\t**allowedProperties,\n\t)\n\tif speechSequence:\n\t\tspeak(speechSequence, priority=priority)\n'

NVDA_SPEAK_TEXT_INFO = 'def speakTextInfo(\n\tinfo: textInfos.TextInfo,\n\tuseCache: Union[bool, SpeakTextInfoState] = True,\n\tformatConfig: Dict[str, bool] = None,\n\tunit: Optional[str] = None,\n\treason: OutputReason = OutputReason.QUERY,\n\t_prefixSpeechCommand: Optional[SpeechCommand] = None,\n\tonlyInitialFields: bool = False,\n\tsuppressBlanks: bool = False,\n\tpriority: Optional[Spri] = None,\n) -> bool:\n\tspeechGen = getTextInfoSpeech(\n\t\tinfo,\n\t\tuseCache,\n\t\tformatConfig,\n\t\tunit,\n\t\treason,\n\t\t_prefixSpeechCommand,\n\t\tonlyInitialFields,\n\t\tsuppressBlanks,\n\t)\n\n\tspeechGen = GeneratorWithReturn(speechGen)\n\tfor seq in speechGen:\n\t\tspeak(seq, priority=priority)\n\treturn speechGen.returnValue\n'

NVDA_FOCUS_LOSS_COMMAND = 'def _getFocusLossCancellableSpeechCommand(\n\tobj,\n\treason: controlTypes.OutputReason,\n) -> Optional[_CancellableSpeechCommand]:\n\tif reason != controlTypes.OutputReason.FOCUS or not speech.manager._shouldCancelExpiredFocusEvents():\n\t\treturn None\n\tfrom NVDAObjects import NVDAObject\n\n\tif not isinstance(obj, NVDAObject):\n\t\tlog.warning("Unhandled object type. Expected all objects to be descendant from NVDAObject")\n\t\treturn None\n\n\tshouldReportDevInfo = speech.manager._shouldDoSpeechManagerLogging()\n\treturn FocusLossCancellableSpeechCommand(obj, reportDevInfo=shouldReportDevInfo)\n'

# Where NVDA_SOURCE (NVDA 2026.2's source folder) has each piece.
NVDA_FILES = {
	"NVDA_REPORT_FOCUS": ("NVDAObjects", "__init__.py"),
	"NVDA_FOCUS_EVENTS": ("NVDAObjects", "__init__.py"),
	"NVDA_CARET_POST_MOVED": ("editableText.py",),
	"NVDA_SPEAK_OBJECT": ("speech", "speech.py"),
	"NVDA_SPEAK_OBJECT_PROPERTIES": ("speech", "speech.py"),
	"NVDA_SPEAK_TEXT_INFO": ("speech", "speech.py"),
	"NVDA_FOCUS_LOSS_COMMAND": ("eventHandler.py",),
}


class OutputReason(enum.Enum):
	FOCUS = "focus"
	FOCUSENTERED = "focusEntered"
	CARET = "caret"
	QUERY = "query"
	MOUSE = "mouse"


# NVDA's roles that test_v138_dialogText's windows don't have; NVDA's event_focusEntered asks about them.
class MenuRole(enum.Enum):
	MENUBAR = "menu bar"
	POPUPMENU = "menu"
	MENUITEM = "menu item"


# What NVDA says of a state as the tester's log has it: "read only", and nothing for "focused", "focusable" or
# "multi line" as the focus moves.
SAID_STATES = (v138.State.READONLY,)
# NVDA's silentRolesOnFocus, as far as these windows go: none of them.
SILENT_ROLES_ON_FOCUS = ()

LINE = 'list  with 2 items  1.  NVDA+Shift+J, then H. Does NVDA say just "Speech History" and the last line?'
# The tester's history, the end of it, with the line they were on.
HISTORY = "Re: [joshknnd1982/jawsMigrator] possible issue (Issue #36) - Message (HTML)\r\n" + LINE
SPEECH_HISTORY_WINDOW = {
	100: v138.FakeWindow("#32770", v138.Role.DIALOG, name="Speech History", children=(101, 102, 103, 104)),
	101: v138.FakeWindow(
		"Edit",
		v138.Role.EDITABLETEXT,
		(v138.State.FOCUSABLE, v138.State.FOCUSED, v138.State.READONLY),
		v138.WS_VISIBLE | v138.ES_MULTILINE,
		text=HISTORY,
	),
	102: v138.FakeWindow("Button", v138.Role.BUTTON, name="Copy all"),
	103: v138.FakeWindow("Button", v138.Role.BUTTON, name="Clear"),
	104: v138.FakeWindow("Button", v138.Role.BUTTON, name="Close"),
}
WINDOWS = {**SPEECH_HISTORY_WINDOW, **v138.UPDATE_DIALOG}


class FocusLossCommand:
	"""The speech manager's command that drops what NVDA says for ``obj`` once the focus has moved on (imitated)."""

	def __init__(self, obj, reportDevInfo):
		self.obj = obj

	def __repr__(self):
		return "FocusLossCancellableSpeechCommand"


def getObjectPropertiesSpeech(obj, reason=OutputReason.QUERY, _prefixSpeechCommand=None, **allowedProperties):
	"""What NVDA says of ``obj``'s properties, as far as these windows go (imitated), with the real command added for
	the focus."""
	sequence = []
	name = obj.name if allowedProperties.get("name") else None
	if name:
		sequence.append(name)
	if allowedProperties.get("role") and not (reason == OutputReason.FOCUS and name and obj.role in SILENT_ROLES_ON_FOCUS):
		sequence.append(obj.role.value)
	if allowedProperties.get("description") and obj.description:
		sequence.append(obj.description)
	if allowedProperties.get("states"):
		sequence.extend(state.value for state in SAID_STATES if state in obj.states)
	if sequence:
		if _prefixSpeechCommand is not None:
			sequence.insert(0, _prefixSpeechCommand)
		cancelCommand = sys.modules["eventHandler"]._getFocusLossCancellableSpeechCommand(obj, reason)
		if cancelCommand is not None:
			sequence.append(cancelCommand)
	return sequence


def getObjectSpeech(obj, reason=OutputReason.QUERY, _prefixSpeechCommand=None):
	"""What NVDA says of ``obj`` (imitated): its name, role, description and states, then, for the focus in a text
	field, the line at its caret, as the tester's log has it for the Speech History window."""
	textContent = reason != OutputReason.FOCUSENTERED and isinstance(obj, sys.modules["editableText"].EditableText)
	if reason == OutputReason.FOCUSENTERED:
		reason = OutputReason.FOCUS
	sequence = getObjectPropertiesSpeech(obj, reason, _prefixSpeechCommand, name=True, role=True, description=True, states=True)
	if textContent:
		sequence.append(obj.makeTextInfo("caret").text)
	return sequence


def getTextInfoSpeech(info, useCache, formatConfig, unit, reason, _prefixSpeechCommand, onlyInitialFields, suppressBlanks):
	"""What NVDA says of a text field's text (imitated): the command first, then the text, in one sequence."""
	sequence = []
	if _prefixSpeechCommand is not None:
		sequence.append(_prefixSpeechCommand)
	sequence.append(info.text)
	yield sequence
	return True


class GeneratorWithReturn:
	def __init__(self, gen):
		self.gen = gen
		self.returnValue = None

	def __iter__(self):
		self.returnValue = yield from self.gen


class Nvda(v138.Nvda):
	"""test_v138_dialogText's NVDA, making the tester's objects, with NVDA's focus events and speech, and the assistant's
	plugin among the running plugins (first or last)."""

	def __init__(self, windows, assistantFirst=False):
		super().__init__(windows)
		self.said = []
		self.braille = []
		controlTypes = self.controlTypes
		controlTypes.OutputReason = OutputReason
		focusRoles = types.SimpleNamespace(**{role.name: role for role in (*v138.Role, *MenuRole)})
		speech = types.ModuleType("speech")
		speech.__dict__.update(
			OutputReason=OutputReason,
			Optional=Optional,
			Union=Union,
			Dict=Dict,
			SpeechCommand=object,
			SpeakTextInfoState=object,
			Spri=object,
			textInfos=types.SimpleNamespace(TextInfo=object),
			getObjectSpeech=getObjectSpeech,
			getObjectPropertiesSpeech=getObjectPropertiesSpeech,
			getTextInfoSpeech=getTextInfoSpeech,
			GeneratorWithReturn=GeneratorWithReturn,
			speak=lambda sequence, priority=None: self.said.append(list(sequence)),
			cancelSpeech=lambda: None,
			clearTypedWordBuffer=lambda: None,
			manager=types.SimpleNamespace(_shouldCancelExpiredFocusEvents=lambda: True, _shouldDoSpeechManagerLogging=lambda: False),
		)
		for code in (NVDA_SPEAK_OBJECT, NVDA_SPEAK_OBJECT_PROPERTIES, NVDA_SPEAK_TEXT_INFO):
			exec(v138.compiled(code, "<NVDA 2026.2 speech>"), speech.__dict__)
		eventHandler = types.ModuleType("eventHandler")
		eventHandler.__dict__.update(
			controlTypes=controlTypes,
			speech=speech,
			log=documentPolling._log(),
			Optional=Optional,
			_CancellableSpeechCommand=FocusLossCommand,
			FocusLossCancellableSpeechCommand=FocusLossCommand,
		)
		exec(v138.compiled(NVDA_FOCUS_LOSS_COMMAND, "<NVDA 2026.2 eventHandler>"), eventHandler.__dict__)
		recorder = types.SimpleNamespace(handleGainFocus=lambda obj: self.braille.append(obj), handleCaretMove=lambda obj: None)
		scope = {
			"controlTypes": types.SimpleNamespace(Role=focusRoles, OutputReason=OutputReason),
			"speech": speech,
			"braille": types.SimpleNamespace(handler=recorder),
			"brailleInput": types.SimpleNamespace(handler=types.SimpleNamespace(handleGainFocus=lambda obj: None)),
			"vision": types.SimpleNamespace(handler=types.SimpleNamespace(handleGainFocus=lambda obj: None)),
			"textInfos": types.SimpleNamespace(POSITION_CARET="caret"),
			"review": types.SimpleNamespace(handleCaretMove=lambda info: None),
			"isScriptWaiting": lambda: False,
			"willSayAllResume": lambda gesture: False,
		}
		exec(
			v138.compiled("class NvdasFocus:\n" + NVDA_REPORT_FOCUS + "\n" + NVDA_FOCUS_EVENTS + "\n" + NVDA_CARET_POST_MOVED, "<NVDA 2026.2>"),
			scope,
		)
		for name in ("reportFocus", "event_focusEntered", "event_gainFocus"):
			setattr(self.NVDAObject, name, scope["NvdasFocus"].__dict__[name])
		self.EditableText._caretScriptPostMovedHelper = scope["NvdasFocus"].__dict__["_caretScriptPostMovedHelper"]
		# NVDAObject._get_isPresentableFocusAncestor says True for a dialog (imitated).
		self.NVDAObject.isPresentableFocusAncestor = True
		# EditTextInfo's line at the caret is already the whole of it.
		self.scope["EditTextInfo"].expand = lambda info, unit: None
		self.modules["NVDAObjects"].NVDAObject = self.NVDAObject
		behaviors = types.ModuleType("NVDAObjects.behaviors")
		behaviors.Dialog = self.Dialog
		editableText = types.ModuleType("editableText")
		editableText.EditableText = self.EditableText
		self.modules.update(
			{
				"NVDAObjects.behaviors": behaviors,
				"editableText": editableText,
				"speech": speech,
				"eventHandler": eventHandler,
				"textInfos": types.SimpleNamespace(POSITION_CARET="caret", POSITION_ALL="all", UNIT_LINE="line"),
			}
		)
		assistant = object.__new__(jawsMigrator.GlobalPlugin)
		plugins = self.globalPluginHandler.runningPlugins
		plugins.insert(0, assistant) if assistantFirst else plugins.append(assistant)

	def opening(self, window=100, text=101):
		"""What NVDA says as the window comes up with the focus in its text box: the window as the focus enters it
		(eventHandler.doPreGainFocus), then the text box as it gets the focus. Only the text of what is said."""
		del self.said[:]
		self.object(window).event_focusEntered()
		self.object(text).event_gainFocus()
		return [[item for item in sequence if isinstance(item, str)] for sequence in self.said]


class OpeningCase(unittest.TestCase):
	def nvda(self, windows=WINDOWS, handles=(100, 101), **kwargs):
		nvda = Nvda(windows, **kwargs)
		patcher = mock.patch.dict(sys.modules, nvda.modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		documentPolling._failed = False
		documentPolling._logged.clear()
		documentPolling.register()
		self.addCleanup(self._restore)
		# Each NVDA here has its own NVDAObject; the assistant makes its classes on it again.
		speechHistory._overlays = None
		speechHistory._failed = False
		speechHistory._viewerHandles = handles
		return nvda

	def _restore(self):
		documentPolling.unregister()
		documentPolling._replaced.clear()
		documentPolling._failed = False
		speechHistory._viewerHandles = (None, None)
		speechHistory._overlays = None
		speechHistory._failed = False


class OpeningTests(OpeningCase):
	def test_theTestersVersionSaidDialogEditAndReadOnly(self):
		# 1.38 (no window open for the assistant): the tester's log.
		nvda = self.nvda(handles=(None, None))
		self.assertEqual(nvda.opening(), [["Speech History", "dialog"], ["edit", "read only", LINE]])

	def test_theTitleThenTheLineAsJaws(self):
		nvda = self.nvda()
		self.assertEqual(nvda.opening(), [["Speech History"], [LINE]])

	def test_whicheverAddOnChoosesFirst(self):
		nvda = self.nvda(assistantFirst=True)
		self.assertEqual(nvda.opening(), [["Speech History"], [LINE]])

	def test_theLineAsTheArrowKeysSayIt(self):
		nvda = self.nvda()
		text = nvda.object(101)
		text._caretScriptPostMovedHelper("line", gesture=None)
		arrowed = nvda.said[-1]
		text.event_gainFocus()
		focused = nvda.said[-1]
		self.assertEqual([item for item in focused if isinstance(item, str)], arrowed)
		self.assertEqual(arrowed, [LINE])

	def test_whatIsSaidForTheFocusIsStillDroppedOnceItMovesOn(self):
		# NVDA's own command, which NVDA's speech manager uses to drop what is still to be said for a focus that has
		# moved on, and what the speech history leaves out (issue 30), is with the title and the line as before.
		nvda = self.nvda()
		window, text = nvda.object(100), nvda.object(101)
		window.event_focusEntered()
		text.event_gainFocus()
		commands = [[item for item in sequence if isinstance(item, FocusLossCommand)] for sequence in nvda.said]
		self.assertEqual([len(sequence) for sequence in commands], [1, 1])
		self.assertIs(commands[0][0].obj, window)
		self.assertIs(commands[1][0].obj, text)

	def test_brailleAndTheObjectsAreAsBefore(self):
		nvda = self.nvda()
		text = nvda.object(101)
		text.event_gainFocus()
		self.assertEqual(nvda.braille, [text])
		self.assertEqual(text.role, v138.Role.EDITABLETEXT)
		self.assertIn(v138.State.READONLY, text.states)
		self.assertIn(v138.State.MULTILINE, text.states, "1.38's fix still holds")
		self.assertEqual(nvda.object(100).role, v138.Role.DIALOG)
		self.assertEqual(nvda.object(100).description, "", "1.38's fix still holds")

	def test_theButtonsAreAsBefore(self):
		nvda = self.nvda()
		windowClass, textClass = speechHistory._overlayClasses()
		for handle in (102, 103, 104):
			mro = type(nvda.object(handle)).__mro__
			self.assertNotIn(windowClass, mro)
			self.assertNotIn(textClass, mro)

	def test_otherWindowsAreAsBefore(self):
		# The update dialog, open while the Speech History window is: NVDA says its role and its text.
		nvda = self.nvda()
		said = nvda.opening(200, 203)
		self.assertEqual(said[0][:2], ["JAWS Migration Assistant update", "dialog"])
		self.assertEqual(said[1][:3], ["What's new:", "edit", "read only"])

	def test_onceTheWindowIsClosedNothing(self):
		# Windows may give a closed window's handle to another window.
		nvda = self.nvda(handles=(None, None))
		windowClass, textClass = speechHistory._overlayClasses()
		for handle in (100, 101):
			mro = type(nvda.object(handle)).__mro__
			self.assertNotIn(windowClass, mro)
			self.assertNotIn(textClass, mro)

	def test_aWindowWithTheHandleButNotADialogOrTextBox(self):
		# Its frame, as NVDA makes an object for it: no Dialog, no EditableText.
		nvda = self.nvda(handles=(102, 103))
		self.assertEqual(nvda.opening(102, 103), [["Copy all", "button"], ["Clear", "button"]])

	def test_neverKeepsNvdaFromMakingTheObject(self):
		self.nvda()

		class Broken:
			@property
			def windowHandle(self):
				raise RuntimeError("gone")

		clsList = [object]
		speechHistory.chooseOverlay(Broken(), clsList)
		self.assertEqual(clsList, [object])

	def test_theObjectsCacheIsLeftAlone(self):
		# The assistant reads nothing NVDA would keep from before the object has its classes (see test_v138_dialogText).
		nvda = self.nvda()
		for handle, classes in ((100, [nvda.Dialog, nvda.IAccessible]), (101, [nvda.IAccessible, nvda.Edit, nvda.Window])):
			obj = nvda.IAccessible.__new__(nvda.IAccessible)
			obj.__init__(windowHandle=handle, event_objectID=v138.OBJID_CLIENT, event_childID=0)
			clsList = list(classes)
			speechHistory.chooseOverlay(obj, clsList)
			self.assertEqual(len(clsList), len(classes) + 1)
			self.assertEqual(obj._propertyCache, {})


class RealWindowTests(v129.SpeechHistoryCase):
	"""The real Speech History window: the handles the assistant tells it by."""

	def setUp(self):
		super().setUp()
		self.addCleanup(speechHistory.closeViewer)
		speechHistory.register()
		self.speak("one")

	def test_theWindowsHandlesWhileItIsOpen(self):
		speechHistory.showAndSay()
		viewer = speechHistory._viewer
		self.assertEqual(speechHistory._viewerHandles, (viewer.GetHandle(), viewer.text.GetHandle()))
		viewer.Close()
		wx.Yield()
		self.assertEqual(speechHistory._viewerHandles, (None, None))

	def test_knownBeforeTheWindowShows(self):
		# NVDA makes the objects for the focus as the window comes up.
		seen = []
		viewerClass = speechHistory._viewerClass()

		def show(viewer, *args):
			seen.append(speechHistory._viewerHandles)
			return wx.Dialog.Show(viewer, *args)

		with mock.patch.object(viewerClass, "Show", show):
			speechHistory.showAndSay()
		viewer = speechHistory._viewer
		self.assertEqual(seen, [(viewer.GetHandle(), viewer.text.GetHandle())])

	def test_turningItOffOrClosingItForgetsThem(self):
		speechHistory.showAndSay()
		speechHistory.unregister()
		self.assertEqual(speechHistory._viewerHandles, (None, None))
		speechHistory.register()
		self.speak("two")
		speechHistory.showAndSay()
		speechHistory.closeViewer()
		self.assertEqual(speechHistory._viewerHandles, (None, None))

	def test_itsTextBoxIsAWin32TextField(self):
		# So NVDA gives it its Edit class, an EditableText (Window.findOverlayClasses), as the tester's log has it:
		# Dynamic_EnhancedSuggestionIAccessibleEditWindowNVDAObject.
		speechHistory.showAndSay()
		buffer = ctypes.create_unicode_buffer(256)
		ctypes.windll.user32.GetClassNameW(speechHistory._viewer.text.GetHandle(), buffer, 256)
		self.assertEqual(buffer.value.lower(), "edit")


class PluginTests(unittest.TestCase):
	def test_thePluginAsksTheSpeechHistory(self):
		plugin = object.__new__(jawsMigrator.GlobalPlugin)
		obj, clsList = object(), []
		with mock.patch.object(speechHistory, "chooseOverlay") as chooseOverlay:
			plugin.chooseNVDAObjectOverlayClasses(obj, clsList)
		chooseOverlay.assert_called_once_with(obj, clsList)


class NvdasOwnCodeTests(unittest.TestCase):
	def test_theCodeIsNvdas(self):
		# Each piece is in NVDA 2026.2's source: set NVDA_SOURCE to its source folder.
		source = os.environ.get("NVDA_SOURCE")
		if not source:
			self.skipTest("NVDA_SOURCE isn't set")
		for name, parts in NVDA_FILES.items():
			with open(os.path.join(source, *parts), encoding="utf-8") as f:
				text = f.read().replace("\r\n", "\n")
			self.assertIn(globals()[name], text, name)


if __name__ == "__main__":
	unittest.main()
