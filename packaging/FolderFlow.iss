[Setup]
AppName=FolderFlow
AppVersion=1.0.0
AppPublisher=dialp
AppPublisherURL=https://github.com/dialp
AppSupportURL=https://github.com/dialp
AppUpdatesURL=https://github.com/dialp
; Install for current user to avoid needing admin privileges
PrivilegesRequired=lowest
DefaultDirName={autopf}\FolderFlow
; If user installs without admin, it falls back to {localappdata}\Programs\FolderFlow automatically
DefaultGroupName=FolderFlow
DisableProgramGroupPage=yes
OutputBaseFilename=FolderFlow_Setup
Compression=lzma2/max
SolidCompression=yes
SetupIconFile=..\folderFlow-icon.ico
UninstallDisplayIcon={app}\FolderFlow.exe

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\FolderFlow.exe"; DestDir: "{app}"; Flags: ignoreversion
; If you have other files, add them here
; NOTE: PyInstaller builds a standalone executable so this should be all we need.

[Icons]
Name: "{group}\FolderFlow"; Filename: "{app}\FolderFlow.exe"
Name: "{autodesktop}\FolderFlow"; Filename: "{app}\FolderFlow.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FolderFlow.exe"; Description: "{cm:LaunchProgram,FolderFlow}"; Flags: nowait postinstall skipifsilent
