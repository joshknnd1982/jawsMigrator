# Minimal stand-ins for the NVDA modules the add-on imports at load time, so its
# pure modules and dialogs can be tested with a normal Python and wxPython.

import logging
import os
import sys
import types

ADDON_ROOT = os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins")
spoken = []
boxes = []


def install(frame=None):
	if ADDON_ROOT not in sys.path:
		sys.path.insert(0, ADDON_ROOT)

	def module(name, **attributes):
		stub = sys.modules.get(name) or types.ModuleType(name)
		for key, value in attributes.items():
			setattr(stub, key, value)
		sys.modules[name] = stub
		return stub

	log = logging.getLogger("nvda")
	log.debugWarning = log.debug
	log.io = log.debug
	module("logHandler", log=log)
	module("ui", message=lambda text: spoken.append(text))
	module("tones", beep=lambda *args, **kwargs: None)

	def initTranslation():
		return None

	def getCodeAddon():
		raise RuntimeError("not running as an add-on")

	module("addonHandler", initTranslation=initTranslation, getCodeAddon=getCodeAddon, getAvailableAddons=lambda: [])

	class GlobalPlugin:
		def __init__(self):
			self._gestureMap = {}

		def getScript(self, gesture):
			return None

		def bindGestures(self, gestures):
			pass

		def clearGestureBindings(self):
			pass

		def terminate(self):
			pass

	module("globalPluginHandler", GlobalPlugin=GlobalPlugin)

	def script(**kwargs):
		def decorate(function):
			function.__doc__ = kwargs.get("description", function.__doc__)
			return function

		return decorate

	module("scriptHandler", script=script, findScript=lambda gesture: None)

	class GestureMap:
		def __init__(self):
			self._map = {}

	class Manager:
		userGestureMap = GestureMap()
		localeGestureMap = GestureMap()
		_captureFunc = None

	class Decider:
		"""NVDA's extensionPoints.Decider: NVDA goes on only when every handler returns True."""

		def __init__(self):
			self.handlers = []

		def register(self, handler):
			if handler not in self.handlers:
				self.handlers.append(handler)

		def unregister(self, handler):
			if handler in self.handlers:
				self.handlers.remove(handler)

		def decide(self, **kwargs):
			return all([handler(**kwargs) for handler in list(self.handlers)])

	# Installed once: the add-on's modules keep what they registered with it.
	decider = getattr(sys.modules.get("inputCore"), "decide_executeGesture", None) or Decider()
	module("inputCore", manager=Manager(), normalizeGestureIdentifier=lambda identifier: identifier.lower(), decide_executeGesture=decider)
	module("gui", mainFrame=None, messageBox=lambda *args, **kwargs: None)
	if frame is not None:
		frame.prePopup = lambda: None
		frame.postPopup = lambda: None

		def messageBox(message, caption="", style=0, parent=None):
			import wx

			boxes.append(message)
			return wx.YES if style & wx.YES else wx.OK

		module("gui", mainFrame=frame, messageBox=messageBox)
