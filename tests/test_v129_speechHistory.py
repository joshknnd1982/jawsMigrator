# Unit tests for version 1.29, from a tester's issue 28, "Making speech history easier": "I find the speech history
# a pain to use." The tester tells us what NVDA said with the Speech History add-on (2026.1): Shift+F11 and Shift+F12
# go back and forth one thing at a time, and F12 copies the one thing it is on; its NVDA+H list shows the newest first.
# JAWS keeps the last 500 things it said. Insert+Space, H opens them in its Results Viewer, titled "Speech History",
# on the line of the most recent one, the oldest first. Insert+Space, Control+H copies all of them, and Insert+Space,
# Shift+H clears them (JAWS 2026's Default.JKM and Default.jss; JAWS's training says 500).
# - speechHistory: NVDA+Shift+J, then H, Control+H and Shift+H do the same, and ? (JAWS's key for the layer's help)
#   or F1 lists the layer's commands. What NVDA says comes through NVDA's own speech.extensions.pre_speech, after every
#   add-on's filter (ClassicSpeech's too), one line each time NVDA speaks. JAWS's [Options] SpeechHistory comes over
#   in a migration, and NVDA's Settings, JAWS Migration Assistant can turn it off.
# NVDA 2026.2's own code runs here, word for word: extensionPoints (HandlerRegistrar, callWithSupportedKwargs, Action
# and Filter), speech.extensions' pre_speech and filter_speechSequence, speech.speak, speakMessage and isBlank,
# ui.message, api.copyToClip and getClipData, winUser's clipboard functions and winKernel.HGLOBAL with the ctypes
# prototypes of winBindings, so the text goes on Windows' own clipboard and back; and EditTextInfo's
# _getSelectionOffsets, _getCaretOffset, _getLineOffsets, _getLineNumFromOffset and the rest, with
# OffsetsTextInfo._getTextRange, Window's windowText and textUtils' WideStringOffsetConverter, which read the line at
# the caret of the Speech History window's text box, as NVDA reads it when the window opens. What NVDA's speak does
# after pre_speech (the synthesizer) is imitated. The assistant's code is the real one: speechHistory, the plugin's
# layer, and settingsMap.
# Run: python -m unittest tests.test_v129_speechHistory -v

import __future__
import contextlib
import ctypes
import encodings
import enum
import inspect
import locale
import logging
import os
import sys
import textwrap
import time
import types
import unicodedata
import unittest
import weakref
from abc import ABCMeta, abstractmethod, abstractproperty
from ctypes import WINFUNCTYPE, c_size_t, c_wchar, windll, wstring_at
from ctypes.wintypes import BOOL, HANDLE, HGLOBAL, HWND, LPARAM, LPVOID, UINT, WPARAM
from functools import cached_property
from typing import Callable, Generator, Generic, Iterable, Optional, OrderedDict, Set, Tuple, Type, TypeVar, Union
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

import wx  # noqa: E402

import jawsMigrator  # noqa: E402
from jawsMigrator import jawsFiles, jawsKeyMap, settingsMap, speechHistory  # noqa: E402

# -- NVDA 2026.2's own code, word for word (see NvdasOwnCodeTests) -----------------------------------------------

NVDA_EXTENSION_POINTS_UTIL = 'HandlerT = TypeVar("HandlerT", bound=Callable)\n\n\nHandlerKeyT = Union[int, Tuple[int, int]]\n\n\nclass AnnotatableWeakref(weakref.ref, Generic[HandlerT]):\n\t"""A weakref.ref which allows annotation with custom attributes."""\n\n\thandlerKey: int\n\n\nclass BoundMethodWeakref(Generic[HandlerT]):\n\t"""Weakly references a bound instance method.\n\tInstance methods are bound dynamically each time they are fetched.\n\tweakref.ref on a bound instance method doesn\'t work because\n\tas soon as you drop the reference, the method object dies.\n\tInstead, this class holds weak references to both the instance and the function,\n\twhich can then be used to bind an instance method.\n\tTo get the actual method, you call an instance as you would a weakref.ref.\n\t"""\n\n\thandlerKey: Tuple[int, int]\n\n\tdef __init__(\n\t\tself,\n\t\ttarget: HandlerT,\n\t\tonDelete: Optional[Callable[[BoundMethodWeakref], None]] = None,\n\t):\n\t\tif onDelete:\n\n\t\t\tdef onRefDelete(weak):\n\t\t\t\t"""Calls onDelete for our BoundMethodWeakref when one of the individual weakrefs (instance or function) dies."""\n\t\t\t\tonDelete(self)\n\t\telse:\n\t\t\tonRefDelete = None\n\t\tinst = target.__self__\n\t\tfunc = target.__func__\n\t\tself.weakInst = weakref.ref(inst, onRefDelete)\n\t\tself.weakFunc = weakref.ref(func, onRefDelete)\n\n\tdef __call__(self) -> Optional[HandlerT]:\n\t\tinst = self.weakInst()\n\t\tif not inst:\n\t\t\treturn\n\t\tfunc = self.weakFunc()\n\t\tassert func, "inst is alive but func is dead"\n\t\t# Get an instancemethod by binding func to inst.\n\t\treturn func.__get__(inst)\n\n\ndef _getHandlerKey(handler: Callable) -> HandlerKeyT:\n\t"""Get a key which identifies a handler function.\n\tThis is needed because we store weak references, not the actual functions.\n\tWe store the key on the weak reference.\n\tWhen the handler dies, we can use the key on the weak reference to remove the handler.\n\t"""\n\tinst = getattr(handler, "__self__", None)\n\tif inst:\n\t\treturn (id(inst), id(handler.__func__))\n\treturn id(handler)\n\n\nclass HandlerRegistrar(Generic[HandlerT]):\n\t"""Base class to Facilitate registration and unregistration of handler functions.\n\tThe handlers are stored using weak references and are automatically unregistered\n\tif the handler dies.\n\tBoth normal functions, instance methods and lambdas are supported. Ensure to keep lambdas alive by maintaining a\n\treference to them.\n\tThe handlers are maintained in the order they were registered\n\tso that they can be called in a deterministic order across runs.\n\tThis class doesn\'t provide any functionality to actually call the handlers.\n\tIf you want to implement an extension point,\n\tyou probably want the L{Action} or L{Filter} subclasses instead.\n\t"""\n\n\tdef __init__(self, *, _deprecationMessage: str | None = None):\n\t\t"""Initialise the handler registrar.\n\n\t\t:param _deprecationMessage: Optional deprecation message to be logged when :method:`register` is called on the handler.\n\t\t"""\n\t\tself._deprecationMessage = _deprecationMessage\n\t\t#: Registered handler functions.\n\t\t#: This is an OrderedDict where the keys are unique identifiers (as returned by _getHandlerKey)\n\t\t#: and the values are weak references.\n\t\tself._handlers = OrderedDict[\n\t\t\tHandlerKeyT,\n\t\t\tUnion[BoundMethodWeakref[HandlerT], AnnotatableWeakref[HandlerT]],\n\t\t]()\n\n\tdef register(self, handler: HandlerT):\n\t\t"""You can register functions, bound instance methods, class methods, static methods or lambdas.\n\t\tHowever, the callable must be kept alive by your code otherwise it will be de-registered.\n\t\tThis is due to the use of weak references.\n\t\tThis is especially relevant when using lambdas.\n\t\t"""\n\t\tif inspect.isfunction(handler):\n\t\t\tsig = inspect.signature(handler)\n\t\t\tif sig.parameters and list(sig.parameters)[0] == "self":\n\t\t\t\traise TypeError("Registering unbound instance methods not supported.")\n\t\tif self._deprecationMessage:\n\t\t\tif NVDAState._allowDeprecatedAPI():\n\t\t\t\tlog.warning(self._deprecationMessage, stack_info=True)\n\t\t\telse:\n\t\t\t\traise RuntimeError(self._deprecationMessage)\n\t\tif inspect.ismethod(handler):\n\t\t\tweak = BoundMethodWeakref(handler, self.unregister)\n\t\telse:\n\t\t\tweak = AnnotatableWeakref(handler, self.unregister)\n\t\tkey = _getHandlerKey(handler)\n\t\t# Store the key on the weakref so we can remove the handler when it dies.\n\t\tweak.handlerKey = key\n\t\tself._handlers[key] = weak\n\n\tdef moveToEnd(self, handler: HandlerT, last: bool = False) -> bool:\n\t\t"""Move a registered handler to the start or end of the collection with registered handlers.\n\t\tThis can be used to modify the order in which handlers are called.\n\t\t@param last: Whether to move the handler to the end.\n\t\t\tIf C{False} (default), the handler is moved to the start.\n\t\t@returns: Whether the handler was found.\n\t\t"""\n\t\tif isinstance(handler, (AnnotatableWeakref, BoundMethodWeakref)):\n\t\t\tkey = handler.handlerKey\n\t\telse:\n\t\t\tkey = _getHandlerKey(handler)\n\t\ttry:\n\t\t\tself._handlers.move_to_end(key=key, last=last)\n\t\texcept KeyError:\n\t\t\treturn False\n\t\treturn True\n\n\tdef unregister(\n\t\tself,\n\t\thandler: Union[AnnotatableWeakref[HandlerT], BoundMethodWeakref[HandlerT], HandlerT],\n\t):\n\t\tif isinstance(handler, (AnnotatableWeakref, BoundMethodWeakref)):\n\t\t\tkey = handler.handlerKey\n\t\telse:\n\t\t\tkey = _getHandlerKey(handler)\n\t\ttry:\n\t\t\tdel self._handlers[key]\n\t\texcept KeyError:\n\t\t\treturn False\n\t\treturn True\n\n\t@property\n\tdef handlers(self) -> Generator[HandlerT, None, None]:\n\t\t"""Generator of registered handler functions.\n\t\tThis should be used when you want to call the handlers.\n\t\t"""\n\t\tfor weak in self._handlers.values():\n\t\t\thandler = weak()\n\t\t\tif not handler:\n\t\t\t\tcontinue  # Died.\n\t\t\tyield handler\n\n\ndef callWithSupportedKwargs(func, *args, **kwargs):\n\t"""Call a function with only the keyword arguments it supports.\n\tFor example, if myFunc is defined as:\n\tC{def myFunc(a=None, b=None):}\n\tand you call:\n\tC{callWithSupportedKwargs(myFunc, a=1, b=2, c=3)}\n\tInstead of raising a TypeError, myFunc will simply be called like this:\n\tC{myFunc(a=1, b=2)}\n\n\tC{callWithSupportedKwargs} does support positional arguments (C{*args}).\n\tUnfortunately, positional args can not be matched on name (keyword)\n\tto the names of the params in the handler.\n\tTherefore, usage is strongly discouraged due to the\n\trisk of parameter order differences causing bugs.\n\n\t@param func: can be any callable that is not an unbound method. EG:\n\t\t- Bound instance methods\n\t\t- class methods\n\t\t- static methods\n\t\t- functions\n\t\t- lambdas\n\t\t- partials\n\n\t\tThe arguments for the supplied callable, C{func}, do not need to have default values, and can take C{**kwargs} to\n\t\tcapture all arguments.\n\t\tSee C{tests/unit/test_extensionPoints.py:TestCallWithSupportedKwargs} for examples.\n\n\t\tAn exception is raised if:\n\t\t\t- the number of positional arguments given can not be received by C{func}.\n\t\t\t- parameters required (parameters declared with no default value) by C{func} are not supplied.\n\t"""\n\tsig = inspect.signature(func)\n\n\tif inspect.isfunction(func) and sig.parameters and list(sig.parameters)[0] == "self":\n\t\traise TypeError("Unbound instance methods are not handled.")\n\n\t# Check whether func has a catch-all for kwargs (**kwargs)\n\t# In this case, we do not need to filter to just the supported args.\n\tif not any(param for param in sig.parameters.values() if param.kind == param.VAR_KEYWORD):\n\t\t# Delete all the kwargs that are not supported by this callable.\n\t\t# Wrap the items call in a list, as the dictionary changes during iteration.\n\t\tfor kwarg in list(kwargs.keys()):\n\t\t\tif kwarg not in sig.parameters:\n\t\t\t\tdel kwargs[kwarg]\n\n\tboundArguments = sig.bind(*args, **kwargs)\n\treturn func(*boundArguments.args, **boundArguments.kwargs)'

