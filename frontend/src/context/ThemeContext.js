import React, { createContext, useContext, useState, useEffect } from 'react';

const ThemeContext = createContext();

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('noc_theme') || 'classic';
  });

  useEffect(() => {
    localStorage.setItem('noc_theme', theme);
    if (theme === 'neon') {
      document.documentElement.classList.add('theme-neon');
      // Optional: set a darker background color immediately to avoid flicker
      document.documentElement.style.backgroundColor = 'hsl(240 10% 2%)';
    } else {
      document.documentElement.classList.remove('theme-neon');
      document.documentElement.style.backgroundColor = 'hsl(240 6% 4%)';
    }
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
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

