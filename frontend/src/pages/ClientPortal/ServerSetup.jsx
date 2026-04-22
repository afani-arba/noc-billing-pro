import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Capacitor } from '@capacitor/core';
import { Preferences } from '@capacitor/preferences';

export default function ServerSetup() {
  const [domain, setDomain] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    // If not running in native app, there's no need for server setup
    if (!Capacitor.isNativePlatform()) {
      navigate('/portal/login', { replace: true });
      return;
    }

    Preferences.get({ key: 'clientServerUrl' }).then(({ value }) => {
      if (value) {
        navigate('/portal/login', { replace: true });
      }
    });
  }, [navigate]);

  const handleSave = async (e) => {
    e.preventDefault();
    if (!domain.trim()) return;

    setLoading(true);
    try {
      // Clean up user input
      let cleanDomain = domain.trim().toLowerCase();
      // Remove http/https if user typed it
      cleanDomain = cleanDomain.replace(/^https?:\/\//, '');
      // Remove trailing slashes
      cleanDomain = cleanDomain.replace(/\/+$/, '');
      
      const serverUrl = `https://${cleanDomain}`;
      
      await Preferences.set({ key: 'clientServerUrl', value: serverUrl });
      localStorage.setItem('clientServerUrl', serverUrl);
      
      navigate('/portal/login', { replace: true });
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background Decor */}
      <div className="absolute top-[-10%] left-[-10%] w-[500px] h-[500px] bg-indigo-600 rounded-full mix-blend-multiply filter blur-[150px] opacity-40 animate-blob"></div>
      <div className="absolute bottom-[-20%] right-[-10%] w-[600px] h-[600px] bg-pink-600 rounded-full mix-blend-multiply filter blur-[150px] opacity-40 animate-blob animation-delay-2000"></div>

      <div className="w-full max-w-md relative z-10">
        <div className="text-center mb-8 space-y-2">
          <div className="w-16 h-16 bg-white/10 rounded-2xl flex items-center justify-center mx-auto mb-4 border border-white/20 backdrop-blur-sm">
            <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-indigo-400">
              <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
              <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
              <line x1="6" y1="6" x2="6.01" y2="6"></line>
              <line x1="6" y1="18" x2="6.01" y2="18"></line>
            </svg>
          </div>
          <h1 className="text-3xl font-bold text-white tracking-tight">
            Setup Server
          </h1>
          <p className="text-gray-400 text-sm max-w-[280px] mx-auto pt-1">
            Silakan masukkan domain provider internet Anda untuk menghubungkan aplikasi.
          </p>
        </div>

        <Card className="bg-white/10 backdrop-blur-xl border-white/20 p-8 rounded-3xl shadow-2xl">
          <form onSubmit={handleSave} className="space-y-6">
            <div className="space-y-2">
              <label className="text-gray-300 text-sm font-medium ml-1">Domain Provider</label>
              <Input 
                type="text" 
                placeholder="Contoh: billing.ispku.com" 
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                className="bg-black/40 border-white/10 text-white placeholder:text-gray-600 h-12 rounded-2xl px-4 focus:ring-2 focus:ring-indigo-500 transition-all text-center tracking-wider"
              />
            </div>

            <Button 
              type="submit" 
              disabled={loading || !domain.trim()}
              className="w-full h-12 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white rounded-2xl font-semibold shadow-lg hover:shadow-indigo-500/25 transition-all duration-300 ease-in-out"
            >
              {loading ? 'Menyimpan...' : 'Hubungkan'}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
