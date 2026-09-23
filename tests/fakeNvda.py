# A small imitation of the parts of NVDA the migration writes to, backed by a temporary folder.
# It is enough to run a whole migration end to end outside NVDA and look at what it wrote.

import enum
import json
import os
import shutil
import sys
import types
from dataclasses import dataclass

import nvdaStubs


class Profile(dict):
	def __init__(self, name=None, filename=""):
		super().__init__()
		self.name = name
		self.filename = filename
		self.manual = False
		self.triggered = False


class View:
	def __init__(self, conf, path):
		self._conf = conf
		self._path = path

	def _lookup(self, profile, key):
		node = profile
		for part in self._path:
			node = node.get(part)
			if not isinstance(node, dict):
				return None, False
		if key in node:
			return node[key], True
		return None, False

	def __getitem__(self, key):
		isSection = False
		for profile in reversed(self._conf.profiles):
			value, found = self._lookup(profile, key)
			if found:
				if isinstance(value, dict):
					isSection = True
					continue
				if not isSection:
					return value
		return View(self._conf, self._path + [key])

	def get(self, key, default=None):
		value = self[key]
		return default if isinstance(value, View) and not self._conf.sectionExists(self._path + [key]) else value

	def __contains__(self, key):
		return any(self._lookup(profile, key)[1] for profile in self._conf.profiles)

	def __setitem__(self, key, value):
		node = self._conf.profiles[-1]
		for part in self._path:
			node = node.setdefault(part, {})
		node[key] = value
		self._conf.dirty.add(self._conf.profiles[-1].name)


class ConfigManager:
	def __init__(self, configDir):
		self.configDir = configDir
		self.base = Profile(None, os.path.join(configDir, "nvda.ini"))
		self.profiles = [self.base]
		self._profileCache = {}
		self.profileTriggersEnabled = True
		self.triggersToProfiles = {}
		self.dirty = set()
		self.saved = 0

	def sectionExists(self, path):
		for profile in self.profiles:
			node = profile
			for part in path:
				node = node.get(part) if isinstance(node, dict) else None
			if isinstance(node, dict):
				return True
		return False

	def __getitem__(self, key):
		return View(self, [])[key]

	def __setitem__(self, key, value):
		View(self, [])[key] = value

	def __contains__(self, key):
		return key in View(self, [])

	def listProfiles(self):
		folder = os.path.join(self.configDir, "profiles")
		try:
			return [os.path.splitext(name)[0] for name in os.listdir(folder) if name.endswith(".ini")]
		except OSError:
			return []

	def createProfile(self, name):
		folder = os.path.join(self.configDir, "profiles")
		os.makedirs(folder, exist_ok=True)
		path = os.path.join(folder, name + ".ini")
		if os.path.exists(path):
			raise ValueError("exists")
		open(path, "w").close()

	def _getProfile(self, name):
		if name not in self._profileCache:
			path = os.path.join(self.configDir, "profiles", name + ".ini")
			profile = Profile(name, path)
			try:
				with open(path, encoding="utf-8") as stream:
					text = stream.read()
				if text.strip():
					profile.update(json.loads(text))
			except (OSError, ValueError):
				pass
			self._profileCache[name] = profile
		return self._profileCache[name]

	def manualActivateProfile(self, name):
		if len(self.profiles) > 1 and self.profiles[-1].manual:
			self.profiles.pop().manual = False
		if name:
			profile = self._getProfile(name)
			profile.manual = True
			self.profiles.append(profile)

	def disableProfileTriggers(self):
		self.profileTriggersEnabled = False

	def enableProfileTriggers(self):
		self.profileTriggersEnabled = True

	def saveProfileTriggers(self):
		with open(os.path.join(self.configDir, "profileTriggers.ini"), "w", encoding="utf-8") as stream:
			json.dump(self.triggersToProfiles, stream, indent=1)

	def save(self):
		self.saved += 1
		with open(self.base.filename, "w", encoding="utf-8") as stream:
			json.dump(self.base, stream, indent=1)
		for name in list(self.dirty):
			if name:
				profile = self._getProfile(name)
				with open(profile.filename, "w", encoding="utf-8") as stream:
					json.dump(profile, stream, indent=1)
		self.dirty.clear()


