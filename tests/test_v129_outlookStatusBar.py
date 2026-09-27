# Unit tests for version 1.29, from a tester's report (issue 26): "When in outlook in the inbox or a sub-folder when I
# press insert page down." JAWS said "Items in View 2,675", "Unread Items in View 1,135" and "Zoom 10%", a line each.
# NVDA said "Status Bar Items in View 2,675 Unread Items in View 1,135 Normal View. Show All Pinned Panes. Reading View.
# Hide All Pinned Panes. Zoom Out 10 Zoom 10 Zoom In 10 Zoom 10%".
# Insert+Page Down is JAWS's "Say Bottom Line of Window" (Default.JKM), which the migration gives NVDA's "Report status
# bar" (jawsKeyMap, saybottomlineofwindow). NVDA 2026.2 reads a status bar as its name, then the name and value of each
# thing in it (api.getStatusBarText), as NVDA's support for Outlook doesn't read it its own way
# (AppModule.getStatusBarText). JAWS 2026 reads it with its script for Outlook (Outlook.jss, SayBottomLineOfWindow and
# GetStatusBarWindowInfo): the name of each item of the status bar whose UI Automation class is "NetUISimpleButton"
# (Outlook.jsh, objn_NetUISimpleButton), a line each, and nothing else.
# - outlookStatusBar: in Outlook, NVDA's api.getStatusBarText gives those names, with ", " between them, as NVDA's
#   File Explorer support gives the parts of its status bar. Twice spells it and three times copies it, as before.
# The imitation NVDA runs NVDA 2026.2's own api.getStatusBar and getStatusBarText, GlobalCommands._getStatusBarText,
# script_readStatusLine, script_spellStatusLine, script_copyStatusLine and script_reportStatusLine, AppModule's
# _get_statusBar, getStatusBarText and _get_statusBarTextInfo, UIA's children, name, value and cached properties,
# Window.correctAPIForRelation, utils.security.objectBelowLockScreenAndWindowsIsLocked, and baseObject's
# AutoPropertyObject (from test_v128_startupFocus), word for word. Outlook's status bar is imitated from what the
# tester heard: the three items JAWS said are NetUISimpleButton items; what kind of control each of the others is
# isn't known, only that JAWS left it out. The zoom slider and its two buttons give NVDA the zoom as their value
# (UI Automation's RangeValue, 10), which NVDA said after each. JAWS's rule is imitated from its script. The
# assistant's code is the real one.
# Run: python -m unittest tests.test_v129_outlookStatusBar -v

import abc
import enum
import functools
import os
import sys
import textwrap
import types
import typing
import unittest
import weakref
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v128_startupFocus as v128  # noqa: E402  (NVDA's baseObject, nvdaCode and nvdaClass)
from jawsMigrator import jawsKeyMap, outlookStatusBar, state  # noqa: E402

# -- NVDA 2026.2's own code -----------------------------------------------------------------------------------------

#: NVDA 2026.2, source/api.py: getStatusBar and getStatusBarText, word for word.
NVDA_API = r'''
def getStatusBar() -> Optional[NVDAObjects.NVDAObject]:
	"""Obtain the status bar for the current foreground object.
	@return: The status bar object or C{None} if no status bar was found.
	"""
	foreground = getForegroundObject()
	try:
		return foreground.appModule.statusBar
	except NotImplementedError:
		pass
	# The status bar is usually at the bottom of the screen.
	# Therefore, get the object at the bottom left of the foreground object using screen coordinates.
	location = foreground.location
	if not location:
		return None
	left, top, width, height = location
	bottom = top + height - 1
	obj = getDesktopObject().objectFromPoint(left, bottom)

	# We may have landed in a child of the status bar, so search the ancestry for a status bar.
	while obj and not obj.role == controlTypes.Role.STATUSBAR:
		obj = obj.parent

	return obj


def getStatusBarText(obj):
	"""Get the text from a status bar.
	This includes the name of the status bar and the names and values of all of its children.
	@param obj: The status bar.
	@type obj: L{NVDAObjects.NVDAObject}
	@return: The status bar text.
	@rtype: str
	"""
	try:
		return obj.appModule.getStatusBarText(obj)
	except NotImplementedError:
		pass
	text = obj.name or ""
	if text:
		text += " "
	return text + " ".join(
		chunk
		for child in obj.children
		for chunk in (child.name, child.value)
		if chunk and isinstance(chunk, str) and not chunk.isspace()
	)
'''

