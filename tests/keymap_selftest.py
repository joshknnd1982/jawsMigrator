# flake8: noqa
# Self-test for jawsKeyMap against a real JAWS installation, when one is present.
# Run: python tests/keymap_selftest.py
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins"))
sys.path.insert(0, os.path.dirname(__file__))
# Importing jawsMigrator runs its __init__, which imports NVDA's modules: stand-ins first.
import nvdaStubs  # noqa: E402

nvdaStubs.install()
from jawsMigrator.jawsKeyMap import *  # noqa: E402,F403
from jawsMigrator.jawsKeyMap import _convertKey  # noqa: E402

DEFAULT_JKM_PATH = r"C:\ProgramData\Freedom Scientific\JAWS\2026\Scripts\enu\Default.JKM"


def _findDefaultJkm() -> str | None:
	import glob
	import os

	if os.path.isfile(DEFAULT_JKM_PATH):
		return DEFAULT_JKM_PATH
	candidates = sorted(glob.glob(r"C:\ProgramData\Freedom Scientific\JAWS\*\Scripts\enu\Default.JKM"))
	return candidates[-1] if candidates else None


def _selfTest() -> bool:
	"""Convert the keyboard bindings of the installed Default.JKM and print a summary."""
	import collections

	problems = []
	# Consistency of the data itself.
	overlap = set(SCRIPT_MAP) & set(QUICK_NAV_MAP)
	if overlap:
		problems.append(f"SCRIPT_MAP and QUICK_NAV_MAP overlap: {sorted(overlap)}")
	for mapName, table in (("SCRIPT_MAP", SCRIPT_MAP), ("QUICK_NAV_MAP", QUICK_NAV_MAP)):
		for name, target in table.items():
			if name != name.lower() or len(target) != 4 or not all(isinstance(v, str) and v for v in target):
				problems.append(f"{mapName}[{name!r}] is malformed")
	for name in ADDITIONAL_TARGETS:
		if name not in SCRIPT_MAP and name not in QUICK_NAV_MAP:
			problems.append(f"ADDITIONAL_TARGETS[{name!r}] has no primary target")
	for name in PASSTHROUGH_SCRIPTS:
		if getNvdaTargets(name):
			problems.append(f"{name!r} is both mapped and pass-through")
	for token in list(KEY_NAMES) + list(UNSUPPORTED_KEY_TOKENS):
		if token != token.lower():
			problems.append(f"key token {token!r} is not lower case")

	path = _findDefaultJkm()
	if not path:
		print("Default.JKM not found; skipping the keymap test.")
		for problem in problems:
			print("PROBLEM:", problem)
		return not problems
	bindings = parseJkm(readJkmFile(path))
	print(f"Keymap: {path} ({len(bindings)} lines with bindings)")

	# Every token used in Default.JKM's keyboard sections must be known.
	keyboardSections = {name for name in DEFAULT_JKM_SECTIONS if name.endswith(" keys")}
	unknownTokens = collections.Counter()
	for section, key, script in bindings:
		if section.lower() not in keyboardSections or key.lower().startswith("braille"):
			continue
		for step in key.rstrip("*").split("&"):
			for token in step.split("+"):
				token = token.replace(" ", "").lower()
				if token not in KEY_NAMES and token not in UNSUPPORTED_KEY_TOKENS:
					unknownTokens[token] += 1
	if unknownTokens:
		problems.append(f"tokens missing from KEY_NAMES: {dict(unknownTokens)}")

	perSection = collections.Counter()
	skippedSections = collections.Counter()
	reasons = collections.Counter()
	reasonExamples = collections.defaultdict(list)
	gestures = set()
	scriptsSeen = set()
	mappedScripts = set()
	# Unmapped scripts, counted over bindings whose key converts (real gaps) and over all bindings.
	unmappedConvertible = collections.Counter()
	unmappedAll = collections.Counter()
	total = converted = mapped = usable = passThrough = 0
	targetsByGesture = collections.defaultdict(set)
	for section, key, script in bindings:
		layout = getSectionLayout(section)
		if layout is None:
			skippedSections[section] += 1
			continue
		total += 1
		perSection[section] += 1
		name = normalizeScriptName(script)
		scriptsSeen.add(name)
		gesture, reason = _convertKey(key, layout)
		if gesture:
			converted += 1
			gestures.add(gesture)
		else:
			reasons[reason] += 1
			if len(reasonExamples[reason]) < 3:
				reasonExamples[reason].append(f"{key}={script}")
		targets = getNvdaTargets(name)
		if targets:
			mapped += 1
			mappedScripts.add(name)
			if gesture:
				usable += 1
				for module, cls, nvdaScript, _desc in targets:
					targetsByGesture[(gesture.lower(), module, cls)].add(nvdaScript)
		elif isPassThroughBinding(key, name):
			passThrough += 1
		else:
			unmappedAll[name] += 1
			if gesture:
				unmappedConvertible[name] += 1

	print("\nBindings in convertible sections:")
	for section, count in perSection.items():
		print(f"  [{section}] ({getSectionLayout(section)}): {count}")
	skipped = sum(skippedSections.values())
	print(f"  Total: {total}   (lines in {len(skippedSections)} other sections skipped: {skipped})")
	print(f"\nConverted to NVDA gestures: {converted} bindings, {len(gestures)} distinct gestures")
	print(f"Unconvertible keys: {total - converted}")
	for reason, count in reasons.most_common():
		print(f"  {reason}: {count}  e.g. {'; '.join(reasonExamples[reason])}")
	print(f"\nDistinct JAWS scripts in these sections: {len(scriptsSeen)}")
	print(
		f"JAWS scripts with an NVDA equivalent: {len(mappedScripts)} used here"
		f" (SCRIPT_MAP holds {len(SCRIPT_MAP)}, QUICK_NAV_MAP {len(QUICK_NAV_MAP)})",
	)
	print(f"Bindings with an NVDA equivalent: {mapped}; with a convertible key too (ready to bind): {usable}")
	print(f"Pass-through bindings NVDA handles natively: {passThrough}")
	onlyUnconvertible = len(set(unmappedAll) - set(unmappedConvertible))
	print(
		f"Unmapped scripts: {len(unmappedAll)} ({sum(unmappedAll.values())} bindings);"
		f" {onlyUnconvertible} of them only have layered, braille or unsupported keys.",
	)
	print(
		f"Unmapped scripts that have a convertible key: {len(unmappedConvertible)}"
		f" ({sum(unmappedConvertible.values())} bindings). Top 40 by frequency:",
	)
	for name, count in unmappedConvertible.most_common(40):
		print(f"  {count:3}  {name}")
	conflicts = {k: v for k, v in targetsByGesture.items() if len(v) > 1}
	print(f"\nGestures mapped to more than one NVDA script on the same class: {len(conflicts)}")
	for (gesture, module, cls), scripts in sorted(conflicts.items())[:10]:
		print(f"  {gesture} on {module}.{cls}: {', '.join(sorted(scripts))}")

	if problems:
		for problem in problems:
			print("PROBLEM:", problem)
	else:
		print("\nData checks passed.")
	return not problems


if __name__ == "__main__":
	_selfTest()
