# Unit tests for version 1.49, from a tester's report (issue 46, "NVDA and unlabeled links in a email"): "Jaws reads
# unlabeled links properly. It is able to determine the link. NVDA can't." The tester attached a promotional message
# (a candle shop's newsletter). Its HTML has thirty links, twenty of which hold only a picture, such as
#   <a href="https://click.shop.example/?qs=..."><img alt="Pink Pumpkin ... on a pink background"></a>
# (six of the pictures have the alt text "Display images to show real-time content"), two are to e-mail addresses. The
# NVDA log the tester attached to issue 42, from the same message opened in classic Outlook 16.0.20326 (UI Automation),
# shows NVDA saying "link" and nothing more for each, going down the message: "link", "blank", "link", "blank"... and
# "link", "Web Browser" for a link with text. NVDA's Elements List would label each "Unlabeled"
# (browseMode.TextInfoQuickNavItem._getLabelForProperties). JAWS's own settings (Default.JCF) list all graphical links,
# name a picture by its alt text before its title, and name a graphical link with neither by its source or where it goes.
# - unlabeledLinks: the links of a message's HTML, the names they give, where a link goes, and the choice among them.
# - outlookMessages: a link with no text in a message you read has a name NVDA says, from Outlook's object model for the
#   message shown; the Elements List and Links List show it in the place of "Unlabeled".
# The imitation NVDA is test_v125_outlookMessages': NVDA 2026.2's own code, word for word, for the fields of Word's text
# and their speech, and for the Elements List's label. The assistant's code is the real one. Outlook is an imitation of
# its object model (Application.Inspectors, ActiveExplorer, MailItem.HTMLBody): classic Outlook isn't on the computer
# these were written on, so nothing here was run in Outlook; the tester's message was read as data, never opened.
# Run: python -m unittest tests.test_v149_unlabeledLinks -v

import os
import sys
import threading
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import test_v125_outlookMessages as base  # noqa: E402
import test_v144_outlookPictures as pictures  # noqa: E402

from jawsMigrator import outlookMessages, outlookPictures, unlabeledLinks  # noqa: E402

UIAHandler, Role, State, OutputReason = base.UIAHandler, base.Role, base.State, base.OutputReason

#: NVDA 2026.2, source/browseMode.py, TextInfoQuickNavItem._getLabelForProperties, word for word.
NVDA_LABEL_FOR_PROPERTIES = r'''
def _getLabelForProperties(self, labelPropertyGetter: Callable[[str], Any]):
	content = self.textInfo.text.strip()
	if self.itemType == "heading":
		# Output: displayed text of the heading.
		return content
	labelParts = None
	name = labelPropertyGetter("name")
	if self.itemType == "landmark":
		landmark = aria.landmarkRoles.get(labelPropertyGetter("landmark"))
		# Example output: main menu; navigation
		labelParts = (name, landmark)
	else:
		role: controlTypes.Role | int = labelPropertyGetter("role")
		role = controlTypes.Role(role)
		roleText = role.displayString
		# Translators: Reported label in the elements list for an element which which has no name and value
		unlabeled = _("Unlabeled")
		realStates = labelPropertyGetter("states")
		labeledStates = " ".join(controlTypes.processAndLabelStates(role, realStates, OutputReason.FOCUS))
		if self.itemType == "formField":
			if role in (
				controlTypes.Role.BUTTON,
				controlTypes.Role.DROPDOWNBUTTON,
				controlTypes.Role.TOGGLEBUTTON,
				controlTypes.Role.SPLITBUTTON,
				controlTypes.Role.MENUBUTTON,
				controlTypes.Role.DROPDOWNBUTTONGRID,
				controlTypes.Role.TREEVIEWBUTTON,
			):
				# Example output: Mute; toggle button; pressed
				labelParts = (content or name or unlabeled, roleText, labeledStates)
			else:
				# Example output: Find a repository...; edit; has auto complete; NVDA
				labelParts = (name or unlabeled, roleText, labeledStates, content)
		elif self.itemType in ("link", "button"):
			# Example output: You have unread notifications; visited
			labelParts = (content or name or unlabeled, labeledStates)
	if labelParts:
		label = "; ".join(lp for lp in labelParts if lp)
	else:
		label = content
	return label
'''

#: NVDA 2026.2, source/UIAHandler/browseMode.py, UIATextRangeQuickNavItem.label, word for word.
NVDA_UIA_LABEL = r'''
@property
def label(self):
	return self._getLabelForProperties(lambda prop: getattr(self.obj, prop, None))
'''

