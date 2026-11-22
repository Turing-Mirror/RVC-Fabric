param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[1-9][0-9]*$')][string]$RunId,
    [switch]$Publish
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$pythonArgs = @()
if ($pythonCommand) {
    $pythonBin = $pythonCommand.Source
} else {
    $pythonBin = (Get-Command py -ErrorAction Stop).Source
    $pythonArgs = @('-3')
}
$previousToken = $env:CNB_TOKEN
$tokenPointer = [IntPtr]::Zero
try {
    if ($Publish -and !$env:CNB_TOKEN) {
        $tokenPath = Join-Path $repoRoot '.local/beta/cnb-token.dpapi'
        if (Test-Path -LiteralPath $tokenPath) {
            $encrypted = [IO.File]::ReadAllText($tokenPath, [Text.Encoding]::UTF8)
            $secureToken = ConvertTo-SecureString $encrypted
        } else {
            $secureToken = Read-Host 'CNB personal token (repo-release:rw and repo-code:rw; hidden input)' -AsSecureString
        }
        $tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
        $env:CNB_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
        if (!$env:CNB_TOKEN) { throw 'CNB token is empty.' }
    }
    $argsList = $pythonArgs + @((Join-Path $PSScriptRoot 'beta_release.py'), '--run-id', $RunId)
    if ($Publish) { $argsList += '--publish' }
    Push-Location $repoRoot
    try {
        & $pythonBin @argsList
        if ($LASTEXITCODE -ne 0) { throw ('Beta command failed (exit ' + $LASTEXITCODE + ').') }
    } finally {
        Pop-Location
    }
} finally {
    $env:CNB_TOKEN = $previousToken
    if ($tokenPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
    }
}
