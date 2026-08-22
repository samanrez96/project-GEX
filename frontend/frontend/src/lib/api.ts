const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

export function get<T>(path: string) {
  return request<T>(path);
}

export function post<T>(path: string, body: unknown) {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export function patch<T>(path: string, body: unknown) {
  return request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
}

export function del<T>(path: string) {
  return request<T>(path, { method: "DELETE" });
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface BalanceReport {
  total_income: number;
  total_expense: number;
  final_balance: number;
  total_employee_cost: number;
  total_equipment_cost: number;
  total_medicine_cost: number;
  center_commission_income: number;
}

// Product (matches ProductListSerializer)
export interface Product {
  id: number;
  name: string;
  internal_code: string;
  product_type: "medicine" | "equipment";
  product_type_display: string;
  current_stock: string;
  minimum_stock: string;
  purchase_price: string;
  is_low_stock: boolean;
  is_out_of_stock: boolean;
  stock_status: string; // موجود / کم‌موجودی / ناموجود
  is_active: boolean;
}

// Product detail (matches ProductSerializer)
export interface ProductDetail {
  id: number;
  name: string;
  internal_code: string;
  product_type: "medicine" | "equipment";
  product_type_display: string;
  category?: number | null;
  unit?: string;
  purchase_price: string;
  sale_price?: string;
  current_stock: string;
  minimum_stock: string;
  internal_notes?: string;
  is_active: boolean;
  is_low_stock: boolean;
  is_out_of_stock: boolean;
  stock_status: string;
  created_at: string;
  updated_at: string;
}

export interface Vendor {
  id: number;
  name: string;
  phone_number: string;
  email?: string;
  address?: string;
  notes?: string;
  is_active: boolean;
  current_balance: string;
  opening_balance?: string;
  tax_id?: string;
  bank_account?: string;
  created_at?: string;
}

export interface ProductVendorLink {
  id: number;
  product: number;
  product_name: string;
  vendor: number;
  vendor_name: string;
  unit_price: string;
  is_primary: boolean;
  is_active: boolean;
  supplier_product_code?: string;
  notes?: string;
}

export interface Purchase {
  id: number;
  vendor_name: string;
  date: string;
  total_amount: number;
  status: string;
  status_display: string;
}

// Employee (matches EmployeeListSerializer)
export interface Employee {
  id: number;
  full_name: string;
  national_id: string;
  job_position: number | null;
  job_position_name: string;
  gender: string;
  gender_display?: string;
  personal_phone: string;
  email: string;
  is_active: boolean;
  start_date: string;
}

export interface JobPosition {
  id: number;
  name: string;
  is_active: boolean;
}

// PayrollPeriod (matches PayrollPeriodSerializer)
export interface PayrollPeriod {
  id: number;
  year: number;
  month: number;
  status: "OPEN" | "CLOSED" | "PROCESSED";
  display_name: string;
  notes?: string;
}

export interface MonthlyWage {
  id: number;
  employee: number;
  employee_name: string;
  amount: string;
  start_date: string;
  end_date?: string | null;
  is_active: boolean;
  notes?: string;
}

export interface CommissionRule {
  id: number;
  job_position: number;
  job_position_name: string;
  surgery_type: number;
  surgery_type_name: string;
  commission_percent: string;
  start_date: string;
  is_active: boolean;
  notes?: string;
}

export interface PayrollReportEmployee {
  employee_id: number;
  employee_name: string;
  job_position: string;
  fixed_salary: string;
  total_commission: string;
  total_payment: string;
}

export interface PayrollReport {
  start_date?: string;
  end_date?: string;
  total_fixed_salary: string;
  total_commission: string;
  total_labor_cost: string;
  employee_count: number;
  employees: PayrollReportEmployee[];
}

export interface SurgeryType {
  id: number;
  name: string;
  code: string;
  base_rate: string;
  is_active: boolean;
}

export interface Doctor {
  id: number;
  full_name: string;
  specialty: number;
  specialty_name: string;
  phone_number: string;
  email?: string;
  national_id?: string;
  medical_system_number?: string;
  clinic_phone?: string;
  collaboration_start_date?: string | null;
  license_last_renewal_date?: string | null;
  is_active: boolean;
}

export interface Patient {
  id: number;
  full_name: string;
  case_code: string;
  phone_number: string;
}

// SurgeryHistory (matches SurgeryHistoryListSerializer)
export interface SurgeryHistory {
  id: number;
  patient_name: string;
  case_code: string;
  medical_record_code?: string;
  surgery_type_name: string;
  doctor_name?: string;
  surgery_date: string;
  amount: string;
  payment_status: string;
  payment_status_display: string;
  status: string;
  status_display: string;
}

export interface FinanceTrend {
  month: string;
  income: number;
  expense: number;
}

export interface Transaction {
  id: number;
  date: string;
  category: string;
  category_display: string;
  description: string;
  amount: number;
  type: string;
  type_display: string;
}
