import { Capacitor } from '@capacitor/core';
import { PushNotifications } from '@capacitor/push-notifications';
import axios from 'axios';

export const registerPushNotifications = async (token) => {
  // Hanya jalankan jika berjalan di dalam Native Android/iOS App
  if (!Capacitor.isNativePlatform()) {
    console.log("Push notifications skipped (Running in standard web browser)");
    return;
  }

  try {
    let permStatus = await PushNotifications.checkPermissions();

    if (permStatus.receive === 'prompt') {
      permStatus = await PushNotifications.requestPermissions();
    }

    if (permStatus.receive !== 'granted') {
      console.warn("User denied push notification permissions");
      return;
    }

    // Daftarkan channel untuk Android 8+ agar bisa muncul Pop-Up (Heads-up) dan getar kuat
    if (Capacitor.getPlatform() === 'android') {
      try {
        await PushNotifications.createChannel({
          id: 'billing_alerts',
          name: 'Tagihan & Peringatan',
          description: 'Notifikasi tagihan dan isolir layanan',
          importance: 5, // IMPORTANCE_HIGH (5)
          visibility: 1, // VISIBILITY_PUBLIC (1)
          vibration: true,
          lights: true,
        });
      } catch (e) {
        console.warn('Failed to create push channel', e);
      }
    }

    // Daftarkan ke sistem native (Apple/Google)
    await PushNotifications.register();

    // Listener saat HP menerima token rahasia dari Firebase
    PushNotifications.addListener('registration', async (fcmToken) => {
      console.log('FCM Token received:', fcmToken.value);
      // Kirim token ini ke NOC Sentinel Backend secara diam-diam
      try {
        await axios.post('/api/client-portal/device-token', 
          { token: fcmToken.value, device_type: Capacitor.getPlatform() },
          { headers: { Authorization: `Bearer ${token}` } }
        );
        console.log('FCM Token successfully synced to NOC Sentinel');
      } catch (err) {
        console.error('Failed to sync FCM Token to Backend', err);
      }
    });

    PushNotifications.addListener('registrationError', (error) => {
      console.error('Error on FCM registration: ', error);
    });

    PushNotifications.addListener('pushNotificationReceived', (notification) => {
      console.log('Push notification received: ', notification);
      // Anda bisa memunculkan Toast Custom di sini jika aplikasi sedang terbuka
    });

  } catch (error) {
    console.error("Error registering push notifications", error);
  }
};
