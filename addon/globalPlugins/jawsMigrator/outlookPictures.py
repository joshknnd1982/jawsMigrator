# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""In an Outlook message, a picture is said with its alternative text, as JAWS says it.

A tester read a marketing e-mail in classic Outlook (issue 42, "Jaws reads an email better then NVDA"): "Jaws will read
some titles for the email. NVDA will read nothing." Their NVDA log (2026-09-29 08.51) has the message open, and Down
Arrow through it says, line after line:

    Speaking ['link', 'Web Browser']
    Speaking ['blank']
    Speaking ['link']
    Speaking ['blank']
    Speaking ['link']
    ... (and so on, 'link' or 'blank' for each picture, until) 'link', 'Update My Email Preferences', '| ',
    'link', 'Unsubscribe'

The words are said; the pictures are not. The Outlook First Line Silence add-on the tester runs, which steps through a
message by its links, says of each of those lines that it has no text ("Outlook First Line Silence links: blank line"):
an inline picture has no text in Word's UI Automation, so a line that holds only pictures is "blank", and a line whose
picture is a link is "link". The e-mail is pictures: its headline, its offer and its buttons are all pictures inside
links, each with the alternative text its sender wrote.

Outlook's messages are Word documents, and with a recent Office such as the tester's 16.0.20326 NVDA reads Word through
UI Automation (``UIAHandler.shouldUseUIAInMSWord``, "Using UIA due to suitable Office version" in the log). Word's UI
Automation doesn't give a picture's alternative text for an e-mail's pictures: NVDA says "graphic" with nothing after it
for a picture in a message (NVDA's issue 14217, "Alt text not announced in Outlook win32 emails", where turning UI
Automation for Word off made NVDA read it), and says only "link" for a picture inside a link (NVDA's issue 18177, "NVDA
fails to read alt or aria-label for linked images in Outlook Classic HTML emails", still open). JAWS reads Word through
its object model: it says a picture's ``AlternativeText`` (WordFunc.jss, SayInlineShape and
GetInlineShapeAlternativeText, ``selection.characters.first.inlineShapes(1)``).

So in an Outlook message, when NVDA has a line of pictures with nothing to say for them, the assistant asks Word's object
model, which NVDA reaches the same way for a range's location (``NVDAObjects.UIA.wordDocument.WordDocumentTextInfo``,
``_get_locationText``: the range's point on the screen, then ``rangeFromPoint``), for the picture at the start of the
line, and gives NVDA's text of the line a graphic with that text as its content, as NVDA does for a graphic whose text
Word does tell it (``_getControlFieldForUIAObject``: ``field["content"]``). NVDA then says "graphic" and the text, inside
the link where there is one: "link, graphic, Make it Pink". A picture NVDA already says the text of is left as it is,
and so is a line with words in it. The alternative text comes before the picture's title, and, for a picture inside a
link, the link's own screen tip is the last to be tried. Where Word has no text for the picture either, NVDA says what
it said before.

What it asks of Word's object model is one range from a point, and up to three short questions about it, for a line
with no text in it; NVDA's own support asks the same of Word for a range's location. If an answer fails three times in a
row, it isn't asked again until NVDA restarts, and the log says so. What Word answered, or that it had nothing, is
noted in NVDA's log, so a tester's log says what happened.

Not tried with classic Outlook: it isn't installed on the computer this was made on. The tests run NVDA 2026.2's own
speech code against the tester's lines, and imitate what Word's object model answers.

The tester's logs of 1.44 and 1.45 (issue 42) show that for the candle shop's message this isn't what is missing: the lines of
its pictures are a link with an empty string in it, and Word's object model had no text at the start of the line ("Word's
object model has no alternative text for the picture at the start of this line of an Outlook message (NVDA's fields: start
EDITABLETEXT, start EDITABLETEXT, start LINK, '', end, end, end)"), for line after line. The pictures of a message like that
are remote ones Outlook doesn't show until told to. The link is what NVDA finds, and unlabeledLinks (1.49) names it from the
message's own words, so a link it has named (``unlabeledLinks.NAMED_BY``) is not asked of Word's object model again. This is
still for a picture NVDA finds with no text, in a link or not; and when Word answers with nothing, the log says what was asked
and what Word held (the point, its range, how many pictures and links, how long their texts are) and not only that it had none.

