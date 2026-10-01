# Testing the add-on in a real NVDA, on a private desktop

Written on 30 September 2026 while fixing issue 47 (1.54), and extended on 1 October (1.55; the stand-in page and Control+Z of 1.57; the unit box and the watchdog of 1.58; the choices one behind the other of 1.59). The tests under `tests/` run the add-on's code against
imitations of NVDA. They could not show what was wrong with 1.46 to 1.53, which only a running NVDA shows (NVDA looks for a key's script on the
keyboard hook's thread, where its objects can't be read, and its buffer has one suggestion of a list). This runs a **second NVDA 2026.2 on its own
Windows desktop**, with Microsoft Edge on that desktop, next to the user's own NVDA, which it never touches. Nothing here is part of the add-on and
none of it is packaged (`build.py` packages only `addon/`).

## Why it is safe, and what to check before changing it

- NVDA's single-instance check (a window of class wxWindowClassNR and a mutex) is per desktop. Starting NVDA on the *same* desktop kills the running one.
  On a desktop made with `CreateDesktopW` it does not. `C:\Program Files\NVDA\nvda.exe` needs elevation (error 740 from `CreateProcess`); `nvda_noUIAccess.exe`
  does not. It is started with `-c <own config> -f <own log> --no-sr-flag --debug-logging`: its own settings and log, and it leaves the system's
  screen reader flag alone.
- The mouse pointer and key injection belong to the window station, not the desktop. `aa47driver.py` is a global plugin (the config has
  `enableScratchpadDir = True`) that replaces `winUser.keybd_event`, `mouse_event`, `SendInput`, `setCursorPos` and `getCursorPos` with recorders as it
  loads. Do not run anything in the private NVDA that can inject input without it loaded. `rig2.py` replays a recorded mouse press on the page with
  DevTools, at (screen position - the document's origin) / devicePixelRatio, as soon as NVDA has made it (the real pointer is never used; a page can
  change in a second, and one replay that came a second and a half late did not choose the row).
- The synthesizer is `silence`, sounds are off, and braille is `noBraille`; the rig reads what NVDA would say from its log (`Speaking [...]`).
- A private desktop has no foreground window, so `aa47driver.py` tells NVDA where the focus is (`syncFocus`: finds the edit field through IAccessible2 and queues
  `foreground` and `gainFocus`), and runs gestures with `inputCore.manager.executeGesture` on a **plain thread**, which is how NVDA's keyboard hook runs the
  search for a script. Run it on the main thread and you will not see failures that only the hook thread has.
- **Stop the rig before running the full test suite** (`touch stop` next to `deskhost.py`): with its NVDA and Edge running, one Remote Access test
  (`test_v148_remoteTransport.SessionTests.test_tPressedAgainClosesTheConnection`) failed in every full run.
- **Two rigs at once** (sessions work in parallel, each in its own worktree) need their own desktop name and DevTools port, because a second NVDA on a desktop that
  already has one ends the first, and a port is the computer's. Set `JM_RIG_DESKTOP` (default `jm47`) and `JM_RIG_PORT` (default `9444`) in the shell before `mkconfig.py`,
  `start_edge.py` and every scenario, to values nobody else uses (1 October: the issue 49 session had `jm47` and 9444, this one `jm47b` and 9455). `ps`-style check first:
  `Get-CimInstance Win32_Process -Filter "Name='nvda_noUIAccess.exe'"` shows each private NVDA's `-c` folder, which names the session that owns it.

## Setting it up (from this folder, `tests/live_nvda`)

1. Make `cfg/addons/jawsMigrator` and `cfg/scratchpad/globalPlugins`; copy `nvda.ini.sample` to `cfg/nvda.ini` and `aa47driver.py` to
   `cfg/scratchpad/globalPlugins/`. Edit the ini to match the user's settings (the sample is the tester's: laptop layout, automatic focus mode for caret movement on).
