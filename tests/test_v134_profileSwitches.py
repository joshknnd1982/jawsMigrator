# Unit tests for version 1.34, from a tester's report (issue 31, "Absolute issue when alt tabbing"): "There is an
# absolute issue when alt tabbing. Also sometimes when pressing insert f7 Links list didn't activate. ... I believe the
# two issues are tied together." Their two logs (NVDA 2026.2, jawsMigrator 1.33, 45 add-ons) show NVDA's main thread
# stuck twice, about two seconds each time, whenever the focus went into or out of Edge:
# 17:36:23.684 Input: kb(laptop):alt+tab
# 17:36:24.368 Starting freeze recovery after 0.500073400005931 seconds.
# 17:36:24.821 Deactivating triggered profile JAWS - msedge
# 17:36:25.917 Recovered from freeze after 2.049114199995529 seconds.
# 17:36:26.544 Starting freeze recovery after 0.5001008000108413 seconds.
# 17:36:26.920 Activating triggered profile JAWS - msedge
# 17:36:27.833 Recovered from freeze after 1.7891983000154141 seconds.
# Each time NVDA was switching configuration profiles: the migration's "JAWS - msedge" profile turns on in Edge, and
# the Custom Browse Mode add-on turns on its "browseMode" profile whenever browse mode does, so each Alt+Tab into or
# out of Edge is two switches. The watchdog's stacks of NVDA's main thread show where each second went:
#   columnsReview\__init__.py, line 231, in handleConfigProfileSwitch: inst.bindCRGestures(reinitializeObj=True)
#   columnsReview\commonFunc.py, getScriptGestures -> inputCore.pyc, line 791, in getAllGestureMappings
# Columns Review 5.7.0, at every switch and for every list it has seen, asks NVDA for every command there is to learn
# three keys of NVDA's own (0.75 to 0.87 s each time), and Emoticons 38.0.0 reads speechDictHandler.dictionaries
# twice for each of its 88 emoticons, which NVDA 2026.2 answers with a warning and the whole stack in the log:
#   176 x "speechDictHandler.dictionaries is deprecated. No public replacement is planned.", then one more, 0.2 s.
# After half a second with the foreground changed, NVDA lets every key through to the program
# (watchdog.isAttemptingRecovery in keyboardHandler.internal_keyDownEvent), and three times Insert+F7 reached Edge as
# F7 during such a freeze, which opened "Turn on caret browsing?" (17:37:11, 17:37:30, 17:37:39), with no NVDA+f7 in
# NVDA's input log.
# - profileSwitches: Columns Review keeps the keys of NVDA's own commands it asked for until NVDA's keys change, and
#   Emoticons reads NVDA's dictionaries once for each change. What Columns Review binds and Emoticons does is the same.
# The imitation NVDA runs NVDA 2026.2's own ScriptableObject, script decorator, gesture maps and list of all commands
# (inputCore._AllGestureMappingsRetriever), NVDA's global commands' own scripts, and its deprecation of
# speechDictHandler.dictionaries with SpeechDict and SpeechDictEntry, word for word. Columns Review 5.7.0's
# getScriptGestures, ConfigFromObject, GlobalPlugin.__init__/handleConfigProfileSwitch and CRList's bindCRGestures
# and bindGesturesForEmpty, and Emoticons 38.0.0's dictionaries, loadDic, activateAnnouncement,
# deactivateAnnouncement, handleConfigProfileSwitch and its 88 emoticons, are the add-ons' own, word for word (from
# the releases the tester has). The assistant's code is the real one.
# Built by an ast script from NVDA's raw release-2026.2 sources and the two .nvda-addon files.
# Run: python -m unittest tests.test_v134_profileSwitches -v

import __future__  # noqa: F401
import abc
import collections
import dataclasses
import enum
import fnmatch
import functools
import importlib
import inspect
import logging
import os
import re
import sys
import tempfile
import textwrap
import types
import typing
import unittest
import weakref
from collections.abc import Callable
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v128_startupFocus as v128  # noqa: E402
from jawsMigrator import profileSwitches, state  # noqa: E402

# -- NVDA 2026.2's own code, word for word --------------------------------------------------------------------------

#: baseObject.py: ScriptableType and ScriptableObject.
NVDA_SCRIPTABLE_OBJECT = r'''
class ScriptableType(AutoPropertyType):
	"""A metaclass used for collecting and caching gestures on a ScriptableObject"""

	def __new__(cls, name: str, bases: tuple[type, ...], namespace: dict[str, Any], /, **kwargs: Any):
		newCls = super().__new__(cls, name, bases, namespace, **kwargs)
		gesturesDictName = "_%s__gestures" % newCls.__name__
		# #8463: To avoid name mangling conflicts, create a copy of the __gestures dictionary.
		try:
			gestures = getattr(newCls, gesturesDictName).copy()
		except AttributeError:
			# This class currently has no gestures dictionary,
			# because no custom __gestures dictionary has been defined.
			gestures = {}
		for name, script in namespace.items():
			if not name.startswith("script_"):
				continue
			scriptName = name[len("script_") :]
			if hasattr(script, "gestures"):
				for gesture in script.gestures:
					gestures[gesture] = scriptName
		if gestures:
			setattr(newCls, gesturesDictName, gestures)
		return newCls


class ScriptableObject(AutoPropertyObject, metaclass=ScriptableType):
	"""A class that implements NVDA's scripting interface.
	Input gestures are bound to scripts such that the script will be executed when the appropriate input gesture is received.
	Scripts are methods named with a prefix of C{script_}; e.g. C{script_foo}.
	They accept an L{inputCore.InputGesture} as their single argument.
	Gesture bindings can be specified on the class by creating a C{__gestures} dict which maps gesture identifiers to script names.
	They can also be bound on an instance using the L{bindGesture} method.
	@cvar scriptCategory: If present, a translatable string displayed to the user
		as the category for scripts in this class;
		e.g. in the Input Gestures dialog.
		This can be overridden for individual scripts
		by setting a C{category} attribute on the script method.
	@type scriptCategory: str
	"""

	def __init__(self):
		#: Maps input gestures to script functions.
		#: @type: dict
		self._gestureMap = {}
		# Bind gestures specified on the class.
		# This includes gestures specified on decorated scripts.
		# This does not include the gestures that are added when creating a DynamicNVDAObjectType.
		for cls in reversed(self.__class__.__mro__):
			try:
				self.bindGestures(getattr(cls, "_%s__gestures" % cls.__name__))
			except AttributeError:
				pass
			try:
				self.bindGestures(cls._scriptDecoratorGestures)
			except AttributeError:
				pass
		super(ScriptableObject, self).__init__()

	def bindGesture(self, gestureIdentifier, scriptName):
		"""Bind an input gesture to a script.
		@param gestureIdentifier: The identifier of the input gesture.
		@type gestureIdentifier: str
		@param scriptName: The name of the script, which is the name of the method excluding the C{script_} prefix.
		@type scriptName: str
		@raise LookupError: If there is no script with the provided name.
		"""
		scriptAttrName = "script_%s" % scriptName
		# Don't store the instance method, as this causes a circular reference
		# and instance methods are meant to be generated on retrieval anyway.
		func = getattr(self.__class__, scriptAttrName, None)
		if not func:
			raise LookupError(
				"No such script on class {className}. Couldn't find attribute: {scriptAttrName}".format(
					className=self.__class__.__name__,
					scriptAttrName=scriptAttrName,
				),
			)
		# Import late to avoid circular import.
		import inputCore

		self._gestureMap[inputCore.normalizeGestureIdentifier(gestureIdentifier)] = func

	def removeGestureBinding(self, gestureIdentifier):
		"""
		Removes the binding for the given gesture identifier if a binding exists.
		@param gestureIdentifier: The identifier of the input gesture.
		@type gestureIdentifier: str
		@raise LookupError: If there is no binding for this gesture
		"""
		# Import late to avoid circular import.
		import inputCore

		del self._gestureMap[inputCore.normalizeGestureIdentifier(gestureIdentifier)]

	def clearGestureBindings(self):
		"""Remove all input gesture bindings from this object."""
		self._gestureMap.clear()

	def bindGestures(self, gestureMap):
		"""Bind or unbind multiple input gestures.
		This is a convenience method which simply calls L{bindGesture} for each gesture and script pair, logging any errors.
		For the case where script is None, L{removeGestureBinding} is called instead.
		@param gestureMap: A mapping of gesture identifiers to script names.
		@type gestureMap: dict of str to str
		"""
		for gestureIdentifier, scriptName in gestureMap.items():
			if scriptName:
				try:
					self.bindGesture(gestureIdentifier, scriptName)
				except LookupError:
					log.error("Error binding script %s in %r" % (scriptName, self))
			else:
				try:
					self.removeGestureBinding(gestureIdentifier)
				except LookupError:
					pass

	def getScript(self, gesture):
		"""Retrieve the script bound to a given gesture.
		@param gesture: The input gesture in question.
		@type gesture: L{inputCore.InputGesture}
		@return: The script function or C{None} if none was found.
		@rtype: script function
		"""
		for identifier in gesture.normalizedIdentifiers:
			try:
				# Convert to instance method.
				return self._gestureMap[identifier].__get__(self, self.__class__)
			except KeyError:
				continue
			except AttributeError:
				log.exception(
					f"Base class may not have been initialized.\nMRO={self.__class__.__mro__}"
					if not hasattr(self, "_gestureMap")
					else None,
				)
				return None
		else:
			return None

	#: A value for sleepMode which indicates that NVDA should fully sleep for this object;
	#: i.e. braille and speech via NVDA controller client is disabled and the user cannot disable sleep mode.
	SLEEP_FULL = "full"
'''

#: scriptHandler.py: the script decorator.
NVDA_SCRIPT_DECORATOR = r'''
def script(
	description: str = "",
	category: Optional[str] = None,
	gesture: Optional[str] = None,
	gestures: Optional[Iterator[str]] = None,
	canPropagate: bool = False,
	bypassInputHelp: bool = False,
	allowInSleepMode: bool = False,
	resumeSayAllMode: Optional[int] = None,
	speakOnDemand: bool = False,
):
	"""Define metadata for a script.
	This function is to be used as a decorator to set metadata used by the scripting system and gesture editor.
	It can only decorate methods which have a name starting with "script_"
	:param description: A short translatable description of the script to be used in the gesture editor, etc.
	:param category: The category of the script displayed in the gesture editor.
	:param gesture: A gesture associated with this script.
	:param gestures: A collection of gestures associated with this script
	:param canPropagate: Whether this script should also apply when it belongs to a  focus ancestor object.
	:param bypassInputHelp: Whether this script should run when input help is active.
	:param allowInSleepMode: Whether this script should run when NVDA is in sleep mode.
	:param resumeSayAllMode: The say all mode that should be resumed when active before executing this script.
	One of the C{sayAll.CURSOR_*} constants.
	:param speakOnDemand: Whether this script should speak when NVDA speech mode is "on-demand"
	"""
	if gestures is None:
		gestures: List[str] = []
	else:
		# A tuple may have been used, however, the collection of gestures may need to be
		# extended (via append) with the value of the 'gesture' string (in-case both are provided in the
		# decorator).
		gestures: List[str] = list(gestures)

	def script_decorator(decoratedScript):
		# Decoratable scripts are functions, not bound instance methods.
		if not isinstance(decoratedScript, types.FunctionType):
			log.warning(
				"Using the script decorator is unsupported for %r" % decoratedScript,
				stack_info=True,
			)
			return decoratedScript
		if not decoratedScript.__name__.startswith("script_"):
			log.warning(
				"Can't apply  script decorator to %r which name does not start with 'script_'"
				% decoratedScript.__name__,
				stack_info=True,
			)
			return decoratedScript
		decoratedScript.__doc__ = description
		if category is not None:
			decoratedScript.category = category
		if gesture is not None:
			gestures.append(gesture)
		if gestures:
			decoratedScript.gestures = gestures
		decoratedScript.canPropagate = canPropagate
		decoratedScript.bypassInputHelp = bypassInputHelp
		if resumeSayAllMode is not None:
			decoratedScript.resumeSayAllMode = resumeSayAllMode
		decoratedScript.allowInSleepMode = allowInSleepMode
		decoratedScript.speakOnDemand = speakOnDemand
		return decoratedScript

	return script_decorator
'''

