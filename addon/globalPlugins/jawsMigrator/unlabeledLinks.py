# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""A link with no text, in an Outlook message you read, is named as JAWS names it.

A tester (issue 46, "NVDA and unlabeled links in a email") wrote: "Jaws reads unlabeled links properly. It is able to
determine the link. NVDA can't." and attached a promotional message (a candle shop's "Make it Pink" newsletter). Its
HTML holds about thirty links, and twenty of them hold only a picture: ``<a href="https://click.example/?qs=..."><img
alt="Pink Pumpkin Yankee Candle with label and a pink pumpkin beside it on a pink background"></a>``. Six of the pictures
have the alt text "Display images to show real-time content", and two links are to e-mail addresses.

The tester's NVDA log (issue 42, from the same message, opened in classic Outlook 16.0.20326 through UI Automation)
shows what NVDA says as the arrow keys go down the message: "link", "blank", "link", "blank", ... For a link with
text it says "link" and the text ("link, Web Browser"). Word's UI Automation gives NVDA no name and no text for a link
that holds only a picture, and no picture for it to say (Outlook doesn't show the pictures of a message until told to,
so there is a box where each is), so NVDA says "link" and nothing more. NVDA's Elements List has the same hole: its
label for a link is the link's text, or its name, or the word "Unlabeled"
(``browseMode.TextInfoQuickNavItem._getLabelForProperties``).

What JAWS does, from its own settings (Default.JCF, [Options], for a web page's virtual cursor, which is where JAWS
documents it): ``IncludeGraphicLinks=2`` (all graphical links are listed, labeled or not), ``GraphicRenderingOption=1``
(a picture is named by its alt text before its title), ``GraphicalLinkLastResort`` (a graphical link with neither is
named by the picture's source, or by the address it goes to), and ``IncludeEmptyAnchors=1`` (a link with no text and
no picture is kept). So a link with no text is never just "link": the name of its picture, or where it goes.

So, while the assistant runs, in an Outlook message you read, a link with no text is named:

1. By the name Word gives it, when it gives one (NVDA ignores it while the link has text).
2. By the alt text of the picture in the link, or its title, from the message's HTML: the link in the HTML with the
   same address. Outlook's object model gives the HTML (``MailItem.HTMLBody``) of the message shown, as Outlook First Line
   Silence reads it for its own links. NVDA's object model handle for Outlook is ``appModule.nativeOm``.
