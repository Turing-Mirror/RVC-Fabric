; 简体中文 — Inno Setup 6 安装向导语言文件（RVC Fabric 随仓库自带）
; 放在 installer/ 内并由 RVC_Fabric_Setup.iss 以相对路径引用，
; 不依赖打包机的 Inno Setup 是否安装了官方简中语言包。
; 保存为 UTF-8（带 BOM）。缺失的条目编译时会回落英文并给出警告，不影响构建。

[LangOptions]
LanguageName=简体中文
LanguageID=$0804
LanguageCodePage=936

[Messages]

; *** 应用程序标题
SetupAppTitle=安装
SetupWindowTitle=安装 - %1
UninstallAppTitle=卸载
UninstallAppFullTitle=%1 卸载

; *** 通用
InformationTitle=信息
ConfirmTitle=确认
ErrorTitle=错误

; *** SetupLdr 消息
SetupLdrStartupMessage=现在将安装 %1。是否继续？
LdrCannotCreateTemp=无法创建临时文件。安装中止
LdrCannotExecTemp=无法执行临时目录中的文件。安装中止
HelpTextNote=

; *** 启动错误消息
LastErrorMessage=%1。%n%n错误 %2: %3
SetupFileMissing=安装目录中缺少文件 %1。请修正该问题或获取程序的新副本。
SetupFileCorrupt=安装文件已损坏。请获取程序的新副本。
SetupFileCorruptOrWrongVer=安装文件已损坏，或与此版本的安装程序不兼容。请修正该问题或获取程序的新副本。
InvalidParameter=命令行中传递了无效的参数:%n%n%1
SetupAlreadyRunning=安装程序正在运行。
WindowsVersionNotSupported=此程序不支持当前计算机运行的 Windows 版本。
WindowsServicePackRequired=此程序需要 %1 Service Pack %2 或更高版本。
NotOnThisPlatform=此程序无法在 %1 上运行。
OnlyOnThisPlatform=此程序必须在 %1 上运行。
OnlyOnTheseArchitectures=此程序只能安装在为下列处理器架构设计的 Windows 版本上:%n%n%1
WinVersionTooLowError=此程序需要 %1 版本 %2 或更高。
WinVersionTooHighError=此程序不能安装在 %1 版本 %2 或更高的系统上。
AdminPrivilegesRequired=安装此程序时您必须以管理员身份登录。
PowerUserPrivilegesRequired=安装此程序时您必须以管理员或 Power Users 组成员身份登录。
SetupAppRunningError=安装程序检测到 %1 正在运行。%n%n请先关闭其所有窗口，然后点击「确定」继续，或点击「取消」退出。
UninstallAppRunningError=卸载程序检测到 %1 正在运行。%n%n请先关闭其所有窗口，然后点击「确定」继续，或点击「取消」退出。

; *** 启动询问
PrivilegesRequiredOverrideTitle=选择安装模式
PrivilegesRequiredOverrideInstruction=选择安装模式
PrivilegesRequiredOverrideText1=%1 可以为所有用户安装（需要管理员权限），或仅为您安装。
PrivilegesRequiredOverrideText2=%1 可以仅为您安装，或为所有用户安装（需要管理员权限）。
PrivilegesRequiredOverrideAllUsers=为所有用户安装(&A)
PrivilegesRequiredOverrideAllUsersRecommended=为所有用户安装（推荐）(&A)
PrivilegesRequiredOverrideCurrentUser=仅为我安装(&M)
PrivilegesRequiredOverrideCurrentUserRecommended=仅为我安装（推荐）(&M)

; *** 其他错误
ErrorCreatingDir=安装程序无法创建目录“%1”
ErrorTooManyFilesInDir=无法在目录“%1”中创建文件，因为其中文件太多

; *** 安装程序通用消息
ExitSetupTitle=退出安装
ExitSetupMessage=安装尚未完成。如果现在退出，程序将不会被安装。%n%n您可以以后再次运行安装程序完成安装。%n%n现在退出安装吗？
AboutSetupMenuItem=关于安装程序(&A)...
AboutSetupTitle=关于安装程序
AboutSetupMessage=%1 版本 %2%n%3%n%n%1 主页:%n%4
AboutSetupNote=
TranslatorNote=

