# Unit tests for version 1.60, from issue 51 (13 October 2026): "When I press x to check the box the check boxes don't get checked." on
# pizzahut.com. The log he named was on his own computer and never attached.
#
# The pizza builder (https://www.pizzahut.com/menu/pizza/builder?id=CLSS001P%7CPROD010B, measured on 6 November 2026) has 21 toppings, each a
# Material UI Accordion whose outer div has role="checkbox", aria-checked and aria-label="Pepperoni checkbox, unchecked", with no tabindex and
# no click handler: a click on it does nothing. Inside it are a heading, the topping's button (aria-expanded) and in the button the real check
# box (input type="checkbox", tabindex="-1", no name). A click on the button or on that check box adds the topping. NVDA's browse mode shows
# the outer div as one line, its label, and none of what is inside (nvdaHelper/vbufBackends/gecko_ia2/gecko_ia2.cpp: a check box's explicit
# label is its content and its children aren't rendered), so X goes to it and Space does its default action, a click that does nothing.
#
# 1.60 (innerControls): Space and Enter on such a check box activate the control inside it, and NVDA says "checked". The fakes below are NVDA's
# roles and states, browse mode's _activateNVDAObject as NVDA 2026.2 has it, NVDA's speech cache, core.callLater and the page.
# Run: python -m unittest tests.test_v160_innerControls -v

import enum
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import innerControls, state  # noqa: E402


class Role(enum.Enum):
	CHECKBOX = 1
	RADIOBUTTON = 2
	SWITCH = 3
	TOGGLEBUTTON = 4
	BUTTON = 5
	HEADING = 6
	GRAPHIC = 7
	STATICTEXT = 8
	SECTION = 9
	REGION = 10
	GROUPING = 11
	DOCUMENT = 12
	LINK = 13


class State(enum.Enum):
	"""NVDA's controlTypes.State, with its labels (controlTypes/state.py, NVDA 2026.2)."""

	FOCUSABLE = 1
	UNAVAILABLE = 2
	INVISIBLE = 3
	CHECKED = 4
	HALFCHECKED = 5
	PRESSED = 6
	HALF_PRESSED = 7
	ON = 8
	EXPANDED = 9
	COLLAPSED = 10
	FOCUSED = 11

	@property
	def displayString(self):
		return {"HALFCHECKED": "half checked", "HALF_PRESSED": "half pressed"}.get(self.name, self.name.lower())

	@property
	def negativeDisplayString(self):
		return {"CHECKED": "not checked", "PRESSED": "not pressed", "ON": "off", "SELECTED": "not selected"}.get(self.name, "not " + self.displayString)


class OutputReason(enum.Enum):
	FOCUS = 1
	CHANGE = 2
	ONLYCACHE = 3
	QUERY = 4



class Obj:
	"""An NVDAObject of a web page: its role, states, name, its children (firstChild and next), and what its default action does."""

	def __init__(self, role, name="", states=(), children=(), action=None):
		self.role = role
		self.name = name
		self.states = set(states)
		self.children = list(children)
		self.parent = None
		self.action = action
		self.actions = 0
		for child in self.children:
			child.parent = self

	@property
	def firstChild(self):
		return self.children[0] if self.children else None

	@property
	def next(self):
		if self.parent is None:
			return None
		siblings = self.parent.children
		index = next(i for i, sibling in enumerate(siblings) if sibling is self)
		return siblings[index + 1] if index + 1 < len(siblings) else None

	def doAction(self):
		self.actions += 1
		if self.action is not None:
			self.action()

	def __repr__(self):
		return f"<{self.role.name} {self.name!r}>"


class Page:
	"""The page's script: it changes what a click changed a moment later (React re-renders after the event)."""

	def __init__(self):
		self.pending = []
		self.clicks = []

	def later(self, change):
		self.pending.append(change)

	def run(self):
		pending, self.pending = self.pending, []
		for change in pending:
			change()


