# Unit tests for version 1.44, from a tester's report (issue 42, "Jaws reads an email better then NVDA"): "Jaws will read some titles for the
# email. NVDA will read nothing." The tester's log (NVDA log 2026-09-29 08.51.21.zip, nvda.log, NVDA 2026.2, Outlook 16.0.20326,
# which NVDA reads through UI Automation) has a marketing e-mail open in classic Outlook, and Down Arrow through it says:
#     08:51:02.245 Speaking ['link', 'Web Browser']
#     08:51:02.832 Speaking ['blank']
#     08:51:03.358 Speaking ['link']
#     ... 'link' or 'blank' for each of its pictures, 34 lines, until ...
#     08:51:16.510 Speaking ['link', 'Update My Email Preferences ']
#     08:51:16.773 Speaking ['| ']
#     08:51:17.528 Speaking ['link', 'Unsubscribe']
# The Outlook First Line Silence add-on the tester runs says of each 'blank' and 'link' line that its text has no length
# ("Outlook First Line Silence links: blank line"): a picture has no text in Word's UI Automation. NVDA's own issues 14217 and
# 18177 are the same: "graphic" with no text for a picture in a message, and "link" alone for a picture inside a link. JAWS says
# a picture's alternative text (WordFunc.jss, SayInlineShape, GetInlineShapeAlternativeText).
# - outlookPictures: in an Outlook message, a line of pictures that NVDA has nothing to say for is said with the alternative
#   text Word's object model has for the picture at its start: "link, graphic, <text>".
# The alternative texts here are made up: the tester's message isn't in the issue. What is the tester's is the log's speech and
# what NVDA's UI Automation gives for a picture (nothing, or a graphic without text). NVDA 2026.2's own speech code says the
# lines (tests/test_v125_linkSpeech.py's speakTextInfo and getControlFieldSpeech, word for word). Word's object model is
# imitated, and classic Outlook isn't installed on the computer this was made on: it was not tried with Outlook.
# Run: python -m unittest tests.test_v144_outlookPictures -v

import os
import sys
import threading
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v125_linkSpeech as v125  # noqa: E402
from jawsMigrator import outlookPictures, state  # noqa: E402

textInfos, controlTypes = v125.textInfos, v125.controlTypes
Role, State, OutputReason = v125.Role, v125.State, v125.OutputReason
ControlField, FormatField, FieldCommand = textInfos.ControlField, textInfos.FormatField, textInfos.FieldCommand
spoken = v125.spoken

#: What each of the tester's Down Arrow presses said, from the log: L is a picture inside a link, B a picture on a line of
#: its own.
LOG = [
	["link", "Web Browser"], "B", "L", "B", "L", "B", "L", "L", "L", "B", "L", "B", "B", "B", "L", "L", "L", "L", "L", "L", "B",
	"B", "B", "L", "B", "L", "L", "L", "B", "L", "L", "L", "B", ["link", "Update My Email Preferences "], ["| "], ["link", "Unsubscribe"],
]
#: What the tester's NVDA said for them.
LOGGED = [["link"] if row == "L" else ["blank"] if row == "B" else row for row in LOG]
#: Made up: what the pictures' alternative texts might be in a promotion like this.
MADE_UP = ["Yankee Candle", "Make it Pink", "40% Off All Candles", "Shop Now", "Free Shipping", "Candle scents we love"]


class Point:
	def __init__(self, x, y):
		self.x, self.y = x, y


# -- Word's object model, imitated: what NVDA asks of it for a range's location ----------------------------------------------


class Collection:
	"""A Word collection: a count, and items from 1."""

	def __init__(self, items):
		self.items = list(items)

	@property
	def count(self):
		return len(self.items)

	def __getitem__(self, index):
		return self.items[index - 1]


class Shape:
	"""Word's InlineShape: where it is in the document, its alternative text and its title."""

	def __init__(self, start, alt="", title="", tip=""):
		self.start, self.AlternativeText, self.Title, self.tip = start, alt, title, tip
		self.Range = types.SimpleNamespace(Start=start)


class Link:
	def __init__(self, tip):
		self.ScreenTip = tip


