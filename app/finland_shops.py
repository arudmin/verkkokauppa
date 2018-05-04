# -*- coding: utf-8 -*-

import html
import json
import os
import re
import time
import requests

from datetime import datetime
from bs4 import BeautifulSoup as bs
from googletrans import Translator

translator = Translator()


class Power:
    def __init__(self):
        self.search_url = 'https://www.power.fi/Umbraco/Api/Product/SuggestionSearch?siteId=6&searchTerm='

    def get_data_by_ean(self, ean):
        r = requests.get(self.search_url + ean)
        return r.json()

    def get_url_by_ean(self, ean):
        json_data = get_data_by_ean(ean)
        return json_data['TopProducts'][0]['Products'][0]['Url']

    def get_pid_by_ean(self, ean):
        json_data = get_data_by_ean(ean)
        return json_data['TopProducts'][0]['Products'][0]['ProductId']

    def get_price_by_ean(self, ean):
        json_data = get_data_by_ean(ean)
        return json_data['TopProducts'][0]['Products'][0]['Price']

    def get_image_by_ean(self, ean):
        json_data = get_data_by_ean(ean)
        host = 'https://www.power.fi/images/products/'
        return host + json_data['TopProducts'][0]['Products'][0]['PrimaryImage']


class Gigantti:
    def __init__(self):
        self.search_url = 'https://www.gigantti.fi/search?search=&searchResultTab=&SearchTerm='
        # https://www.gigantti.fi/INTERSHOP/web/WFS/store-gigantti-Site/fi_FI/-/EUR/ViewSuggestSearch-Suggest

    def get_info_by_ean(self, ean):
        item = {}
        r = requests.get(self.search_url + ean)
        soup = bs(r.content, 'html.parser')
        item['price'] = soup.select_one('div.product-price-container').text.strip()
        item['name'] = soup.select_one('h1.product-title').text
        item['description'] = soup.select_one('p.short-description').text
        item['sku'] = soup.select_one('p.sku')['data-product-sku']
        item['ean'] = soup.find("meta", {"itemprop": "productID"})['content']
        try:
            item['stock_online'] = soup.select_one('div#product-detail-wrapper').select_one('span.items-in-stock').text.split('(')[1].replace(')', '').strip()
            item['stock_offline'] = json.loads(soup.select_one('div#stock-info')['data-stock'])
            item['stores_offline'] = json.loads(soup.select_one('div#product-detail-wrapper')['data-stores'])
        except:
            item['stock_online'] = soup.select_one('div#product-detail-wrapper').select_one('span.items-in-stock').text.strip()
        return item

    def get_stock_online(self, ean):
        data = get_info_by_ean(ean)
        return data['stock_online']


class Verk:
    def __init__(self):
        pass

    def get_json(self, api_url):
        r = requests.get(api_url)
        soup = bs(r.content, 'html.parser')
        json_data = json.loads(html.unescape(soup.find(id='state').text))
        return json_data

    def get_extra_raisio(self, lng=''):
        items = []
        api_url = 'https://www.verkkokauppa.com/fi/avajaiset'
        json_data = self.get_json(api_url)['sisu']['meta']['productInfoProducts']

        for x in json_data:
            # generate sales date (day) and expire key
            item_date = re.search('alkaa .*? (.*?\..*?)\.', x['descriptionShort'])[1] + '.'
            item_date = datetime.strptime(item_date + str(datetime.now().year), '%d.%m.%Y')
            x['date'] = item_date
            x['price'] = x['price'].replace(',', '.').replace('alk. ', '')
            x['expire'] = 1 if (x['date'] - datetime.now()).days + 2 <= 0 else 0

            if lng:
                x['descriptionShort'] = translate(x['descriptionShort'], dest=lng)

            x['name'] = translate(x['name'])
            try:
                x['pid'] = re.search(r'\d{3,6}', x['image'])[0]
            except:
                print(x)

            items.append(x)

        return items


def translate(text='', src='fi', dest='en'):
    return translator.translate(text, dest=dest, src=src).text
