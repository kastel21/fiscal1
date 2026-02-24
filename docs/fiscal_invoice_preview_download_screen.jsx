/**
 * Fiscal Invoice Preview & Download — UI reference (React/shadcn).
 * Implemented in Django: fiscal_ui.views.fiscal_invoice_preview_download,
 * template fiscal_ui/fiscal_invoice_preview_download.html.
 * Routes: /fiscal/invoice/<id>/preview-download/ | .../preview/ | .../download/
 */
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Download, Eye } from "lucide-react";

export default function FiscalInvoicePreview({ receipt }) {
  const data = receipt ?? {
    status: "FISCALIZED",
    receiptID: "FDMS-123456",
    total: 11.5,
    date: "2026-02-06 10:30",
    currency_code: "USD",
  };

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Fiscal Invoice</h1>

      <Card className="rounded-2xl shadow-sm">
        <CardContent className="p-6 grid gap-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Receipt ID</p>
              <p className="font-mono">{data.receiptID}</p>
            </div>
            <Badge variant="success">Fiscalized</Badge>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Date</p>
              <p>{data.date}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Total</p>
              <p>{data.currency_code ?? "USD"} {(data.total ?? 0).toFixed(2)}</p>
            </div>
          </div>

          <div className="flex gap-3 mt-4">
            <Button variant="outline" className="gap-2" asChild>
              <a href={data.previewUrl} target="_blank" rel="noopener noreferrer">
                <Eye size={16} /> Preview Invoice
              </a>
            </Button>
            <Button className="gap-2" asChild>
              <a href={data.downloadUrl}>
                <Download size={16} /> Download Fiscal Invoice (PDF)
              </a>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}