NVDA_EXTENSION_POINTS = 'class Action(HandlerRegistrar[Callable[..., None]]):\n\t"""Allows interested parties to register to be notified when some action occurs.\n\tFor example, this might be used to notify that the configuration profile has been switched.\n\n\tFirst, an Action is created:\n\n\t>>> somethingHappened = extensionPoints.Action()\n\n\tInterested parties then register to be notified about this action, see\n\tL{register} docstring for details of the type of handlers that can be\n\tregistered:\n\n\t>>> def onSomethingHappened(someArg=None):\n\t\t... \tprint(someArg)\n\t...\n\t>>> somethingHappened.register(onSomethingHappened)\n\n\tWhen the action is performed, register handlers are notified, see L{util.callWithSupportedKwargs}\n\tfor how args passed to notify are mapped to the handler:\n\n\t>>> somethingHappened.notify(someArg=42)\n\t"""\n\n\tdef notify(self, **kwargs):\n\t\t"""Notify all registered handlers that the action has occurred.\n\t\t@param kwargs: Arguments to pass to the handlers.\n\t\t"""\n\t\tfor handler in self.handlers:\n\t\t\ttry:\n\t\t\t\tcallWithSupportedKwargs(handler, **kwargs)\n\t\t\texcept:  # noqa: E722\n\t\t\t\tlog.exception("Error running handler %r for %r" % (handler, self))\n\n\tdef notifyOnce(self, **kwargs):\n\t\t"""Notify all registered handlers that the action has occurred.\n\t\tUnregister handlers after calling.\n\t\t@param kwargs: Arguments to pass to the handlers.\n\t\t"""\n\t\toldHandlers = list(self.handlers)\n\t\tfor handler in oldHandlers:\n\t\t\ttry:\n\t\t\t\tcallWithSupportedKwargs(handler, **kwargs)\n\t\t\t\tself.unregister(handler)\n\t\t\texcept Exception as e:\n\t\t\t\tlog.exception(f"Error running handler {handler} for {self}. Exception {e}")\n\n\nFilterValueT = TypeVar("FilterValueT")\n\n\nclass Filter(\n\tHandlerRegistrar[Union[Callable[..., FilterValueT], Callable[[FilterValueT], FilterValueT]]],\n\tGeneric[FilterValueT],\n):\n\t"""Allows interested parties to register to modify a specific kind of data.\n\tFor example, this might be used to allow modification of spoken messages before they are passed to the synthesizer.\n\n\tFirst, a Filter is created:\n\n\t>>> import extensionPoints\n\t>>> messageFilter = extensionPoints.Filter[str]()\n\n\tInterested parties then register to filter the data, see\n\tL{register} docstring for details of the type of handlers that can be\n\tregistered:\n\n\t>>> def filterMessage(message: str, someArg=None) -> str:\n\t... \treturn message + " which has been filtered."\n\t...\n\t>>> messageFilter.register(filterMessage)\n\n\tWhen filtering is desired, all registered handlers are called to filter the data, see L{util.callWithSupportedKwargs}\n\tfor how args passed to apply are mapped to the handler:\n\n\t>>> messageFilter.apply("This is a message", someArg=42)\n\t\'This is a message which has been filtered\'\n\t"""\n\n\tdef apply(self, value: FilterValueT, **kwargs) -> FilterValueT:\n\t\t"""Pass a value to be filtered through all registered handlers.\n\t\tThe value is passed to the first handler\n\t\tand the return value from that handler is passed to the next handler.\n\t\tThis process continues for all handlers until the final handler.\n\t\tThe return value from the final handler is returned to the caller.\n\t\t@param value: The value to be filtered.\n\t\t@param kwargs: Arguments to pass to the handlers.\n\t\t@return: The filtered value.\n\t\t"""\n\t\tfor handler in self.handlers:\n\t\t\ttry:\n\t\t\t\tvalue = callWithSupportedKwargs(handler, value, **kwargs)\n\t\t\texcept:  # noqa: E722\n\t\t\t\tlog.exception("Error running handler %r for %r" % (handler, self))\n\t\treturn value'

NVDA_SPEECH_EXTENSIONS = 'pre_speech = Action()\n\n\nfilter_speechSequence = Filter[SpeechSequence]()'

NVDA_SPEAK = 'BLANK_CHUNK_CHARS = frozenset((" ", "\\n", "\\r", "\\0", "\\xa0"))\n\n\ndef isBlank(text):\n\t"""Determine whether text should be reported as blank.\n\t@param text: The text in question.\n\t@type text: str\n\t@return: C{True} if the text is blank, C{False} if not.\n\t@rtype: bool\n\t"""\n\treturn not text or set(text) <= BLANK_CHUNK_CHARS\n\n\ndef _getSpeakMessageSpeech(\n\ttext: str,\n) -> SpeechSequence:\n\t"""Gets the speech sequence for a given message.\n\t@param text: the message to speak\n\t"""\n\tif text is None:\n\t\treturn []\n\tif isBlank(text):\n\t\treturn [\n\t\t\t# Translators: This is spoken when the line is considered blank.\n\t\t\t_("blank"),\n\t\t]\n\treturn [text]\n\n\ndef speakMessage(\n\ttext: str,\n\tpriority: Optional[Spri] = None,\n) -> None:\n\t"""Speaks a given message.\n\t@param text: the message to speak\n\t@param priority: The speech priority.\n\t"""\n\tseq = _getSpeakMessageSpeech(text)\n\tif seq:\n\t\tspeak(seq, symbolLevel=None, priority=priority)\n\n\ndef speak(  # noqa: C901\n\tspeechSequence: SpeechSequence,\n\tsymbolLevel: characterProcessing.SymbolLevel | None = None,\n\tpriority: Spri = Spri.NORMAL,\n):\n\t"""Speaks a sequence of text and speech commands\n\t@param speechSequence: the sequence of text and L{SpeechCommand} objects to speak\n\t@param symbolLevel: The symbol verbosity level; C{None} (default) to use the user\'s configuration.\n\t@param priority: The speech priority.\n\t"""\n\tspeechSequence = filter_speechSequence.apply(speechSequence)\n\tlogBadSequenceTypes(speechSequence)\n\t# in case priority was explicitly passed in as None, set to default.\n\tpriority: Spri = Spri.NORMAL if priority is None else priority\n\n\tif not speechSequence:  # Pointless - nothing to speak\n\t\treturn\n\timport speechViewer\n\n\tif speechViewer.isActive:\n\t\tspeechViewer.appendSpeechSequence(speechSequence)\n\tpre_speech.notify(speechSequence=speechSequence, symbolLevel=symbolLevel, priority=priority)\n\tif _speechState.speechMode == SpeechMode.off:\n\t\treturn\n\telif _speechState.speechMode == SpeechMode.beeps:\n\t\ttones.beep(config.conf["speech"]["beepSpeechModePitch"], _speechState.speechMode_beeps_ms)\n\t\treturn\n\tif _speechState.isPaused:\n\t\tcancelSpeech()\n\tif _speechState.speechMode == SpeechMode.onDemand:\n\t\timport inputCore\n\t\tfrom scriptHandler import getCurrentScript\n\t\tfrom .sayAll import SayAllHandler\n\n\t\tscript = getCurrentScript()\n\t\tif (\n\t\t\t(script and getattr(script, "speakOnDemand", False))\n\t\t\tor inputCore.manager.isInputHelpActive\n\t\t\tor (SayAllHandler.isRunning() and SayAllHandler.startedFromScript)\n\t\t):\n\t\t\tpass  # Do nothing and continue\n\t\telse:\n\t\t\treturn\n\t_speechState.beenCanceled = False\n\tautoDialectSwitching = config.conf["speech"]["autoDialectSwitching"]\n\tcurLanguage = defaultLanguage = getCurrentLanguage()\n\tprevLanguage = None\n\tdefaultLanguageRoot = defaultLanguage.split("_")[0]\n\tunicodeNormalization = initialUnicodeNormalization = config.conf["speech"]["unicodeNormalization"]\n\toldSpeechSequence = speechSequence\n\tspeechSequence = []\n\tfor item in oldSpeechSequence:\n\t\tif isinstance(item, LangChangeCommand):\n\t\t\tif not languageHandling.shouldMakeLangChangeCommand():\n\t\t\t\tcontinue\n\t\t\tcurLanguage = item.lang\n\t\t\tif not curLanguage or (\n\t\t\t\tnot autoDialectSwitching and curLanguage.split("_")[0] == defaultLanguageRoot\n\t\t\t):\n\t\t\t\tcurLanguage = defaultLanguage\n\t\telif isinstance(item, SuppressUnicodeNormalizationCommand):\n\t\t\tif not unicodeNormalization:\n\t\t\t\tcontinue\n\t\telif isinstance(item, str):\n\t\t\tif not item:\n\t\t\t\tcontinue\n\t\t\tif languageHandling.shouldMakeLangChangeCommand() and curLanguage != prevLanguage:\n\t\t\t\tspeechSequence.append(LangChangeCommand(curLanguage))\n\t\t\t\tprevLanguage = curLanguage\n\t\t\tspeechSequence.append(item)\n\t\telse:\n\t\t\tspeechSequence.append(item)\n\tif not speechSequence:\n\t\t# After normalisation, the sequence is empty.\n\t\t# There\'s nothing to speak.\n\t\treturn\n\timport inputCore\n\n\tinputCore.logTimeSinceInput()\n\tlog.io("Speaking %r" % speechSequence)\n\tif symbolLevel in (characterProcessing.SymbolLevel.UNCHANGED, None):\n\t\tsymbolLevel = characterProcessing.SymbolLevel(config.conf["speech"]["symbolLevel"])\n\tcurLanguage = defaultLanguage\n\tinCharacterMode = False\n\tfor index in range(len(speechSequence)):\n\t\titem = speechSequence[index]\n\t\tif isinstance(item, CharacterModeCommand):\n\t\t\tinCharacterMode = item.state\n\t\tif languageHandling.shouldMakeLangChangeCommand() and isinstance(item, LangChangeCommand):\n\t\t\tcurLanguage = item.lang\n\t\tif isinstance(item, SuppressUnicodeNormalizationCommand):\n\t\t\tunicodeNormalization = initialUnicodeNormalization and not item.state\n\t\tif isinstance(item, str):\n\t\t\tspeechSequence[index] = processText(\n\t\t\t\tcurLanguage,\n\t\t\t\titem,\n\t\t\t\tsymbolLevel,\n\t\t\t\tnormalize=unicodeNormalization,\n\t\t\t)\n\t\t\tif not inCharacterMode:\n\t\t\t\tspeechSequence[index] += CHUNK_SEPARATOR\n\t_manager.speak(speechSequence, priority)'

