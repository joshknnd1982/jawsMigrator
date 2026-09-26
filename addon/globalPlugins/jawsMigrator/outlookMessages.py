# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""An Outlook message you open is read as JAWS reads it: from the top, "send mail link" for an e-mail address, and no
heading for the From line of a message it quotes.

A tester opened the same message in classic Outlook with JAWS and with NVDA (issue 20, "What Jaws says when opening an
outlook message"). It was a forwarded message, whose text starts with Outlook's header of the message it quotes:
"From: nvda-addons@nvda-addons.groups.io <nvda-addons@nvda-addons.groups.io> On Behalf Of Alireza Mamani via
groups.io", each address a link to a mailto: address. JAWS said, with no key pressed: "From: Send Mail Link
nvda-addons@nvda-addons.groups.io < Send Mail Link nvda-addons@nvda-addons.groups.io> On Behalf Of Alireza Mamani via
groups.io", "…", "Today, I am writing to introduce an add-on..." and on through the message. NVDA said nothing, and
with the arrow keys "heading level 1, From:", "link, nvda-addons@nvda-addons.groups.io", "heading level 1, <" and
"heading level 1, > On Behalf Of Alireza Mamani via groups.io". Three things differ.

* JAWS reads a message from the top when it opens. Its Outlook scripts start Say All when a read-only message's
  document loads (Outlook.jss, DocumentLoadedEvent, ShouldMessageSayAll), as JAWS's Outlook settings have it unless
  "Messages automatically read" is turned off (Outlook.jcf, MessageSayAllVerbosity=1). They say no window title first
  (SpeakWindowTitlesForVirtualMessages is off) and no From or Subject (MessageHeaderVerbosity=0). NVDA reads a
  document it opens only with "Automatic Say All on page load", one setting for web pages and messages alike, which
  the migration takes from JAWS's setting for web pages (SayAllOnDocumentLoad, off as JAWS comes). Without it, NVDA
  says the line at the caret (browseMode.BrowseModeDocumentTreeInterceptor.event_treeInterceptor_gainFocus), and the
  Outlook First Line Silence add-on the tester runs keeps even that quiet.
* JAWS says "Send Mail Link" for a link to an e-mail address, one of its link types (jfw.exe: "Send Mail Link",
  "FTP Link", "same page link"...), which it says with "Identify link type" on, as JAWS comes (IdentifyLinkType=1).
  NVDA says "link": its only link type is "same page", which its "Link type" setting turns on and off.
* Word gives the From line of a message that a reply or forward quotes an outline level, so that Outlook can collapse
  what follows it. Word's UI Automation calls that paragraph a heading (UIA_StyleIdAttributeId), and NVDA says
  "heading level 1" (NVDAObjects.UIA.UIATextInfo._getFormatFieldHeadings), again after each link in the line, as the
  links have a style of their own. NVDA's issue #5518 found the same through Word's object model: "outline level is
  used for something other than headings". JAWS says no heading there, though its Outlook settings say headings with
  their level (HeadingIndication=2): it goes by Word's heading styles.

So in classic Outlook:

* When a message you read opens, NVDA reads it from the caret, at the top, as Say All (NVDA+Down Arrow) does, where it
  said the line at the caret: what "Automatic Say All on page load" does, for Outlook messages alone. A message NVDA
  reads already, coming back to a message that is open, and a message you write (which NVDA doesn't read in browse
  mode) are as before. A key stops the reading, as it stops Say All.
* A link to a mailto: address is "send mail link" where NVDA says "link", while NVDA's "Link type" is checked in its
  Document Formatting settings: NVDA says a field's roleText in the place of its role. Braille shows "lnk" as before.
* Text Word calls a heading is said as a heading when its Word style is a heading style, one whose name has the
  heading's level in it ("Heading 1", "Überschrift 1"). The From line of a quoted message, whose style isn't, is said
  without "heading level 1". The debug log names each style this decides for, once.

The last two are for messages NVDA reads through UI Automation, as it does with a recent Office such as the
tester's. It works while the assistant runs, unless it is turned off in NVDA's Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

import contextlib
import functools
import re
import threading

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "outlookMessagesAsJaws"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own versions, so another add-on's wrapper around one is recognized.
MARK = "_jawsMigratorOutlookMessages"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: The name NVDA gives classic Outlook's app module.
APP_NAME = "outlook"
#: What JAWS says for a link to an e-mail address, where NVDA says "link".
SEND_MAIL_LINK = "send mail link"
#: How the address of a link to an e-mail address starts.
MAILTO = "mailto:"
#: What NVDA says in the place of a field's role (speech.getControlFieldSpeech), and what braille shows in its place,
#: before roleText (braille.getControlFieldBraille).
ROLE_TEXT = "roleText"
ROLE_TEXT_BRAILLE = "roleTextBraille"
#: NVDA's browse mode event for a document it comes into, where it reads a document that has just opened.
GAIN_FOCUS = "event_treeInterceptor_gainFocus"
#: NVDA's text of a Word document read through UI Automation: its formatting for a range, and its field for an element.
TEXT_INFO = "WordDocumentTextInfo"
FORMAT_AT_RANGE = "_getFormatFieldAtRange"
CONTROL_FIELD = "_getControlFieldForUIAObject"
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: NVDA's OutputReason.CARET, textInfos.UNIT_LINE and Role.LINK, once known.
_caret = None
_line = None
_linkRole = None
#: (style name, level) pairs the log has noted, so each is noted once; and whether a mail link has been noted.
_notedStyles: set = set()
_notedMailLink = False
#: For each thread: whether a message's opening is being handled, so a second wrapper of the assistant's passes it on.
_local = threading.local()


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
	"""Whether NVDA reads an Outlook message as JAWS does: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have NVDA read Outlook messages as JAWS does, from now on. What isn't in place yet is put in place: each part
	works without the others."""
	global _enabled, _caret, _line, _linkRole
	try:
		import textInfos
		from controlTypes import OutputReason, Role

		_caret, _line, _linkRole = OutputReason.CARET, textInfos.UNIT_LINE, Role.LINK
	except Exception:
		_failure("can't have NVDA read Outlook messages as JAWS does, so NVDA reads them as it does")
		return
	reading = saying = False
	try:
		import browseMode

		with _lock:
			reading = _replace(browseMode.BrowseModeDocumentTreeInterceptor, GAIN_FOCUS, _gainFocusGuarded)
	except Exception:
		_failure("can't have NVDA read an Outlook message from the top when it opens, so NVDA says its first line")
	try:
		# NVDA loads this with UI Automation, before add-ons, and imports it itself for Word and Outlook.
		from NVDAObjects.UIA.wordDocument import WordDocumentTextInfo

		with _lock:
			saying = _replace(WordDocumentTextInfo, CONTROL_FIELD, _controlFieldGuarded)
			saying = _replace(WordDocumentTextInfo, FORMAT_AT_RANGE, _formatGuarded) or saying
	except Exception:
		_failure("can't change how NVDA says links and headings in Outlook messages, so it says them as it does")
	_enabled = _enabled or reading or saying


def unregister() -> None:
	"""Give NVDA its own functions back, where nothing has been put over the assistant's since."""
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
	"""Whether ``function`` is one of the assistant's versions, or wraps one (as another add-on's functools.wraps wrapper would)."""
	for _ in range(_MOST_WRAPPERS):
		if function is None:
			return False
		if getattr(function, MARK, None) is _TOKEN:
			return True
		function = getattr(function, "__wrapped__", None)
	return False


def _replace(owner, name: str, guarded) -> bool:
	"""Put the assistant's version of ``name`` in the place of NVDA's own on ``owner``, once. True when it is there."""
	current = vars(owner).get(name)
	if _isOurs(current):
		# Still there from before: turned off and on again, or another add-on has put its own around it since.
		return True
	if not callable(current):
		_failure(f"NVDA has no {getattr(owner, '__name__', owner)}.{name} the assistant knows, so NVDA reads Outlook messages as it does")
		return False
	installed = guarded(current)
	setattr(installed, MARK, _TOKEN)
	setattr(installed, ORIGINAL, current)
	setattr(owner, name, installed)
	_replaced.append((owner, name, installed, current))
	_log().debug(f"jawsMigrator: NVDA reads Outlook messages as JAWS does ({getattr(owner, '__name__', owner)}.{name})")
	return True


def inOutlook(thing) -> bool:
	"""Whether ``thing``, an NVDA object or its text, is in classic Outlook."""
	obj = getattr(thing, "obj", thing)
	appModule = getattr(obj, "appModule", None)
	return getattr(appModule, "appName", None) == APP_NAME


# -- Reading a message from the top when it opens -----------------------------------------------------------------


def isOpeningMessage(treeInterceptor) -> bool:
	"""Whether NVDA's browse mode ``treeInterceptor`` is an Outlook message you read, coming into it for the first time.

	NVDA reads an Outlook message in browse mode only when it is one you read (appModules.outlook,
	``shouldCreateTreeInterceptor`` is ``isReadonlyViewer``); a message you write has no browse mode.
	"""
	if getattr(treeInterceptor, "_hadFirstGainFocus", True):
		return False
	root = getattr(treeInterceptor, "rootNVDAObject", None)
	return inOutlook(root) and getattr(root, "isReadonlyViewer", False) is True


def _argument(args: tuple, kwargs: dict, name: str, index: int, default=None):
	"""An argument of speech.speakTextInfo after the text: useCache, formatConfig, unit, reason..."""
	if name in kwargs:
		return kwargs[name]
	return args[index] if len(args) > index else default


def isFirstLine(treeInterceptor, info, args: tuple, kwargs: dict) -> bool:
	"""Whether NVDA is saying ``info`` as the line at the caret of ``treeInterceptor``, as it does when it comes into a
	document it doesn't read from the top."""
	return (
		getattr(info, "obj", None) is treeInterceptor
		and _argument(args, kwargs, "reason", 3) == _caret
		and _argument(args, kwargs, "unit", 2) == _line
	)


@contextlib.contextmanager
def _firstLineHeldBack(treeInterceptor, held: list):
	"""While NVDA comes into ``treeInterceptor``, the line at its caret isn't said; ``held`` gets it instead."""
	import speech

	current = speech.speakTextInfo

	def speakTextInfo(info, *args, **kwargs):
		if not held and isFirstLine(treeInterceptor, info, args, kwargs):
			held.append(info)
			return False
		return current(info, *args, **kwargs)

	speech.speakTextInfo = speakTextInfo
	try:
		yield
	finally:
		if speech.speakTextInfo is speakTextInfo:
			speech.speakTextInfo = current


def readMessage(treeInterceptor) -> bool:
	"""Read the message from the caret, as NVDA's "Automatic Say All on page load" does. True when it is read."""
	from speech import sayAll

	if getattr(treeInterceptor, "passThrough", False):
		# Focus mode came on as the message opened: NVDA reads nothing from the caret then.
		return False
	sayAll.SayAllHandler.readText(sayAll.CURSOR.CARET)
	_log().debug(
		"jawsMigrator: an Outlook message you opened is read from the top, as JAWS reads it, where NVDA said its first line",
	)
	return True


def _gainFocusGuarded(original):
	"""NVDA's browse mode coming into a document: an Outlook message that has just opened is read from the top."""

	@functools.wraps(original)
	def event_treeInterceptor_gainFocus(self, *args, **kwargs):
		if not _enabled or getattr(_local, "opening", False):
			return original(self, *args, **kwargs)
		try:
			opening = isOpeningMessage(self)
		except Exception:
			_failure("could not tell whether an Outlook message had just opened, so NVDA says its first line")
			opening = False
		if not opening:
			return original(self, *args, **kwargs)
		held = []
		_local.opening = True
		try:
			with _firstLineHeldBack(self, held):
				result = original(self, *args, **kwargs)
		finally:
			_local.opening = False
		if held:
			try:
				read = readMessage(self)
			except Exception:
				_failure("could not read an Outlook message from the top, so NVDA says its first line")
				read = False
			if not read:
				import speech

				speech.speakTextInfo(held[0], reason=_caret, unit=_line)
		return result

	return event_treeInterceptor_gainFocus


# -- "send mail link" -------------------------------------------------------------------------------------------


def isMailLink(address) -> bool:
	"""Whether ``address``, where a link goes, is an e-mail address: mailto:someone@example.com."""
	return isinstance(address, str) and address.strip().lower().startswith(MAILTO)


def saysLinkType() -> bool:
	"""Whether NVDA's "Link type" is checked in its Document Formatting settings, as it is when NVDA comes: NVDA's
	setting for saying what kind of link a link is."""
	import config

	try:
		return bool(config.conf["documentFormatting"]["reportLinkType"])
	except KeyError:
		return True


def sayAsSendMailLink(field) -> None:
	"""Have NVDA say its ``field`` for a link as "send mail link" where it says "link". NVDA says a field's roleText in
	the place of its role (speech.getControlFieldSpeech); braille shows roleTextBraille before roleText, and with
	nothing there, the link as NVDA shows it ("lnk", or "vlnk" for a visited one)."""
	field[ROLE_TEXT] = SEND_MAIL_LINK
	field[ROLE_TEXT_BRAILLE] = None


def _controlFieldGuarded(original):
	"""NVDA's field for an element of a Word document: a link to an e-mail address in Outlook is a "send mail link"."""

	@functools.wraps(original)
	def _getControlFieldForUIAObject(self, obj, *args, **kwargs):
		global _notedMailLink
		field = original(self, obj, *args, **kwargs)
		if not _enabled:
			return field
		try:
			if field.get("role") != _linkRole or field.get(ROLE_TEXT) or not inOutlook(self):
				return field
			try:
				# Word gives a link's address as its value, which UI Automation has cached for NVDA's fields.
				address = obj.value
			except Exception:
				address = None
			if isMailLink(address) and saysLinkType():
				sayAsSendMailLink(field)
				if not _notedMailLink:
					_notedMailLink = True
					_log().debug(f"jawsMigrator: a link to {address!r} in an Outlook message is \"{SEND_MAIL_LINK}\", as JAWS says it")
		except Exception:
			_failure("could not tell whether a link in an Outlook message is to an e-mail address, so NVDA says \"link\"")
		return field

	return _getControlFieldForUIAObject


# -- Headings ---------------------------------------------------------------------------------------------------


def isHeadingStyle(styleName: str, level) -> bool:
	"""Whether a Word style is a heading style for ``level``: its name has the level in it, as Word's heading styles
	have in every language ("Heading 1", "Überschrift 1", "Titre 1", "見出し 1")."""
	try:
		level = int(level)
	except (TypeError, ValueError):
		return True
	return re.search(rf"(?<!\d){level}(?!\d)", styleName) is not None


def _styleName(field, textRange):
	"""The Word style of the text ``field`` is for: from the field, where NVDA's "Style" is checked, or from Word."""
	style = field.get("style")
	if isinstance(style, str) and style.strip():
		return style
	import UIAHandler

	style = textRange.GetAttributeValue(UIAHandler.UIA_StyleNameAttributeId)
	# A range of more than one style, or a Word without the attribute, gives something other than text.
	return style if isinstance(style, str) and style.strip() else None


def _noteStyle(style: str, level, kept: bool) -> None:
	if (style, level) in _notedStyles:
		return
	_notedStyles.add((style, level))
	if kept:
		_log().debug(f"jawsMigrator: text in Word's style {style!r} in an Outlook message is said as heading level {level}")
	else:
		_log().debug(
			f"jawsMigrator: text in Word's style {style!r} in an Outlook message isn't said as heading level {level}, "
			"as JAWS says it: Word calls it a heading for its outline level, not its style (the From line of a quoted message)",
		)


def leaveOutHeading(textInfo, textRange, formatField) -> bool:
	"""Take the heading level out of ``formatField``, NVDA's formatting of ``textRange`` in ``textInfo``, when the text
	is in Outlook and not in a heading style. True when it was taken out."""
	field = getattr(formatField, "field", formatField)
	if not hasattr(field, "get"):
		return False
	level = field.get("heading-level")
	if not level or not inOutlook(textInfo):
		return False
	style = _styleName(field, textRange)
	if style is None:
		return False
	kept = isHeadingStyle(style, level)
	_noteStyle(style, level, kept)
	if kept:
		return False
	del field["heading-level"]
	return True


def _formatGuarded(original):
	"""NVDA's formatting of a range of a Word document: in Outlook, no heading level for text in no heading style."""

	@functools.wraps(original)
	def _getFormatFieldAtRange(self, textRange, *args, **kwargs):
		formatField = original(self, textRange, *args, **kwargs)
		if _enabled:
			try:
				leaveOutHeading(self, textRange, formatField)
			except Exception:
				_failure("could not tell whether text in an Outlook message is a heading, so NVDA says it as it does")
		return formatField

	return _getFormatFieldAtRange
