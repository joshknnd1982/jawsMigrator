"""The tester's 1.58 log of 1 October 2026 (11:44 to 11:45 his time), on the stand-in page (issue 47, 1.59).

He typed the address, went down to the eleventh (GROVE CITY, PA), Enter, and the page moved the focus to its unit box. Down Arrow went through the units
and Enter chose UNIT 2 ("UNIT 2, selected"). Control+Z took the unit back ("Choice undone"). Then Up Arrow
(NVDA's automatic focus mode for caret movement takes him out of the unit box to the address box) and Down Arrow in the address box, three times over in
different ways: "no suggestions are showing for it". The address choice could not be taken back any more: 1.58 kept one choice, the unit, and a second
Control+Z was the page's own.

    python -u -m scenarios.s61 [letters]

A: his steps, to the end: the eleventh address, Enter, the unit box, Down Arrow x3, Enter on the third, Control+Z, then Control+Z again.
B: the same, then the address box has the focus (Up Arrow's way out of the unit box) and Control+Z is pressed there.
C: the unit chosen, then Shift+Tab to the address box (the unit box stays, holding the unit) and Control+Z in the address box.
D: the unit box left and entered again (a new object for NVDA) after the choice, then Down Arrow in it, then Control+Z.
E: a unit chosen, taken back, another chosen and taken back, and then the address taken back (what NVDA says each time).
F: something typed in the unit box after a unit was chosen (Control+Z is the page's own), then Shift+Tab and Control+Z in the address box (the address choice is
   still there to take back).
G: "APT" typed in the unit box BEFORE a unit is chosen: once the unit is taken back the box holds "APT" again, so NVDA says only "Choice undone, APT" (it must not
   promise that a second Control+Z takes the address back: in a box that holds text it is the page's own), and the address is taken back from the address box.
"""
import sys
import time

from rig2 import Scenario

s = Scenario()
which = sys.argv[1].lower() if len(sys.argv) > 1 else "abcdefg"


def speech():
    return [line.split("Speaking ", 1)[1][:200] for line in s.newLog("Speaking \\[", limit=500)]


def log(pattern="jawsMigrator.suggestionLists|DRIVER|CallCancelled|watchdog"):
    return [line[:330] for line in s.newLog(pattern, limit=400)]


def toAddress():
    s.cdp.js("document.querySelector('#address-input').focus(); 1")
    time.sleep(0.4)
    s.driver("syncFocus", find="Enter your home address")
    time.sleep(0.5)


def toUnit():
    s.cdp.js("document.querySelector('#unit-input').focus(); 1")
    time.sleep(0.4)
    s.driver("syncFocus", find="Enter Unit Label")
    time.sleep(0.8)


def chooseEleventh():
    s.fresh()
    for key in ["downArrow"] * 11 + ["enter"]:
        s.press(key, wait=0.5, show=False)
    time.sleep(0.6)
    print("   page after Enter:", s.unit())
    s.toUnitBox()
    print("   nvda focus:", s.nvda()["focus"])


def chooseUnit():
    for _ in range(3):
        s.press("downArrow", wait=0.8, show=False)
    s.press("enter", wait=1.0, show=False)
    time.sleep(0.5)
    print("   page after the unit was chosen:", s.unit())


def undo(label):
    s.newLog()
    s.press("control+z", wait=1.2, show=False)
    time.sleep(0.6)
    print(f"   {label}: page", s.unit())
    print("   spoken:", speech())
    for line in log():
        print("   LOG", line)


if "a" in which:
    print("=== A: his steps: the eleventh address, the unit chosen, Control+Z, Control+Z again")
    chooseEleventh()
    chooseUnit()
    undo("first Control+Z")
    print("   nvda focus:", s.nvda()["focus"])
    undo("second Control+Z")
    print("   nvda focus:", s.nvda()["focus"])

