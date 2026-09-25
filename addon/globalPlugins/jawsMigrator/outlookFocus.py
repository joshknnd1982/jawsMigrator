# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Opening Outlook puts the focus in Outlook, not in NVDA's own window.

NVDA's Outlook support reads a message's status (unread, replied, has attachment) from Outlook's
object model, which it finds in Windows' list of running programs. Outlook joins that list only once
it has lost the focus after starting. So the first time NVDA asks and Outlook isn't on the list yet,
NVDA makes Outlook lose the focus: it brings its own window to the front, shows "Waiting for
Outlook..." for a second, and lets the focus go back to Outlook (``_registerCOMWithFocusJuggle`` in
NVDA 2026.2's appModules/outlook.py). It does this once per run of Outlook, on whatever thread asked.
Its dialog and its window belong to NVDA's main thread, and the wait only works there.

A tester pressed the Mail key in Edge. Outlook came up, but the first question about its object model
came from another thread than NVDA's main thread: in the tester's log, the helper NVDA runs for it
(nvda_slave) fails with MK_E_UNAVAILABLE while NVDA's main thread goes on logging the switch from Edge.
NVDA's wait then ran on that thread. NVDA brought its hidden window to the front and said "NVDA
window", no "Waiting for Outlook..." dialog came up, and the focus never went back to Outlook, until
the tester pressed Alt+Tab. Neither the assistant nor ClassicSpeech (turned off in that log) asks for
Outlook's object model; NVDA does it for whatever reads a message's status on another thread.

So, while the assistant runs:

- NVDA's Outlook support gets Outlook's object model only on NVDA's main thread. Asked on another
  thread before NVDA has it, it answers that there is none yet, as when Outlook doesn't answer, and
  it neither waits for Outlook nor keeps anything. NVDA's main thread asks when the focus comes to a
  message, and waits for Outlook there, as NVDA intends. (An object model got on another thread would
  serve NVDA's main thread badly anyway: a COM object belongs to the apartment of the thread that got
  it.) Once NVDA has it, every thread gets it, as before.
- When NVDA has waited for Outlook and NVDA's own window still has the focus, the window that had it
  before gets it back.

NVDA still says "Waiting for Outlook..." the first time it needs Outlook's object model, as it does
without add-ons; then the focus is back in Outlook.
"""

from __future__ import annotations

import functools
import threading
import types

#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: NVDA's Outlook support: the object model it keeps once it has it, and its wait for Outlook.
OBJECT_MODEL = "nativeOm"
WAIT_FOR_OUTLOOK = "_registerCOMWithFocusJuggle"
#: Noted on an Outlook app module once another thread than NVDA's main thread has asked for the object model.
OTHER_THREAD_NOTE = "_jawsMigratorAskedOnOtherThread"

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(class, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: The assistant's wrapper of appModuleHandler.fetchAppModule, while NVDA calls it.
_fetchWrapper = None


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


def onMainThread() -> bool:
	"""Whether this is NVDA's main thread. When NVDA can't tell, it counts as the main thread, so NVDA is left alone."""
	try:
		import core

		mainThreadId = getattr(core, "mainThreadId", None)
	except Exception:
		mainThreadId = None
	return mainThreadId is None or threading.get_ident() == mainThreadId


def register() -> None:
	"""Guard NVDA's Outlook support: the Outlook running now, and each Outlook NVDA meets from now on."""
	global _enabled, _fetchWrapper
	if _enabled:
		return
	_enabled = True
	try:
		import appModuleHandler

		current = appModuleHandler.fetchAppModule
		if _fetchWrapper is None or not _calls(current, _fetchWrapper):
			_fetchWrapper = _fetchingGuarded(current)
			appModuleHandler.fetchAppModule = _fetchWrapper
		for appModule in list(appModuleHandler.runningTable.values()):
			guard(appModule)
	except Exception:
		_failure("can't keep NVDA's wait for Outlook on NVDA's main thread")


def _calls(function, wrapper) -> bool:
	"""Whether ``function`` is ``wrapper``, or wraps it (as another add-on's functools.wraps wrapper would)."""
	for _ in range(16):
		if function is wrapper:
			return True
		function = getattr(function, "__wrapped__", None)
		if function is None:
			break
	return False


def unregister() -> None:
	"""Give NVDA its own Outlook support back, where nothing has been put over the assistant's since."""
	global _enabled, _fetchWrapper
	if not _enabled:
		return
	_enabled = False
	with _lock:
		for owner, name, installed, original in reversed(_replaced):
			try:
				if vars(owner).get(name) is installed:
					setattr(owner, name, original)
			except Exception:
				pass
		_replaced.clear()
	try:
		import appModuleHandler

		# Put over by another add-on since, the wrapper stays, and does nothing until the assistant guards Outlook again.
		if _fetchWrapper is not None and appModuleHandler.fetchAppModule is _fetchWrapper:
			appModuleHandler.fetchAppModule = getattr(_fetchWrapper, ORIGINAL)
			_fetchWrapper = None
	except Exception:
		pass


def isRegistered() -> bool:
	return _enabled


def _owner(cls, name: str):
	"""The class, among ``cls`` and its bases, whose own attribute ``name`` an instance of ``cls`` uses."""
	for klass in getattr(cls, "__mro__", ()):
		if name in vars(klass):
			return klass
	return None