#: inputCore.py: gesture maps and NVDA's list of all its commands (the Input Gestures dialog's).
NVDA_GESTURE_MAPS = r'''
def normalizeGestureIdentifier(identifier):
	"""Normalize a gesture identifier so that it matches other identifiers for the same gesture.
	First, the entire identifier is converted to lower case.
	Then, any items separated by a + sign after the source prefix are considered to be of indeterminate order
	and are sorted by character.
	This is done because, for example, "kb:shift+alt+downArrow"
	must be treated the same as "kb:alt+shift+downarrow".
	"""
	identifier = identifier.lower()
	prefix, main = identifier.split(":", 1)
	main = main.split("+")
	# The order of the parts doesn't matter as far as the user is concerned,
	# but we need them to be in a determinate order so they will match other gesture identifiers.
	# We sort them by character.
	main.sort()
	main = "+".join(main)
	return "{0}:{1}".format(prefix, main)


class GlobalGestureMap:
	"""Maps gestures to scripts anywhere in NVDA.
	This is used to allow users and locales to bind gestures in addition to those bound by
	individual scriptable objects.
	Map entries will most often be loaded from a file using the L{load} method.
	See that method for details of the file format.
	"""

	def __init__(self, entries: Optional[FlattenedGestureMapT] = None):
		"""Constructor.
		@param entries: Initial entries to add; see L{update} for the format.
		"""
		self._map: _InternalGestureMapT = {}
		#: Indicates that the last load or update contained an error.
		self.lastUpdateContainedError: bool = False
		#: The file name for this gesture map, if any.
		self.fileName: Optional[str] = None
		if entries:
			self.update(entries)

	def clear(self):
		"""Clear this map."""
		self._map.clear()
		self.lastUpdateContainedError = False

	def add(
		self,
		gesture: str,
		module: str,
		className: str,
		script: Optional[ScriptNameT],
		replace: bool = False,
	):
		"""Add a gesture mapping.
		@param gesture: The gesture identifier.
		@param module: The name of the Python module containing the target script.
		@param className: The name of the class in L{module} containing the target script.
		@param script: The name of the target script
			or C{None} to unbind the gesture for this class.
		@param replace: if true replaces all existing bindings for this gesture with the given script,
			otherwise only appends this binding.
		"""
		gesture = normalizeGestureIdentifier(gesture)
		try:
			scripts = self._map[gesture]
		except KeyError:
			scripts = self._map[gesture] = []
		if replace:
			del scripts[:]
		scripts.append((module, className, script))

	def load(self, filename: str):
		"""Load map entries from a file.
		The file is an ini file.
		Each section contains entries for a particular scriptable object class.
		The section name must be the full Python module and class name.
		The key of each entry is the script name and the value is a comma separated list of one or more gestures.
		If the script name is "None", the gesture will be unbound for this class.
		For example, the following binds the "a" key to move to the next heading in virtual buffers
		and removes the default "h" binding::
			[virtualBuffers.VirtualBuffer]
			nextHeading = kb:a
			None = kb:h
		@param filename: The name of the file to load.
		"""
		self.fileName = filename
		try:
			conf = configobj.ConfigObj(filename, file_error=True, encoding="UTF-8")
		except (configobj.ConfigObjError, UnicodeDecodeError) as e:
			log.warning("Error in gesture map '%s': %s" % (filename, e))
			self.lastUpdateContainedError = True
			return
		self.update(conf)

	def update(self, entries: FlattenedGestureMapT):
		"""Add multiple map entries.
		C{entries} must be a mapping of mappings.
		Each inner mapping contains entries for a particular scriptable object class.
		The key in the outer mapping must be the full Python module and class name.
		The key of each entry in the inner mappings is the script name
		and the value is one gesture string or a list of one or more gesture strings.
		If the script name is C{None}, the gesture will be unbound for this class.
		For example, the following binds the "a" key to move to the next heading in virtual buffers
		and removes the default "h" binding:
			{
				"virtualBuffers.VirtualBuffer": {
					"nextHeading": "kb:a",
					None: "kb:h",
				}
			}
		@param entries: The items to add.
		"""
		self.lastUpdateContainedError = False
		for locationName, location in entries.items():
			try:
				module, className = locationName.rsplit(".", 1)
			except:  # noqa: E722
				log.error("Invalid module/class specification: %s" % locationName)
				self.lastUpdateContainedError = True
				continue
			for script, gestures in location.items():
				if script == "None":
					script = None
				if gestures in ("", None):
					gestures = ()
				elif isinstance(gestures, str):
					gestures = [gestures]
				for gesture in gestures:
					try:
						self.add(gesture, module, className, script)
					except:  # noqa: E722
						log.error("Invalid gesture: %s" % gesture)
						self.lastUpdateContainedError = True
						continue

	def getScriptsForGesture(self, gesture: str) -> Generator[InputGestureScriptT, None, None]:
		"""Get the scripts associated with a particular gesture.
		@param gesture: The gesture identifier.
		@return: The Python class and script name for each script;
			the script name may be C{None} indicating that the gesture should be unbound for this class.
		"""
		try:
			scripts = self._map[gesture]
		except KeyError:
			return
		for moduleName, className, scriptName in scripts:
			try:
				module = sys.modules[moduleName]
			except KeyError:
				continue
			try:
				cls = getattr(module, className)
			except AttributeError:
				continue
			yield cls, scriptName

	def getScriptsForAllGestures(self):
		"""Get all of the scripts and their gestures.
		@return: The Python class, gesture and script name for each mapping;
			the script name may be C{None} indicating that the gesture should be unbound for this class.
		@rtype: generator of (class, str, str)
		"""
		for gesture in self._map:
			for cls, scriptName in self.getScriptsForGesture(gesture):
				yield cls, gesture, scriptName

	def remove(self, gesture: str, module: str, className: str, script: ScriptNameT):
		"""Remove a gesture mapping.
		@param gesture: The gesture identifier.
		@param module: The name of the Python module containing the target script.
		@param className: The name of the class in L{module} containing the target script.
		@param script: The name of the target script.
		@raise ValueError: If the requested mapping does not exist.
		"""
		gesture = normalizeGestureIdentifier(gesture)
		try:
			scripts = self._map[gesture]
		except KeyError:
			raise ValueError("Mapping not found")
		scripts.remove((module, className, script))

	def export(self) -> FlattenedGestureMapT:
		"""Exports this gesture map to a dictionary that can be saved to disk or imported into another gesture map."""
		out: FlattenedGestureMapT = {}
		for gesture, scripts in self._map.items():
			for module, className, script in scripts:
				key = f"{module}.{className}"
				try:
					outSect = out[key]
				except KeyError:
					out[key] = {}
					outSect = out[key]
				if script is None:
					script = "None"
				try:
					outVal = outSect[script]
				except KeyError:
					# Write the first value as a string so configobj doesn't output a comma if there's only one value.
					outVal = outSect[script] = gesture
				else:
					if isinstance(outVal, list):
						outVal.append(gesture)
					else:
						outSect[script] = [outVal, gesture]
		return out

	@blockAction.when(blockAction.Context.SECURE_MODE)
	def save(self):
		"""Save this gesture map to disk.
		@precondition: L{load} must have been called.
		"""
		if not shouldWriteToDisk():
			log.debug("Not saving user gesture map, as shouldWriteToDisk returned false.")
			return
		if not self.fileName:
			raise ValueError("No file name")
		out = configobj.ConfigObj(self.export(), encoding="UTF-8")
		out.filename = self.fileName

		with FaultTolerantFile(out.filename) as f:
			out.write(f)

	def __eq__(self, other: Any) -> bool:
		if isinstance(other, GlobalGestureMap):
			return self._map == other._map
		return NotImplemented


class _AllGestureMappingsRetriever(object):
	results: Dict[
		str,  # category name
		Dict[
			str,  # command display name
			Any,  # AllGesturesScriptInfo
		],
	]

	def __init__(self, obj, ancestors):
		self.results = {}
		self.scriptInfo = {}
		self.handledGestures = set()

		self.addGlobalMap(manager.userGestureMap)
		self.addGlobalMap(manager.localeGestureMap)
		import braille

		gmap = braille.handler.display.gestureMap if braille.handler and braille.handler.display else None
		if gmap:
			self.addGlobalMap(gmap)

		# Global plugins.
		import globalPluginHandler

		for plugin in globalPluginHandler.runningPlugins:
			self.addObj(plugin)

		# App module.
		app = obj.appModule
		if app:
			self.addObj(app)

		# Braille display driver
		if isinstance(braille.handler.display, baseObject.ScriptableObject):
			self.addObj(braille.handler.display)

		# Vision enhancement provider
		import vision

		for provider in vision.handler.getActiveProviderInstances():
			if isinstance(provider, baseObject.ScriptableObject):
				self.addObj(provider)

		# Tree interceptor.
		ti = obj.treeInterceptor
		if ti:
			self.addObj(ti)

		# NVDAObject.
		self.addObj(obj)
		for anc in reversed(ancestors):
			self.addObj(anc, isAncestor=True)

		import globalCommands

		# Configuration profiles
		self.addObj(globalCommands.configProfileActivationCommands)

		# Global commands.
		self.addObj(globalCommands.commands)

	def addResult(self, scriptInfo):
		"""
		@type scriptInfo: AllGesturesScriptInfo
		"""
		self.scriptInfo[scriptInfo.cls, scriptInfo.scriptName] = scriptInfo
		try:
			cat = self.results[scriptInfo.category]
		except KeyError:
			cat = self.results[scriptInfo.category] = {}
		cat[scriptInfo.displayName] = scriptInfo

	def addGlobalMap(self, gmap):
		for cls, gesture, scriptName in gmap.getScriptsForAllGestures():
			key = (cls, gesture)
			if key in self.handledGestures:
				continue
			self.handledGestures.add(key)
			if scriptName is None:
				# The global map specified that no script should execute for this gesture and object.
				continue
			try:
				scriptInfo = self.scriptInfo[cls, scriptName]
			except KeyError:
				if scriptName.startswith("kb:"):
					scriptInfo = self.makeKbEmuScriptInfo(cls, kbGestureIdentifier=scriptName)
				else:
					try:
						script = getattr(cls, "script_%s" % scriptName)
					except AttributeError:
						log.debugWarning(
							f"Unable to bind gesture: script '{scriptName}' not found in class {cls}.",
						)
						self.handledGestures.remove(key)
						continue
					scriptInfo = self.makeNormalScriptInfo(cls, scriptName, script)
					if not scriptInfo:
						# Scripts with no description are not displayed in the Input gesture dialog.
						continue
				self.addResult(scriptInfo)
			scriptInfo.gestures.append(gesture)

	@classmethod
	def makeKbEmuScriptInfo(cls, scriptCls, kbGestureIdentifier):
		"""
		@rtype AllGesturesScriptInfo
		"""
		info = KbEmuScriptInfo(scriptCls, kbGestureIdentifier)
		info.category = SCRCAT_KBEMU
		info.displayName = getDisplayTextForGestureIdentifier(
			normalizeGestureIdentifier(kbGestureIdentifier),
		)[1]
		return info

	@classmethod
	def makeNormalScriptInfo(cls, scriptCls, scriptName, script):
		info = AllGesturesScriptInfo(scriptCls, scriptName)
		info.category = cls.getScriptCategory(scriptCls, script)
		info.displayName = script.__doc__
		if not info.displayName:
			return None
		return info

	@classmethod
	def getScriptCategory(cls, scriptCls, script):
		try:
			return script.category
		except AttributeError:
			pass
		try:
			return scriptCls.scriptCategory
		except AttributeError:
			pass
		return SCRCAT_MISC

	def addObj(self, obj, isAncestor=False):
		scripts = {}
		for cls in obj.__class__.__mro__:
			for scriptName, script in cls.__dict__.items():
				if not scriptName.startswith("script_"):
					continue
				if isAncestor and not getattr(script, "canPropagate", False):
					continue
				scriptName = scriptName[7:]
				try:
					scriptInfo = self.scriptInfo[cls, scriptName]
				except KeyError:
					scriptInfo = self.makeNormalScriptInfo(cls, scriptName, script)
					if not scriptInfo:
						continue
					self.addResult(scriptInfo)
				scripts[script] = scriptInfo
		for gesture, script in obj._gestureMap.items():
			try:
				scriptInfo = scripts[script]
			except KeyError:
				continue
			key = (scriptInfo.cls, gesture)
			if key in self.handledGestures:
				continue
			self.handledGestures.add(key)
			scriptInfo.gestures.append(gesture)


class AllGesturesScriptInfo(object):
	__slots__ = ("cls", "scriptName", "category", "displayName", "gestures")

	def __init__(self, cls, scriptName):
		self.cls = cls
		self.scriptName = scriptName
		self.gestures = []

	@property
	def moduleName(self):
		return self.cls.__module__

	@property
	def className(self):
		return self.cls.__name__


class KbEmuScriptInfo(AllGesturesScriptInfo):
	pass
'''

#: inputCore.py, InputManager.
NVDA_GET_ALL_GESTURE_MAPPINGS = r'''
def getAllGestureMappings(self, obj=None, ancestors=None):
	if not obj:
		obj = api.getFocusObject()
		ancestors = api.getFocusAncestors()
	return _AllGestureMappingsRetriever(obj, ancestors).results
'''

#: globalCommands.py: the categories of the commands below.
NVDA_SCRIPT_CATEGORIES = r'''
SCRCAT_TEXTREVIEW = _("Text review")


SCRCAT_SYSTEMCARET = _("System caret")


SCRCAT_FOCUS = _("System focus")


SCRCAT_CONFIG_PROFILES = _("Configuration profiles")
'''

