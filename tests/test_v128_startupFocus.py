# Unit tests for version 1.28, from a tester's report (issue 25): "When typing in a edit box NVDA is silent". He had
# just started NVDA with its desktop shortcut's key, which leaves the focus on the taskbar, and version 1.18's
# startupFocus gave the focus back to Edge, where he was in Reddit Chat's message box. NVDA said the first capital "I"
# (JAWS Eloquence Typing's own), and nothing else he typed. His log has a "typed word" line for every word and no
# "Speaking" line after it: NVDA echoes typed characters "only in edit controls" (his setting), and asks
# speech.isFocusEditable, which is False for a web page, as a page is read only. His log shows why the page was NVDA's
# focus: NVDA took Edge's focus through UI Automation as it started (a ChromiumUIATreeInterceptor), and a few seconds
# later Edge's own IAccessible2 focus event for the page (a ChromeVBuf); the box already had Edge's focus, so no event
# for it came again when he went into it. In his logs, NVDA took Edge through UI Automation at four of the five
# starts where startupFocus went back to Edge, and through IAccessible2 at every other time: his NVDA reads Edge's
# pages through IAccessible2 ("Use UI Automation to access Chromium based browser controls" as it comes).
# NVDA 2026.2 tells whether it reads a window through UI Automation only once its helper is in the program
# (UIAHandler._isUIAWindowHelper: canUseOlderInProcessApproach). Windows puts the helper in a program when it comes to
# the front or takes the focus (nvdaHelper/remote/injection.cpp), and NVDA takes the helper in on its event queue
# (NVDAHelper, appModuleHandler.update), which runs only after all its plugins have started. Edge's UI Automation
# focus event came while they started, and NVDA made its focus from it (UIAHandler's
# HandleFocusChangedEvent), before core._setInitialFocus.
# - startupFocus: while NVDA starts, a UI Automation focus event of the program it went back to is left out
#   (shouldAllowUIAFocusEvent), and NVDA finds the focus itself once it has started. When NVDA takes a UI Automation
#   object there as the focus, it asks again how it reads the window (focusRedirect): NVDA keeps an answer for half a
#   second (UIAHandler.isUIAWindow), and the one from before the helper can't stand. When NVDA's helper comes into the
#   program only after NVDA has started, the focus is taken again once it has.
# The imitation NVDA runs NVDA 2026.2's own baseObject Getter, CachingGetter, AutoPropertyType and AutoPropertyObject,
# DynamicNVDAObjectType.__call__, NVDAObject.findBestAPIClass, getPossibleAPIClasses and objectWithFocus,
# Window.getPossibleAPIClasses and kwargsFromSuper, UIA.kwargsFromSuper and _get_shouldAllowUIAFocusEvent,
# UIAHandler's HandleFocusChangedEvent, _isUIAWindowHelper, isUIAWindow and isNativeUIAElement with its window class
# lists, config.AllowUiaInChromium, eventHandler.queueEvent, _queueEventCallback, _trackFocusObject and executeEvent,
# core._setInitialFocus, appModuleHandler.update, IAccessibleHandler.winEventToNVDAEvent and processFocusNVDAEvent,
# and speech's isFocusEditable, speakTypedCharacters and clearTypedWordBuffer, word for word. Windows, Edge's UI
# Automation and IAccessible2 objects, NVDA's queue and the rest of its start are imitated. The assistant's code is
# the real one: its plugin's _backFromTaskbar, chooseNVDAObjectOverlayClasses and terminate, and startupFocus.
# Run: python -m unittest tests.test_v128_startupFocus -v

import __future__
import abc
import enum
import os
import sys
import textwrap
import threading
import types
import typing
import unicodedata
import unittest
import weakref
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import jawsMigrator  # noqa: E402
from jawsMigrator import startupFocus  # noqa: E402

# -- NVDA 2026.2's own code -----------------------------------------------------------------------------------------

#: NVDA 2026.2, source/baseObject.py: Getter, CachingGetter, AutoPropertyType, AutoPropertyObject, word for word.
NVDA_BASE_OBJECT = r'''
class Getter(object):
	def __init__(self, fget, abstract=False):
		self.fget = fget
		if abstract:
			self._abstract = self.__isabstractmethod__ = abstract

	def __get__(
		self,
		instance: Union[Any, None, "AutoPropertyObject"],
		owner,
	) -> Union[GetterReturnT, "Getter"]:
		if isinstance(self.fget, classmethod):
			return self.fget.__get__(instance, owner)()
		elif instance is None:
			return self
		return self.fget(instance)

	def setter(self, func):
		return (abstractproperty if self._abstract else property)(fget=self.fget, fset=func)

	def deleter(self, func):
		return (abstractproperty if self._abstract else property)(fget=self.fget, fdel=func)


class CachingGetter(Getter):
	def __get__(
		self,
		instance: Union[Any, None, "AutoPropertyObject"],
		owner,
	) -> Union[GetterReturnT, "CachingGetter"]:
		if isinstance(self.fget, classmethod):
			log.warning("Class properties do not support caching")
			return self.fget.__get__(instance, owner)()
		elif instance is None:
			return self
		return instance._getPropertyViaCache(self.fget)


class AutoPropertyType(ABCMeta):
	def __init__(self, name: str, bases: tuple[type, ...], namespace: dict[str, Any], /, **kwargs: Any):
		super().__init__(name, bases, namespace, **kwargs)

		cacheByDefault = False
		try:
			cacheByDefault = namespace["cachePropertiesByDefault"]
		except KeyError:
			cacheByDefault = any(getattr(base, "cachePropertiesByDefault", False) for base in bases)

		# Create a set containing properties that are marked as abstract.
		newAbstractProps = set()
		# Create a set containing properties that were, but are no longer abstract.
		oldAbstractProps = set()
		# given _get_myVal, _set_myVal, and _del_myVal: "myVal" would be output 3 times
		# use a set comprehension to ensure unique values, "myVal" only needs to occur once.
		props = {x[5:] for x in namespace.keys() if x[0:5] in ("_get_", "_set_", "_del_")}
		for x in props:
			g = namespace.get("_get_%s" % x, None)
			s = namespace.get("_set_%s" % x, None)
			d = namespace.get("_del_%s" % x, None)
			if x in namespace:
				methodsString = ",".join(str(i) for i in (g, s, d) if i)
				raise TypeError(
					"%s is already a class attribute, cannot create descriptor with methods %s"
					% (x, methodsString),
				)
			if not g:
				# There's a setter or deleter, but no getter.
				# This means it could be in one of the base classes.
				for base in bases:
					g = getattr(base, "_get_%s" % x, None)
					if g:
						break

			cache = namespace.get("_cache_%s" % x, None)
			if cache is None:
				# The cache setting hasn't been specified in this class, but it could be in one of the bases.
				for base in bases:
					cache = getattr(base, "_cache_%s" % x, None)
					if cache is not None:
						break
				else:
					cache = cacheByDefault if not isinstance(g, classmethod) else False

			abstract = namespace.get("_abstract_%s" % x, False)
			if g and not (s or d):
				attr = (CachingGetter if cache else Getter)(g, abstract)
			else:
				attr = (abstractproperty if abstract else property)(fget=g, fset=s, fdel=d)
			if abstract:
				newAbstractProps.add(x)
			elif x in self.__abstractmethods__:
				oldAbstractProps.add(x)
			setattr(self, x, attr)

		if newAbstractProps or oldAbstractProps:
			# The __abstractmethods__ set is frozen, therefore we ought to override it.
			self.__abstractmethods__ = (self.__abstractmethods__ | newAbstractProps) - oldAbstractProps


class AutoPropertyObject(garbageHandler.TrackedObject, metaclass=AutoPropertyType):
	"""A class that dynamically supports properties, by looking up _get_*, _set_*, and _del_* methods at runtime.
	_get_x will make property x with a getter (you can get its value).
	_set_x will make a property x with a setter (you can set its value).
	_del_x will make a property x with a deleter that is executed when deleting its value.
	If there is a _get_x but no _set_x then setting x will override the property completely.
	Properties can also be cached for the duration of one core pump cycle.
	This is useful if the same property is likely to be fetched multiple times in one cycle.
	For example, several NVDAObject properties are fetched by both braille and speech.
	Setting _cache_x to C{True} specifies that x should be cached.
	Setting it to C{False} specifies that it should not be cached.
	If _cache_x is not set, L{cachePropertiesByDefault} is used.
	Properties can also be made abstract.
	Setting _abstract_x to C{True} specifies that x should be abstract.
	Setting it to C{False} specifies that it should not be abstract.
	"""

	#: Tracks the instances of this class; used by L{invalidateCaches}.
	#: @type: weakref.WeakKeyDictionary
	__instances = weakref.WeakKeyDictionary()
	#: Specifies whether properties are cached by default;
	#: can be overridden for individual properties by setting _cache_propertyName.
	#: @type: bool
	cachePropertiesByDefault = False

	_propertyCache: Set[GetterMethodT]

	def __new__(cls, *args, **kwargs):
		self = super(AutoPropertyObject, cls).__new__(cls)
		#: Maps properties to cached values.
		#: @type: dict
		self._propertyCache = {}
		self.__instances[self] = None
		return self

	def _getPropertyViaCache(self, getterMethod: Optional[GetterMethodT] = None) -> GetterReturnT:
		if not getterMethod:
			raise ValueError("getterMethod is None")
		missing = False
		try:
			val = self._propertyCache[getterMethod]
		except KeyError:
			missing = True
		if missing:
			val = getterMethod(self)
			self._propertyCache[getterMethod] = val
		return val

	def invalidateCache(self):
		self._propertyCache.clear()

	@classmethod
	def invalidateCaches(cls):
		"""Invalidate the caches for all current instances."""
		# We use a list here, as invalidating the cache on an object may cause instances to disappear,
		# which would in turn cause an exception due to the dictionary changing size during iteration.
		for instance in list(cls.__instances):
			instance.invalidateCache()
'''

