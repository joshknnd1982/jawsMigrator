# Unit tests for version 1.33, from the tester's comments on issue 30 ("issue with how NVDA reads certain things on
# Reddit") after 1.31. With 1.31, E said the reddit post's fields exactly as their JAWS did. Then the tester pasted
# what NVDA and JAWS said as they switched with Alt+Tab from an Outlook message to Edge, where a GitHub page had the
# focus in its comment box, and from there to their reddit tab. NVDA's log (NVDA 2026.2, the assistant 1.31, 16:20:10
# and 16:20:31) has these "Speaking" lines:
#     I've had data issues ... : r/Visible and 2 more pages - Profile 1 - Microsoft Edge
#     issue with how NVDA reads certain things on Reddit · Issue #30 · joshknnd1982/jawsMigrator  document
#     main landmark
#     new Comment  grouping
#     Add a comment  edit  Markdown input: edit mode selected.  W
#     (all of that again)
#     I've had data issues ... : r/Visible
#     I've had data issues ... : r/Visible
#     link  Skip to main content
# The tester had picked the reddit tab in Alt+Tab, and Edge put the focus back in the GitHub comment box, where it had
# been, before it moved to the reddit page. JAWS said the reddit page's title only. Switching to the GitHub tab, JAWS
# said the window, the title without "page" or "document", "MainRegion", "new Comment group" and the focused button.
# - browserPages: a page NVDA says as a place the focus is in (reason FOCUSENTERED) is said by its title too, without
#   "document"; what NVDA says for a place the focus is in, in Edge and Chrome, is dropped if NVDA hasn't said it yet
#   once the focus isn't in it any more; and a window's name or a page's title isn't said again while NVDA is still
#   saying it.
# - speechHistory: what NVDA's speech manager dropped before the synthesizer said any of it isn't in the history, as
#   JAWS's history holds what went to the synthesizer. The tester's pasted history had the GitHub page twice.
# NVDA 2026.2's own code runs here, word for word (see NvdasOwnCodeTests): its speech manager (speech/manager.py) with
# its speech commands and priorities, speech.speak and cancelSpeech, eventHandler's FocusLossCancellableSpeechCommand,
# _getFocusLossCancellableSpeechCommand and doPreGainFocus, api's setFocusObject and the functions around it,
# NVDAObject.event_foreground, and, from tests/test_v126_formFields.py and test_v131_redditPage.py, speakObject,
# getObjectSpeech, getPropertiesSpeech, NVDAObject.reportFocus and event_focusEntered with NVDA's roles and states.
# eventHandler.executeEvent is imitated: a focus event runs doPreGainFocus, then the object's event_gainFocus, as NVDA
# does when no plugin, app module or tree interceptor takes the event. So is the synthesizer: it takes what the speech
# manager gives it, and says it has reached each index when a test lets it finish. The assistant's code is the real one.
# Run: python -m unittest tests.test_v133_tabSwitch -v

import logging
import os
import sys
import textwrap
import types
import typing
import unittest
from abc import ABCMeta, abstractmethod
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple, cast
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import nvdaStubs  # noqa: E402

nvdaStubs.install()

# NVDA 2026.2's object speech, its roles and states, and the tester's settings (test_v126_formFields), the page's
# objects as NVDA gets them from Edge (test_v131_redditPage), and NVDA's extension points and speech.speak
# (test_v129_speechHistory).
import test_v131_redditPage as v131  # noqa: E402
import test_v129_speechHistory as v129  # noqa: E402

v126, v125 = v131.v126, v131.v125

from jawsMigrator import browserPages, formFields, speechHistory, speechQueue  # noqa: E402

Role, State, OutputReason = v126.Role, v126.State, v126.OutputReason

# -- NVDA 2026.2's own code, word for word (see NvdasOwnCodeTests) -----------------------------------------------

NVDA_COMMANDS = 'class SpeechCommand(object):\n\t"""The base class for objects that can be inserted between strings of text to perform actions,\n\tchange voice parameters, etc.\n\n\tNote: Some of these commands are processed by NVDA and are not directly passed to synth drivers.\n\tsynth drivers will only receive commands derived from L{SynthCommand}.\n\t"""\n\n\nclass _CancellableSpeechCommand(SpeechCommand):\n\t"""\n\tA command that allows cancelling the utterance that contains it.\n\tSupport currently experimental and may be subject to change.\n\t"""\n\n\tdef __init__(\n\t\tself,\n\t\treportDevInfo=False,\n\t):\n\t\t"""\n\t\t@param reportDevInfo: If true, developer info is reported for repr implementation.\n\t\t"""\n\t\tself._isCancelled = False\n\t\tself._utteranceIndex = None\n\t\tself._reportDevInfo = reportDevInfo\n\n\t@abstractmethod\n\tdef _checkIfValid(self):\n\t\traise NotImplementedError()\n\n\t@abstractmethod\n\tdef _getDevInfo(self):\n\t\traise NotImplementedError()\n\n\tdef _checkIfCancelled(self):\n\t\tif self._isCancelled:\n\t\t\treturn True\n\t\telif not self._checkIfValid():\n\t\t\tself._isCancelled = True\n\t\treturn self._isCancelled\n\n\t@property\n\tdef isCancelled(self):\n\t\treturn self._checkIfCancelled()\n\n\tdef cancelUtterance(self):\n\t\tself._isCancelled = True\n\n\tdef _getFormattedDevInfo(self):\n\t\treturn (\n\t\t\t""\n\t\t\tif not self._reportDevInfo\n\t\t\telse (\n\t\t\t\tf", devInfo<"\n\t\t\t\tf" isCanceledCache: {self._isCancelled}"\n\t\t\t\tf", isValidCallback: {self._checkIfValid()}"\n\t\t\t\tf", isValidCallbackDevInfo: {self._getDevInfo()} >"\n\t\t\t)\n\t\t)\n\n\tdef __repr__(self):\n\t\treturn (\n\t\t\tf"CancellableSpeech ("\n\t\t\tf"{\'cancelled\' if self._checkIfCancelled() else \'still valid\'}"\n\t\t\tf"{self._getFormattedDevInfo()}"\n\t\t\tf")"\n\t\t)\n\n\nclass SynthCommand(SpeechCommand):\n\t"""Commands that can be passed to synth drivers."""\n\n\nclass IndexCommand(SynthCommand):\n\t"""Marks this point in the speech with an index.\n\tWhen speech reaches this index, the synthesizer notifies NVDA,\n\tthus allowing NVDA to perform actions at specific points in the speech;\n\te.g. synchronizing the cursor, beeping or playing a sound.\n\tCallers should not use this directly.\n\tInstead, use one of the subclasses of L{BaseCallbackCommand}.\n\tNVDA handles the indexing and dispatches callbacks as appropriate.\n\t"""\n\n\tdef __init__(self, index):\n\t\t"""\n\t\t@param index: the value of this index\n\t\t@type index: integer\n\t\t"""\n\t\tif not isinstance(index, int):\n\t\t\traise ValueError("index must be int, not %s" % type(index))\n\t\tself.index = index\n\n\tdef __repr__(self):\n\t\treturn "IndexCommand(%r)" % self.index\n\n\tdef __eq__(self, __o: object) -> bool:\n\t\tif __o is self:\n\t\t\treturn True\n\t\tif type(self) is not type(__o):\n\t\t\treturn super().__eq__(__o)\n\t\treturn self.index == __o.index\n\n\nclass SynthParamCommand(SynthCommand):\n\t"""A synth command which changes a parameter for subsequent speech."""\n\n\t#: Whether this command returns the parameter to its default value.\n\t#: Note that the default might be configured by the user;\n\t#: e.g. for pitch, rate, etc.\n\t#: @type: bool\n\tisDefault = False\n\n\nclass CharacterModeCommand(SynthParamCommand):\n\t"""Turns character mode on and off for speech synths."""\n\n\tdef __init__(self, state):\n\t\t"""\n\t\t@param state: if true character mode is on, if false its turned off.\n\t\t@type state: boolean\n\t\t"""\n\t\tif not isinstance(state, bool):\n\t\t\traise ValueError("state must be boolean, not %s" % type(state))\n\t\tself.state = state\n\t\tself.isDefault = not state\n\n\tdef __repr__(self):\n\t\treturn "CharacterModeCommand(%r)" % self.state\n\n\tdef __eq__(self, __o: object) -> bool:\n\t\tif __o is self:\n\t\t\treturn True\n\t\tif type(self) is not type(__o):\n\t\t\treturn super().__eq__(__o)\n\t\treturn self.state == __o.state\n\n\nclass LangChangeCommand(SynthParamCommand):\n\t"""A command to switch the language within speech."""\n\n\tdef __init__(self, lang: str | None):\n\t\t"""\n\t\t:param lang: The language to switch to: If None then the NVDA locale will be used.\n\t\t"""\n\t\tself.lang = lang\n\t\tself.isDefault = not lang\n\n\tdef __repr__(self):\n\t\treturn "LangChangeCommand (%r)" % self.lang\n\n\tdef __eq__(self, __o: object) -> bool:\n\t\tif __o is self:\n\t\t\t# __o is a reference to the same object.\n\t\t\t# Check performed first for performance reasons.\n\t\t\treturn True\n\t\tif isinstance(__o, LangChangeCommand):\n\t\t\treturn self.lang == __o.lang\n\t\treturn super().__eq__(__o)\n\n\nclass BreakCommand(SynthCommand):\n\t"""Insert a break between words."""\n\n\tdef __init__(self, time: int = 0):\n\t\t"""\n\t\t@param time: The duration of the pause to be inserted in milliseconds.\n\t\t"""\n\t\tself.time = time\n\t\t"""Time in milliseconds"""\n\n\tdef __repr__(self):\n\t\treturn f"BreakCommand(time={self.time})"\n\n\tdef __eq__(self, __o: object) -> bool:\n\t\tif __o is self:\n\t\t\treturn True\n\t\tif type(self) is not type(__o):\n\t\t\treturn super().__eq__(__o)\n\t\treturn self.time == __o.time\n\n\nclass EndUtteranceCommand(SpeechCommand):\n\t"""End the current utterance at this point in the speech.\n\tAny text after this will be sent to the synthesizer as a separate utterance.\n\t"""\n\n\tdef __repr__(self):\n\t\treturn "EndUtteranceCommand()"\n\n\nclass SuppressUnicodeNormalizationCommand(SpeechCommand):\n\t"""Suppresses Unicode normalization at a point in a speech sequence.\n\tFor any text after this, Unicode normalization will be suppressed when state is True.\n\tWhen state is False, original behavior of normalization will be restored.\n\tThis command is a no-op when normalization is disabled.\n\t"""\n\n\tstate: bool\n\n\tdef __init__(self, state: bool = True):\n\t\t"""\n\t\t:param state: Suppress normalization if True, don\'t suppress when False\n\t\t"""\n\t\tself.state = state\n\n\tdef __repr__(self):\n\t\treturn f"SuppressUnicodeNormalizationCommand({self.state!r})"\n\n\nclass BaseProsodyCommand(SynthParamCommand):\n\t"""Base class for commands which change voice prosody; i.e. pitch, rate, etc.\n\tThe change to the setting is specified using either an offset or a multiplier, but not both.\n\tThe L{offset} and L{multiplier} properties convert between the two if necessary.\n\tTo return to the default value, specify neither.\n\tThis base class should not be instantiated directly.\n\t"""\n\n\t#: The name of the setting in the configuration; e.g. pitch, rate, etc.\n\tsettingName = None\n\n\tdef __init__(self, offset=0, multiplier=1):\n\t\t"""Constructor.\n\t\tEither of C{offset} or C{multiplier} may be specified, but not both.\n\t\t@param offset: The amount by which to increase/decrease the user configured setting;\n\t\t\te.g. 30 increases by 30, -10 decreases by 10, 0 returns to the configured setting.\n\t\t@type offset: int\n\t\t@param multiplier: The number by which to multiply the user configured setting;\n\t\t\te.g. 0.5 is half, 1 returns to the configured setting.\n\t\t@param multiplier: int/float\n\t\t"""\n\t\tif offset != 0 and multiplier != 1:\n\t\t\traise ValueError("offset and multiplier both specified")\n\t\tself._offset = offset\n\t\tself._multiplier = multiplier\n\t\tself.isDefault = offset == 0 and multiplier == 1\n\n\t@property\n\tdef defaultValue(self):\n\t\t"""The default value for the setting as configured by the user."""\n\t\tsynth = getSynth()\n\t\tsynthConf = config.conf["speech"][synth.name]\n\t\treturn synthConf[self.settingName]\n\n\t@property\n\tdef multiplier(self):\n\t\t"""The number by which to multiply the default value."""\n\t\tif self._multiplier != 1:\n\t\t\t# Constructed with multiplier. Just return it.\n\t\t\treturn self._multiplier\n\t\tif self._offset == 0:\n\t\t\t# Returning to default.\n\t\t\treturn 1\n\t\t# Calculate multiplier from default value and offset.\n\t\tdefaultVal = self.defaultValue\n\t\tnewVal = defaultVal + self._offset\n\t\treturn float(newVal) / defaultVal\n\n\t@property\n\tdef offset(self):\n\t\t"""The amount by which to increase/decrease the default value."""\n\t\tif self._offset != 0:\n\t\t\t# Constructed with offset. Just return it.\n\t\t\treturn self._offset\n\t\tif self._multiplier == 1:\n\t\t\t# Returning to default.\n\t\t\treturn 0\n\t\t# Calculate offset from default value and multiplier.\n\t\tdefaultVal = self.defaultValue\n\t\tnewVal = defaultVal * self._multiplier\n\t\treturn int(newVal - defaultVal)\n\n\t@property\n\tdef newValue(self):\n\t\t"""The new absolute value after the offset or multiplier is applied to the default value."""\n\t\tif self._offset != 0:\n\t\t\t# Calculate using offset.\n\t\t\treturn self.defaultValue + self._offset\n\t\tif self._multiplier != 1:\n\t\t\t# Calculate using multiplier.\n\t\t\treturn int(self.defaultValue * self._multiplier)\n\t\t# Returning to default.\n\t\treturn self.defaultValue\n\n\tdef __repr__(self):\n\t\tif self._offset != 0:\n\t\t\tparam = "offset=%d" % self._offset\n\t\telif self._multiplier != 1:\n\t\t\tparam = "multiplier=%g" % self._multiplier\n\t\telse:\n\t\t\tparam = ""\n\t\treturn "{type}({param})".format(\n\t\t\ttype=type(self).__name__,\n\t\t\tparam=param,\n\t\t)\n\n\tdef __eq__(self, __o: object) -> bool:\n\t\tif __o is self:\n\t\t\treturn True\n\t\tif type(self) is not type(__o):\n\t\t\treturn super().__eq__(__o)\n\t\treturn self._offset == __o._offset and self._multiplier == __o._multiplier\n\n\tdef __ne__(self, __o) -> bool:\n\t\tif __o is self:\n\t\t\treturn False\n\t\tif type(self) is not type(__o):\n\t\t\treturn super().__ne__(__o)\n\t\treturn self._offset != __o._offset or self._multiplier != __o._multiplier\n\n\nclass PitchCommand(BaseProsodyCommand):\n\t"""Change the pitch of the voice."""\n\n\tsettingName = "pitch"\n\n\nclass VolumeCommand(BaseProsodyCommand):\n\t"""Change the volume of the voice."""\n\n\tsettingName = "volume"\n\n\nclass RateCommand(BaseProsodyCommand):\n\t"""Change the rate of the voice."""\n\n\tsettingName = "rate"\n\n\nclass PhonemeCommand(SynthCommand):\n\t"""Insert a specific pronunciation.\n\tThis command accepts Unicode International Phonetic Alphabet (IPA) characters.\n\tNote that this is not well supported by synthesizers.\n\t"""\n\n\tdef __init__(self, ipa, text=None):\n\t\t"""\n\t\t@param ipa: Unicode IPA characters.\n\t\t@type ipa: str\n\t\t@param text: Text to speak if the synthesizer does not support\n\t\t\tsome or all of the specified IPA characters,\n\t\t\tC{None} to ignore this command instead.\n\t\t@type text: str\n\t\t"""\n\t\tself.ipa = ipa\n\t\tself.text = text\n\n\tdef __repr__(self):\n\t\tout = "PhonemeCommand(%r" % self.ipa\n\t\tif self.text:\n\t\t\tout += ", text=%r" % self.text\n\t\treturn out + ")"\n\n\tdef __eq__(self, __o: object) -> bool:\n\t\tif __o is self:\n\t\t\treturn True\n\t\tif type(self) is not type(__o):\n\t\t\treturn super().__eq__(__o)\n\t\treturn self.ipa == __o.ipa and self.text == __o.text\n\n\nclass BaseCallbackCommand(SpeechCommand, metaclass=ABCMeta):\n\t"""Base class for commands which cause a function to be called when speech reaches them.\n\tThis class should not be instantiated directly.\n\tIt is designed to be subclassed to provide specific functionality;\n\te.g. L{BeepCommand}.\n\tTo supply a generic function to run, use L{CallbackCommand}.\n\tThis command is never passed to synth drivers.\n\t"""\n\n\t@abstractmethod\n\tdef run(self):\n\t\t"""Code to run when speech reaches this command.\n\t\tThis method is executed in NVDA\'s main thread,\n\t\ttherefore must return as soon as practically possible,\n\t\totherwise it will block production of further speech and or other functionality in NVDA.\n\t\t"""\n\n\nclass CallbackCommand(BaseCallbackCommand):\n\t"""\n\tCall a function when speech reaches this point.\n\tNote that  the provided function is executed in NVDA\'s main thread,\n\t\ttherefore must return as soon as practically possible,\n\t\totherwise it will block production of further speech and or other functionality in NVDA.\n\t"""\n\n\tdef __init__(self, callback, name: Optional[str] = None):\n\t\tself._callback = callback\n\t\tself._name = name if name else repr(callback)\n\n\tdef run(self, *args, **kwargs):\n\t\treturn self._callback(*args, **kwargs)\n\n\tdef __repr__(self):\n\t\treturn "CallbackCommand(name={name})".format(\n\t\t\tname=self._name,\n\t\t)\n\n\nclass BeepCommand(BaseCallbackCommand):\n\t"""Produce a beep."""\n\n\tdef __init__(self, hz, length, left=50, right=50):\n\t\tself.hz = hz\n\t\tself.length = length\n\t\tself.left = left\n\t\tself.right = right\n\n\tdef run(self):\n\t\timport tones\n\n\t\ttones.beep(\n\t\t\tself.hz,\n\t\t\tself.length,\n\t\t\tleft=self.left,\n\t\t\tright=self.right,\n\t\t\tisSpeechBeepCommand=True,\n\t\t)\n\n\tdef __repr__(self):\n\t\treturn "BeepCommand({hz}, {length}, left={left}, right={right})".format(\n\t\t\thz=self.hz,\n\t\t\tlength=self.length,\n\t\t\tleft=self.left,\n\t\t\tright=self.right,\n\t\t)\n\n\nclass WaveFileCommand(BaseCallbackCommand):\n\t"""Play a wave file."""\n\n\tdef __init__(self, fileName):\n\t\tself.fileName = fileName\n\n\tdef run(self):\n\t\timport nvwave\n\n\t\tnvwave.playWaveFile(self.fileName, asynchronous=True, isSpeechWaveFileCommand=True)\n\n\tdef __repr__(self):\n\t\treturn "WaveFileCommand(%r)" % self.fileName\n\n\nclass ConfigProfileTriggerCommand(SpeechCommand):\n\t"""Applies (or stops applying) a configuration profile trigger to subsequent speech."""\n\n\tdef __init__(self, trigger, enter=True):\n\t\t"""\n\t\t@param trigger: The configuration profile trigger.\n\t\t@type trigger: L{config.ProfileTrigger}\n\t\t@param enter: C{True} to apply the trigger, C{False} to stop applying it.\n\t\t@type enter: bool\n\t\t"""\n\t\tself.trigger = trigger\n\t\tself.enter = enter\n\t\ttrigger._shouldNotifyProfileSwitch = False'

