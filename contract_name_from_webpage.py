"""
Produces an excel spreadsheet that contains contract descriptions and other data from the defense.gov website.
"""

__author__ = "Harry Staley"
__version__ = "0.5"
__license__ = "MIT"
__maintainer__ = "Harry Staley"
__email__ = "harry.a.staley2.civ@army.mil"
__status__ = "Development"


from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime, date
import time
import regex as re
import pandas as pd
import random
import string

# TODO: Further parsing on multiple-award/IDIQ-type contracts – each IDIQ contract number will be associated with a
#  single “parent” index number.
# TODO “Contract Name” refinements: continue to use “first letter capitalization” for all words in the “contract name”;
#  however, use all lowercase for most prepositions bounded by spaces. For example, use all lowercase for all instances
#  of, eg, “ in ”," " at ", " on ", " of ", “ and ”, " to ”, etc. when bounded by spaces.
# TODO Contract type: add a new column, to the right of “contract number”, entitled “contract type”.  Insert the *ninth*
#  (9th) character of contract number in that field (eg, “C”, “D”, “R”, “F”, etc).
# TODO Extract the “ultimate completion date”-like value from the text?  Would be encapsulated in text like “with an
#  estimated completion date of…”, or the like.
# TODO Extract the contracting office?
# TODO Processing multiple contract numbers – see this Navy sample at
#  https://www.defense.gov/News/Contracts/Contract/Article/2857360/ .


def generate_id():
    """
    Generates a psuedo random string for use as an ID in the excel spreadsheet.

    :return: generated_id: Psuedo random id with the following schema:
    (Year)(month)-(2 random upper case letters)(zero padded six digits from 10 to 999999)
    """
    generated_id = f"{date.today().strftime('%Y%m')}-"
    generated_id += ''.join(random.choices(population=string.ascii_uppercase, k=2))
    generated_id += str(random.randint(10, 999999)).zfill(6)
    return generated_id


def get_driver():
    """
    Downloads a chrome web browser driver and it silently for use ready to parse a web page.

    :return: A chrome web browser driver with the --headless and --disable-gpu options enabled.
    """
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    browser_driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return browser_driver


driver = get_driver()


def parse_awards_date_page_to_dict(url="https://www.defense.gov/News/Contracts/"):
    """
    Parse the page containing a list of URLs for awards on each award_date.

    :param url: The url of the page that you want to parse for contract links and dates.
    :return: A dictionary of hyperlinks in the form of key=award_date: value=hyperlink.
    """

    html = render_markup(url)
    soup = BeautifulSoup(markup=html, features="html.parser")
    pattern = re.compile(r"http://www\.defense\.gov/News/Contracts/Contract/Article/\d+/")
    anchor_tags = soup.find_all("a", href=pattern)

    # Create a dictionary for hyperlinks
    hyperlinks = {}
    for link in anchor_tags:
        # Get the text displayed on the hyperlink and Strip out extraneous data and return the award_date.
        publish_date_raw = link.text.title().replace("Contracts For", "").replace(".", "").strip()
        publish_date = publish_date_raw.split()
        month = publish_date[0][:3].title()
        day = "".join(filter(str.isdigit, publish_date[1]))
        year = "".join(filter(str.isdigit, publish_date[2]))
        # convert the award_date format to normalize award_date
        publish_date = datetime.strptime(f"{month} {day}, {year}", "%b %d, %Y").strftime('%m/%d/%Y')
        # create a key value pair where the key is the award_date and the value is the link.
        hyperlinks[publish_date] = link["href"]
    return hyperlinks


def render_markup(url):
    """
    Render the markup of a given web page using google chrome.

    :param url: the url of the web page you want to render.
    :return: markup rendered by the browser provided by the driver.
    """
    # initiating the webdriver. Parameter includes the path of the webdriver.
    driver.get(url)
    # this is just to ensure that the page is loaded
    time.sleep(4)
    # this renders the JS code and stores all
    # returns all static HTML.
    html = driver.page_source
    return html


