# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""In an Outlook message, NVDA doesn't say page and section numbers, as JAWS doesn't.

A tester writing an Outlook message pressed Control+Home and heard "page 1, section 1" before the first line
(issue 18, "It says page one section 1 when in a outlook message. Jaws doesn't say that"). The log shows the same
for Up Arrow into the text of a reply, and for Enter after "answers:" at the top of another reply.

Outlook's messages are Word documents. NVDA says page and section numbers in Word when "Page numbers" is checked in
its Document Formatting settings, as it is when NVDA comes: ``speech.getFormatFieldSpeech`` says "page 1" and
"section 1" when they differ from the numbers it said last, and in a document it hasn't read yet, that is the first
line it reads. NVDA's own Outlook support leaves them out, "None of which are appropriate for outlook"
(``appModules.outlook.OutlookWordDocument.ignorePageNumbers``), but only where NVDA reads Word through Word's object
model, which then doesn't ask Word for them (``NVDAObjects.window.winword.WordDocumentTextInfo``). With a recent
Office, such as the tester's 16.0.20326, NVDA reads Word through UI Automation (``UIAHandler.shouldUseUIAInMSWord``).
There, NVDA's Outlook support (``OutlookUIAWordDocument``) doesn't set ``ignorePageNumbers``, and NVDA's UI Automation
support for Word doesn't look for it: it asks Word for the page and section numbers
(``NVDAObjects.UIA.wordDocument.WordDocumentTextInfo._getFormatFieldAtRange``) and gives each line the number of the
page it is on (``getTextWithFields``). JAWS says no page, section or column in Outlook: its Word scripts return
before saying any while Outlook is active (WordFunc.jss, PageSectionColumnChangedEvent, ``|| OutlookIsActive()``).

So in Outlook, NVDA's UI Automation support for Word gives no page, section or text column numbers, as its support
through Word's object model gives none: they are taken out of the text's formatting ("page-number",
"section-number", "text-column-number" and "text-column-count") before NVDA says it, for the caret, say all and a
message you read in browse mode. The rest of the formatting is as before, and so is Word itself. It works while the
assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

import functools
import threading

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "outlookWithoutPageNumbers"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own version, so another add-on's wrapper around it is recognized.
MARK = "_jawsMigratorOutlookPages"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: The name NVDA gives classic Outlook's app module.
APP_NAME = "outlook"
#: NVDA's text of a Word document read through UI Automation, and the method that gives its text and formatting.
TEXT_INFO = "WordDocumentTextInfo"
METHOD = "getTextWithFields"
#: What NVDA's formatting holds for a page, a section and text columns: what NVDA says with "Page numbers" checked
#: (speech.getFormatFieldSpeech), and what its Outlook support leaves out through Word's object model.
PAGE_KEYS = ("page-number", "section-number", "text-column-number", "text-column-count")
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: NVDA's textInfos.FieldCommand and textInfos.FormatField, once known.
_fieldCommand = None
_formatField = None
#: Whether the log has said once that page and section numbers were left out of an Outlook message.
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
	"""Whether NVDA leaves page and section numbers out of Outlook messages: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have NVDA leave page and section numbers out of Outlook messages, from now on."""
	global _enabled, _fieldCommand, _formatField
	if _enabled:
		return
	try:
		import textInfos
		# NVDA loads this with UI Automation, before add-ons, and imports it itself for Word and Outlook.
		from NVDAObjects.UIA.wordDocument import WordDocumentTextInfo

		_fieldCommand, _formatField = textInfos.FieldCommand, textInfos.FormatField
		with _lock:
			if not _replace(WordDocumentTextInfo):
				return
	except Exception:
		_failure("can't leave page and section numbers out of Outlook messages, so NVDA says them as it does")
		return
	_enabled = True


def unregister() -> None:
	"""Give NVDA its own method back, where nothing has been put over the assistant's since."""
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
	"""Put the assistant's version of NVDA's method in its place on ``owner``, once. True when it is there."""
	current = vars(owner).get(METHOD)
	if _isOurs(current):
		# Still there from before: turned off and on again, or another add-on has put its own around it since.
		return True
	if not callable(current):
		_failure(f"NVDA has no {TEXT_INFO}.{METHOD} the assistant knows, so NVDA says page numbers in Outlook as it does")
		return False
	installed = _guarded(current)
	setattr(owner, METHOD, installed)
	_replaced.append((owner, METHOD, installed, current))
	_log().debug(f"jawsMigrator: NVDA leaves page and section numbers out of Outlook messages ({owner.__name__}.{METHOD})")
	return True


def _mark(installed, original):
	setattr(installed, MARK, _TOKEN)
	setattr(installed, ORIGINAL, original)
	return installed


def inOutlook(info) -> bool:
	"""Whether ``info``, NVDA's text of a Word document, is in classic Outlook: a message you write or read."""
	appModule = getattr(getattr(info, "obj", None), "appModule", None)
	return getattr(appModule, "appName", None) == APP_NAME


def leaveOutPages(fields) -> list:
	"""Take the page, section and text column numbers out of the formatting in ``fields``, NVDA's text with its
	fields, in place. Gives back what was taken out, as [(name, value)]."""
	left = []
	for item in fields:
		if not isinstance(item, _fieldCommand) or not isinstance(item.field, _formatField):
			continue
		for key in PAGE_KEYS:
			if key in item.field:
				left.append((key, item.field.pop(key)))
	return left


def _guarded(original):
	"""NVDA's WordDocumentTextInfo.getTextWithFields: in Outlook, without page, section and text column numbers."""

	@functools.wraps(original)
	def getTextWithFields(self, *args, **kwargs):
		global _logged
		fields = original(self, *args, **kwargs)
		if _enabled:
			try:
				if inOutlook(self):
					left = leaveOutPages(fields)
					if left and not _logged:
						_logged = True
						_log().debug(
							f"jawsMigrator: page and section numbers are left out of an Outlook message, as JAWS leaves them "
							f"out, and NVDA's Outlook support does through Word's object model: {left}",
						)
			except Exception:
				_failure("could not leave page and section numbers out of an Outlook message, so NVDA says them")
		return fields

	return _mark(getTextWithFields, original)
