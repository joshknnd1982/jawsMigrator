# Unit tests for version 1.21, from a tester's report (issue 14): "There is an issue when you immediately go to github
# that Jaws doesn't say." The log didn't upload. The tester's logs of 25 September (issues 7 and 11) show it: each time
# the tester opened a repository's page on GitHub (jawsMigrator, browseModeCaretFix, reply-to-sender-outlook), NVDA said
# "same page, link, Skip to content", then "alert" and nothing more, as GitHub added an alert with nothing in it:
# 13:53:31.361 Speaking ['alert', CancellableSpeech (still valid)]
# JAWS says an alert's text and nothing else (Default.JSS, MSAAAlertEvent: SayNotification with the alert's text), so it
# says nothing there. NVDA 2026.2's IAccessible.event_alert leaves out an alert only when it has no name, no description
# and no children; GitHub's alert has a child with nothing in it either.
# - emptyAlerts: an alert with nothing in it (no name, description, value or text in it or in anything in it, and
#   nothing in it that can take the focus) isn't said. Any other alert is said as NVDA says it.
# The imitation NVDA runs NVDA 2026.2's own eventHandler._EventExecuter, IAccessible.event_alert and
# NVDAObject._get_recursiveDescendants, word for word: the assistant's global plugin gets the alert event first, as NVDA
# gives it to every global plugin before the object. The assistant's code is the real one.
# Run: python -m unittest tests.test_v121_alerts -v

import enum
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import jawsMigrator  # noqa: E402
from jawsMigrator import emptyAlerts, state  # noqa: E402

#: NVDA 2026.2, source/eventHandler.py, word for word.
NVDA_EVENT_EXECUTER = '''
class _EventExecuter(garbageHandler.TrackedObject):
	"""Facilitates execution of a chain of event functions.
	L{gen} generates the event functions and positional arguments.
	L{next} calls the next function in the chain.
	"""

	def __init__(self, eventName, obj, kwargs):
		self.kwargs = kwargs
		self._gen = self.gen(eventName, obj)
		try:
			self.next()
		except StopIteration:
			pass
		finally:
			del self._gen

	def next(self):
		func, args = next(self._gen)
		try:
			return func(*args, **self.kwargs)
		except TypeError:
			log.warning(
				"Could not execute function {func} defined in {module} module; kwargs: {kwargs}".format(
					func=func.__name__,
					module=func.__module__ or "unknown",
					kwargs=self.kwargs,
				),
				exc_info=True,
			)
			return extensionPoints.callWithSupportedKwargs(func, *args, **self.kwargs)

	def gen(self, eventName, obj):
		funcName = "event_%s" % eventName

		# Global plugin level.
		for plugin in globalPluginHandler.runningPlugins:
			func = getattr(plugin, funcName, None)
			if func:
				yield func, (obj, self.next)

		# App module level.
		app = obj.appModule
		if app:
			func = getattr(app, funcName, None)
			if func:
				yield func, (obj, self.next)

		# Tree interceptor level.
		treeInterceptor = obj.treeInterceptor
		if treeInterceptor:
			func = getattr(treeInterceptor, funcName, None)
			if func and (getattr(func, "ignoreIsReady", False) or treeInterceptor.isReady):
				yield func, (obj, self.next)

		# NVDAObject level.
		func = getattr(obj, funcName, None)
		if func:
			yield func, ()
'''

#: NVDA 2026.2, source/NVDAObjects/IAccessible/__init__.py, IAccessible.event_alert, word for word.
NVDA_EVENT_ALERT = '''
def event_alert(self) -> None:
	if self.role != controlTypes.Role.ALERT:
		# Ignore alert events on objects that aren't alerts.
		return
	if not self.name and not self.description and self.childCount == 0:
		# Don't report if there's no content.
		return
	# If the focus is within the alert object, don't report anything for it.
	if eventHandler.isPendingEvents("gainFocus"):
		# The alert event might be fired before the focus.
		api.processPendingEvents()
	if self in api.getFocusAncestors():
		return
	speech.speakObject(self, reason=controlTypes.OutputReason.FOCUS, priority=speech.Spri.NOW)
	braille.handler.message(braille.getPropertiesBraille(name=self.name, role=self.role))
	for child in self.recursiveDescendants:
		if controlTypes.State.FOCUSABLE in child.states:
			speech.speakObject(child, reason=controlTypes.OutputReason.FOCUS, priority=speech.Spri.NOW)
			braille.handler.message(braille.getPropertiesBraille(name=self.name, role=self.role))
'''

