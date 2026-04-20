import { useState, useEffect, useRef, useCallback } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  MessageCircle, CheckCircle2, AlertTriangle, Clock, Search,
  Send, Trash2, RefreshCw, User, Phone, MessageSquare, X,
  StickyNote, Check, Smartphone, Wifi, RotateCcw, Bot,
  ChevronRight, Filter
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/context/ThemeContext";

// ── Helpers ───────────────────────────────────────────────────────────────────
const STATUS_CONFIG = {
  pending:   { label: "Pending",   color: "text-amber-400",   bg: "bg-amber-400/10 border-amber-400/30",   dot: "bg-amber-400",   icon: Clock },
  open:      { label: "Open",      color: "text-blue-400",    bg: "bg-blue-400/10 border-blue-400/30",     dot: "bg-blue-400",    icon: MessageCircle },
  replied:   { label: "Dibalas",   color: "text-emerald-400", bg: "bg-emerald-400/10 border-emerald-400/30", dot: "bg-emerald-400", icon: CheckCircle2 },
  resolved:  { label: "Selesai",   color: "text-emerald-400", bg: "bg-emerald-400/10 border-emerald-400/30", dot: "bg-emerald-400", icon: CheckCircle2 },
  escalated: { label: "Eskalasi!", color: "text-rose-400",    bg: "bg-rose-400/10 border-rose-400/30",     dot: "bg-rose-400",    icon: AlertTriangle },
  closed:    { label: "Tutup",     color: "text-slate-400",   bg: "bg-slate-400/10 border-slate-400/30",   dot: "bg-slate-400",   icon: X },
};

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.open;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-semibold ${cfg.bg} ${cfg.color}`}>
      <Icon className="w-2.5 h-2.5" />{cfg.label}
    </span>
  );
}

function formatTimestamp(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  const now = new Date();
  if (d.toDateString() === now.toDateString())
    return d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleDateString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function avatarLetter(name) { return (name || "?").charAt(0).toUpperCase(); }
function avatarColor(seed) {
  const colors = ["bg-blue-500","bg-purple-500","bg-emerald-500","bg-rose-500","bg-amber-500","bg-cyan-500","bg-indigo-500","bg-pink-500"];
  let h = 0; for (let i = 0; i < (seed||"").length; i++) h += seed.charCodeAt(i);
  return colors[h % colors.length];
}
function threadStatus(c) {
  if (c.has_escalated) return "escalated";
  if (c.pending_count > 0) return "pending";
  return "resolved";
}

// ══════════════════════════════════════════════════════════════════════════════
// WA CHAT TAB
// ══════════════════════════════════════════════════════════════════════════════
function WAChatTab() {
  const { theme } = useTheme();
  const isCyber = theme === "cyber";
  const [contacts, setContacts] = useState([]);
  const [selectedSender, setSelectedSender] = useState(null);
  const [messages, setMessages] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [msgLoading, setMsgLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [noteInput, setNoteInput] = useState("");
  const [showNoteFor, setShowNoteFor] = useState(null);
  const chatEndRef = useRef(null);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const fetchContacts = useCallback(async () => {
    try {
      const params = filterStatus !== "all" ? `?status=${filterStatus}` : "";
      const res = await api.get(`/wa-chat/conversations${params}`);
      setContacts(res.data);
    } catch { toast.error("Gagal memuat daftar percakapan"); } finally { setLoading(false); }
  }, [filterStatus]);

  const fetchStats = useCallback(async () => {
    try { const res = await api.get("/wa-chat/stats"); setStats(res.data); } catch {}
  }, []);

  const fetchMessages = useCallback(async (sender) => {
    if (!sender) return;
    setMsgLoading(true);
    try { const res = await api.get(`/wa-chat/conversations/${encodeURIComponent(sender)}`); setMessages(res.data); }
    catch { toast.error("Gagal memuat percakapan"); } finally { setMsgLoading(false); }
  }, []);

  useEffect(() => { fetchContacts(); fetchStats(); }, [fetchContacts, fetchStats]);
  useEffect(() => { const t = setInterval(() => { fetchContacts(); fetchStats(); }, 30000); return () => clearInterval(t); }, [fetchContacts, fetchStats]);

  const filteredContacts = contacts.filter(c => !search || c.sender_name?.toLowerCase().includes(search.toLowerCase()) || c.sender?.includes(search));
  const selectedContact = contacts.find(c => c.sender === selectedSender);

  const handleSendReply = async () => {
    if (!replyText.trim() || !selectedSender) return;
    setSending(true);
    try {
      await api.post("/wa-chat/reply", { sender: selectedSender, message: replyText.trim() });
      toast.success("Pesan berhasil dikirim!"); setReplyText("");
      await fetchMessages(selectedSender); await fetchContacts(); await fetchStats();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengirim pesan"); } finally { setSending(false); }
  };

  const handleUpdateStatus = async (sender, status) => {
    try {
      await api.put(`/wa-chat/conversations/sender/${encodeURIComponent(sender)}/status`, { status });
      toast.success(`Status: ${STATUS_CONFIG[status]?.label}`);
      await fetchContacts(); await fetchStats();
      if (selectedSender === sender) await fetchMessages(sender);
    } catch { toast.error("Gagal update status"); }
  };

  return (
    <div className={`flex flex-1 min-h-0 gap-0 border rounded-lg overflow-hidden ${ isCyber ? "glass-card border-white/5" : "bg-card border-border" }`} style={{ height: "calc(100vh - 300px)" }}>
      {/* Left */}
      <div className={`w-72 flex-shrink-0 border-r flex flex-col ${ isCyber ? "border-white/5 bg-black/20" : "border-border" }`}>
        <div className="p-3 border-b border-border space-y-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-muted-foreground" />
            <input type="text" placeholder="Cari nama / nomor..." value={search} onChange={e => setSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-2 text-xs bg-secondary border border-border rounded-md text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary" />
          </div>
          <div className="flex gap-1">
            {["all","pending","escalated","resolved"].map(s => (
              <button key={s} onClick={() => setFilterStatus(s)}
                className={`flex-1 text-[10px] py-1 rounded transition-colors font-medium ${filterStatus===s ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground hover:bg-secondary"}`}>
                {s==="all" ? "Semua" : STATUS_CONFIG[s]?.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loading ? <div className="flex items-center justify-center h-32"><RefreshCw className="w-5 h-5 animate-spin text-muted-foreground" /></div>
          : filteredContacts.length === 0 ? <div className="flex flex-col items-center justify-center h-32 text-muted-foreground"><MessageSquare className="w-8 h-8 mb-2 opacity-30" /><p className="text-xs">Belum ada percakapan</p></div>
          : filteredContacts.map(c => {
            const ts = threadStatus(c); const cfg = STATUS_CONFIG[ts]; const isSel = selectedSender === c.sender;
            return (
              <div key={c.sender} onClick={() => { setSelectedSender(c.sender); setReplyText(""); fetchMessages(c.sender); }}
                className={`flex items-start gap-3 p-3 cursor-pointer border-b border-border/50 transition-colors hover:bg-secondary/50 ${isSel ? "bg-primary/5 border-l-2 border-l-primary" : ""}`}>
                <div className={`w-9 h-9 rounded-full flex-shrink-0 flex items-center justify-center text-white text-sm font-bold ${avatarColor(c.sender)}`}>{avatarLetter(c.sender_name)}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-0.5">
                    <p className="text-xs font-semibold text-foreground truncate">{c.sender_name || c.sender}</p>
                    <span className="text-[10px] text-muted-foreground flex-shrink-0">{formatTimestamp(c.last_timestamp)}</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground truncate">{c.last_message}</p>
                  <div className="flex items-center justify-between mt-1"><StatusBadge status={ts} /></div>
                </div>
              </div>
            );
          })}
        </div>
        <div className="p-2 border-t border-border">
          <button onClick={() => { fetchContacts(); fetchStats(); }}
            className="w-full flex items-center justify-center gap-2 py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
            <RefreshCw className="w-3 h-3" /> Refresh (auto 30s)
          </button>
        </div>
      </div>
      {/* Right */}
      {selectedSender ? (
        <div className="flex-1 flex flex-col min-w-0">
          <div className={`flex items-center justify-between px-4 py-3 border-b ${ isCyber ? "border-white/5 bg-black/20" : "border-border bg-card" }`}>
            <div className="flex items-center gap-3">
              <div className={`w-9 h-9 rounded-full flex-shrink-0 flex items-center justify-center text-white text-sm font-bold ${avatarColor(selectedSender)}`}>{avatarLetter(selectedContact?.sender_name)}</div>
              <div>
                <p className="text-sm font-semibold text-foreground">{selectedContact?.sender_name || selectedSender}</p>
                <p className="text-[11px] text-muted-foreground flex items-center gap-1"><Phone className="w-3 h-3" />{selectedSender}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {[["resolved","Selesai","emerald"],["escalated","Eskalasi","rose"],["pending","Pending","amber"]].map(([s,l,c]) => (
                <button key={s} onClick={() => handleUpdateStatus(selectedSender, s)}
                  className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs bg-${c}-500/10 text-${c}-400 border border-${c}-500/20 hover:bg-${c}-500/20 transition-colors`}>
                  {l}
                </button>
              ))}
            </div>
          </div>
          <div className={`flex-1 overflow-y-auto p-4 space-y-4`} style={isCyber ? { background: "linear-gradient(to bottom, rgba(15,23,42,0.8), rgba(0,0,0,0.5))" } : { background: "hsl(var(--background))" }}>
            {msgLoading ? <div className="flex items-center justify-center h-32"><RefreshCw className="w-5 h-5 animate-spin text-muted-foreground" /></div>
            : messages.map(msg => {
              const isAdminMsg = msg.message?.startsWith("[ADMIN REPLY]");
              return (
                <div key={msg._id} className="space-y-2">
                  {!isAdminMsg && (
                    <div className="flex items-start gap-2">
                      <div className={`w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center text-white text-xs font-bold ${avatarColor(selectedSender)}`}>{avatarLetter(selectedContact?.sender_name)}</div>
                      <div className="max-w-[70%]">
                        <div className="bg-secondary border border-border rounded-lg rounded-tl-none px-3 py-2"><p className="text-xs text-foreground">{msg.message}</p></div>
                        <p className="text-[10px] text-muted-foreground mt-1 ml-1">{formatTimestamp(msg.timestamp)}</p>
                      </div>
                    </div>
                  )}
                  {msg.response && !isAdminMsg && (
                    <div className="flex items-start gap-2 flex-row-reverse">
                      <div className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center bg-primary text-primary-foreground text-xs font-bold">AI</div>
                      <div className="max-w-[70%]">
                        <div className="bg-primary/10 border border-primary/20 rounded-lg rounded-tr-none px-3 py-2"><p className="text-xs text-foreground whitespace-pre-wrap">{msg.response}</p></div>
                        <div className="flex items-center justify-end gap-2 mt-1 mr-1">
                          <p className="text-[10px] text-muted-foreground">{formatTimestamp(msg.timestamp)}</p>
                          <StatusBadge status={msg.status} />
                        </div>
                      </div>
                    </div>
                  )}
                  {isAdminMsg && (
                    <div className="flex items-start gap-2 flex-row-reverse">
                      <div className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center bg-emerald-500 text-white text-xs font-bold">A</div>
                      <div className="max-w-[70%]">
                        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg rounded-tr-none px-3 py-2">
                          <p className="text-[10px] text-emerald-400 font-semibold mb-0.5">Admin (Manual)</p>
                          <p className="text-xs text-foreground whitespace-pre-wrap">{msg.response}</p>
                        </div>
                        <p className="text-[10px] text-muted-foreground mt-1 mr-1 text-right">{formatTimestamp(msg.timestamp)}</p>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
            <div ref={chatEndRef} />
          </div>
          <div className={`p-3 border-t ${ isCyber ? "border-white/5 bg-black/20" : "border-border bg-card" }`}>
            <div className="flex gap-2">
              <textarea value={replyText} onChange={e => setReplyText(e.target.value)}
                onKeyDown={e => { if (e.key==="Enter"&&!e.shiftKey){e.preventDefault();handleSendReply();} }}
                placeholder="Ketik balasan... (Enter kirim, Shift+Enter baris baru)" rows={2}
                className="flex-1 px-3 py-2 text-sm bg-secondary border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary resize-none" />
              <Button onClick={handleSendReply} disabled={!replyText.trim()||sending} className="self-end flex items-center gap-2" size="sm">
                {sending ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />} Kirim
              </Button>
            </div>
            <p className="text-[10px] text-muted-foreground mt-1.5 flex items-center gap-1"><User className="w-3 h-3" />Kirim via WhatsApp (Fonnte)</p>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-3">
          <div className="w-16 h-16 rounded-2xl bg-secondary flex items-center justify-center"><MessageCircle className="w-8 h-8 opacity-40" /></div>
          <div className="text-center"><p className="text-sm font-medium">Pilih percakapan</p><p className="text-xs">Klik pelanggan di sebelah kiri</p></div>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// IN-APP CHAT TAB
// ══════════════════════════════════════════════════════════════════════════════
function InAppChatTab() {
  const { theme } = useTheme();
  const isCyber = theme === "cyber";
  const [tickets, setTickets] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("all");
  const chatEndRef = useRef(null);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [selectedTicket]);

  const fetchTickets = useCallback(async () => {
    try {
      const res = await api.get("/client-portal/admin/inapp-chats");
      setTickets(res.data.tickets || []);
    } catch { toast.error("Gagal memuat daftar chat"); } finally { setLoading(false); }
  }, []);

  const fetchMessages = useCallback(async (ticketId) => {
    try {
      const res = await api.get(`/client-portal/admin/inapp-chats/${ticketId}/messages`);
      setSelectedTicket(res.data.ticket);
    } catch { toast.error("Gagal memuat pesan"); }
  }, []);

  useEffect(() => { fetchTickets(); }, [fetchTickets]);
  useEffect(() => { const t = setInterval(() => { fetchTickets(); if (selectedId) fetchMessages(selectedId); }, 10000); return () => clearInterval(t); }, [fetchTickets, fetchMessages, selectedId]);

  const handleSelect = (t) => { setSelectedId(t.id); setReplyText(""); fetchMessages(t.id); };

  const handleReply = async () => {
    if (!replyText.trim() || !selectedId) return;
    setSending(true);
    try {
      await api.post(`/client-portal/admin/inapp-chats/${selectedId}/reply`, { message: replyText.trim() });
      toast.success("Balasan terkirim + FCM push dikirim ke pelanggan ✓");
      setReplyText("");
      await fetchMessages(selectedId);
      await fetchTickets();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengirim balasan"); } finally { setSending(false); }
  };

  const handleStatus = async (ticketId, status) => {
    try {
      await api.patch(`/client-portal/admin/inapp-chats/${ticketId}/status`, { status });
      toast.success(`Status diupdate: ${STATUS_CONFIG[status]?.label}`);
      await fetchTickets();
      if (selectedId === ticketId) await fetchMessages(ticketId);
    } catch { toast.error("Gagal update status"); }
  };

  const filtered = tickets.filter(t => {
    const matchSearch = !search || t.customer_name?.toLowerCase().includes(search.toLowerCase());
    const matchStatus = filterStatus === "all" || t.status === filterStatus;
    return matchSearch && matchStatus;
  });

  const unreadCount = tickets.filter(t => t.unread_count > 0).length;

  // Summary stats
  const stats = {
    total: tickets.length,
    open: tickets.filter(t => t.status === "open").length,
    escalated: tickets.filter(t => t.status === "escalated").length,
    replied: tickets.filter(t => t.status === "replied").length,
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Stats */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Total Chat", value: stats.total, color: "text-foreground" },
          { label: "Perlu Dibalas", value: stats.open, color: "text-blue-400" },
          { label: "Eskalasi", value: stats.escalated, color: "text-rose-400" },
          { label: "Dibalas AI/CS", value: stats.replied, color: "text-emerald-400" },
        ].map(s => (
          <div key={s.label} className={`p-3 rounded-lg ${ isCyber ? "glass-card border-none" : "bg-card border border-border" }`}>
            <p className={`text-lg font-bold ${s.color}`}>{s.value}</p>
            <p className="text-[11px] text-muted-foreground">{s.label}</p>
          </div>
        ))}
      </div>

      <div className={`flex flex-1 min-h-0 gap-0 border rounded-lg overflow-hidden ${ isCyber ? "glass-card border-white/5" : "bg-card border-border" }`} style={{ height: "calc(100vh - 380px)" }}>
        {/* Left Panel */}
        <div className={`w-72 flex-shrink-0 border-r flex flex-col ${ isCyber ? "border-white/5 bg-black/20" : "border-border" }`}>
          <div className="p-3 border-b border-border space-y-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-muted-foreground" />
              <input type="text" placeholder="Cari nama pelanggan..." value={search} onChange={e => setSearch(e.target.value)}
                className="w-full pl-8 pr-3 py-2 text-xs bg-secondary border border-border rounded-md text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary" />
            </div>
            <div className="flex gap-1">
              {["all","open","escalated","replied","closed"].map(s => (
                <button key={s} onClick={() => setFilterStatus(s)}
                  className={`flex-1 text-[9px] py-1 rounded transition-colors font-medium ${filterStatus===s ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground hover:bg-secondary"}`}>
                  {s==="all" ? "Semua" : STATUS_CONFIG[s]?.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {loading ? <div className="flex items-center justify-center h-32"><RefreshCw className="w-5 h-5 animate-spin text-muted-foreground" /></div>
            : filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-32 text-muted-foreground">
                <Smartphone className="w-8 h-8 mb-2 opacity-30" />
                <p className="text-xs">Belum ada chat in-app</p>
              </div>
            ) : filtered.map(t => (
              <div key={t.id} onClick={() => handleSelect(t)}
                className={`flex items-start gap-3 p-3 cursor-pointer border-b border-border/50 transition-colors hover:bg-secondary/50 ${selectedId===t.id ? "bg-primary/5 border-l-2 border-l-primary" : ""}`}>
                <div className="relative">
                  <div className={`w-9 h-9 rounded-full flex-shrink-0 flex items-center justify-center text-white text-sm font-bold ${avatarColor(t.customer_name)}`}>
                    {avatarLetter(t.customer_name)}
                  </div>
                  {t.unread_count > 0 && (
                    <span className="absolute -top-1 -right-1 w-4 h-4 bg-rose-500 rounded-full flex items-center justify-center text-[9px] text-white font-bold">{t.unread_count}</span>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-0.5">
                    <p className="text-xs font-semibold text-foreground truncate">{t.customer_name}</p>
                    <span className="text-[10px] text-muted-foreground flex-shrink-0">{formatTimestamp(t.last_ts)}</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground truncate">{t.last_message}</p>
                  <div className="flex items-center gap-1 mt-1">
                    <StatusBadge status={t.status} />
                    {t.messages?.some(m => m.action_taken) && (
                      <span className="text-[9px] bg-purple-500/10 text-purple-400 border border-purple-500/20 px-1.5 py-0.5 rounded flex items-center gap-0.5">
                        <Bot className="w-2 h-2" /> AI Action
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="p-2 border-t border-border">
            <button onClick={fetchTickets} className="w-full flex items-center justify-center gap-2 py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
              <RefreshCw className="w-3 h-3" /> Refresh (auto 10s)
            </button>
          </div>
        </div>

        {/* Right Panel */}
        {selectedTicket ? (
          <div className="flex-1 flex flex-col min-w-0">
            {/* Header */}
            <div className={`flex items-center justify-between px-4 py-3 border-b ${ isCyber ? "border-white/5 bg-black/20" : "border-border bg-card" }`}>
              <div className="flex items-center gap-3">
                <div className={`w-9 h-9 rounded-full flex-shrink-0 flex items-center justify-center text-white text-sm font-bold ${avatarColor(selectedTicket.customer_name)}`}>
                  {avatarLetter(selectedTicket.customer_name)}
                </div>
                <div>
                  <p className="text-sm font-semibold text-foreground">{selectedTicket.customer_name}</p>
                  <p className="text-[11px] text-muted-foreground flex items-center gap-1">
                    <Smartphone className="w-3 h-3" /> In-App Chat
                    <StatusBadge status={selectedTicket.status} />
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => handleStatus(selectedTicket.id, "resolved")}
                  className="flex items-center gap-1 px-2.5 py-1.5 rounded text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors">
                  <CheckCircle2 className="w-3 h-3" /> Selesai
                </button>
                <button onClick={() => handleStatus(selectedTicket.id, "escalated")}
                  className="flex items-center gap-1 px-2.5 py-1.5 rounded text-xs bg-rose-500/10 text-rose-400 border border-rose-500/20 hover:bg-rose-500/20 transition-colors">
                  <AlertTriangle className="w-3 h-3" /> Eskalasi
                </button>
                <button onClick={() => handleStatus(selectedTicket.id, "closed")}
                  className="flex items-center gap-1 px-2.5 py-1.5 rounded text-xs bg-slate-500/10 text-slate-400 border border-slate-500/20 hover:bg-slate-500/20 transition-colors">
                  <X className="w-3 h-3" /> Tutup
                </button>
              </div>
            </div>

            {/* Messages */}
            <div className={`flex-1 overflow-y-auto p-4 space-y-3`} style={isCyber ? { background: "linear-gradient(to bottom, rgba(15,23,42,0.8), rgba(0,0,0,0.5))" } : { background: "hsl(var(--background))" }}>
              {(selectedTicket.messages || []).map((msg, i) => (
                <div key={i}>
                  {/* Client message */}
                  {msg.sender === "client" && (
                    <div className="flex items-start gap-2">
                      <div className={`w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center text-white text-xs font-bold ${avatarColor(selectedTicket.customer_name)}`}>
                        {avatarLetter(selectedTicket.customer_name)}
                      </div>
                      <div className="max-w-[70%]">
                        {msg.image_base64 && (
                          <img src={msg.image_base64} className="w-48 rounded-lg mb-1 object-cover border border-border" alt="foto pelanggan" />
                        )}
                        <div className="bg-secondary border border-border rounded-lg rounded-tl-none px-3 py-2">
                          <p className="text-xs text-foreground whitespace-pre-wrap">{msg.message}</p>
                        </div>
                        <p className="text-[10px] text-muted-foreground mt-1 ml-1">{formatTimestamp(msg.timestamp)}</p>
                      </div>
                    </div>
                  )}

                  {/* AI Reply */}
                  {msg.ai_reply && (
                    <div className="flex items-start gap-2 flex-row-reverse mt-2">
                      <div className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center bg-violet-600 text-white text-xs font-bold">
                        <Bot className="w-3.5 h-3.5" />
                      </div>
                      <div className="max-w-[75%]">
                        <div className="bg-violet-500/10 border border-violet-500/20 rounded-lg rounded-tr-none px-3 py-2">
                          <p className="text-[10px] text-violet-400 font-semibold mb-0.5 flex items-center gap-1"><Bot className="w-2.5 h-2.5" /> AI (Gemini)</p>
                          <p className="text-xs text-foreground whitespace-pre-wrap">{msg.ai_reply}</p>
                        </div>
                        {msg.action_taken && (
                          <div className="mt-1 mr-1 flex items-center justify-end gap-1">
                            {msg.action_taken === "modem_reprovisioned" && (
                              <span className="text-[9px] bg-blue-500/10 text-blue-400 border border-blue-500/20 px-1.5 py-0.5 rounded flex items-center gap-0.5">
                                <RotateCcw className="w-2 h-2" /> Modem Re-Provisioned
                              </span>
                            )}
                            {msg.action_taken === "cable_issue" && (
                              <span className="text-[9px] bg-red-500/10 text-red-400 border border-red-500/20 px-1.5 py-0.5 rounded flex items-center gap-0.5">
                                <AlertTriangle className="w-2 h-2" /> Alert Telegram Terkirim
                              </span>
                            )}
                            {msg.action_taken === "needs_cs" && (
                              <span className="text-[9px] bg-amber-500/10 text-amber-400 border border-amber-500/20 px-1.5 py-0.5 rounded flex items-center gap-0.5">
                                <User className="w-2 h-2" /> Perlu CS Manusia
                              </span>
                            )}
                          </div>
                        )}
                        <p className="text-[10px] text-muted-foreground mt-1 mr-1 text-right">{formatTimestamp(msg.timestamp)}</p>
                      </div>
                    </div>
                  )}

                  {/* CS Reply */}
                  {msg.sender === "cs" && (
                    <div className="flex items-start gap-2 flex-row-reverse mt-2">
                      <div className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center bg-emerald-500 text-white text-xs font-bold">CS</div>
                      <div className="max-w-[75%]">
                        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg rounded-tr-none px-3 py-2">
                          <p className="text-[10px] text-emerald-400 font-semibold mb-0.5">{msg.cs_name || "CS NOC"}</p>
                          <p className="text-xs text-foreground whitespace-pre-wrap">{msg.message}</p>
                        </div>
                        <p className="text-[10px] text-muted-foreground mt-1 mr-1 text-right">{formatTimestamp(msg.timestamp)}</p>
                      </div>
                    </div>
                  )}
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>

            {/* Reply Box */}
            <div className={`p-3 border-t ${ isCyber ? "border-white/5 bg-black/20" : "border-border bg-card" }`}>
              <div className="flex gap-2">
                <textarea value={replyText} onChange={e => setReplyText(e.target.value)}
                  onKeyDown={e => { if (e.key==="Enter"&&!e.shiftKey){e.preventDefault();handleReply();} }}
                  placeholder="Ketik balasan CS... (Enter kirim, Shift+Enter baris baru)" rows={2}
                  className="flex-1 px-3 py-2 text-sm bg-secondary border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary resize-none" />
                <Button onClick={handleReply} disabled={!replyText.trim()||sending} className="self-end flex items-center gap-2" size="sm">
                  {sending ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />} Kirim
                </Button>
              </div>
              <p className="text-[10px] text-muted-foreground mt-1.5 flex items-center gap-1">
                <Smartphone className="w-3 h-3" /> Balasan akan dikirim ke App Pelanggan via FCM Push Notification
              </p>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-3">
            <div className="w-16 h-16 rounded-2xl bg-secondary flex items-center justify-center"><Smartphone className="w-8 h-8 opacity-40" /></div>
            <div className="text-center">
              <p className="text-sm font-medium">Pilih percakapan In-App</p>
              <p className="text-xs">Chat dari aplikasi portal pelanggan</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// MAIN PAGE: Tab Switcher
// ══════════════════════════════════════════════════════════════════════════════
export default function WACustomerServicePage() {
  const { theme } = useTheme();
  const isCyber = theme === "cyber";
  const [activeTab, setActiveTab] = useState("inapp");
  const [inappUnread, setInappUnread] = useState(0);

  // Poll unread count for In-App badge
  useEffect(() => {
    const fetchUnread = async () => {
      try {
        const res = await api.get("/client-portal/admin/inapp-chats");
        const tickets = res.data.tickets || [];
        setInappUnread(tickets.filter(t => t.unread_count > 0).length);
      } catch {}
    };
    fetchUnread();
    const t = setInterval(fetchUnread, 15000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Header */}
      <div>
        <h1 className={`text-xl font-bold flex items-center gap-2 ${ isCyber ? "gradient-text font-mono" : "text-foreground" }`}>
          <MessageCircle className={`w-5 h-5 ${ isCyber ? "" : "text-emerald-400" }`} style={isCyber ? { color: "hsl(162,100%,50%)" } : {}} />
          {isCyber ? "> Customer Service Command Center" : "Customer Service Command Center"}
        </h1>
        <p className={`text-sm mt-1 ${ isCyber ? "font-mono text-[hsl(185,100%,35%)]" : "text-muted-foreground" }`}>Monitor dan balas percakapan pelanggan dari WhatsApp & Aplikasi Portal</p>
      </div>

      {/* Tab Switcher */}
      <div className="flex gap-2 border-b border-border pb-0">
        <button
          onClick={() => setActiveTab("wa")}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "wa"
              ? "border-emerald-500 text-emerald-400"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          <MessageCircle className="w-4 h-4" />
          WhatsApp Chat
        </button>
        <button
          onClick={() => setActiveTab("inapp")}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors relative ${
            activeTab === "inapp"
              ? "border-violet-500 text-violet-400"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          <Smartphone className="w-4 h-4" />
          In-App Chat
          <Bot className="w-3.5 h-3.5 text-violet-400" />
          {inappUnread > 0 && (
            <span className="absolute -top-1 -right-1 w-4 h-4 bg-rose-500 rounded-full flex items-center justify-center text-[9px] text-white font-bold">
              {inappUnread}
            </span>
          )}
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === "wa" ? <WAChatTab /> : <InAppChatTab />}
    </div>
  );
}