@dataclass
class Setting:
	id: str


@dataclass
class Info:
	id: str
	displayName: str
	language: str = None


class FakeSynth:
	voicesByDriver = {
		"ibmeci": {"65536": ("American English", "en_US"), "65537": ("British English", "en_GB")},
		"sapi5": {"HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\TTS_MS_EN-US_ZIRA_11.0": ("Microsoft Zira Desktop", "en_US")},
		"espeak": {"en": ("English", "en")},
	}

	def __init__(self, name, conf):
		self.name = name
		self.description = {"ibmeci": "IBMTTS", "sapi5": "Microsoft Speech API version 5", "espeak": "eSpeak NG"}.get(name, name)
		self._conf = conf
		ids = ["voice", "rate", "pitch", "volume", "inflection"]
		if name == "ibmeci":
			ids.insert(1, "variant")
		self.supportedSettings = [Setting(x) for x in ids]
		self.availableVoices = {vid: Info(vid, label, language) for vid, (label, language) in self.voicesByDriver.get(name, {}).items()}
		self.availableVariants = {str(i): Info(str(i), n) for i, n in enumerate(["Reed", "Shelley", "Sandy", "Rocko", "Glen", "FastFlo", "Grandma", "Grandpa"], start=1)} if name == "ibmeci" else {}
		self.voice = next(iter(self.availableVoices), "")
		self.variant = "1"
		self.rate = 50
		self.pitch = 50
		self.volume = 100
		self.inflection = 50

	def saveSettings(self):
		for setting in self.supportedSettings:
			self._conf["speech"][self.name][setting.id] = getattr(self, setting.id)


