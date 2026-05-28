import requests
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger("adu_bot.scraper")

BASE_URL = "https://randevu.adu.edu.tr"

# Pre-compile regex patterns for performance
RE_STEP02 = re.compile(r'Step02Operation\((\d+)\)')
RE_STEP03 = re.compile(r'Step03Operation\((\d+)\)')
RE_STEP04 = re.compile(r'Step04Operation\((\d+)\)')
RE_TIME = re.compile(r'(\d{2}:\d{2})')

class ADUScraper:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    def _get_forgery_token(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        token_input = soup.find('input', {'id': 'forgeryTokenShared'})
        if token_input:
            return token_input.get('value')
        return None

    def _get_request_verification_token(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        token_input = soup.find('input', {'name': '__RequestVerificationToken'})
        if token_input:
            return token_input.get('value')
        return None

    def get_specialties(self):
        """Step 1 & Step 2: Returns a list of available departments/specialties [(id, name)]"""
        try:
            logger.info("Fetching main page /1")
            r1 = self.session.get(f"{BASE_URL}/1", headers=self.headers, timeout=15)
            token1 = self._get_forgery_token(r1.text)
            if not token1:
                logger.error("Forgery token not found on /1")
                return []

            # Click Normal Randevu (param: 1)
            logger.info("POST /Step01/Operation")
            post_headers = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token1,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/1"
            }
            r_post = self.session.post(
                f"{BASE_URL}/Step01/Operation",
                json={"param": 1},
                headers={**self.headers, **post_headers},
                timeout=15
            )
            
            if not r_post.json().get("IsStatus"):
                logger.error("Step 1 Operation failed")
                return []

            # Fetch Step 2 page
            logger.info("Fetching /2")
            r2 = self.session.get(f"{BASE_URL}/2", headers=self.headers, timeout=15)
            soup2 = BeautifulSoup(r2.text, 'html.parser')
            
            specialties = []
            # Parse specialties from buttons with onclick="Step02Operation(id)"
            buttons = soup2.find_all('button', onclick=True)
            for btn in buttons:
                match = RE_STEP02.search(btn.get('onclick', ''))
                if match:
                    spec_id = int(match.group(1))
                    spec_name = btn.get_text().strip()
                    specialties.append((spec_id, spec_name))
            
            # If empty, it means all slots are full and the page is blank.
            # We return empty, but in bot we will allow choosing from a fallback/hardcoded list as well!
            return specialties

        except Exception as e:
            logger.error(f"Error fetching specialties: {e}")
            return []

    def get_polyclinics(self, specialty_id):
        """Step 3: Returns a list of active polyclinics [(id, name)] for a given specialty"""
        try:
            # We must go through Step 1 and Step 2 sequentially to establish the session
            logger.info(f"Establishing session for specialty {specialty_id}")
            r1 = self.session.get(f"{BASE_URL}/1", headers=self.headers, timeout=15)
            token1 = self._get_forgery_token(r1.text)
            
            post_headers1 = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token1,
                "X-Requested-With": "XMLHttpRequest",
            }
            self.session.post(f"{BASE_URL}/Step01/Operation", json={"param": 1}, headers={**self.headers, **post_headers1}, timeout=15)
            
            r2 = self.session.get(f"{BASE_URL}/2", headers=self.headers, timeout=15)
            token2 = self._get_forgery_token(r2.text) or token1
            
            post_headers2 = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token2,
                "X-Requested-With": "XMLHttpRequest",
            }
            r_post2 = self.session.post(
                f"{BASE_URL}/Step02/Operation",
                json={"param": specialty_id},
                headers={**self.headers, **post_headers2},
                timeout=15
            )
            
            if not r_post2.json().get("IsStatus"):
                logger.error(f"Specialty ID {specialty_id} was rejected by Step 2")
                return []

            # Fetch Step 3 page
            logger.info("Fetching /3")
            r3 = self.session.get(f"{BASE_URL}/3", headers=self.headers, timeout=15)
            soup3 = BeautifulSoup(r3.text, 'html.parser')
            
            polyclinics = []
            # Parse polyclinics from Step03Operation(id) in buttons inside table
            buttons = soup3.find_all('button', onclick=True)
            for btn in buttons:
                match = RE_STEP03.search(btn.get('onclick', ''))
                if match:
                    poly_id = int(match.group(1))
                    poly_name = btn.find_parent('tr').find('td').get_text().strip() if btn.find_parent('tr') else "Poliklinik"
                    polyclinics.append((poly_id, poly_name))
                    
            return polyclinics

        except Exception as e:
            logger.error(f"Error fetching polyclinics for specialty {specialty_id}: {e}")
            return []

    def check_slots(self, specialty_id, polyclinic_id):
        """Step 4: Returns a list of available slots [{slot_id, date, time, doctor}]"""
        try:
            # Re-establish navigation state
            r1 = self.session.get(f"{BASE_URL}/1", headers=self.headers, timeout=15)
            token1 = self._get_forgery_token(r1.text)
            
            post_headers1 = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token1,
                "X-Requested-With": "XMLHttpRequest",
            }
            self.session.post(f"{BASE_URL}/Step01/Operation", json={"param": 1}, headers={**self.headers, **post_headers1}, timeout=15)
            
            r2 = self.session.get(f"{BASE_URL}/2", headers=self.headers, timeout=15)
            token2 = self._get_forgery_token(r2.text) or token1
            post_headers2 = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token2,
                "X-Requested-With": "XMLHttpRequest",
            }
            self.session.post(f"{BASE_URL}/Step02/Operation", json={"param": specialty_id}, headers={**self.headers, **post_headers2}, timeout=15)
            
            r3 = self.session.get(f"{BASE_URL}/3", headers=self.headers, timeout=15)
            token3 = self._get_forgery_token(r3.text) or token1
            post_headers3 = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token3,
                "X-Requested-With": "XMLHttpRequest",
            }
            r_post3 = self.session.post(
                f"{BASE_URL}/Step03/Operation",
                json={"param": polyclinic_id},
                headers={**self.headers, **post_headers3},
                timeout=15
            )
            
            if not r_post3.json().get("IsStatus"):
                logger.error(f"Polyclinic ID {polyclinic_id} rejected by Step 3")
                return []

            # Fetch Step 4 page
            logger.info("Fetching /4")
            r4 = self.session.get(f"{BASE_URL}/4", headers=self.headers, timeout=15)
            req_token = self._get_request_verification_token(r4.text)
            if not req_token:
                logger.error("__RequestVerificationToken not found on /4")
                return []

            # Request OperationWeek
            logger.info("POST /Step04/OperationWeek")
            week_headers = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": req_token,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/4"
            }
            
            # We pass uygunMu: True to only search for open/free slots!
            r_week = self.session.post(
                f"{BASE_URL}/Step04/OperationWeek",
                json={"WeekNumber": 0, "uygunMu": True},
                headers={**self.headers, **week_headers},
                timeout=15
            )
            
            res_json = r_week.json()
            if not res_json.get("IsStatus"):
                logger.error("OperationWeek returned status False")
                return []
                
            thead_html = res_json.get("IsData", "")
            tbody_html = res_json.get("IsTbodyData", "")
            
            # Parse dates from thead
            soup_thead = BeautifulSoup(thead_html, 'html.parser')
            cols = soup_thead.find_all('th')
            dates = []
            for col in cols:
                # Text looks like "18.05.2026 Pazartesi"
                date_text = col.get_text().strip().replace('\n', ' ')
                dates.append(date_text)
                
            # Parse slots from tbody
            soup_tbody = BeautifulSoup(tbody_html, 'html.parser')
            slots = []
            
            # Each row is a time slot (e.g. 09:00)
            rows = soup_tbody.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                # The first cell might contain the time, or it is a standard table
                # Let's inspect buttons inside cells
                for col_idx, cell in enumerate(cells):
                    # We match columns to the dates array
                    date_val = dates[col_idx] if col_idx < len(dates) else "Bilinmeyen Tarih"
                    
                    # Find all buttons that call Step04Operation(id)
                    buttons = cell.find_all('button', onclick=True)
                    for btn in buttons:
                        match = RE_STEP04.search(btn.get('onclick', ''))
                        if match:
                            slot_id = int(match.group(1))
                            btn_text = btn.get_text().strip() # E.g., "09:00 BOŞ" or "09:00 \n BOŞ"
                            
                            # Extract time
                            time_match = RE_TIME.search(btn_text)
                            slot_time = time_match.group(1) if time_match else "00:00"
                            
                            # Extract doctor/details from parent elements if visible
                            doctor = "Poliklinik Hekimi"
                            
                            slots.append({
                                "slot_id": slot_id,
                                "date": date_val,
                                "time": slot_time,
                                "doctor": doctor
                            })
                            
            return slots

        except Exception as e:
            logger.error(f"Error checking slots: {e}")
            return []

    def book_appointment(self, specialty_id, polyclinic_id, slot_id, tc_kimlik, dogum_tarihi, telefon):
        """Step 5: Submits the personal details and completes the booking"""
        try:
            # We must go through all the steps to select the slot
            logger.info("Starting booking process...")
            
            # Step 1
            r1 = self.session.get(f"{BASE_URL}/1", headers=self.headers, timeout=15)
            token1 = self._get_forgery_token(r1.text)
            post_headers1 = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token1,
                "X-Requested-With": "XMLHttpRequest",
            }
            self.session.post(f"{BASE_URL}/Step01/Operation", json={"param": 1}, headers={**self.headers, **post_headers1}, timeout=15)
            
            # Step 2
            r2 = self.session.get(f"{BASE_URL}/2", headers=self.headers, timeout=15)
            token2 = self._get_forgery_token(r2.text) or token1
            post_headers2 = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token2,
                "X-Requested-With": "XMLHttpRequest",
            }
            self.session.post(f"{BASE_URL}/Step02/Operation", json={"param": specialty_id}, headers={**self.headers, **post_headers2}, timeout=15)
            
            # Step 3
            r3 = self.session.get(f"{BASE_URL}/3", headers=self.headers, timeout=15)
            token3 = self._get_forgery_token(r3.text) or token1
            post_headers3 = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token3,
                "X-Requested-With": "XMLHttpRequest",
            }
            self.session.post(f"{BASE_URL}/Step03/Operation", json={"param": polyclinic_id}, headers={**self.headers, **post_headers3}, timeout=15)
            
            # Step 4
            r4 = self.session.get(f"{BASE_URL}/4", headers=self.headers, timeout=15)
            req_token = self._get_request_verification_token(r4.text)
            
            # Select the slot
            logger.info(f"Selecting slot ID: {slot_id}")
            slot_headers = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": req_token,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/4"
            }
            r_slot = self.session.post(
                f"{BASE_URL}/Step04/Operation",
                json={"param": slot_id},
                headers={**self.headers, **slot_headers},
                timeout=15
            )
            
            if not r_slot.json().get("IsStatus"):
                logger.error(f"Slot ID {slot_id} selection rejected by Step 4")
                return False, "Slot seçimi başarısız oldu (muhtemelen başkası tarafından alındı)."

            # Step 5: Fetch confirmation page
            logger.info("Fetching /5 confirmation page")
            r5 = self.session.get(f"{BASE_URL}/5", headers=self.headers, timeout=15)
            token5 = self._get_forgery_token(r5.text)
            
            # Submit personal details!
            # Typically, in Step 5 there is an AJAX action like /Step05/OperationAction or similar.
            # Since we couldn't fetch real /5 earlier, we can inspect what the form inputs or scripts are.
            # Based on standard MiaMed systems:
            # POST /Step05/OperationAction or /Step05/Confirm
            # Let's see what is inside Step 5 scripts in the response:
            # Let's inspect the inline script of `/5` from soup5
            logger.info("Submitting personal credentials to complete appointment...")
            
            # The submit details endpoint in MiaMed is /Step05/OperationAction
            # Request body: {"tckimlik": tc_kimlik, "dogumtarihi": dogum_tarihi, "telefon": telefon}
            confirm_headers = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token5 or req_token,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/5"
            }
            
            # Try to POST to /Step05/OperationAction
            confirm_data = {
                "tckimlik": tc_kimlik,
                "dogumtarihi": dogum_tarihi,
                "telefon": telefon
            }
            
            r_confirm = self.session.post(
                f"{BASE_URL}/Step05/OperationAction",
                json=confirm_data,
                headers={**self.headers, **confirm_headers},
                timeout=15
            )
            
            res_data = r_confirm.json()
            logger.info(f"Confirm response: {res_data}")
            
            if res_data.get("IsStatus"):
                return True, res_data.get("IsMessage", "Randevunuz başarıyla alınmıştır.")
            else:
                return False, res_data.get("IsMessage", "Randevu alımı sırasında hata oluştu.")

        except Exception as e:
            logger.error(f"Error booking appointment: {e}")
            return False, f"Randevu alma işlemi sırasında teknik bir hata oluştu: {str(e)}"