#: The message's HTML as the tester's has it, with the shop and its tracking addresses made up: a link of text, links
#: that hold a picture with alt text, the same filler alt text six times, a picture with no alt text, a link with a title
#: only, a link that holds nothing, links of text, and a link to an e-mail address that holds nothing.
SHOP = "https://click.shop.example/"
ALT_LOGO = "Shop logo in gray centered on a white background."
ALT_FILLER = "Display images to show real-time content"
ALT_BARCODE = "Expires 9/30/26. Show barcode for 40 percent off in-store. Barcode with number 260930200."
MESSAGE_HTML = f"""<!DOCTYPE html><html><head><title>Shop</title><style>a {{ color: #4d508e }}</style>
<script>var x = '<a href="{SHOP}?qs=SCRIPT"></a>';</script></head><body>
<p><a href="{SHOP}?qs=TEXT1" name="top">+ Take 50% off fall &amp; Halloween accessories</a></p>
<table role="presentation"><tr><td align="center">
<a href="{SHOP}?qs=LOGO" target="_blank" style="color:#666"><img src="https://image.shop.example/a.jpg" alt="{ALT_LOGO}" width="600"></a>
</td></tr><tr><td>
<a href="{SHOP}?qs=PINK"><img src="https://image.shop.example/b.gif" alt="Text says Pink is the new orange,
   40% off all candles."></a>
<a href="{SHOP}?qs=FILLER1"><img src="https://image.shop.example/us_em_prsw_40PrctOffCandles_1.gif" alt="{ALT_FILLER}"></a>
<a href="{SHOP}?qs=FILLER2"><img src="https://image.shop.example/us_em_prsw_40PrctOffCandles_2.gif" alt="{ALT_FILLER}"></a>
<a href="{SHOP}?qs=NOALT"><img src="https://image.shop.example/c.gif"></a>
<a href="{SHOP}?qs=TITLED" title="Follow us on Facebook"><img src="https://image.shop.example/d.gif" alt=""></a>
<a href="{SHOP}?qs=EMPTY"></a>
<a href="{SHOP}?qs=BARCODE"><img src="https://image.shop.example/e.jpg" alt="{ALT_BARCODE}"></a>
<a href="{SHOP}?qs=SPACES">&nbsp;<span> </span></a>
<a href="{SHOP}?qs=WITHTEXT"><img src="https://image.shop.example/f.jpg" alt="Not said: the link has text">Unsubscribe</a>
<a href="mailto:reply@shop.example"></a>
<a href="{SHOP}?qs=SAME"><img src="https://image.shop.example/g.gif" alt="First of two pictures to one address"></a>
<a href="{SHOP}?qs=SAME"><img src="https://image.shop.example/h.gif" alt="Second of two"></a>
<a href="{SHOP}?qs=HIDDEN" style="display:none"><img alt="{ALT_FILLER}"></a>
</td></tr></table></body></html>"""

#: Where a link goes: the address in the message, for the links above, as Word gives it as the link's value.
def address(query):
	return f"{SHOP}?qs={query}"


class NoOutlook(Exception):
	"""An Outlook object model call that fails, as a COMError does."""


class Item:
	"""Outlook's MailItem, as far as the assistant asks: its HTML, its format and its EntryID. Counts how often the HTML is read."""

	def __init__(self, html=MESSAGE_HTML, entryId="ENTRY1", bodyFormat=unlabeledLinks.OL_FORMAT_HTML):
		self._html, self.EntryID, self.BodyFormat = html, entryId, bodyFormat
		self.reads = 0
		self.Subject, self.ReceivedTime = "Make it Pink", "Tue 9/29/2026 8:35 AM"

	@property
	def HTMLBody(self):
		self.reads += 1
		return self._html


class Collection:
	"""Outlook's Inspectors or Selection: a count and item(n), counting from 1."""

	def __init__(self, *members):
		self._members = list(members)
		self.count = len(self._members)

	def item(self, index):
		return self._members[index - 1]


class Inspector:
	def __init__(self, caption, item):
		self.caption, self.currentItem = caption, item


class Explorer:
	def __init__(self, *selected):
		self.selection = Collection(*selected)


class ObjectModel:
	"""Outlook's Application, which NVDA's Outlook support keeps as the app module's nativeOm."""

	def __init__(self, inspectors=(), selected=()):
		self.inspectors = Collection(*inspectors)
		self._explorer = Explorer(*selected)
		self.asked = 0

	def activeExplorer(self):
		self.asked += 1
		return self._explorer


class FailingObjectModel:
	"""An Outlook that answers every question with an error."""

	def __init__(self):
		self.asked = 0

	@property
	def inspectors(self):
		self.asked += 1
		raise NoOutlook("Outlook is busy")

	def activeExplorer(self):
		self.asked += 1
		raise NoOutlook("Outlook is busy")


TITLE = "Make it Pink - Message (HTML) "
WINDOW = 4242


def winUser(titles):
	"""NVDA's winUser, as far as the assistant asks: the top window of a window, and a window's title."""
	module = types.ModuleType("winUser")
	module.GA_ROOT = 2
	module.getAncestor = lambda hwnd, flags: hwnd
	module.getWindowText = lambda hwnd: titles.get(hwnd, "")
	return module


