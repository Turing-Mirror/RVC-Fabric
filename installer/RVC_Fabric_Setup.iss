; RVC Fabric — Windows installer (Inno Setup 6)
; 企业/独立软件常用安装器技术，不要用自写 Tk 向导替代本脚本。
;
; 构建（在仓库根，先打出 payload）：
;   python scripts/build_setup.py
;   → 调用 ISCC 编译本文件 → dist/RVC_Fabric_Setup.exe
;
; 需要本机安装 Inno Setup 6：
;   https://jrsoftware.org/isinfo.php
;   默认路径: C:\Program Files (x86)\Inno Setup 6\ISCC.exe
;
; 用户动线：
;   Setup.exe（本安装器）安装薄包：启动器 + 主界面 + 源码配置
;   → 启动器从 CNB 补全 Runtime（分版）+ engine-core（共用）+ VB-Cable
;   → 主界面 / 社区音色（LFS）

#define MyAppName "RVC Fabric"
#define MyAppNameCN "RVC Fabric · 图灵镜"
#define MyAppVersion "1.1.1"
#define MyAppPublisher "Turing-Mirror"
#define MyAppURL "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases"
#define MyAppId "{{A1B2C3D4-E5F6-4789-ABCD-EF1234567890}"

; Payload 由 scripts/build_setup.py 生成（相对本 .iss 的路径）
#ifndef PayloadDir
  #define PayloadDir "..\dist\RVC_Fabric_Setup_payload"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef OutputBase
  #define OutputBase "RVC_Fabric_Setup"
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 不要求管理员（装到用户目录）；若改 Program Files 请改 PrivilegesRequired=admin
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBase}
SetupIconFile=
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}
; 安装说明
InfoBeforeFile=
LicenseFile=
; 关闭完成后重启提示
CloseApplications=no
RestartApplications=no
; 目录页允许浏览
DisableDirPage=no
UsePreviousAppDir=yes
; 向导语言：有简中语言包则优先
ShowLanguageDialog=no

[Languages]
; 安装向导整体中文：简中语言文件随仓库自带（installer/ChineseSimplified.isl，
; UTF-8 带 BOM），相对本 .iss 引用，不依赖打包机的 Inno 语言包。
; 英文仅作非中文系统的兜底（ShowLanguageDialog=no 时按系统语言自动匹配，
; 无匹配则取第一项 = 简中）。
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
chinesesimplified.BeveledLabel=RVC Fabric 安装程序
english.BeveledLabel=RVC Fabric Setup

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: checkedonce
; 显卡分版：互斥，写入 package_meta 供启动器下载对应 Runtime
Name: "gpu_nvidia"; Description: "NVIDIA 显卡（CUDA，推荐大多数 N 卡）"; GroupDescription: "选择显卡分版（安装后启动器将下载对应 Runtime）:"; Flags: exclusive checkedonce
Name: "gpu_amd"; Description: "AMD / Intel 显卡（DirectML）"; GroupDescription: "选择显卡分版（安装后启动器将下载对应 Runtime）:"; Flags: exclusive
Name: "gpu_nvidia50"; Description: "NVIDIA 50 系（RTX 50xx / Blackwell）"; GroupDescription: "选择显卡分版（安装后启动器将下载对应 Runtime）:"; Flags: exclusive

[Files]
; 薄包：壳层 + 启动器 + 主界面；不含 Runtime / engine-core / VB-Cable
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName} 启动器"; Filename: "{app}\启动器.exe"; WorkingDir: "{app}"; Comment: "首次补全环境 / 快捷设置"
Name: "{group}\{#MyAppName}"; Filename: "{app}\变声器.exe"; WorkingDir: "{app}"; Comment: "RVC Fabric 主界面"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName} 启动器"; Filename: "{app}\启动器.exe"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\变声器.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\启动器.exe"; Description: "打开启动器（自动补全 Runtime 运行环境）"; Flags: nowait postinstall skipifsilent; WorkingDir: "{app}"

[UninstallDelete]
; 用户下载的 Runtime / 音色体积大，默认不在卸载时删除 User_Data 与 Runtime
; 若需干净卸载可改为删除（谨慎）
; Type: filesandordirs; Name: "{app}\Runtime"
; Type: filesandordirs; Name: "{app}\User_Data"

[Code]
function GpuVariant: String;
begin
  if WizardIsTaskSelected('gpu_amd') then
    Result := 'amd'
  else if WizardIsTaskSelected('gpu_nvidia50') then
    Result := 'nvidia50'
  else
    Result := 'nvidia';
end;

function GpuLabel(const V: String): String;
begin
  if V = 'amd' then
    Result := 'AMD/Intel DirectML'
  else if V = 'nvidia50' then
    Result := 'NVIDIA 50 系 CUDA'
  else
    Result := 'NVIDIA CUDA';
end;

function AccelDefault(const V: String): String;
begin
  if V = 'amd' then
    Result := 'dml'
  else
    Result := 'cuda';
end;

procedure WriteTextFile(const FileName, Content: String);
begin
  if not ForceDirectories(ExtractFilePath(FileName)) then
  begin
    Log('ForceDirectories failed: ' + ExtractFilePath(FileName));
    Exit;
  end;
  SaveStringToFile(FileName, Content, False);
end;

procedure WritePackageMeta;
var
  V, Path, Json, UseDml: String;
begin
  V := GpuVariant;
  if V = 'amd' then
    UseDml := 'true'
  else
    UseDml := 'false';
  Path := ExpandConstant('{app}\package_meta.json');
  Json :=
    '{' + #13#10 +
    '  "variant": "' + V + '",' + #13#10 +
    '  "label": "' + GpuLabel(V) + '",' + #13#10 +
    '  "accel_default": "' + AccelDefault(V) + '",' + #13#10 +
    '  "use_dml": ' + UseDml + ',' + #13#10 +
    '  "tagged": true,' + #13#10 +
    '  "install_via": "inno_setup",' + #13#10 +
    '  "runtime_channel": "cnb_release",' + #13#10 +
    '  "runtime_release_tag": "RVC-runtime",' + #13#10 +
    '  "cnb_repo": "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases"' + #13#10 +
    '}';
  WriteTextFile(Path, Json);
  Log('Wrote ' + Path);
end;

procedure WriteSetupPending;
var
  V, Path, Json: String;
begin
  V := GpuVariant;
  Path := ExpandConstant('{app}\User_Data\setup_pending.json');
  Json :=
    '{' + #13#10 +
    '  "pending_runtime": true,' + #13#10 +
    '  "variant": "' + V + '",' + #13#10 +
    '  "install_via": "inno_setup"' + #13#10 +
    '}';
  WriteTextFile(Path, Json);
  Log('Wrote ' + Path);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    WritePackageMeta;
    WriteSetupPending;
  end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var
  S: String;
begin
  S := '';
  if MemoDirInfo <> '' then
    S := S + MemoDirInfo + NewLine + NewLine;
  S := S + '显卡分版: ' + GpuLabel(GpuVariant) + NewLine;
  S := S + '安装后启动器将从 CNB 下载 Runtime（按显卡）与 engine-core（共用，约 700MB+），需联网。' + NewLine;
  if MemoTasksInfo <> '' then
    S := S + NewLine + MemoTasksInfo;
  Result := S;
end;