#: NVDA 2026.2, source/globalCommands.py, class GlobalCommands: its status bar commands, word for word (without the
#: @script decorators, which only give them their descriptions and gestures).
NVDA_GLOBAL_COMMANDS = r'''
@staticmethod
def _getStatusBarText(setReviewCursor: bool = False) -> Optional[str]:
	"""Returns text of the current status bar and optionally sets review cursor to it.
	If no status bar has been found `None` is returned and this fact is announced in speech and braille.
	"""
	obj = api.getStatusBar()
	found = False
	if (
		obj
		# This script is available on the lock screen via getSafeScripts, as such
		# ensure the status bar does not contain secure information
		# before announcing this object
		and not objectBelowLockScreenAndWindowsIsLocked(obj)
	):
		text = api.getStatusBarText(obj)
		if setReviewCursor:
			if not api.setNavigatorObject(obj):
				return None
		found = True
	else:
		foreground = api.getForegroundObject()
		try:
			info = foreground.appModule.statusBarTextInfo
		except NotImplementedError:
			info = foreground.flatReviewPosition
			if info:
				info.expand(textInfos.UNIT_STORY)
				info.collapse(True)
				info.expand(textInfos.UNIT_LINE)
		if (
			info
			# This script is available on the lock screen via getSafeScripts, as such
			# ensure the status bar does not contain secure information
			# before announcing this object
			and not objectBelowLockScreenAndWindowsIsLocked(info.obj)
		):
			text = info.text
			info.collapse()
			if setReviewCursor:
				api.setReviewPosition(info)
			found = True
	if not found:
		# Translators: Reported when there is no status line for the current program or window.
		ui.message(_("No status line found"))
		return None
	# Ensure any text comes from objects that have been
	# checked with objectBelowLockScreenAndWindowsIsLocked
	return text


def script_readStatusLine(self, gesture):
	text = self._getStatusBarText()
	if text is None:
		return
	if not text.strip():
		# Translators: Reported when status line exist, but is empty.
		ui.message(_("no status bar information"))
	else:
		ui.message(text)


def script_spellStatusLine(self, gesture):
	text = self._getStatusBarText()
	if text is None:
		return
	if not text.strip():
		# Translators: Reported when status line exist, but is empty.
		ui.message(_("no status bar information"))
	else:
		speech.speakSpelling(text)


def script_copyStatusLine(self, gesture):
	text = self._getStatusBarText()
	if text is None:
		return
	if not text.strip():
		# Translators: Reported when user attempts to copy content of the empty status line.
		ui.message(_("Unable to copy status bar content to clipboard"))
	else:
		api.copyToClip(text, notify=True)


def script_reportStatusLine(self, gesture):
	text = self._getStatusBarText()
	if text is None:
		return
	repeats = getLastScriptRepeatCount()
	if repeats == 0:
		self.script_readStatusLine(gesture)
	elif repeats == 1:
		self.script_spellStatusLine(gesture)
	else:
		self.script_copyStatusLine(gesture)
'''

#: NVDA 2026.2, source/appModuleHandler.py, class AppModule: how an app module can read its status bar its own way.
NVDA_APP_MODULE = r'''
def _get_statusBar(self):
	"""Retrieve the status bar object of the application.
	If C{NotImplementedError} is raised, L{api.getStatusBar} will resort to
	perform a lookup by position.
	If C{None} is returned, L{GlobalCommands.script_reportStatusLine} will
	in turn resort to reading the bottom line of text written to the
	display.
	@rtype: NVDAObject
	"""
	raise NotImplementedError()


def getStatusBarText(self, obj: NVDAObjects.NVDAObject) -> str:
	"""Get the text from the given status bar.
	If C{NotImplementedError} is raised, L{api.getStatusBarText} will resort to
	retrieve the name of the status bar and the names and values of all of its children.
	"""
	raise NotImplementedError()


def _get_statusBarTextInfo(self):
	"""Retrieve a L{TextInfo} positioned at the status bar of the application.
	This is used by L{GlobalCommands.script_reportStatusLine} in cases where
	L{api.getStatusBar} could not locate a proper L{NVDAObject} for the
	status bar.
	For this method to get called, L{_get_statusBar} must return C{None}.
	@rtype: TextInfo
	"""
	raise NotImplementedError()
'''

