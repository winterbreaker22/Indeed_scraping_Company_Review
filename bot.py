import asyncio
import pyautogui
import gspread
import nodriver as uc
from oauth2client.service_account import ServiceAccountCredentials

GOOGLE_SHEET_CREDENTIALS = "service_account.json"
SHEET_NAME = "Companies With Bad Reviews"

async def setup_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEET_CREDENTIALS, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
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

async def scrape_reviews(browser, company_name, company_url, sheet):
    page = await browser.get(company_url)
    await asyncio.sleep(3)
    reviews_section = await page.select("main section:has-text('reviews')")
    reviews = await reviews_section.select("div") if reviews_section else []
    bad_reviews = []
    for review in reviews:
        score_element = await review.select("[class*=rating]")
        score_text = await score_element.inner_text() if score_element else ""
        try:
            score = float(score_text)
        except ValueError:
            continue
        text = await review.inner_text()
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
    browser = await uc.start()
    page = await browser.get("https://www.indeed.com/companies/browse-companies")
    await asyncio.sleep(10)

    if await check_cloudflare(page):
        await bypass_cloudflare()

    nav_elements = await page.select_all("main > div > nav")
    print (f"num of nav elements: {len(nav_elements)}")
    alphabetical_nav, numerical_nav = nav_elements
    print (f"alphabetic nav: {alphabetical_nav}")
    alphabetical_links = await alphabetical_nav.select_all("ul > li")
    
    for alpha_link in alphabetical_links:
        alpha_url = await alpha_link.select("a")
        await alpha_url.click()
        
        numerical_links = await numerical_nav.select_all("ul > li")
        
        for num_link in numerical_links:
            num_url = await num_link.select("a")
            await num_url.click()
            
            company_list = await page.select_all("main section ul[data-cy='companies-list'] > li")
            sheet = await setup_google_sheets()
            tasks = []
            
            for company_item in company_list:
                company = company_item.select("a")
                company_name = await company.inner_text()
                company_url = await company.get_attribute("href")
                
                if company_url:
                    company_page = await browser.get(company_url)
                    await scrape_reviews(browser, company_name, company_url, sheet)
                    await company_page.close()
                
    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
