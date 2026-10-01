# Unit tests for version 1.56, from a tester's issue 49, "Audio will get louder and then quiet": "I went into speech settings
# and turned down the volume. It will stay quiet for a little while then get louder", and, with a second log, "when I'm
# typing in this box it is at the lower volume I set. When it is reading it is louder." His NVDA's log (2026-10-01 07.44.39,
# which holds the night before too) has the answer. As NVDA loaded his settings, three configurations held a speech volume
# of Eloquence's: the normal configuration 100, "browseMode" (the profile Custom Browse Mode turns on, by hand, whenever
# browse mode is on) 100, and "JAWS - msedge" (the migration's profile for Edge) 78 at 00:08 and 80 at 07:43. NVDA uses the
# profile turned on last, and writes what is changed into it:
# - 00:10:15, 05:11:52 and 07:42:57: the Speech category of Settings, opened from Edge, said "Editing profile JAWS - msedge".
# - 05:12:03 Home on the Volume slider (100), 05:12:13 OK; 07:43:02 Page Down twice (100, 90, 80), 07:43:13 OK: the volume
#   went into "JAWS - msedge" (saved when NVDA exited at 07:43:27), and into no other profile.
# - Reading a page in Edge, with "browseMode" turned on over "JAWS - msedge", gave 100; an edit field, where browse mode is
#   off, gave 80. Eloquence64RS 19.1.4's own log line, "Eloquence corrected isolated profile settings: ... settings=['volume']",
#   is there at every one of those switches: it keeps a copy of the voice's settings for each set of turned-on profiles.
# What is real here: the assistant's evenSpeech; NVDA 2026.2's AutoPropertyType, AutoPropertyObject and settings ring
# (SynthSetting), which make the ring's "value" a property when the class is made; and Eloquence64RS 19.1.4's functions
# that keep and apply a copy of the settings for each set of profiles, with its SynthDriver's loadSettings, saveSettings,
# pitch and volume (issue49Sources.py has them, word for word, and says where from). What is imitated: NVDA's
# configuration profiles (fakeNvda: the settings of a section come from the profile turned on last that holds them, and a
# value the configuration already gives is not written again, as NVDA's AggregatedSection does it), the Voice settings
# panel's save, the settings of the synthesizer that NVDA's AutoSettings loads and saves, audioDucking, and Eloquence's
# engine. The Settings dialog and the settings ring were tried in a real NVDA for 1.56, see the release notes.
# Run: python -m unittest tests.test_v156_evenSpeech -v

import abc
import enum
import logging
import os
import shutil
import sys
import tempfile
import types
import typing
import unittest
import weakref
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import fakeNvda  # noqa: E402
import issue49Sources  # noqa: E402

from jawsMigrator import duckingToggle, evenSpeech, state  # noqa: E402

BASE_SPEECH = {
	"synth": "eloquence",
	"eloquence": {"voice": "65536", "variant": "1", "pitch": "65", "inflection": "30", "volume": "100", "rgh": "0", "bth": "0", "rate": "65"},
}


def nvdaAutoPropertyObject():
	"""NVDA 2026.2's AutoPropertyObject, made by its own AutoPropertyType: _get_x and _set_x become the property x."""
	namespace = {
		"__name__": "baseObject",
		"abc": abc,
		"ABCMeta": abc.ABCMeta,
		"abstractproperty": abc.abstractproperty,
		"Any": typing.Any,
		"Union": typing.Union,
		"Set": typing.Set,
		"Optional": typing.Optional,
		"GetterReturnT": typing.Any,
		"GetterMethodT": typing.Callable,
		"weakref": weakref,
		"log": logging.getLogger("nvda"),
		"garbageHandler": types.SimpleNamespace(TrackedObject=object),
	}
	exec(issue49Sources.NVDA_AUTO_PROPERTY, namespace)
	return namespace["AutoPropertyObject"]


def _nvdaWrite(view, key, value):
	"""fakeNvda.View.__setitem__ with NVDA's rule as it is written in AggregatedSection.__setitem__: a value is not written
	again when its text is what the configuration gives (what is written to the file is text)."""
	if not isinstance(value, dict):
		current = view[key]
		if not isinstance(current, fakeNvda.View) and str(current) == str(value):
			return
	target = view._profiles()[-1]
	node = target
	for part in view._path:
		node = node.setdefault(part, {})
	node[key] = value
	view._conf.dirty.add(target.name)


class NumericDriverSetting:
	"""NVDA's autoSettingsUtils.driverSetting.NumericDriverSetting, as far as the voice and the ring use it."""


class Setting(NumericDriverSetting):
	def __init__(self, id, defaultVal=50):
		self.id = id
		self.defaultVal = defaultVal
		self.useConfig = True
		self.minVal = 0
		self.maxVal = 100
		self.minStep = 1
		self.normalStep = 5
		self.largeStep = 10
		self.displayName = id


class World:
	"""NVDA's configuration as the tester's PC had it (the profile files, as NVDA's log shows them at its start)."""

	def __init__(self, msedgeVolume="80"):
		self.folder = tempfile.mkdtemp()
		self.conf = fakeNvda.ConfigManager(self.folder)
		self.conf._dirtyProfiles = self.conf.dirty
		self.conf.get = lambda key, default=None: default
		self.refreshes = []
		self.conf._handleProfileSwitch = lambda shouldNotify=True: self.refreshes.append(shouldNotify)
		self.config = types.ModuleType("config")
		self.config.conf = self.conf
		self.patches = [mock.patch.dict(sys.modules, {"config": self.config}), mock.patch.object(fakeNvda.View, "__setitem__", _nvdaWrite)]
		for patch in self.patches:
			patch.start()
		self.conf.base.update({"speech": {key: dict(value) if isinstance(value, dict) else value for key, value in BASE_SPEECH.items()}, "audio": {"audioDuckingMode": "0"}})
		self.make(
			"JAWS - msedge",
			{
				"speech": {"autoLanguageSwitching": "False", "eloquence": {"volume": msedgeVolume}},
				"jawsEloquenceTyping": {"enableSemicolonFix": "False", "enableColonFix": "False"},
				"favoriteLinks": {"readUrlAfterName": "True"},
			},
		)
		self.make(
			"browseMode",
			{
				"mouse": {"enableMouseTracking": "True"},
				"favoriteLinks": {"readUrlAfterName": "True"},
				"speech": {"eloquence": {"volume": "100"}},
				"audio": {"audioDuckingMode": "0"},
			},
		)
		self.make("JAWS - 1password", {"keyboard": {"alertForSpellingErrors": "False"}})
		self.make("kitchen games", {})

	def make(self, name, content):
		self.conf.createProfile(name)
		profile = self.conf._getProfile(name)
		profile.update(content)
		return profile

	def profile(self, name):
		return self.conf._getProfile(name)

	def stack(self, *names, manual=()):
		"""Turn on the profiles ``names`` over the normal configuration, in that order; those in ``manual`` by hand."""
		for profile in self.conf._profileCache.values():
			profile.manual = False
			profile.triggered = False
		self.conf.profiles = [self.conf.base]
		for name in names:
			profile = self.profile(name)
			profile.manual = name in manual
			profile.triggered = name not in manual
			self.conf.profiles.append(profile)

	def volume(self, *names, manual=()):
		"""The speech volume NVDA gives with ``names`` turned on."""
		self.stack(*names, manual=manual)
		return self.conf["speech"]["eloquence"]["volume"]

	def close(self):
		for patch in reversed(self.patches):
			patch.stop()
		shutil.rmtree(self.folder, ignore_errors=True)