def guard(appModule) -> bool:
	"""Guard the NVDA Outlook support ``appModule`` runs on. True when ``appModule`` is Outlook's.

	The guards go on the class of NVDA's own Outlook support (``appModules.outlook.AppModule``, or
	``nvdaBuiltin.appModules.outlook.AppModule`` under an add-on such as Outlook Extended), once, so
	every Outlook app module built on it has them. Any other application's app module is left alone.
	"""
	cls = type(appModule)
	waitOwner = _owner(cls, WAIT_FOR_OUTLOOK)
	if waitOwner is None:
		return False
	with _lock:
		_replace(waitOwner, WAIT_FOR_OUTLOOK, _waitGuarded, lambda value: isinstance(value, types.FunctionType))
		modelOwner = _owner(cls, OBJECT_MODEL)
		if modelOwner is not None:
			# NVDA keeps the object model on the app module itself, which only a descriptor without __set__ allows.
			_replace(modelOwner, OBJECT_MODEL, MainThreadObjectModel, lambda value: hasattr(value, "__get__") and not hasattr(value, "__set__"))
	return True


def _replace(owner, name: str, guarded, usable) -> bool:
	"""Put the guarded ``name`` in the place of NVDA's own on ``owner``, once. True when it is there."""
	current = vars(owner).get(name)
	if any(entry[0] is owner and entry[1] == name and entry[2] is current for entry in _replaced):
		return True
	if current is None or not usable(current):
		_failure(f"NVDA's Outlook support has a {name} the assistant doesn't know, so it is left as it is")
		return False
	installed = guarded(current)
	setattr(owner, name, installed)
	_replaced.append((owner, name, installed, current))
	_log().debug(f"jawsMigrator: NVDA's Outlook support ({owner.__module__}) gets Outlook's object model on NVDA's main thread only ({name})")
	return True


def _fetchingGuarded(original):
	"""appModuleHandler.fetchAppModule, guarding each new Outlook app module before NVDA uses it."""

	@functools.wraps(original)
	def fetchAppModule(*args, **kwargs):
		appModule = original(*args, **kwargs)
		if _enabled and appModule is not None:
			try:
				guard(appModule)
			except Exception:
				_failure("could not guard NVDA's Outlook support")
		return appModule

	setattr(fetchAppModule, ORIGINAL, original)
	return fetchAppModule


class MainThreadObjectModel:
	"""NVDA's ``nativeOm``, which gets Outlook's object model on NVDA's main thread only.

	Like NVDA's own, it has no ``__set__``: NVDA's Outlook support keeps the object model it gets on the
	app module, and from then on every thread reads it from there, without coming here.
	"""

	def __init__(self, original):
		self.original = original
		setattr(self, ORIGINAL, original)

	def __get__(self, instance, owner=None):
		if instance is None:
			return self.original.__get__(None, owner)
		if _enabled and not onMainThread():
			_noteOtherThread(instance)
			return None
		return self.original.__get__(instance, owner if owner is not None else type(instance))


def _waitGuarded(original):
	"""NVDA's wait for Outlook, on NVDA's main thread only, and with the focus given back afterwards."""

	@functools.wraps(original)
	def _registerCOMWithFocusJuggle(appModule, *args, **kwargs):
		if not _enabled:
			return original(appModule, *args, **kwargs)
		if not onMainThread():
			_noteOtherThread(appModule)
			return None
		foreground = _foregroundWindow()
		_log().debug("jawsMigrator: NVDA waits for Outlook to offer its object model")
		try:
			return original(appModule, *args, **kwargs)
		finally:
			giveFocusBack(foreground)

	setattr(_registerCOMWithFocusJuggle, ORIGINAL, original)
	return _registerCOMWithFocusJuggle


def _noteOtherThread(appModule) -> None:
	"""Note in NVDA's log, once for each run of Outlook, that another thread asked for its object model first.

	A thread NVDA didn't start has a name like "Dummy-241", which says nothing about what asked, so the note
	carries the stack that asked: add-on or NVDA code, in the order it was called.
	"""
	try:
		if getattr(appModule, OTHER_THREAD_NOTE, False):
			return
		setattr(appModule, OTHER_THREAD_NOTE, True)
		_log().debug(
			f"jawsMigrator: Outlook's object model was asked for on the thread {threading.current_thread().name!r}, "
			"not NVDA's main thread, so NVDA neither gets it nor waits for Outlook there; "
			"NVDA's main thread gets it when it needs it. What asked:",
			stack_info=True,
		)
	except Exception:
		pass


def _foregroundWindow() -> int:
	try:
		import winUser

		return winUser.getForegroundWindow()
	except Exception:
		return 0


def giveFocusBack(foreground) -> bool:
	"""After NVDA waited for Outlook: when NVDA's own window still has the focus, ``foreground`` gets it back.

	``foreground`` is the window that had the focus before NVDA waited. It gets it back only when it is
	still there and isn't NVDA's own, and NVDA's own window (or none) has the focus now: when the focus
	went back by itself, or went on to another program meanwhile, nothing changes. True when it got it back.
	"""
	try:
		import globalVars
		import winUser

		if not foreground or not winUser.isWindow(foreground):
			return False
		nvda = globalVars.appPid
		if winUser.getWindowThreadProcessID(foreground)[0] == nvda:
			return False
		now = winUser.getForegroundWindow()
		if now == foreground or (now and winUser.getWindowThreadProcessID(now)[0] != nvda):
			return False
		winUser.setForegroundWindow(foreground)
		_log().debug(
			"jawsMigrator: NVDA's own window kept the focus after NVDA waited for Outlook, "
			f"so it goes back to the window that had it ({winUser.getClassName(foreground)})"
		)
		return True
	except Exception:
		_failure("could not give the focus back after NVDA waited for Outlook")
		return False
