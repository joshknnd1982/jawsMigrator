# Unit tests for version 1.24, from a tester's report (issue 19, "something NVDA says that Jaws doesn't"):
# "Items View list List top: Jaws doesn't say that." The tester's log from 2026-09-24 (NVDA 2026.2, Columns Review
# 5.7.0 among 45 add-ons) has it each time File Explorer opened a folder, and on the desktop and after Home:
# 07:20:40.910 Input: kb(laptop):enter, on "Data (D:)" in This PC
# 07:20:41.462 Speaking [LangChangeCommand ('en_US'), 'Items View', 'list', CancellableSpeech (still valid)]
# 07:20:41.503 Speaking [LangChangeCommand ('en_US'), 'List top: ']
# 07:20:41.511 Speaking [LangChangeCommand ('en_US'), '$RECYCLE.BIN', 'not selected', '1 of 364', CancellableSpeech ...]
# The "List top: " has no CancellableSpeech: it isn't NVDA's focus speech but a message. NVDA has no such words; the
# Columns Review add-on does: its "Announce list bounds (top, mono-item, bottom)", on and said with the voice as it
# comes, says it at the first item of a list, "List bottom: " at the last and "Mono-item list: " for a list of one.
# JAWS 2026 has "Top of list" and "Bottom of list" in common.jsm, but none of its scripts uses them.
# - listBounds: Columns Review's reportListBounds says nothing where Columns Review would say it with the voice, as its
#   own settings say for the object (configManager.ConfigFromObject, which follows a program's configuration profile).
#   Its beeps stay. Everything else Columns Review does is unchanged.
# The imitation Columns Review runs Columns Review 5.7.0's own GlobalPlugin.event_focusEntered, event_gainFocus and
# reportListBounds, and configManager.ConfigFromObject, word for word (from columnsReview-5.7.0.nvda-addon, the release
# the tester has), against an imitation NVDA that says what the tester heard. The assistant's code is the real one.
# Run: python -m unittest tests.test_v124_listBounds -v

import enum
import functools
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import listBounds, state  # noqa: E402

MODULE = "globalPlugins.columnsReview"

#: Columns Review 5.7.0, globalPlugins/columnsReview/__init__.py, class GlobalPlugin, word for word.
COLUMNS_REVIEW_PLUGIN = '''
def event_focusEntered(self, obj, nextHandler):
	objRole = obj.role
	if (
		objRole == roles.LIST
		or (objRole == roles.TABLE and obj.windowClassName == "MozillaWindowClass")
	):
		self.proceedWithBounds = True
	else:
		self.proceedWithBounds = False
	nextHandler()

def event_gainFocus(self, obj, nextHandler):
	# avoid None obj
	if not obj:
		return
	# speedup: nothing for web
	if obj.treeInterceptor:
		nextHandler()
		return
	objRole = obj.role
	if (
		self.proceedWithBounds
		and (objRole == roles.LISTITEM
			or (objRole == roles.TABLEROW and obj.windowClassName == "MozillaWindowClass")
		)
	):
		self.reportListBounds(obj)
	nextHandler()

def reportListBounds(self, obj):
	positionInfo = obj._get_positionInfo()
	if not positionInfo:
		return
	pos = None
	index = positionInfo.get("indexInGroup")
	similar = positionInfo.get("similarItemsInGroup")
	if index == similar == 1:
		pos = "mono"
	elif index == similar != None:
		pos = "bottom"
	elif index == 1:
		pos = "top"
	if not pos:
		return
	confFromObj = configManager.ConfigFromObject(obj)
	if not confFromObj.announceListBounds:
		return
	reportFunc = speech.speakMessage if confFromObj.announceListBoundsWith == "voice" else beep
	if reportFunc is beep:
		topBeep = confFromObj.topBeep
		bottomBeep = confFromObj.bottomBeep
		beepLen = confFromObj.beepLen
	if pos == "mono":
		# Translators: message when list contains one item only
		message = (_("Mono-item list: "),) if reportFunc != beep else (abs(topBeep-bottomBeep), beepLen*2,)
	elif pos == "bottom":
		# Translators: message when user lands on the last list item
		message = (_("List bottom: "),) if reportFunc != beep else (topBeep, beepLen,)
	elif pos == "top":
		# Translators: message when user lands on the first list item
		message = (_("List top: "),) if reportFunc != beep else (bottomBeep, beepLen,)
	reportFunc(*message)
'''