#: NVDA 2026.2, source/NVDAObjects/UIA/__init__.py, class UIA: a UI Automation object's children, name and value.
NVDA_UIA_METHODS = r'''
def _get__coreCycleUIAPropertyCacheElementCache(self):
	"""
	A dictionary per core cycle that is ready to map UIA property IDs to UIAElements with that property already cached.
	An example of where multiple cache elements may exist would be where the UIA NVDAObject was instantiated with a UIA element already containing a UI Automation cache (appropriate for generating control fields) but another UIA NVDAObject property (E.g. states) has a set of UIA properties of its own which should be bulk-fetched, and did not exist in the original cache.
	"""
	return {}


def _getUIACacheablePropertyValue(self, ID, ignoreDefault=False):
	"""
	Fetches the value for a UI Automation property from an element cache available in this core cycle. If not cached then a new value will be fetched.
	"""
	elementCache = self._coreCycleUIAPropertyCacheElementCache
	# If we have a UIAElement whos own cache contains the property, fetch the value from there
	cacheElement = elementCache.get(ID, None)
	if cacheElement:
		value = cacheElement.getCachedPropertyValueEx(ID, ignoreDefault)
	else:
		# The value is cached nowhere, so ask the UIAElement for its current value for the property
		value = self.UIAElement.getCurrentPropertyValueEx(ID, ignoreDefault)
	return value


def _get_UIAValue(self) -> typing.Optional[str]:
	val = self._getUIACacheablePropertyValue(UIAHandler.UIA.UIA_ValueValuePropertyId, True)
	if val != UIAHandler.handler.reservedNotSupportedValue:
		return val
	return None


def _get_UIARangeValue(self) -> typing.Optional[float]:
	val = self._getUIACacheablePropertyValue(UIAHandler.UIA.UIA_RangeValueValuePropertyId, True)
	if val != UIAHandler.handler.reservedNotSupportedValue:
		return val
	return None


def _get_value(self) -> typing.Optional[str]:
	if self.UIAValue is not None:
		return self.UIAValue
	if self.UIARangeValue is not None:
		return f"{round(self.UIARangeValue)}"
	return None


def correctAPIForRelation(self, obj, relation=None):
	if obj and self.windowHandle != obj.windowHandle and not obj.UIAElement.cachedNativeWindowHandle:
		# The target element is not the root element for the window, so don't change API class; i.e. always use UIA.
		return obj
	return super(UIA, self).correctAPIForRelation(obj, relation)


def _get_UIAChildren(self):
	childrenCacheRequest = UIAHandler.handler.baseCacheRequest.clone()
	childrenCacheRequest.TreeScope = UIAHandler.TreeScope_Children
	try:
		return self.UIAElement.buildUpdatedCache(childrenCacheRequest).getCachedChildren()
	except COMError as e:
		log.debugWarning("Could not fetch cached children from UIA element: %s" % e)
		raise e


def _get_children(self):
	try:
		cachedChildren = self.UIAChildren
		children = []
		if not cachedChildren:
			# GetCachedChildren returns null if there are no children.
			return children
		for index in range(cachedChildren.length):
			e = cachedChildren.getElement(index)
			windowHandle = self.windowHandle
			children.append(self.correctAPIForRelation(UIA(windowHandle=windowHandle, UIAElement=e)))
		return children
	except COMError:
		return super().children


def _get_childCount(self):
	try:
		cachedChildren = self.UIAChildren
		if not cachedChildren:
			# GetCachedChildren returns null if there are no children.
			return 0
		return cachedChildren.length
	except COMError:
		return len(super().children)


def _get_name(self) -> str:
	try:
		return self._getUIACacheablePropertyValue(UIAHandler.UIA_NamePropertyId)
	except COMError:
		return ""
'''

#: NVDA 2026.2, source/NVDAObjects/window/__init__.py, class Window.
NVDA_WINDOW_METHODS = r'''
def correctAPIForRelation(self, obj, relation=None):
	if not obj:
		return None
	newWindowHandle = obj.windowHandle
	oldWindowHandle = self.windowHandle
	if newWindowHandle and oldWindowHandle and newWindowHandle != oldWindowHandle:
		kwargs = dict(windowHandle=newWindowHandle)
		newAPIClass = Window.findBestAPIClass(kwargs, relation=relation)
		oldAPIClass = self.APIClass
		if newAPIClass and newAPIClass != oldAPIClass:
			return newAPIClass(chooseBestAPI=False, **kwargs)
	return obj
'''

#: NVDA 2026.2, source/utils/security.py.
NVDA_SECURITY = r'''
def objectBelowLockScreenAndWindowsIsLocked(
	obj: "NVDAObjects.NVDAObject",
	shouldLog: bool = True,
) -> bool:
	"""
	While Windows is locked, the current user session is still running, and below the lock screen
	exists the current user's desktop.

	Windows 10 and 11 doesn't prevent object navigation below the lock screen.

	If an object is above the lock screen, it is accessible and visible to the user
	through the Windows UX while Windows is locked.
	An object below the lock screen should only be accessible when Windows is unlocked,
	as it may contain sensitive information.

	As such, NVDA must prevent accessing and reading objects below the lock screen when Windows is locked.
	@return: C{True} if the Windows 10/11 lockscreen is active and C{obj} is below the lock screen.
	"""
	try:
		isObjectBelowLockScreen = isLockScreenModeActive() and obj.isBelowLockScreen
	except Exception:
		log.exception()
		return False

	if isObjectBelowLockScreen:
		if shouldLog and log.isEnabledFor(log.DEBUG):
			devInfo = "\n".join(obj.devInfo)
			log.debug(f"Attempt at navigating to an object below the lock screen: {devInfo}")
		return True

	return False
'''

