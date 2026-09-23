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
Keystrokes NVDA already uses for the same command are left alone. A keystroke
NVDA uses for something else is only taken over when asked, and quick
navigation letters only when the JAWS letters are wanted in browse mode.

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
class KeyPlan:
	bindings: list = field(default_factory=list)
	skipped: list = field(default_factory=list)
	applicationKeys: dict = field(default_factory=dict)

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


def planKeys(
	jkm: jawsFiles.IniFile,
	keyboardLayout: str,
	boundScripts=None,
	scriptExists=None,
	quickNavLetters: bool = True,
	overrideConflicts: bool = False,
	leaseyActive: bool = False,
	layouts=None,
) -> KeyPlan:
	"""Work out which JAWS keystrokes become NVDA gestures.

	``keyboardLayout`` is the JAWS keyboard layout in use (``desktop``, ``laptop``,
	``classic laptop``...). ``layouts`` lists the JAWS layouts whose own keystrokes are wanted;
	None takes just the one in use. ``boundScripts(gesture)`` returns ``(module, class, script)``
	tuples NVDA already binds to a gesture; ``scriptExists(module, class, script)`` confirms a
	target is present in this NVDA. Both may be None outside NVDA.
	"""
	plan = KeyPlan()
	seenGestures: dict = {}
	current = layoutId(keyboardLayout)
	wanted = {current} if layouts is None else {layoutId(name) for name in layouts}
	for section, layout in _sectionsInOrder(jkm, current):
		if layout is not None:
			if layout.id not in wanted:
				for key, script in section.items():
					plan.skipped.append(SkippedKey(key, script, section.name, f"only for the JAWS {layout.name} keyboard layout, which was not chosen", SKIP_LAYOUT))
				continue
			kind = layout.nvdaLayout
		else:
			kind = _sectionKind(section.name)
			if kind is None or kind in ("desktop", "laptop"):
				# Not keystrokes, or a layout section without any.
				continue
		for key, script in section.items():
			if leaseyActive and any(marker in (key + " " + script).lower() for marker in ("leasey", "hartgen")):
				plan.skipped.append(SkippedKey(key, script, section.name, "belongs to Leasey", SKIP_LEASEY))
				continue
			if jawsKeyMap.isPassThroughBinding(key, script):
				plan.skipped.append(SkippedKey(key, script, section.name, "NVDA handles this Windows key itself", SKIP_PASSTHROUGH))
				continue
			gesture, reason = jawsKeyMap._convertKey(key, kind if kind in ("desktop", "laptop") else "common")
			if gesture is None:
				plan.skipped.append(SkippedKey(key, script, section.name, _UNCONVERTIBLE_REASONS.get(reason, reason or "not convertible"), SKIP_UNCONVERTIBLE))
				continue
			targets = jawsKeyMap.getNvdaTargets(script)
			if not targets:
				plan.skipped.append(SkippedKey(key, script, section.name, "NVDA has no equivalent command", SKIP_NO_EQUIVALENT))
				continue
			if kind == "browse" and not quickNavLetters:
				plan.skipped.append(SkippedKey(key, script, section.name, "JAWS quick navigation letters were not chosen", SKIP_QUICKNAV))
				continue
			for module, className, nvdaScript, description in targets:
				if scriptExists is not None and not scriptExists(module, className, nvdaScript):
					plan.skipped.append(SkippedKey(key, script, section.name, f"this NVDA version has no {nvdaScript} command", SKIP_NO_EQUIVALENT))
					break
				normalized = gesture.lower()
				existing = list(boundScripts(gesture)) if boundScripts is not None else []
				if any(entry[0] == module and entry[1] == className and entry[2] == nvdaScript for entry in existing):
					plan.skipped.append(SkippedKey(key, script, section.name, "NVDA already uses this keystroke for the same command", SKIP_SAME))
					break
				others = [entry for entry in existing if entry[2]]
				if others and not overrideConflicts and kind != "browse":
					names = ", ".join(sorted({entry[2] for entry in others}))
					plan.skipped.append(SkippedKey(key, script, section.name, f"NVDA already uses this keystroke for {names}", SKIP_CONFLICT))
					break
				bindingKey = (normalized, module, className)
				if bindingKey in seenGestures:
					first = seenGestures[bindingKey]
					if layout is not None and first.section.lower() != section.name.lower():
						plan.skipped.append(SkippedKey(key, script, section.name, f"{first.section} already uses this keystroke for {first.jawsScript}", SKIP_DUPLICATE))
					break
				binding = GestureBinding(
					gesture=gesture,
					module=module,
					className=className,
					script=nvdaScript,
					description=description,
					jawsKey=key,
					jawsScript=script,
					section=section.name,
					replaces=sorted({entry[2] for entry in others}),
				)
				seenGestures[bindingKey] = binding
				plan.bindings.append(binding)
	return plan


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
	"""
	result: dict = {}
	current = layoutId(keyboardLayout)
	wanted = {current} if layouts is None else {layoutId(name) for name in layouts} | {current}
	for section, layout in _sectionsInOrder(jkm, current):
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
