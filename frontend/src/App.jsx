import { useState } from "react";
import { AuthProvider } from "./auth/AuthContext";
import ProtectedRoute from "./auth/ProtectedRoute";
import Layout from "./layout/Layout";
import DashboardPage from "./components/dashboard/DashboardPage";
import InvoiceCreate from "./pages/InvoiceCreate";
import KPIDashboard from "./pages/KPIDashboard";
import CompanySettings from "./pages/CompanySettings";
import DeviceList from "./pages/DeviceList";
import DeviceDetail from "./pages/DeviceDetail";
import ProductList from "./pages/ProductList";
import ProductForm from "./pages/ProductForm";
import CustomerList from "./pages/CustomerList";
import CustomerForm from "./pages/CustomerForm";

function AppContent() {
  const [view, setView] = useState("kpi");
  const [selectedDeviceId, setSelectedDeviceId] = useState(null);
  const [productView, setProductView] = useState("list");
  const [customerView, setCustomerView] = useState("list");

  return (
    <ProtectedRoute>
      <Layout onViewChange={setView}>
        {view === "kpi" && <KPIDashboard />}
        {view === "system" && <DashboardPage />}
        {view === "company" && <CompanySettings />}
        {view === "devices" && (
          selectedDeviceId ? (
            <DeviceDetail devicePk={selectedDeviceId} onBack={() => setSelectedDeviceId(null)} />
          ) : (
            <DeviceList onSelectDevice={setSelectedDeviceId} />
          )
        )}
        {view === "products" && (
          productView === "list" ? (
            <ProductList
              onAdd={() => setProductView("add")}
              onEdit={(id) => setProductView(id)}
            />
          ) : (
            <ProductForm
              productId={productView === "add" ? null : productView}
              onSaved={() => setProductView("list")}
              onCancel={() => setProductView("list")}
            />
          )
        )}
        {view === "customers" && (
          customerView === "list" ? (
            <CustomerList
              onAdd={() => setCustomerView("add")}
              onEdit={(id) => setCustomerView(id)}
            />
          ) : (
            <CustomerForm
              customerId={customerView === "add" ? null : customerView}
              onSaved={() => setCustomerView("list")}
              onCancel={() => setCustomerView("list")}
            />
          )
        )}
        {view === "invoice" && <InvoiceCreate />}
      </Layout>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
