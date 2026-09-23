# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Facts about the copy of NVDA the assistant runs in, and the voices it can use.

Everything is read from the running NVDA, never assumed: the user's configuration
folder (installed and portable copies keep it in different places), the NVDA
version, installed add-ons, synthesizers, and the SAPI 5, OneCore and Speech
Platform voices on this computer in both 32-bit and 64-bit form.

NVDA modules are imported inside the functions so this module can be loaded,
and fail gracefully, outside NVDA.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import tempfile
from dataclasses import dataclass

try:
	import winreg
except ImportError:  # pragma: no cover
	winreg = None

from . import jawsFiles

ADDON_FOLDER_NAME = "jawsMigrator"
CLASSIC_SPEECH_ID = "ClassicSpeech"


def _log():
	try:
		from logHandler import log

		return log
	except Exception:  # pragma: no cover - outside NVDA
		import logging

		return logging.getLogger("jawsMigrator")


# -- NVDA itself ----------------------------------------------------------------------


def nvdaVersion() -> str:
	try:
		import buildVersion

		return str(buildVersion.version)
	except Exception:
		return "unknown"


def nvdaVersionTuple() -> tuple:
	try:
		import buildVersion

		return (buildVersion.version_year, buildVersion.version_major, buildVersion.version_minor)
	except Exception:
		return (0, 0, 0)


def configDir() -> str:
	"""NVDA's user configuration folder, wherever this copy of NVDA keeps it.

	Outside NVDA (in tests without a stand-in for it) there is none, and a folder in the temporary
	folder stands in, so nothing run outside NVDA reads or writes the settings of an NVDA installed
	on this computer.
	"""
	try:
		from NVDAState import WritePaths

		return WritePaths.configDir
	except Exception:
		pass
	try:
		import globalVars

		return globalVars.appArgs.configPath
	except Exception:
		return os.path.join(tempfile.gettempdir(), "jawsMigrator-outside-nvda")


def appDir() -> str:
	try:
		import globalVars

		return globalVars.appDir
	except Exception:
		return ""


def wavesFolder() -> str:
	folder = appDir()
	return os.path.join(folder, "waves") if folder else ""


def addonDataDir(*parts: str) -> str:
	"""The assistant's own folder inside NVDA's configuration folder."""
	return os.path.join(configDir(), ADDON_FOLDER_NAME, *parts)


def isInstalledCopy() -> bool:
	try:
		import config

		return bool(config.isInstalledCopy())
	except Exception:
		return False


def isAppX() -> bool:
	try:
		import config

		return bool(config.isAppX)
	except Exception:
		return False


def isSecureMode() -> bool:
	try:
		import globalVars

		return bool(getattr(globalVars.appArgs, "secure", False))
	except Exception:
		return False


def shouldWriteToDisk() -> bool:
	try:
		import NVDAState

		return bool(NVDAState.shouldWriteToDisk())
	except Exception:
		return not isSecureMode()


def isWritable(folder: str) -> bool:
	"""Whether a file can be created in ``folder`` (created if missing)."""
	try:
		os.makedirs(folder, exist_ok=True)
		handle, path = tempfile.mkstemp(prefix=".jawsMigrator-", dir=folder)
		os.close(handle)
		os.remove(path)
		return True
	except OSError:
		return False


def freeSpace(folder: str) -> int:
	try:
		return shutil.disk_usage(folder).free
	except OSError:
		return -1


def profileNames() -> list[str]:
	try:
		import config

		return list(config.conf.listProfiles())
	except Exception:
		folder = os.path.join(configDir(), "profiles")
		try:
			return [os.path.splitext(name)[0] for name in os.listdir(folder) if name.lower().endswith(".ini")]
		except OSError:
			return []


def languageCode() -> str:
	try:
		import languageHandler

		return languageHandler.getLanguage()
	except Exception:
		return "en"


def is64BitProcess() -> bool:
	return ctypes.sizeof(ctypes.c_void_p) == 8


# -- add-ons ----------------------------------------------------------------------------


