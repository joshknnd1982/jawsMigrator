# Unit tests for version 1.5:
# - the fix from a tester's report on version 1.4: NVDA said a control's type and state twice on web pages
#   that write them into the control's label. On visible.com, a payment option is labelled "As low as
#   $49.97/mo for 36 months 0% APR + taxes, radio button checked 1 of 2", so NVDA said "..., radio button
#   checked 1 of 2, radio button, checked" (labelRepeats). The speech sequences are the ones in the
#   tester's NVDA log; NVDA's words are its English ones;
# - NVDA+Shift+J plays JAWS's layered keystroke sound, KeyLayerSound.wav (layerSound), from imitation
#   JAWS folders in a temporary folder, or, since version 1.8, a beep when the user chose it.
# Run: python -m unittest tests.test_v15_fixes -v

import collections
import enum
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import jawsDetect, labelRepeats, layerSound, nvdaEnv, state  # noqa: E402

# NVDA 2026.2's English words (controlTypes.role and controlTypes.state).
ENGLISH_ROLES = {
	"BUTTON": "button",
	"TOGGLEBUTTON": "toggle button",
	"MENUBUTTON": "menu button",
	"DROPDOWNBUTTON": "drop down button",
	"DROPDOWNBUTTONGRID": "drop down button grid",
	"SPLITBUTTON": "split button",
	"RADIOBUTTON": "radio button",
	"CHECKBOX": "check box",
	"SWITCH": "switch",
	"COMBOBOX": "combo box",
	"EDITABLETEXT": "edit",
	"PASSWORDEDIT": "password edit",
	"SPINBUTTON": "spin button",
	"SLIDER": "slider",
	"LINK": "link",
	"TAB": "tab",
	"MENUITEM": "menu item",
	"CHECKMENUITEM": "check menu item",
	"RADIOMENUITEM": "radio menu item",
	"LISTITEM": "list item",
	"TREEVIEWITEM": "tree view item",
	"LIST": "list",
	"HEADING": "heading",
	"LANDMARK": "landmark",
}
ENGLISH_STATES = {
	"CHECKED": "checked",
	"HALFCHECKED": "half checked",
	"SELECTED": "selected",
	"PRESSED": "pressed",
	"HALF_PRESSED": "half pressed",
	"ON": "on",
	"EXPANDED": "expanded",
	"COLLAPSED": "collapsed",
	"UNAVAILABLE": "unavailable",
	"REQUIRED": "required",
	"INVALID_ENTRY": "invalid entry",
	"READONLY": "read only",
	"PROTECTED": "protected",
	"MULTILINE": "multi line",
	"AUTOCOMPLETE": "has auto complete",
	"VISITED": "visited",
	"INTERNAL_LINK": "same page",
	"HASPOPUP": "subMenu",
	"HASPOPUP_DIALOG": "opens dialog",
	"HASPOPUP_GRID": "opens grid",
	"HASPOPUP_LIST": "opens list",
	"HASPOPUP_TREE": "opens tree",
	"SORTED_ASCENDING": "sorted ascending",
	"SORTED_DESCENDING": "sorted descending",
	"MULTISELECTABLE": "multi-select",
	"CLICKABLE": "clickable",
	"FOCUSED": "focused",
}
ENGLISH_NEGATIVE_STATES = {"CHECKED": "not checked", "SELECTED": "not selected", "PRESSED": "not pressed", "ON": "off"}

GERMAN_ROLES = {"RADIOBUTTON": "Auswahlschalter", "CHECKBOX": "Kontrollfeld", "BUTTON": "Schalter"}
GERMAN_STATES = {"CHECKED": "aktiviert"}
GERMAN_NEGATIVE_STATES = {"CHECKED": "nicht aktiviert"}


class _Labelled(enum.Enum):
	"""Like NVDA's DisplayStringEnum: each member has its words."""

	@property
	def displayString(self):
		return self.value

	@property
	def negativeDisplayString(self):
		return self.__class__._negative.get(self.name, "not " + self.value)


def _controlTypes(roles, states, negativeStates):
	module = types.ModuleType("controlTypes")
	module.Role = _Labelled("Role", roles)
	module.State = _Labelled("State", states)
	module.State._negative = negativeStates
	return module


