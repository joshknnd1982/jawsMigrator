# Unit tests for version 1.49, from the tester's answer to 1.44 (issue 42, "Jaws reads an email better then NVDA"). The tester
# updated to 1.44 and then 1.45 and sent three NVDA logs (2026-09-30 13.13, 13.17 and 13.30, the last with 1.45) and the message
# as a .msg, and said "it didn't" and "still not reading the links". What the logs show, line after line, for the picture lines
# of the candle shop's message (opened from a .msg in File Explorer, in classic Outlook 16.0.20326 through UI Automation):
#     jawsMigrator: Word's object model has no alternative text for the picture at the start of this line of an Outlook message
#     (NVDA's fields: start EDITABLETEXT, start EDITABLETEXT, start LINK, '', end, end, end)
#     Speaking ['link']   (and, for the next line of the same tall picture, Speaking ['blank'])
# So NVDA's text of each of those lines is a link with an empty string in it: no picture (no "graphic" field), no U+FFFC; Word's
# object model, asked for the picture at the start of the line, had no text. The message's HTML (read from the .msg as data) has
# 21 pictures, all remote (src="https://..."), 20 of them in links, each with the alt text its sender wrote; the window's title
# is "Say Hello to 40% off ALL Candles - Message (HTML) ". 1.49's unlabeledLinks names such a link from the message's HTML, and this
# is what was added to it for the logs:
# - the message's window is found by its caption or by its subject, by the one Outlook has in front, or by the message list's
#   selection, where it was found only by a caption that equals the window's title;
# - Word's own object model is the second place a name is looked for (the alt text of the picture in the link, by the link's
#   address), where the HTML has none;
# - the debug log says what the HTML held and how the message was found, what Word's object model held, what was asked of Word
#   for a picture and what it held, and where a link's name was lost, so that the next log of a tester says why.
# Classic Outlook isn't installed on the computer these were written on: Outlook's and Word's object models are imitations.
# Run: python -m unittest tests.test_v149_issue42Logs -v

import os
import sys
import threading
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import test_v149_unlabeledLinks as ul  # noqa: E402
import test_v144_outlookPictures as pictures  # noqa: E402

from jawsMigrator import outlookMessages, outlookPictures, unlabeledLinks  # noqa: E402

address, run, Item, Inspector, Collection = ul.address, ul.run, ul.Item, ul.Inspector, ul.Collection
ALT_LOGO, ALT_FILLER = ul.ALT_LOGO, ul.ALT_FILLER


class FullObjectModel(ul.ObjectModel):
	"""Outlook's Application with the window Outlook has in front (Application.ActiveInspector)."""

	def __init__(self, *args, active=None, **kwargs):
		super().__init__(*args, **kwargs)
		self._active = active

	def activeInspector(self):
		self.asked += 1
		return self._active


# -- Word's object model: the hyperlinks of a message --------------------------------------------------------------------------


class WordCollection:
	"""A Word collection: a count (Word answers to Count and count alike), and items from 1."""

	def __init__(self, items):
		self.items = list(items)

	@property
	def Count(self):
		return len(self.items)

	count = Count

	def __getitem__(self, index):
		return self.items[index - 1]


class Shape:
	def __init__(self, alt="", title="", kind=1):
		self.AlternativeText, self.Title, self.Type = alt, title, kind


class Hyperlink:
	"""Word's Hyperlink: where it goes, its kind (2, msoHyperlinkInlineShape, for a picture), its screen tip, and its range.
	``typeReads`` counts how often the kind is asked: once for each link each time the links are gone through."""

	def __init__(self, query, alt=None, title="", tip="", kind=None, value=None):
		self.Address = address(query) if value is None else value
		self.ScreenTip = tip
		shapes = [] if alt is None else [Shape(alt, title)]
		self._type = kind if kind is not None else (unlabeledLinks.HYPERLINK_INLINE_SHAPE if shapes else 0)
		self.typeReads = 0
		self.Range = types.SimpleNamespace(InlineShapes=WordCollection(shapes))

	@property
	def Type(self):
		self.typeReads += 1
		return self._type