@dataclass
class AddonState:
	"""One copy of an add-on. During an update NVDA lists two: the installed one and the one waiting to replace it."""

	addonId: str
	summary: str = ""
	version: str = ""
	path: str = ""
	disabled: bool = False
	pendingRemove: bool = False
	#: This copy waits to be installed when NVDA restarts; it never runs before that.
	pendingInstall: bool = False
	#: This copy's code runs in this NVDA session.
	running: bool = False
	#: NVDA does not run it because it is not compatible with this version of NVDA.
	blocked: bool = False

	@property
	def usable(self) -> bool:
		return not self.disabled and not self.pendingRemove

	def describe(self) -> str:
		state = []
		if self.disabled:
			state.append("disabled")
		if self.blocked:
			state.append("not running: NVDA considers it incompatible with this version")
		if self.pendingRemove:
			state.append("will be removed when NVDA restarts")
		if self.pendingInstall:
			state.append("will be installed when NVDA restarts")
		text = f"{self.summary or self.addonId} {self.version}".strip()
		return f"{text} ({', '.join(state)})" if state else text


def installedAddons() -> list[AddonState]:
	"""Every add-on NVDA knows about, including ones waiting for a restart."""
	result = []
	try:
		import addonHandler

		for addon in addonHandler.getAvailableAddons():
			manifest = addon.manifest
			waiting = bool(getattr(addon, "isPendingInstall", False))
			result.append(
				AddonState(
					addonId=str(addon.name),
					summary=str(manifest.get("summary") or addon.name),
					version=str(manifest.get("version") or ""),
					path=str(getattr(addon, "path", "")),
					disabled=bool(getattr(addon, "isDisabled", False)),
					pendingRemove=bool(getattr(addon, "isPendingRemove", False)),
					pendingInstall=waiting,
					# NVDA's isRunning also says True for a copy waiting to replace an installed one,
					# because it only looks at the installed folder; that copy never runs before a restart.
					running=bool(getattr(addon, "isRunning", False)) and not waiting,
					blocked=bool(getattr(addon, "isBlocked", False)),
				),
			)
	except Exception:
		_log().debug("jawsMigrator: could not list add-ons", exc_info=True)
		folder = os.path.join(configDir(), "addons")
		try:
			for name in os.listdir(folder):
				manifestPath = os.path.join(folder, name, "manifest.ini")
				if os.path.isfile(manifestPath):
					ini = jawsFiles.readIni(manifestPath)
					section = ini.section("")

					def value(key, default=""):
						text = (section.get(key) if section else "") or default
						return text.strip().strip('"').strip()

					result.append(
						AddonState(
							addonId=value("name", name),
							summary=value("summary"),
							version=value("version"),
							path=os.path.join(folder, name),
							pendingInstall=name.lower().endswith(".pendinginstall"),
						),
					)
		except OSError:
			pass
	return result


def addonState(addonId: str, addons: list[AddonState] | None = None) -> AddonState | None:
	wanted = addonId.lower()
	for addon in addons if addons is not None else installedAddons():
		if addon.addonId.lower() == wanted:
			return addon
	return None


@dataclass
class ClassicSpeechInfo:
	installed: bool = False
	#: ClassicSpeech runs in this NVDA session and is not being removed, so its settings can be changed.
	usable: bool = False
	#: ClassicSpeech's code runs in this NVDA session (it may still be marked for removal).
	running: bool = False
	version: str = ""
	#: The version waiting to replace the running one when NVDA restarts, or "".
	pendingVersion: str = ""
	dataFolder: str = ""
	schemesFolder: str = ""
	settingsFile: str = ""
	describe: str = "not installed"