def _speechSpeech(position):
	module = types.ModuleType("speech.speech")

	def getPropertiesSpeech(reason=None, **values):
		if "positionInfo_indexInGroup" in values:
			return [position.format(number=values["positionInfo_indexInGroup"], total=values["positionInfo_similarItemsInGroup"])]
		return []

	module.getPropertiesSpeech = getPropertiesSpeech
	return module


class _Filter:
	"""NVDA's extensionPoints.Filter, as far as the assistant uses it: handlers run in their order."""

	def __init__(self):
		self._handlers = collections.OrderedDict()

	def register(self, handler):
		self._handlers[id(handler)] = handler

	def unregister(self, handler):
		return self._handlers.pop(id(handler), None) is not None

	def moveToEnd(self, handler, last=False):
		try:
			self._handlers.move_to_end(id(handler), last=last)
		except KeyError:
			return False
		return True

	@property
	def handlers(self):
		yield from self._handlers.values()

	def apply(self, value):
		for handler in self.handlers:
			value = handler(value)
		return value


def _nvda(roles=ENGLISH_ROLES, states=ENGLISH_STATES, negativeStates=ENGLISH_NEGATIVE_STATES, position="{number} of {total}"):
	"""Stand-ins for the NVDA modules labelRepeats uses, for mock.patch.dict(sys.modules, ...)."""
	extensions = types.ModuleType("speech.extensions")
	extensions.filter_speechSequence = _Filter()
	speech = types.ModuleType("speech")
	speech.extensions = extensions
	speech.speech = _speechSpeech(position)
	return {
		"controlTypes": _controlTypes(roles, states, negativeStates),
		"speech": speech,
		"speech.extensions": extensions,
		"speech.speech": speech.speech,
	}


def _englishVocabulary():
	with mock.patch.dict(sys.modules, _nvda()):
		return labelRepeats.nvdaVocabulary()


ENGLISH = _englishVocabulary()


class _Command:
	"""A speech command, such as NVDA's BreakCommand or CancellableSpeech: never text."""

	def __init__(self, name):
		self.name = name

	def __repr__(self):
		return self.name


BREAK = _Command("BreakCommand(time=80)")
CANCELLABLE = _Command("CancellableSpeech (still valid)")
LANGUAGE = _Command("LangChangeCommand ('en_US')")

AS_LOW_AS = "As low as $49.97/mo for 36 months 0% APR + taxes"
PAY_TODAY = "Pay today one thousand seven hundred ninety nine dollars plus taxes"


def clean(sequence, vocabulary=ENGLISH):
	return labelRepeats.clean(sequence, vocabulary)


