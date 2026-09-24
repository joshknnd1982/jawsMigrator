# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Keyboard Manager and Navigation Quick Keys: JAWS keystrokes as NVDA input gestures.

Only keystrokes of the JAWS default key map (for every application) become NVDA
gestures, and only for JAWS commands NVDA really has (see ``jawsKeyMap``).

JAWS has a keyboard layout for each kind of computer keyboard: Desktop, Laptop,
Classic Laptop and Kinesis, and others in some JAWS versions. Each layout adds its
own keystrokes to the common ones. The user chooses the layouts to bring over; each
one's keystrokes become gestures of the matching NVDA keyboard layout (desktop or
laptop), so they work whenever NVDA uses that layout.

Every key is decided separately for each NVDA keyboard layout NVDA will use:

- A layout's own keystroke replaces the common one, as in JAWS, even when NVDA has no
  equivalent for it. Where Caps Lock is the JAWS key (the Laptop layout), keystrokes written
  with JAWSKey or CapsLock decide what the gesture NVDA+key does, because NVDA calls Insert
  and Caps Lock both NVDA there. An Insert keystroke with a command of its own on the same key
  becomes an ``InsertKey``, which the assistant runs itself while Insert is held.
- Keystrokes NVDA already uses for the same command are left alone. A keystroke NVDA uses
  for something else is only taken over when asked; in browse mode, quick navigation
  letters take over NVDA's letters when the JAWS letters are wanted.
- A common keystroke becomes a ``kb:`` gesture when it works the same in both NVDA layouts,
  and a ``kb(desktop):`` or ``kb(laptop):`` gesture when it only may in one.

Application key maps and JAWS-only commands are listed for the report.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import jawsFiles, jawsKeyMap

SKIP_PASSTHROUGH = "passthrough"
SKIP_UNCONVERTIBLE = "unconvertible"
SKIP_NO_EQUIVALENT = "noEquivalent"
SKIP_SAME = "same"
SKIP_CONFLICT = "conflict"
SKIP_LEASEY = "leasey"
SKIP_QUICKNAV = "quickNavOff"
SKIP_LAYOUT = "otherLayout"
SKIP_DUPLICATE = "duplicate"

_UNCONVERTIBLE_REASONS = {
	"layered": "a layered keystroke (keys pressed one after another), which NVDA does not have",
	"braille": "a braille display key",
	"modifierOnly": "a modifier key on its own",
	"unsupportedKey": "a key NVDA cannot use (such as a MAGic or HomeRow key)",
	"unknownKey": "a key name the assistant does not know",
	"badModifier": "a key NVDA cannot use as a modifier",
	"empty": "an empty key",
}


@dataclass
class GestureBinding:
	gesture: str
	module: str
	className: str
	script: str
	description: str
	jawsKey: str
	jawsScript: str
	section: str
	replaces: list = field(default_factory=list)
	#: ``(module, class)`` whose own binding of this gesture must be removed (a ``None`` binding in the
	#: user's gesture map) so this binding runs: classes NVDA asks before ``globalCommands``.
	unbind: list = field(default_factory=list)

	@property
	def label(self) -> str:
		text = f"{self.jawsKey}: {self.description}"
		if self.replaces:
			text += " (replaces NVDA's " + ", ".join(self.replaces) + ")"
		return text


@dataclass
class SkippedKey:
	jawsKey: str
	jawsScript: str
	section: str
	reason: str
	kind: str


@dataclass
class InsertKey:
	"""A JAWS keystroke that runs one command with Insert and another with Caps Lock as the JAWS key.

	In the JAWS Laptop layout, Caps Lock is the JAWS key, yet Insert+J still opens the JAWS window
	while Caps Lock+J says the previous word. NVDA calls both NVDA+J, so gestures.ini can't hold
	both: the Caps Lock keystroke gets the gesture, and the assistant runs this command itself when
	the NVDA key held down is Insert (see ``insertKeys``).
	"""

	#: The NVDA gesture both keystrokes make, such as ``kb(laptop):NVDA+j``.
	gesture: str
	module: str
	className: str
	script: str
	description: str
	#: The Insert keystroke and its JAWS command, such as ``Insert+J`` and ``JAWSWindow``.
	jawsKey: str
	jawsScript: str
	section: str
	#: The Caps Lock keystroke on the same key and its JAWS command, such as ``JAWSKey+J`` and ``SayPriorWord``.
	capsLockKey: str
	capsLockScript: str
	#: NVDA's own commands that Insert with this key no longer runs.
	replaces: list = field(default_factory=list)

	@property
	def label(self) -> str:
		text = f"{self.jawsKey}: {self.description}, with Insert; {self.capsLockKey} ({self.capsLockScript}) stays with Caps Lock"
		if self.replaces:
			text += " (with Insert, replaces NVDA's " + ", ".join(self.replaces) + ")"
		return text


