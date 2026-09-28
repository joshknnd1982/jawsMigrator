# Unit tests for version 1.38, from a tester's issue 36, "possible issue": "This may be tied to insert shift j and k
# check the log. is it user error or is there a problem?" The tester pressed NVDA+Shift+J, then K, then (meaning
# Insert+Space) a key NVDA logged as Space, and then NVDA+Shift+J, then H. As the Speech History window opened, NVDA
# said "Speech History, dialog" and then the whole history, the oldest first, one typed letter after another:
# "space, h, e, a, r, period, ...". Their older log shows the same with the update dialog: NVDA said all of 1.36's
# release notes as it opened. NVDA says the text of a dialog's static texts and read-only one-line fields as the
# dialog's own (behaviors.Dialog.getDialogText); a field of several lines is left out by its "multi line" state.
# Both boxes are Win32 text fields of several lines (wx.TE_MULTILINE), and they had no "multi line".
# - documentPolling (1.15) decides, in Enhanced Control Support's choice of whether a control gets its timer, whether
#   it is a document or a multi-line text field NVDA follows itself. It read the object's states there, while NVDA was
#   still making the object (DynamicNVDAObjectType.__call__, chooseNVDAObjectOverlayClasses), before the object had
#   the classes NVDA gives it. NVDA keeps a property's value until the end of the core cycle, under the function that
#   worked it out (AutoPropertyObject._getPropertyViaCache): IAccessible._get_states, which takes what the classes
#   after it say (super().states), and NVDA's EditBase, which says "multi line" for the ES_MULTILINE style, is one of
#   them only once the object has its classes. So the states NVDA went on using had no "multi line", and Enhanced
#   Control Support kept its timer on those fields too. Now the assistant tells a Win32 text field of several lines by
#   its window style, as EditBase will, and leaves the object's cache as it found it.
# NVDA 2026.2's own code runs here, word for word: baseObject's Getter, CachingGetter, AutoPropertyType and
# AutoPropertyObject (the property cache), DynamicNVDAObjectType.__call__ (making an object and choosing its classes),
# NVDAObject._get_states, Window._get_states and _get_windowStyle, EditBase, the start of IAccessible._get_states (all
# of it for an object that isn't IAccessible2), and behaviors.Dialog, with getDialogText. So is Enhanced Control
# Support 1.2.2's own shouldUseTimerMixin and TimerMixin.initOverlayClass, which reads the states once the object has
# its classes, and Control Usage Assistant's choice of classes, which the tester's objects had too. What is imitated:
# the windows (their class names, roles, states, styles and text, as Windows gives them for the tester's dialogs),
# how IAccessible and Window choose their classes for them, and the rest of Enhanced Control Support's choice, which
# makes no other change for these windows. The assistant's documentPolling is the real one.
# Run: python -m unittest tests.test_v138_dialogText -v

import __future__
import enum
import os
import sys
import types
import typing
import unittest
import weakref
from abc import ABCMeta, abstractproperty
from typing import Any, Callable, Optional, Set, Union
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import documentPolling  # noqa: E402

MODULE = "globalPlugins.enhancedControlSupport"

