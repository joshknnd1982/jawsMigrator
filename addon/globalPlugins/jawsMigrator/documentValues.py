# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""NVDA doesn't have a document build its whole text at every key, which slowed typing in a large file.

A tester typed at the top of NVDA's log, 21 million characters, open in Windows 11's Notepad: letters and spaces
went missing from the text ("a outlook message" came out "a outlook meg"), some came out of order, and NVDA said
little of what they typed. It didn't happen in a new, empty document.

On another computer, with NVDA 2026.2 and none of the tester's add-ons, the same typing went into a copy of that
log as real key presses, one every 150 ms: "a outlook message about typing in a large document is here " lost 5
to 23 of its 59 characters in each of seven runs. Notepad itself is the bottleneck: in a file that size it takes 0.17 to 0.37 seconds to type
one character (more at the top of a .txt file, less at the end), slower than the keys come, and with NVDA quit it
still lost letters in two runs of three (7 and 4). NVDA makes it worse. While a UI Automation control has the
focus, NVDA listens for changes to its properties, its Value among them (the "local event handler group",
``UIAHandler.UIAHandler.addLocalEventHandlerGroupToElement``). A Notepad document's Value is its whole text, and
with someone listening Notepad builds it at every change, 42 MB here: that added about 0.1 seconds to every
character (0.40 seconds instead of 0.30), and it failed every time, so no Value change ever came. With NVDA quit,
a test program that only listened for the Value lost 4, 17 and 9 letters. NVDA doesn't use those events anyway:
it follows a document through its caret and text events, and ignores a Value change from a UIA text control
(``NVDAObjects.UIA.UIA.event_valueChange``).

So for a document, or a multi-line text field, that NVDA reads through UI Automation's text and whose Value changes
it ignores, the assistant has NVDA register the same events without the Value property: its name, states, caret
and, where NVDA asks for them, its text changes all still come. An object that handles its own Value changes, or
a single-line field, keeps NVDA's registration. Where NVDA registers for every control's events at once (NVDA's
Advanced settings, "Windows UI Automation event registration" set to Global, or Windows 10) this changes nothing.
Notepad stays slow in a file that size, and can still lose a letter; this takes away what NVDA added. It works
while the assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

import collections
import functools
import threading

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "documentsWithoutValueEvents"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's versions.
MARK = "_jawsMigratorDocumentValues"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: NVDA's methods the assistant wraps, on UIAHandler.UIAHandler: the choice of a focused control's events, made in
#: NVDA's main thread, and the registration itself, made in NVDA's UI Automation thread.
CHOOSE = "addLocalEventHandlerGroupToElement"
ADD = "addEventHandlerGroup"
REMOVE = "removeEventHandlerGroup"
#: How many focused documents wait at most for NVDA's UI Automation thread to register their events.
MOST_PENDING = 32

_enabled = False
_failed = False
_lock = threading.Lock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: Focused documents whose events NVDA is about to register, in NVDA's UI Automation thread: {id(element): element}.
_pending: collections.OrderedDict = collections.OrderedDict()
#: Documents registered without the Value property: {id(element): (element, the assistant's group, NVDA's group)}.
_registered: dict = {}
#: The assistant's event groups, made once for each UIAHandler: [(the handler, {id(NVDA's group): the assistant's})].
_groups: list = []
#: The window classes whose documents the log has named once.
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
	"""Whether NVDA leaves the Value property out of a document's events: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have NVDA leave the Value property out of the events it registers for a focused document, from now on."""
	global _enabled
	if _enabled:
		return
	try:
		import UIAHandler

		owner = UIAHandler.UIAHandler
		for name in (CHOOSE, ADD, REMOVE):
			if not callable(owner.__dict__.get(name)):
				raise AttributeError(f"UIAHandler.UIAHandler has no {name}")
		for name, make in ((CHOOSE, _choosing), (ADD, _adding), (REMOVE, _removing)):
			original = owner.__dict__[name]
			installed = make(original)
			setattr(owner, name, installed)
			_replaced.append((owner, name, installed, original))
	except Exception:
		_restore()
		_failure("can't keep NVDA from listening for a document's whole text")
		return
	_enabled = True
	_log().debug("jawsMigrator: NVDA registers a focused document's UI Automation events without its Value (UIAHandler)")


def unregister() -> None:
	"""Give NVDA its own methods back where nothing has been put over the assistant's since, and give the documents
	registered without their Value NVDA's own registration."""
	global _enabled
	if not _enabled:
		return
	_enabled = False
	with _lock:
		registered = list(_registered.values())
		_registered.clear()
		_pending.clear()
		_groups.clear()
	adding = _original(ADD)
	removing = _original(REMOVE)
	_restore()
	if not registered or adding is None or removing is None:
		return
	try:
		import UIAHandler

		handler = UIAHandler.handler
	except Exception:
		return
	if handler is None:
		return

	def giveBack():
		for element, ours, theirs in registered:
			try:
				removing(handler, element, ours)
				adding(handler, element, theirs)
			except Exception:
				# The control has probably gone; the system forgets its registrations itself.
				pass

	try:
		handler.MTAThreadQueue.put_nowait(giveBack)
	except Exception:
		pass


def isRegistered() -> bool:
	return _enabled


def _original(name: str):
	for owner, replacedName, installed, original in _replaced:
		if replacedName == name:
			return original
	return None


def _restore() -> None:
	for owner, name, installed, original in reversed(_replaced):
		try:
			if owner.__dict__.get(name) is installed:
				setattr(owner, name, original)
		except Exception:
			pass
	_replaced.clear()


def _mark(installed, original):
	setattr(installed, MARK, _TOKEN)
	setattr(installed, ORIGINAL, original)
	return installed