def holds(profile, *path):
	"""Whether a profile itself holds the setting at ``path``."""
	node = profile
	for part in path:
		if not isinstance(node, dict) or part not in node:
			return False
		node = node[part]
	return True


class WorldTestCase(unittest.TestCase):
	def setUp(self):
		self.world = World()
		self.addCleanup(self.world.close)
		self.conf = self.world.conf
		evenSpeech._failures.clear()
		self.notes = []
		for name, target in (("note", self.notes), ("error", self.notes)):
			patcher = mock.patch.object(evenSpeech, "_note" if name == "note" else "_failure", lambda message, target=target: target.append(message))
			patcher.start()
			self.addCleanup(patcher.stop)


# -- Which profiles, and where a change goes -------------------------------------------------------------


class ProfileKindTests(unittest.TestCase):
	def test_theMigrationsProfilesForSingleProgramsAreGuarded(self):
		for name in ("JAWS - msedge", "JAWS - outlook", "jaws - Chrome", "JAWS - sr"):
			self.assertTrue(evenSpeech.isAppProfile(name), name)
			self.assertTrue(evenSpeech.isGuarded(name), name)

	def test_customBrowseModesProfileIsGuarded(self):
		self.assertTrue(evenSpeech.isGuarded("browseMode"))
		self.assertTrue(evenSpeech.isGuarded("browsemode"))

	def test_aProfileTheUserMadeIsNeverGuarded(self):
		# "JAWS settings" is the one profile versions 1.0 to 1.2 made for all of the JAWS settings, and which the user turns on.
		for name in ("kitchen games", "JAWS settings", "Gaming", "browseMode copy", "JAWS-msedge", evenSpeech.NORMAL_CONFIGURATION):
			self.assertFalse(evenSpeech.isGuarded(name), name)

	def test_theAssistantsPrefixIsTheMigrationsOwn(self):
		from jawsMigrator import migrator

		self.assertEqual(evenSpeech.APP_PROFILE_PREFIX, migrator.APP_PROFILE_PREFIX)


class WhereANewValueGoesTests(WorldTestCase):
	"""``settlesEverywhere``: NVDA writes to the profile turned on last."""

	def test_theNormalConfigurationAloneIsWhereEveryoneChangesWhatTheyWant(self):
		self.world.stack()
		self.assertTrue(evenSpeech.settlesEverywhere(self.conf, fromDialog=True))
		self.assertTrue(evenSpeech.settlesEverywhere(self.conf, fromDialog=False))

	def test_settingsOpenedFromEdgeWritesToTheProfileForEdgeAndThatIsMadeEverywhere(self):
		self.world.stack("JAWS - msedge")
		self.assertTrue(evenSpeech.settlesEverywhere(self.conf, fromDialog=True))
		self.assertTrue(evenSpeech.settlesEverywhere(self.conf, fromDialog=False))

	def test_theRingOnAPageWritesToBrowseModesProfileAndThatIsMadeEverywhere(self):
		self.world.stack("JAWS - msedge", "browseMode", manual=("browseMode",))
		self.assertTrue(evenSpeech.settlesEverywhere(self.conf, fromDialog=False))

	def test_settingsOpenedWithBrowseModesProfileOnIsTheUsersOwnChoice(self):
		# Browse mode is off while Settings has the focus, so the profile can only have been turned on by hand.
		self.world.stack("browseMode", manual=("browseMode",))
		self.assertFalse(evenSpeech.settlesEverywhere(self.conf, fromDialog=True))

	def test_aProfileTheUserTurnedOnByHandStaysTheUsers(self):
		for name in ("kitchen games", "JAWS - msedge"):
			self.world.stack(name, manual=(name,))
			self.assertFalse(evenSpeech.settlesEverywhere(self.conf, fromDialog=True), name)
			self.assertFalse(evenSpeech.settlesEverywhere(self.conf, fromDialog=False), name)

	def test_aProfileOfTheUsersOwnThatTurnsOnInAProgramStaysTheirs(self):
		self.world.stack("JAWS - msedge", "kitchen games")
		self.assertFalse(evenSpeech.settlesEverywhere(self.conf, fromDialog=True))


# -- Making a setting the same everywhere -----------------------------------------------------------------


class MakeEverywhereTests(WorldTestCase):
	def test_theTestersFilesGaveAVolumeThatDependedOnWhatHeWasDoing(self):
		self.assertEqual(self.world.volume(), "100")
		self.assertEqual(self.world.volume("JAWS - msedge"), "80")
		self.assertEqual(self.world.volume("JAWS - msedge", "browseMode", manual=("browseMode",)), "100")

	def test_aVolumeSetOnceIsTheVolumeInEveryStack(self):
		outcome = evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		self.assertTrue(outcome.wrote)
		self.assertEqual(sorted(outcome.purged), ["JAWS - msedge", "browseMode"])
		for names, manual in (((), ()), (("JAWS - msedge",), ()), (("browseMode",), ("browseMode",)), (("JAWS - msedge", "browseMode"), ("browseMode",))):
			self.assertEqual(str(self.world.volume(*names, manual=manual)), "70", names)

	def test_theSettingIsInTheNormalConfigurationAndInNoProfile(self):
		evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		self.assertEqual(self.conf.base["speech"]["eloquence"]["volume"], 70)
		self.assertFalse(holds(self.world.profile("JAWS - msedge"), "speech", "eloquence"))
		self.assertFalse(holds(self.world.profile("browseMode"), "speech", "eloquence"))

	def test_whatElseTheProfilesHoldIsLeftAlone(self):
		evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		edge = self.world.profile("JAWS - msedge")
		# Only the voice's own section was left empty and taken out, not "speech" itself: it holds a setting of its own.
		self.assertEqual(edge["speech"], {"autoLanguageSwitching": "False"})
		self.assertEqual(edge["jawsEloquenceTyping"], {"enableSemicolonFix": "False", "enableColonFix": "False"})
		self.assertEqual(self.world.profile("browseMode")["audio"], {"audioDuckingMode": "0"})
		self.assertEqual(self.conf.base["speech"]["eloquence"]["rate"], "65")

	def test_aSectionLeftEmptyIsTakenOutToo(self):
		evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		self.assertNotIn("speech", self.world.profile("browseMode"))

	def test_aProfileOfTheUsersOwnKeepsItsVolume(self):
		self.world.profile("kitchen games").update({"speech": {"eloquence": {"volume": "60"}}})
		self.world.make("Gaming", {"speech": {"eloquence": {"rate": "90"}}})
		outcome = evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		self.assertNotIn("kitchen games", outcome.purged)
		self.assertEqual(self.world.profile("kitchen games")["speech"]["eloquence"]["volume"], "60")
		self.assertEqual(self.world.profile("Gaming")["speech"]["eloquence"], {"rate": "90"})

	def test_theProfilesTakenFromAreSavedAndTheNormalConfigurationIsAlwaysSaved(self):
		evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		self.assertEqual(self.conf.dirty, {"JAWS - msedge", "browseMode"})

	def test_nothingIsDoneAgainForAValueThatIsTheSettingEverywhereAlready(self):
		evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		self.world.refreshes.clear()
		self.conf.dirty.clear()
		outcome = evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		self.assertFalse(outcome.changed)
		self.assertEqual(self.world.refreshes, [])
		self.assertEqual(self.conf.dirty, set())

	def test_nvdaReadsItsSettingsAgainWithoutTellingAnyoneProfilesSwitched(self):
		# NVDA keeps what it read in sections made from the profiles; and a notice of a switch would load the synthesizer's
		# settings for the profiles in use, which a copy of Eloquence's would then put back.
		evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		self.assertEqual(self.world.refreshes, [False])

	def test_theNormalConfigurationMayHaveNoSectionForTheVoiceYet(self):
		del self.conf.base["speech"]["eloquence"]
		evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		self.assertEqual(self.conf.base["speech"]["eloquence"], {"volume": 70})

	def test_theNormalConfigurationMayHaveNoSpeechSectionAtAll(self):
		self.conf.base.clear()
		evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		self.assertEqual(self.conf.base, {"speech": {"eloquence": {"volume": 70}}})

	def test_aProfileNvdaCannotReadIsLeftAndTheOthersAreDone(self):
		original = self.conf._getProfile

		def failing(name):
			if name == "JAWS - msedge":
				raise ValueError("a file NVDA could not read")
			return original(name)

		self.conf._getProfile = failing
		outcome = evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		self.assertEqual(outcome.purged, ["browseMode"])
		self.assertTrue(any("JAWS - msedge" in note for note in self.notes))

	def test_audioDuckingIsMadeEverywhereTheSameWay(self):
		self.world.profile("browseMode")["audio"]["audioDuckingMode"] = "2"
		outcome = evenSpeech.makeEverywhere(("audio",), "audioDuckingMode", 1)
		self.assertEqual(outcome.purged, ["browseMode"])
		self.assertEqual(self.conf.base["audio"]["audioDuckingMode"], 1)
		self.assertNotIn("audio", self.world.profile("browseMode"))

	def test_aRateAndAPitchGoTheSameWay(self):
		self.world.profile("JAWS - msedge")["speech"]["eloquence"].update({"rate": "40", "pitch": "70"})
		for key, value in (("rate", 50), ("pitch", 60)):
			evenSpeech.makeEverywhere(("speech", "eloquence"), key, value)
		self.assertEqual(self.conf.base["speech"]["eloquence"]["rate"], 50)
		self.assertEqual(self.conf.base["speech"]["eloquence"]["pitch"], 60)
		self.assertFalse(holds(self.world.profile("JAWS - msedge"), "speech", "eloquence", "rate"))
		self.assertFalse(holds(self.world.profile("JAWS - msedge"), "speech", "eloquence", "pitch"))

	def test_anotherVoicesSettingsAreNotTouched(self):
		self.world.profile("JAWS - msedge")["speech"]["sapi5"] = {"volume": "55"}
		evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		self.assertEqual(self.world.profile("JAWS - msedge")["speech"]["sapi5"], {"volume": "55"})


