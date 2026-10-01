# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""In Outlook, NVDA reads the status bar as JAWS reads it: the items and the zoom, without the view and zoom buttons.

A tester in Outlook's Inbox pressed Insert+Page Down, JAWS's "Say Bottom Line of Window", which the migration gives
NVDA's "Report status bar" (issue 26). JAWS said "Items in View 2,675", "Unread Items in View 1,135" and "Zoom 10%".
NVDA said "Status Bar Items in View 2,675 Unread Items in View 1,135 Normal View. Show All Pinned Panes. Reading View.
Hide All Pinned Panes. Zoom Out 10 Zoom 10 Zoom In 10 Zoom 10%".

NVDA reads a status bar as its name, then the name and value of each thing in it (``api.getStatusBarText``), unless
the program's app module reads it its own way (``AppModule.getStatusBarText``). NVDA's support for Outlook has no way
of its own, so NVDA says "Status Bar", the view buttons with their tooltips, and the zoom slider and its buttons
with the zoom. JAWS reads it with its own script for Outlook (Outlook.jss, ``SayBottomLineOfWindow`` and
``GetStatusBarWindowInfo``): the name of each item in the status bar that Office's UI Automation calls a
"NetUISimpleButton", one on each line. Those are the item counts, the zoom and messages such as a filter or the
connection; the view buttons and the zoom slider are other kinds of controls.

So in Outlook, NVDA reads the status bar as JAWS does: the names of those items, with a pause between them (", ", as
NVDA's own File Explorer support reads its status bar), and nothing else. Pressed twice, NVDA spells that, and three
times copies it, as before. When Outlook's status bar has none of them (or NVDA reads it without UI Automation, or
another add-on's app module reads Outlook's status bar), NVDA reads it as it does, as JAWS reads the bottom line of the
window then. Other programs are unchanged. It works while the assistant runs, unless it is turned off in NVDA's
Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

import functools
import threading

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "outlookStatusBarLikeJaws"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own version, so another add-on's wrapper around it is recognized.
MARK = "_jawsMigratorOutlookStatusBar"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: The name NVDA gives classic Outlook's app module.
APP_NAME = "outlook"
#: NVDA's function that gives a status bar's text, in its api module.
FUNCTION = "getStatusBarText"
#: What Office's UI Automation calls the status bar's items JAWS reads in Outlook (Outlook.jsh, objn_NetUISimpleButton).
ITEM_CLASS = "NetUISimpleButton"
#: Between two items: JAWS says each on a line of its own; NVDA's File Explorer support puts ", " between them.
SEPARATOR = ", "
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []


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
	"""Whether NVDA reads Outlook's status bar as JAWS does: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have NVDA read Outlook's status bar as JAWS does, from now on."""
	global _enabled
	if _enabled:
		return
	try:
		import api

		with _lock:
			if not _replace(api):
				return
	except Exception:
		_failure("can't read Outlook's status bar as JAWS does, so NVDA reads it as it does")
		return
	_enabled = True


def unregister() -> None:
	"""Give NVDA its own function back, where nothing has been put over the assistant's since."""
	global _enabled
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


def isRegistered() -> bool:
	return _enabled


def _isOurs(function) -> bool:
	"""Whether ``function`` is the assistant's version, or wraps it (as another add-on's functools.wraps wrapper would)."""
	for _ in range(_MOST_WRAPPERS):
		if function is None:
			return False
		if getattr(function, MARK, None) is _TOKEN:
			return True
		function = getattr(function, "__wrapped__", None)
	return False


def _replace(owner) -> bool:
	"""Put the assistant's version of NVDA's function in its place on ``owner``, once. True when it is there."""
	current = vars(owner).get(FUNCTION)
	if _isOurs(current):
		# Still there from before: turned off and on again, or another add-on has put its own around it since.
		return True
	if not callable(current):
		_failure(f"NVDA has no api.{FUNCTION} the assistant knows, so NVDA reads Outlook's status bar as it does")
		return False
	installed = _guarded(current)
	setattr(owner, FUNCTION, installed)
	_replaced.append((owner, FUNCTION, installed, current))
	_log().debug(f"jawsMigrator: NVDA reads Outlook's status bar as JAWS does (api.{FUNCTION})")
	return True


def _mark(installed, original):
	setattr(installed, MARK, _TOKEN)
	setattr(installed, ORIGINAL, original)
	return installed


def _appReadsItsOwn(appModule) -> bool:
	"""Whether ``appModule`` reads its status bar its own way (another add-on's app module for Outlook could)."""
	try:
		import appModuleHandler

		nvdas = appModuleHandler.AppModule.getStatusBarText
	except Exception:
		return True
	own = getattr(type(appModule), "getStatusBarText", nvdas)
	return own is not nvdas


def _className(obj) -> str:
	"""The class Office's UI Automation gives ``obj``, or "" for an object NVDA doesn't read through UI Automation."""
	element = getattr(obj, "UIAElement", None)
	if element is None:
		return ""
	try:
		return element.cachedClassName or ""
	except Exception:
		return ""


def jawsText(obj) -> str | None:
	"""What JAWS reads of ``obj``, NVDA's status bar, in Outlook: the names of its NetUISimpleButton items, as
	Outlook.jss's GetStatusBarWindowInfo takes them. None where NVDA reads it as it does: not Outlook, not read
	through UI Automation, Outlook read by an app module of another add-on, or no such item with a name."""
	appModule = getattr(obj, "appModule", None)
	if getattr(appModule, "appName", None) != APP_NAME or getattr(obj, "UIAElement", None) is None:
		return None
	if _appReadsItsOwn(appModule):
		return None
	names = []
	for child in obj.children or ():
		if _className(child) != ITEM_CLASS:
			continue
		name = child.name
		if name and isinstance(name, str) and not name.isspace():
			names.append(name.strip())
	return SEPARATOR.join(names) or None


def _guarded(original):
	"""NVDA's api.getStatusBarText: in Outlook, the status bar's items as JAWS reads them."""

	@functools.wraps(original)
	def getStatusBarText(obj, *args, **kwargs):
		if _enabled:
			try:
				text = jawsText(obj)
			except Exception:
				text = None
				_failure("could not read Outlook's status bar as JAWS does, so NVDA reads it as it does")
			if text is not None:
				# A key press now and then: the log says each time, next to NVDA's "Speaking" line.
				_log().debug(f"jawsMigrator: Outlook's status bar is read as JAWS reads it: {text!r}")
				return text
		return original(obj, *args, **kwargs)

	return _mark(getStatusBarText, original)
