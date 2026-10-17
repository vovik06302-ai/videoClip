; Скрипт Inno Setup для сборки единого установщика MusicVideoStudio_Setup.exe
#define MyAppName "MusicVideoStudio"
#define MyAppTitle "Локальная ИИ-студия музыкальных клипов"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppPublisher "MusicVideoStudio"
#define MyAppURL "https://github.com/vovik06302-ai/videoClip"
#define MyAppExeNameDesktop "MusicVideoStudio_Desktop.exe"
#define MyAppExeNameWeb "MusicVideoStudio_Web.exe"

[Setup]
AppId={{8E94A7F2-5C2D-4C6B-9E8A-3F1D2B4A6C90}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppTitle}
DisableProgramGroupPage=yes
; Разрешаем установку без прав администратора в профиль пользователя при необходимости
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=Output
OutputBaseFilename=MusicVideoStudio_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Упаковываем всё содержимое собранной папки dist\MusicVideoStudio
Source: "dist\MusicVideoStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; Создаём папку projects с полными правами на запись для пользователя
Name: "{app}\projects"; Permissions: users-modify

[Icons]
; Ярлыки в меню «Пуск»
Name: "{group}\{#MyAppTitle} (Desktop GUI)"; Filename: "{app}\{#MyAppExeNameDesktop}"; WorkingDir: "{app}"
Name: "{group}\{#MyAppTitle} (Web Server :8765)"; Filename: "{app}\{#MyAppExeNameWeb}"; WorkingDir: "{app}"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"

; Ярлыки на Рабочем столе
Name: "{autodesktop}\{#MyAppTitle} (Desktop)"; Filename: "{app}\{#MyAppExeNameDesktop}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{autodesktop}\{#MyAppTitle} (Web)"; Filename: "{app}\{#MyAppExeNameWeb}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeNameDesktop}"; Description: "Запустить {#MyAppTitle} (Desktop GUI)"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#MyAppExeNameWeb}"; Description: "Запустить {#MyAppTitle} (Web Server)"; Flags: nowait postinstall skipifsilent unchecked