#: globalCommands.py, GlobalCommands: the commands whose keys Columns Review binds to its own.
NVDA_GLOBAL_COMMAND_SCRIPTS = r'''
@script(
	description=_(
		# Translators: Input help mode message for report current line command.
		"Reports the current line under the application cursor. "
		"Pressing this key twice will spell the current line. "
		"Pressing three times will spell the line using character descriptions.",
	),
	category=SCRCAT_SYSTEMCARET,
	gestures=("kb(desktop):NVDA+upArrow", "kb(laptop):NVDA+l"),
	speakOnDemand=True,
)
def script_reportCurrentLine(self, gesture):
	obj = api.getFocusObject()
	treeInterceptor = obj.treeInterceptor
	if (
		isinstance(treeInterceptor, treeInterceptorHandler.DocumentTreeInterceptor)
		and not treeInterceptor.passThrough
	):
		obj = treeInterceptor
	try:
		info = obj.makeTextInfo(textInfos.POSITION_CARET)
	except (NotImplementedError, RuntimeError):
		info = obj.makeTextInfo(textInfos.POSITION_FIRST)
	info.expand(textInfos.UNIT_LINE)
	scriptCount = getLastScriptRepeatCount()
	if scriptCount == 0:
		speech.speakTextInfo(info, unit=textInfos.UNIT_LINE, reason=controlTypes.OutputReason.CARET)
	else:
		speech.spellTextInfo(info, useCharacterDescriptions=scriptCount > 1)


@script(
	description=_(
		# Translators: Input help mode message for report current selection command.
		"Announces the current selection in edit controls and documents. "
		"Pressing twice spells this information. "
		"Pressing three times spells it using character descriptions. "
		"Pressing four times shows it in a browsable message. ",
	),
	category=SCRCAT_SYSTEMCARET,
	gestures=("kb(desktop):NVDA+shift+upArrow", "kb(laptop):NVDA+shift+s"),
	speakOnDemand=True,
)
def script_reportCurrentSelection(self, gesture):
	obj = api.getFocusObject()
	treeInterceptor = obj.treeInterceptor
	if (
		isinstance(treeInterceptor, treeInterceptorHandler.DocumentTreeInterceptor)
		and not treeInterceptor.passThrough
	):
		obj = treeInterceptor
	try:
		info = obj.makeTextInfo(textInfos.POSITION_SELECTION)
	except (RuntimeError, NotImplementedError):
		info = None
	if not info or info.isCollapsed:
		# Translators: The message reported when there is no selection
		ui.message(_("No selection"))
	else:
		scriptCount = getLastScriptRepeatCount()
		# Translators: The message reported after selected text
		selectMessage = speech.speech._getSelectionMessageSpeech(_("%s selected"), info.text)[0]
		if scriptCount == 0:
			speech.speakTextSelected(info.text)
			braille.handler.message(selectMessage)
		elif scriptCount == 3:
			ui.browseableMessage(info.text, copyButton=True, closeButton=True)
			return

		elif len(info.text) < speech.speech.MAX_LENGTH_FOR_SELECTION_REPORTING:
			speech.speakSpelling(info.text, useCharacterDescriptions=scriptCount > 1)
		else:
			speech.speakTextSelected(info.text)
			braille.handler.message(selectMessage)


@script(
	# Translators: Input help mode message for say all with system caret command.
	description=_("Reads from the system caret up to the end of the text, moving the caret as it goes"),
	category=SCRCAT_SYSTEMCARET,
	gestures=("kb(desktop):NVDA+downArrow", "kb(laptop):NVDA+a"),
	speakOnDemand=True,
)
def script_sayAll(self, gesture: inputCore.InputGesture):
	sayAll.SayAllHandler.readText(sayAll.CURSOR.CARET, startedFromScript=True)


@script(
	description=_(
		# Translators: Input help mode message for report formatting command.
		"Reports formatting info for the current review cursor position."
		" If pressed twice, presents the information in browse mode",
	),
	category=SCRCAT_TEXTREVIEW,
	gesture="kb:NVDA+shift+f",
	speakOnDemand=True,
)
def script_reportFormatting(self, gesture):
	repeats = getLastScriptRepeatCount()
	if repeats == 0:
		self.script_reportFormattingAtReview(gesture)
	elif repeats == 1:
		self.script_showFormattingAtReview(gesture)


@script(
	description=_(
		# Translators: Input help mode message for report formatting at caret command.
		"Reports formatting info for the text under the caret."
		" If pressed twice, presents the information in browse mode",
	),
	category=SCRCAT_SYSTEMCARET,
	gesture="kb:NVDA+f",
	speakOnDemand=True,
)
def script_reportOrShowFormattingAtCaret(self, gesture):
	repeats = getLastScriptRepeatCount()
	if repeats == 0:
		self.script_reportFormattingAtCaret(gesture)
	elif repeats == 1:
		self.script_showFormattingAtCaret(gesture)


@script(
	description=_(
		# Translators: Input help mode message for report current focus command.
		"Reports the object with focus. "
		"If pressed twice, spells the information. "
		"Pressing three times spells it using character descriptions.",
	),
	category=SCRCAT_FOCUS,
	gesture="kb:NVDA+tab",
	speakOnDemand=True,
)
def script_reportCurrentFocus(self, gesture: inputCore.InputGesture):
	focusObject = api.getFocusObject()
	if not isinstance(focusObject, NVDAObject):
		# Translators: Reported when:
		# 1. There is no focusable object e.g. cannot use tab and shift tab to move to controls.
		# 2. Trying to move focus to navigator object but there is no focus.
		ui.message(_("No focus"))
		return

	if objectBelowLockScreenAndWindowsIsLocked(focusObject):
		# This script is available on the lock screen via getSafeScripts, as such
		# ensure the focus object does not contain secure information
		# before announcing this object
		ui.message(gui.blockAction.Context.WINDOWS_LOCKED.translatedMessage)
		return

	repeatCount = getLastScriptRepeatCount()
	if repeatCount == 0:
		speechList = speech.getObjectSpeech(focusObject, reason=controlTypes.OutputReason.QUERY)
		speech.speech.speak(speechList)
		text = " ".join(s for s in speechList if isinstance(s, str))
		braille.handler.message(text)
	else:
		speech.speakSpelling(focusObject.name, useCharacterDescriptions=repeatCount > 1)
'''

#: utils/_deprecate.py.
NVDA_DEPRECATE = r'''
class DeprecatedSymbol(ABC):
	"""A deprecated symbol (variable, constant, function, class, etc).

	Concrete subclasses:

	:class:`MovedSymbol`
		A symbol that has been moved (renamed, moved to a different module, etc) in the public API.

	:class:`RemovedSymbol`
		A symbol that has been removed from the API (including symbols that have been made internal).
	"""

	name: str
	"""Name of the symbol.

	This should be a valid Python name.
	"""

	def __init__(self, name: str):
		"""Initialiser.

		:param name: Old name of the deprecated symbol.
		"""
		self.name = name

	@abstractmethod
	def getLogMessage(self, moduleName: str) -> str:
		"""
		Get the message to be output to the log when attempting to access this symbol.

		:param moduleName: Fully qualified module name from which the symbol is being accessed.
		:return: String to be output to the log.
		"""
		...

	@abstractproperty
	def value(self) -> Any:
		"""Value to be returned as the value of the deprecated symbol."""
		...


class MovedSymbol(DeprecatedSymbol):
	"""A symbol which has been moved (renamed or relocated) in the public API."""

	newModule: str
	"""Fully qualified module name from which the symbol should now be accessed."""

	newPath: tuple[str, ...]
	"""
	Path to access the new symbol from the new module.

	Each element of the path is an attribute of the last.
	The first element is an attribute of :attr:`newModule`.
	"""

	def __init__(self, name: str, newModule: str, *newPath: str):
		"""Initialiser.

		:param name: Old name of the symbol.
		:param newModule: Fully qualified name of the module from which the symbol should now be accessed.
		:param *newPath: Path by which the new symbol is accessed from the new module.
			If the new symbol is an attribute of the new module, this should just be the name of the new symbol.
			If the new symbol is part of a nested data structure (e.g. an enumeration),
			The first element should be an attribute of the new module,
			and each subsequent element should be an element of the previous element.
			If no path segments are provided, ``name`` is used.
		"""
		super().__init__(name)
		self.newModule = newModule
		self.newPath = newPath if newPath else (name,)

	def getLogMessage(self, moduleName: str) -> str:
		return (
			f"{moduleName}.{self.name} is deprecated. Use {self.newModule}.{'.'.join(self.newPath)} instead."
		)

	@property
	def value(self):
		# Get the new module in which the symbol is defined.
		value = import_module(self.newModule)
		# And iteratively drill down to get the actual symbol.
		for segment in self.newPath:
			value = getattr(value, segment)
		return value


class RemovedSymbol(DeprecatedSymbol):
	"""A symbol which has been removed from the public API."""

	def __init__(
		self,
		name: str,
		value: Any,
		*,
		callValue: bool = False,
		message: str = "No public replacement is planned.",
	):
		"""Initialiser.

		:param name: Old name of the symbol.
		:param value: Old value of the symbol.
		:param callValue: Whether to treat the value as a callable that should be called to get the actual value.
		:param message: _description_, defaults to "No public replacement is planned."
		"""
		super().__init__(name)
		self._value = value
		self._callValue = callValue
		self._extraMessage = message

	@property
	def value(self) -> Any:
		if self._callValue:
			return self._value()
		return self._value

	def getLogMessage(self, moduleName: str) -> str:
		return f"{moduleName}.{self.name} is deprecated. {self._extraMessage}"


def _getCallerModule(level: int = 0) -> ModuleType:
	"""Get the module from which this was called.

	..note::
		This function will not work on stackless python implementations,
		and may not work on implementations other than cpython.

	:param level: Number of stack frames to skip, defaults to ``0``.
		This can be used if calling from a helper function to skip the stack frame created by the helper.
	:return: The module from which this function was called.
	"""
	moduleName = inspect.stack()[level + 1].frame.f_globals["__name__"]
	return sys.modules[moduleName]


def handleDeprecations(
	*deprecated: DeprecatedSymbol,
) -> Callable[[str], Any]:
	"""Get a function that can be used as a module's ``__getattr__`` for handling deprecated symbols in the public API.

	:param *deprecated: Symbols deprecated in the calling module's namespace.
	:return: A function which can be used as a module's ``__getattr__``.
	"""
	# Get the name of the calling module.
	modName = _getCallerModule(1).__name__
	# Place the symbols into an indexable data structure for more efficient access.
	deprecatedSymbols = {symbol.name: symbol for symbol in deprecated}

	def module_getattr(attrName: str) -> Any:
		if NVDAState._allowDeprecatedAPI():
			if attrName in deprecatedSymbols:
				# Import late to avoid circular import
				from logHandler import log

				deprecatedSymbol = deprecatedSymbols[attrName]
				# TODO: #17783: switch to using warnings.warn when NVDA's support for it matures.
				log.warning(
					deprecatedSymbol.getLogMessage(modName),
					stack_info=True,
					# TODO: #18785: add stacklevel parameter so the stack trace is less noisy
				)
				return deprecatedSymbol.value
		raise AttributeError(f"module {modName!r} has no attribute {attrName!r}")

	return module_getattr
'''

#: speechDictHandler/__init__.py: what NVDA 2026.2 answers for a name it no longer has.
NVDA_SPEECH_DICT_HANDLER = r'''
__getattr__ = handleDeprecations(
	MovedSymbol("speechDictsPath", "NVDAState", "WritePaths", "speechDictsDir"),
	MovedSymbol("ENTRY_TYPE_ANYWHERE", "speechDictHandler.types", "EntryType", "ANYWHERE"),
	MovedSymbol("ENTRY_TYPE_WORD", "speechDictHandler.types", "EntryType", "WORD"),
	MovedSymbol("ENTRY_TYPE_REGEXP", "speechDictHandler.types", "EntryType", "REGEXP"),
	MovedSymbol("SpeechDict", "speechDictHandler.types"),
	MovedSymbol("SpeechDictEntry", "speechDictHandler.types"),
	RemovedSymbol(
		"dictionaries",
		lambda: {
			d.source: d.dictionary for d in definitions._speechDictDefinitions if d.source in DictionaryType
		},
		callValue=True,
	),
	RemovedSymbol("dictTypes", tuple(t.value for t in DictionaryType)),
)
'''

