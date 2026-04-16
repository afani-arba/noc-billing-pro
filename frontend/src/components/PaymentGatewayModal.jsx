/**
 * PaymentGatewayModal — Modal pilih provider & tampilkan instruksi bayar
 * Mendukung: Xendit VA, Xendit QRIS, BCA VA, BRI VA, E-Wallet (GoPay/OVO/Dana/ShopeePay)
 * Auto-polling status pembayaran setiap 5 detik.
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';

const API_BASE = '/api';

const PROVIDERS = [
  {
    id: 'xendit_va',
    label: 'Virtual Account (Xendit)',
    provider: 'xendit',
    payment_type: 'virtual_account',
    icon: '🏦',
    desc: 'Transfer via ATM/m-banking ke nomor VA',
    banks: ['BNI', 'BCA', 'BRI', 'MANDIRI', 'PERMATA', 'BSI'],
  },
  {
    id: 'xendit_qris',
    label: 'QRIS (Xendit)',
    provider: 'xendit',
    payment_type: 'qris',
    icon: '📱',
    desc: 'Scan QR dengan GoPay, OVO, Dana, ShopeePay, QRIS manapun',
  },
  {
    id: 'bca_va',
    label: 'Virtual Account BCA',
    provider: 'bca',
    payment_type: 'virtual_account',
    icon: '🏦',
    desc: 'Transfer via ATM/m-banking BCA ke nomor VA',
  },
  {
    id: 'bri_va',
    label: 'Virtual Account BRI (BRIVA)',
    provider: 'bri',
    payment_type: 'virtual_account',
    icon: '🏦',
    desc: 'Transfer via ATM/m-banking BRI ke nomor BRIVA',
  },
  {
    id: 'xendit_gopay',
    label: 'GoPay',
    provider: 'xendit',
    payment_type: 'ewallet',
    ewallet_type: 'GOPAY',
    icon: '💚',
    desc: 'Bayar langsung via GoPay / Gojek',
  },
  {
    id: 'xendit_ovo',
    label: 'OVO',
    provider: 'xendit',
    payment_type: 'ewallet',
    ewallet_type: 'OVO',
    icon: '💜',
    desc: 'Bayar langsung via OVO',
  },
  {
    id: 'xendit_dana',
    label: 'DANA',
    provider: 'xendit',
    payment_type: 'ewallet',
    ewallet_type: 'DANA',
    icon: '💙',
    desc: 'Bayar langsung via DANA',
  },
  {
    id: 'xendit_shopeepay',
    label: 'ShopeePay',
    provider: 'xendit',
    payment_type: 'ewallet',
    ewallet_type: 'SHOPEEPAY',
    icon: '🧡',
    desc: 'Bayar langsung via ShopeePay',
  },
];

function rupiah(n) {
  return `Rp ${Number(n).toLocaleString('id-ID')}`;
}

export default function PaymentGatewayModal({ invoice, onClose, onPaid }) {
  const [step, setStep] = useState('select'); // select | confirm | waiting | success
  const [selectedProvider, setSelectedProvider] = useState(null);
  const [selectedBank, setSelectedBank] = useState('BNI');
  const [paymentInfo, setPaymentInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [pollCount, setPollCount] = useState(0);
  const pollerRef = useRef(null);
  const isMounted = useRef(true);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
      if (pollerRef.current) clearInterval(pollerRef.current);
    };
  }, []);

  const handleSelect = (p) => {
    setSelectedProvider(p);
    setError('');
    if (p.banks) setSelectedBank(p.banks[0]);
  };

  const handleCreatePayment = async () => {
    if (!selectedProvider) return;
    setLoading(true);
    setError('');
    try {
      const body = {
        provider: selectedProvider.provider,
        payment_type: selectedProvider.payment_type,
      };
      if (selectedProvider.payment_type === 'virtual_account' && selectedProvider.provider === 'xendit') {
        body.bank_code = selectedBank;
      }
      if (selectedProvider.ewallet_type) {
        body.ewallet_type = selectedProvider.ewallet_type;
      }

      const res = await fetch(`${API_BASE}/billing/invoices/${invoice.id}/create-payment`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Gagal membuat instruksi bayar');
      setPaymentInfo(data.payment_info);
      setStep('waiting');
      startPolling();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const startPolling = useCallback(() => {
    if (pollerRef.current) clearInterval(pollerRef.current);
    pollerRef.current = setInterval(async () => {
      if (!isMounted.current) return;
      try {
        const res = await fetch(`${API_BASE}/billing/invoices/${invoice.id}/payment-status`, {
          credentials: 'include',
        });
        if (!res.ok) return;
        const data = await res.json();
        if (data.status === 'paid') {
          if (pollerRef.current) clearInterval(pollerRef.current);
          if (isMounted.current) {
            setStep('success');
            if (onPaid) onPaid(invoice.id);
          }
        }
        if (isMounted.current) setPollCount((c) => c + 1);
      } catch (_) {}
    }, 5000);
  }, [invoice.id, onPaid]);

  const handleCopyVA = (text) => {
    navigator.clipboard.writeText(text).catch(() => {});
  };

  return (
    <div style={styles.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={styles.modal}>
        {/* Header */}
        <div style={styles.header}>
          <div>
            <div style={styles.headerTitle}>💳 Pembayaran Invoice</div>
            <div style={styles.headerSub}>
              {invoice.invoice_number} · {rupiah(invoice.total)}
            </div>
          </div>
          <button style={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        {/* Body */}
        <div style={styles.body}>
          {step === 'select' && (
            <>
              <div style={styles.sectionLabel}>Pilih Metode Pembayaran</div>
              <div style={styles.providerGrid}>
                {PROVIDERS.map(p => (
                  <button
                    key={p.id}
                    style={{
                      ...styles.providerCard,
                      ...(selectedProvider?.id === p.id ? styles.providerCardSelected : {}),
                    }}
                    onClick={() => handleSelect(p)}
                  >
                    <span style={styles.providerIcon}>{p.icon}</span>
                    <span style={styles.providerLabel}>{p.label}</span>
                    <span style={styles.providerDesc}>{p.desc}</span>
                  </button>
                ))}
              </div>

              {/* Bank Selector (only for Xendit VA) */}
              {selectedProvider?.banks && (
                <div style={styles.bankSelect}>
                  <label style={styles.sectionLabel}>Pilih Bank Virtual Account</label>
                  <div style={styles.bankGrid}>
                    {selectedProvider.banks.map(b => (
                      <button
                        key={b}
                        style={{
                          ...styles.bankBtn,
                          ...(selectedBank === b ? styles.bankBtnSelected : {}),
                        }}
                        onClick={() => setSelectedBank(b)}
                      >
                        {b}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {error && <div style={styles.error}>{error}</div>}

              <button
                style={{
                  ...styles.payBtn,
                  opacity: selectedProvider && !loading ? 1 : 0.5,
                }}
                disabled={!selectedProvider || loading}
                onClick={handleCreatePayment}
              >
                {loading ? '⏳ Membuat instruksi bayar...' : `Lanjutkan — ${rupiah(invoice.total)}`}
              </button>
            </>
          )}

          {step === 'waiting' && paymentInfo && (
            <div style={styles.waitingSection}>
              {/* VA Instructions */}
              {paymentInfo.type === 'virtual_account' && (
                <>
                  <div style={styles.vaBox}>
                    <div style={styles.vaLabel}>Nomor Virtual Account</div>
                    <div style={styles.vaBank}>{paymentInfo.bank_code || paymentInfo.provider?.toUpperCase()}</div>
                    <div style={styles.vaNumber}>{paymentInfo.account_number}</div>
                    <button
                      style={styles.copyBtn}
                      onClick={() => handleCopyVA(paymentInfo.account_number)}
                    >
                      📋 Salin Nomor VA
                    </button>
                  </div>
                  <div style={styles.amountBox}>
                    <div style={styles.amountLabel}>Jumlah Transfer Tepat</div>
                    <div style={styles.amountValue}>{rupiah(paymentInfo.amount)}</div>
                    <div style={styles.amountNote}>
                      ⚠️ Transfer harus tepat sesuai nominal (termasuk kode unik)
                    </div>
                  </div>
                  <div style={styles.instructions}>
                    <b>Cara Bayar:</b>
                    <ol style={{ margin: '8px 0 0', paddingLeft: '20px', lineHeight: '1.8' }}>
                      <li>Buka aplikasi m-banking / ATM</li>
                      <li>Pilih Transfer ke Virtual Account / BRIVA</li>
                      <li>Masukkan nomor VA di atas</li>
                      <li>Pastikan nominal tepat: <b>{rupiah(paymentInfo.amount)}</b></li>
                      <li>Konfirmasi dan selesaikan transaksi</li>
                    </ol>
                  </div>
                </>
              )}

              {/* QRIS */}
              {paymentInfo.type === 'qris' && (
                <div style={styles.qrisBox}>
                  <div style={styles.vaLabel}>Scan QR Code untuk Bayar</div>
                  {paymentInfo.qr_string && (
                    <img
                      src={`https://api.qrserver.com/v1/create-qr-code/?data=${encodeURIComponent(paymentInfo.qr_string)}&size=200x200`}
                      alt="QRIS"
                      style={styles.qrImage}
                    />
                  )}
                  <div style={styles.amountValue}>{rupiah(paymentInfo.amount)}</div>
                  <div style={styles.providerDesc}>Gunakan GoPay, OVO, Dana, ShopeePay, atau aplikasi QRIS manapun</div>
                </div>
              )}

              {/* E-Wallet */}
              {paymentInfo.type === 'ewallet' && paymentInfo.checkout_url && (
                <div style={styles.qrisBox}>
                  <div style={styles.vaLabel}>{paymentInfo.ewallet_type} — {rupiah(paymentInfo.amount)}</div>
                  <a
                    href={paymentInfo.checkout_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={styles.payBtnLink}
                  >
                    🚀 Buka Aplikasi {paymentInfo.ewallet_type}
                  </a>
                  <div style={styles.providerDesc}>Selesaikan pembayaran di aplikasi e-wallet Anda</div>
                </div>
              )}

              {/* Polling status */}
              <div style={styles.pollingStatus}>
                <div style={styles.spinner} />
                <span>Menunggu konfirmasi pembayaran...</span>
                <span style={styles.pollCounter}>(cek #{pollCount + 1})</span>
              </div>
            </div>
          )}

          {step === 'success' && (
            <div style={styles.successBox}>
              <div style={styles.successIcon}>✅</div>
              <div style={styles.successTitle}>Pembayaran Berhasil!</div>
              <div style={styles.successSub}>
                Invoice <b>{invoice.invoice_number}</b> telah lunas.<br />
                Layanan internet Anda akan segera diaktifkan kembali.
              </div>
              <button style={styles.payBtn} onClick={onClose}>Tutup</button>
            </div>
          )}
        </div>

        {/* Footer */}
        {step === 'waiting' && (
          <div style={styles.footer}>
            <button style={styles.cancelBtn} onClick={() => { setStep('select'); setPollCount(0); if (pollerRef.current) clearInterval(pollerRef.current); }}>
              ← Ganti Metode
            </button>
            <span style={styles.footerNote}>Halaman ini akan otomatis update saat pembayaran diterima</span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Inline Styles ──────────────────────────────────────────────────────── */
const styles = {
  overlay: {
    position: 'fixed', inset: 0, zIndex: 1100,
    background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(4px)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    padding: '16px',
  },
  modal: {
    background: '#1a1f2e', borderRadius: '16px', width: '100%', maxWidth: '560px',
    boxShadow: '0 24px 80px rgba(0,0,0,0.6)',
    border: '1px solid rgba(255,255,255,0.08)',
    display: 'flex', flexDirection: 'column', maxHeight: '92vh',
  },
  header: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
    padding: '20px 24px 16px', borderBottom: '1px solid rgba(255,255,255,0.08)',
  },
  headerTitle: { fontSize: '18px', fontWeight: 700, color: '#f1f5f9' },
  headerSub: { fontSize: '13px', color: '#94a3b8', marginTop: '4px' },
  closeBtn: {
    background: 'rgba(255,255,255,0.06)', border: 'none', color: '#94a3b8',
    width: '32px', height: '32px', borderRadius: '8px', cursor: 'pointer',
    fontSize: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center',
  },
  body: { padding: '20px 24px', overflowY: 'auto', flex: 1 },
  sectionLabel: { fontSize: '12px', color: '#64748b', fontWeight: 600,
    textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' },
  providerGrid: {
    display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '16px',
  },
  providerCard: {
    display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '4px',
    background: 'rgba(255,255,255,0.04)', border: '1.5px solid rgba(255,255,255,0.08)',
    borderRadius: '12px', padding: '14px', cursor: 'pointer', textAlign: 'left',
    transition: 'all 0.15s',
  },
  providerCardSelected: {
    border: '1.5px solid #3b82f6', background: 'rgba(59,130,246,0.12)',
  },
  providerIcon: { fontSize: '22px' },
  providerLabel: { fontSize: '13px', fontWeight: 600, color: '#e2e8f0' },
  providerDesc: { fontSize: '11px', color: '#64748b', lineHeight: '1.4' },
  bankSelect: { marginBottom: '16px' },
  bankGrid: { display: 'flex', flexWrap: 'wrap', gap: '8px' },
  bankBtn: {
    padding: '6px 14px', borderRadius: '8px', border: '1.5px solid rgba(255,255,255,0.08)',
    background: 'rgba(255,255,255,0.04)', color: '#94a3b8', cursor: 'pointer',
    fontSize: '13px', fontWeight: 600,
  },
  bankBtnSelected: { border: '1.5px solid #3b82f6', color: '#3b82f6', background: 'rgba(59,130,246,0.12)' },
  error: {
    background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.3)',
    borderRadius: '10px', padding: '10px 14px', color: '#f87171',
    fontSize: '13px', marginBottom: '14px',
  },
  payBtn: {
    width: '100%', padding: '14px', borderRadius: '12px', border: 'none',
    background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
    color: '#fff', fontSize: '15px', fontWeight: 700, cursor: 'pointer',
    marginTop: '8px', transition: 'opacity 0.2s',
  },
  payBtnLink: {
    display: 'inline-block', padding: '14px 24px', borderRadius: '12px',
    background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)', color: '#fff',
    fontSize: '15px', fontWeight: 700, textDecoration: 'none', marginBottom: '12px',
  },
  waitingSection: { display: 'flex', flexDirection: 'column', gap: '16px' },
  vaBox: {
    background: 'rgba(59,130,246,0.08)', border: '1.5px solid rgba(59,130,246,0.3)',
    borderRadius: '14px', padding: '20px', textAlign: 'center',
  },
  vaLabel: { fontSize: '12px', color: '#64748b', fontWeight: 600,
    textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' },
  vaBank: { fontSize: '14px', fontWeight: 700, color: '#3b82f6', marginBottom: '6px' },
  vaNumber: { fontSize: '28px', fontWeight: 800, color: '#f1f5f9',
    letterSpacing: '0.08em', fontFamily: 'monospace', marginBottom: '12px' },
  copyBtn: {
    padding: '8px 20px', borderRadius: '8px', border: '1.5px solid #3b82f6',
    background: 'transparent', color: '#3b82f6', cursor: 'pointer', fontWeight: 600, fontSize: '13px',
  },
  amountBox: {
    background: 'rgba(16,185,129,0.08)', border: '1.5px solid rgba(16,185,129,0.3)',
    borderRadius: '14px', padding: '16px', textAlign: 'center',
  },
  amountLabel: { fontSize: '12px', color: '#64748b', fontWeight: 600,
    textTransform: 'uppercase', marginBottom: '6px' },
  amountValue: { fontSize: '26px', fontWeight: 800, color: '#10b981', marginBottom: '6px' },
  amountNote: { fontSize: '12px', color: '#f59e0b' },
  instructions: {
    background: 'rgba(255,255,255,0.04)', borderRadius: '12px', padding: '16px',
    fontSize: '13px', color: '#94a3b8',
  },
  qrisBox: {
    background: 'rgba(255,255,255,0.04)', borderRadius: '14px', padding: '20px',
    textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px',
  },
  qrImage: { width: '200px', height: '200px', borderRadius: '12px', background: '#fff', padding: '8px' },
  pollingStatus: {
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px',
    padding: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '12px',
    fontSize: '13px', color: '#64748b',
  },
  spinner: {
    width: '16px', height: '16px', borderRadius: '50%',
    border: '2px solid rgba(255,255,255,0.1)', borderTopColor: '#3b82f6',
    animation: 'spin 1s linear infinite',
  },
  pollCounter: { fontSize: '11px', color: '#475569' },
  successBox: {
    display: 'flex', flexDirection: 'column', alignItems: 'center',
    padding: '32px 16px', gap: '12px', textAlign: 'center',
  },
  successIcon: { fontSize: '56px', lineHeight: 1 },
  successTitle: { fontSize: '22px', fontWeight: 800, color: '#10b981' },
  successSub: { fontSize: '14px', color: '#94a3b8', lineHeight: '1.6', marginBottom: '16px' },
  footer: {
    padding: '14px 24px', borderTop: '1px solid rgba(255,255,255,0.08)',
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  },
  cancelBtn: {
    background: 'none', border: 'none', color: '#64748b', cursor: 'pointer',
    fontSize: '13px', fontWeight: 600,
  },
  footerNote: { fontSize: '11px', color: '#475569', textAlign: 'right', maxWidth: '200px' },
};
