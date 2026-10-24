# Start the bot on Windows. The first run asks for the token from @BotFather and keeps it in .env
# (ignored by git), so it never appears in the code or in a chat.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$envFile = Join-Path $PSScriptRoot ".env"

if (-not (Test-Path $envFile)) {
    $secure = Read-Host "Paste the bot token from @BotFather" -AsSecureString
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    $admins = Read-Host "Your Telegram ID for admin notifications (several: comma-separated)"
    "BOT_TOKEN=$($token.Trim())`nADMIN_IDS=$($admins.Trim())" | Set-Content $envFile -Encoding ascii
    Write-Host "Saved to .env"
}

foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*([A-Z_]+)\s*=\s*(.*)$') { Set-Item "env:$($Matches[1])" $Matches[2].Trim() }
}
Write-Host "Starting the bot. Stop it with Ctrl+C."
& "$PSScriptRoot\.venv\Scripts\python.exe" -m bot