#: NVDA 2026.2, source/NVDAObjects/__init__.py: DynamicNVDAObjectType.__call__, word for word.
NVDA_DYNAMIC_CALL = r'''
def __call__(self, chooseBestAPI=True, **kwargs):
	if chooseBestAPI:
		APIClass = self.findBestAPIClass(kwargs)
		if not APIClass:
			return None
	else:
		APIClass = self

	# Instantiate the requested class.
	try:
		obj = APIClass.__new__(APIClass, **kwargs)
		obj.APIClass = APIClass
		if isinstance(obj, self):
			obj.__init__(**kwargs)
	except InvalidNVDAObject as e:
		log.debugWarning("Invalid NVDAObject: %s" % e, exc_info=True)
		return None

	clsList = []
	if "findOverlayClasses" in APIClass.__dict__:
		obj.findOverlayClasses(clsList)
	else:
		clsList.append(APIClass)
	# Allow app modules to choose overlay classes.
	appModule = obj.appModule
	# optimisation: The base implementation of chooseNVDAObjectOverlayClasses does nothing,
	# so only call this method if it's been overridden.
	if appModule and not hasattr(appModule.chooseNVDAObjectOverlayClasses, "_isBase"):
		try:
			appModule.chooseNVDAObjectOverlayClasses(obj, clsList)
		except Exception:
			log.exception(f"Exception in chooseNVDAObjectOverlayClasses for {appModule}")
			pass

	# Allow global plugins to choose overlay classes.
	for plugin in globalPluginHandler.runningPlugins:
		if "chooseNVDAObjectOverlayClasses" in plugin.__class__.__dict__:
			try:
				plugin.chooseNVDAObjectOverlayClasses(obj, clsList)
			except Exception:
				log.exception(f"Exception in chooseNVDAObjectOverlayClasses for {plugin}")
				pass

	# After all other mutation has finished,
	# add LockScreenObject if Windows is locked.
	# LockScreenObject must become the first class to be resolved,
	# i.e. insertion order of 0.
	self._insertLockScreenObject(clsList)

	# Determine the bases for the new class.
	bases = []
	for index in range(len(clsList)):
		# A class doesn't need to be a base if it is already implicitly included by being a superclass of a previous base.
		if index == 0 or not issubclass(clsList[index - 1], clsList[index]):
			bases.append(clsList[index])

	# Construct the new class.
	if len(bases) == 1:
		# We only have one base, so there's no point in creating a dynamic type.
		newCls = bases[0]
	else:
		bases = tuple(bases)
		newCls = self._dynamicClassCache.get(bases, None)
		if not newCls:
			name = "Dynamic_%s" % "".join([x.__name__ for x in clsList])
			newCls = type(name, bases, {"__module__": __name__})
			self._dynamicClassCache[bases] = newCls

	oldMro = frozenset(obj.__class__.__mro__)
	# Mutate obj into the new class.
	obj.__class__ = newCls

	# Initialise the overlay classes.
	for cls in reversed(newCls.__mro__):
		if cls in oldMro:
			# This class was part of the initially constructed object, so its constructor would have been called.
			continue
		initFunc = cls.__dict__.get("initOverlayClass")
		if initFunc:
			try:
				initFunc(obj)
			except Exception:
				log.exception(f"Exception in initOverlayClass for {cls}")
				continue
		# Bind gestures specified on the class.
		try:
			obj.bindGestures(getattr(cls, "_%s__gestures" % cls.__name__))
		except AttributeError:
			pass

	# Allow app modules to make minor tweaks to the instance.
	if appModule and hasattr(appModule, "event_NVDAObject_init"):
		try:
			appModule.event_NVDAObject_init(obj)
		except Exception:
			log.exception(f"Exception in event_NVDAObject_init for {appModule}")
			pass

	return obj
'''

#: NVDA 2026.2, source/NVDAObjects/__init__.py: NVDAObject.findBestAPIClass, NVDAObject.getPossibleAPIClasses, NVDAObject.objectWithFocus, word for word.
NVDA_NVDAOBJECT_METHODS = r'''
@classmethod
def findBestAPIClass(cls, kwargs, relation=None):
	"""
	Finds out the highest-level APIClass this object can get to given these kwargs, and updates the kwargs and returns the APIClass.
	@param relation: the relationship of a possible new object of this type to  another object creating it (e.g. parent).
	@param type: string
	@param kwargs: the arguments necessary to construct an object of the class this method was called on.
	@type kwargs: dictionary
	@returns: the new APIClass
	@rtype: DynamicNVDAObjectType
	"""
	newAPIClass = cls
	if "getPossibleAPIClasses" in newAPIClass.__dict__:
		for possibleAPIClass in newAPIClass.getPossibleAPIClasses(kwargs, relation=relation):
			if "kwargsFromSuper" not in possibleAPIClass.__dict__:
				log.error("possible API class %s does not implement kwargsFromSuper" % possibleAPIClass)
				continue
			if possibleAPIClass.kwargsFromSuper(kwargs, relation=relation):
				return possibleAPIClass.findBestAPIClass(kwargs, relation=relation)
	return newAPIClass if newAPIClass is not NVDAObject else None


@classmethod
def getPossibleAPIClasses(cls, kwargs, relation=None):
	"""
	Provides a generator which can generate all the possible API classes (in priority order) that inherit directly from the class it was called on.
	@param relation: the relationship of a possible new object of this type to  another object creating it (e.g. parent).
	@param type: string
	@param kwargs: the arguments necessary to construct an object of the class this method was called on.
	@type kwargs: dictionary
	@returns: a generator
	@rtype: generator
	"""
	import NVDAObjects.window

	yield NVDAObjects.window.Window


@staticmethod
def objectWithFocus():
	"""Retrieves the object representing the control currently with focus in the Operating System. This differens from NVDA's focus object as this focus object is the real focus object according to the Operating System, not according to NVDA.
	@return: the object with focus.
	@rtype: L{NVDAObject}
	"""
	kwargs = {}
	APIClass = NVDAObject.findBestAPIClass(kwargs, relation="focus")
	if not APIClass:
		return None
	obj = APIClass(chooseBestAPI=False, **kwargs)
	if not obj:
		return None
	focusRedirect = obj.focusRedirect
	if focusRedirect:
		obj = focusRedirect
	return obj
'''

#: NVDA 2026.2, source/NVDAObjects/window/__init__.py: Window.getPossibleAPIClasses, Window.kwargsFromSuper, word for word.
NVDA_WINDOW_METHODS = r'''
@classmethod
def getPossibleAPIClasses(cls, kwargs, relation=None):
	windowHandle = kwargs["windowHandle"]
	windowClassName = winUser.getClassName(windowHandle)
	# The desktop window should stay as a window
	if windowClassName == "#32769":
		return
	# If this window has a ghost window its too dangerous to try any higher APIs
	if _GhostWindowFromHungWindow is not None and _GhostWindowFromHungWindow(windowHandle):
		return
	if windowClassName == "EXCEL7" and (relation == "focus" or isinstance(relation, tuple)):
		from . import excel

		yield excel.ExcelCell
	if windowClassName == "EXCEL:":
		from .excel import ExcelDropdown as newCls

		yield newCls
	import JABHandler

	if JABHandler.isJavaWindow(windowHandle):
		import NVDAObjects.JAB

		yield NVDAObjects.JAB.JAB
	import UIAHandler

	if UIAHandler.handler and UIAHandler.handler.isUIAWindow(windowHandle):
		import NVDAObjects.UIA

		yield NVDAObjects.UIA.UIA
	import NVDAObjects.IAccessible

	yield NVDAObjects.IAccessible.IAccessible


@classmethod
def kwargsFromSuper(cls, kwargs, relation=None):
	windowHandle = None
	if relation in ("focus", "foreground"):
		windowHandle = winUser.getForegroundWindow()
		if not windowHandle:
			windowHandle = winUser.getDesktopWindow()
		if windowHandle and relation == "focus":
			threadID = winUser.getWindowThreadProcessID(windowHandle)[1]
			threadInfo = winUser.getGUIThreadInfo(threadID)
			if threadInfo.hwndFocus:
				windowHandle = threadInfo.hwndFocus
	elif isinstance(relation, tuple):
		windowHandle = user32.WindowFromPhysicalPoint(ctypes.wintypes.POINT(relation[0], relation[1]))
	if not windowHandle:
		return False
	kwargs["windowHandle"] = windowHandle
	return True
'''

#: NVDA 2026.2, source/NVDAObjects/UIA/__init__.py: UIA.kwargsFromSuper, UIA._get_shouldAllowUIAFocusEvent, word for word.
NVDA_UIA_METHODS = r'''
@classmethod
def kwargsFromSuper(cls, kwargs, relation=None, ignoreNonNativeElementsWithFocus=True):
	UIAElement = None
	windowHandle = kwargs.get("windowHandle")
	if isinstance(relation, tuple):
		UIAElement = UIAHandler.handler.clientObject.ElementFromPointBuildCache(
			POINT(relation[0], relation[1]),
			UIAHandler.handler.baseCacheRequest,
		)
		if UIAHandler._isDebug():
			log.debug(
				f"kwargsFromSuper: given coordinates {relation}, "
				f"fetched element {UIAHandler.handler.getUIAElementDebugString(UIAElement)}",
			)
		# Ignore this object if it is non native.
		if not UIAHandler.handler.isNativeUIAElement(UIAElement):
			if UIAHandler._isDebug():
				log.debug(
					f"kwargsFromSuper: ignoring non native element at coordinates {relation}",
				)
			return False
		# This object may be in a different window, so we need to recalculate the window handle.
		kwargs["windowHandle"] = None
	elif relation == "focus":
		try:
			UIAElement = UIAHandler.handler.clientObject.getFocusedElementBuildCache(
				UIAHandler.handler.baseCacheRequest,
			)
		except COMError:
			log.debugWarning("getFocusedElement failed", exc_info=True)
			return False
		if UIAHandler._isDebug():
			log.debug(
				f"kwargsFromSuper: fetched focused element "
				f"{UIAHandler.handler.getUIAElementDebugString(UIAElement)}",
			)
		# Ignore this object if it is non native.
		if ignoreNonNativeElementsWithFocus and not UIAHandler.handler.isNativeUIAElement(UIAElement):
			if UIAHandler._isDebug():
				log.debug(
					"kwargsFromSuper: ignoring non native element with focus",
				)
			return False
		# This object may be in a different window, so we need to recalculate the window handle.
		kwargs["windowHandle"] = None
	else:
		UIAElement = UIAHandler.handler.clientObject.ElementFromHandleBuildCache(
			windowHandle,
			UIAHandler.handler.baseCacheRequest,
		)
	if not UIAElement:
		return False
	kwargs["UIAElement"] = UIAElement
	return True


def _get_shouldAllowUIAFocusEvent(self):
	try:
		return bool(self._getUIACacheablePropertyValue(UIAHandler.UIA_HasKeyboardFocusPropertyId))
	except COMError:
		return True
'''

