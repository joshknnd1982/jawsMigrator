# Unit tests for version 1.55: where the mouse presses a suggestion.
#
# 1.54 pressed a suggestion at the middle of it when that was inside the suggestion's list. In the real NVDA 2026.2 with Edge 154 on
# https://www.visible.com/shop/home-internet, 1 October 2026, a window made small (the page's document 383 pixels high, ending at y
# 526) has the list run past the bottom of the page. The address form is in a part of the page that stays where it is, so nothing
# scrolls the list into the page: neither IAccessible2's scrollTo (every scroll type was tried, and scrollToPoint went the wrong way)
# nor the page's own scrollIntoView moved the page, and they moved the list only as far as its own box asks. What NVDA said of the
# rows:
# - a row entirely below the page is off screen (the states say so);
# - the row at the edge (top 499, bottom 555) is NOT off screen, and its middle was at 527, one pixel below the page; 1.54 pressed
#   there, outside the page, and said "selected" though nothing was chosen.
# A press on any part of a suggestion chooses it, so 1.55 presses at the middle of the part that shows in the list's box and the
# page, and for a suggestion no part of which shows it presses nothing and says so. The hit test NVDA has for a point
# (objectFromPoint) was tried for this and is no use: it answered with a generic section for a row in plain view.
# The fakes are those of test_v154_suggestionVisit: NVDA's objects for the page, a mouse and the page's reaction to it.
# Run: python -m unittest tests.test_v155_suggestionPressPlace -v

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from test_v154_suggestionVisit import CANT_PRESS, Rect, VisitTestCase  # noqa: E402

from jawsMigrator import suggestionLists  # noqa: E402


class Unreadable:
	"""A document NVDA can't read the place of."""

	@property
	def location(self):
		raise OSError("(-2147467259, 'Unspecified error')")


class Nowhere:
	"""A document with no place on the screen."""

	location = Rect(0, 0, 0, 0)


SCROLLBAR = 16