#: speechDictHandler/types.py.
NVDA_SPEECH_DICT_TYPES = r'''
class EntryType(DisplayStringIntEnum):
	"""Types of speech dictionary entries:"""

	ANYWHERE = 0
	"""String can match anywhere"""
	REGEXP = 1
	"""Regular expression"""
	WORD = 2
	"""String must have word boundaries on both sides to match"""
	PART_OF_WORD = 3
	"""String must be preceded or followed by a word character (letter, digit, or underscore) to match."""
	START_OF_WORD = 4
	"""String must have a word boundary at the start and a word character (letter, digit, or underscore) at the end."""
	END_OF_WORD = 5
	"""String must have a word character (letter, digit, or underscore) at the start and a word boundary at the end."""
	UNIX = 6
	"""Unix shell-style wildcards."""

	@cached_property
	def _displayStringLabels(self) -> dict[Self, str]:
		return {
			# Translators: This is a label for an Entry Type radio button in add dictionary entry dialog.
			EntryType.ANYWHERE: _("&Anywhere"),
			# Translators: This is a label for an Entry Type radio button in add dictionary entry dialog.
			EntryType.REGEXP: _("Regular &expression"),
			# Translators: This is a label for an Entry Type radio button in add dictionary entry dialog.
			EntryType.WORD: _("Whole &word"),
			# Translators: This is a label for an Entry Type radio button in add dictionary entry dialog.
			EntryType.PART_OF_WORD: _("&Part of word"),
			# Translators: This is a label for an Entry Type radio button in add dictionary entry dialog.
			EntryType.START_OF_WORD: _("&Start of word"),
			# Translators: This is a label for an Entry Type radio button in add dictionary entry dialog.
			EntryType.END_OF_WORD: _("E&nd of word"),
			# Translators: This is a label for an Entry Type radio button in add dictionary entry dialog.
			EntryType.UNIX: _("&Unix shell-style wildcards"),
		}


def _selectRegexEngine(entryType: "EntryType") -> ModuleType:
	"""Return the regex module to use for compiling a SpeechDictEntry of the
	given type.

	Word-boundary entry types always use the `regex` module under VERSION1
	semantics so combining marks are included in \\w. The REGEXP type uses
	`regex` only when the ``speechDictsUseModernRegex`` feature flag is enabled.
	Other types use the stdlib `re` module.
	"""
	if entryType in (
		EntryType.WORD,
		EntryType.PART_OF_WORD,
		EntryType.START_OF_WORD,
		EntryType.END_OF_WORD,
	):
		return regex
	if entryType is EntryType.REGEXP and config.conf["featureFlag"]["speechDictsUseModernRegex"]:
		return regex
	return re


class DictionaryType(DisplayStringStrEnum):
	"""Types of speech dictionaries."""

	TEMP = "temp"
	"""Temporary speech dictionary."""
	VOICE = "voice"
	"""Voice specific speech dictionary."""
	DEFAULT = "default"
	"""Default speech dictionary."""
	BUILTIN = "builtin"
	"""Built-in speech dictionary."""

	@cached_property
	def _displayStringLabels(self) -> dict[Self, str]:
		return {
			# Translators: A type of speech dictionary.
			DictionaryType.TEMP: _("Temporary"),
			# Translators: A type of speech dictionary.
			DictionaryType.VOICE: _("Voice specific"),
			# Translators: A type of speech dictionary.
			DictionaryType.DEFAULT: _("Default"),
			# Translators: A type of speech dictionary.
			DictionaryType.BUILTIN: _("Built-in"),
		}


@dataclass
class SpeechDictEntry:
	pattern: str
	"""The pattern to match."""
	replacement: str
	"""The replacement string."""
	comment: str = ""
	"""A comment associated with this entry."""
	caseSensitive: bool = True
	"""Whether the match is case sensitive."""
	type: EntryType = EntryType.ANYWHERE
	"""The type of the entry."""
	compiled: "re.Pattern[str] | regex.Pattern[str]" = field(init=False)
	"""The compiled regular expression. May be a `re.Pattern` or a
	`regex.Pattern` depending on the entry type."""

	def __post_init__(self):
		engine = _selectRegexEngine(self.type)
		flags = engine.UNICODE
		if engine is regex:
			flags |= regex.VERSION1
		if not self.caseSensitive:
			flags |= engine.IGNORECASE
		match self.type:
			case EntryType.REGEXP:
				tempPattern = self.pattern
			case EntryType.WORD:
				tempPattern = rf"\b{engine.escape(self.pattern)}\b"
			case EntryType.PART_OF_WORD:
				escaped = engine.escape(self.pattern)
				tempPattern = rf"(?<=\w){escaped}|{escaped}(?=\w)"
			case EntryType.START_OF_WORD:
				tempPattern = rf"\b{engine.escape(self.pattern)}(?=\w)"
			case EntryType.END_OF_WORD:
				tempPattern = rf"(?<=\w){engine.escape(self.pattern)}\b"
			case EntryType.UNIX:
				# fnmatch.translate appends \Z to the end of the pattern; discard that anchor.
				translated = fnmatch.translate(self.pattern)
				suffix = r"\Z"
				if translated.endswith(suffix):
					tempPattern = translated.removesuffix(suffix)
				else:
					tempPattern = translated
			case _:
				tempPattern = engine.escape(self.pattern)
				self.type = EntryType.ANYWHERE  # Ensure sane values.
		self.compiled = engine.compile(tempPattern, flags)

	def sub(self, text: str) -> str:
		if self.type == EntryType.REGEXP:
			replacement = self.replacement
		else:
			# Escape the backslashes for non-regexp replacements
			replacement = self.replacement.replace("\\", "\\\\")
		return self.compiled.sub(replacement, text)


class SpeechDict(list[SpeechDictEntry]):
	fileName: str | None = None

	def __repr__(self) -> str:
		return f"{self.__class__.__name__} ({len(self)} entries, fileName={self.fileName})"

	def load(self, fileName: str, raiseOnError: bool = False) -> None:
		self.fileName = fileName
		comment = ""
		self.clear()
		log.debug("Loading speech dictionary %r...", fileName)
		if not os.path.isfile(fileName):
			msg = f"file {fileName!r} not found."
			if raiseOnError:
				raise FileNotFoundError(msg)
			log.debug(msg)
			return
		with open(fileName, encoding="utf_8_sig", errors="replace") as file:
			for line in file:
				if line.isspace():
					comment = ""
					continue
				line = line.rstrip("\r\n")
				if line.startswith("#"):
					if comment:
						comment += " "
					comment += line[1:]
				else:
					temp = line.split("\t")
					if len(temp) == 4:
						pattern = temp[0].replace(r"\#", "#")
						replace = temp[1].replace(r"\#", "#")
						try:
							dictionaryEntry = SpeechDictEntry(
								pattern,
								replace,
								comment,
								caseSensitive=bool(int(temp[2])),
								type=EntryType(int(temp[3])),
							)
							self.append(dictionaryEntry)
						except Exception as e:
							msg = f"Dictionary {fileName!r} entry invalid for {line!r}"
							if raiseOnError:
								raise ValueError(msg) from e
							log.exception(msg)
						comment = ""
					else:
						msg = f"can't parse line {line!r}"
						if raiseOnError:
							raise ValueError(msg)
						log.warning(msg)
			log.debug("%d loaded records.", len(self))

	def save(self, fileName: str | None = None):
		if not shouldWriteToDisk():
			log.debugWarning("Not writing dictionary, as shouldWriteToDisk returned False.")
			return
		if not fileName:
			fileName = getattr(self, "fileName", None)
		if not fileName:
			return
		dirName = os.path.dirname(fileName)
		if not os.path.isdir(dirName):
			os.makedirs(dirName)
		with open(fileName, "w", encoding="utf_8_sig", errors="replace") as file:
			for entry in self:
				if entry.comment:
					file.write(f"#{entry.comment}\n")
				pattern = entry.pattern.replace("#", r"\#")
				replacement = entry.replacement.replace("#", r"\#")
				file.write(f"{pattern}\t{replacement}\t{entry.caseSensitive:d}\t{entry.type:d}\n")

	def sub(self, text: str) -> str:
		invalidEntries = []
		for index, entry in enumerate(self):
			try:
				text = entry.sub(text)
			except (re.error, regex.error):
				dictName = self.fileName or DictionaryType.TEMP.value
				log.exception("Invalid dictionary entry %d in %r: %r", index + 1, dictName, entry.pattern)
				invalidEntries.append(index)
		for index in reversed(invalidEntries):
			del self[index]
		return text


@dataclass(frozen=True, kw_only=True)
class SpeechDictDefinition:
	"""An abstract class for a speech dictionary definition."""

	name: str
	"""The name of the dictionary."""

	path: str | None = None
	"""The path to the dictionary."""

	source: DictionaryType | str
	"""The source of the dictionary."""

	displayName: str | None = None
	"""The translatable name of the dictionary.
	When not provided, the dictionary can not be visible to the end user.
	"""

	mandatory: bool = False
	"""Whether this dictionary is mandatory.
	Mandatory dictionaries are always enabled."""

	dictionary: SpeechDict = field(init=False, repr=False, compare=False, default_factory=SpeechDict)

	def __post_init__(self):
		if not self.displayName and not self.mandatory:
			raise ValueError("A non-mandatory dictionary without a display name is unsupported")
		if self.path:
			self.dictionary.load(self.path, raiseOnError=self.source not in DictionaryType)

	@property
	def readOnly(self) -> bool:
		"""Whether this dictionary is read-only."""
		return self.source not in DictionaryType

	@property
	def userVisible(self) -> bool:
		"""Whether this dictionary is visible to end users (i.e. in the GUI).
		Mandatory dictionaries are hidden.
		"""
		return not self.mandatory and bool(self.displayName)

	@property
	def enabled(self) -> bool:
		return self.mandatory or self.name in config.conf["speech"]["speechDictionaries"]

	def sub(self, text: str) -> str:
		"""Applies the dictionary to the given text.
		:param text: The text to apply the dictionary to.
		:return: The text after applying the dictionary.
		"""
		return self.dictionary.sub(text)
'''

NVDA_CODE_FILES = {
	"NVDA_SCRIPTABLE_OBJECT": "baseObject.py",
	"NVDA_SCRIPT_DECORATOR": "scriptHandler.py",
	"NVDA_GESTURE_MAPS": "inputCore.py",
	"NVDA_GET_ALL_GESTURE_MAPPINGS": "inputCore.py",
	"NVDA_SCRIPT_CATEGORIES": "globalCommands.py",
	"NVDA_GLOBAL_COMMAND_SCRIPTS": "globalCommands.py",
	"NVDA_DEPRECATE": "utils/_deprecate.py",
	"NVDA_SPEECH_DICT_HANDLER": "speechDictHandler/__init__.py",
	"NVDA_SPEECH_DICT_TYPES": "speechDictHandler/types.py",
}

# -- Columns Review 5.7.0's own code, word for word -----------------------------------------------------------------

#: globalPlugins/columnsReview/commonFunc.py.
COLUMNS_REVIEW_SCRIPT_GESTURES = r'''
def getScriptGestures(*args):
	from inputCore import manager
	allGestures = manager.getAllGestureMappings()
	scriptDict = {}
	for scriptFunc in args:
		scriptGestures = []
		try:
			scriptCategory = scriptFunc.category if hasattr(scriptFunc, "category") else scriptFunc.__self__.__class__.scriptCategory
			scriptDoc = scriptFunc.__doc__
			script = allGestures[scriptCategory][scriptDoc]
			scriptDict[scriptFunc] = script.gestures
		except:
			pass
	# try to avoid garbageHandler warnings
	del allGestures
	return scriptDict
'''

#: globalPlugins/columnsReview/configManager.py.
COLUMNS_REVIEW_CONFIG = r'''
class ConfigFromObject(object):

	def __init__(self, obj):
		self.obj = obj
		try:
			self.possibleTriggerName = "app:{0}".format(self.obj.appModule.appName)
		except AttributeError:
			self.possibleTriggerName = None

	@property
	def triggersApplyForObj(self):
		return (
			list(config.conf.listProfiles())
			and config.conf.profileTriggersEnabled
			and not config.conf._suspendedTriggers
			and self.possibleTriggerName is not None
			and self.possibleTriggerName in config.conf.triggersToProfiles.keys()
		)

	def getApplicableProfiles(self):
		if self.triggersApplyForObj:
			res = []
			if len(config.conf.profiles) > 1:
				profileName = config.conf.profiles[-1].name
				# avoid occasional no manual AttributeError
				# maybe due to cache updating
				if getattr(config.conf._profileCache[profileName], "manual", False):
					res.append(config.conf._profileCache[config.conf.profiles[-1].name])
			try:
				res.append(config.conf._profileCache[config.conf.triggersToProfiles[self.possibleTriggerName]])
			except KeyError:
				try:
					config.conf._getProfile(config.conf.triggersToProfiles[self.possibleTriggerName])
					res.append(config.conf._profileCache[config.conf.triggersToProfiles[self.possibleTriggerName]])
				except KeyError:
					pass
			res.append(config.conf._profileCache[None])  # Default config
			res.append(config.conf)
		else:
			res = [config.conf]
		return res

	@property
	def announceEmptyLists(self):
		for profile in self.getApplicableProfiles():
			try:
				return is_boolean(profile["columnsReview"]["general"]["announceEmptyList"])
			except KeyError:
				continue

	@property
	def announceListBounds(self):
		for profile in self.getApplicableProfiles():
			try:
				return is_boolean(profile["columnsReview"]["general"]["announceListBounds"])
			except KeyError:
				continue

	@property
	def announceListBoundsWith(self):
		for profile in self.getApplicableProfiles():
			try:
				return profile["columnsReview"]["general"]["announceListBoundsWith"]
			except KeyError:
				continue

	@property
	def topBeep(self):
		for profile in self.getApplicableProfiles():
			try:
				return int(profile["columnsReview"]["beep"]["topBeep"])
			except KeyError:
				continue

	@property
	def bottomBeep(self):
		for profile in self.getApplicableProfiles():
			try:
				return int(profile["columnsReview"]["beep"]["bottomBeep"])
			except KeyError:
				continue

	@property
	def beepLen(self):
		for profile in self.getApplicableProfiles():
			try:
				return int(profile["columnsReview"]["beep"]["beepLen"])
			except KeyError:
				continue

	@property
	def numpadUsedForColumnsNavigation(self):
		for profile in self.getApplicableProfiles():
			try:
				return is_boolean(profile["columnsReview"]["keyboard"]["useNumpadKeys"])
			except KeyError:
				continue

	@property
	def nextColumnsGroupKey(self):
		for profile in self.getApplicableProfiles():
			try:
				return profile["columnsReview"]["keyboard"]["switchChar"]
			except KeyError:
				continue

	@property
	def enabledModifiers(self):
		keys = dict()
		POSSIBLE_MODIFIERS = ("NVDA", "control", "alt", "shift", "windows")
		for profile in reversed(self.getApplicableProfiles()):
			for keyName in POSSIBLE_MODIFIERS:
				try:
					keys[keyName] = is_boolean(profile["columnsReview"]["gestures"][keyName])
				except KeyError:
					continue
		enabledKeys = dict(filter(lambda elem: elem[1], keys.items()))
		return "+".join(enabledKeys.keys())
'''

#: globalPlugins/columnsReview/compat.py.
COLUMNS_REVIEW_RANGE = r'''
def rangeFunc(*args, **kwargs):
	try:
		import six
		return six.moves.range(*args, **kwargs)
	except ImportError:
		try:
			import __builtin__
			return __builtin__.xrange(*args, **kwargs)
		except ImportError:
			return range(*args, **kwargs)
'''

