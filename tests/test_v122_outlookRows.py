# Unit tests for version 1.22, from a tester's report (issue 17): "When pressing end to go to new outlook message it
# says the wrong one is highlighted. ... It said your reply was highlighted it wasn't it was another message." The
# tester pressed End in Outlook's Inbox to go to the newest message. The log attached to the issue shows:
# 08:43:47.367 Speaking [... "From joshknnd1982, Subject Re: [joshknnd1982/jawsMigrator] This players name isn't being
#              spoken correctly (Issue #13), Received Sat 9/26/2026 7:34 AM, Size 29 KB,", '2621 of 2663', ...]
# 08:43:47.778 Input: kb(laptop):end
# 08:43:47.856 Speaking [... "unread From joshknnd1982, Subject Re: [joshknnd1982/jawsMigrator] This players name isn't
#              being spoken correctly (Issue #13), Received Sat 9/26/2026 7:34 AM, Size 29 KB,", ...]
# 08:43:47.991 Speaking [... 'unread From 🔴 RTM News, Subject 1 Billion Deaths: Insane Warning, Received Sat 9/26/2026
#              8:38 AM, Size 51 KB,', ..., '2663 of 2663', CancellableSpeech (still valid), ...]
# 08:43:49.201 Input: kb(laptop):enter, which opened RTM News's message.
# The same at 09:03:06 (End), and at 08:29:19 with Down Arrow. Not at 09:03:39, where the message left was unread too.
# NVDA says the message left as a change of its name (NVDAObject.event_nameChange: the focus is still on it), and NVDA's
# Outlook support takes a message's unread status from Outlook's selection (UIAGridRow._get_name), which is already the
# message moved to. JAWS says the new active item only (Outlook.jss, ActiveItemChangedEvent).
# - outlookRows: a change of name of the Outlook message NVDA's focus is on isn't said when UI Automation's focus has
#   left it. A change of the message Outlook's focus is still on, and anything else, is said as NVDA says it.
# The imitation NVDA runs NVDA 2026.2's own eventHandler._EventExecuter, NVDAObject.event_nameChange and
# appModules.outlook.UIAGridRow._get_name, word for word, against an imitation of Outlook's object model and of its
# message list in UI Automation. The assistant's code is the real one.
# Run: python -m unittest tests.test_v122_outlookRows -v

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
from jawsMigrator import outlookRows, state  # noqa: E402

#: NVDA 2026.2, source/eventHandler.py, word for word.
NVDA_EVENT_EXECUTER = '''
class _EventExecuter(garbageHandler.TrackedObject):
	"""Facilitates execution of a chain of event functions.
	L{gen} generates the event functions and positional arguments.
	L{next} calls the next function in the chain.
	"""

	def __init__(self, eventName, obj, kwargs):
		self.kwargs = kwargs
		self._gen = self.gen(eventName, obj)
		try:
			self.next()
		except StopIteration:
			pass
		finally:
			del self._gen

	def next(self):
		func, args = next(self._gen)
		try:
			return func(*args, **self.kwargs)
		except TypeError:
			log.warning(
				"Could not execute function {func} defined in {module} module; kwargs: {kwargs}".format(
					func=func.__name__,
					module=func.__module__ or "unknown",
					kwargs=self.kwargs,
				),
				exc_info=True,
			)
			return extensionPoints.callWithSupportedKwargs(func, *args, **self.kwargs)

	def gen(self, eventName, obj):
		funcName = "event_%s" % eventName

		# Global plugin level.
		for plugin in globalPluginHandler.runningPlugins:
			func = getattr(plugin, funcName, None)
			if func:
				yield func, (obj, self.next)

		# App module level.
		app = obj.appModule
		if app:
			func = getattr(app, funcName, None)
			if func:
				yield func, (obj, self.next)

		# Tree interceptor level.
		treeInterceptor = obj.treeInterceptor
		if treeInterceptor:
			func = getattr(treeInterceptor, funcName, None)
			if func and (getattr(func, "ignoreIsReady", False) or treeInterceptor.isReady):
				yield func, (obj, self.next)

		# NVDAObject level.
		func = getattr(obj, funcName, None)
		if func:
			yield func, ()
'''

