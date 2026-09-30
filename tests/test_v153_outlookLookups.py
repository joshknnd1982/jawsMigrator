# Unit tests for version 1.53, from the tester's second log on issue 40 (NVDA log 2026-09-30 15.51.23): "It is also very slow with the
# option checked to read the message." The log has a picture-heavy newsletter open in classic Outlook 16.0.20326 (UI Automation), and
# NVDA's watchdog says, line after line, "Recovered from potential freeze after 2.5 seconds", "5.0", "7.0" and, for a Down Arrow in a
# message of 73,022 characters with 18 links, "Recovered from freeze after 12.5 seconds", with the stack of NVDA's main thread inside a
# UI Automation call for a line of the message. The assistant's own debug log, in the same file, has "read the HTML of an Outlook
# message" at 15:51:08.562 and "asked Word's object model for the links of an Outlook message: Word has 18 hyperlinks" at 15:51:13.621,
# five seconds later, with nothing but the assistant's code between them: about 145 questions of Word, each about 35 milliseconds in
# that Outlook. The small message the tester opened first took 0.05 seconds for the same (15:49:37.167 to 15:49:37.218).
# What the assistant asked, and asked again for each line, is in outlookLookups' docstring. What is tested here is what it asks now:
# - a message with the focus is asked about once (which message it is, its HTML, Word's links, whether it is one you read), not for
#   each line; a message that takes the focus again is asked about again, and so is one whose window has another title;
# - Word's object model is asked about the links whose names nothing else gave, for half a second at most;
# - Word is asked about the pictures of a message until one answer is slow, and not after.
# Outlook and Word are imitations that count the questions put to them and advance a clock by the time each takes, here the tester's
# 35 milliseconds: classic Outlook isn't installed on the computer this was written on. NVDA's own speech and field code, and the
# assistant's own code, are the real ones, as in the tests of 1.44 and 1.49.
# Run: python -m unittest tests.test_v153_outlookLookups -v

import collections
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import test_v144_outlookPictures as pictures  # noqa: E402
import test_v149_issue42Logs as i42  # noqa: E402
import test_v149_unlabeledLinks as ul  # noqa: E402

from jawsMigrator import outlookLookups, outlookPictures, unlabeledLinks  # noqa: E402

SHOP = ul.SHOP
#: How long each question of Outlook or Word takes in the tester's Outlook, from his log: 145 questions in five seconds.
TESTERS_COST = 0.035


class Clock:
	"""The time, which nothing but the questions put to Outlook and Word moves."""

	def __init__(self):
		self.now = 5000.0

	def __call__(self):
		return self.now


class Meter:
	"""Counts the questions put to Outlook and Word, by kind, and moves the clock by what each takes."""

	def __init__(self, clock, cost=TESTERS_COST):
		self.clock, self.cost = clock, cost
		self.counts = collections.Counter()

	def ask(self, kind):
		self.counts[kind] += 1
		self.clock.now += self.cost

	@property
	def asked(self):
		return sum(self.counts.values())


# -- Outlook's object model, which counts what it is asked -----------------------------------------------------------------------


class MeteredItem:
	"""Outlook's MailItem: its HTML, its format and its EntryID, each a question."""

	Subject, ReceivedTime = "Make it Pink", "Tue 9/29/2026 8:35 AM"

	def __init__(self, meter, html, entryId="ENTRY1"):
		self.meter, self._html, self._entryId = meter, html, entryId
		self.reads = 0

	@property
	def EntryID(self):
		self.meter.ask("EntryID")
		return self._entryId

	@property
	def BodyFormat(self):
		self.meter.ask("BodyFormat")
		return unlabeledLinks.OL_FORMAT_HTML

	@property
	def HTMLBody(self):
		self.meter.ask("HTMLBody")
		self.reads += 1
		return self._html


class MeteredInspector:
	def __init__(self, meter, caption, item):
		self.meter, self._caption, self._item = meter, caption, item

	@property
	def caption(self):
		self.meter.ask("caption")
		return self._caption

	@property
	def currentItem(self):
		self.meter.ask("currentItem")
		return self._item


