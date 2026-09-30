# Unit tests for version 1.30, from a tester's issue 29, "copy product version": "It should work like Jaws. insert
# control V says the product version. Pressing it twice brings up the following. You can arrow and copy any or all of
# what you need." JAWS's version details in Outlook and in Edge followed, and: "also test it works anywhere edge or any
# program. ... Have it test with Jaws." NVDA 2026.2 has no such command: NVDA+Control+V opens NVDA's speech settings.
# - appVersion: JAWS's SayAppVersion, ShowVersionDetails and PutVersionDetailsOnClipboard (Default.jss), in JAWS's
#   words (common.jsm), with its rules for File Explorer (explorer.jss) and Office (Office.jss, OfficeClassic.jss).
# - jawsKeyMap: a migration gives JAWS's keystrokes for them to the assistant's commands, Insert+Control+V only where it
#   may take NVDA's own keystrokes; newKeys adds them once, the same way, for a migration made before.
# JAWS 2026's own files are read where JAWS is installed, to check that the words, rules and keystrokes are JAWS's (JAWS
# itself isn't run). NVDA 2026.2's own code runs here word for word (see NvdasOwnCodeTests), on this computer's real
# programs: fileUtils.getFileVersionInfo with its Wow64 decorator, AppModule's processExecutablePath,
# _getExecutableFileInfo, _getImmersivePackageInfo, _setProductInfo, productName, productVersion and appModuleName,
# appModuleHandler's getProcessHandleFromProcessId and getAppNameFromProcessID, winKernel.openProcess and
# GlobalCommands.script_reportAppModuleInfo, with the ctypes prototypes of winBindings; and, for the keys,
# scriptHandler's _findScript, _yieldObjectsForFindScript, _getObjScript, getGlobalMapScripts, executeScript and
# getLastScriptRepeatCount, with inputCore's GlobalGestureMap and normalizeGestureIdentifier. ui.message, speech.speak
# and api.copyToClip are NVDA's own, from test_v129_speechHistory, on Windows' real clipboard. What is imitated: the
# tester's Outlook (not on this computer), NVDA's browseable message window (a record of what NVDA was asked to show),
# NVDA's own NVDA+Control+V (its speech settings), and Wow64 redirection, which a 64-bit NVDA doesn't have. The
# assistant's code is the real one.
# Run: python -m unittest tests.test_v130_appVersion -v

import array
import contextlib
import ctypes
import functools
import json
import logging
import os
import re
import sys
import tempfile
import threading
import time
import types
import unittest
import weakref
from abc import ABCMeta, abstractproperty
from ctypes import POINTER, WINFUNCTYPE, Structure, c_size_t, c_uint, windll
from ctypes.wintypes import BOOL, DWORD, HANDLE, LONG, LPCVOID, LPCWSTR, LPDWORD, LPVOID, LPWSTR, PDWORD, PUINT, WCHAR
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import test_keys  # noqa: E402  (imitation NVDA classes that bind NVDA's own gestures)
import test_v128_startupFocus as v128  # noqa: E402  (NVDA's baseObject, nvdaCode and nvdaClass)
import test_v129_speechHistory as v129  # noqa: E402  (NVDA's ui.message, speech.speak and api.copyToClip)

import jawsMigrator  # noqa: E402
from jawsMigrator import appVersion, jawsFiles, jawsKeyMap, keyPlan, migrator, newKeys, nvdaApply, state  # noqa: E402

# -- NVDA 2026.2's own code, word for word (see NvdasOwnCodeTests) -----------------------------------------------

#: NVDA 2026.2, source/winBindings/version.py: GetFileVersionInfoSize, GetFileVersionInfo and VerQueryValue.
NVDA_VERSION_BINDINGS = r'''
GetFileVersionInfoSize = WINFUNCTYPE(None)(("GetFileVersionInfoSizeW", dll))
"""
Determines whether the operating system can retrieve version information for a specified file.

.. seealso::
	https://learn.microsoft.com/en-us/windows/win32/api/winver/nf-winver-getfileversioninfosizew
"""


GetFileVersionInfoSize.restype = DWORD


GetFileVersionInfoSize.argtypes = (
	LPCWSTR,  # lptstrFilename: Pointer to a null-terminated string that specifies the name of the file
	LPDWORD,  # lpdwHandle: Pointer to a variable that the function sets to zero (can be NULL)
)


GetFileVersionInfo = WINFUNCTYPE(None)(("GetFileVersionInfoW", dll))
"""
Retrieves version information for the specified file.

.. seealso::
	https://learn.microsoft.com/en-us/windows/win32/api/winver/nf-winver-getfileversioninfow
"""


GetFileVersionInfo.restype = BOOL


GetFileVersionInfo.argtypes = (
	LPCWSTR,  # lptstrFilename: Pointer to a null-terminated string that specifies the name of the file
	DWORD,  # dwHandle: This parameter is ignored
	DWORD,  # dwLen: Specifies the size, in bytes, of the buffer pointed to by the lpData parameter
	LPVOID,  # lpData: Pointer to a buffer that receives the file-version information
)


VerQueryValue = WINFUNCTYPE(None)(("VerQueryValueW", dll))
"""
Retrieves specified version information from the specified version-information resource.

.. seealso::
	https://learn.microsoft.com/en-us/windows/win32/api/winver/nf-winver-verqueryvaluew
"""


VerQueryValue.restype = BOOL


VerQueryValue.argtypes = (
	LPCVOID,  # pBlock: Pointer to the buffer containing the version-information resource
	LPCWSTR,  # lpSubBlock: Pointer to a null-terminated string that specifies the version-information value to retrieve
	POINTER(
		LPVOID,
	),  # lplpBuffer: When the function returns, points to the address of the requested version information
	PUINT,  # puLen: When the function returns, points to the length, in characters, of the requested version information
)
'''

#: NVDA 2026.2, source/winBindings/kernel32.py: CloseHandle, OpenProcess, GetPackageFullName,
#: QueryFullProcessImageName, CreateToolhelp32Snapshot, PROCESSENTRY32W, Process32First and Process32Next.
NVDA_KERNEL32_BINDINGS = r'''
CloseHandle = WINFUNCTYPE(None)(("CloseHandle", dll))
"""
Closes an open object handle. The handle must have been created by the calling process.
.. seealso::
	https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-closehandle
"""


CloseHandle.argtypes = (HANDLE,)


CloseHandle.restype = BOOL


OpenProcess = WINFUNCTYPE(None)(("OpenProcess", dll))
"""
Opens an existing local process object.
.. seealso::
	https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocess
"""


OpenProcess.argtypes = (
	DWORD,  # dwDesiredAccess
	BOOL,  # bInheritHandle
	DWORD,  # dwProcessId
)


OpenProcess.restype = HANDLE


GetPackageFullName = WINFUNCTYPE(None)(("GetPackageFullName", dll))
"""
Gets the package full name for the specified process.

.. seealso::
	https://learn.microsoft.com/en-us/windows/win32/api/appmodel/nf-appmodel-getpackagefullname
"""


GetPackageFullName.argtypes = (
	HANDLE,  # hProcess: A handle to the process
	POINTER(c_uint),  # packageFullNameLength: On input, the size of the packageFullName buffer
	LPWSTR,  # packageFullName: The package full name
)


GetPackageFullName.restype = LONG


QueryFullProcessImageName = WINFUNCTYPE(None)(("QueryFullProcessImageNameW", dll))
"""
Retrieves the full name of the executable image for the specified process.

.. seealso::
	https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-queryfullprocessimagenamew
"""


QueryFullProcessImageName.argtypes = (
	HANDLE,  # hProcess: A handle to the process
	DWORD,  # dwFlags: Flags that control the operation
	LPWSTR,  # lpExeName: The path to the executable image
	PDWORD,  # lpdwSize: On input, specifies the size of the lpExeName buffer
)


QueryFullProcessImageName.restype = BOOL


CreateToolhelp32Snapshot = WINFUNCTYPE(None)(("CreateToolhelp32Snapshot", dll))
"""
Takes a snapshot of the specified processes, as well as the heaps, modules, and threads used by these processes.

.. seealso::
	https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-createtoolhelp32snapshot
"""


CreateToolhelp32Snapshot.argtypes = (
	DWORD,  # dwFlags: The portions of the system to be included in the snapshot
	DWORD,  # th32ProcessID: The process identifier of the process to be included in the snapshot
)


CreateToolhelp32Snapshot.restype = HANDLE


class PROCESSENTRY32W(Structure):
	"""See https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/ns-tlhelp32-processentry32w"""

	_fields_ = [
		("dwSize", DWORD),
		("cntUsage", DWORD),
		("th32ProcessID", DWORD),
		("th32DefaultHeapID", ULONG_PTR),
		("th32ModuleID", DWORD),
		("cntThreads", DWORD),
		("th32ParentProcessID", DWORD),
		("pcPriClassBase", LONG),
		("dwFlags", DWORD),
		("szExeFile", WCHAR * 260),
	]


Process32First = WINFUNCTYPE(None)(("Process32FirstW", dll))
"""
Retrieves information about the first process encountered in a system snapshot.

.. seealso::
	https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-process32firstw
"""


Process32First.argtypes = (
	HANDLE,  # hSnapshot: A handle to the snapshot returned from CreateToolhelp32Snapshot
	POINTER(PROCESSENTRY32W),  # lppe: A pointer to a PROCESSENTRY32 structure
)


Process32First.restype = BOOL


Process32Next = WINFUNCTYPE(None)(("Process32NextW", dll))
"""
Retrieves information about the next process recorded in a system snapshot.

.. seealso::
	https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-process32nextw
"""


Process32Next.argtypes = (
	HANDLE,  # hSnapshot: A handle to the snapshot returned from CreateToolhelp32Snapshot
	POINTER(PROCESSENTRY32W),  # lppe: A pointer to a PROCESSENTRY32 structure
)


Process32Next.restype = BOOL
'''