NVDA_UI_MESSAGE = 'def message(\n\ttext: str,\n\tspeechPriority: Optional[speech.Spri] = None,\n\tbrailleText: Optional[str] = None,\n):\n\t"""Present a message to the user.\n\tThe message will be presented in both speech and braille.\n\t@param text: The text of the message.\n\t@param speechPriority: The speech priority.\n\t@param brailleText: If specified, present this alternative text on the braille display.\n\t"""\n\tspeech.speakMessage(text, priority=speechPriority)\n\tbraille.handler.message(brailleText if brailleText is not None else text)'

NVDA_SPEECH_VIEWER = 'SPEECH_ITEM_SEPARATOR = "  "'

NVDA_API_CLIPBOARD = 'def copyToClip(text: str, notify: Optional[bool] = False) -> bool:\n\t"""Copies the given text to the windows clipboard.\n\t@returns: True if it succeeds, False otherwise.\n\t@param text: the text which will be copied to the clipboard\n\t@param notify: whether to emit a confirmation message\n\t"""\n\tif not isinstance(text, str) or len(text) == 0:\n\t\treturn False\n\timport gui\n\n\ttry:\n\t\twith winUser.openClipboard(gui.mainFrame.Handle):\n\t\t\twinUser.emptyClipboard()\n\t\t\twinUser.setClipboardData(winUser.CF_UNICODETEXT, text)\n\t\tgot = getClipData()\n\texcept OSError:\n\t\tif notify:\n\t\t\tui.reportTextCopiedToClipboard()  # No argument reports a failure.\n\t\treturn False\n\tif got == text:\n\t\tif notify:\n\t\t\tui.reportTextCopiedToClipboard(text)\n\t\treturn True\n\tif notify:\n\t\tui.reportTextCopiedToClipboard()  # No argument reports a failure.\n\treturn False\n\n\ndef getClipData():\n\t"""Receives text from the windows clipboard.\n\t@returns: Clipboard text\n\t@rtype: string\n\t"""\n\timport gui\n\n\twith winUser.openClipboard(gui.mainFrame.Handle):\n\t\treturn winUser.getClipboardData(winUser.CF_UNICODETEXT) or ""'

NVDA_WINUSER_CLIPBOARD = 'CF_UNICODETEXT = 13\n\n\n@contextlib.contextmanager\ndef openClipboard(hwndOwner=None):\n\t"""\n\tA context manager version of OpenClipboard from user32.\n\tUse as the expression of a \'with\' statement, and CloseClipboard will automatically be called at the end.\n\t"""\n\tif not winBindings.user32.OpenClipboard(hwndOwner):\n\t\traise ctypes.WinError()\n\ttry:\n\t\tyield\n\tfinally:\n\t\twinBindings.user32.CloseClipboard()\n\n\ndef emptyClipboard():\n\tif not _user32.EmptyClipboard():\n\t\traise ctypes.WinError()\n\n\ndef getClipboardData(format):\n\t# We only support unicode text for now\n\tif format != CF_UNICODETEXT:\n\t\traise ValueError("Unsupported format")\n\t# Fetch the data from the clipboard as a global memory handle\n\th = winBindings.user32.GetClipboardData(format)\n\tif not h:\n\t\traise ctypes.WinError()\n\t# Lock the global memory  while we fetch the unicode string\n\t# But make sure not to free the memory accidentally -- it is not ours\n\th = winKernel.HGLOBAL(h, autoFree=False)\n\twith h.lock() as addr:\n\t\t# Read the string from the local memory address\n\t\treturn wstring_at(addr)\n\n\ndef setClipboardData(format, data):\n\t# For now only unicode is a supported format\n\tif format != CF_UNICODETEXT:\n\t\traise ValueError("Unsupported format")\n\ttext = data\n\tbufLen = len(text.encode(WCHAR_ENCODING, errors="surrogatepass")) + 2\n\t# Allocate global memory\n\th = winKernel.HGLOBAL.alloc(winKernel.GMEM_MOVEABLE, bufLen)\n\t# Acquire a lock to the global memory receiving a local memory address\n\twith h.lock() as addr:\n\t\t# Write the text into the allocated memory\n\t\tbuf = (c_wchar * bufLen).from_address(addr)\n\t\tbuf.value = text\n\t# Set the clipboard data with the global memory\n\tif not winBindings.user32.SetClipboardData(format, h):\n\t\traise ctypes.WinError()\n\t# NULL the global memory handle so that it is not freed at the end of scope as the clipboard now has it.\n\th.forget()'

NVDA_WINKERNEL_HGLOBAL = 'GMEM_MOVEABLE = 2\n\n\nclass HGLOBAL(HANDLE):\n\t"""\n\tA class for the HGLOBAL Windows handle type.\n\tThis class can auto-free the handle when it goes out of scope,\n\tand also contains a classmethod for alloc,\n\tAnd a context manager compatible method for locking.\n\t"""\n\n\tdef __init__(self, h, autoFree=True):\n\t\t"""\n\t\t@param h: the raw Windows HGLOBAL handle\n\t\t@param autoFree: True by default, the handle will automatically be freed with GlobalFree\n\t\twhen this object goes out of scope.\n\t\t"""\n\t\tsuper(HGLOBAL, self).__init__(h)\n\t\tself._autoFree = autoFree\n\n\tdef __del__(self):\n\t\tif self and self._autoFree:\n\t\t\twinBindings.kernel32.GlobalFree(self)\n\n\t@classmethod\n\tdef alloc(cls, flags, size):\n\t\t"""\n\t\tAllocates global memory with GlobalAlloc\n\t\tproviding it as an instance of this class.\n\t\tThis method Takes the same arguments as GlobalAlloc.\n\t\t"""\n\t\th = winBindings.kernel32.GlobalAlloc(flags, size)\n\t\treturn cls(h)\n\n\t@contextlib.contextmanager\n\tdef lock(self):\n\t\t"""\n\t\tUsed as a context manager,\n\t\tThis method locks the global memory with GlobalLock,\n\t\tproviding the usable memory address to the body of the \'with\' statement.\n\t\tWhen the body completes, GlobalUnlock is automatically called.\n\t\t"""\n\t\ttry:\n\t\t\tyield winBindings.kernel32.GlobalLock(self)\n\t\tfinally:\n\t\t\twinBindings.kernel32.GlobalUnlock(self)\n\n\tdef forget(self):\n\t\t"""\n\t\tSets this HGLOBAL value to NULL, forgetting the existing value.\n\t\tNecessary if you pass this HGLOBAL to an API that takes ownership and therefore will handle freeing itself.\n\t\t"""\n\t\tself.value = None'

