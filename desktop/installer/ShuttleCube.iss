#define MyAppName "ShuttleCube"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "ShuttleCube"
#define MyAppExeName "ShuttleCube.exe"

[Setup]
AppId={{5F189F1E-E4FA-4963-93D5-CCCF4FAE85A8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\ShuttleCube
DefaultGroupName=ShuttleCube
DisableProgramGroupPage=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=ShuttleCube-Setup-{#MyAppVersion}-win-x64
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\..\dist\desktop\ShuttleCube\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ShuttleCube"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\ShuttleCube"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "其他选项："

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 ShuttleCube"; Flags: nowait postinstall skipifsilent
