# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""A one-time repair of the input gestures versions 1.0 to 1.2 wrote into NVDA's gestures.ini.

Those versions wrote three kinds of keystroke that version 1.3 no longer writes:

- Keystrokes for NVDA's editable text caret scripts (``caret_nextSentence`` and
  ``caret_previousSentence`` of ``editableText.EditableText``). Those scripts first send the
  pressed keystroke on to the program, so in an edit field Caps Lock+Y turned Caps Lock on and
  typed "Y" (see ``jawsKeyMap.sendsKeystroke``).
- JAWS virtual cursor keystrokes that took an NVDA command's keystroke in browse mode without
  asking: NVDA+Control+R no longer reverted the configuration, NVDA+Control+B no longer opened
  the browse mode settings and NVDA+F5 no longer refreshed the document. Quick navigation
  letters were asked for, and stay.
- With the JAWS Laptop layout, where Caps Lock is the JAWS key, keystrokes whose Caps Lock
  version does something else in JAWS: NVDA+H and NVDA+J opened the Input Gestures dialog and
  the NVDA menu where JAWS says the sentence and the previous word.

A keystroke that is wrong in only one of NVDA's keyboard layouts keeps working in the other: its
``kb:`` gesture becomes ``kb(desktop):`` or ``kb(laptop):``, as version 1.3 writes it. The others
are removed.

