from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = "http://127.0.0.1:8000"
BEA_URL = "https://www.bea.gov/news/schedule"
FED_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
CENSUS_URL = "https://www.census.gov/economic-indicators/calendar-listview.html"
FMP_URL = "https://financialmodelingprep.com/stable/economic-calendar"
SP500_WEIGHTS_URL = "https://www.slickcharts.com/sp500"
FOREX_FACTORY_URL = "https://www.forexfactory.com/calendar"
TIMEOUT = 20


class BeaScheduleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.year = date.today().year
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.events: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "th":
            self.cell = []
        elif tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.row is not None and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "th" and self.cell is not None:
            heading = " ".join("".join(self.cell).split())
            match = re.search(r"Year\s+(\d{4})", heading)
            if match:
                self.year = int(match.group(1))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.add_row(self.row)
            self.row = None

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def add_row(self, cells: list[str]) -> None:
        if len(cells) < 3:
            return
        date_match = re.search(r"([A-Za-z]+)\s+(\d{1,2})\s+(\d{1,2}:\d{2}\s+[AP]M)", cells[0])
        title = cells[-1].strip()
        if not date_match or not title:
            return
        try:
            month = date_match.group(1)
            day = int(date_match.group(2))
            event_date = date(self.year, datetime.strptime(month, "%B").month, day)
        except ValueError:
            return
        category = "inflation" if "personal income and outlays" in title.lower() else "econ"
        if not any(term in title.lower() for term in ("gdp", "personal income and outlays", "international trade")):
            return
        if category == "inflation":
            title += " (includes PCE and Core PCE)"
        self.events.append({
            "date": event_date.isoformat(),
            "time": date_match.group(3),
            "title": title,
            "category": category,
            "impact": "high" if category == "inflation" or "gdp" in title.lower() else "medium",
            "description": "Scheduled release from the U.S. Bureau of Economic Analysis.",
            "source": BEA_URL,
            "timeZone": "America/New_York",
        })


class CensusRetailParser(HTMLParser):
    def __init__(self, source_url: str) -> None:
        super().__init__()
        self.source_url = source_url
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.events: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.row is not None and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.add_row(self.row)
            self.row = None

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def add_row(self, cells: list[str]) -> None:
        if len(cells) < 3 or "advance monthly sales for retail and food services" not in cells[0].lower():
            return
        date_text = re.search(r"([A-Za-z]+\s+\d{1,2},\s+\d{4})", cells[1])
        time_text = re.search(r"\d{1,2}:\d{2}\s+[AP]M", cells[2], re.IGNORECASE)
        if not date_text:
            return
        try:
            release_date = datetime.strptime(date_text.group(1), "%B %d, %Y").date()
        except ValueError:
            return
        self.events.append({
            "date": release_date.isoformat(),
            "time": time_text.group(0) if time_text else "Time not listed",
            "title": cells[0],
            "category": "econ",
            "impact": "high",
            "description": "Advance monthly U.S. retail and food-services sales release.",
            "source": self.source_url,
            "timeZone": "America/New_York",
        })


