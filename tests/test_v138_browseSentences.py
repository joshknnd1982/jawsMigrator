# Unit tests for version 1.38, from a tester's log (issue 32, their comment of 28 September 2026 with NVDA's log of
# 10:55): on a GitHub page in Edge, NVDA+N said nothing, twice, and each time NVDA's log had
#     error executing script: <bound method CursorManager.script_moveBySentence_forward of
#     <NVDAObjects.IAccessible.chromium.ChromeVBuf object at 0x0000027F8FFB5810>> with gesture 'NVDA+n'
#       File "cursorManager.pyc", line 335, in script_moveBySentence_forward
#       File "...\jawsMigrator\browserPages.py", line 656, in _caretMovementScriptHelper
#       File "cursorManager.pyc", line 172, in _caretMovementScriptHelper
#       File "textInfos\offsets.pyc", line 565, in expand
#       File "virtualBuffers\__init__.pyc", line 494, in _getUnitOffsets
#       File "textInfos\offsets.pyc", line 544, in _getUnitOffsets
#       File "textInfos\offsets.pyc", line 448, in _getSentenceOffsets
#     NotImplementedError
# The tester's migration had "When NVDA already uses a keystroke for something else, use the JAWS command instead"
# checked, so JAWS's Laptop layout keystroke Caps Lock+N, Say Next Sentence, took NVDA+N for NVDA's command that moves
# to the next sentence (KeyPlanTests). NVDA's browse mode on a web page has no sentences, and the command fails.
# - browseSentences: in a browse mode document without sentences, the assistant finds the sentences itself, moves the
#   caret to the next or prior one and says it, as JAWS's virtual cursor reads by sentence.
# The imitation NVDA is NVDA 2026.2's own code, word for word: CursorManager.script_moveBySentence_forward and _back and
# _caretMovementScriptHelper (cursorManager.py), and OffsetsTextInfo's copy, collapse, expand, move, compareEndPoints,
# setEndPoint, _getUnitOffsets, _getSentenceOffsets and moveToCodepointOffset (textInfos/offsets.py), with
# VirtualBufferTextInfo.allowMoveToUnitOffsetPastEnd (virtualBuffers/__init__.py), checked against release-2026.2 by
# NvdasOwnCodeTests when NVDA_SOURCE is set. The virtual buffer's text and its paragraphs (VBuf_getLineOffsets, in
# NVDA's C++ helper) are imitated: a block of the page ends at its line feed. The page is the reddit post of issue 32's
# JAWS speech. The assistant's code is the real one.
# Run: python -m unittest tests.test_v138_browseSentences -v

import ast
import os
import sys
import textwrap
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import browseSentences, jawsFiles, jawsKeyMap, keyPlan  # noqa: E402

#: NVDA 2026.2, source/cursorManager.py, CursorManager.script_moveBySentence_forward, word for word.
NVDA_SENTENCE_FORWARD = r'''
def script_moveBySentence_forward(self, gesture):
	self._caretMovementScriptHelper(gesture, textInfos.UNIT_SENTENCE, 1)
'''

#: NVDA 2026.2, source/cursorManager.py, CursorManager.script_moveBySentence_back, word for word.
NVDA_SENTENCE_BACK = r'''
def script_moveBySentence_back(self, gesture):
	self._caretMovementScriptHelper(gesture, textInfos.UNIT_SENTENCE, -1)
'''

