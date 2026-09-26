# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""An Outlook message you read is said as JAWS says it: "send mail link" for an e-mail address, where a list starts and
ends, and no heading for the From line of a message it quotes; and, when turned on, read from the top when it opens.

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
  mode) are as before. A key stops the reading, as it stops Say All. (Since 1.26, only when turned on: see issue 23
  below.)
* A link to a mailto: address is "send mail link" where NVDA says "link", while NVDA's "Link type" is checked in its
  Document Formatting settings: NVDA says a field's roleText in the place of its role. Braille shows "lnk" as before.
* Text Word calls a heading is said as a heading when its Word style is a heading style, one whose name has the
  heading's level in it ("Heading 1", "Überschrift 1"). The From line of a quoted message, whose style isn't, is said
  without "heading level 1". The debug log names each style this decides for, once.

The last two are for messages NVDA reads through UI Automation, as it does with a recent Office such as the
tester's.

Then the tester wrote (issue 23, "when I open a message Jaws doesn't automatically read unless I press the arrow keys"):
"When I press enter nothing is spoken with Jaws. I press down arrow hear is what I hear." What issue 20 showed was what
JAWS said line by line, not a Say All: the tester's JAWS reads a message only with the arrow keys, as though its
"Messages automatically read" were off. With 1.25, NVDA read the message from the top as it opened (the log: "an
Outlook message you opened is read from the top", then Say All). And what JAWS said with Down Arrow through a message
with lists had "list of 3 items" before a list's first item and "list end" after its last, where NVDA said only the
bullet and the item. NVDA's UI Automation support for Word gets each list from Word, and says it as no list at all,
"to stay compatible with the older MS Word implementation": its note has the list's start and end said as a bullet is
added with Enter, while writing (NVDAObjects.UIA.wordDocument.WordDocumentTextInfo._getControlFieldForUIAObject).

So now:

* Reading a message from the top when it opens is a setting of its own, off unless it is turned on: where it is off,
  NVDA's browse mode comes into a message as NVDA does, and says nothing more than NVDA says (which Outlook First
  Line Silence, as the tester runs it, keeps quiet, so NVDA says nothing, as JAWS did).
* In a message you read (not one you write), a list is said as NVDA says one on a web page: "list with 3 items" where
  it starts, "out of list" after it, while NVDA's "Lists" is checked in its Document Formatting settings, as it is when
  NVDA comes. The number is the list's items, as UI Automation gives them; without it, NVDA says "list".

Both work while the assistant runs: the first when it is turned on, the rest unless turned off, in NVDA's Settings,
JAWS Migration Assistant.

The tester then found the JAWS setting (issue 23): Insert+V in Outlook, QuickSettings, Reading Options, "Messages
Automatically Read", not checked. It is ``[NonJCFOptions] MessageSayAllVerbosity`` in Outlook.jcf (Outlook.qs), which
JAWS 2026's own Outlook.jcf has on, so a JAWS as it comes reads a message you open, and the tester's own Outlook.jcf
turns it off. A migration now takes it into the first setting, the user's Outlook.jcf over JAWS's own, as JAWS reads it
(settingsMap.mapOutlookSettings), so NVDA reads a message as it opens where JAWS did, and not where it didn't.
"""

from __future__ import annotations

import contextlib
import functools
import re
import threading

#: The assistant's setting (state.json) that turns saying messages as JAWS does on or off: links, lists and headings.
STATE_KEY = "outlookMessagesAsJaws"
#: The assistant's setting (state.json) for reading a message from the top when it opens; off unless turned on.
READ_KEY = "readOutlookMessagesOnOpen"
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
#: What NVDA says with a list where it starts, "with 3 items": the number of its items (speech.getControlFieldSpeech).
ITEM_COUNT = "_childcontrolcount"
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16
#: The most lists whose number of items is kept.
_MOST_COUNTS = 64

#: Whether any part is in place; whether messages are said as JAWS says them; whether one is read when it opens.
_enabled = False
_saying = False
_reading = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: NVDA's OutputReason.CARET, textInfos.UNIT_LINE, Role.LINK, Role.LIST and Role.EDITABLETEXT, once known.
_caret = None
_line = None
_linkRole = None
_listRole = None
_editRole = None
#: (style name, level) pairs the log has noted, so each is noted once; and whether a mail link and a list have been.
_notedStyles: set = set()
_notedMailLink = False
_notedList = False
#: The number of items of each list said in one document, by the list's UI Automation runtime id: NVDA compares a
#: line's fields with the last line's, and a list whose number changed would be left and come into again.
_itemCounts: dict = {}
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
	"""Whether NVDA says an Outlook message as JAWS does (links, lists, headings): on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def readWanted(stateData: dict) -> bool:
	"""Whether NVDA reads an Outlook message from the top when it opens: off unless the user turned it on. The tester's
	JAWS reads a message only with the arrow keys (issue 23)."""
	return isinstance(stateData, dict) and bool(stateData.get(READ_KEY, False))


