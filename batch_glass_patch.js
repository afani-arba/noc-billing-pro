/**
 * batch_glass_patch.js
 * Jalankan dengan: node batch_glass_patch.js
 *
 * Script ini menambahkan useTheme import dan melakukan class replacement
 * glassmorphism pada semua halaman yang belum diupdate.
 */

const fs = require('fs');
const path = require('path');

const pagesDir = path.resolve(__dirname, 'frontend/src/pages');
const componentsDir = path.resolve(__dirname, 'frontend/src/components');

// Halaman yang SUDAH manual diupdate — skip
const ALREADY_DONE = new Set([
  'LoginPage.jsx',
  'DashboardPage.jsx',
  'SettingsPage.jsx',
]);

function patchFile(filePath) {
  let content = fs.readFileSync(filePath, 'utf-8');
  const fname = path.basename(filePath);
  let changed = false;

  // 1) Tambah useTheme import jika belum ada
  if (!content.includes("useTheme") && !content.includes("ThemeContext")) {
    // Cari baris import pertama lalu sisipkan setelah import terakhir dari blok import awal
    // Strategi: sisipkan setelah baris "import api" atau setelah import pertama
    if (content.includes("import api from")) {
      content = content.replace(
        /import api from ['""]@\/lib\/api['""];/,
        `import api from "@/lib/api";\nimport { useTheme } from "@/context/ThemeContext";`
      );
    } else if (content.includes('from "react"')) {
      content = content.replace(
        /import \{[^}]+\} from "react";/,
        (match) => match + '\nimport { useTheme } from "@/context/ThemeContext";'
      );
    }
    changed = true;
  }

  // 2) Ganti class-class card utama
  const replacements = [
    // Card container utama
    [/className="bg-card border border-border rounded-sm p-(\d+) sm:p-(\d+) space-y-(\d+)"/g,
     (m, p1, p2, p3) => `className={\`\${isCyber ? 'glass-card' : 'bg-card border border-border rounded-sm'} p-${p1} sm:p-${p2} space-y-${p3}\`}`],

    [/className="bg-card border border-border rounded-sm p-(\d+) sm:p-(\d+)"/g,
     (m, p1, p2) => `className={\`\${isCyber ? 'glass-card' : 'bg-card border border-border rounded-sm'} p-${p1} sm:p-${p2}\`}`],

    [/className="bg-card border border-border rounded-sm p-(\d+)"/g,
     (m, p1) => `className={\`\${isCyber ? 'glass-card' : 'bg-card border border-border rounded-sm'} p-${p1}\`}`],
  ];

  for (const [pattern, replacement] of replacements) {
    const newContent = content.replace(pattern, replacement);
    if (newContent !== content) {
      content = newContent;
      changed = true;
    }
  }

  // 3) Tambah isCyber declaration setelah function declaration jika useTheme diimport tapi isCyber belum ada
  if (content.includes("useTheme") && !content.includes("isCyber")) {
    // Cari pattern "const [" atau "useState" pertama di dalam komponen
    content = content.replace(
      /(export default function \w+\(\)[^{]*\{)/,
      (match) => match + '\n  const { theme } = useTheme();\n  const isCyber = theme === "cyber";'
    );
    changed = true;
  }

  if (changed) {
    fs.writeFileSync(filePath, content, 'utf-8');
    console.log(`✓ Patched: ${fname}`);
  } else {
    console.log(`- Skipped (no change): ${fname}`);
  }
}

// Process pages
const pageFiles = fs.readdirSync(pagesDir)
  .filter(f => f.endsWith('.jsx') && !ALREADY_DONE.has(f))
  .map(f => path.join(pagesDir, f));

// Process components  
const componentFiles = fs.readdirSync(componentsDir)
  .filter(f => f.endsWith('.jsx') && !['Layout.jsx'].includes(f))
  .map(f => path.join(componentsDir, f));

const allFiles = [...pageFiles, ...componentFiles];

console.log(`Processing ${allFiles.length} files...\n`);
allFiles.forEach(patchFile);
console.log('\nDone!');