def parse_contracts_page(url, award_date):
    """
    Parse the page of contracts for a specific date.

    :param url: The url of the individual page containing the award announcements for a specific date.
    :param award_date: The date of the awards announced on the page.
    :return: a dictionary of the awards on the particular page.
    """
    html = render_markup(url)
    soup = BeautifulSoup(markup=html, features="html.parser")
    body = soup.find("div", {"class": "body"})
    paragraphs = body.findChildren()
    awards = []
    service = ""
    for p in paragraphs:
        tag_text = p.text
        if tag_text.strip() == tag_text.strip().upper():
            # pull out the service title from the page.
            service = tag_text
        else:
            # pull out the contractor from the text.
            contractor_pattern = re.compile(r"^.+?(?=,)")
            contractor_search = contractor_pattern.search(tag_text)
            if contractor_search:
                contractor = contractor_search.group()
            else:
                contractor = ''

            # search for small business indicator.
            sm_biz_pattern = re.compile(r",\* ")
            sm_biz_search = sm_biz_pattern.search(tag_text)
            small_business = bool(sm_biz_search)

            # Search for women owned small business indicator.
            wo_sm_biz_pattern = re.compile(r",\*\* ")
            wo_sm_biz_search = wo_sm_biz_pattern.search(tag_text)
            wo_small_business = bool(wo_sm_biz_search)

            # pull the description of the contract out from the paragraph.
            description_pattern = re.compile(r"(contract|agreement|award)+.*for (.+?\.)")
            description_search = description_pattern.search(tag_text)
            if description_search:
                description = description_search.group(2).capitalize()
            else:
                description = ''

            # generate contract name.
            contract_name_pattern = re.compile(r"^((the|or|an|a)*\s+)*(.+)\.+$", re.IGNORECASE)
            contract_name_search = contract_name_pattern.search(description)
            if contract_name_search:
                contract_name = contract_name_search.group(3)
            else:
                contract_name = ''
            contract_name = contract_name.title()
            if len(contract_name) >= 100:
                contract_name = contract_name[:100] + "..."
            contract_name += " (PRELIM. DESC.)"

            """
            Pull the contract number out from the paragraph.
             Referenced PIID schema taken from FAR 4.16:
            https://www.acquisition.gov/sites/default/files/current/far/compiled_html/subpart_4.16.html
            Referenced DODAAC assignment logic taken from DLA Website:
            https://www.dla.mil/Portals/104/Documents/DLMS/Committees/DoDAAD/DoDAAC_Assignment_Logic.pdf
            """
            contract_num_pattern = re.compile(r"[a-zA-Z][a-zA-Z0-9]{5}-*[0-9]{2}-*[a-zA-Z]-*[0-9]{4,8}")
            contract_num_search = contract_num_pattern.search(tag_text)
            # find the contract number and remove - and any leading and trailing whitespace and setting to upper case.
            if contract_num_search:
                contract_num = contract_num_search.group().strip().replace('-', '').upper()
            else:
                contract_num = ''

            # pull the award amount out from the paragraph
            dollars_awarded_pattern = re.compile(r"\$(\d{1,3}(\,\d{3})*|(\d+))(\.\d{2})?")
            dollars_awarded_search = dollars_awarded_pattern.search(tag_text)
            if dollars_awarded_search:
                dollars_awarded = dollars_awarded_search.group()
            else:
                dollars_awarded = ''

            # generate an id for the record
            awards.append({'index': generate_id(),
                           'contract name': contract_name,
                           'link': url,
                           'award date': award_date,
                           'contract number': contract_num,
                           'dollars awarded': dollars_awarded,
                           'service': service,
                           'contractor': contractor,
                           'small business': small_business,
                           'woman owned small business': wo_small_business,
                           'description': description
                           })
    return awards


def generate_report(start_dt, end_dt=date.today().strftime('%Y-%m-%d')):
    """
    :param start_dt: (Required) The start date of the data that you want to parse from the site.
    :param end_dt: (Optional) The end date of the data that you want to parse if left empty the function will use the
    current date.
    :return: An excel spreadsheet containing the contract data.
    """
    contracts = []
    start_page = f"https://www.defense.gov/News/Contracts/StartDate/{start_dt}/EndDate/{end_dt}"
    page_num = 1
    empty_dict = False
    links_dict = {}

    while not empty_dict:
        page_url = start_page + f"/?page={page_num}"
        print(f"parsing links: {page_url}")
        links = parse_awards_date_page_to_dict(url=page_url)
        if len(links) == 0:
            print(f"NO LINKS FOUND: {page_url}")
            empty_dict = True
        else:
            links_dict.update(links)
            page_num += 1

    for award_date, link in links_dict.items():
        print(f"parsing text for: {award_date}, {link}")
        page_data = parse_contracts_page(url=link, award_date=award_date)
        contracts += page_data
    df = pd.DataFrame(contracts)
    filename = f"{date.today().strftime('%Y-%m-%d')}_award_descriptions"
    return df.to_excel(f'{filename}.xlsx', sheet_name=filename, index=False)


if __name__ == '__main__':
    date_format = "%Y-%m-%d"
    while True:
        try:
            start_date = input("(Required) Start Date \"YYYY-MM-DD\": ")
            datetime.strptime(start_date, date_format)
            break
        except ValueError:
            print("This is the incorrect date string format. It should be YYYY-MM-DD")
    while True:
        end_date = input("(Optional) End Date \"YYYY-MM-DD\": ")
        if end_date == "":
            break
        try:
            datetime.strptime(end_date, date_format)
            break
        except ValueError:
            print("This is the incorrect date string format. It should be YYYY-MM-DD")
    if end_date == "":
        generate_report(start_dt=start_date)
    else:
        generate_report(start_dt=start_date, end_dt=end_date)
