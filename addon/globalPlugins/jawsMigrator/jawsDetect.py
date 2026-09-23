# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""Find out what is installed on this computer: JAWS, Leasey, and Windows itself.

Nothing is assumed about the machine. JAWS versions are found from the registry
keys its installer writes and, as a fallback, from the folders JAWS keeps its
program files and settings in, so a computer with several JAWS versions, a
non-English JAWS, or only the settings of an uninstalled JAWS is described
correctly. This module does not need NVDA, so it can be tested on its own.
"""

from __future__ import annotations

import ctypes
import getpass
import os
import re
import sys
from dataclasses import dataclass, field

try:
	import winreg
except ImportError:  # pragma: no cover - not Windows
	winreg = None

FS_KEY = r"SOFTWARE\Freedom Scientific\JAWS"
UNINSTALL_KEYS = (
	r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
	r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)
JAWS_EXE = "jfw.exe"
LEASEY_MARKERS = ("leasey", "hartgen")


def _environ(name: str, fallback: str = "") -> str:
	return os.environ.get(name) or fallback


def appDataFolder() -> str:
	return _environ("APPDATA", os.path.expanduser(r"~\AppData\Roaming"))


def programDataFolder() -> str:
	return _environ("PROGRAMDATA", r"C:\ProgramData")


def programFilesFolders() -> list[str]:
	folders = []
	for name in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
		value = os.environ.get(name)
		if value and value.lower() not in (f.lower() for f in folders):
			folders.append(value)
	if not folders:
		folders = [r"C:\Program Files", r"C:\Program Files (x86)"]
	return folders


# -- registry ----------------------------------------------------------------------


def _registryViews():
	if winreg is None:
		return []
	return [winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY]


def _openKey(root, path, view):
	return winreg.OpenKey(root, path, 0, winreg.KEY_READ | view)


def _subkeyNames(root, path, view) -> list[str]:
	names = []
	try:
		with _openKey(root, path, view) as key:
			index = 0
			while True:
				try:
					names.append(winreg.EnumKey(key, index))
				except OSError:
					break
				index += 1
	except OSError:
		pass
	return names


def _values(root, path, view) -> dict:
	values = {}
	try:
		with _openKey(root, path, view) as key:
			index = 0
			while True:
				try:
					name, value, _kind = winreg.EnumValue(key, index)
				except OSError:
					break
				values[name] = value
				index += 1
	except OSError:
		pass
	return values


def uninstallEntries() -> list[dict]:
	"""Every program in Add or Remove Programs, for both registry views and both hives."""
	if winreg is None:
		return []
	entries = []
	seen = set()
	for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
		for view in _registryViews():
			for path in UNINSTALL_KEYS:
				for name in _subkeyNames(root, path, view):
					values = _values(root, path + "\\" + name, view)
					marker = (name, str(values.get("DisplayName")), str(values.get("DisplayVersion")))
					if marker in seen:
						continue
					seen.add(marker)
					values["_key"] = name
					entries.append(values)
	return entries


# -- file versions -------------------------------------------------------------------


def fileVersionInfo(path: str) -> dict:
	"""Return ``{"FileVersion": ..., "ProductVersion": ..., "ProductName": ...}`` for an executable."""
	result = {}
	if sys.platform != "win32" or not os.path.isfile(path):
		return result
	try:
		version = ctypes.windll.version
		size = version.GetFileVersionInfoSizeW(path, None)
		if not size:
			return result
		buffer = ctypes.create_string_buffer(size)
		if not version.GetFileVersionInfoW(path, 0, size, buffer):
			return result
		pointer = ctypes.c_void_p()
		length = ctypes.c_uint()
		translations = []
		if version.VerQueryValueW(buffer, "\\VarFileInfo\\Translation", ctypes.byref(pointer), ctypes.byref(length)):
			count = length.value // 4
			array = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_ushort * (count * 2))).contents
			translations = [(array[i * 2], array[i * 2 + 1]) for i in range(count)]
		translations.append((0x0409, 0x04B0))
		for name in ("FileVersion", "ProductVersion", "ProductName", "CompanyName"):
			for language, codepage in translations:
				query = f"\\StringFileInfo\\{language:04x}{codepage:04x}\\{name}"
				if version.VerQueryValueW(buffer, query, ctypes.byref(pointer), ctypes.byref(length)) and length.value:
					result[name] = ctypes.wstring_at(pointer, length.value - 1).strip()
					break
	except Exception:
		pass
	return result


# -- running processes ---------------------------------------------------------------


class _ProcessEntry(ctypes.Structure):
	_fields_ = [
		("dwSize", ctypes.c_ulong),
		("cntUsage", ctypes.c_ulong),
		("th32ProcessID", ctypes.c_ulong),
		("th32DefaultHeapID", ctypes.c_size_t),
		("th32ModuleID", ctypes.c_ulong),
		("cntThreads", ctypes.c_ulong),
		("th32ParentProcessID", ctypes.c_ulong),
		("pcPriClassBase", ctypes.c_long),
		("dwFlags", ctypes.c_ulong),
		("szExeFile", ctypes.c_wchar * 260),
	]


def runningProcessNames() -> list[str]:
	"""Lower-cased executable names of every running process."""
	names = []
	if sys.platform != "win32":
		return names
	kernel32 = ctypes.windll.kernel32
	kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
	TH32CS_SNAPPROCESS = 0x00000002
	snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
	if not snapshot or snapshot == ctypes.c_void_p(-1).value:
		return names
	try:
		entry = _ProcessEntry()
		entry.dwSize = ctypes.sizeof(_ProcessEntry)
		ok = kernel32.Process32FirstW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
		while ok:
			names.append(entry.szExeFile.lower())
			ok = kernel32.Process32NextW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
	finally:
		kernel32.CloseHandle(ctypes.c_void_p(snapshot))
	return names


def isJawsRunning() -> bool:
	return JAWS_EXE in runningProcessNames()


# -- JAWS ------------------------------------------------------------------------------


def versionSortKey(version: str) -> float:
	"""JAWS 2026 is newer than JAWS 18.0, which was released in 2017."""
	match = re.match(r"(\d+)(?:\.(\d+))?", version or "")
	if not match:
		return 0.0
	major = int(match.group(1))
	minor = int(match.group(2) or 0)
	if major < 1000:
		major += 1999
	return major + minor / 100.0


@dataclass
class JawsInstallation:
	"""One JAWS version found on this computer."""

	#: The version folder name JAWS uses, such as ``2026`` or ``18.0``.
	version: str
	installDir: str = ""
	productVersion: str = ""
	fileVersion: str = ""
	primaryLanguage: str = ""
	languages: list = field(default_factory=list)
	userRoot: str = ""
	sharedRoot: str = ""
	#: True when the JAWS program (jfw.exe) is on disk, not just leftover settings.
	programInstalled: bool = False
	registryFound: bool = False

	@property
	def displayName(self) -> str:
		name = f"JAWS {self.version}"
		if self.productVersion and self.productVersion != self.version:
			name += f" ({self.productVersion})"
		return name

	@property
	def userSettingsDir(self) -> str:
		return os.path.join(self.userRoot, "Settings")

	@property
	def sharedSettingsDir(self) -> str:
		return os.path.join(self.sharedRoot, "SETTINGS")

	@property
	def sharedScriptsDir(self) -> str:
		return os.path.join(self.sharedRoot, "Scripts")

	def userLanguageDir(self, language: str) -> str:
		return os.path.join(self.userSettingsDir, language)

	def sharedLanguageDir(self, language: str) -> str:
		return os.path.join(self.sharedSettingsDir, language)

	def sharedScriptsLanguageDir(self, language: str) -> str:
		return os.path.join(self.sharedScriptsDir, language)

	@property
	def hasUserSettings(self) -> bool:
		return os.path.isdir(self.userSettingsDir)

	@property
	def hasSharedSettings(self) -> bool:
		return os.path.isdir(self.sharedSettingsDir)

	@property
	def settingsLanguages(self) -> list[str]:
		"""Language folders (``enu``, ``deu``...) that hold settings, primary language first."""
		found = []
		for root in (self.userSettingsDir, self.sharedSettingsDir, self.sharedScriptsDir):
			try:
				names = os.listdir(root)
			except OSError:
				continue
			for name in names:
				if len(name) == 3 and name.isalpha() and os.path.isdir(os.path.join(root, name)):
					lowered = name.lower()
					if lowered not in found:
						found.append(lowered)
		preferred = []
		for lang in [self.primaryLanguage, *self.languages]:
			if lang and lang not in preferred:
				preferred.append(lang)
		ordered = [lang for lang in preferred if lang in found]
		ordered.extend(lang for lang in found if lang not in ordered)
		return ordered

	def toDict(self) -> dict:
		return {
			"version": self.version,
			"displayName": self.displayName,
			"installDir": self.installDir,
			"productVersion": self.productVersion,
			"fileVersion": self.fileVersion,
			"primaryLanguage": self.primaryLanguage,
			"languages": list(self.languages),
			"userRoot": self.userRoot,
			"sharedRoot": self.sharedRoot,
			"programInstalled": self.programInstalled,
			"registryFound": self.registryFound,
			"settingsLanguages": self.settingsLanguages,
		}


def _splitLanguages(text) -> list[str]:
	return [part.strip().lower() for part in re.split(r"[|;, ]+", str(text or "")) if len(part.strip()) == 3]


def findJawsInstallations(
	appData: str | None = None,
	programData: str | None = None,
	programFiles: list[str] | None = None,
	useRegistry: bool = True,
) -> list[JawsInstallation]:
	"""Every JAWS version with a program folder, a registry entry or settings. Newest first."""
	appData = appData or appDataFolder()
	programData = programData or programDataFolder()
	programFiles = programFiles if programFiles is not None else programFilesFolders()
	found: dict[str, JawsInstallation] = {}

	def installation(version: str) -> JawsInstallation:
		key = version.lower()
		if key not in found:
			found[key] = JawsInstallation(
				version=version,
				userRoot=os.path.join(appData, "Freedom Scientific", "JAWS", version),
				sharedRoot=os.path.join(programData, "Freedom Scientific", "JAWS", version),
			)
		return found[key]

	if useRegistry and winreg is not None:
		for view in _registryViews():
			for version in _subkeyNames(winreg.HKEY_LOCAL_MACHINE, FS_KEY, view):
				if not re.match(r"^\d+(\.\d+)?$", version):
					continue
				values = _values(winreg.HKEY_LOCAL_MACHINE, FS_KEY + "\\" + version, view)
				jaws = installation(version)
				jaws.registryFound = True
				target = values.get("Target")
				if target and not jaws.installDir:
					jaws.installDir = str(target).rstrip("\\/")
				if values.get("PrimaryLanguage") and not jaws.primaryLanguage:
					jaws.primaryLanguage = str(values["PrimaryLanguage"]).lower()
				for language in _splitLanguages(values.get("SetupLanguages")):
					if language not in jaws.languages:
						jaws.languages.append(language)

	for root in programFiles:
		jawsRoot = os.path.join(root, "Freedom Scientific", "JAWS")
		try:
			names = os.listdir(jawsRoot)
		except OSError:
			continue
		for version in names:
			folder = os.path.join(jawsRoot, version)
			if re.match(r"^\d+(\.\d+)?$", version) and os.path.isfile(os.path.join(folder, JAWS_EXE)):
				jaws = installation(version)
				if not jaws.installDir:
					jaws.installDir = folder

	for root in (os.path.join(appData, "Freedom Scientific", "JAWS"), os.path.join(programData, "Freedom Scientific", "JAWS")):
		try:
			names = os.listdir(root)
		except OSError:
			continue
		for version in names:
			if re.match(r"^\d+(\.\d+)?$", version) and os.path.isdir(os.path.join(root, version)):
				installation(version)

	for jaws in found.values():
		exe = os.path.join(jaws.installDir, JAWS_EXE) if jaws.installDir else ""
		jaws.programInstalled = bool(exe) and os.path.isfile(exe)
		if jaws.programInstalled:
			info = fileVersionInfo(exe)
			jaws.productVersion = info.get("ProductVersion", "")
			jaws.fileVersion = info.get("FileVersion", "")
		if not jaws.primaryLanguage:
			languages = jaws.settingsLanguages
			jaws.primaryLanguage = languages[0] if languages else "enu"
		if jaws.primaryLanguage not in jaws.languages:
			jaws.languages.insert(0, jaws.primaryLanguage)

	# Only keep versions with something to migrate or a program to report.
	result = [jaws for jaws in found.values() if jaws.programInstalled or jaws.hasUserSettings or jaws.hasSharedSettings]
	result.sort(key=lambda jaws: versionSortKey(jaws.version), reverse=True)
	return result


# -- Leasey ------------------------------------------------------------------------------


@dataclass
class LeaseyInfo:
	"""What was found of Hartgen Consultancy's Leasey, which adds its own JAWS scripts and settings."""

	found: bool = False
	evidence: list = field(default_factory=list)
	version: str = ""