#: globalPlugins/columnsReview/__init__.py.
COLUMNS_REVIEW_NOTIFIERS = r'''
PROFILE_SWITCHED_NOTIFIERS = ("configProfileSwitch", "post_configProfileSwitch")
'''

#: globalPlugins/columnsReview/__init__.py, class GlobalPlugin.
COLUMNS_REVIEW_PLUGIN = r'''
def __init__(self, *args, **kwargs):
	super(GlobalPlugin, self).__init__(*args, **kwargs)
	if globalVars.appArgs.secure:
		return
	self.createMenu()
	self.proceedWithBounds = False
	for extPointName in PROFILE_SWITCHED_NOTIFIERS:
		try:
			getattr(config, extPointName).register(self.handleConfigProfileSwitch)
		except AttributeError:
			continue


def handleConfigProfileSwitch(self):
	# We cannot iterate through original set of instances
	# since it may be mutated during iteration when new objects are created as a result of focus events.
	for inst in CRList._instances.copy():
		inst.bindCRGestures(reinitializeObj=True)
'''

#: globalPlugins/columnsReview/__init__.py, class CRList.
COLUMNS_REVIEW_LIST = r'''
def initOverlayClass(self):
	"""adds the new objects to the list of existing instances"""
	self.__class__._instances.add(self)


def bindCRGestures(self, reinitializeObj=False):
	if reinitializeObj:
		self.clearGestureBindings()
	# find gestures
	self.bindGesture("kb:NVDA+control+f", "find")
	self.bindGesture("kb:NVDA+f3", "findNext")
	self.bindGesture("kb:NVDA+shift+f3", "findPrevious")
	# other useful gesture to remap
	scriptMap = {
		# for color reporting
		getattr(commands, "script_reportOrShowFormattingAtCaret", commands.script_reportFormatting): "reportOrShowFormattingAtCaret",
		# for current selection
		commands.script_reportCurrentSelection: "reportCurrentSelection",
	}
	# for say all - bind only if it is actually supported
	if utils._RowsReader.isSupported():
		scriptMap[commands.script_sayAll] = "readListItems"
	scriptFuncs = scriptMap.keys()
	scriptGesturesMap = getScriptGestures(*scriptFuncs)
	for scriptFunc, gestures in scriptGesturesMap.items():
		for gesture in gestures:
			self.bindGesture(gesture, scriptMap[scriptFunc])
	confFromObj = configManager.ConfigFromObject(self)
	numpadUsedForColumnNav = confFromObj.numpadUsedForColumnsNavigation
	enabledModifiers = confFromObj.enabledModifiers
	# a string useful for defining gestures
	nk = "numpad" if numpadUsedForColumnNav else ""
	# bind gestures from 1 to 9
	for n in rangeFunc(1, 10):
		self.bindGesture("kb:{0}+{1}{2}".format(enabledModifiers, nk, n), "readColumn")
	if numpadUsedForColumnNav:
		# map numpadMinus for 10th column
		self.bindGesture("kb:{0}+numpadMinus".format(enabledModifiers), "readColumn")
		# ...numpadPlus to change interval
		self.bindGesture("kb:{0}+numpadPlus".format(enabledModifiers), "changeInterval")
		# delete for list item info
		self.bindGesture("kb:{0}+numpadDelete".format(enabledModifiers), "itemInfo")
		# ...and enter to headers manager
		self.bindGesture("kb:{0}+numpadEnter".format(enabledModifiers), "manageHeaders")
	else:
		# do same things for no numpad case
		self.bindGesture("kb:{0}+0".format(enabledModifiers), "readColumn")
		self.bindGesture("kb:{0}+{1}".format(enabledModifiers, confFromObj.nextColumnsGroupKey), "changeInterval")
		self.bindGesture("kb:{0}+delete".format(enabledModifiers), "itemInfo")
		self.bindGesture("kb:{0}+enter".format(enabledModifiers), "manageHeaders")


def bindGesturesForEmpty(self):
	# bind gestures to report empty
	for item in ["Up", "Down", "Left", "Right"]:
		self.bindGesture("kb:{0}Arrow".format(item), "reportEmpty")
	# other useful gesture to remap
	scriptFuncs = (
		commands.script_reportCurrentFocus,
		commands.script_reportCurrentLine,
		commands.script_reportCurrentSelection
	)
	scriptDict = getScriptGestures(*scriptFuncs)
	for script, gestures in scriptDict.items():
		for gesture in gestures:
			self.bindGesture(gesture, "reportEmpty")
'''

# -- Emoticons 38.0.0's own code, word for word ---------------------------------------------------------------------

#: globalPlugins/emoticons/__init__.py.
EMOTICONS_DICTIONARIES = r'''
defaultDic = speechDictHandler.SpeechDict()


noEmojisDic = speechDictHandler.SpeechDict()


sD = speechDictHandler.SpeechDict()


def loadDic():
	if profileName is None:
		dicFile = ADDON_DIC_DEFAULT_FILE
	else:
		dicFile = os.path.abspath(os.path.join(ADDON_DICTS_PATH, "profiles", "%s.dic" % profileName))
	sD.load(dicFile)
	if not os.path.isfile(dicFile):
		if config.conf["emoticons"]["speakAddonEmojis"]:
			sD.extend(defaultDic)
		else:
			sD.extend(noEmojisDic)


def activateAnnouncement():
	speechDictHandler.dictionaries["temp"].extend(sD)


def deactivateAnnouncement():
	for entry in sD:
		if entry in speechDictHandler.dictionaries["temp"]:
			speechDictHandler.dictionaries["temp"].remove(entry)
'''

#: globalPlugins/emoticons/__init__.py, class GlobalPlugin.
EMOTICONS_PROFILE_SWITCH = r'''
def handleConfigProfileSwitch(self):
	global profileName, oldProfileName
	profileName = config.conf.profiles[-1].name
	if profileName == oldProfileName:
		return
	deactivateAnnouncement()
	loadDic()
	if config.conf["emoticons"]["announcement"]:
		activateAnnouncement()
	oldProfileName = profileName
'''

ADDON_CODE_FILES = {
	"COLUMNS_REVIEW_SCRIPT_GESTURES": "columnsReview/globalPlugins/columnsReview/commonFunc.py",
	"COLUMNS_REVIEW_CONFIG": "columnsReview/globalPlugins/columnsReview/configManager.py",
	"COLUMNS_REVIEW_RANGE": "columnsReview/globalPlugins/columnsReview/compat.py",
	"COLUMNS_REVIEW_NOTIFIERS": "columnsReview/globalPlugins/columnsReview/__init__.py",
	"COLUMNS_REVIEW_PLUGIN": "columnsReview/globalPlugins/columnsReview/__init__.py",
	"COLUMNS_REVIEW_LIST": "columnsReview/globalPlugins/columnsReview/__init__.py",
	"EMOTICONS_DICTIONARIES": "emoticons/globalPlugins/emoticons/__init__.py",
	"EMOTICONS_PROFILE_SWITCH": "emoticons/globalPlugins/emoticons/__init__.py",
}


def _(text):
	return text


