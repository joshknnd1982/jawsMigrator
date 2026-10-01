# Test driver for a second NVDA on a private desktop (issue 47 tooling, never shipped).
#
# SAFETY: this NVDA runs on its own Windows desktop, but the mouse pointer belongs to the whole window station and
# keybd_event/mouse_event go to the interactive desktop. So the first thing this module does is replace every function
# NVDA uses to inject input with one that only records. Nothing here may send a key or a click to the real desktop.
# For the same reason, NEVER put this in the scratchpad of an NVDA you use: while it is loaded that NVDA can't send a key
# or a click at all (its Say All, the add-on's remote keys, a press on a suggestion would silently do nothing).

import json
import os
import time
import traceback

import globalVars
import winUser

SENT = []
_CURSOR = list(winUser.getCursorPos())


def _keybd_event(vk, scan, flags, extra=0):
	SENT.append({"kind": "key", "vk": vk, "scan": scan, "flags": flags})


def _mouse_event(flags, x, y, data=0, extra=0):
	SENT.append({"kind": "mouse", "flags": flags, "cursor": list(_CURSOR)})


def _setCursorPos(x, y):
	_CURSOR[0], _CURSOR[1] = x, y
	SENT.append({"kind": "cursor", "x": x, "y": y})


def _getCursorPos():
	return list(_CURSOR)


def _sendInput(inputs):
	SENT.append({"kind": "sendinput", "count": len(inputs)})


winUser.keybd_event = _keybd_event
winUser.mouse_event = _mouse_event
winUser.setCursorPos = _setCursorPos
winUser.getCursorPos = _getCursorPos
winUser.SendInput = _sendInput

import api  # noqa: E402
import baseObject  # noqa: E402
import browseMode  # noqa: E402
import controlTypes  # noqa: E402
import core  # noqa: E402
import globalPluginHandler  # noqa: E402
import inputCore  # noqa: E402
import keyboardHandler  # noqa: E402
import scriptHandler  # noqa: E402
import textInfos  # noqa: E402
from logHandler import log  # noqa: E402

DIR = os.path.join(globalVars.appArgs.configPath, "driver")
os.makedirs(DIR, exist_ok=True)
CMD = os.path.join(DIR, "cmd.json")
RES = os.path.join(DIR, "res.json")


def stateNames(states):
	try:
		return sorted(s.name for s in states)
	except Exception:
		return str(states)


def describe(obj, deep=False):
	if obj is None:
		return None
	out = {}
	for key in ("role", "name", "value", "description"):
		try:
			value = getattr(obj, key)
			out[key] = value.name if hasattr(value, "name") and key == "role" else value
		except Exception as e:
			out[key] = f"<{type(e).__name__}: {e}>"
	try:
		out["states"] = stateNames(obj.states)
	except Exception as e:
		out["states"] = f"<{e}>"
	try:
		loc = obj.location
		out["location"] = list(loc) if loc else None
	except Exception as e:
		out["location"] = f"<{e}>"
	try:
		out["class"] = [c.__name__ for c in type(obj).__mro__[:4]]
	except Exception:
		pass
	try:
		out["hasIrrelevantLocation"] = obj.hasIrrelevantLocation
	except Exception as e:
		out["hasIrrelevantLocation"] = f"<{e}>"
	if deep:
		try:
			out["IA2Attributes"] = dict(obj.IA2Attributes)
		except Exception as e:
			out["IA2Attributes"] = f"<{e}>"
		try:
			out["controllerFor"] = [describe(c) for c in (obj.controllerFor or [])]
		except Exception as e:
			out["controllerFor"] = f"<{type(e).__name__}: {e}>"
	return out


def lineAt(document, position=textInfos.POSITION_CARET):
	info = document.makeTextInfo(position)
	info.expand(textInfos.UNIT_LINE)
	return info.text


def neighbourLines(document, before=3, after=8):
	lines = []
	info = document.makeTextInfo(textInfos.POSITION_CARET)
	info.collapse()
	cursor = info.copy()
	cursor.expand(textInfos.UNIT_LINE)
	here = cursor.text
	back = info.copy()
	back.collapse()
	prior = []
	for _ in range(before):
		if not back.move(textInfos.UNIT_LINE, -1):
			break
		line = back.copy()
		line.expand(textInfos.UNIT_LINE)
		prior.append(line.text)
	prior.reverse()
	forward = []
	fwd = info.copy()
	fwd.collapse()
	for _ in range(after):
		if not fwd.move(textInfos.UNIT_LINE, 1):
			break
		line = fwd.copy()
		line.expand(textInfos.UNIT_LINE)
		forward.append(line.text)
	return {"before": prior, "here": here, "after": forward}