#: NVDA 2026.2, source/cursorManager.py, CursorManager._caretMovementScriptHelper, word for word.
NVDA_CARET_MOVEMENT = r'''
def _caretMovementScriptHelper(
	self,
	gesture,
	unit,
	direction=None,
	posConstant=textInfos.POSITION_SELECTION,
	posUnit=None,
	posUnitEnd=False,
	extraDetail=False,
	handleSymbols=False,
):
	if isScriptWaiting():
		# Moving / reporting is quite costly, so we don't want to do it if there are more scripts waiting.
		# Otherwise, NVDA could become unusable while it processes many backed up scripts.
		return
	oldInfo = self.makeTextInfo(posConstant)
	info = oldInfo.copy()
	info.collapse(end=self.isTextSelectionAnchoredAtStart)
	if self.isTextSelectionAnchoredAtStart and not oldInfo.isCollapsed:
		info.move(textInfos.UNIT_CHARACTER, -1)
	if posUnit is not None:
		# expand and collapse to ensure that we are aligned with the end of the intended unit
		info.expand(posUnit)
		try:
			info.collapse(end=posUnitEnd)
		except RuntimeError:
			# MS Word has a "virtual linefeed" at the end of the document which can cause RuntimeError to be raised.
			# In this case it can be ignored.
			# See #7009
			pass
		if posUnitEnd:
			info.move(textInfos.UNIT_CHARACTER, -1)
	if direction is not None:
		info.expand(unit)
		info.collapse(end=posUnitEnd)
		if info.move(unit, direction) == 0 and isinstance(self, DocumentWithPageTurns):
			try:
				self.turnPage(previous=direction < 0)
			except RuntimeError:
				pass
			else:
				info = self.makeTextInfo(
					textInfos.POSITION_FIRST if direction > 0 else textInfos.POSITION_LAST,
				)
	# #10343: Speak before setting selection because setting selection might
	# move the focus, which might mutate the document, potentially invalidating
	# info if it is offset-based.
	selection = info.copy()
	info.expand(unit)
	if not willSayAllResume(gesture):
		speech.speakTextInfo(info, unit=unit, reason=controlTypes.OutputReason.CARET)
	if not oldInfo.isCollapsed:
		speech.speakSelectionChange(oldInfo, selection)
	self.selection = selection
'''

#: NVDA 2026.2, source/textInfos/offsets.py, OffsetsTextInfo.copy, word for word.
NVDA_COPY = r'''
def copy(self):
	return self.__class__(self.obj, self)
'''

#: NVDA 2026.2, source/textInfos/offsets.py, OffsetsTextInfo.collapse, word for word.
NVDA_COLLAPSE = r'''
def collapse(self, end=False):
	if not end:
		self._endOffset = self._startOffset
	else:
		self._startOffset = self._endOffset
'''

#: NVDA 2026.2, source/textInfos/offsets.py, OffsetsTextInfo.expand, word for word.
NVDA_EXPAND = r'''
def expand(self, unit):
	self._startOffset, self._endOffset = self._getUnitOffsets(unit, self._startOffset)
'''

#: NVDA 2026.2, source/textInfos/offsets.py, OffsetsTextInfo.move, word for word.
NVDA_MOVE = r'''
def move(self, unit, direction, endPoint=None):
	if direction == 0:
		return 0
	if endPoint == "end":
		offset = self._endOffset
	elif endPoint == "start":
		offset = self._startOffset
	else:
		self.collapse()
		offset = self._startOffset
	lastOffset = None
	count = 0
	lowLimit = 0
	highLimit = self._getStoryLength()
	if self.allowMoveToUnitOffsetPastEnd(unit):
		highLimit += 1
	while (
		count != direction
		and (
			lastOffset is None
			or (direction > 0 and offset > lastOffset)
			or (direction < 0 and offset < lastOffset)
		)
		and (offset < highLimit or direction < 0)
		and (offset > lowLimit or direction > 0)
	):
		lastOffset = offset
		if direction < 0 and offset > lowLimit:
			offset -= 1
		newStart, newEnd = self._getUnitOffsets(unit, offset)
		if direction < 0:
			offset = newStart
		elif direction > 0:
			offset = newEnd
		count = count + 1 if direction > 0 else count - 1
	if endPoint == "start":
		if (
			(direction > 0 and offset <= self._startOffset)
			or (direction < 0 and offset >= self._startOffset)
			or offset < lowLimit
			or offset >= highLimit
		):
			return 0
		self._startOffset = offset
	elif endPoint == "end":
		if (
			(direction > 0 and offset <= self._endOffset)
			or (direction < 0 and offset >= self._endOffset)
			or offset < lowLimit
			or offset > highLimit
		):
			return 0
		self._endOffset = offset
	else:
		if (
			(direction > 0 and offset <= self._startOffset)
			or (direction < 0 and offset >= self._startOffset)
			or offset < lowLimit
			or offset >= highLimit
		):
			return 0
		self._startOffset = self._endOffset = offset
	if self._startOffset > self._endOffset:
		tempOffset = self._startOffset
		self._startOffset = self._endOffset
		self._endOffset = tempOffset
	return count
'''