2. Optional: `python -m pip install --target pylib websocket-client` (`rig.py` looks in `pylib` here). Without it, `rig.py` uses a small WebSocket client of its own (`_MiniSocket`), so nothing has to be installed.
3. Optional: `python fetch_addons.py` puts some of the tester's other add-ons into `cfg/addons` (the store's datastore JSON gives each URL), to see the assistant next to them. The scenarios also run with this add-on alone.
4. `python deploy.py --norestart` copies this repository's `addon/` to `cfg/addons/jawsMigrator`.
5. `python mkconfig.py nvda`, then run `python deskhost.py` in the background (it creates the desktop, starts NVDA on it, and runs until a file named `stop` appears next to it).
6. `python restart_nvda.py` kills and starts the private NVDA again, and waits for the driver (use it after `deploy.py` changes the add-on; `python deploy.py` does both). **It deletes `nvda.log` first** (there is no `nvda-old.log`), so copy the log away before a restart if you want that session's timeline. **Then run `python restart_edge.py`**:
   NVDA injects its helper into a browser that starts after it, and an Edge that was running when NVDA started again is left without it ("appModule has no binding handle to injected code, can't prepare
   virtualBuffer yet" in NVDA's log). The document then has no buffer (`isReady` False, browse mode, and NVDA never gives a field its own focus event), a state no user has. After `restart_edge.py` the document is
   `ChromeVBuf`, ready, in focus mode while you type, as a user's is (check with `s.driver("eval", ...)`: `api.getFocusObject().treeInterceptor.isReady`).
7. `python start_edge.py` opens Edge on the private desktop with DevTools; then run a scenario from this folder, as a module: `python -m scenarios.s29`. A scenario types the
   address through DevTools, gives NVDA the focus, presses keys through NVDA's gesture handling, forwards what NVDA sent to the page, and prints what NVDA said
   and what the page did. `touch stop` ends it all.

The visible.com address list needs the page's own address service to answer; if no suggestions appear, wait or try again.

**Without the live site.** Set `JM_RIG_PAGE` to the local stand-in, `file:///<this folder>/pages/address.html`: it has the live page's markup and does what the live page was measured to do (Down Arrow in the field
focuses the first suggestion and the blur then closes the list; a suggestion is chosen by its `mousedown`; choosing sets the field's text by script and shuts the list; any edit of the text is an `input` event, forgets
the choice and asks for suggestions 300 ms later), with twenty canned suggestions for "241 w pine st" and one for a whole address. `window.__log` has what the page saw, for the scenarios to print. Nothing is typed
into a live site and no network is needed. Use it for anything that does not depend on the live service.

Since 1 October (1.58) the stand-in also has the unit step of the live page's script (clientlib-fioscheckavailability, read, not typed into): choosing the third or the eleventh address (the eleventh is GROVE CITY, PA,
which the tester chose) shows the unit box and focuses it with a zero-delay timer; its focus handler asks for its list ("Loading...", then five units and "I can't find my unit" and "I don't live in a unit",
`window.__unitServiceDelay` makes its service slower); choosing a unit puts it in the box by script; its blur closes the list 150 ms later; any change of the address box's text hides the unit box. This desktop has
no real focus events, so `Scenario.toUnitBox()` gives NVDA the focus event the page's move would cause (`syncFocus` finds the box by its name), and after Control+Z a scenario gives it the address box's.

## The scenarios (`scenarios/`)

- `s29`, `s15`, `s18`: the tester's steps (type, Down Arrow, Up Arrow, Enter, Down Arrow to the thirteenth, which is out of sight in the list); `s23` with the field's list link made empty;
  `s24` Escape, a typed letter and Tab; `s35` Down Arrow and Enter at once; `s34` presses Down Arrow twice and prints the page after each: with the add-on of the v1.53 release
  deployed (unpack its package into `cfg/addons/jawsMigrator`) it shows the failure of 1.46 to 1.53: the key does nothing to the list. Every scenario uses whatever add-on is deployed.
- Small windows (1 October): `s41` makes the Edge window small with DevTools (`Browser.setWindowBounds`) and prints what NVDA says of each row; `s42` and `s43` press the row at the page's
  bottom edge (1.54 pressed outside the page, 1.55 on its visible part); `s50` a row the page hides, then Up Arrow and Enter; `s51` makes the window usual again.
- What was tried to bring a row that the page's edge hides into the page, and failed, which is why 1.55 presses where a row shows instead: every IAccessible2 `scrollTo` type (`s45`), the
  page's `scrollIntoView` (`s46`, `s48`), and `scrollToPoint` (`s49`: it moved the list the wrong way). The address form is in a part of the page that stays where it is. `s40` tried NVDA's
  hit test `objectFromPoint` for "what is under the pointer": it answered with a generic section for a row in plain view, so it can't be used.

- After a choice (issue 47, 1 October, 1.57; run on the stand-in page): `s52` is the tester's steps from his 1.55 log (type, Down Arrow to the eighth, Enter, then Up Arrow, Down Arrow, Down Arrow: no list, and the last key
  leaves the field because his NVDA has automatic focus mode for caret movement on); `s53` tries what brings the list back (Backspace once: a list of the one address; Control+A and typing the street: all twenty; the browser's
  own Control+Z: the one address again; `accValue` set to the street on NVDA's main thread: the page gets an `input` event and shows all twenty, NVDA says nothing); `s54` and `s55` are Control+Z with the assistant (the choice
  taken back and Down Arrow at once, typing in between, nothing chosen, after Up Arrow and Down Arrow, twice); `s56 [rounds]` repeats choose, Control+Z, Down Arrow at once or after a pause, choose another, and counts the rounds.