; *** 按钮
ButtonBack=< 上一步(&B)
ButtonNext=下一步(&N) >
ButtonInstall=安装(&I)
ButtonOK=确定
ButtonCancel=取消
ButtonYes=是(&Y)
ButtonYesToAll=全是(&A)
ButtonNo=否(&N)
ButtonNoToAll=全否(&O)
ButtonFinish=完成(&F)
ButtonBrowse=浏览(&B)...
ButtonWizardBrowse=浏览(&R)...
ButtonNewFolder=新建文件夹(&M)

; *** 「选择语言」对话框
SelectLanguageTitle=选择安装语言
SelectLanguageLabel=选择安装期间使用的语言。

; *** 通用向导文字
ClickNext=点击「下一步」继续，或点击「取消」退出安装。
BeveledLabel=
BrowseDialogTitle=浏览文件夹
BrowseDialogLabel=在下面的列表中选择一个文件夹，然后点击「确定」。
NewFolderName=新建文件夹

; *** 「欢迎」向导页
WelcomeLabel1=欢迎使用 [name] 安装向导
WelcomeLabel2=现在将在您的计算机上安装 [name/ver]。%n%n建议在继续之前关闭所有其他应用程序。

; *** 「密码」向导页
WizardPassword=密码
PasswordLabel1=此安装受密码保护。
PasswordLabel3=请输入密码，然后点击「下一步」继续。密码区分大小写。
PasswordEditLabel=密码(&P):
IncorrectPassword=您输入的密码不正确，请重试。

; *** 「许可协议」向导页
WizardLicense=许可协议
LicenseLabel=请在继续之前阅读以下重要信息。
LicenseLabel3=请阅读以下许可协议。您必须接受此协议的条款才能继续安装。
LicenseAccepted=我接受协议(&A)
LicenseNotAccepted=我不接受协议(&D)

; *** 「信息」向导页
WizardInfoBefore=信息
InfoBeforeLabel=请在继续之前阅读以下重要信息。
InfoBeforeClickLabel=准备好继续安装后，点击「下一步」。
WizardInfoAfter=信息
InfoAfterLabel=请在继续之前阅读以下重要信息。
InfoAfterClickLabel=准备好继续安装后，点击「下一步」。

; *** 「用户信息」向导页
WizardUserInfo=用户信息
UserInfoDesc=请输入您的信息。
UserInfoName=用户名(&U):
UserInfoOrg=组织(&O):
UserInfoSerial=序列号(&S):
UserInfoNameRequired=必须输入用户名。

; *** 「选择安装位置」向导页
WizardSelectDir=选择安装位置
SelectDirDesc=将 [name] 安装到哪里？
SelectDirLabel3=安装程序将把 [name] 安装到以下文件夹中。
SelectDirBrowseLabel=点击「下一步」继续。如需选择其他文件夹，点击「浏览」。
DiskSpaceGBLabel=至少需要 [gb] GB 的可用磁盘空间。
DiskSpaceMBLabel=至少需要 [mb] MB 的可用磁盘空间。
CannotInstallToNetworkDrive=安装程序无法安装到网络驱动器。
CannotInstallToUNCPath=安装程序无法安装到 UNC 路径。
InvalidPath=必须输入带盘符的完整路径，例如:%n%nC:\APP%n%n或 UNC 路径:%n%n\\server\share
InvalidDrive=您选择的驱动器或 UNC 共享不存在或无法访问。请选择其他位置。
DiskSpaceWarningTitle=磁盘空间不足
DiskSpaceWarning=安装程序至少需要 %1 KB 的可用空间，但所选驱动器只有 %2 KB 可用。%n%n仍然继续吗？
DirNameTooLong=文件夹名称或路径太长。
InvalidDirName=文件夹名称无效。
BadDirName32=文件夹名称不能包含以下任何字符:%n%n%1
DirExistsTitle=文件夹已存在
DirExists=文件夹:%n%n%1%n%n已存在。仍要安装到该文件夹吗？
DirDoesntExistTitle=文件夹不存在
DirDoesntExist=文件夹:%n%n%1%n%n不存在。要创建该文件夹吗？

