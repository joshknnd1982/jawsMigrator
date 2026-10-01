# Unit tests for version 1.58, from the tester's comment of 1 October 2026 (14:04 UTC) on issue 47: "Hear is a log so you can see exactly what is
# happening."
#
# His log (1.57, 09:54 to 10:04 his time) has Control+Z working in the first three rounds (the second, the seventh and the tenth address:
# "Choice undone, 241 w pine st"), and then, in the fourth, the eleventh address, GROVE CITY, PA, which has units:
#   10:03:33  Enter: "241 W PINE ST, GROVE CITY, PA, 16127, USA, selected", the assistant notes the choice
#   10:03:34  NVDA: "Enter Unit Label, edit, has auto complete, blank, placeholder, Enter Unit address" (the page moved the focus to its unit box)
#   10:03:39  Control+Z: "Undo" (the page's own, not the assistant's: the focus was no longer in the field the choice was made in); the unit box
#             vanished, the address box had its address and a list of three variants of it, and nothing brought back the twenty
#   10:03:50 to 10:04:12  Control+Z three more times, each "Undo"; Down Arrow through the three variants (each said 1 of 3, 2 of 3, 3 of 3, and
#             "3 of 3" four times more at the end); Tab, Shift+Tab, Down Arrow ("no suggestions are showing for it").
# The page's script (clientlib-fioscheckavailability, read on 1 October 2026) says why: selectAddress puts the address in the box and, for an
# address that has units (unitExists), calls showUnitField, which shows the unit box and moves the focus to it with a zero-delay timer; the unit
# box asks for its list when it gets the focus ("Loading...", then the units and "I can't find my unit" and "I don't live in a unit"); a change of
# the address box's text hides the unit box. Measured in a second NVDA 2026.2 on its own Windows desktop with Microsoft Edge 154, on the stand-in
# page (tests/live_nvda/pages/address.html) with the same behaviour: 1.57's Control+Z in the unit box went to the page, whose undo hid the unit
# box and left a list of the one address; Down Arrow in the unit box already went through its units ("Unit suggestions, list, APT 1, 1 of 7").
#
# 1.58: the box the page moves the focus to right after a choice is part of the choice. Control+Z in it, while it holds nothing, takes the
# address choice back: the focus goes back to the address box, its text is put back, and Down Arrow goes into the suggestions again. A unit chosen
# with Enter is a choice too: Control+Z puts back the empty box and the page shows all its units. A box that held nothing when the visit began is
# told from one that could not be read (NVDA's value is None for both).
# These fakes follow the stand-in page and NVDA's objects as the earlier tests' do (the assistant's code is the real one): the page's zero-delay
# timer is arrive(), which gives NVDA's focus event to the box; the keyboard hook's thread can't read NVDA's objects (they raise there).
# Run: python -m unittest tests.test_v158_unitBox -v

import copy
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v154_suggestionVisit as visit  # noqa: E402
from test_v154_suggestionVisit import Item, Listbox, Option, Page, Rect, Role, Screen, State, VisitTestCase, _com  # noqa: E402
from test_v157_undoChoice import TYPED, AccValue, TextField, TextPage  # noqa: E402

from jawsMigrator import suggestionLists  # noqa: E402

#: What NVDA says when a unit that was chosen is taken back (1.59: which box is empty, and that the address choice can be taken back too).
UNIT_UNDONE = f"Choice undone, Enter Unit Label is empty. {suggestionLists.EARLIER_CHOICE}"


class AddressField(TextField):
	"""The address field. NVDA's ``value`` is None for a field that holds nothing (IAccessible._get_value), where the earlier fake gave ""."""

	@_com
	def value(self):
		text = self.page.read()
		return text if text.strip() else None

	def setFocus(self):
		self.page.focus(self)


class UnitAccValue(AccValue):
	"""IAccessible's accValue of the unit box."""

	def __getitem__(self, childID):
		return self.field.page.unitRead()

	def __setitem__(self, childID, text):
		self.field.page.unitPut(text)


class UnitField(AddressField):
	"""The unit box (input#unit-input, aria-controls="unit-dropdown"): it controls its list while the page shows it."""

	@_com
	def value(self):
		text = self.page.unitRead()
		return text if text.strip() else None

	@_com
	def controllerFor(self):
		return [self.page.unitList] if self.page.unitPhase() != "hidden" else []

	@_com
	def IAccessibleObject(self):
		return types.SimpleNamespace(accValue=UnitAccValue(self))


class UnitList(Listbox):
	"""The unit box's list: what it holds is what the page has in it now (nothing, "Loading...", or the units)."""

	@_com
	def children(self):
		self.reads += 1
		return self.page.unitChildren()

	@_com
	def childCount(self):
		return len(self.page.unitChildren())


class UnitOption(Option):
	"""A unit in the list: all of them are in sight."""

	@_com
	def location(self):
		box = self.page.unitList._rect
		return Rect(box.left + 1, box.top + self.page.unitOptions.index(self) * Page.ROW, 560, Page.ROW)

	@_com
	def states(self):
		states = {State.FOCUSABLE, State.SELECTABLE}
		if self.page.hidden(self):
			states.add(State.INVISIBLE)
		return states

	@_com
	def positionInfo(self):
		return {"indexInGroup": self.page.unitOptions.index(self) + 1, "similarItemsInGroup": len(self.page.unitOptions)}