# Enhanced Control Support 1.2.2's code, and NVDA 2026.2's, word for word (NvdasOwnCodeTests checks them).
NVDA_BASE_OBJECT = 'class Getter(object):\n\tdef __init__(self, fget, abstract=False):\n\t\tself.fget = fget\n\t\tif abstract:\n\t\t\tself._abstract = self.__isabstractmethod__ = abstract\n\n\tdef __get__(\n\t\tself,\n\t\tinstance: Union[Any, None, "AutoPropertyObject"],\n\t\towner,\n\t) -> Union[GetterReturnT, "Getter"]:\n\t\tif isinstance(self.fget, classmethod):\n\t\t\treturn self.fget.__get__(instance, owner)()\n\t\telif instance is None:\n\t\t\treturn self\n\t\treturn self.fget(instance)\n\n\tdef setter(self, func):\n\t\treturn (abstractproperty if self._abstract else property)(fget=self.fget, fset=func)\n\n\tdef deleter(self, func):\n\t\treturn (abstractproperty if self._abstract else property)(fget=self.fget, fdel=func)\n\n\nclass CachingGetter(Getter):\n\tdef __get__(\n\t\tself,\n\t\tinstance: Union[Any, None, "AutoPropertyObject"],\n\t\towner,\n\t) -> Union[GetterReturnT, "CachingGetter"]:\n\t\tif isinstance(self.fget, classmethod):\n\t\t\tlog.warning("Class properties do not support caching")\n\t\t\treturn self.fget.__get__(instance, owner)()\n\t\telif instance is None:\n\t\t\treturn self\n\t\treturn instance._getPropertyViaCache(self.fget)\n\n\nclass AutoPropertyType(ABCMeta):\n\tdef __init__(self, name: str, bases: tuple[type, ...], namespace: dict[str, Any], /, **kwargs: Any):\n\t\tsuper().__init__(name, bases, namespace, **kwargs)\n\n\t\tcacheByDefault = False\n\t\ttry:\n\t\t\tcacheByDefault = namespace["cachePropertiesByDefault"]\n\t\texcept KeyError:\n\t\t\tcacheByDefault = any(getattr(base, "cachePropertiesByDefault", False) for base in bases)\n\n\t\t# Create a set containing properties that are marked as abstract.\n\t\tnewAbstractProps = set()\n\t\t# Create a set containing properties that were, but are no longer abstract.\n\t\toldAbstractProps = set()\n\t\t# given _get_myVal, _set_myVal, and _del_myVal: "myVal" would be output 3 times\n\t\t# use a set comprehension to ensure unique values, "myVal" only needs to occur once.\n\t\tprops = {x[5:] for x in namespace.keys() if x[0:5] in ("_get_", "_set_", "_del_")}\n\t\tfor x in props:\n\t\t\tg = namespace.get("_get_%s" % x, None)\n\t\t\ts = namespace.get("_set_%s" % x, None)\n\t\t\td = namespace.get("_del_%s" % x, None)\n\t\t\tif x in namespace:\n\t\t\t\tmethodsString = ",".join(str(i) for i in (g, s, d) if i)\n\t\t\t\traise TypeError(\n\t\t\t\t\t"%s is already a class attribute, cannot create descriptor with methods %s"\n\t\t\t\t\t% (x, methodsString),\n\t\t\t\t)\n\t\t\tif not g:\n\t\t\t\t# There\'s a setter or deleter, but no getter.\n\t\t\t\t# This means it could be in one of the base classes.\n\t\t\t\tfor base in bases:\n\t\t\t\t\tg = getattr(base, "_get_%s" % x, None)\n\t\t\t\t\tif g:\n\t\t\t\t\t\tbreak\n\n\t\t\tcache = namespace.get("_cache_%s" % x, None)\n\t\t\tif cache is None:\n\t\t\t\t# The cache setting hasn\'t been specified in this class, but it could be in one of the bases.\n\t\t\t\tfor base in bases:\n\t\t\t\t\tcache = getattr(base, "_cache_%s" % x, None)\n\t\t\t\t\tif cache is not None:\n\t\t\t\t\t\tbreak\n\t\t\t\telse:\n\t\t\t\t\tcache = cacheByDefault if not isinstance(g, classmethod) else False\n\n\t\t\tabstract = namespace.get("_abstract_%s" % x, False)\n\t\t\tif g and not (s or d):\n\t\t\t\tattr = (CachingGetter if cache else Getter)(g, abstract)\n\t\t\telse:\n\t\t\t\tattr = (abstractproperty if abstract else property)(fget=g, fset=s, fdel=d)\n\t\t\tif abstract:\n\t\t\t\tnewAbstractProps.add(x)\n\t\t\telif x in self.__abstractmethods__:\n\t\t\t\toldAbstractProps.add(x)\n\t\t\tsetattr(self, x, attr)\n\n\t\tif newAbstractProps or oldAbstractProps:\n\t\t\t# The __abstractmethods__ set is frozen, therefore we ought to override it.\n\t\t\tself.__abstractmethods__ = (self.__abstractmethods__ | newAbstractProps) - oldAbstractProps\n\n\nclass AutoPropertyObject(garbageHandler.TrackedObject, metaclass=AutoPropertyType):\n\t"""A class that dynamically supports properties, by looking up _get_*, _set_*, and _del_* methods at runtime.\n\t_get_x will make property x with a getter (you can get its value).\n\t_set_x will make a property x with a setter (you can set its value).\n\t_del_x will make a property x with a deleter that is executed when deleting its value.\n\tIf there is a _get_x but no _set_x then setting x will override the property completely.\n\tProperties can also be cached for the duration of one core pump cycle.\n\tThis is useful if the same property is likely to be fetched multiple times in one cycle.\n\tFor example, several NVDAObject properties are fetched by both braille and speech.\n\tSetting _cache_x to C{True} specifies that x should be cached.\n\tSetting it to C{False} specifies that it should not be cached.\n\tIf _cache_x is not set, L{cachePropertiesByDefault} is used.\n\tProperties can also be made abstract.\n\tSetting _abstract_x to C{True} specifies that x should be abstract.\n\tSetting it to C{False} specifies that it should not be abstract.\n\t"""\n\n\t#: Tracks the instances of this class; used by L{invalidateCaches}.\n\t#: @type: weakref.WeakKeyDictionary\n\t__instances = weakref.WeakKeyDictionary()\n\t#: Specifies whether properties are cached by default;\n\t#: can be overridden for individual properties by setting _cache_propertyName.\n\t#: @type: bool\n\tcachePropertiesByDefault = False\n\n\t_propertyCache: Set[GetterMethodT]\n\n\tdef __new__(cls, *args, **kwargs):\n\t\tself = super(AutoPropertyObject, cls).__new__(cls)\n\t\t#: Maps properties to cached values.\n\t\t#: @type: dict\n\t\tself._propertyCache = {}\n\t\tself.__instances[self] = None\n\t\treturn self\n\n\tdef _getPropertyViaCache(self, getterMethod: Optional[GetterMethodT] = None) -> GetterReturnT:\n\t\tif not getterMethod:\n\t\t\traise ValueError("getterMethod is None")\n\t\tmissing = False\n\t\ttry:\n\t\t\tval = self._propertyCache[getterMethod]\n\t\texcept KeyError:\n\t\t\tmissing = True\n\t\tif missing:\n\t\t\tval = getterMethod(self)\n\t\t\tself._propertyCache[getterMethod] = val\n\t\treturn val\n\n\tdef invalidateCache(self):\n\t\tself._propertyCache.clear()\n\n\t@classmethod\n\tdef invalidateCaches(cls):\n\t\t"""Invalidate the caches for all current instances."""\n\t\t# We use a list here, as invalidating the cache on an object may cause instances to disappear,\n\t\t# which would in turn cause an exception due to the dictionary changing size during iteration.\n\t\tfor instance in list(cls.__instances):\n\t\t\tinstance.invalidateCache()\n'

