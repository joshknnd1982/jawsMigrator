# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""The user's choice of exactly what to import: each JAWS setting, scheme, voice profile and voice alias.

Every importable thing a migration plan contains becomes an ``ImportItem`` with a
stable key, such as ``setting:nvda:keyboard.speakTypedCharacters``,
``scheme:Web RentACrowd (from JAWS)``, ``profile:Eloquence`` or
``alias:LinkVoice``. The choice is kept in the assistant's state file as the keys
the user turned off (and the few, off by default, that they turned on), so items
that appear later, for example after changing JAWS, are imported unless the user
says otherwise. Nothing here needs NVDA.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import classicSounds, voices

STATE_KEY = "importSelection"

SETTINGS = "settings"
SCHEMES = "schemes"
PROFILES = "voiceProfiles"
ALIASES = "voiceAliases"
KEYBOARD = "keyboard"
OTHER = "other"

CATEGORIES = (
	(SETTINGS, "JAWS settings (Settings Center)"),
	(SCHEMES, "Speech and sound schemes"),
	(PROFILES, "Voice profiles"),
	(ALIASES, "Voice aliases"),
	(KEYBOARD, "Keyboard settings and layouts (desktop, laptop...)"),
	(OTHER, "Dictionaries, punctuation, sounds and applications"),
)
CATEGORY_LABELS = dict(CATEGORIES)


@dataclass
class ImportItem:
	key: str
	category: str
	label: str
	#: Whether the item is imported when the user has not chosen.
	default: bool = True
	#: False for items this computer cannot use, such as a voice profile with no NVDA synthesizer.
	available: bool = True
	reason: str = ""


def _settingKey(change) -> str:
	return f"setting:{change.target}:{change.key}"


def buildItems(plan) -> list[ImportItem]:
	"""Every importable item in a migration plan, grouped by category."""
	items: list[ImportItem] = []
	for change in plan.settings.changes:
		source = f" (JAWS: {change.source})" if change.source else ""
		prefix = "ClassicSpeech: " if change.target == "classicSpeech" and not change.label.startswith("ClassicSpeech") else ""
		category = KEYBOARD if change.target == "nvda" and change.key.startswith("keyboard.") else SETTINGS
		items.append(ImportItem(_settingKey(change), category, f"{prefix}{change.label}{source}"))
	for scheme in plan.schemes:
		voiceItems = sum(1 for item in scheme.items.values() if item.voiceAlias)
		items.append(
			ImportItem(
				f"scheme:{scheme.name}",
				SCHEMES,
				f"{scheme.name}: {scheme.soundCount} sounds, {voiceItems} voices",
				available=plan.classicSpeech,
				reason="" if plan.classicSpeech else "needs ClassicSpeech",
			),
		)
	for profilePlan in plan.profiles:
		label = ("Your JAWS voice: " if profilePlan.primary else "") + profilePlan.describe()
		reason = ""
		if profilePlan.option is None:
			reason = "no NVDA synthesizer for it on this computer"
		elif profilePlan.sharedWith:
			reason = f"its NVDA synthesizer already takes the {profilePlan.sharedWith} profile"
		items.append(ImportItem(f"profile:{profilePlan.name}", PROFILES, label, available=not reason, reason=reason))
	aliasValues: dict[str, list[str]] = {}
	for profilePlan in plan.profiles:
		for name, value in profilePlan.aliases.items():
			if voices.aliasIsNeutral(value):
				continue
			aliasValues.setdefault(name, [])
			entry = f"{profilePlan.name}: {value}"
			if entry not in aliasValues[name]:
				aliasValues[name].append(entry)
	for name in sorted(aliasValues, key=str.lower):
		values = aliasValues[name]
		shown = "; ".join(values[:3]) + (f"; and {len(values) - 3} more" if len(values) > 3 else "")
		items.append(
			ImportItem(
				f"alias:{name}",
				ALIASES,
				f"{name}: {shown}",
				available=plan.classicSpeech,
				reason="" if plan.classicSpeech else "needs ClassicSpeech",
			),
		)
	items.append(ImportItem("keyboard:gestures", KEYBOARD, f"JAWS keystrokes as NVDA input gestures ({len(plan.keys.bindings)} with the keyboard layouts chosen)"))
	for layout in plan.keyboardLayouts:
		inUse = layout.id == plan.jawsKeyboardLayout
		items.append(ImportItem(f"keyboard:layout:{layout.id}", KEYBOARD, f"{layout.name} keyboard layout: " + layout.describe(inUse).split(": ", 1)[1], default=inUse))
	items.append(ImportItem("keyboard:quickNav", KEYBOARD, "JAWS quick navigation letters in browse mode"))
	userRules = sum(len(d.defaultEntries) + len(d.voiceEntries) for d in plan.dictionaries if d.source.scope == "user")
	sharedRules = sum(len(d.defaultEntries) + len(d.voiceEntries) for d in plan.dictionaries if d.source.scope == "shared")
	others = [
		("other:dictionaries", f"Your dictionary rules ({userRules})", True, True),
		("other:sharedDictionaries", f"Freedom Scientific's own dictionary rules ({sharedRules})", False, sharedRules > 0),
		("other:symbols", f"Punctuation and symbols you changed ({len(plan.symbols)})", True, True),
		("other:jawsSymbolNames", f"JAWS's names for all punctuation symbols ({len(plan.jawsSymbolDefaults)})", False, bool(plan.jawsSymbolDefaults)),
		("other:classicVoices", "The voices JAWS uses for the JAWS cursor and messages, as ClassicSpeech Voice Profiles (the person only)", False, plan.classicSpeech),
		("other:classicSettings", "JAWS verbosity, number and text settings in ClassicSpeech", True, plan.classicSpeech),
		("other:archive", "Keep a copy of your JAWS settings with NVDA's settings", True, True),
	]
	for key, label, default, available in others:
		items.append(ImportItem(key, OTHER, label, default=default, available=available, reason="" if available else "nothing to import"))
	# JAWS sounds play through ClassicSpeech, so both need it.
	allSounds = classicSounds.uniqueSounds(plan.index.wavFiles()) if plan.index is not None else []
	for key, label, default, found in (
		("other:sounds", f"JAWS sounds in place of NVDA's sounds, through ClassicSpeech ({len(plan.sounds)})", False, bool(plan.sounds)),
		("other:allSounds", f"All {len(allSounds)} JAWS sounds copied into ClassicSpeech, as the scheme {classicSounds.JAWS_SOUNDS_SCHEME}", True, bool(allSounds)),
	):
		reason = "" if plan.classicSpeech and found else ("needs ClassicSpeech" if not plan.classicSpeech else "nothing to import")
		items.append(ImportItem(key, OTHER, label, default=default, available=not reason, reason=reason))
	for configName in plan.appSettings:
		items.append(ImportItem(f"app:{configName}", OTHER, f"NVDA profile for {configName}, from its JAWS settings"))
	for configName, executables in plan.sleepCandidates:
		items.append(ImportItem(f"sleep:{configName}", OTHER, f"NVDA sleeps in {configName} ({', '.join(executables)}), as JAWS did"))
	return items


