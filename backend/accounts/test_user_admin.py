"""Tests for the System Users admin panel."""
from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class UserAdminTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser('sadmin', 'a@b.com', 'pass123')
        self.client.force_login(self.superuser)

    def test_user_list_loads(self):
        resp = self.client.get('/admin/auth/user/')
        self.assertEqual(resp.status_code, 200)

    def test_add_user_form_loads(self):
        resp = self.client.get('/admin/auth/user/add/')
        self.assertEqual(resp.status_code, 200)

    def test_edit_user_form_loads(self):
        resp = self.client.get(f'/admin/auth/user/{self.superuser.pk}/change/')
        self.assertEqual(resp.status_code, 200)

    def test_create_user_via_admin(self):
        resp = self.client.post('/admin/auth/user/add/', {
            'username':  'newuser',
            'password1': 'TestPass123!',
            'password2': 'TestPass123!',
        })
        # Successful creation redirects to the change form
        self.assertIn(resp.status_code, (200, 302))
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_unauthenticated_redirects_to_login(self):
        self.client.logout()
        resp = self.client.get('/admin/auth/user/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/login/', resp.url)

    def test_group_list_loads(self):
        resp = self.client.get('/admin/auth/group/')
        self.assertEqual(resp.status_code, 200)