NVDA_DYNAMIC_CALL = '\tdef __call__(self, chooseBestAPI=True, **kwargs):\n\t\tif chooseBestAPI:\n\t\t\tAPIClass = self.findBestAPIClass(kwargs)\n\t\t\tif not APIClass:\n\t\t\t\treturn None\n\t\telse:\n\t\t\tAPIClass = self\n\n\t\t# Instantiate the requested class.\n\t\ttry:\n\t\t\tobj = APIClass.__new__(APIClass, **kwargs)\n\t\t\tobj.APIClass = APIClass\n\t\t\tif isinstance(obj, self):\n\t\t\t\tobj.__init__(**kwargs)\n\t\texcept InvalidNVDAObject as e:\n\t\t\tlog.debugWarning("Invalid NVDAObject: %s" % e, exc_info=True)\n\t\t\treturn None\n\n\t\tclsList = []\n\t\tif "findOverlayClasses" in APIClass.__dict__:\n\t\t\tobj.findOverlayClasses(clsList)\n\t\telse:\n\t\t\tclsList.append(APIClass)\n\t\t# Allow app modules to choose overlay classes.\n\t\tappModule = obj.appModule\n\t\t# optimisation: The base implementation of chooseNVDAObjectOverlayClasses does nothing,\n\t\t# so only call this method if it\'s been overridden.\n\t\tif appModule and not hasattr(appModule.chooseNVDAObjectOverlayClasses, "_isBase"):\n\t\t\ttry:\n\t\t\t\tappModule.chooseNVDAObjectOverlayClasses(obj, clsList)\n\t\t\texcept Exception:\n\t\t\t\tlog.exception(f"Exception in chooseNVDAObjectOverlayClasses for {appModule}")\n\t\t\t\tpass\n\n\t\t# Allow global plugins to choose overlay classes.\n\t\tfor plugin in globalPluginHandler.runningPlugins:\n\t\t\tif "chooseNVDAObjectOverlayClasses" in plugin.__class__.__dict__:\n\t\t\t\ttry:\n\t\t\t\t\tplugin.chooseNVDAObjectOverlayClasses(obj, clsList)\n\t\t\t\texcept Exception:\n\t\t\t\t\tlog.exception(f"Exception in chooseNVDAObjectOverlayClasses for {plugin}")\n\t\t\t\t\tpass\n\n\t\t# After all other mutation has finished,\n\t\t# add LockScreenObject if Windows is locked.\n\t\t# LockScreenObject must become the first class to be resolved,\n\t\t# i.e. insertion order of 0.\n\t\tself._insertLockScreenObject(clsList)\n\n\t\t# Determine the bases for the new class.\n\t\tbases = []\n\t\tfor index in range(len(clsList)):\n\t\t\t# A class doesn\'t need to be a base if it is already implicitly included by being a superclass of a previous base.\n\t\t\tif index == 0 or not issubclass(clsList[index - 1], clsList[index]):\n\t\t\t\tbases.append(clsList[index])\n\n\t\t# Construct the new class.\n\t\tif len(bases) == 1:\n\t\t\t# We only have one base, so there\'s no point in creating a dynamic type.\n\t\t\tnewCls = bases[0]\n\t\telse:\n\t\t\tbases = tuple(bases)\n\t\t\tnewCls = self._dynamicClassCache.get(bases, None)\n\t\t\tif not newCls:\n\t\t\t\tname = "Dynamic_%s" % "".join([x.__name__ for x in clsList])\n\t\t\t\tnewCls = type(name, bases, {"__module__": __name__})\n\t\t\t\tself._dynamicClassCache[bases] = newCls\n\n\t\toldMro = frozenset(obj.__class__.__mro__)\n\t\t# Mutate obj into the new class.\n\t\tobj.__class__ = newCls\n\n\t\t# Initialise the overlay classes.\n\t\tfor cls in reversed(newCls.__mro__):\n\t\t\tif cls in oldMro:\n\t\t\t\t# This class was part of the initially constructed object, so its constructor would have been called.\n\t\t\t\tcontinue\n\t\t\tinitFunc = cls.__dict__.get("initOverlayClass")\n\t\t\tif initFunc:\n\t\t\t\ttry:\n\t\t\t\t\tinitFunc(obj)\n\t\t\t\texcept Exception:\n\t\t\t\t\tlog.exception(f"Exception in initOverlayClass for {cls}")\n\t\t\t\t\tcontinue\n\t\t\t# Bind gestures specified on the class.\n\t\t\ttry:\n\t\t\t\tobj.bindGestures(getattr(cls, "_%s__gestures" % cls.__name__))\n\t\t\texcept AttributeError:\n\t\t\t\tpass\n\n\t\t# Allow app modules to make minor tweaks to the instance.\n\t\tif appModule and hasattr(appModule, "event_NVDAObject_init"):\n\t\t\ttry:\n\t\t\t\tappModule.event_NVDAObject_init(obj)\n\t\t\texcept Exception:\n\t\t\t\tlog.exception(f"Exception in event_NVDAObject_init for {appModule}")\n\t\t\t\tpass\n\n\t\treturn obj\n'

NVDA_OBJECT_STATES = '\tdef _get_states(self) -> typing.Set[controlTypes.State]:\n\t\t"""Retrieves the current states of this object (example: selected, focused).\n\t\t@return: a set of State constants from L{controlTypes}.\n\t\t"""\n\t\treturn set()\n'

NVDA_DIALOG = 'class Dialog(NVDAObject):\n\t"""Overrides the description property to obtain dialog text."""\n\n\t@classmethod\n\tdef getDialogText(cls, obj, allowFocusedDescendants=True):\n\t\t"""This classmethod walks through the children of the given object, and collects up and returns any text that seems to be  part of a dialog\'s message text.\n\t\t@param obj: the object who\'s children you want to collect the text from\n\t\t@type obj: L{IAccessible}\n\t\t@param allowFocusedDescendants: if false no text will be returned at all if one of the descendants is focused.\n\t\t@type allowFocusedDescendants: boolean\n\t\t"""\n\t\tchildren = obj.children\n\t\ttextList = []\n\t\tchildCount = len(children)\n\t\tfor index in range(childCount):\n\t\t\tchild = children[index]\n\t\t\tchildStates = child.states\n\t\t\tchildRole = child.role\n\t\t\t# We don\'t want to handle invisible or unavailable objects\n\t\t\tif controlTypes.State.INVISIBLE in childStates or controlTypes.State.UNAVAILABLE in childStates:\n\t\t\t\tcontinue\n\t\t\t# For particular objects, we want to descend in to them and get their children\'s message text\n\t\t\tif childRole in (\n\t\t\t\tcontrolTypes.Role.OPTIONPANE,\n\t\t\t\tcontrolTypes.Role.PROPERTYPAGE,\n\t\t\t\tcontrolTypes.Role.PANE,\n\t\t\t\tcontrolTypes.Role.PANEL,\n\t\t\t\tcontrolTypes.Role.WINDOW,\n\t\t\t\tcontrolTypes.Role.GROUPING,\n\t\t\t\tcontrolTypes.Role.PARAGRAPH,\n\t\t\t\tcontrolTypes.Role.SECTION,\n\t\t\t\tcontrolTypes.Role.TEXTFRAME,\n\t\t\t\tcontrolTypes.Role.UNKNOWN,\n\t\t\t):\n\t\t\t\t# Grab text from descendants, but not for a child which inherits from Dialog and has focusable descendants\n\t\t\t\t# Stops double reporting when focus is in a property page in a dialog\n\t\t\t\tchildText = cls.getDialogText(child, not isinstance(child, Dialog))\n\t\t\t\tif childText:\n\t\t\t\t\ttextList.append(childText)\n\t\t\t\telif childText is None:\n\t\t\t\t\treturn None\n\t\t\t\tcontinue\n\t\t\t# If the child is focused  we should just stop and return None\n\t\t\tif not allowFocusedDescendants and controlTypes.State.FOCUSED in child.states:\n\t\t\t\treturn None\n\t\t\t# We only want text from certain controls.\n\t\t\tif not (\n\t\t\t\t# Static text, labels and links\n\t\t\t\tchildRole in (controlTypes.Role.STATICTEXT, controlTypes.Role.LABEL, controlTypes.Role.LINK)\n\t\t\t\t# Read-only, non-multiline edit fields\n\t\t\t\tor (\n\t\t\t\t\tchildRole == controlTypes.Role.EDITABLETEXT\n\t\t\t\t\tand controlTypes.State.READONLY in childStates\n\t\t\t\t\tand controlTypes.State.MULTILINE not in childStates\n\t\t\t\t)\n\t\t\t):\n\t\t\t\tcontinue\n\t\t\t# We should ignore a text object directly after a grouping object, as it\'s probably the grouping\'s description\n\t\t\tif index > 0 and children[index - 1].role == controlTypes.Role.GROUPING:\n\t\t\t\tcontinue\n\t\t\t# Like the last one, but a graphic might be before the grouping\'s description\n\t\t\tif (\n\t\t\t\tindex > 1\n\t\t\t\tand children[index - 1].role == controlTypes.Role.GRAPHIC\n\t\t\t\tand children[index - 2].role == controlTypes.Role.GROUPING\n\t\t\t):\n\t\t\t\tcontinue\n\t\t\tchildName = child.name\n\t\t\tif (\n\t\t\t\tchildName\n\t\t\t\tand index < (childCount - 1)\n\t\t\t\tand children[index + 1].role\n\t\t\t\tnot in (\n\t\t\t\t\tcontrolTypes.Role.GRAPHIC,\n\t\t\t\t\tcontrolTypes.Role.STATICTEXT,\n\t\t\t\t\tcontrolTypes.Role.SEPARATOR,\n\t\t\t\t\tcontrolTypes.Role.WINDOW,\n\t\t\t\t\tcontrolTypes.Role.PANE,\n\t\t\t\t\tcontrolTypes.Role.BUTTON,\n\t\t\t\t)\n\t\t\t\tand children[index + 1].name == childName\n\t\t\t):\n\t\t\t\t# This is almost certainly the label for the next object, so skip it.\n\t\t\t\tcontinue\n\t\t\tisNameIncluded = child.TextInfo is NVDAObjectTextInfo or childRole in (\n\t\t\t\tcontrolTypes.Role.LABEL,\n\t\t\t\tcontrolTypes.Role.STATICTEXT,\n\t\t\t)\n\t\t\tchildText = child.makeTextInfo(textInfos.POSITION_ALL).text\n\t\t\tif not childText or childText.isspace() and child.TextInfo is not NVDAObjectTextInfo:\n\t\t\t\tchildText = child.basicText\n\t\t\t\tisNameIncluded = True\n\t\t\tif not isNameIncluded:\n\t\t\t\t# The label isn\'t in the text, so explicitly include it first.\n\t\t\t\tif childName:\n\t\t\t\t\ttextList.append(childName)\n\t\t\tif childText:\n\t\t\t\ttextList.append(childText)\n\t\treturn "\\n".join(textList)\n\n\tdef _get_description(self):\n\t\tsuperDesc = super(Dialog, self).description\n\t\tif superDesc and not superDesc.isspace():\n\t\t\t# The object already provides a useful description, so don\'t override it.\n\t\t\treturn superDesc\n\t\treturn self.getDialogText(self)\n\n\tvalue = None\n'