@dataclass
class KeyPlan:
	bindings: list = field(default_factory=list)
	skipped: list = field(default_factory=list)
	applicationKeys: dict = field(default_factory=dict)
	#: Insert keystrokes that differ from the Caps Lock keystroke on the same key (see InsertKey).
	insertKeys: list = field(default_factory=list)

	def countSkipped(self, kind: str) -> int:
		return sum(1 for item in self.skipped if item.kind == kind)


def _sectionKind(sectionName: str) -> str | None:
	return jawsKeyMap.getSectionLayout(sectionName)


@dataclass
class JawsLayout:
	"""A JAWS keyboard layout with keystrokes of its own in the default key map."""

	#: Lower case, such as ``laptop`` or ``classic laptop``.
	id: str
	#: The name JAWS shows, such as ``Laptop``.
	name: str
	#: The NVDA keyboard layout its keystrokes belong to: ``desktop`` or ``laptop``.
	nvdaLayout: str
	#: The key map section with its keystrokes, such as ``Laptop Keys``.
	section: str
	keyCount: int = 0
	#: True when Caps Lock is the JAWS key in this layout (the Laptop layout).
	capsLock: bool = False

	def describe(self, inUse: bool = False) -> str:
		text = f"{self.name}: {self.keyCount} keystrokes of its own, for NVDA's {self.nvdaLayout} keyboard layout"
		if self.capsLock:
			text += "; Caps Lock is the JAWS key"
		if self.id in LAYOUT_NOTES:
			text += "; " + LAYOUT_NOTES[self.id]
		if inUse:
			text += " (the layout your JAWS uses)"
		return text


#: JAWS keyboard layouts the assistant knows: id -> (name JAWS shows, NVDA keyboard layout).
#: Desktop and Kinesis keyboards have a number pad and use Insert as the JAWS key; Laptop uses
#: Caps Lock; Classic Laptop is the older Alt+letter layout for keyboards without a number pad.
KNOWN_LAYOUTS = {
	"desktop": ("Desktop", "desktop"),
	"laptop": ("Laptop", "laptop"),
	"classic laptop": ("Classic Laptop", "laptop"),
	"kinesis": ("Kinesis", "desktop"),
}
#: What a user should know before choosing a layout.
LAYOUT_NOTES = {"classic laptop": "its Alt+letter keys take those keystrokes away from programs"}
#: Layouts for Freedom Scientific notetakers, not computer keyboards.
DEVICE_LAYOUTS = frozenset({"pac mate"})


def layoutId(keyboardType: str | None) -> str:
	"""The layout id for JAWS's KeyboardType setting (``Laptop``, ``Classic Laptop``...)."""
	value = " ".join((keyboardType or "").split()).lower()
	return value or "desktop"


def keyboardLayouts(jkm: jawsFiles.IniFile) -> list[JawsLayout]:
	"""The JAWS keyboard layouts this key map has keystrokes for.

	JAWS lists its layouts in ``[Keyboard Layouts]`` (``Laptop=Common``: the Laptop layout
	adds ``[Laptop Keys]`` to the common keys); Classic Laptop only has sections of its own.
	Layouts of other JAWS versions and languages are found the same way.
	"""
	names: dict = {}
	listing = jkm.section("keyboard layouts")
	for name, base in listing.items() if listing is not None else ():
		layout = layoutId(name)
		if layout in DEVICE_LAYOUTS or not name.strip():
			continue
		known = KNOWN_LAYOUTS.get(layout)
		names[layout] = known or (name.strip(), "laptop" if "laptop" in f"{layout} {base}".lower() else "desktop")
	for layout, known in KNOWN_LAYOUTS.items():
		names.setdefault(layout, known)
	result = []
	for layout, (name, nvdaLayout) in names.items():
		section = jkm.section(f"{name} Keys")
		if section is None or not len(section):
			continue
		modifiers = jkm.section(f"{name} Modifiers")
		if modifiers is not None:
			capsLock = "capslock" in (key.lower() for key in modifiers.keys())
		else:
			capsLock = layout == "laptop"
		result.append(JawsLayout(layout, name, nvdaLayout, section.name, len(section), capsLock))
	return result


