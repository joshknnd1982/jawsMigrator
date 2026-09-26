# Unit tests for version 1.21, from a tester's report on version 1.20 (issue 15, "issue typing in a large document"):
# - logZip: the tester's log for the issue never reached it. GitHub kept only
#   <!-- Failed to upload "pronunciation issues .txt" -->, as for three more of their issues that night, because the
#   tester's NVDA logs run past the 25 MB GitHub takes. The document they typed in was most likely that log, open in
#   Windows 11's Notepad with their note typed at its top, as in issue 11. NVDA+Shift+J, then L now zips NVDA's logs
#   in Documents, and puts the zip file's full name on the clipboard for GitHub's Open dialog.
# NVDA's log files are made by NVDA 2026.2's own code from logHandler.initialize, word for word: it moves the log of
# NVDA's run before to nvda-old.log, and keeps nvda.log open with a logging.FileHandler while NVDA runs, as the zip
# file is made. Documents is found by NVDA 2026.2's own shlobj.SHGetKnownFolderPath, word for word, through Windows
# itself, and compared with where Windows' registry says Documents is. The log's lines are those of the tester's logs,
# where Emoticons 38.0.0's warnings fill most of it. The assistant's code is the real one.
# Run: python -m unittest tests.test_v121_logZip -v

import ctypes
import datetime
import logging
import os
import shutil
import sys
import tempfile
import threading
import types
import unittest
import winreg
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import comtypes  # noqa: E402

import jawsMigrator  # noqa: E402
from jawsMigrator import debugLog, logZip  # noqa: E402


def nvdaCode(source, name, namespace):
	"""Compile NVDA's own ``source`` in ``namespace``, and give back ``name`` from it."""
	namespace = dict(namespace)
	exec(source, namespace)
	return namespace[name]


# NVDA 2026.2's logHandler.initialize, the part that makes its log files, word for word, as a function of its own.
NVDA_OPEN_LOG = nvdaCode(
	"def openLog(globalVars, FileHandler, log):\n"
	"\t\tif True:\n"
	"\t\t\tif not globalVars.appArgs.logFileName:\n"
	"\t\t\t\tglobalVars.appArgs.logFileName = _getDefaultLogFilePath()\n"
	"\t\t\t# Keep a backup of the previous log file so we can access it even if NVDA crashes or restarts.\n"
	"\t\t\toldLogFileName = os.path.join(os.path.dirname(globalVars.appArgs.logFileName), \"nvda-old.log\")\n"
	"\t\t\ttry:\n"
	"\t\t\t\t# We must remove the old log file first as os.rename does replace it.\n"
	"\t\t\t\tif os.path.exists(oldLogFileName):\n"
	"\t\t\t\t\tos.unlink(oldLogFileName)\n"
	"\t\t\t\tos.rename(globalVars.appArgs.logFileName, oldLogFileName)\n"
	"\t\t\texcept (IOError, WindowsError):\n"
	"\t\t\t\tpass  # Probably log does not exist, don't care.\n"
	"\t\t\ttry:\n"
	"\t\t\t\tlogHandler = FileHandler(globalVars.appArgs.logFileName, mode=\"w\", encoding=\"utf-8\")\n"
	"\t\t\texcept IOError:\n"
	"\t\t\t\t# if log cannot be opened, we use NullHandler to avoid logging preserving logger behaviour\n"
	"\t\t\t\t# and set log filename to None to inform logViewer about it\n"
	"\t\t\t\tglobalVars.appArgs.logFileName = None\n"
	"\t\t\t\tlogHandler = logging.NullHandler()\n"
	"\t\t\t\tlog.error(\"Faile to open log file, redirecting to standard output\")\n"
	"\t\treturn logHandler\n",
	"openLog",
	{"os": os, "logging": logging, "_getDefaultLogFilePath": lambda: None},
)

