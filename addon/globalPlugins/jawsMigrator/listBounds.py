# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Columns Review doesn't say "List top", "List bottom" or "Mono-item list", which JAWS never says.

A tester heard "Items View list, List top:" each time File Explorer opened a folder, and "Desktop list, List top:"
on the desktop; JAWS doesn't say "List top". NVDA itself has no such words: they come from the Columns Review
add-on (5.7.0). Its "Announce list bounds (top, mono-item, bottom)", on and said with the voice as it comes,
says "List top: " when the focus comes to the first item of a list, "List bottom: " at the last and "Mono-item
list: " when the list has one item (``reportListBounds`` in ``globalPlugins.columnsReview``, which its
``event_gainFocus`` calls before NVDA says the item). Opening a folder, Home, End, or an arrow key to the first or
last item all do it: in File Explorer, on the desktop, in Open and Save As dialogs, and in other programs' lists.
JAWS has messages for the ends of a list ("Top of list" and "Bottom of list" in common.jsm), but none of its
scripts uses them: at either end JAWS says the item, and nothing more.

So Columns Review's report of a list's end says nothing when Columns Review would say it with the voice. The
assistant asks Columns Review's own settings, as Columns Review does (``configManager.ConfigFromObject``, which
follows the configuration profile of the program). Set to beep in Columns Review's settings, it still beeps, as
the user chose there; with "Announce list bounds" off, nothing changes. Everything else Columns Review does is
unchanged. It works while the assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

import functools
import sys

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "quietColumnsReviewListBounds"
#: Columns Review's global plugin, as NVDA imports it.
MODULE = "globalPlugins.columnsReview"
#: Its plugin class, and the method with which that says the end of a list: reportListBounds(self, obj).
PLUGIN_CLASS = "GlobalPlugin"
REPORT = "reportListBounds"
#: Its settings for an object: configManager.ConfigFromObject(obj).announceListBoundsWith, "voice" or "beep".
CONFIG_MODULE = "configManager"
CONFIG_CLASS = "ConfigFromObject"
SAID_WITH = "announceListBoundsWith"
VOICE = "voice"
#: Marks what the assistant put in the place of Columns Review's own, and keeps its own.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's version, so another add-on's wrapper around it is recognized.
MARK = "_jawsMigratorListBounds"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
#: What the assistant put in the place of Columns Review's own: [(its plugin class, the assistant's, its own)].
_replaced: list = []
#: Whether the log has said once that Columns Review says nothing at the ends of a list.
_logged = False


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
	"""Whether Columns Review says nothing at the ends of a list, as JAWS: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have Columns Review say nothing at the ends of a list where it would say it with the voice, from now on."""
	global _enabled
	if _enabled:
		# Called again after a migration, a restore or a configuration reload: Columns Review may have loaded since.
		_install()
		return
	_enabled = True
	if not _install():
		# NVDA imports the global plugins one after another, and Columns Review may come after the assistant.
		# Everything NVDA does as it starts, the first focus included, waits for the plugins.
		try:
			import wx

			wx.CallAfter(_installIfWanted)
		except Exception:
			pass


def unregister() -> None:
	"""Give Columns Review its own report back, where nothing has been put over the assistant's since."""
	global _enabled
	if not _enabled:
		return
	_enabled = False
	for plugin, installed, original in reversed(_replaced):
		try:
			if vars(plugin).get(REPORT) is installed:
				setattr(plugin, REPORT, original)
		except Exception:
			pass
	_replaced.clear()


def isRegistered() -> bool:
	return _enabled


def isInstalled() -> bool:
	"""Whether the assistant's version of the report is in Columns Review now."""
	plugin = _pluginClass(sys.modules.get(MODULE))
	return plugin is not None and _isOurs(vars(plugin).get(REPORT))


def _installIfWanted() -> None:
	if _enabled:
		_install()


def _pluginClass(module):
	plugin = vars(module).get(PLUGIN_CLASS) if module is not None else None
	return plugin if isinstance(plugin, type) else None


def _configClass(module):
	"""Columns Review's ConfigFromObject, or None."""
	config = vars(module).get(CONFIG_MODULE)
	settings = getattr(config, CONFIG_CLASS, None)
	return settings if isinstance(settings, type) else None


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
	"""Put the assistant's version of the report in Columns Review, once. True when it is there."""
	module = sys.modules.get(MODULE)
	if module is None:
		# Not installed, turned off, or not loaded yet.
		return False
	try:
		plugin = _pluginClass(module)
		current = vars(plugin).get(REPORT) if plugin is not None else None
		if _isOurs(current):
			# Still there from before: turned off and on again, or another add-on has put its own around it since.
			return True
		if not callable(current) or _configClass(module) is None:
			_failure(f"Columns Review has no {REPORT} the assistant knows, so it says the ends of a list as it always has")
			return False
		installed = _guarded(current, module)
		setattr(plugin, REPORT, installed)
		_replaced.append((plugin, installed, current))
		_log().debug(f"jawsMigrator: Columns Review says nothing at the ends of a list with the voice ({MODULE}.{PLUGIN_CLASS}.{REPORT})")
		return True
	except Exception:
		_failure("can't keep Columns Review from saying the ends of a list")
		return False


def _saidWithVoice(obj, module) -> bool:
	"""Whether Columns Review says the end of a list with the voice for ``obj``, as its own reportListBounds asks."""
	return getattr(_configClass(module)(obj), SAID_WITH) == VOICE


def _note() -> None:
	global _logged
	if _logged:
		return
	_logged = True
	_log().debug(
		'jawsMigrator: Columns Review doesn\'t say "List top", "List bottom" or "Mono-item list"; JAWS says the item alone',
	)


def _guarded(original, module):
	"""Columns Review's report of a list's end: nothing, where it would be said with the voice."""

	@functools.wraps(original)
	def reportListBounds(self, obj, *args, **kwargs):
		if _enabled:
			try:
				quiet = _saidWithVoice(obj, module)
			except Exception:
				_failure("could not tell whether Columns Review says the end of a list with the voice, so it says it")
				quiet = False
			if quiet:
				_note()
				return None
		return original(self, obj, *args, **kwargs)

	setattr(reportListBounds, MARK, _TOKEN)
	setattr(reportListBounds, ORIGINAL, original)
	return reportListBounds
