# Unit tests for version 1.15, from a tester's report on version 1.13 (issue 9, the nvda-old.log it added):
# - documentPolling: after pasting 21 million characters into Windows 11's Notepad, Control+Home froze NVDA
#   until the tester restarted it 17 seconds later, and coming back to a 24-million-character file in Notepad
#   stuck NVDA for a second or two each time. Enhanced Control Support 1.2.2, with "Rely on events by default"
#   off as it comes, gave Notepad's document its timer, which read the whole text every 50 ms.
# The imitation Enhanced Control Support below does what version 1.2.2 does, as far as this goes: its
# shouldUseTimerMixin, word for word, and the end of its chooseNVDAObjectOverlayClasses, which looks the choice
# up in its module each time. The imitation NVDA has the classes NVDA 2026.2 gives the tester's objects. The
# assistant's register, unregister and wrapper are the real ones.
# Run: python -m unittest tests.test_v115_documents -v

import enum
import functools
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import documentPolling, state  # noqa: E402

MODULE = "globalPlugins.enhancedControlSupport"


class Role(enum.Enum):
	DOCUMENT = "document"
	EDITABLETEXT = "edit"
	LISTITEM = "list item"
	BUTTON = "button"
	PANE = "pane"


class State(enum.Enum):
	MULTILINE = "multi line"
	READONLY = "read only"
	FOCUSABLE = "focusable"


class EditableText:
	"""NVDA's editableText.EditableText."""


class EditableTextWithAutoSelectDetection(EditableText):
	"""NVDA's NVDAObjects.behaviors.EditableTextWithAutoSelectDetection."""


class UIA:
	pass


class IAccessible:
	pass


class Edit(EditableTextWithAutoSelectDetection):
	"""NVDA's NVDAObjects.window.edit.Edit."""


class ListItem:
	pass


class Obj:
	def __init__(self, role, states=(), windowClassName="", name=""):
		self.role, self.states, self.windowClassName, self.name = role, set(states), windowClassName, name


# The tester's objects, with the classes NVDA 2026.2 gives them before the global plugins choose theirs.
NOTEPAD_DOCUMENT = (Obj(Role.DOCUMENT, windowClassName="RichEditD2DPT", name="Text editor"), [EditableTextWithAutoSelectDetection, UIA])
LOG_VIEWER = (Obj(Role.EDITABLETEXT, {State.MULTILINE, State.READONLY}, "RICHEDIT50W"), [Edit, IAccessible])
SEARCH_BOX = (Obj(Role.EDITABLETEXT, {State.FOCUSABLE}, "Edit"), [Edit, IAccessible])
FILE_ITEM = (Obj(Role.LISTITEM, windowClassName="DirectUIHWND", name="Jaws files"), [ListItem, UIA])
WEB_PAGE = (Obj(Role.DOCUMENT, windowClassName="Chrome_RenderWidgetHostHWND", name="GitHub"), [IAccessible])


def enhancedControlSupport(trustEvents=False):
	"""Enhanced Control Support 1.2.2's module, as far as its timer goes."""
	module = types.ModuleType(MODULE)
	module.config = types.SimpleNamespace(conf={"enhancedControlSupport": {"trustEvents": trustEvents}})

	class Win32:
		"""Its class for a window NVDA doesn't know."""

	class Complex(Win32):
		pass

	class TimerMixin:
		pass

	module.Win32, module.Complex, module.TimerMixin = Win32, Complex, TimerMixin
	exec(
		"def shouldUseTimerMixin(conf, obj, clsList):\n"
		"\n"
		"	for i in clsList:\n"
		"		if issubclass(i, Complex) or (issubclass(i, Win32) and not conf):\n"
		"			return(True)\n"
		"	if conf and not conf[1]:\n"
		"		return(True)\n"
		"	if not config.conf[\"enhancedControlSupport\"][\"trustEvents\"]:\n"
		"		return(True)\n"
		"	return(False)\n"
		"\n"
		"def chooseTimer(conf, obj, clsList):\n"
		"	# The end of GlobalPlugin.chooseNVDAObjectOverlayClasses.\n"
		"	if shouldUseTimerMixin(conf, obj, clsList):\n"
		"		clsList.insert(0, TimerMixin)\n",
		module.__dict__,
	)
	return module


