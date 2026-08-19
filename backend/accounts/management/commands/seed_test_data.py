"""
Seed 50 test records for each model in the surgery clinic system.

Usage:
    python manage.py seed_test_data
    python manage.py seed_test_data --count 100
    python manage.py seed_test_data --reset

This command creates realistic fake data for all models.
Running with --reset drops all test data (non-DEMO) first.
"""

import random
import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Seed test records for each model with realistic Persian fake data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count", type=int, default=50,
            help="Number of records per model (default: 50)",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help="Drop all test data (non-DEMO) before seeding",
        )

    def handle(self, *args, **options):
        count = options["count"]
        reset = options["reset"]

        if reset:
            self.stdout.write(self.style.WARNING("Resetting test data..."))
            self._reset_data()

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n{'='*60}\n  Seeding {count} test records per model\n{'='*60}"
        ))

        vendors = self._seed_vendors(count)
        categories = self._seed_categories()
        products = self._seed_products(count, categories)
        self._seed_product_vendors(products, vendors)
        positions = self._seed_positions()
        employees = self._seed_employees(count, positions)
        self._seed_wages(employees)
        self._seed_doctor_contacts(count)
        surgery_types = self._seed_surgery_types()
        self._seed_commission_rules(positions, surgery_types)
        patients = self._seed_patients(count)
        self._seed_surgery_histories(count, patients, surgery_types, employees)
        self._seed_transactions(count, categories)

        self.stdout.write(self.style.SUCCESS(
            f"\n{'='*60}\n  Done! Seeded {count} records per model.\n{'='*60}"
        ))

    # ─── Reset ───────────────────────────────────────────────────────────────

    def _reset_data(self):
        from inventory.models import (
            Product, Vendor, ProductVendor, StockMovement,
            Purchase, PurchaseItem, ProductCategory
        )
        from employees.models import Employee, JobPosition, MonthlyWage
        from contacts.models import Doctor
        from surgeries.models import (
            Patient, SurgeryType, SurgeryHistory,
            SurgeryUsedItem, Surgery, SurgeryConsumptionItem
        )
        from payroll.models import (
            PayrollPeriod, PayrollTypeConfig,
            CommissionRule, CommissionTransaction
        )
        from finance.models import (
            FinanceCategory, Transaction, CenterCommissionIncome
        )

        Transaction.objects.exclude(description__startswith="DEMO").delete()
        CenterCommissionIncome.objects.all().delete()
        CommissionTransaction.objects.all().delete()
        SurgeryConsumptionItem.objects.all().delete()
        SurgeryUsedItem.objects.all().delete()
        SurgeryHistory.objects.all().delete()
        Surgery.objects.all().delete()
        StockMovement.objects.all().delete()
        PurchaseItem.objects.all().delete()
        Purchase.objects.all().delete()
        ProductVendor.objects.all().delete()
        Product.objects.exclude(internal_code__startswith="DEMO").delete()
        Vendor.objects.exclude(name__startswith="DEMO").delete()
        ProductCategory.objects.all().delete()
        PayrollPeriod.objects.all().delete()
        PayrollTypeConfig.objects.all().delete()
        MonthlyWage.objects.all().delete()
        CommissionRule.objects.all().delete()
        Employee.objects.exclude(national_id__startswith="DEMO").delete()
        JobPosition.objects.all().delete()
        Doctor.objects.all().delete()
        Patient.objects.all().delete()
        SurgeryType.objects.all().delete()
        self.stdout.write("  Reset complete.")

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _rp(self):
        """Random Persian phone."""
        return f"09{random.randint(100000000, 999999999)}"

    def _rd(self, sy=2020, ey=2026):
        s = datetime.date(sy, 1, 1)
        e = datetime.date(ey, 12, 31)
        return s + datetime.timedelta(days=random.randint(0, (e - s).days))

    def _rdt(self, sy=2023, ey=2026):
        d = self._rd(sy, ey)
        return timezone.make_aware(
            datetime.datetime.combine(d, datetime.time(random.randint(8, 20), random.choice([0, 15, 30, 45])))
        )

    def _ramt(self, lo=50000, hi=5000000):
        return Decimal(str(random.randint(lo, hi)))

    def _rname(self):
        males = [
            "علی", "رضا", "محمد", "امیر", "حسن", "حسین", "احمد", "مهدی",
            "سعید", "فرهاد", "داریوش", "بهرام", "کامران", "منوچهر", "بهروز",
            "جواد", "مرتضی", "محمدرضا", "پوریا", "آرش", "کیان", "آریان",
            "سینا", "امیرحسین", "میلاد", "حمید", "نیما", "یاسین", "طاها", "پارسا",
        ]
        females = [
            "مریم", "فاطمه", "زهرا", "سارا", "نسرین", "ندا", "الناز", "مهسا",
            "سمیرا", "مهناز", "پریسا", "نیلوفر", "ترانه", "آزاده", "گلناز",
            "الهام", "نگار", "یلدا", "دنا", "سوگل", "مینا", "هانیه", "ستاره",
            "پردیس", "شبنم", "لیلا", "بهار", "کوثر", "نرگس", "مائده",
        ]
        lasts = [
            "رضایی", "احمدی", "محمدی", "کریمی", "moradi", "ghasemi", "rahimi",
            "hashemi", "hosseini", "akbari", "jafari", "karimi", "sadeghi",
            "amiri", "mousavi", "tabatabaei", "bagheri", "yazdi", "tehrani",
            "shirazi", "kermani", "lotfi", "shams", "niazi", "zare",
            "salehi", "yousefi", "ahmadi", "kazemi", "rezaei",
        ]
        g = random.choice(["m", "f"])
        f = random.choice(males if g == "m" else females)
        l = random.choice(lasts)
        return f, l, g

    # ─── Seed Vendors ────────────────────────────────────────────────────────

    def _seed_vendors(self, count):
        from inventory.models import Vendor
        self.stdout.write(f"\n[Vendors] Creating {count} records...")
        vendors = []
        for i in range(count):
            n = f"فروشنده تست {i+1}"
            v, created = Vendor.objects.get_or_create(
                name=n,
                defaults={
                    "phone_number": self._rp(),
                    "email": f"vendor{i+1}@test.local",
                    "address": f"آدرس فروشنده شماره {i+1}",
                    "is_active": random.random() > 0.1,
                },
            )
            vendors.append(v)
            if created:
                self.stdout.write(f"  [+] {n}")
        return vendors

    # ─── Seed Categories ─────────────────────────────────────────────────────

    def _seed_categories(self):
        from inventory.models import ProductCategory
        self.stdout.write("\n[Categories] Creating root categories...")
        cats = {}
        for name in ["دارو", "تجهیزات"]:
            c, _ = ProductCategory.objects.get_or_create(
                name=name, parent=None, defaults={"is_active": True}
            )
            cats[name] = c
        return cats

    # ─── Seed Products ───────────────────────────────────────────────────────

    def _seed_products(self, count, cats):
        from inventory.models import Product, ProductType
        self.stdout.write(f"\n[Products] Creating {count} records...")
        products = []
        med_units = ["قرص", "آمپول", "کپسول", "ویال", "محلول", "کرم", "پماد", "قطره"]
        eqp_units = ["عدد", "بسته", "جعبه", "ست", "دستگاه"]

        for i in range(count):
            is_med = i < count // 2
            ptype = ProductType.MEDICINE if is_med else ProductType.EQUIPMENT
            cat = cats.get("دارو" if is_med else "تجهیزات")
            p, created = Product.objects.get_or_create(
                internal_code=f"TEST-{i+1:04d}",
                defaults={
                    "name": f"محصول تست شماره {i+1}",
                    "product_type": ptype,
                    "category": cat,
                    "unit": random.choice(med_units if is_med else eqp_units),
                    "purchase_price": self._ramt(10000, 1000000),
                    "sale_price": self._ramt(15000, 1500000),
                    "barcode": str(random.randint(1000000000000, 9999999999999)),
                    "minimum_stock": self._ramt(5, 100),
                    "is_active": random.random() > 0.1,
                },
            )
            products.append(p)
            if created:
                self.stdout.write(f"  [+] {p.internal_code}")
        return products

    # ─── Seed ProductVendor ──────────────────────────────────────────────────

    def _seed_product_vendors(self, products, vendors):
        from inventory.models import ProductVendor
        self.stdout.write(f"\n[ProductVendor] Creating links...")
        n = 0
        for p in products[:min(50, len(products))]:
            v = random.choice(vendors)
            _, created = ProductVendor.objects.get_or_create(
                product=p, vendor=v,
                defaults={
                    "unit_price": p.purchase_price,
                    "is_primary": random.random() > 0.5,
                    "is_active": True,
                },
            )
            if created:
                n += 1
        self.stdout.write(f"  Created {n} links.")

    # ─── Seed JobPositions ───────────────────────────────────────────────────

    def _seed_positions(self):
        from employees.models import JobPosition
        self.stdout.write("\n[JobPositions] Creating...")
        names = [
            "متخصص بیهوشی", "پرستار", "تکنسین اتاق عمل", "منشی",
            "حسابدار", "جراح", "متخصص زیبایی", "مسئول تجهیزات",
            "کمک بهیار", "مسئول داروخانه",
        ]
        positions = {}
        for n in names:
            p, _ = JobPosition.objects.get_or_create(name=n, defaults={"is_active": True})
            positions[n] = p
        self.stdout.write(f"  Created {len(positions)} positions.")
        return positions

    # ─── Seed Employees ──────────────────────────────────────────────────────

    def _seed_employees(self, count, positions):
        from employees.models import Employee, GenderChoice
        self.stdout.write(f"\n[Employees] Creating {count} records...")
        employees = []
        plist = list(positions.values())

        for i in range(count):
            f, l, g = self._rname()
            gn = GenderChoice.MALE if g == "m" else GenderChoice.FEMALE
            e, created = Employee.objects.get_or_create(
                national_id=str(random.randint(1000000000, 9999999999)),
                defaults={
                    "full_name": f"{f} {l}",
                    "gender": gn,
                    "job_position": random.choice(plist),
                    "start_date": self._rd(2018, 2025),
                    "personal_phone": self._rp(),
                    "emergency_contact_phone": self._rp(),
                    "email": f"emp{i+1}@test.local",
                    "is_active": random.random() > 0.15,
                },
            )
            employees.append(e)
            if created:
                self.stdout.write(f"  [+] {f} {l}")
        return employees

    # ─── Seed Wages ──────────────────────────────────────────────────────────

    def _seed_wages(self, employees):
        from payroll.models import MonthlyWage
        self.stdout.write("\n[MonthlyWage] Creating...")
        n = 0
        for e in employees[:min(50, len(employees))]:
            if random.random() > 0.3:
                amt = self._ramt(3000000, 25000000)
                s = self._rd(2020, 2024)
                w, created = MonthlyWage.objects.get_or_create(
                    employee=e, amount=amt, start_date=s,
                    defaults={"is_active": True},
                )
                if created:
                    n += 1
        self.stdout.write(f"  Created {n} wages.")

    # ─── Seed Doctors ─────────────────────────────────────────────────

    def _seed_doctor_contacts(self, count):
        from contacts.models import Doctor, DoctorSpecialty
        self.stdout.write(f"\n[Doctor] Creating {count} records...")
        specs = [
            "جراحی پلاستیک", "بیهوشی", "جراحی عمومی", "جراحی مغز و اعصاب",
            "ارتوپدی", "قلب و عروق", "پوست و مو", "چشم پزشکی",
            "گوش و حلق و بینی", "زنان و زایمان",
        ]
        specialty_objs = [DoctorSpecialty.objects.get_or_create(name=s)[0] for s in specs]
        for i in range(count):
            f, l, _ = self._rname()
            Doctor.objects.get_or_create(
                phone_number=self._rp(),
                defaults={
                    "full_name": f"دکتر {f} {l}",
                    "specialty": random.choice(specialty_objs),
                    "email": f"dr{i+1}@test.local",
                    "center_commission_percent": Decimal(str(random.choice([10, 15, 20, 25, 30]))),
                    "cooperation_status": random.choice(["active", "active", "active", "inactive"]),
                    "is_active": random.random() > 0.1,
                },
            )
        self.stdout.write(f"  Created {count} doctor contacts.")

    # ─── Seed SurgeryTypes ───────────────────────────────────────────────────

    def _seed_surgery_types(self):
        from surgeries.models import SurgeryType
        self.stdout.write("\n[SurgeryType] Creating...")
        types = [
            ("rhinoplasty", "رینوپلاستی", 15000000),
            ("blepharoplasty", "بلفاروپلاستی", 8000000),
            ("liposuction", "لیپوساکشن", 20000000),
            ("abdominoplasty", "ابدومینوپلاستی", 25000000),
            ("face_lift", "لیفت صورت", 30000000),
            ("brow_lift", "لیفت ابرو", 12000000),
            ("chin_implant", "پروتز چانه", 10000000),
            ("ear_surgery", "جراحی گوش", 7000000),
            ("breast_aug", "پروتز سینه", 22000000),
            ("rhinosepto", "رینوسپتوپلاستی", 18000000),
            ("fat_inject", "تزریق چربی", 8000000),
            ("botox", "تزریق بوتاکس", 3000000),
            ("filler", "تزریق فیلر", 4000000),
            ("gynecomastia", "ژنیکوماستی", 15000000),
            ("hair_transplant", "کاشت مو", 12000000),
        ]
        result = []
        for code, name, rate in types:
            st, created = SurgeryType.objects.get_or_create(
                code=code,
                defaults={"name": name, "base_rate": Decimal(str(rate)), "is_active": True},
            )
            result.append(st)
            if created:
                self.stdout.write(f"  [+] {name}")
        return result

    # ─── Seed CommissionRules ────────────────────────────────────────────────

    def _seed_commission_rules(self, positions, surgery_types):
        from payroll.models import CommissionRule
        self.stdout.write("\n[CommissionRule] Creating...")
        n = 0
        for pos in list(positions.values())[:5]:
            st = random.choice(surgery_types)
            _, created = CommissionRule.objects.get_or_create(
                job_position=pos, surgery_type=st,
                defaults={
                    "commission_percent": Decimal(str(random.choice([5, 10, 15, 20, 25]))),
                    "is_active": True,
                },
            )
            if created:
                n += 1
        self.stdout.write(f"  Created {n} rules.")

    # ─── Seed Patients ───────────────────────────────────────────────────────

    def _seed_patients(self, count):
        from surgeries.models import Patient
        self.stdout.write(f"\n[Patient] Creating {count} records...")
        patients = []
        for i in range(count):
            f, l, _ = self._rname()
            p, created = Patient.objects.get_or_create(
                case_code=f"{random.choice([1401,1402,1403,1404])}-{random.randint(1000,9999)}",
                defaults={
                    "full_name": f"{f} {l}",
                    "phone_number": self._rp(),
                    "description": f"توضیحات بیمار تست {i+1}",
                },
            )
            patients.append(p)
            if created:
                self.stdout.write(f"  [+] {f} {l}")
        return patients

    # ─── Seed SurgeryHistories ───────────────────────────────────────────────

    def _seed_surgery_histories(self, count, patients, surgery_types, employees):
        from surgeries.models import SurgeryHistory, SurgeryStatus, PaymentStatus
        self.stdout.write(f"\n[SurgeryHistory] Creating {count} records...")
        n = 0
        statuses = list(SurgeryStatus)
        pay_statuses = list(PaymentStatus)

        for i in range(count):
            pt = random.choice(patients)
            st = random.choice(surgery_types)
            amt = self._ramt(3000000, 50000000)
            _, created = SurgeryHistory.objects.get_or_create(
                patient=pt,
                surgery_date=self._rdt(2023, 2026),
                defaults={
                    "case_code": pt.case_code,
                    "phone_number": pt.phone_number,
                    "surgery_type": st,
                    "amount": amt,
                    "status": random.choice(statuses).value,
                    "payment_status": random.choice(pay_statuses).value,
                    "center_commission_percent": Decimal(str(random.choice([10, 15, 20, 25]))),
                    "description": f"توضیحات عمل جراحی تست {i+1}",
                },
            )
            if created:
                n += 1
        self.stdout.write(f"  Created {n} surgery histories.")

    # ─── Seed Transactions ───────────────────────────────────────────────────

    def _seed_transactions(self, count, cats):
        from finance.models import Transaction, TransactionPaymentStatus
        self.stdout.write(f"\n[Transaction] Creating {count} records...")
        cat_list = list(cats.values())
        n = 0
        pay_statuses = list(TransactionPaymentStatus)

        for i in range(count):
            tx_type = random.choice(["income", "expense"])
            cat = random.choice(cat_list) if cat_list else None
            _, created = Transaction.objects.get_or_create(
                description=f"تراکنش تست شماره {i+1}",
                defaults={
                    "transaction_type": tx_type,
                    "category": cat,
                    "amount": self._ramt(50000, 10000000),
                    "transaction_date": self._rdt(2023, 2026),
                    "payment_status": random.choice(pay_statuses).value,
                },
            )
            if created:
                n += 1
        self.stdout.write(f"  Created {n} transactions.")
