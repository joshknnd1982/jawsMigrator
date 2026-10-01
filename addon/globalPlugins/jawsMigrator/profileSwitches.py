# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""Columns Review and Emoticons don't hold NVDA up each time it switches configuration profiles, as switching
programs does.

A tester found Alt+Tab slow in and out of Edge (issue 31), and Insert+F7 sometimes opened Edge's "Turn on caret
browsing?" instead of the Links List. NVDA's log showed its main thread stuck for about two seconds, twice, each time
the focus went into or out of Edge. Each time NVDA was switching configuration profiles. The migration's "JAWS -
msedge" profile turns on in Edge, and the Custom Browse Mode add-on turns on its "browseMode" profile whenever
browse mode does. So going into or out of Edge is two switches, and two add-ons made each one take a second:

- Columns Review 5.7.0 binds its keys again on every switch, for every list it has seen
  (``GlobalPlugin.handleConfigProfileSwitch``, ``CRList.bindCRGestures``), and does the same whenever the focus comes
  to a list. To learn which keys NVDA's own commands "Report formatting", "Report selection" and "Say all" have, its
  ``getScriptGestures`` asks NVDA for every command of every add-on, program, object and document
  (``inputCore.manager.getAllGestureMappings``, the list behind Input Gestures): 0.75 to 0.87 seconds each time.
- Emoticons 38 takes its emoticons out of NVDA's temporary speech dictionary and puts them back
  (``deactivateAnnouncement``, ``activateAnnouncement``), reading ``speechDictHandler.dictionaries`` twice for each of
  them. NVDA 2026.2 has removed that name, still answers it, and writes a warning with the whole stack to its log
  each time it is read: 177 warnings, about 0.2 seconds, per switch.

After half a second with the foreground changed, NVDA's watchdog lets every key through to the program
(``watchdog.isAttemptingRecovery``, ``keyboardHandler.internal_keyDownEvent``), so Insert+F7 reached Edge as F7. JAWS
switches its settings for a program at once, and its keys never reach the program.

So Columns Review keeps the keys of NVDA's own commands it asked for, and asks NVDA again only once NVDA's keys have
changed: the user's (gestures.ini), those of NVDA's language, the braille display's, or those of NVDA's global
commands. Wherever the focus is, NVDA's global commands have the same keys. And Emoticons reads NVDA's temporary
dictionary once for each change, as it read it before, so NVDA writes the warning once, not 177 times. What Columns
Review binds and what Emoticons says are unchanged. It works while the assistant runs, unless it is turned off in
NVDA's Settings, JAWS Migration Assistant.

Emoticons 38.2.0, which needs NVDA 2026.3, keeps NVDA's temporary dictionary itself and no longer reads that name, so
NVDA writes no warning for it. Reading the name for it would add a warning at each change, so the assistant leaves
such a version of Emoticons alone, and wraps only functions that still read ``speechDictHandler.dictionaries``.
"""

from __future__ import annotations

import functools
import sys

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "quickProfileSwitches"
#: Columns Review's global plugin, as NVDA imports it, and the name through which it asks for NVDA's keys:
#: getScriptGestures(*scriptFunctions) -> {scriptFunction: [gesture, ...]}.
COLUMNS_REVIEW = "globalPlugins.columnsReview"
SCRIPT_GESTURES = "getScriptGestures"
#: The Emoticons global plugin, and the two functions with which it changes NVDA's temporary speech dictionary.
EMOTICONS = "globalPlugins.emoticons"
EMOTICONS_FUNCTIONS = ("deactivateAnnouncement", "activateAnnouncement")
#: NVDA's speech dictionaries, the name NVDA 2026.2 and 2026.3 warn about each time it is read
#: (speechDictHandler.__getattr__).
DICTIONARIES = "dictionaries"
#: Marks what the assistant put in the place of an add-on's own, and keeps its own.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's versions, so another add-on's wrapper around one is recognized.
MARK = "_jawsMigratorProfileSwitches"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
#: What the assistant put in the place of an add-on's own: [(its module, name, the assistant's, its own)].
_replaced: list = []
#: Columns Review's answers: {the script functions it asked about: (NVDA's keys then, {function: (gesture, ...)})}.
_keys: dict = {}
#: What the log has said once: "columnsReview", "emoticons".
_logged: set = set()


def _log():
	from logHandler import log

	return log


def _failure(what: str) -> None:
	global _failed
	if _failed:
		return
	_failed = True
	try:
		_log().debugWarning(f"jawsMigrator: {what}", exc_info=True)
	except Exception:
		pass


def wanted(stateData: dict) -> bool:
	"""Whether Columns Review and Emoticons are kept from holding NVDA up at a profile switch: on unless turned off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Keep Columns Review and Emoticons from holding NVDA up when it switches profiles, from now on."""
	global _enabled
	if _enabled:
		# Called again after a migration, a restore or a configuration reload: an add-on may have loaded since.
		_install()
		return
	_enabled = True
	_keys.clear()
	_install()
	if not (_columnsReviewInstalled() and _emoticonsInstalled()):
		# NVDA imports the global plugins one after another, and these may come after the assistant. Everything NVDA
		# does as it starts, the first focus included, waits for the plugins.
		try:
			import wx

			wx.CallAfter(_installIfWanted)
		except Exception:
			pass


def unregister() -> None:
	"""Give Columns Review and Emoticons their own functions back, where nothing has been put over the assistant's since."""
	global _enabled
	if not _enabled:
		return
	_enabled = False
	for module, name, installed, original in reversed(_replaced):
		try:
			if vars(module).get(name) is installed:
				setattr(module, name, original)
		except Exception:
			pass
	_replaced.clear()
	_keys.clear()


