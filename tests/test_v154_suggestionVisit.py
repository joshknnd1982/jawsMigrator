# Unit tests for version 1.54, from the tester's second comment on issue 47 ("this is still not working"), after 1.46 had
# kept the focus in the field while browse mode was on a suggestion.
#
# 1.46 to 1.53 never took Down Arrow for a tester. 1.54 was tried in a second NVDA 2026.2 on its own Windows desktop, with
# Microsoft Edge 154 on the live page https://www.visible.com/shop/home-internet (input#address-input, role="listbox"
# #address-dropdown of twenty role="option" elements, the first seven in sight), 30 September 2026, and the shipped 1.53 was
# tried there too. What was measured, which these fakes follow:
# - NVDA looks for the script of a key in the keyboard hook's thread (the tester's log: "executeGesture ... winInputHook"). NVDA's
#   main thread is an STA, so NVDA's objects can't be read from the hook's thread: the COM call fails with "The application called
#   an interface that was marshalled for a different thread", NVDA catches it and gives an empty answer. 1.53's check for the
#   field's list (controllerFor, from getScript) said "none", so Down Arrow went to the page, which closed the list: the tester's
#   report. NVDA's debug log had the COMError the moment Down Arrow was pressed. The fake objects here raise when they are read in
#   the hook (Page.hook), which none of the earlier tests could do;
# - NVDA's browse mode buffer, made by nvdaHelper's gecko_ia2 backend, has ONE of the twenty suggestions (the backend renders only
#   the selected item of an interactive list), also after NVDA made the buffer again: the line after it is the "Check
#   availability" button. 1.46's tests imitated a buffer with all the suggestions in it;
# - the objects NVDA has for the list (the field's controllerFor, its next sibling) are all twenty, each with its name, its place
#   ("2 of 20", IAccessible2's group position) and its place on the screen; the ones scrolled out of the list's box are off screen,
#   with the place they would have below the box; making the twenty took about 200 ms;
# - the field's controllerFor was empty, with the list showing, after the address was cleared and typed again (once; another run
#   of the same steps had it); the list is the field's next sibling in both cases;
# - IAccessible2's scrollTo (NVDA's scrollIntoView) brings an option into the box, and NVDA reports its new place about twelve
#   milliseconds later (the old place right after scrollTo); a press at the new place chose it.
# The imitation here is NVDA's objects for the page, how NVDA finds the script of a key, a mouse and the page's reaction to it; the
# assistant's code is the real one.
# Run: python -m unittest tests.test_v154_suggestionVisit -v

import enum
import os
import sys
import types
import unittest
from collections import namedtuple
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import jawsMigrator  # noqa: E402
from jawsMigrator import suggestionLists  # noqa: E402


class Role(enum.Enum):
	EDITABLETEXT = "edit"
	COMBOBOX = "combo box"
	LIST = "list"
	LISTITEM = "list item"
	SECTION = "section"
	DOCUMENT = "document"
	BUTTON = "button"


class State(enum.Enum):
	EDITABLE = "editable"
	MULTILINE = "multi line"
	AUTOCOMPLETE = "has autocomplete"
	EXPANDED = "expanded"
	COLLAPSED = "collapsed"
	INVISIBLE = "invisible"
	OFFSCREEN = "off screen"
	FOCUSABLE = "focusable"
	SELECTABLE = "selectable"
	FOCUSED = "focused"


controlTypes = types.ModuleType("controlTypes")
controlTypes.Role, controlTypes.State = Role, State
textInfos = types.SimpleNamespace(POSITION_CARET="caret")

_Rect = namedtuple("Rect", "left top width height")

#: What NVDA says when it can't press a suggestion.
CANT_PRESS = "Can't press this suggestion, it is not on the screen. Make the window bigger or the page smaller."


