# Unit tests for version 1.41, from the tester's answer on issue 37. Asked whether NVDA should say JAWS's "Screen Shade
# on" and "Screen Shade off", they wrote: "I'll let that up to you and Josh. I do think we should add a command to keep it
# turned on if the user wants that." Josh kept "Screen curtain", NVDA's name for it, and chose Control+F11.
# 1.39's F11 turns the curtain on JAWS's way, until NVDA restarts; JAWS has no key that keeps its Screen Shade on, and
# its shade is always off when JAWS starts. NVDA's own NVDA+Control+Escape pressed twice keeps the curtain on, also each
# time NVDA starts (it checks "Make screen black"), but the layer ends after one key.
# - NVDA+Shift+J, then Control+F11 or Control+Print Screen turns the curtain on and keeps it on, as NVDA's own key
#   pressed twice, and says "Screen curtain on. NVDA turns it on each time it starts." (KeepTests, WarningTests,
#   RefusalTests, LayerTests). test_v139_screenShade's NVDA 2026.2 ScreenCurtain and its own screen curtain commands run
#   here too, beside the new key.
# Run: python -m unittest tests.test_v141_keepCurtain -v

import ast
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import jawsMigrator  # noqa: E402
from jawsMigrator import screenShade  # noqa: E402
from test_v139_screenShade import CurtainCase, RefreshableRecogResultNVDAObject, Spri, WarnOnLoadDialog  # noqa: E402

KEPT = "Screen curtain on. NVDA turns it on each time it starts."


class KeepTests(CurtainCase):
	def test_controlF11TurnsItOnAndKeepsIt(self):
		curtain = self.startNvda()
		self.assertEqual(screenShade.keep(), KEPT)
		self.assertTrue(curtain.enabled)
		self.assertTrue(self.settings["enabled"], '"Make screen black" checked: NVDA turns it on each time it starts')
		self.assertEqual(self.said, [(KEPT, Spri.NOW)])
		self.assertIn("MagSetFullscreenColorEffect", self.magnification.calls)

	def test_itIsNvdasOwnKeyPressedTwice(self):
		# NVDA's own NVDA+Control+Escape pressed twice leaves NVDA in the same state, with NVDA's own words.
		self.startNvda()
		screenShade.keep()
		mine = (self.package.screenCurtain.enabled, dict(self.settings))
		self.setUp()
		curtain = self.startNvda()
		self.nvdasKey(presses=2)
		self.assertEqual((curtain.enabled, dict(self.settings)), mine)
		self.assertEqual(self.said[-1], ("Screen curtain enabled", Spri.NOW))

	def test_nvdaStartsWithItOnNextTime(self):
		self.startNvda()
		screenShade.keep()
		kept = self.settings["enabled"]
		# NVDA restarts: its ScreenCurtain turns the curtain on from its settings, before any add-on runs.
		curtain = self.startNvda(curtainOn=kept)
		self.assertTrue(curtain.enabled)
		self.said.clear()
		self.assertEqual(screenShade.report(), KEPT, "Shift+F11 says the same")

	def test_onAlreadyItIsKeptFromNow(self):
		# F11 turned it on until NVDA restarts; Control+F11 keeps it on. The screen is black already: no warning.
		curtain = self.startNvda()
		screenShade.toggle()
		self.assertFalse(self.settings["enabled"])
		self.settings["warnOnLoad"] = True
		self.said.clear()
		self.assertEqual(screenShade.keep(), KEPT)
		self.assertTrue(curtain.enabled)
		self.assertTrue(self.settings["enabled"])
		self.assertEqual(WarnOnLoadDialog.made, [])
		self.assertEqual(self.said, [(KEPT, Spri.NOW)])
		self.assertEqual(self.magnification.calls.count("MagInitialize"), 1, "turned on once, not again")

	def test_onAlreadyAsNvdasOwnKeyWhenItsFirstPressTurnedItOn(self):
		# NVDA's own key: the first press turns it on until NVDA restarts, the second finds it on and keeps it on.
		self.startNvda()
		screenShade.toggle()
		screenShade.keep()
		mine = (self.package.screenCurtain.enabled, dict(self.settings))
		self.setUp()
		curtain = self.startNvda()
		self.nvdasKey(presses=2)
		self.assertEqual((curtain.enabled, dict(self.settings)), mine)

	def test_keptAlreadyItSaysSo(self):
		curtain = self.startNvda(curtainOn=True)
		self.assertEqual(screenShade.keep(), KEPT)
		self.assertTrue(curtain.enabled)
		self.assertTrue(self.settings["enabled"])
		self.assertEqual(self.said, [(KEPT, Spri.NOW)])

	def test_f11ThenTurnsItOffForGood(self):
		curtain = self.startNvda()
		screenShade.keep()
		self.said.clear()
		self.assertEqual(screenShade.toggle(), "Screen curtain off")
		self.assertFalse(curtain.enabled)
		self.assertFalse(self.settings["enabled"], "NVDA starts without it next time")
		self.assertEqual(self.said, [("Screen curtain off", Spri.NOW)])

	def test_f11StillTurnsItOnUntilNvdaRestarts(self):
		self.startNvda()
		self.assertEqual(screenShade.toggle(), "Screen curtain on")
		self.assertFalse(self.settings["enabled"])

	def test_nvdasToggleSoundPlaysOnce(self):
		self.settings["playToggleSounds"] = True
		self.startNvda()
		screenShade.keep()
		screenShade.keep()
		self.assertEqual([os.path.basename(path) for path in self.played], ["screenCurtainOn.wav"])


