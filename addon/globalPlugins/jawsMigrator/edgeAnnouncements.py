# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""The MS Edge Discard Announcements add-on's category stays in NVDA's Settings while Edge runs.

The assistant's answer to issue 32 sent a tester to NVDA's Settings, "Microsoft Edge discard announcements" category,
to have NVDA say Edge's "Going back". Opened from Edge, NVDA's Settings had no such category: M went from Magnifier to
Mouse and Math, and Down Arrow went past it too.

That add-on (MSEdgeDiscardAnnouncements 0.11.0) is an app module for Edge. When NVDA makes its app module for an Edge
process, it adds its category to NVDA's Settings (``AppModule.__init__``, appending ``MSEdgeDiscardAnnouncementsPanel``
to ``gui.settingsDialogs.NVDASettingsDialog.categoryClasses``), and when that process ends, it takes the category out
again (``AppModule.terminate``). But Edge runs many processes, and NVDA makes an app module for each one it meets: a
file dialog, as for a file you attach on GitHub, comes from a process of its own. The tester attached their log that
way, and as the dialog closed its process ended: NVDA's log says "application msedge closed" (``appModuleHandler
.cleanup``). That app module's terminate took the category out, though Edge's own app module was still running, so
the category was gone from NVDA's Settings until Edge or NVDA was started again.

So after NVDA lets go of the app modules of processes that ended (``appModuleHandler.cleanup``, which NVDA runs as the
focus moves), the category is put back while an Edge process with that add-on's app module still runs, as the add-on
means it to be. What the add-on says, and its settings, are unchanged. Nothing is done without that add-on. It works
while the assistant runs.
"""

from __future__ import annotations

import functools
import sys
import threading

#: The module NVDA imports Edge's app module from, and the add-on's settings panel in it.
APP_MODULE = "appModules.msedge"
PANEL = "MSEdgeDiscardAnnouncementsPanel"
#: NVDA's function that lets go of the app modules of processes that ended (appModuleHandler).
FUNCTION = "cleanup"
#: Marks the assistant's version, so another add-on's wrapper around it is recognized.
MARK = "_jawsMigratorEdgeAnnouncements"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
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


def _debug(message: str) -> None:
	try:
		_log().debug(message)
	except Exception:
		pass


def register() -> None:
	"""Keep the MS Edge Discard Announcements add-on's category in NVDA's Settings while Edge runs, from now on."""
	global _enabled
	with _lock:
		if _enabled:
			return
		try:
			import appModuleHandler

			current = vars(appModuleHandler).get(FUNCTION)
			if not _isOurs(current):
				if not callable(current):
					_failure(f"NVDA has no appModuleHandler.{FUNCTION} the assistant knows, so Edge's add-on is as it comes")
					return
				installed = _guarded(current)
				setattr(appModuleHandler, FUNCTION, installed)
				_replaced.append((appModuleHandler, FUNCTION, installed, current))
				_debug(f"jawsMigrator: the MS Edge Discard Announcements add-on's category stays in NVDA's Settings while Edge runs (appModuleHandler.{FUNCTION})")
		except Exception:
			_failure("can't keep the MS Edge Discard Announcements add-on's category in NVDA's Settings")
			return
		_enabled = True
	# Edge may have lost it before the assistant started.
	keepPanel()


def unregister() -> None:
	"""Give NVDA its own function back, where nothing has been put over the assistant's since."""
	global _enabled
	with _lock:
		_enabled = False
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


def _guarded(original):
	"""NVDA's appModuleHandler.cleanup, then the Edge add-on's category put back where one of its app modules still runs."""

	@functools.wraps(original)
	def cleanup(*args, **kwargs):
		result = original(*args, **kwargs)
		if _enabled:
			keepPanel()
		return result

	setattr(cleanup, MARK, _TOKEN)
	setattr(cleanup, ORIGINAL, original)
	return cleanup


def keepPanel() -> bool:
	"""Put the MS Edge Discard Announcements add-on's category back in NVDA's Settings when an Edge process with its app
	module runs and the category isn't there. True when it was put back."""
	module = sys.modules.get(APP_MODULE)
	panel = getattr(module, PANEL, None)
	appModuleClass = getattr(module, "AppModule", None)
	if not isinstance(panel, type) or not isinstance(appModuleClass, type):
		# No Edge app module yet, or not that add-on's.
		return False
	try:
		import appModuleHandler

		running = [mod for mod in list(appModuleHandler.runningTable.values()) if isinstance(mod, appModuleClass)]
		if not running:
			return False
		from gui import settingsDialogs

		categories = settingsDialogs.NVDASettingsDialog.categoryClasses
		if panel in categories:
			return False
		categories.append(panel)
	except Exception:
		_failure("could not put the MS Edge Discard Announcements add-on's category back in NVDA's Settings")
		return False
	_debug(f"jawsMigrator: an Edge process ended and the MS Edge Discard Announcements add-on took its category out of NVDA's Settings, though Edge still runs ({len(running)} of its app modules), so it is put back")
	return True