class TheTestersPageTests(unittest.TestCase):
	def test_moving_to_the_radio_button_says_its_type_and_state_once(self):
		# Log lines 54515 and 54593: A, JAWS's quick navigation key for radio buttons.
		spoken = clean([f"{AS_LOW_AS}, radio button checked 1 of 2", "radio button", "checked"])
		self.assertEqual(spoken, [AS_LOW_AS, "radio button", "checked"])
		# Log line 54601.
		spoken = clean([f"{PAY_TODAY}, radio button not checked 2 of 2", "radio button", "not checked"])
		self.assertEqual(spoken, [PAY_TODAY, "radio button", "not checked"])

	def test_checking_it_says_checked_once(self):
		# Log line 54609: Space checks the option; NVDA says its label and its new state.
		self.assertEqual(clean([f"{PAY_TODAY}, radio button checked 2 of 2", "checked"]), [PAY_TODAY, "checked"])

	def test_nvdas_state_wins_over_a_label_the_page_did_not_update(self):
		spoken = clean([f"{PAY_TODAY}, radio button not checked 2 of 2", "radio button", "checked"])
		self.assertEqual(spoken, [PAY_TODAY, "radio button", "checked"])

	def test_reading_line_by_line(self):
		# In browse mode NVDA says a radio button's type and state before its label, with an empty string between.
		spoken = clean(["radio button", "checked", "", f"{AS_LOW_AS}, radio button checked 1 of 2"])
		self.assertEqual(spoken, ["radio button", "checked", "", AS_LOW_AS])

	def test_focus_mode_with_classicspeechs_pauses(self):
		sequence = [f"{PAY_TODAY}, radio button checked 2 of 2", BREAK, "radio button", BREAK, "checked", BREAK, "2 of 2", CANCELLABLE, BREAK]
		spoken = clean(sequence)
		self.assertEqual(spoken, [PAY_TODAY, BREAK, "radio button", BREAK, "checked", BREAK, "2 of 2", CANCELLABLE, BREAK])
		self.assertEqual(len(sequence), 9, "the sequence NVDA passed is left as it was")
		self.assertEqual(sequence[0], f"{PAY_TODAY}, radio button checked 2 of 2")

	def test_what_nvda_said_correctly_stays_the_same(self):
		# Other lines of the tester's log, and the page's label on its own when it changes (line 54615).
		for sequence in (
			["main landmark", "Burgundy", "radio button", "checked"],
			["512 GB", "radio button", "unavailable", "not checked"],
			["No thanks", "button", "checked"],
			["radio button", "checked", "Burgundy"],
			["Color:", " Burgundy"],
			["same page", "link", "See details"],
			["heading", "level 1", "Apple iPhone 18 Pro Max"],
			["10 buttons, 3 landmarks, 23 form fields, 1 heading, 66 links."],
			["banner landmark", "Menu Navigation", "button", "collapsed"],
			[LANGUAGE, "Start", BREAK, "toggle button", BREAK, "not pressed", CANCELLABLE, BREAK],
			[LANGUAGE, "Inbox - Outlook - Outlook row 1 column 1", BREAK, "1 of 34", CANCELLABLE, BREAK],
			[LANGUAGE, "Items View", BREAK, "list", BREAK, BREAK, "jaws customization.txt", BREAK, "32 of 129", CANCELLABLE, BREAK],
			["Address and search bar search landmark Search or enter web address blank", BREAK, "collapsed", BREAK, "Ctrl+L", CANCELLABLE],
			[f"{PAY_TODAY}, radio button checked 2 of 2"],
			[],
		):
			with self.subTest(sequence=sequence):
				self.assertIs(clean(sequence), sequence)


class OtherControlsTests(unittest.TestCase):
	def test_forms(self):
		for sequence, expected in (
			(["Remember me, check box, not checked", "check box", "not checked"], ["Remember me", "check box", "not checked"]),
			(["Remember me, checkbox, checked", "check box", "checked"], ["Remember me", "check box", "checked"]),
			(["Country (dropdown, collapsed)", "combo box", "collapsed"], ["Country", "combo box", "collapsed"]),
			(["State, combo box, expanded", "combo box", "expanded"], ["State", "combo box", "expanded"]),
			(["Email, edit, required, invalid entry", "edit", "required", "invalid entry"], ["Email", "edit", "required", "invalid entry"]),
			(["Mute - toggle button - pressed", "toggle button", "pressed"], ["Mute", "toggle button", "pressed"]),
			(["Dark mode switch on", "switch", "on"], ["Dark mode", "switch", "on"]),
			(["Order history, link, visited", "visited", "link"], ["Order history", "visited", "link"]),
			(["Reviews tab 2 of 4", "tab", "selected", "2 of 4"], ["Reviews", "tab", "selected", "2 of 4"]),
			(["Pay today (with tax), radio button checked", "radio button", "checked"], ["Pay today (with tax)", "radio button", "checked"]),
		):
			with self.subTest(label=sequence[0]):
				self.assertEqual(clean(sequence), expected)

	def test_a_label_that_ends_in_a_state_word_keeps_it(self):
		self.assertEqual(clean(["Select all checked, check box, checked", "check box", "checked"])[0], "Select all checked")
		self.assertEqual(clean(["Enable add-on, check box, checked", "check box", "checked"])[0], "Enable add-on")
		self.assertEqual(clean(["Sign on, button, pressed", "toggle button", "pressed"])[0], "Sign on")
		self.assertEqual(clean(["Show unchecked radio button checked", "radio button", "checked"])[0], "Show unchecked")

	def test_left_alone(self):
		for sequence in (
			# Only a type: a button labelled "Close button" is labelled that way.
			["Close button", "button"],
			["Turn captions on", "switch", "on"],
			# Nothing would be left of the label.
			["radio button checked", "radio button", "checked"],
			# Text after other words, not next to what NVDA says for a control.
			["button", "Help", "Nothing happens with the button pressed"],
			["list", "with 2 items", "Shopping list, 1 of 2"],
			# A position alone doesn't show NVDA is naming the same control.
			["Classic rock radio, 1 of 5", "1 of 5"],
			# The type isn't at the end of the label.
			["radio button checked 1 of 2, As low as", "radio button", "checked"],
		):
			with self.subTest(sequence=sequence):
				self.assertIs(clean(sequence), sequence)

	def test_nvdas_language(self):
		with mock.patch.dict(sys.modules, _nvda(GERMAN_ROLES, GERMAN_STATES, GERMAN_NEGATIVE_STATES, "{number} von {total}")):
			german = labelRepeats.nvdaVocabulary()
		spoken = clean(["Monatlich zahlen, Auswahlschalter aktiviert 1 von 2", "Auswahlschalter", "aktiviert"], german)
		self.assertEqual(spoken, ["Monatlich zahlen", "Auswahlschalter", "aktiviert"])
		# An English page, with NVDA speaking German: NVDA's words are not the page's.
		sequence = [f"{AS_LOW_AS}, radio button checked 1 of 2", "Auswahlschalter", "aktiviert"]
		self.assertIs(clean(sequence, german), sequence)


