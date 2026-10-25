# Finance Calendar

This is a small local web app. Its calendar contains no hard-coded sample event dates.

## Run locally

1. Install Python 3.10 or newer if it is not already installed.
2. From this folder, run `python server.py`.
3. Open <http://127.0.0.1:8000>.
4. Choose **Data sources** and add:
   - a [Finnhub API key](https://finnhub.io/register) for company earnings;
   - optionally, a [Financial Modeling Prep API key](https://financialmodelingprep.com/developer/docs) for an additional U.S. economic-calendar feed, if the selected plan includes that endpoint. The app also loads macro events from Forex Factory without a key.
5. Select a calendar day to open its full schedule. **Copy screenshot** always copies a phone-shaped portrait PNG with up to 15 priority events in a readable two-column grid, whether you copy it on a phone or desktop. The vector-drawn image is rendered at 1170 pixels wide and smoothly exported at 85% dimensions (about 995 pixels wide) to reduce file size while keeping text sharp on a 390-pixel phone display. Compact card spacing keeps the 15-event image about 10% shorter without shrinking its text. Press **Esc**, click outside the dialog, or choose **Close** to dismiss it.

Keys are stored in this browser's local storage. The Finnhub key is sent directly to Finnhub; the FMP key is sent to the local server and forwarded to FMP. Do not enter keys on a shared computer. A public deployment should use a protected server-side key store and proxy.

## Data sources

- [Finnhub earnings calendar](https://finnhub.io/docs/api/earnings-calendar): broad company-symbol coverage, scheduled date, and before/after-market timing where provided.
- [S&P 500 index weights](https://www.slickcharts.com/sp500): live constituent membership and index weights used to keep earnings to index companies and sort same-day reports by float-adjusted market-cap proxy. Index weight is a ranking proxy, not a company's exact total market capitalization.
- [Forex Factory economic calendar](https://www.forexfactory.com/calendar): live U.S. CPI, PPI, employment, jobless claims, PMI, GDP, Fed and other events. This is a third-party calendar, not an official release schedule; event dates and times should be verified with the releasing agency. Times are converted from the time zone reported by the calendar.
- [Financial Modeling Prep economic calendar](https://site.financialmodelingprep.com/developer/docs/stable/economic-calendar): optional additional U.S. macro events when returned by the provider. API access is plan-dependent; the app reports key/plan errors rather than substituting dates, and merges duplicate events when possible.
- [U.S. Census Bureau Economic Indicator Calendar](https://www.census.gov/economic-indicators/calendar-listview.html): retail sales release dates and times, pulled from the year-specific official calendar.
- [Bureau of Economic Analysis release schedule](https://www.bea.gov/news/schedule): GDP and Personal Income and Outlays / PCE releases, including published release times.
- [Federal Reserve FOMC calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm): scheduled meeting dates. The last meeting day is shown; no time is inferred when the official schedule does not provide one.
- [Bureau of Labor Statistics release schedule](https://www.bls.gov/schedule/news_release/) and [ISM PMI reports](https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/): linked for verification. The app uses the third-party Forex Factory calendar for these events because direct automated access to the publisher pages is restricted.

Events link back to their provider or official schedule. If a provider is unavailable or rejects a key, its status is shown in the app rather than replacing missing data with sample entries.