NVDA_CODE_FILES = {
	"NVDA_API": "api.py",
	"NVDA_GLOBAL_COMMANDS": "globalCommands.py",
	"NVDA_APP_MODULE": "appModuleHandler.py",
	"NVDA_UIA_METHODS": "NVDAObjects/UIA/__init__.py",
	"NVDA_WINDOW_METHODS": "NVDAObjects/window/__init__.py",
	"NVDA_SECURITY": "utils/security.py",
}

# -- what the tester heard ------------------------------------------------------------------------------------------

#: What NVDA said at Insert+Page Down in the tester's Inbox.
NVDA_SAID = (
	"Status Bar Items in View 2,675 Unread Items in View 1,135 Normal View. Show All Pinned Panes. Reading View. "
	"Hide All Pinned Panes. Zoom Out 10 Zoom 10 Zoom In 10 Zoom 10%"
)
#: What JAWS said there, a line each.
JAWS_SAID = ["Items in View 2,675", "Unread Items in View 1,135", "Zoom 10%"]

# -- the imitation NVDA --------------------------------------------------------------------------------------------

nvdaLog = nvdaStubs.logging.getLogger("nvda")

UIA_NamePropertyId, UIA_ClassNamePropertyId, UIA_ValueValuePropertyId, UIA_RangeValueValuePropertyId = 30005, 30012, 30045, 30047
UIA_ButtonControlTypeId, UIA_SliderControlTypeId, UIA_StatusBarControlTypeId, UIA_PaneControlTypeId = 50000, 50015, 50017, 50033
TreeScope_Element, TreeScope_Children = 1, 2
#: UI Automation's ReservedNotSupportedValue: what an element gives for a property it doesn't have.
NOT_SUPPORTED = object()
#: The class JAWS reads in Outlook's status bar.
SIMPLE = "NetUISimpleButton"
#: The class of an item JAWS left out: not known, only that it isn't NetUISimpleButton.
OTHER = "not NetUISimpleButton"
OUTLOOK, NOTEPAD = 0x10010, 0x20020


class Role(enum.IntEnum):
	UNKNOWN = 0
	BUTTON = 9
	PANE = 13
	STATUSBAR = 23
	SLIDER = 50


ROLES = {
	UIA_ButtonControlTypeId: Role.BUTTON,
	UIA_SliderControlTypeId: Role.SLIDER,
	UIA_StatusBarControlTypeId: Role.STATUSBAR,
	UIA_PaneControlTypeId: Role.PANE,
}


class COMError(Exception):
	pass


class CacheRequest:
	"""UI Automation's cache request, as far as NVDA's children go."""

	TreeScope = TreeScope_Element

	def clone(self):
		return CacheRequest()


class ElementArray:
	def __init__(self, elements):
		self.elements = elements
		self.length = len(elements)

	def getElement(self, index):
		return self.elements[index]


class Element:
	"""An imitation IUIAutomationElement in Office's status bar, with the properties NVDA and JAWS read."""

	def __init__(self, name, className="", controlType=UIA_ButtonControlTypeId, value=NOT_SUPPORTED, rangeValue=NOT_SUPPORTED, children=()):
		self.cachedName, self.cachedClassName, self.cachedControlType = name, className, controlType
		self.cachedNativeWindowHandle = 0
		self.properties = {
			UIA_NamePropertyId: name,
			UIA_ClassNamePropertyId: className,
			UIA_ValueValuePropertyId: value,
			UIA_RangeValueValuePropertyId: rangeValue,
		}
		self.children = list(children)
		self.parent = None
		for child in self.children:
			child.parent = self

	def getCurrentPropertyValueEx(self, ID, ignoreDefault):
		return self.properties[ID]

	getCachedPropertyValueEx = getCurrentPropertyValueEx

	def buildUpdatedCache(self, cacheRequest):
		assert cacheRequest.TreeScope == TreeScope_Children, "NVDA asks for the children"
		return types.SimpleNamespace(getCachedChildren=lambda: ElementArray(self.children) if self.children else None)


def statusBar(*items, name="Status Bar"):
	"""A status bar of Office's UI Automation, with its items, in Outlook's bottom dock (Outlook.jss, MsoDockBottom)."""
	bar = Element(name, controlType=UIA_StatusBarControlTypeId, children=items)
	Element("MsoDockBottom", controlType=UIA_PaneControlTypeId, children=[bar])
	return bar


