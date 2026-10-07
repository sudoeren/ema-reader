; Inno Setup script for the Windows installer. Built by .github/workflows/build.yml:
;   iscc /DVersion=1.0.0 packaging\windows.iss
#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{8C2B6F4E-3B0B-4E57-9E0A-5D1F7A2C9B10}
AppName=EMA Reader
AppVersion={#Version}
DefaultDirName={autopf}\EMA Reader
DefaultGroupName=EMA Reader
DisableProgramGroupPage=yes
; installs for the current user, so no administrator password is asked for
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=EMA-Reader-Setup
SetupIconFile=..\static\logo.ico
UninstallDisplayIcon={app}\EMA Reader.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\EMA Reader\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\EMA Reader"; Filename: "{app}\EMA Reader.exe"
Name: "{autodesktop}\EMA Reader"; Filename: "{app}\EMA Reader.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\EMA Reader.exe"; Description: "{cm:LaunchProgram,EMA Reader}"; Flags: nowait postinstall skipifsilent