class UnitPage(TextPage):
	"""The address picker with units: choosing the third address shows the unit box; the page's zero-delay timer then moves the focus to it
	(moveFocus), and its focus handler asks for the units, which arrive ``unitDelay`` seconds later. A change of the address box's text
	(Control+Z's accValue) hides the unit box, as the page's input handler does, and the focus falls to the page if the unit box had it."""

	UNITS = ("APT 1", "APT 2", "APT 3A", "APT 3B", "UNIT 4", "I can't find my unit", "I don't live in a unit")
	WITH_UNITS = (3,)

	def __init__(self, *args, **kwargs):
		self.unitText = ""
		self.unitBox = False
		self.unitClosed = False
		self.unitAskAt = None
		self.unitDelay = 0.3
		self.unitInputs = []
		self.unitUnreadable = False
		self.setFocusFails = False
		self.events = []
		super().__init__(*args, **kwargs)
		self.unitField = self.wrapper.add(self.makeUnitField())
		self.unitList = self.wrapper.add(UnitList(self, Role.LIST, "Unit suggestions", rect=Rect(589, 468, 581, self.ROW * 8)))
		self.loading = self.unitList.add(Item(self, Role.SECTION, "Loading..."))
		self.unitOptions = [self.unitList.add(UnitOption(self, Role.LISTITEM, name)) for name in self.UNITS]

	def makeUnitField(self, uniqueID=None):
		"""The unit box, as NVDA makes it: the assistant is asked about it, and may add its class. ``uniqueID`` makes it the same element on
		the page as an object made before (NVDA makes a new object each time the focus comes to a field)."""
		raw = UnitField(self, Role.EDITABLETEXT, "Enter Unit Label", rect=Rect(589, 420, 581, 40))
		if uniqueID is not None:
			raw.IA2UniqueID = uniqueID
		raw._states = {State.EDITABLE, State.FOCUSABLE, State.AUTOCOMPLETE}
		classes = [visit.Ia2Web]
		suggestionLists.chooseOverlay(raw, classes)
		if classes[0] is visit.Ia2Web:
			return raw
		made = type("Dynamic_" + "".join(cls.__name__ for cls in classes), (classes[0], type(raw)), {})
		field = made.__new__(made)
		field.__dict__.update(raw.__dict__)
		return field

	# -- the unit box and its list
	def unitPhase(self):
		""""hidden", "loading" (the list says "Loading...") or "listed" (the units are in it)."""
		if not self.unitBox or self.unitAskAt is None or self.unitClosed:
			return "hidden"
		now = self.clock.now
		if now < self.unitAskAt:
			return "hidden"
		return "listed" if now >= self.unitAskAt + self.unitDelay else "loading"

	def unitChildren(self):
		phase = self.unitPhase()
		return [] if phase == "hidden" else [self.loading] if phase == "loading" else self.unitOptions

	def hidden(self, obj):
		if obj is self.unitField:
			return not self.unitBox
		if obj is self.unitList:
			return self.unitPhase() == "hidden"
		if obj is self.loading:
			return self.unitPhase() != "loading"
		if obj in self.unitOptions:
			return self.unitPhase() != "listed"
		return super().hidden(obj)

	def unitRead(self):
		if self.unitUnreadable:
			raise OSError("(-2147467259, 'Unspecified error')")
		return self.unitText

	def unitPut(self, text):
		"""Text put in the unit box through accessibility is an input event: the page asks for the units 300 ms later."""
		self.events.append(("unitPut", text))
		self.unitText = text
		self.unitInputs.append(text)
		self.unitClosed = False
		self.unitAskAt = self.clock.now + 0.3

	def chooseUnit(self, option):
		"""The page's mousedown on a unit: the box gets it by script (no input event) and the list closes."""
		self.events.append(("unit", option._name))
		self.unitText = option._name
		self.unitClosed = True

	# -- the page's reactions
	def focus(self, item):
		if self.setFocusFails:
			raise OSError("(-2147467259, 'Unspecified error')")
		self.events.append(("focus", item._name))
		self.focused = item
		if item is self.unitField and self.unitBox:
			self.unitAskAt = self.clock.now
			self.unitClosed = False

	def choose(self, option):
		super().choose(option)
		self.events.append(("choose", option._name))
		if self.options.index(option) + 1 in self.WITH_UNITS:
			self.unitBox, self.unitText, self.unitClosed, self.unitAskAt = True, "", False, None
		else:
			self.unitBox = False

	def putText(self, text):
		self.events.append(("put", text, getattr(self.focused, "_name", None)))
		super().putText(text)
		self.unitBox, self.unitText = False, ""
		if self.focused is self.unitField:
			self.focused = self.document  # the page hides the box that has the focus: the focus falls to the page


class UnitScreen(Screen):
	"""The mouse: a press on a unit in the unit box's list chooses it, a press elsewhere is the address list's (as before)."""

	def doPrimaryClick(self):
		page = self.page
		x, y = self.pointer
		if page.unitPhase() == "listed":
			box = page.unitList._rect
			if box.left <= x < box.left + box.width and box.top <= y < box.top + box.height:
				self.clicks.append((x, y))
				for option in page.unitOptions:
					place = option.location
					if place.top <= y < place.top + place.height:
						page.chooseUnit(option)
						return
				return
		super().doPrimaryClick()


