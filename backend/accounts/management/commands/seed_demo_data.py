"""
Seed demo data for the Surgery Clinic management system.

Usage:
    python manage.py seed_demo_data              # normal run (idempotent)
    python manage.py seed_demo_data --quiet      # suppress per-record messages
    python manage.py seed_demo_data --force      # allow running when DEBUG=False
    python manage.py seed_demo_data --reset      # wipe demo data then re-seed

All demo records carry a stable DEMO- prefix or description marker so they
can be identified without touching real user data.

Side effects triggered via existing services:
  - Purchase.confirm()       → IN StockMovements + finance expense Transactions
  - SurgeryHistory save      → CommissionTransaction (via signal)
  - SurgeryFinanceService    → CenterCommissionIncome + income Transaction
  - SurgeryInventoryService  → OUT StockMovement per used item
  - PayrollPeriod.close()   → salary finance expense Transactions
"""

import datetime
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

_DEMO = "DEMO"
_MARKER = "داده نمونه سیستم"


# ---------------------------------------------------------------------------
# Static data tables
# ---------------------------------------------------------------------------

_VENDORS = [
    {"name": "DEMO تامین طب آریا",            "phone_number": "02188001000", "email": "arya@demo.local",    "address": "تهران، ولیعصر، پلاک ۱۲۰"},
    {"name": "DEMO تجهیزات پزشکی پارس",       "phone_number": "02188002000", "email": "pars@demo.local",    "address": "تهران، شریعتی، پلاک ۲۴۰"},
    {"name": "DEMO دارو گستر سلامت",           "phone_number": "02188003000", "email": "salamat@demo.local", "address": "تهران، آزادی، پلاک ۵۵"},
    {"name": "DEMO داروپخش مهرگان",            "phone_number": "02155001000", "email": "mehrgan@demo.local", "address": "تهران، مطهری، پلاک ۸۸"},
    {"name": "DEMO تجهیزات استریل نوین",       "phone_number": "02166001000", "email": "novin@demo.local",   "address": "تهران، کریمخان، پلاک ۳۳"},
    {"name": "DEMO شرکت پزشکی سینا",           "phone_number": "02177001000", "email": "sina@demo.local",    "address": "تهران، انقلاب، پلاک ۶۷"},
]

_POSITIONS = [
    "متخصص بیهوشی", "پرستار", "تکنسین اتاق عمل",
    "منشی", "حسابدار", "مسئول انبار", "خدمات", "اپراتور لیزر",
]

_EMPLOYEES = [
    # (national_id, full_name, gender, position, phone, emerg_phone, start)
    ("DEMO-EMP-001", "دکتر علی رضایی",     "male",   "متخصص بیهوشی",   "09120000001", "09120000011", datetime.date(2020, 1,  1)),
    ("DEMO-EMP-002", "مریم احمدی",          "female", "پرستار",           "09120000002", "09120000012", datetime.date(2021, 3,  1)),
    ("DEMO-EMP-003", "رضا کریمی",           "male",   "تکنسین اتاق عمل","09120000003", "09120000013", datetime.date(2022, 6,  1)),
    ("DEMO-EMP-004", "فاطمه محمودی",        "female", "منشی",             "09120000004", "09120000014", datetime.date(2019, 9,  1)),
    ("DEMO-EMP-005", "حسن نظری",            "male",   "حسابدار",          "09120000005", "09120000015", datetime.date(2023, 1, 15)),
    ("DEMO-EMP-006", "زهرا موسوی",          "female", "پرستار",           "09120000006", "09120000016", datetime.date(2021, 9,  1)),
    ("DEMO-EMP-007", "امیر صادقی",          "male",   "مسئول انبار",      "09120000007", "09120000017", datetime.date(2020, 5,  1)),
    ("DEMO-EMP-008", "نیلوفر حیدری",        "female", "خدمات",            "09120000008", "09120000018", datetime.date(2022, 2,  1)),
    ("DEMO-EMP-009", "کامران فروزان",       "male",   "اپراتور لیزر",    "09120000009", "09120000019", datetime.date(2021, 7,  1)),
    ("DEMO-EMP-010", "سمیه قاسمی",          "female", "پرستار",           "09120000010", "09120000020", datetime.date(2023, 4,  1)),
    ("DEMO-EMP-011", "مهدی جعفری",          "male",   "تکنسین اتاق عمل","09120000021", "09120000031", datetime.date(2020, 8,  1)),
    ("DEMO-EMP-012", "لیلا ناصری",          "female", "منشی",             "09120000022", "09120000032", datetime.date(2022, 11, 1)),
]

_WAGES = {
    "منشی":             Decimal("180000000"),
    "حسابدار":          Decimal("220000000"),
    "مسئول انبار":      Decimal("200000000"),
    "خدمات":            Decimal("140000000"),
    "پرستار":           Decimal("250000000"),
    "اپراتور لیزر":     Decimal("230000000"),
    "متخصص بیهوشی":    Decimal("450000000"),
    "تکنسین اتاق عمل": Decimal("190000000"),
}

