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

class TestSlotAlertView(unittest.TestCase):

    def setUp(self):
        self.alert_data = {
            'profile_id': 1,
            'profile_name': 'Ahmet Yılmaz',
            'tc_masked': '123***',
            'rtype_label': '🩺 Normal Randevu',
            'specialty_name': 'Kardiyoloji',
            'polyclinic_name': 'Kardiyoloji Polikliniği 1',
            'dates': ['15.10.2026', '16.10.2026'],
            'slots_by_date': {
                '15.10.2026': [
                    {'key': 'abc1', 'time': '09:00', 'slot_id': 's1'},
                    {'key': 'abc2', 'time': '09:30', 'slot_id': 's2'},
                    {'key': 'abc3', 'time': '10:00', 'slot_id': 's3'},
                    {'key': 'abc4', 'time': '10:30', 'slot_id': 's4'},
                    {'key': 'abc5', 'time': '11:00', 'slot_id': 's5'},
                    {'key': 'abc6', 'time': '11:30', 'slot_id': 's6'},
                    {'key': 'abc7', 'time': '13:00', 'slot_id': 's7'},
                    {'key': 'abc8', 'time': '13:30', 'slot_id': 's8'},
                ],
                '16.10.2026': [
                    {'key': 'abc9', 'time': '14:00', 'slot_id': 's9'},
                ]
            },
            'all_slots': [{'key': f'abc{i}', 'time': 'time', 'slot_id': f's{i}'} for i in range(1, 10)],
            'timestamp': 100000.0
        }

    def test_build_slot_alert_view_content(self):
        text, markup = handlers.build_slot_alert_view(self.alert_data, "testalert", date_idx=0, slot_page=0)
        self.assertIn("ADÜ BOŞ RANDEVU BİLDİRİMİ", text)
        self.assertIn("Ahmet Yılmaz", text)
        self.assertIn("15.10.2026", text)
        self.assertIn("Kardiyoloji Polikliniği 1", text)
        self.assertIsNotNone(markup)

    def test_build_slot_alert_view_pagination_controls(self):
        # 15.10.2026 has 8 slots, page size is 6 -> total_slot_pages = 2
        # dates has 2 dates -> date navigation present
        text, markup = handlers.build_slot_alert_view(self.alert_data, "testalert", date_idx=0, slot_page=0)
        buttons = [btn for row in markup.inline_keyboard for btn in row]
        
        # Check slot buttons on page 0: 6 slots
        slot_buttons = [b for b in buttons if b.callback_data.startswith("book:1:")]
        self.assertEqual(len(slot_buttons), 6)

        # Check time paging buttons
        time_nav = [b for b in buttons if "Saat" in b.text]
        self.assertTrue(len(time_nav) >= 2)

        # Check date paging buttons
        date_nav = [b for b in buttons if "Gün" in b.text]
        self.assertTrue(len(date_nav) >= 2)

        # Ensure all callback_data are <= 64 bytes
        for btn in buttons:
            self.assertLessEqual(len(btn.callback_data.encode('utf-8')), 64)

    def test_build_slot_alert_view_second_page(self):
        text, markup = handlers.build_slot_alert_view(self.alert_data, "testalert", date_idx=0, slot_page=1)
        buttons = [btn for row in markup.inline_keyboard for btn in row]
        slot_buttons = [b for b in buttons if b.callback_data.startswith("book:1:")]
        # Remaining 2 slots on page 1 (8 - 6 = 2)
        self.assertEqual(len(slot_buttons), 2)
        self.assertEqual(slot_buttons[0].text, "⚡️ 13:00 Al")
        self.assertEqual(slot_buttons[1].text, "⚡️ 13:30 Al")

    def test_build_slot_alert_view_second_date(self):
        text, markup = handlers.build_slot_alert_view(self.alert_data, "testalert", date_idx=1, slot_page=0)
        self.assertIn("16.10.2026", text)
        buttons = [btn for row in markup.inline_keyboard for btn in row]
        slot_buttons = [b for b in buttons if b.callback_data.startswith("book:1:")]
        self.assertEqual(len(slot_buttons), 1)
        self.assertEqual(slot_buttons[0].text, "⚡️ 14:00 Al")

    def test_build_slot_alert_view_empty_dates(self):
        text, markup = handlers.build_slot_alert_view({'dates': []}, "empty")
        self.assertIn("Randevu bulunamadı", text)
        self.assertEqual(len(markup.inline_keyboard), 0)

