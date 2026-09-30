# Unit tests for version 1.45, from a tester's report (issue 43, "It no longer says page ready"; issue 44 has the same
# silence with "Loading Complete" as the message). ClassicSpeech 1.18's "Notify when page is ready" said "Page Ready" for
# most pages and nothing for some. The tester's logs (NVDA log 2026-09-29 11.48.51 and 12.07.57, nvda.log and nvda-old.log,
# NVDA 2026.2, Edge, ClassicSpeech 1.18, JAWS Migration Assistant 1.41): most pages that loaded say it, within half a second
# of NVDA's first line of the page (a tenth of a second for most):
#     11:50:13.517 jawsMigrator: NVDA came into the page for the first time ... 'Skip to content'
#     11:50:13.576 Speaking ['Page Ready']
#     11:50:15.283 (...) Speaking ['6 buttons, 13 landmarks, 18 form fields, 30 headings, 409 links.'], two seconds later
# Two say nothing, not the message and not the page summary that follows it (11:47:09.575 in nvda-old.log, "NBA Rumors -
# HoopsRumors.com", and 12:05:35.398, "MLB Rumors - MLBTradeRumors.com"; the same addresses said both in the same logs at
# 11:48:24.472 and at 12:04:06.315):
#     12:05:35.436 jawsMigrator: NVDA came into the page for the first time ... 'Skip to content'
#     (nothing until 12:05:40.750, when the tree interceptor was killed)
# A third (11:49:24.189) is the Elements List opening as the page loaded, which takes the focus and ends ClassicSpeech's wait
# too, and is not meant to say it.
# ClassicSpeech's global plugin says it in event_documentLoadComplete, after nextHandler() (classicSpeech.py, 1.18). NVDA
# 2026.2's eventHandler._EventExecuter.gen gives the event to the document's tree interceptor only if treeInterceptor.isReady
# (VirtualBuffer._get_isReady: VBufHandle and not isLoading), and there is no other handler for it (NVDA's only
# event_documentLoadComplete is the tree interceptor's), so for a page whose buffer is still loading, or has no tree
# interceptor yet, nextHandler() raises StopIteration into the handler, which ends before ClassicSpeech's second line.
# - pageReady: noted after the rest of the chain (a finally), a page ClassicSpeech didn't take is waited for until it is the
#   document NVDA's focus is in and is ready, and ClassicSpeech is then given the event, with its own settings and message.
#   Nothing changes for a page it took.
# The imitation NVDA runs NVDA 2026.2's own eventHandler._EventExecuter (tests/test_v121_alerts.py), doPreDocumentLoadComplete
# and the tree interceptor's gate, with ClassicSpeech 1.18's own lifecycle (tests/classicSpeechLifecycle118.py, word for word)
# and its plugin's three handlers. The assistant's code (pageReady and the global plugin's event) is the real one. The logs
# can't show the order the browser's events came in, so the tests run every order: the buffer ready at the load event, loading
# at it, and the page not in focus yet. Not run in NVDA and Edge themselves.
# Run: python -m unittest tests.test_v145_pageReady -v

import importlib.util
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_v121_alerts as v121  # noqa: E402

import jawsMigrator  # noqa: E402
from jawsMigrator import pageReady, state  # noqa: E402

#: The fake clock every timer of the imitation runs on, and the imitation of Edge and NVDA's focus, for the test that is running.
CLOCK = None
WORLD = None


class Timer:
	"""wx.CallLater, as far as ClassicSpeech and the assistant use it: it runs once, and Stop() cancels it."""

	def __init__(self, due, function, args):
		self.due, self.function, self.args, self.stopped = due, function, args, False

	def Stop(self):
		self.stopped = True


class Clock:
	def __init__(self):
		self.now = 0.0
		self.timers = []

	def time(self):
		return self.now

	def callLater(self, milliseconds, function, *args):
		timer = Timer(self.now + milliseconds / 1000.0, function, args)
		self.timers.append(timer)
		return timer

	def advance(self, seconds):
		"""Run every timer that falls due within ``seconds``, in order, as the clock reaches it."""
		end = self.now + seconds
		while True:
			due = sorted((timer for timer in self.timers if not timer.stopped and timer.due <= end), key=lambda timer: timer.due)
			if not due:
				break
			timer = due[0]
			self.now = max(self.now, timer.due)
			timer.stopped = True
			timer.function(*timer.args)
		self.now = end


