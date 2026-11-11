# FinPilotPet v15

Windows x64 local desktop companion for the existing FinPilot server. The character is a real multi-frame 2D sprite, not a new 3D model. Its source, credits and separate non-commercial asset terms are in `web/companion/`.

From the project root, run `powershell -ExecutionPolicy Bypass -File .\start-desktop.ps1`. It reuses a verified FinPilot server or starts the project's installed Python environment. **The portable EXE still requires the FinPilot project backend and its Python dependencies.** It does not contain Python, a model key, a broker connection or old chats.

Development: `cd desktop`, `npm ci`, `npm start -- --base-url=http://127.0.0.1:8000`. Build the Windows portable executable with `npm run dist`. Versions are locked in package-lock.json. `npm test` checks the host's geometry and input contracts.

- Single click: local interaction; double click or Enter: chat panel.
- Drag: pick up and drop; arrow keys: move the focused character.
- Three-dot menu / tray: show, hide, size, reset, click-through and quit.
- In the workspace explicitly connect the selected conversation. Other conversations are never automatically scanned. The pet can continue the same selected conversation after the browser closes.
- Sending a question explicitly requests the selected backend engine. Patting, opening the panel, connecting, syncing and animation do not generate model answers or collect market data.
- Closing the chat panel does not delete or cancel a saved backend answer. On a network failure, check the saved conversation before resending.

The host only opens its fixed loopback pages and public HTTPS source links. Renderer Node integration is off, context isolation and sandboxing are enabled, and native IPC is limited to the pet window. It has no screenshot, other-window enumeration, computer-control, microphone or account API. The Python backend continues to hold credentials; never copy `.env` into desktop resources.

The host is an original small implementation informed by [Coopanion](https://github.com/Pal-AI-Lab/Coopanion)'s interaction design. Its AGPL desktop agent/Core and character textures are not bundled. FinPilot uses the separately credited Q-version character assets selected in the project plan.