class WarningTests(CurtainCase):
	"""NVDA's "Always show a warning when enabling Screen Curtain", checked as NVDA comes: its warning comes first."""

	def setUp(self):
		super().setUp()
		self.settings["warnOnLoad"] = True
		self.curtain = self.startNvda()

	def test_nvdasWarningFirst(self):
		self.assertIsNone(screenShade.keep())
		self.assertEqual(self.said, [])
		self.assertFalse(self.curtain.enabled)
		self.assertFalse(self.settings["enabled"])
		self.assertEqual(len(WarnOnLoadDialog.made), 1)
		self.assertIs(WarnOnLoadDialog.made[0].settings, self.settings)

	def test_yesTurnsItOnAndKeepsIt(self):
		screenShade.keep()
		self.modal[0][1](self.wx.YES)
		self.assertEqual([timer.milliseconds for timer in self.wx.timers], [100], "as NVDA waits after its warning")
		self.fireTimers()
		self.assertTrue(self.curtain.enabled)
		self.assertTrue(self.settings["enabled"])
		self.assertEqual(self.said, [(KEPT, Spri.NOW)])
		self.assertIsNone(screenShade._warning)

	def test_noLeavesItOffWithoutAWord(self):
		screenShade.keep()
		self.modal[0][1](self.wx.NO)
		self.fireTimers()
		self.assertFalse(self.curtain.enabled)
		self.assertFalse(self.settings["enabled"])
		self.assertEqual(self.said, [])

	def test_f11sWarningStillTurnsItOnUntilNvdaRestarts(self):
		screenShade.toggle()
		self.modal[0][1](self.wx.YES)
		self.fireTimers()
		self.assertTrue(self.curtain.enabled)
		self.assertFalse(self.settings["enabled"])
		self.assertEqual(self.said, [("Screen curtain on", Spri.NOW)])

	def test_pressedAgainTheWarningIsReadAgain(self):
		screenShade.keep()
		self.assertIsNone(screenShade.keep())
		self.assertIsNone(screenShade.toggle())
		self.assertEqual(len(WarnOnLoadDialog.made), 1, "no second warning")
		self.assertEqual(WarnOnLoadDialog.made[0].raised, 2)
		self.assertEqual(self.said, [])

	def test_nvdasOwnWarningOpen(self):
		self.nvdasKey()
		self.assertIsNone(screenShade.keep())
		self.assertEqual(len(WarnOnLoadDialog.made), 1)
		self.assertEqual(WarnOnLoadDialog.made[0].raised, 1)


