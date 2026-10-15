; Inno Setup — สร้าง Setup.exe สำหรับแจกพนักงาน  (ปกติเรียกผ่าน build_release.py ซึ่งส่งชื่อ/เวอร์ชันมาจาก app/config.py)
#ifndef AppName
  #define AppName "PDF Governix"
#endif
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef AppPublisher
  #define AppPublisher "Governix"
#endif
#ifndef AppSlug
  #define AppSlug "PDFGovernix"
#endif
#define AppExe AppName + ".exe"

[Setup]
AppId={{B7D2E4A1-3C59-4F18-A6E0-8D1F5C2B9A47}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppCopyright=Copyright (C) 2026 {#AppPublisher}. All rights reserved.
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=installer
OutputBaseFilename={#AppSlug}_Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

[Tasks]
Name: "desktopicon"; Description: "สร้างไอคอนบนเดสก์ท็อป"; GroupDescription: "ทางลัด:"
Name: "assocpdf"; Description: "ตั้ง {#AppName} เป็นตัวเลือก ""เปิดด้วย"" สำหรับไฟล์ .pdf"; GroupDescription: "การเชื่อมโยงไฟล์:"; Flags: unchecked

[Files]
Source: "dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "{#AppSlug}.pdf"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\{#AppSlug}.pdf"; ValueType: string; ValueData: "PDF Document"; Flags: uninsdeletekey; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\{#AppSlug}.pdf\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExe},0"; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\{#AppSlug}.pdf\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assocpdf

[Run]
Filename: "{app}\{#AppExe}"; Description: "เปิด {#AppName} ตอนนี้"; Flags: nowait postinstall skipifsilent
