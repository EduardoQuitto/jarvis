# J.A.R.V.I.S. CORE — Windows autostart without console window

`start_core_hidden.ps1` starts the official entry point
(`scripts\run_node.py server`) with the windowless project interpreter
(`.venv\Scripts\pythonw.exe`) and no visible terminal. It changes nothing
about Uvicorn, `.env`, or the startup logic itself.

## Why PowerShell + pythonw.exe

`WScript.Shell.Run(cmd, 0)` was tested and is NOT enough, and neither was
`CreateProcess + CREATE_NO_WINDOW` against `python.exe`: the console
binary still produced a window in this environment. The child is therefore
`pythonw.exe` (GUI-subsystem build, never allocates a console — already
verified to run JARVIS directly). Task Scheduler keeps calling PowerShell
(direct `pythonw.exe` as a task action proved unreliable); PowerShell
supervises the child with `WaitForSingleObject` and propagates its exit
code, so Task Scheduler failure/restart semantics keep working.

## `JARVIS_DEBUG` behavior under autostart

- The project `.env` stays untouched: `JARVIS_DEBUG=true` remains
  available for development and manual starts (with reload enabled).
- When started through this autostart launcher, the child process alone
  receives `JARVIS_DEBUG=false`. The override exists only in the child's
  environment — it does not modify `.env` or any persisted global setting.
- Reason: `pythonw.exe` combined with `JARVIS_DEBUG=true` gets stuck in
  Uvicorn StatReload and never serves port 8000. With the override, the
  autostarted CORE runs without StatReload.
- The launcher still uses the official `scripts\run_node.py server` entry
  point, supervises the child, and propagates its exit code.

## Task Scheduler setup (existing `JARVIS CORE` task)

Edit the task action to:

- **Program/script:** `powershell.exe`
- **Add arguments:** `-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\sergi\jarvis\scripts\windows\start_core_hidden.ps1"`
- **Start in:** `C:\Users\sergi\jarvis`

(`-ExecutionPolicy Bypass` applies only to this invocation; it does not
change the system policy.) Keep the existing trigger/settings (e.g. run at
log on / at startup).

## Notes

- The script derives the project root from its own location; moving the
  whole project folder keeps working, only the Task Scheduler action path
  must be updated.
- `pythonw.exe` as a direct Task Scheduler action proved unreliable; run
  through this supervising PowerShell launcher instead.
- No logs are written by the wrapper; Uvicorn output follows the existing
  project logging. Do not commit `*.log` files (already gitignored via `logs/`).