NVDA_PRIORITIES = 'class SpeechPriority(IntEnum):\n\t"""Facilitates the ability to prioritize speech.\n\tNote: This enum has its counterpart in the NVDAController RPC interface (nvdaController.idl).\n\tAdditions to this enum should also be reflected in nvdaController.idl.\n\t"""\n\n\t#: Indicates that a speech sequence should have normal priority.\n\tNORMAL = 0\n\t#: Indicates that a speech sequence should be spoken after the next utterance of lower priority is complete.\n\tNEXT = 1\n\t#: Indicates that a speech sequence is very important and should be spoken right now,\n\t#: interrupting low priority speech.\n\t#: After it is spoken, interrupted speech will resume.\n\t#: Note that this does not interrupt previously queued speech at the same priority.\n\tNOW = 2\n\n\n#: Easy shorthand for the Speechpriority class\nSpri = SpeechPriority\n#: The speech priorities ordered from highest to lowest.\nSPEECH_PRIORITIES = tuple(reversed(SpeechPriority))'

NVDA_MANAGER = 'def _shouldCancelExpiredFocusEvents():\n\t# 0: default (yes), 1: yes, 2: no\n\treturn config.conf["featureFlag"]["cancelExpiredFocusSpeech"] != 2\n\n\ndef _shouldDoSpeechManagerLogging():\n\treturn config.conf["debugLog"]["speechManager"]\n\n\ndef _speechManagerDebug(msg, *args, **kwargs) -> None:\n\t"""Log \'msg % args\' with severity \'DEBUG\' if speech manager logging is enabled.\n\t\'SpeechManager-\' is prefixed to all messages to make searching the log easier.\n\t"""\n\tif not log.isEnabledFor(log.DEBUG) or not _shouldDoSpeechManagerLogging():\n\t\treturn\n\tlog._log(log.DEBUG, "SpeechManager- " + msg, args, **kwargs)\n\n\n#: Turns on unit test logging, logs the key interactions that happen with speech manager. When False,\n# log messages are sent to _speechManagerDebug\nIS_UNIT_TEST_LOG_ENABLED = False\n\n\ndef _speechManagerUnitTest(msg, *args, **kwargs) -> None:\n\t"""Log \'msg % args\' with severity \'DEBUG\' if .\n\t\'SpeechManUnitTest-\' is prefixed to all messages to make searching the log easier.\n\tWhen\n\t"""\n\tif not IS_UNIT_TEST_LOG_ENABLED:\n\t\t# Don\'t reuse _speechManagerDebug, it leads to incorrect function names in the log (all\n\t\t# SpeechManager debug logging appears to come from _speechManagerUnitTest instead of the frame\n\t\t# one stack higher. The codepath argument for _log could also be used to resolve this, but duplication\n\t\t# simpler.\n\t\tif log.isEnabledFor(log.DEBUG) and _shouldDoSpeechManagerLogging():\n\t\t\tlog._log(log.DEBUG, "SpeechManager- " + msg, args, **kwargs)\n\t\treturn\n\tlog._log(log.INFO, "SpeechManUnitTest- " + msg, args, **kwargs)\n\n\n# Install the custom log handlers.\n#: For extra debug level logging, this is a category that must be enabled in the advanced settings panel.\nlog._speechManagerDebug = _speechManagerDebug\n\n#: Info level logging (only enabled if IS_UNIT_TEST_LOG_ENABLED hardcoded to True). This is a developer\n# tool to ease the creation of unit tests for SpeechManager. It should log all external interactions with\n# SpeechManager so they can be recreated in tests.\nlog._speechManagerUnitTest = _speechManagerUnitTest\n\n\nclass ParamChangeTracker(object):\n\t"""Keeps track of commands which change parameters from their defaults.\n\tThis is useful when an utterance needs to be split.\n\tAs you are processing a sequence,\n\tyou update the tracker with a parameter change using the L{update} method.\n\tWhen you split the utterance, you use the L{getChanged} method to get\n\tthe parameters which have been changed from their defaults.\n\t"""\n\n\tdef __init__(self):\n\t\tself._commands = {}\n\n\tdef update(self, command):\n\t\t"""Update the tracker with a parameter change.\n\t\t@param command: The parameter change command.\n\t\t@type command: L{SynthParamCommand}\n\t\t"""\n\t\tparamType = type(command)\n\t\tif command.isDefault:\n\t\t\t# This no longer applies.\n\t\t\tself._commands.pop(paramType, None)\n\t\telse:\n\t\t\tself._commands[paramType] = command\n\n\tdef getChanged(self):\n\t\t"""Get the commands for the parameters which have been changed from their defaults.\n\t\t@return: List of parameter change commands.\n\t\t@type: list of L{SynthParamCommand}\n\t\t"""\n\t\treturn list(self._commands.values())\n\n\nclass _ManagerPriorityQueue(object):\n\t"""A speech queue for a specific priority.\n\tThis is intended for internal use by L{_SpeechManager} only.\n\tEach priority has a separate queue.\n\tIt holds the pending speech sequences to be spoken,\n\tas well as other information necessary to restore state when this queue\n\tis preempted by a higher priority queue.\n\t"""\n\n\tdef __init__(self, priority: Spri):\n\t\tself.priority = priority\n\t\t#: The pending speech sequences to be spoken.\n\t\t#: These are split at indexes,\n\t\t#: so a single utterance might be split over multiple sequences.\n\t\tself.pendingSequences: List[SpeechSequence] = []\n\t\t#: The configuration profile triggers that have been entered during speech.\n\t\tself.enteredProfileTriggers: List[config.ProfileTrigger] = []\n\t\t#: Keeps track of parameters that have been changed during an utterance.\n\t\tself.paramTracker: ParamChangeTracker = ParamChangeTracker()\n\n\nclass SpeechManager(object):\n\t"""Manages queuing of speech utterances, calling callbacks at desired points in the speech, profile switching, prioritization, etc.\n\tThis is intended for internal use only.\n\tIt is used by higher level functions such as L{speak}.\n\n\tThe high level flow of control is as follows:\n\t1. A speech sequence is queued with L{speak}, which in turn calls L{_queueSpeechSequence}.\n\t2. L{_processSpeechSequence} is called to normalize, process and split the input sequence.\n\t\tIt converts callbacks to indexes.\n\t\tAll indexing is assigned and managed by this class.\n\t\tIt maps any indexes to their corresponding callbacks.\n\t\tIt splits the sequence at indexes so we easily know what has completed speaking.\n\t\tIf there are end utterance commands, the sequence is split at that point.\n\t\tWe ensure there is an index at the end of all utterances so we know when they\'ve finished speaking.\n\t\tWe ensure any config profile trigger commands are preceded by an utterance end.\n\t\tParameter changes are re-applied after utterance breaks.\n\t\tWe ensure any entered profile triggers are exited at the very end.\n\t3. L{_queueSpeechSequence} places these processed sequences in the queue\n\t\tfor the priority specified by the caller in step 1.\n\t\tThere is a separate queue for each priority.\n\t4. L{_pushNextSpeech} is called to begin pushing speech.\n\t\tIt looks for the highest priority queue with pending speech.\n\t\tBecause there\'s no other speech queued, that\'ll be the queue we just touched.\n\t5. If the input begins with a profile switch, it is applied immediately.\n\t6. L{_buildNextUtterance} is called to build a full utterance and it is sent to the synth.\n\t7. For every index reached, L{_handleIndex} is called.\n\t\tThe completed sequence is removed from L{_pendingSequences}.\n\t\tIf there is an associated callback, it is run.\n\t\tIf the index marks the end of an utterance, L{_pushNextSpeech} is called to push more speech.\n\t8. If there is another utterance before a profile switch, it is built and sent as per steps 6 and 7.\n\t9. In L{_pushNextSpeech}, if a profile switch is next, we wait for the synth to finish speaking before pushing more.\n\t\tThis is because we don\'t want to start speaking too early with a different synth.\n\t\tL{_handleDoneSpeaking} is called when the synth finishes speaking.\n\t\tIt pushes more speech, which includes applying the profile switch.\n\t10. The flow then repeats from step 6 onwards until there are no more pending sequences.\n\t11. If another sequence is queued via L{speak} during speech,\n\t\tit is processed and queued as per steps 2 and 3.\n\t12. If this is the first utterance at priority now, speech is interrupted\n\t\tand L{_pushNextSpeech} is called.\n\t\tOtherwise, L{_pushNextSpeech} is called when the current utterance completes\n\t\tas per step 7.\n\t13. When L{_pushNextSpeech} is next called, it looks for the highest priority queue with pending speech.\n\t\tIf that priority is different to the priority of the utterance just spoken,\n\t\tany relevant profile switches are applied to restore the state for this queue.\n\t14. If a lower priority utterance was interrupted in the middle,\n\t\tL{_buildNextUtterance} applies any parameter changes that applied before the interruption.\n\t15. The flow then repeats from step 6 onwards until there are no more pending sequences.\n\n\tNote:\n\tAll of this activity is (and must be) synchronized and serialized on the main thread.\n\t"""\n\n\t_cancelCommandsForUtteranceBeingSpokenBySynth: Dict[_CancellableSpeechCommand, _IndexT]\n\t_priQueues: Dict[Any, _ManagerPriorityQueue]\n\t_curPriQueue: Optional[_ManagerPriorityQueue]  # None indicates no more speech.\n\n\tdef __init__(self):\n\t\t#: A counter for indexes sent to the synthesizer for callbacks, etc.\n\t\tself._indexCounter = self._generateIndexes()\n\t\tself._reset()\n\t\tsynthDriverHandler.synthIndexReached.register(self._onSynthIndexReached)\n\t\tsynthDriverHandler.synthDoneSpeaking.register(self._onSynthDoneSpeaking)\n\n\t#: Maximum index number to pass to synthesizers.\n\tMAX_INDEX: _IndexT = 9999\n\n\tdef _generateIndexes(self) -> typing.Generator[_IndexT, None, None]:\n\t\t"""Generator of index numbers.\n\t\tWe don\'t want to reuse index numbers too quickly,\n\t\tas there can be race conditions when cancelling speech which might result\n\t\tin an index from a previous utterance being treated as belonging to the current utterance.\n\t\tHowever, we don\'t want the counter increasing indefinitely,\n\t\tas some synths might not be able to handle huge numbers.\n\t\tTherefore, we use a counter which starts at 1, counts up to L{MAX_INDEX},\n\t\twraps back to 1 and continues cycling thus.\n\t\tThis maximum is arbitrary, but\n\t\tit\'s small enough that any synth should be able to handle it\n\t\tand large enough that previous indexes won\'t reasonably get reused\n\t\tin the same or previous utterance.\n\t\t"""\n\t\twhile True:\n\t\t\tfor index in range(1, self.MAX_INDEX + 1):\n\t\t\t\tyield index\n\n\tdef _reset(self):\n\t\t#: The queues for each priority.\n\t\tself._priQueues = {}\n\t\t#: The priority queue for the utterance currently being spoken.\n\t\tself._curPriQueue = None\n\t\t#: Maps indexes to BaseCallbackCommands.\n\t\tself._indexesToCallbacks = {}\n\t\t#: a list of indexes currently being spoken by the synthesizer\n\t\tself._indexesSpeaking = []\n\t\t#: Whether to push more speech when the synth reports it is done speaking.\n\t\tself._shouldPushWhenDoneSpeaking = False\n\t\tself._cancelCommandsForUtteranceBeingSpokenBySynth = {}\n\t\t#: True if the synth.cancel was called due to cancellableSpeech no longer being valid\n\t\t# and no new speech has been sent.\n\t\tself._cancelledLastSpeechWithSynth = False\n\n\tdef _synthStillSpeaking(self) -> bool:\n\t\treturn 0 < len(self._indexesSpeaking)\n\n\tdef _hasNoMoreSpeech(self):\n\t\treturn self._curPriQueue is None\n\n\tdef speak(self, speechSequence: SpeechSequence, priority: Spri):\n\t\tlog._speechManagerUnitTest("speak (priority %r): %r", priority, speechSequence)\n\t\tpre_speechQueued.notify(speechSequence=speechSequence, priority=priority)\n\t\tinterrupt = self._queueSpeechSequence(speechSequence, priority)\n\t\tself._doRemoveCancelledSpeechCommands()\n\t\t# If speech isn\'t already in progress, we need to push the first speech.\n\t\tpush = self._hasNoMoreSpeech() or not self._synthStillSpeaking()\n\t\tlog._speechManagerDebug(\n\t\t\tf"Will interrupt: {interrupt}"\n\t\t\tf" Will push: {push}"\n\t\t\tf" | _indexesSpeaking: {self._indexesSpeaking!r}"\n\t\t\tf" | _curPriQueue valid: {not self._hasNoMoreSpeech()}"\n\t\t\tf" | _shouldPushWhenDoneSpeaking: {self._shouldPushWhenDoneSpeaking}"\n\t\t\tf" | _cancelledLastSpeechWithSynth {self._cancelledLastSpeechWithSynth}",\n\t\t)\n\t\tif interrupt:\n\t\t\tlog._speechManagerDebug("Interrupting speech")\n\t\t\tgetSynth().cancel()\n\t\t\tself._indexesSpeaking.clear()\n\t\t\tself._cancelCommandsForUtteranceBeingSpokenBySynth.clear()\n\t\t\tpush = True\n\t\tif push:\n\t\t\tlog._speechManagerDebug("Pushing next speech")\n\t\t\tself._pushNextSpeech(True)\n\t\telse:\n\t\t\tlog._speechManagerDebug("Not pushing speech")\n\n\tdef _queueSpeechSequence(self, inSeq: SpeechSequence, priority: Spri) -> bool:\n\t\t"""\n\t\t@return: Whether to interrupt speech.\n\t\t"""\n\t\toutSeq = self._processSpeechSequence(inSeq)\n\t\tlog._speechManagerDebug("Out Seq: %r", outSeq)  # expensive string to build - defer\n\t\tqueue = self._priQueues.get(priority)\n\t\tlog._speechManagerDebug(\n\t\t\tf"Current priority: {priority}, queLen: {0 if queue is None else len(queue.pendingSequences)}",\n\t\t)\n\t\tif not queue:\n\t\t\tqueue = self._priQueues[priority] = _ManagerPriorityQueue(priority)\n\t\telse:\n\t\t\tlog._speechManagerDebug(\n\t\t\t\t"current queue: %r",  # expensive string to build - defer\n\t\t\t\tqueue.pendingSequences,\n\t\t\t)\n\t\tfirst = len(queue.pendingSequences) == 0\n\t\tqueue.pendingSequences.extend(outSeq)\n\t\tif priority is Spri.NOW and first:\n\t\t\t# If this is the first sequence at Spri.NOW, interrupt speech.\n\t\t\treturn True\n\t\treturn False\n\n\tdef _ensureEndUtterance(self, seq: SpeechSequence, outSeqs, paramsToReplay, paramTracker):\n\t\t"""\n\t\tWe split at EndUtteranceCommands so the ends of utterances are easily found.\n\t\tThis function ensures the given sequence ends with an EndUtterance command,\n\t\tEnsures that the sequence also includes an index command at the end,\n\t\tIt places the complete sequence in outSeqs,\n\t\tIt clears the given sequence list ready to build a new one,\n\t\tAnd clears the paramsToReplay list\n\t\tand refills it with any params that need to be repeated if a new sequence is going to be built.\n\t\t"""\n\t\tif seq:\n\t\t\t# There have been commands since the last split.\n\t\t\tlastOutSeq = paramsToReplay + seq\n\t\t\toutSeqs.append(lastOutSeq)\n\t\t\tparamsToReplay.clear()\n\t\t\tseq.clear()\n\t\t\t# Re-apply parameters that have been changed from their defaults.\n\t\t\tparamsToReplay.extend(paramTracker.getChanged())\n\t\telse:\n\t\t\tlastOutSeq = outSeqs[-1] if outSeqs else None\n\t\tlastCommand = lastOutSeq[-1] if lastOutSeq else None\n\t\tif lastCommand is None or isinstance(lastCommand, (EndUtteranceCommand, ConfigProfileTriggerCommand)):\n\t\t\t# It doesn\'t make sense to start with or repeat EndUtteranceCommands.\n\t\t\t# We also don\'t want an EndUtteranceCommand immediately after a ConfigProfileTriggerCommand.\n\t\t\treturn\n\t\tif not isinstance(lastCommand, IndexCommand):\n\t\t\t# Add an index so we know when we\'ve reached the end of this utterance.\n\t\t\treachedIndex = next(self._indexCounter)\n\t\t\tlastOutSeq.append(IndexCommand(reachedIndex))\n\t\toutSeqs.append([EndUtteranceCommand()])\n\n\tdef _processSpeechSequence(self, inSeq: SpeechSequence):\n\t\tparamTracker = ParamChangeTracker()\n\t\tenteredTriggers = []\n\t\toutSeqs = []\n\t\tparamsToReplay = []\n\n\t\toutSeq = []\n\t\tfor command in inSeq:\n\t\t\tif isinstance(command, BaseCallbackCommand):\n\t\t\t\t# When the synth reaches this point, we want to call the callback.\n\t\t\t\tspeechIndex = next(self._indexCounter)\n\t\t\t\toutSeq.append(IndexCommand(speechIndex))\n\t\t\t\tself._indexesToCallbacks[speechIndex] = command\n\t\t\t\t# We split at indexes so we easily know what has completed speaking.\n\t\t\t\toutSeqs.append(paramsToReplay + outSeq)\n\t\t\t\tparamsToReplay.clear()\n\t\t\t\toutSeq.clear()\n\t\t\t\tcontinue\n\t\t\tif isinstance(command, ConfigProfileTriggerCommand):\n\t\t\t\tif not command.trigger.hasProfile:\n\t\t\t\t\t# Ignore triggers that have no associated profile.\n\t\t\t\t\tcontinue\n\t\t\t\tif command.enter and command.trigger in enteredTriggers:\n\t\t\t\t\tlog.debugWarning(\n\t\t\t\t\t\t"Request to enter trigger which has already been entered: %r" % command.trigger.spec,\n\t\t\t\t\t)\n\t\t\t\t\tcontinue\n\t\t\t\tif not command.enter and command.trigger not in enteredTriggers:\n\t\t\t\t\tlog.debugWarning(\n\t\t\t\t\t\t"Request to exit trigger which wasn\'t entered: %r" % command.trigger.spec,\n\t\t\t\t\t)\n\t\t\t\t\tcontinue\n\t\t\t\tself._ensureEndUtterance(outSeq, outSeqs, paramsToReplay, paramTracker)\n\t\t\t\toutSeqs.append([command])\n\t\t\t\tif command.enter:\n\t\t\t\t\tenteredTriggers.append(command.trigger)\n\t\t\t\telse:\n\t\t\t\t\tenteredTriggers.remove(command.trigger)\n\t\t\t\tcontinue\n\t\t\tif isinstance(command, EndUtteranceCommand):\n\t\t\t\tself._ensureEndUtterance(outSeq, outSeqs, paramsToReplay, paramTracker)\n\t\t\t\tcontinue\n\t\t\tif isinstance(command, SynthParamCommand):\n\t\t\t\tif isinstance(command, LangChangeCommand) and not shouldSwitchVoice():\n\t\t\t\t\t# Language change shouldn\'t be passed to synthesizer.\n\t\t\t\t\tcontinue\n\t\t\t\tparamTracker.update(command)\n\t\t\tif isinstance(command, SuppressUnicodeNormalizationCommand):\n\t\t\t\tcontinue  # Not handled by speech manager\n\t\t\toutSeq.append(command)\n\t\t# Add the last sequence and make sure the sequence ends the utterance.\n\t\tself._ensureEndUtterance(outSeq, outSeqs, paramsToReplay, paramTracker)\n\t\t# Exit any profile triggers the caller didn\'t exit.\n\t\tfor trigger in reversed(enteredTriggers):\n\t\t\tcommand = ConfigProfileTriggerCommand(trigger, False)\n\t\t\toutSeqs.append([command])\n\t\treturn outSeqs\n\n\tdef _pushNextSpeech(self, doneSpeaking: bool):\n\t\tlog._speechManagerDebug(f"pushNextSpeech - doneSpeaking: {doneSpeaking}")\n\t\tqueue = self._getNextPriority()\n\t\tif not queue:\n\t\t\t# No more speech.\n\t\t\tlog._speechManagerDebug("No more speech")\n\t\t\tself._curPriQueue = None\n\t\t\treturn\n\t\tif self._hasNoMoreSpeech():\n\t\t\t# First utterance after no speech.\n\t\t\tself._curPriQueue = queue\n\t\telif queue.priority > self._curPriQueue.priority:\n\t\t\t# Preempted by higher priority speech.\n\t\t\tif self._curPriQueue.enteredProfileTriggers:\n\t\t\t\tif not doneSpeaking:\n\t\t\t\t\t# Wait for the synth to finish speaking.\n\t\t\t\t\t# _handleDoneSpeaking will call us again.\n\t\t\t\t\tself._shouldPushWhenDoneSpeaking = True\n\t\t\t\t\treturn\n\t\t\t\tself._exitProfileTriggers(self._curPriQueue.enteredProfileTriggers)\n\t\t\tself._curPriQueue = queue\n\t\telif queue.priority < self._curPriQueue.priority:\n\t\t\t# Resuming a preempted, lower priority queue.\n\t\t\tif queue.enteredProfileTriggers:\n\t\t\t\tif not doneSpeaking:\n\t\t\t\t\t# Wait for the synth to finish speaking.\n\t\t\t\t\t# _handleDoneSpeaking will call us again.\n\t\t\t\t\tself._shouldPushWhenDoneSpeaking = True\n\t\t\t\t\treturn\n\t\t\t\tself._restoreProfileTriggers(queue.enteredProfileTriggers)\n\t\t\tself._curPriQueue = queue\n\t\twhile queue.pendingSequences and isinstance(\n\t\t\tqueue.pendingSequences[0][0],\n\t\t\tConfigProfileTriggerCommand,\n\t\t):\n\t\t\tif not doneSpeaking:\n\t\t\t\t# Wait for the synth to finish speaking.\n\t\t\t\t# _handleDoneSpeaking will call us again.\n\t\t\t\tself._shouldPushWhenDoneSpeaking = True\n\t\t\t\treturn\n\t\t\tself._switchProfile()\n\t\tif not queue.pendingSequences:\n\t\t\t# The last commands in this queue were profile switches.\n\t\t\t# Call this method again in case other queues are waiting.\n\t\t\treturn self._pushNextSpeech(True)\n\t\tseq = self._buildNextUtterance()\n\t\tif seq:\n\t\t\t# So that we can handle any accidentally skipped indexes.\n\t\t\tfor item in seq:\n\t\t\t\tif isinstance(item, IndexCommand):\n\t\t\t\t\tself._indexesSpeaking.append(item.index)\n\t\t\tself._cancelledLastSpeechWithSynth = False\n\t\t\tlog._speechManagerUnitTest(f"Synth Gets: {seq}")\n\t\t\tpre_synthSpeak.notify(speechSequence=seq)\n\t\t\tgetSynth().speak(seq)\n\n\tdef _getNextPriority(self):\n\t\t"""Get the highest priority queue containing pending speech."""\n\t\tfor priority in SPEECH_PRIORITIES:\n\t\t\tqueue = self._priQueues.get(priority)\n\t\t\tif not queue:\n\t\t\t\tcontinue\n\t\t\tif queue.pendingSequences:\n\t\t\t\treturn queue\n\t\treturn None\n\n\tdef _buildNextUtterance(self):\n\t\t"""Since an utterance might be split over several sequences,\n\t\tbuild a complete utterance to pass to the synth.\n\t\t"""\n\t\tutterance = []\n\t\t# If this utterance was preempted by higher priority speech,\n\t\t# apply any parameters changed before the preemption.\n\t\tparams = self._curPriQueue.paramTracker.getChanged()\n\t\tutterance.extend(params)\n\t\tlastSequenceIndexAddedToUtterance = None\n\t\tfor seqIndex, seq in enumerate(self._curPriQueue.pendingSequences):\n\t\t\tif isinstance(seq[0], EndUtteranceCommand):\n\t\t\t\t# The utterance ends here.\n\t\t\t\tbreak\n\t\t\tutterance.extend(seq)\n\t\t\tlastSequenceIndexAddedToUtterance = seqIndex\n\t\t# if any items are cancelled, cancel the whole utterance.\n\t\ttry:\n\t\t\tutteranceValid = len(utterance) == 0 or self._checkForCancellations(utterance)\n\t\texcept IndexError:\n\t\t\tlog.error(\n\t\t\t\tf"Checking for cancellations failed, cancelling sequence: {utterance}",\n\t\t\t\texc_info=True,\n\t\t\t)\n\t\t\t# Avoid infinite recursion by removing the problematic sequences:\n\t\t\tdel self._curPriQueue.pendingSequences[: lastSequenceIndexAddedToUtterance + 1]\n\t\t\tutteranceValid = False\n\n\t\tif utteranceValid:\n\t\t\treturn utterance\n\t\telse:\n\t\t\treturn self._buildNextUtterance()\n\n\tdef _checkForCancellations(self, utterance: SpeechSequence) -> bool:\n\t\t"""\n\t\tChecks utterance to ensure it is not cancelled (via a _CancellableSpeechCommand).\n\t\tBecause synthesizers do not expect CancellableSpeechCommands, they are removed from the utterance.\n\t\t:arg utterance: The utterance to check for cancellations. Modified in place, CancellableSpeechCommands are\n\t\tremoved.\n\t\t:return True if sequence is still valid, else False\n\t\t"""\n\t\tif not _shouldCancelExpiredFocusEvents():\n\t\t\treturn True\n\t\tutteranceIndex = self._getUtteranceIndex(utterance)\n\t\tif utteranceIndex is None:\n\t\t\traise IndexError(\n\t\t\t\tf"no utterance index({utterance}), can\'t save cancellable commands",\n\t\t\t)\n\t\tcancellableItems = list(\n\t\t\titem for item in reversed(utterance) if isinstance(item, _CancellableSpeechCommand)\n\t\t)\n\t\tfor item in cancellableItems:\n\t\t\tutterance.remove(item)  # CancellableSpeechCommands should not be sent to the synthesizer.\n\t\t\tif item.isCancelled:\n\t\t\t\tlog._speechManagerDebug(f"item already cancelled, canceling up to: {utteranceIndex}")\n\t\t\t\tself._removeCompletedFromQueue(utteranceIndex)\n\t\t\t\treturn False\n\t\t\telse:\n\t\t\t\titem._utteranceIndex = utteranceIndex\n\t\t\t\tlog._speechManagerDebug(\n\t\t\t\t\tf"Speaking utterance with cancellable item, index: {utteranceIndex}",\n\t\t\t\t)\n\t\t\t\tself._cancelCommandsForUtteranceBeingSpokenBySynth[item] = utteranceIndex\n\t\treturn True\n\n\t_WRAPPED_INDEX_MAGNITUDE = int(MAX_INDEX / 2)\n\n\t@classmethod\n\tdef _isIndexABeforeIndexB(cls, indexA: _IndexT, indexB: _IndexT) -> bool:\n\t\t"""Was indexB created before indexB\n\t\tBecause indexes wrap after MAX_INDEX, custom logic is needed to compare relative positions.\n\t\tThe boundary for considering a wrapped value as before another value is based on the distance\n\t\tbetween the indexes. If the distance is greater than half the available index space it is no longer\n\t\tbefore.\n\t\t@return True if indexA was created before indexB, else False\n\t\t"""\n\t\tw = cls._WRAPPED_INDEX_MAGNITUDE\n\t\treturn indexA != indexB and (\n\t\t\t(indexA < indexB and w >= indexB - indexA)\n\t\t\tor (\n\t\t\t\t# Test for wrapped values\n\t\t\t\tindexB < indexA\n\t\t\t\t# Avoid dealing with wrapping logic, check distance in the other direction.\n\t\t\t\tand w < indexA - indexB\n\t\t\t)\n\t\t)\n\n\t@classmethod\n\tdef _isIndexAAfterIndexB(cls, indexA: _IndexT, indexB: _IndexT) -> bool:\n\t\treturn indexA != indexB and not cls._isIndexABeforeIndexB(indexA, indexB)\n\n\tdef _getMostRecentlyCancelledUtterance(self) -> Optional[_IndexT]:\n\t\t# Index of the most recently cancelled utterance.\n\t\tlatestCancelledUtteranceIndex: Optional[_IndexT] = None\n\t\tlog._speechManagerDebug(\n\t\t\tf"Length of _cancelCommandsForUtteranceBeingSpokenBySynth: "\n\t\t\tf"{len(self._cancelCommandsForUtteranceBeingSpokenBySynth)} "\n\t\t\tf"Length of _indexesSpeaking: "\n\t\t\tf"{len(self._indexesSpeaking)} ",\n\t\t)\n\t\tcancelledIndexes = (\n\t\t\tindex\n\t\t\tfor command, index in self._cancelCommandsForUtteranceBeingSpokenBySynth.items()\n\t\t\tif command.isCancelled\n\t\t)\n\t\tfor index in cancelledIndexes:\n\t\t\tif latestCancelledUtteranceIndex is None or self._isIndexABeforeIndexB(\n\t\t\t\tlatestCancelledUtteranceIndex,\n\t\t\t\tindex,\n\t\t\t):\n\t\t\t\tlatestCancelledUtteranceIndex = index\n\t\treturn latestCancelledUtteranceIndex\n\n\tdef removeCancelledSpeechCommands(self):\n\t\tlog._speechManagerUnitTest("removeCancelledSpeechCommands")\n\t\tself._doRemoveCancelledSpeechCommands()\n\n\tdef _doRemoveCancelledSpeechCommands(self):\n\t\tif not _shouldCancelExpiredFocusEvents():\n\t\t\treturn\n\t\t# Don\'t delete commands while iterating over _cancelCommandsForUtteranceBeingSpokenBySynth.\n\t\tlatestCancelledUtteranceIndex = self._getMostRecentlyCancelledUtterance()\n\t\tlog._speechManagerDebug(f"Last index: {latestCancelledUtteranceIndex}")\n\t\tif latestCancelledUtteranceIndex is not None:\n\t\t\tlog._speechManagerDebug("Cancel and push speech")\n\t\t\t# Minimise the number of calls to _removeCompletedFromQueue by using the most recently cancelled\n\t\t\t# utterance index. This will remove all older queued speech also.\n\t\t\tself._removeCompletedFromQueue(latestCancelledUtteranceIndex)\n\t\t\tgetSynth().cancel()\n\t\t\tself._cancelledLastSpeechWithSynth = True\n\t\t\tself._cancelCommandsForUtteranceBeingSpokenBySynth.clear()\n\t\t\tself._indexesSpeaking.clear()\n\t\t\tself._pushNextSpeech(True)\n\n\tdef _getUtteranceIndex(self, utterance: SpeechSequence):\n\t\t#  find the index command, should be the last in sequence\n\t\tindexItem: IndexCommand = cast(IndexCommand, utterance[-1])\n\t\tif not isinstance(indexItem, IndexCommand):\n\t\t\tlog.error("Expected last item to be an indexCommand.")\n\t\t\treturn None\n\t\treturn indexItem.index\n\n\tdef _onSynthIndexReached(self, synth=None, index=None):\n\t\tlog._speechManagerUnitTest(f"synthReachedIndex: {index}, synth: {synth}")\n\t\tif synth != getSynth():\n\t\t\treturn\n\t\t# This needs to be handled in the main thread.\n\t\tqueueHandler.queueFunction(queueHandler.eventQueue, self._handleIndex, index)\n\n\t# C901 \'SpeechManager._removeCompletedFromQueue\' is too complex\n\t# SpeechManager needs unit tests and a breakdown of responsibilities.\n\tdef _removeCompletedFromQueue(self, index: int) -> Tuple[bool, bool]:  # noqa: C901\n\t\t"""Removes completed speech sequences from the queue.\n\t\t@param index: The index just reached indicating a completed sequence.\n\t\t@return: Tuple of (valid, endOfUtterance),\n\t\t\twhere valid indicates whether the index was valid and\n\t\t\tendOfUtterance indicates whether this sequence was the end of the current utterance.\n\t\t@rtype: (bool, bool)\n\t\t"""\n\t\t# Find the sequence that just completed speaking.\n\t\tif not self._curPriQueue:\n\t\t\t# No speech in progress. Probably from a previous utterance which was cancelled.\n\t\t\treturn False, False\n\t\tfor seqIndex, seq in enumerate(self._curPriQueue.pendingSequences):\n\t\t\tlastCommand = seq[-1] if isinstance(seq, list) else None\n\t\t\tif isinstance(lastCommand, IndexCommand):\n\t\t\t\tif self._isIndexAAfterIndexB(index, lastCommand.index):\n\t\t\t\t\tlog.debugWarning(\n\t\t\t\t\t\tf"Reached speech index {index:d}, but index {lastCommand.index:d} never handled",\n\t\t\t\t\t)\n\t\t\t\telif index == lastCommand.index:\n\t\t\t\t\tendOfUtterance = isinstance(\n\t\t\t\t\t\tself._curPriQueue.pendingSequences[seqIndex + 1][0],\n\t\t\t\t\t\tEndUtteranceCommand,\n\t\t\t\t\t)\n\t\t\t\t\tif endOfUtterance:\n\t\t\t\t\t\t# Remove the EndUtteranceCommand as well.\n\t\t\t\t\t\tseqIndex += 1\n\t\t\t\t\tbreak  # Found it!\n\t\telse:\n\t\t\tlog._speechManagerDebug(\n\t\t\t\t"Unknown index. Probably from a previous utterance which was cancelled.",\n\t\t\t)\n\t\t\treturn False, False\n\t\tif endOfUtterance:\n\t\t\t# These params may not apply to the next utterance if it was queued separately,\n\t\t\t# so reset the tracker.\n\t\t\t# The next utterance will include the commands again if they do still apply.\n\t\t\tself._curPriQueue.paramTracker = ParamChangeTracker()\n\t\telse:\n\t\t\t# Keep track of parameters changed so far.\n\t\t\t# This is necessary in case this utterance is preempted by higher priority speech.\n\t\t\tfor seqIndex in range(seqIndex + 1):\n\t\t\t\tseq = self._curPriQueue.pendingSequences[seqIndex]\n\t\t\t\tfor command in seq:\n\t\t\t\t\tif isinstance(command, SynthParamCommand):\n\t\t\t\t\t\tself._curPriQueue.paramTracker.update(command)\n\t\t# This sequence is done, so we don\'t need to track it any more.\n\t\ttoRemove = self._curPriQueue.pendingSequences[: seqIndex + 1]\n\t\tlog._speechManagerDebug("Removing: %r", seq)\n\t\tif _shouldCancelExpiredFocusEvents():\n\t\t\tcancellables = (\n\t\t\t\titem\n\t\t\t\tfor seq in toRemove\n\t\t\t\tfor item in seq\n\t\t\t\tif isinstance(\n\t\t\t\t\titem,\n\t\t\t\t\t_CancellableSpeechCommand,\n\t\t\t\t)\n\t\t\t)\n\t\t\tfor item in cancellables:\n\t\t\t\tif log.isEnabledFor(log.DEBUG) and _shouldDoSpeechManagerLogging():\n\t\t\t\t\t# Debug logging for cancelling expired focus events.\n\t\t\t\t\tlog._speechManagerDebug(\n\t\t\t\t\t\tf"Item is in _cancelCommandsForUtteranceBeingSpokenBySynth: "\n\t\t\t\t\t\tf"{item in self._cancelCommandsForUtteranceBeingSpokenBySynth.keys()}",\n\t\t\t\t\t)\n\t\t\t\tself._cancelCommandsForUtteranceBeingSpokenBySynth.pop(item, None)\n\t\tdel self._curPriQueue.pendingSequences[: seqIndex + 1]\n\n\t\treturn True, endOfUtterance\n\n\tdef _handleIndex(self, index: int):\n\t\tlog._speechManagerDebug(f"Handle index: {index}")\n\t\t# A synth (such as OneCore) may skip indexes\n\t\t# If before another index, with no text content in between.\n\t\t# Therefore, detect this and ensure we handle all skipped indexes.\n\t\thandleIndexes = []\n\t\tfor oldIndex in list(self._indexesSpeaking):\n\t\t\tif self._isIndexABeforeIndexB(oldIndex, index):\n\t\t\t\tlog.debugWarning("Handling skipped index %s" % oldIndex)\n\t\t\t\thandleIndexes.append(oldIndex)\n\t\thandleIndexes.append(index)\n\t\tvalid, endOfUtterance = False, False\n\t\tfor i in handleIndexes:\n\t\t\ttry:\n\t\t\t\tself._indexesSpeaking.remove(i)\n\t\t\texcept ValueError:\n\t\t\t\tlog.debug("Unknown index %s, speech probably cancelled from main thread." % i)\n\t\t\t\tbreak  # try the rest, this is a very unexpected path.\n\t\t\tif i != index:\n\t\t\t\tlog.debugWarning("Handling skipped index %s" % i)\n\t\t\t# we must do the following for each index, any/all of them may be end of utterance, which must\n\t\t\t# trigger _pushNextSpeech\n\t\t\t_valid, _endOfUtterance = self._removeCompletedFromQueue(i)\n\t\t\tvalid = valid or _valid\n\t\t\tendOfUtterance = endOfUtterance or _endOfUtterance\n\t\t\tif _valid:\n\t\t\t\tcallbackCommand = self._indexesToCallbacks.pop(i, None)\n\t\t\t\tif callbackCommand:\n\t\t\t\t\ttry:\n\t\t\t\t\t\tlog._speechManagerUnitTest(f"CallbackCommand Start: {callbackCommand!r}")\n\t\t\t\t\t\tcallbackCommand.run()\n\t\t\t\t\t\tlog._speechManagerUnitTest("CallbackCommand End")\n\t\t\t\t\texcept Exception:\n\t\t\t\t\t\tlog.exception("Error running speech callback")\n\t\tself._doRemoveCancelledSpeechCommands()\n\t\tshouldPush = (\n\t\t\tendOfUtterance and not self._synthStillSpeaking()  # stops double speaking errors\n\t\t)\n\t\tif shouldPush:\n\t\t\tif self._indexesSpeaking:\n\t\t\t\tlog._speechManagerDebug(\n\t\t\t\t\tf"Indexes speaking: {self._indexesSpeaking!r},"\n\t\t\t\t\tf" queue: {self._curPriQueue.pendingSequences}",\n\t\t\t\t)\n\t\t\t# Even if we have many indexes, we should only push next speech once.\n\t\t\tself._pushNextSpeech(False)\n\n\tdef _onSynthDoneSpeaking(self, synth: Optional[synthDriverHandler.SynthDriver] = None):\n\t\tlog._speechManagerUnitTest(f"synthDoneSpeaking synth:{synth}")\n\t\tif synth != getSynth():\n\t\t\treturn\n\t\t# This needs to be handled in the main thread.\n\t\tqueueHandler.queueFunction(queueHandler.eventQueue, self._handleDoneSpeaking)\n\n\tdef _handleDoneSpeaking(self):\n\t\tlog._speechManagerDebug(\n\t\t\tf"Synth done speaking, should push: {self._shouldPushWhenDoneSpeaking}",\n\t\t)\n\t\tif self._shouldPushWhenDoneSpeaking:\n\t\t\tself._shouldPushWhenDoneSpeaking = False\n\t\t\tself._pushNextSpeech(True)\n\n\tdef _switchProfile(self):\n\t\tcommand = self._curPriQueue.pendingSequences.pop(0)[0]\n\t\tassert isinstance(\n\t\t\tcommand,\n\t\t\tConfigProfileTriggerCommand,\n\t\t), "First pending command should be a ConfigProfileTriggerCommand"\n\t\tif command.enter:\n\t\t\ttry:\n\t\t\t\tcommand.trigger.enter()\n\t\t\texcept:  # noqa: E722\n\t\t\t\tlog.exception("Error entering new trigger %r" % command.trigger.spec)\n\t\t\tself._curPriQueue.enteredProfileTriggers.append(command.trigger)\n\t\telse:\n\t\t\ttry:\n\t\t\t\tcommand.trigger.exit()\n\t\t\texcept:  # noqa: E722\n\t\t\t\tlog.exception("Error exiting active trigger %r" % command.trigger.spec)\n\t\t\tself._curPriQueue.enteredProfileTriggers.remove(command.trigger)\n\t\tsynthDriverHandler.handlePostConfigProfileSwitch(resetSpeechIfNeeded=False)\n\n\tdef _exitProfileTriggers(self, triggers):\n\t\tfor trigger in reversed(triggers):\n\t\t\ttry:\n\t\t\t\ttrigger.exit()\n\t\t\texcept:  # noqa: E722\n\t\t\t\tlog.exception("Error exiting profile trigger %r" % trigger.spec)\n\t\tsynthDriverHandler.handlePostConfigProfileSwitch(resetSpeechIfNeeded=False)\n\n\tdef _restoreProfileTriggers(self, triggers):\n\t\tfor trigger in triggers:\n\t\t\ttry:\n\t\t\t\ttrigger.enter()\n\t\t\texcept:  # noqa: E722\n\t\t\t\tlog.exception("Error entering profile trigger %r" % trigger.spec)\n\t\tsynthDriverHandler.handlePostConfigProfileSwitch(resetSpeechIfNeeded=False)\n\n\tdef cancel(self):\n\t\tlog._speechManagerUnitTest("Cancel")\n\t\tgetSynth().cancel()\n\t\tif self._curPriQueue and self._curPriQueue.enteredProfileTriggers:\n\t\t\tself._exitProfileTriggers(self._curPriQueue.enteredProfileTriggers)\n\t\tself._reset()'