#: NVDA 2026.2, source/UIAHandler/__init__.py: UIAHandler.IUIAutomationFocusChangedEventHandler_HandleFocusChangedEvent, UIAHandler._isUIAWindowHelper, UIAHandler.isUIAWindow, UIAHandler.isNativeUIAElement, word for word.
NVDA_UIA_HANDLER_METHODS = r'''
def IUIAutomationFocusChangedEventHandler_HandleFocusChangedEvent(self, sender):
	if _isDebug():
		log.debug(f"handleFocusChangedEvent called with element {self.getUIAElementDebugString(sender)}")
	if not self.MTAThreadInitEvent.is_set():
		# UIAHandler hasn't finished initialising yet, so just ignore this event.
		if _isDebug():
			log.debug("HandleFocusChangedEvent: event received while not fully initialized")
		return
	self.lastFocusedUIAElement = sender
	if not self.isNativeUIAElement(sender):
		# #12982: This element may be the root of an MS Word document
		# for which we may be refusing to use UIA as its implementation may be incomplete.
		# However, there are some controls embedded in the MS Word document window
		# such as the Modern comments side track pane
		# for which we do have to use UIA.
		# But, if focus jumps from one of these controls back to the document (E.g. the user presses escape),
		# we receive no MSAA focus event, only a UIA focus event.
		# As we are not treating the Word doc as UIA, we need to manually fire an MSAA focus event on the document.
		self._emitMSAAFocusForWordDocIfNecessary(sender)
		if _isDebug():
			log.debug(f"Ignoring for non native element {self.getUIAElementDebugString(sender)}")
		return
	import NVDAObjects.UIA

	if isinstance(eventHandler.lastQueuedFocusObject, NVDAObjects.UIA.UIA):
		lastFocusObj = eventHandler.lastQueuedFocusObject
		# Ignore duplicate focus events.
		# It seems that it is possible for compareElements to return True, even though the objects are different.
		# Therefore, don't ignore the event if the last focus object has lost its hasKeyboardFocus state.
		try:
			if (
				not lastFocusObj.shouldAllowDuplicateUIAFocusEvent
				and self.clientObject.compareElements(sender, lastFocusObj.UIAElement)
				and lastFocusObj.UIAElement.currentHasKeyboardFocus
			):
				if _isDebug():
					log.debugWarning(
						"HandleFocusChangedEvent: Ignoring duplicate focus event ",
					)
				return
		except COMError:
			if _isDebug():
				log.debugWarning(
					"HandleFocusChangedEvent: Couldn't check for duplicate focus event ",
					exc_info=True,
				)
	window = self.getNearestWindowHandle(sender)
	if window and not eventHandler.shouldAcceptEvent("gainFocus", windowHandle=window):
		if _isDebug():
			log.debug(
				"HandleFocusChangedEvent: Ignoring for shouldAcceptEvent=False",
			)
		return
	try:
		obj = NVDAObjects.UIA.UIA(windowHandle=window, UIAElement=sender)
	except Exception:
		if _isDebug():
			log.debugWarning(
				"HandleFocusChangedEvent: Exception while creating NVDAObject ",
				exc_info=True,
			)
		obj = None
	if not obj:
		if _isDebug():
			log.debug(
				"handleFocusChangedEvent: Could not create an NVDAObject ",
			)
		return
	if _isDebug():
		log.debug(f"Created object {obj} for element {self.getUIAElementDebugString(sender)}")
	if not obj.shouldAllowUIAFocusEvent:
		if _isDebug():
			log.debug(
				"HandleFocusChangedEvent: NVDAObject chose to ignore event ",
			)
		return
	if _isDebug():
		log.debug(
			f"handleFocusChangedEvent: Queuing NVDA gainFocus event for obj {obj} ",
		)
	eventHandler.queueEvent("gainFocus", obj)


def _isUIAWindowHelper(self, hwnd: int, isDebug=False) -> bool:  # noqa: C901
	if isDebug:
		log.debug(f"checking window {self.getWindowHandleDebugString(hwnd)}")
	# UIA in NVDA's process freezes in Windows 7 and below
	processID = winUser.getWindowThreadProcessID(hwnd)[0]
	if globalVars.appPid == processID:
		if isDebug:
			log.debug("Window is from NVDA's process. Treating as non-UIA")
		return False
	import NVDAObjects.window

	rawWindowClass = winUser.getClassName(hwnd)
	windowClass = NVDAObjects.window.Window.normalizeWindowClassName(rawWindowClass)
	# For certain window classes, we always want to use UIA.
	if windowClass in goodUIAWindowClassNames:
		if isDebug:
			log.debug("Window found in goodUIAWindowClassNames. Treating as UIA")
		return True
	# allow the appModule for the window to also choose if this window is good
	# An appModule should be able to override bad UIA class names as prescribed by core
	appModule = appModuleHandler.getAppModuleFromProcessID(processID)
	if appModule and appModule.isGoodUIAWindow(hwnd):
		if isDebug:
			log.debug(
				f"appModule {appModule.appName} says to treat window as UIA",
			)
		return True
	# There are certain window classes that just had bad UIA implementations
	if windowClass in badUIAWindowClassNames:
		if isDebug:
			log.debug("Window found in baddUIAWindowClassNames. Treating as non-UIA")
		return False
	# allow the appModule for the window to also choose if this window is bad
	if appModule and appModule.isBadUIAWindow(hwnd):
		if isDebug:
			log.debug(
				f"appModule {appModule.appName} says to not treat window as UIA",
			)
		return False
	if windowClass == "NetUIHWND" and appModule:
		# NetUIHWND is used for various controls in MS Office.
		# IAccessible should be used for NetUIHWND in versions older than 2016
		# Fixes: lack of focus reporting (#4207),
		# Fixes: strange reporting of context menu items(#9252),
		# fixes: not being able to report ribbon sections when they starts with an edit  field (#7067)
		# Note that #7067 is not fixed for Office 2016 and never.
		# Using IAccessible for NetUIHWND controls causes focus changes not to be reported
		# when the ribbon is collapsed.
		# Testing shows that these controls emits proper events but they are ignored by NVDA.
		try:
			isOfficeApp = appModule.productName.startswith(("Microsoft Office", "Microsoft Outlook"))
			isOffice2013OrOlder = isOfficeApp and int(appModule.productVersion.split(".")[0]) < 16
		except RuntimeError:
			# this is not necessarily an office app, or an app with version information, for example geekbench 6.
			log.debugWarning(
				"Failed parsing productName / productVersion, version information likely missing",
				exc_info=True,
			)
			isOfficeApp = False
			isOffice2013OrOlder = False
		if isOfficeApp and isOffice2013OrOlder:
			parentHwnd = winUser.getAncestor(hwnd, winUser.GA_PARENT)
			while parentHwnd:
				if winUser.getClassName(parentHwnd) in ("Net UI Tool Window", "MsoCommandBar"):
					if isDebug:
						log.debug("Office 2013 ribon or older. Treating as non-UIA")
					return False
				parentHwnd = winUser.getAncestor(parentHwnd, winUser.GA_PARENT)
	# Ask the window if it supports UIA natively
	res = winBindings.uiAutomationCore.UiaHasServerSideProvider(hwnd)
	if res:
		if isDebug:
			log.debug("window has UIA server side provider")
		canUseOlderInProcessApproach = bool(appModule.helperLocalBindingHandle)
		if windowClass == MS_WORD_DOCUMENT_WINDOW_CLASS:
			# The window does support UIA natively, but MS Word documents now
			# have a fairly usable UI Automation implementation.
			# However, builds of MS Office 2016 before build 15000 or so had bugs which
			# we cannot work around.
			# Therefore, if we can inject in-process, refuse to use UIA and instead
			# fall back to the MS Word object model.
			if not shouldUseUIAInMSWord(appModule):
				if isDebug:
					log.debug("MS word document treated as non-UIA")
				return False
		# MS Excel spreadsheets now have a fairly usable UI Automation implementation.
		# However, builds of MS Office 2016 before build 9000 or so had bugs which we
		# cannot work around.
		# And even current builds of Office 2016 are still missing enough info from UIA
		# that it is still impossible to switch to UIA completely.
		# Therefore, if we can inject in-process, refuse to use UIA and instead fall
		# back to the MS Excel object model.
		elif (
			# An MS Excel spreadsheet window
			windowClass == "EXCEL7"
			# Disabling is only useful if we can inject in-process (and use our older code)
			and appModule.helperLocalBindingHandle
			# Allow the user to explicitly force UIA support for MS Excel spreadsheets
			# no matter the Office version
			and not config.conf["UIA"]["useInMSExcelWhenAvailable"]
		):
			if isDebug:
				log.debug("MS Excel spreadsheet  treated as non-UIA")
			return False
		elif windowClass == "Chrome_RenderWidgetHostHWND":
			# Unless explicitly allowed, all Chromium implementations (including Edge) should not be UIA,
			# As their IA2 implementation is still better at the moment.
			# However, in cases where Chromium is running under another logon session,
			# the IAccessible2 implementation is unavailable.
			# 'brchrome' is part of HP SureClick, a chromium-based browser which runs webpages to run in separate
			# virtual machines - it supports UIA remoting but not IAccessible2 remoting.
			hasAccessToIA2 = (
				not appModule.isRunningUnderDifferentLogonSession and not appModule.appName == "brchrome"
			)
			if (
				AllowUiaInChromium.getConfig() == AllowUiaInChromium.NO
				# Disabling is only useful if we can inject in-process (and use our older code)
				or (
					canUseOlderInProcessApproach
					and hasAccessToIA2
					and AllowUiaInChromium.getConfig()
					!= AllowUiaInChromium.YES  # Users can prefer to use UIA
				)
			):
				if isDebug:
					log.debug("_isUIAWindowHelper:Chromium window treated as non-UIA")
				return False
		elif windowClass == "ConsoleWindowClass":
			if not utils._shouldUseUIAConsole(hwnd):
				if isDebug:
					log.debug("Windows console treated as non-UIA")
				return False
		elif windowClass == "SysListView32":
			# #15283: SysListView32 controls in Windows Forms have a native UIA implementation
			# and lack a MSAA implementation.
			# We need to rely on UIA for these controls, as otherwise parent/child navigation is broken.
			# For other instances however, even when the control advertises a native UIA implementation,
			# the implementation is likely to be incomplete and MSAA should be prefered.
			if isDebug:
				log.debug(f"Checking framework of {rawWindowClass} window ")
			if not utils._isFrameworkIdWinForm(hwnd):
				if isDebug:
					log.debug("SysListView32 treated as non-UIA")
				return False
		if isDebug:
			log.debug("Treating as UIA")
	else:
		if isDebug:
			log.debug("window does not have UIA server side provider. Treating as non-UIA")
	return bool(res)


def isUIAWindow(self, hwnd: int, isDebug: bool = False) -> bool:
	# debugging for this function is explicitly controled via an argument
	# as this function may be also called from MSAA code.
	now = time.time()
	v = self.UIAWindowHandleCache.get(hwnd, None)
	if not v or (now - v[1]) > 0.5:
		v = (
			self._isUIAWindowHelper(hwnd, isDebug=isDebug),
			now,
		)
		self.UIAWindowHandleCache[hwnd] = v
	elif isDebug:
		log.debug(f"Found cached is UIA window {v[0]} for hwnd {self.getWindowHandleDebugString(hwnd)}")
	return v[0]


def isNativeUIAElement(self, UIAElement):
	if _isDebug():
		log.debug(f"checking if is native UIA  element: {self.getUIAElementDebugString(UIAElement)}")
	# Due to issues dealing with UIA elements coming from the same process, we do not class these UIA elements as usable.
	# It seems to be safe enough to retrieve the cached processID,
	# but using tree walkers or fetching other properties causes a freeze.
	try:
		processID = UIAElement.cachedProcessId
	except COMError:
		if _isDebug():
			log.debug(f"could not fetch processId. {self.getUIAElementDebugString(UIAElement)}")
		return False
	if processID == globalVars.appPid:
		if _isDebug():
			log.debug(
				"element is local to NVDA, treating as non-native.",
			)
		return False
	# Whether this is a native element depends on whether its window natively supports UIA.
	windowHandle = self.getNearestWindowHandle(UIAElement)
	if windowHandle:
		if self.isUIAWindow(windowHandle, isDebug=_isDebug()):
			if _isDebug():
				log.debug(
					"treating element as native due to "
					f"windowHandle {self.getWindowHandleDebugString(windowHandle)}. ",
				)
			return True
		# #12982: although NVDA by default may not treat this element's window as native UIA,
		# E.g. it is proxied from MSAA, or NVDA has specifically black listed it,
		# It may be an element from a NetUIcontainer embedded in a Word document,
		# such as the MS Word Modern Comments side track pane.
		# These elements are only exposed via UIA, and not MSAA,
		# thus we must treat these elements as native UIA.
		if self._isNetUIEmbeddedInWordDoc(UIAElement):
			if _isDebug():
				log.debug(
					"treating as native as is a netUI embedded in word doc. ",
				)
			return True
		if (
			winUser.getClassName(windowHandle) == "DirectUIHWND"
			and "IEFRAME.dll" in UIAElement.cachedProviderDescription
			and UIAElement.currentClassName
			in ("DownloadBox", "accessiblebutton", "DUIToolbarButton", "PushButton")
		):
			# This is the IE 9 downloads list.
			# #3354: UiaHasServerSideProvider returns false for the IE 9 downloads list window,
			# so we'd normally use MSAA for this control.
			# However, its MSAA implementation is broken (fires invalid events) if UIA is initialised,
			# whereas its UIA implementation works correctly.
			# Therefore, we must use UIA here.
			if _isDebug():
				log.debug(
					"treating as native as is in IE9 downloads list. ",
				)
			return True
	if _isDebug():
		log.debug("Treating element as non-native")
	return False
'''

