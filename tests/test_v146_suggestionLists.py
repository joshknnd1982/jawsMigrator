# Unit tests for version 1.46, from a tester's report (issue 47): "You enter your address. They have suggested addresses.
# You can't get to them using NVDA." on https://www.visible.com/shop/home-internet.
# The page's address field (input#address-input, aria-autocomplete="list", aria-controls="address-dropdown") shows its
# suggestions in a role="listbox", each a div with role="option" and tabindex="0". Its script
# (clientlib-fioscheckavailability.min.js) was read and run in Chromium on 30 September 2026:
# - the field's keydown: ArrowDown moves the focus to the first suggestion (first.focus(), preventDefault);
# - the field's blur: setTimeout(closeAddressDropdown, 150), so the suggestion that has just been given the focus is
#   hidden 150 ms later and the focus falls to the page (the log there: "input blur", "dd focus", "dd blur");
# - a suggestion's mousedown chooses it (item.dispatchEvent(new MouseEvent("mousedown")) filled the field, and the list
#   closed); item.click() did nothing; Enter and Space on a focused suggestion choose it.
# NVDA 2026.2, in its source: Down Arrow in the field goes to the page (the first, above); browse mode's cursor on a list
# item chooses focus mode (ALWAYS_SWITCH_TO_PASS_THROUGH_ROLES) and _set_selection then sets the focus to it, with the
# migration's "Automatic focus mode for caret movement"; Enter sets the focus to it (_focusLastFocusableObject) and
# _activatePosition chooses focus mode for it, so nothing is pressed; doAction, where it is reached, sends a click alone.
# The tester's NVDA log of 30 September (1.43, NVDA 2026.2, Edge, 13:01:44 and 13:02:02) shows the first of those in NVDA itself: in
# focus mode Down Arrow in the field, with "has auto complete", said "Address suggestions, list, <address>, 1 of 20", then the
# field had the focus again and the list was gone (test_nvda_down_arrow_in_the_field_shows_the_first_suggestion_and_the_list_closes).
# The assistant's suggestionLists keeps the focus in the field while browse mode is on a suggestion, and presses the suggestion
# with the mouse.
# Version 1.54: this file was written for 1.46, which also had Down Arrow in the field go on in browse mode to the suggestions,
# and imitated a browse mode buffer with all of them in it. NVDA's buffer has one (the selected item of an interactive list, see
# test_v154_suggestionVisit), and the decision about Down Arrow ran in the keyboard hook's thread, where NVDA's objects can't be
# read, so 1.46 to 1.53 never took the key. Down Arrow in the field, going through the suggestions, and Enter are tested in
# test_v154_suggestionVisit; what is left here is what is kept from 1.46: browse mode's cursor on the suggestion its buffer
# has (focus stays in the field, Enter presses it with the mouse) and the way NVDA's methods are put in place and given back.
# The imitation NVDA runs NVDA 2026.2's own browseMode.BrowseModeTreeInterceptor.shouldPassThrough, _activateNVDAObject,
# _activatePosition, script_activatePosition and _focusLastFocusableObject, and BrowseModeDocumentTreeInterceptor's
# _activatePosition, _set_selection and _shouldSetFocusToObj, word for word; the page is visible.com's script, as above.
# The assistant's code is the real one.
# Run: python -m unittest tests.test_v146_suggestionLists -v

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
from jawsMigrator import autoFormsMode, state, suggestionLists  # noqa: E402

#: NVDA 2026.2, source/browseMode.py, BrowseModeTreeInterceptor: its roles for focus mode, and shouldPassThrough, word for word.
NVDA_ROLES_AND_DECISION = '''
	ALWAYS_SWITCH_TO_PASS_THROUGH_ROLES = frozenset(
		{
			controlTypes.Role.COMBOBOX,
			controlTypes.Role.EDITABLETEXT,
			controlTypes.Role.LIST,
			controlTypes.Role.LISTITEM,
			controlTypes.Role.SLIDER,
			controlTypes.Role.TABCONTROL,
			controlTypes.Role.MENUBAR,
			controlTypes.Role.POPUPMENU,
			controlTypes.Role.TREEVIEW,
			controlTypes.Role.TREEVIEWITEM,
			controlTypes.Role.SPINBUTTON,
			controlTypes.Role.TABLEROW,
			controlTypes.Role.TABLECELL,
			controlTypes.Role.TABLEROWHEADER,
			controlTypes.Role.TABLECOLUMNHEADER,
		},
	)

	SWITCH_TO_PASS_THROUGH_ON_FOCUS_ROLES = frozenset(
		{
			controlTypes.Role.LISTITEM,
			controlTypes.Role.RADIOBUTTON,
			controlTypes.Role.TAB,
			controlTypes.Role.MENUITEM,
			controlTypes.Role.RADIOMENUITEM,
			controlTypes.Role.CHECKMENUITEM,
		},
	)

	IGNORE_DISABLE_PASS_THROUGH_WHEN_FOCUSED_ROLES = frozenset(
		{
			controlTypes.Role.MENUITEM,
			controlTypes.Role.RADIOMENUITEM,
			controlTypes.Role.CHECKMENUITEM,
			controlTypes.Role.TABLECELL,
		},
	)

	def shouldPassThrough(self, obj, reason: OutputReason | None = None):
		"""Determine whether pass through mode should be enabled (focus mode) or disabled (browse mode) for a given object.
		@param obj: The object in question.
		@type obj: L{NVDAObjects.NVDAObject}
		@param reason: The reason for this query;
		one of the output reasons, or C{None} for manual pass through mode activation by the user.
		@return: C{True} if pass through mode (focus mode) should be enabled, C{False} if it should be disabled (browse mode).
		"""
		if reason and (
			self.disableAutoPassThrough
			or (
				reason == OutputReason.FOCUS
				and not config.conf["virtualBuffers"]["autoPassThroughOnFocusChange"]
			)
			or (
				reason == OutputReason.CARET
				and not config.conf["virtualBuffers"]["autoPassThroughOnCaretMove"]
			)
		):
			# This check relates to auto pass through and auto pass through is disabled, so don't change the pass through state.
			return self.passThrough
		if reason == OutputReason.QUICKNAV:
			return False
		states = obj.states
		role = obj.role
		if controlTypes.State.EDITABLE in states and controlTypes.State.UNAVAILABLE not in states:
			return True
		# Menus sometimes get focus due to menuStart events even though they don't report as focused/focusable.
		if (
			not obj.isFocusable
			and controlTypes.State.FOCUSED not in states
			and role != controlTypes.Role.POPUPMENU
		):
			return False
		# many controls that are read-only should not switch to passThrough.
		# However, there are exceptions.
		if controlTypes.State.READONLY in states:
			# #13221: For Slack message lists, and the MS Edge downloads window, switch to passthrough
			# even though the list item and list are read-only, but focusable.
			if (
				role == controlTypes.Role.LISTITEM
				and controlTypes.State.FOCUSED in states
				and obj.parent.role == controlTypes.Role.LIST
				and controlTypes.State.FOCUSABLE in obj.parent.states
			):
				return True
			# Certain controls such as combo boxes and readonly edits are read-only but still interactive.
			# #5118: read-only ARIA grids should also be allowed (focusable table cells, rows and headers).
			if role not in (
				controlTypes.Role.EDITABLETEXT,
				controlTypes.Role.COMBOBOX,
				controlTypes.Role.TABLEROW,
				controlTypes.Role.TABLECELL,
				controlTypes.Role.TABLEROWHEADER,
				controlTypes.Role.TABLECOLUMNHEADER,
			):
				return False
		# Any roles or states for which we always switch to passThrough
		if role in self.ALWAYS_SWITCH_TO_PASS_THROUGH_ROLES or controlTypes.State.EDITABLE in states:
			return True
		# focus is moving to this control. Perhaps after pressing tab or clicking a button that brings up a menu (via javascript)
		if reason == OutputReason.FOCUS:
			if role in self.SWITCH_TO_PASS_THROUGH_ON_FOCUS_ROLES:
				return True
			# If this is a focus change, pass through should be enabled for certain ancestor containers.
			# this is done last for performance considerations. Walking up the through the parents could be costly
			while obj and obj != self.rootNVDAObject:
				if obj.role == controlTypes.Role.TOOLBAR:
					return True
				obj = obj.parent
		return False
'''

