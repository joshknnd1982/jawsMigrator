# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""NVDA's log in a zip file small enough to attach to a GitHub issue, without opening the log.

A tester's NVDA logs run to 20 MB and more: NVDA logs at its debug level, and an add-on fills the log with warnings (see
Debug logs in the help). GitHub takes an attached file of 25 MB at most. In one night four of the tester's logs never
reached their issues, and each issue kept only ``<!-- Failed to upload "pronunciation issues .txt" -->``. One of those
issues was about typing in a large document. To send a log, the tester saves it from NVDA's Log Viewer, opens it in
Windows 11's Notepad and types a note at its top, and that is where version 1.19's report had letters and spaces go
missing as they typed (see typingWatch). Zipped, the tester's 22 MB log comes to a third of a megabyte, in a tenth of
a second, and nothing needs to be typed into it.

NVDA+Shift+J, then L (or the NVDA menu, Tools, JAWS Migration Assistant, Save NVDA's log for a GitHub issue) puts
into one zip file, in Documents:

- ``nvda.log``: NVDA's log since NVDA started, as NVDA writes it (``globalVars.appArgs.logFileName``);
- ``nvda-old.log``: the log of NVDA's run before, which NVDA keeps next to its log, when there is one;
- ``jawsMigrator debug.log``: the assistant's own debug log, and the one before it when it has been started again.

The logs are read where they are, and nothing opens or changes them. The zipping happens in a thread of its own, so NVDA
goes on speaking meanwhile. NVDA then says the zip file's name and size, and puts its full name on the clipboard. In the
Open dialog of GitHub's "Paste, drop, or click to add files" button, Control+V then Enter attaches it. A note about
the problem goes in the issue's comment box, not into the log.
"""

from __future__ import annotations

import datetime
import os
import threading
import zipfile

#: The largest file GitHub attaches to an issue, in bytes.
GITHUB_LIMIT = 25 * 1024 * 1024
#: Windows' Documents folder (FOLDERID_Documents), where the zip file goes.
DOCUMENTS = "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"
#: The zip file's name, from the time it is saved: one a second at most, and in the order they were saved.
NAME = "NVDA log {:%Y-%m-%d %H.%M.%S}.zip"
#: The log NVDA keeps from its run before, next to its log (logHandler.initialize).
OLD_LOG = "nvda-old.log"

#: Held while a zip file is being written; a second press meanwhile only says so.
_saving = threading.Lock()


class NoLog(Exception):
	"""NVDA writes no log, as when it was started with logging off."""


def _log():
	from logHandler import log

	return log


def nvdaLogPath() -> str | None:
	"""The file NVDA writes its log to, or None when it writes none, as when started with logging off."""
	try:
		import globalVars

		return globalVars.appArgs.logFileName or None
	except Exception:
		return None


def logFiles() -> list[tuple[str, str]]:
	"""Each log there is, as (file, name in the zip file): NVDA's, NVDA's from its run before, then the assistant's."""
	files = []
	path = nvdaLogPath()
	if path:
		files.append((path, "nvda.log"))
		files.append((os.path.join(os.path.dirname(path), OLD_LOG), OLD_LOG))
	try:
		from . import debugLog

		general = debugLog.generalLogPath()
	except Exception:
		general = ""
	if general:
		files.append((general, "jawsMigrator debug.log"))
		files.append((general + ".1", "jawsMigrator debug.log.1"))
	return [(source, name) for source, name in files if os.path.isfile(source)]


def documentsFolder() -> str:
	"""Windows' Documents folder, wherever it has been moved, as to OneDrive; the user's own folder without one."""
	try:
		import shlobj

		path = shlobj.SHGetKnownFolderPath(DOCUMENTS)
		if path and os.path.isdir(path):
			return path
	except Exception:
		pass
	home = os.path.expanduser("~")
	path = os.path.join(home, "Documents")
	return path if os.path.isdir(path) else home


def save(folder: str | None = None, now: datetime.datetime | None = None) -> tuple[str, int, list[str]]:
	"""Zip the logs into ``folder`` (Documents): (the zip file, its size in bytes, the names in it).

	Raises NoLog when NVDA writes no log, and OSError when the zip file can't be written.
	"""
	files = logFiles()
	if not any(name == "nvda.log" for _source, name in files):
		raise NoLog()
	folder = folder or documentsFolder()
	path = os.path.join(folder, NAME.format(now or datetime.datetime.now()))
	# Written under another name first, so a zip file with this name is always whole.
	partial = path + ".part"
	try:
		with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
			for source, name in files:
				# NVDA goes on writing its log meanwhile: what it wrote until then is zipped.
				archive.write(source, name)
		os.replace(partial, path)
	except BaseException:
		try:
			os.remove(partial)
		except OSError:
			pass
		raise
	return path, os.path.getsize(path), [name for _source, name in files]


def describeSize(size: int) -> str:
	"""A size as NVDA says it: "850 KB", "1.4 MB"."""
	if size < 1024 * 1024:
		return f"{max(1, round(size / 1024))} KB"
	return f"{size / (1024 * 1024):.1f} MB"


def _folderName(path: str) -> str:
	folder = os.path.dirname(path)
	return "Documents" if os.path.normcase(folder) == os.path.normcase(documentsFolder()) else folder


def message(path: str, size: int, copied: bool) -> str:
	"""What NVDA says once the zip file ``path`` of ``size`` bytes is saved, its full name ``copied`` to the clipboard or not."""
	said = f"NVDA's log is saved in {_folderName(path)}, as {os.path.basename(path)}, {describeSize(size)}."
	if size > GITHUB_LIMIT:
		return (
			f"{said} That is more than the 25 MB GitHub takes. Restart NVDA, show the problem again, "
			"then save the log again right after it happens."
		)
	if copied:
		return (
			f"{said} Its full name is on the clipboard. To attach it to a GitHub issue, press the button "
			"Paste, drop, or click to add files, then Control+V and Enter."
		)
	return f"{said} Its full name is {path}"


def _copy(text: str) -> bool:
	try:
		import api

		return bool(api.copyToClip(text))
	except Exception:
		return False


def _speak(text: str) -> None:
	try:
		import ui

		ui.message(text)
	except Exception:
		pass


def _finish(path: str | None, size: int, failure: str | None) -> None:
	"""In NVDA's main thread, which owns the clipboard: say where the zip file is."""
	if failure is not None:
		_speak(failure)
		return
	_speak(message(path, size, _copy(path)))


def _onMainThread(function, *args) -> None:
	import wx

	wx.CallAfter(function, *args)


def _work() -> None:
	path, size, failure = None, 0, None
	try:
		path, size, names = save()
		_log().debug(f"jawsMigrator: NVDA's log is saved for a GitHub issue in {path}, {size} bytes: {', '.join(names)}")
	except NoLog:
		failure = "NVDA isn't writing a log, so there is none to save. Its log level is in NVDA's Settings, General."
	except Exception:
		try:
			from . import debugLog

			debugLog.error("could not save NVDA's log for a GitHub issue")
		except Exception:
			pass
		failure = "NVDA's log could not be saved. The assistant's debug log says why."
	finally:
		_saving.release()
	_onMainThread(_finish, path, size, failure)


def saveAndSay() -> None:
	"""NVDA+Shift+J, then L: zip NVDA's logs in Documents, in a thread of their own, then say where the file is."""
	if not _saving.acquire(blocking=False):
		_speak("NVDA's log is still being saved.")
		return
	try:
		threading.Thread(target=_work, name="jawsMigratorLogZip", daemon=True).start()
	except Exception:
		_saving.release()
		raise
	_speak("Saving NVDA's log.")