def _followedDocument(element) -> bool:
	"""Whether ``element``, which NVDA registers events for as it gets the focus, is a document, or a multi-line text
	field, that NVDA reads through UI Automation's text and whose Value changes NVDA ignores. In NVDA's main thread."""
	import api
	from NVDAObjects.UIA import UIA, UIATextInfo

	focus = api.getFocusObject()
	if not isinstance(focus, UIA) or focus.UIAElement is not element:
		return False
	if not issubclass(focus.TextInfo, UIATextInfo):
		return False
	# An object that does something with its Value changes keeps them (NVDA's own ignores them for UIA text).
	if getattr(type(focus), "event_valueChange", None) is not UIA.event_valueChange:
		return False
	from controlTypes import Role, State

	role = focus.role
	if role == Role.DOCUMENT or (role == Role.EDITABLETEXT and State.MULTILINE in focus.states):
		_note(focus)
		return True
	return False


def _note(obj) -> None:
	windowClass = getattr(obj, "windowClassName", None) or "?"
	if windowClass in _logged:
		return
	_logged.add(windowClass)
	_log().debug(
		f"jawsMigrator: NVDA doesn't listen for this document's Value ({windowClass}): it is the whole text, which a "
		"program like Notepad builds at every key, slowing typing in a large file",
	)


def _choosing(original):
	"""NVDA's addLocalEventHandlerGroupToElement, in its main thread: note a focused document for _adding."""

	@functools.wraps(original)
	def addLocalEventHandlerGroupToElement(self, element, isFocus=False, *args, **kwargs):
		if _enabled and isFocus:
			try:
				if _followedDocument(element):
					with _lock:
						_pending[id(element)] = element
						while len(_pending) > MOST_PENDING:
							_pending.popitem(last=False)
			except Exception:
				_failure("could not tell whether the focus is a document, so NVDA listens for its Value")
		return original(self, element, isFocus, *args, **kwargs)

	return _mark(addLocalEventHandlerGroupToElement, original)


def _adding(original):
	"""NVDA's addEventHandlerGroup, in its UI Automation thread: a noted document gets the group without its Value."""

	@functools.wraps(original)
	def addEventHandlerGroup(self, element, eventHandlerGroup, *args, **kwargs):
		if _enabled:
			with _lock:
				noted = _pending.pop(id(element), None) is element
			if noted:
				try:
					ours = _withoutValue(self, eventHandlerGroup)
				except Exception:
					ours = None
					_failure("could not make NVDA's events without the Value property, so NVDA listens for it")
				if ours is not None:
					original(self, element, ours, *args, **kwargs)
					with _lock:
						_registered[id(element)] = (element, ours, eventHandlerGroup)
					return None
		return original(self, element, eventHandlerGroup, *args, **kwargs)

	return _mark(addEventHandlerGroup, original)


def _removing(original):
	"""NVDA's removeEventHandlerGroup, in its UI Automation thread: a document registered without its Value has
	that registration taken off."""

	@functools.wraps(original)
	def removeEventHandlerGroup(self, element, eventHandlerGroup, *args, **kwargs):
		with _lock:
			entry = _registered.get(id(element))
			if entry is not None and entry[0] is element:
				del _registered[id(element)]
			else:
				entry = None
		if entry is not None:
			return original(self, element, entry[1], *args, **kwargs)
		return original(self, element, eventHandlerGroup, *args, **kwargs)

	return _mark(removeEventHandlerGroup, original)


def _withoutValue(handler, group):
	"""The assistant's copy of NVDA's local event group ``group``, without the Value property, or None for a group
	that isn't one of NVDA's local groups. Made once, in NVDA's UI Automation thread, as NVDA makes its own."""
	local = getattr(handler, "localEventHandlerGroup", None)
	withTextChanges = getattr(handler, "localEventHandlerGroupWithTextChanges", None)
	if group is None or (group is not local and group is not withTextChanges):
		return None
	with _lock:
		for owner, made in _groups:
			if owner is handler:
				if id(group) in made:
					return made[id(group)]
				break
		else:
			made = {}
			_groups.append((handler, made))
	ours = _makeGroup(handler, textChanges=group is withTextChanges)
	with _lock:
		made[id(group)] = ours
	return ours


def _makeGroup(handler, textChanges: bool):
	"""NVDA's local event group (UIAHandler.UIAHandler._createLocalEventHandlerGroup), without the Value property."""
	import UIAHandler
	from UIAHandler import UIA, utils

	client = handler.clientObject
	# The event handler NVDA gave its own groups: its rate-limited one, or the UIAHandler itself.
	eventHandler = getattr(handler, "_rateLimitedEventHandler", None) or handler
	if isinstance(client, UIA.IUIAutomation6):
		group = client.CreateEventHandlerGroup()
	else:
		group = utils.FakeEventHandlerGroup(client)
	scope = UIA.TreeScope_Ancestors | UIA.TreeScope_Element
	propertyIds = sorted(set(UIAHandler.localEventHandlerGroupUIAPropertyIds) - {UIA.UIA_ValueValuePropertyId})
	group.AddPropertyChangedEventHandler(
		scope,
		handler.baseCacheRequest,
		eventHandler,
		*client.IntSafeArrayToNativeArray(propertyIds),
	)
	for eventId in UIAHandler.localEventHandlerGroupUIAEventIds:
		group.AddAutomationEventHandler(eventId, scope, handler.baseCacheRequest, eventHandler)
	if textChanges:
		group.AddAutomationEventHandler(UIA.UIA_Text_TextChangedEventId, scope, handler.baseCacheRequest, eventHandler)
	return group
