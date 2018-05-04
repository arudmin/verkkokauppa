# -*- coding: utf-8 -*-

import redis
import datetime, time, locale, hashlib
import requests, re, os, html, json, math
import xml.etree.ElementTree as xml
from flask import Flask, Response, jsonify, abort, redirect, url_for
from flask import session, escape, request, render_template
from flask_compress import Compress
from bs4 import BeautifulSoup
from googletrans import Translator
from app.finland_shops import Gigantti, Power, Verk

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.jinja_env.add_extension('jinja2.ext.do')
app.config['TEMPLATES_AUTO_RELOAD'] = False
app.debug = True
app.config['DEBUG'] = True
# app.secret_key = hashlib.md5(os.environ.get("REDIS_URL"))

Compress(app)

translator = Translator()

# If you use redis, install this add-on https://elements.heroku.com/addons/heroku-redis
redis = redis.from_url(os.environ.get("REDIS_URL"), charset="utf-8", decode_responses=True)

domain = 'https://www.verkkokauppa.com/'
search_url = 'https://www.verkkokauppa.com/fi/search?query='
vat_percent = {0.14: 1 - 1 / 1.14, 0.24: 1 - 1 / 1.24}
lang = ['en', 'ru']


@app.route("/")
def hello():
    abort(404)
    # return "Hello World!"


@app.route("/search/<query>/")
def search(query):
    search_url = "https://www.verkkokauppa.com/fi/search?query=%s" % query
    r = requests.get(search_url)
    soup = BeautifulSoup(r.content, 'html.parser')
    items_count = soup.select_one('h1.search-result-count').text.split()[0]

    if not items_count.isdigit():
        # print(items_count)
        abort(404)

    i, sku, result, out = 0, {}, {}, {}
    items = soup.find_all('li', {'class': 'product-list-detailed__item'})

    result.update({'timestamp': time.time(), 'search_query': query, 'items_count': int(items_count)})

    # чистим выдачу от лишних слов
    stop_words = ['phone, ', ', MQHM2', ', MQHK2', ', MQH22', ', MKQU2', ', MKQW2', ', MQ6G2', 'Telephone ', ', MQ6H2', ', MQ6J2', ', MN922', 'MQTX2', ', MN962', ', MQU72', ', MN4V2', ', MKQT2', ', MKUE2', ', MKQV2', ', MKUD2', ', MKUG2', ', MKUF2', ' phone with mirror', 'Phone, ', '-Android ', 'Phone Dual-SIM, ', 'Android ', 'Graphics Card for PCI-E', '11264 MB ', '8192 MB ', '', '', '', '', '', '', '', '', '', '']

    def clean_result(out):
        for stop_word in stop_words:
            out = out.replace(stop_word, "")
        return out.strip()

    for item in items:
        out = {
            'sku_id': item.select_one('div.image__product-id').text,
            # 'sku_name' : translate(",".join(item.select_one('span.list-product-link__name').text)[0]),
            'sku_name': clean_result(translate(item.select_one('span.list-product-link__name').text)),
            'sku_price': float(item.select_one('span.product-price__price').text.replace(',', '.').replace(' ', '').replace(u'\xa0', u''))
        }
        sku.update({i: out})
        i += 1

    result.update({'items': sku})
    return jsonify(result)


@app.route("/extra/")
def get_extra():
    extra = redis.lrange('extra_list', 0, -1)
    # return '0'
    pipe = redis.pipeline()
    for sku in extra:
        # название ключа для редиса, где хранятся записи
        r_sku = "items:%s" % sku
        # проверяем, есть ли уже запись по данному товару (по sku)
        if redis.exists(r_sku + ":_sku"):
            print("%s exist" % sku)
            continue
        # делаем запрос данных по товару
        json_data = requests.get('https://verkcom.herokuapp.com/sku/%s' % sku)

        # json_data2 = get_sumary(sku)
        # pprint(json_data2)
        # exit()

        if (json_data.status_code != 200):
            print("%s not found" % sku)
            r_errors(sku)
            continue

        for k, v in json_data.json().items():
            # print("-" * 10)
            if isinstance(v, (list, tuple)):
                if not v:
                    v = ['null']
                # print(v)
                pipe.lpush("%s:%s" % (r_sku, k), *v)
            else:
                pipe.set("%s:%s" % (r_sku, k), v)
        pipe.execute()
        print("%s added" % sku)
        # print('– ' * 10)
    return "0"


