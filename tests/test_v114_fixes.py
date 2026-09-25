# Unit tests for version 1.14, from a tester's report on version 1.13 (issue 4):
# - listPosition: Alt+Tab back to This PC still said "Data (D:), 3 of 3", where JAWS says "Data (D:)", and
#   Alt+Tab said "This PC - File Explorer, 2 of 11" at each press, where JAWS says the window's name alone.
#   JAWS's File Explorer script adds the position only when you move from item to item.
# The imitation NVDA below does what NVDA 2026.2 does, as far as this goes:
# speech.speech._objectSpeech_calculateAllowedProps with "Cell coordinates" and "Report object position
# information" on, api.getFocusObject, and globalVars.focusAncestors with focusDifferenceLevel, as
# api.setFocusObject leaves them (the ancestors from the difference level on are the ones the focus has just
# entered). The objects are the tester's, as the 1.13 log has them. The assistant's register, unregister and
# wrapper are the real ones.
# Run: python -m unittest tests.test_v114_fixes -v

import enum
import functools
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

from jawsMigrator import listCoordinates, listPosition, state  # noqa: E402


class OutputReason(enum.Enum):
	FOCUS = "focus"
	FOCUSENTERED = "focusEntered"
	CARET = "caret"
	QUICKNAV = "quickNav"
	QUERY = "query"


class Role(enum.Enum):
	PANE = "pane"
	WINDOW = "window"
	DIALOG = "dialog"
	LIST = "list"
	LISTITEM = "list item"
	GROUPING = "grouping"
	MENU = "menu"
	MENUITEM = "menu item"
	TABLE = "table"
	TABLECELL = "cell"


POSITION = ("positionInfo_indexInGroup", "positionInfo_similarItemsInGroup")


def _objectSpeech_calculateAllowedProps(reason, shouldReportTextContent, objRole):
	"""NVDA 2026.2's speech.speech._objectSpeech_calculateAllowedProps, with "Cell coordinates" and positions on."""
	return {
		"name": True,
		"rowNumber": True,
		"columnNumber": True,
		"includeTableCellCoords": True,
		"cellCoordsText": True,
		"positionInfo_level": True,
		"positionInfo_indexInGroup": True,
		"positionInfo_similarItemsInGroup": True,
	}


class Obj:
	def __init__(self, role, name, windowClassName="DirectUIHWND"):
		self.role, self.name, self.windowClassName = role, name, windowClassName


class MultitaskingViewFrameListItem(Obj):
	"""NVDA's class for an Alt+Tab item (appModules.explorer)."""


# This PC, as NVDA's focus ancestors had it in the tester's log: "Items View, list, Devices and drives, grouping".
DESKTOP = Obj(Role.PANE, "Desktop", "#32769")
EXPLORER = Obj(Role.WINDOW, "This PC - File Explorer", "CabinetWClass")
FOLDER_VIEW = Obj(Role.PANE, "Shell Folder View")
ITEMS_VIEW = Obj(Role.LIST, "Items View")
DRIVES = Obj(Role.GROUPING, "Devices and drives")
THIS_PC = [DESKTOP, EXPLORER, FOLDER_VIEW, ITEMS_VIEW, DRIVES]
DATA_DRIVE = Obj(Role.LISTITEM, "Data (D:)")
LOCAL_DISK = Obj(Role.LISTITEM, "Local Disk (C:)")
ALT_TAB_ITEM = MultitaskingViewFrameListItem(Role.LISTITEM, "This PC - File Explorer", "XamlExplorerHostIslandWindow")