class Pattern:
	"""UI Automation's text pattern of the document: the range of a child element, which has its text."""

	def rangeFromChild(self, element):
		return types.SimpleNamespace(getText=lambda most: element.text[:most])


class Message(base.Document):
	"""The Outlook message: NVDA's object for the Word document, which a link's text is asked of."""

	UIATextPattern = Pattern()


class Link(base.Node):
	"""NVDA's object for a link in Word's text: its address as the value, Word's name for it, its text and its window."""

	def __init__(self, query=None, text="", name="", appName="outlook", nativeOm=None, runtimeId=(42, 1), value=None, states=()):
		super().__init__(address(query) if value is None else value, appName=appName, name=name, runtimeId=runtimeId)
		self.windowHandle = WINDOW
		self.UIAElement.text = text
		self._linkStates = set(states)
		if nativeOm is not None:
			self.appModule.nativeOm = nativeOm

	@property
	def states(self):
		return set(self._linkStates)


def run(link, text=""):
	return base.Run(text, UIAHandler.StyleId_Custom, "Hyperlink", link=link)


class Outlook(base.Isolated):
	"""Each test starts with the assistant off, Outlook with the message open in a window of its own, and nothing read."""

	def setUp(self):
		super().setUp()
		self.item = Item()
		self.outlook = ObjectModel(inspectors=[Inspector(TITLE.strip(), self.item)])
		for patch in (
			mock.patch.dict(sys.modules, {"winUser": winUser({WINDOW: TITLE})}),
			mock.patch.object(unlabeledLinks, "_messages", unlabeledLinks.collections.OrderedDict()),
			mock.patch.object(unlabeledLinks, "_wordMessages", unlabeledLinks.collections.OrderedDict()),
			mock.patch.object(unlabeledLinks, "_noted", set()),
			mock.patch.object(unlabeledLinks, "_failed", False),
			mock.patch.object(unlabeledLinks, "_retryAt", 0.0),
		):
			patch.start()
			self.addCleanup(patch.stop)
		self.quickNavItem = self.makeQuickNavItemClass()
		uiaBrowseMode = types.ModuleType("UIAHandler.browseMode")
		uiaBrowseMode.UIATextRangeQuickNavItem = self.quickNavItem
		sys.modules["UIAHandler.browseMode"] = uiaBrowseMode
		self.original = vars(self.quickNavItem)["label"]

	def makeQuickNavItemClass(self):
		# controlTypes.processAndLabelStates gives the labels of the states it is given, here their words.
		controlTypes = types.SimpleNamespace(
			Role=Role,
			processAndLabelStates=lambda role, states, reason: [state.displayString for state in sorted(states, key=lambda state: state.name)],
		)
		label = base.nvdaCode(
			NVDA_LABEL_FOR_PROPERTIES,
			"_getLabelForProperties",
			{
				"controlTypes": controlTypes,
				"OutputReason": OutputReason,
				"aria": types.SimpleNamespace(landmarkRoles={}),
				"_": base._,
				"Callable": base.typing.Callable,
				"Any": base.typing.Any,
			},
		)
		return type("UIATextRangeQuickNavItem", (), {
			"_getLabelForProperties": label,
			"label": base.nvdaCode(NVDA_UIA_LABEL, "label", {}),
			# UIATextRangeQuickNavItem.obj: the NVDA object of the link; a callable stands for one the document took away.
			"obj": property(lambda self: self._link() if callable(self._link) else self._link),
		})

	def link(self, query="LOGO", text="", **kwargs):
		kwargs.setdefault("nativeOm", self.outlook)
		return Link(query, text, **kwargs)

	def said(self, *runs, document=None):
		return self.nvda.speakLine(document or Message(), list(runs))

	def listItem(self, link, text="", itemType="link", document=None):
		"""An element of NVDA's Elements List (UIATextRangeQuickNavItem): the link, and the text it has."""
		item = self.quickNavItem()
		item.itemType = itemType
		item.textInfo = types.SimpleNamespace(text=text)
		item.document = types.SimpleNamespace(rootNVDAObject=document or Message())
		item._link = link
		return item


class NvdaAloneTest(Outlook):
	def test_nvda_says_link_and_nothing_more_for_a_link_with_no_text(self):
		# The tester's log: "link", going down the message.
		self.assertEqual(self.said(run(self.link("LOGO"))), ["link"])

	def test_nvda_says_the_text_of_a_link_that_has_some(self):
		self.assertEqual(self.said(run(self.link("TEXT1"), "Web Browser")), ["link", "Web Browser"])

	def test_nvdas_elements_list_says_unlabeled(self):
		self.assertEqual(self.listItem(self.link("LOGO")).label, "Unlabeled")