# -- Eloquence64RS's copies of the settings ----------------------------------------------------------------


class Registry:
	"""NVDA's config.post_configProfileSwitch."""

	def __init__(self):
		self.handlers = []

	def register(self, handler):
		if handler not in self.handlers:
			self.handlers.append(handler)

	def notify(self, **kwargs):
		for handler in list(self.handlers):
			handler(**kwargs)


class EloquenceWorld(World):
	"""The tester's profiles with Eloquence64RS 19.1.4's own code deciding the voice's settings at each profile switch."""

	def __init__(self, msedgeVolume="80"):
		super().__init__(msedgeVolume)
		self.registry = Registry()
		self.engine = {"pitch": 65, "volume": 100}
		# NVDA's configuration gives these settings of Eloquence's driver, which the tester's files don't hold, their defaults.
		self.conf.base["speech"]["eloquence"].update({"hsz": "50", "backquoteVoiceTags": "False", "ABRDICT": "False", "phrasePrediction": "False", "pauseMode": "0", "audioQuality": "standard"})
		module = types.ModuleType("synthDrivers.eloquence")
		self.module = module
		module.config = types.SimpleNamespace(conf=self.conf, post_configProfileSwitch=self.registry)
		logger = logging.getLogger("eloquence-test")
		module.log = logger
		module.os = os
		module.globalVars = types.SimpleNamespace(appArgs=types.SimpleNamespace(secure=False))
		module.wx = types.SimpleNamespace(CallAfter=lambda function, *args: self.later.append((function, args)))
		self.later = []
		module.synthDriverHandler = types.SimpleNamespace(getSynth=lambda: self.driver)
		module._eloquence = types.SimpleNamespace(
			rate="rate",
			pitch="pitch",
			vlm="volume",
			eciPath="C:/Eloquence/eci.dll",
			getVParam=lambda parameter: self.engine.get(parameter),
			setVParam=lambda parameter, value: self.engine.__setitem__(parameter, value),
			set_dictionary_directory=lambda directory: None,
		)
		module._eloquence_dictionaries = types.SimpleNamespace(resolve_profile=lambda conf, directory, migrate=False: "standard", active_directory=lambda directory, profile: directory)
		exec(issue49Sources.ELOQUENCE_PROFILES, module.__dict__)

		class Base(nvdaAutoPropertyObject()):
			"""NVDA's SynthDriver, as far as the driver's own methods use it (AutoSettings._loadSpecificSettings and
			_saveSettings, in short). The settings Eloquence's driver has besides the pitch and the volume, which it makes
			properties of, are plain here."""

			name = "eloquence"
			supportedSettings = (Setting("pitch"), Setting("volume"))
			voice = "65536"
			variant = "1"
			rate = 65
			inflection = 30
			hsz = 50
			rgh = 0
			bth = 0
			backquoteVoiceTags = False
			ABRDICT = False
			phrasePrediction = False
			pauseMode = "0"
			audioQuality = "standard"

			def loadSettings(base, onlyChanged=False):
				conf = self.conf["speech"][base.name]
				for setting in base.supportedSettings:
					if conf.get(setting.id) is None:
						continue
					value = conf[setting.id]
					if onlyChanged and getattr(base, setting.id) == value:
						continue
					setattr(base, setting.id, value)

			def saveSettings(base):
				conf = self.conf["speech"][base.name]
				for setting in base.supportedSettings:
					conf[setting.id] = getattr(base, setting.id)

		namespace = dict(module.__dict__, Base=Base)
		exec("class Driver(Base):\n" + issue49Sources.ELOQUENCE_DRIVER_METHODS, namespace)
		self.driverClass = namespace["Driver"]
		self.driver = None
		for name in ("_profile_settings_by_stack", "_pending_profile_setting_changes"):
			setattr(module, name, getattr(module, name))
		self.patches.append(mock.patch.dict(sys.modules, {"synthDrivers.eloquence": module}))
		self.patches[-1].start()

	def start(self):
		"""NVDA starts, with the voice and its settings loaded before anything is turned on."""
		self.stack()
		self.driver = self.driverClass()
		self.driver._loading_profile_settings = True
		self.driver.loadSettings()
		self.runLater()

	def runLater(self):
		while self.later:
			function, args = self.later.pop(0)
			function(*args)

	def switch(self, *names, manual=()):
		"""NVDA's profile switch: the synthesizer loads the settings that changed, then each handler is told (Eloquence's too)."""
		self.stack(*names, manual=manual)
		self.driver.loadSettings(onlyChanged=True)
		self.registry.notify(prevConf={})
		self.runLater()

	def reading(self):
		self.switch("JAWS - msedge", "browseMode", manual=("browseMode",))

	def typing(self):
		self.switch("JAWS - msedge")


