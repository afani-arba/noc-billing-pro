import api from './api';

export async function printInvoiceWithProfile(invoice, pkgName, customerName, customerUsername, customerPhone, customerAddress) {
  let profile = {};
  try {
     // Fetch profil perusahaan untuk mendapatkan logo_base64 dan nama perusahaan
     const r = await api.get("/system/company-profile");
     profile = r.data || {};
  } catch(e) {
     console.error("Gagal get profile", e);
  }

  const Rp = (n) => `Rp ${(Number(n) || 0).toLocaleString("id-ID")}`;
  const fmtDate = (isoStr) => {
    if (!isoStr) return "";
    const p = String(isoStr).substring(0, 10).split("-");
    return p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : isoStr;
  };

  const hasLogo = !!profile.logo_base64;
  const logoHtml = hasLogo ? `<img src="${profile.logo_base64}" alt="Logo" class="logo" />` : '';

  // Gunakan data dari parameter ATAU dari objek invoice (fallback)
  const custName     = customerName     || invoice.customer_name     || '—';
  const custUsername = customerUsername || invoice.customer_username || '—';
  const custPhone    = customerPhone    || invoice.customer_phone    || '—';
  const custAddress  = customerAddress  || invoice.customer_address  || '';
  const companyName  = profile.product_name || profile.company_name || 'NOC Sentinel';
  const companyAddr  = profile.address || '';
  const companyWA    = profile.whatsapp_number ? 'WA: ' + profile.whatsapp_number : '';

  const statusLabel = invoice.status === 'paid' ? 'LUNAS' : invoice.status === 'overdue' ? 'JATUH TEMPO' : 'BELUM BAYAR';
  const statusColor = invoice.status === 'paid' ? '#22c55e' : invoice.status === 'overdue' ? '#ef4444' : '#f59e0b';

  const printedAt = new Date().toLocaleString('id-ID', { day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' });

  const html = `
    <html><head><title>Invoice #${invoice.invoice_number}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body { font-family: 'Inter', 'Segoe UI', system-ui, sans-serif; color: #111; background: #fff; -webkit-font-smoothing: antialiased; }
      
      /* ── HALAMAN UTAMA ── */
      .page { width: 100%; max-width: 720px; margin: 0 auto; background: #fff; overflow-x: hidden; }
      
      /* ── HEADER / BANNER GELAP ── */
      .header {
        background: #0f172a;
        color: #fff;
        padding: 24px;
        display: flex;
        flex-wrap: wrap;
        align-items: flex-start;
        justify-content: space-between;
        gap: 16px;
      }
      .company-block { display: flex; align-items: center; gap: 12px; flex: 1; min-width: 200px; }
      .logo { max-width: 64px; max-height: 64px; object-fit: contain; border-radius: 6px; }
      .company-name { font-size: 20px; font-weight: 800; color: #fff; letter-spacing: -.3px; line-height: 1.2; word-break: break-word; }
      .company-sub { font-size: 11px; color: #94a3b8; margin-top: 4px; }
      .company-wa  { font-size: 11px; color: #64748b; margin-top: 2px; }
      
      .inv-block { text-align: left; flex-shrink: 0; min-width: 140px; }
      @media (min-width: 480px) { .inv-block { text-align: right; } }
      .inv-label { font-size: 11px; font-weight: 700; color: #f59e0b; letter-spacing: 1.5px; text-transform: uppercase; }
      .inv-number { font-size: 18px; font-weight: 800; color: #f59e0b; margin-top: 2px; word-break: break-all; }
      .inv-date { font-size: 12px; color: #94a3b8; margin-top: 4px; }
      .status-badge {
        display: inline-block;
        margin-top: 10px;
        padding: 4px 10px;
        border: 2px solid ${statusColor};
        border-radius: 4px;
        color: ${statusColor};
        font-size: 12px;
        font-weight: 800;
        letter-spacing: 1px;
        text-transform: uppercase;
      }
      
      /* ── BODY ── */
      .body { padding: 24px; }
      
      /* ── CUSTOMER & PAYMENT BLOCK ── */
      .info-row { display: flex; flex-wrap: wrap; gap: 24px; margin-bottom: 24px; padding-bottom: 20px; border-bottom: 1px solid #e5e7eb; }
      .info-col { flex: 1; min-width: 200px; }
      .info-label { font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 1.2px; text-transform: uppercase; margin-bottom: 8px; }
      .info-name { font-size: 22px; font-weight: 700; color: #111; line-height: 1.2; }
      .info-sub { font-size: 13px; color: #6b7280; margin-top: 3px; }
      
      /* ── CUSTOMER INFO TABLE ── */
      .cust-table { width: 100%; border-collapse: collapse; margin-bottom: 24px; table-layout: fixed; }
      .cust-table th, .cust-table td { padding: 10px 12px; font-size: 12px; border: 1px solid #e5e7eb; vertical-align: top; word-break: break-word; }
      .cust-table th { background: #f8fafc; font-weight: 600; color: #374151; width: 40%; }
      .cust-table td { color: #111; font-weight: 500; width: 60%; }
      
      /* ── SECTION HEADER ── */
      .section-title { font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 10px; }
      
      /* ── SERVICE TABLE ── */
      .svc-table { width: 100%; border-collapse: collapse; margin-bottom: 8px; table-layout: fixed; }
      .svc-table thead tr { background: #f8fafc; }
      .svc-table th { padding: 10px 12px; font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 1px; text-transform: uppercase; text-align: left; border-bottom: 2px solid #e5e7eb; }
      .svc-table th:last-child { text-align: right; width: 35%; }
      .svc-table td { padding: 12px 12px; font-size: 12px; vertical-align: top; border-bottom: 1px solid #f3f4f6; word-break: break-word; }
      .svc-table td:last-child { text-align: right; font-weight: 600; }
      .svc-desc strong { font-weight: 600; color: #111; display: block; margin-bottom: 4px; }
      .svc-period { font-size: 11px; color: #9ca3af; }
      
      /* ── TOTAL SECTION ── */
      .total-section { margin-top: 4px; }
      .total-row { display: flex; padding: 10px 0; border-top: 1px dashed #e5e7eb; font-size: 13px; justify-content: space-between; }
      .total-final { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; background: #0f172a; color: #fff; padding: 16px; border-radius: 6px; margin-top: 12px; gap: 8px;}
      .total-final .label { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; }
      .total-final .amount { font-size: 20px; font-weight: 900; color: #f59e0b; }
      
      /* ── FOOTER ── */
      .footer { margin-top: 24px; padding-top: 16px; border-top: 1px solid #e5e7eb; display: flex; flex-direction: column; gap: 12px; text-align: left; }
      @media (min-width: 480px) { .footer { flex-direction: row; justify-content: space-between; } }
      .footer-left { font-size: 11px; color: #94a3b8; }
      .footer-right { font-size: 11px; color: #94a3b8; }
      @media (min-width: 480px) { .footer-right { text-align: right; } }
      .thank-you { font-size: 12px; color: #374151; font-weight: 500; margin-bottom: 4px; }

      @media print {
        body { print-color-adjust: exact; -webkit-print-color-adjust: exact; margin: 0; }
        .page { max-width: 100%; border: none; box-shadow: none; padding: 0; }
        .header { align-items: center; padding: 20px !important; }
      }
    </style></head><body>
    <div class="page">
      <!-- HEADER -->
      <div class="header">
        <div class="company-block">
          ${logoHtml}
          <div>
            <div class="company-name">${companyName}</div>
            ${companyAddr ? `<div class="company-sub">${companyAddr}</div>` : ''}
            ${companyWA ? `<div class="company-wa">${companyWA}</div>` : ''}
          </div>
        </div>
        <div class="inv-block">
          <div class="inv-label">Invoice</div>
          <div class="inv-number">#${invoice.invoice_number}</div>
          <div class="inv-date">${new Date().toLocaleDateString('id-ID', { day: 'numeric', month: 'long', year: 'numeric' })}</div>
          <div class="status-badge">${statusLabel}</div>
        </div>
      </div>

      <!-- BODY -->
      <div class="body">

        <!-- INFORMASI PELANGGAN -->
        <div class="section-title">Informasi Pelanggan</div>
        <table class="cust-table">
          <tr>
            <th>Nama Pelanggan</th>
            <td>${custName}</td>
          </tr>
          <tr>
            <th>Username / Client ID</th>
            <td>${custUsername}</td>
          </tr>
          <tr>
            <th>No. Telepon / WA</th>
            <td>${custPhone}</td>
          </tr>
          ${custAddress ? `<tr>
            <th>Alamat</th>
            <td>${custAddress}</td>
          </tr>` : ''}
          <tr>
            <th>Status Pembayaran</th>
            <td><span style="color: ${statusColor}; font-weight: 700;">${statusLabel}</span></td>
          </tr>
        </table>

        <!-- RINCIAN LAYANAN -->
        <div class="section-title" style="margin-top:8px;">Rincian Layanan &amp; Penagihan</div>
        <table class="svc-table">
          <thead>
            <tr>
              <th>Deskripsi Layanan</th>
              <th style="text-align:right;">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td class="svc-desc">
                <strong>Paket: ${pkgName || invoice.package_name || '—'}</strong>
                <div class="svc-period">Periode: ${fmtDate(invoice.period_start)} s/d ${fmtDate(invoice.period_end)}</div>
              </td>
              <td>${Rp(invoice.amount)}</td>
            </tr>
            ${invoice.discount ? `<tr>
              <td style="color:#6b7280;">Diskon Promo Berlangganan</td>
              <td style="color:#22c55e;">- ${Rp(invoice.discount)}</td>
            </tr>` : ''}
            ${invoice.unique_code ? `<tr>
              <td style="color:#6b7280;">Kode Unik</td>
              <td>+ ${Rp(invoice.unique_code)}</td>
            </tr>` : ''}
          </tbody>
        </table>
        
        <div class="total-section">
          <div class="total-final">
            <div class="label">Total Bayar</div>
            <div class="amount">${Rp(invoice.total)}</div>
          </div>
        </div>

        ${invoice.status === 'paid' ? `
        <div style="margin-top:14px; padding:12px 16px; background:#f0fdf4; border:1px solid #bbf7d0; border-radius:6px; font-size:12px; color:#166534;">
          ✅ Dibayar via <strong>${invoice.payment_method || '—'}</strong> pada ${invoice.paid_at?.slice(0, 10) || ''}
        </div>` : ''}

        <!-- FOOTER -->
        <div class="footer">
          <div class="footer-left">
            <div class="thank-you">Terima kasih atas kepercayaan Anda 🙏</div>
            <span>Dicetak pada: ${printedAt}</span>
          </div>
          <div class="footer-right">
            ${companyWA || companyAddr || ''}
          </div>
        </div>

      </div>
    </div>
    </body></html>
  `;

  // Deteksi Webview Ponsel / PWA / Capacitor
  const isMobileApp = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent) || window.Capacitor;

  if (isMobileApp) {
    // Implementasi Overlay Iframe demi Back-Button Aman
    const overlay = document.createElement('div');
    overlay.style.position = 'fixed';
    overlay.style.top = '0';
    overlay.style.left = '0';
    overlay.style.width = '100%';
    overlay.style.height = '100%';
    overlay.style.backgroundColor = '#f8fafc';
    overlay.style.zIndex = '9999999';
    overlay.style.display = 'flex';
    overlay.style.flexDirection = 'column';

    const header = document.createElement('div');
    header.style.padding = '16px';
    header.style.background = '#0f172a';
    header.style.display = 'flex';
    header.style.justifyContent = 'space-between';
    header.style.alignItems = 'center';
    header.innerHTML = `
      <span style="color:#fff; font-weight:700; font-family:sans-serif; font-size: 14px;">Preview Tagihan</span>
      <button id="closePrintBtn" style="background:#ef4444; color:#fff; border:none; padding:8px 16px; border-radius:6px; font-weight:700; font-size: 12px; cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">TUTUP (X)</button>
    `;

    const iframe = document.createElement('iframe');
    iframe.style.flex = '1';
    iframe.style.border = 'none';
    iframe.style.width = '100%';

    overlay.appendChild(header);
    overlay.appendChild(iframe);
    document.body.appendChild(overlay);

    // Mencegah scroll body tertinggal
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    // Tambah pushState untuk bisa kembali dengan HW Back Button
    const onPopState = () => {
       if(document.body.contains(overlay)) {
           document.body.removeChild(overlay);
           document.body.style.overflow = originalOverflow;
       }
       window.removeEventListener('popstate', onPopState);
    };
    window.history.pushState({ doc: 'print_preview' }, '', '#print');
    window.addEventListener('popstate', onPopState);

    header.querySelector('#closePrintBtn').onclick = () => {
      window.history.back(); // Memanggil onPopState otomatis via event
    };

    const doc = iframe.contentWindow.document;
    doc.open();
    doc.write(html);
    doc.close();
  } else {
    // Mode Desktop Biasa (Tab/Window Baru)
    const w = window.open('', '_blank', 'width=780,height=980');
    if(w) {
      w.document.write(html);
      w.document.close();
      w.focus();
      setTimeout(() => { w.print(); }, 700);
    } else {
      alert("Popup blocker mencegah print invoice tertampil. Izinkan popup untuk website ini.");
    }
  }
}