class WordDocumentObject:
	"""Word's Document, as far as the assistant asks: its Hyperlinks. Counts what it is asked."""

	def __init__(self, *links):
		self.asked = 0
		self._links = list(links)

	@property
	def Hyperlinks(self):
		self.asked += 1
		return WordCollection(self._links)

	def goneThrough(self):
		"""How many times the links were gone through, link by link: the kinds asked."""
		return sum(link.typeReads for link in self._links if isinstance(link, Hyperlink))


def messageIn(document=None, readOnly=True):
	message = ul.Message(readOnly=readOnly)
	message.WinwordDocumentObject = document
	return message


class Nothing(ul.Outlook):
	"""Each test starts with the assistant on, the message open in Outlook with its HTML, and Word's object model with the
	hyperlinks of the message as Word has them (its own alt texts, so that which of the two named a link can be told)."""

	def setUp(self):
		super().setUp()
		self.turnOn()
		self.word = WordDocumentObject(
			Hyperlink("LOGO", alt="Word says: " + ALT_LOGO),
			Hyperlink("FILLER1", alt=ALT_FILLER),
			Hyperlink("TITLED", alt="", title="", tip="Follow us on Facebook"),
			Hyperlink("ONLYTITLE", alt="", title="A title and no alt text"),
			Hyperlink("TEXT1", kind=0),
		)

	def said(self, *runs, document=None):
		return super().said(*runs, document=document or messageIn(self.word))


# -- Finding the message -------------------------------------------------------------------------------------------------------