class MeteredInspectors:
	def __init__(self, meter, *members):
		self.meter, self._members = meter, list(members)

	@property
	def count(self):
		self.meter.ask("count")
		return len(self._members)

	def item(self, index):
		self.meter.ask("item")
		return self._members[index - 1]


class MeteredOutlook:
	"""Outlook's Application, as NVDA's Outlook support keeps it (the app module's nativeOm)."""

	def __init__(self, meter, *inspectors):
		self.meter, self._inspectors = meter, MeteredInspectors(meter, *inspectors)

	@property
	def inspectors(self):
		self.meter.ask("inspectors")
		return self._inspectors

	def activeExplorer(self):
		self.meter.ask("activeExplorer")
		return None


# -- Word's object model, which counts what it is asked ----------------------------------------------------------------------------


class MeteredShapes:
	"""Word's InlineShapes of a range: a count and items from 1, each a question."""

	def __init__(self, meter, alt):
		self.meter, self._alt = meter, alt

	@property
	def Count(self):
		self.meter.ask("shapes")
		return 0 if self._alt is None else 1

	def __getitem__(self, index):
		self.meter.ask("shape")
		return types.SimpleNamespace(AlternativeText=self._alt, Title="")


class MeteredHyperlink:
	"""Word's Hyperlink: where it goes, its kind, its range and its screen tip, each a question."""

	def __init__(self, meter, query, alt=None):
		self.meter, self._query, self._alt = meter, query, alt

	@property
	def Address(self):
		self.meter.ask("Address")
		return ul.address(self._query)

	@property
	def Type(self):
		self.meter.ask("Type")
		return unlabeledLinks.HYPERLINK_INLINE_SHAPE

	@property
	def Range(self):
		self.meter.ask("Range")
		return types.SimpleNamespace(InlineShapes=MeteredShapes(self.meter, self._alt))

	@property
	def ScreenTip(self):
		self.meter.ask("ScreenTip")
		return ""


class MeteredLinks:
	"""Word's Hyperlinks of the message: a count and items from 1."""

	def __init__(self, meter, links):
		self.meter, self._links = meter, list(links)

	@property
	def Count(self):
		self.meter.ask("Count")
		return len(self._links)

	count = Count

	def __getitem__(self, index):
		self.meter.ask("Hyperlink")
		return self._links[index - 1]


class MeteredWord:
	"""Word's Document (NVDA's WinwordDocumentObject)."""

	def __init__(self, meter, links):
		self.meter, self._links = meter, links

	@property
	def Hyperlinks(self):
		self.meter.ask("Hyperlinks")
		return self._links


def newsletter(total, named=()):
	"""The HTML of a message of ``total`` links that hold a picture: those numbered in ``named`` have alt text, the others none."""
	parts = []
	for number in range(1, total + 1):
		alt = f' alt="The HTML names picture {number}"' if number in named else ""
		parts.append(f'<a href="{SHOP}?qs=P{number}"><img src="https://image.shop.example/{number}.gif"{alt}></a>')
	return "<html><body>" + "\n".join(parts) + "</body></html>"