#: NVDA 2026.2, source/UIAHandler/__init__.py: MS_WORD_DOCUMENT_WINDOW_CLASS, goodUIAWindowClassNames, badUIAWindowClassNames, word for word.
NVDA_UIA_WINDOW_CLASSES = r'''
MS_WORD_DOCUMENT_WINDOW_CLASS = "_WwG"


goodUIAWindowClassNames = (
	# A WDAG (Windows Defender Application Guard) Window is always native UIA, even if it doesn't report as such.
	"RAIL_WINDOW",
	# #17407, #17771: WinUI 3 top-level pane window class name.
	"Microsoft.UI.Content.DesktopChildSiteBridge",
)


badUIAWindowClassNames = (
	# UIA events of candidate window interfere with MSAA events.
	"Microsoft.IME.CandidateWindow.View",
	"SysTreeView32",
	"WuDuiListView",
	"ComboBox",
	"msctls_progress32",
	"Edit",
	"CommonPlacesWrapperWndClass",
	"SysMonthCal32",
	"SUPERGRID",  # Outlook 2010 message list
	"RichEdit",
	"RichEdit20",
	"RICHEDIT50W",
	"Button",
	# #8944: The Foxit UIA implementation is incomplete and should not be used for now.
	"FoxitDocWnd",
	# Mozilla Gecko (Firefox, etc.) has a native UIA implementation. However, IA2
	# is still better for web content in screen readers for now.
	"MozillaWindowClass",
	"MozillaDropShadowWindowClass",
	"MozillaDialogClass",
	"MozillaContentWindowClass",
)
'''

#: NVDA 2026.2, source/config/__init__.py: AllowUiaInChromium, word for word.
NVDA_ALLOW_UIA_IN_CHROMIUM = r'''
class AllowUiaInChromium(Enum):
	_DEFAULT = 0  # maps to 'when necessary'
	WHEN_NECESSARY = 1  # the current default
	YES = 2
	NO = 3

	@staticmethod
	def getConfig() -> "AllowUiaInChromium":
		allow = AllowUiaInChromium(conf["UIA"]["allowInChromium"])
		if allow == AllowUiaInChromium._DEFAULT:
			return AllowUiaInChromium.WHEN_NECESSARY
		return allow
'''

#: NVDA 2026.2, source/eventHandler.py: queueEvent, _queueEventCallback, _trackFocusObject, executeEvent, word for word.
NVDA_EVENT_HANDLER = r'''
def queueEvent(eventName, obj, **kwargs):
	"""Queues an NVDA event to be executed.
	@param eventName: the name of the event type (e.g. 'gainFocus', 'nameChange')
	@type eventName: string
	"""
	_trackFocusObject(eventName, obj)
	with _pendingEventCountsLock:
		_pendingEventCountsByName[eventName] = _pendingEventCountsByName.get(eventName, 0) + 1
		_pendingEventCountsByObj[obj] = _pendingEventCountsByObj.get(obj, 0) + 1
		_pendingEventCountsByNameAndObj[(eventName, obj)] = (
			_pendingEventCountsByNameAndObj.get((eventName, obj), 0) + 1
		)
	queueHandler.queueFunction(
		queueHandler.eventQueue,
		_queueEventCallback,
		eventName,
		obj,
		kwargs,
		_immediate=eventName == "gainFocus",
	)


def _queueEventCallback(eventName, obj, kwargs):
	with _pendingEventCountsLock:
		curCount = _pendingEventCountsByName.get(eventName, 0)
		if curCount > 1:
			_pendingEventCountsByName[eventName] = curCount - 1
		elif curCount == 1:
			del _pendingEventCountsByName[eventName]
		curCount = _pendingEventCountsByObj.get(obj, 0)
		if curCount > 1:
			_pendingEventCountsByObj[obj] = curCount - 1
		elif curCount == 1:
			del _pendingEventCountsByObj[obj]
		curCount = _pendingEventCountsByNameAndObj.get((eventName, obj), 0)
		if curCount > 1:
			_pendingEventCountsByNameAndObj[(eventName, obj)] = curCount - 1
		elif curCount == 1:
			del _pendingEventCountsByNameAndObj[(eventName, obj)]
	executeEvent(eventName, obj, **kwargs)


def _trackFocusObject(eventName: str, obj: "NVDAObjects.NVDAObject") -> None:
	"""Keeps track of lastQueuedFocusObject and sets wasGainFocusObj attr on objects.
	:param eventName: the event type, eg "gainFocus"
	:param obj: the object to track if focused
	"""
	global lastQueuedFocusObject

	if eventName == "gainFocus" and not objectBelowLockScreenAndWindowsIsLocked(
		obj,
		shouldLog=config.conf["debugLog"]["events"],
	):
		lastQueuedFocusObject = obj


def executeEvent(
	eventName: str,
	obj: "NVDAObjects.NVDAObject",
	**kwargs,
) -> None:
	"""Executes an NVDA event.
	@param eventName: the name of the event type (e.g. 'gainFocus', 'nameChange')
	@param obj: the object the event is for
	@param kwargs: Additional event parameters as keyword arguments.
	"""
	if objectBelowLockScreenAndWindowsIsLocked(
		obj,
		shouldLog=config.conf["debugLog"]["events"],
	):
		return
	try:
		global _virtualDesktopName
		isGainFocus = eventName == "gainFocus"
		# Allow NVDAObjects to redirect focus events to another object of their choosing.
		if isGainFocus and obj.focusRedirect:
			obj = obj.focusRedirect
		sleepMode = obj.sleepMode
		# Handle possible virtual desktop name change event.
		# More effective in Windows 10 Version 1903 and later.
		from NVDAObjects.window import Window

		if (
			eventName == "nameChange"
			and isinstance(obj, Window)
			and obj.windowClassName == "#32769"
			and _canAnnounceVirtualDesktopNames
		):
			import core

			_virtualDesktopName = obj.name
			core.callLater(250, handlePossibleDesktopNameChange)
		if isGainFocus and not doPreGainFocus(obj, sleepMode=sleepMode):
			return
		elif not sleepMode and eventName == "documentLoadComplete" and not doPreDocumentLoadComplete(obj):
			return
		elif not sleepMode:
			_EventExecuter(eventName, obj, kwargs)
	except Exception:
		log.exception(f"error executing event: {eventName} on {obj} with extra args of {kwargs}")
'''

#: NVDA 2026.2, source/core.py: _setInitialFocus, word for word.
NVDA_SET_INITIAL_FOCUS = r'''
def _setInitialFocus():
	"""Sets the initial focus if no focus event was received at startup."""
	import eventHandler
	import api

	if eventHandler.lastQueuedFocusObject:
		# The focus has already been set or a focus event is pending.
		return
	try:
		focus = api.getDesktopObject().objectWithFocus()
		if focus:
			eventHandler.queueEvent("gainFocus", focus)
	except:  # noqa: E722
		log.exception("Error retrieving initial focus")
'''

#: NVDA 2026.2, source/appModuleHandler.py: update, word for word.
NVDA_APP_MODULE_UPDATE = r'''
def update(processID, helperLocalBindingHandle=None, inprocRegistrationHandle=None):
	"""Tries to load a new appModule for the given process ID if need be.
	@param processID: the ID of the process.
	@type processID: int
	@param helperLocalBindingHandle: an optional RPC binding handle pointing to the RPC server for this process
	@param inprocRegistrationHandle: an optional rpc context handle representing successful registration with the rpc server for this process
	"""
	# This creates a new app module if necessary.
	mod = getAppModuleFromProcessID(processID)
	if helperLocalBindingHandle:
		mod.helperLocalBindingHandle = helperLocalBindingHandle
	if inprocRegistrationHandle:
		mod._inprocRegistrationHandle = inprocRegistrationHandle
'''