class UnitTestCase(VisitTestCase):
	def setUp(self):
		for patch in (mock.patch.object(visit, "Page", UnitPage), mock.patch.object(visit, "Field", AddressField), mock.patch.object(visit, "Screen", UnitScreen)):
			patch.start()
			self.addCleanup(patch.stop)
		super().setUp()
		self.page.clock = self.clock
		for patch in (mock.patch.object(suggestionLists, "_chosen", None), mock.patch.object(suggestionLists, "_returning", None)):
			patch.start()
			self.addCleanup(patch.stop)
		# The unit box was made while the assistant was off, like the address field was: make it again.
		self.newUnitField()
		# Time passes between NVDA's making the objects and the user's choosing (the fake clock moves only when something sleeps).
		self.clock.now += 1.0

	def newUnitField(self, uniqueID=None):
		"""NVDA's object for the unit box, as it makes one when the focus comes to it: the assistant is asked about it as it is made."""
		old = self.page.unitField
		new = self.page.makeUnitField(uniqueID)
		new._parent = old._parent
		siblings = old._parent._children
		siblings[siblings.index(old)] = new
		new.treeInterceptor = self.document
		self.page.unitField = new
		return new

	def choose(self, number=3, key="enter"):
		"""Down Arrow to a suggestion and Enter on it; what is said after that is what the test looks at."""
		for _ in range(number):
			self.press("downArrow")
		self.press(key)
		nvdaStubs.spoken.clear()

	def arrive(self, after=0.1):
		"""The page's zero-delay timer moves the focus to its unit box, and NVDA makes its object for the box (in NVDA's main thread)."""
		self.clock.now += after
		field = self.newUnitField()
		self.page.focus(field)
		return field

	def undo(self):
		return self.press("z", "control")

	def inUnitBox(self):
		"""The address with units chosen, and the page's focus in its unit box."""
		self.choose(3)
		return self.arrive()


class TheTestersFourthRoundTest(UnitTestCase):
	def test_control_z_in_the_unit_box_takes_the_address_choice_back(self):
		self.inUnitBox()
		self.assertEqual(self.page.text, self.name(3), "the page put the address in the box")
		self.assertIs(self.page.focused, self.page.unitField)
		gesture = self.undo()
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])
		self.assertEqual(self.page.text, TYPED)
		self.assertEqual(self.page.inputs, [TYPED], "the page got the new text")
		self.assertEqual(gesture.sent, 0, "the key did not go on to the page, whose undo hid the unit box and left the one address")
		self.assertEqual(self.page.keys, [])

	def test_the_focus_goes_back_to_the_address_box_before_the_text_is_put(self):
		# The page hides the unit box when the address box's text changes: with the focus in it, the focus would fall to the page.
		self.inUnitBox()
		self.page.events.clear()
		self.undo()
		self.assertEqual(self.page.events[0], ("focus", "Enter your home address (required)"))
		self.assertEqual(self.page.events[1], ("put", TYPED, "Enter your home address (required)"), "put while the address box had the focus")
		self.assertIs(self.page.focused, self.page.field)
		self.assertFalse(self.page.unitBox, "the page hid the unit box, as it does when the address changes")

	def test_down_arrow_then_goes_into_the_address_suggestions_again(self):
		self.inUnitBox()
		self.undo()
		self.press("downArrow")
		self.advance(1.0)
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}", f"Address suggestions, list, {self.name(1)}, 1 of 10"])
		self.assertEqual(self.page.keys, [])
		self.assertEqual(self.stockRan, [], "NVDA's own Down Arrow did not run")

	def test_the_choice_can_be_made_again_and_taken_back_again(self):
		self.inUnitBox()
		self.undo()
		self.press("downArrow")
		self.advance(1.0)
		self.press("downArrow")
		self.press("enter")
		self.assertEqual(self.page.text, self.name(2))
		self.assertFalse(self.page.unitBox, "the second address has no units")
		self.undo()
		self.assertEqual(self.page.text, TYPED)

	def test_a_second_control_z_is_the_pages(self):
		self.inUnitBox()
		self.undo()
		nvdaStubs.spoken.clear()
		self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(self.said(), [])

	def test_the_choice_is_taken_back_though_the_page_had_it_for_a_while(self):
		self.inUnitBox()
		self.clock.now += 40
		self.undo()
		self.assertEqual(self.page.text, TYPED)