# NVDA 2026.2's shlobj.SHGetKnownFolderPath, word for word, on Windows' own shell32 and ole32.
_shell32 = ctypes.WinDLL("shell32")
_shell32.SHGetKnownFolderPath.restype = ctypes.HRESULT
_ole32 = ctypes.WinDLL("ole32")
_ole32.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
_winBindings = types.SimpleNamespace(
	shell32=types.SimpleNamespace(SHGetKnownFolderPath=lambda *args: _shell32.SHGetKnownFolderPath(*args) or 0),
	ole32=types.SimpleNamespace(CoTaskMemFree=lambda pointer: _ole32.CoTaskMemFree(ctypes.cast(pointer, ctypes.c_void_p))),
)
NVDA_KNOWN_FOLDER = nvdaCode(
	"def SHGetKnownFolderPath(\n"
	"\tfolderGuid: Union[FolderId, str],\n"
	"\tdwFlags: int = 0,\n"
	"\thToken: Optional[int] = None,\n"
	") -> str:\n"
	"\t\"\"\"Wrapper for `SHGetKnownFolderPath` which caches the results\n"
	"\tto avoid calling the win32 function unnecessarily.\"\"\"\n"
	"\tif isinstance(folderGuid, FolderId):\n"
	"\t\tfolderGuid = folderGuid.value\n"
	"\tguid = comtypes.GUID(folderGuid)\n"
	"\n"
	"\tpathPointer = ctypes.c_wchar_p()\n"
	"\tres = winBindings.shell32.SHGetKnownFolderPath(\n"
	"\t\tcomtypes.byref(guid),\n"
	"\t\tdwFlags,\n"
	"\t\thToken,\n"
	"\t\tctypes.byref(pathPointer),\n"
	"\t)\n"
	"\tif res != 0:\n"
	"\t\traise RuntimeError(f\"SHGetKnownFolderPath failed with error code {res}\")\n"
	"\tpath = pathPointer.value\n"
	"\twinBindings.ole32.CoTaskMemFree(pathPointer)\n"
	"\treturn path\n",
	"SHGetKnownFolderPath",
	{
		"comtypes": comtypes,
		"ctypes": ctypes,
		"winBindings": _winBindings,
		"FolderId": type("FolderId", (), {}),
		"Union": __import__("typing").Union,
		"Optional": __import__("typing").Optional,
	},
)

#: A warning from the tester's logs, which fill most of them: 176 of these each time NVDA switches profiles.
EMOTICONS_WARNING = (
	"WARNING - external:globalPlugins.emoticons.GlobalPlugin.handleConfigProfileSwitch (00:15:12.345) - MainThread (11484):\n"
	"Importing speechDictHandler.dictFormatUpgrade is deprecated. Use speechDictHandler.dictFormatUpgrade instead.\n"
	"Stack trace:\n"
	"  File \"nvda.pyw\", line 405, in <module>\n"
	"  File \"core.pyc\", line 953, in main\n"
	"  File \"C:\\Users\\admin\\AppData\\Roaming\\nvda\\addons\\emoticons\\globalPlugins\\emoticons\\__init__.py\", line 212, in handleConfigProfileSwitch\n"
)
TYPED = (
	"IO - inputCore.InputManager.executeGesture (10:38:39.125) - winInputHook (8044):\n"
	"Input: kb(laptop):s\n"
)
NOW = datetime.datetime(2026, 9, 26, 0, 45, 12)


class LogZipTestCase(unittest.TestCase):
	def setUp(self):
		self.folder = tempfile.mkdtemp(prefix="jawsMigratorLogZip")
		self.addCleanup(shutil.rmtree, self.folder, True)
		self.temp = os.path.join(self.folder, "Temp")
		self.documents = os.path.join(self.folder, "Documents")
		self.nvdaConfig = os.path.join(self.folder, "nvda", "jawsMigrator")
		for path in (self.temp, self.documents, self.nvdaConfig):
			os.makedirs(path)
		self.globalVars = types.SimpleNamespace(appArgs=types.SimpleNamespace(logFileName=os.path.join(self.temp, "nvda.log")))
		patches = (
			mock.patch.dict(sys.modules, {"globalVars": self.globalVars}),
			mock.patch.object(debugLog, "generalLogPath", lambda: os.path.join(self.nvdaConfig, "debug.log")),
			mock.patch.object(logZip, "documentsFolder", lambda: self.documents),
		)
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)
		self.handlers = []

	def startNvda(self, lines: str = "") -> logging.Handler:
		"""NVDA starting: its own code moves the last run's log to nvda-old.log and opens nvda.log for writing."""
		handler = NVDA_OPEN_LOG(self.globalVars, logging.FileHandler, logging.getLogger("nvda"))
		self.handlers.append(handler)
		self.addCleanup(handler.close)
		self.write(handler, lines)
		return handler

	def write(self, handler, text: str):
		if text:
			handler.stream.write(text)
			handler.flush()

	def read(self, path: str) -> bytes:
		with open(path, "rb") as stream:
			return stream.read()

	def zipped(self, path: str) -> dict:
		with zipfile.ZipFile(path) as archive:
			return {name: archive.read(name) for name in archive.namelist()}


