# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""The rate, pitch and volume you set for NVDA's voice apply everywhere, not only in the program or on the page you set them in.

A tester turned the speech volume down in NVDA's Settings and wrote (issue 49): "It will stay quiet for a little while then
get louder", and later "when I'm typing in this box it is at the lower volume I set. When it is reading it is louder." NVDA's
log shows what it was. As NVDA loaded his settings, three configurations held a volume of their own: his normal
configuration, 100; "browseMode", the profile the Custom Browse Mode add-on turns on whenever browse mode is on, 100; and
"JAWS - msedge", the profile the migration made for Edge, 78 and, after he set it again, 80. NVDA uses the value of the
profile turned on last, so reading a page in Edge, with "browseMode" on top of "JAWS - msedge", was at 100, and an edit
field, where browse mode is off, at 80.

His own steps put the 80 where it was. NVDA saves a changed setting into the profile turned on last (ConfigManager: "Changed
settings are written to the most recently activated profile"), and opening Settings from Edge leaves "JAWS - msedge" the
last one, which NVDA says as "Editing profile JAWS - msedge" when the Speech category comes up. So the volume applied in Edge
and not on a page, and nowhere else. NVDA's settings ring (and JAWS's keys for the voice rate, which the assistant gives it)
writes into the profile turned on last too, which in browse mode is "browseMode"; so does NVDA+Shift+J, then D, which turns
audio ducking on or off.

The Eloquence add-on he uses (Eloquence64RS 19.1.4) keeps a copy of the voice's settings for each set of turned-on
profiles, applies the copy when NVDA switches to that set, and writes the copy into the profile turned on last when NVDA's own
value differs (synthDrivers.eloquence, _apply_profile_snapshot and _sync_profile_snapshot_to_config). A volume changed in one
set is not in the copies of the others, so for it to apply everywhere those copies have to change too.

Someone who turns the voice down means it for everything they hear, and the assistant already keeps ClassicSpeech's voices from
holding a rate, pitch or volume of their own, so that the user's NVDA ones apply everywhere (see classicRepair). So, while this
is on, what you set in NVDA's Settings, Speech, with the settings ring, or with NVDA+Shift+J, then D, is made the setting
everywhere, once you have changed it: the normal configuration gets it, and the same setting is taken out of "browseMode" and
of the profiles for single programs that the migration (and Quick Settings) make, where it would hide the new one.
Eloquence64RS's copies are changed to match. A change made while a profile of your own is the one NVDA writes to (one you
turned on by hand in NVDA's Configuration Profiles dialog, or that turns on in a program of its own) stays in that profile:
it is what that profile is for.