def register(saying: bool = True, reading: bool = False) -> None:
	"""From now on, have NVDA say Outlook messages as JAWS does when ``saying``, and read one from the top when it opens
	when ``reading``. What is asked for and isn't in place yet is put in place, and what isn't asked for is taken out:
	each part works without the others."""
	global _enabled, _saying, _reading, _caret, _line, _linkRole, _listRole, _editRole
	try:
		import textInfos
		from controlTypes import OutputReason, Role

		_caret, _line, _linkRole = OutputReason.CARET, textInfos.UNIT_LINE, Role.LINK
		# Lists alone need these: without them, the rest still works.
		_listRole, _editRole = getattr(Role, "LIST", None), getattr(Role, "EDITABLETEXT", None)
	except Exception:
		_failure("can't have NVDA read Outlook messages as JAWS does, so NVDA reads them as it does")
		return
	readingInPlace = sayingInPlace = False
	if reading:
		try:
			import browseMode

			with _lock:
				readingInPlace = _replace(browseMode.BrowseModeDocumentTreeInterceptor, GAIN_FOCUS, _gainFocusGuarded)
		except Exception:
			_failure("can't have NVDA read an Outlook message from the top when it opens, so NVDA says its first line")
	else:
		_restore(GAIN_FOCUS)
	if saying:
		try:
			# NVDA loads this with UI Automation, before add-ons, and imports it itself for Word and Outlook.
			from NVDAObjects.UIA.wordDocument import WordDocumentTextInfo

			with _lock:
				sayingInPlace = _replace(WordDocumentTextInfo, CONTROL_FIELD, _controlFieldGuarded)
				sayingInPlace = _replace(WordDocumentTextInfo, FORMAT_AT_RANGE, _formatGuarded) or sayingInPlace
		except Exception:
			_failure("can't change how NVDA says links, lists and headings in Outlook messages, so it says them as it does")
	else:
		_restore(CONTROL_FIELD, FORMAT_AT_RANGE)
	# What was in place from before stays in place, should NVDA's modules be missing this time.
	_reading = reading and (readingInPlace or _reading)
	_saying = saying and (sayingInPlace or _saying)
	_enabled = _reading or _saying


def _restore(*names: str) -> None:
	"""Give NVDA its own ``names`` back, where nothing has been put over the assistant's since; where something has,
	the assistant's does nothing while its part is off."""
	with _lock:
		for entry in list(_replaced):
			owner, name, installed, original = entry
			if name not in names:
				continue
			try:
				if vars(owner).get(name) is installed:
					setattr(owner, name, original)
			except Exception:
				pass
			_replaced.remove(entry)


def unregister() -> None:
	"""Give NVDA its own functions back, where nothing has been put over the assistant's since."""
	global _enabled, _saying, _reading
	_saying = _reading = False
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


