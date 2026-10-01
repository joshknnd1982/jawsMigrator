# Unit tests for version 1.57, from the tester's comment of 1 October 2026 on issue 47: "The address picker is accessible. The only thing
# I noticed is if I accidently select the wrong one I can't unselect it. if that is by design that is fine."
#
# His log (1.55) has it: the eighth address chosen with Enter ("... CANTON, IL, 61520, USA, selected"), then Up Arrow (NVDA said the
# address in the field), Down Arrow (the assistant: "no suggestions are showing for it", NVDA said the address again) and Down Arrow
# (his NVDA has automatic focus mode for caret movement on, so it left the field: "button, Check availability"). The page, once a
# suggestion is chosen, has the address in its field and its list shut, and brings suggestions back only when the text changes (its
# input event also makes it forget the choice), so there was nothing to go back to.
#
# 1.57: Control+Z, while the field still holds what the choice put there, puts back the text the field held when Down Arrow began the
# visit. It is put through the page's accessibility (IAccessible's accValue). Measured in a second NVDA 2026.2 on its own Windows
# desktop with Microsoft Edge 154, on a stand-in for the page's picker (tests/live_nvda/pages/address.html: markup and behaviour of
# the live page, canned suggestions, so that nothing was typed into the live site), 1 October 2026, which these fakes follow:
# - Backspace once brings back a list of the one address that was chosen; Control+A and the street typed again brings back all twenty;
#   the browser's own Control+Z after a choice brings back the one address (the page gets an input event with the chosen address);
# - accValue set to the street gives the page an input event with it (it forgets the choice) and the page shows all twenty again
#   about 0.45 seconds later (300 ms of quiet and its service); NVDA says nothing of the change; the focus stays in the field;
# - NVDA runs the lookup of a key's script in the keyboard hook's thread, where the field can't be read (the fakes raise there, as the
#   earlier tests' do), so the claim of Control+Z reads nothing of NVDA's objects; the script, in the main thread, looks whether the
#   field still holds what the choice put there, and if not the key goes on;
# - the mouse press of a choice reaches the page a little after it is made, so the text is not waited for when the choice is made.
# The imitation is NVDA's objects for the page, how NVDA finds the script of a key, a mouse and the page's reaction to it; the
# assistant's code is the real one.
# Run: python -m unittest tests.test_v157_undoChoice -v

import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v154_suggestionVisit as visit  # noqa: E402
from test_v154_suggestionVisit import Field, Page, VisitTestCase, _com  # noqa: E402

from jawsMigrator import suggestionLists  # noqa: E402

TYPED = "241 w pine st"


class AccValue:
	"""IAccessible's accValue, read and written by child ID."""

	def __init__(self, field):
		self.field = field

	def __getitem__(self, childID):
		return self.field.page.read()

	def __setitem__(self, childID, text):
		self.field.page.putText(text)


class TextField(Field):
	"""The address field with the text it holds."""

	IAccessibleChildID = 0

	@_com
	def value(self):
		return self.page.read()

	@_com
	def IAccessibleObject(self):
		return types.SimpleNamespace(accValue=AccValue(self))


class TextPage(Page):
	"""The page, with the text of its field. Choosing puts the suggestion there. Text put there by accessibility makes the page forget the
	choice and show its suggestions again ``listDelay`` seconds later."""

	def __init__(self, *args, **kwargs):
		self.text = TYPED
		self._shown, self._returnAt = True, None
		self.clock = None
		self.listDelay = 0.45
		self.accValueFails = False
		self.unreadable = False
		self.inputs = []
		super().__init__(*args, **kwargs)

	@property
	def listShowing(self):
		if self._returnAt is not None and self.clock is not None and self.clock.now >= self._returnAt:
			self._shown, self._returnAt = True, None
		return self._shown

	@listShowing.setter
	def listShowing(self, value):
		self._shown = value

	def read(self):
		if self.unreadable:
			raise OSError("(-2147467259, 'Unspecified error')")
		return self.text

	def choose(self, option):
		super().choose(option)
		self.text = option._name

	def putText(self, text):
		if self.accValueFails:
			raise OSError("(-2147467259, 'Unspecified error')")
		self.text = text
		self.chosen = None
		self.inputs.append(text)
		self._shown = False
		self._returnAt = self.clock.now + self.listDelay


class UndoTestCase(VisitTestCase):
	def setUp(self):
		for patch in (mock.patch.object(visit, "Page", TextPage), mock.patch.object(visit, "Field", TextField)):
			patch.start()
			self.addCleanup(patch.stop)
		super().setUp()
		self.page.clock = self.clock
		for patch in (mock.patch.object(suggestionLists, "_chosen", None), mock.patch.object(suggestionLists, "_returning", None)):
			patch.start()
			self.addCleanup(patch.stop)

	def choose(self, number=3, key="enter"):
		"""Down Arrow to a suggestion and Enter on it; what is said after that is what the test looks at."""
		for _ in range(number):
			self.press("downArrow")
		self.press(key)
		nvdaStubs.spoken.clear()

	def undo(self):
		return self.press("z", "control")