def docInfo(obj):
	document = getattr(obj, "treeInterceptor", None)
	if document is None:
		return None
	out = {"isReady": getattr(document, "isReady", None), "passThrough": getattr(document, "passThrough", None)}
	try:
		out["caretLine"] = lineAt(document)
	except Exception as e:
		out["caretLine"] = f"<{type(e).__name__}: {e}>"
	try:
		caret = document.makeTextInfo(textInfos.POSITION_CARET)
		out["caretObj"] = describe(caret.NVDAObjectAtStart)
		out["caretFocusable"] = describe(caret.focusableNVDAObjectAtStart)
	except Exception as e:
		out["caretObj"] = f"<{type(e).__name__}: {e}>"
	return out


def _windows():
	"""Top-level windows of this desktop: [(hwnd, class, title)]."""
	import ctypes
	from ctypes import wintypes

	user32 = ctypes.windll.user32
	found = []
	proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

	def cb(hwnd, lparam):
		cls = ctypes.create_unicode_buffer(256)
		user32.GetClassNameW(hwnd, cls, 255)
		title = ctypes.create_unicode_buffer(256)
		user32.GetWindowTextW(hwnd, title, 255)
		found.append((hwnd, cls.value, title.value, bool(user32.IsWindowVisible(hwnd))))
		return True

	user32.EnumWindows(proc(cb), 0)
	return found


def _children(parent):
	import ctypes
	from ctypes import wintypes

	user32 = ctypes.windll.user32
	found = []
	proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

	def cb(hwnd, lparam):
		cls = ctypes.create_unicode_buffer(256)
		user32.GetClassNameW(hwnd, cls, 255)
		found.append((hwnd, cls.value))
		return True

	user32.EnumChildWindows(parent, proc(cb), 0)
	return found


def edgeWindows():
	top = [w for w in _windows() if w[1] == "Chrome_WidgetWin_1" and "Edge" in w[2] and w[3]]
	if not top:
		return None, None
	hwnd = top[0][0]
	render = [c for c in _children(hwnd) if c[1] == "Chrome_RenderWidgetHostHWND"]
	return hwnd, (render[0][0] if render else None)


def findIn(root, test, limit=4000):
	"""Breadth-first search below an NVDAObject: the first object test() accepts."""
	queue = [root]
	seen = 0
	while queue and seen < limit:
		obj = queue.pop(0)
		seen += 1
		try:
			if test(obj):
				return obj
		except Exception:
			pass
		try:
			queue.extend(obj.children)
		except Exception:
			pass
	return None


def syncFocus(find=None):
	"""Tell NVDA what Edge's page has focus on, as its WinEvent handler would (this desktop has no foreground window)."""
	import eventHandler
	import NVDAObjects.IAccessible as ia

	top, render = edgeWindows()
	if not render:
		return {"error": "no render widget", "top": top}
	root = ia.getNVDAObjectFromEvent(render, winUser.OBJID_CLIENT, 0)
	out = {"top": top, "render": render, "root": describe(root)}
	focus = None
	try:
		raw = root.IAccessibleObject.accFocus
		out["rawAccFocus"] = str(raw)
	except Exception as e:
		out["rawAccFocus"] = f"<{type(e).__name__}: {e}>"
	if find:
		focus = findIn(root, lambda o: o.role == controlTypes.Role.EDITABLETEXT and find in (o.name or ""))
		out["found"] = describe(focus, deep=True)
	if focus is None:
		focus = root
	topObj = ia.getNVDAObjectFromEvent(top, winUser.OBJID_WINDOW, 0)
	eventHandler.queueEvent("foreground", topObj)
	eventHandler.queueEvent("gainFocus", focus)
	return out