NVDA_WINDOW_STATES = '\tdef _get_states(self):\n\t\tstates = super(Window, self)._get_states()\n\t\tstyle = self.windowStyle\n\t\tif not style & winUser.WS_VISIBLE:\n\t\t\tstates.add(controlTypes.State.INVISIBLE)\n\t\tif style & winUser.WS_DISABLED:\n\t\t\tstates.add(controlTypes.State.UNAVAILABLE)\n\t\treturn states\n\n\tdef _get_windowStyle(self):\n\t\treturn winUser.getWindowStyle(self.windowHandle)\n'

NVDA_EDIT_BASE = 'class EditBase(Window):\n\t""" "Base class for Edit and Rich Edit controls, shared by legacy and UIA implementations."""\n\n\tdef _get_value(self):\n\t\treturn None\n\n\tdef _get_role(self):\n\t\treturn controlTypes.Role.EDITABLETEXT\n\n\tdef _get_states(self):\n\t\tstates = super()._get_states()\n\t\tif self.windowStyle & winUser.ES_MULTILINE:\n\t\t\tstates.add(controlTypes.State.MULTILINE)\n\t\treturn states\n'

NVDA_IACCESSIBLE_STATES = '\tdef _get_states(self) -> set[controlTypes.State]:  # noqa: C901\n\t\tstates = set()\n\t\tif self.event_objectID in (winUser.OBJID_CLIENT, winUser.OBJID_WINDOW) and self.event_childID == 0:\n\t\t\tstates.update(super().states)\n\t\ttry:\n\t\t\tIAccessibleStates = self.IAccessibleStates\n\t\texcept COMError:\n\t\t\tlog.debugWarning("could not get IAccessible states", exc_info=True)\n\t\telse:\n\t\t\tstates.update(\n\t\t\t\tIAccessibleHandler.calculateNvdaStates(self.IAccessibleRole, IAccessibleStates),\n\t\t\t)\n\n\t\tif not isinstance(self.IAccessibleObject, IA2.IAccessible2):\n\t\t\t# Not an IA2 object.\n\t\t\treturn states\n'

ECS_SHOULD_USE_TIMER_MIXIN = 'def shouldUseTimerMixin(conf, obj, clsList):\n\n\tfor i in clsList:\n\t\tif issubclass(i, Complex) or (issubclass(i, Win32) and not conf):\n\t\t\treturn(True)\n\tif conf and not conf[1]:\n\t\treturn(True)\n\tif not config.conf["enhancedControlSupport"]["trustEvents"]:\n\t\treturn(True)\n\treturn(False)\n'

ECS_TIMER_MIXIN_INIT = '\tdef initOverlayClass(self):\n\t\tself.staticName = self.name\n\t\tself.staticValue = self.value\n\t\tself.staticStates = self.states\n\t\ttry:\n\t\t\tself.staticCaret = self.makeTextInfo(textInfos.POSITION_CARET)\n\t\texcept:\n\t\t\tpass\n'

# Where NVDA_SOURCE (NVDA 2026.2's source folder) has each piece.
NVDA_FILES = {
	"NVDA_BASE_OBJECT": ("baseObject.py",),
	"NVDA_DYNAMIC_CALL": ("NVDAObjects", "__init__.py"),
	"NVDA_OBJECT_STATES": ("NVDAObjects", "__init__.py"),
	"NVDA_DIALOG": ("NVDAObjects", "behaviors.py"),
	"NVDA_WINDOW_STATES": ("NVDAObjects", "window", "__init__.py"),
	"NVDA_EDIT_BASE": ("NVDAObjects", "window", "edit.py"),
	"NVDA_IACCESSIBLE_STATES": ("NVDAObjects", "IAccessible", "__init__.py"),
}
# Where ECS_SOURCE (Enhanced Control Support 1.2.2's folder) has each piece.
ECS_FILES = {
	"ECS_SHOULD_USE_TIMER_MIXIN": ("addon", "globalPlugins", "enhancedControlSupport", "__init__.py"),
	"ECS_TIMER_MIXIN_INIT": ("addon", "globalPlugins", "enhancedControlSupport", "__init__.py"),
}