class UndoingAChoiceTest(UndoTestCase):
	def test_control_z_after_a_choice_puts_back_what_was_typed(self):
		self.choose(3)
		self.assertEqual(self.page.text, self.name(3), "the page put the suggestion in the field")
		gesture = self.undo()
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])
		self.assertEqual(self.page.text, TYPED)
		self.assertEqual(self.page.inputs, [TYPED], "the page got the new text")
		self.assertEqual(gesture.sent, 0, "the key did not go on to the page")
		self.assertEqual(self.page.keys, [])
		self.assertIs(self.page.focused, self.page.field, "the focus stays in the field")

	def test_down_arrow_then_goes_into_the_suggestions_the_page_shows_again(self):
		self.choose(3)
		self.undo()
		self.clock.now += 1.0
		self.press("downArrow")
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}", f"Address suggestions, list, {self.name(1)}, 1 of 10"])
		self.assertEqual(self.page.keys, [])

	def test_down_arrow_right_after_waits_for_the_page_to_show_them(self):
		# 1.57 held NVDA's main thread for up to 1.5 seconds; 1.58 does not (the watchdog cancels COM calls from half a second on): its own
		# timer looks again every 50 milliseconds.
		self.choose(3)
		self.undo()
		before, started = self.clock.slept, self.clock.now
		self.press("downArrow")
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"], "nothing yet: the page has not shown them")
		self.assertEqual(self.stockRan, [], "NVDA's own Down Arrow did not run")
		while len(self.said()) < 2 and self.clock.now - started < 3:
			self.advance(0.01)
		waited = self.clock.now - started
		self.assertGreaterEqual(waited, self.page.listDelay)
		self.assertLess(waited, self.page.listDelay + 0.1)
		self.assertEqual(self.said()[-1], f"Address suggestions, list, {self.name(1)}, 1 of 10")
		self.assertEqual(self.stockRan, [], "NVDA's own Down Arrow did not run")
		self.assertEqual(self.page.keys, [])
		self.assertEqual(self.clock.slept, before, "NVDA's main thread was not held")

	def test_it_goes_on_to_the_next_suggestion_and_a_second_choice_can_be_made(self):
		self.choose(3)
		self.undo()
		self.press("downArrow")
		self.advance(1.0)
		self.press("downArrow")
		self.press("enter")
		self.assertEqual(self.page.text, self.name(2))
		self.assertEqual(self.said()[-1], f"{self.name(2)}, selected")
		self.undo()
		self.assertEqual(self.page.text, TYPED, "and that one can be taken back too")

	def test_down_arrow_gives_up_after_a_second_and_a_half_when_the_page_shows_nothing(self):
		self.page.listDelay = 99
		self.choose(3)
		self.undo()
		before, started = self.clock.slept, self.clock.now
		self.press("downArrow")
		self.assertEqual(self.stockRan, [], "the key waits: NVDA's own Down Arrow has not run yet")
		self.advance(suggestionLists._RETURN_WAIT - 0.2)
		self.assertEqual(self.stockRan, [])
		self.advance(0.4)
		self.assertLess(self.clock.now - started, suggestionLists._RETURN_WAIT + 0.3)
		# 1.57 then did what NVDA does with the key, which in the field is to walk out of it (and, measured, into the buffer's "Loading...").
		self.assertEqual(self.said()[-1], suggestionLists.NO_SUGGESTIONS_YET)
		self.assertEqual(self.stockRan, [], "NVDA's own Down Arrow does not run")
		self.assertEqual(self.page.keys, [])
		self.assertEqual(self.clock.slept, before, "and NVDA's main thread was not held")

	def test_the_wait_is_shorter_than_the_time_the_keys_that_follow_are_taken_for_the_visit(self):
		# A key pressed while Down Arrow waits is looked for after the wait began, and is the visit's only for _PENDING_SECONDS.
		self.assertLess(suggestionLists._RETURN_WAIT, suggestionLists._PENDING_SECONDS)

	def test_down_arrow_long_after_the_undo_does_not_wait(self):
		self.page.listDelay = 99
		self.choose(3)
		self.undo()
		self.clock.now += suggestionLists._RETURN_WINDOW + 1
		before = self.clock.slept
		self.press("downArrow")
		self.assertEqual(self.clock.slept, before)
		self.assertEqual(self.stockRan, ["downArrow"])

	def test_down_arrow_without_an_undo_does_not_wait_for_a_list_that_is_not_showing(self):
		self.page.listShowing = False
		before = self.clock.slept
		self.press("downArrow")
		self.assertEqual(self.clock.slept, before)
		self.assertEqual(self.stockRan, ["downArrow"])

	def test_the_arrow_keys_the_tester_pressed_after_the_choice_do_not_end_it(self):
		# His log: Up Arrow, Down Arrow (no list showing), Down Arrow. Then the choice can still be taken back.
		self.choose(3)
		self.press("upArrow")
		self.press("downArrow")
		self.assertEqual(self.stockRan, ["upArrow", "downArrow"])
		nvdaStubs.spoken.clear()
		self.undo()
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])
		self.assertEqual(self.page.text, TYPED)

	def test_it_works_when_nvda_is_in_browse_mode_with_the_focus_still_in_the_field(self):
		self.choose(3)
		self.document.passThrough = False
		self.undo()
		self.assertEqual(self.page.text, TYPED)
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])

	def test_what_was_typed_is_kept_through_the_whole_visit(self):
		for key in ("downArrow", "downArrow", "downArrow", "upArrow", "end", "home", "downArrow"):
			self.press(key)
		self.press("enter")
		nvdaStubs.spoken.clear()
		self.undo()
		self.assertEqual(self.page.text, TYPED)

	def test_space_chooses_and_that_can_be_taken_back_too(self):
		self.choose(2, key="space")
		self.assertEqual(self.page.text, self.name(2))
		self.undo()
		self.assertEqual(self.page.text, TYPED)

	def test_a_later_visit_puts_back_the_text_it_began_with(self):
		self.choose(3)
		self.page.text = TYPED + ", canton"  # the user typed more, and the page showed its suggestions for it
		self.page.listShowing = True
		self.choose(2)
		self.assertEqual(self.page.text, self.name(2))
		self.undo()
		self.assertEqual(self.page.text, TYPED + ", canton")

	def test_the_field_text_may_differ_in_spaces_from_the_suggestions(self):
		self.choose(3)
		self.page.text = self.name(3).replace(", ", ",  ")
		self.undo()
		self.assertEqual(self.page.text, TYPED)