class ListPositionTests(unittest.TestCase):
	def setUp(self):
		self.speechModule = types.ModuleType("speech.speech")
		self.speechModule._objectSpeech_calculateAllowedProps = _objectSpeech_calculateAllowedProps
		speechPackage = types.ModuleType("speech")
		speechPackage.speech = self.speechModule
		controlTypes = types.ModuleType("controlTypes")
		controlTypes.OutputReason, controlTypes.Role = OutputReason, Role
		self.focus = None
		api = types.ModuleType("api")
		api.getFocusObject = lambda: self.focus
		self.globalVars = types.ModuleType("globalVars")
		self.globalVars.focusAncestors, self.globalVars.focusDifferenceLevel = [], 0
		modules = mock.patch.dict(
			sys.modules,
			{"speech": speechPackage, "speech.speech": self.speechModule, "controlTypes": controlTypes, "api": api, "globalVars": self.globalVars},
		)
		modules.start()
		self.addCleanup(modules.stop)
		self.addCleanup(self._restoreNvda)
		for module in (listCoordinates, listPosition):
			module._failed = False
		listCoordinates._logged = False
		listPosition._logged.clear()

	def _restoreNvda(self):
		listPosition.unregister()
		listCoordinates.unregister()
		listCoordinates._positionRule = None
		self.speechModule._objectSpeech_calculateAllowedProps = _objectSpeech_calculateAllowedProps
		listCoordinates._replaced.clear()
		for module in (listCoordinates, listPosition):
			module._failed = False

	def focusOn(self, obj, ancestors=(), differenceLevel=0):
		"""What api.setFocusObject leaves: the focus, its ancestors, and how many of them the old focus shared."""
		self.focus = obj
		self.globalVars.focusAncestors, self.globalVars.focusDifferenceLevel = list(ancestors), differenceLevel

	def allowed(self, role=Role.LISTITEM, reason=OutputReason.FOCUS):
		return self.speechModule._objectSpeech_calculateAllowedProps(reason, False, role)

	def saysPosition(self, **kwargs):
		allowed = self.allowed(**kwargs)
		return all(allowed[name] for name in POSITION)

	def registerBoth(self):
		listCoordinates.register()
		listPosition.register()

	def test_altTabBackToThisPcSaysTheDriveAlone(self):
		# Issue 4 with 1.13: Alt+Tab from Notepad to This PC said "Items View, list, Devices and drives, grouping,
		# expanded", then "Data (D:), 3 of 3". Only the desktop and the window were shared with Notepad's focus.
		self.registerBoth()
		self.focusOn(DATA_DRIVE, THIS_PC, 2)
		allowed = self.allowed()
		self.assertFalse(any(allowed[name] for name in POSITION), "Data (D:), as JAWS says it")
		self.assertFalse(allowed["includeTableCellCoords"], "and still without 1.13's row and column")
		self.assertTrue(allowed["name"])

	def test_movingThroughTheListSaysThePosition(self):
		# JAWS's ActiveItemChangedEvent (ExplorerFrame.jss) says the position as the active item changes.
		self.registerBoth()
		self.focusOn(LOCAL_DISK, THIS_PC, len(THIS_PC))
		self.assertTrue(self.saysPosition(), "Up Arrow to C: says 2 of 3")
		self.focusOn(DATA_DRIVE, THIS_PC, 4)
		self.assertTrue(self.saysPosition(), "from the Folders group to Devices and drives: the list is the same")

	def test_tabToTheFileListInAnOpenDialog(self):
		self.registerBoth()
		dialog = [DESKTOP, Obj(Role.DIALOG, "Open", "#32770"), Obj(Role.LIST, "Items View")]
		self.focusOn(Obj(Role.LISTITEM, "Jaws migrator 1.12 log .txt"), dialog, 2)
		self.assertFalse(self.saysPosition(), "Shift+Tab to the file list: the file alone")
		self.focusOn(Obj(Role.LISTITEM, "jaws migrator 3.12 log with several bugs.txt"), dialog, 3)
		self.assertTrue(self.saysPosition(), "Down Arrow: 8 of 16")

	def test_altTabSaysTheWindowAlone(self):
		# JAWS's ProcessTaskSwitchList (Default.JSS) says only the window's name. While Alt is down, NVDA gives an
		# Alt+Tab item the desktop as its container, so it has no list among its ancestors.
		self.registerBoth()
		self.focusOn(ALT_TAB_ITEM, [DESKTOP], 1)
		self.assertFalse(self.saysPosition(), "This PC - File Explorer, without 1 of 11")
		self.focusOn(ALT_TAB_ITEM, [DESKTOP, Obj(Role.WINDOW, "Task Switching"), Obj(Role.LIST, "Running applications")], 3)
		self.assertFalse(self.saysPosition(), "and after Tab, with Alt still down")

	def test_nvdaTabAndOtherReasonsKeepThePosition(self):
		self.registerBoth()
		self.focusOn(DATA_DRIVE, THIS_PC, 2)
		for reason in (OutputReason.QUERY, OutputReason.CARET, OutputReason.QUICKNAV, OutputReason.FOCUSENTERED):
			self.assertTrue(self.saysPosition(reason=reason), reason)
		self.focusOn(ALT_TAB_ITEM, [DESKTOP], 1)
		self.assertTrue(self.saysPosition(reason=OutputReason.QUERY), "NVDA+Tab in Alt+Tab")

	def test_otherListsAndControlsKeepThePosition(self):
		self.registerBoth()
		outlook = [DESKTOP, Obj(Role.WINDOW, "Inbox - Outlook", "rctrl_renwnd32"), Obj(Role.TABLE, "Table View", "OutlookGrid")]
		self.focusOn(Obj(Role.LISTITEM, "From joshknnd1982", "OutlookGrid"), outlook, 1)
		self.assertTrue(self.saysPosition(), "Outlook's messages")
		self.focusOn(Obj(Role.LISTITEM, "Colors", "SysListView32"), [DESKTOP, Obj(Role.LIST, "Colors", "SysListView32")], 1)
		self.assertTrue(self.saysPosition(), "a list in another window")
		self.focusOn(Obj(Role.MENUITEM, "View log", "#32768"), [DESKTOP, Obj(Role.MENU, "NVDA", "#32768")], 1)
		self.assertTrue(self.saysPosition(role=Role.MENUITEM), "a menu item")
		self.focusOn(Obj(Role.LISTITEM, "Data (D:)"), [DESKTOP, EXPLORER], 1)
		self.assertTrue(self.saysPosition(), "an items view item with no list among its ancestors")

	def test_onlyTheFocusIsChecked(self):
		self.registerBoth()
		self.focusOn(EXPLORER, [DESKTOP], 1)
		self.assertTrue(self.saysPosition(), "a list item read while the focus is elsewhere")
		self.focusOn(DATA_DRIVE, THIS_PC, None)
		self.assertTrue(self.saysPosition(), "no difference level known")

	def test_withPositionsOffInNvdaNothingIsLogged(self):
		# "Report object position information" unchecked: NVDA allows no position, and the assistant has nothing to do.
		def withoutPositions(reason, shouldReportTextContent, objRole):
			allowed = _objectSpeech_calculateAllowedProps(reason, shouldReportTextContent, objRole)
			for name in POSITION:
				allowed[name] = False
			return allowed

		self.speechModule._objectSpeech_calculateAllowedProps = withoutPositions
		listPosition.register()
		self.focusOn(DATA_DRIVE, THIS_PC, 2)
		with mock.patch.object(listPosition, "_log") as log:
			self.assertFalse(any(self.allowed()[name] for name in POSITION))
		log.assert_not_called()

	def test_eitherSettingAlone(self):
		self.focusOn(DATA_DRIVE, THIS_PC, 2)
		listPosition.register()
		allowed = self.allowed()
		self.assertFalse(any(allowed[name] for name in POSITION), "the position is left out")
		self.assertTrue(allowed["includeTableCellCoords"], "the row and column stay: that setting is off")
		listPosition.unregister()
		self.assertIs(self.speechModule._objectSpeech_calculateAllowedProps, _objectSpeech_calculateAllowedProps, "NVDA's own is back")
		listCoordinates.register()
		allowed = self.allowed()
		self.assertTrue(all(allowed[name] for name in POSITION), "1.13 alone keeps the position")
		self.assertFalse(allowed["includeTableCellCoords"])

	def test_bothOffInEitherOrderGiveNvdaItsOwnBack(self):
		for first, second in ((listCoordinates, listPosition), (listPosition, listCoordinates)):
			for on in ((listCoordinates, listPosition), (listPosition, listCoordinates)):
				for module in on:
					module.register()
				self.assertIs(self.speechModule._objectSpeech_calculateAllowedProps.__wrapped__, _objectSpeech_calculateAllowedProps, "one wrapper for both")
				first.unregister()
				self.assertIsNot(self.speechModule._objectSpeech_calculateAllowedProps, _objectSpeech_calculateAllowedProps, "the other is still on")
				second.unregister()
				self.assertIs(self.speechModule._objectSpeech_calculateAllowedProps, _objectSpeech_calculateAllowedProps, (first, second))
				self.focusOn(DATA_DRIVE, THIS_PC, 2)
				self.assertTrue(self.saysPosition())

	def test_registeredTwiceWrappedOnce(self):
		self.registerBoth()
		self.registerBoth()
		listPosition.register()
		self.assertIs(self.speechModule._objectSpeech_calculateAllowedProps.__wrapped__, _objectSpeech_calculateAllowedProps)
		self.assertTrue(listPosition.isRegistered())
		listPosition.unregister()
		self.assertFalse(listPosition.isRegistered())
		self.assertIsNone(listCoordinates._positionRule)

	def test_anotherAddonsWrapperOverTheAssistants(self):
		listPosition.register()
		ours = self.speechModule._objectSpeech_calculateAllowedProps

		@functools.wraps(ours)
		def otherAddon(*args, **kwargs):
			return ours(*args, **kwargs)

		self.speechModule._objectSpeech_calculateAllowedProps = otherAddon
		self.focusOn(DATA_DRIVE, THIS_PC, 2)
		listPosition.unregister()
		self.assertIs(self.speechModule._objectSpeech_calculateAllowedProps, otherAddon)
		self.assertTrue(self.saysPosition(), "the assistant's, still inside it, does nothing")
		listPosition.register()
		self.assertIs(self.speechModule._objectSpeech_calculateAllowedProps, otherAddon, "not wrapped a second time")
		self.assertFalse(self.saysPosition())

	def test_theSetting(self):
		self.assertTrue(listPosition.wanted({}))
		self.assertFalse(listPosition.wanted({listPosition.STATE_KEY: False}))
		self.assertFalse(listPosition.wanted(None))
		self.assertIs(state.DEFAULTS[listPosition.STATE_KEY], True)

	def test_whatTheLogSaysOnce(self):
		with self.assertLogs("nvda", level="DEBUG") as logged:
			listPosition.register()
			for _ in range(3):
				self.focusOn(DATA_DRIVE, THIS_PC, 2)
				self.allowed()
				self.focusOn(ALT_TAB_ITEM, [DESKTOP], 1)
				self.allowed()
		lines = [line for line in logged.output if "jawsMigrator" in line]
		self.assertEqual(sum("NVDA says a position in File Explorer and Alt+Tab where JAWS says it" in line for line in lines), 1, lines)
		self.assertEqual(sum("the focus came to File Explorer's list (Items View)" in line for line in lines), 1, lines)
		self.assertEqual(sum("Alt+Tab says a window without its position" in line for line in lines), 1, lines)

	def test_aFailureLeavesNvdasChoice(self):
		listPosition.register()
		self.focus = DATA_DRIVE
		self.globalVars.focusDifferenceLevel = 2
		self.globalVars.focusAncestors = [DESKTOP, types.SimpleNamespace(name="broken")]  # no role: a dead object
		with self.assertLogs("nvda", level="DEBUG") as logged:
			self.assertTrue(self.saysPosition())
			self.assertTrue(self.saysPosition())
		failures = [line for line in logged.output if "could not leave out a position" in line]
		self.assertEqual(len(failures), 1, logged.output)

	def test_nvdaWithoutTheFunctionIsLeftAlone(self):
		del self.speechModule._objectSpeech_calculateAllowedProps
		with self.assertLogs("nvda", level="DEBUG") as logged:
			listPosition.register()
		self.assertTrue(any("NVDA has no _objectSpeech_calculateAllowedProps" in line for line in logged.output), logged.output)
		self.speechModule._objectSpeech_calculateAllowedProps = _objectSpeech_calculateAllowedProps


if __name__ == "__main__":
	unittest.main()
