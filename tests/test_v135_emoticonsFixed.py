# Unit tests for version 1.35: profileSwitches leaves the Emoticons add-on alone from its version 38.2.0.
# 1.34 (issue 31) had Emoticons 38.0.0 read speechDictHandler.dictionaries once for each change of NVDA's temporary
# dictionary instead of twice for each emoticon, because NVDA 2026.2 writes a warning with its whole stack each time
# that name is read: 177 at every profile switch. To do that, the assistant read the name once itself. Emoticons
# 38.2.0 (for NVDA 2026.3, whose speechDictHandler.definitions.getDictionaryDefinition is public) keeps the temporary
# dictionary itself ("Replace deprecated symbols with their corresponding updates", nvdaes/emoticons#66) and reads
# no such name, so NVDA writes no warning at all. The assistant's reading would have added one at each change.
# - profileSwitches wraps only Emoticons functions whose code reads speechDictHandler.dictionaries. Emoticons 38.2.0
#   is left as it is; 38.0.0, on NVDA 2026.2 or 2026.3 (which still warns), is wrapped as in 1.34.
# The imitation NVDA is 1.34's (tests/test_v134_profileSwitches.py: NVDA 2026.2's own gesture maps, script code and
# speech dictionary code with its warning), with NVDA 2026.3's getDictionaryDefinition, and Emoticons 38.2.0's
# dictionaries, tempDict, loadDic, activateAnnouncement, deactivateAnnouncement and handleConfigProfileSwitch, word
# for word (from its 38.2.0 tag). Built by an ast script.
# Run: python -m unittest tests.test_v135_emoticonsFixed -v

import functools
import os
import sys
import textwrap
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import test_v134_profileSwitches as v134  # noqa: E402
from test_v134_profileSwitches import v128  # noqa: E402
from jawsMigrator import profileSwitches  # noqa: E402

#: Emoticons 38.2.0, globalPlugins/emoticons/__init__.py.
EMOTICONS_382_DICTIONARIES = r'''
defaultDic = SpeechDict()


noEmojisDic = SpeechDict()


sD = SpeechDict()


tempDict = speechDictHandler.definitions.getDictionaryDefinition(DictionaryType.TEMP).dictionary


def loadDic():
	if profileName is None:
		dicFile = ADDON_DIC_DEFAULT_FILE
	else:
		dicFile = os.path.abspath(os.path.join(ADDON_DICTS_PATH, "profiles", "%s.dic" % profileName))
	sD.load(dicFile)
	if not os.path.isfile(dicFile):
		if config.conf["emoticons"]["speakAddonEmojis"]:
			sD.extend(defaultDic)
		else:
			sD.extend(noEmojisDic)


def activateAnnouncement():
	tempDict.extend(sD)


def deactivateAnnouncement():
	for entry in sD:
		if entry in tempDict:
			tempDict.remove(entry)
'''

#: Emoticons 38.2.0, globalPlugins/emoticons/__init__.py, class GlobalPlugin.
EMOTICONS_382_PROFILE_SWITCH = r'''
def handleConfigProfileSwitch(self):
	global profileName, oldProfileName
	profileName = config.conf.profiles[-1].name
	if profileName == oldProfileName:
		return
	deactivateAnnouncement()
	loadDic()
	if config.conf["emoticons"]["announcement"]:
		activateAnnouncement()
	oldProfileName = profileName
'''

#: NVDA 2026.3 (release-2026.3beta2), speechDictHandler/definitions.py; NVDA 2026.2 has it as _getDictionaryDefinition.
NVDA_2026_3_GET_DICTIONARY_DEFINITION = r'''
def getDictionaryDefinition(source: DictionaryType | str) -> SpeechDictDefinition:
	"""Get the speech dictionary definition for a given source.
	:param source: The source of the speech dictionary, which can be a DictionaryType or a string (e.g., add-on name).
	:return: The corresponding SpeechDictDefinition.
	:raises KeyError: If no definition is found for the given source.
	"""
	for definition in _speechDictDefinitions:
		if definition.source == source:
			return definition
	raise KeyError(f"No speech dictionary definition found for source {source!r}")
'''