class Selection:
	"""Which items are chosen. Stored as exceptions to each item's default."""

	def __init__(self, excluded=None, included=None, customized: bool = False):
		self.excluded = set(excluded or ())
		self.included = set(included or ())
		self.customized = customized

	def isSelected(self, item: ImportItem) -> bool:
		if not item.available:
			return False
		if item.key in self.included:
			return True
		return item.default and item.key not in self.excluded

	def set(self, item: ImportItem, selected: bool) -> None:
		self.customized = True
		self.excluded.discard(item.key)
		self.included.discard(item.key)
		if selected and not item.default:
			self.included.add(item.key)
		elif not selected and item.default:
			self.excluded.add(item.key)

	def toDict(self) -> dict:
		return {"version": 1, "customized": self.customized, "excluded": sorted(self.excluded), "included": sorted(self.included)}

	@classmethod
	def fromDict(cls, data) -> "Selection":
		if not isinstance(data, dict):
			return cls()
		return cls(data.get("excluded") or (), data.get("included") or (), bool(data.get("customized")))


def load() -> Selection:
	from . import state

	return Selection.fromDict(state.get(STATE_KEY))


def save(selection: Selection) -> None:
	from . import state

	state.set(STATE_KEY, selection.toDict())


def apply(plan, selection: Selection) -> None:
	"""Narrow a migration plan and its options to the chosen items."""
	if not selection.customized:
		return
	items = {item.key: item for item in buildItems(plan)}

	def chosen(key: str, default: bool = True) -> bool:
		item = items.get(key)
		return selection.isSelected(item) if item is not None else default

	options = plan.options
	plan.settings.changes = [change for change in plan.settings.changes if chosen(_settingKey(change))]
	options.schemes = [scheme.name for scheme in plan.schemes if chosen(f"scheme:{scheme.name}")]
	options.classicSchemes = bool(options.schemes)
	if options.activeClassicScheme and options.activeClassicScheme not in options.schemes:
		options.activeClassicScheme = ""
	options.voiceProfiles = [profilePlan.name for profilePlan in plan.profiles if chosen(f"profile:{profilePlan.name}")]
	primary = next((profilePlan for profilePlan in plan.profiles if profilePlan.primary), None)
	if primary is not None and primary.name not in options.voiceProfiles:
		# The JAWS voice was left out, so NVDA keeps its own synthesizer and voice.
		options.voiceChoice = -1
	options.voiceAliases = sorted(key[len("alias:") :] for key in items if key.startswith("alias:") and chosen(key))
	options.dictionaries = chosen("other:dictionaries")
	options.sharedDictionaries = chosen("other:sharedDictionaries", False)
	options.symbols = chosen("other:symbols")
	options.jawsSymbolNames = chosen("other:jawsSymbolNames", False)
	options.keyboard = chosen("keyboard:gestures")
	options.quickNavLetters = chosen("keyboard:quickNav")
	options.keyboardLayouts = [layout.id for layout in plan.keyboardLayouts if chosen(f"keyboard:layout:{layout.id}", layout.id == plan.jawsKeyboardLayout)]
	options.sounds = chosen("other:sounds", False)
	options.allSounds = chosen("other:allSounds")
	options.classicVoices = chosen("other:classicVoices", False)
	options.classicSettings = chosen("other:classicSettings")
	options.archive = chosen("other:archive")
	plan.appSettings = {name: mapping for name, mapping in plan.appSettings.items() if chosen(f"app:{name}")}
	options.appProfiles = bool(plan.appSettings)
	options.sleepApps = [name for name, _exes in plan.sleepCandidates if chosen(f"sleep:{name}")]
	options.selectionApplied = True


def summary(items: list[ImportItem], selection: Selection) -> str:
	chosen = sum(1 for item in items if selection.isSelected(item))
	usable = sum(1 for item in items if item.available)
	return f"{chosen} of {usable} items selected"