#: Columns Review 5.7.0, globalPlugins/columnsReview/configManager.py, word for word.
COLUMNS_REVIEW_CONFIG = '''
class ConfigFromObject(object):

	def __init__(self, obj):
		self.obj = obj
		try:
			self.possibleTriggerName = "app:{0}".format(self.obj.appModule.appName)
		except AttributeError:
			self.possibleTriggerName = None

	@property
	def triggersApplyForObj(self):
		return (
			list(config.conf.listProfiles())
			and config.conf.profileTriggersEnabled
			and not config.conf._suspendedTriggers
			and self.possibleTriggerName is not None
			and self.possibleTriggerName in config.conf.triggersToProfiles.keys()
		)

	def getApplicableProfiles(self):
		if self.triggersApplyForObj:
			res = []
			if len(config.conf.profiles) > 1:
				profileName = config.conf.profiles[-1].name
				# avoid occasional no manual AttributeError
				# maybe due to cache updating
				if getattr(config.conf._profileCache[profileName], "manual", False):
					res.append(config.conf._profileCache[config.conf.profiles[-1].name])
			try:
				res.append(config.conf._profileCache[config.conf.triggersToProfiles[self.possibleTriggerName]])
			except KeyError:
				try:
					config.conf._getProfile(config.conf.triggersToProfiles[self.possibleTriggerName])
					res.append(config.conf._profileCache[config.conf.triggersToProfiles[self.possibleTriggerName]])
				except KeyError:
					pass
			res.append(config.conf._profileCache[None])  # Default config
			res.append(config.conf)
		else:
			res = [config.conf]
		return res

	@property
	def announceEmptyLists(self):
		for profile in self.getApplicableProfiles():
			try:
				return is_boolean(profile["columnsReview"]["general"]["announceEmptyList"])
			except KeyError:
				continue

	@property
	def announceListBounds(self):
		for profile in self.getApplicableProfiles():
			try:
				return is_boolean(profile["columnsReview"]["general"]["announceListBounds"])
			except KeyError:
				continue

	@property
	def announceListBoundsWith(self):
		for profile in self.getApplicableProfiles():
			try:
				return profile["columnsReview"]["general"]["announceListBoundsWith"]
			except KeyError:
				continue

	@property
	def topBeep(self):
		for profile in self.getApplicableProfiles():
			try:
				return int(profile["columnsReview"]["beep"]["topBeep"])
			except KeyError:
				continue

	@property
	def bottomBeep(self):
		for profile in self.getApplicableProfiles():
			try:
				return int(profile["columnsReview"]["beep"]["bottomBeep"])
			except KeyError:
				continue

	@property
	def beepLen(self):
		for profile in self.getApplicableProfiles():
			try:
				return int(profile["columnsReview"]["beep"]["beepLen"])
			except KeyError:
				continue

	@property
	def numpadUsedForColumnsNavigation(self):
		for profile in self.getApplicableProfiles():
			try:
				return is_boolean(profile["columnsReview"]["keyboard"]["useNumpadKeys"])
			except KeyError:
				continue

	@property
	def nextColumnsGroupKey(self):
		for profile in self.getApplicableProfiles():
			try:
				return profile["columnsReview"]["keyboard"]["switchChar"]
			except KeyError:
				continue

	@property
	def enabledModifiers(self):
		keys = dict()
		POSSIBLE_MODIFIERS = ("NVDA", "control", "alt", "shift", "windows")
		for profile in reversed(self.getApplicableProfiles()):
			for keyName in POSSIBLE_MODIFIERS:
				try:
					keys[keyName] = is_boolean(profile["columnsReview"]["gestures"][keyName])
				except KeyError:
					continue
		enabledKeys = dict(filter(lambda elem: elem[1], keys.items()))
		return "+".join(enabledKeys.keys())
'''


class Role(enum.Enum):
	"""NVDA's controlTypes.Role, which Columns Review calls roles."""

	LIST = "list"
	LISTITEM = "list item"
	TABLE = "table"
	TABLEROW = "row"
	BUTTON = "button"


def is_boolean(value):
	"""configobj's validate.is_boolean, as far as this goes."""
	if isinstance(value, str):
		return {"true": True, "on": True, "1": True, "false": False, "off": False, "0": False}[value.lower()]
	return bool(value)