class WhereControlZInTheUnitBoxIsNotTheAssistantsTest(UnitTestCase):
	def test_something_typed_in_the_unit_box_is_the_pages_to_undo(self):
		self.inUnitBox()
		self.page.unitText = "4B"
		gesture = self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(gesture.sent, 1)
		self.assertEqual(self.page.text, self.name(3), "the address box is as it was")
		self.assertEqual(self.said(), [])
		self.assertIsNotNone(suggestionLists._chosen, "the choice can still be taken back from the address box")

	def test_a_unit_box_that_cant_be_read_is_not_taken_for_empty(self):
		self.inUnitBox()
		self.page.unitUnreadable = True
		self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(self.page.text, self.name(3))

	def test_a_box_that_got_the_focus_long_after_the_choice_is_not_part_of_it(self):
		self.choose(3)
		self.arrive(after=suggestionLists._FOLLOW_SECONDS + 1)
		self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(self.page.text, self.name(3))
		self.assertIsNotNone(suggestionLists._chosen, "nothing was used up: the field the choice was made in can still take it back")

	def test_control_z_in_a_field_that_is_not_one_with_suggestions_is_the_pages(self):
		self.inUnitBox()
		self.page.focused = self.page.button
		self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(self.page.text, self.name(3))

	def test_the_address_box_that_was_changed_is_the_pages_even_from_the_unit_box(self):
		self.inUnitBox()
		self.page.text += "x"
		self.undo()
		self.assertEqual(self.page.keys, ["z"])
		self.assertEqual(self.page.text, self.name(3) + "x")
		self.assertIsNone(suggestionLists._chosen, "the choice is used up: the address box doesn't hold it any more")

	def test_when_the_assistant_is_off_control_z_is_the_pages(self):
		self.inUnitBox()
		with mock.patch.object(suggestionLists, "_enabled", False):
			self.undo()
		self.assertEqual(self.page.keys, ["z"])

	def test_an_address_without_units_has_no_box_that_the_page_moves_the_focus_to(self):
		self.choose(2)
		self.assertFalse(self.page.unitBox)
		self.assertFalse(suggestionLists._madeAfter(self.page.unitField, suggestionLists._chosen), "the unit box was made before the choice")
		self.undo()
		self.assertEqual(self.page.text, TYPED, "and Control+Z in the address box is as in 1.57")
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])


class BackInTheAddressBoxTest(UnitTestCase):
	def test_control_z_in_the_address_box_that_the_focus_came_back_to_takes_the_choice_back(self):
		# Shift+Tab from the unit box: NVDA makes a new object for the field, the same field on the page.
		self.inUnitBox()
		again = copy.copy(self.page.field)
		self.assertIsNot(again, self.page.field)
		self.page.focused = again
		self.undo()
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])
		self.assertEqual(self.page.text, TYPED)
		self.assertEqual(self.page.keys, [])

	def test_it_is_the_address_box_that_is_put_back_and_not_given_the_focus_again_when_it_has_it(self):
		self.inUnitBox()
		self.page.focused = self.page.field
		self.page.events.clear()
		self.undo()
		self.assertNotIn(("focus", "Enter your home address (required)"), self.page.events)


class TheUnitsTest(UnitTestCase):
	def test_down_arrow_in_the_unit_box_goes_through_its_units(self):
		self.inUnitBox()
		self.clock.now += 1.0
		self.press("downArrow")
		self.press("downArrow")
		self.assertEqual(self.said(), ["Unit suggestions, list, APT 1, 1 of 7", "APT 2, 2 of 7"])
		self.assertEqual(self.page.keys, [])

	def test_down_arrow_right_after_the_focus_arrives_waits_for_the_units(self):
		# The list says "Loading..." for a moment: one child that is no suggestion.
		self.inUnitBox()
		self.assertEqual(self.page.unitPhase(), "loading")
		before, started = self.clock.slept, self.clock.now
		self.press("downArrow")
		self.assertEqual(self.said(), [], "nothing yet: the page's list says \"Loading...\"")
		self.assertEqual(self.stockRan, [], "NVDA's own Down Arrow did not run")
		while not self.said() and self.clock.now - started < 3:
			self.advance(0.01)
		waited = self.clock.now - started
		self.assertGreater(waited, 0)
		self.assertLess(waited, self.page.unitDelay + 0.15)
		self.assertEqual(self.said(), ["Unit suggestions, list, APT 1, 1 of 7"])
		self.assertEqual(self.stockRan, [], "NVDA's own Down Arrow did not run")
		self.assertEqual(self.page.keys, [])
		self.assertEqual(self.clock.slept, before, "NVDA's main thread was not held")

	def test_down_arrow_waits_no_longer_than_a_second_and_a_half_for_a_slow_service(self):
		self.page.unitDelay = 99
		self.inUnitBox()
		started = self.clock.now
		self.press("downArrow")
		self.advance(suggestionLists._RETURN_WAIT - 0.2)
		self.assertEqual(self.stockRan, [])
		self.advance(0.4)
		self.assertLess(self.clock.now - started, suggestionLists._RETURN_WAIT + 0.3)
		self.assertEqual(self.said(), [suggestionLists.NO_SUGGESTIONS_YET], "the user is told, and stays where he is")
		self.assertEqual(self.stockRan, [], "NVDA's own Down Arrow does not run: in the box it walks into the buffer's \"Loading...\" and leaves it")

	def test_down_arrow_long_after_the_focus_arrived_does_not_wait(self):
		self.page.unitDelay = 99
		self.inUnitBox()
		self.clock.now += suggestionLists._RETURN_WINDOW + 1
		before = self.clock.slept
		self.press("downArrow")
		self.assertEqual(self.clock.slept, before)
		self.assertEqual(self.stockRan, ["downArrow"])

	def test_enter_chooses_a_unit_with_the_mouse(self):
		self.inUnitBox()
		self.clock.now += 1.0
		self.press("downArrow")
		self.press("downArrow")
		gesture = self.press("enter")
		self.assertEqual(gesture.sent, 0)
		self.assertEqual(self.page.unitText, "APT 2")
		self.assertEqual(self.said()[-1], "APT 2, selected")

	def test_the_fixed_choices_after_the_units_are_suggestions_too(self):
		self.inUnitBox()
		self.clock.now += 1.0
		self.press("downArrow")
		self.press("end")
		self.assertEqual(self.said()[-1], "I don't live in a unit, 7 of 7")
		self.press("enter")
		self.assertEqual(self.page.unitText, "I don't live in a unit")