def doOp(command):
	op = command["op"]
	if op == "ping":
		return {"pong": True}
	if op == "focus":
		focus = api.getFocusObject()
		out = {"focus": describe(focus, deep=True), "doc": docInfo(focus)}
		try:
			out["foreground"] = describe(api.getForegroundObject())
		except Exception as e:
			out["foreground"] = f"<{e}>"
		return out
	if op == "lines":
		focus = api.getFocusObject()
		document = getattr(focus, "treeInterceptor", None)
		if document is None:
			return {"error": "no tree interceptor"}
		return neighbourLines(document, command.get("before", 3), command.get("after", 8))
	if op == "sent":
		taken = list(SENT)
		if command.get("clear", True):
			SENT.clear()
		return {"sent": taken}
	if op == "clear":
		SENT.clear()
		return {"cleared": True}
	if op == "gesture":
		name = command["name"]
		SENT.clear()
		log.info(f"DRIVER gesture {name}")
		gesture = keyboardHandler.KeyboardInputGesture.fromName(name)
		out = {"identifiers": list(gesture.identifiers)[:3]}
		out["script"] = "(found on the hook thread)"
		# As NVDA does it: the keyboard hook's thread looks for the script (and queues it for the main thread). A plain thread
		# is the same for COM: NVDA's main thread is an STA, so its objects can't be used from here.
		import threading

		box = {}

		def hook():
			try:
				inputCore.manager.executeGesture(gesture)
				box["handled"] = True
			except inputCore.NoInputGestureAction:
				box["handled"] = False
			except BaseException:
				import traceback as tb
				box["error"] = tb.format_exc()
			box["thread"] = threading.current_thread().name

		thread = threading.Thread(target=hook, name="winInputHook")
		thread.start()
		thread.join(30)
		out["handled"] = box.get("handled")
		out["hookThread"] = box.get("thread")
		if "error" in box:
			out["error"] = box["error"]
		out["passedThrough"] = not out["handled"]
		return out
	if op == "scriptFor":
		# What the add-on's Down Arrow decision says right now, with the pieces it looks at.
		from globalPlugins.jawsMigrator import suggestionLists  # noqa

		name = command.get("name", "downArrow")
		gesture = keyboardHandler.KeyboardInputGesture.fromName(name)
		field = api.getFocusObject()
		out = {"gesture": list(gesture.identifiers)[:2], "mainKeyName": gesture.mainKeyName, "modifiers": str(gesture.modifiers)}
		try:
			out["suggestingField"] = suggestionLists._suggestingField(field)
		except Exception as e:
			out["suggestingField"] = f"<{type(e).__name__}: {e}>"
		try:
			controls = suggestionLists._controls(field)
			out["controls"] = [describe(c) for c in controls]
			out["hasSuggestions"] = suggestionLists._hasSuggestions(field)
		except Exception as e:
			out["controls"] = f"<{type(e).__name__}: {e}>"
		out["scriptFor"] = str(suggestionLists.scriptFor(gesture))
		return out
	if op == "inThread":
		# Run code on another thread, as NVDA's keyboard hook runs the search for a script (the tester's log: executeGesture is on winInputHook).
		import threading
		import time as _time

		box = {}

		def runner():
			scope = {"api": api, "describe": describe, "controlTypes": controlTypes, "keyboardHandler": keyboardHandler, "scriptHandler": scriptHandler, "globalPluginHandler": globalPluginHandler, "inputCore": inputCore, "textInfos": textInfos}
			start = _time.perf_counter()
			try:
				exec(command["code"], scope)
				box["result"] = scope.get("result")
			except BaseException as e:
				import traceback as tb
				box["error"] = tb.format_exc()
			box["ms"] = round((_time.perf_counter() - start) * 1000, 1)
			box["thread"] = threading.current_thread().name

		thread = threading.Thread(target=runner, name="fakeHook")
		thread.start()
		thread.join(30)
		return box
	if op == "syncFocus":
		return syncFocus(command.get("find"))
	if op == "edge":
		return {"edge": edgeWindows()}
	if op == "eval":
		scope = {"api": api, "describe": describe, "log": log}
		exec(command["code"], scope)
		return {"result": scope.get("result")}
	return {"error": f"unknown op {op}"}


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super().__init__()
		log.info("DRIVER loaded; input injection is recorded, not sent")
		self._last = None
		core.callLater(500, self._poll)

	def _poll(self):
		try:
			if os.path.exists(CMD):
				with open(CMD, encoding="utf-8") as stream:
					command = json.load(stream)
				if command.get("id") != self._last:
					self._last = command.get("id")
					try:
						result = doOp(command)
					except Exception:
						result = {"error": traceback.format_exc()}
					path = os.path.join(DIR, "res-%s.json" % command.get("id"))
					with open(path + ".tmp", "w", encoding="utf-8") as stream:
						json.dump({"id": command.get("id"), "result": result}, stream, default=str)
					os.rename(path + ".tmp", path)
		except Exception:
			log.error("DRIVER poll failed", exc_info=True)
		core.callLater(150, self._poll)