class VocabularyTests(unittest.TestCase):
	def test_nvdas_words(self):
		self.assertEqual(ENGLISH.kindOf("Radio Button"), labelRepeats.ROLE)
		self.assertEqual(ENGLISH.kindOf("not checked"), labelRepeats.STATE)
		self.assertEqual(ENGLISH.kindOf("subMenu"), labelRepeats.STATE)
		self.assertEqual(ENGLISH.kindOf("checkbox"), labelRepeats.ROLE, "as English pages spell it")
		self.assertEqual(ENGLISH.kindOf("12 of 30"), labelRepeats.POSITION)
		# Types that are everyday words are not among them.
		self.assertIsNone(ENGLISH.kindOf("list"))
		self.assertIsNone(ENGLISH.kindOf("heading"))
		self.assertIsNone(ENGLISH.kindOf("focused"))
		self.assertIsNone(ENGLISH.kindOf("radio"))

	def test_nvdas_position_in_its_language(self):
		with mock.patch.dict(sys.modules, _nvda(position="{number} von {total}")):
			self.assertEqual(labelRepeats._nvdaPosition(), r"\d+\s+von\s+\d+")
		with mock.patch.dict(sys.modules, _nvda(position="{number}/{total}")):
			self.assertEqual(labelRepeats._nvdaPosition(), r"\d+/\d+")
		with mock.patch.dict(sys.modules, {"speech.speech": None}):
			self.assertEqual(labelRepeats._nvdaPosition(), "", "without NVDA's speech, only English")

	def test_split_label(self):
		label, words = ENGLISH.splitLabel(f"{AS_LOW_AS}, radio button checked 1 of 2")
		self.assertEqual(label, AS_LOW_AS)
		self.assertEqual(words, [("role", "radio button"), ("state", "checked"), ("position", "1 of 2")])
		self.assertEqual(ENGLISH.splitLabel("As low as $49.97/mo"), ("As low as $49.97/mo", []))
		self.assertEqual(ENGLISH.splitLabel("Turn captions on"), ("Turn captions on", []))