class TheChoiceStaysWhileTheUnitsAreLookedAtTest(UnitTestCase):
	def test_control_z_after_a_visit_to_the_units_takes_the_address_choice_back(self):
		self.inUnitBox()
		self.clock.now += 1.0
		self.press("downArrow")
		self.press("downArrow")
		self.press("escape")  # the page closes the list; the visit is over
		self.assertIsNone(suggestionLists._session)
		nvdaStubs.spoken.clear()
		self.undo()
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])
		self.assertEqual(self.page.text, TYPED)

	def test_control_z_in_the_middle_of_a_visit_to_the_units_takes_it_back_too(self):
		# The tester pressed Control+Z while going down the list (10:04:04, 10:04:12): the page's own undo made it worse.
		self.inUnitBox()
		self.clock.now += 1.0
		self.press("downArrow")
		self.press("downArrow")
		self.assertIsNotNone(suggestionLists._session)
		nvdaStubs.spoken.clear()
		gesture = self.undo()
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])
		self.assertEqual(gesture.sent, 0)
		self.assertEqual(self.page.text, TYPED)
		self.assertIsNone(suggestionLists._session, "the visit is over")

	def test_a_visit_in_another_field_forgets_the_choice(self):
		self.choose(3)
		self.arrive(after=40)  # long after: the unit box is no part of the choice
		self.clock.now += 1.0
		self.page.focused = self.page.field
		self.page.listShowing = True
		self.press("downArrow")
		self.assertIsNone(suggestionLists._chosen)

	def test_a_modified_key_that_is_not_control_z_is_not_a_command_in_a_visit(self):
		self.inUnitBox()
		self.clock.now += 1.0
		self.press("downArrow")
		for key, modifiers in (("downArrow", ("control",)), ("z", ("control", "shift")), ("z", ("alt",))):
			with self.subTest(key=key, modifiers=modifiers):
				self.assertIsNone(self.plugin.getScript(visit.Gesture(self.page, key, *modifiers)))
		self.assertIsNotNone(suggestionLists._session)


class TakingBackAUnitTest(UnitTestCase):
	def chooseUnit(self, number=2):
		self.inUnitBox()
		self.clock.now += 1.0
		for _ in range(number):
			self.press("downArrow")
		self.press("enter")
		nvdaStubs.spoken.clear()

	def test_a_unit_that_was_chosen_can_be_taken_back(self):
		self.chooseUnit(2)
		self.assertEqual(self.page.unitText, "APT 2")
		self.assertEqual(suggestionLists._chosen.typed, "", "the box held nothing")
		gesture = self.undo()
		self.assertEqual(self.said(), [UNIT_UNDONE], "1.59 says which box is empty, and that the address choice is still there to take back")
		self.assertEqual(self.page.unitText, "")
		self.assertEqual(self.page.unitInputs, [""], "the page got an input event for the empty box")
		self.assertEqual(gesture.sent, 0)
		self.assertEqual(self.page.text, self.name(3), "the address is as it was")

	def test_the_page_then_shows_all_its_units_and_down_arrow_waits_for_them(self):
		self.chooseUnit(2)
		self.undo()
		started = self.clock.now
		self.press("downArrow")
		self.assertEqual(self.said(), [UNIT_UNDONE], "nothing more yet")
		self.advance(1.0)
		self.assertGreater(self.page.unitAskAt - started, 0.29, "the page asks 300 ms after the change")
		self.assertEqual(self.said()[-1], "Unit suggestions, list, APT 1, 1 of 7")
		self.press("downArrow")
		self.press("enter")
		self.assertEqual(self.page.unitText, "APT 2", "and another unit can be chosen")

	def test_the_address_choice_is_not_replaced_by_the_unit_choice(self):
		# 1.58 kept one choice: a second Control+Z was the page's own, which hid the unit box and left a list of the one address (the tester's
		# 1.58 log of 11:45, after he took his unit back). 1.59 keeps both: the second Control+Z takes the address choice back.
		self.chooseUnit(2)
		self.undo()
		nvdaStubs.spoken.clear()
		gesture = self.undo()
		self.assertEqual(self.page.keys, [], "a second Control+Z is not the page's")
		self.assertEqual(gesture.sent, 0)
		self.assertEqual(self.page.text, TYPED, "the address choice was taken back")
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"], "there is no earlier choice to say")

	def test_a_box_that_held_something_gets_it_back(self):
		self.inUnitBox()
		self.clock.now += 1.0
		self.page.unitText = "APT"  # the user typed "APT" and the page showed the units that contain it
		self.press("downArrow")
		self.press("enter")
		self.assertEqual(self.page.unitText, "APT 1")
		nvdaStubs.spoken.clear()
		self.undo()
		self.assertEqual(self.page.unitText, "APT")
		# 1.59: no "Control+Z again takes back the earlier choice": the box holds "APT" again, and a second Control+Z in a box that holds text
		# is left to the page (tests/test_v159_choiceHistory.py, TheWordsOnlySayWhatTheNextKeyDoesTest).
		self.assertEqual(self.said(), ["Choice undone, APT"])


