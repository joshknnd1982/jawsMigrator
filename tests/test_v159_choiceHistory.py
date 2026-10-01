# Unit tests for version 1.59, from the tester's comment of 1 October 2026 (15:46 UTC) on issue 47: "I'm attaching a log so you can see what
# happened."
#
# His log (1.58, 11:43 to 11:45 his time) has the whole unit step working: he typed "241 w pine st", went down to the eleventh address, GROVE
# CITY, PA, and chose it ("..., selected"); NVDA said "Enter Unit Label, edit, has auto complete, blank, placeholder, Enter Unit address"; Down
# Arrow went through the five units (FLR 1, FLR 3, UNIT 2, "I can't find my unit", "I don't live in a unit"), Enter chose UNIT 2 ("UNIT 2,
# selected"), and Control+Z took it back ("Choice undone"; Down Arrow then said the units again). Then he pressed Up Arrow (his NVDA has
# automatic focus mode for caret movement on, so it took him out of the unit box to the address box) and Down Arrow in the address box, which
# found no suggestions showing ("no suggestions are showing for it", the assistant's line in the log), three times over in different ways (11:45:05,
# 11:45:13 and 11:45:20), and went on up the page.
# What the log shows is that the address choice could not be taken back any more: 1.58 kept one choice, the newest, so choosing the unit
# replaced the address choice, and a second Control+Z was the page's own, which hides the unit box and leaves a list of the one address chosen
# (measured on the stand-in page, tests/live_nvda/scenarios/s61.py, with 1.58; and his 1.57 log has the same list of three variants).
#
# 1.59: the choices are kept one behind the other (an address, then its unit). Control+Z takes back the newest one that belongs to where the focus
# is and drops the ones after it, and says which box is empty and that the earlier choice can be taken back too ("Choice undone, Enter Unit Label
# is empty. Control+Z again takes back the earlier choice."); a second one takes back the address: "Choice undone, 241 w pine st", and the twenty
# suggestions come back. The unit box is known by what it is (its identity, kept with the choice as NVDA makes its object the first time), and not
# only by when NVDA made its object: NVDA makes a new object each time the focus comes to a field, and the focus came to the unit box again in his
# log (11:45:05 and 11:45:14), more than three seconds after the choice, where 1.58 no longer took the box for a part of the choice.
# The fakes are the ones of tests/test_v158_unitBox.py (the assistant's code is the real one).
# Run: python -m unittest tests.test_v159_choiceHistory -v

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v154_suggestionVisit as visit  # noqa: E402
from test_v157_undoChoice import TYPED  # noqa: E402
from test_v158_unitBox import UNIT_UNDONE, UnitTestCase  # noqa: E402

from jawsMigrator import suggestionLists  # noqa: E402


class HistoryTestCase(UnitTestCase):
	def chooseUnit(self, number=2):
		"""The address with units chosen, the page's focus in its unit box, and a unit chosen in it with Enter (the unit is the ``number``-th)."""
		self.inUnitBox()
		self.clock.now += 1.0
		for _ in range(number):
			self.press("downArrow")
		self.press("enter")
		nvdaStubs.spoken.clear()

	def addressBoxAgain(self):
		"""NVDA's new object for the address box: the focus came back to it (Shift+Tab), and it is the same element on the page."""
		again = self.page.makeField()
		again.IA2UniqueID = self.page.field.IA2UniqueID
		again.treeInterceptor = self.document
		self.page.focused = again
		return again


