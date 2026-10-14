#ifndef AppVersion
  #error AppVersion is required
#endif
[Setup]
AppId={{61B62CBE-239E-4233-A913-202E485B102A}
AppName=Wallpaper Cutter
AppVersion={#AppVersion}
AppPublisher=Wallpaper Cutter contributors
AppPublisherURL=https://github.com/aytacmalkoc/wallpaper-cutter
DefaultDirName={localappdata}\Programs\Wallpaper Cutter
DefaultGroupName=Wallpaper Cutter
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist\release
OutputBaseFilename=WallpaperCutter-{#AppVersion}-windows-x64-Setup
SetupIconFile=..\..\build\app.ico
UninstallDisplayIcon={app}\wallpaper-cutter.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
[Files]
Source: "..\..\dist\wallpaper-cutter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\Wallpaper Cutter"; Filename: "{app}\wallpaper-cutter.exe"
[Run]
Filename: "{app}\wallpaper-cutter.exe"; Description: "Launch Wallpaper Cutter"; Flags: nowait postinstall skipifsilent