class AFieldThatHeldNothingTest(UnitTestCase):
	"""NVDA's ``value`` is None for a field that holds nothing and for one it can't read: the field is asked again, and it is the second that
	offers nothing to put back."""

	def test_an_address_box_that_held_nothing_is_put_back_empty(self):
		self.page.text = ""
		self.choose(3)
		self.assertEqual(suggestionLists._chosen.typed, "")
		self.undo()
		self.assertEqual(self.page.text, "")
		self.assertEqual(self.page.inputs, [""])
		self.assertEqual(self.said(), ["Choice undone, Enter your home address (required) is empty"], "1.59 says which box is empty")

	def test_a_field_that_could_not_be_read_at_the_start_offers_nothing_to_put_back(self):
		self.page.unreadable = True
		self.choose(3)
		self.page.unreadable = False
		self.assertIsNone(suggestionLists._chosen)
		self.undo()
		self.assertEqual(self.page.keys, ["z"])

	def test_the_text_of_a_field_with_only_spaces_is_nothing(self):
		# NVDA's value is None for spaces only (IAccessible._get_value); the field answers with the spaces when it is asked again.
		self.page.text = "   "
		self.assertIsNone(self.page.field.value)
		self.assertEqual(suggestionLists._readText(self.page.field), "")
		self.choose(3)
		self.assertEqual(suggestionLists._chosen.typed, "")

	def test_read_text_tells_nothing_from_an_error(self):
		field = self.page.field
		self.page.text = ""
		self.assertEqual(suggestionLists._readText(field), "")
		self.page.text = "241 w"
		self.assertEqual(suggestionLists._readText(field), "241 w")
		self.page.unreadable = True
		self.assertIsNone(suggestionLists._readText(field))

	def test_normal_makes_one_line_of_words_and_nothing_of_none(self):
		self.assertEqual(suggestionLists._normal("  241   w  pine "), "241 w pine")
		self.assertEqual(suggestionLists._normal(None), "")
		self.assertEqual(suggestionLists._normal(""), "")


class WhenTheFocusCannotBeGivenBackTest(UnitTestCase):
	def test_the_text_is_put_back_and_the_user_told_all_the_same(self):
		self.inUnitBox()
		self.page.setFocusFails = True
		with self.assertLogs("nvda", level="DEBUG"):
			self.undo()
		self.assertEqual(self.page.text, TYPED)
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])

	def test_a_page_that_will_not_take_the_text_is_told_to_the_user(self):
		self.inUnitBox()
		self.page.accValueFails = True
		gesture = self.undo()
		self.assertEqual(self.said(), ["Can't put back what you typed"])
		self.assertEqual(gesture.sent, 0)


class TheBoxThePageMovedTheFocusToTest(UnitTestCase):
	"""NVDA gives the object of a field its focus event only in focus mode, and not at all while its buffer is not ready, so the box is known
	by when NVDA made its object: the assistant stamps the time on the objects of the fields it gives its class, as they are made."""

	def test_a_field_given_the_class_is_stamped_with_the_time_it_was_made(self):
		self.clock.now += 7
		field = self.page.makeUnitField()
		self.assertEqual(getattr(field, suggestionLists.MADE_AT), self.clock.now)

	def test_a_field_that_gets_no_class_is_not_stamped(self):
		raw = self.page.makeField(states=(State.EDITABLE, State.FOCUSABLE))
		self.assertFalse(self.hasClass(raw))
		self.assertFalse(hasattr(raw, suggestionLists.MADE_AT))

	def test_the_box_made_just_after_the_choice_is_part_of_it(self):
		self.choose(3)
		field = self.arrive()
		self.assertTrue(suggestionLists._madeAfter(field, suggestionLists._chosen))

	def test_the_box_made_a_while_after_the_choice_is_not(self):
		self.choose(3)
		field = self.arrive(after=suggestionLists._FOLLOW_SECONDS + 0.5)
		self.assertFalse(suggestionLists._madeAfter(field, suggestionLists._chosen))

	def test_a_box_made_before_the_choice_is_not(self):
		self.clock.now += 5
		earlier = self.page.makeUnitField()
		self.clock.now += 5
		self.choose(3)
		self.assertFalse(suggestionLists._madeAfter(earlier, suggestionLists._chosen))

	def test_an_object_without_the_stamp_is_not(self):
		self.choose(3)
		self.assertFalse(suggestionLists._madeAfter(self.page.button, suggestionLists._chosen))

	def test_the_address_box_made_again_is_the_field_of_the_choice_and_not_a_box_the_page_moved_the_focus_to(self):
		self.choose(3)
		self.clock.now += 0.5
		again = self.page.makeField()
		again.IA2UniqueID = self.page.field.IA2UniqueID
		self.page.focused = again
		self.undo()
		self.assertEqual(self.said(), [f"Choice undone, {TYPED}"])
		self.assertNotIn(("focus", "Enter your home address (required)"), self.page.events, "it has the focus: nothing to give back")

	def test_a_box_is_waited_for_after_the_page_moved_the_focus_to_it_and_not_long_after(self):
		field = self.inUnitBox()
		self.assertTrue(suggestionLists._expectsList(field))
		self.clock.now += suggestionLists._RETURN_WINDOW + 1
		self.assertFalse(suggestionLists._expectsList(field))

	def test_the_address_box_after_a_choice_is_not_waited_for(self):
		self.choose(2)
		self.assertFalse(suggestionLists._expectsList(self.page.field))