class TheTestersLogOfTheUnitStepTest(HistoryTestCase):
	def test_the_unit_taken_back_leaves_the_address_choice_to_take_back(self):
		self.chooseUnit(2)
		self.assertEqual(self.page.unitText, "APT 2")
		gesture = self.undo()
		self.assertEqual(self.said(), [UNIT_UNDONE], "he is told which box is empty, and that the earlier choice can be taken back too")
		self.assertEqual(self.page.unitText, "")
		self.assertEqual(gesture.sent, 0)
		self.assertIsNotNone(suggestionLists._chosen)
		self.assertEqual(suggestionLists._chosen.text, self.name(3), "what is left is the address choice")
		self.assertIsNone(suggestionLists._chosen.before)

	def test_a_second_control_z_takes_the_address_choice_back(self):
		self.chooseUnit(2)
		self.undo()
		nvdaStubs.spoken.clear()
		gesture = self.undo()
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"], "there is no earlier choice to tell of")
		self.assertEqual(self.page.text, TYPED)
		self.assertEqual(self.page.inputs, [TYPED], "the page got the new text")
		self.assertEqual(gesture.sent, 0, "the key did not go on to the page, whose undo hid the unit box and left the one address")
		self.assertEqual(self.page.keys, [])
		self.assertFalse(self.page.unitBox, "the page hid the unit box, as it does when the address changes")
		self.assertIsNone(suggestionLists._chosen)

	def test_the_focus_goes_back_to_the_address_box_before_the_text_is_put(self):
		self.chooseUnit(2)
		self.undo()
		self.page.events.clear()
		self.undo()
		self.assertEqual(self.page.events[0], ("focus", "Enter your home address (required)"))
		self.assertEqual(self.page.events[1], ("put", TYPED, "Enter your home address (required)"), "put while the address box had the focus")
		self.assertIs(self.page.focused, self.page.field)

	def test_down_arrow_then_goes_into_the_twenty_addresses_again(self):
		self.chooseUnit(2)
		self.undo()
		self.undo()
		nvdaStubs.spoken.clear()
		self.press("downArrow")
		self.advance(1.0)
		self.assertEqual(self.said(), [f"Address suggestions, list, {self.name(1)}, 1 of 10"])
		self.assertEqual(self.page.keys, [])
		self.assertEqual(self.stockRan, [], "NVDA's own Down Arrow did not run")

	def test_a_third_control_z_is_the_pages(self):
		self.chooseUnit(2)
		self.undo()
		self.undo()
		nvdaStubs.spoken.clear()
		self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(self.said(), [])

	def test_the_second_control_z_is_claimed_on_the_keyboard_hooks_thread_without_reading_nvdas_objects(self):
		self.chooseUnit(2)
		self.undo()
		self.page.hook = True
		try:
			found = suggestionLists.scriptFor(visit.Gesture(self.page, "z", "control"))
		finally:
			self.page.hook = False
		self.assertIs(found, suggestionLists._undoChoice)

	def test_the_unit_can_be_chosen_again_after_it_was_taken_back_and_still_be_taken_back_with_the_address_to_follow(self):
		self.chooseUnit(2)
		self.undo()
		self.press("downArrow")
		self.advance(1.0)
		self.press("downArrow")
		self.press("enter")
		self.assertEqual(self.page.unitText, "APT 2")
		nvdaStubs.spoken.clear()
		self.undo()
		self.assertEqual(self.said(), [UNIT_UNDONE])
		self.undo()
		self.assertEqual(self.page.text, TYPED)


class WhatIsSaidTest(HistoryTestCase):
	def test_the_unit_is_said_to_be_empty_by_its_name(self):
		self.chooseUnit(2)
		self.undo()
		self.assertEqual(self.said(), ["Choice undone, Enter Unit Label is empty. " + suggestionLists.EARLIER_CHOICE])

	def test_the_earlier_choice_is_not_mentioned_when_the_address_was_changed_since(self):
		self.chooseUnit(2)
		self.page.text += "x"  # he typed in the address box: it no longer holds the choice, so it can't be taken back
		self.undo()
		self.assertEqual(self.said(), ["Choice undone, Enter Unit Label is empty"])

	def test_the_address_choice_alone_says_what_was_typed_and_nothing_more(self):
		self.inUnitBox()
		self.undo()
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])

	def test_the_words_for_each_case(self):
		field = self.page.unitField
		choice = suggestionLists._Choice
		self.assertEqual(suggestionLists._undoneWords(choice(field, "241 w", "x", 0), field, False), "Choice undone, 241 w")
		self.assertEqual(
			suggestionLists._undoneWords(choice(field, "241 w", "x", 0), field, True),
			"Choice undone, 241 w. Control+Z again takes back the earlier choice.",
		)
		self.assertEqual(suggestionLists._undoneWords(choice(field, "", "x", 0), field, False), "Choice undone, Enter Unit Label is empty")
		self.assertEqual(suggestionLists._undoneWords(choice(field, "   ", "x", 0), field, False), "Choice undone, Enter Unit Label is empty")
		nameless = visit.Item(self.page, visit.Role.EDITABLETEXT, "")
		self.assertEqual(suggestionLists._undoneWords(choice(nameless, "", "x", 0), nameless, False), "Choice undone, the box is empty")

	def test_the_words_say_control_z(self):
		self.assertIn("Control+Z", suggestionLists.EARLIER_CHOICE)