class PressWhereItShowsTest(VisitTestCase):
	def setUp(self):
		super().setUp()
		patch = mock.patch.object(suggestionLists, "_scrollbarSize", lambda: SCROLLBAR)
		patch.start()
		self.addCleanup(patch.stop)

	def pageEndsAt(self, bottom):
		"""The page, as the browser shows it, ends at ``bottom`` on the screen, as a small window's does: the list runs past it.

		The document's rectangle, which NVDA gives, is the page and the scrollbar below it.
		"""
		self.page.document._rect = Rect(14, 143, 1573, bottom - 143 + SCROLLBAR)

	def tallList(self):
		"""The list's box is six rows high (368 to 704): rows are inside it, and what hides them is the page's edge."""
		self.page.height = 6 * self.page.ROW
		self.page.list._rect = Rect(589, 368, 581, self.page.height)

	def visit(self, number):
		for _ in range(number):
			self.press("downArrow")

	def test_a_suggestion_at_the_pages_edge_is_pressed_on_the_part_that_shows(self):
		# The list's box is 368 to 564, rows are 56 high: the fourth row is 536 to 592, and 28 pixels of it are in the box. The
		# page ends at 560, so its middle (564) is outside the page and 24 pixels of it show.
		self.pageEndsAt(560)
		self.visit(4)
		option = self.page.options[3]
		self.assertFalse(option.hasIrrelevantLocation, "NVDA does not call it off screen")
		self.assertGreaterEqual(option.location.center[1], 560, "its middle is outside the page")
		self.press("enter")
		self.assertEqual(self.page.chosen, option._name)
		x, y = self.screen.clicks[0]
		self.assertTrue(143 <= y < 560, "the press is inside the page")
		self.assertTrue(536 <= y < 560, "on the suggestion's part that shows")
		self.assertEqual(option.calls, [], "nothing needed to scroll")
		self.assertEqual(self.said()[-1], f"{option._name}, selected")

	def test_a_row_in_a_tall_list_at_the_pages_edge_is_pressed_on_the_part_that_shows(self):
		# NVDA's measured case: the whole row is in the list's box, the page cuts it.
		self.tallList()
		self.pageEndsAt(560)
		self.visit(4)
		option = self.page.options[3]
		self.assertFalse(option.hasIrrelevantLocation)
		self.assertGreaterEqual(option.location.center[1], 560)
		self.press("enter")
		self.assertEqual(self.page.chosen, option._name)
		self.assertEqual(self.screen.clicks[0][1], (536 + 560) // 2, "the middle of the part that shows")

	def test_a_suggestion_that_all_shows_is_pressed_at_its_middle_as_before(self):
		self.visit(2)
		option = self.page.options[1]
		self.press("enter")
		self.assertEqual(self.screen.clicks, [option.location.center])

	def test_a_suggestion_with_too_little_showing_is_not_pressed(self):
		# Four pixels of the row show: a press there is a coin toss between the row and the edge.
		self.tallList()
		self.pageEndsAt(540)
		self.visit(4)
		option = self.page.options[3]
		self.assertFalse(option.hasIrrelevantLocation)
		self.press("enter")
		self.assertIsNone(self.page.chosen)
		self.assertEqual(self.screen.clicks, [])
		self.assertEqual(self.said()[-1], CANT_PRESS)

	def test_a_suggestion_that_shows_only_in_the_scrollbars_place_is_not_pressed(self):
		# The document's rectangle has the browser's scrollbar in it; a press on the scrollbar chooses nothing (measured: the press
		# at the middle of a 6 pixel slice of the row, which was in the horizontal scrollbar's 15 pixels, chose nothing, and 1.55
		# before this said "selected").
		self.tallList()
		self.pageEndsAt(530)
		self.visit(4)
		option = self.page.options[3]
		self.assertFalse(option.hasIrrelevantLocation, "NVDA does not call it off screen: the scrollbar's place is the document's")
		self.assertTrue(530 < option.location.top < 530 + SCROLLBAR, "its top is in the scrollbar's place")
		self.press("enter")
		self.assertIsNone(self.page.chosen)
		self.assertEqual(self.screen.clicks, [])
		self.assertEqual(self.said()[-1], CANT_PRESS)

	def test_a_suggestion_the_page_hides_completely_is_not_pressed_and_the_user_is_told(self):
		# The list is in a part of the page that does not move, so scrolling it into view does nothing (measured).
		self.tallList()
		self.pageEndsAt(520)
		self.visit(4)
		option = self.page.options[3]
		self.assertTrue(option.hasIrrelevantLocation, "NVDA says it is off screen")
		gesture = self.press("enter")
		self.assertIsNone(self.page.chosen)
		self.assertEqual(self.screen.clicks, [])
		self.assertEqual(self.screen.moves, [], "the pointer did not move")
		self.assertIn("scrollIntoView", option.calls, "the page was asked to scroll it into view first")
		self.assertEqual(self.said()[-1], CANT_PRESS)
		self.assertEqual(gesture.sent, 0, "and Enter doesn't submit the form")
		self.assertGreaterEqual(self.clock.slept, suggestionLists._SCROLL_WAIT, "after waiting for it to show")
		self.assertIsNotNone(suggestionLists._session, "the visit goes on: Up Arrow can go to a suggestion that shows")

	def test_up_arrow_goes_on_to_a_suggestion_that_shows_and_it_is_pressed(self):
		self.tallList()
		self.pageEndsAt(520)
		self.visit(4)
		self.press("enter")
		self.press("upArrow")
		self.press("enter")
		self.assertEqual(self.page.chosen, self.name(3))

	def test_what_is_not_pressed_is_told_to_the_log(self):
		self.tallList()
		self.pageEndsAt(520)
		self.visit(4)
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.press("enter")
		self.assertTrue(any("no part of the suggestion" in line and "shows" in line for line in logged.output), logged.output)

	def test_a_suggestion_cut_by_the_pages_right_edge_is_pressed_on_the_part_that_shows(self):
		self.page.document._rect = Rect(14, 143, 800 + SCROLLBAR, 1067)  # the page ends at x 814, its scrollbar at 830; the row is 590 to 1150
		self.visit(2)
		option = self.page.options[1]
		self.press("enter")
		self.assertEqual(self.page.chosen, option._name)
		self.assertEqual(self.screen.clicks[0][0], (590 + 814) // 2)

	def test_a_suggestion_cut_by_the_pages_left_edge_is_pressed_on_the_part_that_shows(self):
		self.page.document._rect = Rect(1000, 143, 573 + SCROLLBAR, 1067)  # the page starts at x 1000
		self.visit(2)
		option = self.page.options[1]
		self.press("enter")
		self.assertEqual(self.page.chosen, option._name)
		self.assertEqual(self.screen.clicks[0][0], (1000 + 1150) // 2)

	def test_when_the_page_cant_say_where_it_is_the_press_is_as_it_was(self):
		# The row at the page's edge, and the page's place unreadable: the list's box alone decides, the row's part in it.
		self.pageEndsAt(560)
		self.visit(4)
		self.document.rootNVDAObject = Unreadable()
		self.press("enter")
		self.assertEqual(self.page.chosen, self.name(4))
		self.assertEqual(self.screen.clicks[0][1], (536 + 564) // 2, "the middle of the part in the list's box")

	def test_a_document_with_no_place_is_the_same(self):
		self.pageEndsAt(560)
		self.visit(4)
		self.document.rootNVDAObject = Nowhere()
		self.press("enter")
		self.assertEqual(self.page.chosen, self.name(4))

	def test_a_field_whose_document_is_unknown_is_the_same(self):
		self.visit(2)
		self.document.rootNVDAObject = None
		self.press("enter")
		self.assertEqual(self.page.chosen, self.name(2))

	def test_a_suggestion_that_scrolls_into_the_list_is_pressed_where_it_shows_then(self):
		# 1.54's case, still: out of the list's box, the page scrolls the list.
		for _ in range(9):
			self.press("downArrow")
		option = self.page.options[8]
		self.press("enter")
		self.assertEqual(self.page.chosen, option._name)
		self.assertIn("scrollIntoView", option.calls)

	def test_the_press_nvda_makes_when_it_activates_a_suggestion_uses_the_page_too(self):
		self.pageEndsAt(560)
		option = self.page.options[3]
		self.page.field.treeInterceptor = self.document
		with mock.patch.object(suggestionLists, "_suggestionAndList", return_value=(option, self.page.list)):
			self.assertTrue(suggestionLists.pressSuggestion(option))
		self.assertEqual(self.page.chosen, option._name)
		self.assertTrue(536 <= self.screen.clicks[0][1] < 560)


class PressPlaceTest(unittest.TestCase):
	"""The helpers, on their own."""

	def test_the_part_of_a_rectangle_in_an_area(self):
		self.assertEqual(suggestionLists._part((0, 0, 100, 100), Rect(50, 50, 100, 100)), (50, 50, 100, 100))
		self.assertEqual(suggestionLists._part((0, 0, 100, 100), None), (0, 0, 100, 100), "an area that is not known holds all of it")
		self.assertEqual(suggestionLists._part((0, 0, 100, 100), Rect(0, 0, 0, 0)), (0, 0, 100, 100))
		left, top, right, bottom = suggestionLists._part((0, 0, 100, 100), Rect(200, 200, 10, 10))
		self.assertTrue(right <= left or bottom <= top, "nothing of it is there")


if __name__ == "__main__":
	unittest.main()