class SpeechTest(Outlook):
	def setUp(self):
		super().setUp()
		self.turnOn()

	def test_a_picture_link_is_named_by_its_alt_text(self):
		self.assertEqual(self.said(run(self.link("LOGO"))), ["link", ALT_LOGO])

	def test_alt_text_on_two_lines_is_said_on_one(self):
		self.assertEqual(self.said(run(self.link("PINK"))), ["link", "Text says Pink is the new orange, 40% off all candles."])

	def test_the_filler_alt_text_is_said_as_jaws_says_a_pictures_alt_text(self):
		self.assertEqual(self.said(run(self.link("FILLER1"))), ["link", ALT_FILLER])

	def test_a_long_alt_text_is_said_in_full(self):
		self.assertEqual(self.said(run(self.link("BARCODE"))), ["link", ALT_BARCODE])

	def test_a_title_names_a_picture_with_no_alt_text(self):
		self.assertEqual(self.said(run(self.link("TITLED"))), ["link", "Follow us on Facebook"])

	def test_a_picture_with_no_alt_text_and_no_title_is_named_by_where_it_goes(self):
		self.assertEqual(self.said(run(self.link("NOALT"))), ["link", "click.shop.example"])

	def test_a_link_that_holds_nothing_is_named_by_where_it_goes(self):
		self.assertEqual(self.said(run(self.link("EMPTY"))), ["link", "click.shop.example"])

	def test_a_link_of_spaces_or_a_pictures_place_is_a_link_with_no_text(self):
		# What Word's range of a link holds: a picture's place is the object replacement character.
		for text in (" ", "\U0000fffc", "\U000000a0\U0000200b", "\r\x07"):
			with self.subTest(text=text):
				self.assertEqual(self.said(run(self.link("SPACES", text=text))), ["link", "click.shop.example"])

	def test_a_link_with_text_is_said_as_before(self):
		# The link holds a picture with alt text and the word "Unsubscribe": its text is said, as NVDA says it.
		self.assertEqual(self.said(run(self.link("WITHTEXT", text="Unsubscribe"), "Unsubscribe")), ["link", "Unsubscribe"])
		self.assertEqual(self.said(run(self.link("TEXT1", text="Web Browser"), "Web Browser")), ["link", "Web Browser"])

	def test_a_link_to_an_e_mail_address_with_no_text_is_named_by_the_address(self):
		self.assertEqual(
			self.said(run(self.link(value="mailto:reply@shop.example"))),
			["send mail link", "reply@shop.example"],
		)

	def test_the_first_picture_to_an_address_names_it(self):
		self.assertEqual(self.said(run(self.link("SAME"))), ["link", "First of two pictures to one address"])

	def test_a_link_the_message_doesnt_have_is_named_by_where_it_goes(self):
		self.assertEqual(self.said(run(self.link("NOSUCH"))), ["link", "click.shop.example"])

	def test_the_address_is_found_however_it_is_spelled(self):
		# Word gives the address with a slash at the end, or with percent-escapes.
		self.assertEqual(self.said(run(self.link(value=address("LOGO") + "/"))), ["link", ALT_LOGO])
		self.assertEqual(self.said(run(self.link(value=address("LO%47O")))), ["link", ALT_LOGO])

	def test_the_name_is_in_the_field_for_braille_and_for_quick_navigation(self):
		info = base.WordDocumentTextInfo(Message())
		field = info._getControlFieldForUIAObject(self.link("LOGO"))
		self.assertEqual(field["content"], ALT_LOGO)
		# Quick navigation says a link's content first, and "link" after it, as it says a link's text.
		# (NVDA drops the empty strings its field speech leaves, speech.speak.)
		spoken = lambda fieldType, reason: [x for x in base.getControlFieldSpeech(field, [], fieldType, base.config.conf["documentFormatting"], False, reason) if x != ""]
		self.assertEqual(spoken("end_relative", OutputReason.QUICKNAV), [ALT_LOGO, "link"])
		self.assertEqual(spoken("start_addedToControlFieldStack", OutputReason.CARET), ["link", ALT_LOGO])

	def test_a_name_word_gives_the_link_is_said(self):
		self.assertEqual(self.said(run(self.link("LOGO", name="Shop logo"))), ["link", "Shop logo"])
		self.assertEqual(self.item.reads, 0, "Outlook isn't asked when Word names the link")

	def test_an_address_as_a_name_is_no_name(self):
		self.assertEqual(self.said(run(self.link("LOGO", name=address("LOGO")))), ["link", ALT_LOGO])

	def test_links_off_in_nvda_say_nothing(self):
		base.config.conf["documentFormatting"]["reportLinks"] = False
		self.assertEqual(self.said(run(self.link("LOGO"))), [])