def hasLeaseyMarker(text: str) -> bool:
	lowered = (text or "").lower()
	return any(marker in lowered for marker in LEASEY_MARKERS)


def detectLeasey(installations: list[JawsInstallation] | None = None, entries: list[dict] | None = None) -> LeaseyInfo:
	"""Look for Leasey in Add or Remove Programs, its program and data folders, and JAWS settings."""
	info = LeaseyInfo()
	for entry in entries if entries is not None else uninstallEntries():
		name = str(entry.get("DisplayName") or "")
		publisher = str(entry.get("Publisher") or "")
		if "leasey" in name.lower() or "hartgen" in publisher.lower():
			info.found = True
			info.evidence.append(f"Installed program: {name or entry.get('_key')} {entry.get('DisplayVersion') or ''}".strip())
			if "leasey" in name.lower() and entry.get("DisplayVersion"):
				info.version = str(entry.get("DisplayVersion"))
	roots = [appDataFolder(), programDataFolder(), _environ("LOCALAPPDATA"), *programFilesFolders()]
	for root in roots:
		if not root:
			continue
		for name in ("Hartgen Consultancy", "Leasey"):
			folder = os.path.join(root, name)
			if os.path.isdir(folder):
				info.found = True
				info.evidence.append(f"Folder: {folder}")
	for jaws in installations or []:
		for root in (jaws.userSettingsDir, jaws.sharedSettingsDir, jaws.sharedScriptsDir):
			for folder, dirs, files in _walk(root, maxDepth=3):
				for name in list(dirs) + list(files):
					if hasLeaseyMarker(name):
						info.found = True
						info.evidence.append(f"JAWS {jaws.version} file: {os.path.join(folder, name)}")
	# Keep the list readable.
	seen = []
	for item in info.evidence:
		if item not in seen:
			seen.append(item)
	info.evidence = seen[:40]
	return info


