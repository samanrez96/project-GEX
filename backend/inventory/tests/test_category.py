"""
Tests for ProductCategory model, serializers, and API endpoints.

Business decision documented here (per spec):
  Deactivating a parent does NOT cascade to children.
  Rationale: is_active on a category is an editorial flag (hide from UI).
  Children may still be relevant independently. The application layer
  (serializer/view) can choose to filter by is_active; it is not enforced
  at the model level because that cascade would be a silent, hard-to-reverse
  side effect. If cascade behaviour is ever needed, it should be explicit
  (a management command or admin action with a confirmation step).
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status

from inventory.models import ProductCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_category(name, parent=None, is_active=True):
    return ProductCategory.objects.create(name=name, parent=parent, is_active=is_active)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class ProductCategoryModelTest(TestCase):

    def test_create_root_category(self):
        cat = make_category("دارو")
        self.assertIsNotNone(cat.pk)
        self.assertTrue(cat.is_root)
        self.assertIsNone(cat.parent)

    def test_create_child_category(self):
        root = make_category("دارو")
        child = make_category("داروی بیهوشی", parent=root)
        self.assertFalse(child.is_root)
        self.assertEqual(child.parent, root)

    def test_duplicate_name_under_same_parent_raises(self):
        root = make_category("دارو")
        make_category("زیرمجموعه", parent=root)
        with self.assertRaises(IntegrityError):
            make_category("زیرمجموعه", parent=root)

    def test_same_name_under_different_parents_allowed(self):
        root1 = make_category("دارو")
        root2 = make_category("تجهیزات")
        c1 = make_category("عمومی", parent=root1)
        c2 = make_category("عمومی", parent=root2)
        self.assertNotEqual(c1.pk, c2.pk)

    def test_circular_reference_raises_validation_error(self):
        root = make_category("دارو")
        child = make_category("داروی بیهوشی", parent=root)
        # Attempt to make root a child of its own descendant
        root.parent = child
        with self.assertRaises(ValidationError):
            root.clean()

    def test_self_reference_raises_validation_error(self):
        root = make_category("دارو")
        root.parent = root
        with self.assertRaises(ValidationError):
            root.clean()

    def test_full_path_three_levels(self):
        root = make_category("دارو")
        mid  = make_category("داروی بیهوشی", parent=root)
        leaf = make_category("داروی تزریقی", parent=mid)
        self.assertEqual(leaf.full_path, "دارو / داروی بیهوشی / داروی تزریقی")

    def test_full_path_root_category(self):
        root = make_category("دارو")
        self.assertEqual(root.full_path, "دارو")

    def test_str_returns_full_path(self):
        root = make_category("دارو")
        child = make_category("داروی بیهوشی", parent=root)
        self.assertEqual(str(child), "دارو / داروی بیهوشی")

    def test_get_all_descendants(self):
        root  = make_category("دارو")
        mid   = make_category("داروی بیهوشی", parent=root)
        leaf1 = make_category("داروی تزریقی", parent=mid)
        leaf2 = make_category("داروی استنشاقی", parent=mid)
        descendants = root.get_all_descendants()
        pks = {d.pk for d in descendants}
        self.assertIn(mid.pk, pks)
        self.assertIn(leaf1.pk, pks)
        self.assertIn(leaf2.pk, pks)
        self.assertEqual(len(descendants), 3)

    def test_get_all_descendants_empty_for_leaf(self):
        root = make_category("دارو")
        self.assertEqual(root.get_all_descendants(), [])

    def test_delete_parent_with_children_raises_protected_error(self):
        root = make_category("دارو")
        make_category("داروی بیهوشی", parent=root)
        with self.assertRaises(ProtectedError):
            root.delete()

    def test_deactivating_parent_does_not_affect_children(self):
        """Explicit business rule: is_active does NOT cascade to children."""
        root = make_category("دارو")
        child = make_category("داروی بیهوشی", parent=root)
        root.is_active = False
        root.save()
        child.refresh_from_db()
        self.assertTrue(child.is_active)


# ---------------------------------------------------------------------------
# Migration seed test
# ---------------------------------------------------------------------------

class SeedMigrationTest(TestCase):
    """Verifies that the data migration seeded the two root categories.

    Django's test runner applies all migrations before running tests, so
    the seed rows will be present if the migration ran correctly.
    """

    def test_daro_root_exists(self):
        self.assertTrue(
            ProductCategory.objects.filter(name="دارو", parent=None).exists()
        )

    def test_tajhizat_root_exists(self):
        self.assertTrue(
            ProductCategory.objects.filter(name="تجهیزات", parent=None).exists()
        )


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class ProductCategoryAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass1234")
        self.client.force_authenticate(user=self.user)

        self.root_daro     = ProductCategory.objects.get(name="دارو",      parent=None)
        self.root_tajhizat = ProductCategory.objects.get(name="تجهیزات",  parent=None)
        self.child         = make_category("داروی بیهوشی", parent=self.root_daro)

    def test_list_returns_all_categories(self):
        resp = self.client.get("/api/v1/inventory/categories/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [item["name"] for item in resp.data["results"]]
        self.assertIn("دارو", names)
        self.assertIn("تجهیزات", names)
        self.assertIn("داروی بیهوشی", names)

    def test_list_filter_by_is_active(self):
        inactive = make_category("منسوخ", is_active=False)
        resp = self.client.get("/api/v1/inventory/categories/?is_active=true")
        names = [item["name"] for item in resp.data["results"]]
        self.assertNotIn("منسوخ", names)
        _ = inactive  # silence unused-var warning

    def test_list_filter_by_parent_null(self):
        resp = self.client.get("/api/v1/inventory/categories/?parent=null")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for item in resp.data["results"]:
            self.assertIsNone(item["parent"])

    def test_retrieve_includes_direct_children(self):
        resp = self.client.get(f"/api/v1/inventory/categories/{self.root_daro.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        child_names = [c["name"] for c in resp.data["children"]]
        self.assertIn("داروی بیهوشی", child_names)

    def test_tree_endpoint_returns_roots_only(self):
        resp = self.client.get("/api/v1/inventory/categories/tree/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # All top-level items should be root categories
        for item in resp.data:
            self.assertEqual(item["depth"], 0)

    def test_tree_endpoint_nests_children(self):
        resp = self.client.get("/api/v1/inventory/categories/tree/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        daro_node = next(
            (item for item in resp.data if item["name"] == "دارو"), None
        )
        self.assertIsNotNone(daro_node)
        child_names = [c["name"] for c in daro_node["children"]]
        self.assertIn("داروی بیهوشی", child_names)

    def test_unauthenticated_request_is_rejected(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get("/api/v1/inventory/categories/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
