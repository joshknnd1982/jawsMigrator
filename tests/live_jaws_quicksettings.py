# Live check of JAWS's Quick Settings (Insert+V), for issue 40: what JAWS shows in each program, read from a running JAWS.
#
# This is not a unit test (its name doesn't start with test_): it needs JAWS, and it opens programs and windows. It runs
# the script QuickSettings, the one Insert+V runs, through JAWS's own programming interface (FreedomSci.JawsApi), waits
# for the window "QuickSettings - <program>", reads the rows of its tree through Microsoft Active Accessibility, and
# presses Cancel, so no JAWS setting changes. What it read goes to tests/jaws_quicksettings_live.json, which
# test_quickSettings compares the assistant's window with, offline, program by program.
#
# JAWS's tree is a custom control with no UI Automation children, so its rows are read through MSAA (oleacc): each
# category and each setting is a child of the FeatureTree window, named by its text.
#
# Needs Windows, JAWS 2026 (installed; it is started if it isn't running and exited at the end), pywin32 and comtypes.
# Run: python tests/live_jaws_quicksettings.py [scenario ...]
# The scenarios: notepad, edge-page (the focus in a web page: JAWS's virtual cursor), edge-window (the focus in Edge's
# address bar), olk (new Outlook). Without one named, all of them.

import ctypes
import ctypes.wintypes
import json
import os
import subprocess
import sys
import time

import comtypes
import comtypes.client
import win32api
import win32com.client
import win32con
import win32gui
import win32process

comtypes.client.GetModule("oleacc.dll")
from comtypes.gen import Accessibility  # noqa: E402

RESULT = os.path.join(os.path.dirname(__file__), "jaws_quicksettings_live.json")
JAWS = r"C:\Program Files\Freedom Scientific\JAWS\2026\jfw.exe"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PAGE = "data:text/html,<title>QS test page</title><h1>Quick Settings test</h1><p>Hello <a href=#x>link</a></p>"
OBJID_CLIENT = 0xFFFFFFFC
DOCUMENT_CONTROL_TYPE = 50030
EDIT_CONTROL_TYPE = 50004


def topWindows():
	found = []

	def visit(handle, _):
		if win32gui.IsWindowVisible(handle) and win32gui.GetWindowText(handle):
			found.append((handle, win32process.GetWindowThreadProcessId(handle)[1], win32gui.GetWindowText(handle)))

	win32gui.EnumWindows(visit, None)
	return found


def exeOf(pid):
	process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
	if not process:
		return ""
	buffer = ctypes.create_unicode_buffer(520)
	size = ctypes.wintypes.DWORD(520)
	ctypes.windll.kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size))
	ctypes.windll.kernel32.CloseHandle(process)
	return buffer.value.lower()


def bringToFront(exe, title, timeout=40):
	"""The window of the program ``exe`` (a part of its path) whose title has ``title``, in front; or None."""
	end = time.time() + timeout
	while time.time() < end:
		for handle, pid, text in topWindows():
			if exe in exeOf(pid) and title.lower() in text.lower() and not text.startswith("QuickSettings"):
				win32gui.ShowWindow(handle, win32con.SW_RESTORE)
				win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
				win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
				try:
					win32gui.SetForegroundWindow(handle)
				except Exception:
					pass
				return handle
		time.sleep(1)
	return None