class BackInTheAddressBoxAfterAUnitWasChosenTest(HistoryTestCase):
	def test_control_z_in_the_address_box_takes_the_address_choice_back_and_the_unit_goes_with_it(self):
		# Shift+Tab from the unit box right after the unit was chosen: NVDA makes a new object for the address box within a few seconds of the
		# unit's choice, which makes it look like a box that followed that choice too, with text in it: the address choice is the one it belongs to.
		self.chooseUnit(2)
		self.addressBoxAgain()
		gesture = self.undo()
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])
		self.assertEqual(self.page.text, TYPED)
		self.assertEqual(gesture.sent, 0)
		self.assertEqual(self.page.keys, [])
		self.assertIsNone(suggestionLists._chosen, "the unit's choice went with it: the page hid the unit box")

	def test_the_same_long_after_the_unit_was_chosen(self):
		self.chooseUnit(2)
		self.clock.now += 30
		self.addressBoxAgain()
		self.undo()
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])
		self.assertEqual(self.page.keys, [])

	def test_an_address_box_that_was_changed_is_the_pages_to_undo(self):
		self.chooseUnit(2)
		self.addressBoxAgain()
		self.page.text += "x"
		self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(self.page.text, self.name(3) + "x")
		self.assertIsNone(suggestionLists._chosen, "the choices are used up: the address box doesn't hold the choice any more")

	def test_it_is_not_given_the_focus_again_when_it_has_it(self):
		self.chooseUnit(2)
		self.addressBoxAgain()
		self.page.events.clear()
		self.undo()
		self.assertNotIn(("focus", "Enter your home address (required)"), self.page.events)


