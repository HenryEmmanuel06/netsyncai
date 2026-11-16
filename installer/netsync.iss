; NetSync AI installer — Inno Setup script
; Builds NetSyncAI-Setup.exe from the PyInstaller windowed build.
; Prerequisite: pyinstaller desktop_agent\agent.spec
;
; Behavior:
;   - per-user install (no admin required)
;   - no-arg launch = tray/GUI app (no console window)
;   - optional "start with Windows"
;   - registers the netsync:// protocol so the website's pairing
;     deep link opens the app with the code filled in
;   - uninstall stops the running instance and removes app data

#define AppName "NetSync AI"
#define AppVersion "0.2.0"
#define AppPublisher "NetSync AI"
#define AppExe "netsync-agent.exe"
#define AppURL "https://github.com/HenryEmmanuel06/netsyncai"

[Setup]
AppId={{7E2D9B1A-5F3C-4A1E-9C0D-NETSYNCAI01}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
DefaultDirName={localappdata}\Programs\NetSyncAI
DefaultGroupName={#AppName}
OutputDir=..\release
OutputBaseFilename=NetSyncAI-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
SetupIconFile=..\desktop_agent\assets\netsync.ico
UninstallDisplayIcon={app}\{#AppExe}
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\desktop_agent\dist\netsync-agent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\desktop_agent\assets\netsync.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\netsync.ico"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "startup"; Description: "Start {#AppName} automatically when I sign in"; GroupDescription: "Startup:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Icons:"; Flags: unchecked

[Registry]
; netsync:// deep links (pairing approval from the website)
Root: HKCU; Subkey: "Software\Classes\netsync"; \
  ValueType: string; ValueName: ""; ValueData: "URL:NetSync AI Protocol"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\netsync"; \
  ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\netsync\DefaultIcon"; \
  ValueType: string; ValueName: ""; ValueData: "{app}\netsync.ico"
Root: HKCU; Subkey: "Software\Classes\netsync\shell\open\command"; \
  ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""

; autostart: no args → tray app (GUI mode)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "NetSyncAI"; ValueData: """{app}\{#AppExe}"""; \
  Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; \
  Description: "Launch {#AppName} (tray)"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/IM netsync-agent.exe /F /T"; Flags: runhidden; RunOnceId: "killagent"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\NetSyncAI"
