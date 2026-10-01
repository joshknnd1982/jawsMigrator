# Testing the add-on in a real NVDA, on a private desktop

Written on 30 September 2026 while fixing issue 47 (1.54), and extended on 1 October (1.55). The tests under `tests/` run the add-on's code against
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

## Setting it up (from this folder, `tests/live_nvda`)

1. Make `cfg/addons/jawsMigrator` and `cfg/scratchpad/globalPlugins`; copy `nvda.ini.sample` to `cfg/nvda.ini` and `aa47driver.py` to
   `cfg/scratchpad/globalPlugins/`. Edit the ini to match the user's settings (the sample is the tester's: laptop layout, automatic focus mode for caret movement on).
2. `python -m pip install --target pylib websocket-client` (the DevTools client; `rig.py` looks in `pylib` here).
3. Optional: `python fetch_addons.py` puts some of the tester's other add-ons into `cfg/addons` (the store's datastore JSON gives each URL), to see the assistant next to them. The scenarios also run with this add-on alone.
4. `python deploy.py --norestart` copies this repository's `addon/` to `cfg/addons/jawsMigrator`.
5. `python mkconfig.py nvda`, then run `python deskhost.py` in the background (it creates the desktop, starts NVDA on it, and runs until a file named `stop` appears next to it).
6. `python restart_nvda.py` kills and starts the private NVDA again, and waits for the driver (use it after `deploy.py` changes the add-on; `python deploy.py` does both).
7. `python start_edge.py` opens Edge on the private desktop with DevTools; then run a scenario from this folder, as a module: `python -m scenarios.s29`. A scenario types the
   address through DevTools, gives NVDA the focus, presses keys through NVDA's gesture handling, forwards what NVDA sent to the page, and prints what NVDA said
   and what the page did. `touch stop` ends it all.

The visible.com address list needs the page's own address service to answer; if no suggestions appear, wait or try again.

## The scenarios (`scenarios/`)

- `s29`, `s15`, `s18`: the tester's steps (type, Down Arrow, Up Arrow, Enter, Down Arrow to the thirteenth, which is out of sight in the list); `s23` with the field's list link made empty;
  `s24` Escape, a typed letter and Tab; `s35` Down Arrow and Enter at once; `s34` presses Down Arrow twice and prints the page after each: with the add-on of the v1.53 release
  deployed (unpack its package into `cfg/addons/jawsMigrator`) it shows the failure of 1.46 to 1.53: the key does nothing to the list. Every scenario uses whatever add-on is deployed.
- Small windows (1 October): `s41` makes the Edge window small with DevTools (`Browser.setWindowBounds`) and prints what NVDA says of each row; `s42` and `s43` press the row at the page's
  bottom edge (1.54 pressed outside the page, 1.55 on its visible part); `s50` a row the page hides, then Up Arrow and Enter; `s51` makes the window usual again.
- What was tried to bring a row that the page's edge hides into the page, and failed, which is why 1.55 presses where a row shows instead: every IAccessible2 `scrollTo` type (`s45`), the
  page's `scrollIntoView` (`s46`, `s48`), and `scrollToPoint` (`s49`: it moved the list the wrong way). The address form is in a part of the page that stays where it is. `s40` tried NVDA's
  hit test `objectFromPoint` for "what is under the pointer": it answered with a generic section for a row in plain view, so it can't be used.

## The speech volume that changed between typing and reading (issue 49, 1 October, 1.56)

No Edge is needed. `setup_issue49.py` writes the tester's profiles (`JAWS - msedge`, `browseMode`, ...), his normal configuration's Eloquence settings, the triggers, the assistant's settings, and a **silent copy of
Eloquence64RS 19.1.4's driver** into the private NVDA's `cfg/scratchpad/synthDrivers`: its functions that keep and apply a copy of the voice's settings for each set of turned-on profiles, and its
`loadSettings`, `saveSettings`, pitch and volume, are the add-on's own, word for word (`tests/issue49Sources.py`), with an engine that is a table of numbers, so nothing can be heard on the PC. Run it with `off`
(the assistant's setting that keeps the voice's settings the same everywhere turned off: NVDA and Eloquence as the tester had them) or `ask` (the question about settings that differ is asked 20 seconds after
NVDA starts), then `python restart_nvda.py`, then, from this folder, `python -m scenarios.s60 control|fixed|question|user`. `scenarios/s60.py` says what each does: NVDA's real Settings dialog is opened on its Speech
category, the Volume slider is moved with the slider's own event and OK is pressed; the settings ring is NVDA's own scripts; Edge's profile is turned on with NVDA's own `ProfileTrigger` and `browseMode` with
`config.conf.manualActivateProfile`, as Custom Browse Mode does. This NVDA is not an installed copy and can't duck audio, so the scenario imitates only `audioDucking.setAudioDuckingMode`.