def _sectionsInOrder(jkm: jawsFiles.IniFile, current: str) -> list:
	"""``(section, JawsLayout or None)``: other sections in file order, then the layouts, the one in use first.

	Keystrokes of the layout in use then win over another layout's for the same NVDA layout.
	"""
	layouts = {layout.section.lower(): layout for layout in keyboardLayouts(jkm)}
	others = []
	layoutSections = []
	for section in jkm.sections.values():
		layout = layouts.get(section.name.lower())
		if layout is None:
			others.append((section, None))
		else:
			layoutSections.append((section, layout))
	layoutSections.sort(key=lambda pair: pair[1].id != current)
	return others + layoutSections


#: NVDA's keyboard layouts, in the order their gestures are listed.
NVDA_LAYOUTS = ("desktop", "laptop")
#: The class NVDA asks last for a script, after browse mode documents and the focused control.
_GLOBAL_COMMANDS = ("globalCommands", "GlobalCommands")


@dataclass
class _Line:
	"""A convertible keystroke of the key map, ready to be planned."""

	order: int
	section: object
	#: The JAWS layout whose own section this is; None for the common and browse mode sections.
	layout: JawsLayout | None
	#: ``browse`` for virtual cursor sections, whose bindings are browse mode commands; ``normal`` otherwise.
	group: str
	key: str
	script: str
	gesture: str
	#: ``kb``, ``kb(desktop)`` or ``kb(laptop)``.
	prefix: str
	#: The gesture without its prefix, as written: ``NVDA+shift+h``.
	main: str
	#: ``main`` as NVDA normalizes it: lower case and sorted.
	keys: str
	#: The JAWS key names, lower case: ``{"jawskey", "shift", "h"}``.
	tokens: frozenset
	passThrough: bool
	quickNav: bool
	targets: tuple

	@property
	def nvdaLayouts(self) -> tuple:
		"""The NVDA keyboard layouts in which the gesture fires."""
		return NVDA_LAYOUTS if self.prefix == "kb" else (self.prefix[3:-1],)

	@property
	def usesNvdaKey(self) -> bool:
		return bool(self.tokens & jawsKeyMap.JAWS_MODIFIER_TOKENS)

	def capsLockKey(self, capsLockLayout: bool) -> bool:
		"""Whether this keystroke's JAWS key is Caps Lock.

		``JAWSKey`` means the JAWS key of the section's own layout; in the common sections, that of the
		JAWS layout that decides the NVDA layout (``capsLockLayout`` is True for the Laptop layout).
		"""
		if "capslock" in self.tokens:
			return True
		if "jawskey" in self.tokens:
			return self.layout.capsLock if self.layout is not None else capsLockLayout
		return False


@dataclass
class _Bound:
	"""A binding NVDA or the user already has for the keys of a gesture."""

	module: str
	className: str
	#: None where the gesture map unbinds the keystroke for that class.
	script: str | None
	#: The NVDA keyboard layout of the binding's gesture, None for both.
	layout: str | None
	#: ``class`` (the class binds it itself), ``user`` (gestures.ini), ``locale``, or ``addon`` (another
	#: add-on's global plugin binds it; NVDA asks those before anything else).
	source: str

	@property
	def location(self) -> tuple:
		return (self.module, self.className)


@dataclass
class _Decision:
	#: ``bind``, ``same``, ``conflict``, or ``blocked``: a binding in the user's gestures.ini would run instead.
	kind: str
	others: list = field(default_factory=list)
	unbind: list = field(default_factory=list)


def _identifierLayout(identifier) -> str | None:
	prefix = str(identifier or "").split(":", 1)[0].strip().lower()
	if prefix.startswith("kb(") and prefix.endswith(")"):
		return prefix[3:-1]
	return None


def _boundEntries(boundScripts, gesture: str) -> list:
	"""What ``boundScripts`` reports for ``gesture``, as ``_Bound`` items.

	Entries are ``(module, class, script)``, optionally followed by the gesture identifier of the
	binding and where it comes from (see ``nvdaApply.gestureBoundScripts``). Without those, a binding
	counts for both NVDA layouts and as the class's own.
	"""
	entries = []
	if boundScripts is None:
		return entries
	for entry in boundScripts(gesture) or ():
		entry = tuple(entry)
		if len(entry) < 3:
			continue
		identifier = entry[3] if len(entry) > 3 else None
		source = entry[4] if len(entry) > 4 else "class"
		entries.append(_Bound(entry[0], entry[1], entry[2], _identifierLayout(identifier), source))
	return entries