class WhereControlZIsNotTheAssistantsTest(UndoTestCase):
	def test_control_z_with_nothing_chosen_is_the_pages(self):
		gesture = self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(gesture.sent, 1)
		self.assertEqual(self.said(), [])

	def test_control_z_during_a_visit_is_the_pages(self):
		self.press("downArrow")
		nvdaStubs.spoken.clear()
		self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(self.said(), [])

	def test_control_z_after_the_user_typed_something_else_is_the_pages(self):
		self.choose(3)
		self.page.text += "x"
		gesture = self.undo()
		self.assertEqual(self.page.text, self.name(3) + "x", "what the user typed is not replaced")
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(gesture.sent, 1)
		self.assertEqual(self.said(), [])

	def test_the_choice_is_forgotten_once_it_found_the_text_changed(self):
		self.choose(3)
		self.page.text += "x"
		self.undo()
		self.page.text = self.name(3)  # the user deleted the letter again
		self.undo()
		self.assertEqual(self.page.keys, ["z", "z"], "both are the page's")
		self.assertEqual(self.said(), [])

	def test_a_second_control_z_is_the_pages(self):
		self.choose(3)
		self.undo()
		nvdaStubs.spoken.clear()
		self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(self.said(), [])

	def test_control_z_after_the_focus_moved_is_the_pages(self):
		self.choose(3)
		self.page.focused = self.page.button
		self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(self.page.text, self.name(3))

	def test_other_keys_with_z_are_not_control_z(self):
		self.choose(3)
		for modifiers in (("control", "shift"), ("alt",), ("control", "alt"), ("shift",), ()):
			self.press("z", *modifiers)
		self.assertEqual(self.page.keys, ["z"] * 5)
		self.assertEqual(self.page.text, self.name(3))
		self.undo()
		self.assertEqual(self.page.text, TYPED, "and Control+Z alone still does")

	def test_the_control_key_alone_is_not_control_z(self):
		self.choose(3)
		self.press("control", isModifier=True)
		self.assertEqual(self.page.text, self.name(3))

	def test_a_new_visit_forgets_the_choice(self):
		self.choose(3)
		self.page.listShowing = True
		self.press("downArrow")
		self.press("tab")  # the visit is over
		self.undo()
		self.assertEqual(self.page.keys, ["tab", "z"])
		self.assertEqual(self.page.text, self.name(3))

	def test_a_field_that_held_nothing_is_put_back_empty(self):
		# 1.57 left this to the page. 1.58 puts the nothing back: the unit box holds nothing when the page shows its units (tests/test_v158_unitBox.py).
		self.page.text = ""
		self.choose(3)
		self.undo()
		self.assertEqual(self.page.keys, [])
		self.assertEqual(self.page.text, "")
		self.assertEqual(self.said(), ["Choice undone"])

	def test_a_field_that_cant_be_read_offers_nothing(self):
		self.page.unreadable = True
		self.choose(3)
		self.page.unreadable = False
		self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(self.said(), [])

	def test_a_field_that_cant_be_read_when_control_z_is_pressed_gets_the_key_on(self):
		self.choose(3)
		self.page.unreadable = True
		self.undo()
		self.assertEqual(self.page.keys, ["z"], "the key goes on as NVDA has it")

	def test_when_the_assistant_is_off_control_z_is_the_pages(self):
		self.choose(3)
		with mock.patch.object(suggestionLists, "_enabled", False):
			self.undo()
		self.assertEqual(self.page.keys, ["z"])


