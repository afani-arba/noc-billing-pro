$path = 'e:\noc-billing-pro\frontend\src\pages\HotspotBillingPage.jsx'
$content = Get-Content -Path $path -Raw -Encoding UTF8

$oldImport = 'import { Plus, Trash2, Edit, Save, RefreshCw, Send, CheckCircle2, Ticket, XCircle, Settings2, Package, Globe, Clock, MessageCircle, Activity, ShoppingCart, Loader2, Link2, Download, Zap, Wifi, WifiOff, ArrowRightLeft, Radio, AlertTriangle, AlertCircle, MessageSquare, Key, Image, ShieldCheck, CreditCard, Printer, BarChart2, List, TrendingUp, CheckCircle, Ban } from "lucide-react";'
$newImport = 'import { Plus, Trash2, Edit, Save, RefreshCw, Send, CheckCircle2, Ticket, XCircle, Settings2, Package, Globe, Clock, MessageCircle, Activity, ShoppingCart, Loader2, Link2, Download, Zap, Wifi, WifiOff, ArrowRightLeft, Radio, AlertTriangle, AlertCircle, MessageSquare, Key, Image, ShieldCheck, CreditCard, Printer, BarChart2, List, TrendingUp, CheckCircle, Ban, Banknote, Landmark, Bot, QrCode } from "lucide-react";'

$content = $content.Replace($oldImport, $newImport)

$pattern = '(?s)<SelectContent>\s*<SelectItem value="cash">.*?</SelectItem>\s*<SelectItem value="transfer">.*?</SelectItem>\s*<SelectItem value="qris">.*?</SelectItem>\s*<SelectItem value="transfer_moota">.*?</SelectItem>\s*</SelectContent>'

$replacement = '<SelectContent>
                <SelectItem value="cash"><div className="flex items-center gap-1.5"><Banknote className="w-4 h-4"/> Tunai / Cash</div></SelectItem>
                <SelectItem value="transfer"><div className="flex items-center gap-1.5"><Landmark className="w-4 h-4"/> Transfer Bank</div></SelectItem>
                <SelectItem value="qris"><div className="flex items-center gap-1.5"><QrCode className="w-4 h-4"/> QRIS</div></SelectItem>
                <SelectItem value="transfer_moota"><div className="flex items-center gap-1.5"><Bot className="w-4 h-4"/> Auto-Moota</div></SelectItem>
              </SelectContent>'

$content = [System.Text.RegularExpressions.Regex]::Replace($content, $pattern, $replacement)

Set-Content -Path $path -Value $content -Encoding UTF8
Write-Host "Patched successfully!"
