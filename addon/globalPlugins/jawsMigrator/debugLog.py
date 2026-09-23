# JAWS Migration Assistant for NVDA
# Copyright (C) 2026 Josh Kennedy
# This file is covered by the GNU General Public License, version 2 or later.

"""A detailed log of what the assistant reads, decides and changes, for finding problems.

Every migration writes ``debug.log`` in its own folder (``jawsMigrator\\migrations\\<date>``),
next to its report. Everything else the assistant does (JAWS sounds, restoring a backup,
repairs, errors) goes to ``jawsMigrator\\debug.log`` in NVDA's settings folder, which is kept
under 2 MB: when it grows past that, it becomes ``debug.log.1`` and a new one starts. Each
line also goes to NVDA's log at debug level, and errors at error level, so they show in
NVDA's log viewer when NVDA logs at those levels.

Nothing here raises: logging must never be the reason something fails.
"""

from __future__ import annotations

import datetime
import os
import threading
import traceback

LOG_NAME = "debug.log"
MAX_BYTES = 2 * 1024 * 1024

_lock = threading.RLock()
#: The file lines go to while a migration runs; None for the assistant's general log.
_active: str | None = None


def _nvdaLog():
	try:
		from logHandler import log

		return log
	except Exception:
		return None


def generalLogPath() -> str:
	try:
		from . import nvdaEnv

		return nvdaEnv.addonDataDir(LOG_NAME)
	except Exception:
		return ""


def currentPath() -> str:
	return _active or generalLogPath()


def _rotate(path: str) -> None:
	try:
		if os.path.getsize(path) > MAX_BYTES:
			os.replace(path, path + ".1")
	except OSError:
		pass


def _append(path: str, text: str) -> None:
	if not path:
		return
	try:
		from . import nvdaEnv

		if not nvdaEnv.shouldWriteToDisk():
			return
	except Exception:
		pass
	try:
		from . import safety

		# Like every file the assistant writes, never inside JAWS's folders.
		safety.checkWritable(path)
		os.makedirs(os.path.dirname(path), exist_ok=True)
		if path != _active:
			_rotate(path)
		with open(path, "a", encoding="utf-8") as stream:
			stream.write(text)
	except OSError:
		pass


def _stamp() -> str:
	return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def note(message: str) -> None:
	"""Add one line to the current log, and to NVDA's log at debug level."""
	try:
		with _lock:
			thread = threading.current_thread().name
			prefix = f"{_stamp()} [{thread}] "
			lines = str(message).splitlines() or [""]
			_append(currentPath(), "".join(prefix + line + "\n" for line in lines))
		log = _nvdaLog()
		if log is not None:
			log.debug(f"jawsMigrator: {message}")
	except Exception:
		pass


def section(title: str) -> None:
	note(f"== {title} ==")


def error(message: str, exc_info: bool = True) -> None:
	"""Record an error with its traceback, here and in NVDA's log."""
	try:
		details = traceback.format_exc() if exc_info else ""
		if details.strip() == "NoneType: None":
			details = ""
		note(f"ERROR: {message}" + (f"\n{details.rstrip()}" if details else ""))
		log = _nvdaLog()
		if log is not None:
			log.error(f"jawsMigrator: {message}", exc_info=exc_info)
	except Exception:
		pass


def start(path: str, title: str) -> None:
	"""Send lines to ``path`` (a migration's own log) until ``stop``."""
	global _active
	with _lock:
		_active = path
	section(title)
	try:
		from . import nvdaEnv

		note(f"NVDA {nvdaEnv.nvdaVersion()}, JAWS Migration Assistant {_addonVersion()}, settings folder {nvdaEnv.configDir()}")
	except Exception:
		pass
	with _lock:
		_append(generalLogPath(), f"{_stamp()} {title}: detailed log in {path}\n")


def stop() -> None:
	global _active
	note("== end ==")
	with _lock:
		_active = None


def _addonVersion() -> str:
	try:
		import addonHandler

		return str(addonHandler.getCodeAddon().manifest["version"])
	except Exception:
		return ""


def describe(value, limit: int = 400) -> str:
	"""A short printable form of a value for the log."""
	try:
		text = repr(value)
	except Exception:
		text = "<unprintable>"
	return text if len(text) <= limit else text[:limit] + f"... ({len(text)} characters)"
