# Unit tests for version 1.8, from a tester's report on version 1.7: checking a radio button in browse
# mode, NVDA said "checked" twice on visible.com, whose payment options rewrite their label when they are
# checked (changeRepeats). The imitation NVDA below does what NVDA 2026.2 does, as far as a control's name
# and states go: browseMode's _focusLastFocusableObject and event_gainFocus,
# speech.getObjectPropertiesSpeech with its notes of what was said (_speakObjectPropertiesCache), and
# objects that keep what they read until NVDA's core cycle ends. The notices come in the order of the
# tester's NVDA log. The assistant's own event handlers (GlobalPlugin.event_*) are the real ones.
# Run: python -m unittest tests.test_v18_fixes -v

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import jawsMigrator  # noqa: E402
from jawsMigrator import changeRepeats, labelRepeats, state  # noqa: E402

UNCHECKED = "As low as $49.97/mo for 36 months 0% APR + taxes, radio button not checked 1 of 2"
CHECKED = "As low as $49.97/mo for 36 months 0% APR + taxes, radio button checked 1 of 2"
#: The states NVDA says, in this imitation: "checked" when it comes, "not checked" when it goes.
SPOKEN_STATES = {"checked"}


class Control:
	"""A control on a web page, as the browser has it now."""

	def __init__(self, name, states):
		self.name = name
		self.states = set(states)


class NVDAObject:
	"""NVDA's object for a control: it keeps what it read from the browser until the core cycle ends."""

	def __init__(self, nvda, control, treeInterceptor):
		self.nvda = nvda
		self.control = control
		self.treeInterceptor = treeInterceptor
		self.appModule = None
		self._read = {}
		nvda.objects.append(self)

	def _get(self, name):
		if name not in self._read:
			value = getattr(self.control, name)
			self._read[name] = set(value) if isinstance(value, set) else value
		return self._read[name]

	name = property(lambda self: self._get("name"))
	states = property(lambda self: self._get("states"))

	def __eq__(self, other):
		return isinstance(other, NVDAObject) and other.control is self.control

	__hash__ = object.__hash__


class BrowseMode:
	"""A browse mode document: NVDA's tree interceptor."""

	passThrough = False
	_objPendingFocusBeforeActivate = None


class Nvda:
	def __init__(self, plugin):
		self.plugin = plugin
		self.objects = []
		self.spoken = []
		self.focus = None
		self.document = BrowseMode()

	def newObject(self, control):
		return NVDAObject(self, control, self.document)

	def endCycle(self):
		for obj in self.objects:
			obj._read.clear()

	def propertiesSpeech(self, obj, reason, *names):
		"""speech.getObjectPropertiesSpeech, for the name and the states."""
		new = {name: getattr(obj, name) for name in names}
		old = dict(getattr(obj, "_speakObjectPropertiesCache", {}))
		obj._speakObjectPropertiesCache = {**old, **new}
		if reason == "onlyCache":
			return []
		if reason == "change":
			for name in set(new) & set(old):
				if new[name] == old[name]:
					del new[name]
		sequence = [new["name"]] if "name" in new else []
		if "states" in new:
			gained = new["states"] - old.get("states", set()) if reason == "change" else new["states"]
			lost = old.get("states", set()) - new["states"] if reason == "change" else set()
			sequence += sorted(gained & SPOKEN_STATES) + [f"not {state}" for state in sorted(lost & SPOKEN_STATES)]
		return sequence

	def speak(self, sequence):
		if sequence:
			self.spoken.append(sequence)

	def pressSpaceInBrowseMode(self, obj, click):
		"""browseMode._focusLastFocusableObject(activatePosition=True): focus the control, note it, click it."""
		if obj != self.focus:
			self.propertiesSpeech(obj, "onlyCache", "name", "states")
			self.document._objPendingFocusBeforeActivate = obj
		click()

	def gainFocus(self, obj, sayActivation=True):
		"""The focus arrives: the assistant's handler, then browseMode's event_gainFocus (virtual caret already there)."""
		self.focus = obj

		def browseMode():
			pending = self.document._objPendingFocusBeforeActivate
			self.document._objPendingFocusBeforeActivate = None
			if self.document.passThrough:
				self.speak(self.propertiesSpeech(obj, "focus", "name", "states"))
				return
			self.propertiesSpeech(obj, "onlyCache", "name", "states")
			if sayActivation and pending is not None and pending == obj and pending is not obj:
				self.speak(self.propertiesSpeech(pending, "change", "name", "states"))

		self.plugin.event_gainFocus(obj, browseMode)

	def notice(self, obj, event, name):
		"""A notice from the browser (stateChange, IA2AttributeChange, nameChange): the assistant, then NVDA's object."""
		calls = []

		def nvdaObject():
			calls.append(event)
			if obj is self.focus:
				self.speak(self.propertiesSpeech(obj, "change", name))

		getattr(self.plugin, f"event_{event}")(obj, nvdaObject)
		assert calls == [event], "NVDA handles every notice, once"


