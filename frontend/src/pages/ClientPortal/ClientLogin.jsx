import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Capacitor } from '@capacitor/core';
import { Preferences } from '@capacitor/preferences';

export default function ClientLogin() {
  const [customerId, setCustomerId] = useState('');
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [profile, setProfile] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    // If token already exists, skip login
    Preferences.get({ key: 'clientToken' }).then(({ value }) => {
      if (value) {
        navigate('/portal/dashboard', { replace: true });
      }
    }).catch(() => {});

    const baseUrl = '/api';
    axios.get(`${baseUrl}/system/company-profile`)
      .then(res => setProfile(res.data))
      .catch(e => console.error("Failed to load company profile", e));
  }, [navigate]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      // Basic validation
      if (!customerId.trim() || !phone.trim()) {
        throw new Error('Semua kolom wajib diisi');
      }

      // Login to backend directly
      // Note: we can't use the standard api.js if it intercepts 401s to Admin login.
      // So we use standard axios or careful fetch.
      const baseUrl = '/api';
      const res = await axios.post(`${baseUrl}/client-portal/login`, {
        customer_id: customerId,
        phone: phone
      });

      if (res.data.ok) {
        await Preferences.set({ key: 'clientToken', value: res.data.token });
        localStorage.setItem('clientToken', res.data.token);
        navigate('/portal/dashboard');
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Gagal masuk. Periksa kembali data Anda.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background Decor */}
      <div className="absolute top-[-10%] left-[-10%] w-[500px] h-[500px] bg-indigo-600 rounded-full mix-blend-multiply filter blur-[150px] opacity-40 animate-blob"></div>
      <div className="absolute top-[20%] right-[-10%] w-[400px] h-[400px] bg-purple-600 rounded-full mix-blend-multiply filter blur-[150px] opacity-40 animate-blob animation-delay-2000"></div>
      <div className="absolute bottom-[-20%] left-[20%] w-[600px] h-[600px] bg-pink-600 rounded-full mix-blend-multiply filter blur-[150px] opacity-40 animate-blob animation-delay-4000"></div>

      <div className="w-full max-w-md relative z-10">
        <div className="text-center mb-8 space-y-1">
          <h1 className="text-4xl font-bold text-white tracking-tight">
            {profile?.product_name || 'Client Portal'}
          </h1>
          {profile?.company_name && (
            <p className="text-indigo-300 font-medium text-sm">{profile.company_name}</p>
          )}
          <p className="text-gray-400 text-sm pt-1">Kelola tagihan & WiFi rumah dengan mudah</p>
        </div>

        <Card className="bg-white/10 backdrop-blur-xl border-white/20 p-8 rounded-3xl shadow-2xl">
          <form onSubmit={handleLogin} className="space-y-6">
            {error && (
              <div className="bg-red-500/10 border border-red-500/50 text-red-200 p-3 rounded-xl text-sm text-center font-medium">
                {error}
              </div>
            )}
            
          <div className="space-y-2">
              <label className="text-gray-300 text-sm font-medium ml-1">ID Pelanggan</label>
              <Input 
                type="text" 
                placeholder="Contoh: CUST-1001" 
                value={customerId}
                onChange={(e) => setCustomerId(e.target.value.toUpperCase())}
                className="bg-black/40 border-white/10 text-white placeholder:text-gray-600 h-12 rounded-2xl px-4 focus:ring-2 focus:ring-indigo-500 transition-all font-mono tracking-wider"
              />
              <p className="text-xs text-gray-600 ml-1">ID Pelanggan tertera pada nota/struk pemasangan Anda.</p>
            </div>
            
            <div className="space-y-2">
              <label className="text-gray-300 text-sm font-medium ml-1">Nomor Handphone (Terdaftar/WA)</label>
              <Input 
                type="text" 
                placeholder="Contoh: 08123456789" 
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="bg-black/40 border-white/10 text-white placeholder:text-gray-600 h-12 rounded-2xl px-4 focus:ring-2 focus:ring-indigo-500 transition-all"
              />
            </div>

            <Button 
              type="submit" 
              disabled={loading}
              className="w-full h-12 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white rounded-2xl font-semibold shadow-lg hover:shadow-indigo-500/25 transition-all duration-300 ease-in-out"
            >
              {loading ? 'Memeriksa Data...' : 'Masuk ke Dashboard'}
            </Button>
          </form>
          
          <div className="mt-8 text-center space-y-2">
            <p className="text-xs text-gray-500">
              Lupa ID Pelanggan? Hubungi CS melalui WhatsApp: 
              {profile?.whatsapp_number ? (
                <a href={`https://wa.me/${profile.whatsapp_number}`} target="_blank" rel="noreferrer" className="text-indigo-400 ml-1 hover:underline">
                  {profile.whatsapp_number}
                </a>
              ) : ' —'}
            </p>
            {profile?.address && (
              <p className="text-[10px] text-gray-600 max-w-xs mx-auto">
                {profile.address}
              </p>
            )}

            {!Capacitor.isNativePlatform() && (
              <div className="pt-4 mt-6 border-t border-white/10">
                <p className="text-gray-400 text-sm mb-3">Lebih nyaman bayar & dapet notifikasi tagihan?</p>
                <a 
                  href="https://github.com/afani-arba/noc-sentinel-v3/releases/latest/download/NOC.Sentinel.Client.APK.apk" 
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Button className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-xl h-11 flex items-center justify-center gap-2">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-download"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
                    Download Aplikasi Android (APK)
                  </Button>
                </a>
              </div>
            )}

            <div className="pt-4 mt-4 border-t border-white/5 space-y-1">
              <p className="text-[10px] text-gray-600 font-medium tracking-wide">Powered By PT Arsya Barokah Abadi</p>
              <p>
                <a href="https://www.arbatraining.com" target="_blank" rel="noreferrer" className="text-[10px] text-indigo-500/80 hover:text-indigo-400 transition-colors">
                  www.arbatraining.com
                </a>
              </p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