class ThePinsOfEloquence64RSTests(unittest.TestCase):
	"""Eloquence's own code, run on the tester's files: why a volume turned down in Settings was loud again on a page."""

	def setUp(self):
		self.world = EloquenceWorld()
		self.addCleanup(self.world.close)
		self.world.start()

	def test_theTestersFilesGaveWhatHeHeard(self):
		self.world.typing()
		self.assertEqual(self.world.driver.volume, 80)
		self.world.reading()
		self.assertEqual(self.world.driver.volume, 100)
		self.world.typing()
		self.assertEqual(self.world.driver.volume, 80)


class ThePinOfAVolumeSetLaterTests(unittest.TestCase):
	"""The same, from profiles that hold no volume yet: a volume turned down in Settings, and then a page."""

	def setUp(self):
		self.world = EloquenceWorld()
		self.addCleanup(self.world.close)
		del self.world.profile("JAWS - msedge")["speech"]["eloquence"]
		del self.world.profile("browseMode")["speech"]
		self.world.start()
		self.world.reading()
		self.world.typing()

	def test_aVolumeSetInOneSetOfProfilesIsNotInTheCopiesOfTheOthers(self):
		# What the Settings dialog does from Edge: the slider moves the voice, and Apply saves into the profile turned on last.
		self.world.driver.volume = 70
		self.world.driver.saveSettings()
		self.assertEqual(self.world.profile("JAWS - msedge")["speech"]["eloquence"]["volume"], 70)
		self.assertFalse(holds(self.world.profile("browseMode"), "speech"))
		self.world.reading()
		# Eloquence puts its old copy back, and writes it into the profile that is on top, "browseMode".
		self.assertEqual(self.world.driver.volume, 100)
		self.assertEqual(self.world.profile("browseMode")["speech"]["eloquence"]["volume"], 100)
		self.world.typing()
		self.assertEqual(self.world.driver.volume, 70)


class EloquenceCopiesAreChangedTests(unittest.TestCase):
	"""``refreshEloquence``, and what it takes for a volume to apply everywhere with Eloquence64RS."""

	def setUp(self):
		self.world = EloquenceWorld()
		self.addCleanup(self.world.close)
		self.world.start()
		self.world.reading()
		self.world.typing()
		evenSpeech._failures.clear()
		self.notes = []
		patcher = mock.patch.object(evenSpeech, "_note", lambda message: self.notes.append(message))
		patcher.start()
		self.addCleanup(patcher.stop)

	def copies(self):
		return {stack: dict(settings) for stack, settings in self.world.module._profile_settings_by_stack.items()}

	def test_theDriverHasACopyForEachSetOfProfilesItHasSeen(self):
		stacks = set(self.copies())
		self.assertIn(("normal configuration",), stacks)
		self.assertIn(("normal configuration", "JAWS - msedge"), stacks)
		self.assertIn(("normal configuration", "JAWS - msedge", "browseMode"), stacks)

	def test_aVolumeSetFromEdgeIsTheVolumeOnAPageToo(self):
		self.world.driver.volume = 70
		self.world.driver.saveSettings()
		evenSpeech._enabled = True
		self.addCleanup(setattr, evenSpeech, "_enabled", False)
		evenSpeech.afterChange(("speech", "eloquence"), "volume", 70, fromDialog=True)
		self.world.reading()
		self.assertEqual(self.world.driver.volume, 70)
		self.world.typing()
		self.assertEqual(self.world.driver.volume, 70)
		self.world.switch()
		self.assertEqual(self.world.driver.volume, 70)
		self.world.reading()
		self.assertEqual(self.world.driver.volume, 70)

	def test_noProfileGetsTheOldVolumeBack(self):
		self.world.driver.volume = 70
		self.world.driver.saveSettings()
		evenSpeech._enabled = True
		self.addCleanup(setattr, evenSpeech, "_enabled", False)
		evenSpeech.afterChange(("speech", "eloquence"), "volume", 70, fromDialog=True)
		for _ in range(2):
			self.world.reading()
			self.world.typing()
			self.world.switch()
		self.assertFalse(holds(self.world.profile("browseMode"), "speech"))
		self.assertFalse(holds(self.world.profile("JAWS - msedge"), "speech", "eloquence"))
		self.assertEqual(self.conf_volume(), 70)

	def conf_volume(self):
		return self.world.conf.base["speech"]["eloquence"]["volume"]

	def test_everyCopyHasTheNewVolumeAndTheOthersSettingsAreTheSame(self):
		before = self.copies()
		evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		after = self.copies()
		self.assertEqual(set(before), set(after))
		for stack in after:
			self.assertEqual(str(after[stack]["volume"]), "70", stack)
			self.assertEqual({key: value for key, value in after[stack].items() if key != "volume"}, {key: value for key, value in before[stack].items() if key != "volume"}, stack)

	def test_theNumberOfCopiesChangedIsSaid(self):
		outcome = evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		self.assertGreaterEqual(outcome.eloquence, 3)
		self.assertTrue(outcome.changed)

	def test_aCopyForSetsThatHoldAProfileOfTheUsersOwnGetsThatProfilesVolume(self):
		self.world.profile("kitchen games").update({"speech": {"eloquence": {"volume": "60"}}})
		self.world.module._profile_settings_by_stack[("normal configuration", "kitchen games")] = {"volume": 60, "rate": 65}
		evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		self.assertEqual(self.world.module._profile_settings_by_stack[("normal configuration", "kitchen games")], {"volume": 60, "rate": 65})
		self.assertEqual(self.world.module._profile_settings_by_stack[("normal configuration", "JAWS - msedge")]["volume"], 70)

	def test_changesAPanelWasStillHoldingForTheVolumeAreLetGo(self):
		pending = self.world.module._pending_profile_setting_changes
		pending[(("normal configuration", "JAWS - msedge"), "volume")] = 80
		pending[(("normal configuration", "JAWS - msedge"), "rate")] = 65
		evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		self.assertEqual(list(pending), [(("normal configuration", "JAWS - msedge"), "rate")])

	def test_onlyEloquencesOwnSectionHasCopies(self):
		before = self.copies()
		evenSpeech.makeEverywhere(("audio",), "audioDuckingMode", 1)
		self.assertEqual(self.copies(), before)
		self.assertEqual(evenSpeech.refreshEloquence(self.world.conf, ("speech", "sapi5"), "volume"), 0)

	def test_withoutEloquenceNothingIsDone(self):
		with mock.patch.dict(sys.modules, {"synthDrivers.eloquence": None}):
			self.assertEqual(evenSpeech.refreshEloquence(self.world.conf, ("speech", "eloquence"), "volume"), 0)

	def test_copiesThatAreNotWhatTheAssistantKnowsAreLeftAlone(self):
		for broken in (None, [], "text", {"a": 1}):
			with mock.patch.object(self.world.module, "_profile_settings_by_stack", broken):
				self.assertEqual(evenSpeech.refreshEloquence(self.world.conf, ("speech", "eloquence"), "volume"), 0)

	def test_aSetOfProfilesThatNoLongerExistsIsLeftAlone(self):
		self.world.module._profile_settings_by_stack[("normal configuration", "deleted profile")] = {"volume": 55}
		original = self.world.conf._getProfile

		def getProfile(name):
			if name == "deleted profile":
				# NVDA's: the file must exist.
				raise OSError("no such profile")
			return original(name)

		self.world.conf._getProfile = getProfile
		evenSpeech.makeEverywhere(("speech", "eloquence"), "volume", 70)
		self.assertEqual(self.world.module._profile_settings_by_stack[("normal configuration", "deleted profile")], {"volume": 55})


# -- NVDA's Settings, Speech ---------------------------------------------------------------------------------