NVDA_EXTENSIONS = 'speechCanceled = Action()\n\n\npre_speechCanceled = Action()\n\n\npre_speechQueued = Action()'

NVDA_SYNTH_EXTENSIONS = 'synthIndexReached = extensionPoints.Action()\n\n\nsynthDoneSpeaking = extensionPoints.Action()\n\n\npre_synthSpeak = extensionPoints.Action()'

NVDA_CANCEL_SPEECH = 'def cancelSpeech():\n\t"""Interupts the synthesizer from currently speaking"""\n\t# Import only for this function to avoid circular import.\n\tfrom .sayAll import SayAllHandler\n\n\tSayAllHandler.stop()\n\tpre_speechCanceled.notify()\n\tif _speechState.beenCanceled:\n\t\treturn\n\telif _speechState.speechMode == SpeechMode.off:\n\t\treturn\n\telif _speechState.speechMode == SpeechMode.beeps:\n\t\treturn\n\t_manager.cancel()\n\tspeechCanceled.notify()\n\t_speechState.beenCanceled = True\n\t_speechState.isPaused = False'

NVDA_FOCUS_EVENTS = 'WAS_GAIN_FOCUS_OBJ_ATTR_NAME = "wasGainFocusObj"\n\n\nclass FocusLossCancellableSpeechCommand(_CancellableSpeechCommand):\n\tdef __init__(self, obj, reportDevInfo: bool):\n\t\tfrom NVDAObjects import NVDAObject\n\n\t\tif not isinstance(obj, NVDAObject):\n\t\t\tlog.warning("Unhandled object type. Expected all objects to be descendant from NVDAObject")\n\t\t\traise TypeError(f"Unhandled object type: {obj!r}")\n\t\tself._obj = obj\n\t\tsuper(FocusLossCancellableSpeechCommand, self).__init__(reportDevInfo=reportDevInfo)\n\n\t\tif self.isLastFocusObj():\n\t\t\t# Objects may be re-used.\n\t\t\t# WAS_GAIN_FOCUS_OBJ_ATTR_NAME state should be cleared at some point?\n\t\t\t# perhaps instead keep a weak ref list of obj that had focus, clear on keypress?\n\n\t\t\t# Assumption: we only process one focus event at a time, so even if several focus events are queued,\n\t\t\t# all focused objects will still gain this tracking attribute. Otherwise, this may need to be set via\n\t\t\t# api.setFocusObject when api.getFocusObject is set.\n\t\t\tsetattr(obj, WAS_GAIN_FOCUS_OBJ_ATTR_NAME, True)\n\t\telif not hasattr(obj, WAS_GAIN_FOCUS_OBJ_ATTR_NAME):\n\t\t\tsetattr(obj, WAS_GAIN_FOCUS_OBJ_ATTR_NAME, False)\n\n\tdef _checkIfValid(self) -> bool:\n\t\tstillValid = (\n\t\t\tself.isLastFocusObj()\n\t\t\tor not self.previouslyHadFocus()\n\t\t\tor self.isAncestorOfCurrentFocus()\n\t\t\t# Ensure titles for dialogs gaining focus are reported, EG NVDA Find dialog\n\t\t\tor self.isForegroundObject()\n\t\t\t# Ensure menu items are reported when focus is gained to the menu start (see #12624).\n\t\t\tor self.isMenuItemOfCurrentFocus()\n\t\t)\n\t\treturn stillValid\n\n\tdef _getDevInfo(self) -> str:\n\t\treturn (\n\t\t\tf"isLast: {self.isLastFocusObj()}"\n\t\t\tf", previouslyHad: {self.previouslyHadFocus()}"\n\t\t\tf", isAncestorOfCurrentFocus: {self.isAncestorOfCurrentFocus()}"\n\t\t\tf", is foreground obj {self.isForegroundObject()}"\n\t\t\tf", isMenuItemOfCurrentFocus: {self.isMenuItemOfCurrentFocus()}"\n\t\t)\n\n\tdef isLastFocusObj(self):\n\t\t# Use \'==\' rather than \'is\' because obj may have been created multiple times\n\t\t# pointing to the same underlying object.\n\t\treturn self._obj == api.getFocusObject()\n\n\tdef previouslyHadFocus(self):\n\t\treturn getattr(self._obj, WAS_GAIN_FOCUS_OBJ_ATTR_NAME, False)\n\n\tdef isAncestorOfCurrentFocus(self):\n\t\treturn self._obj in api.getFocusAncestors()\n\n\tdef isForegroundObject(self):\n\t\tforeground = api.getForegroundObject()\n\t\treturn self._obj is foreground or self._obj == foreground\n\n\tdef isMenuItemOfCurrentFocus(self) -> bool:\n\t\t"""\n\t\tChecks if the current object is a menu item of the current focus.\n\t\tThe only known case where this returns True is the following (see #12624, #14550):\n\n\t\tWhen opening a submenu in certain applications (like Thunderbird 78.12),\n\t\tNVDA can process a menu start event after the first item in the menu is focused.\n\t\tThe menu start event causes a focus event on the menu, taking NVDA\'s focus from the menu item.\n\t\tAdditionally, the "menu" parent of the submenu item is not keyboard focusable, and is separate from\n\t\tthe menu item which triggered the submenu.\n\t\tThe object tree in this case (menu item > submenu (not keyboard focusable) > submenu item).\n\t\tThe focus event order after activating the menu item\'s sub menu is (submenu item, submenu).\n\t\t"""\n\t\tfrom NVDAObjects import IAccessible\n\n\t\tlastFocus = api.getFocusObject()\n\n\t\t# This case can only occur when:\n\t\t# 1. the old and new focus targets are instances of IAccessible; and\n\t\t# 2. the old focus is a menuitem, menuitemradio or menuitemcheckbox; and\n\t\t# 3. the new focus is a menu; and\n\t\t# 4. the old focus has a parent.\n\t\tif not (\n\t\t\tisinstance(self._obj, IAccessible.IAccessible)\n\t\t\tand isinstance(lastFocus, IAccessible.IAccessible)\n\t\t\tand self._obj.IAccessibleRole\n\t\t\tin (\n\t\t\t\toleacc.ROLE_SYSTEM_MENUITEM,\n\t\t\t\tIA2.IA2_ROLE_CHECK_MENU_ITEM,\n\t\t\t\tIA2.IA2_ROLE_RADIO_MENU_ITEM,\n\t\t\t)\n\t\t\tand lastFocus.IAccessibleRole == oleacc.ROLE_SYSTEM_MENUPOPUP\n\t\t\tand self._obj.parent\n\t\t):\n\t\t\treturn False\n\n\t\t# Check that the old focus is a descendant of the new focus.\n\t\tancestor = self._obj.parent\n\t\twhile ancestor is not None:\n\t\t\tif ancestor == lastFocus:\n\t\t\t\tlog.debugWarning(\n\t\t\t\t\t"This ancestor menu was not announced properly, and should have been focused before the submenu item.\\n"\n\t\t\t\t\tf"Object info: {self._obj.devInfo}\\n"\n\t\t\t\t\tf"Ancestor info: {ancestor.devInfo}",\n\t\t\t\t)\n\t\t\t\treturn True\n\n\t\t\tancestor = ancestor.parent\n\n\t\treturn False\n\n\ndef _getFocusLossCancellableSpeechCommand(\n\tobj,\n\treason: controlTypes.OutputReason,\n) -> Optional[_CancellableSpeechCommand]:\n\tif reason != controlTypes.OutputReason.FOCUS or not speech.manager._shouldCancelExpiredFocusEvents():\n\t\treturn None\n\tfrom NVDAObjects import NVDAObject\n\n\tif not isinstance(obj, NVDAObject):\n\t\tlog.warning("Unhandled object type. Expected all objects to be descendant from NVDAObject")\n\t\treturn None\n\n\tshouldReportDevInfo = speech.manager._shouldDoSpeechManagerLogging()\n\treturn FocusLossCancellableSpeechCommand(obj, reportDevInfo=shouldReportDevInfo)\n\n\ndef doPreGainFocus(obj: "NVDAObjects.NVDAObject", sleepMode: bool = False) -> bool:\n\tif objectBelowLockScreenAndWindowsIsLocked(\n\t\tobj,\n\t\tshouldLog=config.conf["debugLog"]["events"],\n\t):\n\t\treturn False\n\toldFocus = api.getFocusObject()\n\toldTreeInterceptor = oldFocus.treeInterceptor if oldFocus else None\n\tif not api.setFocusObject(obj):\n\t\treturn False\n\tif speech.manager._shouldCancelExpiredFocusEvents():\n\t\tlog._speechManagerDebug("executeEvent: Removing cancelled speech commands.")\n\t\t# ask speechManager to check if any of it\'s queued utterances should be cancelled\n\t\t# Note: Removing cancelled speech commands should happen after all dependencies for the isValid check\n\t\t# have been updated:\n\t\t# - obj.WAS_GAIN_FOCUS_OBJ_ATTR_NAME\n\t\t# - api.setFocusObject()\n\t\t# - api.getFocusAncestors()\n\t\t# When these are updated:\n\t\t# - obj.WAS_GAIN_FOCUS_OBJ_ATTR_NAME\n\t\t#   - Set during creation of the _CancellableSpeechCommand.\n\t\t# - api.getFocusAncestors() via api.setFocusObject() called in doPreGainFocus\n\t\tspeech._manager.removeCancelledSpeechCommands()\n\n\tif api.getFocusDifferenceLevel() <= 1:\n\t\tnewForeground = api.getDesktopObject().objectInForeground()\n\t\tif not newForeground:\n\t\t\tlog.debugWarning("Can not get real foreground, resorting to focus ancestors")\n\t\t\tancestors = api.getFocusAncestors()\n\t\t\tif len(ancestors) > 1:\n\t\t\t\tnewForeground = ancestors[1]\n\t\t\telse:\n\t\t\t\tnewForeground = obj\n\t\tif not api.setForegroundObject(newForeground):\n\t\t\treturn False\n\t\texecuteEvent("foreground", newForeground)\n\thandlePossibleDesktopNameChange()\n\tif sleepMode:\n\t\treturn True\n\t# Fire focus entered events for all new ancestors of the focus if this is a gainFocus event\n\tfor parent in api.getFocusAncestors()[api.getFocusDifferenceLevel() :]:\n\t\texecuteEvent("focusEntered", parent)\n\tif obj.treeInterceptor is not oldTreeInterceptor:\n\t\tif hasattr(oldTreeInterceptor, "event_treeInterceptor_loseFocus"):\n\t\t\toldTreeInterceptor.event_treeInterceptor_loseFocus()\n\t\tif (\n\t\t\tobj.treeInterceptor\n\t\t\tand obj.treeInterceptor.isReady\n\t\t\tand hasattr(obj.treeInterceptor, "event_treeInterceptor_gainFocus")\n\t\t):\n\t\t\tobj.treeInterceptor.event_treeInterceptor_gainFocus()\n\treturn True'

