"use client";

import { usePathname } from "next/navigation";
import dynamic from "next/dynamic";
import Shell from "@/components/Shell";

// ========== صفحات (با import داینامیک) ==========
const DashboardMain = dynamic(() => import("@/components/pages/DashboardMain"));
const FinanceDashboard = dynamic(() => import("@/components/pages/FinanceDashboard"));
const TransactionsList = dynamic(() => import("@/components/pages/TransactionsList"));
const ProductsList = dynamic(() => import("@/components/pages/ProductsList"));
const ProductsDetail = dynamic(() => import("@/components/pages/ProductsDetail"));
const VendorsList = dynamic(() => import("@/components/pages/VendorsList"));
const PurchasesList = dynamic(() => import("@/components/pages/PurchasesList"));
const EmployeesList = dynamic(() => import("@/components/pages/EmployeesList"));
const PayrollPage = dynamic(() => import("@/components/pages/PayrollPage"));
const SurgeriesList = dynamic(() => import("@/components/pages/SurgeriesList"));
const ContactsList = dynamic(() => import("@/components/pages/ContactsList"));

// مپ مسیرها به کامپوننت‌ها (با پشتیبانی از id)
const routeMap: Record<string, React.ComponentType<{ id?: string }>> = {
  "/dashboard": DashboardMain,
  "/finance": FinanceDashboard,
  "/finance/transactions": TransactionsList,
  "/inventory": ProductsList,
  "/inventory/products": ProductsList,
  "/inventory/vendors": VendorsList,
  "/inventory/purchases": PurchasesList,
  "/employees": EmployeesList,
  "/payroll": PayrollPage,
  "/surgeries": SurgeriesList,
  "/contacts": ContactsList,
};

export default function DynamicPage() {
  const pathname = usePathname() || "/dashboard";

  // استخراج basePath و id (اگر وجود داشته باشد)
  const parts = pathname.split("/").filter(Boolean);
  let basePath = "/" + parts.slice(0, 2).join("/"); // مثلاً /inventory/products
  let id: string | undefined;

  // اگر بخش سوم عدد بود، آن را به‌عنوان id در نظر بگیر
  if (parts.length >= 3 && /^\d+$/.test(parts[2])) {
    id = parts[2];
  } else {
    basePath = "/" + parts.join("/");
  }

  // حذف trailing slash
  basePath = basePath.replace(/\/$/, "") || "/";

  const Component = routeMap[basePath];

  if (!Component) {
    return (
      <Shell>
        <div className="p-8 text-center">
          <h1 className="text-2xl font-bold text-red-500">صفحه‌ی مورد نظر یافت نشد</h1>
          <p className="text-muted mt-2">مسیر: {pathname}</p>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <Component id={id} />
    </Shell>
  );
}