; *** 「选择组件」向导页
WizardSelectComponents=选择组件
SelectComponentsDesc=要安装哪些组件？
SelectComponentsLabel2=选中要安装的组件；清除不想安装的组件。准备好后点击「下一步」。
FullInstallation=完全安装
CompactInstallation=简洁安装
CustomInstallation=自定义安装
NoUninstallWarningTitle=组件已存在
NoUninstallWarning=安装程序检测到以下组件已安装:%n%n%1%n%n取消选中这些组件不会卸载它们。%n%n仍要继续吗？
ComponentSize1=%1 KB
ComponentSize2=%1 MB
ComponentsDiskSpaceGBLabel=当前选择至少需要 [gb] GB 磁盘空间。
ComponentsDiskSpaceMBLabel=当前选择至少需要 [mb] MB 磁盘空间。

; *** 「选择附加任务」向导页
WizardSelectTasks=选择附加任务
SelectTasksDesc=要执行哪些附加任务？
SelectTasksLabel2=选择在安装 [name] 时要执行的附加任务，然后点击「下一步」。

; *** 「选择开始菜单文件夹」向导页
WizardSelectProgramGroup=选择开始菜单文件夹
SelectStartMenuFolderDesc=把程序快捷方式放到哪里？
SelectStartMenuFolderLabel3=安装程序将在以下开始菜单文件夹中创建快捷方式。
SelectStartMenuFolderBrowseLabel=点击「下一步」继续。如需选择其他文件夹，点击「浏览」。
MustEnterGroupName=必须输入文件夹名称。
GroupNameTooLong=文件夹名称或路径太长。
InvalidGroupName=文件夹名称无效。
BadGroupName=文件夹名称不能包含以下任何字符:%n%n%1
NoProgramGroupCheck2=不创建开始菜单文件夹(&D)

; *** 「准备安装」向导页
WizardReady=准备安装
ReadyLabel1=安装程序已准备好在您的计算机上安装 [name]。
ReadyLabel2a=点击「安装」开始安装，或点击「上一步」检查、修改设置。
ReadyLabel2b=点击「安装」开始安装。
ReadyMemoUserInfo=用户信息:
ReadyMemoDir=安装位置:
ReadyMemoType=安装类型:
ReadyMemoComponents=已选组件:
ReadyMemoGroup=开始菜单文件夹:
ReadyMemoTasks=附加任务:

; *** 「下载」向导页（含 Inno 6.4+ 的 DownloadingLabel2）
DownloadingLabel=正在下载附加文件...
DownloadingLabel2=正在下载文件...
ButtonStopDownload=停止下载(&S)
StopDownload=确定要停止下载吗？
ErrorDownloadAborted=下载已中止
ErrorDownloadFailed=下载失败: %1 %2
ErrorDownloadSizeFailed=获取大小失败: %1 %2
ErrorDownloading=下载出错: %1
ErrorFileHash1=文件哈希校验失败: %1
ErrorFileHash2=文件哈希无效: 期望 %1，实际 %2
ErrorProgress=进度无效: %1 / %2
ErrorFileSize=文件大小错误: 期望 %1，实际 %2

; *** 「解压归档」向导页（Inno 6.3+）
ExtractingLabel=正在解压文件...
ButtonStopExtraction=停止解压(&S)
StopExtraction=确定要停止解压吗？
ErrorExtractionAborted=解压已中止
ErrorExtractionFailed=解压失败: %1
ErrorExtracting=解压出错: %1
ArchiveUnsupportedFormat=不支持的归档格式
ArchiveIsCorrupted=归档文件已损坏
ArchiveIncorrectPassword=归档密码不正确

; *** 校验错误（Inno 6.5+）
SourceVerificationFailed=源文件校验失败: %1
VerificationSignatureDoesntExist=签名文件“%1”不存在
VerificationSignatureInvalid=签名文件“%1”无效
VerificationKeyNotFound=签名文件“%1”使用了未知密钥
VerificationFileNameIncorrect=文件“%1”的名称不正确
VerificationFileTagIncorrect=文件“%1”的标记不正确
VerificationFileSizeIncorrect=文件“%1”的大小不正确
VerificationFileHashIncorrect=文件“%1”的哈希不正确

