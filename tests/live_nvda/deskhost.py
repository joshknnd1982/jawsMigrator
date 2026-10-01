"""Hosts a private Windows desktop with its own NVDA and Edge on it (test tooling, not part of the add-on).

Nothing on this desktop receives Josh's keyboard or mouse, and Josh's NVDA, on the interactive desktop, never sees it:
NVDA's single-instance check and its mutex are per desktop. This process holds the desktop open; it runs until the file
``stop`` appears next to this script, then ends what it started.
"""
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GENERIC_ALL = 0x10000000
CREATE_NEW_CONSOLE = 0x10
CREATE_UNICODE_ENVIRONMENT = 0x400


class STARTUPINFOW(ctypes.Structure):
	_fields_ = [
		("cb", wintypes.DWORD),
		("lpReserved", wintypes.LPWSTR),
		("lpDesktop", wintypes.LPWSTR),
		("lpTitle", wintypes.LPWSTR),
		("dwX", wintypes.DWORD),
		("dwY", wintypes.DWORD),
		("dwXSize", wintypes.DWORD),
		("dwYSize", wintypes.DWORD),
		("dwXCountChars", wintypes.DWORD),
		("dwYCountChars", wintypes.DWORD),
		("dwFillAttribute", wintypes.DWORD),
		("dwFlags", wintypes.DWORD),
		("wShowWindow", wintypes.WORD),
		("cbReserved2", wintypes.WORD),
		("lpReserved2", ctypes.c_void_p),
		("hStdInput", wintypes.HANDLE),
		("hStdOutput", wintypes.HANDLE),
		("hStdError", wintypes.HANDLE),
	]


class PROCESS_INFORMATION(ctypes.Structure):
	_fields_ = [
		("hProcess", wintypes.HANDLE),
		("hThread", wintypes.HANDLE),
		("dwProcessId", wintypes.DWORD),
		("dwThreadId", wintypes.DWORD),
	]


kernel32.CreateProcessW.argtypes = [
	wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD,
	ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFOW), ctypes.POINTER(PROCESS_INFORMATION),
]
kernel32.CreateProcessW.restype = wintypes.BOOL
user32.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
user32.CreateDesktopW.restype = wintypes.HANDLE


def start(desktopName, commandLine, cwd=None):
	si = STARTUPINFOW()
	si.cb = ctypes.sizeof(si)
	si.lpDesktop = f"winsta0\\{desktopName}"
	pi = PROCESS_INFORMATION()
	buffer = ctypes.create_unicode_buffer(commandLine)
	if not kernel32.CreateProcessW(None, buffer, None, None, False, 0, None, cwd, ctypes.byref(si), ctypes.byref(pi)):
		raise ctypes.WinError(ctypes.get_last_error())
	kernel32.CloseHandle(pi.hThread)
	return pi.hProcess, pi.dwProcessId


def main():
	config = json.load(open(os.path.join(HERE, "deskhost.json"), encoding="utf-8"))
	name = config["desktop"]
	stop = os.path.join(HERE, "stop")
	if os.path.exists(stop):
		os.remove(stop)
	desktop = user32.CreateDesktopW(name, None, None, 0, GENERIC_ALL, None)
	if not desktop:
		raise ctypes.WinError(ctypes.get_last_error())
	children = []
	status = open(os.path.join(HERE, "deskhost.status"), "w", encoding="utf-8")

	def say(text):
		status.write(f"{time.strftime('%H:%M:%S')} {text}\n")
		status.flush()

	say(f"desktop {name} created")
	try:
		for entry in config["start"]:
			handle, pid = start(name, entry["cmd"], entry.get("cwd"))
			children.append((entry.get("label", entry["cmd"]), handle, pid))
			say(f"started {entry.get('label')} pid {pid}")
			time.sleep(entry.get("wait", 3))
		import glob

		reported = set()
		while not os.path.exists(stop):
			for label, handle, pid in children:
				if pid not in reported and kernel32.WaitForSingleObject(handle, 0) == 0:
					reported.add(pid)
					say(f"{label} (pid {pid}) has exited")
			for path in glob.glob(os.path.join(HERE, "spawn-*.json")):
				try:
					with open(path, encoding="utf-8") as stream:
						entry = json.load(stream)
					os.replace(path, path + ".done")
					handle, pid = start(name, entry["cmd"], entry.get("cwd"))
					children.append((entry.get("label", entry["cmd"]), handle, pid))
					say(f"started {entry.get('label')} pid {pid}")
				except Exception as error:
					say(f"spawn failed: {error}")
			for path in glob.glob(os.path.join(HERE, "kill-*.json")):
				try:
					with open(path, encoding="utf-8") as stream:
						label = json.load(stream)["label"]
					os.replace(path, path + ".done")
					for childLabel, handle, pid in children:
						if childLabel == label and kernel32.WaitForSingleObject(handle, 0) != 0:
							kernel32.TerminateProcess(handle, 0)
							say(f"killed {childLabel} pid {pid}")
				except Exception as error:
					say(f"kill failed: {error}")
			time.sleep(0.5)
	finally:
		for label, handle, pid in reversed(children):
			if kernel32.WaitForSingleObject(handle, 0) != 0:
				kernel32.TerminateProcess(handle, 0)
				say(f"terminated {label} pid {pid}")
		time.sleep(1)
		user32.CloseDesktop(desktop)
		say("desktop closed")
		status.close()


if __name__ == "__main__":
	main()