def classicSpeechInfo(addons: list[AddonState] | None = None) -> ClassicSpeechInfo:
	"""ClassicSpeech as it is in this NVDA session.

	It counts as usable only while it runs. Its settings then live in NVDA's configuration, where it
	saves them to ClassicSpeech\\settings.ini itself. While it doesn't run they are only in that file,
	and writing them through NVDA would put a ``[classicSpeech]`` section in nvda.ini that ClassicSpeech
	later takes for old settings and moves over settings.ini.

	Right after an update NVDA lists two copies: the old one, still running and marked for removal,
	and the new one, waiting to be installed. The old copy is usable for the rest of this session. A
	running copy marked for removal with no new copy waiting is being removed, so it is not usable.
	"""
	info = ClassicSpeechInfo()
	info.dataFolder = os.path.join(configDir(), "ClassicSpeech")
	info.schemesFolder = os.path.join(info.dataFolder, "Schemes")
	info.settingsFile = os.path.join(info.dataFolder, "settings.ini")
	wanted = CLASSIC_SPEECH_ID.lower()
	copies = [addon for addon in (addons if addons is not None else installedAddons()) if addon.addonId.lower() == wanted]
	if not copies:
		return info
	info.installed = True
	running = next((copy for copy in copies if copy.running), None)
	waiting = next((copy for copy in copies if copy.pendingInstall), None)
	current = running or next((copy for copy in copies if not copy.pendingInstall), None) or waiting or copies[0]
	info.running = running is not None
	info.version = current.version
	beingRemoved = running is not None and running.pendingRemove and waiting is None
	info.usable = info.running and not beingRemoved
	if waiting is not None and waiting is not current:
		info.pendingVersion = waiting.version
	notes = []
	if running is None:
		if current.pendingInstall:
			notes.append("will be installed when NVDA restarts")
		elif current.blocked:
			notes.append("not running: NVDA considers it incompatible with this version")
		elif current.disabled:
			notes.append("disabled")
		elif current.pendingRemove:
			notes.append("will be removed when NVDA restarts")
		else:
			notes.append("not running until NVDA restarts")
	elif beingRemoved:
		notes.append("will be removed when NVDA restarts")
	if info.pendingVersion:
		notes.append(f"version {info.pendingVersion} starts after NVDA restarts")
	name = f"{current.summary or CLASSIC_SPEECH_ID} {info.version}".strip()
	info.describe = f"{name} ({'; '.join(notes)})" if notes else name
	return info


# -- synthesizers and voices -------------------------------------------------------------


def synthList() -> list[tuple[str, str]]:
	"""NVDA's usable synthesizers as ``(name, description)``, as its Select Synthesizer dialog lists them."""
	try:
		import synthDriverHandler

		return [(str(name), str(description)) for name, description in synthDriverHandler.getSynthList()]
	except Exception:
		_log().debug("jawsMigrator: could not list synthesizers", exc_info=True)
		return []


def currentSynth() -> dict:
	"""The synthesizer NVDA speaks with now, and its voice settings."""
	result = {"name": "", "description": "", "voice": "", "variant": "", "voices": {}, "variants": {}}
	try:
		import synthDriverHandler

		synth = synthDriverHandler.getSynth()
		if synth is None:
			return result
		result["name"] = synth.name
		result["description"] = synth.description
		settingIds = {setting.id for setting in synth.supportedSettings}
		for settingId in ("voice", "variant", "rate", "pitch", "volume", "inflection"):
			if settingId in settingIds:
				try:
					result[settingId] = getattr(synth, settingId)
				except Exception:
					pass
		if "voice" in settingIds:
			try:
				result["voices"] = {voiceId: (info.displayName, getattr(info, "language", None)) for voiceId, info in synth.availableVoices.items()}
			except Exception:
				pass
		if "variant" in settingIds:
			try:
				result["variants"] = {variantId: info.displayName for variantId, info in synth.availableVariants.items()}
			except Exception:
				pass
	except Exception:
		_log().debug("jawsMigrator: could not read the current synthesizer", exc_info=True)
	return result


def _lcidToLocale(lcidText: str) -> str:
	try:
		lcid = int(lcidText.split(";")[0].strip(), 16)
	except (ValueError, AttributeError):
		return ""
	try:
		buffer = ctypes.create_unicode_buffer(85)
		if ctypes.windll.kernel32.LCIDToLocaleName(lcid, buffer, 85, 0):
			return buffer.value.replace("-", "_")
	except Exception:
		pass
	return jawsFiles.LCID_LANGUAGES.get(lcid, "")