class TheWaitDoesNotHoldNvdaTest(UnitTestCase):
	"""NVDA's watchdog gives up on a core that has not come round for half a second and cancels the COM calls made until it does ("COM call
	cancelled", measured in the second NVDA from a second into a loop that slept between looks; 1.57's wait of up to 1.5 seconds was such a
	loop), so a key that waits for the page's list is waited with by NVDA's own timer (core.callLater): the thread is free between looks."""

	def test_the_wait_is_a_timer_and_not_a_sleep(self):
		self.inUnitBox()
		before = self.clock.slept
		self.press("downArrow")
		self.assertEqual(len(self.later), 1, "one look is asked for")
		self.advance(2.0)
		self.assertEqual(self.clock.slept, before, "nothing slept")

	def test_it_looks_again_every_fifty_milliseconds_until_the_time_is_up(self):
		self.page.unitDelay = 99
		self.inUnitBox()
		with mock.patch.object(suggestionLists, "_poll", wraps=suggestionLists._poll) as poll:
			self.press("downArrow")
			self.advance(suggestionLists._RETURN_WAIT + 0.5)
		self.assertAlmostEqual(poll.call_count, suggestionLists._RETURN_WAIT / suggestionLists._RETURN_STEP, delta=3)

	def test_two_down_arrows_during_the_wait_begin_the_visit_at_the_second_suggestion(self):
		self.inUnitBox()
		self.press("downArrow")
		self.advance(0.05)
		self.press("downArrow")
		self.assertEqual(suggestionLists._waiting.presses, 2)
		self.assertEqual(self.said(), [])
		self.assertEqual(self.stockRan, [], "the second Down Arrow is not NVDA's either")
		self.advance(1.0)
		self.assertEqual(self.said(), ["Unit suggestions, list, APT 2, 2 of 7"])
		self.assertIsNone(suggestionLists._waiting)

	def test_more_down_arrows_than_there_are_suggestions_stop_at_the_last(self):
		self.inUnitBox()
		for _ in range(10):
			self.press("downArrow")
		self.advance(1.0)
		self.assertEqual(self.said(), ["Unit suggestions, list, I don't live in a unit, 7 of 7"])

	def test_the_visit_goes_on_from_there(self):
		self.inUnitBox()
		self.press("downArrow")
		self.advance(1.0)
		self.press("downArrow")
		self.assertEqual(self.said()[-1], "APT 2, 2 of 7")

	def test_a_letter_typed_during_the_wait_ends_it_and_goes_to_the_page(self):
		self.inUnitBox()
		self.press("downArrow")
		gesture = self.press("a")
		self.assertEqual(gesture.sent, 1)
		self.assertIsNone(suggestionLists._waiting)
		self.advance(2.0)
		self.assertEqual(self.said(), [], "the units are not said when the user has gone on typing")
		self.assertIsNone(suggestionLists._session)

	def test_enter_during_the_wait_ends_it_and_is_nvdas(self):
		self.inUnitBox()
		self.press("downArrow")
		gesture = self.press("enter")
		self.assertEqual(gesture.sent, 1, "NVDA does what it does with the key: no script of its own here, the key to the page")
		self.assertIsNone(suggestionLists._waiting)
		self.advance(2.0)
		self.assertEqual(self.said(), [])

	def test_up_arrow_during_the_wait_ends_it_and_is_nvdas(self):
		self.inUnitBox()
		self.press("downArrow")
		self.press("upArrow")
		self.assertEqual(self.stockRan, ["upArrow"])
		self.advance(2.0)
		self.assertEqual(self.said(), [])

	def test_the_focus_moving_during_the_wait_ends_it(self):
		self.inUnitBox()
		self.press("downArrow")
		self.page.focused = self.page.button
		self.advance(2.0)
		self.assertEqual(self.said(), [])
		self.assertEqual(self.stockRan, [])
		self.assertIsNone(suggestionLists._waiting)

	def test_a_look_that_fails_sends_the_key_on(self):
		self.inUnitBox()
		self.press("downArrow")
		with mock.patch.object(suggestionLists, "_tryList", side_effect=RuntimeError("boom")), self.assertLogs("nvda", level="DEBUG"):
			self.advance(0.2)
		self.assertEqual(self.stockRan, ["downArrow"])
		self.assertIsNone(suggestionLists._waiting)

	def test_a_look_when_nothing_waits_does_nothing(self):
		suggestionLists._poll()
		self.assertEqual(self.said(), [])
		self.assertEqual(self.later, [])

	def test_the_wait_ends_once_with_a_word_if_no_list_comes(self):
		self.page.unitDelay = 99
		self.inUnitBox()
		self.press("downArrow")
		self.advance(5.0)
		self.assertEqual(self.said(), [suggestionLists.NO_SUGGESTIONS_YET])
		self.assertEqual(self.stockRan, [])
		self.assertEqual(self.later, [], "and nothing is asked for any more")
		self.assertIsNone(suggestionLists._waiting)

	def test_down_arrow_can_be_pressed_again_when_the_list_has_come_later(self):
		self.page.unitDelay = 2.0
		self.inUnitBox()
		self.press("downArrow")
		self.advance(suggestionLists._RETURN_WAIT + 0.3)
		self.assertEqual(self.said(), [suggestionLists.NO_SUGGESTIONS_YET])
		self.advance(1.0)  # the units are there now
		nvdaStubs.spoken.clear()
		self.press("downArrow")
		self.assertEqual(self.said(), ["Unit suggestions, list, APT 1, 1 of 7"])

	def test_a_list_that_is_read_while_the_page_replaces_its_nodes_is_looked_at_again(self):
		# visible.com's unit list says "Loading..." and then puts the units in its place: NVDA's COM call for a node that has just gone raises.
		self.inUnitBox()
		reads = {"count": 0}
		original = suggestionLists._suggestionList

		def flaky(field):
			reads["count"] += 1
			if reads["count"] <= 3:
				raise OSError("(-2147467259, 'Unspecified error')")
			return original(field)

		self.press("downArrow")
		with mock.patch.object(suggestionLists, "_suggestionList", flaky):
			self.advance(1.0)
		self.assertGreater(reads["count"], 3)
		self.assertEqual(self.said(), ["Unit suggestions, list, APT 1, 1 of 7"])
		self.assertEqual(self.stockRan, [], "the key did not go on")