class TestCryptoModule(unittest.TestCase):

    def test_encrypt_decrypt_roundtrip(self):
        import crypto
        sample = "12345678901"
        enc = crypto.encrypt_text(sample)
        self.assertTrue(enc.startswith("enc:v1:"))
        self.assertNotEqual(enc, sample)
        dec = crypto.decrypt_text(enc)
        self.assertEqual(dec, sample)

    def test_decrypt_plaintext_fallback(self):
        import crypto
        plain = "05051234567"
        self.assertEqual(crypto.decrypt_text(plain), plain)

    def test_empty_string_handling(self):
        import crypto
        self.assertEqual(crypto.encrypt_text(""), "")
        self.assertEqual(crypto.decrypt_text(""), "")

class TestSlotFiltering(unittest.TestCase):

    def setUp(self):
        self.slots = [
            {'date': '15.10.2026', 'time': '09:30'},
            {'date': '15.10.2026', 'time': '14:30'},
            {'date': '20.10.2026', 'time': '10:00'},
        ]

    def test_filter_morning_only(self):
        res = handlers.filter_slots_for_profile(self.slots, filter_date_days=0, filter_time_pref=1)
        self.assertTrue(all(int(s['time'].split(':')[0]) < 12 for s in res))

    def test_filter_afternoon_only(self):
        res = handlers.filter_slots_for_profile(self.slots, filter_date_days=0, filter_time_pref=2)
        self.assertTrue(all(int(s['time'].split(':')[0]) >= 12 for s in res))

    def test_filter_no_preference(self):
        res = handlers.filter_slots_for_profile(self.slots, filter_date_days=0, filter_time_pref=0)
        self.assertEqual(len(res), len(self.slots))

class TestCalendarUtil(unittest.TestCase):

    def test_ics_generation(self):
        import calendar_util
        ics = calendar_util.generate_ics_calendar(
            specialty_name="Kardiyoloji",
            polyclinic_name="Poliklinik 1",
            patient_name="Ali Veli",
            date_str="15.10.2026",
            time_str="09:30"
        )
        self.assertIn(b"BEGIN:VCALENDAR", ics)
        self.assertIn(b"SUMMARY:AD\xc3\x9c Randevusu: Kardiyoloji", ics)
        self.assertIn(b"END:VCALENDAR", ics)

    def test_google_calendar_url(self):
        import calendar_util
        url = calendar_util.generate_google_calendar_url(
            specialty_name="Kardiyoloji",
            polyclinic_name="Poliklinik 1",
            patient_name="Ali Veli",
            date_str="15.10.2026",
            time_str="09:30"
        )
        self.assertIn("calendar.google.com", url)
        self.assertIn("Kardiyoloji", url)

class TestDNDLogic(unittest.TestCase):

    def test_dnd_disabled(self):
        user = {'dnd_enabled': 0}
        self.assertFalse(handlers.is_in_dnd(user))

    def test_dnd_active(self):
        # Window that covers all 24 hours: start=0, end=24
        user = {'dnd_enabled': 1, 'dnd_start': 0, 'dnd_end': 24}
        self.assertTrue(handlers.is_in_dnd(user))

class TestKeyboardsPreferences(unittest.TestCase):

    @patch('keyboards.db.get_profile_by_id')
    def test_profile_prefs_keyboard(self, mock_profile):
        mock_profile.return_value = {
            'id': 1,
            'name': 'Ali',
            'auto_book': 1,
            'filter_date_days': 7,
            'filter_time_pref': 1
        }
        kb = keyboards.get_profile_prefs_keyboard(1)
        self.assertIsNotNone(kb)
        buttons_text = [btn.text for row in kb.inline_keyboard for btn in row]
        self.assertTrue(any("Sniper" in txt and "AÇIK" in txt for txt in buttons_text))
        self.assertTrue(any("7 Gün" in txt for txt in buttons_text))

    def test_admin_keyboard_metrics(self):
        kb = keyboards.get_admin_keyboard()
        buttons_text = [btn.text for row in kb.inline_keyboard for btn in row]
        self.assertTrue(any("Sistem Metrikleri" in txt for txt in buttons_text))

if __name__ == '__main__':
    unittest.main()