#: NVDA 2026.2, source/IAccessibleHandler/__init__.py: winEventToNVDAEvent, processFocusNVDAEvent, word for word.
NVDA_WIN_EVENT_TO_NVDA_EVENT = r'''
def winEventToNVDAEvent(  # noqa: C901
	eventID: int,
	window: int,
	objectID: int,
	childID: int,
	useCache: bool = True,
) -> Optional[Tuple[str, NVDAObjects.IAccessible.IAccessible]]:
	"""Tries to convert a win event ID to an NVDA event name, and instantiate or fetch an NVDAObject for
	 the win event parameters.
	@param eventID: the win event ID (type)
	@param window: the win event's window handle
	@param objectID: the win event's object ID
	@param childID: the win event's childID
	@param useCache: C{True} to use the L{liveNVDAObjectTable} cache when
	 retrieving an NVDAObject, C{False} if the cache should not be used.
	@returns: the NVDA event name and the NVDAObject the event is for
	"""
	if isMSAADebugLoggingEnabled():
		log.debug(
			f"Creating NVDA event from winEvent: {getWinEventLogInfo(window, objectID, childID, eventID)}, "
			f"use cache {useCache}",
		)
	NVDAEventName = internalWinEventHandler.winEventIDsToNVDAEventNames.get(eventID, None)
	if not NVDAEventName:
		log.debugWarning(f"No NVDA event name for {getWinEventName(eventID)}")
		return None
	if isMSAADebugLoggingEnabled():
		log.debug(f"winEvent mapped to NVDA event: {NVDAEventName}")
	# Ignore any events with invalid window handles
	if not window or not winUser.isWindow(window):
		if isMSAADebugLoggingEnabled():
			log.debug(
				f"Invalid window. Dropping winEvent {getWinEventLogInfo(window, objectID, childID, eventID)}",
			)
		return None
	# Make sure this window does not have a ghost window if possible
	if user32._GhostWindowFromHungWindow is not None and user32._GhostWindowFromHungWindow(window):
		if isMSAADebugLoggingEnabled():
			log.debug(
				f"Ghosted hung window. Dropping winEvent {getWinEventLogInfo(window, objectID, childID, eventID)}",
			)
		return None
	# We do not support MSAA object proxied from native UIA
	if UIAHandler.handler and UIAHandler.handler.isUIAWindow(window, isDebug=isMSAADebugLoggingEnabled()):
		if isMSAADebugLoggingEnabled():
			log.debug(
				f"Native UIA window. Dropping winEvent {getWinEventLogInfo(window, objectID, childID, eventID)}",
			)
		return None
	obj = None
	if useCache:
		# See if we already know an object by this win event info
		obj = liveNVDAObjectTable.get((window, objectID, childID), None)
		if isMSAADebugLoggingEnabled() and obj:
			log.debug(
				f"Fetched existing NVDAObject {obj} from liveNVDAObjectTable"
				f" for winEvent {getWinEventLogInfo(window, objectID, childID)}",
			)
	# If we don't yet have the object, then actually instanciate it.
	if not obj:
		obj = NVDAObjects.IAccessible.getNVDAObjectFromEvent(window, objectID, childID)
	# At this point if we don't have an object then we can't do any more
	if not obj:
		if isMSAADebugLoggingEnabled():
			log.debug(
				"Could not instantiate an NVDAObject for winEvent: "
				f"{getWinEventLogInfo(window, objectID, childID, eventID)}",
			)
		return None
	# SDM MSAA objects sometimes don't contain enough information to be useful Sometimes there is a real
	# window that does, so try to get the SDMChild property on the NVDAObject, and if successull use that as
	# obj instead.
	if "bosa_sdm" in obj.windowClassName:
		SDMChild = getattr(obj, "SDMChild", None)
		if SDMChild:
			obj = SDMChild
	if isMSAADebugLoggingEnabled():
		log.debug(
			f"Successfully created NVDA event {NVDAEventName} for {obj} "
			f"from winEvent {getWinEventLogInfo(window, objectID, childID, eventID)}",
		)
	return (NVDAEventName, obj)


def processFocusNVDAEvent(obj, force=False):
	"""Processes a focus NVDA event.
	If the focus event is valid, it is queued.
	@param obj: the NVDAObject the focus event is for
	@type obj: L{NVDAObjects.NVDAObject}
	@param force: If True, the shouldAllowIAccessibleFocusEvent property of the object is ignored.
	@type force: boolean
	@return: C{True} if the focus event is valid and was queued, C{False} otherwise.
	@rtype: boolean
	"""
	if not force and isinstance(obj, NVDAObjects.IAccessible.IAccessible):
		focus = eventHandler.lastQueuedFocusObject
		if isinstance(focus, NVDAObjects.IAccessible.IAccessible) and focus.isDuplicateIAccessibleEvent(obj):
			if isMSAADebugLoggingEnabled():
				log.debug(f"Dropping duplicate IAccessible focus event for {obj}")
			return True
		if not obj.shouldAllowIAccessibleFocusEvent:
			if isMSAADebugLoggingEnabled():
				log.debug(f"IAccessible focus event not allowed by {obj}")
			return False
	eventHandler.queueEvent("gainFocus", obj)
	return True
'''

#: NVDA 2026.2, source/speech/speech.py: PROTECTED_CHAR, FIRST_NONCONTROL_CHAR, isFocusEditable, speakTypedCharacters, clearTypedWordBuffer, word for word.
NVDA_TYPED_CHARACTERS = r'''
PROTECTED_CHAR = "*"


FIRST_NONCONTROL_CHAR = " "


def isFocusEditable() -> bool:
	"""Check if the currently focused object is editable.
	:return: ``True`` if the focused object is editable, ``False`` otherwise.
	"""
	obj = api.getFocusObject()
	controls = {controlTypes.ROLE_EDITABLETEXT, controlTypes.ROLE_DOCUMENT, controlTypes.ROLE_TERMINAL}
	return (
		obj.role in controls or controlTypes.STATE_EDITABLE in obj.states
	) and controlTypes.STATE_READONLY not in obj.states


def speakTypedCharacters(ch: str):
	typingIsProtected = api.isTypingProtected()
	if typingIsProtected:
		realChar = PROTECTED_CHAR
	else:
		realChar = ch
	if unicodedata.category(ch)[0] in "LMN":
		_curWordChars.append(realChar)
	elif ch == "\b":
		# Backspace, so remove the last character from our buffer.
		del _curWordChars[-1:]
	elif ch == "\u007f":
		# delete character produced in some apps with control+backspace
		return
	elif len(_curWordChars) > 0:
		typedWord = "".join(_curWordChars)
		clearTypedWordBuffer()
		if log.isEnabledFor(log.IO):
			log.io("typed word: %s" % typedWord)
		typingEchoMode = config.conf["keyboard"]["speakTypedWords"]
		if typingEchoMode != TypingEcho.OFF.value and not typingIsProtected:
			if typingEchoMode == TypingEcho.ALWAYS.value or (
				typingEchoMode == TypingEcho.EDIT_CONTROLS.value and isFocusEditable()
			):
				speakText(typedWord)
	if _speechState._suppressSpeakTypedCharactersNumber > 0:
		# We primarily suppress based on character count and still have characters to suppress.
		# However, we time out after a short while just in case.
		suppress = time.time() - _speechState._suppressSpeakTypedCharactersTime <= 0.1
		if suppress:
			_speechState._suppressSpeakTypedCharactersNumber -= 1
		else:
			_speechState._suppressSpeakTypedCharactersNumber = 0
			_speechState._suppressSpeakTypedCharactersTime = None
	else:
		suppress = False

	typingEchoMode = config.conf["keyboard"]["speakTypedCharacters"]
	if not suppress and typingEchoMode != TypingEcho.OFF.value and ch >= FIRST_NONCONTROL_CHAR:
		if typingEchoMode == TypingEcho.ALWAYS.value or (
			typingEchoMode == TypingEcho.EDIT_CONTROLS.value and isFocusEditable()
		):
			speakSpelling(realChar)


def clearTypedWordBuffer() -> None:
	"""
	Forgets any word currently being built up with typed characters for speaking.
	This should be called when the user's context changes such that they could no longer
	complete the word (such as a focus change or choosing to move the caret).
	"""
	_curWordChars.clear()
'''

#: The file of NVDA 2026.2's source each piece is from.
NVDA_CODE_FILES = {
	"NVDA_BASE_OBJECT": "baseObject.py",
	"NVDA_DYNAMIC_CALL": "NVDAObjects/__init__.py",
	"NVDA_NVDAOBJECT_METHODS": "NVDAObjects/__init__.py",
	"NVDA_WINDOW_METHODS": "NVDAObjects/window/__init__.py",
	"NVDA_UIA_METHODS": "NVDAObjects/UIA/__init__.py",
	"NVDA_UIA_HANDLER_METHODS": "UIAHandler/__init__.py",
	"NVDA_UIA_WINDOW_CLASSES": "UIAHandler/__init__.py",
	"NVDA_ALLOW_UIA_IN_CHROMIUM": "config/__init__.py",
	"NVDA_EVENT_HANDLER": "eventHandler.py",
	"NVDA_SET_INITIAL_FOCUS": "core.py",
	"NVDA_APP_MODULE_UPDATE": "appModuleHandler.py",
	"NVDA_WIN_EVENT_TO_NVDA_EVENT": "IAccessibleHandler/__init__.py",
	"NVDA_TYPED_CHARACTERS": "speech/speech.py",
}

# -- the imitation NVDA --------------------------------------------------------------------------------------------

nvdaLog = nvdaStubs.logging.getLogger("nvda")


def nvdaCode(source, name, namespace):
	"""Compile NVDA's own ``source`` in ``namespace``, the imitation NVDA, and give back ``name`` from it. Annotations
	aren't evaluated, as they needn't be to run NVDA's code."""
	code = compile(source, f"<NVDA 2026.2: {name}>", "exec", flags=__future__.annotations.compiler_flag, dont_inherit=True)
	exec(code, namespace)
	return namespace[name]


def nvdaClass(header, sources, namespace):
	"""A class made of NVDA's own methods and the imitation's: their sources go in the class's body, so that super()
	and their decorators work in them. ``header`` is the class line without its colon."""
	name = header.split()[1].split("(")[0]
	body = "\n".join(textwrap.indent(textwrap.dedent(source), "\t") for source in sources)
	return nvdaCode(f"{header}:\n{body}", name, namespace)


PROCESS_NVDA, PROCESS_EXPLORER, PROCESS_EDGE, PROCESS_NOTEPAD = 1234, 5000, 6000, 7000
TASKBAR, EDGE, EDGE_PAGE, NOTEPAD, NOTEPAD_TEXT = 0x10010, 0x20020, 0x20021, 0x30030, 0x30031
EVENT_OBJECT_FOCUS = 0x8005
OBJID_CLIENT = -4
UIA_HasKeyboardFocusPropertyId = 30008


class Role(enum.IntEnum):
	UNKNOWN = 0
	EDITABLETEXT = 8
	DOCUMENT = 52
	BUTTON = 9
	TERMINAL = 84


class State(enum.IntEnum):
	FOCUSED = 5
	READONLY = 8
	EDITABLE = 0x40000


class Element:
	"""A UI Automation element of a program, or an IAccessible2 object: what NVDA gets from the program."""

	def __init__(self, process, window, name, role, states=()):
		self.cachedProcessId = process
		self.cachedNativeWindowHandle = window
		self.name, self.role, self.states = name, role, frozenset(states)
		self.currentHasKeyboardFocus = True

	def __repr__(self):
		return f"<{self.name}, {self.role.name.lower()}>"


class Computer:
	"""The tester's Windows: NVDA started on the taskbar, Edge behind it with the focus in Reddit Chat's message box,
	and Notepad, a program NVDA reads through UI Automation."""

	def __init__(self):
		self.windows = {
			TASKBAR: ("Shell_TrayWnd", PROCESS_EXPLORER, None),
			EDGE: ("Chrome_WidgetWin_1", PROCESS_EDGE, None),
			EDGE_PAGE: ("Chrome_RenderWidgetHostHWND", PROCESS_EDGE, EDGE),
			NOTEPAD: ("Notepad", PROCESS_NOTEPAD, None),
			NOTEPAD_TEXT: ("RichEditD2DPT", PROCESS_NOTEPAD, NOTEPAD),
		}
		#: The windows that answer UI Automation themselves (UiaHasServerSideProvider): Chromium's page and Notepad's text.
		self.uiaServers = {EDGE_PAGE, NOTEPAD_TEXT}
		self.foreground = TASKBAR
		#: The window with the keyboard focus in each top-level window, when it is in front.
		self.focusWindow = {TASKBAR: TASKBAR, EDGE: EDGE_PAGE, NOTEPAD: NOTEPAD_TEXT}
		self.messageBox = Element(PROCESS_EDGE, EDGE_PAGE, "Write message", Role.EDITABLETEXT, (State.EDITABLE, State.FOCUSED))
		self.page = Element(PROCESS_EDGE, EDGE_PAGE, "Reddit Chat", Role.DOCUMENT, (State.READONLY, State.FOCUSED))
		self.notepadText = Element(PROCESS_NOTEPAD, NOTEPAD_TEXT, "Text editor", Role.DOCUMENT, (State.EDITABLE, State.FOCUSED))
		self.taskbarButton = Element(PROCESS_EXPLORER, TASKBAR, "Copilot pinned", Role.BUTTON)
		#: What has the focus in each window, for UI Automation and for IAccessible2: the same control.
		self.focusIn = {EDGE_PAGE: self.messageBox, NOTEPAD_TEXT: self.notepadText, TASKBAR: self.taskbarButton}

	def focusedWindow(self):
		return self.focusWindow.get(self.foreground, self.foreground)

	def focused(self):
		return self.focusIn.get(self.focusedWindow())


