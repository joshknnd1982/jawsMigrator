# JAWS Migration Assistant for NVDA

An NVDA add-on that brings a JAWS user's settings into NVDA. It reads everything JAWS knows about you:

- Settings Center options.
- Voice profiles and voice aliases.
- Speech and sound schemes.
- Dictionaries and punctuation.
- Keyboard assignments and quick navigation keys.
- Sounds, and settings for single applications.

Each one is mapped to its NVDA equivalent, strictly: NVDA announces what JAWS announced, in the voice JAWS used, and nothing more. You choose exactly which settings, schemes, voice profiles, voice aliases and keyboard layouts come over. Anything NVDA can't use is kept in an archive and explained in a report.

Before anything changes, NVDA's settings, every add-on and the add-ons' own settings are backed up, so you can always go back to how NVDA was.

JAWS itself is never changed. The assistant only reads JAWS files. It never writes to, updates, reconfigures or uninstalls JAWS. When the migration is finished, it tells you that you can uninstall JAWS yourself if you want to.

- Version: 1.9
- Requires: NVDA 2026.1 or later (tested with NVDA 2026.2) on Windows 10 22H2 or Windows 11
- Works with: JAWS 18 and later, in any JAWS language, including settings left behind by an uninstalled JAWS
- License: GNU General Public License, version 2 or later

## Contents

