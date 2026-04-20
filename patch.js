const fs = require('fs');
let filePaths = [
    'e:/noc-billing-pro/frontend/src/pages/HotspotBillingPage.jsx'
];

filePaths.forEach(fp => {
    let content = fs.readFileSync(fp, 'utf8');
    
    // Replace the imports line
    content = content.replace(
        /import \{ Plus, Trash2, Edit, Save, RefreshCw, Send, CheckCircle2, Ticket, XCircle, Settings2, Package, Globe, Clock, MessageCircle, Activity, ShoppingCart, Loader2, Link2, Download, Zap, Wifi, WifiOff, ArrowRightLeft, Radio, AlertTriangle, AlertCircle, MessageSquare, Key, Image, ShieldCheck, CreditCard, Printer, BarChart2, List, TrendingUp, CheckCircle, Ban \} from "lucide-react";/,
        'import { Plus, Trash2, Edit, Save, RefreshCw, Send, CheckCircle2, Ticket, XCircle, Settings2, Package, Globe, Clock, MessageCircle, Activity, ShoppingCart, Loader2, Link2, Download, Zap, Wifi, WifiOff, ArrowRightLeft, Radio, AlertTriangle, AlertCircle, MessageSquare, Key, Image, ShieldCheck, CreditCard, Printer, BarChart2, List, TrendingUp, CheckCircle, Ban, Banknote, Landmark, Bot, QrCode } from "lucide-react";'
    );

    // Replace the select items options block
    content = content.replace(
        / <SelectContent>\s*<SelectItem value="cash">.*?<\/SelectItem>\s*<SelectItem value="transfer">.*?<\/SelectItem>\s*<SelectItem value="qris">.*?<\/SelectItem>\s*<SelectItem value="transfer_moota">.*?<\/SelectItem>\s*<\/SelectContent>/s,
        ` <SelectContent>
                <SelectItem value="cash"><div className="flex items-center gap-1.5"><Banknote className="w-4 h-4"/> Tunai / Cash</div></SelectItem>
                <SelectItem value="transfer"><div className="flex items-center gap-1.5"><Landmark className="w-4 h-4"/> Transfer Bank</div></SelectItem>
                <SelectItem value="qris"><div className="flex items-center gap-1.5"><QrCode className="w-4 h-4"/> QRIS</div></SelectItem>
                <SelectItem value="transfer_moota"><div className="flex items-center gap-1.5"><Bot className="w-4 h-4"/> Auto-Moota</div></SelectItem>
              </SelectContent>`);

    fs.writeFileSync(fp, content, 'utf8');
});

console.log("Patched hotspots");
