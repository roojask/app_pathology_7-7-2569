; Script generated for Pathology Voice Assistant Installer

[Setup]
AppName=Pathology Voice Assistant
AppVersion=1.0
AppPublisher=Pathology Lab
DefaultDirName={autopf}\Pathology Voice Assistant
DefaultGroupName=Pathology Voice Assistant
OutputDir=c:\app_pathology_7-7-2569-main\installer_output
OutputBaseFilename=PathologyApp_Setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Tasks]
Name: "desktopicon"; Description: "สร้างไอคอนบนหน้าจอ Desktop"; GroupDescription: "ทางลัดเพิ่มเติม:"; Flags: unchecked

[Files]
; ดึงไฟล์ทั้งหมดจากโฟลเดอร์ที่บิลด์ (รวม _internal, dlls, templates และ assets)
Source: "c:\app_pathology_7-7-2569-main\dist\PathologyApp\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "c:\app_pathology_7-7-2569-main\data\assets\*"; DestDir: "{app}\data\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "c:\app_pathology_7-7-2569-main\bin\*"; DestDir: "{app}\bin"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "c:\app_pathology_7-7-2569-main\models\*"; DestDir: "{app}\models"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Pathology Voice Assistant"; Filename: "{app}\PathologyApp.exe"
Name: "{group}\ถอนการติดตั้งโปรแกรม"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Pathology Voice Assistant"; Filename: "{app}\PathologyApp.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PathologyApp.exe"; Description: "เปิดโปรแกรมทันทีหลังติดตั้งเสร็จ"; Flags: nowait postinstall skipifsilent