def _registryTokens(category: str, view) -> list[dict]:
	tokens = []
	if winreg is None:
		return tokens
	path = category + r"\Tokens"
	try:
		with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ | view) as key:
			index = 0
			while True:
				try:
					name = winreg.EnumKey(key, index)
				except OSError:
					break
				index += 1
				token = {"id": "HKEY_LOCAL_MACHINE\\" + path + "\\" + name, "name": name, "vendor": "", "language": "", "clsid": ""}
				try:
					with winreg.OpenKey(key, name) as tokenKey:
						try:
							token["name"] = winreg.QueryValueEx(tokenKey, "")[0] or name
						except OSError:
							pass
						try:
							token["clsid"] = winreg.QueryValueEx(tokenKey, "CLSID")[0]
						except OSError:
							pass
						try:
							with winreg.OpenKey(tokenKey, "Attributes") as attributes:
								for attribute in ("Vendor", "Language", "Name"):
									try:
										value = winreg.QueryValueEx(attributes, attribute)[0]
									except OSError:
										continue
									if attribute == "Language":
										token["language"] = _lcidToLocale(str(value))
									elif attribute == "Name" and not token["name"]:
										token["name"] = str(value)
									elif attribute == "Vendor":
										token["vendor"] = str(value)
						except OSError:
							pass
				except OSError:
					pass
				tokens.append(token)
	except OSError:
		pass
	return tokens


def _clsidServerExists(clsid: str, view) -> bool:
	if winreg is None or not clsid:
		return False
	try:
		with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\InprocServer32", 0, winreg.KEY_READ | view):
			return True
	except OSError:
		return False


def sapi5Voices() -> list[dict]:
	"""SAPI 5 voices, each tagged with the NVDA driver that can use it (sapi5 or sapi5_32).

	Voices made up at run time by a SAPI token enumerator have no registry keys, so the
	64-bit list also comes from SAPI itself.
	"""
	voices: dict[str, dict] = {}
	if winreg is not None:
		for view, driver in ((winreg.KEY_WOW64_64KEY, "sapi5"), (winreg.KEY_WOW64_32KEY, "sapi5_32")):
			for token in _registryTokens(r"SOFTWARE\Microsoft\Speech\Voices", view):
				has64 = _clsidServerExists(token["clsid"], winreg.KEY_WOW64_64KEY)
				has32 = _clsidServerExists(token["clsid"], winreg.KEY_WOW64_32KEY)
				token["driver"] = "sapi5" if has64 else ("sapi5_32" if has32 else driver)
				key = (token["driver"] + "|" + token["name"]).lower()
				voices.setdefault(key, token)
	try:
		import comtypes.client

		spVoice = comtypes.client.CreateObject("SAPI.SpVoice")
		tokens = spVoice.GetVoices()
		for index in range(tokens.Count):
			token = tokens.Item(index)
			name = token.GetDescription()
			entry = {"id": token.Id, "name": name, "vendor": "", "language": "", "clsid": "", "driver": "sapi5"}
			for attribute in ("Vendor", "Language"):
				try:
					value = token.GetAttribute(attribute)
				except Exception:
					continue
				entry["vendor" if attribute == "Vendor" else "language"] = _lcidToLocale(value) if attribute == "Language" else str(value)
			voices.setdefault(("sapi5|" + name).lower(), entry)
	except Exception:
		_log().debug("jawsMigrator: SAPI 5 voices could not be listed through SAPI", exc_info=True)
	return sorted(voices.values(), key=lambda voice: (voice["driver"], voice["name"].lower()))


def oneCoreVoices() -> list[dict]:
	if winreg is None:
		return []
	voices = _registryTokens(r"SOFTWARE\Microsoft\Speech_OneCore\Voices", winreg.KEY_WOW64_64KEY)
	for voice in voices:
		voice["driver"] = "oneCore"
	return voices


def speechPlatformVoices() -> list[dict]:
	if winreg is None:
		return []
	voices = []
	for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
		for token in _registryTokens(r"SOFTWARE\Microsoft\Speech Server\v11.0\Voices", view):
			token["driver"] = "mssp"
			if all(existing["name"] != token["name"] for existing in voices):
				voices.append(token)
	return voices


# -- braille ---------------------------------------------------------------------------


def brailleDisplayList() -> list[tuple[str, str]]:
	try:
		import braille

		return [(str(name), str(description)) for name, description, *_rest in braille.getDisplayList()]
	except Exception:
		return []
