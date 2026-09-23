# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Offer to install ClassicSpeech when it is missing, or to update it when a newer release exists.

Like the update dialog, the explanation is a read-only text that NVDA can read line by line;
focus starts in it, and Tab reaches the buttons. When the assistant makes the offer on its own
(as it opens), a check box lets the user say not to offer it again; asking for a ClassicSpeech
feature always offers it.

Installing always takes ClassicSpeech's newest release from GitHub, checked against its
SHA-256 file, after NVDA's settings, add-ons and add-on settings are backed up. NVDA's own
installer does the rest; ClassicSpeech starts (or switches to the new version) when NVDA restarts.
"""

from __future__ import annotations

import wx

from .. import addonUpdates, debugLog, nvdaEnv, state
from .common import BORDER, TITLE, messageBox, postPopup, prePopup

TEXT_SIZE = (620, 220)
#: State key: the user asked not to be offered ClassicSpeech when the assistant opens.
DECLINED_KEY = "classicSpeechOfferDeclined"

EXPLANATION = (
	"ClassicSpeech is an NVDA add-on for speech and sound schemes, voice profiles and verbosity, much like JAWS's "
	"Speech and Sounds Manager and voice aliases. The JAWS Migration Assistant uses it for:\n"
	"- your JAWS speech and sound schemes, and the voices of your JAWS voice aliases;\n"
	"- JAWS sounds in place of NVDA's own sounds, and every JAWS sound, ready to use;\n"
	"- JAWS verbosity, number and text settings.\n\n"
	"Without it, everything NVDA itself supports is still migrated, and NVDA keeps its own sounds.\n\n"
	"ClassicSpeech is not in NVDA's Add-on Store. Its newest release is downloaded from GitHub "
	f"({addonUpdates.CLASSIC_SPEECH_PAGE}) at the moment you install it, checked against the release's SHA-256 "
	"checksum, and installed with NVDA's own installer, after NVDA's settings, add-ons and add-on settings are backed "
	"up. It starts after NVDA restarts. Then open the JAWS Migration Assistant again to bring over what needs it."
)


class ClassicSpeechOfferDialog(wx.Dialog):
	def __init__(self, parent, summary: str, detailsLabel: str, details: str, installLabel: str, automatic: bool = False):
		super().__init__(parent, title=f"{TITLE}: ClassicSpeech", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		sizer = wx.BoxSizer(wx.VERTICAL)
		text = wx.StaticText(self, label=summary)
		text.Wrap(TEXT_SIZE[0])
		sizer.Add(text, flag=wx.BOTTOM, border=6)
		# The label comes first, so NVDA names the text box after it.
		sizer.Add(wx.StaticText(self, label=detailsLabel))
		self.details = wx.TextCtrl(self, value=details, style=wx.TE_MULTILINE | wx.TE_READONLY, size=TEXT_SIZE)
		sizer.Add(self.details, proportion=1, flag=wx.EXPAND | wx.TOP, border=2)
		self.dontOffer = None
		if automatic:
			self.dontOffer = wx.CheckBox(self, label="&Don't offer this again when the assistant opens")
			sizer.Add(self.dontOffer, flag=wx.TOP, border=8)
		buttons = wx.BoxSizer(wx.HORIZONTAL)
		self.installButton = wx.Button(self, id=wx.ID_YES, label=installLabel)
		self.installButton.Bind(wx.EVT_BUTTON, lambda event: self.EndModal(wx.ID_YES))
		self.installButton.SetDefault()
		self.laterButton = wx.Button(self, id=wx.ID_CANCEL, label="&Not now")
		self.laterButton.Bind(wx.EVT_BUTTON, lambda event: self.EndModal(wx.ID_CANCEL))
		buttons.Add(self.installButton, flag=wx.RIGHT, border=8)
		buttons.Add(self.laterButton)
		sizer.Add(buttons, flag=wx.TOP | wx.ALIGN_RIGHT, border=8)
		outer = wx.BoxSizer(wx.VERTICAL)
		outer.Add(sizer, proportion=1, flag=wx.EXPAND | wx.ALL, border=BORDER)
		self.SetSizerAndFit(outer)
		self.CentreOnScreen()
		self.SetEscapeId(wx.ID_CANCEL)
		self.details.SetFocus()
		self.details.SetInsertionPoint(0)

	@property
	def dontOfferAgain(self) -> bool:
		return bool(self.dontOffer and self.dontOffer.GetValue())


def _ask(summary: str, detailsLabel: str, details: str, installLabel: str, automatic: bool) -> tuple[bool, bool]:
	import gui

	prePopup()
	try:
		dialog = ClassicSpeechOfferDialog(gui.mainFrame, summary, detailsLabel, details, installLabel, automatic)
		try:
			return dialog.ShowModal() == wx.ID_YES, dialog.dontOfferAgain
		finally:
			dialog.Destroy()
	finally:
		postPopup()


def _run(function, message: str):
	from .. import nvdaApply

	return nvdaApply.runWithProgress(function, message)


def _installNewest(reason: str) -> bool:
	"""Back up, download ClassicSpeech's newest release and install it. Main thread. True when installed."""
	from .. import migrator

	# NVDA's list of add-ons is read here, on its main thread; the backup and download run in the background.
	addons = nvdaEnv.installedAddons()
	folder = nvdaEnv.addonDataDir("downloads")

	def work():
		migrator._backupFirst(reason)
		return addonUpdates.fetchNewest([addonUpdates.CLASSIC_SPEECH_ID], folder, addons)

	try:
		fetched = _run(work, "Backing up NVDA's settings, then downloading the newest ClassicSpeech from GitHub. Please wait.")
	except Exception as error:
		debugLog.error("ClassicSpeech could not be downloaded")
		messageBox(f"ClassicSpeech was not installed, and nothing was changed: {error}", TITLE, wx.OK | wx.ICON_ERROR)
		return False
	messages, errors = addonUpdates.installDownloads(fetched.downloads)
	errors = fetched.errors + errors
	if errors:
		messageBox("ClassicSpeech was not installed: " + " ".join(errors), TITLE, wx.OK | wx.ICON_ERROR)
		return False
	if not messages:
		messageBox(" ".join(fetched.notes) or "ClassicSpeech is already up to date.", TITLE, wx.OK | wx.ICON_INFORMATION)
		return False
	if messageBox(
		" ".join(messages) + "\n\nNVDA's settings were backed up first. Restart NVDA now? After the restart, open the JAWS "
		"Migration Assistant again to bring your JAWS schemes, voice aliases and sounds into ClassicSpeech.",
		TITLE,
		wx.YES | wx.NO | wx.ICON_QUESTION,
	) == wx.YES:
		import core

		wx.CallLater(500, core.restart)
	return True


