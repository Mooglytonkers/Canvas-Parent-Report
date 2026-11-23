; Inno Setup script for Canvas Parent Report 2.2.0.
; Per-user install so a parent is not asked for an administrator password.
;
; AppId stays the same across versions, so a newer setup is an in-place
; upgrade into the folder the parent already chose (UsePreviousAppDir).
; Settings, the Canvas token, and the scheduled task live outside {app}:
; %APPDATA%\CanvasParentReport, Windows Credential Manager, and Task
; Scheduler. This script does not delete them.
;
; CloseApplications closes CanvasParentReport.exe if it still has files
; open. RestartApplications is for a parent who double-clicks the setup
; while the window is open. The in-app updater passes
; /NORESTARTAPPLICATIONS and opens the app itself after setup exits, so
; that path does not start two copies.

#define MyAppName "Canvas Parent Report"
#define MyAppVersion "2.2.0"
#define MyAppPublisher "Cooper Street Press"
#define MyAppExeName "CanvasParentReport.exe"
#define MyAppId "{{8C4E2A71-5B19-4D33-9F60-2A7C1E8B44D0}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppMutex=CanvasParentReportMutex
DefaultDirName={localappdata}\Canvas Parent Report
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
CloseApplications=yes
RestartApplications=yes
CloseApplicationsFilter=CanvasParentReport.exe
OutputDir=Output
OutputBaseFilename=CanvasParentReport-Setup-2.2.0
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
LicenseFile=..\LICENSE

[Tasks]
Name: "desktopicon"; Description: "Add a shortcut on the desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\CanvasParentReport\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Open Canvas Parent Report"; Flags: nowait postinstall skipifsilent