class VoicePanel:
	"""NVDA's VoiceSettingsPanel for the voice of the world: onSave saves what the sliders hold (AutoSettingsMixin.onSave)."""

	driver = None

	def onSave(self):
		self.driver.saveSettings()
		self.saved = True


class SettingsDialogTests(unittest.TestCase):
	def setUp(self):
		self.world = EloquenceWorld()
		self.addCleanup(self.world.close)
		self.world.start()
		self.world.reading()
		self.world.typing()
		evenSpeech._failures.clear()
		self.notes = []
		for name in ("_note", "_failure"):
			patcher = mock.patch.object(evenSpeech, name, lambda message: self.notes.append(message))
			patcher.start()
			self.addCleanup(patcher.stop)
		self.panelClass = type("VoiceSettingsPanel", (), {"driver": self.world.driver, "onSave": VoicePanel.onSave})
		gui = types.ModuleType("gui")
		self.settingsDialogs = types.ModuleType("gui.settingsDialogs")
		self.settingsDialogs.VoiceSettingsPanel = self.panelClass
		gui.settingsDialogs = self.settingsDialogs
		synthDriverHandler = types.ModuleType("synthDriverHandler")
		synthDriverHandler.getSynth = lambda: self.world.driver
		patcher = mock.patch.dict(sys.modules, {"gui": gui, "gui.settingsDialogs": self.settingsDialogs, "synthDriverHandler": synthDriverHandler, "synthSettingsRing": None})
		patcher.start()
		self.addCleanup(patcher.stop)
		self.world.driver.supportedSettings = (Setting("pitch"), Setting("volume"))
		self.original = self.panelClass.__dict__["onSave"]
		evenSpeech._installDialog()
		evenSpeech._enabled = True
		self.addCleanup(evenSpeech.unregister)

	def save(self, volume):
		"""The tester's steps: the slider moves the voice, OK saves."""
		panel = self.panelClass()
		self.world.driver.volume = volume
		panel.onSave()
		return panel

	def test_aVolumeTurnedDownInSettingsFromEdgeApplies_inEdgeAndOnAPageAndElsewhere(self):
		self.world.typing()
		self.save(70)
		self.assertEqual(self.world.driver.volume, 70)
		for place in (self.world.reading, self.world.typing, self.world.switch, self.world.reading):
			place()
			self.assertEqual(self.world.driver.volume, 70)
		self.assertFalse(holds(self.world.profile("browseMode"), "speech"))
		self.assertFalse(holds(self.world.profile("JAWS - msedge"), "speech", "eloquence"))
		self.assertEqual(self.world.conf.base["speech"]["eloquence"]["volume"], 70)

	def test_theMessageInTheDebugLogSaysWhatWasDone(self):
		self.world.typing()
		self.save(70)
		line = next(note for note in self.notes if "volume" in note)
		self.assertIn("speech.eloquence.volume = 70 everywhere", line)
		self.assertIn("taken out of browseMode, JAWS - msedge", line)
		self.assertIn("Eloquence's remembered value changed for", line)

	def test_whatIsSavedStaysTheSameWhenNothingWasChanged(self):
		self.world.typing()
		files = {name: dict(self.world.profile(name)) for name in ("JAWS - msedge", "browseMode")}
		self.save(80)
		self.assertEqual({name: dict(self.world.profile(name)) for name in files}, files)
		self.assertEqual(self.world.conf.base["speech"]["eloquence"]["volume"], "100")

	def test_aPitchChangedAlongWithItGoesTheSameWay(self):
		self.world.typing()
		self.world.driver.pitch = 55
		self.save(70)
		self.assertEqual(self.world.conf.base["speech"]["eloquence"]["pitch"], 55)
		self.assertEqual(self.world.conf.base["speech"]["eloquence"]["volume"], 70)

	def test_theOriginalSaveStillRunsAndItsAnswerIsKept(self):
		self.assertIsNot(self.panelClass.__dict__["onSave"], self.original)
		panel = self.save(70)
		self.assertTrue(panel.saved)

	def test_aVolumeSavedWhileTheUsersOwnProfileIsTheOneBeingEditedStaysInIt(self):
		self.world.switch("kitchen games", manual=("kitchen games",))
		self.save(55)
		self.assertEqual(self.world.profile("kitchen games")["speech"]["eloquence"]["volume"], 55)
		self.assertEqual(self.world.profile("JAWS - msedge")["speech"]["eloquence"]["volume"], "80")
		self.assertEqual(self.world.conf.base["speech"]["eloquence"]["volume"], "100")

	def test_turnedOffTheSaveIsNvdasOwn(self):
		evenSpeech._enabled = False
		self.world.typing()
		self.save(70)
		self.assertEqual(self.world.profile("JAWS - msedge")["speech"]["eloquence"]["volume"], 70)
		self.assertEqual(self.world.profile("browseMode")["speech"]["eloquence"]["volume"], "100")

	def test_putOverNvdasSaveOnlyOnce(self):
		installed = self.panelClass.__dict__["onSave"]
		evenSpeech._installDialog()
		evenSpeech._installDialog()
		self.assertIs(self.panelClass.__dict__["onSave"], installed)
		self.assertEqual(len([item for item in evenSpeech._installed if item[1] == "onSave"]), 1)

	def test_nvdasSaveIsGivenBack(self):
		evenSpeech.unregister()
		self.assertIs(self.panelClass.__dict__["onSave"], self.original)

	def test_nvdasSaveIsLeftWhereSomeoneElseHasPutTheirsOverOurs(self):
		def theirs(panel):
			return "theirs"

		self.panelClass.onSave = theirs
		evenSpeech.unregister()
		self.assertIs(self.panelClass.__dict__["onSave"], theirs)

	def test_aFailureAfterTheSaveDoesNotStopIt(self):
		with mock.patch.object(evenSpeech, "afterChange", side_effect=RuntimeError("broken")):
			self.world.typing()
			panel = self.save(70)
		self.assertTrue(panel.saved)
		self.assertTrue(any("could not be made the same everywhere" in note for note in self.notes))

	def test_aSaveThatFailsRaisesAsNvdaRaisesIt(self):
		with mock.patch.object(self.world.driver, "saveSettings", side_effect=ValueError("not saved")):
			with self.assertRaises(ValueError):
				self.save(70)

	def test_aPanelNvdaChangedIsLeftAsItIs(self):
		evenSpeech.unregister()
		self.settingsDialogs.VoiceSettingsPanel = type("VoiceSettingsPanel", (), {})
		self.assertFalse(evenSpeech._installDialog())
		self.assertTrue(any("do not save as the assistant knows" in note for note in self.notes))


# -- The settings ring --------------------------------------------------------------------------------------------