class Sp500WeightParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.symbol = ""
        self.rows: list[dict[str, object]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = []
        elif tag == "a" and self.cell is not None:
            symbol_match = re.search(r"/symbol/([A-Za-z0-9.-]+)", attributes.get("href") or "")
            if symbol_match:
                self.symbol = symbol_match.group(1).upper()

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.row is not None and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.add_row(self.row)
            self.row = None

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def add_row(self, cells: list[str]) -> None:
        if len(cells) < 4 or not cells[0].isdigit() or not self.symbol:
            self.symbol = ""
            return
        try:
            weight = float(cells[3].strip().rstrip("%"))
        except ValueError:
            self.symbol = ""
            return
        self.rows.append({
            "symbol": self.symbol,
            "company": cells[1],
            "rank": int(cells[0]),
            "weight": weight,
        })
        self.symbol = ""


class ForexFactoryParser(HTMLParser):
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    def __init__(self, year: int, week_start: date, start: date, end: date) -> None:
        super().__init__()
        self.year = year
        self.week_start = week_start
        self.start = start
        self.end = end
        self.row_class = ""
        self.row_event_id = ""
        self.row_cells: list[tuple[str, str]] | None = None
        self.cell_text: list[str] | None = None
        self.cell_class = ""
        self.nested_classes: list[str] = []
        self.current_date: date | None = None
        self.time_zone = "America/New_York"
        self.events: list[dict[str, str]] = []

    def calendar_date(self, month: int, day: int) -> date:
        parsed = date(self.year, month, day)
        if parsed < self.week_start - timedelta(days=1):
            parsed = date(self.year + 1, month, day)
        elif parsed > self.week_start + timedelta(days=7):
            parsed = date(self.year - 1, month, day)
        return parsed

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = attributes.get("class") or ""
        if tag == "tr":
            self.row_class = classes
            self.row_event_id = attributes.get("data-event-id") or ""
            self.row_cells = []
        elif tag == "td" and self.row_cells is not None:
            self.cell_class = classes
            self.cell_text = []
            self.nested_classes = []
        elif self.cell_text is not None and classes:
            self.nested_classes.append(classes)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.row_cells is not None and self.cell_text is not None:
            self.row_cells.append((self.cell_class + " " + " ".join(self.nested_classes), " ".join("".join(self.cell_text).split())))
            self.cell_text = None
            self.cell_class = ""
            self.nested_classes = []
        elif tag == "tr" and self.row_cells is not None:
            self.finish_row(self.row_cells)
            self.row_cells = None

    def handle_data(self, data: str) -> None:
        if self.cell_text is not None:
            self.cell_text.append(data)

    def finish_row(self, cells: list[tuple[str, str]]) -> None:
        row_text = [text for _, text in cells]
        if "calendar__row--day-breaker" in self.row_class:
            marker = next((text for text in row_text if re.match(r"\w{3}\s+\w{3}\s+\d{1,2}", text)), "")
            match = re.match(r"(\w{3})\s+(\w{3})\s+(\d{1,2})", marker)
            if match and match.group(2).lower() in self.months:
                month = self.months[match.group(2).lower()]
                day = int(match.group(3))
                try:
                    self.current_date = self.calendar_date(month, day)
                except ValueError:
                    self.current_date = None
            return

        if not self.row_event_id:
            return
        date_cell = next((text for classes, text in cells if "calendar__date" in classes), "")
        date_match = re.match(r"\w{3}\s+(\w{3})\s+(\d{1,2})", date_cell)
        if date_match and date_match.group(1).lower() in self.months:
            month = self.months[date_match.group(1).lower()]
            try:
                self.current_date = self.calendar_date(month, int(date_match.group(2)))
            except ValueError:
                self.current_date = None
        if self.current_date is None:
            return

        currency = next((text for classes, text in cells if "calendar__currency" in classes), "").upper()
        if currency != "USD":
            return

        raw_time = next((text for classes, text in cells if "calendar__time" in classes), "")
        title = next((text for classes, text in cells if "calendar__event" in classes), "").strip()
        if not title or self.current_date < self.start or self.current_date > self.end:
            return

        normalized = title.lower()
        if not any(term in normalized for term in (
            "cpi", "consumer price", "ppi", "producer price", "employment",
            "unemployment", "jobless", "payroll", "retail sales", "pce",
            "pmi", "purchasing manager", "gdp", "fed funds", "fomc",
        )):
            return
        if "fomc member" in normalized:
            return

        time_match = re.fullmatch(r"(\d{1,2}):(\d{2})(am|pm)", raw_time, re.IGNORECASE)
        if time_match:
            event_time = f"{int(time_match.group(1))}:{time_match.group(2)} {time_match.group(3).upper()}"
        else:
            event_time = raw_time.title() if raw_time else "Time not listed"

        if re.search(r"\b(cpi|consumer price|ppi|producer price|pce)\b", normalized):
            category = "inflation"
        elif re.search(r"\b(fed funds|fomc|interest rate)\b", normalized):
            category = "fed"
        else:
            category = "econ"
        impact_classes = " ".join(class_name for class_name, _ in cells)
        impact = "high" if "ff-impact-red" in impact_classes else "medium" if "ff-impact-yel" in impact_classes else "low"
        self.events.append({
            "date": self.current_date.isoformat(),
            "time": event_time,
            "timeZone": self.time_zone,
            "title": title,
            "category": category,
            "impact": impact,
            "description": "U.S. economic release schedule from Forex Factory. Verify details with the releasing agency.",
            "source": "https://www.forexfactory.com/calendar",
        })


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "FinanceCalendar local personal calendar"})
    with urlopen(request, timeout=TIMEOUT) as response:
        return response.read().decode("utf-8", errors="replace")


def bea_events(start: date, end: date) -> list[dict[str, str]]:
    parser = BeaScheduleParser()
    parser.feed(fetch_text(BEA_URL))
    return [event for event in parser.events if start.isoformat() <= event["date"] <= end.isoformat()]