#: NVDA 2026.2, source/fileUtils.py: getFileVersionInfo, with the decorator that suspends Wow64 redirection.
NVDA_FILE_VERSION_INFO = r'''
def _suspendWow64RedirectionForFileInfoRetrieval(func):
	"""
	This decorator checks if the file provided as a `filePath`
	is placed in a system32 directory, and if for the current system system32
	redirects 32-bit processes such as NVDA to a different syswow64 directory
	disables redirection for the duration of the function call.
	This is necessary when fetching file version info since NVDA is a 32-bit application
	and without redirection disabled we would either access a wrong file or not be able to access it at all.
	"""

	@wraps(func)
	def funcWrapper(filePath, *attributes):
		nativeSys32 = shlobj.SHGetKnownFolderPath(shlobj.FolderId.SYSTEM)
		if (
			systemUtils.hasSyswow64Dir()
			# Path's returned from `appModule.appPath` and `shlobj.SHGetKnownFolderPath` often differ in case
			and filePath.casefold().startswith(nativeSys32.casefold())
		):
			with winKernel.suspendWow64Redirection():
				return func(filePath, *attributes)
		else:
			return func(filePath, *attributes)

	return funcWrapper


@_suspendWow64RedirectionForFileInfoRetrieval
def getFileVersionInfo(name: str, *attributes: str) -> dict[str, str | None]:
	"""
	Gets the specified file version info attributes from the provided file.
	:param name: The path to the file to get version info from.
	:param attributes: The list of attributes to get. E.g. "FileVersion", "ProductVersion"
	:return: A dictionary mapping the provided attributes to their values.
	If an attribute is not found or invalid, its value will be None.

	:raises RuntimeError: If the file does not exist, has no version information, or has no codepage.
	"""
	if not os.path.exists(name):
		raise RuntimeError("The file %s does not exist" % name)
	fileVersionInfo = {}
	# Get size needed for buffer (0 if no info)
	size = winBindings.version.GetFileVersionInfoSize(name, None)
	if not size:
		raise RuntimeError("No version information")
	# Create buffer
	res = ctypes.create_string_buffer(size)
	# Load file informations into buffer res
	winBindings.version.GetFileVersionInfo(name, 0, size, res)
	r = ctypes.c_void_p()
	l = ctypes.c_uint()  # noqa: E741
	# Look for codepages
	winBindings.version.VerQueryValue(
		res,
		"\\VarFileInfo\\Translation",
		ctypes.byref(r),
		ctypes.byref(l),
	)
	if not l.value:
		raise RuntimeError("No codepage")
	# Take the first codepage (what else ?)
	codepage = array.array("H", ctypes.string_at(r.value, 4))
	codepage = "%04x%04x" % tuple(codepage)
	for attr in attributes:
		if not winBindings.version.VerQueryValue(
			res,
			"\\StringFileInfo\\%s\\%s" % (codepage, attr),
			ctypes.byref(r),
			ctypes.byref(l),
		):
			log.warning("Invalid or unavailable version info attribute for %r: %s" % (name, attr))
			fileVersionInfo[attr] = None
		else:
			fileVersionInfo[attr] = ctypes.wstring_at(r.value, l.value - 1)
	return fileVersionInfo
'''

#: NVDA 2026.2, source/winKernel.py: openProcess and the access it asks for.
NVDA_OPEN_PROCESS = r'''
SYNCHRONIZE = 0x100000


PROCESS_QUERY_INFORMATION = 0x400


def openProcess(*args) -> int:
	try:
		return winBindings.kernel32.OpenProcess(*args) or 0
	except Exception:
		# Compatibility: error should just be a handle of 0.
		return 0
'''

#: NVDA 2026.2, source/appModuleHandler.py: getProcessHandleFromProcessId, which gives an app module its process.
NVDA_PROCESS_HANDLE = r'''
def getProcessHandleFromProcessId(processId: int, fallBackToTopLevelWindowEnumeration: bool = True) -> int:
	"""
	Get a process handle for the given process ID.

	This function attempts to open a process handle using the Windows API. If the direct
	approach fails and fallback is enabled, it will attempt to find a top-level window
	belonging to the process and derive the process handle from that window.

	:param processId: The ID of the process for which to obtain a handle
	:param fallBackToTopLevelWindowEnumeration: Whether to attempt window enumeration
		as a fallback method if direct process opening fails. Defaults to True
	:return: A handle to the process, or 0 if no handle could be obtained
	"""
	processHandle: int = 0
	try:
		if not (
			processHandle := winKernel.openProcess(
				winKernel.SYNCHRONIZE | winKernel.PROCESS_QUERY_INFORMATION,
				False,
				processId,
			)
		):
			raise ctypes.WinError()
	except WindowsError:
		log.debugWarning(f"Unable to open process for processId {processId}", exc_info=True)
	else:
		return processHandle

	if fallBackToTopLevelWindowEnumeration:
		try:
			if not (
				foundWindowHandle := _findTopLevelWindow(
					lambda hwnd: _getWindowThreadProcessID(hwnd)[0] == processId,
				)
			):
				raise RuntimeError(f"No window handle found for process {processId} to create process handle")
			if not (processHandle := _getProcessHandleFromHwnd(foundWindowHandle)):
				raise ctypes.WinError()
		except (WindowsError, RuntimeError):
			log.debugWarning(
				f"Unable to get process handle for process {processId} using window enumeration "
				"and subsequently getting process handle from that window",
				exc_info=True,
			)

	return processHandle
'''

#: NVDA 2026.2, source/appModuleHandler.py: getAppNameFromProcessID, the executable NVDA+Control+F1 names.
NVDA_APP_NAME = r'''
def getAppNameFromProcessID(processID: int, includeExt: bool = False) -> str:
	"""Finds out the application name of the given process.
	@param processID: the ID of the process handle of the application you wish to get the name of.
	@param includeExt: C{True} to include the extension of the application's executable filename,
	C{False} to exclude it.
	@returns: application name
	"""
	if processID == globalVars.appPid:
		return "nvda.exe" if includeExt else "nvda"
	FSnapshotHandle = winBindings.kernel32.CreateToolhelp32Snapshot(2, 0)
	FProcessEntry32 = winBindings.kernel32.PROCESSENTRY32W()
	FProcessEntry32.dwSize = ctypes.sizeof(FProcessEntry32)
	ContinueLoop = winBindings.kernel32.Process32First(FSnapshotHandle, ctypes.byref(FProcessEntry32))
	appName = str()
	while ContinueLoop:
		if FProcessEntry32.th32ProcessID == processID:
			appName = FProcessEntry32.szExeFile
			break
		ContinueLoop = winBindings.kernel32.Process32Next(FSnapshotHandle, ctypes.byref(FProcessEntry32))
	winBindings.kernel32.CloseHandle(FSnapshotHandle)
	if not includeExt:
		appName = os.path.splitext(appName)[0].lower()
	if not appName:
		return appName

	# This might be an executable which hosts multiple apps.
	# Try querying the app module for the name of the app being hosted.
	try:
		return _importAppModuleForExecutable(appName).getAppNameFromHost(processID)
	except (AttributeError, LookupError):
		pass
	return appName
'''

#: NVDA 2026.2, source/appModuleHandler.py, class AppModule: the program's executable, name and version.
NVDA_APP_MODULE = r'''
def _get_processExecutablePath(self) -> str:
	# Create the buffer to get the executable name
	exeFileName = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
	length = ctypes.wintypes.DWORD(ctypes.wintypes.MAX_PATH)
	if not winBindings.kernel32.QueryFullProcessImageName(
		self.processHandle,
		0,
		exeFileName,
		ctypes.byref(length),
	):
		raise ctypes.WinError()
	return exeFileName.value


def _getExecutableFileInfo(self):
	# Used for obtaining file name and version for the executable.
	# This is needed in case immersive app package returns an error,
	# dealing with a native app, or a converted desktop app.
	fileinfo = getFileVersionInfo(self.processExecutablePath, "ProductName", "ProductVersion")
	return (fileinfo["ProductName"], fileinfo["ProductVersion"])


def _getImmersivePackageInfo(self):
	# Used to obtain full package structure for a hosted app.
	# The package structure consists of product name, version, architecture, language, and app ID.
	# This is useful for confirming whether an app is hosted or not despite an app reporting otherwise.
	# Some apps such as File Explorer says it is an immersive process but error 15700 is shown.
	# Others such as Store version of Office are not truly hosted apps but are distributed via Store.
	length = ctypes.c_uint()
	winBindings.kernel32.GetPackageFullName(self.processHandle, ctypes.byref(length), None)
	packageFullName = ctypes.create_unicode_buffer(length.value)
	if (
		winBindings.kernel32.GetPackageFullName(
			self.processHandle,
			ctypes.byref(length),
			packageFullName,
		)
		== 0
	):
		return packageFullName.value
	else:
		return None


def _setProductInfo(self):
	"""Set productName and productVersion attributes.
	There are at least two ways of obtaining product info for an app:
	* Package info for hosted apps
	* File version info for other apps and for some hosted apps
	"""
	# Sometimes (I.E. when NVDA starts) handle is 0, so stop if it is the case
	if not self.processHandle:
		raise RuntimeError("processHandle is 0")
	# Some apps such as File Explorer says it is an immersive process but error 15700 is shown.
	# Therefore resort to file version info behavior because it is not a hosted app.
	# Others such as Store version of Office are not truly hosted apps,
	# yet returns an internal version anyway because they are converted desktop apps.
	# For immersive apps, default implementation is generic - returns Windows version information.
	# Thus probe package full name and parse the serialized representation of package info structure.
	packageInfo = self._getImmersivePackageInfo()
	if packageInfo is not None:
		# Product name is of the form publisher.name for a hosted app.
		productInfo = packageInfo.split("_")
	else:
		# File Explorer and friends which are really native aps.
		# Also includes converted desktop apps such as Office.
		productInfo = self._getExecutableFileInfo()
	self.productName = productInfo[0]
	self.productVersion = productInfo[1]


def _get_productName(self):
	self._setProductInfo()
	return self.productName


def _get_productVersion(self):
	self._setProductInfo()
	return self.productVersion


def _get_appModuleName(self):
	return self.__class__.__module__.split(".")[-1]
'''