NVDA_API_FOCUS = 'def getForegroundObject() -> NVDAObjects.NVDAObject:\n\t"""Gets the current foreground object.\n\tThis (cached) object is the (effective) top-level "window" (hwnd).\n\tEG a Dialog rather than the focused control within the dialog.\n\tThe cache is updated as queued events are processed, as such there will be a delay between the winEvent\n\tand this function matching. However, within NVDA this should be used in order to be in sync with other\n\tfunctions such as "getFocusAncestors".\n\t@returns: the current foreground object\n\t"""\n\treturn globalVars.foregroundObject\n\n\ndef setForegroundObject(obj: NVDAObjects.NVDAObject) -> bool:\n\t"""Stores the given object as the current foreground object.\n\tNote: does not cause the operating system to change the foreground window,\n\t\tbut simply allows NVDA to keep track of what the foreground window is.\n\t\tAlternative names for this function may have been:\n\t\t- setLastForegroundWindow\n\t\t- setLastForegroundEventObject\n\t@param obj: the object that will be stored as the current foreground object\n\t"""\n\tif not isinstance(obj, NVDAObjects.NVDAObject):\n\t\tlog.error("Object is not a valid NVDAObject")\n\t\treturn False\n\tif objectBelowLockScreenAndWindowsIsLocked(obj):\n\t\treturn False\n\tglobalVars.foregroundObject = obj\n\treturn True\n\n\ndef setFocusObject(obj: NVDAObjects.NVDAObject) -> bool:  # noqa: C901\n\t"""Stores an object as the current focus object.\n\tNote: this does not physically change the window with focus in the operating system,\n\tbut allows NVDA to keep track of the correct object.\n\tBefore overriding the last object,\n\tthis function calls event_loseFocus on the object to notify it that it is losing focus.\n\t@param obj: the object that will be stored as the focus object\n\t"""\n\tif not isinstance(obj, NVDAObjects.NVDAObject):\n\t\tlog.error("Object is not a valid NVDAObject")\n\t\treturn False\n\tif objectBelowLockScreenAndWindowsIsLocked(obj):\n\t\treturn False\n\tif globalVars.focusObject:\n\t\teventHandler.executeEvent("loseFocus", globalVars.focusObject)\n\t\toldTreeInterceptor = globalVars.focusObject.treeInterceptor\n\telse:\n\t\toldTreeInterceptor = None\n\toldFocusLine = globalVars.focusAncestors\n\t# add the old focus to the old focus ancestors, but only if its not None (is none at NVDA initialization)\n\tif globalVars.focusObject:\n\t\toldFocusLine.append(globalVars.focusObject)\n\toldAppModules = [o.appModule for o in oldFocusLine if o and o.appModule]\n\tappModuleHandler.cleanup()\n\tancestors = []\n\ttempObj = obj\n\tmatchedOld = False\n\tfocusDifferenceLevel = 0\n\toldFocusLineLength = len(oldFocusLine)\n\t# Starting from the focus, move up the ancestor chain.\n\tsafetyCount = 0\n\twhile tempObj:\n\t\tif safetyCount < 100:\n\t\t\tsafetyCount += 1\n\t\telse:\n\t\t\ttry:\n\t\t\t\tlog.error(\n\t\t\t\t\t"Never ending focus ancestry:"\n\t\t\t\t\tf" last object: {tempObj.name}, {controlTypes.Role(tempObj.role).displayString},"\n\t\t\t\t\tf" window class {tempObj.windowClassName if isinstance(tempObj, Window) else type(tempObj)}, "\n\t\t\t\t\tf"application name {tempObj.appModule.appName}",\n\t\t\t\t)\n\t\t\texcept:  # noqa: E722\n\t\t\t\tpass\n\t\t\ttempObj = getDesktopObject()\n\t\t# Scan backwards through the old ancestors looking for a match.\n\t\tfor index in range(oldFocusLineLength - 1, -1, -1):\n\t\t\twatchdog.alive()\n\t\t\tif tempObj == oldFocusLine[index]:\n\t\t\t\t# Match! The old and new focus ancestors converge at this point.\n\t\t\t\t# Copy the old ancestors up to and including this object.\n\t\t\t\torigAncestors = oldFocusLine[0 : index + 1]\n\t\t\t\t# make sure to cache the last old ancestor as a parent on the first new ancestor so as not to leave a broken parent cache\n\t\t\t\tif ancestors and origAncestors:\n\t\t\t\t\tancestors[0].container = origAncestors[-1]\n\t\t\t\torigAncestors.extend(ancestors)\n\t\t\t\tancestors = origAncestors\n\t\t\t\tfocusDifferenceLevel = index + 1\n\t\t\t\t# We don\'t need to process any more in either this loop or the outer loop; we have all of the ancestors.\n\t\t\t\tmatchedOld = True\n\t\t\t\tbreak\n\t\tif matchedOld:\n\t\t\tbreak\n\t\t# We\'re moving backwards along the ancestor chain, so add this to the start of the list.\n\t\tancestors.insert(0, tempObj)\n\t\tcontainer = tempObj.container\n\t\ttempObj.container = container  # Cache the parent.\n\t\ttempObj = container\n\t# Remove the final new ancestor as this will be the new focus object\n\tdel ancestors[-1]\n\t# #5467: Ensure that the appModule of the real focus is included in the newAppModule list for profile switching\n\t# Rather than an original focus ancestor which happened to match the new focus.\n\tnewAppModules = [o.appModule for o in ancestors if o and o.appModule]\n\tif obj.appModule:\n\t\tnewAppModules.append(obj.appModule)\n\ttry:\n\t\ttreeInterceptorHandler.cleanup()\n\texcept exceptions.CallCancelled:\n\t\tpass\n\ttreeInterceptorObject = None\n\to = None\n\twatchdog.alive()\n\tfor o in ancestors[focusDifferenceLevel:] + [obj]:\n\t\ttry:\n\t\t\ttreeInterceptorObject = treeInterceptorHandler.update(o)\n\t\texcept:  # noqa: E722\n\t\t\tlog.error("Error updating tree interceptor", exc_info=True)\n\t# Always make sure that the focus object\'s treeInterceptor is forced to either the found treeInterceptor (if its in it) or to None\n\t# This is to make sure that the treeInterceptor does not have to be looked up, which can cause problems for winInputHook\n\tif obj is o or obj in treeInterceptorObject:\n\t\tobj.treeInterceptor = treeInterceptorObject\n\telse:\n\t\tobj.treeInterceptor = None\n\tif oldTreeInterceptor is not obj.treeInterceptor:\n\t\tif obj.treeInterceptor:\n\t\t\t# obj.treeInterceptor has been assigned to treeInterceptorObject.\n\t\t\tbrowseMode = not treeInterceptorObject.passThrough\n\t\telse:\n\t\t\tbrowseMode = False\n\t\ttreeInterceptorHandler.post_browseModeStateChange.notify(browseMode=browseMode)\n\t# #3804: handleAppSwitch should be called as late as possible,\n\t# as triggers must not be out of sync with global focus variables.\n\t# setFocusObject shouldn\'t fail earlier anyway, but it\'s best to be safe.\n\tappModuleHandler.handleAppSwitch(oldAppModules, newAppModules)\n\t# Set global focus variables.\n\tglobalVars.focusDifferenceLevel = focusDifferenceLevel\n\tglobalVars.focusObject = obj\n\tglobalVars.focusAncestors = ancestors\n\tbraille.invalidateCachedFocusAncestors(focusDifferenceLevel)\n\tif config.conf["reviewCursor"]["followFocus"]:\n\t\tsetNavigatorObject(obj, isFocus=True)\n\t# Fire focusExited event for all old focus ancestors not common with the new focus\n\tfor oldFocusAncestor in reversed(oldFocusLine[focusDifferenceLevel:-1]):\n\t\teventHandler.executeEvent("focusExited", oldFocusAncestor)\n\treturn True\n\n\ndef getFocusDifferenceLevel():\n\treturn globalVars.focusDifferenceLevel\n\n\ndef getFocusAncestors():\n\t"""An array of NVDAObjects that are all parents of the object which currently has focus"""\n\treturn globalVars.focusAncestors\n\n\ndef getFocusObject() -> NVDAObjects.NVDAObject:\n\t"""\n\tGets the current object with focus.\n\t@returns: the object with focus\n\t"""\n\treturn globalVars.focusObject\n\n\ndef getDesktopObject() -> NVDAObjects.NVDAObject:\n\t"""Get the desktop object"""\n\treturn globalVars.desktopObject'

