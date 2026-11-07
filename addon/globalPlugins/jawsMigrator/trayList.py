# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""Enter in the System Tray List add-on's list right-clicks the icon, as Enter in JAWS's list does (issue 54).

A tester pressed NVDA+F11, moved to "Volume" in the list of system tray icons and pressed Enter, and Windows' Quick
Settings opened, where JAWS would have opened the icon's menu. NVDA itself has no list of the tray's icons: NVDA+F11 is
the System Tray List add-on (systrayList, 2026.08.24), whose dialog has the buttons Left Click (Alt+L), Left Double
Click (Alt+D) and Right Click (Alt+R), and Left Double Click is its default button, so Enter in the list double-clicks
the icon. JAWS's list, Insert+F11 ("Select a System Tray Icon", in jfw.exe of JAWS 2027), has the buttons Right Single
Click, Left Single Click and Left Double Click with the same letters, and Right Single Click is its default button
(BS_DEFPUSHBUTTON); JAWS's own help for the list (common.jsm, cmsg368_L) says "To simulate a right single mouse click
on the selected item, press ENTER." So in JAWS, Enter on an icon in the list opens its menu, and Alt+L clicks it.

So when System Tray List shows the tray's icons, its Right Click button is made the default, and Enter in the list
right-clicks the icon, as in JAWS. Alt+L, Alt+D and Alt+R, and Enter on a button you Tab to, still press that button.
The same dialog shows the taskbar's programs when NVDA+F11 is pressed twice, which JAWS's list doesn't; there the
add-on's own default comes back. Nothing else the add-on does changes. It works while the assistant runs, unless it is
turned off in NVDA's Settings, JAWS Migration Assistant.

What the assistant changes is read from the add-on's own code: its plugin (``globalPlugins.systrayList.GlobalPlugin``)
fills and shows the dialog in ``_createSystrayList`` (the tray's icons) and ``_createTaskList`` (the taskbar's
programs), and keeps it in ``_systrayListDialog``; the dialog's buttons, in the order the add-on makes them, are Left
Click, Left Double Click, Right Click and Cancel. The buttons are found by that order, so the add-on's translations
don't matter.
"""

from __future__ import annotations

import functools
import sys

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "rightClickInSystrayList"
#: System Tray List's global plugin, as NVDA imports it.
MODULE = "globalPlugins.systrayList"
PLUGIN_CLASS = "GlobalPlugin"
#: Its methods that fill and show the dialog: the tray's icons (NVDA+F11), and the taskbar's programs (pressed twice).
TRAY = "_createSystrayList"
TASKS = "_createTaskList"
#: Where its plugin keeps the dialog.
DIALOG = "_systrayListDialog"
#: The dialog's buttons other than Cancel, in the order the add-on makes them: Left Click, Left Double Click, Right Click.
BUTTONS = 3
RIGHT_CLICK = 2
#: Marks what the assistant put in the place of the add-on's own, and keeps its own.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's versions, so another add-on's wrapper around one is recognized.
MARK = "_jawsMigratorTrayList"
#: Where the dialog keeps the add-on's own default button, once the assistant has changed it.
OWN_DEFAULT = "_jawsMigratorOwnDefault"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
#: The failures already logged, once each: {what}.
_failed: set = set()
#: What the assistant put in the place of the add-on's own: [(its plugin class, method name, the assistant's, its own)].
_replaced: list = []
#: The plugin whose dialog the assistant changed last, to give the dialog its own default back when turned off.
_plugin = None
#: Whether the log has said once that Enter in the list right-clicks.
_logged = False


def _log():
	from logHandler import log

	return log


def _failure(what: str) -> None:
	if what in _failed:
		return
	_failed.add(what)
	try:
		_log().debugWarning(f"jawsMigrator: {what}", exc_info=True)
	except Exception:
		pass


def wanted(stateData: dict) -> bool:
	"""Whether Enter in System Tray List's list right-clicks the icon, as in JAWS: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have Enter in System Tray List's list of the tray's icons right-click the icon, from now on."""
	global _enabled
	if _enabled:
		# Called again after a migration, a restore or a configuration reload: the add-on may have loaded since.
		_install()
		return
	_enabled = True
	if not _install():
		# NVDA imports the global plugins one after another, and System Tray List may come after the assistant.
		try:
			import wx

			wx.CallAfter(_installIfWanted)
		except Exception:
			pass


def unregister() -> None:
	"""Give System Tray List its own methods and its dialog its own default button back."""
	global _enabled, _plugin
	if not _enabled:
		return
	_enabled = False
	plugin, _plugin = _plugin, None
	try:
		_ownDefault(_dialogOf(plugin))
	except Exception:
		_failure("could not give System Tray List's dialog its own default button back")
	for pluginClass, name, installed, original in reversed(_replaced):
		try:
			if vars(pluginClass).get(name) is installed:
				setattr(pluginClass, name, original)
		except Exception:
			pass
	_replaced.clear()


