# Unit tests for version 1.23, from a tester's report (issue 15): typing in a large document, letters and spaces went
# missing ("a outlook message" came out "a outlook meg"), came out of order, and NVDA didn't say them. It didn't happen
# in a new, empty Notepad document.
# On another computer, NVDA 2026.2 with none of the tester's add-ons, real key presses one every 150 ms at the top of
# a copy of the tester's 21 MB NVDA log in Windows 11's Notepad lost 5 to 23 of 59 characters a run. Notepad takes
# 0.3 seconds a character there with NVDA quit, and lost 7 and 4 in two runs of three; a test program that only
# listened for the document's Value property, with NVDA quit, lost 4, 17 and 9, and made each character 0.1 seconds
# slower: Notepad builds its whole text, 42 MB, for the event at every key, and the build fails every time.
# NVDA 2026.2 listens for the Value of the focused control (UIAHandler.UIAHandler.addLocalEventHandlerGroupToElement,
# its "local event handler group") and ignores a UIA text control's Value change (NVDAObjects.UIA.UIA.event_valueChange).
# - documentValues: a focused document, or multi-line field, that NVDA reads through UIA text and whose Value changes
#   NVDA ignores, gets NVDA's local events without the Value property; everything else keeps NVDA's own.
# - typingWatch: L after NVDA+Shift+J was logged as a key Outlook and Edge "never typed": a key NVDA runs a command for
#   never reaches the program, so it isn't waited for.
# The imitation NVDA runs NVDA 2026.2's own UIAHandler.UIAHandler._createLocalEventHandlerGroup,
# addLocalEventHandlerGroupToElement, removeLocalEventHandlerGroupFromElement, addEventHandlerGroup and
# removeEventHandlerGroup, and NVDAObjects.UIA.UIA.event_gainFocus, event_loseFocus and event_valueChange, word for
# word. The assistant's code is the real one.
# Run: python -m unittest tests.test_v123_documentValues -v

import enum
import logging
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import documentValues, state, typingWatch  # noqa: E402
from test_v121_alerts import nvdaCode  # noqa: E402

#: NVDA 2026.2, source/UIAHandler/__init__.py, UIAHandler._createLocalEventHandlerGroup, word for word.
NVDA_CREATE_LOCAL_EVENT_HANDLER_GROUP = '''
def _createLocalEventHandlerGroup(self, handler: "UIAHandler"):
	if isinstance(self.clientObject, UIA.IUIAutomation6):
		self.localEventHandlerGroup = self.clientObject.CreateEventHandlerGroup()
		self.localEventHandlerGroupWithTextChanges = self.clientObject.CreateEventHandlerGroup()
	else:
		self.localEventHandlerGroup = utils.FakeEventHandlerGroup(self.clientObject)
		self.localEventHandlerGroupWithTextChanges = utils.FakeEventHandlerGroup(self.clientObject)
	self.localEventHandlerGroup.AddPropertyChangedEventHandler(
		UIA.TreeScope_Ancestors | UIA.TreeScope_Element,
		self.baseCacheRequest,
		handler,
		*self.clientObject.IntSafeArrayToNativeArray(localEventHandlerGroupUIAPropertyIds),
	)
	self.localEventHandlerGroupWithTextChanges.AddPropertyChangedEventHandler(
		UIA.TreeScope_Ancestors | UIA.TreeScope_Element,
		self.baseCacheRequest,
		handler,
		*self.clientObject.IntSafeArrayToNativeArray(localEventHandlerGroupUIAPropertyIds),
	)
	for eventId in localEventHandlerGroupUIAEventIds:
		self.localEventHandlerGroup.AddAutomationEventHandler(
			eventId,
			UIA.TreeScope_Ancestors | UIA.TreeScope_Element,
			self.baseCacheRequest,
			handler,
		)
		self.localEventHandlerGroupWithTextChanges.AddAutomationEventHandler(
			eventId,
			UIA.TreeScope_Ancestors | UIA.TreeScope_Element,
			self.baseCacheRequest,
			handler,
		)
	self.localEventHandlerGroupWithTextChanges.AddAutomationEventHandler(
		UIA.UIA_Text_TextChangedEventId,
		UIA.TreeScope_Ancestors | UIA.TreeScope_Element,
		self.baseCacheRequest,
		handler,
	)
'''