#: NVDA 2026.2, source/textInfos/offsets.py, OffsetsTextInfo.compareEndPoints, word for word.
NVDA_COMPARE_END_POINTS = r'''
def compareEndPoints(self, other, which):
	if which == "startToStart":
		diff = self._startOffset - other._startOffset
	elif which == "startToEnd":
		diff = self._startOffset - other._endOffset
	elif which == "endToStart":
		diff = self._endOffset - other._startOffset
	elif which == "endToEnd":
		diff = self._endOffset - other._endOffset
	else:
		raise ValueError("bad argument - which: %s" % which)
	if diff < 0:
		diff = -1
	elif diff > 0:
		diff = 1
	return diff
'''

#: NVDA 2026.2, source/textInfos/offsets.py, OffsetsTextInfo.setEndPoint, word for word.
NVDA_SET_END_POINT = r'''
def setEndPoint(self, other, which):
	if which == "startToStart":
		self._startOffset = other._startOffset
	elif which == "startToEnd":
		self._startOffset = other._endOffset
	elif which == "endToStart":
		self._endOffset = other._startOffset
	elif which == "endToEnd":
		self._endOffset = other._endOffset
	else:
		raise ValueError("bad argument - which: %s" % which)
	if self._startOffset > self._endOffset:
		# start should never be after end.
		if which in ("startToStart", "startToEnd"):
			self._endOffset = self._startOffset
		else:
			self._startOffset = self._endOffset
'''

#: NVDA 2026.2, source/textInfos/offsets.py, OffsetsTextInfo._getUnitOffsets, word for word.
NVDA_GET_UNIT_OFFSETS = r'''
def _getUnitOffsets(self, unit: str, offset: int) -> tuple[int, int]:
	"""Gets the start and end offsets of the unit containing the given offset.

	:param unit: Any of UNIT_CHARACTER, UNIT_WORD, UNIT_LINE, UNIT_SENTENCE, UNIT_PARAGRAPH,
		UNIT_READINGCHUNK, UNIT_STORY, or UNIT_OFFSET as defined in textInfos.
	:param offset: The offset of the character within the text unit.
	:return: A tuple of the start and end offsets of the unit.
	:raises ValueError: If the unit is not recognised.
	:raises NotImplementedError: If the offset getter for the given unit is not implemented.
	"""
	match unit:
		case textInfos.UNIT_CHARACTER:
			offsetsFunc = self._getCharacterOffsets
		case textInfos.UNIT_WORD:
			offsetsFunc = self._getWordOffsets
		case textInfos.UNIT_LINE:
			offsetsFunc = self._getLineOffsets
		case textInfos.UNIT_SENTENCE:
			offsetsFunc = self._getSentenceOffsets
		case textInfos.UNIT_PARAGRAPH:
			offsetsFunc = self._getParagraphOffsets
		case textInfos.UNIT_READINGCHUNK:
			offsetsFunc = self._getReadingChunkOffsets
		case textInfos.UNIT_STORY:
			return 0, self._getStoryLength()
		case textInfos.UNIT_OFFSET:
			return offset, offset + 1
		case _:
			raise ValueError(f"unknown unit: {unit!r}")
	return offsetsFunc(offset)
'''

#: NVDA 2026.2, source/textInfos/offsets.py, OffsetsTextInfo._getSentenceOffsets, word for word.
NVDA_GET_SENTENCE_OFFSETS = r'''
def _getSentenceOffsets(self, offset: int) -> tuple[int, int]:
	"""
	Gets the start and end offsets of the sentence containing the given offset.
	:param offset: The offset of the character within the sentence.
	:return: A tuple of the start and end offsets of the sentence.
	:raise NotImplementedError: If the method is not implemented.
	"""
	raise NotImplementedError
'''

#: NVDA 2026.2, source/textInfos/offsets.py, OffsetsTextInfo.moveToCodepointOffset, word for word.
NVDA_MOVE_TO_CODEPOINT_OFFSET = r'''
def moveToCodepointOffset(
	self,
	codepointOffset: int,
) -> Self:
	result = self.copy()
	encodedOffset = self._startOffset + self._getOffsetEncoder().strToEncodedOffsets(codepointOffset)
	result._startOffset = result._endOffset = encodedOffset
	return result
'''

#: NVDA 2026.2, source/virtualBuffers/__init__.py, VirtualBufferTextInfo.allowMoveToUnitOffsetPastEnd, word for word.
NVDA_ALLOW_MOVE_PAST_END = r'''
def allowMoveToUnitOffsetPastEnd(self, unit: str) -> bool:
	"""Virtual buffers have no insertion point, so no need to move past the end of text."""
	return False
'''

