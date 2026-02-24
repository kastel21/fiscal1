import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { RefreshCw, Link2, Unlink, CheckCircle, XCircle, Webhook, Activity, AlertTriangle } from "lucide-react";

export default function QuickBooksIntegrationUI() {
  const connected = true; // backend state

  const health = {
    lastSync: "2026-02-06 10:45",
    failedReceipts: 3,
  };

  const taxMappings = [
    { qbTax: "VAT15", fdmsTax: "VAT 15%" },
    { qbTax: "ZERO", fdmsTax: "Zero Rated" },
  ];

  const webhookEvents = [
    { id: 1, type: "SalesReceipt.Created", status: "Processed", time: "2026-02-06 10:12" },
    { id: 2, type: "Invoice.Paid", status: "Failed", time: "2026-02-06 09:41" },
  ];

  const devices = [
    { id: 1, name: "Harare Branch – Device 01" },
    { id: 2, name: "Bulawayo Branch – Device 02" },
  ];

  return (
    <div className="p-6 grid gap-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold">QuickBooks Integration Management</h1>

      {/* Branch / Device Selector */}
      <Card className="rounded-2xl shadow-sm">
        <CardContent className="p-6 grid gap-4">
          <h2 className="text-lg font-semibold">Active Branch / Device</h2>
          <Select defaultValue="1">
            <SelectTrigger className="w-[300px]">
              <SelectValue placeholder="Select branch / device" />
            </SelectTrigger>
            <SelectContent>
              {devices.map(d => (
                <SelectItem key={d.id} value={String(d.id)}>
                  {d.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {/* Integration Health Panel */}
      <Card className="rounded-2xl shadow-sm">
        <CardContent className="p-6 grid gap-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Activity size={18} /> Integration Health
          </h2>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Last Sync</p>
              <p className="font-medium">{health.lastSync}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Failed Receipts</p>
              <p className="font-medium text-red-600">{health.failedReceipts}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Connection</p>
              {connected ? (
                <Badge className="flex items-center gap-1" variant="success">
                  <CheckCircle size={14} /> Connected
                </Badge>
              ) : (
                <Badge className="flex items-center gap-1" variant="destructive">
                  <XCircle size={14} /> Disconnected
                </Badge>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Connection Controls */}
      <Card className="rounded-2xl shadow-sm">
        <CardContent className="p-6 grid gap-4">
          <h2 className="text-lg font-semibold">Connection Controls</h2>
          <div className="flex gap-3">
            {connected ? (
              <Button variant="destructive" className="gap-2">
                <Unlink size={16} /> Disconnect
              </Button>
            ) : (
              <Button className="gap-2">
                <Link2 size={16} /> Connect to QuickBooks
              </Button>
            )}
            <Button variant="outline" className="gap-2">
              <RefreshCw size={16} /> Refresh Token
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Tax Mapping */}
      <Card className="rounded-2xl shadow-sm">
        <CardContent className="p-6 grid gap-4">
          <h2 className="text-lg font-semibold">Tax Mapping (QuickBooks → FDMS)</h2>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>QuickBooks Tax Code</TableHead>
                <TableHead>FDMS Tax</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {taxMappings.map((t, i) => (
                <TableRow key={i}>
                  <TableCell>{t.qbTax}</TableCell>
                  <TableCell>{t.fdmsTax}</TableCell>
                  <TableCell>
                    <Button size="sm" variant="outline">Edit</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Button variant="outline">Add Tax Mapping</Button>
        </CardContent>
      </Card>

      {/* Webhook Monitor */}
      <Card className="rounded-2xl shadow-sm">
        <CardContent className="p-6 grid gap-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Webhook size={18} /> Webhook Monitor
          </h2>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Event</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Time</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {webhookEvents.map(e => (
                <TableRow key={e.id}>
                  <TableCell>{e.type}</TableCell>
                  <TableCell className={e.status === "Failed" ? "text-red-600" : ""}>
                    {e.status === "Failed" && <AlertTriangle size={14} className="inline mr-1" />}
                    {e.status}
                  </TableCell>
                  <TableCell>{e.time}</TableCell>
                  <TableCell>
                    <Button size="sm" variant="outline">Replay</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}