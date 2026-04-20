$srcDir = "e:\noc-billing-pro\frontend\src"
$files = Get-ChildItem -Path $srcDir -Recurse -Include "*.jsx","*.js"

$replacements = @(
    # [Old chars, New chars]
    @([string][char]0x00E2+[char]0x20AC+[char]0x201D, [string][char]0x2014),
    @([string][char]0x00E2+[char]0x20AC+[char]0x201C, [string][char]0x2013),
    @([string][char]0x00E2+[char]0x0153+[char]0x201C, [string][char]0x2713),
    @([string][char]0x00E2+[char]0x0153+[char]0x2014, [string][char]0x2717),
    @([string][char]0x00E2+[char]0x0153+[char]0x2022, [string][char]0x2715),
    @([string][char]0x00E2+[char]0x201D+[char]0x20AC, [string][char]0x2500),
    @([string][char]0x00E2+[char]0x0161+[char]0x00A0+[char]0x00EF+[char]0x00B8+[char]0x008F, [string][char]0x26A0+[char]0xFE0F),
    @([string][char]0x00E2+[char]0x0161+[char]0x00A0, [string][char]0x26A0),
    @([string][char]0x00E2+[char]0x201A+[char]0x00B9+[char]0x00EF+[char]0x00B8+[char]0x008F, [string][char]0x2139+[char]0xFE0F),
    @([string][char]0x00E2+[char]0x201A+[char]0x00B9, [string][char]0x2139),
    @([string][char]0x00E2+[char]0x02C6+[char]0x2122, [string][char]0x2219),
    @([string][char]0x00E2+[char]0x20AC+[char]0x00A2, [string][char]0x2022)
)

$count = 0
foreach ($file in $files) {
    try {
        $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
        $text = [System.Text.Encoding]::UTF8.GetString($bytes)
        $orig = $text

        foreach ($rep in $replacements) {
            $text = $text.Replace($rep[0], $rep[1])
        }

        # Half-fixed checkmark / warning
        $text = $text.Replace(([string][char]0x2713+[char]0x00EF+[char]0x00B8+[char]0x008F), [string][char]0x2705)
        $text = $text.Replace(([string][char]0x26A0+[char]0x00EF+[char]0x00B8+[char]0x008F), [string][char]0x26A0+[char]0xFE0F)
        
        if ($text -ne $orig) {
            $newBytes = [System.Text.Encoding]::UTF8.GetBytes($text)
            [System.IO.File]::WriteAllBytes($file.FullName, $newBytes)
            $rel = $file.FullName.Replace("e:\noc-billing-pro\frontend\src\", "")
            Write-Host "CLEANED: $rel"
            $count++
        }
    } catch {
        Write-Host "ERROR $($file.Name): $_"
    }
}
Write-Host "Total cleaned: $count files"
