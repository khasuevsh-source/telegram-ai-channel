Add-Type -AssemblyName System.Drawing

$size = 512
$bmp = New-Object System.Drawing.Bitmap($size, $size)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

$rect = New-Object System.Drawing.Rectangle(0, 0, $size, $size)
$color1 = [System.Drawing.Color]::FromArgb(255, 11, 18, 32)    # #0B1220
$color2 = [System.Drawing.Color]::FromArgb(255, 30, 27, 75)    # #1E1B4B
$bgBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush($rect, $color1, $color2, 45)
$g.FillRectangle($bgBrush, $rect)

$centerX = 256
$centerY = 256
$outerRadius = 150
$angles = 0, 72, 144, 216, 288

$linePen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(220, 255, 255, 255), 8)
$nodeBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)

$points = @()
foreach ($angle in $angles) {
    $rad = $angle * [Math]::PI / 180
    $x = $centerX + $outerRadius * [Math]::Cos($rad)
    $y = $centerY + $outerRadius * [Math]::Sin($rad)
    $points += , (New-Object System.Drawing.PointF($x, $y))
}

foreach ($p in $points) {
    $g.DrawLine($linePen, (New-Object System.Drawing.PointF($centerX, $centerY)), $p)
}

foreach ($p in $points) {
    $r = 24
    $g.FillEllipse($nodeBrush, $p.X - $r, $p.Y - $r, $r * 2, $r * 2)
}

$cr = 46
$g.FillEllipse($nodeBrush, $centerX - $cr, $centerY - $cr, $cr * 2, $cr * 2)

$outDir = Join-Path $PSScriptRoot "..\assets"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$outPath = Join-Path $outDir "avatar.png"
$bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)

$g.Dispose()
$bmp.Dispose()
Write-Output "Saved: $outPath"
