# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the MIT License.

"""JAWS's Insert+Control+V: the name and version of the program you are in; pressed twice, the version details.

The tester wrote (issue 29): "It should work like Jaws. insert control V says the product version. Pressing it twice
brings up the following. You can arrow and copy any or all of what you need." In Outlook, JAWS said "Microsoft
Outlook Subscription Version 16.0.20326.20158", and in Edge "Microsoft Edge Version 154.0.4258.37". NVDA has no such
command: NVDA+Control+V opens NVDA's speech settings, and NVDA+Control+F1 names the program's executable and NVDA's
app module for it, not its version.

JAWS's script (Default.jss, SayAppVersion and GetFocusedApplicationVersionInfo) says the focused program's name and
version, from the version information of the program's file (ProductName and ProductVersion, "%1 Version %2"), or
from the package of a Store app. Pressed twice, it shows the version details in JAWS's Virtual Viewer
(ShowVersionDetails, GetExtendedVersionDetailsInfo): "Version Details Information:", the program's version, JAWS's
version, its scripts' revision and serial number, the settings, program and configuration in use, the speech and
sounds scheme, and the version of Windows, a line each. JAWS's scripts for some programs name them their own way: in
File Explorer it says the version of Windows (explorer.jss), and Word, Outlook, PowerPoint and Access are "Microsoft",
JAWS's name for the program, then "Retail" or "Subscription", from Office's version (Office.jss and OfficeClassic.jss,
GetVersionInfoString and GetOfficePurchaseInfo). JAWS's Control+Insert+Windows+V puts the version details on the
clipboard (PutVersionDetailsOnClipboard) and says "Version Details Copied To Clipboard".

The assistant does the same with NVDA's facts. Once, NVDA says the program's name and version in JAWS's words, with
JAWS's rules for File Explorer and Office. The name and version are those NVDA's app module has for the program
(``productName`` and ``productVersion``: the version information of the program's file, or a Store app's package),
where JAWS takes them from too. Twice, NVDA shows the version details in a window it reads in browse mode, with a
Copy and a Close button: the arrow keys read them, Shift with the arrow keys selects, and Control+C copies, as in
JAWS's Virtual Viewer. They are JAWS's lines, with NVDA's version where JAWS has its own and the assistant's where
JAWS has its scripts' revision (NVDA has no serial number). The settings are NVDA's configuration profile in use, the
configuration is NVDA's app module for the program, the scheme is ClassicSpeech's while its speech and sounds schemes
are on, and the version of Windows is read from the registry as JAWS reads it (GetOSVersionInfo). Copying puts the
details on the clipboard, a line each, and NVDA says JAWS's words.

A migration gives these commands JAWS's keystrokes (see jawsKeyMap). Insert+Control+V is NVDA's keystroke for its
speech settings, so it gets the program's version only when the migration may take NVDA's keystrokes;
Control+Insert+Windows+V copies the version details either way. For a migration made before, those keystrokes are
added once after the update, the same way (see newKeys). NVDA+Shift+J, then V, Shift+V or Control+V do the same, and
each command can get a keystroke of its own in NVDA's Input Gestures dialog.
"""

from __future__ import annotations

import json

from . import debugLog

# -- JAWS's words and rules ---------------------------------------------------------------------------------------

#: The first line of the version details (common.jsm, cmsgVersionDetails).
VERSION_DETAILS = "Version Details Information:"
#: What JAWS says when it copies them (common.jsm, cmsgVersionDetailsCopiedToClipboard).
COPIED = "Version Details Copied To Clipboard"
#: A program's name and version (common.jsm, cmsg239_L: "%1 Version %2").
PRODUCT_VERSION = "{0} Version {1}"
#: Windows 10 and later (common.jsm, cmsgMicrosoftWindows10AndHigherVersionTemplate): its major version, DisplayVersion,
#: the update build revision (UBR), EditionID, CurrentBuild and the system type, as "%1 %4 Version %2 (OS Build %5.%3),
#: System Type %6" puts them.
WINDOWS_VERSION = "Microsoft Windows {0} {3} Version {1} (OS Build {4}.{2}), System Type {5}"
#: The settings, program and configuration in use (common.jsm, cmsgActiveConfigurationInfo, without the scheme's line,
#: which is left out where NVDA has no scheme).
CONFIGURATION = "Current settings: {0}.\nCurrent application: {1}.\nActive configuration: {2}."
SCHEME = "Current Speech and Sounds Scheme: {0}."
#: JAWS's name for what it uses where a program has nothing of its own (common.jsm, cmsg238_L).
DEFAULT = "Default"
#: How Office was bought (Office.jsm and Outlook.jsm, msgRetail and msgSubscription).
RETAIL = "{0} Retail"
SUBSCRIPTION = "{0} Subscription"
#: Office programs JAWS names "Microsoft" and its name for them (ConfigNames.ini), then how Office was bought: by the
#: name of NVDA's app module for them.
OFFICE_PROGRAMS = {"outlook": "Outlook", "winword": "Word", "powerpnt": "PowerPoint", "msaccess": "Access"}
#: Office 16 is retail before this update version (its third number), and a subscription from it (GetOfficePurchaseInfo,
#: officeMinorVersion < 6700); later Offices are subscriptions.
FIRST_SUBSCRIPTION_UPDATE = 6700
#: Programs for which JAWS says the version of Windows (explorer.jss, GetFocusedApplicationVersionInfo), by their app name.
WINDOWS_PROGRAMS = frozenset({"explorer"})
#: The processor architectures Windows names, and JAWS's names for them (HJConst.jsh, Architecture_x64 and
#: Architecture_arm64). JAWS names no other.
SYSTEM_TYPES = {"amd64": "x64", "x64": "x64", "arm64": "Arm64"}
#: Where Windows keeps its version (GetOSVersionInfo).
CURRENT_VERSION_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
WINDOWS_VALUES = ("CurrentMajorVersionNumber", "CurrentBuild", "DisplayVersion", "EditionID", "UBR")
#: Windows 11's first build: Windows says 10.0 for it too.
FIRST_WINDOWS_11_BUILD = 22000

