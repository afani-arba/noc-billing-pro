/** @type {import('@capacitor/cli').CapacitorConfig} */
const config = {
  appId: 'com.nocsentinel.client',
  appName: 'NOC Sentinel',
  webDir: 'build',
  bundledWebRuntime: false,
  plugins: {
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert'],
    },
  },
  server: {
    cleartext: true,
  }
};

module.exports = config;