if "b" in which:
    print("=== B: the unit chosen and taken back, the address box has the focus, Control+Z there")
    chooseEleventh()
    chooseUnit()
    undo("first Control+Z")
    toAddress()
    print("   nvda focus:", s.nvda()["focus"])
    s.newLog()
    info = s.press("downArrow", wait=1.0, show=False)
    print("   Down Arrow in the address box, spoken:", speech(), " page:", s.unit()["addressList"], "active:", s.unit()["active"])
    print("   what the key did:", {k: info.get(k) for k in ("script", "handled", "passedThrough", "forwardedToPage")})
    # NVDA's own Down Arrow moved the page's focus to the unit box; this desktop has no real focus events, so NVDA is told, as a real NVDA is.
    if s.unit()["active"] == "unit-input":
        s.toUnitBox()
    print("   nvda focus:", s.nvda()["focus"])
    undo("Control+Z after Down Arrow in the address box")
    print("   page focus:", s.unit()["active"], "nvda focus:", s.nvda()["focus"])

if "c" in which:
    print("=== C: the unit chosen, Shift+Tab to the address box (the unit box stays), Control+Z there")
    chooseEleventh()
    chooseUnit()
    toAddress()
    print("   page before:", s.unit())
    undo("Control+Z in the address box")
    s.press("downArrow", wait=1.5)

if "d" in which:
    print("=== D: the unit box left and entered again after the choice, Down Arrow in it, then Control+Z")
    chooseEleventh()
    toAddress()
    time.sleep(3.5)
    toUnit()
    print("   nvda focus:", s.nvda()["focus"])
    s.newLog()
    s.press("downArrow", wait=1.0, show=False)
    print("   Down Arrow in the unit box, spoken:", speech())
    undo("Control+Z in the unit box that was entered again")

if "e" in which:
    print("=== E: a unit chosen and taken back, another chosen and taken back, then the address taken back")
    chooseEleventh()
    chooseUnit()
    undo("Control+Z (the first unit)")
    time.sleep(1.0)
    s.press("downArrow", wait=1.0, show=False)
    s.press("downArrow", wait=0.8, show=False)
    s.press("enter", wait=1.0, show=False)
    time.sleep(0.5)
    print("   page after the second unit was chosen:", {k: v for k, v in s.unit().items() if k in ("active", "unitValue", "address")})
    undo("Control+Z (the second unit)")
    undo("Control+Z (the address)")
    # The page's focus is in the address box again; this desktop has no real focus events, so NVDA is told, as a real NVDA is.
    s.driver("syncFocus", find="Enter your home address")
    time.sleep(0.5)
    s.press("downArrow", wait=1.5)

if "f" in which:
    print("=== F: something typed in the unit box after a unit was chosen, then Shift+Tab to the address box and Control+Z there")
    chooseEleventh()
    chooseUnit()
    s.cdp.type("x")
    time.sleep(1.2)
    print("   page after typing:", {k: v for k, v in s.unit().items() if k in ("active", "unitValue", "address")})
    undo("Control+Z with the typing in the unit box (the page's own)")
    toAddress()
    print("   nvda focus:", s.nvda()["focus"])
    undo("Control+Z in the address box")

if "g" in which:
    print("=== G: APT typed in the unit box before a unit is chosen; the unit taken back; Control+Z again; then the address box")
    chooseEleventh()
    s.cdp.type("APT")
    time.sleep(1.5)
    print("   page after typing:", {k: v for k, v in s.unit().items() if k in ("active", "unitValue", "address", "unitOptions")})
    s.press("downArrow", wait=0.8, show=False)
    s.press("enter", wait=1.0, show=False)
    time.sleep(0.5)
    print("   page after the unit was chosen:", {k: v for k, v in s.unit().items() if k in ("active", "unitValue", "address")})
    undo("Control+Z (the unit: the box holds APT again, so no promise of the address)")
    undo("Control+Z again (the page's own, as the box holds text)")
    toAddress()
    undo("Control+Z in the address box (the address choice is still there)")