3. By the alt text or title of the picture in the link, or the link's screen tip, from Word's own object model (the
   Hyperlinks of the message's document), where the HTML has none: the same address, asked of Word, which is also how
   JAWS reads a picture (and how NVDA's own support for Word reads a picture link, ``_getLinkDataAtCaretPosition``).
4. By where it goes, when the message has nothing more: the site of a web address ("click.example.com"), with the last
   part of its path when that is words ("unsubscribe"), or the e-mail address of a ``mailto:`` link.

The name is what NVDA says after "link" (and in front of it for quick navigation and the focus, as it says a link's
text), in the Elements List and the Links List (Insert+F7) in the place of "Unlabeled", and in braille. A link with text
is said as before, and so is a message you write. It works unless "Say Outlook messages as JAWS does" is turned off in
NVDA's Settings, JAWS Migration Assistant.

What the tester's logs of 1.44 and 1.45 showed (issue 42, 2026-09-30; the message is another one of the same shop's, opened
from a .msg file in File Explorer): the lines of the pictures are, in NVDA's text, a link with an empty string in it
(``start EDITABLETEXT, start EDITABLETEXT, start LINK, '', end, end, end``): no picture, no text, so 1.44's way of asking Word's
object model for the picture at the start of a line found no text ("Word's object model has no alternative text for the
picture"). The pictures of that kind of message are remote (``src="https://..."``) and Outlook doesn't show them until told
to, so Word has a box where each is, and the link around it is what NVDA finds. Some lines of a tall picture say "link" and the
next lines "blank": NVDA enters the link once, and the lines after it are the same link. So it is the link that is named,
from the message's own words, and not the line's picture. The names above are for that, and the debug log says what each
step had: how the message's window was found, what the HTML held (its links, those with no text, those that hold a picture
with alt text, and the sites they go to, never an address), what Word's object model held, and what UI Automation gave for
the first link. Where an Outlook gives a window caption as the subject alone, or as the window's title, either is taken.

The code here needs only the standard library, apart from the Outlook object model it asks, so the tests load it
without NVDA.
"""

from __future__ import annotations

import collections
import re
import threading
import time
from html.parser import HTMLParser
from typing import NamedTuple
from urllib.parse import unquote, urlsplit

#: Outlook's olFormatHTML, a message's BodyFormat when it is HTML.
OL_FORMAT_HTML = 2
#: How many messages' links are kept, so that reading a message again asks Outlook for nothing.
_MOST_MESSAGES = 8
#: After Outlook's object model fails, it isn't asked again for this long (seconds).
_RETRY_AFTER = 20.0
#: The most characters of a link's text looked at, to tell whether it has any.
TEXT_LOOKED_AT = 64
#: The longest name said: a longer alt text is cut at a word.
_LONGEST_NAME = 400
#: What Word puts in a range where a picture or a break is, and what shows nothing: the object replacement character,
#: vertical tab, line and paragraph breaks, the end of a table cell, no-break and zero-width spaces, and the byte order mark.
_NOTHING = "\U0000fffc\x0b\r\n\x07\x01\x00\xa0\U0000200b\U0000200c\U0000200d\U00002060\U0000feff\U000000ad"
_WHITESPACE = re.compile(r"\s+")
#: Elements whose text is never shown.
_UNSHOWN = frozenset(("head", "script", "style", "template", "title"))
#: The key of a link's field in which the assistant notes where the link's name came from ("name", "html", "word" or "address").
NAMED_BY = "jawsMigratorNamedBy"
#: The names that are the message's own words: where the picture is said by them, nothing is added from Word's object model.
REAL_NAMES = ("name", "html", "word")
#: The kinds of address that give a name.
_WEB = ("http", "https", "ftp")
#: What a word of a path is: letters, with hyphens and underscores between them ("candle-jars", "unsubscribe").
_WORDS = re.compile(r"^[A-Za-z]{2,}(?:[-_][A-Za-z]{2,})*$")
#: A path's last part is said only when it is this short.
_LONGEST_PATH_WORDS = 40
#: What marks text as an address, and so as no name at all.
_ADDRESS_START = re.compile(r"^(?:https?://|ftp://|mailto:|www\.)", re.IGNORECASE)


def hasText(text) -> bool:
	"""Whether ``text``, the text of a link, shows anything: more than a picture's place, breaks and spaces."""
	if not isinstance(text, str):
		return False
	return any(not (character in _NOTHING or character.isspace()) for character in text)


def cleanLabel(text) -> str:
	"""``text`` as one line, without what shows nothing, and no longer than a name should be."""
	if not isinstance(text, str):
		return ""
	text = _WHITESPACE.sub(" ", "".join(" " if character in _NOTHING else character for character in text)).strip()
	if len(text) > _LONGEST_NAME:
		cut = text.rfind(" ", 0, _LONGEST_NAME)
		text = text[: cut if cut > 0 else _LONGEST_NAME].rstrip(" ,;:-") + "..."
	return text


def isAddress(text) -> bool:
	"""Whether ``text`` is a web or e-mail address, which says nothing of its own."""
	return isinstance(text, str) and bool(_ADDRESS_START.match(text.strip()))


def addressKey(address) -> str:
	"""An address as Word and the HTML may both spell it, to tell which link is which: no spaces around it, no
	percent-escapes, no slash at the end."""
	if not isinstance(address, str):
		return ""
	return unquote(address.strip()).rstrip("/")


# -- The links in a message's HTML ---------------------------------------------------------------------------------


class Anchor(NamedTuple):
	"""A link in a message's HTML: where it goes, the text in it, the alt texts of its pictures, and its title."""

	href: str
	text: str
	alts: tuple
	title: str


class _Anchors(HTMLParser):
	"""Collects the links of an HTML page, in order: their text, and the alt text of the pictures in them."""

	def __init__(self):
		super().__init__(convert_charrefs=True)
		self.found = []
		self._open = None
		self._skipTag = None
		self._skipDepth = 0

	def _finish(self):
		link, self._open = self._open, None
		if link is None:
			return
		self.found.append(Anchor(link["href"], "".join(link["text"]), tuple(link["alts"]), link["title"]))

	def handle_starttag(self, tag, attrs):
		if self._skipTag is not None:
			if tag == self._skipTag:
				self._skipDepth += 1
			return
		attributes = {name: (value or "") for name, value in attrs}
		if tag in _UNSHOWN:
			self._skipTag, self._skipDepth = tag, 1
			return
		if tag == "a":
			# Links don't nest in HTML: a new one ends any link left open.
			self._finish()
			href = attributes.get("href", "").strip()
			if href:
				title = cleanLabel(attributes.get("aria-label") or attributes.get("title"))
				self._open = {"href": href, "text": [], "alts": [], "title": title}
		elif tag == "img" and self._open is not None:
			alt = cleanLabel(attributes.get("alt"))
			if alt and alt not in self._open["alts"]:
				self._open["alts"].append(alt)
			elif not alt and not self._open["title"]:
				self._open["title"] = cleanLabel(attributes.get("title"))

	def handle_startendtag(self, tag, attrs):
		self.handle_starttag(tag, attrs)
		if tag != "a":
			self.handle_endtag(tag)

	def handle_endtag(self, tag):
		if self._skipTag is not None:
			if tag == self._skipTag:
				self._skipDepth -= 1
				if self._skipDepth <= 0:
					self._skipTag = None
			return
		if tag == "a":
			self._finish()

	def handle_data(self, data):
		if self._skipTag is None and self._open is not None:
			self._open["text"].append(data)

	def read(self, html):
		self.feed(html or "")
		self.close()
		self._finish()
		return self


def anchors(html) -> list:
	"""The links of ``html`` in the order they come: a list of ``Anchor``."""
	if not isinstance(html, str):
		return []
	return _Anchors().read(html).found


def labelsByAddress(html) -> dict:
	"""The name the HTML gives each link that has no text: ``{addressKey: name}``, from the alt text of the pictures in
	the link, before its title, as JAWS names a graphical link. The first link to an address that has a name gives it."""
	labels = {}
	for anchor in anchors(html):
		if hasText(anchor.text):
			continue
		key = addressKey(anchor.href)
		if not key or key in labels:
			continue
		label = cleanLabel(" ".join(anchor.alts)) or anchor.title
		if label:
			labels[key] = label
	return labels


# -- Where a link goes ---------------------------------------------------------------------------------------------


def addressLabel(address) -> str | None:
	"""Where a link goes, as words: the site of a web address, and the last part of its path when that is words;
	the e-mail address of a ``mailto:`` link. None for any other address, or none."""
	if not isinstance(address, str):
		return None
	address = address.strip()
	if not address:
		return None
	if address.lower().startswith("mailto:"):
		person = unquote(address[len("mailto:") :].split("?", 1)[0]).strip()
		return person or None
	try:
		parts = urlsplit(address if "://" in address else ("http://" + address if address.lower().startswith("www.") else address))
	except ValueError:
		return None
	if parts.scheme.lower() not in _WEB or not parts.hostname:
		return None
	site = parts.hostname
	if site.lower().startswith("www."):
		site = site[4:]
	last = unquote(parts.path.rstrip("/").rsplit("/", 1)[-1]) if parts.path.strip("/") else ""
	if last and len(last) <= _LONGEST_PATH_WORDS and _WORDS.match(last):
		return f"{site} {last.replace('-', ' ').replace('_', ' ')}"
	return site


def siteOf(address) -> str:
	"""The site of an address, for the debug log: never the rest of it."""
	try:
		return urlsplit(address.strip()).hostname or ""
	except (AttributeError, ValueError):
		return ""


# -- The name -----------------------------------------------------------------------------------------------------


def chooseName(name, htmlName, address) -> tuple:
	"""(name, where it came from) for a link with no text, or (None, None): the name Word gives it, the name the HTML
	gives it, or where it goes, in that order. ``where`` is "name", "html" or "address"."""
	name = cleanLabel(name)
	if name and not isAddress(name):
		return name, "name"
	if htmlName:
		return htmlName, "html"
	where = addressLabel(address) or addressLabel(name)
	if where:
		return where, "address"
	return None, None


# -- Outlook's object model ----------------------------------------------------------------------------------------

_lock = threading.RLock()
#: {message key: {addressKey: name}}, the messages seen last, oldest first.
_messages: collections.OrderedDict = collections.OrderedDict()
#: {key of a Word document's links: {addressKey: name}}: what Word's own object model names, for the messages seen last.
_wordMessages: collections.OrderedDict = collections.OrderedDict()
#: When Outlook's object model may be asked again after it failed (time.monotonic).
_retryAt = 0.0
#: Which kinds of name the debug log has named, what it has said of each message, and Outlook failures it has told of.
_noted: set = set()
_failed = False
#: The most sites the debug log names for the links of a message.
_FACTS_MOST_SITES = 3


def _log():
	from logHandler import log

	return log


def reset() -> None:
	"""Forget every message and what was noted (for the tests, and when the assistant is turned off and on)."""
	global _retryAt, _failed
	with _lock:
		_messages.clear()
		_wordMessages.clear()
		_noted.clear()
		_retryAt = 0.0
		_failed = False


def _failure(what: str, holdOff: bool = True) -> None:
	"""Say in NVDA's log, once, that ``what`` failed. ``holdOff``: Outlook isn't asked again for a while."""
	global _failed, _retryAt
	if holdOff:
		_retryAt = time.monotonic() + _RETRY_AFTER
	if _failed:
		return
	_failed = True
	try:
		_log().debugWarning(f"jawsMigrator: {what}", exc_info=True)
	except Exception:
		pass


def _say(once: str, text) -> None:
	"""Say ``text`` in NVDA's debug log, the first time ``once`` is seen: what happened to the first link of a message,
	so that a tester's log tells where a link's name was lost, and not each of its thirty links' in turn. ``text`` may be
	a function that gives it, which is asked only that first time (it may ask UI Automation things)."""
	with _lock:
		if once in _noted:
			return
		_noted.add(once)
	try:
		_log().debug(f"jawsMigrator: {text() if callable(text) else text}")
	except Exception:
		pass


def _normal(text) -> str:
	"""``text`` as one line in lower case, to tell whether two titles are the same."""
	if not isinstance(text, str):
		return ""
	return _WHITESPACE.sub(" ", text).strip().casefold()


def _outlookWindows(node):
	"""The top window of the message ``node`` is in, and its title."""
	import winUser

	window = winUser.getAncestor(node.windowHandle, winUser.GA_ROOT) or node.windowHandle
	return window, (winUser.getWindowText(window) or "").strip()


def isMainWindow(title: str) -> bool:
	"""Whether ``title`` is the title of Outlook's main window, "Inbox - someone@example.com - Outlook", which has the
	reading pane, and not a message's own window, "Subject - Message (HTML)"."""
	wanted = _normal(title)
	return wanted == "outlook" or wanted.endswith(" - outlook")


def fit(title, caption) -> int:
	"""How well ``caption`` fits ``title``, a message window's title, as a number to compare: 0 for not at all. A window's
	title is the message's subject and its kind, "Subject - Message (HTML)"; Outlook gives an inspector's caption as that
	or as the subject, and the tester's Outlook is not one we have, so both are taken, and the longer caption is the
	better fit ("Re: Sale" is the window of "Re: Sale - Message (HTML)" and not of "Re: Sale on candles")."""
	title, caption = _normal(title), _normal(caption)
	if not title or not caption:
		return 0
	if caption == title:
		return 1_000_000
	if title.startswith(caption + " - "):
		return 1000 + len(caption)
	if caption.startswith(title + " - "):
		return 1000 + len(title)
	return 0


def _best(title, inspectors, describe) -> tuple:
	"""The inspector whose ``describe`` (its caption, or its subject) fits ``title`` best, and how well: (inspector, fit)."""
	found, most = None, 0
	for index in range(1, inspectors.count + 1):
		try:
			inspector = inspectors.item(index)
			score = fit(title, describe(inspector))
		except Exception:
			# One window that can't be asked doesn't hide the others.
			continue
		if score > most:
			found, most = inspector, score
	return found, most


def shownWhy(node) -> tuple:
	"""(the Outlook item shown in the window of the link ``node``, how it was found): the message open in its own window,
	found by its caption or its subject, or the one the message list has selected, which the reading pane shows. (None,
	why not) when it can't be told."""
	nativeOm = getattr(node.appModule, "nativeOm", None)
	if not nativeOm:
		return None, "NVDA has no object model for Outlook (appModule.nativeOm)"
	_window, title = _outlookWindows(node)
	inspectors = nativeOm.inspectors
	found, _score = _best(title, inspectors, lambda inspector: inspector.caption)
	if found is not None:
		return found.currentItem, "the caption of its window"
	found, _score = _best(title, inspectors, lambda inspector: inspector.currentItem.Subject)
	if found is not None:
		return found.currentItem, "the subject of its window"
	if not isMainWindow(title):
		# A message window no caption or subject fits: the one Outlook has in front is the one being read.
		try:
			active = nativeOm.activeInspector()
		except Exception:
			active = None
		if active is not None:
			return active.currentItem, "Outlook's active window"
	explorer = nativeOm.activeExplorer()
	lost = "no open message has a caption or a subject that fits the window's title" if not isMainWindow(title) else "Outlook's main window"
	if not explorer:
		return None, f"{lost}, and Outlook has no main window"
	selection = explorer.selection
	if selection.count != 1:
		return None, f"{lost}, and the message list has {selection.count} messages selected, not one"
	return selection.item(1), "the message selected in the message list"


def shownItem(node):
	"""The Outlook item shown in the window of the link ``node``, or None when it can't be told."""
	return shownWhy(node)[0]


def _messageKey(item) -> str:
	key = getattr(item, "EntryID", "") or ""
	return str(key) or f"{getattr(item, 'Subject', '')}|{getattr(item, 'ReceivedTime', '')}"


def _sitesOf(addresses) -> str:
	"""The sites of ``addresses`` and how many go to each, for the log: never the rest of an address."""
	counts = collections.Counter(siteOf(address) or "no site" for address in addresses)
	shown = ", ".join(f"{site} x{count}" for site, count in counts.most_common(_FACTS_MOST_SITES))
	return shown + (f", and {len(counts) - _FACTS_MOST_SITES} more sites" if len(counts) > _FACTS_MOST_SITES else "")


def _factsOfHtml(found: list, labels: dict) -> str:
	"""What the HTML holds, for the debug log: its links, those with no text, those the HTML names, and where they go."""
	unlabeled = [anchor for anchor in found if not hasText(anchor.text)]
	pictures = [anchor for anchor in unlabeled if anchor.alts]
	named = sum(1 for anchor in unlabeled if addressKey(anchor.href) in labels)
	return (
		f"{len(found)} links, {len(unlabeled)} with no text, {len(pictures)} of those hold a picture with alt text, "
		f"{named} have a name from the HTML (sites: {_sitesOf(anchor.href for anchor in found) or 'none'})"
	)


def messageLabels(node) -> dict:
	"""The names the HTML of the message that has the link ``node`` gives its links without text: ``{addressKey: name}``;
	empty when Outlook can't say or the message isn't HTML. A message is read from Outlook once."""
	if time.monotonic() < _retryAt or threading.current_thread() is not threading.main_thread():
		# Outlook's object model belongs to NVDA's main thread: a question from another thread fails, and is not asked.
		return {}
	try:
		item, how = shownWhy(node)
		if item is None:
			_say("no item", f"a link with no text in an Outlook message can't be named from the message's HTML: {how}")
			return {}
		format_ = getattr(item, "BodyFormat", None)
		if format_ != OL_FORMAT_HTML:
			_say(f"format {format_}", f"a link with no text in an Outlook message can't be named from its HTML: the message is not HTML (its body format is {format_!r})")
			return {}
		key = _messageKey(item)
		with _lock:
			if key in _messages:
				_messages.move_to_end(key)
				return _messages[key]
		html = item.HTMLBody
		found = anchors(html)
		labels = labelsByAddress(html)
	except Exception:
		_failure("can't read the links of an Outlook message from Outlook, so a link with no text is named by where it goes")
		return {}
	with _lock:
		_messages[key] = labels
		while len(_messages) > _MOST_MESSAGES:
			_messages.popitem(last=False)
	_say(
		f"read {key}",
		f"read the HTML of an Outlook message from Outlook (found by {how}): {len(html or '')} characters, "
		f"{_factsOfHtml(found, labels)}",
	)
	return labels


# -- Word's object model -------------------------------------------------------------------------------------------

#: Word's MsoHyperlinkType for a link around a picture, msoHyperlinkInlineShape.
HYPERLINK_INLINE_SHAPE = 2
#: The most links of a message asked of Word.
_MOST_WORD_LINKS = 400


def _textOfShape(shape) -> str:
	"""What JAWS says for a picture (WordFunc.jss, GetInlineShapeAlternativeText): its alternative text, or its title."""
	for name in ("AlternativeText", "Title"):
		try:
			text = cleanLabel(getattr(shape, name))
		except Exception:
			text = ""
		if text:
			return text
	return ""


def _hyperlinksOf(document):
	"""Word's Hyperlinks of the message ``document`` (NVDA's object for the Word document) shows, or None."""
	word = getattr(document, "WinwordDocumentObject", None)
	if not word:
		return None
	return word.Hyperlinks


def wordNames(links) -> tuple:
	"""What Word's own object model names the links of the message whose Hyperlinks are ``links``: ({addressKey: name}, what
	it had, in words for the debug log). A link around a picture is named by the picture's alternative text or title, before
	its screen tip (as NVDA's own support for Word reads a picture link, ``_getLinkDataAtCaretPosition``); the address is
	Word's, which is how the link is found. Asks Word about each link once for the whole message."""
	total = int(links.Count)
	names, pictures, shapes, withText = {}, 0, 0, 0
	for index in range(1, min(total, _MOST_WORD_LINKS) + 1):
		try:
			link = links[index]
			address = link.Address or ""
			name = ""
			if link.Type == HYPERLINK_INLINE_SHAPE:
				pictures += 1
				inline = link.Range.InlineShapes
				if inline.Count:
					shapes += 1
					name = _textOfShape(inline[1])
					withText += 1 if name else 0
			if not name:
				name = cleanLabel(link.ScreenTip)
		except Exception:
			continue
		key = addressKey(address)
		if key and name and key not in names:
			names[key] = name
	facts = (
		f"Word has {total} hyperlinks: {pictures} around a picture, {shapes} of those with the picture in Word's range, "
		f"{withText} with alt text or a title, and {len(names)} with a name"
	)
	return names, facts


def _addressAt(links, index) -> str:
	"""The address of Word's hyperlink number ``index`` of ``links``, or "" when it can't be read."""
	try:
		return addressKey(links[index].Address or "")
	except Exception:
		return ""


def _wordKey(node, links) -> str:
	"""What says which message the hyperlinks ``links`` are of, for what Word's object model said of them: the window's title
	(which is the same for each message of the reading pane), and how many links there are and where the first and the last
	go. A few questions of Word, asked each time, are less than the names of every link."""
	total = int(links.Count)
	ends = [_addressAt(links, index) for index in ((1, total) if total > 1 else (1,) if total else ())]
	return "|".join(["word", _outlookWindows(node)[1], str(total)] + ends)


def wordLabels(node, document) -> dict:
	"""``wordNames`` of the message shown in ``document``, asked of Word once, as {addressKey: name}; {} when it can't be
	asked."""
	if threading.current_thread() is not threading.main_thread():
		return {}
	try:
		links = _hyperlinksOf(document)
		if links is None:
			_say("no word", "a link with no text in an Outlook message can't be named by Word's object model: NVDA has none for this message (WinwordDocumentObject)")
			return {}
		key = _wordKey(node, links)
		with _lock:
			if key in _wordMessages:
				_wordMessages.move_to_end(key)
				return _wordMessages[key]
		names, facts = wordNames(links)
	except Exception:
		_say("word failed", "Word's object model couldn't name the links of an Outlook message, so a link with no text is named by where it goes")
		try:
			_log().debug("jawsMigrator: Word's object model failed:", exc_info=True)
		except Exception:
			pass
		return {}
	with _lock:
		_wordMessages[key] = names
		while len(_wordMessages) > _MOST_MESSAGES:
			_wordMessages.popitem(last=False)
	_say(f"word {key}", f"asked Word's object model for the links of an Outlook message: {facts}")
	return names


def linkText(document, node) -> str | None:
	"""The text of the link ``node`` in ``document``, NVDA's object for the Word document: its first characters, as UI
	Automation gives them. None when it can't be told."""
	try:
		textRange = document.UIATextPattern.rangeFromChild(node.UIAElement)
		return textRange.getText(TEXT_LOOKED_AT)
	except Exception:
		# Outlook is fine: only this link's text couldn't be read, so Outlook is asked for the next.
		_failure("can't read the text of a link in an Outlook message, so NVDA says it as it does", holdOff=False)
		return None


def isUnlabeled(document, node) -> bool:
	"""Whether the link ``node`` has no text to say, which is what NVDA says "link" alone for. A link whose text can't be read
	is left as NVDA has it: Word's link has no name of its own (its text is its content), so no name says nothing."""
	text = linkText(document, node)
	return text is not None and not hasText(text)


def _note(kind: str, site: str) -> None:
	if kind in _noted:
		return
	_noted.add(kind)
	where = {
		"name": "the name Word gives it",
		"html": "the alt text or title of its picture in the message's HTML",
		"word": "the alt text or screen tip Word's object model has for its picture",
		"address": "where it goes",
	}[kind]
	try:
		_log().debug(f"jawsMigrator: a link with no text in an Outlook message is named, as JAWS names one, by {where} (for {site or 'an address'})")
	except Exception:
		pass


_SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")


def schemeOf(address) -> str:
	"""The kind of address ``address`` is ("https", "mailto"), for the debug log: "none" for no address."""
	if not isinstance(address, str) or not address.strip():
		return "none"
	found = _SCHEME.match(address.strip())
	return found.group(1).lower() if found else "no scheme"


def factsOfLink(node, address) -> str:
	"""What UI Automation gives for the link ``node``, for the debug log: how long its value (the address, which is how the
	link is found in the HTML), name, description and help are, and its class and automation id. Never the text of any."""

	def asked(name):
		try:
			value = getattr(node, name, None)
		except Exception:
			return "can't be read"
		return f"{len(value)} characters" if isinstance(value, str) and value else "empty"

	element = getattr(node, "UIAElement", None)
	try:
		className = getattr(element, "cachedClassName", None)
	except Exception:
		className = None
	try:
		automationId = getattr(node, "UIAAutomationId", None)
	except Exception:
		automationId = None
	return (
		f"its value is {asked('value')} ({schemeOf(address)}), its name {asked('name')}, its description {asked('description')}, "
		f"its help {asked('helpText')}; UI Automation's class {className!r} and automation id {automationId!r}"
	)


def nameWhere(node, address, document=None) -> tuple:
	"""(the name for the link ``node`` (whose address is ``address``) when it has no text, where it came from), or (None,
	None): "name", "html", "word" or "address". Asks Outlook for the message's HTML only when Word gives the link no name,
	and Word's own object model (of ``document``, NVDA's object for the Word document) only when the HTML has none either."""
	name = cleanLabel(getattr(node, "name", ""))
	htmlName = wordName = None
	site = siteOf(address if isinstance(address, str) else "")
	if not name or isAddress(name):
		_say("link facts", lambda: f"the first link with no text of an Outlook message: {factsOfLink(node, address)}")
		key = addressKey(address)
		htmlName = messageLabels(node).get(key)
		if not htmlName and document is not None:
			wordName = wordLabels(node, document).get(key)
		if not htmlName and not wordName:
			_say(f"missed {site}", f"no name for a link with no text in an Outlook message was found in its HTML or in Word's object model (the link is {'to ' + site if site else 'to an address the assistant has no site for (' + schemeOf(address) + ')'})")
	chosen, where = chooseName(name, htmlName or wordName, address)
	if chosen and where == "html" and not htmlName:
		# chooseName calls the HTML's name "html": this one was Word's.
		where = "word"
	if chosen:
		_note(where, site)
	return chosen, where


def nameOf(node, address, document=None) -> str | None:
	"""The name for the link ``node`` when it has no text (``nameWhere``), or None."""
	return nameWhere(node, address, document)[0]