def _userEntryWins(entry: _Bound, target: tuple) -> bool:
	"""Whether a binding in the user's gestures.ini runs instead of a new one for ``target``.

	NVDA uses the first gesture map entry whose class fits the object it asks, and asks
	``globalCommands`` last. A new binding comes after the user's own, so it can't win over one on
	its own class, nor over one on a class NVDA may ask first.
	"""
	location = tuple(target[:2])
	if entry.location == location:
		return True
	if entry.location == _GLOBAL_COMMANDS:
		return False
	if entry.script is None:
		# That unbinding only stops NVDA asking its class; NVDA still goes on to globalCommands.
		return location != _GLOBAL_COMMANDS
	return True


def _decide(target: tuple, entries: list, layout: str, overrideAllowed: bool) -> _Decision:
	"""What to do with ``target`` in one NVDA keyboard layout, given what is bound there already."""
	here = [entry for entry in entries if entry.layout in (None, layout)]
	unbound = {entry.location for entry in here if entry.script is None}
	current = [entry for entry in here if entry.script is not None and entry.location not in unbound]
	if any((entry.module, entry.className, entry.script) == tuple(target[:3]) for entry in current):
		return _Decision("same")
	winners = [entry for entry in here if entry.source == "user" and _userEntryWins(entry, target)]
	if winners:
		return _Decision("blocked", winners)
	if not current:
		return _Decision("bind")
	if not overrideAllowed:
		return _Decision("conflict", current)
	unbind = []
	if tuple(target[:2]) == _GLOBAL_COMMANDS:
		# NVDA asks browse mode documents and the focused control before globalCommands: remove their
		# own binding of these keys, or the JAWS command would never run there.
		unbind = sorted({entry.location for entry in current if entry.source != "user" and entry.location != _GLOBAL_COMMANDS})
	else:
		# NVDA asks the add-ons' global plugins before any other class.
		unbind = sorted({entry.location for entry in current if entry.source == "addon"})
	return _Decision("bind", current, unbind)


def _sameBinding(first: _Decision, second: _Decision) -> bool:
	"""Whether two layouts' decisions to bind replace and unbind the same things."""

	def replaced(decision):
		return sorted((entry.module, entry.className, entry.script) for entry in decision.others)

	return replaced(first) == replaced(second) and sorted(first.unbind) == sorted(second.unbind)


def _decisionText(decision: _Decision) -> str:
	if decision.kind == "blocked":
		assigned = sorted({entry.script for entry in decision.others if entry.script})
		removed = sorted({entry.className for entry in decision.others if not entry.script})
		parts = []
		if assigned:
			parts.append("assign this keystroke to " + ", ".join(assigned))
		if removed:
			parts.append("take it away from " + ", ".join(removed))
		return f"your NVDA input gestures (gestures.ini) {' and '.join(parts)}, and a new gesture can't take their place"
	names = ", ".join(sorted({entry.script for entry in decision.others if entry.script and entry.source != "addon"}))
	addons = ", ".join(sorted({f"{_addonName(entry.module)} ({entry.script})" for entry in decision.others if entry.script and entry.source == "addon"}))
	parts = []
	if names:
		parts.append(f"NVDA already uses this keystroke for {names}")
	if addons:
		parts.append(f"the add-on {addons} uses this keystroke")
	return "; ".join(parts) or "NVDA already uses this keystroke"


def _keptReason(decisions: dict, layouts: list, qualify: bool) -> str:
	"""Why a keystroke is kept for NVDA in ``layouts``, naming the layouts where that matters."""
	texts: dict = {}
	for layout in layouts:
		texts.setdefault(_decisionText(decisions[layout]), []).append(layout)
	if len(texts) == 1 and not qualify:
		return next(iter(texts))
	return "; ".join(f"{text} (NVDA's {' and '.join(names)} keyboard layout{'s' if len(names) > 1 else ''})" for text, names in texts.items())


def _rank(line: _Line, capsLockLayout: bool) -> tuple:
	"""Sort key of the keystrokes for one key in one NVDA layout: the first one decides what the key does.

	A layout's own keystroke replaces the common one. Where Caps Lock is the JAWS key, keystrokes with
	Caps Lock come before those with Insert, which NVDA can't tell apart from Caps Lock.
	"""
	insertKey = capsLockLayout and line.usesNvdaKey and not line.capsLockKey(capsLockLayout)
	return (insertKey, line.layout is None, line.order)