Smiley = collections.namedtuple("Smiley", "pattern name chars isEmoji")
#: Emoticons 38.0.0, globalPlugins/emoticons/smileysList.py: its 88 emoticons (the emoji left out), word for word.
EMOTICONS_SMILEYS_SOURCE = r'''
	# Translators: :) Smile
	Smiley(r"(\s|^)(:([\-]|)([)]{1})(\B|\s|$))", _("smiling smiley"), r":-)", False),
	# Translators: :( Sad face.
	Smiley(r"(\s|^)(:([\-]|)([(]{1})\B)", _("Sad face"), r":-(", False),
	# Translators: :D Laugh
	Smiley(r"(\s|^)(:([\-]|)([D]{1,})\b)", _("Laughing smiley"), r":-D", False),
	# Translators: :@ angry face.
	Smiley(r"(\s|^)(:([\-]|)([@]{1})(\B|\s|$))", _("Angry face"), r":@", False),
	# Translators: :O Surprised
	Smiley(r"(\s|^)(:([\-]|)([O]{1})(\W|\s|$))", _("surprised smiley"), r":O", False),
	# Translators: ;) Wink;
	Smiley(r"(\s|^)(;([\-]|)([)D]{1})(\B|\s|$))", _("winking smiley"), r";)", False),
	# Translators: ;( Crying
	Smiley(r"(\s|^)(;([\-]|)([(]{1})(\B|\s|$))", _("crying smiley"), r";(", False),
	# Translators: :s :-S :-Q Confused face:
	Smiley(r"(\s|^)(:([\-]|)([sSQ$])(\b|\s|$))", _("Confused Face"), r":s", False),
	# Translators: (:| Sweating
	Smiley(r"(\s|^)\((:[\|])(\B|\s|$)", _("sweating smiley"), r"(:|", False),
	# Translators: :|] Robot (a robot head)
	Smiley(r"(\s|^)(:[\|][\]])(\W|\s|$)", _("Robot Smiley"), r":|]", False),
	# Translators: :| Speechless
	Smiley(r"(\s|^)(:[\|])(\B|\s|$)", _("speechless smiley"), r":|", False),
	# Translators: :* Kiss
	Smiley(r"(\s|^)(:([\-]|)([\*]{1})(\B|\s|$))", _("kiss smiley"), r":*", False),
	# Translators: :P Cheeky
	Smiley(r"(\s|^)(:([\-]|)([pP])(\W|\s|$))", _("cheeky smiley"), r":P", False),
	# Translators: :$ Blushing
	Smiley(r"(\s|^)(:[\$])(\B|\s|$)", _("blushing smiley"), r":$", False),
	# Translators: :^) Wondering
	Smiley(r"(\s|^)(:[\^][\)])(\B|\s|$)", _("wondering smiley"), r":^)", False),
	# Translators: |-) Sleepy
	Smiley(r"(\s|^)([\|][\-][\)])(\B|\s|$)", _("sleepy smiley"), r"|-)", False),
	# Translators: |-( Dull
	Smiley(r"(\s|^)([\|][\-][\(])(\B|\s|$)", _("dull smiley"), r"|-(", False),
	# Translators: :x My lips are sealed
	Smiley(r"(\s|^)(:([\-]|)([xX])\b)", _("my lips are sealed smiley"), r":x", False),
	# Translators: \o/ Dancing
	Smiley(r"(\s|^)([\\]o[/])(\B|\s|$)", _("dancing smiley"), r"\o/", False),
	# Translators: :'( crying a lot smiley
	Smiley(r"(\s|^)([:]['][\(])(\B|\s|$)", _("crying a lot smiley"), r":'(", False),
	# Translators: >:( Angry
	Smiley(r"(\s|^)(>:[\(])(\B|\s|$)", _("angry smiley"), r">:(", False),
	# Translators: :/ Worried
	Smiley(r"(\s|^)(:[/])(\B|\s|$)", _("worried smiley"), r":/", False),
	# Translators: <3 Heart
	Smiley(r"(\s|^)<3(\W|\s|$)", _("heart smiley"), r"<3", False),
	# Translators:  O:)  O:-) Angel
	Smiley(r"(\s|^)(O:([\-]|)([)])(\W|\s|$))", _("Angel Smiley"), r"O:)", False),
	# Translators:  O.o  o.O  Confused
	Smiley(r"(\s|^)[Oo][\.][oO](\B|\s|$)", _("Confused Smiley"), r"O.o", False),
	# Translators:   3:-) Devil
	Smiley(r"(\s|^)(3:([\-]|)([\)]))(\B|\s|$)", _("Devil Smiley"), r"3:-)", False),
	# Translators:  ^_^ Keke (This smiley is inspired by the Asian style, which is a happy face.)
	Smiley(r"(\s|^)[\^]_[\^](\B|\s|$)", _("Keke Smiley"), r"^_^", False),
	# Translators: -_- Bored (This smiley face has its eyes closed and is sporting a very small grin.)
	Smiley(r"(\s|^)[\-]_[\-](\B|\s|$)", _("Bored smiley"), r"-_-", False),
	# Translators:  >:O  Upset, angry or shouting...
	Smiley(r"(\s|^)(>:O)(\W|\s|$)", _("Angry Smiley"), r">:O", False),
	# Translators:  :3  Cat (Cat faced smiley with curly lips)
	Smiley(r"(\s|^)(:3)(\W|\s|$)", _("Cat Smiley"), r":3", False),
	# Translators: (-.-)ZZZ Iӭ Sleepy
	Smiley(r"(\s|^)\([-][\.][-]\)ZZZ(\B|\s|$)", _("I am Sleepy smiley"), r"(-.-)ZZZ", False),
	# Translators: 8-) Glasses
	Smiley(r"(\s|^)8[-][)](\B|\s|$)", _("glasses smiley"), r"8-)", False),
	# Translators: (^^^) shark
	Smiley(r"(\s|^)\([\^]{3}\)(\B|\s|$)", _("shark smiley"), r"(^^^)", False),
	# Translators: (worry) Worried
	Smiley(r"(\s|^)\(worry\)(\B|\s|$)", _("worried smiley"), r"(worry)", False),
	# Translators:  (cash) Cash
	Smiley(r"(\s|^)\(cash\)(\B|\s|$)", _("cash smiley"), r"(cash)", False),
	# Translators: (flex) Muscle
	Smiley(r"(\s|^)\(flex\)(\B|\s|$)", _("muscle smiley"), r"(flex)", False),
	# Translators: (beer) Beer
	Smiley(r"(\s|^)\(beer\)(\B|\s|$)", _("beer smiley"), r"(beer)", False),
	# Translators: (d) Drink
	Smiley(r"(\s|^)\(d\)(\B|\s|$)", _("drink smiley"), r"(d)", False),
	# Translators: (ninja) Ninja
	Smiley(r"(\s|^)\(ninja\)(\B|\s|$)", _("ninja smiley"), r"(ninja)", False),
	# Translators: (cool) Cool
	Smiley(r"(\s|^)\(cool\)(\B|\s|$)", _("cool smiley"), r"(cool)", False),
	# Translators: (inlove) In Love
	Smiley(r"(\s|^)\(inlove\)(\B|\s|$)", _("in love smiley"), r"(inlove)", False),
	# Translators: (yn) Fingers crossed
	Smiley(r"(\s|^)([\(]yn[\)])(\B|\s|$)", _("fingers crossed smiley"), r"(yn)", False),
	# Translators: (yawn) Yawn
	Smiley(r"(\s|^)\(yawn\)(\B|\s|$)", _("yawning smiley"), r"(yawn)", False),
	# Translators: (puke) Puking
	Smiley(r"(\s|^)\(puke\)(\B|\s|$)", _("puking smiley"), r"(puke)", False),
	# Translators: (doh) Doh!
	Smiley(r"(\s|^)\(doh\)(\B|\s|$)", _("doh! smiley"), r"(doh)", False),
	# Translators: (angry) Angry
	Smiley(r"(\s|^)\(angry\)(\B|\s|$)", _("angry smiley"), r"(angry)", False),
	# Translators: (wasntme) It wasn't me!
	Smiley(r"(\s|^)\(wasntme\)(\B|\s|$)", _("it wasn't me! smiley"), r"(wasntme)", False),
	# Translators: (party) Party
	Smiley(r"(\s|^)\(party\)(\B|\s|$)", _("party smiley"), r"(party)", False),
	# Translators: (mm) Mmmm...
	Smiley(r"(\s|^)\(mm\)(\B|\s|$)", _("mmmmmm... smiley"), r"(mm)", False),
	# Translators: (nerd) Nerdy
	Smiley(r"(\s|^)\(nerd\)(\B|\s|$)", _("nerdy smiley"), r"(nerd)", False),
	# Translators: (wave) Hi
	Smiley(r"(\s|^)\(wave\)(\B|\s|$)", _("hi smiley"), r"(wave)", False),
	# Translators: (facepalm) Facepalm
	Smiley(r"(\s|^)\(facepalm\)(\B|\s|$)", _("facepalm smiley"), r"(facepalm)", False),
	# Translators: (devil) Devil
	Smiley(r"(\s|^)\(devil\)(\B|\s|$)", _("devil smiley"), r"(devil)", False),
	# Translators: (angel) Angel
	Smiley(r"(\s|^)\(angel\)(\B|\s|$)", _("angel smiley"), r"(angel)", False),
	# Translators: (envy) Envy
	Smiley(r"(\s|^)\(envy\)(\B|\s|$)", _("envy smiley"), r"(envy)", False),
	# Translators: (wait) Wait
	Smiley(r"(\s|^)\(wait\)(\B|\s|$)", _("wait smiley"), r"(wait)", False),
	# Translators: (hug) Hug
	Smiley(r"(\s|^)\(hug\)(\B|\s|$)", _("hug smiley"), r"(hug)", False),
	# Translators: (makeup) Make-up
	Smiley(r"(\s|^)\(makeup\)(\B|\s|$)", _("make-up smiley"), r"(makeup)", False),
	# Translators: (chuckle) Giggle
	Smiley(r"(\s|^)\(chuckle\)(\B|\s|$)", _("giggle smiley"), r"(chuckle)", False),
	# Translators: (clap) Clapping
	Smiley(r"(\s|^)\(clap\)(\B|\s|$)", _("clapping smiley"), r"(clap)", False),
	# Translators: (think) Thinking
	Smiley(r"(\s|^)\(think\)(\B|\s|$)", _("thinking smiley"), r"(think)", False),
	# Translators: (bow) Bowing
	Smiley(r"(\s|^)\(bow\)(\B|\s|$)", _("bowing smiley"), r"(bow)", False),
	# Translators: (rofl) Rolling on the floor laughing
	Smiley(r"(\s|^)\(rofl\)(\B|\s|$)", _("rolling on the floor laughing! smiley"), r"(rofl)", False),
	# Translators: (whew) Relieved
	Smiley(r"(\s|^)\(whew\)(\B|\s|$)", _("relieved smiley"), r"(whew)", False),
	# Translators: (happy) Happy
	Smiley(r"(\s|^)\(happy\)(\B|\s|$)", _("happy smiley"), r"(happy)", False),
	# Translators: (smirk) Smirking
	Smiley(r"(\s|^)\(smirk\)(\B|\s|$)", _("smirking smiley"), r"(smirk)", False),
	# Translators: (nod) Nodding
	Smiley(r"(\s|^)\(nod\)(\B|\s|$)", _("nodding smiley"), r"(nod)", False),
	# Translators: (shake) Shake
	Smiley(r"(\s|^)\(shake\)(\B|\s|$)", _("shakeing smiley"), r"(shake)", False),
	# Translators: (waiting) Waiting
	Smiley(r"(\s|^)\(waiting\)(\B|\s|$)", _("waiting smiley"), r"(waiting)", False),
	# Translators: (emo) Emo;
	Smiley(r"(\s|^)\(emo\)(\B|\s|$)", _("Emo smiley"), r"(emo)", False),
	# Translators: (y) Yes
	Smiley(r"(\s|^)\(y\)(\B|\s|$)", _("yes smiley"), r"(y)", False),
	# Translators: (n) no;
	Smiley(r"(\s|^)\(n\)(\B|\s|$)", _("no smiley"), r"(n)", False),
	# Translators: (handshake) Handshake
	Smiley(r"(\s|^)\(handshake\)(\B|\s|$)", _("handshake smiley"), r"(handshake)", False),
	# Translators: (highfive) High five
	Smiley(r"(\s|^)\(highfive\)(\B|\s|$)", _("high five smiley"), r"(highfive)", False),
	# Translators: (heart) Heart
	Smiley(r"(\s|^)\(heart\)(\B|\s|$)", _("heart smiley"), r"(heart)", False),
	# Translators: (lalala) Lalala;
	Smiley(r"(\s|^)\(lalala\)(\B|\s|$)", _("lalala smiley"), r"(lalala)", False),
	# Translators: (heidy) Heidy;
	Smiley(r"(\s|^)\(heidy\)(\B|\s|$)", _("heidy smiley"), r"(heidy)", False),
	# Translators: (F) Flower
	Smiley(r"(\s|^)\(F\)(\B|\s|$)", _("flower smiley"), r"(F)", False),
	# Translators: (rain) Raining
	Smiley(r"(\s|^)\(rain\)(\B|\s|$)", _("raining smiley"), r"(rain)", False),
	# Translators: (sun) Sun
	Smiley(r"(\s|^)\(sun\)(\B|\s|$)", _("sunny smiley"), r"(sun)", False),
	# Translators: (tumbleweed) Tumbleweed
	Smiley(r"(\s|^)\(tumbleweed\)(\B|\s|$)", _("tumbleweed smiley"), r"(tumbleweed)", False),
	# Translators: (music) Music
	Smiley(r"(\s|^)\(music\)(\B|\s|$)", _("music smiley"), r"(music)", False),
	# Translators: (bandit) Bandit
	Smiley(r"(\s|^)\(bandit\)(\B|\s|$)", _("bandit smiley"), r"(bandit)", False),
	# Translators: (tmi) Too much information
	Smiley(r"(\s|^)\(tmi\)(\B|\s|$)", _("too much information smiley"), r"(tmi)", False),
	# Translators: (coffee) Coffee
	Smiley(r"(\s|^)\(coffee\)(\B|\s|$)", _("coffee smiley"), r"(coffee)", False),
	# Translators: (pi) Pizza
	Smiley(r"(\s|^)\(pi\)(\B|\s|$)", _("pizza smiley"), r"(pi)", False),
	# Translators: (^) Cake
	Smiley(r"(\s|^)([\(][\^][\)])(\B|\s|$)", _("cake smiley"), r"(^)", False),
	# Translators: (*) Star
	Smiley(r"(\s|^)([\(][\*][\)])(\B|\s|$)", _("star smiley"), r"(*)", False),
'''
EMOTICONS_SMILEYS = eval(f"[\n{EMOTICONS_SMILEYS_SOURCE}\n]", {"Smiley": Smiley, "_": _})

# -- the imitation NVDA ---------------------------------------------------------------------------------------------

#: Columns Review's own scripts, which its bindCRGestures binds keys to; what they do doesn't matter here.
IMITATION_CR_LIST = r'''
_instances = weakref.WeakSet()
scriptCategory = "Columns Review (DO NOT EDIT!)"

def script_find(self, gesture):
	pass

def script_findNext(self, gesture):
	pass

def script_findPrevious(self, gesture):
	pass

def script_readListItems(self, gesture):
	pass

def script_reportOrShowFormattingAtCaret(self, gesture):
	pass

def script_reportCurrentSelection(self, gesture):
	pass

def script_readColumn(self, gesture):
	pass

def script_changeInterval(self, gesture):
	pass

def script_itemInfo(self, gesture):
	pass

def script_manageHeaders(self, gesture):
	pass

def script_reportEmpty(self, gesture):
	pass
'''

#: Columns Review's menu in NVDA's Settings, which its __init__ adds; nothing here.
IMITATION_CR_PLUGIN = r'''
def createMenu(self):
	pass
'''

#: Emoticons' GlobalPlugin.__init__, the parts about its dictionary: the rest makes its menus.
IMITATION_EMOTICONS_PLUGIN = r'''
def __init__(self):
	super(GlobalPlugin, self).__init__()
	SpeechDictEntry, REGEXP = speechDictHandler.SpeechDictEntry, speechDictHandler.ENTRY_TYPE_REGEXP
	for em in emoticons:
		emType = "Emoji" if em.isEmoji else "Emoticon"
		comment = "{type}: {name}".format(type=emType, name=em.name)
		otherReplacement = " %s; " % em.name
		defaultDic.append(SpeechDictEntry(em.pattern, otherReplacement, comment, True, REGEXP))
		if not em.isEmoji:
			noEmojisDic.append(SpeechDictEntry(em.pattern, otherReplacement, comment, True, REGEXP))
	global profileName, oldProfileName
	profileName = oldProfileName = config.conf.profiles[-1].name
	loadDic()
	announcement = config.conf["emoticons"]["announcement"]
	if announcement:
		activateAnnouncement()
	config.post_configProfileSwitch.register(self.handleConfigProfileSwitch)
'''

DEPRECATED = "speechDictHandler.dictionaries is deprecated. No public replacement is planned."


class Records(logging.Handler):
	"""NVDA's log, as its handler gets it: each warning with its stack, as NVDA writes it (stack_info=True)."""

	def __init__(self):
		super().__init__(logging.DEBUG)
		self.records = []

	def emit(self, record):
		self.format(record)
		self.records.append(record)


class DisplayStringIntEnum(enum.IntEnum):
	pass


class DisplayStringStrEnum(str, enum.Enum):
	pass


class Profile(dict):
	"""An NVDA configuration profile: its sections, and its name (None for the normal configuration)."""

	def __init__(self, name, manual=False, sections=None):
		super().__init__(sections or {})
		self.name = name
		self.manual = manual


class Action:
	"""NVDA's extensionPoints.Action: a handler that is a bound method is kept by a weak reference to its object and
	function (extensionPoints.util.BoundMethodWeakref), so replacing the function on the class later changes nothing."""

	def __init__(self):
		self._handlers = []

	def register(self, handler):
		self._handlers.append(weakref.WeakMethod(handler) if inspect.ismethod(handler) else (lambda handler=handler: handler))

	def unregister(self, handler):
		self._handlers = [ref for ref in self._handlers if ref() != handler]

	def notify(self, **kwargs):
		for ref in list(self._handlers):
			handler = ref()
			if handler is not None:
				handler()