class Profile(dict):
	"""A configuration profile as NVDA keeps it: its values, its name, and whether the user turned it on."""

	def __init__(self, name, values, manual=False):
		super().__init__(values)
		self.name, self.manual = name, manual


def columnsReviewValues(saidWith="voice", bounds=True):
	return {"columnsReview": {"general": {"announceListBounds": bounds, "announceListBoundsWith": saidWith}, "beep": {"topBeep": 620, "bottomBeep": 440, "beepLen": 100}}}


class Conf(dict):
	"""NVDA's config.conf, as ConfigFromObject reads it: the values in use, then the profiles and their triggers."""

	def __init__(self, values, profiles=(), triggers=None):
		super().__init__(values)
		base = Profile(None, values)
		self.profiles = [base, *profiles]
		self._profileCache = {profile.name: profile for profile in self.profiles}
		self.triggersToProfiles = dict(triggers or {})
		self.profileTriggersEnabled = True
		self._suspendedTriggers = None

	def listProfiles(self):
		return [profile.name for profile in self.profiles if profile.name]

	def _getProfile(self, name):
		return self._profileCache[name]


class Obj:
	"""An object as NVDA gives it to Columns Review, with its place in its list (NVDAObject.positionInfo)."""

	def __init__(self, name, role, index=None, count=None, windowClassName="DirectUIHWND", appName="explorer"):
		self.name, self.role, self.windowClassName = name, role, windowClassName
		self.treeInterceptor = None
		self.appModule = types.SimpleNamespace(appName=appName)
		self._position = {"indexInGroup": index, "similarItemsInGroup": count} if index else {}

	def _get_positionInfo(self):
		return dict(self._position)


ITEMS_VIEW = Obj("Items View", Role.LIST)
RECYCLE_BIN = Obj("$RECYCLE.BIN", Role.LISTITEM, 1, 364)
ELOQUENCE_BACKUP = Obj("Eloquence-backup-addon", Role.LISTITEM, 1, 134)
BROWSE_MODE_CARET_FIX = Obj("browseModeCaretFix-3_0_9.nvda-addon", Role.LISTITEM, 9, 134)
LAST_FILE = Obj("the last file", Role.LISTITEM, 134, 134)
DESKTOP = Obj("Desktop", Role.LIST, windowClassName="SysListView32")
RECYCLE_BIN_ICON = Obj("Recycle Bin", Role.LISTITEM, 1, 124, windowClassName="SysListView32")
ONE_DRIVE = Obj("Data (D:)", Role.LISTITEM, 1, 1)