def _lostTo(line: _Line, winner: _Line, capsLockLayout: bool, decidingLayout) -> str:
	"""Why ``line`` does not decide its key, or "" when it needs no mention (the same command)."""
	if line.layout is not None and winner.layout is not None and winner.layout.id != line.layout.id:
		# Two chosen JAWS layouts for one NVDA layout: the one in use wins.
		return f"{winner.section.name} already uses this keystroke for {winner.script}"
	if jawsKeyMap.normalizeScriptName(winner.script) == jawsKeyMap.normalizeScriptName(line.script):
		return ""
	owner = winner.layout or decidingLayout
	if capsLockLayout and line.usesNvdaKey and not line.capsLockKey(capsLockLayout) and winner.capsLockKey(capsLockLayout):
		return (
			f"Caps Lock is the JAWS key of the JAWS {owner.name if owner else 'Laptop'} layout, where {winner.key} runs {winner.script}; "
			"NVDA can't tell Insert from Caps Lock, so the Caps Lock keystroke decides"
		)
	if winner.layout is not None:
		return f"the JAWS {winner.layout.name} layout uses this keystroke for {winner.script}"
	return f"{winner.key} already uses this keystroke for {winner.script}"


def planKeys(
	jkm: jawsFiles.IniFile,
	keyboardLayout: str,
	boundScripts=None,
	scriptExists=None,
	quickNavLetters: bool = True,
	overrideConflicts: bool = False,
	leaseyActive: bool = False,
	layouts=None,
	nvdaLayout: str | None = None,
) -> KeyPlan:
	"""Work out which JAWS keystrokes become NVDA gestures.

	``keyboardLayout`` is the JAWS keyboard layout in use (``desktop``, ``laptop``,
	``classic laptop``...). ``layouts`` lists the JAWS layouts whose own keystrokes are wanted;
	None takes just the one in use. ``nvdaLayout`` is NVDA's keyboard layout after the migration
	(``desktop`` or ``laptop``); keys are planned for it and for the NVDA layouts of the chosen JAWS
	layouts. None plans for both NVDA layouts, for when NVDA may use either.

	``boundScripts(gesture)`` returns what NVDA already binds to the keys of a gesture, as
	``(module, class, script)`` tuples, optionally followed by the binding's gesture identifier and
	source (see ``nvdaApply.gestureBoundScripts``); ``scriptExists(module, class, script)`` confirms a
	target is present in this NVDA. Both may be None outside NVDA.
	"""
	plan = KeyPlan()
	current = layoutId(keyboardLayout)
	wanted = {current} if layouts is None else {layoutId(name) for name in layouts}
	sections = _sectionsInOrder(jkm, current)
	# The JAWS layout that decides each NVDA layout: the one in use, else the first one chosen.
	deciding: dict = {}
	for _section, layout in sections:
		if layout is not None and layout.id in wanted:
			deciding.setdefault(layout.nvdaLayout, layout)
	inUse = ({nvdaLayout} | set(deciding)) if nvdaLayout in NVDA_LAYOUTS else set(NVDA_LAYOUTS)
	capsLock = {name: bool(deciding[name].capsLock) if name in deciding else False for name in NVDA_LAYOUTS}

	records: list = []
	for section, layout in sections:
		if layout is not None:
			if layout.id not in wanted:
				for key, script in section.items():
					records.append(SkippedKey(key, script, section.name, f"only for the JAWS {layout.name} keyboard layout, which was not chosen", SKIP_LAYOUT))
				continue
			kind = layout.nvdaLayout
		else:
			kind = _sectionKind(section.name)
			if kind is None or kind in ("desktop", "laptop"):
				# Not keystrokes, or a layout section without any.
				continue
		for key, script in section.items():
			if leaseyActive and any(marker in (key + " " + script).lower() for marker in ("leasey", "hartgen")):
				records.append(SkippedKey(key, script, section.name, "belongs to Leasey", SKIP_LEASEY))
				continue
			passThrough = jawsKeyMap.isPassThroughBinding(key, script)
			gesture, reason = jawsKeyMap._convertKey(key, kind if kind in ("desktop", "laptop") else "common")
			if gesture is None:
				if passThrough:
					records.append(SkippedKey(key, script, section.name, "NVDA handles this Windows key itself", SKIP_PASSTHROUGH))
				else:
					records.append(SkippedKey(key, script, section.name, _UNCONVERTIBLE_REASONS.get(reason, reason or "not convertible"), SKIP_UNCONVERTIBLE))
				continue
			quickNav = kind == "browse" and jawsKeyMap.isQuickNavKey(key)
			targets = () if passThrough else jawsKeyMap.getNvdaTargets(script, key)
			if quickNav and targets and not quickNavLetters:
				records.append(SkippedKey(key, script, section.name, "JAWS quick navigation letters were not chosen", SKIP_QUICKNAV))
				continue
			prefix, main = gesture.split(":", 1)
			records.append(
				_Line(
					order=len(records),
					section=section,
					layout=layout,
					group="browse" if kind == "browse" else "normal",
					key=key,
					script=script,
					gesture=gesture,
					prefix=prefix,
					main=main,
					keys="+".join(sorted(part.lower() for part in main.split("+"))),
					tokens=frozenset(token.replace(" ", "").lower() for token in key.strip().rstrip("*").split("+")),
					passThrough=passThrough,
					quickNav=quickNav,
					targets=tuple(targets),
				),
			)

	# The keystroke that decides each key in each NVDA layout, even one NVDA has no equivalent for:
	# a lower one must not take its place.
	winners: dict = {}
	for line in records:
		if not isinstance(line, _Line):
			continue
		for name in line.nvdaLayouts:
			slot = (line.group, name, line.keys)
			best = winners.get(slot)
			if best is None or _rank(line, capsLock[name]) < _rank(best, capsLock[name]):
				winners[slot] = line

	claimed: dict = {}
	insertCandidates: list = []
	for record in records:
		if isinstance(record, SkippedKey):
			plan.skipped.append(record)
		else:
			_planLine(plan, record, winners, inUse, capsLock, deciding, boundScripts, scriptExists, overrideConflicts, claimed, insertCandidates)
	# Once every Caps Lock keystroke is planned, it is known what NVDA+key does for Caps Lock.
	planned: set = set()
	for line, name, winner in insertCandidates:
		_planInsertKey(plan, line, name, winner, boundScripts, scriptExists, overrideConflicts, planned)
	return plan