def _plugin():
	"""The assistant's global plugin, as far as its event handlers go."""
	plugin = object.__new__(jawsMigrator.GlobalPlugin)
	plugin._sleepApps = set()
	plugin._changeRepeats = changeRepeats
	return plugin


class ActivationTests(unittest.TestCase):
	def setUp(self):
		changeRepeats.register()
		self.addCleanup(changeRepeats.unregister)
		self.nvda = Nvda(_plugin())

	def _checkTheTestersRadioButton(self, nameReadEarly=False):
		"""Space on "As low as $49.97/mo ..., radio button not checked 1 of 2", as in the tester's log."""
		nvda = self.nvda
		button = Control(UNCHECKED, {"checkable", "focusable"})
		# The virtual caret is on the button; the focus is elsewhere.
		nvda.focus = nvda.newObject(Control("Visible", set()))
		clicked = nvda.newObject(button)
		nvda.pressSpaceInBrowseMode(clicked, click=lambda: None)
		nvda.endCycle()
		# The browser moves the focus. NVDA makes an object for it and checks it before the click lands.
		focus = nvda.newObject(button)
		focus.states
		if nameReadEarly:
			focus.name
		# The click lands: the page checks the button and rewrites its label.
		button.states.add("checked")
		button.name = CHECKED
		nvda.gainFocus(focus)
		nvda.endCycle()
		return focus

	def test_the_testers_radio_button_says_checked_once(self):
		focus = self._checkTheTestersRadioButton()
		self.assertEqual(self.nvda.spoken, [[CHECKED, "checked"]], "browse mode says what the click changed")
		self.nvda.notice(focus, "stateChange", "states")
		self.assertEqual(self.nvda.spoken, [[CHECKED, "checked"]], "the button's own notice doesn't say it again")
		self.nvda.notice(focus, "stateChange", "states")
		self.assertEqual(len(self.nvda.spoken), 1)

	def test_nor_its_new_label(self):
		# The tester's first try: the focus object had read the old label too, so NVDA read the new one again.
		focus = self._checkTheTestersRadioButton(nameReadEarly=True)
		self.nvda.notice(focus, "nameChange", "name")
		self.nvda.notice(focus, "IA2AttributeChange", "states")
		self.nvda.notice(focus, "stateChange", "states")
		self.assertEqual(self.nvda.spoken, [[CHECKED, "checked"]])

	def test_nvda_alone_says_it_twice(self):
		# What NVDA does without the assistant, or with saying a control's type and state once turned off.
		changeRepeats.unregister()
		focus = self._checkTheTestersRadioButton(nameReadEarly=True)
		self.nvda.notice(focus, "nameChange", "name")
		self.nvda.notice(focus, "stateChange", "states")
		self.assertEqual(self.nvda.spoken, [[CHECKED, "checked"], [CHECKED], ["checked"]])

	def test_a_notice_in_the_same_cycle_keeps_it_for_the_next(self):
		# A notice NVDA handles before its objects read the browser again finds nothing new; the next one would.
		nvda = self.nvda
		button = Control("Pay today $1799 plus taxes", {"checkable"})
		nvda.focus = nvda.newObject(Control("Visible", set()))
		nvda.pressSpaceInBrowseMode(nvda.newObject(button), click=lambda: None)
		nvda.endCycle()
		focus = nvda.newObject(button)
		focus.states
		button.states.add("checked")
		nvda.gainFocus(focus)
		nvda.notice(focus, "stateChange", "states")
		nvda.endCycle()
		nvda.notice(focus, "IA2AttributeChange", "states")
		self.assertEqual(nvda.spoken, [["checked"]])

	def test_later_changes_are_said(self):
		nvda = self.nvda
		box = Control("Remember me", {"checkable"})
		nvda.focus = nvda.newObject(Control("Sign in", set()))
		nvda.pressSpaceInBrowseMode(nvda.newObject(box), click=lambda: None)
		nvda.endCycle()
		focus = nvda.newObject(box)
		focus.states
		box.states.add("checked")
		nvda.gainFocus(focus)
		nvda.endCycle()
		nvda.notice(focus, "stateChange", "states")
		self.assertEqual(nvda.spoken, [["checked"]])
		# Space again, and again: the focus is on the check box already, so each change comes as its notice.
		for expected in (["not checked"], ["checked"]):
			nvda.pressSpaceInBrowseMode(nvda.newObject(box), click=lambda: box.states.symmetric_difference_update({"checked"}))
			nvda.endCycle()
			nvda.notice(focus, "stateChange", "states")
			self.assertEqual(nvda.spoken[-1], expected)
		self.assertEqual(len(nvda.spoken), 3)

	def test_a_value_nvda_did_not_say_is_said(self):
		focus = self._checkTheTestersRadioButton()
		self.nvda.notice(focus, "stateChange", "states")
		# The page changes the label once more, to something NVDA hasn't said.
		focus.control.name = "Selected: As low as $49.97/mo"
		self.nvda.notice(focus, "nameChange", "name")
		self.assertEqual(self.nvda.spoken[-1], ["Selected: As low as $49.97/mo"])

	def test_only_what_browse_mode_said(self):
		nvda = self.nvda
		# Browse mode said nothing about the click (as in focus mode): the notice says "checked".
		button = Control("Silver", {"checkable"})
		nvda.focus = nvda.newObject(Control("Black", set()))
		nvda.pressSpaceInBrowseMode(nvda.newObject(button), click=lambda: None)
		nvda.endCycle()
		focus = nvda.newObject(button)
		focus.states
		button.states.add("checked")
		nvda.gainFocus(focus, sayActivation=False)
		nvda.endCycle()
		nvda.notice(focus, "stateChange", "states")
		self.assertEqual(nvda.spoken, [["checked"]])
		# A focus that no click brought: nothing is kept.
		other = Control("1 TB", {"checkable"})
		moved = nvda.newObject(other)
		nvda.gainFocus(moved)
		other.states.add("checked")
		nvda.endCycle()
		nvda.notice(moved, "stateChange", "states")
		self.assertEqual(nvda.spoken[-1], ["checked"])

	def test_not_after_a_few_seconds(self):
		with mock.patch.object(changeRepeats.time, "monotonic", return_value=1000.0):
			focus = self._checkTheTestersRadioButton()
		with mock.patch.object(changeRepeats.time, "monotonic", return_value=1000.0 + changeRepeats.REPEATS_WITHIN + 1):
			self.nvda.notice(focus, "stateChange", "states")
		self.assertEqual(self.nvda.spoken, [[CHECKED, "checked"], ["checked"]])

	def test_another_object_is_left_alone(self):
		focus = self._checkTheTestersRadioButton()
		other = self.nvda.newObject(focus.control)
		other._speakObjectPropertiesCache = {"states": {"checkable"}}
		self.nvda.plugin.event_stateChange(other, lambda: None)
		self.assertEqual(other._speakObjectPropertiesCache, {"states": {"checkable"}})
		# Another focus forgets what browse mode said.
		self.nvda.gainFocus(self.nvda.newObject(Control("Visible Protect Plan", set())))
		self.nvda.focus = focus
		self.nvda.notice(focus, "stateChange", "states")
		self.assertEqual(self.nvda.spoken[-1], ["checked"])

	def test_turned_off_with_saying_a_controls_type_and_state_once(self):
		self.assertTrue(changeRepeats.wanted(dict(state.DEFAULTS)))
		self.assertFalse(changeRepeats.wanted({labelRepeats.STATE_KEY: False}))
		changeRepeats.unregister()
		self.assertIsNone(changeRepeats.beforeFocus(object()))
		self.assertFalse(changeRepeats.isRegistered())

	def test_never_in_the_way_of_nvda(self):
		# Whatever goes wrong in the assistant, NVDA handles the focus and the notice, and nothing is changed.
		class Broken:
			@property
			def treeInterceptor(self):
				raise RuntimeError("broken for the test")

		calls = []
		plugin = self.nvda.plugin
		with mock.patch.object(changeRepeats, "_log"):
			plugin.event_gainFocus(Broken(), lambda: calls.append("gainFocus"))
			focus = self._checkTheTestersRadioButton()
			with mock.patch.object(NVDAObject, "states", property(lambda self: 1 / 0)):
				plugin.event_stateChange(focus, lambda: calls.append("stateChange"))
		self.assertEqual(calls, ["gainFocus", "stateChange"])
		plugin._changeRepeats = None
		plugin.event_nameChange(focus, lambda: calls.append("nameChange"))
		self.assertEqual(calls[-1], "nameChange")


if __name__ == "__main__":
	unittest.main()