class Role(enum.Enum):
	UNKNOWN = "unknown"
	WINDOW = "window"
	DIALOG = "dialog"
	STATICTEXT = "static text"
	LABEL = "label"
	LINK = "link"
	EDITABLETEXT = "edit"
	BUTTON = "button"
	GRAPHIC = "graphic"
	SEPARATOR = "separator"
	PANE = "pane"
	PANEL = "panel"
	GROUPING = "grouping"
	OPTIONPANE = "option pane"
	PROPERTYPAGE = "property page"
	PARAGRAPH = "paragraph"
	SECTION = "section"
	TEXTFRAME = "text frame"
	DOCUMENT = "document"


class State(enum.Enum):
	INVISIBLE = "invisible"
	UNAVAILABLE = "unavailable"
	FOCUSED = "focused"
	FOCUSABLE = "focusable"
	READONLY = "read only"
	MULTILINE = "multi line"


WS_VISIBLE = 0x10000000
ES_MULTILINE = 0x0004
OBJID_CLIENT = -4


class FakeWindow:
	"""A window as Windows gives it: its class, and its role and states through MSAA (as NVDA's states), its style,
	name and text."""

	def __init__(self, className, role, states=(State.FOCUSABLE,), style=WS_VISIBLE, name=None, text="", children=()):
		self.className, self.role, self.states, self.style = className, role, set(states), style
		self.name, self.text, self.children = name, text, tuple(children)


# The tester's Speech History, from its start and its end in their log (issue 36), with NVDA's line breaks.
HISTORY = (
	"space\r\nh\r\ne\r\na\r\nr\r\nperiod\r\nspace\r\nspace\r\nL\r\nL\r\no\r\no\r\nk\r\nspace\r\na\r\nt\r\nspace\r\nt\r\nh"
	"\r\ne\r\nspace\r\nl\r\no\r\ng\r\nperiod\r\nspace\r\nspace\r\nI\r\nI\r\nspace\r\nc\r\na\r\nn\r\napostrophe\r\nt\r\n"
	"space\r\nf\r\ni\r\nn\r\nd\r\nspace\r\nt\r\nh\r\ne\r\nspace\r\ns\r\ne\r\nt\r\nt\r\ni\r\nn\r\ng\r\ns\r\nspace\r\nb\r\n"
	"u\r\nt\r\nspace\r\nt\r\nh\r\na\r\nt\r\nspace\r\ni\r\ns\r\nspace\r\ns\r\ne\r\nc\r\no\r\nn\r\nd\r\na\r\nr\r\ny\r\n"
	"period\r\nPaste, drop, or click to add files  button\r\nInbox - Outlook - Outlook\r\n"
	"Press a JAWS 2026 (2026.2606.132.400) keystroke to hear what it does in NVDA, or Escape to cancel.\r\n"
	"In JAWS, Space runs Virtual Spacebar. NVDA has no command that does the same. In NVDA, space has no command of its own."
)
SUMMARY = "JAWS Migration Assistant 1.36 is available. You have version 1.35."
NOTES = (
	"JAWS Migration Assistant 1.36\r\n\r\nFrom the tester's reports on 1.35: going back on a website (#32), the layer's "
	"commands (#33), Insert+Q (#34), and JAWS and NVDA side by side on several sites (#35)."
)
ADDRESS = "https://github.com/joshknnd1982/jawsMigrator/issues/36"

# The assistant's Speech History window (speechHistory.SpeechHistoryViewer): its text box has no label.
SPEECH_HISTORY_WINDOW = {
	100: FakeWindow("#32770", Role.DIALOG, name="Speech History", children=(101, 102, 103, 104)),
	101: FakeWindow("Edit", Role.EDITABLETEXT, (State.FOCUSABLE, State.FOCUSED, State.READONLY), WS_VISIBLE | ES_MULTILINE, text=HISTORY),
	102: FakeWindow("Button", Role.BUTTON, name="Copy all"),
	103: FakeWindow("Button", Role.BUTTON, name="Clear"),
	104: FakeWindow("Button", Role.BUTTON, name="Close"),
}
# The assistant's update dialog (gui.updateDialog.UpdateOfferDialog), as the tester's older log has it.
UPDATE_DIALOG = {
	200: FakeWindow("#32770", Role.DIALOG, name="JAWS Migration Assistant update", children=(201, 202, 203, 204, 205)),
	201: FakeWindow("Static", Role.STATICTEXT, (), name=SUMMARY),
	202: FakeWindow("Static", Role.STATICTEXT, (), name="What's new:"),
	203: FakeWindow("Edit", Role.EDITABLETEXT, (State.FOCUSABLE, State.FOCUSED, State.READONLY), WS_VISIBLE | ES_MULTILINE, "What's new:", NOTES),
	204: FakeWindow("Button", Role.BUTTON, name="Download and install"),
	205: FakeWindow("Button", Role.BUTTON, name="Close"),
}
# A dialog with a read-only field of one line, whose text NVDA says as the dialog's own.
ONE_LINE_DIALOG = {
	300: FakeWindow("#32770", Role.DIALOG, name="Link address", children=(301, 302, 303)),
	301: FakeWindow("Static", Role.STATICTEXT, (), name="Address:"),
	302: FakeWindow("Edit", Role.EDITABLETEXT, (State.FOCUSABLE, State.READONLY), WS_VISIBLE, "Address:", ADDRESS),
	303: FakeWindow("Button", Role.BUTTON, name="OK"),
}