NVDA_TEXT_UTILS = 'WCHAR_ENCODING = "utf_16_le"\n\n\nUSER_ANSI_CODE_PAGE = locale.getpreferredencoding()\n\n\nclass OffsetConverter(metaclass=ABCMeta):\n\tdecoded: str\n\n\tdef __init__(self, text: str):\n\t\tif not isinstance(text, str):\n\t\t\traise TypeError("Value must be of type str")\n\t\tself.decoded: str = text\n\n\tdef __repr__(self):\n\t\treturn f"{self.__class__.__name__}({repr(self.decoded)})"\n\n\t@abstractproperty\n\tdef encodedStringLength(self) -> int:\n\t\t"""Returns the length of the string in itssubclass-specific encoded representation."""\n\t\traise NotImplementedError\n\n\t@property\n\tdef strLength(self) -> int:\n\t\t"""Returns the length of the string in its pythonic string representation."""\n\t\treturn len(self.decoded)\n\n\t@abstractmethod\n\tdef strToEncodedOffsets(\n\t\tself,\n\t\tstrStart: int,\n\t\tstrEnd: int | None = None,\n\t\traiseOnError: bool = False,\n\t) -> int | Tuple[int, int]:\n\t\t"""\n\t\tThis method takes two offsets from the str representation\n\t\tof the string the object is initialized with, and converts them to subclass-specific encoded string offsets.\n\t\t@param strStart: The start offset in the str representation of the string.\n\t\t@param strEnd: The end offset in the str representation of the string.\n\t\t\tThis offset is exclusive.\n\t\t@param raiseOnError: Raises an IndexError when one of the given offsets\n\t\t\texceeds L{strLength} or is lower than zero.\n\t\t\tIf C{False}, the out of range offset will be bounded to the range of the string.\n\t\t@raise ValueError: if strEnd < strStart\n\t\t"""\n\t\tif strEnd is not None and strEnd < strStart:\n\t\t\traise ValueError(\n\t\t\t\t"strEnd=%d must be greater than or equal to strStart=%d" % (strEnd, strStart),\n\t\t\t)\n\t\tif strStart < 0 or strStart > self.strLength:\n\t\t\tif raiseOnError:\n\t\t\t\traise IndexError("str start index out of range")\n\t\tif strEnd is not None and (strEnd < 0 or strEnd > self.strLength):\n\t\t\tif raiseOnError:\n\t\t\t\traise IndexError("str end index out of range")\n\n\t@abstractmethod\n\tdef encodedToStrOffsets(\n\t\tself,\n\t\tencodedStart: int,\n\t\tencodedEnd: int | None = None,\n\t\traiseOnError: bool = False,\n\t) -> int | Tuple[int, int]:\n\t\tr"""\n\t\tThis method takes two offsets from subclass-specific encoded string representation\n\t\tof the string the object is initialized with, and converts them to str offsets.\n\t\t@param encodedStart: The start offset in the wide character representation of the string.\n\t\t@param encodedEnd: The end offset in the wide character representation of the string.\n\t\t\tThis offset is exclusive.\n\t\t@param raiseOnError: Raises an IndexError when one of the given offsets\n\t\t\texceeds L{encodedStringLength} or is lower than zero.\n\t\t\tIf C{False}, the out of range offset will be bounded to the range of the string.\n\t\t@raise ValueError: if wideStringEnd < wideStringStart\n\t\t"""\n\t\tif encodedEnd is not None and encodedEnd < encodedStart:\n\t\t\traise ValueError(\n\t\t\t\tf"{encodedEnd=} must be greater than or equal to {encodedStart=}",\n\t\t\t)\n\t\tif encodedStart < 0 or encodedStart > self.encodedStringLength:\n\t\t\tif raiseOnError:\n\t\t\t\traise IndexError("Wide string start index out of range")\n\t\tif encodedEnd is not None and (encodedEnd < 0 or encodedEnd > self.encodedStringLength):\n\t\t\tif raiseOnError:\n\t\t\t\traise IndexError("Wide string end index out of range")\n\n\nclass WideStringOffsetConverter(OffsetConverter):\n\t"""\n\tObject that holds a string in both its decoded and its UTF-16 encoded form.\n\tThe object allows for easy conversion between offsets in str type strings,\n\tand offsets in wide character (UTF-16) strings (that are aware of surrogate characters).\n\tThis representation is used by all wide character strings in Windows (i.e. with characters of type L{ctypes.c_wchar}).\n\n\tIn Python 3 strings, every offset in a string corresponds with one unicode codepoint.\n\tIn UTF-16 encoded strings, 32-bit unicode characters (such as emoji)\n\tare encoded as one high surrogate and one low surrogate character.\n\tTherefore, they take not one, but two offsets in such a string.\n\n\tFor example: 😂 takes one offset in a Python 3 string.\n\t"""\n\n\t_encoding: str = WCHAR_ENCODING\n\t_bytesPerIndex: int = ctypes.sizeof(ctypes.c_wchar)\n\n\tdef __init__(self, text: str):\n\t\tsuper().__init__(text)\n\t\tself.encoded: bytes = text.encode(self._encoding, errors="surrogatepass")\n\n\t@property\n\tdef encodedStringLength(self) -> int:\n\t\t"""Returns the length of the string in its wide character (UTF-16) representation."""\n\t\treturn len(self.encoded) // self._bytesPerIndex\n\n\tdef strToEncodedOffsets(\n\t\tself,\n\t\tstrStart: int,\n\t\tstrEnd: int | None = None,\n\t\traiseOnError: bool = False,\n\t) -> int | Tuple[int, int]:\n\t\t"""\n\t\tThis method takes two offsets from the str representation\n\t\tof the string the object is initialized with, and converts them to wide character string offsets.\n\t\t@param strStart: The start offset in the str representation of the string.\n\t\t@param strEnd: The end offset in the str representation of the string.\n\t\t\tThis offset is exclusive.\n\t\t@param raiseOnError: Raises an IndexError when one of the given offsets\n\t\t\texceeds L{strLength} or is lower than zero.\n\t\t\tIf C{False}, the out of range offset will be bounded to the range of the string.\n\t\t@raise ValueError: if strEnd < strStart\n\t\t"""\n\t\tsuper().strToEncodedOffsets(strStart, strEnd, raiseOnError)\n\t\tstrStart = max(0, min(strStart, self.strLength))\n\t\t# Optimisation, don\'t do anything special if offsets are collapsed at the start.\n\t\tif 0 == strEnd == strStart:\n\t\t\treturn (0, 0)\n\t\t# If the original string contains surrogate characters, we want to preserve them\n\t\tif strStart == 0:\n\t\t\twideStringStart: int = 0\n\t\telse:\n\t\t\tprecedingBytes: bytes = self.decoded[:strStart].encode(self._encoding, errors="surrogatepass")\n\t\t\twideStringStart = len(precedingBytes) // self._bytesPerIndex\n\t\tif strEnd is None:\n\t\t\treturn wideStringStart\n\t\tstrEnd = max(0, min(strEnd, self.strLength))\n\t\tif strStart == strEnd:\n\t\t\treturn (wideStringStart, wideStringStart)\n\t\tencodedRange: bytes = self.decoded[strStart:strEnd].encode(self._encoding, errors="surrogatepass")\n\t\twideStringEnd: int = wideStringStart + (len(encodedRange) // self._bytesPerIndex)\n\t\treturn (wideStringStart, wideStringEnd)\n\n\tdef encodedToStrOffsets(\n\t\tself,\n\t\tencodedStart: int,\n\t\tencodedEnd: int,\n\t\traiseOnError: bool = False,\n\t) -> Tuple[int, int]:\n\t\tr"""\n\t\tThis method takes two offsets from the wide character representation\n\t\tof the string the object is initialized with, and converts them to str offsets.\n\t\tencodedEnd is considered an exclusive offset.\n\t\tIf either encodedStart or encodedEnd corresponds with an offset\n\t\tin the middel of a surrogate pair, it is yet counted as one offset in the string.\n\t\tFor example, when L{decoded} is "😂", which is one offset in the str representation,\n\t\tthis method returns (0, 1) in all of the following cases:\n\t\t\t* encodedStart=0, encodedEnd=1\n\t\t\t* encodedStart=0, encodedEnd=2\n\t\t\t* encodedStart=1, encodedEnd=2\n\t\tHowever, encodedStart=1, encodedEnd=1 results in (0, 0)\n\t\t@param encodedStart: The start offset in the wide character representation of the string.\n\t\t@param encodedEnd: The end offset in the wide character representation of the string.\n\t\t\tThis offset is exclusive.\n\t\t@param raiseOnError: Raises an IndexError when one of the given offsets\n\t\t\texceeds L{encodedStringLength} or is lower than zero.\n\t\t\tIf C{False}, the out of range offset will be bounded to the range of the string.\n\t\t@raise ValueError: if encodedEnd < encodedStart\n\t\t"""\n\t\t# Optimisation, don\'t do anything special if offsets are collapsed at the start.\n\t\tif 0 == encodedEnd == encodedStart:\n\t\t\treturn (0, 0)\n\t\tif encodedEnd is None:\n\t\t\treturn self.encodedToStrOffsets(encodedStart, encodedStart, raiseOnError)[0]\n\t\tsuper().encodedToStrOffsets(encodedStart, encodedEnd, raiseOnError)\n\t\tencodedStart = max(0, min(encodedStart, self.encodedStringLength))\n\t\tencodedEnd = max(0, min(encodedEnd, self.encodedStringLength))\n\t\tbytesStart: int = encodedStart * self._bytesPerIndex\n\t\tbytesEnd: int = encodedEnd * self._bytesPerIndex\n\t\tprecedingStr = self.encoded[:bytesStart].decode(self._encoding, errors="surrogatepass")\n\t\tstrStart = len(precedingStr)\n\t\tif bytesStart == bytesEnd and bytesEnd <= (len(self.encoded) - self._bytesPerIndex):\n\t\t\t# Though we are trying to fetch str offsets for a single offset,\n\t\t\t# we need to make sure to avoid off by one errors caused by surrogates\n\t\t\tcorrectedBytesEnd = bytesEnd + self._bytesPerIndex\n\t\telse:\n\t\t\tcorrectedBytesEnd = bytesEnd\n\t\tdecodedRange: str = self.encoded[bytesStart:correctedBytesEnd].decode(\n\t\t\tself._encoding,\n\t\t\terrors="surrogatepass",\n\t\t)\n\t\tstrEnd: int = strStart + len(decodedRange)\n\t\t# In the case where precedingStr ends with a high surrogate,\n\t\t# and decodedRange ends with a low surrogate character\n\t\t# They take one offset in the resulting string, so our offsets are off by one.\n\t\tif (\n\t\t\tprecedingStr\n\t\t\tand isHighSurrogate(precedingStr[-1])\n\t\t\tand decodedRange\n\t\t\tand isLowSurrogate(decodedRange[0])\n\t\t):\n\t\t\tstrStart -= 1\n\t\t\tstrEnd -= 1\n\t\tif correctedBytesEnd > bytesEnd:\n\t\t\t# Compensate for the case where we stretched our offsets earlier\n\t\t\tstrEnd -= (correctedBytesEnd - bytesEnd) // self._bytesPerIndex\n\t\treturn (strStart, strEnd)\n\n\twideStringLength = encodedStringLength\n\tstrToWideOffsets = strToEncodedOffsets\n\twideToStrOffsets = encodedToStrOffsets\n\n\nHIGH_SURROGATE_FIRST = "\\ud800"\n\n\nHIGH_SURROGATE_LAST = "\\udbff"\n\n\ndef isHighSurrogate(ch: str) -> bool:\n\t"""Returns if the given character is a high surrogate UTF-16 character."""\n\treturn HIGH_SURROGATE_FIRST <= ch <= HIGH_SURROGATE_LAST\n\n\nLOW_SURROGATE_FIRST = "\\udc00"\n\n\nLOW_SURROGATE_LAST = "\\udfff"\n\n\ndef isLowSurrogate(ch: str) -> bool:\n\t"""Returns if the given character is a low surrogate UTF-16 character."""\n\treturn LOW_SURROGATE_FIRST <= ch <= LOW_SURROGATE_LAST'

NVDA_WINUSER_MESSAGES = 'WM_GETTEXT = 13\n\n\nWM_GETTEXTLENGTH = 14\n\n\nEM_GETSEL = 176\n\n\nEM_GETLINECOUNT = 186\n\n\nEM_LINEINDEX = 187\n\n\nEM_LINELENGTH = 193\n\n\nEM_LINEFROMCHAR = 201\n\n\nMAPVK_VK_TO_CHAR = 2'

NVDA_NORMALIZE_GESTURE = 'def normalizeGestureIdentifier(identifier):\n\t"""Normalize a gesture identifier so that it matches other identifiers for the same gesture.\n\tFirst, the entire identifier is converted to lower case.\n\tThen, any items separated by a + sign after the source prefix are considered to be of indeterminate order\n\tand are sorted by character.\n\tThis is done because, for example, "kb:shift+alt+downArrow"\n\tmust be treated the same as "kb:alt+shift+downarrow".\n\t"""\n\tidentifier = identifier.lower()\n\tprefix, main = identifier.split(":", 1)\n\tmain = main.split("+")\n\t# The order of the parts doesn\'t matter as far as the user is concerned,\n\t# but we need them to be in a determinate order so they will match other gesture identifiers.\n\t# We sort them by character.\n\tmain.sort()\n\tmain = "+".join(main)\n\treturn "{0}:{1}".format(prefix, main)'