class TheUnitBoxIsKnownByWhatItIsTest(HistoryTestCase):
	def test_a_box_made_soon_after_the_choice_is_noted_with_it(self):
		self.choose(3)
		field = self.arrive()
		self.assertIn(suggestionLists._identity(field), suggestionLists._chosen.followers)

	def test_a_box_made_long_after_the_choice_is_not_noted(self):
		self.choose(3)
		self.clock.now += suggestionLists._FOLLOW_SECONDS + 1
		field = self.newUnitField()
		self.assertNotIn(suggestionLists._identity(field), suggestionLists._chosen.followers)

	def test_the_unit_box_the_focus_came_back_to_is_still_part_of_the_choice(self):
		# 11:45:05 and 11:45:14 in his log: Down Arrow from the address box into the unit box, NVDA makes a new object for it.
		first = self.inUnitBox()
		self.page.focused = self.page.field
		self.clock.now += 20
		again = self.newUnitField(first.IA2UniqueID)
		self.page.focused = again
		self.assertIsNot(again, first)
		self.assertFalse(suggestionLists._madeAfter(again, suggestionLists._chosen), "by when NVDA made it, it is no longer one")
		self.assertTrue(suggestionLists._follows(again, suggestionLists._chosen), "by what it is, it is")
		self.undo()
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])
		self.assertEqual(self.page.text, TYPED)
		self.assertEqual(self.page.keys, [])

	def test_a_visit_in_the_unit_box_that_was_made_again_keeps_the_choice(self):
		# 1.58 forgot the address choice here: the box was made long after it. Down Arrow through the units, and Control+Z in the middle of it.
		first = self.inUnitBox()
		self.page.focused = self.page.field
		self.clock.now += 20
		again = self.newUnitField(first.IA2UniqueID)
		self.page.focus(again)
		self.clock.now += 1.0  # the page has shown its units
		self.press("downArrow")
		self.press("downArrow")
		self.assertEqual(self.said()[-2:], ["Unit suggestions, list, APT 1, 1 of 7", "APT 2, 2 of 7"])
		self.assertIsNotNone(suggestionLists._chosen, "the address choice is kept")
		nvdaStubs.spoken.clear()
		gesture = self.undo()
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])
		self.assertEqual(gesture.sent, 0)
		self.assertEqual(self.page.text, TYPED)

	def test_another_field_made_long_after_the_choice_is_not_part_of_it(self):
		self.choose(3)
		self.arrive()
		self.clock.now += 20
		stranger = self.newUnitField()  # another element: it has an identity of its own
		self.page.focused = stranger
		self.assertFalse(suggestionLists._follows(stranger, suggestionLists._chosen))
		self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(self.page.text, self.name(3))

	def test_the_field_of_the_choice_is_never_a_box_that_followed_it(self):
		self.choose(3)
		again = self.addressBoxAgain()
		self.assertFalse(suggestionLists._follows(again, suggestionLists._chosen))

	def test_only_the_last_few_boxes_are_kept(self):
		self.choose(3)
		for _ in range(suggestionLists._MOST_BOXES + 2):
			self.newUnitField()
		self.assertEqual(len(suggestionLists._chosen.followers), suggestionLists._MOST_BOXES)

	def test_the_identity_of_an_object_nvda_cant_say_is_none(self):
		self.assertIsNone(suggestionLists._identity(object()))
		silent = visit.Item(self.page, visit.Role.EDITABLETEXT, "x")
		silent.IA2UniqueID = 0
		self.assertIsNone(suggestionLists._identity(silent))
		self.assertEqual(suggestionLists._identity(self.page.field), (self.page.field.IA2WindowHandle, self.page.field.IA2UniqueID))

	def test_an_object_that_raises_is_not_a_follower(self):
		self.choose(3)

		class Broken:
			IA2WindowHandle = property(lambda self: 1 / 0)

			def __eq__(self, other):
				raise RuntimeError("boom")

		self.assertFalse(suggestionLists._follows(Broken(), suggestionLists._chosen))


class TheChainOfChoicesTest(HistoryTestCase):
	def test_a_unit_chosen_in_the_box_the_page_moved_the_focus_to_goes_on_from_the_address(self):
		self.chooseUnit(2)
		unit = suggestionLists._chosen
		self.assertEqual(unit.text, "APT 2")
		self.assertEqual(unit.before.text, self.name(3))
		self.assertIsNone(unit.before.before)

	def test_an_address_chosen_alone_has_nothing_before_it(self):
		self.choose(2)
		self.assertIsNone(suggestionLists._chosen.before)

	def test_a_choice_in_the_address_box_starts_over(self):
		self.chooseUnit(2)
		self.addressBoxAgain()
		self.page.listShowing = True
		self.press("downArrow")
		self.press("downArrow")
		self.press("enter")
		chosen = suggestionLists._chosen
		self.assertEqual(chosen.text, self.name(2))
		self.assertIsNone(chosen.before, "the unit's choice went with the address it belonged to")

	def test_a_visit_in_the_address_box_forgets_the_chain(self):
		self.chooseUnit(2)
		self.addressBoxAgain()
		self.page.listShowing = True
		self.press("downArrow")
		self.assertIsNone(suggestionLists._chosen)

	def test_a_visit_in_the_unit_box_forgets_the_unit_before_it_and_keeps_the_address(self):
		self.chooseUnit(2)
		self.page.unitClosed = False  # the page shows its units again for the unit box
		self.press("downArrow")
		self.assertEqual(suggestionLists._chosen.text, self.name(3))

	def test_a_unit_chosen_again_replaces_the_unit_before_it(self):
		self.chooseUnit(2)
		self.page.unitClosed = False
		self.press("downArrow")
		self.press("downArrow")
		self.press("enter")
		chosen = suggestionLists._chosen
		self.assertEqual(chosen.text, "APT 2")
		self.assertEqual(chosen.before.text, self.name(3))
		self.assertIsNone(chosen.before.before, "not three deep: the first unit is gone")

	def test_the_chain_is_cut_after_the_most_it_keeps(self):
		choice = suggestionLists._Choice
		newest = None
		for number in range(suggestionLists._MOST_CHOICES + 3):
			newest = choice(None, "", str(number), number, newest)
		self.assertEqual(len(list(suggestionLists._each(newest))), suggestionLists._MOST_CHOICES)
		self.assertEqual(next(iter(suggestionLists._each(newest))).text, str(suggestionLists._MOST_CHOICES + 2))
		self.assertEqual(list(suggestionLists._each(None)), [])

	def test_something_typed_in_the_unit_box_after_a_unit_was_chosen_is_the_pages_and_the_address_choice_stays(self):
		self.chooseUnit(2)
		self.page.unitText = "APT 2x"
		self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(self.page.unitText, "APT 2x", "the page's undo is the page's to do")
		self.assertIsNotNone(suggestionLists._chosen)
		self.assertEqual(suggestionLists._chosen.text, self.name(3), "the unit's choice is used up; the address choice stays")

	def test_a_key_with_the_focus_somewhere_else_is_the_pages_and_nothing_is_used_up(self):
		self.chooseUnit(2)
		self.page.focused = self.page.button
		self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(suggestionLists._chosen.text, "APT 2")
		self.assertEqual(suggestionLists._chosen.before.text, self.name(3))

	def test_unregistered_the_whole_chain_is_forgotten(self):
		self.chooseUnit(2)
		with mock.patch.object(suggestionLists, "_replaced", []):
			suggestionLists.unregister()
		self.assertIsNone(suggestionLists._chosen)