#: NVDA 2026.2, source/NVDAObjects/__init__.py, NVDAObject.event_nameChange, word for word.
NVDA_EVENT_NAME_CHANGE = '''
def event_nameChange(self):
	if self is api.getFocusObject():
		speech.speakObjectProperties(self, name=True, reason=controlTypes.OutputReason.CHANGE)
	braille.handler.handleUpdate(self)
	vision.handler.handleUpdate(self, property="name")
'''

#: NVDA 2026.2, source/appModules/outlook.py, UIAGridRow._get_name, word for word.
NVDA_GRID_ROW_NAME = '''
def _get_name(self):
	textList = []
	if controlTypes.State.EXPANDED in self.states:
		textList.append(controlTypes.State.EXPANDED.displayString)
	elif controlTypes.State.COLLAPSED in self.states:
		textList.append(controlTypes.State.COLLAPSED.displayString)
	selection = None
	if self.appModule.nativeOm:
		try:
			selection = self.appModule.nativeOm.activeExplorer().selection.item(1)
		except COMError:
			pass
	if selection:
		try:
			unread = selection.unread
		except COMError:
			unread = False
		# Translators: when an email is unread
		if unread:
			textList.append(_("unread"))
		try:
			mapiObject = selection.mapiObject
		except COMError:
			mapiObject = None
		if mapiObject:
			v = comtypes.automation.VARIANT()
			res = NVDAHelper.localLib.nvdaInProcUtils_outlook_getMAPIProp(
				self.appModule.helperLocalBindingHandle,
				self.windowThreadID,
				mapiObject,
				PR_LAST_VERB_EXECUTED,
				ctypes.byref(v),
			)
			if res == S_OK:
				verbLabel = executedVerbLabels.get(v.value, None)
				if verbLabel:
					textList.append(verbLabel)
		try:
			attachmentCount = selection.attachments.count
		except COMError:
			attachmentCount = 0
		# Translators: when an email has attachments
		if attachmentCount > 0:
			textList.append(_("has attachment"))
		try:
			importance = selection.importance
		except COMError:
			importance = 1
		importanceLabel = importanceLabels.get(importance)
		if importanceLabel:
			textList.append(importanceLabel)
		try:
			messageClass = selection.messageClass
		except COMError:
			messageClass = None
		if messageClass == "IPM.Schedule.Meeting.Request":
			# Translators: the email is a meeting request
			textList.append(_("meeting request"))
	childrenCacheRequest = UIAHandler.handler.baseCacheRequest.clone()
	childrenCacheRequest.addProperty(UIAHandler.UIA_NamePropertyId)
	childrenCacheRequest.addProperty(UIAHandler.UIA_TableItemColumnHeaderItemsPropertyId)
	childrenCacheRequest.TreeScope = UIAHandler.TreeScope_Children
	# We must filter the children for just text and image elements otherwise getCachedChildren fails completely in conversation view.
	childrenCacheRequest.treeFilter = createUIAMultiPropertyCondition(
		{
			UIAHandler.UIA_ControlTypePropertyId: [
				UIAHandler.UIA_TextControlTypeId,
				UIAHandler.UIA_ImageControlTypeId,
			],
		},
	)
	cachedChildren = self.UIAElement.buildUpdatedCache(childrenCacheRequest).getCachedChildren()
	if not cachedChildren:
		# There are no children
		# This is unexpected here.
		log.debugWarning("Unable to get relevant children for UIAGridRow", stack_info=True)
		return super(UIAGridRow, self).name
	for index in range(cachedChildren.length):
		e = cachedChildren.getElement(index)
		UIAControlType = e.cachedControlType
		UIAClassName = e.cachedClassName
		# We only want to include particular children.
		# We only include the flagField if the object model's flagIcon or flagStatus is set.
		# Stops us from reporting "unflagged" which is too verbose.
		if selection and UIAClassName == "FlagField":
			try:
				if not selection.flagIcon and not selection.flagStatus:
					continue
			except COMError:
				continue
		# the category field should only be reported if the objectModel's categories property actually contains a valid string.
		# Stops us from reporting "no categories" which is too verbose.
		elif selection and UIAClassName == "CategoryField":
			try:
				if not selection.categories:
					continue
			except COMError:
				continue
		# And we don't care about anything else that is not a text element.
		elif UIAControlType != UIAHandler.UIA_TextControlTypeId:
			continue
		name = e.cachedName
		columnHeaderTextList = []
		if name and config.conf["documentFormatting"]["reportTableHeaders"] in (
			ReportTableHeaders.ROWS_AND_COLUMNS,
			ReportTableHeaders.COLUMNS,
		):
			columnHeaderItems = e.getCachedPropertyValueEx(
				UIAHandler.UIA_TableItemColumnHeaderItemsPropertyId,
				True,
			)
		else:
			columnHeaderItems = None
		if columnHeaderItems:
			columnHeaderItems = columnHeaderItems.QueryInterface(UIAHandler.IUIAutomationElementArray)
			for index in range(columnHeaderItems.length):
				columnHeaderItem = columnHeaderItems.getElement(index)
				columnHeaderTextList.append(columnHeaderItem.currentName)
		columnHeaderText = " ".join(columnHeaderTextList)
		if columnHeaderText:
			text = "{header} {name}".format(header=columnHeaderText, name=name)
		else:
			text = name
		if text:
			if UIAClassName == "FlagField":
				textList.insert(0, text)
			else:
				text += ","
				textList.append(text)
	return " ".join(textList)
'''