def testersStatusBar(*more):
	"""The status bar of the tester's Inbox, as NVDA read it, in its order."""
	return statusBar(
		Element("Items in View 2,675", SIMPLE),
		Element("Unread Items in View 1,135", SIMPLE),
		*more,
		Element("Normal View. Show All Pinned Panes.", OTHER),
		Element("Reading View. Hide All Pinned Panes.", OTHER),
		Element("Zoom Out", OTHER, rangeValue=10.0),
		Element("Zoom", OTHER, controlType=UIA_SliderControlTypeId, rangeValue=10.0),
		Element("Zoom In", OTHER, rangeValue=10.0),
		Element("Zoom 10%", SIMPLE),
	)


def jawsReads(bar):
	"""JAWS 2026's Outlook.jss, GetStatusBarWindowInfo, imitated: the status bar's children whose class is
	objn_NetUISimpleButton, their names a line each (cscBufferNewLine before each), the first line break chopped off."""
	text = ""
	for item in bar.children:
		if item.cachedClassName == SIMPLE:
			text = text + "\n" + item.cachedName
	return text[1:]


#: The imitation's NVDAObject, Window and UIA: NVDA's own methods, and the imitation's for the rest.
IMITATION_NVDA_OBJECT = '''
def _get_children(self):
	return []
'''

IMITATION_WINDOW = '''
#: The app module of each window, as NVDA finds it from the window's process.
appModules = {}

def __init__(self, windowHandle=None):
	super().__init__()
	self.windowHandle = windowHandle

def _get_appModule(self):
	return self.appModules[self.windowHandle]
'''

IMITATION_UIA = '''
def __init__(self, windowHandle=None, UIAElement=None):
	super().__init__(windowHandle=windowHandle)
	self.UIAElement = UIAElement

def _get_role(self):
	return ROLES.get(self.UIAElement.cachedControlType, controlTypes.Role.UNKNOWN)

def _get_parent(self):
	parent = self.UIAElement.parent
	return UIA(windowHandle=self.windowHandle, UIAElement=parent) if parent is not None else None
'''

IMITATION_APP_MODULE = '''
def __init__(self, appName):
	super().__init__()
	self.appName = appName
'''


class Nvda:
	"""The imitation NVDA, with a program in front whose status bar is ``bar``."""

	def __init__(self, bar, appName="outlook", appModuleMethods=None, foreground=OUTLOOK):
		self.spoken, self.spelled, self.copied, self.navigator = [], [], [], []
		self.repeats = 0
		base = {
			"garbageHandler": types.SimpleNamespace(TrackedObject=object),
			"log": nvdaLog,
			"weakref": weakref,
			"ABCMeta": abc.ABCMeta,
			"abstractproperty": abc.abstractproperty,
		}
		AutoPropertyObject = v128.nvdaCode(v128.NVDA_BASE_OBJECT, "AutoPropertyObject", base)
		controlTypes = types.SimpleNamespace(Role=Role)
		uiaHandler = types.SimpleNamespace(
			handler=types.SimpleNamespace(baseCacheRequest=CacheRequest(), reservedNotSupportedValue=NOT_SUPPORTED),
			TreeScope_Children=TreeScope_Children,
			UIA_NamePropertyId=UIA_NamePropertyId,
			UIA=types.SimpleNamespace(UIA_ValueValuePropertyId=UIA_ValueValuePropertyId, UIA_RangeValueValuePropertyId=UIA_RangeValueValuePropertyId),
		)
		objects = dict(base, AutoPropertyObject=AutoPropertyObject, UIAHandler=uiaHandler, COMError=COMError, controlTypes=controlTypes, typing=typing, ROLES=ROLES)
		v128.nvdaClass("class NVDAObject(AutoPropertyObject)", [IMITATION_NVDA_OBJECT], objects)
		self.Window = v128.nvdaClass("class Window(NVDAObject)", [IMITATION_WINDOW, NVDA_WINDOW_METHODS], objects)
		self.UIA = v128.nvdaClass("class UIA(Window)", [IMITATION_UIA, NVDA_UIA_METHODS], objects)

		# NVDA's app modules: NVDA's own AppModule, and its support for Outlook, which reads no status bar its own way.
		self.appModuleHandler = types.ModuleType("appModuleHandler")
		AppModule = v128.nvdaClass("class AppModule(AutoPropertyObject)", [IMITATION_APP_MODULE, NVDA_APP_MODULE], dict(base, AutoPropertyObject=AutoPropertyObject))
		self.appModuleHandler.AppModule = AppModule
		# The program's app module: NVDA's support for it, or another add-on's in its place, with ``appModuleMethods``.
		self.appModule = type("AppModule", (AppModule,), dict(appModuleMethods or {}))(appName)
		self.Window.appModules[foreground] = self.appModule
		self.bar = bar

		# The program's window in front; at its bottom left corner, the status bar's first item.
		foregroundObject = types.SimpleNamespace(appModule=self.appModule, location=(0, 0, 1280, 1024))

		def objectFromPoint(x, y):
			assert (x, y) == (0, 1023), "NVDA looks at the window's bottom left corner"
			return self.UIA(windowHandle=foreground, UIAElement=bar.children[0]) if bar is not None else None

		self.api = types.ModuleType("api")
		self.api.getForegroundObject = lambda: foregroundObject
		self.api.getDesktopObject = lambda: types.SimpleNamespace(objectFromPoint=objectFromPoint)
		self.api.controlTypes = controlTypes
		self.api.setNavigatorObject = lambda obj: self.navigator.append(obj) or True
		self.api.copyToClip = lambda text, notify=False: self.copied.append(text) or True
		v128.nvdaCode(NVDA_API, "getStatusBarText", vars(self.api))
		self.nvdasGetStatusBarText = self.api.getStatusBarText

		security = {"log": nvdaLog, "isLockScreenModeActive": lambda: False}
		commands = {
			"api": self.api,
			"ui": types.SimpleNamespace(message=self.spoken.append),
			"speech": types.SimpleNamespace(speakSpelling=self.spelled.append),
			"getLastScriptRepeatCount": lambda: self.repeats,
			"objectBelowLockScreenAndWindowsIsLocked": v128.nvdaCode(NVDA_SECURITY, "objectBelowLockScreenAndWindowsIsLocked", security),
			"textInfos": types.SimpleNamespace(UNIT_STORY="story", UNIT_LINE="line"),
			"_": lambda text: text,
		}
		self.GlobalCommands = v128.nvdaClass("class GlobalCommands", [NVDA_GLOBAL_COMMANDS], commands)

	def modules(self):
		"""The imitation's api and appModuleHandler, as the assistant imports them."""
		return mock.patch.dict(sys.modules, {"api": self.api, "appModuleHandler": self.appModuleHandler})

	def press(self, times=1):
		"""Insert+Page Down, NVDA's "Report status bar", pressed ``times`` times in a row."""
		commands = self.GlobalCommands()
		for count in range(times):
			self.repeats = count
			commands.script_reportStatusLine(None)