class Windows:
	"""Windows as startupFocus asks it about top-level windows, on the tester's computer: the taskbar, then Edge."""

	def __init__(self, computer, order):
		self.computer, self.order = computer, order
		self.madeForeground = []

	def foreground(self):
		return self.computer.foreground

	def setForeground(self, window):
		self.madeForeground.append(window)
		self.computer.foreground = window
		return True

	def zOrder(self):
		return iter(self.order)

	def className(self, window):
		return self.computer.windows[window][0]

	def processId(self, window):
		return self.computer.windows[window][1]

	def isVisible(self, window):
		return True

	def isEnabled(self, window):
		return True

	def isMinimized(self, window):
		return False

	def isCloaked(self, window):
		return False

	def extendedStyle(self, window):
		return 0

	def hasTitle(self, window):
		return True

	def hasSize(self, window):
		return True

	def rootOwner(self, window):
		return window

	def lastActivePopup(self, window):
		return window

	def shellWindow(self):
		return 0

	def child(self, parent, className):
		return 0

	def topLevel(self, className):
		return iter(())


class Clock:
	"""NVDA's time.time(), which it keeps a window's UI Automation answer by (half a second)."""

	def __init__(self):
		self.now = 1000.0

	def time(self):
		return self.now


class Nvda:
	"""NVDA 2026.2 as it starts, made of its own code where it decides which object is the focus."""

	def __init__(self, computer):
		self.computer = computer
		self.clock = Clock()
		self.starting = True
		self.focus = None
		self.executed = []
		self.pendingWinEvents = []
		self.config = {
			"UIA": {"allowInChromium": 0, "useInMSExcelWhenAvailable": False},
			"debugLog": {"events": False},
			"keyboard": {"speakTypedCharacters": 1, "speakTypedWords": 0},
		}
		self.modules = {}
		self._makeModules()

	# -- modules ---------------------------------------------------------------------------------------------------

	def module(self, name, **attributes):
		made = types.ModuleType(name)
		for key, value in attributes.items():
			setattr(made, key, value)
		self.modules[name] = made
		return made

	def _makeModules(self):  # noqa: C901
		computer = self.computer
		nvda = self

		class GUIThreadInfo:
			def __init__(self, hwndFocus):
				self.hwndFocus = hwndFocus

		self.winUser = self.module(
			"winUser",
			getClassName=lambda window: computer.windows[window][0] if window in computer.windows else "",
			getWindowThreadProcessID=lambda window: (computer.windows[window][1], computer.windows[window][1] + 1),
			getForegroundWindow=lambda: computer.foreground,
			getDesktopWindow=lambda: 0x10000,
			getGUIThreadInfo=lambda threadID: GUIThreadInfo(computer.focusedWindow()),
			isWindow=lambda window: window in computer.windows,
			getAncestor=lambda window, flags: computer.windows[window][2] or 0,
			GA_PARENT=1,
			OBJID_CLIENT=OBJID_CLIENT,
			EVENT_OBJECT_FOCUS=EVENT_OBJECT_FOCUS,
		)
		self.globalVars = self.module("globalVars", appPid=PROCESS_NVDA)
		self.configModule = self.module("config", conf=self.config)
		self.NVDAState = self.module(
			"NVDAState",
			_TrackNVDAInitialization=types.SimpleNamespace(isInitializationComplete=lambda: not nvda.starting),
		)
		self.JABHandler = self.module("JABHandler", isJavaWindow=lambda window: False)
		self.winBindings = self.module(
			"winBindings",
			uiAutomationCore=types.SimpleNamespace(UiaHasServerSideProvider=lambda window: window in computer.uiaServers),
		)
		self.globalPluginHandler = self.module("globalPluginHandler", runningPlugins=[], GlobalPlugin=sys.modules["globalPluginHandler"].GlobalPlugin)

		# NVDA's event queue: a pump runs what was queued before it (queueHandler.flushQueue).
		queue = []

		def queueFunction(q, func, *args, _immediate=False, **kwargs):
			q.append((func, args, kwargs))

		def pumpAll():
			for _count in range(len(queue) + 1):
				if queue:
					func, args, kwargs = queue.pop(0)
					func(*args, **kwargs)

		self.queue = queue
		self.queueHandler = self.module("queueHandler", eventQueue=queue, queueFunction=queueFunction, pumpAll=pumpAll)

		# App modules: Edge's gets NVDA's helper when its registration is taken in (appModuleHandler.update).
		class AppModule:
			def __init__(self, processID, appName):
				self.processID, self.appName = processID, appName
				self.helperLocalBindingHandle = None
				self._inprocRegistrationHandle = None
				self.isRunningUnderDifferentLogonSession = False

			def isGoodUIAWindow(self, hwnd):
				return False

			def isBadUIAWindow(self, hwnd):
				return False

			def chooseNVDAObjectOverlayClasses(self, obj, clsList):
				pass

			chooseNVDAObjectOverlayClasses._isBase = True

		names = {PROCESS_EDGE: "msedge", PROCESS_NOTEPAD: "notepad", PROCESS_EXPLORER: "explorer", PROCESS_NVDA: "nvda"}
		runningTable = {}

		def getAppModuleFromProcessID(processID):
			if processID not in runningTable:
				runningTable[processID] = AppModule(processID, names[processID])
			return runningTable[processID]

		self.appModuleHandler = self.module("appModuleHandler", runningTable=runningTable, getAppModuleFromProcessID=getAppModuleFromProcessID)
		nvdaCode(NVDA_APP_MODULE_UPDATE, "update", vars(self.appModuleHandler))

		# baseObject, and the NVDAObjects NVDA makes for the focus.
		base = {
			"garbageHandler": types.SimpleNamespace(TrackedObject=object),
			"log": nvdaLog,
			"weakref": weakref,
			"ABCMeta": abc.ABCMeta,
			"abstractproperty": abc.abstractproperty,
		}
		nvdaCode(NVDA_BASE_OBJECT, "AutoPropertyObject", base)
		self.AutoPropertyObject = base["AutoPropertyObject"]
		self.NVDAObjects = self.module("NVDAObjects")
		self.windowModule = self.module("NVDAObjects.window")
		self.UIAModule = self.module("NVDAObjects.UIA")
		self.IAccessibleModule = self.module("NVDAObjects.IAccessible")
		self.NVDAObjects.window, self.NVDAObjects.UIA, self.NVDAObjects.IAccessible = self.windowModule, self.UIAModule, self.IAccessibleModule

		class InvalidNVDAObject(RuntimeError):
			pass

		objects = dict(
			base,
			InvalidNVDAObject=InvalidNVDAObject,
			globalPluginHandler=self.globalPluginHandler,
			appModuleHandler=self.appModuleHandler,
			winUser=self.winUser,
			_GhostWindowFromHungWindow=None,
			user32=None,
			ctypes=None,
			COMError=OSError,
			POINT=None,
		)
		self.objectNamespace = objects
		nvdaClass(
			"class DynamicNVDAObjectType(AutoPropertyType)",
			[
				"_dynamicClassCache = {}\n",
				# Windows isn't locked.
				"@staticmethod\ndef _insertLockScreenObject(clsList):\n\tpass\n",
				NVDA_DYNAMIC_CALL,
			],
			objects,
		)
		NVDAObject = nvdaClass(
			"class NVDAObject(AutoPropertyObject, metaclass=DynamicNVDAObjectType)",
			[
				"cachePropertiesByDefault = True\n",
				"focusRedirect = None\n",
				# NVDA's own is its app module's: no program here is in sleep mode.
				"sleepMode = False\n",
				NVDA_NVDAOBJECT_METHODS,
				"def __init__(self):\n\tpass\n",
				"def bindGestures(self, gestures):\n\tpass\n",
				"def _get_appModule(self):\n\treturn appModuleHandler.getAppModuleFromProcessID(self.processID)\n",
			],
			objects,
		)
		self.NVDAObjects.NVDAObject = NVDAObject
		Window = nvdaClass(
			"class Window(NVDAObject)",
			[
				NVDA_WINDOW_METHODS,
				"def __init__(self, windowHandle=None):\n\tself.windowHandle = windowHandle\n",
				# NVDA's changes only the names of Windows Forms' and some other windows' classes.
				"@classmethod\ndef normalizeWindowClassName(cls, name):\n\treturn name\n",
				"def _get_windowClassName(self):\n\treturn winUser.getClassName(self.windowHandle)\n",
				"def _get_processID(self):\n\treturn winUser.getWindowThreadProcessID(self.windowHandle)[0]\n",
			],
			objects,
		)
		self.windowModule.Window = Window
		self.UIAHandlerModule = self.module("UIAHandler", _isDebug=lambda: False, handler=None)
		objects["UIAHandler"] = self.UIAHandlerModule
		UIA = nvdaClass(
			"class UIA(Window)",
			[
				NVDA_UIA_METHODS,
				# NVDA's own takes the window, name, role and states from the element too.
				"def __init__(self, windowHandle=None, UIAElement=None, initialUIACachedPropertyIDs=None):\n"
				"\tif not UIAElement:\n\t\traise ValueError('needs a UIA element')\n"
				"\tself.UIAElement = UIAElement\n"
				"\tself.windowHandle = UIAElement.cachedNativeWindowHandle\n",
				"shouldAllowDuplicateUIAFocusEvent = False\n",
				"def _getUIACacheablePropertyValue(self, propertyID):\n"
				"\tassert propertyID == UIAHandler.UIA_HasKeyboardFocusPropertyId\n"
				"\treturn self.UIAElement.currentHasKeyboardFocus\n",
				"def _get_processID(self):\n\treturn self.UIAElement.cachedProcessId\n",
				"def _get_name(self):\n\treturn self.UIAElement.name\n",
				"def _get_role(self):\n\treturn self.UIAElement.role\n",
				"def _get_states(self):\n\treturn set(self.UIAElement.states)\n",
			],
			objects,
		)
		self.UIAModule.UIA = UIA
		self.UIAHandlerModule.UIA_HasKeyboardFocusPropertyId = UIA_HasKeyboardFocusPropertyId
		IAccessible = nvdaClass(
			"class IAccessible(Window)",
			[
				# NVDA's own asks accFocus from the window's client object down to the focus, as Edge answers it here.
				"@classmethod\n"
				"def kwargsFromSuper(cls, kwargs, relation=None):\n"
				"\tif relation != 'focus':\n\t\treturn False\n"
				"\tacc = computer.focusIn.get(kwargs['windowHandle'])\n"
				"\tif not acc:\n\t\treturn False\n"
				"\tkwargs['IAccessibleObject'] = acc\n"
				"\tkwargs['IAccessibleChildID'] = 0\n"
				"\treturn True\n",
				"def __init__(self, windowHandle=None, IAccessibleObject=None, IAccessibleChildID=None, event_windowHandle=None, event_objectID=None, event_childID=None):\n"
				"\tself.IAccessibleObject = IAccessibleObject\n"
				"\tself.windowHandle = windowHandle or IAccessibleObject.cachedNativeWindowHandle\n"
				"\tself.event_windowHandle, self.event_objectID, self.event_childID = event_windowHandle, event_objectID, event_childID\n",
				"shouldAllowIAccessibleFocusEvent = True\n",
				"def isDuplicateIAccessibleEvent(self, obj):\n\treturn isinstance(obj, IAccessible) and obj.IAccessibleObject is self.IAccessibleObject\n",
				"def _get_name(self):\n\treturn self.IAccessibleObject.name\n",
				"def _get_role(self):\n\treturn self.IAccessibleObject.role\n",
				"def _get_states(self):\n\treturn set(self.IAccessibleObject.states)\n",
			],
			dict(objects, computer=computer),
		)
		objects["IAccessible"] = IAccessible
		self.IAccessibleModule.IAccessible = IAccessible
		self.IAccessibleModule.getNVDAObjectFromEvent = lambda window, objectID, childID: IAccessible(
			windowHandle=window, IAccessibleObject=computer.focusIn[window], event_windowHandle=window, event_objectID=objectID, event_childID=childID
		)
		self.UIAObject, self.IAccessibleObject, self.NVDAObject = UIA, IAccessible, NVDAObject

		# NVDA's focus, and its desktop object, which asks Windows for the focus (NVDAObject.objectWithFocus).
		self.api = self.module(
			"api",
			getFocusObject=lambda: nvda.focus,
			getDesktopObject=lambda: types.SimpleNamespace(objectWithFocus=NVDAObject.objectWithFocus),
			isTypingProtected=lambda: False,
		)

		def setFocusObject(obj):
			nvda.focus = obj
			return True

		self.api.setFocusObject = setFocusObject

		# eventHandler: NVDA's own queueing and executing; its doPreGainFocus is imitated, as far as NVDA's focus goes.
		eventHandler = self.module("eventHandler", lastQueuedFocusObject=None)
		self.eventHandler = eventHandler

		def doPreGainFocus(obj, sleepMode=False):
			nvda.api.setFocusObject(obj)
			return True

		def executed(eventName, obj, kwargs):
			nvda.executed.append((eventName, obj))

		vars(eventHandler).update(
			_pendingEventCountsByName={},
			_pendingEventCountsByObj={},
			_pendingEventCountsByNameAndObj={},
			_pendingEventCountsLock=threading.RLock(),
			queueHandler=self.queueHandler,
			config=self.configModule,
			log=nvdaLog,
			objectBelowLockScreenAndWindowsIsLocked=lambda obj, shouldLog=False: False,
			doPreGainFocus=doPreGainFocus,
			doPreDocumentLoadComplete=lambda obj: True,
			_EventExecuter=executed,
			handlePossibleDesktopNameChange=lambda: None,
			_canAnnounceVirtualDesktopNames=False,
			shouldAcceptEvent=lambda eventName, windowHandle=None: True,
			_virtualDesktopName=None,
		)
		nvdaCode(NVDA_EVENT_HANDLER, "executeEvent", vars(eventHandler))

		# UIAHandler: NVDA's own focus event, UI Automation window and native element checks.
		handlerNamespace = vars(self.UIAHandlerModule)
		handlerNamespace.update(
			log=nvdaLog,
			eventHandler=eventHandler,
			winUser=self.winUser,
			globalVars=self.globalVars,
			appModuleHandler=self.appModuleHandler,
			winBindings=self.winBindings,
			config=self.configModule,
			time=self.clock,
			COMError=OSError,
			utils=None,
			shouldUseUIAInMSWord=lambda appModule: False,
			Enum=enum.Enum,
			conf=self.config,
		)
		nvdaCode(NVDA_UIA_WINDOW_CLASSES, "badUIAWindowClassNames", handlerNamespace)
		nvdaCode(NVDA_ALLOW_UIA_IN_CHROMIUM, "AllowUiaInChromium", handlerNamespace)

		class Client:
			"""UI Automation's client object: the element with the keyboard focus, as Windows has it."""

			def getFocusedElementBuildCache(self, cacheRequest):
				return computer.focused()

			def compareElements(self, first, second):
				return first is second

		handlerClass = nvdaClass(
			"class UIAHandler",
			[
				NVDA_UIA_HANDLER_METHODS,
				"def getNearestWindowHandle(self, UIAElement):\n\treturn UIAElement.cachedNativeWindowHandle\n",
				"def _emitMSAAFocusForWordDocIfNecessary(self, element):\n\tpass\n",
				"def _isNetUIEmbeddedInWordDoc(self, element):\n\treturn False\n",
				"def getUIAElementDebugString(self, element):\n\treturn repr(element)\n",
				"def getWindowHandleDebugString(self, window):\n\treturn hex(window)\n",
			],
			handlerNamespace,
		)
		handler = handlerClass()
		handler.MTAThreadInitEvent = threading.Event()
		handler.MTAThreadInitEvent.set()
		handler.UIAWindowHandleCache = {}
		handler.clientObject = Client()
		handler.baseCacheRequest = None
		handler.lastFocusedUIAElement = None
		self.UIAHandlerModule.handler = handler
		self.handler = handler

		# IAccessibleHandler: NVDA's own conversion of a focus winEvent, and its queueing of the focus.
		iaNamespace = {
			"log": nvdaLog,
			"winUser": self.winUser,
			"user32": types.SimpleNamespace(_GhostWindowFromHungWindow=None),
			"UIAHandler": self.UIAHandlerModule,
			"NVDAObjects": self.NVDAObjects,
			"eventHandler": eventHandler,
			"internalWinEventHandler": types.SimpleNamespace(winEventIDsToNVDAEventNames={EVENT_OBJECT_FOCUS: "gainFocus"}),
			"isMSAADebugLoggingEnabled": lambda: False,
			"liveNVDAObjectTable": {},
			"getWinEventLogInfo": lambda *args: str(args),
			"getWinEventName": str,
		}
		self.winEventToNVDAEvent = nvdaCode(NVDA_WIN_EVENT_TO_NVDA_EVENT, "winEventToNVDAEvent", iaNamespace)
		self.processFocusNVDAEvent = iaNamespace["processFocusNVDAEvent"]
		self.setInitialFocus = nvdaCode(NVDA_SET_INITIAL_FOCUS, "_setInitialFocus", {"log": nvdaLog})

	# -- NVDA starting -----------------------------------------------------------------------------------------------

	def installed(self):
		return mock.patch.dict(sys.modules, self.modules)

	def uiaFocusEvent(self):
		"""The program in front fires UI Automation's focus event; NVDA handles it on its UI Automation thread."""
		element = self.computer.focused()
		thread = threading.Thread(target=self.handler.IUIAutomationFocusChangedEventHandler_HandleFocusChangedEvent, args=(element,))
		thread.start()
		thread.join()

	def ia2FocusEvent(self):
		"""The program in front fires its IAccessible2 focus winEvent; NVDA takes it on its next pump."""
		self.pendingWinEvents.append((EVENT_OBJECT_FOCUS, self.computer.focusedWindow(), OBJID_CLIENT, 0))

	def helperRegisters(self, process):
		"""NVDA's helper is in ``process`` and registers with NVDA, which takes it in on its event queue (NVDAHelper)."""
		self.queueHandler.queueFunction(
			self.queue,
			self.appModuleHandler.update,
			process,
			helperLocalBindingHandle=f"binding {process}",
			inprocRegistrationHandle=f"registration {process}",
		)

	def plugInsStarted(self):
		"""core.main after NVDA's plugins: it queues _setInitialFocus, and marks its start complete."""
		self.queueHandler.queueFunction(self.queue, self.setInitialFocus)
		self.starting = False

	def pump(self, times=4):
		"""NVDA's core pumps: winEvents first (IAccessibleHandler.pumpAll), then its queue, 10 ms apart."""
		for _time in range(times):
			winEvents, self.pendingWinEvents = self.pendingWinEvents, []
			for eventID, window, objectID, childID in winEvents:
				# IAccessibleHandler.processFocusWinEvent, as far as a focus winEvent from Edge goes.
				NVDAEvent = self.winEventToNVDAEvent(eventID, window, objectID, childID, useCache=False)
				if NVDAEvent:
					self.processFocusNVDAEvent(NVDAEvent[1])
			self.queueHandler.pumpAll()
			self.AutoPropertyObject.invalidateCaches()
			self.clock.now += 0.01

	def focusEvents(self):
		return [obj for name, obj in self.executed]