class ShownMessageTest(ul.Outlook):
	def setUp(self):
		super().setUp()
		self.other = Item(html="<p>other</p>", entryId="OTHER")
		self.other.Subject = "Re: Sale on candles"

	def shown(self, title, outlook, node=None):
		with mock.patch.dict(sys.modules, {"winUser": ul.winUser({ul.WINDOW: title})}):
			return unlabeledLinks.shownWhy(node or self.link("LOGO", nativeOm=outlook))

	def test_the_caption_of_the_window_is_the_title(self):
		item, how = self.shown(ul.TITLE, ul.ObjectModel(inspectors=[Inspector(ul.TITLE.strip(), self.item)]))
		self.assertIs(item, self.item)
		self.assertIn("caption", how)

	def test_the_caption_may_be_the_subject_alone(self):
		# Outlook may give an inspector's caption as the message's subject, the title as "Subject - Message (HTML)".
		item, how = self.shown(ul.TITLE, ul.ObjectModel(inspectors=[Inspector("Make it Pink", self.item)]))
		self.assertIs(item, self.item)
		self.assertIn("caption", how)

	def test_the_caption_may_be_nothing_like_the_title_while_the_subject_is(self):
		item, how = self.shown(ul.TITLE, ul.ObjectModel(inspectors=[Inspector("Untitled", self.item)]))
		self.assertIs(item, self.item)
		self.assertIn("subject", how)

	def test_the_subject_with_a_picture_character_in_it(self):
		# The tester's subject: "Make it Pink 💗 40% Off All Candles".
		self.item.Subject = "Make it Pink \U0001f497 40% Off All Candles"
		title = "Make it Pink \U0001f497 40% Off All Candles - Message (HTML) "
		item, _how = self.shown(title, ul.ObjectModel(inspectors=[Inspector("x", self.item)]))
		self.assertIs(item, self.item)

	def test_the_longer_subject_is_the_better_fit(self):
		outlook = ul.ObjectModel(inspectors=[Inspector("Re: Sale", self.item), Inspector("Re: Sale on candles", self.other)])
		self.item.Subject = "Re: Sale"
		self.assertIs(self.shown("Re: Sale on candles - Message (HTML)", outlook)[0], self.other)
		self.assertIs(self.shown("Re: Sale - Message (HTML)", outlook)[0], self.item)

	def test_an_inspector_that_cant_be_asked_does_not_hide_the_others(self):
		class Broken:
			@property
			def caption(self):
				raise ul.NoOutlook("busy")

		outlook = ul.ObjectModel(inspectors=[Broken(), Inspector(ul.TITLE.strip(), self.item)])
		self.assertIs(self.shown(ul.TITLE, outlook)[0], self.item)

	def test_a_message_window_no_caption_fits_is_the_one_in_front(self):
		outlook = FullObjectModel(inspectors=[Inspector("Untitled", self.other)], active=Inspector("Something else", self.item))
		item, how = self.shown(ul.TITLE, outlook)
		self.assertIs(item, self.item)
		self.assertIn("active", how)

	def test_a_message_window_with_nothing_to_go_by_falls_back_to_the_selection(self):
		outlook = FullObjectModel(inspectors=[], selected=[self.item], active=None)
		item, how = self.shown(ul.TITLE, outlook)
		self.assertIs(item, self.item)
		self.assertIn("selected", how)

	def test_the_main_window_has_the_reading_pane_which_shows_the_selected_message(self):
		outlook = FullObjectModel(inspectors=[Inspector("Untitled", self.other)], selected=[self.item], active=Inspector("x", self.other))
		for title in ("Inbox - someone@example.com - Outlook", "Inbox - Outlook", "Outlook"):
			with self.subTest(title=title):
				item, how = self.shown(title, outlook)
				self.assertIs(item, self.item)
				self.assertIn("selected", how)

	def test_which_windows_are_the_main_window(self):
		self.assertTrue(unlabeledLinks.isMainWindow("Inbox - someone@example.com - Outlook"))
		self.assertTrue(unlabeledLinks.isMainWindow("  OUTLOOK "))
		self.assertFalse(unlabeledLinks.isMainWindow("Make it Pink - Message (HTML) "))
		self.assertFalse(unlabeledLinks.isMainWindow(""))

	def test_why_it_could_not_be_found_is_said(self):
		node = self.link("LOGO", nativeOm=ul.ObjectModel(selected=[self.item, self.other]))
		item, how = self.shown("Inbox - someone@example.com - Outlook", node.appModule.nativeOm, node)
		self.assertIsNone(item)
		self.assertIn("2 messages selected", how)
		self.assertIn("Outlook's main window", how)
		noOutlook = self.link("LOGO")
		noOutlook.appModule = types.SimpleNamespace(appName="outlook", nativeOm=None)
		item, how = unlabeledLinks.shownWhy(noOutlook)
		self.assertIsNone(item)
		self.assertIn("no object model", how)

	def test_the_fit(self):
		fit = unlabeledLinks.fit
		self.assertEqual(fit("A - Message (HTML) ", "a - message (html)"), 1_000_000)
		self.assertGreater(fit("Re: Sale on candles - Message (HTML)", "Re: Sale on candles"), fit("Re: Sale on candles - Message (HTML)", "Re: Sale"))
		self.assertEqual(fit("Re: Sale on candles - Message (HTML)", "Re: Sal"), 0)
		self.assertEqual(fit("", "x"), 0)
		self.assertEqual(fit("x", ""), 0)
		self.assertEqual(fit(None, "x"), 0)


# -- Word's object model names a link --------------------------------------------------------------------------------------------