def topping(page, name="Pepperoni", checked=False):
	"""pizzahut.com's topping: the outer check box (not focusable, does nothing), its heading, button and the real check box in the button."""
	wrapper = Obj(Role.CHECKBOX, f"{name} checkbox, {'checked' if checked else 'unchecked'}", {State.CHECKED} if checked else ())

	def toggle(what):
		page.clicks.append((name, what))

		def change():
			on = State.CHECKED not in wrapper.states
			wrapper.states.discard(State.CHECKED)
			box.states.discard(State.CHECKED)
			if on:
				wrapper.states.add(State.CHECKED)
				box.states.add(State.CHECKED)
			wrapper.name = f"{name} checkbox, {'checked' if on else 'unchecked'}"
			button.states = {State.FOCUSABLE, State.EXPANDED if on else State.COLLAPSED}

		page.later(change)

	box = Obj(Role.CHECKBOX, "", {State.FOCUSABLE} | ({State.CHECKED} if checked else set()), action=lambda: toggle("check box"))
	button = Obj(
		Role.BUTTON,
		f"{name} option {name} add 50 cal/Slice",
		{State.FOCUSABLE, State.EXPANDED if checked else State.COLLAPSED},
		[Obj(Role.GRAPHIC, f"{name} option"), Obj(Role.STATICTEXT, name), Obj(Role.STATICTEXT, "add 50 cal/Slice"), box],
		action=lambda: toggle("button"),
	)
	heading = Obj(Role.HEADING, button.name, (), [button])
	wrapper.children = [heading]
	heading.parent = wrapper
	wrapper.action = lambda: page.clicks.append((name, "outer div"))
	wrapper.box, wrapper.button = box, button
	return wrapper


class BrowseModeTreeInterceptor:
	"""browseMode.BrowseModeTreeInterceptor._activateNVDAObject as NVDA 2026.2 has it, without the mouse."""

	rootNVDAObject = None

	def _activateNVDAObject(self, obj):
		while obj and obj != self.rootNVDAObject:
			try:
				obj.doAction()
				break
			except NotImplementedError:
				obj = obj.parent


NVDA_ACTIVATE = BrowseModeTreeInterceptor._activateNVDAObject


class Speech:
	"""ui.message: what NVDA says."""

	def __init__(self):
		self.said = []


class Core:
	"""core.callLater: what NVDA would run later, run by the test one step (LOOK_EVERY) at a time."""

	def __init__(self):
		self.queue = []

	def callLater(self, delay, callable, *args, **kwargs):
		self.queue.append((delay, callable, args, kwargs))


class InnerControlsTestCase(unittest.TestCase):
	def setUp(self):
		browseMode = types.ModuleType("browseMode")
		browseMode.BrowseModeTreeInterceptor = BrowseModeTreeInterceptor
		controlTypes = types.ModuleType("controlTypes")
		controlTypes.Role, controlTypes.State, controlTypes.OutputReason = Role, State, OutputReason
		self.speech = Speech()
		ui = types.ModuleType("ui")
		ui.message = self.speech.said.append
		self.core = Core()
		core = types.ModuleType("core")
		core.callLater = self.core.callLater
		self.focus = Obj(Role.DOCUMENT, "Pizza Hut", {State.FOCUSABLE})
		self.focusAncestors = []
		api = types.ModuleType("api")
		api.getFocusObject = lambda: self.focus
		api.getFocusAncestors = lambda: list(self.focusAncestors)
		modules = mock.patch.dict(sys.modules, {"browseMode": browseMode, "controlTypes": controlTypes, "ui": ui, "core": core, "api": api})
		modules.start()
		self.addCleanup(modules.stop)
		self.addCleanup(self._restoreNvda)
		innerControls._failed = False
		self.page = Page()
		self.document = BrowseModeTreeInterceptor()

	def _restoreNvda(self):
		innerControls.unregister()
		BrowseModeTreeInterceptor._activateNVDAObject = NVDA_ACTIVATE
		innerControls._replaced.clear()
		innerControls._failed = False

	def space(self, obj):
		"""Space in browse mode on ``obj``, as _activatePosition hands it to _activateNVDAObject."""
		self.document._activateNVDAObject(obj)

	def wait(self, steps=None):
		"""Time passes: the page makes its change at once, then NVDA runs what was called for later, one step at a time."""
		self.page.run()
		count = 0
		while self.core.queue and (steps is None or count < steps):
			delay, function, args, kwargs = self.core.queue.pop(0)
			self.assertEqual(delay, innerControls.LOOK_EVERY)
			function(*args, **kwargs)
			count += 1
		return count