def nvdaCode(source, name, namespace):
	"""Compile NVDA's own ``source`` against the imitation NVDA, and give back ``name`` from it."""
	scope = dict(namespace)
	exec(source, scope)
	return scope[name]


class OutputReason(enum.Enum):
	FOCUS = "focus"
	CHANGE = "change"


class State(enum.Enum):
	EXPANDED = "expanded"
	COLLAPSED = "collapsed"

	@property
	def displayString(self):
		return self.value


class ReportTableHeaders(enum.Enum):
	OFF = 0
	ROWS_AND_COLUMNS = 1
	ROWS = 2
	COLUMNS = 3


controlTypes = types.ModuleType("controlTypes")
controlTypes.OutputReason, controlTypes.State = OutputReason, State


class COMError(Exception):
	"""comtypes' COMError: what a call to Outlook or to UI Automation raises when it fails."""


#: UI Automation's ids, as NVDA's UIAHandler has them.
UIA_IDS = dict(
	UIA_NamePropertyId=30005,
	UIA_ControlTypePropertyId=30003,
	UIA_TableItemColumnHeaderItemsPropertyId=30121,
	UIA_TextControlTypeId=50020,
	UIA_ImageControlTypeId=50006,
	TreeScope_Children=2,
	IUIAutomationElementArray="IUIAutomationElementArray",
)


class CacheRequest:
	"""A UI Automation cache request, as NVDA's _get_name builds one."""

	TreeScope = None
	treeFilter = None

	def __init__(self):
		self.properties = []

	def clone(self):
		return CacheRequest()

	def addProperty(self, propertyId):
		self.properties.append(propertyId)


class Elements:
	"""An IUIAutomationElementArray."""

	def __init__(self, elements):
		self._elements = list(elements)

	@property
	def length(self):
		return len(self._elements)

	def getElement(self, index):
		return self._elements[index]

	def QueryInterface(self, interface):
		return self


class Header:
	def __init__(self, name):
		self.currentName = name


class Cell:
	"""A column of a message in Outlook's list: a text element, its value and its column's header."""

	cachedControlType = UIA_IDS["UIA_TextControlTypeId"]

	def __init__(self, header, name, className="TextField"):
		self.cachedName, self.cachedClassName, self._header = name, className, header

	def getCachedPropertyValueEx(self, propertyId, ignoreDefault):
		return Elements([Header(self._header)])