Since 1.53 (issue 40, "very slow": each line of pictures asked Word a dozen questions, and in the tester's Outlook each took
35 milliseconds) Word is asked about the pictures of a message until one answer takes more than a third of a second, and not
after that while the message has the focus; see outlookLookups.
"""

from __future__ import annotations

import functools
import threading

from . import outlookLookups as lookups

#: The assistant's setting (state.json) that turns this on or off.
STATE_KEY = "outlookPictureText"
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's own version, so another add-on's wrapper around it is recognized.
MARK = "_jawsMigratorOutlookPictures"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: The name NVDA gives classic Outlook's app module.
APP_NAME = "outlook"
#: NVDA's text of a Word document read through UI Automation, and the method that gives its text and formatting.
TEXT_INFO = "WordDocumentTextInfo"
METHOD = "getTextWithFields"
#: Word's units for Range.Expand and Range.MoveStart: wdCharacter.
WD_CHARACTER = 1
#: What Word's UI Automation puts in the text of a picture, or around one: none of these is a word.
NOT_WORDS = "\ufffc\u200b\u200c\u200d\ufeff\xa0 \t\r\n\v\f\0"
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16
#: How many times in a row Word's object model may fail before it isn't asked again.
_MOST_FAILURES = 3
#: How many times the log says each thing it has to say: what Word answered, and what it had nothing for. (What it had nothing for
#: asks Word a dozen more questions, for the log alone.)
_MOST_NOTES = 3

_enabled = False
_failed = False
_lock = threading.RLock()
#: What the assistant put in the place of NVDA's own: [(owner, attribute name, the assistant's, NVDA's)].
_replaced: list = []
#: NVDA's textInfos.FieldCommand and textInfos.ControlField, and controlTypes.Role.GRAPHIC and LINK, once known.
_fieldCommand = None
_controlField = None
_graphicRole = None
_linkRole = None
#: How many times in a row Word's object model has failed, and whether it is left alone since.
_failures = 0
_suspended = False
#: How many times each thing has been noted in the log.
_noted: dict = {}


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


def _note(kind: str, text) -> None:
	"""Say ``text`` in NVDA's log, for the first few times ``kind`` happens. ``text`` may be a function that gives it, asked
	only when it is said (it may ask Word's object model things)."""
	count = _noted.get(kind, 0)
	if count >= _MOST_NOTES:
		return
	_noted[kind] = count + 1
	try:
		_log().debug(f"jawsMigrator: {text() if callable(text) else text}")
	except Exception:
		pass


def wanted(stateData: dict) -> bool:
	"""Whether NVDA says the alternative text of a picture in an Outlook message: on unless the user turned it off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


def register() -> None:
	"""Have NVDA say the alternative text of a picture in an Outlook message, from now on."""
	global _enabled, _fieldCommand, _controlField, _graphicRole, _linkRole, _failures, _suspended
	if _enabled:
		return
	try:
		import textInfos
		from controlTypes import Role

		# NVDA loads this with UI Automation, before add-ons, and imports it itself for Word and Outlook.
		from NVDAObjects.UIA.wordDocument import WordDocumentTextInfo

		_fieldCommand, _controlField, _graphicRole = textInfos.FieldCommand, textInfos.ControlField, Role.GRAPHIC
		_linkRole = getattr(Role, "LINK", None)
		with _lock:
			if not _replace(WordDocumentTextInfo):
				return
	except Exception:
		_failure("can't have NVDA say the alternative text of a picture in an Outlook message, so NVDA says what it does")
		return
	_failures, _suspended = 0, False
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
		_failure(f"NVDA has no {TEXT_INFO}.{METHOD} the assistant knows, so NVDA says no alternative text for pictures in Outlook")
		return False
	installed = _guarded(current)
	setattr(owner, METHOD, installed)
	_replaced.append((owner, METHOD, installed, current))
	_log().debug(f"jawsMigrator: NVDA says the alternative text of a picture in an Outlook message ({owner.__name__}.{METHOD})")
	return True


def _mark(installed, original):
	setattr(installed, MARK, _TOKEN)
	setattr(installed, ORIGINAL, original)
	return installed


def inOutlook(info) -> bool:
	"""Whether ``info``, NVDA's text of a Word document, is in classic Outlook: a message you write or read."""
	appModule = getattr(getattr(info, "obj", None), "appModule", None)
	return getattr(appModule, "appName", None) == APP_NAME


# -- The fields of a line --------------------------------------------------------------------------------------------


def _isCommand(item, command: str) -> bool:
	return isinstance(item, _fieldCommand) and item.command == command


def hasWords(fields) -> bool:
	"""Whether ``fields``, NVDA's text with its fields, has a word in it: text that is more than what Word puts where
	there is a picture, a space or the end of a paragraph."""
	return any(isinstance(item, str) and item.strip(NOT_WORDS) for item in fields)


def hasPictureCharacter(fields) -> bool:
	"""Whether the text of ``fields`` holds the object replacement character Word puts where a picture is, or none at
	all: a line of pictures, not an empty paragraph, which has its paragraph mark."""
	text = "".join(item for item in fields if isinstance(item, str))
	return not text or "\ufffc" in text


def pictureFields(fields) -> list:
	"""The control fields in ``fields`` for a picture: what NVDA's UI Automation support for Word makes of Word's
	pictures, with the text it has for each as ``content``."""
	return [
		item.field
		for item in fields
		if _isCommand(item, "controlStart") and isinstance(item.field, _controlField) and item.field.get("role") == _graphicRole
	]


def _startsEnd(fields) -> tuple[int, int]:
	"""Where the control fields at the start of ``fields`` end, and where those at its end begin: the places a picture
	goes in, between the fields around a line and its text."""
	start = 0
	while start < len(fields) and _isCommand(fields[start], "controlStart"):
		start += 1
	end = len(fields)
	while end > start and _isCommand(fields[end - 1], "controlEnd"):
		end -= 1
	return start, end


def pictureField(text: str, identity) -> object:
	"""A control field for a picture with ``text``, as NVDA's UI Automation support for Word makes one for a picture
	whose text Word does tell it: a graphic, with the text as its content."""
	field = _controlField()
	field["runtimeID"] = identity
	field["_startOfNode"] = field["_endOfNode"] = True
	field["role"] = _graphicRole
	field["states"] = set()
	field["nameIsContent"] = True
	field["description"] = ""
	field["level"] = None
	field["content"] = text
	return field


def withPicture(fields: list, text: str, identity) -> list:
	"""``fields`` with a graphic, its content ``text``, around the line's text: inside the control fields that start the
	line, such as the link around a picture, and before those that end it. Changes ``fields``, and gives it back."""
	start, end = _startsEnd(fields)
	field = pictureField(text, identity)
	fields.insert(end, _fieldCommand("controlEnd", None))
	fields.insert(start, _fieldCommand("controlStart", field))
	return fields


def linkSaysIt(fields, text: str) -> bool:
	"""Whether a link in ``fields`` has ``text`` in the content NVDA says for it: another part of the assistant, or an
	add-on, has named the link already, as it would be said twice."""
	wanted = _clean(text).casefold()
	for item in fields:
		if _isCommand(item, "controlStart") and _linkRole is not None and item.field.get("role") == _linkRole:
			content = item.field.get("content")
			if content and wanted in _clean(content).casefold():
				return True
	return False


def fillPictures(fields: list, text: str) -> int:
	"""Give each picture in ``fields`` that has no text the text Word's object model gave. Gives the number."""
	count = 0
	for field in pictureFields(fields):
		if not field.get("content"):
			field["content"] = text
			count += 1
	return count


# -- What Word's object model has for the picture ----------------------------------------------------------------------


def _clean(text) -> str:
	"""A text Word gave, as one line of words."""
	if not isinstance(text, str):
		return ""
	return " ".join(text.split()).strip(NOT_WORDS)


def _textOf(shape) -> str:
	"""What JAWS says for a picture: its alternative text (WordFunc.jss, GetInlineShapeAlternativeText); its title if it
	has no alternative text."""
	for name in ("AlternativeText", "Title"):
		try:
			text = _clean(getattr(shape, name))
		except Exception:
			text = ""
		if text:
			return text
	return ""


def _pictureIn(candidate):
	"""The first picture in Word's range ``candidate``, as (text, where it is in the document), or None."""
	shapes = candidate.InlineShapes
	if not shapes.count:
		return None
	shape = shapes[1]
	try:
		where = int(shape.Range.Start)
	except Exception:
		where = None
	return _textOf(shape), where


def _screenTipOf(candidate) -> str:
	"""The screen tip of the link around Word's range ``candidate``, if it has one."""
	try:
		links = candidate.Hyperlinks
		if links.count:
			return _clean(links[1].ScreenTip)
	except Exception:
		pass
	return ""


class _TooSlow(Exception):
	"""Word's object model took longer to answer than ``lookups.SLOW_ASK`` allows."""


def _ask(info, watch=None):
	"""What Word's object model has for the picture at the start of ``info``, NVDA's text of a line, as (text, where, asked),
	with text "" when Word has none, or None when it couldn't be asked. ``asked`` is what was asked of Word, for the log: the
	point on the screen, and the ranges of Word's document looked at. ``watch`` is the time since asking began: when the
	point's range took longer than ``lookups.SLOW_ASK`` to come, the rest isn't asked (``_TooSlow``)."""
	window = info.obj.WinwordWindowObject
	if not window:
		return None
	try:
		point = info.pointAtStart
	except LookupError:
		# Off the screen: NVDA scrolls a range into view before it moves the caret there, as it is about to.
		info._ensureRangeVisibility()
		point = info.pointAtStart
	# A pixel inside the line's corner, as the point of a picture's edge could be the next character's.
	where = window.rangeFromPoint(int(point.x) + 1, int(point.y) + 1)
	if watch is not None and watch.took() > lookups.SLOW_ASK:
		raise _TooSlow
	candidates = []
	# The point is on the picture, or just after it.
	for shift in (0, -1):
		candidate = where.duplicate
		if shift:
			candidate.moveStart(WD_CHARACTER, shift)
		else:
			candidate.expand(WD_CHARACTER)
		candidates.append(candidate)
	asked = (point, where, candidates)
	found = None
	for candidate in candidates:
		found = _pictureIn(candidate)
		if found and found[0]:
			return found + (asked,)
		if found:
			break
	# The picture has no text of its own: the link around it may have a screen tip.
	for candidate in candidates:
		tip = _screenTipOf(candidate)
		if tip:
			return tip, found[1] if found else None, asked
	return "", found[1] if found else None, asked


def _count(collection) -> str:
	try:
		return str(int(collection.count))
	except Exception:
		return "?"


def _textLength(shape, name: str) -> str:
	try:
		return str(len(_clean(getattr(shape, name))))
	except Exception:
		return "?"


def _rangeFacts(candidate) -> str:
	"""What Word's range ``candidate`` holds, for the log: where it is, its pictures (their kind, and how long the alternative
	text and the title of the first are) and its links. Never the text itself."""
	parts = []
	for name in ("Start", "End"):
		try:
			parts.append(str(int(getattr(candidate, name))))
		except Exception:
			parts.append("?")
	text = f"range {parts[0]}-{parts[1]}"
	try:
		shapes = candidate.InlineShapes
		text += f": {_count(shapes)} pictures"
		if int(shapes.count):
			shape = shapes[1]
			kind = getattr(shape, "Type", "?")
			text += f" (the first of kind {kind}, alt text {_textLength(shape, 'AlternativeText')} characters, title {_textLength(shape, 'Title')})"
	except Exception:
		text += ": pictures can't be read"
	try:
		text += f", {_count(candidate.Hyperlinks)} links"
	except Exception:
		text += ", links can't be read"
	return text


def _asking(asked) -> str:
	"""What was asked of Word, in words for the log. (None where Word was slow to answer: what it held is not asked for the log
	too, which is a dozen questions more.)"""
	if asked is None:
		return "Word was slow to answer, so what it held is not described"
	point, where, candidates = asked
	try:
		place = f"the point {int(point.x)},{int(point.y)} of the screen"
	except Exception:
		place = "the start of the line"
	return f"asked at {place}; Word's range there is {_rangeFacts(where)}; looked at {'; '.join(_rangeFacts(candidate) for candidate in candidates)}"


def _readingOf(info):
	"""What the assistant has learned of the message ``info`` is in (``outlookLookups.reading``), or None."""
	try:
		return lookups.reading(info.obj)
	except Exception:
		return None


def _slow(reading, watch, answered: bool) -> None:
	"""Word took long over a picture: it isn't asked about the pictures of this message again (until the message takes the
	focus again), so a message that keeps Outlook busy doesn't keep NVDA waiting for each line of it (issue 40)."""
	if reading is not None:
		reading.picturesOff = True
	_note(
		"slow",
		f"Word's object model took {watch.took():.2f} seconds to answer about a picture in an Outlook message"
		f"{'' if answered else ' and was not asked more'} (more than {lookups.SLOW_ASK} seconds), so it isn't asked about the pictures "
		"of this message again, and a picture is said as NVDA says it",
	)


def _asked(info):
	"""``_ask``, counting how often Word's object model fails: (text, where), or None. Not asked again about a message whose
	pictures Word was slow to answer for."""
	global _failures, _suspended
	if _suspended or threading.current_thread() is not threading.main_thread():
		return None
	reading = _readingOf(info)
	if reading is not None and reading.picturesOff:
		return None
	watch = lookups.Deadline(0)
	try:
		answer = _ask(info, watch)
	except LookupError:
		return None
	except _TooSlow:
		_slow(reading, watch, answered=False)
		return None
	except Exception:
		_failures += 1
		_note("failed", f"Word's object model couldn't give the picture in an Outlook message its text ({_failures} in a row)")
		if _failures >= _MOST_FAILURES:
			_suspended = True
			_note("suspended", "Word's object model failed again and again, so NVDA doesn't ask it for pictures' text until it restarts")
		return None
	_failures = 0
	if watch.took() > lookups.SLOW_ASK:
		# It answered, and the answer is used; the next line's picture is not asked.
		_slow(reading, watch, answered=True)
		if answer is not None:
			answer = answer[:2] + (None,)
	return answer


def namedFromTheMessage(fields) -> bool:
	"""Whether a link in ``fields`` has been given a name from the message itself (unlabeledLinks: the name Word gives it, the
	picture's alt text or title in the message's HTML, or Word's own): the picture says nothing more than that."""
	from . import unlabeledLinks

	return any(
		_isCommand(item, "controlStart") and item.field.get(unlabeledLinks.NAMED_BY) in unlabeledLinks.REAL_NAMES
		for item in fields
	)


def addPictureText(info, fields) -> list:
	"""``fields``, NVDA's text of ``info``, a range of an Outlook message, with the alternative text of the picture in it
	where NVDA has none to say. Changes ``fields``, and gives it back."""
	if not fields or getattr(info, "isCollapsed", False) or hasWords(fields):
		return fields
	pictures = pictureFields(fields)
	if any(field.get("content") for field in pictures):
		# Word told NVDA what the picture is.
		return fields
	if not pictures and not hasPictureCharacter(fields):
		# An empty paragraph, not a picture.
		return fields
	if namedFromTheMessage(fields):
		# The link around the picture has its name from the message, which Word's object model can't improve on.
		return fields
	answer = _asked(info)
	if answer is None:
		return fields
	text, where, asked = answer
	if not text:
		_note("empty", lambda: f"Word's object model has no alternative text for the picture at the start of this line of an Outlook message (NVDA's fields: {_describe(fields)}; {_asking(asked)})")
		return fields
	if linkSaysIt(fields, text):
		_note("named", f"the link around a picture in an Outlook message is said with its name already, which has the picture's text: {text!r}")
		return fields
	if pictures:
		fillPictures(fields, text)
	else:
		withPicture(fields, text, ("jawsMigrator", where if where is not None else text))
	_note("said", f"the alternative text of a picture in an Outlook message, said as JAWS says it: {text!r}")
	return fields


def _describe(fields) -> str:
	"""What ``fields`` has in it, for the log: the roles of its control fields, and its text."""
	parts = []
	for item in fields:
		if _isCommand(item, "controlStart"):
			role = getattr(item.field.get("role"), "name", item.field.get("role"))
			parts.append(f"start {role}")
		elif _isCommand(item, "controlEnd"):
			parts.append("end")
		elif isinstance(item, str):
			parts.append(repr(item))
	return ", ".join(parts)


def _guarded(original):
	"""NVDA's WordDocumentTextInfo.getTextWithFields: in Outlook, with the alternative text of its pictures."""

	@functools.wraps(original)
	def getTextWithFields(self, *args, **kwargs):
		fields = original(self, *args, **kwargs)
		if _enabled:
			try:
				if inOutlook(self):
					fields = addPictureText(self, fields)
			except Exception:
				_failure("could not say the alternative text of a picture in an Outlook message, so NVDA says what it does")
		return fields

	return _mark(getTextWithFields, original)