#: NVDA 2026.2, source/UIAHandler/__init__.py, UIAHandler.addEventHandlerGroup, word for word.
NVDA_ADD_EVENT_HANDLER_GROUP = '''
def addEventHandlerGroup(self, element, eventHandlerGroup):
	if isinstance(eventHandlerGroup, UIA.IUIAutomationEventHandlerGroup):
		self.clientObject.AddEventHandlerGroup(element, eventHandlerGroup)
	elif isinstance(eventHandlerGroup, utils.FakeEventHandlerGroup):
		eventHandlerGroup.registerToClientObject(element)
	else:
		raise NotImplementedError
'''

#: NVDA 2026.2, source/UIAHandler/__init__.py, UIAHandler.removeEventHandlerGroup, word for word.
NVDA_REMOVE_EVENT_HANDLER_GROUP = '''
def removeEventHandlerGroup(self, element, eventHandlerGroup):
	if isinstance(eventHandlerGroup, UIA.IUIAutomationEventHandlerGroup):
		self.clientObject.RemoveEventHandlerGroup(element, eventHandlerGroup)
	elif isinstance(eventHandlerGroup, utils.FakeEventHandlerGroup):
		eventHandlerGroup.unregisterFromClientObject(element)
	else:
		raise NotImplementedError
'''

#: NVDA 2026.2, source/UIAHandler/__init__.py, UIAHandler.addLocalEventHandlerGroupToElement, word for word.
NVDA_ADD_LOCAL_EVENT_HANDLER_GROUP_TO_ELEMENT = '''
def addLocalEventHandlerGroupToElement(self, element, isFocus=False):
	if not self.localEventHandlerGroup or element in self._localEventHandlerGroupElements:
		return

	def func():
		if isFocus:
			try:
				isStillFocus = self.clientObject.CompareElements(
					self.clientObject.GetFocusedElement(),
					element,
				)
			except COMError:
				isStillFocus = False
			if not isStillFocus:
				return
		try:
			if (
				element.currentClassName in textChangeUIAClassNames
				or element.CachedAutomationID in textChangeUIAAutomationIDs
				or (
					not utils._shouldUseWindowsTerminalNotifications()
					and element.currentClassName in windowsTerminalUIAClassNames
				)
			):
				group = self.localEventHandlerGroupWithTextChanges
				logPrefix = "Explicitly"
			else:
				group = self.localEventHandlerGroup
				logPrefix = "Not"

			if _isDebug():
				log.debugWarning(
					f"{logPrefix} registering for textChange events from UIA element "
					f"with class name {repr(element.currentClassName)} "
					f"and automation ID {repr(element.CachedAutomationID)}",
				)
			self.addEventHandlerGroup(element, group)
		except COMError:
			log.error("Could not register for UIA events for element", exc_info=True)
		else:
			self._localEventHandlerGroupElements.add(element)

	self.MTAThreadQueue.put_nowait(func)
'''

#: NVDA 2026.2, source/UIAHandler/__init__.py, UIAHandler.removeLocalEventHandlerGroupFromElement, word for word.
NVDA_REMOVE_LOCAL_EVENT_HANDLER_GROUP_FROM_ELEMENT = '''
def removeLocalEventHandlerGroupFromElement(self, element):
	if not self.localEventHandlerGroup or element not in self._localEventHandlerGroupElements:
		return

	def func():
		try:
			self.removeEventHandlerGroup(element, self.localEventHandlerGroup)
		except COMError:
			# The old UIAElement has probably died as the window was closed.
			# The system should forget the old event registration itself.
			# Yet, as we don't expect this to happen very often, log a debug warning.
			log.debugWarning("Could not unregister for UIA events for element", exc_info=True)
		self._localEventHandlerGroupElements.remove(element)

	self.MTAThreadQueue.put_nowait(func)
'''

#: NVDA 2026.2, source/NVDAObjects/UIA/__init__.py, UIA.event_gainFocus, UIA.event_loseFocus and
#: UIA.event_valueChange, word for word.
NVDA_UIA_EVENTS = '''
class UIA(NVDAObject):
	def event_gainFocus(self):
		UIAHandler.handler.addLocalEventHandlerGroupToElement(self.UIAElement, isFocus=True)
		super().event_gainFocus()

	def event_loseFocus(self):
		super().event_loseFocus()
		UIAHandler.handler.removeLocalEventHandlerGroupFromElement(self.UIAElement)

	def event_valueChange(self):
		if issubclass(self.TextInfo, UIATextInfo):
			return
		return super(UIA, self).event_valueChange()
'''

