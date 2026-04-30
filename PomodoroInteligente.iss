; Pomodoro Inteligente — Inno Setup Script
; Requires: Inno Setup 6+ (https://jrsoftware.org/isinfo.php)

#define AppName "Pomodoro Inteligente"
#define AppVersion "1.0"
#define AppPublisher "obrenoalvim"
#define AppURL "https://github.com/obrenoalvim/smartPomodoro"
#define AppExeName "Pomodoro Inteligente.exe"

[Setup]
AppId={{B7C4D3E2-5F6A-4B8C-9D0E-1F2A3B4C5D6E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=PomodoroInteligente_Setup
SetupIconFile=pomodoro.ico
WizardImageFile=logo.png
WizardSmallImageFile=logo.png
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar ícone na Área de Trabalho"; GroupDescription: "Ícones adicionais:"
Name: "startup"; Description: "Iniciar automaticamente com o Windows"; GroupDescription: "Inicialização:"; Flags: unchecked

[Files]
Source: "dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExeName}"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Iniciar {#AppName} agora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