class RegistrationTests(unittest.TestCase):
	def setUp(self):
		labelRepeats.unregister()
		labelRepeats._vocabulary = None
		self.modules = _nvda()
		patcher = mock.patch.dict(sys.modules, self.modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(self._reset)

	def _reset(self):
		labelRepeats.unregister()
		labelRepeats._vocabulary = None
		labelRepeats._failed = False

	def test_runs_before_other_addons_filters(self):
		speechFilter = self.modules["speech.extensions"].filter_speechSequence
		sound = _Command("WaveFileCommand('radio button.wav')")

		# Like ClassicSpeech with a JAWS scheme: a control type becomes a sound.
		def classicSpeech(sequence):
			return [sound if item == "radio button" else item for item in sequence]

		speechFilter.register(classicSpeech)
		self.assertTrue(labelRepeats.register())
		self.assertTrue(labelRepeats.isRegistered())
		self.assertIs(next(iter(speechFilter.handlers)), labelRepeats._speechFilter)
		spoken = speechFilter.apply([f"{AS_LOW_AS}, radio button checked 1 of 2", "radio button", "checked"])
		self.assertEqual(spoken, [AS_LOW_AS, sound, "checked"])
		self.assertTrue(labelRepeats.register(), "registering twice does nothing more")
		self.assertEqual(len(list(speechFilter.handlers)), 2)
		labelRepeats.unregister()
		self.assertFalse(labelRepeats.isRegistered())
		self.assertEqual(list(speechFilter.handlers), [classicSpeech])

	def test_never_keeps_nvda_from_speaking(self):
		self.assertTrue(labelRepeats.register())
		with mock.patch.object(labelRepeats, "clean", side_effect=RuntimeError("broken")):
			sequence = ["Burgundy", "radio button", "checked"]
			self.assertIs(labelRepeats._speechFilter(sequence), sequence)
			self.assertEqual(labelRepeats._speechFilter(("Black", "radio button")), ["Black", "radio button"])
		self.assertEqual(labelRepeats._speechFilter(iter(["Burgundy", "radio button", "checked"])), ["Burgundy", "radio button", "checked"])

	def test_without_nvdas_speech_nothing_is_registered(self):
		with mock.patch.dict(sys.modules, {"speech.extensions": None}):
			self.assertFalse(labelRepeats.register())
		self.assertFalse(labelRepeats.isRegistered())
		labelRepeats.unregister()


class SettingTests(unittest.TestCase):
	def test_on_unless_turned_off(self):
		self.assertIs(state.DEFAULTS[labelRepeats.STATE_KEY], True)
		self.assertTrue(labelRepeats.wanted({}))
		self.assertTrue(labelRepeats.wanted({labelRepeats.STATE_KEY: True}))
		self.assertFalse(labelRepeats.wanted({labelRepeats.STATE_KEY: False}))
		self.assertFalse(labelRepeats.wanted(None))


# -- JAWS's layered keystroke sound -------------------------------------------------------------


# The start of JAWS 2026's Default.jcf [options] section, as far as the layer sound goes.
SHARED_JCF = (
	"[options]\n"
	";sound played when a layer is activated by pressing the initial key in a key layer sequence\n"
	"KeyLayerSound=KeyLayerSound.wav\n"
	";sound for exiting the table layer:\n"
	"TableLayerExitSound=TableLayerExit.wav\n"
)


class LayerSoundTests(unittest.TestCase):
	def setUp(self):
		self.root = tempfile.mkdtemp(prefix="jawsMigrator-layer-")
		self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
		self.addCleanup(layerSound.forget)
		layerSound.forget()

	def _write(self, path, content):
		os.makedirs(os.path.dirname(path), exist_ok=True)
		with open(path, "wb") as stream:
			stream.write(content.encode("utf-8") if isinstance(content, str) else content)
		return path

	def _jaws(self, version="2026", sharedJcf=SHARED_JCF, userJcf=None, sharedSounds=("KeyLayerSound.wav",), userSounds=()):
		"""An imitation JAWS: its shared and user settings, each sound file holding its own path."""
		jaws = jawsDetect.JawsInstallation(
			version=version,
			userRoot=os.path.join(self.root, "AppData", version),
			sharedRoot=os.path.join(self.root, "ProgramData", version),
			primaryLanguage="enu",
			languages=["enu"],
		)
		if sharedJcf is not None:
			self._write(os.path.join(jaws.sharedLanguageDir("enu"), "Default.JCF"), sharedJcf)
		if userJcf is not None:
			self._write(os.path.join(jaws.userLanguageDir("enu"), "DEFAULT.JCF"), userJcf)
		for folder, names in ((jaws.sharedLanguageDir("enu"), sharedSounds), (jaws.userLanguageDir("enu"), userSounds)):
			for name in names:
				path = os.path.join(folder, "SOUNDS" if folder == jaws.sharedLanguageDir("enu") else "Sounds", name)
				self._write(path, path)
		return jaws

	def _shared(self, jaws, name="KeyLayerSound.wav"):
		return os.path.join(jaws.sharedLanguageDir("enu"), "SOUNDS", name)

	def test_jaws_own_sound(self):
		jaws = self._jaws()
		self.assertTrue(os.path.samefile(layerSound.jawsLayerSound([jaws]), self._shared(jaws)))
		# Without the option, JAWS plays KeyLayerSound.wav all the same.
		jaws = self._jaws(version="2025", sharedJcf="[options]\nSpeechHistory=1\n")
		self.assertTrue(os.path.samefile(layerSound.jawsLayerSound([jaws]), self._shared(jaws)))

	def test_the_users_choices(self):
		jaws = self._jaws(userSounds=("KeyLayerSound.wav",))
		self.assertEqual(layerSound.jawsLayerSound([jaws]), os.path.join(jaws.userLanguageDir("enu"), "Sounds", "KeyLayerSound.wav"), "the user's own file first")
		jaws = self._jaws(version="2025", userJcf="[OPTIONS]\nKeyLayerSound=Ding\n", sharedSounds=("KeyLayerSound.wav", "Ding.wav"))
		self.assertTrue(os.path.samefile(layerSound.jawsLayerSound([jaws]), self._shared(jaws, "Ding.wav")))
		jaws = self._jaws(version="2024", userJcf="[options]\nKeyLayerSound=Missing.wav\n")
		self.assertTrue(os.path.samefile(layerSound.jawsLayerSound([jaws]), self._shared(jaws)), "a sound that isn't there: JAWS's own")
		jaws = self._jaws(version="2023", userJcf="[options]\nKeyLayerSound=\n")
		self.assertEqual(layerSound.jawsLayerSound([jaws]), "", "turned off in JAWS")

	def test_the_jaws_migrated_from_comes_first(self):
		newest = self._jaws(version="2026", sharedSounds=("KeyLayerSound.wav",))
		older = self._jaws(version="2025", userJcf="[options]\nKeyLayerSound=Older.wav\n", sharedSounds=("Older.wav",))
		self.assertTrue(os.path.samefile(layerSound.jawsLayerSound([newest, older]), self._shared(newest)))
		self.assertTrue(os.path.samefile(layerSound.jawsLayerSound([newest, older], "JAWS 2025"), self._shared(older, "Older.wav")))
		self.assertIsNone(layerSound.jawsLayerSound([]))
		self.assertIsNone(layerSound.jawsLayerSound([self._jaws(version="2022", sharedSounds=())]), "no sound file: the layer beeps")
		# JAWS settings of another version fill in when the one migrated from has no file.
		missing = self._jaws(version="2021", sharedSounds=())
		self.assertTrue(os.path.samefile(layerSound.jawsLayerSound([missing, newest], "JAWS 2021"), self._shared(newest)))

	def _playing(self, installations, migrated="JAWS 2026", writable=True, chosen=True):
		played = []
		nvwave = types.SimpleNamespace(playWaveFile=lambda fileName, asynchronous=True: played.append((fileName, asynchronous)))
		config = os.path.join(self.root, "nvda")
		with (
			mock.patch.object(jawsDetect, "findJawsInstallations", return_value=installations),
			mock.patch.object(nvdaEnv, "configDir", return_value=config),
			mock.patch.object(nvdaEnv, "shouldWriteToDisk", return_value=writable),
			mock.patch.object(state, "get", side_effect=lambda key: {"jaws": migrated} if key == "lastMigration" else None),
			mock.patch.object(state, "load", return_value={**state.DEFAULTS, layerSound.STATE_KEY: chosen}),
		):
			result = layerSound.play(nvwave)
			copy = layerSound.copyPath()
		layerSound.forget()
		return result, played, copy

	def test_plays_a_copy_that_outlives_jaws(self):
		jaws = self._jaws()
		result, played, copy = self._playing([jaws])
		self.assertTrue(result)
		self.assertEqual(played, [(copy, True)])
		self.assertTrue(copy.startswith(os.path.join(self.root, "nvda", "jawsMigrator", "sounds")))
		with open(copy, encoding="utf-8") as stream:
			self.assertTrue(os.path.samefile(stream.read(), self._shared(jaws)), "the copy is JAWS's file")
		# After JAWS is uninstalled, the copy still plays.
		self.assertEqual(self._playing([])[:2], (True, [(copy, True)]))
		# Turned off in JAWS: the layer beeps, whatever copy there is.
		off = self._jaws(version="2025", userJcf="[options]\nKeyLayerSound=\n")
		self.assertEqual(self._playing([off], "JAWS 2025")[:2], (False, []))

	def test_the_beep_when_chosen(self):
		# NVDA's Settings, JAWS Migration Assistant: "Play JAWS's layered keystroke sound for NVDA+Shift+J, instead of a beep".
		self.assertTrue(layerSound.wanted(dict(state.DEFAULTS)), "JAWS's sound, unless the user chose the beep")
		self.assertFalse(layerSound.wanted({layerSound.STATE_KEY: False}))
		jaws = self._jaws()
		result, played, copy = self._playing([jaws], chosen=False)
		self.assertEqual((result, played), (False, []), "the layer beeps")
		self.assertTrue(os.path.isfile(copy), "JAWS's sound is copied all the same")
		# Chosen again after JAWS is uninstalled, the copy plays.
		self.assertEqual(self._playing([])[:2], (True, [(copy, True)]))

	def test_jaws_file_when_nothing_may_be_written(self):
		jaws = self._jaws()
		result, played, copy = self._playing([jaws], writable=False)
		self.assertTrue(result)
		self.assertTrue(os.path.samefile(played[0][0], self._shared(jaws)))
		self.assertFalse(os.path.exists(copy))

	def test_beeps_without_a_sound_or_when_playing_fails(self):
		self.assertEqual(self._playing([])[:2], (False, []))
		jaws = self._jaws()

		def broken(fileName, asynchronous=True):
			raise OSError("no audio device")

		with (
			mock.patch.object(jawsDetect, "findJawsInstallations", return_value=[jaws]),
			mock.patch.object(nvdaEnv, "shouldWriteToDisk", return_value=False),
			mock.patch.object(state, "get", return_value=None),
			mock.patch.object(layerSound.debugLog, "error") as logged,
		):
			self.assertFalse(layerSound.play(types.SimpleNamespace(playWaveFile=broken)))
			self.assertFalse(layerSound.play(types.SimpleNamespace(playWaveFile=broken)), "and it isn't tried again")
		self.assertEqual(logged.call_count, 1)

	def test_same_content(self):
		# In place of filecmp, which NVDA's own Python doesn't have (see test_nvda_runtime).
		first = self._write(os.path.join(self.root, "a.wav"), b"RIFF" + bytes(range(256)) * 300)
		same = self._write(os.path.join(self.root, "b.wav"), b"RIFF" + bytes(range(256)) * 300)
		other = self._write(os.path.join(self.root, "c.wav"), b"RIFF" + bytes(range(256)) * 299 + bytes(256))
		shorter = self._write(os.path.join(self.root, "d.wav"), b"RIFF")
		self.assertTrue(layerSound.sameContent(first, same))
		self.assertFalse(layerSound.sameContent(first, other), "same size, one byte different")
		self.assertFalse(layerSound.sameContent(first, shorter))
		self.assertFalse(layerSound.sameContent(first, os.path.join(self.root, "missing.wav")))

	def test_sound_names(self):
		self.assertEqual(layerSound.soundName(None), "KeyLayerSound.wav")
		self.assertEqual(layerSound.soundName(_ini("[options]\nKeyLayerSound=\"Ding.wav\"\n")), "Ding.wav")
		self.assertEqual(layerSound.soundName(_ini("[options]\nKeyLayerSound=Ding\n")), "Ding.wav")
		self.assertEqual(layerSound.soundName(_ini("[options]\nKeyLayerSound=  \n")), "")


def _ini(text):
	from jawsMigrator import jawsFiles

	return jawsFiles.parseIni(text, path=None, inlineComments=True)


if __name__ == "__main__":
	unittest.main()