def _isInsertKeyCandidate(line: _Line, winner: _Line, capsLockLayout: bool, decidingLayout) -> bool:
	"""Whether ``line`` is an Insert keystroke that runs something else than the Caps Lock keystroke ``winner``.

	Only keystrokes JAWS has in the layout that decides the NVDA layout (the Laptop layout) count, or in
	its common sections: another chosen layout's keystrokes, such as Classic Laptop's, where Insert is the
	JAWS key, don't work in the Laptop layout.
	"""
	sameLayout = line.layout is None or decidingLayout is None or line.layout.id == decidingLayout.id
	return (
		capsLockLayout
		and sameLayout
		and line.usesNvdaKey
		and not line.capsLockKey(capsLockLayout)
		and winner.capsLockKey(capsLockLayout)
		and jawsKeyMap.normalizeScriptName(winner.script) != jawsKeyMap.normalizeScriptName(line.script)
	)


def _planInsertKey(plan, line, name, winner, boundScripts, scriptExists, overrideConflicts, planned) -> None:
	"""Plan the Insert version of a key whose NVDA gesture the Caps Lock keystroke ``winner`` has.

	What NVDA+key already runs for Caps Lock (JAWS's Caps Lock command, bound by this plan or an earlier
	migration, or NVDA's own command) stays; Insert gets the Insert keystroke's command, unless the
	user's own input gestures or another add-on use the keystroke, or it is NVDA's own and taking over
	NVDA's keystrokes wasn't asked for.
	"""

	def skip(reason: str, kind: str):
		plan.skipped.append(SkippedKey(line.key, line.script, line.section.name, reason, kind))

	slot = (line.group, name, line.keys)
	if slot in planned:
		# The same Insert keystroke written twice in the key map (Insert+h and Insert+H).
		return
	planned.add(slot)
	target = None
	for module, className, nvdaScript, description in line.targets:
		if scriptExists is None or scriptExists(module, className, nvdaScript):
			target = (module, className, nvdaScript, description)
			break
	if target is None:
		skip(f"this NVDA version has no {line.targets[0][2]} command", SKIP_NO_EQUIVALENT)
		return
	gesture = line.gesture if line.prefix == f"kb({name})" else f"kb({name}):{line.main}"
	entries = [entry for entry in _boundEntries(boundScripts, gesture) if entry.layout in (None, name)]
	unbound = {entry.location for entry in entries if entry.script is None}
	current = [entry for entry in entries if entry.script is not None and entry.location not in unbound]
	winnerTargets = {tuple(winnerTarget[:3]) for winnerTarget in winner.targets}

	def isJaws(entry) -> bool:
		return (entry.module, entry.className, entry.script) in winnerTargets

	plannedWinner = any(
		binding.jawsKey == winner.key and binding.section == winner.section.name and _identifierLayout(binding.gesture) in (None, name)
		for binding in plan.bindings
	)
	capsLockOwns = plannedWinner or any(isJaws(entry) for entry in current)
	users = [entry for entry in current if entry.source == "user" and not isJaws(entry)]
	if users:
		assigned = sorted({entry.script for entry in users})
		skip(f"your NVDA input gestures (gestures.ini) assign {', '.join(assigned)} to this keystroke, which Insert keeps running", SKIP_CONFLICT)
		return
	addons = [entry for entry in current if entry.source == "addon"]
	if addons:
		names = ", ".join(sorted({f"{_addonName(entry.module)} ({entry.script})" for entry in addons}))
		skip(f"the add-on {names} uses this keystroke, and NVDA may ask it first", SKIP_CONFLICT)
		return
	if not capsLockOwns and any((entry.module, entry.className, entry.script) == tuple(target[:3]) for entry in current):
		skip("NVDA already uses this keystroke for the same command", SKIP_SAME)
		return
	nvdaOwn = [] if capsLockOwns else [entry for entry in current if not isJaws(entry)]
	if nvdaOwn and not overrideConflicts:
		skip(_decisionText(_Decision("conflict", nvdaOwn)), SKIP_CONFLICT)
		return
	plan.insertKeys.append(
		InsertKey(
			gesture=gesture,
			module=target[0],
			className=target[1],
			script=target[2],
			description=target[3],
			jawsKey=line.key,
			jawsScript=line.script,
			section=line.section.name,
			capsLockKey=winner.key,
			capsLockScript=winner.script,
			replaces=sorted({entry.script for entry in nvdaOwn if entry.script}),
		),
	)


