import asyncio
import pyautogui
import gspread
import re
import nodriver as uc
from oauth2client.service_account import ServiceAccountCredentials

GOOGLE_SHEET_CREDENTIALS = "service_account.json"
SHEET_NAME = "Companies With Bad Reviews"

async def setup_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEET_CREDENTIALS, scope)
    client = gspread.authorize(creds)

    SHEET_URL = "https://docs.google.com/spreadsheets/d/1EYGTEF7DkDk_1icKdso8Rl37LjAIQ3ixXTYOj4YDu7E/edit?gid=0#gid=0"
    
    try:
        sheet = client.open_by_url(SHEET_URL).sheet1
    except gspread.SpreadsheetNotFound:
        print(f"Error: Cannot access the spreadsheet. Check if the URL is correct and the sheet is shared with the service account.")
        return None

    if sheet.row_count == 0 or sheet.get_all_values() == []:
        sheet.append_row(["Company Name", "Company URL", "Bad Review #1", "Bad Review #2"])

    return sheet

async def save_to_google_sheets(sheet, data):
    sheet.append_row(data)

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
    review_tab = await page.select("header div[data-testid='reviews-tab'] a span")
    await review_tab.click()
    await asyncio.sleep(1)
    show_all_reviews = await page.select("main div[data-testid='more-review-options'] > ul > li:first-of-type a div")
    if show_all_reviews:
        await show_all_reviews.click()
        await asyncio.sleep(2)

    review_areas = await page.select_all("main div[data-testid='content'] > div:last-of-type > ul > li")
    review_count = len(review_areas)
    bad_reviews = []
    for i in range(review_count):
        score_element = await page.select(f"main div[data-testid='reviewsList'] > ul > li:nth-of-type({i + 1}) > div > div > div > div:first-of-type > div > span:first-of-type")
        if not score_element:
            continue
        score_text = score_element.text_all
        try:
            score = float(score_text)
        except ValueError:
            continue
        review = await page.select(f"main div[data-testid='content'] > div:last-of-type > ul > li:nth-of-type({i + 1}) > div > div > div > div:last-of-type > div[data-testid='reviewDescription'] > span")
        text = review.text_all
        if 1.0 <= score <= 2.0:
            bad_reviews.append(text)
        if len(bad_reviews) >= 2:
            break
    if bad_reviews:
        await save_to_google_sheets(sheet, [company_name, company_url] + bad_reviews)
    else:
        await save_to_google_sheets(sheet, [company_name, company_url])
    await page.close()

async def main():
    alphabetical_page_start_number = 0
    numerical_page_start_number = 0
    section_start_number = 18

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
                print (f"company name: {company_name}")                
                match = re.search(r'href="(/cmp/[^"]+)"', str(company))
                if match:
                    company_url = match.group(1)
                    company_url = "https://www.indeed.com" + company_url if company_url.startswith("/cmp/") else company_url
                print (f"company url: {company_url}")  
                
                if company_url:
                    company_page = await browser.get(company_url, new_tab=True)
                    await scrape_reviews(company_page, company_name, company_url, sheet)

                k = k + 1
            k = 0
            j = j + 1
        j = 0
        i = i + 1
    i = 0

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
