import unittest
from unittest.mock import patch
import handlers

class TestCheckAuth(unittest.TestCase):

    @patch('handlers.db')
    @patch('handlers.config')
    def test_check_auth_admin(self, mock_config, mock_db):
        # Scenario 1: chat_id matches config.ADMIN_CHAT_ID
        # The function should automatically authorize the admin
        mock_config.ADMIN_CHAT_ID = "12345"
        chat_id = 12345

        result = handlers.check_auth(chat_id)

        self.assertTrue(result)
        mock_db.ensure_user_exists.assert_called_once_with("12345")
        mock_db.set_user_authorized.assert_called_once_with("12345", True)

    @patch('handlers.db')
    @patch('handlers.config')
    def test_check_auth_authorized_user(self, mock_config, mock_db):
        # Scenario 2: chat_id does not match config.ADMIN_CHAT_ID and user is authorized in DB
        mock_config.ADMIN_CHAT_ID = "12345"
        chat_id = 67890
        mock_db.get_user.return_value = {'chat_id': '67890', 'is_authorized': 1}

        result = handlers.check_auth(chat_id)

        self.assertTrue(result)
        mock_db.get_user.assert_called_once_with("67890")

    @patch('handlers.db')
    @patch('handlers.config')
    def test_check_auth_unauthorized_user(self, mock_config, mock_db):
        # Scenario 3: chat_id does not match config.ADMIN_CHAT_ID and user is NOT authorized in DB
        mock_config.ADMIN_CHAT_ID = "12345"
        chat_id = 67890
        mock_db.get_user.return_value = {'chat_id': '67890', 'is_authorized': 0}

        result = handlers.check_auth(chat_id)

        self.assertFalse(result)
        mock_db.get_user.assert_called_once_with("67890")

    @patch('handlers.db')
    @patch('handlers.config')
    def test_check_auth_nonexistent_user(self, mock_config, mock_db):
        # Scenario 4: chat_id does not match config.ADMIN_CHAT_ID and user does not exist in DB
        mock_config.ADMIN_CHAT_ID = "12345"
        chat_id = 67890
        mock_db.get_user.return_value = None

        result = handlers.check_auth(chat_id)

        self.assertFalse(result)
        mock_db.get_user.assert_called_once_with("67890")

    @patch('handlers.db')
    @patch('handlers.config')
    def test_check_auth_missing_authorized_key(self, mock_config, mock_db):
        # Scenario 5: User exists but is_authorized key is missing.
        # handlers.py uses .get('is_authorized', 0) which avoids KeyError.
        mock_config.ADMIN_CHAT_ID = "12345"
        chat_id = 67890
        mock_db.get_user.return_value = {'chat_id': '67890'}

        result = handlers.check_auth(chat_id)

        self.assertFalse(result)
        mock_db.get_user.assert_called_once_with("67890")

    @patch('handlers.db')
    @patch('handlers.config')
    def test_check_auth_no_admin_config(self, mock_config, mock_db):
        # Scenario 6: config.ADMIN_CHAT_ID is None
        mock_config.ADMIN_CHAT_ID = None
        chat_id = 67890
        mock_db.get_user.return_value = {'chat_id': '67890', 'is_authorized': 1}

        result = handlers.check_auth(chat_id)

        self.assertTrue(result)
        mock_db.get_user.assert_called_once_with("67890")

if __name__ == '__main__':
    unittest.main()