#: NVDA 2026.2, source/globalCommands.py, class GlobalCommands: NVDA+Control+F1.
NVDA_REPORT_APP_MODULE_INFO = r'''
@script(
	description=_(
		# Translators: Input help mode message for report current program name and app module name command.
		"Speaks the filename of the active application along with the name of the currently loaded appModule",
	),
	category=SCRCAT_TOOLS,
	gesture="kb:NVDA+control+f1",
	speakOnDemand=True,
)
def script_reportAppModuleInfo(self, gesture):
	focus = api.getFocusObject()
	message = ""
	mod = focus.appModule
	if isinstance(mod, appModuleHandler.AppModule) and type(mod) is not appModuleHandler.AppModule:
		# Translators: Indicates the name of the appModule for the current program (example output: explorer module is loaded).
		# This message will not be presented if there is no module for the current program.
		message = _(" %s module is loaded. ") % mod.appModuleName.split(".")[0]
	appName = appModuleHandler.getAppNameFromProcessID(focus.processID, True)
	# Translators: Indicates the name of the current program (example output: explorer.exe is currently running).
	# Note that it does not give friendly name such as Windows Explorer; it presents the file name of the current application.
	# For example, the complete message for Windows explorer is: "explorer module is loaded. Explorer.exe is currenty running."
	message += _(" %s is currently running.") % appName
	ui.message(message)
'''

#: NVDA 2026.2, source/scriptHandler.py: how NVDA finds the command for a key, runs it, and counts its presses.
NVDA_SCRIPT_HANDLER = r'''
_lastScriptTime = 0  # Time in MS of when the last script was executed


_lastScriptRef = None  # Holds a weakref to the last script that was executed


_lastScriptCount = 0  # The amount of times the last script was repeated


_isScriptRunning = False


def _getObjScript(
	obj: "NVDAObjects.NVDAObject",
	gesture: "inputCore.InputGesture",
	globalMapScripts: List["inputCore.InputGestureScriptT"],
) -> Optional[_ScriptFunctionT]:
	"""
	@param globalMapScripts: An ordered list of scripts.
	The list is ordered by resolution priority,
	the first map in the list should be used to resolve the script first.
	"""
	# Search the scripts from the global gesture maps.
	for cls, scriptName in globalMapScripts:
		if isinstance(obj, cls):
			if scriptName is None:
				# The global map specified that no script should execute for this gesture and object.
				return None
			if scriptName.startswith("kb:"):
				# Emulate a key press.
				return _makeKbEmulateScript(scriptName)
			try:
				return getattr(obj, "script_%s" % scriptName)
			except AttributeError:
				pass

	try:
		# Search the object itself for in-built bindings.
		return obj.getScript(gesture)
	except Exception:  # Prevent a faulty add-on from breaking script handling altogether (#5446)
		log.exception()


def getGlobalMapScripts(gesture: "inputCore.InputGesture") -> List["inputCore.InputGestureScriptT"]:
	"""
	@returns: An ordered list of scripts.
	The list is ordered by resolution priority,
	the first map in the list should be used to resolve scripts first.
	"""
	globalMapScripts: List["inputCore.InputGestureScriptT"] = []
	globalMaps = [inputCore.manager.userGestureMap, inputCore.manager.localeGestureMap]
	globalMap = braille.handler.display.gestureMap if braille.handler and braille.handler.display else None
	if globalMap:
		globalMaps.append(globalMap)
	for globalMap in globalMaps:
		for identifier in gesture.normalizedIdentifiers:
			globalMapScripts.extend(globalMap.getScriptsForGesture(identifier))
	return globalMapScripts


def _findScript(gesture: "inputCore.InputGesture") -> Optional[_ScriptFunctionT]:
	focus = api.getFocusObject()
	if not focus:
		return None

	globalMapScripts = getGlobalMapScripts(gesture)

	for obj, filterFunc in _yieldObjectsForFindScript(gesture):
		if obj:
			func = _getObjScript(obj, gesture, globalMapScripts)
			if filterFunc is not None:
				func = filterFunc(func, obj, gesture)
			if func:
				return func

	return None


def _yieldObjectsForFindScript(
	gesture: "inputCore.InputGesture",
) -> Generator[Tuple["NVDAObjects.NVDAObject", Optional[_ScriptFilterT]], None, None]:
	"""
	This generator is used to determine which NVDAObject to perform an input gesture on,
	in order of priority.
	For example, if the first yielded object has an associated script for the given gesture, findScript
	will use that script.
	@yields: A tuple, which includes
	 - an NVDAObject, to check if there is an associated script
	 - an optional function to handle any further filtering required after checking for an associated script
	"""
	# Import late to avoid circular import.
	# We need to import this here because this might be the first import of this module
	# and it might be needed by global maps.
	import globalCommands

	focus = api.getFocusObject()

	# Gesture specific scriptable object
	yield gesture.scriptableObject, None
	# Global plugins
	yield from ((p, None) for p in globalPluginHandler.runningPlugins)
	# App module
	yield focus.appModule, None

	# Braille display
	if braille.handler and isinstance(braille.handler.display, baseObject.ScriptableObject):
		yield braille.handler.display, None

	# Vision enhancement provider
	if vision.handler:
		for provider in vision.handler.getActiveProviderInstances():
			if isinstance(provider, baseObject.ScriptableObject):
				yield provider, None

	# Tree interceptor
	treeInterceptor = focus.treeInterceptor
	if treeInterceptor and treeInterceptor.isReady:
		yield treeInterceptor, _getTreeModeInterceptorScript

	# NVDAObject
	yield focus, None

	# Focus ancestors
	yield from ((a, _getFocusAncestorScript) for a in reversed(api.getFocusAncestors()))

	# Configuration profile activation scripts
	yield globalCommands.configProfileActivationCommands, None
	# Global commands
	yield globalCommands.commands, None


def executeScript(script, gesture):
	"""Executes a given script (function) passing it the given gesture.
	It also keeps track of the execution of duplicate scripts with in a certain amount of time, and counts how many times this happens.
	Use L{getLastScriptRepeatCount} to find out this count value.
	@param script: the function or method that should be executed. The function or method must take an argument of 'gesture'. This must be the same value as gesture.script, but its passed in here purely for performance.
	@type script: callable.
	@param gesture: the input gesture that activated this script
	@type gesture: L{inputCore.InputGesture}
	"""
	global _lastScriptTime, _lastScriptCount, _lastScriptRef, _isScriptRunning
	lastScriptRef = _lastScriptRef() if _lastScriptRef else None
	# We don't allow the same script to be executed from with in itself, but we still should pass the key through
	scriptFunc = getattr(script, "__func__", script)
	if _isScriptRunning and lastScriptRef == scriptFunc:
		return gesture.send()
	_isScriptRunning = True
	resumeSayAllMode = None
	if willSayAllResume(gesture):
		resumeSayAllMode = sayAll.SayAllHandler.lastSayAllMode
	try:
		scriptTime = time.time()
		scriptRef = weakref.ref(scriptFunc)
		timeDiffMs = (scriptTime - _lastScriptTime) * 1000
		if timeDiffMs <= config.conf["keyboard"]["multiPressTimeout"] and scriptFunc == lastScriptRef:
			_lastScriptCount += 1
		else:
			_lastScriptCount = 0
		_lastScriptRef = scriptRef
		_lastScriptTime = scriptTime
		script(gesture)
	except:  # noqa: E722
		log.exception("error executing script: %s with gesture %r" % (script, gesture.displayName))
	finally:
		_isScriptRunning = False
		if resumeSayAllMode is not None:
			sayAll.SayAllHandler.readText(resumeSayAllMode, startedFromScript=None)


def getLastScriptRepeatCount():
	"""The count of how many times the most recent script has been executed.
	This should only be called from with in a script.
	@returns: a value greater or equal to 0. If the script has not been repeated it is 0, if it has been repeated once its 1, and so forth.
	@rtype: integer
	"""
	if (time.time() - _lastScriptTime) * 1000 > config.conf["keyboard"]["multiPressTimeout"]:
		return 0
	else:
		return _lastScriptCount
'''

#: NVDA 2026.2, source/inputCore.py, class GlobalGestureMap: gestures.ini's bindings, as NVDA holds them.
NVDA_GESTURE_MAP = r'''
def __init__(self, entries: Optional[FlattenedGestureMapT] = None):
	"""Constructor.
	@param entries: Initial entries to add; see L{update} for the format.
	"""
	self._map: _InternalGestureMapT = {}
	#: Indicates that the last load or update contained an error.
	self.lastUpdateContainedError: bool = False
	#: The file name for this gesture map, if any.
	self.fileName: Optional[str] = None
	if entries:
		self.update(entries)


def add(
	self,
	gesture: str,
	module: str,
	className: str,
	script: Optional[ScriptNameT],
	replace: bool = False,
):
	"""Add a gesture mapping.
	@param gesture: The gesture identifier.
	@param module: The name of the Python module containing the target script.
	@param className: The name of the class in L{module} containing the target script.
	@param script: The name of the target script
		or C{None} to unbind the gesture for this class.
	@param replace: if true replaces all existing bindings for this gesture with the given script,
		otherwise only appends this binding.
	"""
	gesture = normalizeGestureIdentifier(gesture)
	try:
		scripts = self._map[gesture]
	except KeyError:
		scripts = self._map[gesture] = []
	if replace:
		del scripts[:]
	scripts.append((module, className, script))


def getScriptsForGesture(self, gesture: str) -> Generator[InputGestureScriptT, None, None]:
	"""Get the scripts associated with a particular gesture.
	@param gesture: The gesture identifier.
	@return: The Python class and script name for each script;
		the script name may be C{None} indicating that the gesture should be unbound for this class.
	"""
	try:
		scripts = self._map[gesture]
	except KeyError:
		return
	for moduleName, className, scriptName in scripts:
		try:
			module = sys.modules[moduleName]
		except KeyError:
			continue
		try:
			cls = getattr(module, className)
		except AttributeError:
			continue
		yield cls, scriptName
'''

