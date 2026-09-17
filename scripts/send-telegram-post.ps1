param(
    [Parameter(Mandatory = $true)][string]$Text,
    [string]$ParseMode = "HTML"
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$configPath = Join-Path $PSScriptRoot "..\config\config.json"
if (-not (Test-Path $configPath)) {
    throw "config/config.json не найден. Скопируйте config/config.example.json в config/config.json и заполните BotToken и ChannelId."
}

$config = Get-Content $configPath -Raw | ConvertFrom-Json

$uri = "https://api.telegram.org/bot$($config.BotToken)/sendMessage"
$body = @{
    chat_id                  = $config.ChannelId
    text                     = $Text
    parse_mode               = $ParseMode
    disable_web_page_preview = $false
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri $uri -Method Post -Body $body -ContentType "application/json; charset=utf-8"

if (-not $response.ok) {
    throw "Telegram API вернул ошибку: $($response.description)"
}

Write-Output "Пост опубликован: message_id=$($response.result.message_id)"