#: textInfos, as NVDA 2026.2 names its units and positions.
textInfos = types.ModuleType("textInfos")
for _name, _value in {
	"UNIT_CHARACTER": "character",
	"UNIT_WORD": "word",
	"UNIT_LINE": "line",
	"UNIT_SENTENCE": "sentence",
	"UNIT_PARAGRAPH": "paragraph",
	"UNIT_READINGCHUNK": "readingChunk",
	"UNIT_STORY": "story",
	"UNIT_OFFSET": "offset",
	"POSITION_FIRST": "first",
	"POSITION_LAST": "last",
	"POSITION_CARET": "caret",
	"POSITION_SELECTION": "selection",
	"POSITION_ALL": "all",
}.items():
	setattr(textInfos, _name, _value)


class OutputReason:
	CARET = "caret"
	FOCUS = "focus"


controlTypes = types.ModuleType("controlTypes")
controlTypes.OutputReason = OutputReason

#: What NVDA said: (text, unit, reason), and selection changes.
spoken = []
speech = types.ModuleType("speech")
speech.speakTextInfo = lambda info, unit=None, reason=None, **kwargs: spoken.append((info.text.strip(), unit, reason))
speech.speakSelectionChange = lambda old, new, **kwargs: spoken.append(("selection change", None, None))

#: More keys waiting (isScriptWaiting), and a key pressed during say all that has it go on (willSayAllResume).
waiting = {"scripts": False}
scriptHandler = types.ModuleType("scriptHandler")
scriptHandler.isScriptWaiting = lambda: waiting["scripts"]
scriptHandler.willSayAllResume = lambda gesture: bool(getattr(gesture, "inSayAll", False))


class DocumentWithPageTurns:
	"""documentBase.DocumentWithPageTurns: a web page isn't one."""


def _namespace():
	return {
		"textInfos": textInfos,
		"speech": speech,
		"controlTypes": controlTypes,
		"isScriptWaiting": lambda: scriptHandler.isScriptWaiting(),
		"willSayAllResume": lambda gesture: scriptHandler.willSayAllResume(gesture),
		"DocumentWithPageTurns": DocumentWithPageTurns,
		"Self": object,
	}


def nvdas(*names):
	"""NVDA's functions, from their code above."""
	namespace = _namespace()
	for name in names:
		exec(globals()[name], namespace)
	return namespace


_offsets = nvdas(
	"NVDA_COPY",
	"NVDA_COLLAPSE",
	"NVDA_EXPAND",
	"NVDA_MOVE",
	"NVDA_COMPARE_END_POINTS",
	"NVDA_SET_END_POINT",
	"NVDA_GET_UNIT_OFFSETS",
	"NVDA_GET_SENTENCE_OFFSETS",
	"NVDA_MOVE_TO_CODEPOINT_OFFSET",
	"NVDA_ALLOW_MOVE_PAST_END",
)


class _Encoder:
	"""The offsets are Python's characters here (a page without characters outside the Basic Multilingual Plane)."""

	@staticmethod
	def strToEncodedOffsets(offset):
		return offset


class PageText:
	"""A web page's text in NVDA's virtual buffer (VirtualBufferTextInfo), with NVDA's OffsetsTextInfo code."""

	copy = _offsets["copy"]
	collapse = _offsets["collapse"]
	expand = _offsets["expand"]
	move = _offsets["move"]
	compareEndPoints = _offsets["compareEndPoints"]
	setEndPoint = _offsets["setEndPoint"]
	_getUnitOffsets = _offsets["_getUnitOffsets"]
	_getSentenceOffsets = _offsets["_getSentenceOffsets"]
	moveToCodepointOffset = _offsets["moveToCodepointOffset"]
	allowMoveToUnitOffsetPastEnd = _offsets["allowMoveToUnitOffsetPastEnd"]

	def __init__(self, obj, position):
		self.obj = obj
		if isinstance(position, PageText):
			start, end = position._startOffset, position._endOffset
		elif position in (textInfos.POSITION_CARET, textInfos.POSITION_SELECTION):
			start, end = obj.selectionOffsets
		elif position == textInfos.POSITION_FIRST:
			start = end = 0
		elif position == textInfos.POSITION_ALL:
			start, end = 0, len(obj.text)
		else:
			raise NotImplementedError(position)
		self._startOffset, self._endOffset = start, end

	def _getStoryLength(self):
		return len(self.obj.text)

	def _getTextRange(self, start, end):
		return self.obj.text[start:end]

	@property
	def text(self):
		return self._getTextRange(self._startOffset, self._endOffset)

	@property
	def isCollapsed(self):
		return self._startOffset == self._endOffset

	def _getOffsetEncoder(self):
		return _Encoder

	def _getCharacterOffsets(self, offset):
		return offset, offset + 1

	def _getParagraphOffsets(self, offset):
		# VBuf_getLineOffsets with no line length and the screen's layout: the block the offset is in, to its line feed.
		text = self.obj.text
		start = text.rfind("\n", 0, offset) + 1
		end = text.find("\n", offset)
		return start, (len(text) if end < 0 else end + 1)

	_getLineOffsets = _getParagraphOffsets
	_getReadingChunkOffsets = _getParagraphOffsets

	def _getWordOffsets(self, offset):
		raise NotImplementedError


