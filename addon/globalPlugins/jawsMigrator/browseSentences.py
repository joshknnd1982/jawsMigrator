# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""JAWS's Say Next Sentence and Say Prior Sentence read by sentence on web pages, as JAWS's virtual cursor does.

A tester pressed NVDA+N twice on a GitHub page in Edge (issue 32), and NVDA said nothing. Each time NVDA's log had an
error: NotImplementedError, from NVDA's own command for the next sentence. The tester's migration had "When NVDA
already uses a keystroke for something else, use the JAWS command instead" checked, so JAWS's Laptop layout keystroke
Caps Lock+N, Say Next Sentence, took NVDA+N (in browse mode) for NVDA's command that moves to the next sentence, and
Caps Lock+Y, Say Prior Sentence, took NVDA+Y. In the Desktop layout they are Alt+NumPadPlus and Alt+NumPadMinus
(Default.jkm, [Common Keys]).

JAWS reads "by word, line, sentence, or paragraph" in its virtual cursor, in Edge, Chrome, Firefox, Adobe Acrobat Reader
and Outlook's messages (JAWS's help, Using the Virtual Cursor). NVDA 2026.2 moves by sentence only in a document that
knows its sentences, such as Word's (cursorManager.CursorManager.script_moveBySentence_forward and _back, through
_caretMovementScriptHelper). A web page or a PDF in browse mode is NVDA's virtual buffer, which has no sentences
(textInfos.offsets.OffsetsTextInfo._getSentenceOffsets raises NotImplementedError), so the command failed before it
moved or said anything. NVDA's own keys for it (Alt+Up and Alt+Down) open and close a combo box in browse mode
instead, so NVDA users never meet it there.

So in a browse mode document without sentences, the assistant finds them itself: a sentence ends at ".", "!" or "?"
(or an ellipsis), with any closing quotes or brackets after it, before a space or the end of the paragraph, and a
paragraph (a block of the page, links in it included) always ends one. Say Next Sentence moves browse mode's caret to
the start of the sentence after the one it is in, going on to the next paragraph with text, and says it as NVDA says a
sentence it moves to; Say Prior Sentence moves to the sentence before the one it is in. Where there is none, the caret
stays and the sentence it is in is said again, as NVDA's own command does at the start or end of a document. Where
NVDA held back a page's first line as the page opened (see browserPages), Say Next Sentence says the first sentence,
as JAWS, whose cursor starts on the page's title, goes from the title to it. A document with sentences of its own, and
every other key, are as NVDA has them. It works while the assistant runs.
"""

from __future__ import annotations

import functools
import re
import threading

#: NVDA's commands for the next and the prior sentence (cursorManager.CursorManager), which JAWS's SayNextSentence and
#: SayPriorSentence become (jawsKeyMap), with the way each goes.
SCRIPTS = {"script_moveBySentence_forward": 1, "script_moveBySentence_back": -1}
#: Marks what the assistant put in the place of NVDA's own, and keeps NVDA's.
ORIGINAL = "_jawsMigratorOriginal"
#: Marks the assistant's versions, so another add-on's wrapper around one is recognized.
MARK = "_jawsMigratorBrowseSentences"
#: What the mark holds: this copy of the module, as NVDA loads the add-on again when it reloads its plugins.
_TOKEN = object()
#: No function is wrapped deeper than this.
_MOST_WRAPPERS = 16
#: How many paragraphs without text are passed over looking for the next or prior sentence, at most.
MOST_PARAGRAPHS = 500
#: Where a sentence ends: ".", "!" or "?", or an ellipsis (and the full stops of Chinese and Japanese), with any closing
#: quotes or brackets after them, before a space or the end of the text.
SENTENCE_END = re.compile("[.!?…。！？]+[\"'’”)\\]}»]*(?=\\s|$)")

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
	"""Have NVDA's commands for the next and prior sentence read by sentence in browse mode documents without
	sentences, from now on."""
	global _enabled
	with _lock:
		if _enabled:
			return
		try:
			import cursorManager

			owner = cursorManager.CursorManager
		except Exception:
			_failure("can't find NVDA's commands for the next and prior sentence, so they are as NVDA has them")
			return
		for name, step in SCRIPTS.items():
			current = vars(owner).get(name)
			if _isOurs(current):
				continue
			if not callable(current):
				_debug(f"jawsMigrator: NVDA has no CursorManager.{name}, so it is as before")
				continue
			installed = _guarded(current, step)
			setattr(owner, name, installed)
			_replaced.append((owner, name, installed, current))
		_debug("jawsMigrator: JAWS's Say Next Sentence and Say Prior Sentence read by sentence on web pages, where NVDA has no sentences (CursorManager.script_moveBySentence_forward, _back)")
		_enabled = True


def unregister() -> None:
	"""Give NVDA its own commands back, where nothing has been put over the assistant's since."""
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