#: NVDA 2026.2, source/browseMode.py, BrowseModeTreeInterceptor: _activateNVDAObject, _activatePosition, script_activatePosition
#: and _focusLastFocusableObject, word for word.
NVDA_ACTIVATION = '''
	def _activateNVDAObject(self, obj):
		"""Activate an object in response to a user request.
		This should generally perform the default action or click on the object.
		@param obj: The object to activate.
		@type obj: L{NVDAObjects.NVDAObject}
		"""
		while obj and obj != self.rootNVDAObject:
			try:
				obj.doAction()
				break
			except NotImplementedError:
				log.debugWarning("doAction failed")
			if obj.hasIrrelevantLocation:
				# This check covers invisible, off screen and a None location
				log.debugWarning("No relevant location for object")
				obj = obj.parent
				continue
			location = obj.location
			if not location.width or not location.height:
				obj = obj.parent
				continue
			log.debugWarning("Clicking with mouse")
			oldX, oldY = winUser.getCursorPos()
			winUser.setCursorPos(*location.center)
			mouseHandler.doPrimaryClick()
			winUser.setCursorPos(oldX, oldY)
			break

	def _activatePosition(self, obj=None):
		if not obj:
			obj = self.currentNVDAObject
			if not obj:
				return
		if obj.role == controlTypes.Role.MATH:
			import mathPres

			try:
				return mathPres.interactWithMathMl(obj.mathMl)
			except (NotImplementedError, LookupError):
				pass
			return
		if self.shouldPassThrough(obj):
			obj.setFocus()
			self.passThrough = True
			reportPassThrough(self)
		elif obj.role == controlTypes.Role.EMBEDDEDOBJECT or obj.role in self.APPLICATION_ROLES:
			obj.setFocus()
			speech.speakObject(obj, reason=OutputReason.FOCUS)
		else:
			self._activateNVDAObject(obj)

	def script_activatePosition(self, gesture: inputCore.InputGesture) -> None:
		self._focusLastFocusableObject(activatePosition=True)

	# Translators: the description for the activatePosition script on browseMode documents.
	script_activatePosition.__doc__ = _("Activates the current object in the document")

	def _focusLastFocusableObject(self, activatePosition=False):
		"""Used when auto focus focusable elements is disabled to sync the focus
		to the browse mode cursor.
		When auto focus focusable elements is disabled, NVDA doesn't focus elements
		as the user moves the browse mode cursor. However, there are some cases
		where the user always wants to interact with the focus; e.g. if they press
		the applications key to open the context menu. In these cases, this method
		is called first to sync the focus to the browse mode cursor.
		"""
		obj = self.currentFocusableNVDAObject
		if obj != self.rootNVDAObject and self._shouldSetFocusToObj(obj) and obj != api.getFocusObject():
			obj.setFocus()
			# We might be about to activate or pass through a key which will cause
			# this object to change (e.g. checking a check box). However, we won't
			# actually get the focus event until after the change has occurred.
			# Therefore, we must cache properties for speech before the change occurs.
			speech.speakObject(obj, OutputReason.ONLYCACHE)
			self._objPendingFocusBeforeActivate = obj
		if activatePosition:
			# Make sure we activate the object at the caret, which is not necessarily focusable.
			self._activatePosition()
'''