NVDA_EVENT_FOREGROUND = 'def event_foreground(self):\n\t"""Called when the foreground window changes.\n\tThis method should only perform tasks specific to the foreground window changing.\n\tL{event_focusEntered} or L{event_gainFocus} will be called for this object, so this method should not speak/braille the object, etc.\n\t"""\n\tspeech.cancelSpeech()\n\tvision.handler.handleForeground(self)'

NVDA_CODE_FILES = {'NVDA_COMMANDS': 'speech/commands.py', 'NVDA_PRIORITIES': 'speech/priorities.py', 'NVDA_MANAGER': 'speech/manager.py', 'NVDA_EXTENSIONS': 'speech/extensions.py', 'NVDA_SYNTH_EXTENSIONS': 'synthDriverHandler.py', 'NVDA_CANCEL_SPEECH': 'speech/speech.py', 'NVDA_FOCUS_EVENTS': 'eventHandler.py', 'NVDA_API_FOCUS': 'api.py', 'NVDA_EVENT_FOREGROUND': 'NVDAObjects/__init__.py'}

# -- the tester's windows and pages -------------------------------------------------------------------------------

GITHUB_TITLE = "issue with how NVDA reads certain things on Reddit · Issue #30 · joshknnd1982/jawsMigrator"
REDDIT_TITLE = "I've had data issues for the past 3 days since I switched from total wireless to visible. I need help : r/Visible"
#: Edge's window, named after the tab it shows.
GITHUB_WINDOW = f"{GITHUB_TITLE} and 2 more pages - Profile 1 - Microsoft​ Edge"
REDDIT_WINDOW = f"{REDDIT_TITLE} and 2 more pages - Profile 1 - Microsoft​ Edge"
COMMENT_BOX = ["Add a comment", "edit", "Markdown input: edit mode selected.", "W"]