class NoHtmlTest(Nothing):
	"""Outlook's object model can't give the message (its window isn't found): Word's object model has the pictures."""

	def setUp(self):
		super().setUp()
		self.outlook = ul.ObjectModel(inspectors=[], selected=[])

	def link(self, query="LOGO", text="", **kwargs):
		kwargs.setdefault("nativeOm", self.outlook)
		return ul.Link(query, text, **kwargs)

	def test_a_picture_link_is_named_by_the_alt_text_word_has_for_its_picture(self):
		self.assertEqual(self.said(run(self.link("LOGO"))), ["link", "Word says: " + ALT_LOGO])
		self.assertEqual(self.said(run(self.link("FILLER1"))), ["link", ALT_FILLER])

	def test_a_picture_with_no_alt_text_is_named_by_its_title_then_the_screen_tip(self):
		self.assertEqual(self.said(run(self.link("ONLYTITLE"))), ["link", "A title and no alt text"])
		self.assertEqual(self.said(run(self.link("TITLED"))), ["link", "Follow us on Facebook"])

	def test_a_link_word_has_no_name_for_is_named_by_where_it_goes(self):
		self.assertEqual(self.said(run(self.link("NOSUCH"))), ["link", "click.shop.example"])

	def test_the_links_of_a_message_are_asked_of_word_once(self):
		for query in ("LOGO", "FILLER1", "NOSUCH", "LOGO"):
			self.said(run(self.link(query)))
		self.assertEqual(self.word.goneThrough(), 5, "each of the five links once, for the four names")

	def test_another_message_is_asked_again(self):
		self.said(run(self.link("LOGO")))
		other = WordDocumentObject(Hyperlink("LOGO", alt="The other message"))
		with mock.patch.dict(sys.modules, {"winUser": ul.winUser({ul.WINDOW: "Another - Message (HTML)"})}):
			self.assertEqual(self.said(run(self.link("LOGO")), document=messageIn(other)), ["link", "The other message"])
		self.assertEqual((self.word.goneThrough(), other.goneThrough()), (5, 1))

	def test_another_message_in_the_reading_pane_is_asked_again_though_the_window_is_the_same(self):
		# The reading pane's title is Outlook's main window's, whichever message it shows: its links say which message it is.
		with mock.patch.dict(sys.modules, {"winUser": ul.winUser({ul.WINDOW: "Inbox - someone@example.com - Outlook"})}):
			self.assertEqual(self.said(run(self.link("LOGO"))), ["link", "Word says: " + ALT_LOGO])
			other = WordDocumentObject(Hyperlink("LOGO", alt="The other message"), Hyperlink("PINK", alt="Another"))
			self.assertEqual(self.said(run(self.link("LOGO")), document=messageIn(other)), ["link", "The other message"])
			self.assertEqual(self.said(run(self.link("LOGO")), document=messageIn(self.word)), ["link", "Word says: " + ALT_LOGO])

	def test_a_link_with_text_is_not_named(self):
		self.assertEqual(self.said(run(self.link("LOGO", text="Unsubscribe"), "Unsubscribe")), ["link", "Unsubscribe"])
		self.assertEqual(self.word.asked, 0)

	def test_a_name_word_gives_the_link_is_said_and_word_is_not_asked(self):
		self.assertEqual(self.said(run(self.link("LOGO", name="Shop logo"))), ["link", "Shop logo"])
		self.assertEqual(self.word.asked, 0)

	def test_a_message_you_write_is_left_alone(self):
		self.assertEqual(self.said(run(self.link("LOGO")), document=messageIn(self.word, readOnly=False)), ["link"])
		self.assertEqual(self.word.asked, 0)

	def test_word_is_asked_from_nvdas_main_thread_only(self):
		spoken = []
		thread = threading.Thread(target=lambda: spoken.append(self.said(run(self.link("LOGO")))))
		thread.start()
		thread.join()
		self.assertEqual(spoken, [["link", "click.shop.example"]])
		self.assertEqual(self.word.asked, 0)

	def test_a_message_with_no_object_model_for_word_is_named_by_where_the_link_goes(self):
		message = messageIn(None)
		self.assertEqual(self.said(run(self.link("LOGO")), document=message), ["link", "click.shop.example"])

	def test_when_word_fails_the_link_is_named_by_where_it_goes_and_the_log_says_so_once(self):
		class Failing:
			@property
			def Hyperlinks(self):
				raise ul.NoOutlook("Word is busy")

		with self.assertLogs("nvda", level="DEBUG") as logged:
			for query in ("LOGO", "FILLER1"):
				self.assertEqual(self.said(run(self.link(query)), document=messageIn(Failing())), ["link", "click.shop.example"])
		failures = [line for line in logged.output if "Word's object model couldn't name the links" in line]
		self.assertEqual(len(failures), 1, logged.output)

	def test_a_link_word_cant_read_does_not_hide_the_others(self):
		class Broken:
			@property
			def Address(self):
				raise ul.NoOutlook("no address")

		links = WordDocumentObject(Broken(), Hyperlink("LOGO", alt=ALT_LOGO))
		self.assertEqual(self.said(run(self.link("LOGO")), document=messageIn(links)), ["link", ALT_LOGO])

	def test_the_first_link_to_an_address_that_has_a_name_names_it(self):
		links = WordDocumentObject(Hyperlink("LOGO", alt=""), Hyperlink("LOGO", alt="Second"), Hyperlink("LOGO", alt="Third"))
		self.assertEqual(self.said(run(self.link("LOGO")), document=messageIn(links)), ["link", "Second"])

	def test_the_name_is_noted_in_the_field_as_word(self):
		info = ul.base.WordDocumentTextInfo(messageIn(self.word))
		field = info._getControlFieldForUIAObject(self.link("LOGO"))
		self.assertEqual(field["content"], "Word says: " + ALT_LOGO)
		self.assertEqual(field[unlabeledLinks.NAMED_BY], "word")

	def test_the_elements_list_says_it_too(self):
		item = self.listItem(self.link("LOGO"), document=messageIn(self.word))
		self.assertEqual(item.label, "Word says: " + ALT_LOGO)