# -- the assistant's own words ------------------------------------------------------------------------------------

#: The window's title: JAWS's Virtual Viewer has none, and NVDA's window needs one.
TITLE = "Version Details"
NVDA_VERSION = "NVDA version {0}"
ASSISTANT_VERSION = "JAWS Migration Assistant version {0}"
#: A program whose file has no version.
NO_VERSION = "unknown"
NOT_COPIED = "The version details could not be copied to the clipboard."
NOT_SHOWN = "The version details could not be shown. The assistant's debug log says why."


def _log():
	from logHandler import log

	return log


# -- the version of Windows ---------------------------------------------------------------------------------------


def readWindowsValues() -> dict:
	"""The values of Windows's version in the registry that JAWS reads (GetOSVersionInfo); a missing one is left out."""
	import winreg

	values = {}
	with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CURRENT_VERSION_KEY) as key:
		for name in WINDOWS_VALUES:
			try:
				values[name] = winreg.QueryValueEx(key, name)[0]
			except OSError:
				pass
	return values


def processorArchitecture() -> str:
	"""The computer's processor architecture as NVDA names it (winVersion), such as ``AMD64`` or ``ARM64``."""
	try:
		import winVersion

		architecture = winVersion.getWinVer().processorArchitecture
		if architecture:
			return str(architecture)
	except Exception:
		pass
	import platform

	return platform.machine()


def systemType(architecture: str | None = None) -> str:
	"""JAWS's name for the processor architecture: ``x64`` or ``Arm64``, else nothing (GetSystemType)."""
	if architecture is None:
		architecture = processorArchitecture()
	return SYSTEM_TYPES.get(str(architecture or "").lower(), "")


def windowsVersion(values: dict | None = None, architecture: str | None = None) -> str:
	"""The version of Windows, as JAWS says it: "Microsoft Windows 11 Professional Version 25H2 (OS Build 26200.9457),
	System Type x64". ``values`` are the registry's (``readWindowsValues``) and ``architecture`` NVDA's name for the
	processor, read from the computer when None."""
	if values is None:
		values = readWindowsValues()
	build = str(values.get("CurrentBuild") or "")
	major = values.get("CurrentMajorVersionNumber") or 10
	windows = "11" if build.isdigit() and int(build) >= FIRST_WINDOWS_11_BUILD else str(major)
	return WINDOWS_VERSION.format(
		windows,
		values.get("DisplayVersion") or "",
		values.get("UBR") or 0,
		values.get("EditionID") or "",
		build,
		systemType(architecture),
	)


# -- the program's version ----------------------------------------------------------------------------------------


def officeName(name: str, version: str) -> str:
	"""``name`` with how Office was bought, from Office's ``version``, as JAWS's scripts for Office say it."""
	parts = str(version or "").split(".")
	try:
		major = int(parts[0])
		update = int(parts[2]) if len(parts) > 2 else 0
	except ValueError:
		return name
	if major < 16:
		return name
	if major == 16 and update < FIRST_SUBSCRIPTION_UPDATE:
		return RETAIL.format(name)
	return SUBSCRIPTION.format(name)


def _appName(appModule) -> str:
	try:
		return str(getattr(appModule, "appName", "") or "")
	except Exception:
		return ""


def productInfo(appModule) -> tuple[str, str]:
	"""The program's name and version as NVDA's app module has them, or its app name and nothing when it has none."""
	name = version = ""
	try:
		name = str(appModule.productName or "")
		version = str(appModule.productVersion or "")
	except Exception:
		# NVDA can't read them, as for a program whose file has no version information.
		_log().debugWarning("jawsMigrator: no product name and version for %r" % (appModule,), exc_info=True)
	return name.strip() or _appName(appModule), version.strip()