#: NVDA 2026.2, source/inputCore.py: normalizeGestureIdentifier.
NVDA_NORMALIZE_GESTURE = r'''
def normalizeGestureIdentifier(identifier):
	"""Normalize a gesture identifier so that it matches other identifiers for the same gesture.
	First, the entire identifier is converted to lower case.
	Then, any items separated by a + sign after the source prefix are considered to be of indeterminate order
	and are sorted by character.
	This is done because, for example, "kb:shift+alt+downArrow"
	must be treated the same as "kb:alt+shift+downarrow".
	"""
	identifier = identifier.lower()
	prefix, main = identifier.split(":", 1)
	main = main.split("+")
	# The order of the parts doesn't matter as far as the user is concerned,
	# but we need them to be in a determinate order so they will match other gesture identifiers.
	# We sort them by character.
	main.sort()
	main = "+".join(main)
	return "{0}:{1}".format(prefix, main)
'''

NVDA_CODE_FILES = {
	"NVDA_VERSION_BINDINGS": "winBindings/version.py",
	"NVDA_KERNEL32_BINDINGS": "winBindings/kernel32.py",
	"NVDA_FILE_VERSION_INFO": "fileUtils.py",
	"NVDA_OPEN_PROCESS": "winKernel.py",
	"NVDA_PROCESS_HANDLE": "appModuleHandler.py",
	"NVDA_APP_NAME": "appModuleHandler.py",
	"NVDA_APP_MODULE": "appModuleHandler.py",
	"NVDA_REPORT_APP_MODULE_INFO": "globalCommands.py",
	"NVDA_SCRIPT_HANDLER": "scriptHandler.py",
	"NVDA_GESTURE_MAP": "inputCore.py",
	"NVDA_NORMALIZE_GESTURE": "inputCore.py",
}

# -- the imitation ------------------------------------------------------------------------------------------------

#: What NVDA's AppModule.__init__ does that the tests need: the process and its handle (NVDA's own
#: getProcessHandleFromProcessId, without its window search). An app module has no keys here.
IMITATION_APP_MODULE = r'''
def __init__(self, processID, appName):
	self.processID = processID
	self.appName = appName
	self.processHandle = getProcessHandleFromProcessId(processID, False)


def getScript(self, gesture):
	return None
'''

#: gestures.ini is written as NVDA writes it; here, it is noted.
IMITATION_GESTURE_MAP_SAVE = r'''
def save(self):
	self.saved = getattr(self, "saved", 0) + 1
'''

_log = logging.getLogger("nvda.test_v130")
_log.debugWarning = _log.debug
_log.io = _log.debug

#: What JAWS said for the tester, pressed twice, in Outlook and in Edge (issue 29). Their serial number is left out.
TESTER_OUTLOOK = """Version Details Information:
Microsoft Outlook Subscription Version 16.0.20326.20158
JAWS version 2026.2606.132.400
Scripts Revision: 4
Current settings: Outlook.
Current application: OUTLOOK.EXE.
Active configuration: Outlook.
Current Speech and Sounds Scheme: Classic.
Microsoft Windows 11 Professional Version 25H2 (OS Build 26200.9457), System Type x64 """
TESTER_EDGE = """Version Details Information:
Microsoft Edge Version 154.0.4258.37
JAWS version 2026.2606.132.400
Scripts Revision: 4
Current settings: Default.
Current application: msedge.dll.
Active configuration: github.com.
Current Speech and Sounds Scheme: Classic.
Microsoft Windows 11 Professional Version 25H2 (OS Build 26200.9457), System Type x64 """
#: The registry values of the tester's Windows that JAWS read for that last line.
TESTER_WINDOWS = {"CurrentMajorVersionNumber": 10, "CurrentBuild": "26200", "DisplayVersion": "25H2", "EditionID": "Professional", "UBR": 9457}
#: What NVDA 2026.2's nvda.exe says of itself, on this computer (buildVersion.version and version_detailed).
NVDA_VERSION = ("2026.2", "2026.2.0.57664")

JAWS_ROOT = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Freedom Scientific", "JAWS", "2026")
JAWS_SCRIPTS = os.path.join(JAWS_ROOT, "Scripts")
EDGE = os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), "Microsoft", "Edge", "Application", "msedge.exe")
#: Store apps Windows 11 runs, one of which is likely running: NVDA reads their name and version from their package.
STORE_APPS = ("StartMenuExperienceHost.exe", "SearchHost.exe", "ShellExperienceHost.exe", "TextInputHost.exe", "Widgets.exe", "Notepad.exe", "CalculatorApp.exe", "WindowsTerminal.exe")
#: JAWS's keystrokes for these commands, as JAWS 2026's Default.JKM has them.
JAWS_KEYS = (
	"[Keyboard Layouts]\nDesktop=Common\nLaptop=Common\n"
	"[Common Keys]\nControl+JAWSKey+Windows+V=PutVersionDetailsOnClipboard\nControl+Insert+Windows+V=PutVersionDetailsOnClipboard\n"
	"Control+JAWSKey+V=SayAppVersion\nJAWSKey+T=SayWindowTitle\n"
	"[Laptop Keys]\nControl+Insert+V=SayAppVersion\n"
	"[Laptop Modifiers]\nCapsLock=14|3|0|0|0|0|0x4000\n[Desktop Modifiers]\nInsert=17|3|0|2|0|0|0x4020800\n"
)
#: NVDA's own NVDA+Control+V: "Shows NVDA's speech settings" (globalCommands.py).
NVDA_SPEECH_SETTINGS = ("kb:NVDA+control+v", "activateVoiceDialog")


def jawsMessages(*names) -> dict:
	"""JAWS's messages (``@name``, the text, ``@@``) in its .jsm and .jsh files."""
	messages = {}
	for name in names:
		with open(os.path.join(JAWS_SCRIPTS, name), encoding="utf-8-sig", errors="replace") as f:
			text = f.read().replace("\r\n", "\n")
		for found in re.finditer(r"^@(\w+)\n(.*?)\n@@", text, re.M | re.S):
			messages.setdefault(found.group(1).lower(), found.group(2))
	return messages


def jawsFormat(message: str) -> str:
	"""A JAWS message's %1, %2... as Python's {0}, {1}..."""
	return re.sub(r"%(\d)", lambda found: "{%d}" % (int(found.group(1)) - 1), message)


def jawsScript(name: str) -> str:
	with open(os.path.join(JAWS_SCRIPTS, name), encoding="utf-8-sig", errors="replace") as f:
		return f.read().replace("\r\n", "\n")


def needsJaws(test):
	return unittest.skipUnless(os.path.isdir(JAWS_SCRIPTS), "JAWS 2026 isn't installed")(test)


class Shlobj:
	"""shlobj's SHGetKnownFolderPath, for the one folder NVDA's decorator asks for: Windows' own System32."""

	FolderId = types.SimpleNamespace(SYSTEM="system")

	@staticmethod
	def SHGetKnownFolderPath(folder):
		return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")


class Programs:
	"""NVDA 2026.2's own code for a program's name, version and executable, run on this computer's processes."""

	def __init__(self):
		version = v129.module(
			"winBindings.version",
			NVDA_VERSION_BINDINGS,
			"winBindings/version.py",
			WINFUNCTYPE=WINFUNCTYPE,
			POINTER=POINTER,
			dll=windll.version,
			BOOL=BOOL,
			DWORD=DWORD,
			LPCVOID=LPCVOID,
			LPCWSTR=LPCWSTR,
			LPDWORD=LPDWORD,
			LPVOID=LPVOID,
			PUINT=PUINT,
		)
		kernel32 = v129.module(
			"winBindings.kernel32",
			NVDA_KERNEL32_BINDINGS,
			"winBindings/kernel32.py",
			WINFUNCTYPE=WINFUNCTYPE,
			POINTER=POINTER,
			Structure=Structure,
			c_uint=c_uint,
			ULONG_PTR=c_size_t,
			dll=windll.kernel32,
			BOOL=BOOL,
			DWORD=DWORD,
			HANDLE=HANDLE,
			LONG=LONG,
			LPWSTR=LPWSTR,
			PDWORD=PDWORD,
			WCHAR=WCHAR,
		)
		self.winBindings = types.SimpleNamespace(version=version, kernel32=kernel32)
		# A 64-bit NVDA, as NVDA 2026 is and this Python is, has no Wow64 redirection to suspend.
		winKernel = v129.module("winKernel", NVDA_OPEN_PROCESS, "winKernel.py", winBindings=self.winBindings, suspendWow64Redirection=contextlib.nullcontext)
		self.fileUtils = v129.module(
			"fileUtils",
			NVDA_FILE_VERSION_INFO,
			"fileUtils.py",
			os=os,
			ctypes=ctypes,
			array=array,
			log=_log,
			wraps=functools.wraps,
			winBindings=self.winBindings,
			shlobj=Shlobj,
			systemUtils=types.SimpleNamespace(hasSyswow64Dir=lambda: True),
			winKernel=winKernel,
		)

		def importAppModuleForExecutable(appName):
			# No program here hosts other apps.
			raise LookupError(appName)

		self.appModuleHandler = v129.module(
			"appModuleHandler",
			NVDA_PROCESS_HANDLE + "\n\n\n" + NVDA_APP_NAME,
			"appModuleHandler.py",
			ctypes=ctypes,
			os=os,
			log=_log,
			winKernel=winKernel,
			winBindings=self.winBindings,
			WindowsError=OSError,
			globalVars=types.SimpleNamespace(appPid=0),
			_importAppModuleForExecutable=importAppModuleForExecutable,
		)
		base = {
			"garbageHandler": types.SimpleNamespace(TrackedObject=object),
			"log": _log,
			"weakref": weakref,
			"ABCMeta": ABCMeta,
			"abstractproperty": abstractproperty,
		}
		AutoPropertyObject = v128.nvdaCode(v128.NVDA_BASE_OBJECT, "AutoPropertyObject", base)
		names = dict(
			base,
			AutoPropertyObject=AutoPropertyObject,
			ctypes=ctypes,
			winBindings=self.winBindings,
			getFileVersionInfo=self.fileUtils.getFileVersionInfo,
			getProcessHandleFromProcessId=self.appModuleHandler.getProcessHandleFromProcessId,
		)
		self.AppModule = v128.nvdaClass("class AppModule(AutoPropertyObject)", [IMITATION_APP_MODULE, NVDA_APP_MODULE], names)
		self.appModuleHandler.AppModule = self.AppModule
		self._handles = []

	def appModule(self, processID, appName, moduleName=None):
		"""NVDA's app module for a process: NVDA's own AppModule, or, with ``moduleName``, NVDA's support for the program
		(a subclass in ``appModules.<moduleName>``, as NVDA's app modules for Outlook and File Explorer are)."""
		cls = self.AppModule if moduleName is None else type("AppModule", (self.AppModule,), {"__module__": f"appModules.{moduleName}"})
		module = cls(processID, appName)
		if module.processHandle:
			self._handles.append(module.processHandle)
		return module

	def appModuleFor(self, appName, moduleName=None, **attributes):
		"""An app module for a program that isn't running here, with what NVDA would have read from it."""
		cls = self.AppModule if moduleName is None else type("AppModule", (self.AppModule,), {"__module__": f"appModules.{moduleName}"})
		module = cls.__new__(cls)
		module.processID = 0
		module.appName = appName
		module.processHandle = 0
		vars(module).update(attributes)
		return module

	def processes(self) -> list:
		"""``(process ID, executable)`` for each process, from Windows' process snapshot, as NVDA reads it."""
		kernel32 = self.winBindings.kernel32
		snapshot = kernel32.CreateToolhelp32Snapshot(2, 0)
		entry = kernel32.PROCESSENTRY32W()
		entry.dwSize = ctypes.sizeof(entry)
		found = []
		more = kernel32.Process32First(snapshot, ctypes.byref(entry))
		while more:
			found.append((entry.th32ProcessID, entry.szExeFile))
			more = kernel32.Process32Next(snapshot, ctypes.byref(entry))
		kernel32.CloseHandle(snapshot)
		return found

	def running(self, *executables) -> list:
		wanted = [name.lower() for name in executables]
		return sorted(((wanted.index(exe.lower()), pid, exe) for pid, exe in self.processes() if exe.lower() in wanted))

	def close(self):
		for handle in self._handles:
			self.winBindings.kernel32.CloseHandle(handle)
		self._handles = []