class WordText(PageText):
	"""A document that knows its sentences, as Word's does (its TextInfo gets them from Word)."""

	def _getSentenceOffsets(self, offset):
		text = self.obj.text
		starts = browseSentences.sentenceStarts(text) + [len(text)]
		for start, end in zip(starts, starts[1:]):
			if start <= offset < end:
				return start, end
		return offset, offset


CursorManager = type(
	"CursorManager",
	(),
	{
		name: function
		for name, function in nvdas("NVDA_CARET_MOVEMENT", "NVDA_SENTENCE_FORWARD", "NVDA_SENTENCE_BACK").items()
		if callable(function) and name.startswith(("script_", "_caretMovementScriptHelper"))
	},
)
# As NVDA's class sets them (sayAll.CURSOR.CARET).
CursorManager.script_moveBySentence_forward.resumeSayAllMode = "caret"
CursorManager.script_moveBySentence_back.resumeSayAllMode = "caret"
CursorManager.script_moveBySentence_forward.__doc__ = "Moves to the next sentence"
cursorManager = types.ModuleType("cursorManager")
cursorManager.CursorManager = CursorManager


class ChromeVBuf(CursorManager):
	"""An Edge page in browse mode."""

	TextInfo = PageText
	isTextSelectionAnchoredAtStart = True

	def __init__(self, text, caret=0):
		self.text = text
		self.selectionOffsets = (caret, caret)

	def makeTextInfo(self, position):
		return self.TextInfo(self, position)

	@property
	def selection(self):
		return self.makeTextInfo(textInfos.POSITION_SELECTION)

	@selection.setter
	def selection(self, info):
		self.selectionOffsets = (info._startOffset, info._endOffset)

	@property
	def caret(self):
		return self.selectionOffsets[0]


class Gesture:
	def __init__(self, inSayAll=False):
		self.inSayAll = inSayAll


TITLE = "What Phones Work Best On Visible?"
SENTENCES = [
	"I currently have the Pixel 8 Pro, and I'm getting ready to upgrade.",
	"I'm looking for a phone that works really well on the service.",
	"I was looking into OnePlus (but they don't seem to be around anymore), but they don't work on Visible for some reason.",
	"I've seen the odd post here and there saying Samsung phones have trouble.",
	"Are there any other phones that have issues?",
	"Any phone you've never had an issue with?",
	"Any help would be great.",
]
#: The post as NVDA's virtual buffer has it: its title, "Question", the post, a block without text, and the next line.
PAGE = f"{TITLE}\nQuestion\n{' '.join(SENTENCES)}\n\n  \nUpvote\n"


def offsetOf(text):
	return PAGE.index(text)


class _Stubbed(unittest.TestCase):
	def setUp(self):
		patcher = mock.patch.dict(
			sys.modules,
			{
				"textInfos": textInfos,
				"speech": speech,
				"controlTypes": controlTypes,
				"scriptHandler": scriptHandler,
				"cursorManager": cursorManager,
			},
		)
		patcher.start()
		self.addCleanup(patcher.stop)
		spoken.clear()
		waiting["scripts"] = False
		self.addCleanup(browseSentences.unregister)

	def page(self, caretAt=0):
		return ChromeVBuf(PAGE, caretAt)

	def said(self):
		return [text for text, _unit, _reason in spoken]