class SettingsRingTests(unittest.TestCase):
	"""NVDA's own SynthSetting, made as NVDA makes it: its "value" is a property made when the class was made."""

	def setUp(self):
		self.world = EloquenceWorld()
		self.addCleanup(self.world.close)
		self.world.start()
		self.world.reading()
		evenSpeech._failures.clear()
		self.notes = []
		for name in ("_note", "_failure"):
			patcher = mock.patch.object(evenSpeech, name, lambda message: self.notes.append(message))
			patcher.start()
			self.addCleanup(patcher.stop)
		baseObject = types.SimpleNamespace(AutoPropertyObject=nvdaAutoPropertyObject())
		ring = types.ModuleType("synthSettingsRing")
		ring.__dict__.update({"baseObject": baseObject, "config": self.world.config, "typing": typing, "NumericDriverSetting": NumericDriverSetting})
		exec(issue49Sources.NVDA_SYNTH_SETTINGS, ring.__dict__)
		self.ring = ring
		self.original = vars(ring.SynthSetting)["value"]
		synthDriverHandler = types.ModuleType("synthDriverHandler")
		synthDriverHandler.getSynth = lambda: self.world.driver
		gui = types.ModuleType("gui")
		gui.settingsDialogs = types.ModuleType("gui.settingsDialogs")
		patcher = mock.patch.dict(sys.modules, {"synthSettingsRing": ring, "synthDriverHandler": synthDriverHandler, "gui": gui, "gui.settingsDialogs": gui.settingsDialogs})
		patcher.start()
		self.addCleanup(patcher.stop)
		self.world.driver.supportedSettings = (Setting("pitch"), Setting("volume"))
		self.addCleanup(evenSpeech.unregister)

	def setting(self, key="volume"):
		return self.ring.SynthSetting(self.world.driver, Setting(key))

	def test_nvdaMadeValueAPropertyFromItsOwnSetter(self):
		prop = vars(self.ring.SynthSetting)["value"]
		self.assertIsInstance(prop, property)
		self.assertIs(prop.fset, self.ring.SynthSetting._set_value)

	def test_aFunctionPutOverTheSetterAfterwardsChangesNothing(self):
		# Why the assistant replaces the property and not the setter.
		calls = []
		original = self.ring.SynthSetting._set_value
		self.ring.SynthSetting._set_value = lambda setting, value: (calls.append(value), original(setting, value))
		self.setting().value = 60
		self.assertEqual(calls, [])

	def test_theRingOnAPageMakesTheVolumeTheOneEverywhere(self):
		evenSpeech.register()
		self.assertTrue(evenSpeech._isOurs(vars(self.ring.SynthSetting)["value"].fset))
		self.world.reading()
		self.assertEqual(self.world.driver.volume, 100)
		self.setting().value = 60
		self.assertEqual(self.world.driver.volume, 60)
		self.assertEqual(self.world.conf.base["speech"]["eloquence"]["volume"], 60)
		self.assertFalse(holds(self.world.profile("browseMode"), "speech"))
		self.assertFalse(holds(self.world.profile("JAWS - msedge"), "speech", "eloquence"))
		for place in (self.world.typing, self.world.switch, self.world.reading):
			place()
			self.assertEqual(self.world.driver.volume, 60)

	def test_withoutItTheRingWritesIntoBrowseModesProfileAlone(self):
		self.world.reading()
		self.setting().value = 60
		self.assertEqual(self.world.profile("browseMode")["speech"]["eloquence"]["volume"], 60)
		self.assertEqual(self.world.conf.base["speech"]["eloquence"]["volume"], "100")

	def test_increaseAndDecreaseGoThroughTheSameSetter(self):
		evenSpeech.register()
		self.world.reading()
		setting = self.setting()
		setting.value = 50
		setting.increase()
		self.assertEqual(self.world.conf.base["speech"]["eloquence"]["volume"], 55)
		setting.decrease()
		setting.decrease()
		self.assertEqual(self.world.conf.base["speech"]["eloquence"]["volume"], 45)

	def test_aSettingThatIsNotTheVoicesIsLeftToNvda(self):
		evenSpeech.register()
		self.world.reading()
		self.world.driver.supportedSettings = (Setting("pitch"), Setting("volume"), Setting("hsz"))
		setting = self.setting("hsz")
		setting.value = 30
		self.assertEqual(self.world.profile("browseMode")["speech"]["eloquence"]["hsz"], 30)
		self.assertEqual(self.world.conf.base["speech"]["eloquence"]["hsz"], "50")

	def test_nvdasPropertyIsGivenBack(self):
		evenSpeech.register()
		evenSpeech.unregister()
		self.assertIs(vars(self.ring.SynthSetting)["value"], self.original)

	def test_theBooleanAndStringSettingsOfTheRingAreNotChanged(self):
		before = (vars(self.ring.StringSynthSetting)["value"], vars(self.ring.BooleanSynthSetting)["value"])
		evenSpeech.register()
		self.assertEqual((vars(self.ring.StringSynthSetting)["value"], vars(self.ring.BooleanSynthSetting)["value"]), before)

	def test_putOverTheRingOnlyOnce(self):
		evenSpeech.register()
		installed = vars(self.ring.SynthSetting)["value"]
		evenSpeech.register()
		self.assertIs(vars(self.ring.SynthSetting)["value"], installed)

	def test_aRingThatIsNotWhatTheAssistantKnowsIsLeftAlone(self):
		self.ring.SynthSetting.value = property(lambda setting: 0)
		evenSpeech.register()
		self.assertTrue(any("does not set a value as the assistant knows" in note for note in self.notes))


# -- Audio ducking ---------------------------------------------------------------------------------------------------


class DuckingTests(WorldTestCase):
	def setUp(self):
		super().setUp()

		class Modes(enum.IntEnum):
			NONE = 0
			OUTPUTTING = 1
			ALWAYS = 2

		self.applied = []
		audioDucking = types.ModuleType("audioDucking")
		audioDucking.AudioDuckingMode = Modes
		audioDucking.isAudioDuckingSupported = lambda: True
		audioDucking._isAudioDuckingSuspended = lambda: False
		audioDucking.setAudioDuckingMode = lambda mode: self.applied.append(mode)
		patcher = mock.patch.dict(sys.modules, {"audioDucking": audioDucking})
		patcher.start()
		self.addCleanup(patcher.stop)
		self.spoken = []
		patcher = mock.patch.object(duckingToggle, "_say", lambda message: self.spoken.append(message))
		patcher.start()
		self.addCleanup(patcher.stop)
		evenSpeech._enabled = True
		self.addCleanup(setattr, evenSpeech, "_enabled", False)

	def test_duckingTurnedOnOnAPageIsOnEverywhere(self):
		self.world.stack("JAWS - msedge", "browseMode", manual=("browseMode",))
		self.assertTrue(duckingToggle.toggle())
		self.assertEqual(self.spoken, ["Duck other audio"])
		self.assertEqual(self.conf.base["audio"]["audioDuckingMode"], 1)
		self.assertNotIn("audio", self.world.profile("browseMode"))
		for names, manual in (((), ()), (("JAWS - msedge",), ()), (("browseMode",), ("browseMode",))):
			self.world.stack(*names, manual=manual)
			self.assertEqual(int(self.conf["audio"]["audioDuckingMode"]), 1, names)

	def test_duckingTurnedOffAgainIsOffEverywhere(self):
		self.world.stack("browseMode", manual=("browseMode",))
		duckingToggle.toggle()
		duckingToggle.toggle()
		self.assertEqual(self.spoken, ["Duck other audio", "Do not duck other audio"])
		self.assertEqual(int(self.conf.base["audio"]["audioDuckingMode"]), 0)
		self.assertNotIn("audio", self.world.profile("browseMode"))

	def test_theModeNvdaAppliesIsTheOneThatWasSaid(self):
		self.world.stack("browseMode", manual=("browseMode",))
		duckingToggle.toggle()
		self.assertEqual([int(mode) for mode in self.applied], [1])

	def test_duckingInAProfileTheUserTurnedOnByHandStaysThere(self):
		self.world.stack("kitchen games", manual=("kitchen games",))
		duckingToggle.toggle()
		self.assertEqual(self.world.profile("kitchen games")["audio"]["audioDuckingMode"], 1)
		self.assertEqual(self.conf.base["audio"]["audioDuckingMode"], "0")
		self.assertEqual(self.world.profile("browseMode")["audio"]["audioDuckingMode"], "0")

	def test_turnedOffTheModeGoesWhereNvdaPutsIt(self):
		evenSpeech._enabled = False
		self.world.stack("browseMode", manual=("browseMode",))
		duckingToggle.toggle()
		self.assertEqual(self.world.profile("browseMode")["audio"]["audioDuckingMode"], 1)
		self.assertEqual(self.conf.base["audio"]["audioDuckingMode"], "0")

	def test_aFailureOfTheAssistantsDoesNotStopTheToggle(self):
		with mock.patch.object(evenSpeech, "afterChange", side_effect=RuntimeError("broken")):
			self.assertTrue(duckingToggle.toggle())
		self.assertEqual(self.spoken, ["Duck other audio"])


