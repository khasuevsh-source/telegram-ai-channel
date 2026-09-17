param(
    [Parameter(Mandatory = $true)][string]$Headline,
    [string]$RubricLabel = "AI BEZ VODY",
    [string]$AccentHex = "#8B5CF6",
    [string]$OutFile
)

Add-Type -AssemblyName System.Drawing

function New-Color([string]$hex, [int]$alpha = 255) {
    $hex = $hex.TrimStart('#')
    $r = [Convert]::ToInt32($hex.Substring(0, 2), 16)
    $gg = [Convert]::ToInt32($hex.Substring(2, 2), 16)
    $b = [Convert]::ToInt32($hex.Substring(4, 2), 16)
    return [System.Drawing.Color]::FromArgb($alpha, $r, $gg, $b)
}

function Add-RoundedRect([System.Drawing.Drawing2D.GraphicsPath]$path, $x, $y, $w, $h, $r) {
    $path.AddArc($x, $y, $r, $r, 180, 90)
    $path.AddArc($x + $w - $r, $y, $r, $r, 270, 90)
    $path.AddArc($x + $w - $r, $y + $h - $r, $r, $r, 0, 90)
    $path.AddArc($x, $y + $h - $r, $r, $r, 90, 90)
    $path.CloseFigure()
}

function Add-Glow($g, $cx, $cy, $r, $colorHex) {
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $path.AddEllipse($cx - $r, $cy - $r, $r * 2, $r * 2)
    $brush = New-Object System.Drawing.Drawing2D.PathGradientBrush($path)
    $brush.CenterColor = New-Color $colorHex 200
    $brush.SurroundColors = @((New-Color $colorHex 0))
    $g.FillPath($brush, $path)
}

$size = 1024
$bmp = New-Object System.Drawing.Bitmap($size, $size)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit

$g.Clear((New-Color "#0B1120"))

Add-Glow $g 160 180 460 "#6D28D9"
Add-Glow $g 900 260 400 $AccentHex
Add-Glow $g 250 950 420 "#0EA5A4"

$overlay = New-Color "#0B1120" 60
$g.FillRectangle((New-Object System.Drawing.SolidBrush($overlay)), 0, 0, $size, $size)

# rubric tag pill
$tagFont = New-Object System.Drawing.Font("Segoe UI", 28, [System.Drawing.FontStyle]::Bold)
$tagSize = $g.MeasureString($RubricLabel, $tagFont)
$padX = 40; $padY = 18
$tagW = $tagSize.Width + $padX * 2
$tagH = $tagSize.Height + $padY * 2
$tagX = 80; $tagY = 90
$tagPath = New-Object System.Drawing.Drawing2D.GraphicsPath
Add-RoundedRect $tagPath $tagX $tagY $tagW $tagH ($tagH / 2)
$g.FillPath((New-Object System.Drawing.SolidBrush((New-Color $AccentHex 255))), $tagPath)
$g.DrawString($RubricLabel, $tagFont, (New-Object System.Drawing.SolidBrush([System.Drawing.Color]::Black)), ($tagX + $padX), ($tagY + $padY - 4))

# headline
$font = New-Object System.Drawing.Font("Segoe UI", 58, [System.Drawing.FontStyle]::Bold)
$whiteBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
$layoutRect = New-Object System.Drawing.RectangleF(80, 320, ($size - 160), 620)
$format = New-Object System.Drawing.StringFormat
$format.Alignment = [System.Drawing.StringAlignment]::Near
$format.LineAlignment = [System.Drawing.StringAlignment]::Near
$g.DrawString($Headline, $font, $whiteBrush, $layoutRect, $format)

# small brand mark, bottom-right
$cx = $size - 110; $cy = $size - 110; $r = 45
$linePen = New-Object System.Drawing.Pen((New-Color "#FFFFFF" 160), 4)
$nodeBrush = New-Object System.Drawing.SolidBrush((New-Color "#FFFFFF" 210))
foreach ($angle in 0, 72, 144, 216, 288) {
    $rad = $angle * [Math]::PI / 180
    $x = $cx + $r * [Math]::Cos($rad)
    $y = $cy + $r * [Math]::Sin($rad)
    $g.DrawLine($linePen, $cx, $cy, $x, $y)
    $g.FillEllipse($nodeBrush, $x - 7, $y - 7, 14, 14)
}
$g.FillEllipse($nodeBrush, $cx - 13, $cy - 13, 26, 26)

if (-not $OutFile) {
    $OutFile = Join-Path (Split-Path $PSScriptRoot -Parent) "assets\card-demo.png"
}
$bmp.Save($OutFile, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()
Write-Output "Saved: $OutFile"