; *** 「准备安装」阶段
WizardPreparing=正在准备安装
PreparingDesc=安装程序正在准备在您的计算机上安装 [name]。
PreviousInstallNotCompleted=先前程序的安装或卸载尚未完成，需要重启计算机才能完成。%n%n重启后请再次运行安装程序以完成 [name] 的安装。
CannotContinue=安装程序无法继续。请点击「取消」退出。
ApplicationsFound=以下应用程序正在使用需要由安装程序更新的文件。建议允许安装程序自动关闭这些应用程序。
ApplicationsFound2=以下应用程序正在使用需要由安装程序更新的文件。建议允许安装程序自动关闭这些应用程序。安装完成后，安装程序将尝试重新启动它们。
CloseApplications=自动关闭这些应用程序(&A)
DontCloseApplications=不要关闭这些应用程序(&D)
ErrorCloseApplications=安装程序无法自动关闭所有应用程序。建议先关闭所有正在使用相关文件的应用程序，然后再继续。
PrepareToInstallNeedsRestart=安装程序需要重启计算机。重启后请再次运行安装程序以完成 [name] 的安装。%n%n现在重启吗？

; *** 「正在安装」向导页
WizardInstalling=正在安装
InstallingLabel=正在您的计算机上安装 [name]，请稍候。

; *** 「安装完成」向导页
FinishedHeadingLabel=[name] 安装完成
FinishedLabelNoIcons=安装程序已在您的计算机上安装了 [name]。
FinishedLabel=安装程序已在您的计算机上安装了 [name]。可通过已安装的快捷方式运行该应用程序。
ClickFinish=点击「完成」退出安装程序。
FinishedRestartLabel=为完成 [name] 的安装，必须重启计算机。现在重启吗？
FinishedRestartMessage=为完成 [name] 的安装，必须重启计算机。%n%n现在重启吗？
ShowReadmeCheck=是，查看自述文件
YesRadio=是，立即重启计算机(&Y)
NoRadio=否，稍后自行重启计算机(&N)
RunEntryExec=运行 %1
RunEntryShellExec=查看 %1

; *** 「需要下一张磁盘」
ChangeDiskTitle=需要下一张磁盘
SelectDiskLabel2=请插入磁盘 %1 并点击「确定」。%n%n如果文件位于其他文件夹，请输入正确路径或点击「浏览」。
PathLabel=路径(&P):
FileNotInDir2=在“%2”中找不到文件“%1”。请插入正确的磁盘或选择其他文件夹。
SelectDirectoryLabel=请指定下一张磁盘的位置。

; *** 安装阶段消息
SetupAborted=安装未完成。%n%n请修正问题后重新运行安装程序。
AbortRetryIgnoreSelectAction=选择操作
AbortRetryIgnoreRetry=重试(&T)
AbortRetryIgnoreIgnore=忽略错误并继续(&I)
AbortRetryIgnoreCancel=取消安装
RetryCancelSelectAction=选择操作
RetryCancelRetry=重试(&T)
RetryCancelCancel=取消

; *** 安装状态消息
StatusClosingApplications=正在关闭应用程序...
StatusDownloadFiles=正在下载文件...
StatusCreateDirs=正在创建目录...
StatusExtractFiles=正在解压文件...
StatusCreateIcons=正在创建快捷方式...
StatusCreateIniEntries=正在创建 INI 条目...
StatusCreateRegistryEntries=正在创建注册表条目...
StatusRegisterFiles=正在注册文件...
StatusSavingUninstall=正在保存卸载信息...
StatusRunProgram=正在完成安装...
StatusRestartingApplications=正在重启应用程序...
StatusRollback=正在回滚更改...

; *** 其他错误
ErrorInternal2=内部错误: %1
ErrorFunctionFailedNoCode=%1 失败
ErrorFunctionFailed=%1 失败；错误代码 %2
ErrorFunctionFailedWithMessage=%1 失败；错误代码 %2。%n%3
ErrorExecutingProgram=无法执行文件:%n%1

; *** 注册表错误
ErrorRegOpenKey=打开注册表键出错:%n%1\%2
ErrorRegCreateKey=创建注册表键出错:%n%1\%2
ErrorRegWriteKey=写入注册表键出错:%n%1\%2

; *** INI 错误
ErrorIniEntry=在文件“%1”中创建 INI 条目出错。

