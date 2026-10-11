import requests
from bs4 import BeautifulSoup
import re
import logging
import config

logger = logging.getLogger("adu_bot.scraper")

BASE_URL = "https://randevu.adu.edu.tr"

# Regex patterns matching actual MiaMed / ADU online randevu HTML & JS
RE_STEP02 = re.compile(r'Step02Operation\((-?\d+)\)')
RE_STEP03 = re.compile(r'Step03Operation\((\d+)\)')
RE_STEP04 = re.compile(r'Step04Operation\([\"\'](.*?)[\"\']\)')
RE_STEP05 = re.compile(r'Step05Operation\([\"\'](.*?)[\"\']\)')
RE_TIME = re.compile(r'(\d{2}:\d{2}(?:\s*-\s*\d{2}:\d{2})?)')

class ADUScraper:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    def _reset_session(self):
        """Creates a fresh session to prevent state leakage between multi-step operations"""
        self.session = requests.Session()

    def _get_forgery_token(self, html):
        """Extracts forgery token from #forgeryTokenShared"""
        soup = BeautifulSoup(html, 'html.parser')
        token_input = soup.find('input', {'id': 'forgeryTokenShared'})
        if token_input:
            return token_input.get('value')
        return None

    def _get_request_verification_token(self, html):
        """Extracts __RequestVerificationToken or falls back to forgeryTokenShared"""
        soup = BeautifulSoup(html, 'html.parser')
        token_input = soup.find('input', {'name': '__RequestVerificationToken'})
        if token_input:
            return token_input.get('value')
        return self._get_forgery_token(html)

    def get_specialties(self, randevu_type=1):
        """Step 1 & Step 2: Returns list of available active departments [(spec_id, spec_name)].
        randevu_type: 1 = Normal Randevu, 2 = Özel Öğretim Üyesi Randevusu"""
        self._reset_session()
        try:
            type_label = "Özel Öğretim Üyesi" if int(randevu_type) == 2 else "Normal Randevu"
            logger.info(f"Fetching specialties for {type_label} (type={randevu_type})...")
            
            r1 = self.session.get(f"{BASE_URL}/1", headers=self.headers, timeout=15)
            token1 = self._get_forgery_token(r1.text)
            if not token1:
                logger.error("Forgery token not found on /1")
                return []

            # Step 1: Select randevu_type (1: Normal, 2: Özel Öğretim Üyesi)
            post_headers = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token1,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/1"
            }
            r_post = self.session.post(
                f"{BASE_URL}/Step01/Operation",
                json={"param": int(randevu_type)},
                headers={**self.headers, **post_headers},
                timeout=15
            )

            res_op1 = r_post.json() if r_post.text else {}
            if not res_op1.get("IsStatus"):
                logger.error(f"Step 1 Operation failed for randevu_type={randevu_type}")
                return []

            # Step 2: Fetch /2
            r2 = self.session.get(f"{BASE_URL}/2", headers=self.headers, timeout=15)
            soup2 = BeautifulSoup(r2.text, 'html.parser')

            specialties = []
            seen_ids = set()

            # Find all elements (a or button) with Step02Operation(id)
            for el in soup2.find_all(attrs={'onclick': RE_STEP02}):
                onclick = el.get('onclick', '')
                match = RE_STEP02.search(onclick)
                if match:
                    spec_id = int(match.group(1))
                    if spec_id in seen_ids:
                        continue
                    seen_ids.add(spec_id)

                    # Lookup canonical Turkish name from config
                    spec_name = config.ADU_DEPARTMENTS.get(spec_id)
                    if not spec_name:
                        el_text = el.get_text(strip=True)
                        spec_name = el_text if el_text else f"Uzmanlık ({spec_id})"

                    specialties.append((spec_id, spec_name))

            logger.info(f"Retrieved {len(specialties)} active specialties for randevu_type={randevu_type}.")
            return specialties

        except Exception as e:
            logger.error(f"Error fetching specialties (type={randevu_type}): {e}", exc_info=True)
            return []

    def get_polyclinics(self, specialty_id, randevu_type=1):
        """Step 3: Returns list of active polyclinics [{'id': poly_id, 'name': poly_name}] for a given specialty"""
        self._reset_session()
        try:
            logger.info(f"Navigating to polyclinics for specialty={specialty_id}, type={randevu_type}")
            r1 = self.session.get(f"{BASE_URL}/1", headers=self.headers, timeout=15)
            token1 = self._get_forgery_token(r1.text)
            if not token1:
                return []

            post_headers1 = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token1,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/1"
            }
            self.session.post(f"{BASE_URL}/Step01/Operation", json={"param": int(randevu_type)}, headers={**self.headers, **post_headers1}, timeout=15)

            # Step 2: Select specialty
            post_headers2 = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token1,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/2"
            }
            r_post2 = self.session.post(
                f"{BASE_URL}/Step02/Operation",
                json={"param": int(specialty_id)},
                headers={**self.headers, **post_headers2},
                timeout=15
            )

            res_op2 = r_post2.json() if r_post2.text else {}
            if not res_op2.get("IsStatus"):
                logger.error(f"Specialty ID {specialty_id} was rejected by Step 2")
                return []

            # Step 3: Fetch /3
            r3 = self.session.get(f"{BASE_URL}/3", headers=self.headers, timeout=15)
            soup3 = BeautifulSoup(r3.text, 'html.parser')

            polyclinics = []
            for tr in soup3.find_all('tr'):
                tds = tr.find_all('td')
                if not tds:
                    continue

                poly_name = tds[0].get_text(strip=True)
                # Check for active appointment button with Step03Operation
                action_el = tds[1].find(attrs={'onclick': RE_STEP03}) if len(tds) > 1 else tr.find(attrs={'onclick': RE_STEP03})
                if action_el:
                    match = RE_STEP03.search(action_el.get('onclick', ''))
                    if match:
                        poly_id = int(match.group(1))
                        polyclinics.append({
                            "id": poly_id,
                            "name": poly_name
                        })

            logger.info(f"Retrieved {len(polyclinics)} active polyclinics for specialty={specialty_id}, type={randevu_type}.")
            return polyclinics

        except Exception as e:
            logger.error(f"Error fetching polyclinics for specialty {specialty_id}: {e}", exc_info=True)
            return []

    def check_slots(self, specialty_id, polyclinic_id, randevu_type=1):
        """Step 4: Returns list of available appointment slots [{'slot_id': slot_token, 'date': date, 'time': time, 'doctor': doctor}]"""
        self._reset_session()
        try:
            # Step 1
            r1 = self.session.get(f"{BASE_URL}/1", headers=self.headers, timeout=15)
            token1 = self._get_forgery_token(r1.text)
            if not token1:
                return []

            post_headers1 = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token1,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/1"
            }
            self.session.post(f"{BASE_URL}/Step01/Operation", json={"param": int(randevu_type)}, headers={**self.headers, **post_headers1}, timeout=15)

            # Step 2
            post_headers2 = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token1,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/2"
            }
            r_post2 = self.session.post(f"{BASE_URL}/Step02/Operation", json={"param": int(specialty_id)}, headers={**self.headers, **post_headers2}, timeout=15)
            if not (r_post2.json() if r_post2.text else {}).get("IsStatus"):
                return []

            # Step 3
            post_headers3 = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token1,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/3"
            }
            r_post3 = self.session.post(f"{BASE_URL}/Step03/Operation", json={"param": int(polyclinic_id)}, headers={**self.headers, **post_headers3}, timeout=15)
            if not (r_post3.json() if r_post3.text else {}).get("IsStatus"):
                return []

            # Step 4: GET /4
            r4 = self.session.get(f"{BASE_URL}/4", headers=self.headers, timeout=15)
            req_token = self._get_request_verification_token(r4.text) or token1

            week_headers = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": req_token,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/4"
            }

            # Query available days (uygunMu: True jumps directly to available days)
            r_week = self.session.post(
                f"{BASE_URL}/Step04/OperationWeek",
                json={"WeekNumber": 0, "uygunMu": True},
                headers={**self.headers, **week_headers},
                timeout=15
            )

            res_json = r_week.json() if r_week.text else {}
            if not res_json.get("IsStatus"):
                # Fallback to current week without uygunMu filter
                r_week = self.session.post(
                    f"{BASE_URL}/Step04/OperationWeek",
                    json={"WeekNumber": 0, "uygunMu": False},
                    headers={**self.headers, **week_headers},
                    timeout=15
                )
                res_json = r_week.json() if r_week.text else {}

            if not res_json.get("IsStatus"):
                return []

            thead_html = res_json.get("IsData", "")
            tbody_html = res_json.get("IsTbodyData", "")

            # Parse dates from thead
            thead_soup = BeautifulSoup(thead_html, 'html.parser')
            dates = [th.get_text(strip=True, separator=' ') for th in thead_soup.find_all('th')]

            # In MiaMed Step 4, IsTbodyData contains top-level <td> elements, one per date column
            tbody_soup = BeautifulSoup(tbody_html, 'html.parser')
            day_tds = [c for c in tbody_soup.children if getattr(c, 'name', None) == 'td']
            if not day_tds:
                day_tds = tbody_soup.find_all('td', style=lambda s: s and 'vertical-align:top' in s)
            if not day_tds:
                day_tds = tbody_soup.find_all('td', recursive=False)

            slots = []
            for col_idx, day_td in enumerate(day_tds):
                date_val = dates[col_idx] if col_idx < len(dates) else "Bilinmeyen Tarih"
                for el in day_td.find_all(['a', 'button'], onclick=True):
                    onclick = el.get('onclick', '')
                    m = RE_STEP04.search(onclick)
                    if m:
                        slot_param = m.group(1)
                        btn_text = el.get_text(strip=True)
                        time_match = RE_TIME.search(btn_text)
                        slot_time = time_match.group(1) if time_match else btn_text

                        slots.append({
                            "slot_id": slot_param,
                            "date": date_val,
                            "time": slot_time,
                            "doctor": "Poliklinik Hekimi"
                        })

            logger.info(f"Retrieved {len(slots)} free slots for polyclinic {polyclinic_id} (type={randevu_type}).")
            return slots

        except Exception as e:
            logger.error(f"Error checking slots: {e}", exc_info=True)
            return []

    def book_appointment(self, specialty_id, polyclinic_id, slot_id, tc_kimlik, dogum_tarihi, telefon, randevu_type=1):
        """Step 5: Submits personal details and completes the appointment reservation"""
        self._reset_session()
        try:
            logger.info(f"Starting booking reservation for specialty={specialty_id}, polyclinic={polyclinic_id}, type={randevu_type}...")

            # Step 1
            r1 = self.session.get(f"{BASE_URL}/1", headers=self.headers, timeout=15)
            token1 = self._get_forgery_token(r1.text)
            if not token1:
                return False, "Sistem güvenlik belirteci (token) alınamadı."

            post_headers1 = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token1,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/1"
            }
            self.session.post(f"{BASE_URL}/Step01/Operation", json={"param": int(randevu_type)}, headers={**self.headers, **post_headers1}, timeout=15)

            # Step 2
            post_headers2 = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token1,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/2"
            }
            self.session.post(f"{BASE_URL}/Step02/Operation", json={"param": int(specialty_id)}, headers={**self.headers, **post_headers2}, timeout=15)

            # Step 3
            post_headers3 = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token1,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/3"
            }
            self.session.post(f"{BASE_URL}/Step03/Operation", json={"param": int(polyclinic_id)}, headers={**self.headers, **post_headers3}, timeout=15)

            # Step 4
            r4 = self.session.get(f"{BASE_URL}/4", headers=self.headers, timeout=15)
            req_token = self._get_request_verification_token(r4.text) or token1

            # Select slot in Step 4
            slot_headers = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": req_token,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/4"
            }
            r_slot = self.session.post(
                f"{BASE_URL}/Step04/Operation",
                json={"param": str(slot_id)},
                headers={**self.headers, **slot_headers},
                timeout=15
            )

            res_slot = r_slot.json() if r_slot.text else {}
            if not res_slot.get("IsStatus"):
                logger.error(f"Slot selection rejected: {res_slot}")
                return False, "Slot seçimi başarısız oldu (muhtemelen bu randevu başkası tarafından alındı)."

            # Step 5: GET /5
            r5 = self.session.get(f"{BASE_URL}/5", headers=self.headers, timeout=15)
            token5 = self._get_forgery_token(r5.text) or req_token

            # Extract dynamic security cookie parameter from Step05 button
            m = RE_STEP05.search(r5.text)
            cookie_param = m.group(1) if m else ""

            # Prepare confirmation payload
            confirm_headers = {
                "Content-Type": "application/json; charset=utf-8",
                "VerificationToken": token5,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/5"
            }

            confirm_data = {
                "tckimlik": str(tc_kimlik).strip(),
                "dogumtarihi": str(dogum_tarihi).strip(),
                "cookie": cookie_param,
                "ceptel": str(telefon).strip()
            }

            logger.info(f"Submitting personal details to /Step05/Operation (type={randevu_type})...")
            r_confirm = self.session.post(
                f"{BASE_URL}/Step05/Operation",
                json=confirm_data,
                headers={**self.headers, **confirm_headers},
                timeout=15
            )

            res_data = r_confirm.json() if r_confirm.text else {}
            logger.info(f"Confirm response: {res_data}")

            if res_data.get("IsStatus"):
                return True, res_data.get("IsMessage", "Randevunuz başarıyla onaylanıp alınmıştır.")
            else:
                return False, res_data.get("IsMessage", "Randevu alımı sırasında hastane hatası oluştu.")

        except Exception as e:
            logger.error(f"Error booking appointment: {e}", exc_info=True)
            return False, f"Randevu alma işlemi sırasında hata oluştu: {str(e)}"
