$lines = [System.IO.File]::ReadAllLines('backend\routers\system.py')
Write-Host "Total lines: $($lines.Count)"

# Cari baris awal sisa kode lama (setelah changelog function yang kita tambahkan)
# Cari "return {""commits"": [], ""error"": str(e)}" diikuti kode lama
$startDelete = -1
$endDelete = -1

for ($i = 255; $i -lt 345; $i++) {
    $line = $lines[$i]
    if ($line -match "Ambil latest commit dari GitHub API agar jalan tanpa git CLI") {
        $startDelete = $i - 2  # Include blank lines before
        Write-Host "Found leftover start at line $($i+1): $line"
    }
    if ($startDelete -ge 0 -and $line -match "@router\.post.*perform-update") {
        $endDelete = $i - 1
        Write-Host "Found perform-update at line $($i+1)"
        break
    }
}

if ($startDelete -ge 0 -and $endDelete -ge 0) {
    Write-Host "Deleting lines $($startDelete+1) to $($endDelete+1)"
    $newLines = @()
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($i -lt $startDelete -or $i -gt $endDelete) {
            $newLines += $lines[$i]
        }
    }
    [System.IO.File]::WriteAllLines('backend\routers\system.py', $newLines)
    Write-Host "Done! New total: $($newLines.Count) lines"
} else {
    Write-Host "Could not find deletion range: start=$startDelete end=$endDelete"
    # Print context around expected area
    $lines[255..340] | ForEach-Object -Begin {$n=256} -Process { Write-Host "${n}: $_"; $n++ }
}