#: NVDA's "Speaking" lines in the tester's log as the focus came back to the GitHub comment box (16:20:10 and 16:20:31),
#: with the assistant 1.31, which already left "window" out.
TESTERS_LOG = [[REDDIT_WINDOW], [GITHUB_TITLE, "document"], ["main landmark"], ["new Comment", "grouping"], COMMENT_BOX]
#: What JAWS said as the tester switched to the reddit tab: its title only (its Alt+Tab list and tutor messages aside).
JAWS_REDDIT = [[REDDIT_TITLE], [REDDIT_TITLE]]
#: And switching to the GitHub tab, where its focus was on the button next to the comment box.
JAWS_GITHUB = [[GITHUB_WINDOW], [GITHUB_TITLE], ["MainRegion"], ["new Comment", "group"], ["Paste, drop, or click to add files", "Button"]]

EDGE = types.SimpleNamespace(appName="msedge")
OUTLOOK = types.SimpleNamespace(appName="outlook")
CHUNK_SEPARATOR = "  "


class CallCancelled(Exception):
	"""NVDA's exceptions.CallCancelled."""


class Log:
	"""NVDA's logHandler.log, as far as its speech manager and focus code use it; nothing is logged."""

	DEBUG = logging.DEBUG

	def isEnabledFor(self, level):
		return False

	def _log(self, *args, **kwargs):
		pass

	debug = debugWarning = error = warning = info = exception = _log