class Element:
	"""A message's row in Outlook's list, in UI Automation: its class and its columns."""

	def __init__(self, className, cells):
		self.cachedClassName, self._cells = className, cells

	def buildUpdatedCache(self, request):
		return self

	def getCachedChildren(self):
		return Elements(self._cells)


class Message:
	"""A message in Outlook's object model, as NVDA's _get_name asks it about its status."""

	mapiObject = None
	importance = 1
	messageClass = "IPM.Note"
	flagIcon = flagStatus = 0
	categories = ""

	def __init__(self, sender, subject, received, size, unread, rowClass="LeafRow"):
		self.unread = unread
		self.attachments = types.SimpleNamespace(count=0)
		self.cells = [Cell("From", sender), Cell("Subject", subject), Cell("Received", received), Cell("Size", size)]
		self.rowClass = rowClass


class Outlook:
	"""Classic Outlook: its object model's selection and UI Automation's focus, which move together."""

	appName = "outlook"

	def __init__(self):
		self.selected = None
		self.focused = None
		self.failing = False
		self.nativeOm = types.SimpleNamespace(activeExplorer=lambda: types.SimpleNamespace(selection=self))

	def item(self, index):
		return self.selected

	def select(self, row):
		self.selected, self.focused = row.message, row.UIAElement

	# UI Automation's client object, as UIAHandler.handler.clientObject.
	def GetFocusedElement(self):
		if self.failing:
			raise COMError(-2147220991, "An event was unable to invoke any of the subscribers")
		return self.focused

	def CompareElements(self, first, second):
		return first is second


class Row:
	"""NVDA's object for a message in Outlook's list (appModules.outlook.UIAGridRow): NVDA's name and nameChange."""

	windowThreadID = 1
	treeInterceptor = None

	def __init__(self, appModule, message, position):
		self.appModule, self.message, self.position = appModule, message, position
		self.UIAElement = Element(message.rowClass, message.cells)
		self.states = set()

	def __repr__(self):
		return f"<row {self.message.cells[0].cachedName}>"


class NVDA:
	"""The imitation NVDA: its focus, its speech and braille, and its event chain, with the assistant's plugin first."""

	def __init__(self, test):
		self.focus = None
		self.spoken = []
		self.braille = []
		self.plugin = object.__new__(jawsMigrator.GlobalPlugin)
		self.plugin._changeRepeats = None
		self.plugin._trayChanges = None
		self.plugin._outlookRows = outlookRows
		self.plugins = [self.plugin]
		self.executer = nvdaCode(
			NVDA_EVENT_EXECUTER,
			"_EventExecuter",
			{
				"garbageHandler": types.SimpleNamespace(TrackedObject=object),
				"globalPluginHandler": types.SimpleNamespace(runningPlugins=self.plugins),
				"log": nvdaStubs.logging.getLogger("nvda"),
				"extensionPoints": types.SimpleNamespace(callWithSupportedKwargs=lambda func, *args, **kwargs: func(*args)),
			},
		)

	def getFocusObject(self):
		return self.focus

	def speakObjectProperties(self, obj, reason=None, name=False, position=False):
		"""NVDA's speech.speakObjectProperties, as far as a name goes: it notes what it says for the object
		(_speakObjectPropertiesCache), and for a change says only what differs from what it noted
		(getObjectPropertiesSpeech)."""
		new = {"name": obj.name}
		old = dict(getattr(obj, "_speakObjectPropertiesCache", {}))
		obj._speakObjectPropertiesCache = {**old, **new}
		if reason == OutputReason.CHANGE and old.get("name") == new["name"]:
			return
		self.spoken.append(new["name"] if not position else f"{new['name']} {obj.position}")

	def gainFocus(self, row):
		"""NVDA's focus event for a message: the focus moves, and NVDA says it with its position."""
		self.focus = row
		self.speakObjectProperties(row, reason=OutputReason.FOCUS, name=True, position=True)
		self.braille.append(row)

	def event(self, name, obj):
		self.executer(name, obj, {})