def _guarded(original, step: int):
	"""NVDA's command for the next (``step`` 1) or prior (-1) sentence: the assistant's in a browse mode document without
	sentences, NVDA's own anywhere else."""

	@functools.wraps(original)
	def script(self, gesture, *args, **kwargs):
		if not _enabled or args or kwargs:
			return original(self, gesture, *args, **kwargs)
		try:
			own = hasSentences(self)
		except Exception:
			own = True
		if own:
			return original(self, gesture)
		try:
			moveBySentence(self, gesture, step)
		except Exception:
			_failure("could not move by sentence in a document without sentences, so the key did nothing")
		return None

	setattr(script, MARK, _TOKEN)
	setattr(script, ORIGINAL, original)
	return script


def hasSentences(document) -> bool:
	"""Whether ``document`` knows its own sentences, as Word's does; a web page or PDF in browse mode doesn't."""
	import textInfos

	info = document.makeTextInfo(textInfos.POSITION_CARET)
	try:
		info.expand(textInfos.UNIT_SENTENCE)
	except NotImplementedError:
		return False
	return True


# -- sentences in a paragraph's text ------------------------------------------------------------------------------


def _textAfter(text: str, index: int) -> int | None:
	"""Where the first character after ``index`` that isn't a space is, or None."""
	while index < len(text):
		if not text[index].isspace():
			return index
		index += 1
	return None


def sentenceStarts(text: str) -> list[int]:
	"""Where each sentence in a paragraph's ``text`` starts, in order."""
	starts = []
	first = _textAfter(text, 0)
	if first is None:
		return starts
	starts.append(first)
	for match in SENTENCE_END.finditer(text):
		start = _textAfter(text, match.end())
		if start is not None and start > starts[-1]:
			starts.append(start)
	return starts


def sentenceEnd(text: str, starts: list[int], start: int) -> int:
	"""Where the sentence of a paragraph's ``text`` that starts at ``start`` ends, without the spaces after it."""
	later = [index for index in starts if index > start]
	end = later[0] if later else len(text)
	return start + len(text[start:end].rstrip())


# -- paragraphs ---------------------------------------------------------------------------------------------------


def _offsetIn(paragraph, point) -> int:
	"""How many characters of ``paragraph``'s text come before ``point``, a collapsed position in it."""
	before = paragraph.copy()
	before.setEndPoint(point, "endToStart")
	return len(before.text)


def _nextParagraph(paragraph, step: int) -> bool:
	"""Move ``paragraph`` to the paragraph after it (``step`` 1) or before it (-1), as NVDA's browse mode moves by
	paragraph for its text paragraph quick navigation (browseMode.BrowseModeDocumentTreeInterceptor._moveToNextParagraph).
	False at the end or start of the document."""
	import textInfos

	old = paragraph.copy()
	if step > 0:
		paragraph.collapse(end=True)
	else:
		paragraph.collapse()
		if paragraph.move(textInfos.UNIT_CHARACTER, -1) == 0:
			return False
	paragraph.expand(textInfos.UNIT_PARAGRAPH)
	if paragraph.isCollapsed:
		return False
	if step > 0 and paragraph.compareEndPoints(old, "startToStart") <= 0:
		return False
	return True


def _sentence(paragraph, start: int, end: int):
	"""The sentence of ``paragraph`` from ``start`` to ``end`` (characters of its text), as a range of the document."""
	sentence = paragraph.moveToCodepointOffset(start)
	sentence.setEndPoint(paragraph.moveToCodepointOffset(end), "endToEnd")
	return sentence


