import os
import re

# Karakter yang rusak encoding-nya (multi-byte UTF-8 yang terbaca salah):
BROKEN_PATTERNS = {
    'â€"':  '—',   # em dash
    'â€™':  ''',   # right single quote / apostrophe
    'â€˜':  ''',   # left single quote
    'â€œ':  '"',   # left double quote
    'â€':   '"',   # right double quote
    'â€¦':  '…',   # ellipsis
    'â€¢':  '•',   # bullet
    'â€˜':  ''',   # single quote left
    'â€‹':  '',    # zero-width space
}

EXTENSIONS = {'.jsx', '.js', '.tsx', '.ts', '.py', '.html', '.css', '.md'}

ROOT = r'e:\noc-billing-pro'

fixed_files = []

for dirpath, dirnames, filenames in os.walk(ROOT):
    # Skip node_modules and .git
    dirnames[:] = [d for d in dirnames if d not in ('node_modules', '.git', '__pycache__', 'dist', 'build')]
    
    for filename in filenames:
        ext = os.path.splitext(filename)[1].lower()
        if ext not in EXTENSIONS:
            continue
        
        filepath = os.path.join(dirpath, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            new_content = content
            changed = False
            for bad, good in BROKEN_PATTERNS.items():
                if bad in new_content:
                    new_content = new_content.replace(bad, good)
                    changed = True
            
            if changed:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                rel = os.path.relpath(filepath, ROOT)
                fixed_files.append(rel)
                print(f"  FIXED: {rel}")
        except Exception as e:
            pass

print(f"\nTotal: {len(fixed_files)} file diperbaiki.")