#: NVDA 2026.2, source/browseMode.py, BrowseModeDocumentTreeInterceptor: _activatePosition, _set_selection and
#: _shouldSetFocusToObj, word for word.
NVDA_DOCUMENT = '''
	def _activatePosition(self, obj=None, info=None):
		if info:
			obj = info.NVDAObjectAtStart
			if not obj:
				return
		super(BrowseModeDocumentTreeInterceptor, self)._activatePosition(obj=obj)

	def _set_selection(self, info, reason=OutputReason.CARET):
		super(BrowseModeDocumentTreeInterceptor, self)._set_selection(info)
		if isScriptWaiting() or not info.isCollapsed:
			return
		# Save the last caret position for use in terminate().
		# This must be done here because the buffer might be cleared just before terminate() is called,
		# causing the last caret position to be lost.
		caret = info.copy()
		caret.collapse()
		self._lastCaretPosition = caret.bookmark
		docID = self.documentConstantIdentifier
		if docID:
			# Update the cached document constant identifier
			# so it can be saved with the last caret position on termination.
			# As the original property may not be available as the document will be already dead.
			# Updating here is necessary as the identifier could have dynamically changed since initial load,
			# such as with  a SPA (single page app)
			self._lastCachedDocumentConstantIdentifier = self.documentConstantIdentifier
		review.handleCaretMove(caret)
		if reason == OutputReason.FOCUS:
			self._lastCaretMoveWasFocus = True
			focusObj = api.getFocusObject()
			if focusObj == self.rootNVDAObject:
				return
		else:
			self._lastCaretMoveWasFocus = False
			focusObj = info.focusableNVDAObjectAtStart
			obj = info.NVDAObjectAtStart
			if not obj:
				log.debugWarning("Invalid NVDAObjectAtStart")
				return
			if obj == self.rootNVDAObject:
				return
			obj.scrollIntoView()
			if self.programmaticScrollMayFireEvent:
				self._lastProgrammaticScrollTime = time.time()
		if focusObj:
			self.passThrough = self.shouldPassThrough(focusObj, reason=reason)
			if (
				not eventHandler.isPendingEvents("gainFocus")
				and focusObj != self.rootNVDAObject
				and focusObj != api.getFocusObject()
				and self._shouldSetFocusToObj(focusObj)
			):
				if self.passThrough:
					focusObj.setFocus()
			# Queue the reporting of pass through mode so that it will be spoken after the actual content.
			queueHandler.queueFunction(queueHandler.eventQueue, reportPassThrough, self)

	def _shouldSetFocusToObj(self, obj):
		"""Determine whether an object should receive focus.
		Subclasses may extend or override this method.
		@param obj: The object in question.
		@type obj: L{NVDAObjects.NVDAObject}
		"""
		return (
			obj.role not in self.APPLICATION_ROLES
			and obj.isFocusable
			and obj.role != controlTypes.Role.EMBEDDEDOBJECT
		)
'''


class Role(enum.Enum):
	"""NVDA's controlTypes.Role, as far as the page and NVDA's code above go."""

	EDITABLETEXT = "edit"
	COMBOBOX = "combo box"
	LIST = "list"
	LISTITEM = "list item"
	SLIDER = "slider"
	TABCONTROL = "tab control"
	MENUBAR = "menu bar"
	POPUPMENU = "menu"
	TREEVIEW = "tree view"
	TREEVIEWITEM = "tree view item"
	SPINBUTTON = "spin button"
	TABLEROW = "row"
	TABLECELL = "cell"
	TABLEROWHEADER = "row header"
	TABLECOLUMNHEADER = "column header"
	RADIOBUTTON = "radio button"
	TAB = "tab"
	MENUITEM = "menu item"
	RADIOMENUITEM = "radio menu item"
	CHECKMENUITEM = "check menu item"
	TOOLBAR = "toolbar"
	EMBEDDEDOBJECT = "embedded object"
	APPLICATION = "application"
	DIALOG = "dialog"
	MATH = "math"
	BUTTON = "button"
	DOCUMENT = "document"
	SECTION = "section"


class State(enum.Enum):
	"""NVDA's controlTypes.State, as far as the page and NVDA's code above go."""

	EDITABLE = "editable"
	UNAVAILABLE = "unavailable"
	FOCUSED = "focused"
	FOCUSABLE = "focusable"
	READONLY = "read only"
	MULTILINE = "multi line"
	AUTOCOMPLETE = "has autocomplete"
	EXPANDED = "expanded"
	COLLAPSED = "collapsed"
	INVISIBLE = "invisible"
	OFFSCREEN = "off screen"


class OutputReason(enum.Enum):
	FOCUS = "focus"
	CARET = "caret"
	QUICKNAV = "quickNav"
	ONLYCACHE = "onlyCache"


controlTypes = types.ModuleType("controlTypes")
controlTypes.Role, controlTypes.State, controlTypes.OutputReason = Role, State, OutputReason
textInfos = types.SimpleNamespace(POSITION_CARET="caret", UNIT_CONTROLFIELD="controlField", UNIT_CHARACTER="character")

_Rect = namedtuple("Rect", "left top width height")