class WordRange:
	"""Word's Range, for what NVDA asks: a duplicate of it, one character more, or one before, and the pictures and links in it."""

	def __init__(self, document, start, end):
		self.document, self.start, self.end = document, start, end

	@property
	def duplicate(self):
		return WordRange(self.document, self.start, self.end)

	def expand(self, unit):
		assert unit == outlookPictures.WD_CHARACTER
		if self.end == self.start:
			self.end += 1

	def moveStart(self, unit, count):
		assert unit == outlookPictures.WD_CHARACTER
		self.start += count

	@property
	def InlineShapes(self):
		return Collection(shape for shape in self.document.shapes if self.start <= shape.start < self.end)

	@property
	def Hyperlinks(self):
		return Collection(Link(shape.tip) for shape in self.document.shapes if shape.tip and self.start <= shape.start < self.end)


class WordWindow:
	"""Word's Window: the range at a point on the screen. A picture is drawn 40 pixels wide from its ``x``, 30 high from its
	``y``; a point outside every picture gives the range after the last one."""

	def __init__(self, document):
		self.document = document
		self.asked = []
		self.fails = 0
		self.after = False

	def rangeFromPoint(self, x, y):
		self.asked.append((x, y))
		if self.fails:
			self.fails -= 1
			raise OSError("Word didn't answer")
		for shape in self.document.shapes:
			left, top = shape.at
			if left <= x < left + 40 and top <= y < top + 30:
				offset = shape.start + (1 if self.after else 0)
				return WordRange(self.document, offset, offset)
		return WordRange(self.document, 10_000, 10_000)


class WordDocument:
	"""The message, as Word has it: its pictures."""

	def __init__(self):
		self.shapes = []

	def picture(self, alt="", title="", tip="", at=None):
		shape = Shape(len(self.shapes) * 3 + 2, alt, title, tip)
		shape.at = at or (20, 40 * len(self.shapes) + 10)
		self.shapes.append(shape)
		return shape


# -- NVDA's UI Automation text of a Word document: what it gives for the tester's lines ---------------------------------------


def hyperlink(uniqueID):
	"""NVDA's control field for Word's Hyperlink element: the link's text is its content, so it has no name."""
	field = ControlField()
	field.update(role=Role.LINK, states={State.LINKED}, runtimeID=(42, uniqueID), nameIsContent=True, description="", level=None)
	field["_startOfNode"] = field["_endOfNode"] = True
	return field


def graphic(uniqueID, content=None):
	"""NVDA's control field for an Image element (WordDocumentTextInfo._getControlFieldForUIAObject): its content is what Word
	tells NVDA the picture is: nothing, for an e-mail's pictures."""
	field = ControlField()
	field.update(role=Role.GRAPHIC, states=set(), runtimeID=(42, uniqueID), nameIsContent=True, description="", level=None)
	field["_startOfNode"] = field["_endOfNode"] = True
	if content is not None:
		field["content"] = content
	return field


class Line:
	"""A line of the message: what NVDA's getTextWithFields gives for it, and where its first picture is on the screen."""

	def __init__(self, parts, at=(20, 10), collapsed=False):
		self.parts, self.at, self.collapsed = parts, at, collapsed


def linkedPicture(uniqueID, at=(20, 10)):
	"""A line with a picture inside a link: Word's Hyperlink element, and no text. NVDA puts a blank formatChange and an
	empty string between a controlStart and its controlEnd, as the comment in its getTextWithFields says."""
	return Line([("start", hyperlink(uniqueID)), ("format", FormatField()), "", ("end", None)], at)


def picture(at=(20, 10)):
	"""A line with only a picture in it: no control field of its own, no text."""
	return Line([("format", FormatField()), ""], at)


def words(*text):
	return Line([("format", FormatField()), *text])