_SURGERY_TYPES = [
    ("DEMO-RHIN", "جراحی بینی (رینوپلاستی)", Decimal("15000000")),
    ("DEMO-LIPO", "لیپوماتیک",               Decimal("20000000")),
    ("DEMO-LIFT", "لیفت صورت",               Decimal("25000000")),
    ("DEMO-BLEP", "بلفاروپلاستی (جراحی پلک)",Decimal("12000000")),
    ("DEMO-FESS", "FESS / جراحی سینوس",      Decimal("11000000")),
    ("DEMO-SEPT", "سپتوپلاستی",              Decimal("10000000")),
    ("DEMO-MAST", "ماستوپکسی",               Decimal("18000000")),
    ("DEMO-BRTM", "توده پستان",              Decimal("14000000")),
    ("DEMO-FATG", "تزریق چربی",              Decimal("10000000")),
    ("DEMO-MOLE", "برداشت خال / ضایعه پوستی",Decimal("9000000")),
]

_COMMISSION_RULES = [
    ("متخصص بیهوشی",   "DEMO-RHIN", Decimal("15")),
    ("متخصص بیهوشی",   "DEMO-LIPO", Decimal("15")),
    ("متخصص بیهوشی",   "DEMO-LIFT", Decimal("12")),
    ("متخصص بیهوشی",   "DEMO-BLEP", Decimal("15")),
    ("متخصص بیهوشی",   "DEMO-FESS", Decimal("12")),
    ("متخصص بیهوشی",   "DEMO-SEPT", Decimal("12")),
    ("متخصص بیهوشی",   "DEMO-MAST", Decimal("15")),
    ("متخصص بیهوشی",   "DEMO-BRTM", Decimal("15")),
    ("متخصص بیهوشی",   "DEMO-FATG", Decimal("12")),
    ("متخصص بیهوشی",   "DEMO-MOLE", Decimal("12")),
    ("پرستار",          "DEMO-RHIN", Decimal("5")),
    ("پرستار",          "DEMO-LIPO", Decimal("5")),
    ("پرستار",          "DEMO-LIFT", Decimal("4")),
    ("پرستار",          "DEMO-BLEP", Decimal("4")),
    ("تکنسین اتاق عمل","DEMO-RHIN", Decimal("3")),
    ("تکنسین اتاق عمل","DEMO-LIPO", Decimal("3")),
    ("تکنسین اتاق عمل","DEMO-LIFT", Decimal("3")),
    ("تکنسین اتاق عمل","DEMO-BLEP", Decimal("3")),
]

_DOCTORS = [
    ("DEMO-DR-001", "دکتر مصطفی رضوانی",  "02122001001", "گوش و حلق و بینی", Decimal("3000000")),
    ("DEMO-DR-002", "دکتر ناهید احمدی",   "02122001002", "پوست و زیبایی",    Decimal("3500000")),
    ("DEMO-DR-003", "دکتر آرمان کریمی",   "02122001003", "جراحی عمومی",      Decimal("4000000")),
    ("DEMO-DR-004", "دکتر سارا یوسفی",    "02122001004", "زنان",             Decimal("3200000")),
    ("DEMO-DR-005", "دکتر امیر طباطبایی", "02122001005", "پلاستیک",          Decimal("5000000")),
    ("DEMO-DR-006", "دکتر مریم رستمی",    "02122001006", "گوش و حلق و بینی", Decimal("3000000")),
    ("DEMO-DR-007", "دکتر کامران نوری",   "02122001007", "جراحی پستان",      Decimal("4500000")),
    ("DEMO-DR-008", "دکتر الهام صادقی",   "02122001008", "زیبایی",           Decimal("3800000")),
]

_PATIENT_FIRST = [
    "فاطمه","زینب","مریم","سارا","نگار","رویا","ندا","شیرین","پریسا","نازنین",
    "محمد","علی","حسین","رضا","امیر","مهدی","سعید","کیان","آرمان","بهرام",
    "لیلا","سمیه","آزاده","مینا","صبا","الهام","شهلا","گلنار","بهناز","هانیه",
    "داوود","بابک","کاوه","سیامک","آرش","نوید","پوریا","شاهین","مانی","فرید",
]
_PATIENT_LAST = [
    "محمدی","احمدی","حسینی","رضایی","کریمی","موسوی","صادقی","جعفری",
    "نظری","قاسمی","ناصری","مرادی","فروزان","طاهری","اکبری","شریفی",
    "رحیمی","یوسفی","سلطانی","امیری","خانی","مومنی","حسن‌زاده","دولتی",
]

_AMOUNTS = [
    Decimal("9000000"),  Decimal("10000000"), Decimal("11000000"),
    Decimal("12000000"), Decimal("13000000"), Decimal("15000000"),
    Decimal("18000000"), Decimal("20000000"), Decimal("22000000"),
    Decimal("25000000"),
]
_PAY_STATUSES = ["PENDING", "PARTIAL", "PAID"]
_SURG_STATUSES = ["PLANNED", "IN_PROGRESS", "COMPLETED", "COMPLETED", "COMPLETED"]