class StatusBarTests(unittest.TestCase):
	def setUp(self):
		self.addCleanup(self._reset)

	def _reset(self):
		outlookStatusBar.unregister()
		outlookStatusBar._failed = False

	def nvda(self, bar, register=True, **kwargs):
		nvda = Nvda(bar, **kwargs)
		patcher = nvda.modules()
		patcher.start()
		self.addCleanup(patcher.stop)
		if register:
			outlookStatusBar.register()
			self.assertTrue(outlookStatusBar.isRegistered())
		return nvda

	def test_theImitationIsTheTestersStatusBar(self):
		# NVDA's own code says what the tester heard from NVDA, and JAWS's rule what he heard from JAWS.
		bar = testersStatusBar()
		self.assertEqual(jawsReads(bar).split("\n"), JAWS_SAID)
		nvda = self.nvda(bar, register=False)
		nvda.press()
		self.assertEqual(nvda.spoken, [NVDA_SAID])

	def test_insertPageDownIsNvdasReportStatusBar(self):
		self.assertEqual(jawsKeyMap.SCRIPT_MAP["saybottomlineofwindow"][:3], ("globalCommands", "GlobalCommands", "reportStatusLine"))

	def test_asJawsSaysIt(self):
		nvda = self.nvda(testersStatusBar())
		nvda.press()
		self.assertEqual(nvda.spoken, ["Items in View 2,675, Unread Items in View 1,135, Zoom 10%"])
		self.assertEqual(nvda.spoken, [outlookStatusBar.SEPARATOR.join(JAWS_SAID)])
		self.assertIs(nvda.api.getStatusBarText.__wrapped__, nvda.nvdasGetStatusBarText, "NVDA's own is kept, wrapped")

	def test_pressedTwiceSpellsIt(self):
		nvda = self.nvda(testersStatusBar())
		nvda.press(2)
		self.assertEqual(nvda.spelled, ["Items in View 2,675, Unread Items in View 1,135, Zoom 10%"])

	def test_threeTimesCopiesIt(self):
		nvda = self.nvda(testersStatusBar())
		nvda.press(3)
		self.assertEqual(nvda.copied, ["Items in View 2,675, Unread Items in View 1,135, Zoom 10%"])

	def test_moreItemsAreReadAsJawsReadsThem(self):
		# Outlook shows more such items at times, a filter or the connection; JAWS reads each one.
		bar = testersStatusBar(Element("Filter Applied", SIMPLE))
		nvda = self.nvda(bar)
		nvda.press()
		self.assertEqual(nvda.spoken, [outlookStatusBar.SEPARATOR.join(jawsReads(bar).split("\n"))])
		self.assertIn("Filter Applied", nvda.spoken[0])

	def test_anItemWithoutAName(self):
		# JAWS says nothing for an item without a name (an empty line), nor does NVDA now.
		bar = testersStatusBar(Element("", SIMPLE), Element("   ", SIMPLE))
		nvda = self.nvda(bar)
		nvda.press()
		self.assertEqual(nvda.spoken, ["Items in View 2,675, Unread Items in View 1,135, Zoom 10%"])

	def test_withoutSuchItemsNvdaReadsItAsItDoes(self):
		# JAWS reads the bottom line of the window then (its own SayBottomLineOfWindow), and NVDA its status bar.
		bar = statusBar(Element("Zoom Out", OTHER, rangeValue=100.0), Element("Zoom", OTHER, controlType=UIA_SliderControlTypeId, rangeValue=100.0))
		nvda = self.nvda(bar)
		nvda.press()
		self.assertEqual(nvda.spoken, ["Status Bar Zoom Out 100 Zoom 100"])

	def test_otherProgramsAreUnchanged(self):
		bar = statusBar(Element("Ln 1, Col 1", SIMPLE), Element("100%", OTHER))
		nvda = self.nvda(bar, appName="notepad", foreground=NOTEPAD)
		nvda.press()
		self.assertEqual(nvda.spoken, ["Status Bar Ln 1, Col 1 100%"])

	def test_anAppModuleThatReadsItsOwn(self):
		# Another add-on's app module for Outlook that reads the status bar its own way keeps its way.
		def getStatusBarText(self, obj):
			return "its own"

		nvda = self.nvda(testersStatusBar(), appModuleMethods={"getStatusBarText": getStatusBarText})
		nvda.press()
		self.assertEqual(nvda.spoken, ["its own"])

	def test_anotherAddonsAppModuleForOutlook(self):
		# Outlook Extended, which the tester has, puts its own app module over NVDA's; it reads no status bar.
		nvda = self.nvda(testersStatusBar(), appModuleMethods={"script_addressField": lambda self, gesture: None})
		nvda.press()
		self.assertEqual(nvda.spoken, ["Items in View 2,675, Unread Items in View 1,135, Zoom 10%"])

	def test_notThroughUIAutomation(self):
		# An Office older than 2016 is read through IAccessible there (UIAHandler, NetUIHWND): NVDA reads it as it does.
		nvda = self.nvda(None)
		bar = types.SimpleNamespace(
			name="Status Bar",
			appModule=nvda.appModule,
			children=[types.SimpleNamespace(name="Items in View 2,675", value=None), types.SimpleNamespace(name="Zoom", value="10")],
		)
		self.assertEqual(nvda.api.getStatusBarText(bar), "Status Bar Items in View 2,675 Zoom 10")

	def test_noStatusBar(self):
		nvda = self.nvda(statusBar())
		nvda.api.getDesktopObject = lambda: types.SimpleNamespace(objectFromPoint=lambda x, y: None)
		nvda.api.getForegroundObject().appModule.__class__.statusBarTextInfo = property(lambda self: None)
		nvda.press()
		self.assertEqual(nvda.spoken, ["No status line found"])

	def test_aFailureLeavesNvdasOwn(self):
		nvda = self.nvda(testersStatusBar())
		with mock.patch.object(outlookStatusBar, "jawsText", side_effect=RuntimeError("broken for the test")):
			nvda.press()
		self.assertEqual(nvda.spoken, [NVDA_SAID])
		self.assertTrue(outlookStatusBar._failed)

	def test_turnedOff(self):
		nvda = self.nvda(testersStatusBar())
		outlookStatusBar.unregister()
		self.assertIs(nvda.api.getStatusBarText, nvda.nvdasGetStatusBarText, "NVDA's own is back")
		nvda.press()
		self.assertEqual(nvda.spoken, [NVDA_SAID])
		outlookStatusBar.register()
		nvda.press()
		self.assertEqual(nvda.spoken[-1], "Items in View 2,675, Unread Items in View 1,135, Zoom 10%")

	def test_anotherAddonsWrapperOverIt(self):
		nvda = self.nvda(testersStatusBar())
		ours = nvda.api.getStatusBarText

		@functools.wraps(ours)
		def theirs(obj):
			return ours(obj)

		nvda.api.getStatusBarText = theirs
		outlookStatusBar.unregister()
		self.assertIs(nvda.api.getStatusBarText, theirs, "the other add-on's stays")
		nvda.press()
		self.assertEqual(nvda.spoken, [NVDA_SAID], "the assistant's passes NVDA's on")
		outlookStatusBar.register()
		self.assertIs(nvda.api.getStatusBarText, theirs, "not wrapped a second time")
		nvda.press()
		self.assertEqual(nvda.spoken[-1], "Items in View 2,675, Unread Items in View 1,135, Zoom 10%")

	def test_registeredOnce(self):
		nvda = self.nvda(testersStatusBar())
		installed = nvda.api.getStatusBarText
		outlookStatusBar.register()
		self.assertIs(nvda.api.getStatusBarText, installed)

	def test_withoutNvdasFunction(self):
		nvda = Nvda(testersStatusBar())
		del nvda.api.getStatusBarText
		with nvda.modules():
			outlookStatusBar.register()
		self.assertFalse(outlookStatusBar.isRegistered())

	def test_onUnlessTurnedOff(self):
		self.assertIs(state.DEFAULTS[outlookStatusBar.STATE_KEY], True)
		self.assertTrue(outlookStatusBar.wanted(dict(state.DEFAULTS)))
		self.assertTrue(outlookStatusBar.wanted({}))
		self.assertFalse(outlookStatusBar.wanted({outlookStatusBar.STATE_KEY: False}))