Settings already different when this is first on (the tester's 100, 100 and 80) can't be told apart from ones you chose, so
once, a while after NVDA starts, a question asks which value should apply everywhere, after NVDA's settings are backed up.
Nothing is changed if you leave it as it is, and it isn't asked again for the same values. It can be turned off in NVDA's
Settings, JAWS Migration Assistant.
"""

from __future__ import annotations

import functools
import sys
import threading
from dataclasses import dataclass, field

#: The assistant's setting (state.json) that turns this on or off, and the questions already asked.
STATE_KEY = "keepSpeechEven"
ASKED_KEY = "evenSpeechAsked"

#: What NVDA calls its base configuration (ConfigManager gives it no name).
NORMAL_CONFIGURATION = "normal configuration"
#: The profile the Custom Browse Mode add-on turns on, by hand, whenever browse mode is on.
BROWSE_MODE_PROFILE = "browseMode"
#: The migration's profiles for single programs start with this (migrator.APP_PROFILE_PREFIX).
APP_PROFILE_PREFIX = "JAWS - "
#: The settings of a voice that are kept the same everywhere, and what the voice question calls them.
VOICE_SETTINGS = ("rate", "pitch", "volume", "inflection")
SETTING_NAMES = {"rate": "speech rate", "pitch": "pitch", "volume": "speech volume", "inflection": "inflection"}
#: The module of Eloquence64RS's driver, and what it keeps for each set of profiles.
ELOQUENCE_MODULE = "synthDrivers.eloquence"
ELOQUENCE_SNAPSHOTS = "_profile_settings_by_stack"
ELOQUENCE_PENDING = "_pending_profile_setting_changes"
#: Marks what the assistant put over NVDA's own, and which copy of this module did.
MARK = "_jawsMigratorEvenSpeech"
ORIGINAL = "_jawsMigratorEvenSpeechOriginal"
_TOKEN = object()

_enabled = False
#: What the assistant put over NVDA's own: [(owner, name, installed, original)].
_installed: list = []
#: What has been written to the debug log as a failure already.
_failures: set = set()


def _log():
	from logHandler import log

	return log


def _failure(what: str) -> None:
	"""Say once, in the assistant's debug log, that something went wrong; speech goes on as NVDA has it."""
	if what in _failures:
		return
	_failures.add(what)
	try:
		from . import debugLog

		debugLog.error(what)
	except Exception:
		pass


def _note(message: str) -> None:
	try:
		from . import debugLog

		debugLog.note(message)
	except Exception:
		pass


def wanted(stateData: dict) -> bool:
	"""Whether the rate, pitch and volume you set apply everywhere: on unless turned off."""
	return isinstance(stateData, dict) and bool(stateData.get(STATE_KEY, True))


# -- Which profile a change goes to, and which profiles hide it -------------------------------


def profileName(profile) -> str:
	return getattr(profile, "name", None) or NORMAL_CONFIGURATION


def isAppProfile(name: str) -> bool:
	"""Whether ``name`` is one of the migration's (or Quick Settings') profiles for a single program."""
	return str(name).lower().startswith(APP_PROFILE_PREFIX.lower())


def isBrowseModeProfile(name: str) -> bool:
	return str(name).lower() == BROWSE_MODE_PROFILE.lower()


def isGuarded(name: str) -> bool:
	"""Whether a voice setting in the profile ``name`` is taken out when you set it for everywhere.

	Only profiles nobody chose to give a voice setting: the migration's for single programs (the migration never writes
	a rate, pitch or volume into them) and Custom Browse Mode's. A profile you made yourself is never touched.
	"""
	return isAppProfile(name) or isBrowseModeProfile(name)


def settlesEverywhere(conf, fromDialog: bool) -> bool:
	"""Whether a change just written to NVDA's configuration should be made the setting everywhere.

	NVDA writes to the profile turned on last. That is the normal configuration, one of the migration's profiles for a
	program (which NVDA turned on by itself, when the program has the focus), or Custom Browse Mode's "browseMode", which
	it turns on by hand while browse mode is on. A profile of the user's own, or any profile turned on by hand while
	nothing is being read in browse mode, is one the user chose to edit: the change stays in it. NVDA's Settings opens on
	a profile turned on by hand only when the user turned it on, as browse mode is off when its window has the focus, so
	"browseMode" there is the user's too. The settings ring and NVDA+Shift+J, D are used in the page itself.
	"""
	profiles = list(getattr(conf, "profiles", ()) or ())
	if len(profiles) < 2:
		return True
	top = profiles[-1]
	name = profileName(top)
	if getattr(top, "manual", False):
		return (not fromDialog) and isBrowseModeProfile(name)
	return isAppProfile(name)


# -- NVDA's profiles, as plain sections ---------------------------------------------------------


def _section(profile, path: tuple):
	"""The section at ``path`` in a profile, or None."""
	section = profile
	for part in path:
		try:
			section = section[part]
		except (KeyError, TypeError, IndexError):
			return None
	return section if hasattr(section, "keys") else None


def rawValue(profile, path: tuple, key: str):
	"""What a profile itself holds for ``key`` in the section at ``path``: None when nothing, as NVDA writes a setting
	into a profile only when it differs from those below."""
	section = _section(profile, path)
	if section is None:
		return None
	try:
		# dict.get: the stored value, without ConfigObj's interpolation of %(...)s.
		return dict.get(section, key)
	except TypeError:
		return section.get(key)


def _put(profile, path: tuple, key: str, value) -> None:
	"""Set ``key`` in the section at ``path`` of one profile, making the sections that are missing."""
	section = profile
	for part in path:
		try:
			section = section[part]
		except KeyError:
			section[part] = {}
			section = section[part]
	section[key] = value


def _discard(profile, path: tuple, key: str) -> bool:
	"""Take ``key`` out of the section at ``path`` of one profile, and the sections left empty. True when it was there."""
	parents = []
	section = profile
	for part in path:
		try:
			child = section[part]
		except (KeyError, TypeError):
			return False
		if not hasattr(child, "keys"):
			return False
		parents.append((section, part))
		section = child
	if key not in section:
		return False
	del section[key]
	while parents and len(section) == 0:
		parent, part = parents.pop()
		del parent[part]
		section = parent
	return True


def guardedProfiles(conf) -> list:
	"""``[(name, profile)]`` for every guarded profile NVDA has, loaded as NVDA loads one it turns on."""
	found = []
	try:
		names = sorted(conf.listProfiles(), key=str.lower)
	except Exception:
		return found
	for name in names:
		if not isGuarded(name):
			continue
		try:
			found.append((name, conf._getProfile(name)))
		except Exception:
			_failure(f"the profile {name} could not be read, so the speech settings in it are left as they are")
	return found


def _markDirty(conf, name: str) -> None:
	"""Have NVDA save the profile ``name`` (it saves the normal configuration every time)."""
	dirty = getattr(conf, "_dirtyProfiles", None)
	if isinstance(dirty, set):
		dirty.add(name)


def _refresh(conf) -> None:
	"""Have NVDA read its settings again from the profiles, as it does at a profile switch, but without telling anything
	that the profiles switched: the value now in use is the one that was just set. NVDA keeps what it read in the
	sections it made from the profiles, and those would go on giving the old value."""
	handle = getattr(conf, "_handleProfileSwitch", None)
	if callable(handle):
		try:
			handle(False)
		except Exception:
			_failure("NVDA could not read its settings again after the speech settings were made the same everywhere")


def stackValue(conf, stack, path: tuple, key: str):
	"""What the configurations in ``stack`` (names, the normal configuration first) give ``key``: the last one that holds it."""
	value = None
	for index, name in enumerate(stack):
		if index == 0 and name == NORMAL_CONFIGURATION:
			profile = conf.profiles[0]
		else:
			try:
				profile = conf._getProfile(name)
			except Exception:
				return None
		held = rawValue(profile, path, key)
		if held is not None:
			value = held
	return value


# -- Eloquence64RS's copies ---------------------------------------------------------------------


def refreshEloquence(conf, path: tuple, key: str) -> int:
	"""Make Eloquence64RS's copy of ``key`` for each set of profiles what the profiles now give. Returns how many changed.

	Its driver puts a set's copy back, into the profile turned on last, whenever the copy differs from what NVDA gives
	(see the top). Done through the driver's own names, only where there are such copies, and nothing else of it is touched.
	"""
	if path != ("speech", "eloquence"):
		return 0
	module = sys.modules.get(ELOQUENCE_MODULE)
	copies = getattr(module, ELOQUENCE_SNAPSHOTS, None)
	if not isinstance(copies, dict):
		return 0
	changed = 0
	for stack, settings in list(copies.items()):
		if not isinstance(settings, dict) or key not in settings or not isinstance(stack, tuple):
			continue
		value = stackValue(conf, stack, path, key)
		if value is None or str(settings[key]) == str(value):
			continue
		try:
			settings[key] = int(value) if isinstance(settings[key], int) else str(value)
		except (TypeError, ValueError):
			continue
		changed += 1
	pending = getattr(module, ELOQUENCE_PENDING, None)
	if isinstance(pending, dict):
		# Changes the driver took for a settings dialog that has not saved them: now saved, or not wanted.
		for pendingKey in [k for k in pending if isinstance(k, tuple) and len(k) == 2 and k[1] == key]:
			del pending[pendingKey]
	return changed


# -- Making a setting the same everywhere -------------------------------------------------------


@dataclass
class Outcome:
	#: True when the normal configuration was changed.
	wrote: bool = False
	#: The guarded profiles the setting was taken out of.
	purged: list = field(default_factory=list)
	#: How many of Eloquence64RS's copies were changed.
	eloquence: int = 0

	@property
	def changed(self) -> bool:
		return bool(self.wrote or self.purged or self.eloquence)


def makeEverywhere(path: tuple, key: str, value, conf=None) -> Outcome:
	"""Make ``key`` in the section at ``path`` (("speech", "eloquence"), ("audio",)) ``value`` in the normal configuration,
	and take it out of every guarded profile, so that no profile NVDA turns on hides it. Main thread."""
	if conf is None:
		import config

		conf = config.conf
	outcome = Outcome()
	base = conf.profiles[0]
	held = rawValue(base, path, key)
	if held is None or str(held) != str(value):
		_put(base, path, key, value)
		outcome.wrote = True
	for name, profile in guardedProfiles(conf):
		if profile is base:
			continue
		if _discard(profile, path, key):
			outcome.purged.append(name)
			_markDirty(conf, name)
	if outcome.wrote or outcome.purged:
		_refresh(conf)
	outcome.eloquence = refreshEloquence(conf, path, key)
	return outcome


def afterChange(path: tuple, key: str, value, fromDialog: bool = False):
	"""A change of ``key`` to ``value`` was just written to NVDA's configuration by the user: make it the setting everywhere,
	unless it was written to a profile the user chose. Returns the outcome, or None where nothing was done."""
	if not _enabled:
		return None
	import config

	conf = config.conf
	if not settlesEverywhere(conf, fromDialog):
		return None
	try:
		outcome = makeEverywhere(path, key, value, conf)
	except Exception:
		_failure(f"{'.'.join(path)}.{key} could not be made the same everywhere")
		return None
	if outcome.changed:
		_note(f"{'.'.join(path)}.{key} = {value!r} everywhere: " + _describeOutcome(outcome))
	return outcome


def _describeOutcome(outcome: Outcome) -> str:
	parts = []
	parts.append("set in the normal configuration" if outcome.wrote else "the normal configuration already had it")
	if outcome.purged:
		parts.append("taken out of " + ", ".join(outcome.purged))
	if outcome.eloquence:
		parts.append(f"Eloquence's remembered value changed for {outcome.eloquence} sets of profiles")
	return "; ".join(parts)


# -- NVDA's own ways of changing the voice ----------------------------------------------------------


def _isOurs(function) -> bool:
	return getattr(function, MARK, None) is _TOKEN


def _voiceNow():
	"""``(synthesizer name, {setting: value NVDA has for it now})`` for the settings kept even, or None."""
	import config
	import synthDriverHandler

	synth = synthDriverHandler.getSynth()
	if synth is None:
		return None
	name = synth.name
	supported = {setting.id for setting in synth.supportedSettings}
	values = {}
	for key in VOICE_SETTINGS:
		if key not in supported:
			continue
		try:
			value = config.conf["speech"][name][key]
		except (KeyError, TypeError):
			continue
		if isinstance(value, (str, int, float)):
			values[key] = value
	return name, values


def _afterSettingsDialog(before) -> None:
	now = _voiceNow()
	if not before or not now or before[0] != now[0]:
		return
	name = now[0]
	for key, value in now[1].items():
		if key not in before[1] or str(before[1][key]) != str(value):
			afterChange(("speech", name), key, value, fromDialog=True)


def _voicePanelSave(original):
	"""Settings, Speech: what was changed there is made the setting everywhere once NVDA has saved it."""

	@functools.wraps(original)
	def onSave(panel, *args, **kwargs):
		if not _enabled:
			return original(panel, *args, **kwargs)
		try:
			before = _voiceNow()
		except Exception:
			before = None
		result = original(panel, *args, **kwargs)
		try:
			_afterSettingsDialog(before)
		except Exception:
			_failure("the speech settings could not be made the same everywhere after NVDA's Settings saved them")
		return result

	setattr(onSave, MARK, _TOKEN)
	setattr(onSave, ORIGINAL, original)
	return onSave


def _ringSetter(original):
	"""The settings ring (NVDA+Control+Arrow keys, and JAWS's keys for the voice rate): the setting it just changed is made
	the setting everywhere."""

	@functools.wraps(original)
	def setValue(setting, value):
		original(setting, value)
		if not _enabled:
			return
		try:
			key = setting.setting.id
			if key in VOICE_SETTINGS:
				afterChange(("speech", setting.synth.name), key, value)
		except Exception:
			_failure("the speech setting the settings ring changed could not be made the same everywhere")

	setattr(setValue, MARK, _TOKEN)
	setattr(setValue, ORIGINAL, original)
	return setValue


def _installDialog() -> bool:
	try:
		from gui import settingsDialogs

		panel = settingsDialogs.VoiceSettingsPanel
	except Exception:
		_failure("NVDA's Speech settings are not where the assistant looks, so a change made there is saved as NVDA saves it")
		return False
	current = vars(panel).get("onSave")
	if not callable(current):
		_failure("NVDA's Speech settings do not save as the assistant knows, so a change made there is saved as NVDA saves it")
		return False
	if _isOurs(current):
		return True
	installed = _voicePanelSave(current)
	setattr(panel, "onSave", installed)
	_installed.append((panel, "onSave", installed, current))
	return True


def _installRing() -> bool:
	try:
		import synthSettingsRing

		owner = synthSettingsRing.SynthSetting
	except Exception:
		_failure("NVDA's settings ring is not where the assistant looks, so a change made with it is saved as NVDA saves it")
		return False
	# NVDA made the property "value" from the class's _get_value and _set_value when it made the class, so putting a
	# function over _set_value now would change nothing: the property is replaced.
	current = vars(owner).get("value")
	if not isinstance(current, property) or current.fset is None:
		_failure("NVDA's settings ring does not set a value as the assistant knows, so a change made with it is saved as NVDA saves it")
		return False
	if _isOurs(current.fset):
		return True
	installed = property(current.fget, _ringSetter(current.fset), current.fdel, current.__doc__)
	setattr(owner, "value", installed)
	_installed.append((owner, "value", installed, current))
	return True


def register() -> None:
	"""Make what is set for the voice in NVDA's Settings, with the settings ring and with the assistant's audio ducking key
	the setting everywhere, from now on."""
	global _enabled
	_enabled = True
	_installDialog()
	_installRing()


def unregister() -> None:
	"""Give NVDA's Speech settings and settings ring back as they were, where nothing has been put over the assistant's since."""
	global _enabled
	_enabled = False
	for owner, name, installed, original in reversed(_installed):
		try:
			if vars(owner).get(name) is installed:
				setattr(owner, name, original)
		except Exception:
			pass
	_installed.clear()


def isRegistered() -> bool:
	return _enabled


# -- Settings that are already different ---------------------------------------------------------------


def _phrase(name: str) -> str:
	if name == NORMAL_CONFIGURATION:
		return "NVDA's normal configuration"
	return f'the profile "{name}"'


def _listed(items: list, parts: bool = False) -> str:
	"""``items`` as a list in a sentence: "a and b", "a, b, and c". ``parts``: items that have "and" in them, so two are
	"a, and b"."""
	if len(items) <= 1 or (len(items) == 2 and not parts):
		return " and ".join(items)
	return ", ".join(items[:-1]) + ", and " + items[-1]


def _rank(name: str) -> int:
	"""Which value the question puts first: one a program's profile holds, which is where NVDA's Settings put what the
	user set, then the normal configuration's, then Custom Browse Mode's."""
	if isAppProfile(name):
		return 0
	if name == NORMAL_CONFIGURATION:
		return 1
	return 2


@dataclass
class Difference:
	"""A voice setting that has different values in the configurations NVDA turns on."""

	key: str
	synth: str
	#: ``[(configuration, value as text)]``: the normal configuration first, then each guarded profile that holds one.
	places: list

	@property
	def label(self) -> str:
		return SETTING_NAMES.get(self.key, self.key)

	@property
	def values(self) -> list:
		"""The different values, in the order the question offers them."""
		ordered = sorted(enumerate(self.places), key=lambda item: (_rank(item[1][0]), item[0]))
		values = []
		for _index, (_name, value) in ordered:
			if value not in values:
				values.append(value)
		return values

	def where(self, value: str) -> str:
		return _listed([_phrase(name) for name, held in self.places if held == value])

	@property
	def signature(self) -> str:
		"""What was asked about, so the same question isn't asked again."""
		return f"{self.synth}.{self.key}:" + "|".join(sorted(f"{name}={value}" for name, value in self.places))

	def question(self) -> str:
		held = [f"{value} in {self.where(value)}" for value in self.values]
		return (
			f"Your {self.label} is not the same everywhere, so it changes as you move between programs and web pages. "
			f"It is {_listed(held, parts=True)}. Which {self.label} should apply everywhere?"
		)

	def choices(self) -> list:
		return [f"{value}, as in {self.where(value)}" for value in self.values] + ["Leave it as it is"]


def differenceFor(conf, synthName: str, key: str, default=None):
	"""The ``Difference`` for one setting of the synthesizer ``synthName``, or None when every configuration agrees.

	The normal configuration counts with its own value, or the setting's default where it holds none.
	"""
	path = ("speech", synthName)
	places = []
	value = rawValue(conf.profiles[0], path, key)
	if value is None:
		value = default
	if value is not None:
		places.append((NORMAL_CONFIGURATION, str(value)))
	for name, profile in guardedProfiles(conf):
		held = rawValue(profile, path, key)
		if held is not None:
			places.append((name, str(held)))
	if len({value for _name, value in places}) < 2:
		return None
	return Difference(key, synthName, places)


def currentDifferences(conf=None) -> list:
	"""The differences in the voice NVDA speaks with now."""
	import synthDriverHandler

	if conf is None:
		import config

		conf = config.conf
	synth = synthDriverHandler.getSynth()
	if synth is None:
		return []
	settings = {setting.id: setting for setting in synth.supportedSettings}
	found = []
	for key in VOICE_SETTINGS:
		if key not in settings:
			continue
		difference = differenceFor(conf, synth.name, key, getattr(settings[key], "defaultVal", None))
		if difference is not None:
			found.append(difference)
	return found


def _asDialog(question: str, choices: list):
	"""Ask with a list of choices, and say which was chosen (its index), or None when the question was left."""
	import wx

	from .gui import common

	common.prePopup()
	try:
		dialog = wx.SingleChoiceDialog(None, question, common.TITLE, choices)
		try:
			dialog.SetSelection(0)
			if dialog.ShowModal() != wx.ID_OK:
				return None
			return dialog.GetSelection()
		finally:
			dialog.Destroy()
	finally:
		common.postPopup()


def offerOnce(announce, backupFirst, done=None, ask=None) -> None:
	"""Once for each different set of values, a while after NVDA starts: ask which should apply everywhere. Main thread.

	``backupFirst(reason)`` backs NVDA's settings up and returns the backup; it runs in the background. Nothing changes where
	the user leaves the question or closes it. ``ask(question, choices)`` says the index of the choice, None for none. ``done()``
	is called on the main thread when it is over.
	"""
	from . import debugLog, migrator, nvdaEnv, state

	finished = migrator.callOnce(done)
	started = False
	try:
		if not wanted(state.load()) or not nvdaEnv.shouldWriteToDisk():
			return
		asked = list(state.get(ASKED_KEY) or [])
		pending = [difference for difference in currentDifferences() if difference.signature not in asked]
		if not pending:
			return
		chosen = []
		for difference in pending:
			index = (ask or _asDialog)(difference.question(), difference.choices())
			values = difference.values
			picked = index is not None and 0 <= index < len(values)
			debugLog.note(f"{difference.synth}.{difference.key} differs ({difference.signature}): the user chose {values[index] if picked else 'to leave it'}")
			if picked:
				chosen.append((difference, values[index]))
			else:
				# Left as it is, or the question closed: not asked again for these values. A choice that is made is not
				# written down: once it is made the values are the same everywhere, and where it could not be made
				# (NVDA's settings could not be backed up) the question is asked again when NVDA next starts.
				asked.append(difference.signature)
		state.set(ASKED_KEY, asked[-100:])
		if not chosen:
			return

		def work():
			outcome = None
			try:
				outcome = (chosen, backupFirst("Before making NVDA's speech settings the same everywhere"))
			except Exception as error:
				debugLog.error("NVDA's settings could not be backed up, so the speech settings are left as they are")
				outcome = error
			import wx

			wx.CallAfter(finish, outcome)

		def finish(outcome):
			try:
				_applyChoices(outcome, announce)
			finally:
				finished()

		threading.Thread(target=work, name="jawsMigratorEvenSpeech", daemon=True).start()
		started = True
	except Exception:
		debugLog.error("the question about speech settings that differ failed")
	finally:
		if not started:
			finished()


def _applyChoices(outcome, announce) -> None:
	import synthDriverHandler

	from . import debugLog, nvdaApply

	if isinstance(outcome, Exception):
		return
	chosen, backupInfo = outcome
	done = []
	for difference, value in chosen:
		try:
			number = int(value)
		except (TypeError, ValueError):
			number = value
		try:
			result = makeEverywhere(("speech", difference.synth), difference.key, number)
			done.append((difference, value))
			debugLog.note(
				f"speech.{difference.synth}.{difference.key} = {value} everywhere: {_describeOutcome(result)}; backup {backupInfo.path if backupInfo else ''}",
			)
		except Exception:
			debugLog.error(f"the {difference.label} could not be made {value} everywhere")
	if not done:
		return
	try:
		nvdaApply.saveConfig()
	except Exception:
		debugLog.error("NVDA's settings could not be saved after the speech settings were made the same everywhere")
	try:
		synth = synthDriverHandler.getSynth()
		if synth is not None:
			synth.loadSettings(onlyChanged=True)
	except Exception:
		debugLog.error("the synthesizer did not take the new speech settings yet; it does after NVDA restarts")
	text = _listed([f"{difference.label} is now {value}" for difference, value in done])
	announce(f"JAWS Migration Assistant: NVDA's {text} everywhere. NVDA's settings were backed up first.")
