; GraphLab — установщик (Inno Setup 6+)
; Сборка: "C:\Program Files\Inno Setup 7\ISCC.exe" installer.iss

#define MyAppName "GraphLab"
#define MyAppVersion "1.0.5"
#define MyAppPublisher "Barinov"
#define MyAppExeName "GraphLab.exe"

[Setup]
AppId={{985DC85F-EA90-44E1-9D40-7FAD18EBA0A5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; По умолчанию — Program Files (64-битная папка на 64-битной системе)
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=out
OutputBaseFilename=GraphLab-Setup-{#MyAppVersion}
SetupIconFile=GraphLab.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
; Галочка создания ярлыка на рабочем столе, по умолчанию включена
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные задачи:"

[Files]
; Весь onedir-бандл: GraphLab.exe + _internal\
Source: "dist\GraphLab\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Comment: "Запустить {#MyAppName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Папки автосохранения не трогаем (%APPDATA%\GraphLab) — данные пользователя