- [What it does](#what-it-does)
- [Installing](#installing)
- [What's new in 1.9](#whats-new-in-19)
- [What's new in 1.8](#whats-new-in-18)
- [What's new in 1.7](#whats-new-in-17)
- [What's new in 1.6](#whats-new-in-16)
- [What's new in 1.5](#whats-new-in-15)
- [What's new in 1.4](#whats-new-in-14)
- [Using the assistant](#using-the-assistant)
- [Choosing what to import](#choosing-what-to-import)
- [What each JAWS manager becomes in NVDA](#what-each-jaws-manager-becomes-in-nvda)
- [Voices, voice profiles and voice aliases](#voices-voice-profiles-and-voice-aliases)
- [ClassicSpeech](#classicspeech)
- [Sounds](#sounds)
- [Keyboard commands](#keyboard-commands)
- [The assistant's own commands](#the-assistants-own-commands)
- [Add-ons: always the newest versions](#add-ons-always-the-newest-versions)
- [Backups and restoring](#backups-and-restoring)
- [JAWS is never changed](#jaws-is-never-changed)
- [Adapting to each computer](#adapting-to-each-computer)
- [Leasey](#leasey)
- [Updates](#updates)
- [Debug logs](#debug-logs)
- [Where things are kept](#where-things-are-kept)
- [Limits](#limits)
- [Building from source](#building-from-source)
- [Credits](#credits)

## What it does

1. **Checks the computer.** It finds every installed JAWS version, its build and languages, and your personal and shared JAWS settings. It also checks Windows, your copy of NVDA, the synthesizers and voices NVDA can use, and ClassicSpeech. If JAWS is not installed, an accessible message box says so; press OK and carry on with your day. If JAWS was uninstalled but its settings are still there, it offers to migrate those.
2. **Indexes all JAWS settings.** It catalogs every JAWS settings file, sound and synthesizer for the chosen JAWS version, by JAWS manager. Your personal settings are for the Windows user who is signed in. Shared settings apply to everyone on the computer.
3. **Lets you choose** your settings, the shared settings, or both, layered as JAWS layers them. It also lets you choose what to migrate, down to single settings, schemes, voice profiles, voice aliases and keyboard layouts, and where it goes.
4. **Migrates** into NVDA's normal configuration (recommended), or into a separate NVDA configuration profile.
5. **Backs up NVDA first**: its settings, every add-on and the add-ons' own settings. If anything goes wrong, the settings are put back automatically. You can restore any backup later, add-ons included.
6. **Writes a report** of everything that changed, everything kept for NVDA, and everything JAWS had that NVDA has no equivalent for, and a [detailed debug log](#debug-logs).

## Installing

1. Download `jawsMigrator-1.9.nvda-addon` from the [releases page](https://github.com/joshknnd1982/jawsMigrator/releases).
2. Press Enter on the file. NVDA asks you to confirm, installs the add-on and offers to restart.
3. A few seconds after NVDA starts, the assistant checks the computer once and offers to migrate. After that it only runs when you ask.
4. If [ClassicSpeech](#classicspeech) is not installed, the assistant offers to install it, in a dialog you can read line by line. It downloads ClassicSpeech's newest release from GitHub. If you install it, restart NVDA and open the assistant again, so your JAWS schemes, voice aliases and sounds can come over too. You can say not to be asked again, and install it later from the NVDA menu, Tools, JAWS Migration Assistant, Install or update ClassicSpeech.

## What's new in 1.9

A fix from a tester's report on version 1.8:

- **NVDA no longer reads a system tray icon over and over.** Programs keep the name of their system tray icon up to date. A temperature monitor shows your computer's temperatures there and changes them every few seconds, and the clock changes every minute. While the focus was on such an icon, NVDA read it again every time it changed. A tester's NVDA started with the focus on a temperature monitor's icon and kept saying "CPU 129.9 F; Drive C Temperature 113.0 F; ...", with new temperatures every few seconds, until the tester pressed Alt+Tab. Now NVDA says a system tray icon when you move to it, and NVDA+Tab reads it as it is now, but NVDA doesn't read it again when its program changes it. Braille still shows every change. If you press a key on the icon and the icon changes within a moment, NVDA says the change, once for each key press, because your key may have made it. This works on Windows 10 and Windows 11, for the programs' icons, the clock, the system's own icons and the hidden icons. To hear every change again, uncheck "Say a system tray icon when you move to it, not each time its program changes it" in NVDA's Settings, JAWS Migration Assistant.

NVDA itself reads every change of the icon that has the focus, with or without add-ons. The assistant keeps it to one reading while it is installed.

## What's new in 1.8

A fix from a tester's report on version 1.7, and a new setting:

- **"Checked" is said once.** When you press Space on a control in browse mode, NVDA says what changed as the focus moves to it. Then the control reports the same change itself, and NVDA said it again: on visible.com, whose payment options rewrite their label when they are checked, you heard "As low as $49.97/mo for 36 months 0% APR + taxes, checked", then "checked". Now NVDA says it once, for radio buttons, check boxes and any other control you activate in browse mode. Only a change NVDA has just said is left out, once, within a few seconds of saying it. If the control changes again, NVDA says so as usual, and braille still shows every change. This is part of "Say a control's type and state once, even when its label repeats them" in NVDA's Settings, JAWS Migration Assistant, and turns off with it.
- **A beep for NVDA+Shift+J, if you prefer one.** NVDA's Settings, JAWS Migration Assistant, has a new check box: "Play JAWS's layered keystroke sound for NVDA+Shift+J, instead of a beep". It is checked, so NVDA+Shift+J plays JAWS's layered keystroke sound, as it has since version 1.5. Uncheck it, and NVDA+Shift+J beeps. The assistant keeps its copy of JAWS's sound either way, so you can check the box again after JAWS is uninstalled.

## What's new in 1.7

- **The assistant always appears in NVDA's menus.** With version 1.5 it was missing from the NVDA menu's Preferences and Tools, from NVDA's Settings and from Input Gestures, because 1.5 didn't start (1.6 fixed that). The assistant now adds its menu items and its Settings category first as NVDA starts, and every other part of its start runs on its own. If one ever fails, it goes to the [debug log](#debug-logs), and NVDA menu, Preferences, JAWS Migration Assistant settings, the Tools submenu, the Settings category and NVDA+Shift+J keep working. So you can always open the assistant, restore a backup or read the debug log.
- **If you still have 1.5, install 1.7 yourself** from the [releases page](https://github.com/joshknnd1982/jawsMigrator/releases). Version 1.5 never started, so it can't check for updates.

## What's new in 1.6

- **The assistant starts again.** Version 1.5 didn't start in NVDA at all: the assistant was missing from the NVDA menu and from NVDA's Input Gestures dialog, and NVDA+Shift+J did nothing. Its new layered keystroke sound used a part of Python that NVDA's own copy of Python doesn't include. That is fixed, so everything 1.5 added now works. If one of the assistant's own features ever can't start, it is left out on its own, and the rest of the assistant keeps working.

## What's new in 1.5

- **NVDA says a control's type and state once.** Some web pages write what a screen reader says into a control's label. On visible.com, a payment option is labelled "As low as $49.97/mo for 36 months 0% APR + taxes, radio button checked 1 of 2", so NVDA said "radio button checked 1 of 2, radio button, checked". When NVDA says a control's type and state itself, the assistant now leaves the page's copy out of the label, and you hear "As low as $49.97/mo for 36 months 0% APR + taxes, radio button, checked". NVDA's own words are the ones kept, because they are right even when a page forgets to update its copy. This works for radio buttons, check boxes, buttons, combo boxes, edit fields, links, tabs and other controls, in browse mode, in focus mode and while reading line by line. A label that only ends in the control's type, such as a button labelled "Close button", is left as it is. To turn this off, uncheck "Say a control's type and state once, even when its label repeats them" in NVDA's Settings, JAWS Migration Assistant.
- **NVDA+Shift+J sounds like JAWS's layered keystrokes.** When NVDA+Shift+J starts the assistant's commands, NVDA now plays the sound JAWS plays when a layered keystroke such as Insert+Space starts: KeyLayerSound.wav, or the sound you chose for it in JAWS. The assistant keeps a copy, so the sound stays after JAWS is uninstalled. If JAWS plays no sound there, or none is found, NVDA+Shift+J beeps as before.

Saying a control's type and state once works while the assistant is installed; NVDA itself has no such setting.

## What's new in 1.4

Fixes from a tester's report on version 1.3:

- **No sound when NVDA exits.** With Screen Curtain on, NVDA turns it off as it exits, which played the Screen Curtain off sound (through ClassicSpeech, JAWS's Screen Shade sound). JAWS plays no sound when it exits, so after a migration the assistant leaves that sound out while NVDA exits. Turning Screen Curtain off yourself still plays it.
- **Insert+J opens the NVDA menu on the Laptop layout.** In JAWS's Laptop layout, Caps Lock is the JAWS key, but some Insert keystrokes do something else than the Caps Lock ones: Insert+J opens the JAWS window while Caps Lock+J says the previous word. NVDA calls both NVDA+J, so the assistant now runs the Insert command itself when you hold Insert. With JAWS 2026 that is Insert+J (the NVDA menu), and Insert+H and Insert+8 (NVDA's Input Gestures dialog, which lists and changes keystrokes). Migrations made with 1.3 get these once, a little after NVDA starts. Keystrokes other add-ons use are now taken into account too, so the report no longer promises a keystroke another add-on answers first.
- **Times are read as times.** JAWS has a rule of its own for a colon between digits, as in 6:02 PM: it is only spoken at the All punctuation level. NVDA said "6 colon 02" at its Most level. The assistant now gives NVDA the same rule, so the synthesizer reads the time as it does in JAWS.
- **Eloquence speaks at your JAWS speed.** JAWS keeps Eloquence's own speed as its rate, and NVDA's Eloquence drivers start their range higher, so the same percentage was faster in NVDA: a JAWS rate of 75% became NVDA's 75, about 10% faster than JAWS. The rate now keeps JAWS's speed (75% in JAWS is 65 with the Eloquence add-on, 61 with IBMTTS). A rate set by versions 1.0 to 1.3 is corrected once, after a backup, unless you changed it since.
- **Restoring says what you'll notice.** Restoring the backup from before your first migration brings NVDA's own behaviour back, such as saying "clickable" before clickable items on web pages. That is NVDA's Document Formatting setting "Clickable", not ClassicSpeech or the assistant. Before restoring, the assistant now lists the changes you will notice, such as "clickable", the punctuation level and the speech rate, and where to change each one.

The Insert keystrokes, the time rule and the silent exit work while the assistant is installed; NVDA itself has no way to keep them.

## Using the assistant

Open it from the NVDA menu: Tools, JAWS Migration Assistant, Migrate JAWS settings to NVDA. Or press NVDA+Shift+J, then M.

The assistant is a single dialog with Back, Next and Cancel buttons. Each step is a labeled group. NVDA says the step name and puts you on the step's first control. Long text is in read-only boxes you can read line by line. Nothing changes until you press Migrate on the last step.

1. **System check.** What was found on this computer. Choose the JAWS version and settings language if there is more than one.
2. **Which JAWS settings.** Your settings and the shared settings (recommended), only yours, or only the shared ones.
3. **What was found.** A summary of every JAWS manager's files and entries, JAWS's synthesizers and their NVDA equivalents, and whether Eloquence or IBM ViaVoice is available. The View the full index button shows every file.
4. **Choose what to migrate.** A checklist with counts: Settings Center, voices, application profiles, sleep mode applications, dictionaries, punctuation, keyboard commands, and the archive. If you saved a choice in [JAWS Migration Assistant settings](#choosing-what-to-import), the step says so and starts from it.
5. **Where the JAWS settings go.** NVDA's normal configuration (recommended), or a separate profile. NVDA's settings are backed up first either way. A separate profile is only on while nothing else replaces it: NVDA can have one profile turned on by hand at a time, and add-ons such as Custom Browse Mode turn on their own, which switches the JAWS profile off, so speech and verbosity change back and forth. Settings you change while the profile is on also go into it.
6. **Voices.** Which NVDA synthesizer and voice replaces your JAWS voice, and which JAWS voice profiles to migrate.
7. **ClassicSpeech** (only when it is installed). Which JAWS speech and sound schemes to copy, which one to turn on (none, unless you choose one), and whether to copy the JAWS cursor and message voices as Voice Profiles, and verbosity, number and text settings.
8. **Sound effects** (only when ClassicSpeech is installed). Whether JAWS sounds play in place of NVDA's sounds, with the list of which JAWS sound replaces which NVDA sound, and whether to copy every JAWS sound into ClassicSpeech.
9. **Keyboard commands.** Whether JAWS keystrokes become NVDA input gestures, which [JAWS keyboard layouts](#keyboard-layouts) to bring over (desktop, laptop and so on), NVDA's keyboard layout afterwards, whether to use JAWS quick navigation letters in browse mode, and whether JAWS keystrokes may replace NVDA's own. The list shows every keystroke that will be added.
10. **Add-ons.** ClassicSpeech and the five recommended add-ons: which to install, what each does, and what happens if you don't. Add-ons you already have are updated to their newest versions, unless you uncheck them. See [Add-ons: always the newest versions](#add-ons-always-the-newest-versions).
11. **Ready to migrate.** A summary of what will happen. Press Migrate.

Every checklist in the assistant has Select all and Select none buttons.

Progress is spoken as it happens. The last step shows the result. It has buttons to open the report, open the folder with the migration's files, and restart NVDA when a restart is needed.

## Choosing what to import

To pick exactly which JAWS items come over, open the NVDA menu, Preferences, JAWS Migration Assistant settings. You can also press NVDA+Shift+J then O, use the NVDA menu, Tools, JAWS Migration Assistant, Choose what to import, or use the button in NVDA's Settings, JAWS Migration Assistant.

The dialog reads your JAWS settings, which takes a few seconds, and lists every item with a check box:

- **JAWS settings (Settings Center):** each option that has an NVDA equivalent, with the JAWS file and option it comes from.
- **Speech and sound schemes:** each scheme, with its number of sounds and voices.
- **Voice profiles:** each JAWS voice profile and the NVDA synthesizer it becomes.
- **Voice aliases:** each alias (LinkVoice, HeadingLevel1Voice, the Rent-A-Crowd aliases...) with what it does in each voice profile.
- **Keyboard settings and layouts:** keyboard options such as typing echo, the NVDA key and the keyboard layout, JAWS keystrokes as NVDA gestures, each [JAWS keyboard layout](#keyboard-layouts), and quick navigation letters.
- **Dictionaries, punctuation, sounds and applications:** your dictionary rules, Freedom Scientific's rules, punctuation, JAWS sounds in place of NVDA's, all JAWS sounds copied into ClassicSpeech, ClassicSpeech voices and settings, the archive, each application's profile, and each application where NVDA should sleep.

The dialog's controls:

| Control | What it does |
| --- | --- |
| Show | Lists everything, or one kind of item |
| Items to import | Check the items you want; Space checks or unchecks one |
| Select all, Select none | Check or uncheck every item shown, so a whole kind can be turned on or off at once |
| Import the selected items now | Saves your choice and opens the migration assistant |
| Check for updates | Looks for a newer version of the assistant on GitHub |
| Open NVDA's Input Gestures dialog | Opens NVDA's Input Gestures dialog, to see or change keystrokes |
| Save and close | Saves your choice |
| Close without saving | Closes; if you changed anything, asks whether to save it |

Items this computer can't use (for example a voice profile for a synthesizer NVDA doesn't have, or schemes when ClassicSpeech isn't installed) say why and can't be checked. The choice is saved and used by every migration. Items that appear later, for example after you change JAWS, are imported unless you turn them off. The dialog never changes NVDA or JAWS; only a migration does.

## What each JAWS manager becomes in NVDA

| JAWS manager | What happens |
| --- | --- |
| Settings Center (`.jcf`) | Every option with an NVDA equivalent is set to what JAWS does (details below this table). Examples: typing echo, keyboard layout and NVDA key, speech interruption, screen echo (dynamic content), language switching, phonetic reading after a pause, capitals, verbosity (access keys, tooltips, position information), progress bars, mouse echo, touch typing, audio ducking. Also browse mode (simple layout, line length, lines per page, Say All on page load, forms mode, audio indication), document formatting (headings, lists, tables, landmarks, links, graphics, table headers and coordinates, font attributes) and braille (mode, word wrap, cursor shapes and blink rate, messages, scroll rate, English braille tables). |
| Settings for one application (`.jcf` for that program) | An NVDA configuration profile named "JAWS - program" that turns on in that program, when it holds settings that differ from NVDA's normal configuration. A trigger you already have for that program is kept. Settings for web sites and parts of Windows, which can't turn a profile on, are listed in the report. Empty "JAWS - program" profiles an earlier version left are removed. |
| Sleep mode in an application | NVDA sleeps in that application too. You can change this in NVDA's Settings, JAWS Migration Assistant. |
| Quick Settings (`.qs`, `.qsm`) | Quick Settings saves into the application's `.jcf`, which is migrated as above. |
| Voice profiles (`.vpf`) | See [Voices](#voices-voice-profiles-and-voice-aliases). |
| Speech and Sounds Manager (`.smf`) | ClassicSpeech Speech and Sound Schemes. See [ClassicSpeech](#classicspeech). |
| Dictionary Manager (`.jdf`) | NVDA speech dictionary entries (details below this table). |
| Punctuation (`.sbl`) | Symbols you changed become NVDA symbol pronunciations, at the NVDA level where JAWS spoke them. You can also choose JAWS's names for every symbol. |
| Keyboard Manager (`.jkm`) | NVDA input gestures for JAWS commands NVDA also has. See [Keyboard commands](#keyboard-commands). |
| Navigation Quick Keys | NVDA browse mode quick navigation letters, when you choose JAWS letters. |
| Mark Colors in Braille | NVDA's font attribute reporting includes braille when JAWS marked bold, italic or underline. |
| Skim Reading Tool | Skim reading rules are archived. NVDA's "Allow skim reading in Say All" is left as it is: JAWS's AllowRapidSkimRead only says whether a document can be read in full at once. |
| Window Class Reassign | Archived and listed. Enhanced Control Support from the Add-on Store adds support for more controls. |
| Prompt Create and custom labels | Archived and listed. Custom Labels from the Add-on Store lets you label controls in NVDA. |
| Graphics Labeler (`.jgf`) | Archived. NVDA cannot recognize graphics by their pixels. |
| Frame Viewer (`.jff`, `.jfd`) | Archived. NVDA reports changing content through its dynamic content setting. |
| Custom Highlight Assign | Archived. NVDA has no color-based highlight detection. |
| Customize List View | Archived. NVDA reads all list columns. |
| Flexible Web (`FlexibleWeb.db`) | Archived. Custom Browse Mode from the Add-on Store can switch profiles in browse mode. |
| Research It | Options and rules archived. |
| Commands Search | Archived. NVDA's Input Gestures dialog has a filter box. |
| Message Center | Nothing to migrate (Freedom Scientific news). Archived. |
| Notification History | Archived. Custom Notifications from the Add-on Store chooses how notifications are read. |
| Script Manager (`.jss`, `.jsb`, `.jsh`, `.jsd`, `.jsm`) | JAWS scripts cannot run in NVDA. Your scripts are archived and listed in the report, with the commands they add. |

Settings Center options in more detail:

- With your settings and the shared settings (the recommended choice), NVDA is set to what JAWS does as it runs, your changes layered over the shared settings. Where an older JAWS has no entry for something at all, JAWS's own default is used.
- Browse mode announcements follow JAWS's web verbosity level (Low, Medium or High) and its table of what each level announces. At Medium, JAWS's default, JAWS doesn't say "clickable", so NVDA's "Report if clickable" is turned off. Frames, banners and other items JAWS leaves out at your level are left out in NVDA too.
- Font names, font sizes, colors and attributes follow the speech and sounds scheme JAWS uses, as JAWS itself does. JAWS's default scheme, Classic, announces none of them. JAWS's old Format and Text options are no longer used by JAWS and are listed in the report.
- With only your settings, NVDA changes only what you changed in JAWS. If you changed a verbosity level, everything that level decides comes over.
- A few JAWS defaults would hide information NVDA gives, such as object descriptions, which JAWS gives through its tutor messages. Those only come over when you changed them in JAWS.
- JAWS plays no sound when it starts or exits, so NVDA's "Play sounds when starting or exiting NVDA" is turned off.

Dictionary rules in more detail:

- Plain words become whole-word entries in NVDA's default dictionary.
- JAWS root words such as `reposition*` keep matching every word that starts with the root.
- Rules for another language are left out.
- Rules for one synthesizer go into NVDA's voice dictionary for the voice you migrate to.
- Rules that only play a sound are listed, because NVDA dictionaries cannot play sounds.
- Freedom Scientific's own rules are only added if you ask.

## Voices, voice profiles and voice aliases

The assistant reads every JAWS voice profile, yours and the shared ones. Your changes are layered over JAWS's defaults, as JAWS does. Each profile's contexts are read: Global, PC cursor, JAWS cursor, keyboard, menus and dialogs, and messages.

- **Your JAWS voice** becomes NVDA's voice. The assistant looks for the NVDA synthesizer that speaks the same voices. It prefers a native NVDA add-on driver, such as IBMTTS for Eloquence, then matching SAPI 5 or OneCore voices, in your JAWS language. Eloquence and IBM ViaVoice are looked for both as NVDA add-ons and as SAPI 5 voices. JAWS person names (Reed, Shelley, Glen, Rocko, Grandma and the others) select the matching voice or variant.
- **Rate, pitch and volume** come from your JAWS voice profile's Global voice, as the percentage JAWS shows for them, so a JAWS rate of 64% becomes an NVDA rate of 64. JAWS keeps them in each synthesizer's own units (Eloquence rate 95 is 64%, SAPI 5 uses 0 to 20, DECtalk words per minute...). They are set once, in NVDA's voice settings, and from then on only you change them: nothing the assistant writes speeds speech up or slows it down in some places.
- **Eloquence's rate keeps JAWS's speed**, not its percentage: JAWS's Eloquence rate is Eloquence's own speed, and NVDA's Eloquence drivers (IBMTTS, and the Eloquence add-on) give their 0% a speed of 40, so the same percentage is faster in NVDA. JAWS's 75% (speed 111) becomes 65 with the Eloquence add-on and 61 with IBMTTS. Versions 1.0 to 1.3 used the percentage; such a rate is corrected once after updating, after a backup, unless you changed it since.
- **Punctuation level** and **capital pitch change** are migrated too. JAWS's rule for a colon between digits comes along: in a time such as 6:02 PM the colon is only spoken at the All level, so the synthesizer reads the time as a time. NVDA lists the rule in its Punctuation/symbol pronunciation dialog as "colon between digits, as in 6:02", where you can change it.
- **Every other voice profile** with an NVDA synthesizer on this computer is saved as that synthesizer's NVDA settings. When you switch NVDA to it later, your JAWS settings for it are already there.
- **Voice aliases** (for example HeadingLevel1Voice, LinkVoice, QuotationVoice, and the Rent-A-Crowd aliases) are migrated into ClassicSpeech, as described next. An alias that only changes pitch or rate is not a different voice there, so it keeps your NVDA voice.

## ClassicSpeech

When [ClassicSpeech](https://github.com/joshknnd1982/classicspeech-nvda) is installed, the assistant also copies these into it, in ClassicSpeech's own formats:

- **Voice Profiles**, only if you choose them. Each JAWS context whose voice is a different person becomes a ClassicSpeech category, with that person only; rate, pitch and volume always stay yours:
  - JAWS cursor becomes Review and object navigation, and Mouse.
  - JAWS messages become System and notifications.
  - PC cursor becomes Focus and navigation, and keyboard becomes Keyboard entry, but only if JAWS used another person there; usually they speak in your own voice, so they are left out.
  - This is done for every migrated voice profile's NVDA synthesizer.
- **Speech and Sound Schemes.** Every JAWS scheme becomes a ClassicSpeech scheme with its sounds, including SayAll Text With Sounds, Web RentACrowd, ProofReading and your own schemes:
  - JAWS control types become NVDA roles, including heading levels and landmarks.
  - JAWS control states become NVDA states.
  - Text attributes become formatting items (bold, italic, spelling errors, revisions, comments...).
  - A voice is only given where ClassicSpeech uses it as JAWS does. When JAWS only speaks its announcement in another voice (such as "link" in the message voice, in the Classic scheme), the text is not read in that voice, and the report says so. When JAWS reads the text itself in another voice (links and headings in Web RentACrowd, attributes in the ProofReading schemes), so does ClassicSpeech.
  - Sounds are copied with the scheme. The "clickable" sound is left out: ClassicSpeech would play it on every link.
  - Compressed JAWS sounds are converted so NVDA can play them.
  - No scheme is turned on unless you choose one; then ClassicSpeech keeps speaking and sounding as it does. You choose on every migration, and the scheme JAWS uses is marked in the list.
- **Voice aliases.** Each alias becomes a ClassicSpeech voice for every migrated synthesizer:
  - The alias's person becomes the matching NVDA voice or variant. Rate, pitch and volume are never stored, so speech keeps the rate, pitch and volume you set in NVDA everywhere.
  - An alias whose person is your own voice, or that only changes pitch or rate, is left out.
  - Aliases list fallbacks after a semicolon, and the first person the NVDA synthesizer has is used, as JAWS does.
  - Rent-A-Crowd's links, headings and quotations keep their different voices.
  - A "JAWS voice aliases" scheme gives every alias its natural item, even aliases no JAWS scheme used. JAWS itself uses an alias only where a scheme says so, so turn this scheme on only if you want that.
- **Verbosity, number and text processing.** JAWS Beginner, Intermediate and Advanced verbosity become ClassicSpeech's verbosity profiles. Number processing, single digits, currency, dates, mixed case, repeated characters and new line announcements are also copied.

Each migration also saves `.classicspeech-voices` and `.classicspeech-scheme` files. ClassicSpeech's Import buttons can bring those into ClassicSpeech on another computer.

Versions 1.0 to 1.2 of the assistant stored rate, pitch and volume in ClassicSpeech's voices, which made speech speed up, slow down or change pitch in places (on radio buttons, for example). Version 1.3 repairs those voices once, a little after NVDA starts, after backing up NVDA's settings: each keeps only its person, and ClassicSpeech Voice Profiles that only held a copy of your voice are removed.

Without ClassicSpeech, everything NVDA itself supports is migrated. The report lists what ClassicSpeech would add. The assistant offers to install ClassicSpeech when it opens, and whenever you ask for something that needs it.

## Sounds

JAWS sounds play through [ClassicSpeech](https://github.com/joshknnd1982/classicspeech-nvda). Without ClassicSpeech, NVDA keeps its own sounds; the assistant offers to install ClassicSpeech instead of changing anything.

### Every JAWS sound in ClassicSpeech

The assistant can copy every JAWS sound it finds (`.wav`, your own and the shared ones) into ClassicSpeech, as a scheme named "JAWS Sounds (from JAWS)":

`%APPDATA%\nvda\ClassicSpeech\Schemes\JAWS Sounds (from JAWS)\Sounds`

Sounds JAWS keeps compressed are converted so NVDA can play them. Where you have your own copy of a JAWS sound, yours is used, as in JAWS. The scheme changes nothing by itself; its sounds are at hand in ClassicSpeech's Speech and Sound Schemes, for any item. Copying again later keeps what you set up in the scheme.

Do it in the migration's Sound effects step, or at any time with NVDA+Shift+J then A, or NVDA menu, Tools, JAWS Migration Assistant, Copy all JAWS sounds into ClassicSpeech.

### JAWS sounds in place of NVDA's

NVDA plays its own sounds when you switch between focus and browse mode, and for other events. The assistant can have JAWS sounds play instead:

| NVDA sound | JAWS sound used |
| --- | --- |
| Switching to browse mode | Leaving forms mode (boink1, or the sound you chose in JAWS) |
| Switching to focus mode | Entering forms mode (boink2, or your choice) |
| Spelling error | Proofing error (BuzzerShort, or your choice) |
| Auto-suggestions appear and close | Auto-complete list opens and closes |
| Screen curtain on and off | Screen Shade blinds down and up |
| Remote Access connected, controlled, joined and disconnected | Tandem connect and disconnect (or your choice) |
| Error written to the NVDA log | Error buzzer |

JAWS plays no sound when it starts or exits, so NVDA's start and exit sounds are turned off (Play sounds when starting or exiting NVDA, in NVDA's General settings). Restoring NVDA's own sounds turns them on again if they were on before. JAWS has no sounds for the Remote Access clipboard, so NVDA keeps its own for those.

With Screen Curtain on, NVDA also turns the curtain off as it exits, which plays the Screen Curtain off sound. While the start and exit sounds are off after a migration, the assistant leaves that one out as NVDA exits; turning the curtain off yourself still plays it. NVDA turns the curtain on as it starts, before add-ons load, so its own Screen Curtain on sound still plays then; turn off "Play sound when toggling Screen Curtain" in NVDA's Vision settings if you don't want it.

To switch quickly, press NVDA+Shift+J then S. The first press plays JAWS sounds; the next restores NVDA's own. The same actions are in NVDA menu, Tools, JAWS Migration Assistant (Use JAWS sounds in place of NVDA's sounds, and Restore NVDA's own sounds), and in NVDA's Settings, JAWS Migration Assistant. The migration's Sound effects step does it too.

How it works, and how to go back:

- ClassicSpeech plays a scheme's "NVDA sound" items in place of NVDA's own sounds. The assistant gives every ClassicSpeech scheme the JAWS sounds, each copied into that scheme's own Sounds folder, so the JAWS sounds play whichever scheme is active. A sound you already chose for an item in a scheme is left as it is. If ClassicSpeech's speech and sound schemes were off, they are turned on, since the sounds need them.
- NVDA's own sound files, in NVDA's program folder, are never changed. Before the JAWS sounds go in, a copy of NVDA's own sounds is kept in `jawsMigrator\nvdaSounds`, and NVDA's settings, add-ons and add-on settings are backed up.
- Restore NVDA's own sounds takes out exactly what the assistant added, and turns ClassicSpeech's schemes off again if the assistant had turned them on. Sounds you changed in ClassicSpeech since are left as you set them. The JAWS sounds copied into "JAWS Sounds (from JAWS)" stay.
- Restoring a backup also puts everything back as it was.

Some NVDA sounds only play when their NVDA option is on. For example, focus and browse mode sounds need "Audio indication of focus and browse modes" in NVDA's Browse Mode settings. NVDA plays the logged error sound only in its test versions, unless you change that in its Advanced settings.

Version 1.1 of the assistant played JAWS sounds by itself. In 1.2 they play through ClassicSpeech, and 1.1's way is turned off. If you used it, turn JAWS sounds on again with NVDA+Shift+J then S.

## Keyboard commands

The assistant reads JAWS's default key map and turns keystrokes for commands NVDA also has into NVDA input gestures. It uses both your changes and the shared key map. Examples:

- Reading the current line, word or character, Say All, and reading sentences.
- The window title, status line, focus, time and date.
- The elements list and the Find commands.
- Reading table rows and columns.
- Speech rate and punctuation level.

### Keyboard layouts

JAWS has a keyboard layout for each kind of computer keyboard. Each layout adds its own keystrokes to the ones all layouts share. The assistant finds the layouts in your JAWS key map and lets you choose which to bring over. Its keystrokes become gestures of the matching NVDA keyboard layout, so they work whenever NVDA uses that layout:

| JAWS layout | JAWS key | NVDA keyboard layout |
| --- | --- | --- |
| Desktop | Insert | Desktop |
| Laptop | Caps Lock | Laptop |
| Classic Laptop (the older Alt+letter layout) | Insert | Laptop |
| Kinesis | Insert | Desktop |

Layouts of other JAWS versions and languages are found the same way. Freedom Scientific notetaker layouts (PAC Mate) are left out.

- The layout your JAWS uses is chosen at first. Choose more to have your JAWS keystrokes on another kind of keyboard too. For example, choose Desktop and Laptop if you switch NVDA between them.
- When two chosen JAWS layouts put different commands on the same keystroke for the same NVDA layout, the layout your JAWS uses wins. The report lists the others.
- NVDA's keyboard layout follows the JAWS layout you used, or the layouts you chose. You can also pick Desktop, Laptop, or keep NVDA's current layout.
- Caps Lock becomes an NVDA key when the Laptop layout's keystrokes come over, as it was the JAWS key there. The Insert keys follow your JAWS key setting.
- Classic Laptop uses Alt with letters, which takes those keystrokes away from programs. Choose it only if you used it in JAWS.

### Everything else about keystrokes

- Before any gesture is added, gestures.ini is backed up.
- Each keystroke is decided separately for NVDA's desktop and laptop keyboard layouts, so a keystroke only gets a command in the layouts where it is free or the same.
- On the Laptop layout, where Caps Lock is the JAWS key, Caps Lock keystrokes decide what NVDA+key does in gestures.ini, because NVDA calls both keys NVDA+key there. For example, Caps Lock+H and Caps Lock+J don't open NVDA's Input Gestures dialog or menu.
- Where JAWS's Laptop layout gives the Insert keystroke another command, the assistant runs it itself when you hold Insert, as NVDA can tell which key you hold. With JAWS 2026: Insert+J opens the NVDA menu, and Insert+H and Insert+8 open NVDA's Input Gestures dialog. The report lists them. Assign the keystroke to something else in NVDA's Input Gestures dialog and Insert runs your choice.
- Keystrokes that other add-ons use count as taken: NVDA asks add-ons first, so a gesture on the same keystroke would never run. Choosing to use the JAWS command anyway also takes the keystroke from the add-on.
- The report and the wizard say when a keystroke only works in one of NVDA's keyboard layouts, such as "NVDA+j, only in NVDA's desktop keyboard layout".
- Keystrokes NVDA already uses for the same command are left alone.
- Keystrokes NVDA uses for something else stay NVDA's, unless you choose otherwise. That includes JAWS's browse mode keystrokes such as Control+Insert+R: NVDA+Control+R still reloads NVDA's settings.
- JAWS quick navigation letters can be used in browse mode, so R moves to regions and A to radio buttons, as in JAWS.
- No JAWS keystroke gets an NVDA command that passes the keystroke on to the program. In edit fields, NVDA's sentence commands do that, so Caps Lock+Y would type a Y; those JAWS keystrokes only work in browse mode.
- Versions 1.0 to 1.2 added some keystrokes that do such things. Version 1.3 removes them once, a little after NVDA starts, after backing up NVDA's settings; keystrokes you added yourself are left alone.
- Layered keystrokes (such as INSERT+SPACE, then a letter) and braille display keys are listed in the report. NVDA has no layered keys of its own.
- Application key maps and JAWS-only commands are listed too.

To learn NVDA, use the JAWS keystroke helper: press NVDA+Shift+J, then K, then a JAWS keystroke. NVDA tells you:

- what that keystroke did in JAWS, from JAWS's own documentation;
- the NVDA command that does the same, and its keystroke;
- what the keystroke now does in NVDA.

## The assistant's own commands

Press NVDA+Shift+J, then:

| Key | Command |
| --- | --- |
| M | Open the JAWS Migration Assistant |
| O | JAWS Migration Assistant settings: choose which JAWS items to import |
| G | Open NVDA's Input Gestures dialog |
| P | Turn the JAWS settings profile on or off |
| K | JAWS keystroke helper: hear what a JAWS keystroke does in NVDA |
| S | Play JAWS sounds in place of NVDA's sounds, or restore NVDA's own (needs ClassicSpeech) |
| A | Copy all JAWS sounds into ClassicSpeech |
| R | Open the last migration report |
| B | Restore NVDA settings from a backup |
| U | Check for updates |
| C | Install ClassicSpeech, or update it to its newest version |
| I | Hear the JAWS, Windows and NVDA versions on this computer |
| H or F1 | List these commands |

Any other key, or Escape, leaves the layer. Every command is also in NVDA's Input Gestures dialog, under JAWS Migration Assistant, where you can give it its own keystroke. NVDA+Shift+J itself can be changed there too.

NVDA+Shift+J plays the sound JAWS plays when a layered keystroke such as Insert+Space starts. That is the sound JAWS's Default.jcf names (KeyLayerSound.wav, unless you chose another), found in your JAWS sounds and then in the shared ones, as JAWS finds it. It comes from the JAWS you migrated from, or else the newest JAWS on the computer. The assistant keeps a copy in its own folder, so the sound stays after JAWS is uninstalled. If JAWS plays no sound there, or none is found, NVDA+Shift+J beeps. To hear the beep in place of JAWS's sound, uncheck "Play JAWS's layered keystroke sound for NVDA+Shift+J, instead of a beep" in NVDA's Settings, JAWS Migration Assistant.

The NVDA menu, Tools, JAWS Migration Assistant has the same actions, plus Open the debug log, and the NVDA menu, Preferences, has JAWS Migration Assistant settings. The JAWS Migration Assistant category of NVDA's Settings dialog has buttons to choose which JAWS items to import, open NVDA's Input Gestures dialog, use JAWS sounds in place of NVDA's, restore NVDA's own sounds, copy all JAWS sounds into ClassicSpeech, open the assistant, restore a backup, open the last migration report and check for updates. It also says whether JAWS sounds or NVDA's own are playing. That category also has:

- automatic update checks;
- turning on the JAWS settings profile when NVDA starts;
- saying a control's type and state once, even when its label repeats them, and a change once when you activate a control in browse mode (on unless you turn it off; see [What's new in 1.5](#whats-new-in-15) and [What's new in 1.8](#whats-new-in-18));
- saying a system tray icon when you move to it, not each time its program changes it (on unless you turn it off; see [What's new in 1.9](#whats-new-in-19));
- playing JAWS's layered keystroke sound for NVDA+Shift+J, or a beep (JAWS's sound unless you uncheck it);
- the list of applications where NVDA sleeps.

## Add-ons: always the newest versions

The assistant uses ClassicSpeech, and recommends five add-ons from NVDA's Add-on Store. Whenever it installs one, it gets the newest version at that moment: ClassicSpeech's newest release from [its GitHub page](https://github.com/joshknnd1982/classicspeech-nvda) (ClassicSpeech is not in the Add-on Store), and the newest stable version for your NVDA from the Add-on Store. Nothing is installed from an old copy.

The migration's Add-ons step lists each one:

- **Not installed:** a check box to install it, with what it does and what happens if you don't install it.
- **Installed:** a check box, checked, to update it to its newest version. If it is already the newest, or newer, it is left as it is.
- **Turned off, or being removed:** left as it is, and the step says so.

| Add-on | What it adds | Without it |
| --- | --- | --- |
| ClassicSpeech | Speech and sound schemes, voices for voice aliases, JAWS sounds and verbosity, like JAWS's Speech and Sounds Manager | Your JAWS schemes, voice aliases and sounds don't come over, and NVDA keeps its own sounds |

| Add-on | What it adds | Without it |
| --- | --- | --- |
| Enhanced Control Support | Support for controls NVDA does not recognize, like JAWS Window Class Reassign | Controls JAWS read only because of a reassignment may be silent or "unknown" in NVDA |
| Custom Labels | Your own labels for unlabeled controls, like JAWS Prompt Create and custom labels | Controls you named in JAWS are read without your names; the report lists them |
| Custom Browse Mode | An NVDA profile that turns on in browse mode, like JAWS's separate web settings | Browse mode uses the same settings as everything else, as NVDA normally does |
| Custom Notifications | How notifications are read: full text, just the application, speech or braille | NVDA keeps reading every notification in full |
| Control Usage Assistant | Tells you how to use the control you are on, like JAWS's screen-sensitive help (Insert+F1); for people new to computers, Windows or NVDA | You look up how to use a control in NVDA's user guide |

The add-ons you choose are, after the migration and its backup:

1. looked up: ClassicSpeech's newest GitHub release, or the newest stable Add-on Store version that works with your NVDA;
2. compared with the version you have, so only a missing or older add-on is downloaded;
3. downloaded and checked against the published SHA-256 checksum, and checked to be the add-on it claims to be;
4. installed with NVDA's own installer, which replaces an older version and keeps its settings.

They start, or switch to the new version, after NVDA restarts. To install or update ClassicSpeech at any other time, use the NVDA menu, Tools, JAWS Migration Assistant, Install or update ClassicSpeech, or press NVDA+Shift+J then C; NVDA's settings are backed up first.

## Backups and restoring

Before every migration, and before every restore, the assistant backs up NVDA's whole settings folder:

- nvda.ini, gestures.ini and profileTriggers.ini, with the settings add-ons keep in nvda.ini;
- every configuration profile, speech dictionary and user symbol file;
- ClassicSpeech's settings and schemes;
- every installed add-on, including ones waiting for a restart;
- the settings and data add-ons keep in their own files and folders, such as downloaded voices;
- NVDA's record of which add-ons are enabled or disabled;
- the assistant's own record of sounds and sleeping applications;
- NVDA's own sound files.

Left out is only what NVDA downloads or builds again by itself: the Add-on Store's cache, NVDA update downloads and compiled Python files. The assistant's own add-on and backups aren't copied into backups.

The first backup copies everything, which can take a minute and a few gigabytes when many add-ons are installed. Later backups share every unchanged file with the previous one (as a hard link), so they take seconds and almost no space. The wizard's last step says how much will be copied. If the disk doesn't have room, nothing is migrated.

If the migration fails, the backup is put back and NVDA reloads its saved settings, so NVDA is left as it was.

To undo a migration later, open the NVDA menu, Tools, JAWS Migration Assistant, Restore NVDA settings from a backup, or press NVDA+Shift+J then B. Choose a backup and press Restore. Before restoring, the assistant tells you what will happen to each add-on, and what you will notice: with a backup from before your first migration, NVDA behaves as it did then, for example saying "clickable" before clickable items on web pages, with its own punctuation level and speech rate. Each one says where it is set, so you can change it after the restore. Uninstalling the assistant doesn't change NVDA's settings back or forth. Then:

1. Your current settings and add-ons are backed up first, so a restore can be undone too.
2. Settings files that changed are put back, each checked against the backup's SHA-256 first. Files the migration created, such as the JAWS settings profile and the ClassicSpeech schemes, are removed.
3. Add-ons go back the way NVDA itself installs and removes them. Add-ons installed after the backup, such as the recommended ones, are removed. Add-ons that were removed or updated since are reinstalled from the backup. Each add-on is enabled or disabled as it was, and add-on settings are put back.
4. NVDA reloads its settings. It offers to restart, which finishes putting back the add-ons.

The backup made before your first migration is kept for good, as your NVDA before any JAWS migration. Of the others, the fifteen newest are kept. Backups made by version 1.0 hold NVDA's settings only; restoring one leaves add-ons as they are.

## JAWS is never changed

- JAWS files are only ever opened for reading.
- Every file the assistant writes goes through a check that refuses any location inside a JAWS program or settings folder. So even a mistake in the assistant cannot change JAWS.
- The assistant does not uninstall, update or reconfigure JAWS, and does not stop JAWS if it is running.
- Your JAWS settings stay where they are. A copy is also kept with NVDA's settings.

When the migration finishes, the assistant tells you that you can now uninstall JAWS yourself if you wish, from Windows Settings, Apps, Installed apps. You might keep JAWS for a while to compare, or for programs you still need it for.

## Adapting to each computer

Nothing about the computer is assumed. The System Check reports, and the migration adapts to:

- **Windows:** version, build and architecture (x64 or ARM64), and roaming or redirected profiles.
- **NVDA:** version, and whether it is an installed, portable or Microsoft Store copy. Also whether its settings folder can be written, the free disk space, secure screens, and existing profiles.
- **JAWS:**
  - every version found in the registry or on disk (JAWS 18 and later, including several side by side);
  - settings left behind by an uninstalled JAWS;
  - every settings language (enu, deu, fra, esn...);
  - whether JAWS is running;
  - personal and shared settings folders, including missing or unreadable ones;
  - files in UTF-8, UTF-16 or the Windows code page.
- **Speech:** every synthesizer NVDA can load, and every SAPI 5 voice (32-bit and 64-bit, including voices SAPI makes up at run time), OneCore voice and Speech Platform voice.
- **Add-ons:** ClassicSpeech and the recommended add-ons, including disabled ones and ones waiting for a restart.

## Leasey

If Hartgen Consultancy's Leasey is installed, the assistant ignores all Leasey settings. Leasey is detected from:

- its entry in Add or Remove Programs;
- its program and data folders;
- Leasey files in the JAWS settings.

Leasey files, settings sections and keystrokes are left out of the migration and the archive, and the report says what was found.

## Updates

The assistant checks [its GitHub releases](https://github.com/joshknnd1982/jawsMigrator/releases) for a newer version at most once a day, a little after NVDA starts. It only speaks up when there is one. You can also check any time with NVDA+Shift+J then U.

The update dialog shows the release notes in a box you can read line by line. It offers to download the new version. The download must match the release's SHA-256 checksum. NVDA's own installer then asks you to confirm, installs it, keeps your settings, backups and reports, and offers to restart. This is the same updater ClassicSpeech uses. Automatic checks can be turned off in NVDA's Settings, JAWS Migration Assistant.

## Debug logs

For finding problems, the assistant keeps detailed logs:

- `jawsMigrator\debug.log`: what the assistant did outside migrations, such as repairs, sounds and add-on installs, and any errors. NVDA menu, Tools, JAWS Migration Assistant, Open the debug log opens it.
- `debug.log` in each migration's folder: every step of that migration. It lists the JAWS values read (rates in JAWS's own units, voice aliases, the web verbosity level...), the NVDA and ClassicSpeech settings written and where, each scheme item and voice decision, the keystrokes, the add-ons installed, and any error with its details.

Errors also go to NVDA's own log. When reporting a problem, attach the debug log and NVDA's log (NVDA menu, Tools, View log).

## Where things are kept

Everything the assistant writes is inside NVDA's settings folder, usually `%APPDATA%\nvda`:

| Location | What |
| --- | --- |
| `jawsMigrator\backups\<date>` | Backups of NVDA's settings, add-ons and add-on settings (`backup.json` lists every file and add-on) |
| `jawsMigrator\archive\JAWS <version> <date>` | Copies of your JAWS settings (and the shared settings, when chosen) |
| `jawsMigrator\migrations\<date>` | The report (`report.html`, `report.txt`), the migration's `debug.log`, the JAWS index (`jaws-index.json`, `jaws-index.txt`), gestures.ini as it was, and ClassicSpeech voice and scheme files |
| `jawsMigrator\debug.log` | The assistant's general debug log |
| `jawsMigrator\nvdaSounds\<NVDA version>` | A copy of NVDA's own sounds, kept before JAWS sounds are used in their place |
| `jawsMigrator\sounds\keyLayer.wav` | A copy of JAWS's layered keystroke sound, which NVDA+Shift+J plays unless you chose the beep |
| `jawsMigrator\state.json` | The assistant's own settings, including your choice of JAWS items to import |
| `profiles\JAWS - program.ini` (and `profiles\JAWS settings.ini` if you chose a separate profile) | Migrated NVDA configuration profiles |
| `ClassicSpeech\Schemes\<scheme> (from JAWS)` | Migrated ClassicSpeech schemes |
| `ClassicSpeech\Schemes\JAWS Sounds (from JAWS)\Sounds` | Every JAWS sound, ready for ClassicSpeech |

## Limits

- JAWS scripts cannot run in NVDA, and there is no automatic translation. Custom scripts are archived and listed.
- NVDA has no layered keystrokes, frames, graphics labels, color-based highlight detection, Flexible Web, Research It or list view column customization. Those settings are archived and listed.
- Rates and pitches are converted from the percentage JAWS shows, except Eloquence's rate, which keeps JAWS's speed. Two synthesizers can sound a little different at the same percentage, so a voice may need a small adjustment afterwards, in NVDA's voice settings.
- The Insert keystrokes of the Laptop layout, JAWS's rule for times, the silent exit, saying a control's type and state once, and saying a system tray icon only when you move to it need the assistant: they stop when it is uninstalled or disabled.
- NVDA can't tell what changed a system tray icon. A change within a moment of a key you press on the icon is said, whatever made it. Any other change isn't said until you move to the icon again or press NVDA+Tab.
- A control's type and state are only left out of a label when they are at its end, in NVDA's words (or "checkbox", "dropdown" and similar English spellings), right next to where NVDA says them. A page that puts them first, or in another language than NVDA's, is read as it is.
- JAWS voices from synthesizers with no NVDA equivalent on the computer (for example old hardware synthesizers) cannot be used. The report says which ones.
- NVDA speech dictionaries are not per application. Rules from JAWS application dictionaries go into the default dictionary; you can leave them out.
- Braille tables are chosen automatically for English only. For other languages, choose the table in NVDA's Braille settings.

## Building from source

The add-on is plain Python. To build it you need Python 3.10 or later and the `markdown` package (`pip install markdown`), which turns this README into the add-on's help page.

```bash
python build.py
```

This writes `dist/jawsMigrator-<version>.nvda-addon` and its `.sha256` checksum file. The version comes from `addon/manifest.ini`.

Tests:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

`tests/test_nvda_runtime.py` checks that every module the add-on imports exists in the NVDA installed on the computer. NVDA's own copy of Python has only part of Python's standard library, so code that works in the other tests can still fail to load in NVDA. It is skipped where NVDA isn't installed.

`tests/plugin_smoke.py` needs wxPython. It loads the add-on as NVDA does, with real menus, and checks the NVDA menu items, the Settings panel, the NVDA+Shift+J commands and their sound (JAWS's, when the computer has JAWS, or the beep when chosen), the check that has NVDA say a control's type and state once, the one that has NVDA say a system tray icon when you move to it, and that NVDA gets every focus and change notice, and runs every key press, the assistant looks at. It also checks that the assistant still loads, with its Preferences item, Tools submenu, Settings panel and NVDA+Shift+J, when some of its modules can't be loaded, and when every other step of its start fails.

Three further scripts need wxPython and a computer with JAWS or JAWS settings. They change nothing outside a temporary folder:

- `tests/gui_smoke.py` walks through every step of the wizard.
- `tests/settings_dialog_smoke.py` drives JAWS Migration Assistant settings (filters, Select all, Select none, saving) and checks that the wizard and its keyboard layouts follow the saved choice.
- `tests/integration_migration.py` runs a whole migration into an imitation NVDA, checks what it wrote, then restores it, add-ons included.

## Credits

- Written by Josh Kennedy, with Claude.
- The update check and update dialog follow [ClassicSpeech](https://github.com/joshknnd1982/classicspeech-nvda)'s, also under the GPL.
- JAWS, Leasey, Eloquence and other product names belong to their owners. This add-on is not affiliated with Freedom Scientific, Vispero or Hartgen Consultancy.