#: ClassicSpeech's settings for the tester: "Notify when page is ready", "Summary after page is ready" with its two seconds.
SETTINGS = {"summary": True, "ready": True, "orientation": False, "delay": 2, "message": "Page Ready"}


def loadLifecycle():
	"""ClassicSpeech 1.18's lifecycle.py, run as its package runs it, with the imitation NVDA's api and wx."""
	said = []
	modules = {}
	for name in ("_cs", "_cs.processors", "_cs.processors.web", "_cs.settings", "_cs.settings.web"):
		module = types.ModuleType(name)
		module.__path__ = []
		modules[name] = module
	messagePriority = types.ModuleType("_cs.message_priority")
	messagePriority.speak_message = lambda text: said.append((CLOCK.now, text))
	summaryConfig = types.ModuleType("_cs.settings.web.summary_config")
	summaryConfig.get_automatic_reporting_enabled = lambda: SETTINGS["summary"]
	summaryConfig.get_notify_when_page_ready = lambda: SETTINGS["ready"]
	summaryConfig.get_page_entry_summary_delay_seconds = lambda: SETTINGS["delay"]
	summaryConfig.get_page_orientation_enabled = lambda: SETTINGS["orientation"]
	summaryConfig.get_page_ready_message = lambda: SETTINGS["message"]
	modules["_cs.message_priority"] = messagePriority
	modules["_cs.settings.web.summary_config"] = summaryConfig
	fakeApi = types.ModuleType("api")
	fakeApi.getFocusObject = lambda: WORLD.focus
	fakeWx = types.ModuleType("wx")
	fakeWx.CallLater = lambda milliseconds, function, *args: CLOCK.callLater(milliseconds, function, *args)
	modules["api"], modules["wx"] = fakeApi, fakeWx
	path = os.path.join(os.path.dirname(__file__), "classicSpeechLifecycle118.py")
	spec = importlib.util.spec_from_file_location("_cs.processors.web.lifecycle", path)
	module = importlib.util.module_from_spec(spec)
	with mock.patch.dict(sys.modules, modules):
		spec.loader.exec_module(module)
	return module, said


class ClassicSpeechPlugin:
	"""ClassicSpeech 1.18's global plugin, as far as a page's load goes: classicSpeech.py, word for word where it is code."""

	def __init__(self, lifecycleModule, summaries):
		self._webPageLifecycle = lifecycleModule.WebPageLifecycle(lambda document: summaries.append((CLOCK.now, document)), lambda message: None)
		self._lifecycleModule = lifecycleModule

	def _get_web_page_lifecycle(self):
		"""Return the automatic web lifecycle, including test-double fallback."""
		lifecycle = getattr(self, "_webPageLifecycle", None)
		if lifecycle is None:
			lifecycle = self._lifecycleModule.WebPageLifecycle(lambda document: None, lambda message: None)
			self._webPageLifecycle = lifecycle
		return lifecycle

	@property
	def _automaticSummaryPending(self):
		return self._get_web_page_lifecycle().automatic_summary_pending

	@property
	def _automaticSummaryReported(self):
		return self._get_web_page_lifecycle().automatic_summary_reported

	def event_gainFocus(self, obj, nextHandler):
		"""Keep NVDA's native focus event first, exactly once."""
		nextHandler()
		self._get_web_page_lifecycle().handle_focus_change(obj)

	def event_documentLoadComplete(self, obj, nextHandler):
		"""Keep NVDA's native load event first, exactly once."""
		nextHandler()
		self._get_web_page_lifecycle().handle_document_load_complete(obj)


class App:
	def __init__(self, name):
		self.appName = name


EDGE, NVDA = App("msedge"), App("nvda")


class Page:
	"""A web page's document object, as NVDA makes one each time it asks: two of them are equal when they are the same document."""

	windowClassName = "Chrome_RenderWidgetHostHWND"

	def __init__(self, ident, app=EDGE):
		self.ident = ident
		self.appModule = app

	def __eq__(self, other):
		return isinstance(other, Page) and other.ident == self.ident

	def __hash__(self):
		return hash(self.ident)

	@property
	def treeInterceptor(self):
		"""treeInterceptorHandler.getTreeInterceptor: the running tree interceptor that has this document, if any."""
		for tree in WORLD.running:
			if tree.rootNVDAObject == self:
				return tree
		return None

	def __repr__(self):
		return f"<page {self.ident}>"


