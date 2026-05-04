# Fix two issues in system.py:
# 1. Remove duplicate old check_update code (lines 213-341)
# 2. Restore @router.post("/perform-update") decorator

$lines = [System.IO.File]::ReadAllLines('backend\routers\system.py')
Write-Host "Total lines: $($lines.Count)"

$newLines = New-Object System.Collections.Generic.List[string]
$i = 0
$skipping = $false
$skipStart = -1
$skipEnd = -1

# Find the orphaned block: starts with blank line then "    REPO = os.environ.get" 
# (indented code outside a function after line 212)
# and ends before "@router.get("/changelog")"
for ($i = 0; $i -lt $lines.Count; $i++) {
    $line = $lines[$i]
    
    # Detect start of orphaned block (line 213 area):
    # It's unindented var assignment that is not inside any function (unreachable code after return)
    if ($i -ge 211 -and $i -le 220 -and $line -match '^\s+REPO = os\.environ') {
        $skipping = $true
        $skipStart = $i
        Write-Host "Skip start at line $($i+1): $line"
        continue
    }
    
    # Detect end of orphaned block: @router.get("/changelog")
    if ($skipping -and $line -match '@router\.get\("/changelog"\)') {
        $skipping = $false
        $skipEnd = $i - 1
        Write-Host "Skip end at line $($i): resumed at @router.get changelog"
    }
    
    # Fix missing @router.post decorator for perform_update
    if ($line -match '^async def perform_update\(user=Depends') {
        # Check if previous non-empty line has @router.post
        $prevLine = if ($i -gt 0) { $lines[$i-1] } else { "" }
        if ($prevLine -notmatch '@router\.post') {
            $newLines.Add('@router.post("/perform-update")')
            Write-Host "Added missing @router.post decorator at line $($i+1)"
        }
    }
    
    if (-not $skipping) {
        $newLines.Add($line)
    }
}

Write-Host "Removed $($lines.Count - $newLines.Count) lines"
Write-Host "New total: $($newLines.Count)"
[System.IO.File]::WriteAllLines('backend\routers\system.py', $newLines)
Write-Host "Done!"
