; Inno Setup — สร้าง Setup.exe สำหรับแจกพนักงาน  (ปกติเรียกผ่าน build_release.py ซึ่งส่งชื่อ/เวอร์ชันมาจาก app/config.py)
#ifndef AppName
  #define AppName "Governix PDF"
#endif
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef AppPublisher
  #define AppPublisher "Governix"
#endif
#ifndef AppSlug
  #define AppSlug "GovernixPDF"
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

[Code]
// ───────── Serial Number: ถามตอนติดตั้งเท่านั้น (ไม่ถามตอนเปิดโปรแกรม) ─────────
// เก็บเฉพาะค่าแฮช SHA-256 ของ "governix-pdf|" + Serial (ตัวพิมพ์ใหญ่ ไม่มีช่องว่าง)
// เปลี่ยน Serial: python -c "import hashlib;print(hashlib.sha256(('governix-pdf|'+'SERIAL ใหม่'.upper()).encode()).hexdigest())"
const
  SerialHash = 'abe2b1628f8836969f920c96a14968433ec86af44cfba75102a59cbc5fe76cbb';

var
  SerialPage: TInputQueryWizardPage;

function NormalizeSerial(S: String): String;
var
  I: Integer;
  C: String;
begin
  Result := '';
  for I := 1 to Length(S) do
  begin
    C := Copy(S, I, 1);
    if (C <> ' ') and (C <> #9) then
      Result := Result + C;
  end;
  Result := Uppercase(Result);
end;

function SerialOk(S: String): Boolean;
begin
  Result := CompareText(GetSHA256OfString('governix-pdf|' + NormalizeSerial(S)), SerialHash) = 0;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  // ติดตั้งแบบเงียบ (IT แจกหลายเครื่อง): ต้องส่ง /SERIAL=xxxx-xxxxxxxxxx มาด้วย
  if WizardSilent and (not SerialOk(ExpandConstant('{param:SERIAL|}'))) then
  begin
    Log('Serial Number ไม่ถูกต้อง — ยกเลิกการติดตั้ง');
    Result := False;
  end;
end;

procedure InitializeWizard();
begin
  SerialPage := CreateInputQueryPage(wpWelcome,
    'Serial Number', 'กรอก Serial Number ของระบบ',
    'ต้องกรอก Serial Number ที่ถูกต้องจึงจะติดตั้งต่อได้ (กรอกเฉพาะตอนติดตั้ง) หากไม่มี Serial ติดต่อผู้ดูแลระบบ');
  SerialPage.Add('Serial Number:', False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = SerialPage.ID then
    if not SerialOk(SerialPage.Values[0]) then
    begin
      MsgBox('Serial Number ไม่ถูกต้อง กรุณาตรวจสอบแล้วลองอีกครั้ง', mbError, MB_OK);
      Result := False;
    end;
end;