class NvdasOwnCodeTests(unittest.TestCase):
	def test_theCodeIsNvdas(self):
		# Each piece is in NVDA 2026.2's source, at the margin or as a method, when a copy of it is around: set
		# NVDA_SOURCE to its source folder.
		source = os.environ.get("NVDA_SOURCE")
		if not source:
			self.skipTest("NVDA_SOURCE isn't set to a folder with NVDA 2026.2's source")
		for name, path in NVDA_CODE_FILES.items():
			with open(os.path.join(source, *path.split("/")), encoding="utf-8") as f:
				text = f.read().replace("\r\n", "\n")
			for block in globals()[name].strip("\n").split("\n\n\n"):
				self.assertTrue(block in text or textwrap.indent(block, "\t") in text, f"{name}: {block.splitlines()[0]}")

	def test_nvdasOutlookSupportReadsNoStatusBar(self):
		# NVDA's support for Outlook reads no status bar its own way, so NVDA reads Outlook's as any other.
		source = os.environ.get("NVDA_SOURCE")
		if not source:
			self.skipTest("NVDA_SOURCE isn't set to a folder with NVDA 2026.2's source")
		with open(os.path.join(source, "appModules", "outlook.py"), encoding="utf-8") as f:
			text = f.read()
		self.assertNotIn("getStatusBarText", text)
		self.assertNotIn("_get_statusBar", text)