NVDA_EDIT_TEXT_INFO = 'def _getSelectionOffsets(self):\n\tif self.obj.editAPIVersion >= 1:\n\t\tcharRange = CharRangeStruct()\n\t\tprocessHandle = self.obj.processHandle\n\t\tinternalCharRange = winKernel.virtualAllocEx(\n\t\t\tprocessHandle,\n\t\t\tNone,\n\t\t\tctypes.sizeof(charRange),\n\t\t\twinKernel.MEM_COMMIT,\n\t\t\twinKernel.PAGE_READWRITE,\n\t\t)\n\t\ttry:\n\t\t\twatchdog.cancellableSendMessage(self.obj.windowHandle, EM_EXGETSEL, 0, internalCharRange)\n\t\t\twinKernel.readProcessMemory(\n\t\t\t\tprocessHandle,\n\t\t\t\tinternalCharRange,\n\t\t\t\tctypes.byref(charRange),\n\t\t\t\tctypes.sizeof(charRange),\n\t\t\t\tNone,\n\t\t\t)\n\t\tfinally:\n\t\t\twinKernel.virtualFreeEx(processHandle, internalCharRange, 0, winKernel.MEM_RELEASE)\n\t\treturn (charRange.cpMin, charRange.cpMax)\n\telse:\n\t\tstart = ctypes.c_uint()\n\t\tend = ctypes.c_uint()\n\t\twatchdog.cancellableSendMessage(\n\t\t\tself.obj.windowHandle,\n\t\t\twinUser.EM_GETSEL,\n\t\t\tctypes.byref(start),\n\t\t\tctypes.byref(end),\n\t\t)\n\t\treturn start.value, end.value\n\n\ndef _getCaretOffset(self):\n\treturn self._getSelectionOffsets()[0]\n\n\ndef _getStoryText(self):\n\tif controlTypes.State.PROTECTED in self.obj.states:\n\t\treturn "*" * self._getStoryLength()\n\treturn self.obj.windowText\n\n\ndef _getStoryLength(self):\n\tif self.obj.editAPIVersion >= 2:\n\t\tinfo = getTextLengthExStruct()\n\t\tinfo.flags = GTL_NUMCHARS\n\t\tif self.obj.isWindowUnicode:\n\t\t\tinfo.codepage = 1200\n\t\telse:\n\t\t\tinfo.codepage = 0\n\t\tprocessHandle = self.obj.processHandle\n\t\tinternalInfo = winKernel.virtualAllocEx(\n\t\t\tprocessHandle,\n\t\t\tNone,\n\t\t\tctypes.sizeof(info),\n\t\t\twinKernel.MEM_COMMIT,\n\t\t\twinKernel.PAGE_READWRITE,\n\t\t)\n\t\ttry:\n\t\t\twinKernel.writeProcessMemory(\n\t\t\t\tprocessHandle,\n\t\t\t\tinternalInfo,\n\t\t\t\tctypes.byref(info),\n\t\t\t\tctypes.sizeof(info),\n\t\t\t\tNone,\n\t\t\t)\n\t\t\ttextLen = watchdog.cancellableSendMessage(\n\t\t\t\tself.obj.windowHandle,\n\t\t\t\tEM_GETTEXTLENGTHEX,\n\t\t\t\tinternalInfo,\n\t\t\t\t0,\n\t\t\t)\n\t\tfinally:\n\t\t\twinKernel.virtualFreeEx(processHandle, internalInfo, 0, winKernel.MEM_RELEASE)\n\t\treturn textLen\n\telse:\n\t\t# ForWM_GETTEXTLENGTH documentation, see\n\t\t# https://docs.microsoft.com/en-us/windows/desktop/winmsg/wm-gettextlength\n\t\t# It determines the length, in characters, of the text associated with a window.\n\t\treturn watchdog.cancellableSendMessage(self.obj.windowHandle, winUser.WM_GETTEXTLENGTH, 0, 0)\n\n\ndef _getLineCount(self):\n\treturn self.obj.windowTextLineCount\n\n\ndef _getLineNumFromOffset(self, offset):\n\tif self.obj.editAPIVersion >= 1:\n\t\tres = watchdog.cancellableSendMessage(self.obj.windowHandle, EM_EXLINEFROMCHAR, 0, offset)\n\t\treturn res\n\telse:\n\t\treturn watchdog.cancellableSendMessage(self.obj.windowHandle, winUser.EM_LINEFROMCHAR, offset, 0)\n\n\ndef _getLineOffsets(self, offset):\n\tlineNum = self._getLineNumFromOffset(offset)\n\tstart = watchdog.cancellableSendMessage(self.obj.windowHandle, winUser.EM_LINEINDEX, lineNum, 0)\n\tlength = watchdog.cancellableSendMessage(self.obj.windowHandle, winUser.EM_LINELENGTH, offset, 0)\n\tend = start + length\n\t# If we just seem to get invalid line info, calculate manually\n\tif (\n\t\tstart <= 0\n\t\tand end <= 0\n\t\tand lineNum <= 0\n\t\tand self._getLineCount() <= 0\n\t\tand self._getStoryLength() > 0\n\t):\n\t\treturn super(EditTextInfo, self)._getLineOffsets(offset)\n\t# Some edit controls that show both line feed and carage return can give a length not including the line feed\n\tif end <= offset:\n\t\tend = offset + 1\n\t# edit controls lye about their line length\n\tlimit = self._getStoryLength()\n\twhile self._getLineNumFromOffset(end) == lineNum and end < limit:\n\t\tend += 1\n\treturn (start, end)'

NVDA_OFFSETS_TEXT_RANGE = 'def _getTextRange(self, start, end):\n\t"""Retrieve the text in a given offset range.\n\t@param start: The start offset.\n\t@type start: int\n\t@param end: The end offset (exclusive).\n\t@type end: int\n\t@return: The text contained in the requested range.\n\t@rtype: str\n\t"""\n\ttext = self._getStoryText()\n\tif self.encoding == textUtils.WCHAR_ENCODING:\n\t\toffsetConverter = textUtils.WideStringOffsetConverter(text)\n\t\tstart, end = offsetConverter.encodedToStrOffsets(start, end)\n\telif not (\n\t\tself.encoding is None\n\t\tor self.encoding == "utf_32_le"\n\t\tor self.encoding == textUtils.USER_ANSI_CODE_PAGE\n\t):\n\t\traise NotImplementedError\n\treturn text[start:end]'

NVDA_WINDOW_TEXT = 'def _get_windowText(self):\n\ttextLength = watchdog.cancellableSendMessage(self.windowHandle, winUser.WM_GETTEXTLENGTH, 0, 0)\n\ttextBuf = ctypes.create_unicode_buffer(textLength + 2)\n\twatchdog.cancellableSendMessage(self.windowHandle, winUser.WM_GETTEXT, textLength + 1, textBuf)\n\treturn textBuf.value\n\n\ndef _get_windowTextLineCount(self):\n\treturn watchdog.cancellableSendMessage(self.windowHandle, winUser.EM_GETLINECOUNT, 0, 0)'

NVDA_USER32_CLIPBOARD = 'OpenClipboard = WINFUNCTYPE(None)(("OpenClipboard", dll))\n\n\nOpenClipboard.argtypes = (\n\tHWND,  # hWndNewOwner\n)\n\n\nOpenClipboard.restype = BOOL\n\n\nCloseClipboard = WINFUNCTYPE(None)(("CloseClipboard", dll))\n\n\nCloseClipboard.argtypes = ()\n\n\nCloseClipboard.restype = BOOL\n\n\nEmptyClipboard = WINFUNCTYPE(None)(("EmptyClipboard", dll))\n\n\nEmptyClipboard.restype = BOOL\n\n\nEmptyClipboard.argtypes = ()\n\n\nGetClipboardData = WINFUNCTYPE(None)(("GetClipboardData", dll))\n\n\nGetClipboardData.argtypes = (\n\tUINT,  # uFormat\n)\n\n\nGetClipboardData.restype = HANDLE\n\n\nSetClipboardData = WINFUNCTYPE(None)(("SetClipboardData", dll))\n\n\nSetClipboardData.argtypes = (\n\tUINT,  # uFormat\n\tHANDLE,  # hMem\n)\n\n\nSetClipboardData.restype = HANDLE'

NVDA_KERNEL32_GLOBAL = 'GlobalAlloc = WINFUNCTYPE(None)(("GlobalAlloc", dll))\n\n\nGlobalAlloc.argtypes = (\n\tUINT,  # uFlags\n\tc_size_t,  # dwBytes\n)\n\n\nGlobalAlloc.restype = HGLOBAL\n\n\nGlobalFree = WINFUNCTYPE(None)(("GlobalFree", dll))\n\n\nGlobalFree.argtypes = (\n\tHGLOBAL,  # hMem\n)\n\n\nGlobalFree.restype = HGLOBAL\n\n\nGlobalLock = WINFUNCTYPE(None)(("GlobalLock", dll))\n\n\nGlobalLock.argtypes = (\n\tHGLOBAL,  # hMem\n)\n\n\nGlobalLock.restype = LPVOID\n\n\nGlobalUnlock = WINFUNCTYPE(None)(("GlobalUnlock", dll))\n\n\nGlobalUnlock.argtypes = (\n\tHGLOBAL,  # hMem\n)\n\n\nGlobalUnlock.restype = BOOL'

NVDA_CODE_FILES = {'NVDA_EXTENSION_POINTS_UTIL': 'extensionPoints/util.py', 'NVDA_EXTENSION_POINTS': 'extensionPoints/__init__.py', 'NVDA_SPEECH_EXTENSIONS': 'speech/extensions.py', 'NVDA_SPEAK': 'speech/speech.py', 'NVDA_UI_MESSAGE': 'ui.py', 'NVDA_SPEECH_VIEWER': 'speechViewer.py', 'NVDA_API_CLIPBOARD': 'api.py', 'NVDA_WINUSER_CLIPBOARD': 'winUser.py', 'NVDA_WINKERNEL_HGLOBAL': 'winKernel.py', 'NVDA_TEXT_UTILS': 'textUtils/__init__.py', 'NVDA_WINUSER_MESSAGES': 'winUser.py', 'NVDA_NORMALIZE_GESTURE': 'inputCore.py', 'NVDA_EDIT_TEXT_INFO': 'NVDAObjects/window/edit.py', 'NVDA_OFFSETS_TEXT_RANGE': 'textInfos/offsets.py', 'NVDA_WINDOW_TEXT': 'NVDAObjects/window/__init__.py', 'NVDA_USER32_CLIPBOARD': 'winBindings/user32.py', 'NVDA_KERNEL32_GLOBAL': 'winBindings/kernel32.py'}