class TheTestersLogTests(_Stubbed):
	def test_nvdasOwnCommandFails(self):
		# What the tester's log shows: NVDA's own command for the next sentence, on an Edge page, raises before it moves
		# or says anything.
		page = self.page(offsetOf(SENTENCES[0]))
		with self.assertRaises(NotImplementedError):
			page.script_moveBySentence_forward(Gesture())
		self.assertEqual(spoken, [])
		self.assertEqual(page.caret, offsetOf(SENTENCES[0]))

	def test_nvdasOwnCommandForTheSentenceBeforeFailsToo(self):
		page = self.page(offsetOf(SENTENCES[2]))
		with self.assertRaises(NotImplementedError):
			page.script_moveBySentence_back(Gesture())


class SayNextSentenceTests(_Stubbed):
	def setUp(self):
		super().setUp()
		browseSentences.register()

	def test_theNextSentence(self):
		page = self.page(offsetOf(SENTENCES[0]))
		page.script_moveBySentence_forward(Gesture())
		self.assertEqual(spoken, [(SENTENCES[1], "sentence", "caret")])
		self.assertEqual(page.caret, offsetOf(SENTENCES[1]))

	def test_fromTheMiddleOfASentence(self):
		page = self.page(offsetOf("OnePlus"))
		page.script_moveBySentence_forward(Gesture())
		self.assertEqual(self.said(), [SENTENCES[3]])

	def test_sentenceBySentenceThroughThePost(self):
		page = self.page(offsetOf(TITLE))
		for expected in ["Question", *SENTENCES, "Upvote"]:
			page.script_moveBySentence_forward(Gesture())
			self.assertEqual(self.said()[-1], expected)
		# The block without text between the post and "Upvote" is passed over.
		self.assertNotIn("", self.said())

	def test_atTheEndTheSentenceIsSaidAgain(self):
		page = self.page(offsetOf("Upvote"))
		page.script_moveBySentence_forward(Gesture())
		self.assertEqual(self.said(), ["Upvote"])
		self.assertEqual(page.caret, offsetOf("Upvote"))

	def test_saysNothingWithMoreKeysWaiting(self):
		page = self.page(offsetOf(SENTENCES[0]))
		waiting["scripts"] = True
		page.script_moveBySentence_forward(Gesture())
		self.assertEqual(spoken, [])
		self.assertEqual(page.caret, offsetOf(SENTENCES[0]))

	def test_duringSayAllTheCaretMovesSilently(self):
		page = self.page(offsetOf(SENTENCES[0]))
		page.script_moveBySentence_forward(Gesture(inSayAll=True))
		self.assertEqual(spoken, [])
		self.assertEqual(page.caret, offsetOf(SENTENCES[1]))

	def test_aSelectionIsSaidAsUnselected(self):
		page = self.page(offsetOf(SENTENCES[0]))
		page.selectionOffsets = (offsetOf(SENTENCES[0]), offsetOf(SENTENCES[0]) + 5)
		page.script_moveBySentence_forward(Gesture())
		self.assertEqual(self.said(), [SENTENCES[1], "selection change"])

	def test_fromAFirstLineNvdaHeldBack(self):
		# browserPages held the page's first line back as it opened: JAWS goes from the title to the first sentence.
		page = self.page(0)
		from jawsMigrator import browserPages

		with mock.patch.object(browserPages, "isRegistered", return_value=True), mock.patch.object(browserPages, "unsaidFirstLine", return_value=object()), mock.patch.object(browserPages, "forgetFirstLine") as forget:
			page.script_moveBySentence_forward(Gesture())
		self.assertEqual(self.said(), [TITLE])
		self.assertEqual(page.caret, 0)
		forget.assert_called_once_with(page)
		page.script_moveBySentence_forward(Gesture())
		self.assertEqual(self.said()[-1], "Question")


class SayPriorSentenceTests(_Stubbed):
	def setUp(self):
		super().setUp()
		browseSentences.register()

	def test_theSentenceBefore(self):
		page = self.page(offsetOf(SENTENCES[2]))
		page.script_moveBySentence_back(Gesture())
		self.assertEqual(spoken, [(SENTENCES[1], "sentence", "caret")])
		self.assertEqual(page.caret, offsetOf(SENTENCES[1]))

	def test_fromTheMiddleOfASentenceTheOneBeforeIt(self):
		# As NVDA's own command: the start of the sentence before the one the caret is in, not of this one.
		page = self.page(offsetOf("OnePlus"))
		page.script_moveBySentence_back(Gesture())
		self.assertEqual(self.said(), [SENTENCES[1]])

	def test_intoTheParagraphBefore(self):
		page = self.page(offsetOf("Upvote"))
		page.script_moveBySentence_back(Gesture())
		self.assertEqual(self.said(), [SENTENCES[-1]])
		page.script_moveBySentence_back(Gesture())
		self.assertEqual(self.said()[-1], SENTENCES[-2])
		page = self.page(offsetOf(SENTENCES[0]))
		page.script_moveBySentence_back(Gesture())
		self.assertEqual(self.said()[-1], "Question")

	def test_atTheStartTheSentenceIsSaidAgain(self):
		page = self.page(0)
		page.script_moveBySentence_back(Gesture())
		self.assertEqual(self.said(), [TITLE])
		self.assertEqual(page.caret, 0)