Only bindings the assistant wrote are touched (see ``isAssistants``). A binding counts as the
assistant's when its command is one the assistant binds JAWS keystrokes to, it is not in the copy
of gestures.ini kept before the first migration that added keystrokes (the user's own bindings),
and one of these shows the assistant wrote it:

- a migration's report lists its keystroke among those the migration added;
- the migrations kept copies of gestures.ini, and it is in none of them;
- it is bound to one of the editable text caret scripts above: NVDA's Input Gestures dialog
  doesn't offer them, so only the assistant bound keystrokes to them.

Everything else in gestures.ini, the user's own bindings included, stays exactly as it is. NVDA's
settings are backed up before the repair (see repairOnce).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from . import jawsKeyMap, keyPlan, nvdaEnv, safety

#: Bumped when a new repair is needed; kept in state.json as "gesturesRepaired".
REPAIR_VERSION = 1
STATE_KEY = "gesturesRepaired"
GESTURES_FILE = "gestures.ini"
#: What each migration kept of gestures.ini before adding keystrokes, in the migration's folder.
COPY_NAME = "gestures.ini.before-migration"
REPORT_NAME = "report.txt"
#: Commands versions 1.0 to 1.2 bound that today's maps no longer have: they send the keystroke on.
OLD_TARGETS = frozenset(
	{
		("editableText", "EditableText", "caret_nextSentence"),
		("editableText", "EditableText", "caret_previousSentence"),
	},
)
#: NVDA's own gestures for those scripts; the assistant never wrote them.
NVDA_SENTENCE_GESTURES = frozenset({"kb:alt+downarrow", "kb:alt+uparrow"})
#: What Caps Lock+key runs in JAWS 2026's Laptop layout, for the keys where versions 1.0 to 1.2 bound
#: NVDA+key to something else. Used when JAWS's own key map can no longer be read.
STOCK_CAPS_LOCK_KEYS = {
	"h+nvda": ("JAWSKey+H", "SaySentence"),
	"j+nvda": ("JAWSKey+J", "SayPriorWord"),
	"8+nvda": ("JAWSKey+8", "LeftMouseButton"),
}
_MODIFIERS = frozenset({"nvda", "control", "alt", "shift", "windows"})
#: Modules of NVDA's browse mode commands. Versions 1.0 to 1.2 bound JAWS's virtual cursor
#: keystrokes to them even over an NVDA command's keystroke, without asking; other keystrokes
#: only took an NVDA command's keystroke when the user asked for the JAWS commands instead.
_BROWSE_MODULES = frozenset({"browseMode", "virtualBuffers"})
#: Browse mode commands that JAWS's keyboard layouts bind too (Caps Lock+Control+O in the Laptop
#: layout), not only its virtual cursor keys. Without JAWS's key map to tell which keystroke a
#: binding came from, taking an NVDA command's keystroke for them may have been asked for.
_LAYOUT_BROWSE_SCRIPTS = frozenset({"nextTextParagraph", "previousTextParagraph"})


# -- gestures.ini ----------------------------------------------------------------------------


def normalizeGesture(identifier: str) -> str:
	"""A gesture identifier as NVDA normalizes it: lower case, its keys sorted."""
	prefix, _sep, main = identifier.strip().lower().partition(":")
	return f"{prefix}:{'+'.join(sorted(main.split('+')))}"


def _gestureLayouts(gesture: str) -> tuple:
	"""The NVDA keyboard layouts a keyboard gesture works in."""
	layout = keyPlan._identifierLayout(gesture)
	return (layout,) if layout in keyPlan.NVDA_LAYOUTS else keyPlan.NVDA_LAYOUTS


def _splitValue(value: str) -> tuple[list, str]:
	"""The items of a configobj value as ``[(as written, text)]``, and its trailing ``# comment``."""
	items = []
	current: list = []
	quote = None
	comment = ""
	for index, char in enumerate(value):
		if quote:
			current.append(char)
			if char == quote:
				quote = None
		elif char in "\"'" and not "".join(current).strip():
			quote = char
			current.append(char)
		elif char == "#":
			comment = value[index:]
			break
		elif char == ",":
			items.append("".join(current))
			current = []
		else:
			current.append(char)
	items.append("".join(current))
	result = []
	for item in items:
		written = item.strip()
		if not written:
			continue
		quoted = len(written) >= 2 and written[0] == written[-1] and written[0] in "\"'"
		result.append((written, written[1:-1] if quoted else written))
	return result, comment.strip()


def _written(gesture: str, like: str) -> str:
	"""``gesture`` written as configobj reads it back, quoted the way ``like`` was."""
	if like[:1] in ("'", '"'):
		quote = like[0]
	elif any(char in gesture for char in ",#'\""):
		quote = "'" if '"' in gesture else '"'
	else:
		return gesture
	return f"{quote}{gesture}{quote}"


@dataclass
class _Entry:
	"""A ``script = gestures`` line of gestures.ini."""

	index: int
	module: str
	className: str
	script: str
	#: The line up to its value, as written.
	head: str
	items: list
	comment: str
	ending: str


def parseGestures(text: str) -> tuple[list, list]:
	"""The lines of a gestures.ini, line ends kept, and its ``script = gestures`` lines as ``_Entry``."""
	lines = text.splitlines(keepends=True)
	entries = []
	module = className = ""
	for index, raw in enumerate(lines):
		line = raw.rstrip("\r\n")
		stripped = line.strip()
		if not stripped or stripped.startswith("#"):
			continue
		if stripped.startswith("[") and stripped.endswith("]"):
			module, _sep, className = stripped.strip("[]").strip().rpartition(".")
			continue
		if not module or "=" not in line:
			continue
		separator = line.index("=")
		after = line[separator + 1 :]
		start = separator + 1 + len(after) - len(after.lstrip())
		items, comment = _splitValue(line[start:])
		script = line[:separator].strip().strip("\"'")
		entries.append(_Entry(index, module, className, script, line[:start], items, comment, raw[len(line) :]))
	return lines, entries


def bindingsOf(text: str) -> set:
	"""``{(gesture, module, class, script)}`` of a gestures.ini, gestures normalized."""
	_lines, entries = parseGestures(text)
	return {(normalizeGesture(value), entry.module, entry.className, entry.script) for entry in entries for _written, value in entry.items}


def _readText(path: str) -> str | None:
	try:
		with open(path, "rb") as stream:
			return stream.read().decode("utf-8-sig", errors="replace")
	except OSError:
		return None


# -- what the assistant wrote ---------------------------------------------------------------


@dataclass
class Evidence:
	"""What the migrations' folders and state.json show about the keystrokes the assistant added."""

	#: Normalized gestures the migration reports list among the keystrokes they added.
	reported: set = field(default_factory=set)
	#: The JAWS keystroke each reported gesture came from.
	jawsKeys: dict = field(default_factory=dict)
	#: The bindings of each copy of gestures.ini the migrations kept, oldest first.
	copies: list = field(default_factory=list)
	#: The bindings the user had before the first migration that added keystrokes.
	userBefore: set = field(default_factory=set)
	#: JAWS keyboard layout ids the migrations brought keystrokes over from ("laptop").
	layouts: set = field(default_factory=set)


_REPORT_HEADING = "=== Keyboard Manager and Navigation Quick Keys"
_REPORT_COUNT = re.compile(r"^(\d+) JAWS keystrokes became NVDA input gestures")
# The gesture is the last bracketed part; it can itself hold a bracket key (kb(laptop):NVDA+[).
_REPORT_ITEM = re.compile(r"^\s+- (?P<label>.+?) \[(?P<gesture>kb(?:\([a-z]+\))?:.+)\]\s*$")
_REPORT_LAYOUTS = re.compile(r"Keystrokes brought over from: (?P<names>.+?)\.?\s*$")


def readReport(text: str) -> tuple:
	"""``(count, [(jawsKey, gesture)], layout names)`` from a migration's report.txt.

	``count`` is how many keystrokes the migration added, or None when the report doesn't say. The
	listed keystrokes are the ones the migration planned; they were added when ``count`` isn't 0.
	"""
	count = None
	listed = []
	names = set()
	inKeyboard = inList = False
	for line in text.splitlines():
		if line.startswith("=== "):
			inKeyboard = inList = line.strip() == _REPORT_HEADING
			continue
		if not inKeyboard:
			continue
		if line.startswith("--- "):
			inList = False
			continue
		match = _REPORT_COUNT.match(line)
		if match:
			count = int(match.group(1))
			continue
		match = _REPORT_LAYOUTS.search(line)
		if match:
			names.update(name.strip() for name in match.group("names").split(",") if name.strip() not in ("", "none"))
			continue
		match = _REPORT_ITEM.match(line) if inList else None
		if match:
			listed.append((match.group("label").split(": ", 1)[0], match.group("gesture")))
	return count, listed, names


def _readState(configDir: str) -> dict:
	try:
		with open(os.path.join(configDir, nvdaEnv.ADDON_FOLDER_NAME, "state.json"), encoding="utf-8") as stream:
			data = json.load(stream)
		return data if isinstance(data, dict) else {}
	except (OSError, ValueError):
		return {}


def gatherEvidence(configDir: str) -> Evidence:
	"""Read every migration folder, oldest first, and state.json in NVDA's settings folder ``configDir``."""
	evidence = Evidence()
	root = os.path.join(configDir, nvdaEnv.ADDON_FOLDER_NAME, "migrations")
	try:
		folders = sorted(name for name in os.listdir(root) if os.path.isdir(os.path.join(root, name)))
	except OSError:
		folders = []
	firstWriter = None
	for name in folders:
		folder = os.path.join(root, name)
		copyText = _readText(os.path.join(folder, COPY_NAME))
		copy = bindingsOf(copyText) if copyText is not None else None
		if copy is not None:
			evidence.copies.append(copy)
		reportText = _readText(os.path.join(folder, REPORT_NAME))
		count = None
		if reportText is not None:
			count, listed, names = readReport(reportText)
			if count:
				for jawsKey, gesture in listed:
					normalized = normalizeGesture(gesture)
					evidence.reported.add(normalized)
					evidence.jawsKeys.setdefault(normalized, jawsKey)
				evidence.layouts.update(keyPlan.layoutId(layoutName) for layoutName in names)
		# A migration keeps its copy just before adding keystrokes, when gestures.ini exists.
		wroteKeys = bool(count) if count is not None else copy is not None
		if wroteKeys and firstWriter is None:
			firstWriter = copy if copy is not None else set()
	if firstWriter is not None:
		evidence.userBefore = firstWriter
	elif evidence.copies:
		evidence.userBefore = evidence.copies[0]
	lastMigration = _readState(configDir).get("lastMigration")
	if isinstance(lastMigration, dict):
		evidence.layouts.update(str(layout) for layout in lastMigration.get("keyboardLayouts") or () if layout)
	return evidence


def assistantTargets() -> frozenset:
	"""Every ``(module, class, script)`` any version of the assistant binds JAWS keystrokes to."""
	targets = set(OLD_TARGETS)
	for table in (jawsKeyMap.SCRIPT_MAP, jawsKeyMap.QUICK_NAV_MAP, jawsKeyMap.COMMAND_KEY_TARGETS):
		targets.update(target[:3] for target in table.values())
	for extra in jawsKeyMap.ADDITIONAL_TARGETS.values():
		targets.update(target[:3] for target in extra)
	return frozenset(targets)


def isAssistants(binding: tuple, evidence: Evidence) -> bool:
	"""Whether the assistant wrote a gestures.ini binding ``(gesture, module, class, script)``."""
	gesture, module, className, script = binding
	if (module, className, script) not in assistantTargets() or binding in evidence.userBefore:
		return False
	if gesture in evidence.reported:
		return True
	if evidence.copies and not any(binding in copy for copy in evidence.copies):
		return True
	return (module, className, script) in OLD_TARGETS and gesture not in NVDA_SENTENCE_GESTURES


# -- what version 1.3 would not write ---------------------------------------------------------


def capsLockKeystrokes(jkm, layouts=None) -> dict:
	"""``{keys: (jawsKey, script)}``: what Caps Lock+key runs where Caps Lock is the JAWS key.

	``keys`` are the NVDA gesture's, normalized (``h+nvda``). The layout's own keystroke comes before
	the common one, as in JAWS. ``layouts`` limits the JAWS layouts to those ids. Empty when the key
	map has no such layout.
	"""
	chosen = [layout for layout in keyPlan.keyboardLayouts(jkm) if layout.capsLock and (not layouts or layout.id in layouts)]
	if not chosen:
		return {}
	sections = [(jkm.section(layout.section), "laptop") for layout in chosen]
	sections += [(section, "common") for section in jkm.sections.values() if keyPlan._sectionKind(section.name) == "common"]
	result: dict = {}
	for section, kind in sections:
		if section is None:
			continue
		for key, script in section.items():
			tokens = {token.replace(" ", "").lower() for token in key.strip().rstrip("*").split("+")}
			if not tokens & {"jawskey", "capslock"}:
				continue
			gesture = jawsKeyMap.jawsKeyToNvdaGesture(key, kind)
			if gesture is not None:
				result.setdefault(normalizeGesture(gesture).split(":", 1)[1], (key, script))
	return result


def _readJawsKeyMap(configDir: str):
	"""JAWS's default key map with the user's changes over it, or None when JAWS can't be read. Only reads."""
	try:
		from . import jawsDetect, jawsFiles

		installations = list(jawsDetect.findJawsInstallations())
	except Exception:
		return None
	lastMigration = _readState(configDir).get("lastMigration")
	migrated = str(lastMigration.get("jaws") or "") if isinstance(lastMigration, dict) else ""
	installations.sort(key=lambda jaws: (jaws.displayName != migrated, not jaws.programInstalled))
	for jaws in installations:
		language = jaws.primaryLanguage or "enu"
		files = []
		for path in (os.path.join(jaws.sharedScriptsLanguageDir(language), "Default.jkm"), os.path.join(jaws.userLanguageDir(language), "Default.jkm")):
			if os.path.isfile(path):
				try:
					files.append(jawsFiles.readIni(path))
				except OSError:
					pass
		if files:
			return jawsFiles.mergeIni(*files)
	return None


class KeyMap:
	"""JAWS's key map for the repair, read only when first needed.

	``source`` is a parsed key map, None for none, or a function that reads one (or returns None).
	"""

	def __init__(self, source=None, layouts=None):
		self._source = source
		self._jkm = None
		self._read = False
		self._layouts = set(layouts or ())
		self._capsLockKeys: dict | None = None

	@property
	def jkm(self):
		if not self._read:
			self._read = True
			source = self._source
			try:
				self._jkm = source() if callable(source) else source
			except Exception:
				self._jkm = None
		return self._jkm

	def capsLockKeys(self) -> dict:
		"""What Caps Lock+key runs in the JAWS Laptop layout (see capsLockKeystrokes); JAWS 2026's without a key map."""
		if self._capsLockKeys is None:
			keys = {}
			if self.jkm is not None:
				keys = capsLockKeystrokes(self.jkm, self._layouts or None) or capsLockKeystrokes(self.jkm)
			self._capsLockKeys = keys or dict(STOCK_CAPS_LOCK_KEYS)
		return self._capsLockKeys

	def origin(self, jawsKey: str, target: tuple) -> str | None:
		"""``browse`` when only JAWS's virtual cursor sections bind ``jawsKey`` to a script for ``target``,
		``normal`` when another section does, None when the key map doesn't tell."""
		jkm = self.jkm
		if jkm is None or not jawsKey:
			return None
		layoutSections = {layout.section.lower() for layout in keyPlan.keyboardLayouts(jkm)}
		kinds = set()
		for section in jkm.sections.values():
			kind = keyPlan._sectionKind(section.name)
			if kind is None and section.name.lower() not in layoutSections:
				continue
			script = section.get(jawsKey)
			if script is None:
				continue
			# Versions 1.0 to 1.2 looked scripts up without the keystroke.
			targets = {found[:3] for found in jawsKeyMap.getNvdaTargets(script) + jawsKeyMap.getNvdaTargets(script, jawsKey)}
			if tuple(target) in targets:
				kinds.add("browse" if kind == "browse" else "normal")
		if "normal" in kinds:
			return "normal"
		return "browse" if kinds else None


def _isQuickNavKeys(parts: list) -> bool:
	keys = [part for part in parts if part not in _MODIFIERS]
	return len(keys) == 1 and len(keys[0]) == 1 and all(part == "shift" for part in parts if part in _MODIFIERS)


def _takenCommands(binding: tuple, boundScripts, assistant: set) -> dict:
	"""``{NVDA layout: [scripts]}``: the commands NVDA or the user bind to a binding's keys, besides its own."""
	gesture, module, className, script = binding
	taken: dict = {}
	if boundScripts is None:
		return taken
	try:
		entries = [tuple(entry) for entry in boundScripts(gesture)]
	except Exception:
		return taken
	others = []
	for entry in entries:
		if len(entry) < 3:
			continue
		identifier = entry[3] if len(entry) > 3 else gesture
		source = entry[4] if len(entry) > 4 else "class"
		if source == "user" and (normalizeGesture(identifier), entry[0], entry[1], entry[2]) in assistant:
			continue
		others.append((entry[0], entry[1], entry[2], keyPlan._identifierLayout(identifier), source))
	for layout in _gestureLayouts(gesture):
		here = [entry for entry in others if entry[3] in (None, layout)]
		unbound = {(entry[0], entry[1]) for entry in here if entry[2] is None and entry[4] != "class"}
		names = sorted(
			{
				entry[2]
				for entry in here
				if entry[2] and (entry[0], entry[1]) not in unbound and entry[:3] != (module, className, script)
			},
		)
		if names:
			taken[layout] = names
	return taken


@dataclass
class Change:
	"""A binding the repair removes, or keeps for one NVDA keyboard layout only."""

	line: int
	item: int
	gesture: str
	module: str
	className: str
	script: str
	#: The gesture it becomes, or None when it is removed.
	newGesture: str | None
	reason: str

	def describe(self) -> str:
		what = f"{self.gesture} for {self.module}.{self.className}.{self.script}"
		if self.newGesture is None:
			return f"removed {what}: {self.reason}"
		return f"kept {what} only as {self.newGesture}: {self.reason}"


def planRepair(text: str, evidence: Evidence, boundScripts=None, keyMap=None) -> list:
	"""The changes the repair makes to the text of a gestures.ini, as ``Change`` items.

	``boundScripts`` is ``nvdaApply.gestureBoundScripts`` or a stand-in; None finds no taken commands.
	``keyMap`` is JAWS's key map: a ``KeyMap``, a parsed key map, a function that reads one, or None.
	"""
	if not isinstance(keyMap, KeyMap):
		keyMap = KeyMap(keyMap, evidence.layouts)
	_lines, entries = parseGestures(text)
	items = [(entry, position, normalizeGesture(value)) for entry in entries for position, (_written, value) in enumerate(entry.items)]
	present = {(gesture, entry.module, entry.className, entry.script) for entry, _position, gesture in items}
	assistant = {binding for binding in present if isAssistants(binding, evidence)}
	capsLockLaptop = "laptop" in evidence.layouts or any(
		gesture.startswith("kb(laptop):") and "nvda" in gesture.split(":", 1)[1].split("+") for gesture, *_target in assistant
	)
	changes = []
	for entry, position, gesture in items:
		binding = (gesture, entry.module, entry.className, entry.script)
		if binding not in assistant or not gesture.startswith("kb"):
			continue
		target = binding[1:]
		layouts = _gestureLayouts(gesture)
		keys = gesture.split(":", 1)[1]
		parts = keys.split("+")
		wrong: dict = {}
		if jawsKeyMap.sendsKeystroke(*target):
			for layout in layouts:
				wrong[layout] = "its command sends the keystroke on to the program, so a Caps Lock keystroke turned Caps Lock on and typed a letter"
		else:
			if entry.module in _BROWSE_MODULES and not _isQuickNavKeys(parts):
				taken = _takenCommands(binding, boundScripts, assistant)
				if taken:
					origin = keyMap.origin(evidence.jawsKeys.get(gesture, ""), target)
					if origin == "browse" or (origin is None and entry.script not in _LAYOUT_BROWSE_SCRIPTS):
						for layout, names in taken.items():
							wrong.setdefault(layout, f"it took this keystroke from NVDA's {', '.join(names)} in browse mode without asking")
			if capsLockLaptop and "laptop" in layouts and "nvda" in parts and entry.module not in _BROWSE_MODULES:
				meaning = keyMap.capsLockKeys().get(keys)
				if meaning is not None and target not in {found[:3] for found in jawsKeyMap.getNvdaTargets(meaning[1], meaning[0])}:
					wrong.setdefault("laptop", f"in the JAWS Laptop layout, where Caps Lock is the JAWS key, {meaning[0]} runs {meaning[1]}")
		if not wrong:
			continue
		keep = [layout for layout in layouts if layout not in wrong]
		newGesture = f"kb({keep[0]}):{keys}" if keep else None
		if newGesture is not None and (newGesture, *target) in present:
			# The gesture for that layout alone is there already.
			newGesture = None
		reason = "; ".join(dict.fromkeys(wrong.values()))
		changes.append(Change(entry.index, position, gesture, entry.module, entry.className, entry.script, newGesture, reason))
	return changes


def applyChanges(text: str, changes: list) -> str:
	"""``text`` with ``changes`` made. Lines left without gestures go, and so do section headers left empty."""
	lines, entries = parseGestures(text)
	byLine: dict = {}
	for change in changes:
		byLine.setdefault(change.line, {})[change.item] = change
	emptied = set()
	for entry in entries:
		changed = byLine.get(entry.index)
		if not changed:
			continue
		kept = []
		for position, (written, _value) in enumerate(entry.items):
			change = changed.get(position)
			if change is None:
				kept.append(written)
			elif change.newGesture is not None:
				kept.append(_written(change.newGesture, written))
		if kept:
			lines[entry.index] = entry.head + ", ".join(kept) + (" " + entry.comment if entry.comment else "") + entry.ending
		else:
			emptied.add(entry.index)
	# A section header goes when every line under it went.
	header = None
	sectionLines: list = []
	dropped = set(emptied)
	for index in range(len(lines) + 1):
		line = lines[index].strip() if index < len(lines) else "["
		if line.startswith("[") and line.endswith("]") or index == len(lines):
			if header is not None and sectionLines and all(number in emptied for number in sectionLines):
				dropped.add(header)
			header, sectionLines = index, []
		elif line:
			sectionLines.append(index)
	return "".join(line for index, line in enumerate(lines) if index not in dropped)


# -- the repair -----------------------------------------------------------------------------


@dataclass
class GestureRepairResult:
	path: str = ""
	changes: list = field(default_factory=list)
	failed: list = field(default_factory=list)


def _plan(configDir: str, boundScripts=None, keyMap=None):
	"""``(path, file bytes, text, changes)`` for NVDA's gestures.ini. Raises OSError or UnicodeDecodeError."""
	if boundScripts is None:
		from . import nvdaApply

		boundScripts = nvdaApply.gestureBoundScripts
	path = os.path.join(configDir, GESTURES_FILE)
	with open(path, "rb") as stream:
		data = stream.read()
	text = data.decode("utf-8-sig")
	evidence = gatherEvidence(configDir)
	source = keyMap if keyMap is not None else (lambda: _readJawsKeyMap(configDir))
	return path, data, text, planRepair(text, evidence, boundScripts, KeyMap(source, evidence.layouts))


def needsRepair(configDir: str, boundScripts=None, keyMap=None) -> bool | None:
	"""Whether gestures.ini has keystrokes to repair; None when it can't be read (tried again later)."""
	try:
		return bool(_plan(configDir, boundScripts, keyMap)[3])
	except FileNotFoundError:
		return False
	except (OSError, UnicodeDecodeError):
		return None


def repairGestures(configDir: str, log=None, boundScripts=None, keyMap=None) -> GestureRepairResult:
	"""Repair the assistant's wrong keystrokes in NVDA's gestures.ini in ``configDir``. Writes it only when it changes.

	``boundScripts`` finds what NVDA binds to a gesture (``nvdaApply.gestureBoundScripts`` when None);
	``keyMap`` is JAWS's key map (read from JAWS when None and needed).
	"""
	say = log or (lambda message: None)
	result = GestureRepairResult(os.path.join(configDir, GESTURES_FILE))
	try:
		path, data, text, changes = _plan(configDir, boundScripts, keyMap)
	except FileNotFoundError:
		return result
	except (OSError, UnicodeDecodeError) as error:
		# A file that can't be read exactly is never rewritten.
		result.failed.append(f"{result.path}: {error}")
		say(f"could not read {result.path}: {error}")
		return result
	if not changes:
		return result
	repaired = applyChanges(text, changes)
	try:
		safety.checkWritable(path)
		temporary = path + ".jawsMigrator.tmp"
		with open(temporary, "wb") as stream:
			stream.write((b"\xef\xbb\xbf" if data.startswith(b"\xef\xbb\xbf") else b"") + repaired.encode("utf-8"))
		os.replace(temporary, path)
	except OSError as error:
		result.failed.append(f"{path}: {error}")
		say(f"could not repair {path}: {error}")
		return result
	result.changes = changes
	for change in changes:
		say(change.describe())
	return result


def reloadUserGestures() -> None:
	"""Have NVDA read gestures.ini again, as it does when it reverts to its saved configuration."""
	try:
		import inputCore

		inputCore.manager.loadUserGestureMap()
	except Exception:
		from . import debugLog

		debugLog.error("NVDA could not read its input gestures again")


def repairOnce(announce, done=None) -> None:
	"""Once, after updating from versions 1.0 to 1.2: repair their keystrokes, after a backup.

	Main thread; the backup runs in the background. ``announce(message)`` tells the user, and
	``done()`` is called on the main thread when the repair is over, whether or not it did anything.
	"""
	from . import migrator

	finished = migrator.callOnce(done)
	started = False
	try:
		started = _startRepair(announce, finished)
	finally:
		if not started:
			finished()


def _startRepair(announce, finished) -> bool:
	"""Start the repair; True when a backup started in the background, which calls ``finished`` at its end."""
	import threading

	from . import debugLog, state

	if state.get(STATE_KEY) == REPAIR_VERSION or not nvdaEnv.shouldWriteToDisk():
		return False
	configDir = nvdaEnv.configDir()
	needed = needsRepair(configDir)
	if needed is None:
		debugLog.note("gestures.ini could not be read, so the keystroke repair is tried again next time NVDA starts")
		return False
	if not needed:
		state.set(STATE_KEY, REPAIR_VERSION)
		return False
	debugLog.section("Repairing the keystrokes of an earlier migration")

	def finish(outcome):
		try:
			_finish(outcome)
		finally:
			finished()

	def _finish(outcome):
		if isinstance(outcome, Exception):
			debugLog.note(f"the backup failed, so nothing was repaired; it is tried again next time NVDA starts: {outcome}")
			return
		result = repairGestures(configDir, debugLog.note)
		if result.failed:
			debugLog.note(f"gestures.ini could not be repaired; tried again next time NVDA starts: {result.failed}")
			return
		if result.changes:
			reloadUserGestures()
		state.set(STATE_KEY, REPAIR_VERSION)
		debugLog.note(f"repaired {len(result.changes)} keystrokes in {result.path}; backup {getattr(outcome, 'path', '')}")
		if result.changes:
			count = len(result.changes)
			announce(
				f"JAWS Migration Assistant repaired {count} {'keystroke' if count == 1 else 'keystrokes'} from your earlier JAWS migration "
				"that typed letters or took the place of NVDA's own commands.",
			)

	def work():
		from . import migrator

		try:
			outcome = migrator._backupFirst("Before repairing the keystrokes of an earlier migration")
		except Exception as error:
			debugLog.error("the backup before the keystroke repair failed")
			outcome = error
		import wx

		wx.CallAfter(finish, outcome)

	threading.Thread(target=work, name="jawsMigratorGestureRepair", daemon=True).start()
	return True