def _walk(root: str, maxDepth: int = 4):
	if not root or not os.path.isdir(root):
		return
	baseDepth = root.rstrip("\\/").count(os.sep)
	for folder, dirs, files in os.walk(root):
		if folder.count(os.sep) - baseDepth >= maxDepth:
			dirs[:] = []
		yield folder, dirs, files


# -- Windows -------------------------------------------------------------------------------


def windowsVersionDescription() -> str:
	"""A readable Windows version, such as ``Windows 11 25H2 (10.0.26200) workstation``."""
	try:
		import winVersion

		return str(winVersion.getWinVer())
	except Exception:
		pass
	try:
		version = sys.getwindowsversion()
		name = "Windows 11" if version.major == 10 and version.build >= 22000 else f"Windows {version.major}"
		release = ""
		if winreg is not None:
			values = _values(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", winreg.KEY_WOW64_64KEY)
			release = str(values.get("DisplayVersion") or values.get("ReleaseId") or "")
		return f"{name} {release} ({version.major}.{version.minor}.{version.build})".replace("  ", " ")
	except Exception:
		return "Windows"


def windowsBuild() -> int:
	try:
		return sys.getwindowsversion().build
	except Exception:
		return 0


def currentUserName() -> str:
	try:
		return getpass.getuser()
	except Exception:
		return _environ("USERNAME", "")