class Focus:
	"""NVDA's focus object, as far as the assistant and scriptHandler look at it."""

	def __init__(self, appModule):
		self.appModule = appModule
		self.processID = appModule.processID
		self.treeInterceptor = None

	def getScript(self, gesture):
		return None


class Key:
	"""A key NVDA's keyboard handler gives scriptHandler: its identifiers as NVDA normalizes them, desktop layout first."""

	def __init__(self, gesture, normalize):
		main = gesture.split(":", 1)[1]
		self.normalizedIdentifiers = [normalize(f"kb(desktop):{main}"), normalize(f"kb:{main}")]
		self.displayName = main
		self.scriptableObject = None
		self.sent = 0

	def send(self):
		self.sent += 1


class GlobalCommands:
	"""NVDA's globalCommands.commands, with NVDA's own NVDA+Control+V, "Shows NVDA's speech settings"."""

	_GlobalCommands__gestures = {NVDA_SPEECH_SETTINGS[0]: NVDA_SPEECH_SETTINGS[1]}

	def __init__(self):
		self.opened = []

	def script_activateVoiceDialog(self, gesture):
		self.opened.append("speech settings")

	def getScript(self, gesture):
		wanted = "kb:control+nvda+v"
		return self.script_activateVoiceDialog if wanted in gesture.normalizedIdentifiers else None


GlobalCommands.__module__ = "globalCommands"


class Conf(types.SimpleNamespace):
	"""config.conf: its profiles, and the keyboard section."""

	def __getitem__(self, key):
		return {"keyboard": {"keyboardLayout": "desktop"}}[key]


