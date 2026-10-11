import unittest
from unittest.mock import patch, MagicMock
import handlers
import config
import keyboards

class TestCheckAuth(unittest.TestCase):

    @patch('handlers.db')
    @patch('handlers.config')
    def test_check_auth_admin(self, mock_config, mock_db):
        mock_config.ADMIN_CHAT_ID = "12345"
        chat_id = 12345

        result = handlers.check_auth(chat_id)

        self.assertTrue(result)
        mock_db.ensure_user_exists.assert_called_once_with("12345")
        mock_db.set_user_authorized.assert_called_once_with("12345", True)

    @patch('handlers.db')
    @patch('handlers.config')
    def test_check_auth_authorized_user(self, mock_config, mock_db):
        mock_config.ADMIN_CHAT_ID = "12345"
        chat_id = 67890
        mock_db.get_user.return_value = {'chat_id': '67890', 'is_authorized': 1}

        result = handlers.check_auth(chat_id)

        self.assertTrue(result)
        mock_db.get_user.assert_called_once_with("67890")

    @patch('handlers.db')
    @patch('handlers.config')
    def test_check_auth_unauthorized_user(self, mock_config, mock_db):
        mock_config.ADMIN_CHAT_ID = "12345"
        chat_id = 67890
        mock_db.get_user.return_value = {'chat_id': '67890', 'is_authorized': 0}

        result = handlers.check_auth(chat_id)

        self.assertFalse(result)
        mock_db.get_user.assert_called_once_with("67890")

    @patch('handlers.db')
    @patch('handlers.config')
    def test_check_auth_nonexistent_user(self, mock_config, mock_db):
        mock_config.ADMIN_CHAT_ID = "12345"
        chat_id = 67890
        mock_db.get_user.return_value = None

        result = handlers.check_auth(chat_id)

        self.assertFalse(result)
        mock_db.get_user.assert_called_once_with("67890")

    @patch('handlers.db')
    @patch('handlers.config')
    def test_check_auth_missing_authorized_key(self, mock_config, mock_db):
        mock_config.ADMIN_CHAT_ID = "12345"
        chat_id = 67890
        mock_db.get_user.return_value = {'chat_id': '67890'}

        result = handlers.check_auth(chat_id)

        self.assertFalse(result)
        mock_db.get_user.assert_called_once_with("67890")

    @patch('handlers.db')
    @patch('handlers.config')
    def test_check_auth_no_admin_config(self, mock_config, mock_db):
        mock_config.ADMIN_CHAT_ID = None
        chat_id = 67890
        mock_db.get_user.return_value = {'chat_id': '67890', 'is_authorized': 1}

        result = handlers.check_auth(chat_id)

        self.assertTrue(result)
        mock_db.get_user.assert_called_once_with("67890")

class TestMakeToken(unittest.TestCase):

    def test_make_token_format(self):
        token = handlers.make_token()
        self.assertRegex(token, r'^ADU-[A-Z0-9]{4}-[A-Z0-9]{4}$')

    def test_make_token_randomness(self):
        tokens = set()
        for _ in range(50):
            tokens.add(handlers.make_token())
        self.assertEqual(len(tokens), 50)

class TestDepartments(unittest.TestCase):

    def test_all_departments_count(self):
        """Verify that all official hospital departments are registered"""
        self.assertEqual(len(config.ADU_DEPARTMENTS), 53)
        self.assertIn(208, config.ADU_DEPARTMENTS) # Aile Hekimliği
        self.assertIn(260, config.ADU_DEPARTMENTS) # Kardiyoloji
        self.assertIn(288, config.ADU_DEPARTMENTS) # Göz
        self.assertIn(389, config.ADU_DEPARTMENTS) # Çocuk Hematolojisi (Özel)
        self.assertIn(-147, config.ADU_DEPARTMENTS) # Yara Bakım Ünitesi
        self.assertEqual(len(config.RANDEVU_TYPES), 3)

    def test_matching_specialty_by_id(self):
        """Verify matching by exact department ID"""
        active_specs = [(208, "Aile Hekimliği"), (260, "Kardiyoloji")]
        matched = handlers.find_matching_specialty(208, "Aile Hekimliği", active_specs)
        self.assertEqual(matched, (208, "Aile Hekimliği"))

    def test_matching_specialty_by_name_fallback(self):
        """Verify fallback matching by cleaned Turkish name"""
        active_specs = [(208, "Aile Hekimliği"), (260, "Kardiyoloji")]
        matched = handlers.find_matching_specialty(999, "Kardiyoloji", active_specs)
        self.assertEqual(matched, (260, "Kardiyoloji"))

    def test_matching_specialty_not_found(self):
        """Verify matching returns None when not present"""
        active_specs = [(208, "Aile Hekimliği")]
        matched = handlers.find_matching_specialty(260, "Kardiyoloji", active_specs)
        self.assertIsNone(matched)

class TestKeyboardsPagination(unittest.TestCase):

    @patch('keyboards.db.get_profile_specialties')
    def test_track_add_keyboard_pagination(self, mock_specs):
        mock_specs.return_value = [{'specialty_id': 208, 'specialty_name': 'Aile Hekimliği'}]

        # Page 0 (First page)
        kb_page0 = keyboards.get_track_add_keyboard(profile_id=1, page=0, page_size=8)
        self.assertIsNotNone(kb_page0)
        self.assertTrue(len(kb_page0.inline_keyboard) > 0)

        # Check navigation buttons row
        nav_row = [btn for row in kb_page0.inline_keyboard for btn in row if "1/" in btn.text]
        self.assertTrue(len(nav_row) > 0, "Page indicator should be present")

        # Check toggle prefix for tracked item (Aile Hekimliği is in page 0)
        buttons_text = [btn.text for row in kb_page0.inline_keyboard for btn in row]
        self.assertTrue(any("✅" in txt for txt in buttons_text), "Tracked specialty should have ✅ prefix")

    @patch('keyboards.db.get_profile_specialties')
    def test_track_add_keyboard_boundary_pages(self, mock_specs):
        mock_specs.return_value = []
        # Page index larger than max should clamp gracefully
        kb_clamped = keyboards.get_track_add_keyboard(profile_id=1, page=999, page_size=8)
        self.assertIsNotNone(kb_clamped)

if __name__ == '__main__':
    unittest.main()