class Slow(ul.Outlook):
	"""A newsletter open in an Outlook that answers in the tester's 35 milliseconds: ``total`` links, the HTML names those in
	``named``, and Word's object model names the links in ``wordNamed`` (by their alt text, which only Word has). The assistant is
	on, and the message has the focus."""

	total = 18
	named = (2, 5)
	wordNamed = (1,)

	def setUp(self):
		super().setUp()
		self.clock = Clock()
		self.meter = Meter(self.clock)
		self.focus = types.SimpleNamespace(name="the message")
		for patch in (
			mock.patch.object(outlookLookups, "clock", self.clock),
			mock.patch.object(outlookLookups, "focusObject", lambda: self.focus),
			mock.patch.object(outlookLookups, "_current", None),
		):
			patch.start()
			self.addCleanup(patch.stop)
		self.turnOn()
		self.item = MeteredItem(self.meter, newsletter(self.total, self.named))
		self.outlook = MeteredOutlook(self.meter, MeteredInspector(self.meter, ul.TITLE.strip(), self.item))
		self.links = MeteredLinks(
			self.meter,
			[MeteredHyperlink(self.meter, f"P{n}", alt=f"Word says picture {n}" if n in self.wordNamed else None) for n in range(1, self.total + 1)],
		)

	def say(self, number):
		"""NVDA says the line of the link numbered ``number``, which holds only a picture: what it says, and what the questions put
		to Outlook and Word for it took."""
		message = i42.messageIn(MeteredWord(self.meter, self.links))
		before = self.clock.now
		spoken = self.said(ul.run(self.link(f"P{number}")), document=message)
		return spoken, self.clock.now - before

	def link(self, query="P1", text="", **kwargs):
		kwargs.setdefault("nativeOm", self.outlook)
		return ul.Link(query, text, **kwargs)


class OncePerFocusTest(Slow):
	def test_the_names_are_what_they_were(self):
		# Not asked for less: the HTML names the picture it names, Word the one only it names, and where a link goes the rest.
		self.assertEqual(self.say(2)[0], ["link", "The HTML names picture 2"])
		self.assertEqual(self.say(1)[0], ["link", "Word says picture 1"])
		self.assertEqual(self.say(3)[0], ["link", "click.shop.example"])

	def test_the_first_line_asks_outlook_and_no_other_line_does(self):
		first = self.say(1)[1]
		self.assertGreater(first, 0)
		for number in range(2, 19):
			with self.subTest(number=number):
				self.assertEqual(self.say(number)[1], 0, "no question put to Outlook or Word")
		self.assertEqual(self.item.reads, 1)

	def test_eighteen_links_of_a_newsletter_cost_the_main_thread_a_second_and_not_a_minute(self):
		# Before 1.53, each link asked Outlook which message is shown (eight questions) and Word for the message's hyperlinks
		# (six more) each time, and the first asked about each of the 18 hyperlinks: five seconds and then half a second a line.
		start = self.clock.now
		for number in range(1, 19):
			self.say(number)
		self.assertLess(self.clock.now - start, 1.6)

	def test_a_message_that_takes_the_focus_again_is_asked_which_it_is_again_but_not_for_its_html_and_words(self):
		self.say(1)
		asked, reads, hyperlinks = self.meter.asked, self.item.reads, self.meter.counts["Type"]
		self.focus = types.SimpleNamespace(name="the message, again")
		self.assertEqual(self.say(1)[0], ["link", "Word says picture 1"])
		self.assertGreater(self.meter.asked, asked, "which message it is, and which Word's links are, are asked again")
		self.assertEqual(self.item.reads, reads, "its HTML is kept for the messages seen last")
		self.assertEqual(self.meter.counts["Type"], hyperlinks, "and so are the names Word gave")

	def test_the_window_with_another_title_is_another_message(self):
		self.say(1)
		asked = self.meter.asked
		with mock.patch.dict(sys.modules, {"winUser": ul.winUser({ul.WINDOW: "Another message - Message (HTML) "})}):
			# The message window's title is what the inspector's caption is found by: this one has no inspector, so the links are
			# named by where they go, but the message shown is asked about again.
			self.assertEqual(self.say(2)[0], ["link", "click.shop.example"])
		self.assertGreater(self.meter.asked, asked)

	def test_what_was_learned_is_kept_for_ten_minutes(self):
		self.say(1)
		asked = self.meter.asked
		self.clock.now += outlookLookups.MAX_AGE - 1
		self.say(2)
		self.assertEqual(self.meter.asked, asked)
		self.clock.now += 2
		self.say(3)
		self.assertGreater(self.meter.asked, asked)

	def test_where_the_focus_cant_be_told_nothing_is_kept_and_each_line_asks_as_it_did(self):
		# NVDA has no object that has the focus (or its api can't say): each line is a new message as far as the assistant knows.
		with mock.patch.object(outlookLookups, "focusObject", lambda: None):
			self.say(1)
			asked = self.meter.asked
			self.say(2)
		self.assertGreater(self.meter.asked, asked)
		self.assertEqual(self.item.reads, 1, "the message's HTML is still kept for the messages seen last")