#: NVDAObjects as NVDA's api and eventHandler import it: its NVDAObject, and no IAccessible menu items here.
NVDA_OBJECTS = types.ModuleType("NVDAObjects")
NVDA_OBJECTS.NVDAObject = v126.NVDAObject
NVDA_OBJECTS.IAccessible = types.SimpleNamespace(IAccessible=type("IAccessible", (), {}))
#: What NVDAObject.event_foreground finds as NVDA's speech: each test's own cancelSpeech.
objectSpeech = types.SimpleNamespace(cancelSpeech=None)
#: An object of Edge's (and of Outlook's), as NVDA gets it through IAccessible2, with NVDA's own event_foreground.
TabObject = v125.nvdaMethods(
	"TabObject",
	[v126.WebObject],
	[NVDA_EVENT_FOREGROUND],
	{"speech": objectSpeech, "vision": types.SimpleNamespace(handler=types.SimpleNamespace(handleForeground=lambda obj: None))},
)


class Page:
	"""The browse mode document NVDA made for a page (its tree interceptor), as far as NVDA's focus code and the
	assistant ask it: not ready for a first focus of its own here, so NVDA's plain focus events say the page."""

	def __init__(self, passThrough):
		self.rootNVDAObject = None
		self.passThrough = passThrough
		self.isReady = False


def screenObject(uniqueID, role, name="", parent=None, page=None, appModule=EDGE, windowClassName="Chrome_RenderWidgetHostHWND", **kwargs):
	obj = TabObject(uniqueID, role, name=name, **kwargs)
	obj.appModule = appModule
	obj.windowClassName = windowClassName
	obj.UIAElement = None
	obj.container = parent
	if page is not None:
		# What NVDA's treeInterceptorHandler.update finds for it.
		obj.inPage = page
	if role == Role.DOCUMENT:
		# Through IAccessible2 a page has no value (ia2Web.Document.value is None).
		obj.value = None
		if page is not None and page.rootNVDAObject is None:
			page.rootNVDAObject = obj
			obj.treeInterceptor = page
	return obj


class Synthesizer:
	"""A synthesizer: it takes what NVDA's speech manager gives it, and, when a test lets it finish, tells NVDA it has
	reached each index in it, as a synthesizer does as it speaks (synthDriverHandler.synthIndexReached)."""

	def __init__(self, nvda):
		self.nvda = nvda
		#: Each utterance NVDA's speech manager gave it: said, at least in part.
		self.given = []
		self._unfinished = []

	def speak(self, sequence):
		self.given.append(list(sequence))
		self._unfinished.append([item.index for item in sequence if isinstance(item, self.nvda.commands.IndexCommand)])

	def cancel(self):
		self._unfinished.clear()

	def finish(self):
		"""Say everything NVDA's speech manager has for it, to the end."""
		for _ in range(1000):
			if not self._unfinished:
				return
			for index in self._unfinished.pop(0):
				self.nvda.synthDriverHandler.synthIndexReached.notify(synth=self, index=index)
			self.nvda.synthDriverHandler.synthDoneSpeaking.notify(synth=self)
		raise AssertionError("the synthesizer never finished")

	def heard(self) -> list:
		"""What it said: the words of each utterance, without the separator NVDA's speak puts after each."""
		return [[item.removesuffix(CHUNK_SEPARATOR) for item in utterance if isinstance(item, str)] for utterance in self.given]


class Nvda:
	"""NVDA 2026.2's speech manager, speech.speak and cancelSpeech, focus events and api, around one synthesizer."""

	def __init__(self):
		#: NVDA's one log, which NVDA's speech manager gives its own methods.
		self.log = Log()
		self.config = types.SimpleNamespace(
			conf={
				# 0, NVDA's default: speech for a focus that has moved on is dropped.
				"featureFlag": {"cancelExpiredFocusSpeech": 0},
				"debugLog": {"speechManager": False, "events": False},
				"reviewCursor": {"followFocus": False},
			},
			ProfileTrigger=object,
		)
		self.synth = Synthesizer(self)
		# NVDA's extension points, pre_speech, filter_speechSequence and speech.speak (test_v129_speechHistory).
		self.base = v129.Nvda(v129._frame)
		self.extensions = self.base.extensions
		Action = type(self.extensions.pre_speech)
		for name, action in v129.run(NVDA_EXTENSIONS, {"Action": Action}, "speech/extensions.py").items():
			if isinstance(action, Action):
				setattr(self.extensions, name, action)
		self.synthDriverHandler = v129.module(
			"synthDriverHandler",
			NVDA_SYNTH_EXTENSIONS,
			"synthDriverHandler.py",
			extensionPoints=types.SimpleNamespace(Action=Action),
		)
		self.synthDriverHandler.getSynth = lambda: self.synth
		self.synthDriverHandler.handlePostConfigProfileSwitch = lambda resetSpeechIfNeeded=True: None
		self.commands = commands = v129.module(
			"speech.commands",
			NVDA_COMMANDS,
			"speech/commands.py",
			ABCMeta=ABCMeta,
			abstractmethod=abstractmethod,
			Optional=Optional,
			config=self.config,
			getSynth=self.synthDriverHandler.getSynth,
		)
		self.priorities = v129.module("speech.priorities", NVDA_PRIORITIES, "speech/priorities.py", IntEnum=IntEnum)
		self.managerModule = v129.module(
			"speech.manager",
			NVDA_MANAGER,
			"speech/manager.py",
			typing=typing,
			queueHandler=types.SimpleNamespace(eventQueue=None, queueFunction=lambda queue, function, *args, **kwargs: function(*args, **kwargs)),
			synthDriverHandler=self.synthDriverHandler,
			config=self.config,
			SpeechSequence=list,
			_IndexT=int,
			EndUtteranceCommand=commands.EndUtteranceCommand,
			SuppressUnicodeNormalizationCommand=commands.SuppressUnicodeNormalizationCommand,
			SynthParamCommand=commands.SynthParamCommand,
			LangChangeCommand=commands.LangChangeCommand,
			BaseCallbackCommand=commands.BaseCallbackCommand,
			ConfigProfileTriggerCommand=commands.ConfigProfileTriggerCommand,
			IndexCommand=commands.IndexCommand,
			_CancellableSpeechCommand=commands._CancellableSpeechCommand,
			pre_speechQueued=self.extensions.pre_speechQueued,
			Spri=self.priorities.Spri,
			SPEECH_PRIORITIES=self.priorities.SPEECH_PRIORITIES,
			shouldSwitchVoice=lambda: False,
			log=self.log,
			getSynth=self.synthDriverHandler.getSynth,
			pre_synthSpeak=self.synthDriverHandler.pre_synthSpeak,
			Dict=Dict,
			Any=Any,
			List=List,
			Tuple=Tuple,
			Optional=Optional,
			cast=cast,
		)
		self.manager = self.managerModule.SpeechManager()
		vars(self.base.speechModule).update(_manager=self.manager, Spri=self.priorities.Spri)
		self.speak = self.base.speechModule.speak
		self.cancelSpeech = v129.run(
			NVDA_CANCEL_SPEECH,
			{
				"__name__": "speech.speech",
				"__package__": "speech",
				"pre_speechCanceled": self.extensions.pre_speechCanceled,
				"speechCanceled": self.extensions.speechCanceled,
				"_speechState": self.base.speechState,
				"SpeechMode": v129.SpeechMode,
				"_manager": self.manager,
			},
			"speech/speech.py",
		)["cancelSpeech"]
		self.globalVars = types.SimpleNamespace(focusObject=None, focusAncestors=[], focusDifferenceLevel=0, foregroundObject=None, desktopObject=None)
		self.api = v129.module(
			"api",
			NVDA_API_FOCUS,
			"api.py",
			globalVars=self.globalVars,
			NVDAObjects=NVDA_OBJECTS,
			log=self.log,
			objectBelowLockScreenAndWindowsIsLocked=lambda obj, shouldLog=False: False,
			# loseFocus and focusExited: nothing here does anything for them.
			eventHandler=types.SimpleNamespace(executeEvent=lambda eventName, obj, **kwargs: None),
			appModuleHandler=types.SimpleNamespace(cleanup=lambda: None, handleAppSwitch=lambda oldAppModules, newAppModules: None),
			watchdog=types.SimpleNamespace(alive=lambda: None),
			controlTypes=v126.controlTypes,
			Window=object,
			treeInterceptorHandler=types.SimpleNamespace(
				cleanup=lambda: None,
				update=lambda obj: vars(obj).get("inPage"),
				post_browseModeStateChange=types.SimpleNamespace(notify=lambda **kwargs: None),
			),
			exceptions=types.SimpleNamespace(CallCancelled=CallCancelled),
			braille=types.SimpleNamespace(invalidateCachedFocusAncestors=lambda level: None),
			config=self.config,
			setNavigatorObject=lambda obj, isFocus=False: None,
		)
		self.eventHandler = v129.module(
			"eventHandler",
			NVDA_FOCUS_EVENTS,
			"eventHandler.py",
			_CancellableSpeechCommand=commands._CancellableSpeechCommand,
			api=self.api,
			speech=types.SimpleNamespace(manager=self.managerModule, _manager=self.manager),
			log=self.log,
			controlTypes=v126.controlTypes,
			oleacc=types.SimpleNamespace(),
			IA2=types.SimpleNamespace(),
			config=self.config,
			objectBelowLockScreenAndWindowsIsLocked=lambda obj, shouldLog=False: False,
			handlePossibleDesktopNameChange=lambda: None,
			executeEvent=self.executeEvent,
			Optional=Optional,
			typing=typing,
		)
		#: What NVDA was asked to say (its log's "Speaking" lines), heard through NVDA's own pre_speech.
		self.speaking = []
		self._onSpeech = lambda speechSequence=None, **kwargs: self.speaking.append([item for item in speechSequence if isinstance(item, str) and item])
		self.extensions.pre_speech.register(self._onSpeech)

	def executeEvent(self, eventName, obj, **kwargs):
		"""NVDA's eventHandler.executeEvent, when no plugin, app module or tree interceptor takes the event: a focus event
		runs doPreGainFocus, then the object's event_gainFocus; others run the object's event."""
		if eventName == "gainFocus":
			if self.eventHandler.doPreGainFocus(obj):
				obj.event_gainFocus()
		elif eventName in ("foreground", "focusEntered"):
			getattr(obj, f"event_{eventName}")()

	def focus(self, obj):
		self.executeEvent("gainFocus", obj)

	def modules(self) -> dict:
		"""What sys.modules holds while NVDA runs, for NVDA's code and the assistant's."""
		modules = dict(self.base.modules())
		# The speech package and speech.speech are test_v126_formFields' (patched by test_v131_redditPage).
		for name in ("speech", "speech.speech"):
			modules.pop(name, None)
		modules.update(
			{
				"api": self.api,
				"eventHandler": self.eventHandler,
				"NVDAObjects": NVDA_OBJECTS,
				"speech.commands": self.commands,
				"speech.manager": self.managerModule,
				"speech.priorities": self.priorities,
				"speech.sayAll": types.SimpleNamespace(SayAllHandler=types.SimpleNamespace(stop=lambda: None)),
				"synthDriverHandler": self.synthDriverHandler,
			},
		)
		return modules


