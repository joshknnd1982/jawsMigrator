# Unit tests for version 1.38, from a tester's issue 36: to try 1.36's JAWS keystroke helper on Insert+Space, the tester
# pressed NVDA+Shift+J, then K, then what they meant as Insert+Space. NVDA's log has "Input: kb(laptop):space", not
# "NVDA+space": Insert, one of their NVDA keys (NVDAModifierKeys 7: Caps Lock and both Inserts), wasn't down when Space
# went down. So the helper said what Space does: "In JAWS, Space runs Virtual Spacebar. NVDA has no command that does
# the same. In NVDA, space has no command of its own." It named the key, but nothing said Insert had been let go.
# - Now, when the NVDA key went down during the helper but is not held with the key that follows, the helper says so
#   first: "You let go of Insert before you pressed space, so NVDA got space by itself. For Insert+space, hold Insert
#   down while you press space." Then what that key does, as before.
# NVDA hands the helper's capture function each key as it goes down (inputCore.InputManager.executeGesture, from
# keyboardHandler.internal_keyDownEvent): the NVDA key as a modifier (isModifier, isNVDAModifierKey), and the next key
# with the modifiers held with it, the NVDA key's (vkCode, extended) among them while it is down. The key presses here
# are imitations of NVDA's KeyboardInputGesture with those attributes. JAWS 2026's key map lines are its own, from
# Scripts\enu\Default.JKM. The assistant's code is the real one.
# Run: python -m unittest tests.test_v138_heldKeys -v

import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import jawsMigrator  # noqa: E402
from jawsMigrator import jawsFiles, jawsKeyMap, keyPlan, nvdaApply  # noqa: E402

VK_INSERT = 0x2D
VK_CAPITAL = 0x14
VK_SPACE = 0x20
VK_ESCAPE = 0x1B
INSERT = (VK_INSERT, True)
NUMPAD_INSERT = (VK_INSERT, False)
CAPS_LOCK = (VK_CAPITAL, False)

# JAWS 2026's own lines of Scripts\enu\Default.JKM (line numbers in that file).
JAWS_JKM_LINES = (
	"[Common Keys]\n"
	"JAWSKey+Space&H=ShowSpeechHistory\n"  # 79
	"Insert+Space&H=ShowSpeechHistory\n"  # 80
	"[virtual keys]\n"
	"Space=VirtualSpacebar\n"
)
SPACE_ALONE = "In JAWS, Space runs Virtual Spacebar. NVDA has no command that does the same. In NVDA, space has no command of its own."
INSERT_SPACE = (
	"In JAWS, Insert+Space starts a layered keystroke: you press it, then another key. "
	"In NVDA, NVDA+shift+j starts the JAWS Migration Assistant's layer of commands. It has JAWS's speech history keys, "
	"H, Control+H and Shift+H, its notification keys, N and Shift+N, D for audio ducking, F11 and Print Screen for the "
	"screen curtain, and question mark for its help. "
	"In NVDA, NVDA+space has no command of its own."
)


class KeyDown:
	"""A key going down, as NVDA hands it to a capture function (keyboardHandler.KeyboardInputGesture)."""

	def __init__(self, vkCode, extended=False, modifiers=(), nvdaKey=False, modifier=False, displayName="", identifier=""):
		self.vkCode, self.isExtended = vkCode, extended
		self.modifiers = set(modifiers)
		self.isNVDAModifierKey = nvdaKey
		self.isModifier = modifier or nvdaKey
		self.displayName = displayName
		self.normalizedIdentifiers = [identifier] if identifier else []


def nvdaKeyDown(key):
	return KeyDown(key[0], key[1], nvdaKey=True, displayName="NVDA", identifier="kb:nvda")


def space(*held):
	name = "NVDA+space" if held else "space"
	return KeyDown(VK_SPACE, modifiers=held, displayName=name, identifier=f"kb:{name.lower()}")


ESCAPE = KeyDown(VK_ESCAPE, displayName="escape", identifier="kb:escape")