class NvdaCase(unittest.TestCase):
	"""NVDA's speech, ui.message and clipboard (test_v129_speechHistory), its code for programs, and the assistant's own
	settings file in a folder of its own."""

	def setUp(self):
		super().setUp()
		self.nvda = v129.Nvda(v129._frame)
		self.shown = []
		self.nvda.ui.browseableMessage = lambda message, title=None, isHtml=False, closeButton=False, copyButton=False: self.shown.append(
			(message, title, closeButton, copyButton),
		)
		self.programs = Programs()
		self.addCleanup(self.programs.close)
		self.focus = None
		self.nvda.api.getFocusObject = lambda: self.focus
		self.nvda.api.getFocusAncestors = lambda: []
		modules = dict(
			self.nvda.modules(),
			appModuleHandler=self.programs.appModuleHandler,
			buildVersion=types.SimpleNamespace(version=NVDA_VERSION[0], version_detailed=NVDA_VERSION[1]),
			addonHandler=types.SimpleNamespace(getCodeAddon=lambda: types.SimpleNamespace(manifest={"version": "1.30"})),
			config=types.SimpleNamespace(conf=types.SimpleNamespace(profiles=[types.SimpleNamespace(name=None)])),
			winVersion=types.SimpleNamespace(getWinVer=lambda: types.SimpleNamespace(processorArchitecture="AMD64")),
		)
		patcher = mock.patch.dict(sys.modules, modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		folder = tempfile.TemporaryDirectory()
		self.addCleanup(folder.cleanup)
		patcher = mock.patch.object(state, "statePath", return_value=os.path.join(folder.name, "state.json"))
		patcher.start()
		self.addCleanup(patcher.stop)
		state.forget()
		self.addCleanup(state.forget)
		self.errors = []
		patcher = mock.patch.object(appVersion.debugLog, "error", side_effect=lambda what, *args, **kwargs: self.errors.append(what))
		patcher.start()
		self.addCleanup(patcher.stop)

	def useTestersComputer(self, scheme="Classic"):
		"""The tester's Windows, and ClassicSpeech with JAWS's Classic scheme."""
		for patcher in (
			mock.patch.object(appVersion, "readWindowsValues", return_value=dict(TESTER_WINDOWS)),
			mock.patch.object(nvdaApply, "classicSpeechRunning", return_value=scheme is not None),
			mock.patch.object(nvdaApply, "classicSpeechSection", return_value={"schemeData": json.dumps({"version": 2, "enabled": True, "activeScheme": scheme})}),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def useTestersOutlook(self):
		# The tester's Outlook isn't on this computer: its app module holds what NVDA reads from OUTLOOK.EXE (NVDA's
		# _setProductInfo sets them so), and the executable is the one JAWS named.
		self.focus = Focus(self.programs.appModuleFor("outlook", "outlook", productName="Microsoft Outlook", productVersion="16.0.20326.20158"))
		patcher = mock.patch.object(appVersion, "executableName", return_value="OUTLOOK.EXE")
		patcher.start()
		self.addCleanup(patcher.stop)

	def plugin(self, secure=False):
		"""The assistant's global plugin, as NVDA runs it, without its menus and timers."""
		plugin = jawsMigrator.GlobalPlugin.__new__(jawsMigrator.GlobalPlugin)
		plugin._gestureMap = {}
		plugin._secure = secure
		plugin._layerActive = False
		plugin._insertKeys = {}
		return plugin


# -- JAWS's own words, rules and keys -----------------------------------------------------------------------------


@needsJaws
class JawsTests(unittest.TestCase):
	def test_theWordsAreJaws(self):
		common = jawsMessages("common.jsm")
		self.assertEqual(appVersion.VERSION_DETAILS, common["cmsgversiondetails"])
		self.assertEqual(appVersion.COPIED, common["cmsgversiondetailscopiedtoclipboard"])
		self.assertEqual(appVersion.PRODUCT_VERSION, jawsFormat(common["cmsg239_l"]))
		self.assertEqual(appVersion.WINDOWS_VERSION, jawsFormat(common["cmsgmicrosoftwindows10andhigherversiontemplate"]))
		self.assertEqual(appVersion.CONFIGURATION + "\n" + appVersion.SCHEME, jawsFormat(common["cmsgactiveconfigurationinfo"]).replace("{3}", "{0}"))
		self.assertEqual(appVersion.DEFAULT, common["cmsg238_l"])
		for office in ("Outlook.jsm", "MSOffice2007.jsm"):
			words = jawsMessages(office)
			self.assertEqual((appVersion.RETAIL, appVersion.SUBSCRIPTION), (jawsFormat(words["msgretail"]), jawsFormat(words["msgsubscription"])), office)
		constants = jawsMessages("HJConst.JSH")
		self.assertEqual((constants["cmsg282_l"], constants["cmsg283_l"]), ("ProductName", "ProductVersion"))
		architectures = dict(re.findall(r'^\s*(Architecture_\w+)\s*=\s*"(\w+)"', jawsScript("HJConst.JSH"), re.M))
		self.assertEqual({appVersion.SYSTEM_TYPES["amd64"], appVersion.SYSTEM_TYPES["arm64"]}, set(architectures.values()))

	def test_theRulesAreJaws(self):
		default = jawsScript("Default.JSS")
		sayAppVersion = default[default.index("Script SayAppVersion ()") :]
		sayAppVersion = sayAppVersion[: sayAppVersion.index("EndScript")]
		# Twice, the version details; once, the program's version (GetFocusedApplicationVersionInfo).
		self.assertIn("if IsSameScript() then\n\tPerformScript ShowVersionDetails ()", sayAppVersion)
		self.assertIn("GetFocusedApplicationVersionInfo ()", sayAppVersion)
		self.assertIn("SayMessage (OT_USER_BUFFER, GetExtendedVersionDetailsInfo ())", default)
		self.assertIn("copyToClipboard (GetExtendedVersionDetailsInfo ())\nsayMessage (OT_STATUS, cmsgVersionDetailsCopiedToClipboard)", default)
		# The name and version from the program's file (cmsg282_L ProductName, cmsg283_L ProductVersion), or its package.
		self.assertIn("let sProduct = GetVersionInfoString (GetAppFilePath (), cmsg282_L)", default)
		self.assertIn("let sVersion = GetVersionInfoString (GetAppFilePath (), cmsg283_L)", default)
		self.assertIn("let sProduct = GetMetroAppName()", default)
		# Windows's version, from the registry values the assistant reads.
		osVersion = default[default.index("string function GetOSVersionInfo ()") :]
		osVersion = osVersion[: osVersion.index("endFunction")]
		for name in appVersion.WINDOWS_VALUES:
			self.assertIn(f'"{name}"', osVersion)
		self.assertIn("if isWindows11 () then\n\twinVersion = \"11\"", osVersion)
		# File Explorer: Windows's version.
		self.assertIn("string function GetFocusedApplicationVersionInfo ()\nreturn GetOSVersionInfo()", jawsScript("explorer.jss"))
		# Office: "Microsoft", JAWS's name for the program, and how Office was bought, from its third number.
		office = jawsScript("Office.jss")
		self.assertIn("string appName = scMicrosoft + cScSpace + GetActiveConfiguration ()", office)
		self.assertIn(f"if officeMinorVersion < {appVersion.FIRST_SUBSCRIPTION_UPDATE} then\n\t\treturn formatString (msgRetail, appName)", office)
		self.assertIn("GetFixedProductVersion (GetAppFilePath (), 0, 0, officeMinorVersion, 0)", office)
		self.assertIn("If OfficeVersion < 16 then return appName endIf", jawsScript("OfficeClassic.jss"))
		for script, uses in (("WORD.jss", 'use "office.jsb"'), ("Outlook.jss", 'use "word.jsb"'), ("PowerPoint.jss", 'use "Office.jsb"'), ("MSAcFunc.jss", 'use "OfficeClassic.jsb"')):
			self.assertIn(uses, jawsScript(script), script)
		with open(os.path.join(JAWS_ROOT, "SETTINGS", "enu", "ConfigNames.ini"), encoding="utf-8", errors="replace") as f:
			names = dict(re.findall(r"^(\w+)=(.+?)\s*$", f.read(), re.M))
		for appName in ("outlook", "winword", "msaccess"):
			self.assertEqual(appVersion.OFFICE_PROGRAMS[appName], names[appName])

	def test_theKeysAreJaws(self):
		with open(os.path.join(JAWS_SCRIPTS, "enu", "Default.JKM"), encoding="utf-8-sig", errors="replace") as f:
			jkm = jawsFiles.parseIni(f.read())
		self.assertEqual(jkm.get("Common Keys", "Control+JAWSKey+V"), "SayAppVersion")
		self.assertEqual(jkm.get("Common Keys", "Control+JAWSKey+Windows+V"), "PutVersionDetailsOnClipboard")
		self.assertEqual(jkm.get("Common Keys", "Control+Insert+Windows+V"), "PutVersionDetailsOnClipboard")
		self.assertEqual(jkm.get("Laptop Keys", "Control+Insert+V"), "SayAppVersion")


# -- what JAWS said for the tester --------------------------------------------------------------------------------


class TesterTests(NvdaCase):
	def test_outlookAsJawsSaysIt(self):
		self.useTestersComputer()
		self.useTestersOutlook()
		self.assertEqual(appVersion.programVersion(self.focus.appModule), TESTER_OUTLOOK.splitlines()[1])

	def test_windowsAsJawsSaysIt(self):
		self.assertEqual(appVersion.windowsVersion(TESTER_WINDOWS, "AMD64"), TESTER_OUTLOOK.splitlines()[-1].rstrip())

	def test_outlookDetails(self):
		self.useTestersComputer()
		self.useTestersOutlook()
		details = appVersion.details(self.focus)
		self.assertEqual(
			details.splitlines(),
			[
				"Version Details Information:",
				"Microsoft Outlook Subscription Version 16.0.20326.20158",
				"NVDA version 2026.2 (2026.2.0.57664)",
				"JAWS Migration Assistant version 1.30",
				"Current settings: normal configuration.",
				"Current application: OUTLOOK.EXE.",
				"Active configuration: outlook.",
				"Current Speech and Sounds Scheme: Classic.",
				"Microsoft Windows 11 Professional Version 25H2 (OS Build 26200.9457), System Type x64",
			],
		)
		# Every line JAWS and NVDA have alike is JAWS's, word for word.
		jaws = [line.rstrip() for line in TESTER_OUTLOOK.splitlines()]
		for line in (0, 1, 5, 7, 8):
			self.assertIn(details.splitlines()[line], jaws)
		self.assertEqual(self.errors, [])

	def test_edgeDetails(self):
		# Edge on this computer, read by NVDA's own code (see RealProgramTests); NVDA 2026.2 has no app module for it.
		if not os.path.isfile(EDGE):
			self.skipTest("Edge isn't installed")
		self.useTestersComputer()
		self.focus = Focus(RealProgramTests.edge(self.programs))
		with mock.patch.object(appVersion, "executableName", return_value="msedge.exe"):
			lines = appVersion.details(self.focus).splitlines()
		version = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(EDGE))))
		self.assertEqual(lines[1], f"Microsoft Edge Version {self.focus.appModule.productVersion}")
		self.assertEqual(lines[5:7], ["Current application: msedge.exe.", "Active configuration: Default."])
		self.assertEqual(lines[8], TESTER_EDGE.splitlines()[-1].rstrip())
		self.assertTrue(version)

	def test_officeAsJawsNamesIt(self):
		cases = (
			("outlook", "16.0.20326.20158", "Microsoft Outlook Subscription Version 16.0.20326.20158"),
			("winword", "16.0.6699.1000", "Microsoft Word Retail Version 16.0.6699.1000"),
			("winword", "16.0.6700.1000", "Microsoft Word Subscription Version 16.0.6700.1000"),
			("powerpnt", "17.0.100.1", "Microsoft PowerPoint Subscription Version 17.0.100.1"),
			("msaccess", "15.0.5023.1000", "Microsoft Access Version 15.0.5023.1000"),
			# Excel: JAWS's scripts for it don't rename it, so it is its file's name.
			("excel", "16.0.20326.20158", "Microsoft Excel Version 16.0.20326.20158"),
		)
		for appName, version, said in cases:
			module = self.programs.appModuleFor(appName, appName, productName=f"Microsoft {appName.title()}" if appName == "excel" else "Microsoft Office", productVersion=version)
			self.assertEqual(appVersion.programVersion(module), said, appName)

	def test_systemTypes(self):
		values = dict(TESTER_WINDOWS)
		self.assertTrue(appVersion.windowsVersion(values, "ARM64").endswith("System Type Arm64"))
		# JAWS names no other architecture; NVDA 2026 runs on no other.
		self.assertTrue(appVersion.windowsVersion(values, "x86").endswith("System Type "))
		values["CurrentBuild"] = "19045"
		values["DisplayVersion"] = "22H2"
		self.assertEqual(appVersion.windowsVersion(values, "AMD64"), "Microsoft Windows 10 Professional Version 22H2 (OS Build 19045.9457), System Type x64")


# -- this computer's programs, read by NVDA's own code ------------------------------------------------------------


class RealProgramTests(NvdaCase):
	@staticmethod
	def edge(programs):
		"""Edge's msedge.exe, read by NVDA's own code. Edge isn't left running here, so the app module is that of this
		Python, which isn't a Store app either, with Edge's executable in place of Python's."""
		module = programs.appModule(os.getpid(), "msedge")
		module.processExecutablePath = EDGE
		return module

	def test_edge(self):
		if not os.path.isfile(EDGE):
			self.skipTest("Edge isn't installed")
		module = self.edge(self.programs)
		self.assertIsNone(module._getImmersivePackageInfo())
		# Edge installs each version in a folder of that name, next to msedge.exe.
		folder = os.path.dirname(EDGE)
		versions = [name for name in os.listdir(folder) if re.fullmatch(r"\d+(\.\d+){3}", name)]
		self.assertIn(module.productVersion, versions)
		self.assertEqual(module.productName, "Microsoft Edge")
		said = appVersion.programVersion(module)
		self.assertEqual(said, f"Microsoft Edge Version {module.productVersion}")
		if module.productVersion == "154.0.4258.37":
			# The tester's Edge.
			self.assertEqual(said, TESTER_EDGE.splitlines()[1])

	def test_fileExplorer(self):
		running = self.programs.running("explorer.exe")
		if not running:
			self.skipTest("File Explorer isn't running")
		_order, pid, exe = running[0]
		module = self.programs.appModule(pid, "explorer", "explorer")
		self.assertTrue(module.processHandle, "NVDA opens File Explorer's process")
		# NVDA's own name for it is Windows's, "Microsoft® Windows® Operating System", and its version that of the file.
		self.assertEqual(module.productName, "Microsoft\u00ae Windows\u00ae Operating System")
		said = appVersion.programVersion(module)
		self.assertEqual(said, appVersion.windowsVersion())
		self.assertRegex(said, r"^Microsoft Windows 1[01] \S+ Version \w+ \(OS Build \d+\.\d+\), System Type (x64|Arm64)$")
		self.focus = Focus(module)
		self.assertEqual(appVersion.executableName(self.focus), exe)
		self.assertEqual(appVersion.appModuleName(module), "explorer")

	def test_storeApp(self):
		for _order, pid, exe in self.programs.running(*STORE_APPS):
			module = self.programs.appModule(pid, os.path.splitext(exe)[0].lower())
			if module.processHandle and module._getImmersivePackageInfo():
				break
		else:
			self.skipTest("no Store app is running")
		# NVDA takes a Store app's name and version from its package, as JAWS does (GetMetroAppName and GetMetroAppVersion).
		package = module._getImmersivePackageInfo().split("_")
		self.assertEqual((module.productName, module.productVersion), (package[0], package[1]))
		self.assertEqual(appVersion.programVersion(module), f"{package[0]} Version {package[1]}")
		self.assertEqual(appVersion.appModuleName(module), appVersion.DEFAULT)

	def test_aDesktopProgram(self):
		# This Python, a program like any other: its file's name and version.
		module = self.programs.appModule(os.getpid(), "python")
		self.assertEqual(appVersion.programVersion(module), f"Python Version {sys.version.split()[0]}")
		self.focus = Focus(module)
		self.assertEqual(appVersion.executableName(self.focus).lower(), os.path.basename(sys.executable).lower())

	def test_noVersionInformation(self):
		# NVDA can't read a program's version when its process has no handle: NVDA's _setProductInfo raises.
		module = self.programs.appModuleFor("someprogram")
		self.assertEqual(appVersion.programVersion(module), "someprogram Version unknown")

	def test_sameFactsAsNvdaControlF1(self):
		running = self.programs.running("explorer.exe")
		if not running:
			self.skipTest("File Explorer isn't running")
		_order, pid, exe = running[0]
		self.focus = Focus(self.programs.appModule(pid, "explorer", "explorer"))
		commands = v128.nvdaClass(
			"class GlobalCommands",
			[NVDA_REPORT_APP_MODULE_INFO],
			{
				"script": lambda **kwargs: (lambda function: function),
				"_": lambda text: text,
				"SCRCAT_TOOLS": "tools",
				"api": self.nvda.api,
				"appModuleHandler": self.programs.appModuleHandler,
				"ui": self.nvda.ui,
			},
		)
		commands().script_reportAppModuleInfo(None)
		self.assertEqual(self.nvda.said(), [f" explorer module is loaded.  {exe} is currently running."])
		self.useTestersComputer(scheme=None)
		lines = appVersion.details(self.focus).splitlines()
		self.assertIn(f"Current application: {exe}.", lines)
		self.assertIn("Active configuration: explorer.", lines)