class ConfigManager:
	"""config.conf: what Columns Review and Emoticons read, and NVDA's order of profiles (a program's triggered profile
	before a manual one, as the tester's log shows: ['normal configuration', 'JAWS - msedge', 'browseMode'])."""

	def __init__(self, action, profilesDir):
		self.post_configProfileSwitch = action
		self.profilesDir = profilesDir
		self.base = Profile(
			None,
			sections={
				"columnsReview": {
					"general": {"announceEmptyList": True, "announceListBounds": True, "announceListBoundsWith": "voice"},
					"beep": {"topBeep": 620, "bottomBeep": 440, "beepLen": 100},
					"keyboard": {"useNumpadKeys": False, "switchChar": "-"},
					"gestures": {"NVDA": True, "control": True, "alt": False, "shift": False, "windows": False},
				},
				"emoticons": {"announcement": 1, "speakAddonEmojis": False, "speakInsertedSymbols": False, "cleanDicts": False},
				"featureFlag": {"speechDictsUseModernRegex": False},
			},
		)
		self.profiles = [self.base]
		self._profileCache = {None: self.base}
		self.triggersToProfiles = {"app:msedge": "JAWS - msedge"}
		self.profileTriggersEnabled = True
		self._suspendedTriggers = None
		for name in ("browseMode", "JAWS - msedge", "JAWS - 1password", "kitchen games"):
			open(os.path.join(profilesDir, f"{name}.ini"), "w").close()

	def __getitem__(self, key):
		for profile in reversed(self.profiles):
			if key in profile:
				return profile[key]
		raise KeyError(key)

	def listProfiles(self):
		for name in os.listdir(self.profilesDir):
			name, ext = os.path.splitext(name)
			if ext == ".ini":
				yield name

	def _getProfile(self, name):
		profile = self._profileCache.get(name)
		if profile is None:
			profile = self._profileCache[name] = Profile(name)
		return profile

	def _switched(self):
		self.post_configProfileSwitch.notify()

	def manualActivateProfile(self, name):
		if self.profiles[-1].manual:
			del self.profiles[-1]
		if name is not None:
			profile = self._getProfile(name)
			profile.manual = True
			self.profiles.append(profile)
		self._switched()

	def enterTrigger(self, spec):
		profile = self._getProfile(self.triggersToProfiles[spec])
		index = len(self.profiles) - 1 if self.profiles[-1].manual else len(self.profiles)
		self.profiles.insert(index, profile)
		self._switched()

	def exitTrigger(self, spec):
		self.profiles.remove(self._getProfile(self.triggersToProfiles[spec]))
		self._switched()


def module(name, **attributes):
	made = types.ModuleType(name)
	vars(made).update(attributes)
	return made


class Nvda:
	"""NVDA 2026.2 with Columns Review 5.7.0 and Emoticons 38.0.0, as the tester has them, and the focus in Outlook's
	message list after File Explorer's list: two lists Columns Review has seen."""

	def __init__(self, test, nvdaVersion="2026.2"):
		self.test = test
		self.records = Records()
		self.log = logging.Logger(f"nvda-{id(self)}", logging.DEBUG)
		self.log.addHandler(self.records)
		self.log.debugWarning = self.log.debug
		self.log.io = self.log.debug
		folder = tempfile.TemporaryDirectory()
		test.addCleanup(folder.cleanup)
		os.makedirs(os.path.join(folder.name, "profiles"))
		os.makedirs(os.path.join(folder.name, "emoticons", "profiles"))
		# Each of the imitation's modules is where NVDA's code imports it from as soon as it is made.
		patcher = mock.patch.dict(sys.modules)
		patcher.start()
		test.addCleanup(patcher.stop)
		self.modules = {}

		def add(name, made):
			self.modules[name] = sys.modules[name] = made

		add("logHandler", module("logHandler", log=self.log))
		add("NVDAState", module("NVDAState", _allowDeprecatedAPI=lambda: True, shouldWriteToDisk=lambda: False, WritePaths=None))
		add("globalVars", module("globalVars", appArgs=types.SimpleNamespace(secure=False)))
		self.config = module("config")
		self.config.post_configProfileSwitch = Action()
		self.config.conf = ConfigManager(self.config.post_configProfileSwitch, os.path.join(folder.name, "profiles"))
		add("config", self.config)

		# baseObject and scriptHandler.
		base = {
			"garbageHandler": types.SimpleNamespace(TrackedObject=object),
			"log": self.log,
			"weakref": weakref,
			"ABCMeta": abc.ABCMeta,
			"abstractproperty": abc.abstractproperty,
		}
		v128.nvdaCode(v128.NVDA_BASE_OBJECT, "AutoPropertyObject", base)
		v128.nvdaCode(NVDA_SCRIPTABLE_OBJECT, "ScriptableObject", base)
		self.baseObject = module("baseObject", **base)
		add("baseObject", self.baseObject)
		ScriptableObject = self.baseObject.ScriptableObject
		self.scriptHandler = module("scriptHandler", types=types, log=self.log)
		v128.nvdaCode(NVDA_SCRIPT_DECORATOR, "script", vars(self.scriptHandler))
		add("scriptHandler", self.scriptHandler)

		# inputCore: the gesture maps and the list of all commands.
		self.api = module("api")
		add("api", self.api)
		# GlobalGestureMap.save runs only outside secure mode (gui.blockAction); it doesn't run here.
		blockAction = types.SimpleNamespace(when=lambda *contexts: lambda function: function, Context=types.SimpleNamespace(SECURE_MODE="secureMode"))
		self.inputCore = module("inputCore", sys=sys, log=self.log, api=self.api, baseObject=self.baseObject, blockAction=blockAction, SCRCAT_KBEMU="Emulated system keyboard keys", SCRCAT_MISC="Miscellaneous")
		v128.nvdaCode(NVDA_GESTURE_MAPS, "GlobalGestureMap", vars(self.inputCore))
		InputManager = v128.nvdaClass(
			"class InputManager(object)",
			["def __init__(self):\n\tself.userGestureMap = GlobalGestureMap()\n\tself.localeGestureMap = GlobalGestureMap()\n", NVDA_GET_ALL_GESTURE_MAPPINGS],
			vars(self.inputCore),
		)
		self.inputCore.manager = InputManager()
		add("inputCore", self.inputCore)
		self.asked = 0
		nvdasGetAllGestureMappings = self.inputCore.manager.getAllGestureMappings

		def getAllGestureMappings(*args, **kwargs):
			self.asked += 1
			return nvdasGetAllGestureMappings(*args, **kwargs)

		self.inputCore.manager.getAllGestureMappings = getAllGestureMappings

		# globalCommands: NVDA's own commands, with their own keys.
		self.globalCommands = module("globalCommands", _=_, pgettext=lambda context, text: text, script=self.scriptHandler.script, inputCore=self.inputCore, ScriptableObject=ScriptableObject)
		v128.nvdaCode(NVDA_SCRIPT_CATEGORIES, "SCRCAT_TEXTREVIEW", vars(self.globalCommands))
		GlobalCommands = v128.nvdaClass("class GlobalCommands(ScriptableObject)", [NVDA_GLOBAL_COMMAND_SCRIPTS], vars(self.globalCommands))
		self.globalCommands.commands = GlobalCommands()
		ConfigProfileActivationCommands = type("ConfigProfileActivationCommands", (ScriptableObject,), {"scriptCategory": self.globalCommands.SCRCAT_CONFIG_PROFILES})
		self.globalCommands.configProfileActivationCommands = ConfigProfileActivationCommands()
		add("globalCommands", self.globalCommands)

		self.braille = module("braille", handler=types.SimpleNamespace(display=types.SimpleNamespace(name="noBraille", gestureMap=None)))
		add("braille", self.braille)
		add("vision", module("vision", handler=types.SimpleNamespace(getActiveProviderInstances=lambda: [])))
		GlobalPlugin = type("GlobalPlugin", (ScriptableObject,), {"chooseNVDAObjectOverlayClasses": lambda self, obj, clsList: None, "terminate": lambda self: None})
		self.globalPluginHandler = module("globalPluginHandler", GlobalPlugin=GlobalPlugin, runningPlugins=set())
		add("globalPluginHandler", self.globalPluginHandler)

		# speechDictHandler, as NVDA 2026.2 has it, or with the name itself as NVDA 2026.1 has it.
		deprecate = module("utils._deprecate", inspect=inspect, sys=sys, ABC=abc.ABC, abstractmethod=abc.abstractmethod, abstractproperty=abc.abstractproperty, Callable=Callable, import_module=importlib.import_module, ModuleType=types.ModuleType, Any=typing.Any, NVDAState=self.modules["NVDAState"])
		v128.nvdaCode(NVDA_DEPRECATE, "handleDeprecations", vars(deprecate))
		add("utils", module("utils", _deprecate=deprecate))
		add("utils._deprecate", deprecate)
		regex = module("regex", **{name: getattr(re, name) for name in ("UNICODE", "IGNORECASE", "compile", "escape", "error")}, VERSION1=0)
		dictTypes = module(
			"speechDictHandler.types",
			fnmatch=fnmatch, os=os, re=re, regex=regex, dataclass=dataclasses.dataclass, field=dataclasses.field,
			cached_property=functools.cached_property, ModuleType=types.ModuleType, config=self.config, log=self.log,
			shouldWriteToDisk=lambda: False, DisplayStringIntEnum=DisplayStringIntEnum, DisplayStringStrEnum=DisplayStringStrEnum, _=_,
		)
		# Before its code: dataclasses reads the string annotations in the class's module.
		add("speechDictHandler.types", dictTypes)
		v128.nvdaCode(NVDA_SPEECH_DICT_TYPES, "SpeechDict", vars(dictTypes))
		definitions = module("speechDictHandler.definitions")
		definitions._speechDictDefinitions = [
			dictTypes.SpeechDictDefinition(name="builtin", source=dictTypes.DictionaryType.BUILTIN, mandatory=True),
			dictTypes.SpeechDictDefinition(name="default", source=dictTypes.DictionaryType.DEFAULT, displayName="Default"),
			dictTypes.SpeechDictDefinition(name="temp", source=dictTypes.DictionaryType.TEMP, displayName="Temporary"),
		]
		self.temporary = definitions._speechDictDefinitions[2].dictionary
		add("speechDictHandler.definitions", definitions)
		self.speechDictHandler = module(
			"speechDictHandler",
			definitions=definitions, types=dictTypes, DictionaryType=dictTypes.DictionaryType,
			handleDeprecations=deprecate.handleDeprecations, MovedSymbol=deprecate.MovedSymbol, RemovedSymbol=deprecate.RemovedSymbol,
		)
		self.nvdaVersion = nvdaVersion
		if nvdaVersion != "2026.2":
			# NVDA 2026.1: the dictionaries are the module's own, and reading them writes nothing.
			self.speechDictHandler.dictionaries = {"temp": self.temporary}
			self.speechDictHandler.SpeechDict = dictTypes.SpeechDict
			self.speechDictHandler.SpeechDictEntry = dictTypes.SpeechDictEntry
			self.speechDictHandler.ENTRY_TYPE_REGEXP = dictTypes.EntryType.REGEXP
		add("speechDictHandler", self.speechDictHandler)
		self.folder = folder.name

	def install(self):
		if self.nvdaVersion == "2026.2":
			# In the module's own namespace, with the module where NVDA looks for it (utils._deprecate._getCallerModule).
			v128.nvdaCode(NVDA_SPEECH_DICT_HANDLER, "__getattr__", vars(self.speechDictHandler))
		self._loadColumnsReview()
		self._loadEmoticons()
		return self

	def _loadColumnsReview(self):
		ScriptableObject = self.baseObject.ScriptableObject
		package = module("globalPlugins")
		configManager = module("globalPlugins.columnsReview.configManager", config=self.config, is_boolean=lambda value: value if isinstance(value, bool) else str(value).lower() in ("1", "true", "on", "yes"))
		v128.nvdaCode(COLUMNS_REVIEW_CONFIG, "ConfigFromObject", vars(configManager))
		commonFunc = module("globalPlugins.columnsReview.commonFunc")
		v128.nvdaCode(COLUMNS_REVIEW_SCRIPT_GESTURES, "getScriptGestures", vars(commonFunc))
		cr = self.columnsReview = module(
			"globalPlugins.columnsReview",
			config=self.config, configManager=configManager, commonFunc=commonFunc, getScriptGestures=commonFunc.getScriptGestures,
			commands=self.globalCommands.commands, globalVars=self.modules["globalVars"], globalPluginHandler=self.globalPluginHandler,
			weakref=weakref, utils=module("utils", _RowsReader=type("_RowsReader", (object,), {"isSupported": classmethod(lambda cls: True)})),
		)
		v128.nvdaCode(COLUMNS_REVIEW_RANGE, "rangeFunc", vars(cr))
		v128.nvdaCode(COLUMNS_REVIEW_NOTIFIERS, "PROFILE_SWITCHED_NOTIFIERS", vars(cr))
		v128.nvdaClass("class CRList(object)", [IMITATION_CR_LIST, COLUMNS_REVIEW_LIST], vars(cr))
		v128.nvdaClass("class GlobalPlugin(globalPluginHandler.GlobalPlugin)", [IMITATION_CR_PLUGIN, COLUMNS_REVIEW_PLUGIN], vars(cr))
		package.columnsReview = cr
		sys.modules["globalPlugins"] = package
		sys.modules["globalPlugins.columnsReview"] = cr
		sys.modules["globalPlugins.columnsReview.configManager"] = configManager
		sys.modules["globalPlugins.columnsReview.commonFunc"] = commonFunc
		self.columnsReviewPlugin = cr.GlobalPlugin()
		self.globalPluginHandler.runningPlugins.add(self.columnsReviewPlugin)

		# Outlook's message list (Columns Review's UIASuperGrid) and File Explorer's (its CRList64), each an NVDAObject
		# with Columns Review's CRList among its classes, as NVDA makes them (initOverlayClass), and the focus in each
		# in turn: Columns Review binds its keys on each as the focus comes to it.
		script = self.scriptHandler.script

		class AppModule(ScriptableObject):
			@script(description="Reads the message's status", category="Outlook", gesture="kb:NVDA+shift+o")
			def script_appModuleScript(self, gesture):
				pass

		class NVDAObject(ScriptableObject):
			treeInterceptor = None

			def __init__(self, appName):
				super().__init__()
				self.appModule = AppModule()
				self.appModule.appName = appName

			@script(description="Reports the object's description", category="System focus", gesture="kb:NVDA+shift+d")
			def script_objectScript(self, gesture):
				pass

		self.lists = []
		for appName, className in (("explorer", "CRList64"), ("outlook", "UIASuperGrid")):
			listClass = type(className, (cr.CRList, NVDAObject), {})
			obj = listClass(appName)
			obj.initOverlayClass()
			self.api.getFocusObject = lambda obj=obj: obj
			self.api.getFocusAncestors = lambda: []
			obj.bindCRGestures()
			self.lists.append(obj)

	def _loadEmoticons(self):
		em = self.emoticons = module(
			"globalPlugins.emoticons",
			os=os, config=self.config, speechDictHandler=self.speechDictHandler, globalPluginHandler=self.globalPluginHandler,
			emoticons=EMOTICONS_SMILEYS, profileName=None, oldProfileName=None,
			ADDON_DICTS_PATH=os.path.join(self.folder, "emoticons"),
			ADDON_DIC_DEFAULT_FILE=os.path.join(self.folder, "emoticons", "emoticons.dic"),
		)
		v128.nvdaCode(EMOTICONS_DICTIONARIES, "deactivateAnnouncement", vars(em))
		v128.nvdaClass("class GlobalPlugin(globalPluginHandler.GlobalPlugin)", [IMITATION_EMOTICONS_PLUGIN, EMOTICONS_PROFILE_SWITCH], vars(em))
		sys.modules["globalPlugins.emoticons"] = em
		self.emoticonsPlugin = em.GlobalPlugin()
		self.globalPluginHandler.runningPlugins.add(self.emoticonsPlugin)

	# -- what happens, and what it did

	def altTabOutOfEdge(self):
		"""Browse mode goes off (Custom Browse Mode: manualActivateProfile(None)), and NVDA leaves Edge's profile."""
		self.config.conf.manualActivateProfile(None)
		self.config.conf.exitTrigger("app:msedge")

	def altTabIntoEdge(self):
		"""NVDA turns on Edge's profile, and browse mode comes on (Custom Browse Mode: "browseMode")."""
		self.config.conf.enterTrigger("app:msedge")
		self.config.conf.manualActivateProfile("browseMode")

	def warnings(self):
		return sum(1 for record in self.records.records if record.getMessage() == DEPRECATED)

	def keys(self):
		"""The keys Columns Review has bound on each list: {list: {gesture: script}}."""
		return {type(obj).__name__: {gesture: function.__name__ for gesture, function in obj._gestureMap.items()} for obj in self.lists}

	def temporaryDictionary(self):
		return [entry.pattern for entry in self.temporary]


