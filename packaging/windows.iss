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
UninstallDisplayIcon={app}\static\logo.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

; what versions before 1.1 left behind: a PyInstaller build
[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\EMA Reader.exe"

[Files]
Source: "..\dist\EMA Reader\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
; Microsoft's setup for WebView2, which draws the window; the build workflow downloads it next to this script
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsWebView2

; the app is its own Python running desktop.py; "EMA Reader.exe" is that Python's windowless program (see build.py)
[Icons]
Name: "{group}\EMA Reader"; Filename: "{app}\python\EMA Reader.exe"; Parameters: """{app}\desktop.py"""; WorkingDir: "{app}"; IconFilename: "{app}\static\logo.ico"
Name: "{autodesktop}\EMA Reader"; Filename: "{app}\python\EMA Reader.exe"; Parameters: """{app}\desktop.py"""; WorkingDir: "{app}"; IconFilename: "{app}\static\logo.ico"; Tasks: desktopicon

; no "skipifsilent": the app updates itself by running this installer silently, and must come back afterwards
[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Microsoft Edge WebView2 kuruluyor..."; Check: NeedsWebView2
Filename: "{app}\python\EMA Reader.exe"; Parameters: """{app}\desktop.py"""; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,EMA Reader}"; Flags: nowait postinstall

; PyTorch and the model, downloaded on the first start, go with the app; the library and the settings stay
[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\EMA Reader\runtime"
Type: filesandordirs; Name: "{app}"

; Windows 11 comes with WebView2 and most Windows 10 computers have received it; without it the window stays empty
[Code]
function HasWebView2(Root: Integer; Key: String): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(Root, Key + '\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version)
    and (Version <> '') and (Version <> '0.0.0.0');
end;

function NeedsWebView2: Boolean;
begin
  Result := not (HasWebView2(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients')
    or HasWebView2(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients')
    or HasWebView2(HKCU, 'Software\Microsoft\EdgeUpdate\Clients'));
end;