def focusedControlType():
	from comtypes.gen import UIAutomationClient as automation

	comtypes.client.GetModule("UIAutomationCore.dll")
	client = comtypes.client.CreateObject("{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=automation.IUIAutomation)
	return client.GetFocusedElement().CurrentControlType


def press(code):
	win32api.keybd_event(code, 0, 0, 0)
	win32api.keybd_event(code, 0, win32con.KEYEVENTF_KEYUP, 0)


def focusWebPage():
	"""F6 goes round Edge's parts; stop when the focus is in the page."""
	for _ in range(10):
		time.sleep(0.8)
		if focusedControlType() == DOCUMENT_CONTROL_TYPE:
			return True
		press(win32con.VK_F6)
	return False


def focusAddressBar():
	win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
	press(ord("L"))
	win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
	time.sleep(1)
	return focusedControlType() == EDIT_CONTROL_TYPE


def accessible(handle):
	pointer = ctypes.POINTER(Accessibility.IAccessible)()
	ctypes.oledll.oleacc.AccessibleObjectFromWindow(handle, OBJID_CLIENT, ctypes.byref(Accessibility.IAccessible._iid_), ctypes.byref(pointer))
	return pointer


def quickSettingsWindow():
	found = []

	def visit(handle, _):
		if win32gui.IsWindowVisible(handle) and win32gui.GetWindowText(handle).startswith("QuickSettings - "):
			found.append(handle)

	win32gui.EnumWindows(visit, None)
	return found[0] if found else None


def readAndCancel(window):
	"""``(title, application list, rows of the tree)`` of the window; then Cancel."""
	children = []
	win32gui.EnumChildWindows(window, lambda handle, _: children.append((handle, win32gui.GetClassName(handle), win32gui.GetWindowText(handle))), None)
	tree = next(handle for handle, name, _text in children if name == "FeatureTree")
	root = accessible(tree)
	rows = []
	for number in range(1, root.accChildCount + 1):
		rows.append(root.accName(number))
	combo = next(handle for handle, name, _text in children if name == "ComboBox")
	applications = []
	for index in range(win32gui.SendMessage(combo, win32con.CB_GETCOUNT, 0, 0)):
		length = win32gui.SendMessage(combo, win32con.CB_GETLBTEXTLEN, index, 0)
		buffer = ctypes.create_unicode_buffer(length + 2)
		ctypes.windll.user32.SendMessageW(combo, win32con.CB_GETLBTEXT, index, buffer)
		applications.append(buffer.value)
	title = win32gui.GetWindowText(window)
	cancel = next(handle for handle, name, text in children if name == "Button" and text == "Cancel")
	win32gui.SendMessage(cancel, win32con.BM_CLICK, 0, 0)
	return title, applications, rows


def runQuickSettings():
	api = win32com.client.Dispatch("FreedomSci.JawsApi")
	api.RunScript("QuickSettings")
	end = time.time() + 20
	while time.time() < end:
		window = quickSettingsWindow()
		if window:
			time.sleep(2)
			return window
		time.sleep(1)
	return None


def isRunning(image):
	output = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}"], capture_output=True, text=True).stdout
	return image.lower() in output.lower()


def closeWindows(exe, title):
	for handle, pid, text in topWindows():
		if exe in exeOf(pid) and title.lower() in text.lower():
			win32gui.PostMessage(handle, win32con.WM_CLOSE, 0, 0)


def scenarios():
	def notepad():
		subprocess.Popen(["notepad.exe"])
		handle = bringToFront("notepad.exe", "Notepad")
		return handle is not None, lambda: closeWindows("notepad.exe", "Untitled")

	def edgePage(focus):
		subprocess.Popen([EDGE, "--new-window", PAGE])
		handle = bringToFront("msedge.exe", "QS test page")
		time.sleep(2)
		return handle is not None and focus(), lambda: closeWindows("msedge.exe", "QS test page")

	def olk():
		# Outlook the person already has open is left open: only a window this started is closed.
		wasOpen = isRunning("olk.exe")
		if not wasOpen:
			subprocess.Popen(["explorer.exe", "shell:appsFolder\\Microsoft.OutlookForWindows_8wekyb3d8bbwe!Microsoft.OutlookForWindows"])
		handle = bringToFront("olk.exe", "Outlook", timeout=60)
		time.sleep(5)
		return handle is not None, (lambda: None) if wasOpen else (lambda: closeWindows("olk.exe", "Outlook"))

	return {
		"notepad": notepad,
		"edge-page": lambda: edgePage(focusWebPage),
		"edge-window": lambda: edgePage(focusAddressBar),
		"olk": olk,
	}


def main(names):
	started = False
	if not isRunning("jfw.exe"):
		os.startfile(JAWS)  # ShellExecute: jfw.exe asks Windows for its rights, which CreateProcess refuses
		started = True
		time.sleep(25)
	available = scenarios()
	result = {"jaws": os.path.basename(os.path.dirname(JAWS)), "scenarios": {}}
	for name in names or available:
		print("==", name)
		ready, cleanup = available[name]()
		try:
			if not ready:
				print("   the program or its focus was not ready")
				continue
			window = runQuickSettings()
			if window is None:
				print("   no QuickSettings window")
				continue
			title, applications, rows = readAndCancel(window)
			result["scenarios"][name] = {"title": title, "applications": applications, "rows": rows}
			print("  ", title, len(rows), "rows")
		finally:
			time.sleep(1.5)
			cleanup()
			time.sleep(1)
	with open(RESULT, "w", encoding="utf-8") as stream:
		json.dump(result, stream, indent="\t", ensure_ascii=False)
	if started:
		win32com.client.Dispatch("FreedomSci.JawsApi").RunScript("ShutDownJAWS")


if __name__ == "__main__":
	main(sys.argv[1:])