; *** 文件复制错误
FileAbortRetryIgnoreSkipNotRecommended=跳过此文件（不推荐）(&S)
FileAbortRetryIgnoreIgnoreNotRecommended=忽略错误并继续（不推荐）(&I)
SourceIsCorrupted=源文件已损坏
SourceDoesntExist=源文件“%1”不存在
ExistingFileReadOnly2=无法替换现有文件，它是只读的。
ExistingFileReadOnlyRetry=移除只读属性并重试(&R)
ExistingFileReadOnlyKeepExisting=保留现有文件(&K)
ErrorReadingExistingDest=读取现有文件时出错:
FileExistsSelectAction=选择操作
FileExists2=文件已存在。
FileExistsOverwriteExisting=覆盖现有文件(&O)
FileExistsKeepExisting=保留现有文件(&K)
FileExistsOverwriteOrKeepAll=对后续冲突执行相同操作(&D)
ExistingFileNewerSelectAction=选择操作
ExistingFileNewer2=现有文件比要安装的文件更新。
ExistingFileNewerOverwriteExisting=覆盖现有文件(&O)
ExistingFileNewerKeepExisting=保留现有文件（推荐）(&K)
ExistingFileNewerOverwriteOrKeepAll=对后续冲突执行相同操作(&D)
ErrorChangingAttr=更改现有文件属性时出错:
ErrorCreatingTemp=在目标目录创建文件时出错:
ErrorReadingSource=读取源文件时出错:
ErrorCopying=复制文件时出错:
ErrorReplacingExistingFile=替换现有文件时出错:
ErrorRestartReplace=RestartReplace 失败:
ErrorRenamingTemp=重命名目标目录中的文件时出错:
ErrorRegisterServer=无法注册 DLL/OCX: %1
ErrorRegSvr32Failed=RegSvr32 失败，退出代码 %1
ErrorRegisterTypeLib=无法注册类型库: %1

; *** 卸载显示名标记
UninstallDisplayNameMark=%1 (%2)
UninstallDisplayNameMarks=%1 (%2, %3)
UninstallDisplayNameMark32Bit=32 位
UninstallDisplayNameMark64Bit=64 位
UninstallDisplayNameMarkAllUsers=所有用户
UninstallDisplayNameMarkCurrentUser=当前用户

; *** 安装后错误
ErrorOpeningReadme=打开自述文件时出错。
ErrorRestartingComputer=安装程序无法重启计算机。请手动重启。

; *** 卸载消息
UninstallNotFound=文件“%1”不存在。无法卸载。
UninstallOpenError=无法打开文件“%1”。无法卸载
UninstallUnsupportedVer=卸载日志文件“%1”的格式无法被此版本的卸载程序识别。无法卸载
UninstallUnknownEntry=卸载日志中遇到未知条目 (%1)
ConfirmUninstall=确定要完全移除 %1 及其所有组件吗？
UninstallOnlyOnWin64=此程序只能在 64 位 Windows 上卸载。
OnlyAdminCanUninstall=此程序只能由具有管理员权限的用户卸载。
UninstallStatusLabel=正在从您的计算机移除 %1，请稍候。
UninstalledAll=%1 已成功从您的计算机移除。
UninstalledMost=%1 卸载完成。%n%n某些内容无法移除，可手动删除。
UninstalledAndNeedsRestart=为完成 %1 的卸载，必须重启计算机。%n%n现在重启吗？
UninstallDataCorrupted=文件“%1”已损坏。无法卸载

; *** 卸载阶段消息
ConfirmDeleteSharedFileTitle=移除共享文件？
ConfirmDeleteSharedFile2=系统显示以下共享文件已不再被任何程序使用。要移除该共享文件吗？%n%n如果仍有程序需要此文件而它被移除，这些程序可能无法正常运行。若不确定，请选择「否」。保留该文件不会造成任何损害。
SharedFileNameLabel=文件名:
SharedFileLocationLabel=位置:
WizardUninstalling=卸载状态
StatusUninstalling=正在卸载 %1...

; *** 关机阻止原因
ShutdownBlockReasonInstallingApp=正在安装 %1。
ShutdownBlockReasonUninstallingApp=正在卸载 %1。

[CustomMessages]

NameAndVersion=%1 版本 %2
AdditionalIcons=附加快捷方式:
CreateDesktopIcon=创建桌面快捷方式(&D)
CreateQuickLaunchIcon=创建快速启动栏快捷方式(&Q)
ProgramOnTheWeb=%1 网站
UninstallProgram=卸载 %1
LaunchProgram=运行 %1
AssocFileExtension=将 %1 与 %2 文件扩展名关联(&A)
AssocingFileExtension=正在将 %1 与 %2 文件扩展名关联...
AutoStartProgramGroupDescription=启动:
AutoStartProgram=自动启动 %1
AddonHostProgramNotFound=在您选择的文件夹中找不到 %1。%n%n仍要继续吗？