class WhenThePageWillNotTakeTheTextTest(UndoTestCase):
	def test_the_user_is_told_and_the_key_is_not_sent_on(self):
		self.page.accValueFails = True
		self.choose(3)
		gesture = self.undo()
		self.assertEqual(self.said(), ["Can't put back what you typed"])
		self.assertEqual(gesture.sent, 0)
		self.assertEqual(self.page.text, self.name(3))

	def test_it_is_logged(self):
		self.page.accValueFails = True
		self.choose(3)
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.undo()
		self.assertIn("Control+Z could not put", "\n".join(logged.output))

	def test_a_page_that_says_it_took_the_text_but_still_has_the_old_is_told_too(self):
		self.choose(3)
		with mock.patch.object(TextPage, "putText", lambda page, text: None):
			self.undo()
		self.assertEqual(self.said(), ["Can't put back what you typed"])


class TheKeyboardHooksThreadTest(UndoTestCase):
	def test_the_claim_of_control_z_reads_nothing_of_nvdas_objects(self):
		self.choose(3)
		gesture = visit.Gesture(self.page, "z", "control")
		self.page.hook = True
		try:
			script = suggestionLists.scriptFor(gesture)
		finally:
			self.page.hook = False
		self.assertIs(script, suggestionLists._undoChoice)

	def test_the_key_is_not_claimed_when_nothing_was_chosen(self):
		gesture = visit.Gesture(self.page, "z", "control")
		self.assertIsNone(suggestionLists.scriptFor(gesture))

	def test_the_key_is_not_claimed_once_the_focus_moved_off_the_field(self):
		self.choose(3)
		self.page.focused = self.page.button
		self.assertIsNone(suggestionLists.scriptFor(visit.Gesture(self.page, "z", "control")))

	def test_control_z_is_looked_for_before_the_page_gets_it_at_all(self):
		self.choose(3)
		self.undo()
		self.assertEqual(self.page.keys, [], "not even the key's sending ran")


class TheLogSaysWhatHappenedTest(UndoTestCase):
	def test_the_choice_and_its_undoing_are_logged(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.choose(3)
			self.undo()
			self.press("downArrow")
			self.advance(1.0)
		text = "\n".join(logged.output)
		self.assertIn(f"the suggestion {self.name(3)!r} was chosen, and Control+Z puts back {TYPED!r}", text)
		self.assertIn(f"Control+Z took the choice back: the field holds {TYPED!r} again", text)
		self.assertIn("the page's suggestions were back", text)

	def test_a_key_that_found_the_text_changed_is_logged(self):
		self.choose(3)
		self.page.text += "x"
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.undo()
		self.assertIn("Control+Z goes on as NVDA has it: the field no longer holds what the choice put there", "\n".join(logged.output))

	def test_suggestions_that_did_not_come_back_are_logged(self):
		self.page.listDelay = 99
		self.choose(3)
		self.undo()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.press("downArrow")
			self.advance(suggestionLists._RETURN_WAIT + 0.2)
		self.assertIn("were not back", "\n".join(logged.output))


class SettingTest(unittest.TestCase):
	def test_unregistered_the_choice_is_forgotten(self):
		with mock.patch.object(suggestionLists, "_chosen", object()), mock.patch.object(suggestionLists, "_returning", (object(), 1)), mock.patch.object(suggestionLists, "_enabled", True), mock.patch.object(suggestionLists, "_replaced", []):
			suggestionLists.unregister()
			self.assertIsNone(suggestionLists._chosen)
			self.assertIsNone(suggestionLists._returning)

	def test_the_key_is_control_z(self):
		self.assertEqual(suggestionLists.UNDO_KEY, "z")


if __name__ == "__main__":
	unittest.main()