class TheLogSaysWhatHappenedTest(HistoryTestCase):
	def test_the_choice_before_is_in_the_log(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.chooseUnit(2)
		self.assertIn(f"the suggestion 'APT 2' was chosen, and Control+Z puts back '', and then the choice before it ({self.name(3)!r})", "\n".join(logged.output))

	def test_the_taking_back_says_the_earlier_choice_can_be_taken_back(self):
		self.chooseUnit(2)
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.undo()
		text = "\n".join(logged.output)
		self.assertIn("Control+Z took the choice back: the field holds '' again", text)
		self.assertIn(f"Control+Z again takes back the choice before it, {self.name(3)!r}", text)

	def test_the_taking_back_of_the_address_says_nothing_of_an_earlier_one(self):
		self.inUnitBox()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.undo()
		self.assertNotIn("Control+Z again takes back", "\n".join(logged.output))

	def test_a_key_that_is_the_pages_says_why(self):
		self.chooseUnit(2)
		self.clock.now += 20
		self.page.focused = self.newUnitField()  # a field with suggestions that the page did not move the focus to after the choices
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.undo()
		self.assertIn("nothing was chosen, or the focus is not where the choice was made", "\n".join(logged.output))

	def test_text_typed_in_the_box_says_why(self):
		self.inUnitBox()
		self.page.unitText = "4B"
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.undo()
		self.assertIn("something is typed in the box the page moved the focus to", "\n".join(logged.output))


class WhyNoSuggestionsAreShowingTest(HistoryTestCase):
	"""His log has Down Arrow in the address box three times after a choice, each "no suggestions are showing for it": the log now says the page shut
	its list when the suggestion was chosen, and that Control+Z takes the choice back. Nothing is said to him: whether he wants that is a question."""

	def test_down_arrow_in_a_field_whose_list_a_choice_shut_says_so_in_the_log(self):
		self.choose(2)
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.press("downArrow")
		text = "\n".join(logged.output)
		self.assertIn(
			f"goes on as NVDA has it: no suggestions are showing for it: the page shut its list when {self.name(2)!r} was chosen in it, and Control+Z takes that choice back",
			text,
		)
		self.assertEqual(self.stockRan, ["downArrow"], "NVDA does what it does with the key, as before")
		self.assertEqual(self.said(), [], "and nothing is said to the user")

	def test_without_a_choice_it_says_what_it_said_before(self):
		self.page.listShowing = False
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.press("downArrow")
		text = "\n".join(logged.output)
		self.assertIn("goes on as NVDA has it: no suggestions are showing for it", text)
		self.assertNotIn("the page shut its list", text)

	def test_in_another_field_it_is_not_said(self):
		self.chooseUnit(2)
		self.clock.now += 20
		stranger = self.newUnitField()
		self.page.focused = stranger
		self.page.unitClosed = True
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.press("downArrow")
		self.assertNotIn("the page shut its list", "\n".join(logged.output))

	def test_the_reason_is_asked_for_in_the_unit_box_too(self):
		self.chooseUnit(2)
		self.assertIn("'APT 2'", suggestionLists._closedByChoice(self.page.unitField))
		self.assertEqual(suggestionLists._closedByChoice(self.page.button), "")

	def test_a_field_that_cant_be_asked_gives_nothing(self):
		self.choose(2)
		self.assertEqual(suggestionLists._closedByChoice(object()), "")


class TheWordsOnlySayWhatTheNextKeyDoesTest(HistoryTestCase):
	"""An independent review of this change found that "Control+Z again takes back the earlier choice" was said whenever the earlier choice still
	held its text, but a second Control+Z in a box that holds text is the page's (what is typed in a box is the page's to undo): a unit box that held
	"APT" when the unit was chosen holds "APT" again once the unit is taken back, and was promised an undo it did not get."""

	def chooseUnitAfterTyping(self):
		self.inUnitBox()
		self.clock.now += 1.0
		self.page.unitText = "APT"  # typed before: the page showed the units that contain it
		self.press("downArrow")
		self.press("enter")
		nvdaStubs.spoken.clear()

	def test_a_unit_box_that_held_text_is_not_promised_the_address(self):
		self.chooseUnitAfterTyping()
		self.undo()
		self.assertEqual(self.said(), ["Choice undone, APT"])
		self.assertEqual(self.page.unitText, "APT")

	def test_and_the_next_control_z_there_is_the_pages(self):
		self.chooseUnitAfterTyping()
		self.undo()
		gesture = self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(gesture.sent, 1)
		self.assertEqual(self.page.text, self.name(3), "the address choice was not touched")
		self.assertEqual(suggestionLists._chosen.text, self.name(3), "and it is still there to take back")

	def test_from_the_address_box_it_can_still_be_taken_back(self):
		self.chooseUnitAfterTyping()
		self.undo()
		nvdaStubs.spoken.clear()
		self.addressBoxAgain()
		self.undo()
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])
		self.assertEqual(self.page.text, TYPED)

	def test_the_words_are_said_exactly_where_the_next_control_z_takes_the_earlier_choice(self):
		self.chooseUnit(2)
		unit = suggestionLists._chosen
		address = unit.before
		unitBox, addressBox = self.page.unitField, self.page.field
		self.assertEqual(unit.typed, "")
		self.assertTrue(suggestionLists._canGoBack(unit, unitBox), "an empty box that followed the earlier choice: the next key takes it back")
		unit.typed = "APT"
		self.assertFalse(suggestionLists._canGoBack(unit, unitBox), "a box that holds text: the next key is the page's")
		self.assertTrue(suggestionLists._canGoBack(unit, addressBox), "the earlier choice's own field: the next key takes it back")
		unit.typed = ""
		self.page.text += "x"
		self.assertFalse(suggestionLists._canGoBack(unit, unitBox), "the earlier choice no longer holds its text")
		self.assertFalse(suggestionLists._canGoBack(unit, addressBox), "nor there")
		self.page.text = address.text
		self.assertFalse(suggestionLists._canGoBack(address, addressBox), "nothing before the address")
		self.clock.now += 20
		stranger = self.newUnitField()  # another element, made long after: the page did not move the focus to it
		self.assertFalse(suggestionLists._canGoBack(unit, stranger))

	def test_the_log_does_not_say_it_either(self):
		self.chooseUnitAfterTyping()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.undo()
		self.assertNotIn("Control+Z again takes back", "\n".join(logged.output))