class WordText(v125.TextInfo):
	"""NVDA's WordDocumentTextInfo for a line of the message: its fields, where it is on the screen, and Word's scrolling."""

	isCollapsed = False

	def __init__(self, obj, line):
		self.obj, self.line = obj, line
		self.isCollapsed = line.collapsed

	def copy(self):
		return WordText(self.obj, self.line)

	def expand(self, unit):
		pass

	@property
	def text(self):
		return "".join(part for part in self.line.parts if isinstance(part, str))

	@property
	def pointAtStart(self):
		if self.obj.offScreen:
			raise LookupError
		return Point(*self.line.at)

	def _ensureRangeVisibility(self):
		self.obj.scrolled += 1
		self.obj.offScreen = self.obj.stillOffScreen

	def getTextWithFields(self, formatConfig=None):
		commands = []
		for part in self.line.parts:
			if isinstance(part, str):
				commands.append(part)
			else:
				kind, field = part
				if kind == "start":
					commands.append(FieldCommand("controlStart", ControlField(field)))
				elif kind == "format":
					commands.append(FieldCommand("formatChange", field))
				else:
					commands.append(FieldCommand("controlEnd", None))
		return commands


NVDAS_OWN = vars(WordText)["getTextWithFields"]


class Message:
	"""NVDA's object for the message (appModules.outlook.OutlookUIAWordDocument), with Word's object model behind it."""

	def __init__(self, appName="outlook", document=None):
		self.appModule = types.SimpleNamespace(appName=appName)
		self.document = document or WordDocument()
		self.WinwordWindowObject = WordWindow(self.document)
		self.offScreen = False
		self.stillOffScreen = False
		self.scrolled = 0


def wordModules(textInfoClass):
	module = types.ModuleType("NVDAObjects.UIA.wordDocument")
	module.WordDocumentTextInfo = textInfoClass
	return {
		"textInfos": textInfos,
		"controlTypes": controlTypes,
		"NVDAObjects": types.ModuleType("NVDAObjects"),
		"NVDAObjects.UIA": types.ModuleType("NVDAObjects.UIA"),
		"NVDAObjects.UIA.wordDocument": module,
	}


class Isolated(unittest.TestCase):
	"""Each test starts with the assistant off, NVDA's own method in place, nothing logged, and NVDA's own speech."""

	def setUp(self):
		# NVDA's speech module, as much of it as these lines use: its own speakTextInfo, getControlFieldSpeech, getPropertiesSpeech.
		self.speech = types.ModuleType("speech")
		self.speech.getControlFieldSpeech = v125.NVDA_FIELD_SPEECH
		self.speech.getPropertiesSpeech = v125.speechScope["getPropertiesSpeech"]
		self.speech.speakTextInfo = v125.speechScope["speakTextInfo"]
		for patch in (
			mock.patch.dict(sys.modules, dict(wordModules(WordText), speech=self.speech, config=v125.config)),
			mock.patch.object(outlookPictures, "_enabled", False),
			mock.patch.object(outlookPictures, "_failed", False),
			mock.patch.object(outlookPictures, "_replaced", []),
			mock.patch.object(outlookPictures, "_failures", 0),
			mock.patch.object(outlookPictures, "_suspended", False),
			mock.patch.object(outlookPictures, "_noted", {}),
		):
			patch.start()
			self.addCleanup(patch.stop)
		self.addCleanup(setattr, WordText, "getTextWithFields", NVDAS_OWN)
		self.addCleanup(outlookPictures.unregister)
		v125.config.conf = v125.testersConfig()
		spoken.clear()

	def say(self, message, line):
		"""Down Arrow to the line: NVDA says it for the caret, as it says the lines of the tester's log."""
		spoken.clear()
		self.speech.speakTextInfo(WordText(message, line), unit=textInfos.UNIT_LINE, reason=OutputReason.CARET)
		return spoken[-1]