# -- the commands -------------------------------------------------------------------------------------------------


class CommandTests(NvdaCase):
	def setUp(self):
		super().setUp()
		self.useTestersComputer()
		self.useTestersOutlook()
		self.repeats = 0
		scriptHandler = types.SimpleNamespace(getLastScriptRepeatCount=lambda: self.repeats)
		patcher = mock.patch.object(jawsMigrator, "scriptHandler", scriptHandler)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_oncePressedSaysTheVersion(self):
		self.plugin().script_sayAppVersion(None)
		self.assertEqual(self.nvda.said(), ["Microsoft Outlook Subscription Version 16.0.20326.20158"])
		self.assertEqual(self.shown, [])

	def test_twiceShowsTheDetails(self):
		self.repeats = 1
		self.plugin().script_sayAppVersion(None)
		self.assertEqual(self.shown, [(appVersion.details(self.focus), "Version Details", True, True)])
		self.assertEqual(self.nvda.said(), [])

	def test_anNvdaWithoutButtons(self):
		def browseableMessage(message, title=None, isHtml=False):
			self.shown.append((message, title))

		self.nvda.ui.browseableMessage = browseableMessage
		self.plugin().script_showVersionDetails(None)
		self.assertEqual(self.shown, [(appVersion.details(self.focus), "Version Details")])

	def test_copy(self):
		before = v129.clipboardText()
		try:
			self.plugin().script_copyVersionDetails(None)
			self.assertEqual(v129.rawClipboardText(), appVersion.details(self.focus).replace("\n", "\r\n"))
			self.assertEqual(v129.rawClipboardText().count("\r\n"), 8)
			self.assertEqual(self.nvda.said(), ["Version Details Copied To Clipboard"])
		finally:
			if before is not None:
				self.nvda.api.copyToClip(before)

	def test_theLayer(self):
		layer = jawsMigrator.LAYER_GESTURES
		self.assertEqual((layer["kb:v"], layer["kb:shift+v"], layer["kb:control+v"]), ("sayAppVersion", "showVersionDetails", "copyVersionDetails"))
		for text in (
			"V, the name and version of the program you are in, as JAWS's Insert+Control+V. ",
			"Shift+V, the version details, to read and copy. ",
			"Control+V, copy the version details to the clipboard. ",
		):
			self.assertIn(text, jawsMigrator.LAYER_HELP)
		for name in ("sayAppVersion", "showVersionDetails", "copyVersionDetails"):
			self.assertIn("JAWS", getattr(jawsMigrator.GlobalPlugin, f"script_{name}").__doc__)

	def test_aSecureScreen(self):
		# NVDA can show no window and copy nothing there: twice says the version again.
		plugin = self.plugin(secure=True)
		self.repeats = 1
		plugin.script_sayAppVersion(None)
		plugin.script_showVersionDetails(None)
		plugin.script_copyVersionDetails(None)
		self.assertEqual(self.nvda.said(), ["Microsoft Outlook Subscription Version 16.0.20326.20158"])
		self.assertEqual(self.shown, [])

	def test_aLineThatFailsIsLeftOut(self):
		with mock.patch.object(nvdaApply, "classicSpeechSection", side_effect=RuntimeError("ClassicSpeech changed")):
			lines = appVersion.details(self.focus).splitlines()
		self.assertEqual(len(lines), 8)
		self.assertFalse([line for line in lines if line.startswith("Current Speech")])
		self.assertEqual(self.errors, ["could not work out ClassicSpeech's scheme for the version details"])

	def test_withoutClassicSpeechsSchemes(self):
		with mock.patch.object(nvdaApply, "classicSpeechSection", return_value={"schemeData": json.dumps({"enabled": False, "activeScheme": "Classic"})}):
			self.assertNotIn("Current Speech and Sounds Scheme: Classic.", appVersion.details(self.focus))
		with mock.patch.object(nvdaApply, "classicSpeechRunning", return_value=False):
			self.assertNotIn("Current Speech", appVersion.details(self.focus))

	def test_aProfile(self):
		sys.modules["config"].conf.profiles.append(types.SimpleNamespace(name="JAWS - Outlook"))
		self.assertIn("Current settings: JAWS - Outlook.", appVersion.details(self.focus))


# -- the keys -----------------------------------------------------------------------------------------------------


class KeysCase(NvdaCase):
	"""NVDA's own gesture maps and scriptHandler, with NVDA's NVDA+Control+V for its speech settings."""

	def setUp(self):
		super().setUp()
		self.useTestersComputer()
		self.useTestersOutlook()
		base = {"sys": sys}
		self.normalize = v128.nvdaCode(NVDA_NORMALIZE_GESTURE, "normalizeGestureIdentifier", base)
		names = dict(base, normalizeGestureIdentifier=self.normalize)
		GlobalGestureMap = v128.nvdaClass("class GlobalGestureMap", [NVDA_GESTURE_MAP, IMITATION_GESTURE_MAP_SAVE], names)
		self.userMap, self.localeMap = GlobalGestureMap(), GlobalGestureMap()
		self.commands = GlobalCommands()
		modules = test_keys.fakeNvdaModules()
		globalCommands = modules["globalCommands"]
		globalCommands.GlobalCommands = GlobalCommands
		globalCommands.commands = self.commands
		globalCommands.configProfileActivationCommands = types.SimpleNamespace(getScript=lambda gesture: None)
		# NVDA loads the assistant as globalPlugins.jawsMigrator.
		package = types.ModuleType("globalPlugins")
		package.jawsMigrator = jawsMigrator
		modules.update({"globalPlugins": package, "globalPlugins.jawsMigrator": jawsMigrator})
		patcher = mock.patch.dict(sys.modules, modules)
		patcher.start()
		self.addCleanup(patcher.stop)
		manager = types.SimpleNamespace(userGestureMap=self.userMap, localeGestureMap=self.localeMap, getAllGestureMappings=lambda: {})
		patcher = mock.patch.object(sys.modules["inputCore"], "manager", manager)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.thePlugin = self.plugin()
		self.scriptHandler = v129.module(
			"scriptHandler",
			NVDA_SCRIPT_HANDLER,
			"scriptHandler.py",
			api=self.nvda.api,
			inputCore=types.SimpleNamespace(manager=manager),
			braille=types.SimpleNamespace(handler=None),
			vision=types.SimpleNamespace(handler=None),
			globalPluginHandler=types.SimpleNamespace(runningPlugins=[self.thePlugin]),
			log=_log,
			time=time,
			weakref=weakref,
			config=types.SimpleNamespace(conf={"keyboard": {"multiPressTimeout": 500}}),
			willSayAllResume=lambda gesture: False,
		)
		# The assistant asks NVDA's scriptHandler how many times its key was pressed.
		patcher = mock.patch.object(jawsMigrator, "scriptHandler", self.scriptHandler)
		patcher.start()
		self.addCleanup(patcher.stop)

	def plan(self, layout="desktop", overrideConflicts=False, text=JAWS_KEYS):
		return keyPlan.planKeys(
			jawsFiles.parseIni(text),
			layout,
			boundScripts=nvdaApply.gestureBoundScripts,
			scriptExists=nvdaApply.scriptExists,
			overrideConflicts=overrideConflicts,
		)

	def press(self, gesture):
		"""The key, as NVDA runs it: the command scriptHandler finds, run by scriptHandler."""
		key = Key(gesture, self.normalize)
		script = self.scriptHandler._findScript(key)
		self.assertIsNotNone(script, gesture)
		self.scriptHandler.executeScript(script, key)
		return script


