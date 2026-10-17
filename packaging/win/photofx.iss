; Inno Setup script for the photofx Windows installer.
;
; Built in CI (see .github/workflows/build.yml) after PyInstaller produced
; dist/photofx.exe and dist/photofx-viewer.exe. Per-user install: no
; admin rights, no UAC prompt.
;
; PHOTOFX_VERSION must be set in the environment (read by the
; preprocessor), e.g. iscc packaging\win\photofx.iss

#define Version GetEnv("PHOTOFX_VERSION")

[Setup]
AppId={{831C3F70-8C16-4FA0-9FCC-A5BA8A361A6C}
AppName=photofx
AppVersion={#Version}
AppPublisher=michaleczky
AppPublisherURL=https://github.com/michaleczky/photofx
AppUpdatesURL=https://github.com/michaleczky/photofx/releases
DefaultDirName={localappdata}\Programs\photofx
DefaultGroupName=photofx
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=photofx
UninstallDisplayIcon={app}\photofx.exe
OutputDir=dist
OutputBaseFilename=photofx-{#Version}-setup

[Files]
Source: "dist\photofx.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\photofx-viewer.exe"; DestDir: "{app}"; Flags: ignoreversion

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; \
    GroupDescription: "Additional icons:"; Flags: unchecked

[Icons]
Name: "{group}\photofx"; Filename: "{app}\photofx.exe"
Name: "{group}\photofx viewer"; Filename: "{app}\photofx-viewer.exe"
Name: "{group}\Uninstall photofx"; Filename: "{uninstallexe}"
Name: "{autodesktop}\photofx"; Filename: "{app}\photofx.exe"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\photofx.exe"; Description: "Launch photofx"; \
    Flags: nowait postinstall skipifsilent