def isRegistered() -> bool:
	return _enabled


def isInstalled() -> bool:
	"""Whether the assistant's version is in Columns Review or Emoticons now."""
	return _columnsReviewInstalled() or _emoticonsInstalled()


def _columnsReviewInstalled() -> bool:
	module = sys.modules.get(COLUMNS_REVIEW)
	return module is not None and _isOurs(vars(module).get(SCRIPT_GESTURES))


def _emoticonsInstalled() -> bool:
	module = sys.modules.get(EMOTICONS)
	return module is not None and all(_isOurs(vars(module).get(name)) for name in EMOTICONS_FUNCTIONS)


def _installIfWanted() -> None:
	if _enabled:
		_install()


def _isOurs(function) -> bool:
	"""Whether ``function`` is the assistant's version, or wraps it (as another add-on's functools.wraps wrapper would)."""
	for _ in range(_MOST_WRAPPERS):
		if function is None:
			return False
		if getattr(function, MARK, None) is _TOKEN:
			return True
		function = getattr(function, "__wrapped__", None)
	return False


def _install() -> bool:
	"""Put the assistant's versions in Columns Review and Emoticons, once each. True when either is there."""
	columnsReview = _installIn(COLUMNS_REVIEW, (SCRIPT_GESTURES,), _rememberedKeys, "Columns Review asks NVDA for the keys of NVDA's own commands only when they change")
	emoticons = _installIn(
		EMOTICONS,
		EMOTICONS_FUNCTIONS,
		_oneWarning,
		"Emoticons reads NVDA's temporary speech dictionary once for each change",
		needed=_readsDictionaries,
		notNeeded="Emoticons doesn't read speechDictHandler.dictionaries (as from its version 38.2.0), so NVDA writes no warning "
		"at a profile switch, and the assistant leaves it as it is",
	)
	return columnsReview or emoticons


def _installIn(moduleName: str, names: tuple, make, what: str, needed=None, notNeeded: str = "") -> bool:
	"""Put the assistant's version in the place of each of the add-on's functions ``names``, where ``needed`` (if given)
	says the function holds NVDA up. True when the assistant's versions are there."""
	module = sys.modules.get(moduleName)
	if module is None:
		# Not installed, turned off, or not loaded yet.
		return False
	try:
		current = {name: vars(module).get(name) for name in names}
		if all(_isOurs(function) for function in current.values()):
			# Still there from before: turned off and on again, or another add-on has put its own around it since.
			return True
		if not all(callable(function) for function in current.values()):
			_failure(f"{moduleName} has no {', '.join(names)} the assistant knows, so it switches profiles as it always has")
			return False
		wrapping = {
			name: function
			for name, function in current.items()
			if not _isOurs(function) and (needed is None or needed(function))
		}
		if not wrapping:
			if not any(_isOurs(function) for function in current.values()):
				# This version of the add-on doesn't hold NVDA up.
				_note(moduleName, notNeeded)
				return False
			return True
		for name, function in wrapping.items():
			installed = make(function)
			setattr(module, name, installed)
			_replaced.append((module, name, installed, function))
		_log().debug(f"jawsMigrator: {what} ({moduleName}.{', '.join(wrapping)})")
		return True
	except Exception:
		_failure(f"can't keep {moduleName} from holding NVDA up at a profile switch")
		return False


def _note(which: str, message: str) -> None:
	if which in _logged:
		return
	_logged.add(which)
	_log().debug(f"jawsMigrator: {message}")


