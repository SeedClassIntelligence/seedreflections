# SeedReflections Capture (browser extension)

Saves the one AI conversation you have open to your own SeedReflections archive. It reads the page only when you click the toolbar button, shows you what it found, and sends it only after you click **Save**.

Supported pages: ChatGPT (chatgpt.com), Claude (claude.ai), Gemini (gemini.google.com). For everything else, and for complete history, use each service's data export and import it in SeedReflections.

## Try it (unpacked)
1. Chrome → `chrome://extensions` → turn on Developer mode → **Load unpacked** → choose this `extension` folder.
2. In SeedReflections open Settings, create an API connection (name it "Browser extension"), and copy the token.
3. Click the extension icon, paste your SeedReflections address and the token, press **Connect**, and approve Chrome's prompt (it covers that one address only).
4. Open a conversation, click the icon, **Read this conversation**, check the preview, **Save to SeedReflections**.

For a local install the address is `http://127.0.0.1:8476` (or your port). Plain http is accepted only for localhost.

## What it can and cannot do
- Permissions: `activeTab` (the page you clicked on, for that moment), `scripting` (to read it), `storage` (to remember your address and token). No standing access to any site, no background process, no always-on content script.
- Network: only to the SeedReflections address you entered. No analytics, no third parties.
- Only messages loaded on the page are captured. Scroll up to load older ones first.
- A re-save of the same conversation updates the same entry; it never overwrites a fuller copy you imported from an export file (captures are stored under their own id).
- Your token is kept in this browser's extension storage. Disconnect removes it and the permission.

## Tested, and not
Tested: the readers against pages built to copy each service's structure, the payload and delivery against a real SeedReflections server (including re-save and wrong token), and the real extension loading in Chromium with its popup and address checks.
Not tested: capture on the live ChatGPT, Claude and Gemini sites (their layouts change, and the readers were written from their current structure, not run against a logged-in account), and the Chrome permission prompt and toolbar-click flow. Test with your own accounts before publishing. If a reader stops working, the extension says so and points to the export route.

## Publishing to the Chrome Web Store
- A developer account in the company's name (one-time fee).
- Single purpose statement: "Save the AI conversation the user has open to their own SeedReflections archive."
- Justify each permission as above, plus the optional host permissions, which are requested at run time for the one address the user enters.
- Link the live Privacy page and describe the data handled (conversation text the user chooses to save, and the user's token). Disclose that data goes only to the user's own server.
- Package: zip the contents of this folder (not the folder itself).