class RefusalTests(CurtainCase):
	def test_notAvailable(self):
		self.assertEqual(screenShade.keep(), "Screen curtain not available")
		self.assertEqual(self.said, [("Screen curtain not available", Spri.NOW)])

	def test_whileNvdaRecognizesContent(self):
		curtain = self.startNvda()
		self.focus = RefreshableRecogResultNVDAObject()
		self.assertEqual(screenShade.keep(), "Cannot enable screen curtain while performing content recognition")
		self.assertFalse(curtain.enabled)
		self.assertFalse(self.settings["enabled"])

	def test_theScreenDidNotGoBlack(self):
		# NVDA's ScreenCurtain saves "Make screen black" only once the screen is black.
		curtain = self.startNvda()
		self.black = False
		self.assertEqual(screenShade.keep(), "Could not enable screen curtain")
		self.assertFalse(curtain.enabled)
		self.assertFalse(self.settings["enabled"])
		self.assertEqual(self.said, [("Could not enable screen curtain", Spri.NOW)])
		self.assertEqual(self.log.errors, ["jawsMigrator: could not turn the screen curtain on"])


class LayerTests(unittest.TestCase):
	def test_theLayersKeys(self):
		rows = {script: (gestures, key, words) for gestures, script, key, words in jawsMigrator.LAYER_COMMANDS}
		self.assertEqual(
			rows["keepScreenShade"],
			(
				("kb:control+f11", "kb:control+printScreen"),
				"Control+F11 or Control+Print Screen",
				"turn the screen curtain on and keep it on, also each time NVDA starts.",
			),
		)
		self.assertEqual(jawsMigrator.LAYER_GESTURES["kb:control+f11"], "keepScreenShade")
		self.assertEqual(jawsMigrator.LAYER_GESTURES["kb:control+printScreen"], "keepScreenShade")
		# 1.39's keys are as they were.
		self.assertEqual(jawsMigrator.LAYER_GESTURES["kb:f11"], "toggleScreenShade")
		self.assertEqual(jawsMigrator.LAYER_GESTURES["kb:shift+f11"], "reportScreenShade")
		scripts = [script for _gestures, script, _key, _words in jawsMigrator.LAYER_COMMANDS]
		self.assertEqual(scripts.index("keepScreenShade"), scripts.index("reportScreenShade") + 1, "after Shift+F11 in the help")

	def test_theScriptRunsTheModule(self):
		plugin = jawsMigrator.GlobalPlugin.__new__(jawsMigrator.GlobalPlugin)
		calls = []
		with mock.patch.object(screenShade, "keep", lambda: calls.append("keep")):
			plugin.script_keepScreenShade(None)
		self.assertEqual(calls, ["keep"])
		self.assertIn("as NVDA+Control+Escape pressed twice does", jawsMigrator.GlobalPlugin.script_keepScreenShade.__doc__)

	def test_notSpokenOnDemand(self):
		# As NVDA's own toggle, and F11: it changes something rather than reading something out.
		with open(jawsMigrator.__file__, encoding="utf-8") as file:
			tree = ast.parse(file.read())
		node = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "script_keepScreenShade")
		keywords = {keyword.arg for decorator in node.decorator_list for keyword in getattr(decorator, "keywords", [])}
		self.assertNotIn("speakOnDemand", keywords)

	def test_theWordsAreShiftF11s(self):
		self.assertEqual(screenShade.ON_AT_EVERY_START, KEPT)

	def test_theReadme(self):
		with open(os.path.join(os.path.dirname(__file__), "..", "README.md"), encoding="utf-8") as file:
			text = file.read()
		self.assertIn("| Control+F11 or Control+Print Screen |", text)
		self.assertIn("- **Control+F11** or **Control+Print Screen** turns the curtain on and keeps it on", text)


if __name__ == "__main__":
	unittest.main()