# JAWS 2026's own lines, from Scripts\enu\Default.JKM and Scripts\common.jsm, where JAWS isn't installed.
JAWS_LAYER_KEYS = {
	"Insert+Space&H": "ShowSpeechHistory",
	"Insert+Space&Control+H": "CopySpeechHistoryToClipboard",
	"Insert+Space&Shift+H": "ClearSpeechHistory",
	"Insert+Space&Shift+Slash": "BasicLayerHelp",
}
JAWS_MESSAGES = {
	"cmsgClearSpeechHistory": "Speech history cleared",
	"cmsgCopySpeechHistory": "Copy speech history to clipboard",
	"cmsgSpeechHistoryNotAvailable": "Speech history disabled",
	"cmsgSpeechHistoryTitle": "Speech History",
}
JAWS_SCRIPTS = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Freedom Scientific", "JAWS", "2026", "Scripts")

FLAGS = __future__.annotations.compiler_flag


def run(source, namespace, filename):
	"""Run NVDA's ``source`` in ``namespace``, with its annotations never evaluated, as ``from __future__ import
	annotations`` at the top of most of NVDA's files does."""
	exec(compile(source, filename, "exec", flags=FLAGS, dont_inherit=True), namespace)
	return namespace


def module(name, source, filename, **names):
	made = types.ModuleType(name)
	vars(made).update(names)
	run(source, vars(made), filename)
	return made


_log = logging.getLogger("nvda.test_v129")
_log.io = _log.debug
_log.debugWarning = _log.debug


class SpeechMode(enum.IntEnum):
	off = 0
	beeps = 1
	talk = 2
	onDemand = 3


class Spri(enum.IntEnum):
	NORMAL = 0
	NEXT = 1
	NOW = 2


class SymbolLevel(enum.IntEnum):
	NONE = 0
	SOME = 100
	MOST = 200
	ALL = 300
	CHAR = 1000
	UNCHANGED = -1


class LangChangeCommand:
	def __init__(self, lang):
		self.lang = lang


class SuppressUnicodeNormalizationCommand:
	def __init__(self, state=True):
		self.state = state


class CharacterModeCommand:
	def __init__(self, state):
		self.state = state


class BeepCommand:
	"""A speech command without text, as NVDA's BeepCommand and WaveFileCommand (ClassicSpeech's sounds) are."""

	def __init__(self, hz=440):
		self.hz = hz


class Nvda:
	"""NVDA 2026.2's extension points, speech.speak, ui.message and api.copyToClip, as sys.modules has them."""

	def __init__(self, frame):
		#: What NVDA's speech manager was given: what the synthesizer says.
		self.synthesizer = []
		util = module(
			"extensionPoints.util",
			NVDA_EXTENSION_POINTS_UTIL,
			"extensionPoints/util.py",
			weakref=weakref,
			inspect=inspect,
			Callable=Callable,
			Generator=Generator,
			Generic=Generic,
			Optional=Optional,
			OrderedDict=OrderedDict,
			Tuple=Tuple,
			TypeVar=TypeVar,
			Union=Union,
			NVDAState=types.SimpleNamespace(_allowDeprecatedAPI=lambda: True),
			log=_log,
		)
		extensionPoints = module(
			"extensionPoints",
			NVDA_EXTENSION_POINTS,
			"extensionPoints/__init__.py",
			log=_log,
			HandlerRegistrar=util.HandlerRegistrar,
			callWithSupportedKwargs=util.callWithSupportedKwargs,
			BoundMethodWeakref=util.BoundMethodWeakref,
			Callable=Callable,
			Generator=Generator,
			Generic=Generic,
			Iterable=Iterable,
			Set=Set,
			TypeVar=TypeVar,
			Union=Union,
		)
		self.extensions = module(
			"speech.extensions",
			NVDA_SPEECH_EXTENSIONS,
			"speech/extensions.py",
			Action=extensionPoints.Action,
			Filter=extensionPoints.Filter,
			SpeechSequence=list,
		)
		self.speechState = types.SimpleNamespace(speechMode=SpeechMode.talk, isPaused=False, beenCanceled=False, speechMode_beeps_ms=15)
		self.speechModule = module(
			"speech.speech",
			NVDA_SPEAK,
			"speech/speech.py",
			filter_speechSequence=self.extensions.filter_speechSequence,
			pre_speech=self.extensions.pre_speech,
			logBadSequenceTypes=lambda sequence: None,
			Spri=Spri,
			Optional=Optional,
			_speechState=self.speechState,
			SpeechMode=SpeechMode,
			tones=types.SimpleNamespace(beep=lambda *args: None),
			config=types.SimpleNamespace(
				conf={"speech": {"autoDialectSwitching": False, "unicodeNormalization": False, "symbolLevel": 100, "beepSpeechModePitch": 10000}},
			),
			cancelSpeech=lambda: None,
			getCurrentLanguage=lambda: "en_US",
			LangChangeCommand=LangChangeCommand,
			SuppressUnicodeNormalizationCommand=SuppressUnicodeNormalizationCommand,
			CharacterModeCommand=CharacterModeCommand,
			languageHandling=types.SimpleNamespace(shouldMakeLangChangeCommand=lambda: False),
			log=_log,
			characterProcessing=types.SimpleNamespace(SymbolLevel=SymbolLevel),
			processText=lambda locale, text, symbolLevel, normalize=False: text,
			CHUNK_SEPARATOR="  ",
			_manager=types.SimpleNamespace(speak=lambda sequence, priority: self.synthesizer.append([item.removesuffix("  ") for item in sequence if isinstance(item, str)])),
			_=lambda text: text,
		)
		self.speech = types.ModuleType("speech")
		self.speech.speech = self.speechModule
		self.speech.extensions = self.extensions
		self.speech.speakMessage = self.speechModule.speakMessage
		self.speech.Spri = Spri
		self.ui = module(
			"ui",
			NVDA_UI_MESSAGE,
			"ui.py",
			speech=self.speech,
			braille=types.SimpleNamespace(handler=types.SimpleNamespace(message=lambda text: None)),
			Optional=Optional,
		)
		self.speechViewer = module("speechViewer", NVDA_SPEECH_VIEWER, "speechViewer.py", isActive=False)
		# Windows' own clipboard, through NVDA's code and the prototypes NVDA gives Windows' functions.
		user32 = module("winBindings.user32", NVDA_USER32_CLIPBOARD, "winBindings/user32.py", WINFUNCTYPE=WINFUNCTYPE, dll=windll.user32, HWND=HWND, BOOL=BOOL, UINT=UINT, HANDLE=HANDLE)
		kernel32 = module(
			"winBindings.kernel32",
			NVDA_KERNEL32_GLOBAL,
			"winBindings/kernel32.py",
			WINFUNCTYPE=WINFUNCTYPE,
			dll=windll.kernel32,
			UINT=UINT,
			c_size_t=c_size_t,
			HGLOBAL=HGLOBAL,
			LPVOID=LPVOID,
			BOOL=BOOL,
		)
		winBindings = types.SimpleNamespace(user32=user32, kernel32=kernel32)
		winKernel = module("winKernel", NVDA_WINKERNEL_HGLOBAL, "winKernel.py", HANDLE=HANDLE, contextlib=contextlib, winBindings=winBindings)
		self.winUser = module(
			"winUser",
			NVDA_WINUSER_CLIPBOARD + "\n\n\n" + NVDA_WINUSER_MESSAGES,
			"winUser.py",
			contextlib=contextlib,
			ctypes=ctypes,
			winBindings=winBindings,
			_user32=user32,
			winKernel=winKernel,
			wstring_at=wstring_at,
			c_wchar=c_wchar,
			WCHAR_ENCODING=textUtilsModule().WCHAR_ENCODING,
		)
		self.api = module(
			"api",
			NVDA_API_CLIPBOARD,
			"api.py",
			winUser=self.winUser,
			ui=types.SimpleNamespace(reportTextCopiedToClipboard=lambda text=None: None),
			Optional=Optional,
		)
		self.gui = types.SimpleNamespace(mainFrame=frame)
		self.inputCore = types.SimpleNamespace(logTimeSinceInput=lambda: None, manager=sys.modules["inputCore"].manager)

	def modules(self) -> dict:
		"""What sys.modules holds while NVDA runs: the assistant imports these as it needs them."""
		return {
			"speech": self.speech,
			"speech.speech": self.speechModule,
			"speech.extensions": self.extensions,
			"ui": self.ui,
			"api": self.api,
			"speechViewer": self.speechViewer,
			"inputCore": self.inputCore,
			"gui": types.SimpleNamespace(mainFrame=self.gui.mainFrame, messageBox=lambda *args, **kwargs: None),
		}

	def said(self) -> list:
		"""What the synthesizer said, one string for each time NVDA spoke."""
		return ["  ".join(sequence) for sequence in self.synthesizer]


_app = wx.App.Get() or wx.App(False)
_frame = wx.Frame(None, title="NVDA")


def textUtilsModule():
	return module(
		"textUtils",
		NVDA_TEXT_UTILS,
		"textUtils/__init__.py",
		ctypes=ctypes,
		encodings=encodings,
		locale=locale,
		unicodedata=unicodedata,
		ABCMeta=ABCMeta,
		abstractmethod=abstractmethod,
		abstractproperty=abstractproperty,
		cached_property=cached_property,
		Generator=Generator,
		Optional=Optional,
		Tuple=Tuple,
		Type=Type,
		log=_log,
	)