def fed_events(start: date, end: date) -> list[dict[str, str]]:
    html = fetch_text(FED_URL)
    section_match = re.search(
        rf"{start.year}\s+FOMC Meetings(.*?)(?:{start.year - 1}\s+FOMC Meetings|$)",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if not section_match:
        raise ValueError(f"Could not find the {start.year} FOMC schedule on the official Federal Reserve page.")

    month_numbers = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    events: list[dict[str, str]] = []
    pattern = re.compile(
        r'fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>.*?'
        r'fomc-meeting__date[^>]*>([^<]+)<',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(section_match.group(1)):
        month = month_numbers.get(match.group(1).strip().lower())
        days = re.search(r"(\d{1,2})(?:\s*-\s*(\d{1,2}))?", match.group(2))
        if not month or not days:
            continue
        release_day = int(days.group(2) or days.group(1))
        try:
            event_date = date(start.year, month, release_day)
        except ValueError:
            continue
        if not start <= event_date <= end:
            continue
        events.append({
            "date": event_date.isoformat(),
            "time": "Time not listed",
            "title": "Federal Reserve rate decision",
            "category": "fed",
            "impact": "high",
            "description": "Final day of the scheduled FOMC meeting. The official calendar does not list a release time.",
            "source": FED_URL,
        })
    return events


def census_events(start: date, end: date) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for year in range(start.year, end.year + 1):
        if year <= date.today().year:
            source_url = f"https://www.census.gov/economic-indicators/calendar-listview-{year}.html"
        else:
            source_url = CENSUS_URL
        parser = CensusRetailParser(source_url)
        parser.feed(fetch_text(source_url))
        events.extend(
            event for event in parser.events
            if start.isoformat() <= event["date"] <= end.isoformat()
        )
    return events


def sp500_weights() -> list[dict[str, object]]:
    parser = Sp500WeightParser()
    parser.feed(fetch_text(SP500_WEIGHTS_URL))
    if len(parser.rows) < 400:
        raise ValueError("S&P 500 constituent weight page returned an incomplete list.")
    return parser.rows


def forex_factory_events(start: date, end: date) -> list[dict[str, str]]:
    events_by_key: dict[tuple[str, str], dict[str, str]] = {}
    week_start = start - timedelta(days=start.weekday())
    while week_start <= end:
        week_slug = f"{week_start.strftime('%b').lower()}{week_start.day}.{week_start.year}"
        url = f"{FOREX_FACTORY_URL}?week={week_slug}"
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Referer": FOREX_FACTORY_URL,
            },
        )
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urlopen(request, timeout=TIMEOUT) as response:
                    html = response.read().decode("utf-8", errors="replace")
                last_error = None
                break
            except (HTTPError, URLError, TimeoutError) as error:
                last_error = error
                if attempt < 2:
                    time.sleep(0.4 * (attempt + 1))
        if last_error:
            raise ValueError(f"Forex Factory calendar request failed: {last_error}") from last_error

        parser = ForexFactoryParser(week_start.year, week_start, start, end)
        timezone_match = re.search(r"""timezone_name:\s*['"]([^'"]+)""", html)
        if timezone_match:
            parser.time_zone = timezone_match.group(1)
        parser.feed(html)
        for event in parser.events:
            key = (event["date"], event["title"].casefold())
            events_by_key[key] = event
        week_start += timedelta(days=7)

    return list(events_by_key.values())