class TabCase(unittest.TestCase):
	"""The tester's Edge: a GitHub tab with the focus in its comment box, and a reddit tab; Outlook in front."""

	def setUp(self):
		v131.patchNvda(self)
		speechHistory.unregister()
		self.addCleanup(speechHistory.unregister)
		self.nvda = nvda = Nvda()
		patcher = mock.patch.dict(sys.modules, nvda.modules())
		patcher.start()
		self.addCleanup(patcher.stop)
		# NVDA's speech package, as NVDA's speakObject and the assistant find it: NVDA's speak, manager and cancelSpeech.
		for owner, name, value in (
			(v126.speechPackage, "_manager", nvda.manager),
			(v126.speechPackage, "cancelSpeech", nvda.cancelSpeech),
			(v126.speechPackage, "speak", nvda.speak),
			(objectSpeech, "cancelSpeech", nvda.cancelSpeech),
		):
			patcher = mock.patch.object(owner, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)
		patcher = mock.patch.dict(v126.speechScope, {"speak": nvda.speak})
		patcher.start()
		self.addCleanup(patcher.stop)

		self.desktop = screenObject(-1, Role.PANE, "Desktop", appModule=None, windowClassName="#32769")
		self.outlook = screenObject(900, Role.WINDOW, "Inbox - Outlook - Outlook", self.desktop, appModule=OUTLOOK, windowClassName="rctrl_renwnd32")
		self.message = screenObject(901, Role.LISTITEM, "Dennis, Re: issue #30", self.outlook, appModule=OUTLOOK, windowClassName="rctrl_renwnd32")
		self.window = screenObject(10, Role.WINDOW, GITHUB_WINDOW, self.desktop, windowClassName="Chrome_WidgetWin_1")
		github = Page(passThrough=True)
		self.githubPage = screenObject(20, Role.DOCUMENT, GITHUB_TITLE, self.window, github, states=(State.FOCUSABLE, State.READONLY))
		self.main = screenObject(21, Role.LANDMARK, "", self.githubPage, github, attributes={"xml-roles": "main"})
		self.group = screenObject(22, Role.GROUPING, "new Comment", self.main, github)
		self.commentBox = screenObject(
			23,
			Role.EDITABLETEXT,
			"Add a comment",
			self.group,
			github,
			states=(State.FOCUSABLE, State.EDITABLE, State.MULTILINE),
			description="Markdown input: edit mode selected.",
			text="W",
		)
		self.button = screenObject(24, Role.BUTTON, "Paste, drop, or click to add files", self.group, github, states=(State.FOCUSABLE,))
		reddit = Page(passThrough=False)
		self.redditPage = screenObject(30, Role.DOCUMENT, REDDIT_TITLE, self.window, reddit, states=(State.FOCUSABLE, State.READONLY))
		self.adFrame = screenObject(31, Role.INTERNALFRAME, "Advertisement", self.redditPage, reddit)
		self.adPage = screenObject(32, Role.DOCUMENT, "Ad", self.adFrame, reddit, states=(State.FOCUSABLE, State.READONLY))
		self.adButton = screenObject(33, Role.BUTTON, "Learn more", self.adPage, reddit, states=(State.FOCUSABLE,))

		# Outlook is in front, with the focus on a message; the synthesizer has said all it had.
		self.foreground = self.outlook
		self.desktop.objectInForeground = lambda: self.foreground
		nvda.globalVars.desktopObject = self.desktop
		nvda.globalVars.foregroundObject = self.outlook
		nvda.globalVars.focusObject = self.message
		nvda.globalVars.focusAncestors = [self.desktop, self.outlook]
		nvda.globalVars.focusDifferenceLevel = 1

	def asTheTesterHasIt(self):
		"""The tester's assistant: edit fields as JAWS says them (formFields), and Edge's windows and pages
		(browserPages), and the speech history."""
		formFields.register()
		browserPages.register()
		speechHistory.register()

	def altTab(self, windowName, *focusEvents):
		"""Alt+Tab to Edge, its window named ``windowName``: Windows puts Edge in front, and Edge sends its focus events."""
		self.window.name = windowName
		self.foreground = self.window
		for obj in focusEvents:
			self.nvda.focus(obj)

	def caretLine(self):
		"""What browse mode says after a page's title as you come to it: the line at its caret (speakTextInfo), which
		has no command for the focus."""
		self.nvda.speak(["link", "Skip to main content"])

	def heard(self):
		self.nvda.synth.finish()
		return self.nvda.synth.heard()


# -- choosing the reddit tab in Alt+Tab ----------------------------------------------------------------------------


class RedditTabTests(TabCase):
	def switch(self):
		# Edge puts the focus back in the comment box of the tab it is leaving, then on the chosen tab's page.
		self.altTab(REDDIT_WINDOW, self.commentBox, self.redditPage)
		self.caretLine()
		return self.heard()

	def test_nvdaAskedToSayWhatTheTestersLogHas(self):
		# NVDA's own, but without "window", which 1.31 already took out: the log's lines word for word.
		self.asTheTesterHasIt()
		browserPages.unregister()
		self.switch()
		self.assertEqual(self.nvda.speaking[0], [REDDIT_WINDOW, "window"])
		self.assertEqual(self.nvda.speaking[1:5], TESTERS_LOG[1:])

	def test_nvdaDropsTheCommentBoxButSaysTheGitHubPageAroundIt(self):
		formFields.register()
		self.assertEqual(
			self.switch(),
			[[REDDIT_WINDOW, "window"], [GITHUB_TITLE, "document"], ["main landmark"], ["new Comment", "grouping"], [REDDIT_TITLE, "document"], ["link", "Skip to main content"]],
		)

	def test_onlyTheRedditPageAsJaws(self):
		self.asTheTesterHasIt()
		self.assertEqual(self.switch(), [[REDDIT_WINDOW], [REDDIT_TITLE], ["link", "Skip to main content"]])
		# NVDA was asked to say the GitHub page's places, with the assistant's command, and never did.
		self.assertIn([GITHUB_TITLE], self.nvda.speaking)
		self.assertIn(["new Comment", "grouping"], self.nvda.speaking)

	def test_theSpeechHistoryHoldsWhatWasSaid(self):
		self.asTheTesterHasIt()
		self.switch()
		self.assertEqual(speechHistory.entries(), [REDDIT_WINDOW, REDDIT_TITLE, "link  Skip to main content"])
		self.assertEqual(speechHistory.entries(), ["  ".join(words) for words in self.nvda.synth.heard()])

	def test_theAssistantsCommandNeverReachesTheSynthesizer(self):
		self.asTheTesterHasIt()
		self.switch()
		for utterance in self.nvda.synth.given:
			for item in utterance:
				self.assertNotIsInstance(item, self.nvda.commands._CancellableSpeechCommand)

	def test_aPageAlreadyBeingSaidIsSaidToTheEnd(self):
		# The window's name was with the synthesizer when the focus moved to the reddit page: the window is still around
		# the focus, so it isn't cut short.
		self.asTheTesterHasIt()
		self.altTab(REDDIT_WINDOW, self.commentBox)
		self.assertEqual(self.nvda.synth.heard(), [[REDDIT_WINDOW]])
		self.nvda.focus(self.redditPage)
		self.assertEqual(self.heard(), [[REDDIT_WINDOW], [REDDIT_TITLE]])

	def test_turnedOffNvdasOwn(self):
		self.asTheTesterHasIt()
		browserPages.unregister()
		self.assertEqual(
			self.switch(),
			[[REDDIT_WINDOW, "window"], [GITHUB_TITLE, "document"], ["main landmark"], ["new Comment", "grouping"], [REDDIT_TITLE, "document"], ["link", "Skip to main content"]],
		)

	def test_whereNvdaKeepsSpeechForAFocusThatMovedOnSoDoesTheAssistant(self):
		# NVDA's "cancelExpiredFocusSpeech" feature flag set to no: NVDA drops nothing, and neither does the assistant.
		self.nvda.config.conf["featureFlag"]["cancelExpiredFocusSpeech"] = 2
		self.asTheTesterHasIt()
		heard = self.switch()
		self.assertEqual(heard, [[REDDIT_WINDOW], [GITHUB_TITLE], ["main landmark"], ["new Comment", "grouping"], COMMENT_BOX, [REDDIT_TITLE], ["link", "Skip to main content"]])
		self.assertEqual(speechHistory.entries(), ["  ".join(words) for words in heard])


# -- choosing the GitHub tab ---------------------------------------------------------------------------------------


class GitHubTabTests(TabCase):
	def test_thePageByItsTitleAsJaws(self):
		self.asTheTesterHasIt()
		self.altTab(GITHUB_WINDOW, self.commentBox)
		heard = self.heard()
		self.assertEqual(heard, [[GITHUB_WINDOW], [GITHUB_TITLE], ["main landmark"], ["new Comment", "grouping"], COMMENT_BOX])
		# JAWS's words for the window and the page, the same.
		self.assertEqual(heard[:2], JAWS_GITHUB[:2])

	def test_nvdaSaidDocument(self):
		formFields.register()
		self.altTab(GITHUB_WINDOW, self.commentBox)
		self.assertEqual(self.heard()[:2], [[GITHUB_WINDOW, "window"], [GITHUB_TITLE, "document"]])

	def test_placesTheFocusIsStillInAreSaid(self):
		# Tab from the comment box to the button next to it before NVDA has said the places around them: they are still
		# around the focus, so NVDA says them; only the comment box, which the focus left, is dropped (by NVDA).
		self.asTheTesterHasIt()
		self.altTab(GITHUB_WINDOW, self.commentBox, self.button)
		self.assertEqual(
			self.heard(),
			[[GITHUB_WINDOW], [GITHUB_TITLE], ["main landmark"], ["new Comment", "grouping"], ["Paste, drop, or click to add files", "button"]],
		)

	def test_aFramesPageIsSaidAsNvdaSaysIt(self):
		# A document inside the page (a frame's) isn't the page: NVDA says it as before.
		self.asTheTesterHasIt()
		self.altTab(REDDIT_WINDOW, self.adButton)
		heard = self.heard()
		self.assertEqual(heard[1], [REDDIT_TITLE])
		self.assertIn(["Ad", "document"], heard)

	def test_otherProgramsAreAsBefore(self):
		self.asTheTesterHasIt()
		self.foreground = self.outlook
		self.nvda.focus(self.githubPage)
		self.nvda.synth.finish()
		self.nvda.synth.given.clear()
		self.nvda.focus(self.message)
		self.assertEqual(self.heard(), [["Inbox - Outlook - Outlook", "window"], ["Dennis, Re: issue #30"]])


# -- a title NVDA is still saying ----------------------------------------------------------------------------------


class SaidOnceTests(TabCase):
	def test_aPageSaidTwiceAtOnceIsSaidOnce(self):
		# The tester's log, 16:20:11.382 and 16:20:11.394: the reddit page's title twice, as browse mode reports the page
		# as it gets the focus and again as the page takes it.
		self.asTheTesterHasIt()
		self.altTab(REDDIT_WINDOW, self.redditPage)
		v126.speechPackage.speakObject(self.redditPage, reason=OutputReason.FOCUS)
		self.assertEqual(self.heard(), [[REDDIT_WINDOW], [REDDIT_TITLE]])
		# Once NVDA has said it, it is said again when asked.
		self.redditPage.reportFocus()
		self.assertEqual(self.heard(), [[REDDIT_WINDOW], [REDDIT_TITLE], [REDDIT_TITLE]])

	def test_aWindowSaidTwiceAtOnceIsSaidOnce(self):
		self.asTheTesterHasIt()
		self.altTab(GITHUB_WINDOW, self.commentBox)
		self.window.event_focusEntered()
		self.assertEqual(self.heard()[:2], [[GITHUB_WINDOW], [GITHUB_TITLE]])

	def test_saidAgainWhenNvdaCutItShort(self):
		# Alt+Tab to Edge twice in a row: NVDA cuts speech short for the new window in front (event_foreground), so the
		# second time the window is said again.
		self.asTheTesterHasIt()
		self.altTab(GITHUB_WINDOW, self.commentBox)
		self.foreground = self.outlook
		self.nvda.focus(self.message)
		self.altTab(GITHUB_WINDOW, self.commentBox)
		self.assertEqual([words for words in self.heard() if words == [GITHUB_WINDOW]], [[GITHUB_WINDOW], [GITHUB_WINDOW]])

	def test_nvdasOwnSaysItTwice(self):
		formFields.register()
		self.altTab(REDDIT_WINDOW, self.redditPage)
		v126.speechPackage.speakObject(self.redditPage, reason=OutputReason.FOCUS)
		self.assertEqual(self.heard(), [[REDDIT_WINDOW, "window"], [REDDIT_TITLE, "document"], [REDDIT_TITLE, "document"]])


# -- the speech history ---------------------------------------------------------------------------------------------


class HistoryTests(TabCase):
	def test_whatNvdaCutShortBeforeSayingItIsLeftOut(self):
		# NVDA cuts speech short as another window comes to the front: what it hadn't started saying was never said.
		speechHistory.register()
		self.nvda.speak(["first", self.nvda.eventHandler._getFocusLossCancellableSpeechCommand(self.message, OutputReason.FOCUS)])
		self.nvda.speak(["second", self.nvda.eventHandler._getFocusLossCancellableSpeechCommand(self.message, OutputReason.FOCUS)])
		self.nvda.speak(["no focus command"])
		self.assertEqual(speechHistory.entries(), ["first", "second", "no focus command"], "still to be said")
		self.nvda.cancelSpeech()
		self.nvda.speak(["third"])
		self.nvda.synth.finish()
		self.assertEqual(self.nvda.synth.heard(), [["first"], ["third"]])
		# "first" was with the synthesizer; "no focus command" can't be told apart, so it stays.
		self.assertEqual(speechHistory.entries(), ["first", "no focus command", "third"])

	def test_copiedAsListed(self):
		self.asTheTesterHasIt()
		self.altTab(REDDIT_WINDOW, self.commentBox, self.redditPage)
		self.nvda.synth.finish()
		self.assertEqual(speechHistory.text("\r\n"), f"{REDDIT_WINDOW}\r\n{REDDIT_TITLE}")

	def test_withoutNvdasSpeechManagerEverythingStays(self):
		# An NVDA the assistant can't read the speech manager of: nothing is left out.
		self.asTheTesterHasIt()
		self.altTab(REDDIT_WINDOW, self.commentBox, self.redditPage)
		self.nvda.synth.finish()
		with mock.patch.object(v126.speechPackage, "_manager", None):
			self.assertEqual(len(speechHistory.entries()), len(self.nvda.speaking))


# -- the assistant's parts -----------------------------------------------------------------------------------------


class QueueTests(unittest.TestCase):
	def test_nothingToTellIsNeverLeftOut(self):
		self.assertFalse(speechQueue.neverSaid(()))
		self.assertFalse(speechQueue.stillToSay(()))
		self.assertEqual(speechQueue.cancellables(["a", object()]), ())

	def test_browserPagesStillHasSpeakObjectAlone(self):
		v131.SettingTests("test_theTwoModulesChangeDifferentFunctions").test_theTwoModulesChangeDifferentFunctions()


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
