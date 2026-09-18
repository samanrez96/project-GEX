const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v2";

// ============================================================
// Token storage
// ============================================================
const ACCESS_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh?: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACCESS_KEY, access);
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

// ============================================================
// Error type that carries the backend response
// ============================================================
export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown, message?: string) {
    super(message || `API ${status}`);
    this.status = status;
    this.body = body;
  }
}

// ============================================================
// Refresh coordination — avoid parallel refresh storms
// ============================================================
let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  if (refreshPromise) return refreshPromise;
  const refresh = getRefreshToken();
  if (!refresh) throw new ApiError(401, null, "No refresh token");

  refreshPromise = (async () => {
    const res = await fetch(`${API_BASE}/auth/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    if (!res.ok) {
      clearTokens();
      throw new ApiError(res.status, null, "Refresh failed");
    }
    const data = (await res.json()) as { access: string };
    setTokens(data.access);
    return data.access;
  })();

  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

// ============================================================
// Core request
// ============================================================
interface RequestOptions extends RequestInit {
  /** Skip attaching Authorization header (used by login/refresh) */
  skipAuth?: boolean;
  /** Do not attempt auto-refresh on 401 (used by login) */
  skipRefresh?: boolean;
  /** Parse as blob instead of JSON (Excel exports) */
  asBlob?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { skipAuth, skipRefresh, asBlob, ...fetchOptions } = options;

  const headers = new Headers(fetchOptions.headers);
  if (!headers.has("Content-Type") && !asBlob && fetchOptions.body) {
    headers.set("Content-Type", "application/json");
  }
  if (!skipAuth) {
    const token = getAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  let res = await fetch(`${API_BASE}${path}`, {
    ...fetchOptions,
    headers,
    credentials: "include",
  });

  // Auto-refresh on 401
  if (res.status === 401 && !skipRefresh && !skipAuth) {
    try {
      const newToken = await refreshAccessToken();
      headers.set("Authorization", `Bearer ${newToken}`);
      res = await fetch(`${API_BASE}${path}`, {
        ...fetchOptions,
        headers,
        credentials: "include",
      });
    } catch {
      clearTokens();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
      throw new ApiError(401, null, "Unauthorized");
    }
  }

  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, body, `API ${res.status}: ${path}`);
  }

  if (asBlob) return (await res.blob()) as unknown as T;

  // 204 No Content
  if (res.status === 204) return undefined as unknown as T;

  return (await res.json()) as T;
}

// ============================================================
// HTTP verbs
// ============================================================
export function get<T>(path: string, options?: RequestOptions) {
  return request<T>(path, { ...options, method: "GET" });
}

export function post<T>(path: string, body?: unknown, options?: RequestOptions) {
  return request<T>(path, {
    ...options,
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function put<T>(path: string, body: unknown, options?: RequestOptions) {
  return request<T>(path, { ...options, method: "PUT", body: JSON.stringify(body) });
}

export function patch<T>(path: string, body: unknown, options?: RequestOptions) {
  return request<T>(path, { ...options, method: "PATCH", body: JSON.stringify(body) });
}

export function del<T>(path: string, options?: RequestOptions) {
  return request<T>(path, { ...options, method: "DELETE" });
}

/** Excel/binary downloads — returns a Blob. */
export function download(path: string) {
  return request<Blob>(path, { asBlob: true });
}

// ============================================================
// Auth helpers
// ============================================================
export interface AuthUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_staff: boolean;
  is_superuser: boolean;
  roles: string[];
}

export interface TokenPair {
  access: string;
  refresh: string;
}

export async function login(username: string, password: string): Promise<TokenPair> {
  const tokens = await post<TokenPair>(
    "/auth/login/",
    { username, password },
    { skipAuth: true, skipRefresh: true }
  );
  setTokens(tokens.access, tokens.refresh);
  return tokens;
}

export async function logout(): Promise<void> {
  const refresh = getRefreshToken();
  try {
    if (refresh) {
      await post("/auth/logout/", { refresh });
    }
  } catch {
    /* ignore — we're logging out regardless */
  } finally {
    clearTokens();
    if (typeof window !== "undefined") window.location.href = "/login";
  }
}

export function me() {
  return get<AuthUser>("/auth/me/");
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
// Finance
// ============================================================
export interface FinanceCategory {
  id: number;
  name: string;
  slug: string;
  category_type: "income" | "expense";
  description?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface BalanceReport {
  total_income_period: number;
  total_expense_period: number;
  final_balance_cumulative: number;
  total_employee_cost_period: number;
  total_equipment_cost_period: number;
  total_medicine_cost_period: number;
  center_commission_income_period: number;
  university_commission_period?: number;
  anesthesia_cost_period?: number;
  daily_supplies_cost_period?: number;
}

export interface FinanceTrend {
  month: string;
  income: number;
  expense: number;
  cumulative_balance: number;
}

export interface TransactionCategoryRef {
  id: number;
  name: string;
  slug: string;
  category_type: "income" | "expense";
}

export interface Transaction {
  id: number;
  transaction_type: "income" | "expense";
  transaction_type_display?: string;
  category?: number | TransactionCategoryRef | null;
  amount: string;
  transaction_date: string;
  description?: string;
  payment_status: "pending" | "partial" | "paid" | "cancelled";
  payment_status_display?: string;
  content_type?: number | null;
  object_id?: number | null;
  created_at: string;
  updated_at: string;
}

export function getTransactionCategoryName(t: Transaction): string {
  if (t.category == null) return "—";
  if (typeof t.category === "number") return String(t.category);
  return t.category.name || "—";
}

// ============================================================
// Inventory
// ============================================================
export interface Product {
  id: number;
  name: string;
  internal_code: string;
  product_type: "medicine" | "equipment";
  product_type_display: string;
  category?: number | null;
  category_name?: string | null;
  current_stock: string;
  minimum_stock: string;
  purchase_price: string;
  is_low_stock: boolean;
  is_out_of_stock: boolean;
  stock_status: string;
  is_active: boolean;
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
  barcode?: string | null;
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
  updated_at?: string;
  phones?: string[];
}

export interface ProductVendorLink {
  id: number;
  product: number;
  product_name: string;
  product_code?: string;
  vendor: number;
  vendor_name: string;
  supplier_product_code?: string;
  unit_price: string;
  currency?: string;
  is_primary: boolean;
  is_active: boolean;
  total_purchased_quantity?: string;
  latest_purchase_date?: string | null;
}

export interface Purchase {
  id: number;
  vendor: number;
  vendor_name: string;
  reference_number?: string;
  purchase_date: string;
  status: "PENDING" | "CONFIRMED" | "CANCELLED" | string;
  status_display: string;
  stock_applied: boolean;
  item_count?: number;
  average_unit_price?: string;
  total_amount: string;
  product_names_display?: string;
  created_at: string;
}

export interface PurchaseItem {
  id: number;
  purchase: number;
  product: number;
  product_name: string;
  product_code: string;
  quantity: string;
  unit: string;
  unit_price: string;
  notes?: string;
  created_at: string;
  updated_at: string;
}

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

export interface InventoryStockReportSummary {
  total_products: number;
  low_stock_count: number;
  out_of_stock_count: number;
  total_inventory_value: string;
}

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

// ============================================================
// Employees
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

export interface EmployeePurchaseCommission {
  id: number;
  employee: number;
  employee_name: string;
  purchase?: number | null;
  purchase_pk?: number | null;
  purchase_ref?: string | null;
  purchase_date?: string | null;
  purchase_amount?: string | null;
  items_summary?: string | null;
  vendor_name?: string | null;
  amount: string;
  commission_date: string;
  description?: string;
  created_at: string;
  updated_at: string;
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

export interface PayrollReportEmployee {
  employee_id: number;
  employee_name: string;
  job_position: string;
  fixed_salary: string;
  surgery_commission: string;
  purchase_commission?: string;
  total_commission: string;
  has_commission: boolean;
  hourly_salary: string;
  total_hours_worked: string;
  total_payment: string;
}

export interface PayrollReport {
  start_date?: string;
  end_date?: string;
  total_fixed_salary: string;
  total_commission: string;
  total_hourly_salary: string;
  total_hours_worked: string;
  total_labor_cost: string;
  employee_count: number;
  employees: PayrollReportEmployee[];
}

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
// Surgeries
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
  gender_display?: string | null;
  is_hidden?: boolean;
  created_at?: string;
}

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
  missing_cost_items_count: number;
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
  has_missing_cost_data: boolean;
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