# -- the tester's start ---------------------------------------------------------------------------------------------


class Timers:
	"""wx.CallLater, as startupFocus uses it: the timers wait until the test runs them."""

	def __init__(self):
		self.waiting = []

	def CallLater(self, milliseconds, function):
		timers = self

		class Timer:
			def Stop(self):
				if self in timers.waiting:
					timers.waiting.remove(self)

			def run(self):
				timers.waiting.remove(self)
				function()

		timer = Timer()
		self.waiting.append(timer)
		return timer

	def runAll(self, nvda, most=200):
		for _count in range(most):
			if not self.waiting:
				return
			self.waiting[0].run()
			nvda.pump(1)


class StartTests(unittest.TestCase):
	def setUp(self):
		self.computer = Computer()
		self.nvda = Nvda(self.computer)
		self.timers = Timers()
		self.nvda.modules["wx"] = self.timers
		patcher = self.nvda.installed()
		patcher.start()
		self.addCleanup(patcher.stop)
		for name, value in (("_process", 0), ("_overlay", None), ("_timer", None), ("_failed", False), ("_redirecting", False)):
			setattr(startupFocus, name, value)
		self.addCleanup(startupFocus.stop)
		self.plugin = jawsMigrator.GlobalPlugin.__new__(jawsMigrator.GlobalPlugin)
		self.plugin._startupFocus = None
		self.nvda.globalPluginHandler.runningPlugins.append(self.plugin)

	def backFromTaskbar(self, turnedOn=True):
		"""The assistant's plugin starts: NVDA started on the taskbar goes back to Edge (see startupFocus)."""
		windows = Windows(self.computer, [TASKBAR, EDGE, NOTEPAD])
		with mock.patch.object(startupFocus, "Win32", return_value=windows), mock.patch.object(
			jawsMigrator.state, "load", return_value={startupFocus.STATE_KEY: turnedOn}
		):
			self.plugin._backFromTaskbar()
		return windows

	def start(self, helper="with the focus", version="1.28"):
		"""NVDA starts on the taskbar, with the tester's Edge behind it. ``helper``: when NVDA's helper in Edge
		registers: before Edge's focus events, after them, or only once NVDA has started."""
		nvda = self.nvda
		if version == "1.28":
			windows = self.backFromTaskbar()
		else:
			# Version 1.27 went back to Edge in the same way, and did nothing more.
			windows = Windows(self.computer, [TASKBAR, EDGE, NOTEPAD])
			startupFocus.atStart(windows)
			startupFocus.stop()
		self.assertEqual(windows.madeForeground, [EDGE])
		if helper == "with the focus":
			nvda.helperRegisters(PROCESS_EDGE)
		nvda.uiaFocusEvent()
		nvda.ia2FocusEvent()
		if helper == "after the focus":
			nvda.helperRegisters(PROCESS_EDGE)
		nvda.plugInsStarted()
		nvda.pump()
		if helper == "once NVDA started":
			self.timers.runAll(nvda, most=3)
			nvda.helperRegisters(PROCESS_EDGE)
		self.timers.runAll(nvda)
		nvda.pump()

	def assertFocusIs(self, kind, element):
		focus = self.nvda.focus
		self.assertIsInstance(focus, kind)
		self.assertIs(focus.IAccessibleObject if kind is self.nvda.IAccessibleObject else focus.UIAElement, element)

	def test_version127TookEdgeThroughUIAutomation(self):
		# The tester's log: "Adding new treeInterceptor to runningTable: <NVDAObjects.UIA.chromium.ChromiumUIATreeInterceptor".
		self.start(version="1.27")
		self.assertFocusIs(self.nvda.UIAObject, self.computer.messageBox)
		self.assertEqual(len(self.nvda.focusEvents()), 1)

	def test_version127AnyOrder(self):
		for helper in ("with the focus", "after the focus"):
			with self.subTest(helper=helper):
				self.setUp()
				self.start(helper=helper, version="1.27")
				self.assertIsInstance(self.nvda.focus, self.nvda.UIAObject)

	def test_edgeThroughIAccessible2(self):
		self.start()
		self.assertFocusIs(self.nvda.IAccessibleObject, self.computer.messageBox)
		self.assertEqual(self.nvda.focusEvents(), [self.nvda.focus], "NVDA says the message box once, as it starts")
		self.assertFalse(startupFocus.isFollowing(), "and there is nothing more to do")
		self.assertEqual(self.timers.waiting, [])

	def test_helperAfterTheFocusEvents(self):
		self.start(helper="after the focus")
		self.assertFocusIs(self.nvda.IAccessibleObject, self.computer.messageBox)
		self.assertEqual(len(self.nvda.focusEvents()), 1)

	def test_nvdasHalfSecondAnswer(self):
		# NVDA's first pump drops Edge's IAccessible2 focus event, and keeps "UI Automation" as its answer for Edge's
		# page for half a second, just before _setInitialFocus asks for the focus. Leaving out the UI Automation focus
		# event while NVDA starts isn't enough: were that answer kept, NVDA would take Edge through UI Automation still.
		class Kept(dict):
			def pop(self, key, default=None):
				return self.get(key, default)

		self.nvda.handler.UIAWindowHandleCache = Kept()
		self.start()
		self.assertFocusIs(self.nvda.UIAObject, self.computer.messageBox)
		self.assertEqual(len(self.nvda.focusEvents()), 1)

	def test_helperOnlyOnceNvdaStarted(self):
		# NVDA takes the focus through UI Automation as it starts, then again as it reads Edge once the helper is in.
		self.start(helper="once NVDA started")
		events = self.nvda.focusEvents()
		self.assertIsInstance(events[0], self.nvda.UIAObject)
		self.assertIsInstance(events[-1], self.nvda.IAccessibleObject)
		self.assertEqual(len(events), 2)
		self.assertFocusIs(self.nvda.IAccessibleObject, self.computer.messageBox)
		self.assertFalse(startupFocus.isFollowing())

	def test_edgesFocusEventJustAfterNvdaStarted(self):
		# Edge's UI Automation focus event comes once NVDA has started, before NVDA took the helper in: NVDA takes it
		# through UI Automation, and when it handles it, NVDA's executeEvent asks for its focusRedirect twice.
		self.backFromTaskbar()
		self.nvda.helperRegisters(PROCESS_EDGE)
		self.nvda.plugInsStarted()
		self.nvda.uiaFocusEvent()
		self.assertIsInstance(self.nvda.eventHandler.lastQueuedFocusObject, self.nvda.UIAObject)
		self.nvda.pump()
		self.timers.runAll(self.nvda)
		self.assertFocusIs(self.nvda.IAccessibleObject, self.computer.messageBox)
		self.assertEqual(len(self.nvda.focusEvents()), 1)

	def test_uiaFocusEventLeftOutWhileNvdaStarts(self):
		self.backFromTaskbar()
		self.nvda.uiaFocusEvent()
		self.assertIsNone(self.nvda.eventHandler.lastQueuedFocusObject, "NVDA finds the focus once it has started")
		self.nvda.starting = False
		self.nvda.uiaFocusEvent()
		self.assertIsInstance(self.nvda.eventHandler.lastQueuedFocusObject, self.nvda.UIAObject, "and takes the event after that")

	def test_edgeThroughUIAutomationByChoice(self):
		# "Use UI Automation to access Chromium based browser controls: Yes": NVDA's own choice stays.
		self.nvda.config["UIA"]["allowInChromium"] = 2
		self.start()
		self.assertFocusIs(self.nvda.UIAObject, self.computer.messageBox)
		self.assertFalse(startupFocus.isFollowing(), "the helper is in Edge: NVDA reads it through UI Automation")

	def test_notepadThroughUIAutomation(self):
		# Windows 11's Notepad, which NVDA reads through UI Automation: the focus there is NVDA's own.
		self.computer.windows[EDGE] = ("Notepad", PROCESS_NOTEPAD, None)
		self.computer.windows[EDGE_PAGE] = ("RichEditD2DPT", PROCESS_NOTEPAD, EDGE)
		self.computer.messageBox = self.computer.focusIn[EDGE_PAGE] = Element(PROCESS_NOTEPAD, EDGE_PAGE, "Text editor", Role.DOCUMENT, (State.EDITABLE,))
		windows = self.backFromTaskbar()
		self.assertEqual(windows.madeForeground, [EDGE])
		self.nvda.helperRegisters(PROCESS_NOTEPAD)
		self.nvda.uiaFocusEvent()
		self.nvda.plugInsStarted()
		self.nvda.pump()
		self.timers.runAll(self.nvda)
		self.assertFocusIs(self.nvda.UIAObject, self.computer.messageBox)
		self.assertEqual(len(self.nvda.focusEvents()), 1)
		self.assertFalse(startupFocus.isFollowing())

	def test_otherProgramsObjects(self):
		self.backFromTaskbar()
		clsList = [self.nvda.UIAObject]
		button = self.nvda.UIAObject(chooseBestAPI=False, UIAElement=self.computer.taskbarButton)
		self.assertNotIsInstance(button, startupFocus.overlayClass())
		startupFocus.chooseOverlay(button, clsList)
		self.assertEqual(clsList, [self.nvda.UIAObject])
		page = self.nvda.IAccessibleObject(windowHandle=EDGE_PAGE, IAccessibleObject=self.computer.page)
		clsList = [self.nvda.IAccessibleObject]
		startupFocus.chooseOverlay(page, clsList)
		self.assertEqual(clsList, [self.nvda.IAccessibleObject], "an IAccessible2 object is NVDA's own")

	def test_notWhenNvdaReloadsItsPlugins(self):
		self.nvda.starting = False
		windows = self.backFromTaskbar()
		self.assertEqual(windows.madeForeground, [])
		self.assertFalse(startupFocus.isFollowing())
		self.assertIsNone(self.plugin._startupFocus)

	def test_turnedOff(self):
		windows = self.backFromTaskbar(turnedOn=False)
		self.assertEqual(windows.madeForeground, [])
		self.assertIsNone(self.plugin._startupFocus)

	def test_theTimeIsUp(self):
		self.backFromTaskbar()
		self.nvda.starting = False
		startupFocus._until = 0
		self.assertTrue(startupFocus.followUp())
		self.assertFalse(startupFocus.isFollowing())

	def test_elsewhereMeanwhile(self):
		# The focus is in another program before NVDA took Edge's: NVDA waits for it.
		self.backFromTaskbar()
		self.nvda.starting = False
		self.nvda.focus = self.nvda.UIAObject(chooseBestAPI=False, UIAElement=self.computer.taskbarButton)
		self.assertFalse(startupFocus.followUp())
		self.assertTrue(startupFocus.isFollowing())

	def test_terminate(self):
		self.backFromTaskbar()
		self.assertTrue(self.timers.waiting)
		self.plugin._silenceExit = lambda: None
		self.plugin.updater = mock.Mock()
		self.plugin._menuItem = self.plugin._preferencesItem = None
		self.plugin.terminate()
		self.assertEqual(self.timers.waiting, [])
		self.assertFalse(startupFocus.isFollowing())
		self.assertIsNone(self.plugin._startupFocus)