def offerInstall(automatic: bool = False) -> bool:
	"""Offer to install ClassicSpeech, which is missing. Main thread. True when it was installed.

	An automatic offer (as the assistant opens) is skipped once the user said not to offer it again.
	"""
	if automatic and state.get(DECLINED_KEY):
		return False
	install, dontOffer = _ask(
		"ClassicSpeech is not installed. Do you want to install its newest version now?",
		"&About ClassicSpeech:",
		EXPLANATION,
		"&Install ClassicSpeech",
		automatic,
	)
	if dontOffer:
		state.set(DECLINED_KEY, True)
	debugLog.note(f"ClassicSpeech offer ({'automatic' if automatic else 'asked for'}): {'install' if install else 'not now'}{', not again' if dontOffer else ''}")
	if not install:
		return False
	state.set(DECLINED_KEY, False)
	return _installNewest("Before installing ClassicSpeech")


def installOrUpdate() -> bool:
	"""Install ClassicSpeech, or update it to its newest release. Main thread. True when something was installed."""
	info = nvdaEnv.classicSpeechInfo()
	if not info.installed:
		return offerInstall(automatic=False)
	try:
		release = _run(addonUpdates.latestClassicSpeech, "Looking for the newest ClassicSpeech release on GitHub. Please wait.")
	except Exception as error:
		messageBox(f"The newest ClassicSpeech release could not be found: {error}", TITLE, wx.OK | wx.ICON_ERROR)
		return False
	installed = addonUpdates.installedVersions().get(addonUpdates.CLASSIC_SPEECH_ID.lower(), info.version)
	fetch, why = addonUpdates.decide(addonUpdates.CLASSIC_SPEECH_NAME, installed, release.version, addonUpdates.GITHUB)
	if not fetch:
		messageBox(why, TITLE, wx.OK | wx.ICON_INFORMATION)
		return False
	from .. import updater

	notes = updater.notesAsText(release.notes) or "This release has no notes."
	update, _dontOffer = _ask(
		f"ClassicSpeech {release.version} is available. You have version {installed}. Do you want to update it now?",
		"&What's new:",
		notes,
		"&Update ClassicSpeech",
		False,
	)
	if not update:
		return False
	return _installNewest(f"Before updating ClassicSpeech from {installed} to {release.version}")