#: NVDA 2026.2, source/NVDAObjects/__init__.py, NVDAObject._get_recursiveDescendants, word for word.
NVDA_RECURSIVE_DESCENDANTS = '''
def _get_recursiveDescendants(self):
	"""Recursively traverse and return the descendants of this object.
	This is a depth-first forward traversal.
	@return: The recursive descendants of this object.
	@rtype: generator of L{NVDAObject}
	"""
	for child in self.children:
		yield child
		for recursiveChild in child.recursiveDescendants:
			yield recursiveChild
'''


class Role(enum.Enum):
	"""NVDA's controlTypes.Role, as far as these alerts go."""

	ALERT = "alert"
	SECTION = "section"
	STATICTEXT = "text"
	BUTTON = "button"
	GRAPHIC = "graphic"
	LINK = "link"


class State(enum.Enum):
	FOCUSABLE = "focusable"
	INVISIBLE = "invisible"


class OutputReason(enum.Enum):
	FOCUS = "focus"


controlTypes = types.ModuleType("controlTypes")
controlTypes.Role, controlTypes.State, controlTypes.OutputReason = Role, State, OutputReason


class Speech:
	"""NVDA's speech, as far as event_alert goes: what it asks to speak, and with which priority."""

	class Spri(enum.Enum):
		NOW = "now"

	def __init__(self):
		self.spoken = []

	def speakObject(self, obj, reason=None, priority=None):
		self.spoken.append((obj, reason, priority))


class TextObject:
	"""IAccessible2's IAccessibleText, as comtypes gives it to NVDA: nCharacters, and text(start, end)."""

	def __init__(self, text):
		self._text = text
		self.reads = []

	@property
	def nCharacters(self):
		return len(self._text)

	def text(self, start, end):
		self.reads.append((start, end))
		return self._text[start:end]


def nvdaCode(source, name, namespace):
	"""Compile NVDA's own ``source`` against the imitation NVDA, and give back ``name`` from it."""
	scope = dict(namespace)
	exec(source, scope)
	return scope[name]


class Web:
	"""An IAccessible2 object on a web page in Edge: its role, name, description, value, states, text and children."""

	presType_content = "content"
	presentationType = "content"
	appModule = None
	treeInterceptor = None

	def __init__(self, role, name="", children=(), text=None, description="", value=None, states=(), label=""):
		self.role, self.name, self.description, self.value = role, name, description, value
		self.states = set(states)
		self._children = list(children)
		self.IAccessibleTextObject = TextObject(text) if text is not None else None
		self.label = label or role.value

	@property
	def children(self):
		return list(self._children)

	@property
	def childCount(self):
		return len(self._children)

	def __repr__(self):
		return f"<{self.label}>"


class GoneText:
	"""The text of an object the page took away: Edge answers with an error (COMError in NVDA)."""

	@property
	def nCharacters(self):
		raise OSError("(-2147467259, 'Unspecified error')")


def brokenAlert():
	"""An alert whose text can't be read any more, around an empty div."""
	alert = Web(Role.ALERT, children=[Web(Role.SECTION)], label="alert the page took away")
	alert.IAccessibleTextObject = GoneText()
	return alert


def textLeaf(text):
	"""A text node as Edge gives it: a static text object whose name and text are the text."""
	return Web(Role.STATICTEXT, name=text, text=text, label=f"text {text!r}")


def githubAlert():
	"""GitHub's alert as its repository page loads: role="alert" around an empty div, so an embedded object and no text."""
	return Web(Role.ALERT, children=[Web(Role.SECTION, text="", label="empty div")], text="￼", label="GitHub's empty alert")