class NvdaReadsTheLine:
	"""NVDA 2026.2's EditTextInfo for a standard Edit window (the Speech History window's text box is one), with
	Window's windowText and windowTextLineCount: the line NVDA says at the caret."""

	def __init__(self, textCtrl):
		# NVDA's watchdog.cancellableSendMessage sends the message as SendMessage does, and gives back its result.
		SendMessage = ctypes.WinDLL("user32").SendMessageW
		SendMessage.restype = LPARAM

		def cancellableSendMessage(hwnd, msg, wParam, lParam):
			wParam = WPARAM(wParam) if isinstance(wParam, int) else wParam
			lParam = LPARAM(lParam) if isinstance(lParam, int) else lParam
			return SendMessage(HWND(hwnd), UINT(msg), wParam, lParam)

		winUser = module("winUser", NVDA_WINUSER_MESSAGES, "winUser.py")
		textUtils = textUtilsModule()
		namespace = {
			"ctypes": ctypes,
			"winUser": winUser,
			"watchdog": types.SimpleNamespace(cancellableSendMessage=cancellableSendMessage),
			"controlTypes": types.SimpleNamespace(State=types.SimpleNamespace(PROTECTED="protected")),
			"textUtils": textUtils,
		}
		run(
			"class Window:\n"
			+ textwrap.indent(NVDA_WINDOW_TEXT, "\t")
			+ "\n\n\twindowText = property(_get_windowText)\n\twindowTextLineCount = property(_get_windowTextLineCount)\n\n\n"
			"class OffsetsTextInfo:\n\tencoding = textUtils.WCHAR_ENCODING\n\n"
			+ textwrap.indent(NVDA_OFFSETS_TEXT_RANGE, "\t")
			+ "\n\n\nclass EditTextInfo(OffsetsTextInfo):\n"
			+ textwrap.indent(NVDA_EDIT_TEXT_INFO, "\t")
			+ "\n",
			namespace,
			"NVDAObjects/window/edit.py",
		)
		obj = namespace["Window"]()
		obj.windowHandle = textCtrl.GetHandle()
		obj.editAPIVersion = 0
		obj.states = set()
		self.info = namespace["EditTextInfo"]()
		self.info.obj = obj

	def lineAtCaret(self) -> str:
		offset = self.info._getCaretOffset()
		start, end = self.info._getLineOffsets(offset)
		return self.info._getTextRange(start, end)


def rawClipboardText():
	"""What Windows' clipboard holds as text (CF_UNICODETEXT), exactly, read without NVDA's code or wx's, which
	gives 
 for 
."""
	user32 = ctypes.WinDLL("user32")
	kernel32 = ctypes.WinDLL("kernel32")
	user32.OpenClipboard.argtypes = (HWND,)
	user32.OpenClipboard.restype = BOOL
	user32.GetClipboardData.argtypes = (UINT,)
	user32.GetClipboardData.restype = HANDLE
	kernel32.GlobalLock.argtypes = (HGLOBAL,)
	kernel32.GlobalLock.restype = LPVOID
	kernel32.GlobalUnlock.argtypes = (HGLOBAL,)
	for _attempt in range(20):
		if user32.OpenClipboard(None):
			break
		time.sleep(0.05)
	else:
		return None
	try:
		handle = user32.GetClipboardData(13)
		if not handle:
			return None
		address = kernel32.GlobalLock(handle)
		try:
			return wstring_at(address)
		finally:
			kernel32.GlobalUnlock(handle)
	finally:
		user32.CloseClipboard()


def clipboardText():
	"""What Windows' clipboard holds as text, or None, to put it back after a test."""
	if not wx.TheClipboard.Open():
		return None
	try:
		data = wx.TextDataObject()
		return data.GetText() if wx.TheClipboard.GetData(data) else None
	finally:
		wx.TheClipboard.Close()


class SpeechHistoryCase(unittest.TestCase):
	def setUp(self):
		speechHistory.unregister()
		self.nvda = Nvda(_frame)
		patcher = mock.patch.dict(sys.modules, self.nvda.modules())
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(speechHistory.unregister)

	def speak(self, *items):
		self.nvda.speechModule.speak(list(items))


# -- keeping what NVDA says ------------------------------------------------------------------------------------------


class KeepingTests(SpeechHistoryCase):
	def test_whatNvdaSaysIsKeptOneLineEachTime(self):
		self.assertTrue(speechHistory.register())
		self.speak("Items View", "list")
		self.speak("Data (D", "2 of 8")
		self.nvda.ui.message("Speech history cleared")
		self.assertEqual(speechHistory.entries(), ["Items View  list", "Data (D  2 of 8", "Speech history cleared"])
		self.assertEqual(self.nvda.said(), speechHistory.entries(), "NVDA still says it all")

	def test_thePartsAreTwoSpacesApartAsInNvdasSpeechViewer(self):
		namespace = run(NVDA_SPEECH_VIEWER, {}, "speechViewer.py")
		self.assertEqual(speechHistory.SEPARATOR, namespace["SPEECH_ITEM_SEPARATOR"])

	def test_whatYouHearAfterAddOnsFilters(self):
		# ClassicSpeech changes what NVDA says in filter_speechSequence; NVDA notifies pre_speech after every filter.
		def classicSpeech(speechSequence):
			return [item.replace("clickable", "") if isinstance(item, str) else item for item in speechSequence] + [BeepCommand()]

		self.nvda.extensions.filter_speechSequence.register(classicSpeech)
		speechHistory.register()
		self.speak("clickable", "Homepage", "link")
		self.assertEqual(speechHistory.entries(), ["Homepage  link"])

	def test_onlyTextOneLine(self):
		speechHistory.register()
		self.speak(BeepCommand(), CharacterModeCommand(True), "a", CharacterModeCommand(False))
		self.speak("line one\r\nline two", "  ", "")
		self.speak(BeepCommand())
		self.speak(" ")
		self.assertEqual(speechHistory.entries(), ["a", "line one line two"])
		self.assertEqual(len(self.nvda.said()), 4, "NVDA still speaks each one, the beep and the blank too")

	def test_theLast500AsJaws(self):
		speechHistory.register()
		for number in range(1, 511):
			self.speak(f"line {number}")
		entries = speechHistory.entries()
		self.assertEqual(len(entries), 500)
		self.assertEqual((entries[0], entries[-1]), ("line 11", "line 510"))

	def test_wrapsNothing(self):
		# The Speech History add-on puts its own function in the place of speech.speech.speak, which calls NVDA's.
		nvdasSpeak = self.nvda.speechModule.speak
		kept = []

		def speechHistoryAddOn(sequence, *args, **kwargs):
			nvdasSpeak(sequence, *args, **kwargs)
			kept.append(sequence)

		self.nvda.speechModule.speak = speechHistoryAddOn
		speechHistory.register()
		self.speak("File Explorer")
		speechHistory.unregister()
		self.assertIs(self.nvda.speechModule.speak, speechHistoryAddOn, "the add-on keeps its own")
		self.assertEqual(kept, [["File Explorer"]])
		speechHistory.register()
		self.speak("Desktop")
		self.assertEqual(speechHistory.entries(), ["Desktop"], "once each time NVDA speaks, with the add-on too")

	def test_registeredOnceAndKeptWhenSettingsApplyAgain(self):
		speechHistory.register()
		self.speak("one")
		# A migration, a restore or NVDA's configuration reload applies the settings again.
		speechHistory.register()
		self.speak("two")
		self.assertEqual(speechHistory.entries(), ["one", "two"])
		self.assertEqual(len(list(self.nvda.extensions.pre_speech.handlers)), 1)

	def test_offForgetsAndStops(self):
		speechHistory.register()
		self.speak("one")
		speechHistory.unregister()
		self.assertFalse(speechHistory.isRegistered())
		self.assertEqual(list(self.nvda.extensions.pre_speech.handlers), [])
		self.speak("two")
		self.assertEqual(speechHistory.entries(), [], "forgotten, and nothing more kept")

	def test_neverKeepsNvdaFromSpeaking(self):
		speechHistory.register()
		with mock.patch.object(speechHistory, "lineOf", side_effect=RuntimeError("broken")):
			self.speak("still said")
		self.assertEqual(self.nvda.said(), ["still said"])


# -- the commands: NVDA+Shift+J, then H, Control+H and Shift+H ------------------------------------------------------


class CommandTests(SpeechHistoryCase):
	def setUp(self):
		super().setUp()
		before = clipboardText()
		self.addCleanup(self._restoreClipboard, before)

	def _restoreClipboard(self, before):
		if before is not None and wx.TheClipboard.Open():
			try:
				wx.TheClipboard.SetData(wx.TextDataObject(before))
				wx.TheClipboard.Flush()
			finally:
				wx.TheClipboard.Close()

	def test_controlHCopiesAllOfItOneLineEach(self):
		speechHistory.register()
		self.speak("Speech History", "dialog")
		self.speak("Data (D", "2 of 8")
		self.speak("Items View", "list")
		self.assertTrue(speechHistory.copyAndSay())
		# Through NVDA's api.copyToClip, on Windows' own clipboard, which it read back.
		self.assertEqual(rawClipboardText(), "Speech History  dialog\r\nData (D  2 of 8\r\nItems View  list")
		self.assertEqual(self.nvda.said()[-1], "Copy speech history to clipboard")
		self.assertEqual(speechHistory.entries()[-1], "Copy speech history to clipboard", "said after the copy, as JAWS")
		# Pasted with Control+V, each thing said is a line of its own.
		box = wx.TextCtrl(_frame, style=wx.TE_MULTILINE)
		try:
			box.Paste()
			self.assertEqual(box.GetValue().splitlines(), ["Speech History  dialog", "Data (D  2 of 8", "Items View  list"])
		finally:
			box.Destroy()

	def test_nothingToCopy(self):
		speechHistory.register()
		self.assertFalse(speechHistory.copyAndSay())
		self.assertEqual(self.nvda.said(), ["No speech history"])

	def test_shiftHSaysItThenClears(self):
		speechHistory.register()
		self.speak("one")
		speechHistory.clearAndSay()
		self.assertEqual(self.nvda.said(), ["one", "Speech history cleared"])
		self.assertEqual(speechHistory.entries(), [], "the words aren't in it, as in JAWS")
		self.speak("two")
		self.assertEqual(speechHistory.entries(), ["two"])

	def test_turnedOff(self):
		speechHistory.register()
		speechHistory.unregister()
		self.assertFalse(speechHistory.showAndSay())
		self.assertFalse(speechHistory.copyAndSay())
		message = "Speech history disabled. Turn it on in NVDA's Settings, JAWS Migration Assistant."
		self.assertEqual(self.nvda.said(), [message, message])

	def test_whenNvdaWontLetItListen(self):
		extensions = types.ModuleType("speech.extensions")
		with mock.patch.dict(sys.modules, {"speech.extensions": extensions}):
			self.assertFalse(speechHistory.register())
		self.assertFalse(speechHistory.copyAndSay())
		self.assertEqual(self.nvda.said(), ["The speech history can't be kept. The assistant's debug log says why."])