# What is imitated: NVDA's objects as far as these tests go, around NVDA's own code above.
IMITATED_NVDA = (
	"class DynamicNVDAObjectType(AutoPropertyType):\n"
	"\t_dynamicClassCache = {}\n"
	"\n" + NVDA_DYNAMIC_CALL + "\n"
	"\tdef _insertLockScreenObject(self, clsList):\n"
	"\t\t# Windows isn't locked.\n"
	"\t\tpass\n"
	"\n"
	"\n"
	"class NVDAObjectTextInfo:\n"
	"\tdef __init__(self, obj, position):\n"
	"\t\tself.text = obj.basicText\n"
	"\n"
	"\n"
	"class EditTextInfo:\n"
	"\t# All of a Win32 text field's text, or the line at its caret (the last).\n"
	"\tdef __init__(self, obj, position):\n"
	"\t\ttext = windows[obj.windowHandle].text\n"
	"\t\tself.text = text if position == textInfos.POSITION_ALL else text.split('\\r\\n')[-1]\n"
	"\n"
	"\n"
	"class NVDAObject(AutoPropertyObject, metaclass=DynamicNVDAObjectType):\n"
	"\tcachePropertiesByDefault = True\n"
	"\tTextInfo = NVDAObjectTextInfo\n"
	"\tappModule = None\n"
	"\n"
	"\tdef findOverlayClasses(self, clsList):\n"
	"\t\tclsList.append(NVDAObject)\n"
	"\n"
	"\tdef _get_name(self):\n"
	"\t\treturn windows[self.windowHandle].name\n"
	"\n"
	"\tdef _get_role(self):\n"
	"\t\treturn controlTypes.Role.UNKNOWN\n"
	"\n"
	"\tdef _get_value(self):\n"
	"\t\treturn None\n"
	"\n"
	"\tdef _get_description(self):\n"
	"\t\treturn ''\n"
	"\n"
	"\tdef _get_basicText(self):\n"
	"\t\treturn self.name or ''\n"
	"\n"
	"\tdef _get_children(self):\n"
	"\t\treturn []\n"
	"\n"
	"\tdef makeTextInfo(self, position):\n"
	"\t\treturn self.TextInfo(self, position)\n"
	"\n" + NVDA_OBJECT_STATES + "\n"
	"\n" + NVDA_DIALOG + "\n"
	"\n"
	"class Window(NVDAObject):\n"
	"\tdef __init__(self, windowHandle=None):\n"
	"\t\tself.windowHandle = windowHandle\n"
	"\n"
	"\tdef findOverlayClasses(self, clsList):\n"
	"\t\t# Window.findOverlayClasses, for these window classes.\n"
	"\t\tif self.windowClassName == 'Edit':\n"
	"\t\t\tclsList.append(Edit)\n"
	"\t\tclsList.append(Window)\n"
	"\t\tsuper(Window, self).findOverlayClasses(clsList)\n"
	"\n"
	"\tdef _get_windowClassName(self):\n"
	"\t\treturn windows[self.windowHandle].className\n"
	"\n" + NVDA_WINDOW_STATES + "\n"
	"\n" + NVDA_EDIT_BASE + "\n"
	"\n"
	"class EditableText:\n"
	"\tpass\n"
	"\n"
	"\n"
	"class Edit(EditableText, EditBase):\n"
	"\tTextInfo = EditTextInfo\n"
	"\n"
	"\n"
	"class IAccessible(Window):\n"
	"\tdef __init__(self, windowHandle=None, event_objectID=None, event_childID=None):\n"
	"\t\tself.IAccessibleObject = object()\n"
	"\t\tself.event_windowHandle = windowHandle\n"
	"\t\tself.event_objectID = event_objectID\n"
	"\t\tself.event_childID = event_childID\n"
	"\t\tsuper(IAccessible, self).__init__(windowHandle=windowHandle)\n"
	"\n"
	"\t@classmethod\n"
	"\tdef kwargsFromSuper(cls, kwargs, relation=None):\n"
	"\t\treturn True\n"
	"\n"
	"\tdef findOverlayClasses(self, clsList):\n"
	"\t\t# The end of IAccessible.findOverlayClasses. Dialog comes from its map of window classes and roles.\n"
	"\t\tif self.windowClassName == '#32770' and self.IAccessibleRole == controlTypes.Role.DIALOG:\n"
	"\t\t\tclsList.append(Dialog)\n"
	"\t\tclsList.append(IAccessible)\n"
	"\t\tif self.event_objectID == winUser.OBJID_CLIENT and self.event_childID == 0:\n"
	"\t\t\tsuper(IAccessible, self).findOverlayClasses(clsList)\n"
	"\n"
	"\tdef _get_IAccessibleRole(self):\n"
	"\t\treturn windows[self.windowHandle].role\n"
	"\n"
	"\tdef _get_IAccessibleStates(self):\n"
	"\t\treturn windows[self.windowHandle].states\n"
	"\n"
	"\tdef _get_role(self):\n"
	"\t\treturn self.IAccessibleRole\n"
	"\n"
	"\tdef _get_children(self):\n"
	"\t\t# Each child window as NVDA makes it (Window.findBestAPIClass, relation 'parent': the window's client).\n"
	"\t\treturn [\n"
	"\t\t\tIAccessible(chooseBestAPI=False, windowHandle=child, event_objectID=winUser.OBJID_CLIENT, event_childID=0)\n"
	"\t\t\tfor child in windows[self.windowHandle].children\n"
	"\t\t]\n"
	"\n" + NVDA_IACCESSIBLE_STATES + "\n"
	"\n"
	"class EnhancedSuggestion(NVDAObject):\n"
	"\t# Control Usage Assistant's (NVDAObjects.behaviors.InputFieldWithSuggestions): no states of its own.\n"
	"\tpass\n"
	"\n"
	"\n"
	"class ControlUsageAssistant:\n"
	"\t# Its GlobalPlugin.chooseNVDAObjectOverlayClasses, word for word.\n"
	"\tdef chooseNVDAObjectOverlayClasses(self, obj, clsList):\n"
	"\t\tif obj.role == controlTypes.Role.EDITABLETEXT:\n"
	"\t\t\tclsList.insert(0, EnhancedSuggestion)\n"
	"\n"
	"\n"
	"class TimerMixin(NVDAObject):\n"
	"\t# Enhanced Control Support's, with its initOverlayClass word for word.\n"
	"\tstaticName = staticValue = ''\n"
	"\tstaticStates = set()\n"
	"\n" + ECS_TIMER_MIXIN_INIT
)

# The rest of Enhanced Control Support's GlobalPlugin.chooseNVDAObjectOverlayClasses, for a window no one set up in
# it (getConfigFromWindow gives nothing, so it chooses no class of its own), looking its choice up in its module.
IMITATED_ECS_CHOICE = (
	"def chooseNVDAObjectOverlayClasses(obj, clsList):\n"
	"\tif not isinstance(obj, window.Window):\n"
	"\t\treturn\n"
	"\tconf = None\n"
	"\tif not issubclass(obj.APIClass, Win32) and not \"kwargsFromSuper\" in obj.APIClass.__dict__:\n"
	"\t\treturn\n"
	"\tif shouldUseTimerMixin(conf, obj, clsList):\n"
	"\t\tclsList.insert(0, TimerMixin)\n"
)


def compiled(source, name):
	# NVDA's annotations are only read by type checkers.
	return compile(source, name, "exec", flags=__future__.annotations.compiler_flag, dont_inherit=True)


