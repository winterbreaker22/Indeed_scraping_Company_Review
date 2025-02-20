import asyncio
import pyautogui
import gspread
import re
import nodriver as uc
import requests
from oauth2client.service_account import ServiceAccountCredentials

GOOGLE_SHEET_CREDENTIALS = "service_account.json"
SHEET_NAME = "Companies With Bad Reviews"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1EYGTEF7DkDk_1icKdso8Rl37LjAIQ3ixXTYOj4YDu7E/edit?gid=0#gid=0"
SERPAPI_KEY = "a3f192c06ef7a0d381572e36420645a57c3d98b8d6743d7149b58075e0e6d2bc"  
APOLLO_API_KEY = "FZiKkpQGco1VyX57tM_pAA"  
HUNTER_API_KEY = '5ec67b32558c9bb5d7d3f00c2091b61912b581f7'

async def setup_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEET_CREDENTIALS, scope)
    client = gspread.authorize(creds)

    try:
        sheet = client.open_by_url(SHEET_URL).sheet1
    except gspread.SpreadsheetNotFound:
        print("Error: Cannot access the spreadsheet. Check if the URL is correct and shared properly.")
        return None

    all_values = sheet.get_all_values()
    if not all_values or all(len(cell) == 0 for cell in all_values):
        sheet.append_row(["Company Name", "Company URL", "Company Domain", "Decision Maker First Name", "Decision Maker Last Name", "Decision Maker Email", "Bad Review #1", "Bad Review #2"])
    else:
        print("Sheet already contains data, no need to add header.")

    return sheet

async def save_to_google_sheets(sheet, data):
    sheet.append_row(data)

async def get_company_domain(company_name):
    search_url = "https://serpapi.com/search"
    params = {
        "q": f"{company_name} official website",
        "api_key": SERPAPI_KEY,
        "num": 1
    }

    try:
        response = requests.get(search_url, params=params)
        data = response.json()
        return data['organic_results'][0]['link'] if 'organic_results' in data else "Not Found"
    except Exception as e:
        print(f"Error fetching domain for {company_name}: {e}")
        return "Not Found"

async def get_decision_maker_info(domain):
    if domain.startswith("https://www."):
        domain = domain.replace("https://www.", "").split("/")[0]

    url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={HUNTER_API_KEY}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        print (f"data: {data}")

        if "data" in data and "emails" in data["data"]:
            for email_entry in data["data"]["emails"]:
                position = email_entry.get("position", "")
                position_lower = position.lower() if position else ""

                if any(keyword in position_lower for keyword in ["manager", "owner", "executive", "ceo", "cto", "cfo", "founder", "director", "chairman"]):
                    return {
                        "first_name": email_entry.get("first_name", "").strip(),
                        "last_name": email_entry.get("last_name", "").strip(),
                        "email": email_entry.get("value", "").strip()
                    }
    return None

async def bypass_cloudflare():
    location = pyautogui.locateOnScreen('checkbox.png', confidence=0.8)
    if location:
        center = pyautogui.center(location)
        pyautogui.click(center)
    await asyncio.sleep(10)

async def check_cloudflare(page):
    html_content = await page.get_content()
    return "additional verification required" in html_content.lower()

async def scrape_reviews(page, company_name, company_url, sheet):
    await asyncio.sleep(1)

    company_domain = await get_company_domain(company_name)
    decision_maker_info = await get_decision_maker_info(company_domain)
    
    print(f"Company: {company_name}, Domain: {company_domain}, Decision Maker: {decision_maker_info}")

    review_tab = await page.select("header div[data-testid='reviews-tab'] a span")
    await review_tab.click()
    await asyncio.sleep(1)
    
    show_all_reviews = await page.select("main div[data-testid='more-review-options'] > ul > li:first-of-type a div")
    if show_all_reviews:
        await show_all_reviews.click()
        await asyncio.sleep(2)

    review_areas = await page.select_all("main div[data-testid='content'] > div:last-of-type > ul > li")
    bad_reviews = []
    
    for i, review_area in enumerate(review_areas, start=1):
        score_element = await page.select(f"main div[data-testid='reviewsList'] > ul > li:nth-of-type({i}) > div > div > div > div:first-of-type > div > span:first-of-type")
        if not score_element:
            continue

        try:
            score = float(score_element.text_all)
        except ValueError:
            continue

        if 1.0 <= score <= 2.0:
            review_text = await page.select(f"main div[data-testid='content'] > div:last-of-type > ul > li:nth-of-type({i}) > div > div > div > div:last-of-type > div[data-testid='reviewDescription'] > span")
            bad_reviews.append(review_text.text_all)

        if len(bad_reviews) >= 2:
            break

    row_data = [
        company_name.strip() if company_name else "",
        company_url.strip() if company_url else "",
        company_domain.strip() if company_domain else ""
    ]

    if decision_maker_info:
        row_data.extend([
            decision_maker_info.get('first_name', '').strip(),
            decision_maker_info.get('last_name', '').strip(),
            decision_maker_info.get('email', '').strip()
        ])
    else:
        row_data.extend(["", "", ""])

    row_data.extend(bad_reviews)
    print(f"Row being added: {row_data}")

    await save_to_google_sheets(sheet, row_data)
    await page.close()

async def main():
    alphabetical_page_start_number = 0
    numerical_page_start_number = 0
    section_start_number = 0

    browser = await uc.start()
    page = await browser.get("https://www.indeed.com/companies/browse-companies")
    await asyncio.sleep(15)

    if await check_cloudflare(page):
        await bypass_cloudflare()

    alphabetical_page_links = await page.select_all("main > div > nav:first-of-type ul[data-cy='alphabetical-pagination'] > li")
    numerical_page_links = await page.select_all("main > div > nav:last-of-type ul[data-cy='numeric-pagination'] > li")
    alphabetical_page_count = len(alphabetical_page_links)
    numerical_page_count = len(numerical_page_links)
    
    i = alphabetical_page_start_number
    j = numerical_page_start_number
    k = section_start_number

    while i < alphabetical_page_count:
        alpha_index = await page.select(f"main > div > nav:last-of-type ul[data-cy='numeric-pagination'] > li:nth-of-type({str(i + 1)}) a span")
        await alpha_index.click()
        await asyncio.sleep(1)
        
        while j < numerical_page_count:
            num_index = await page.select(f"main > div > nav:last-of-type ul[data-cy='numeric-pagination'] > li:nth-of-type({str(j + 1)}) a span")
            await num_index.click()
            await asyncio.sleep(1)

            company_list = await page.select_all("main > div > section > ul[data-cy='companies-list'] > li")
            company_count = len(company_list)
            sheet = await setup_google_sheets()
            
            while k < company_count:
                company = await page.select(f"main section ul[data-cy='companies-list'] > li:nth-of-type({str(k + 1)}) a")
                company_name = company.text_all              

                match = re.search(r'href="(/cmp/[^"]+)"', str(company))
                if match:
                    company_url = match.group(1)
                    company_url = "https://www.indeed.com" + company_url if company_url.startswith("/cmp/") else company_url
                
                if company_url:
                    company_page = await browser.get(company_url, new_tab=True)
                    await scrape_reviews(company_page, company_name, company_url, sheet)

                k += 1
            k = 0
            j += 1
        j = 0
        i += 1
    i = 0

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