class TesterTests(Isolated):
	"""The tester's message, line by line, with NVDA's own speech code."""

	def theMessage(self):
		"""The lines of the log: a link, pictures, and the footer's links, with the alternative texts made up."""
		message = Message()
		lines, pictures = [], 0
		for index, row in enumerate(LOG):
			if row == "L" or row == "B":
				text = MADE_UP[pictures % len(MADE_UP)]
				pictures += 1
				at = (20, 40 * index + 10)
				message.document.picture(alt=text, at=at)
				lines.append((linkedPicture(index, at) if row == "L" else picture(at), text))
			elif row[0] == "link":
				lines.append((Line([("start", hyperlink(index)), ("format", FormatField()), row[1], ("end", None)]), None))
			else:
				lines.append((words(row[0]), None))
		return message, lines

	def test_nvdaSaidWhatTheLogSays(self):
		# The imitation NVDA, with NVDA 2026.2's own speech code, says the tester's 36 lines word for word.
		message, lines = self.theMessage()
		self.assertEqual([self.say(message, line) for line, _ in lines], LOGGED)
		self.assertEqual(message.WinwordWindowObject.asked, [], "and Word's object model is not asked")

	def test_aPictureIsSaidWithItsText(self):
		outlookPictures.register()
		message, lines = self.theMessage()
		said = [self.say(message, line) for line, _ in lines]
		expected = []
		for row, (line, text) in zip(LOG, lines):
			if row == "L":
				expected.append(["link", "graphic", text])
			elif row == "B":
				expected.append(["graphic", text])
			else:
				expected.append(row)
		self.assertEqual(said, expected)
		self.assertEqual(said[1], ["graphic", "Yankee Candle"])
		self.assertEqual(said[2], ["link", "graphic", "Make it Pink"])
		self.assertEqual(said[0], ["link", "Web Browser"], "a link with words in it is said as before")
		self.assertEqual(said[-3:], [["link", "Update My Email Preferences "], ["| "], ["link", "Unsubscribe"]])

	def test_twoPicturesInARowAreBothSaid(self):
		# Down Arrow from a picture to the next, both in links: NVDA compares a line's fields with the last line's, and says
		# each line's picture.
		outlookPictures.register()
		message = Message()
		message.document.picture(alt="Shop Now", at=(20, 10))
		message.document.picture(alt="Free Shipping", at=(20, 50))
		first = self.say(message, linkedPicture(1, (20, 10)))
		second = self.say(message, linkedPicture(1, (20, 50)))
		self.assertEqual(first, ["link", "graphic", "Shop Now"])
		self.assertEqual(second, ["link", "graphic", "Free Shipping"], "each line is said in full, as NVDA says a line of a link")

	def test_theSamePictureAgainIsSaidAgain(self):
		outlookPictures.register()
		message = Message()
		message.document.picture(alt="Shop Now", at=(20, 10))
		line = linkedPicture(1, (20, 10))
		self.assertEqual(self.say(message, line), ["link", "graphic", "Shop Now"])
		self.assertEqual(self.say(message, line), ["link", "graphic", "Shop Now"], "arrowing back to it says it again")

	def test_turnedOffNvdaSaysWhatItSaid(self):
		message, lines = self.theMessage()
		outlookPictures.register()
		outlookPictures.unregister()
		self.assertIs(vars(WordText)["getTextWithFields"], NVDAS_OWN)
		self.assertEqual([self.say(message, line) for line, _ in lines], LOGGED)