class Nvda:
	"""NVDA 2026.2 making objects for ``windows``, with the tester's add-ons that choose classes for them."""

	def __init__(self, windows, enhancedControlSupport=True, trustEvents=False):
		self.windows = windows
		controlTypes = types.ModuleType("controlTypes")
		controlTypes.Role, controlTypes.State = Role, State
		self.controlTypes = controlTypes
		self.globalPluginHandler = types.SimpleNamespace(runningPlugins=[])
		scope = {
			"__name__": "NVDAObjects",
			"Any": Any,
			"Callable": Callable,
			"Optional": Optional,
			"Set": Set,
			"Union": Union,
			"GetterReturnT": Any,
			"GetterMethodT": Callable,
			"ABCMeta": ABCMeta,
			"abstractproperty": abstractproperty,
			"weakref": weakref,
			"typing": typing,
			"garbageHandler": types.SimpleNamespace(TrackedObject=object),
			"log": documentPolling._log(),
			"InvalidNVDAObject": type("InvalidNVDAObject", (Exception,), {}),
			"globalPluginHandler": self.globalPluginHandler,
			"controlTypes": controlTypes,
			"textInfos": types.SimpleNamespace(POSITION_ALL="all", POSITION_CARET="caret"),
			"winUser": types.SimpleNamespace(
				OBJID_CLIENT=OBJID_CLIENT,
				OBJID_WINDOW=0,
				WS_VISIBLE=WS_VISIBLE,
				WS_DISABLED=0x08000000,
				ES_MULTILINE=ES_MULTILINE,
				getWindowStyle=lambda windowHandle: windows[windowHandle].style,
			),
			"IAccessibleHandler": types.SimpleNamespace(calculateNvdaStates=lambda role, states: set(states)),
			"IA2": types.SimpleNamespace(IAccessible2=type("IAccessible2", (), {})),
			"COMError": type("COMError", (Exception,), {}),
			"windows": windows,
		}
		exec(compiled(NVDA_BASE_OBJECT, "<NVDA 2026.2 baseObject>"), scope)
		exec(compiled(IMITATED_NVDA, "<NVDA 2026.2 NVDAObjects>"), scope)
		self.scope = scope
		for name in ("AutoPropertyObject", "IAccessible", "Window", "Edit", "EditBase", "EditableText", "Dialog", "NVDAObject"):
			setattr(self, name, scope[name])
		self.TimerMixin = scope["TimerMixin"]
		self.ecs = None
		plugins = [scope["ControlUsageAssistant"]()]
		if enhancedControlSupport:
			self.ecs = self._enhancedControlSupport(trustEvents)
			ecs = self.ecs

			class EnhancedControlSupport:
				def chooseNVDAObjectOverlayClasses(self, obj, clsList):
					ecs.chooseNVDAObjectOverlayClasses(obj, clsList)

			# The order of the classes in the tester's log (TimerMixin, then EnhancedSuggestion): Control Usage
			# Assistant chose first.
			plugins.append(EnhancedControlSupport())
		self.globalPluginHandler.runningPlugins[:] = plugins
		package = types.ModuleType("NVDAObjects")
		package.__path__ = []
		windowPackage = types.ModuleType("NVDAObjects.window")
		windowPackage.__path__ = []
		editModule = types.ModuleType("NVDAObjects.window.edit")
		editModule.EditBase = self.EditBase
		self.modules = {
			"controlTypes": controlTypes,
			"editableText": types.SimpleNamespace(EditableText=self.EditableText),
			"NVDAObjects": package,
			"NVDAObjects.window": windowPackage,
			"NVDAObjects.window.edit": editModule,
		}
		if self.ecs is not None:
			self.modules[MODULE] = self.ecs

	def _enhancedControlSupport(self, trustEvents):
		module = types.ModuleType(MODULE)
		Window = self.Window

		class Win32(Window):
			"""Its class for a window NVDA doesn't know."""

		class Complex(Win32):
			pass

		module.__dict__.update(
			config=types.SimpleNamespace(conf={"enhancedControlSupport": {"trustEvents": trustEvents}}),
			window=types.SimpleNamespace(Window=Window),
			Win32=Win32,
			Complex=Complex,
			TimerMixin=self.TimerMixin,
		)
		exec(compiled(ECS_SHOULD_USE_TIMER_MIXIN, "<Enhanced Control Support 1.2.2>"), module.__dict__)
		exec(compiled(IMITATED_ECS_CHOICE, "<Enhanced Control Support 1.2.2, imitated>"), module.__dict__)
		return module

	def object(self, windowHandle):
		"""The object NVDA makes for a window's client, as for the focus or the foreground window."""
		return self.IAccessible(chooseBestAPI=False, windowHandle=windowHandle, event_objectID=OBJID_CLIENT, event_childID=0)

	def endCoreCycle(self):
		self.AutoPropertyObject.invalidateCaches()


def asUpTo137():
	"""The assistant's check as it was from 1.15 to 1.37: the object's role and states, read into its cache."""
	return (
		mock.patch.object(documentPolling, "_peek", lambda obj, name: getattr(obj, name)),
		mock.patch.object(documentPolling, "_win32EditClass", lambda: None),
	)