class EmptyAlertsTest(unittest.TestCase):
	def setUp(self):
		self.speech = Speech()
		self.braille = []
		self.pending = []
		self.focusAncestors = []
		self.plugin = object.__new__(jawsMigrator.GlobalPlugin)
		self.plugin._emptyAlerts = emptyAlerts
		self.plugins = [self.plugin]
		patches = [
			mock.patch.dict(sys.modules, {"controlTypes": controlTypes}),
			mock.patch.object(emptyAlerts, "_failed", False),
			mock.patch.object(emptyAlerts, "_enabled", emptyAlerts._enabled),
		]
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)
		emptyAlerts.register()
		braille = types.SimpleNamespace(
			handler=types.SimpleNamespace(message=self.braille.append),
			getPropertiesBraille=lambda name=None, role=None: f"{name} {role.value}".strip(),
		)
		api = types.SimpleNamespace(processPendingEvents=lambda: None, getFocusAncestors=lambda: self.focusAncestors)
		eventHandler = types.SimpleNamespace(isPendingEvents=lambda name: name in self.pending)
		namespace = {"controlTypes": controlTypes, "speech": self.speech, "braille": braille, "api": api, "eventHandler": eventHandler}
		Web.event_alert = nvdaCode(NVDA_EVENT_ALERT, "event_alert", namespace)
		Web.recursiveDescendants = property(nvdaCode(NVDA_RECURSIVE_DESCENDANTS, "_get_recursiveDescendants", namespace))
		self.addCleanup(lambda: [delattr(Web, name) for name in ("event_alert", "recursiveDescendants")])
		self.executer = nvdaCode(
			NVDA_EVENT_EXECUTER,
			"_EventExecuter",
			{
				"garbageHandler": types.SimpleNamespace(TrackedObject=object),
				"globalPluginHandler": types.SimpleNamespace(runningPlugins=self.plugins),
				"log": nvdaStubs.logging.getLogger("nvda"),
				"extensionPoints": types.SimpleNamespace(callWithSupportedKwargs=lambda func, *args, **kwargs: func(*args)),
			},
		)

	def alert(self, obj):
		"""NVDA's alert event for obj, as eventHandler.executeEvent runs it: global plugins first, then the object."""
		self.executer("alert", obj, {})
		return [spoken for spoken, reason, priority in self.speech.spoken]

	def nvdaAlone(self, obj):
		"""What NVDA 2026.2 says for obj's alert event without the assistant."""
		self.plugins.clear()
		try:
			return self.alert(obj)
		finally:
			self.plugins.append(self.plugin)

	def test_githubs_empty_alert_was_said_as_alert_alone(self):
		alert = githubAlert()
		self.assertEqual(self.nvdaAlone(alert), [alert], "NVDA 2026.2 says the alert itself: its role alone, 'alert'")
		self.assertEqual(self.braille, ["alert"])

	def test_githubs_empty_alert_is_not_said(self):
		self.assertEqual(self.alert(githubAlert()), [])
		self.assertEqual(self.braille, [], "nor flashed in braille")

	def test_empty_alert_deeper_is_not_said(self):
		# Nothing in anything in it: an empty div in an empty div, an image and a hidden span without text.
		alert = Web(
			Role.ALERT,
			children=[Web(Role.SECTION, children=[Web(Role.SECTION, text=" \n"), Web(Role.GRAPHIC)]), Web(Role.SECTION, text="", states=[State.INVISIBLE])],
			text="￼￼",
		)
		self.assertEqual(self.alert(alert), [])

	def test_alert_with_text_is_said_as_nvda_says_it(self):
		saved = Web(Role.ALERT, children=[textLeaf("Your changes were saved")], text="Your changes were saved")
		self.assertEqual(self.alert(saved), [saved])
		self.assertEqual(self.alert(Web(Role.ALERT, children=[Web(Role.SECTION, text="Saved")], text="￼")), [saved, mock.ANY])

	def test_alert_with_its_own_text_only_is_said(self):
		# Text in the alert itself, with an object beside it that has nothing in it.
		alert = Web(Role.ALERT, children=[Web(Role.SECTION)], text="Saved ￼")
		self.assertEqual(self.alert(alert), [alert])

	def test_alert_with_text_deep_inside_is_said(self):
		alert = Web(Role.ALERT, children=[Web(Role.SECTION, children=[Web(Role.SECTION, children=[textLeaf("Try again")])])], text="￼")
		self.assertEqual(self.alert(alert), [alert])

	def test_alert_with_a_name_description_or_value_is_said(self):
		for alert in (
			Web(Role.ALERT, name="Error", children=[Web(Role.SECTION)]),
			Web(Role.ALERT, description="Try again", children=[Web(Role.SECTION)]),
			Web(Role.ALERT, children=[Web(Role.SECTION, value="3 new")]),
			Web(Role.ALERT, children=[Web(Role.GRAPHIC, name="Warning")]),
		):
			self.speech.spoken.clear()
			self.assertEqual(self.alert(alert), [alert], alert)

	def test_alert_with_a_button_in_it_is_said_with_the_button(self):
		# A control that can take the focus is said by NVDA, even without a name.
		close = Web(Role.BUTTON, states=[State.FOCUSABLE])
		alert = Web(Role.ALERT, children=[Web(Role.SECTION, children=[close])], text="￼")
		self.assertEqual(self.alert(alert), [alert, close])

	def test_large_alert_is_said_as_nvda_says_it(self):
		# More empty objects than the assistant looks through: said as NVDA says it rather than guessed at.
		alert = Web(Role.ALERT, children=[Web(Role.SECTION) for _ in range(emptyAlerts.MOST_OBJECTS)])
		self.assertEqual(self.alert(alert), [alert])
		fits = Web(Role.ALERT, children=[Web(Role.SECTION) for _ in range(emptyAlerts.MOST_OBJECTS - 1)])
		self.speech.spoken.clear()
		self.assertEqual(self.alert(fits), [])

	def test_long_text_is_read_in_part(self):
		textObject = TextObject(" " * 5000)
		alert = Web(Role.ALERT, children=[Web(Role.SECTION)])
		alert.IAccessibleTextObject = textObject
		self.assertEqual(self.alert(alert), [])
		self.assertEqual(textObject.reads, [(0, emptyAlerts.MOST_CHARACTERS)])

	def test_alert_that_cant_be_read_is_said_and_logged_once(self):
		broken = brokenAlert()
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.assertEqual(self.alert(broken), [broken])
			self.assertEqual(self.alert(brokenAlert()), [broken, mock.ANY])
		failures = [line for line in logged.output if "could not look into an alert" in line]
		self.assertEqual(len(failures), 1, logged.output)

	def test_nvda_leaves_out_an_alert_without_children_as_before(self):
		self.assertEqual(self.alert(Web(Role.ALERT)), [])
		self.assertEqual(self.nvdaAlone(Web(Role.ALERT)), [])

	def test_other_roles_go_on_to_nvda(self):
		handled = []
		link = Web(Role.LINK, children=[Web(Role.SECTION)])
		jawsMigrator.GlobalPlugin.event_alert(self.plugin, link, lambda: handled.append(link))
		self.assertEqual(handled, [link])
		self.assertEqual(self.alert(link), [], "NVDA ignores alert events on objects that aren't alerts")

	def test_turned_off_nvda_says_it_as_it_does(self):
		emptyAlerts.unregister()
		alert = githubAlert()
		self.assertEqual(self.alert(alert), [alert])
		self.assertFalse(emptyAlerts.nothingToSay(alert))

	def test_before_the_settings_are_applied_nvda_says_it(self):
		self.plugin._emptyAlerts = None
		alert = githubAlert()
		self.assertEqual(self.alert(alert), [alert])

	def test_logged_for_the_debug_log(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.alert(githubAlert())
		self.assertTrue(any('NVDA would have said "alert" alone, and JAWS says nothing' in line for line in logged.output), logged.output)


class SettingTest(unittest.TestCase):
	def test_on_unless_turned_off(self):
		self.assertTrue(emptyAlerts.wanted({}))
		self.assertTrue(emptyAlerts.wanted(dict(state.DEFAULTS)))
		self.assertFalse(emptyAlerts.wanted({emptyAlerts.STATE_KEY: False}))
		self.assertFalse(emptyAlerts.wanted(None))
		self.assertIs(state.DEFAULTS[emptyAlerts.STATE_KEY], True)

	def test_register_and_unregister(self):
		with mock.patch.object(emptyAlerts, "_enabled", False):
			emptyAlerts.register()
			self.assertTrue(emptyAlerts.isRegistered())
			emptyAlerts.unregister()
			self.assertFalse(emptyAlerts.isRegistered())


if __name__ == "__main__":
	unittest.main()