class KeyTests(KeysCase):
	def test_theTargets(self):
		for jawsName, script in (("SayAppVersion", "sayAppVersion"), ("ShowVersionDetails", "showVersionDetails"), ("PutVersionDetailsOnClipboard", "copyVersionDetails")):
			self.assertEqual(jawsKeyMap.getNvdaTargets(jawsName)[0][:3], ("globalPlugins.jawsMigrator", "GlobalPlugin", script))
			self.assertTrue(nvdaApply.scriptExists("globalPlugins.jawsMigrator", "GlobalPlugin", script), script)

	def test_nvdasKeyStaysNvdas(self):
		plan = self.plan()
		self.assertEqual(
			[(b.gesture, b.module, b.className, b.script) for b in plan.bindings if "version" in b.script.lower()],
			[("kb:NVDA+control+windows+v", "globalPlugins.jawsMigrator", "GlobalPlugin", "copyVersionDetails")],
		)
		skipped = {item.jawsKey: item for item in plan.skipped if item.jawsScript == "SayAppVersion"}
		self.assertEqual(skipped["Control+JAWSKey+V"].kind, keyPlan.SKIP_CONFLICT)
		self.assertIn("activateVoiceDialog", skipped["Control+JAWSKey+V"].reason)
		nvdaApply.addGestures(plan.bindings)
		# Insert+Control+V still opens NVDA's speech settings; Control+Insert+Windows+V copies the version details.
		self.press("kb:NVDA+control+v")
		self.assertEqual(self.commands.opened, ["speech settings"])
		before = v129.clipboardText()
		try:
			self.press("kb:NVDA+control+windows+v")
			self.assertEqual(self.nvda.said(), ["Version Details Copied To Clipboard"])
		finally:
			if before is not None:
				self.nvda.api.copyToClip(before)

	def test_takingNvdasKeys(self):
		plan = self.plan(overrideConflicts=True)
		sayAppVersion = [b for b in plan.bindings if b.script == "sayAppVersion"]
		self.assertEqual([(b.gesture, b.replaces, b.unbind) for b in sayAppVersion], [("kb:NVDA+control+v", ["activateVoiceDialog"], [])])
		nvdaApply.addGestures(plan.bindings)
		self.assertEqual(self.userMap.saved, 1)
		# NVDA asks the global plugins before its own commands: Insert+Control+V says the version, as in JAWS...
		script = self.press("kb:NVDA+control+v")
		self.assertEqual(script.__name__, "script_sayAppVersion")
		self.assertEqual(self.nvda.said(), ["Microsoft Outlook Subscription Version 16.0.20326.20158"])
		# ... and pressed again at once, shows the version details.
		self.press("kb:NVDA+control+v")
		self.assertEqual([title for _message, title, _close, _copy in self.shown], ["Version Details"])
		self.assertEqual(self.commands.opened, [])
		# Pressed again later, it says the version again.
		time.sleep(0.6)
		self.press("kb:NVDA+control+v")
		self.assertEqual(len(self.nvda.said()), 2)
		self.assertEqual(len(self.shown), 1)

	def test_theLaptopLayout(self):
		# Caps Lock+Control+V and Insert+Control+V are both NVDA+Control+V, and both are SayAppVersion.
		plan = self.plan(layout="laptop", overrideConflicts=True)
		self.assertEqual([b.gesture for b in plan.bindings if b.script == "sayAppVersion"], ["kb:NVDA+control+v"])
		self.assertEqual(plan.insertKeys, [])

	@needsJaws
	def test_jawsDefaultKeyMap(self):
		with open(os.path.join(JAWS_SCRIPTS, "enu", "Default.JKM"), encoding="utf-8-sig", errors="replace") as f:
			text = f.read()
		for layout in ("desktop", "laptop"):
			plan = self.plan(layout=layout, overrideConflicts=True, text=text)
			versions = sorted((b.gesture, b.script) for b in plan.bindings if b.module == "globalPlugins.jawsMigrator")
			# The program's version (1.30), JAWS's Insert+V, QuickSettings (issue 40), which NVDA has no key for, and, since
			# 1.48, JAWS's Start or End Tandem Session (Insert+Alt+T, Caps Lock+Alt+T).
			self.assertEqual(
				versions,
				[
					("kb:NVDA+alt+t", "startOrEndRemoteSession"),
					("kb:NVDA+control+v", "sayAppVersion"),
					("kb:NVDA+control+windows+v", "copyVersionDetails"),
					("kb:NVDA+v", "quickSettings"),
				],
				layout,
			)


class NewKeysTests(KeysCase):
	"""Once after the update, for a migration made before: its layouts and its choice about NVDA's keystrokes."""

	def setUp(self):
		super().setUp()
		self.said = []
		self.done = []
		self.backups = []
		# NVDA's configuration: the normal configuration, and NVDA's desktop keyboard layout.
		sys.modules["config"].conf = Conf(profiles=[types.SimpleNamespace(name=None)])

		def backupFirst(reason):
			self.backups.append(reason)
			return types.SimpleNamespace(path="backup")

		class Thread:
			# The backup runs at once here, where NVDA runs it in the background.
			def __init__(self, target, name=None, daemon=None):
				self.target = target

			def start(self):
				self.target()

		for patcher in (
			mock.patch.object(migrator, "_backupFirst", side_effect=backupFirst),
			mock.patch.object(threading, "Thread", Thread),
			mock.patch("wx.CallAfter", side_effect=lambda function, *args: function(*args)),
			mock.patch.object(newKeys.nvdaEnv, "shouldWriteToDisk", return_value=True),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def migrated(self, overrideConflicts, layouts=("desktop",)):
		state.set("lastMigration", {"when": "2026-09-26T10:00:00", "keyboardLayouts": list(layouts), "overrideConflicts": overrideConflicts})

	def addOnce(self):
		newKeys.addOnce(lambda: (jawsFiles.parseIni(JAWS_KEYS), "desktop"), self.said.append, lambda: self.done.append(True))

	def bound(self):
		return sorted((gesture, script) for gesture, scripts in self.userMap._map.items() for _module, _cls, script in scripts)

	def test_aMigrationThatTookNvdasKeys(self):
		self.migrated(overrideConflicts=True)
		self.addOnce()
		self.assertEqual(self.bound(), [("kb:control+nvda+v", "sayAppVersion"), ("kb:control+nvda+v+windows", "copyVersionDetails")])
		self.assertEqual(self.done, [True])
		self.assertEqual(len(self.backups), 1)
		self.assertEqual(
			self.said,
			[
				"JAWS Migration Assistant: 2 more JAWS keystrokes work in NVDA. NVDA+control+v, the name and version of the "
				"program you are in; twice, the version details. NVDA+control+windows+v, copy the version details.",
			],
		)
		self.assertEqual(state.get(newKeys.STATE_KEY), sorted(newKeys.NEW_SCRIPTS))
		# Once only.
		self.addOnce()
		self.assertEqual(len(self.backups), 1)
		self.assertEqual(len(self.said), 1)
		self.assertEqual(self.done, [True, True])
		# Insert+Control+V now says the version, where it opened NVDA's speech settings.
		self.press("kb:NVDA+control+v")
		self.assertEqual(self.nvda.said(), ["Microsoft Outlook Subscription Version 16.0.20326.20158"])

	def test_aMigrationThatLeftNvdasKeys(self):
		self.migrated(overrideConflicts=False)
		self.addOnce()
		self.assertEqual(self.bound(), [("kb:control+nvda+v+windows", "copyVersionDetails")])
		self.assertEqual(self.said, ["JAWS Migration Assistant: 1 more JAWS keystroke works in NVDA. NVDA+control+windows+v, copy the version details."])
		self.press("kb:NVDA+control+v")
		self.assertEqual(self.commands.opened, ["speech settings"])

	def test_yourOwnKeystrokeStays(self):
		# The tester gave NVDA+Control+V a command of their own in Input Gestures.
		self.userMap.add("kb:NVDA+control+v", "globalCommands", "GlobalCommands", "reportCurrentLine")
		self.migrated(overrideConflicts=True)
		self.addOnce()
		self.assertEqual(self.bound(), [("kb:control+nvda+v", "reportCurrentLine"), ("kb:control+nvda+v+windows", "copyVersionDetails")])

	def test_noMigratedKeystrokes(self):
		self.migrated(overrideConflicts=True, layouts=())
		self.addOnce()
		self.assertEqual((self.bound(), self.backups, self.said, self.done), ([], [], [], [True]))
		self.assertEqual(state.get(newKeys.STATE_KEY), sorted(newKeys.NEW_SCRIPTS))

	def test_neverMigrated(self):
		self.addOnce()
		self.assertEqual((self.bound(), self.backups, self.done), ([], [], [True]))
		self.assertEqual(newKeys.pending(state.load()), [])

	def test_aFailedBackupTriesAgain(self):
		self.migrated(overrideConflicts=True)
		with mock.patch.object(migrator, "_backupFirst", side_effect=OSError("disk full")):
			self.addOnce()
		self.assertEqual((self.bound(), self.said, self.done), ([], [], [True]))
		self.assertEqual(newKeys.pending(state.load()), sorted(newKeys.NEW_SCRIPTS))
		self.addOnce()
		self.assertEqual(len(self.bound()), 2)

	def test_withoutJaws(self):
		self.migrated(overrideConflicts=True)
		newKeys.addOnce(lambda: None, self.said.append, lambda: self.done.append(True))
		self.assertEqual((self.bound(), self.done), ([], [True]))
		self.assertEqual(newKeys.pending(state.load()), [])

	def test_aNewMigrationCountsThemDone(self):
		# What a migration of this version writes (Migration._applyEverything).
		with open(migrator.__file__, encoding="utf-8") as f:
			source = f.read()
		self.assertIn("updates[newKeys.STATE_KEY] = sorted(newKeys.NEW_SCRIPTS)", source)
		self.assertEqual(state.DEFAULTS[newKeys.STATE_KEY], [])
		state.set(newKeys.STATE_KEY, sorted(newKeys.NEW_SCRIPTS))
		state.forget()
		self.assertEqual(newKeys.pending(state.load()), [])

	def test_thePluginRunsItAfterAnUpdate(self):
		steps = []
		plugin = self.plugin()
		plugin._busy = False
		plugin._runRepairs = lambda given: steps.extend(given)
		plugin._repairVoices()
		names = [what for what, _step in steps]
		self.assertIn("the keystrokes of JAWS commands new since the last migration", names)
		self.assertGreater(names.index("the keystrokes of JAWS commands new since the last migration"), names.index("the Insert keystrokes of the JAWS Laptop layout"))


# -- NVDA's own code ----------------------------------------------------------------------------------------------


class NvdasOwnCodeTests(unittest.TestCase):
	def test_theCodeIsNvdas(self):
		# Each piece is in NVDA 2026.2's source, at the margin or as a method, when a copy of it is around: set
		# NVDA_SOURCE to its source folder.
		source = os.environ.get("NVDA_SOURCE")
		if not source:
			self.skipTest("NVDA_SOURCE isn't set to a folder with NVDA 2026.2's source")
		import textwrap

		for name, path in NVDA_CODE_FILES.items():
			with open(os.path.join(source, *path.split("/")), encoding="utf-8") as f:
				text = f.read().replace("\r\n", "\n")
			for block in globals()[name].strip("\n").split("\n\n\n"):
				self.assertTrue(block in text or textwrap.indent(block, "\t") in text, f"{name}: {block.splitlines()[0]}")


if __name__ == "__main__":
	unittest.main()