#: UI Automation's identifiers, as NVDA's comInterfaces.UIAutomationClient has them.
UIA = types.SimpleNamespace(
	TreeScope_Element=1,
	TreeScope_Ancestors=16,
	UIA_Text_TextChangedEventId=20015,
	UIA_Text_TextSelectionChangedEventId=20014,
	UIA_NamePropertyId=30005,
	UIA_IsEnabledPropertyId=30010,
	UIA_HelpTextPropertyId=30013,
	UIA_ItemStatusPropertyId=30026,
	UIA_ValueValuePropertyId=30045,
	UIA_RangeValueValuePropertyId=30047,
	UIA_ExpandCollapseExpandCollapseStatePropertyId=30070,
	UIA_ToggleToggleStatePropertyId=30086,
	UIA_ControllerForPropertyId=30104,
	UIA_DragDropEffectPropertyId=30139,
	UIA_DropTargetDropTargetEffectPropertyId=30142,
)
#: NVDA 2026.2's UIAPropertyIdsToNVDAEventNames, less globalEventHandlerGroupUIAPropertyIds.
LOCAL_PROPERTIES = {
	UIA.UIA_NamePropertyId,
	UIA.UIA_HelpTextPropertyId,
	UIA.UIA_ExpandCollapseExpandCollapseStatePropertyId,
	UIA.UIA_ToggleToggleStatePropertyId,
	UIA.UIA_IsEnabledPropertyId,
	UIA.UIA_ValueValuePropertyId,
	UIA.UIA_ControllerForPropertyId,
	UIA.UIA_ItemStatusPropertyId,
}
LOCAL_EVENTS = {UIA.UIA_Text_TextSelectionChangedEventId}


class COMError(Exception):
	"""comtypes' COMError."""


class IUIAutomation6:
	"""UI Automation's client with event handler groups (Windows 10 1809 and later)."""


class EventHandlerGroup:
	"""IUIAutomationEventHandlerGroup: the property changes and events it asks for."""

	def __init__(self):
		self.properties = []
		self.events = []

	def AddPropertyChangedEventHandler(self, scope, cacheRequest, handler, propertyArray, propertyCount):
		self.properties.append((scope, cacheRequest, handler, sorted(propertyArray[:propertyCount])))

	def AddAutomationEventHandler(self, eventId, scope, cacheRequest, handler):
		self.events.append((eventId, scope, cacheRequest, handler))

	def propertyIds(self):
		return {propertyId for scope, cache, handler, ids in self.properties for propertyId in ids}

	def eventIds(self):
		return {event[0] for event in self.events}


UIA.IUIAutomation6 = IUIAutomation6
UIA.IUIAutomationEventHandlerGroup = EventHandlerGroup


class Client(IUIAutomation6):
	"""NVDA's UI Automation client object: its registrations, and the element with the focus."""

	def __init__(self):
		self.registered = []
		self.focused = None
		self.made = 0
		self.failToMake = False

	def CreateEventHandlerGroup(self):
		if self.failToMake:
			raise COMError("no groups for the test")
		self.made += 1
		return EventHandlerGroup()

	def IntSafeArrayToNativeArray(self, ids):
		ids = list(ids)
		return ids, len(ids)

	def AddEventHandlerGroup(self, element, group):
		self.registered.append((element, group))

	def RemoveEventHandlerGroup(self, element, group):
		if (element, group) not in self.registered:
			raise COMError("that group isn't registered for that element")
		self.registered.remove((element, group))

	def CompareElements(self, one, other):
		return one is other

	def GetFocusedElement(self):
		return self.focused


class Element:
	"""A UI Automation element, with NVDA's cached properties."""

	def __init__(self, className, automationId=""):
		self.currentClassName = className
		self.CachedAutomationID = automationId


class Queue:
	"""NVDA's MTAThreadQueue: the functions its UI Automation thread runs, in order."""

	def __init__(self):
		self.waiting = []

	def put_nowait(self, function):
		self.waiting.append(function)

	def run(self):
		while self.waiting:
			self.waiting.pop(0)()


class Role(enum.Enum):
	DOCUMENT = "document"
	EDITABLETEXT = "edit"
	SLIDER = "slider"


