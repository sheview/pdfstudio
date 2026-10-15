; Inno Setup — สร้าง Setup.exe สำหรับแจกพนักงาน (ดาวน์โหลด Inno Setup ฟรีที่ jrsoftware.org)
; ขั้นตอน: รัน build_windows.bat ก่อน แล้วเปิดไฟล์นี้ด้วย Inno Setup กด Compile -> ได้ installer\PDFStudio_Setup.exe
#define AppName "PDF Studio"
#define AppVersion "1.0.0"
#define AppExe "PDF Studio.exe"

[Setup]
AppId={{6F1B2C5E-7A44-4C0B-9B53-5D0F5A7C1E01}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=installer
OutputBaseFilename=PDFStudio_Setup
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
Name: "assocpdf"; Description: "ตั้ง PDF Studio เป็นตัวเลือก ""เปิดด้วย"" สำหรับไฟล์ .pdf"; GroupDescription: "การเชื่อมโยงไฟล์:"; Flags: unchecked

[Files]
Source: "dist\PDF Studio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "PDFStudio.pdf"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\PDFStudio.pdf"; ValueType: string; ValueData: "PDF Document"; Flags: uninsdeletekey; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\PDFStudio.pdf\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExe},0"; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\PDFStudio.pdf\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assocpdf

[Run]
Filename: "{app}\{#AppExe}"; Description: "เปิด {#AppName} ตอนนี้"; Flags: nowait postinstall skipifsilent