def describeGesture(gesture: str) -> str:
	"""An NVDA gesture as a person reads it: ``NVDA+j``, or ``NVDA+j, only in NVDA's laptop keyboard layout``."""
	prefix, _sep, main = str(gesture).partition(":")
	layout = _identifierLayout(gesture)
	if layout:
		return f"{main}, only in NVDA's {layout} keyboard layout"
	return main or str(gesture)


def _addonName(module: str) -> str:
	"""An add-on's plugin name from its module, such as ``goldenCursor`` for ``globalPlugins.goldenCursor``."""
	parts = str(module or "").split(".")
	return parts[1] if len(parts) > 1 and parts[0] == "globalPlugins" else str(module)


def _planLine(plan, line, winners, inUse, capsLock, deciding, boundScripts, scriptExists, overrideConflicts, claimed, insertCandidates=None) -> None:
	"""Add the bindings or the skipped entry for one keystroke."""

	def skip(reason: str, kind: str):
		plan.skipped.append(SkippedKey(line.key, line.script, line.section.name, reason, kind))

	if line.passThrough:
		skip("NVDA handles this Windows key itself", SKIP_PASSTHROUGH)
		return
	if not line.targets:
		skip("NVDA has no equivalent command", SKIP_NO_EQUIVALENT)
		return
	layouts = [name for name in line.nvdaLayouts if name in inUse]
	if not layouts:
		skip(f"only works in NVDA's {' and '.join(line.nvdaLayouts)} keyboard layout, which NVDA won't use", SKIP_LAYOUT)
		return
	won = [name for name in layouts if winners[(line.group, name, line.keys)] is line]
	if not won:
		name = layouts[0]
		winner = winners[(line.group, name, line.keys)]
		if insertCandidates is not None and _isInsertKeyCandidate(line, winner, capsLock[name], deciding.get(name)):
			# Decided once the Caps Lock keystrokes are planned (see _planInsertKey).
			insertCandidates.append((line, name, winner))
			return
		reason = _lostTo(line, winner, capsLock[name], deciding.get(name))
		if reason:
			skip(reason, SKIP_DUPLICATE)
		return
	entries = None
	for module, className, nvdaScript, description in line.targets:
		if scriptExists is not None and not scriptExists(module, className, nvdaScript):
			skip(f"this NVDA version has no {nvdaScript} command", SKIP_NO_EQUIVALENT)
			return
		if entries is None:
			entries = _boundEntries(boundScripts, line.gesture)
		target = (module, className, nvdaScript)
		overrideAllowed = overrideConflicts or line.quickNav
		decisions = {name: _decide(target, entries, name, overrideAllowed) for name in won}
		binds = [name for name in NVDA_LAYOUTS if name in decisions and decisions[name].kind == "bind"]
		if binds and line.prefix == "kb":
			# Keep a kb: gesture where the NVDA layout that won't be used would get just the same binding.
			for name in NVDA_LAYOUTS:
				other = winners.get((line.group, name, line.keys))
				if name in inUse or other is None:
					continue
				if other is not line and jawsKeyMap.normalizeScriptName(other.script) != jawsKeyMap.normalizeScriptName(line.script):
					continue
				decision = _decide(target, entries, name, overrideAllowed)
				if decision.kind == "bind" and all(_sameBinding(decision, decisions[bound]) for bound in binds):
					decisions[name] = decision
					binds = [layout for layout in NVDA_LAYOUTS if layout in binds or layout == name]
		if line.prefix == "kb" and len(binds) == len(NVDA_LAYOUTS):
			gestures = [(line.gesture, binds)]
		else:
			gestures = [(line.gesture if line.prefix == f"kb({name})" else f"kb({name}):{line.main}", [name]) for name in binds]
		for gesture, names in gestures:
			slot = (module, className, line.keys)
			taken = [claimed[slot][name] for name in names if name in claimed.get(slot, {})]
			if taken:
				first = taken[0]
				if jawsKeyMap.normalizeScriptName(first.jawsScript) != jawsKeyMap.normalizeScriptName(line.script):
					skip(f"{first.section} already uses this keystroke for {first.jawsScript}", SKIP_DUPLICATE)
				continue
			others = [entry for name in names for entry in decisions[name].others]
			binding = GestureBinding(
				gesture=gesture,
				module=module,
				className=className,
				script=nvdaScript,
				description=description,
				jawsKey=line.key,
				jawsScript=line.script,
				section=line.section.name,
				replaces=sorted({entry.script for entry in others if entry.script}),
				unbind=sorted({location for name in names for location in decisions[name].unbind}),
			)
			plan.bindings.append(binding)
			for name in names:
				claimed.setdefault(slot, {})[name] = binding
		kept = [name for name in won if decisions[name].kind in ("conflict", "blocked")]
		if kept:
			skip(_keptReason(decisions, kept, qualify=len(kept) < len(layouts)), SKIP_CONFLICT)
		elif not binds:
			skip("NVDA already uses this keystroke for the same command", SKIP_SAME)