def programVersion(appModule) -> str:
	"""What JAWS's Insert+Control+V says once for the program of ``appModule``."""
	appName = _appName(appModule).lower()
	if appName in WINDOWS_PROGRAMS:
		return windowsVersion()
	name, version = productInfo(appModule)
	office = OFFICE_PROGRAMS.get(appName)
	if office:
		name = officeName(f"Microsoft {office}", version)
	return PRODUCT_VERSION.format(name, version or NO_VERSION)


# -- the version details ------------------------------------------------------------------------------------------


def nvdaVersion() -> str:
	"""NVDA's version, as NVDA's About dialog gives it: "2026.2 (2026.2.0.57664)"."""
	import buildVersion

	version = str(buildVersion.version)
	detailed = str(getattr(buildVersion, "version_detailed", "") or "")
	return f"{version} ({detailed})" if detailed and detailed != version else version


def assistantVersion() -> str:
	import addonHandler

	return str(addonHandler.getCodeAddon().manifest["version"])


def settingsInUse() -> str:
	"""NVDA's configuration profile in use, or its normal configuration."""
	from . import nvdaApply

	return nvdaApply.writingConfigurationName()


def executableName(focus) -> str:
	"""The program's executable, as NVDA+Control+F1 names it (``OUTLOOK.EXE``)."""
	import appModuleHandler

	return appModuleHandler.getAppNameFromProcessID(focus.processID, True)


def appModuleName(appModule) -> str:
	"""NVDA's app module for the program, as NVDA+Control+F1 names it, or JAWS's "Default" where NVDA has none."""
	import appModuleHandler

	base = appModuleHandler.AppModule
	if isinstance(appModule, base) and type(appModule) is not base:
		return appModule.appModuleName.split(".")[0]
	return DEFAULT


def classicSpeechScheme() -> str:
	"""ClassicSpeech's active speech and sounds scheme, or nothing when it doesn't run or its schemes are off."""
	from . import nvdaApply

	if not nvdaApply.classicSpeechRunning():
		return ""
	data = json.loads(nvdaApply.classicSpeechSection().get("schemeData") or "{}")
	if not isinstance(data, dict) or not data.get("enabled", True):
		return ""
	return str(data.get("activeScheme") or "").strip()


def _schemeLine() -> str:
	scheme = classicSpeechScheme()
	return SCHEME.format(scheme) if scheme else ""


def details(focus=None) -> str:
	"""The version details, a line each, as JAWS's Insert+Control+V shows them pressed twice.

	A line that can't be worked out is left out, as JAWS leaves out a blank one.
	"""
	if focus is None:
		import api

		focus = api.getFocusObject()
	appModule = getattr(focus, "appModule", None)
	lines = [VERSION_DETAILS]

	def add(what: str, line) -> None:
		try:
			text = line()
		except Exception:
			debugLog.error(f"could not work out {what} for the version details")
			return
		if text:
			lines.append(text)

	add("the program's version", lambda: programVersion(appModule))
	add("NVDA's version", lambda: NVDA_VERSION.format(nvdaVersion()))
	add("the assistant's version", lambda: ASSISTANT_VERSION.format(assistantVersion()))
	add("the settings in use", lambda: CONFIGURATION.format(settingsInUse(), executableName(focus), appModuleName(appModule)))
	add("ClassicSpeech's scheme", _schemeLine)
	add("the version of Windows", windowsVersion)
	return "\n".join(lines)


# -- the commands -------------------------------------------------------------------------------------------------


def _say(message: str) -> None:
	import ui

	ui.message(message)


def sayVersion(focus=None) -> str:
	"""JAWS's Insert+Control+V, pressed once: the name and version of the program you are in."""
	if focus is None:
		import api

		focus = api.getFocusObject()
	message = programVersion(getattr(focus, "appModule", None))
	_say(message)
	return message


def showDetails(focus=None) -> bool:
	"""JAWS's Insert+Control+V, pressed twice: the version details, in a window to read and copy."""
	text = details(focus)
	try:
		import ui

		try:
			ui.browseableMessage(text, TITLE, copyButton=True, closeButton=True)
		except TypeError:
			# An NVDA whose window has no buttons.
			ui.browseableMessage(text, TITLE)
	except Exception:
		debugLog.error("could not show the version details")
		_say(NOT_SHOWN)
		return False
	return True


def copyDetails(focus=None) -> bool:
	"""JAWS's Control+Insert+Windows+V: the version details on the clipboard, a line each, and JAWS's words."""
	text = details(focus)
	try:
		import api

		# Windows programs take \r\n as a line break; api.copyToClip checks the clipboard holds just that.
		copied = bool(api.copyToClip(text.replace("\n", "\r\n")))
	except Exception:
		debugLog.error("could not copy the version details to the clipboard")
		copied = False
	_say(COPIED if copied else NOT_COPIED)
	return copied


def sayOrShow(repeatCount: int, focus=None) -> None:
	"""Insert+Control+V: once, the program's version; twice, the version details, as JAWS's SayAppVersion does."""
	if repeatCount:
		showDetails(focus)
	else:
		sayVersion(focus)