def isRegistered() -> bool:
	return _enabled


def isInstalled() -> bool:
	"""Whether the assistant's versions of both methods are in System Tray List now."""
	pluginClass = _pluginClass(sys.modules.get(MODULE))
	return pluginClass is not None and all(_isOurs(vars(pluginClass).get(name)) for name in (TRAY, TASKS))


def _installIfWanted() -> None:
	if _enabled:
		_install()


def _pluginClass(module):
	pluginClass = vars(module).get(PLUGIN_CLASS) if module is not None else None
	return pluginClass if isinstance(pluginClass, type) else None


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
	"""Put the assistant's versions of the two methods in System Tray List, once. True when they are there."""
	module = sys.modules.get(MODULE)
	if module is None:
		# Not installed, turned off, or not loaded yet.
		return False
	try:
		pluginClass = _pluginClass(module)
		if pluginClass is None:
			_failure(f"System Tray List has no {PLUGIN_CLASS} the assistant knows, so Enter in its list does what it always has")
			return False
		current = {name: vars(pluginClass).get(name) for name in (TRAY, TASKS)}
		if all(_isOurs(function) for function in current.values()):
			# Still there from before: turned off and on again, or another add-on has put its own around them since.
			return True
		if not all(callable(function) for function in current.values()):
			_failure(f"System Tray List has no {TRAY} and {TASKS} the assistant knows, so Enter in its list does what it always has")
			return False
		for name, makeDefault in ((TRAY, _rightClickDefault), (TASKS, _ownDefault)):
			original = current[name]
			if _isOurs(original):
				continue
			installed = _wrapped(original, makeDefault)
			setattr(pluginClass, name, installed)
			_replaced.append((pluginClass, name, installed, original))
		_log().debug(f"jawsMigrator: Enter in System Tray List's list of the tray's icons right-clicks the icon ({MODULE}.{PLUGIN_CLASS}.{TRAY})")
		return True
	except Exception:
		_failure("can't have Enter in System Tray List's list right-click the icon")
		return False


def _dialogOf(plugin):
	"""The dialog System Tray List's plugin shows, while it is there (wx's deleted windows are false), or None."""
	if plugin is None:
		return None
	dialog = getattr(plugin, DIALOG, None)
	try:
		return dialog if dialog else None
	except Exception:
		return None


def _clickButtons(dialog) -> list:
	"""The dialog's buttons other than Cancel, in the order the add-on made them."""
	import wx

	return [child for child in dialog.GetChildren() if isinstance(child, wx.Button) and child.GetId() != wx.ID_CANCEL]


def _note() -> None:
	global _logged
	if _logged:
		return
	_logged = True
	_log().debug(
		"jawsMigrator: Enter in System Tray List's list right-clicks the icon, as Enter in JAWS's list (Insert+F11) does: "
		"its default button is Right Single Click; Alt+L still clicks and Alt+D double-clicks",
	)


def _rightClickDefault(dialog) -> None:
	"""The dialog's Right Click button made its default, so Enter in the list right-clicks; its own default is kept."""
	if dialog is None:
		return
	buttons = _clickButtons(dialog)
	if len(buttons) != BUTTONS:
		_failure(f"System Tray List's dialog has {len(buttons)} buttons, not the {BUTTONS} the assistant knows, so Enter does what it always has")
		return
	if getattr(dialog, OWN_DEFAULT, None) is None:
		setattr(dialog, OWN_DEFAULT, dialog.GetDefaultItem())
	buttons[RIGHT_CLICK].SetDefault()
	_note()


def _ownDefault(dialog) -> None:
	"""The dialog's own default button back, where the assistant changed it."""
	if dialog is None:
		return
	own = getattr(dialog, OWN_DEFAULT, None)
	if own is None:
		return
	setattr(dialog, OWN_DEFAULT, None)
	if own:
		own.SetDefault()


def _wrapped(original, makeDefault):
	"""System Tray List's method that fills and shows the dialog, and then the default button the list should have."""

	@functools.wraps(original)
	def create(self, *args, **kwargs):
		global _plugin
		result = original(self, *args, **kwargs)
		if _enabled:
			try:
				_plugin = self
				makeDefault(_dialogOf(self))
			except Exception:
				_failure("could not choose the default button of System Tray List's dialog, so Enter does what it always has")
		return result

	setattr(create, MARK, _TOKEN)
	setattr(create, ORIGINAL, original)
	return create
