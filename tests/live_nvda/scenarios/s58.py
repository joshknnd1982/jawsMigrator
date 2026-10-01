"""Choosing an address that has units, then Control+Z (issue 47, 1 October 2026, 1.58; run on the stand-in page, pages/address.html).

The tester's fourth round in his 1.57 log: Down Arrow eleven times to GROVE CITY, Enter ("... selected"), the page shows its unit box and moves the focus
to it ("Enter Unit Label, edit, has auto complete, blank"), and Control+Z said "Undo" (the page's own) instead of "Choice undone". With 1.57 this
scenario shows the same: the page's undo hides the unit box and leaves a list of the one address.

This desktop has no real focus events, so the scenario gives NVDA the focus event the page's change would cause: toUnitBox() after the choice and
backToAddress() after Control+Z (NVDA's own, queued as the WinEvent handler would).

    python -u -m scenarios.s58 [letters]

A: the eleventh address, Enter, the unit box has the focus, Control+Z; then Down Arrow into the address suggestions and Enter on the second.
B: the same, Down Arrow twice in the unit box first (a visit to the units), then Control+Z in the middle of it.
C: a unit chosen with Enter in the unit box, then Control+Z (the empty box, the page shows its units again), Down Arrow at once, Enter.
D: a slow unit service (2200 ms): Down Arrow in the unit box as soon as the focus arrives waits for the units. G: a service slower than the wait (4500 ms).
E: something typed in the unit box, then Control+Z: the page's own, as before.
F: Shift+Tab to the address box and Control+Z there.
"""
import sys
import time

from rig2 import Scenario

s = Scenario()
which = sys.argv[1].lower() if len(sys.argv) > 1 else "abcdefg"


def speech():
    return [line.split("Speaking ", 1)[1] for line in s.newLog("Speaking \\[", limit=500)]


def chooseEleventh(unitDelay=None):
    s.fresh()
    s.cdp.js(f"window.__unitServiceDelay = {unitDelay if unitDelay is not None else 'undefined'}; 1")
    for key in ["downArrow"] * 11 + ["enter"]:
        s.press(key, wait=0.5, show=False)
    time.sleep(0.6)
    print("   page after Enter:", s.unit())


def backToAddress():
    s.driver("syncFocus", find="Enter your home address")
    time.sleep(0.5)


def log(pattern="jawsMigrator|DRIVER"):
    return [line[:300] for line in s.newLog(pattern, limit=300)]


if "a" in which:
    print("=== A: the eleventh address, Enter, the unit box has the focus, Control+Z, Down Arrow, Down Arrow, Enter")
    chooseEleventh()
    s.toUnitBox()
    print("   nvda focus:", s.nvda()["focus"])
    s.newLog()
    s.press("control+z", wait=1.0)
    print("   page after Control+Z:", s.unit())
    backToAddress()
    print("   nvda focus:", s.nvda()["focus"])
    print("   spoken since Control+Z:", speech())
    s.press("downArrow", wait=1.0)
    s.press("downArrow", wait=0.8)
    s.press("enter", wait=1.0)
    print("   page at the end:", s.unit())

if "b" in which:
    print("=== B: the eleventh address, Enter, Down Arrow twice in the unit box, then Control+Z in the middle of the visit")
    chooseEleventh()
    s.toUnitBox()
    s.press("downArrow", wait=0.8)
    s.press("downArrow", wait=0.8)
    s.newLog()
    s.press("control+z", wait=1.0)
    print("   page after Control+Z:", s.unit())
    backToAddress()
    print("   nvda focus:", s.nvda()["focus"])
    s.press("downArrow", wait=1.0)
    print("   page:", s.unit()["address"], s.unit()["addressList"])

if "c" in which:
    print("=== C: a unit chosen with Enter, then Control+Z, Down Arrow at once, Enter")
    chooseEleventh()
    s.toUnitBox()
    s.press("downArrow", wait=0.8)
    s.press("downArrow", wait=0.8)
    s.press("enter", wait=1.0)
    print("   page after the unit was chosen:", s.unit())
    s.newLog()
    s.press("control+z", wait=0.4)
    print("   page after Control+Z:", s.unit())
    s.press("downArrow", wait=1.0)
    s.press("downArrow", wait=0.8)
    s.press("enter", wait=1.0)
    print("   page after the second choice:", s.unit())
    s.press("control+z", wait=1.0)
    print("   page after a Control+Z that takes back the second choice:", s.unit())

def slowUnits(delay):
    """The unit service answers after ``delay`` ms: the unit list says "Loading..." until then. Enter, the focus event, Down Arrow, as fast as the rig goes."""
    s.fresh()
    s.cdp.js(f"window.__unitServiceDelay = {delay}; 1")
    for key in ["downArrow"] * 11:
        s.press(key, wait=0.3, show=False)
    s.press("enter", wait=0.1, show=False)
    s.driver("syncFocus", find="Enter Unit Label")
    print("   page as the focus arrives:", {k: v for k, v in s.unit().items() if k.startswith("unit") or k == "active"})
    s.newLog()
    started = time.time()
    s.press("downArrow", wait=0.5)
    print(f"   Down Arrow answered {time.time() - started:.1f} s after it was sent; speech so far:", speech())
    time.sleep(2.5)
    print("   speech 3 s after the key:", speech())
    for line in log("jawsMigrator.suggestionLists|watchdog|CallCancelled"):
        print("   LOG", line)
    print("   page later:", {k: v for k, v in s.unit().items() if k.startswith("unit") or k == "active"})


if "d" in which:
    print("=== D: the unit service answers after 2200 ms; Down Arrow as soon as the focus arrives waits for the units (at most 1.5 s)")
    slowUnits(2200)

if "g" in which:
    print("=== G: the unit service answers after 4500 ms; Down Arrow waits 1.5 s, then does what NVDA does with the key")
    slowUnits(4500)

if "e" in which:
    print("=== E: something typed in the unit box, then Control+Z")
    chooseEleventh()
    s.toUnitBox()
    s.cdp.type("4B")
    time.sleep(1.2)
    print("   page after typing:", s.unit())
    s.newLog()
    s.press("control+z", wait=1.0)
    print("   page after Control+Z:", s.unit())

if "f" in which:
    print("=== F: Shift+Tab to the address box, then Control+Z there")
    chooseEleventh()
    s.toUnitBox()
    s.cdp.js("document.querySelector('#address-input').focus(); 1")
    time.sleep(0.5)
    s.driver("syncFocus", find="Enter your home address")
    time.sleep(0.5)
    print("   page before:", s.unit())
    print("   nvda focus:", s.nvda()["focus"])
    s.newLog()
    s.press("control+z", wait=1.0)
    print("   page after Control+Z:", s.unit())
    s.press("downArrow", wait=1.0)