class TheTestersToppingsTest(InnerControlsTestCase):
	def test_nvda_alone_clicks_the_outer_check_box_and_nothing_changes(self):
		pepperoni = topping(self.page)
		self.space(pepperoni)
		self.wait()
		self.assertEqual(self.page.clicks, [("Pepperoni", "outer div")], "issue 51: the click NVDA makes is on the div, which does nothing")
		self.assertNotIn(State.CHECKED, pepperoni.states)
		self.assertEqual(self.speech.said, [])

	def test_space_checks_the_topping_and_says_checked(self):
		innerControls.register()
		pepperoni = topping(self.page)
		self.space(pepperoni)
		self.assertEqual(self.page.clicks, [("Pepperoni", "check box")], "the real check box inside is activated")
		self.assertEqual(pepperoni.actions, 0, "and not the outer div")
		self.assertEqual(self.speech.said, [], "nothing is said before the page has made the change")
		self.wait()
		self.assertIn(State.CHECKED, pepperoni.states)
		self.assertEqual(pepperoni.name, "Pepperoni checkbox, checked")
		self.assertEqual(self.speech.said, ["checked"], "as NVDA says it for a check box with the focus")
		self.assertIsNone(innerControls._watched)

	def test_space_again_takes_the_topping_off(self):
		innerControls.register()
		pepperoni = topping(self.page)
		self.space(pepperoni)
		self.wait()
		self.speech.said.clear()
		self.space(pepperoni)
		self.wait()
		self.assertNotIn(State.CHECKED, pepperoni.states)
		self.assertEqual(self.speech.said, ["not checked"])
		self.assertEqual(self.page.clicks, [("Pepperoni", "check box")] * 2)

	def test_a_topping_already_on_the_pizza(self):
		innerControls.register()
		pepperoni = topping(self.page, checked=True)
		self.space(pepperoni)
		self.wait()
		self.assertEqual(self.speech.said, ["not checked"])

	def test_each_topping_is_its_own(self):
		innerControls.register()
		pepperoni, bacon = topping(self.page), topping(self.page, "Bacon")
		self.space(pepperoni)
		self.wait()
		self.space(bacon)
		self.wait()
		self.assertEqual(self.page.clicks, [("Pepperoni", "check box"), ("Bacon", "check box")])
		self.assertEqual(self.speech.said, ["checked", "checked"])
		self.assertIn(State.CHECKED, pepperoni.states)
		self.assertIn(State.CHECKED, bacon.states)

	def test_the_open_topping_still_uses_its_own_check_box(self):
		"""An added topping opens on its placement and its Extra switch, after the check box in the button."""
		innerControls.register()
		pepperoni = topping(self.page, checked=True)
		extra = Obj(Role.CHECKBOX, "Extra Pepperoni", {State.FOCUSABLE}, action=lambda: self.page.clicks.append(("Pepperoni", "extra")))
		place = Obj(Role.GROUPING, "Pepperoni placement", (), [Obj(Role.RADIOBUTTON, "Whole pizza", {State.FOCUSABLE, State.CHECKED})])
		region = Obj(Role.REGION, "", (), [place, extra])
		pepperoni.children.append(region)
		region.parent = pepperoni
		self.assertIs(innerControls.innerControl(pepperoni), pepperoni.box)

	def test_the_page_that_is_slow_to_change(self):
		innerControls.register()
		pepperoni = topping(self.page)
		change = None

		def slow():
			nonlocal change
			change = self.page.pending.pop()

		self.space(pepperoni)
		slow()
		self.assertEqual(self.wait(steps=5), 5)
		self.assertEqual(self.speech.said, [], "nothing yet: the page hasn't changed it")
		change()
		self.wait()
		self.assertEqual(self.speech.said, ["checked"], "said when the page changes it, within two seconds")

	def test_a_page_that_never_changes_it_says_nothing(self):
		innerControls.register()
		pepperoni = topping(self.page)
		self.space(pepperoni)
		self.page.pending.clear()
		looks = self.wait()
		self.assertEqual(looks, innerControls.LOOK_FOR // innerControls.LOOK_EVERY, "it stops looking after two seconds")
		self.assertEqual(self.speech.said, [])
		self.assertIsNone(innerControls._watched)

	def test_a_change_after_two_seconds_isnt_said(self):
		innerControls.register()
		pepperoni = topping(self.page)
		self.space(pepperoni)
		change = self.page.pending.pop()
		self.wait()
		change()
		self.wait()
		self.assertEqual(self.speech.said, [])

	def test_a_second_activation_says_only_its_own_change(self):
		innerControls.register()
		pepperoni, bacon = topping(self.page), topping(self.page, "Bacon")
		self.space(pepperoni)
		pepperoniChange = self.page.pending.pop()
		self.space(bacon)
		pepperoniChange()
		self.wait()
		self.assertEqual(self.speech.said, ["checked"], "Bacon's, once; Pepperoni's is no longer waited for")
		self.assertEqual(len(self.core.queue), 0)

	def test_the_page_takes_the_check_box_away(self):
		innerControls.register()
		pepperoni = topping(self.page)
		self.space(pepperoni)
		self.page.pending.clear()

		def gone(self):
			raise RuntimeError("COM object gone")

		with mock.patch.object(Obj, "states", property(gone), create=True):
			self.wait()
		self.assertEqual(self.speech.said, [])
		self.assertIsNone(innerControls._watched)
		self.assertFalse(innerControls._failed, "a control the page took away is not a failure")

	def test_the_browser_moves_the_focus_to_the_check_box_inside(self):
		"""Chrome focuses a check box it activates for NVDA: NVDA says it as the focus, "check box, checked", and the assistant says nothing."""
		innerControls.register()
		pepperoni = topping(self.page)
		self.space(pepperoni)
		self.focus = pepperoni.box
		self.focusAncestors = [self.document, pepperoni.parent, pepperoni, pepperoni.firstChild, pepperoni.button]
		self.wait()
		self.assertIn(State.CHECKED, pepperoni.states)
		self.assertEqual(self.speech.said, [])
		self.assertIsNone(innerControls._watched)

	def test_a_focus_event_a_moment_after_the_change(self):
		innerControls.register()
		pepperoni = topping(self.page)
		self.space(pepperoni)
		self.page.run()
		self.assertEqual(self.wait(steps=1), 1, "the first look sees the change")
		self.assertEqual(self.speech.said, [], "and looks once more for the focus")
		self.focus = pepperoni.box
		self.focusAncestors = [self.document, pepperoni.parent, pepperoni, pepperoni.firstChild, pepperoni.button]
		self.wait()
		self.assertEqual(self.speech.said, [], "NVDA says it, with the focus")

	def test_the_check_box_inside_is_focused_before_nvdas_focus_moves(self):
		"""Chrome gives the check box it activates the focused state at once; NVDA's focus event, and its speech, can come later."""
		innerControls.register()
		pepperoni = topping(self.page)
		self.space(pepperoni)
		pepperoni.box.states.add(State.FOCUSED)
		self.wait()
		self.assertIn(State.CHECKED, pepperoni.states)
		self.assertEqual(self.speech.said, [], "NVDA says it with the focus: check box, checked")

	def test_a_focus_event_that_never_comes(self):
		innerControls.register()
		pepperoni = topping(self.page)
		self.space(pepperoni)
		self.assertEqual(self.wait(), 2, "the change is seen at the first look and said at the second")
		self.assertEqual(self.speech.said, ["checked"])

	def addExtra(self, pepperoni):
		"""The added topping's panel: its placement and its Extra switch, inside the outer check box, after the button."""
		extra = Obj(Role.CHECKBOX, "Extra Pepperoni", {State.FOCUSABLE}, action=lambda: self.page.clicks.append(("Pepperoni", "extra")))
		whole = Obj(Role.RADIOBUTTON, "Whole pizza", {State.FOCUSABLE, State.CHECKED})
		region = Obj(Role.REGION, "", (), [Obj(Role.GROUPING, "Pepperoni placement", (), [whole]), extra])
		pepperoni.children.append(region)
		region.parent = pepperoni
		return extra, region

	def test_space_on_the_extra_switch_tabbed_to(self):
		"""Tab to Extra, inside the topping: browse mode's cursor stays on the topping, and Space is for Extra, not the topping."""
		innerControls.register()
		pepperoni = topping(self.page, checked=True)
		extra, region = self.addExtra(pepperoni)
		self.focus = extra
		self.focusAncestors = [self.document, pepperoni.parent, pepperoni, region]
		self.space(pepperoni)
		self.assertIsNone(innerControls._watched, "nothing to wait for: NVDA says the change of the focus")
		self.assertEqual(self.core.queue, [])
		self.wait()
		self.assertEqual(self.page.clicks, [("Pepperoni", "extra")])
		self.assertIn(State.CHECKED, pepperoni.states, "the topping stays on")
		self.assertEqual(self.speech.said, [], "NVDA says the change of the focus")
		self.assertIsNone(innerControls._watched)

	def test_the_focus_on_the_check_box_inside_already(self):
		innerControls.register()
		pepperoni = topping(self.page, checked=True)
		self.focus = pepperoni.box
		self.focusAncestors = [self.document, pepperoni.parent, pepperoni, pepperoni.firstChild, pepperoni.button]
		self.assertEqual(innerControls.target(pepperoni), (pepperoni.box, False))
		self.space(pepperoni)
		self.wait()
		self.assertEqual(self.page.clicks, [("Pepperoni", "check box")])
		self.assertNotIn(State.CHECKED, pepperoni.states)

	def test_the_focus_in_another_topping(self):
		innerControls.register()
		pepperoni, bacon = topping(self.page), topping(self.page, "Bacon")
		self.focus = bacon.box
		self.focusAncestors = [self.document, bacon.parent, bacon, bacon.firstChild, bacon.button]
		self.space(pepperoni)
		self.assertEqual(self.page.clicks, [("Pepperoni", "check box")])

	def test_the_focus_inside_on_something_that_cant_be_used(self):
		innerControls.register()
		pepperoni = topping(self.page, checked=True)
		extra, region = self.addExtra(pepperoni)
		extra.states.add(State.UNAVAILABLE)
		self.focus = extra
		self.focusAncestors = [self.document, pepperoni.parent, pepperoni, region]
		self.assertEqual(innerControls.target(pepperoni), (pepperoni.box, False))

	def test_nvda_says_it_itself_when_the_focus_is_in_it(self):
		"""After Tab to the topping's button: NVDA's event_stateChange says the change of a focus ancestor itself."""
		innerControls.register()
		pepperoni = topping(self.page)
		self.focus = pepperoni.button
		self.focusAncestors = [self.document, pepperoni.parent, pepperoni, pepperoni.firstChild]
		self.space(pepperoni)
		self.wait()
		self.assertIn(State.CHECKED, pepperoni.states)
		self.assertEqual(self.speech.said, [], "said once, by NVDA")


class TheWordsTest(InnerControlsTestCase):
	"""NVDA's speech of a change says "not checked" only for the focus (controlTypes.processAndLabelStates); the words here are NVDA's."""

	def setUp(self):
		super().setUp()
		innerControls.register()

	def words(self, before, now):
		return innerControls.changeWords(frozenset(before), frozenset(now))

	def test_checked_and_not_checked(self):
		self.assertEqual(self.words((), (State.CHECKED,)), ["checked"])
		self.assertEqual(self.words((State.CHECKED,), ()), ["not checked"])

	def test_half_checked(self):
		self.assertEqual(self.words((State.CHECKED,), (State.HALFCHECKED,)), ["half checked"], "not also \"not checked\"")
		self.assertEqual(self.words((State.HALFCHECKED,), (State.CHECKED,)), ["checked"])
		self.assertEqual(self.words((State.HALFCHECKED,), ()), ["not checked"], "as NVDA says it (#6946)")
		self.assertEqual(self.words((State.CHECKED, State.HALFCHECKED), ()), ["not checked"], "once")
		self.assertEqual(self.words((State.HALF_PRESSED,), ()), ["not pressed"])

	def test_pressed_and_on(self):
		self.assertEqual(self.words((), (State.PRESSED,)), ["pressed"])
		self.assertEqual(self.words((State.PRESSED,), (State.HALF_PRESSED,)), ["half pressed"])
		self.assertEqual(self.words((State.ON,), ()), ["off"])
		self.assertEqual(self.words((), (State.ON,)), ["on"])

	def test_a_radio_button_that_stands_for_one_inside_says_checked(self):
		radio = Obj(Role.RADIOBUTTON, "Whole pizza", {State.FOCUSABLE})
		wrapper = Obj(Role.RADIOBUTTON, "Whole pizza radio", (), [radio])
		radio.action = lambda: self.page.later(lambda: wrapper.states.add(State.CHECKED))
		self.space(wrapper)
		self.wait()
		self.assertEqual(self.speech.said, ["checked"])


class WhatIsLeftToNvdaTest(InnerControlsTestCase):
	def setUp(self):
		super().setUp()
		innerControls.register()

	def activated(self, obj):
		self.space(obj)
		self.wait()
		return self.page.clicks

	def test_a_check_box_the_page_made_focusable(self):
		"""pizzahut.com's Garlic-Parm Hut Blend: a div with role="checkbox" and tabindex="0", which a click checks."""
		garlic = Obj(Role.CHECKBOX, "Garlic-Parm Hut Blend checkbox, checked", {State.FOCUSABLE, State.CHECKED})
		garlic.action = lambda: self.page.clicks.append(("Garlic", "div"))
		box = Obj(Role.CHECKBOX, "", {State.FOCUSABLE, State.CHECKED}, action=lambda: self.page.clicks.append(("Garlic", "check box")))
		garlic.children = [Obj(Role.GRAPHIC, "Garlic-Parm Hut Blend option"), box]
		for child in garlic.children:
			child.parent = garlic
		self.assertEqual(self.activated(garlic), [("Garlic", "div")])
		self.assertEqual(self.speech.said, [], "NVDA moves the focus to it and says the change itself")

	def test_a_check_box_of_its_own(self):
		box = Obj(Role.CHECKBOX, "Remember me", action=lambda: self.page.clicks.append(("Remember me", "check box")))
		self.assertEqual(self.activated(box), [("Remember me", "check box")])
		self.assertIsNone(innerControls.innerControl(box))

	def test_a_check_box_with_nothing_to_use_inside(self):
		box = Obj(Role.CHECKBOX, "Extra cheese", (), [Obj(Role.GRAPHIC, "cheese"), Obj(Role.STATICTEXT, "Extra cheese")])
		box.action = lambda: self.page.clicks.append(("Extra cheese", "div"))
		self.assertEqual(self.activated(box), [("Extra cheese", "div")])

	def test_an_unavailable_check_box(self):
		pepperoni = topping(self.page)
		pepperoni.states.add(State.UNAVAILABLE)
		self.assertEqual(self.activated(pepperoni), [("Pepperoni", "outer div")])

	def test_controls_inside_that_cant_be_used(self):
		pepperoni = topping(self.page)
		pepperoni.box.states.add(State.UNAVAILABLE)
		pepperoni.button.states.add(State.INVISIBLE)
		self.assertIsNone(innerControls.innerControl(pepperoni))
		pepperoni.button.states.discard(State.INVISIBLE)
		self.assertIs(innerControls.innerControl(pepperoni), pepperoni.button, "the button, when the check box can't be used")

	def test_a_check_box_inside_that_the_page_didnt_make_focusable(self):
		"""A picture of a check box marked as one (role="checkbox", no tabindex) is not a control to use: the button is."""
		pepperoni = topping(self.page)
		pepperoni.box.states.discard(State.FOCUSABLE)
		self.assertIs(innerControls.innerControl(pepperoni), pepperoni.button)
		pepperoni.button.states.discard(State.FOCUSABLE)
		self.assertIsNone(innerControls.innerControl(pepperoni), "nothing inside the page made focusable")

	def test_a_button_when_there_is_no_check_box_inside(self):
		pepperoni = topping(self.page)
		pepperoni.button.children.remove(pepperoni.box)
		self.assertEqual(self.activated(pepperoni), [("Pepperoni", "button")])
		self.assertEqual(self.speech.said, ["checked"])

	def test_other_controls_inside_are_not_activated(self):
		link = Obj(Role.LINK, "Nutrition", {State.FOCUSABLE}, action=lambda: self.page.clicks.append(("link", "link")))
		box = Obj(Role.CHECKBOX, "Pepperoni checkbox, unchecked", (), [Obj(Role.STATICTEXT, "Pepperoni"), link])
		self.assertIsNone(innerControls.innerControl(box))

	def test_a_radio_button_that_stands_for_one_inside(self):
		radio = Obj(Role.RADIOBUTTON, "Whole pizza", {State.FOCUSABLE})
		wrapper = Obj(Role.RADIOBUTTON, "Whole pizza radio, unchecked", (), [Obj(Role.SECTION, "", (), [radio])])
		self.assertIs(innerControls.innerControl(wrapper), radio)
		other = Obj(Role.RADIOBUTTON, "Half", (), [Obj(Role.CHECKBOX, "", {State.FOCUSABLE})])
		self.assertIsNone(innerControls.innerControl(other), "a radio button stands only for a radio button or a button")

	def test_a_switch_that_stands_for_one_inside(self):
		box = Obj(Role.CHECKBOX, "", {State.FOCUSABLE})
		wrapper = Obj(Role.SWITCH, "Extra", (), [box])
		self.assertIs(innerControls.innerControl(wrapper), box)

	def test_other_roles_are_left_to_nvda(self):
		for role in (Role.BUTTON, Role.HEADING, Role.SECTION, Role.LINK):
			obj = Obj(role, "x", (), [Obj(Role.CHECKBOX, "", {State.FOCUSABLE})])
			self.assertIsNone(innerControls.innerControl(obj), role)

	def test_it_looks_no_further_than_it_should(self):
		deep = Obj(Role.CHECKBOX, "", {State.FOCUSABLE})
		node = deep
		for _ in range(innerControls.MOST_DEPTH):
			node = Obj(Role.SECTION, "", (), [node])
		self.assertIsNone(innerControls.innerControl(Obj(Role.CHECKBOX, "deep", (), [node])))
		many = [Obj(Role.STATICTEXT, str(i)) for i in range(innerControls.MOST_OBJECTS)]
		wide = Obj(Role.CHECKBOX, "wide", (), many + [Obj(Role.CHECKBOX, "", {State.FOCUSABLE})])
		self.assertIsNone(innerControls.innerControl(wide))
		near = Obj(Role.CHECKBOX, "", {State.FOCUSABLE})
		node = near
		for _ in range(innerControls.MOST_DEPTH - 2):
			node = Obj(Role.SECTION, "", (), [node])
		self.assertIs(innerControls.innerControl(Obj(Role.CHECKBOX, "near", (), [node])), near)

	def test_a_failure_leaves_the_activation_to_nvda(self):
		pepperoni = topping(self.page)
		with mock.patch.object(innerControls, "innerControl", side_effect=RuntimeError("COM error")):
			self.assertEqual(self.activated(pepperoni), [("Pepperoni", "outer div")])
		self.assertTrue(innerControls._failed)

	def test_no_object_at_the_caret(self):
		self.space(None)
		self.assertEqual(self.page.clicks, [])


class SettingTest(InnerControlsTestCase):
	def test_on_unless_turned_off(self):
		self.assertTrue(innerControls.wanted({}))
		self.assertTrue(innerControls.wanted({innerControls.STATE_KEY: True}))
		self.assertFalse(innerControls.wanted({innerControls.STATE_KEY: False}))
		self.assertFalse(innerControls.wanted(None))
		self.assertTrue(state.DEFAULTS[innerControls.STATE_KEY])

	def test_turned_off_gives_nvda_its_own_back(self):
		innerControls.register()
		self.assertIsNot(BrowseModeTreeInterceptor._activateNVDAObject, NVDA_ACTIVATE)
		self.assertTrue(innerControls.isRegistered())
		innerControls.unregister()
		self.assertIs(BrowseModeTreeInterceptor._activateNVDAObject, NVDA_ACTIVATE)
		self.assertFalse(innerControls.isRegistered())
		pepperoni = topping(self.page)
		self.space(pepperoni)
		self.assertEqual(self.page.clicks, [("Pepperoni", "outer div")])

	def test_turned_off_while_waiting(self):
		innerControls.register()
		pepperoni = topping(self.page)
		self.space(pepperoni)
		innerControls.unregister()
		self.wait()
		self.assertEqual(self.speech.said, [])

	def test_registered_twice_wraps_once(self):
		innerControls.register()
		installed = BrowseModeTreeInterceptor._activateNVDAObject
		innerControls.unregister()
		innerControls.register()
		innerControls.register()
		self.assertEqual(len(innerControls._replaced), 1)
		self.assertIs(getattr(BrowseModeTreeInterceptor._activateNVDAObject, innerControls.ORIGINAL), NVDA_ACTIVATE)
		self.assertIsNot(BrowseModeTreeInterceptor._activateNVDAObject, installed, "a new one after it was taken off")

	def test_another_add_on_wrapped_around_it(self):
		import functools

		innerControls.register()
		ours = BrowseModeTreeInterceptor._activateNVDAObject

		@functools.wraps(ours)
		def theirs(self, obj):
			return ours(self, obj)

		BrowseModeTreeInterceptor._activateNVDAObject = theirs
		innerControls.unregister()
		self.assertIs(BrowseModeTreeInterceptor._activateNVDAObject, theirs, "the other add-on's stays")
		self.space(topping(self.page, "Ham"))
		self.assertEqual(self.page.clicks, [("Ham", "outer div")], "turned off, the assistant's still in the chain does nothing")
		self.page.clicks.clear()
		innerControls.register()
		self.assertIs(BrowseModeTreeInterceptor._activateNVDAObject, theirs, "and isn't wrapped again")
		pepperoni = topping(self.page)
		self.space(pepperoni)
		self.assertEqual(self.page.clicks, [("Pepperoni", "check box")])

	def test_nvda_without_the_function(self):
		del BrowseModeTreeInterceptor._activateNVDAObject
		try:
			innerControls.register()
			self.assertTrue(innerControls._failed)
			self.assertEqual(innerControls._replaced, [])
		finally:
			BrowseModeTreeInterceptor._activateNVDAObject = NVDA_ACTIVATE


if __name__ == "__main__":
	unittest.main()
