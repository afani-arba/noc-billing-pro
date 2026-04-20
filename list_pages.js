const fs = require('fs');
const path = require('path');

const pagesDir = 'e:/noc-billing-pro/frontend/src/pages';
const files = fs.readdirSync(pagesDir).filter(f => f.endsWith('.jsx'));
const excludes = ['LoginPage.jsx', 'DashboardPage.jsx'];
const toProcess = files.filter(f => !excludes.includes(f));
console.log('Files to process:');
toProcess.forEach(f => console.log(' -', f));
console.log('Total:', toProcess.length);