# -- Settings that are different already ----------------------------------------------------------------------------------


class DifferenceTests(WorldTestCase):
	def test_theTestersFilesDifferInTheVolumeAlone(self):
		difference = evenSpeech.differenceFor(self.conf, "eloquence", "volume", 100)
		# The profiles in the order of their names, whatever order the folder lists them in.
		self.assertEqual(difference.places, [("normal configuration", "100"), ("browseMode", "100"), ("JAWS - msedge", "80")])
		for key in ("rate", "pitch", "inflection"):
			self.assertIsNone(evenSpeech.differenceFor(self.conf, "eloquence", key, 50), key)

	def test_theValuesAreOfferedStartingWithTheOneNvdasSettingsPutInAProgramsProfile(self):
		difference = evenSpeech.differenceFor(self.conf, "eloquence", "volume", 100)
		self.assertEqual(difference.values, ["80", "100"])

	def test_theQuestionSaysWhereEachValueIs(self):
		difference = evenSpeech.differenceFor(self.conf, "eloquence", "volume", 100)
		self.assertEqual(
			difference.question(),
			"Your speech volume is not the same everywhere, so it changes as you move between programs and web pages. "
			'It is 80 in the profile "JAWS - msedge", and 100 in NVDA\'s normal configuration and the profile "browseMode". '
			"Which speech volume should apply everywhere?",
		)
		self.assertEqual(
			difference.choices(),
			['80, as in the profile "JAWS - msedge"', '100, as in NVDA\'s normal configuration and the profile "browseMode"', "Leave it as it is"],
		)

	def test_aVolumeEveryProfileAgreesOnIsNotAsked(self):
		self.world.profile("JAWS - msedge")["speech"]["eloquence"]["volume"] = "100"
		self.assertIsNone(evenSpeech.differenceFor(self.conf, "eloquence", "volume", 100))

	def test_aProfileThatHoldsNoVoiceSettingIsNotAskedAbout(self):
		for name in ("JAWS - msedge", "browseMode"):
			del self.world.profile(name)["speech"]
		self.assertIsNone(evenSpeech.differenceFor(self.conf, "eloquence", "volume", 100))

	def test_theNormalConfigurationCountsWithTheDefaultWhereItHoldsNoValue(self):
		del self.conf.base["speech"]["eloquence"]["volume"]
		difference = evenSpeech.differenceFor(self.conf, "eloquence", "volume", 100)
		self.assertEqual(difference.places[0], ("normal configuration", "100"))
		self.assertEqual(difference.values, ["80", "100"])

	def test_aProfileOfTheUsersOwnIsNotCounted(self):
		self.world.profile("kitchen games").update({"speech": {"eloquence": {"volume": "10"}}})
		self.assertNotIn("kitchen games", [name for name, _value in evenSpeech.differenceFor(self.conf, "eloquence", "volume", 100).places])

	def test_threeValuesAreListedWithCommasAndAnd(self):
		self.world.make("JAWS - outlook", {"speech": {"eloquence": {"volume": "60"}}})
		difference = evenSpeech.differenceFor(self.conf, "eloquence", "volume", 100)
		self.assertEqual(difference.values, ["80", "60", "100"])
		self.assertIn('It is 80 in the profile "JAWS - msedge", 60 in the profile "JAWS - outlook", and 100 in NVDA\'s normal configuration and the profile "browseMode".', difference.question())

	def test_theSameValuesAreTheSameQuestionAndOtherValuesAreAnother(self):
		first = evenSpeech.differenceFor(self.conf, "eloquence", "volume", 100)
		again = evenSpeech.differenceFor(self.conf, "eloquence", "volume", 100)
		self.assertEqual(first.signature, again.signature)
		self.world.profile("JAWS - msedge")["speech"]["eloquence"]["volume"] = "70"
		self.assertNotEqual(first.signature, evenSpeech.differenceFor(self.conf, "eloquence", "volume", 100).signature)

	def test_eachSettingHasItsOwnWords(self):
		for key, words in (("rate", "speech rate"), ("pitch", "pitch"), ("volume", "speech volume"), ("inflection", "inflection")):
			self.assertEqual(evenSpeech.Difference(key, "eloquence", [("normal configuration", "1"), ("browseMode", "2")]).label, words)


class FakeSynth:
	name = "eloquence"

	def __init__(self):
		self.supportedSettings = [Setting("voice", None), Setting("rate", 50), Setting("pitch", 50), Setting("volume", 100), Setting("inflection", 50)]
		self.loaded = []

	def loadSettings(self, onlyChanged=False):
		self.loaded.append(onlyChanged)