class KeystrokeHelperTests(unittest.TestCase):
	"""NVDA+Shift+J, then K, then keys going down, as NVDA hands them to the helper."""

	def setUp(self):
		del nvdaStubs.spoken[:]
		self.plugin = jawsMigrator.GlobalPlugin.__new__(jawsMigrator.GlobalPlugin)
		jkm = jawsFiles.parseIni(JAWS_JKM_LINES)
		jaws = types.SimpleNamespace(displayName="JAWS 2026 (2026.2606.132.400)")
		self.plugin._keymapCache = (jaws, keyPlan.buildReverseMap(jkm, "laptop"), {}, "laptop", keyPlan.layerStarts(jkm, "laptop"))
		bound = {(jawsKeyMap.ASSISTANT_MODULE, jawsKeyMap.ASSISTANT_CLASS, "commandLayer"): ["NVDA+shift+j"]}
		self.notes = []
		patches = (
			mock.patch.object(nvdaApply, "gesturesForScript", lambda module, className, script: list(bound.get((module, className, script), []))),
			mock.patch.object(jawsMigrator.scriptHandler, "findScript", lambda gesture: None),
			# NVDA's wx.CallAfter, run once the capture function returns.
			mock.patch.object(jawsMigrator.wx, "CallAfter", lambda function, *args: self.later.append((function, args))),
			mock.patch.object(jawsMigrator.debugLog, "note", self.notes.append),
			mock.patch.object(jawsMigrator.inputCore.manager, "_captureFunc", None),
		)
		self.later = []
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)

	def press(self, *keys):
		"""NVDA+Shift+J, then K, then ``keys`` going down: what NVDA says after K."""
		self.plugin._startKeystrokeHelp()
		self.assertEqual(nvdaStubs.spoken.pop(), "Press a JAWS 2026 (2026.2606.132.400) keystroke to hear what it does in NVDA, or Escape to cancel.")
		for key in keys:
			capture = jawsMigrator.inputCore.manager._captureFunc
			self.assertIsNotNone(capture, "the helper still waits for a key")
			self.assertEqual(capture(key), True if key.isModifier else False)
		self.assertIsNone(jawsMigrator.inputCore.manager._captureFunc, "the helper is done")
		later, self.later[:] = list(self.later), []
		for function, args in later:
			function(*args)
		self.assertEqual(len(nvdaStubs.spoken), 1, nvdaStubs.spoken)
		return nvdaStubs.spoken.pop()

	def test_insertLetGoBeforeSpace(self):
		# What the tester's log shows, if Insert went down first: Space alone, without "NVDA+".
		said = self.press(nvdaKeyDown(INSERT), space())
		self.assertEqual(
			said,
			"You let go of Insert before you pressed space, so NVDA got space by itself. For Insert+space, hold Insert "
			"down while you press space. " + SPACE_ALONE,
		)
		self.assertEqual(self.notes, ["the JAWS keystroke helper got space after Insert was let go"])

	def test_insertHeldWithSpace(self):
		# Held, Windows repeats it as it stays down.
		said = self.press(nvdaKeyDown(INSERT), nvdaKeyDown(INSERT), space(INSERT))
		self.assertEqual(said, INSERT_SPACE)
		self.assertEqual(self.notes, [])

	def test_theNumericPadsInsert(self):
		self.assertEqual(self.press(nvdaKeyDown(NUMPAD_INSERT), space(NUMPAD_INSERT)), INSERT_SPACE)
		self.assertTrue(self.press(nvdaKeyDown(NUMPAD_INSERT), space()).startswith("You let go of Insert before you pressed space"))

	def test_capsLockLetGo(self):
		said = self.press(nvdaKeyDown(CAPS_LOCK), space())
		self.assertTrue(said.startswith("You let go of Caps Lock before you pressed space, so NVDA got space by itself. For Caps Lock+space, hold Caps Lock down"), said)

	def test_anotherNvdaKeyHeld(self):
		# Insert let go, then Caps Lock held with Space: Caps Lock+Space, as NVDA gets it.
		self.assertEqual(self.press(nvdaKeyDown(INSERT), nvdaKeyDown(CAPS_LOCK), space(CAPS_LOCK)), INSERT_SPACE)

	def test_spaceWithNoNvdaKey(self):
		# The tester's log, if Insert never went down: as 1.36 said.
		self.assertEqual(self.press(space()), SPACE_ALONE)
		self.assertEqual(self.notes, [])

	def test_escapeAfterInsertLetGo(self):
		self.assertEqual(self.press(nvdaKeyDown(INSERT), ESCAPE), "Cancelled")

	def test_shiftIsNotAnNvdaKey(self):
		shift = KeyDown(0x10, modifier=True, displayName="shift")
		self.assertEqual(self.press(shift, space()), SPACE_ALONE)

	def test_eachTimeStartsAfresh(self):
		# Insert went down, then Escape with Insert still down; the next time, Space alone isn't taken for a let-go Insert.
		self.assertEqual(self.press(nvdaKeyDown(INSERT), KeyDown(VK_ESCAPE, modifiers=[INSERT], displayName="NVDA+escape", identifier="kb:escape")), "Cancelled")
		self.assertEqual(self.press(space()), SPACE_ALONE)


if __name__ == "__main__":
	unittest.main()
