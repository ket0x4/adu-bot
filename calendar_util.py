import datetime
import urllib.parse
import re
import uuid

def parse_appointment_datetime(date_str: str, time_str: str):
    """Parses Turkish hospital appointment date and time strings into UTC start and end datetimes.
    Assumes Turkish timezone (UTC+3 / Europe/Istanbul).
    """
    m_date = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', str(date_str))
    m_time = re.search(r'(\d{2}):(\d{2})', str(time_str))
    
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if not m_date or not m_time:
        return now_utc, now_utc + datetime.timedelta(minutes=30)
        
    day, month, year = map(int, m_date.groups())
    hour, minute = map(int, m_time.groups())
    
    # Turkey standard time is UTC+3
    tz_tr = datetime.timezone(datetime.timedelta(hours=3))
    try:
        dt_local = datetime.datetime(year, month, day, hour, minute, tzinfo=tz_tr)
        dt_utc_start = dt_local.astimezone(datetime.timezone.utc)
        dt_utc_end = dt_utc_start + datetime.timedelta(minutes=30)
        return dt_utc_start, dt_utc_end
    except Exception:
        return now_utc, now_utc + datetime.timedelta(minutes=30)

def generate_ics_calendar(
    specialty_name: str,
    polyclinic_name: str,
    patient_name: str,
    date_str: str,
    time_str: str,
    rtype_label: str = "ADÜ Hastane Randevusu"
) -> bytes:
    """Generates an iCalendar (.ics) file as UTF-8 encoded bytes."""
    start_utc, end_utc = parse_appointment_datetime(date_str, time_str)
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    
    dtstamp = now_utc.strftime("%Y%m%dT%H%M%SZ")
    dtstart = start_utc.strftime("%Y%m%dT%H%M%SZ")
    dtend = end_utc.strftime("%Y%m%dT%H%M%SZ")
    event_uid = f"adu-{uuid.uuid4().hex[:12]}@randevu.adu.edu.tr"
    
    summary = f"ADÜ Randevusu: {specialty_name}"
    description = (
        f"Hasta: {patient_name}\\n"
        f"Bölüm: {specialty_name}\\n"
        f"Poliklinik/Hekim: {polyclinic_name}\\n"
        f"Tür: {rtype_label}\\n"
        f"Randevu Saati: {time_str}\\n"
        f"Tarih: {date_str}"
    )
    location = "Aydın Adnan Menderes Üniversitesi Uygulama ve Araştırma Hastanesi, Efeler/Aydın"
    
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ADU Bot//TR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{event_uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        f"LOCATION:{location}",
        "STATUS:CONFIRMED",
        "BEGIN:VALARM",
        "TRIGGER:-PT2H",
        "ACTION:DISPLAY",
        "DESCRIPTION:Randevunuza 2 saat kaldı!",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR"
    ]
    
    return "\r\n".join(ics_lines).encode("utf-8")

def generate_google_calendar_url(
    specialty_name: str,
    polyclinic_name: str,
    patient_name: str,
    date_str: str,
    time_str: str,
    rtype_label: str = "ADÜ Hastane Randevusu"
) -> str:
    """Generates a direct Google Calendar appointment creation URL."""
    start_utc, end_utc = parse_appointment_datetime(date_str, time_str)
    
    title = f"ADÜ Randevusu - {specialty_name}"
    details = (
        f"Hasta: {patient_name}\n"
        f"Bölüm: {specialty_name}\n"
        f"Poliklinik/Hekim: {polyclinic_name}\n"
        f"Randevu Türü: {rtype_label}\n"
        f"Tarih & Saat: {date_str} {time_str}\n"
        f"ADÜ Hastane Randevu Takip Botu tarafından oluşturuldu."
    )
    location = "Aydın Adnan Menderes Üniversitesi Hastanesi, Aydın"
    
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{start_utc.strftime('%Y%m%dT%H%M%SZ')}/{end_utc.strftime('%Y%m%dT%H%M%SZ')}",
        "details": details,
        "location": location
    }
    return f"https://calendar.google.com/calendar/render?{urllib.parse.urlencode(params)}"
