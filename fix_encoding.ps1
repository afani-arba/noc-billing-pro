# Fix corrupted encoding: UTF-8 bytes were converted to codepoints individually
# E.g. UTF-8 bytes E2 80 94 (= em-dash —) were read as chars U+00E2, U+0080, U+0094
# But in file they're stored as UTF-8 encoding of those codepoints:
# U+00E2 = C3 A2, U+0080 = C2 80 (or as U+20AC E2 82 AC), U+0094 = C2 94
# This script detects the pattern in the Unicode string and replaces it

$srcDir = "e:\noc-billing-pro\frontend\src"
$files = Get-ChildItem -Path $srcDir -Recurse -Include "*.jsx","*.js","*.tsx","*.ts"

$totalFixed = 0
$utf8 = [System.Text.Encoding]::UTF8

# When original UTF-8 multi-byte sequence like E2 80 XX was misread as Latin-1:
# byte E2 -> latin1 char 'â' = U+00E2
# byte 80 -> latin1 char '€' = U+0080 BUT displayed as U+20AC in Windows-1252
# byte 9x -> latin1 char = U+009x or Windows-1252 mapping
# Then when saved as UTF-8, these codepoints become multi-byte sequences again.

# In the UTF-8 file read as Unicode string:
# 'â' = U+00E2 (correct, 1 char)
# '€' might be U+20AC (Windows-1252 mismap of 0x80) or U+0080
# The 3rd byte maps as per Windows-1252

# Windows-1252 special mappings (bytes 0x80-0x9F that differ from Latin-1):
$win1252Map = @{
    0x80 = 0x20AC  # € 
    0x82 = 0x201A  # ‚
    0x83 = 0x0192  # ƒ
    0x84 = 0x201E  # „
    0x85 = 0x2026  # …
    0x86 = 0x2020  # †
    0x87 = 0x2021  # ‡
    0x88 = 0x02C6  # ˆ
    0x89 = 0x2030  # ‰
    0x8A = 0x0160  # Š
    0x8B = 0x2039  # ‹
    0x8C = 0x0152  # Œ
    0x8E = 0x017D  # Ž
    0x91 = 0x2018  # '
    0x92 = 0x2019  # '
    0x93 = 0x201C  # "
    0x94 = 0x201D  # "
    0x95 = 0x2022  # •
    0x96 = 0x2013  # –
    0x97 = 0x2014  # —
    0x98 = 0x02DC  # ˜
    0x99 = 0x2122  # ™
    0x9A = 0x0161  # š
    0x9B = 0x203A  # ›
    0x9C = 0x0153  # œ
    0x9E = 0x017E  # ž
    0x9F = 0x0178  # Ÿ
}

# Build reverse map: Windows-1252 Unicode char -> original UTF-8 byte
# for the range that matters (0x80-0x9F)
$reverseWin1252 = @{}
for ($b = 0x80; $b -le 0x9F; $b++) {
    $unicode = if ($win1252Map.ContainsKey($b)) { $win1252Map[$b] } else { $b }
    $reverseWin1252[$unicode] = $b
}

foreach ($file in $files) {
    try {
        $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
        $text = $utf8.GetString($bytes)
        $original = $text

        # Strip BOM
        if ($text.Length -gt 0 -and [int][char]$text[0] -eq 0xFEFF) {
            $text = $text.Substring(1)
        }

        $sb = New-Object System.Text.StringBuilder($text.Length)
        $i = 0
        $fixCount = 0

        while ($i -lt $text.Length) {
            $c1 = [int]$text[$i]
            
            # Look for pattern: U+00E2 followed by 2 more bytes that together form a 3-byte UTF-8 sequence
            # U+00E2 = 'â' which is the first byte (0xE2) of many 3-byte UTF-8 sequences read as Latin-1
            if ($c1 -eq 0x00E2 -and ($i + 2) -lt $text.Length) {
                $c2 = [int]$text[$i + 1]
                $c3 = [int]$text[$i + 2]
                
                # Map c2 back to original byte
                $origByte2 = if ($reverseWin1252.ContainsKey($c2)) { $reverseWin1252[$c2] } elseif ($c2 -le 0x00FF) { $c2 } else { -1 }
                $origByte3 = if ($c3 -le 0x00FF) { $c3 } else { -1 }
                
                if ($origByte2 -ge 0x80 -and $origByte2 -le 0xBF -and $origByte3 -ge 0x80 -and $origByte3 -le 0xBF) {
                    # Try decoding these 3 bytes as UTF-8
                    try {
                        $tryBytes = [byte[]]@(0xE2, [byte]$origByte2, [byte]$origByte3)
                        $decoded = $utf8.GetString($tryBytes)
                        if ($decoded.Length -eq 1 -and [int]$decoded[0] -gt 0x007F) {
                            [void]$sb.Append($decoded)
                            $i += 3
                            $fixCount++
                            continue
                        }
                    } catch { }
                }
            }
            
            # Look for pattern: U+00C3 or U+00C2 followed by 1 byte that forms a 2-byte UTF-8 sequence
            if (($c1 -eq 0x00C3 -or $c1 -eq 0x00C2) -and ($i + 1) -lt $text.Length) {
                $c2 = [int]$text[$i + 1]
                $origByte1 = $c1  # 0xC3 or 0xC2 as byte
                $origByte2 = if ($reverseWin1252.ContainsKey($c2)) { $reverseWin1252[$c2] } elseif ($c2 -le 0x00FF) { $c2 } else { -1 }
                
                if ($origByte2 -ge 0x80 -and $origByte2 -le 0xBF) {
                    try {
                        $tryBytes = [byte[]]@([byte]$origByte1, [byte]$origByte2)
                        $decoded = $utf8.GetString($tryBytes)
                        if ($decoded.Length -eq 1 -and [int]$decoded[0] -gt 0x007F) {
                            [void]$sb.Append($decoded)
                            $i += 2
                            $fixCount++
                            continue
                        }
                    } catch { }
                }
            }
            
            [void]$sb.Append($text[$i])
            $i++
        }

        $newText = $sb.ToString()
        if ($newText -ne $original) {
            $newBytes = $utf8.GetBytes($newText)
            [System.IO.File]::WriteAllBytes($file.FullName, $newBytes)
            $rel = $file.FullName.Replace("e:\noc-billing-pro\frontend\src\", "")
            Write-Host "  FIXED ($fixCount seqs): $rel"
            $totalFixed++
        }

    } catch {
        Write-Host "  ERROR $($file.Name): $_"
    }
}

Write-Host ""
Write-Host "Total: $totalFixed file(s) diperbaiki."