#: Emoticons 38.2.0's GlobalPlugin.__init__, the parts about its dictionary: the rest makes its menus.
IMITATION_EMOTICONS_382_PLUGIN = r'''
def __init__(self):
	super(GlobalPlugin, self).__init__()
	for em in emoticons:
		emType = "Emoji" if em.isEmoji else "Emoticon"
		comment = "{type}: {name}".format(type=emType, name=em.name)
		otherReplacement = " %s; " % em.name
		defaultDic.append(SpeechDictEntry(em.pattern, otherReplacement, comment, True, EntryType.REGEXP))
		if not em.isEmoji:
			noEmojisDic.append(SpeechDictEntry(em.pattern, otherReplacement, comment, True, EntryType.REGEXP))
	global profileName, oldProfileName
	profileName = oldProfileName = config.conf.profiles[-1].name
	loadDic()
	announcement = config.conf["emoticons"]["announcement"]
	if announcement:
		activateAnnouncement()
	config.post_configProfileSwitch.register(self.handleConfigProfileSwitch)
'''


class Nvda2026_3(v134.Nvda):
	"""NVDA 2026.3, which still warns for speechDictHandler.dictionaries and has getDictionaryDefinition, with Columns
	Review 5.7.0 and Emoticons 38.2.0 (or 38.0.0)."""

	def __init__(self, test, emoticons="38.2.0"):
		self.emoticonsVersion = emoticons
		super().__init__(test)
		definitions = self.modules["speechDictHandler.definitions"]
		v128.nvdaCode(NVDA_2026_3_GET_DICTIONARY_DEFINITION, "getDictionaryDefinition", vars(definitions))

	def _loadEmoticons(self):
		if self.emoticonsVersion != "38.2.0":
			return super()._loadEmoticons()
		dictTypes = self.modules["speechDictHandler.types"]
		em = self.emoticons = v134.module(
			"globalPlugins.emoticons",
			os=os, config=self.config, speechDictHandler=self.speechDictHandler, globalPluginHandler=self.globalPluginHandler,
			emoticons=v134.EMOTICONS_SMILEYS, profileName=None, oldProfileName=None,
			ADDON_DICTS_PATH=os.path.join(self.folder, "emoticons"),
			ADDON_DIC_DEFAULT_FILE=os.path.join(self.folder, "emoticons", "emoticons.dic"),
			DictionaryType=dictTypes.DictionaryType, EntryType=dictTypes.EntryType, SpeechDict=dictTypes.SpeechDict, SpeechDictEntry=dictTypes.SpeechDictEntry,
		)
		v128.nvdaCode(EMOTICONS_382_DICTIONARIES, "deactivateAnnouncement", vars(em))
		v128.nvdaClass("class GlobalPlugin(globalPluginHandler.GlobalPlugin)", [IMITATION_EMOTICONS_382_PLUGIN, EMOTICONS_382_PROFILE_SWITCH], vars(em))
		sys.modules["globalPlugins.emoticons"] = em
		self.emoticonsPlugin = em.GlobalPlugin()
		self.globalPluginHandler.runningPlugins.add(self.emoticonsPlugin)


class EmoticonsFixedCase(v134.ProfileSwitchCase):
	def nvda(self, assistant=True, emoticons="38.2.0"):
		nvda = Nvda2026_3(self, emoticons=emoticons).install()
		nvda.altTabIntoEdge()
		if assistant:
			profileSwitches.register()
		nvda.records.records.clear()
		nvda.asked = 0
		return nvda

	def altTabRounds(self, nvda, rounds=2):
		"""What NVDA's temporary dictionary holds after each switch of ``rounds`` Alt+Tabs out of Edge and back."""
		held = []
		for _round in range(rounds):
			nvda.altTabOutOfEdge()
			held.append(nvda.temporaryDictionary())
			nvda.altTabIntoEdge()
			held.append(nvda.temporaryDictionary())
		return held


