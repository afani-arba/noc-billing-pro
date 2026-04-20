import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { useTheme } from "@/context/ThemeContext";
import {
  ClipboardList, RefreshCw, Search, Filter, X, ChevronLeft, ChevronRight, Trash2
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

const ACTION_CONFIG = {
  CREATE:  { bg: "bg-blue-500/10",   border: "border-blue-500/40",   text: "text-blue-400",   label: "CREATE" },
  UPDATE:  { bg: "bg-yellow-500/10", border: "border-yellow-500/40", text: "text-yellow-400", label: "UPDATE" },
  DELETE:  { bg: "bg-red-500/10",    border: "border-red-500/40",    text: "text-red-400",    label: "DELETE" },
  LOGIN:   { bg: "bg-green-500/10",  border: "border-green-500/40",  text: "text-green-400",  label: "LOGIN" },
  LOGOUT:  { bg: "bg-slate-500/10",  border: "border-slate-500/40",  text: "text-slate-400",  label: "LOGOUT" },
  VIEW:    { bg: "bg-purple-500/10", border: "border-purple-500/40", text: "text-purple-400", label: "VIEW" },
};

function ActionBadge({ action }) {
  const c = ACTION_CONFIG[action?.toUpperCase()] || ACTION_CONFIG.VIEW;
  return (
    <span className={`inline-flex px-2 py-0.5 rounded text-[10px] font-bold border ${c.bg} ${c.border} ${c.text}`}>
      {c.label}
    </span>
  );
}

export default function AuditLogPage() {
  const { theme } = useTheme();
  const isCyber = theme === "cyber";
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);

  // Filters
  const [filterUsername, setFilterUsername] = useState("");
  const [filterAction, setFilterAction] = useState("__all__");
  const [filterResource, setFilterResource] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  // Pagination
  const [page, setPage] = useState(0);
  const LIMIT = 50;

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        limit: LIMIT,
        skip: page * LIMIT,
      };
      if (filterUsername) params.username = filterUsername;
      if (filterAction && filterAction !== "__all__") params.action = filterAction;
      if (filterResource) params.resource = filterResource;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;

      const r = await api.get("/audit/logs", { params });
      setLogs(r.data.logs || []);
      setTotal(r.data.total || 0);
    } catch (e) {
      console.error("Audit log fetch error:", e);
    }
    setLoading(false);
  }, [page, filterUsername, filterAction, filterResource, dateFrom, dateTo]);

  const fetchSummary = useCallback(async () => {
    try {
      const r = await api.get("/audit/summary");
      setSummary(r.data);
    } catch (e) {}
  }, []);

  useEffect(() => { fetchLogs(); fetchSummary(); }, [fetchLogs, fetchSummary]);

  const handleClear = () => {
    setFilterUsername("");
    setFilterAction("__all__");
    setFilterResource("");
    setDateFrom("");
    setDateTo("");
    setPage(0);
  };

  const totalPages = Math.ceil(total / LIMIT);
  const hasFilters = filterUsername || (filterAction && filterAction !== "__all__") || filterResource || dateFrom || dateTo;

  return (
    <div className="space-y-6 pb-16">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <ClipboardList className="w-6 h-6 text-purple-400" /> Audit Log
          </h1>
          <p className="text-sm text-muted-foreground">Track all user actions and system events</p>
        </div>
        <Button variant="outline" size="icon" className="h-9 w-9 rounded-sm" onClick={() => { fetchLogs(); fetchSummary(); }} disabled={loading}>
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </Button>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          <div className={`col-span-2 sm:col-span-1 px-3 py-2 ${ isCyber ? "glass-card" : "bg-card border border-border rounded-sm" }`}>
            <p className="text-[10px] uppercase text-muted-foreground">Last 7 Days</p>
            <p className="text-2xl font-bold text-foreground">{summary.total_last_7_days}</p>
          </div>
          {Object.entries(summary.by_action || {}).map(([action, count]) => {
            const c = ACTION_CONFIG[action] || {};
            return (
              <div key={action} className={`border rounded-sm px-3 py-2 ${c.bg} ${c.border}`}>
                <p className={`text-[10px] uppercase ${c.text}`}>{action}</p>
                <p className={`text-2xl font-bold ${c.text}`}>{count}</p>
              </div>
            );
          })}
        </div>
      )}

      {/* Filter Bar */}
      <div className={`p-3 flex flex-wrap gap-2 items-center ${ isCyber ? "glass-card" : "bg-card border border-border rounded-sm" }`}>
        <Filter className="w-4 h-4 text-muted-foreground flex-shrink-0" />

        <div className="relative min-w-32">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            value={filterUsername}
            onChange={e => { setFilterUsername(e.target.value); setPage(0); }}
            placeholder="Username..."
            className="pl-7 text-xs h-8 rounded-sm w-32"
          />
        </div>

        <Select value={filterAction} onValueChange={v => { setFilterAction(v); setPage(0); }}>
          <SelectTrigger className="w-32 h-8 text-xs rounded-sm"><SelectValue placeholder="All Actions" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Actions</SelectItem>
            {["CREATE", "UPDATE", "DELETE", "LOGIN", "LOGOUT"].map(a => <SelectItem key={a} value={a}>{a}</SelectItem>)}
          </SelectContent>
        </Select>

        <div className="relative min-w-32">
          <Input
            value={filterResource}
            onChange={e => { setFilterResource(e.target.value); setPage(0); }}
            placeholder="Resource..."
            className="text-xs h-8 rounded-sm w-32"
          />
        </div>

        <input
          type="date"
          value={dateFrom}
          onChange={e => { setDateFrom(e.target.value); setPage(0); }}
          className="h-8 px-2 text-xs rounded-sm border border-input bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />
        <span className="text-muted-foreground text-xs">to</span>
        <input
          type="date"
          value={dateTo}
          onChange={e => { setDateTo(e.target.value); setPage(0); }}
          className="h-8 px-2 text-xs rounded-sm border border-input bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />

        {hasFilters && (
          <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={handleClear}>
            <X className="w-3 h-3 mr-1" /> Clear
          </Button>
        )}

        <span className="ml-auto text-xs text-muted-foreground">{total.toLocaleString()} total entries</span>
      </div>

      {/* Log Table */}
      <div className={`overflow-hidden ${ isCyber ? "glass-card" : "bg-card border border-border rounded-sm" }`}>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 py-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">Timestamp</th>
                <th className="px-4 py-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">User</th>
                <th className="px-4 py-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">Action</th>
                <th className="px-4 py-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">Resource</th>
                <th className="px-4 py-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">Details</th>
                <th className="px-4 py-3 text-left text-[10px] uppercase tracking-wider text-muted-foreground">IP</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center">
                    <RefreshCw className="w-5 h-5 animate-spin mx-auto text-muted-foreground" />
                  </td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground text-sm">
                    <ClipboardList className="w-10 h-10 mx-auto mb-2 opacity-30" />
                    No audit log entries found
                    {hasFilters && <p className="text-xs mt-1 text-muted-foreground/50">Try clearing filters</p>}
                  </td>
                </tr>
              ) : (
                logs.map((log, i) => (
                  <tr key={log.id || i} className="border-b border-border/40 hover:bg-secondary/30 transition-colors">
                    <td className="px-4 py-2.5 text-xs font-mono text-muted-foreground whitespace-nowrap">
                      {log.timestamp ? new Date(log.timestamp).toLocaleString("id-ID") : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-xs font-semibold">{log.username || "system"}</td>
                    <td className="px-4 py-2.5"><ActionBadge action={log.action} /></td>
                    <td className="px-4 py-2.5 text-xs">
                      <span className="font-mono text-foreground/80">{log.resource}</span>
                      {log.resource_id && (
                        <span className="text-muted-foreground ml-1 text-[10px]">#{log.resource_id.slice(-8)}</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground max-w-xs truncate" title={log.details}>
                      {log.details || "—"}
                    </td>
                    <td className="px-4 py-2.5 text-xs font-mono text-muted-foreground">{log.ip_address || "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-border flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              Showing {page * LIMIT + 1}–{Math.min((page + 1) * LIMIT, total)} of {total}
            </p>
            <div className="flex items-center gap-1">
              <Button
                variant="outline" size="icon" className="h-7 w-7 rounded-sm"
                disabled={page === 0} onClick={() => setPage(p => p - 1)}
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </Button>
              <span className="text-xs text-muted-foreground px-2">
                {page + 1} / {totalPages}
              </span>
              <Button
                variant="outline" size="icon" className="h-7 w-7 rounded-sm"
                disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

