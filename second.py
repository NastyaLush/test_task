import csv
import datetime
import os
import re
from asyncio import Lock
from enum import Enum

import psycopg2
import requests
import json
import time
from datetime import date

from dotenv import load_dotenv
from psycopg2.extras import execute_batch
from selenium import webdriver
from selenium.webdriver.common.by import By
from dateutil.parser import parse
from bs4 import BeautifulSoup

file_to_read_csv = "./articles.csv"


class ArticleType(Enum):
    COIN_MARKET_CAP = "COIN_MARKET_CAP"
    WEB = "WEB"
class Link(Enum):
    SELF = "_self"
    BLANK = "_blank"


def get_text_from_coin_market_cap_page(link):
    text_page = requests.get(link)
    text_soup = BeautifulSoup(text_page.text, "html.parser")
    js_text = text_soup.find('script', id="__NEXT_DATA__")
    j = json.loads(js_text.text)
    content = j["props"]["pageProps"]["article"]["content"]
    return BeautifulSoup(content, "html.parser").get_text()


def automatic_work(driver, url, cursor):
    driver.get(url)
    while True:
        print("do update")
        driver.refresh()
        articles = get_lazy_data_from_page(driver, cursor)
        execute_batch(cursor, '''
                                    insert into articles(
                                    heading,
                                    article_type,
                                    author,
                                    created_at,
                                    text,
                                    associated_tokens,
                                    link) values (%s,%s,%s,%s,%s,%s,%s) on conflict(link) do nothing;
                                    ''', articles)
        print(f"added articles:{articles} ")
        time.sleep(60)


def start():
    load_dotenv()
    with psycopg2.connect(
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            dbname=os.getenv("POSTGRES_DB")
    ) as conn:
        with conn.cursor() as cursor:
            with open(file_to_read_csv, 'w', newline='', encoding="utf-8") as csvfile:
                fieldnames = ['heading', 'article_type', 'author', 'created_at', 'text', 'associated_tokens', 'link']
                writer = csv.writer(csvfile)
                writer.writerow(fieldnames)

                driver = webdriver.Chrome()

                load_first_content(cursor, conn, writer, driver)

            automatic_work(driver,
                           f"https://coinmarketcap.com/community/articles/browse/?sort=-publishedOn&page=1&category=",
                           cursor)
            driver.close()


def load_first_content(cursor, conn, writer, driver, count_of_pages=10):
    lock = Lock()
    for page in range(1, count_of_pages + 1):
        print(f"start load page:{page}")
        url_tmp = f"https://coinmarketcap.com/community/articles/browse/?sort=-publishedOn&page={page}&category="
        lock.acquire()
        driver.get(url_tmp)
        driver.implicitly_wait(10)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        with open('out.html', 'w', encoding="utf-8") as f:
            print(driver.page_source, "data.html", file=f)
        print(f"start read page:{page}")
        articles_data = get_articles_from_page(driver, lock)
        print(f"got all articles from page {page}")
        execute_batch(cursor, '''
                            insert into articles(
                            heading,
                            article_type,
                            author,
                            created_at,
                            text,
                            associated_tokens,
                            link) values (%s,%s,%s,%s,%s,%s,%s) on conflict(link) do nothing;
                            ''', articles_data)
        print(f"wrote all articles from page {page} to db")
        for article in articles_data:
            writer.writerow(article)
        print(f"wrote all articles from page {page} to file")
        conn.commit()
        print(f"read page:{page}")
def load(driver, conn, cursor, lock, page):
    print(f"start load page:{page}")
    url_tmp = f"https://coinmarketcap.com/community/articles/browse/?sort=-publishedOn&page={page}&category="
    lock.acquire()
    driver.get(url_tmp)
    driver.implicitly_wait(10)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    with open('out.html', 'w', encoding="utf-8") as f:
        print(driver.page_source, "data.html", file=f)
    print(f"start read page:{page}")
    articles_data = get_articles_from_page(driver, lock)
    print(f"got all articles from page {page}")
    execute_batch(cursor, '''
                                insert into articles(
                                heading,
                                article_type,
                                author,
                                created_at,
                                text,
                                associated_tokens,
                                link) values (%s,%s,%s,%s,%s,%s,%s) on conflict(link) do nothing;
                                ''', articles_data)
    print(f"wrote all articles from page {page} to db")
    for article in articles_data:
        writer.writerow(article)
    print(f"wrote all articles from page {page} to file")
    conn.commit()
    print(f"read page:{page}")

def get_articles_from_page(driver, lock):
    articles_list = list()
    contents = driver.find_element(By.CLASS_NAME, 'ibVHPJ')
    html = contents.get_attribute('innerHTML')
    lock.release()
    soup = BeautifulSoup(html, "html.parser")
    articles = soup.find_all('a', class_="cmc-link")
    for a in articles:
        # heading: str
        # article_type: str
        # author: str
        # created_at: date
        # text: str
        # associated_tokens = list()
        # link: str
        article, link = get_article(a)
        articles_list.append(article)
    return articles_list


def get_lazy_data_from_page(driver, cursor):
    articlesList = list()
    driver.implicitly_wait(10)
    contents = driver.find_element(By.CLASS_NAME, 'ibVHPJ').find_elements(By.CLASS_NAME, 'cmc-link')
    for c in contents:
        article, link = get_article(c)
        if not check_if_article_exists_in_db(cursor, link):
            articlesList.append(article)
        else:
            return articlesList
    return articlesList

def check_if_article_exists_in_db(cursor, current_link):
    cursor.execute('''
    select exists(select * from articles where link = %s)
    ''', (current_link,))
    return cursor.fetchone()[0]


def get_article(article):
    associated_tokens = list()
    link = article["href"]

    data = article.find('div', class_='ehRbwo')
    heading = data.find('p', class_='title').text
    text = data.find('p', class_= 'description').text

    meta = data.find('div', class_= 'jRnXDB')
    author = meta.find('div', class_= 'tooltip')["data-text"]
    created_at = parse_date(meta.find('div', class_='date-info').text)
    for token in meta.find('div', class_= 'kHhYHG').find_all('span'):
        associated_tokens.append(token.text)

    if article["target"] == Link.SELF.value:
        article_type = ArticleType.COIN_MARKET_CAP.value
        text = get_text_from_coin_market_cap_page(link)
    elif article["target"] == Link.BLANK.value:
        article_type = ArticleType.WEB.value
    else:
        raise Exception(f"Unknown article type {article.get_attribute("target")}")
    # print((heading, article_type, author, str(created_at), text, associated_tokens, link))
    return (heading, article_type, author, str(created_at), text, associated_tokens, link), link
def parse_date(input):
    hour_match = re.search(r"(\d{2})h", input)
    min_match = re.search(r"(\d{2})m", input)
    day_match = re.search(r"(\d{2})day", input)

    if hour_match:
        hours = int(hour_match.group(1))
        return datetime.datetime.now() - datetime.timedelta(hours=hours)
    elif min_match:
        minutes = int(min_match.group(1))
        return datetime.datetime.now() - datetime.timedelta(minutes=minutes)
    elif day_match:
        days = int(day_match.group(1))
        return datetime.datetime.now() - datetime.timedelta(days=days)
    else:
        return parse(input)

start()