class OtherDocumentsTests(_Stubbed):
	def test_aDocumentWithSentencesKeepsNvdasOwn(self):
		browseSentences.register()
		page = self.page(offsetOf(SENTENCES[0]))
		page.TextInfo = WordText
		with mock.patch.object(browseSentences, "moveBySentence") as ours:
			page.script_moveBySentence_forward(Gesture())
		ours.assert_not_called()
		self.assertEqual(page.caret, offsetOf(SENTENCES[1]))
		self.assertEqual(self.said(), [SENTENCES[1]])

	def test_nvdasOwnKeepsItsNameHelpAndSayAll(self):
		original = vars(CursorManager)["script_moveBySentence_forward"]
		browseSentences.register()
		installed = vars(CursorManager)["script_moveBySentence_forward"]
		self.assertIsNot(installed, original)
		self.assertEqual(installed.__name__, "script_moveBySentence_forward")
		self.assertEqual(installed.__doc__, "Moves to the next sentence")
		self.assertEqual(installed.resumeSayAllMode, "caret")
		self.assertEqual(vars(CursorManager)["script_moveBySentence_back"].resumeSayAllMode, "caret")
		browseSentences.register()
		self.assertIs(vars(CursorManager)["script_moveBySentence_forward"], installed)
		browseSentences.unregister()
		self.assertIs(vars(CursorManager)["script_moveBySentence_forward"], original)

	def test_offLeavesNvdasOwn(self):
		browseSentences.register()
		browseSentences.unregister()
		with self.assertRaises(NotImplementedError):
			self.page(offsetOf(SENTENCES[0])).script_moveBySentence_forward(Gesture())


class SentencesTests(unittest.TestCase):
	def starts(self, text):
		return [text[start:browseSentences.sentenceEnd(text, browseSentences.sentenceStarts(text), start)] for start in browseSentences.sentenceStarts(text)]

	def test_endsOfSentences(self):
		self.assertEqual(self.starts("One. Two! Three? Four"), ["One.", "Two!", "Three?", "Four"])
		self.assertEqual(self.starts("Really?! Yes."), ["Really?!", "Yes."])
		self.assertEqual(self.starts('He said "Stop." Then left.'), ['He said "Stop."', "Then left."])
		self.assertEqual(self.starts("(See above.) Next one."), ["(See above.)", "Next one."])
		self.assertEqual(self.starts("Wait… what"), ["Wait…", "what"])

	def test_notEnds(self):
		self.assertEqual(self.starts("It costs 3.5 dollars."), ["It costs 3.5 dollars."])
		self.assertEqual(self.starts("See github.com/joshknnd1982 now"), ["See github.com/joshknnd1982 now"])

	def test_spaces(self):
		self.assertEqual(browseSentences.sentenceStarts("   \n"), [])
		self.assertEqual(self.starts("  Lead.  Two.\n"), ["Lead.", "Two."])


