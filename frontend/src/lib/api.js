import axios from 'axios';

import { Capacitor } from '@capacitor/core';

// Use relative URL so Nginx proxies /api/ to backend automatically.
// If running natively via Capacitor, read the user-configured server URL.
const getBaseUrl = () => {
  if (Capacitor.isNativePlatform()) {
    const saved = localStorage.getItem('clientServerUrl');
    return saved ? `${saved}/api` : '/api';
  }
  return '/api';
};

const api = axios.create({ baseURL: getBaseUrl() });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('noc_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Jangan reload halaman jika 401 berasal dari percobaan login
      if (error.config?.url !== '/auth/login') {
        localStorage.removeItem('noc_token');
        localStorage.removeItem('noc_user');
        window.location.href = '/login';
      }
    }
    if (error.response?.status === 403 && error.response?.data?.detail?.includes("License Error")) {
      if (window.location.pathname !== '/admin/license') {
        window.location.href = '/admin/license';
      }
    }
    return Promise.reject(error);
  }
);

export default api;