class PictureTests(Isolated):
	def setUp(self):
		super().setUp()
		outlookPictures.register()
		self.message = Message()

	def asked(self):
		return self.message.WinwordWindowObject.asked

	def test_aPictureNvdaSaysNothingAbout(self):
		# NVDA's issue 14217: "graphic" with nothing after it; Word's UI Automation gives the picture, without its text.
		self.message.document.picture(alt="a person on a boat")
		self.assertEqual(self.say(self.message, Line([("start", graphic(3, "")), ("format", FormatField()), "", ("end", None)])), ["graphic", "a person on a boat"])
		self.assertEqual(self.asked(), [(21, 11)], "one question, for the pixel inside the line's top left corner")

	def test_aPictureNvdaSaysTheTextOfIsLeftAlone(self):
		self.message.document.picture(alt="another text")
		line = Line([("start", graphic(3, "Word told NVDA")), ("format", FormatField()), "", ("end", None)])
		self.assertEqual(self.say(self.message, line), ["graphic", "Word told NVDA"])
		self.assertEqual(self.asked(), [], "Word's object model is not asked")

	def test_aLineWithWordsIsLeftAlone(self):
		self.message.document.picture(alt="text")
		self.assertEqual(self.say(self.message, words("Order today and save.")), ["Order today and save."])
		self.assertEqual(self.say(self.message, words("\ufffc Order today")), ["\ufffc Order today"], "a picture beside words: the words")
		self.assertEqual(self.asked(), [])

	def test_anEmptyParagraphIsNotAPicture(self):
		self.message.document.picture(alt="text")
		self.assertEqual(self.say(self.message, words("\r")), ["blank"])
		self.assertEqual(self.asked(), [])

	def test_aCollapsedRangeIsNotAsked(self):
		self.message.document.picture(alt="text")
		self.assertEqual(self.say(self.message, Line([("format", FormatField()), ""], collapsed=True)), ["blank"])
		self.assertEqual(self.asked(), [])

	def test_theObjectReplacementCharacterIsAPicture(self):
		self.message.document.picture(alt="Shop Now")
		self.assertEqual(self.say(self.message, words("\ufffc"))[:2], ["graphic", "Shop Now"])

	def test_theTitleWhenThereIsNoAlternativeText(self):
		self.message.document.picture(alt="", title="Spring sale")
		self.assertEqual(self.say(self.message, picture()), ["graphic", "Spring sale"])

	def test_theLinksScreenTipWhenThePictureHasNoText(self):
		self.message.document.picture(alt="", title="", tip="Shop the sale")
		self.assertEqual(self.say(self.message, linkedPicture(1)), ["link", "graphic", "Shop the sale"])

	def test_thePictureJustBeforeThePoint(self):
		# The point of a picture's edge can be the next character's: Word's range starts after the picture.
		self.message.WinwordWindowObject.after = True
		self.message.document.picture(alt="Shop Now")
		self.assertEqual(self.say(self.message, picture()), ["graphic", "Shop Now"])

	def test_noTextAnywhereNvdaSaysWhatItSaid(self):
		self.message.document.picture(alt="")
		self.assertEqual(self.say(self.message, linkedPicture(1)), ["link"])
		self.assertEqual(self.say(self.message, picture()), ["blank"])

	def test_aTextWithSpacesIsOneLine(self):
		self.message.document.picture(alt="  Free \r\n shipping   today ")
		self.assertEqual(self.say(self.message, picture()), ["graphic", "Free shipping today"])

	def test_aPictureOffTheScreenIsScrolledTo(self):
		self.message.document.picture(alt="Shop Now")
		self.message.offScreen = True
		self.assertEqual(self.say(self.message, picture()), ["graphic", "Shop Now"])
		self.assertEqual(self.message.scrolled, 1)

	def test_aPictureThatStaysOffTheScreenIsLeftAlone(self):
		self.message.document.picture(alt="Shop Now")
		self.message.offScreen = self.message.stillOffScreen = True
		self.assertEqual(self.say(self.message, picture()), ["blank"])
		self.assertEqual(self.say(self.message, picture()), ["blank"])
		self.assertEqual(outlookPictures._failures, 0, "not a failure of Word's object model")
		self.assertFalse(outlookPictures._suspended)

	def test_whereWordHasNoPictureThereIsNothingToSay(self):
		# A point that is on no picture: an empty table cell, say.
		self.assertEqual(self.say(self.message, picture(at=(500, 500))), ["blank"])

	def test_wordNotAnsweringThreeTimesItIsLeftAlone(self):
		self.message.document.picture(alt="Shop Now")
		self.message.WinwordWindowObject.fails = 3
		with self.assertLogs("nvda", level="DEBUG") as logged:
			for _ in range(3):
				self.assertEqual(self.say(self.message, picture()), ["blank"])
			self.assertTrue(outlookPictures._suspended)
			self.assertEqual(self.say(self.message, picture()), ["blank"], "Word would answer now, and isn't asked")
		self.assertEqual(len(self.asked()), 3)
		notes = [line for line in logged.output if "couldn't give the picture" in line or "doesn't ask it for pictures" in line]
		self.assertEqual(len(notes), 4, logged.output)

	def test_aFailureAndThenAnAnswerStartsTheCountAgain(self):
		self.message.document.picture(alt="Shop Now")
		window = self.message.WinwordWindowObject
		for round_ in range(3):
			window.fails = 2
			self.say(self.message, picture())
			self.say(self.message, picture())
			self.assertEqual(self.say(self.message, picture()), ["graphic", "Shop Now"], round_)
		self.assertFalse(outlookPictures._suspended)
		self.assertEqual(outlookPictures._failures, 0)

	def test_whenWordHasNoObjectModelNvdaSaysWhatItSaid(self):
		self.message.WinwordWindowObject = None
		self.assertEqual(self.say(self.message, picture()), ["blank"])

	def test_onlyOnNvdasMainThread(self):
		self.message.document.picture(alt="Shop Now")
		result = []
		thread = threading.Thread(target=lambda: result.append(self.say(self.message, picture())))
		thread.start()
		thread.join()
		self.assertEqual(result, [["blank"]])
		self.assertEqual(self.asked(), [])

	def test_inWordItself(self):
		message = Message("winword")
		message.document.picture(alt="Shop Now")
		self.assertEqual(self.say(message, picture()), ["blank"])
		self.assertEqual(message.WinwordWindowObject.asked, [])

	def test_whatItSaidIsInTheLog(self):
		self.message.document.picture(alt="Shop Now")
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.say(self.message, picture())
		self.assertTrue(any("alternative text of a picture in an Outlook message, said as JAWS says it: 'Shop Now'" in line for line in logged.output), logged.output)

	def test_whatItCouldntFindIsInTheLogWithTheLinesFields(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.say(self.message, linkedPicture(1))
		note = [line for line in logged.output if "no alternative text for the picture" in line]
		self.assertEqual(len(note), 1, logged.output)
		self.assertIn("start LINK, '', end", note[0])

	def test_theLogIsNotFlooded(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			for index in range(40):
				self.say(self.message, linkedPicture(index))
		notes = [line for line in logged.output if "no alternative text for the picture" in line]
		self.assertEqual(len(notes), outlookPictures._MOST_NOTES)

	def test_aLinkNamedAlreadyIsNotSaidTwice(self):
		# Another part of the assistant, or an add-on, gives a link with no text of its own a name (its content). The same
		# text after "graphic" would be said twice: "link Shop Now, graphic, Shop Now".
		self.message.document.picture(alt="Shop Now")
		named = hyperlink(1)
		named["content"] = "Shop Now"
		line = Line([("start", named), ("format", FormatField()), "", ("end", None)])
		self.assertEqual(self.say(self.message, line), ["link", "Shop Now"], "NVDA says the link's name, and the picture adds nothing")
		self.assertEqual(len(self.asked()), 1, "Word's object model is asked to tell whether it is the same")

	def test_aLinkNamedAlreadyWithOtherWordsHasThePictureSaidToo(self):
		self.message.document.picture(alt="Make it Pink")
		named = hyperlink(1)
		named["content"] = "example.com"
		line = Line([("start", named), ("format", FormatField()), "", ("end", None)])
		self.assertEqual(self.say(self.message, line), ["link", "example.com", "graphic", "Make it Pink"])

	def test_theLinksNameHasThePicturesTextInLongerWords(self):
		self.message.document.picture(alt="shop now")
		named = hyperlink(1)
		named["content"] = "Shop Now: 40% off all candles"
		line = Line([("start", named), ("format", FormatField()), "", ("end", None)])
		self.assertEqual(self.say(self.message, line), ["link", "Shop Now: 40% off all candles"])

	def test_theFieldsNvdaMadeAreKept(self):
		self.message.document.picture(alt="Shop Now")
		fields = WordText(self.message, linkedPicture(7)).getTextWithFields()
		kinds = [item.command if isinstance(item, FieldCommand) else repr(item) for item in fields]
		self.assertEqual(kinds, ["controlStart", "controlStart", "formatChange", "''", "controlEnd", "controlEnd"])
		link, picture_ = fields[0].field, fields[1].field
		self.assertEqual(link["role"], Role.LINK)
		self.assertEqual((picture_["role"], picture_["content"]), (Role.GRAPHIC, "Shop Now"))
		self.assertEqual(picture_["runtimeID"], ("jawsMigrator", 2), "the picture's place in the document")


class RegisterTests(Isolated):
	def test_registerAndUnregister(self):
		outlookPictures.register()
		self.assertTrue(outlookPictures.isRegistered())
		installed = vars(WordText)["getTextWithFields"]
		self.assertIsNot(installed, NVDAS_OWN)
		self.assertIs(getattr(installed, outlookPictures.ORIGINAL), NVDAS_OWN)
		outlookPictures.register()
		self.assertIs(vars(WordText)["getTextWithFields"], installed, "registered twice, wrapped once")
		outlookPictures.unregister()
		self.assertFalse(outlookPictures.isRegistered())
		self.assertIs(vars(WordText)["getTextWithFields"], NVDAS_OWN)

	def test_anotherAddonsWrapperIsKept(self):
		outlookPictures.register()
		ours = vars(WordText)["getTextWithFields"]

		def theirs(self, *args, **kwargs):
			return ours(self, *args, **kwargs)

		theirs.__wrapped__ = ours
		WordText.getTextWithFields = theirs
		outlookPictures.unregister()
		self.assertIs(vars(WordText)["getTextWithFields"], theirs, "the other add-on's wrapper stays")
		message = Message()
		message.document.picture(alt="Shop Now")
		self.assertEqual(self.say(message, picture()), ["blank"], "and the assistant's does nothing")
		outlookPictures.register()
		self.assertIs(vars(WordText)["getTextWithFields"], theirs, "turned on again, nothing is wrapped twice")
		self.assertEqual(self.say(message, picture()), ["graphic", "Shop Now"])

	def test_withoutNvdasUiaSupportForWordNothingChanges(self):
		with mock.patch.dict(sys.modules, {"NVDAObjects.UIA.wordDocument": None}):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				outlookPictures.register()
		self.assertFalse(outlookPictures.isRegistered())
		self.assertTrue(any("can't have NVDA say the alternative text of a picture" in line for line in logged.output), logged.output)

	def test_anNvdaWithoutTheMethodChangesNothing(self):
		bare = type("WordDocumentTextInfo", (), {})
		with mock.patch.dict(sys.modules, wordModules(bare)):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				outlookPictures.register()
		self.assertFalse(outlookPictures.isRegistered())
		self.assertNotIn("getTextWithFields", vars(bare))
		self.assertTrue(any("NVDA has no WordDocumentTextInfo.getTextWithFields" in line for line in logged.output), logged.output)

	def test_aFailureOfItsOwnIsLoggedOnceAndNvdaSaysWhatItSaid(self):
		outlookPictures.register()
		message = Message()
		message.document.picture(alt="Shop Now")
		with mock.patch.object(outlookPictures, "addPictureText", side_effect=RuntimeError("broken")):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				self.assertEqual(self.say(message, picture()), ["blank"])
				self.assertEqual(self.say(message, picture()), ["blank"])
		failures = [line for line in logged.output if "could not say the alternative text of a picture" in line]
		self.assertEqual(len(failures), 1, logged.output)

	def test_registeringAgainAfterASuspensionAsksAgain(self):
		outlookPictures.register()
		outlookPictures._suspended, outlookPictures._failures = True, 3
		outlookPictures.unregister()
		outlookPictures.register()
		self.assertFalse(outlookPictures._suspended)
		self.assertEqual(outlookPictures._failures, 0)


class SettingTests(unittest.TestCase):
	def test_onUnlessTurnedOff(self):
		self.assertTrue(outlookPictures.wanted({}))
		self.assertTrue(outlookPictures.wanted(dict(state.DEFAULTS)))
		self.assertFalse(outlookPictures.wanted({outlookPictures.STATE_KEY: False}))
		self.assertFalse(outlookPictures.wanted(None))
		self.assertIs(state.DEFAULTS[outlookPictures.STATE_KEY], True)


if __name__ == "__main__":
	unittest.main()