def joshsReply(number=13, unread=False):
	subjects = {
		13: "Re: [joshknnd1982/jawsMigrator] This players name isn't being spoken correctly (Issue #13)",
		14: "Re: [joshknnd1982/jawsMigrator] There is an issue when you immediately go to github that Jaws doesn't say. (Issue #14)",
	}
	received = {13: "Sat 9/26/2026 7:34 AM", 14: "Sat 9/26/2026 7:33 AM"}
	return Message("joshknnd1982", subjects[number], received[number], "29 KB", unread)


def rtmNews():
	return Message("🔴 RTM News", "1 Billion Deaths: Insane Warning", "Sat 9/26/2026 8:38 AM", "51 KB", unread=True)


class LeftMessageTest(unittest.TestCase):
	def setUp(self):
		self.outlook = Outlook()
		self.nvda = NVDA(self)
		api = types.ModuleType("api")
		api.getFocusObject = self.nvda.getFocusObject
		uiaHandler = types.ModuleType("UIAHandler")
		uiaHandler.handler = types.SimpleNamespace(clientObject=self.outlook, baseCacheRequest=CacheRequest())
		for key, value in UIA_IDS.items():
			setattr(uiaHandler, key, value)
		patches = [
			mock.patch.dict(sys.modules, {"api": api, "UIAHandler": uiaHandler, "controlTypes": controlTypes}),
			mock.patch.object(outlookRows, "_failed", False),
			mock.patch.object(outlookRows, "_enabled", outlookRows._enabled),
		]
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)
		outlookRows.register()
		speech = types.SimpleNamespace(speakObjectProperties=self.nvda.speakObjectProperties)
		braille = types.SimpleNamespace(handler=types.SimpleNamespace(handleUpdate=self.nvda.braille.append))
		vision = types.SimpleNamespace(handler=types.SimpleNamespace(handleUpdate=lambda obj, property=None: None))
		Row.event_nameChange = nvdaCode(
			NVDA_EVENT_NAME_CHANGE,
			"event_nameChange",
			{"api": api, "speech": speech, "controlTypes": controlTypes, "braille": braille, "vision": vision},
		)
		config = types.SimpleNamespace(conf={"documentFormatting": {"reportTableHeaders": ReportTableHeaders.ROWS_AND_COLUMNS}})
		Row.name = property(
			nvdaCode(
				NVDA_GRID_ROW_NAME,
				"_get_name",
				{
					"controlTypes": controlTypes,
					"_": lambda text: text,
					"COMError": COMError,
					"comtypes": None,
					"NVDAHelper": None,
					"ctypes": None,
					"PR_LAST_VERB_EXECUTED": 0x10810003,
					"S_OK": 0,
					"executedVerbLabels": {},
					"importanceLabels": {0: "low importance", 2: "high importance"},
					"UIAHandler": uiaHandler,
					"createUIAMultiPropertyCondition": lambda conditions: conditions,
					"config": config,
					"ReportTableHeaders": ReportTableHeaders,
					"log": nvdaStubs.logging.getLogger("nvda"),
					"UIAGridRow": Row,
				},
			)
		)
		self.addCleanup(lambda: [delattr(Row, name) for name in ("event_nameChange", "name")])

	def row(self, message, position):
		return Row(self.outlook, message, position)

	def onMessage(self, row):
		"""The tester comes to ``row``: Outlook selects it and NVDA says it."""
		self.outlook.select(row)
		self.nvda.gainFocus(row)
		self.nvda.spoken.clear()
		self.nvda.braille.clear()

	def move(self, left, to):
		"""End or Down Arrow: Outlook selects ``to``, tells of a change of name of ``left``, then of the focus on ``to``."""
		self.outlook.select(to)
		self.nvda.event("nameChange", left)
		self.nvda.gainFocus(to)
		return list(self.nvda.spoken)

	def nvdaAlone(self, left, to):
		"""What NVDA 2026.2 says for the same move without the assistant."""
		self.nvda.plugins.clear()
		try:
			return self.move(left, to)
		finally:
			self.nvda.plugins.append(self.nvda.plugin)

	def test_end_said_the_message_left_as_unread_first(self):
		# 08:43:47: from Josh's reply, which the tester had read, to RTM News's message, which is unread.
		reply, newest = self.row(joshsReply(), "2621 of 2663"), self.row(rtmNews(), "2663 of 2663")
		self.onMessage(reply)
		self.assertEqual(
			self.nvdaAlone(reply, newest),
			[
				"unread From joshknnd1982, Subject Re: [joshknnd1982/jawsMigrator] This players name isn't being spoken correctly "
				"(Issue #13), Received Sat 9/26/2026 7:34 AM, Size 29 KB,",
				"unread From 🔴 RTM News, Subject 1 Billion Deaths: Insane Warning, Received Sat 9/26/2026 8:38 AM, Size 51 KB, "
				"2663 of 2663",
			],
			"NVDA 2026.2 says the message left, with the status of the one moved to, as in the tester's log",
		)

	def test_end_says_only_the_message_moved_to(self):
		reply, newest = self.row(joshsReply(), "2621 of 2663"), self.row(rtmNews(), "2663 of 2663")
		self.onMessage(reply)
		self.assertEqual(
			self.move(reply, newest),
			["unread From 🔴 RTM News, Subject 1 Billion Deaths: Insane Warning, Received Sat 9/26/2026 8:38 AM, Size 51 KB, 2663 of 2663"],
		)
		self.assertEqual(self.nvda.braille, [newest], "braille shows the message moved to, not the one left with a wrong status")

	def test_down_arrow_says_only_the_message_moved_to(self):
		# 08:29:19: Down Arrow from Josh's reply on issue 14, read, to Daily Caller's message, unread.
		reply = self.row(joshsReply(14), "2616 of 2658")
		dailyCaller = self.row(
			Message("Daily Caller", "Entertainment Update: Joe Jonas Recalls Plunging Into Terrifying Situation At Sea", "Sat 9/26/2026 7:35 AM", "74 KB", unread=True),
			"2617 of 2658",
		)
		self.onMessage(reply)
		self.assertEqual(len(self.nvdaAlone(reply, dailyCaller)), 2, "NVDA 2026.2 says both")
		self.onMessage(reply)
		spoken = self.move(reply, dailyCaller)
		self.assertEqual(len(spoken), 1, spoken)
		self.assertTrue(spoken[0].startswith("unread From Daily Caller"), spoken)

	def test_messages_with_the_same_status_were_said_once_already(self):
		# 09:03:39: End from the Astros message, unread, to Popular Science Shop's, unread: nothing differs, so NVDA
		# 2026.2 said only the message moved to. It says the same with the assistant.
		astros = self.row(Message("Houston Chronicle Sports", "Astros must regroup for final two games after ugly loss", "Sat 9/26/2026 8:30 AM", "80 KB", True), "2630 of 2640")
		shop = self.row(Message("Popular Science Shop", "Weekend Deals? Yes Please!!", "Sat 9/26/2026 9:01 AM", "130 KB", True), "2640 of 2640")
		self.onMessage(astros)
		self.assertEqual(len(self.nvdaAlone(astros, shop)), 1)
		self.onMessage(astros)
		self.assertEqual(len(self.move(astros, shop)), 1)

	def test_conversations_too(self):
		for rowClass in ("ThreadItem", "ThreadHeader"):
			with self.subTest(rowClass):
				left, to = joshsReply(), rtmNews()
				left.rowClass = to.rowClass = rowClass
				left, to = self.row(left, "1 of 2"), self.row(to, "2 of 2")
				self.onMessage(left)
				self.assertEqual(self.move(left, to), [mock.ANY], rowClass)

	def test_a_change_of_the_message_the_focus_is_on_is_said(self):
		# Outlook's focus is still on the message, and its status changed: Outlook marked it unread.
		reply = self.row(joshsReply(), "2621 of 2663")
		self.onMessage(reply)
		reply.message.unread = True
		self.nvda.event("nameChange", reply)
		self.assertEqual(self.nvda.spoken, [mock.ANY])
		self.assertTrue(self.nvda.spoken[0].startswith("unread From joshknnd1982"), self.nvda.spoken)

	def test_when_uia_cant_tell_nvda_says_it_and_it_is_logged_once(self):
		reply, newest = self.row(joshsReply(), "2621 of 2663"), self.row(rtmNews(), "2663 of 2663")
		self.onMessage(reply)
		self.outlook.failing = True
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.assertEqual(len(self.move(reply, newest)), 2)
			self.onMessage(reply)
			self.assertEqual(len(self.move(reply, newest)), 2)
		failures = [line for line in logged.output if "could not check whether Outlook's focus is still on a message" in line]
		self.assertEqual(len(failures), 1, logged.output)

	def test_other_programs_and_other_objects_go_on_to_nvda(self):
		reply = self.row(joshsReply(), "1 of 2")
		elsewhere = types.SimpleNamespace(appName="explorer")
		fileRow = Row(elsewhere, joshsReply(), "1 of 2")
		ribbon = self.row(joshsReply(), "1 of 2")
		ribbon.UIAElement.cachedClassName = "NetUIRibbonButton"
		noUia = types.SimpleNamespace(appModule=self.outlook)
		for obj in (fileRow, ribbon, noUia):
			with self.subTest(obj):
				self.nvda.focus = obj
				handled = []
				jawsMigrator.GlobalPlugin.event_nameChange(self.nvda.plugin, obj, lambda: handled.append(obj))
				self.assertEqual(handled, [obj])
		# A message NVDA's focus isn't on: NVDA says nothing for it, but braille follows it, as before.
		self.onMessage(self.row(rtmNews(), "2 of 2"))
		handled = []
		jawsMigrator.GlobalPlugin.event_nameChange(self.nvda.plugin, reply, lambda: handled.append(reply))
		self.assertEqual(handled, [reply])

	def test_turned_off_nvda_says_it_as_it_does(self):
		outlookRows.unregister()
		reply, newest = self.row(joshsReply(), "2621 of 2663"), self.row(rtmNews(), "2663 of 2663")
		self.onMessage(reply)
		self.assertEqual(len(self.move(reply, newest)), 2)
		self.assertFalse(outlookRows.leftBehind(reply))

	def test_before_the_settings_are_applied_nvda_says_it(self):
		self.nvda.plugin._outlookRows = None
		reply, newest = self.row(joshsReply(), "2621 of 2663"), self.row(rtmNews(), "2663 of 2663")
		self.onMessage(reply)
		self.assertEqual(len(self.move(reply, newest)), 2)

	def test_logged_for_the_debug_log(self):
		reply, newest = self.row(joshsReply(), "2621 of 2663"), self.row(rtmNews(), "2663 of 2663")
		self.onMessage(reply)
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.move(reply, newest)
		self.assertTrue(
			any("Outlook's focus has left the message \"From joshknnd1982, Subject Re:" in line for line in logged.output),
			logged.output,
		)


class SettingTest(unittest.TestCase):
	def test_on_unless_turned_off(self):
		self.assertTrue(outlookRows.wanted({}))
		self.assertTrue(outlookRows.wanted(dict(state.DEFAULTS)))
		self.assertFalse(outlookRows.wanted({outlookRows.STATE_KEY: False}))
		self.assertFalse(outlookRows.wanted(None))
		self.assertIs(state.DEFAULTS[outlookRows.STATE_KEY], True)

	def test_register_and_unregister(self):
		with mock.patch.object(outlookRows, "_enabled", False):
			outlookRows.register()
			self.assertTrue(outlookRows.isRegistered())
			outlookRows.unregister()
			self.assertFalse(outlookRows.isRegistered())


if __name__ == "__main__":
	unittest.main()