class HtmlFirstTest(Nothing):
	"""The message's HTML is the sender's own words, and is used before Word's object model, which isn't asked then."""

	def test_the_html_names_the_link_and_word_is_not_asked(self):
		self.assertEqual(self.said(run(self.link("LOGO"))), ["link", ALT_LOGO])
		self.assertEqual(self.word.asked, 0)

	def test_a_link_the_html_has_no_name_for_is_named_by_word(self):
		self.assertEqual(self.said(run(self.link("ONLYTITLE", nativeOm=self.outlook))), ["link", "A title and no alt text"])
		self.assertEqual(self.word.asked, 1)

	def test_the_field_says_where_the_name_came_from(self):
		info = ul.base.WordDocumentTextInfo(messageIn(self.word))
		for query, kind in (("LOGO", "html"), ("ONLYTITLE", "word"), ("NOSUCH", "address")):
			with self.subTest(query=query):
				field = info._getControlFieldForUIAObject(self.link(query))
				self.assertEqual(field[unlabeledLinks.NAMED_BY], kind)
		field = info._getControlFieldForUIAObject(self.link("LOGO", name="Shop logo"))
		self.assertEqual(field[unlabeledLinks.NAMED_BY], "name")


# -- Pictures Word's object model is asked about ------------------------------------------------------------------------------------