# -- typing in the box -----------------------------------------------------------------------------------------------


class TypingEcho(enum.IntEnum):
	"""NVDA 2026.2's config.configFlags.TypingEcho, without its labels."""

	OFF = 0
	EDIT_CONTROLS = 1
	ALWAYS = 2


class TypingTests(unittest.TestCase):
	"""What NVDA says as the tester types "I have" in the message box, with NVDA's focus as his log shows it."""

	def type(self, focus, text):
		heard, logged = [], []

		class Log:
			IO = 12

			def isEnabledFor(self, level):
				return True

			def io(self, message):
				logged.append(message)

		controlTypes = types.SimpleNamespace(
			ROLE_EDITABLETEXT=Role.EDITABLETEXT,
			ROLE_DOCUMENT=Role.DOCUMENT,
			ROLE_TERMINAL=Role.TERMINAL,
			STATE_EDITABLE=State.EDITABLE,
			STATE_READONLY=State.READONLY,
		)
		namespace = {
			"api": types.SimpleNamespace(getFocusObject=lambda: focus, isTypingProtected=lambda: False),
			"config": types.SimpleNamespace(conf={"keyboard": {"speakTypedCharacters": 1, "speakTypedWords": 0}}),
			"controlTypes": controlTypes,
			"log": Log(),
			"TypingEcho": TypingEcho,
			"_curWordChars": [],
			"_speechState": types.SimpleNamespace(_suppressSpeakTypedCharactersNumber=0, _suppressSpeakTypedCharactersTime=None),
			"speakSpelling": heard.append,
			"speakText": heard.append,
			"time": None,
			"unicodedata": unicodedata,
		}
		speakTypedCharacters = nvdaCode(NVDA_TYPED_CHARACTERS, "speakTypedCharacters", namespace)
		for character in text:
			speakTypedCharacters(character)
		return heard, logged

	def test_thePageAsTheFocus(self):
		# The tester's log: "typed word: I", then "typed word: have", and no "Speaking" line.
		page = types.SimpleNamespace(role=Role.DOCUMENT, states={State.READONLY, State.FOCUSED})
		heard, logged = self.type(page, "I have ")
		self.assertEqual(heard, [])
		self.assertEqual(logged, ["typed word: I", "typed word: have"])

	def test_theMessageBoxAsTheFocus(self):
		box = types.SimpleNamespace(role=Role.EDITABLETEXT, states={State.EDITABLE, State.FOCUSED})
		heard, logged = self.type(box, "I have ")
		self.assertEqual(heard, list("I have "))


# -- NVDA's own code, as this test has it ----------------------------------------------------------------------------


class NvdasOwnCodeTests(unittest.TestCase):
	def test_theConstantsAreNvdas(self):
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


if __name__ == "__main__":
	unittest.main()
