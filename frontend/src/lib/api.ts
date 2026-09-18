const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v2";

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

export function put<T>(path: string, body: unknown) {
  return request<T>(path, { method: "PUT", body: JSON.stringify(body) });
}

export function patch<T>(path: string, body: unknown) {
  return request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
}

export function del<T>(path: string) {
  return request<T>(path, { method: "DELETE" });
}

// ============================================================
// Paginated Response
// ============================================================
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ============================================================
// Finance Category (با فیلد slug جدید)
// ============================================================
export interface FinanceCategory {
  id: number;
  name: string;
  slug: string; // ← جدید
  category_type: "income" | "expense";
  description?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// ============================================================
// Balance Report (فیلدها تغییر نام داده‌اند)
// ============================================================
export interface BalanceReport {
  total_income_period: number;          // ← تغییر نام
  total_expense_period: number;         // ← تغییر نام
  final_balance_cumulative: number;     // ← تغییر نام
  total_employee_cost_period: number;   // ← تغییر نام
  total_equipment_cost_period: number;  // ← تغییر نام
  total_medicine_cost_period: number;   // ← تغییر نام
  center_commission_income_period: number; // ← تغییر نام
  university_commission_period?: number; // جدید
  anesthesia_cost_period?: number;      // جدید
  daily_supplies_cost_period?: number;  // جدید
}

// ============================================================
// Finance Trend (با cumulative_balance)
// ============================================================
export interface FinanceTrend {
  month: string;
  income: number;
  expense: number;
  cumulative_balance: number; // ← جدید
}

// ============================================================
// Product
// ============================================================
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
  stock_status: string;
  is_active: boolean;
  category_name?: string | null; // جدید (برای لیست)
}