@app.route("/extragen/")
def get_extra_items():
    # extra = r.lrange('extra', 0, -1)

    i, out = 1, ''
    pipe = redis.pipeline()
    # r = requests.get(domain)
    # soup = BeautifulSoup(r.content, "html.parser")
    # extra_url = soup.select_one('a.catalog-newsletter-item__link')['href']
    # extra_url = "https://www.verkkokauppa.com/fi/extra"
    extra_url = "https://view.24mags.com/schedule/verkkokauppa.com/tarjouslehti"

    r = requests.get(extra_url)
    soup = BeautifulSoup(r.content, "html.parser")

    pattern = re.compile('dataUrl: "\/\/(.*?)\?')
    extra_url = re.findall(pattern, soup.get_text())[0]

    # pages[0].active_content.links[0].title
    r = requests.get('https://' + extra_url)
    result = r.json()
    redis.delete('extra_list')

    for page in result['pages']:
        for link in page['active_content']['links']:
            sku = str(link['title'].replace('https://www.verkkokauppa.com', '').replace('/', ''))
            if sku:
                pipe.rpush('extra_list', sku)
                # pipe.expire(10)
                # out += str(i) + " " + sku + "<br>"
                # i += 1

            # print(i, link['title'].replace('https://www.verkkokauppa.com','').replace('/',''))
    pipe.execute()
    # return extra_url
    return redirect(url_for('get_extra'))


@app.route("/pid/<pid>/")
def get_item_by_pid(pid):
    r = requests.get(search_url + pid)
    if (r.status_code != 200):
        r_errors(pid)
        abort(404)

    soup = BeautifulSoup(r.content, "html.parser")
    try:
        item = soup.select('div.list-product')[0]
        sku = item.select_one('div.image__product-id').text
        return get_sumary(sku)
    except:
        r_errors(pid)
        abort(404)


@app.route("/sku/<sku>/")
@app.route("/sku/<sku>/<lng>/")
def get_sumary(sku, lng='en'):
    if lng and lng not in lang:
        abort(400)

    def translate(text='', src='fi', dest=lng):
        return translator.translate(text, dest=dest, src=src).text

    r = requests.get(domain + sku)
    if (r.status_code != 200):
        r_errors(pid)
        abort(404)

    soup = BeautifulSoup(r.content, "html.parser")
    item = {}

    item['name'] = translate(soup.find("h1", {"class": "heading-page product__name-title"}).text)

    try:
        item['avail_helsinki'] = translate(soup.find("span", {"class": "store-availability__status"}).text)
    except:
        item['avail_helsinki'] = '0'

    try:
        item['avail_online'] = translate(soup.find("div", {"class": "web-availability__title"}).text)
    except:
        item['avail_online'] = '0'

    item['price'] = float(soup.find("div", {"class": "price-tag-content__price-tag-price--current"}).text.replace(',', '.').replace(u'\xa0', u'').replace(' ', ''))
    item['price_tax'] = [float(s) for s in soup.find('span', {'class': 'price-tag-tax-text-bold'}).text.split() if s.isdigit()][0] / 100
    item['price_vat'] = round(item['price'] * vat_percent[item['price_tax']], 2)
    item['price_export'] = round(item['price'] - item['price_vat'], 2)
    try:
        item['price_old'] = soup.find("div", {"class": "price-tag-content__price-tag-price--original"}).text.replace(",", ".")
        item['price_old'] = float("".join(item['price_old'].split()))
        # item['price_vat'] = item['price_old'] * vat_percent
    except:
        pass

    item['images'] = [s.replace('/576/', '/') for s in [x['src'] for x in soup.find("ul", {"class": 'ratio-carousel--gallery'}).find_all("img")]]

    item['brand'] = soup.find('a', {'itemprop': 'brand'}).text

    item['product_code'] = soup.find('dd', {'class': 'product-share-details__js-producerId'}).text

    item['categories'] = [translate(x.text) for x in soup.find_all("li", {"class": "breadcrumbs__item"})][1:-1]

    item['highlights'] = [translate(x.text) for x in soup.find("div", {"class": "product-description__highlights"}).find_all('li')]

    features = soup.find("div", {"class": "product-description__description-container"}).find_all('li')
    if features:
        item['features'] = [translate(x.text) for x in features]

    description = soup.find("div", {"class": "product-description__description-container"}).find('font')
    if description:
        item['description'] = description

    try:
        json_data = json.loads(html.unescape(soup.find(id='state').text))
        item['discounts'] = json_data['initialModel']['product']['discounts'][0]['uiLabels']['activeText']
    except:
        pass

    try:
        item['warranty'] = int(soup.find('section', {'class': 'product-details'}).find(string=re.compile("Takuuaika")).findNext('td').contents[0])
    except:
        pass

    try:
        item['package_weight'] = float(soup.find('section', {'class': 'product-details'}).find(string=re.compile("kg")).replace(u'\xa0kg', u'').replace(',', '.'))
        item['package_volume'] = soup.find('section', {'class': 'product-details'}).find(string=re.compile("m³")).replace(u'\xa0', u' ')
        item['package_size'] = " × ".join([x.replace(u'\xa0', u' ') for x in soup.find("section", {"class": "product-details"}).find_all(string=re.compile("cm"))])
    except:
        pass

    try:
        item['product_discounts'] = translate(soup.find('section', {'class': 'product-discounts'}).text)
    except:
        pass

    try:
        product_restrictions = translate(soup.find('div', {'class': 'product-restrictions'}).text)
        if product_restrictions:
            item['product_restrictions'] = product_restrictions
    except:
        pass

    item['timestamp'] = time.time()
    item['ean'] = soup.select_one('td[itemprop="gtin13"]').text
    item['_last_update'] = time.strftime('%d.%m.%Y %H:%M:%S', time.localtime(time.time()))
    item['_sku'] = sku
    item['_url'] = 'https://www.verkkokauppa.com/fi/product/%s' % sku

    # https://www.gigantti.fi/search?SearchTerm=[EAN]
    # balticlivecam.com/cameras/finland/helsinki/helsinki-view-klaus-k-hotel/?embed
    return jsonify(item)