class TheKeyboardHooksThreadTest(UnitTestCase):
	def hook(self, gesture):
		self.page.hook = True
		try:
			return suggestionLists.scriptFor(gesture)
		finally:
			self.page.hook = False

	def test_the_claim_of_control_z_in_the_unit_box_reads_nothing_of_nvdas_objects(self):
		self.inUnitBox()
		self.assertIs(self.hook(visit.Gesture(self.page, "z", "control")), suggestionLists._undoChoice)

	def test_the_claim_during_a_visit_reads_nothing_of_nvdas_objects_either(self):
		self.inUnitBox()
		self.clock.now += 1.0
		self.press("downArrow")
		self.assertIs(self.hook(visit.Gesture(self.page, "z", "control")), suggestionLists._undoChoice)

	def test_the_claim_is_for_control_z_alone(self):
		self.inUnitBox()
		for modifiers in (("control", "shift"), ("alt",), ("control", "alt"), ("shift",), ()):
			with self.subTest(modifiers=modifiers):
				self.assertIsNone(self.hook(visit.Gesture(self.page, "z", *modifiers)))

	def test_no_claim_when_nothing_was_chosen(self):
		self.assertIsNone(self.hook(visit.Gesture(self.page, "z", "control")))

	def test_no_claim_before_the_assistant_has_made_a_field(self):
		self.inUnitBox()
		with mock.patch.object(suggestionLists, "_overlay", None):
			self.assertIsNone(self.hook(visit.Gesture(self.page, "z", "control")))


class TheLogSaysWhatHappenedTest(UnitTestCase):
	def test_the_unit_box_and_the_taking_back_are_logged(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.inUnitBox()
			self.undo()
		text = "\n".join(logged.output)
		self.assertIn(f"Control+Z took the choice back: the field holds {TYPED!r} again and has the focus, which the page had moved to 'Enter Unit Label'", text)

	def test_something_typed_in_the_unit_box_is_logged(self):
		self.inUnitBox()
		self.page.unitText = "4B"
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.undo()
		self.assertIn("something is typed in the box the page moved the focus to", "\n".join(logged.output))

	def test_a_key_pressed_in_a_box_that_is_not_part_of_the_choice_is_logged(self):
		self.choose(3)
		self.arrive(after=suggestionLists._FOLLOW_SECONDS + 1)
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.undo()
		self.assertIn("nothing was chosen, or the focus is not where the choice was made", "\n".join(logged.output))


class SettingTest(unittest.TestCase):
	def test_the_follow_time_is_a_few_seconds(self):
		self.assertGreaterEqual(suggestionLists._FOLLOW_SECONDS, 2.0)
		self.assertLessEqual(suggestionLists._FOLLOW_SECONDS, 10.0)

	def test_unregistered_the_choice_and_the_wait_are_forgotten(self):
		with mock.patch.object(suggestionLists, "_chosen", object()), mock.patch.object(suggestionLists, "_returning", (object(), 1)), mock.patch.object(suggestionLists, "_waiting", object()), mock.patch.object(suggestionLists, "_enabled", True), mock.patch.object(suggestionLists, "_replaced", []):
			suggestionLists.unregister()
			self.assertIsNone(suggestionLists._chosen)
			self.assertIsNone(suggestionLists._returning)
			self.assertIsNone(suggestionLists._waiting)


if __name__ == "__main__":
	unittest.main()
