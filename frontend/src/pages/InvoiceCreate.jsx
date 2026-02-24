import React, { useEffect, useState } from "react";
import axios from "axios";
import InvoiceHeader from "../components/invoice/InvoiceHeader";
import CustomerSection from "../components/invoice/CustomerSection";
import InvoiceItemsTable from "../components/invoice/InvoiceItemsTable";
import InvoiceTotals from "../components/invoice/InvoiceTotals";
import InvoicePayments from "../components/invoice/InvoicePayments";
import { computeInvoiceTotals } from "../components/invoice/invoiceTotalsUtils";

function getCsrfToken() {
  const el = document.querySelector('meta[name="csrf-token"]');
  if (el) return el.getAttribute("content") || "";
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : "";
}

export default function InvoiceCreate() {
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState(null);
  const [issueTaxInvoice, setIssueTaxInvoice] = useState(true);
  const [currency, setCurrency] = useState("ZWL");
  const [customerName, setCustomerName] = useState("");
  const [customerTin, setCustomerTin] = useState("");
  const [customerAddress, setCustomerAddress] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState([]);
  const [payments, setPayments] = useState([{ method: "CASH", amount: 0 }]);
  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState(null);
  const [result, setResult] = useState(null);

  useEffect(() => {
    axios.get("/api/devices/", { withCredentials: true }).then((r) => setDevices(r.data.devices || [])).catch(() => setDevices([]));
  }, []);

  const INVOICE_TAXES = [
    { taxID: 1, taxPercent: 0, taxCode: "1" },
    { taxID: 2, taxPercent: 0, taxCode: "2" },
    { taxID: 517, taxPercent: 15.5, taxCode: "517" },
  ];

  useEffect(() => {
    if (items.length === 0) {
      const firstTax = INVOICE_TAXES[0];
      setItems([{
        description: "",
        quantity: 1,
        unit_price: 0,
        tax_id: firstTax.taxID,
        tax_percent: firstTax.taxPercent,
        tax_code: firstTax.taxCode,
        hs_code: "",
      }]);
    }
  }, [items.length]);

  useEffect(() => {
    if (!submitting || !deviceId) return;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/fdms/device/${deviceId}/`);
    ws.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        if (d.type === "receipt.progress") setProgress(d);
        if (d.type === "receipt.completed" || d.type === "receipt.failed" || d.type === "error") {
          ws.close();
        }
      } catch (_) {}
    };
    return () => ws.close();
  }, [submitting, deviceId]);

  const { grandTotal } = computeInvoiceTotals(items);

  useEffect(() => {
    const totalPaid = payments.reduce((s, p) => s + (parseFloat(p.amount) || 0), 0);
    if (grandTotal > 0 && totalPaid < grandTotal && payments.length > 0) {
      const shortfall = Math.round((grandTotal - totalPaid) * 100) / 100;
      setPayments((prev) => {
        const next = [...prev];
        const newAmount = Math.round(((parseFloat(next[0].amount) || 0) + shortfall) * 100) / 100;
        next[0] = { ...next[0], amount: newAmount };
        return next;
      });
    }
  }, [grandTotal]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!deviceId) {
      setResult({ error: "Select a device" });
      return;
    }
    if (items.some((it) => !(it.description || "").trim())) {
      setResult({ error: "All items must have an item name" });
      return;
    }
    if (items.some((it) => it.tax_id == null || it.tax_id === "")) {
      setResult({ error: "All items must have a tax selected (0% or 15.5%)" });
      return;
    }
    if (issueTaxInvoice && !customerName.trim() && !customerTin.trim()) {
      setResult({ error: "Tax invoice requires customer name or TIN" });
      return;
    }
    const validPcts = [0, 15.5];
    const validTaxIds = [1, 2, 517];
    if (items.some((it) => !validTaxIds.includes(parseInt(it.tax_id, 10)))) {
      setResult({ error: "Invalid tax. Use 0% (1/2) or 15.5% (517) only." });
      return;
    }
    if (items.some((it) => !validPcts.includes(parseFloat(it.tax_percent)))) {
      setResult({ error: "Invalid tax. Use 0% or 15.5% only." });
      return;
    }
    const totalPaid = payments.reduce((s, p) => s + (parseFloat(p.amount) || 0), 0);
    if (totalPaid < grandTotal) {
      setResult({ error: "Payment total must be >= grand total" });
      return;
    }
    setResult(null);
    setSubmitting(true);
    setProgress({ percent: 0, stage: "Submitting..." });
    try {
      const payload = {
        device_id: deviceId,
        issue_tax_invoice: issueTaxInvoice,
        currency,
        customer_name: customerName,
        customer_tin: customerTin,
        customer_address: customerAddress,
        customer_phone: customerPhone,
        customer_email: customerEmail,
        notes,
        items: items.map((it) => ({
          item_name: (it.description || "").trim(),
          quantity: parseFloat(it.quantity) || 0,
          unit_price: parseFloat(it.unit_price) || 0,
          tax_id: it.tax_id,
          tax_percent: Number.isNaN(parseFloat(it.tax_percent)) ? null : parseFloat(it.tax_percent),
          tax_code: (it.tax_code || "").trim() || null,
          hs_code: (it.hs_code || "").trim() || "000000",
        })),
        payments: payments.map((p) => ({ method: p.method, amount: parseFloat(p.amount) || 0 })),
      };
      const r = await axios.post("/api/invoices/", payload, {
        withCredentials: true,
        headers: { "X-CSRFToken": getCsrfToken(), "Content-Type": "application/json" },
      });
      setResult({ success: true, ...r.data });
    } catch (err) {
      setResult({ error: err.response?.data?.error || err.message });
    } finally {
      setSubmitting(false);
      setProgress(null);
    }
  };

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold text-slate-800 mb-6">Create Invoice</h1>
      <form onSubmit={handleSubmit}>
        <InvoiceHeader
          deviceId={deviceId}
          setDeviceId={setDeviceId}
          currency={currency}
          setCurrency={setCurrency}
          devices={devices}
        />
        <div className="mb-4">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={issueTaxInvoice}
              onChange={(e) => setIssueTaxInvoice(e.target.checked)}
            />
            <span>Issue tax invoice (requires buyer details)</span>
          </label>
        </div>
        <CustomerSection
          customerName={customerName}
          setCustomerName={setCustomerName}
          customerTin={customerTin}
          setCustomerTin={setCustomerTin}
          customerAddress={customerAddress}
          setCustomerAddress={setCustomerAddress}
          customerPhone={customerPhone}
          setCustomerPhone={setCustomerPhone}
          customerEmail={customerEmail}
          setCustomerEmail={setCustomerEmail}
          notes={notes}
          setNotes={setNotes}
        />
        <InvoiceItemsTable
          items={items}
          setItems={setItems}
          isVatRegistered={devices.find((d) => d.device_id === deviceId)?.is_vat_registered ?? true}
        />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <InvoiceTotals items={items} />
          <InvoicePayments payments={payments} setPayments={setPayments} grandTotal={grandTotal} />
        </div>
        {submitting && (
          <div className="mb-4 p-4 bg-indigo-50 rounded-lg">
            <p className="text-indigo-800 font-medium">{progress?.stage || "Submitting..."}</p>
            <div className="mt-2 h-2 bg-indigo-200 rounded overflow-hidden">
              <div
                className="h-full bg-indigo-600 transition-all"
                style={{ width: `${progress?.percent ?? 0}%` }}
              />
            </div>
          </div>
        )}
        {result && (
          <div
            className={`mb-4 p-4 rounded-lg ${result.error ? "bg-red-50 text-red-800" : "bg-green-50 text-green-800"}`}
          >
            {result.error ? (
              <p>{result.error}</p>
            ) : (
              <p>
                Success! Receipt #{result.receipt_global_no} (FDMS ID: {result.receipt_id})
                {result.invoice_no && ` • Invoice: ${result.invoice_no}`}
              </p>
            )}
          </div>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="px-6 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? "Submitting..." : "Submit to FDMS"}
        </button>
      </form>
    </div>
  );
}