class JawsOwnScriptTests(unittest.TestCase):
	#: Where JAWS 2026 keeps its scripts, when it is installed.
	SCRIPTS = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Freedom Scientific", "JAWS", "2026", "Scripts")

	def read(self, *path):
		fullPath = os.path.join(self.SCRIPTS, *path)
		if not os.path.isfile(fullPath):
			self.skipTest(f"JAWS 2026's scripts aren't on this computer ({fullPath})")
		with open(fullPath, encoding="utf-8-sig", errors="replace") as f:
			return f.read()

	def test_insertPageDownIsSayBottomLineOfWindow(self):
		self.assertIn("Insert+PageDown=SayBottomLineOfWindow", self.read("enu", "Default.JKM"))

	def test_outlooksScriptReadsTheSimpleButtons(self):
		# JAWS's rule, as the imitation (jawsReads) follows it: in Outlook, Insert+Page Down reads the status bar's
		# children of that class, the name of each on a line of its own.
		script = self.read("Outlook.jss")
		function = script[script.index("string function GetStatusBarWindowInfo()") :]
		function = function[: function.index("EndFunction")]
		self.assertIn("UIA_ClassNamePropertyId, objn_NetUISimpleButton", function)
		self.assertIn("oStatusBar.findAll(TreeScope_Children", function)
		self.assertIn("sText = oStatusBarItem.name", function)
		self.assertIn("sStatusBarText + cscBufferNewLine + sText", function)
		sayBottomLine = script[script.index("script SayBottomLineOfWindow()") :]
		self.assertIn("sStatusBar = GetStatusBarWindowInfo()", sayBottomLine[: sayBottomLine.index("EndScript")])
		self.assertIn('objn_NetUISimpleButton = "NetUISimpleButton"', self.read("Outlook.jsh"))
		self.assertEqual(outlookStatusBar.ITEM_CLASS, "NetUISimpleButton")


if __name__ == "__main__":
	unittest.main()