class Emoticons382Tests(EmoticonsFixedCase):
	def test_leftAsItIsAndNoWarning(self):
		without = self.nvda(assistant=False)
		expected = self.altTabRounds(without)
		self.assertEqual(without.warnings(), 0, "Emoticons 38.2.0 reads no deprecated name")
		self.doCleanups()
		self.setUp()
		nvda = self.nvda()
		own = (vars(nvda.emoticons)["deactivateAnnouncement"], vars(nvda.emoticons)["activateAnnouncement"])
		got = self.altTabRounds(nvda)
		# 1.34 read speechDictHandler.dictionaries for Emoticons at each change: 16 warnings for these 8 switches.
		self.assertEqual(nvda.warnings(), 0)
		self.assertEqual((nvda.emoticons.deactivateAnnouncement, nvda.emoticons.activateAnnouncement), own)
		self.assertEqual(got, expected)
		self.assertEqual(len(got[-1]), 88)
		self.assertNotIn("dictionaries", vars(nvda.speechDictHandler))

	def test_columnsReviewIsStillQuick(self):
		nvda = self.nvda()
		self.altTabRounds(nvda)
		self.assertTrue(profileSwitches.isInstalled())
		self.assertEqual(nvda.asked, 1)

	def test_theLogSaysWhyOnce(self):
		nvda = self.nvda()

		def notes():
			return [record for record in nvda.records.records if "doesn't read speechDictHandler.dictionaries" in record.getMessage()]

		# Turned on again after a migration or a configuration reload: nothing new in the log.
		profileSwitches.register()
		self.assertEqual(notes(), [])
		profileSwitches.unregister()
		profileSwitches._logged.clear()
		profileSwitches.register()
		profileSwitches.register()
		self.assertEqual(len(notes()), 1)


class Emoticons380OnNvda2026_3Tests(EmoticonsFixedCase):
	def test_stillOneWarningAChange(self):
		# NVDA 2026.3 still warns for speechDictHandler.dictionaries, and Emoticons 38.0.0 still reads it for each
		# emoticon: the assistant still has it read once for each change, as in 1.34.
		nvda = self.nvda(emoticons="38.0.0")
		self.altTabRounds(nvda)
		self.assertEqual(nvda.warnings(), 8 * 2)
		self.assertTrue(profileSwitches._isOurs(nvda.emoticons.deactivateAnnouncement))


class ReadsDictionariesTests(unittest.TestCase):
	def compiled(self, source, name):
		namespace = {}
		exec(textwrap.dedent(source), namespace)
		return namespace[name]

	def test_emoticons380ReadsIt(self):
		for name in ("activateAnnouncement", "deactivateAnnouncement"):
			self.assertTrue(profileSwitches._readsDictionaries(self.compiled(v134.EMOTICONS_DICTIONARIES.split("\n\n\n", 3)[3], name)), name)

	def test_emoticons382DoesNot(self):
		for name in ("activateAnnouncement", "deactivateAnnouncement"):
			self.assertFalse(profileSwitches._readsDictionaries(self.compiled(EMOTICONS_382_DICTIONARIES.split("\n\n\n", 4)[4], name)), name)

	def test_throughAnotherAddOnsWrapper(self):
		original = self.compiled(v134.EMOTICONS_DICTIONARIES.split("\n\n\n", 3)[3], "deactivateAnnouncement")

		@functools.wraps(original)
		def theirs():
			return original()

		self.assertTrue(profileSwitches._readsDictionaries(theirs))

	def test_whenItCantBeToldAsIn134(self):
		class Callable:
			def __call__(self):
				pass

		self.assertTrue(profileSwitches._readsDictionaries(Callable()))


class OwnCodeTests(unittest.TestCase):
	def check(self, name, path):
		with open(path, encoding="utf-8") as f:
			text = f.read().replace("\r\n", "\n")
		for block in globals()[name].strip("\n").split("\n\n\n"):
			self.assertTrue(block in text or textwrap.indent(block, "\t") in text, f"{name}: {block.splitlines()[0]}")

	def test_theConstantsAreNvdas(self):
		# Set NVDA_2026_3_SOURCE to a folder with NVDA 2026.3's source (release-2026.3beta2 or later).
		source = os.environ.get("NVDA_2026_3_SOURCE")
		if not source:
			self.skipTest("NVDA_2026_3_SOURCE isn't set to a folder with NVDA 2026.3's source")
		self.check("NVDA_2026_3_GET_DICTIONARY_DEFINITION", os.path.join(source, "speechDictHandler", "definitions.py"))

	def test_theConstantsAreEmoticons(self):
		# Set ADDONS_SOURCE to a folder with Emoticons 38.2.0 unpacked into emoticons-38.2.0.
		source = os.environ.get("ADDONS_SOURCE")
		if not source:
			self.skipTest("ADDONS_SOURCE isn't set to a folder with Emoticons 38.2.0")
		path = os.path.join(source, "emoticons-38.2.0", "globalPlugins", "emoticons", "__init__.py")
		self.check("EMOTICONS_382_DICTIONARIES", path)
		self.check("EMOTICONS_382_PROFILE_SWITCH", path)


if __name__ == "__main__":
	unittest.main()