def applicationKeyMaps(files: list) -> dict:
	"""``{key map name: [(key, script), ...]}`` for application key maps, for the report."""
	result = {}
	for indexed in files:
		if indexed.name.lower() == "default.jkm":
			continue
		try:
			ini = jawsFiles.readIni(indexed.path)
		except OSError:
			continue
		entries = []
		for section in ini.sections.values():
			if _sectionKind(section.name) is None:
				continue
			entries.extend(section.items())
		if entries:
			result[indexed.relative] = entries
	return result


def describeJawsKeystroke(gesture, jawsBindings: dict) -> list:
	"""JAWS bindings matching an NVDA gesture's identifiers: ``[(jawsKey, script, section), ...]``."""
	found = []
	for identifier in getattr(gesture, "normalizedIdentifiers", ()) or ():
		for entry in jawsBindings.get(identifier.lower(), ()):
			if entry not in found:
				found.append(entry)
	return found


def buildReverseMap(jkm: jawsFiles.IniFile, keyboardLayout: str, layouts=None) -> dict:
	"""``{normalized NVDA gesture: [(jawsKey, script, section)]}`` for every convertible JAWS keystroke.

	``layouts`` are the JAWS keyboard layouts to include besides the common keys; None takes the one in use.
	A layout's own keystrokes come first, the layout in use first, because they replace the common ones.
	"""
	result: dict = {}
	current = layoutId(keyboardLayout)
	wanted = {current} if layouts is None else {layoutId(name) for name in layouts} | {current}
	sections = _sectionsInOrder(jkm, current)
	for section, layout in [pair for pair in sections if pair[1] is not None] + [pair for pair in sections if pair[1] is None]:
		if layout is not None:
			if layout.id not in wanted:
				continue
			kind = layout.nvdaLayout
		else:
			kind = _sectionKind(section.name)
			if kind is None or kind in ("desktop", "laptop"):
				continue
		for key, script in section.items():
			gesture, _reason = jawsKeyMap._convertKey(key, kind if kind in ("desktop", "laptop") else "common")
			if gesture is None:
				continue
			for variant in _gestureVariants(gesture):
				result.setdefault(variant, [])
				entry = (key, script, section.name)
				if entry not in result[variant]:
					result[variant].append(entry)
	return result


def _gestureVariants(gesture: str) -> list[str]:
	"""Normalized identifiers a key press can produce: with the layout prefix and without."""
	prefix, main = gesture.split(":", 1)
	parts = sorted(part.lower() for part in main.split("+"))
	normalizedMain = "+".join(parts)
	variants = {f"{prefix.lower()}:{normalizedMain}"}
	if prefix.lower() != "kb":
		variants.add(f"kb:{normalizedMain}")
	return sorted(variants)
