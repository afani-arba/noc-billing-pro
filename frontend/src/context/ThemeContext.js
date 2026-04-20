import React, { createContext, useContext, useState, useEffect } from 'react';

const ThemeContext = createContext();

const THEMES = {
  cyber: {
    label: 'Cyber Glassmorphism',
    description: 'Neon Green & Cyan — NOC / Network Engineer aesthetic',
    className: 'theme-cyber',
    bgColor: 'hsl(210, 20%, 5%)',
  },
  classic: {
    label: 'Classic Navy',
    description: 'Corporate dark navy — clean and professional',
    className: '',
    bgColor: 'hsl(220, 35%, 8%)',
  },
};

export { THEMES };

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    // Default ke 'cyber' jika belum ada pilihan tersimpan
    return localStorage.getItem('noc_theme') || 'cyber';
  });

  useEffect(() => {
    localStorage.setItem('noc_theme', theme);
    const root = document.documentElement;
    const current = THEMES[theme] || THEMES.cyber;

    // Bersihkan semua class tema dulu
    Object.values(THEMES).forEach(t => {
      if (t.className) root.classList.remove(t.className);
    });

    // Terapkan class tema baru
    if (current.className) {
      root.classList.add(current.className);
    }

    // Set background color agar tidak flicker saat transisi
    root.style.backgroundColor = current.bgColor;
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, themes: THEMES }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
