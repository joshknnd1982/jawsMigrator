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

- Version: 1.39
- Requires: NVDA 2026.1 or later (tested with NVDA 2026.2) on Windows 10 22H2 or Windows 11
- Works with: JAWS 18 and later, in any JAWS language, including settings left behind by an uninstalled JAWS
- License: GNU General Public License, version 2 or later

## Contents

- [What it does](#what-it-does)
- [Installing](#installing)
- [What's new in 1.39](#whats-new-in-139)
- [What's new in 1.38](#whats-new-in-138)
- [What's new in 1.37](#whats-new-in-137)
- [What's new in 1.36](#whats-new-in-136)
- [What's new in 1.35](#whats-new-in-135)
- [What's new in 1.34](#whats-new-in-134)
- [What's new in 1.33](#whats-new-in-133)
- [What's new in 1.32](#whats-new-in-132)
- [What's new in 1.31](#whats-new-in-131)
- [What's new in 1.30](#whats-new-in-130)
- [What's new in 1.29](#whats-new-in-129)
- [What's new in 1.28](#whats-new-in-128)
- [What's new in 1.27](#whats-new-in-127)
- [What's new in 1.26](#whats-new-in-126)
- [What's new in 1.25](#whats-new-in-125)
- [What's new in 1.24](#whats-new-in-124)
- [What's new in 1.23](#whats-new-in-123)
- [What's new in 1.22](#whats-new-in-122)
- [What's new in 1.21](#whats-new-in-121)
- [What's new in 1.20](#whats-new-in-120)
- [What's new in 1.19](#whats-new-in-119)
- [What's new in 1.18](#whats-new-in-118)
- [What's new in 1.17](#whats-new-in-117)
- [What's new in 1.16](#whats-new-in-116)
- [What's new in 1.15](#whats-new-in-115)
- [What's new in 1.14](#whats-new-in-114)
- [What's new in 1.13](#whats-new-in-113)
- [What's new in 1.12](#whats-new-in-112)
- [What's new in 1.11](#whats-new-in-111)
- [What's new in 1.10](#whats-new-in-110)
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

1. Download `jawsMigrator-1.39.nvda-addon` from the [releases page](https://github.com/joshknnd1982/jawsMigrator/releases).
2. Press Enter on the file. NVDA asks you to confirm, installs the add-on and offers to restart.
3. A few seconds after NVDA starts, the assistant checks the computer once and offers to migrate. After that it only runs when you ask.
4. If [ClassicSpeech](#classicspeech) is not installed, the assistant offers to install it, in a dialog you can read line by line. It downloads ClassicSpeech's newest release from GitHub. If you install it, restart NVDA and open the assistant again, so your JAWS schemes, voice aliases and sounds can come over too. You can say not to be asked again, and install it later from the NVDA menu, Tools, JAWS Migration Assistant, Install or update ClassicSpeech.

## What's new in 1.39

From the tester's answers on issue 33:

- **NVDA+Shift+J, then N lists the recent notifications, and NVDA+Shift+J, then Shift+N says the last one again, as JAWS's Insert+Space, N and Shift+N.** Asked whether they would use a notification history, the tester said yes. JAWS keeps the notifications it gets from Windows and programs, the last 500 of the last 24 hours, whether or not it said them. NVDA says a notification once, as it comes, and keeps nothing. Now the assistant keeps them as JAWS does: messages from programs, such as Edge's "Loading page" or a download finishing, and Windows notifications, such as Outlook's for new mail, including those NVDA or an add-on such as MS Edge Discard Announcements keeps silent, and those from a program in the background. As JAWS, it leaves out Windows' notice that the keyboard's language changed and a terminal's output, keeps only the last of a flood from the Snipping Tool, and keeps the same text again within half a second once. N opens a window called Notification History with the list, the most recent first. Enter, or Details, shows the whole notification, its program and when it came. Copy copies it, Clear history empties the list, and Escape closes it. Shift+N says the last notification again, or "No notification", as JAWS. What NVDA and other add-ons say for a notification doesn't change. The history is in memory only. To stop keeping it, uncheck "Keep the notifications Windows and programs send, for NVDA+Shift+J then N, as JAWS's notification history" in NVDA's Settings, JAWS Migration Assistant. See [Notification history](#notification-history).
- **NVDA+Shift+J, then D turns audio ducking on or off, as JAWS's Insert+Space, D.** JAWS's toggle has two choices and says "Duck other audio" or "Do not duck other audio". NVDA has three (no ducking, ducking while NVDA speaks, and always), and NVDA's own NVDA+Shift+D goes through all three. D goes between JAWS's two: ducking while NVDA speaks, and none, with JAWS's words. A portable copy of NVDA can't duck, and says so.
- **Tested with NVDA 2026.2's own code.** The tests run NVDA's own chain of event handlers, its own handlers for UI Automation notifications and Windows notifications, and the tester's MS Edge Discard Announcements add-on's own code: what NVDA says is word for word as before, and the history keeps what JAWS keeps. NVDA's own NVDA+Shift+D is run beside D.

From the tester's issue 37:

- **NVDA says "Screen curtain on" when it starts with the screen curtain on.** The tester wrote: "The status of the screen curtin isn't being said. Also should we make this more like Jaws?" In their log, NVDA started with the screen curtain on, from "Make screen black" in NVDA's Settings, Privacy and Security, and its first words were "Inbox - Outlook - Outlook". NVDA tells you it started with the curtain on only on a braille display. Now NVDA says "Screen curtain on" after it says where you are. If a window coming to the front cuts it off, it is said after that window's focus; a key you press stops it, as it stops any speech. It isn't said when NVDA reloads its add-ons. To turn it off, uncheck 'Say "Screen curtain on" when NVDA starts with the screen curtain on' in NVDA's Settings, JAWS Migration Assistant.
- **NVDA+Shift+J, then F11 or Print Screen turns the screen curtain on or off, as JAWS's Insert+Space, F11 or Print Screen turns Screen Shade on or off.** On issue 33 the tester also asked for "announcements that indicate screen shade is on like Jaws". JAWS says "Screen Shade on" or "Screen Shade off", and its shade stays on until you turn it off or JAWS restarts. Now NVDA says "Screen curtain on" or "Screen curtain off", JAWS's words with NVDA's name for it, and the curtain stays on until you turn it off or NVDA restarts. NVDA's own key, NVDA+Control+Escape, still works: pressed once it says "Temporary Screen curtain, enabled until next restart", and pressed twice it keeps the curtain on after NVDA restarts. While "Always show a warning when enabling Screen Curtain" is checked in NVDA's Settings, as it comes, NVDA's own warning comes first, as with NVDA's key. See [Screen curtain](#screen-curtain).
- **NVDA+Shift+J, then Shift+F11 says whether the screen curtain is on.** In the log the tester looked for a key that says it. NVDA 2026.2 has a command for it, "Reports the state of the screen curtain", with no key. They gave it NVDA+Escape in NVDA's Input Gestures dialog, then took the key off again. Before that, NVDA+Escape said nothing in Outlook: it is JAWS's Insert+Escape, Refresh Screen, which a migration gives to NVDA's refresh of a web page. Shift+F11 says "Screen curtain on", "Screen curtain off", or "Screen curtain on. NVDA turns it on each time it starts." when "Make screen black" is checked in NVDA's Settings.
- **Tested with NVDA 2026.2's own code and JAWS 2026's own files.** The tests run NVDA's own Screen Curtain, its own NVDA+Control+Escape and its own report beside the layer's keys. F11 leaves the curtain as NVDA's key pressed once does, and turning it off leaves "Make screen black" off, as NVDA's key does. NVDA's own speech manager, focus and window code start NVDA in Outlook with the curtain on, as in the tester's log: without the new check box nothing about the curtain is said, and with it "Screen curtain on" comes after the window and the message you are on. The tests also read JAWS 2026's ScreenShadeToggle script, its "Screen Shade on" and "Screen Shade off", and its keys after Insert+Space.

## What's new in 1.38

From the tester's log on issue 32:

- **JAWS's Say Next Sentence and Say Prior Sentence read by sentence on web pages.** On a GitHub page in Edge the tester pressed NVDA+N twice, and NVDA said nothing. Each time NVDA's log had an error from NVDA's own command for the next sentence. The tester's migration had "When NVDA already uses a keystroke for something else, use the JAWS command instead" checked, so JAWS's Laptop layout keystroke Caps Lock+N, Say Next Sentence, took NVDA+N on web pages, and Caps Lock+Y, Say Prior Sentence, took NVDA+Y. In the Desktop layout they are Alt+NumPadPlus and Alt+NumPadMinus. JAWS's virtual cursor reads by sentence in Edge, Chrome, Firefox and PDFs. NVDA knows sentences only in documents such as Word's; on a web page its command failed before it moved or said anything. Now, where a document in browse mode has no sentences, the assistant finds them itself. A sentence ends at a full stop, question mark, exclamation mark or ellipsis followed by a space, and a paragraph always ends one. The next-sentence key moves to the next sentence and says it, going on to the next paragraph with text, and the prior-sentence key moves to the sentence before. At the end or start of the page, the sentence you are on is said again, as NVDA does. When a page has just opened and NVDA has held back its first line, the next-sentence key says the first sentence, as JAWS goes from the page's title to it. Word documents, and every other key, are as before.
- **The MS Edge Discard Announcements add-on's category stays in NVDA's Settings while Edge runs.** 1.36's notes sent the tester to NVDA's Settings, "Microsoft Edge discard announcements" category, to hear Edge's "Going back". They couldn't find it, and it wasn't there. That add-on adds its category when NVDA meets an Edge process, and takes it out when that process ends. But Edge runs many processes. The Open dialog the tester had just used to attach their log was one, and as it closed, NVDA's log said "application msedge closed" and the category was gone while Edge still ran, until Edge or NVDA was started again. Now, each time NVDA lets go of a program that ended, the assistant puts the category back while Edge is still running. Nothing else about the add-on changes, and nothing happens without it.
- **Tested with NVDA 2026.2's own code.** The tests run NVDA's own commands for the next and prior sentence and its caret movement, on NVDA's own text code for a web page. With 1.37, NVDA+N raises the error in the tester's log; with 1.38, it reads the reddit post from issue 32 sentence by sentence, forward and back, past blank lines, and says the last sentence again at the end. The key planner, run on JAWS 2026's own keystrokes, gives NVDA+N the next sentence only when JAWS commands take NVDA's keys, as the tester's log shows. NVDA's own clean-up of programs that ended runs with the add-on's own code: it takes the category away as in the tester's log, and with 1.38 the category comes back.

From the tester's report on issue 36:

- **Opening the Speech History, or the update dialog, no longer reads out everything in it.** The tester pressed NVDA+Shift+J, then H, and NVDA said "Speech History, dialog", then the whole history, oldest first, one typed letter at a time: "space, h, e, a, r, period, …". Their older log shows NVDA reading all of 1.36's release notes the same way as the update dialog opened. NVDA reads a dialog's text and its one-line read-only fields as the dialog opens, and leaves out a box of several lines. Both of these are boxes of several lines, but NVDA took them for one line. The cause was the assistant's own fix in 1.15 for Enhanced Control Support, which the tester has. To decide whether Enhanced Control Support should check a text field 20 times a second, it asked for the field's states while NVDA was still putting the field together, before NVDA knew the field had several lines, and NVDA kept that answer. Now the assistant tells a box of several lines from its window, and leaves NVDA's answer alone. NVDA says "Speech History" and the most recent line, as JAWS does, and the update dialog says its first line and the notes' first line, from where the arrow keys read on. The same happened with a read-only box of several lines in any program's dialog, and that's fixed too. Enhanced Control Support now really leaves such boxes, like NVDA's Log Viewer, to NVDA, as 1.15 meant. The unit tests run NVDA 2026.2's own code for making objects, keeping their properties and reading a dialog's text, with Enhanced Control Support 1.2.2's own code. With 1.37's check they give, word for word, the release notes the tester's log shows NVDA reading; with 1.38's, only the dialog's own text.
- **The JAWS keystroke helper says when Insert was let go too soon.** For Insert+Space, the tester pressed NVDA+Shift+J, then K, then what they meant as Insert+Space, and heard "In JAWS, Space runs Virtual Spacebar…". NVDA's log shows it got Space alone: Insert wasn't down when Space went down. Now, if Insert or Caps Lock goes down after K and is let go before the next key, the helper says so first: "You let go of Insert before you pressed space, so NVDA got space by itself. For Insert+space, hold Insert down while you press space." Then it says what that key does alone. Held down, Insert+Space gets 1.36's answer about JAWS's layered keystrokes.

## What's new in 1.37

From the tester's answer on issue 34:

- **NVDA says "Unloading NVDA" as it exits, where JAWS says "Unloading JAWS".** Asked whether NVDA should say something as it exits, the tester wrote: "probably the best way to handle that is if they have it speak a conformation when unloading Jaws you do the same for NVDA. ... This could be able to be turned off just like you can in Jaws. If it is turned off in Jaws nothing changes." JAWS's Insert+F4 says "Unloading JAWS", then unloads JAWS. It says it as a JAWS Message, one of the Items to be Spoken that Settings Center has for each verbosity level, so JAWS says it only where JAWS Messages are on at your verbosity level: at Beginner and Intermediate as JAWS comes, and not at Advanced. A migration now takes that from your JAWS. Where your JAWS says "Unloading JAWS", NVDA says "Unloading NVDA" when you exit it, with Insert+F4, NVDA's menu or its exit dialog. Where your JAWS doesn't, NVDA exits without a word, as before. NVDA stops speaking as it exits, so it now waits for the message: it exits once the message has been said, at once if you press a key, and after 4 seconds at the most. Nothing is said when NVDA restarts, or when speech is off. To turn it on or off, check or uncheck 'Say "Unloading NVDA" as NVDA exits, as JAWS says "Unloading JAWS"' in NVDA's Settings, JAWS Migration Assistant.
- **For a migration you made before, the assistant looks at your JAWS once.** You don't need to migrate again. A little after NVDA first starts with 1.37, the assistant reads your JAWS settings. If your JAWS says "Unloading JAWS", it turns the message on, and NVDA says: "JAWS Migration Assistant: NVDA now says "Unloading NVDA" as it exits, as your JAWS says "Unloading JAWS". To turn it off, uncheck it in NVDA's Settings, JAWS Migration Assistant." If your JAWS doesn't say it, nothing changes, and NVDA says nothing about it. The debug log says which JAWS setting decided.
- **Tested with NVDA 2026.2's own code and JAWS 2026's own files.** In the tester's log, NVDA stopped speaking 0.2 seconds after it was asked to exit, too soon for a message. The tests run NVDA's own exit code (its exit command, its menu's and exit dialog's Exit, and its restart), and NVDA's own speech manager, speak and speech cancelling, with its focus and foreground events. With 1.37 the synthesizer says the whole message before NVDA's exit starts. Exiting from NVDA's menu gives the foreground back to the program you were in, which stops NVDA's speech; the message is then said again, once, to the end. The tests also read JAWS 2026's own ShutDownJAWS script, its "Unloading JAWS" message and its JAWS Messages row in Default.jcf at each verbosity level.

## What's new in 1.36

From the tester's reports on 1.35: going back on a website (issue 32), the layer's commands (issue 33), Insert+Q (issue 34), and JAWS and NVDA side by side on several sites (issue 35):

- **Alt+Left and Alt+Right say "Back" and "Forward", and the page you go back to is read, as in JAWS.** On reddit.com the tester read a post in Edge and pressed Alt+Left. JAWS said "Back", then "Going back", then the line it was on. NVDA said nothing. JAWS's scripts for Edge, Chrome and Firefox bind Alt+Left and Alt+Right to their own commands, which say "Back" and "Forward" and turn forms mode off. Now NVDA says "Back" or "Forward" as the key goes to the browser, and leaves focus mode for browse mode. Reddit doesn't load a page when you go back: it puts the subreddit back into the page that is there and changes the address, so NVDA came into no new page to read. The Browse Mode Caret Fix add-on, which the tester runs, put browse mode's caret back on the post they had opened, without saying it. Now, when a page's address changes and no new page loads, NVDA reads the line at the caret once the page and the caret are still, after Browse Mode Caret Fix has put the caret back: "heading level 2, visited, link, What Phones Work Best On Visible?". Run live, an ordinary two-page site went silent too. Edge keeps the pages you leave, and going back to one, Browse Mode Caret Fix gave NVDA the page's focus itself, so NVDA never came into the page. Going forward, NVDA's focus stayed on the page you had left. JAWS said the page's title and the line it came back to: "Plain page one", then "heading level 2, Link, Go to page two". Now NVDA does the same. A page that loads is read by NVDA as before, a link a page moves the focus to is said as before, and nothing NVDA says itself is said again. Another key, or another program, ends it. "Going back" is Edge's own announcement, which NVDA says as it comes; if you use the MS Edge Discard Announcements add-on, set its "Navigating back" and "Navigating forward" to Speak to hear them, as they are off as it comes. When NVDA logs at its debug level, its log says what was read and why. To turn this off, uncheck 'Say "Back" and "Forward" for Alt+Left and Alt+Right in web browsers, and read the line a page comes back to, as JAWS does' in NVDA's Settings, JAWS Migration Assistant.
- **Quick navigation says no description of a link or heading, as JAWS.** On reddit.com the tester pressed H, and NVDA said "What Phones Work Best On Visible?, visited, heading, level 2, link, Author: u/Pikachufourtytwo 2 hr. ago". JAWS said the same without "Author: ...", which is the description reddit gives each post's title. As JAWS comes, its virtual cursor says no descriptions (its Default.jcf has DescribedBy and ElementDescription off at the Medium verbosity), and Alt+Insert+R reads one when you ask. Now H, K, 1 to 9 and the Elements List's Move to say a link or heading without its description, whatever it comes from. Tab says it, as JAWS says a link's description when the focus moves to it. A link's title, which 1.25 left out everywhere, is said on Tab again, as JAWS 2026 said a Wikipedia link's title on Tab. This is part of 'Say links on web pages as JAWS does'.
- **Tested live with JAWS 2026 and NVDA 2026.2.** Claude ran JAWS and NVDA on the maintainer's computer in Edge 154, with the same keys, on a copy of the tester's subreddit that works as reddit does (a post opens in the same page, and Back puts the subreddit back) and on a plain two-page site. JAWS said "Back" and "Going back", then on the plain site "Plain page one" and "heading level 2, Link, Go to page two"; on H to a post's link it said no description, and on Tab it said it. NVDA with 1.36 and Browse Mode Caret Fix said "Back", "Going back" and "link, What Phones Work Best On Visible?" on the copy of the subreddit, and "Back", "Plain page one" and "link, Go to page two" on the plain site. The unit tests replay the tester's log with NVDA 2026.2's own speech code and Browse Mode Caret Fix 3.0.24's own code: with 1.35 nothing after Alt+Left, as in the log, and with 1.36 "Back" and the post's line.
- **NVDA+Shift+J, then question mark shows the layer's commands in a window, as JAWS does.** The tester pressed NVDA+Shift+J, then question mark, and asked: "Are the commands being properly updated?" They were: the help named all 20 of the layer's commands, on its 21 keys, and nothing else. But the keys and the help were two lists kept by hand, so a new command could have been left out of the help. Now both come from one list, and a test checks that README's table of the assistant's own commands has the same keys. JAWS shows its own layer's help, Insert+Space then question mark, in its Results Viewer, a line for each command. Now question mark and F1 open a window called JAWS Migration Assistant Layer Help, instead of NVDA saying all 20 commands in one go: the arrow keys read it a line at a time, Control+C copies what you select, the Copy button copies it all, and Escape closes it. See [The assistant's own commands](#the-assistants-own-commands).
- **The JAWS keystroke helper knows the layer, and says each JAWS command once.** NVDA+Shift+J, then K, then a JAWS keystroke tells you what it does in NVDA. For Insert+Control+V, when a migration hadn't given the version command a key, it said "It has no keystroke yet; assign one in NVDA's Input Gestures dialog", though NVDA+Shift+J, then V does it. Now it also names the key after NVDA+Shift+J for each JAWS command the assistant does itself. For Insert+Space, it said "does nothing special in JAWS", because JAWS's key map lists only the keys pressed after it. Now it says Insert+Space starts a layered keystroke, and that NVDA+Shift+J starts the assistant's layer, which has JAWS's speech history keys, H, Control+H and Shift+H, and question mark for its help. JAWS binds about a quarter of its keystrokes twice, such as Control+JAWSKey+V and Control+Insert+V, or Alt+Control+LeftArrow and Alt+Control+ExtendedLeftArrow, and the helper said those commands twice. Now it says each once.
- **README names what the NVDA menu's Tools, JAWS Migration Assistant has.** It said the menu had the layer's actions. It has most of them, and G, P, I, the version keys and the speech history keys are only in the layer and in NVDA's Input Gestures dialog.
- **Insert+Q says the program you are in, as in JAWS, and no longer exits NVDA.** The tester wrote: "Insert q tells you the active program. ... It doesn't do that in NVDA". JAWS exits with Insert+F4 and says the program you are in with Insert+Q. NVDA exits with NVDA+Q and has no key of its own on NVDA+F4. A migration already gave Insert+F4 to exiting NVDA, and the tester's logs show it exiting NVDA at once, as their JAWS does with its exit confirmation off. Insert+Q, though, stayed NVDA's exit unless you let JAWS's keys take NVDA's, so it closed NVDA where JAWS would say the program. Now, wherever Insert+F4 exits NVDA, Insert+Q runs NVDA's command that says the program, the one on NVDA+Control+F1: "outlook module is loaded. OUTLOOK.EXE is currently running." Exiting NVDA keeps Insert+F4, JAWS's key for it. Your other keys stay as your migration decided, and an add-on's key or one you gave a command of your own stays as it is. If you migrated your keystrokes before, the assistant adds Insert+Q once, a little after NVDA first starts with this version: NVDA's settings are backed up first, and NVDA says "NVDA+q, the program you are in, as JAWS's Insert+Q; it no longer exits NVDA: NVDA+f4 does." See [Everything else about keystrokes](#everything-else-about-keystrokes).
- **Every quick navigation key says only what it moves to, as JAWS does.** The tester asked for tests on several sites, Amazon among them, with both JAWS and NVDA, and whether big differences should be fixed or left alone. JAWS 2026 and NVDA 2026.2 with the assistant were run side by side in Edge, on copies of Amazon's home page and its search results for "usb c cable", Wikipedia's "Screen reader" article, BBC News, a BBC News article and the assistant's GitHub page, with the same 59 keys on each (NVDA with the settings a migration from JAWS gives it). Headings, links, buttons you Tab to, regions and lists you arrow through, and edit fields already said the same things. The quick navigation keys did not: JAWS says what it moves to, and NVDA said every landmark, region and list it came into first. B on Amazon: JAWS "Delivering to Williamstown 17098 Update location, Button", NVDA "banner region, Primary, navigation region, Delivering to Williamstown 17098, Update location, button". C: JAWS "Search in, Combo box, collapsed", NVDA "banner region, Primary, navigation region, search region, Search in, combo box, collapsed". I on Wikipedia: JAWS "Link Donate", NVDA "banner region, Personal tools, navigation region, list of 3 items, Donate, link". Now, on web pages in Edge, Chrome and Firefox, every quick navigation key (B, C, X, G, L, I, K, U, V, F, D, T, O and the others, and Move to in the Elements List) leaves out the landmarks, regions, lists and tables around what it moves to, as H and E have done since 1.13 and 1.31. What it moves to is said as before, with what is in it: L says the list and its first line ("list of 3 items, Donate, link"), D the region and its first line, T the table and its first cell, and a link or heading around a graphic is still said. The arrow keys and Tab still say the regions and lists they come into, as JAWS does. It is part of the check box for headings, now "When quick navigation moves to a heading, a button or anything else, don't say the landmark, region or list it is in, and say "blank, placeholder" for an empty edit field".
- **The first Down Arrow after a page opens reads the page's first line.** Since 1.33, the first time you come to a page NVDA says its title without the page's first line, as JAWS does, whose cursor starts on the title. But NVDA's caret stayed on that first line, so the first Down Arrow read the second line and the first line was never said. On BBC News JAWS's first Down Arrow said "same page link Skip to content"; NVDA's said "button, collapsed, Open menu". H and Tab went past an element on the first line too: on Amazon H went to the second heading, and on BBC News Tab went to "Open menu", where JAWS's went to "Skip to content". Now, until the caret moves, the Down Arrow says the first line and stays there (the next one reads the second line), and H, Tab and the other quick navigation keys go to an element the first line starts with. This is part of "Say Edge and Chrome windows and pages as JAWS does".
- **What was left as NVDA has it.** The run found other differences, left alone for now: at the last heading JAWS's H says "wrapping to top" and goes to the first, where NVDA says "no next heading", and where there are none JAWS says "There are no Check boxes on this page"; JAWS says a table's columns before its rows ("table with 2 columns and 7 rows, Column 1, Row 1"); JAWS gives "list of 3 items", "list end" and a region's name a line of their own, so its Down Arrow stops on them; Control+Home says the page's title in JAWS and the first line in NVDA; as a page opens JAWS says how many regions, headings and links it has (ClassicSpeech's page summary does something like it); JAWS's O finds a page's articles, which NVDA's article command misses in Edge; and N, P and C move by different rules. Tell us on GitHub if any of these should change.

## What's new in 1.35

- **The Emoticons add-on is left alone from its version 38.2.0, which writes no warnings.** Since 1.34, the assistant has Emoticons 38.0.0 read NVDA's speech dictionaries once for each change instead of twice for each emoticon, so NVDA writes its warning once instead of 177 times at each profile switch (see [What's new in 1.34](#whats-new-in-134)). To do that, the assistant read them once itself. Emoticons 38.2.0, which needs NVDA 2026.3, keeps NVDA's temporary dictionary itself and no longer reads the name NVDA warns about, so NVDA writes no warning, but the assistant's own reading would have added one at each change. Now the assistant helps only a version of Emoticons that still reads that name, such as 38.0.0 on NVDA 2026.2 or 2026.3. Columns Review is helped as before; its author has [the report](https://github.com/ABuffEr/columnsReview/issues/55).
- **Tested with NVDA 2026.3's own code and Emoticons 38.2.0's own code.** The tests run NVDA 2026.3's getDictionaryDefinition, on 1.34's imitation of NVDA 2026.2's speech dictionaries and their warning, with Emoticons 38.2.0's own code for a profile switch. With 1.34, eight profile switches wrote 16 warnings; now none, and NVDA's temporary dictionary holds the same emoticons. Emoticons 38.0.0 on NVDA 2026.3, which still warns, gets one warning for each change, as in 1.34.

This is part of "Keep Columns Review and Emoticons from holding NVDA up each time you switch programs or browse mode turns on or off", in NVDA's Settings, JAWS Migration Assistant.

## What's new in 1.34

From the tester's comments on 1.33 (issue 30), where they pasted what NVDA said as they switched with Alt+Tab between Outlook and three Edge windows, asked whether NVDA should match JAWS, and asked for it to be tested with JAWS so nothing is missed; and from the tester's report of Alt+Tab holding NVDA up (issue 31):

- **Regions, groups, lists and articles on web pages are said with JAWS's words.** JAWS 2026 was run in Edge 154 on copies of the tester's reddit and GitHub pages, with its speech history copied after each key. As the focus moves (Tab, or coming back to a field on a page), JAWS said "main region", "banner region", "Global navigation region", "Reply form region", "content info region" and "new Comment group". NVDA said "main landmark", "banner landmark", "Global navigation landmark", "Reply form landmark", "content info landmark" and "new Comment grouping". With the arrow keys, JAWS names only the main and navigation regions, as JAWS comes (its Medium verbosity), with their names, and says where they end: "Reddit navigation region" … "Reddit navigation region end", "main region" … "main region end". It doesn't name the banner, search, form, complementary and content information regions. It says "list of 2 items" … "list end", "Community actions region" … "Community actions region end", "Comment by visible_help article" … "Comment by visible_help article end", and "group start new Comment" … "group end new Comment". NVDA named every landmark and never said where one ends, and said "list with 2 items" … "out of list", "region" … "out of region", "article" … "out of article", "grouping" … "out of grouping". Now NVDA says all of these with JAWS's words, in Edge, Chrome and Firefox. In Say All NVDA names every region, as JAWS named the form and search regions reading a page from the top. What NVDA's Document Formatting settings leave out (landmarks, lists, articles, groupings) stays out, a role a page gives its own words to is said as NVDA says it, and braille is unchanged. When NVDA logs at its debug level, its log says what was said with JAWS's words. To have NVDA say them as before, uncheck 'Say regions, groups and lists on web pages with JAWS's words: "main region", "group", "list of 2 items", "main region end"' in NVDA's Settings, JAWS Migration Assistant.
- **The first time you come to a page, NVDA says its title without the page's first line.** With 1.33, switching with Alt+Tab to a reddit window NVDA hadn't read yet, NVDA said the window's name, the post's title, then "same page link Skip to main content". JAWS said the window's name and the title. Coming back to a page, JAWS says the line its cursor is on ("same page link Skip to main content", when it was left there), as NVDA does. But JAWS's cursor starts on the page's title, which is what Control+Home says in JAWS, and NVDA's caret starts on the page's first line. Now, the first time NVDA comes into an Edge or Chrome page (a page that opens, or one you come to for the first time since NVDA started), with the page itself focused and the caret on its first line, NVDA says the title and not that line. A caret that starts further down, as on the tester's SiriusXM page ("Showing channels for myStreaming & Most Radios."), coming back to a page, focus mode and "Automatic Say All on page load" are as before. This is part of 'Say Edge and Chrome windows and pages as JAWS does'.
- **Tested live with JAWS 2026, and with NVDA 2026.2's own code.** Claude ran JAWS twice on the maintainer's computer, driven through its programming interface: the tester's Alt+Tab trip between a window standing in for Outlook and three Edge windows, the arrow keys, Tab, Control+Tab and R through the copies of the pages, and coming back to a page with the cursor in different places. The unit tests run NVDA's own speech for a page's text and for an object, its browse mode coming into a page, word for word, with the tester's settings. With the changes, NVDA says JAWS's words for every region, group, list and article JAWS named on the copies.
- **Alt+Tab into and out of Edge no longer holds NVDA up, and Insert+F7 opens the Links List again.** The tester's log showed NVDA stuck twice, about two seconds each time, whenever the focus went into or out of Edge. Three times, Insert+F7 opened Edge's "Turn on caret browsing?" instead of the Links List, with no Insert+F7 in NVDA's input log. Each time, NVDA was switching configuration profiles. The migration's "JAWS - msedge" profile turns on in Edge, and the Custom Browse Mode add-on turns on its "browseMode" profile whenever browse mode does, so each Alt+Tab into or out of Edge is two switches. At every switch, the Columns Review add-on binds its keys again for each list it has seen. To learn which keys NVDA's own Say all, Report formatting and Report selection have, it asked NVDA for every command of every add-on, program and object, the list behind Input Gestures: 0.75 to 0.87 seconds each time. The Emoticons add-on reads NVDA's speech dictionaries twice for each of its 88 emoticons. NVDA 2026.2 answers each read with a warning and the whole stack in its log: 177 warnings, 0.2 seconds, at every switch. When NVDA is stuck for half a second after the foreground window changes, it lets every key go straight to the program, so you can still reach Task Manager. That is how Edge got F7. Now Columns Review asks NVDA for those keys again only once NVDA's keys have changed: yours, NVDA's language's, a braille display's, or NVDA's own commands'. Emoticons reads NVDA's dictionaries once for each change, so NVDA writes its warning once, not 177 times, and the tester's logs get much smaller too. What the two add-ons bind, say and put in the temporary dictionary is unchanged. JAWS switches a program's settings at once.
- **Tested with NVDA 2026.2's own code and the two add-ons' own code.** The tests run NVDA's own ScriptableObject, script decorator, gesture maps, its list of all commands, its global commands' scripts and its speech dictionary code with its warning. They also run Columns Review 5.7.0's and Emoticons 38.0.0's own code for a profile switch, with the tester's profiles in the tester's order. Before the change, an Alt+Tab out of Edge and back had Columns Review ask NVDA for every command 8 times and Emoticons write 708 warnings. Now Columns Review asks once, until a key changes, and Emoticons writes 2 warnings a switch. The keys Columns Review binds, with or without a key you changed, and Emoticons' dictionary, are the same as before.

The last two are "Keep Columns Review and Emoticons from holding NVDA up each time you switch programs or browse mode turns on or off", in NVDA's Settings, JAWS Migration Assistant; unchecking it gives both add-ons their own back.

## What's new in 1.33

From the tester's comments on 1.31, with what NVDA and JAWS said as they switched with Alt+Tab from an Outlook message to Edge, where a GitHub page had the focus in its comment box, and from there to their reddit tab:

- **Coming back to Edge or Chrome, a page is said by its title without "document", also when the focus is in a field on it.** Switching to the GitHub tab, NVDA said "issue with how NVDA reads certain things on Reddit · Issue #30 · joshknnd1982/jawsMigrator, document". JAWS said the title alone, then "main region", "new Comment group" and the button that had the focus. 1.31 left "document" out only when the page itself gets the focus, as when it opens or you come back to it in browse mode. Here the focus was in the comment box, so NVDA said the page as a place the focus is in, as it says the landmark and the group. Now NVDA says the page by its title either way. A frame's own page, inside a page, is said as before.
- **Choosing another tab, NVDA no longer says the page of the tab you are leaving.** The tester chose their reddit tab in Alt+Tab. Edge first put the focus back in the GitHub comment box, where it had been, then moved it to the reddit page. So NVDA said the window, the GitHub page's title, "main landmark", "new Comment grouping" and the comment box, then the reddit page. JAWS said only the reddit page's title. NVDA drops what it hasn't said yet about the focus once the focus has moved on, but it keeps what it says about the places the focus is in: the page, a landmark, a group. Now, in Edge and Chrome, what NVDA hasn't said yet about such a place is dropped once the focus has left it. A place the focus is still in is said as before, for example when you Tab to the next field in the same group, and NVDA never cuts short what it has started saying. NVDA's debug log says what was dropped.
- **A page's title or a window's name isn't said twice at once.** Coming to the reddit page, NVDA said its title twice in a row. Now it says it once, and again whenever you come back to it.
- **The speech history leaves out what NVDA dropped before saying any of it.** JAWS's speech history holds what went to the synthesizer. The history the tester pasted (NVDA+Shift+J, then Control+H) had the whole GitHub part twice, but NVDA had dropped most of the first, and the second one's comment box, before saying a word of them. Now NVDA+Shift+J, then H and Control+H leave out what NVDA's speech manager dropped without saying a word of it: what NVDA had for a focus that moved on, and what it hadn't started when it cut speech short, as when another window comes to the front. What you paste is what you heard. Anything NVDA started to say stays in, even if it was cut short.
- **Tested with NVDA 2026.2's own speech manager and focus code.** The tests run NVDA's own speech manager, its speech commands, speak, cancelSpeech, the focus handling of its event handler and api, and its object speech, with the tester's windows, pages and settings, and a synthesizer that says what the speech manager gives it. Before the change, NVDA was asked to say the lines of the tester's log word for word. After it, choosing the reddit tab, the synthesizer said the window, the reddit page's title and its first line, and the speech history held just those three.

This is part of 'Say Edge and Chrome windows and pages as JAWS does' and of 'Keep what NVDA says, for NVDA+Shift+J then H, as JAWS's speech history', in NVDA's Settings, JAWS Migration Assistant; unchecking them gives NVDA's own back.

## What's new in 1.32

From the tester's report:

- **Insert+Control+V says the program's version where an add-on that is turned off had the key.** After updating to 1.30, the tester wrote: "It has been more then a minute and insert control V still brings up NVDA speech settings." Their log showed why. The tester's NVDA input gestures give Insert+Control+V to the add-on Say Product Name and Version, which is turned off. NVDA passes over a key given to an add-on that is off, so the key opened NVDA's speech settings. But 1.30 took it for a key the tester had chosen for something else, left it alone, and added only Control+Insert+Windows+V. Now a key given to an add-on that is off or removed doesn't count as taken, in a migration or when keys are added after an update. While that add-on was on, the key didn't run NVDA's own command, so the JAWS command takes it even if you chose to keep NVDA's keys. Where 1.30 or 1.31 left a key out this way, the assistant adds it once, a little after NVDA starts, after backing up NVDA's settings, and NVDA says: "1 more JAWS keystroke works in NVDA. NVDA+control+v, the name and version of the program you are in; twice, the version details." Keys added before, and keys you have changed since, stay as they are. The add-on's own line in gestures.ini is left alone; if you turn that add-on on again, NVDA runs whichever of the two commands it asks first.
- **Tested with NVDA's own code for keys.** NVDA 2026.2's own code that finds the command a key runs (scriptHandler and its gesture map) ran with the tester's gestures.ini line and NVDA's laptop keyboard layout, as in the tester's log. Before the change, Insert+Control+V opened NVDA's speech settings, and the assistant left the key out in the very words of the tester's log. After it, the key was added once, one press said "Microsoft Outlook Subscription Version 16.0.20326.20158", and two opened Version Details, whether or not the migration let JAWS's keys take NVDA's. With the add-on turned on, its key still runs, and the assistant leaves it alone.

## What's new in 1.31

From the tester's report:

- **Edge and Chrome windows and pages are said as JAWS says them, by their titles.** The tester opened a reddit post in Edge, and NVDA said "Worst three days of my life : r/Visible and 1 more page - Profile 1 - Microsoft Edge, window", then "Worst three days of my life : r/Visible - Microsoft Edge, region", then "Worst three days of my life : r/Visible, document" and the page's whole address. On a copy of the page, JAWS 2026 said the titles alone: "Worst three days of my life : r/Visible - Microsoft Edge", the page's title, and how many regions, headings and links the page has, never "window", "document" or the address. NVDA said the address and "region" because it read Edge through UI Automation that time. That way, a page's value is its address, and Edge's own frame around the page is a region named after the page. NVDA normally reads Edge's pages through IAccessible2, as JAWS does, and there it says neither. Now NVDA says Edge's and Chrome's window by its name, without "window", and a page, when it opens or you come back to it, by its title, without "document" or its address, and it doesn't say Edge's frame. Anything else NVDA says with them, such as "busy", stays. NVDA+Tab, a page without a title, other programs and braille are as before. When NVDA logs at its debug level, its log says what was left out. To have NVDA say them as before, uncheck 'Say Edge and Chrome windows and pages as JAWS does: their titles, without "window", "document", the address or Edge\'s "region"' in NVDA's Settings, JAWS Migration Assistant.
- **E says an edit field as JAWS does: without the landmarks around it, and "blank, placeholder" when it is empty.** On the same post, E said "banner landmark, navigation landmark, search landmark, Remove r/Visible filter and expand search to all of Reddit, edit, Search in r/Visible" for the search box, and "main landmark, edit, Join the conversation" for the reply box. JAWS's E says no landmark. For a field with nothing in it, JAWS says "blank", then "placeholder" and the grey text the field shows: on a copy of the page JAWS said "Remove r/Visible filter and expand search to all of Reddit, edit, blank, placeholder, Search in r/Visible", and on reddit the tester's JAWS said "edit, blank, placeholder, Join the conversation". (The search box has that long name because Reddit puts the button that removes the r/Visible filter inside the box's label; on the copy, JAWS said it too.) Now E and Shift+E, and Move to in the Elements List, say an edit field without the landmarks, regions and lists around it, as H has said a heading since 1.13, and an empty one with "blank", then "placeholder" and its placeholder, after its type. A field with text in it is said as before, and the arrow keys, Tab and NVDA's other quick navigation keys still say the landmarks they come into. It is part of the check box for headings, now "When quick navigation moves to a heading or an edit field, don't say the landmark, region or list it is in, and say "blank, placeholder" for an empty edit field".
- **Tested with both NVDA and JAWS, as the tester asked.** Reddit turns automated browsers away, so the tests used a copy of the post's page, with the search box and the reply box built the way Reddit's own scripts build them. On the maintainer's computer, with Edge 154, JAWS 2026 read the copy, driven through JAWS's own programming interface, and its speech history was copied after each step; then NVDA 2026.2 read it without this version's changes and with them. With them, NVDA said for E exactly what JAWS said, and the window and page by their titles. The assistant's tests also run NVDA 2026.2's own speech code on the tester's page and give the tester's lines word for word before the change, and JAWS's words after it.

## What's new in 1.30

From the tester's reports:

- **Insert+Control+V says the name and version of the program you are in, and pressed twice shows the version details, as in JAWS.** The tester wrote: "It should work like Jaws. insert control V says the product version. Pressing it twice brings up the following. You can arrow and copy any or all of what you need." NVDA has no such command; its own NVDA+Control+V opens its speech settings. Now, once, NVDA says what JAWS says, from the version information in the program's file, or from a Store app's package: "Microsoft Edge Version 154.0.4258.37". As JAWS's scripts do, File Explorer and the desktop give the version of Windows, and Word, Outlook, PowerPoint and Access say how Office was bought: "Microsoft Outlook Subscription Version 16.0.20326.20158". Twice, NVDA opens a window called Version Details: the arrow keys read it, Shift with the arrow keys selects, Control+C copies what you selected, the Copy button copies it all, and Escape closes it. Its lines are JAWS's, with NVDA's facts: the program's version, NVDA's version, the assistant's version, the NVDA configuration profile in use, the program's executable, NVDA's support for the program, ClassicSpeech's speech and sounds scheme, and the version of Windows as JAWS words it, "Microsoft Windows 11 Professional Version 25H2 (OS Build 26200.9457), System Type x64". Control+Insert+Windows+V, JAWS's key for it, copies the version details without opening anything, and NVDA says "Version Details Copied To Clipboard". NVDA+Shift+J, then V, Shift+V and Control+V do the same, wherever you are. A migration gives JAWS's keys to these commands. Insert+Control+V is NVDA's key for its speech settings, so it gets the program's version only when you let JAWS's keys take NVDA's; Control+Insert+Windows+V isn't NVDA's, so it always does. If you migrated your keystrokes before, the assistant adds these keys once, a little after NVDA first starts with this version, as your migration added its own: NVDA's settings are backed up first, NVDA says which keys now work, and a key you gave a command of your own in NVDA's Input Gestures dialog stays yours. See [Program version](#program-version).

## What's new in 1.29

From the tester's reports:

- **In Outlook, Insert+Page Down reads the status bar as JAWS does.** In Outlook's Inbox, the tester pressed Insert+Page Down, JAWS's command to read the bottom line of the window, which the migration gives NVDA's "Report status bar". JAWS said "Items in View 2,675", "Unread Items in View 1,135" and "Zoom 10%". NVDA said "Status Bar", those, and every other control in the status bar too: "Normal View. Show All Pinned Panes. Reading View. Hide All Pinned Panes. Zoom Out 10 Zoom 10 Zoom In 10". NVDA reads a status bar as its name, then the name and value of each control in it, and NVDA's support for Outlook has no way of its own. JAWS's script for Outlook reads only the status bar's items, the kind of control Office calls a simple button: the item counts, the zoom, and messages Outlook shows there at times, such as a filter being applied, a line each. The view buttons and the zoom slider and its buttons are other kinds of controls, and JAWS leaves them out. Now NVDA reads Outlook's status bar as JAWS does, with a short pause between the items: "Items in View 2,675, Unread Items in View 1,135, Zoom 10%". Pressed twice, NVDA spells that, and pressed three times copies it to the clipboard, as before. Where Outlook's status bar has no such item, NVDA reads it as before, and so it does in other programs. When NVDA logs at its debug level, its log says what it read. To have NVDA read Outlook's status bar as before, uncheck "Read Outlook's status bar as JAWS does: its items and zoom, without the view and zoom buttons" in NVDA's Settings, JAWS Migration Assistant.
- **Insert+F7 lists the links alone, as JAWS's Links List does, and JAWS's other list keys list their own kinds.** The tester wrote: "When using Jaws pressing insert f7 only brings up links. should we Make the Jaws migrator do the same?" In NVDA the key opens the Elements List, whose radio buttons choose links, headings, form fields, buttons or landmarks. JAWS has a list of its own for each kind, each with its own key: Insert+F7 its Links List, Insert+F6 its Heading List, Insert+F5 its list of form fields, Control+Insert+B its list of buttons and Control+Insert+R its list of regions. The migration gives each of those keys to NVDA's Elements List, so each opened the same list, on links or on the kind last chosen there. Now each of JAWS's keys opens the Elements List on its own kind alone. The list has JAWS's title, so NVDA says "Links List dialog" or "Heading List dialog" as it opens. It has no radio buttons, so Tab goes from the list to the Filter box and the buttons. The Filter box, Move to and Activate work as before, and moving to a heading from the Heading List doesn't change the kind NVDA's own list opens on. On a page with none of that kind, NVDA says what JAWS says and opens nothing: "no links", "No headings found", "no form fields were found", "no buttons were found" or "No regions were found on the page". NVDA+F7 is NVDA's own key for the Elements List, and the migration gives it Insert+F6. Insert+F5, Control+Insert+B and Control+Insert+R are NVDA's keys for refreshing a web page, its browse mode settings and reverting its configuration, and the migration takes them only when you let JAWS's keys take NVDA's; otherwise they stay NVDA's. Any other key you give the Elements List in NVDA's Input Gestures opens NVDA's own list with every kind, and so does a JAWS key in a program whose list lacks that kind, such as Excel. When NVDA logs at its debug level, its log says which list a key opened. To have NVDA's own list with every kind for every key, uncheck "Open a list of one kind for each JAWS list key, as JAWS does" in NVDA's Settings, JAWS Migration Assistant.
- **NVDA+Shift+J, then H shows what NVDA said, as JAWS's speech history does.** The tester wrote: "I find the speech history a pain to use. should we make it easier?" To tell us what NVDA said, the tester uses the Speech History add-on: Shift+F11 and Shift+F12 go back and forth through what NVDA said one thing at a time, and F12 copies the one thing it is on, so a report of five things takes five copies and five pastes. Its NVDA+H list shows the newest first. JAWS keeps the last 500 things it said, and has three layered keys for them: Insert+Space, H opens them in its Results Viewer, the oldest first, on the line of the most recent one; Insert+Space, Control+H copies them all to the clipboard; and Insert+Space, Shift+H clears them. Now the assistant keeps the last 500 things NVDA said, one line for each time NVDA spoke, and NVDA+Shift+J, then the same keys do the same. H opens a window called Speech History on the most recent line: Up Arrow goes back through what NVDA said, Control+C copies what you select, Copy all copies everything, Clear empties it, and Escape closes it. Control+H copies it all without opening anything, and NVDA says "Copy speech history to clipboard", as JAWS does. Shift+H says "Speech history cleared" and clears it. So to show us what NVDA says: press NVDA+Shift+J, then Shift+H; do what makes NVDA say it; press NVDA+Shift+J, then Control+H; and press Control+V in GitHub's comment box. What is kept is what you heard, after ClassicSpeech changed it, the parts of each thing two spaces apart, as NVDA's Speech Viewer shows them. What NVDA says while the window is in front isn't kept, so reading the history doesn't change it. It stays in memory only, and is gone when NVDA restarts. The Speech History add-on keeps working as before. The layer's help, which was on H, is now on question mark and F1, JAWS's keys for it (Insert+Space, question mark). A migration takes JAWS's own option for its speech history, on as JAWS comes. To stop keeping a speech history, uncheck "Keep what NVDA says, for NVDA+Shift+J then H, as JAWS's speech history" in NVDA's Settings, JAWS Migration Assistant. See [Speech history](#speech-history).

## What's new in 1.28

From a tester's report:

- **NVDA says what you type in Edge after it starts on the taskbar and goes back to your window.** A tester started NVDA with Control+Alt+N while writing a message in Reddit's chat in Edge. NVDA went back to Edge, as it has since 1.18, and then said nothing the tester typed in the message box but a capital I. NVDA reads Edge's web pages through IAccessible2, as it reads Chrome's, but it can tell whether it reads a program through UI Automation only once its helper is in that program, and it takes the helper in only after all its add-ons have started. The assistant brings Edge back to the front while they start, so Edge's UI Automation focus came first, and NVDA took the message box through UI Automation, which it doesn't otherwise do in Edge. A few keys later NVDA had the page itself as the focus, while the tester typed in the box. NVDA says typed characters "only in edit controls" as set, and a page isn't one, so it was silent. It happened at four of the five starts in the tester's logs that went back to Edge. Now, while NVDA starts, it leaves out the UI Automation focus event of the program you go back to, finds the focus itself once it has started, as for a window that was in front when it started, and asks again how it reads that window. On another computer, with a page like the tester's, NVDA started with its desktop shortcut's key took the message box through UI Automation at each of four starts with 1.27, and through IAccessible2 at each of four starts with 1.28, and said it once. Programs NVDA reads through UI Automation, such as Notepad, are as before, and so is Edge with "Use UI Automation to access Chromium based browser controls" set to Yes. When NVDA logs at its debug level, its log says when this happens. There is nothing to set: it is part of "When NVDA starts with the focus on the taskbar, as Control+Alt+N leaves it, go back to the window you were in".

## What's new in 1.27

From a tester's answer:

- **A migration takes JAWS's "Messages Automatically Read" for Outlook.** Asked whether their JAWS reads an Outlook message as it opens, the tester found the option in Outlook's Quick Settings (Insert+V in Outlook), under Reading Options: "Messages Automatically Read", not checked. That is why their JAWS says nothing when they press Enter on a message. JAWS keeps the option in its settings for Outlook, and JAWS 2026 has it checked as it comes, so a JAWS user who never changed it hears each message read from the top as it opens. Now a migration sets the check box 'Read an Outlook message from the top when it opens, as JAWS's "Messages automatically read" does' to what your JAWS does: your own Outlook settings first, then JAWS's. The tester's JAWS has it off, so it stays off for them, as 1.26 already had it. It is listed with the Settings Center options when you migrate, where you can leave it out, and the report names the JAWS file it came from. With "your settings only", it comes over only if you changed it in JAWS. Nothing changes until you migrate again, and you can check or uncheck it in NVDA's Settings, JAWS Migration Assistant, at any time. A test also checks that the settings 1.25 left behind, when you update, don't turn reading on open back on.

## What's new in 1.26

From a tester's reports:

- **An empty edit field on a web page is said as JAWS says it.** On a reddit post in Edge the tester pressed E to go to the reply box, then Enter. JAWS said "edit, blank, placeholder, Join the conversation". NVDA said "main landmark", then "Join the conversation, edit, multi line, blank". Three things were different:
  - The box has no label, only the grey text "Join the conversation" that goes away when you type: its placeholder. When a field has no label, Edge makes the placeholder its name, and tells screen readers it did; NVDA said it as the name, first. JAWS's scripts for Edge, Chrome and Firefox say an empty edit field as its name and "edit", its states such as "required", "blank", then "placeholder" and the placeholder, then its description, and a name made from the placeholder isn't a name to them. Now NVDA says an empty edit field on a web page that way when the focus moves to it and when you press NVDA+Tab: the reply box is "edit, blank, placeholder, Join the conversation", and GitHub's title box is "Add a title, edit, required, blank, placeholder, Title", where NVDA said "Add a title, edit, required, Title, blank". A field with text in it is said without its placeholder, as before, and without a name made from it.
  - JAWS says "edit" for an edit field of several lines too: its "Announce multi-line edit" option is off as JAWS comes. Now NVDA doesn't say "multi line" for an edit field, anywhere. Braille still shows it.
  - NVDA said "main landmark" when E moved to the box, and again when Enter put the focus in it. In browse mode NVDA leaves the focus where it was, so when Enter puts the focus in a field, NVDA says everything the focus has come into since, even what browse mode's cursor was already in. JAWS's virtual cursor takes the focus with it, so JAWS doesn't say that again. Now, when the focus moves within a web page, NVDA doesn't say again a landmark, region, list or grouping browse mode's cursor was already in. Tab to a field in another landmark still says that landmark.

  To have NVDA's own way back, uncheck 'Say edit fields on web pages as JAWS does: "blank, placeholder" and the placeholder, no "multi line", and no landmark you were already in' in NVDA's Settings, JAWS Migration Assistant.
- **An Outlook message isn't read from the top when you open it any more, as JAWS doesn't read it.** In 1.25 NVDA read a message from the top as it opened, because JAWS seemed to. The tester has since found that JAWS, as they have it, says nothing when they press Enter on a message and reads it only with the arrow keys: what they pasted for 1.25 was JAWS reading line by line. So reading a message as it opens now has a check box of its own, 'Read an Outlook message from the top when it opens, as JAWS's "Messages automatically read" does', off unless you check it. With it off, NVDA comes into a message as NVDA does, and the Outlook First Line Silence add-on keeps the first line quiet, so the tester hears nothing, as with JAWS. The other check box is now 'Say Outlook messages as JAWS does: "send mail link" for an e-mail address, where lists start and end, and no heading for the From line of a quoted message', on as before.
- **NVDA says where a list starts and ends in an Outlook message.** Arrowing through a message with a bulleted list, the tester's JAWS said "list of 3 items" before the first item and "list end" after the last; NVDA said only each bullet and item. NVDA gets each list from Word but leaves it out of Word documents, as its older Word support did. Now, in a message you read (not one you write), NVDA says "list with 3 items" where a list starts and "out of list" after it, as it says lists on web pages, while "Lists" is checked in NVDA's Document Formatting settings, as it is when NVDA comes. This has not been tried in a live Outlook yet.

## What's new in 1.25

From a tester's reports:

- **An Outlook message is read from the top when you open it, as JAWS reads it.** The tester opened the same message with JAWS and with NVDA. JAWS read it straight through: "From: Send Mail Link nvda-addons@nvda-addons.groups.io < Send Mail Link nvda-addons@nvda-addons.groups.io> On Behalf Of Alireza Mamani via groups.io", then the message itself. NVDA said nothing, and then, with the arrow keys, "heading level 1, From:", "link, nvda-addons@nvda-addons.groups.io" and "heading level 1, <". Three things were different:
  - JAWS reads a message you open from the top, as its Outlook settings have it when JAWS comes ("Messages automatically read"). NVDA reads a document as it opens only with "Automatic Say All on page load", one setting for web pages and messages alike, and the migration takes it from JAWS's setting for web pages, which is off as JAWS comes. So NVDA said only the first line of a message, and the Outlook First Line Silence add-on the tester has keeps even that quiet. Now NVDA reads an Outlook message you open from the top, as NVDA+Down Arrow does, and a key stops it as it stops NVDA+Down Arrow. Web pages are as before. Coming back to a message that is already open, with Alt+Tab for example, doesn't read it again, and messages you write are as before.
  - JAWS says "Send Mail Link" for a link to an e-mail address, where NVDA says "link". Now NVDA says "send mail link" for one in an Outlook message, while "Link type" is checked in NVDA's Document Formatting settings, as it is when NVDA comes. Braille shows the link as before.
  - NVDA said "heading level 1" before "From:", and again after each address. When you reply to a message or forward it, Outlook gives the From line of the message it quotes an outline level, so that it can collapse what comes after it, and Word tells NVDA that line is a heading. JAWS says a heading only for text in one of Word's heading styles, and that line isn't. Now, in an Outlook message, NVDA says a heading only for text in a heading style, such as "Heading 1": the headings of a newsletter are said as before.

  The last two are for messages NVDA reads through UI Automation, as it does with a recent Office such as the tester's. To have NVDA say Outlook messages as before, uncheck 'Read an Outlook message from the top when it opens, as JAWS does, with "send mail link" for an e-mail address and no heading for the From line of a quoted message' in NVDA's Settings, JAWS Migration Assistant. Since 1.26 that is two check boxes, and a message is read from the top only if you turn it on: see [What's new in 1.26](#whats-new-in-126).
- **NVDA says a heading that is a link as JAWS does.** On profootballrumors.com the tester pressed H. JAWS said "HEADLINES, heading level 3, Link", "Pro Football Rumors, heading level 1, Link" and "Vikings To Sign P Johnny Hekker, heading level 2, Link". NVDA said "HEADLINES, same page, link, Homepage, heading, level 3", "Pro Football Rumors, same page, link, Home, heading, level 1" and "Vikings To Sign P Johnny Hekker, link, heading, level 2". Each of those headings is a link, and three things differed. First, NVDA called a link to the page you are on a "same page" link: HEADLINES and Pro Football Rumors go to the site's home page, and the tester was on it. JAWS says "same page" only for a link to a place on the page, such as "Skip to content", and now NVDA does too: it says "same page" only when the link's address has a "#". Second, "Homepage" and "Home" are the links' titles, which a page gives links for the mouse pointer. NVDA says them because "Report object descriptions" is checked in its Object Presentation settings when NVDA comes; JAWS says a link's text, not its title. Now NVDA leaves a link's title out in Edge and Chrome (Firefox doesn't tell NVDA which description is a title), and still says a description the page writes for screen readers. Third, NVDA said "link" before "heading, level 3". Now, when H, Shift+H, 1 to 9 or the Elements List moves to a heading that is a link, NVDA says the text, then "visited" if you have been there (on reddit.com the tester's JAWS said "visited, heading level 2"), then the heading and its level, then "link". Tab, K and the arrow keys say links as before. To have NVDA's own way back, uncheck 'Say links on web pages as JAWS does: "same page" only for a link to a place on the page, no link titles, and "link" after a heading' in NVDA's Settings, JAWS Migration Assistant.
- **Migrating JAWS settings: NVDA's "Report link type" follows JAWS's "Identify same page links".** NVDA's only link type is "same page". The migration took it from JAWS's "Identify link type", which is about mail and FTP links, which NVDA doesn't name on web pages.

## What's new in 1.24

From a tester's reports:

- **NVDA no longer says "page 1, section 1" in an Outlook message.** Writing a message in Outlook, the tester pressed Control+Home and heard "page 1, section 1" before the first line. It came at the first line NVDA read in a message: Up Arrow into a reply said it too, and so did Enter after the first word of another reply. JAWS says no page or section in Outlook. Outlook's messages are Word documents, and NVDA says page and section numbers in Word, because "Page numbers" is checked in its Document Formatting settings when NVDA comes. NVDA's own Outlook support leaves them out of messages, but only when NVDA reads Word the older way, through Word's object model. With a recent Office, as the tester has, NVDA reads Word through UI Automation, and there it doesn't leave them out. Now NVDA leaves page, section and column numbers out of Outlook messages. The rest of the formatting is said as before, and so are page numbers in Word itself. To hear page and section numbers in Outlook again, uncheck "Don't say page and section numbers in Outlook messages" in NVDA's Settings, JAWS Migration Assistant.
- **NVDA no longer says "List top" when File Explorer opens a folder.** The tester heard "Items View list, List top:" each time File Explorer opened a folder, and "List top" on the desktop and when Home went back to the first file. JAWS says the first file alone. NVDA itself never says "List top": the words come from the Columns Review add-on, which the tester has. Its "Announce list bounds (top, mono-item, bottom)" is on as it comes, and says "List top" when you come to the first item of a list, "List bottom" at the last, and "Mono-item list" when a list has only one item. JAWS has messages for the top and bottom of a list, but none of its scripts uses them. Now Columns Review says nothing at the ends of a list, in File Explorer, on the desktop and in other programs' lists. If you'd rather have a beep there, choose "beep" under "Announce with" in Columns Review's own settings: the assistant leaves its beeps alone, and the rest of Columns Review works as before. To hear "List top" again, uncheck 'Keep Columns Review from saying "List top" and "List bottom" at the ends of a list' in NVDA's Settings, JAWS Migration Assistant.

## What's new in 1.23

From a tester's answers about typing in a large document:

- **Typing in a large document loses fewer letters.** The tester typed a note at the top of a saved NVDA log in Windows 11's Notepad, and letters and spaces went missing, some came out of order, and NVDA said little of what they typed. It doesn't happen in a new, empty document. On another computer, with NVDA 2026.2 and no other add-ons, the same kind of typing went into a copy of the tester's log, 21 million characters, as real key presses, one every 150 ms: "a outlook message about typing in a large document is here " lost 5 to 23 of its 59 characters each time. Most of that is Notepad's own. In a file that size Notepad takes a fifth to a third of a second to type each character, slower than the keys come, and with NVDA quit it still lost letters in two tries of three. NVDA made it worse. While you are in a document, NVDA listens for changes to its value, and the value of Notepad's document is its whole text: Notepad built all 42 MB of it at every key, which took a tenth of a second more for each character, and the build failed every time, so NVDA never even got the change. A test program that did nothing but listen for the value, with NVDA quit, had Notepad lose 4, 17 and 9 characters. NVDA doesn't use that change for a document anyway: it follows the caret and the text as you type. Now NVDA doesn't listen for the value of a document or a text field of more than one line that it reads that way, and everything else, such as the caret moving and the text changing, comes as before. Notepad is still slow with a file that size, and can still lose a letter. So type your notes in a new document or in GitHub's comment box, not in a saved log, and attach NVDA's log with NVDA+Shift+J, then L (see [What's new in 1.21](#whats-new-in-121)). To have NVDA listen for a document's value again, uncheck "Keep NVDA from having a document build its whole text at every key, which slows typing in a large file" in NVDA's Settings, JAWS Migration Assistant.
- **Fixed: the log noted the L of NVDA+Shift+J, then L as a key the program never typed.** When NVDA logs at its debug level, the assistant notes a key a program types late or never (see [What's new in 1.19](#whats-new-in-119)). The L after NVDA+Shift+J goes to the assistant's command, never to the program, so waiting for it only filled the log with a false "never typed 'l'". Now a key NVDA runs a command for isn't waited for.

## What's new in 1.22

From a tester's reports on version 1.21:

- **The arrow keys stay in an edit field on a web page at its start and end.** Writing a comment on GitHub, the tester pressed Control+Right Arrow at the end of the text. NVDA said "out of edit, button" and was in browse mode on the "Paste, drop, or click to add files" button after the comment box. Right Arrow and Down Arrow at the end did the same. JAWS stays in the comment box. JAWS's Auto Forms Mode is on in the tester's JAWS, so the migration turned on NVDA's nearest option, "Automatic focus mode for caret movement" (NVDA's Settings, Browse Mode). That option does more than JAWS: whenever a caret key can't move any further in a field, NVDA leaves focus mode and runs the key again in browse mode, past the field. JAWS leaves forms mode only when you arrow past a field of one line with Up or Down Arrow. Now, in a field of more than one line, such as GitHub's comment box, and with Left and Right Arrow, Page Up, Page Down and Control with an arrow key in any field, the caret stays in the field, in focus mode. Up or Down Arrow in a field of one line, such as a search box, still goes on in browse mode, as in JAWS, and arrowing into a field still switches to focus mode. To have NVDA leave fields at their edges again, uncheck "Stay in an edit field on a web page when the arrow keys reach its start or end; only Up and Down Arrow leave a field of one line" in NVDA's Settings, JAWS Migration Assistant.
- **NVDA says the Outlook message you move to, not the one you leave.** A tester pressed End in Outlook's Inbox to go to the newest message and heard "unread From joshknnd1982, Subject Re: ...", the message the tester was leaving, which had already been read, and only then the newest message. The tester pressed Enter while NVDA was still saying the first one, and opened the newest message, not the one NVDA had just said. Down Arrow did the same when the next message was unread and the one left wasn't. When the selection moves, Outlook tells NVDA that the name of the message you left changed, and NVDA's focus is still on that message until Outlook's focus event for the new one comes, so NVDA said it again. NVDA's Outlook support takes a message's status, such as unread, from Outlook's selection, which is already the new message, so the message you left was said with the new message's status. JAWS says only the message you move to. Now, when Outlook's focus has left a message, NVDA doesn't say that message again, and says the one you moved to as before. A change of the message you are on is still said. To hear the message you leave again, uncheck "When you move in Outlook's message list, say only the message you come to, not the one you leave" in NVDA's Settings, JAWS Migration Assistant.

## What's new in 1.21

From a tester's reports on version 1.20:

- **A JAWS dictionary for one program changes speech only in that program.** Reading an article about the Chicago Bears in Edge, the tester heard a player's name and the word "job" said wrongly. JAWS keeps a dictionary for each program beside its default one, and uses it only in that program. Freedom Scientific's own dictionary for the Bible program Theophilos says "Job" as "jobe", for the Book of Job. Earlier versions put the rules of every JAWS program dictionary into NVDA's default dictionary, which NVDA uses in every program, so NVDA said "jobe" everywhere. In the same article, a rule from Excel's dictionary, meant for its columns, had NVDA say the word "a" as "eigh" three times ("he deals with eigh concussion"), and a rule from Outlook's said an ellipsis as "dot dot dot". Now the rules of each JAWS program dictionary are in a dictionary of their own (see [Where things are kept](#where-things-are-kept)), which NVDA uses only while you are in that program, before its default dictionary, as JAWS does. Shortly after NVDA starts with version 1.21, the rules an earlier migration put into NVDA's default and voice dictionaries move there, after a backup of NVDA's settings, and NVDA says how many. Your own rules, and the rules from JAWS's default dictionary, stay where they are. NVDA's log shows the text NVDA is given to say before its dictionaries change it, so the log couldn't show what changed the player's name. When NVDA logs at its debug level, the assistant now notes there each dictionary rule that changes what NVDA says, with the JAWS file and line it came from (see [Debug logs](#debug-logs)). There is nothing to set.
- **NVDA no longer says "alert" alone when a GitHub page loads.** A tester who went straight to a repository's page on GitHub heard "Skip to content", then "alert" and nothing more, where JAWS says nothing. As the page finishes loading, GitHub adds an alert with nothing in it. NVDA says an alert in two parts: the text in it, as for any live region, and the alert itself, that is its name, the word "alert" and any control in it that can take the focus. NVDA leaves out an alert only when it has nothing at all under it. GitHub's alert has an empty part under it, so NVDA said "alert" alone. JAWS says an alert's text and nothing else. Now NVDA leaves out an alert with nothing in it: no name, description or text in it or in anything in it, and nothing in it that can take the focus. An alert with anything in it is said as before. To have NVDA say every alert again, uncheck "Don't say "alert" for an alert with nothing in it, as on GitHub pages" in NVDA's Settings, JAWS Migration Assistant.
- **NVDA+Shift+J, then L saves NVDA's log for a GitHub issue.** The tester's log for "issue typing in a large document" never reached the issue. Neither did the logs for three more of their issues that night. GitHub attaches a file of 25 MB at most, and at NVDA's debug level the tester's logs run past 20 MB, so GitHub left only "Failed to upload" in each issue. The document the tester typed in was most likely such a log, open in Windows 11's Notepad with a note typed at its top. That is where their letters and spaces went missing before (see [What's new in 1.19](#whats-new-in-119)). Now NVDA+Shift+J, then L puts NVDA's log, the log of NVDA's run before and the assistant's debug log into one zip file in Documents. So does the NVDA menu: Tools, JAWS Migration Assistant, Save NVDA's log for a GitHub issue. Zipped, a 22 MB log came to a third of a megabyte. NVDA says the file's name and size, and puts its full name on the clipboard. On GitHub, press "Paste, drop, or click to add files", then Control+V and Enter. Type what happened in the comment box, not into the log. See [Debug logs](#debug-logs).

## What's new in 1.20

From a tester's answer about version 1.19: what NVDA+F7 says on a GitHub page right after it loads, and again after Alt+Left. The tester asked for NVDA to behave as JAWS does:

- **NVDA+F7 on a page without links says "no links".** Alt+Left from a GitHub issue took the tester to Edge's New Tab page, which has no links. NVDA+F7 opened an empty Elements List, and NVDA said only "Elements List dialog, tree view"; Down Arrow said nothing. JAWS's Insert+F7 says "no links" there and opens nothing. Now NVDA does the same when its list would open on links. The list remembers the kind of element you chose in it last. If you left it on headings, form fields, buttons or landmarks, it opens as before, even on a page that has none of them, so that you can choose another kind there.
- **Activating a link from the Elements List moves NVDA's cursor to it.** On the page of the tester's repositories, the list opened on "Current page Repositories (48), 10 of 128", the link NVDA's cursor was on, as JAWS's Links List starts on the link at its cursor. The tester chose "reply-to-sender-outlook" and pressed Enter, then went back with Alt+Left, and NVDA+F7 opened on "Current page Repositories (48)" again. NVDA activated the link without moving its cursor there, so the cursor, and the place NVDA goes back to, stayed on Repositories. Now NVDA moves its cursor to the link first, as the list's Move to button does, without saying it, then activates it, as pressing Enter on the link does. Going back with Alt+Left brings you to the link you chose, and NVDA+F7 opens on it. Buttons in the list work the same way. In focus mode, NVDA activates the link as before.
- **The Elements List's item is said once when NVDA fills the list again.** When GitHub changed the page just as NVDA filled its list, the tester heard "Skip to content level 1, 1 of 69" three times, then "Skip to content, 1 of 69". Since version 1.17, NVDA fills the list again when the page changes meanwhile. The list's tree has the focus while NVDA fills it, and Windows gave the focus to each item of the first list as NVDA took it away. NVDA said those items after the dialog appeared, when they were already gone, which is also where "level 1" came from. Now NVDA leaves out a focus event for an item the list no longer has, and says the list's item once. There is nothing to set.

The first two can be turned off with the setting "Show links in NVDA's Elements List as JAWS's Links List does: current page and shortcut keys, without visited, same page or level 0; "no links" on a page without links; activating a link moves to it", in NVDA's Settings, JAWS Migration Assistant.

## What's new in 1.19

From a tester's answers about version 1.18. The tester asked for NVDA to behave as JAWS does:

- **Links in the Elements List are shown as JAWS's Links List shows them.** The tester compared the two on github.com. JAWS said "Homepage ( g then d ), 2 of 34", where NVDA said "Homepage ( g then d ); visited, 2 of 50, level 0". Now a link in NVDA's Elements List (NVDA+F7) is its text, without NVDA's "visited" and "same page", as in JAWS's list. As JAWS does, NVDA puts "current page" before a link the page marks as the one for the page you are on, as GitHub marks the tab you are on: "Current page Code". And it puts a link's shortcut key after its text, as GitHub gives its user and commit links one: "joshknnd1982 Alt+ArrowUp". NVDA also no longer says "level 0" with each item. The list is a tree, and "level 0" only said that the link is at its top, where every link is. The same goes for buttons and form fields. Where headings or landmarks are under others, NVDA still says each one's level in the list. Typing in the list's Filter box finds a link by what the list shows. To have NVDA's own labels back, uncheck "Show links in NVDA's Elements List as JAWS's Links List does: current page and shortcut keys, without visited, same page or level 0" in NVDA's Settings, JAWS Migration Assistant.
- **NVDA's log shows what happens to the keys you type.** The tester typed a note at the top of NVDA's log, open in Windows 11's Notepad. NVDA said nothing, and letters and spaces were missing from the text itself: "It isn't reading what I'm typing" came out "I sn't reetg wt 'mtyping". NVDA says a character when the program types it, not when you press the key, so it can't say a letter the program never typed. The tester's earlier logs show Notepad losing keys in the same way, each time while NVDA was waiting for Notepad: "message" came out "meg". Those logs are from before version 1.15, when Enhanced Control Support read Notepad's whole document 20 times a second. This time the typing came after the log had been saved, so no log shows what held Notepad up. Now, when NVDA logs at its debug level, NVDA's log says when a program types a key late, which keys it never types, and what NVDA was doing meanwhile. Nothing else changes. See [Debug logs](#debug-logs).

## What's new in 1.18

Fixes from a tester's reports on version 1.17. The tester asked for NVDA to behave as JAWS does, and each change below does what JAWS does in the same place:

- **NVDA+F7 never reaches the program.** The tester was in Edge's Downloads panel, pressed Alt+Left, then NVDA+F7 three seconds later. Edge said "Turn on caret browsing?". NVDA has browse mode's commands only while a browse mode document is ready. The Downloads panel's document had stopped being ready, so NVDA had no command for NVDA+F7. It gave the key to Edge, less NVDA's own key, and F7 is Edge's key for caret browsing. JAWS's Insert+F7 never reaches the program. Now a key that opens the Elements List never does either. That is NVDA+F7, or a key the migration gave the list, such as JAWS's Insert+F6 or Insert+F5, whose F6 and F5 would have moved Edge to its address bar or reloaded the page. When the page is still loading, NVDA opens the list as soon as the page is ready, if that takes no more than three seconds and you press nothing else meanwhile. Otherwise NVDA says what JAWS says there: "This feature is only available from within a virtual document, such as a page on the Internet." Wherever NVDA has a command for the key, it runs it as before. There is nothing to set.
- **The Elements List shows what is still on the page.** With 1.17, when a web page took a link away while NVDA filled the list, NVDA filled it again, and if that happened at each of its three tries, the list opened empty. Now a link the page took away is left out, and every other link is listed, as JAWS's Links List lists what is on the page. The same goes for headings, form fields, buttons and landmarks; a heading under one the page took away comes under the heading above that. Typing in the list's Filter box after the page changed works too; before, NVDA stopped with an error there. A heading the page moved is read where it is now, not half from where it was.
- **NVDA started with Control+Alt+N comes up in the window you were in.** The tester heard "Copilot pinned" when NVDA started. That is the name Windows 11 gives the first button of the taskbar when Copilot is pinned there. The focus was already on that button when NVDA started, and NVDA says where the focus is. Windows puts the focus on the taskbar whenever a desktop shortcut's key starts a program, and Control+Alt+N is the key of NVDA's desktop shortcut, so starting or restarting NVDA with it takes you away from your window (NV Access knows this: [nvaccess/nvda#13028](https://github.com/nvaccess/nvda/issues/13028)). NVDA's own restart, from NVDA+Q or after installing an add-on, leaves the focus where it was. JAWS, started with its own desktop shortcut's key, Control+Alt+J, goes back to the window that was active. Now NVDA does too, as it starts and before it says where the focus is: you hear the window you were in, as after Alt+Tab. That is the window Alt+Tab goes back to: the top one that isn't minimized, hidden, on another virtual desktop, or one of Windows' own or NVDA's. When no window is open, or all are minimized, NVDA goes to the desktop. It happens only as NVDA starts: a taskbar you moved to yourself keeps the focus. To leave the focus on the taskbar, uncheck "When NVDA starts with the focus on the taskbar, as Control+Alt+N leaves it, go back to the window you were in" in NVDA's Settings, JAWS Migration Assistant.

## What's new in 1.17

A fix from a tester's report on version 1.15:

- **NVDA's Elements List opens even while a web page is still changing.** A tester opened the jawsMigrator page on GitHub and pressed NVDA+F7 right after NVDA said "Page ready", just as the page showed an alert. NVDA said "Elements List dialog, tree view", but no dialog appeared, and it kept the focus all the same: Enter activated the Issues link on the page behind it, Escape did nothing, NVDA+F7 did nothing, and only Alt+Tab got the tester out. NVDA fills its Elements List in two steps: it finds the page's links, then reads each one's name. GitHub changed the page in between, so a link was no longer where NVDA had found it, and NVDA 2026.2 stopped with an error halfway through making its dialog, which it left unseen with the focus in it. JAWS's Links List (Insert+F7) comes up whatever the page does meanwhile. Now a link, heading or other element that has moved is read where it is now, and when the page changed while NVDA filled the list, NVDA fills it again, so the list shows the page as it is. If the page still won't hold still after three tries, the list opens empty and NVDA says "The page changed while NVDA listed its elements. Press Escape, then NVDA+F7 again.", so you are never left in a dialog you can't see. There is nothing to set: on a page that isn't changing, the list works as before.

## What's new in 1.16

A fix from a tester's report on version 1.15:

- **No smiley in a drive's name, whatever NVDA's speech dictionaries hold.** With 1.15, a tester still heard File Explorer's "Data (D:)" read with a smiley. NVDA's own symbols, with 1.15's rule, leave the colon and parenthesis out, but NVDA applies its speech dictionaries first, and an entry for ":)" in a dictionary changes the drive's name before that rule ever sees it. Such an entry matches anywhere in the text: that is how NVDA's dictionary dialog makes entries unless you choose otherwise, and how the migration brings over a JAWS dictionary rule made only of symbols. JAWS's own dictionary matches whole words, so it never finds ":)" inside "(D:)". Now the colon and parenthesis after a drive letter are taken out before NVDA's speech dictionaries too: "Data left paren D" at the Most punctuation level, "Data D" at Some. At the All level, and when you read by character, NVDA reads the drive's name as before, and a ":)" anywhere else, such as a smiley in an e-mail, is read as your dictionaries say. It is part of "Say a drive's name as JAWS does, without the colon and parenthesis after its letter, as in Data (D:)" in NVDA's Settings, JAWS Migration Assistant, and turns off with it.

## What's new in 1.15

Fixes from a tester's reports on versions 1.13 and 1.14:

- **A drive is said without the ":)" after its letter.** File Explorer names a drive with its letter in parentheses: "Data (D:)". At NVDA's Most punctuation level, which the migration set from your JAWS voice profile, NVDA said every symbol in it, "Data left paren D colon right paren", and the end sounded like a smiley. JAWS says "Data (D", with nothing after the letter. Now NVDA leaves out the colon and closing parenthesis after a drive letter: "Data left paren D" at the Most level, "Data D" at Some. This works wherever a drive is named: This PC, the navigation pane, the address bar, Open and Save As dialogs, and a window's title in Alt+Tab. At the All level NVDA still says every symbol, and reading by character still says each one. A ":)" anywhere else, such as a smiley in an e-mail, is said as before. To hear the colon and parenthesis again, uncheck "Say a drive's name as JAWS does, without the colon and parenthesis after its letter, as in Data (D:)" in NVDA's Settings, JAWS Migration Assistant.
- **NVDA no longer freezes in a large Notepad file.** A tester pasted 21 million characters into Windows 11's Notepad and pressed Control+Home. NVDA stopped responding, and came back only when the tester restarted it with Control+Alt+N, 17 seconds later. Each time they went back to a file of 24 million characters in Notepad, NVDA was stuck for a second or two. The cause was Enhanced Control Support, which the assistant offers to install for controls NVDA doesn't recognize. As it comes, with "Rely on events by default" unchecked, it checks the control you are on 20 times a second for a change in its name, value or state. A document's value is all of its text, so it read the whole file each time, and in Notepad each read took about a quarter of a second. NVDA had time for little else, and when a key made NVDA wait for the caret to move, the checks never let it finish. NVDA follows a document's text itself as you type and move, so these checks add nothing there. Now Enhanced Control Support leaves them off documents and multi-line text fields, such as Notepad's document and NVDA's Log Viewer. It goes on checking everything else, including the controls it adds support for and any window you set up in it with NVDA+Alt+C. To let it check documents again, uncheck "Keep Enhanced Control Support from reading a document's whole text 20 times a second, which can freeze NVDA in a large file" in NVDA's Settings, JAWS Migration Assistant.

## What's new in 1.14

Fixes from a tester's reports on version 1.13:

- **No "3 of 3" when you come to File Explorer, or in Alt+Tab.** Version 1.13 took the row and column out of "Data (D:), row 2, column 1, 3 of 3", but pressing Alt+Tab to get back to This PC still said "Data (D:), 3 of 3", where JAWS says "Data (D:)". Alt+Tab itself said each window's place in the list: "This PC - File Explorer, 2 of 11". JAWS's Alt+Tab says only the window's name. In File Explorer, JAWS says the position as you arrow from drive to drive or file to file, if its "Announce Position and Count" is on, but not when you come to the list from somewhere else. NVDA says the position whenever an item gets the focus. Now Alt+Tab says the window's name alone. File Explorer says "Data (D:)" when you switch to its window, open a folder or Tab to its list, and that includes the file list in Open and Save As dialogs. The arrow keys still say "2 of 3" while "Report object position information" is on (NVDA's Settings, Object Presentation), and NVDA+Tab still says everything. Other lists, menus and tree views haven't changed. To hear the position everywhere again, uncheck "Don't say the position, such as 3 of 3, in Alt+Tab or when you come to a list in File Explorer".
- **Sending NVDA's log.** A tester's NVDA log grew to 24 million characters in ten minutes. Selecting it all in NVDA's Log Viewer froze NVDA for about three seconds at each key press, and the copy never reached the clipboard. [Debug logs](#debug-logs) now says how to attach the log file itself, and what filled that log.

## What's new in 1.13

Fixes from a tester's reports on version 1.12:

- **Quick navigation says the heading, not the landmark it is in.** When you pressed H, NVDA said the landmark or region the heading was in before the heading itself: "main landmark, Welcome to AppleVis, heading, level 1" on applevis.com, "Community actions, region, r/Visible, heading, level 1" on reddit.com. It sounded as if the heading were the main landmark. NVDA says every landmark, region and list a move takes it into, whatever made the move, but JAWS's H says the heading alone. Now, when quick navigation moves to a heading, NVDA leaves out the landmarks, regions, lists, tables and articles around it: "Welcome to AppleVis, heading, level 1". This works for H and Shift+H, the keys 1 to 9 and Move to in NVDA's Elements List (NVDA+F7). A link in or around the heading, and what NVDA adds for it, are still said. D still says the landmark it moves to, and the arrow keys and Tab still say the landmarks and lists they enter. To hear them with H again, uncheck "When quick navigation moves to a heading, don't say the landmark, region or list it is in" in NVDA's Settings, JAWS Migration Assistant.
- **A heading's text comes first again.** Version 1.12 read a heading's level before its text when you pressed H: "heading, level 2, Texans' Nico Collins Likely To Miss Week 3". That came from a report that turned out to be about "main landmark". JAWS says the text first; on reddit.com it says "Feels to good to be true, visited, heading level 2". So NVDA says the text first again, as it does without the assistant: "Texans' Nico Collins Likely To Miss Week 3, link, heading, level 2". Version 1.12's check box is gone.
- **No row and column numbers for drives, files and messages.** In File Explorer, NVDA said "Data (D:), row 2, column 1, 3 of 3", where JAWS says "Data (D:)". Windows lays out drives and files, the windows of Alt+Tab and Outlook's messages in a grid, and NVDA said each item's place in that grid, as it does for a table cell: Alt+Tab said "row 1, column 2", and Outlook "row 2610, column 1, through 13" after every message. JAWS says a row and column only in tables. Now NVDA doesn't say them for an item in a list: "Data (D:), 3 of 3". NVDA+Tab still says them, and table cells in Excel, Word and web pages keep theirs. "3 of 3" follows NVDA's "Report object position information", which the migration set from JAWS's "Announce Position and Count" at your JAWS verbosity level. To hear the row and column again, uncheck "Leave out the row and column numbers of items in lists, such as drives, files and messages".
- **Backspace says what it deletes, even when the program is slow.** A tester pasted a long NVDA log, over 3 million characters, into Windows 11's Notepad, and pressing Backspace there said nothing. NVDA reads the character before the caret, presses Backspace, and says the character once it sees the caret move. In a document like Notepad's it can only see that from Notepad's own notice, if it comes within a tenth of a second. With such a long document Notepad took longer, so NVDA gave up and said nothing. JAWS says the character as it presses Backspace, without waiting. Now, when NVDA gives up, the assistant watches the text around the caret for up to 0.4 seconds more, and as soon as the character is gone NVDA says it, as it would have. Control+Backspace says the word it deletes. In a read-only field, at the start of the text, or when you press another key meanwhile, NVDA does as it always has. To turn this off, uncheck "Say what Backspace deletes, even when the program is slow to delete it".
- **A web page's tabs and toolbar buttons stay in browse mode.** A tester typed an issue's title on github.com, pressed Tab, typed the description, and found themselves in GitHub's search. Tab had gone to the "Write" tab above the text box, not to the text box. NVDA stays in focus mode on a tab, so the letters went to the page, and S opens GitHub's search. The editor's formatting toolbar comes next, and NVDA uses focus mode for anything in a toolbar too. JAWS stays in its virtual cursor on both: its Auto Forms Mode leaves forms mode for tabs, buttons and check boxes, and in the virtual cursor letters are quick navigation keys. Now NVDA does the same. When you move to a tab on a web page, or Tab to a button or check box in a toolbar, NVDA uses browse mode there (it says "browse mode", or plays its sound, when it was in focus mode), and letters you type don't reach the page. Press Tab again to go on to the text box, where NVDA goes to focus mode as always, or Enter to choose a tab or press a button. Once you are in focus mode (NVDA+Space), the arrow keys move from tab to tab, or from button to button in a toolbar, and NVDA stays in focus mode. To keep NVDA's own focus mode there, uncheck "Stay in browse mode when you Tab to a tab or a toolbar button on a web page".
- **Outlook: the log names whatever asks Outlook from elsewhere.** Since version 1.11, when something other than NVDA's main thread asks Outlook for a message's status, the assistant keeps it from getting stuck in NVDA's window, and notes it in NVDA's log. That note named only the thread, such as "Dummy-241", which says nothing about what asked. It now includes what asked, so a log of a message announced without "unread" can show where the question came from. The logs of this report show no message announced without its status: with ClassicSpeech 1.17, every unread message in the Inbox was announced with "unread".

NVDA itself says the landmark a heading is in and a list item's row and column, says nothing for Backspace when a program deletes after it stopped waiting, and uses focus mode on tabs and toolbars, with or without add-ons. The assistant changes that while it is installed.

## What's new in 1.12

A fix from a tester's report on version 1.10, undone in version 1.13, where JAWS turned out to say the text first:

- **Quick navigation says a heading's level first.** When you pressed H to move to the next heading, NVDA read the heading's text first and said that it was a heading last. A tester pressed H on a football news site and heard "main landmark, Texans' Nico Collins Likely To Miss Week 3, link, heading, level 2". NVDA reads whatever quick navigation moves to the way it reads a control you Tab to, text first, headings included. The arrow keys read the same heading with its level first, and JAWS says a heading's level before its text too. Now, when quick navigation moves to a heading, NVDA reads it in the order the arrow keys use: "main landmark, heading, level 2, link, Texans' Nico Collins Likely To Miss Week 3". This works for H and Shift+H, the keys 1 to 9 for headings of one level, and Move to in NVDA's Elements List (NVDA+F7). NVDA says the same words as before, with the level first, and a link's title that quick navigation adds is still said. Everything else keeps NVDA's order: K on the same link still says "Texans' Nico Collins Likely To Miss Week 3, link, heading, level 2", and so does Tab. To hear headings text first again, uncheck "Say a heading's level before its text when you move to it with quick navigation" in NVDA's Settings, JAWS Migration Assistant.

NVDA itself reads a heading text first when quick navigation moves to it, with or without add-ons. The assistant changes that order while it is installed.

## What's new in 1.11

A fix from a tester's report on version 1.8:

- **Opening Outlook puts you in Outlook, not in NVDA's own window.** A tester pressed the Mail key in Microsoft Edge. Outlook came up, but NVDA said "NVDA window", and the focus stayed there until the tester pressed Alt+Tab. NVDA reads a message's status, such as unread or replied, from Outlook itself, and Outlook offers it only after it has lost the focus once since it started. So the first time NVDA asks, it moves the focus for a moment to a "Waiting for Outlook..." window of its own, then lets it go back to Outlook. That works only when NVDA's main thread asks. This time the question came from elsewhere in NVDA, while NVDA was still busy with the switch from Edge: NVDA's window came up, but no "Waiting for Outlook..." dialog did, and the focus never went back. Now only NVDA's main thread asks Outlook, when you reach a message, and if NVDA's own window still has the focus after NVDA waited for Outlook, the focus goes back to the window you were in.

The first time NVDA needs Outlook after Outlook starts, NVDA still says "Waiting for Outlook..." for a moment, as it does without add-ons. Then you are in Outlook. Neither the assistant nor ClassicSpeech asks Outlook for a message's status; the assistant keeps whatever asks from leaving you in NVDA's window.

## What's new in 1.10

A fix from a tester's report on version 1.8:

- **NVDA no longer says "non breaking space" on web pages.** Web pages put a no-break space between words, in place of an ordinary space, all the time. JAWS's symbol file for Eloquence names it "non breaking space" at the Most punctuation level, and the assistant gave the name that level in NVDA. So at NVDA's Most level, NVDA said "non breaking space" wherever a page had one. A tester heard it all through a football news site: "tight end non breaking space", then a link, then "non breaking space", "and defensive tackle non breaking space". Now JAWS's names for spaces and line breaks are said only when you read by character, as NVDA does with its own names for them. Between words, a no-break space is a space again. The same goes for the vertical tab, which Word and HTML e-mail use for a line break: NVDA no longer says "vertical tab" there. Page breaks and tabs are said as before.

If you migrated with an earlier version, the assistant repairs this once, a little after NVDA starts, after backing up NVDA's settings, and tells you what it changed. It only changes the symbols it wrote itself, JAWS's names for spaces and line breaks. Symbols you made yourself in NVDA stay as they are.

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
| Punctuation (`.sbl`) | Symbols you changed become NVDA symbol pronunciations, at the NVDA level where JAWS spoke them. You can also choose JAWS's names for every symbol. Names for spaces and line breaks, such as "non breaking space", are only said when you read by character, as NVDA says its own. |
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
- JAWS's Insert+F4 says "Unloading JAWS" where JAWS Messages are on at your verbosity level. There, the assistant's own check box has NVDA say "Unloading NVDA" as it exits. NVDA has no setting for JAWS's other JAWS Messages.
- JAWS's Outlook option "Messages Automatically Read" (Quick Settings, Insert+V in Outlook) has no NVDA setting, so it sets the assistant's own check box for reading an Outlook message from the top when it opens.

Dictionary rules in more detail:

- Plain words become whole-word entries in NVDA's default dictionary.
- JAWS root words such as `reposition*` keep matching every word that starts with the root.
- Rules for another language are left out.
- Rules for one synthesizer go into NVDA's voice dictionary for the voice you migrate to.
- Rules from a JAWS dictionary for one program, such as Outlook.jdf or Theophilos.jdf, go into a dictionary for that program, which NVDA uses only while you are in it, before its default dictionary, as JAWS does (see [Where things are kept](#where-things-are-kept)). The programs are the ones JAWS's ConfigNames.ini names for it. Rules for parts of Windows JAWS has settings of its own for, such as Windows OS, and for web sites, are listed in the report instead, because NVDA can't tell when you are in them.
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
- The program you are in (Insert+Q), and exiting NVDA (Insert+F4).
- The program's name and version, and the version details (Insert+Control+V), with the assistant's own commands.
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
- A keystroke your input gestures give to an add-on that is turned off or removed doesn't count as taken, since NVDA passes over it. While that add-on was on, the keystroke didn't run NVDA's own command, so the JAWS command takes it even if NVDA's keystrokes stay NVDA's. The add-on's line stays in gestures.ini.
- The report and the wizard say when a keystroke only works in one of NVDA's keyboard layouts, such as "NVDA+j, only in NVDA's desktop keyboard layout".
- Keystrokes NVDA already uses for the same command are left alone.
- Keystrokes NVDA uses for something else stay NVDA's, unless you choose otherwise. That includes JAWS's browse mode keystrokes such as Control+Insert+R: NVDA+Control+R still reloads NVDA's settings.
- Insert+Q is the exception. NVDA exits with it, and JAWS says the program you are in. JAWS exits with Insert+F4, which NVDA doesn't use, so the migration gives Insert+F4 to exiting NVDA. Wherever it does, Insert+Q says the program you are in, as in JAWS, even when NVDA's keystrokes stay NVDA's: exiting NVDA keeps a key, the one JAWS has for it.
- JAWS quick navigation letters can be used in browse mode, so R moves to regions and A to radio buttons, as in JAWS.
- No JAWS keystroke gets an NVDA command that passes the keystroke on to the program. In edit fields, NVDA's sentence commands do that, so Caps Lock+Y would type a Y; those JAWS keystrokes only work in browse mode.
- Versions 1.0 to 1.2 added some keystrokes that do such things. Version 1.3 removes them once, a little after NVDA starts, after backing up NVDA's settings; keystrokes you added yourself are left alone.
- When a new version of the assistant can do a JAWS command it couldn't before, such as Insert+Control+V in version 1.30, or decides one of JAWS's keys anew, such as Insert+Q in version 1.36, it adds that command's keys once, a little after NVDA starts, if you migrated your keystrokes before. They are decided as your migration decided its own: the same JAWS keyboard layouts, and NVDA's keys taken only if you let it take them. A key you gave a command of your own in NVDA's Input Gestures dialog stays yours, unless that command belongs to an add-on that is turned off. NVDA's settings are backed up first, and NVDA says which keys it added.
- Layered keystrokes (such as INSERT+SPACE, then a letter) and braille display keys are listed in the report. NVDA has no layered keys of its own. JAWS's speech history keys, Insert+Space, then H, Control+H or Shift+H, are NVDA+Shift+J, then the same key (see [Speech history](#speech-history)), and so are its notification history keys, N and Shift+N, and D for audio ducking (see [Notification history](#notification-history)), and its Screen Shade keys, F11 and Print Screen (see [Screen curtain](#screen-curtain)).
- Application key maps and JAWS-only commands are listed too.

To learn NVDA, use the JAWS keystroke helper: press NVDA+Shift+J, then K, then a JAWS keystroke. NVDA tells you:

- what that keystroke did in JAWS, from JAWS's own documentation;
- the NVDA command that does the same, and its keystroke; for a JAWS command the assistant does itself, such as Insert+Control+V, also its key after NVDA+Shift+J;
- what the keystroke now does in NVDA.

Insert+Space, which starts JAWS's layered keystrokes, is explained too: the helper says that NVDA+Shift+J starts the assistant's own layer, which has JAWS's speech history keys, its notification keys, D for audio ducking, F11 and Print Screen for the screen curtain, and question mark for its help.

Hold the JAWS key down while you press the rest of the keystroke, as in JAWS. If you press Insert or Caps Lock and let it go before the next key, NVDA gets that key by itself, and the helper says so first: "You let go of Insert before you pressed space, so NVDA got space by itself. For Insert+space, hold Insert down while you press space." Then it tells you what that key does alone.

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
| C | Install ClassicSpeech, or update it to its newest version |
| R | Open the last migration report |
| B | Restore NVDA settings from a backup |
| U | Check for updates |
| I | Hear the JAWS, Windows and NVDA versions on this computer |
| L | Save NVDA's log in Documents as a zip file, small enough to attach to a GitHub issue (see [Debug logs](#debug-logs)) |
| V | Say the name and version of the program you are in, as JAWS's Insert+Control+V (see [Program version](#program-version)) |
| Shift+V | Show the version details, to read and copy |
| Control+V | Copy the version details to the clipboard |
| H | Speech history: what NVDA said, in a window, on the most recent line, as JAWS's Insert+Space, H (see [Speech history](#speech-history)) |
| Control+H | Copy the speech history to the clipboard, one line for each time NVDA spoke |
| Shift+H | Clear the speech history |
| N | Notification history: the notifications Windows and programs sent, the most recent first, as JAWS's Insert+Space, N (see [Notification history](#notification-history)) |
| Shift+N | Say the last notification again, as JAWS's Insert+Space, Shift+N |
| D | Turn audio ducking on or off: "Duck other audio" lowers other programs' sound while NVDA speaks, as JAWS's Insert+Space, D |
| F11 or Print Screen | Turn the screen curtain on or off, as JAWS's Insert+Space, F11 or Print Screen turns Screen Shade on or off: "Screen curtain on" or "Screen curtain off" (see [Screen curtain](#screen-curtain)) |
| Shift+F11 | Say whether the screen curtain is on |
| ? or F1 | Show these commands in a window, a line each, as JAWS's Insert+Space, question mark does |

Any other key, or Escape, leaves the layer. Every command is also in NVDA's Input Gestures dialog, under JAWS Migration Assistant, where you can give it its own keystroke. NVDA+Shift+J itself can be changed there too.

The window that question mark opens is called JAWS Migration Assistant Layer Help. The arrow keys read it, a line for each command, Control+C copies what you select, the Copy button copies it all, and Escape closes it. JAWS shows its own layer's help the same way, in its Results Viewer. The keys and the help come from one list in the assistant, so a command added to the layer is always in its help, and a test checks that this table has the same keys.

NVDA+Shift+J plays the sound JAWS plays when a layered keystroke such as Insert+Space starts. That is the sound JAWS's Default.jcf names (KeyLayerSound.wav, unless you chose another), found in your JAWS sounds and then in the shared ones, as JAWS finds it. It comes from the JAWS you migrated from, or else the newest JAWS on the computer. The assistant keeps a copy in its own folder, so the sound stays after JAWS is uninstalled. If JAWS plays no sound there, or none is found, NVDA+Shift+J beeps. To hear the beep in place of JAWS's sound, uncheck "Play JAWS's layered keystroke sound for NVDA+Shift+J, instead of a beep" in NVDA's Settings, JAWS Migration Assistant.

### Speech history

As JAWS does, the assistant keeps the last 500 things NVDA said, one line for each time NVDA spoke, in the order it said them. The keys after NVDA+Shift+J are JAWS's keys after Insert+Space:

- **H** opens them in a window called Speech History, on the line of the most recent one. NVDA says "Speech History" and that line, as JAWS does, not the whole history. Up Arrow goes back through what NVDA said, and you can select any of it and copy it with Control+C. Copy all copies everything in the window, Clear empties it, and Escape closes it. Press H again and the window shows what NVDA said since.
- **Control+H** copies the whole speech history to the clipboard, without opening anything. NVDA says "Copy speech history to clipboard", as JAWS does.
- **Shift+H** clears it. NVDA says "Speech history cleared", and those words aren't kept either.

To show what NVDA says in a GitHub issue: press NVDA+Shift+J, then Shift+H. Do what makes NVDA say it. Then press NVDA+Shift+J, then Control+H, and paste into the comment box with Control+V.

What is kept is what NVDA sends to the synthesizer, after add-ons such as ClassicSpeech changed it and before speech dictionaries. So it is what you heard, with the parts of each thing two spaces apart, as NVDA's Speech Viewer shows them. While the Speech History window is in front, what NVDA says in it isn't kept, so reading the history doesn't change it. The history is kept in memory only, never on disk, and is gone when NVDA exits or restarts. The Speech History add-on, if you have it, keeps working as before; this doesn't need it. To stop keeping a speech history, uncheck "Keep what NVDA says, for NVDA+Shift+J then H, as JAWS's speech history" in NVDA's Settings, JAWS Migration Assistant; what was kept is forgotten at once. A migration takes this setting from JAWS's own option for its speech history (`SpeechHistory` in Default.jcf, on as JAWS comes).

### Notification history

As JAWS does, the assistant keeps the notifications Windows and programs send while NVDA runs, the last 500 of the last 24 hours: messages from programs, such as Edge's "Loading page", and Windows notifications, such as Outlook's for new mail. It keeps them whether or not NVDA said them, as JAWS does, but not Windows' notice that the keyboard's language changed, or a terminal's output. The keys after NVDA+Shift+J are JAWS's keys after Insert+Space:

- **N** opens a window called Notification History, with a list of the notifications, the most recent first. Enter, or the Details button, shows the whole notification, the program it came from, and when it came. Copy copies the notification you are on, Clear history empties the list, and Escape closes it.
- **Shift+N** says the last notification again, such as one cut short while you typed. With none, NVDA says "No notification", as JAWS does.

What NVDA and your other add-ons say for a notification doesn't change. The history stays in memory only, and is gone when NVDA restarts. To stop keeping it, uncheck "Keep the notifications Windows and programs send, for NVDA+Shift+J then N, as JAWS's notification history" in NVDA's Settings, JAWS Migration Assistant.

**D** after NVDA+Shift+J turns audio ducking on or off, as JAWS's Insert+Space, D does: NVDA says "Duck other audio" when it lowers other programs' sound while it speaks, and "Do not duck other audio" when it doesn't. NVDA's own NVDA+Shift+D still goes through all three of NVDA's choices. NVDA can duck only as an installed copy; a portable copy says "Audio ducking not supported".

### Screen curtain

NVDA's screen curtain is JAWS's Screen Shade: it makes the screen black, so no one can see what is on it. After NVDA+Shift+J, JAWS's keys after Insert+Space work JAWS's way:

- **F11** or **Print Screen** turns the curtain on or off, and NVDA says "Screen curtain on" or "Screen curtain off", as JAWS says "Screen Shade on" or "Screen Shade off". As with JAWS's Screen Shade, it stays on until you turn it off or NVDA restarts. Turning it off also leaves "Make screen black" off in NVDA's Settings, so NVDA starts without it, as NVDA's own key does.
- **Shift+F11** says whether the curtain is on: "Screen curtain on", "Screen curtain off", or, when "Make screen black" is checked in NVDA's Settings, Privacy and Security, "Screen curtain on. NVDA turns it on each time it starts." JAWS has no key for this.

While "Always show a warning when enabling Screen Curtain" is checked in NVDA's Settings, Privacy and Security, as it comes, NVDA asks before the screen goes black, and No has the focus. Uncheck that box in the warning and choose Yes, and NVDA doesn't ask again. Pressing F11 again while the warning is open brings it back and reads it again.

When NVDA starts with the curtain on, because "Make screen black" is checked, NVDA says "Screen curtain on" after it says where you are. NVDA itself says so only on a braille display. To stop it, uncheck 'Say "Screen curtain on" when NVDA starts with the screen curtain on' in NVDA's Settings, JAWS Migration Assistant.

NVDA's own keys still work. NVDA+Control+Escape pressed once turns the curtain on until NVDA restarts, and pressed twice keeps it on after that. NVDA's own "Reports the state of the screen curtain", under Miscellaneous in NVDA's Input Gestures dialog, has no key until you give it one. NVDA+Escape isn't a screen curtain key: a migration gives it JAWS's Insert+Escape, Refresh Screen, which refreshes a web page in browse mode.

### Program version

As JAWS's Insert+Control+V does:

- **Once**, NVDA says the name and version of the program you are in, as JAWS says them: the name and version in the program's file, or a Store app's package, such as "Microsoft Edge Version 154.0.4258.37". In File Explorer and on the desktop, it is the version of Windows. Word, Outlook, PowerPoint and Access are named as JAWS names them, with "Retail" or "Subscription": "Microsoft Outlook Subscription Version 16.0.20326.20158".
- **Twice**, NVDA shows the version details in a window called Version Details, which it reads in browse mode. The arrow keys read it, Shift with the arrow keys selects, Control+C copies what you selected, the Copy button copies it all, and Escape closes it.
- **Control+Insert+Windows+V** copies the version details to the clipboard without opening anything, one line each, and NVDA says "Version Details Copied To Clipboard".

The version details have JAWS's lines, with NVDA's facts. In Outlook they look like this:

```
Version Details Information:
Microsoft Outlook Subscription Version 16.0.20326.20158
NVDA version 2026.2 (2026.2.0.57664)
JAWS Migration Assistant version 1.33
Current settings: normal configuration.
Current application: OUTLOOK.EXE.
Active configuration: outlook.
Current Speech and Sounds Scheme: Classic.
Microsoft Windows 11 Professional Version 25H2 (OS Build 26200.9457), System Type x64
```

NVDA's version and the assistant's are where JAWS has its own version and its scripts' revision; NVDA has no serial number. Current settings is the NVDA configuration profile in use. Active configuration is NVDA's support for the program, as NVDA+Control+F1 names it, or Default where NVDA has none. The scheme is ClassicSpeech's, and is left out when ClassicSpeech isn't running or its schemes are off. The version of Windows is read from the registry as JAWS reads it.

After NVDA+Shift+J, V says the version, Shift+V shows the version details, and Control+V copies them. A migration gives JAWS's keys to these commands, and Insert+Control+V, NVDA's key for its speech settings, only when you let JAWS's keys take NVDA's (see [Everything else about keystrokes](#everything-else-about-keystrokes)). To put them on other keys, find them under JAWS Migration Assistant in NVDA's Input Gestures dialog.

The NVDA menu, Tools, JAWS Migration Assistant has most of the layer's commands, and two more: Migrate JAWS settings to NVDA, Choose what to import, Use JAWS sounds in place of NVDA's sounds, Restore NVDA's own sounds, Copy all JAWS sounds into ClassicSpeech, Install or update ClassicSpeech, Restore NVDA settings from a backup, Open the last migration report, What does a JAWS keystroke do in NVDA?, Check for updates, Open the debug log, Save NVDA's log for a GitHub issue, and Help. The layer's G, P, I, the version keys, the speech history and notification keys, D, and the screen curtain keys are only in the layer and in NVDA's Input Gestures dialog. The NVDA menu, Preferences, has JAWS Migration Assistant settings. The JAWS Migration Assistant category of NVDA's Settings dialog has buttons to choose which JAWS items to import, open NVDA's Input Gestures dialog, use JAWS sounds in place of NVDA's, restore NVDA's own sounds, copy all JAWS sounds into ClassicSpeech, open the assistant, restore a backup, open the last migration report and check for updates. It also says whether JAWS sounds or NVDA's own are playing. That category also has:

- automatic update checks;
- turning on the JAWS settings profile when NVDA starts;
- saying a control's type and state once, even when its label repeats them, and a change once when you activate a control in browse mode (on unless you turn it off; see [What's new in 1.5](#whats-new-in-15) and [What's new in 1.8](#whats-new-in-18));
- saying a system tray icon when you move to it, not each time its program changes it (on unless you turn it off; see [What's new in 1.9](#whats-new-in-19));
- going back to the window you were in when NVDA starts with the focus on the taskbar, as Control+Alt+N leaves it, where NVDA then reads the focus as it reads that program (on unless you turn it off; see [What's new in 1.18](#whats-new-in-118) and [What's new in 1.28](#whats-new-in-128));
- saying what quick navigation moves to without the landmark, region or list it is in, and "blank, placeholder" for an empty edit field (on unless you turn it off; see [What's new in 1.13](#whats-new-in-113), [What's new in 1.31](#whats-new-in-131) and [What's new in 1.36](#whats-new-in-136));
- leaving out the row and column numbers of items in lists, such as drives, files and messages (on unless you turn it off);
- leaving out the position, such as 3 of 3, in Alt+Tab and when you come to a list in File Explorer (on unless you turn it off; see [What's new in 1.14](#whats-new-in-114));
- saying a drive's name without the colon and parenthesis after its letter, as in Data (D:) (on unless you turn it off; see [What's new in 1.15](#whats-new-in-115));
- saying what Backspace deletes, even when the program is slow to delete it (on unless you turn it off);
- keeping Enhanced Control Support from reading a document's whole text 20 times a second, which can freeze NVDA in a large file (on unless you turn it off; see [What's new in 1.15](#whats-new-in-115));
- keeping NVDA from having a document build its whole text at every key, which slows typing in a large file (on unless you turn it off; see [What's new in 1.23](#whats-new-in-123));
- staying in browse mode when you Tab to a tab or a toolbar button on a web page (on unless you turn it off);
- showing links in NVDA's Elements List as JAWS's Links List does: current page and shortcut keys, without visited, same page or level 0; "no links" on a page without links; activating a link moves to it (on unless you turn it off; see [What's new in 1.19](#whats-new-in-119) and [What's new in 1.20](#whats-new-in-120));
- opening a list of one kind for each JAWS list key, as JAWS does: Insert+F7 links, Insert+F6 headings, Insert+F5 form fields, Control+Insert+B buttons and Control+Insert+R regions, each with JAWS's title and no radio buttons, and JAWS's words on a page with none (on unless you turn it off; see [What's new in 1.29](#whats-new-in-129));
- not saying "alert" for an alert with nothing in it, as on GitHub pages (on unless you turn it off; see [What's new in 1.21](#whats-new-in-121));
- staying in an edit field on a web page when the arrow keys reach its start or end, where only Up and Down Arrow leave a field of one line (on unless you turn it off; see [What's new in 1.22](#whats-new-in-122));
- saying only the Outlook message you come to, not the one you leave, when you move in the message list (on unless you turn it off; see [What's new in 1.22](#whats-new-in-122));
- not saying page and section numbers in Outlook messages (on unless you turn it off; see [What's new in 1.24](#whats-new-in-124));
- saying Outlook messages as JAWS does: "send mail link" for an e-mail address, where lists start and end, and no heading for the From line of a quoted message (on unless you turn it off; see [What's new in 1.25](#whats-new-in-125) and [What's new in 1.26](#whats-new-in-126));
- reading an Outlook message from the top when it opens, as JAWS's "Messages automatically read" does (off unless you turn it on, or a migration takes it from that JAWS option; see [What's new in 1.26](#whats-new-in-126) and [What's new in 1.27](#whats-new-in-127));
- reading Outlook's status bar as JAWS does, with Insert+Page Down: its items, such as Items in View and the zoom, without "Status Bar" and the view and zoom buttons (on unless you turn it off; see [What's new in 1.29](#whats-new-in-129));
- keeping the Columns Review add-on from saying "List top" and "List bottom" at the ends of a list (on unless you turn it off; see [What's new in 1.24](#whats-new-in-124));
- keeping the Columns Review and Emoticons add-ons from holding NVDA up each time NVDA switches configuration profiles, as switching programs or browse mode does (on unless you turn it off; see [What's new in 1.34](#whats-new-in-134) and [What's new in 1.35](#whats-new-in-135));
- saying links on web pages as JAWS does: "same page" only for a link to a place on the page, no link titles, and "link" after a heading (on unless you turn it off; see [What's new in 1.25](#whats-new-in-125));
- saying edit fields on web pages as JAWS does: "blank, placeholder" and the placeholder for an empty field, no "multi line", and no landmark you were already in (on unless you turn it off; see [What's new in 1.26](#whats-new-in-126));
- saying Edge and Chrome windows and pages as JAWS does: their titles, without "window", "document", the page's address or Edge's "region", not the page of a tab you are leaving, and not a page's first line the first time you come to it (on unless you turn it off; see [What's new in 1.31](#whats-new-in-131), [What's new in 1.33](#whats-new-in-133) and [What's new in 1.34](#whats-new-in-134));
- saying regions, groups, lists and articles on web pages with JAWS's words: "main region", "group", "list of 2 items", "main region end", and, reading, no banner, search, form, complementary or content information region (on unless you turn it off; see [What's new in 1.34](#whats-new-in-134));
- keeping what NVDA says, for NVDA+Shift+J, then H, Control+H and Shift+H, as JAWS's speech history, without what NVDA dropped before saying it (on unless you turn it off, or a migration takes it from JAWS's option; see [What's new in 1.29](#whats-new-in-129) and [What's new in 1.33](#whats-new-in-133));
- saying "Unloading NVDA" as NVDA exits, where JAWS says "Unloading JAWS", and exiting once it has been said (off unless you turn it on, or a migration takes it from JAWS's JAWS Messages at your verbosity level; see [What's new in 1.37](#whats-new-in-137));
- saying "Screen curtain on" after NVDA says where you are, when NVDA starts with the screen curtain on, which NVDA itself says only on a braille display (on unless you turn it off; see [Screen curtain](#screen-curtain));
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

Enhanced Control Support, as it comes, checks the control you are on 20 times a second. In a document that means reading all of its text each time, which froze NVDA in a large Notepad file, so while the assistant runs, Enhanced Control Support leaves documents and multi-line text fields to NVDA (see [What's new in 1.15](#whats-new-in-115)). Up to version 1.37, the way the assistant checked for a multi-line text field kept NVDA from knowing that a Win32 text field had several lines, so NVDA read the whole text of such a field as a dialog opened, such as the Speech History and the update dialog's release notes, and Enhanced Control Support went on checking those fields (see [What's new in 1.38](#whats-new-in-138)).

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

Errors also go to NVDA's own log. When reporting a problem, attach the debug log and NVDA's log.

To send NVDA's log, press NVDA+Shift+J, then L, right after the problem, or choose Save NVDA's log for a GitHub issue in the NVDA menu, Tools, JAWS Migration Assistant. The assistant puts NVDA's log (`nvda.log`), the log of NVDA's run before (`nvda-old.log`), and its own debug log into one zip file in Documents, named for the time, such as `NVDA log 2026-09-26 00.45.12.zip`. NVDA says the file's name and size, and puts its full name on the clipboard. On GitHub, press the button "Paste, drop, or click to add files" under the comment box, then Control+V and Enter. Type what happened in the comment box, not into the log. GitHub attaches a file of 25 MB at most, and NVDA's log at its debug level often grows past that: GitHub then leaves only `<!-- Failed to upload ... -->` in the issue. Zipped, a tester's 22 MB log came to a third of a megabyte. The logs themselves are left as they are, and nothing opens them. At its debug level, NVDA's log holds every key you pressed and everything NVDA said, passwords included, so attach it only where you would show those.

To find the log yourself, press Windows+R, type `%temp%` and press Enter. NVDA's log is `nvda.log` in that folder. After NVDA has restarted or stopped unexpectedly, the log from before is `nvda-old.log`. Attach the file itself rather than copying it out of the Log Viewer: selecting all of a very long log in the Log Viewer (NVDA menu, Tools, View log) can freeze NVDA for seconds at each key press, because NVDA reads the selection to announce it, and the Log Viewer is part of NVDA. NVDA starts a new log each time it starts, so restart NVDA just before you show the problem, and the log stays short.

When letters go missing as you type, or NVDA doesn't say them, save the log with NVDA+Shift+J, then L, right after it happens, before you type anything about it. Don't type into a log you saved, or into any very large document, to describe the problem: in Windows 11's Notepad, that is where a tester's letters went missing. When NVDA logs at its debug level, the assistant notes there each key a program you type in was slow to type ("jawsMigrator: notepad typed 's' 1240 ms after the key"), each one it never typed ("jawsMigrator: notepad never typed 's'"), and what NVDA was doing meanwhile, which shows whether NVDA or the program held the typing up.

When NVDA says a word wrongly, save the log right after NVDA has said it. NVDA's log shows the text NVDA was given to say ("Speaking [...]") before its speech dictionaries changed it. When NVDA logs at its debug level, the assistant notes there each dictionary rule that changed it, with the rule's comment, which for a rule from JAWS names the file and line it came from: `jawsMigrator: speech dictionary rules change 'the word job': 'Job' -> 'jobe' (default dictionary: From JAWS shared Theophilos.jdf, line 40)`.

A log can also grow quickly because of another add-on. With NVDA 2026.2, Emoticons 38.0.0 uses names NVDA has since replaced, and NVDA writes a warning with a full list of calls each time it does. It does that 176 times each time NVDA switches configuration profiles, which happens whenever you move to or from a program with a profile of its own. In one tester's log that was over 12,000 warnings in ten minutes. JAWS has no emoticons of its own: at the Most punctuation level it says ":)" as "colon right paren". If you don't use Emoticons, disabling it (NVDA menu, Tools, Add-on Store, Installed add-ons) keeps the log short. Emoticons 38.2.0 fixes the warnings but needs NVDA 2026.3.

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
| `speechDicts\jawsApplications\<JAWS configuration>.dic` | Rules from JAWS's dictionaries for single programs, such as `Outlook.dic`, in the format of NVDA's own dictionaries. The line `#Programs:` at the top names the programs NVDA uses them in, by their file names without ".exe". NVDA's Speech dictionaries menu doesn't show them: to change one, open it in Notepad, then restart NVDA |
| `ClassicSpeech\Schemes\<scheme> (from JAWS)` | Migrated ClassicSpeech schemes |
| `ClassicSpeech\Schemes\JAWS Sounds (from JAWS)\Sounds` | Every JAWS sound, ready for ClassicSpeech |

## Limits

- JAWS scripts cannot run in NVDA, and there is no automatic translation. Custom scripts are archived and listed.
- NVDA has no layered keystrokes, frames, graphics labels, color-based highlight detection, Flexible Web, Research It or list view column customization. Those settings are archived and listed.
- Rates and pitches are converted from the percentage JAWS shows, except Eloquence's rate, which keeps JAWS's speed. Two synthesizers can sound a little different at the same percentage, so a voice may need a small adjustment afterwards, in NVDA's voice settings.
- The Insert keystrokes of the Laptop layout, JAWS's rule for times, the silent exit, "Unloading NVDA" as NVDA exits, saying a control's type and state once, saying a system tray icon only when you move to it, saying what quick navigation moves to without what it is in, leaving out a list item's row and column, saying what Backspace deletes in a slow program, browse mode on a web page's tabs and toolbar buttons, the focus going back to Outlook after NVDA waits for it, NVDA's Elements List on a page that is still changing and its key kept from the program, and the focus going back to your window when NVDA starts on the taskbar need the assistant: they stop when it is uninstalled or disabled.
- The first time NVDA needs Outlook after Outlook starts, NVDA still moves the focus to its "Waiting for Outlook..." window for a moment, as it does without add-ons: Outlook offers what NVDA reads only after it has lost the focus once.
- Quick navigation leaves out what it moves into on web pages read through IAccessible2 (Edge, Chrome and Firefox), and for headings and edit fields everywhere. Elsewhere, such as in Word, K, B, F and the other quick navigation keys still say the landmark or list they move into, as NVDA says it. The arrow keys and Tab say them everywhere, as JAWS does.
- JAWS's Say Next Sentence and Say Prior Sentence work in browse mode only: on web pages and in PDFs, and in Word's browse mode. NVDA has no command for them it can use in an edit field, an Outlook message or a Word document you are editing, so they aren't given keys there. With JAWS commands taking NVDA's keys, NVDA+N there is still NVDA's menu. The assistant finds a web page's sentences by their punctuation, so an abbreviation such as "Mr." ends a sentence.
- Backspace is said once the program has deleted, up to half a second after the key. A program slower than that is still silent, as NVDA is without the assistant; the text itself is never changed. While NVDA waits, it can't do anything else.
- Only tabs, and buttons and check boxes in toolbars, keep browse mode. When you Tab to a list, a radio button, a menu or an edit field on a web page, NVDA goes to focus mode there, as it does without the assistant, so letters you type there reach the page. A toolbar button you reach by clicking, or with the arrow keys in focus mode, gets NVDA's own focus mode too.
- NVDA can't tell what changed a system tray icon. A change within a moment of a key you press on the icon is said, whatever made it. Any other change isn't said until you move to the icon again or press NVDA+Tab.
- A control's type and state are only left out of a label when they are at its end, in NVDA's words (or "checkbox", "dropdown" and similar English spellings), right next to where NVDA says them. A page that puts them first, or in another language than NVDA's, is read as it is.
- JAWS voices from synthesizers with no NVDA equivalent on the computer (for example old hardware synthesizers) cannot be used. The report says which ones.
- NVDA's own speech dictionaries are the same in every program, so the assistant uses JAWS's dictionaries for single programs itself, while it runs. NVDA uses them in the programs JAWS's ConfigNames.ini names for them. JAWS also has settings for parts of Windows, such as Windows OS or Windows Media Player, and for web sites; NVDA can't tell when you are in those, so their rules are left out.
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

`tests/plugin_smoke.py` needs wxPython. It loads the add-on as NVDA does, with real menus, and checks the NVDA menu items, the Settings panel, the NVDA+Shift+J commands and their sound (JAWS's, when the computer has JAWS, or the beep when chosen), the check that has NVDA say a control's type and state once, the one that has NVDA say a system tray icon when you move to it, the ones that have quick navigation say a heading without what it is in, leave out a list item's row and column, say what Backspace deletes in a slow program and keep browse mode on a web page's tabs and toolbar buttons, the one that keeps Enhanced Control Support's timer off documents, the one that takes a drive letter's ":)" out before NVDA's speech dictionaries, the guard that keeps the focus in Outlook when NVDA waits for it, the one that keeps NVDA's Elements List working while a web page changes, and that NVDA gets every focus and change notice, and runs every key press, the assistant looks at. It also checks that the assistant still loads, with its Preferences item, Tools submenu, Settings panel and NVDA+Shift+J, when some of its modules can't be loaded, and when every other step of its start fails.

Three further scripts need wxPython and a computer with JAWS or JAWS settings. They change nothing outside a temporary folder:

- `tests/gui_smoke.py` walks through every step of the wizard.
- `tests/settings_dialog_smoke.py` drives JAWS Migration Assistant settings (filters, Select all, Select none, saving) and checks that the wizard and its keyboard layouts follow the saved choice.
- `tests/integration_migration.py` runs a whole migration into an imitation NVDA, checks what it wrote, then restores it, add-ons included.

## Credits

- Written by Josh Kennedy, with Claude.
- The update check and update dialog follow [ClassicSpeech](https://github.com/joshknnd1982/classicspeech-nvda)'s, also under the GPL.
- JAWS, Leasey, Eloquence and other product names belong to their owners. This add-on is not affiliated with Freedom Scientific, Vispero or Hartgen Consultancy.