class KeyPlanTests(unittest.TestCase):
	#: JAWS 2026's Default.JKM, the lines for sentences.
	jkm = jawsFiles.parseIni(
		"[Common Keys]\nAlt+NumPadMinus=SayPriorSentence\nAlt+NumPadPlus=SayNextSentence\n"
		"[Laptop Keys]\nJAWSKey+H=SaySentence\nJAWSKey+N=SayNextSentence\nJAWSKey+Y=SayPriorSentence\n[DESKTOP Keys]\n",
	)

	@staticmethod
	def bound(gesture):
		# NVDA's own NVDA+N: the NVDA menu (globalCommands.GlobalCommands.script_showGui).
		if gesture.lower().endswith("nvda+n"):
			return [("globalCommands", "GlobalCommands", "showGui", "kb:NVDA+n", "class")]
		return []

	def plan(self, override):
		plan = keyPlan.planKeys(self.jkm, "laptop", boundScripts=self.bound, overrideConflicts=override, nvdaLayout="laptop")
		return {binding.gesture: (binding.className, binding.script, binding.replaces) for binding in plan.bindings}

	def test_nvdaNIsTheNextSentenceOnlyWhenJawsCommandsTakeNvdasKeys(self):
		# The tester's log has NVDA+N run CursorManager.script_moveBySentence_forward: their migration had "use the JAWS
		# command instead" checked, as it keeps NVDA's menu on NVDA+N otherwise.
		self.assertNotIn("kb(laptop):NVDA+n", self.plan(False))
		self.assertEqual(self.plan(True)["kb(laptop):NVDA+n"], ("CursorManager", "moveBySentence_forward", ["showGui"]))
		self.assertEqual(self.plan(False)["kb(laptop):NVDA+y"], ("CursorManager", "moveBySentence_back", []))

	def test_theTargetIsTheCommandTheAssistantReadsBy(self):
		self.assertEqual(jawsKeyMap.SCRIPT_MAP["saynextsentence"][:3], ("cursorManager", "CursorManager", "moveBySentence_forward"))
		self.assertEqual(jawsKeyMap.SCRIPT_MAP["saypriorsentence"][:3], ("cursorManager", "CursorManager", "moveBySentence_back"))
		self.assertEqual(set(browseSentences.SCRIPTS), {"script_moveBySentence_forward", "script_moveBySentence_back"})


#: Where each piece of NVDA's code above is in NVDA 2026.2's source: (file, class, method).
NVDA_CODE = {
	"NVDA_SENTENCE_FORWARD": ("cursorManager.py", "CursorManager", "script_moveBySentence_forward"),
	"NVDA_SENTENCE_BACK": ("cursorManager.py", "CursorManager", "script_moveBySentence_back"),
	"NVDA_CARET_MOVEMENT": ("cursorManager.py", "CursorManager", "_caretMovementScriptHelper"),
	"NVDA_COPY": ("textInfos/offsets.py", "OffsetsTextInfo", "copy"),
	"NVDA_COLLAPSE": ("textInfos/offsets.py", "OffsetsTextInfo", "collapse"),
	"NVDA_EXPAND": ("textInfos/offsets.py", "OffsetsTextInfo", "expand"),
	"NVDA_MOVE": ("textInfos/offsets.py", "OffsetsTextInfo", "move"),
	"NVDA_COMPARE_END_POINTS": ("textInfos/offsets.py", "OffsetsTextInfo", "compareEndPoints"),
	"NVDA_SET_END_POINT": ("textInfos/offsets.py", "OffsetsTextInfo", "setEndPoint"),
	"NVDA_GET_UNIT_OFFSETS": ("textInfos/offsets.py", "OffsetsTextInfo", "_getUnitOffsets"),
	"NVDA_GET_SENTENCE_OFFSETS": ("textInfos/offsets.py", "OffsetsTextInfo", "_getSentenceOffsets"),
	"NVDA_MOVE_TO_CODEPOINT_OFFSET": ("textInfos/offsets.py", "OffsetsTextInfo", "moveToCodepointOffset"),
	"NVDA_ALLOW_MOVE_PAST_END": ("virtualBuffers/__init__.py", "VirtualBufferTextInfo", "allowMoveToUnitOffsetPastEnd"),
}


class NvdasOwnCodeTests(unittest.TestCase):
	def test_theCodeIsNvdas(self):
		# Each piece is in NVDA 2026.2's source, as a method, when a copy of it is around: set NVDA_SOURCE to its
		# source folder.
		source = os.environ.get("NVDA_SOURCE")
		if not source:
			self.skipTest("NVDA_SOURCE isn't set to a folder with NVDA 2026.2's source")
		for name, (path, className, method) in NVDA_CODE.items():
			with open(os.path.join(source, path), encoding="utf-8") as file:
				text = file.read()
			tree = ast.parse(text)
			found = None
			for node in ast.walk(tree):
				if isinstance(node, ast.ClassDef) and node.name == className:
					for item in node.body:
						if isinstance(item, ast.FunctionDef) and item.name == method:
							found = textwrap.dedent(ast.get_source_segment(text, item, padded=True))
			self.assertEqual(globals()[name].strip(), (found or "").strip(), name)


if __name__ == "__main__":
	unittest.main()