class State(enum.Enum):
	MULTILINE = "multi line"


class NVDAObject:
	"""NVDA's NVDAObjects.NVDAObject, as far as these events go."""

	def event_gainFocus(self):
		pass

	def event_loseFocus(self):
		pass

	def event_valueChange(self):
		self.valueSaid = True


class UIATextInfo:
	"""NVDA's NVDAObjects.UIA.UIATextInfo."""


class OtherTextInfo:
	"""Text NVDA reads another way than through UI Automation's text, such as its display model."""


class UIAHandlerTests(unittest.TestCase):
	def setUp(self):
		self.focus = None
		self.client = Client()
		namespace = {
			"UIA": UIA,
			"utils": types.SimpleNamespace(
				FakeEventHandlerGroup=type("FakeEventHandlerGroup", (), {}),
				_shouldUseWindowsTerminalNotifications=lambda: True,
			),
			"COMError": COMError,
			"textChangeUIAClassNames": ("_WwG", "WinwordWindow", "EXCEL7"),
			"textChangeUIAAutomationIDs": ("Text Area",),
			"windowsTerminalUIAClassNames": ("TermControl", "TermControl2", "WPFTermControl"),
			"_isDebug": lambda: False,
			"log": logging.getLogger("nvda"),
			"localEventHandlerGroupUIAPropertyIds": LOCAL_PROPERTIES,
			"localEventHandlerGroupUIAEventIds": LOCAL_EVENTS,
		}
		methods = {
			name: nvdaCode(source, name, namespace)
			for name, source in (
				("_createLocalEventHandlerGroup", NVDA_CREATE_LOCAL_EVENT_HANDLER_GROUP),
				("addEventHandlerGroup", NVDA_ADD_EVENT_HANDLER_GROUP),
				("removeEventHandlerGroup", NVDA_REMOVE_EVENT_HANDLER_GROUP),
				("addLocalEventHandlerGroupToElement", NVDA_ADD_LOCAL_EVENT_HANDLER_GROUP_TO_ELEMENT),
				("removeLocalEventHandlerGroupFromElement", NVDA_REMOVE_LOCAL_EVENT_HANDLER_GROUP_FROM_ELEMENT),
			)
		}
		self.nvdaMethods = dict(methods)
		self.UIAHandlerClass = type("UIAHandler", (), methods)
		self.handler = self.UIAHandlerClass()
		self.handler.clientObject = self.client
		self.handler.baseCacheRequest = "NVDA's base cache request"
		# NVDA's "enhanced event processing", on by default: its rate-limited handler gets the events.
		self.handler._rateLimitedEventHandler = "NVDA's rate-limited event handler"
		self.handler._localEventHandlerGroupElements = set()
		self.handler.MTAThreadQueue = Queue()
		# As NVDA does in its UI Automation thread when it registers selectively (Windows 11 22H2 and later).
		self.handler._createLocalEventHandlerGroup(self.handler._rateLimitedEventHandler)
		self.made = self.client.made
		UIAHandler = types.ModuleType("UIAHandler")
		UIAHandler.UIAHandler = self.UIAHandlerClass
		UIAHandler.handler = self.handler
		UIAHandler.UIA = UIA
		UIAHandler.utils = namespace["utils"]
		UIAHandler.localEventHandlerGroupUIAPropertyIds = LOCAL_PROPERTIES
		UIAHandler.localEventHandlerGroupUIAEventIds = LOCAL_EVENTS
		self.UIA = nvdaCode(NVDA_UIA_EVENTS, "UIA", {"NVDAObject": NVDAObject, "UIAHandler": UIAHandler, "UIATextInfo": UIATextInfo})
		modules = {
			"UIAHandler": UIAHandler,
			"NVDAObjects.UIA": types.SimpleNamespace(UIA=self.UIA, UIATextInfo=UIATextInfo),
			"controlTypes": types.SimpleNamespace(Role=Role, State=State),
			"api": types.SimpleNamespace(getFocusObject=lambda: self.focus),
		}
		patcher = mock.patch.dict(sys.modules, modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		documentValues._failed = False
		documentValues._logged.clear()
		self.addCleanup(self._unregister)
		documentValues.register()

	def _unregister(self):
		documentValues.unregister()
		documentValues._failed = False
		documentValues._logged.clear()

	def uiaObject(self, className="RichEditD2DPT", role=Role.DOCUMENT, states=(), TextInfo=UIATextInfo, base=None):
		"""A UIA NVDAObject: by default Windows 11 Notepad's document."""
		cls = type("Control", (base or self.UIA,), {})
		obj = cls()
		obj.UIAElement = Element(className)
		obj.windowClassName = className
		obj.role = role
		obj.states = set(states)
		obj.TextInfo = TextInfo
		return obj

	def gainFocus(self, obj):
		"""NVDA's focus event: NVDA's main thread notes the focus, then its UI Automation thread registers the events."""
		self.focus = obj
		self.client.focused = obj.UIAElement
		obj.event_gainFocus()
		self.handler.MTAThreadQueue.run()

	def loseFocus(self, obj):
		obj.event_loseFocus()
		self.handler.MTAThreadQueue.run()

	def groupOf(self, obj):
		groups = [group for element, group in self.client.registered if element is obj.UIAElement]
		self.assertEqual(len(groups), 1, "the element is registered once")
		return groups[0]

	def test_notepadsDocumentGetsNvdasEventsWithoutItsValue(self):
		notepad = self.uiaObject()
		with self.assertLogs("nvda", level="DEBUG") as logs:
			self.gainFocus(notepad)
		group = self.groupOf(notepad)
		nvdas = self.handler.localEventHandlerGroup
		self.assertIsNot(group, nvdas)
		self.assertEqual(group.propertyIds(), nvdas.propertyIds() - {UIA.UIA_ValueValuePropertyId})
		self.assertNotIn(UIA.UIA_ValueValuePropertyId, group.propertyIds())
		self.assertIn(UIA.UIA_NamePropertyId, group.propertyIds(), "a change of name still comes")
		self.assertEqual(group.eventIds(), nvdas.eventIds(), "and the caret events")
		self.assertNotIn(UIA.UIA_Text_TextChangedEventId, group.eventIds(), "and no text changes, as NVDA doesn't ask for them here")
		for scope, cacheRequest, handler, ids in group.properties:
			self.assertEqual(
				(scope, cacheRequest, handler),
				(UIA.TreeScope_Ancestors | UIA.TreeScope_Element, "NVDA's base cache request", "NVDA's rate-limited event handler"),
			)
		for eventId, scope, cacheRequest, handler in group.events:
			self.assertEqual(
				(scope, cacheRequest, handler),
				(UIA.TreeScope_Ancestors | UIA.TreeScope_Element, "NVDA's base cache request", "NVDA's rate-limited event handler"),
			)
		self.assertIn(notepad.UIAElement, self.handler._localEventHandlerGroupElements, "NVDA knows the element has its events")
		self.assertTrue(any("RichEditD2DPT" in record.getMessage() for record in logs.records), "the log says why, once")
		# NVDA still ignores a Value change that comes anyway.
		notepad.event_valueChange()
		self.assertFalse(getattr(notepad, "valueSaid", False))

	def test_theDocumentLosesTheFocus(self):
		notepad = self.uiaObject()
		self.gainFocus(notepad)
		self.loseFocus(notepad)
		self.assertEqual(self.client.registered, [], "the registration without the Value is the one taken off")
		self.assertNotIn(notepad.UIAElement, self.handler._localEventHandlerGroupElements)
		self.assertEqual(documentValues._registered, {})
		# And back to it: registered again the same way, with the same group.
		self.gainFocus(notepad)
		self.assertNotIn(UIA.UIA_ValueValuePropertyId, self.groupOf(notepad).propertyIds())
		self.assertEqual(self.client.made - self.made, 1, "the group without the Value is made once")

	def test_aMultiLineFieldToo(self):
		field = self.uiaObject("Edit", Role.EDITABLETEXT, states=[State.MULTILINE])
		self.gainFocus(field)
		self.assertNotIn(UIA.UIA_ValueValuePropertyId, self.groupOf(field).propertyIds())

	def test_aSingleLineFieldKeepsNvdasEvents(self):
		field = self.uiaObject("Edit", Role.EDITABLETEXT)
		self.gainFocus(field)
		self.assertIs(self.groupOf(field), self.handler.localEventHandlerGroup)

	def test_aSliderKeepsNvdasEvents(self):
		slider = self.uiaObject("Slider", Role.SLIDER)
		self.gainFocus(slider)
		self.assertIs(self.groupOf(slider), self.handler.localEventHandlerGroup)

	def test_aDocumentNvdaDoesntReadThroughUiaTextKeepsItsValue(self):
		document = self.uiaObject("Custom", Role.DOCUMENT, TextInfo=OtherTextInfo)
		self.gainFocus(document)
		self.assertIs(self.groupOf(document), self.handler.localEventHandlerGroup)
		document.event_valueChange()
		self.assertTrue(document.valueSaid, "NVDA says its Value when it changes, as before")

	def test_anObjectThatHandlesItsValueChangesKeepsThem(self):
		class ItsOwnValue(self.UIA):
			def event_valueChange(self):
				self.valueSaid = True

		document = self.uiaObject(base=ItsOwnValue)
		self.gainFocus(document)
		self.assertIs(self.groupOf(document), self.handler.localEventHandlerGroup)

	def test_whereNvdaAsksForTextChangesTheyStillCome(self):
		word = self.uiaObject("_WwG")
		self.gainFocus(word)
		group = self.groupOf(word)
		nvdas = self.handler.localEventHandlerGroupWithTextChanges
		self.assertIsNot(group, nvdas)
		self.assertEqual(group.propertyIds(), nvdas.propertyIds() - {UIA.UIA_ValueValuePropertyId})
		self.assertEqual(group.eventIds(), nvdas.eventIds())
		self.assertIn(UIA.UIA_Text_TextChangedEventId, group.eventIds())
		self.loseFocus(word)
		self.assertEqual(self.client.registered, [])

	def test_theFocusMovedOnBeforeNvdaRegistered(self):
		notepad = self.uiaObject()
		other = self.uiaObject("Button", Role.SLIDER)
		self.focus = notepad
		self.client.focused = other.UIAElement
		notepad.event_gainFocus()
		self.handler.MTAThreadQueue.run()
		self.assertEqual(self.client.registered, [], "NVDA registers nothing for a control that no longer has the focus")
		self.gainFocus(other)
		self.assertIs(self.groupOf(other), self.handler.localEventHandlerGroup)

	def test_nvdaRegisteringForEveryControlAtOnceIsLeftAlone(self):
		# NVDA's Advanced settings, "Windows UI Automation event registration": Global. NVDA has no local groups.
		self.handler.localEventHandlerGroup = None
		self.handler.localEventHandlerGroupWithTextChanges = None
		notepad = self.uiaObject()
		self.gainFocus(notepad)
		self.assertEqual(self.client.registered, [])

	def test_withoutGroupsNvdasOwnEventsStay(self):
		self.client.failToMake = True
		notepad = self.uiaObject()
		with self.assertLogs("nvda", level="DEBUG") as logs:
			self.gainFocus(notepad)
		self.assertIs(self.groupOf(notepad), self.handler.localEventHandlerGroup)
		self.assertTrue(any("NVDA listens for it" in record.getMessage() for record in logs.records))
		self.loseFocus(notepad)
		self.assertEqual(self.client.registered, [])

	def test_turnedOffWhileNotepadHasTheFocus(self):
		notepad = self.uiaObject()
		self.gainFocus(notepad)
		documentValues.unregister()
		self.assertFalse(documentValues.isRegistered())
		for name, function in self.nvdaMethods.items():
			self.assertIs(self.UIAHandlerClass.__dict__[name], function, f"NVDA has its own {name} back")
		self.handler.MTAThreadQueue.run()
		self.assertIs(self.groupOf(notepad), self.handler.localEventHandlerGroup, "the document gets NVDA's own events back")
		self.loseFocus(notepad)
		self.assertEqual(self.client.registered, [])
		documentValues.register()
		self.gainFocus(notepad)
		self.assertNotIn(UIA.UIA_ValueValuePropertyId, self.groupOf(notepad).propertyIds(), "and on again")

	def test_notedDocumentsAreKeptToAFew(self):
		for _ in range(documentValues.MOST_PENDING + 10):
			notepad = self.uiaObject()
			self.focus = notepad
			notepad.event_gainFocus()
		self.assertEqual(len(documentValues._pending), documentValues.MOST_PENDING)
		self.handler.MTAThreadQueue.waiting.clear()
		documentValues._pending.clear()

	def test_anotherAddonsWrapperIsLeftInPlace(self):
		ours = self.UIAHandlerClass.__dict__["addEventHandlerGroup"]

		def theirs(self, element, group):
			return ours(self, element, group)

		self.UIAHandlerClass.addEventHandlerGroup = theirs
		documentValues.unregister()
		self.assertIs(self.UIAHandlerClass.__dict__["addEventHandlerGroup"], theirs)
		self.assertIs(self.UIAHandlerClass.__dict__["removeEventHandlerGroup"], self.nvdaMethods["removeEventHandlerGroup"])


class RegisterTests(unittest.TestCase):
	def tearDown(self):
		documentValues.unregister()
		documentValues._failed = False

	def test_withoutNvdasMethodsNothingChanges(self):
		UIAHandlerClass = type("UIAHandler", (), {"addEventHandlerGroup": lambda self, element, group: None})
		with mock.patch.dict(sys.modules, {"UIAHandler": types.SimpleNamespace(UIAHandler=UIAHandlerClass)}):
			documentValues.register()
		self.assertFalse(documentValues.isRegistered())
		self.assertEqual(set(UIAHandlerClass.__dict__) & {"addLocalEventHandlerGroupToElement", "removeEventHandlerGroup"}, set())
		self.assertFalse(hasattr(UIAHandlerClass.__dict__["addEventHandlerGroup"], documentValues.MARK))

	def test_onUnlessTurnedOff(self):
		self.assertTrue(documentValues.wanted({}))
		self.assertTrue(documentValues.wanted({documentValues.STATE_KEY: True}))
		self.assertFalse(documentValues.wanted({documentValues.STATE_KEY: False}))
		self.assertFalse(documentValues.wanted(None))
		self.assertIs(state.DEFAULTS[documentValues.STATE_KEY], True)


class EditableText:
	"""NVDA's editableText.EditableText."""


class Outlook(EditableText):
	"""An Outlook message's body, where NVDA hears typing from Outlook."""

	treeInterceptor = None
	appModule = types.SimpleNamespace(appName="outlook")


def key(character, script=None):
	"""NVDA 2026.2's KeyboardInputGesture for a key that types ``character``, and the command NVDA runs for it."""
	return types.SimpleNamespace(vkCode=0x41, isModifier=False, isCharacter=True, character=character, mainKeyName=character, script=script)


class LayerKeyTests(unittest.TestCase):
	def setUp(self):
		self.now = 0.0
		modules = {
			"api": types.SimpleNamespace(getFocusObject=lambda: Outlook()),
			"editableText": types.SimpleNamespace(EditableText=EditableText),
			"keyboardHandler": types.SimpleNamespace(shouldUseToUnicodeEx=lambda focus: False),
			"watchdog": types.SimpleNamespace(isCoreAsleep=lambda: True),
		}
		patcher = mock.patch.dict(sys.modules, modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		clock = mock.patch.object(typingWatch, "time", types.SimpleNamespace(monotonic=lambda: self.now))
		clock.start()
		self.addCleanup(clock.stop)
		typingWatch._waiting.clear()
		typingWatch._registered = True
		typingWatch._failed = False
		logger = logging.getLogger("nvda")
		self.addCleanup(logger.setLevel, logger.level)
		logger.setLevel(logging.DEBUG)
		self.addCleanup(self._restore)

	def _restore(self):
		typingWatch._registered = False
		typingWatch._waiting.clear()

	def test_theLayersLIsntWaitedFor(self):
		# The tester's log, 26 September, 08:35:26: NVDA+Shift+J, then L in an Outlook message, which saved NVDA's log
		# in a zip file. At 08:35:36: "jawsMigrator: outlook never typed 'l', pressed 10057 ms ago".
		def saveLog(gesture):
			pass

		self.assertIs(typingWatch.noteKey(gesture=key("l", script=saveLog)), True, "the key goes on to NVDA's command")
		self.assertEqual(list(typingWatch._waiting), [])
		self.now = 10.057
		with self.assertNoLogs("nvda", level="DEBUG"):
			typingWatch.noteKey(gesture=key("x", script=saveLog))
		self.assertEqual(list(typingWatch._waiting), [])

	def test_aLetterOutlookTypesIsStillWaitedFor(self):
		typingWatch.noteKey(gesture=key("l"))
		self.assertEqual([entry[1] for entry in typingWatch._waiting], ["l"])
		typingWatch.typed("l")
		self.assertEqual(list(typingWatch._waiting), [])


if __name__ == "__main__":
	unittest.main()
