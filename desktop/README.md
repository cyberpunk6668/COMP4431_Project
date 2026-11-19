# FinPilotPet v15

Windows x64 local desktop companion for the existing FinPilot server. The character is a real multi-frame 2D sprite, not a new 3D model. Its source, credits and separate non-commercial asset terms are in `web/companion/`.

The project's main launcher starts the backend and this floating 2D assistant together. Run `start-finpilot.bat` in the full checkout, or `start-finpilot.cmd` in the compact checkout. `powershell -NoProfile -ExecutionPolicy Bypass -File .\start-desktop.ps1` starts the same project session without opening a browser. Keep its launch window open.

Closing that launch window, pressing Ctrl+C, running the main launcher with `-Stop`, or double-clicking `stop-finpilot.cmd` ends the owned backend and assistant. A backend exit also closes the assistant. Closing a browser tab leaves the project running. Repeated launches reuse the same project session; stop and restart to apply configuration or source changes. The launcher never takes ownership of a separately started service.

Pass `-NoDesktop` to the main launcher for a browser-only session. Missing Node/Electron dependencies are prepared automatically in the external per-project runtime cache. The full checkout can also reuse its installed, matching Electron runtime. The main launcher runs current host source; the old v15 portable EXE is a historical build and does not include the new lifecycle behavior. **Portable builds still require the project backend and Python dependencies.** They contain no Python, model key, broker connection or old chats.

Development: `cd desktop`, `npm ci`, `npm start -- --base-url=http://127.0.0.1:8000`. This direct development command requires a separately running backend. Build the Windows portable executable with `npm run dist`. Versions are locked in package-lock.json. `npm test` checks geometry, input, startup/shutdown, and lifecycle guards. Python `scripts/check_project_lifecycle.py` exercises isolated Windows process trees without models or IBKR.

- Single click: local interaction; double click or Enter: chat panel.
- Drag: pick up and drop; arrow keys: move the focused character.
- Three-dot menu / tray: show, hide, size, reset, click-through and quit.
- Tray “Quit pet” closes only the assistant; the backend remains until the project session stops.
- In the workspace explicitly connect the selected conversation. Other conversations are never automatically scanned. The pet can continue the same selected conversation after the browser closes.
- Sending a question explicitly requests the selected backend engine. Patting, opening the panel, connecting, syncing and animation do not generate model answers or collect market data.
- Closing the chat panel does not delete or cancel a saved backend answer. On a network failure, check the saved conversation before resending.

The host only opens its fixed loopback pages and public HTTPS source links. Renderer Node integration is off, context isolation and sandboxing are enabled, and native IPC is limited to the pet window. It has no screenshot, other-window enumeration, computer-control, microphone or account API. The Python backend continues to hold credentials; never copy `.env` into desktop resources.

The host is an original small implementation informed by [Coopanion](https://github.com/Pal-AI-Lab/Coopanion)'s interaction design. Its AGPL desktop agent/Core and character textures are not bundled. FinPilot uses the separately credited Q-version character assets selected in the project plan.