def fmp_events(start: date, end: date, api_key: str) -> list[dict[str, str]]:
    query = urlencode({"from": start.isoformat(), "to": end.isoformat(), "apikey": api_key})
    request = Request(
        f"{FMP_URL}?{query}",
        headers={"Accept": "application/json", "User-Agent": "FinanceCalendar local personal calendar"},
    )
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code in (401, 403):
            raise ValueError("API key is invalid or its plan does not include the economic calendar.") from None
        if error.code == 429:
            raise ValueError("API request limit reached. Try again later.") from None
        raise ValueError(f"Financial Modeling Prep returned HTTP {error.code}.") from None
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read the Financial Modeling Prep calendar: {error}.") from None

    if isinstance(payload, dict):
        if payload.get("Error Message") or payload.get("error"):
            raise ValueError("Financial Modeling Prep rejected the request. Check API key and plan access.")
        raise ValueError("Financial Modeling Prep returned an unexpected economic-calendar response.")
    if not isinstance(payload, list):
        raise ValueError("Financial Modeling Prep returned an unexpected economic-calendar response.")

    events: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        country = str(item.get("country") or "").strip().lower()
        currency = str(item.get("currency") or "").strip().upper()
        if country and country not in {"us", "united states", "usa"}:
            continue
        if currency and currency != "USD":
            continue

        title = str(item.get("event") or "").strip()
        if not title:
            continue
        normalized_title = title.lower()
        if not any(term in normalized_title for term in (
            "cpi", "consumer price", "ppi", "producer price", "employment",
            "unemployment", "jobless", "nonfarm", "retail sales", "pce",
            "pmi", "purchasing managers", "gdp", "fed funds", "interest rate",
        )):
            continue

        raw_date = str(item.get("date") or "").strip()
        try:
            parsed_date = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed_date = datetime.strptime(raw_date[:10], "%Y-%m-%d")
            except ValueError:
                continue
        if parsed_date.tzinfo is not None:
            parsed_date = parsed_date.astimezone(ZoneInfo("America/New_York"))
        event_date = parsed_date.date()
        if not start <= event_date <= end:
            continue

        if re.search(r"\b(cpi|consumer price|ppi|producer price|pce|inflation)\b", normalized_title):
            category = "inflation"
        elif re.search(r"\b(fed|interest rate|fomc)\b", normalized_title):
            category = "fed"
        else:
            category = "econ"
        impact_text = str(item.get("impact") or "").lower()
        impact = "high" if "high" in impact_text else "low" if "low" in impact_text else "medium"
        event_time = parsed_date.strftime("%I:%M %p").lstrip("0") if re.search(r"\d{2}:\d{2}", raw_date) else "Time not listed"
        events.append({
            "date": event_date.isoformat(),
            "time": event_time,
            "title": title,
            "category": category,
            "impact": impact,
            "description": "U.S. economic event from Financial Modeling Prep.",
            "source": "https://site.financialmodelingprep.com/developer/docs/stable/economic-calendar",
            "timeZone": "America/New_York",
        })
    return events


class CalendarHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/sp500-weights":
            try:
                self.send_json(200, {"companies": sp500_weights(), "source": {"name": "S&P 500 index weights", "status": "ok", "url": SP500_WEIGHTS_URL}})
            except (HTTPError, URLError, TimeoutError, ValueError) as error:
                detail = getattr(error, "reason", str(error))
                self.send_json(502, {"error": f"Could not load S&P 500 weights: {detail}", "source": {"name": "S&P 500 index weights", "status": "error", "url": SP500_WEIGHTS_URL}})
            return
        if parsed.path != "/api/official-events":
            super().do_GET()
            return

        params = parse_qs(parsed.query)
        try:
            start = date.fromisoformat(params.get("from", [""])[0])
            end = date.fromisoformat(params.get("to", [""])[0])
            if end < start or (end - start).days > 62:
                raise ValueError("Date range must be valid and no longer than 63 days.")
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
            return

        events: list[dict[str, str]] = []
        sources: list[dict[str, str]] = []
        for name, loader, source_url in (
            ("BEA", bea_events, BEA_URL),
            ("Federal Reserve", fed_events, FED_URL),
            ("Census", census_events, CENSUS_URL),
            ("U.S. macro calendar", forex_factory_events, FOREX_FACTORY_URL),
        ):
            try:
                events.extend(loader(start, end))
                sources.append({"name": name, "status": "ok", "url": source_url})
            except (HTTPError, URLError, TimeoutError, ValueError) as error:
                detail = getattr(error, "reason", str(error))
                sources.append({"name": name, "status": "error", "url": source_url, "error": str(detail)})

        self.send_json(200, {"events": events, "sources": sources})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/fmp-events":
            self.send_json(404, {"error": "Not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 4096:
                raise ValueError("Request body must be between 1 and 4096 bytes.")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            start = date.fromisoformat(body["from"])
            end = date.fromisoformat(body["to"])
            api_key = self.headers.get("X-FMP-API-Key", "").strip()
            if not api_key:
                raise ValueError("Financial Modeling Prep API key is required.")
            if end < start or (end - start).days > 62:
                raise ValueError("Date range must be valid and no longer than 63 days.")
        except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            self.send_json(400, {"error": str(error)})
            return

        try:
            events = fmp_events(start, end, api_key)
            self.send_json(200, {"events": events, "source": {"name": "Financial Modeling Prep", "status": "ok", "url": "https://site.financialmodelingprep.com/developer/docs/stable/economic-calendar"}})
        except ValueError as error:
            self.send_json(502, {"error": str(error), "source": {"name": "Financial Modeling Prep", "status": "error", "url": "https://site.financialmodelingprep.com/developer/docs/stable/economic-calendar"}})

    def send_json(self, status: int, value: object) -> None:
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print(f"Finance Calendar server: {ROOT}")
    ThreadingHTTPServer(("127.0.0.1", 8000), CalendarHandler).serve_forever()