def readsOnOpen() -> bool:
	"""Whether NVDA reads an Outlook message from the top when it opens."""
	return _reading


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
		if not _reading or getattr(_local, "opening", False):
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
	"""NVDA's field for an element of a Word document: a link to an e-mail address in Outlook is a "send mail link", and
	a list in a message you read is a list."""

	@functools.wraps(original)
	def _getControlFieldForUIAObject(self, obj, *args, **kwargs):
		global _notedMailLink
		field = original(self, obj, *args, **kwargs)
		if not _saying:
			return field
		try:
			if _listRole is not None and field.get("role") == _editRole and getattr(obj, "role", None) == _listRole:
				sayListAsList(self, obj, field)
				return field
		except Exception:
			_failure("could not tell whether a list in an Outlook message is one you read, so NVDA says it as no list")
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


# -- Lists ------------------------------------------------------------------------------------------------------

#: The document whose lists' numbers of items are kept: they are kept for one document at a time.
_countsFor = None


def isMessageYouRead(textInfo) -> bool:
	"""Whether ``textInfo`` is the text of an Outlook message you read, not one you write: NVDA's Outlook support reads a
	message in browse mode only then (appModules.outlook.OutlookUIAWordDocument.isReadonlyViewer)."""
	document = getattr(textInfo, "obj", None)
	return inOutlook(document) and getattr(document, "isReadonlyViewer", False) is True


def countListItems(listObject):
	"""The number of items of ``listObject``, NVDA's object for a list in Word's text: its children that UI Automation
	calls list items."""
	import UIAHandler

	condition = UIAHandler.handler.clientObject.CreatePropertyCondition(
		UIAHandler.UIA_ControlTypePropertyId,
		UIAHandler.UIA_ListItemControlTypeId,
	)
	items = listObject.UIAElement.FindAll(UIAHandler.TreeScope_Children, condition)
	return int(items.Length) if items is not None else None


def itemCount(textInfo, listObject, field):
	"""The number of items of the list ``field`` is for, as it was the first time it was asked for in this document, or
	None where UI Automation couldn't tell: NVDA compares a line's fields with the last line's, and says a field that
	differs as left and come into again."""
	global _countsFor
	document = id(getattr(textInfo, "obj", None))
	try:
		key = tuple(field.get("runtimeID") or ())
	except TypeError:
		key = ()
	with _lock:
		if _countsFor != document:
			_itemCounts.clear()
			_countsFor = document
		if key and key in _itemCounts:
			return _itemCounts[key]
	try:
		count = countListItems(listObject)
	except Exception:
		_log().debugWarning("jawsMigrator: UI Automation didn't give the number of a list's items, so NVDA says \"list\"", exc_info=True)
		count = None
	if key:
		with _lock:
			if len(_itemCounts) >= _MOST_COUNTS:
				_itemCounts.clear()
			_itemCounts[key] = count
	return count


def sayListAsList(textInfo, listObject, field) -> None:
	"""Have NVDA say ``field``, its field for ``listObject``, a list in the text ``textInfo`` of an Outlook message you
	read, as it says a list on a web page: where it starts ("list with 3 items") and after it ("out of list"). NVDA's own
	made it a read-only edit field, which it doesn't say; it has marked it read only, as NVDA says a list only then."""
	global _notedList
	if not isMessageYouRead(textInfo):
		return
	field["role"] = _listRole
	count = itemCount(textInfo, listObject, field)
	if count:
		field[ITEM_COUNT] = count
	if not _notedList:
		_notedList = True
		_log().debug(
			f"jawsMigrator: a list in an Outlook message ({count} items) is said where it starts and after it, as JAWS says "
			"\"list of 3 items\" and \"list end\", where NVDA said no list in Word's text",
		)


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
		if _saying:
			try:
				leaveOutHeading(self, textRange, formatField)
			except Exception:
				_failure("could not tell whether text in an Outlook message is a heading, so NVDA says it as it does")
		return formatField

	return _getFormatFieldAtRange