class ViewerTests(SpeechHistoryCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(speechHistory.closeViewer)
		speechHistory.register()

	def _viewer(self):
		viewer = speechHistory._viewer
		self.assertIsNotNone(viewer)
		return viewer

	def test_hShowsItOnTheMostRecentLine(self):
		for said in ("Start Button", "Folder View  List view", "JAWS 2021  checked", "6 of 8"):
			self.speak(*said.split("  "))
		self.assertTrue(speechHistory.showAndSay())
		viewer = self._viewer()
		self.assertEqual(viewer.GetTitle(), "Speech History")
		self.assertEqual(viewer.text.GetValue().splitlines(), ["Start Button", "Folder View  List view", "JAWS 2021  checked", "6 of 8"])
		# The line NVDA reads when the window opens: the most recent one, as JAWS's Results Viewer opens on it.
		self.assertEqual(NvdaReadsTheLine(viewer.text).lineAtCaret(), "6 of 8")
		labels = [child.GetLabel() for child in viewer.GetChildren() if isinstance(child, wx.Button)]
		self.assertEqual(labels, ["&Copy all", "C&lear", "Cl&ose"])
		self.assertEqual(viewer.GetEscapeId(), wx.ID_CANCEL, "Escape closes it")

	def test_500LongLines(self):
		for number in range(1, 501):
			self.speak(f"line {number}", "x" * 150)
		speechHistory.showAndSay()
		viewer = self._viewer()
		self.assertEqual(len(viewer.text.GetValue().splitlines()), 500)
		self.assertEqual(NvdaReadsTheLine(viewer.text).lineAtCaret(), "line 500  " + "x" * 150)

	def test_readingItAddsNothing(self):
		self.speak("one")
		speechHistory.showAndSay()
		viewer = self._viewer()
		viewer._onActivate(wx.ActivateEvent(wx.wxEVT_ACTIVATE, True))
		self.speak("Speech History", "dialog")
		self.speak("one")
		self.assertEqual(speechHistory.entries(), ["one"])
		# In another window, NVDA's speech is kept again.
		viewer._onActivate(wx.ActivateEvent(wx.wxEVT_ACTIVATE, False))
		self.speak("Notepad")
		self.assertEqual(speechHistory.entries(), ["one", "Notepad"])

	def test_hAgainShowsWhatIsNewInTheSameWindow(self):
		self.speak("one")
		speechHistory.showAndSay()
		viewer = self._viewer()
		viewer._onActivate(wx.ActivateEvent(wx.wxEVT_ACTIVATE, False))
		self.speak("two")
		speechHistory.showAndSay()
		self.assertIs(self._viewer(), viewer)
		self.assertEqual(NvdaReadsTheLine(viewer.text).lineAtCaret(), "two")

	def test_copyAllAndClear(self):
		self.speak("one")
		self.speak("two")
		speechHistory.showAndSay()
		viewer = self._viewer()
		before = clipboardText()
		try:
			viewer._onCopy(None)
			self.assertEqual(rawClipboardText(), "one\r\ntwo")
		finally:
			if before is not None and wx.TheClipboard.Open():
				wx.TheClipboard.SetData(wx.TextDataObject(before))
				wx.TheClipboard.Flush()
				wx.TheClipboard.Close()
		viewer._onClear(None)
		self.assertEqual(viewer.text.GetValue(), "")
		self.assertEqual(speechHistory.entries(), [])
		self.assertEqual(self.nvda.said()[-2:], ["Copy speech history to clipboard", "Speech history cleared"])

	def test_closing(self):
		self.speak("one")
		speechHistory.showAndSay()
		viewer = self._viewer()
		viewer._onActivate(wx.ActivateEvent(wx.wxEVT_ACTIVATE, True))
		viewer.Close()
		wx.Yield()
		self.assertIsNone(speechHistory._viewer)
		self.speak("Notepad")
		self.assertEqual(speechHistory.entries(), ["one", "Notepad"], "kept again once the window is gone")

	def test_escapeClosesIt(self):
		self.speak("one")
		speechHistory.showAndSay()
		viewer = self._viewer()
		# wx's dialogs press their Escape button (SetEscapeId) for Escape, from any control in them.
		event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
		event.SetKeyCode(wx.WXK_ESCAPE)
		event.SetEventObject(viewer.text)
		viewer.ProcessEvent(event)
		wx.Yield()
		self.assertIsNone(speechHistory._viewer)

	def test_turningItOffClosesTheWindow(self):
		self.speak("one")
		speechHistory.showAndSay()
		speechHistory.unregister()
		self.assertIsNone(speechHistory._viewer)

	def test_nothingToShow(self):
		self.assertFalse(speechHistory.showAndSay())
		self.assertIsNone(speechHistory._viewer)
		self.assertEqual(self.nvda.said(), ["No speech history"])


# -- JAWS's keys, NVDA's names for them, and JAWS's option ----------------------------------------------------------


class JawsTests(unittest.TestCase):
	def _jawsLayerKeys(self):
		path = os.path.join(JAWS_SCRIPTS, "enu", "Default.JKM")
		if not os.path.isfile(path):
			return JAWS_LAYER_KEYS
		jkm = jawsFiles.readIni(path)
		found = {}
		for key, script in jkm.section("Common Keys").items():
			if key in JAWS_LAYER_KEYS:
				found[key] = script
		return found

	def test_theLayerHasJawsKeys(self):
		keys = self._jawsLayerKeys()
		self.assertEqual(keys, JAWS_LAYER_KEYS)
		ours = {"ShowSpeechHistory": "showSpeechHistory", "CopySpeechHistoryToClipboard": "copySpeechHistory", "ClearSpeechHistory": "clearSpeechHistory", "BasicLayerHelp": "layerHelp"}
		normalize = run(NVDA_NORMALIZE_GESTURE, {}, "inputCore.py")["normalizeGestureIdentifier"]
		layer = {normalize(gesture): script for gesture, script in jawsMigrator.LAYER_GESTURES.items()}
		self.assertEqual(len(layer), len(jawsMigrator.LAYER_GESTURES), "no key twice")
		for jawsKey, jawsScript in keys.items():
			# The key after Insert+Space, as the assistant names JAWS's keys for NVDA everywhere else.
			gesture, reason = jawsKeyMap._convertKey(jawsKey.split("&", 1)[1], "common")
			self.assertIsNotNone(gesture, reason)
			self.assertEqual(layer.get(normalize(gesture)), ours[jawsScript], jawsKey)
		self.assertEqual(layer.get(normalize("kb:f1")), "layerHelp")
		self.assertFalse(set(layer.values()) - {name[len("script_"):] for name in dir(jawsMigrator.GlobalPlugin) if name.startswith("script_")})

	def test_questionMarkIsSlashWithShiftInNvda(self):
		# keyboardHandler.KeyboardInputGesture._get_mainKeyName: a key vkCodes doesn't name is named by the character
		# MapVirtualKeyEx(vkCode, MAPVK_VK_TO_CHAR) gives, and "?" is Shift and VK_OEM_2 on a US keyboard.
		layout = windll.user32.GetKeyboardLayout(0) & 0xFFFF
		if layout != 0x0409:
			self.skipTest("not a US English keyboard layout")
		winUser = run(NVDA_WINUSER_MESSAGES, {}, "winUser.py")
		MapVirtualKeyEx = windll.user32.MapVirtualKeyExW
		MapVirtualKeyEx.argtypes = (UINT, UINT, HANDLE)
		MapVirtualKeyEx.restype = UINT
		vkChar = MapVirtualKeyEx(0xBF, winUser["MAPVK_VK_TO_CHAR"], windll.user32.GetKeyboardLayout(0))
		self.assertEqual(chr(vkChar).lower(), "/")
		self.assertIn("kb:shift+/", jawsMigrator.LAYER_GESTURES)

	def test_theHelpSaysTheKeys(self):
		for text in (
			"H, what NVDA said, the most recent last, as JAWS's speech history. ",
			"Control+H, copy the speech history to the clipboard. ",
			"Shift+H, clear the speech history. ",
			"Question mark or F1, this help. Escape leaves the layer.",
		):
			self.assertIn(text, jawsMigrator.LAYER_HELP)
		self.assertNotIn("H, this help", jawsMigrator.LAYER_HELP)

	def test_jawsOwnWords(self):
		path = os.path.join(JAWS_SCRIPTS, "common.jsm")
		messages = dict(JAWS_MESSAGES)
		if os.path.isfile(path):
			with open(path, encoding="utf-8", errors="replace") as f:
				lines = [line.strip() for line in f]
			for name in messages:
				messages[name] = lines[lines.index("@" + name) + 1]
		self.assertEqual(messages, JAWS_MESSAGES)
		self.assertEqual(speechHistory.CLEARED, messages["cmsgClearSpeechHistory"])
		self.assertEqual(speechHistory.COPIED, messages["cmsgCopySpeechHistory"])
		self.assertEqual(speechHistory.TITLE, messages["cmsgSpeechHistoryTitle"])
		self.assertTrue(speechHistory.DISABLED.startswith(messages["cmsgSpeechHistoryNotAvailable"] + ". "))

	def test_jawsOptionComesOver(self):
		for raw, value in (("0", False), ("1", True)):
			source = jawsFiles.parseIni(f"[Options]\nSpeechHistory={raw}\nTypingInterrupt=1\n")
			result = settingsMap.mapSettings(source)
			changes = [c for c in result.changes if c.target == settingsMap.ASSISTANT]
			self.assertEqual([(c.path, c.value) for c in changes], [(("keepSpeechHistory",), value)])
			self.assertIn(f"{'on' if value else 'off'}, as JAWS's speech history", changes[0].label)
			self.assertEqual(changes[0].source, f"[options] SpeechHistory={raw}")
			self.assertNotIn("SpeechHistory", [item.key for item in result.notMigrated])
		# A JAWS setting for every application, not for one.
		result = settingsMap.mapSettings(jawsFiles.parseIni("[Options]\nSpeechHistory=0\n"), isApplication=True)
		self.assertEqual([c for c in result.changes if c.target == settingsMap.ASSISTANT], [])

	def test_onUnlessTurnedOff(self):
		from jawsMigrator import state

		self.assertIs(state.DEFAULTS[speechHistory.STATE_KEY], True)
		self.assertTrue(speechHistory.wanted({}))
		self.assertFalse(speechHistory.wanted({speechHistory.STATE_KEY: False}))


class NvdasOwnCodeTests(unittest.TestCase):
	def test_theCodeIsNvdas(self):
		# Each piece is in NVDA 2026.2's source, at the margin or as a method, when a copy of it is around: set
		# NVDA_SOURCE to its source folder.
		source = os.environ.get("NVDA_SOURCE")
		if not source:
			self.skipTest("NVDA_SOURCE isn't set to a folder with NVDA 2026.2's source")
		for name, path in NVDA_CODE_FILES.items():
			with open(os.path.join(source, *path.split("/")), encoding="utf-8") as f:
				text = f.read().replace("\r\n", "\n")
			for block in globals()[name].strip("\n").split("\n\n\n"):
				self.assertTrue(block in text or textwrap.indent(block, "\t") in text, f"{name}: {block.splitlines()[0]}")


if __name__ == "__main__":
	unittest.main()
