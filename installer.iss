; Inno Setup script for ForTheMix
; Build the app first:  pyinstaller forthemix.spec
; Then compile this with Inno Setup (iscc installer.iss) to produce Setup.exe.

#define AppName "ForTheMix"
#define AppVersion "0.1.0"
#define AppPublisher "OMG Events"
#define AppExe "ForTheMix.exe"

[Setup]
AppId={{9F1D3B4E-7A21-4C0E-8E2A-FORTHEMIX0001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputBaseFilename=ForTheMix-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Files]
; The PyInstaller one-folder output.
Source: "dist\ForTheMix\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