def findSentence(caret, step: int, fromFirstLine: bool = False):
	"""The sentence after (``step`` 1) or before (-1) the one ``caret`` is in, and whether it is another sentence (False:
	there is none, and it is the one the caret is in). None where the document has no text there.

	With ``fromFirstLine``, the caret is on a first line NVDA hasn't said, and the next sentence is the one the caret is at.
	"""
	import textInfos

	paragraph = caret.copy()
	paragraph.expand(textInfos.UNIT_PARAGRAPH)
	text = paragraph.text
	position = _offsetIn(paragraph, caret)
	starts = sentenceStarts(text)
	current = [start for start in starts if start <= position]
	if step > 0:
		ahead = [start for start in starts if start >= position] if fromFirstLine else [start for start in starts if start > position]
		if ahead:
			return _sentence(paragraph, ahead[0], sentenceEnd(text, starts, ahead[0])), True
	elif len(current) > 1:
		start = current[-2]
		return _sentence(paragraph, start, sentenceEnd(text, starts, start)), True
	# On to the paragraphs after or before, past those without text.
	other = paragraph.copy()
	for _ in range(MOST_PARAGRAPHS):
		if not _nextParagraph(other, step):
			break
		otherText = other.text
		otherStarts = sentenceStarts(otherText)
		if otherStarts:
			start = otherStarts[0] if step > 0 else otherStarts[-1]
			return _sentence(other, start, sentenceEnd(otherText, otherStarts, start)), True
	# None: the sentence the caret is in, as NVDA's own says it again at the start or end of a document.
	if current:
		start = current[-1]
	elif starts:
		start = starts[0]
	else:
		return None, False
	return _sentence(paragraph, start, sentenceEnd(text, starts, start)), False


def moveBySentence(document, gesture, step: int) -> None:
	"""Move browse mode's caret in ``document`` to the next (``step`` 1) or prior (-1) sentence and say it, as NVDA's
	_caretMovementScriptHelper does in a document with sentences."""
	import speech
	import textInfos
	from controlTypes import OutputReason
	from scriptHandler import isScriptWaiting, willSayAllResume

	if isScriptWaiting():
		# As NVDA's own: with more keys waiting, nothing is said or moved.
		return
	oldInfo = document.makeTextInfo(textInfos.POSITION_SELECTION)
	caret = oldInfo.copy()
	caret.collapse(end=document.isTextSelectionAnchoredAtStart)
	if document.isTextSelectionAnchoredAtStart and not oldInfo.isCollapsed:
		caret.move(textInfos.UNIT_CHARACTER, -1)
	fromFirstLine = step > 0 and _heldBackFirstLine(document)
	sentence, moved = findSentence(caret, step, fromFirstLine)
	if sentence is None:
		_debug("jawsMigrator: no sentence to read by in this document")
		return
	selection = sentence.copy()
	selection.collapse()
	if not willSayAllResume(gesture):
		speech.speakTextInfo(sentence, unit=textInfos.UNIT_SENTENCE, reason=OutputReason.CARET)
	if not oldInfo.isCollapsed:
		speech.speakSelectionChange(oldInfo, selection)
	document.selection = selection
	if moved:
		_debug(f"jawsMigrator: the {'next' if step > 0 else 'prior'} sentence, as JAWS's virtual cursor reads it, where NVDA's browse mode has no sentences: {sentence.text[:80]!r}")
	else:
		_debug(f"jawsMigrator: no {'next' if step > 0 else 'prior'} sentence, so the one at the caret is said again, as NVDA's own does: {sentence.text[:80]!r}")


def _heldBackFirstLine(document) -> bool:
	"""Whether the caret is still on a page's first line NVDA held back as the page opened (browserPages), which the
	sentence at the caret starts, as JAWS goes from the title to it. The page forgets it either way."""
	try:
		from . import browserPages

		if not browserPages.isRegistered() or browserPages.unsaidFirstLine(document) is None:
			return False
		browserPages.forgetFirstLine(document)
		return True
	except Exception:
		return False
