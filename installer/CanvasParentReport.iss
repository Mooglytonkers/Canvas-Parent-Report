; Inno Setup script for Canvas Parent Report 2.1.0.
; Per-user install so a parent is not asked for an administrator password.

#define MyAppName "Canvas Parent Report"
#define MyAppVersion "2.1.0"
#define MyAppPublisher "Cooper Street Press"
#define MyAppExeName "CanvasParentReport.exe"
#define MyAppId "{{8C4E2A71-5B19-4D33-9F60-2A7C1E8B44D0}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Canvas Parent Report
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=CanvasParentReport-Setup-2.1.0
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