class Element:
	"""An object that is not in a page: Edge's address bar, NVDA's own dialog."""

	windowClassName = "Edit"
	treeInterceptor = None

	def __init__(self, name, app):
		self.name, self.appModule = name, app

	def __repr__(self):
		return f"<{self.name}>"


class Tree:
	"""A Chromium browse mode buffer, loading until it has loaded (virtualBuffers.VirtualBuffer)."""

	def __init__(self, root):
		self.rootNVDAObject = root
		self.VBufHandle = object()
		self.isLoading = True

	@property
	def isReady(self):
		"""NVDA 2026.2's VirtualBuffer._get_isReady, word for word."""
		return bool(self.VBufHandle and not self.isLoading)

	def _iterNodesByType(self, itemType, direction="next", pos=None):
		return iter(())

	def event_documentLoadComplete(self, obj, nextHandler):
		"""NVDA's VirtualBuffer.event_documentLoadComplete, for a document that had the focus: it doesn't call nextHandler."""
		return None


class World:
	"""Edge and NVDA's focus, as far as a document load goes."""

	def __init__(self):
		self.running = []
		self.focus = Element("Address and search bar", EDGE)

	def prepare(self, page):
		"""treeInterceptorHandler.update: the tree interceptor of a page, whose buffer starts to load."""
		if page.treeInterceptor is None:
			self.running.append(Tree(page))

	def bufferReady(self, page):
		page.treeInterceptor.isLoading = False