class ListBoundsTests(unittest.TestCase):
	def setUp(self):
		self.said = []
		self.later = []
		wx = types.ModuleType("wx")
		wx.CallAfter = lambda function, *args: self.later.append((function, args))
		patcher = mock.patch.dict(sys.modules, {"wx": wx})
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(self._restore)
		listBounds._failed = False
		listBounds._logged = False

	def _restore(self):
		listBounds.unregister()
		listBounds._replaced.clear()
		listBounds._failed = False
		sys.modules.pop(MODULE, None)

	def load(self, conf=None, **names):
		"""NVDA imports Columns Review's global plugin and makes its GlobalPlugin."""
		configManager = types.ModuleType(f"{MODULE}.configManager")
		vars(configManager).update(config=types.SimpleNamespace(conf=conf or Conf(columnsReviewValues())), is_boolean=is_boolean)
		exec(COLUMNS_REVIEW_CONFIG, vars(configManager))
		module = types.ModuleType(MODULE)
		vars(module).update(
			roles=Role,
			speech=types.SimpleNamespace(speakMessage=lambda text: self.said.append(text)),
			beep=lambda hz, length: self.said.append(f"beep {hz} Hz"),
			configManager=configManager,
			_=lambda text: text,
		)
		vars(module).update(names)
		# Its __init__ sets proceedWithBounds to False, and adds its Settings panel, which this imitation hasn't.
		exec("class GlobalPlugin:\n\tproceedWithBounds = False\n" + "".join(f"\t{line}\n" for line in COLUMNS_REVIEW_PLUGIN.splitlines()), vars(module))
		sys.modules[MODULE] = module
		self.plugin = module.GlobalPlugin()
		return module

	def runLater(self):
		"""What wx.CallAfter left for once NVDA has loaded its global plugins."""
		later, self.later[:] = list(self.later), []
		for function, args in later:
			function(*args)

	def focus(self, item, entering=None):
		"""NVDA moves the focus to ``item``: the list it enters, if any, and then the item, each through the global plugins."""
		self.said.clear()
		if entering is not None:
			self.plugin.event_focusEntered(entering, lambda: self.said.append(f"{entering.name} list"))
		self.plugin.event_gainFocus(item, lambda: self.said.append(item.name))
		return list(self.said)

	def test_openingAFolderSaysListTopWithoutTheAssistant(self):
		# The tester's log, 07:20:41: Enter on "Data (D:)" opened it.
		self.load()
		self.assertEqual(self.focus(RECYCLE_BIN, entering=ITEMS_VIEW), ["Items View list", "List top: ", "$RECYCLE.BIN"])
		listBounds.register()
		self.assertEqual(self.focus(RECYCLE_BIN, entering=ITEMS_VIEW), ["Items View list", "$RECYCLE.BIN"], "with the assistant, as JAWS")

	def test_homeEndAndAListOfOneSayTheItemAlone(self):
		# 07:20:50 to 07:20:52: B to "browseModeCaretFix-3_0_9.nvda-addon, 9 of 134", then Home: "List top: " again.
		self.load()
		self.focus(BROWSE_MODE_CARET_FIX, entering=ITEMS_VIEW)
		self.assertEqual(self.focus(ELOQUENCE_BACKUP), ["List top: ", "Eloquence-backup-addon"], "Columns Review alone, Home")
		self.assertEqual(self.focus(LAST_FILE), ["List bottom: ", "the last file"], "End")
		self.assertEqual(self.focus(ONE_DRIVE), ["Mono-item list: ", "Data (D:)"], "a list of one")
		listBounds.register()
		self.assertEqual(self.focus(ELOQUENCE_BACKUP), ["Eloquence-backup-addon"])
		self.assertEqual(self.focus(LAST_FILE), ["the last file"])
		self.assertEqual(self.focus(ONE_DRIVE), ["Data (D:)"])
		self.assertEqual(self.focus(BROWSE_MODE_CARET_FIX), ["browseModeCaretFix-3_0_9.nvda-addon"], "and the middle of the list as before")

	def test_theDesktop(self):
		# 07:19:40: Alt+F4 closed Notepad and left the focus on the desktop: "Desktop list", "List top: ", "Recycle Bin".
		self.load()
		listBounds.register()
		self.assertEqual(self.focus(RECYCLE_BIN_ICON, entering=DESKTOP), ["Desktop list", "Recycle Bin"])

	def test_itsBeepsStay(self):
		# Set to beep in Columns Review's settings: the user chose that there.
		self.load(Conf(columnsReviewValues("beep")))
		listBounds.register()
		self.assertEqual(self.focus(RECYCLE_BIN, entering=ITEMS_VIEW), ["Items View list", "beep 440 Hz", "$RECYCLE.BIN"])
		self.assertEqual(self.focus(LAST_FILE), ["beep 620 Hz", "the last file"])

	def test_turnedOffInColumnsReviewNothingChanges(self):
		self.load(Conf(columnsReviewValues(bounds=False)))
		listBounds.register()
		self.assertEqual(self.focus(RECYCLE_BIN, entering=ITEMS_VIEW), ["Items View list", "$RECYCLE.BIN"])

	def test_aProgramsProfileIsFollowedAsColumnsReviewFollowsIt(self):
		# Beeps in a profile for File Explorer, the voice everywhere else: the assistant asks as Columns Review asks.
		explorer = Profile("File Explorer", columnsReviewValues("beep"))
		self.load(Conf(columnsReviewValues("voice"), [explorer], {"app:explorer": "File Explorer"}))
		listBounds.register()
		self.assertEqual(self.focus(RECYCLE_BIN, entering=ITEMS_VIEW), ["Items View list", "beep 440 Hz", "$RECYCLE.BIN"])
		# And the voice in File Explorer's profile, beeps everywhere else.
		explorer = Profile("File Explorer", columnsReviewValues("voice"))
		self.load(Conf(columnsReviewValues("beep"), [explorer], {"app:explorer": "File Explorer"}))
		listBounds.register()
		self.assertEqual(self.focus(RECYCLE_BIN, entering=ITEMS_VIEW), ["Items View list", "$RECYCLE.BIN"])

	def test_columnsReviewLoadedAfterTheAssistant(self):
		# NVDA imports the global plugins one after another; the assistant may come first.
		listBounds.register()
		self.assertFalse(listBounds.isInstalled())
		self.load()
		self.assertEqual(self.focus(RECYCLE_BIN, entering=ITEMS_VIEW)[1], "List top: ", "not yet")
		self.runLater()
		self.assertTrue(listBounds.isInstalled())
		self.assertEqual(self.focus(RECYCLE_BIN, entering=ITEMS_VIEW), ["Items View list", "$RECYCLE.BIN"])

	def test_turnedOffColumnsReviewHasItsOwnBack(self):
		module = self.load()
		own = vars(module.GlobalPlugin)["reportListBounds"]
		listBounds.register()
		listBounds.register()
		self.assertIs(vars(module.GlobalPlugin)["reportListBounds"].__wrapped__, own, "wrapped once")
		listBounds.unregister()
		self.assertIs(vars(module.GlobalPlugin)["reportListBounds"], own)
		self.assertEqual(self.focus(RECYCLE_BIN, entering=ITEMS_VIEW), ["Items View list", "List top: ", "$RECYCLE.BIN"])

	def test_anotherAddonsWrapperStays(self):
		module = self.load()
		listBounds.register()
		ours = vars(module.GlobalPlugin)["reportListBounds"]

		@functools.wraps(ours)
		def theirs(self, obj):
			return ours(self, obj)

		module.GlobalPlugin.reportListBounds = theirs
		listBounds.register()
		self.assertIs(vars(module.GlobalPlugin)["reportListBounds"], theirs, "the assistant's is still inside it")
		self.assertEqual(self.focus(RECYCLE_BIN, entering=ITEMS_VIEW), ["Items View list", "$RECYCLE.BIN"])
		listBounds.unregister()
		self.assertIs(vars(module.GlobalPlugin)["reportListBounds"], theirs, "the other add-on's stays")
		self.assertEqual(self.focus(RECYCLE_BIN, entering=ITEMS_VIEW)[1], "List top: ", "and says as Columns Review does")

	def test_aColumnsReviewTheAssistantDoesntKnowIsLeftAlone(self):
		# Another version, which says the ends of a list some other way.
		module = self.load()
		module.GlobalPlugin.announceBounds = vars(module.GlobalPlugin)["reportListBounds"]
		del module.GlobalPlugin.reportListBounds
		with self.assertLogs("nvda", "DEBUG") as logged:
			listBounds.register()
		self.assertFalse(listBounds.isInstalled())
		self.assertIn("Columns Review has no reportListBounds the assistant knows", "\n".join(logged.output))
		self.assertNotIn("reportListBounds", vars(module.GlobalPlugin), "nothing put in its place")

	def test_whenTheAssistantCantTellItSaysIt(self):
		self.load()
		listBounds.register()
		with mock.patch.object(listBounds, "_saidWithVoice", side_effect=RuntimeError("broken for the test")):
			with self.assertLogs("nvda", "DEBUG"):
				self.assertEqual(self.focus(RECYCLE_BIN, entering=ITEMS_VIEW)[1], "List top: ", "as Columns Review says it")

	def test_onUnlessTurnedOff(self):
		self.assertTrue(state.DEFAULTS[listBounds.STATE_KEY])
		self.assertTrue(listBounds.wanted({}))
		self.assertFalse(listBounds.wanted({listBounds.STATE_KEY: False}))
		self.assertFalse(listBounds.wanted(None))

	def test_theCodeIsColumnsReviews(self):
		# The imitation runs the release's code: its own messages, and the order of its checks.
		self.assertIn('(_("List top: "),)', COLUMNS_REVIEW_PLUGIN)
		self.assertIn('reportFunc = speech.speakMessage if confFromObj.announceListBoundsWith == "voice" else beep', COLUMNS_REVIEW_PLUGIN)
		self.assertIn("self.reportListBounds(obj)", COLUMNS_REVIEW_PLUGIN)
		self.assertIn("def announceListBoundsWith(self):", COLUMNS_REVIEW_CONFIG)


if __name__ == "__main__":
	unittest.main()