class ThePicturesTest(pictures.Isolated):
	"""outlookPictures, which asks Word's object model for the picture at the start of a line (1.44), with the assistant's names
	for links with no text (unlabeledLinks, 1.49) on: a link named from the message isn't asked about."""

	def setUp(self):
		super().setUp()
		for patch in (
			mock.patch.dict(sys.modules, {"winUser": ul.winUser({ul.WINDOW: ul.TITLE})}),
			mock.patch.object(unlabeledLinks, "_messages", unlabeledLinks.collections.OrderedDict()),
			mock.patch.object(unlabeledLinks, "_wordMessages", unlabeledLinks.collections.OrderedDict()),
			mock.patch.object(unlabeledLinks, "_noted", set()),
			mock.patch.object(unlabeledLinks, "_failed", False),
			mock.patch.object(unlabeledLinks, "_retryAt", 0.0),
		):
			patch.start()
			self.addCleanup(patch.stop)
		self.outlook = ul.ObjectModel(inspectors=[Inspector(ul.TITLE.strip(), Item())])
		outlookPictures.register()
		self.message = pictures.Message()

	def lineOf(self, query, how):
		"""A line with a link that has no text, as it is in the tester's logs, named as it is when NVDA makes its field: from the
		message's HTML ("html"), or only by where it goes ("address")."""
		field = pictures.hyperlink(1)
		link = ul.Link(query, nativeOm=self.outlook)
		if how == "address":
			link = ul.Link("NOSUCH", nativeOm=self.outlook)
		self.assertTrue(outlookMessages.nameLinkWithNoText(types.SimpleNamespace(obj=ul.Message()), link, field, link.value))
		self.assertEqual(field[unlabeledLinks.NAMED_BY], how)
		return pictures.Line([("start", field), ("format", pictures.FormatField()), "", ("end", None)])

	def test_a_link_named_from_the_html_is_said_and_word_is_not_asked(self):
		self.message.document.picture(alt="Something else")
		self.assertEqual(self.say(self.message, self.lineOf("LOGO", "html")), ["link", ALT_LOGO])
		self.assertEqual(self.message.WinwordWindowObject.asked, [])

	def test_a_link_named_only_by_where_it_goes_has_the_picture_asked_of_word(self):
		self.message.document.picture(alt="Make it Pink")
		self.assertEqual(self.say(self.message, self.lineOf("LOGO", "address")), ["link", "click.shop.example", "graphic", "Make it Pink"])
		self.assertEqual(len(self.message.WinwordWindowObject.asked), 1)

	def test_a_link_with_a_name_nobody_noted_is_as_in_1_44(self):
		# Another add-on names the link: Word is asked, and the picture's text is said if it isn't the name.
		self.message.document.picture(alt="Shop Now")
		named = pictures.hyperlink(1)
		named["content"] = "Shop Now"
		line = pictures.Line([("start", named), ("format", pictures.FormatField()), "", ("end", None)])
		self.assertEqual(self.say(self.message, line), ["link", "Shop Now"])
		self.assertEqual(len(self.message.WinwordWindowObject.asked), 1)

	def test_the_log_says_what_was_asked_of_word_and_what_it_held(self):
		# The tester's log said only that Word had no text for the picture: not whether it found the picture. Now: the point on the
		# screen, Word's range there, and what is in each range looked at, without the text.
		self.message.document.picture(alt="", title="", at=(20, 10))
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.say(self.message, pictures.linkedPicture(1, at=(20, 10)))
		note = [line for line in logged.output if "no alternative text for the picture" in line]
		self.assertEqual(len(note), 1, logged.output)
		self.assertIn("start LINK, '', end", note[0])
		self.assertIn("asked at the point 20,10 of the screen", note[0])
		self.assertIn("Word's range there is range 2-2: 0 pictures, 0 links", note[0])
		self.assertIn("range 2-3: 1 pictures (the first of kind ", note[0])
		self.assertIn("alt text 0 characters, title 0)", note[0])

	def test_the_log_says_when_word_had_no_picture_there(self):
		# Not the same as a picture with no text: the point was not on a picture.
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.say(self.message, pictures.linkedPicture(1, at=(500, 500)))
		note = [line for line in logged.output if "no alternative text for the picture" in line]
		self.assertEqual(len(note), 1, logged.output)
		self.assertIn("Word's range there is range 10000-10000: 0 pictures", note[0])

	def test_what_was_asked_of_word_is_looked_at_only_for_the_notes_that_are_said(self):
		with mock.patch.object(outlookPictures, "_asking", return_value="x") as asking:
			for index in range(40):
				self.say(self.message, pictures.linkedPicture(index))
		self.assertEqual(asking.call_count, outlookPictures._MOST_NOTES)


# -- What the log says ------------------------------------------------------------------------------------------------------------