class DocumentPollingTests(unittest.TestCase):
	def setUp(self):
		controlTypes = types.ModuleType("controlTypes")
		controlTypes.Role, controlTypes.State = Role, State
		editableText = types.ModuleType("editableText")
		editableText.EditableText = EditableText
		self.later = []
		wx = types.ModuleType("wx")
		wx.CallAfter = lambda function, *args: self.later.append((function, args))
		self.modules = {"controlTypes": controlTypes, "editableText": editableText, "wx": wx}
		patcher = mock.patch.dict(sys.modules, self.modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(self._restore)
		documentPolling._failed = False
		documentPolling._logged.clear()

	def _restore(self):
		documentPolling.unregister()
		documentPolling._replaced.clear()
		documentPolling._failed = False
		sys.modules.pop(MODULE, None)

	def load(self, **kwargs):
		"""NVDA imports Enhanced Control Support's global plugin."""
		module = enhancedControlSupport(**kwargs)
		sys.modules[MODULE] = module
		return module

	def runLater(self):
		"""What wx.CallAfter left for once NVDA has loaded its global plugins."""
		later, self.later[:] = list(self.later), []
		for function, args in later:
			function(*args)

	def getsTimer(self, module, case, conf=None):
		obj, classes = case
		clsList = list(classes)
		module.chooseTimer(conf, obj, clsList)
		return module.TimerMixin in clsList

	def test_notepadsDocumentGetsNoTimer(self):
		# The tester's Notepad: TimerMixin read the whole document as NVDA made the object, then every 50 ms.
		module = self.load()
		self.assertTrue(self.getsTimer(module, NOTEPAD_DOCUMENT), "Enhanced Control Support alone checks Notepad's document")
		documentPolling.register()
		self.assertFalse(self.getsTimer(module, NOTEPAD_DOCUMENT), "with the assistant, it doesn't")
		self.assertFalse(self.getsTimer(module, LOG_VIEWER), "nor NVDA's Log Viewer, a multi-line field")

	def test_everythingElseKeepsItsTimer(self):
		module = self.load()
		documentPolling.register()
		self.assertTrue(self.getsTimer(module, SEARCH_BOX), "a one-line field")
		self.assertTrue(self.getsTimer(module, FILE_ITEM), "a file in File Explorer")
		self.assertTrue(self.getsTimer(module, WEB_PAGE), "a web page NVDA reads in browse mode")

	def test_enhancedControlSupportsOwnControlsKeepTheirTimer(self):
		# A window NVDA doesn't know, for which Enhanced Control Support put in its own classes.
		module = self.load()
		documentPolling.register()
		obj, classes = NOTEPAD_DOCUMENT
		self.assertTrue(self.getsTimer(module, (obj, [module.Win32] + classes)))
		self.assertTrue(self.getsTimer(module, (obj, [module.Complex] + classes), conf=["edit", True, False]))

	def test_aWindowTheUserSetUpKeepsItsTimer(self):
		# NVDA+Alt+C in Enhanced Control Support, choosing to check the control rather than rely on its events.
		module = self.load(trustEvents=True)
		documentPolling.register()
		self.assertTrue(self.getsTimer(module, NOTEPAD_DOCUMENT, conf=["edit", False, False]))

	def test_relyingOnEventsNothingChanges(self):
		module = self.load(trustEvents=True)
		documentPolling.register()
		for case in (NOTEPAD_DOCUMENT, LOG_VIEWER, FILE_ITEM):
			self.assertFalse(self.getsTimer(module, case))

	def test_enhancedControlSupportLoadedAfterTheAssistant(self):
		# NVDA imports the global plugins one after another; the assistant may come first.
		documentPolling.register()
		self.assertFalse(documentPolling.isInstalled())
		module = self.load()
		self.assertTrue(self.getsTimer(module, NOTEPAD_DOCUMENT), "not yet")
		self.runLater()
		self.assertTrue(documentPolling.isInstalled())
		self.assertFalse(self.getsTimer(module, NOTEPAD_DOCUMENT), "once NVDA has loaded every plugin")

	def test_withoutEnhancedControlSupportNothingHappens(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			documentPolling.register()
			self.runLater()
			documentPolling._log().debug("end")
		self.assertFalse(documentPolling.isInstalled())
		self.assertEqual([line for line in logged.output if "jawsMigrator" in line], [])

	def test_turnedOffEnhancedControlSupportHasItsOwnBack(self):
		module = self.load()
		own = module.shouldUseTimerMixin
		documentPolling.register()
		documentPolling.unregister()
		self.assertIs(module.shouldUseTimerMixin, own)
		self.assertTrue(self.getsTimer(module, NOTEPAD_DOCUMENT))
		documentPolling.register()
		self.assertIs(module.shouldUseTimerMixin.__wrapped__, own, "on again, wrapped once")

	def test_registeredTwiceWrappedOnce(self):
		module = self.load()
		own = module.shouldUseTimerMixin
		documentPolling.register()
		documentPolling.register()
		self.assertIs(module.shouldUseTimerMixin.__wrapped__, own)
		self.assertEqual(len(documentPolling._replaced), 1)

	def test_anotherAddonsWrapperOverTheAssistants(self):
		module = self.load()
		documentPolling.register()
		ours = module.shouldUseTimerMixin

		@functools.wraps(ours)
		def otherAddon(*args, **kwargs):
			return ours(*args, **kwargs)

		module.shouldUseTimerMixin = otherAddon
		documentPolling.unregister()
		self.assertIs(module.shouldUseTimerMixin, otherAddon)
		self.assertTrue(self.getsTimer(module, NOTEPAD_DOCUMENT), "the assistant's, still inside it, does nothing")
		documentPolling.register()
		self.assertIs(module.shouldUseTimerMixin, otherAddon, "not wrapped a second time")
		self.assertFalse(self.getsTimer(module, NOTEPAD_DOCUMENT))

	def test_pluginsReloaded(self):
		# NVDA+Control+F3 imports every global plugin again: a new Enhanced Control Support module.
		first = self.load()
		documentPolling.register()
		documentPolling.unregister()
		documentPolling.register()
		second = self.load()
		self.assertTrue(self.getsTimer(second, NOTEPAD_DOCUMENT))
		documentPolling.register()
		self.assertFalse(self.getsTimer(second, NOTEPAD_DOCUMENT), "a migration or reload applies the settings again")
		self.assertFalse(self.getsTimer(first, NOTEPAD_DOCUMENT))

	def test_anotherVersionWithoutTheChoiceIsLeftAlone(self):
		module = self.load()
		del module.shouldUseTimerMixin
		with self.assertLogs("nvda", level="DEBUG") as logged:
			documentPolling.register()
		self.assertTrue(any("Enhanced Control Support has no shouldUseTimerMixin" in line for line in logged.output), logged.output)
		self.assertFalse(hasattr(module, "shouldUseTimerMixin"))
		del module.TimerMixin
		module.shouldUseTimerMixin = lambda conf, obj, clsList: True
		documentPolling.unregister()
		documentPolling.register()
		self.assertFalse(documentPolling.isInstalled(), "a choice without its TimerMixin is not the one the assistant knows")

	def test_aFailureLeavesEnhancedControlSupportsChoice(self):
		module = self.load()
		documentPolling.register()

		class Dead:
			windowClassName = "RichEditD2DPT"

			@property
			def role(self):
				raise RuntimeError("the object died")

		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.assertTrue(self.getsTimer(module, (Dead(), [EditableTextWithAutoSelectDetection, UIA])))
			self.assertTrue(self.getsTimer(module, (Dead(), [EditableTextWithAutoSelectDetection, UIA])))
		failures = [line for line in logged.output if "could not tell whether a control is a document" in line]
		self.assertEqual(len(failures), 1, logged.output)

	def test_whatTheLogSaysOnce(self):
		module = self.load()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			documentPolling.register()
			for _ in range(3):
				self.getsTimer(module, NOTEPAD_DOCUMENT)
				self.getsTimer(module, LOG_VIEWER)
				self.getsTimer(module, FILE_ITEM)
		lines = [line for line in logged.output if "jawsMigrator" in line]
		self.assertEqual(sum("leaves its timer off documents NVDA follows" in line for line in lines), 1, lines)
		self.assertEqual(sum("doesn't check this document (RichEditD2DPT)" in line for line in lines), 1, lines)
		self.assertEqual(sum("doesn't check this document (RICHEDIT50W)" in line for line in lines), 1, lines)
		self.assertEqual(len(lines), 3, lines)

	def test_theSetting(self):
		self.assertTrue(documentPolling.wanted({}))
		self.assertFalse(documentPolling.wanted({documentPolling.STATE_KEY: False}))
		self.assertFalse(documentPolling.wanted(None))
		self.assertIs(state.DEFAULTS[documentPolling.STATE_KEY], True)


if __name__ == "__main__":
	unittest.main()