class WordForHalfASecondTest(Slow):
	total = 40
	named = ()
	wordNamed = (1, 40)

	def test_word_is_asked_about_the_links_for_half_a_second_and_then_no_more(self):
		spoken, took = self.say(1)
		# The message's HTML and Word's first questions are about 15 questions; Word's links take the half second, and one link is
		# the most the time can run over by.
		self.assertLess(took, 0.6 + outlookLookups.WORD_BUDGET + 0.4)
		self.assertEqual(spoken, ["link", "Word says picture 1"])
		self.assertLess(self.meter.counts["Address"], self.total, "Word wasn't asked about every link")
		self.assertEqual(self.say(40)[0], ["link", "click.shop.example"], "the link it got no time for is named by where it goes")
		self.assertEqual(self.say(40)[1], 0)

	def test_the_log_says_the_time_ran_out(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.say(1)
		text = "\n".join(logged.output)
		self.assertIn("the time allowed ran out", text)
		self.assertRegex(text, r"asked Word's object model for the links of an Outlook message, in \d\.\d\d seconds")

	def test_a_healthy_outlook_is_asked_about_every_link(self):
		self.meter.cost = 0.001
		self.say(1)
		self.assertEqual(self.say(40)[0], ["link", "Word says picture 40"])


class OnlyTheLinksThatNeedAnAnswerTest(Slow):
	"""Which links Word is asked about, in an Outlook that answers quickly enough for the time allowed not to matter."""

	def setUp(self):
		super().setUp()
		self.meter.cost = 0.001

	def test_word_isnt_asked_about_the_links_the_html_named(self):
		# Links 2 and 5 have their names from the HTML: Word's Type and range are asked for the other 16 and not for those.
		self.say(1)
		self.assertEqual(self.meter.counts["Type"], self.total - len(self.named))
		self.assertEqual(self.meter.counts["Address"], self.total + 2, "each link's address, and the first's and last's for the key")

	def test_where_the_html_is_not_known_word_is_asked_about_them_all(self):
		with mock.patch.object(unlabeledLinks, "messageLabels", lambda node: {}):
			self.say(1)
		self.assertEqual(self.meter.counts["Type"], self.total)


class NothingLeftForWordTest(Slow):
	named = tuple(range(1, 19))

	def test_word_isnt_asked_when_the_html_names_every_link(self):
		self.assertEqual(self.say(1)[0], ["link", "The HTML names picture 1"])
		self.assertEqual(self.meter.counts["Hyperlinks"], 0)
		self.assertEqual(self.meter.counts["Address"], 0)

	def test_and_no_later_line_asks_either(self):
		self.assertEqual(self.say(18)[0], ["link", "The HTML names picture 18"])
		self.assertEqual(self.say(1)[1], 0)


class ReadingTest(unittest.TestCase):
	"""outlookLookups itself."""

	def setUp(self):
		self.clock = Clock()
		self.focus = object()
		self.holder = types.SimpleNamespace(windowHandle=7)
		for patch in (
			mock.patch.object(outlookLookups, "clock", self.clock),
			mock.patch.object(outlookLookups, "focusObject", lambda: self.focus),
			mock.patch.object(outlookLookups, "_current", None),
			mock.patch.dict(sys.modules, {"winUser": ul.winUser({7: "Subject - Message (HTML) "})}),
		):
			patch.start()
			self.addCleanup(patch.stop)

	def test_the_same_object_in_the_same_window_is_the_same_reading(self):
		self.assertIs(outlookLookups.reading(self.holder), outlookLookups.reading(self.holder))

	def test_another_object_that_has_the_focus_is_another_reading(self):
		first = outlookLookups.reading(self.holder)
		self.focus = object()
		self.assertIsNot(outlookLookups.reading(self.holder), first)

	def test_another_title_is_another_reading(self):
		first = outlookLookups.reading(self.holder)
		with mock.patch.dict(sys.modules, {"winUser": ul.winUser({7: "Other - Message (HTML) "})}):
			self.assertIsNot(outlookLookups.reading(self.holder), first)

	def test_a_window_without_a_title_is_still_kept(self):
		with mock.patch.dict(sys.modules, {"winUser": None}):
			self.assertIs(outlookLookups.reading(self.holder), outlookLookups.reading(self.holder))

	def test_no_focus_keeps_nothing(self):
		self.focus = None
		self.assertIsNot(outlookLookups.reading(self.holder), outlookLookups.reading(self.holder))

	def test_a_reading_knows_nothing_at_first(self):
		reading = outlookLookups.reading(self.holder)
		self.assertEqual((reading.labels, reading.words, reading.readOnly, reading.picturesOff), (None, None, None, False))

	def test_readOnly_asks_once(self):
		asked = []

		def ask():
			asked.append(1)
			return True

		self.assertTrue(outlookLookups.readOnly(self.holder, ask))
		self.assertTrue(outlookLookups.readOnly(self.holder, ask))
		self.assertEqual(len(asked), 1)
		self.focus = object()
		outlookLookups.readOnly(self.holder, ask)
		self.assertEqual(len(asked), 2)

	def test_a_message_you_write_is_kept_as_one_too(self):
		self.assertFalse(outlookLookups.readOnly(self.holder, lambda: False))
		self.assertFalse(outlookLookups.readOnly(self.holder, lambda: True), "asked once: the first answer stands")

	def test_a_deadline_is_over_when_its_time_is(self):
		deadline = outlookLookups.Deadline(0.5)
		self.assertFalse(deadline.over())
		self.clock.now += 0.49
		self.assertFalse(deadline.over())
		self.clock.now += 0.02
		self.assertTrue(deadline.over())
		self.assertAlmostEqual(deadline.took(), 0.51)


class Counting(ul.Message):
	"""The Outlook message that counts how often it is asked whether it is one you read (its UI Automation states)."""

	statesAsked = 0

	@property
	def states(self):
		type(self).statesAsked += 1
		return super().states


class ReadOnlyOnceTest(ul.Outlook):
	def setUp(self):
		super().setUp()
		self.focus = types.SimpleNamespace()
		for patch in (
			mock.patch.object(outlookLookups, "focusObject", lambda: self.focus),
			mock.patch.object(outlookLookups, "_current", None),
		):
			patch.start()
			self.addCleanup(patch.stop)
		self.turnOn()
		Counting.statesAsked = 0

	def test_a_message_is_asked_whether_it_is_one_you_read_once_and_not_for_each_link(self):
		message = Counting()
		self.said(ul.run(self.link("LOGO", text="Web Browser"), "Web Browser"), document=message)
		once = Counting.statesAsked
		self.assertGreater(once, 0)
		for _ in range(10):
			self.said(ul.run(self.link("LOGO", text="Web Browser"), "Web Browser"), document=message)
		self.assertEqual(Counting.statesAsked, once)

	def test_and_again_when_it_takes_the_focus_again(self):
		message = Counting()
		self.said(ul.run(self.link("LOGO", text="Web Browser"), "Web Browser"), document=message)
		once = Counting.statesAsked
		self.focus = types.SimpleNamespace()
		self.said(ul.run(self.link("LOGO", text="Web Browser"), "Web Browser"), document=message)
		self.assertGreater(Counting.statesAsked, once)


# -- Pictures ----------------------------------------------------------------------------------------------------------------------


class SlowRange(pictures.WordRange):
	"""Word's Range, whose pictures take the clock ``cost`` seconds to give."""

	def __init__(self, document, start, end, meter):
		super().__init__(document, start, end)
		self.meter = meter

	@property
	def duplicate(self):
		return SlowRange(self.document, self.start, self.end, self.meter)

	@property
	def InlineShapes(self):
		self.meter.ask("InlineShapes")
		return super().InlineShapes


class SlowWindow(pictures.WordWindow):
	"""Word's Window: the range at a point takes ``cost`` seconds, and so do the questions about it."""

	def __init__(self, document, meter, pointCost=None):
		super().__init__(document)
		self.meter, self.pointCost = meter, pointCost

	def rangeFromPoint(self, x, y):
		self.meter.ask("rangeFromPoint")
		if self.pointCost is not None:
			self.meter.clock.now += self.pointCost
		found = super().rangeFromPoint(x, y)
		return SlowRange(found.document, found.start, found.end, self.meter)


class PicturesTest(pictures.Isolated):
	"""A line of pictures that NVDA has nothing for, in a message whose pictures Word has no text for: what the tester's candle
	shop's message is. Down Arrow through ``lines`` of it."""

	lines = 6

	def setUp(self):
		super().setUp()
		self.clock = Clock()
		self.meter = Meter(self.clock, cost=0.0)
		self.focus = types.SimpleNamespace()
		for patch in (
			mock.patch.object(outlookLookups, "clock", self.clock),
			mock.patch.object(outlookLookups, "focusObject", lambda: self.focus),
			mock.patch.object(outlookLookups, "_current", None),
		):
			patch.start()
			self.addCleanup(patch.stop)
		outlookPictures.register()
		self.message = pictures.Message()
		self.window = self.message.WinwordWindowObject = SlowWindow(self.message.document, self.meter)
		self.rows = []
		for index in range(self.lines):
			at = (20, 40 * index + 10)
			self.message.document.picture(alt="", at=at)
			self.rows.append(pictures.linkedPicture(index, at))

	def down(self):
		return [self.say(self.message, row) for row in self.rows]

	def test_a_healthy_word_is_asked_for_every_line(self):
		self.down()
		self.assertEqual(len(self.window.asked), self.lines)

	def test_a_word_slow_to_answer_is_asked_for_one_line_and_no_more(self):
		# 35 ms a question, and the range at the point alone is half a second.
		self.meter.cost = TESTERS_COST
		self.window.pointCost = 0.5
		start = self.clock.now
		said = self.down()
		self.assertEqual(len(self.window.asked), 1)
		self.assertLess(self.clock.now - start, 0.7, "one slow answer, not six")
		self.assertEqual(said, [["link"]] * self.lines, "NVDA says what it said before")

	def test_a_word_that_answers_slowly_after_the_point_is_asked_once_and_its_answer_is_used(self):
		self.message.document.shapes[0].AlternativeText = "Shop logo"
		self.meter.cost = 0.2
		said = self.down()
		self.assertEqual(said[0], ["link", "graphic", "Shop logo"], "the answer is said")
		self.assertEqual(len(self.window.asked), 1, "and Word isn't asked for the lines after it")
		self.assertEqual(said[1:], [["link"]] * (self.lines - 1))

	def test_a_message_that_takes_the_focus_again_is_asked_again(self):
		self.meter.cost = TESTERS_COST
		self.window.pointCost = 0.5
		self.down()
		self.focus = types.SimpleNamespace()
		self.down()
		self.assertEqual(len(self.window.asked), 2)

	def test_the_log_says_why(self):
		self.meter.cost = TESTERS_COST
		self.window.pointCost = 0.5
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.down()
		self.assertIn("took 0.5", "\n".join(logged.output))
		self.assertIn("isn't asked about the pictures of this message again", "\n".join(logged.output))

	def test_where_the_focus_cant_be_told_the_slow_word_is_asked_for_each_line_as_it_was(self):
		self.focus = None
		self.meter.cost = TESTERS_COST
		self.window.pointCost = 0.5
		self.down()
		self.assertEqual(len(self.window.asked), self.lines)

	def test_what_the_log_says_of_a_line_with_no_text_is_not_asked_of_a_slow_word(self):
		# A line Word has no text for says what Word held, which is a dozen questions more: not when Word is slow.
		self.meter.cost = 0.2
		self.down()
		self.assertLess(self.meter.counts["InlineShapes"], 6)


if __name__ == "__main__":
	unittest.main()