_CONSUMABLES = [
    "DEMO-MED-001", "DEMO-MED-002", "DEMO-MED-003", "DEMO-MED-004", "DEMO-MED-005",
    "DEMO-EQP-001", "DEMO-EQP-002", "DEMO-EQP-003", "DEMO-EQP-004", "DEMO-EQP-005",
]


class Command(BaseCommand):
    help = "Seed realistic Persian demo data for the surgery clinic admin panel."

    def add_arguments(self, parser):
        parser.add_argument("--force",  action="store_true", help="Allow running in production (DEBUG=False).")
        parser.add_argument("--quiet",  action="store_true", help="Suppress per-record messages.")
        parser.add_argument("--reset",  action="store_true", help="Delete demo records then re-seed.")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Refusing to seed in production. Pass --force to override.")
        self.quiet  = options["quiet"]
        self.stats  = {}

        if options["reset"]:
            self._log(self.style.WARNING("حذف داده‌های نمونه قبلی..."))
            self._reset()

        self._log(self.style.MIGRATE_HEADING(">> ایجاد داده‌های نمونه..."))

        with transaction.atomic():
            vendors       = self._seed_vendors()
            products      = self._seed_products()
            self._seed_product_vendors(products, vendors)
            positions     = self._seed_positions()
            employees     = self._seed_employees(positions)
            self._seed_wages(employees)
            surg_types    = self._seed_surgery_types()
            self._seed_commission_rules(positions, surg_types)
            doctors       = self._seed_doctors()
            patients      = self._seed_patients()
            self._seed_purchases(vendors, products)
            surgeries     = self._seed_surgeries(patients, surg_types, employees, doctors)
            self._seed_used_items(surgeries, products)
            self._seed_purchase_commissions(employees)
            self._seed_payroll_period()
            self._seed_manual_finance()

        self._print_summary()

    # ------------------------------------------------------------------ utils

    def _log(self, msg):
        if self.quiet:
            return
        try:
            self.stdout.write(msg)
        except UnicodeEncodeError:
            self.stdout.write(msg.encode(self.stdout.encoding or "utf-8", errors="replace")
                                 .decode(self.stdout.encoding or "utf-8"))

    def _track(self, key, created):
        s = self.stats.setdefault(key, {"c": 0, "e": 0})
        if created:
            s["c"] += 1
        else:
            s["e"] += 1

    # ------------------------------------------------------------------ reset

    def _reset(self):
        from inventory.models import Purchase, PurchaseItem, Product, ProductVendor, StockMovement
        from surgeries.models import SurgeryHistory, SurgeryUsedItem, Patient, SurgeryType
        from employees.models import Employee, EmployeePurchaseCommission
        from payroll.models import CommissionRule, MonthlyWage
        from contacts.models import Doctor

        EmployeePurchaseCommission.objects.filter(description__startswith=f"[{_DEMO}]").delete()
        demo_sh = SurgeryHistory.objects.filter(description__icontains="[DEMO-S")
        SurgeryUsedItem.objects.filter(surgery__in=demo_sh).delete()
        demo_sh.delete()
        Patient.objects.filter(case_code__startswith="DEMO-CASE-").delete()
        CommissionRule.objects.filter(notes__contains=_MARKER).delete()
        MonthlyWage.objects.filter(notes__contains=_MARKER).update(is_active=False)
        demo_pur = Purchase.objects.filter(reference_number__startswith="DEMO-INV-")
        PurchaseItem.objects.filter(purchase__in=demo_pur).delete()
        demo_pur.delete()
        demo_prod = Product.objects.filter(internal_code__startswith="DEMO-")
        StockMovement.objects.filter(product__in=demo_prod).delete()
        ProductVendor.objects.filter(product__in=demo_prod).delete()
        Employee.objects.filter(national_id__startswith="DEMO-EMP-").delete()
        Doctor.objects.filter(phone_number__startswith="0212200").delete()
        demo_prod.delete()
        SurgeryType.objects.filter(code__startswith="DEMO-").delete()
        self._log("  ✓ داده‌های نمونه قبلی پاک شدند")

    # ------------------------------------------------------------------ vendors

    def _seed_vendors(self):
        from inventory.models import Vendor
        vendors = []
        for d in _VENDORS:
            name = d["name"]
            v = Vendor.objects.filter(name=name).first()
            if v is None:
                v = Vendor.objects.create(**d)
                self._log(f"  [+] Vendor: {name}")
                self._track("vendors", True)
            else:
                self._track("vendors", False)
            vendors.append(v)
        return vendors

    # ------------------------------------------------------------------ products

    def _seed_products(self):
        from inventory.models import Product, ProductType, MovementType, SourceType
        from inventory.services import StockService

        core = [
            ("DEMO-MED-001", "پروپوفول",          ProductType.MEDICINE,  "ml",  Decimal("150000"), Decimal("180000"), Decimal("50"),  500),
            ("DEMO-MED-002", "لیدوکائین",          ProductType.MEDICINE,  "ml",  Decimal("80000"),  Decimal("95000"),  Decimal("30"),  300),
            ("DEMO-MED-003", "سفازولین",           ProductType.MEDICINE,  "g",   Decimal("120000"), Decimal("145000"), Decimal("20"),  200),
            ("DEMO-MED-004", "سرم نرمال سالین",    ProductType.MEDICINE,  "لیتر",Decimal("50000"),  Decimal("60000"),  Decimal("100"),1000),
            ("DEMO-MED-005", "ایزوفلوران",         ProductType.MEDICINE,  "ml",  Decimal("200000"), Decimal("240000"), Decimal("10"),  100),
            ("DEMO-EQP-001", "نخ بخیه",            ProductType.EQUIPMENT, "بسته",Decimal("25000"),  Decimal("30000"),  Decimal("50"),  500),
            ("DEMO-EQP-002", "گاز استریل",         ProductType.EQUIPMENT, "بسته",Decimal("15000"),  Decimal("18000"),  Decimal("100"),1000),
            ("DEMO-EQP-003", "دستکش جراحی",        ProductType.EQUIPMENT, "جفت", Decimal("12000"),  Decimal("15000"),  Decimal("200"),2000),
            ("DEMO-EQP-004", "ماسک اکسیژن",        ProductType.EQUIPMENT, "عدد", Decimal("35000"),  Decimal("42000"),  Decimal("30"),  300),
            ("DEMO-EQP-005", "سرنگ ۱۰ سی‌سی",     ProductType.EQUIPMENT, "عدد", Decimal("8000"),   Decimal("10000"),  Decimal("500"),5000),
        ]

        products = {}
        for code, name, ptype, unit, pp, sp, minst, init_stock in core:
            p, created = Product.objects.get_or_create(
                internal_code=code,
                defaults=dict(name=name, product_type=ptype, unit=unit,
                              purchase_price=pp, sale_price=sp, minimum_stock=minst),
            )
            self._log(f"  {'[+]' if created else ' - '} Product: {code}")
            self._track("products", created)
            if created:
                StockService.create_movement(
                    product=p, quantity=Decimal(str(init_stock)),
                    movement_type=MovementType.IN, source_type=SourceType.MANUAL_ADJUSTMENT,
                    reference_id=f"DEMO-INIT-{code}",
                    description=f"موجودی اولیه | {_MARKER}",
                    movement_date=timezone.now() - datetime.timedelta(days=90),
                )
            products[code] = p

        # extra medicines (bulk, idempotent)
        extra = [
            dict(internal_code="DEMO-MED-006",  name="استامینوفن",        unit="قرص",   purchase_price=Decimal("8000"),    sale_price=Decimal("10000"),   minimum_stock=Decimal("200")),
            dict(internal_code="DEMO-MED-007",  name="ایبوپروفن",         unit="قرص",   purchase_price=Decimal("12000"),   sale_price=Decimal("15000"),   minimum_stock=Decimal("150")),
            dict(internal_code="DEMO-MED-008",  name="دیکلوفناک",         unit="آمپول", purchase_price=Decimal("25000"),   sale_price=Decimal("30000"),   minimum_stock=Decimal("50")),
            dict(internal_code="DEMO-MED-009",  name="ناپروکسن",          unit="قرص",   purchase_price=Decimal("15000"),   sale_price=Decimal("18000"),   minimum_stock=Decimal("100")),
            dict(internal_code="DEMO-MED-010",  name="کتورولاک",          unit="آمپول", purchase_price=Decimal("45000"),   sale_price=Decimal("55000"),   minimum_stock=Decimal("30")),
            dict(internal_code="DEMO-MED-011",  name="مورفین",            unit="آمپول", purchase_price=Decimal("180000"),  sale_price=Decimal("215000"),  minimum_stock=Decimal("20")),
            dict(internal_code="DEMO-MED-012",  name="پتیدین",            unit="آمپول", purchase_price=Decimal("150000"),  sale_price=Decimal("180000"),  minimum_stock=Decimal("20")),
            dict(internal_code="DEMO-MED-013",  name="فنتانیل",           unit="آمپول", purchase_price=Decimal("320000"),  sale_price=Decimal("385000"),  minimum_stock=Decimal("10")),
            dict(internal_code="DEMO-MED-014",  name="کتامین",            unit="آمپول", purchase_price=Decimal("280000"),  sale_price=Decimal("335000"),  minimum_stock=Decimal("15")),
            dict(internal_code="DEMO-MED-015",  name="بوپیواکائین",       unit="آمپول", purchase_price=Decimal("95000"),   sale_price=Decimal("115000"),  minimum_stock=Decimal("20")),
            dict(internal_code="DEMO-MED-016",  name="میدازولام",         unit="آمپول", purchase_price=Decimal("95000"),   sale_price=Decimal("115000"),  minimum_stock=Decimal("30")),
            dict(internal_code="DEMO-MED-017",  name="دگزامتازون",        unit="آمپول", purchase_price=Decimal("22000"),   sale_price=Decimal("27000"),   minimum_stock=Decimal("50")),
            dict(internal_code="DEMO-MED-018",  name="آدرنالین",          unit="آمپول", purchase_price=Decimal("45000"),   sale_price=Decimal("54000"),   minimum_stock=Decimal("50")),
            dict(internal_code="DEMO-MED-019",  name="بتادین",            unit="ml",    purchase_price=Decimal("35000"),   sale_price=Decimal("42000"),   minimum_stock=Decimal("50")),
            dict(internal_code="DEMO-MED-020",  name="هپارین",            unit="ویال",  purchase_price=Decimal("220000"),  sale_price=Decimal("264000"),  minimum_stock=Decimal("10")),
            dict(internal_code="DEMO-MED-021",  name="سرم رینگر لاکتات", unit="لیتر",  purchase_price=Decimal("48000"),   sale_price=Decimal("58000"),   minimum_stock=Decimal("100")),
            dict(internal_code="DEMO-MED-022",  name="نالوکسان",          unit="آمپول", purchase_price=Decimal("220000"),  sale_price=Decimal("264000"),  minimum_stock=Decimal("10")),
            dict(internal_code="DEMO-MED-023",  name="متوکلوپرامید",      unit="آمپول", purchase_price=Decimal("20000"),   sale_price=Decimal("24000"),   minimum_stock=Decimal("50")),
            dict(internal_code="DEMO-MED-024",  name="اوندانسترون",       unit="آمپول", purchase_price=Decimal("85000"),   sale_price=Decimal("102000"),  minimum_stock=Decimal("30")),
            dict(internal_code="DEMO-MED-025",  name="آتراکوریوم",        unit="آمپول", purchase_price=Decimal("145000"),  sale_price=Decimal("175000"),  minimum_stock=Decimal("15")),
            dict(internal_code="DEMO-EQP-006",  name="شان استریل",        unit="عدد",   purchase_price=Decimal("95000"),   sale_price=Decimal("115000"),  minimum_stock=Decimal("30")),
            dict(internal_code="DEMO-EQP-007",  name="تیغ بیستوری",       unit="عدد",   purchase_price=Decimal("12000"),   sale_price=Decimal("15000"),   minimum_stock=Decimal("40")),
            dict(internal_code="DEMO-EQP-008",  name="سرنگ ۵ سی‌سی",     unit="عدد",   purchase_price=Decimal("3500"),    sale_price=Decimal("4500"),    minimum_stock=Decimal("150")),
            dict(internal_code="DEMO-EQP-009",  name="آنژیوکت ۱۸G",      unit="عدد",   purchase_price=Decimal("18000"),   sale_price=Decimal("22000"),   minimum_stock=Decimal("50")),
            dict(internal_code="DEMO-EQP-010",  name="ست سرم",            unit="عدد",   purchase_price=Decimal("25000"),   sale_price=Decimal("30000"),   minimum_stock=Decimal("60")),
        ]
        existing_codes = set(Product.objects.filter(
            internal_code__in=[d["internal_code"] for d in extra]
        ).values_list("internal_code", flat=True))
        to_create = [Product(product_type="medicine" if d["internal_code"].startswith("DEMO-MED") else "equipment", **d)
                     for d in extra if d["internal_code"] not in existing_codes]
        if to_create:
            Product.objects.bulk_create(to_create, ignore_conflicts=True)
            self._log(f"  [+] {len(to_create)} محصول اضافی ایجاد شد")
            for _ in to_create:
                self._track("products", True)
        for p in Product.objects.filter(internal_code__in=[d["internal_code"] for d in extra]):
            products[p.internal_code] = p

        return products

    # ------------------------------------------------------------------ product-vendor

    def _seed_product_vendors(self, products, vendors):
        from inventory.models import ProductVendor
        arya, pars, salamat = vendors[0], vendors[1], vendors[2]
        links = []
        for code, p in products.items():
            if code.startswith("DEMO-MED"):
                links += [(p, arya, True), (p, salamat, False)]
            else:
                links += [(p, pars, True)]
        existing = set(ProductVendor.objects.filter(
            product__internal_code__startswith="DEMO-"
        ).values_list("product_id", "vendor_id"))
        new = [ProductVendor(product=pr, vendor=v, unit_price=pr.purchase_price, is_primary=ip, is_active=True)
               for pr, v, ip in links if (pr.pk, v.pk) not in existing]
        if new:
            ProductVendor.objects.bulk_create(new, ignore_conflicts=True)
            self._log(f"  [+] {len(new)} ارتباط محصول–تامین‌کننده")
            for _ in new:
                self._track("pv", True)

    # ------------------------------------------------------------------ positions

    def _seed_positions(self):
        from employees.models import JobPosition
        pos = {}
        for name in _POSITIONS:
            obj, created = JobPosition.objects.get_or_create(name=name, defaults={"is_active": True})
            self._track("positions", created)
            pos[name] = obj
        return pos

    # ------------------------------------------------------------------ employees

    def _seed_employees(self, positions):
        from employees.models import Employee, GenderChoice
        emps = {}
        for nid, name, gender, pos_name, phone, emer, start in _EMPLOYEES:
            pos = positions.get(pos_name)
            if pos is None:
                continue
            emp, created = Employee.objects.get_or_create(
                national_id=nid,
                defaults=dict(full_name=name, gender=gender, job_position=pos,
                              start_date=start, personal_phone=phone,
                              emergency_contact_phone=emer, is_active=True),
            )
            self._log(f"  {'[+]' if created else ' - '} Employee: {name}")
            self._track("employees", created)
            emps[nid] = emp
        return emps

    # ------------------------------------------------------------------ wages

    def _seed_wages(self, employees):
        from payroll.models import MonthlyWage
        for nid, emp in employees.items():
            pos = emp.job_position.name
            amount = _WAGES.get(pos)
            if amount is None:
                continue
            exists = MonthlyWage.objects.filter(
                employee=emp, is_active=True, notes__contains=_MARKER
            ).exists()
            if not exists:
                MonthlyWage.objects.create(
                    employee=emp, amount=amount,
                    start_date=emp.start_date, is_active=True,
                    notes=_MARKER,
                )
                self._log(f"  [+] Wage: {emp.full_name}  {amount:,} ریال")
                self._track("wages", True)
            else:
                self._track("wages", False)

    # ------------------------------------------------------------------ surgery types

    def _seed_surgery_types(self):
        from surgeries.models import SurgeryType
        types = {}
        for code, name, rate in _SURGERY_TYPES:
            # name has unique constraint — try name first, fall back to code
            st = SurgeryType.objects.filter(name=name).first() \
              or SurgeryType.objects.filter(code=code).first()
            if st is None:
                st = SurgeryType.objects.create(
                    code=code, name=name, base_rate=rate,
                    is_active=True, description=_MARKER,
                )
                self._log(f"  [+] SurgeryType: {name}")
                self._track("surgery_types", True)
            else:
                self._track("surgery_types", False)
            types[code] = st
        return types

    # ------------------------------------------------------------------ commission rules

    def _seed_commission_rules(self, positions, surg_types):
        from payroll.models import CommissionRule
        for pos_name, st_code, pct in _COMMISSION_RULES:
            pos = positions.get(pos_name)
            st  = surg_types.get(st_code)
            if pos is None or st is None:
                continue
            exists = CommissionRule.objects.filter(job_position=pos, surgery_type=st, is_active=True).exists()
            if not exists:
                CommissionRule.objects.create(
                    job_position=pos, surgery_type=st, commission_percent=pct,
                    is_active=True, start_date=datetime.date(2020, 1, 1), notes=_MARKER,
                )
                self._track("commission_rules", True)
            else:
                self._track("commission_rules", False)

    # ------------------------------------------------------------------ doctors

    def _seed_doctors(self):
        from contacts.models import Doctor, DoctorSpecialty
        doctors = {}
        for d_id, name, phone, specialty, rate in _DOCTORS:
            existing = Doctor.objects.filter(phone_number=phone).first()
            if existing is None:
                specialty_obj, _ = DoctorSpecialty.objects.get_or_create(name=specialty)
                existing = Doctor.objects.create(
                    full_name=name, phone_number=phone, specialty=specialty_obj,
                    rate_per_surgery=rate, center_commission_percent=Decimal("30"),
                    cooperation_status="active", is_active=True, notes=_MARKER,
                )
                self._log(f"  [+] Doctor: {name}")
                self._track("doctors", True)
            else:
                self._track("doctors", False)
            doctors[d_id] = existing
        return doctors

    # ------------------------------------------------------------------ patients (40)

    def _seed_patients(self):
        from surgeries.models import Patient
        import hashlib
        patients = {}
        rnd = _seeded_rng(2025)
        for i in range(40):
            cc = f"DEMO-CASE-{i+1:03d}"
            first = _PATIENT_FIRST[i % len(_PATIENT_FIRST)]
            last  = _PATIENT_LAST[i  % len(_PATIENT_LAST)]
            name  = f"{first} {last}"
            phone = f"0913{(i+1):07d}"
            nat   = str(1000000000 + i * 97531)
            p, created = Patient.objects.get_or_create(
                case_code=cc,
                defaults=dict(full_name=name, phone_number=phone,
                              national_id=nat, description=_MARKER),
            )
            self._track("patients", created)
            patients[cc] = p
        self._log(f"  [+/{self.stats.get('patients',{}).get('e',0)}] {self.stats.get('patients',{}).get('c',0)} بیمار جدید")
        return patients

    # ------------------------------------------------------------------ purchases (40)

    def _seed_purchases(self, vendors, products):
        from inventory.models import Purchase, PurchaseItem, PurchaseStatus
        rnd = _seeded_rng(42)
        now = timezone.now()
        core_codes = list(_CONSUMABLES)
        count_new = 0
        for i in range(40):
            ref = f"DEMO-INV-{i+1:03d}"
            if Purchase.objects.filter(reference_number=ref).exists():
                self._track("purchases", False)
                continue
            vendor = vendors[i % len(vendors)]
            days   = 5 + i * 2
            pdate  = now - datetime.timedelta(days=days)
            pur = Purchase.objects.create(
                vendor=vendor, reference_number=ref,
                purchase_date=pdate, status=PurchaseStatus.PENDING,
                notes=f"[{_DEMO}] فاکتور نمونه {ref}",
            )
            num_items = 2 + (i % 4)
            chosen = core_codes[i % len(core_codes):(i % len(core_codes)) + num_items]
            if len(chosen) < num_items:
                chosen += core_codes[:num_items - len(chosen)]
            for code in chosen:
                p = products.get(code)
                if p is None:
                    continue
                qty   = Decimal(str(50 + (i % 5) * 20))
                price = (p.purchase_price * Decimal("0.97")).quantize(Decimal("1"))
                PurchaseItem.objects.create(purchase=pur, product=p, quantity=qty, unit_price=price)
            if i < 38:
                pur.confirm()
            self._log(f"  [+] Purchase {ref} {'confirmed' if i < 38 else 'pending'}")
            self._track("purchases", True)
            count_new += 1

    # ------------------------------------------------------------------ surgeries (50)

    def _seed_surgeries(self, patients, surg_types, employees, doctors):
        from surgeries.models import SurgeryHistory, PaymentStatus, SurgeryStatus
        from surgeries.services import SurgeryFinanceService
        now = timezone.now()
        st_codes = list(surg_types.keys())
        dr_ids   = list(doctors.keys())
        pt_codes = [f"DEMO-CASE-{i+1:03d}" for i in range(40)]
        # commission-eligible employees
        comm_emps = [e for e in employees.values() if e.job_position.name in ("متخصص بیهوشی","پرستار","تکنسین اتاق عمل")]
        surgeries = {}
        for i in range(50):
            tag = f"DEMO-S{i+1:03d}"
            existing = SurgeryHistory.objects.filter(description__contains=tag).first()
            if existing:
                self._track("surgeries", False)
                surgeries[tag] = existing
                continue
            cc      = pt_codes[i % len(pt_codes)]
            patient = patients.get(cc)
            if patient is None:
                continue
            st_code = st_codes[i % len(st_codes)]
            st      = surg_types[st_code]
            amount  = _AMOUNTS[i % len(_AMOUNTS)]
            pay_st  = _PAY_STATUSES[i % len(_PAY_STATUSES)]
            s_st    = _SURG_STATUSES[i % len(_SURG_STATUSES)]
            sdate   = now - datetime.timedelta(days=1 + i * 2)
            emp     = comm_emps[i % len(comm_emps)] if comm_emps else None
            doc_id  = dr_ids[i % len(dr_ids)]
            doctor  = doctors[doc_id]

            sh = SurgeryHistory.objects.create(
                patient=patient, surgery_type=st,
                clinical_doctor=doctor, doctor_or_therapist=emp,
                surgery_date=sdate, amount=amount,
                status=s_st, payment_status=pay_st,
                center_commission_percent=Decimal("30"),
                description=f"[{tag}] عمل نمونه | {_MARKER}",
            )
            SurgeryFinanceService.sync_center_commission_income(sh)
            self._log(f"  [+] Surgery {tag}: {st.name} — {amount:,}")
            self._track("surgeries", True)
            surgeries[tag] = sh
        return surgeries

    # ------------------------------------------------------------------ used items

    def _seed_used_items(self, surgeries, products):
        from surgeries.models import SurgeryUsedItem, SurgeryStatus
        from surgeries.services import SurgeryInventoryService
        from django.core.exceptions import ValidationError
        consumable_codes = [c for c in _CONSUMABLES if c in products]
        done = 0
        for tag, sh in surgeries.items():
            if sh.status != SurgeryStatus.COMPLETED:
                continue
            if SurgeryUsedItem.objects.filter(surgery=sh).exists():
                self._track("used_items", False)
                continue
            idx = int(tag.replace("DEMO-S","")) - 1
            for j in range(2 + (idx % 4)):
                code = consumable_codes[(idx + j) % len(consumable_codes)]
                p    = products.get(code)
                if p is None:
                    continue
                p.refresh_from_db()
                qty = Decimal(str(2 + j))
                if p.current_stock < qty:
                    qty = max(Decimal("1"), p.current_stock)
                if qty <= 0:
                    continue
                try:
                    item = SurgeryUsedItem.objects.create(
                        surgery=sh, product=p, quantity=qty,
                        description=f"[{_DEMO}] مصرف {tag}",
                    )
                    SurgeryInventoryService.consume_product(item)
                    self._track("used_items", True)
                    done += 1
                except ValidationError:
                    pass
        self._log(f"  [+] {done} قلم مصرف جراحی (موجودی کاهش یافت)")

    # ------------------------------------------------------------------ purchase commissions

    def _seed_purchase_commissions(self, employees):
        from employees.models import EmployeePurchaseCommission
        from inventory.models import Purchase
        _DEMO_COMMS = [
            # (employee_nid, purchase_ref, amount, date, description)
            ("DEMO-EMP-007", "DEMO-INV-001", Decimal("350000"), datetime.date(2025, 1, 15), f"[{_DEMO}] پورسانت خرید بهمن ۱۴۰۳"),
            ("DEMO-EMP-007", "DEMO-INV-005", Decimal("480000"), datetime.date(2025, 3, 10), f"[{_DEMO}] پورسانت خرید اسفند ۱۴۰۳"),
            ("DEMO-EMP-004", None,            Decimal("200000"), datetime.date(2025, 2,  5), f"[{_DEMO}] کمیسیون هماهنگی خرید"),
        ]
        for nid, ref, amount, date, desc in _DEMO_COMMS:
            emp = employees.get(nid)
            if emp is None:
                continue
            purchase = Purchase.objects.filter(reference_number=ref).first() if ref else None
            exists = EmployeePurchaseCommission.objects.filter(
                employee=emp, commission_date=date, description=desc,
            ).exists()
            if not exists:
                EmployeePurchaseCommission.objects.create(
                    employee=emp,
                    purchase=purchase,
                    amount=amount,
                    commission_date=date,
                    description=desc,
                )
                self._log(f"  [+] PurchaseCommission: {emp.full_name}  {amount:,} تومان")
                self._track("purchase_commissions", True)
            else:
                self._track("purchase_commissions", False)

    # ------------------------------------------------------------------ payroll period

    def _seed_payroll_period(self):
        from payroll.models import PayrollPeriod, PayrollStatus
        year, month = 1405, 2
        period = PayrollPeriod.objects.filter(year=year, month=month).first()
        if period is None:
            period = PayrollPeriod.objects.create(
                year=year, month=month, status=PayrollStatus.OPEN,
                notes=f"[{_DEMO}] دوره آزمایشی",
            )
            self._track("payroll_periods", True)
            self._log(f"  [+] PayrollPeriod {year}/{month}")
        else:
            self._track("payroll_periods", False)
        if period.status == PayrollStatus.OPEN:
            period.close()
            self._log("  [+] دوره حقوقی بسته شد — هزینه حقوق در مالی ثبت شد")

    # ------------------------------------------------------------------ manual finance

    def _seed_manual_finance(self):
        from finance.models import FinanceCategory, Transaction, CategoryType, TransactionType
        entries = [
            (TransactionType.EXPENSE, "هزینه تجهیزات",   CategoryType.EXPENSE, Decimal("5000000")),
            (TransactionType.INCOME,  "کمیسیون مرکز از اعمال جراحی", CategoryType.INCOME, Decimal("3000000")),
        ]
        for tx_type, cat_name, cat_type, amount in entries:
            desc = f"[{_DEMO}] {cat_name} آزمایشی"
            if Transaction.objects.filter(description=desc).exists():
                self._track("finance_manual", False)
                continue
            cat = FinanceCategory.objects.filter(name=cat_name, category_type=cat_type).first()
            if cat is None:
                continue
            Transaction.objects.create(transaction_type=tx_type, category=cat, amount=amount, description=desc)
            self._track("finance_manual", True)
            self._log(f"  [+] Finance: {desc}")

    # ------------------------------------------------------------------ summary

    def _print_summary(self):
        sep = "=" * 55
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(sep))
        self._log(self.style.SUCCESS("  [OK] داده نمونه با موفقیت ایجاد شد"))
        self.stdout.write(self.style.SUCCESS(sep))
        rows = [
            ("Vendors",           "vendors"),
            ("Products",          "products"),
            ("Product-Vendor",    "pv"),
            ("Positions",         "positions"),
            ("Employees",         "employees"),
            ("Wages",             "wages"),
            ("Surgery types",     "surgery_types"),
            ("Commission rules",  "commission_rules"),
            ("Doctors",           "doctors"),
            ("Patients",          "patients"),
            ("Purchases",         "purchases"),
            ("Surgeries",         "surgeries"),
            ("Used items",        "used_items"),
            ("Payroll periods",   "payroll_periods"),
            ("Finance manual",    "finance_manual"),
        ]
        for label, key in rows:
            s = self.stats.get(key, {"c": 0, "e": 0})
            if s["c"] + s["e"] > 0:
                self.stdout.write(f"  {label:<20}  created={s['c']}  reused={s['e']}")
        self.stdout.write(self.style.SUCCESS(sep))
        self.stdout.write("  [idempotent]  python manage.py seed_demo_data --reset")
        self.stdout.write("")

        self.stdout.write("")


def _seeded_rng(seed):
    import random
    r = random.Random(seed)
    return r


_PATIENT_FIRST = [
    "فاطمه","زینب","مریم","سارا","نگار","رویا","ندا","شیرین","پریسا","نازنین",
    "محمد","علی","حسین","رضا","امیر","مهدی","سعید","کیان","آرمان","بهرام",
    "لیلا","سمیه","آزاده","مینا","صبا","الهام","شهلا","گلنار","بهناز","هانیه",
    "داوود","بابک","کاوه","سیامک","آرش","نوید","پوریا","شاهین","مانی","فرید",
]
_PATIENT_LAST = [
    "محمدی","احمدی","حسینی","رضایی","کریمی","موسوی","صادقی","جعفری",
    "نظری","قاسمی","ناصری","مرادی","فروزان","طاهری","اکبری","شریفی",
    "رحیمی","یوسفی","سلطانی","امیری","خانی","مومنی","حسن‌زاده","دولتی",
]