class ProfileSwitchCase(unittest.TestCase):
	def setUp(self):
		profileSwitches.unregister()
		profileSwitches._logged.clear()
		profileSwitches._failed = False
		self.addCleanup(profileSwitches.unregister)

	def nvda(self, assistant=True, **kwargs):
		nvda = Nvda(self, **kwargs).install()
		# NVDA starts in Edge, in browse mode, as the tester's log does.
		nvda.altTabIntoEdge()
		if assistant:
			profileSwitches.register()
		nvda.records.records.clear()
		nvda.asked = 0
		return nvda


class TesterAltTabTests(ProfileSwitchCase):
	def test_withoutTheAssistantEverySwitchAsksForEveryCommandAndWarns177Times(self):
		# What the tester's log shows: each of the four switches of an Alt+Tab out of Edge and back has Columns Review ask
		# NVDA for every command once for each of its two lists, and Emoticons write 177 warnings with their stacks.
		nvda = self.nvda(assistant=False)
		nvda.altTabOutOfEdge()
		nvda.altTabIntoEdge()
		self.assertEqual(nvda.asked, 8)
		self.assertEqual(nvda.warnings(), 4 * 177)
		self.assertTrue(all(record.stack_info for record in nvda.records.records if record.getMessage() == DEPRECATED))

	def test_theAssistantAsksNvdaOnceAndEmoticonsWarnsOnceAChange(self):
		nvda = self.nvda()
		self.assertTrue(profileSwitches.isInstalled())
		for _round in range(3):
			nvda.altTabOutOfEdge()
			nvda.altTabIntoEdge()
		# Columns Review asked NVDA once, for its first list at the first switch; then NVDA's keys were the same.
		self.assertEqual(nvda.asked, 1)
		# Emoticons: one warning as it takes its emoticons out, one as it puts them back, at each of the 12 switches.
		self.assertEqual(nvda.warnings(), 12 * 2)
		self.assertNotIn("dictionaries", vars(nvda.speechDictHandler))

	def test_whatColumnsReviewBindsIsTheSame(self):
		without = self.nvda(assistant=False)
		expected = []
		for _round in range(2):
			without.altTabOutOfEdge()
			expected.append((without.keys(), without.temporaryDictionary()))
			without.altTabIntoEdge()
			expected.append((without.keys(), without.temporaryDictionary()))
		self.doCleanups()
		self.setUp()
		nvda = self.nvda()
		got = []
		for _round in range(2):
			nvda.altTabOutOfEdge()
			got.append((nvda.keys(), nvda.temporaryDictionary()))
			nvda.altTabIntoEdge()
			got.append((nvda.keys(), nvda.temporaryDictionary()))
		self.assertEqual(got, expected)
		# NVDA's own keys for Say all, Report formatting and Report selection, on Columns Review's own commands, and
		# Emoticons' 88 emoticons in NVDA's temporary dictionary (its announcement is on).
		outlook = got[-1][0]["UIASuperGrid"]
		self.assertEqual(outlook["kb(laptop):a+nvda"], "script_readListItems")
		self.assertEqual(outlook["kb(desktop):downarrow+nvda"], "script_readListItems")
		self.assertEqual(outlook["kb:f+nvda"], "script_reportOrShowFormattingAtCaret")
		self.assertEqual(outlook["kb(laptop):nvda+s+shift"], "script_reportCurrentSelection")
		self.assertEqual(outlook["kb:control+enter+nvda"], "script_manageHeaders")
		self.assertEqual(len(got[-1][1]), 88)


class KeysChangeTests(ProfileSwitchCase):
	def compare(self, change):
		"""The keys Columns Review binds after ``change`` and a switch, without the assistant and with it."""
		results = []
		for assistant in (False, True):
			self.doCleanups()
			self.setUp()
			nvda = self.nvda(assistant=assistant)
			nvda.altTabOutOfEdge()
			nvda.asked = 0
			change(nvda)
			nvda.altTabIntoEdge()
			results.append((nvda.keys(), nvda.asked))
		(expected, askedWithout), (got, askedWith) = results
		self.assertEqual(got, expected)
		self.assertEqual(askedWithout, 4)
		# NVDA's keys changed, so Columns Review asked NVDA again, once, and then kept that answer.
		self.assertEqual(askedWith, 1)
		return got

	def test_aKeyTheUserGaveSayAll(self):
		got = self.compare(lambda nvda: nvda.inputCore.manager.userGestureMap.add("kb:NVDA+shift+r", "globalCommands", "GlobalCommands", "sayAll"))
		self.assertEqual(got["UIASuperGrid"]["kb:nvda+r+shift"], "script_readListItems")

	def test_aKeyTheUserTookFromReportFormatting(self):
		got = self.compare(lambda nvda: nvda.inputCore.manager.userGestureMap.add("kb:NVDA+f", "globalCommands", "GlobalCommands", None))
		self.assertNotIn("kb:f+nvda", got["UIASuperGrid"])

	def test_aBrailleDisplayWithItsOwnKeys(self):
		def display(nvda):
			gestureMap = nvda.inputCore.GlobalGestureMap({"globalCommands.GlobalCommands": {"sayAll": "br(freedomScientific):leftWizWheelPress"}})
			nvda.braille.handler.display = types.SimpleNamespace(name="freedomScientific", gestureMap=gestureMap)

		got = self.compare(display)
		self.assertEqual(got["UIASuperGrid"]["br(freedomscientific):leftwizwheelpress"], "script_readListItems")

	def test_aKeyAnotherAddOnGaveNvdasCommand(self):
		got = self.compare(lambda nvda: nvda.globalCommands.commands.bindGesture("kb:NVDA+shift+control+s", "reportCurrentSelection"))
		self.assertEqual(got["UIASuperGrid"]["kb:control+nvda+s+shift"], "script_reportCurrentSelection")


class EmoticonsTests(ProfileSwitchCase):
	def test_nvda2026_1WritesNoWarningAndNothingChanges(self):
		nvda = self.nvda(nvdaVersion="2026.1")
		dictionaries = nvda.speechDictHandler.dictionaries
		nvda.altTabOutOfEdge()
		nvda.altTabIntoEdge()
		self.assertEqual(nvda.warnings(), 0)
		self.assertIs(nvda.speechDictHandler.dictionaries, dictionaries)
		self.assertEqual(len(nvda.temporaryDictionary()), 88)

	def test_emoticonsTurnedOffStayOut(self):
		nvda = self.nvda()
		nvda.config.conf.base["emoticons"]["announcement"] = 0
		nvda.altTabOutOfEdge()
		self.assertEqual(nvda.temporaryDictionary(), [])
		nvda.altTabIntoEdge()
		self.assertEqual(nvda.temporaryDictionary(), [])
		# Only the reads Emoticons makes to take its emoticons out: one warning at each switch.
		self.assertEqual(nvda.warnings(), 4)

	def test_aFailureInEmoticonsGivesNvdaItsNameBack(self):
		nvda = self.nvda()
		with mock.patch.object(nvda.temporary, "remove", side_effect=RuntimeError("broken for the test")):
			with self.assertRaises(RuntimeError):
				nvda.emoticons.deactivateAnnouncement()
		self.assertNotIn("dictionaries", vars(nvda.speechDictHandler))


class OnOffTests(ProfileSwitchCase):
	def test_turnedOffTheAddOnsHaveTheirOwnBack(self):
		nvda = self.nvda(assistant=False)
		own = (nvda.columnsReview.getScriptGestures, nvda.emoticons.deactivateAnnouncement, nvda.emoticons.activateAnnouncement)
		profileSwitches.register()
		self.assertIsNot(nvda.columnsReview.getScriptGestures, own[0])
		self.assertIs(nvda.columnsReview.getScriptGestures.__wrapped__, own[0])
		profileSwitches.register()
		self.assertIs(nvda.columnsReview.getScriptGestures.__wrapped__, own[0], "wrapped once")
		profileSwitches.unregister()
		self.assertEqual((nvda.columnsReview.getScriptGestures, nvda.emoticons.deactivateAnnouncement, nvda.emoticons.activateAnnouncement), own)
		nvda.altTabOutOfEdge()
		self.assertEqual(nvda.asked, 4)

	def test_anotherAddOnsWrapperIsKept(self):
		nvda = self.nvda()
		ours = nvda.columnsReview.getScriptGestures

		@functools.wraps(ours)
		def theirs(*args):
			return ours(*args)

		nvda.columnsReview.getScriptGestures = theirs
		profileSwitches.register()
		self.assertIs(nvda.columnsReview.getScriptGestures, theirs)
		profileSwitches.unregister()
		self.assertIs(nvda.columnsReview.getScriptGestures, theirs)

	def test_withoutTheAddOnsNothingHappens(self):
		profileSwitches.register()
		self.assertTrue(profileSwitches.isRegistered())
		self.assertFalse(profileSwitches.isInstalled())

	def test_onByDefault(self):
		self.assertTrue(profileSwitches.wanted(dict(state.DEFAULTS)))
		self.assertFalse(profileSwitches.wanted({profileSwitches.STATE_KEY: False}))


class OwnCodeTests(unittest.TestCase):
	def blocks(self, name):
		return globals()[name].strip("\n").split("\n\n\n")

	def test_theConstantsAreNvdas(self):
		# Each piece is in NVDA 2026.2's source, at the margin or as a method, when a copy of it is around: set
		# NVDA_SOURCE to its source folder.
		source = os.environ.get("NVDA_SOURCE")
		if not source:
			self.skipTest("NVDA_SOURCE isn't set to a folder with NVDA 2026.2's source")
		for name, path in NVDA_CODE_FILES.items():
			with open(os.path.join(source, *path.split("/")), encoding="utf-8") as f:
				text = f.read().replace("\r\n", "\n")
			for block in self.blocks(name):
				self.assertTrue(block in text or textwrap.indent(block, "\t") in text, f"{name}: {block.splitlines()[0]}")

	def test_theConstantsAreTheAddOns(self):
		# Set ADDONS_SOURCE to a folder with columnsReview-5.7.0.nvda-addon and emoticons-38.0.0.nvda-addon unpacked
		# into columnsReview and emoticons.
		source = os.environ.get("ADDONS_SOURCE")
		if not source:
			self.skipTest("ADDONS_SOURCE isn't set to a folder with Columns Review 5.7.0 and Emoticons 38.0.0")
		for name, path in ADDON_CODE_FILES.items():
			with open(os.path.join(source, *path.split("/")), encoding="utf-8") as f:
				text = f.read().replace("\r\n", "\n")
			for block in self.blocks(name):
				self.assertTrue(block in text or textwrap.indent(block, "\t") in text, f"{name}: {block.splitlines()[0]}")
		with open(os.path.join(source, "emoticons", "globalPlugins", "emoticons", "smileysList.py"), encoding="utf-8") as f:
			smileys = f.read().replace("\r\n", "\n")
		self.assertEqual(len(EMOTICONS_SMILEYS), 88)
		self.assertEqual(sum(smiley.isEmoji for smiley in EMOTICONS_SMILEYS), 0)
		for line in EMOTICONS_SMILEYS_SOURCE.split("\n"):
			self.assertIn(line, smileys)


if __name__ == "__main__":
	unittest.main()