- The unit box (issue 47, 1 October, 1.58; run on the stand-in page, with `restart_edge.py` done so that the buffer is ready): `s58 [letters]`. A is the tester's fourth round (the eleventh address, Enter, the unit box has the
  focus, Control+Z): with 1.57 the key was the page's, which hid the unit box and left a list of the one address; with 1.58 NVDA says "Choice undone, 241 w pine st", the page has its text, the unit box is gone and
  all twenty suggestions are back. B is Control+Z in the middle of going down the units, C a unit chosen with Enter and taken back (twice), D a unit service that answers after 2.2 seconds (Down Arrow as soon as the
  focus arrives waits and says the first unit), E something typed in the unit box (the key is left to the page; the rig does not show the key NVDA sends on), F Control+Z in the address box after Shift+Tab,
  G a unit service that answers after 4.5 seconds ("No suggestions yet"). `s57` is the same for the address list after Control+Z, with a service that answers after 0.9 and after 4 seconds.
  **NVDA's watchdog:** do not hold NVDA's main thread in a script (a loop that sleeps between looks, `driver("eval")` included) for much more than half a second. The watchdog then cancels the COM calls made until the thread
  comes round ("COM call cancelled", on and off from a second in, measured here with a loop of looks at the unit list), and the results are not what a user would get. 1.57's Down Arrow waited that way (up to 1.5 seconds);
  1.58's looks with NVDA's own timer (`core.callLater`).
  What the rig cannot show: a press replayed on the page after the script returns, so a script that waits for the page to react to its own press (a loop of reads) waits for nothing: the rig only replays the press when
  `driver("sent")` is answered, which the main thread, busy in that script, cannot do. The assistant does not wait for it.
- Choices one behind the other (issue 47, 1 October, 1.59; run on the stand-in page, `restart_edge.py` done): `s61 [letters]`, from the tester's 1.58 log of 11:44 to 11:45 (the eleventh address, a unit chosen with Enter, Control+Z, and then Down Arrow in
  the address box, which found no list). A is his steps and then a second Control+Z (with 1.58 the page's own: it hid the unit box and left a list of the one address; with 1.59 NVDA says "Choice undone, 241 w pine st" and all twenty come back),
  B the address box after the unit was taken back (Down Arrow there goes on as NVDA has it; NVDA is then told the focus is in the unit box, as a real NVDA's focus event would, and Control+Z takes the address back from there), C Shift+Tab to the address box
  right after the unit was chosen and Control+Z there, D the unit box left and entered again 3.5 seconds after the choice (NVDA's new object, known by its identity) with a visit to the units and Control+Z in the middle of it,
  E a unit chosen and taken back, another chosen and taken back, then the address, and Down Arrow into the twenty, F something typed in the unit box (the page's own Control+Z) and then Control+Z in the address box, G "APT" typed in the unit box before a unit is chosen (once the unit is taken back the box holds "APT" again, so NVDA says only "Choice undone, APT":
  it must not promise the address, because a second Control+Z in a box that holds text is the page's own).
  This desktop delivers no focus events, so a scenario that moves the page's focus tells NVDA (`syncFocus`) before the next key, or NVDA's idea of the focus is stale (B showed it: the page's focus fell to the body when the unit box was hidden).

## The speech volume that changed between typing and reading (issue 49, 1 October, 1.56)

No Edge is needed. `setup_issue49.py` writes the tester's profiles (`JAWS - msedge`, `browseMode`, ...), his normal configuration's Eloquence settings, the triggers, the assistant's settings, and a **silent copy of
Eloquence64RS 19.1.4's driver** into the private NVDA's `cfg/scratchpad/synthDrivers`: its functions that keep and apply a copy of the voice's settings for each set of turned-on profiles, and its
`loadSettings`, `saveSettings`, pitch and volume, are the add-on's own, word for word (`tests/issue49Sources.py`), with an engine that is a table of numbers, so nothing can be heard on the PC. Run it with `off`
(the assistant's setting that keeps the voice's settings the same everywhere turned off: NVDA and Eloquence as the tester had them) or `ask` (the question about settings that differ is asked 20 seconds after
NVDA starts), then `python restart_nvda.py`, then, from this folder, `python -m scenarios.s60 control|fixed|question|user`. `scenarios/s60.py` says what each does: NVDA's real Settings dialog is opened on its Speech
category, the Volume slider is moved with the slider's own event and OK is pressed; the settings ring is NVDA's own scripts; Edge's profile is turned on with NVDA's own `ProfileTrigger` and `browseMode` with
`config.conf.manualActivateProfile`, as Custom Browse Mode does. This NVDA is not an installed copy and can't duck audio, so the scenario imitates only `audioDucking.setAudioDuckingMode`.