class SaveTests(LogZipTestCase):
	def test_theLogsNvdaKeepsAreZippedInDocuments(self):
		before = self.startNvda("INFO - __main__ (23:54:33.140) - MainThread (11484):\nStarting NVDA version 2026.2 AMD64\n")
		before.close()
		# The tester's log: about 20 MB, most of it Emoticons' warnings.
		running = self.startNvda(EMOTICONS_WARNING * 50000 + TYPED)
		with open(os.path.join(self.nvdaConfig, "debug.log"), "w", encoding="utf-8") as stream:
			stream.write("[2026-09-26 00:40:00] typed late\n")
		logSize = os.path.getsize(self.globalVars.appArgs.logFileName)
		self.assertGreater(logSize, 20 * 1024 * 1024, "the log is as big as the tester's")

		path, size, names = logZip.save(now=NOW)

		self.assertEqual(path, os.path.join(self.documents, "NVDA log 2026-09-26 00.45.12.zip"))
		self.assertEqual(names, ["nvda.log", "nvda-old.log", "jawsMigrator debug.log"])
		files = self.zipped(path)
		self.assertEqual(files["nvda.log"], self.read(self.globalVars.appArgs.logFileName))
		self.assertEqual(files["nvda-old.log"], self.read(os.path.join(self.temp, "nvda-old.log")))
		self.assertIn(b"Starting NVDA version 2026.2", files["nvda-old.log"])
		self.assertEqual(files["jawsMigrator debug.log"], self.read(os.path.join(self.nvdaConfig, "debug.log")))
		self.assertEqual(size, os.path.getsize(path))
		self.assertLess(size, logSize / 10, f"zipped, the log is a tenth of its size or less: {size} of {logSize} bytes")
		self.assertLess(size, logZip.GITHUB_LIMIT)
		self.assertEqual(os.listdir(self.documents), [os.path.basename(path)], "nothing else is left in Documents")
		# NVDA goes on writing its log, which nothing changed.
		self.write(running, TYPED)
		# NVDA writes Windows' line ends.
		self.assertEqual(self.read(self.globalVars.appArgs.logFileName), files["nvda.log"] + TYPED.replace("\n", "\r\n").encode())

	def test_whatNvdaWritesMeanwhileIsInTheNextZipFile(self):
		running = self.startNvda(TYPED)
		first, _size, _names = logZip.save(now=NOW)
		self.write(running, "IO - speech.speech.speak (10:38:39.711) - MainThread (25208):\nSpeaking ['m']\n")
		second, _size, names = logZip.save(now=NOW + datetime.timedelta(seconds=1))
		self.assertEqual(names, ["nvda.log"], "without an earlier run or a debug log, NVDA's log alone")
		self.assertNotIn(b"Speaking ['m']", self.zipped(first)["nvda.log"])
		self.assertIn(b"Speaking ['m']", self.zipped(second)["nvda.log"])
		self.assertLess(os.path.basename(first), os.path.basename(second), "the zip files are in the order they were saved")

	def test_theAssistantsEarlierDebugLogToo(self):
		self.startNvda(TYPED)
		for name in ("debug.log", "debug.log.1"):
			with open(os.path.join(self.nvdaConfig, name), "w", encoding="utf-8") as stream:
				stream.write(name)
		_path, _size, names = logZip.save(now=NOW)
		self.assertEqual(names, ["nvda.log", "jawsMigrator debug.log", "jawsMigrator debug.log.1"])

	def test_withoutNvdaLogNothingIsSaved(self):
		self.globalVars.appArgs.logFileName = None
		with open(os.path.join(self.nvdaConfig, "debug.log"), "w", encoding="utf-8") as stream:
			stream.write("x")
		with self.assertRaises(logZip.NoLog):
			logZip.save(now=NOW)
		self.assertEqual(os.listdir(self.documents), [])

	def test_aZipFileThatCantBeWrittenIsntLeftHalfMade(self):
		self.startNvda(TYPED)
		missing = os.path.join(self.folder, "gone")
		with self.assertRaises(OSError) as raised:
			logZip.save(folder=missing, now=NOW)
		self.assertNotIsInstance(raised.exception, logZip.NoLog, "a folder that isn't there isn't a missing log")
		with mock.patch.object(zipfile.ZipFile, "write", side_effect=OSError("disk full")):
			with self.assertRaises(OSError):
				logZip.save(now=NOW)
		self.assertEqual(os.listdir(self.documents), [], "no zip file, and no .part file")


class DocumentsTests(unittest.TestCase):
	def test_documentsIsWhereWindowsSaysItIs(self):
		# NVDA's own SHGetKnownFolderPath, given the assistant's folder id, against Windows' registry.
		found = NVDA_KNOWN_FOLDER(logZip.DOCUMENTS)
		with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
			registered, _kind = winreg.QueryValueEx(key, "Personal")
		self.assertEqual(os.path.normcase(found), os.path.normcase(os.path.expandvars(registered)))
		shlobj = types.SimpleNamespace(SHGetKnownFolderPath=NVDA_KNOWN_FOLDER)
		with mock.patch.dict(sys.modules, {"shlobj": shlobj}):
			self.assertEqual(logZip.documentsFolder(), found)

	def test_withoutNvdaTheUsersDocuments(self):
		with mock.patch.dict(sys.modules, {"shlobj": None}):
			folder = logZip.documentsFolder()
		self.assertTrue(os.path.isdir(folder))
		self.assertIn(os.path.normcase(folder), (os.path.normcase(os.path.expanduser("~\\Documents")), os.path.normcase(os.path.expanduser("~"))))


