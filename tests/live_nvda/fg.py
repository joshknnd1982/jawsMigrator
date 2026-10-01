"""Runs ON the private desktop: lists its windows and brings Edge to the foreground (no input injection)."""
import ctypes
import os
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
out = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fg.out"), "w", encoding="utf-8")


def say(text):
	out.write(text + "\n")
	out.flush()


WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
found = []


def cb(hwnd, lparam):
	buf = ctypes.create_unicode_buffer(256)
	user32.GetClassNameW(hwnd, buf, 255)
	cls = buf.value
	title = ctypes.create_unicode_buffer(256)
	user32.GetWindowTextW(hwnd, title, 255)
	visible = bool(user32.IsWindowVisible(hwnd))
	say(f"hwnd={hwnd} class={cls!r} title={title.value!r} visible={visible}")
	if cls == "Chrome_WidgetWin_1" and visible:
		found.append(hwnd)
	return True


desktop = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
name = ctypes.create_unicode_buffer(256)
needed = wintypes.DWORD()
user32.GetUserObjectInformationW(desktop, 2, name, 512, ctypes.byref(needed))
say(f"running on desktop {name.value!r}")
user32.EnumWindows(WNDENUMPROC(cb), 0)
say(f"candidates: {found}")
for hwnd in found:
	user32.ShowWindow(hwnd, 9)
	user32.SwitchToThisWindow(hwnd, True)
	user32.BringWindowToTop(hwnd)
	user32.SetForegroundWindow(hwnd)
	time.sleep(0.5)
	say(f"foreground now: {user32.GetForegroundWindow()}")