@app.route("/ean/<ean>/")
@app.route("/ean/<ean>.js")
def compare_price(ean):
    gigantti = Gigantti().get_info_by_ean(str(ean))
    try:
        gigantti = Gigantti().get_info_by_ean(str(ean))
    except:
        abort(403)

    if gigantti['ean'] == ean:
        # resp = Response(json.dumps(gigantti), mimetype='application/javascript')
        # resp.headers['Access-Control-Allow-Origin'] = '*'
        # resp.headers['Content-Encoding'] = 'gzip'
        # resp.headers['Cache-Control'] = 'public, max-age=28800'
        # resp.headers['Referrer-Policy'] = 'origin'
        # resp.headers['Access-Control-Max-Age'] = '1728000'
        # resp.headers['Vary'] = 'Accept-Encoding'
        # resp.headers['Last-Modified'] = 'Tue, 17 Apr 2018 20:00:00 GMT'
        # return resp
        # return json.dumps(gigantti)
        return jsonify(gigantti)

    abort(404)


# @app.route("/sku/<sku>/json")
@app.route("/product/<sku>/")
@app.route("/info/<sku>/")
@app.route("/sku/<sku>/json/")
def get_sku(sku):
    r = requests.get("https://verk.com/%s" % sku)
    soup = BeautifulSoup(r.content, 'html.parser')
    sku_json_data = json.loads(html.unescape(soup.find(id='state').text))
    return jsonify(sku_json_data)


@app.route("/info/<sku>/pid/")
def get_pid_by_sku(sku):
    r = requests.get("https://verk.com/%s" % sku)
    soup = BeautifulSoup(r.content, 'html.parser')
    sku_json_data = json.loads(html.unescape(soup.find(id='state').text))
    return str(sku_json_data['initialModel']['product']['financing']['pid'])


@app.route('/menu/<catalog_id>/')
def get_menu(catalog_id):

    def function(lst, parent_index):
        res = ''
        for ii, item in enumerate(lst['childIds']):
            new_childs = json.loads(get_catalog_info(item).get_data())[0]
            print(new_childs['categoryName'])
            res += 'submenu-%d-%d %s<br>' % (parent_index, ii + 1, new_childs['categoryName'])
            if new_childs['childIds']:
                res += function(new_childs, ii + 1)
        return res

    json_data = json.loads(get_catalog_info(catalog_id).get_data())[0]
    res = 'menu for ' + json_data['categoryName'] + '<br>'
    for i, parent in enumerate(json_data['childIds']):
        child = json.loads(get_catalog_info(parent).get_data())[0]
        res += '<br>submenu-%d %s<br>' % (i + 1, child['categoryName'])
        print('===', child['categoryName'])
        if child['childIds']:
            res += function(child, i + 1)

    return res


@app.route('/hi/')
def hi():
    if 'username' in session:
        return 'Logged in as %s' % escape(session['username'])
    return 'You are not logged in'


@app.route('/raisio/json')
def raisio_json():
    return jsonify(Verk().get_extra_raisio(lng='ru'))


