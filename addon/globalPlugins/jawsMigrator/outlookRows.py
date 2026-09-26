# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""In Outlook's message list, NVDA says the message you move to, not the one you leave.

A tester pressed End in Outlook's Inbox to go to the newest message. NVDA said "unread From joshknnd1982,
Subject Re: [joshknnd1982/jawsMigrator] ...", the message the tester had been on, and only then the newest
message, "unread From RTM News, ..., 2663 of 2663". The tester pressed Enter while NVDA was still saying the first
one and opened the newest message, which wasn't the one NVDA had said. The first message wasn't unread either.
Down Arrow did the same when the next message was unread and the one the tester left wasn't.

When the selection moves, Outlook tells screen readers that the name of the message you left changed. That
message still has NVDA's focus until NVDA handles Outlook's focus event for the new message, so NVDA says its
name again as a change (NVDAObject.event_nameChange, NVDA 2026.2), without its position. NVDA's Outlook support
builds a message's name from its columns and adds unread, replied, has attachment and the importance, but it takes
those from Outlook's selection, not from the message itself (``UIAGridRow._get_name`` in appModules/outlook.py).
By then the selection is the message you moved to. So the name of the message you left has the other message's
status, and when that status differs, for example unread where the left message was read, NVDA finds the name
changed and says it. JAWS says the message list's new item when it becomes the active one, and nothing for the
item you left (Outlook.jss, ActiveItemChangedEvent).

So when Outlook reports a change of name for the message NVDA's focus is on, and Outlook's focus is no longer on
that message, NVDA doesn't handle it: the focus event for the message you moved to follows, and NVDA says that
message as usual. NVDA asks UI Automation where the focus is, as NVDA does itself to know whether an element
still has the focus (``UIAHandler.addLocalEventHandlerGroupToElement``). A change of the message Outlook's
focus is still on is said as before, and so is anything else in Outlook, and anything that can't be checked.
Braille shows the message you moved to once NVDA has its focus event. It works while the assistant runs, unless
it is turned off in NVDA's Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "quietLeftOutlookMessage"
#: The name NVDA gives classic Outlook's app module.
APP_NAME = "outlook"
#: The UI Automation classes of the rows of Outlook's message list, which NVDA's Outlook support reads as
#: messages (``UIAGridRow``): a message, a message in a conversation, and a conversation's heading.
ROW_CLASSES = ("LeafRow", "ThreadItem", "ThreadHeader")

_enabled = False
_failed = False


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
	"""Whether NVDA leaves out the Outlook message you leave: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Leave out the Outlook message you leave, from now on."""
	global _enabled
	_enabled = True


def unregister() -> None:
	"""Have NVDA handle every change of an Outlook message's name as it does."""
	global _enabled
	_enabled = False


def isRegistered() -> bool:
	return _enabled


def isMessage(obj) -> bool:
	"""Whether ``obj`` is a message, a message in a conversation or a conversation's heading in Outlook's message list."""
	appModule = getattr(obj, "appModule", None)
	if getattr(appModule, "appName", None) != APP_NAME:
		return False
	element = getattr(obj, "UIAElement", None)
	if element is None:
		return False
	return element.cachedClassName in ROW_CLASSES


def _hasOutlooksFocus(obj) -> bool:
	"""Whether UI Automation's focus is on ``obj``'s element, as NVDA checks it: CompareElements with GetFocusedElement."""
	import UIAHandler

	client = UIAHandler.handler.clientObject
	return bool(client.CompareElements(client.GetFocusedElement(), obj.UIAElement))


def leftBehind(obj) -> bool:
	"""Whether ``obj`` is the Outlook message NVDA's focus is on, and Outlook's focus has moved on from it.

	NVDA would say its name with the status of the message you moved to, so the change isn't said: the focus
	event for that message follows. False for anything else, and when it can't be checked.
	"""
	if not _enabled:
		return False
	try:
		import api

		if api.getFocusObject() is not obj or not isMessage(obj) or _hasOutlooksFocus(obj):
			return False
	except Exception:
		_failure("could not check whether Outlook's focus is still on a message, so NVDA says its change as it does")
		return False
	try:
		# What NVDA said for the message, from its notes: reading its name again would ask Outlook for it.
		notes = getattr(obj, "_speakObjectPropertiesCache", None)
		said = notes.get("name") if isinstance(notes, dict) else None
		_log().debug(
			f"jawsMigrator: Outlook's focus has left the message {said!r}, so NVDA doesn't say it again "
			"with the status of the message you moved to"
		)
	except Exception:
		pass
	return True