class PageReadyTest(unittest.TestCase):
	def setUp(self):
		global CLOCK, WORLD
		CLOCK, WORLD = Clock(), World()
		self.addCleanup(lambda: globals().update(CLOCK=None, WORLD=None))
		self.lifecycleModule, self.said = loadLifecycle()
		self.summaries = []
		self.classic = ClassicSpeechPlugin(self.lifecycleModule, self.summaries)
		self.assistant = object.__new__(jawsMigrator.GlobalPlugin)
		self.assistant._pageReady = pageReady
		# What the assistant's own focus event looks at, with none of its other modules loaded.
		self.assistant._sleepApps = set()
		self.assistant._autoFormsMode = self.assistant._changeRepeats = self.assistant._formFields = self.assistant._screenShade = None
		# NVDA's log shows the assistant's handlers outermost, so its plugin is the first one NVDA asks.
		self.plugins = [self.assistant, self.classic]
		fakeApi = types.ModuleType("api")
		fakeApi.getFocusObject = lambda: WORLD.focus
		fakeApi.getFocusAncestors = lambda: []
		self.api = fakeApi
		patches = [
			mock.patch.dict(sys.modules, {"api": fakeApi}),
			mock.patch.object(sys.modules["globalPluginHandler"], "runningPlugins", self.plugins, create=True),
			mock.patch.object(pageReady, "_later", CLOCK.callLater),
			mock.patch.object(pageReady, "_now", CLOCK.time),
			mock.patch.object(pageReady, "_failed", False),
			mock.patch.object(pageReady, "_waiting", None),
			mock.patch.object(pageReady, "_enabled", False),
		]
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)
		pageReady.register()
		self.executer = v121.nvdaCode(
			v121.NVDA_EVENT_EXECUTER,
			"_EventExecuter",
			{
				"garbageHandler": types.SimpleNamespace(TrackedObject=object),
				"globalPluginHandler": types.SimpleNamespace(runningPlugins=self.plugins),
				"log": nvdaStubs.logging.getLogger("nvda"),
				"extensionPoints": types.SimpleNamespace(callWithSupportedKwargs=lambda func, *args, **kwargs: func(*args)),
			},
		)

	# -- what the browser and NVDA do ------------------------------------------------------------------------------------

	def loaded(self, ident, app=EDGE):
		"""The browser says the document has finished loading: NVDA's documentLoadComplete, for an object of its own,
		as eventHandler.executeEvent runs it (doPreDocumentLoadComplete first, NVDA 2026.2, word for word in effect)."""
		obj = Page(ident, app)
		if not obj.treeInterceptor and (obj == WORLD.focus or obj in self.api.getFocusAncestors()):
			WORLD.prepare(obj)
		self.executer("documentLoadComplete", obj, {})

	def focusOn(self, element):
		"""NVDA's gainFocus event: doPreGainFocus makes the tree interceptor of a page, then the global plugins have it."""
		WORLD.focus = element
		if isinstance(element, Page):
			WORLD.prepare(element)
		self.executer("gainFocus", element, {})

	def enterPage(self, ident, bufferReadyAfter=0.04):
		"""The browser puts the focus in the page, and NVDA's buffer for it loads."""
		page = Page(ident)
		self.focusOn(page)
		CLOCK.advance(bufferReadyAfter)
		WORLD.bufferReady(page)
		return page

	def spoken(self):
		return [text for when, text in self.said]

	def summarized(self):
		return [document.rootNVDAObject.ident for when, document in self.summaries]

	def take(self, seconds):
		CLOCK.advance(seconds)

	def assistantsTimers(self):
		return [timer for timer in CLOCK.timers if timer.function is pageReady._look]

	# -- the buffer was ready when the browser said the page loaded: ClassicSpeech took it -----------------------------------

	def test_page_loaded_after_its_buffer_was_ready_says_page_ready_and_the_summary_once(self):
		self.enterPage("mlb")
		self.take(0.03)
		self.loaded("mlb")
		self.take(5)
		self.assertEqual(self.spoken(), ["Page Ready"])
		self.assertEqual(self.summarized(), ["mlb"], "the summary follows two seconds later, as in the tester's log")
		self.assertAlmostEqual(self.said[0][0], 0.04 + 0.03 + 0.05, places=2, msg="ClassicSpeech's own 50 ms")
		self.assertAlmostEqual(self.summaries[0][0], 0.04 + 0.03 + 0.05 + 2, places=2)
		self.assertIsNone(pageReady._waiting, "a page ClassicSpeech took is not waited for")
		self.assertEqual(self.assistantsTimers(), [], "and the assistant set no timer for it")

	# -- the buffer was still loading, or there was no tree interceptor: NVDA's event ended before ClassicSpeech's code --------

	def test_classicspeech_alone_never_sees_a_load_while_the_buffer_is_loading(self):
		self.plugins.remove(self.assistant)
		page = Page("mlb")
		self.focusOn(page)
		self.take(0.01)
		self.loaded("mlb")
		self.take(0.03)
		WORLD.bufferReady(page)
		self.take(10)
		self.assertIsNone(self.classic._automaticSummaryPending, "NVDA's chain ended at the tree interceptor that wasn't ready")
		self.assertEqual(self.spoken(), [], "as in the tester's log: the page is read, and there is nothing after it")
		self.assertEqual(self.summarized(), [])

	def test_page_loaded_while_its_buffer_was_loading_says_page_ready_and_the_summary_once(self):
		page = Page("mlb")
		self.focusOn(page)
		self.take(0.01)
		self.loaded("mlb")
		self.take(0.03)
		WORLD.bufferReady(page)
		ready = CLOCK.now
		self.take(10)
		self.assertEqual(self.spoken(), ["Page Ready"])
		self.assertEqual(self.summarized(), ["mlb"])
		self.assertLess(self.said[0][0] - ready, 0.25, "as soon as the page is ready, within a look of the assistant's and ClassicSpeech's 50 ms")
		self.assertIsNone(pageReady._waiting)

	def test_page_loaded_before_it_had_a_tree_interceptor_says_page_ready_and_the_summary_once(self):
		# The load event arrives first, while the focus is in the address bar, and the focus follows.
		self.plugins.remove(self.assistant)
		self.loaded("mlb")
		self.take(0.9)
		self.enterPage("mlb")
		self.take(10)
		self.assertEqual(self.spoken(), [], "ClassicSpeech alone: nothing")
		self.setUp()
		self.loaded("mlb")
		self.take(0.9)
		self.enterPage("mlb")
		self.take(10)
		self.assertEqual(self.spoken(), ["Page Ready"])
		self.assertEqual(self.summarized(), ["mlb"])
		self.assertIsNone(pageReady._waiting)

	def test_page_the_load_event_found_the_focus_in_makes_the_tree_interceptor_first(self):
		# doPreDocumentLoadComplete makes the tree interceptor of a page that has the focus and none yet: its buffer loads.
		page = Page("mlb")
		WORLD.focus = page
		self.loaded("mlb")
		self.assertFalse(page.treeInterceptor.isReady)
		self.take(0.03)
		WORLD.bufferReady(page)
		self.take(10)
		self.assertEqual(self.spoken(), ["Page Ready"])
		self.assertEqual(self.summarized(), ["mlb"])

	def test_the_assistants_note_is_made_though_nvdas_event_ended_in_stopiteration(self):
		page = Page("mlb")
		self.focusOn(page)
		self.loaded("mlb")
		self.assertIsNotNone(pageReady._waiting, "the assistant's handler runs its note in a finally")
		self.assertEqual(len(self.assistantsTimers()), 1)

	def test_it_is_said_when_the_focus_and_the_buffer_are_there_not_before(self):
		self.loaded("mlb")
		self.take(0.9)
		self.assertEqual(self.spoken(), [])
		self.enterPage("mlb", bufferReadyAfter=0.04)
		entered = CLOCK.now
		self.take(1)
		self.assertEqual(len(self.said), 1)
		self.assertGreaterEqual(self.said[0][0], entered)
		self.assertLess(self.said[0][0] - entered, 0.3)

	def test_the_assistant_gives_classicspeech_the_event_and_leaves_the_words_to_it(self):
		SETTINGS["message"] = "Loading Complete"
		self.addCleanup(lambda: SETTINGS.update(message="Page Ready"))
		self.loaded("mlb")
		self.take(0.5)
		self.enterPage("mlb")
		self.take(1)
		self.assertEqual(self.spoken(), ["Loading Complete"], "issue 44's message, as ClassicSpeech has it")

	def test_the_summary_alone_or_the_message_alone_follow_classicspeechs_settings(self):
		for summary, ready, expected, summarized in ((False, True, ["Page Ready"], []), (True, False, [], ["mlb"])):
			with self.subTest(summary=summary, ready=ready):
				self.setUp()
				SETTINGS.update(summary=summary, ready=ready)
				self.addCleanup(lambda: SETTINGS.update(summary=True, ready=True))
				self.loaded("mlb")
				self.take(0.5)
				self.enterPage("mlb")
				self.take(10)
				self.assertEqual(self.spoken(), expected)
				self.assertEqual(self.summarized(), summarized)

	def test_a_page_whose_buffer_was_ready_is_left_to_classicspeech_even_when_it_said_nothing(self):
		# ClassicSpeech's message and summary are off: it had the whole event and declined it. No wait, no timer, no log line.
		SETTINGS.update(summary=False, ready=False)
		self.addCleanup(lambda: SETTINGS.update(summary=True, ready=True))
		self.enterPage("mlb")
		with self.assertNoLogs("nvda", level="DEBUG"):
			self.loaded("mlb")
		self.take(10)
		self.assertEqual(self.assistantsTimers(), [])
		self.assertIsNone(pageReady._waiting)
		self.assertEqual(self.spoken(), [])

	def test_both_off_in_classicspeech_nothing_is_said(self):
		SETTINGS.update(summary=False, ready=False)
		self.addCleanup(lambda: SETTINGS.update(summary=True, ready=True))
		self.loaded("mlb")
		self.take(0.5)
		self.enterPage("mlb")
		self.take(10)
		self.assertEqual(self.spoken(), [])
		self.assertEqual(self.summarized(), [])
		self.assertIsNone(pageReady._waiting)

	def test_page_loaded_while_the_page_it_replaces_still_has_the_focus(self):
		# The address bar's Enter: the old page is still the focus's document when the new one says it has loaded.
		self.enterPage("hoops")
		self.loaded("hoops")
		self.take(5)
		self.assertEqual(self.spoken(), ["Page Ready"])
		self.said.clear()
		self.summaries.clear()
		self.loaded("mlb")
		self.take(0.6)
		self.assertEqual(self.spoken(), [], "the old page has the focus, and is not the page that loaded")
		self.enterPage("mlb")
		self.take(10)
		self.assertEqual(self.spoken(), ["Page Ready"])
		self.assertEqual(self.summarized(), ["mlb"])

	def test_the_testers_pages_in_turn(self):
		# Buffer ready at the load event, buffer loading at it, and ready again: each says it once.
		self.enterPage("a")
		self.loaded("a")
		self.take(5)
		page = Page("b")
		self.focusOn(page)
		self.loaded("b")
		self.take(0.04)
		WORLD.bufferReady(page)
		self.take(5)
		self.enterPage("c")
		self.loaded("c")
		self.take(5)
		self.assertEqual(self.spoken(), ["Page Ready"] * 3)
		self.assertEqual(self.summarized(), ["a", "b", "c"])

	def test_a_page_not_ready_for_seconds_is_said_when_it_is(self):
		page = Page("big")
		self.focusOn(page)
		self.loaded("big")
		self.take(2)
		self.assertEqual(self.spoken(), [])
		WORLD.bufferReady(page)
		self.take(10)
		self.assertEqual(self.spoken(), ["Page Ready"])
		self.assertEqual(self.summarized(), ["big"])

	def test_a_page_that_never_gets_ready_is_let_go(self):
		page = Page("broken")
		self.focusOn(page)
		self.loaded("broken")
		self.take(30)
		self.assertEqual(self.spoken(), [])
		self.assertIsNone(pageReady._waiting)
		WORLD.bufferReady(page)
		self.take(10)
		self.assertEqual(self.spoken(), [], "it was let go after ten seconds")

	def test_a_load_event_again_for_the_page_waited_for_is_one_wait(self):
		self.loaded("mlb")
		first = pageReady._waiting
		self.take(0.3)
		self.loaded("mlb")
		self.assertIs(pageReady._waiting, first)
		self.enterPage("mlb")
		self.take(10)
		self.assertEqual(self.spoken(), ["Page Ready"])

	# -- where it does nothing -------------------------------------------------------------------------------------------

	def test_a_page_the_focus_never_comes_to_is_let_go(self):
		# A tab in the background that finished loading.
		self.enterPage("front")
		self.loaded("front")
		self.take(5)
		self.said.clear()
		self.loaded("background")
		self.take(3.5)
		self.assertIsNone(pageReady._waiting)
		self.enterPage("background")
		self.take(10)
		self.assertEqual(self.spoken(), [], "the tab is switched to long after it loaded: not a page that has just loaded")

	def test_the_focus_going_to_nvdas_dialog_ends_the_wait(self):
		# As in the tester's 11:49:24 log, where the Elements List opened as the page did.
		page = Page("github")
		self.focusOn(page)
		self.loaded("github")
		self.take(0.01)
		self.focusOn(Element("Links List", NVDA))
		self.take(0.5)
		self.assertIsNone(pageReady._waiting)
		WORLD.bufferReady(page)
		self.focusOn(page)
		self.take(10)
		self.assertEqual(self.spoken(), [])

	def test_a_program_that_is_not_a_browser_is_left_alone(self):
		self.loaded("message", app=App("outlook"))
		self.assertIsNone(pageReady._waiting)
		self.loaded("document", app=App("winword"))
		self.assertIsNone(pageReady._waiting)

	def test_firefox_and_chrome_count(self):
		for name in ("firefox", "chrome"):
			with self.subTest(name):
				self.assertTrue(pageReady.inBrowser(Page("x", app=App(name))))

	def test_without_classicspeech_nothing_is_waited_for(self):
		self.plugins.remove(self.classic)
		self.loaded("mlb")
		self.assertIsNone(pageReady._waiting)
		self.assertEqual(CLOCK.timers, [])

	def test_a_plugin_that_is_not_classicspeech_is_not_taken_for_it(self):
		self.plugins[self.plugins.index(self.classic)] = types.SimpleNamespace(event_documentLoadComplete=lambda obj, nextHandler: nextHandler())
		self.loaded("mlb")
		self.assertIsNone(pageReady._waiting)
		self.assertIsNone(pageReady.classicSpeech())

	def test_turned_off_it_does_nothing(self):
		pageReady.unregister()
		self.loaded("mlb")
		self.assertIsNone(pageReady._waiting)
		self.enterPage("mlb")
		self.take(10)
		self.assertEqual(self.spoken(), [])

	def test_turned_off_while_waiting_it_stops(self):
		self.loaded("mlb")
		pageReady.unregister()
		self.take(0.5)
		self.enterPage("mlb")
		self.take(10)
		self.assertEqual(self.spoken(), [])

	def test_a_classicspeech_that_changed_is_left_alone_with_one_note_in_the_log(self):
		self.loaded("mlb")
		self.classic._get_web_page_lifecycle().handle_document_load_complete = None
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.take(0.5)
			self.enterPage("mlb")
			self.take(10)
		self.assertEqual(self.spoken(), [])
		self.assertIsNone(pageReady._waiting)
		self.assertEqual(sum("can't ask ClassicSpeech" in line for line in logged.output), 1)

	def test_classicspeech_doing_its_work_in_a_finally_takes_the_page_first(self):
		# A later ClassicSpeech that survives NVDA's StopIteration: it has the page pending when the assistant looks.
		def handler(obj, nextHandler):
			try:
				nextHandler()
			finally:
				self.classic._get_web_page_lifecycle().handle_document_load_complete(obj)

		self.classic.event_documentLoadComplete = handler
		page = Page("mlb")
		self.focusOn(page)
		self.loaded("mlb")
		self.take(0.03)
		WORLD.bufferReady(page)
		self.take(10)
		self.assertEqual(self.spoken(), ["Page Ready"], "once, and by ClassicSpeech alone")
		self.assertIsNone(pageReady._waiting)
		self.assertEqual(self.assistantsTimers(), [])

	# -- the global plugin's event -----------------------------------------------------------------------------------------

	def test_the_assistants_event_runs_nvdas_handlers_first_and_then_notes_the_page(self):
		order = []
		self.classic.event_documentLoadComplete = lambda obj, nextHandler: (nextHandler(), order.append("classicspeech"))
		with mock.patch.object(pageReady, "noteLoad", side_effect=lambda obj: order.append("note")):
			page = Page("mlb")
			self.focusOn(page)
			WORLD.bufferReady(page)
			self.loaded("mlb")
		self.assertEqual(order, ["classicspeech", "note"])

	def test_the_assistants_event_notes_the_page_when_the_chain_raises(self):
		noted = []
		with mock.patch.object(pageReady, "noteLoad", side_effect=noted.append):
			with self.assertRaises(StopIteration):
				self.assistant.event_documentLoadComplete(Page("mlb"), self.executerEnd)
		self.assertEqual(len(noted), 1)

	@staticmethod
	def executerEnd():
		"""nextHandler() at the end of NVDA's chain: next(self._gen) raises StopIteration."""
		return next(iter(()))

	def test_an_error_in_the_assistant_never_reaches_nvda(self):
		with mock.patch.object(pageReady, "classicSpeech", side_effect=RuntimeError("broken for the test")):
			with self.assertLogs("nvda", level="DEBUG"):
				self.loaded("mlb")
		self.assertIsNone(pageReady._waiting)

	def test_a_plugin_without_the_module_loaded_is_fine(self):
		self.assistant._pageReady = None
		self.loaded("mlb")
		self.assertEqual(CLOCK.timers, [])
		self.assertIsNone(pageReady._waiting)

	# -- the log ---------------------------------------------------------------------------------------------------------

	def test_the_log_says_why_the_page_was_missed_and_what_the_assistant_did(self):
		page = Page("mlb")
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.focusOn(page)
			self.loaded("mlb")
			self.take(0.03)
			WORLD.bufferReady(page)
			self.take(1)
		text = "\n".join(logged.output)
		self.assertIn("its buffer isn't ready, so NVDA's event ended before ClassicSpeech's code after it", text)
		self.assertIn("the assistant asks ClassicSpeech to say it now", text)
		self.assertIn("(it has it pending now)", text)

	def test_the_log_says_the_focus_was_not_in_the_page(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.loaded("mlb")
			self.take(0.5)
		text = "\n".join(logged.output)
		self.assertIn("NVDA's focus isn't in it yet", text)
		self.assertIn("Element (Edit, in msedge)", text, "where the focus was")

	def test_the_log_says_why_a_page_was_let_go(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.loaded("mlb")
			self.take(4)
		text = "\n".join(logged.output)
		self.assertIn("didn't come into the page that loaded within 3 seconds", text)
		self.assertIn("Element (Edit, in msedge)", text)

	# -- the setting -----------------------------------------------------------------------------------------------------

	def test_on_unless_turned_off(self):
		self.assertTrue(pageReady.wanted({}))
		self.assertTrue(pageReady.wanted({pageReady.STATE_KEY: True}))
		self.assertFalse(pageReady.wanted({pageReady.STATE_KEY: False}))
		self.assertFalse(pageReady.wanted(None))
		self.assertIs(state.DEFAULTS[pageReady.STATE_KEY], True)


if __name__ == "__main__":
	unittest.main()