class LogTest(Nothing):
	def test_the_html_of_the_message_is_described_once_without_its_addresses(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			for query in ("LOGO", "PINK", "FILLER1", "LOGO"):
				self.said(run(self.link(query)))
		notes = [line for line in logged.output if "read the HTML of an Outlook message from Outlook" in line]
		self.assertEqual(len(notes), 1, logged.output)
		note = notes[0]
		self.assertIn("found by the caption of its window", note)
		self.assertIn("15 links", note)
		self.assertIn("with no text", note)
		self.assertIn("click.shop.example x", note)
		self.assertNotIn("qs=", note)
		self.assertNotIn("https://", note)
		self.assertNotIn(ALT_LOGO, note)

	def test_why_the_message_was_not_found_is_said_once(self):
		outlook = ul.ObjectModel(inspectors=[], selected=[])
		with self.assertLogs("nvda", level="DEBUG") as logged:
			for query in ("LOGO", "PINK"):
				self.said(run(self.link(query, nativeOm=outlook)))
		notes = [line for line in logged.output if "can't be named from the message's HTML" in line]
		self.assertEqual(len(notes), 1, logged.output)
		self.assertIn("no open message has a caption or a subject that fits the window's title", notes[0])
		self.assertIn("0 messages selected", notes[0])

	def test_a_message_that_is_not_html_is_said_once(self):
		self.item.BodyFormat = 1
		with self.assertLogs("nvda", level="DEBUG") as logged:
			for query in ("LOGO", "PINK"):
				self.said(run(self.link(query)))
		notes = [line for line in logged.output if "the message is not HTML" in line]
		self.assertEqual(len(notes), 1, logged.output)
		self.assertIn("body format is 1", notes[0])

	def test_what_word_held_is_said_once_without_its_addresses(self):
		outlook = ul.ObjectModel(inspectors=[], selected=[])
		with self.assertLogs("nvda", level="DEBUG") as logged:
			for query in ("LOGO", "FILLER1", "NOSUCH"):
				self.said(run(self.link(query, nativeOm=outlook)))
		notes = [line for line in logged.output if "asked Word's object model for the links of an Outlook message" in line]
		self.assertEqual(len(notes), 1, logged.output)
		self.assertIn("Word has 5 hyperlinks: 4 around a picture, 4 of those with the picture in Word's range, 3 with alt text or a title, and 4 with a name", notes[0])
		self.assertNotIn("qs=", notes[0])

	def test_where_a_name_was_lost_is_said_once_for_each_site(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			for query in ("NOSUCH", "NOSUCH2"):
				self.said(run(self.link(query)))
		notes = [line for line in logged.output if "was found in its HTML or in Word's object model" in line]
		self.assertEqual(len(notes), 1, logged.output)
		self.assertIn("click.shop.example", notes[0])
		self.assertNotIn("qs=", notes[0])


class LinkFactsTest(Nothing):
	def test_what_ui_automation_gives_for_the_first_link_is_said_once_without_its_text(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			for query in ("LOGO", "PINK"):
				self.said(run(self.link(query)))
		notes = [line for line in logged.output if "the first link with no text of an Outlook message" in line]
		self.assertEqual(len(notes), 1, logged.output)
		self.assertIn("its value is %d characters (https)" % len(address("LOGO")), notes[0])
		self.assertIn("its name empty", notes[0])
		self.assertNotIn("qs=", notes[0])

	def test_the_facts_are_asked_of_ui_automation_once(self):
		reads = []

		class Counting(ul.Link):
			@property
			def helpText(self):
				reads.append(1)
				return ""

		for query in ("LOGO", "PINK", "FILLER1"):
			self.said(run(Counting(query, nativeOm=self.outlook)))
		self.assertEqual(len(reads), 1)

	def test_a_link_with_no_address_is_said_to_have_none(self):
		# The tester's Outlook may give no value for a link: then it can't be found in the HTML, and the log says so.
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.assertEqual(self.said(run(self.link(value=""))), ["link"])
		facts = [line for line in logged.output if "the first link with no text" in line]
		self.assertIn("its value is empty (none)", facts[0])
		missed = [line for line in logged.output if "was found in its HTML or in Word's object model" in line]
		self.assertEqual(len(missed), 1, logged.output)
		self.assertIn("(none)", missed[0])

	def test_the_kind_of_address(self):
		for address_, kind in (("https://x.example/", "https"), ("MAILTO:a@b.example", "mailto"), ("cid:image001", "cid"), ("#top", "no scheme"), ("", "none"), (None, "none")):
			with self.subTest(address=address_):
				self.assertEqual(unlabeledLinks.schemeOf(address_), kind)


class SettingTest(unittest.TestCase):
	def test_it_is_still_part_of_saying_outlook_messages_as_jaws_does(self):
		self.assertTrue(outlookMessages.wanted({}))
		self.assertFalse(outlookMessages.wanted({outlookMessages.STATE_KEY: False}))


if __name__ == "__main__":
	unittest.main()