class WhatCantBeReadOrCompared(HistoryTestCase):
	"""The gaps the review listed: a choice whose typed text could not be read, an object whose identity NVDA can't say, an object that can't be
	compared, and the window handle, which NVDA 2026.2 reads through COM (the fakes now fail it in the keyboard hook's thread)."""

	def test_a_choice_whose_typed_text_could_not_be_read_keeps_the_choice_before_it(self):
		self.inUnitBox()
		self.clock.now += 1.0
		self.page.unitUnreadable = True
		self.press("downArrow")
		self.press("enter")
		self.page.unitUnreadable = False
		self.assertEqual(suggestionLists._chosen.text, self.name(3), "no unit choice was noted (nothing to put back), and the address choice stays")
		self.assertIsNone(suggestionLists._chosen.before)
		self.addressBoxAgain()
		nvdaStubs.spoken.clear()
		self.undo()
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])
		self.assertEqual(self.page.text, TYPED)

	def test_an_object_whose_identity_cant_be_read_is_not_noted(self):
		self.choose(3)
		before = suggestionLists._chosen.followers
		silent = visit.Item(self.page, visit.Role.EDITABLETEXT, "x")
		silent.IA2UniqueID = 0
		suggestionLists._noteFollower(silent, self.clock.now)
		self.assertEqual(suggestionLists._chosen.followers, before)

	def test_the_same_survives_an_object_that_cant_be_compared(self):
		class Gone:
			IA2WindowHandle, IA2UniqueID = 4242, 7

			def __eq__(self, other):
				raise RuntimeError("the object is gone")

		class Twin:
			IA2WindowHandle, IA2UniqueID = 4242, 7

		self.assertTrue(suggestionLists._same(Gone(), Twin()), "told by its unique ID")
		self.assertFalse(suggestionLists._same(Gone(), object()))

	def test_the_window_handle_is_a_com_read_that_fails_in_the_keyboard_hooks_thread(self):
		self.page.hook = True
		try:
			with self.assertRaises(visit.ComThreadError):
				self.page.field.IA2WindowHandle
			self.assertIsNone(suggestionLists._identity(self.page.field))
		finally:
			self.page.hook = False
		self.assertEqual(suggestionLists._identity(self.page.field), (4242, self.page.field.IA2UniqueID))

	def test_the_claim_of_control_z_does_not_look_at_an_identity(self):
		self.chooseUnit(2)
		self.undo()
		self.page.hook = True
		try:
			self.assertIs(suggestionLists.scriptFor(visit.Gesture(self.page, "z", "control")), suggestionLists._undoChoice)
		finally:
			self.page.hook = False

	def test_text_typed_after_a_choice_is_not_blamed_on_it_in_the_log(self):
		self.choose(2)
		self.page.text += "x"  # the field no longer holds the suggestion
		self.assertEqual(suggestionLists._closedByChoice(self.page.field), "")
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.press("downArrow")
		text = "\n".join(logged.output)
		self.assertIn("goes on as NVDA has it: no suggestions are showing for it", text)
		self.assertNotIn("the page shut its list", text)


class SettingTest(unittest.TestCase):
	def test_the_chain_and_the_boxes_kept_are_a_few(self):
		for value in (suggestionLists._MOST_CHOICES, suggestionLists._MOST_BOXES):
			self.assertGreaterEqual(value, 2)
			self.assertLessEqual(value, 10)

	def test_a_choice_holds_what_it_replaced(self):
		field = object()
		choice = suggestionLists._Choice(field, "typed", "text", 5.0)
		self.assertIs(choice.field, field)
		self.assertEqual((choice.typed, choice.text, choice.at), ("typed", "text", 5.0))
		self.assertIsNone(choice.before)
		self.assertEqual(choice.followers, ())

	def test_the_choice_before_is_kept(self):
		before = suggestionLists._Choice(object(), "a", "b", 1.0)
		self.assertIs(suggestionLists._Choice(object(), "c", "d", 2.0, before).before, before)


if __name__ == "__main__":
	unittest.main()