class SayTests(LogZipTestCase):
	def setUp(self):
		super().setUp()
		nvdaStubs.spoken.clear()
		self.clipboard = []
		self.copies = True
		api = types.SimpleNamespace(copyToClip=lambda text, notify=False: self.clipboard.append(text) or self.copies)
		self.mainThread = []
		self.done = threading.Event()

		def onMainThread(function, *args):
			self.mainThread.append((function, args))
			self.done.set()

		for patch in (mock.patch.dict(sys.modules, {"api": api}), mock.patch.object(logZip, "_onMainThread", onMainThread)):
			patch.start()
			self.addCleanup(patch.stop)

	def press(self):
		"""NVDA+Shift+J, then L; then what the thread hands NVDA's main thread, run there."""
		self.done.clear()
		logZip.saveAndSay()
		self.assertTrue(self.done.wait(30), "the zip file is saved")
		function, args = self.mainThread.pop()
		function(*args)

	def test_saysWhereTheZipFileIsAndPutsItsNameOnTheClipboard(self):
		self.startNvda(EMOTICONS_WARNING * 1000)
		self.press()
		saved = [name for name in os.listdir(self.documents)]
		self.assertEqual(len(saved), 1)
		path = os.path.join(self.documents, saved[0])
		self.assertEqual(self.clipboard, [path], "the zip file's full name is on the clipboard")
		self.assertEqual(nvdaStubs.spoken[0], "Saving NVDA's log.")
		said = nvdaStubs.spoken[1]
		self.assertTrue(said.startswith(f"NVDA's log is saved in Documents, as {saved[0]}, "), said)
		self.assertIn(" KB. Its full name is on the clipboard. To attach it to a GitHub issue, press the button Paste, drop, or click to add files, then Control+V and Enter.", said)

	def test_aSecondPressWhileSavingOnlySaysSo(self):
		self.startNvda(TYPED)
		with logZip._saving:
			logZip.saveAndSay()
		self.assertEqual(nvdaStubs.spoken, ["NVDA's log is still being saved."])
		self.assertEqual(os.listdir(self.documents), [])
		self.press()
		self.assertEqual(len(os.listdir(self.documents)), 1, "once the first is saved, the key saves again")

	def test_withoutNvdaLogItSaysSo(self):
		self.globalVars.appArgs.logFileName = None
		self.press()
		self.assertEqual(nvdaStubs.spoken[-1], "NVDA isn't writing a log, so there is none to save. Its log level is in NVDA's Settings, General.")
		self.assertEqual(self.clipboard, [])

	def test_aFailureIsSaidAndTheKeyWorksAgain(self):
		self.startNvda(TYPED)
		with mock.patch.object(zipfile.ZipFile, "write", side_effect=PermissionError("in use")), mock.patch.object(debugLog, "error"):
			self.press()
		self.assertEqual(nvdaStubs.spoken[-1], "NVDA's log could not be saved. The assistant's debug log says why.")
		self.press()
		self.assertTrue(nvdaStubs.spoken[-1].startswith("NVDA's log is saved in Documents"))

	def test_withoutTheClipboardItSaysTheFullName(self):
		self.copies = False
		path = os.path.join(self.documents, "NVDA log 2026-09-26 00.45.12.zip")
		said = logZip.message(path, 900 * 1024, copied=False)
		self.assertEqual(said, f"NVDA's log is saved in Documents, as NVDA log 2026-09-26 00.45.12.zip, 900 KB. Its full name is {path}")

	def test_aZipFileTooBigForGitHubIsSaidSo(self):
		path = os.path.join(self.documents, "NVDA log 2026-09-26 00.45.12.zip")
		said = logZip.message(path, 26 * 1024 * 1024, copied=True)
		self.assertIn("26.0 MB. That is more than the 25 MB GitHub takes. Restart NVDA, show the problem again", said)
		self.assertIn("in Documents", said)
		elsewhere = logZip.message(os.path.join(self.folder, "x.zip"), 2 * 1024 * 1024 + 1, copied=True)
		self.assertTrue(elsewhere.startswith(f"NVDA's log is saved in {self.folder}, as x.zip, 2.0 MB."), elsewhere)


class LayerTests(unittest.TestCase):
	def test_nvdaShiftJThenL(self):
		self.assertEqual(jawsMigrator.LAYER_GESTURES.get("kb:l"), "saveLogForIssue")
		self.assertTrue(callable(getattr(jawsMigrator.GlobalPlugin, "script_saveLogForIssue", None)))
		self.assertIn("L, save NVDA's log in Documents as a zip file, small enough to attach to a GitHub issue. ", jawsMigrator.LAYER_HELP)


if __name__ == "__main__":
	unittest.main()
