# -*- coding: utf-8 -*-

import html
import json
import os
import re
import time
import requests

from bs4 import BeautifulSoup
from flask import Flask, jsonify
from googletrans import Translator

translator = Translator()


def translate(text='', src='fi', dest='en'):
    return translator.translate(text, dest=dest, src=src).text

# file = open('test.json', 'r')
# soup = BeautifulSoup(file, "html.parser")

# name = json.loads(soup.text)['initialModel']['product']['name'])


class VVerk:
    BASE_URL = "https://127.0.0.1:5000/"

    def __init__(self, json_string):
        self.json = json.loads(json_string)
        # self.secret = secret

    def get_host(self):
        return self.json['initialModel']['classicHost']

    def get_name(self):
        return translate(self.json['initialModel']['product']['name'])

    def get_price(self):
        return float(self.json['initialModel']['product']['price'].replace(',', '.'))

    def get_price_export(self):
        return float(self.json['initialModel']['product']['priceWithoutTax'].replace(',', '.'))

    def get_price_vat(self):
        return "%.2f" % float(self.get_price() - self.get_price_export())

    def get_price_tax(self):
        return int(self.json['initialModel']['product']['taxRate'])

    def get_warranty(self):
        return int(self.json['initialModel']['product']['warranty'])

    def get_support(self):
        return translate(self.json['initialModel']['product']['support'])

    def get_package(self):  # return dict
        return self.json['initialModel']['product']['package']

    def get_sku(self):
        return str(self.json['initialModel']['product']['productId'])

    def get_categories(self):  # return list
        return self.json['initialModel']['product']['bulletPoints']

    def get_brand(self):
        return self.json['initialModel']['product']['brandName']

    def get_description_full(self):
        return self.json['initialModel']['product']['descriptionLong']  # html

    def get_description(self):
        return self.json['initialModel']['product']['descriptionShort']  # html

    def get_ean(self):
        return self.json['initialModel']['product']['ean']

    def get_ean(self):
        return self.json['initialModel']['product']['ean']

    def get_href(self):
        return self.json['initialModel']['product']['href']

    def get_images(self):
        images = []
        for image in self.json['initialModel']['product']['images']:
            images.append('https://' + image['host'] + image['path'])
        return images

    def get_product_code(self):
        return str(self.json['initialModel']['product']['manufacturerProductCode'])

    def is_active(self):
        return self.json['initialModel']['product']['isActive']

    def is_bundle(self):
        return self.json['initialModel']['product']['isBundle']

    def is_bundled(self):
        return self.json['initialModel']['product']['isBundled']

    def is_price_visible(self):
        return self.json['initialModel']['product']['isPriceVisible']

    def is_electronic_product(self):
        return self.json['initialModel']['product']['isElectronicProduct']