@app.route('/raisio/')
def raisio():
    month = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
    locale.setlocale(locale.LC_TIME, 'ru_RU.utf8')
    today = datetime.datetime.today()
    weekday = today.weekday()
    start = today - datetime.timedelta(days=weekday)
    end = start + datetime.timedelta(days=6)
    week = "с %s по %s %s" % (start.strftime('%d'), end.strftime('%d'), month[today.month - 1])
    data = list(Verk().get_extra_raisio(lng='ru'))
    return render_template('raisio.html', data=data, timestamp=time.time(), week=week, cur_eur=get_cur('eur'))


@app.route('/catalog/<catalog_id>/')
def get_catalog(catalog_id):
    api_url = "https://www.verkkokauppa.com/fi/catalog/%s?sort=price" % catalog_id
    data = Verk().get_json(api_url)
    return jsonify(data)


@app.route('/catalog/<catalog_id>/<int:page_num>')
def get_catalog_page(catalog_id, page_num):
    api_url = "https://www.verkkokauppa.com/fi/catalog/%s?sort=price" % catalog_id
    data = Verk().get_json(api_url)
    totalItems = int(data['productPaginator']['totalItems'])
    pageSize = int(data['productPaginator']['pageSize'])
    pages = math.ceil(totalItems / pageSize)

    # for i in range(1, pages + 1):
    #     print(i)

    if totalItems > pageSize and page_num <= pages:
        title = [x['categoryName'] for x in data['categories']['items'] if x['categoryId'] == catalog_id][0]
        print(title)
        api_url = 'https://www.verkkokauppa.com/fi/catalog/%s/%s/products/%d?sort=price' % (catalog_id, title, page_num)
        data = Verk().get_json(api_url)
        return jsonify(data)

    return abort(404)


@app.route('/catalog/<catalog_id>/view/')
def get_catalog_view(catalog_id):
    api_url = "https://www.verkkokauppa.com/fi/catalog/%s?sort=price" % catalog_id
    data = dict(Verk().get_json(api_url))
    # if int(data['productPaginator']['totalItems']) > int(data['productPaginator']['pageSize']):
    brands = set([x['brandSlug'] for x in data['productPaginator']['products']['1']['results']])

    return render_template('catalog.html', data=data, timestamp=time.time(), brands=brands, cur_eur=get_cur('eur'))


@app.route('/catalog/<catalog_id>/items/')
def get_catalog_items(catalog_id):
    api_url = "https://www.verkkokauppa.com/fi/catalog/" + catalog_id
    return jsonify(Verk().get_json(api_url)['productPaginator']['products']['1']['results'])


@app.route('/catalog/<catalog_id>/items/name/')
def get_catalog_items_name(catalog_id):
    api_url = "https://www.verkkokauppa.com/fi/catalog/" + catalog_id
    res = Verk().get_json(api_url)['productPaginator']['products']['1']['results']
    return jsonify([x['name'].split('"')[0] for x in res])


@app.route('/catalog/<catalog_id>/info/')
def get_catalog_info(catalog_id):
    # out = lambda x: 'big' if x > 100 else 'small'
    api_url = "https://www.verkkokauppa.com/fi/catalog/" + catalog_id
    items = Verk().get_json(api_url)['categories']['items']
    child_ids = list(filter(lambda x: x['categoryId'] == str(catalog_id), items))
    return jsonify(child_ids)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['username'] = request.form['username']
        return redirect(url_for('hi'))
    return '''
        <form method="post">
            <p><input type=text name=username>
            <p><input type=submit value=Login>
        </form>
    '''


@app.route('/logout')
def logout():
    # remove the username from the session if it's there
    session.pop('username', None)
    return redirect(url_for('hi'))


def get_plural(x, y):
    inumber = x % 100
    if inumber >= 11 and inumber <= 19:
        y = y[2]
    else:
        iinumber = inumber % 10
        if iinumber == 1:
            y = y[0]
        elif iinumber == 2 or iinumber == 3 or iinumber == 4:
            y = y[1]
        else:
            y = y[2]
    return str(x) + " " + y


def translate(text='', src='fi', dest='en'):
    return translator.translate(text, dest=dest, src=src).text


def r_errors(s):
    redis.sadd('errors', s)


# return currency exchange CUR to RUB
def get_cur(cur='eur'):
    cur_id = {'eur': 'R01239', 'usd': 'R01235'}
    api_url = "http://www.cbr.ru/scripts/XML_daily.asp"
    r = requests.get(api_url)
    tree = xml.fromstring(r.text)
    # print(r.text)
    return tree.find(".//Valute[@ID='%s']/Value" % cur_id[cur]).text.replace(',', '.')


# Default port:
if __name__ == '__main__':
    app.run(debug=True)

# http://www.unicode.org/cldr/charts/29/supplemental/language_plural_rules.html
# https://www.verkkokauppa.com/api/v3/availability?pids=458550