def _gestureMapEntries(gestureMap):
	"""What a gesture map holds, to compare: None for no map."""
	if gestureMap is None:
		return None
	entries = vars(gestureMap).get("_map")
	if not isinstance(entries, dict):
		# Not NVDA's GlobalGestureMap as the assistant knows it: never the same, so Columns Review asks NVDA each time.
		return object()
	return frozenset((gesture, tuple(tuple(script) for script in scripts)) for gesture, scripts in entries.items())


def _nvdasKeysNow() -> tuple:
	"""Everything the keys of NVDA's global commands come from, in NVDA's list of all of them
	(inputCore._AllGestureMappingsRetriever): the user's gesture map, the one for NVDA's language, the braille
	display's, and NVDA's global commands' own. Its other parts (add-ons, the program, the focus and what it is in)
	give keys to their own classes, never to NVDA's global commands."""
	import braille
	import globalCommands
	import inputCore

	manager = inputCore.manager
	display = braille.handler.display if braille.handler else None
	commands = globalCommands.commands
	return (
		_gestureMapEntries(manager.userGestureMap),
		_gestureMapEntries(manager.localeGestureMap),
		_gestureMapEntries(getattr(display, "gestureMap", None) if display else None),
		id(commands),
		frozenset(commands._gestureMap.items()),
	)


def _rememberedKeys(original):
	"""Columns Review's getScriptGestures: its answer from before, while NVDA's keys are the same."""

	@functools.wraps(original)
	def getScriptGestures(*scriptFunctions):
		if not _enabled:
			return original(*scriptFunctions)
		try:
			now = _nvdasKeysNow()
			remembered = _keys.get(scriptFunctions)
		except Exception:
			_failure("could not tell whether NVDA's keys have changed, so Columns Review asks NVDA for them")
			return original(*scriptFunctions)
		if remembered is not None and remembered[0] == now:
			_note(
				"columnsReview",
				"Columns Review binds its keys without asking NVDA for every command again (inputCore.getAllGestureMappings), "
				"which took about a second at each profile switch; NVDA's own commands still have the same keys",
			)
			return {function: list(gestures) for function, gestures in remembered[1].items()}
		answer = original(*scriptFunctions)
		try:
			_keys[scriptFunctions] = (now, {function: tuple(gestures) for function, gestures in answer.items()})
		except Exception:
			_failure("could not keep Columns Review's keys, so it asks NVDA for them each time")
		return answer

	setattr(getScriptGestures, MARK, _TOKEN)
	setattr(getScriptGestures, ORIGINAL, original)
	return getScriptGestures


def _readsDictionaries(function) -> bool:
	"""Whether one of Emoticons' functions reads ``speechDictHandler.dictionaries``, as Emoticons 38.0.0's do; from
	38.2.0 they use a dictionary Emoticons keeps itself. When that can't be told, as if it does, as 1.34 had it."""
	try:
		import inspect

		code = getattr(inspect.unwrap(function), "__code__", None)
		if code is None:
			return True
		codes = [code]
		while codes:
			code = codes.pop()
			if DICTIONARIES in code.co_names:
				return True
			# Any function or comprehension inside it.
			codes.extend(constant for constant in code.co_consts if hasattr(constant, "co_names"))
		return False
	except Exception:
		return True


def _oneWarning(original):
	"""One of Emoticons' changes to NVDA's temporary speech dictionary, with NVDA's dictionaries read once."""

	@functools.wraps(original)
	def changeTemporaryDictionary(*args, **kwargs):
		if not _enabled:
			return original(*args, **kwargs)
		try:
			import speechDictHandler

			if DICTIONARIES in vars(speechDictHandler):
				# NVDA before 2026.2 has the name itself and writes no warning, or someone else has put it there.
				return original(*args, **kwargs)
			# NVDA's own answer, with its warning: once.
			dictionaries = getattr(speechDictHandler, DICTIONARIES)
		except Exception:
			return original(*args, **kwargs)
		_note(
			"emoticons",
			"Emoticons reads NVDA's speech dictionaries once for each change of its emoticons, not twice for each "
			"emoticon, so NVDA writes its warning once, not 177 times at each profile switch",
		)
		# NVDA's answer holds its own dictionaries, which Emoticons changes; for this change, reading the name again
		# gives the same ones without another warning.
		setattr(speechDictHandler, DICTIONARIES, dictionaries)
		try:
			return original(*args, **kwargs)
		finally:
			try:
				if vars(speechDictHandler).get(DICTIONARIES) is dictionaries:
					delattr(speechDictHandler, DICTIONARIES)
			except Exception:
				_failure("could not give NVDA back its own speechDictHandler.dictionaries")

	setattr(changeTemporaryDictionary, MARK, _TOKEN)
	setattr(changeTemporaryDictionary, ORIGINAL, original)
	return changeTemporaryDictionary