class Rect(_Rect):
	"""NVDA's locationHelper.RectLTWH."""

	@property
	def center(self):
		return (self.left + self.width // 2, self.top + self.height // 2)


class NVDAObject:
	"""NVDAObjects.NVDAObject, as far as an overlay class goes: scripts are looked up with getScript."""

	def getScript(self, gesture):
		return None


class Ia2Web(NVDAObject):
	"""NVDAObjects.IAccessible.ia2Web.Ia2Web."""


class OtherObject(NVDAObject):
	"""An object that isn't on a web page in IAccessible2, as a UI Automation one."""


class ComThreadError(RuntimeError):
	"""NVDA's COMError -2147417842: an interface marshalled for another thread."""


class Clock:
	"""time.monotonic and time.sleep, with no waiting: sleeping moves the clock."""

	def __init__(self):
		self.now = 100.0
		self.slept = 0.0

	def monotonic(self):
		return self.now

	def sleep(self, seconds):
		self.now += seconds
		self.slept += seconds


def _com(method):
	"""A property of NVDA's objects that is read through COM: it fails in the keyboard hook's thread."""

	def read(self):
		if self.page.hook:
			raise ComThreadError(f"{type(self).__name__}.{method.__name__} was read in the keyboard hook's thread")
		return method(self)

	return property(read)


class Item(Ia2Web):
	"""An NVDA object of the page in Edge (IAccessible2)."""

	count = 0

	def __init__(self, page, role, name="", states=(), rect=None):
		self.page = page
		self._role, self._name = role, name
		self._states = set(states)
		self._rect = rect
		self._parent = None
		self._children = []
		self.treeInterceptor = None
		self.calls = []
		Item.count += 1
		self._ia2Window, self.IA2UniqueID = 4242, -2000 - Item.count

	@_com
	def IA2WindowHandle(self):
		# NVDA 2026.2 reads the window handle through COM the first time (then keeps it) and has the unique ID as a plain attribute (set in
		# IAccessible.__init__): so an identity looked up in the keyboard hook's thread fails here as it does there.
		return self._ia2Window

	def add(self, child):
		child._parent = self
		self._children.append(child)
		return child

	@_com
	def role(self):
		return self._role

	@_com
	def name(self):
		return self._name

	@_com
	def parent(self):
		return self._parent

	@_com
	def children(self):
		return self._children

	@_com
	def states(self):
		states = set(self._states)
		if self.page.focused is self:
			states.add(State.FOCUSED)
		if self.page.hidden(self):
			states.add(State.INVISIBLE)
		return states

	@_com
	def location(self):
		return self._rect

	@_com
	def hasIrrelevantLocation(self):
		"""NVDA 2026.2, source/NVDAObjects/__init__.py, _get_hasIrrelevantLocation, word for word."""
		states = self.states
		return State.INVISIBLE in states or State.OFFSCREEN in states or not self.location or not any(self.location)

	@_com
	def controllerFor(self):
		return []

	@_com
	def next(self):
		if self._parent is None:
			return None
		siblings = self._parent._children
		index = siblings.index(self)
		return siblings[index + 1] if index + 1 < len(siblings) else None

	@_com
	def childCount(self):
		return len([child for child in self._children if not self.page.hidden(child)])

	def invalidateCache(self):
		self.calls.append("invalidateCache")

	def scrollIntoView(self):
		self.calls.append("scrollIntoView")

	def __repr__(self):
		return f"<{self._role.value} {self._name!r}>"


class Listbox(Item):
	"""The list: NVDA makes the objects of its children each time ``children`` is read; ``childCount`` makes none."""

	def __init__(self, *args, **kwargs):
		self.reads = 0
		super().__init__(*args, **kwargs)

	@_com
	def children(self):
		self.reads += 1
		return self._children


class Field(Item):
	"""The address field: the browser says it controls the list while the page shows it, if it does."""

	@_com
	def controllerFor(self):
		return [self.page.list] if self.page.listShowing and self.page.relation else []


class Option(Item):
	"""A suggestion: where it is follows the list's scrolling, the way the page lays it out."""

	@_com
	def location(self):
		return self.page.optionRect(self)

	@_com
	def states(self):
		states = set(self._states) | {State.FOCUSABLE, State.SELECTABLE}
		if self.page.hidden(self):
			states.add(State.INVISIBLE)
		if self.page.listShowing and self.page.offscreen(self):
			states.add(State.OFFSCREEN)
		return states

	@_com
	def positionInfo(self):
		return {"indexInGroup": self.page.options.index(self) + 1, "similarItemsInGroup": len(self.page.options)}

	def scrollIntoView(self):
		self.calls.append("scrollIntoView")
		self.page.scrollTo(self)


class Page:
	"""The address field and its suggestions: the list is a box that shows ``rowsShown`` rows of ``ROW`` pixels."""

	ROW = 56
	ADDRESSES = tuple(f"241 W PINE ST, TOWN {i}, ST, 1000{i}, USA" for i in range(1, 11))

	def __init__(self, count=10, rowsShown=3.5):
		self.listShowing = True
		self.relation = True
		self.chosen = None
		self.scrollTop = 0
		#: Whether the code that runs is NVDA's keyboard hook's, where NVDA's objects can't be read.
		self.hook = False
		#: The keys the page got.
		self.keys = []
		#: How many reads of a place still give the place before a scroll, as NVDA did right after scrollTo.
		self.scrollLag = 0
		self._lag = 0
		self._before = 0
		self.document = Item(self, Role.DOCUMENT, "Shop Home Internet", rect=Rect(14, 143, 1573, 1067))
		self.wrapper = self.document.add(Item(self, Role.SECTION, rect=Rect(589, 308, 581, 410)))
		self.height = int(self.ROW * rowsShown)
		self.field = self.wrapper.add(self.makeField())
		self.list = self.wrapper.add(Listbox(self, Role.LIST, "Address suggestions", rect=Rect(589, 368, 581, self.height)))
		self.options = [self.list.add(Option(self, Role.LISTITEM, self.ADDRESSES[i % len(self.ADDRESSES)] + ("" if i < len(self.ADDRESSES) else f" {i}"))) for i in range(count)]
		self.button = self.wrapper.add(Item(self, Role.BUTTON, "Check availability", states={State.FOCUSABLE}, rect=Rect(589, 740, 200, 40)))
		self.focused = self.field

	def makeField(self, states=(State.EDITABLE, State.FOCUSABLE, State.AUTOCOMPLETE), role=Role.EDITABLETEXT):
		"""The address field, as NVDA makes it: the assistant is asked about it, and may add its class."""
		raw = Field(self, role, "Enter your home address (required)", rect=Rect(589, 308, 581, 60))
		raw._states = set(states)
		classes = [Ia2Web]
		suggestionLists.chooseOverlay(raw, classes)
		if classes[0] is Ia2Web:
			return raw
		made = type("Dynamic_" + "".join(cls.__name__ for cls in classes), (classes[0], type(raw)), {})
		field = made.__new__(made)
		field.__dict__.update(raw.__dict__)
		return field

	def hidden(self, obj):
		return not self.listShowing and (obj is self.list or obj in self.options)

	def optionRect(self, option):
		index = self.options.index(option)
		if self._lag > 0:
			self._lag -= 1
			top = self.list._rect.top + index * self.ROW - self._before
		else:
			top = self.list._rect.top + index * self.ROW - self.scrollTop
		return Rect(590, top, 560, self.ROW)

	def offscreen(self, option):
		"""NVDA's off screen state: all of the suggestion is outside its list's box, or outside the page (its document's rectangle)."""
		box, page = self.list._rect, self.document._rect
		top = box.top + self.options.index(option) * self.ROW - self.scrollTop
		bottom = top + self.ROW
		if bottom <= box.top or top >= box.top + box.height:
			return True
		return bottom <= page.top or top >= page.top + page.height

	def scrollTo(self, option):
		"""IAccessible2's scrollTo: the box scrolls as far as it takes to have the whole option in it."""
		top = self.options.index(option) * self.ROW
		self._before = self.scrollTop
		if top < self.scrollTop:
			self.scrollTop = top
		elif top + self.ROW > self.scrollTop + self.height:
			self.scrollTop = top + self.ROW - self.height
		self._lag = self.scrollLag

	def choose(self, option):
		self.chosen = option._name
		self.listShowing = False

	def keyDown(self, key):
		self.keys.append(key)


class Screen:
	"""The mouse pointer and what is under it: a press on a suggestion in the box chooses it (the page's mousedown)."""

	def __init__(self, page):
		self.page = page
		self.pointer = [10, 10]
		self.moves = []
		self.clicks = []

	def getCursorPos(self):
		return list(self.pointer)

	def setCursorPos(self, x, y):
		self.pointer = [x, y]
		self.moves.append((x, y))

	def doPrimaryClick(self):
		x, y = self.pointer
		self.clicks.append((x, y))
		if not self.page.listShowing:
			return
		box = self.page.list._rect
		if not (box.left <= x < box.left + box.width and box.top <= y < box.top + box.height):
			return
		for index, option in enumerate(self.page.options):
			top = box.top + index * self.page.ROW - self.page.scrollTop
			if top <= y < top + self.page.ROW:
				self.page.choose(option)
				return


class Gesture:
	"""NVDA's KeyboardInputGesture, as far as these scripts go."""

	def __init__(self, page, mainKeyName, *modifierNames, isModifier=False):
		self.page = page
		self.mainKeyName = mainKeyName
		self.modifiers = {(name, False) for name in modifierNames}
		self.isModifier = isModifier
		self.sent = 0

	@property
	def modifierNames(self):
		"""NVDA's KeyboardInputGesture.modifierNames: the names of the modifiers held."""
		return sorted(name for name, _ in self.modifiers)

	def send(self):
		self.sent += 1
		self.page.keyDown(self.mainKeyName)

	def __repr__(self):
		return "+".join([name for name, _ in sorted(self.modifiers)] + [self.mainKeyName])


class Document:
	"""The browse mode document: which mode it is in."""

	def __init__(self):
		self.isReady = True
		self.passThrough = True


class VisitTestCase(unittest.TestCase):
	#: The keys NVDA has a script for in an edit field in focus mode, which it runs, and then sends the key on (EditableText).
	STOCK_KEYS = ("downArrow", "upArrow", "home", "end", "leftArrow", "rightArrow", "pageDown")

	def setUp(self):
		nvdaStubs.spoken.clear()
		Item.count = 0
		self.stockRan = []
		self.page = Page()
		self.screen = Screen(self.page)
		self.document = Document()
		self.document.rootNVDAObject = self.page.document
		self.clock = Clock()
		#: What NVDA's own timer (core.callLater) was asked to run: (when it is due, the function, its arguments).
		self.later = []
		nvdaObjects = types.ModuleType("NVDAObjects")
		nvdaObjects.NVDAObject = NVDAObject
		iaccessible = types.ModuleType("NVDAObjects.IAccessible")
		ia2web = types.ModuleType("NVDAObjects.IAccessible.ia2Web")
		ia2web.Ia2Web = Ia2Web
		modules = {
			"controlTypes": controlTypes,
			"textInfos": textInfos,
			"api": types.SimpleNamespace(getFocusObject=lambda: self.page.focused),
			"core": types.SimpleNamespace(callLater=lambda delay, function, *args, **kwargs: self.later.append((self.clock.now + delay / 1000, function, args, kwargs))),
			"winUser": self.screen,
			"mouseHandler": self.screen,
			"scriptHandler": types.SimpleNamespace(findScript=lambda gesture: self.findScript(gesture)),
			"NVDAObjects": nvdaObjects,
			"NVDAObjects.IAccessible": iaccessible,
			"NVDAObjects.IAccessible.ia2Web": ia2web,
		}
		for patch in (
			mock.patch.dict(sys.modules, modules),
			mock.patch.object(suggestionLists, "time", self.clock),
			mock.patch.object(suggestionLists, "_enabled", True),
			mock.patch.object(suggestionLists, "_failed", False),
			mock.patch.object(suggestionLists, "_session", None),
			mock.patch.object(suggestionLists, "_declined", None),
			mock.patch.object(suggestionLists, "_pending", None),
			mock.patch.object(suggestionLists, "_waiting", None),
			mock.patch.object(suggestionLists, "_passing", False),
			mock.patch.object(suggestionLists, "_overlay", None),
			mock.patch.object(suggestionLists, "_noticed", set()),
		):
			patch.start()
			self.addCleanup(patch.stop)
		# The field was made while the assistant was off: make it again, as NVDA makes it when it is next needed.
		self.replaceField(self.page.makeField())
		self.plugin = object.__new__(jawsMigrator.GlobalPlugin)
		self.plugin._layerActive = False
		self.plugin._insertKeys = None
		self.plugin._suggestionLists = suggestionLists

	def advance(self, seconds):
		"""Time passes while NVDA's main thread is idle: what core.callLater was asked to run runs when it is due (the clock moves to it)."""
		end = self.clock.now + seconds
		while True:
			ready = sorted((item for item in self.later if item[0] <= end), key=lambda item: item[0])
			if not ready:
				break
			item = ready[0]
			self.later.remove(item)
			self.clock.now = max(self.clock.now, item[0])
			item[1](*item[2], **item[3])
		self.clock.now = max(self.clock.now, end)

	def replaceField(self, new):
		"""``new`` is the address field in the place of the one the page has."""
		old = self.page.field
		new._parent = old._parent
		siblings = old._parent._children
		siblings[siblings.index(old)] = new
		new.treeInterceptor = self.document
		self.page.field = self.page.focused = new
		return new

	def fieldWith(self, states, role=Role.EDITABLETEXT):
		return self.replaceField(self.page.makeField(states, role))

	@staticmethod
	def hasClass(obj):
		return any(cls.__name__ == "SuggestingField" for cls in type(obj).__mro__)

	# -- how NVDA finds the script of a key, and runs it ------------------------------------------------------------------

	def stock(self, gesture):
		"""NVDA's own script for the key in an edit field, if it has one: it sends the key to the page, as EditableText's does."""
		if gesture.mainKeyName not in self.STOCK_KEYS or gesture.modifiers:
			return None

		def script(gesture):
			self.stockRan.append(gesture.mainKeyName)
			gesture.send()

		return script

	def findScript(self, gesture):
		"""NVDA's scriptHandler.findScript: global plugins, then browse mode (when it is in browse mode), then the focus object."""
		script = self.plugin.getScript(gesture)
		if script is None and self.document.passThrough is False and gesture.mainKeyName == "downArrow":

			def script(gesture):
				self.stockRan.append("browse:" + gesture.mainKeyName)

		if script is None:
			script = self.page.focused.getScript(gesture)
		if script is None:
			script = self.stock(gesture)
		return script

	def press(self, key, *modifiers, isModifier=False):
		"""A key press: the script is looked for in the keyboard hook's thread, and runs in NVDA's main thread; no script, the key is the page's."""
		gesture = Gesture(self.page, key, *modifiers, isModifier=isModifier)
		self.page.hook = True
		try:
			script = self.findScript(gesture)
		finally:
			self.page.hook = False
		if script is not None:
			script(gesture)
		else:
			gesture.send()
		return gesture

	def said(self):
		return list(nvdaStubs.spoken)

	def name(self, number):
		return self.page.options[number - 1]._name


class WalkingThroughTheSuggestionsTest(VisitTestCase):
	def test_down_arrow_in_the_field_says_the_first_suggestion_with_its_list_and_place(self):
		gesture = self.press("downArrow")
		self.assertEqual(gesture.sent, 0, "the key never reaches the page, whose own Down Arrow would close the list")
		self.assertEqual(self.said(), [f"Address suggestions, list, {self.name(1)}, 1 of 10"])
		self.assertIs(self.page.focused, self.page.field, "the focus stays in the field")
		self.assertTrue(self.page.listShowing)
		self.assertEqual(self.stockRan, [], "NVDA's own Down Arrow did not run")

	def test_down_arrow_goes_through_all_the_suggestions_though_the_buffer_has_one(self):
		# What 1.46 to 1.53 could not do: their tests had every suggestion in browse mode's buffer, NVDA's has the selected one.
		for _ in range(10):
			self.press("downArrow")
		self.assertEqual(
			self.said(),
			[f"Address suggestions, list, {self.name(1)}, 1 of 10"] + [f"{self.name(number)}, {number} of 10" for number in range(2, 11)],
		)
		self.assertTrue(self.page.listShowing)
		self.assertEqual(self.page.keys, [], "no key went to the page")

	def test_each_next_suggestion_is_said_with_its_place_and_no_list(self):
		self.press("downArrow")
		self.press("downArrow")
		self.assertEqual(self.said()[1], f"{self.name(2)}, 2 of 10")

	def test_up_arrow_goes_back_and_stays_on_the_first(self):
		self.press("downArrow")
		self.press("downArrow")
		self.press("downArrow")
		self.press("upArrow")
		self.assertEqual(self.said()[-1], f"{self.name(2)}, 2 of 10")
		self.press("upArrow")
		self.press("upArrow")
		self.assertEqual(self.said()[-1], f"{self.name(1)}, 1 of 10")

	def test_down_arrow_stays_on_the_last_suggestion(self):
		for _ in range(12):
			self.press("downArrow")
		self.assertEqual(self.said()[-1], f"{self.name(10)}, 10 of 10")

	def test_home_and_end_go_to_the_first_and_the_last(self):
		self.press("downArrow")
		self.press("end")
		self.assertEqual(self.said()[-1], f"{self.name(10)}, 10 of 10")
		self.press("home")
		self.assertEqual(self.said()[-1], f"{self.name(1)}, 1 of 10")
		self.assertEqual(self.page.keys, [])

	def test_the_place_is_the_one_the_page_gives(self):
		with mock.patch.object(Option, "positionInfo", property(lambda self: {"indexInGroup": 3, "similarItemsInGroup": 40})):
			self.press("downArrow")
		self.assertEqual(self.said(), [f"Address suggestions, list, {self.name(1)}, 3 of 40"])

	def test_the_place_is_counted_when_the_page_gives_none(self):
		def none(self):
			raise NotImplementedError

		with mock.patch.object(Option, "positionInfo", property(none)):
			self.press("downArrow")
			self.press("downArrow")
		self.assertEqual(self.said()[1], f"{self.name(2)}, 2 of 10")

	def test_a_list_without_a_name_is_said_as_a_list(self):
		self.page.list._name = ""
		self.press("downArrow")
		self.assertEqual(self.said(), [f"list, {self.name(1)}, 1 of 10"])

	def test_the_objects_of_the_list_are_made_once_for_a_visit(self):
		# NVDA took about 200 ms to make twenty of them, which was each key's wait.
		self.page.list.reads = 0
		for _ in range(8):
			self.press("downArrow")
		self.assertEqual(self.page.list.reads, 1, "the list's objects were made once for eight keys")

	def test_a_page_that_shows_the_list_again_with_other_suggestions_is_gone_through_from_its_start(self):
		self.press("downArrow")
		self.press("downArrow")
		self.page.options[1]._name = "SOMETHING ELSE ENTIRELY"
		self.press("downArrow")
		self.assertEqual(self.said()[-1], f"Address suggestions, list, {self.name(1)}, 1 of 10", "the list is not the one gone through")

	def test_a_list_with_another_number_of_suggestions_is_gone_through_from_its_start(self):
		self.press("downArrow")
		self.press("downArrow")
		extra = self.page.list.add(Option(self.page, Role.LISTITEM, "ONE MORE"))
		self.page.options.append(extra)
		self.press("downArrow")
		self.assertEqual(self.said()[-1], f"Address suggestions, list, {self.name(1)}, 1 of 11")

	def test_the_visit_is_over_when_the_focus_moves(self):
		self.press("downArrow")
		other = self.page.wrapper.add(Item(self.page, Role.BUTTON, "Other", states={State.FOCUSABLE}))
		self.page.focused = other
		gesture = self.press("downArrow")
		self.assertEqual(self.stockRan, ["downArrow"], "NVDA's own")
		self.assertEqual(gesture.sent, 1)
		self.assertIsNone(suggestionLists._session)


class TheKeyboardHooksThreadTest(VisitTestCase):
	"""NVDA looks for a key's script in the keyboard hook's thread; none of NVDA's objects can be read there."""

	def test_the_fake_objects_raise_when_they_are_read_in_the_hook(self):
		self.page.hook = True
		for read in (lambda: self.page.field.states, lambda: self.page.field.controllerFor, lambda: self.page.list.children, lambda: self.page.field.next, lambda: self.page.field.role):
			with self.assertRaises(ComThreadError):
				read()

	def test_what_1_53_did_in_the_hook_is_not_possible(self):
		# 1.53's getScript read the field's states and its controllerFor, which in NVDA gave the answer "no suggestions".
		self.page.hook = True
		with self.assertRaises(ComThreadError):
			suggestionLists._suggestingField(self.page.field)

	def test_down_arrow_is_taken_with_nothing_of_nvdas_objects_read_in_the_hook(self):
		self.page.hook = True
		script = self.page.field.getScript(Gesture(self.page, "downArrow"))
		self.assertIsNotNone(script, "the field's class takes it: its script finds out, in the main thread, whether there are suggestions")

	def test_every_key_of_a_visit_is_looked_for_with_nothing_read_in_the_hook(self):
		for key in ("downArrow", "upArrow", "home", "end", "a", "tab", "escape", "enter", "space"):
			self.press("downArrow")
			self.press("downArrow")
			self.press(key)
		for key in ("shift", "control"):
			self.press("downArrow")
			self.press(key, isModifier=True)
		self.press("downArrow", "shift")

	def test_keys_pressed_at_once_after_down_arrow_are_the_visits_too(self):
		# The first Down Arrow makes the objects of the list, about 200 ms, and Enter may be pressed meanwhile: both are looked
		# for before the first runs.
		self.page.hook = True
		down = Gesture(self.page, "downArrow")
		enter = Gesture(self.page, "enter")
		first = self.findScript(down)
		second = self.findScript(enter)
		self.page.hook = False
		self.assertIsNotNone(second, "Enter is taken for the suggestion, which has not been said yet")
		first(down)
		second(enter)
		self.assertEqual(self.page.chosen, self.name(1))
		self.assertEqual(enter.sent, 0, "and Enter does not submit the form")

	def test_keys_taken_before_a_visit_began_pass_on_when_there_is_none(self):
		self.page.listShowing = False
		self.page.hook = True
		down = Gesture(self.page, "downArrow")
		up = Gesture(self.page, "upArrow")
		first = self.findScript(down)
		second = self.findScript(up)
		self.page.hook = False
		first(down)
		self.assertEqual(self.stockRan, ["downArrow"])
		self.assertIsNotNone(second, "taken, as the visit was not known to have been over")
		second(up)
		self.assertEqual(self.stockRan, ["downArrow", "upArrow"], "NVDA's own Up Arrow ran")

	def test_keys_are_not_taken_for_ever_after_down_arrow(self):
		self.page.listShowing = False
		self.press("downArrow")
		self.clock.now += suggestionLists._PENDING_SECONDS + 1
		self.page.hook = True
		self.assertIsNone(self.plugin.getScript(Gesture(self.page, "enter")))


class ChoosingTest(VisitTestCase):
	def test_enter_presses_the_suggestion_with_the_mouse_and_says_it(self):
		self.press("downArrow")
		self.press("downArrow")
		option = self.page.options[1]
		gesture = self.press("enter")
		self.assertEqual(gesture.sent, 0, "Enter is not sent to the page, which would submit the form")
		self.assertEqual(self.page.chosen, option._name)
		self.assertEqual(len(self.screen.moves), 2, "the pointer went to it and back")
		self.assertEqual(self.screen.moves[0], option.location.center)
		self.assertEqual(self.screen.moves[-1], (10, 10), "back where it was")
		self.assertEqual(self.screen.clicks, [option.location.center], "one press in the middle of it")
		self.assertEqual(self.said()[-1], f"{option._name}, selected")
		self.assertIs(self.page.focused, self.page.field, "the field keeps the focus, as when the mouse chooses")

	def test_space_and_numpad_enter_choose_too(self):
		for key in ("space", "numpadEnter"):
			with self.subTest(key):
				self.setUp()
				self.press("downArrow")
				self.press(key)
				self.assertEqual(self.page.chosen, self.name(1))

	def test_after_a_choice_the_keys_go_to_the_page(self):
		self.press("downArrow")
		self.press("enter")
		self.assertIsNone(suggestionLists._session)
		gesture = self.press("enter")
		self.assertEqual(gesture.sent, 1)

	def test_a_suggestion_out_of_the_boxs_sight_is_scrolled_in_and_pressed_where_it_is_then(self):
		for _ in range(9):
			self.press("downArrow")
		option = self.page.options[8]
		self.assertTrue(option.hasIrrelevantLocation, "off screen below the box")
		self.press("enter")
		self.assertEqual(self.page.chosen, option._name)
		self.assertIn("scrollIntoView", option.calls)
		self.assertIn("invalidateCache", option.calls, "NVDA reads its place again")
		x, y = self.screen.clicks[0]
		box = self.page.list._rect
		self.assertTrue(box.top <= y < box.top + box.height, "the press is in the list's box, on the suggestion that was chosen")

	def test_a_suggestion_only_partly_in_sight_is_pressed_where_it_shows(self):
		# The fourth row of 3.5 shows its top half: its middle is outside the box, where the mouse would press the page.
		for _ in range(4):
			self.press("downArrow")
		option = self.page.options[3]
		self.assertFalse(option.hasIrrelevantLocation, "NVDA says nothing is wrong with its place")
		self.press("enter")
		self.assertEqual(self.page.chosen, option._name)
		self.assertEqual(option.calls, [], "it shows enough to be pressed: no scrolling")
		x, y = self.screen.clicks[0]
		box = self.page.list._rect
		self.assertTrue(box.top <= y < box.top + box.height, "the press is in the list's box, not at the middle of the row, which is outside it")

	def test_a_suggestion_in_sight_is_not_scrolled(self):
		self.press("downArrow")
		self.press("enter")
		self.assertEqual(self.page.options[0].calls, [])

	def test_nvda_is_waited_for_when_it_reports_the_old_place_after_the_scroll(self):
		self.page.scrollLag = 6
		for _ in range(9):
			self.press("downArrow")
		self.press("enter")
		self.assertEqual(self.page.chosen, self.name(9))
		self.assertGreater(self.clock.slept, 0, "it looked again")
		self.assertLess(self.clock.slept, suggestionLists._SCROLL_WAIT)

	def test_a_suggestion_that_never_gets_to_its_place_is_not_pressed_and_the_user_is_told(self):
		self.page.scrollLag = 10**6
		for _ in range(9):
			self.press("downArrow")
		gesture = self.press("enter")
		self.assertIsNone(self.page.chosen)
		self.assertEqual(self.screen.clicks, [])
		self.assertEqual(self.said()[-1], CANT_PRESS)
		self.assertEqual(gesture.sent, 0, "and Enter doesn't submit the form")
		self.assertGreaterEqual(self.clock.slept, suggestionLists._SCROLL_WAIT)
		self.assertIsNotNone(suggestionLists._session, "the visit goes on")

	def test_the_pointer_goes_back_even_when_the_press_fails(self):
		self.press("downArrow")
		with mock.patch.object(self.screen, "doPrimaryClick", side_effect=OSError("no input")):
			with self.assertLogs("nvda", level="DEBUG"):
				gesture = self.press("enter")
		self.assertEqual(self.screen.pointer, [10, 10])
		self.assertEqual(gesture.sent, 1, "the key goes on as NVDA has it: no script of NVDA's, the key to the page")

	def test_a_suggestion_without_a_place_is_not_pressed(self):
		self.press("downArrow")
		with mock.patch.object(Option, "location", property(lambda self: Rect(0, 0, 0, 0))):
			self.press("enter")
		self.assertEqual(self.screen.clicks, [])
		self.assertEqual(self.said()[-1], CANT_PRESS)


class OtherKeysTest(VisitTestCase):
	def test_a_typed_letter_goes_to_the_page_and_ends_the_visit(self):
		self.press("downArrow")
		self.press("downArrow")
		gesture = self.press("a")
		self.assertEqual(gesture.sent, 1)
		self.assertIsNone(suggestionLists._session)
		self.press("downArrow")
		self.assertEqual(self.said()[-1], f"Address suggestions, list, {self.name(1)}, 1 of 10", "from the first, with the list again")

	def test_escape_tab_backspace_and_the_other_arrows_go_to_the_page(self):
		for key in ("escape", "tab", "backspace", "leftArrow", "rightArrow", "pageDown", "delete"):
			with self.subTest(key):
				self.setUp()
				self.press("downArrow")
				gesture = self.press(key)
				self.assertEqual(gesture.sent, 1, key)
				self.assertIsNone(suggestionLists._session)

	def test_a_key_with_a_modifier_is_no_command_here_and_the_visit_goes_on(self):
		self.press("downArrow")
		for key, modifiers in (("downArrow", ("shift",)), ("downArrow", ("control",)), ("downArrow", ("NVDA",)), ("enter", ("alt",))):
			with self.subTest(key=key, modifiers=modifiers):
				self.assertIsNone(self.plugin.getScript(Gesture(self.page, key, *modifiers)))
				self.assertIsNotNone(suggestionLists._session)
		self.press("downArrow")
		self.assertEqual(self.said()[-1], f"{self.name(2)}, 2 of 10")

	def test_a_modifier_key_alone_does_not_end_the_visit(self):
		self.press("downArrow")
		self.assertIsNone(self.plugin.getScript(Gesture(self.page, "shift", isModifier=True)))
		self.assertIsNotNone(suggestionLists._session)

	def test_up_arrow_and_enter_go_on_as_nvda_has_them_before_a_visit(self):
		for key in ("upArrow", "enter", "space", "home", "end"):
			with self.subTest(key):
				self.stockRan.clear()
				gesture = self.press(key)
				self.assertEqual(gesture.sent, 1, key)
				self.assertEqual(self.stockRan, [key] if key in self.STOCK_KEYS else [], "NVDA's own script, where it has one")


class WhereDownArrowIsNotTheKeyIntoTheSuggestionsTest(VisitTestCase):
	def nvdas(self):
		"""Down Arrow went to NVDA's own script, and so to the page, and nothing was said."""
		self.assertEqual(self.said(), [])
		self.assertEqual(self.stockRan, ["downArrow"])
		self.assertEqual(self.page.keys, ["downArrow"])

	def test_a_multi_line_field(self):
		self.assertFalse(self.hasClass(self.fieldWith({State.EDITABLE, State.FOCUSABLE, State.AUTOCOMPLETE, State.MULTILINE})))
		self.press("downArrow")
		self.nvdas()

	def test_a_combo_box(self):
		self.assertFalse(self.hasClass(self.fieldWith({State.EDITABLE, State.FOCUSABLE, State.AUTOCOMPLETE}, Role.COMBOBOX)))
		self.press("downArrow")
		self.nvdas()

	def test_an_expandable_field(self):
		for expandable in (State.EXPANDED, State.COLLAPSED):
			with self.subTest(expandable):
				self.assertFalse(self.hasClass(self.fieldWith({State.EDITABLE, State.FOCUSABLE, State.AUTOCOMPLETE, expandable})))

	def test_a_field_that_says_nothing_of_suggestions(self):
		self.assertFalse(self.hasClass(self.fieldWith({State.EDITABLE, State.FOCUSABLE})))
		self.press("downArrow")
		self.nvdas()

	def test_an_object_that_is_not_an_edit_field(self):
		raw = Field(self.page, Role.BUTTON, "Search", states={State.AUTOCOMPLETE, State.FOCUSABLE})
		classes = [Ia2Web]
		suggestionLists.chooseOverlay(raw, classes)
		self.assertEqual(classes, [Ia2Web])

	def test_an_edit_field_that_is_not_on_a_web_page_in_iaccessible2(self):
		raw = Field(self.page, Role.EDITABLETEXT, "Search", states={State.EDITABLE, State.FOCUSABLE, State.AUTOCOMPLETE})
		classes = [OtherObject]
		suggestionLists.chooseOverlay(raw, classes)
		self.assertEqual(classes, [OtherObject])

	def test_the_class_is_put_first_so_that_its_key_is_the_one_found(self):
		raw = Field(self.page, Role.EDITABLETEXT, "Search", states={State.EDITABLE, State.FOCUSABLE, State.AUTOCOMPLETE})
		classes = [Ia2Web]
		suggestionLists.chooseOverlay(raw, classes)
		self.assertEqual(len(classes), 2)
		self.assertEqual(classes[0].__name__, "SuggestingField")
		self.assertIs(classes[0], suggestionLists._overlayClass(), "one class for all of them")

	def test_a_closed_list_leaves_down_arrow_to_nvda(self):
		self.page.listShowing = False
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.press("downArrow")
		self.nvdas()
		self.assertTrue(any("no suggestions are showing for it" in line for line in logged.output), logged.output)

	def test_an_empty_list_leaves_down_arrow_to_nvda(self):
		self.page.list._children[:] = []
		self.press("downArrow")
		self.nvdas()

	def test_something_else_having_the_focus(self):
		self.page.focused = self.page.button
		self.press("downArrow")
		self.nvdas()

	def test_the_assistant_turned_off(self):
		with mock.patch.object(suggestionLists, "_enabled", False):
			self.press("downArrow")
		self.nvdas()
		raw = Field(self.page, Role.EDITABLETEXT, "Search", states={State.EDITABLE, State.FOCUSABLE, State.AUTOCOMPLETE})
		classes = [Ia2Web]
		with mock.patch.object(suggestionLists, "_enabled", False):
			suggestionLists.chooseOverlay(raw, classes)
		self.assertEqual(classes, [Ia2Web])

	def test_turned_off_during_a_visit_the_keys_are_nvdas(self):
		self.press("downArrow")
		with mock.patch.object(suggestionLists, "_enabled", False):
			self.assertIsNone(self.plugin.getScript(Gesture(self.page, "enter")))
			self.assertIsNone(self.page.field.getScript(Gesture(self.page, "downArrow")))

	def test_the_plugin_has_no_command_before_the_settings_are_applied(self):
		self.plugin._suggestionLists = None
		self.assertIsNone(self.plugin.getScript(Gesture(self.page, "downArrow")))
		self.assertIsNone(self.plugin.getScript(Gesture(self.page, "enter")))

	def test_keys_other_than_down_arrow_alone_are_not_taken_in_a_field_with_suggestions(self):
		for key, modifiers in (("downArrow", ("shift",)), ("downArrow", ("control",)), ("upArrow", ()), ("enter", ()), ("a", ())):
			with self.subTest(key=key, modifiers=modifiers):
				self.assertIsNone(self.page.field.getScript(Gesture(self.page, key, *modifiers)))
				self.assertIsNone(self.plugin.getScript(Gesture(self.page, key, *modifiers)))

	def test_a_modifier_key_alone_is_not_down_arrow(self):
		self.assertIsNone(self.page.field.getScript(Gesture(self.page, "downArrow", isModifier=True)))


class BrowseModeTest(VisitTestCase):
	def test_in_browse_mode_down_arrow_is_browse_modes(self):
		# Browse mode's script is looked for before the focus object's, so the field's class is not asked: browse mode has one
		# suggestion in its buffer and its Down Arrow goes on past it. Down Arrow in focus mode, as the tester types, is the way in.
		self.document.passThrough = False
		self.press("downArrow")
		self.assertEqual(self.stockRan, ["browse:downArrow"])
		self.assertEqual(self.said(), [])
		self.assertIsNone(suggestionLists._session)


class TheFieldDoesNotSayWhatItControlsTest(VisitTestCase):
	"""Edge 154 gave an empty controllerFor for the address field after the address was cleared and typed again."""

	def setUp(self):
		super().setUp()
		self.page.relation = False
		self.assertEqual(self.page.field.controllerFor, [])

	def test_the_list_that_follows_the_field_is_the_suggestions(self):
		self.press("downArrow")
		self.press("downArrow")
		self.assertEqual(self.said(), [f"Address suggestions, list, {self.name(1)}, 1 of 10", f"{self.name(2)}, 2 of 10"])
		self.press("enter")
		self.assertEqual(self.page.chosen, self.name(2))

	def test_a_list_above_the_field_is_found_too(self):
		self.page.list._rect = Rect(589, 308 - self.page.height, 581, self.page.height)
		self.press("downArrow")
		self.assertEqual(self.said(), [f"Address suggestions, list, {self.name(1)}, 1 of 10"])

	def test_a_list_after_the_container_of_the_field_is_found(self):
		holder = self.page.wrapper
		inner = Item(self.page, Role.SECTION, rect=Rect(589, 308, 581, 60))
		inner._parent = holder
		holder._children[holder._children.index(self.page.field)] = inner
		inner.add(self.page.field)
		self.press("downArrow")
		self.assertEqual(self.said(), [f"Address suggestions, list, {self.name(1)}, 1 of 10"])

	def test_a_list_far_from_the_field_is_not_its_suggestions(self):
		self.page.list._rect = Rect(589, 900, 581, self.page.height)
		self.press("downArrow")
		self.assertEqual(self.said(), [])
		self.assertEqual(self.stockRan, ["downArrow"])

	def test_a_list_beside_the_field_is_not_its_suggestions(self):
		self.page.list._rect = Rect(1300, 368, 300, self.page.height)
		self.press("downArrow")
		self.assertEqual(self.stockRan, ["downArrow"])

	def test_an_object_that_is_no_list_after_the_field_is_not_its_suggestions(self):
		self.page.list._role = Role.SECTION
		self.press("downArrow")
		self.assertEqual(self.stockRan, ["downArrow"])

	def test_a_hidden_list_after_the_field_is_not_its_suggestions(self):
		self.page.listShowing = False
		self.press("downArrow")
		self.assertEqual(self.stockRan, ["downArrow"])

	def test_the_list_the_field_does_control_is_used_before_the_one_after_it(self):
		self.page.relation = True
		elsewhere = self.page.document.add(Item(self.page, Role.LIST, "Elsewhere", rect=Rect(10, 10, 300, 200)))
		elsewhere.add(Item(self.page, Role.LISTITEM, "ELSEWHERE ONE"))
		with mock.patch.object(Field, "controllerFor", property(lambda self: [elsewhere])):
			self.press("downArrow")
		self.assertEqual(self.said(), ["Elsewhere, list, ELSEWHERE ONE, 1 of 1"])


class PassingAKeyOnTest(VisitTestCase):
	def test_a_key_is_sent_on_when_nvda_has_no_script_for_it(self):
		self.page.listShowing = False
		with mock.patch.object(VisitTestCase, "STOCK_KEYS", ()):
			gesture = self.press("downArrow")
		self.assertEqual(self.stockRan, [])
		self.assertEqual(gesture.sent, 1)

	def test_nvdas_script_is_looked_for_without_the_assistants_commands(self):
		# Not found again as the assistant's own: that would be asked again and again.
		seen = []
		real = self.findScript

		def watching(gesture):
			seen.append(suggestionLists._passing)
			return real(gesture)

		self.page.listShowing = False
		with mock.patch.dict(sys.modules, {"scriptHandler": types.SimpleNamespace(findScript=watching)}):
			self.press("downArrow")
		self.assertIn(True, seen)
		self.assertEqual(self.stockRan, ["downArrow"])
		self.assertFalse(suggestionLists._passing, "and not left that way")

	def test_a_failure_in_looking_for_it_sends_the_key_on_and_logs_once(self):
		self.page.listShowing = False

		def broken(gesture):
			raise RuntimeError("no scripts")

		with mock.patch.dict(sys.modules, {"scriptHandler": types.SimpleNamespace(findScript=broken)}):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				gesture = self.press("downArrow")
		self.assertEqual(gesture.sent, 1)
		self.assertFalse(suggestionLists._passing)
		self.assertTrue(any("could not find what NVDA does with a key" in line for line in logged.output), logged.output)


class WhenItCantTellTest(VisitTestCase):
	def test_a_field_that_cant_be_read_sends_the_key_on_and_logs_once(self):
		def fail(self):
			raise OSError("(-2147467259, 'Unspecified error')")

		with mock.patch.object(Field, "controllerFor", property(fail)):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				gesture = self.press("downArrow")
				self.press("downArrow")
		self.assertEqual(gesture.sent, 1, "the key is not lost")
		failures = [line for line in logged.output if "could not go through the field's suggestions" in line]
		self.assertEqual(len(failures), 1, logged.output)

	def test_a_press_that_cant_be_made_sends_the_key_on(self):
		self.press("downArrow")
		with mock.patch.object(suggestionLists, "_press", side_effect=RuntimeError("gone")):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				gesture = self.press("enter")
		self.assertEqual(gesture.sent, 1)
		self.assertTrue(any("could not choose the suggestion" in line for line in logged.output), logged.output)

	def test_a_list_that_vanished_between_the_decision_and_the_key_leaves_the_key_to_nvda(self):
		gesture = Gesture(self.page, "downArrow")
		self.page.hook = True
		script = self.findScript(gesture)
		self.page.hook = False
		self.assertIsNotNone(script)
		self.page.listShowing = False
		script(gesture)
		self.assertEqual(self.stockRan, ["downArrow"])
		self.assertEqual(gesture.sent, 1)

	def test_the_class_for_a_field_that_cant_be_read_is_left_out_and_logged_once(self):
		raw = Field(self.page, Role.EDITABLETEXT, "Field", rect=Rect(1, 1, 1, 1))

		def fail(self):
			raise OSError("gone")

		with mock.patch.object(Field, "states", property(fail)):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				classes = [Ia2Web]
				suggestionLists.chooseOverlay(raw, classes)
				suggestionLists.chooseOverlay(raw, classes)
		self.assertEqual(classes, [Ia2Web])
		self.assertEqual(len([line for line in logged.output if "could not tell whether an edit field has suggestions" in line]), 1)


class TheDecisionIsLoggedTest(VisitTestCase):
	def test_down_arrow_left_to_nvda_is_said_once_for_a_field(self):
		self.page.listShowing = False
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.press("downArrow")
			self.press("downArrow")
		lines = [line for line in logged.output if "goes on as NVDA has it" in line]
		self.assertEqual(len(lines), 1, logged.output)
		self.assertIn("Enter your home address (required)", lines[0])

	def test_a_field_given_the_class_is_said_once(self):
		suggestionLists._noticed.clear()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.page.makeField()
			self.page.makeField()
		lines = [line for line in logged.output if "says it has suggestions, so Down Arrow in it can go into them" in line]
		self.assertEqual(len(lines), 1, logged.output)
		self.assertIn("Enter your home address (required)", lines[0])

	def test_what_is_said_and_pressed_is_logged(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.press("downArrow")
			self.press("enter")
		text = "\n".join(logged.output)
		self.assertIn("suggestion 1 of 10 of the field's list said", text)
		self.assertIn("was pressed with the mouse", text)
		self.assertIn("the visit to the field's suggestions is over: the suggestion was chosen", text)


class SettingTest(unittest.TestCase):
	def test_the_setting_is_the_one_the_panel_and_the_state_use(self):
		self.assertEqual(suggestionLists.STATE_KEY, "chooseWebSuggestions")
		self.assertTrue(suggestionLists.wanted({}))
		self.assertFalse(suggestionLists.wanted({"chooseWebSuggestions": False}))

	def test_unregistered_the_visit_is_forgotten(self):
		with mock.patch.object(suggestionLists, "_session", object()), mock.patch.object(suggestionLists, "_pending", (object(), 1)), mock.patch.object(suggestionLists, "_enabled", True), mock.patch.object(suggestionLists, "_replaced", []):
			suggestionLists.unregister()
			self.assertIsNone(suggestionLists._session)
			self.assertIsNone(suggestionLists._pending)
			self.assertFalse(suggestionLists.isRegistered())


if __name__ == "__main__":
	unittest.main()
