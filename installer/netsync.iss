; NetSync AI installer — Inno Setup script (Phase 6 target: NetSyncAI-Setup.exe)
; Build prerequisite: pyinstaller desktop_agent\agent.spec
; The binary must never contain secrets; pairing uses short-lived codes.

#define AppName "NetSync AI"
#define AppVersion "0.1.0"
#define AppExe "netsync-agent.exe"

[Setup]
AppId={{7E2D9B1A-5F3C-4A1E-9C0D-NETSYNCAI01}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\NetSyncAI
DefaultGroupName={#AppName}
OutputBaseFilename=NetSyncAI-Setup
Compression=lzma2
PrivilegesRequired=lowest          ; per-user install, no admin needed

[Files]
Source: "..\desktop_agent\dist\netsync-agent.exe"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Writable data lives under %LOCALAPPDATA%, not next to the exe
Name: "{localappdata}\NetSyncAI"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"

[Tasks]
Name: "startup"; Description: "Start {#AppName} with Windows"; GroupDescription: "Startup:"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueName: "NetSyncAI"; ValueData: """{app}\{#AppExe}"" run"; \
  Tasks: startup; Flags: uninsdeletevalue

[Run]
; Initialize DB + show pairing instructions on first install
Filename: "{app}\{#AppExe}"; Parameters: "init"; Flags: runhidden
Filename: "{app}\{#AppExe}"; Parameters: "run"; Description: "Launch {#AppName}"; Flags: nowait postinstall

[UninstallRun]
Filename: "{app}\{#AppExe}"; Parameters: "uninstall-cleanup"; Flags: runhidden; RunOnceId: "cleanup"

; TODO Phase 6: LibreOffice detection + optional bundled installer,
; tray app entrypoint, version info resource.