export interface ProductDetail {
  id: number;
  name: string;
  internal_code: string;
  product_type: "medicine" | "equipment";
  product_type_display: string;
  category?: number | null;
  category_detail?: {
    id: number;
    name: string;
    full_path: string;
    parent: number | null;
  } | null;
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

// ============================================================
// Vendor
// ============================================================
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

// ============================================================
// Purchase
// ============================================================
export interface Purchase {
  id: number;
  vendor_name: string;
  purchase_date: string;
  total_amount: string;
  status: string;
  status_display: string;
  reference_number?: string;
  stock_applied: boolean;
}

// ============================================================
// Employee
// ============================================================
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

export interface EmployeeDetail {
  id: number;
  full_name: string;
  national_id: string;
  gender: string;
  gender_display: string;
  job_position: number;
  job_position_name: string;
  start_date: string;
  is_active: boolean;
  email: string;
  personal_phone: string;
  emergency_contact_phone: string;
  address?: string;
  description?: string;
  legacy_hourly_rate?: string | null;
  current_hourly_rate?: string | null;
  current_hourly_rate_start_date?: string | null;
  current_hourly_rate_end_date?: string | null;
  future_hourly_rate?: string | null;
  future_hourly_rate_start_date?: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobPosition {
  id: number;
  name: string;
  description?: string;
  is_active: boolean;
}

// ============================================================
// Payroll
// ============================================================
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

// گزارش حقوق و دستمزد (با فیلدهای ساعتی جدید)
export interface PayrollReportEmployee {
  employee_id: number;
  employee_name: string;
  job_position: string;
  fixed_salary: string;
  surgery_commission: string;
  purchase_commission?: string;
  total_commission: string;
  has_commission: boolean;
  hourly_salary: string;        // ← جدید
  total_hours_worked: string;   // ← جدید
  total_payment: string;
}

export interface PayrollReport {
  start_date?: string;
  end_date?: string;
  total_fixed_salary: string;
  total_commission: string;
  total_hourly_salary: string;  // ← جدید
  total_hours_worked: string;   // ← جدید
  total_labor_cost: string;
  employee_count: number;
  employees: PayrollReportEmployee[];
}

// ============================================================
// Surgery
// ============================================================
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
  internal_code?: string | null;
  phone_number: string;
  national_id?: string;
  age?: number | null;
  gender?: string | null;
}

// SurgeryHistory (با فیلدهای جدید)
export interface SurgeryHistory {
  id: number;
  patient_name: string;
  patient_national_id?: string;
  patient_age?: number | null;
  patient_gender?: string | null;
  patient_gender_display?: string | null;
  case_code: string;
  medical_record_code?: string;
  phone_number: string;
  surgery_type_name: string;
  doctor_name?: string;
  surgery_date: string;
  amount: string;
  university_share?: string;
  doctor_share?: string;
  payment_status: string;
  payment_status_display: string;
  status: string;
  status_display: string;
  center_commission_income_amount?: string | null;
  description?: string;
  created_at: string;
}

// SurgeryProfitReport
export interface SurgeryProfitReportSummary {
  start_date?: string | null;
  end_date?: string | null;
  group_by: string;
  surgery_type_id?: number | null;
  doctor_id?: number | null;
  patient_id?: number | null;
  status?: string | null;
  payment_status?: string | null;
  total_surgeries: number;
  total_center_income: string;
  total_consumed_items_cost: string;
  total_employee_commission_cost: string;
  total_approximate_profit: string;
  average_profit_per_surgery?: string | null;
  profitable_surgeries_count: number;
  loss_surgeries_count: number;
  missing_cost_items_count: number; // ← جدید
}

export interface SurgeryProfitReportRow {
  surgery_id?: number | null;
  patient_name?: string | null;
  case_code?: string | null;
  phone_number?: string | null;
  doctor_name?: string | null;
  surgery_type_name?: string | null;
  surgery_date?: string | null;
  surgery_amount?: string | null;
  payment_status?: string | null;
  surgery_status?: string | null;
  center_income?: string | null;
  consumed_items_cost?: string | null;
  employee_commission_cost?: string | null;
  approximate_profit?: string | null;
  profit_margin_percent?: string | null;
  used_items_count?: number | null;
  commission_transactions_count?: number | null;
  has_missing_cost_data: boolean; // ← جدید
  // group_by=surgery_type/doctor fields
  surgeries_count?: number | null;
  average_profit_per_surgery?: string | null;
  average_profit_margin_percent?: string | null;
  surgery_type_id?: number | null;
  doctor_id?: number | null;
  total_center_income?: string | null;
  total_consumed_items_cost?: string | null;
  total_employee_commission_cost?: string | null;
  total_approximate_profit?: string | null;
}

// ============================================================
// Transaction (با وضعیت پرداخت)
// ============================================================
export interface Transaction {
  id: number;
  transaction_type: "income" | "expense";
  transaction_type_display: string;
  category?: number | null;
  category_name?: string;
  amount: string;
  transaction_date: string;
  description?: string;
  payment_status: "pending" | "partial" | "paid" | "cancelled"; // ← جدید
  payment_status_display?: string;
  content_type?: number | null;
  object_id?: number | null;
  created_at: string;
  updated_at: string;
}

// ============================================================
// CommissionTransaction
// ============================================================
export interface CommissionTransaction {
  id: number;
  surgery: number;
  employee: number;
  employee_name: string;
  job_position_name: string;
  commission_rule: number;
  surgery_type_name: string;
  commission_percent: string;
  amount: string;
  notes?: string;
  created_at: string;
}

// ============================================================
// Purchase Commission (EmployeePurchaseCommission)
// ============================================================
export interface EmployeePurchaseCommission {
  id: number;
  employee: number;
  employee_name: string;
  purchase?: number | null;
  purchase_ref?: string | null;
  purchase_date?: string | null;
  purchase_amount?: string | null;
  vendor_name?: string | null;
  amount: string;
  commission_date: string;
  description?: string;
  created_at: string;
  updated_at: string;
}

// ============================================================
// Hourly Work Entry
// ============================================================
export interface HourlyWorkEntry {
  id: number;
  employee: number;
  employee_name: string;
  work_date: string;
  hours_worked: string;
  rate_used?: string | null;
  amount?: string | null;
  payroll_period?: number | null;
  is_processed: boolean;
  description?: string;
  created_at: string;
  updated_at: string;
}

// ============================================================
// Inventory Stock Report
// ============================================================
export interface InventoryStockReportSummary {
  total_products: number;
  low_stock_count: number;
  out_of_stock_count: number;
  total_inventory_value: string;
}

export interface InventoryStockProduct {
  id: number;
  name: string;
  internal_code: string;
  product_type: string;
  category?: number | null;
  category_name?: string | null;
  unit?: string;
  purchase_price: string;
  current_stock: string;
  minimum_stock: string;
  is_low_stock: boolean;
  is_out_of_stock: boolean;
  inventory_value: string;
  is_active: boolean;
}

// ============================================================
// Surgery Used Item
// ============================================================
export interface SurgeryUsedItem {
  id: number;
  surgery: number;
  product: number;
  product_name: string;
  product_code: string;
  quantity: string;
  unit: string;
  description?: string;
  current_stock?: string;
  created_at: string;
  updated_at: string;
}

// ============================================================
// Surgery Consumption Item (legacy)
// ============================================================
export interface SurgeryConsumptionItem {
  id: number;
  surgery: number;
  product: number;
  product_name: string;
  product_code: string;
  quantity: string;
  unit: string;
  notes?: string;
  created_at: string;
  updated_at: string;
}

// ============================================================
// Stock Movement
// ============================================================
export interface StockMovement {
  id: number;
  product: number;
  product_name: string;
  product_code: string;
  quantity: string;
  unit: string;
  movement_type: "IN" | "OUT" | "ADJUSTMENT";
  movement_type_display: string;
  source_type: string;
  source_type_display: string;
  reference_id?: string;
  movement_date: string;
  description?: string;
  created_at: string;
  updated_at: string;
}

// ============================================================
// Payroll Type Config
// ============================================================
export interface PayrollTypeConfig {
  id: number;
  employee: number;
  employee_name: string;
  has_monthly_wage: boolean;
  has_commission: boolean;
  has_hourly_wage: boolean;
  notes?: string;
  updated_at: string;
}

// ============================================================
// Employee Cost Report (CLI-52)
// ============================================================
export interface EmployeeCostReportSummary {
  start_date?: string | null;
  end_date?: string | null;
  wage_type: string;
  employee_id?: number | null;
  position_id?: number | null;
  total_fixed_wages: string;
  total_commissions: string;
  total_hourly_wages: string;
  total_hours_worked: string;
  total_payments: string;
  employee_count: number;
}

export interface EmployeeCostReportRow {
  employee_id: number;
  employee_name: string;
  position_name: string;
  total_fixed_wages: string;
  total_commissions: string;
  total_hourly_wages: string;
  total_hours_worked: string;
  total_payments: string;
}

// ============================================================
// Product Cost Report
// ============================================================
export interface ProductCostReportSummary {
  start_date?: string | null;
  end_date?: string | null;
  product_type: string;
  group_by: string;
  vendor_id?: number | null;
  total_cost: string;
  total_quantity: string;
  total_line_items: number;
}

export interface ProductCostReportRow {
  product_id?: number | null;
  product_name?: string | null;
  product_code?: string | null;
  product_type?: string | null;
  vendor_id?: number | null;
  vendor_name?: string | null;
  total_quantity: string;
  total_cost: string;
  avg_unit_price: string;
  purchase_count: number;
}