class DialogTextTests(unittest.TestCase):
	"""What NVDA says of a dialog as it comes up: its name, "dialog", and its text (Dialog.description)."""

	def nvda(self, windows, upTo137=False, assistant=True, **kwargs):
		nvda = Nvda(windows, **kwargs)
		patcher = mock.patch.dict(sys.modules, nvda.modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		if upTo137:
			for patch in asUpTo137():
				patch.start()
				self.addCleanup(patch.stop)
		documentPolling._failed = False
		documentPolling._logged.clear()
		self.addCleanup(self._restore)
		if assistant:
			documentPolling.register()
		return nvda

	def _restore(self):
		documentPolling.unregister()
		documentPolling._replaced.clear()
		documentPolling._failed = False

	def test_theTestersVersionSaidTheWholeHistory(self):
		# The tester's log: "Speech History, dialog, space, h, e, a, r, period, ...", 26,000 characters of it.
		nvda = self.nvda(SPEECH_HISTORY_WINDOW, upTo137=True)
		self.assertEqual(nvda.object(100).description, HISTORY)

	def test_theSpeechHistoryWindowSaysNoneOfItsText(self):
		nvda = self.nvda(SPEECH_HISTORY_WINDOW)
		self.assertEqual(nvda.object(100).description, "")

	def test_theTestersVersionSaidTheReleaseNotes(self):
		# The tester's older log, word for word as far as NOTES goes: "JAWS Migration Assistant update, dialog, JAWS
		# Migration Assistant 1.36 is available. You have version 1.35.\nWhat's new:\nJAWS Migration Assistant 1.36 ...".
		# "What's new:" is the box's name, which NVDA says before a field's text; the label itself is left out.
		nvda = self.nvda(UPDATE_DIALOG, upTo137=True)
		self.assertEqual(nvda.object(200).description, SUMMARY + "\nWhat's new:\n" + NOTES)

	def test_theUpdateDialogSaysItsSummaryNotItsNotes(self):
		nvda = self.nvda(UPDATE_DIALOG)
		self.assertEqual(nvda.object(200).description, SUMMARY)

	def test_aReadOnlyFieldOfOneLineIsStillTheDialogsText(self):
		# NVDA's own way, which the assistant doesn't change.
		for upTo137 in (True, False):
			with self.subTest(upTo137=upTo137):
				nvda = self.nvda(ONE_LINE_DIALOG, upTo137=upTo137)
				self.assertIn(ADDRESS, nvda.object(300).description)
				self._restore()

	def test_enhancedControlSupportAloneDoesntDoIt(self):
		# It reads the states only once the object has its classes (TimerMixin.initOverlayClass).
		nvda = self.nvda(SPEECH_HISTORY_WINDOW, assistant=False)
		self.assertEqual(nvda.object(100).description, "")
		focus = nvda.object(101)
		self.assertIn(State.MULTILINE, focus.states)
		self.assertIsInstance(focus, nvda.TimerMixin)

	def test_withoutEnhancedControlSupportNothingChanges(self):
		nvda = self.nvda(SPEECH_HISTORY_WINDOW, enhancedControlSupport=False)
		self.assertEqual(nvda.object(100).description, "")
		self.assertIn(State.MULTILINE, nvda.object(101).states)

	def test_theTestersVersionTookMultiLineFromTheFocus(self):
		nvda = self.nvda(SPEECH_HISTORY_WINDOW, upTo137=True)
		focus = nvda.object(101)
		self.assertNotIn(State.MULTILINE, focus.states)
		# The class in the tester's log, with Enhanced Control Support's timer on the history's text box.
		self.assertEqual(type(focus).__name__, "Dynamic_TimerMixinEnhancedSuggestionIAccessibleEditWindowNVDAObject")
		nvda.endCoreCycle()
		# 50 ms on, the timer finds the states changed, and NVDA gets a state change for nothing.
		self.assertIn(State.MULTILINE, focus.states)
		self.assertNotEqual(focus.staticStates, focus.states)

	def test_theFocusIsMultiLineWithoutTheTimer(self):
		nvda = self.nvda(SPEECH_HISTORY_WINDOW)
		focus = nvda.object(101)
		self.assertIn(State.MULTILINE, focus.states)
		self.assertIn(State.READONLY, focus.states)
		self.assertEqual(type(focus).__name__, "Dynamic_EnhancedSuggestionIAccessibleEditWindowNVDAObject")
		self.assertNotIsInstance(focus, nvda.TimerMixin)

	def test_aFieldOfOneLineKeepsTheTimer(self):
		nvda = self.nvda(ONE_LINE_DIALOG)
		field = nvda.object(302)
		self.assertIsInstance(field, nvda.TimerMixin)
		self.assertNotIn(State.MULTILINE, field.states)

	def test_relyingOnEventsNothingChanges(self):
		nvda = self.nvda(SPEECH_HISTORY_WINDOW, trustEvents=True)
		self.assertEqual(nvda.object(100).description, "")
		self.assertNotIsInstance(nvda.object(101), nvda.TimerMixin)


class TheObjectsCacheTests(unittest.TestCase):
	"""The assistant's check, as Enhanced Control Support asks it while NVDA is making the object."""

	def setUp(self):
		self.nvda = Nvda(SPEECH_HISTORY_WINDOW)
		patcher = mock.patch.dict(sys.modules, self.nvda.modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(self._restore)
		documentPolling._failed = False
		documentPolling.register()

	def _restore(self):
		documentPolling.unregister()
		documentPolling._replaced.clear()
		documentPolling._failed = False

	def bare(self, windowHandle):
		"""An object as NVDA has it when the global plugins choose its classes: its API class alone."""
		IAccessible = self.nvda.IAccessible
		obj = IAccessible.__new__(IAccessible)
		obj.APIClass = IAccessible
		obj.__init__(windowHandle=windowHandle, event_objectID=OBJID_CLIENT, event_childID=0)
		return obj, [IAccessible, self.nvda.Edit, self.nvda.Window, self.nvda.NVDAObject]

	def test_theCacheIsLeftAsItWas(self):
		obj, clsList = self.bare(101)
		obj._propertyCache[id] = "kept"
		self.assertFalse(self.nvda.ecs.shouldUseTimerMixin(None, obj, clsList))
		self.assertEqual(obj._propertyCache, {id: "kept"})

	def test_theTestersVersionLeftStatesWithoutMultiLine(self):
		obj, clsList = self.bare(101)
		with asUpTo137()[0], asUpTo137()[1]:
			self.assertTrue(self.nvda.ecs.shouldUseTimerMixin(None, obj, clsList))
		self.assertNotIn(State.MULTILINE, obj._propertyCache[self.nvda.IAccessible._get_states])

	def test_aFieldOtherThanWin32sByItsStates(self):
		# A text field NVDA reads through UI Automation or IAccessible2 says "multi line" itself.
		NVDAObject, EditableText = self.nvda.NVDAObject, self.nvda.EditableText

		class Field(NVDAObject):
			def _get_role(self):
				return Role.EDITABLETEXT

			def _get_states(self):
				return {State.MULTILINE}

		class Field1(Field):
			def _get_states(self):
				return set()

		field = Field.__new__(Field)
		field.windowClassName = "RichEditD2DPT"
		self.assertFalse(self.nvda.ecs.shouldUseTimerMixin(None, field, [EditableText, Field]))
		self.assertEqual(field._propertyCache, {})
		oneLine = Field1.__new__(Field1)
		self.assertTrue(self.nvda.ecs.shouldUseTimerMixin(None, oneLine, [EditableText, Field1]))
		self.assertEqual(oneLine._propertyCache, {})

	def test_withoutNvdasEditClassByItsStates(self):
		# An NVDA without window.edit.EditBase: the object's states, as before.
		obj, clsList = self.bare(101)
		with mock.patch.object(documentPolling, "_win32EditClass", lambda: None):
			self.assertTrue(self.nvda.ecs.shouldUseTimerMixin(None, obj, clsList))
		self.assertEqual(obj._propertyCache, {}, "still nothing left in the cache")


class NvdasOwnCodeTests(unittest.TestCase):
	def check(self, variable, blocks):
		source = os.environ.get(variable)
		if not source:
			self.skipTest(f"{variable} isn't set")
		for name, parts in blocks.items():
			with open(os.path.join(source, *parts), encoding="utf-8") as f:
				text = f.read().replace("\r\n", "\n")
			self.assertIn(globals()[name], text, name)

	def test_theCodeIsNvdas(self):
		# Each piece is in NVDA 2026.2's source: set NVDA_SOURCE to its source folder.
		self.check("NVDA_SOURCE", NVDA_FILES)

	def test_theCodeIsEnhancedControlSupports(self):
		# Each piece is in Enhanced Control Support 1.2.2 (github.com/emil-18/enhanced-control-support, tag v1.2.2): set
		# ECS_SOURCE to its folder.
		self.check("ECS_SOURCE", ECS_FILES)


if __name__ == "__main__":
	unittest.main()