class OutlookTest(Outlook):
	def setUp(self):
		super().setUp()
		self.turnOn()

	def test_the_message_is_read_from_outlook_once(self):
		for query in ("LOGO", "PINK", "FILLER1", "FILLER2", "NOALT", "LOGO"):
			self.said(run(self.link(query)))
		self.assertEqual(self.item.reads, 1)

	def test_another_message_is_read_again(self):
		other = Item(html=f'<a href="{address("LOGO")}"><img alt="The other message"></a>', entryId="ENTRY2")
		self.assertEqual(self.said(run(self.link("LOGO"))), ["link", ALT_LOGO])
		self.outlook.inspectors = Collection(Inspector(TITLE.strip(), other))
		self.assertEqual(self.said(run(self.link("LOGO"))), ["link", "The other message"])

	def test_the_message_in_the_reading_pane_is_the_one_selected(self):
		# The window is Outlook's main window, which has no inspector: the message list's one selected message.
		outlook = ObjectModel(selected=[self.item])
		with mock.patch.dict(sys.modules, {"winUser": winUser({WINDOW: "Inbox - someone@example.com - Outlook"})}):
			self.assertEqual(self.said(run(self.link("LOGO", nativeOm=outlook))), ["link", ALT_LOGO])

	def test_with_two_messages_selected_the_reading_pane_is_not_asked(self):
		outlook = ObjectModel(selected=[self.item, Item(entryId="ENTRY2")])
		with mock.patch.dict(sys.modules, {"winUser": winUser({WINDOW: "Inbox - someone@example.com - Outlook"})}):
			self.assertEqual(self.said(run(self.link("LOGO", nativeOm=outlook))), ["link", "click.shop.example"])

	def test_a_message_window_is_found_by_its_title_among_others(self):
		other = Item(html=f'<a href="{address("LOGO")}"><img alt="Not this one"></a>', entryId="ENTRY2")
		self.outlook.inspectors = Collection(Inspector("Another - Message (HTML)", other), Inspector(TITLE.strip(), self.item))
		self.assertEqual(self.said(run(self.link("LOGO"))), ["link", ALT_LOGO])

	def test_a_plain_text_message_is_named_by_where_the_link_goes(self):
		self.item.BodyFormat = 1
		self.assertEqual(self.said(run(self.link("LOGO"))), ["link", "click.shop.example"])
		self.assertEqual(self.item.reads, 0)

	def test_no_object_model_names_a_link_by_where_it_goes(self):
		# NVDA has no handle on Outlook (appModule.nativeOm is None, or it has none).
		for appModule in (types.SimpleNamespace(appName="outlook", nativeOm=None), types.SimpleNamespace(appName="outlook")):
			with self.subTest(appModule=appModule):
				node = Link("LOGO")
				node.appModule = appModule
				self.assertEqual(self.said(run(node)), ["link", "click.shop.example"])

	def test_when_outlook_fails_the_link_is_named_by_where_it_goes_and_outlook_is_left_alone_for_a_while(self):
		outlook = FailingObjectModel()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			for query in ("LOGO", "PINK", "FILLER1"):
				self.assertEqual(self.said(run(self.link(query, nativeOm=outlook))), ["link", "click.shop.example"])
		warnings = [line for line in logged.output if "can't read the links of an Outlook message from Outlook" in line]
		self.assertEqual(len(warnings), 1, logged.output)
		self.assertEqual(outlook.asked, 1, "Outlook was asked once, not for each link")

	def test_outlook_is_asked_again_after_a_while(self):
		outlook = FailingObjectModel()
		self.said(run(self.link("LOGO", nativeOm=outlook)))
		with mock.patch.object(unlabeledLinks.time, "monotonic", return_value=unlabeledLinks._retryAt + 1):
			self.said(run(self.link("LOGO", nativeOm=outlook)))
		self.assertEqual(outlook.asked, 2)

	def test_outlook_is_asked_from_nvdas_main_thread_only(self):
		spoken = []
		thread = threading.Thread(target=lambda: spoken.append(self.said(run(self.link("LOGO")))))
		thread.start()
		thread.join()
		self.assertEqual(spoken, [["link", "click.shop.example"]])
		self.assertEqual((self.item.reads, self.outlook.asked), (0, 0))
		self.assertEqual(self.said(run(self.link("LOGO"))), ["link", ALT_LOGO], "the main thread isn't held back afterwards")

	def test_the_debug_log_names_each_kind_of_name_once_and_the_site_only(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.said(run(self.link("LOGO")))
			self.said(run(self.link("PINK")))
			self.said(run(self.link("NOALT")))
			self.said(run(self.link("EMPTY")))
		notes = [line for line in logged.output if "is named, as JAWS names one" in line]
		self.assertEqual(len(notes), 2, logged.output)
		self.assertIn("alt text or title", notes[0])
		self.assertIn("where it goes", notes[1])
		self.assertTrue(all("click.shop.example" in line and "qs=" not in line for line in notes), notes)

	def test_the_text_of_a_link_that_cant_be_read_is_left_as_nvda_has_it(self):
		message = Message()
		message.UIATextPattern = types.SimpleNamespace(rangeFromChild=mock.Mock(side_effect=NoOutlook("no range")))
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.assertEqual(self.said(run(self.link("LOGO")), document=message), ["link"])
		self.assertTrue(any("can't read the text of a link in an Outlook message" in line for line in logged.output), logged.output)

	def test_a_link_whose_text_cant_be_read_does_not_keep_outlook_from_the_next(self):
		# Only this link's text failed: Outlook is fine, and the next link, whose text can be read, is named.
		message = Message()
		message.UIATextPattern = types.SimpleNamespace(rangeFromChild=mock.Mock(side_effect=NoOutlook("no range")))
		self.assertEqual(self.said(run(self.link("LOGO")), document=message), ["link"])
		self.assertEqual(self.said(run(self.link("LOGO"))), ["link", ALT_LOGO])


class NotOutlookMessageTest(Outlook):
	def setUp(self):
		super().setUp()
		self.turnOn()

	def test_word_is_as_before(self):
		document = Message("winword")
		self.assertEqual(self.said(run(self.link("LOGO", appName="winword")), document=document), ["link"])

	def test_a_message_you_write_is_as_before(self):
		self.assertEqual(self.said(run(self.link("LOGO")), document=Message(readOnly=False)), ["link"])

	def test_turned_off_nvda_says_link_as_it_does(self):
		outlookMessages.unregister()
		self.assertEqual(self.said(run(self.link("LOGO"))), ["link"])

	def test_a_footnote_is_a_link_with_its_name_as_before(self):
		info = base.WordDocumentTextInfo(Message())
		field = info._getControlFieldForUIAObject(base.Node(None, controlType=UIAHandler.UIA_CustomControlTypeId, role=Role.UNKNOWN, name="1"))
		self.assertEqual(field["role"], Role.LINK)
		self.assertEqual(field["content"], "1")


class ElementsListTest(Outlook):
	def setUp(self):
		super().setUp()
		self.turnOn()
		self.assertIsNot(vars(self.quickNavItem)["label"], self.original, "the assistant changed the label")

	def test_a_picture_link_is_named_in_the_place_of_unlabeled(self):
		self.assertEqual(self.listItem(self.link("LOGO")).label, ALT_LOGO)

	def test_a_link_with_no_name_anywhere_is_named_by_where_it_goes(self):
		self.assertEqual(self.listItem(self.link("NOSUCH")).label, "click.shop.example")

	def test_a_link_with_text_is_labeled_by_its_text(self):
		self.assertEqual(self.listItem(self.link("WITHTEXT"), text="Unsubscribe").label, "Unsubscribe")
		self.assertEqual(self.item.reads, 0)

	def test_the_name_word_gives_a_link_is_kept(self):
		self.assertEqual(self.listItem(self.link("LOGO", name="Shop logo")).label, "Shop logo")

	def test_states_are_kept(self):
		self.assertEqual(self.listItem(self.link("LOGO", states={State.LINKED})).label, f"{ALT_LOGO}; linked")

	def test_a_button_is_labeled_as_before(self):
		self.assertEqual(self.listItem(self.link("LOGO"), itemType="button").label, "Unlabeled")

	def test_word_and_a_message_you_write_are_as_before(self):
		self.assertEqual(self.listItem(self.link("LOGO", appName="winword"), document=Message("winword")).label, "Unlabeled")
		self.assertEqual(self.listItem(self.link("LOGO"), document=Message(readOnly=False)).label, "Unlabeled")

	def test_an_element_the_document_took_away_is_seen_by_the_elements_list(self):
		# UIATextRangeQuickNavItem.obj raises LookupError for an element the document no longer has: the Elements List
		# needs to see it (elementsList), so the assistant lets it through.
		def gone():
			raise LookupError("the element is gone")

		with self.assertRaises(LookupError):
			self.listItem(gone).label

	def test_turned_off_the_label_is_nvdas(self):
		outlookMessages.unregister()
		self.assertIs(vars(self.quickNavItem)["label"], self.original)
		self.assertEqual(self.listItem(self.link("LOGO")).label, "Unlabeled")

	def test_an_nvda_without_the_label_still_names_links_in_speech(self):
		outlookMessages.unregister()
		with mock.patch.dict(sys.modules, {"UIAHandler.browseMode": None}):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				outlookMessages.register(reading=True)
		self.addCleanup(outlookMessages.unregister)
		self.assertTrue(any("NVDA has no UIAHandler.browseMode.UIATextRangeQuickNavItem" in line for line in logged.output), logged.output)
		self.assertEqual(self.said(run(self.link("LOGO"))), ["link", ALT_LOGO])
		self.assertIs(vars(self.quickNavItem)["label"], self.original)

	def test_register_and_unregister_put_the_label_back(self):
		outlookMessages.unregister()
		self.assertIs(vars(self.quickNavItem)["label"], self.original)
		outlookMessages.register(reading=True)
		installed = vars(self.quickNavItem)["label"]
		self.assertIs(installed.fget.__wrapped__, self.original.fget)
		outlookMessages.register(reading=True)
		self.assertIs(vars(self.quickNavItem)["label"], installed, "registered twice, wrapped once")
		outlookMessages.unregister()
		self.assertIs(vars(self.quickNavItem)["label"], self.original)

	def test_the_links_list_keeps_its_own_label_and_both_work_together(self):
		# The Links List changes NVDA's _getLabelForProperties; the assistant's label goes through whatever is there.
		seen = []
		nvdas = vars(self.quickNavItem)["_getLabelForProperties"]

		def linksList(self, labelPropertyGetter):
			seen.append(labelPropertyGetter("name"))
			return "Links List: " + nvdas(self, labelPropertyGetter)

		self.quickNavItem._getLabelForProperties = linksList
		self.assertEqual(self.listItem(self.link("LOGO")).label, "Links List: " + ALT_LOGO)
		self.assertEqual(seen, [ALT_LOGO])


class WithPicturesTest(pictures.Isolated):
	"""1.44's picture text (outlookPictures, which adds "graphic" and the picture's text from Word's object model) and the
	assistant's name for a link with no text, both on: the picture's text is said once."""

	def setUp(self):
		super().setUp()
		for patch in (
			mock.patch.dict(sys.modules, {"winUser": winUser({WINDOW: TITLE})}),
			mock.patch.object(unlabeledLinks, "_messages", unlabeledLinks.collections.OrderedDict()),
			mock.patch.object(unlabeledLinks, "_wordMessages", unlabeledLinks.collections.OrderedDict()),
			mock.patch.object(unlabeledLinks, "_noted", set()),
			mock.patch.object(unlabeledLinks, "_failed", False),
			mock.patch.object(unlabeledLinks, "_retryAt", 0.0),
		):
			patch.start()
			self.addCleanup(patch.stop)
		self.outlook = ObjectModel(inspectors=[Inspector(TITLE.strip(), Item())])
		outlookPictures.register()
		self.message = pictures.Message()

	def lineOf(self, query, alt):
		"""A line with a picture inside a link, whose field the assistant names as it does when NVDA makes it, and whose
		picture Word's object model has the alt text ``alt`` for."""
		self.message.document.picture(alt=alt)
		field = pictures.hyperlink(1)
		link = Link(query, nativeOm=self.outlook)
		self.assertTrue(outlookMessages.nameLinkWithNoText(types.SimpleNamespace(obj=Message()), link, field, link.value))
		return pictures.Line([("start", field), ("format", pictures.FormatField()), "", ("end", None)]), field["content"]

	def test_a_name_that_is_the_pictures_text_is_said_once(self):
		line, name = self.lineOf("LOGO", ALT_LOGO)
		self.assertEqual(name, ALT_LOGO)
		self.assertEqual(self.say(self.message, line), ["link", ALT_LOGO])

	def test_a_name_that_is_only_where_the_link_goes_has_the_pictures_text_said_too(self):
		line, name = self.lineOf("NOALT", "Make it Pink")
		self.assertEqual(name, "click.shop.example")
		self.assertEqual(self.say(self.message, line), ["link", "click.shop.example", "graphic", "Make it Pink"])


class HtmlTest(unittest.TestCase):
	def test_the_links_come_in_order(self):
		found = unlabeledLinks.anchors(MESSAGE_HTML)
		self.assertEqual(len(found), 15, "the link in the script isn't one")
		self.assertEqual(found[0].href, address("TEXT1"))
		self.assertEqual(found[0].text, "+ Take 50% off fall & Halloween accessories")

	def test_what_holds_a_picture_has_its_alt_text(self):
		found = {anchor.href: anchor for anchor in unlabeledLinks.anchors(MESSAGE_HTML)}
		self.assertEqual(found[address("LOGO")].alts, (ALT_LOGO,))
		self.assertEqual(found[address("LOGO")].text.strip(), "")
		self.assertEqual(found[address("NOALT")].alts, ())
		self.assertEqual(found[address("TITLED")].title, "Follow us on Facebook")

	def test_a_link_with_text_gives_no_name(self):
		labels = unlabeledLinks.labelsByAddress(MESSAGE_HTML)
		self.assertNotIn(unlabeledLinks.addressKey(address("TEXT1")), labels)
		self.assertNotIn(unlabeledLinks.addressKey(address("WITHTEXT")), labels)

	def test_the_names_of_the_links_with_no_text(self):
		labels = unlabeledLinks.labelsByAddress(MESSAGE_HTML)
		key = unlabeledLinks.addressKey
		self.assertEqual(labels[key(address("LOGO"))], ALT_LOGO)
		self.assertEqual(labels[key(address("FILLER2"))], ALT_FILLER)
		self.assertEqual(labels[key(address("TITLED"))], "Follow us on Facebook")
		self.assertEqual(labels[key(address("SAME"))], "First of two pictures to one address")
		for nameless in ("NOALT", "EMPTY", "SPACES", "SCRIPT"):
			self.assertNotIn(key(address(nameless)), labels)
		self.assertNotIn("mailto:reply@shop.example", labels)

	def test_several_pictures_in_a_link_are_all_said(self):
		html = '<a href="https://x.example/a"><img alt="One"><img alt="Two"><img alt="One"></a>'
		self.assertEqual(unlabeledLinks.labelsByAddress(html), {"https://x.example/a": "One Two"})

	def test_a_link_left_open_is_ended_by_the_next(self):
		html = '<a href="https://x.example/a"><img alt="One"><a href="https://x.example/b"><img alt="Two">'
		self.assertEqual(unlabeledLinks.labelsByAddress(html), {"https://x.example/a": "One", "https://x.example/b": "Two"})

	def test_an_aria_label_names_a_link_before_its_title(self):
		html = '<a href="https://x.example/a" title="Title" aria-label="Label"></a>'
		self.assertEqual(unlabeledLinks.labelsByAddress(html), {"https://x.example/a": "Label"})

	def test_what_isnt_html_gives_nothing(self):
		for html in (None, "", 42, "plain text, no links"):
			self.assertEqual(unlabeledLinks.labelsByAddress(html), {})

	def test_a_long_name_is_cut_at_a_word(self):
		long = " ".join(["word"] * 200)
		label = unlabeledLinks.cleanLabel(long)
		self.assertLessEqual(len(label), unlabeledLinks._LONGEST_NAME + 3)
		self.assertTrue(label.endswith("word..."), label[-20:])


class WhereALinkGoesTest(unittest.TestCase):
	def test_addresses(self):
		for address_, said in (
			("https://click.shop.example/?qs=ABC123", "click.shop.example"),
			("https://www.example.com/", "example.com"),
			("http://www.example.com/products/candle-jars", "example.com candle jars"),
			("https://example.com/help/unsubscribe/", "example.com unsubscribe"),
			("https://example.com/dp/B08XYZ1234", "example.com"),
			("https://example.com/a/2026/09/30", "example.com"),
			("https://example.com/image.jpg", "example.com"),
			("https://example.com:8443/status", "example.com status"),
			("https://user@example.com/x/y", "example.com"),
			("www.example.com/news", "example.com news"),
			("ftp://files.example.com/pub/", "files.example.com pub"),
			("mailto:reply@shop.example", "reply@shop.example"),
			("MailTo:Reply@Shop.example?subject=Hello%20there", "Reply@Shop.example"),
		):
			with self.subTest(address=address_):
				self.assertEqual(unlabeledLinks.addressLabel(address_), said)

	def test_what_isnt_an_address_gives_nothing(self):
		for address_ in (None, "", "   ", 42, "#top", "javascript:void(0)", "file:///C:/x.txt", "tel:+15555550100", "cid:image001", "mailto:"):
			with self.subTest(address=address_):
				self.assertIsNone(unlabeledLinks.addressLabel(address_))

	def test_the_site_for_the_log_is_never_the_rest(self):
		self.assertEqual(unlabeledLinks.siteOf("https://click.shop.example/?qs=SECRET"), "click.shop.example")
		self.assertEqual(unlabeledLinks.siteOf(None), "")
		self.assertEqual(unlabeledLinks.siteOf("mailto:someone@example.com"), "")


class ChoiceTest(unittest.TestCase):
	def test_the_order(self):
		choose = unlabeledLinks.chooseName
		self.assertEqual(choose("Word's name", "From the HTML", "https://x.example/"), ("Word's name", "name"))
		self.assertEqual(choose("", "From the HTML", "https://x.example/"), ("From the HTML", "html"))
		self.assertEqual(choose("", None, "https://x.example/help"), ("x.example help", "address"))
		self.assertEqual(choose("https://y.example/", None, None), ("y.example", "address"))
		self.assertEqual(choose("", None, None), (None, None))
		self.assertEqual(choose(None, None, "#top"), (None, None))

	def test_text_that_shows_nothing(self):
		self.assertFalse(unlabeledLinks.hasText(None))
		self.assertFalse(unlabeledLinks.hasText(""))
		self.assertFalse(unlabeledLinks.hasText(" \ufffc\r\n\x07\xa0\u200b"))
		self.assertTrue(unlabeledLinks.hasText("\ufffc Shop"))
		self.assertTrue(unlabeledLinks.hasText("|"))

	def test_addresses_as_names(self):
		for text in ("https://x.example/", "HTTP://X.example", "mailto:a@b.example", "www.example.com"):
			self.assertTrue(unlabeledLinks.isAddress(text), text)
		for text in ("Shop logo", "", None, "https", "see www.example.com"):
			self.assertFalse(unlabeledLinks.isAddress(text), text)


class SettingTest(unittest.TestCase):
	def test_it_is_part_of_saying_outlook_messages_as_jaws_does(self):
		self.assertTrue(outlookMessages.wanted({}))
		self.assertFalse(outlookMessages.wanted({outlookMessages.STATE_KEY: False}))


if __name__ == "__main__":
	unittest.main()