class OfferTests(WorldTestCase):
	def setUp(self):
		super().setUp()
		self.store = dict(state.DEFAULTS)
		self.synth = FakeSynth()
		synthDriverHandler = types.ModuleType("synthDriverHandler")
		synthDriverHandler.getSynth = lambda: self.synth
		self.logged = []
		from jawsMigrator import debugLog, nvdaApply, nvdaEnv

		self.saved = []
		for owner, name, replacement in (
			(sys.modules, "synthDriverHandler", synthDriverHandler),
			(state, "load", lambda: self.store),
			(state, "get", lambda key: self.store.get(key)),
			(state, "set", lambda key, value: self.store.__setitem__(key, value)),
			(nvdaEnv, "shouldWriteToDisk", lambda: True),
			(debugLog, "note", lambda message: self.logged.append(message)),
			(debugLog, "error", lambda message, exc_info=True: self.logged.append(message)),
			(nvdaApply, "saveConfig", lambda: self.saved.append(True)),
		):
			if owner is sys.modules:
				patcher = mock.patch.dict(sys.modules, {name: replacement})
			else:
				patcher = mock.patch.object(owner, name, replacement)
			patcher.start()
			self.addCleanup(patcher.stop)

		class Thread:
			def __init__(thread, target=None, name=None, daemon=None):
				thread.target = target

			def start(thread):
				thread.target()

		patcher = mock.patch.object(evenSpeech.threading, "Thread", Thread)
		patcher.start()
		self.addCleanup(patcher.stop)
		import wx

		patcher = mock.patch.object(wx, "CallAfter", lambda function, *args: function(*args))
		patcher.start()
		self.addCleanup(patcher.stop)
		self.said = []
		self.backups = []
		self.finished = []
		self.questions = []
		self.world.stack("JAWS - msedge", "browseMode", manual=("browseMode",))

	def backup(self, reason):
		self.backups.append(reason)
		return types.SimpleNamespace(path="C:/backups/1")

	def offer(self, answers):
		answers = list(answers)

		def ask(question, choices):
			self.questions.append((question, choices))
			return answers.pop(0)

		evenSpeech.offerOnce(self.said.append, self.backup, lambda: self.finished.append(True), ask=ask)

	def test_theTestersFilesGetOneQuestionAndTheChoiceIsMadeEverywhere(self):
		self.offer([0])
		self.assertEqual(len(self.questions), 1)
		self.assertEqual(self.questions[0][1][0], '80, as in the profile "JAWS - msedge"')
		self.assertEqual(self.conf.base["speech"]["eloquence"]["volume"], 80)
		self.assertFalse(holds(self.world.profile("JAWS - msedge"), "speech", "eloquence"))
		self.assertFalse(holds(self.world.profile("browseMode"), "speech"))
		self.assertEqual(self.finished, [True])

	def test_theBackupIsMadeFirstAndTheVoiceTakesTheValueAtOnce(self):
		self.offer([1])
		self.assertEqual(self.backups, ["Before making NVDA's speech settings the same everywhere"])
		# The normal configuration held "100" already, so it is not written again.
		self.assertEqual(str(self.conf.base["speech"]["eloquence"]["volume"]), "100")
		self.assertEqual(self.saved, [True])
		self.assertEqual(self.synth.loaded, [True])
		self.assertEqual(self.said, ["JAWS Migration Assistant: NVDA's speech volume is now 100 everywhere. NVDA's settings were backed up first."])

	def test_theDebugLogSaysWhatWasAskedAndChosen(self):
		self.offer([0])
		self.assertTrue(any("eloquence.volume differs" in line and "the user chose 80" in line for line in self.logged))
		self.assertTrue(any("speech.eloquence.volume = 80 everywhere" in line and "backup C:/backups/1" in line for line in self.logged))

	def test_leavingItChangesNothingAndIsNotAskedAgain(self):
		before = {name: dict(self.world.profile(name)) for name in ("JAWS - msedge", "browseMode")}
		self.offer([2])
		self.assertEqual(self.backups, [])
		self.assertEqual({name: dict(self.world.profile(name)) for name in before}, before)
		self.assertEqual(self.said, [])
		self.assertEqual(self.finished, [True])
		self.offer([])
		self.assertEqual(len(self.questions), 1)

	def test_aQuestionClosedIsLeftAndNotAskedAgain(self):
		self.offer([None])
		self.assertEqual(self.backups, [])
		self.assertEqual(self.conf.base["speech"]["eloquence"]["volume"], "100")
		self.offer([])
		self.assertEqual(len(self.questions), 1)

	def test_theSameValuesAreNotAskedAboutAgainAfterTheChoice(self):
		self.offer([0])
		self.offer([])
		self.assertEqual(len(self.questions), 1)

	def test_otherValuesLaterAreAskedAbout(self):
		self.offer([2])
		self.world.profile("JAWS - msedge")["speech"]["eloquence"]["volume"] = "70"
		self.offer([0])
		self.assertEqual(len(self.questions), 2)

	def test_nothingIsAskedWhereEveryProfileAgrees(self):
		for name in ("JAWS - msedge", "browseMode"):
			del self.world.profile(name)["speech"]
		self.offer([])
		self.assertEqual(self.questions, [])
		self.assertEqual(self.finished, [True])

	def test_nothingIsAskedWhenItIsTurnedOff(self):
		self.store[evenSpeech.STATE_KEY] = False
		self.offer([])
		self.assertEqual(self.questions, [])
		self.assertEqual(self.finished, [True])

	def test_nothingIsAskedWhereNvdaDoesNotWriteToDisk(self):
		from jawsMigrator import nvdaEnv

		with mock.patch.object(nvdaEnv, "shouldWriteToDisk", lambda: False):
			self.offer([])
		self.assertEqual(self.questions, [])
		self.assertEqual(self.finished, [True])

	def test_aBackupThatFailsLeavesTheSettingsAsTheyAre(self):
		def failing(reason):
			raise OSError("disk full")

		answers = [0]
		evenSpeech.offerOnce(self.said.append, failing, lambda: self.finished.append(True), ask=lambda question, choices: answers.pop(0))
		self.assertEqual(self.conf.base["speech"]["eloquence"]["volume"], "100")
		self.assertTrue(holds(self.world.profile("JAWS - msedge"), "speech", "eloquence"))
		self.assertEqual(self.said, [])
		self.assertEqual(self.finished, [True])
		# The choice could not be made, so the question is asked again when NVDA next starts.
		self.offer([0])
		self.assertEqual(len(self.questions), 1)
		self.assertEqual(self.conf.base["speech"]["eloquence"]["volume"], 80)

	def test_aQuestionLeftIsWrittenDownAndAChoiceMadeIsNot(self):
		self.offer([2])
		self.assertEqual(len(self.store[evenSpeech.ASKED_KEY]), 1)
		self.assertTrue(self.store[evenSpeech.ASKED_KEY][0].startswith("eloquence.volume:"))
		self.store[evenSpeech.ASKED_KEY] = []
		self.offer([0])
		# Once it is made, the values are the same everywhere and nothing is left to ask about.
		self.assertEqual(self.store[evenSpeech.ASKED_KEY], [])
		self.offer([])
		self.assertEqual(len(self.questions), 2)

	def test_aVoiceWithoutTheSettingIsNotAskedAbout(self):
		self.synth.supportedSettings = [Setting("voice", None)]
		self.offer([])
		self.assertEqual(self.questions, [])

	def test_noVoiceNoQuestion(self):
		self.synth = None
		self.offer([])
		self.assertEqual(self.questions, [])
		self.assertEqual(self.finished, [True])

	def test_twoSettingsThatDifferAreTwoQuestions(self):
		self.world.profile("browseMode").setdefault("speech", {}).setdefault("eloquence", {})["rate"] = "40"
		# Rate first: 65 (the normal configuration's) or 40 ("browseMode"'s); then the volume: 80 or 100.
		self.offer([1, 1])
		self.assertEqual(len(self.questions), 2)
		# Rate and then volume, in the order NVDA lists a voice's settings.
		self.assertEqual(self.said, ["JAWS Migration Assistant: NVDA's speech rate is now 40 and speech volume is now 100 everywhere. NVDA's settings were backed up first."])


# -- The assistant's own settings and the docs ----------------------------------------------------------------------


class SettingsTests(unittest.TestCase):
	def test_itIsOnUnlessTheUserTurnsItOff(self):
		self.assertTrue(evenSpeech.wanted({}))
		self.assertTrue(evenSpeech.wanted(dict(state.DEFAULTS)))
		self.assertFalse(evenSpeech.wanted({evenSpeech.STATE_KEY: False}))
		self.assertFalse(evenSpeech.wanted(None))

	def test_theStateHasTheSettingAndTheQuestionsAsked(self):
		self.assertIs(state.DEFAULTS[evenSpeech.STATE_KEY], True)
		self.assertEqual(state.DEFAULTS[evenSpeech.ASKED_KEY], [])

	def test_theSettingsPanelHasTheCheckBox(self):
		with open(os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "jawsMigrator", "gui", "settingsPanel.py"), encoding="utf-8") as stream:
			source = stream.read()
		self.assertIn("evenSpeech.wanted(state.load())", source)
		self.assertIn("updates[evenSpeech.STATE_KEY]", source)

	def test_thePluginPutsItOnAndTakesItOff(self):
		with open(os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "jawsMigrator", "__init__.py"), encoding="utf-8") as stream:
			source = stream.read()
		self.assertIn("evenSpeech.register()", source)
		self.assertIn("evenSpeech.unregister()", source)
		self.assertIn("evenSpeech.offerOnce(announce, migrator._backupFirst, done)", source)


if __name__ == "__main__":
	unittest.main()