class Rect(_Rect):
	"""NVDA's locationHelper.RectLTWH: where an object is on the screen."""

	@property
	def center(self):
		return (self.left + self.width // 2, self.top + self.height // 2)


class Obj:
	"""An NVDA object on the page in Chrome (IAccessible2): its role, name, states, place, parent and children."""

	def __init__(self, page, role, name="", states=(), rect=None, focusable=False):
		self.page, self.role, self.name = page, role, name
		self._states = set(states)
		self.location = rect
		self.focusable = focusable
		self.parent = None
		self.children = []
		self.treeInterceptor = None
		self.calls = []
		Obj.count += 1
		self.IA2WindowHandle, self.IA2UniqueID = 4242, -1000 - Obj.count

	count = 0

	def add(self, child):
		child.parent = self
		self.children.append(child)
		return child

	@property
	def states(self):
		states = set(self._states)
		if self.page.focused is self:
			states.add(State.FOCUSED)
		if self.page.hidden(self):
			states.add(State.INVISIBLE)
		return states

	@property
	def isFocusable(self):
		return self.focusable

	@property
	def controllerFor(self):
		return []

	@property
	def firstChild(self):
		return self.children[0] if self.children and not self.page.hidden(self.children[0]) else None

	@property
	def hasIrrelevantLocation(self):
		"""NVDA 2026.2, source/NVDAObjects/__init__.py, _get_hasIrrelevantLocation, word for word."""
		states = self.states
		return State.INVISIBLE in states or State.OFFSCREEN in states or not self.location or not any(self.location)

	def setFocus(self):
		self.calls.append("setFocus")
		self.page.focus(self)

	def doAction(self):
		self.calls.append("doAction")
		self.page.click(self)

	def scrollIntoView(self):
		pass

	def __repr__(self):
		return f"<{self.role.value} {self.name!r}>"


class Twin(Obj):
	"""The same element as another object, reached another way, with another class: NVDA's == is false for the two."""

	def __init__(self, original):
		super().__init__(original.page, original.role, original.name, original._states, original.location, original.focusable)
		self.parent, self.children, self.treeInterceptor = original.parent, original.children, original.treeInterceptor
		self.IA2WindowHandle, self.IA2UniqueID = original.IA2WindowHandle, original.IA2UniqueID


class Field(Obj):
	"""The address field: it controls the list, which is there while the page shows it."""

	@property
	def controllerFor(self):
		return [self.page.list] if self.page.listShowing else []


class Button(Obj):
	"""A menu button: it controls a list (aria-controls), and is no edit field."""

	@property
	def controllerFor(self):
		return [self.page.list]


class Page:
	"""visible.com's address field and suggestions, as the page's script does (see the top of this file)."""

	ADDRESSES = (
		"1600 PENNSYLVANIA AVE, GUILDERLAND, NY, 12084, USA",
		"1600 PENNSYLVANIA AVE, DALLAS, TX, 75215, USA",
		"1600 PENNSYLVANIA AVE NW, WASHINGTON, DC, 20502, USA",
	)

	def __init__(self):
		self.now = 0
		self.timers = []
		self.listShowing = True
		self.chosen = None
		self.document = Obj(self, Role.DOCUMENT, "Shop Home Internet & Save - Visible Wireless", rect=Rect(0, 0, 1280, 720))
		self.wrapper = self.document.add(Obj(self, Role.SECTION))
		self.input = self.wrapper.add(Field(self, Role.EDITABLETEXT, "Enter your home address (required)", rect=Rect(300, 130, 800, 40), focusable=True))
		self.input._states = {State.EDITABLE, State.FOCUSABLE, State.AUTOCOMPLETE}
		self.list = self.wrapper.add(Obj(self, Role.LIST, "Address suggestions", rect=Rect(300, 170, 800, 32 * len(self.ADDRESSES))))
		self.options = [
			self.list.add(Obj(self, Role.LISTITEM, address, states={State.FOCUSABLE}, rect=Rect(300, 170 + 32 * i, 800, 32), focusable=True))
			for i, address in enumerate(self.ADDRESSES)
		]
		self.focused = self.input

	def hidden(self, obj):
		return not self.listShowing and (obj is self.list or obj in self.options)

	def focus(self, target):
		"""element.focus(): the field's blur event starts the timer that closes the list."""
		previous, self.focused = self.focused, target
		if previous is self.input and target is not self.input:
			self.timers.append((self.now + 150, self.closeList))

	def closeList(self):
		self.listShowing = False
		if self.focused in self.options:
			# A hidden element can't have the focus: it falls to the page.
			self.focused = self.document

	def elapse(self, milliseconds):
		self.now += milliseconds
		for due, action in [timer for timer in self.timers if timer[0] <= self.now]:
			self.timers.remove((due, action))
			action()

	def keyDown(self, key):
		"""The key reaches the page, at the element that has the focus."""
		if self.focused is self.input:
			if key == "downArrow" and self.listShowing:
				self.focus(self.options[0])
			elif key == "escape":
				self.closeList()
		elif self.focused in self.options:
			index = self.options.index(self.focused)
			if key in ("enter", "space"):
				self.choose(self.focused)
			elif key == "downArrow" and index + 1 < len(self.options):
				self.focus(self.options[index + 1])
			elif key == "upArrow":
				self.focus(self.options[index - 1] if index else self.input)
			elif key == "escape":
				self.closeList()
				self.focus(self.input)

	def mouseDown(self, option):
		"""The suggestion's mousedown: chosen at once, and preventDefault keeps the focus where it is."""
		self.choose(option)

	def click(self, option):
		"""A click alone: the suggestions have no click event."""

	def choose(self, option):
		self.chosen = option.name
		self.closeList()


class Screen:
	"""The mouse pointer, and what is under it."""

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
		for option in self.page.options:
			left, top, width, height = option.location
			if left <= x < left + width and top <= y < top + height:
				# mousedown, mouseup, then click on what is under the pointer.
				self.page.mouseDown(option)
				return


class Gesture:
	"""NVDA's KeyboardInputGesture, as far as these scripts go: its main key, its modifiers and send()."""

	def __init__(self, page, mainKeyName, *modifierNames):
		self.page = page
		self.mainKeyName = mainKeyName
		self.modifierNames = list(modifierNames)
		self.modifiers = {(name, False) for name in modifierNames}
		self.sent = 0

	def send(self):
		self.sent += 1
		self.page.keyDown(self.mainKeyName)

	def __repr__(self):
		return "+".join(self.modifierNames + [self.mainKeyName])


class TreeInterceptor:
	"""treeInterceptorHandler.TreeInterceptor, as far as NVDA's code above goes."""

	isReady = True
	disableAutoPassThrough = False
	programmaticScrollMayFireEvent = False
	documentConstantIdentifier = None

	def __init__(self, page):
		self.page = page
		self.rootNVDAObject = page.document
		self.passThrough = False
		self.caret = page.input
		self.moved = []

	def _set_selection(self, info):
		self.caret = info.obj

	def _activatePosition(self, obj=None):
		raise AssertionError("NVDA's BrowseModeTreeInterceptor._activatePosition is defined below")

	@property
	def currentNVDAObject(self):
		return self.caret

	@property
	def currentFocusableNVDAObject(self):
		return Info(self, self.caret).focusableNVDAObjectAtStart

	def makeTextInfo(self, position):
		return Info(self, self.caret)

	def moveCaretTo(self, obj, reason=OutputReason.CARET):
		"""Browse mode's cursor moves to obj: NVDA's own _set_selection, as Down Arrow or a click does."""
		self.moved.append(obj)
		self._set_selection(Info(self, obj), reason)


class Info:
	"""A position in browse mode's document (a TextInfo): the object it is in, what was done to it."""

	isCollapsed = True

	def __init__(self, document, obj):
		self.document, self.obj = document, obj
		self.steps = []

	@property
	def bookmark(self):
		return self.obj

	@property
	def NVDAObjectAtStart(self):
		return self.obj

	@property
	def focusableNVDAObjectAtStart(self):
		obj = self.obj
		while obj is not None and obj is not self.document.rootNVDAObject:
			if obj.isFocusable:
				return obj
			obj = obj.parent
		return self.document.rootNVDAObject

	def copy(self):
		return self

	def collapse(self, end=False):
		self.steps.append(("collapse", "end" if end else "start"))

	def expand(self, unit):
		self.steps.append(("expand", unit))

	def move(self, unit, direction):
		self.steps.append(("move", unit, direction))
		return direction

	def updateCaret(self):
		self.document.caretSteps.append(self.steps)
		self.document.moveCaretTo(self.obj)


class Nvda:
	"""NVDA 2026.2's browse mode classes, built from its own code, around the page, a mouse and NVDA's settings."""

	def __init__(self, autoFocusMode=True):
		self.page = Page()
		self.screen = Screen(self.page)
		self.conf = {"virtualBuffers": {"autoPassThroughOnCaretMove": autoFocusMode, "autoPassThroughOnFocusChange": True}}
		self.queued = []
		self.reported = []
		self.said = []
		#: Whether another key is already waiting, as when keys are pressed quickly.
		self.scriptWaiting = False
		page = self.page
		namespace = {
			"controlTypes": controlTypes,
			"OutputReason": OutputReason,
			"TreeInterceptor": TreeInterceptor,
			"inputCore": types.SimpleNamespace(InputGesture=object),
			"_": lambda text: text,
			"config": types.SimpleNamespace(conf=self.conf),
			"api": types.SimpleNamespace(getFocusObject=lambda: page.focused),
			"winUser": self.screen,
			"mouseHandler": self.screen,
			"speech": types.SimpleNamespace(speakObject=lambda obj, reason=None: self.said.append((obj, reason))),
			"log": nvdaStubs.logging.getLogger("nvda"),
			"reportPassThrough": lambda document: self.reported.append(document.passThrough),
			"isScriptWaiting": lambda: self.scriptWaiting,
			"review": types.SimpleNamespace(handleCaretMove=lambda caret: None),
			"eventHandler": types.SimpleNamespace(isPendingEvents=lambda name: False),
			"queueHandler": types.SimpleNamespace(queueFunction=lambda queue, function, *args: function(*args), eventQueue=None),
			"time": types.SimpleNamespace(time=lambda: 0),
		}
		exec(
			"class BrowseModeTreeInterceptor(TreeInterceptor):\n"
			"\tAPPLICATION_ROLES = (controlTypes.Role.APPLICATION, controlTypes.Role.DIALOG)\n" + NVDA_ROLES_AND_DECISION + "\n\n" + NVDA_ACTIVATION + "\n",
			namespace,
		)
		exec("class BrowseModeDocumentTreeInterceptor(BrowseModeTreeInterceptor):\n" + NVDA_DOCUMENT + "\n", namespace)
		document = namespace["BrowseModeDocumentTreeInterceptor"]
		document.caretSteps = None
		self.browseMode = types.ModuleType("browseMode")
		self.browseMode.BrowseModeTreeInterceptor = namespace["BrowseModeTreeInterceptor"]
		self.browseMode.BrowseModeDocumentTreeInterceptor = document
		self.document = document(page)
		self.document.caretSteps = []
		for obj in (page.document, page.wrapper, page.input, page.list, *page.options):
			obj.treeInterceptor = self.document
		scriptHandler = types.SimpleNamespace(queueScript=lambda script, gesture: self.queued.append((script, gesture)))
		self.modules = {
			"controlTypes": controlTypes,
			"browseMode": self.browseMode,
			"api": namespace["api"],
			"winUser": self.screen,
			"mouseHandler": self.screen,
			"config": namespace["config"],
			"scriptHandler": scriptHandler,
			"textInfos": textInfos,
		}
		#: What NVDA has in place of each method, to compare with it afterwards.
		self.own = {
			name: vars(owner)[name]
			for owner, name in (
				(self.browseMode.BrowseModeTreeInterceptor, "shouldPassThrough"),
				(self.browseMode.BrowseModeDocumentTreeInterceptor, "_shouldSetFocusToObj"),
				(self.browseMode.BrowseModeTreeInterceptor, "_activateNVDAObject"),
			)
		}

	def press(self, key, *modifiers):
		"""A key press, as NVDA runs it: the assistant's plugin first, browse mode's scripts next, or the page gets it."""
		gesture = Gesture(self.page, key, *modifiers)
		script = None
		plugin = getattr(self, "plugin", None)
		if plugin is not None:
			script = plugin.getScript(gesture)
		if script is None and not self.document.passThrough:
			if key in ("enter", "space") and not modifiers:
				script = self.document.script_activatePosition
		if script is not None:
			script(gesture)
			self.runQueued()
		else:
			gesture.send()
		return gesture

	def runQueued(self):
		while self.queued:
			script, gesture = self.queued.pop(0)
			script(gesture)


class SuggestionListsTest(unittest.TestCase):
	def setUp(self):
		nvdaStubs.spoken.clear()
		self.nvda = Nvda()
		self.patches = [
			mock.patch.dict(sys.modules, self.nvda.modules),
			mock.patch.object(suggestionLists, "_failed", False),
			mock.patch.object(suggestionLists, "_enabled", False),
			mock.patch.object(suggestionLists, "_noted", None),
			mock.patch.object(suggestionLists, "_replaced", []),
		]
		for patch in self.patches:
			patch.start()
			self.addCleanup(patch.stop)
		self.addCleanup(suggestionLists.unregister)
		self.page = self.nvda.page
		self.document = self.nvda.document
		self.field = self.page.input

	def assistant(self):
		"""The assistant, running as it does once its settings are applied."""
		suggestionLists.register()
		plugin = object.__new__(jawsMigrator.GlobalPlugin)
		plugin._layerActive = False
		plugin._insertKeys = None
		plugin._suggestionLists = suggestionLists
		self.nvda.plugin = plugin
		return plugin

	def typed(self, passThrough=True):
		"""The address typed in the field: its list is showing, and the field has the focus, in focus mode."""
		self.document.passThrough = passThrough
		self.document.caret = self.field
		self.assertTrue(self.page.listShowing)
		self.assertIs(self.page.focused, self.field)

	def settle(self):
		self.page.elapse(500)

	# -- NVDA 2026.2 alone: what the tester met ------------------------------------------------------------------------------

	def test_nvda_down_arrow_in_the_field_shows_the_first_suggestion_and_the_list_closes(self):
		self.typed()
		self.nvda.press("downArrow")
		self.assertIs(self.page.focused, self.page.options[0], "the page moved the focus to the first suggestion")
		self.settle()
		self.assertFalse(self.page.listShowing, "the field's blur closed the list, 150 ms later")
		self.assertIs(self.page.focused, self.page.document, "and the focus fell to the page")
		self.assertIsNone(self.page.chosen)

	def test_nvda_browse_mode_on_a_suggestion_takes_the_focus_from_the_field(self):
		# Escape, then Down Arrow, with automatic focus mode for caret movement, which the migration turns on.
		self.typed(passThrough=False)
		self.document.moveCaretTo(self.page.options[0])
		self.assertTrue(self.document.passThrough, "a list item is one of the roles NVDA has focus mode for")
		self.assertEqual(self.page.options[0].calls, ["setFocus"])
		self.settle()
		self.assertFalse(self.page.listShowing)
		self.assertIsNone(self.page.chosen)

	def test_nvda_enter_on_a_suggestion_moves_the_focus_to_it_and_chooses_nothing(self):
		# NVDA's own setting, without the migration's: browse mode's cursor moving to the suggestion leaves the focus in the field.
		self.nvda.conf["virtualBuffers"]["autoPassThroughOnCaretMove"] = False
		self.typed(passThrough=False)
		self.document.moveCaretTo(self.page.options[0])
		self.assertEqual(self.page.options[0].calls, [], "the focus is still in the field")
		self.nvda.press("enter")
		self.assertEqual(self.page.options[0].calls, ["setFocus", "setFocus"], "Enter moved it, and _activatePosition moved it again")
		self.assertTrue(self.document.passThrough, "focus mode, and no activation")
		self.settle()
		self.assertFalse(self.page.listShowing)
		self.assertIsNone(self.page.chosen)

	def test_a_click_alone_chooses_nothing(self):
		# What NVDA's doAction, where it is reached, sends.
		self.page.click(self.page.options[0])
		self.assertIsNone(self.page.chosen)
		self.assertTrue(self.page.listShowing)

	# -- with the assistant ---------------------------------------------------------------------------------------------------

	def test_browse_mode_on_a_suggestion_keeps_the_focus_in_the_field(self):
		self.assistant()
		self.typed(passThrough=False)
		self.document.moveCaretTo(self.page.options[0])
		self.assertFalse(self.document.passThrough, "browse mode")
		self.assertEqual(self.page.options[0].calls, [], "the focus never leaves the field")
		self.settle()
		self.assertTrue(self.page.listShowing, "so the page doesn't close the list")
		self.assertIs(self.page.focused, self.field)

	def test_browse_mode_moves_from_one_suggestion_to_the_next_with_the_list_open(self):
		self.assistant()
		self.typed(passThrough=False)
		for option in self.page.options:
			self.document.moveCaretTo(option)
			self.settle()
		self.assertTrue(self.page.listShowing)
		self.assertFalse(self.document.passThrough)
		self.assertEqual([option.calls for option in self.page.options], [[], [], []])

	def test_focus_mode_still_comes_for_the_field_itself(self):
		self.assistant()
		self.typed(passThrough=False)
		self.document.moveCaretTo(self.page.options[0])
		self.document.moveCaretTo(self.field)
		self.assertTrue(self.document.passThrough, "browse mode's cursor back in the field: NVDA's own choice, focus mode")

	def test_enter_on_a_suggestion_presses_it_with_the_mouse(self):
		self.assistant()
		self.typed(passThrough=False)
		option = self.page.options[2]
		self.document.moveCaretTo(option)
		self.nvda.press("enter")
		self.assertEqual(self.page.chosen, "1600 PENNSYLVANIA AVE NW, WASHINGTON, DC, 20502, USA")
		self.assertEqual(self.nvda.screen.moves, [option.location.center, (10, 10)], "the pointer went to it, and back where it was")
		self.assertEqual(self.nvda.screen.clicks, [option.location.center], "one press, in the middle of the suggestion")
		self.assertEqual(option.calls, [], "no focus and no click alone")
		self.assertIs(self.page.focused, self.field, "the field keeps the focus, as when the mouse chooses")
		self.assertEqual(nvdaStubs.spoken, ["1600 PENNSYLVANIA AVE NW, WASHINGTON, DC, 20502, USA, selected"])

	def test_space_presses_it_too(self):
		self.assistant()
		self.typed(passThrough=False)
		self.document.moveCaretTo(self.page.options[1])
		self.nvda.press("space")
		self.assertEqual(self.page.chosen, "1600 PENNSYLVANIA AVE, DALLAS, TX, 75215, USA")

	def test_the_pointer_goes_back_even_when_the_press_fails(self):
		self.assistant()
		self.typed(passThrough=False)
		self.document.moveCaretTo(self.page.options[0])
		with mock.patch.object(self.nvda.screen, "doPrimaryClick", side_effect=OSError("no input")):
			self.nvda.press("enter")
		self.assertEqual(self.nvda.screen.pointer, [10, 10])
		self.assertEqual(self.page.options[0].calls, ["doAction"], "NVDA activates it as it does, once the press failed")

	def test_the_list_reached_through_the_field_is_the_list_the_option_is_in_though_nvda_calls_them_different(self):
		# controllerFor gives an object of another class than the option's parent, for the same element.
		self.assistant()
		twin = Twin(self.page.list)
		self.assertNotEqual(twin, self.page.list, "NVDA's own == says they aren't")
		self.typed(passThrough=False)
		with mock.patch.object(Field, "controllerFor", new_callable=mock.PropertyMock, return_value=[twin]):
			self.document.moveCaretTo(self.page.options[0])
			self.assertFalse(self.document.passThrough)
			self.assertEqual(self.page.options[0].calls, [])
			self.nvda.press("enter")
		self.assertEqual(self.page.chosen, self.page.options[0].name)

	def test_another_element_with_another_class_is_not_the_list(self):
		self.assistant()
		other = Twin(self.page.list)
		other.IA2UniqueID = 7
		self.typed(passThrough=False)
		with mock.patch.object(Field, "controllerFor", new_callable=mock.PropertyMock, return_value=[other]):
			self.document.moveCaretTo(self.page.options[0])
		self.assertTrue(self.document.passThrough, "NVDA's choice: another list")

	def test_the_suggestion_is_pressed_from_something_in_it_too(self):
		self.assistant()
		option = self.page.options[1]
		inner = option.add(Obj(self.page, Role.SECTION, "DALLAS", rect=option.location))
		inner.treeInterceptor = self.document
		self.typed(passThrough=False)
		self.document.moveCaretTo(inner)
		self.assertFalse(self.document.passThrough)
		self.assertEqual(option.calls, [])
		self.nvda.press("enter")
		self.assertEqual(self.page.chosen, option.name, "and what is said is the suggestion, not what is in it")

	# -- what stays as NVDA does it -------------------------------------------------------------------------------------------

	def test_a_suggestion_of_a_list_another_control_controls_is_left_to_nvda(self):
		# A menu button's list: the focus is on the button, which is no edit field.
		self.assistant()
		button = self.page.wrapper.add(Button(self.page, Role.BUTTON, "Sort by", states={State.FOCUSABLE}, focusable=True))
		button.treeInterceptor = self.document
		self.page.focused = button
		self.document.passThrough = False
		self.document.moveCaretTo(self.page.options[0])
		self.assertTrue(self.document.passThrough, "focus mode, as NVDA chooses for a list item")
		self.assertEqual(self.page.options[0].calls, ["setFocus"])

	def test_a_suggestion_of_another_field_is_left_to_nvda(self):
		self.assistant()
		other = self.page.wrapper.add(Field(self.page, Role.EDITABLETEXT, "Search", states={State.EDITABLE, State.FOCUSABLE, State.AUTOCOMPLETE}, rect=Rect(300, 400, 800, 40), focusable=True))
		other.treeInterceptor = self.document
		self.page.focused = other
		self.document.passThrough = False
		with mock.patch.object(Field, "controllerFor", new_callable=mock.PropertyMock, return_value=[]):
			self.document.moveCaretTo(self.page.options[0])
		self.assertTrue(self.document.passThrough, "the list isn't the one this field controls")

	def test_a_list_item_with_the_focus_on_it_is_left_to_nvda(self):
		# The page's own focus in the list: NVDA's focus event, as before.
		self.assistant()
		option = self.page.options[0]
		self.page.focused = option
		self.document.passThrough = False
		self.document.moveCaretTo(option, reason=OutputReason.FOCUS)
		self.assertTrue(self.document.passThrough)

	def test_the_field_that_isnt_a_suggestion_keeps_nvdas_choice(self):
		self.assistant()
		self.typed(passThrough=False)
		self.document.moveCaretTo(self.page.wrapper)
		self.assertFalse(self.document.passThrough, "the section round the field: browse mode, as NVDA chooses")

	def test_an_activation_without_a_place_on_the_screen_goes_on_to_nvda(self):
		self.assistant()
		self.typed(passThrough=False)
		option = self.page.options[0]
		option.location = Rect(0, 0, 0, 0)
		self.document.moveCaretTo(option)
		self.nvda.press("enter")
		self.assertEqual(self.nvda.screen.clicks, [])
		self.assertEqual(self.page.chosen, None)
		self.assertNotIn("setFocus", option.calls, "the focus stays in the field; NVDA's doAction and its own fallback are what is left")

	# -- when it can't tell -----------------------------------------------------------------------------------------------------

	def test_a_field_that_cant_be_read_leaves_everything_to_nvda_and_logs_once(self):
		self.assistant()
		self.typed(passThrough=False)
		with mock.patch.object(Field, "controllerFor", new_callable=mock.PropertyMock, side_effect=OSError("(-2147467259, 'Unspecified error')")):
			with self.assertLogs("nvda", level="DEBUG") as logged:
				self.document.moveCaretTo(self.page.options[0])
				self.document.moveCaretTo(self.page.options[1])
		self.assertTrue(self.document.passThrough, "NVDA's choice")
		failures = [line for line in logged.output if "could not tell whether browse mode is on a suggestion" in line]
		self.assertEqual(len(failures), 1, logged.output)

	# -- putting NVDA's methods in place, and back ------------------------------------------------------------------------------

	def test_registered_twice_it_is_put_in_once_and_unregistered_nvda_is_as_it_was(self):
		base = self.nvda.browseMode.BrowseModeTreeInterceptor
		document = self.nvda.browseMode.BrowseModeDocumentTreeInterceptor
		suggestionLists.register()
		suggestionLists.register()
		for name in ("shouldPassThrough", "_activateNVDAObject"):
			with self.subTest(name):
				self.assertIn(name, vars(document), "on the class of web pages' documents, calling the one above it")
				self.assertIs(vars(base)[name], self.nvda.own[name], "and nothing is put over NVDA's own on the class above")
		self.assertIs(vars(document)["_shouldSetFocusToObj"].__wrapped__, self.nvda.own["_shouldSetFocusToObj"], "wrapped once")
		self.assertTrue(suggestionLists.isRegistered())
		suggestionLists.unregister()
		self.assertNotIn("shouldPassThrough", vars(document))
		self.assertNotIn("_activateNVDAObject", vars(document))
		self.assertIs(vars(document)["_shouldSetFocusToObj"], self.nvda.own["_shouldSetFocusToObj"], "NVDA's own again")
		for name in ("shouldPassThrough", "_activateNVDAObject"):
			self.assertIs(vars(base)[name], self.nvda.own[name])
		self.assertFalse(suggestionLists.isRegistered())

	def test_turned_off_nvda_does_as_it_does(self):
		self.assistant()
		suggestionLists.unregister()
		self.typed(passThrough=False)
		self.document.moveCaretTo(self.page.options[0])
		self.assertTrue(self.document.passThrough)
		self.assertIsNone(self.nvda.plugin.getScript(Gesture(self.page, "downArrow")))

	def test_turned_off_while_another_add_ons_wrapper_is_over_ours_nothing_changes_for_the_user(self):
		suggestionLists.register()
		owner = self.nvda.browseMode.BrowseModeDocumentTreeInterceptor
		ours = vars(owner)["shouldPassThrough"]
		calls = []

		def theirs(self, obj, *args, **kwargs):
			calls.append(obj)
			return ours(self, obj, *args, **kwargs)

		theirs.__wrapped__ = ours
		owner.shouldPassThrough = theirs
		suggestionLists.unregister()
		self.assertIs(vars(owner)["shouldPassThrough"], theirs, "theirs is left in place")
		self.typed(passThrough=False)
		self.document.moveCaretTo(self.page.options[0])
		self.assertTrue(self.document.passThrough, "and ours, inside it, is off")
		suggestionLists.register()
		self.assertIs(vars(owner)["shouldPassThrough"], theirs, "turned on again, ours is still under theirs: not wrapped twice")

	def test_it_works_with_the_wrapper_that_keeps_browse_mode_on_tabs_and_toolbars(self):
		# autoFormsMode wraps the same method of NVDA, with its own marks.
		for first, second in ((autoFormsMode, suggestionLists), (suggestionLists, autoFormsMode)):
			with self.subTest(order=[first.__name__, second.__name__]):
				self.setUp()
				with mock.patch.object(autoFormsMode, "_replaced", []), mock.patch.object(autoFormsMode, "_enabled", False), mock.patch.object(autoFormsMode, "_noting", False):
					first.register()
					second.register()
					self.assistant()
					self.typed(passThrough=False)
					self.document.moveCaretTo(self.page.options[0])
					self.assertFalse(self.document.passThrough)
					self.assertEqual(self.page.options[0].calls, [])
					self.assertIsNot(vars(self.nvda.browseMode.BrowseModeTreeInterceptor)["shouldPassThrough"], self.nvda.own["shouldPassThrough"])
					autoFormsMode.unregister()
					suggestionLists.unregister()
					self.assertIs(
						vars(self.nvda.browseMode.BrowseModeTreeInterceptor)["shouldPassThrough"],
						self.nvda.own["shouldPassThrough"],
						"turned off in either order, the assistant's other wrapper gives NVDA's own back",
					)
					self.assertNotIn("shouldPassThrough", vars(self.nvda.browseMode.BrowseModeDocumentTreeInterceptor))
					self.document.moveCaretTo(self.page.options[1])
					self.assertTrue(self.document.passThrough, "both off: NVDA's own choice")

	def test_nvda_without_the_method_the_assistant_knows_is_left_alone_and_logged_once(self):
		owner = self.nvda.browseMode.BrowseModeDocumentTreeInterceptor
		del owner._shouldSetFocusToObj
		self.nvda.browseMode.BrowseModeDocumentTreeInterceptor._shouldSetFocusToObj = None
		with self.assertLogs("nvda", level="DEBUG") as logged:
			suggestionLists.register()
		self.assertTrue(any("NVDA has no _shouldSetFocusToObj the assistant knows" in line for line in logged.output), logged.output)
		self.assertTrue(suggestionLists.isRegistered(), "the rest is applied")


class SettingTest(unittest.TestCase):
	def test_on_unless_turned_off(self):
		self.assertTrue(suggestionLists.wanted({}))
		self.assertTrue(suggestionLists.wanted(dict(state.DEFAULTS)))
		self.assertFalse(suggestionLists.wanted({suggestionLists.STATE_KEY: False}))
		self.assertFalse(suggestionLists.wanted(None))
		self.assertIs(state.DEFAULTS[suggestionLists.STATE_KEY], True)

	def test_the_key_is_the_one_the_settings_panel_and_the_state_use(self):
		self.assertEqual(suggestionLists.STATE_KEY, "chooseWebSuggestions")

	def test_the_plugin_has_no_command_before_the_settings_are_applied(self):
		plugin = object.__new__(jawsMigrator.GlobalPlugin)
		plugin._layerActive = False
		plugin._insertKeys = None
		self.assertIsNone(plugin.getScript(types.SimpleNamespace(mainKeyName="downArrow", modifiers=set())))

	def test_register_and_unregister(self):
		with mock.patch.object(suggestionLists, "_enabled", False), mock.patch.object(suggestionLists, "_replaced", []):
			suggestionLists.register()
			self.assertTrue(suggestionLists.isRegistered())
			suggestionLists.unregister()
			self.assertFalse(suggestionLists.isRegistered())


if __name__ == "__main__":
	unittest.main()