def install(configDir, appDir, frame):
	nvdaStubs.install(frame)
	conf = ConfigManager(configDir)
	conf.base.update({"speech": {"synth": "espeak", "symbolLevel": 100}, "keyboard": {"keyboardLayout": "desktop"}})

	def module(name, **attributes):
		stub = sys.modules.get(name) or types.ModuleType(name)
		for key, value in attributes.items():
			setattr(stub, key, value)
		sys.modules[name] = stub
		return stub

	module("config", conf=conf, isInstalledCopy=lambda: True, isAppX=False)
	module("globalVars", appDir=appDir, appArgs=types.SimpleNamespace(secure=False, configPath=configDir), speechDictionaryProcessing=True)

	class WritePaths:
		pass

	WritePaths.configDir = configDir
	WritePaths.getSymbolsConfigFile = staticmethod(lambda locale: os.path.join(configDir, f"symbols-{locale}.dic"))
	module("NVDAState", WritePaths=WritePaths, shouldWriteToDisk=lambda: True)
	module("buildVersion", version="2026.2", version_year=2026, version_major=2, version_minor=0)
	current = {"synth": FakeSynth("espeak", conf)}

	def setSynth(name, isFallback=False):
		if name not in FakeSynth.voicesByDriver:
			return False
		current["synth"] = FakeSynth(name, conf)
		conf["speech"]["synth"] = name
		return True

	module(
		"synthDriverHandler",
		getSynth=lambda: current["synth"],
		setSynth=setSynth,
		getSynthList=lambda: [("ibmeci", "IBMTTS"), ("sapi5", "Microsoft Speech API version 5"), ("espeak", "eSpeak NG")],
	)

	class DictionaryType(enum.Enum):
		DEFAULT = "default"
		VOICE = "voice"

	class EntryType(enum.IntEnum):
		ANYWHERE = 0
		REGEXP = 1
		WORD = 2

	@dataclass
	class SpeechDictEntry:
		pattern: str
		replacement: str
		comment: str = ""
		caseSensitive: bool = True
		type: EntryType = EntryType.ANYWHERE

	class SpeechDict(list):
		fileName = None

		def save(self, fileName=None):
			with open(fileName or self.fileName, "w", encoding="utf-8") as stream:
				for entry in self:
					stream.write(f"{entry.pattern}\t{entry.replacement}\t{int(entry.caseSensitive)}\t{int(entry.type)}\n")

		def load(self, fileName):
			self.fileName = fileName

	defaultDict = SpeechDict()
	defaultDict.fileName = os.path.join(configDir, "speechDicts", "default.dic")
	voiceDict = SpeechDict()
	voiceDict.fileName = os.path.join(configDir, "speechDicts", "voiceDicts.v1", "voice.dic")
	os.makedirs(os.path.dirname(voiceDict.fileName), exist_ok=True)
	definitions = types.SimpleNamespace(
		_speechDictDefinitions=[
			types.SimpleNamespace(source=DictionaryType.DEFAULT, dictionary=defaultDict),
			types.SimpleNamespace(source=DictionaryType.VOICE, dictionary=voiceDict),
		],
	)
	speechDictHandler = module("speechDictHandler", definitions=definitions)
	module("speechDictHandler.types", DictionaryType=DictionaryType, EntryType=EntryType, SpeechDictEntry=SpeechDictEntry)
	sys.modules["speechDictHandler.definitions"] = definitions
	speechDictHandler.types = sys.modules["speechDictHandler.types"]

	class Symbols:
		def fetchLocaleData(self, locale, fallback=True):
			if locale != "en":
				raise LookupError(locale)
			return object()

	module("characterProcessing", terminate=lambda: None, initialize=lambda: None, _localeSpeechSymbolProcessors=Symbols())
	module("speech", getCurrentLanguage=lambda: "en_US")
	module("core", resetConfiguration=lambda: None, restart=lambda: None)
	module("languageHandler", getLanguage=lambda: "en")

	class GestureMap:
		def __init__(self, fileName):
			self._map = {}
			self.fileName = fileName
			# Load what the user already has, as NVDA does at start up.
			section = None
			if os.path.isfile(fileName):
				for line in open(fileName, encoding="utf-8"):
					line = line.strip()
					if line.startswith("[") and line.endswith("]"):
						section = line[1:-1]
					elif "=" in line and section:
						script, gestures = (part.strip() for part in line.split("=", 1))
						module, className = section.rsplit(".", 1)
						for gesture in gestures.split(","):
							self.add(gesture.strip(), module, className, None if script == "None" else script)

		def add(self, gesture, module, className, script, replace=False):
			self._map.setdefault(gesture.lower(), []).append((module, className, script))

		def getScriptsForGesture(self, gesture):
			return iter(self._map.get(gesture, []))

		def save(self):
			sections = {}
			for gesture, scripts in self._map.items():
				for module, className, script in scripts:
					sections.setdefault(f"{module}.{className}", {}).setdefault(str(script), []).append(gesture)
			with open(self.fileName, "w", encoding="utf-8") as stream:
				for section, entries in sections.items():
					stream.write(f"[{section}]\n")
					for script, gestures in entries.items():
						stream.write(f"\t{script} = {', '.join(gestures)}\n")

	manager = types.SimpleNamespace(
		userGestureMap=GestureMap(os.path.join(configDir, "gestures.ini")),
		localeGestureMap=GestureMap(os.path.join(configDir, "locale-gestures.ini")),
		_captureFunc=None,
	)
	module("inputCore", manager=manager, normalizeGestureIdentifier=lambda identifier: identifier.lower())
	return conf, current


def makeNvdaFolders(root):
	configDir = os.path.join(root, "nvda-config")
	appDir = os.path.join(root, "nvda-program")
	os.makedirs(configDir)
	os.makedirs(os.path.join(appDir, "waves"))
	realWaves = r"C:\Program Files\NVDA\waves"
	if os.path.isdir(realWaves):
		for name in os.listdir(realWaves):
			shutil.copy(os.path.join(realWaves, name), os.path.join(appDir, "waves", name))
	with open(os.path.join(configDir, "gestures.ini"), "w", encoding="utf-8") as stream:
		stream.write("[globalCommands.GlobalCommands]\n\ttoggleScreenCurtain = kb:f11+nvda\n")
	return configDir, appDir
